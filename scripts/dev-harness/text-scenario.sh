#!/bin/bash
# scripts/dev-harness/text-scenario.sh -- D-TEXT-1: a channel name must not
# be a network request. The wall caption (Guide.qml, the Text under the tile
# plate that shows `tile.name`) rendered provider text under Qt's AutoText
# default, so `<img src="http://...">` in a channel name made the shell GET
# it. A marketplace maintainer found that from the code
# (omacom/omarchy-plugin-marketplace#9628); the measurement behind it ran on a
# replica of the caption's shape (QA-RESULTS "Marketplace finding at
# 2d3cee3"). THIS script is the observation on the shipping Guide.qml, live,
# through the harness, against a server that logs every request it gets.
#
#   T1  the playlist loaded: the service holds exactly the channels this
#       run generated (control: a guide over an empty list fetches nothing)
#   T2  the guide opened in LIST view, resultList holds its delegates, the
#       HIDDEN channelWall already holds a page of captions (the mechanism
#       behind "every guide open"), and the cursor row's name still carries
#       the probe tag (control: a name the parser had stripped would make
#       every zero below vacuous)
#   T3  after the list open the server logged ZERO requests carrying this
#       run's token                                            <- the fix
#   T4  the WALL was reached through the real Ctrl+G key, channelWall
#       holds a page of captions (control), and the server STILL logged zero
#   T5  the server is alive and logging: a request the scenario makes
#       itself IS in the log, so T3/T4's zero is not a dead server
#   T6  the harness log carries no "Error transferring" line and no probe
#       path (the first measurement saw that line once, beside an https img
#       to a non-routable host; it never appears on a 404 alone, so this is
#       a log check, not a discriminator between trees)
#
# Against the shipped tree the proof is the other way round: run with
# --baseline 2d3cee3 and T3 and T4 MUST fail with request counts above zero.
# The summary line names the baseline so a red run there reads as evidence,
# not as a broken script. Whether T3 is red (the captions fetch on the LIST
# open, because channelWall has `visible: root.wallView` and a live model)
# or only T4 is red (they fetch only once the wall shows) is reported from
# the counts, not assumed: the first is what QA-RESULTS claims from a
# replica, and this is the run that settles it on Guide.qml.
#
# HOW IT OBSERVES. The scenario runs its OWN http server on 127.0.0.1:8767
# (8765 is run.sh --serve, 8766 is argv-scenario) that answers 404 and logs
# method, path and User-Agent per request. The playlist is generated per run:
# 40 probe channels whose names are `<img src="http://127.0.0.1:8767/
# <token>-<n>.png">Probe <n>`, where the token is unique to this run so a
# request logged by anything else cannot be mistaken for ours, plus one plain
# control channel. 40 fills a wall page plus the cacheBuffer row on this
# screen. Realised-delegate counts come from the harness's `realised <view>`
# verb, which counts the delegates a named channel view holds RIGHT NOW
# without re-opening the guide (-1 when the guide is not loaded or the name
# is not a channel view). The first draft read them from `openMs`, which
# re-opens the guide (so the baseline's log carried every caption twice, 49
# requests for 25 names) and reports 1 for the hidden wall (what an empty
# view looks like), so its control said nothing about the captions a hidden
# wall had laid out. Now the control is the count itself: on the list open,
# resultList holds its page of rows AND the hidden channelWall already holds
# its page of captions -- the mechanism behind "every guide open" -- and T2
# asserts both. Against 2d3cee3 on this screen: resultList 16, hidden wall
# 25, and the server logged 25 requests for 25 names, one per hidden
# caption; after the wall (21 shown) 26 for 26.
#
# Holds the display (starts the harness, sends one real chord). Reaps
# everything it starts and proves it at the end. The server's pid is read
# from ss ONCE, when our server is confirmed up, and remembered; cleanup
# kills that pid and never one looked up at cleanup time, so an exit before
# our server exists (the port taken, the server failing to start) sends no
# signal to whatever else holds the port.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
PORT=8767
PROBES=40
EXPECT_CHANNELS=$((PROBES + 1))
# Unique per run; letters and digits only, so it is safe inside a URL path
# and inside an m3u name without quoting.
TOKEN="t$$$RANDOM"
WORK=$(mktemp -d /tmp/omarchy-iptv-text.XXXXXX)
PLAYLIST="$WORK/probes.m3u"
REQLOG="$WORK/requests.log"
BASELINE=""; EXPORT_DIR=""
while (( $# )); do
  case $1 in
    --baseline) BASELINE=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac; shift
done
if [[ -n $BASELINE ]]; then
  EXPORT_DIR=$(mktemp -d /tmp/omarchy-iptv-text-baseline.XXXXXX)
  git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR" || { echo "cannot export $BASELINE"; exit 2; }
  export OMARCHY_IPTV_PLUGIN_ROOT=$EXPORT_DIR
fi
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL $1${2:+ -- $2}"; }
ipc() { "$RUN" ipc "$@" 2>/dev/null; }
gf() { python3 -c 'import json,sys
try: g=json.loads(sys.argv[2])["guide"]; print(json.dumps(eval(sys.argv[1])))
except Exception: print("NOSTATE")' "$1" "$(ipc state)"; }
sf() { python3 -c 'import json,sys
try: s=json.loads(sys.argv[2])["service"]; print(json.dumps(eval(sys.argv[1])))
except Exception: print("NOSTATE")' "$1" "$(ipc state)"; }
wait_sf() { local i; for ((i=0;i<$3;i++)); do [[ $(sf "$1") == "$2" ]] && return 0; sleep 0.25; done; return 1; }
# The listener's pid, from ss -- never from $!. The project's own rule,
# learned when a live pass "killed" a fixture server and found it still
# serving at the next segment.
listener_pid() { ss -ltnp 2>/dev/null | awk -v p=":$PORT " '$0 ~ p {print $0}' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }
# Requests the PROBE captions made: the per-run token followed by a number
# and .png. The control request T5 makes carries the token too, under a
# different suffix, so the two never count as each other.
probe_hits() { grep -c -- "/${TOKEN}-[0-9]*\.png" "$REQLOG" 2>/dev/null || true; }
probe_paths() { grep -o -- "GET /${TOKEN}-[0-9]*\.png UA=[^ ]*" "$REQLOG" 2>/dev/null | head -5 | tr '\n' ';'; }
# Distinct probe names fetched, beside the raw count: the two agree when
# each caption fetched once (25 for 25 on 2d3cee3) and part when delegates
# are recreated, which a re-open would do and this scenario does not.
probe_distinct() { grep -o -- "/${TOKEN}-[0-9]*\.png" "$REQLOG" 2>/dev/null | sort -u | wc -l; }
# Set only once OUR server is confirmed listening; empty until then, so a
# cleanup on an earlier exit path (the port already taken, the server not
# starting) has no pid to signal and leaves the foreign listener alone.
SERVER_PID=""
# The pid bash handed us for the server we started, kept apart from
# SERVER_PID: it is OUR child by construction (no wrapper in between), so
# reaping it by this number is not the forbidden "listener from $!" -- it
# is never used to find the LISTENER, only to stop a child of ours that
# started too late to be confirmed. Every kill below checks the pid is
# still a child of this shell first, so a reused pid is never signalled.
OWN_CHILD=""
ours() { [[ -n $1 && $(ps -o ppid= -p "$1" 2>/dev/null | tr -d ' ') == "$$" ]]; }
cleanup() {
  "$RUN" reap >/dev/null 2>&1
  ours "$SERVER_PID" && kill "$SERVER_PID" 2>/dev/null
  ours "$OWN_CHILD" && kill "$OWN_CHILD" 2>/dev/null
  [[ -n $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  rm -rf "$WORK"
}
trap cleanup EXIT
pgrep -x hyprlock >/dev/null && { echo "screen is locked"; exit 2; }
ss -ltn 2>/dev/null | grep -q ":$PORT " && { echo "port $PORT is already in use"; exit 2; }

# ---- the logging server: every request line to REQLOG, every answer 404
cat >"$WORK/probe_server.py" <<'PY'
import http.server, socketserver, sys
PORT = int(sys.argv[1]); LOG = sys.argv[2]
class H(http.server.BaseHTTPRequestHandler):
    def _log(self):
        with open(LOG, "a") as f:
            f.write("%s %s UA=%r\n" % (self.command, self.path, self.headers.get("User-Agent")))
        self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers()
    do_GET = do_HEAD = do_POST = _log
    def log_message(self, *a): pass
class S(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
with S(("127.0.0.1", PORT), H) as s:
    s.serve_forever()
PY
: >"$REQLOG"
python3 "$WORK/probe_server.py" "$PORT" "$REQLOG" >/dev/null 2>&1 &
OWN_CHILD=$!
for i in $(seq 1 30); do ss -ltn 2>/dev/null | grep -q ":$PORT " && break; sleep 0.1; done
# On this exit the trap reaps OWN_CHILD if it is still ours: a server that
# binds after the 3 s window must not be left holding 8767 for the next run
# to refuse as foreign.
ss -ltn 2>/dev/null | grep -q ":$PORT " || { echo "probe server did not start"; exit 2; }
# The listener is ours only if this shell is its parent; a server that lost
# the port to someone who bound it between the check above and the bind
# would leave a foreign pid on the port, and that one is not remembered.
lpid=$(listener_pid)
[[ -n $lpid && $(ps -o ppid= -p "$lpid" 2>/dev/null | tr -d ' ') == "$$" ]] || { echo "port $PORT is held by pid ${lpid:-?}, not a child of this run; leaving it alone"; exit 2; }
SERVER_PID=$lpid

# ---- the playlist: 40 probe names plus one plain control
{
  echo "#EXTM3U"
  for ((n = 1; n <= PROBES; n++)); do
    printf '#EXTINF:-1 tvg-id="p%d" group-title="Probe",<img src="http://127.0.0.1:%d/%s-%d.png">Probe %d\n' "$n" "$PORT" "$TOKEN" "$n" "$n"
    printf 'http://127.0.0.1:9/dead/%d\n' "$n"
  done
  echo '#EXTINF:-1 tvg-id="plain" group-title="Probe",Plain Control'
  echo 'http://127.0.0.1:9/dead/plain'
} >"$PLAYLIST"

# ---- the harness, guide closed; the opens below are the measurement
"$RUN" reap >/dev/null 2>&1
"$RUN" --detach --timeout 0 --playlist "$PLAYLIST" >/dev/null 2>&1 || { echo "harness did not start"; exit 2; }
wait_sf 's["stateLoaded"] and s["cacheReady"]' true 80 || { fail "startup" "service never became ready: $(ipc state | head -c 300)"; exit 1; }
wait_sf 's["channels"]' "$EXPECT_CHANNELS" 80
channels=$(sf 's["channels"]')
[[ $channels == "$EXPECT_CHANNELS" ]] && pass "T1 the playlist loaded: $channels channels ($PROBES probes + 1 control)" || fail "T1" "service holds $channels channels, generated $EXPECT_CHANNELS"
# Requests before any open are reported, never asserted: they would say the
# captions exist (and fetch) with the guide closed, which no document claims.
before_open=$(probe_hits)
echo "info: probe requests before the first open: $before_open"

# ---- LIST view: open, settle, read the view through the instrument
ipc open '{}' >/dev/null; sleep 1.5
opened=$(gf 'g["opened"]'); wall=$(gf 'g["wallView"]'); rows=$(gf 'g["rows"]'); cname=$(gf 'g["cursorName"]')
realised=$(ipc realised resultList); hidden_wall=$(ipc realised channelWall)
if [[ $opened == true && $wall == false && ${realised:--1} -gt 0 && ${hidden_wall:--1} -gt 1 && $rows == "$EXPECT_CHANNELS" && $cname == *"<img src="* ]]; then
  pass "T2 list view open: $rows rows, resultList holds $realised delegates, the HIDDEN channelWall already holds $hidden_wall captions, cursor name carries the probe tag"
else
  fail "T2" "opened=$opened wallView=$wall rows=$rows resultList=$realised hiddenWall=$hidden_wall cursorName=$(python3 -c 'import sys; print(sys.argv[1][:60])' "$cname")"
fi
sleep 0.5
list_hits=$(probe_hits)
[[ $list_hits -eq 0 ]] && pass "T3 zero probe requests after the list open" || fail "T3" "$list_hits probe request(s) for $(probe_distinct) distinct names after the list open: $(probe_paths)"

# ---- WALL view: the real chord, then the same instrument
pgrep -x hyprlock >/dev/null && { fail "T4" "screen locked before the keystroke; refusing to type"; echo "text-scenario: $PASS passed, $FAIL failed"; exit 1; }
via="key"
"$RUN" key -M ctrl g -m ctrl >/dev/null 2>&1; sleep 0.6
if [[ $(gf 'g["wallView"]') != true ]]; then
  # One retry for the first-keystroke race run.sh primes against; a second
  # miss falls back to the harness setter so the SINK is still measured,
  # and the line below says the key path was not what reached it.
  "$RUN" key -M ctrl g -m ctrl >/dev/null 2>&1; sleep 0.6
  if [[ $(gf 'g["wallView"]') != true ]]; then via="ipc-fallback"; ipc wall true >/dev/null; sleep 0.3; fi
fi
sleep 1.5
wall=$(gf 'g["wallView"]'); cols=$(gf 'g["wallColumns"]')
# The count as the wall stands, no re-open: a shown wall holds a page of
# captions, and that number is what T4's zero is measured against. The
# distinct-name count on a red run (25 on the list open and 26 after the
# wall on 2d3cee3, this screen) is the same quantity seen from the server.
realised=$(ipc realised channelWall)
sleep 0.5
wall_hits=$(probe_hits)
if [[ $via == key && $wall == true && ${cols:-0} -gt 0 && ${realised:--1} -gt 1 && $wall_hits -eq 0 ]]; then
  pass "T4 wall via the real Ctrl+G: wallView true, $cols columns, channelWall holds $realised captions, still zero probe requests"
else
  fail "T4" "wall via $via, wallView=$wall columns=$cols channelWall=$realised, $wall_hits probe request(s) for $(probe_distinct) distinct names after the wall: $(probe_paths)"
fi
ipc close >/dev/null; sleep 0.3

# ---- T5: the server is alive and logging. The scenario's own request.
curl -s -o /dev/null -A "text-scenario" "http://127.0.0.1:$PORT/${TOKEN}-control" 2>/dev/null
ctrl_hits=$(grep -c -- "GET /${TOKEN}-control UA='text-scenario'" "$REQLOG" 2>/dev/null || true)
[[ $ctrl_hits -eq 1 ]] && pass "T5 the server logged the scenario's own control request (so a zero above is a real zero)" || fail "T5" "control request logged $ctrl_hits times; the server was not observing"

# ---- T6: the harness log, named the way run.sh names it
log="$SCRATCH/harness${OMARCHY_IPTV_HARNESS_INSTANCE:-}.log"
if [[ -f $log ]]; then
  if grep -qa "Error transferring" "$log" || grep -qa -- "$TOKEN" "$log"; then
    fail "T6" "the harness log carries a transfer error or a probe path: $(grep -a "Error transferring\|$TOKEN" "$log" | head -2 | cut -c1-160 | tr '\n' ';')"
  else
    pass "T6 the harness log carries no transfer error and no probe path"
  fi
else
  fail "T6" "no harness log at $log; nothing to read and nothing to pass"
fi

# ---- teardown, proven: the shell is gone and the port is free
"$RUN" reap >/dev/null 2>&1
ours "$SERVER_PID" && kill "$SERVER_PID" 2>/dev/null
for i in $(seq 1 30); do ss -ltn 2>/dev/null | grep -q ":$PORT " || break; sleep 0.1; done
qs_left=$([[ -f "$SCRATCH/qs${OMARCHY_IPTV_HARNESS_INSTANCE:-}.pid" ]] && echo "pidfile present" || echo "no pidfile")
port_left=$(ss -ltn 2>/dev/null | grep -q ":$PORT " && echo "port $PORT STILL LISTENING" || echo "port $PORT free")
echo "teardown: $qs_left, $port_left"
echo "requests: before-open=$before_open after-list=$list_hits after-wall=$wall_hits distinct-names=$(probe_distinct) of $PROBES (probe paths only; UA of the first: $(grep -o -- "/${TOKEN}-[0-9]*\.png UA=.*" "$REQLOG" 2>/dev/null | head -1 | sed 's/.*UA=//'))"
if [[ -n $BASELINE ]]; then
  echo "baseline $BASELINE: T3 and T4 are expected RED here; T3 red means the captions fetched on the LIST open, T4-only red means they fetched only once the wall showed"
fi
echo "text-scenario: $PASS passed, $FAIL failed"
(( FAIL == 0 ))
