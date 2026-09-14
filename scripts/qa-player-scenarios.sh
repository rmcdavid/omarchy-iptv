#!/bin/bash
# scripts/qa-player-scenarios.sh -- the NEW detached-player harness scenarios
# of docs/QA-PLAYER.md section 8.1 (PLY-H11..H18), printed or, with --apply,
# executed against the dev harness (scripts/dev-harness/run.sh) in a scratch
# directory. PLY-H01..H10 are shipped and live in
# scripts/dev-harness/player-scenario.sh; this script does not repeat them.
#
#   qa-player-scenarios.sh list                        scenario ids, titles, what each needs
#   qa-player-scenarios.sh print <PLY-Hnn>             print the exact commands and EXPECT lines
#   qa-player-scenarios.sh run <PLY-Hnn> --apply       execute the deterministic steps (same output)
#   qa-player-scenarios.sh run all --apply             every scenario in order
#   qa-player-scenarios.sh run cold --apply            only PLY-H17/H18 phase A: no display, no shell
#   qa-player-scenarios.sh run PLY-H18 --apply --with-display   phase B as well (display lane only)
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
# /usr/share/omarchy, $XDG_RUNTIME_DIR/omarchy-iptv) or into the repository.
# Every signal this script sends to a player goes through
# signal_scratch_player, which will not signal a process whose
# --input-ipc-server is outside the scratch tree - see `stop`. It never calls
# `omarchy plugin|bar|theme`, never restarts the user's shell and never uses
# sudo.
#
# Scenario -> case map (docs/QA-PLAYER.md section 1.1):
#   PLY-H11  restart at 0/100/300/600 ms after a zap          PLY-RST-02
#   PLY-H12  restart inside the 3 s first-load window         PLY-RST-03
#   PLY-H13  unlink the socket under a live attached player   PLY-RST-06
#   PLY-H14  rm -rf the scratch runtime dir while playing     PLY-RST-08
#   PLY-H15  a stub mpv that never binds; a missing mpv       PLY-LIFE-06, 07, PLY-RST-14
#   PLY-H16  the channel id disappears between shells         PLY-RST-16
#   PLY-H17  a cold start that is no longer the newest        PLY-LIFE-16
#            intent stands down (D-PLY-11's fix)
#   PLY-H18  a divergence is visible to the health tick and   PLY-LIFE-17
#            the label converges within one tick (CL6)
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
RUN="$ROOT/scripts/dev-harness/run.sh"
# The TREE UNDER TEST. `baseline` exports a ref and re-runs this same script
# with OMARCHY_IPTV_PLUGIN_ROOT pointing at the export, and run.sh already
# honours it - but HELPER was pinned to $ROOT, so every step that calls the
# helper directly (PLY-H15's three, and now PLY-H17/H18's) ran TODAY'S helper
# under `baseline` and could not have failed there whatever the ref said.
# Same family as D-PLY-9: a comparison with only one side.
PLUGIN_ROOT=${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}
HELPER="$PLUGIN_ROOT/bin/omarchy-iptv"
# QA TOOLING, never the tree under test: the stub mpv is this lane's
# instrument and always comes from the current checkout, the way the scenario
# text itself does.
STUB="$ROOT/scripts/qa-stub-mpv.py"
FIX="$ROOT/tests/fixtures/qa-player"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-qa-player}
SOCK="$SCRATCH/runtime/omarchy-iptv/mpv.sock"
# PLY-H17/H18 run with no shell and no display at all, so they keep their own
# runtime tree beside the harness one and never share its socket.
COLD="$SCRATCH/cold"
COLD_SOCK="$COLD/runtime/omarchy-iptv/mpv.sock"
PLAYLIST="http://127.0.0.1:8765/qa-player.m3u"
APPLY=0
WITH_DISPLAY=0
BASELINE=""
pass=0
fail=0
checks=0

# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

usage() { sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'; }
die()   { echo "qa-player: $*" >&2; exit 1; }
ok()    { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad()   { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
is()    { checks=$((checks + 1)); if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }
ck()    { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }
# The D-PLY-9 floor, per scenario. Bash gives no way to turn a failed
# expansion into a failed test, so a check that stops executing merely
# shortens the summary. Only the asserting scenarios carry one.
floor() {   # floor <label> <expected assertions>
  local label=$1 want=$2
  if [[ "$checks" == "$want" ]]; then ok "$label ran every check it has ($want)"
  else bad "$label ran $checks assertions, expected $want (one stopped executing)"; fi
}

# ---------------------------------------------------------------- guards

refuse_real_dirs() {
  local real home b
  # F4. sh_step interpolates $SCRATCH (from OMARCHY_IPTV_HARNESS_DIR) into a
  # `bash -c` snippet unquoted, which is exactly the shape CLAUDE.md
  # constraint 2 forbids: a scratch path carrying a quote or $(...) would be
  # EXECUTED. Until every snippet takes its data as argv, refuse to run
  # against a path that could be shell text at all.
  qa_safe_path "$SCRATCH" || die "refusing: OMARCHY_IPTV_HARNESS_DIR carries shell metacharacters: $SCRATCH"
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

# A6. Both functions above were defined and never called: the header advertised
# a safety guarantee implemented entirely by dead code, while the killing that
# actually happened went through `run.sh reap`. `stop` now reaps and then
# sweeps through the guarded path, so the guarantee is on the executed route.
cmd_stop() {
  refuse_real_dirs
  step "reap the harness" "$RUN" reap
  if (( APPLY )); then
    local left
    left=$(signal_scratch_player TERM)
    printf '# sweep: %s scratch player(s) signalled (never a player outside %s)\n' "$left" "$SCRATCH"
    sleep 0.5
    left=$(scratch_player_pids | wc -l | tr -d ' ')
    if [[ "$left" == "0" ]]; then ok "no scratch player survived the reap"
    else bad "$left scratch player(s) still running after reap"; fi
  else
    printf '# then signal_scratch_player TERM, which refuses any pid whose\n'
    printf '# --input-ipc-server is not %s\n' "$SOCK"
  fi
}

# ------------------------------------------------------------- step runner

step()    { printf '# %s\n$ %s\n' "$1" "$(printf '%q ' "${@:2}")"; if ((APPLY)); then "${@:2}"; fi; }
sh_step() { printf '# %s\n$ %s\n' "$1" "$2"; if ((APPLY)); then bash -c "$2"; fi; }
expect()  { printf 'EXPECT: %s\n' "$*"; }
note()    { printf 'NOTE: %s\n' "$*"; }
head1()   { printf '\n===== %s =====\n' "$*"; }

ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
# F1's shape, in the helpers CL7's conversion will wire up next round: this
# printed "" for a dead IPC, for an absent field and for a healthy "unset"
# alike. Fixed here so the conversion does not inherit it.
svc()  { qa_field "$1" "$(ipc state)"; }
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
# B1. The setup used to be three printed steps whose exit status nobody read,
# so a scenario whose harness never came up ran every later step against
# nothing and printed its EXPECT lines exactly as a good run does. Setting up
# is not a scenario assertion (those are CL7's next round) - it is the
# precondition without which none of them mean anything. Returns non-zero so
# the caller can abandon the scenario.
start_harness() {
  sh_step "start the harness detached on its own runtime dir" \
    "'$RUN' clean && '$RUN' --detach --serve --playlist '$FIX/qa-player.m3u' --timeout 0"
  prepare_fixture
  sh_step "point the service at the rewritten playlist and wait for the channels" \
    "'$RUN' ipc set playlistUrl 'http://127.0.0.1:$HPORT/qa-player.m3u' >/dev/null; sleep 4; '$RUN' ipc state | jq -r '.service.channels|length'"
  expect "9"
  (( APPLY )) || return 0
  local answer count i
  for ((i = 0; i < 20; i++)); do
    answer=$(ipc state)
    [[ -n $answer ]] && break
    sleep 1
  done
  if [[ -z $answer ]]; then
    bad "SETUP FAILED: the harness never answered; every step below would measure nothing"
    return 1
  fi
  count=$(jq -r '.service.channels|length' <<<"$answer" 2>/dev/null)
  if [[ "$count" != "9" ]]; then
    bad "SETUP FAILED: the service loaded $count channels, not the fixture's 9"
    return 1
  fi
  ok "setup: the harness answered and loaded the fixture's 9 channels"
  return 0
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
    if qa_case_arm "$RUN" "$v"; then ok "run.sh $v"; else bad "run.sh $v MISSING"; fi
  done
  # D1. `grep -q -- "$v" "$RUN"` was satisfied by run.sh's own header comment
  # as readily as by its parser, so deleting `--detach) DETACH=1; ...` left
  # this gate green. Anchor on the case arm, the way the loop above always
  # did. Proven both ways in scripts/qa-lib-test.sh.
  for v in --detach --serve --instance --playlist --timeout; do
    if qa_case_arm "$RUN" "$v"; then ok "run.sh $v"; else bad "run.sh $v MISSING"; fi
  done
  # D2. The first branch of `"$HELPER" ${v#player } --help || "$HELPER" player
  # "${v#player }" --help` succeeded for `player stop` because the helper has
  # an unrelated top-level `stop` verb (the M1 mpv-IPC one), so this reported
  # ok even if the `player stop` subparser were gone. Of the five probed verbs
  # only `stop` collides - which is exactly why the fallback has to go: it
  # hides the one collision it was masking.
  for v in start stop probe restart orphan-check; do
    if "$HELPER" player "$v" --help >/dev/null 2>&1; then ok "helper player $v"
    else bad "helper player $v MISSING"; fi
  done
  for v in socat jq ffmpeg hyprctl; do
    if command -v "$v" >/dev/null; then ok "tool $v"; else bad "tool $v MISSING"; fi
  done
  printf '\n%s pass, %s fail\n' "$pass" "$fail"
  # B1. This ended on a printf and returned 0, so a MISSING harness verb -
  # the whole point of the command - exited green.
  (( fail == 0 ))
}

# --------------------------------------------------------------- PLY-H11

h11() {
  head1 "PLY-H11  restart at 0 / 100 / 300 / 600 ms after a zap  (PLY-RST-02)"
  note "The window between play's helper call and its reply. The stash is written"
  note "BEFORE the loadfile with the new identity and rewritten AFTER with the"
  note "entry id, so the stash is the truth in either outcome. Four offsets"
  note "because the failure this looks for is an ordering one."
  start_harness || return 1
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
  start_harness || return 1
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
  start_harness || return 1
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
  start_harness || return 1
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
  start_harness || return 1
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
  start_harness || return 1
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

# ------------------------------------------- the cold interleave, in a box
#
# PLY-H17 and PLY-H18 both turn on an ORDERING inside a cold start: a channel
# change has to reach the player between the spawn and `player start`'s own
# apply_channel. Wave two measured that window on the real thing - roughly
# twenty milliseconds, hit 10 times in 20 cold bursts - which is a coin flip,
# and a coin flip cannot be shown failing on another tree on demand.
#
# So the ordering is decided by a gate instead of by luck, at a point that
# already exists in the helper: `probe_client` will not return until mpv
# answers `mpv-version`, while `cmd_play` demands no handshake at all. The
# stub mpv (scripts/qa-stub-mpv.py) withholds the reply on the FIRST client
# connection while a gate file exists, so the start is parked exactly where
# the field race puts it, the zap lands, and then the start is released. 1/1.
#
# NO DISPLAY AND NO SHELL. The stub opens no window, quickshell is never
# started, and everything lives under $COLD. This is the only half of these
# two scenarios that can be run by a lane which does not hold the display -
# and it is the half CLAUDE.md rule 11 needs, because it is the half that can
# be pointed at another tree.
cold_reset() {
  rm -rf "$COLD"
  mkdir -p "$COLD/bin" "$COLD/runtime/omarchy-iptv" "$COLD/cache"
  chmod 700 "$COLD/runtime" "$COLD/runtime/omarchy-iptv"
  cp -f "$STUB" "$COLD/bin/mpv"
  chmod +x "$COLD/bin/mpv"
  python3 "$HELPER" playlist --url "$FIX/qa-player.m3u" --cache-dir "$COLD/cache" >/dev/null 2>&1
}

# cold_interleave <start-id> <zap-id>
# Leaves in $COLD: start.json, play.json, status.json, stub.log, and the three
# properties read back off the player afterwards.
cold_interleave() {
  local start_id=$1 zap_id=$2 i
  cold_reset
  : >"$COLD/gate"
  export PATH="$COLD/bin:$PATH"
  export STUB_LOG="$COLD/stub.log"
  export STUB_GATE="$COLD/gate"
  export STUB_LIFE=45

  timeout 45 python3 "$HELPER" player start --socket "$COLD_SOCK" \
    --cache-dir "$COLD/cache" --id "$start_id" --seq 1 --scope g:QA \
    >"$COLD/start.json" 2>"$COLD/start.err" &
  local startpid=$!
  for ((i = 0; i < 400; i++)); do [[ -S $COLD_SOCK ]] && break; sleep 0.05; done
  # ... and parked at the gate: its first request is logged before the stub
  # withholds the reply, so this is the instant the field race happens in.
  for ((i = 0; i < 400; i++)); do grep -q '^REQ' "$COLD/stub.log" 2>/dev/null && break; sleep 0.05; done

  STUB_GATE= timeout 20 python3 "$HELPER" play --socket "$COLD_SOCK" \
    --cache-dir "$COLD/cache" --id "$zap_id" --scope g:QA --since 3000 \
    >"$COLD/play.json" 2>"$COLD/play.err"
  rm -f "$COLD/gate"
  wait "$startpid"

  cold_prop 'user-data/omarchy-iptv' >"$COLD/stash.json"
  cold_prop 'force-media-title'      >"$COLD/title.json"
  cold_prop 'playlist-count'         >"$COLD/loads.json"
  timeout 20 python3 "$HELPER" status --socket "$COLD_SOCK" >"$COLD/status.json" 2>/dev/null
  printf '{"command":["quit"],"request_id":99}\n' | socat -t2 - "UNIX-CONNECT:$COLD_SOCK" >/dev/null 2>&1
  unset STUB_LOG STUB_GATE STUB_LIFE
  return 0
}

cold_prop() {   # read one property straight off the player
  printf '{"command":["get_property","%s"],"request_id":90}\n' "$1" \
    | socat -t2 - "UNIX-CONNECT:$COLD_SOCK" 2>/dev/null | head -1
}
# A field out of one of those files, through the sentinels: a missing file and
# a helper that printed nothing are different answers and neither is "".
cold_field() {   # cold_field <file> <python expr over d>
  python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("NOFILE"); raise SystemExit(0)
try:
    v = eval(sys.argv[2])
except Exception:
    v = None
print(json.dumps(v) if isinstance(v, bool) else ("NOFIELD" if v is None else v))' "$1" "$2" 2>/dev/null \
    || printf '%s\n' "$QA_NO_FILE"
}
cold_guard() {
  # AF_UNIX is 108 bytes and the bind is the whole scenario. Say so rather
  # than reporting "the player did not open its socket".
  if (( ${#COLD_SOCK} > 100 )); then
    bad "SETUP FAILED: $COLD_SOCK is ${#COLD_SOCK} bytes, past the AF_UNIX limit; set OMARCHY_IPTV_HARNESS_DIR shorter"
    return 1
  fi
  command -v socat >/dev/null || { bad "SETUP FAILED: socat is not installed"; return 1; }
  [[ -f $STUB ]] || { bad "SETUP FAILED: $STUB is missing"; return 1; }
  return 0
}

# --------------------------------------------------------------- PLY-H17

h17() {
  checks=0    # the floor below is this scenario's own, not the run's
  head1 "PLY-H17  a cold start that is no longer the newest intent stands down  (PLY-LIFE-16)"
  note "D-PLY-11's cause, measured by wave two: 10 user-visible divergences in 20"
  note "cold concurrent bursts, 0 in 10 warm and 0 in 6 cold-serial. In every one"
  note "a channel change reached the socket the instant mpv bound it while the"
  note "single player start was still inside its handshake, and the start then"
  note "applied ITS channel over the top. The fix: a player this helper just"
  note "SPAWNED was born idle with playlist-count 0 and no user-data node of"
  note "ours, so a channel on it now came from a client that connected after the"
  note "spawn - a strictly later intent - and the start stands down."
  note "NO DISPLAY: stub mpv, no shell, no window. Deterministic, 1/1."
  cold_guard || return 1
  step "spawn a cold start, hold it at its handshake, land a channel change, release it" \
    cold_interleave t:qa.plain t:qa.live
  expect "the start completes ok, having left the newer channel playing"
  (( APPLY )) || { note "dry run: the assertions below execute with --apply"; return 0; }

  # Positive controls first. Without them every assertion below is satisfied
  # by a run in which nothing happened at all.
  is "PLY-H17 the cold start completed (positive control)" \
     "$(cold_field "$COLD/start.json" "d['ok']")" "true"
  is "PLY-H17 it really did spawn the player, rather than adopt one" \
     "$(cold_field "$COLD/start.json" "d['spawned']")" "true"
  is "PLY-H17 the channel change landed while it was parked (positive control)" \
     "$(cold_field "$COLD/play.json" "d['ok']")" "true"
  is "PLY-H17 the start carried the FIRST intent, which is the losing one" \
     "$(cold_field "$COLD/start.json" "d['id']")" "t:qa.plain"

  # The three that discriminate. Every one of them is produced by BOTH trees
  # and read differently: measured here at HEAD and at a939fd7, 1/1 each.
  is "PLY-H17 the player took exactly ONE load, not two (a939fd7: 2)" \
     "$(cold_field "$COLD/loads.json" "d['data']")" "1"
  is "PLY-H17 the channel left playing is the NEWER intent (a939fd7: t:qa.plain)" \
     "$(cold_field "$COLD/stash.json" "d['data']['id']")" "t:qa.live"
  is "PLY-H17 and the title the user reads names it too (a939fd7: QA Plain No Headers)" \
     "$(cold_field "$COLD/title.json" "d['data']")" "QA Live Stream"

  # Forward regression guards, NOT the evidence: these fields exist only on a
  # tree that already has the fix, so they can never tell two trees apart.
  # Labelled, the way CL10 asks the journal line to be.
  is "PLY-H17 (forward guard only) the reply says it did not apply its channel" \
     "$(cold_field "$COLD/start.json" "d['applied']")" "false"
  is "PLY-H17 (forward guard only) and names what it left playing, so the shell can re-apply" \
     "$(cold_field "$COLD/start.json" "d['playing']['id']")" "t:qa.live"
  ck "PLY-H17 (forward guard only) the journal line names the stand-down" \
     'grep -q "newer channel change reached the player first" "$COLD/start.err"'
  ck "PLY-H17 no URL reached the reply or the journal line" \
     '! grep -qE "://" "$COLD/start.json" "$COLD/start.err" "$COLD/play.json"'
  floor "PLY-H17" 11
}

# --------------------------------------------------------------- PLY-H18

h18() {
  checks=0    # the floor below is this scenario's own, not the run's
  head1 "PLY-H18  a divergence is visible to the health tick, and the label converges  (CL6)"
  note "Ruling CL6: the invariant is that the interface's label and the player's"
  note "channel agree WITHIN ONE HEALTH TICK, not that the last of several"
  note "simultaneous intents wins. Wave two's divergences were all still there"
  note "at t+20 s and t+40 s, past two ticks, because nothing ever looked: the"
  note "health tick had no reading of the player's own channel to compare."
  note "Phase A below is the reading, and runs with NO DISPLAY. Phase B is the"
  note "convergence itself and needs the harness: run it with --with-display"
  note "from the lane that holds the display."
  cold_guard || return 1
  head1 "PLY-H18 phase A  the health tick's input (no display)"
  step "make the same divergence PLY-H17 makes, and ask the helper what is playing" \
    cold_interleave t:qa.plain t:qa.live
  expect "status carries the player's own now-playing record, naming t:qa.live"
  if (( APPLY )); then
    is "PLY-H18 status answered at all (positive control)" \
       "$(cold_field "$COLD/status.json" "d['ok']")" "true"
    is "PLY-H18 and the player really is running (positive control)" \
       "$(cold_field "$COLD/status.json" "d['running']")" "true"
    # The discriminator. On a939fd7 `status` carries no such field at all, so
    # this reads NOFIELD against a player that is demonstrably on t:qa.live -
    # which is the whole reason the divergence was silent.
    is "PLY-H18 status carries the player's own record (a939fd7: NOFIELD)" \
       "$(cold_field "$COLD/status.json" "d['stash']['id']")" "t:qa.live"
    is "PLY-H18 and it agrees with what the player itself reports" \
       "$(cold_field "$COLD/status.json" "d['stash']['id']")" \
       "$(cold_field "$COLD/stash.json" "d['data']['id']")"
    is "PLY-H18 the record names which side wrote it, so the two can be compared" \
       "$(cold_field "$COLD/status.json" "d['stash']['verb']")" "play"
    ck "PLY-H18 and carries a real intent number, not the hardcoded 0" \
       'qa_value "$(cold_field "$COLD/status.json" "d[\"stash\"][\"seq\"]")" && \
        [[ "$(cold_field "$COLD/status.json" "d[\"stash\"][\"seq\"]")" != "0" ]]'
    ck "PLY-H18 the status reply carries no URL, only a host" \
       '! grep -qE "://" "$COLD/status.json"'
  else
    note "dry run: phase A's assertions execute with --apply"
  fi

  head1 "PLY-H18 phase B  the convergence itself (NEEDS THE DISPLAY)"
  note "Requires --with-display. Only the lane holding the display may run it."
  if (( WITH_DISPLAY == 0 )); then
    note "skipped: phase B not requested. Phase A above is the part a lane"
    note "without the display can run, and it is the part that fails on a939fd7."
    (( APPLY )) && floor "PLY-H18 phase A" 7
    return 0
  fi
  start_harness || return 1
  sh_step "play a channel and wait for the observer to attach" \
    "'$RUN' ipc play t:qa.live >/dev/null; sleep 5; '$RUN' ipc state | jq -r '.service.socketAttached'"
  expect "true"
  sh_step "move the PLAYER behind the shell's back, so the label and the player disagree" \
    "printf '%s\\n' '{\"command\":[\"loadfile\",\"http://127.0.0.1:$HPORT/test.ts\",\"replace\"],\"request_id\":1}' \\
       | socat -t2 - 'UNIX-CONNECT:$SOCK' >/dev/null; \\
     printf '%s\\n' '{\"command\":[\"set_property\",\"user-data/omarchy-iptv\",{\"schema\":1,\"playing\":true,\"id\":\"t:qa.plain\",\"name\":\"QA Plain No Headers\",\"seq\":0,\"verb\":\"play\"}],\"request_id\":2}' \\
       | socat -t2 - 'UNIX-CONNECT:$SOCK' >/dev/null; echo diverged"
  expect "the shell still says t:qa.live; the player says t:qa.plain"
  sh_step "wait ONE health tick (10 s timer, 2 s probe deadline) and look again" "sleep 14"
  if (( APPLY )); then
    is "PLY-H18 the shell never relabelled itself from the player (CL5)" \
       "$(svc "d['nowPlaying']['id'] if d.get('nowPlaying') else None")" "t:qa.live"
    is "PLY-H18 the player is back on the channel the user chose (CL6)" \
       "$(mpvq '{"command":["get_property","user-data/omarchy-iptv"],"request_id":7}' \
          | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["id"])' 2>/dev/null)" \
       "t:qa.live"
    is "PLY-H18 and the interface is not idle after the repair" "$(svc "d['playing']")" "true"
    floor "PLY-H18 A+B" 10
  fi
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
PLY-H17  a cold start no longer the newest intent stands   PLY-LIFE-16  needs: socat. NO DISPLAY: stub mpv, no shell
         down                                                           asserts 11 checks; fails against a939fd7
PLY-H18  a divergence is visible to the health tick and    PLY-LIFE-17  phase A needs: socat, NO DISPLAY (7 checks)
         the label converges within one tick (CL6)                      phase B needs the harness: --with-display

Rule 11 (CLAUDE.md 11, and the PO's double force in ARCH-P section 12): every
scenario above must be shown to FAIL against pre-M2-02 code before it counts
as evidence. Use `baseline <PLY-Hnn> <ref>`; it exports <ref> and re-runs the
same steps with OMARCHY_IPTV_PLUGIN_ROOT pointed at the export. Record BOTH
counts in docs/QA-RESULTS.md.
EOF
}

cmd_baseline() {
  local id=${1:-} ref=${2:-} exp
  [[ -n $id ]]  || die "baseline needs a scenario id and a git ref (see: list)"
  [[ -n $ref ]] || die "baseline needs a git ref, e.g. baseline PLY-H13 396a69a"
  exp="$SCRATCH/baseline-$ref"
  refuse_real_dirs
  head1 "rule 11 baseline: $id against $ref"
  step "export the tree" bash -c "rm -rf '$exp' && mkdir -p '$exp' && git -C '$ROOT' archive '$ref' | tar -x -C '$exp'"
  note "now re-run with OMARCHY_IPTV_PLUGIN_ROOT='$exp'; the checks this scenario"
  note "owns must FAIL there. A scenario that passes on both trees is a"
  note "regression guard, not evidence for this milestone - label it as one."
  # F5. `${APPLY:+--apply}` expands whenever APPLY is SET and non-empty, and
  # APPLY is always 0 or 1 - so the dry run, whose entire contract is "without
  # --apply nothing runs", printed a baseline command carrying --apply for
  # anyone to copy and paste at their live session.
  local flag=()
  (( APPLY )) && flag=(--apply)
  (( WITH_DISPLAY )) && flag+=(--with-display)
  step "run" env OMARCHY_IPTV_PLUGIN_ROOT="$exp" "$0" run "$id" "${flag[@]}"
}

main() {
  local cmd=${1:-}; shift || true
  local args=()
  while (($# > 0)); do
    case $1 in
      --apply) APPLY=1 ;;
      --with-display) WITH_DISPLAY=1 ;;
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
    stop)          cmd_stop ;;
    # F6: under `set -u` an empty array aborted with bash's own
    # "args[0]: unbound variable" instead of reaching this script's die().
    baseline)      cmd_baseline "${args[0]:-}" "${args[1]:-}" ;;
    print|run)
      refuse_real_dirs
      case ${args[0]:-all} in
        PLY-H11|H11) h11 ;;
        PLY-H12|H12) h12 ;;
        PLY-H13|H13) h13 ;;
        PLY-H14|H14) h14 ;;
        PLY-H15|H15) h15 ;;
        PLY-H16|H16) h16 ;;
        PLY-H17|H17) h17 ;;
        PLY-H18|H18) h18 ;;
        all)         h11; h12; h13; h14; h15; h16; h17; h18 ;;
        # The two scenarios a lane WITHOUT the display can run end to end,
        # and the two that can be pointed at another tree and seen failing.
        cold)        h17; h18 ;;
        *) die "unknown scenario: ${args[0]} (try: list)" ;;
      esac
      # B1. `main` used to end on `((APPLY)) || printf ...`, which is TRUE
      # when APPLY=1 - so `run all --apply` exited 0 no matter what happened,
      # including six scenarios whose harness never started. The six EXPECT
      # blocks still have no machine-checkable verdict; converting them is
      # next round (ruling CL7). What is fixed here is that the suite can
      # report a failure at all.
      if (( APPLY )); then
        printf '\n===== %s pass, %s fail =====\n' "$pass" "$fail"
        if (( fail == 0 )) && (( pass == 0 )); then
          printf 'NOTE: the PLY-H11..H16 bodies still assert nothing; only their\n'
          printf 'setup is checked. Their EXPECT lines are read by a human (CL7).\n'
        fi
        (( fail == 0 )) || exit 1
      else
        printf '\n(dry run: nothing above was executed. Add --apply to run it.)\n'
      fi
      ;;
    ""|-h|--help) usage ;;
    *) die "unknown command: $cmd (try: list)" ;;
  esac
}

main "$@"
