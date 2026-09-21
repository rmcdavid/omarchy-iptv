#!/bin/bash
# scripts/dev-harness/chno-entry-scenario.sh -- the runner ruling CN23 says
# must exist: scripted verification of channel-number ENTRY in the guide.
#
#   chno-entry-scenario.sh check-tree   the capability preflight ONLY; no
#                                       display, no quickshell, no player.
#                                       Run by scripts/check.sh.
#   chno-entry-scenario.sh [live]       the preflight, then the live half.
#
# WHY IT EXISTS. `docs/M2-03-CHANNEL-NUMBERS.md` section 10.6 specified four
# harness verbs -- `number`, `numberState`, `commitNumber`, `cancelNumber` --
# and an extension of `state()`. None of the five was ever built, so scenarios
# N1-N16 and N21-N24 had no runner and had never executed (F-CHNO-3, and the
# live pass had to drive all of them by hand with wtype). A test that has
# never run is not coverage; this file, the verbs in shell.qml, and the node
# checks named for the same scenarios are the answer to that.
#
# WHAT RUNS WHERE. The half of each scenario that is a decision -- what a
# digit resolves to, when the commit fires, what a miss reports, what the
# cycle lands on -- is not in this file at all: it lives in Model.js and is
# asserted by name (`N1:`, `N5:`, `N8:` ...) in tests/Model.test.js, which
# runs in scripts/check.sh on every commit. What is HERE is the half only a
# running guide can answer: the cursor, the scope hop, the timer, the
# transient, the column, and the source switch.
#
# STATUS OF THE LIVE HALF, stated plainly because CN23 is about exactly this:
# the preflight below has been run and has been seen failing against a tree
# without the verbs. The live half is IPC-only (no wtype, no screenshot), so
# it runs headless under a nested cage (docs/SPIKE-CAGE-HEADLESS.md) as well
# as on the display. It was first run that way on 2026-09-21 and failed 34 of
# 73 assertions for its OWN reasons (F-CHNO-5 and the quoting slip below),
# then passed in full after the fix. A pass is evidence only for the run that
# produced it; do not record these scenarios as passing on the strength of
# this file existing.
#
# F-CHNO-5. The guide opens in SEARCH mode on every display: Model.guideState
# says so and Guide.open() rebuilds the state from it on EVERY open, a reopen
# included. The harness `number` verb routes through handleSharedKey, whose
# listMode guard keeps a digit literal in search mode (that is N16's rule),
# so a scenario that types a digit without entering list mode first is
# testing N16 thirty times over. This file assumed list mode at open and its
# N16 block toggled from there. `enter_mode` below is the fix: it reads the
# mode, toggles only when the parity calls for it, and the caller asserts
# what it got. It is called after every open and around N16.
#
# The quoting slip, found by the same run: seven reads outside a `check` were
# spelled gf "['\''x'\'']" -- the '\'' idiom that ends and restarts a
# SINGLE-quoted check expression -- inside DOUBLE quotes, where the backslash
# survives and python sees a syntax error. Every one answered NOFIELD, so two
# waits could never match, three "parked row" comparisons compared against a
# sentinel, the N10 scope lookup found no UK group, and N22's `key` was
# NOFIELD (the add's own auto-switch is what made the reads after it pass).
# Outside a check the spelling is plain: gf "['x']".
#
# Cases that are NOT here, and why (the honest half of CN23):
#   N15  keypad and shifted digits: only real key events through the
#        compositor prove the `event.text` rule, so it stays a `run.sh key`
#        item for the display lane (10.7 item 4).
#   N21  narrow card: a window resize under Style.space(720) plus a
#        screenshot. Nothing over IPC can resize the overlay.
#   N23  the 10k switch budget: the same measurement sources-scenario.sh
#        already makes (H6/H8, five switches each way, median under 150 ms),
#        with the number ordering on top of it. Duplicating the harness half
#        buys nothing; the ordering cost is a Model-level figure.
#   N24  theme re-skin while the chip is visible: visual, live shell only.
#
# The fixture (fixtures/harness.m3u.in) carries 15 numbered rows: 7, 7.1, 7.2,
# 8.1 (from 8-1), 42 (from 0042), 101, 102, 103, 300, 501 twice (the duplicate
# pair), 900, 901, 1000, 1001 (the two alias attributes). "10" is ambiguous
# (101/102/103/1000/1001 extend it) and "300" is not, which is what makes the
# timeout and the instant path both reachable on one list.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
PLUGIN_ROOT=$(cd "${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}" 2>/dev/null && pwd)
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
FIX="$SCRATCH/fixtures"
LOG="$SCRATCH/chno-entry-scenario.log"
HARNESS_PID=""
ENTRY_MS=${OMARCHY_IPTV_ENTRY_MS:-2000}
pass=0
fail=0
checks=0

# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

ok()   { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad()  { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
check() { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }
ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
# Every read goes through the sentinel predicates: a harness without the verbs
# answers every field null, and a bare reader would let that count as "the
# entry is not active" (see scripts/qa-lib-test.sh).
nf()   { qa_json_field "d$1" "$2"; }
gf()   { qa_guide_field "d$1" "$(ipc state)"; }
sf()   { qa_field "d$1" "$(ipc state)"; }

cleanup() {
  if [[ -n $HARNESS_PID ]]; then kill -TERM "$HARNESS_PID" 2>/dev/null; wait "$HARNESS_PID" 2>/dev/null; fi
  return 0
}

# Bounded, and it SAYS it gave up (CLAUDE.md rule 3).
wait_for() {
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ "$("$@")" == "$want" ]] && return 0
    sleep 0.1
  done
  echo "[chno-entry-scenario] gave up waiting ${secs}s for '$want' from: $*" >&2
  return 1
}

# The digit window, plus a margin. Every timeout check waits exactly this.
wait_out_entry() { sleep "$(awk -v ms="$ENTRY_MS" 'BEGIN { printf "%.2f", ms / 1000 + 0.4 }')"; }

# enter_mode <list|search>: put the guide in that mode (F-CHNO-5, header).
# `ipc mode` is a TOGGLE, so sending it blind is right only when the parity
# is; this reads first. It asserts nothing itself: the caller checks the mode
# it needed, so a harness whose `mode` verb is a no-op goes red there rather
# than being corrected here silently.
enter_mode() {
  local want=$1
  [[ "$(gf "['mode']")" == "$want" ]] || ipc mode >/dev/null
  return 0
}

# ---------------------------------------------------------------- preflight
#
# `seam <label> <file> <ere> <at least>`: a POSITIVE count, never a `! grep`.
# qa_count answers 0 for a missing or unreadable file, so a tree without the
# file fails here instead of passing an absence test.
seam() {
  local label=$1 file=$2 ere=$3 want=$4
  checks=$((checks + 1))
  local got
  got=$(qa_count "$ere" "$file")
  if (( got >= want )); then ok "$label"; else bad "$label (matched $got, wanted at least $want in ${file#"$PLUGIN_ROOT/"})"; fi
}

preflight() {
  echo "== preflight: can this tree drive number entry? (plugin: $PLUGIN_ROOT)"
  # The four verbs of section 10.6, and the state() extension.
  seam "the harness declares the number verb"            "$HERE/shell.qml" 'function number\(keys: string\): string' 1
  seam "the harness declares numberState"                "$HERE/shell.qml" 'function numberState\(\): string' 1
  seam "the harness declares commitNumber"               "$HERE/shell.qml" 'function commitNumber\(play: bool, keepOpen: bool\): string' 1
  seam "the harness declares cancelNumber"               "$HERE/shell.qml" 'function cancelNumber\(\): string' 1
  seam "the harness answers with one entry snapshot"     "$HERE/shell.qml" 'function numberSnapshot\(g\)' 1
  seam "state() carries the guide number entry"          "$HERE/shell.qml" 'numberEntry: harness\.numberSnapshot\(g\)' 1
  seam "state() carries hasNumbers on the guide side"    "$HERE/shell.qml" 'hasNumbers: g\.hasNumbers' 1
  seam "the verb drives the guide's own key router"      "$HERE/shell.qml" 'g\.handleSharedKey\(' 2
  # What those verbs call. A tree missing any of these answers `no_verb`
  # rather than throwing, so the live half would go red rather than vacuous -
  # but it should not get that far.
  seam "Guide.qml routes a number key"                   "$PLUGIN_ROOT/Guide.qml" '^ *function handleNumberKey\(event\)' 1
  seam "Guide.qml commits an entry"                      "$PLUGIN_ROOT/Guide.qml" '^ *function commitNumberEntry\(opts\)' 1
  seam "Guide.qml cancels an entry"                      "$PLUGIN_ROOT/Guide.qml" '^ *function cancelNumberEntry\(\)' 1
  seam "Guide.qml has the shared key router the verb uses" "$PLUGIN_ROOT/Guide.qml" '^ *function handleSharedKey\(event\)' 1
  # CN21 and D-CHNO-1, the two fixes this runner exists to keep fixed.
  seam "Guide.qml disarms the resume window"             "$PLUGIN_ROOT/Guide.qml" '^ *function disarmNumberResume\(\)' 1
  seam "Guide.qml lets the digit window outlive an auto-commit" "$PLUGIN_ROOT/Guide.qml" '^ *function numberTimerFired\(\)' 1
  seam "Model.js owns the per-key sequence"              "$PLUGIN_ROOT/Model.js" '^function numberKeyStep\(entry, index, text, ctx\)' 1
  seam "Model.js owns the commit"                        "$PLUGIN_ROOT/Model.js" '^function numberCommitStep\(entry, resolution, name, opts\)' 1
  seam "Model.js owns Backspace"                         "$PLUGIN_ROOT/Model.js" '^function numberPopStep\(entry, index\)' 1
  seam "Model.js arms the buffer an auto-commit closed"  "$PLUGIN_ROOT/Model.js" '^function closeNumberEntry\(entry, reason\)' 1
  seam "the entry snapshot carries the pre-entry cursor" "$PLUGIN_ROOT/Model.js" 'cursorId: str\(c\.cursorId\)' 1
  # What run.sh must parse for the live half to be driveable at all.
  checks=$((checks + 1))
  if qa_case_arm "$RUN" --entry-ms && qa_case_arm "$RUN" --order; then ok "run.sh parses --entry-ms and --order"
  else bad "run.sh does not parse --entry-ms / --order (they are option spellings, not comments)"; fi
}

# ------------------------------------------------------------------- live
live() {
  echo "== setup (scratch $SCRATCH)"
  "$RUN" clean >/dev/null
  mkdir -p "$FIX"
  sed "s|__LIVE__|http://127.0.0.1:9/dead/live.m3u8|g" "$HERE/fixtures/harness.m3u.in" >"$FIX/harness.m3u"
  # A second, UNNUMBERED list for N14 and N22, generated rather than written
  # so it cannot drift: --numbering none is what every real iptv-org list is.
  python3 "$ROOT/scripts/gen-playlist.py" --profile realistic --numbering none \
    --channels 40 --groups 6 --seed 3 --out "$FIX/nonumbers.m3u" >/dev/null 2>&1
  : >"$LOG"

  echo "== start harness (--open, --entry-ms $ENTRY_MS)"
  HARNESS_TIMEOUT=${OMARCHY_IPTV_SCENARIO_TIMEOUT:-300}
  "$RUN" --keep --open --timeout "$HARNESS_TIMEOUT" --entry-ms "$ENTRY_MS" --playlist "$FIX/harness.m3u" >>"$LOG" 2>&1 &
  HARNESS_PID=$!
  wait_for 20 30 sf "['channels']" || bad "the fixture playlist never loaded; every check below is about nothing"
  wait_for true 10 gf "['opened']" || bad "the guide never opened; every check below is about nothing"
  # F-CHNO-5: the guide is in search mode here, and a digit typed there is
  # literal. Every number check below is about list mode.
  enter_mode list
  check "setup: the guide is in list mode before the first digit (F-CHNO-5)" '[[ "$(gf "['\''mode'\'']")" == "list" ]]'
  ipc setScope all >/dev/null
  ipc move -99 >/dev/null

  echo "== N1 live preview, one digit at a time"
  # The harness `move` verb WRAPS (moveCursorBy(delta, true)), so `move -99`
  # is not "park at the top": on this 20-row list it is +1 mod 20. No check
  # here may assume an index; it reads where the cursor is and compares.
  parked0=$(gf "['cursorIndex']")
  a1=$(ipc number 1)
  check "N1: the first digit opens entry and previews the lowest match"  '[[ "$(nf "['\''active'\'']" "$a1")" == true && "$(nf "['\''buffer'\'']" "$a1")" == "1" && "$(nf "['\''label'\'']" "$a1")" == "101" ]]'
  check "N1: and the cursor is already on it"                            '[[ "$(nf "['\''cursorName'\'']" "$a1")" == "BBC One HD" ]]'
  a2=$(ipc number 0)
  check "N1: the second digit extends the same buffer"                   '[[ "$(nf "['\''buffer'\'']" "$a2")" == "10" && "$(nf "['\''kind'\'']" "$a2")" == "prefix" ]]'
  check "N1: an ambiguous buffer does NOT commit"                        '[[ "$(nf "['\''active'\'']" "$a2")" == true ]]'
  check "N1: the entry snapshot remembers where the cursor started"      'qa_value "$parked0" && [[ "$(nf "['\''cursorIndex'\'']" "$a2")" == "$parked0" ]]'

  echo "== N2 the timeout commits"
  wait_out_entry
  a3=$(ipc numberState)
  check "N2: the window closes the entry"                                '[[ "$(nf "['\''active'\'']" "$a3")" == false && "$(nf "['\''buffer'\'']" "$a3")" == "" ]]'
  check "N2: the cursor stays on what the preview chose"                 '[[ "$(nf "['\''cursorName'\'']" "$a3")" == "BBC One HD" ]]'
  check "N2: and the footer names the channel it landed on"              '[[ "$(nf "['\''transient'\'']" "$a3")" == *"101"* && "$(nf "['\''transient'\'']" "$a3")" == *"BBC One HD"* ]]'
  check "N2: a timeout commit does not arm anything"                     '[[ "$(nf "['\''resume'\'']" "$a3")" == false ]]'

  echo "== N13 an unambiguous number commits on its last digit"
  ipc move -99 >/dev/null
  # N8 below continues THIS entry (CN21), so the row it restores to is the
  # one the cursor is on now, before the first digit.
  before_cursor=$(gf "['cursorIndex']")
  a4=$(ipc number 300)
  check "N13: 300 commits without waiting for the window"                '[[ "$(nf "['\''active'\'']" "$a4")" == false && "$(nf "['\''cursorName'\'']" "$a4")" == "Harness Live" ]]'
  check "N13: the footer says so immediately"                            '[[ "$(nf "['\''transient'\'']" "$a4")" == *"300"* ]]'
  # CN21: that commit is provisional for the rest of the window, and this is
  # the state D-CHNO-2 turns on.
  check "CN21: and the buffer it closed early is armed, not forgotten"   '[[ "$(nf "['\''resume'\'']" "$a4")" == true ]]'

  echo "== N8 / D-CHNO-2 a number that does not exist says so"
  # CN21: the buffer 300 is still armed from N13, so the FOURTH digit alone
  # continues it. This used to move the cursor and type all of 3009 again,
  # which appended to the armed buffer and asserted about "3003009".
  a5=$(ipc number 9)
  check "CN21: the fourth digit continues 300 instead of starting a new number" '[[ "$(nf "['\''active'\'']" "$a5")" == true && "$(nf "['\''buffer'\'']" "$a5")" == "3009" ]]'
  check "N8: which resolves to nothing"                                  '[[ "$(nf "['\''kind'\'']" "$a5")" == "none" ]]'
  wait_out_entry
  a6=$(ipc numberState)
  check "N8: the miss is reported with the number the user typed"        '[[ "$(nf "['\''transient'\'']" "$a6")" == "No channel 3009" ]]'
  check "N8: and the cursor is back where it started, not somewhere else" '[[ "$(nf "['\''cursorIndexLive'\'']" "$a6")" == "$before_cursor" ]]'
  check "N8: nothing started playing"                                    '[[ "$(sf "['\''nowPlaying'\'']")" == "NOFIELD" ]]'

  echo "== N5 / N6 Backspace"
  ipc move -99 >/dev/null
  a7=$(ipc number "10<")
  check "N5: Backspace drops the last digit and previews what is left"   '[[ "$(nf "['\''buffer'\'']" "$a7")" == "1" && "$(nf "['\''active'\'']" "$a7")" == true ]]'
  ipc cancelNumber >/dev/null
  ipc move 4 >/dev/null
  parked=$(gf "['cursorIndex']")
  parked_name=$(gf "['cursorName']")
  a8=$(ipc number "1<")
  check "N6: Backspace to empty ends the entry"                          '[[ "$(nf "['\''active'\'']" "$a8")" == false && "$(nf "['\''buffer'\'']" "$a8")" == "" ]]'
  check "N6: and restores the row the user was parked on"                '[[ "$(nf "['\''cursorIndexLive'\'']" "$a8")" == "$parked" && "$(nf "['\''cursorName'\'']" "$a8")" == "$parked_name" ]]'

  echo "== N7 Esc cancels and the guide stays open"
  ipc number 10 >/dev/null
  a9=$(ipc cancelNumber)
  check "N7: the entry is gone"                                          '[[ "$(nf "['\''cancelled'\'']" "$a9")" == true && "$(nf "['\''active'\'']" "$a9")" == false ]]'
  check "N7: the cursor is exactly back on the parked row"               '[[ "$(nf "['\''cursorIndexLive'\'']" "$a9")" == "$parked" ]]'
  check "N7: and the guide is still open"                                '[[ "$(gf "['\''opened'\'']")" == true ]]'

  echo "== N11 subchannels, both separators (CN8 / CN17)"
  ipc move -99 >/dev/null
  b1=$(ipc number "7.1")
  check "N11: a dot subchannel lands on its channel"                     '[[ "$(nf "['\''cursorName'\'']" "$b1")" == "BBC News" ]]'
  wait_out_entry
  ipc move -99 >/dev/null
  b2=$(ipc number "7,1")
  check "N11: a comma is the same number"                                '[[ "$(nf "['\''cursorName'\'']" "$b2")" == "BBC News" ]]'
  wait_out_entry
  ipc move -99 >/dev/null
  ipc number 7 >/dev/null
  wait_out_entry
  b3=$(ipc numberState)
  check "N11: the major alone waits out the window and lands on 7"       '[[ "$(nf "['\''cursorName'\'']" "$b3")" == "Sky News" ]]'

  echo "== N12 / D-CHNO-1 duplicate cycling"
  ipc move -99 >/dev/null
  c1=$(ipc number 501)
  wait_out_entry
  c2=$(ipc number 501)
  wait_out_entry
  c3=$(ipc number 501)
  check "N12: the first commit lands on the first twin"                  '[[ "$(nf "['\''cursorName'\'']" "$c1")" == "Sky Sports Main Event" && "$(nf "['\''transient'\'']" "$c1")" == *"(1 of 2)"* ]]'
  check "N12: re-typing it reaches the OTHER twin"                       '[[ "$(nf "['\''cursorName'\'']" "$c2")" == "Sky Sports Football" && "$(nf "['\''transient'\'']" "$c2")" == *"(2 of 2)"* ]]'
  check "N12: and a third commit wraps"                                  '[[ "$(nf "['\''cursorName'\'']" "$c3")" == "Sky Sports Main Event" && "$(nf "['\''transient'\'']" "$c3")" == *"(1 of 2)"* ]]'
  wait_out_entry

  echo "== N10 the scope hop"
  # gf prefixes the expression with `d`; `d['scopes'][0] and ...` keeps that
  # prefix meaningful and still answers NOFIELD (IndexError) when there is no
  # scope at all or no UK group among them.
  uk=$(gf "['scopes'][0] and [s.split('=')[0] for s in d['scopes'] if s.startswith('g:UK')][0]")
  check "N10: there is a UK group to scope into"                         'qa_value "$uk"'
  ipc setScope "$uk" >/dev/null
  d1=$(ipc number 900)
  check "N10: a number outside the scope moves the scope to All"         '[[ "$(gf "['\''effectiveScope'\'']")" == "all" ]]'
  check "N10: and lands on the channel"                                  '[[ "$(nf "['\''cursorName'\'']" "$d1")" == "Cartoon Corner" ]]'
  wait_out_entry

  echo "== N16 digits stay literal in search mode"
  # F-CHNO-5: entered explicitly and asserted, not reached by toggling from
  # an assumed list mode.
  enter_mode search
  check "N16: the guide is in search mode"                               '[[ "$(gf "['\''mode'\'']")" == "search" ]]'
  e1=$(ipc number 101)
  check "N16: a digit there opens no entry at all"                       '[[ "$(nf "['\''active'\'']" "$e1")" == false && "$(nf "['\''buffer'\'']" "$e1")" == "" ]]'
  ipc query 101 >/dev/null
  check "N16: an all-digit query floats the exact number match first"    '[[ "$(gf "['\''cursorName'\'']")" == "BBC One HD" ]]'
  ipc query "" >/dev/null
  enter_mode list
  check "N16: and list mode is back for the checks that follow"          '[[ "$(gf "['\''mode'\'']")" == "list" ]]'

  echo "== N3 / N4 Enter plays and closes, Space plays and stays"
  ipc move -99 >/dev/null
  ipc number 10 >/dev/null
  f1=$(ipc commitNumber true false)
  check "N3: Enter commits the entry and reports that it landed"         '[[ "$(nf "['\''landed'\'']" "$f1")" == true ]]'
  check "N3: the guide closes"                                           '[[ "$(gf "['\''opened'\'']")" == false ]]'
  check "N3: and the service is playing the number that was typed"       '[[ "$(sf "['\''nowPlaying'\''][\"chno\"]")" == "101" ]]'
  ipc open '{}' >/dev/null
  wait_for true 10 gf "['opened']" || bad "the guide did not reopen"
  # F-CHNO-5: Guide.open() rebuilds the state on every open, so the reopened
  # guide is in search mode again.
  enter_mode list
  check "N4: the reopened guide is back in list mode before the next digit" '[[ "$(gf "['\''mode'\'']")" == "list" ]]'
  ipc setScope all >/dev/null
  ipc move -99 >/dev/null
  # 102 is unambiguous and commits on its own last digit, leaving nothing for
  # Space to commit (landed false, by design). 50 is a prefix of the 501
  # twins, so the entry is still open and Space plays what the preview chose.
  ipc number 50 >/dev/null
  f2=$(ipc commitNumber true true)
  check "N4: Space commits and keeps the guide open"                     '[[ "$(nf "['\''landed'\'']" "$f2")" == true && "$(gf "['\''opened'\'']")" == true ]]'
  check "N4: playing what the preview selected"                          '[[ "$(sf "['\''nowPlaying'\''][\"chno\"]")" == "501" ]]'

  echo "== N9 Enter on a number that does not exist refuses to play"
  ipc move -99 >/dev/null
  ipc number 3009 >/dev/null
  # "Nothing new" is what is playing before against after, read either side
  # of the commit: the URLs here are dead, so mpv exits within a second and
  # nowPlaying clears on its own; a fixed "still 501" would race that.
  np_before=$(sf "['nowPlaying']")
  g1=$(ipc commitNumber true false)
  np_after=$(sf "['nowPlaying']")
  check "N9: the commit reports that it did not land"                    '[[ "$(nf "['\''landed'\'']" "$g1")" == false ]]'
  check "N9: it says which number, and plays nothing new"                '[[ "$(nf "['\''transient'\'']" "$g1")" == "No channel 3009" && "$np_after" == "$np_before" ]]'
  check "N9: and the guide is still open"                                '[[ "$(gf "['\''opened'\'']")" == true ]]'

  echo "== N14 / N22 a source with no numbers at all"
  add=$(ipc addSource "$FIX/nonumbers.m3u" "" "No Numbers")
  key=$(qa_json_field "d['id']" "$add")
  check "N22: the unnumbered source was added"                           'qa_value "$key"'
  ipc switchSource "$key" >/dev/null
  wait_for false 20 sf "['hasNumbers']" || bad "the service never reported hasNumbers false after the switch"
  check "N22: the index follows the active source"                       '[[ "$(qa_json_field "d['\''hasNumbers'\'']" "$(ipc chnoIndex)")" == false ]]'
  check "N14: the guide knows there are no numbers"                      '[[ "$(gf "['\''hasNumbers'\'']")" == false ]]'
  check "N14: and draws no number column"                                '[[ "$(gf "['\''numberWidth'\'']")" == 0 ]]'
  h1=$(ipc number 5)
  check "N14: a digit answers with one transient instead of silence"     '[[ "$(nf "['\''transient'\'']" "$h1")" == "No channel numbers in this playlist" ]]'
  check "N14: and opens no entry"                                        '[[ "$(nf "['\''active'\'']" "$h1")" == false ]]'
  check "N14: the hint line drops the 0-9 pair"                          '[[ "$(gf "['\''footerHint'\'']")" != *"0-9"* ]]'

  echo "== privacy (R12)"
  checks=$((checks + 1))
  qa_answer_lacks '://' "$(ipc numberState)"
  case $? in
    0) ok "the numberState answer carries no URL" ;;
    1) bad "the numberState answer carries a URL" ;;
    *) bad "the IPC did not answer at all: 'no URL' is not evidence" ;;
  esac
  checks=$((checks + 1))
  qa_answer_lacks '://' "$(ipc state)"
  case $? in
    0) ok "the state answer carries no URL" ;;
    1) bad "the state answer carries a URL" ;;
    *) bad "the IPC did not answer at all: 'no URL' is not evidence" ;;
  esac
}

trap cleanup EXIT

case ${1:-live} in
  check-tree) preflight ;;
  live|"")    preflight; live ;;
  *) echo "usage: chno-entry-scenario.sh [check-tree|live]" >&2; exit 2 ;;
esac

# The floor. A check that stops executing must turn the run red rather than
# shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ *seam ' chno-entry-scenario.sh            plus 1  -> check-tree
#   grep -cE '^ *(check|seam) ' chno-entry-scenario.sh    plus 3  -> live
# (the 1 is the run.sh option probe, which bumps `checks` by hand; the 3 are
# that probe plus the privacy block's two bumps. The definitions of check()
# and seam() do not match the pattern, and the floor's own bump lands after
# the count is taken.) scripts/qa-lib-test.sh asserts both numbers against
# this file, so a forgotten bump turns check.sh red here rather than on the
# display lane's machine weeks later. Never lower it to make a run green.
if [[ ${1:-live} == check-tree ]]; then
  EXPECTED_CHECKS=20
else
  EXPECTED_CHECKS=75
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
