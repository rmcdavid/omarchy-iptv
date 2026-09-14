#!/bin/bash
# scripts/dev-harness/player-scenario.sh -- scripted verification of the
# DETACHED player (M2-02, lane PB) through the harness IPC. Started by
# `run.sh player-scenario`. Opens a real mpv window on the current Wayland
# session for ~60 s and reaps everything it starts.
#
# Scenarios (docs/ARCHITECTURE-PLAYER.md section 10, harness half):
#   P1  cold start        one player, one window, class omarchy-iptv, title = channel
#   P2  S-03 argv         no URL, no credential, no token, no header value and no
#                         channel name on mpv's command line -- TC-PLAY-08 inverted
#   P3  detachment        the player is NOT a child of the shell
#   P4  restart-shell     the shell dies and returns: same player pid, now-playing and
#                         the zap ring recovered from the player's own stash
#   P5  zap               one window reused, title follows, same pid
#   P6  stop              now-playing clears at once, nothing survives, socket unlinked
#   P7  dead stream       failure detected, channel marked, reason host-only
#   P8  two services      a second shell on the same runtime dir adopts, never spawns
#   P9  reap              the harness teardown still finds a detached grandchild
#
# Evidence rule (CLAUDE.md 10): run with --baseline <git-ref> to export that
# tree and run the same checks against it. P2, P3, P4 and P8 MUST fail there;
# the rest are regression guards that must pass on both.
#
#   ./scripts/dev-harness/player-scenario.sh
#   ./scripts/dev-harness/player-scenario.sh --baseline <pre-M2-02 ref>
#
# Output: one PASS/FAIL line per check and a summary. No URL is ever printed.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
FIX="$SCRATCH/fixtures"
LOG="$SCRATCH/player-scenario.log"
SOCK="$SCRATCH/runtime/omarchy-iptv/mpv.sock"
PLUGIN_ROOT=${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}
BASELINE=""
EXPORT_DIR=""
pass=0
fail=0

# The secrets that must never reach a command line or a log (S-03, R12).
SECRET_USER="harnessuser"
SECRET_PW="s3cr3tpw"
SECRET_TOKEN="token-ABCDEF0123"
SECRET_UA="HarnessSecretAgent/9.9"

while (($# > 0)); do
  case $1 in
    --baseline) BASELINE=$2; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

ok()  { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad() { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
# is <label> <actual> <expected>
is()  { if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }
# yes <label> <cmd...>: the command's exit status is the verdict
yes() { local label=$1; shift; if "$@"; then ok "$label"; else bad "$label"; fi; }

ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
ipc2() { OMARCHY_IPTV_HARNESS_INSTANCE=2 "$RUN" ipc "$@" 2>/dev/null; }
# Field of the service half of state(), by python expression over `d`.
field() { python3 -c '
import json, sys
try: d = json.loads(sys.argv[2])["service"]
except Exception: print(""); raise SystemExit(0)
try: v = eval(sys.argv[1])
except Exception: v = None
print(json.dumps(v) if isinstance(v, bool) else ("" if v is None else v))' "$1" "$2" 2>/dev/null; }
svc()  { field "$1" "$(ipc state)"; }
svc2() { field "$1" "$(ipc2 state)"; }
np()   { svc "d['nowPlaying']['$1'] if d.get('nowPlaying') else None"; }
np2()  { svc2 "d['nowPlaying']['$1'] if d.get('nowPlaying') else None"; }

# Every mpv bound to THIS scratch socket. It can never match the live
# session's player: the pattern carries the scratch path.
player_pids()  { pgrep -f "input-ipc-server=$SOCK" 2>/dev/null; }
player_count() { player_pids | wc -l | tr -d ' '; }
player_pid()   { player_pids | head -1; }
cmdline_of()   { tr '\0' ' ' <"/proc/$1/cmdline" 2>/dev/null; }
ppid_of()      { ps -o ppid= -p "$1" 2>/dev/null | tr -d ' '; }
window_of() {
  hyprctl clients -j 2>/dev/null | python3 -c '
import json, sys
pid = int(sys.argv[1])
for c in json.load(sys.stdin):
    if c.get("pid") == pid:
        print("%s|%s" % (c.get("class", ""), c.get("title", "")))
        break
' "$1" 2>/dev/null
}
windows_named() {
  hyprctl clients -j 2>/dev/null | python3 -c '
import json, sys
print(len([c for c in json.load(sys.stdin) if c.get("class") == "omarchy-iptv"]))' 2>/dev/null
}

# until_eq <want> <secs> <cmd...>
until_eq() {
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ "$("$@")" == "$want" ]] && return 0
    sleep 0.1
  done
  return 1
}
until_set() {   # until_set <secs> <cmd...>: wait for a non-empty answer
  local secs=$1; shift
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ -n "$("$@")" ]] && return 0
    sleep 0.1
  done
  return 1
}
wait_log() {
  local re=$1 secs=$2 i
  for ((i = 0; i < secs * 10; i++)); do
    grep -qE "$re" "$SCRATCH"/harness.log 2>/dev/null && return 0
    sleep 0.1
  done
  return 1
}

cleanup() {
  OMARCHY_IPTV_HARNESS_INSTANCE=2 "$RUN" shell-stop >/dev/null 2>&1
  "$RUN" reap >/dev/null 2>&1
  [[ -n $EXPORT_DIR && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ---- which checkout is under test
if [[ -n $BASELINE ]]; then
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-baseline-XXXXXX")
  git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR" || { echo "could not export $BASELINE" >&2; exit 2; }
  PLUGIN_ROOT="$EXPORT_DIR"
  echo "== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported"
fi
export OMARCHY_IPTV_PLUGIN_ROOT="$PLUGIN_ROOT"
echo "== plugin tree $PLUGIN_ROOT   scratch $SCRATCH"

# ---- fixtures: two playable channels (so a zap keeps the window alive) and
# one dead channel whose URL carries credentials and a token, with headers.
mkdir -p "$FIX"
if [[ ! -f $FIX/test.ts ]]; then
  echo "== generating the test stream (ffmpeg, 120 s)"
  ffmpeg -loglevel error -y -f lavfi -i "testsrc=size=320x240:rate=15" -f lavfi -i "sine=frequency=440:sample_rate=22050" \
    -t 120 -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 32k -f mpegts "$FIX/test.ts" || { echo "ffmpeg failed" >&2; exit 1; }
fi
cp -f "$FIX/test.ts" "$FIX/test2.ts"
cat >"$FIX/player.m3u" <<EOF
#EXTM3U
#EXTINF:-1 tvg-id="live1" group-title="Harness",Harness Live One
http://127.0.0.1:8765/test.ts
#EXTINF:-1 tvg-id="live2" group-title="Harness",Harness Live Two
http://127.0.0.1:8765/test2.ts
#EXTINF:-1 tvg-id="dead1" group-title="Harness",Harness Dead
#EXTVLCOPT:http-user-agent=$SECRET_UA
#EXTVLCOPT:http-referrer=http://127.0.0.1:9/$SECRET_TOKEN/
http://$SECRET_USER:$SECRET_PW@127.0.0.1:9/$SECRET_TOKEN/dead.m3u8
EOF

"$RUN" reap >/dev/null 2>&1
"$RUN" clean >/dev/null
: >"$LOG"
: >"$SCRATCH/harness.log"

echo "== start the harness (detached, fixture server, player kept across restarts)"
"$RUN" --detach --serve --timeout 0 --playlist "$FIX/player.m3u" >>"$LOG" 2>&1
wait_log 'service loaded' 20 || { bad "the harness did not start (see $LOG)"; exit 1; }
until_eq 3 20 svc "d['channels']" || bad "the fixture playlist did not load"

echo "== P1 cold start"
ipc play "t:live1" >/dev/null
until_eq 1 15 player_count || true
PID1=$(player_pid)
is "P1 exactly one player process" "$(player_count)" "1"
until_eq true 10 svc "d['playing']" || true
is "P1 the service reports playing" "$(svc "d['playing']")" "true"
is "P1 now-playing is the channel asked for" "$(np id)" "t:live1"
is "P1 window class and title" "$(window_of "$PID1")" "omarchy-iptv|Harness Live One"
is "P1 exactly one omarchy-iptv window" "$(windows_named)" "1"

echo "== P2 S-03: nothing channel-specific on the player command line"
cmd=$(cmdline_of "$PID1")
yes "P2 no URL on the command line"        [[ "$cmd" != *"://"* ]]
yes "P2 no credential on the command line" [[ "$cmd" != *"$SECRET_PW"* && "$cmd" != *"$SECRET_USER"* ]]
yes "P2 no token on the command line"      [[ "$cmd" != *"$SECRET_TOKEN"* ]]
yes "P2 no header value on the command line" [[ "$cmd" != *"$SECRET_UA"* && "$cmd" != *"--user-agent="* && "$cmd" != *"--referrer="* && "$cmd" != *"--http-header-fields"* ]]
yes "P2 no channel name on the command line" [[ "$cmd" != *"Harness Live One"* ]]
yes "P2 the neutral launch options are there" [[ "$cmd" == *"--idle=once"* && "$cmd" == *"--wayland-app-id=omarchy-iptv"* && "$cmd" == *"--ytdl=no"* ]]
is  "P2 no yt-dlp process" "$(pgrep -c yt-dlp 2>/dev/null || echo 0)" "0"

echo "== P3 the player is not a child of the shell"
QS_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null)
yes "P3 the shell is up" kill -0 "${QS_PID:-0}"
yes "P3 the player's parent is not the shell" [[ "$(ppid_of "$PID1")" != "$QS_PID" ]]
yes "P3 the player is not a direct child of the shell" ! pgrep -P "${QS_PID:-0}" -f "input-ipc-server=$SOCK" >/dev/null 2>&1

echo "== P4 restart the shell while playing (the headline case)"
"$RUN" restart-shell >>"$LOG" 2>&1
is "P4 the player survived the shell going away" "$(player_count)" "1"
is "P4 the same player pid" "$(player_pid)" "$PID1"
wait_log 'service loaded' 20 || bad "P4 the new shell did not start"
until_eq true 4 svc "d['playing']" || true      # the 2 s acceptance bar, doubled
is "P4 the new shell recovered now-playing" "$(svc "d['playing']")" "true"
is "P4 it recovered the right channel" "$(np id)" "t:live1"
yes "P4 it recovered the zap ring (launchedFrom, which no mpv property knows)" [[ -n "$(np launchedFrom)" ]]
is "P4 still exactly one player" "$(player_count)" "1"
is "P4 still the same pid" "$(player_pid)" "$PID1"
is "P4 still exactly one window" "$(windows_named)" "1"
until_eq true 6 svc "d['socketAttached']" || true
is "P4 the observer reattached to the surviving socket" "$(svc "d['socketAttached']")" "true"

echo "== P5 zap reuses the one window"
ipc zap 1 >/dev/null
until_eq "t:live2" 10 np id || true
is "P5 now-playing moved to the next channel" "$(np id)" "t:live2"
is "P5 no second player process" "$(player_count)" "1"
is "P5 the same pid" "$(player_pid)" "$PID1"
until_eq "omarchy-iptv|Harness Live Two" 10 window_of "$PID1" || true
is "P5 the window title followed the zap" "$(window_of "$PID1")" "omarchy-iptv|Harness Live Two"
cmd=$(cmdline_of "$PID1")
yes "P5 still nothing channel-specific on the command line" [[ "$cmd" != *"://"* && "$cmd" != *"Harness Live Two"* ]]

echo "== P8 a second service on the same runtime dir adopts the player"
OMARCHY_IPTV_HARNESS_INSTANCE=2 "$RUN" --detach --keep --timeout 0 --instance 2 --playlist "$FIX/player.m3u" >>"$LOG" 2>&1
sleep 4
is "P8 still exactly one player with two shells up" "$(player_count)" "1"
is "P8 still exactly one window" "$(windows_named)" "1"
is "P8 the second shell adopted the same channel" "$(np2 id)" "t:live2"
OMARCHY_IPTV_HARNESS_INSTANCE=2 "$RUN" shell-stop >>"$LOG" 2>&1
sleep 2
is "P8 the second shell leaving did not stop the player" "$(player_count)" "1"

echo "== P6 stop is immediate in the UI and leaves nothing behind"
ipc stop >/dev/null
is "P6 now-playing cleared at once" "$(svc "d['playing']")" "false"
until_eq 0 8 player_count || true
is "P6 no player process survives the ladder" "$(player_count)" "0"
until_eq 0 4 windows_named || true
is "P6 no omarchy-iptv window survives" "$(windows_named)" "0"
yes "P6 the socket file was unlinked" [[ ! -e "$SOCK" ]]

echo "== P7 a dead stream is detected, named and marked"
ipc play "t:dead1" >/dev/null
until_set 20 svc "d['failedAt'].get('t:dead1')" || true
yes "P7 the channel is marked failed for the session" [[ -n "$(svc "d['failedAt'].get('t:dead1')")" ]]
until_eq false 10 svc "d['playing']" || true
is "P7 playback did not stay up" "$(svc "d['playing']")" "false"
err=$(svc "d['lastError']")
yes "P7 a reason was recorded" [[ -n "$err" ]]
yes "P7 the reason carries no credential and no token" [[ "$err" != *"$SECRET_PW"* && "$err" != *"$SECRET_TOKEN"* && "$err" != *"$SECRET_USER"* ]]
until_eq 0 8 player_count || true
is "P7 no player left behind by the failure" "$(player_count)" "0"

echo "== P9 the harness reaps a detached grandchild"
ipc play "t:live1" >/dev/null
until_eq 1 15 player_count || bad "P9 no player to reap"
"$RUN" reap >>"$LOG" 2>&1
until_eq 0 8 player_count || true
is "P9 reap killed the detached player" "$(player_count)" "0"
yes "P9 reap stopped the shell" ! pgrep -f "quickshell -p $SCRATCH/root" >/dev/null

printf '\n== summary: %d passed, %d failed\n' "$pass" "$fail"
(( fail == 0 )) || exit 1
