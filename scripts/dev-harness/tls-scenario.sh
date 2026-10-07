#!/bin/bash
# scripts/dev-harness/tls-scenario.sh -- D-SINK-13: the stream's TLS PEER is a
# sink, and the real player path must refuse an unverified one.
#
# The marketplace maintainer raised it against the shipped 0.12.1
# (omacom/omarchy-plugin-marketplace#10323): mpv is launched with no TLS
# verification while the helper supplies provider headers and HTTPS stream
# URLs, so an on-path attacker can impersonate the provider, replace the media
# and collect the credentials carried in the URL and the headers. The lead
# measured it and then measured four ways the obvious fix could be undone; the
# measurements live in docs/QA-RESULTS.md and are CITED here, never restated as
# this script's own. What this script adds is the observation the lead's rig
# could not make: the same question asked through the SHIPPING path -- the
# service, the helper, `player start`, the IPC loadfile -- rather than through a
# hand-written mpv command line.
#
# THE SINK IS WATCHED FROM THE ATTACKER'S SIDE. A server that logs a GET of
# the stream is an attacker who got the bytes, the URL's credentials and the
# provider headers; a server that logs no GET got nothing. Every verdict below
# is that hit log, read per channel path, with the service's own verdict beside
# it. This is the D-TEXT-1 shape (scripts/dev-harness/text-scenario.sh), which
# is the model this file was written from.
#
# THE FOUR LAYERS OF THE FIX, and which check observes which:
#   1  `--tls-verify=yes` in the base argv            S1, S5 (two occurrences)
#   2  the same token re-asserted LAST, after the      S3 (profile bypass),
#      user's mpvArgs -- the layer that guarantees it   S5 (last token)
#   3  `--tls-verify` RESERVED, both spellings, so a    S5 (absent from argv,
#      direct attempt is refused LOUDLY                 named in the log)
#   4  `--tls-ca-file` left UNRESERVED: the targeted    S2 (through a profile),
#      escape for a private CA                          S4 (on argv)
# `--profile` is deliberately NOT reserved, because layer 2 makes it harmless,
# and S3 is the check that says so at the sink rather than in prose.
#
#   G1..G8  THE RIG, and it runs in both modes. A fresh CA signs a server
#           certificate for 127.0.0.1; a second, self-signed certificate is
#           what the on-path attacker presents. `openssl verify` and four
#           `curl`s establish that the rig DISCRIMINATES before anything is
#           asked of the plugin: the CA-signed cert verifies against our CA and
#           NOT against the system store (so a stream that plays in S2/S4 can
#           only be playing because the CA was named), the attacker's cert is
#           refused by a verifying client, and both servers really do serve the
#           media (so a zero in S1/S3 is a refusal and not a dead server).
#   S1      THE PLAIN CASE. The attacker's self-signed certificate, no user
#           mpvArgs, the real player path: the stream is REFUSED and the
#           attacker's log holds no GET of it.
#   S2      THE CONTROL FOR S3, and it runs BEFORE it for the reason the lead's
#           addendum gives -- a positive control after the fact proves nothing
#           about the row above it. The `good` profile names the CA and nothing
#           else, against the CA-signed server. On a verifying tree the only way
#           that stream can play is if mpv read this run's config, applied the
#           profile and honoured the CA, so a green S2 is what makes S3's zero
#           mean something; it is also layer 4 surviving a profile.
#   S3      THE PROFILE BYPASS, and the reason this scenario matters more than
#           a unit test. User mpvArgs `--profile=evil` and an mpv config whose
#           `evil` profile says `tls-verify=no`. The lead measured that a later
#           command-line token beats an earlier one, so without the trailing
#           re-assertion this case PLAYS; with it the stream is still refused.
#   S4      THE CA ESCAPE as the README will document it: `--tls-ca-file=<path>`
#           in mpvArgs, against the CA-signed server, PLAYS. If it does not,
#           the ruling that leaves `--tls-ca-file` unreserved is wrong and this
#           scenario saying so is the most useful thing in it -- but read G3
#           first before saying it. G3 is the same certificate verified by
#           `curl --cacert`, so the chain, the name and the IP:127.0.0.1 SAN are
#           established before mpv is asked; a red S4 beside a green G3 is about
#           what FFmpeg's TLS layer does with an IP literal, which is a
#           different finding from "the escape does not work".
#   S5      THE RESERVATION AND THE COMPOSED ARGV, read off /proc/<pid>/cmdline
#           of the player that is actually playing -- the real process, not the
#           source text (rule 14). `--tls-verify=no` and `--no-tls-verify` must
#           not reach mpv and must be NAMED in the shell's log; `--profile=evil`
#           and `--tls-ca-file=` must reach it (the control: the attack and the
#           escape were really delivered); the LAST token must be
#           `--tls-verify=yes` and the token must appear at least twice, which
#           is layer 2 and layer 1 respectively.
#   privacy The synthetic credential in the fixture URLs reaches neither the
#           harness log nor this run's transcript, and no URL reaches mpv's
#           argv (S-03, free regression guard).
#
# AGAINST THE CODE BEFORE THE FIX the proof is the other way round. Run with
# `--baseline <ref>`: S1 and S3 must report `played`, with the GET in the hit
# log -- the attacker holding the stream -- and S5's argv checks must fail,
# because `--tls-verify` is not reserved there and nothing re-asserts it last.
# S2, S4 and the rig pass on both trees and are labelled as controls in the
# summary, so a red run reads as evidence rather than as a broken script.
#
# `--rig-only` runs G1..G8 and stops: no quickshell, no mpv, no display, no
# harness. It exists because the rig is the half of this file that can be
# exercised without a display, and because a rig nobody has seen discriminate
# is not evidence of anything.
#
# WHERE THE MPV CONFIG COMES FROM. $MPV_HOME, pointed at a scratch directory
# this run creates and deletes. The lead's own measurement used a fake HOME and
# XDG_CONFIG_HOME; this script may not write the user's ~/.config/mpv and does
# not touch HOME at all, because HOME belongs to every other process in the
# harness as well. MPV_HOME is read by mpv and by nothing else, and it reaches
# mpv because the player is exec'd with the environment it inherits
# (bin/omarchy-iptv `spawn_detached` ends in `os.execvp`, and the service
# assigns no `environment` to its player Process). Whether mpv honoured it is
# not assumed: S2 is the observation, it runs BEFORE the case that depends on it,
# and S3 is called out as VACUOUS in the run's own output if S2 did not play.
#
# HOLDS THE DISPLAY in live mode: it starts five harnesses and each one opens a
# real mpv window on the current Wayland session. It sends no keystroke, so it
# needs no focus; it refuses to run under hyprlock anyway, because a player
# window over a lock screen is nobody's idea of a measurement.
#
# Ports 8773 (the attacker) and 8774 (the CA-signed provider). 8765 is
# run.sh --serve, 8766 argv-scenario, 8767 text-scenario, 8771 rewind-scenario,
# 8791 and 8799 the live runbooks. F-HARNESS-14: the EXIT trap is installed
# BELOW every refusal that starts nothing, and both halves of cleanup are
# guarded by a flag that is set only once the thing they would kill is ours --
# so a refusal that started nothing signals nothing, least of all the process
# holding a port this run refused to take.
#
#   ./scripts/dev-harness/tls-scenario.sh --rig-only
#   ./scripts/dev-harness/tls-scenario.sh
#   ./scripts/dev-harness/tls-scenario.sh --baseline <pre-fix ref>
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
SOCK="$SCRATCH/runtime/omarchy-iptv/mpv.sock"
LOG="$SCRATCH/tls-scenario.log"
HARNESS_LOG="$SCRATCH/harness${OMARCHY_IPTV_HARNESS_INSTANCE:-}.log"
PORT_SELF=8773
PORT_CA=8774
EXPECT_CHANNELS=5
# Unique per run, letters and digits only, so it is safe inside a URL path and
# inside an m3u name with no quoting: a request logged by anything else can
# never be mistaken for ours.
TOKEN="t$$$RANDOM"
# The synthetic credential the fixture URLs carry. It is local-only and worth
# nothing, and it is in the URL because that is where a provider's credential
# is: a GET in the attacker's log is the attacker holding THIS string. The
# server logs whether an Authorization header arrived as a BOOLEAN and never
# its value, and this script prints neither (rule 5 applies to a scenario's own
# stdout as much as to the plugin's).
CRED_USER="tlsuser"
CRED_PASS="tlspass9kq"
# The provider header the playlist sets per channel, so a logged GET also shows
# the header reaching the attacker. Set over IPC by the helper before the
# loadfile, never on argv (S-03).
PROBE_UA="TlsProbeAgent/1.0"
MODE=live
BASELINE=""
EXPORT_DIR=""
WORK=""
PLUGIN_ROOT=${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}

pass=0
fail=0
# `pass`/`fail` count OUTCOMES; `checks` counts ASSERTIONS. A `|| bad` guard
# moves fail without being an assertion, so only `checks` is comparable
# between a green run and a red one, which is what the floor needs.
checks=0

while (($# > 0)); do
  case $1 in
    # A dropped value is REFUSED rather than defaulted, and the reason is worth
    # a line: `BASELINE=${2:-}` silently left this a full LIVE run -- five
    # harnesses, five mpv windows and a baseline comparison nobody got -- for an
    # operator who typed one word too few. Measured on 2026-10-07 while driving
    # this file's own refusal paths; it started a harness before it was caught.
    --baseline)
      [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--baseline needs a git ref, and got '${2:-}'" >&2; exit 2; }
      BASELINE=$2; shift ;;
    --rig-only) MODE=rig ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

# ---- the refusals. Every one of them exits before anything is started, so
# they sit ABOVE the EXIT trap and above the transcript: a mistyped lever
# should die as a usage error, not as an almost-empty transcript with a path
# printed for it (qa-lib.sh item 3). scripts/qa-lib-test.sh drives four of these
# refusals and asserts that no transcript lands, and that a refusing run never
# asks which pid holds a port.
pgrep -x hyprlock >/dev/null && { echo "the screen is locked; refusing to open a player over a lock prompt" >&2; exit 2; }
for tool in openssl ffmpeg curl python3 ss; do
  command -v "$tool" >/dev/null 2>&1 || { echo "$tool is not on PATH; this scenario needs it" >&2; exit 2; }
done
for port in "$PORT_SELF" "$PORT_CA"; do
  ss -ltn 2>/dev/null | grep -q ":$port " && { echo "port $port is already in use; refusing to disturb whatever holds it" >&2; exit 2; }
done
TREE_LINE=""
if [[ -n $BASELINE ]]; then
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-tls-baseline.XXXXXX") || exit 2
  if ! git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR"; then
    echo "could not export $BASELINE" >&2
    rm -rf "$EXPORT_DIR"
    exit 2
  fi
  PLUGIN_ROOT="$EXPORT_DIR"
  TREE_LINE="== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported"
fi

# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

# ---- the two flags cleanup is guarded by. F-HARNESS-14: a scenario that
# installed its trap above its refusals killed whatever held its port on a
# refusal that had started nothing -- including on the "port is already in
# use" refusal, which exists to protect exactly that process. HARNESS_STARTED
# is set immediately before our own `--detach`, because a start that half
# succeeds still has to be reaped; SERVER_UP only once OUR listener is
# confirmed on both ports and owned by this shell.
HARNESS_STARTED=0
SERVER_UP=0
SERVER_PID=""
# The pid bash handed us for the server we started, kept apart from SERVER_PID:
# it is OUR child by construction (no setsid, no wrapper), so reaping by this
# number is not the forbidden "listener from $!" -- it is never used to find
# the LISTENER, only to stop a child of ours that started too late to be
# confirmed. Every kill checks the pid is still a child of this shell, so a
# reused pid is never signalled.
OWN_CHILD=""
ours() { [[ -n ${1-} && $(ps -o ppid= -p "$1" 2>/dev/null | tr -d ' ') == "$$" ]]; }
cleanup() {
  (( HARNESS_STARTED )) && "$RUN" reap >/dev/null 2>&1
  (( SERVER_UP )) && ours "$SERVER_PID" && kill "$SERVER_PID" 2>/dev/null
  ours "$OWN_CHILD" && kill "$OWN_CHILD" 2>/dev/null
  [[ -n $EXPORT_DIR && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  [[ -n $WORK && -d $WORK ]] && rm -rf "$WORK"
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

qa_transcript_start tls || exit 2
[[ -n $TREE_LINE ]] && echo "$TREE_LINE"
export OMARCHY_IPTV_PLUGIN_ROOT="$PLUGIN_ROOT"
echo "== mode $MODE   plugin tree $PLUGIN_ROOT   scratch $SCRATCH"
echo "== the attacker is https://127.0.0.1:$PORT_SELF (self-signed), the provider is https://127.0.0.1:$PORT_CA (signed by this run's CA)"

ok()  { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad() { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
# The rig phase's two assertion spellings and the live phase's two. They are
# spelled differently ON PURPOSE: the floor recipes in the footer and in
# scripts/qa-lib-test.sh count them by prefix, and a single spelling could not
# tell the --rig-only floor from the live one. Same arrangement chno-scenario
# uses for `seam` and `check`.
rig()   { checks=$((checks + 1)); if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }
rigck() { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }
is()    { checks=$((checks + 1)); if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }
ck()    { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }

ipc() { "$RUN" ipc "$@" 2>/dev/null; }
# qa_field speaks sentinels: NOSTATE when the IPC did not answer, NOFIELD when
# it answered and the field is absent. "" for both is what made three P14
# assertions pass against a dead shell.
svc() { qa_field "$1" "$(ipc state)"; }

WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-tls.XXXXXX") || exit 2
chmod 0700 "$WORK"
# The CA path below is handed to mpv INSIDE the mpvArgs setting, which the
# plugin splits on whitespace (Model.splitMpvArgs), and to openssl as argv. A
# path that could act as shell text or carry a space would make S4 and S5 fail
# for a reason that has nothing to do with TLS, so refuse it here and say so.
qa_safe_path "$WORK" || { echo "the work directory $WORK is not a plain absolute path; set TMPDIR somewhere simpler" >&2; exit 2; }
[[ $WORK != *" "* ]] || { echo "the work directory $WORK carries a space; mpvArgs is whitespace-split, so set TMPDIR somewhere simpler" >&2; exit 2; }
REQLOG="$WORK/hits.log"
PLAYLIST="$WORK/tls.m3u"
MPV_CONF_DIR="$WORK/mpv"
CA_PEM="$WORK/ca.pem"
CA_KEY="$WORK/ca.key"
SRV_PEM="$WORK/srv.pem"
SRV_KEY="$WORK/srv.key"
EVIL_PEM="$WORK/evil.pem"
EVIL_KEY="$WORK/evil.key"
# The media is cached in the harness fixtures directory, the way
# player-scenario.sh caches its own: generating it is the slowest thing here
# and it is the same bytes every run.
mkdir -p "$SCRATCH/fixtures" || exit 2
MEDIA="$SCRATCH/fixtures/tls-test.ts"

# Requests for ONE segment's channel path. The control requests this script
# makes itself use a different path, so the two can never count as each other.
hits()     { qa_count "^GET [0-9]+ /$TOKEN/$1\\.ts " "$REQLOG"; }
hit_lines() { grep -aE -- "^GET [0-9]+ /$TOKEN/$1\\.ts " "$REQLOG" 2>/dev/null | head -2 | tr '\n' ';'; }
all_hits() { qa_count "^GET [0-9]+ /$TOKEN/s[0-9]+\\.ts " "$REQLOG"; }
ctl_hits() { qa_count "^GET [0-9]+ /$TOKEN/control\\.ts " "$REQLOG"; }
# Both spellings, and which one fires is not a detail: the server logs
# TLSREFUSED when the handshake raises inside its own wrap_socket and TLSERROR
# when the CLIENT's alert arrives after the server has finished its half, which
# is what TLS 1.3 does here. Measured --rig-only on 2026-10-07: counting
# TLSREFUSED alone saw 0 of the 2 refusals G4 and G5 provoked; counting both saw
# 2 of 2. It is still only REPORTED and never asserted -- a refusal the server
# never notices is a refusal all the same, so the discriminator is the absence of
# a GET.
tls_refusals() { qa_count '^(TLSREFUSED|TLSERROR) ' "$REQLOG"; }
# The listener's pid, from ss -- never from $!. The project's own rule, learned
# when a live pass "killed" a fixture server and found it still serving at the
# next segment.
listener_pid() { ss -ltnp 2>/dev/null | awk -v p=":$1 " '$0 ~ p' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2; }
# Every mpv bound to THIS scratch socket. The pattern carries the scratch path,
# so it can never match the live session's player, and it appears nowhere in
# this script's own argv, so it can never match the shell running it.
player_pids()  { pgrep -f "input-ipc-server=$SOCK" 2>/dev/null; }
player_count() { player_pids | wc -l | tr -d ' '; }
player_pid()   { player_pids | head -1; }

# A bounded wait that SAYS it gave up (rule 3): no loop here may be the one
# that waits forever.
until_eq() {   # until_eq <want> <secs> <cmd...>
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 5; i++)); do
    [[ "$("$@")" == "$want" ]] && return 0
    sleep 0.2
  done
  printf 'gave up after %ss waiting for %s to read %s\n' "$secs" "$*" "$want" >&2
  return 1
}
wait_port() {   # wait_port <port> <up|down> <secs>
  local port=$1 want=$2 secs=$3 i seen
  for ((i = 0; i < secs * 10; i++)); do
    seen=up; ss -ltn 2>/dev/null | grep -q ":$port " || seen=down
    [[ $seen == "$want" ]] && return 0
    sleep 0.1
  done
  printf 'gave up after %ss waiting for port %s to be %s\n' "$secs" "$port" "$want" >&2
  return 1
}
wait_value() {   # wait_value <secs> <python-expr over d>: a REAL answer, not a sentinel
  local secs=$1 expr=$2 i
  for ((i = 0; i < secs * 5; i++)); do
    qa_value "$(svc "$expr")" && return 0
    sleep 0.2
  done
  printf 'gave up after %ss waiting for a real answer to %s\n' "$secs" "$expr" >&2
  return 1
}
wait_log() {   # wait_log <ere> <secs>
  local re=$1 secs=$2 i
  for ((i = 0; i < secs * 10; i++)); do
    grep -qaE -- "$re" "$HARNESS_LOG" 2>/dev/null && return 0
    sleep 0.1
  done
  printf 'gave up after %ss waiting for the harness log to carry %s\n' "$secs" "$re" >&2
  return 1
}

# ---- the certificates. Three openssl runs, every argument a literal or a path
# this run created: no shell text is composed out of anything (rule 2).
#
# Both leaf certificates carry the SAME subject and the SAME subjectAltName,
# and that is the whole point of the pair: the ONLY thing that differs is who
# signed them, so a refusal can only be about the trust chain. The SAN carries
# IP:127.0.0.1 and, belt and braces, DNS:127.0.0.1 as well -- OpenSSL checks an
# IP literal through a different path from a DNS name depending on how the
# client asks, and a scenario that failed because of the shape of its own SAN
# would read as a failure of the fix.
cat >"$WORK/leaf.ext" <<'EXT'
basicConstraints = critical,CA:FALSE
extendedKeyUsage = serverAuth
subjectAltName = IP:127.0.0.1, DNS:localhost, DNS:127.0.0.1
EXT
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -sha256 \
  -keyout "$CA_KEY" -out "$CA_PEM" \
  -subj "/CN=omarchy-iptv tls-scenario CA $TOKEN" \
  -addext "basicConstraints=critical,CA:TRUE" >/dev/null 2>&1 \
  || { echo "openssl could not make the CA" >&2; exit 2; }
openssl req -newkey rsa:2048 -nodes -sha256 \
  -keyout "$SRV_KEY" -out "$WORK/srv.csr" -subj "/CN=127.0.0.1" >/dev/null 2>&1 \
  || { echo "openssl could not make the server request" >&2; exit 2; }
openssl x509 -req -in "$WORK/srv.csr" -CA "$CA_PEM" -CAkey "$CA_KEY" -CAcreateserial \
  -days 1 -sha256 -extfile "$WORK/leaf.ext" -out "$SRV_PEM" >/dev/null 2>&1 \
  || { echo "openssl could not sign the server certificate" >&2; exit 2; }
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -sha256 \
  -keyout "$EVIL_KEY" -out "$EVIL_PEM" -subj "/CN=127.0.0.1" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "extendedKeyUsage=serverAuth" \
  -addext "subjectAltName=IP:127.0.0.1,DNS:localhost,DNS:127.0.0.1" >/dev/null 2>&1 \
  || { echo "openssl could not make the self-signed certificate" >&2; exit 2; }
chmod 0600 "$CA_KEY" "$SRV_KEY" "$EVIL_KEY" 2>/dev/null

# G1/G2: the chain, before any of it is pointed at the plugin. `openssl verify`
# with no -CAfile uses the system store, which is where the second half of G2
# comes from: a certificate nobody signed is refused by a verifier that has not
# been handed our CA.
openssl verify -CAfile "$CA_PEM" "$SRV_PEM" >/dev/null 2>&1; srv_chain=$?
openssl verify "$EVIL_PEM" >/dev/null 2>&1; evil_chain=$?
rig "G1 the CA this run generated really signs the server certificate" "$srv_chain" "0"
rigck "G2 and the attacker's self-signed certificate verifies against nothing in the system store" '(( evil_chain != 0 ))'

# ---- the media. Cached between runs; 60 s so that a player which reaches the
# bytes stays up long enough to be read off /proc, rather than racing its own
# end-of-file.
if [[ ! -s $MEDIA ]]; then
  echo "== generating the test stream (ffmpeg, 60 s, cached at $MEDIA for later runs)"
  timeout 180 ffmpeg -loglevel error -y -f lavfi -i "testsrc=size=320x240:rate=15" \
    -f lavfi -i "sine=frequency=440:sample_rate=22050" -t 60 \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 32k -f mpegts "$MEDIA" >/dev/null 2>&1 \
    || { echo "ffmpeg could not generate the test stream" >&2; exit 2; }
fi
MEDIA_BYTES=$(stat -c '%s' "$MEDIA" 2>/dev/null || echo 0)

# ---- the attacker's own view: one process, two TLS listeners, one hit log.
#
# It answers every GET with the media and writes one line per request. The
# Authorization header is logged as a BOOLEAN: the whole finding is that a
# successful handshake hands this server the credential, and a scenario that
# wrote the credential into its own evidence file would be the same leak one
# layer along (rule 5). A handshake that fails is logged too, best effort and
# never asserted on -- under TLS 1.3 the client's refusal can arrive as an
# alert the server sees late or not at all, so the DISCRIMINATOR is the absence
# of a GET, not the presence of a refusal line.
cat >"$WORK/tls_server.py" <<'PY'
import http.server
import socketserver
import ssl
import sys
import threading

LOG = sys.argv[1]
MEDIA = sys.argv[2]
SPECS = sys.argv[3:]
LOCK = threading.Lock()


def log(line):
    with LOCK:
        with open(LOG, "a") as handle:
            handle.write(line + "\n")
            handle.flush()


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def _record(self, method):
        port = self.server.server_address[1]
        auth = "yes" if self.headers.get("Authorization") else "no"
        log("%s %d %s UA=%s AUTH=%s"
            % (method, port, self.path, self.headers.get("User-Agent") or "-", auth))

    def do_GET(self):
        self._record("GET")
        try:
            with open(MEDIA, "rb") as handle:
                data = handle.read()
        except OSError:
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "video/mp2t")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def do_HEAD(self):
        self._record("HEAD")
        self.send_response(200)
        self.send_header("Content-Type", "video/mp2t")
        self.end_headers()

    def log_message(self, *args):
        pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    context = None

    def get_request(self):
        conn, addr = self.socket.accept()
        try:
            return self.context.wrap_socket(conn, server_side=True), addr
        except Exception as exc:
            log("TLSREFUSED %d %s" % (self.server_address[1], type(exc).__name__))
            try:
                conn.close()
            except Exception:
                pass
            raise OSError("tls handshake refused")

    def handle_error(self, request, client_address):
        log("TLSERROR %d" % (self.server_address[1],))


def serve(port, cert, key):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server = Server(("127.0.0.1", port), Handler)
    server.context = context
    server.serve_forever()


threads = []
for index in range(0, len(SPECS), 3):
    port, cert, key = int(SPECS[index]), SPECS[index + 1], SPECS[index + 2]
    thread = threading.Thread(target=serve, args=(port, cert, key), daemon=True)
    thread.start()
    threads.append(thread)
for thread in threads:
    thread.join()
PY
: >"$REQLOG"
chmod 0600 "$REQLOG"
python3 "$WORK/tls_server.py" "$REQLOG" "$MEDIA" \
  "$PORT_SELF" "$EVIL_PEM" "$EVIL_KEY" \
  "$PORT_CA" "$SRV_PEM" "$SRV_KEY" >/dev/null 2>&1 &
OWN_CHILD=$!
# On every exit from here down, the trap reaps OWN_CHILD while it is still
# ours: a server that binds after this window must not be left holding a port
# for the next run to refuse as foreign.
wait_port "$PORT_SELF" up 5 || { echo "the attacker's listener never came up on $PORT_SELF" >&2; exit 2; }
wait_port "$PORT_CA" up 5   || { echo "the provider's listener never came up on $PORT_CA" >&2; exit 2; }
pid_self=$(listener_pid "$PORT_SELF")
pid_ca=$(listener_pid "$PORT_CA")
# Ours only if this shell is its parent and one process holds both: a listener
# somebody else bound between the preflight check and ours is NOT remembered,
# and is therefore never signalled.
if ! ours "$pid_self" || [[ -z $pid_ca || $pid_ca != "$pid_self" ]]; then
  echo "ports $PORT_SELF/$PORT_CA are held by pid ${pid_self:-?}/${pid_ca:-?}, not by one child of this run; leaving them alone" >&2
  exit 2
fi
SERVER_PID=$pid_self
SERVER_UP=1
echo "== the rig is up: pid $SERVER_PID holds $PORT_SELF and $PORT_CA, media $MEDIA_BYTES bytes"

# G3..G6: does the rig DISCRIMINATE? Four curls, every one of them a client
# that verifies the way the plugin's own helper already does, so these also say
# what `curl` said in the lead's control: refused without the CA, accepted with
# it. The control path is used so these never count as a stream hit.
# "<exit> <http_code>". Both halves, because they fail differently and the
# difference is the evidence: 60 is curl's "peer certificate was not OK", which
# is a REFUSAL, while 7 would be "nothing is listening" -- and a check that
# accepted any non-zero exit would read a dead server as a successful refusal.
# G3 and G6 are what keep that honest from the other side: they demand 200 on
# the same two ports.
curl_code() {   # curl_code <url> <extra curl args...>
  local url=$1; shift
  local out status
  out=$(curl -s -o /dev/null -A "tls-scenario" -m 20 -w '%{http_code}' "$@" "$url" 2>/dev/null)
  status=$?
  printf '%s %s\n' "$status" "$out"
}
CTL_PATH="/$TOKEN/control.ts"
rig "G3 a client that trusts this run's CA fetches the provider's stream" \
   "$(curl_code "https://127.0.0.1:$PORT_CA$CTL_PATH" --cacert "$CA_PEM")" "0 200"
rig "G4 and a client that does NOT name the CA refuses it, so this CA is in no system store" \
   "$(curl_code "https://127.0.0.1:$PORT_CA$CTL_PATH")" "60 000"
rig "G5 a verifying client refuses the attacker's self-signed certificate" \
   "$(curl_code "https://127.0.0.1:$PORT_SELF$CTL_PATH")" "60 000"
rig "G6 and the attacker's server does serve the stream to a client that stops verifying" \
   "$(curl_code "https://127.0.0.1:$PORT_SELF$CTL_PATH" -k)" "0 200"
# G7/G8: the counter itself. Without these, every zero below could be a
# mis-spelled grep rather than a refusal.
rigck "G7 the hit log attributes what the server answered (control: $(ctl_hits) control GETs, $(tls_refusals) refused handshakes)" \
   '(( $(ctl_hits) >= 2 ))'
rig "G8 and no channel path has been fetched by anything yet" "$(all_hits)" "0"

if [[ $MODE == rig ]]; then
  (( SERVER_UP )) && ours "$SERVER_PID" && kill "$SERVER_PID" 2>/dev/null
  wait_port "$PORT_SELF" down 5 || true
  wait_port "$PORT_CA" down 5 || true
  echo "teardown: $(ss -ltn 2>/dev/null | grep -cE ":($PORT_SELF|$PORT_CA) ") of 2 ports still listening"
  # The floor, --rig-only half. Recipe in the footer; scripts/qa-lib-test.sh
  # asserts it matches what this file actually has. This line is INDENTED on
  # purpose: both recipes count assertions by prefix at column zero, so a floor
  # line must not count itself.
  EXPECTED_CHECKS=8
  ran=$checks
  rig "the rig ran every check it has" "$ran" "$EXPECTED_CHECKS"
  printf '\n== summary (--rig-only, the plugin was not asked anything): %d passed, %d failed, %d assertions executed\n' \
    "$pass" "$fail" "$checks"
  (( fail == 0 )) || exit 1
  exit 0
fi

# ---- the mpv config the profile cases need, in a directory mpv alone reads.
mkdir -p "$MPV_CONF_DIR" && chmod 0700 "$MPV_CONF_DIR" || exit 2
{
  printf '# scripts/dev-harness/tls-scenario.sh, D-SINK-13. Written per run, deleted with it.\n'
  printf '# The global section is EMPTY on purpose: S1 and S4 must be unaffected by\n'
  printf '# this file existing at all.\n'
  printf '\n[evil]\n'
  printf '# The bypass the lead measured: a profile is a later command-line token\n'
  printf '# carrying arbitrary options, so this beats --tls-verify=yes in the base argv\n'
  printf '# and loses to the same token re-asserted after the user arguments.\n'
  printf 'tls-verify=no\n'
  printf '\n[good]\n'
  printf '# The control. On a verifying tree the CA-signed stream can only play if mpv\n'
  printf '# read THIS file and applied THIS profile.\n'
  printf 'tls-ca-file=%s\n' "$CA_PEM"
} >"$MPV_CONF_DIR/mpv.conf"
chmod 0600 "$MPV_CONF_DIR/mpv.conf"
export MPV_HOME="$MPV_CONF_DIR"

# ---- the playlist: one channel per segment, each pointed at the server that
# segment needs -- S1 and S3 at the attacker, S2, S4 and S5 at the provider --
# and each on its own path, which is how the hit log attributes per segment.
# Every channel carries the same provider header, so a logged GET shows the
# header reaching the attacker along with the URL.
channel() {   # channel <n> <port>
  printf '#EXTINF:-1 tvg-id="s%d" group-title="TLS",TLS Probe %d\n' "$1" "$1"
  printf '#EXTVLCOPT:http-user-agent=%s\n' "$PROBE_UA"
  printf 'https://%s:%s@127.0.0.1:%d/%s/s%d.ts\n' "$CRED_USER" "$CRED_PASS" "$2" "$TOKEN" "$1"
}
{
  printf '#EXTM3U\n'
  channel 1 "$PORT_SELF"
  channel 2 "$PORT_CA"
  channel 3 "$PORT_SELF"
  channel 4 "$PORT_CA"
  channel 5 "$PORT_CA"
} >"$PLAYLIST"
chmod 0600 "$PLAYLIST"

: >"$LOG"

# segment <mpvArgs>: a fresh harness with those user arguments in force.
# mpvArgs reaches the service through the environment the fake bar entry reads
# (shell.qml's seedBarEntry), which is why each segment is its own shell: the
# setting is read at launch, and a fresh start also means no failure mark from
# the previous segment can decide this one.
segment() {
  local args=$1
  "$RUN" reap >/dev/null 2>&1
  : >"$HARNESS_LOG"
  export OMARCHY_IPTV_MPV_ARGS="$args"
  HARNESS_STARTED=1
  "$RUN" --detach --timeout 0 --playlist "$PLAYLIST" >>"$LOG" 2>&1 || return 1
  wait_log 'service loaded' 20 || return 1
  until_eq "$EXPECT_CHANNELS" 20 svc "d['channels']" || {
    # The shell can be alive and UNREACHABLE, and then every `svc` answers
    # NOSTATE and the cause is in the shell's own log rather than in ours. Seen
    # on 2026-10-07 with OMARCHY_IPTV_HARNESS_DIR set deep under /tmp:
    # quickshell's ipc.sock went past the 108-byte sockaddr_un limit, so
    # `Failed to start IPC server on path ...` and nothing could be asked. Print
    # the shell's errors rather than making the operator go looking.
    printf 'the shell is up but did not answer; its own errors:\n' >&2
    grep -a 'ERROR' "$HARNESS_LOG" 2>/dev/null | head -3 >&2
    return 1
  }
  return 0
}

# outcome <id> <stem> <secs>: what the ATTACKER saw, in one word -- `played`,
# `refused` or `undecided`. The DECISION is qa_outcome in scripts/qa-lib.sh,
# which scripts/qa-lib-test.sh calls for real without a display; what is here is
# only the bounded poll that feeds it. `undecided` is what the poll reports when
# neither signal arrives, and it is never a pass: a zero measured after a
# timeout says nothing about a refusal.
outcome() {
  local id=$1 stem=$2 secs=$3 i verdict
  for ((i = 0; i < secs * 5; i++)); do
    verdict=$(qa_outcome "$(hits "$stem")" "$(svc "d['failedAt'].get('$id')")")
    [[ $verdict == undecided ]] || { printf '%s\n' "$verdict"; return 0; }
    sleep 0.2
  done
  printf 'undecided\n'
  printf 'gave up after %ss: neither a GET of /%s/%s.ts nor a failure verdict for %s\n' \
    "$secs" "$TOKEN" "$stem" "$id" >&2
  return 1
}
# One line of context per segment, printed always, so a red run says what it
# saw rather than only that it was unhappy. No URL and no credential: the host
# is in the header line above and the path identifies the segment. `lastError`
# is redacted at its source (Model.redactUrls) and S1 asserts that for real;
# the stderr tail is reported as a LINE COUNT rather than quoted, because this
# script's own stdout is a sink and a tail quoted here would be a second copy
# of whatever mpv said about the address.
segment_info() {
  printf '   info %s: hits=%s playing=%s player=%s failedAt=%s stderrLines=%s lastError=%s\n' \
    "$1" "$(hits "$2")" "$(svc "d['playing']")" "$(player_count)" \
    "$(svc "d['failedAt'].get('t:$2')")" "$(svc "len(d['playerStderr'])")" "$(svc "d['lastError']")"
}

# ============================================================== S1, the plain case
echo "== S1 the attacker's certificate, no user mpvArgs: the stream must be REFUSED"
segment "" || bad "S1 the harness did not come up (see $LOG)"
ipc play "t:s1" >/dev/null
s1_outcome=$(outcome "t:s1" s1 40)
s1_hits=$(hits s1)
wait_value 10 "d['lastError']" || true
s1_err=$(svc "d['lastError']")
segment_info S1 s1
is "S1 the attacker's stream was REFUSED, not played" "$s1_outcome" "refused"
is "S1 and the attacker's log holds no GET of it" "$s1_hits" "0"
until_eq 0 15 player_count || true
is "S1 no player is left behind by the refusal" "$(player_count)" "0"
ck "S1 a reason was recorded and it carries no credential" \
   'qa_value "$s1_err" && [[ "$s1_err" != *"$CRED_PASS"* && "$s1_err" != *"$CRED_USER:"* ]]'

# ============================================================== S2, the control for S3
# It runs BEFORE the case it de-vacuums, which is the lead's own discipline in
# the addendum ("positive control first, because without it the next rows prove
# nothing"): if mpv never read the scratch config, S3's refusal would be a
# refusal of nothing in particular.
echo "== S2 control: the CA named ONLY inside an mpv profile. If this plays, the config was read"
segment "--profile=good" || bad "S2 the harness did not come up (see $LOG)"
ipc play "t:s2" >/dev/null
s2_outcome=$(outcome "t:s2" s2 40)
s2_hits=$(hits s2)
segment_info S2 s2
is "S2 the provider's stream PLAYS with the CA named through a profile" "$s2_outcome" "played"
ck "S2 and the provider's log holds the GET (control: $s2_hits)" '(( s2_hits >= 1 ))'
[[ $s2_outcome == played ]] || echo "WARNING: S2 did not play, so mpv may not have read $MPV_CONF_DIR/mpv.conf at all -- and then S3 below is VACUOUS: it may be refusing because no profile was ever applied, not because the trailing token beat one. Diagnose this before reading S3 either way."

# ============================================================== S3, the profile bypass
echo "== S3 the attacker again, with user mpvArgs --profile=evil and a profile that says tls-verify=no"
segment "--profile=evil" || bad "S3 the harness did not come up (see $LOG)"
ipc play "t:s3" >/dev/null
s3_outcome=$(outcome "t:s3" s3 40)
s3_hits=$(hits s3)
segment_info S3 s3
is "S3 the profile did not reopen the hole: still REFUSED" "$s3_outcome" "refused"
is "S3 and still no GET in the attacker's log" "$s3_hits" "0"

# ============================================================== S4, the documented escape
echo "== S4 the documented escape: --tls-ca-file on argv, unreserved, against the signed certificate"
segment "--tls-ca-file=$CA_PEM" || bad "S4 the harness did not come up (see $LOG)"
ipc play "t:s4" >/dev/null
s4_outcome=$(outcome "t:s4" s4 40)
s4_hits=$(hits s4)
segment_info S4 s4
is "S4 a provider with a private CA can still be watched" "$s4_outcome" "played"
ck "S4 and the stream really was fetched (control: $s4_hits)" '(( s4_hits >= 1 ))'

# ============================================================== S5, the reservation and the argv
echo "== S5 the reservation and the composed argv, read off the player that is playing"
segment "--tls-verify=no --no-tls-verify --profile=evil --tls-ca-file=$CA_PEM" \
  || bad "S5 the harness did not come up (see $LOG)"
ipc play "t:s5" >/dev/null
s5_outcome=$(outcome "t:s5" s5 40)
s5_hits=$(hits s5)
s5_pid=$(player_pid)
# qa_cmdline refuses an EMPTY pid: /proc//cmdline is /proc/cmdline, and six
# S-03 sweeps once compared their secrets against the KERNEL command line and
# passed.
s5_cmd=$(qa_cmdline "$s5_pid")
s5_last=$(awk '{ print $NF }' <<<"$s5_cmd")
s5_yes=$(grep -o -- '--tls-verify=yes' <<<"$s5_cmd" | wc -l | tr -d ' ')
segment_info S5 s5
is "S5 the escape survives the hostile profile and the reserved tokens" "$s5_outcome" "played"
ck "S5 the stream was fetched (control: $s5_hits)" '(( s5_hits >= 1 ))'
# The positive control. Without it every sweep below is a statement about a
# string nobody has established is the player's argv.
ck "S5 the player's command line was actually read" '[[ -n "$s5_cmd" && "$s5_cmd" == *"input-ipc-server=$SOCK"* ]]'
ck "S5 the hostile profile really was delivered to mpv (control for S3)" '[[ "$s5_cmd" == *"--profile=evil"* ]]'
ck "S5 the CA file really was delivered to mpv (control for S4)" '[[ "$s5_cmd" == *"--tls-ca-file="* ]]'
ck "S5 layer 3: --tls-verify=no never reached mpv" '[[ "$s5_cmd" != *"--tls-verify=no"* ]]'
ck "S5 layer 3: --no-tls-verify never reached mpv either" '[[ "$s5_cmd" != *"--no-tls-verify"* ]]'
is "S5 layer 2: the LAST token of the composed argv re-asserts verification" "$s5_last" "--tls-verify=yes"
ck "S5 layer 1 and 2 are both there: $s5_yes occurrences of --tls-verify=yes" '(( s5_yes >= 2 ))'
ck "S5 and S-03 still holds: no URL and no credential on the argv" \
   '[[ "$s5_cmd" != *"://"* && "$s5_cmd" != *"$CRED_PASS"* ]]'
wait_log 'ignoring mpvArgs tokens' 10 || true
s5_warn=$(qa_count 'ignoring mpvArgs tokens.*--tls-verify=no.*--no-tls-verify' "$HARNESS_LOG")
ck "S5 layer 3 is HEARD: the shell names both refused spellings in its log" '(( s5_warn >= 1 ))'

# ============================================================== privacy
echo "== the credential in the fixture URL reaches no log of ours"
# qa_leak_scan PRINTS the offending lines, so its output is captured and only
# COUNTED here: a sweep that echoed the leak it found would put the credential
# into this run's transcript, which is the same exposure one layer along. The
# status is the verdict (0 clean, 1 leak, 2 vacuous) and 2 is never a pass --
# the control ERE has to match something or the file is not evidence.
# The harness log covers S5's shell: one whole start, playlist parse and play.
leak_hits=$(qa_leak_scan 'service loaded' "$CRED_PASS|$CRED_USER:" "$HARNESS_LOG"); leak_log=$?
is "the harness log carries no credential (0 clean, 1 leak, 2 vacuous)" "$leak_log" "0"
[[ $leak_log == 1 ]] && printf '   %s leaking line(s) in %s; read them there, they are not repeated here\n' \
  "$(printf '%s\n' "$leak_hits" | wc -l)" "$HARNESS_LOG"
# R18's lesson: the transcript is written by a tee on the far side of a pipe,
# so a sweep that does not sync can read a file short of its last lines -- a
# privacy check that cannot go red for the thing it guards.
qa_transcript_sync 5 || true
leak_hits=$(qa_leak_scan 'PASS|FAIL' "$CRED_PASS|$CRED_USER:" "$QA_TRANSCRIPT"); leak_tr=$?
is "and this run's own transcript carries none either" "$leak_tr" "0"
[[ $leak_tr == 1 ]] && printf '   %s leaking line(s) in the transcript named above\n' \
  "$(printf '%s\n' "$leak_hits" | wc -l)"

# ============================================================== teardown, proven
"$RUN" reap >/dev/null 2>&1
(( SERVER_UP )) && ours "$SERVER_PID" && kill "$SERVER_PID" 2>/dev/null
wait_port "$PORT_SELF" down 5 || true
wait_port "$PORT_CA" down 5 || true
until_eq 0 10 player_count || true
is "teardown: no player survives the run" "$(player_count)" "0"
is "teardown: both ports are free again" "$(ss -ltn 2>/dev/null | grep -cE ":($PORT_SELF|$PORT_CA) ")" "0"
echo "hits: s1=$s1_hits s2=$s2_hits s3=$s3_hits s4=$s4_hits s5=$s5_hits control=$(ctl_hits) refused-handshakes=$(tls_refusals)"
echo "what the attacker logged for the two cases that must refuse (empty is the point): s1=[$(hit_lines s1)] s3=[$(hit_lines s3)]"
if [[ -n $BASELINE ]]; then
  echo "baseline $BASELINE: S1 and S3 are expected RED here -- 'played', with a GET of the stream in the attacker's own log, is the finding reproduced -- and so are S5's four argv checks and its log check, because --tls-verify is not reserved on that tree and nothing re-asserts it last. S1's 'no player left behind' goes red with them: a player that is playing is not a player a refusal left behind. S2, S4 and G1-G8 pass on both trees; they are controls, not discriminators."
fi

# The floor, live half. D-PLY-9 was not that an assertion was wrong -- it was
# that bash offers NO way to turn a failed expansion into a failed test, so a
# check vanished and the summary printed one line fewer than anyone expected
# and nobody counted. Assert how many assertions ran, so a check that stops
# executing turns the run red instead of shortening the summary.
#
# Recount after adding or removing one:
#   rig-only:  grep -c '^\(rig\|rigck\) ' scripts/dev-harness/tls-scenario.sh
#   live:      that, plus grep -c '^\(is\|ck\) ' ..., minus 1 for THIS line.
# The rig floor's own line is indented inside the --rig-only arm, so neither
# floor line is ever counted by the recipe that guards it.
# scripts/qa-lib-test.sh asserts both numbers against those greps, so a
# forgotten bump reddens the gate on this machine rather than on the display
# lane's, weeks later. Never lower one to make a run green.
EXPECTED_CHECKS=33
ran=$checks
is "the scenario ran every check it has" "$ran" "$EXPECTED_CHECKS"

printf '\n== summary: %d passed, %d failed, %d assertions executed\n' "$pass" "$fail" "$checks"
(( fail == 0 )) || exit 1
