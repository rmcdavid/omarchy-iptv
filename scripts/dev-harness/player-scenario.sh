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
#   P10 superseded stop   a lock sequence pushed ahead by another launcher does not
#                         turn every later stop into a silent no-op
#   P11 health respawn    D-PLY-1 trigger A: after the two-strike verdict's
#                         `player restart --from term` the shell reattaches to the
#                         new player, ONE relaunch, and never goes idle
#   P12 socket respawn    D-PLY-1 trigger B: the same after a socket unlink that
#                         makes `player start` ladder the old player down
#   P13 startup race      D-PLY-4: a play issued from the earliest instant the
#                         successor's IPC accepts one keeps its session record
#   P14 marked once       D-PLY-3: PO-3's record is retired when it is consumed,
#                         so the next start does not raise the same mark again
#   P9  reap              the harness teardown still finds a detached grandchild
#
# Evidence rule (CLAUDE.md 10): run with --baseline <git-ref> to export that
# tree and run the same checks against it. Against the last pre-M2-02 commit
# P2, P3, P4, P5, P6 and P8 MUST fail; P10 is evidence against the first
# detached-player commit, which is the code that shipped that bug; P11, P12,
# P13 and P14 MUST fail against 396a69a, the tree the M2-02 QA pass filed
# D-PLY-1, D-PLY-3 and D-PLY-4 against. The rest are regression guards that
# must pass on both.
#
#   ./scripts/dev-harness/player-scenario.sh
#   ./scripts/dev-harness/player-scenario.sh --baseline <pre-M2-02 ref>
#   ./scripts/dev-harness/player-scenario.sh --race-trials 30   (D-PLY-4's measurement)
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
RACE_TRIALS=5
pass=0
fail=0
# `pass`/`fail` count OUTCOMES; `checks` counts ASSERTIONS. A `|| bad` guard
# moves fail without being an assertion, so only `checks` is comparable
# between a green run and a red one - which is what the floor at the end
# needs. See EXPECTED_CHECKS below.
checks=0

# The predicates this file asserts on, so that they can be tested without a
# display: scripts/qa-lib-test.sh drives every one of them both ways.
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

# The secrets that must never reach a command line or a log (S-03, R12).
SECRET_USER="harnessuser"
SECRET_PW="s3cr3tpw"
SECRET_TOKEN="token-ABCDEF0123"
SECRET_UA="HarnessSecretAgent/9.9"

while (($# > 0)); do
  case $1 in
    --baseline) BASELINE=$2; shift ;;
    --race-trials) RACE_TRIALS=$2; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

ok()  { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad() { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
# is <label> <actual> <expected>
is()  { checks=$((checks + 1)); if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }
# ck <label> '<bash test>': `[[ ]]` is a keyword, so the test is evaluated,
# not executed. Single-quote the expression and let it read the variables.
ck()  { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }

ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
ipc2() { OMARCHY_IPTV_HARNESS_INSTANCE=2 "$RUN" ipc "$@" 2>/dev/null; }
# Field of the service half of state(), by python expression over `d`.
# qa_field speaks sentinels: NOSTATE when the IPC did not answer, NOFIELD when
# it answered and the field is absent. The old helper printed "" for both, and
# for a healthy "nothing here" as well - so three P14 assertions were asserting
# a value that every failure mode of the tooling also produced.
svc()  { qa_field "$1" "$(ipc state)"; }
svc2() { qa_field "$1" "$(ipc2 state)"; }
np()   { svc "d['nowPlaying']['$1'] if d.get('nowPlaying') else None"; }
np2()  { svc2 "d['nowPlaying']['$1'] if d.get('nowPlaying') else None"; }

# Every mpv bound to THIS scratch socket. It can never match the live
# session's player: the pattern carries the scratch path.
player_pids()  { pgrep -f "input-ipc-server=$SOCK" 2>/dev/null; }
player_count() { player_pids | wc -l | tr -d ' '; }
player_pid()   { player_pids | head -1; }
# qa_cmdline refuses an empty pid. `tr '\0' ' ' </proc/$1/cmdline` with an
# empty $1 reads /proc//cmdline, which the kernel resolves to /proc/cmdline:
# the six S-03 "no secret on mpv's argv" sweeps then compared the secrets
# against the KERNEL command line and passed.
cmdline_of()   { qa_cmdline "$1"; }
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
until_set() {   # until_set <secs> <cmd...>: wait for a REAL answer
  # qa_value, not [[ -n ]]: a sentinel is non-empty and must not end the wait.
  local secs=$1; shift
  local i
  for ((i = 0; i < secs * 10; i++)); do
    qa_value "$("$@")" && return 0
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
# D-PLY-9. The shipped form was
#   log_count() { grep -acE "$1" "$SCRATCH"/harness.log 2>/dev/null || echo 0; }
# and `grep -c` prints its own 0 AND exits 1 on a no-match, so both sides of
# the || ran and the value was $'0\n0'. The $(( )) at P11 then died as an
# EXPANSION error, which means bash never ran the `is` whose word it was:
# no pass, no fail, exit 0, on every run of both trees.
log_count() { qa_count "$1" "$SCRATCH/harness.log"; }
# until_changed <secs> <old> <cmd...>: wait for a different, non-empty answer
until_changed() {
  local secs=$1 old=$2; shift 2
  local i now
  for ((i = 0; i < secs * 10; i++)); do
    now=$("$@")
    [[ -n "$now" && "$now" != "$old" ]] && return 0
    sleep 0.1
  done
  return 1
}
STATE_JSON="$SCRATCH/state/omarchy-iptv/state.json"
# The session record on DISK, which is what a later shell start reads.
# NOFILE (no state file, or unparseable) and NOSESSION (parsed, no record) are
# different answers and neither of them is "". P14 asserted "" three times.
session_id() { qa_session_id "$STATE_JSON"; }
# until_session <want> <secs>: saveState() is gated on dirsReady, so the write
# can legitimately land a moment after the play.
until_session() { until_eq "$1" "$2" session_id; }
# Waiting for "no record" must accept either shape - a state file with the
# record retired (NOSESSION) or no state file yet (NOFILE, e.g. straight after
# `run.sh clean`). The ASSERTIONS stay strict: a vanished state file is a
# different failure from a retired record and must not read as one.
until_no_session() {
  local secs=$1 i now
  for ((i = 0; i < secs * 10; i++)); do
    now=$(session_id)
    [[ $now == "$QA_NO_SESSION" || $now == "$QA_NO_FILE" ]] && return 0
    sleep 0.1
  done
  return 1
}
shell_pid() { cat "$SCRATCH/qs.pid" 2>/dev/null; }
# The play the successor accepts first: qs ipc fails until the IpcHandler
# exists, which is exactly the window ARCHITECTURE-PLAYER.md section 15
# describes. Returns the attempt number that landed.
play_asap() {
  local id=$1 i answer
  for ((i = 1; i <= 200; i++)); do
    answer=$(ipc play "$id")
    [[ $answer == ok ]] && { echo "$i"; return 0; }
    sleep 0.02
  done
  echo 0
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
# The positive control. Without it every sweep below is a statement about a
# string nobody has established is the player's argv (A5).
ck "P2 the player command line was actually read" '[[ -n "$cmd" && "$cmd" == *"input-ipc-server=$SOCK"* ]]'
ck "P2 no URL on the command line"           '[[ "$cmd" != *"://"* ]]'
ck "P2 no credential on the command line"    '[[ "$cmd" != *"$SECRET_PW"* && "$cmd" != *"$SECRET_USER"* ]]'
ck "P2 no token on the command line"         '[[ "$cmd" != *"$SECRET_TOKEN"* ]]'
ck "P2 no header value on the command line"  '[[ "$cmd" != *"$SECRET_UA"* && "$cmd" != *"--user-agent="* && "$cmd" != *"--referrer="* && "$cmd" != *"--http-header-fields"* ]]'
ck "P2 no channel name on the command line"  '[[ "$cmd" != *"Harness Live One"* ]]'
ck "P2 the neutral launch options are there" '[[ "$cmd" == *"--idle=once"* && "$cmd" == *"--wayland-app-id=omarchy-iptv"* && "$cmd" == *"--ytdl=no"* ]]'
# F2: a bare negated pgrep cannot tell "nothing is running" from "pgrep is not
# installed" or "the pattern stopped matching". Establish that pgrep answers.
ck "P2 pgrep answers on this box (positive control)" 'pgrep -f "input-ipc-server=$SOCK" >/dev/null 2>&1'
ck "P2 no yt-dlp process"                    '! pgrep -x yt-dlp >/dev/null 2>&1'

echo "== P3 the player is not a child of the shell"
QS_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null)
ck "P3 the shell is up"                                '[[ -n "$QS_PID" ]] && kill -0 "$QS_PID" 2>/dev/null'
ck "P3 the player's parent is not the shell"           '[[ "$(ppid_of "$PID1")" != "$QS_PID" ]]'
# -P "${QS_PID:-0}" would quietly become "-P 0" - a question about a pid that
# is not the shell - so the shell's pid has to be real before this means
# anything. `ck "P3 the shell is up"` above establishes it; assert it here too
# rather than relying on a check four lines away staying put.
ck "P3 the player is not a child of the shell"         '[[ -n "$QS_PID" ]] && ! pgrep -P "$QS_PID" -f "input-ipc-server=$SOCK" >/dev/null 2>&1'

echo "== P4 restart the shell while playing (the headline case)"
# C4: run.sh exits 2 when last-start.env is missing. An unchecked restart
# leaves the old shell dead and no new one, and P4/P13/P14 then measure
# nothing while their wait_log guards blame the wrong thing.
"$RUN" restart-shell >>"$LOG" 2>&1 || { bad "P4 restart-shell failed (see $LOG)"; exit 1; }
is "P4 the player survived the shell going away" "$(player_count)" "1"
is "P4 the same player pid" "$(player_pid)" "$PID1"
wait_log 'service loaded' 20 || bad "P4 the new shell did not start"
until_eq true 4 svc "d['playing']" || true      # the 2 s acceptance bar, doubled
is "P4 the new shell recovered now-playing" "$(svc "d['playing']")" "true"
is "P4 it recovered the right channel" "$(np id)" "t:live1"
ck "P4 it recovered the zap ring (launchedFrom, which no mpv property knows)" 'qa_value "$(np launchedFrom)"'
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
# A5: this is the unguarded half. P2's sweep has the "--idle=once" positive
# control four lines down; P5's has nothing between it and an empty $cmd.
ck "P5 the player command line was actually read" '[[ -n "$cmd" && "$cmd" == *"input-ipc-server=$SOCK"* ]]'
ck "P5 still nothing channel-specific on the command line" '[[ "$cmd" != *"://"* && "$cmd" != *"Harness Live Two"* ]]'

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
ck "P6 the socket file was unlinked" '[[ ! -e "$SOCK" ]]'

echo "== P10 a stop that the lock record would supersede still ends the player"
# Found in the live pass: `player stop` is detached, so a `superseded`
# refusal is invisible to the service, and anything that leaves a higher
# --seq in the lock file (a terminal `omarchy-iptv player stop`, another
# launcher) made every later stop a silent no-op - the UI went idle with the
# player still playing. The service must notice and finish the job.
ipc play "t:live1" >/dev/null
until_eq 1 15 player_count || bad "P10 no player to stop"
cache=$(ipc activeCache)
python3 "$PLUGIN_ROOT/bin/omarchy-iptv" player start --socket "$SOCK" --cache-dir "$cache" \
  --id "t:live1" --seq 9999 >>"$LOG" 2>&1
lock_seq=$(python3 -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get("seq"))
except Exception: print("")' "$SCRATCH/runtime/omarchy-iptv/player.lock")
is "P10 another launcher pushed the lock sequence ahead" "$lock_seq" "9999"
is "P10 it adopted rather than spawning" "$(player_count)" "1"
ipc stop >/dev/null
is "P10 the UI drops the channel at once" "$(svc "d['playing']")" "false"
until_eq 0 14 player_count || true
is "P10 the player is gone despite the superseded first stop" "$(player_count)" "0"
ck "P10 the socket file was unlinked" '[[ ! -e "$SOCK" ]]'

echo "== P7 a dead stream is detected, named and marked"
ipc play "t:dead1" >/dev/null
until_set 20 svc "d['failedAt'].get('t:dead1')" || true
failed_at=$(svc "d['failedAt'].get('t:dead1')")
ck "P7 the channel is marked failed for the session" 'qa_value "$failed_at"'
until_eq false 10 svc "d['playing']" || true
is "P7 playback did not stay up" "$(svc "d['playing']")" "false"
err=$(svc "d['lastError']")
ck "P7 a reason was recorded" 'qa_value "$err"'
ck "P7 the reason carries no credential and no token" 'qa_value "$err" && [[ "$err" != *"$SECRET_PW"* && "$err" != *"$SECRET_TOKEN"* && "$err" != *"$SECRET_USER"* ]]'
until_eq 0 8 player_count || true
is "P7 no player left behind by the failure" "$(player_count)" "0"

echo "== P11 D-PLY-1 trigger A: the health verdict's ladder-and-respawn"
# Found live at 8f9447e, 3/3: after `player restart --from term` the shell
# reported nothing playing and, because it also dropped playerWanted, the
# 250 ms retry timer was off, so it never reattached - while the relaunched
# player kept playing with a mapped window and a correct stash.
ipc play "t:live1" >/dev/null
until_eq 1 15 player_count || bad "P11 no player to wedge"
PID11=$(player_pid)
until_eq true 10 svc "d['playing']" || true
# Let `player start`'s own first-load window close, so the wedge provokes the
# health check and not the start.
for i in $(seq 1 250); do pgrep -f "bin/omarchy-iptv player start" >/dev/null 2>&1 || break; sleep 0.1; done
sleep 2
before11=$(log_count 'mpv unresponsive, restarting player')
kill -STOP "$PID11" 2>/dev/null
ck "P11 the player is wedged" '[[ -n "$PID11" ]]'
until_changed 45 "$PID11" player_pid || bad "P11 the health check never respawned the player"
PID11B=$(player_pid)
is "P11 exactly one player after the respawn" "$(player_count)" "1"
ck "P11 it is a NEW player" '[[ -n "$PID11B" && "$PID11B" != "$PID11" ]]'
until_eq true 10 svc "d['socketAttached']" || true
is "P11 the observer reattached to the new player" "$(svc "d['socketAttached']")" "true"
is "P11 the shell still wants the player (the retry timer stays armed)" "$(svc "d['playerWanted']")" "true"
is "P11 the interface is NOT idle while the player plays" "$(svc "d['playing']")" "true"
is "P11 it still names the right channel" "$(np id)" "t:live1"
is "P11 the zap ring survived the respawn" "$(np launchedFrom)" "g:Harness"
is "P11 still exactly one window" "$(windows_named)" "1"
is "P11 exactly ONE relaunch, not a second one at the healthy player" "$(( $(log_count 'mpv unresponsive, restarting player') - before11 ))" "1"

echo "== P12 D-PLY-1 trigger B: the socket-unlink recovery"
# The same end state from a second, independent trigger (2/2 live): remove
# the socket, play another channel, and `player start` finds the old player
# unreachable, ladders it down and spawns a replacement. Start from a
# player the observer is ATTACHED to, independently of how P11 ended - it is
# the attached observer's EOF that the defect misreads, so a shell P11 left
# idle would hide it.
ipc stop >/dev/null
until_eq 0 10 player_count || true
ipc play "t:live1" >/dev/null
until_eq 1 15 player_count || bad "P12 no player to strand"
until_eq true 15 svc "d['socketAttached']" || bad "P12 the observer never attached"
for i in $(seq 1 250); do pgrep -f "bin/omarchy-iptv player start" >/dev/null 2>&1 || break; sleep 0.1; done
PID12=$(player_pid)
rm -f "$SOCK"
ipc play "t:live2" >/dev/null
until_changed 30 "$PID12" player_pid || bad "P12 the helper never replaced the unreachable player"
PID12B=$(player_pid)
is "P12 exactly one player after the respawn" "$(player_count)" "1"
until_eq true 15 svc "d['socketAttached']" || true
is "P12 the observer reattached to the new player" "$(svc "d['socketAttached']")" "true"
is "P12 the shell still wants the player" "$(svc "d['playerWanted']")" "true"
is "P12 the interface is NOT idle while the player plays" "$(svc "d['playing']")" "true"
is "P12 it moved to the channel that was asked for" "$(np id)" "t:live2"
until_eq "omarchy-iptv|Harness Live Two" 10 window_of "$PID12B" || true
is "P12 the window is the new player's, titled with the channel" "$(window_of "$PID12B")" "omarchy-iptv|Harness Live Two"
is "P12 still exactly one window" "$(windows_named)" "1"

echo "== P13 D-PLY-4: the startup state race (ARCHITECTURE-PLAYER.md section 15)"
# Measured by QA at 14 losses in 30 trials. state.json is read
# asynchronously while a play can be issued immediately, so the arriving
# file used to replace the session record the play had just written - and
# PO-3 then had no evidence that the channel died unattended.
losses=0
nostarts=0
landed=""
for ((trial = 1; trial <= RACE_TRIALS; trial++)); do
  ipc stop >/dev/null
  until_eq 0 10 player_count || true
  until_no_session 6 || true
  "$RUN" restart-shell >>"$LOG" 2>&1 || { bad "P13 trial $trial: restart-shell failed (see $LOG)"; exit 1; }
  attempt=$(play_asap "t:live1")
  landed="$landed $attempt"
  until_eq true 15 svc "d['playing']" || true
  if [[ "$(svc "d['playing']")" != "true" ]]; then
    # The worse half of the same race: the probe's stale "nothing is
    # running" cleared nowPlaying and drainPendingPlay dropped the play.
    bad "P13 trial $trial: the play was DROPPED, nothing ever started"
    nostarts=$((nostarts + 1))
    continue
  fi
  until_session "t:live1" 8 || true
  [[ "$(session_id)" == "t:live1" ]] || losses=$((losses + 1))
done
echo "   P13 the play landed on attempt(s):$landed"
is "P13 no play issued at shell start is dropped ($RACE_TRIALS trials)" "$nostarts" "0"
is "P13 no play issued at shell start loses its session record ($RACE_TRIALS trials)" "$losses" "0"
is "P13 and the record names the channel that is demonstrably playing" "$(session_id)" "$(np id)"

echo "== P14 D-PLY-3: PO-3's mark is raised once, not on every later start"
# The full PO-3 procedure: play, kill the shell and then the player with
# nobody listening, come back. The mark must land once and the record must be
# RETIRED - live at 8f9447e it stayed on disk in 2 runs of 3, so the next
# start consumed it again and re-marked the same channel with the same HH:MM.
ipc play "t:live1" >/dev/null
until_eq 1 15 player_count || bad "P14 no player to abandon"
until_session "t:live1" 10 || true
is "P14 the play wrote a session record" "$(session_id)" "t:live1"
kill -KILL "$(shell_pid)" 2>/dev/null
sleep 0.5
for pid in $(player_pids); do kill -KILL "$pid" 2>/dev/null; done
until_eq 0 8 player_count || true
: >"$SCRATCH/harness.log"
"$RUN" restart-shell >>"$LOG" 2>&1 || { bad "P14 restart-shell failed (see $LOG)"; exit 1; }
wait_log 'service loaded' 20 || bad "P14 the shell did not come back"
until_set 15 svc "d['failedAt'].get('t:live1')" || true
mark14=$(svc "d['failedAt'].get('t:live1')")
ck "P14 the channel that died unattended is marked in the guide" 'qa_value "$mark14"'
until_no_session 10 || true
is "P14 the record is retired once it has been consumed" "$(session_id)" "$QA_NO_SESSION"
for again in 1 2; do
  "$RUN" restart-shell >>"$LOG" 2>&1 || { bad "P14 restart $again failed (see $LOG)"; exit 1; }
  wait_log 'service loaded' 20 || bad "P14 restart $again did not come back"
  sleep 3
  # F1's positive control. Without it, the two assertions below are satisfied
  # by a shell that never came up: the old helpers answered a dead IPC with
  # exactly the "" they demanded. NOFIELD/NOSESSION are answers from a service
  # that is alive; this line proves it is.
  is "P14 start $again the service is reachable (the fixture's 3 channels)" "$(svc "d['channels']")" "3"
  is "P14 start $again raises no second mark for the same event" "$(svc "d['failedAt'].get('t:live1')")" "$QA_NO_FIELD"
  is "P14 start $again still finds no record" "$(session_id)" "$QA_NO_SESSION"
done

echo "== P9 the harness reaps a detached grandchild"
ipc play "t:live1" >/dev/null
until_eq 1 15 player_count || bad "P9 no player to reap"
# F2. `! pgrep -f "quickshell -p $SCRATCH/root"` is the SAME pattern run.sh's
# own `pkill -f` uses to reap. If the launcher's argv ever stops matching it,
# reap stops reaping AND this check reports PASS - one point of failure shared
# between the teardown and its only verifier. So prove the pattern matches
# while the shell is up, before trusting it to say the shell is gone.
ck "P9 the reap pattern matches the running shell (positive control)" 'pgrep -f "quickshell -p $SCRATCH/root" >/dev/null'
"$RUN" reap >>"$LOG" 2>&1
until_eq 0 8 player_count || true
is "P9 reap killed the detached player" "$(player_count)" "0"
ck "P9 reap stopped the shell" '! pgrep -f "quickshell -p $SCRATCH/root" >/dev/null'

# The floor. D-PLY-9 was not that one assertion was wrong - it was that bash
# offers NO way to turn a failed expansion into a failed test, so the check
# vanished and the summary printed one line less than anybody expected and
# nobody counted. This is the only thing that closes that class: assert how
# many assertions ran, unguarded, so a check that stops executing turns the
# run red instead of shortening the summary.
#
# It counts `checks` (is/ck) rather than pass+fail, because the twelve
# `|| bad` guards move `fail` without being assertions - on the --baseline
# run, where five of them fire, a pass+fail floor would go red for a reason
# that has nothing to do with a missing check.
#
# Recount after adding or removing one:
#   grep -c '^\(is\|ck\) ' scripts/dev-harness/player-scenario.sh   -> top level
#   plus the three inside P14's `for again in 1 2` loop, twice.
# Never lower it to make a run green.
EXPECTED_CHECKS=82
ran=$checks
is "the harness ran every check it has" "$ran" "$EXPECTED_CHECKS"

printf '\n== summary: %d passed, %d failed, %d assertions executed\n' "$pass" "$fail" "$checks"
(( fail == 0 )) || exit 1
