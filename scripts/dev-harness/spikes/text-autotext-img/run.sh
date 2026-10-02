#!/bin/bash
# scripts/dev-harness/spikes/text-autotext-img/run.sh -- the measurement that
# D-TEXT-1 rests on, kept so "measured" means "re-runnable":
#
#   scripts/dev-harness/spikes/text-autotext-img/run.sh
#
# Does laying out a Text whose string carries `<img src="http://...">` make
# the QML process GET that URL, and which textFormat stops it? One element
# per case in sweep.spec.qml, each with its own probe path; probe_server.py
# logs every request it receives -- request line and the FULL header set --
# and answers 404; qmltestrunner runs the scene offscreen (no display needed,
# nothing shipped is loaded). The table is read from the server's log and
# the runner's console and compared with the result recorded below, so a Qt
# that changes this is visible rather than quietly assumed. The comparator
# checks the `fetched` column, the set of header NAMES each fetch carried,
# that no request arrived for a path no case owns, and that all 11 report
# lines came back. contentWidth and truncated are printed, never compared:
# the PlainText and entity cases render the URL as glyphs, so their width
# moves with the digits of the port -- up to about 7 px, one glyph's width,
# between runs -- and the other columns are context for a reader, not
# assertions.
#
# On Qt 6.11.2 (qt6-declarative 6.11.2-1), QT_QPA_PLATFORM=offscreen,
# 2026-10-02, three runs, it printed:
#
#   case  shape                    declared    fetched   UA           contentWidth  truncated
#   a     tag first                AutoText    yes       Mozilla/5.0  72.3          false
#   b     tag last                 AutoText    yes       Mozilla/5.0  72.3          false
#   c     elided narrow (caption)  AutoText    yes       Mozilla/5.0  56.2          true
#   d     invisible                AutoText    yes       Mozilla/5.0  72.3          false
#   e     PlainText control        PlainText   no        -            356.6         false
#   f     StyledText               StyledText  yes       Mozilla/5.0  72.3          false
#   g     RichText                 RichText    yes       Mozilla/5.0  79.9          false
#   h     <b> only                 AutoText    (no img)  -            64.6          false
#   i     entity-escaped           AutoText    no        -            369.6         false
#   twin  hPlain                   PlainText   -         -            127.3         false
#   twin  iPlain                   PlainText   -         -            435.6         false
#   stderr: 0 "Error transferring" line(s)
#
# What every fetch carried, the whole header set, identical across the six
# fetching cases and across runs (the Host value is the port of the run):
#
#   Host: 127.0.0.1:<port>
#   Connection: Keep-Alive
#   Accept-Encoding: zstd, br, gzip, deflate
#   Accept-Language: en-US,*
#   User-Agent: Mozilla/5.0
#
# Five headers, in that order, no cookie, no referer, no authorization,
# nothing from the environment but the locale behind Accept-Language (and
# the compressors this Qt was built with behind Accept-Encoding). This
# measurement replaced the CHANGELOG's first sentence about the request
# ("... nothing else of yours", withdrawn 2026-10-02 because nothing had
# logged the other headers); the CHANGELOG now names the five. The comparator
# holds the NAMES and their order; the values are printed per case so a
# change in one is seen, not failed. A server patched to drop one header
# from its log turns the comparator red (six "carried headers" entries on
# the one DIFFERS line, exit 1), which is how the log-to-comparator join
# was proven on 2026-10-02.
#
# What the table says: every format but PlainText fetches, visible or not,
# elided or not, with `Mozilla/5.0` as the client; AutoText resolves to
# StyledText on these strings (identical metrics). h's tag was CONSUMED (64.6
# against the twin's 127.3) and i's entities were DECODED (369.6 against
# 435.6): escaping is a rendering change, not a closure. PlainText is the
# only stop.
#
# The console line. The finding's table in QA-RESULTS first said that
# RichText "logs the FULL URL to stderr on failure"; it was corrected there
# on 2026-10-02 from this sweep, which does NOT see it: zero lines in three
# runs, and zero again with a later relayout of the element or of a sibling.
# The line the first measurement saw ("QML Text: Error transferring <url> -
# server replied: Not Found") appeared only while the scene also held an
# AutoText `<img>` toward https://10.255.255.1 -- a request that never
# completes -- and vanished when that one element was removed (bisected
# 2026-10-02, each of the first sweep's other extra cases kept alone: no
# line). So the sink exists, under a condition this spike does not
# reproduce on purpose: that case sends a packet off the loopback
# interface, which a re-runnable spike should not do on its own. The count
# is printed, never asserted.
#
# Server pid from ss, never $!, read ONCE at the moment our server is
# confirmed up and remembered; cleanup kills that pid and nothing it looks
# up later, so an exit before our server exists (the port taken, the server
# failing to start) kills nobody. Every wait bounded; nothing left listening.
# Not part of the gate.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
RUNNER=/usr/lib/qt6/bin/qmltestrunner
[[ -x $RUNNER ]] || { echo "no $RUNNER"; exit 2; }
WORK=$(mktemp -d /tmp/omarchy-iptv-text-spike.XXXXXX)
LOG="$WORK/requests.log"; : >"$LOG"
QMLOUT="$WORK/qml.out"
listener_pid() { ss -ltnp 2>/dev/null | awk -v p=":$PORT " '$0 ~ p {print $0}' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }
# Set only once OUR server is confirmed listening; empty until then, so a
# cleanup on an earlier exit path has no pid to send a signal to.
SERVER_PID=""
# OWN_CHILD is the pid bash handed us for the server we started -- our
# child by construction, used only to stop a late starter of ours, never to
# find the listener. Every kill checks the pid is still a child of this
# shell, so a reused pid is never signalled.
OWN_CHILD=""
ours() { [[ -n $1 && $(ps -o ppid= -p "$1" 2>/dev/null | tr -d ' ') == "$$" ]]; }
cleanup() {
  ours "$SERVER_PID" && kill "$SERVER_PID" 2>/dev/null
  ours "$OWN_CHILD" && kill "$OWN_CHILD" 2>/dev/null
  rm -rf "$WORK"
}
trap cleanup EXIT
# A free loopback port, found by binding 0 and letting go; the server binds
# it a moment later. The listener check below only says that SOMETHING
# listens there, so the pid it names is checked to be a child of this shell
# before it is remembered: two spikes started in the same instant and handed
# the same number would otherwise have the loser record the winner's server
# and read its log.
PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
python3 "$HERE/probe_server.py" "$PORT" "$LOG" >/dev/null 2>&1 &
OWN_CHILD=$!
for i in $(seq 1 50); do ss -ltn 2>/dev/null | grep -q ":$PORT " && break; sleep 0.1; done
ss -ltn 2>/dev/null | grep -q ":$PORT " || { echo "probe server did not start on $PORT"; exit 2; }
lpid=$(listener_pid)
[[ -n $lpid && $(ps -o ppid= -p "$lpid" 2>/dev/null | tr -d ' ') == "$$" ]] || { echo "port $PORT is held by pid ${lpid:-?}, not a child of this run; leaving it alone"; exit 2; }
SERVER_PID=$lpid
echo "probe server: 127.0.0.1:$PORT pid $SERVER_PID (from ss, parent $$)"
sed "s#__PORT__#$PORT#g" "$HERE/sweep.spec.qml" >"$WORK/sweep.run.spec.qml"
QT_QPA_PLATFORM=offscreen timeout 30 "$RUNNER" -input "$WORK/sweep.run.spec.qml" >"$QMLOUT" 2>&1
echo "qmltestrunner exit=$? ($(grep -c . "$QMLOUT") lines)"
# Let a request that was in flight at the runner's exit reach the log.
sleep 0.5
python3 - "$LOG" "$QMLOUT" "$PORT" <<'PY'
import re, sys
log, out, port = open(sys.argv[1]).read(), open(sys.argv[2]).read(), sys.argv[3]
shapes = {"a": "tag first", "b": "tag last", "c": "elided narrow (caption)", "d": "invisible",
          "e": "PlainText control", "f": "StyledText", "g": "RichText", "h": "<b> only",
          "i": "entity-escaped"}
# What 2026-10-02 measured on Qt 6.11.2; None means the case carries no image.
expected = {"a": True, "b": True, "c": True, "d": True, "e": False, "f": True, "g": True, "h": None, "i": False}
# The header NAMES every fetch carried on 2026-10-02, in the order sent.
expected_headers = ["Host", "Connection", "Accept-Encoding", "Accept-Language", "User-Agent"]
rpt = {}
for m in re.finditer(r"RPT (\w+) declared=(\w+) contentWidth=([\d.]+) truncated=(\w+)", out):
    rpt[m.group(1)] = (m.group(2), m.group(3), m.group(4))
# One block per request: "METHOD /path", then "  Name: value" per header.
hits = {}
for block in re.split(r"\n\s*\n", log.strip()):
    lines = block.splitlines()
    if not lines:
        continue
    m = re.match(r"^(\w+) /(\w+)\.png$", lines[0])
    if not m:
        hits.setdefault("?" + lines[0], []).append((lines[0], []))
        continue
    headers = []
    for h in lines[1:]:
        hm = re.match(r"^\s+([^:]+): (.*)$", h)
        if hm:
            headers.append((hm.group(1), hm.group(2)))
    hits.setdefault(m.group(2), []).append((m.group(1), headers))
def header(hs, name):
    for n, v in hs:
        if n.lower() == name.lower():
            return v
    return "-"
print("%-5s %-24s %-11s %-8s %-12s %-13s %s" % ("case", "shape", "declared", "fetched", "UA", "contentWidth", "truncated"))
diff = []
for c in "abcdefghi":
    d = rpt.get(c, ("?", "?", "?"))
    got = hits.get(c, [])
    fetched = "(no img)" if expected[c] is None else ("yes" if got else "no")
    ua = header(got[0][1], "User-Agent") if got else "-"
    print("%-5s %-24s %-11s %-8s %-12s %-13s %s" % (c, shapes[c], d[0], fetched, ua, d[1], d[2]))
    if expected[c] is not None and bool(got) != expected[c]:
        diff.append("%s fetched=%s expected=%s" % (c, bool(got), expected[c]))
    if expected[c] is None and got:
        diff.append("%s carried no image and still fetched" % c)
for c in ("hPlain", "iPlain"):
    d = rpt.get(c, ("?", "?", "?"))
    print("twin  %-24s %-11s %-8s %-12s %-13s %s" % (c, d[0], "-", "-", d[1], d[2]))
# Every header each fetch carried, name and value, so "nothing else of
# yours" is read from the log and not assumed from the User-Agent alone.
print("headers carried, per fetched case (every header the request had):")
for c in "abcdefghi":
    for i, (method, hs) in enumerate(hits.get(c, [])):
        tag = c if len(hits[c]) == 1 else "%s#%d" % (c, i + 1)
        print("  %-4s %s %s" % (tag, method, "; ".join("%s: %s" % (n, v) for n, v in hs)))
        names = [n for n, _ in hs]
        if names != expected_headers:
            diff.append("%s carried headers %s, measured %s" % (tag, names, expected_headers))
errs = [l for l in out.splitlines() if "Error transferring" in l]
print("stderr: %d \"Error transferring\" line(s)%s" % (len(errs), ", carrying the URL" if any(port in l for l in errs) else ""))
extra = sorted(set(hits) - set("abcdefghi"))
if extra:
    diff.append("requests for paths no case owns: %s" % extra)
if len(rpt) < 11:
    diff.append("only %d of 11 report lines; the runner did not finish" % len(rpt))
if diff:
    print("result DIFFERS from the 2026-10-02 measurement: " + "; ".join(diff))
    sys.exit(1)
print("result matches the 2026-10-02 measurement (Qt 6.11.2): fetched column and header names")
PY
status=$?
kill "$SERVER_PID" 2>/dev/null
for i in $(seq 1 30); do ss -ltn 2>/dev/null | grep -q ":$PORT " || break; sleep 0.1; done
ss -ltn 2>/dev/null | grep -q ":$PORT " && echo "WARNING: port $PORT still listening" || echo "probe server stopped, port $PORT free"
exit $status
