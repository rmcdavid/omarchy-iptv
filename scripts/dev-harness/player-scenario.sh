#!/bin/bash
# scripts/dev-harness/player-scenario.sh -- scripted verification of the
# DETACHED player (M2-02, lane PB) through the harness IPC. Started by
# `run.sh player-scenario`. Opens a real mpv window on the current Wayland
# session for ~60 s and reaps everything it starts.
#
# Scenarios (docs/ARCHITECTURE-PLAYER.md section 10, harness half):
#   P1  cold start        one player, one window, class omarchy-iptv, title = channel
#   P2  S-03 argv         no URL, no credential, no token, no header value and no
#                         channel name on mpv's command line -- TC-PLAY-08 inverted;
#                         and D-PLY-27's `--gpu-sw=yes` in the BASE section, once
#                         (F-HARNESS-46)
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
#                         new player, ONE relaunch, and never goes idle. The
#                         one-relaunch half is asserted on the INTENT COUNTER
#                         (ruling CL10), which reads 1 here and must read 2 on
#                         `396a69a`; the journal line is printed, not asserted.
#   P12 socket respawn    D-PLY-1 trigger B: the same after a socket unlink that
#                         makes `player start` ladder the old player down
#   P13 startup race      D-PLY-4: a play issued from the earliest instant the
#                         successor's IPC accepts one keeps its session record
#   P14 marked once       D-PLY-3: PO-3's record is retired when it is consumed,
#                         so the next start does not raise the same mark again.
#                         Since D-PLY-33 (owner, 2026-10-28) the reattach marks
#                         nothing at all -- nobody saw an end-file -- so the
#                         check is that the record is retired and NO mark lands
#   P9  reap              the harness teardown still finds a detached grandchild
#
# Restart on adoption (owner, 2026-10-31 and 2026-11-01; lane RB): a player
# ANOTHER build of this plugin launched is replaced, never fed. The older
# players are started by the real tags' own helpers (git archive of v0.15.0
# and v0.16.0, qa_helper_parts); the replacement is read off the kernel.
#   L1  v0.15.0's player  this tree's shell starts over it: P0 (the canary
#                         --osd-duration=4321 on its argv) gone, never two
#                         token-holders at a 50 ms sample, P1's argv byte for
#                         byte what this tree's OWN builder composes, core 0 0,
#                         the options file gone, the same channel, time-pos
#                         advancing, one restart line, no player card, the
#                         coredump journal +0
#   L1b paused, volume 37 the replacement comes back paused at 37 (answer 3)
#   L2  v0.16.0's player  the same; that it is another build's comes from the
#                         two trees' own builders, never from launch_verdict
#   L3  counter-case      this tree's P1 across a shell stop, its orphan check
#                         run out, and a start: same pid, same stat field 22,
#                         time-pos continuous, no restart or replaced line, the
#                         probe reads `current`; with M8's observation (P4
#                         gains the no-restart-line check too)
#   L4  old QML           v0.16.0's Service and helper play A; this tree's
#                         helper and manifest replace the export's under the
#                         running shell (the update's fast-forward; the host
#                         keeps a keepLoaded service across rescanPlugins);
#                         a zap to B: P0 gone, P1 this tree's, B playing, the
#                         same shell process, no card, one replaced line
#   L5  never fed         a logging server for B: B's first request follows
#                         P0's first absent sample, none with B's header before
#   L7  late list         D-SINK-71: a v0.15.0 player the probe must migrate
#                         (its load-auto-profiles read auto, then false), the
#                         channel list withheld past the 15 s hold: P0 still
#                         alone on the socket past the hold, and replaced only
#                         after `ipc refresh` lands the list -- P1 this tree's,
#                         the same channel, one restart line, no card, the
#                         coredump journal +0
#   L8  late, not migrated D-SINK-71's counter-case: a v0.16.0 player, every
#                         pin on its own argv, the list withheld the same way:
#                         P0 alone on the socket at every sample from the
#                         refresh until 8 s after the list landed, no restart
#                         line, no card, the coredump journal +0
#
# L6 is the baseline: `--baseline 202a7bc` (v0.16.0's code) must red L1, L1b,
# L2 and L4/L5 (P0 survives, is adopted and fed, keeps the canary) and L3's
# probe check (that tree's probe has no `launch`, NOFIELD), and leave the rest
# green. `--baseline 6b5ba6c` (restart on adoption, before D-SINK-71) must red
# L7's replacement checks: the expired hold deferred P0, so it is still alive
# after the list lands and no restart line is written; its premises hold there.
# L8 is green on `--baseline 6b5ba6c` (it defers P0 too), and red on a tree
# whose hold's end late-delivers to every safe player (rc-sk71's run of
# lane-sk71's mutant M1).
#
# Evidence rule (CLAUDE.md 10): run with --baseline <git-ref> to export that
# tree and run the same checks against it. Against the last pre-M2-02 commit
# P2, P3, P4, P5, P6 and P8 MUST fail; P10 is evidence against the first
# detached-player commit, which is the code that shipped that bug; P11, P12,
# P13 and P14 MUST fail against 396a69a, the tree the M2-02 QA pass filed
# D-PLY-1, D-PLY-3 and D-PLY-4 against. The rest are regression guards that
# must pass on both.
#
# One check SKIPs on a baseline, and only there: P2's `--gpu-sw=yes` check
# (F-HARNESS-46) against a ref that predates D-PLY-27, which no tree through
# 0.15.0 carries. It prints `SKIP <label>: <reason>` and is counted in the
# summary; see gpu_sw_skip_reason for the one condition. Without --baseline it
# always asserts.
#
#   ./scripts/dev-harness/player-scenario.sh
#   ./scripts/dev-harness/player-scenario.sh --baseline <pre-M2-02 ref>
#   ./scripts/dev-harness/player-scenario.sh --race-trials 30   (D-PLY-4's measurement)
#
# Output: one PASS/FAIL line per check and a summary. No URL is ever printed.
set -uo pipefail
# ---- refusals above EVERY external command (F-M3-18 (b), the clip- and
# logo-scenario shape): `command -v`, `[[ ]]` and `echo` are builtins, so an
# empty PATH reaches the SKIP line -- exit 77, what the gate reads as "this
# machine cannot run it" -- and nothing else. HERE is resolved from
# BASH_SOURCE with builtins for the same reason: `dirname "$0"` used to run
# first and an empty PATH died on `dirname: command not found` instead.
for tool in python3 ffmpeg mpv pgrep mktemp; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP player-scenario: $tool is not on PATH" >&2; exit 77; }
done

HERE=${BASH_SOURCE[0]%/*}
[[ $HERE == "${BASH_SOURCE[0]}" ]] && HERE=.
HERE=$(cd "$HERE" && pwd)
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
# Checks this run decided NOT to assert (`skp`, F-HARNESS-46). Neither an
# outcome nor an assertion: the floor counts them beside `checks`, so a run
# that skips is held to the same number as one that asserts.
skipped=0

# The predicates this file asserts on, so that they can be tested without a
# display: scripts/qa-lib-test.sh drives every one of them both ways.
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
# F-HARNESS-20: this driver's own processes (its helper runs, probes, mpv)
# get the harness's HOME as well, not only what run.sh starts. Exports only.
qa_harness_home "$SCRATCH" || exit 2

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
# skp <label> <reason>: printed in the shape every other SKIP here takes
# (`SKIP <what>: <why>`), so a reader of the transcript sees the reason on the
# line, and counted, so the summary says how many checks were not asserted.
skp() { printf 'SKIP %s: %s\n' "$1" "$2"; skipped=$((skipped + 1)); }

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
# F-HARNESS-46. D-PLY-27 put `--gpu-sw=yes` in the BASE section of the launch
# argv in both mirrors (MPV_GPU_SW: after the two cache directories, before
# D-SINK-13's layer 1 `--tls-verify=yes`), once, never re-asserted, never
# reserved. Where it sits IS the property: run.sh's harness_env appends a
# second `--gpu-sw=yes` to the USER's mpvArgs under a pixman cage
# (F-HARNESS-45), and the user's section comes after layer 1, so a check that
# counted the token anywhere would pass on a tree that lost the base one.
#
# So the argv is read as ITEMS. cmdline_of joins /proc/<pid>/cmdline with
# spaces, and a joined string cannot tell an item from a piece of one; this
# splits it on the NULs the kernel wrote (`mapfile -d ''`), with qa_cmdline's
# refusals: a pid that is not a number never reads /proc//cmdline, which the
# kernel resolves to /proc/cmdline, the KERNEL's command line.
#
# gpu_sw_base <pid> -> "layer1:<yes|no> base:<n>" where base counts the items
# that are exactly `--gpu-sw=yes` before the FIRST `--tls-verify=yes`, or
# NOARGV when the command line cannot be read. `layer1:yes` is the check's own
# positive control: without layer 1 there is no "before" to be in, and every
# copy, the lever's included, would count as base.
# gpu_sw_items <pid> -> the items that decide it, with their argv indexes, for
# the transcript: every `--gpu-sw*` / `--no-gpu-sw` spelling and every
# `--tls-verify*`, plus the user's `--ao=` the lever adds beside its copy.
argv_items() {
  local pid=${1-}
  ARGV=()
  [[ $pid =~ ^[0-9]+$ && -r /proc/$pid/cmdline ]] || return 1
  mapfile -d '' -t ARGV <"/proc/$pid/cmdline" 2>/dev/null || return 1
  (( ${#ARGV[@]} > 0 ))
}
gpu_sw_base() {
  local item layer1=no base=0
  argv_items "${1-}" || { echo NOARGV; return 0; }
  for item in "${ARGV[@]}"; do
    if [[ $item == --tls-verify=yes ]]; then layer1=yes; break; fi
    [[ $item == --gpu-sw=yes ]] && base=$((base + 1))
  done
  printf 'layer1:%s base:%d\n' "$layer1" "$base"
}
gpu_sw_items() {
  local i out=""
  argv_items "${1-}" || { echo NOARGV; return 0; }
  for ((i = 0; i < ${#ARGV[@]}; i++)); do
    case ${ARGV[i]} in
      --gpu-sw|--gpu-sw=*|--no-gpu-sw|--tls-verify|--tls-verify=*|--no-tls-verify|--ao=*) out="$out #$i ${ARGV[i]}" ;;
    esac
  done
  printf '%s of %d items\n' "${out# }" "${#ARGV[@]}"
}
# gpu_sw_skip_reason <baseline ref>: answers 0 and prints why when the check
# must SKIP, answers 1 and prints nothing when it must ASSERT. The only SKIP:
# --baseline names a ref that does NOT contain D-PLY-27's code commit AND whose
# manifest declares 0.15.0 or older. Never keyed on whether the tree under
# test defines MPV_GPU_SW -- a tree that LOST the constant would then skip
# instead of going red (rule 14) -- and never without --baseline.
# Why the version as well as the ancestry: `main` holds only release.py's
# export, each release commit's parent the previous release, so NO release
# tag contains any dev commit (measured: `merge-base --is-ancestor cc35557
# v0.15.0` is false, cc35557 being the dev commit 0.15.0 was exported from).
# On ancestry alone `--baseline v0.16.0`, which will carry the token, would
# skip. The version alone would not do either: dev keeps the last release's
# number until the cut, so a dev ref before D-PLY-27 and one after it both say
# 0.15.0, and only the ancestry tells them apart. Anything git or the manifest
# cannot answer (an unknown ref, a clone without 1044f7b, an unreadable
# version) ASSERTS.
DPLY27_CODE=1044f7b
gpu_sw_skip_reason() {
  local ref=${1-} anc ver
  [[ -n $ref ]] || return 1
  git -C "$ROOT" merge-base --is-ancestor "$DPLY27_CODE" "$ref" >/dev/null 2>&1
  anc=$?
  (( anc == 1 )) || return 1
  ver=$(git -C "$ROOT" show "$ref:manifest.json" 2>/dev/null | python3 -I -c '
import json, sys
try:
    v = json.load(sys.stdin)["version"]
    t = tuple(int(x) for x in v.split("."))
except Exception:
    raise SystemExit(1)
if len(t) != 3 or t > (0, 15, 0):
    raise SystemExit(1)
print(v)') || return 1
  printf '%s (manifest %s) does not contain D-PLY-27 (%s): no tree through 0.15.0 launches mpv with --gpu-sw=yes\n' \
    "$ref" "$ver" "$DPLY27_CODE"
}
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
# The INTENT COUNTER, from both sides of the lock (ruling CL10). The shell
# hands every player verb a sequence number and the helper writes the one it
# acted on into the lock record, so one logical relaunch moves both by exactly
# one. Wave two measured that live on the fixed tree three times over
# (docs/QA-RESULTS.md section D4) and both readings exist unchanged on
# `396a69a`, which is what makes them able to tell the trees apart at all.
# `playSeq` is the harness fake's defensive read (null on a tree that has no
# such property), so this never throws and never invents a number.
player_seq() { svc "d['playSeq']"; }
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

# ---- restart on adoption (owner, 2026-10-31 and 2026-11-01; lane RB): the
# L segments' instruments. A player ANOTHER build of this plugin launched is
# replaced, never fed, and the evidence is the KERNEL's: which processes hold
# the socket token at every 50 ms sample, what /proc/<pid>/cmdline and
# /proc/<pid>/limits say, what the player answers over its own socket, and,
# for L5, what a logging server saw and when. The older players are launched
# by the real tags' own helpers (git archive of v0.15.0 and v0.16.0, checked
# whole with qa_helper_parts), never by a hand-made imitation of their argv.
#
# One python program, verbs below, run `-I -B` so it neither reads the
# caller's site nor writes a .pyc into any tree it loads a helper from. It
# prints words and numbers only: never an argv element, a string property, a
# path the player holds, or a request's header value (rule 5 holds for a
# scenario's own output too).
#   tokens <sock>                      pids whose argv holds --input-ipc-server=<sock> as an item
#   alive <sock> <pid>                 alive | gone (a zombie's empty cmdline is gone)
#   sample <sock> <file> <secs>        every 50 ms, "<monotonic> <pids>" into <file> (0600)
#                                      until <file>.stop exists or <secs> pass
#   verdict <file> <p0> <p1>           samples:<n> max:<k> p0:yes|no p1:yes|no end:END|DEADLINE
#                                      p0all:yes|no (P0 held the socket in EVERY sample)
#   p0times <file> <p0>                "<last monotonic P0 was seen> <first monotonic it was not>"
#   build <root> <sock> <pid>          plain | include | neither | NOARGV | NOBUILDER: whether
#                                      <pid>'s argv equals what <root>'s OWN mpv_launch_argv
#                                      composes, byte for byte, in either form -- the BUILDER,
#                                      never launch_verdict, the reading under test
#   differ <rootA> <rootB> <sock>      differ | same | NOBUILDER: two trees' own builders
#   get <sock> <prop>                  a number (%g), true/false, null, STR (a string, never
#                                      printed), ERR or NOREPLY
#   set <sock> <prop> <json>           ok | ERR | NOREPLY
#   stashid <sock>                     the stash's channel id, or NOSTASH
#   starttime <pid>                    /proc/<pid>/stat field 22, or NOSTAT
#   core <pid>                         "<soft> <hard>" of Max core file size, or NOLIMITS
#   orphans <sock>                     pids of `player orphan-check` helpers on <sock>
#   helpers <sock>                     pids of every `player ...` helper verb on <sock>
#   serve <port> <dir> <log> <ua>      L5's server: one "<monotonic> GET <path> ua:yes|no" a request
#   m8 <sock> <shellpid> <file> <secs> every 50 ms: "<monotonic> <shell up 0|1> <orphan-check
#                                      pids or -> <player pids or ->" (L3's M8 reading)
#   m8verdict <file> <t0>              shell-exit / orphan-seen / orphan-gone, seconds after t0
#   now                                CLOCK_MONOTONIC, the clock every stamp here is on
#   notifier <pid> <dir>               stub | other | none | NOENV: which omarchy-notification-send
#                                      <pid>'s own PATH resolves first (/proc/<pid>/environ; the
#                                      shell is ours and dumpable) -- the "no card" checks' control
L_PY=$(cat <<'PY'
import json, os, socket, sys, time

def tok(sock):
    return os.fsencode("--input-ipc-server=" + sock)

def items(pid):
    try:
        with open("/proc/%d/cmdline" % int(pid), "rb") as handle:
            return [part for part in handle.read().split(b"\0") if part]
    except (OSError, ValueError):
        return []

def scan(token, needle=None):
    me = os.getpid()
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == me:
            continue
        argv = items(entry)
        if needle is None and token in argv:
            found.append(int(entry))
        elif needle is not None and needle in argv and token in argv:
            found.append(int(entry))
    return sorted(found)

def load_helper(root, name):
    import importlib.machinery, importlib.util
    path = os.path.join(root, "bin", "omarchy-iptv")
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

def composed(root, name, sock):
    helper = load_helper(root, name)
    return [("plain", [os.fsencode(e) for e in helper.mpv_launch_argv(sock, [])]),
            ("include", [os.fsencode(e) for e in helper.mpv_launch_argv(sock, ["--osd-level=1"])])]

def show(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "%g" % value
    if value is None:
        return "null"
    return "STR"

def ipc(sock, command):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(2.0)
    try:
        conn.connect(sock)
        conn.sendall((json.dumps({"command": command, "request_id": 4242}) + "\n").encode())
        buf = b""
        end = time.monotonic() + 2.0
        while time.monotonic() < end:
            chunk = conn.recv(65536)
            if not chunk:
                return None
            buf += chunk
            lines = buf.split(b"\n")
            buf = lines.pop()
            for line in lines:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict) and msg.get("request_id") == 4242:
                    return msg
    except OSError:
        return None
    finally:
        conn.close()
    return None

def main(verb, args):
    if verb == "tokens":
        print(" ".join(str(p) for p in scan(tok(args[0]))))
    elif verb == "alive":
        print("alive" if tok(args[0]) in items(args[1]) else "gone")
    elif verb == "orphans":
        print(" ".join(str(p) for p in scan(os.fsencode(args[0]), b"orphan-check")))
    elif verb == "helpers":
        print(" ".join(str(p) for p in scan(os.fsencode(args[0]), b"player")))
    elif verb == "sample":
        token, path, end = tok(args[0]), args[1], time.monotonic() + float(args[2])
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            while time.monotonic() < end and not os.path.exists(path + ".stop"):
                pids = scan(token)
                os.write(fd, ("%.3f %s\n" % (time.monotonic(), ",".join(str(p) for p in pids))).encode())
                time.sleep(0.05)
            os.write(fd, b"END\n" if os.path.exists(path + ".stop") else b"DEADLINE\n")
        finally:
            os.close(fd)
    elif verb == "m8":
        sock, shell, path, end = os.fsencode(args[0]), args[1], args[2], time.monotonic() + float(args[3])
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            while time.monotonic() < end and not os.path.exists(path + ".stop"):
                up = 1 if items(shell) else 0
                orphans = scan(sock, b"orphan-check")
                players = scan(tok(args[0]))
                os.write(fd, ("%.3f %d %s %s\n" % (time.monotonic(), up, ",".join(map(str, orphans)) or "-", ",".join(map(str, players)) or "-")).encode())
                time.sleep(0.05)
        finally:
            os.close(fd)
    elif verb == "m8verdict":
        t0 = float(args[1])
        exit_at = first_orphan = orphan_gone = None
        seen = False
        for line in open(args[0]).read().splitlines():
            stamp, up, orphans, _ = line.split(" ")
            stamp = float(stamp)
            if exit_at is None and up == "0":
                exit_at = stamp
            if orphans != "-":
                seen = True
                if first_orphan is None:
                    first_orphan = stamp
            elif seen and orphan_gone is None:
                orphan_gone = stamp
        rel = lambda t: "NONE" if t is None else "%.2f" % (t - t0)
        print("shell-exit:%s orphan-seen:%s orphan-gone:%s" % (rel(exit_at), rel(first_orphan), rel(orphan_gone)))
    elif verb == "now":
        print("%.3f" % time.monotonic())
    elif verb == "notifier":
        try:
            env = open("/proc/%d/environ" % int(args[0]), "rb").read().split(b"\0")
        except (OSError, ValueError):
            print("NOENV")
            return
        path = next((e[5:].decode("utf-8", "replace") for e in env if e.startswith(b"PATH=")), "")
        for folder in path.split(":"):
            cand = os.path.join(folder, "omarchy-notification-send")
            if folder and os.path.isfile(cand) and os.access(cand, os.X_OK):
                print("stub" if os.path.realpath(folder) == os.path.realpath(args[1]) else "other")
                return
        print("none")
    elif verb in ("verdict", "p0times"):
        p0 = int(args[1] or 0) if args[1].isdigit() else 0
        p1 = int(args[2]) if verb == "verdict" and args[2].isdigit() else 0
        count = most = seen0 = seen1 = 0
        last0 = gone0 = None
        end = "none"
        try:
            lines = open(args[0]).read().splitlines()
        except OSError:
            lines = []
        for line in lines:
            if line in ("END", "DEADLINE"):
                end = line
                continue
            stamp, _, pids = line.partition(" ")
            held = [int(x) for x in pids.split(",") if x.isdigit()]
            count += 1
            most = max(most, len(held))
            if p0 and p0 in held:
                seen0 += 1
                last0, gone0 = float(stamp), None
            elif last0 is not None and gone0 is None:
                gone0 = float(stamp)
            if p1 and p1 in held:
                seen1 += 1
        if verb == "verdict":
            print("samples:%d max:%d p0:%s p1:%s end:%s p0all:%s" % (count, most, "yes" if seen0 else "no", "yes" if seen1 else "no", end,
                                                                     "yes" if count and seen0 == count else "no"))
        else:
            print("%s %s" % ("%.3f" % last0 if last0 is not None else "NONE", "%.3f" % gone0 if gone0 is not None else "NONE"))
    elif verb == "build":
        argv = items(args[2])
        if not argv:
            print("NOARGV")
            return
        try:
            forms = composed(args[0], "omarchy_iptv_rb_build", args[1])
        except BaseException:
            print("NOBUILDER")
            return
        print(next((form for form, want in forms if want == argv), "neither"))
    elif verb == "differ":
        try:
            a = composed(args[0], "omarchy_iptv_rb_a", args[2])
            b = composed(args[1], "omarchy_iptv_rb_b", args[2])
        except BaseException:
            print("NOBUILDER")
            return
        print("same" if any(x[1] == y[1] for x, y in zip(a, b)) else "differ")
    elif verb == "get":
        msg = ipc(args[0], ["get_property", args[1]])
        print("NOREPLY" if msg is None else (show(msg.get("data")) if msg.get("error") == "success" else "ERR"))
    elif verb == "set":
        msg = ipc(args[0], ["set_property", args[1], json.loads(args[2])])
        print("NOREPLY" if msg is None else ("ok" if msg.get("error") == "success" else "ERR"))
    elif verb == "stashid":
        msg = ipc(args[0], ["get_property", "user-data/omarchy-iptv"])
        data = msg.get("data") if msg and msg.get("error") == "success" else None
        ident = data.get("id") if isinstance(data, dict) else None
        ok = isinstance(ident, str) and ident and all(c.isalnum() or c in ":._-" for c in ident) and len(ident) <= 64
        print(ident if ok else "NOSTASH")
    elif verb == "starttime":
        try:
            fields = open("/proc/%d/stat" % int(args[0])).read().rsplit(")", 1)[1].split()
            print(fields[19])
        except (OSError, ValueError, IndexError):
            print("NOSTAT")
    elif verb == "core":
        try:
            for line in open("/proc/%d/limits" % int(args[0])):
                if line.startswith("Max core file size"):
                    print(" ".join(line.split()[4:6]))
                    return
        except (OSError, ValueError):
            pass
        print("NOLIMITS")
    elif verb == "serve":
        import http.server, socketserver
        port, root, log, agent = int(args[0]), args[1], args[2], args[3]
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **k):
                super().__init__(*a, directory=root, **k)
            def log_message(self, *a):
                pass
            def do_GET(self):
                has = "yes" if self.headers.get("User-Agent", "") == agent else "no"
                os.write(fd, ("%.3f GET %s ua:%s\n" % (time.monotonic(), self.path.split("?")[0], has)).encode())
                return super().do_GET()
        class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True
        Server(("127.0.0.1", port), Handler).serve_forever()

main(sys.argv[1], sys.argv[2:])
PY
)
l_py() { python3 -I -B -c "$L_PY" "$@"; }
# Model.OLDER_RESTART_LINE and the helper's PLAYER_REPLACED_LINE, fixed text
# (the interface frozen for lane RB): the shell's one journal line per
# automatic restart, and the helper's one per replaced player.
L_RESTART_TEXT='restarting a player another build of this plugin started'
L_REPLACED_TEXT='replaced a player another build of this plugin started'
# The inert canary L1 puts on v0.15.0's own command line (that release put the
# user's mpvArgs on the argv; D-SINK-47 moved them into a 0600 file in 0.16.0).
L_CANARY='--osd-duration=4321'
# The tokens every older player here is launched with, as run.sh's lever adds
# them to the shell's (F-HARNESS-45): a software context mpv's VO probe accepts
# under a pixman cage, and no sound on the user's own server.
L_LEVER=(--mpv-arg=--gpu-sw=yes --mpv-arg=--ao=null)
L5_PORT=8769
L5_UA="RaoNeverFedAgent/1.0"
L_NESTED=0
L_CACHE=""
SAMPLER_PID=""
L5_PID=""
L15_DIR=""
L16_DIR=""
L4_DIR=""
crash_count() { journalctl -o json MESSAGE_ID=fc2e22bc6ee647b6b90729ab34a250b1 2>/dev/null | wc -l | tr -d ' '; }
notify_cards() {   # player cards the scenario's notification stub logged (never "Bar setting ignored")
  qa_count $'\t(Stream failed|Could not start playback|Playback stopped|Audio output failed|Video output failed|mpv not found)\t' "$SCRATCH/notify.log"
}
# l_export <tag>: the tag's own tree, checked whole (the stub and every part
# it names), or nothing.
l_export() {
  local dir
  dir=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-rao-XXXXXX") || return 1
  if git -C "$ROOT" archive "$1" 2>/dev/null | tar -x -C "$dir" 2>/dev/null \
     && [[ -f $dir/manifest.json ]] && [[ -n $(qa_helper_parts "$dir") ]]; then
    printf '%s\n' "$dir"
    return 0
  fi
  rm -rf -- "$dir"
  return 1
}
# l_old_start <tree> <id> [more --mpv-arg tokens]: that tree's OWN helper runs
# `player start` on the harness socket with no shell up, the way the release
# that tree is would have; its reply goes to $LOG. The seq continues the
# lock's, so the next shell's starts are not superseded by it.
l_old_start() {
  local tree=$1 id=$2 seq; shift 2
  seq=$(lock_seq)
  [[ $seq =~ ^[0-9]+$ ]] && seq=$((seq + 1)) || seq=1
  env -u DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE timeout -k 2 60 python3 -I "$tree/bin/omarchy-iptv" player start \
    --socket "$SOCK" --cache-dir "$L_CACHE" --id "$id" --seq "$seq" "${L_LEVER[@]}" "$@" >>"$LOG" 2>&1
}
# l_wait_up <secs>: until the player on the socket reports a numeric time-pos.
l_wait_up() {
  local secs=$1 i v
  for ((i = 0; i < secs * 10; i++)); do
    v=$(l_py get "$SOCK" time-pos)
    [[ $v =~ ^[0-9.e+-]+$ ]] && return 0
    sleep 0.1
  done
  printf 'gave up after %ss waiting for a time-pos on the socket\n' "$secs" >&2
  return 1
}
# l_advances: two time-pos readings 2 s apart, the second larger.
l_advances() {
  local a b
  l_wait_up 20 || { echo "never-up"; return 0; }
  a=$(l_py get "$SOCK" time-pos); sleep 2; b=$(l_py get "$SOCK" time-pos)
  python3 -I -c 'import sys
try:
    print("advancing" if float(sys.argv[2]) > float(sys.argv[1]) else "stuck")
except ValueError:
    print("unreadable")' "$a" "$b"
}
# l_wait_replaced <p0> <secs>: until P0 is gone and exactly one other process
# holds the token; prints it. Bounded, and says when it gave up.
l_wait_replaced() {
  local p0=$1 secs=$2 i pids
  for ((i = 0; i < secs * 10; i++)); do
    pids=$(l_py tokens "$SOCK")
    if [[ -n $pids && $pids != *" "* && $pids != "$p0" && $(l_py alive "$SOCK" "$p0") == gone ]]; then
      printf '%s\n' "$pids"
      return 0
    fi
    sleep 0.1
  done
  printf 'gave up after %ss waiting for the older player %s to be replaced\n' "$secs" "${p0:-<none>}" >&2
  return 1
}
# l_wait_orphans <secs> [verb]: until no `player orphan-check` helper of this
# socket is left (the dying shell's, PO-2), so a player started next is never
# judged by a check from the previous shell; with `helpers`, until no player
# verb at all is left -- the shell's detached `player stop` writes the lock's
# seq after `ipc stop` has returned, and an older helper's start read before
# that write is superseded by it (seen on the first run). Prints the seconds.
l_wait_orphans() {
  local secs=$1 verb=${2:-orphans} i
  for ((i = 0; i < secs * 10; i++)); do
    [[ -z $(l_py "$verb" "$SOCK") ]] && { printf '%s\n' "$((i / 10)).$((i % 10))"; return 0; }
    sleep 0.1
  done
  printf 'gave up after %ss waiting for the %s of this socket to exit\n' "$secs" "$verb" >&2
  echo "NONE"
  return 1
}
sampler_start() {   # sampler_start <file> <secs>
  rm -f -- "$1" "$1.stop"
  l_py sample "$SOCK" "$1" "$2" >/dev/null 2>&1 &
  SAMPLER_PID=$!
}
sampler_stop() {
  [[ -n $SAMPLER_PID ]] || return 0
  : >"$1.stop"
  local i
  for ((i = 0; i < 50; i++)); do kill -0 "$SAMPLER_PID" 2>/dev/null || break; sleep 0.1; done
  kill -0 "$SAMPLER_PID" 2>/dev/null && kill -TERM "$SAMPLER_PID" 2>/dev/null
  wait "$SAMPLER_PID" 2>/dev/null
  SAMPLER_PID=""
}
# l_stop_all: no player, no shell, and no orphan check of the last shell left.
l_stop_all() {
  ipc stop >/dev/null
  until_eq 0 10 player_count || true
  "$RUN" shell-stop >>"$LOG" 2>&1
  l_wait_orphans 15 helpers >/dev/null || true
}
# l_update_tree <dir>: what `omarchy plugin update`'s fast-forward does to an
# install, for the files a release changes under a running shell: the tree
# under test's helper (the stub and every part it names) and its manifest
# replace <dir>'s, each by a rename, so a running process keeps any file it
# has open and the next spawn reads the new one. The QML is left alone: the
# keepLoaded service the host keeps across rescanPlugins is still the old one.
l_update_tree() {
  local dir=$1 part
  local -a parts=()
  mapfile -t parts < <(qa_helper_parts "$PLUGIN_ROOT")
  (( ${#parts[@]} > 0 )) || return 1
  for part in "${parts[@]}"; do
    cp -- "$part" "$dir/bin/helper/.rb-new" && mv -f -- "$dir/bin/helper/.rb-new" "$dir/bin/helper/${part##*/}" || return 1
  done
  cp -- "$PLUGIN_ROOT/bin/omarchy-iptv" "$dir/bin/.rb-new" && chmod 0755 "$dir/bin/.rb-new" \
    && mv -f -- "$dir/bin/.rb-new" "$dir/bin/omarchy-iptv" || return 1
  cp -- "$PLUGIN_ROOT/manifest.json" "$dir/.rb-new" && mv -f -- "$dir/.rb-new" "$dir/manifest.json"
}
probe_launch() {   # the shipping probe's `launch`, no owner claim written; NOFIELD on a tree without it
  timeout -k 2 20 python3 -I "$PLUGIN_ROOT/bin/omarchy-iptv" player probe --socket "$SOCK" 2>>"$LOG" | python3 -I -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    print("NOREPLY"); raise SystemExit(0)
print("NOFIELD" if "launch" not in d else str(d["launch"]))'
}

cleanup() {
  [[ -n $SAMPLER_PID ]] && kill -TERM "$SAMPLER_PID" 2>/dev/null
  [[ -n $L5_PID ]] && kill -TERM "$L5_PID" 2>/dev/null
  OMARCHY_IPTV_HARNESS_INSTANCE=2 "$RUN" shell-stop >/dev/null 2>&1
  "$RUN" reap >/dev/null 2>&1
  [[ -n $EXPORT_DIR && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  local d; for d in "$L15_DIR" "$L16_DIR" "$L4_DIR"; do [[ -n $d && -d $d ]] && rm -rf -- "$d"; done
  rm -f -- "$SCRATCH/bin/omarchy-notification-send"
  rmdir -- "$SCRATCH/bin" 2>/dev/null
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ---- which checkout is under test. The one refusal in it (git cannot export
# the ref --baseline names) sits ABOVE the transcript, and only the line that
# NAMES the tree sits below: a mistyped lever should die as a usage error
# rather than as an almost-empty transcript with a path printed for it. It
# used to sit below, as rewind-scenario.sh's four did -- found by the first
# review of F-M3-1 (b), which also found this comment claiming the opposite.
TREE_LINE=""
if [[ -n $BASELINE ]]; then
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-baseline-XXXXXX")
  git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR" || { echo "could not export $BASELINE" >&2; exit 2; }
  PLUGIN_ROOT="$EXPORT_DIR"
  TREE_LINE="== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported"
fi

# F-M3-1 half (b). The transcript opens HERE: after argument parsing, the traps
# and the refusals above, and before the first line of evidence -- which
# includes the line naming WHICH TREE is under test, because a transcript that
# cannot say that is evidence for nothing.
qa_transcript_start player || exit 2
[[ -n $TREE_LINE ]] && echo "$TREE_LINE"
export OMARCHY_IPTV_PLUGIN_ROOT="$PLUGIN_ROOT"
echo "== plugin tree $PLUGIN_ROOT   scratch $SCRATCH"
# Restart on adoption: the two releases whose OWN helpers launch the older
# players of L1, L1b, L2 and L4. A tag that cannot be exported whole is not a
# refusal (the scenario's other checks still mean something) but every L check
# that needs it then FAILS on its premise rather than passing on nothing.
L15_DIR=$(l_export v0.15.0) || bad "L the v0.15.0 tag could not be exported whole (git archive, then qa_helper_parts)"
L16_DIR=$(l_export v0.16.0) || bad "L the v0.16.0 tag could not be exported whole (git archive, then qa_helper_parts)"
echo "== L helpers: v0.15.0 $(qa_json_field "d['version']" "$(cat "$L15_DIR/manifest.json" 2>/dev/null)") ($(qa_helper_parts "$L15_DIR" | wc -l) parts), v0.16.0 $(qa_json_field "d['version']" "$(cat "$L16_DIR/manifest.json" 2>/dev/null)") ($(qa_helper_parts "$L16_DIR" | wc -l) parts)"
qa_target_nested "${WAYLAND_DISPLAY:-}" "$REAL_RUNTIME" && L_NESTED=1

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
# F-HARNESS-46: D-PLY-27's token in the base section, once, read off the live
# player's argv items (gpu_sw_base has why the position is the property). The
# items are printed first, unasserted, so a FAIL shows where the copies were.
printf '   P2 argv items read: %s\n' "$(gpu_sw_items "$PID1")"
if GPU_SW_WHY=$(gpu_sw_skip_reason "$BASELINE"); then
  skp "P2 the base section carries --gpu-sw=yes exactly once, before layer 1's --tls-verify=yes (D-PLY-27)" "$GPU_SW_WHY"
else
# Column 0 is load-bearing: scripts/qa-lib-test.sh recounts EXPECTED_CHECKS
# from the assertions that START a line, and reads an indented one as P14's
# loop body, which runs twice.
is "P2 the base section carries --gpu-sw=yes exactly once, before layer 1's --tls-verify=yes (D-PLY-27)" "$(gpu_sw_base "$PID1")" "layer1:yes base:1"
fi
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
# Restart on adoption's counter-case on the headline path: a player this tree
# launched is ADOPTED, so the shell writes no restart line (Model's
# OLDER_RESTART_LINE) and the helper no replaced line.
is "P4 no restart line and no replaced line: this tree's own player is adopted, not replaced" "$(log_count "$L_RESTART_TEXT") $(log_count "$L_REPLACED_TEXT")" "0 0"

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
is "P10 another launcher pushed the lock sequence ahead" "$(lock_seq)" "9999"
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
# Ruling CL10. This used to read `before11=$(log_count 'mpv unresponsive,
# restarting player')` and the assertion below was that delta. It could never
# discriminate: the string sits at ONE place in the shell, both trees emit it
# exactly once, and the SECOND relaunch the fix cancels is issued by the retry
# timer's `playerUp` branch, which logs nothing at all. Wave two ran the whole
# scenario both ways on a real display and the line
# `PASS P11 exactly ONE relaunch` appeared in BOTH summaries
# (docs/QA-RESULTS.md section D4). A pass against nothing.
#
# So the property moves onto the intent counter, which both trees produce and
# produce differently: one logical relaunch advances it by 1, and a tree that
# leaves the delivered relaunch queued fires a second `player restart` at the
# player it has just respawned and advances it by 2. Measured 1/1/1 live on
# the fixed tree, and 2 is what the baseline must read.
before11=$(player_seq)
beforelock11=$(lock_seq)
beforelog11=$(log_count 'mpv unresponsive, restarting player')
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
ck "P11 the intent counter answered before the wedge (positive control)" 'qa_value "$before11" && qa_value "$beforelock11"'
is "P11 exactly ONE relaunch, not a second one at the healthy player" "$(qa_delta "$before11" "$(player_seq)")" "1"
is "P11 and the player lock recorded exactly one intent for it" "$(qa_delta "$beforelock11" "$(lock_seq)")" "1"
# NOT the evidence, and labelled so nobody mistakes it for the assertion a
# second time (CL10: "keep the log line for humans reading a journal"). The
# delta is printed, never asserted: it reads 1 on both trees.
printf '   P11 journal observation only: "mpv unresponsive, restarting player" delta %s\n' \
  "$(qa_delta "$beforelog11" "$(log_count 'mpv unresponsive, restarting player')")"

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

echo "== P14 D-PLY-3 / D-PLY-33: PO-3's record is retired, and the reattach marks nothing"
# The full PO-3 procedure: play, kill the shell and then the player with
# nobody listening, come back. The record must be RETIRED - live at 8f9447e it
# stayed on disk in 2 runs of 3, so the next start consumed it again and
# re-marked the same channel with the same HH:MM.
#
# D-PLY-33 (owner, 2026-10-28): a record found with no player is a death
# nobody saw an end-file for, so the reattach marks NOTHING (it told nothing
# before either). This check used to wait for the mark. The retirement is
# read FIRST because it is the evidence that the reattach decided:
# markDeadSession retires the record in the same turn that dev 795a7bf
# raised the mark in, so once the file reads no record a mark that was
# coming is already in failedAt -- and NOFIELD is qa_field's answer from a
# service that answered, never from a dead one (NOSTATE).
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
until_no_session 10 || true
is "P14 the record is retired once it has been consumed" "$(session_id)" "$QA_NO_SESSION"
is "P14 the channel that died unattended is NOT marked (D-PLY-33)" "$(svc "d['failedAt'].get('t:live1')")" "$QA_NO_FIELD"
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

echo "== L1 restart on adoption: a player v0.15.0's own helper launched, met by this tree's shell"
# The decision's case (owner, 2026-10-31): the shell restarts over a player an
# earlier release started. v0.15.0 put the user's mpvArgs ON the argv, so the
# canary is the thing that must not survive: P1 is this tree's launch, built by
# this tree's own builder, and P0 -- with the canary -- is gone, never two at
# once. The notification stub is the scenario's own, in front of PATH for the
# shells the L segments start (run.sh harness_env puts $SCRATCH/bin first), so
# "no card" is read off what the shell actually posted.
mkdir -p "$SCRATCH/bin"
cat >"$SCRATCH/bin/omarchy-notification-send" <<'STUB'
#!/bin/bash
# player-scenario's L segments: the host's notification wrapper, logged. One
# line per post (tab-separated argv) into $SCRATCH/notify.log, and, as the
# real wrapper does with -p, a server id on stdout.
log="${0%/*}/../notify.log"
umask 077
n=$(( $(wc -l <"$log" 2>/dev/null || echo 0) + 1 ))
line=""
for a in "$@"; do line="$line"$'\t'"$a"; done
printf '%s%s\t\n' "$n" "$line" >>"$log"
for a in "$@"; do [[ $a == -p ]] && { echo "$n"; break; }; done
exit 0
STUB
chmod 0700 "$SCRATCH/bin/omarchy-notification-send"
: >"$SCRATCH/notify.log"
L_CACHE=$(ipc activeCache)
ck "L1 premise: the shell names the active source's cache folder for the old helpers to resolve the channel in" '[[ $L_CACHE == /* && -d $L_CACHE ]]'
l_stop_all
l_old_start "$L15_DIR" "t:live1" "--mpv-arg=$L_CANARY"
L1_P0=$(l_py tokens "$SOCK")
l_wait_up 30 || true
L1_CMD0=$(cmdline_of "$L1_P0")
ck "L1 premise: v0.15.0's own helper launched one player P0 on the harness socket, its argv carrying the canary" \
   '[[ $L1_P0 =~ ^[0-9]+$ && "$L1_CMD0" == *"input-ipc-server=$SOCK"* && "$L1_CMD0" == *"$L_CANARY"* ]]'
printf '   L1 P0 %s argv vs this tree'"'"'s builder: %s\n' "${L1_P0:-<none>}" "$(l_py build "$PLUGIN_ROOT" "$SOCK" "$L1_P0")"
j0=$(crash_count); cards0=$(notify_cards)
: >"$SCRATCH/harness.log"
sampler_start "$SCRATCH/l1.samples" 120
"$RUN" restart-shell >>"$LOG" 2>&1 || bad "L1 restart-shell failed (see $LOG)"
wait_log 'service loaded' 20 || bad "L1 the shell did not start"
L1_P1=$(l_wait_replaced "$L1_P0" 60)
until_eq "t:live1" 15 np id || true
L1_ADV=$(l_advances)
sampler_stop "$SCRATCH/l1.samples"
printf '   L1 samples %s; restart lines %s, helper replaced lines %s, P1 %s\n' "$(l_py verdict "$SCRATCH/l1.samples" "$L1_P0" "$L1_P1")" \
  "$(log_count "$L_RESTART_TEXT")" "$(log_count "$L_REPLACED_TEXT")" "${L1_P1:-<none>}"
is "L1 P0, the player v0.15.0 launched, is gone" "$(l_py alive "$SOCK" "$L1_P0")" "gone"
ck "L1 one new player P1 holds the socket in its place" '[[ $L1_P1 =~ ^[0-9]+$ && $L1_P1 != "$L1_P0" ]]'
is "L1 never two players on the socket at any 50 ms sample, and both were seen" "$(l_py verdict "$SCRATCH/l1.samples" "$L1_P0" "$L1_P1" | cut -d' ' -f2-4)" "max:1 p0:yes p1:yes"
L1_FORM=$(l_py build "$PLUGIN_ROOT" "$SOCK" "$L1_P1")
ck "L1 P1's argv is this tree's own composed launch, byte for byte, build marker included ($L1_FORM)" '[[ $L1_FORM == plain || $L1_FORM == include ]]'
# Every process that holds the socket token now, not P1 alone: on a tree that
# kept P0 the canary is still on ITS argv, and that is what this reads
# (rc-rao-b; the first version read only P1's, so on 202a7bc it went red for
# want of a P1, never for the canary it names).
L1_HOLDERS=$(l_py tokens "$SOCK")
L1_CANARY_ON=""
for p in $L1_HOLDERS; do [[ "$(cmdline_of "$p")" == *"$L_CANARY"* ]] && L1_CANARY_ON+="$p "; done
ck "L1 and the canary from v0.15.0's argv is on no command line holding the socket (holders: ${L1_HOLDERS:-none}; with the canary: ${L1_CANARY_ON:-none})" '[[ -n $L1_HOLDERS && -z $L1_CANARY_ON ]]'
is "L1 P1 dumps no core (its /proc limits)" "$(l_py core "$L1_P1")" "0 0"
ck "L1 the private options file is gone once P1 answered" '[[ ! -e $SCRATCH/runtime/omarchy-iptv/mpv-args.conf ]]'
is "L1 the shell still plays the channel P0 was playing" "$(np id)" "t:live1"
is "L1 and P1's own stash names it" "$(l_py stashid "$SOCK")" "t:live1"
is "L1 P1 plays: time-pos advances" "$L1_ADV" "advancing"
is "L1 exactly one restart line in the journal" "$(log_count "$L_RESTART_TEXT")" "1"
is "L1 no player card was posted, by a shell whose notifier is the logging stub" "$(qa_delta "$cards0" "$(notify_cards)") $(l_py notifier "$(shell_pid)" "$SCRATCH/bin")" "0 stub"
is "L1 the coredump journal did not move" "$(qa_delta "$j0" "$(crash_count)")" "0"
if (( L_NESTED )); then
  skp "L1 exactly one omarchy-iptv window" "the target is a nested compositor and hyprctl lists only the session's own windows; one player process at every sample is what is observed here"
else
is "L1 exactly one omarchy-iptv window" "$(windows_named)" "1"
fi

echo "== L1b the replaced player's pause and volume come back (owner's answer 3)"
l_stop_all
l_old_start "$L15_DIR" "t:live1"
L1B_P0=$(l_py tokens "$SOCK")
l_wait_up 30 || true
l_py set "$SOCK" volume 37 >/dev/null
l_py set "$SOCK" pause true >/dev/null
is "L1b premise: P0 (v0.15.0's) is paused at volume 37" "$(l_py get "$SOCK" pause) $(l_py get "$SOCK" volume)" "true 37"
: >"$SCRATCH/harness.log"
"$RUN" restart-shell >>"$LOG" 2>&1 || bad "L1b restart-shell failed (see $LOG)"
wait_log 'service loaded' 20 || bad "L1b the shell did not start"
L1B_P1=$(l_wait_replaced "$L1B_P0" 60)
until_eq "t:live1" 15 np id || true
l_wait_up 20 || true
ck "L1b P0 was replaced by P1" '[[ $L1B_P1 =~ ^[0-9]+$ && $L1B_P1 != "$L1B_P0" ]]'
is "L1b P1 comes back paused, at volume 37" "$(l_py get "$SOCK" pause) $(l_py get "$SOCK" volume)" "true 37"
is "L1b and the shell knows it is paused" "$(svc "d['paused']")" "true"

echo "== L2 the same with a player v0.16.0's own helper launched: no marker, so another build's"
l_stop_all
# The expectation comes from the two TREES' OWN builders, never from the
# verdict under test: v0.16.0's composed launch is not this tree's.
is "L2 premise: v0.16.0's own builder and this tree's compose different launch argvs" "$(l_py differ "$L16_DIR" "$PLUGIN_ROOT" "$SOCK")" "differ"
l_old_start "$L16_DIR" "t:live1"
L2_P0=$(l_py tokens "$SOCK")
l_wait_up 30 || true
L2_FORM0=$(l_py build "$L16_DIR" "$SOCK" "$L2_P0")
ck "L2 premise: P0's argv is exactly what v0.16.0's own builder composes ($L2_FORM0)" '[[ $L2_FORM0 == plain || $L2_FORM0 == include ]]'
j0=$(crash_count)
: >"$SCRATCH/harness.log"
sampler_start "$SCRATCH/l2.samples" 120
"$RUN" restart-shell >>"$LOG" 2>&1 || bad "L2 restart-shell failed (see $LOG)"
wait_log 'service loaded' 20 || bad "L2 the shell did not start"
L2_P1=$(l_wait_replaced "$L2_P0" 60)
until_eq "t:live1" 15 np id || true
L2_ADV=$(l_advances)
sampler_stop "$SCRATCH/l2.samples"
printf '   L2 samples %s; P1 %s\n' "$(l_py verdict "$SCRATCH/l2.samples" "$L2_P0" "$L2_P1")" "${L2_P1:-<none>}"
is "L2 P0, the player v0.16.0 launched, is gone" "$(l_py alive "$SOCK" "$L2_P0")" "gone"
ck "L2 one new player P1 holds the socket in its place" '[[ $L2_P1 =~ ^[0-9]+$ && $L2_P1 != "$L2_P0" ]]'
is "L2 never two players on the socket at any 50 ms sample, and both were seen" "$(l_py verdict "$SCRATCH/l2.samples" "$L2_P0" "$L2_P1" | cut -d' ' -f2-4)" "max:1 p0:yes p1:yes"
L2_FORM=$(l_py build "$PLUGIN_ROOT" "$SOCK" "$L2_P1")
ck "L2 P1's argv is this tree's own composed launch ($L2_FORM)" '[[ $L2_FORM == plain || $L2_FORM == include ]]'
is "L2 P1 dumps no core" "$(l_py core "$L2_P1")" "0 0"
is "L2 P1 plays the same channel: time-pos advances" "$(np id) $L2_ADV" "t:live1 advancing"
is "L2 exactly one restart line" "$(log_count "$L_RESTART_TEXT")" "1"
is "L2 the coredump journal did not move" "$(qa_delta "$j0" "$(crash_count)")" "0"

echo "== L3 the counter-case: this tree's own player across a shell stop and start is adopted, never restarted"
L3_PID=$(l_py tokens "$SOCK")
L3_START=$(l_py starttime "$L3_PID")
L3_T0=$(l_py get "$SOCK" time-pos)
: >"$SCRATCH/harness.log"
sampler_start "$SCRATCH/l3.samples" 120
# M8 (D-HOST-8), what the cage can show of it. omarchy 4.0.6's
# omarchy-restart-shell asks the old instance to quit with `quickshell kill`,
# loops until it has EXITED, and only then starts the new one, so the dying
# service's orphan check (Service.qml onDestruction, grace 6 s, PO-2) decides
# alone: it stops the player only if the old shell is still alive when the
# grace ends. run.sh's shell-stop is a SIGTERM, under which the harness shell
# exits without destroying its service (no orphan check is spawned: seen on
# the first L run), so this stop is the host's own: `quickshell kill --pid`
# of the harness shell's RECORDED pid, under the harness's runtime directory,
# where only the harness's instances are registered. The m8 sampler stamps
# the shell's exit and the orphan check's life on one clock.
L3_QS=$(shell_pid)
rm -f -- "$SCRATCH/m8.samples" "$SCRATCH/m8.samples.stop"
l_py m8 "$SOCK" "${L3_QS:-0}" "$SCRATCH/m8.samples" 30 >/dev/null 2>&1 &
L3_M8=$!
L3_T=$(l_py now)
[[ $L3_QS =~ ^[0-9]+$ ]] && XDG_RUNTIME_DIR="$SCRATCH/runtime" timeout -k 2 35 quickshell kill --pid "$L3_QS" >>"$LOG" 2>&1
for ((i = 0; i < 300; i++)); do [[ -z $(l_py helpers "$SOCK") ]] && ! kill -0 "${L3_QS:-0}" 2>/dev/null && break; sleep 0.1; done
# One more sample past the moment the loop above saw the check gone: the
# sampler reads the stop file before it writes, so stopping it at once can
# lose the only sample that shows the check ended (orphan-gone NONE, seen once).
sleep 0.3
: >"$SCRATCH/m8.samples.stop"; wait "$L3_M8" 2>/dev/null
"$RUN" shell-stop >>"$LOG" 2>&1
L3_M8V=$(l_py m8verdict "$SCRATCH/m8.samples" "$L3_T")
printf '   L3 / M8: after `quickshell kill`: %s (seconds); the player %s\n' "$L3_M8V" "$(l_py alive "$SOCK" "$L3_PID")"
ck "L3 premise: the dying shell spawned its orphan check and it ran out, so the player's survival is that check's answer ($L3_M8V)" \
   '[[ $L3_M8V != *"orphan-seen:NONE"* && $L3_M8V != *"orphan-gone:NONE"* && -z $(l_py orphans "$SOCK") ]]'
is "L3 the player outlived its shell's orphan check (M8: the restart case, not orphan-stopped)" "$(l_py alive "$SOCK" "$L3_PID")" "alive"
L3_TRS=$(l_py now)
"$RUN" restart-shell >>"$LOG" 2>&1 || bad "L3 restart-shell failed (see $LOG)"
wait_log 'service loaded' 20 || bad "L3 the shell did not start"
until_eq true 10 svc "d['socketAttached']" || true
sleep 3
sampler_stop "$SCRATCH/l3.samples"
L3_T1=$(l_py get "$SOCK" time-pos)
L3_TREAD=$(l_py now)
L3_START1=$(l_py starttime "$(l_py tokens "$SOCK")")
ck "L3 premise: the player read before the stop is this tree's P1 of L2" '[[ $L3_PID =~ ^[0-9]+$ && $L3_PID == "$L2_P1" ]]'
# end:END as well: a sampler that died early would have judged only the
# samples before the stop (rc-rao-b).
is "L3 the same pid holds the socket, alone, at every sample" "$(l_py verdict "$SCRATCH/l3.samples" "$L3_PID" "" | cut -d' ' -f2,5,6)" "max:1 end:END p0all:yes"
# A start time that could not be read is not a match: NOSTAT on both sides (no
# holder before, none after) used to read as "unchanged" (rc-rao-b).
ck "L3 the same process: /proc stat field 22 unchanged ($L3_START -> $L3_START1)" '[[ $L3_START =~ ^[0-9]+$ && $L3_START1 == "$L3_START" ]]'
# Continuous, and not by chance: a replacement can only be spawned after the
# new shell starts, so its time-pos is at most the seconds since then. The
# player read here must be PAST that -- it was playing before the new shell
# existed. `T1 > T0` alone passed any replacement that had played longer than
# the old player had when T0 was read (rc-rao-b; under M-OLDER it read 3.18 ->
# 1.85 only because T0 was small).
L3_UP=$(python3 -I -c 'import sys
try:
    print("%.2f" % (float(sys.argv[2]) - float(sys.argv[1])))
except ValueError:
    print("NOCLOCK")' "$L3_TRS" "$L3_TREAD")
ck "L3 time-pos is continuous across the restart ($L3_T0 -> $L3_T1 s, past the new shell's $L3_UP s)" 'python3 -I -c "import sys; t0, t1, up = map(float, sys.argv[1:4]); sys.exit(0 if t1 > t0 and t1 > up else 1)" "$L3_T0" "$L3_T1" "$L3_UP" 2>/dev/null'
is "L3 no restart line and no replaced line" "$(log_count "$L_RESTART_TEXT") $(log_count "$L_REPLACED_TEXT")" "0 0"
is "L3 the probe the shell runs reads it as this build's launch" "$(probe_launch)" "current"
is "L3 the shell adopted it and plays its channel" "$(np id) $(svc "d['socketAttached']")" "t:live1 true"

echo "== L7 D-SINK-71: a player v0.15.0 launched, which the probe must migrate, its channel list landing only after the hold"
# The owner's decision of 2026-11-02: an older player whose settings the probe
# had to change in place is replaced when the list lands, however late. The
# lever is what the harness already has: the active source's channels.json is
# moved aside before the shell starts (playlist-status.json stays, so the
# cache reads fresh and nothing is fetched at start), so the shell has no list
# when the 15 s hold (Model.OLDER_RESTART_HOLD_MS) runs out; `ipc refresh`
# then runs the fixture server's fetch, whose exit reloads channels.json
# (handlePlaylistExit), and the list lands. That the probe MIGRATED P0 is read
# off P0 itself: v0.15.0 leaves load-auto-profiles at mpv's auto (a string,
# which `get` never prints), and only the migration (secure_player) sets it
# to no, which mpv answers as false.
l_stop_all
l_old_start "$L15_DIR" "t:live1"
L7_P0=$(l_py tokens "$SOCK")
l_wait_up 30 || true
L7_CMD0=$(cmdline_of "$L7_P0")
ck "L7 premise: v0.15.0's own helper launched one player P0 on the harness socket" '[[ $L7_P0 =~ ^[0-9]+$ && "$L7_CMD0" == *"input-ipc-server=$SOCK"* ]]'
is "L7 premise: P0's load-auto-profiles is mpv's auto, so the shell's probe has to migrate it" "$(l_py get "$SOCK" load-auto-profiles)" "STR"
mv -f -- "$L_CACHE/channels.json" "$SCRATCH/l7-channels.json" 2>>"$LOG"
ck "L7 premise: the active source's channel list is withheld" '[[ ! -e $L_CACHE/channels.json && -s $SCRATCH/l7-channels.json ]]'
j0=$(crash_count); cards0=$(notify_cards)
: >"$SCRATCH/harness.log"
sampler_start "$SCRATCH/l7.samples" 120
"$RUN" restart-shell >>"$LOG" 2>&1 || bad "L7 restart-shell failed (see $LOG)"
wait_log 'service loaded' 20 || bad "L7 the shell did not start"
L7_TS=$(l_py now)
until_eq "t:live1" 15 np id || true
# Past the hold: the probe goes out as the service loads and answers in well
# under a second, so 19 s after the load was seen is 4 s past the hold's end.
L7_PAST=$(python3 -I -c 'import sys, time; print("%.1f" % max(0.0, float(sys.argv[1]) + 19 - time.monotonic()))' "$L7_TS")
sleep "$L7_PAST"
L7_HELD=$(python3 -I -c 'import sys, time; print("%.1f" % (time.monotonic() - float(sys.argv[1])))' "$L7_TS")
is "L7 premise: the shell adopted P0 and names its channel, with no channel list" "$(np id) $(svc "d['channels']")" "t:live1 0"
is "L7 premise: the shell's probe migrated P0 in place (load-auto-profiles now reads false, mpv's no)" "$(l_py get "$SOCK" load-auto-profiles)" "false"
is "L7 past the hold ($L7_HELD s after the shell loaded): P0 still holds the socket alone, and no restart line yet" "$(l_py tokens "$SOCK") $(log_count "$L_RESTART_TEXT")" "$L7_P0 0"
L7_TR=$(l_py now)
ipc refresh >/dev/null
L7_P1=$(l_wait_replaced "$L7_P0" 40)
until_eq "t:live1" 15 np id || true
L7_ADV=$(l_advances)
sampler_stop "$SCRATCH/l7.samples"
L7_TIMES=$(l_py p0times "$SCRATCH/l7.samples" "$L7_P0")
printf '   L7 samples %s; P0 last seen / first missed %s (refresh at %s, shell loaded at %s); P1 %s\n' \
  "$(l_py verdict "$SCRATCH/l7.samples" "$L7_P0" "$L7_P1")" "$L7_TIMES" "$L7_TR" "$L7_TS" "${L7_P1:-<none>}"
# The fetch rewrote channels.json; the copy moved aside goes, or comes back
# when the fetch did not write one (the later segments need the list).
if [[ -e $L_CACHE/channels.json ]]; then rm -f -- "$SCRATCH/l7-channels.json"; else mv -f -- "$SCRATCH/l7-channels.json" "$L_CACHE/channels.json"; fi
is "L7 the list landed: the fixture's 3 channels" "$(svc "d['channels']")" "3"
is "L7 P0, the player v0.15.0 launched, is gone" "$(l_py alive "$SOCK" "$L7_P0")" "gone"
ck "L7 one new player P1 holds the socket in its place" '[[ $L7_P1 =~ ^[0-9]+$ && $L7_P1 != "$L7_P0" ]]'
ck "L7 the replacement followed the list, not the hold: P0 was still seen after the refresh went out and first missed after it ($L7_TIMES; refresh $L7_TR)" \
   'python3 -I -c "import sys; last, gone, tr = map(float, sys.argv[1:4]); sys.exit(0 if last >= tr and gone > tr else 1)" $L7_TIMES "$L7_TR" 2>/dev/null'
is "L7 never two players on the socket at any 50 ms sample, and both were seen" "$(l_py verdict "$SCRATCH/l7.samples" "$L7_P0" "$L7_P1" | cut -d' ' -f2-4)" "max:1 p0:yes p1:yes"
L7_FORM=$(l_py build "$PLUGIN_ROOT" "$SOCK" "$L7_P1")
ck "L7 P1's argv is this tree's own composed launch ($L7_FORM)" '[[ $L7_FORM == plain || $L7_FORM == include ]]'
is "L7 the same channel plays on, in P1's own stash: time-pos advances" "$(np id) $(l_py stashid "$SOCK") $L7_ADV" "t:live1 t:live1 advancing"
is "L7 exactly one restart line" "$(log_count "$L_RESTART_TEXT")" "1"
is "L7 no player card, and the coredump journal did not move" "$(qa_delta "$cards0" "$(notify_cards)") $(qa_delta "$j0" "$(crash_count)")" "0 0"

echo "== L8 D-SINK-71's counter-case: a player v0.16.0 launched, which the probe finds already safe, its channel list landing only after the hold"
# The owner's decision is late delivery ONLY for a player whose settings the
# probe had to change in place. v0.16.0 put every pin on its own argv, so this
# tree's probe should find nothing to migrate, the hold's end defers it, and
# the late list does NOT replace it: it plays on, fed nothing, until a channel
# change (Q4). lane-sk71 had that premise by reading the helper diff only;
# this observes it, and a tree that late-delivers to every safe player (the
# migrated guard removed) reds the check that P0 survived the list (rc-sk71).
# The lever is L7's.
l_stop_all
l_old_start "$L16_DIR" "t:live1"
L8_P0=$(l_py tokens "$SOCK")
l_wait_up 30 || true
L8_CMD0=$(cmdline_of "$L8_P0")
ck "L8 premise: v0.16.0's own helper launched one player P0 on the harness socket" '[[ $L8_P0 =~ ^[0-9]+$ && "$L8_CMD0" == *"input-ipc-server=$SOCK"* ]]'
is "L8 premise: P0's load-auto-profiles already reads false, from its own argv's pin" "$(l_py get "$SOCK" load-auto-profiles)" "false"
mv -f -- "$L_CACHE/channels.json" "$SCRATCH/l8-channels.json" 2>>"$LOG"
ck "L8 premise: the active source's channel list is withheld" '[[ ! -e $L_CACHE/channels.json && -s $SCRATCH/l8-channels.json ]]'
j0=$(crash_count); cards0=$(notify_cards)
: >"$SCRATCH/harness.log"
"$RUN" restart-shell >>"$LOG" 2>&1 || bad "L8 restart-shell failed (see $LOG)"
wait_log 'service loaded' 20 || bad "L8 the shell did not start"
L8_TS=$(l_py now)
until_eq "t:live1" 15 np id || true
L8_PAST=$(python3 -I -c 'import sys, time; print("%.1f" % max(0.0, float(sys.argv[1]) + 19 - time.monotonic()))' "$L8_TS")
sleep "$L8_PAST"
L8_HELD=$(python3 -I -c 'import sys, time; print("%.1f" % (time.monotonic() - float(sys.argv[1])))' "$L8_TS")
is "L8 premise: the shell adopted P0 and names its channel, with no channel list" "$(np id) $(svc "d['channels']")" "t:live1 0"
is "L8 past the hold ($L8_HELD s after the shell loaded): P0 still holds the socket alone, and no restart line" "$(l_py tokens "$SOCK") $(log_count "$L_RESTART_TEXT")" "$L8_P0 0"
sampler_start "$SCRATCH/l8.samples" 60
ipc refresh >/dev/null
until_eq 3 30 svc "d['channels']" || true
# L7's replacement followed its refresh by 1.2 s; 8 s after the list landed
# is well past any replacement the list could have caused.
sleep 8
sampler_stop "$SCRATCH/l8.samples"
L8_VERDICT=$(l_py verdict "$SCRATCH/l8.samples" "$L8_P0" "")
printf '   L8 samples %s\n' "$L8_VERDICT"
if [[ -e $L_CACHE/channels.json ]]; then rm -f -- "$SCRATCH/l8-channels.json"; else mv -f -- "$SCRATCH/l8-channels.json" "$L_CACHE/channels.json"; fi
is "L8 the list landed: the fixture's 3 channels" "$(svc "d['channels']")" "3"
is "L8 P0 alone on the socket at every 50 ms sample from the refresh until 8 s after the list landed" "$(cut -d' ' -f2,3,5,6 <<<"$L8_VERDICT")" "max:1 p0:yes end:END p0all:yes"
is "L8 P0 was not replaced: the same pid holds the socket alone, no restart line, the bar still names its channel" "$(l_py tokens "$SOCK") $(log_count "$L_RESTART_TEXT") $(np id)" "$L8_P0 0 t:live1"
is "L8 no player card, and the coredump journal did not move" "$(qa_delta "$cards0" "$(notify_cards)") $(qa_delta "$j0" "$(crash_count)")" "0 0"
# The deferred player is left to a stop, as Q4 leaves it to the user; P9
# starts from no player.
ipc stop >/dev/null
until_eq 0 10 player_count || true

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

echo "== L4 the old QML after an update: v0.16.0's keepLoaded Service, this tree's helper on disk, then a zap"
# `omarchy plugin update` is `git merge --ff-only` and then `rescanPlugins`,
# and the host KEEPS a keepLoaded service across that (shell.qml
# unloadPluginServices; M7), so until the shell restarts the service that runs
# is the old release's and every helper it spawns is the new one on disk
# (design 1, D-SINK-70's path). The harness never destroys its service, which
# is that state; the update is the helper and the manifest replaced under it
# (l_update_tree). Then a channel change: the old Service's zap reaches the
# NEW helper's `play`, the gate refuses another build's player before any
# command, v0.16.0's QML routes `not_running` to `player start`, and the start
# replaces the player. L5 reads the same moment off a logging server.
L4_DIR=$(l_export v0.16.0) || bad "L4 the v0.16.0 tag could not be exported for the old QML"
cat >"$FIX/l4.m3u" <<EOF
#EXTM3U
#EXTINF:-1 tvg-id="l4a" group-title="Harness",Harness L4 A
http://127.0.0.1:8765/test.ts
#EXTINF:-1 tvg-id="l4b" group-title="Harness",Harness L4 B
#EXTVLCOPT:http-user-agent=$L5_UA
http://127.0.0.1:$L5_PORT/l5b.ts
EOF
cp -f "$FIX/test.ts" "$FIX/l5b.ts"
: >"$SCRATCH/l5.log"
python3 -I -B -c "$L_PY" serve "$L5_PORT" "$FIX" "$SCRATCH/l5.log" "$L5_UA" >/dev/null 2>&1 &
L5_STARTED=$!
# The listener's pid from ss, never $! alone (working in parallel 3); the two
# agree here because nothing wraps it -- python is started directly, not
# through l_py, whose function body would be a subshell between them -- and
# the check says so.
for i in $(seq 1 50); do
  L5_PID=$(ss -ltnpH "sport = :$L5_PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)
  [[ -n $L5_PID ]] && break
  sleep 0.1
done
ck "L5 premise: the logging server holds its port and is the process this scenario started" '[[ -n $L5_PID && $L5_PID == "$L5_STARTED" ]]'
: >"$SCRATCH/harness.log"
OMARCHY_IPTV_PLUGIN_ROOT="$L4_DIR" QS_DISABLE_FILE_WATCHER=1 "$RUN" --detach --serve --timeout 0 --playlist "$FIX/l4.m3u" >>"$LOG" 2>&1
wait_log 'service loaded' 20 || bad "L4 the v0.16.0 harness did not start (see $LOG)"
until_eq 2 20 svc "d['channels']" || bad "L4 the L4 playlist did not load"
ipc play "t:l4a" >/dev/null
until_eq 1 15 player_count || true
L4_P0=$(l_py tokens "$SOCK")
l_wait_up 30 || true
L4_FORM0=$(l_py build "$L4_DIR" "$SOCK" "$L4_P0")
ck "L4 premise: v0.16.0's own Service and helper launched P0, exactly v0.16.0's composed argv ($L4_FORM0)" '[[ $L4_FORM0 == plain || $L4_FORM0 == include ]]'
L4_QS=$(shell_pid)
l_update_tree "$L4_DIR" || bad "L4 the update could not replace the export's helper and manifest"
ck "L4 premise: the helper on disk is now this tree's, byte for byte" 'cmp -s "$L4_DIR/bin/omarchy-iptv" "$PLUGIN_ROOT/bin/omarchy-iptv" && cmp -s "$L4_DIR/manifest.json" "$PLUGIN_ROOT/manifest.json"'
j0=$(crash_count); cards0=$(notify_cards)
L5_BEFORE=$(wc -l <"$SCRATCH/l5.log" | tr -d ' ')
sampler_start "$SCRATCH/l4.samples" 120
ipc play "t:l4b" >/dev/null
L4_P1=$(l_wait_replaced "$L4_P0" 60)
until_eq "t:l4b" 15 np id || true
L4_ADV=$(l_advances)
sampler_stop "$SCRATCH/l4.samples"
L4_TIMES=$(l_py p0times "$SCRATCH/l4.samples" "$L4_P0")
printf '   L4 samples %s; P0 last seen / first gone %s; helper replaced lines %s; P1 %s\n' \
  "$(l_py verdict "$SCRATCH/l4.samples" "$L4_P0" "$L4_P1")" "$L4_TIMES" "$(log_count "$L_REPLACED_TEXT")" "${L4_P1:-<none>}"
ck "L4 the old Service ran throughout: the same shell process before the update and after the zap" '[[ -n $L4_QS && "$(shell_pid)" == "$L4_QS" ]] && kill -0 "$L4_QS" 2>/dev/null'
is "L4 P0, v0.16.0's player, is gone" "$(l_py alive "$SOCK" "$L4_P0")" "gone"
ck "L4 one new player P1 holds the socket in its place" '[[ $L4_P1 =~ ^[0-9]+$ && $L4_P1 != "$L4_P0" ]]'
is "L4 never two players on the socket at any 50 ms sample, and both were seen" "$(l_py verdict "$SCRATCH/l4.samples" "$L4_P0" "$L4_P1" | cut -d' ' -f2-4)" "max:1 p0:yes p1:yes"
L4_FORM=$(l_py build "$PLUGIN_ROOT" "$SOCK" "$L4_P1")
ck "L4 P1's argv is this tree's own composed launch ($L4_FORM)" '[[ $L4_FORM == plain || $L4_FORM == include ]]'
is "L4 P1 dumps no core" "$(l_py core "$L4_P1")" "0 0"
is "L4 the old Service plays B" "$(np id) $(svc "d['playing']")" "t:l4b true"
is "L4 and P1 plays it: time-pos advances" "$L4_ADV" "advancing"
is "L4 the helper journaled exactly one replacement" "$(log_count "$L_REPLACED_TEXT")" "1"
is "L4 no player card was posted, by a shell whose notifier is the logging stub" "$(qa_delta "$cards0" "$(notify_cards)") $(l_py notifier "$(shell_pid)" "$SCRATCH/bin")" "0 stub"
is "L4 the coredump journal did not move" "$(qa_delta "$j0" "$(crash_count)")" "0"
if (( L_NESTED )); then
  skp "L4 exactly one omarchy-iptv window" "the target is a nested compositor and hyprctl lists only the session's own windows; one player process at every sample is what is observed here"
else
is "L4 exactly one omarchy-iptv window" "$(windows_named)" "1"
fi

echo "== L5 never fed: B's URL and header reach the server only after P0 is gone"
# The server stamps every GET with CLOCK_MONOTONIC, the sampler every sample:
# one clock. A request for B, or one carrying B's header, before P0's first
# absent sample could only be P0's -- P1 is spawned after the ladder has P0
# gone -- so "every one after" is "none from P0".
L5_VERDICT=$(python3 -I - "$SCRATCH/l5.log" "${L5_BEFORE:-0}" $L4_TIMES <<'PY'
import sys
path, before = sys.argv[1], int(sys.argv[2]) if sys.argv[2].isdigit() else 0
gone = sys.argv[4] if len(sys.argv) > 4 else "NONE"
try:
    lines = open(path).read().splitlines()[before:]
except OSError:
    lines = []
b = [float(l.split()[0]) for l in lines if " GET /l5b.ts " in l]
ua = [float(l.split()[0]) for l in lines if l.endswith(" ua:yes")]
if gone == "NONE":
    print("requests:%d first:p0-never-gone header-before:NA header-all:%d" % (len(b), len(ua)))
else:
    g = float(gone)
    first = "none" if not b else ("after" if min(b) > g else "before")
    print("requests:%d first:%s header-before:%d header-all:%d" % (len(b), first, len([t for t in ua if t <= g]), len(ua)))
PY
)
printf '   L5 %s\n' "$L5_VERDICT"
ck "L5 B was fetched at all, so a zero below is about P0 ($L5_VERDICT)" '[[ $L5_VERDICT =~ ^requests:[1-9] ]]'
# And B's header was seen at all: the server recognises it, so the zero below
# is about P0 and not a header nobody sends (rc-rao-b; the first version had
# no control for the header half).
ck "L5 B's provider header reached the server on some request, so the header count below can see one ($L5_VERDICT)" '[[ $L5_VERDICT =~ header-all:[1-9] ]]'
is "L5 every request for B's path follows P0's exit, and none carrying B's header came before it" "$(cut -d' ' -f2-3 <<<"$L5_VERDICT")" "first:after header-before:0"
"$RUN" reap >>"$LOG" 2>&1
[[ -n $L5_PID ]] && kill -TERM "$L5_PID" 2>/dev/null && { wait "$L5_STARTED" 2>/dev/null; L5_PID=""; }
until_eq 0 8 player_count || true

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
#
# A SKIPPED check counts toward it (F-HARNESS-46): P2's `--gpu-sw=yes` check
# skips on a baseline that predates D-PLY-27, and that run has still reached
# every check site. A skip only ever comes from `skp`, which prints its line
# and moves `skipped`, so the floor cannot be met by a check that vanished.
# 85 -> 142 (lane RB, 2026-11-02, restart on adoption): P4's no-restart-line
# check and the L segments' 56 (L1 16, L1b 4, L2 10, L3 9, L4 15 with L5's
# server premise, L5 2; the two window checks SKIP under a nested compositor
# and still count here).
# 142 -> 143 (rc-rao-b, 2026-11-02): L5's control that B's header is seen at all.
# 143 -> 158 (lane-sk71, 2026-11-02): L7's 15, the late list (D-SINK-71).
# 158 -> 167 (rc-sk71, 2026-11-02): L8's 9, its counter-case.
EXPECTED_CHECKS=167
ran=$((checks + skipped))
is "the harness ran every check it has" "$ran" "$EXPECTED_CHECKS"

printf '\n== summary: %d passed, %d failed, %d skipped, %d assertions executed\n' "$pass" "$fail" "$skipped" "$checks"
(( fail == 0 )) || exit 1
