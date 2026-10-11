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
#   F2  the logo directory holds exactly the four legitimate names
#   R1  reasons.logo_dimensions == 13   (10 bombs + 2 edges + the unreadable)
#   R2  refusedOnPolicy == 13
#   R3  fetched == 3, cached == 1
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
#
# MODES. `check-tree` (what scripts/check.sh runs on every commit: no
# transcript, no network beyond loopback, no display, no bomb decoded, under
# 20 s) and `live` (the default: a transcript, the same checks, and the
# --baseline lever). Both need python3, openssl, util-linux prlimit and
# /usr/lib/qt6/bin/qml; a machine without them exits 77 with the reason,
# never 0, and the tool checks run BEFORE anything else so the reason is the
# first line out even with an empty PATH. LOGO_QML_BIN overrides the qml
# path; it exists so the 77 path can be driven on a machine that has qml.
#
# Holds no display: starts no quickshell, no mpv, sends no keystroke, reads
# nothing from the live install, touches nothing under ~/.config, ~/.cache or
# ~/.local/state (the helper is run with HOME and every XDG variable pointed
# into the scratch directory).
set -uo pipefail
QML_BIN=${LOGO_QML_BIN:-/usr/lib/qt6/bin/qml}
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
  *) echo "usage: logo-scenario.sh [check-tree|live] [--baseline <ref>]" >&2; exit 2 ;;
esac
BASELINE=""
while (( $# )); do
  case $1 in
    --baseline)
      # Refused rather than defaulted, as tls-scenario.sh's is: a dropped ref
      # would silently grade the current tree and call it a baseline.
      [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--baseline needs a git ref, and got '${2:-}'" >&2; exit 2; }
      BASELINE=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

# ---- refusals, above the transcript (qa-lib.sh item 3) and above every
# external command: `command -v`, `[[ -x ]]` and `echo` are builtins, so a
# PATH with nothing on it reaches the SKIP line and nothing else. The first
# version computed HERE with dirname above these, and an empty PATH printed
# "dirname: command not found" and a sourcing error before its own reason.
for tool in python3 openssl prlimit; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP logo-scenario: $tool is not on PATH" >&2; exit $SKIP; }
done
[[ -x $QML_BIN ]] || { echo "SKIP logo-scenario: $QML_BIN is not here (qt6-declarative)" >&2; exit $SKIP; }
prlimit --as=$CAP_AS -- true 2>/dev/null \
  || { echo "SKIP logo-scenario: prlimit cannot set an address-space limit of $CAP_AS here" >&2; exit $SKIP; }
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
HELPER="$ROOT/bin/omarchy-iptv"
EXPORT_DIR=""
TREE_LINE="== tree $ROOT ($(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git))"
if [[ -n $BASELINE ]]; then
  git -C "$ROOT" rev-parse --verify -q "$BASELINE^{commit}" >/dev/null \
    || { echo "--baseline '$BASELINE' does not resolve to a commit in this repository" >&2; exit 2; }
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-logo-baseline.XXXXXX") || exit 2
  chmod 0700 "$EXPORT_DIR"
  if ! git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR"; then
    echo "could not export $BASELINE" >&2; rm -rf "$EXPORT_DIR"; exit 2
  fi
  [[ -f $EXPORT_DIR/bin/omarchy-iptv ]] || { echo "$BASELINE holds no bin/omarchy-iptv" >&2; rm -rf "$EXPORT_DIR"; exit 2; }
  HELPER="$EXPORT_DIR/bin/omarchy-iptv"
  TREE_LINE="== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported to $EXPORT_DIR"
fi

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
OWN_WORK=1
cleanup() {
  (( OWN_WORK )) || return
  [[ -n ${WORK:-} && -d $WORK ]] && rm -rf "$WORK"
  [[ -n ${EXPORT_DIR:-} && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
}
trap cleanup EXIT

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
BOMBS=(bomb-prog-20000.jpg bomb-prog-rgb-20000.jpg bomb-base-65500.jpg
       bomb-png-20000.png bomb-gif-20000.gif bomb-webp-16383.webp valid-png-20000.png
       bomb-exif-thumb-20000.jpg bomb-column-64x65535.jpg bomb-gif-second-frame-65500.gif)
EDGE_SIDE=edge-side-only.jpg
EDGE_PIXELS=edge-pixels-only.jpg
UNREADABLE=unreadable-no-sof.jpg
SINK_BOMB=bomb-prog-20000.jpg
join() { local IFS=,; echo "$*"; }
SERVED=$(join "$GOOD" "$AT_BOUND" "$CACHED_OK" "$EXIF_OK" "${BOMBS[@]}" "$EDGE_SIDE" "$EDGE_PIXELS" "$UNREADABLE")
PLANTED=$(join "$CACHED_OK" "${BOMBS[@]}")
CORPUS="$WORK/corpus"
if ! python3 "$SPIKE/make-corpus.py" "$CORPUS" --only "$SERVED" >"$WORK/corpus.log" 2>&1; then
  cat "$WORK/corpus.log"; echo "make-corpus failed" >&2; exit 2
fi
echo "== corpus: $(grep -c ' bytes ' "$WORK/corpus.log") files, $(du -sh "$CORPUS" | cut -f1)"

# ---- the run: plant, serve, fetch. One helper invocation.
RIG="$WORK/rig"
if ! python3 "$SPIKE/serve-and-fetch.py" fetch --helper "$HELPER" --corpus "$CORPUS" --work "$RIG" \
       --names "$SERVED" --plant "$PLANTED" --timeout 5 --deadline 60 >"$WORK/rig.out" 2>"$WORK/rig.err"; then
  cat "$WORK/rig.out" "$WORK/rig.err"; echo "the rig did not run" >&2; exit 2
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
want_disk=$(printf '%s\n' "$good_name" "$ab_name" "$ok_name" "$ex_name" | sort | tr '\n' ' ')
have_disk=$(rig_field logos-on-disk | cut -d' ' -f2- | tr ' ' '\n' | sort | tr '\n' ' ')
ck "F2 the logo directory holds exactly the four legitimate names" "$have_disk" "$want_disk"

# ---- R1..R3: the counts the service reads.
ck "R1 reasons.logo_dimensions" "$(field 'd["reasons"].get("logo_dimensions")')" "13"
ck "R2 refusedOnPolicy" "$(field 'd["refusedOnPolicy"]')" "13"
ck "R3 fetched cached" "$(field 'd["fetched"]') $(field 'd["cached"]')" "3 1"

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

# The floor. A check that stops executing must turn the run red rather than
# quietly shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ck "?[A-Z]' logo-scenario.sh    -> 22, the column-zero ck calls
# plus the P loop, whose one ck line is indented inside `for` and runs once
# per bomb, ${#BOMBS[@]} = 10 times: 22 + 10 = 32. The definition of ck() does
# not match the recipe and the floor's own line -- not a `ck` -- cannot count
# itself. The first version of this recipe read `^ck [A-Z]` and counted 2,
# because every label but V1 and V2 opens with a quote; a recipe that does
# not reproduce the floor is the off-by-one the lead has been bitten by.
# Never lower the floor to make a run green, and keep it a LITERAL: derived
# from ${#BOMBS[@]} it would follow a bomb quietly deleted from the array.
# 28 -> 32 on 2026-10-11: three reviewer bombs (P8..P10) and the EXIF control
# (C4). scripts/check.sh's LOGO_PREFLIGHT_MIN is this plus one, and
# scripts/qa-lib-test.sh asserts that join.
EXPECTED_CHECKS=32
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  pass "the scenario ran every check it has ($ran)"
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi

if [[ -n $BASELINE ]]; then
  echo "baseline $BASELINE: P1..P10, S1, G1, F1, F2, R1, R2, R3, E1, E2, E3, M1, M2, T1 and K2 are expected RED here -- that helper announces and writes every bomb, sweeps nothing, reports neither bound and has no refusal function; K2's line carries what the Image did with the announced 304 bytes. V1, V2, C1, C2, C3, C4, T2 and K1 pass on both trees: they are controls, not discriminators."
fi
echo "logo-scenario: $PASS passed, $FAIL failed (mode $MODE, helper $HELPER${BASELINE:+, baseline $BASELINE})"
(( FAIL == 0 ))
