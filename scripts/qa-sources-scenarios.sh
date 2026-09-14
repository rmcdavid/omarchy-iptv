#!/bin/bash
# scripts/qa-sources-scenarios.sh -- the Sources (M2-01) harness scenarios of
# docs/QA-SOURCES.md section 8, printed or, with --apply, executed against the
# dev harness (scripts/dev-harness/run.sh) in a scratch directory.
#
#   qa-sources-scenarios.sh list                          scenario ids, titles, what each needs
#   qa-sources-scenarios.sh print <SRC-Hnn> [--fresh] [--worst] [--count N]
#                                                         print the exact commands and EXPECT lines
#   qa-sources-scenarios.sh run <SRC-Hnn> --apply [...]   execute the deterministic steps (same output)
#   qa-sources-scenarios.sh fixtures [--apply]            parse every fixture; run the M3U/XMLTV ones through the helper
#   qa-sources-scenarios.sh seed [--apply] [--fresh]      copy fixtures into the scratch tree, seed the v1 state + legacy cache
#   qa-sources-scenarios.sh check-harness                 which Lane 2 harness verbs / helper verbs are present
#   qa-sources-scenarios.sh key <url-or-path>             fnv1a32 source key of a URL (same algorithm as Model.js / helper)
#   qa-sources-scenarios.sh stop                          kill a harness started by `run` (by recorded pid)
#
# Everything lives under $OMARCHY_IPTV_HARNESS_DIR (default
# $XDG_RUNTIME_DIR/omarchy-iptv-qa-sources): the harness scratch tree
# (root/ cache/ state/ runtime/ fixtures/ shots/) plus logs/ and cli-cache/.
# The script REFUSES to run when that directory resolves into a real plugin
# location (~/.config, ~/.cache/omarchy-iptv, ~/.local/state/omarchy-iptv,
# /usr/share/omarchy, $XDG_RUNTIME_DIR/omarchy-iptv) or into the repository.
# It never calls `omarchy plugin|bar|theme`, `hyprctl dispatch|reload|keyword`
# or sudo; every helper invocation passes --cache-dir / --state-dir under the
# scratch tree; key events (wtype) are sent only while the harness guide
# reports itself open (exclusive keyboard focus), so they cannot land in
# another window. `wl-copy` DOES replace the user's clipboard (paste steps).
#
# Scenarios that need Lane 2's harness verbs (addSource, switchSource, ...)
# or the helper `cache` subcommand refuse to --apply until those exist and
# say which one is missing; `print` always works.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
H="$ROOT/scripts/dev-harness/run.sh"
HELPER="$ROOT/bin/omarchy-iptv"
FIX="$ROOT/tests/fixtures/qa-sources"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-qa-sources}
APPLY=0
FRESH=0
WORST=0
COUNT=49
T0=1789244100

# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

# Fixture URLs as served by the harness fixture server (run.sh --serve) and their keys.
A=http://127.0.0.1:8765/qa-src-a.m3u;        KA=584a58e5
B=http://127.0.0.1:8765/qa-src-b.m3u;        KB=733cf68c
C="http://qa-user:qa-secret@127.0.0.1:8765/qa-src-userinfo.m3u"; KC=25b70358
XS=http://127.0.0.1:8765; XU=user; XP="pa ss"; KX=6e90a03e
EPGA=http://127.0.0.1:8765/qa-src-a.xml

usage() { sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; }
fail() { echo "qa-sources: $*" >&2; exit 1; }
# Set by harness_start when the harness never answered; read by main.
setup_failed=0

# ---------------------------------------------------------------- guards

refuse_real_dirs() {
  local real home b
  # F4: sh_step interpolates $SCRATCH into a `bash -c` snippet unquoted, so a
  # scratch path carrying a quote or $(...) would be EXECUTED - the shape
  # CLAUDE.md constraint 2 forbids. Refuse a path that could be shell text.
  qa_safe_path "$SCRATCH" || fail "refusing: OMARCHY_IPTV_HARNESS_DIR carries shell metacharacters: $SCRATCH"
  real=$(realpath -m -- "$SCRATCH")
  home=$(realpath -m -- "$HOME")
  [[ $real == /* ]] || fail "scratch dir must be absolute: $SCRATCH"
  # Exactly these two are refused as a whole (a scratch dir below $HOME is fine).
  for b in / "$home"; do
    [[ $real == "$b" ]] && fail "refusing: scratch dir $real is $b itself; set OMARCHY_IPTV_HARNESS_DIR to a scratch path"
  done
  # These trees (and anything inside them) hold the real plugin, its settings,
  # its cache and state, the host shell, the runtime socket dir, and the repo.
  for b in "$home/.config" "$home/.cache/omarchy-iptv" "$home/.local/state/omarchy-iptv" \
           /usr/share/omarchy "$REAL_RUNTIME/omarchy-iptv" "$ROOT"; do
    b=$(realpath -m -- "$b")
    if [[ $real == "$b" || $real == "$b"/* ]]; then
      fail "refusing: scratch dir $real is inside $b (a real plugin location or the repository); set OMARCHY_IPTV_HARNESS_DIR to a scratch path"
    fi
  done
}

# ------------------------------------------------------------- step runner

step() {            # step "<what>" cmd args...   (printed as a shell line; run with --apply)
  local desc=$1; shift
  printf '# %s\n$ %s\n' "$desc" "$(printf '%q ' "$@")"
  if (( APPLY )); then "$@"; fi
}
sh_step() {         # sh_step "<what>" "<snippet>"   (snippet printed verbatim; run through bash -c)
  printf '# %s\n$ %s\n' "$1" "$2"
  if (( APPLY )); then bash -c "$2"; fi
}
expect() { printf 'EXPECT: %s\n' "$*"; }
note()   { printf 'NOTE: %s\n' "$*"; }
pause()  { printf '$ sleep %s\n' "$1"; if (( APPLY )); then sleep "$1"; fi; }

ipc_step() {        # ipc_step "<what>" <fn> [args]   -> run.sh ipc <fn> ...
  local desc=$1; shift
  step "$desc" "$H" ipc "$@"
}

keys() {            # keys <wtype args>: only while the harness guide is open
  printf '$ %q key %s\n' "$H" "$(printf '%q ' "$@")"
  if (( APPLY )); then
    local opened
    opened=$("$H" ipc state 2>/dev/null | jq -r '.guide.opened' 2>/dev/null || true)
    if [[ $opened != true ]]; then
      echo "skip: the harness guide is not open; keys would reach another window" >&2
      return 0
    fi
    "$H" key "$@"
    sleep 0.3
  fi
}

shot() { step "screenshot $1" "$H" shot "$1"; }

# B3. This returns 1 after 30 s with "harness did not answer" on stderr, and
# every one of its 19 call sites invoked it bare in a file with no `set -e`.
# All sixteen SRC-H* scenarios then ran every remaining step against a dead
# harness, printing empty output under each EXPECT line exactly as a good run
# prints its answers. Call sites now say `|| return 1`, and a SETUP FAILED
# banner makes the abandonment visible in the transcript.
harness_start() {   # harness_start <run.sh args>
  mkdir -p "$SCRATCH/logs"
  printf '# start the harness in the background (log: %s)\n$ %q %s > %q 2>&1 &\n' "$SCRATCH/logs/run.log" "$H" "$(printf '%q ' "$@")" "$SCRATCH/logs/run.log"
  (( APPLY )) || return 0
  "$H" "$@" > "$SCRATCH/logs/run.log" 2>&1 &
  echo $! > "$SCRATCH/logs/run.pid"
  local i
  for i in $(seq 1 60); do
    sleep 0.5
    if "$H" ipc state >/dev/null 2>&1; then return 0; fi
  done
  echo "harness did not answer within 30 s; see $SCRATCH/logs/run.log" >&2
  printf '\n!!!! SETUP FAILED: the harness never came up. Every step below this\n'
  printf '!!!! point would have run against nothing and printed empty output\n'
  printf '!!!! under its EXPECT line. This scenario is ABANDONED, not passed.\n\n'
  setup_failed=1
  harness_stop
  return 1
}

harness_stop() {
  printf '# stop the harness\n$ kill "$(cat %q)"\n' "$SCRATCH/logs/run.pid"
  (( APPLY )) || return 0
  if [[ -f $SCRATCH/logs/run.pid ]]; then
    local pid; pid=$(cat "$SCRATCH/logs/run.pid")
    kill "$pid" 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; sleep 0.3; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    rm -f "$SCRATCH/logs/run.pid"
  fi
  # Belt and braces, scoped to THIS scratch dir (see run.sh cleanup).
  pkill -f "quickshell -p $SCRATCH/root" 2>/dev/null
  pkill -f "http.server 8765 --bind 127.0.0.1 --directory $SCRATCH/fixtures" 2>/dev/null
  return 0
}

# ------------------------------------------------------ availability checks

have_verb() { grep -qE "function $1\(" "$ROOT/scripts/dev-harness/shell.qml"; }
have_cache_verb() { python3 "$HELPER" cache --help >/dev/null 2>&1; }
fake_applies_entry() {
  awk '/function updateEntryInline/{f=1} f&&/barConfig|setSetting/{print "yes"; exit} f&&/^  }/{exit}' "$ROOT/scripts/dev-harness/shell.qml" | grep -q yes
}

need() {            # need verbs:a,b helper:cache apply:entry -- in print mode only notes
  local req missing=() r kind what
  for req in "$@"; do
    kind=${req%%:*}; what=${req#*:}
    case $kind in
      verbs) IFS=, read -ra vs <<<"$what"; for r in "${vs[@]}"; do have_verb "$r" || missing+=("harness verb $r"); done ;;
      helper) have_cache_verb || missing+=("helper subcommand $what") ;;
      apply) fake_applies_entry || missing+=("fake updateEntryInline must APPLY the entry to fakeShell.barConfig") ;;
    esac
  done
  if (( ${#missing[@]} )); then
    local m; for m in "${missing[@]}"; do note "needs $m (Lane 2)"; done
    if (( APPLY )); then echo "qa-sources: cannot --apply: ${missing[*]}" >&2; exit 3; fi
  fi
}

fnv1a32() {
  python3 - "$1" <<'PY'
import sys
h = 0x811C9DC5
for b in sys.argv[1].encode("utf-8"):
    h ^= b
    h = (h * 0x01000193) & 0xFFFFFFFF
print("%08x" % h)
PY
}

# ---------------------------------------------------------------- seeding

seed_fixtures() {
  step "scratch tree" mkdir -p "$SCRATCH/fixtures" "$SCRATCH/logs" "$SCRATCH/shots" "$SCRATCH/cache" "$SCRATCH/state"
  step "copy the served fixtures" cp "$FIX/qa-src-a.m3u" "$FIX/qa-src-b.m3u" "$FIX/qa-src-userinfo.m3u" "$FIX/qa-src-a.xml" "$FIX/xtream/get.php" "$FIX/xtream/xmltv.php" "$SCRATCH/fixtures/"
  step "served error fixtures from the M1 catalogue" cp "$ROOT/tests/fixtures/qa-empty.m3u" "$ROOT/tests/fixtures/qa-not-m3u.html" "$SCRATCH/fixtures/"
}

seed_v1() {         # v1 state + legacy single cache (docs/QA-SOURCES.md section 4)
  step "v0.1.0 directories" mkdir -p "$SCRATCH/cache/omarchy-iptv" "$SCRATCH/state/omarchy-iptv"
  step "legacy cache files" cp "$FIX/legacy-cache/channels.json" "$FIX/legacy-cache/playlist-status.json" "$SCRATCH/cache/omarchy-iptv/"
  step "v1 state" cp "$FIX/state-v1.json" "$SCRATCH/state/omarchy-iptv/state.json"
  step "v0.1.0 modes" chmod 700 "$SCRATCH/cache/omarchy-iptv" "$SCRATCH/state/omarchy-iptv"
  step "v0.1.0 modes (files)" chmod 600 "$SCRATCH/cache/omarchy-iptv/channels.json" "$SCRATCH/cache/omarchy-iptv/playlist-status.json" "$SCRATCH/state/omarchy-iptv/state.json"
  sh_step "record the legacy bytes" "cd $(printf '%q' "$SCRATCH/cache/omarchy-iptv") && sha256sum channels.json playlist-status.json > $(printf '%q' "$SCRATCH/logs/legacy.sha")"
  if (( FRESH )); then
    sh_step "fresh stamps so no refresh runs (proves the moved bytes and 'no helper run')" "python3 - $(printf '%q' "$SCRATCH/cache/omarchy-iptv") <<'PY'
import json, os, sys, time
d = sys.argv[1]; now = int(time.time())
for name, key in (('channels.json', 'generatedAt'), ('playlist-status.json', 'fetchedAt')):
    p = os.path.join(d, name); doc = json.load(open(p)); doc[key] = now
    json.dump(doc, open(p, 'w'), separators=(',', ':'))
print('stamped', now)
PY"
  else
    note "stamps stay at T0 (1789244100): the migrated cache is stale, a background refresh follows (SRC-SW-04 path); use --fresh for the no-refresh variant"
  fi
}

write_state_v2() {  # write_state_v2 <count>: a v2 state with N sources, all at 127.0.0.1:9 (never fetched)
  local worst=$WORST
  sh_step "v2 state with $1 sources ($( ((worst)) && echo worst-case 2048-char URLs || echo typical URLs ))" "python3 - $(printf '%q' "$SCRATCH/state/omarchy-iptv") $1 $worst <<'PY'
import json, os, sys
d, n, worst = sys.argv[1], int(sys.argv[2]), sys.argv[3] == '1'
os.makedirs(d, mode=0o700, exist_ok=True)
def fnv(s):
    h = 0x811C9DC5
    for b in s.encode(): h ^= b; h = (h * 0x01000193) & 0xFFFFFFFF
    return '%08x' % h
srcs = []
for i in range(n):
    url = 'http://127.0.0.1:9/src%03d.m3u' % i
    epg = ''
    label = 'src%03d' % i
    if worst:
        url = (url + '?t=').ljust(2048, 'a'); epg = ('http://127.0.0.1:9/epg%03d.xml?t=' % i).ljust(2048, 'b'); label = ('Label %03d ' % i).ljust(64, 'x')
    srcs.append({'key': fnv(url), 'url': url, 'epgUrl': epg, 'kind': 'http', 'label': label, 'labelCustom': False,
                 'origin': 'guide', 'addedAt': 1789244100 + i, 'lastUsed': 1789244100 + i, 'fetchedAt': 0, 'channelCount': 0, 'groupCount': 0})
st = {'version': 2, 'cacheLayout': 2, 'favorites': [], 'recents': [], 'lastPlayed': None, 'sources': srcs}
p = os.path.join(d, 'state.json')
fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as h: json.dump(st, h, separators=(',', ':'))
os.chmod(p, 0o600)
print(p, os.path.getsize(p), 'bytes', n, 'sources')
PY"
}

write_tampered_state() {
  sh_step "tampered v2 state (SRC-SEC-21 shapes)" "python3 - $(printf '%q' "$SCRATCH/state/omarchy-iptv") <<'PY'
import json, os, sys
d = sys.argv[1]; os.makedirs(d, mode=0o700, exist_ok=True)
good = {'key': '584a58e5', 'url': 'http://127.0.0.1:8765/qa-src-a.m3u', 'epgUrl': '', 'kind': 'http', 'label': 'Alpha', 'labelCustom': False, 'origin': 'guide', 'addedAt': 1, 'lastUsed': 1, 'fetchedAt': 0, 'channelCount': 0, 'groupCount': 0}
bad = [
  dict(good, key='../x', url='http://127.0.0.1:9/a.m3u'),
  dict(good, key='abc', url='http://127.0.0.1:9/b.m3u'),
  dict(good, key='deadbeef', url='http://127.0.0.1:9/c\\u0000d.m3u'),
  dict(good, key='deadbef0', url='http://127.0.0.1:9/' + 'a' * 3000),
  dict(good, key='deadbef1', url='http://127.0.0.1:9/e.m3u', label='L' * 500),
  dict(good),                                      # duplicate url and key: first wins
  'not-an-object', 42, None,
  dict(good, key='deadbef2', url='http://127.0.0.1:9/f.m3u', channelCount='x', lastUsed='y'),
]
st = {'version': 2, 'cacheLayout': 'x', 'favorites': ['t:qa.a.news1'], 'recents': [], 'lastPlayed': None, 'sources': [good] + bad}
p = os.path.join(d, 'state.json')
fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as h: json.dump(st, h)
print(p, 'written; valid records expected after load: 584a58e5 (+ deadbef2 if coercion keeps it)')
PY"
}

# --------------------------------------------------------------- scenarios

SCENARIOS=(
  "SRC-H01|Migration from a v1 install (v1 state + legacy cache -> v2 + sources/<key>/)|helper:cache"
  "SRC-H02|First run (S1): typed path / served URL, Enter, result line, Esc rules, focus order|verbs:sources,activeCache apply:entry"
  "SRC-H03|Invalid input (S8): every UX 5.4 code inline, no helper run|verbs:sources"
  "SRC-H04|Paste (D9): Ctrl+V, Shift+Insert, multi-line, RTL, 100 KB, masked-on-arrival|verbs:sources"
  "SRC-H05|Add + fetch failure keeps the active source (S8)|verbs:addSource,sources,signals apply:entry"
  "SRC-H06|Switch (S3) and the Sources list (S2)|verbs:addSource,switchSource,sources,activeCache apply:entry"
  "SRC-H07|Remove (S7): dialog, non-active, active, last|verbs:sources,removeSource apply:entry"
  "SRC-H08|Switch timing on a 10k list (PERF)|verbs:switchSource,addSource apply:entry"
  "SRC-H09|CLI parity (S5) through ipc set|verbs:sources apply:entry"
  "SRC-H10|Xtream (S6) with the served get.php / xmltv.php routes|verbs:xtream,editMasked,sources apply:entry"
  "SRC-H11|Duplicate, label collisions, the 50-source cap|verbs:addSource,sources"
  "SRC-H12|Edit (S4): label-only, EPG-only, playlist URL, masked field keys|verbs:updateSource,sources,editMasked apply:entry"
  "SRC-H13|Privacy and security sweep of every sink|verbs:sources,addSource,xtream helper:cache"
  "SRC-H14|Cancel, busy, deadlines, persist failure|verbs:addSource,cancelProbe,switchSource,removeSource"
  "SRC-H15|Cache verbs and key safety (helper CLI only)|helper:cache"
  "SRC-H16|State file hygiene and size (50 records, tampered file)|helper:cache"
)

scenario_title() { local s; for s in "${SCENARIOS[@]}"; do [[ ${s%%|*} == "$1" ]] && { local r=${s#*|}; echo "${r%%|*}"; return; }; done; }
scenario_needs() { local s; for s in "${SCENARIOS[@]}"; do [[ ${s%%|*} == "$1" ]] && { echo "${s##*|}"; return; }; done; }

banner() { printf '\n==== %s: %s ====\n' "$1" "$(scenario_title "$1")"; printf 'scratch: %s\n' "$SCRATCH"; }

common_start() {    # common_start <playlist or none> [extra run.sh args]
  local pl=$1; shift
  seed_fixtures
  harness_start --open --serve --keep --timeout 0 --playlist "$pl" "$@" || return 1
}

scenario_SRC_H01() {
  banner SRC-H01; need helper:cache
  step "wipe cache/state/runtime" "$H" clean
  seed_fixtures
  seed_v1
  harness_start --open --serve --keep --timeout 0 --playlist "$A" || return 1
  pause 3
  sh_step "state after migration" "jq '{version,cacheLayout,favorites,recents,lastPlayed,sources}' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  expect "version 2, cacheLayout 2, favorites [t:qa.a.news1, t:qa.shared, u:502142db], 3 recents in order, lastPlayed intact; sources[0] key $KA url $A origin migrated fetchedAt 1789244100 (or now with --fresh) channelCount 8 groupCount 3 (SRC-MIG-01)"
  sh_step "layout" "ls -la $(printf '%q' "$SCRATCH/cache/omarchy-iptv") $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources/$KA")"
  expect "top-level channels.json / playlist-status.json gone, no .tmp-*, sources/$KA/ holds them (SRC-MIG-02)"
  sh_step "modes" "find $(printf '%q' "$SCRATCH/cache") $(printf '%q' "$SCRATCH/state") -exec stat -c '%a %n' {} +"
  expect "700 directories, 600 files (SRC-SEC-09)"
  sh_step "moved bytes (with --fresh the sha must match)" "cd $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources/$KA") && sha256sum channels.json playlist-status.json; cat $(printf '%q' "$SCRATCH/logs/legacy.sha")"
  sh_step "console: migrate, prune, helper runs" "grep -nE 'cache migrate|cache prune|playlist:|omarchy-iptv' $(printf '%q' "$SCRATCH/logs/run.log") | head -40"
  expect "one migrate then one prune; with --fresh no 'playlist:' line (SRC-SW-05); keys only, no URL (SRC-PRIV-08)"
  ipc_step "guide and service state" state
  expect "guide rows 8 within ~1.5 s of start, favorites 3, Recent 3 (SRC-MIG-03); service activeSourceKey $KA"
  shot sources-migrated
  harness_stop
  harness_start --open --serve --keep --timeout 0 --playlist "$A" || return 1
  pause 3
  sh_step "second start: no second migrate" "grep -c 'cache migrate' $(printf '%q' "$SCRATCH/logs/run.log"); stat -c '%Y %a %s' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  expect "0 migrate lines; state.json untouched (SRC-MIG-04, SRC-SEC-22)"
  harness_stop
  note "variants: (a) '--playlist none' over a fresh seed_v1 -> legacy files deleted (cache migrate without --key), sources [] (SRC-MIG-05); (b) printf 'garbage{{{' > state.json before start -> empty v2 state, migration still runs (SRC-MIG-08)"
}

scenario_SRC_H02() {
  banner SRC-H02; need verbs:sources,activeCache apply:entry
  step "wipe" "$H" clean
  common_start none || return 1
  shot sources-first-run
  ipc_step "mode and form" state
  expect "guide.mode sourceEdit (origin firstRun), Playlist focused; footer 'Enter load - Tab next field - Ctrl+V paste - Esc close' (SRC-FR-01, SRC-UI-01)"
  keys o r f x s
  ipc_step "letters became text, nothing acted" state
  expect "form value 'orfxs', no refresh, no stop (SRC-KEY-07)"
  keys -M ctrl u -m ctrl
  keys "$SCRATCH/fixtures/qa-src-a.m3u"
  keys -k Return
  pause 2
  ipc_step "after Enter (path)" state
  expect "'Reading the file...' then mode search, rows 8, footer transient '8 channels in 3 groups' (SRC-FR-02/03)"
  shot sources-first-run-done
  sh_step "updateEntryInline logged once, keys only" "grep -n updateEntryInline $(printf '%q' "$SCRATCH/logs/run.log")"
  ipc_step "sources view" sources
  expect "one record, kind file, host 'local file', label qa-src-a.m3u, no url key (SRC-LST-11)"
  ipc_step "active cache dir" activeCache
  expect "$SCRATCH/cache/omarchy-iptv/sources/<fnv1a32 of the path> (scripts/qa-sources-scenarios.sh key <path>)"
  harness_stop
  note "repeat from --playlist none typing the served URL $A, Tab, $EPGA, Return: 'Fetching from 127.0.0.1...', then 'Now: Alpha Evergreen' rows and epg-* files under sources/$KA/ (SRC-FR-10)"
  note "Esc rules (SRC-FR-06): type text, Escape (cleared, footer 'Esc clear'); Tab, type in EPG, Escape x2 (focus moves then clears); Escape with every field empty closes the guide"
  note "focus order (SRC-A11Y-03): Tab x5 while reading state().guide.form.focus -> Playlist, EPG, Use Xtream login instead, Load, Playlist"
}

scenario_SRC_H03() {
  banner SRC-H03; need verbs:sources
  step "wipe" "$H" clean
  common_start none || return 1
  local v
  for v in 'ftp://x' 'javascript:alert(1)' 'data:text/plain,x' 'provider.test/list' './list.m3u' '~/tv/list.m3u' '/proc/self/environ' 'http://h .test/' 'http://'; do
    keys -M ctrl u -m ctrl
    keys "$v"
    keys -k Return
    ipc_step "result line for $v" state
    sh_step "no helper process, no new directory" "pgrep -fc 'omarchy-iptv playlist' || true; ls $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources") 2>/dev/null || echo '(no sources dir yet)'"
  done
  expect "per vector the UX 5.4 string (scheme / relative_path / invalid; /proc per SRC-DEC-03; ~ per SRC-DEC-01), focus on Playlist, accent urgent, 0 helper processes, no directory (SRC-ERR-01/04)"
  sh_step "3,000-character vector" "python3 -c \"print('http://h.test/' + 'a'*3000, end='')\" | wl-copy"
  keys -M ctrl u -m ctrl
  keys -M ctrl v -m ctrl
  keys -k Return
  ipc_step "too_long" state
  expect "'Too long - max 2,048 characters'; the field holds 2048 characters (maximumLength)"
  keys -M ctrl u -m ctrl
  keys -k Return
  ipc_step "empty" state
  expect "'Enter a playlist URL or path'"
  keys "http://h .test/"
  keys -k Return
  shot sources-invalid
  keys x
  ipc_step "error clears on the next edit" state
  harness_stop
}

scenario_SRC_H04() {
  banner SRC-H04; need verbs:sources
  step "wipe" "$H" clean
  common_start none || return 1
  note "wl-copy replaces the user's clipboard for the duration of this scenario"
  step "clipboard = plain URL" wl-copy -- "$A"
  keys -M ctrl v -m ctrl
  ipc_step "field after Ctrl+V" state
  expect "value $A (length 34), not masked, no eye (SRC-FR-12)"
  keys -M ctrl u -m ctrl
  keys -M shift -k Insert -m shift
  ipc_step "field after Shift+Insert" state
  expect "same value; if both chords paste nothing, Lane 1 flips pasteViaProcess and this scenario is re-run (D9)"
  keys -M ctrl u -m ctrl
  step "clipboard = two lines + tab" wl-copy < "$FIX/paste/paste-multiline.txt"
  keys -M ctrl v -m ctrl
  ipc_step "multi-line paste collapsed" state
  expect "one line, value $A, length 34 (SRC-SEC-01)"
  keys -M ctrl u -m ctrl
  step "clipboard = RTL / zero-width / BOM / NBSP" wl-copy < "$FIX/nonascii/paste-rtl.txt"
  keys -M ctrl v -m ctrl
  ipc_step "RTL paste" state
  shot sources-paste-rtl
  expect "per SRC-DEC-05: control chars stripped, NBSP trimmed, bidi/zero-width kept or refused; scheme://host readable in the screenshot (SRC-SEC-03)"
  keys -M ctrl u -m ctrl
  sh_step "clipboard = 100 KB" "python3 -c \"print('http://h.test/' + 'a'*102400, end='')\" | wl-copy"
  keys -M ctrl v -m ctrl
  shot sources-paste-100k
  ipc_step "100 KB paste capped" state
  expect "field length 2048, screenshot within 1 s, no console line with the text (SRC-SEC-02)"
  keys -k Return
  ipc_step "validator" state
  expect "'Too long - max 2,048 characters', no helper process"
  keys -M ctrl u -m ctrl
  step "clipboard = userinfo URL" wl-copy -- "$C"
  keys -M ctrl v -m ctrl
  shot sources-first-run-masked
  ipc_step "masked on arrival" state
  expect "masked rendering http://****@127.0.0.1:8765/qa-src-userinfo.m3u, eye U+F0208, caret hidden, footer '... Ctrl+R reveal - Ctrl+V replace - Esc clear' (SRC-UI-02, SRC-PRIV-06)"
  step "clipboard = plain URL again" wl-copy -- "$A"
  keys -M ctrl v -m ctrl
  ipc_step "paste over a masked field replaces it" state
  expect "value $A, no longer masked (SRC-KEY-04)"
  harness_stop
}

scenario_SRC_H05() {
  banner SRC-H05; need verbs:addSource,sources,signals apply:entry
  step "wipe" "$H" clean
  common_start "$A" || return 1
  pause 3
  sh_step "updateEntryInline count before" "grep -c updateEntryInline $(printf '%q' "$SCRATCH/logs/run.log")"
  ipc_step "add a refused endpoint" addSource http://127.0.0.1:9/x.m3u "" ""
  expect "{ok:true, id:9d0767b3} at once (probe started)"
  pause 3
  ipc_step "signals" signals
  expect "sourceProbeFinished {ok:false, id:9d0767b3, reason:'Connection refused', host:'127.0.0.1'} (SRC-SVC-03, SRC-ERR-02)"
  ipc_step "active source untouched" state
  expect "service.activeSourceKey $KA, guide rows 8, configured true (SRC-ERR-03)"
  sh_step "updateEntryInline count after (unchanged)" "grep -c updateEntryInline $(printf '%q' "$SCRATCH/logs/run.log")"
  ipc_step "history after the failure" sources
  expect "per SRC-DEC-13: a 'not loaded yet' row for 127.0.0.1 or no row"
  ipc_step "open the guide" open '{}'
  keys -k Tab o a
  keys "http://127.0.0.1:8765/missing.m3u"
  keys -k Return
  pause 2
  shot sources-add-failed
  ipc_step "form after the failure" state
  expect "result line 'HTTP 404 Not Found from 127.0.0.1', form thawed, focus Playlist (SRC-UI-04)"
  keys -k Return
  pause 2
  ipc_step "retry re-probes the same record" sources
  expect "no duplicate record (SRC-ERR-08)"
  keys -k Escape
  ipc_step "served qa-not-m3u.html" addSource http://127.0.0.1:8765/qa-not-m3u.html "" ""
  pause 2
  ipc_step "served qa-empty.m3u" addSource http://127.0.0.1:8765/qa-empty.m3u "" ""
  pause 2
  ipc_step "reasons" signals
  expect "'Not an M3U playlist' and 'Playlist has no channels' with host 127.0.0.1"
  sh_step "console stderr relay is redacted" "grep -n 'omarchy-iptv' $(printf '%q' "$SCRATCH/logs/run.log") | grep -cE '://|\\?' || true"
  expect "0 (SRC-SEC-15)"
  harness_stop
}

scenario_SRC_H06() {
  banner SRC-H06; need verbs:addSource,switchSource,sources,activeCache apply:entry
  step "wipe" "$H" clean
  seed_fixtures
  FRESH=1 seed_v1
  harness_start --open --serve --keep --timeout 0 --playlist "$A" || return 1
  pause 3
  ipc_step "add B (probe, becomes active)" addSource "$B" "" ""
  pause 3
  ipc_step "add C as a path source" addSource "$SCRATCH/fixtures/qa-src-userinfo.m3u" "" "Charlie"
  pause 3
  ipc_step "back to A through the CLI path" set playlistUrl "$A"
  pause 1
  ipc_step "open the guide" open '{}'
  keys -k Tab o
  shot sources-list
  ipc_step "sources mode" state
  expect "guide.mode sources, cursor on the active row (A), header '3 sources' (SRC-LST-01, SRC-UI-07)"
  ipc_step "rows" sources
  expect "A active host 127.0.0.1 8 channels 3 groups; B 5/2 no EPG; Charlie kind file host 'local file' 3/1; no url key (SRC-LST-03, SRC-LST-11)"
  keys j j k
  keys -k Home
  keys -k End
  keys h l r s f / 4
  keys -k Tab
  ipc_step "ignored keys" state
  expect "cursor moved by j/k/Home/End only; no refresh, no stop, no search (SRC-LST-10)"
  keys -k Home
  keys j
  sh_step "updateEntryInline count before the switch" "grep -c updateEntryInline $(printf '%q' "$SCRATCH/logs/run.log")"
  keys -k Return
  pause 2
  ipc_step "after Enter on B" state
  expect "service.activeSourceKey $KB, rows 5, mode search, query empty, footer 'Switched to <label of B> - 5 channels' (SRC-SW-01, SRC-SW-10)"
  ipc_step "active cache" activeCache
  expect ".../sources/$KB"
  sh_step "updateEntryInline count after (+1)" "grep -n updateEntryInline $(printf '%q' "$SCRATCH/logs/run.log") | tail -1"
  shot sources-switched
  ipc_step "favorites under B" setScope favorites
  ipc_step "favorites scope" state
  expect "1 row 'Shared Channel' (t:qa.shared); Favorites - 1 channel (SRC-SW-07)"
  sh_step "state.json keeps all three favorites" "jq -c .favorites $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  keys -k Tab o
  keys -k Home
  keys -k space
  ipc_step "Space on A: switched in place" state
  expect "mode still sources, A active, transient in the footer (SRC-SW-03)"
  shot sources-space
  sh_step "helper processes after the switches (fresh cache: none)" "for i in 1 2 3 4 5 6; do pgrep -fc 'omarchy-iptv playlist' || true; sleep 0.5; done"
  expect "0 every time (SRC-SW-05)"
  keys -k Return
  ipc_step "Enter on the active row: no reload" state
  sh_step "no extra updateEntryInline" "grep -c updateEntryInline $(printf '%q' "$SCRATCH/logs/run.log")"
  expect "count unchanged (SRC-SW-02, SRC-SVC-08)"
  harness_stop
  note "stale variant: set fetchedAt of sources/$KB/playlist-status.json to now-40000 (python json edit), restart --keep, switch to B -> 'Refreshing...' then silent success (SRC-SW-04)"
  note "playback variant: --serve fixture source (harness.m3u) added and a channel played, then switch: same mpv pid, zap 1 -> no (SRC-SW-08)"
}

scenario_SRC_H07() {
  banner SRC-H07; need verbs:sources,removeSource apply:entry
  note "starts from the SRC-H06 end state (three sources, A active); run SRC-H06 first or seed the same way"
  harness_start --open --serve --keep --timeout 0 --playlist "$A" || return 1
  pause 3
  ipc_step "open the guide" open '{}'
  keys -k Tab o j
  keys x
  shot sources-confirm
  ipc_step "dialog" state
  expect "mode confirmRemove; message 'Remove \"<label of B>\"? Its cache is deleted too.'; Remove preselected; footer 'Left/Right choose - Enter confirm - Esc cancel' (SRC-RM-01, SRC-UI-10)"
  keys -k Escape
  keys j
  ipc_step "cancel restored key focus" state
  expect "mode sources, cursor moved by j (SRC-RM-05, SRC-KEY-10)"
  keys k x
  keys -k Left
  keys -k Right
  keys -k Return
  pause 2
  sh_step "B's directory gone, others intact" "ls $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources"); jq -c '[.sources[].key]' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  expect "$KB absent; $KA and the path source present (SRC-RM-02)"
  ipc_step "transient" state
  expect "footer 'Removed <label of B>', cursor clamped"
  keys -k Home
  keys x
  ipc_step "active variant message" state
  expect "'Remove \"<label of A>\"? It is the active source; the guide returns to setup.' (SRC-RM-03)"
  keys -k Return
  pause 2
  sh_step "settings cleared through updateEntryInline" "grep -n updateEntryInline $(printf '%q' "$SCRATCH/logs/run.log") | tail -1"
  expect "playlist (none) epg (none); other keys kept"
  ipc_step "Sources stays open, service unconfigured" state
  expect "guide.mode sources, service.configured false, transient 'Removed <label> - no active source'"
  keys -k Escape
  shot sources-none-active
  ipc_step "first-run form behind" state
  expect "sourceEdit[firstRun] with 'Saved sources (1)' (SRC-FR-08, SRC-UI-06); D-LIVE-19 regression: no rows drawn under the form"
  keys -k Tab
  keys -k Tab
  keys -k Return
  ipc_step "link row opens Sources" state
  keys x
  keys -k Return
  pause 2
  ipc_step "last source removed" state
  expect "Sources closed, first-run form focused on Playlist, no 'Saved sources' link (SRC-RM-04)"
  sh_step "cache tree" "ls -la $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources") 2>/dev/null || echo '(empty)'"
  harness_stop
  note "queue variant: three quick removeSource calls in a row all complete (SRC-SVC-07); playing variant with --serve: mpv untouched (SRC-RM-09)"
}

scenario_SRC_H08() {
  banner SRC-H08; need verbs:switchSource,addSource apply:entry
  step "wipe" "$H" clean
  seed_fixtures
  step "10k fixture (deterministic)" python3 "$ROOT/scripts/gen-playlist.py" --channels 10000 --groups 400 --seed 1 --out "$SCRATCH/fixtures/gen-10k.m3u"
  local K10; K10=$(fnv1a32 http://127.0.0.1:8765/gen-10k.m3u)
  note "OMARCHY_IPTV_DEBUG=1 makes switchSource and the guide rebuild log 'omarchy-iptv switch <ms>' (Lane 2)"
  export OMARCHY_IPTV_DEBUG=1
  harness_start --open --serve --keep --timeout 0 --playlist "$A" || return 1
  pause 3
  ipc_step "add the 10k source (probe ~0.6 s)" addSource http://127.0.0.1:8765/gen-10k.m3u "" ""
  pause 6
  sh_step "5 switches each way" "for i in 1 2 3 4 5; do $(printf '%q' "$H") ipc switchSource $KA; sleep 2; $(printf '%q' "$H") ipc switchSource $K10; sleep 2; done"
  sh_step "timing lines" "grep -n 'omarchy-iptv switch' $(printf '%q' "$SCRATCH/logs/run.log")"
  expect "median under 150 ms to the 10k source (report median/max both ways) (SRC-PERF-01)"
  sh_step "harness RSS" "ps -o rss= -p \$(pgrep -f 'quickshell -p $SCRATCH/roo[t]')"
  harness_stop
  unset OMARCHY_IPTV_DEBUG
  note "repeat with scripts/gen-playlist.py --profile realistic --channels 1500 --groups 40 --seed 7 for the typical number; PERF-04 uses the QA.md PERF-02 method with the SRC-H16 50-record state"
}

scenario_SRC_H09() {
  banner SRC-H09; need verbs:sources apply:entry
  step "wipe" "$H" clean
  common_start "$A" || return 1
  pause 3
  ipc_step "open the guide on Sources" open '{}'
  keys -k Tab o
  ipc_step "CLI sets an unknown URL" set playlistUrl "$B"
  pause 1
  ipc_step "row appears without reopening" sources
  expect "B present with origin cli (state.json), label derived, active, 'not loaded yet' then 5 channels after the first fetch (SRC-CLI-01)"
  pause 3
  sh_step "exactly one fetch" "grep -c 'playlist:' $(printf '%q' "$SCRATCH/logs/run.log") || true"
  ipc_step "CLI sets a known URL" set playlistUrl "$A"
  pause 1
  sh_step "no new record" "jq -c '[.sources[] | {key, origin, label, labelCustom}]' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  expect "still two records; A active again (SRC-CLI-02)"
  ipc_step "CLI sets an EPG URL" set epgUrl "$EPGA"
  pause 2
  sh_step "epg helper ran into the active directory" "ls $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources/$KA"); jq -r '.sources[] | select(.key==\"$KA\") | .epgUrl' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  expect "epg-now.json / epg-status.json under sources/$KA, record epgUrl adopted (SRC-CLI-08)"
  local v
  for v in 'ftp://x' 'javascript:alert(1)' '/proc/self/environ'; do
    ipc_step "CLI invalid value $v" set playlistUrl "$v"
    pause 1
    ipc_step "synthesized error" state
    sh_step "no helper, no record" "pgrep -fc 'omarchy-iptv playlist' || true; jq '.sources|length' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  done
  expect "emptyKind error with the reason and host '', settingsInvalid set, 0 helper processes, 2 records (SRC-FR-11, SRC-CLI-03)"
  sh_step "3,000-character CLI value" "$(printf '%q' "$H") ipc set playlistUrl \"\$(python3 -c \"print('http://h.test/' + 'a'*3000, end='')\")\""
  pause 1
  ipc_step "too_long synthesized" state
  ipc_step "CLI clears the URL" set playlistUrl ""
  pause 1
  ipc_step "first-run, history untouched" state
  sh_step "records kept" "jq '.sources|length' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  expect "2 (SRC-CLI-04); guide shows the first-run form with no rows under it (D-LIVE-19)"
  ipc_step "IPC status shape" state
  expect "service.activeSource null, service.sources[] with key/label/host/active/channelCount/lastUsed; no '://' anywhere (SRC-CLI-06)"
  harness_stop
}

scenario_SRC_H10() {
  banner SRC-H10; need verbs:xtream,editMasked,sources apply:entry
  step "wipe" "$H" clean
  common_start "$A" || return 1
  pause 3
  ipc_step "Xtream login through the harness" xtream "$XS" "$XU" "$XP"
  expect "{ok:true, id:$KX} then the probe of the served get.php (SRC-XT-02)"
  pause 4
  ipc_step "row and EPG" sources
  expect "kind xtream, host 127.0.0.1, 4 channels 2 groups, hasEpg true, active (SRC-XT-04)"
  sh_step "EPG from xmltv.php" "jq -c .channels $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources/$KX/epg-now.json")"
  expect "qa.x.one / qa.x.two now 'Xtream Evergreen One/Two'"
  ipc_step "masked edit form values" editMasked "$KX"
  expect "http://127.0.0.1:8765/get.php?username=****&password=****&type=m3u_plus&output=ts and http://127.0.0.1:8765/xmltv.php?username=****&password=**** (SR4, SRC-XT-05)"
  ipc_step "open the guide" open '{}'
  keys -k Tab o c
  shot sources-xtream
  ipc_step "Xtream form" state
  expect "header 'Add Xtream login', Server focused, placeholder http://host:port, footer 'Enter save - Tab next field - Esc cancel' (SRC-XT-01, SRC-UI-09)"
  keys -k Tab
  keys -k Tab
  keys -k Tab
  keys -k Tab
  keys -k Tab
  ipc_step "focus order after 5 Tabs" state
  expect "Server -> Username -> Password -> Save -> Cancel -> Label (SRC-A11Y-03)"
  keys -k Escape
  keys c
  keys "$XS"
  keys -k Tab
  keys "$XU"
  keys -k Tab
  keys "$XP"
  shot sources-xtream-filled
  keys -k Return
  shot sources-xtream-fetching
  pause 3
  ipc_step "duplicate login" state
  expect "'Already in Sources as \"127.0.0.1\"' (same key; SRC-XT-09) - the first login already exists"
  keys -k Escape
  keys c
  ipc_step "reopened form is empty" state
  expect "no password value in the form state (SRC-XT-07)"
  keys -k Escape
  ipc_step "errors: empty server" xtream "" u p
  ipc_step "errors: ftp server" xtream ftp://h.test u p
  ipc_step "errors: server with a query" xtream 'http://h.test/get.php?username=a' u p
  ipc_step "errors: empty username" xtream http://h.test "" p
  ipc_step "errors: empty password" xtream http://h.test u ""
  expect "server_empty, server_scheme, server_path, user_empty, pass_empty with the UX 5.4 strings (SRC-XT-03)"
  ipc_step "failing server" xtream http://127.0.0.1:9 u p
  pause 2
  ipc_step "failure reason" state
  expect "'Connection refused from 127.0.0.1', nothing saved (SRC-XT-10)"
  harness_stop
  note "first-run variant: --playlist none, Tab Tab (Use Xtream login instead), Return, fill, Return -> search mode with '4 channels in 2 groups' (SRC-XT-08); needles per SRC-H13"
}

scenario_SRC_H11() {
  banner SRC-H11; need verbs:addSource,sources
  step "wipe" "$H" clean
  common_start "$A" || return 1
  pause 3
  ipc_step "duplicate: case-changed scheme/host" addSource "HTTP://127.0.0.1:8765/qa-src-a.m3u" "" ""
  ipc_step "duplicate: fragment" addSource "$A#x" "" ""
  ipc_step "duplicate: bare ?" addSource "$A?" "" ""
  expect "code duplicate with id $KA each time (SRC-DEC-04)"
  ipc_step "typed duplicate label" addSource "$B" "" "qa-src-a.m3u"
  expect "label_taken if A's derived label is 'qa-src-a.m3u'... served A derives '127.0.0.1' (or '127.0.0.1:8765', SRC-DEC-09): use that label to collide (SRC-LBL-05)"
  ipc_step "collide with the derived label" addSource "$B" "" "127.0.0.1"
  ipc_step "65-character label" addSource "$B" "" "$(printf 'a%.0s' $(seq 1 65))"
  expect "label_too_long (SRC-LBL-06)"
  ipc_step "second source on the same host: derived suffix" addSource "$B" "" ""
  pause 3
  ipc_step "labels" sources
  expect "'127.0.0.1 2' or '127.0.0.1 (2)' (SRC-DEC-11, SRC-LBL-02)"
  harness_stop
  step "wipe" "$H" clean
  seed_fixtures
  write_state_v2 "$COUNT"
  harness_start --open --serve --keep --timeout 0 --playlist "$A" || return 1
  pause 3
  ipc_step "50th source (the served A counts as one: check the count first)" state
  ipc_step "add up to the cap" addSource http://127.0.0.1:9/cap-50.m3u "" ""
  pause 2
  ipc_step "51st" addSource http://127.0.0.1:9/cap-51.m3u "" ""
  expect "too_many once 50 records exist; canAddSource false; the guide's copy per SRC-DEC-14 (SRC-ERR-05)"
  ipc_step "CLI 51st: LRU eviction" set playlistUrl http://127.0.0.1:9/cap-cli.m3u
  pause 2
  sh_step "eviction: still 50, the oldest lastUsed non-active gone, console names the key only" "jq '.sources|length' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json"); grep -n 'evict' $(printf '%q' "$SCRATCH/logs/run.log") || true"
  expect "50; the active source never evicted (SRC-CLI-05, SRC-SEC-10)"
  harness_stop
}

scenario_SRC_H12() {
  banner SRC-H12; need verbs:updateSource,sources,editMasked apply:entry
  step "wipe" "$H" clean
  common_start "$A" || return 1
  pause 3
  ipc_step "add B" addSource "$B" "" ""
  pause 3
  ipc_step "Xtream login (for the masked edit form)" xtream "$XS" "$XU" "$XP"
  pause 4
  sh_step "helper count before" "grep -c 'playlist:' $(printf '%q' "$SCRATCH/logs/run.log") || true"
  ipc_step "label-only edit" updateSource "$KB" '{"label":"Bravo"}'
  pause 1
  sh_step "immediate commit, labelCustom" "jq -c '.sources[] | select(.key==\"$KB\") | {label, labelCustom}' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json"); grep -c 'playlist:' $(printf '%q' "$SCRATCH/logs/run.log") || true"
  expect "label Bravo, labelCustom true, no new helper run (SRC-LBL-04)"
  ipc_step "EPG-only edit" updateSource "$KB" "{\"epgUrl\":\"$EPGA\"}"
  pause 2
  expect "committed at once; epg helper only if B is active"
  ipc_step "playlist URL edit (success)" updateSource "$KB" "{\"playlistUrl\":\"http://127.0.0.1:8765/qa-src-userinfo.m3u\"}"
  pause 3
  sh_step "record moved to the new key, old directory gone, label kept" "jq -c '[.sources[] | {key, label, addedAt}]' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json"); ls $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources")"
  expect "$KB absent, a new key present with label Bravo and the old addedAt (SRC-H12 success variant)"
  ipc_step "playlist URL edit (failure)" updateSource "$KX" '{"playlistUrl":"http://127.0.0.1:8765/missing.m3u"}'
  pause 3
  sh_step "old record and directory intact" "jq -c '[.sources[] | .key]' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json"); ls $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources")"
  expect "$KX still present with its directory; error shown for the edit"
  ipc_step "open the guide on the Xtream source" open '{}'
  keys -k Tab o
  keys -k End
  keys k k e
  shot sources-edit
  ipc_step "edit form" state
  expect "header 'Edit source', Label focused caret at the end, Playlist masked (username=****&password=****&type=m3u_plus&output=ts), EPG masked, no Xtream link (SRC-LBL-03, SRC-UI-08)"
  keys -k Tab
  keys -k Right
  ipc_step "arrows are no-ops while masked" state
  expect "footer '... Ctrl+R reveal ...' (SRC-KEY-04)"
  keys -M ctrl r -m ctrl
  shot sources-edit-revealed
  ipc_step "revealed" state
  expect "raw value in the field, eye-off U+F0209, footer 'Enter save - Tab next field - Ctrl+R hide - Esc cancel'"
  keys -k Tab
  keys -M shift -k Tab -m shift
  ipc_step "Tab away re-masks" state
  keys -k BackSpace
  ipc_step "Backspace on a masked field clears it" state
  keys -k Escape
  ipc_step "Esc cancels, nothing kept" state
  expect "mode sources; state.json unchanged (SRC-KEY-05)"
  keys e
  keys -k Return
  ipc_step "Enter with unchanged values" state
  expect "'Saved', no helper run (SRC-LBL-04)"
  harness_stop
}

scenario_SRC_H13() {
  banner SRC-H13; need verbs:sources,addSource,xtream helper:cache
  step "wipe" "$H" clean
  common_start "$A" || return 1
  pause 3
  ipc_step "userinfo source" addSource "$C" "" ""
  pause 3
  ipc_step "Xtream login" xtream "$XS" "$XU" "$XP"
  pause 4
  ipc_step "failed add with credentials in the URL" addSource "http://qa-user:qa-secret@127.0.0.1:9/x.m3u" "" ""
  pause 3
  ipc_step "open the guide" open '{}'
  keys -k Tab o
  shot sources-privacy-list
  local L="$SCRATCH/logs"
  sh_step "collect the sinks" "$(printf '%q' "$H") ipc sources > $(printf '%q' "$L/sources.json"); $(printf '%q' "$H") ipc state > $(printf '%q' "$L/state.json"); $(printf '%q' "$H") ipc widget > $(printf '%q' "$L/widget.json"); $(printf '%q' "$H") ipc tooltip > $(printf '%q' "$L/tooltip.txt"); python3 $(printf '%q' "$HELPER") state --state-dir $(printf '%q' "$SCRATCH/state/omarchy-iptv") show > $(printf '%q' "$L/state-show.json"); cp $(printf '%q' "$SCRATCH/logs/run.log") $(printf '%q' "$L/console.log"); touch $(printf '%q' "$L/notifications.log")"
  sh_step "needles in every sink" "grep -nE 'qa-user|qa-secret|pa ss|pa%20ss|username=user|password=|cu:cs|/live/' $(printf '%q' "$L")/sources.json $(printf '%q' "$L")/state.json $(printf '%q' "$L")/widget.json $(printf '%q' "$L")/tooltip.txt $(printf '%q' "$L")/state-show.json $(printf '%q' "$L")/console.log $(printf '%q' "$L")/notifications.log; echo \"exit \$? (1 = no hits = pass)\""
  expect "no hits (SRC-SEC-07, SRC-PRIV-01..08, SRC-XT-06)"
  sh_step "URL-shaped strings in the view and the helper output" "grep -c '://' $(printf '%q' "$L/sources.json") $(printf '%q' "$L/state-show.json") || true"
  expect "0 and 0 (SRC-LST-11, SRC-SEC-14)"
  sh_step "expected hits (by design, 0600)" "grep -c 'qa-secret' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json"); grep -lc 'cu:cs' $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources")/*/channels.json || true"
  sh_step "notifications from Sources operations" "wc -l < $(printf '%q' "$L/notifications.log")"
  expect "0 new lines from add/switch/edit/remove/Xtream/cancel (SRC-PRIV-04); the shim must be on PATH before the harness starts"
  harness_stop
  note "during a probe: ps -o args= -p \$(pgrep -f 'omarchy-iptv playlist') shows the URL after --url for the helper's lifetime (expected, record it: SRC-SEC-16)"
}

scenario_SRC_H14() {
  banner SRC-H14; need verbs:addSource,cancelProbe,switchSource,removeSource
  step "wipe" "$H" clean
  common_start "$A" || return 1
  pause 3
  ipc_step "slow probe (blackhole address, 20 s timeout)" addSource http://10.255.255.1/x.m3u "" ""
  local KS; KS=$(fnv1a32 http://10.255.255.1/x.m3u)
  ipc_step "second add while probing" addSource "$B" "" ""
  ipc_step "switch while probing" switchSource "$KA"
  ipc_step "remove the probing record" removeSource "$KS"
  expect "busy, busy, busy (SRC-ERR-06, SRC-RM-06, SRC-SEC-20)"
  ipc_step "cancel" cancelProbe
  pause 1
  sh_step "helper gone, no temp files, no leftover directory" "pgrep -fc 'omarchy-iptv playlist' || true; find $(printf '%q' "$SCRATCH/cache") -name '.tmp-*'; ls -la $(printf '%q' "$SCRATCH/cache/omarchy-iptv/sources/$KS") 2>/dev/null || echo 'no directory for $KS'"
  expect "0 processes, no .tmp-*, directory absent or empty (SRC-SEC-11, SRC-FR-07)"
  ipc_step "probing flag cleared" state
  ipc_step "from the guide: Esc while fetching" open '{}'
  keys -k Tab a
  keys "http://10.255.255.1/y.m3u"
  keys -k Return
  pause 1
  keys -k Escape
  ipc_step "form thawed with the typed value" state
  expect "guide.form values kept, probing false, no result line"
  keys -k Escape
  harness_stop
  note "deadline: the M1 trickle server (one M3U line every 2 s) as a source -> 'Timed out from 127.0.0.1' at ~60 s (SRC-ERR-09); not_ready: addSource right after start; failPersist (optional verb) -> sourcesPersistFailed with the fallback argv logged as keys only (SRC-ERR-07)"
}

scenario_SRC_H15() {
  banner SRC-H15; need helper:cache
  local Cd="$SCRATCH/cli-cache" K1=584a58e5 K2=733cf68c K3=25b70358
  step "fresh CLI cache tree" rm -rf "$Cd"
  step "three key directories plus non-key names" mkdir -p "$Cd/sources/$K1" "$Cd/sources/$K2" "$Cd/sources/$K3" "$Cd/sources/evil" "$Cd/sources/..x"
  sh_step "canary outside sources/ and a symlink inside" "echo canary > $(printf '%q' "$Cd/canary"); ln -sfn $(printf '%q' "$Cd/canary") $(printf '%q' "$Cd/sources/deadbeef")"
  step "populate k1" python3 "$HELPER" playlist --url "file://$FIX/qa-src-a.m3u" --cache-dir "$Cd/sources/$K1"
  step "populate k2 (+ EPG)" python3 "$HELPER" playlist --url "file://$FIX/qa-src-b.m3u" --cache-dir "$Cd/sources/$K2"
  step "k2 EPG" python3 "$HELPER" epg --url "$FIX/qa-src-a.xml" --cache-dir "$Cd/sources/$K2" --force
  step "populate k3" python3 "$HELPER" playlist --url "file://$FIX/qa-src-userinfo.m3u" --cache-dir "$Cd/sources/$K3"
  step "unknown file in k1" touch "$Cd/sources/$K1/foo.bin"
  local K
  for K in '../x' '../../x' 'abc' 'd5977d8a/..' 'd5977d8a/../../x' '%2e%2e' '' 'D5977D8A' 'd5977d8a-1000' 'd5977d8a-0' 'deadbeef'; do
    sh_step "cache remove with key '$K'" "python3 $(printf '%q' "$HELPER") cache remove --cache-dir $(printf '%q' "$Cd") --key $(printf '%q' "$K"); echo \"exit \$?\"; cat $(printf '%q' "$Cd/canary")"
  done
  expect "every call: {\"ok\":false,\"kind\":\"cache\",\"error\":{\"code\":\"bad_key\",\"message\":\"invalid cache key\"}} exit 1 (the symlink deadbeef: bad_key or skipped, never followed); 'canary' printed each time; no path echoed (SRC-SEC-08)"
  sh_step "remove k1 keeps the unknown file" "python3 $(printf '%q' "$HELPER") cache remove --cache-dir $(printf '%q' "$Cd") --key $K1; ls $(printf '%q' "$Cd/sources/$K1")"
  expect "kept: [\"foo.bin\"], directory left with foo.bin only (SRC-RM-07)"
  step "drop the unknown file" rm -f "$Cd/sources/$K1/foo.bin"
  sh_step "remove k1 again" "python3 $(printf '%q' "$HELPER") cache remove --cache-dir $(printf '%q' "$Cd") --key $K1; ls $(printf '%q' "$Cd/sources")"
  expect "directory gone"
  sh_step "remove a missing key" "python3 $(printf '%q' "$HELPER") cache remove --cache-dir $(printf '%q' "$Cd") --key $K1"
  expect "{\"ok\":true,...,\"removed\":[]}"
  step "legacy files for migrate" cp "$FIX/legacy-cache/channels.json" "$FIX/legacy-cache/playlist-status.json" "$Cd/"
  step "stray temp file" touch "$Cd/.tmp-abc"
  sh_step "migrate into k1" "python3 $(printf '%q' "$HELPER") cache migrate --cache-dir $(printf '%q' "$Cd") --key $K1; ls -la $(printf '%q' "$Cd") $(printf '%q' "$Cd/sources/$K1")"
  expect "moved: [channels.json, playlist-status.json], .tmp-abc gone, k1 0700 with 0600 files (SRC-MIG-09)"
  sh_step "migrate again (idempotent)" "python3 $(printf '%q' "$HELPER") cache migrate --cache-dir $(printf '%q' "$Cd") --key $K1"
  expect "moved: [], removed: []"
  step "legacy files again" cp "$FIX/legacy-cache/channels.json" "$FIX/legacy-cache/playlist-status.json" "$Cd/"
  sh_step "migrate with the target present: legacy deleted" "python3 $(printf '%q' "$HELPER") cache migrate --cache-dir $(printf '%q' "$Cd") --key $K1; ls $(printf '%q' "$Cd")"
  expect "removed: [channels.json, playlist-status.json]; no top-level json left"
  step "legacy files for the no-key variant" cp "$FIX/legacy-cache/channels.json" "$FIX/legacy-cache/playlist-status.json" "$Cd/"
  sh_step "migrate without --key" "python3 $(printf '%q' "$HELPER") cache migrate --cache-dir $(printf '%q' "$Cd"); ls $(printf '%q' "$Cd")"
  expect "legacy files deleted (SRC-MIG-05)"
  sh_step "age k2's EPG files" "touch -d '2 days ago' $(printf '%q' "$Cd/sources/$K2")/epg-now.json $(printf '%q' "$Cd/sources/$K2")/epg-status.json $(printf '%q' "$Cd/sources/$K2")/epg-window.txt"
  sh_step "prune: keep k1 and k2, k1 active" "python3 $(printf '%q' "$HELPER") cache prune --cache-dir $(printf '%q' "$Cd") --keep $K1 $K2 --active $K1 --epg-max-age 86400; ls $(printf '%q' "$Cd/sources") $(printf '%q' "$Cd/sources/$K2")"
  expect "removed: [$K3], agedEpg: [$K2] (its epg-* gone, channels.json kept), skipped: [..x, deadbeef, evil]; canary intact (SRC-HELP-07, SRC-SEC-23, SRC-PERF-07)"
  sh_step "prune with a traversal in --keep" "python3 $(printf '%q' "$HELPER") cache prune --cache-dir $(printf '%q' "$Cd") --keep ../x; echo \"exit \$?\""
  expect "bad_key exit 1"
  sh_step "one JSON line per call, no path" "python3 $(printf '%q' "$HELPER") cache remove --cache-dir $(printf '%q' "$Cd") --key $K2 | wc -l; cat $(printf '%q' "$Cd/canary")"
}

scenario_SRC_H16() {
  banner SRC-H16; need helper:cache
  step "wipe" "$H" clean
  seed_fixtures
  write_state_v2 "$COUNT"
  sh_step "size and mode before start" "stat -c '%a %s %n' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  harness_start --open --serve --keep --timeout 0 --playlist "$A" || return 1
  pause 3
  sh_step "after start (reconcile added the served A)" "stat -c '%a %s' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json"); jq '.sources|length' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json")"
  sh_step "prune argv carries at most 50 keys" "grep -n 'cache prune' $(printf '%q' "$SCRATCH/logs/run.log") | head -2"
  ipc_step "open Sources with $COUNT+1 rows" open '{}'
  keys -k Tab o
  sh_step "no helper run on opening Sources" "for i in 1 2 3 4 5 6; do pgrep -fc 'omarchy-iptv' || true; sleep 0.5; done"
  expect "0 every time (SRC-PERF-02)"
  keys -k Escape
  ipc_step "five saves: favorite" favorite
  ipc_step "label edit" updateSource "$KA" '{"label":"Alpha"}'
  ipc_step "add" addSource http://127.0.0.1:9/extra.m3u "" ""
  pause 2
  ipc_step "remove" removeSource "$(fnv1a32 http://127.0.0.1:9/extra.m3u)"
  pause 1
  ipc_step "switch" switchSource "$(fnv1a32 http://127.0.0.1:9/src000.m3u)"
  pause 2
  sh_step "mode and size after the saves" "stat -c '%a %s %n' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json"); ls -la $(printf '%q' "$SCRATCH/state/omarchy-iptv")"
  expect "600 after every save; size recorded: typical under ~35 KB, --worst about 215 KB (SRC-SEC-09, SRC-PERF-03)"
  sh_step "state show is URL-free" "python3 $(printf '%q' "$HELPER") state --state-dir $(printf '%q' "$SCRATCH/state/omarchy-iptv") show | grep -cE '\"url\"|\"epgUrl\"|://' || true"
  expect "0 (SRC-CLI-07, SRC-SEC-14)"
  harness_stop
  step "wipe" "$H" clean
  seed_fixtures
  write_tampered_state
  harness_start --open --serve --keep --timeout 0 --playlist "$A" || return 1
  pause 3
  sh_step "tampered records dropped, no crash" "jq -c '[.sources[] | .key]' $(printf '%q' "$SCRATCH/state/omarchy-iptv/state.json"); grep -n 'cache prune' $(printf '%q' "$SCRATCH/logs/run.log") | head -1; grep -ciE 'error|TypeError|undefined' $(printf '%q' "$SCRATCH/logs/run.log") || true"
  expect "valid keys only (584a58e5 and possibly deadbef2), prune argv with valid keys only, no QML errors (SRC-SEC-21, SRC-MODEL-07)"
  ipc_step "guide opened" state
  harness_stop
}

# ------------------------------------------------------------- subcommands

cmd_list() {
  local s id rest title needs
  printf '%-8s  %-70s  %s\n' ID TITLE NEEDS
  for s in "${SCENARIOS[@]}"; do
    id=${s%%|*}; rest=${s#*|}; title=${rest%%|*}; needs=${rest##*|}
    printf '%-8s  %-70s  %s\n' "$id" "$title" "$needs"
  done
  printf '\nscratch: %s\napply-able now: ' "$SCRATCH"
  local ok=() miss=()
  for s in "${SCENARIOS[@]}"; do
    id=${s%%|*}; needs=${s##*|}
    if ( APPLY=1; need $needs >/dev/null 2>&1 ); then ok+=("$id"); else miss+=("$id"); fi
  done
  echo "${ok[*]:-none}"; echo "waiting on Lane 2: ${miss[*]:-none}"
}

cmd_fixtures() {
  local out="$SCRATCH/fixture-check" f n
  printf 'fixtures: %s\n' "$FIX"
  sh_step "JSON fixtures parse" "python3 - $(printf '%q' "$FIX") <<'PY'
import json, os, sys
d = sys.argv[1]
for root, _, files in os.walk(d):
    for f in sorted(files):
        if f.endswith('.json'):
            p = os.path.join(root, f); doc = json.load(open(p, encoding='utf-8'))
            kind = 'array of %d' % len(doc) if isinstance(doc, list) else 'object keys ' + ','.join(sorted(doc)[:6])
            print('ok', os.path.relpath(p, d), kind)
u = json.load(open(os.path.join(d, 'qa-source-urls.json')))
ids = [c['id'] for c in u]; assert len(ids) == len(set(ids)), 'duplicate ids in qa-source-urls.json'
for c in u:
    if c.get('skip'): continue
    assert 'input' in c and 'ok' in c, c['id']
    if c['ok']: assert 'kind' in c, c['id']
    else: assert 'code' in c, c['id']
print('qa-source-urls.json: %d vectors, %d decision-flagged' % (len(u) - 1, sum(1 for c in u if c.get('decision'))))
x = json.load(open(os.path.join(d, 'xtream-expect.json')))['cases']
print('xtream-expect.json: %d cases (%d ok, %d error, %d decision)' % (len(x), sum(1 for c in x if c['expect'].get('ok')), sum(1 for c in x if not c['expect'].get('ok') and not c.get('decision')), sum(1 for c in x if c.get('decision'))))
l = json.load(open(os.path.join(d, 'qa-source-labels.json')))
print('qa-source-labels.json: %d derive, %d validate' % (len(l['derive']), len(l['validate'])))
s = json.load(open(os.path.join(d, 'state-v1.json'))); assert s['version'] == 1 and len(s['favorites']) == 3 and len(s['recents']) == 3
print('state-v1.json: version 1, 3 favorites, 3 recents')
st = json.load(open(os.path.join(d, 'legacy-cache', 'playlist-status.json'))); ch = json.load(open(os.path.join(d, 'legacy-cache', 'channels.json')))
assert st['fetchedAt'] == 1789244100 and ch['generatedAt'] == 1789244100 and st['channelCount'] == ch['count'] == 8 and st['groupCount'] == 3
print('legacy-cache: fetchedAt/generatedAt 1789244100, 8 channels, 3 groups, ids', [c['id'] for c in ch['channels']])
PY"
  sh_step "XMLTV fixtures parse" "python3 - $(printf '%q' "$FIX") <<'PY'
import sys, os, xml.etree.ElementTree as ET
d = sys.argv[1]
for p in ('qa-src-a.xml', 'xtream/xmltv.php'):
    t = ET.parse(os.path.join(d, p)).getroot()
    print('ok', p, len(t.findall('channel')), 'channels', len(t.findall('programme')), 'programmes')
PY"
  sh_step "ASCII gate (only nonascii/ may hit)" "LC_ALL=C grep -rlP '[^\\x00-\\x7F]' $(printf '%q' "$FIX") | grep -v /nonascii/ || echo 'ascii ok'"
  for f in qa-src-a.m3u qa-src-b.m3u qa-src-userinfo.m3u xtream/get.php; do
    n=$(basename "$f" .m3u)
    step "helper: $f" python3 "$HELPER" playlist --url "$FIX/$f" --cache-dir "$out/$n"
    sh_step "ids" "jq -c '[.channels[] | .id]' $(printf '%q' "$out/$n/channels.json")"
  done
  step "helper: EPG pair for A, pinned to T0" python3 "$HELPER" epg --url "$FIX/qa-src-a.xml" --cache-dir "$out/qa-src-a" --force --now "$T0"
  sh_step "now/next at T0" "jq -c .channels $(printf '%q' "$out/qa-src-a/epg-now.json")"
  expect "qa.shared now 'Shared Now' next 'Shared Next'; qa.a.news1/news2 evergreen; warning about 1 programme dropped"
  step "helper: EPG pair for A at the real clock" python3 "$HELPER" epg --url "$FIX/qa-src-a.xml" --cache-dir "$out/qa-src-a" --force
  sh_step "now at the real clock" "jq -c .channels $(printf '%q' "$out/qa-src-a/epg-now.json")"
  step "helper: Xtream xmltv.php" python3 "$HELPER" epg --url "$FIX/xtream/xmltv.php" --cache-dir "$out/get.php" --force
  sh_step "modes of the scratch caches" "find $(printf '%q' "$out") -exec stat -c '%a %n' {} + | sed 's|$out||'"
}

# B2. This printed MISSING lines and the caller exited 0 unconditionally, so
# the Sources capability gate reported a missing verb with a green status.
# It counts now, and `check-harness` exits 1 when anything is missing.
gate_missing=0
gate_ok()      { echo "  ok      $*"; }
gate_missing() { echo "  MISSING $*"; gate_missing=$((gate_missing + 1)); }

cmd_check_harness() {
  local v
  echo "harness: $ROOT/scripts/dev-harness/shell.qml"
  for v in addSource updateSource removeSource switchSource xtream sources activeCache cancelProbe editMasked signals failPersist; do
    if have_verb "$v"; then gate_ok "verb $v"; else gate_missing "verb $v"; fi
  done
  if fake_applies_entry; then gate_ok "fake updateEntryInline applies the entry"; else gate_missing "fake updateEntryInline must apply the entry to fakeShell.barConfig (docs/QA-SOURCES.md section 6)"; fi
  # D1's shape again: a bare grep for an option matches run.sh's header
  # comment as readily as its parser.
  if qa_case_arm "$H" '--source2'; then gate_ok "run.sh --source2"; else gate_missing "run.sh --source2 (ARCH 8.4)"; fi
  if have_cache_verb; then gate_ok "helper cache subcommand"; else gate_missing "helper 'cache' subcommand (Lane 2)"; fi
  # D3. `grep -qE 'validateSourceUrl|sourceView|xtreamUrls' Model.js` was
  # satisfied by a COMMENT mentioning any one of the three names. Load the
  # module and call for the functions instead - the gate's whole question is
  # whether the scenarios can use them. (Correction to the record: have_verb
  # at :148 anchors on `function <name>(` and was never comment-satisfiable;
  # it is left alone.)
  if node -e '
const M = require(process.argv[1]);
const want = ["validateSourceUrl", "sourceView", "xtreamUrls"];
const missing = want.filter(f => typeof M[f] !== "function");
if (missing.length) { console.error("not callable: " + missing.join(", ")); process.exit(1); }
' "$ROOT/Model.js" 2>/dev/null; then
    gate_ok "Model.js source functions (loaded and callable)"
  else
    gate_missing "Model.js validateSourceUrl / sourceView / xtreamUrls not callable from node (Lane 1)"
  fi
  # Service.qml cannot be invoked from here, so anchor on the definition the
  # way have_verb does rather than on a bare mention.
  if qa_defines_function "$ROOT/Service.qml" switchSource; then
    gate_ok "Service.qml switchSource()"
  else
    gate_missing "Service.qml switchSource() (Lane 2)"
  fi
  if [[ -f $ROOT/tests/fixtures/source-urls.json ]]; then gate_ok "tests/fixtures/source-urls.json (reconcile with qa-sources/qa-source-urls.json, SRC-MODEL-02)"; else gate_missing "tests/fixtures/source-urls.json (Lane 1)"; fi
  if command -v wtype >/dev/null; then gate_ok wtype; else gate_missing wtype; fi
  if command -v grim >/dev/null; then gate_ok grim; else gate_missing grim; fi
  if command -v wl-copy >/dev/null; then gate_ok wl-copy; else gate_missing wl-copy; fi
  printf '\n%d missing\n' "$gate_missing"
  (( gate_missing == 0 ))
}

# ----------------------------------------------------------------- main

CMD=${1:-}
[[ -n $CMD ]] || { usage; exit 2; }
shift
ARG=""
while (( $# > 0 )); do
  case $1 in
    --apply) APPLY=1 ;;
    --fresh) FRESH=1 ;;
    --worst) WORST=1 ;;
    --count) COUNT=${2:-49}; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) fail "unknown option: $1" ;;
    *) [[ -z $ARG ]] || fail "unexpected argument: $1"; ARG=$1 ;;
  esac
  shift
done

case $CMD in
  -h|--help|help) usage; exit 0 ;;
  key) [[ -n $ARG ]] || fail "key needs a URL or path"; fnv1a32 "$ARG"; exit 0 ;;
  list) refuse_real_dirs; cmd_list; exit 0 ;;
  # B2: this was `cmd_check_harness; exit 0`, so the gate printed MISSING
  # lines and exited green.
  check-harness) cmd_check_harness; exit $? ;;
esac

refuse_real_dirs
export OMARCHY_IPTV_HARNESS_DIR="$SCRATCH"
mkdir -p "$SCRATCH/logs"

case $CMD in
  fixtures) cmd_fixtures ;;
  seed) seed_fixtures; seed_v1 ;;
  stop) APPLY=1 harness_stop ;;
  print|run)
    [[ -n $ARG ]] || fail "$CMD needs a scenario id (see list)"
    [[ $CMD == print ]] && APPLY=0
    fn="scenario_${ARG//-/_}"
    declare -F "$fn" >/dev/null || fail "unknown scenario $ARG (see list)"
    if (( APPLY )) && [[ $CMD == run ]]; then
      trap 'harness_stop' EXIT
    fi
    "$fn"
    # B3: a scenario that gave up on its setup must not exit 0. Before this
    # the file had no non-zero exit path at all.
    (( setup_failed == 0 )) || { echo "qa-sources: $ARG ABANDONED (setup failed)" >&2; exit 1; }
    ;;
  *) usage; exit 2 ;;
esac
