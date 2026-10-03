#!/bin/bash
# scripts/dev-harness/rewind-scenario.sh -- live rewind (M5-01, lane Q) on
# REAL mpv against a LOCAL live-like stream, through the harness IPC.
# Holds the display: opens a real mpv window and the guide overlay for about
# four minutes, and reaps everything it starts. Plan: docs/QA-REWIND.md.
#
# THE STREAM. Two HLS playlists with a sliding window (6 x 2 s segments,
# ffmpeg -re from lavfi, ~1.4 Mbps on the wire, a burned-in clock in the
# picture), served from this script's own loopback server on 127.0.0.1:8771
# (8765 is run.sh --serve, 8766 argv-scenario, 8767 text-scenario). mpv
# reads them exactly as it reads a provider's channel: `seekable` false,
# `file-format` hls, `demuxer-cache-state` growing one second per second
# (measured; docs/QA-REWIND.md section 2). The player's cache is SHRUNK to
# 2 MiB back + 4 MiB forward through the plugin's own `mpvArgs` setting, so
# the window plateaus at about 30 s and the floor is evicted inside the run
# -- at mpv's 200 MiB default the floor would not move for twenty minutes
# at this bitrate, and R4's refusal needs an evicted floor.
#
# Checks, each OBSERVED on the player's own socket (fixtures/rewind-probe.py)
# and never inferred from the reply under test:
#   R0  the stream control: history grows at ~1 s/s on this player (green on
#       every tree; it is the one check that is not about the feature)
#   R1  `player seek --by -10` moves time-pos by -10 within tolerance,
#       the reply says so, and playback continues
#   R2  `--by 10` moves forward by 10
#   R3  `--live` lands at the cache edge: atEdge, ahead <= 1 s, behindLive < 2
#   R4  an over-long seek: raw `seek -100000 relative` on the socket is
#       DROPPED by mpv alone (success, unmoved), and the helper's `--by
#       -100000` is CLAMPED to the floor with the reply saying clamped
#       -- MUST be red against today's tree (2d7df1f)
#   R5  at the floor, `--by -10` reports atFloor rather than a false success
#   R6  no helper reply and no harness log line carries a URL or the fixture
#       host (a control proves the capture is non-empty)
#   R7  the service readout: harness `back 10` and the plugin IPC verb
#       `back 10`; `rewind.behindLive` and `playbackStateText` follow
#   R8  the bar: the history glyph U+F02DA and `-m:ss` outside the name
#   R9  a zap resets the readout to ABSENT (null), never 0, then returns
#   R10 pause then rewind: position moves while paused, the count goes UP
#   R11 rewind then pause: position holds, the count goes up, resume is from
#       the rewound point
#   R12 run.sh restart-shell: the new shell recovers behindLive from the
#       player, same player pid
#   R13 a held `b` (20 presses, 60 ms apart, through wtype into the guide in
#       list mode) is COALESCED: fewer helper runs than presses, and the
#       position reflects the capped sum
#   R14 and it never trips the health restart: same pid, intent counter
#       (playSeq and the lock record) unmoved, healthSkips 0
#   R15 per-press budget: the helper's spawn-to-reply for `player seek`
#       stays within 300 ms (median of five), the probe's own bound
#
# Evidence rule (CLAUDE.md 10/11): `--baseline <ref>` exports that tree and
# runs the same checks against it. Against 2d7df1f every check but R0 is
# red: the verb, the service state and the harness verbs are all absent,
# and the sentinels (qa-lib.sh) make an absent answer a FAIL, never a pass.
#
#   scripts/dev-harness/rewind-scenario.sh
#   scripts/dev-harness/rewind-scenario.sh --baseline 2d7df1f
#
# Output: one PASS/FAIL line per assertion and a summary. No URL is printed.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
PROBE="$HERE/fixtures/rewind-probe.py"
SWEEP="$HERE/fixtures/rewind-sweep.py"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
FIX="$SCRATCH/fixtures/rewind"
LOG="$SCRATCH/rewind-scenario.log"
HLOG="$SCRATCH/harness.log"
SOCK="$SCRATCH/runtime/omarchy-iptv/mpv.sock"
PLUGIN_ROOT=${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}
PLUGIN_ID="io.github.rmcdavid.iptv"
PORT=8771
HOST="127.0.0.1:$PORT"
STREAM_S=540
# The names that join the lanes (design 2.1-2.5): the step, the display
# threshold and the glyph. Spelled here so a drift is a red check.
STEP=10
SHOW_S=2
HISTORY_GLYPH=$'\xf3\xb0\x8b\x9a'   # U+F02DA, UTF-8 bytes (ASCII file, rule 8)
BASELINE=""
EXPORT_DIR=""
WORK=""
pass=0
fail=0
checks=0

# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

while (($# > 0)); do
  case $1 in
    --baseline) BASELINE=$2; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

ok()  { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad() { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
is()  { checks=$((checks + 1)); if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }
ck()  { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1${3:+ ($3)}"; fi; }
# near <a> <b> <tol>: "0" when both are numbers within tol, "1" when not,
# "2" (never equal to "0") when either side is not a number -- a sentinel
# or an empty answer cannot satisfy a numeric check.
near() { python3 -c '
import sys
try: print(0 if abs(float(sys.argv[1]) - float(sys.argv[2])) <= float(sys.argv[3]) else 1)
except Exception: print(2)' "$1" "$2" "$3"; }
# fdelta <before> <after>: after - before as a float, or "x" when either is
# not a number. qa_delta is integer-only by design (it subtracts counters);
# the rewind readings are floats, and feeding them to it printed NODELTA on
# every run of the integrated tree (F-HARNESS-3) -- a red that was the
# instrument's, invisible on the pre-feature tree where the field was
# NOSTATE anyway.
fdelta() { python3 -c '
import sys
try: print(round(float(sys.argv[2]) - float(sys.argv[1]), 3))
except Exception: print("x")' "$1" "$2"; }
# ge <a> <b>: "0" when a >= b as numbers, else "1"/"2" as above.
ge() { python3 -c '
import sys
try: print(0 if float(sys.argv[1]) >= float(sys.argv[2]) else 1)
except Exception: print(2)' "$1" "$2"; }

ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
# The PLUGIN's own IpcHandler, reachable with the harness environment
# (SPIKE-LIVE-REWIND 12.5 measured the form): the verbs a user binds.
pipc() {
  local wl=${WAYLAND_DISPLAY:-wayland-1}
  [[ $wl == /* ]] || wl="$REAL_RUNTIME/$wl"
  XDG_RUNTIME_DIR="$SCRATCH/runtime" WAYLAND_DISPLAY="$wl" qs ipc -p "$SCRATCH/root" call "$PLUGIN_ID" "$@" 2>/dev/null
}
svc()  { qa_field "$1" "$(ipc state)"; }
# pause_toggle: the plugin's `pause` verb through the single control slot,
# which answers `busy` while a status tick or a seek holds it. That is a
# transient, not a refusal (D-PLY-23's shape), so retry a bounded five
# times; anything else is the answer.
pause_toggle() {
  local i a
  for ((i = 0; i < 5; i++)); do
    a=$(pipc pause)
    [[ $a == busy ]] || { printf '%s\n' "$a"; return 0; }
    sleep 0.5
  done
  printf '%s\n' "$a"
}
rf()   { qa_json_field "$1" "$2"; }
# The rewind snapshot fields lane S adds (`rewind`, `playbackStateText`,
# `barLabel`): read from the service half first, then the guide half, then
# the widget, so the join holds wherever the snapshot places them.
# `rewind` must be able to say "null" (readout absent) distinctly from
# "undefined" (a tree that has no such property), because R9's whole point
# is null-not-zero, and a defensive snapshot that maps undefined to null
# would otherwise pass R9 on a tree with no feature. R9 therefore also
# requires the readout to come BACK with numbers (positive control).
snap() {
  python3 -c '
import json, sys
key = sys.argv[1]
try:
    st = json.loads(sys.argv[2])
except Exception:
    print("NOSTATE"); raise SystemExit(0)
try:
    w = json.loads(sys.argv[3])
except Exception:
    w = {}
for part in (st.get("service"), st.get("guide"), w, st):
    if isinstance(part, dict) and key in part:
        v = part[key]
        print("null" if v is None else (json.dumps(v) if isinstance(v, (bool, dict, list)) else v))
        raise SystemExit(0)
print("undefined")' "$1" "$(ipc state)" "$(ipc widget)"
}
rw() {   # rw <field>: one field of the service's rewind object, through the sentinels
  svc "d['rewind']['$1'] if isinstance(d.get('rewind'), dict) else None"
}
player_pids()  { pgrep -f "input-ipc-server=$SOCK" 2>/dev/null; }
player_count() { player_pids | wc -l | tr -d ' '; }
player_pid()   { player_pids | head -1; }
player_seq()   { svc "d['playSeq']"; }
lock_seq() {
  python3 -c '
import json, sys
try:
    v = json.load(open(sys.argv[1])).get("seq")
except Exception:
    print("NOFILE"); raise SystemExit(0)
print("NOFIELD" if v is None else v)' "$SCRATCH/runtime/omarchy-iptv/player.lock" 2>/dev/null \
    || printf '%s\n' "$QA_NO_FILE"
}
until_eq() {   # until_eq <want> <secs> <cmd...>
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ "$("$@")" == "$want" ]] && return 0
    sleep 0.1
  done
  return 1
}
wait_log() {
  local re=$1 secs=$2 i
  for ((i = 0; i < secs * 10; i++)); do
    grep -qE "$re" "$HLOG" 2>/dev/null && return 0
    sleep 0.1
  done
  return 1
}
# The player's own numbers, off the socket. `measure SECONDS` runs for
# SECONDS, so its bound is SECONDS plus the connect; a flat 12 s bound once
# killed a 12 s measurement before it printed, and R0 read NOSTATE.
probe() {
  local bound=12
  [[ ${1-} == measure ]] && bound=$(( ${3:-30} + 10 ))
  timeout "$bound" python3 "$PROBE" "$@" 2>/dev/null
}
pos()     { rf 'd["pos"]' "$(probe range "$SOCK")"; }
history() { rf 'd["history"]' "$(probe range "$SOCK")"; }
floor_()  { rf 'd["floor"]' "$(probe range "$SOCK")"; }
# until_history <seconds> <bound>: the plateau takes about 33 s to reach.
until_history() {
  local want=$1 secs=$2 i h
  for ((i = 0; i < secs; i++)); do
    h=$(history)
    [[ $(ge "$h" "$want") == 0 ]] && return 0
    sleep 1
  done
  return 1
}
# until_rw <field> <min> <max> <secs>: a rewind field inside a band.
until_rw() {
  local f=$1 lo=$2 hi=$3 secs=$4 i v
  for ((i = 0; i < secs * 4; i++)); do
    v=$(rw "$f")
    [[ $(ge "$v" "$lo") == 0 && $(ge "$hi" "$v") == 0 ]] && return 0
    sleep 0.25
  done
  return 1
}
# The verb under test. Every reply is appended to the capture R6 sweeps.
HELPER=""
seek() {   # seek <--by N | --live>
  local out
  out=$(timeout 10 python3 "$HELPER" player seek --socket "$SOCK" "$@" 2>>"$WORK/seek.err")
  printf '%s\n' "$out" >>"$WORK/replies.jsonl"
  printf '%s' "$out"
}

STREAM_PIDS=()
cleanup() {
  ipc close >/dev/null 2>&1
  "$RUN" reap >/dev/null 2>&1
  local p i
  for p in "${STREAM_PIDS[@]}"; do kill -TERM "$p" 2>/dev/null; done
  for ((i = 0; i < 30; i++)); do
    local alive=0
    for p in "${STREAM_PIDS[@]}"; do kill -0 "$p" 2>/dev/null && alive=1; done
    (( alive )) || break
    sleep 0.1
  done
  for p in "${STREAM_PIDS[@]}"; do kill -KILL "$p" 2>/dev/null; done
  # The server's pid is read from the LISTENER, never from $!.
  local lpid
  lpid=$(ss -ltnp 2>/dev/null | grep ":$PORT " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
  [[ -n $lpid ]] && kill "$lpid" 2>/dev/null
  rm -rf "$FIX"
  [[ -n $EXPORT_DIR && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  [[ -n $WORK && -d $WORK ]] && rm -rf "$WORK"
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ---- preflight
pgrep -x hyprlock >/dev/null && { echo "screen is locked" >&2; exit 2; }
command -v ffmpeg >/dev/null || { echo "ffmpeg is required for the local stream" >&2; exit 2; }
command -v mpv >/dev/null || { echo "mpv is required" >&2; exit 2; }
command -v wtype >/dev/null || { echo "wtype is required (R13)" >&2; exit 2; }
ss -ltn 2>/dev/null | grep -q ":$PORT " && { echo "port $PORT is already in use" >&2; exit 2; }
qa_safe_path "$SCRATCH" || { echo "unsafe scratch path" >&2; exit 2; }

# ---- which checkout is under test
if [[ -n $BASELINE ]]; then
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-rewind-baseline-XXXXXX")
  git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR" || { echo "could not export $BASELINE" >&2; exit 2; }
  PLUGIN_ROOT="$EXPORT_DIR"
  echo "== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported"
fi
export OMARCHY_IPTV_PLUGIN_ROOT="$PLUGIN_ROOT"
HELPER=$(readlink -f "$PLUGIN_ROOT/bin/omarchy-iptv")
WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-rewind-XXXXXX")
: >"$WORK/replies.jsonl"
echo "== plugin tree $PLUGIN_ROOT   scratch $SCRATCH"

# ---- the local live stream: a loopback server and two sliding-window HLS
# outputs. The server is a threading one (a segment fetch must not block
# the playlist refresh), quiet, and its pid is taken from `ss`.
mkdir -p "$FIX/a" "$FIX/b"
python3 - "$PORT" "$FIX" >/dev/null 2>&1 <<'PY' &
import functools, http.server, sys
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])),
    functools.partial(Quiet, directory=sys.argv[2])).serve_forever()
PY
for i in $(seq 1 30); do ss -ltn 2>/dev/null | grep -q ":$PORT " && break; sleep 0.1; done
ss -ltn 2>/dev/null | grep -q ":$PORT " || { echo "the fixture server did not start" >&2; exit 2; }
start_stream() {   # start_stream <dir> <size> <tone-hz>
  ffmpeg -hide_banner -loglevel error -re \
    -f lavfi -i "testsrc=size=$2:rate=25" -f lavfi -i "sine=frequency=$3:sample_rate=44100" \
    -vf "drawtext=text='%{pts\:hms}':fontsize=64:fontcolor=white:box=1:boxcolor=black@0.6:x=(w-tw)/2:y=(h-th)/2" \
    -c:v libx264 -preset ultrafast -tune zerolatency -g 50 -keyint_min 50 -sc_threshold 0 \
    -b:v 1000k -maxrate 1000k -bufsize 2000k -pix_fmt yuv420p -c:a aac -b:a 64k -t "$STREAM_S" \
    -f hls -hls_time 2 -hls_list_size 6 -hls_flags delete_segments+independent_segments \
    -hls_segment_filename "$1/seg%05d.ts" "$1/live.m3u8" 2>>"$WORK/ffmpeg.err" &
  STREAM_PIDS+=("$!")
}
start_stream "$FIX/a" 640x360 440
start_stream "$FIX/b" 480x270 660
for i in $(seq 1 100); do
  [[ $(grep -c '\.ts' "$FIX/a/live.m3u8" 2>/dev/null) -ge 3 && $(grep -c '\.ts' "$FIX/b/live.m3u8" 2>/dev/null) -ge 3 ]] && break
  sleep 0.2
done
[[ $(grep -c '\.ts' "$FIX/a/live.m3u8" 2>/dev/null) -ge 3 ]] || { echo "the stream did not start (see $WORK/ffmpeg.err)" >&2; cat "$WORK/ffmpeg.err" >&2; exit 2; }
sed -e "s|__LIVE_A__|http://$HOST/a/live.m3u8|" -e "s|__LIVE_B__|http://$HOST/b/live.m3u8|" \
  "$HERE/fixtures/rewind.m3u.in" >"$FIX/rewind.m3u"

# ---- the harness, detached (restart-shell needs it), with the shrunken
# cache on the plugin's own mpvArgs setting. Recorded in last-start.env so
# the restarted shell carries the same.
"$RUN" reap >/dev/null 2>&1
"$RUN" clean >/dev/null
: >"$LOG"
: >"$HLOG"
export OMARCHY_IPTV_MPV_ARGS="--demuxer-max-back-bytes=2MiB --demuxer-max-bytes=4MiB"
"$RUN" --detach --timeout 0 --playlist "$FIX/rewind.m3u" >>"$LOG" 2>&1
wait_log 'service loaded' 20 || { bad "the harness did not start (see $LOG)"; exit 1; }
until_eq 2 20 svc "d['channels']" || { bad "the fixture playlist did not load"; exit 1; }

echo "== play A and wait for the window to fill"
ipc play "t:rw.a" >/dev/null
until_eq 1 15 player_count || { bad "no player started"; exit 1; }
PID1=$(player_pid)
until_eq true 10 svc "d['playing']" || true
w=$(probe wait "$SOCK" 25)
ck "the player is playing A (time-pos advancing; positive control)" '[[ "$(rf "d[\"ok\"]" "$w")" == true ]]'
cmd=$(qa_cmdline "$PID1")
ck "the shrunken cache reached the player's argv (control for R4)" '[[ "$cmd" == *"--demuxer-max-back-bytes=2MiB"* && "$cmd" == *"--demuxer-max-bytes=4MiB"* ]]'

echo "== R0 the stream control"
m=$(probe measure "$SOCK" 12 2)
rate=$(rf 'd["historyRatePerS"]' "$m")
ck "R0 history grows at ~1 s/s on the local stream ($rate)" '[[ $(near "$rate" 1.0 0.2) == 0 ]]'
until_history 26 60 || bad "R0 the window never filled (history $(history))"
printf '   R0 at the plateau: history %s floor %s\n' "$(history)" "$(floor_)"

echo "== R1 back 10"
p0=$(pos)
r=$(seek --by -10)
p1=$(pos)
is "R1 the reply is a seek reply" "$(rf 'd["kind"]' "$r")" "seek"
is "R1 ok" "$(rf 'd["ok"]' "$r")" "true"
is "R1 mode by" "$(rf 'd["mode"]' "$r")" "by"
ck "R1 applied -10 ($(rf 'd["applied"]' "$r"))" '[[ $(near "$(rf "d[\"applied\"]" "$r")" -10 0.01) == 0 ]]'
is "R1 not refused" "$(rf 'd["refused"]' "$r")" "false"
ck "R1 time-pos moved back by 10 on the socket (before $p0, after $p1)" '[[ $(near "$(python3 -c "print(float(\"$p1\")-float(\"$p0\"))" 2>/dev/null || echo x)" -10 2.5) == 0 ]]'
ck "R1 the reply's position agrees with the socket" '[[ $(near "$(rf "d[\"rewind\"][\"position\"]" "$r")" "$p1" 2.5) == 0 ]]'
ck "R1 the reply reports ~10 s behind live" '[[ $(near "$(rf "d[\"rewind\"][\"behindLive\"]" "$r")" 10 2.5) == 0 ]]'
ck "R1 playback continues from the rewound point" '[[ "$(rf "d[\"ok\"]" "$(probe wait "$SOCK" 8)")" == true ]]'

echo "== R2 forward 10 (from 20 behind)"
seek --by -10 >/dev/null
p0=$(pos)
r=$(seek --by 10)
p1=$(pos)
is "R2 ok" "$(rf 'd["ok"]' "$r")" "true"
ck "R2 applied +10" '[[ $(near "$(rf "d[\"applied\"]" "$r")" 10 0.01) == 0 ]]'
ck "R2 time-pos moved forward by 10 on the socket (before $p0, after $p1)" '[[ $(near "$(python3 -c "print(float(\"$p1\")-float(\"$p0\"))" 2>/dev/null || echo x)" 10 2.5) == 0 ]]'
ck "R2 the reply reports ~10 s behind live" '[[ $(near "$(rf "d[\"rewind\"][\"behindLive\"]" "$r")" 10 2.5) == 0 ]]'

echo "== R3 live"
r=$(seek --live)
is "R3 mode live" "$(rf 'd["mode"]' "$r")" "live"
is "R3 atEdge" "$(rf 'd["atEdge"]' "$r")" "true"
ck "R3 ahead <= 1 s ($(rf 'd["rewind"]["ahead"]' "$r"))" '[[ $(ge 1.0 "$(rf "d[\"rewind\"][\"ahead\"]" "$r")") == 0 ]]'
ck "R3 behindLive below the display threshold ($(rf 'd["rewind"]["behindLive"]' "$r"))" '[[ $(ge "$SHOW_S" "$(rf "d[\"rewind\"][\"behindLive\"]" "$r")") == 0 && $(ge "$(rf "d[\"rewind\"][\"behindLive\"]" "$r")" 0) == 0 ]]'
# The socket's own read a moment later: on a 2 s-segment stream the cache
# end moves in 2 s steps as segments land, so `ahead` at the edge is
# anywhere up to a segment plus the 0.5 s margin (F-RWD-12's quantisation,
# on arrival rather than eviction); the helper's own read, a millisecond
# after its seek, is the 0.5 s R3 asserts above.
r3a=$(rf 'd["ahead"]' "$(probe range "$SOCK")")
ck "R3 the socket agrees it is at the edge, within a segment ($r3a <= 2.5)" '[[ $(ge 2.5 "$r3a") == 0 ]]'

echo "== R4 the over-long seek: mpv drops it, the helper clamps it (MUST be red on 2d7df1f)"
# The refusal needs an EVICTED floor: while the start of the stream is
# still cached (floor 0) mpv clamps an over-long relative seek to 0 instead
# (SPIKE 4.3, and measured on this stream), and the control below would
# read a clamp as a drop. The floor evicts in 4-6 s steps once the window
# is full, so wait for it to have moved, bounded.
until_history 26 40 || true
for ((i = 0; i < 60; i++)); do [[ $(ge "$(floor_)" 1.0) == 0 ]] && break; sleep 1; done
ck "R4 control: the floor has been evicted (floor $(floor_) > 0)" '[[ $(ge "$(floor_)" 1.0) == 0 ]]'
raw=$(probe seek "$SOCK" -100000 relative)
is "R4 control: mpv alone replies success to seek -100000" "$(rf 'd["reply"]' "$raw")" "success"
ck "R4 control: and does not move (moved $(rf 'd["moved"]' "$raw"))" '[[ $(near "$(rf "d[\"moved\"]" "$raw")" 0 1.0) == 0 ]]'
ck "R4 control: playback carries on" '[[ $(ge "$(rf "d[\"later\"]" "$raw")" "$(rf "d[\"after\"]" "$raw")") == 0 ]]'
f0=$(floor_); p0=$(pos)
r=$(seek --by -100000)
p1=$(pos); f1=$(floor_)
is "R4 the helper says clamped" "$(rf 'd["clamped"]' "$r")" "true"
is "R4 and not refused" "$(rf 'd["refused"]' "$r")" "false"
ck "R4 clampedTo is the floor plus the margin (floor $f0..$f1, clampedTo $(rf 'd["clampedTo"]' "$r"))" '[[ $(near "$(rf "d[\"clampedTo\"]" "$r")" "$(python3 -c "print(float(\"$f1\")+2)" 2>/dev/null || echo x)" 6.5) == 0 ]]'
ck "R4 time-pos landed near the floor on the socket (before $p0, after $p1)" '[[ $(near "$p1" "$(python3 -c "print(float(\"$f1\")+2)" 2>/dev/null || echo x)" 6.5) == 0 ]]'
ck "R4 applied is the whole history, not the request ($(rf 'd["applied"]' "$r"))" '[[ $(near "$(rf "d[\"applied\"]" "$r")" "$(python3 -c "print(float(\"$p1\")-float(\"$p0\"))" 2>/dev/null || echo x)" 2.5) == 0 ]]'
ck "R4 playback continues from the floor" '[[ "$(rf "d[\"ok\"]" "$(probe wait "$SOCK" 8)")" == true ]]'

echo "== R5 at the floor"
p0=$(pos)
r=$(seek --by -10)
p1=$(pos)
is "R5 atFloor reported" "$(rf 'd["atFloor"]' "$r")" "true"
ck "R5 no false 10 s movement (before $p0, after $p1)" '[[ $(ge "$(python3 -c "print(float(\"$p1\")-float(\"$p0\"))" 2>/dev/null || echo x)" -8) == 0 ]]'
ck "R5 the reply reports a behindLive near the whole window ($(rf 'd["rewind"]["behindLive"]' "$r"))" '[[ $(ge "$(rf "d[\"rewind\"][\"behindLive\"]" "$r")" 20) == 0 ]]'

echo "== R6 no URL anywhere"
# The control proves the capture holds replies; a vacuous scan is a FAIL.
checks=$((checks + 1))
if qa_leak_scan '"kind"' "://|$HOST|live\\.m3u8|/rewind/" "$WORK/replies.jsonl"; then ok "R6 no helper reply carries a URL or the fixture host ($(qa_count '"kind"' "$WORK/replies.jsonl") replies)"
else bad "R6 helper replies: leak or vacuous capture (status $?; $(wc -l <"$WORK/replies.jsonl") lines)"; fi
checks=$((checks + 1))
if qa_leak_scan 'service loaded' "://|$HOST|live\\.m3u8|/rewind/" "$HLOG"; then ok "R6 the harness log carries neither a URL nor the fixture host"
else bad "R6 harness log: leak or vacuous (status $?)"; fi

echo "== R7 the service readout through the harness and the plugin verbs"
ipc live >/dev/null 2>&1
until_history 24 40 || true
until_rw behindLive 0 "$SHOW_S" 6 || true
is "R7 the harness verb back answers" "$(rf 'd["ok"]' "$(ipc back 10)")" "true"
until_rw behindLive 8 13 6 || true
ck "R7 service rewind.behindLive ~10 ($(rw behindLive))" '[[ $(near "$(rw behindLive)" 10 2.5) == 0 ]]'
ck "R7 playbackStateText says so ($(snap playbackStateText))" '[[ "$(snap playbackStateText)" =~ ^0:(0[8-9]|1[0-3])\ behind\ live$ ]]'
pr=$(pipc back 10)
is "R7 the plugin IPC verb back answers JSON ok" "$(rf 'd["ok"]' "$pr")" "true"
until_rw behindLive 18 23 6 || true
ck "R7 and the readout followed it (~20, $(rw behindLive))" '[[ $(near "$(rw behindLive)" 20 2.5) == 0 ]]'
ck "R7 the hint pairs name the keys (b back, w forward, g live)" '[[ "$(snap keyboardMap)" == *"b=back"* && "$(snap keyboardMap)" == *"w=forward"* && "$(snap keyboardMap)" == *"g=live"* ]]'

echo "== R8 the bar"
lbl=$(snap barLabel)
ck "R8 barLabel carries -m:ss outside the name ($lbl)" '[[ "$lbl" =~ -0:(1[7-9]|2[0-4])$ ]]'
glyph=$(rf 'd["glyph"]' "$(ipc widget)")
ck "R8 the bar glyph is the history glyph U+F02DA while behind live" '[[ "$glyph" == "$HISTORY_GLYPH" ]]'

echo "== R9 a zap resets the readout to ABSENT, never 0"
ipc zap 1 >/dev/null
z=$(snap rewind)
is "R9 rewind is null right after the zap (not 0, not undefined)" "$z" "null"
is "R9 playbackStateText is empty right after the zap" "$(snap playbackStateText)" ""
until_eq "t:rw.b" 10 svc "d['nowPlaying']['id'] if d.get('nowPlaying') else None" || true
is "R9 now playing B" "$(svc "d['nowPlaying']['id'] if d.get('nowPlaying') else None")" "t:rw.b"
is "R9 the same player" "$(player_pid)" "$PID1"
probe wait "$SOCK" 25 >/dev/null
until_rw behindLive 0 "$SHOW_S" 20 || true
ck "R9 the readout comes back with numbers at live ($(rw behindLive); positive control)" '[[ $(ge "$SHOW_S" "$(rw behindLive)") == 0 && $(ge "$(rw behindLive)" 0) == 0 ]]'
is "R9 and the text is empty at live" "$(snap playbackStateText)" ""

echo "== R10 pause, then rewind"
until_history 16 40 || true
is "R10 paused through the plugin verb" "$(pause_toggle)" "paused"
# mpv's time-pos creeps a few frames (0.12-0.16 s seen) in the first
# half-second after the pause while the audio drains; the spike's 0.000 s
# drift was measured from 10 s in. Let it settle before reading.
sleep 1
p0=$(pos)
ipc back 10 >/dev/null
sleep 1.5
p1=$(pos)
is "R10 still paused on the socket" "$(rf 'd["paused"]' "$(probe range "$SOCK")")" "true"
ck "R10 the position moved back 10 while paused (before $p0, after $p1)" '[[ $(near "$(python3 -c "print(float(\"$p1\")-float(\"$p0\"))" 2>/dev/null || echo x)" -10 2.5) == 0 ]]'
b0=$(rw behindLive); sleep 3; b1=$(rw behindLive)
ck "R10 behindLive counts UP while paused ($b0 -> $b1)" '[[ $(near "$(fdelta "$b0" "$b1")" 3 1.5) == 0 ]]'
ck "R10 playbackStateText says paused ($(snap playbackStateText))" '[[ "$(snap playbackStateText)" == paused* && "$(snap playbackStateText)" == *"behind live" ]]'
is "R10 resumed" "$(pause_toggle)" "playing"
w=$(probe wait "$SOCK" 8)
ck "R10 playback resumed from the rewound point ($(rf 'd["pos"]' "$w") vs $p1)" '[[ "$(rf "d[\"ok\"]" "$w")" == true && $(near "$(rf "d[\"pos\"]" "$w")" "$p1" 4.0) == 0 ]]'

echo "== R11 rewind, then pause"
ipc back 10 >/dev/null
sleep 1.5
is "R11 paused" "$(pause_toggle)" "paused"
sleep 1
p0=$(pos); sleep 2; p1=$(pos)
ck "R11 the position holds while paused ($p0, $p1)" '[[ $(near "$p0" "$p1" 0.25) == 0 ]]'
b0=$(rw behindLive); sleep 3; b1=$(rw behindLive)
ck "R11 behindLive counts up ($b0 -> $b1)" '[[ $(near "$(fdelta "$b0" "$b1")" 3 1.5) == 0 ]]'
is "R11 resumed" "$(pause_toggle)" "playing"
w=$(probe wait "$SOCK" 8)
ck "R11 resumed from the held position ($(rf 'd["pos"]' "$w") vs $p1)" '[[ "$(rf "d[\"ok\"]" "$w")" == true && $(near "$(rf "d[\"pos\"]" "$w")" "$p1" 4.0) == 0 ]]'

echo "== R12 restart the shell while behind live"
sleep 1
b_before=$(rw behindLive)
ck "R12 behindLive known before the restart ($b_before; positive control)" 'qa_value "$b_before" && [[ $(ge "$b_before" 5) == 0 ]]'
"$RUN" restart-shell >>"$LOG" 2>&1 || { bad "R12 restart-shell failed (see $LOG)"; exit 1; }
wait_log 'service loaded' 20 || bad "R12 the new shell did not start"
until_eq true 10 svc "d['playing']" || true
is "R12 the new shell recovered now-playing" "$(svc "d['playing']")" "true"
is "R12 the same player pid" "$(player_pid)" "$PID1"
until_rw behindLive "$(python3 -c "print(float('$b_before')-4)" 2>/dev/null || echo 0)" "$(python3 -c "print(float('$b_before')+4)" 2>/dev/null || echo 0)" 15 || true
ck "R12 behindLive recovered from the player ($b_before -> $(rw behindLive))" '[[ $(near "$(rw behindLive)" "$b_before" 4.0) == 0 ]]'

echo "== R13 a held key is coalesced"
ipc live >/dev/null 2>&1
until_history 26 45 || true
until_rw behindLive 0 "$SHOW_S" 6 || true
ipc open '{}' >/dev/null
until_eq true 5 svc "d['playing']" || true
for i in 1 2 3; do
  [[ "$(qa_guide_field "d['mode']" "$(ipc state)")" == list ]] && break
  ipc mode >/dev/null; sleep 0.3
done
is "R13 the guide is open in list mode" "$(qa_guide_field "d['mode']" "$(ipc state)")" "list"
seq0=$(player_seq); lock0=$(lock_seq); pid0=$(player_pid); skips0=$(svc "d['healthSkips']")
python3 "$SWEEP" 9 "$HELPER" "$WORK/sweep.json" &
SWEEP_PID=$!
sleep 0.3
"$RUN" key -d 60 -- bbbbbbbbbbbbbbbbbbbb >/dev/null 2>&1
PRESSES=20
for ((i = 0; i < 120; i++)); do kill -0 "$SWEEP_PID" 2>/dev/null || break; sleep 0.1; done
kill "$SWEEP_PID" 2>/dev/null; wait "$SWEEP_PID" 2>/dev/null
runs=$(rf 'd["runs"]' "$(cat "$WORK/sweep.json" 2>/dev/null)")
lifetimes=$(rf 'd["lifetimesMs"]' "$(cat "$WORK/sweep.json" 2>/dev/null)")
ck "R13 the helper ran for the presses at all ($runs runs; positive control)" '[[ $(ge "$runs" 1) == 0 ]]'
ck "R13 fewer helper runs than presses: coalesced ($runs < $PRESSES)" '[[ $(ge "$runs" 1) == 0 && $(ge "$((PRESSES - 1))" "$runs") == 0 ]]'
ck "R13 the position reflects the capped sum (behind $(rw behindLive) >= 20, window ~30)" '[[ $(ge "$(rw behindLive)" 20) == 0 ]]'
printf '   R13 seek helper lifetimes ms (20 ms sampling): %s\n' "$lifetimes"
ipc close >/dev/null

echo "== R14 and never trips the health restart"
sleep 2
ck "R14 positive control: seeks were issued ($runs)" '[[ $(ge "$runs" 1) == 0 ]]'
is "R14 the same player pid" "$(player_pid)" "$pid0"
is "R14 the intent counter did not move" "$(qa_delta "$seq0" "$(player_seq)")" "0"
is "R14 the lock record did not move" "$(qa_delta "$lock0" "$(lock_seq)")" "0"
is "R14 healthSkips is 0" "$(svc "d['healthSkips']")" "0"
is "R14 still playing" "$(svc "d['playing']")" "true"

echo "== R15 the per-press budget"
seek --live >/dev/null
until_history 26 45 || true
times=""
for i in 1 2 3 4 5; do
  s=$(date +%s%N)
  seek --by -4 >/dev/null
  e=$(date +%s%N)
  times="$times $(( (e - s) / 1000000 ))"
done
med=$(tr ' ' '\n' <<<"$times" | sed '/^$/d' | sort -n | sed -n 3p)
ck "R15 player seek spawn-to-reply median $med ms within 300 (runs:$times)" '[[ -n "$med" && $(ge 300 "$med") == 0 ]]'
ck "R15 and the replies were real (ok true on the last)" '[[ "$(rf "d[\"ok\"]" "$(tail -1 "$WORK/replies.jsonl")")" == true ]]'

# The floor (player-scenario.sh's rule): assert how many assertions ran so a
# check that stops executing turns the run red instead of shortening it.
# Recount after adding or removing one:
#   grep -cE '^(is|ck) ' scripts/dev-harness/rewind-scenario.sh  plus the two R6 blocks.
EXPECTED_CHECKS=78
is "the scenario ran every check it has" "$checks" "$EXPECTED_CHECKS"

printf '\n== rewind-scenario: %d passed, %d failed, %d assertions executed\n' "$pass" "$fail" "$checks"
(( fail == 0 )) || exit 1
