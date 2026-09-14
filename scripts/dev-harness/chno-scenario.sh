#!/bin/bash
# scripts/dev-harness/chno-scenario.sh -- scripted verification of channel
# numbers on the SERVICE side (M2-03 Lane B): the `channel` IPC verb, the
# chno index, channelOrder and the bar's number slot. No guide keystrokes,
# so it needs no window focus; scenarios N1-N18 and N21 (digit entry in the
# guide) belong to Lane A and are not here.
#
#   chno-scenario.sh check-tree     the capability preflight ONLY; no display,
#                                   no quickshell, no player. Exit 0 when the
#                                   tree under test can answer what the live
#                                   half asks, non-zero when it cannot.
#   chno-scenario.sh [live]         the preflight, then the live half.
#
# WHY A PREFLIGHT EXISTS AT ALL. Every question below is asked over IPC, and
# a harness whose plugin tree lacks the verb answers with an empty string or
# `no_verb` rather than an error. Several of these checks would then be
# VACUOUS rather than red - the exact failure CLAUDE.md rule 11 and
# scripts/qa-lib.sh were written for. So the tree is asked, up front and
# cheaply, whether it has the seams at all; that check is also what a lane
# without a display can run against a pre-change export to show this file
# detects the feature's absence (rule 10).
#
# The preflight is NOT the behavioural evidence: it proves the code is there,
# never that it works. Only the live half does that, and only on the machine
# of record.
#
# Live half (design section 10.6):
#   N19  the `channel` verb: exact, leading zeros, `-` as the subchannel
#        separator, an unknown number, junk, and `status` carrying chno and
#        hasNumbers with no URL anywhere
#   N20  the bar: the number in the label and in the tooltip, and what
#        barShowChannelNumber false changes
#   N17  channelOrder number: All is numerically ordered, unnumbered last
#   N18  the same setting flipped at runtime: no helper run
#
# The fixture (fixtures/harness.m3u.in) carries 20 channels, 15 of them
# numbered: a duplicate pair (501), two subchannels (7.1, 7.2), a dash form
# (8-1 -> 8.1), leading zeros (0042 -> 42), a non-numeric value (N/A, which
# is NOT a number, CN6) and both alias attributes (1000, 1001).
#
# `channel` PLAYS (CN1), so the live half starts the harness player against
# the fixture's dead URLs exactly as player-scenario.sh does.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
# The tree under test: the plugin QML, the helper and the manifest come from
# here, while the harness fake is always THIS checkout's (run.sh stages it).
PLUGIN_ROOT=$(cd "${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}" 2>/dev/null && pwd)
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
CACHE="$SCRATCH/cache/omarchy-iptv"
FIX="$SCRATCH/fixtures"
LOG="$SCRATCH/chno-scenario.log"
HARNESS_PID=""
pass=0
fail=0
checks=0

# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

ok()   { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad()  { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
check() { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }
ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
py()   { python3 -c 'import json,sys; d=json.loads(sys.argv[2]); v=eval(sys.argv[1]); print(json.dumps(v) if isinstance(v, bool) else v)' "$1" "$2" 2>/dev/null; }
svc()  { py "d['service']$1" "$(ipc state)"; }

cleanup() {
  if [[ -n $HARNESS_PID ]]; then kill -TERM "$HARNESS_PID" 2>/dev/null; wait "$HARNESS_PID" 2>/dev/null; fi
  return 0
}

cache_mtime() { stat -c %Y "$CACHE/channels.json" 2>/dev/null; }

wait_for() {   # wait_for <want> <secs> <cmd...>: bounded, and it SAYS it gave up
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ "$("$@")" == "$want" ]] && return 0
    sleep 0.1
  done
  echo "[chno-scenario] gave up waiting ${secs}s for '$want' from: $*" >&2
  return 1
}

# ---------------------------------------------------------------- preflight
#
# `seam <label> <file> <ere> <at least>`: a POSITIVE count, never a `! grep`.
# qa_count answers 0 for a missing or unreadable file, so a tree without the
# file fails here instead of passing an absence test. The bound is a MINIMUM
# on purpose: this asks whether the seam exists, and an exact count would go
# red on a rename that changes nothing about the answer.
seam() {
  local label=$1 file=$2 ere=$3 want=$4
  checks=$((checks + 1))
  local got
  got=$(qa_count "$ere" "$file")
  if (( got >= want )); then ok "$label"; else bad "$label (matched $got, wanted at least $want in ${file#"$PLUGIN_ROOT/"})"; fi
}

preflight() {
  echo "== preflight: can this tree answer the live half? (plugin: $PLUGIN_ROOT)"
  seam "Service.qml declares the channel-number index"      "$PLUGIN_ROOT/Service.qml"  '^ *property var chnoIndex' 1
  seam "Service.qml resolves a number to a channel"         "$PLUGIN_ROOT/Service.qml"  '^ *function channelByNumber\(text\)' 1
  seam "Service.qml has the tuneByNumber the harness calls" "$PLUGIN_ROOT/Service.qml"  '^ *function tuneByNumber\(text\)' 1
  seam "Service.qml exposes the IPC channel verb"           "$PLUGIN_ROOT/Service.qml"  'function channel\(n: string\): string' 1
  seam "status carries hasNumbers"                          "$PLUGIN_ROOT/Service.qml"  'hasNumbers: root\.chnoIndex' 1
  seam "nowPlaying carries the number"                      "$PLUGIN_ROOT/Service.qml"  'chno: root\.nowPlayingChno' 1
  seam "channelOrder re-derives the list"                   "$PLUGIN_ROOT/Service.qml"  'onChannelOrderChanged' 1
  seam "BarWidget.qml knows the playing number"             "$PLUGIN_ROOT/BarWidget.qml" 'nowPlayingChno' 3
  seam "BarWidget.qml can hide it"                          "$PLUGIN_ROOT/BarWidget.qml" 'barShowChannelNumber' 1
  seam "the manifest declares channelOrder"                 "$PLUGIN_ROOT/manifest.json" '"channelOrder"' 2
  seam "the manifest declares numberEntryMs"                "$PLUGIN_ROOT/manifest.json" '"numberEntryMs"' 2
  seam "the manifest declares barShowChannelNumber"         "$PLUGIN_ROOT/manifest.json" '"barShowChannelNumber"' 2
  seam "the harness passes the channel verb through"      "$HERE/shell.qml"                       'function channel\(n: string\): string' 1
  seam "the harness reports the index"                      "$HERE/shell.qml"            'function chnoIndex\(\): string' 1
}

# ------------------------------------------------------------------- live
live() {
  echo "== setup (scratch $SCRATCH)"
  "$RUN" clean >/dev/null
  mkdir -p "$FIX" "$CACHE"
  sed "s|__LIVE__|http://127.0.0.1:9/dead/live.m3u8|g" "$HERE/fixtures/harness.m3u.in" >"$FIX/harness.m3u"
  : >"$LOG"

  echo "== start harness (--order playlist)"
  HARNESS_TIMEOUT=${OMARCHY_IPTV_SCENARIO_TIMEOUT:-300}
  "$RUN" --keep --timeout "$HARNESS_TIMEOUT" --playlist "$FIX/harness.m3u" >>"$LOG" 2>&1 &
  HARNESS_PID=$!
  wait_for 20 30 svc "['channels']" || bad "the fixture playlist never loaded; every check below is about nothing"

  echo "== N19 the channel verb"
  # 15 of the fixture's 20 rows carry a usable number; ZDF's "N/A" is not one
  # (CN6) and four rows have no attribute at all.
  check "the index sees the fixture's 15 numbered channels" '[[ "$(py "d['\''count'\'']" "$(ipc chnoIndex)")" == 15 ]]'
  check "it counts the duplicate pair"                      '[[ "$(py "d['\''duplicates'\'']" "$(ipc chnoIndex)")" == 2 ]]'
  check "it measures the widest label (1001)"               '[[ "$(py "d['\''maxLabelLen'\'']" "$(ipc chnoIndex)")" == 4 ]]'
  check "the playlist reports that it has numbers"          '[[ "$(py "d['\''hasNumbers'\'']" "$(ipc chnoIndex)")" == true ]]'
  a101=$(ipc channel 101)
  check "channel 101 answers ok"                            '[[ "$(py "d['\''ok'\'']" "$a101")" == true ]]'
  check "channel 101 names the channel and its number"      '[[ "$(py "d['\''name'\'']" "$a101")" == "BBC One HD" && "$(py "d['\''chno'\'']" "$a101")" == "101" ]]'
  check "channel 101 reports kind channel"                  '[[ "$(py "d['\''kind'\'']" "$a101")" == "channel" ]]'
  # CN1 and CN10: outside the guide a number TUNES, immediately.
  check "and it is what is now playing"                     '[[ "$(svc "['\''nowPlaying'\'']['\''id'\'']")" == "$(py "d['\''id'\'']" "$a101")" ]]'
  check "status carries the playing channel's number"       '[[ "$(svc "['\''nowPlaying'\'']['\''chno'\'']")" == "101" ]]'
  check "status carries hasNumbers"                         '[[ "$(svc "['\''hasNumbers'\'']")" == true ]]'
  a0101=$(ipc channel 0101)
  check "leading zeros reach the same channel (CN7)"        '[[ "$(py "d['\''id'\'']" "$a0101")" == "$(py "d['\''id'\'']" "$a101")" ]]'
  a81=$(ipc channel 8-1)
  check "a dash subchannel resolves and is labelled 8.1"    '[[ "$(py "d['\''ok'\'']" "$a81")" == true && "$(py "d['\''chno'\'']" "$a81")" == "8.1" ]]'
  a42=$(ipc channel 42)
  check "a 0042 playlist value answers to 42"               '[[ "$(py "d['\''name'\'']" "$a42")" == "DW English" ]]'
  a1000=$(ipc channel 1000)
  check "an alias attribute is reachable too (CN11)"        '[[ "$(py "d['\''ok'\'']" "$a1000")" == true ]]'
  bad205=$(ipc channel 20509)
  check "an unknown number is an error, not a play"         '[[ "$(py "d['\''ok'\'']" "$bad205")" == false && "$(py "d['\''error'\'']['\''code'\'']" "$bad205")" == "unknown_chno" ]]'
  check "the error says which number, sanitized"            '[[ "$(py "d['\''error'\'']['\''message'\'']" "$bad205")" == "no channel 20509" ]]'
  check "it did not change what is playing"                 '[[ "$(svc "['\''nowPlaying'\'']['\''chno'\'']")" == "1000" ]]'
  junk=$(ipc channel "N/A")
  check "a non-numeric argument is the same error (CN6)"    '[[ "$(py "d['\''error'\'']['\''code'\'']" "$junk")" == "unknown_chno" ]]'

  echo "== N20 the bar"
  check "the bar draws the number"                          '[[ "$(py "d['\''number'\'']" "$(ipc widget)")" == "1000" ]]'
  check "the tooltip carries it"                            '[[ "$(py "d['\''tooltip'\'']" "$(ipc widget)")" == *"1000"* ]]'
  ipc set barShowChannelNumber false >/dev/null
  wait_for false 5 svc "['barShowChannelNumber']" || true
  check "barShowChannelNumber false drops it from the bar"  '[[ "$(py "d['\''number'\'']" "$(ipc widget)")" == "" && "$(py "d['\''chno'\'']" "$(ipc widget)")" == "1000" ]]'
  ipc set barShowChannelNumber true >/dev/null

  echo "== N17 / N18 channelOrder"
  check "playlist order is the shipped order"               '[[ "$(py "d['\''channels'\''][0]['\''name'\'']" "$(cat "$CACHE/channels.json")")" == "Harness Live" ]]'
  # N18's real question is whether the flip re-derives from the prepared
  # entry or re-fetches. The cache file's mtime answers it without depending
  # on a log line the helper only writes when it has something to say.
  mtime_before=$(cache_mtime)
  check "there is a cache to compare against"               '[[ -n "$mtime_before" ]]'
  ipc set channelOrder number >/dev/null
  wait_for number 5 svc "['channelOrder']" || bad "the service never saw channelOrder=number"
  ipc setScope all >/dev/null
  ipc move -99 >/dev/null
  check "number order puts the lowest number first"         '[[ "$(py "d['\''guide'\'']['\''cursorName'\'']" "$(ipc state)")" == "Sky News" ]]'
  check "the index is untouched by the re-order"            '[[ "$(py "d['\''count'\'']" "$(ipc chnoIndex)")" == 15 ]]'
  check "channel 101 still reaches BBC One HD"              '[[ "$(py "d['\''name'\'']" "$(ipc channel 101)")" == "BBC One HD" ]]'
  # N18: a re-order is derived from the prepared entry, never re-fetched.
  check "the flip rewrote no cache, so no helper ran"       '[[ -n "$(cache_mtime)" && "$(cache_mtime)" == "$mtime_before" ]]'
  ipc set channelOrder playlist >/dev/null

  echo "== privacy (R12)"
  status_answer=$(ipc state)
  qa_answer_lacks '://' "$status_answer"
  case $? in
    0) ok "the state answer carries no URL" ;;
    1) bad "the state answer carries a URL" ;;
    *) bad "the IPC did not answer at all: 'no URL' is not evidence" ;;
  esac
  checks=$((checks + 1))
  chan_answer=$(ipc channel 101)
  qa_answer_lacks '://' "$chan_answer"
  case $? in
    0) ok "the channel answer carries no URL" ;;
    1) bad "the channel answer carries a URL" ;;
    *) bad "the IPC did not answer at all: 'no URL' is not evidence" ;;
  esac
  checks=$((checks + 1))
}

trap cleanup EXIT

case ${1:-live} in
  check-tree) preflight ;;
  live|"")    preflight; live ;;
  *) echo "usage: chno-scenario.sh [check-tree|live]" >&2; exit 2 ;;
esac

# The floor. A check that stops executing must turn the run red rather than
# shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ *seam ' chno-scenario.sh                      -> the check-tree floor
#   grep -cE '^ *(check|seam) ' chno-scenario.sh  plus 2      -> the live floor
# (the 2 are the privacy block's hand-written bumps; the definitions of
# check() and seam() do not match, and the floor's own bump lands after the
# count is taken). Never lower it to make a run green.
if [[ ${1:-live} == check-tree ]]; then
  EXPECTED_CHECKS=14
else
  EXPECTED_CHECKS=43
fi
ran=$checks
checks=$((checks + 1))
if [[ "$ran" == "$EXPECTED_CHECKS" ]]; then
  ok "the scenario ran every check it has ($ran)"
else
  bad "the scenario ran $ran checks, expected $EXPECTED_CHECKS (one stopped executing)"
fi

echo
echo "summary: $pass passed, $fail failed, $checks assertions executed"
(( fail == 0 ))
