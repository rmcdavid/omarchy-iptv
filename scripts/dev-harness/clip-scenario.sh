#!/bin/bash
# scripts/dev-harness/clip-scenario.sh -- D-CLIP-1, observed at the sink: does
# a foreign clipboard offer make the SHELL read it?
#
#   clip-scenario.sh check-tree              the probe arm ONLY; run by check.sh
#   clip-scenario.sh [live] [--baseline REF] the probe arm, then the shell arm
#
# THE FINDING. Every editable QtQuick TextInput subscribes to
# QClipboard::dataChanged, and on the RELEASED Qt 6.11.2 that slot calls
# QMimeData::text(), which on Wayland reads the whole foreign offer through a
# pipe -- 1 s timeout per read, no total byte limit, no deadline --
# synchronously, on the main thread of the process that owns the field. For
# this plugin that process is omarchy-shell, and the field is any unmasked
# field of the first-run / add-source form while the form is open. Measured
# by the lead with a throwaway client under the user's compositor: a 100 MB
# text/plain offer grew one editable TextField by 238 MB within 600 ms;
# readOnly true grew by nothing; a window with no field made zero pipe reads.
# Attributed by a gdb catchpoint on pipe2: q_canPasteChanged ->
# QMimeData::text(). Raised by the marketplace maintainer against the shipped
# 0.13.4 (d55149b) on omacom/omarchy-plugin-marketplace#11077; the lead's
# write-up is docs/QA-RESULTS.md under "Sixth maintainer finding, 2026-10-11".
#
# THE FIX (lane A, 44b250b): every form field is `readOnly: true`, always, and
# the plugin edits the model value itself (Guide.qml handleFormKey through
# Model.editInsert / editDelete); paste is the out-of-process path only.
# Its second half (R8, 51866a3): the shell never holds more than the bounded
# reply. Service.qml requestClipboard runs the helper's `clipboard` verb as
# argv; the HELPER runs wl-paste, reads at most Model.CLIPBOARD_MAX_BYTES
# (32 KiB) of it, terminates the child at the cap, and answers one JSON line
# cut at Model.CLIPBOARD_MAX_CHARS, which the guide then fits to the field's
# capacity. Before R8 the shell ran wl-paste itself and collected the WHOLE
# offer before cutting it (the review measured +298 MB on one Ctrl+V over a
# 100 MB offer, most of it kept); that is what L10 below observes.
#
# WHAT THIS SCENARIO OBSERVES, AND HOW. Two arms, both inside a NESTED
# headless compositor (cage, docs/SPIKE-CAGE-HEADLESS.md) on its own display,
# so the user's clipboard is never offered to, read from, or replaced:
#
#   the probe arm (check-tree, and the preflight of live). The lead's three
#   probes, verbatim from spikes/clip-offer/ (one editable TextField, one
#   read-only TextField, a window with no field), each started on the nested
#   display, offered OFFER_MB of text/plain by a foreign producer (wl-copy on
#   the same display), and sampled for resident set from outside. This is the
#   fact the fix rests on, re-measured on THIS machine on every commit: a
#   read-only control reads nothing, an editable one reads everything.
#
#   the shell arm (live). The dev-harness fake shell with the REAL Guide.qml
#   and Service.qml under the same cage, in the harness-only floating window
#   so the guide maps and takes the keyboard. Started with no playlist, the
#   guide opens straight into the first-run form with the playlist field
#   focused (UX-SOURCES 1.2) -- confirmed over IPC, not assumed. Then the
#   same foreign producer offers OFFER_MB on that display; the shell's RSS is
#   sampled for 1 s before and 3 s after, and twelve IPC round trips are
#   timed back to back from the instant of the offer. Then the positive
#   controls: typing through the harness `key` verb (wtype on the nested
#   display) still changes the MODEL value of the read-only field, and a
#   paste through Ctrl+V / Shift+Insert lands capped at the tree's own
#   Model.formCapacity, read from the tree under test by calling it. Then
#   the user-initiated half (R8): a Ctrl+V over an OFFER_MB offer itself,
#   with the shell's RSS sampled across the paste and the helper child
#   watched by pid: the paste lands at formCapacity and the shell grows by
#   less than the band, because the helper, not the shell, is the process
#   that reads the clipboard, and it reads 32 KiB of it.
#
# THE SEAT, and why the editable probe is a control and not only a finding.
# cage's headless seat has no keyboard, and a compositor hands
# wl_data_device.selection only to the client holding KEYBOARD focus -- so
# with nothing on the seat NOT EVEN the editable control reads (+0 on both
# probes; found by lane A re-running the lead's rig under cage). A virtual
# keyboard (wtype, held open on the nested display across every offer) is
# what attaches one. Without it a baseline run passes vacuously, which is
# why P3 (the editable probe grew by at least the payload) is asserted in
# both arms: it proves the rig delivers offers at all, so a +0 elsewhere
# means "did not read" and not "was never offered".
#
#   P1  the nested display came up and is not the caller's session
#   P2  a consumer on that display reads the whole offer (wl-paste byte count
#       equals the payload): the producer serves what it offers
#   P3  the editable probe grew by at least OFFER_MB    <- reads everything;
#                                                          the rig's control
#   P4  the read-only probe grew by less than PROBE_BAND_MB   <- reads nothing
#   P5  the no-field probe grew by less than PROBE_BAND_MB    <- nothing below
#                                                          the control reads
#   P6  every probe, the producer, the keyboard and the compositor are gone
#       and the nested socket is removed (parallel rule 3: by recorded pid)
#   L1  the shell came up into the first-run form with `playlist` focused
#   L2  the keyboard is held by a TextField of the guide, in a floating window
#   L3  typing through the harness key verb lands in the model value
#       (the form edits itself; the control is read-only)   <- positive control
#   L4  the shell's RSS grew by less than SHELL_BAND_MB after the offer
#   L5  the slowest of twelve IPC round trips after the offer is under
#       IPC_BOUND_MS: the main thread was never held by the read. Asserted
#       on the tree under test; on a --baseline it is REPORTED, not asserted
#       (DR-B2: whether a call lands inside the read is timing)
#   L6  the offer alone changed nothing in the field
#   L7  Shift+Insert pastes a 10-byte offer through the process path
#   L8  Ctrl+V pastes a 5,000-byte offer and it lands at exactly
#       Model.formCapacity("playlist") of the tree under test
#   L9  no clipboard helper and no wl-paste is left under the shell after
#       the paste answered (the helper's child counted as well as the
#       shell's: since R8 wl-paste is the helper's child, not the shell's)
#   L10 Ctrl+V over the OFFER_MB offer itself lands at formCapacity and
#       grows the shell by less than SHELL_BAND_MB: the byte bound (R8)
#   L11 no clipboard helper and no wl-paste is left under the shell after
#       THAT paste, the one the helper had to cut short
#   L12 the harness log carries no run of the payload (the console sink)
#   L13 the shell, the keyboard, the producer and the compositor are gone
#       (the shell through `run.sh reap`: by its recorded pid, then run.sh's
#       pattern sweep scoped to this scenario's own harness directory; the
#       rest by the pid this scenario recorded)
#
# RULE 11, THE RED RUNS. `--baseline <ref>` exports that tree and runs its
# Guide.qml / Service.qml / Model.js / bin through the same rig (the harness
# shell.qml is this tree's; it hands the floating-window property in as an
# initial property, which both baselines below already carry). Every P check
# passes on every tree (the probes are the lead's and do not involve the
# plugin), and so do L1, L2, L3, L6, L7, L8, L9, L11, L12 and L13: controls,
# not discriminators. Measured 2026-10-11, recipe and both counts in the
# footer the run prints:
#   --baseline d55149b (the shipped 0.13.4, fields editable): L4 is RED,
#     +240..+297 MB on a 100 MB offer (about 2.5x the payload; peak
#     589..642 MB over seven runs), the finding at the sink; and L10 is RED,
#     +122 MB, the editable field pasting natively over the offer. L5 is
#     reported: 673..746 ms when one of the twelve round trips landed inside
#     the read (seven runs of seven, against 56..81 ms around it), which
#     the header does not promise.
#   --baseline 96f5261 (fields read-only, the shell still running wl-paste
#     itself): L4 passes, +0, and L10 is RED, +304..+310 MB on one Ctrl+V
#     over the 100 MB offer with most of it kept after the paste -- the shell
#     collected the whole offer and cut it afterwards. The fixed tree
#     answers +0 with the helper's peak at 32 MB and gone afterwards.
# The discriminators are L4 and L10; L5 is the stall half of the
# maintainer's finding, observed when timing allows and asserted on the
# tree under test always.
#
# MODES. `check-tree` (what scripts/check.sh runs on every commit: no
# transcript, nothing on the user's session, the probe arm alone over a
# 25 MB offer, about 9 s) and `live` (the default: a transcript, both arms
# over 100 MB, and the --baseline lever). The gate's offer is a quarter of
# the live one (DR-B1): a 100 MB editable probe holds about 300 MB while it
# reads, which on a machine short of memory could be killed mid-read and
# turn P3 red for the wrong reason; 25 MB keeps the gate's transient under
# 100 MB and the probe still reads every byte of it (the bands below are
# restated for both sizes). CLIP_OFFER_MB overrides either.
# Both modes need cage, wl-copy, wl-paste, wtype, python3, node and the qml
# runtime; a machine without one of them exits 77 with the reason, never 0,
# and those checks run BEFORE anything else so the reason is the first line
# out even with an empty PATH. A cage that does not bring up a display within
# 10 s is the same 77: the sink cannot be observed here. CLIP_CAGE_BIN and
# CLIP_QML_BIN override the two binaries; they exist so the 77 path can be
# driven on a machine that has both.
#
# INTERRUPTED. INT and TERM are trapped into an exit, so cleanup() runs
# (bash runs no EXIT trap for a signal that kills it while it waits on a
# foreground child): `timeout -s TERM 19 clip-scenario.sh` lands after L3
# with a detached shell, a cage and a nested socket up, and leaves none of
# them. Measured 2026-10-11 both ways -- with the EXIT trap alone that run
# stranded `cage -- .../child.sh`, `quickshell -p .../omarchy-iptv-clip/root`,
# `sleep 120`, `wayland-0` and the work directory (the review's finding,
# and player-, rewind- and tls-scenario.sh had the two lines already).
#
# Holds no display: everything this starts lives on the nested display cage
# creates, read from cage's own child and refused if it names the caller's
# session. It starts no quickshell on the user's session, sends no keystroke
# there, reads nothing from the live install and touches nothing under
# ~/.config, ~/.cache or ~/.local/state: the harness gives the shell its own
# HOME and XDG directories in its scratch tree, which this scenario keeps apart
# from the shared harness directory so a display lane's running harness is
# never reaped by this one, and this driver's own processes get a home inside
# its work directory (F-HARNESS-20; see the call after WORK is made).
set -uo pipefail
SKIP=77
CAGE_BIN=${CLIP_CAGE_BIN:-cage}
QML_BIN=${CLIP_QML_BIN:-/usr/lib/qt6/bin/qml}
# The payload, in MiB, by mode (DR-B1; see MODES). 100 is the lead's and the
# maintainer's number and the live default; 25 is the gate's.
OFFER_MB_CHECK_TREE=25
OFFER_MB_LIVE=100
OFFER_MB=${CLIP_OFFER_MB:-}
# Bands and bounds, all measured 2026-10-11 under cage on this machine and
# recorded in spikes/clip-offer/README.md: a probe that reads nothing and the
# fixed shell both grew by exactly 0 MB in every run, at either size; the
# editable probe by 235..307 MB on 100 MB and, sampled at 20 ms, by
# 58..80 MB on 25 MB over seven runs (a transient of about 80 ms, 2.3..3.2x
# the payload, settling to +36 MB kept, 1.4x -- the probes sample at 20 ms
# so the transient is what P3 sees and never the settled tail alone); the
# baseline shell by 240..297 MB on 100 MB; an IPC round trip is 55..159 ms
# on the fixed tree (the first call carries a process cold start) and the
# baseline's stalled call was 673..746 ms. The shell band is wider than the
# probe band because the shell has timers and a service behind it; both are
# a small fraction of the payload, which is the defect's signature. L10
# (the paste) uses the shell band too: the helper's reply is at most
# 32 KiB, so a shell that grew by the band over a paste would have read the
# offer itself; the fixed tree measured +0, +0 and +7 MB over three runs
# with the helper's own peak at 32 MB.
PROBE_BAND_MB=8
SHELL_BAND_MB=16
HELPER_BAND_MB=${HELPER_BAND_MB:-64}
IPC_BOUND_MS=400
MODE=${1:-}
case $MODE in
  check-tree) shift ;;
  live|"")
    MODE=live; (( $# )) && shift ;;
  -*) MODE=live ;;
  *) echo "usage: clip-scenario.sh [check-tree|live] [--baseline <ref>]" >&2; exit 2 ;;
esac
if [[ -z $OFFER_MB ]]; then
  [[ $MODE == check-tree ]] && OFFER_MB=$OFFER_MB_CHECK_TREE || OFFER_MB=$OFFER_MB_LIVE
fi
[[ $OFFER_MB =~ ^[1-9][0-9]*$ ]] || { echo "CLIP_OFFER_MB must be a positive integer (MiB), not '$OFFER_MB'" >&2; exit 2; }
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
# logo-scenario.sh does them: `command -v`, `[[ -x ]]` and `echo` are
# builtins, so an empty PATH reaches the SKIP line and nothing else.
for tool in python3 node wl-copy wl-paste wtype "$CAGE_BIN"; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP clip-scenario: $tool is not on PATH" >&2; exit $SKIP; }
done
[[ -x $QML_BIN ]] || { echo "SKIP clip-scenario: $QML_BIN is not here (qt6-declarative)" >&2; exit $SKIP; }
HERE=${BASH_SOURCE[0]%/*}
[[ $HERE == "${BASH_SOURCE[0]}" ]] && HERE=.
HERE=$(cd "$HERE" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
SPIKE="$HERE/spikes/clip-offer"
for f in editable.qml readonly.qml nofield.qml; do
  [[ -f $SPIKE/$f ]] || { echo "$SPIKE/$f is missing" >&2; exit 2; }
done
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
# The caller's own display, which the nested one must never be.
LIVE_DISPLAY=${WAYLAND_DISPLAY:-wayland-1}
# This scenario's OWN harness directory, not the shared default: `run.sh
# reap` kills by a pattern scoped to this directory, and a display lane's
# harness in the shared one must survive a clip run on the same machine.
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-clip}
export OMARCHY_IPTV_HARNESS_DIR=$SCRATCH
# F-HARNESS-20: this driver's own processes (its helper runs, probes, mpv)
# get the harness's HOME as well, not only what run.sh starts. Exports only.
qa_harness_home "$SCRATCH" || exit 2
PLUGIN_ROOT=$ROOT
EXPORT_DIR=""
TREE_LINE="== tree $ROOT ($(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git))"
if [[ -n $BASELINE ]]; then
  git -C "$ROOT" rev-parse --verify -q "$BASELINE^{commit}" >/dev/null \
    || { echo "--baseline '$BASELINE' does not resolve to a commit in this repository" >&2; exit 2; }
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-clip-baseline.XXXXXX") || exit 2
  chmod 0700 "$EXPORT_DIR"
  if ! git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR"; then
    echo "could not export $BASELINE" >&2; rm -rf "$EXPORT_DIR"; exit 2
  fi
  [[ -f $EXPORT_DIR/Guide.qml ]] && qa_model_files "$EXPORT_DIR" >/dev/null || { echo "$BASELINE holds no Guide.qml / model" >&2; rm -rf "$EXPORT_DIR"; exit 2; }
  PLUGIN_ROOT=$EXPORT_DIR
  export OMARCHY_IPTV_PLUGIN_ROOT=$EXPORT_DIR
  TREE_LINE="== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported to $EXPORT_DIR"
fi

if [[ $MODE == live ]]; then
  # CLAUDE.md parallel rule 7, and F-M3-1: the evidence does not live in
  # whoever remembered to keep stdout. Not in check-tree: a gate step may
  # neither print a path nobody asked for nor leave a file behind.
  qa_transcript_start clip || exit 2
fi
echo "$TREE_LINE"
echo "== mode $MODE   offer ${OFFER_MB} MiB   bands: probe <${PROBE_BAND_MB} MB, shell <${SHELL_BAND_MB} MB, ipc <${IPC_BOUND_MS} ms   caller's display $LIVE_DISPLAY (never driven)"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-clip.XXXXXX") || exit 2
chmod 0700 "$WORK"
# F-HARNESS-20, the sibling this scenario carried. The probe arm's own
# processes -- cage and the qml probes -- write a mesa shader cache, a Qt
# cache ("QtProject/Qml Runtime") and an fcitx directory into whatever home
# they are given. Measured 2026-10-13 by running the check-tree of dev
# 8c8862f with a decoy HOME and decoy XDG directories: all three landed in the
# decoy, which on an ordinary run is the developer's REAL ~/.cache and
# ~/.config, on every gate run -- while the header above said this scenario
# touched nothing there. The call at the top moved them into $SCRATCH, which a
# check-tree run then left behind (a gate step may leave nothing). So the
# driver's home goes into WORK, which cleanup() removes; run.sh, in live
# mode, still hands the shell the harness's own home under $SCRATCH.
qa_harness_home "$WORK" || exit 2
T_START=$(date +%s.%N)
elapsed() { python3 -c 'import sys; print("%.1f" % (float(sys.argv[1]) - float(sys.argv[2])))' "$(date +%s.%N)" "$T_START"; }

# Every process this scenario starts, by the pid bash handed it (each is a
# direct child: no wrapper, nothing setsid'd by us, so `$!` IS the process),
# or by the pid the process wrote itself (cage's child). Nothing here is
# found by pattern.
CAGE_PID=""; CAGE_CHILD=""; WTYPE_PID=""; PRODUCER_PID=""; PROBE_PID=""; SAMPLER_PID=""; SHELL_STARTED=0
NESTED=""; T_OFFER=""; KEY_RC=0
kill_pid() { [[ -n ${1:-} ]] && kill -0 "$1" 2>/dev/null && { kill -TERM "$1" 2>/dev/null; wait "$1" 2>/dev/null; }; return 0; }
cleanup() {
  (( SHELL_STARTED )) && env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" reap >/dev/null 2>&1
  kill_pid "$PROBE_PID"; kill_pid "$PRODUCER_PID"; kill_pid "$WTYPE_PID"; kill_pid "$SAMPLER_PID"
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  kill_pid "$CAGE_PID"
  [[ -n ${EXPORT_DIR:-} && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  [[ -n ${WORK:-} && -d $WORK ]] && rm -rf "$WORK"
  return 0
}
trap cleanup EXIT
# A signal while this shell waits on a foreground child runs no EXIT trap;
# an exit does. Without these two lines a `timeout -s TERM` mid-run left the
# detached shell, the cage, `sleep 120`, the nested socket and the work
# directory behind (measured; see INTERRUPTED above).
trap 'exit 130' INT
trap 'exit 143' TERM

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL $1${2:+ -- $2}"; }
# One assertion, one line, labelled P<n> or L<n>, so the floor at the foot
# can be counted by recipe.
ck() { local label=$1 got=$2 want=$3; [[ $got == "$want" ]] && pass "$label: $want" || fail "$label" "got [$got], want [$want]"; }

# ---- the nested compositor. cage's child writes the display cage gave it
# and its own pid, then sleeps under a bound; cage exits when its child
# does, so teardown is "kill the child by that pid" (the spike measured that
# SIGTERM to cage itself is ignored for 10 s and leaves a stale socket).
# `timeout` around cage is the hard bound on the whole arm.
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
    echo "SKIP clip-scenario: cage did not bring up a nested display within 10 s ($(tr '\n' ' ' <"$WORK/cage.log" | head -c 300))" >&2
    exit $SKIP
  fi
  # The one refusal that matters more than any check: the display we are
  # about to drive is not the one the user is sitting at.
  if [[ $NESTED == "$LIVE_DISPLAY" || $NESTED == wayland-1 ]]; then
    echo "REFUSING: cage's child reports display '$NESTED', which is the live session; nothing will be driven" >&2
    exit 2
  fi
  # The virtual keyboard, held across every offer this arm makes (see THE
  # SEAT above). Its own bound is the arm's.
  WAYLAND_DISPLAY=$NESTED wtype -s $((secs * 1000)) '' >"$WORK/wtype.log" 2>&1 &
  WTYPE_PID=$!
  sleep 0.3
}
# Teardown by pid, then the verdict in STOP_VERDICT: "gone" when the
# keyboard, the child, cage and the socket are all gone within the bound,
# else what survived. Called in the MAIN shell, never in `$(...)`: a
# subshell cannot `wait` for the parent's child, so cage would sit as a
# zombie that `kill -0` still answers for, and the verdict would be wrong.
STOP_VERDICT=""
cage_stop() {
  local i left=""
  kill_pid "$WTYPE_PID"; WTYPE_PID=""
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  for ((i = 0; i < 50; i++)); do kill -0 "$CAGE_PID" 2>/dev/null || break; sleep 0.1; done
  if kill -0 "$CAGE_PID" 2>/dev/null; then left="$left cage($CAGE_PID)"; kill -KILL "$CAGE_PID" 2>/dev/null; fi
  wait "$CAGE_PID" 2>/dev/null; CAGE_PID=""; CAGE_CHILD=""
  for ((i = 0; i < 20; i++)); do [[ -e $REAL_RUNTIME/$NESTED ]] || break; sleep 0.1; done
  [[ -e $REAL_RUNTIME/$NESTED ]] && left="$left socket($NESTED)"
  [[ -z $left ]] && STOP_VERDICT=gone || STOP_VERDICT="left:$left"
}

rss_kb() { awk '/VmRSS/ { print $2 }' "/proc/$1/status" 2>/dev/null; }
# Bounded (10 s): two samples 300 ms apart within 512 KB of each other, and
# past the toolkit's startup, so a growth measured from here is the offer's
# and not Qt mapping its first window (the lead's no-field row grew 52 MB at
# startup and nothing after; measured at the catchpoint, not assumed).
settle() {
  local pid=$1 a b i
  for ((i = 0; i < 33; i++)); do
    a=$(rss_kb "$pid"); sleep 0.3; b=$(rss_kb "$pid")
    [[ -n $a && -n $b && $a -gt 50000 ]] && (( b - a < 512 && a - b < 512 )) && return 0
  done
  echo "   (rss of $pid never settled within 10 s; the growth below is measured anyway)"
  return 1
}
# The foreign producer: `bytes` of one letter (A unless given) as text/plain
# on the nested display, never written to disk. `--foreground` keeps wl-copy
# as our direct child, and `$!` of a background pipeline is its LAST
# command, so this pid is wl-copy's.
producer_start() {
  local bytes=$1 letter=${2:-A}
  python3 -c 'import sys; sys.stdout.write(sys.argv[2] * int(sys.argv[1]))' "$bytes" "$letter" \
    | WAYLAND_DISPLAY=$NESTED wl-copy --foreground --type text/plain >/dev/null 2>"$WORK/wl-copy.err" &
  PRODUCER_PID=$!
  T_OFFER=$(date +%s.%N)
}
producer_stop() { kill_pid "$PRODUCER_PID"; PRODUCER_PID=""; }
# Peak RSS over `n` samples 20 ms apart, printed as "before peak growth" in
# MB. The sampler is this shell, not a subshell, so nothing to reap. 20 ms
# and not 100: a 25 MB read is a transient of about 80 ms (0, 15, 37, 43,
# 78, then 36 MB kept, measured 2026-10-11 at 20 ms), and a sampler at
# 100 ms saw +36..+80 over four gate-sized runs depending on where its one
# sample fell. The growth P3 asserts is the read's, not the sampler's luck.
sample_peak() {
  local pid=$1 n=$2 before=$3 peak=$3 i v
  for ((i = 0; i < n; i++)); do v=$(rss_kb "$pid"); [[ -n $v && $v -gt $peak ]] && peak=$v; sleep 0.02; done
  printf '%d %d %d\n' $((before / 1024)) $((peak / 1024)) $(((peak - before) / 1024))
}
# The shell arm's sampler: `n` samples 100 ms apart of one pid's RSS, with a
# timestamp each, into a file, CONCURRENTLY with whatever the main shell does
# meanwhile (the IPC loop). A subshell child of this shell, so `wait` reaps
# it and cleanup knows its pid. The probes sample inline instead: nothing
# else happens during their window.
sampler_start() {
  local pid=$1 n=$2 file=$3
  ( for ((i = 0; i < n; i++)); do printf '%s %s\n' "$(date +%s.%N)" "$(rss_kb "$pid")"; sleep 0.1; done ) >"$file" 2>/dev/null &
  SAMPLER_PID=$!
}
# From the sample file and T_OFFER: "before peak growth last_growth_ms
# window_ms" in MB, where before is the last sample taken before the offer
# and peak the highest after it; last_growth_ms is when the RSS last sat
# above before, and window_ms is when the last sample was taken, so the
# line that prints these says how long the shell was watched rather than
# how long it was meant to be.
sampler_report() {
  python3 - "$1" "$T_OFFER" <<'PYRPT'
import sys
rows = [l.split() for l in open(sys.argv[1]) if len(l.split()) == 2]
t0 = float(sys.argv[2])
before = [int(r[1]) for r in rows if float(r[0]) < t0]
after = [(float(r[0]) - t0, int(r[1])) for r in rows if float(r[0]) >= t0]
b = before[-1] if before else (after[0][1] if after else 0)
peak = max([v for _, v in after] + [b])
last = max([t for t, v in after if v > b + 1024] + [0.0])
end = after[-1][0] if after else 0.0
print("%d %d %d %d %d" % (b // 1024, peak // 1024, (peak - b) // 1024, round(last * 1000), round(end * 1000)))
PYRPT
}
# One probe: start it on the nested display, settle, offer, sample 2 s (50
# samples 20 ms apart, each a read of /proc, about 40 ms a turn), kill by
# pid. Leaves "before peak growth" in MB in
# PROBE_RESULT. In the main shell for the same reason as cage_stop, and so
# that an interrupted run's cleanup knows the probe's and the producer's pids.
PROBE_RESULT=""
probe() {
  local name=$1 before
  PROBE_PID=""
  WAYLAND_DISPLAY=$NESTED QT_QPA_PLATFORM=wayland "$QML_BIN" "$SPIKE/$name.qml" >"$WORK/$name.log" 2>&1 &
  PROBE_PID=$!
  settle "$PROBE_PID"
  before=$(rss_kb "$PROBE_PID")
  producer_start $((OFFER_MB * 1024 * 1024))
  PROBE_RESULT=$(sample_peak "$PROBE_PID" 50 "$before")
  if [[ $name == readonly ]]; then
    # P2 rides on this offer, after the sampling window: wl-paste takes
    # keyboard focus for the duration of its read, which is an event the
    # probes must not see inside their window.
    CONSUMER_BYTES=$(WAYLAND_DISPLAY=$NESTED timeout 20 wl-paste --no-newline --type text/plain 2>/dev/null | wc -c | tr -d ' ')
  fi
  kill_pid "$PROBE_PID"; PROBE_PID=""
  producer_stop
}

# ------------------------------------------------------------- the probe arm
probes() {
  local r rd ed nf verdict
  echo "== probe arm: the lead's three probes under cage ($(elapsed) s)"
  cage_start 60
  ck "P1 the nested display is cage's own (caller: $LIVE_DISPLAY)" "$([[ -n $NESTED && $NESTED != "$LIVE_DISPLAY" ]] && echo nested || echo "$NESTED")" "nested"
  CONSUMER_BYTES=""
  probe readonly; rd=$PROBE_RESULT; echo "   readonly.qml  before/peak/growth MB: $rd"
  probe editable; ed=$PROBE_RESULT; echo "   editable.qml  before/peak/growth MB: $ed"
  probe nofield;  nf=$PROBE_RESULT; echo "   nofield.qml   before/peak/growth MB: $nf"
  ck "P2 a consumer on the nested display reads the whole offer (bytes)" "$CONSUMER_BYTES" "$((OFFER_MB * 1024 * 1024))"
  r=${ed##* }
  if [[ $r =~ ^-?[0-9]+$ ]] && (( r >= OFFER_MB )); then verdict="reads-everything (+$r MB, $(python3 -c 'import sys; print("%.1f" % (float(sys.argv[1]) / float(sys.argv[2])))' "$r" "$OFFER_MB" 2>/dev/null || true)x the payload)"; else verdict="grew-only-+${r}-MB-on-${OFFER_MB}-MB"; fi
  ck "P3 the editable probe reads everything (the rig's control: offers are delivered)" "${verdict%% *}" "reads-everything"
  [[ ${verdict%% *} == reads-everything ]] && echo "   P3 detail: $verdict"
  r=${rd##* }
  ck "P4 the read-only probe reads nothing (grew less than ${PROBE_BAND_MB} MB)" "$([[ $r =~ ^-?[0-9]+$ ]] && (( r < PROBE_BAND_MB )) && echo reads-nothing || echo "grew +$r MB")" "reads-nothing"
  r=${nf##* }
  ck "P5 the no-field probe reads nothing (grew less than ${PROBE_BAND_MB} MB)" "$([[ $r =~ ^-?[0-9]+$ ]] && (( r < PROBE_BAND_MB )) && echo reads-nothing || echo "grew +$r MB")" "reads-nothing"
  cage_stop
  ck "P6 probes, producer, keyboard and compositor gone, socket removed" "$STOP_VERDICT" "gone"
  echo "== probe arm done ($(elapsed) s)"
}

# ------------------------------------------------------------- the shell arm
h()   { env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" "$@"; }
ipc() { h ipc "$@" 2>/dev/null; }
gf()  { qa_guide_field "d$1" "$(ipc state)"; }
field_len()   { gf "['form']['values']['playlist']['length']"; }
field_head()  { gf "['form']['values']['playlist']['value'][:3]"; }
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
# The guide holds the keyboard again, before any chord. wl-copy maps a
# surface of its own for an instant to obtain a serial, and under cage a
# producer restarted within milliseconds of the previous one's death leaves
# the guide with NO active focus item until the next focus change -- 2 runs
# in 10 when measured, for longer than 4 s, and once as a refused chord
# (exit 3) in a scenario run: run.sh's focus guard doing its job. Focus
# comes back within 100 ms of any surface mapping and unmapping, so the
# nudge is `wl-paste -l` on the nested display (it lists the offer's types,
# reads no data, and maps a surface to do it). Bounded both ways, and the
# nudge is SAID when it happens; the join is `ipc focusState`, the same
# question `key` asks before typing.
focus_held() { qa_json_field 'd["keyboard"] is True' "$(ipc focusState)"; }
regain_focus() {
  wait_for true 2 focus_held >/dev/null && return 0
  echo "   focus: the guide lost its focus item after a producer restart (cage); nudging with wl-paste -l"
  WAYLAND_DISPLAY=$NESTED timeout 5 wl-paste -l >/dev/null 2>&1
  wait_for true 5 focus_held
}
# A chord through run.sh key, its exit in KEY_RC, and -- when the guard
# refused or wtype failed -- the verb's own reason in the transcript, so a
# red control says WHY rather than only that the value did not move.
chord() {
  : >"$WORK/key.log"
  h key "$@" >"$WORK/key.log" 2>&1; KEY_RC=$?
  (( KEY_RC == 0 )) || sed 's/^/   key: /' "$WORK/key.log" | tail -n 4
  return 0
}
# The clipboard processes under the shell, by parent pid, so neither can
# match this script's own shell (CLAUDE.md parallel rule 3: the shell is
# not our parent). Since R8 the shell's child is the helper's `clipboard`
# verb and wl-paste is the HELPER's child; before R8 wl-paste was the
# shell's own. clip_helpers lists the helper pids; clip_children counts
# both generations of either shape.
clip_helpers()  { pgrep -P "$1" -f 'omarchy-iptv clipboard' 2>/dev/null; return 0; }
clip_children() {
  local shell=$1 n hp
  n=$(pgrep -P "$shell" -x wl-paste 2>/dev/null | wc -l | tr -d ' ')
  for hp in $(clip_helpers "$shell"); do
    n=$((n + 1 + $(pgrep -P "$hp" -x wl-paste 2>/dev/null | wc -l | tr -d ' ')))
  done
  echo "$n"
}
# One IPC round trip in ms, bounded; a timeout answers the bound itself.
ipc_ms() {
  local t1 t2
  t1=$(date +%s%N)
  timeout 20 env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" ipc tooltip >/dev/null 2>&1
  t2=$(date +%s%N)
  echo $(( (t2 - t1) / 1000000 ))
}

shell_arm() {
  local shell_pid before peak r ms worst cap len head i left helper_bound helper_peak helper_seen hp v
  echo "== shell arm: the real Guide.qml under cage (plugin tree $PLUGIN_ROOT) ($(elapsed) s)"
  cage_start 120
  # The stub compositor in front of PATH, as pip-scenario.sh does it, and
  # HYPRLAND_INSTANCE_SIGNATURE unset: the service's hyprctl probe stops at
  # `which`, and nothing can reach the user's compositor from in here.
  mkdir -p "$SCRATCH/bin" && ln -sfn "$HERE/stub-hyprctl.py" "$SCRATCH/bin/hyprctl"
  h reap >/dev/null 2>&1
  SHELL_STARTED=1
  h --detach --playlist none --open --window floating >"$WORK/start.log" 2>&1
  shell_pid=$(cat "$SCRATCH/qs.pid" 2>/dev/null)
  wait_for true 20 gf "['formActive']"
  ck "L1 the guide opened into the first-run form with the playlist field focused" \
     "$(gf "['opened']") $(gf "['formActive']") $(gf "['form']['origin']") $(gf "['formFocus']")" "true true firstRun playlist"
  ck "L2 the keyboard is held by a TextField of the guide in a floating window" \
     "$(qa_json_field 'd["open"], d["keyboard"], d["item"], d["window"]' "$(ipc focusState)")" "(True, True, 'TextField', 'floating')"
  # L3: the positive control. `key` refuses (exit 3) unless the guide holds
  # the keyboard, so a 0 here is itself evidence the chord reached the form.
  regain_focus
  chord -- abc
  wait_for 3 5 field_len
  ck "L3 typing through the harness key verb lands in the model value (key exit $KEY_RC)" "$(field_len) $(field_head)" "3 abc"
  # The measurement: settle, sample 1 s before, offer, twelve round trips
  # back to back from the instant of the offer, 3 s of samples after.
  settle "$shell_pid"
  # 40 samples: 1 s before the offer, 3 s after, concurrent with the twelve
  # IPC round trips that start at the instant of the offer -- so the peak is
  # observed WHILE the read happens, not after the shell has freed the byte
  # array and kept only the decoded string (sampling after the loop read the
  # baseline's growth as +89 MB where the peak is +255).
  sampler_start "$shell_pid" 40 "$WORK/shell.rss"
  sleep 1.0
  producer_start $((OFFER_MB * 1024 * 1024))
  worst=0; ms=""
  for ((i = 0; i < 12; i++)); do r=$(ipc_ms); ms="$ms $r"; (( r > worst )) && worst=$r; done
  echo "   ipc round trips after the offer (ms):$ms   worst $worst"
  wait "$SAMPLER_PID" 2>/dev/null; SAMPLER_PID=""
  r=$(sampler_report "$WORK/shell.rss")
  set -- $r; before=$1; peak=$2; r=$3
  echo "   shell rss MB: before $before, peak $peak, growth +$r, last growth at +$4 ms (offer at +0 ms, sampled from -1 s to +$5 ms)"
  ck "L4 the shell grew by less than ${SHELL_BAND_MB} MB after a ${OFFER_MB} MB offer" "$([[ $r =~ ^-?[0-9]+$ ]] && (( r < SHELL_BAND_MB )) && echo unchanged || echo "grew +$r MB")" "unchanged"
  # L5: the stall. The got/want pair is a verdict, never the number, so a
  # FAIL line shows the bound and the measurement apart. On a --baseline the
  # line is reported and not asserted (DR-B2): whether one of twelve calls
  # lands inside a ~300 ms read is timing, and a baseline run is the red
  # proof of L4 and L10, not of this.
  if [[ -n $BASELINE ]]; then
    echo "   L5 reported, not asserted, on a baseline: worst round trip $worst ms against the ${IPC_BOUND_MS} ms bound ($( (( worst < IPC_BOUND_MS )) && echo "no stall caught" || echo "STALLED: a call landed inside the read"))"
  else
    ck "L5 the slowest IPC round trip after the offer (worst $worst ms) is under ${IPC_BOUND_MS} ms" "$( (( worst < IPC_BOUND_MS )) && echo under || echo "stalled at $worst ms")" "under"
  fi
  ck "L6 the offer alone changed nothing in the field" "$(field_len) $(field_head)" "3 abc"
  producer_stop
  # L7 / L8: the paste controls, through the two chords that match
  # StandardKey.Paste. Small offers, after the measurement window, so that
  # the paste path's own read is never confused with the change-driven one;
  # the paste over the big offer itself is L10, measured on its own.
  python3 -c 'import sys; sys.stdout.write("C" * 10)' | WAYLAND_DISPLAY=$NESTED wl-copy --foreground --type text/plain >/dev/null 2>&1 &
  PRODUCER_PID=$!
  regain_focus
  chord -M shift -k Insert -m shift
  wait_for 13 5 field_len
  ck "L7 Shift+Insert pastes a 10-byte offer through the process path (key exit $KEY_RC)" "$(field_len) $(field_head)" "13 abc"
  producer_stop
  cap=$(node -e 'console.log(require(process.argv[1]).formCapacity("playlist"))' "$(qa_model_files "$PLUGIN_ROOT" | head -n 1)" 2>/dev/null)
  python3 -c 'import sys; sys.stdout.write("B" * 5000)' | WAYLAND_DISPLAY=$NESTED wl-copy --foreground --type text/plain >/dev/null 2>&1 &
  PRODUCER_PID=$!
  regain_focus
  chord -M ctrl v -m ctrl
  wait_for "$cap" 5 field_len
  len=$(field_len); head=$(field_head)
  ck "L8 Ctrl+V pastes a 5,000-byte offer and it lands at the tree's formCapacity (key exit $KEY_RC)" "$len $head" "$cap abc"
  wait_for 0 3 clip_children "$shell_pid"
  ck "L9 no clipboard helper and no wl-paste left under the shell after the paste answered" "$(clip_children "$shell_pid")" "0"
  producer_stop
  # L10: the user-initiated half (R8). The field is selected whole (Ctrl+A,
  # native on a read-only control and on an editable one) so the paste
  # REPLACES it on both trees -- a different letter, so that the paste
  # landing is read off the field's head and not inferred. The sampler runs
  # across the chord and the helper child is watched by pid for its peak,
  # 60 samples at 100 ms from 0.5 s before the chord: on 96f5261 the shell's
  # own wl-paste collector grew +304 MB with its last growth 6.9 s after the
  # chord, and on the fixed tree the helper peaks at 32 MB and the shell at
  # +0. The offer is the same size as the change-driven one, so a shell that
  # read it would show it; the chord is the only difference from L4.
  producer_start $((OFFER_MB * 1024 * 1024)) D
  sleep 1.0
  regain_focus
  chord -M ctrl a -m ctrl
  settle "$shell_pid"
  helper_bound=$(node -e 'var m = require(process.argv[1]); console.log(m.CLIPBOARD_MAX_BYTES === undefined ? "none (this tree has no helper bound)" : m.CLIPBOARD_MAX_BYTES + " bytes")' "$(qa_model_files "$PLUGIN_ROOT" | head -n 1)" 2>/dev/null)
  sampler_start "$shell_pid" 60 "$WORK/paste.rss"
  sleep 0.5
  T_OFFER=$(date +%s.%N)
  chord -M ctrl v -m ctrl
  helper_peak=0; helper_seen=0
  for ((i = 0; i < 40; i++)); do
    for hp in $(clip_helpers "$shell_pid"); do
      helper_seen=1; v=$(rss_kb "$hp"); [[ -n $v && $v -gt $helper_peak ]] && helper_peak=$v
    done
    sleep 0.1
  done
  wait "$SAMPLER_PID" 2>/dev/null; SAMPLER_PID=""
  r=$(sampler_report "$WORK/paste.rss")
  set -- $r; before=$1; peak=$2; r=$3
  len=$(field_len); head=$(field_head)
  echo "   shell rss MB over the paste: before $before, peak $peak, growth +$r, last growth at +$4 ms (chord at +0 ms, sampled from -0.5 s to +$5 ms); at the window's end $(( $(rss_kb "$shell_pid") / 1024 )) MB"
  echo "   clipboard helper seen under the shell: $helper_seen, peak rss $((helper_peak / 1024)) MB; the tree's helper byte bound: $helper_bound"
  # R8 is observed on BOTH halves, or the label claims more than the check
  # can redden for: the shell's growth (the exhaust half) AND the helper's own
  # peak while it held the bytes -- a dropped byte cap left this check green
  # in a review until the helper's peak joined the verdict. HELPER_BAND_MB is
  # twice the 32 MB an interpreter peaks at on a 2-byte reply (measured six
  # runs on this machine), so it is the cap that is asserted, not the floor.
  hb=$(( helper_peak / 1024 ))
  ck "L10 Ctrl+V over the ${OFFER_MB} MB offer lands at formCapacity, grows the shell by less than ${SHELL_BAND_MB} MB, and the helper that held the bytes peaked under ${HELPER_BAND_MB} MB (key exit $KEY_RC)" \
     "$len $head $([[ $r =~ ^-?[0-9]+$ ]] && (( r < SHELL_BAND_MB )) && echo unchanged || echo "grew +$r MB") $([[ $helper_seen == 1 ]] && (( hb < HELPER_BAND_MB )) && echo helper-bounded || echo "helper seen=$helper_seen peak=${hb}MB")" "$cap DDD unchanged helper-bounded"
  wait_for 0 3 clip_children "$shell_pid"
  ck "L11 no clipboard helper and no wl-paste left under the shell after the cut-short paste" "$(clip_children "$shell_pid")" "0"
  producer_stop
  # L12: the console sink. The payloads are runs of a single letter; a run of
  # 64 of any in the harness log would be the shell printing what it read.
  ck "L12 the harness log carries no run of the payload" "$(qa_count 'A{64}|B{64}|D{64}' "$SCRATCH/harness.log")" "0"
  # L13: teardown. `run.sh reap` stops the detached shell by the pid it
  # recorded, then sweeps by its patterns, every one scoped to this
  # scenario's own harness directory ($SCRATCH, never the shared one); then
  # the arm's compositor by the pids this scenario recorded.
  h reap >/dev/null 2>&1; SHELL_STARTED=0
  for ((i = 0; i < 50; i++)); do kill -0 "$shell_pid" 2>/dev/null || break; sleep 0.1; done
  left=""; kill -0 "$shell_pid" 2>/dev/null && left="shell($shell_pid) "
  cage_stop
  ck "L13 the shell, keyboard, producer and compositor are gone, socket removed" "$left$STOP_VERDICT" "gone"
  echo "== shell arm done ($(elapsed) s)"
}

probes
[[ $MODE == live ]] && shell_arm

# The floor. A check that stops executing must turn the run red rather than
# quietly shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ *ck "P[0-9]' clip-scenario.sh   -> 6, the probe arm   -> check-tree
#   grep -cE '^ *ck "[PL][0-9]' clip-scenario.sh -> 19, both arms      -> live
# and a --baseline run is one fewer: L5 is reported there, not asserted.
# Every assertion is one `ck "P<n> ...` or `ck "L<n> ...` line, none in a
# loop, and the definition of ck() does not match either recipe. Never lower
# a floor to make a run green. scripts/check.sh's CLIP_PREFLIGHT_MIN is the
# check-tree number plus one (this line), and scripts/qa-lib-test.sh asserts
# every join.
if [[ $MODE == check-tree ]]; then
  EXPECTED_CHECKS=6
else
  EXPECTED_CHECKS=19
  [[ -n $BASELINE ]] && EXPECTED_CHECKS=$((EXPECTED_CHECKS - 1))
fi
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  pass "the scenario ran every check it has ($ran)"
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi

if [[ -n $BASELINE ]]; then
  echo "baseline $BASELINE: the expected reds are L4 on a tree whose form fields are editable (the shell reads the offer: +240..+297 MB on 100 MB when measured on d55149b, about 2.5x the payload) and L10 on any tree whose shell collects wl-paste's whole output itself before cutting it (+304 MB on 96f5261; on d55149b the editable field pastes natively and reads it again). L5 is reported above, not asserted. Every P check and L1, L2, L3, L6..L9, L11..L13 pass on every tree: they are controls, not discriminators."
fi
echo "clip-scenario: $PASS passed, $FAIL failed (mode $MODE, tree $PLUGIN_ROOT${BASELINE:+, baseline $BASELINE}, $(elapsed) s)"
(( FAIL == 0 ))
