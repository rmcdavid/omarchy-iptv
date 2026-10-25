#!/bin/bash
# scripts/dev-harness/spikes/first-open/run.sh -- the D-PERF-2 attribution
# spike (2026-10-24): WHERE the first guide open's ~440 ms goes. A measurement
# rig, not a scenario: it grades nothing, it prints figures with the load
# beside them, and the transcript is the evidence (rule 7).
#
#   scripts/dev-harness/private-bus.sh <dir> 3000 \
#       scripts/dev-harness/spikes/first-open/run.sh [--arm probe|harness|all] [--reps N]
#
# It REFUSES the user's own session bus (CLAUDE.md, parallel 6b), holds no
# display but the one the nested headless cage it starts creates, sends no
# key, and ends every process by the pid it recorded (printed under
# "== pids"): the cage, its child, each probe quickshell, each harness shell
# (through run.sh's own pid file). Nothing is matched by pattern.
#
# Two arms:
#   probe    floor.qml beside this file, a bare Quickshell config: a window's
#            first swapped frame, cold and warm, rect / text / the guide's glyph
#            set, re-created, hidden pre-warm (content at opacity 0 or 0.01),
#            a PanelWindow (never maps in the cage), under QSG_INFO=1 and the
#            scene-graph timing categories; first, second and third process of
#            one shader-cache directory, and one with the cache wiped.
#   harness  the dev-harness fake shell with the REAL Service.qml and
#            Guide.qml in the floating window (scripts/dev-harness/run.sh,
#            the open instrument's shell arm), the cold openAsync and one warm,
#            RSS from /proc before and after, the scene-graph timing lines of
#            the shell's log for that open; at 10,000 channels, at 40, and
#            over an EMPTY playlist (a header-only M3U: no row is realised,
#            the instrument never settles, its first frame is what is read);
#            plus one shell started with --keep so the previous shell's Qt
#            shader cache is in place.
set -uo pipefail
SKIP=77
CAGE_BIN=${OPEN_CAGE_BIN:-cage}
ARM=all; REPS=3
while (( $# )); do
  case $1 in
    --arm) ARM=${2:-}; shift ;;
    --reps) REPS=${2:-3}; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
case $ARM in probe|harness|all) ;; *) echo "--arm takes probe, harness or all" >&2; exit 2 ;; esac
for tool in node python3 "$CAGE_BIN" quickshell qs; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP first-open: $tool is not on PATH" >&2; exit $SKIP; }
done
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
if [[ -z ${DBUS_SESSION_BUS_ADDRESS:-} || $DBUS_SESSION_BUS_ADDRESS == "unix:path=$REAL_RUNTIME/bus" ]]; then
  echo "REFUSING first-open: not on a private D-Bus (run it under scripts/dev-harness/private-bus.sh, CLAUDE.md parallel 6b)" >&2
  exit 2
fi
HERE=${BASH_SOURCE[0]%/*}
[[ $HERE == "${BASH_SOURCE[0]}" ]] && HERE=.
HERE=$(cd "$HERE" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
RUN="$ROOT/scripts/dev-harness/run.sh"
LIVE_DISPLAY=${WAYLAND_DISPLAY:-wayland-1}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-first-open}
export OMARCHY_IPTV_HARNESS_DIR=$SCRATCH
qa_harness_home "$SCRATCH" || exit 2
mkdir -p "$SCRATCH/runtime" "$SCRATCH/bin" "$SCRATCH/fixtures" || exit 2
qa_transcript_start first-open || exit 2
echo "== tree $ROOT ($(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git))   arm $ARM   reps $REPS"
echo "== quickshell $(quickshell --version 2>/dev/null | head -1); $(pacman -Q qt6-declarative qt6-wayland mesa cage 2>/dev/null | tr '\n' ' ')"
echo "== load at start $(cut -d' ' -f1-3 /proc/loadavg)   cores $(nproc)   caller's display $LIVE_DISPLAY (never driven)"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-first-open.XXXXXX") || exit 2
chmod 0700 "$WORK"
PIDS="$WORK/pids"; : >"$PIDS"
CAGE_PID=""; CAGE_CHILD=""; NESTED=""; PROBE_PID=""; SHELL_PID=""; SHELL_STARTED=0
record_pid() { echo "$1 $2" >>"$PIDS"; echo "== pid $1 $2"; }
h() { env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" "$@"; }
cleanup() {
  [[ -n $PROBE_PID ]] && qa_stop_pid "$PROBE_PID" 3 "probe quickshell" 2>/dev/null
  (( SHELL_STARTED )) && h reap >/dev/null 2>&1
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  if [[ -n $CAGE_PID ]] && kill -0 "$CAGE_PID" 2>/dev/null; then kill -TERM "$CAGE_PID" 2>/dev/null; wait "$CAGE_PID" 2>/dev/null; fi
  echo "== pids this run started and ended, by record:"; sed 's/^/   /' "$PIDS" 2>/dev/null
  [[ -n ${WORK:-} && -d $WORK ]] && rm -rf "$WORK"
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

RULES="qt.scenegraph.time.*=true;qt.scenegraph.general=true;qt.opengl.diskcache=true;qt.rhi.general=true"
PATTERN="%{time process} %{if-category}%{category}: %{endif}%{message}"
load() { cut -d' ' -f1 /proc/loadavg; }
rss_kb() { awk '/^VmRSS:/ { print $2 }' "/proc/$1/status" 2>/dev/null || echo -1; }
jf() { qa_json_field "d$1" "$2"; }

# ------------------------------------------------------------------- cage
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
  if [[ -z $NESTED || -z $CAGE_CHILD ]]; then echo "SKIP first-open: cage brought up no display within 10 s" >&2; exit $SKIP; fi
  if [[ $NESTED == "$LIVE_DISPLAY" || $NESTED == wayland-1 ]]; then echo "REFUSING: cage's child reports the live display '$NESTED'" >&2; exit 2; fi
  record_pid cage "$CAGE_PID"; record_pid cage-child "$CAGE_CHILD"
  echo "== cage display $NESTED (WLR_RENDERER=pixman, headless)"
}
cage_stop() {
  local i
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  for ((i = 0; i < 50; i++)); do kill -0 "$CAGE_PID" 2>/dev/null || break; sleep 0.1; done
  kill -0 "$CAGE_PID" 2>/dev/null && kill -KILL "$CAGE_PID" 2>/dev/null
  wait "$CAGE_PID" 2>/dev/null; CAGE_PID=""; CAGE_CHILD=""
}

# -------------------------------------------------------------- probe arm
# The probe gets what harness_env gives the shell: the scratch runtime
# directory and the ABSOLUTE socket path of the nested display; and a shader
# cache directory of its own under the scratch so this script decides when it
# is fresh.
PROBE_CACHE="$SCRATCH/probe-cache"
pipc() { timeout 10 env -u HYPRLAND_INSTANCE_SIGNATURE -u DISPLAY WAYLAND_DISPLAY="$REAL_RUNTIME/$NESTED" XDG_RUNTIME_DIR="$SCRATCH/runtime" qs ipc -p "$HERE/floor.qml" call probe "$@" 2>/dev/null; }
probe_start() {   # probe_start <label>
  local log="$WORK/probe-$1.log" i
  # `env` inline, not through a function: a backgrounded function is a
  # subshell and `$!` would be ITS pid, two off the quickshell it started
  # (seen on the first smoke run: `qs ipc` answered 767529 for a recorded
  # 767527). `env` execs quickshell, so this pid is the window's process.
  env -u HYPRLAND_INSTANCE_SIGNATURE -u DISPLAY WAYLAND_DISPLAY="$REAL_RUNTIME/$NESTED" XDG_RUNTIME_DIR="$SCRATCH/runtime" \
    XDG_CACHE_HOME="$PROBE_CACHE" NO_COLOR=1 QSG_INFO=1 QT_LOGGING_RULES="$RULES" QT_MESSAGE_PATTERN="$PATTERN" \
    quickshell -p "$HERE/floor.qml" >"$log" 2>&1 &
  PROBE_PID=$!
  record_pid "probe-$1" "$PROBE_PID"
  for ((i = 0; i < 100; i++)); do [[ $(pipc pid) == "$PROBE_PID" ]] && return 0; sleep 0.1; done
  echo "   probe $1 (pid $PROBE_PID) answered no IPC within 10 s; qs ipc says: $(timeout 10 env -u HYPRLAND_INSTANCE_SIGNATURE -u DISPLAY WAYLAND_DISPLAY="$REAL_RUNTIME/$NESTED" XDG_RUNTIME_DIR="$SCRATCH/runtime" qs ipc -p "$HERE/floor.qml" call probe pid 2>&1 | head -c 300); log: $(tr '\n' ' ' <"$log" | head -c 1200)"
  return 1
}
probe_stop() {
  pipc quit >/dev/null
  qa_stop_pid "$PROBE_PID" 3 "probe quickshell" 2>/dev/null
  PROBE_PID=""
}
# probe_process <label> <fresh|keep> <step>...   step: create:K show:K hide:K
# destroy:K opacity:K:V rss sleep:MS. A show is waited for (bounded 4 s; 3 s
# for panel, which never maps here) and printed with its figures.
probe_process() {
  local label=$1 cache=$2 s kind val res i t0 bound log
  shift 2
  [[ $cache == fresh ]] && rm -rf "$PROBE_CACHE"
  mkdir -p "$PROBE_CACHE"
  log="$WORK/probe-$label.log"
  echo "-- probe process $label (shader cache $cache: $(find "$PROBE_CACHE" -type f 2>/dev/null | wc -l) files before)   load $(load)"
  t0=$(date +%s%N)
  probe_start "$label" || { probe_stop; return 1; }
  echo "   up: IPC answered $(( ($(date +%s%N) - t0) / 1000000 )) ms after spawn; engine uptime $(pipc uptime) ms; rss $(rss_kb "$PROBE_PID") kB"
  for s in "$@"; do
    kind=${s#*:}; kind=${kind%%:*}
    case $s in
      create:*) echo "   create $kind: $(pipc create "$kind")" ;;
      destroy:*) pipc destroy "$kind" >/dev/null; echo "   destroy $kind" ;;
      hide:*) pipc dismiss "$kind" >/dev/null; sleep 0.4 ;;
      opacity:*) val=${s##*:}; echo "   opacity $kind $val: $(pipc opacity "$kind" "$val")" ;;
      rss) echo "   rss $(rss_kb "$PROBE_PID") kB" ;;
      sleep:*) sleep "$(python3 -c 'import sys; print(int(sys.argv[1]) / 1000)' "$kind")" ;;
      show:*)
        res=$(pipc present "$kind")
        [[ $(jf "['ok']" "$res") == true ]] || { echo "   show $kind REFUSED: $res"; continue; }
        bound=40; [[ $kind == panel ]] && bound=30
        for ((i = 0; i < bound; i++)); do
          res=$(pipc result)
          [[ $(jf "['state']" "$res") == done ]] && break
          sleep 0.1
        done
        echo "   SHOW $label $kind tFirst=$(jf "['tFirst']" "$res") ms tBacker=$(jf "['tBacker']" "$res") ms frames=$(jf "['frames']" "$res") set=$(jf "['setMs']" "$res") ms state=$(jf "['state']" "$res") rss=$(rss_kb "$PROBE_PID") kB load=$(load)"
        ;;
      *) echo "   unknown step $s" ;;
    esac
  done
  probe_stop
  echo "   shader cache after: $(find "$PROBE_CACHE" -type f 2>/dev/null | wc -l) files $(du -sk "$PROBE_CACHE" 2>/dev/null | cut -f1) kB"
  echo "   QSG lines ($label): the renderer, the caches, every frame over 30 ms with its sync/render/swap split, every glyph and texture upload"
  qsg_lines "$log" | head -60 | sed 's/^/      /'
}
# The lines worth a reader's time, in order: which renderer and context,
# whether a pipeline cache was seeded, each window's slow frames (the
# first one per window is the cost in question) with the renderloop's own
# split, the GUI thread's wait on it, and the glyph / texture / shader work.
qsg_lines() {
  grep -a -E 'Creating QRhi|Created OpenGL|RENDERER:|pipeline cache|Seeded|diskcache.*(location|supported)|frame rendered in ([3-9][0-9]|[0-9]{3,})ms|blockedForSync=([3-9][0-9]|[0-9]{3,}) ms|time\.glyph|time\.texture|time\.compilation|atlas|Failed|layershell' "$1" \
    | sed -E 's/^ *DEBUG *//; s/\[window (0x[0-9a-f]+)\]/[\1]/; s/\[render thread 0x[0-9a-f]+\]/[render]/'
}

probe_arm() {
  local r
  echo "== probe arm: floor.qml, $REPS repetitions"
  # P1: cache FRESH, the floor from cold. P2, P3: the same steps, the cache
  # left as P1 wrote it (lever b: a second process start).
  for ((r = 1; r <= REPS; r++)); do
    probe_process "P$r" "$([[ $r == 1 ]] && echo fresh || echo keep)" \
      rss create:rect show:rect rss hide:rect show:rect \
      create:text show:text rss hide:text show:text \
      create:glyphs show:glyphs rss hide:glyphs show:glyphs \
      destroy:text sleep:400 create:text show:text \
      create:panel show:panel
  done
  # T: the TEXT window as the first window of a fresh process (cold font and
  # glyph work on top of the cold context), fresh cache then kept.
  for ((r = 1; r <= REPS; r++)); do
    probe_process "T$r" "$([[ $r == 1 ]] && echo fresh || echo keep)" rss create:text show:text rss hide:text show:text create:glyphs show:glyphs rss
  done
  # G: the GLYPH window first.
  probe_process G1 fresh rss create:glyphs show:glyphs rss hide:glyphs show:glyphs
  probe_process G2 keep rss create:glyphs show:glyphs rss hide:glyphs show:glyphs
  # W0: lever (a), the hidden pre-warm at opacity 0 -- a mapped window that
  # draws nothing -- then the first visible show of the SAME window, then a
  # second window. W1: the same at opacity 0.01 (everything drawn, invisible
  # to a person).
  for ((r = 1; r <= REPS; r++)); do
    probe_process "W0-$r" "$([[ $r == 1 ]] && echo fresh || echo keep)" rss create:glyphs opacity:glyphs:0 show:glyphs rss hide:glyphs opacity:glyphs:1 show:glyphs rss create:text show:text
  done
  for ((r = 1; r <= REPS; r++)); do
    probe_process "W1-$r" "$([[ $r == 1 ]] && echo fresh || echo keep)" rss create:glyphs opacity:glyphs:0.01 show:glyphs rss hide:glyphs opacity:glyphs:1 show:glyphs rss create:text show:text
  done
  echo "== probe arm done   load $(load)"
}

# ------------------------------------------------------------ harness arm
FIX10K="$SCRATCH/fixtures/gen-10k.m3u"; FIX40="$SCRATCH/fixtures/gen-40.m3u"; FIX0="$SCRATCH/fixtures/empty.m3u"
HLOG="$SCRATCH/harness.log"
ipc() { h ipc "$@" 2>/dev/null; }
svc() { qa_field "d$1" "$(ipc state)"; }
start_shell() {   # start_shell <fixture> <channels> <keep 0|1>
  local i keep=()
  (( $3 )) && keep=(--keep)
  # Prefix assignments, not `env ...`: `h` is a function and `env` cannot
  # exec one (the first full run lost every harness shell to "env: 'h': No
  # such file or directory" in start.log, and read it as a shell that did
  # not settle). The variables reach run.sh and the quickshell it setsids.
  NO_COLOR=1 QSG_INFO=1 QT_LOGGING_RULES="$RULES" QT_MESSAGE_PATTERN="$PATTERN" \
    h --detach --timeout 0 --playlist "$1" --window floating "${keep[@]}" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  [[ -n $SHELL_PID ]] || { echo "   run.sh --detach recorded no shell pid: $(tr '\n' ' ' <"$WORK/start.log" | head -c 300)"; return 1; }
  record_pid harness-shell "$SHELL_PID"
  for ((i = 0; i < 600; i++)); do
    [[ $(svc "['channels']") == "$2" ]] && { (( $2 == 0 )) && sleep 2; return 0; }
    sleep 0.1
  done
  echo "   the shell (pid $SHELL_PID) did not hold $2 channels within 60 s: $(svc "['channels']")"
  return 1
}
stop_shell() { h shell-stop >/dev/null 2>&1; local i; for ((i = 0; i < 50; i++)); do kill -0 "$SHELL_PID" 2>/dev/null || break; sleep 0.1; done; SHELL_STARTED=0; }
async_open() {   # async_open <view> -> result json; bounded 8 s
  local i res
  ipc close >/dev/null; sleep 0.4
  ipc openAsync "$1" >"$WORK/started.json"
  for ((i = 0; i < 80; i++)); do
    res=$(ipc openAsyncResult)
    [[ $(jf "['state']" "$res") == done ]] && { printf '%s\n' "$res"; return 0; }
    sleep 0.1
  done
  printf '%s\n' "$res"; return 1
}
trace() { python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(" ".join("%s:%s/%s:%s" % (f["at"], f["drawn"], f["built"], f["reason"] or "ok") for f in d.get("trace", [])[:12]))' "$1" 2>/dev/null; }
report_open() {   # report_open <label> <kind> <json> <rss-before> <rss-after>
  echo "   OPEN $1 $2 summon=$(jf "['summonMs']" "$3") ms firstFrame=$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); t=d.get("trace", []); print(t[0]["at"] if t else -1)' "$3" 2>/dev/null) ms realised=$(jf "['realisedMs']" "$3") ms drawn=$(jf "['count']" "$3") built=$(jf "['built']" "$3") endedBy=$(jf "['endedBy']" "$3") view=$(jf "['view']" "$3") rss=$4->$5 kB load=$(load)"
  echo "      trace (ms:drawn/built:reason): $(trace "$3")"
}
harness_shell() {   # harness_shell <label> <fixture> <channels> <keep>
  local label=$1 fix=$2 n=$3 keep=$4 off res r0 r1 r2 r3
  off=0; [[ -f $HLOG ]] && off=$(wc -l <"$HLOG")
  echo "-- harness shell $label: $n channels, floating window, shader cache $([[ $keep == 1 ]] && echo kept || echo fresh)   load $(load)"
  start_shell "$fix" "$n" "$keep" || { echo "   shell $label did not settle: $(ipc state | head -c 300)"; stop_shell; return 1; }
  echo "   shell pid $SHELL_PID settled; playlist status $(svc "['status']") configured $(svc "['configured']")"
  sleep 1
  r0=$(rss_kb "$SHELL_PID")
  res=$(async_open list); r1=$(rss_kb "$SHELL_PID")
  report_open "$label" cold "$res" "$r0" "$r1"
  ipc close >/dev/null; sleep 0.6; r2=$(rss_kb "$SHELL_PID")
  res=$(async_open list); r3=$(rss_kb "$SHELL_PID")
  report_open "$label" warm "$res" "$r2" "$r3"
  ipc close >/dev/null
  stop_shell
  echo "   QSG lines ($label): the renderer, the caches, every frame over 30 ms with its split, glyph and texture uploads (the bar's PanelWindow never maps here, so the windows are the guide's)"
  tail -n +"$((off + 1))" "$HLOG" >"$WORK/shell-$label.log"
  qsg_lines "$WORK/shell-$label.log" | head -70 | sed 's/^/      /'
  echo "   frames in the shell's log ($label): $(grep -a -c 'frame rendered in' "$WORK/shell-$label.log")"
  echo "   shell cache dir after: $(find "$SCRATCH/cache" -type f 2>/dev/null | grep -c -E 'qtshadercache|qtpipelinecache|mesa_shader') shader-cache files"
}
harness_arm() {
  local r
  echo "== harness arm: scripts/dev-harness/run.sh, plugin tree $ROOT, $REPS shells per case"
  python3 "$ROOT/scripts/gen-playlist.py" --channels 10000 --groups 400 --seed 1 --out "$FIX10K" >/dev/null || { echo "gen-playlist failed" >&2; return 1; }
  python3 "$ROOT/scripts/gen-playlist.py" --channels 40 --groups 4 --seed 1 --out "$FIX40" >/dev/null || { echo "gen-playlist failed" >&2; return 1; }
  printf '#EXTM3U\n' >"$FIX0"
  export OMARCHY_IPTV_PLUGIN_ROOT=$ROOT
  ln -sfn "$ROOT/scripts/dev-harness/stub-hyprctl.py" "$SCRATCH/bin/hyprctl"
  h reap >/dev/null 2>&1
  for ((r = 1; r <= REPS; r++)); do harness_shell "H10K-$r" "$FIX10K" 10000 0; done
  # lever (b) on the real guide: the shell after a 10k shell, its cache KEPT
  # (--keep keeps the scratch cache and state, so it must follow a shell over
  # the SAME playlist: after the empty one it inherits a playlist error and
  # holds 0 channels, which is how the first full run lost these two).
  for ((r = 1; r <= REPS; r++)); do harness_shell "H10K-keep-$r" "$FIX10K" 10000 1; done
  for ((r = 1; r <= REPS; r++)); do harness_shell "H40-$r" "$FIX40" 40 0; done
  # Last: the instrument never settles over an empty view, so each open is
  # 6 s of continuous frames, and the load average that follows is its own.
  for ((r = 1; r <= REPS; r++)); do harness_shell "H0-$r" "$FIX0" 0 0; done
  echo "== harness arm done   load $(load)"
}

cage_start 2900
[[ $ARM == probe || $ARM == all ]] && probe_arm
[[ $ARM == harness || $ARM == all ]] && harness_arm
cage_stop
echo "== done   load $(load)   user's quickshell untouched: $(pgrep -x quickshell | tr '\n' ' ')"
