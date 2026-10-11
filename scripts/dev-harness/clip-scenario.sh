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
# Model.editInsert / editDelete); paste is the out-of-process path only
# (Service.qml requestClipboard runs wl-paste as argv, bounded by a watchdog,
# capped at Model.LIMITS.url * 4 and then at the field's capacity).
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
#   Model.formCapacity, read from the tree under test by calling it.
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
#       IPC_BOUND_MS: the main thread was never held by the read
#   L6  the offer alone changed nothing in the field
#   L7  Shift+Insert pastes a 10-byte offer through the process path
#   L8  Ctrl+V pastes a 5,000-byte offer and it lands at exactly
#       Model.formCapacity("playlist") of the tree under test
#   L9  the shell has no wl-paste child left after the paste answered
#   L10 the harness log carries no run of the payload (the console sink)
#   L11 the shell, the keyboard, the producer and the compositor are gone
#
# RULE 11, THE RED RUN. `--baseline d55149b` exports the shipped 0.13.4 and
# runs its Guide.qml / Service.qml / Model.js through the same rig (the
# harness shell.qml is this tree's; it hands the floating-window property in
# as an initial property, which that tree already carries). Measured
# 2026-10-11, recipe and both counts in the footer the run prints: every P
# check passes on both trees (the probes are the lead's and do not involve
# the plugin), L1, L2, L3, L6, L7, L8, L9, L10 and L11 pass on both (controls:
# the editable field types and pastes natively, and Qt truncates a paste to
# maximumLength, which is the same capacity), and L4 is RED -- +254..+297 MB on
# a 100 MB offer, peak 600..642 MB over four runs, the finding at the sink.
# L5 is red on the baseline WHEN a round trip lands inside the read
# (673..685 ms against 56..81 ms around it, four runs of four; the read of
# 100 MB takes a few hundred ms, so the twelve back-to-back calls caught it
# every time measured, and the header does not promise they always will). The
# discriminator is L4; L5 is the stall half of the maintainer's finding,
# observed when timing allows and asserted on the fixed tree always.
#
# MODES. `check-tree` (what scripts/check.sh runs on every commit: no
# transcript, nothing on the user's session, the probe arm alone, about 13 s)
# and `live` (the default: a transcript, both arms, and the --baseline lever).
# Both need cage, wl-copy, wl-paste, wtype, python3, node and the qml
# runtime; a machine without one of them exits 77 with the reason, never 0,
# and those checks run BEFORE anything else so the reason is the first line
# out even with an empty PATH. A cage that does not bring up a display within
# 10 s is the same 77: the sink cannot be observed here. CLIP_CAGE_BIN and
# CLIP_QML_BIN override the two binaries; they exist so the 77 path can be
# driven on a machine that has both.
#
# Holds no display: everything this starts lives on the nested display cage
# creates, read from cage's own child and refused if it names the caller's
# session. It starts no quickshell on the user's session, sends no keystroke
# there, reads nothing from the live install and touches nothing under
# ~/.config, ~/.cache or ~/.local/state (the harness points every XDG
# directory into its own scratch tree, which this scenario keeps apart from
# the shared harness directory so a display lane's running harness is never
# reaped by this one).
set -uo pipefail
SKIP=77
CAGE_BIN=${CLIP_CAGE_BIN:-cage}
QML_BIN=${CLIP_QML_BIN:-/usr/lib/qt6/bin/qml}
# The payload, in MiB. 100 is the lead's and the maintainer's number.
OFFER_MB=${CLIP_OFFER_MB:-100}
# Bands and bounds, all measured 2026-10-11 under cage on this machine and
# recorded in spikes/clip-offer/README.md: a probe that reads nothing and the
# fixed shell both grew by exactly 0 MB in every run; the editable probe by
# 235..305 MB and the baseline shell by 254..297 MB on 100 MB; an IPC round
# trip is 55..159 ms on the fixed tree (the first call carries a process
# cold start) and the baseline's stalled call was 673..685 ms. The shell band
# is wider than the probe band because the shell has
# timers and a service behind it; both are a small fraction of the payload,
# which is the defect's signature.
PROBE_BAND_MB=8
SHELL_BAND_MB=16
IPC_BOUND_MS=400
MODE=${1:-}
case $MODE in
  check-tree) shift ;;
  live|"")
    MODE=live; (( $# )) && shift ;;
  -*) MODE=live ;;
  *) echo "usage: clip-scenario.sh [check-tree|live] [--baseline <ref>]" >&2; exit 2 ;;
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
  [[ -f $EXPORT_DIR/Guide.qml && -f $EXPORT_DIR/Model.js ]] || { echo "$BASELINE holds no Guide.qml / Model.js" >&2; rm -rf "$EXPORT_DIR"; exit 2; }
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
# The foreign producer: OFFER_MB of text/plain on the nested display, never
# written to disk. `--foreground` keeps wl-copy as our direct child, and `$!`
# of a background pipeline is its LAST command, so this pid is wl-copy's.
producer_start() {
  local bytes=$1
  python3 -c 'import sys; sys.stdout.write("A" * int(sys.argv[1]))' "$bytes" \
    | WAYLAND_DISPLAY=$NESTED wl-copy --foreground --type text/plain >/dev/null 2>"$WORK/wl-copy.err" &
  PRODUCER_PID=$!
  T_OFFER=$(date +%s.%N)
}
producer_stop() { kill_pid "$PRODUCER_PID"; PRODUCER_PID=""; }
# Peak RSS over `n` samples 100 ms apart, printed as "before peak growth" in
# MB. The sampler is this shell, not a subshell, so nothing to reap.
sample_peak() {
  local pid=$1 n=$2 before=$3 peak=$3 i v
  for ((i = 0; i < n; i++)); do v=$(rss_kb "$pid"); [[ -n $v && $v -gt $peak ]] && peak=$v; sleep 0.1; done
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
# From the sample file and T_OFFER: "before peak growth last_growth_ms" in
# MB, where before is the last sample taken before the offer and peak the
# highest after it; last_growth_ms is when the RSS last sat above before.
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
print("%d %d %d %d" % (b // 1024, peak // 1024, (peak - b) // 1024, round(last * 1000)))
PYRPT
}
# One probe: start it on the nested display, settle, offer, sample 2 s, kill
# by pid. Leaves "before peak growth" in MB in PROBE_RESULT. In the main
# shell for the same reason as cage_stop, and so that an interrupted run's
# cleanup knows the probe's and the producer's pids.
PROBE_RESULT=""
probe() {
  local name=$1 before
  PROBE_PID=""
  WAYLAND_DISPLAY=$NESTED QT_QPA_PLATFORM=wayland "$QML_BIN" "$SPIKE/$name.qml" >"$WORK/$name.log" 2>&1 &
  PROBE_PID=$!
  settle "$PROBE_PID"
  before=$(rss_kb "$PROBE_PID")
  producer_start $((OFFER_MB * 1024 * 1024))
  PROBE_RESULT=$(sample_peak "$PROBE_PID" 20 "$before")
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
# One IPC round trip in ms, bounded; a timeout answers the bound itself.
ipc_ms() {
  local t1 t2
  t1=$(date +%s%N)
  timeout 20 env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" ipc tooltip >/dev/null 2>&1
  t2=$(date +%s%N)
  echo $(( (t2 - t1) / 1000000 ))
}

shell_arm() {
  local shell_pid before peak r ms worst cap len head i left
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
  echo "   shell rss MB: before $before, peak $peak, growth +$r, last growth at +$4 ms (offer at +0 ms, sampled -1 s .. +3 s)"
  ck "L4 the shell grew by less than ${SHELL_BAND_MB} MB after a ${OFFER_MB} MB offer" "$([[ $r =~ ^-?[0-9]+$ ]] && (( r < SHELL_BAND_MB )) && echo unchanged || echo "grew +$r MB")" "unchanged"
  ck "L5 the slowest IPC round trip after the offer is under ${IPC_BOUND_MS} ms" "$(( worst < IPC_BOUND_MS ? 1 : 0 )) ($worst ms)" "1 ($worst ms)"
  ck "L6 the offer alone changed nothing in the field" "$(field_len) $(field_head)" "3 abc"
  producer_stop
  # L7 / L8: the paste controls, through the two chords that match
  # StandardKey.Paste. Small offers, after the measurement window, so the
  # process path's own read (DR-1: wl-paste pulls the offer into the shell
  # before the cap applies) is never confused with the finding.
  python3 -c 'import sys; sys.stdout.write("C" * 10)' | WAYLAND_DISPLAY=$NESTED wl-copy --foreground --type text/plain >/dev/null 2>&1 &
  PRODUCER_PID=$!
  regain_focus
  chord -M shift -k Insert -m shift
  wait_for 13 5 field_len
  ck "L7 Shift+Insert pastes a 10-byte offer through the process path (key exit $KEY_RC)" "$(field_len) $(field_head)" "13 abc"
  producer_stop
  cap=$(node -e 'console.log(require(process.argv[1] + "/Model.js").formCapacity("playlist"))' "$PLUGIN_ROOT" 2>/dev/null)
  python3 -c 'import sys; sys.stdout.write("B" * 5000)' | WAYLAND_DISPLAY=$NESTED wl-copy --foreground --type text/plain >/dev/null 2>&1 &
  PRODUCER_PID=$!
  regain_focus
  chord -M ctrl v -m ctrl
  wait_for "$cap" 5 field_len
  len=$(field_len); head=$(field_head)
  ck "L8 Ctrl+V pastes a 5,000-byte offer and it lands at the tree's formCapacity (key exit $KEY_RC)" "$len $head" "$cap abc"
  for ((i = 0; i < 30; i++)); do pgrep -P "$shell_pid" -x wl-paste >/dev/null 2>&1 || break; sleep 0.1; done
  ck "L9 the shell has no wl-paste child left after the paste answered" "$(pgrep -P "$shell_pid" -x wl-paste 2>/dev/null | wc -l | tr -d ' ')" "0"
  producer_stop
  # L10: the console sink. The payloads are runs of a single letter; a run of
  # 64 of either in the harness log would be the shell printing what it read.
  ck "L10 the harness log carries no run of the payload" "$(qa_count 'A{64}|B{64}' "$SCRATCH/harness.log")" "0"
  # L11: teardown by pid. `run.sh reap` stops the detached shell by the pid
  # it recorded; then the arm's compositor.
  h reap >/dev/null 2>&1; SHELL_STARTED=0
  for ((i = 0; i < 50; i++)); do kill -0 "$shell_pid" 2>/dev/null || break; sleep 0.1; done
  left=""; kill -0 "$shell_pid" 2>/dev/null && left="shell($shell_pid) "
  cage_stop
  ck "L11 the shell, keyboard, producer and compositor are gone, socket removed" "$left$STOP_VERDICT" "gone"
  echo "== shell arm done ($(elapsed) s)"
}

probes
[[ $MODE == live ]] && shell_arm

# The floor. A check that stops executing must turn the run red rather than
# quietly shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ *ck "P[0-9]' clip-scenario.sh   -> 6, the probe arm   -> check-tree
#   grep -cE '^ *ck "[PL][0-9]' clip-scenario.sh -> 17, both arms      -> live
# Every assertion is one `ck "P<n> ...` or `ck "L<n> ...` line, none in a
# loop, and the definition of ck() does not match either recipe. Never lower
# a floor to make a run green. scripts/check.sh's CLIP_PREFLIGHT_MIN is the
# check-tree number plus one (this line), and scripts/qa-lib-test.sh asserts
# both joins.
if [[ $MODE == check-tree ]]; then
  EXPECTED_CHECKS=6
else
  EXPECTED_CHECKS=17
fi
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  pass "the scenario ran every check it has ($ran)"
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi

if [[ -n $BASELINE ]]; then
  echo "baseline $BASELINE: L4 is expected RED here (that tree's form fields are editable, so the shell reads the offer: +254..+297 MB on 100 MB when measured) and L5 is red when one of the twelve round trips lands inside the read (673..685 ms measured). Every P check and L1, L2, L3, L6..L11 pass on both trees: they are controls, not discriminators."
fi
echo "clip-scenario: $PASS passed, $FAIL failed (mode $MODE, tree $PLUGIN_ROOT${BASELINE:+, baseline $BASELINE}, $(elapsed) s)"
(( FAIL == 0 ))
