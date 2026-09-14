#!/bin/bash
# scripts/qa-player-scenarios.sh -- the six NEW detached-player harness
# scenarios of docs/QA-PLAYER.md section 8.1 (PLY-H11..H16), printed or, with
# --apply, executed against the dev harness (scripts/dev-harness/run.sh) in a
# scratch directory. PLY-H01..H10 are shipped and live in
# scripts/dev-harness/player-scenario.sh; this script does not repeat them.
#
#   qa-player-scenarios.sh list                        scenario ids, titles, what each needs
#   qa-player-scenarios.sh print <PLY-Hnn>             print the exact commands and EXPECT lines
#   qa-player-scenarios.sh run <PLY-Hnn> --apply       execute the deterministic steps (same output)
#   qa-player-scenarios.sh run all --apply             every scenario in order
#   qa-player-scenarios.sh baseline <PLY-Hnn> <ref>    CLAUDE.md rule 11: the same checks against <ref>
#   qa-player-scenarios.sh check-harness               which harness / helper verbs are present
#   qa-player-scenarios.sh fixtures [--apply]          make the media tests/fixtures/qa-player needs
#   qa-player-scenarios.sh stop                        reap a harness started by `run`
#
# DRY BY DEFAULT. Without --apply nothing runs: every step is printed as the
# shell line it would be, with its EXPECT. This is the same contract as
# scripts/qa-sources-scenarios.sh.
#
# Everything lives under $OMARCHY_IPTV_HARNESS_DIR (default
# $XDG_RUNTIME_DIR/omarchy-iptv-qa-player). The harness exports its OWN
# XDG_RUNTIME_DIR, so nothing here can reach the live player's socket. The
# script REFUSES to run when that directory resolves into a real plugin
# location (~/.config, ~/.cache/omarchy-iptv, ~/.local/state/omarchy-iptv,
# /usr/share/omarchy, $XDG_RUNTIME_DIR/omarchy-iptv) or into the repository,
# and it refuses outright to signal a process whose --input-ipc-server is not
# under the scratch tree. It never calls `omarchy plugin|bar|theme`, never
# restarts the user's shell and never uses sudo.
#
# Scenario -> case map (docs/QA-PLAYER.md section 1.1):
#   PLY-H11  restart at 0/100/300/600 ms after a zap          PLY-RST-02
#   PLY-H12  restart inside the 3 s first-load window         PLY-RST-03
#   PLY-H13  unlink the socket under a live attached player   PLY-RST-06
#   PLY-H14  rm -rf the scratch runtime dir while playing     PLY-RST-08
#   PLY-H15  a stub mpv that never binds; a missing mpv       PLY-LIFE-06, 07, PLY-RST-14
#   PLY-H16  the channel id disappears between shells         PLY-RST-16
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
RUN="$ROOT/scripts/dev-harness/run.sh"
HELPER="$ROOT/bin/omarchy-iptv"
FIX="$ROOT/tests/fixtures/qa-player"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-qa-player}
SOCK="$SCRATCH/runtime/omarchy-iptv/mpv.sock"
PLAYLIST="http://127.0.0.1:8765/qa-player.m3u"
APPLY=0
BASELINE=""
pass=0
fail=0

usage() { sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'; }
die()   { echo "qa-player: $*" >&2; exit 1; }
ok()    { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad()   { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
is()    { if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }
ck()    { if eval "$2"; then ok "$1"; else bad "$1"; fi; }

# ---------------------------------------------------------------- guards

refuse_real_dirs() {
  local real home b
  real=$(realpath -m -- "$SCRATCH")
  home=$(realpath -m -- "$HOME")
  [[ $real == /* ]] || die "scratch dir must be absolute: $SCRATCH"
  for b in / "$home"; do
    [[ $real == "$b" ]] && die "refusing: scratch dir $real is $b itself; set OMARCHY_IPTV_HARNESS_DIR to a scratch path"
  done
  for b in "$home/.config" "$home/.cache/omarchy-iptv" "$home/.local/state/omarchy-iptv" \
           /usr/share/omarchy "$REAL_RUNTIME/omarchy-iptv" "$ROOT"; do
    b=$(realpath -m -- "$b")
    if [[ $real == "$b" || $real == "$b"/* ]]; then
      die "refusing: scratch dir $real is inside $b (a real plugin location or the repository); set OMARCHY_IPTV_HARNESS_DIR to a scratch path"
    fi
  done
}

# The one place this script is allowed to signal anything. A pid whose
# --input-ipc-server is not under the scratch tree is the USER'S player (or
# somebody else's) and is never touched, whatever the caller asked for.
scratch_player_pids() {
  local p cmd
  for p in /proc/[0-9]*; do
    [[ -r $p/cmdline ]] || continue
    cmd=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null) || continue
    [[ $cmd == *"--input-ipc-server=$SOCK"* ]] || continue
    basename "$p"
  done
}
signal_scratch_player() {   # signal_scratch_player <signal>
  local sig=$1 p n=0
  for p in $(scratch_player_pids); do kill "-$sig" "$p" 2>/dev/null && n=$((n + 1)); done
  echo "$n"
}

# ------------------------------------------------------------- step runner

step()    { printf '# %s\n$ %s\n' "$1" "$(printf '%q ' "${@:2}")"; if ((APPLY)); then "${@:2}"; fi; }
sh_step() { printf '# %s\n$ %s\n' "$1" "$2"; if ((APPLY)); then bash -c "$2"; fi; }
expect()  { printf 'EXPECT: %s\n' "$*"; }
note()    { printf 'NOTE: %s\n' "$*"; }
head1()   { printf '\n===== %s =====\n' "$*"; }

ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
svc()  { python3 -c '
import json, sys
try: d = json.loads(sys.argv[2])["service"]
except Exception: print(""); raise SystemExit(0)
try: v = eval(sys.argv[1])
except Exception: v = None
print(json.dumps(v) if isinstance(v, bool) else ("" if v is None else v))' "$1" "$(ipc state)" 2>/dev/null; }
wins() { hyprctl clients -j 2>/dev/null | jq '[.[]|select(.class=="omarchy-iptv")]|length' 2>/dev/null || echo 0; }
mpvq() { printf '%s\n' "$1" | socat -t2 - "UNIX-CONNECT:$SOCK" 2>/dev/null | head -1; }

# The committed fixture points at 127.0.0.1:8791, the port the LIVE runbook
# (docs/QA-PLAYER.md 9.3) serves it on. The harness serves its own fixtures
# directory on 8765, so the playlist is copied in with the port rewritten and
# the media linked beside it. Without this every channel is dead in the
# harness and the scenarios measure a failure path instead of the one they
# name - which is exactly what the first run of PLY-H13 did.
HPORT=8765
prepare_fixture() {
  sh_step "copy the fixture into the harness tree with the port rewritten to $HPORT" \
    "mkdir -p '$SCRATCH/fixtures/live/qa-token-XYZ' && \\
     sed 's|127\\.0\\.0\\.1:8791|127.0.0.1:$HPORT|g' '$FIX/qa-player.m3u' > '$SCRATCH/fixtures/qa-player.m3u' && \\
     cp -f '$FIX/test.ts' '$SCRATCH/fixtures/test.ts' && \\
     cp -f '$FIX/short.ts' '$SCRATCH/fixtures/short.ts' && \\
     cp -f '$FIX/test.ts' '$SCRATCH/fixtures/live/qa-token-XYZ/stream.ts' && \\
     grep -c '^http' '$SCRATCH/fixtures/qa-player.m3u'"
  expect "9 URLs, all on 127.0.0.1:$HPORT"
}
start_harness() {
  sh_step "start the harness detached on its own runtime dir" \
    "'$RUN' clean && '$RUN' --detach --serve --playlist '$FIX/qa-player.m3u' --timeout 0"
  prepare_fixture
  sh_step "point the service at the rewritten playlist and wait for the channels" \
    "'$RUN' ipc set playlistUrl 'http://127.0.0.1:$HPORT/qa-player.m3u' >/dev/null; sleep 4; '$RUN' ipc state | jq -r '.service.channels|length'"
  expect "9"
}

# ---------------------------------------------------------------- fixtures

cmd_fixtures() {
  head1 "fixtures for tests/fixtures/qa-player"
  step "generate the local media (ffmpeg; skipped when the files exist)" "$FIX/make-media.sh"
  expect "test.ts, short.ts and live/qa-token-XYZ/stream.ts exist under $FIX"
  sh_step "the playlist parses and carries the nine QA channels" \
    "python3 '$HELPER' playlist --url '$FIX/qa-player.m3u' | jq -r '.channels|length'"
  expect "9"
}

# ---------------------------------------------------------- check-harness

cmd_check_harness() {
  local v
  head1 "harness and helper verbs this script needs"
  for v in clean ipc restart-shell shell-stop reap; do
    if grep -qE "^  $v\)" "$RUN"; then ok "run.sh $v"; else bad "run.sh $v MISSING"; fi
  done
  for v in --detach --serve --instance --playlist --timeout; do
    if grep -q -- "$v" "$RUN"; then ok "run.sh $v"; else bad "run.sh $v MISSING"; fi
  done
  for v in "player start" "player stop" "player probe" "player restart" "player orphan-check"; do
    if "$HELPER" ${v#player } --help >/dev/null 2>&1 || "$HELPER" player "${v#player }" --help >/dev/null 2>&1; then
      ok "helper $v"
    else bad "helper $v MISSING"; fi
  done
  for v in socat jq ffmpeg hyprctl; do
    if command -v "$v" >/dev/null; then ok "tool $v"; else bad "tool $v MISSING"; fi
  done
  printf '\n%s pass, %s fail\n' "$pass" "$fail"
}

# --------------------------------------------------------------- PLY-H11

h11() {
  head1 "PLY-H11  restart at 0 / 100 / 300 / 600 ms after a zap  (PLY-RST-02)"
  note "The window between play's helper call and its reply. The stash is written"
  note "BEFORE the loadfile with the new identity and rewritten AFTER with the"
  note "entry id, so the stash is the truth in either outcome. Four offsets"
  note "because the failure this looks for is an ordering one."
  start_harness
  local off
  for off in 0 0.1 0.3 0.6; do
    sh_step "settle on the live channel" \
      "'$RUN' ipc play t:qa.live >/dev/null; sleep 3"
    sh_step "zap to another channel and restart the harness shell $off s later" \
      "( '$RUN' ipc play t:qa.plain >/dev/null & ); sleep $off; '$RUN' restart-shell; sleep 4"
    sh_step "exactly one scratch player" \
      "test \$(pgrep -u \$(id -u) -f -- '--input-ipc-server=$SOCK' | wc -l) -eq 1 && echo one || echo NOT-ONE"
    expect "one"
    sh_step "nowPlaying matches what the player is actually on" \
      "diff <(printf '%s\\n' \"\$('$RUN' ipc state | jq -r '.service.nowPlaying.id // \"null\"')\") \\
            <(printf '%s\\n' \"\$(printf '%s\\n' '{\"command\":[\"get_property\",\"user-data/omarchy-iptv\"]}' | socat -t2 - UNIX-CONNECT:$SOCK | jq -r '.data.id // \"null\"')\")"
    expect "no output: the id in the stash and the id the guide shows are the same"
    expect "the id is either t:qa.live or t:qa.plain, never a third state"
    note "If the loadfile never landed mpv exited under --idle=once: the probe"
    note "reports running:false and state.json.session drives the PO-3 mark."
  done
  sh_step "reap" "'$RUN' reap"
}

# --------------------------------------------------------------- PLY-H12

h12() {
  head1 "PLY-H12  restart inside the 3 s first-load window on a dead channel  (PLY-RST-03)"
  note "The trap is a DOUBLE toast: the old shell may raise one before dying and"
  note "the new one must not raise a second for the same event. Counted on the"
  note "session bus, because omarchy-shell notifications showHistory returns"
  note "'ok' and opens a panel - it cannot be counted with wc -l."
  start_harness
  sh_step "start a notification counter on the session bus" \
    "dbus-monitor --session \"interface='org.freedesktop.Notifications',member='Notify'\" > $SCRATCH/notify.txt 2>&1 & echo \$! > $SCRATCH/notify.pid; sleep 1"
  sh_step "count before" "grep -c 'member=Notify' $SCRATCH/notify.txt"
  sh_step "play the dead credentialed fixture channel and restart inside 3 s" \
    "'$RUN' ipc play t:qa.sentinel-dead >/dev/null; sleep 1; '$RUN' restart-shell; sleep 6"
  sh_step "count after" "grep -c 'member=Notify' $SCRATCH/notify.txt"
  expect "the count grew by AT MOST 1 in total, and by 0 across the restart itself"
  sh_step "the reattached shell reports nothing playing" \
    "'$RUN' ipc state | jq -c '{playing:.service.playing, nowPlaying:.service.nowPlaying}'"
  expect "playing false, nowPlaying null"
  sh_step "no needle reached any notification body" \
    "grep -cE 'qa-user|qa-secret|qa-token-XYZ|qa-ua-SENTINEL|://' $SCRATCH/notify.txt"
  expect "0"
  sh_step "stop the counter" "kill \$(cat $SCRATCH/notify.pid) 2>/dev/null; rm -f $SCRATCH/notify.pid"
  sh_step "reap" "'$RUN' reap"
  note "failedAt is session-only (Service.qml:230), so the mark does NOT survive"
  note "the restart when a live shell already saw and toasted the failure. Only"
  note "the PO-3 path (PLY-WEAK-06) carries a mark across a shell boundary."
}

# --------------------------------------------------------------- PLY-H13

h13() {
  head1 "PLY-H13  unlink the socket file under a live attached player  (PLY-RST-06)"
  note "Two opposite truths, both from the spike: an ALREADY ATTACHED connection"
  note "survives the unlink (Q4 row 3), while a FUTURE connect gets"
  note "ServerNotFoundError instead of ConnectionRefusedError."
  start_harness
  sh_step "play and confirm the observer is attached" \
    "'$RUN' ipc play t:qa.live >/dev/null; sleep 4; '$RUN' ipc state | jq -r '.service.player.attached'"
  expect "true"
  sh_step "record the pid" "pgrep -u \$(id -u) -f -- '--input-ipc-server=$SOCK' | head -1"
  sh_step "unlink the socket under it" "rm -f '$SOCK'; sleep 1"
  sh_step "the LIVE half: the attached observer survives the unlink" \
    "'$RUN' ipc state | jq -r '.service.player.attached'"
  expect "true  (the QML connection is unaffected: SPIKE Q4 row 3)"
  sh_step "the RECOVERY half: a fresh connect by path cannot reach it" \
    "python3 '$HELPER' player probe --socket '$SOCK' | jq -c '{running,responsive}'"
  expect "running true, responsive false (connect gives ENOENT)"
  note "COMMANDS DO NOT TRAVEL OVER THE OBSERVER. Service.qml's socket is a"
  note "read-only event stream; every zap and stop goes through the helper,"
  note "which connects BY PATH. So a zap after an unlink takes the wedged"
  note "branch of ARCH-P 4.5 - ladder down, then respawn into a re-created"
  note "0700 directory - rather than reusing the live connection."
  sh_step "zap after the unlink: one player at the end, on the new channel" \
    "'$RUN' ipc play t:qa.plain >/dev/null; sleep 5; '$RUN' ipc state | jq -c '{playing:.service.playing, id:.service.nowPlaying.id}'; pgrep -u \$(id -u) -f -- '--input-ipc-server=$SOCK' | wc -l"
  expect "playing true, id t:qa.plain, exactly 1 player, and never 2 at any sample"
  sh_step "the re-created directory and socket keep their modes" \
    "stat -c '%a %n' '$SCRATCH/runtime/omarchy-iptv' '$SOCK'"
  expect "700 for the directory, 600 for the socket"
  sh_step "reap" "'$RUN' reap"
}

# --------------------------------------------------------------- PLY-H14

h14() {
  head1 "PLY-H14  rm -rf the scratch runtime dir while playing  (PLY-RST-08)"
  note "NEVER the live /run/user/<uid>/omarchy-iptv. This scenario refuses to run"
  note "if SOCK does not resolve under the scratch tree (see refuse_real_dirs)."
  start_harness
  sh_step "play and record the pid and seq" \
    "'$RUN' ipc play t:qa.live >/dev/null; sleep 4; pgrep -u \$(id -u) -f -- '--input-ipc-server=$SOCK' | head -1; '$RUN' ipc state | jq -r '.service.player.seq'"
  sh_step "clear the runtime directory under the running player" \
    "rm -rf '$SCRATCH/runtime/omarchy-iptv'; sleep 1; ls -la '$SCRATCH/runtime' | head"
  sh_step "the /proc scan still finds it by the --input-ipc-server token" \
    "python3 '$HELPER' player probe --socket '$SOCK' | jq -c '{running,responsive,pid}'"
  expect "running true, responsive false (connect gives ENOENT), pid = the one recorded above"
  sh_step "a start ladders the unreachable player down and respawns" \
    "'$RUN' ipc play t:qa.plain >/dev/null; sleep 6"
  sh_step "freshly created 0700 directory, 0600 socket, 0600 lock" \
    "find '$SCRATCH/runtime/omarchy-iptv' -exec stat -c '%a %n' {} +"
  expect "700 for the directory, 600 for mpv.sock and player.lock, nothing else present"
  sh_step "playSeq resets on both sides together" \
    "'$RUN' ipc state | jq -r '.service.player.seq'; cat '$SCRATCH/runtime/omarchy-iptv/player.lock'"
  expect "status.player.seq and the seq in the new lock record agree; no 'busy' storm follows"
  sh_step "exactly one player" \
    "pgrep -u \$(id -u) -f -- '--input-ipc-server=$SOCK' | wc -l"
  expect "1"
  sh_step "reap" "'$RUN' reap"
}

# --------------------------------------------------------------- PLY-H15

h15() {
  head1 "PLY-H15  a stub mpv that never binds, a missing mpv, a shell killed mid-cold-start"
  head1 "         (PLY-LIFE-06, PLY-LIFE-07, PLY-RST-14)"
  note "mpv is an Omarchy dependency and removing it needs sudo, so the missing-mpv"
  note "half is only reachable through a PATH-shadowed stub (QA-PLAYER section 10 item 7)."
  sh_step "build the two stubs in the scratch tree" \
    "mkdir -p '$SCRATCH/stub-nobind' '$SCRATCH/stub-missing' && \\
     printf '#!/bin/sh\\n# never binds the socket: sleep past --spawn-timeout 5.0 and exit\\nexec sleep 30\\n' > '$SCRATCH/stub-nobind/mpv' && \\
     chmod +x '$SCRATCH/stub-nobind/mpv' && \\
     ls -la '$SCRATCH/stub-nobind/mpv'; echo '(stub-missing is an EMPTY dir: PATH=it means execvp gives ENOENT)'"
  head1 "PLY-LIFE-06  a spawn that never binds is reaped by its creator"
  sh_step "start with the non-binding stub first on PATH" \
    "PATH='$SCRATCH/stub-nobind:\$PATH' python3 '$HELPER' player start --socket '$SOCK' \\
       --cache-dir '$SCRATCH/cache/omarchy-iptv' --id t:qa.live --seq 1 --spawn-timeout 5.0 | jq -c '{ok,code,spawned,pid}'"
  expect "code no_socket after ~5 s; the stub's pid is dead afterwards; NO window is left behind"
  sh_step "nothing survived" \
    "pgrep -u \$(id -u) -f -- '--input-ipc-server=$SOCK' | wc -l; ls -la '$SCRATCH/runtime/omarchy-iptv' 2>&1 | tail -3"
  expect "0 players; the socket the stub never created is not left as a stale file"
  head1 "PLY-LIFE-07  mpv cannot be exec'd"
  sh_step "start with an EMPTY dir as the whole PATH" \
    "PATH='$SCRATCH/stub-missing' python3 '$HELPER' player start --socket '$SOCK' \\
       --cache-dir '$SCRATCH/cache/omarchy-iptv' --id t:qa.live --seq 2 | jq -c '{ok,code}'"
  expect "code mpv_missing, reported SYNCHRONOUSLY through the CLOEXEC errno pipe (ENOENT)"
  note "In the service this sets mpvAvailable=false and raises 'mpv not found' /"
  note "'Install mpv to play channels.', urgency critical, glyph U+F0567."
  head1 "PLY-RST-14  the shell is killed between the start issue and the socket bind"
  note "Designed bind latency 0.114-0.151 s. Ten runs. Both outcomes are a pass:"
  note "the helper completes the spawn as a reparented grandchild and the next"
  note "shell adopts it, OR the helper dies with it and its own 5 s"
  note "--spawn-timeout path reaps the spawn it created."
  note "A WINDOWED PLAYER THAT NOTHING CAN REACH IS A P1 FAIL."
  start_harness
  sh_step "ten runs, sampling the window count at 100 ms throughout" \
    "for i in \$(seq 10); do \\
       ( for j in \$(seq 40); do hyprctl clients -j | jq '[.[]|select(.class==\"omarchy-iptv\")]|length'; sleep 0.1; done ) > '$SCRATCH/winct-\$i.txt' & \\
       '$RUN' ipc play t:qa.live >/dev/null; sleep 0.12; '$RUN' shell-stop; sleep 3; \\
       '$RUN' --detach --serve --playlist '$FIX/qa-player.m3u' --timeout 0 >/dev/null 2>&1; sleep 4; \\
       wait; echo \"run \$i windows: \$(sort -u '$SCRATCH/winct-\$i.txt' | tr '\\n' ' ')\"; \\
       echo \"run \$i players: \$(pgrep -u \$(id -u) -f -- '--input-ipc-server=$SOCK' | wc -l)\"; \\
     done"
  expect "max window count 1 in every run; players 0 or 1, never 2"
  expect "when a player survives it answers the next shell's probe (adopted, not orphaned)"
  sh_step "reap" "'$RUN' reap"
}

# --------------------------------------------------------------- PLY-H16

h16() {
  head1 "PLY-H16  the channel id disappears from channels.json between shells  (PLY-RST-16)"
  note "nowPlaying must be restored from the stash BEFORE channelIndex exists, so"
  note "the bar is correct immediately; then reconcileNowPlaying() on"
  note "channelsLoaded must degrade to name-only rather than resolving to a"
  note "DIFFERENT channel. Never a match on the wrong row."
  start_harness
  sh_step "play a channel that is about to vanish" \
    "'$RUN' ipc play t:qa.nonascii >/dev/null; sleep 4; '$RUN' ipc state | jq -c '{id:.service.nowPlaying.id,name:.service.nowPlaying.name}'"
  sh_step "take the shell down, leaving the player alone" "'$RUN' shell-stop; sleep 1"
  sh_step "remove that channel from the served playlist and from the cache" \
    "python3 - <<'PY'
import json, os, re
fix = os.environ['SCRATCH'] + '/fixtures/qa-player.m3u'
src = open(fix).read().splitlines(True)
out, skip = [], 0
for i, line in enumerate(src):
    if 'tvg-id=\"qa.nonascii\"' in line: skip = 2
    if skip: skip -= 1; continue
    out.append(line)
open(fix, 'w').writelines(out)
print('playlist entries left:', sum(1 for l in out if l.startswith('#EXTINF')))
PY"
  sh_step "bring a new shell up against the shortened playlist" \
    "'$RUN' --detach --serve --playlist '$SCRATCH/fixtures/qa-player.m3u' --timeout 0 >/dev/null 2>&1; sleep 6"
  sh_step "the bar still names the right channel" \
    "'$RUN' ipc state | jq -c '{playing:.service.playing, id:.service.nowPlaying.id, name:.service.nowPlaying.name, from:.service.nowPlaying.launchedFrom}'"
  expect "playing true; name is the channel that is actually playing (name-only degrade)"
  expect "the id is NOT silently re-pointed at a different channel"
  sh_step "the zap ring is empty rather than wrong" \
    "'$RUN' ipc zap 1; sleep 3; '$RUN' ipc state | jq -r '.service.nowPlaying.id // \"null\"'"
  expect "unchanged: an empty ring is correct, a jump to an unrelated channel is a P2"
  sh_step "the same pid throughout" \
    "pgrep -u \$(id -u) -f -- '--input-ipc-server=$SOCK' | wc -l"
  expect "1"
  sh_step "reap" "'$RUN' reap"
}

# ---------------------------------------------------------------- driver

cmd_list() {
  cat <<'EOF'
PLY-H11  restart at 0/100/300/600 ms after a zap           PLY-RST-02   needs: --detach, restart-shell, the qa-player fixture
PLY-H12  restart inside the 3 s first-load window          PLY-RST-03   needs: dbus-monitor (showHistory cannot be counted)
PLY-H13  unlink the socket under a live attached player    PLY-RST-06   needs: socat
PLY-H14  rm -rf the scratch runtime dir while playing      PLY-RST-08   needs: nothing extra; refuses outside the scratch tree
PLY-H15  stub mpv that never binds; missing mpv; killed    PLY-LIFE-06, PLY-LIFE-07, PLY-RST-14
         mid-cold-start
PLY-H16  the channel id disappears between shells          PLY-RST-16   needs: --detach, shell-stop

Rule 11 (CLAUDE.md 11, and the PO's double force in ARCH-P section 12): every
scenario above must be shown to FAIL against pre-M2-02 code before it counts
as evidence. Use `baseline <PLY-Hnn> <ref>`; it exports <ref> and re-runs the
same steps with OMARCHY_IPTV_PLUGIN_ROOT pointed at the export. Record BOTH
counts in docs/QA-RESULTS.md.
EOF
}

cmd_baseline() {
  local id=$1 ref=$2 exp
  exp="$SCRATCH/baseline-$ref"
  refuse_real_dirs
  head1 "rule 11 baseline: $id against $ref"
  step "export the tree" bash -c "rm -rf '$exp' && mkdir -p '$exp' && git -C '$ROOT' archive '$ref' | tar -x -C '$exp'"
  note "now re-run with OMARCHY_IPTV_PLUGIN_ROOT='$exp'; the checks this scenario"
  note "owns must FAIL there. A scenario that passes on both trees is a"
  note "regression guard, not evidence for this milestone - label it as one."
  step "run" env OMARCHY_IPTV_PLUGIN_ROOT="$exp" "$0" run "$id" ${APPLY:+--apply}
}

main() {
  local cmd=${1:-}; shift || true
  local args=()
  while (($# > 0)); do
    case $1 in
      --apply) APPLY=1 ;;
      --baseline) BASELINE=$2; shift ;;
      -h|--help) usage; exit 0 ;;
      *) args+=("$1") ;;
    esac
    shift
  done
  case $cmd in
    list)          cmd_list ;;
    check-harness) cmd_check_harness ;;
    fixtures)      refuse_real_dirs; cmd_fixtures ;;
    stop)          refuse_real_dirs; step "reap the harness" "$RUN" reap ;;
    baseline)      cmd_baseline "${args[0]}" "${args[1]}" ;;
    print|run)
      refuse_real_dirs
      case ${args[0]:-all} in
        PLY-H11|H11) h11 ;;
        PLY-H12|H12) h12 ;;
        PLY-H13|H13) h13 ;;
        PLY-H14|H14) h14 ;;
        PLY-H15|H15) h15 ;;
        PLY-H16|H16) h16 ;;
        all)         h11; h12; h13; h14; h15; h16 ;;
        *) die "unknown scenario: ${args[0]} (try: list)" ;;
      esac
      ((APPLY)) || printf '\n(dry run: nothing above was executed. Add --apply to run it.)\n'
      ;;
    ""|-h|--help) usage ;;
    *) die "unknown command: $cmd (try: list)" ;;
  esac
}

main "$@"
