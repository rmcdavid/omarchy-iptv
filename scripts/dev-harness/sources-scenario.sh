#!/bin/bash
# scripts/dev-harness/sources-scenario.sh -- scripted verification of the
# Sources service (M2-01, Lane 2) through the harness IPC, no guide needed.
# Started by `run.sh scenario`. Opens the harness windows on the current
# Wayland session for ~60 s and reaps everything it starts.
#
# Scenarios (ARCHITECTURE-SOURCES.md 8.4, service side only):
#   H1  migration      v0.1 cache + v1 state.json -> sources/<key>/, state v2, favorites kept
#   H5  add failure    a dead URL keeps the active source; the record carries the reason
#   H2  add + probe    a fixture path is added, probed and becomes active
#   H6/H8 switch       two fetched sources; 5 switches each way with a 10k list, timing
#   D-LIVE-20          the plugin applies its own write; the host's echo lags or never
#                      comes, an external write still wins, the echo is idempotent
#   cancel             a probe against a silent server is cancelled; its dir is discarded
#   H9  CLI parity     `set playlistUrl` (omarchy bar set) reconciles into the history
#   H11 duplicate      the active URL again -> duplicate with the existing id
#   H7  remove active  settings cleared, only that directory deleted, first-run state
#
# Output: one PASS/FAIL line per check, the switch timings, and a summary.
# URLs are never printed (fixture paths under the scratch dir are local).
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
HELPER="$ROOT/bin/omarchy-iptv"
CACHE="$SCRATCH/cache/omarchy-iptv"
STATE="$SCRATCH/state/omarchy-iptv/state.json"
LOG="$SCRATCH/scenario.log"
FIX="$SCRATCH/fixtures"
CHANNELS_10K=${OMARCHY_IPTV_SCENARIO_CHANNELS:-10000}
HARNESS_PID=""
SILENT_PID=""
pass=0
fail=0
# `checks` counts ASSERTIONS; the bare `|| bad` guards move `fail` without
# being assertions. Only `checks` is comparable run to run, which is what the
# floor at the end of the file needs.
checks=0

# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

ok()   { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad()  { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
check() { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }
ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
# JSON helper: jq-less field access, `py '<expr over d>' <json>`; booleans
# print as JSON (true / false), everything else as Python prints it.
py()   { python3 -c 'import json,sys; d=json.loads(sys.argv[2]); v=eval(sys.argv[1]); print(json.dumps(v) if isinstance(v, bool) else v)' "$1" "$2" 2>/dev/null; }
svc()  { py "d['service']$1" "$(ipc state)"; }
key_of() { python3 -c 'import json,sys; s=[x for x in json.load(open(sys.argv[1]))["sources"] if x["label"]==sys.argv[2]]; print(s[0]["key"] if s else "")' "$STATE" "$1"; }

cleanup() {
  [[ -n $SILENT_PID ]] && kill "$SILENT_PID" 2>/dev/null
  if [[ -n $HARNESS_PID ]]; then kill -TERM "$HARNESS_PID" 2>/dev/null; wait "$HARNESS_PID" 2>/dev/null; fi
  return 0
}
trap cleanup EXIT

# Wait until `cmd` prints `want` (or up to `secs` seconds).
wait_for() {
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ "$("$@")" == "$want" ]] && return 0
    sleep 0.1
  done
  return 1
}
wait_log() {   # wait_log <regex> <secs>: the harness log gains a matching line
  local re=$1 secs=$2 i
  for ((i = 0; i < secs * 10; i++)); do
    grep -qE "$re" "$LOG" && return 0
    sleep 0.1
  done
  return 1
}
last_log() { grep -E "$1" "$LOG" | tail -1; }
# NOT IN THE AUDIT, found by sweeping for the shape rather than by reading the
# list: four `! grep -q ... "$LOG"` assertions below are the A4 shape without
# A4's labels. "No playlist helper ran", "no sourcesPersistFailed", "no
# omarchy bar fallback" are all TRUE of a log that is empty, missing or
# truncated. `wait_log 'service loaded'` at the top makes that unlikely rather
# than impossible, and "unlikely" is what this whole round is about. Every
# negative log assertion goes through here, and a log with none of our lines
# in it is vacuous, which `check` treats as a failure. Output is swallowed:
# a match may be a credentialed URL and the transcript is an artifact (S-08).
log_lacks() { qa_leak_scan 'service loaded' "$1" "$LOG" >/dev/null 2>&1; }
wait_gone() {  # wait_gone <path> <secs>: a queued `cache remove` has run
  local p=$1 secs=$2 i
  for ((i = 0; i < secs * 10; i++)); do
    [[ ! -e $p ]] && return 0
    sleep 0.1
  done
  return 1
}

echo "== setup (scratch $SCRATCH)"
"$RUN" clean >/dev/null
mkdir -p "$FIX" "$CACHE" "$(dirname "$STATE")"
sed "s|__LIVE__|http://127.0.0.1:9/dead/live.m3u8|g" "$HERE/fixtures/harness.m3u.in" >"$FIX/harness.m3u"
cp "$ROOT/tests/fixtures/basic.m3u" "$FIX/basic.m3u"
# C5. `-f` alone trusted whatever was on disk: $FIX survives `run.sh clean`,
# the generator's exit status was discarded, and gen-playlist.py wrote
# non-atomically, so an interrupted generation or a run with a different
# OMARCHY_IPTV_SCENARIO_CHANNELS left a stale or truncated playlist that every
# later run reused. Validate the CONTENT, not the existence, and regenerate on
# a mismatch.
fixture_channels() { qa_count '^#EXTINF' "$FIX/gen-10k.m3u"; }
if [[ "$(fixture_channels)" != "$CHANNELS_10K" ]]; then
  echo "   generating the $CHANNELS_10K channel fixture (had $(fixture_channels))"
  if ! python3 "$ROOT/scripts/gen-playlist.py" --channels "$CHANNELS_10K" --groups 400 --seed 1 --out "$FIX/gen-10k.m3u" >/dev/null; then
    bad "the 10k fixture could not be generated"; exit 1
  fi
fi
check "the 10k fixture really holds $CHANNELS_10K channels" '[[ "$(fixture_channels)" == "$CHANNELS_10K" ]]'
# H1 seed: the 0.1 layout (five files at the cache root) and a v1 state file.
python3 "$HELPER" playlist --url "$FIX/harness.m3u" --cache-dir "$CACHE" >/dev/null
printf '{"version":1,"favorites":["t:bbc1.uk","t:bbc2.uk"],"recents":[{"id":"t:bbc1.uk","name":"BBC One HD","at":1757700000}],"lastPlayed":null}\n' >"$STATE"
chmod 600 "$STATE"
: >"$LOG"

# A silent listener: accepts the TCP handshake and never answers, so a probe
# against it hangs until the helper's timeout (20 s) -- long enough to cancel.
python3 - >"$SCRATCH/silent.port" <<'PY' &
import socket, sys, time
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(4)
print(s.getsockname()[1]); sys.stdout.flush()
while True: time.sleep(3600)
PY
SILENT_PID=$!
# C6. A flat `sleep 0.3` then an unchecked read: if the background python had
# not flushed, SILENT_PORT was empty, the cancel-probe block built
# http://127.0.0.1:/slow.m3u, and its check went red for a reason nobody would
# read as a race.
qa_wait_nonempty "$SCRATCH/silent.port" 10 || { bad "the silent listener never reported a port"; exit 1; }
SILENT_PORT=$(cat "$SCRATCH/silent.port")
check "the silent listener reported a usable port" '[[ "$SILENT_PORT" =~ ^[0-9]+$ ]]'

echo "== start harness (OMARCHY_IPTV_DEBUG=1, --keep)"
# C7. The scenario's own waits sum well past 120 s (a 30 s wait_log, a 20 s,
# ten switch loops, several 15 s waits). When quickshell was killed mid-run
# every later svc returned empty, most checks went red - and the two privacy
# checks at the end PASSED, because a dead harness cannot leak. That is the
# concrete path by which the privacy sweep reported clean on nothing at all.
HARNESS_TIMEOUT=${OMARCHY_IPTV_SCENARIO_TIMEOUT:-600}
OMARCHY_IPTV_DEBUG=1 "$RUN" --keep --timeout "$HARNESS_TIMEOUT" --playlist "$FIX/harness.m3u" >>"$LOG" 2>&1 &
HARNESS_PID=$!
wait_log 'service loaded' 15 || { bad "harness did not start (see $LOG)"; exit 1; }
wait_for true 15 svc "['cacheReady']" || bad "cacheReady never became true"

echo "== H1 migration"
check "state.json is version 2 with cacheLayout 2" \
  '[[ "$(python3 -c "import json;d=json.load(open(\"$STATE\"));print(d[\"version\"],d[\"cacheLayout\"])")" == "2 2" ]]'
check "favorites and recents survived" \
  '[[ "$(python3 -c "import json;d=json.load(open(\"$STATE\"));print(len(d[\"favorites\"]),len(d[\"recents\"]))")" == "2 1" ]]'
check "one source record, origin migrated, label harness.m3u" \
  '[[ "$(python3 -c "import json;d=json.load(open(\"$STATE\"));s=d[\"sources\"];print(len(s),s[0][\"origin\"],s[0][\"label\"])")" == "1 migrated harness.m3u" ]]'
K1=$(key_of harness.m3u)
check "legacy files moved into sources/$K1 (dir 700, files 600)" \
  '[[ -f "$CACHE/sources/$K1/channels.json" && ! -e "$CACHE/channels.json" && "$(stat -c %a "$CACHE/sources/$K1")" == 700 && "$(stat -c %a "$CACHE/sources/$K1/channels.json")" == 600 ]]'
wait_for 20 10 svc "['channels']" || true
check "guide data loaded from the migrated cache (20 channels)" '[[ "$(svc "['\''channels'\'']")" == 20 ]]'
check "state.json mode 600" '[[ "$(stat -c %a "$STATE")" == 600 ]]'
check "activeCache() is the per-source dir" '[[ "$(ipc activeCache)" == "$CACHE/sources/$K1" ]]'
check "no playlist helper run for a fresh cache (freshness)" 'log_lacks "omarchy-iptv playlist:"'

echo "== H5 add failure keeps the active source and saves nothing (SR23)"
res=$(ipc addSource "http://127.0.0.1:9/x.m3u" "" "")
check "addSource returned ok with an id" '[[ "$(py "d['\''ok'\'']" "$res")" == true ]]'
KBAD=$(py "d['id']" "$res")
wait_log 'sourceProbeFinished .*"ok":false' 15 || bad "probe result did not arrive"
line=$(last_log 'sourceProbeFinished')
check "reason is 'Connection refused' from 127.0.0.1" '[[ "$line" == *Connection\ refused* && "$line" == *host*127.0.0.1* ]]'
check "active key unchanged, channels still 20" '[[ "$(svc "['\''activeSourceKey'\'']")" == "$K1" && "$(svc "['\''channels'\'']")" == 20 ]]'
wait_gone "$CACHE/sources/$KBAD" 5
check "nothing saved: no record, no directory, state.json untouched by the add" \
  '[[ "$(py "len([s for s in d if s['\''id'\'']=='\''$KBAD'\''])" "$(ipc sources)")" == 0 && ! -e "$CACHE/sources/$KBAD" && "$(python3 -c "import json;print(len(json.load(open(\"$STATE\"))[\"sources\"]))")" == 1 ]]'
check "signals() lists the failed probe, host only" 'ipc signals | grep -q "sourceProbeFinished" && ! ipc signals | grep -q "://"'
check "sources() carries no URL" '! ipc sources | grep -q "://"'
check "re-submitting is a fresh add with the same id (the form is the retry)" '[[ "$(py "(d['\''code'\''], d['\''id'\''])" "$(ipc addSource "http://127.0.0.1:9/x.m3u" "" "")")" == "('\''ok'\'', '\''$KBAD'\'')" ]]'
wait_for false 15 svc "['probing']" || true
check "removeSource of the never-recorded id -> unknown_source" '[[ "$(py "d['\''code'\'']" "$(ipc removeSource "$KBAD")")" == unknown_source ]]'

echo "== H2 add + probe + switch (10k fixture)"
res=$(ipc addSource "$FIX/gen-10k.m3u" "" "")
K2=$(py "d['id']" "$res")
check "addSource ok" '[[ "$(py "d['\''ok'\'']" "$res")" == true && -n "$K2" ]]'
wait_log "sourceSwitched .*\"id\":\"$K2\"" 30 || bad "sourceSwitched($K2) not observed"
check "probe ok with $CHANNELS_10K channels" '[[ "$(last_log sourceProbeFinished)" == *"\"ok\":true"*"\"channelCount\":$CHANNELS_10K"* ]]'
check "new source active, channels loaded" '[[ "$(svc "['\''activeSourceKey'\'']")" == "$K2" && "$(svc "['\''channels'\'']")" == "$CHANNELS_10K" ]]'
check "updateEntryInline logged with keys only" 'grep -q "updateEntryInline io.github.rmcdavid.iptv keys:" "$LOG" && ! grep "updateEntryInline" "$LOG" | grep -q "gen-10k"'
check "activeCache() switched" '[[ "$(ipc activeCache)" == "$CACHE/sources/$K2" ]]'

echo "== H6/H8 switch timing (5 each way, warm caches)"
for i in 1 2 3 4 5; do
  ipc switchSource "$K1" >/dev/null; wait_for false 10 svc "['switching']" || bad "switch to K1 #$i timed out"
  ipc switchSource "$K2" >/dev/null; wait_for false 10 svc "['switching']" || bad "switch to K2 #$i timed out"
done
mapfile -t times < <(grep -oE 'omarchy-iptv switch [0-9]+ ms \([^)]*\)' "$LOG" | tail -10)
printf '     %s\n' "${times[@]}"
stats=$(printf '%s\n' "${times[@]}" | grep -E "\($CHANNELS_10K channels" | grep -oE 'switch [0-9]+' | grep -oE '[0-9]+' | sort -n | python3 -c 'import sys; v=[int(x) for x in sys.stdin]; print("median %d ms max %d ms (n=%d)" % (v[len(v)//2], max(v), len(v)) if v else "no samples")')
echo "     10k-side switch: $stats"
median=$(echo "$stats" | grep -oE 'median [0-9]+' | grep -oE '[0-9]+')
check "median 10k switch under 150 ms ($stats)" '[[ -n "$median" && "$median" -lt 150 ]]'
check "no playlist helper run during warm switches" 'log_lacks "omarchy-iptv playlist:"'
check "active is K2 with $CHANNELS_10K channels after the last switch" '[[ "$(svc "['\''activeSourceKey'\'']")" == "$K2" && "$(svc "['\''channels'\'']")" == "$CHANNELS_10K" ]]'

echo "== D-LIVE-20 the plugin applies its own write, it never waits for the echo"
# The host publishes barConfig from its shellConfig change handler
# (shell.qml:66), which runs before the barConfig binding it reads
# (shell.qml:109), so what a plugin is handed is one write behind. An
# external write is flushed by the assignment after it; a plugin's OWN write
# is the last assignment there is, so its echo never arrives. A switch must
# therefore take effect from the plugin's own apply.
ipc switchSource "$K1" >/dev/null
sleep 0.5                       # a tenth of switchTimeoutMs: no backstop can have fired
he=$(ipc hostEntry)
check "the switch took effect at once, with no echo from the host" \
  '[[ "$(svc "['\''activeSourceKey'\'']")" == "$K1" && "$(svc "['\''channels'\'']")" == 20 && "$(svc "['\''switching'\'']")" == false ]]'
check "and while the host has published only the PREVIOUS bar (the defect shape)" \
  '[[ "$(py "d['\''stored'\'']" "$he")" == "$K1" && "$(py "d['\''published'\'']" "$he")" != "$(py "d['\''stored'\'']" "$he")" ]]'
check "sourceSwitched fired, no switch backstop warning" \
  '[[ "$(last_log sourceSwitched)" == *"\"id\":\"$K1\""* ]] && ! grep -q "did not observe a cache load" "$LOG"'
check "switching to the source that is already active is ok, not busy" \
  '[[ "$(py "d['\''ok'\'']" "$(ipc switchSource "$K1")")" == true ]]'
# The retry that used to answer `Could not save settings`: the host already
# stores the value (updateEntryInline takes its `!dirty` branch and returns
# false) while the plugin has not been handed it yet. False from a writable
# entry means "already saved", which is success.
ipc setStored playlistUrl "$FIX/harness.m3u" >/dev/null
sleep 0.3
res=$(ipc switchSource "$K2")
check "a switch the host already stores is not reported as a persist failure" \
  '[[ "$(py "d['\''ok'\'']" "$res")" == true && "$(py "d['\''code'\'']" "$res")" == ok ]]'
res=$(ipc switchSource "$K1")
check "switching back after that is still ok" '[[ "$(py "d['\''ok'\'']" "$res")" == true ]]'
check "no sourcesPersistFailed anywhere in the switch sequence" 'log_lacks "sourcesPersistFailed"'
wait_for 20 10 svc "['channels']" || bad "the guide did not settle on K1 after the retry sequence"

echo "== external writes still reconcile, and the echo of our own write is a no-op"
ipc set playlistUrl "$FIX/gen-10k.m3u" >/dev/null
wait_for "$K2" 10 svc "['activeSourceKey']" || bad "an external set playlistUrl did not reconcile"
check "omarchy bar set still wins over a spent own-write override" \
  '[[ "$(svc "['\''activeSourceKey'\'']")" == "$K2" && "$(svc "['\''channels'\'']")" == "$CHANNELS_10K" ]]'
ipc switchSource "$K1" >/dev/null
sleep 0.5
before=$(svc "['channels']")
ipc set playlistUrl "$FIX/harness.m3u" >/dev/null   # the host catching up with our own value
sleep 0.7
check "the host echoing our own value back changes nothing (idempotent)" \
  '[[ "$(svc "['\''activeSourceKey'\'']")" == "$K1" && "$(svc "['\''channels'\'']")" == "$before" && "$(svc "['\''switching'\'']")" == false ]]'
# leave K2 active again for the sections below
ipc switchSource "$K2" >/dev/null
wait_for "$K2" 10 svc "['activeSourceKey']" || bad "could not restore K2 as the active source"
wait_for "$CHANNELS_10K" 10 svc "['channels']" || bad "K2 did not reload after the D-LIVE-20 block"

echo "== cancel probe discards the temp dir"
res=$(ipc addSource "http://127.0.0.1:$SILENT_PORT/slow.m3u" "" "")
KSLOW=$(py "d['id']" "$res")
sleep 1
check "probing while the silent server hangs" '[[ "$(svc "['\''probing'\'']")" == true ]]'
res=$(ipc cancelProbe)
wait_log 'sourceProbeFinished .*"cancelled":true' 10 || bad "cancelled probe result not observed"
sleep 0.5
check "probing false, record dropped" '[[ "$(svc "['\''probing'\'']")" == false && "$(py "len([s for s in d if s['\''id'\'']=='\''$KSLOW'\''])" "$(ipc sources)")" == 0 ]]'
check "temp directory sources/$KSLOW gone" '[[ ! -e "$CACHE/sources/$KSLOW" ]]'
check "active still K2" '[[ "$(svc "['\''activeSourceKey'\'']")" == "$K2" ]]'

echo "== H9 CLI parity (set playlistUrl)"
ipc set playlistUrl "$FIX/basic.m3u" >/dev/null
sleep 0.5
K3=$(key_of basic.m3u)
check "new record origin cli, label basic.m3u, active" \
  '[[ -n "$K3" && "$(python3 -c "import json;d=json.load(open(\"$STATE\"));s=[x for x in d[\"sources\"] if x[\"key\"]==\"$K3\"][0];print(s[\"origin\"])")" == cli && "$(svc "['\''activeSourceKey'\'']")" == "$K3" ]]'
wait_for 3 20 svc "['channels']" || bad "first fetch of the CLI source did not load"
check "first fetch ran (no cache yet) and loaded 3 channels" '[[ "$(svc "['\''channels'\'']")" == 3 && -f "$CACHE/sources/$K3/channels.json" ]]'
check "H11 duplicate of the active URL -> duplicate with its id" '[[ "$(py "(d['\''code'\''], d['\''id'\''])" "$(ipc addSource "$FIX/basic.m3u" "" "")")" == "('\''duplicate'\'', '\''$K3'\'')" ]]'
check "invalid CLI value synthesizes an error and runs no helper" \
  'ipc set playlistUrl "ftp://h.test/x" >/dev/null; sleep 0.3; [[ "$(svc "['\''settingsInvalid'\'']['\''code'\'']")" == scheme && "$(svc "['\''configured'\'']")" == true && "$(svc "['\''channels'\'']")" == 0 ]] && ! grep -q "h.test" "$LOG"'
ipc set playlistUrl "$FIX/basic.m3u" >/dev/null; wait_for 3 10 svc "['channels']" || true

echo "== H12 edit: label and EPG commit at once, editMasked masks (SR4, SR22)"
res=$(ipc updateSource "$K2" '{"label":"Ten Thousand"}')
check "label edit ok, no probe" '[[ "$(py "d['\''ok'\'']" "$res")" == true && "$(svc "['\''probing'\'']")" == false ]]'
check "label stored with labelCustom" '[[ "$(python3 -c "import json;s=[x for x in json.load(open(\"$STATE\"))[\"sources\"] if x[\"key\"]==\"$K2\"][0];print(s[\"label\"],s[\"labelCustom\"])")" == "Ten Thousand True" ]]'
check "label_taken is case-insensitive (SR21)" '[[ "$(py "d['\''code'\'']" "$(ipc updateSource "$K1" '\''{"label":"ten thousand"}'\'')")" == label_taken ]]'
check "65 code points -> label_too_long (SR22)" '[[ "$(py "d['\''code'\'']" "$(ipc updateSource "$K1" "{\"label\":\"$(printf 'x%.0s' $(seq 65))\"}")")" == label_too_long ]]'
res=$(ipc updateSource "$K2" '{"epgUrl":"http://u:p@127.0.0.1:9/e.xml?token=abc&type=x"}')
check "EPG edit of an inactive source commits without a probe" '[[ "$(py "d['\''ok'\'']" "$res")" == true && "$(svc "['\''probing'\'']")" == false ]]'
masked=$(ipc editMasked "$K2")
check "editMasked: userinfo and query values masked, type kept, no raw URL field" \
  '[[ "$masked" == *"http://****@127.0.0.1:9/e.xml?token=****&type=x"* && "$masked" != *"u:p@"* && "$masked" != *"abc"* && "$masked" != *playlistUrl* ]]'
ipc updateSource "$K2" '{"epgUrl":""}' >/dev/null
check "empty label restores the derived one" '[[ "$(py "d['\''ok'\'']" "$(ipc updateSource "$K2" '\''{"label":""}'\'')")" == true && "$(python3 -c "import json;s=[x for x in json.load(open(\"$STATE\"))[\"sources\"] if x[\"key\"]==\"$K2\"][0];print(s[\"label\"],s[\"labelCustom\"])")" == "gen-10k.m3u False" ]]'

echo "== H7 remove active"
res=$(ipc removeSource "$K3")
check "removeSource ok" '[[ "$(py "d['\''ok'\'']" "$res")" == true ]]'
# D-LIVE-21: removing the active source must return the guide to the setup
# surface from the plugin's own write, not from an echo that never comes.
sleep 0.5
check "the guide left the loading state at once (D-LIVE-21)" \
  '[[ "$(svc "['\''configured'\'']")" == false && "$(svc "['\''channels'\'']")" == 0 ]]'
wait_for false 10 svc "['configured']" || bad "settings were not cleared"
sleep 0.5
check "first-run state: unconfigured, 0 channels, activeCache empty" '[[ "$(svc "['\''configured'\'']")" == false && "$(svc "['\''channels'\'']")" == 0 && "$(ipc activeCache)" == "" ]]'
check "sources/$K3 gone, K1 and K2 intact" '[[ ! -e "$CACHE/sources/$K3" && -f "$CACHE/sources/$K1/channels.json" && -f "$CACHE/sources/$K2/channels.json" ]]'
check "updateEntryInline logged 'playlist (none)'" 'grep -q "playlist (none)" "$LOG"'
check "history keeps the two other sources" '[[ "$(py "len(d)" "$(ipc sources)")" == 2 ]]'
res=$(ipc switchSource "$K1"); wait_log "sourceSwitched .*\"id\":\"$K1\"" 10 || bad "switch back after removal failed"
check "switch after removal restores the guide (20 channels)" '[[ "$(svc "['\''channels'\'']")" == 20 ]]'

echo "== SR25 persist failure (failPersist): signal only, no argv fallback"
ipc failPersist true >/dev/null
res=$(ipc switchSource "$K2")
check "switchSource with a refusing host -> persist_failed with the SR25 copy" \
  '[[ "$(py "d['\''code'\'']" "$res")" == persist_failed && "$(py "d['\''message'\'']" "$res")" == "Could not save settings"*"try omarchy bar set" ]]'
check "sourcesPersistFailed signalled, active unchanged, switching released" \
  'wait_log "sourcesPersistFailed" 3 && [[ "$(svc "['\''activeSourceKey'\'']")" == "$K1" && "$(svc "['\''switching'\'']")" == false ]]'
check "no omarchy bar argv fallback in the log" 'log_lacks "omarchy bar"'
ipc failPersist false >/dev/null
res=$(ipc switchSource "$K2"); wait_log "sourceSwitched .*\"id\":\"$K2\"" 10 || bad "switch after failPersist false did not complete"
check "switch works again once the host accepts" '[[ "$(svc "['\''activeSourceKey'\'']")" == "$K2" ]]'

echo "== privacy"
# C7's other half: assert the harness is still alive BEFORE the sweeps, so a
# scenario that died at minute two cannot sign off on privacy.
check "the harness is still alive at the privacy sweep" 'kill -0 "$HARNESS_PID" 2>/dev/null'
# A4. `! grep -E <labels> "$LOG" | grep -qE "://"` passed on an empty log and
# on a log whose only leak sat on a line carrying none of the three labels.
# The stated cause on record - pipefail making the pipeline status 1 - is
# wrong: the expression behaves identically with pipefail on and off, because
# the second grep already exits 1 on empty input. The real cause is the absent
# positive control. qa_leak_on_labelled returns 2 when there is nothing
# labelled to judge, and 2 is not a pass.
qa_leak_on_labelled 'sourceProbeFinished|sourceSwitched|updateEntryInline' "://|$FIX" "$LOG"
privacy_st=$?
checks=$((checks + 1))
case $privacy_st in
  0) ok "harness log carries no fixture path or URL from source operations" ;;
  1) bad "harness log LEAKS a fixture path or URL on a source-operation line" ;;
  *) bad "no sourceProbeFinished/sourceSwitched/updateEntryInline line in the log at all: the privacy sweep swept nothing" ;;
esac
# The residue A4 names and the plan's fix does not close: a leak on a line
# that carries none of the three labels. Separate check, so that a red here is
# diagnosable rather than conflated with the labelled sweep above.
check "no credentialed URL anywhere in the harness log" 'log_lacks "://[^ ]*[@?]"'
# :292 and :144 passed outright when the IPC was dead, because ipc() swallows
# stderr and an empty answer contains no "://". An empty answer is vacuous.
state_answer=$(ipc state)
qa_answer_lacks '://' "$state_answer"
state_st=$?
checks=$((checks + 1))
case $state_st in
  0) ok "IPC status carries no URL" ;;
  1) bad "IPC status carries a URL" ;;
  *) bad "the IPC did not answer at all: 'status carries no URL' is not evidence" ;;
esac

# The floor. A check that stops executing must turn the run red rather than
# shorten the summary - see D-PLY-9 and scripts/qa-lib-test.sh. Recount as
#   grep -c '^check ' <this file>  plus the standalone `checks=$((checks + 1))`
#   bumps, minus 1
# (the three-way `case` blocks bump the counter by hand, and the floor's own
# bump does not count). scripts/qa-lib-test.sh asserts that arithmetic, so a
# forgotten bump goes red on check.sh rather than here. Never lower it.
EXPECTED_CHECKS=65
ran=$checks
checks=$((checks + 1))
if [[ "$ran" == "$EXPECTED_CHECKS" ]]; then
  ok "the scenario ran every check it has ($ran)"
else
  bad "the scenario ran $ran checks, expected $EXPECTED_CHECKS (one stopped executing)"
fi

echo
echo "summary: $pass passed, $fail failed, $checks assertions executed (log: $LOG)"
(( fail == 0 ))
