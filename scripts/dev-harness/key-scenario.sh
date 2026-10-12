#!/bin/bash
# scripts/dev-harness/key-scenario.sh -- D-SINK-19, the repair round (lead
# rulings R1-R7), observed on the REAL Service.qml under a nested headless
# compositor: the active source is named by a KEY on the bar entry and the
# URL lives only in the plugin's own state.json.
#
#   key-scenario.sh check-tree              the instrument arm ONLY; run by check.sh
#   key-scenario.sh [live] [--baseline REF] the instrument arm, then the shell arm
#
# THE FINDING. For the life of the project the host's bar entry carried the
# provider's playlist URL -- credentials and all -- in ~/.config/omarchy/
# shell.json, a file the plugin does not own and whose mode other software
# resets (D-SINK-18 was the containment, the mode). D-SINK-19 removes the
# cause: the entry carries `sourceKey`, an 8-hex pointer; state.json (0600 in
# a 0700 directory) carries `activeKey`; `omarchy bar set ... playlistUrl`
# becomes an INPUT that is adopted and then taken OFF the entry by the
# plugin's own write. The first build (e618fce, integrated as f275bde) was
# reviewed and found not shippable: a URL set while the shell was down was
# DISCARDED and then ERASED from shell.json (review P1), removing the active
# source left a dangling key in the file (harness P1), the migration's only
# copy of a new source could be destroyed between its two writes (P2), and
# the harness's own instrument -- `hostEntry`, which hashes the entry's
# playlistUrl -- went blind on the very tree it had to grade (P2). Lane A
# repaired R1-R5 in Model.js / Service.qml (f84ee50); this file is R6 (the
# instrument) and R7 (the scenarios).
#
# "CLOSED" IS THE WRONG WORD AND THIS FILE NEVER USES IT. The key is fnv1a32
# of the normalized URL: it reveals no URL and it DOES confirm a guessed one,
# a 32-bit check on a guess. A green run here says the exposure went from the
# credential itself to that check, not that it went to zero.
#
# WHAT THIS SCENARIO OBSERVES, AND HOW. Two arms:
#
#   the instrument arm (check-tree, and the preflight of live). R6: the fake
#   shell's `entryKey` reads `sourceKey` first and the `playlistUrl` hash
#   second, NAMED CANDIDATES ONLY. It lives in harness-lib.js, which
#   shell.qml imports and node loads (rule 12), and this arm drives it with
#   the tree's own Model.js: a key beside a differing URL answers the key; a
#   URL alone answers its hash; an entry whose only key-shaped values sit in
#   OTHER settings (`mpvArgs` "deadbeef", a label of 8 hex) answers "" -- the
#   first repair iterated every own value and would have reported the user's
#   mpv argument as the active source; an empty or malformed mirror falls
#   through to the URL. Then three seams: shell.qml's entryKey and hostEntry
#   go through that function, and run.sh stages the file beside Model.js.
#
#   the shell arm (live). The dev-harness fake shell with the REAL
#   Service.qml and Model.js under cage (docs/SPIKE-CAGE-HEADLESS.md), IPC
#   only -- no keystroke, no screenshot, the guide never opened -- over a
#   state.json this scenario seeds and real cache directories the real
#   helper writes. Six shells are started and stopped by their recorded pid,
#   each presenting the bar entry a HOST would hold at that point
#   (`run.sh --playlist` for a URL, `--source-key` for the mirror an earlier
#   shell wrote); the fake host models the config in memory, so what
#   survives a stop is what this scenario observed stored and re-seeds. The
#   entry's content is read through `hostEntry` as keys and key NAMES, never
#   values.
#
#   I1  a key beside a differing URL answers the key (sourceKey first)
#   I2  a URL alone answers its hash (the URL hash second)
#   I3  key-shaped values in other settings answer ""   <- named candidates only
#   I4  an empty mirror beside a URL answers the URL's hash
#   I5  a malformed mirror (uppercase) beside a URL answers the URL's hash
#   I6  an absent entry answers "" and does not throw
#   I7  the key-NAMES reader lists names sorted, `id` excluded, no value
#   S1  shell.qml's entryKey is HarnessLib.entryKey over findBarEntry   (seam)
#   S2  hostEntry reads BOTH sides through entryKey                     (seam)
#   S3  run.sh stages harness-lib.js beside Model.js and proves the copy (seam)
#
#   D1  the first start over the 0.13.5 shape ADOPTS the entry's URL in memory
#       while the state save is parked behind the start-up dirs (control: the
#       rig sees the adoption at all)
#   D2  the adopted key SURVIVES the start-up dirs becoming ready: still in
#       memory and now in the file           <- the drop this file found (see STATUS)
#   M1  two-source migration: state.json `activeKey` = the entry URL's key
#   M2  ... and the file still holds the TWO records it went in with, as does
#       `sources()`                                                  <- R7, SRC-MIG-09
#   M3  the stored entry carries `sourceKey` = that key and NO playlistUrl /
#       epgUrl                                                       <- the fix
#   M4  the published entry (one write behind, rule 9) still carries the URL:
#       the host shape the instrument has to read through
#   M5  configured, 20 channels from the migrated cache, activeCache is its dir
#   M6  the inactive source's cache and the active one's are untouched: no
#       fetch ran, nothing was moved
#   J1  a start over the MIGRATED shape (key on the entry, no URL, key in the
#       file) makes NO entry write
#   J2  ... and the file's key and count are unchanged (idempotent, SRC-MIG-08)
#   J3  ... configured with the same 20 channels
#   C1  a URL set while the shell was down, beside the surviving mirror: a
#       record for it, origin cli                                 <- R1, review P1
#   C2  ... state.json `activeKey` = ITS key, not the mirror's
#   C3  ... the stored entry carries the NEW key and no URL
#   C4  ... the history kept every record (3)
#   C5  ... configured on it, its first fetch loaded, activeCache is its dir
#   E1  an epgUrl set while the shell was down lands on the ACTIVE record  <- R4
#   E2  ... and is taken off the stored entry by the same write
#   E3  ... and neither the harness log nor any IPC reply carries its credential
#   R1  removing the active source leaves `activeKey` "" IN THE FILE     <- R3
#   R2  ... the stored entry's mirror is "" and still present
#   R3  ... unconfigured, 0 channels, no active cache
#   R4  ... only that cache directory is gone; the other record and its
#       cache survive
#   R5  a start over that leaves it unconfigured with the one record
#       (control: the dangling-key resolution both trees have)
#   O1  the interruptible window was OBSERVED from inside: state loaded, dirs
#       not ready, state save parked, the in-memory state already naming the
#       NEW source (control: the rig reached the window at all)
#   O2  inside it the entry write WAITS: the stored entry still carries the
#       URL and the service holds the key for later        <- R5, review P2
#   O3  inside it state.json on disk is untouched (control)
#   O4  after a SIGKILL in the window state.json is still the file the shell
#       started from (control: nothing was written by either tree)
#   O5  the next start RECOVERS: the new source is in the file, active,
#       configured, fetched                                 <- R5, the loss
#   O6  ... and the migration then completes: key on the entry, URL off it
#   P1  no labelled harness-log line carries a URL or a fixture path
#   P2  no credential token anywhere in the harness log
#   T1  the shell, the compositor and the nested socket are gone (by pid)
#
# Every segment seeds its OWN state.json, caches and entry and starts a fresh
# shell, so a red in one is attributable to one ruling and never to the
# segment before it (the first version chained them and one red cascaded
# into seventeen).
#
# STATUS, MEASURED 2026-10-11 ON lane-key-r1 (f84ee50), THE TREE THIS WAS
# WRITTEN AGAINST -- read before reading any red line. D2 is RED there, and
# so is everything that rests on an adoption made at START-UP: M1, M3, M5,
# C1..C5, E1, O5, O6 -- 12 of 43, "32 passed, 12 failed". The mechanism,
# attributed by polling `pointerState` at 50 ms through a start and then
# repeating it with a helper whose `state init` does nothing: the service
# adopts the entry's URL at the state load and PARKS the save (dirsReady
# false); the helper's start-up `state init` then runs `os.chmod(path,
# 0o600)` on the EXISTING state.json (bin/omarchy-iptv init_state_file, "an
# existing file is not rewritten; only its mode is tightened"); that chmod
# is an inotify IN_ATTRIB on the file the service's FileView watches, so
# `onFileChanged: reload()` fires and applyUserState is handed the
# PRE-ADOPTION text; Model.stateOnLoad keeps only the session record of the
# in-memory state, so the adopted key -- and a newly adopted RECORD, which
# is the review's P1 shape again -- is dropped; stateInitProc's exit then
# writes the parked save, which is now the key-less state, and flushes the
# entry mirror, which strips the URL and writes `sourceKey ""`. Measured:
# +1489 ms adopted, parked, key held; +1909 ms dirsReady, memory "", file
# "", entry `sourceKey ""` with no URL; with `state init` skipped the key
# survives in memory, in the file and on the entry. The shape pre-exists
# D-SINK-19 (the review's P2 said the URL on the entry "was doing work here
# too" as an accidental backup); D-SINK-19 turns a harmless re-adoption on
# the next start into the loss of the user's active source on the first
# start after the upgrade. NOT fixed here (Service.qml and the helper are
# not this lane's); filed for the lead with this measurement. Until it is
# fixed these checks have no green tree; the expectations below are what
# the rulings say, not what the tree does.
#
# RULE 11, THE RED RUN. `--baseline f275bde` exports the first build (the
# side integration of e618fce, red by design) and runs its Model.js,
# Service.qml and helper through the same rig, with this tree's harness.
# Measured 2026-10-11, both trees, recipe in the footer the run prints:
#   lane-key-r1:        32 passed, 12 failed  (the STATUS list above)
#   --baseline f275bde: 35 passed,  9 failed  (C1..C5, E1, O2, O5, O6)
# The one check red on the baseline and green on the repaired tree is O2:
# the first build rewrote the entry while the state save was still parked
# (the review's P2, R5), observed as the stored entry losing its URL inside
# the window with nothing held for later. D2, M1, M3 and M5 are the other
# way round -- GREEN on the baseline, RED on lane-key-r1: the first build
# wrote the entry BEFORE the chmod reload and its own-write overlay then
# handed the mirror back to adoptActiveSource step 3, which recovers a KNOWN
# record by accident; the repaired tree waits for the parked save (R5) and
# has nothing left to recover from. C1..C5, E1, O5 and O6 are red on both
# (the review's P1 on the baseline, where a URL set while down is
# discarded; the drop above on the repaired tree). R1 and R2 pass on BOTH
# trees live, which the review's harness P1 did not predict: Service.
# removeSource reaches persistActive(""), and withActiveKey clears the key
# in the state the service saves on either tree; lane A's R3 (Model.
# removeSource clearing it in what IT returns) is reached by the node and
# python fixtures, not by this path. Every I and S check, D1, M2, M4, M6,
# J1..J3, E2, E3, R1..R5, O1, O3, O4, P1, P2 and T1 pass on every tree:
# controls, not discriminators. The instrument's own red is against the
# two instruments before it, not a tree: f275bde's entryKey hashed the URL
# alone (I1 reads the URL's key where the mirror names another source:
# "I1 df479b3d want 15f4dbc4") and the first repair iterated every entry
# value (I3 reads "cafebabe"). Both were driven through this arm's node
# probe with their bodies in place of harness-lib.js's, one red of seven
# each; scripts/qa-lib-test.sh drives the same three clauses on every
# commit.
#
# MODES. `check-tree` (what scripts/check.sh runs on every commit: no
# transcript, no display, node over the tree's Model.js, under 2 s) and
# `live` (the default: a transcript, both arms, and the --baseline lever;
# about 100 s). check-tree needs node and python3; live also needs cage and
# quickshell. A machine without one of them exits 77 with the reason, never
# 0, and those checks run BEFORE anything else so the reason is the first
# line out even with an empty PATH. KEY_CAGE_BIN overrides the cage binary,
# so the 77 path can be driven on a machine that has it.
#
# INTERRUPTED. INT and TERM are trapped into an exit, so cleanup() runs
# (bash runs no EXIT trap for a signal that kills it while it waits on a
# foreground child): a `timeout -s TERM` landing mid-arm leaves no shell, no
# slow-helper child, no cage, no nested socket and no work directory.
# Measured 2026-10-11; the recipe is in scripts/qa-lib-test.sh's trap list.
#
# Holds no display: everything this starts lives on the nested display cage
# creates, read from cage's own child and refused if it names the caller's
# session. It starts no quickshell on the user's session, sends no keystroke
# anywhere, reads nothing from the live install and touches nothing under
# ~/.config, ~/.cache or ~/.local/state (the harness points every XDG
# directory into its own scratch tree, which this scenario keeps apart from
# the shared harness directory so a display lane's running harness is never
# reaped by this one).
set -uo pipefail
SKIP=77
CAGE_BIN=${KEY_CAGE_BIN:-cage}
# How long the staged slow helper holds `state init` (ms): the width of the
# interruptible window O1-O4 look into. Under the service's own start-up it
# is otherwise ~100 ms wide. 8 s leaves the polling loop (bounded at 6 s)
# room to observe it and stop the shell inside it on a loaded machine.
SLOW_MS=${KEY_SLOW_MS:-8000}
MODE=${1:-}
case $MODE in
  check-tree) shift ;;
  live|"")
    MODE=live; (( $# )) && shift ;;
  -*) MODE=live ;;
  *) echo "usage: key-scenario.sh [check-tree|live] [--baseline <ref>]" >&2; exit 2 ;;
esac
BASELINE=""
while (( $# )); do
  case $1 in
    --baseline)
      [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--baseline needs a git ref, and got '${2:-}'" >&2; exit 2; }
      BASELINE=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

# ---- refusals, above the transcript and above every external command, as
# logo- and clip-scenario.sh do them: builtins only, so an empty PATH reaches
# the SKIP line and nothing else.
for tool in node python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP key-scenario: $tool is not on PATH" >&2; exit $SKIP; }
done
if [[ $MODE == live ]]; then
  for tool in "$CAGE_BIN" quickshell qs; do
    command -v "$tool" >/dev/null 2>&1 || { echo "SKIP key-scenario: $tool is not on PATH" >&2; exit $SKIP; }
  done
fi
HERE=${BASH_SOURCE[0]%/*}
[[ $HERE == "${BASH_SOURCE[0]}" ]] && HERE=.
HERE=$(cd "$HERE" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
[[ -f $HERE/harness-lib.js ]] || { echo "$HERE/harness-lib.js is missing" >&2; exit 2; }
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
LIVE_DISPLAY=${WAYLAND_DISPLAY:-wayland-1}
# This scenario's OWN harness directory, never the shared default.
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-key}
export OMARCHY_IPTV_HARNESS_DIR=$SCRATCH
PLUGIN_ROOT=$ROOT
EXPORT_DIR=""
TREE_LINE="== tree $ROOT ($(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git))"
if [[ -n $BASELINE ]]; then
  git -C "$ROOT" rev-parse --verify -q "$BASELINE^{commit}" >/dev/null \
    || { echo "--baseline '$BASELINE' does not resolve to a commit in this repository" >&2; exit 2; }
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-key-baseline.XXXXXX") || exit 2
  chmod 0700 "$EXPORT_DIR"
  if ! git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR"; then
    echo "could not export $BASELINE" >&2; rm -rf "$EXPORT_DIR"; exit 2
  fi
  [[ -f $EXPORT_DIR/Service.qml && -f $EXPORT_DIR/Model.js && -f $EXPORT_DIR/bin/omarchy-iptv ]] \
    || { echo "$BASELINE holds no Service.qml / Model.js / bin/omarchy-iptv" >&2; rm -rf "$EXPORT_DIR"; exit 2; }
  PLUGIN_ROOT=$EXPORT_DIR
  TREE_LINE="== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported to $EXPORT_DIR"
fi

if [[ $MODE == live ]]; then
  # CLAUDE.md parallel rule 7, and F-M3-1: the evidence does not live in
  # whoever remembered to keep stdout. Not in check-tree: a gate step may
  # neither print a path nobody asked for nor leave a file behind.
  qa_transcript_start key || exit 2
fi
echo "$TREE_LINE"
echo "== mode $MODE   plugin tree $PLUGIN_ROOT   instrument $HERE/harness-lib.js   caller's display $LIVE_DISPLAY (never driven)"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-key.XXXXXX") || exit 2
chmod 0700 "$WORK"
T_START=$(date +%s.%N)
elapsed() { python3 -c 'import sys; print("%.1f" % (float(sys.argv[1]) - float(sys.argv[2])))' "$(date +%s.%N)" "$T_START"; }

# Every process this scenario starts, by the pid bash handed it or the pid
# the process wrote itself (cage's child, run.sh's qs.pid). Nothing here is
# found by a pattern that could match this shell.
CAGE_PID=""; CAGE_CHILD=""; SHELL_STARTED=0; NESTED=""; ORPHANS=""
kill_pid() { [[ -n ${1:-} ]] && kill -0 "$1" 2>/dev/null && { kill -TERM "$1" 2>/dev/null; wait "$1" 2>/dev/null; }; return 0; }
cleanup() {
  (( SHELL_STARTED )) && env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" reap >/dev/null 2>&1
  # The slow helper's sleeping child survives its parent's SIGKILL (O4): it
  # was recorded by pid before the kill and is not ours to `wait` for.
  local p; for p in $ORPHANS; do kill -KILL "$p" 2>/dev/null; done
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  kill_pid "$CAGE_PID"
  [[ -n ${EXPORT_DIR:-} && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  [[ -n ${WORK:-} && -d $WORK ]] && rm -rf "$WORK"
  return 0
}
trap cleanup EXIT
# A signal while this shell waits on a foreground child runs no EXIT trap;
# an exit does (clip-scenario.sh measured the stranded cage, shell and socket
# without these two lines).
trap 'exit 130' INT
trap 'exit 143' TERM

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL $1${2:+ -- $2}"; }
# One assertion, one line at column zero (inside a function, two spaces),
# labelled by its letter and number, so the floor at the foot can be counted
# by recipe.
ck() { local label=$1 got=$2 want=$3; [[ $got == "$want" ]] && pass "$label: $want" || fail "$label" "got [$got], want [$want]"; }

# ------------------------------------------------------- the instrument arm
instrument() {
  local out seams
  echo "== instrument arm: harness-lib.js entryKey over $PLUGIN_ROOT/Model.js ($(elapsed) s)"
  # The probe hands the instrument the tree's own Model and prints one
  # `<label> <answer>` line per case. URLs are fixture paths under $WORK and
  # never reach stdout: the answers are keys, "" or names.
  cat >"$WORK/probe.js" <<'JS'
const M = require(process.argv[2])
const H = require(process.argv[3])
const url = process.argv[4]
const other = process.argv[5]
const key = M.sourceKey(M.normalizeSourceUrl(url, { origin: "cli" }))
const otherKey = M.sourceKey(M.normalizeSourceUrl(other, { origin: "cli" }))
const show = (v) => v === "" ? "(empty)" : String(v)
console.log("KEY " + key + " " + otherKey)
console.log("I1 " + show(H.entryKey(M, { id: "x", sourceKey: otherKey, playlistUrl: url })) + " want " + otherKey)
console.log("I2 " + show(H.entryKey(M, { id: "x", playlistUrl: url })) + " want " + key)
console.log("I3 " + show(H.entryKey(M, { id: "x", mpvArgs: "deadbeef", label: "0123abcd", activeKey: "cafebabe", key: "12345678", barLabelMaxWidth: 180 })))
console.log("I4 " + show(H.entryKey(M, { id: "x", sourceKey: "", playlistUrl: url })) + " want " + key)
console.log("I5 " + show(H.entryKey(M, { id: "x", sourceKey: "DEADBEEF", playlistUrl: url })) + " want " + key)
let i6
try { i6 = show(H.entryKey(M, M.findBarEntry({ layout: { right: ["io.github.other"] } }, "io.github.rmcdavid.iptv"))) } catch (e) { i6 = "threw " + e }
console.log("I6 " + i6)
console.log("I7 " + JSON.stringify(H.entryKeyNames({ id: "x", playlistUrl: url, sourceKey: key, epgUrl: other, showLogos: false })))
JS
  out=$(node "$WORK/probe.js" "$PLUGIN_ROOT/Model.js" "$HERE/harness-lib.js" "$WORK/fixtures/a.m3u" "$WORK/fixtures/b.m3u" 2>&1)
  line() { printf '%s\n' "$out" | grep -a "^$1 " | head -1 | cut -d' ' -f2-; }
  local k1 k2; read -r k1 k2 <<<"$(line KEY)"
  if [[ ! $k1 =~ ^[0-9a-f]{8}$ || ! $k2 =~ ^[0-9a-f]{8}$ || $k1 == "$k2" ]]; then
    echo "   the probe did not run: $out"; fail "I1 the probe ran at all"; fail "I2"; fail "I3"; fail "I4"; fail "I5"; fail "I6"; fail "I7"
  else
    ck "I1 a key beside a differing URL answers the key (sourceKey first)" "$(line I1)" "$k2 want $k2"
    ck "I2 a URL alone answers its hash" "$(line I2)" "$k1 want $k1"
    ck "I3 key-shaped values in other settings answer nothing (named candidates only)" "$(line I3)" "(empty)"
    ck "I4 an empty mirror beside a URL answers the URL's hash" "$(line I4)" "$k1 want $k1"
    ck "I5 a malformed mirror beside a URL answers the URL's hash" "$(line I5)" "$k1 want $k1"
    ck "I6 an absent entry answers nothing and does not throw" "$(line I6)" "(empty)"
    ck "I7 the key-names reader lists names sorted, id excluded, no value" "$(line I7)" '["epgUrl","playlistUrl","showLogos","sourceKey"]'
  fi
  # The seams: the live arm observes the call; this is what keeps a copy of
  # the function from being pasted back into shell.qml beside the import.
  seams=$(qa_count '^ *return HarnessLib\.entryKey\(Model, Model\.findBarEntry\(barConfig, harness\.pluginId\)\)$' "$HERE/shell.qml")
  ck "S1 shell.qml's entryKey is HarnessLib.entryKey over findBarEntry" "$seams" "1"
  seams="$(qa_count 'stored: harness\.entryKey\(fakeHost\.barConfig\), published: harness\.entryKey\(fakeShell\.barConfig\)' "$HERE/shell.qml") $(qa_count 'storedKeys: HarnessLib\.entryKeyNames\(Model\.findBarEntry\(fakeHost\.barConfig' "$HERE/shell.qml")"
  ck "S2 hostEntry reads both sides through entryKey and the names through entryKeyNames" "$seams" "1 1"
  seams="$(qa_count '^ *cp "\$HERE/harness-lib\.js" "\$root/harness-lib\.js" \|\| die' "$RUN") $(qa_count '^ *qa_same_file "\$HERE/harness-lib\.js" "\$root/harness-lib\.js"' "$RUN") $(qa_count '^import "harness-lib\.js" as HarnessLib$' "$HERE/shell.qml")"
  ck "S3 run.sh stages harness-lib.js beside Model.js and proves the copy; shell.qml imports it" "$seams" "1 1 1"
  echo "== instrument arm done ($(elapsed) s)"
}

# ------------------------------------------------------------ the shell arm
h()    { env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" "$@"; }
ipc()  { h ipc "$@" 2>/dev/null; }
svc()  { qa_field "d$1" "$(ipc state)"; }
hf()   { qa_json_field "d$1" "$(ipc hostEntry)"; }
pf()   { qa_json_field "d$1" "$(ipc pointerState)"; }
# A field of state.json on disk, through the same sentinels as the IPC reads.
sj() {
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
print(json.dumps(v) if isinstance(v, bool) else ("NOFIELD" if v is None else v))' "$STATE" "$1" 2>/dev/null \
    || printf '%s\n' "$QA_NO_FILE"
}
# The key of a URL or path, by the tree under test's own function.
key_of() { node -e 'const M = require(process.argv[1]); const n = M.normalizeSourceUrl(process.argv[2], { origin: "cli" }); process.stdout.write(n === "" ? "" : M.sourceKey(n))' "$PLUGIN_ROOT/Model.js" "$1"; }
# Does the stored entry carry a key NAME? yes | no (names, never values).
stored_has() { qa_json_field "'yes' if '$1' in d['storedKeys'] else 'no'" "$(ipc hostEntry)"; }
published_has() { qa_json_field "'yes' if '$1' in d['publishedKeys'] else 'no'" "$(ipc hostEntry)"; }
sha() { sha256sum "$1" 2>/dev/null | cut -c1-16; }
# Bounded, and it SAYS it gave up (CLAUDE.md rule 3).
wait_for() {
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ "$("$@")" == "$want" ]] && return 0
    sleep 0.1
  done
  echo "   gave up waiting ${secs}s for '$want' from: $*"
  return 1
}
wait_gone() {
  local p=$1 secs=$2 i
  for ((i = 0; i < secs * 10; i++)); do [[ ! -e $p ]] && return 0; sleep 0.1; done
  return 1
}
LOG="$SCRATCH/harness.log"
LOG_MARK=0
log_mark() { LOG_MARK=$(wc -l <"$LOG" 2>/dev/null || echo 0); LOG_MARK=${LOG_MARK:-0}; }
# Lines the CURRENT shell added that match an ERE: the log is appended to by
# every detached start, so a count is taken from the mark the last start set.
log_since() { tail -n +"$((LOG_MARK + 1))" "$LOG" 2>/dev/null | grep -acE -- "$1"; }
SHELL_PID=""
# Start a detached shell on the nested display and wait until its service has
# loaded the state and settled the cache layout. `--keep`: the seed below is
# this scenario's, and every later start must find what the previous one
# wrote. Bounded 20 s; a shell that never settles is reported, not waited on.
start_shell() {
  log_mark
  h --detach --timeout 0 --keep "$@" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  local i
  for ((i = 0; i < 200; i++)); do
    [[ $(log_since 'service loaded') -gt 0 ]] && [[ $(svc "['stateLoaded']") == true ]] && [[ $(svc "['cacheReady']") == true ]] && return 0
    sleep 0.1
  done
  echo "   the shell (pid $SHELL_PID) did not settle within 20 s: $(tail -n 3 "$WORK/start.log" | tr '\n' ' ')"
  return 1
}
# Stop it by its recorded pid (run.sh shell-stop: TERM, wait, KILL after 5 s).
stop_shell() { h shell-stop >/dev/null 2>&1; local i; for ((i = 0; i < 50; i++)); do kill -0 "$SHELL_PID" 2>/dev/null || break; sleep 0.1; done; SHELL_STARTED=0; }

# The nested compositor, as clip-scenario.sh starts and stops it (the spike
# measured that SIGTERM to cage itself is ignored for 10 s and leaves a stale
# socket; its child's exit is what ends it).
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
  NESTED=$(cat "$WORK/display" 2>/dev/null)
  CAGE_CHILD=$(cat "$WORK/child.pid" 2>/dev/null)
  if [[ -z $NESTED || -z $CAGE_CHILD ]]; then
    echo "SKIP key-scenario: cage did not bring up a nested display within 10 s ($(tr '\n' ' ' <"$WORK/cage.log" | head -c 300))" >&2
    exit $SKIP
  fi
  if [[ $NESTED == "$LIVE_DISPLAY" || $NESTED == wayland-1 ]]; then
    echo "REFUSING: cage's child reports display '$NESTED', which is the live session; nothing will be driven" >&2
    exit 2
  fi
}
STOP_VERDICT=""
cage_stop() {
  local i left=""
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  for ((i = 0; i < 50; i++)); do kill -0 "$CAGE_PID" 2>/dev/null || break; sleep 0.1; done
  if kill -0 "$CAGE_PID" 2>/dev/null; then left="$left cage($CAGE_PID)"; kill -KILL "$CAGE_PID" 2>/dev/null; fi
  wait "$CAGE_PID" 2>/dev/null; CAGE_PID=""; CAGE_CHILD=""
  for ((i = 0; i < 20; i++)); do [[ -e $REAL_RUNTIME/$NESTED ]] || break; sleep 0.1; done
  [[ -e $REAL_RUNTIME/$NESTED ]] && left="$left socket($NESTED)"
  [[ -z $left ]] && STOP_VERDICT=gone || STOP_VERDICT="left:$left"
}

# A source record for the seeded state file: fetched, so a start over it
# reads the cache rather than fetching (the migration's own shape).
record() {
  local key=$1 url=$2 label=$3 count=$4
  python3 -c 'import json, sys; print(json.dumps({"key": sys.argv[1], "url": sys.argv[2], "epgUrl": "", "kind": "file", "label": sys.argv[3], "labelCustom": False, "origin": "cli", "addedAt": 1799990000, "lastUsed": 1799990000, "fetchedAt": 1799990000, "channelCount": int(sys.argv[4]), "groupCount": 1}))' "$key" "$url" "$label" "$count"
}
# Every segment starts from ITS OWN seed: the shell stopped, the scratch
# cache and state wiped, real cache directories for A (20 channels) and C
# (7) written by the real helper, and a v2 state file holding exactly those
# two records -- with the active key the segment names, or none at all
# (the 0.13.5 shape) when it names "". Mode 0600 in 0700 directories, the
# modes the service and the helper both keep (CLAUDE.md 6).
seed() {
  local active=$1 extra=""
  (( SHELL_STARTED )) && stop_shell
  h clean >/dev/null 2>&1
  mkdir -p "$CACHE/sources/$KA" "$CACHE/sources/$KC" "$(dirname "$STATE")"
  chmod 0700 "$CACHE" "$CACHE/sources" "$CACHE/sources/$KA" "$CACHE/sources/$KC" "$(dirname "$STATE")"
  python3 "$PLUGIN_ROOT/bin/omarchy-iptv" playlist --url "$A" --cache-dir "$CACHE/sources/$KA" >/dev/null 2>&1
  python3 "$PLUGIN_ROOT/bin/omarchy-iptv" playlist --url "$C" --cache-dir "$CACHE/sources/$KC" >/dev/null 2>&1
  [[ -f $CACHE/sources/$KA/channels.json && -f $CACHE/sources/$KC/channels.json ]] || echo "   the helper did not write the seed caches"
  [[ -n $active ]] && extra=",\"activeKey\":\"$active\""
  printf '{"version":2,"cacheLayout":2,"favorites":[],"recents":[],"lastPlayed":null,"session":null,"sources":[%s,%s],"savedSearches":[],"hiddenGroups":[]%s}\n' \
    "$(record "$KA" "$A" "a-twenty" 20)" "$(record "$KC" "$C" "c-seven" 7)" "$extra" >"$STATE"
  chmod 0600 "$STATE"
  SHA_A=$(sha "$CACHE/sources/$KA/channels.json"); SHA_C=$(sha "$CACHE/sources/$KC/channels.json"); SHA_STATE=$(sha "$STATE")
}
# Into the start-up window from inside: the state loaded and the in-memory
# state naming `key` while the dirs are NOT ready. Polled at 100 ms, bounded
# at `secs`; WINDOW is "observed" or "missed" and the snapshot fields are
# left in W_* for the check that reads them. Used by D (the ~400 ms window
# the real helper leaves) and by O (the seconds the slow helper leaves).
WINDOW=""; W_DIRS=""; W_PARKED=""; W_HELD=""; W_MEMORY=""; W_LOADED=""
observe_window() {
  local key=$1 secs=$2 i ps
  WINDOW=missed
  for ((i = 0; i < secs * 10; i++)); do
    ps=$(ipc pointerState)
    W_LOADED=$(qa_json_field "d['stateLoaded']" "$ps"); W_MEMORY=$(qa_json_field "d['memoryActiveKey']" "$ps")
    W_DIRS=$(qa_json_field "d['dirsReady']" "$ps"); W_PARKED=$(qa_json_field "d['stateSavePending']" "$ps"); W_HELD=$(qa_json_field "d['pendingEntryKey']" "$ps")
    if [[ $W_LOADED == true && $W_MEMORY == "$key" ]]; then
      [[ $W_DIRS == false ]] && WINDOW=observed
      return 0
    fi
    [[ $W_LOADED == true && $W_DIRS == true ]] && return 0   # the window is over; what we saw is what we report
    sleep 0.1
  done
  return 1
}

shell_arm() {
  local i left before window orphan seed_playlist seed_key sha0 staged
  echo "== shell arm: the real Service.qml under cage (plugin tree $PLUGIN_ROOT) ($(elapsed) s)"
  cage_start 500
  # The stub compositor in front of PATH, as pip- and clip-scenario.sh do
  # it, and HYPRLAND_INSTANCE_SIGNATURE unset: the service's hyprctl probe
  # stops at `which`, and nothing can reach the user's compositor from here.
  mkdir -p "$SCRATCH/bin" && ln -sfn "$HERE/stub-hyprctl.py" "$SCRATCH/bin/hyprctl"
  h reap >/dev/null 2>&1
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT
  CACHE="$SCRATCH/cache/omarchy-iptv"
  STATE="$SCRATCH/state/omarchy-iptv/state.json"
  KA=$(key_of "$A"); KB=$(key_of "$B"); KC=$(key_of "$C"); KD=$(key_of "$D")
  echo "   keys: A $KA  B $KB  C $KC  D $KD"

  echo "== D: the adoption made at start-up, watched across the start-up dirs becoming ready ($(elapsed) s)"
  seed ""
  log_mark
  h --detach --timeout 0 --keep --playlist "$A" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  observe_window "$KA" 20 || true
  ck "D1 the first start adopts the entry's URL in memory while the state save is parked (control)" \
     "$WINDOW memory:$W_MEMORY dirs:$W_DIRS parked:$W_PARKED" "observed memory:$KA dirs:false parked:true"
  wait_for true 20 pf "['dirsReady']" >/dev/null || true
  sleep 1.0   # the parked save and the entry flush land in stateInitProc's exit; give the file its moment
  ck "D2 the adopted key survives the dirs becoming ready: in memory and in the file" \
     "dirs:$(pf "['dirsReady']") memory:$(pf "['memoryActiveKey']") file:$(sj "d.get('activeKey', 'absent')")" "dirs:true memory:$KA file:$KA"

  echo "== M: the two-source migration (entry URL, no activeKey) ($(elapsed) s)"
  seed ""
  start_shell --playlist "$A" || true
  wait_for true 10 svc "['configured']" >/dev/null || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  # The entry write is deferred behind the start-up dirs (R5); give it its
  # bound rather than reading the entry on the way past.
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  ck "M1 state.json activeKey is the entry URL's key" "$(sj "d.get('activeKey', 'absent')")" "$KA"
  ck "M2 the file still holds the two records it went in with, and so does sources()" "$(sj "len(d['sources'])") $(qa_json_field 'len(d)' "$(ipc sources)")" "2 2"
  ck "M3 the stored entry carries sourceKey = that key and no playlistUrl / epgUrl" "$(hf "['stored']") sourceKey:$(stored_has sourceKey) playlistUrl:$(stored_has playlistUrl) epgUrl:$(stored_has epgUrl)" "$KA sourceKey:yes playlistUrl:no epgUrl:no"
  ck "M4 the published entry, one write behind, still carries the URL (the host shape)" "$(hf "['published']") playlistUrl:$(published_has playlistUrl)" "$KA playlistUrl:yes"
  ck "M5 configured, 20 channels from the migrated cache, activeCache is its directory" "$(svc "['configured']") $(svc "['channels']") $(ipc activeCache)" "true 20 $CACHE/sources/$KA"
  ck "M6 neither cache was touched: no fetch ran, nothing moved" "A:$([[ $(sha "$CACHE/sources/$KA/channels.json") == "$SHA_A" ]] && echo same || echo changed) C:$([[ $(sha "$CACHE/sources/$KC/channels.json") == "$SHA_C" ]] && echo same || echo changed) fetches:$(log_since 'omarchy-iptv playlist:')" "A:same C:same fetches:0"

  echo "== J: a start over the MIGRATED shape (key in the file, key on the entry, no URL) ($(elapsed) s)"
  seed "$KA"
  start_shell --playlist none --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  sleep 1.0   # the window in which a deferred entry write would land
  ck "J1 no entry write at all" "$(log_since 'updateEntryInline')" "0"
  ck "J2 the file's key and count are unchanged (idempotent)" "$(sj "d.get('activeKey', 'absent')") $(sj "len(d['sources'])")" "$KA 2"
  ck "J3 configured with the same 20 channels" "$(svc "['configured']") $(svc "['channels']")" "true 20"

  echo "== C: a playlistUrl set while the shell was down, beside the surviving mirror (review P1, R1) ($(elapsed) s)"
  seed "$KA"
  start_shell --playlist "$B" --source-key "$KA" || true
  wait_for "$KB" 10 svc "['activeSourceKey']" >/dev/null || true
  wait_for 3 20 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  ck "C1 a record for the new URL, origin cli" "$(sj "[s['origin'] for s in d['sources'] if s['key'] == '$KB']")" "['cli']"
  ck "C2 state.json activeKey is ITS key, not the mirror's" "$(sj "d.get('activeKey', 'absent')")" "$KB"
  ck "C3 the stored entry carries the NEW key and no URL" "$(hf "['stored']") playlistUrl:$(stored_has playlistUrl)" "$KB playlistUrl:no"
  ck "C4 the history kept every record" "$(sj "len(d['sources'])")" "3"
  ck "C5 configured on it, its first fetch loaded, activeCache is its directory" "$(svc "['configured']") $(svc "['channels']") $(ipc activeCache)" "true 3 $CACHE/sources/$KB"

  echo "== E: an epgUrl set while the shell was down (R4) ($(elapsed) s)"
  seed "$KA"
  start_shell --playlist none --epg "$EPG" --source-key "$KA" || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  ck "E1 the EPG URL landed on the ACTIVE record, masked for the form" \
     "file:$(sj "'same' if [s['epgUrl'] for s in d['sources'] if s['key'] == '$KA'] == ['$EPG'] else 'other'") form:$(qa_json_field "d['epgMasked']" "$(ipc editMasked "$KA")")" \
     "file:same form:http://****@127.0.0.1:9/epg.xml?token=****&kind=x"
  ck "E2 the same write took it off the stored entry" "epgUrl:$(stored_has epgUrl) $(hf "['stored']")" "epgUrl:no $KA"
  ck "E3 no IPC reply and no harness-log line carries its credential" "$(qa_count 'u:p@|token=abc' "$LOG") $(printf '%s\n%s\n%s\n' "$(ipc editMasked "$KA")" "$(ipc sources)" "$(ipc state)" | grep -acE 'u:p@|token=abc')" "0 0"

  echo "== R: removing the active source (R3) ($(elapsed) s)"
  seed "$KA"
  start_shell --playlist none --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  before=$(sj "len(d['sources'])")
  ipc removeSource "$KA" >/dev/null
  wait_for false 10 svc "['configured']" >/dev/null || true
  wait_for '' 10 hf "['stored']" >/dev/null || true
  wait_gone "$CACHE/sources/$KA" 10 || true
  ck "R1 state.json activeKey is empty IN THE FILE" "$(sj "json.dumps(d.get('activeKey', 'absent'))")" '""'
  ck "R2 the stored entry's mirror is empty and still present" "$(qa_json_field "json.dumps(d['stored'])" "$(ipc hostEntry)") sourceKey:$(stored_has sourceKey)" '"" sourceKey:yes'
  ck "R3 unconfigured, 0 channels, no active cache" "$(svc "['configured']") $(svc "['channels']") [$(ipc activeCache)]" "false 0 []"
  ck "R4 only that cache directory is gone; the other record and its cache survive" "removed:$([[ -e $CACHE/sources/$KA ]] && echo present || echo gone) C:$([[ -f $CACHE/sources/$KC/channels.json ]] && echo present || echo gone) records:$(sj "len(d['sources'])")/$before" "removed:gone C:present records:1/2"
  stop_shell
  start_shell --playlist none --source-key "" || true
  sleep 1.0
  ck "R5 a start over that stays unconfigured with the one record (control)" "$(svc "['configured']") $(sj "json.dumps(d.get('activeKey', 'absent'))") $(sj "len(d['sources'])")" 'false "" 1'

  echo "== O: the interrupted order -- a NEW URL on the entry, the shell killed between the two writes (R5, review P2) ($(elapsed) s)"
  seed ""
  # The slow tree: the tree under test with its helper replaced by
  # fixtures/slow-helper.py, which holds `state init` for SLOW_MS and then
  # execs the real helper (bin/omarchy-iptv.real) with the same argv. Nothing
  # is stubbed: `dirsReady` simply stays false for seconds instead of ~400 ms,
  # which is the window the review's P2 lives in. rewind-scenario.sh's R16
  # stages the same shape for the same reason.
  SLOW_TREE="$WORK/slow-tree"; mkdir -p "$SLOW_TREE/bin"
  staged=1
  for f in manifest.json Model.js Service.qml Guide.qml BarWidget.qml; do cp "$PLUGIN_ROOT/$f" "$SLOW_TREE/$f" 2>/dev/null || staged=0; done
  cp -R "$PLUGIN_ROOT/contrib" "$SLOW_TREE/contrib" 2>/dev/null || true
  cp "$PLUGIN_ROOT/bin/omarchy-iptv" "$SLOW_TREE/bin/omarchy-iptv.real" 2>/dev/null || staged=0
  cp "$HERE/fixtures/slow-helper.py" "$SLOW_TREE/bin/omarchy-iptv" 2>/dev/null || staged=0
  chmod +x "$SLOW_TREE/bin/omarchy-iptv" "$SLOW_TREE/bin/omarchy-iptv.real" 2>/dev/null || true
  (( staged )) || echo "   the slow tree could not be staged from $PLUGIN_ROOT"
  sha0=$SHA_STATE
  export OMARCHY_IPTV_PLUGIN_ROOT=$SLOW_TREE OMARCHY_IPTV_SLOW_MS=$SLOW_MS OMARCHY_IPTV_SLOW_VERBS="state init"
  log_mark
  h --detach --timeout 0 --keep --playlist "$D" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  observe_window "$KD" 6 || true
  ck "O1 the window was observed from inside: state loaded, dirs not ready, save parked, memory naming the new source (control)" \
     "$WINDOW loaded:$W_LOADED dirs:$W_DIRS parked:$W_PARKED memory:$W_MEMORY" "observed loaded:true dirs:false parked:true memory:$KD"
  ck "O2 inside it the entry write WAITS for the parked state save: URL still stored, key held" \
     "playlistUrl:$(stored_has playlistUrl) held:$W_HELD" "playlistUrl:yes held:$KD"
  ck "O3 inside it state.json on disk is untouched (control)" "$([[ $(sha "$STATE") == "$sha0" ]] && echo untouched || echo written)" "untouched"
  # The seed for the restart is what the host would still HOLD: observed
  # now, before the kill, because a killed shell cannot be asked. The fake
  # host lives in memory, so this observation is the only thing that
  # survives the kill; the real host's file would survive it by itself.
  seed_playlist=none; [[ $(stored_has playlistUrl) == yes ]] && seed_playlist=$D
  seed_key=$(hf "['stored']")
  # The crash: SIGKILL by the recorded pid, the slow helper's sleeping child
  # recorded first (it is orphaned by the kill and reaped by pid below).
  orphan=$(pgrep -P "$SHELL_PID" 2>/dev/null | tr '\n' ' '); ORPHANS="$ORPHANS $orphan"
  kill -KILL "$SHELL_PID" 2>/dev/null
  for ((i = 0; i < 50; i++)); do kill -0 "$SHELL_PID" 2>/dev/null || break; sleep 0.1; done
  for p in $orphan; do kill -KILL "$p" 2>/dev/null; done
  rm -f "$SCRATCH/qs.pid"; SHELL_STARTED=0
  ck "O4 after the kill state.json is still the file the shell started from (control)" "$([[ $(sha "$STATE") == "$sha0" ]] && echo untouched || echo written) activeKey:$(sj "json.dumps(d.get('activeKey', 'absent'))")" 'untouched activeKey:"absent"'
  # The next start, on the real tree, over the entry as the host held it.
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT; unset OMARCHY_IPTV_SLOW_MS OMARCHY_IPTV_SLOW_VERBS
  echo "   restarting over the entry as stored: playlist $([[ $seed_playlist == none ]] && echo none || echo '(set)'), sourceKey '$seed_key'"
  start_shell --playlist "$seed_playlist" --source-key "$seed_key" || true
  wait_for "$KD" 10 svc "['activeSourceKey']" >/dev/null || true
  wait_for 11 20 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  ck "O5 the next start RECOVERS the new source: in the file, active, configured, fetched" \
     "record:$(sj "len([s for s in d['sources'] if s['key'] == '$KD'])") activeKey:$(sj "d.get('activeKey', 'absent')") $(svc "['configured']") $(svc "['channels']")" \
     "record:1 activeKey:$KD true 11"
  ck "O6 and the migration then completes: key on the entry, URL off it" "$(hf "['stored']") playlistUrl:$(stored_has playlistUrl)" "$KD playlistUrl:no"

  echo "== P: the console sink, then teardown ($(elapsed) s)"
  qa_leak_on_labelled 'sourceProbeFinished|sourceSwitched|sourceRemoved|updateEntryInline' "://|$WORK" "$LOG"
  case $? in 0) left=clean ;; 1) left=LEAK ;; *) left="nothing labelled to judge" ;; esac
  ck "P1 no labelled harness-log line carries a URL or a fixture path" "$left" "clean"
  ck "P2 no credential token anywhere in the harness log" "$(qa_count 'u:p@|token=abc|harness-live-cred' "$LOG")" "0"
  h reap >/dev/null 2>&1; SHELL_STARTED=0
  for ((i = 0; i < 50; i++)); do kill -0 "$SHELL_PID" 2>/dev/null || break; sleep 0.1; done
  left=""; kill -0 "$SHELL_PID" 2>/dev/null && left="shell($SHELL_PID) "
  cage_stop
  ck "T1 the shell, the compositor and the nested socket are gone" "$left$STOP_VERDICT" "gone"
  echo "== shell arm done ($(elapsed) s)"
}

# ---- fixtures: four playlists with distinct channel counts, under $WORK so a
# path in any sink is this run's. Live URLs inside them are dead loopback
# ports; one carries a synthetic credential so P2 can tell a leak from a path.
mkdir -p "$WORK/fixtures"
sed "s|__LIVE__|http://harness-live-cred:secret@127.0.0.1:9/dead/live.m3u8|g" "$HERE/fixtures/harness.m3u.in" >"$WORK/fixtures/a.m3u"
cp "$ROOT/tests/fixtures/basic.m3u" "$WORK/fixtures/b.m3u"
python3 "$ROOT/scripts/gen-playlist.py" --channels 7 --groups 2 --seed 2 --out "$WORK/fixtures/c.m3u" >/dev/null 2>&1
python3 "$ROOT/scripts/gen-playlist.py" --channels 11 --groups 3 --seed 3 --out "$WORK/fixtures/d.m3u" >/dev/null 2>&1
A="$WORK/fixtures/a.m3u"; B="$WORK/fixtures/b.m3u"; C="$WORK/fixtures/c.m3u"; D="$WORK/fixtures/d.m3u"
EPG="http://u:p@127.0.0.1:9/epg.xml?token=abc&kind=x"

instrument
[[ $MODE == live ]] && shell_arm

# The floor. A check that stops executing must turn the run red rather than
# quietly shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ *ck "[IS][0-9]' key-scenario.sh   -> 10, the instrument arm -> check-tree
#   grep -cE '^ *ck "[A-Z][0-9]' key-scenario.sh  -> 43, both arms          -> live
# Every assertion is one `ck "<letter><n> ...` line, none in a loop; the
# probe's fallback `fail` lines replace the seven I lines one for one when
# the probe does not run, so the count holds either way; the definition of
# ck() does not match the recipe. Never lower a floor to make a run green.
# scripts/check.sh's KEY_PREFLIGHT_MIN is the check-tree number plus one
# (this line), and scripts/qa-lib-test.sh asserts every join.
if [[ $MODE == check-tree ]]; then
  EXPECTED_CHECKS=10
else
  EXPECTED_CHECKS=43
fi
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  pass "the scenario ran every check it has ($ran)"
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi

if [[ -n $BASELINE ]]; then
  echo "baseline $BASELINE: on the first build (f275bde) the one discriminating red is O2 (the entry is rewritten while the state save is still parked); D2, M1, M3 and M5 pass THERE and fail on lane-key-r1 (the first build's immediate entry write plus its own-write overlay recover a known record from the start-up chmod reload by accident); C1..C5, E1, O5, O6 are red on both trees (the review's P1 on the baseline, the chmod reload drop on the repaired tree -- see STATUS in the header). Every I and S check, D1, M2, M4, M6, J1..J3, E2, E3, R1..R5, O1, O3, O4, P1, P2 and T1 pass on every tree: controls, not discriminators."
fi
echo "key-scenario: $PASS passed, $FAIL failed (mode $MODE, tree $PLUGIN_ROOT${BASELINE:+, baseline $BASELINE}, $(elapsed) s)"
(( FAIL == 0 ))
