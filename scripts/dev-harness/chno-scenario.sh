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
# `channel` PLAYS (CN1), so the live half starts the harness player.
#
# F-HARNESS-21 (2026-10-15). This scenario was red 6-8 checks on EVERY tree
# for two reasons, and neither was the plugin:
#   - it read the cache at `.../cache/omarchy-iptv/channels.json`, the path
#     from before Sources. The cache has lived in `sources/<key>/` since M2;
#     the active directory is what `ipc activeCache` answers, and N17/N18 now
#     read the file there (and assert it IS there).
#   - every channel it tuned was DEAD (127.0.0.1:9). mpv exits about 1.4 s
#     after such a tune (measured under a nested cage) and the service then
#     clears nowPlaying by itself, so "it did not change what is playing"
#     and the three N20 bar checks read a value on a timer. The live half
#     now plays every row from run.sh's fixture server (`--serve`,
#     qa_served_fixture), refuses to count a play from a server that is not
#     this harness's (qa_listener_owned), and asserts the stream HOLDS
#     before any check leans on it.
#   - N17's "lowest number first" parked with `move -99`, which WRAPS
#     (moveCursorBy(delta, true)): on 20 rows it is +1, so it read row 1.
#     park_top moves by minus the cursor index, which lands on 0 exactly,
#     and the check asserts the index it read.
# Each repaired check was seen red against a one-decision mutation kept in
# spikes/chno-mutations/ (README there has the table and the counts).
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
# F-HARNESS-20: this driver's own processes (its helper runs, probes, mpv)
# get the harness's HOME as well, not only what run.sh starts. Exports only.
qa_harness_home "$SCRATCH" || exit 2

ok()   { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad()  { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
check() { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }
ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
py()   { python3 -c 'import json,sys; d=json.loads(sys.argv[2]); v=eval(sys.argv[1]); print(json.dumps(v) if isinstance(v, bool) else v)' "$1" "$2" 2>/dev/null; }
svc()  { py "d['service']$1" "$(ipc state)"; }

cleanup() {
  if [[ -n $HARNESS_PID ]]; then kill -TERM "$HARNESS_PID" 2>/dev/null; wait "$HARNESS_PID" 2>/dev/null; fi
  # The live half PLAYS a served stream now. run.sh's reap used to end such
  # a player with TERM alone and was seen to leave one spinning for most of
  # an hour (F-HARNESS-30); since R26h it is qa_reap_players too. This
  # cleanup calls it as well, so ours are ended by pid, with KILL behind
  # the TERM, whether or not run.sh's own cleanup runs.
  [[ -n $HARNESS_PID ]] && qa_reap_players "$SCRATCH"
  return 0
}

# The active source's cache directory, as the service itself answers it, and
# only when it is a per-source directory inside this harness's cache: an
# answer outside it (a pre-Sources path, an empty string from a dead IPC) is
# "no cache", never a path to stat.
active_cache() {
  local d
  d=$(ipc activeCache)
  [[ $d == "$CACHE/sources/"?* && -d $d ]] && printf '%s\n' "$d"
}
# The cache file's identity: inode, nanosecond mtime, size and content hash.
# A helper run replaces the file by rename, which a one-second mtime could
# not see inside the same second; the inode and the hash can.
cache_identity() {
  local f=$1/channels.json
  [[ -f $f ]] || return 1
  printf '%s %s\n' "$(stat -c '%i %.9Y %s' "$f" 2>/dev/null)" "$(sha256sum <"$f" | cut -c1-16)"
}
# Put the guide's cursor on row 0. `move` WRAPS, so `move -99` is not the
# top (on 20 rows it is +1); minus the current index is, exactly.
park_top() {
  local at
  at=$(py "d['guide']['cursorIndex']" "$(ipc state)")
  [[ $at =~ ^[0-9]+$ ]] && (( at > 0 )) && ipc move "-$at" >/dev/null
  return 0
}
# What is playing, as one comparable token: the channel id and the service's
# play sequence (every new play bumps it, a re-tune of the same id included).
playing_token() { py "(d['service']['nowPlaying'] or {}).get('id','NONE') + ' ' + str(d['service']['player']['seq'])" "$(ipc state)"; }
# The stream HOLDS: <chno> is playing, and the token does not change across
# HOLD_S seconds -- longer than the 1.4 s a dead stream lasts. Prints the
# verdict, "held" or what it saw instead.
HOLD_S=${OMARCHY_IPTV_CHNO_HOLD_S:-3}
steady_playing() {
  local want=$1 first="" now i
  for ((i = 0; i < 100; i++)); do
    [[ "$(svc "['nowPlaying']['chno']")" == "$want" && "$(svc "['player']['up']")" == true ]] && break
    sleep 0.1
  done
  first=$(playing_token)
  for ((i = 0; i < HOLD_S * 5; i++)); do
    sleep 0.2
    now=$(playing_token)
    [[ $now == "$first" ]] || { echo "moved:$first->$now"; return 1; }
  done
  [[ "$(svc "['nowPlaying']['chno']")" == "$want" ]] || { echo "not-$want:$(svc "['nowPlaying']")"; return 1; }
  echo held
}
# R12's needle, with what it matched on a red: a privacy check that fails
# with no context cannot be told from a redacted host (scheme://host is the
# redaction itself). Prints at most three matches, cut after the host.
url_context() { grep -oE '.{0,60}[a-z]+://[^/"?#@ ]*' <<<"$1" | head -n 3; }

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
  mkdir -p "$FIX"
  # F-HARNESS-21: every row served, none dead (qa_served_fixture). The port
  # is run.sh's; it is read from there rather than written twice, and the
  # listener check below is what makes that join a call.
  SERVE_PORT=$(grep -oE '^SERVE_PORT=[0-9]+$' "$RUN" | cut -d= -f2)
  qa_served_fixture "$HERE/fixtures/harness.m3u.in" "$FIX/chno-served.m3u" "${SERVE_PORT:-0}" \
    || bad "could not write the served fixture (port '${SERVE_PORT}')"
  : >"$LOG"
  qa_listener_owned "${SERVE_PORT:-0}" "$SCRATCH/fixtures"
  [[ $? == 2 ]] || echo "[chno-scenario] 127.0.0.1:${SERVE_PORT} is already held by another process; run.sh's server cannot bind it" >&2

  echo "== start harness (--order playlist, --serve)"
  HARNESS_TIMEOUT=${OMARCHY_IPTV_SCENARIO_TIMEOUT:-300}
  "$RUN" --keep --serve --timeout "$HARNESS_TIMEOUT" --playlist "$FIX/chno-served.m3u" >>"$LOG" 2>&1 &
  HARNESS_PID=$!
  wait_for 20 60 svc "['channels']" || bad "the fixture playlist never loaded; every check below is about nothing"
  check "the stream server on 127.0.0.1:$SERVE_PORT is this harness's own (F-HARNESS-21)" 'qa_listener_owned "$SERVE_PORT" "$SCRATCH/fixtures"'

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
  # F-HARNESS-21: everything below that reads "what is playing" leans on a
  # tuned stream STAYING tuned. Asserted, not assumed.
  held=$(steady_playing 101)
  check "a tuned channel stays playing (the served fixture holds $HOLD_S s)" '[[ "$held" == held ]] || { echo "   saw: $held"; false; }'
  a0101=$(ipc channel 0101)
  check "leading zeros reach the same channel (CN7)"        '[[ "$(py "d['\''id'\'']" "$a0101")" == "$(py "d['\''id'\'']" "$a101")" ]]'
  a81=$(ipc channel 8-1)
  check "a dash subchannel resolves and is labelled 8.1"    '[[ "$(py "d['\''ok'\'']" "$a81")" == true && "$(py "d['\''chno'\'']" "$a81")" == "8.1" ]]'
  a42=$(ipc channel 42)
  check "a 0042 playlist value answers to 42"               '[[ "$(py "d['\''name'\'']" "$a42")" == "DW English" ]]'
  a1000=$(ipc channel 1000)
  check "an alias attribute is reachable too (CN11)"        '[[ "$(py "d['\''ok'\'']" "$a1000")" == true ]]'
  tok1000=$(playing_token)
  bad205=$(ipc channel 20509)
  check "an unknown number is an error, not a play"         '[[ "$(py "d['\''ok'\'']" "$bad205")" == false && "$(py "d['\''error'\'']['\''code'\'']" "$bad205")" == "unknown_chno" ]]'
  check "the error says which number, sanitized"            '[[ "$(py "d['\''error'\'']['\''message'\'']" "$bad205")" == "no channel 20509" ]]'
  # The play token (id and play sequence) as well as the number: a refusal
  # that re-tuned anything at all, the same channel included, moves it.
  check "it did not change what is playing"                 'np=$(svc "['\''nowPlaying'\'']['\''chno'\'']"); now=$(playing_token); [[ "$np" == "1000" && "$now" == "$tok1000" ]] || { echo "   chno:$np token:$tok1000 -> $now"; false; }'
  junk=$(ipc channel "N/A")
  check "a non-numeric argument is the same error (CN6)"    '[[ "$(py "d['\''error'\'']['\''code'\'']" "$junk")" == "unknown_chno" ]]'

  echo "== N20 the bar"
  check "the bar draws the number"                          'w=$(ipc widget); [[ "$(py "d['\''number'\'']" "$w")" == "1000" ]] || { echo "   widget: $w"; false; }'
  check "the tooltip carries it"                            'w=$(ipc widget); [[ "$(py "d['\''tooltip'\'']" "$w")" == *"1000"* ]] || { echo "   widget: $w"; false; }'
  ipc set barShowChannelNumber false >/dev/null
  wait_for false 5 svc "['barShowChannelNumber']" || true
  check "barShowChannelNumber false drops it from the bar"  'w=$(ipc widget); [[ "$(py "d['\''number'\'']" "$w")" == "" && "$(py "d['\''chno'\'']" "$w")" == "1000" ]] || { echo "   widget: $w"; false; }'
  ipc set barShowChannelNumber true >/dev/null

  echo "== N17 / N18 channelOrder"
  # F-HARNESS-21: the per-source directory the service reads, not the
  # pre-Sources root.
  CACHE_DIR=$(active_cache)
  ipc setScope all >/dev/null
  park_top
  # The guide's first row AND the cache file's first entry: the order the
  # user sees is the playlist's, read from the file the helper wrote.
  check "playlist order is the shipped order"               'st=$(ipc state); at=$(py "d['\''guide'\'']['\''cursorIndex'\'']" "$st"); nm=$(py "d['\''guide'\'']['\''cursorName'\'']" "$st"); c0=$(py "d['\''channels'\''][0]['\''name'\'']" "$(cat "$CACHE_DIR/channels.json" 2>/dev/null)"); [[ "$at" == 0 && "$nm" == "Harness Live" && "$c0" == "Harness Live" ]] || { echo "   row $at: $nm; cache[0]: $c0 (in ${CACHE_DIR:-no cache dir})"; false; }'
  # N18's real question is whether the flip re-derives from the prepared
  # entry or re-fetches. The cache file's identity answers it without
  # depending on a log line the helper only writes when it has something to
  # say.
  id_before=$(cache_identity "$CACHE_DIR")
  check "there is a cache to compare against"               '[[ -n "$CACHE_DIR" && -n "$id_before" ]] || { echo "   activeCache: $(ipc activeCache)"; false; }'
  ipc set channelOrder number >/dev/null
  wait_for number 5 svc "['channelOrder']" || bad "the service never saw channelOrder=number"
  ipc setScope all >/dev/null
  park_top
  check "number order puts the lowest number first"         'st=$(ipc state); at=$(py "d['\''guide'\'']['\''cursorIndex'\'']" "$st"); nm=$(py "d['\''guide'\'']['\''cursorName'\'']" "$st"); [[ "$at" == 0 && "$nm" == "Sky News" ]] || { echo "   row $at: $nm"; false; }'
  check "the index is untouched by the re-order"            '[[ "$(py "d['\''count'\'']" "$(ipc chnoIndex)")" == 15 ]]'
  check "channel 101 still reaches BBC One HD"              '[[ "$(py "d['\''name'\'']" "$(ipc channel 101)")" == "BBC One HD" ]]'
  # N18: a re-order is derived from the prepared entry, never re-fetched. An
  # absence needs a window: FLIP_SETTLE_S is longer than a fetch of this
  # 20-row local file takes (the flip-refetches mutation rewrites it inside
  # it, spikes/chno-mutations/README.md).
  sleep "${OMARCHY_IPTV_CHNO_FLIP_SETTLE_S:-3}"
  check "the flip rewrote no cache, so no helper ran"       'now=$(cache_identity "$CACHE_DIR"); [[ -n "$now" && "$now" == "$id_before" ]] || { echo "   $id_before -> $now"; false; }'
  ipc set channelOrder playlist >/dev/null

  echo "== privacy (R12)"
  # The needle is QA_URL_PAST_HOST_ERE, not a bare `://`: rule 5 redacts to
  # scheme and host, and the bare needle went red on that redaction itself
  # (service.lastError after a dead tune, F-HARNESS-22). Stated plainly: with
  # every row served nothing fails, so no URL-bearing field is populated
  # when these run, and a full-URL leak into one of them would be seen only
  # if it happened anyway. The needle itself is proven both ways in
  # scripts/qa-lib-test.sh; a failing row for R12 to observe is open.
  status_answer=$(ipc state)
  qa_answer_lacks "$QA_URL_PAST_HOST_ERE" "$status_answer"
  case $? in
    0) ok "the state answer carries no URL past scheme and host" ;;
    1) bad "the state answer carries a URL past its host"; url_context "$status_answer" | sed 's/^/   /' ;;
    *) bad "the IPC did not answer at all: 'no URL' is not evidence" ;;
  esac
  checks=$((checks + 1))
  chan_answer=$(ipc channel 101)
  qa_answer_lacks "$QA_URL_PAST_HOST_ERE" "$chan_answer"
  case $? in
    0) ok "the channel answer carries no URL past scheme and host" ;;
    1) bad "the channel answer carries a URL past its host"; url_context "$chan_answer" | sed 's/^/   /' ;;
    *) bad "the IPC did not answer at all: 'no URL' is not evidence" ;;
  esac
  checks=$((checks + 1))
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

case ${1:-live} in
  check-tree) preflight ;;
  live|"")
    # F-M3-1 half (b): the transcript covers the WHOLE run, preflight
    # included, because the summary at the bottom counts both halves and a
    # transcript that holds only one of them cannot be summarised from. It is
    # NOT opened on the check-tree path: scripts/check.sh runs that half on
    # every commit, and a gate step may neither print a path nobody asked for
    # nor leave a file behind.
    qa_transcript_start chno || exit 2
    preflight
    live
    ;;
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
  EXPECTED_CHECKS=45
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
