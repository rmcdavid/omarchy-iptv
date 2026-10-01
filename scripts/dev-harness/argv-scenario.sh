#!/bin/bash
# scripts/dev-harness/argv-scenario.sh -- D-SINK-8: the credential-bearing
# playlist and EPG URLs must not appear on the helper's command line, and
# must travel in its environment instead. Observed on the real /proc, not
# reasoned about: a marketplace reviewer read them from /proc/<pid>/cmdline
# on the shipped v0.9.1 (omacom/omarchy-plugin-marketplace#8998).
#
#   S1  the sweep saw at least one helper `playlist` run (control: a scan
#       that saw nothing proves nothing)
#   S2  the sweep saw at least one helper `epg` run (control)
#   S3  NO helper command line carried the credential      <- the fix
#   S4  at least one helper ENVIRONMENT carried it          <- the route
#   S5  at the end, no process on the machine still carries it on a
#       command line (the one self-inflicted argv, `qs ipc addSource`, has
#       exited)
#   S6  the harness log carried neither the credential nor the path
#
# Against the shipped tree the proof is the other way round: run with
# --baseline dbcbd0f and S3 MUST fail (hits) and S4 MUST fail (no variable).
#
# HOW IT CATCHES A 200 ms PROCESS. The scenario runs its OWN http server on
# 127.0.0.1:8766 that sleeps before answering, so each helper fetch lives
# for seconds, and a python sweeper samples /proc every 50 ms for the whole
# window. Helper processes are identified by argv[1] ending in
# /bin/omarchy-iptv, which also excludes the two processes that carry the
# URL by the scenario's own doing: run.sh never sees it (the source is
# added over IPC after start), and the `qs ipc` client that adds it exits
# within milliseconds -- S5 checks that it did.
#
# Holds the display (starts the harness). Reaps everything it starts.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
PORT=8766
# Unique per run, so a process that happens to carry the same word for some
# other reason cannot be mistaken for ours.
NEEDLE="SYNTH3TIC$$$RANDOM"
PLAYLIST_URL="http://user:${NEEDLE}@127.0.0.1:${PORT}/p.m3u"
EPG_URL="http://user:${NEEDLE}@127.0.0.1:${PORT}/e.xml"
WORK=$(mktemp -d /tmp/omarchy-iptv-argv.XXXXXX)
SWEEP="$WORK/sweep.jsonl"
BASELINE=""; EXPORT_DIR=""
while (( $# )); do
  case $1 in
    --baseline) BASELINE=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac; shift
done
if [[ -n $BASELINE ]]; then
  EXPORT_DIR=$(mktemp -d /tmp/omarchy-iptv-argv-baseline.XXXXXX)
  git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR" || { echo "cannot export $BASELINE"; exit 2; }
  export OMARCHY_IPTV_PLUGIN_ROOT=$EXPORT_DIR
fi
# THE helper this harness spawns, by exact resolved path. The first draft
# matched any argv[1] ending in /bin/omarchy-iptv and read another lane's
# test processes -- running concurrently from a worktree, with the same
# example credential in THEIR environment -- as the route working on a tree
# that had no such route. A measurement that can see processes it did not
# start is rule 4b's concurrent-tree trap in a new form.
HELPER=$(readlink -f "${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}/bin/omarchy-iptv")
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL $1${2:+ -- $2}"; }
ipc() { "$RUN" ipc "$@" 2>/dev/null; }
sf() { python3 -c 'import json,sys
try: s=json.loads(sys.argv[2])["service"]; print(json.dumps(eval(sys.argv[1])))
except Exception: print("NOSTATE")' "$1" "$(ipc state)"; }
wait_sf() { local i; for ((i=0;i<$3;i++)); do [[ $(sf "$1") == "$2" ]] && return 0; sleep 0.25; done; return 1; }
SERVER_PID=""; SWEEP_PID=""
cleanup() {
  [[ -n $SWEEP_PID ]] && kill "$SWEEP_PID" 2>/dev/null
  "$RUN" reap >/dev/null 2>&1
  # The server's pid is read from the LISTENER, never from $!: this is the
  # project's own rule, learned when a live pass "killed" a fixture server
  # and found it still serving at the next segment.
  local lpid; lpid=$(ss -ltnp 2>/dev/null | awk -v p=":$PORT " '$0 ~ p {print $0}' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
  [[ -n $lpid ]] && kill "$lpid" 2>/dev/null
  [[ -n $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  rm -rf "$WORK"
}
trap cleanup EXIT
pgrep -x hyprlock >/dev/null && { echo "screen is locked"; exit 2; }
ss -ltn 2>/dev/null | grep -q ":$PORT " && { echo "port $PORT is already in use"; exit 2; }

# ---- the slow server: each request sleeps 2.5 s, then answers
cat >"$WORK/slow.py" <<'PY'
import http.server, sys, time
M3U = "#EXTM3U\n#EXTINF:-1 tvg-id=\"a\" group-title=\"News\",Alpha\nhttp://127.0.0.1:1/a\n#EXTINF:-1 tvg-id=\"b\" group-title=\"News\",Bravo\nhttp://127.0.0.1:1/b\n"
XML = "<?xml version=\"1.0\"?><tv><channel id=\"a\"><display-name>Alpha</display-name></channel><programme start=\"20260101000000 +0000\" stop=\"20991231000000 +0000\" channel=\"a\"><title>Now</title></programme></tv>"
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        time.sleep(2.5)
        body = (M3U if self.path.endswith(".m3u") else XML).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
python3 "$WORK/slow.py" "$PORT" >/dev/null 2>&1 &
for i in $(seq 1 20); do ss -ltn 2>/dev/null | grep -q ":$PORT " && break; sleep 0.1; done
ss -ltn 2>/dev/null | grep -q ":$PORT " || { echo "slow server did not start"; exit 2; }

# ---- the sweeper: every 50 ms, every helper process, cmdline and environ
cat >"$WORK/sweep.py" <<'PY'
import os, sys, time, json
# The needle arrives in THIS process's environment, not its argv: a sweeper
# that carried the credential on its own command line would be the leak it
# is looking for.
needle = os.environ["ARGV_NEEDLE"].encode(); deadline = time.monotonic() + float(sys.argv[1]); out = open(sys.argv[2], "a")
seen = {}
while time.monotonic() < deadline:
    for d in os.listdir("/proc"):
        if not d.isdigit(): continue
        try:
            with open("/proc/%s/cmdline" % d, "rb") as f: argv = f.read().split(b"\0")
        except OSError: continue
        if len(argv) < 3: continue
        try: helper_here = os.path.realpath(argv[1].decode("utf-8", "replace")) == os.environ["ARGV_HELPER"]
        except Exception: helper_here = False
        if not helper_here: continue
        key = (d, argv[2])
        if key in seen: continue
        try:
            with open("/proc/%s/environ" % d, "rb") as f: env = f.read()
        except OSError: env = b""
        carriers = sorted(set(e.split(b"=", 1)[0].decode("ascii", "replace") for e in env.split(b"\0") if needle in e))
        rec = {"pid": int(d), "verb": argv[2].decode("ascii", "replace"),
               "cmdline_has_needle": needle in b"\0".join(argv),
               "environ_has_needle": needle in env,
               "environ_carriers": carriers,
               "env_var_present": b"OMARCHY_IPTV_URL=" in env}
        seen[key] = rec; out.write(json.dumps(rec) + "\n"); out.flush()
    time.sleep(0.05)
PY
: >"$SWEEP"
ARGV_NEEDLE="$NEEDLE" ARGV_HELPER="$HELPER" python3 "$WORK/sweep.py" 40 "$SWEEP" &
SWEEP_PID=$!

# ---- the harness, unconfigured; the source arrives over IPC after start
"$RUN" reap >/dev/null 2>&1
"$RUN" --detach --open --timeout 0 --playlist none >/dev/null 2>&1 || { echo "harness did not start"; exit 2; }
# sourcesReady() wants BOTH: the state file loaded and the cache migrated.
# The first draft waited on stateLoaded alone, addSource answered not_ready,
# and the sweep saw no fetch at all -- which S1 and S2 then refused to
# call clean. That is what the two controls are for.
wait_sf 's["stateLoaded"] and s["cacheReady"]' true 80 || { fail "startup" "service never became ready: $(ipc state | head -c 300)"; exit 1; }
added=$(ipc addSource "$PLAYLIST_URL" "$EPG_URL" "sweep")
echo "addSource: $(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print("ok" if d.get("ok") else "REFUSED " + str(d.get("code")))' "$added" 2>/dev/null)"
key=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("key") or json.loads(sys.argv[1]).get("id") or "")' "$added" 2>/dev/null)
# The probe (a playlist fetch into the candidate dir) is running now. Wait
# for the add to land, then make sure the source is active so the real
# playlist fetch and the EPG fetch both run.
for i in $(seq 1 60); do [[ $(sf 's["sourceCount"]') == 1 ]] && break; sleep 0.25; done
[[ -n $key ]] && ipc switchSource "$key" >/dev/null 2>&1
ipc refresh >/dev/null 2>&1
for i in $(seq 1 60); do [[ $(sf 's["channels"]') == 2 ]] && break; sleep 0.25; done
# Give the EPG fetch its own 2.5 s window, then let the sweep drain.
sleep 6
kill "$SWEEP_PID" 2>/dev/null; wait "$SWEEP_PID" 2>/dev/null; SWEEP_PID=""

# ---- the verdicts, from the sweep log
summary=$(python3 - "$SWEEP" <<'PY'
import json, sys
recs = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
pl = [r for r in recs if r["verb"] == "playlist"]; ep = [r for r in recs if r["verb"] == "epg"]
print(json.dumps({
  "playlist_runs": len(pl), "epg_runs": len(ep),
  "cmdline_hits": sum(1 for r in recs if r["cmdline_has_needle"]),
  "environ_hits": sum(1 for r in recs if r["environ_has_needle"]),
  "intended_route": sum(1 for r in recs if "OMARCHY_IPTV_URL" in r.get("environ_carriers", [])),
  "carriers": sorted(set(c for r in recs for c in r.get("environ_carriers", []))),
  "env_var_runs": sum(1 for r in recs if r["env_var_present"]),
  "runs": [[r["verb"], r["cmdline_has_needle"], r["environ_has_needle"]] for r in recs]}))
PY
)
g() { python3 -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$summary" "$1"; }
echo "sweep: $summary"
[[ $(g playlist_runs) -ge 1 ]] && pass "S1 the sweep saw a helper playlist run ($(g playlist_runs))" || fail "S1" "no playlist run observed; the scan proves nothing"
[[ $(g epg_runs) -ge 1 ]] && pass "S2 the sweep saw a helper epg run ($(g epg_runs))" || fail "S2" "no epg run observed"
[[ $(g cmdline_hits) -eq 0 ]] && pass "S3 no helper command line carried the credential" || fail "S3" "$(g cmdline_hits) helper command line(s) carried it -- readable by every local user"
[[ $(g intended_route) -ge 1 ]] && pass "S4 the credential travelled as OMARCHY_IPTV_URL in the helper's environment ($(g intended_route) run(s))" || fail "S4" "OMARCHY_IPTV_URL never carried it; variables that did: $(g carriers)"
# S5: nothing on the whole machine still carries it on a command line.
left=$(ARGV_NEEDLE="$NEEDLE" python3 - <<'PY'
import os
n = os.environ["ARGV_NEEDLE"].encode(); me = os.getpid(); hits = []
for d in os.listdir("/proc"):
    if not d.isdigit() or int(d) == me: continue
    try:
        with open("/proc/%s/cmdline" % d, "rb") as f: c = f.read()
    except OSError: continue
    if n in c:
        hits.append(d + ":" + c.replace(n, b"<needle>").replace(b"\0", b" ").decode("utf-8", "replace")[:90])
print(len(hits)); [print("  " + h) for h in hits]
PY
)
[[ $(head -1 <<<"$left") -eq 0 ]] && pass "S5 no process on the machine carries it on a command line now" || fail "S5" "still on a command line:
$(tail -n +2 <<<"$left")"
log="$SCRATCH/harness.log"
if [[ -f $log ]]; then
  if grep -qa -- "$NEEDLE" "$log" || grep -qa -- "/p.m3u" "$log"; then fail "S6" "the harness log carries the credential or the path"; else pass "S6 the harness log carries neither the credential nor the path"; fi
else
  pass "S6 (no harness log written; nothing to leak into)"
fi
echo "argv-scenario: $PASS passed, $FAIL failed"
(( FAIL == 0 ))
