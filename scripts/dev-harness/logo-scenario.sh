#!/bin/bash
# scripts/dev-harness/logo-scenario.sh -- D-LOGO-11: a provider logo chooses
# how much memory the shell allocates, and the HELPER is the gate that must
# stop it before the shell's Image ever sees the file.
#
# THE FINDING. A provider JPEG passed `write_logo` on content type, magic
# bytes and a 256 KiB byte cap, and nothing bounded the dimensions its header
# DECLARED. The decoder's cost is quadratic in that number and the bytes do
# not have to honour it: 304 bytes took a Qt Image declared as the guide's row
# slot to 840 MB of resident memory, 555 bytes to 1,239 MB, and a 65500x65500
# header past a 1.5 GB cap in 1.5 s. Qt's own allocation limit is consulted
# about the image already divided by libjpeg's largest scale denominator, and
# at the format's maximum that is exactly the 256 MiB default, so no JPEG can
# trip it on this path. Raised by the marketplace maintainer against the
# shipped 0.13.3 (159da94) on omacom/omarchy-plugin-marketplace#10802. The
# lead's measurements are in docs/QA-RESULTS.md under "Fifth maintainer
# finding, 2026-10-09"; they are re-runnable from spikes/logo-decode-bomb/ and
# CITED here, not restated as this script's own.
#
# THE FIX (fb2acdc, lane A): two numbers at the one gate that puts a
# provider's bytes into the cache -- no side over 4096, no more than 4,194,304
# pixels, read from the header for all four allowed types, a header that
# cannot be read refused rather than passed -- and a SWEEP of the cache the
# shipped releases wrote without checking: the "already on disk" branch of
# `logos --fetch` proves a file's header before announcing its name, unlinks
# what fails, and falls through to the fetch where the gate refuses the bytes
# again. The guide points an Image at a cache file ONLY when the helper
# announced that name (Model.logoSlot, Model.wallTile, Service.qml logoHave),
# so a name withheld is a file the shell never decodes.
#
# WHAT THIS SCENARIO OBSERVES, AND HOW. Two sinks, both real:
#
#   1. The helper, as the SUBPROCESS the service runs: `logos --fetch
#      --cache-dir <scratch>` from bin/omarchy-iptv, against a cache this run
#      owns and a provider this run is. `fetch_logo` is https-only, so the
#      provider is spikes/logo-decode-bomb/serve-and-fetch.py: a server with a
#      self-signed certificate in a THREAD of that process, the helper as its
#      CHILD with SSL_CERT_FILE pointed at the certificate, nothing detached,
#      no pid read from `$!`, nothing to kill by pattern (parallel rule 3).
#      The corpus is built from spikes/logo-decode-bomb/make-corpus.py, which
#      is stdlib only, so the gate depends on nothing installed.
#      The provider is PUBLIC (2026-10-29). Since D-SINK-40 a logo never
#      reaches an address on this machine or a local network, so the rig's
#      first provider, on 127.0.0.1, was refused `local_address` before a
#      byte moved and the preflight read 23 passed, 10 failed over a helper
#      that was right. The rig and the helper now run inside `unshare -rn`, a
#      private network namespace whose only interfaces are its own loopback
#      and a dummy one carrying 11.0.0.1 -- an address the helper's REAL
#      classifier calls global, which exists nowhere but there, so nothing
#      the helper does can reach a real interface. No seam: the helper is the
#      tree's, unpatched. A second server on 127.0.0.1 inside the namespace
#      serves the good logo to one more channel, and the shipping policy must
#      refuse it with no GET reaching it (R2), so a namespace or a helper that
#      stopped enforcing the policy is red in the same run (rule 10). The
#      QML probe below reads files from disk and runs outside it.
#   2. The shell's Image, as the probe spikes/logo-decode-bomb/probe-tmpl.qml
#      declares it (exactly Guide.qml's row slot), handed whatever the helper
#      ANNOUNCED, under an ADDRESS-SPACE RLIMIT of 2.5 GB (util-linux
#      `prlimit --as`) on the qml process alone, with ru_maxrss read by
#      peakrun.py. The rlimit is the cap, and not a service-manager scope,
#      for two reasons: the marketplace scan reads the scope tool's name as a
#      service-management capability wherever it appears in a tracked file,
#      and under the rlimit an over-bound decode is a clean allocator
#      refusal (Qt reports Image.Error, rc 1) rather than a kill. That is the
#      POSITIVE CONTROL: a scenario where everything is refused passes against
#      a helper that refuses everything, so the legitimate 512x512 logo must
#      be fetched, announced, written AND reach Image.Ready at control memory.
#
# THE RUN. One cache, one helper invocation, four kinds of fixture:
#   planted   ten over-bound files copied into the logo cache under the name
#             the helper derives (a cache "written by 0.13.3"), ALSO served
#   served    the same ten, plus two edge files that drive the two bounds
#             apart (side over with pixels under; pixels over with both sides
#             under), plus a JPEG with magic bytes and no frame header (the
#             truncated-download shape), plus the good logo, a file at the
#             bound exactly, and a 64x64 JPEG carrying an EXIF thumbnail
#   cached    one legitimate 64x64 planted and served, which must be announced
#             with NO request made (the sweep must not sweep what is sound)
#   sink      the good logo's cache file, decoded by the probe under the cap
#
#   V1  the helper HAS `logos --fetch`           (a status-2 helper makes every
#                                                 refusal below vacuous; read
#                                                 this line first on a red run)
#   V2  the name the helper announces for the good logo is the name the rig
#       computed -- so the planted files sat where the helper looks (rule 13)
#   C1  the good 512x512 logo: one GET, announced, on disk       <- positive control
#   C2  the file AT the bound (4096x1024, 4,194,304 px): announced, on disk
#   C3  the legitimate cached file: announced, NO GET, still on disk
#   C4  a 64x64 JPEG with a whole thumbnail JPEG in its APP1: announced, on
#       disk -- a parser that refused every APP1 would get the bomb below
#       right for the wrong reason
#   C5  D-LOGO-13 (2026-10-29): a 64x64 PNG carrying iCCP, zTXt, iTXt and
#       tEXt, served: one GET, announced, and the file on disk is IHDR, IDAT,
#       IEND with the provider's IDAT bytes unchanged -- read from the file,
#       not from the helper's word
#   C6  the same bytes planted in the cache under a second name: no GET,
#       announced, and the file rewritten to that canonical form in place
#   P1..P10 each planted bomb is GONE from the cache afterwards  <- the sweep
#       P8 is the EXIF-thumbnail bomb (a 64x64 SOF inside the APP1, the real
#       SOF 20000x20000 after it), P9 the 64x65535 column (pixels UNDER the
#       bound by 64, one side over), P10 the two-frame GIF (64x64 first frame,
#       65500x65500 second) -- the three shapes a reviewer crafted against
#       the parser, each kept because a mutation of the helper passed it
#   S1  the summary counts them: swept == 10
#   G1  each swept bomb was fetched exactly once: the sweep fell through to
#       the gate, one bomb one refusal, and nothing was fetched twice
#   F1  no bomb's name was announced                              <- the gate
#   F2  the logo directory holds exactly the six legitimate names
#   R1  reasons.logo_dimensions == 13   (10 bombs + 2 edges + the unreadable)
#   R2  the policy refusals, four numbers in one line: refusedOnPolicy == 14
#       (the 13 above and the logo on 127.0.0.1), reasons.local_address == 1,
#       no GET reached the 127.0.0.1 server, and its name is not announced --
#       the destination policy observed live inside the namespace, folded
#       into R2 so the floor (and check.sh's join to it) does not move
#   R3  fetched == 4, cached == 2 (C5 is the fourth fetch, C6 the second
#       cached file)
#   E1  side over, pixels under (5000x800): not announced
#   E2  pixels over, both sides under (2048x2049): not announced
#   E3  magic bytes and no frame header: not announced (refused, not passed)
#   M1  the summary carries maxSide == 4096
#   M2  the summary carries maxPixels == 4194304
#   T1  the refusal text names the HOST and the numbers and carries no URL
#       (rule 5), read by calling the shipping function from the tree under test
#   T2  nothing the helper printed on either stream carries the URL path token
#   K1  the sink: the good logo's file reaches Image.Ready at control memory
#   K2  the sink is never handed the 304-byte bomb: its name is withheld AND
#       the file is gone. The evidence line says which of three things
#       happened: `withheld-and-gone` (the pass), `withheld-but-file-survived`
#       (the name was withheld but the unlink failed, so a stale `logoHave`
#       could still reach it), or `announced`. On a tree that announces it,
#       the LIVE arm decodes it under the cap and prints the peak -- that is
#       the finding, observed -- and check-tree reports "announced" WITHOUT
#       decoding (the gate must never decode a bomb on somebody's desktop,
#       even capped)
#
# THE LIVE SEGMENT, W1..W7 (F-M3-18's open half, 2026-10-25). The three
# lifecycle decisions that lived only in Service.qml -- clearSourceData
# emptying `logoHave` on a switch, the announced set tagged with the LOGOS
# directory through Model.logoDirFor, and the count rebuilt from the new
# source's announced names alone -- observed on the real Service.qml under
# a nested headless cage of this scenario's own (key-scenario.sh's shape),
# through the harness shell's exposed `logoCount`, `logoHaveDir` and
# `logoDir`. Two sources with DISTINCT logo sets, both local files, their
# logos planted in each source's cache under the name the helper derives
# (the cached-file branch announces a sound file with no request, so nothing
# is contacted: every logo host here is .invalid and nothing resolves it);
# logos switched on over the first, then a switch to the second, then back:
#
#   W1  over A, logos on: logoCount == A's 6, and the announced set's tag
#       IS the directory the guide compares it with (logoHaveDir == logoDir
#       == <A's cache>/logos, derived by the tree's own Model.logoDirFor)
#   W2  the FIRST sample after the switch to B whose logoDir is B's reads
#       logoCount 0 and no tag: the set was emptied in the turn the
#       directory changed (clearSourceData), before any fetch for B answered
#   W3  no sample between the switch and the rebuild carries a non-empty set
#       tagged for a directory other than the one under it
#   W4  the count rebuilds to B's 4 -- B's announced names only, not A's 6,
#       not 10 -- tagged for B's logos directory
#   W5, W6  the same two on the way back to A (0 first, then 6 tagged A)
#   W7  the shell, the cage and the nested socket are gone at the end
#
# Seen red by mutation (rule 11), through `--tree` over a copy of the tree
# with ONE Service.qml decision broken (the recipe is in README.md under
# "Logos"): `root.logoHave = ({})` deleted from clearSourceData -> W2, W3
# and W5 red (the first sample at B's directory still carries A's 6 names
# tagged for A), 37 passed 3 failed; the tag made `root.activeCacheDir`
# instead of `Model.logoDirFor(root.activeCacheDir)` -> W1, W3, W4 and W6
# red (a set tagged for the cache directory, which the guide never compares
# equal), 36 passed 4 failed; the tree itself 40 passed 0 failed
# (lane-liveproofs over 0cae446, 2026-10-25, under private-bus.sh). The
# window W2 reads is narrow: on the tree the first sample at the new
# directory came about 60 ms after switchSource returned and the rebuilt set
# one sample later, so the switch loop samples as fast as IPC answers.
#
# RULE 11, THE RED RUN. `--baseline 159da94` exports the shipped 0.13.3 and
# runs its helper through the same rig. Measured 2026-10-11 (recipe and both
# counts in the footer line the run prints): V1, V2, C1, C2, C3, C4, T2 and K1
# pass as controls, and P1..P10, S1, G1, F1, F2, R1, R2, R3, E1, E2, E3, M1,
# M2, T1 and K2 go red -- 24 of the 32 checks; "9 passed, 24 failed" with the
# floor line -- because that helper announces and writes every bomb, sweeps
# nothing, has no `logo_dimension_refusal`, and reports neither bound. K2's
# red line carries the peak the probe measured on the announced 304 bytes:
# rc=0 peak_mb=839, which is the finding at the sink. G1 is red there for
# the right reason: the planted bombs were served from the cache and never
# fetched, so the GET count reads 0 of 10, not 10 of 10.
# Re-measured on the namespace rig, 2026-10-29, check-tree: the tree 33
# passed, 0 failed; `--baseline 159da94` the same 9 passed, 24 failed, its R2
# reading "0 NULL 1 true" (the 127.0.0.1 logo fetched and announced);
# `--baseline 713afbf`, the last dev before D-SINK-40, 30 passed, 3 failed --
# F2, R2 and R3, the policy's three, and nothing else; and the tree with
# `for_logos` made to permit every address (`--tree` over a sealed copy) the
# same 30 and 3. The rig run outside a namespace refuses with exit 2 before
# it serves anything. With C5 and C6 (lane-p1c, the same day): the tree 35
# passed, 0 failed; a sealed copy whose canonical_png returns its input 33
# and 2, C5 and C6 alone; `--baseline 159da94` 9 and 26, C5 and C6 among
# them; `--baseline 713afbf` (D-LOGO-13 shipped, D-SINK-40 not) 32 and 3,
# the policy's three as before.
#
# MODES. `check-tree` (what scripts/check.sh runs on every commit: no
# transcript, no network outside a private namespace of its own, no display,
# no bomb decoded, under 20 s) and `live` (the default: a transcript, the
# same checks, the W segment under a nested cage, and the --baseline / --tree
# levers; `--tree <dir>` takes a prepared plugin tree where --baseline takes
# a ref; both work in check-tree too). Both need python3, openssl, util-linux
# prlimit and unshare, iproute2's ip, /usr/lib/qt6/bin/qml, and a kernel
# that lets this user make a network namespace with a dummy interface in it;
# live also needs node, cage, quickshell and qs. A machine without one exits
# 77 with the reason, never 0 (and check.sh calls a 77 red unless
# LOGO_PREFLIGHT_SKIP_OK=1), and the tool checks run BEFORE anything else so
# the reason is the first line out even with an empty PATH. LOGO_QML_BIN
# overrides the qml path, LOGO_CAGE_BIN the cage binary and LOGO_UNSHARE_BIN
# the unshare binary; they exist so the 77 path can be driven on a machine
# that has all three.
#
# Holds no display: check-tree starts no quickshell and no compositor; live
# starts a nested headless cage of its own (cage's child records the display
# and the run refuses one that names the caller's session) and the harness
# shell on THAT display, in this scenario's own harness directory
# ($XDG_RUNTIME_DIR/omarchy-iptv-logo unless OMARCHY_IPTV_HARNESS_DIR says
# otherwise, so a display lane's shared harness is never reaped by this one).
# No mpv, no keystroke, nothing read from the live install, nothing under
# ~/.config, ~/.cache or ~/.local/state (the helper is run with HOME and
# every XDG variable pointed into the scratch directory, and since
# F-HARNESS-20 the QML probe and the rest of the driver run with a home
# inside the work directory). INT and TERM are trapped into an exit, so
# cleanup() reaps the shell by its recorded pid and the cage by its child's,
# the way key-scenario.sh does; the F-HARNESS-18 live proof (a TERM at 6 s
# in the cage and shell start, a TERM and an INT at 10 s inside the W
# switch loop with the shell and the cage up, each leaving nothing) is in
# docs/QA-RESULTS.md.
set -uo pipefail
QML_BIN=${LOGO_QML_BIN:-/usr/lib/qt6/bin/qml}
CAGE_BIN=${LOGO_CAGE_BIN:-cage}
UNSHARE_BIN=${LOGO_UNSHARE_BIN:-unshare}
# RLIMIT_AS, in bytes, on the qml process alone. Address space, not resident
# set: Qt offscreen maps about 1 GB before it decodes anything, the 840 MB
# bomb sits under this, and the 65500x65500 header asks for more than the
# limit allows and is refused by the allocator. Measured 2026-10-11, in
# spikes/logo-decode-bomb/README.md.
CAP_AS=2500000000
CONTROL_MB=160
SKIP=77
MODE=${1:-}
case $MODE in
  check-tree) shift ;;
  live|"")
    MODE=live; (( $# )) && shift ;;
  -*) MODE=live ;;
  *) echo "usage: logo-scenario.sh [check-tree|live] [--baseline <ref>|--tree <dir>]" >&2; exit 2 ;;
esac
BASELINE=""; TREE=""
while (( $# )); do
  case $1 in
    --baseline)
      # Refused rather than defaulted, as tls-scenario.sh's is: a dropped ref
      # would silently grade the current tree and call it a baseline.
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

# ---- refusals, above the transcript (qa-lib.sh item 3) and above every
# external command: `command -v`, `[[ -x ]]` and `echo` are builtins, so a
# PATH with nothing on it reaches the SKIP line and nothing else. The first
# version computed HERE with dirname above these, and an empty PATH printed
# "dirname: command not found" and a sourcing error before its own reason.
for tool in python3 openssl prlimit "$UNSHARE_BIN" ip; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP logo-scenario: $tool is not on PATH" >&2; exit $SKIP; }
done
[[ -x $QML_BIN ]] || { echo "SKIP logo-scenario: $QML_BIN is not here (qt6-declarative)" >&2; exit $SKIP; }
if [[ $MODE == live ]]; then
  for tool in node "$CAGE_BIN" quickshell qs; do
    command -v "$tool" >/dev/null 2>&1 || { echo "SKIP logo-scenario: $tool is not on PATH" >&2; exit $SKIP; }
  done
fi
prlimit --as=$CAP_AS -- true 2>/dev/null \
  || { echo "SKIP logo-scenario: prlimit cannot set an address-space limit of $CAP_AS here" >&2; exit $SKIP; }
# Since D-SINK-40 the provider is a global address inside a private network
# namespace, so a machine that cannot make one (unprivileged user namespaces
# off, or no dummy driver) cannot run the scenario at all -- said here, as a
# SKIP, rather than as ten refusals that read like a broken helper. The
# probe makes the same interface the rig makes, in a namespace that is gone
# when it exits.
ns_why=$(timeout -k 2 10 "$UNSHARE_BIN" -rn ip link add d0 type dummy 2>&1) \
  || { echo "SKIP logo-scenario: cannot make a private network namespace with a dummy interface here (\`$UNSHARE_BIN -rn ip link add d0 type dummy\`: ${ns_why:-no reason given}); the provider has to be a global address that exists nowhere else" >&2; exit $SKIP; }
HERE=${BASH_SOURCE[0]%/*}
[[ $HERE == "${BASH_SOURCE[0]}" ]] && HERE=.
HERE=$(cd "$HERE" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
SPIKE="$HERE/spikes/logo-decode-bomb"
for f in make-corpus.py serve-and-fetch.py probe-tmpl.qml peakrun.py; do
  [[ -f $SPIKE/$f ]] || { echo "$SPIKE/$f is missing" >&2; exit 2; }
done
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
LIVE_DISPLAY=${WAYLAND_DISPLAY:-wayland-1}
# This scenario's OWN harness directory (the W segment's shell, and the
# transcript beside it), never the shared default: key-scenario.sh's shape.
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-logo}
export OMARCHY_IPTV_HARNESS_DIR=$SCRATCH
PLUGIN_ROOT=$ROOT
EXPORT_DIR=""
TREE_LINE="== tree $ROOT ($(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git))"
if [[ -n $TREE ]]; then
  PLUGIN_ROOT=$(cd "$TREE" 2>/dev/null && pwd) || { echo "--tree $TREE is not a directory I can enter" >&2; exit 2; }
  [[ -f $PLUGIN_ROOT/Service.qml && -f $PLUGIN_ROOT/bin/omarchy-iptv ]] && qa_model_files "$PLUGIN_ROOT" >/dev/null \
    || { echo "--tree $PLUGIN_ROOT is not a plugin tree (no Service.qml / readable model / bin/omarchy-iptv)" >&2; exit 2; }
  TREE_LINE="== prepared tree $PLUGIN_ROOT"
fi
if [[ -n $BASELINE ]]; then
  git -C "$ROOT" rev-parse --verify -q "$BASELINE^{commit}" >/dev/null \
    || { echo "--baseline '$BASELINE' does not resolve to a commit in this repository" >&2; exit 2; }
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-logo-baseline.XXXXXX") || exit 2
  chmod 0700 "$EXPORT_DIR"
  if ! git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR"; then
    echo "could not export $BASELINE" >&2; rm -rf "$EXPORT_DIR"; exit 2
  fi
  [[ -f $EXPORT_DIR/bin/omarchy-iptv ]] || { echo "$BASELINE holds no bin/omarchy-iptv" >&2; rm -rf "$EXPORT_DIR"; exit 2; }
  PLUGIN_ROOT=$EXPORT_DIR
  TREE_LINE="== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported to $EXPORT_DIR"
fi
HELPER="$PLUGIN_ROOT/bin/omarchy-iptv"

if [[ $MODE == live ]]; then
  # CLAUDE.md parallel rule 7, and F-M3-1: the evidence does not live in
  # whoever remembered to keep stdout. Printed first, so the transcript names
  # itself. Not in check-tree: a gate step may neither print a path nobody
  # asked for nor leave a file behind.
  qa_transcript_start logo || exit 2
fi
echo "$TREE_LINE"
echo "== mode $MODE   helper $HELPER   rlimit AS=$CAP_AS bytes on the qml process only"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-logo.XXXXXX") || exit 2
chmod 0700 "$WORK"
T_START=$(date +%s.%N)
elapsed() { python3 -c 'import sys; print("%.1f" % (float(sys.argv[1]) - float(sys.argv[2])))' "$(date +%s.%N)" "$T_START"; }
OWN_WORK=1
# Every process the W segment starts, by the pid bash handed it or the pid
# the process wrote itself (cage's child, run.sh's qs.pid). Nothing is found
# by a pattern that could match this shell (parallel rule 3).
CAGE_PID=""; CAGE_CHILD=""; SHELL_STARTED=0; SHELL_PID=""; NESTED=""
cleanup() {
  (( OWN_WORK )) || return
  # The shell by its recorded pid (run.sh reap: TERM, a bound, KILL), then
  # cage by its CHILD -- a TERM to cage itself is ignored for 10 s and
  # leaves a stale socket (docs/SPIKE-CAGE-HEADLESS.md) -- so a TERM or an
  # INT landing inside the W segment strands neither (F-HARNESS-18).
  (( SHELL_STARTED )) && env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" reap >/dev/null 2>&1
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  if [[ -n $CAGE_PID ]] && kill -0 "$CAGE_PID" 2>/dev/null; then kill -TERM "$CAGE_PID" 2>/dev/null; wait "$CAGE_PID" 2>/dev/null; fi
  [[ -n ${WORK:-} && -d $WORK ]] && rm -rf "$WORK"
  [[ -n ${EXPORT_DIR:-} && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  return 0
}
trap cleanup EXIT
# A signal while this shell waits on a foreground child runs no EXIT trap;
# an exit does. These two lines turn INT and TERM into exits (the clip-scenario
# shape, F-HARNESS-18), so a `timeout -s TERM` or a Ctrl-C mid-run reaps what
# cleanup reaps instead of stranding the shell, the server or the cage.
trap 'exit 130' INT
trap 'exit 143' TERM
# F-HARNESS-20, a sibling found by measuring rather than by reading. The
# header says the helper runs with HOME and every XDG variable in the scratch
# directory, and it does (serve-and-fetch.py builds that environment); the
# QML probe did not. Run with a decoy HOME and decoy XDG directories on
# 2026-10-13, this check-tree left a Qt cache ("QtProject/Qml Runtime") and an
# fcitx directory in the decoy -- on an ordinary run, the developer's real
# ~/.cache and ~/.config, on every gate run. The whole driver now has a home
# inside WORK, which cleanup() removes -- in check-tree, the gate's arm, so a
# gate step leaves no file behind. The live arm drives run.sh (the W
# segment's shell, the helper that seeds its caches), so its home is the
# harness directory's, the way every other driver of run.sh has it
# (tests/test_harness_home.py pins the call by its argument).
if [[ $MODE == live ]]; then
  qa_harness_home "$SCRATCH" || exit 2
else
  qa_harness_home "$WORK" || exit 2
fi

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL $1${2:+ -- $2}"; }
# One assertion, one line at column zero, so the floor at the foot can be
# counted by recipe.
ck() { local label=$1 got=$2 want=$3; [[ $got == "$want" ]] && pass "$label: $want" || fail "$label" "got [$got], want [$want]"; }

# ---- the corpus. Names are the generator's (rule 13: --only refuses a name
# it does not know rather than producing nothing).
GOOD=good-512.png
AT_BOUND=edge-at-bound.jpg
CACHED_OK=ctl-prog-64.jpg
EXIF_OK=ctl-exif-thumb-64.jpg
# D-LOGO-13: one PNG carrying iCCP, zTXt, iTXt and tEXt that is only served,
# and the same bytes under a second name planted in the cache as well.
META=meta-chunks-64.png
META_PLANTED=meta-chunks-planted-64.png
BOMBS=(bomb-prog-20000.jpg bomb-prog-rgb-20000.jpg bomb-base-65500.jpg
       bomb-png-20000.png bomb-gif-20000.gif bomb-webp-16383.webp valid-png-20000.png
       bomb-exif-thumb-20000.jpg bomb-column-64x65535.jpg bomb-gif-second-frame-65500.gif)
EDGE_SIDE=edge-side-only.jpg
EDGE_PIXELS=edge-pixels-only.jpg
UNREADABLE=unreadable-no-sof.jpg
SINK_BOMB=bomb-prog-20000.jpg
join() { local IFS=,; echo "$*"; }
SERVED=$(join "$GOOD" "$AT_BOUND" "$CACHED_OK" "$EXIF_OK" "${BOMBS[@]}" "$EDGE_SIDE" "$EDGE_PIXELS" "$UNREADABLE" \
  "$META" "$META_PLANTED")
PLANTED=$(join "$CACHED_OK" "${BOMBS[@]}" "$META_PLANTED")
CORPUS="$WORK/corpus"
if ! python3 "$SPIKE/make-corpus.py" "$CORPUS" --only "$SERVED" >"$WORK/corpus.log" 2>&1; then
  cat "$WORK/corpus.log"; echo "make-corpus failed" >&2; exit 2
fi
echo "== corpus: $(grep -c ' bytes ' "$WORK/corpus.log") files, $(du -sh "$CORPUS" | cut -f1)"

# ---- the run: plant, serve, fetch. One helper invocation, inside a
# private network namespace (since D-SINK-40): the rig refuses to run in the
# namespace this shell is in, which it is told by its link, and the bound
# covers the rig's own 60 s deadline on the helper with room to spare.
RIG="$WORK/rig"
OUTER_NETNS=$(readlink "/proc/$$/ns/net")
timeout -k 5 120 "$UNSHARE_BIN" -rn python3 -I "$SPIKE/serve-and-fetch.py" fetch --outer-netns "$OUTER_NETNS" \
  --helper "$HELPER" --corpus "$CORPUS" --work "$RIG" --names "$SERVED" --plant "$PLANTED" \
  --loopback "$GOOD" --timeout 5 --deadline 60 >"$WORK/rig.out" 2>"$WORK/rig.err"
rig_rc=$?
if (( rig_rc == SKIP )); then
  echo "SKIP logo-scenario: $(grep -a '^RIG netns-refused ' "$WORK/rig.out" | head -1 | cut -d' ' -f3-)" >&2; exit $SKIP
fi
if (( rig_rc != 0 )); then
  cat "$WORK/rig.out" "$WORK/rig.err"; echo "the rig did not run (exit $rig_rc)" >&2; exit 2
fi
grep -a '^RIG ' "$WORK/rig.out" | grep -av '^RIG name ' | sed 's/^/   /'
rig_field() { grep -a "^RIG $1 " "$WORK/rig.out" | head -1 | cut -d' ' -f3-; }
name_of() { grep -a "^RIG name $1 " "$WORK/rig.out" | head -1 | awk '{ print $4 }'; }
gets_of() { grep -a "^RIG get $1 " "$WORK/rig.out" | head -1 | awk '{ print $4 }'; }
HELPER_OUT="$RIG/helper.out"; HELPER_ERR="$RIG/helper.err"
LOGO_DIR="$RIG/cache/logos"
TOKEN=$(rig_field token)
HELPER_RC=$(rig_field helper | awk '{ print $2 }')
# The summary is the LAST line of the helper's stdout (D-LOGO-8: one line per
# file as it lands, then the summary object).
SUMMARY=$(tail -n 1 "$HELPER_OUT" 2>/dev/null)
field() { qa_json_field "$1" "$SUMMARY"; }
announced() { field "\"$1\" in d[\"names\"]"; }   # true | false | NOFIELD

# ---- V1: the verb exists on this helper. argparse answers status 2 and
# "invalid choice" / "unrecognized arguments" on stderr when it does not, and
# a status 2 is indistinguishable from a refusal in every check below.
if [[ $HELPER_RC == 2 ]] && grep -qa "invalid choice\|unrecognized arguments" "$HELPER_ERR"; then v1=absent; else v1="present rc=$HELPER_RC"; fi
ck V1 "$v1" "present rc=0"

# ---- V2: the join. The rig computed every planted file's name with its OWN
# fnv1a32; if the helper derives a different name, every "planted" bomb sat
# where the helper never looked and P1..P10 would pass for nothing.
good_name=$(name_of "$GOOD")
if [[ -n $good_name && $(announced "$good_name") == true ]]; then v2=joined; else v2="not-joined(rig=$good_name announced=$(field 'd["names"]'))"; fi
ck V2 "$v2" "joined"

# ---- C1..C4: the controls, which a helper that refuses everything fails.
ondisk() { [[ -f $LOGO_DIR/$1 ]] && echo yes || echo no; }
ck "C1 $GOOD: GET=$(gets_of "$GOOD") announced=$(announced "$good_name") ondisk" "$(gets_of "$GOOD") $(announced "$good_name") $(ondisk "$good_name")" "1 true yes"
ab_name=$(name_of "$AT_BOUND")
ck "C2 $AT_BOUND at the bound exactly: GET announced ondisk" "$(gets_of "$AT_BOUND") $(announced "$ab_name") $(ondisk "$ab_name")" "1 true yes"
ok_name=$(name_of "$CACHED_OK")
ck "C3 $CACHED_OK planted sound: GET announced ondisk" "$(gets_of "$CACHED_OK") $(announced "$ok_name") $(ondisk "$ok_name")" "0 true yes"
ex_name=$(name_of "$EXIF_OK")
ck "C4 $EXIF_OK (a thumbnail JPEG inside its APP1, real frame 64x64): GET announced ondisk" "$(gets_of "$EXIF_OK") $(announced "$ex_name") $(ondisk "$ex_name")" "1 true yes"

# ---- C5 / C6: D-LOGO-13 at the sink that matters, the file the Image will
# read. The chunk list of the cache file, and whether its IDAT is the
# provider's own bytes, read from disk -- not from the helper's word.
canon_of() {
  python3 -I -c '
import struct, sys
def chunks(path):
    data = open(path, "rb").read()
    pos, out = 8, []
    while pos + 12 <= len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        out.append((data[pos + 4:pos + 8].decode("ascii", "replace"), data[pos + 8:pos + 8 + n]))
        pos += 12 + n
    return out
try:
    have, want = chunks(sys.argv[1]), chunks(sys.argv[2])
except OSError:
    print("absent")
    sys.exit(0)
idat = lambda c: b"".join(p for k, p in c if k == "IDAT")
print(",".join(k for k, _ in have) + (" same-idat" if idat(have) == idat(want) else " other-idat"))
' "$LOGO_DIR/$1" "$CORPUS/$2"
}
me_name=$(name_of "$META")
ck "C5 $META (iCCP, zTXt, iTXt, tEXt) fetched: GET announced, and the cache file" \
   "$(gets_of "$META") $(announced "$me_name") $(canon_of "$me_name" "$META")" "1 true IHDR,IDAT,IEND same-idat"
mp_name=$(name_of "$META_PLANTED")
ck "C6 $META_PLANTED planted with them: GET announced, and the cache file rewritten" \
   "$(gets_of "$META_PLANTED") $(announced "$mp_name") $(canon_of "$mp_name" "$META_PLANTED")" "0 true IHDR,IDAT,IEND same-idat"

# ---- P1..P10: the sweep, at the sink that matters -- the directory.
i=0
for bomb in "${BOMBS[@]}"; do
  i=$((i + 1))
  ck "P$i $bomb planted in the cache is" "$([[ -f $LOGO_DIR/$(name_of "$bomb") ]] && echo present || echo swept)" "swept"
done
ck "S1 swept" "$(field 'd["swept"]')" "10"

# ---- G1: and each was refetched exactly once, so the sweep fell through to
# the gate (one bomb, one refusal) rather than to nothing or to a loop.
once=0; detail=""
for bomb in "${BOMBS[@]}"; do
  n=$(gets_of "$bomb"); [[ $n == 1 ]] && once=$((once + 1)) || detail="$detail $bomb=$n"
done
ck "G1 bombs fetched exactly once after the sweep${detail:+ (not:$detail)}" "$once of 10" "10 of 10"

# ---- F1 / F2: the gate's two sinks -- the announcement and the directory.
leaked=""
for bomb in "${BOMBS[@]}"; do [[ $(announced "$(name_of "$bomb")") == false ]] || leaked="$leaked $bomb"; done
ck "F1 bombs announced" "${leaked:-none}" "none"
want_disk=$(printf '%s\n' "$good_name" "$ab_name" "$ok_name" "$ex_name" "$me_name" "$mp_name" | sort | tr '\n' ' ')
have_disk=$(rig_field logos-on-disk | cut -d' ' -f2- | tr ' ' '\n' | sort | tr '\n' ' ')
ck "F2 the logo directory holds exactly the six legitimate names" "$have_disk" "$want_disk"

# ---- R1..R3: the counts the service reads.
ck "R1 reasons.logo_dimensions" "$(field 'd["reasons"].get("logo_dimensions")')" "13"
lb_name=$(grep -a "^RIG name-loopback $GOOD " "$WORK/rig.out" | head -1 | awk '{ print $4 }')
lb_gets=$(grep -a "^RIG get-loopback $GOOD " "$WORK/rig.out" | head -1 | awk '{ print $4 }')
ck "R2 refusedOnPolicy, reasons.local_address, GETs at 127.0.0.1, the 127.0.0.1 logo announced" \
   "$(field 'd["refusedOnPolicy"]') $(field 'd["reasons"].get("local_address")') ${lb_gets:-NA} $(announced "${lb_name:-NA}")" "14 1 0 false"
ck "R3 fetched cached" "$(field 'd["fetched"]') $(field 'd["cached"]')" "4 2"

# ---- E1..E3: the two bounds driven apart, and the unreadable header.
ck "E1 $EDGE_SIDE (5000x800: side over, pixels under) announced" "$(announced "$(name_of "$EDGE_SIDE")")" "false"
ck "E2 $EDGE_PIXELS (2048x2049: pixels over, sides under) announced" "$(announced "$(name_of "$EDGE_PIXELS")")" "false"
ck "E3 $UNREADABLE (magic bytes, no frame header) announced" "$(announced "$(name_of "$UNREADABLE")")" "false"

# ---- M1 / M2: the numbers the README states, as the summary carries them.
ck "M1 maxSide" "$(field 'd["maxSide"]')" "4096"
ck "M2 maxPixels" "$(field 'd["maxPixels"]')" "4194304"

# ---- T1: the refusal text. `logos --fetch` swallows it into a count, so the
# sink it reaches is the function's own return value; call the shipping
# function from the tree under test (rule 14 allows that), with a URL whose
# path carries a token the text must not echo.
t1_url="https://localhost:8443/$TOKEN/$SINK_BOMB"
t1=$(python3 "$SPIKE/serve-and-fetch.py" refusal --helper "$HELPER" --corpus "$CORPUS" --name "$SINK_BOMB" --url "$t1_url" 2>&1 | grep -a '^RIG ' | head -1)
if [[ $t1 == "RIG refusal "* ]]; then
  text=${t1#RIG refusal }
  echo "   T1 text: $text"
  t1v="host"; [[ $text == *localhost* ]] || t1v="no-host"
  [[ $text == *20000x20000* ]] && t1v="$t1v numbers" || t1v="$t1v no-numbers"
  if [[ $text == *"$TOKEN"* || $text == *"https://"* || $text == *"$SINK_BOMB"* ]]; then t1v="$t1v URL-LEAKED"; else t1v="$t1v no-url"; fi
else
  t1v="absent"
fi
ck "T1 the refusal text carries" "$t1v" "host numbers no-url"

# ---- T2: rule 5 over everything the helper printed on either stream.
if grep -qa -- "$TOKEN" "$HELPER_OUT" "$HELPER_ERR"; then t2="leaked: $(grep -a -o -- ".\{0,20\}$TOKEN.\{0,12\}" "$HELPER_OUT" "$HELPER_ERR" | head -1)"; else t2=clean; fi
ck "T2 the helper's streams carry the URL path token" "$t2" "clean"

# ---- the sink. probe <file> -> "rc=<n> peak_mb=<n>"; the only invocation
# that keeps the desktop safe (spikes/logo-decode-bomb/run.sh says why): the
# rlimit wraps the qml process alone -- prlimit execs the command in place
# (measured: the pid it runs under is the pid peakrun spawned) -- and never
# the reporter, which reads ru_maxrss from outside the limit.
probe() {
  local file=$1 qml="$WORK/probe-$RANDOM.qml" out line rc kb
  sed -e "s|__PATH__|$file|" -e "s|__SOURCE_SIZE__|44|" "$SPIKE/probe-tmpl.qml" >"$qml"
  out=$(PEAKRUN_TIMEOUT=90 python3 "$SPIKE/peakrun.py" prlimit --as=$CAP_AS -- \
          env QT_QPA_PLATFORM=offscreen "$QML_BIN" "$qml" 2>&1)
  line=$(printf '%s\n' "$out" | grep -a '^PEAKRUN ' | tail -1)
  rc=$(printf '%s' "$line" | sed -n 's/.*rc=\(-\{0,1\}[0-9]*\).*/\1/p')
  kb=$(printf '%s' "$line" | sed -n 's/.*peak_rss_kb=\([0-9]*\).*/\1/p')
  [[ -n $rc && -n $kb ]] && printf 'rc=%s peak_mb=%d\n' "$rc" "$((kb / 1024))" || printf 'rc=NA peak_mb=NA\n'
}
# K1: the positive control at the sink.
if [[ -f $LOGO_DIR/$good_name ]]; then
  r=$(probe "$LOGO_DIR/$good_name"); rc=${r#rc=}; rc=${rc%% *}; mb=${r#*peak_mb=}
  echo "   K1 probe on $GOOD: $r"
  if [[ $rc == 0 ]] && [[ $mb =~ ^[0-9]+$ ]] && (( mb < CONTROL_MB )); then k1="ready control-memory"; else k1="rc=$rc peak_mb=$mb"; fi
else
  k1="no file to decode"
fi
ck "K1 the good logo at the sink (control: under $CONTROL_MB MB)" "$k1" "ready control-memory"
# K2: the bomb never reaches the sink. Three outcomes, named for what
# happened rather than for what the check wanted: the first version said
# "announced" whenever the pass condition failed, including on a run where
# the name WAS withheld and only the file survived an unlink failure, so its
# evidence line stated the opposite of what the cache held. On a tree that
# announces it, live decodes it under the cap so the red line carries the
# number; check-tree never decodes a bomb.
sb_name=$(name_of "$SINK_BOMB")
if [[ $(announced "$sb_name") == false ]]; then
  if [[ -f $LOGO_DIR/$sb_name ]]; then
    k2="withheld-but-file-survived ($(stat -c %s "$LOGO_DIR/$sb_name") bytes still at $LOGO_DIR/$sb_name)"
  else
    k2=withheld-and-gone
  fi
elif [[ $MODE == live && -f $LOGO_DIR/$sb_name ]]; then
  r=$(probe "$LOGO_DIR/$sb_name")
  echo "   K2 probe on the ANNOUNCED $SINK_BOMB ($(stat -c %s "$LOGO_DIR/$sb_name") bytes): $r"
  k2="announced $r"
elif [[ -f $LOGO_DIR/$sb_name ]]; then
  k2="announced (not decoded in $MODE)"
else
  k2="announced, and the file is not on disk (announced=$(announced "$sb_name"))"
fi
ck "K2 $SINK_BOMB at the sink" "$k2" "withheld-and-gone"

# ------------------------------------------------- the W segment (live only)
# The real Service.qml under a nested headless cage of this scenario's own,
# driven over IPC through the harness shell: key-scenario.sh's cage_start /
# cage_stop / start_shell / stop_shell shapes, trimmed to what one switch
# needs. Every value asserted is read off the running shell (`ipc state`:
# the guide's `logoCount`, `logoHaveDir`, `logoDir`), never off a file.
# F-HARNESS-45: the nested cage renders with pixman, so a player started toward
# it gets run.sh's software-GPU lever (harness_env appends --gpu-sw=yes and
# --ao=null to the mpvArgs). Since D-PLY-27 the base argv carries --gpu-sw=yes
# itself, so on this tree the lever's job is --ao=null (the cage's player stays
# off the user's sound server); on an older tree, such as a --baseline ref
# through 0.15.0, mpv 0.41.0 aborts in its VO probe without it.
h()    { env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" OMARCHY_IPTV_HARNESS_SOFTWARE_GPU=1 "$RUN" "$@"; }
ipc()  { h ipc "$@" 2>/dev/null; }
svc()  { qa_field "d$1" "$(ipc state)"; }
# One state read, three fields: "<logoDir>|<logoHaveDir>|<logoCount>", with
# None for a tag that is not there ({} is "nothing announced"); NOSTATE when
# the shell did not answer.
logo_sample() { qa_guide_field "'%s|%s|%s' % (d.get('logoDir'), d.get('logoHaveDir'), d.get('logoCount'))" "$(ipc state)"; }
# The tree under test's own joins, called and not mirrored (rule 12): the
# key a path gets, the logo directory a cache directory gets, and the file
# name a logo URL gets -- the helper's logo_filename is fnv1a32(url), and the
# model's fnv1a32 matches it byte for byte (bin/helper/01-core.py). The
# first file qa_model_files names is the aggregator node requires.
model_file() { qa_model_files "$PLUGIN_ROOT" | head -n 1; }
key_of() { node -e 'const M = require(process.argv[1]); const n = M.normalizeSourceUrl(process.argv[2], { origin: "cli" }); process.stdout.write(n === "" ? "" : M.sourceKey(n))' "$(model_file)" "$1"; }
logo_dir_of() { node -e 'const M = require(process.argv[1]); process.stdout.write(M.logoDirFor(process.argv[2]))' "$(model_file)" "$1"; }
logo_name_of() { node -e 'const M = require(process.argv[1]); process.stdout.write(M.fnv1a32(process.argv[2]))' "$(model_file)" "$1"; }
record() {
  local key=$1 url=$2 label=$3 count=$4
  python3 -c 'import json, sys; print(json.dumps({"key": sys.argv[1], "url": sys.argv[2], "epgUrl": "", "kind": "file", "label": sys.argv[3], "labelCustom": False, "origin": "cli", "addedAt": 1799990000, "lastUsed": 1799990000, "fetchedAt": 1799990000, "channelCount": int(sys.argv[4]), "groupCount": 1}))' "$key" "$url" "$label" "$count"
}
# A playlist of N channels whose logos live on one .invalid host: nothing
# resolves it, and nothing needs to -- every logo is planted below.
write_playlist() {
  local out=$1 host=$2 tag=$3 n=$4 i
  {
    echo "#EXTM3U"
    for ((i = 1; i <= n; i++)); do
      printf '#EXTINF:-1 tvg-id="%s%d" tvg-logo="https://%s/%d.png" group-title="%s",%s %d\n' "$tag" "$i" "$host" "$i" "$tag" "$tag" "$i"
      printf 'http://127.0.0.1:9/dead/%s%d.m3u8\n' "$tag" "$i"
    done
  } >"$out"
}
# Plant the within-bound control (good-512.png, canonical: IHDR, IDAT, IEND)
# under the name the helper derives for each logo URL of a playlist, 0600 in
# a 0700 logos directory, so `logos --fetch` finds every one on disk and
# announces it from the cached-file branch with no request.
plant_logos() {
  local playlist=$1 logo_dir=$2 url name
  mkdir -p "$logo_dir" && chmod 0700 "$logo_dir"
  while IFS= read -r url; do
    name=$(logo_name_of "$url")
    cp "$CORPUS/$GOOD" "$logo_dir/$name" && chmod 0600 "$logo_dir/$name"
  done < <(grep -o 'tvg-logo="[^"]*"' "$playlist" | cut -d'"' -f2)
}
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
    echo "SKIP logo-scenario: cage did not bring up a nested display within 10 s ($(tr '\n' ' ' <"$WORK/cage.log" | head -c 300))" >&2
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
# Bounded 20 s; a shell that never settles is reported, not waited on.
start_shell() {
  h --detach --timeout 0 --keep "$@" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  local i
  for ((i = 0; i < 200; i++)); do
    [[ $(svc "['stateLoaded']") == true && $(svc "['cacheReady']") == true ]] && return 0
    sleep 0.1
  done
  echo "   the shell (pid $SHELL_PID) did not settle within 20 s: $(tail -n 3 "$WORK/start.log" | tr '\n' ' ')"
  return 1
}
stop_shell() {
  h shell-stop >/dev/null 2>&1; local i
  for ((i = 0; i < 50; i++)); do kill -0 "$SHELL_PID" 2>/dev/null || break; sleep 0.1; done
  SHELL_STARTED=0; [[ -z $SHELL_PID ]] || kill -0 "$SHELL_PID" 2>/dev/null && echo "   the shell $SHELL_PID outlived shell-stop" || true
}
# wait_for <want> <secs> <cmd...>: until cmd prints want; says when it gave up.
wait_for() {
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do [[ $("$@") == "$want" ]] && return 0; sleep 0.1; done
  echo "   gave up waiting ${secs}s for '$want' from: $*"
  return 1
}
# switch_and_sample <key> <want-dir> <want-count>: ask for the switch, then
# read the shell as fast as IPC answers until the set has rebuilt for the
# directory asked for (or 15 s). Leaves FIRST (the first sample whose
# logoDir is the wanted one), STRAY (every sample carrying a non-empty set
# tagged for a directory other than the one under it) and LAST.
FIRST=""; STRAY=""; LAST=""; SAMPLES=0
switch_and_sample() {
  local key=$1 want_dir=$2 want_count=$3 i smp dir have count
  FIRST=""; STRAY=""; LAST=""; SAMPLES=0
  ipc switchSource "$key" >/dev/null
  for ((i = 0; i < 300; i++)); do
    smp=$(logo_sample); SAMPLES=$((SAMPLES + 1))
    dir=${smp%%|*}; have=${smp#*|}; have=${have%%|*}; count=${smp##*|}
    [[ -z $FIRST && $dir == "$want_dir" ]] && FIRST=$smp
    [[ $count =~ ^[0-9]+$ && $count -gt 0 && $have != "$dir" ]] && STRAY="$STRAY [$smp]"
    LAST=$smp
    [[ $dir == "$want_dir" && $have == "$want_dir" && $count == "$want_count" ]] && return 0
    sleep 0.05
  done
  return 1
}
two_source_segment() {
  local A B KA KB DIR_A DIR_B LOGOS_A LOGOS_B CACHE STATE smp i
  echo "== W: two sources, two logo sets, one switch each way, on the real Service.qml under cage (plugin tree $PLUGIN_ROOT) ($(elapsed) s)"
  cage_start 300
  # The stub compositor in front of PATH and HYPRLAND_INSTANCE_SIGNATURE
  # unset (h): the service's hyprctl probe stops at the stub and nothing can
  # reach the user's compositor from here (pip- and key-scenario's shape).
  mkdir -p "$SCRATCH/bin" && ln -sfn "$HERE/stub-hyprctl.py" "$SCRATCH/bin/hyprctl"
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT
  h reap >/dev/null 2>&1; h clean >/dev/null 2>&1
  CACHE="$SCRATCH/cache/omarchy-iptv"; STATE="$SCRATCH/state/omarchy-iptv/state.json"
  A="$WORK/a-six.m3u"; B="$WORK/b-four.m3u"
  write_playlist "$A" logos-a.invalid A 6
  write_playlist "$B" logos-b.invalid B 4
  KA=$(key_of "$A"); KB=$(key_of "$B")
  DIR_A="$CACHE/sources/$KA"; DIR_B="$CACHE/sources/$KB"
  LOGOS_A=$(logo_dir_of "$DIR_A"); LOGOS_B=$(logo_dir_of "$DIR_B")
  mkdir -p "$DIR_A" "$DIR_B" "$(dirname "$STATE")"
  chmod 0700 "$CACHE" "$CACHE/sources" "$DIR_A" "$DIR_B" "$(dirname "$STATE")"
  python3 "$HELPER" playlist --url "$A" --cache-dir "$DIR_A" >/dev/null 2>&1
  python3 "$HELPER" playlist --url "$B" --cache-dir "$DIR_B" >/dev/null 2>&1
  [[ -f $DIR_A/channels.json && -f $DIR_B/channels.json ]] || echo "   the helper did not write the two caches"
  plant_logos "$A" "$LOGOS_A"; plant_logos "$B" "$LOGOS_B"
  printf '{"version":2,"cacheLayout":2,"favorites":[],"recents":[],"lastPlayed":null,"session":null,"sources":[%s,%s],"savedSearches":[],"hiddenGroups":[],"activeKey":"%s","entryMigrated":true}\n' \
    "$(record "$KA" "$A" "a-six" 6)" "$(record "$KB" "$B" "b-four" 4)" "$KA" >"$STATE"
  chmod 0600 "$STATE"
  echo "   keys: A $KA (6 logos planted in $LOGOS_A)  B $KB (4 in $LOGOS_B)"
  start_shell --playlist none --source-key "$KA" || true
  wait_for 6 10 svc "['channels']" >/dev/null || true
  ipc set showLogos true >/dev/null
  # The first fetch: the planted names announced from the cached-file
  # branch; bounded 15 s, the last sample is what W1 reads either way.
  for ((i = 0; i < 150; i++)); do smp=$(logo_sample); [[ ${smp##*|} == 6 ]] && break; sleep 0.1; done
  ck "W1 over A with logos on (dir|tag|count)" "$smp" "$LOGOS_A|$LOGOS_A|6"
  switch_and_sample "$KB" "$LOGOS_B" 4 || true
  echo "   switch A->B: $SAMPLES samples; first at B's directory [$FIRST]; last [$LAST]"
  ck "W2 the first sample at B's directory: the set is EMPTY (dir|tag|count)" "$FIRST" "$LOGOS_B|None|0"
  ck "W3 samples carrying a set tagged for another directory than the one under it" "${STRAY:-none}" "none"
  ck "W4 the set rebuilt from B's announced names alone (dir|tag|count)" "$LAST" "$LOGOS_B|$LOGOS_B|4"
  switch_and_sample "$KA" "$LOGOS_A" 6 || true
  echo "   switch B->A: $SAMPLES samples; first at A's directory [$FIRST]; last [$LAST]"
  ck "W5 the first sample back at A's directory: the set is EMPTY (dir|tag|count)" "$FIRST" "$LOGOS_A|None|0"
  ck "W6 the set rebuilt from A's announced names alone (dir|tag|count)" "$LAST" "$LOGOS_A|$LOGOS_A|6"
  stop_shell
  cage_stop
  ck "W7 the shell, the cage and the nested socket at the end" "$STOP_VERDICT$([[ -n $SHELL_PID ]] && kill -0 "$SHELL_PID" 2>/dev/null && echo " shell($SHELL_PID)")" "gone"
  echo "== W segment done ($(elapsed) s)"
}
[[ $MODE == live ]] && two_source_segment

# The floor. A check that stops executing must turn the run red rather than
# quietly shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ck "?[A-Z]' logo-scenario.sh    -> 24, the column-zero ck calls
# plus the P loop, whose one ck line is indented inside `for` and runs once
# per bomb, ${#BOMBS[@]} = 10 times: 24 + 10 = 34. The definition of ck() does
# not match the recipe and the floor's own line -- not a `ck` -- cannot count
# itself. The first version of this recipe read `^ck [A-Z]` and counted 2,
# because every label but V1 and V2 opens with a quote; a recipe that does
# not reproduce the floor is the off-by-one the lead has been bitten by.
# Never lower the floor to make a run green, and keep it a LITERAL: derived
# from ${#BOMBS[@]} it would follow a bomb quietly deleted from the array.
# 28 -> 32 on 2026-10-11: three reviewer bombs (P8..P10) and the EXIF control
# (C4). 32 -> 34 on 2026-10-29 (lane-p1c): C5 and C6, the first checks this
# scenario has that observe D-LOGO-13 (a canonical_png that returned its
# input unchanged read 33 passed, 0 failed here before them).
# scripts/check.sh's LOGO_PREFLIGHT_MIN is this plus one, and
# scripts/qa-lib-test.sh asserts that join.
EXPECTED_CHECKS=34
# The live arm adds the W segment: the `ck "W<n>` lines inside
# two_source_segment, indented so the column-zero recipe above does not count
# them; scripts/qa-lib-test.sh asserts this number against that count.
[[ $MODE == live ]] && EXPECTED_CHECKS=$((EXPECTED_CHECKS + 7))
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  pass "the scenario ran every check it has ($ran)"
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi

if [[ -n $BASELINE ]]; then
  echo "baseline $BASELINE: P1..P10, S1, G1, F1, F2, R1, R2, R3, E1, E2, E3, M1, M2, T1 and K2 are expected RED here -- that helper announces and writes every bomb, sweeps nothing, reports neither bound and has no refusal function; K2's line carries what the Image did with the announced 304 bytes. V1, V2, C1, C2, C3, C4, T2 and K1 pass on both trees: they are controls, not discriminators."
  echo "baseline $BASELINE: W1..W6 are expected RED on a tree from before D-LOGO-11 (no tagged set, no logoHaveDir) and read for information only; W7 is a control."
fi
echo "logo-scenario: $PASS passed, $FAIL failed (mode $MODE, helper $HELPER${BASELINE:+, baseline $BASELINE})"
(( FAIL == 0 ))
