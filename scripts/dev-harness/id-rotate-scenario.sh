#!/bin/bash
# scripts/dev-harness/id-rotate-scenario.sh -- D-ID-3, observed at the sink:
# does the SHELL keep the id migration the helper made, or write over it?
#
#   id-rotate-scenario.sh check-tree   the seam preflight ONLY; no display,
#                                      no quickshell, no player.
#   id-rotate-scenario.sh [live]       the preflight, then the live half.
#
# WHY IT EXISTS. D-ID-1 keyed channels with no unique tvg-id by name instead
# of by stream URL, and shipped a one-time migration of state.json that the
# helper runs when the active fetch carries --state-dir. Every proof of it
# drove the helper alone (tests/test_fixture_id_rotate.py). The first time the
# running plugin was observed headless (docs/QA-HEADLESS-2026-09-21.md,
# section 1) the helper logged `moved 8` and the shell then wrote the state it
# had loaded BEFORE the fetch back over the file, on the same fetch, both
# fetches observed: favourites resolved 4 rows where the migrated state
# resolves 7, and `ipc refresh` logged `moved 8` a second time, which is only
# possible if the file had reverted. That is D-ID-3. This scenario is that
# observation made repeatable, and it is what a fix is graded by.
#
# WHAT IT DRIVES. IPC only, no wtype, no screenshot, so it runs under a
# nested headless cage (docs/SPIKE-CAGE-HEADLESS.md) or on the live session
# alike. The fixture is tests/fixtures/qa-id-rotate/ (read its README.md):
# list-v1.m3u, a seeded scheme-1 state with eight references that must move,
# and list-v2.m3u, the same list after a credential rotation. Every host is
# under .test; nothing here reaches the network.
#
# WHAT IS ASSERTED, and where the numbers come from (README.md's table):
#   ID1  the guide's Favorites scope resolves 7 rows, not 4, and by NAME in
#        state order: Alpha News, Hotel TV, Charlie Kids, Lima Twins, Golf HD,
#        Bravo Sports, Hash Twin 132789.
#   ID2  state.json on disk holds the n: id of every unique-name row the seed
#        referenced (six A rows plus the B pair Golf HD and Golf SD), the
#        merged favourite once, the seed's session record replayed as the last
#        play and moved with the rest (ruling PO-3; see RECENT_IDS below), the
#        two accepted-limit u: rows untouched (D-ID-2), and none of the eight
#        legacy ids anywhere; mode 0600.
#   ID3  `moved` appears EXACTLY once in the harness log after the first
#        fetch, and STILL exactly once after `ipc refresh`: a second `moved`
#        is the revert, in one number.
#   ID4  state.json is byte-stable across that refresh except the one field
#        the service legitimately rewrites on every successful fetch,
#        sources[].fetchedAt (Model.sourceStatsDiffer / withSourceStats): the
#        raw sha256 differs because of it, the file with that field masked
#        does not. The check is not vacuous: fetchedAt is asserted to have
#        advanced.
#   ID5  after switching to list-v2.m3u the favourites resolve by name on the
#        rotated list. NOT 7: the fixture's own README and python test say 5.
#        Lima Twins (a colliding-name pair) and Hash Twin 132789 (an fnv1a32
#        collision) stayed on u: ids by design and are orphaned by the
#        rotation -- D-ID-2's accepted limit, observable. The five that can
#        survive do, the two that cannot are named, and nothing moved on the
#        switch (the map of the rotated list has no key in the state).
#
# STATUS. Unlike the other scenarios in this directory, the live half HAS been
# run by the lane that wrote it, under cage on a nested display, never on the
# live session: against dev's Service.qml before the fix it answers 4 rows and
# two `moved` lines (red), against the fixed tree it is green. The counts are
# in the commit that added this file and on the D-ID-3 row of docs/STATUS.md.
#
# The seeded state is exactly the shape a user's own state.json has the first
# time they start a plugin version carrying scheme 2; `run.sh clean` wipes it,
# so it is installed after the clean and before the start, at 0600
# (CLAUDE.md 6), the mode the helper and the service both keep.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
PLUGIN_ROOT=$(cd "${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}" 2>/dev/null && pwd)
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
FIXTURE="$ROOT/tests/fixtures/qa-id-rotate"
STATE_DIR="$SCRATCH/state/omarchy-iptv"
STATE_FILE="$STATE_DIR/state.json"
# The harness's own stdout/stderr: run.sh prefixes quickshell's lines with
# `[qs] `, and the helper's stderr reaches it through Service.qml's
# console.warn sink as `omarchy-iptv playlist: ... moved N saved ...`.
LOG="$SCRATCH/id-rotate-scenario.log"
HARNESS_PID=""
pass=0
fail=0
checks=0

# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

ok()   { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad()  { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
check() { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }

# The display this scenario is about to drive, printed before every call that
# reaches a compositor (the harness start, every `run.sh ipc`), and refused
# when it is the live session and the caller said headless-only. A lane
# without the display sets OMARCHY_IPTV_HEADLESS_ONLY=1 and runs under cage;
# the display lane leaves it unset and this prints and proceeds.
display_guard() {
  local wl=${WAYLAND_DISPLAY:-wayland-1}
  printf '[id-rotate-scenario] WAYLAND_DISPLAY=%s\n' "$wl" >>"$LOG"
  if [[ ${OMARCHY_IPTV_HEADLESS_ONLY:-0} == 1 && ( $wl == wayland-1 || $wl == */wayland-1 ) ]]; then
    echo "[id-rotate-scenario] refusing: WAYLAND_DISPLAY=$wl is the live session and OMARCHY_IPTV_HEADLESS_ONLY=1" >&2
    exit 2
  fi
}
ipc()  { display_guard; "$RUN" ipc "$@" 2>/dev/null; }
gf()   { qa_guide_field "d$1" "$(ipc state)"; }
sf()   { qa_field "d$1" "$(ipc state)"; }
# A field of state.json on disk, through the same sentinels as the IPC reads:
# NOFILE when the file is missing or not JSON, NOFIELD when the expression
# does not resolve. Lists print as python prints them.
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
print(json.dumps(v) if isinstance(v, bool) else ("NOFIELD" if v is None else v))' "$STATE_FILE" "$1" 2>/dev/null \
    || printf '%s\n' "$QA_NO_FILE"
}
# The record of the active source in state.json, by the key the service
# reports, so the fetchedAt read is the active record's and not sources[0]'s.
active_fetched_at() {
  local key; key=$(sf "['activeSourceKey']")
  qa_value "$key" || { printf '%s\n' "$QA_NO_FIELD"; return; }
  sj "[s for s in d['sources'] if s.get('key') == '$key'][0]['fetchedAt']"
}
# `same` when two state.json snapshots are equal once sources[].fetchedAt is
# masked on both, else the top-level keys that differ; NOFILE when either
# side is not JSON. The mask is the ONE field adoptSourceStats rewrites on
# every successful fetch (Model.withSourceStats); nothing else may move.
state_diff_masked() {
  python3 -c '
import json, sys
try:
    a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
except Exception:
    print("NOFILE"); raise SystemExit(0)
for d in (a, b):
    for s in d.get("sources") or []:
        if isinstance(s, dict): s.pop("fetchedAt", None)
if a == b:
    print("same")
else:
    print(",".join(sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))) or "differs")' "$1" "$2" 2>/dev/null \
    || printf '%s\n' "$QA_NO_FILE"
}
moved_lines() { qa_count 'moved [0-9]+ saved channel reference' "$LOG"; }
# The Favorites rows AS THE GUIDE LISTS THEM, by name, in order, `|`-joined:
# scope to favorites, park on the first row, read the cursor, step. This is
# resolution by name through the guide's own rows (Model.js favorites scope:
# state order, unresolved ids skipped), not through a table of ids.
favorite_names() {
  local n c names="" i name
  ipc setScope favorites >/dev/null
  # Park on row 0 by the cursor's own index: `move` wraps (Model.moveCursor),
  # so a large negative delta lands anywhere, not at the top.
  n=$(gf "['rows']")
  c=$(gf "['cursorIndex']")
  qa_value "$n" && qa_value "$c" || { printf '%s\n' "$QA_NO_STATE"; return; }
  (( c > 0 )) && ipc move "$((-c))" >/dev/null
  [[ "$(gf "['cursorIndex']")" == 0 ]] || { printf '%s\n' "$QA_NO_STATE"; return; }
  for ((i = 0; i < n; i++)); do
    name=$(gf "['cursorName']")
    names+="${names:+|}$name"
    ipc move 1 >/dev/null
  done
  printf '%s\n' "$names"
}

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
  echo "[id-rotate-scenario] gave up waiting ${secs}s for '$want' from: $*" >&2
  return 1
}
# Until a command's answer is no longer `avoid`, bounded the same way.
wait_change() {
  local avoid=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ "$("$@")" != "$avoid" ]] && return 0
    sleep 0.1
  done
  echo "[id-rotate-scenario] gave up waiting ${secs}s for a change from '$avoid' by: $*" >&2
  return 1
}
# Until the file's mtime has held still for `quiet` tenths of a second, at
# most `secs` seconds: the exit path of a fetch writes state.json up to three
# times (the helper, adoptSourceStats, the remap), and a read in between
# would grade a transient.
wait_settled() {
  local file=$1 quiet=$2 secs=$3 i last now still=0
  last=$(stat -c %Y.%N -- "$file" 2>/dev/null || echo none)
  for ((i = 0; i < secs * 10; i++)); do
    sleep 0.1
    now=$(stat -c %Y.%N -- "$file" 2>/dev/null || echo none)
    if [[ $now == "$last" ]]; then still=$((still + 1)); (( still >= quiet )) && return 0
    else still=0; last=$now; fi
  done
  echo "[id-rotate-scenario] gave up waiting ${secs}s for $file to settle" >&2
  return 1
}

# The seed, row by row, as tests/fixtures/qa-id-rotate/README.md tabulates
# it. Literals on purpose: the point is that the RUNNING shell produces them.
FAV_V1_IDS="['n:de152e0a', 't:hotel.test', 'n:d8cf1772', 'u:4a0e659f', 'n:2a0db957', 'n:99ad941e', 'u:e2ffd78c']"
FAV_V1_NAMES="Alpha News|Hotel TV|Charlie Kids|Lima Twins|Golf HD|Bravo Sports|Hash Twin 132789"
FAV_V2_NAMES="Alpha News|Hotel TV|Charlie Kids|Golf HD|Bravo Sports"
# The seed's `session` record (Golf SD, u:1db3ed20) is a play this shell finds
# unfinished at load and, by ruling PO-3, replays as the last play before the
# record is cleared: it lands at the head of recents and on lastPlayed (over
# the seed's Foxtrot Docs, which is older). The helper never does that, so
# the python fixture test never sees it; here it is the eighth moved
# reference, visible as n:47f21214 in both slots.
RECENT_IDS="['n:47f21214', 'n:92937b2e', 't:india.test', 'n:320e63f7']"
LAST_PLAYED_ID="n:47f21214"
MERGED_ID="n:d8cf1772"
# The eight scheme-1 ids the migration moves (favourites, recents, lastPlayed,
# session). None may survive anywhere in the file.
LEGACY_MOVED_ERE='u:(9712e180|36f90b72|402cf731|58b2a668|33db2e82|b170b7bd|f91b61c4|1db3ed20)'

# ---------------------------------------------------------------- preflight
#
# `seam <label> <file> <ere> <at least>`: a POSITIVE count, never a `! grep`
# (qa_count answers 0 for a missing file, so an absent tree fails here).
seam() {
  local label=$1 file=$2 ere=$3 want=$4
  checks=$((checks + 1))
  local got
  got=$(qa_count "$ere" "$file")
  if (( got >= want )); then ok "$label"; else bad "$label (matched $got, wanted at least $want in ${file#"$PLUGIN_ROOT/"})"; fi
}

preflight() {
  echo "== preflight: can this tree keep the migration? (plugin: $PLUGIN_ROOT)"
  # The fix (D-ID-3): the map per parsed list, the move at apply, gated on moved.
  seam "Service.qml derives the id map of every parsed list"    "$PLUGIN_ROOT/Service.qml" 'idRemap: Model\.channelIdRemap\(channels\)' 1
  seam "Service.qml moves the loaded state onto it at apply"    "$PLUGIN_ROOT/Service.qml" 'Model\.remapStateIds\(root\.userState, remap\)' 1
  seam "Service.qml writes only when something moved"           "$PLUGIN_ROOT/Service.qml" '^ *if \(!\(moved\.moved > 0\)\) return' 1
  # What that calls, and what the helper half still needs (D-ID-1).
  seam "Model.js owns the scheme-1 -> scheme-2 map"             "$PLUGIN_ROOT/Model.js" '^function channelIdRemap\(channels\)' 1
  seam "Model.js owns the state move"                           "$PLUGIN_ROOT/Model.js" '^function remapStateIds\(state, remap\)' 1
  seam "the active fetch still carries --state-dir"             "$PLUGIN_ROOT/Service.qml" 'Model\.playlistFetchArgv\(root\.helperPath, root\.playlistUrl, root\.activeCacheDir, root\.stateDir\)' 1
  # The verbs the live half drives.
  seam "the harness answers state()"                            "$HERE/shell.qml" 'function state\(\): string' 1
  seam "the harness refreshes the active source"                "$HERE/shell.qml" 'function refresh\(\): string' 1
  seam "the harness adds a source"                              "$HERE/shell.qml" 'function addSource\(playlistUrl: string, epgUrl: string, label: string\): string' 1
  seam "the harness scopes the guide"                           "$HERE/shell.qml" 'function setScope\(id: string\): string' 1
  seam "state() carries the scope counts"                       "$HERE/shell.qml" 'scopes: g\.scopeList\.map' 1
  # The fixture, and that run.sh can be told to keep the seeded state.
  checks=$((checks + 1))
  if [[ -f $FIXTURE/state-seed.json && -f $FIXTURE/list-v1.m3u && -f $FIXTURE/list-v2.m3u ]]; then ok "the qa-id-rotate fixture is present"
  else bad "the qa-id-rotate fixture is missing under $FIXTURE"; fi
  checks=$((checks + 1))
  if qa_case_arm "$RUN" --keep && qa_case_arm "$RUN" --playlist; then ok "run.sh parses --keep and --playlist"
  else bad "run.sh does not parse --keep / --playlist (they are option spellings, not comments)"; fi
}

# ------------------------------------------------------------------- live
live() {
  echo "== setup (scratch $SCRATCH)"
  "$RUN" clean >/dev/null
  : >"$LOG"
  mkdir -p "$STATE_DIR" && chmod 0700 "$STATE_DIR"
  install -m 0600 "$FIXTURE/state-seed.json" "$STATE_FILE"
  check "the seed is installed at 0600 before the shell starts"        '[[ "$(stat -c %a "$STATE_FILE")" == 600 && "$(sj "len(d['\''favorites'\''])")" == 8 ]]'

  echo "== start harness (--open, list-v1)"
  HARNESS_TIMEOUT=${OMARCHY_IPTV_SCENARIO_TIMEOUT:-300}
  display_guard
  "$RUN" --keep --open --timeout "$HARNESS_TIMEOUT" --playlist "$FIXTURE/list-v1.m3u" >>"$LOG" 2>&1 &
  HARNESS_PID=$!
  wait_for 16 30 sf "['channels']" || bad "list-v1 never loaded; every check below is about nothing"
  wait_for true 10 gf "['opened']" || bad "the guide never opened; the scope reads below are about nothing"
  # The first fetch: the helper's move, then the exit path's writes.
  wait_for 1 15 moved_lines || bad "the helper never reported a move; the seed did not reach it"
  wait_settled "$STATE_FILE" 10 15 || bad "state.json kept changing; the reads below may grade a transient"

  echo "== ID1 the guide resolves the migrated favourites"
  scopes=$(gf "['scopes']")
  check "ID1: the Favorites scope resolves 7 rows, not 4 (got: $scopes)"   '[[ "$scopes" == *"'\''favorites=7'\''"* ]]'
  names=$(favorite_names)
  check "ID1: and by name, in state order, the merged row once (got: $names)" '[[ "$names" == "$FAV_V1_NAMES" ]]'

  echo "== ID2 state.json on disk holds the migrated ids"
  favs=$(sj "d['favorites']")
  check "ID2: favorites are the seven migrated ids, in order (got: $favs)" '[[ "$favs" == "$FAV_V1_IDS" ]]'
  check "ID2: the merged favourite appears exactly once"                  '[[ "$(sj "d['\''favorites'\''].count('\''$MERGED_ID'\'')")" == 1 ]]'
  recents=$(sj "[r['id'] for r in d['recents']]")
  last=$(sj "d['lastPlayed']['id']")
  check "ID2: recents moved with them, the replayed session first (got: $recents)" '[[ "$recents" == "$RECENT_IDS" ]]'
  check "ID2: so did lastPlayed (got: $last)"                             '[[ "$last" == "$LAST_PLAYED_ID" ]]'
  check "ID2: no moved legacy id survives anywhere in the file"           '[[ "$(qa_count "$LEGACY_MOVED_ERE" "$STATE_FILE")" == 0 ]]'
  check "ID2: the two accepted-limit rows keep their u: ids (D-ID-2)"     '[[ "$(qa_count "u:4a0e659f" "$STATE_FILE")" == 1 && "$(qa_count "u:e2ffd78c" "$STATE_FILE")" == 1 ]]'
  check "ID2: the file is 0600"                                           '[[ "$(stat -c %a "$STATE_FILE")" == 600 ]]'
  check "ID3: the first fetch logged exactly one move"                    '[[ "$(moved_lines)" == 1 ]]'

  echo "== ID3 / ID4 a refresh moves nothing and rewrites only fetchedAt"
  before_fetched=$(active_fetched_at)
  check "ID4: the active record carries the first fetch"                  'qa_value "$before_fetched"'
  cp -p "$STATE_FILE" "$SCRATCH/state-before-refresh.json"
  sha_before=$(sha256sum "$STATE_FILE" | cut -c1-64)
  ipc refresh >/dev/null
  wait_change "$before_fetched" 20 active_fetched_at || bad "the refresh never landed on the record"
  wait_settled "$STATE_FILE" 10 15 || bad "state.json kept changing after the refresh"
  sha_after=$(sha256sum "$STATE_FILE" | cut -c1-64)
  echo "   sha256 before $sha_before"
  echo "   sha256 after  $sha_after"
  check "ID3: the refresh logged no second move (still exactly one; got $(moved_lines))" '[[ "$(moved_lines)" == 1 ]]'
  check "ID4: fetchedAt advanced, so the stability check is about a real rewrite" '[[ "$(active_fetched_at)" != "$before_fetched" ]]'
  masked=$(state_diff_masked "$SCRATCH/state-before-refresh.json" "$STATE_FILE")
  check "ID4: state.json is identical across the refresh except sources[].fetchedAt (masked diff: $masked)" '[[ "$masked" == same ]]'
  check "ID4: and the guide still resolves 7"                             '[[ "$(gf "['\''scopes'\'']")" == *"'\''favorites=7'\''"* ]]'

  echo "== ID5 the rotated list (list-v2): names survive, the map has no key"
  v1key=$(sf "['activeSourceKey']")
  add=$(ipc addSource "$FIXTURE/list-v2.m3u" "" "Rotated")
  v2key=$(qa_json_field "d['id']" "$add")
  check "ID5: the rotated source was added"                               'qa_value "$v2key" && [[ "$v2key" != "$v1key" ]]'
  wait_for "$v2key" 30 sf "['activeSourceKey']" || bad "the shell never switched to the rotated source"
  wait_for false 10 sf "['switching']" || bad "the switch never finished"
  wait_for 16 10 sf "['channels']" || bad "list-v2 never loaded"
  wait_settled "$STATE_FILE" 10 15 || bad "state.json kept changing after the switch"
  names2=$(favorite_names)
  scopes2=$(gf "['scopes']")
  check "ID5: five favourites resolve by name on the rotated list (got: $names2)" '[[ "$scopes2" == *"'\''favorites=5'\''"* && "$names2" == "$FAV_V2_NAMES" ]]'
  check "ID5: the two D-ID-2 rows are the ones missing"                   '[[ "$names2" != *"Lima Twins"* && "$names2" != *"Hash Twin"* ]]'
  check "ID5: the switch moved nothing (still exactly one move logged)"   '[[ "$(moved_lines)" == 1 ]]'
  check "ID5: and left the seven favourite ids exactly as they were"      '[[ "$(sj "d['\''favorites'\'']")" == "$FAV_V1_IDS" ]]'

  echo "== privacy (R12)"
  checks=$((checks + 1))
  qa_answer_lacks '://' "$(ipc state)"
  case $? in
    0) ok "the state answer carries no URL" ;;
    1) bad "the state answer carries a URL" ;;
    *) bad "the IPC did not answer at all: 'no URL' is not evidence" ;;
  esac
  checks=$((checks + 1))
  qa_leak_on_labelled 'omarchy-iptv playlist' '://' "$LOG"
  case $? in
    0) ok "the helper's lines in the harness log carry no URL" ;;
    1) bad "a helper line in the harness log carries a URL" ;;
    *) bad "no helper line reached the harness log: 'no URL' is not evidence" ;;
  esac
}

trap cleanup EXIT

case ${1:-live} in
  check-tree) preflight ;;
  live|"")    preflight; live ;;
  *) echo "usage: id-rotate-scenario.sh [check-tree|live]" >&2; exit 2 ;;
esac

# The floor. A check that stops executing must turn the run red rather than
# shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ *seam ' id-rotate-scenario.sh            plus 2  -> check-tree
#   grep -cE '^ *(check|seam) ' id-rotate-scenario.sh    plus 4  -> live
# (the 2 are the fixture and run.sh probes, which bump `checks` by hand; the
# 4 are those two plus the privacy block's two bumps. The definitions of
# check() and seam() do not match the pattern, and the floor's own bump lands
# after the count is taken.) Never lower it to make a run green.
if [[ ${1:-live} == check-tree ]]; then
  EXPECTED_CHECKS=13
else
  EXPECTED_CHECKS=36
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
