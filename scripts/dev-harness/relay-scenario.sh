#!/bin/bash
# scripts/dev-harness/relay-scenario.sh -- D-SINK-102 observed at the sinks.
#
# D-SINK-102 is the marketplace maintainer's finding on
# omacom/omarchy-plugin-marketplace#14290 against 0.19.1 (9e006be): the
# player's destination checks could be bypassed by an HTTP redirect, an HLS
# or DASH open on another host, or a name that answered the player
# differently from the helper's lookup a moment earlier. The fix pins the
# player to a relay the helper runs as its parent (bin/helper/12-relay.py),
# which judges every connection the player makes against the address it
# connects to. tests/test_relay.py and tests/test_relay_player.py prove the
# parts; this scenario observes the whole: the SHIPPING helper's `playlist`,
# `player start` and `play`, a real headless mpv, and logging servers the
# player must never reach, which log nothing (rule 14).
#
# The rig (tests/relay_rig.py, dev branch; its docstring lists R1..R20)
# runs inside `unshare -rn`, a private network namespace whose only
# interfaces are its own loopback and a dummy one carrying 11.0.0.1 (global
# to the helper's classifier: the internet) and 10.0.0.1 (a local network),
# so a server on 127.0.0.1 is this machine. Nothing can leave the
# namespace, every address is a literal, and nothing is looked up by name.
# mpv runs with --vo=null --ao=null --force-window=no, without DISPLAY,
# WAYLAND_DISPLAY, HYPRLAND_INSTANCE_SIGNATURE or the session bus, under a
# scratch HOME, XDG tree and runtime directory -- its socket is never the
# owner's -- with a core limit of 0. Every process the rig starts it stops
# with `player stop`, and as a last resort through a pidfd whose command
# line names this run's scratch socket or this tree's relay of one of its
# players; nothing is ever signalled by ancestry or by a pattern. The crash
# journal is counted before and after, and a rise is red.
#
#   relay-scenario.sh check-tree      the gate's arm: no transcript, no file
#                                     left behind (scripts/check.sh)
#   relay-scenario.sh [live]          the same checks, with a transcript
#   ... --baseline <ref>              the same checks against <ref>'s helper
#   ... --tree <dir>                  against a prepared plugin tree
#
# `--baseline 9e006be` (0.19.1, the release the finding is against) must red
# R1..R8, R10, R11 (the sinks are reached), R12, R16, R17's relay count, R18
# and R19 (there is no relay), and leave the controls (R9, R13b, R14's
# redirect) and the teardown green. Counts in docs/QA-RESULTS.md (dev branch)
# "D-SINK-102".
#
# A machine without python3, mpv, ffmpeg, openssl, unshare, ip or
# journalctl, or one that cannot make a network namespace with a dummy
# interface, exits 77 with the reason; scripts/check.sh calls that RED
# unless RELAY_SCENARIO_SKIP_OK=1 says the machine cannot run it.
# RELAY_UNSHARE_BIN overrides the unshare binary, so the 77 path can be
# driven on a machine that has it. About 2-3 minutes; holds no display.
set -uo pipefail
SKIP=77
UNSHARE_BIN=${RELAY_UNSHARE_BIN:-unshare}
MODE=${1:-}
case $MODE in
  check-tree) shift ;;
  live|"") MODE=live; (( $# )) && shift ;;
  -*) MODE=live ;;
  *) echo "usage: relay-scenario.sh [check-tree|live] [--baseline <ref>|--tree <dir>]" >&2; exit 2 ;;
esac
BASELINE=""; TREE=""
while (( $# )); do
  case $1 in
    --baseline)
      # Refused rather than defaulted (tls-scenario.sh's reason): a dropped
      # ref would grade the current tree and call it a baseline.
      [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--baseline needs a git ref, and got '${2:-}'" >&2; exit 2; }
      BASELINE=$2; shift ;;
    --tree)
      [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--tree needs a directory, and got '${2:-}'" >&2; exit 2; }
      TREE=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[[ -n $BASELINE && -n $TREE ]] && { echo "--baseline and --tree are the same lever; pass one" >&2; exit 2; }

# ---- refusals above every external command (F-M3-18 (b)): `command -v`,
# `[[ ]]` and `echo` are builtins, so an empty PATH reaches the SKIP line.
for tool in python3 mpv ffmpeg openssl "$UNSHARE_BIN" ip journalctl readlink mktemp timeout git tar; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP relay-scenario: $tool is not on PATH" >&2; exit $SKIP; }
done
ns_why=$(timeout -k 2 10 "$UNSHARE_BIN" -rn ip link add d0 type dummy 2>&1) \
  || { echo "SKIP relay-scenario: cannot make a private network namespace with a dummy interface here (\`$UNSHARE_BIN -rn ip link add d0 type dummy\`: ${ns_why:-no reason given}); the provider has to be a global address that exists nowhere else" >&2; exit $SKIP; }
HERE=${BASH_SOURCE[0]%/*}
[[ $HERE == "${BASH_SOURCE[0]}" ]] && HERE=.
HERE=$(cd "$HERE" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
[[ -f $ROOT/tests/relay_rig.py ]] || { echo "$ROOT/tests/relay_rig.py is missing" >&2; exit 2; }
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
PLUGIN_ROOT=$ROOT
EXPORT_DIR=""
TREE_LINE="== tree $ROOT ($(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git))"
if [[ -n $TREE ]]; then
  PLUGIN_ROOT=$(cd "$TREE" 2>/dev/null && pwd) || { echo "--tree $TREE is not a directory I can enter" >&2; exit 2; }
  [[ -f $PLUGIN_ROOT/bin/omarchy-iptv ]] || { echo "--tree $PLUGIN_ROOT holds no bin/omarchy-iptv" >&2; exit 2; }
  TREE_LINE="== prepared tree $PLUGIN_ROOT"
fi
if [[ -n $BASELINE ]]; then
  git -C "$ROOT" rev-parse --verify -q "$BASELINE^{commit}" >/dev/null \
    || { echo "--baseline '$BASELINE' does not resolve to a commit in this repository" >&2; exit 2; }
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/oiptv-relay-base.XXXXXX") || exit 2
  chmod 0700 "$EXPORT_DIR"
  if ! git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR"; then
    echo "could not export $BASELINE" >&2; rm -rf "$EXPORT_DIR"; exit 2
  fi
  [[ -f $EXPORT_DIR/bin/omarchy-iptv ]] || { echo "$BASELINE holds no bin/omarchy-iptv" >&2; rm -rf "$EXPORT_DIR"; exit 2; }
  PLUGIN_ROOT=$EXPORT_DIR
  TREE_LINE="== baseline tree $BASELINE ($(qa_ref_commit "$ROOT" "$BASELINE")) exported"
fi

if [[ $MODE == live ]]; then
  # Parallel rule 7: the evidence is the transcript, printed first. Not in
  # check-tree: a gate step may neither print a path nobody asked for nor
  # leave a file behind.
  qa_transcript_start relay || exit 2
fi
echo "$TREE_LINE"
echo "== mode $MODE   helper $PLUGIN_ROOT/bin/omarchy-iptv   rig $ROOT/tests/relay_rig.py"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/oiptv-relay.XXXXXX") || exit 2
# The scratch runtime is its own short directory: the player's socket with
# its relay's suffix has to fit sun_path, and WORK under a long TMPDIR need not.
RT=$(mktemp -d "${TMPDIR:-/tmp}/rr.XXXXXX") || exit 2
chmod 0700 "$WORK" "$RT"
cleanup() {
  # The rig stops its own players before it exits, TERM included; what is
  # left here is files.
  [[ -n ${WORK:-} && -d $WORK ]] && rm -rf "$WORK"
  [[ -n ${RT:-} && -d $RT ]] && rm -rf "$RT"
  [[ -n ${EXPORT_DIR:-} && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# F-HARNESS-20: this driver's own processes get a home inside WORK.
qa_harness_home "$WORK" || exit 2

journal() { journalctl -o json MESSAGE_ID=fc2e22bc6ee647b6b90729ab34a250b1 2>/dev/null | wc -l | tr -d ' '; }
J0=$(journal)
OUTER=$(readlink /proc/self/ns/net)
env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u DBUS_SESSION_BUS_ADDRESS -u MPV_HOME \
  timeout -k 20 900 "$UNSHARE_BIN" -rn python3 -I "$ROOT/tests/relay_rig.py" \
  --tree "$PLUGIN_ROOT" --work "$WORK" --runtime "$RT" --outer-netns "$OUTER" 2>&1 | tee "$WORK/rig.log"
rig_rc=${PIPESTATUS[0]}
(( rig_rc == SKIP )) && exit $SKIP
(( rig_rc == 2 )) && exit 2
J1=$(journal)
if [[ $J0 == "$J1" ]]; then
  echo "PASS the crash journal did not move ($J0 before, $J1 after)"
else
  echo "FAIL the crash journal moved ($J0 before, $J1 after): a player or a tool crashed"
fi
rig_pass=$(grep -c '^PASS' "$WORK/rig.log" || true)
rig_fail=$(grep -c '^FAIL' "$WORK/rig.log" || true)
total_pass=$(( rig_pass + (J0 == J1 ? 1 : 0) ))
total_fail=$(( rig_fail + (J0 == J1 ? 0 : 1) ))
(( rig_rc != 0 && rig_fail == 0 )) && { echo "FAIL the rig exited $rig_rc with no FAIL line"; total_fail=$((total_fail + 1)); }
echo "relay-scenario: $total_pass passed, $total_fail failed (rig exit $rig_rc)"
(( total_fail == 0 ))
