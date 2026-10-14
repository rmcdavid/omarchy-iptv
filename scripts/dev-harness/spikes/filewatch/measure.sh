#!/bin/bash
# scripts/dev-harness/spikes/filewatch/measure.sh -- R23g (D-SINK-19 round
# 13): what does Quickshell's FileView do to its watch?
#
#   measure.sh [HELPER] [SET]
#                           HELPER: the bin/omarchy-iptv whose `state` verb
#                           makes the atomic rename (default: this tree's)
#                           SET: r23g (default, the round-13 sixteen), r24
#                           (round 14: the dir-absent first session, R24c,
#                           and a symlink at the path, R24b) or r25 (round
#                           15, R25a: what TEXT each echo of a burst of the
#                           view's own saves carries, and in what order)
#
# R25 (round 15). R25a narrows the service's own-write record to the texts
# still in flight, so whether an echo can carry a text of the burst AFTER
# the burst's last save has landed decides whether that is safe (rule 10:
# measured, not assumed). The set issues bursts from INSIDE the probe --
# `burst` n setText in one turn, `spread` one per timer tick -- with every
# signal logged in order with the tag of the text the view holds then, at
# idle and with LOADN busy loops running (bounded by timeout, killed by
# recorded pid). Each line names the loads and flags STALE: a load carrying
# an earlier text of the burst after the burst's last text was reported
# `saved` (the case R25a must not mistake for another writer's).
#
# R24 (round 14) adds three file SHAPES the r23g set never started from:
#   absent  the production fresh-install shape -- the FileView's path is
#           <xs>/omarchy-iptv/state.json with <xs> present and omarchy-iptv/
#           under it ABSENT, so the first load fails 2; the step `mkinit` is
#           the service's start-up (mkdir -p -m 700, then the helper's
#           `state init`, which creates the file)
#   link    state.json is a symbolic link to a regular file in another
#           directory (a dotfiles user); each line also says what is AT the
#           path afterwards and whether the target holds the bytes
#   dangle  state.json is a symbolic link to a file that does not exist
# and two steps: `garbage` (an in-place write of text that is not JSON) and
# `repath` (the view's path set to "" and back, the other re-arm candidate).
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
  WORK=$2 HELPER=$3 SET=${4:-r23g}
  OUT=$WORK/result.txt
  SHAPE=file
  # Where the view looks, per shape (fresh_* sets it before every start).
  FILE=$WORK/state/state.json
  STATE_DIR=$WORK/state
  TARGET=""
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
    FVPROBE_FILE="$FILE" quickshell -p "$WORK/cfg" >>"$WORK/qs.log" 2>&1 &
    QS_PID=$!
    for ((i = 0; i < 100; i++)); do
      reply=$(ipc counts)
      [[ $reply == *'"loaded":1'* || $reply == *'"failed":1'* ]] && return 0
      sleep 0.1
    done
    echo "GAVE UP: the probe did not load within 10 s" >>"$OUT"
    return 1
  }
  SEED='{"version":2,"cacheLayout":0,"favorites":["t:seed"],"recents":[],"lastPlayed":null,"session":null,"sources":[],"savedSearches":[],"hiddenGroups":[],"activeKey":""}'
  reset_dirs() { rm -rf "$WORK/state" "$WORK/xs" "$WORK/target"; }
  fresh_file() {
    reset_dirs
    SHAPE=file FILE=$WORK/state/state.json STATE_DIR=$WORK/state TARGET=""
    mkdir -m 700 "$WORK/state"
    printf '%s\n' "$SEED" >"$FILE"
    chmod 600 "$FILE"
  }
  fresh_absent() {
    reset_dirs
    SHAPE=absent FILE=$WORK/xs/omarchy-iptv/state.json STATE_DIR=$WORK/xs/omarchy-iptv TARGET=""
    mkdir -m 700 "$WORK/xs"
  }
  fresh_nofile() {
    reset_dirs
    SHAPE=nofile FILE=$WORK/state/state.json STATE_DIR=$WORK/state TARGET=""
    mkdir -m 700 "$WORK/state"
  }
  fresh_link() {
    reset_dirs
    SHAPE=link FILE=$WORK/state/state.json STATE_DIR=$WORK/state TARGET=$WORK/target/state.json
    mkdir -m 700 "$WORK/state" "$WORK/target"
    printf '%s\n' "$SEED" >"$TARGET"
    chmod 600 "$TARGET"
    ln -s "$TARGET" "$FILE"
  }
  fresh_dangle() {
    reset_dirs
    SHAPE=dangle FILE=$WORK/state/state.json STATE_DIR=$WORK/state TARGET=$WORK/target/state.json
    mkdir -m 700 "$WORK/state"
    ln -s "$TARGET" "$FILE"
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
      helper)   python3 -I "$HELPER" state --state-dir "$STATE_DIR" favorite add "t:helper$N" >/dev/null 2>&1 ;;
      inplace)  printf '{"version":2,"favorites":["t:inplace%s"],"sources":[]}\n' "$N" >"$FILE" ;;
      garbage)  printf 'not json %s\n' "$N" >"$FILE" ;;
      truncate) : >"$FILE" ;;
      chmod)    chmod 600 "$FILE" ;;
      reload)   ipc reload >/dev/null ;;
      repath)   ipc repath >/dev/null ;;
      mkinit)   mkdir -p -m 700 "$STATE_DIR" && python3 -I "$HELPER" state --state-dir "$STATE_DIR" init >/dev/null 2>&1 ;;
      restart)  stop_qs; start_qs || return 1; before='{"changed":0,"loaded":0,"failed":0,"saved":0,"saveFailed":0}' ;;
    esac
    sleep "$wait"
    if [[ $wait == 0 ]]; then GROUP="$GROUP$what+"; return 0; fi
    what="$GROUP$what"; GROUP="" GROUP_BEFORE=""
    after=$(ipc counts)
    python3 -I - "$what" "$before" "$after" "$FILE" "$SHAPE" "$TARGET" >>"$OUT" <<'PY'
import json, os, stat, sys
what, before, after, path, shape, target = sys.argv[1], json.loads(sys.argv[2] or "{}"), json.loads(sys.argv[3] or "{}"), sys.argv[4], sys.argv[5], sys.argv[6]
d = {k: after.get(k, 0) - before.get(k, 0) for k in ("changed", "loaded", "failed", "saved", "saveFailed")}
try:
    disk = open(path, encoding="utf-8").read()
except OSError:
    disk = None
seen = after.get("text", "") == disk
line = ("  %-14s fileChanged+%d loaded+%d loadFailed+%d saved+%d saveFailed+%d  view==disk:%s"
        % (what, d["changed"], d["loaded"], d["failed"], d["saved"], d["saveFailed"], "yes" if seen else "NO"))
if shape in ("link", "dangle"):
    # What is AT the path now (lstat), and what the link's target holds.
    try:
        st = os.lstat(path)
        kind = "symlink" if stat.S_ISLNK(st.st_mode) else "regular" if stat.S_ISREG(st.st_mode) else "other"
    except OSError:
        kind = "nothing"
    try:
        held = open(target, encoding="utf-8").read()
        tgt = "target:%d bytes%s" % (len(held), " (the view's text)" if held == after.get("text", "") else "")
    except OSError:
        tgt = "target:none"
    line += "  at-path:%s %s" % (kind, tgt)
print(line)
PY
  }
  sequence() {
    local name=$1 s
    shift
    echo "SEQ $name ($SHAPE_NEXT): $*" >>"$OUT"
    "fresh_$SHAPE_NEXT"
    start_qs || return
    for s in "$@"; do step "$s" || break; done
    stop_qs
  }
  mkdir -m 700 -p "$WORK/cfg"
  cp "$HERE/shell.qml" "$WORK/cfg/shell.qml"
  : >"$OUT"
  SHAPE_NEXT=file
  if [[ $SET == r25 ]]; then
    BURNERS=()
    burn_on() {
      local i
      for ((i = 0; i < ${LOADN:-8}; i++)); do
        timeout 120 sh -c 'while :; do :; done' &
        BURNERS+=($!)
      done
    }
    burn_off() {
      local p
      for p in "${BURNERS[@]}"; do kill -TERM "$p" 2>/dev/null; wait "$p" 2>/dev/null; done
      BURNERS=()
    }
    trap 'burn_off; stop_qs' EXIT
    # One burst: KIND burst|spread, N saves, PAD bytes each, MS between
    # (spread only). Prints the ordered events and the verdict.
    burst_step() {
      local kind=$1 n=$2 pad=$3 ms=${4:-0} prefix ev
      N=$((N + 1)); prefix="b${N}x"
      ipc clearEvents >/dev/null
      if [[ $kind == burst ]]; then ipc burst "$n" "$prefix" "$pad" >/dev/null
      else ipc spread "$n" "$prefix" "$pad" "$ms" >/dev/null; fi
      sleep "${BURST_WAIT:-2}"
      ev=$(ipc events)
      python3 -I - "$kind n=$n pad=$pad ms=$ms load=${LOADSTATE:-idle}" "$prefix" "$n" "$ev" >>"$OUT" <<'PY'
import json, sys
label, prefix, n, ev = sys.argv[1], sys.argv[2], int(sys.argv[3]), json.loads(sys.argv[4] or "[]")
final = prefix + str(n)
short = lambda t: t.replace(prefix, "T") if t.startswith(prefix) else t
landed = None
loads, stale, superseded, notlast = [], [], [], []
saved_max = 0
last_saved = None
for i, e in enumerate(ev):
    kind, _, tag = e.partition(":")
    num = int(tag[len(prefix):]) if tag.startswith(prefix) and tag[len(prefix):].isdigit() else None
    if kind == "saved":
        if num is not None: saved_max = max(saved_max, num)
        last_saved = tag
        if tag == final and landed is None: landed = i
    if kind == "loaded":
        loads.append(short(tag) + ("@after-final" if landed is not None else ""))
        if landed is not None and tag != final: stale.append(short(tag))
        if num is not None and num < saved_max: superseded.append(short(tag))
        if tag != last_saved: notlast.append(short(tag))
print("  %-40s saved:%d loaded:%d landed:%s loads=[%s] STALE:%s superseded-at-load:%s not-the-last-saved:%s"
      % (label, sum(1 for e in ev if e.startswith("saved:")), len(loads), "yes" if landed is not None else "NO",
         ",".join(loads), ",".join(stale) or "none", ",".join(superseded) or "none", ",".join(notlast) or "none"))
print("    order: " + " ".join(short(e.partition(":")[0]) + ":" + short(e.partition(":")[2]) for e in ev))
PY
    }
    for LOADSTATE in idle loaded; do
      [[ $LOADSTATE == loaded ]] && burn_on
      echo "SEQ burst ($LOADSTATE, load $(cut -d' ' -f1 /proc/loadavg))" >>"$OUT"
      fresh_file
      start_qs || break
      for ((rep = 0; rep < ${REPS:-3}; rep++)); do
        burst_step burst 2 0
        burst_step burst 3 2000
        burst_step burst 5 4000
        burst_step burst 10 4000
        burst_step spread 3 4000 0
        burst_step spread 5 4000 0
        burst_step spread 5 4000 5
        burst_step spread 10 4000 2
      done
      stop_qs
      [[ $LOADSTATE == loaded ]] && burn_off
    done
    echo "END" >>"$OUT"
    exit 0
  fi
  if [[ $SET == r24 ]]; then
    # R24c: the production fresh shape. Q is the session as it ships (nothing
    # re-arms); R the explicit reload() after the start-up mkdir/init; S the
    # path reset; T reload then an own save; U the same with the directory
    # PRESENT and the file absent, for contrast.
    SHAPE_NEXT=absent
    sequence Q mkinit helper inplace garbage
    sequence R mkinit reload helper inplace garbage
    sequence S mkinit repath helper inplace garbage
    sequence T mkinit reload own helper garbage
    sequence R2 mkinit reload helper own inplace
    # U: the directory exists, the file does not (the r23g shapes all had one).
    SHAPE_NEXT=nofile
    sequence U mkinit helper inplace garbage
    # R24b: what the view's OWN save and the helper's write do to a VALID
    # symlink at the path, and what each sees of the other.
    SHAPE_NEXT=link
    sequence V own helper inplace
    sequence W helper own helper
    SHAPE_NEXT=dangle
    sequence X own
    echo "END" >>"$OUT"
    exit 0
  fi
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
SET=${2:-r23g}
RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
WORK=$(mktemp -d "$RUNTIME/omarchy-iptv-fw.XXXXXX") || exit 2
chmod 700 "$WORK"
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "filewatch: set $SET, work $WORK, helper $HELPER, step wait ${STEP_WAIT}s, load $(cut -d' ' -f1-3 /proc/loadavg)"
env -u WAYLAND_DISPLAY -u DISPLAY WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
  "$ROOT/scripts/dev-harness/private-bus.sh" "$WORK/bus" 240 \
  cage -- "$0" --child "$WORK" "$HELPER" "$SET" >"$WORK/cage.log" 2>&1
status=$?
if [[ -s $WORK/result.txt ]]; then cat "$WORK/result.txt"; else echo "NO RESULT (cage exit $status)"; tail -n 20 "$WORK/cage.log"; fi
grep -c 'FVPROBE' "$WORK/qs.log" 2>/dev/null | sed 's/^/probe signal lines: /'
exit "$status"
