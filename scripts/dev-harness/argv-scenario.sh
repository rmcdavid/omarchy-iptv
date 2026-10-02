#!/bin/bash
# scripts/dev-harness/argv-scenario.sh -- D-SINK-8: the credential-bearing
# playlist and EPG URLs must not appear on the helper's command line, and
# must travel in its environment instead. A marketplace reviewer reported,
# from the code, that any local user could read them from /proc/<pid>/cmdline
# on the shipped v0.9.1 (omacom/omarchy-plugin-marketplace#8998). That was a
# statement of capability citing line numbers; THIS script is the observation,
# on the real /proc, in both directions. An earlier version of this header
# said the reviewer "read them from /proc" -- a claim larger than its
# evidence, caught by review (F-M3-8's shape, in the proof's own preamble).
#
#   S1  the sweep saw at least one helper `playlist` run (control: a scan
#       that saw nothing proves nothing)
#   S2  the sweep saw at least one helper `epg` run (control)
#   S3  NO helper command line carried the credential      <- the fix
#   S4  every helper ENVIRONMENT ended REFUSED to this same-uid reader, and
#       the fetch succeeded anyway -- so the URL arrived by the only route
#       left, and that route is readable by root alone (D-SINK-9)
#   S4b the window between exec and the shield -- the interpreter starting
#       and compiling the helper, since the shield sits above every import
#       but sys -- is MEASURED, and bounded against an in-run start-up
#       control taken under the same load (it is CPU-bound and runs 2-5x
#       longer on a busy machine; an absolute bound failed there)
#   S5  at the end, no process on the machine still carries it on a
#       command line (the one self-inflicted argv, `qs ipc addSource`, has
#       exited)
#   S6  the harness log carried neither the credential nor the path
#
# Against the shipped tree the proof is the other way round: run with
# --baseline dbcbd0f and S3 MUST fail (hits) and S4 MUST fail (every environ
# readable, and none of them carrying the variable).
#
# HOW IT CATCHES A 200 ms PROCESS. The scenario runs its OWN http server on
# 127.0.0.1:8766 that sleeps before answering, so each helper fetch lives
# for seconds, and a python sweeper samples /proc every 50 ms for the whole
# window. Helper processes are identified by argv[1] resolving to THIS
# harness's bin/omarchy-iptv by exact path (HELPER below; a suffix match was
# the first draft, and it read another lane's processes), which also excludes
# the two processes that carry the URL by the scenario's own doing: run.sh
# never sees it (the source is added over IPC after start), and the `qs ipc`
# client that adds it exits within milliseconds -- S5 checks that it did.
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
# Every helper is re-sampled on every tick, not recorded once: the first
# draft recorded each pid the first time it was seen, which for a process
# that shields itself before its imports is ALWAYS the start-up window
# before the shield, and reported the shield as absent. The record for
# a pid is rewritten each tick with first-seen / first-refused times, so the
# window between them is MEASURED and the final state is what is asserted.
seen = {}
t0 = time.monotonic()
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
        now = round((time.monotonic() - t0) * 1000)
        refused = False
        try:
            with open("/proc/%s/environ" % d, "rb") as f: env = f.read()
        except PermissionError: env = b""; refused = True
        except OSError:
            # Gone between the cmdline read and this one: its last real
            # sample stands. Rewriting it as "not refused" was the first
            # draft's bug in the other direction (last sample wins, with no
            # distinction between readable and vanished).
            continue
        carriers = sorted(set(e.split(b"=", 1)[0].decode("ascii", "replace") for e in env.split(b"\0") if needle in e))
        prev = seen.get(key)
        rec = {"pid": int(d), "verb": argv[2].decode("ascii", "replace"),
               "cmdline_has_needle": (prev or {}).get("cmdline_has_needle", False) or needle in b"\0".join(argv),
               "environ_has_needle": (prev or {}).get("environ_has_needle", False) or needle in env,
               "environ_refused": refused,
               "environ_carriers": sorted(set((prev or {}).get("environ_carriers", []) + carriers)),
               "env_var_present": (prev or {}).get("env_var_present", False) or b"OMARCHY_IPTV_URL=" in env,
               "first_seen_ms": (prev or {}).get("first_seen_ms", now),
               "first_refused_ms": (prev or {}).get("first_refused_ms") if prev and prev.get("first_refused_ms") is not None else (now if refused else None),
               "samples": (prev or {}).get("samples", 0) + 1}
        seen[key] = rec
    out.seek(0); out.truncate()
    for r in seen.values(): out.write(json.dumps(r) + "\n")
    out.flush()
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
  # Refusals are counted over the FETCH runs, which is what S4 compares them
  # to. The first draft counted every helper verb -- all of them are shielded
  # now, at module level -- and reported "8 of 4".
  "environ_refused": sum(1 for r in pl + ep if r.get("environ_refused")),
  "all_helper_runs": len(recs),
  "all_refused": sum(1 for r in recs if r.get("environ_refused")),
  "fetch_runs": len(pl) + len(ep),
  "readable_before_shield_ms": [ (r["first_refused_ms"] - r["first_seen_ms"]) if r.get("first_refused_ms") is not None else None for r in pl + ep ],
  "max_window_ms": max([ (r["first_refused_ms"] - r["first_seen_ms"]) for r in pl + ep if r.get("first_refused_ms") is not None ] or [-1]),
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
# S4 is two facts that only mean something together: the environment of
# every fetch was refused to us (a same-uid reader with no capabilities),
# AND the fetch produced channels. Refusal alone could be a helper that
# never ran; success alone could be a URL that arrived on argv (S3 rules
# that out). Together they say the URL went by a route root alone can read.
channels=$(sf 's["channels"]')
if [[ $(g environ_refused) -eq $(g fetch_runs) && $(g fetch_runs) -ge 2 && $channels == 2 ]]; then
  pass "S4 every fetch's environment ended REFUSED to this uid ($(g environ_refused)/$(g fetch_runs); every helper verb: $(g all_refused)/$(g all_helper_runs)) and the fetch still landed 2 channels"
else
  fail "S4" "environ refused at the end on $(g environ_refused) of $(g fetch_runs) fetch runs (readable ones carried: $(g carriers)), channels=$channels, windows ms=$(g readable_before_shield_ms)"
fi
# S4b: the pre-shield window is CPU-bound -- the interpreter starting, the
# file compiling, the imports above the shield -- so it scales with load:
# 117-127 ms idle, 264-634 ms with the cores oversubscribed twice over
# (measured by the final review). An absolute bound fails on a busy box for
# a reason unrelated to the fix, which is the wrong failure and invites
# raising the number. So the bound is RELATIVE: three timed runs of the
# helper's own `--version`, which pays the identical start-up under the
# identical load, and the window may be at most three times their median
# plus one sampling tick. The absolute number is reported, never enforced.
ctrl_ms=$(for i in 1 2 3; do s=$(date +%s%N); python3 "$HELPER" --version >/dev/null 2>&1; e=$(date +%s%N); echo $(( (e - s) / 1000000 )); done | sort -n | sed -n 2p)
bound=$(( ctrl_ms * 3 + 60 ))
if [[ $(g max_window_ms) -ge 0 && $(g max_window_ms) -le $bound ]]; then
  pass "S4b pre-shield window $(g max_window_ms) ms (per fetch: $(g readable_before_shield_ms), 50 ms sampling) against an in-run start-up control of $ctrl_ms ms: bound $bound"
else
  fail "S4b" "pre-shield window $(g max_window_ms) ms against control $ctrl_ms ms (bound $bound); windows: $(g readable_before_shield_ms)"
fi
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
# The log is named the way run.sh names it (harness$INSTANCE.log), and a
# --detach start always creates it, so a missing file is a wrong path and
# a FAIL -- never "nothing to leak into", which is what the first draft said.
log="$SCRATCH/harness${OMARCHY_IPTV_HARNESS_INSTANCE:-}.log"
if [[ -f $log ]]; then
  if grep -qa -- "$NEEDLE" "$log" || grep -qa -- "/p.m3u" "$log"; then fail "S6" "the harness log carries the credential or the path"; else pass "S6 the harness log carries neither the credential nor the path"; fi
else
  fail "S6" "no harness log at $log; the scan has nothing to read and cannot pass"
fi
echo "argv-scenario: $PASS passed, $FAIL failed"
(( FAIL == 0 ))
