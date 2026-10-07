#!/bin/bash
# scripts/dev-harness/run.sh -- smoke-test the plugin without installing it.
#
#   run.sh [options]                 start the harness (foreground, killed after --timeout)
#   run.sh ipc <fn> [args...]        call the running harness (IpcHandler target "harness")
#   run.sh plugin-ipc <fn> [args...] call the PLUGIN's own IpcHandler inside the harness
#                                    (target io.github.rmcdavid.iptv): toggle, stop, next,
#                                    previous, refresh, play, channel, pip, pause, back,
#                                    forward, live -- the verbs a user binds (F-RWD-14)
#   run.sh shot [name]               screenshot the focused output into the scratch dir
#   run.sh key [--to-compositor] <wtype args...>
#                                    send keys to the guide (wtype). REFUSES, exit 3,
#                                    unless the harness guide holds the keyboard, and
#                                    always refuses while hyprlock is up (F-M3-1)
#   run.sh type <text>               type text and PROVE it arrived (F-HARNESS-1). Same
#                                    two refusals; no --to-compositor (see below)
#   run.sh clean                     wipe the scratch dirs (cache, state, runtime)
#   run.sh scenario                  scripted Sources verification (sources-scenario.sh)
#   run.sh player-scenario           scripted detached-player verification (player-scenario.sh)
#   run.sh restart-shell             kill the detached harness shell and start a new one with
#                                    the same environment, leaving the player alone (M2-02)
#   run.sh shell-stop                SIGTERM the detached harness shell and wait for it
#   run.sh reap                      kill the detached shell, the fixture server and the
#                                    harness player (what the foreground EXIT trap does)
#
# Options for start:
#   --open              open the guide right after load
#   --timeout N         kill quickshell after N seconds (default 15; 0 = no limit)
#   --playlist SRC      playlist URL/path (default: generated fixture with dead local URLs; "none" = unconfigured)
#   --epg URL           EPG URL (default: none)
#   --source2 SRC       seed the source history (state.json v2) with a second, never-fetched
#                       source before start (helper `state source add`); printed as scheme://host
#   --serve             serve a generated test video on 127.0.0.1:8765 and point the
#                       fixture's "Harness Live" channel at it (exercises the mpv path locally)
#   --fake-epg          drop a synthetic epg-now.json into the scratch cache (guide EPG rows)
#   --vertical          fake a vertical bar
#   --no-name           showChannelName=false
#   --label-max N       barLabelMaxWidth
#   --order ORDER       channelOrder: playlist (default) or number (M2-03)
#   --entry-ms N        numberEntryMs, the channel-number entry timeout
#   --no-bar-number     barShowChannelNumber=false
#   --keep              keep the scratch cache/state between runs (default wipes cache+state)
#   --detach            start in the background and return (no EXIT trap): the shell survives
#                       this invocation, which is what `restart-shell` needs. Reap with `reap`.
#   --instance NAME     a second config root (root<NAME>) sharing the same cache / state /
#                       runtime dirs: two services, one runtime directory, one player
#   --window MODE       layer (default): the production PanelWindow + layer-shell. floating: host
#                       the guide in a FloatingWindow (xdg toplevel) so it maps under a compositor
#                       with no layer-shell, e.g. headless cage (docs/SPIKE-CAGE-HEADLESS.md). Harness-only.
#
# Why `key` and `type` refuse (F-M3-1 half (a)). wtype types into whatever
# surface holds the keyboard, which on a bad day is the terminal the scenario is
# running in, the editor behind it, or -- worst -- a lock prompt, where every
# keystroke registers as a failed unlock attempt. NEITHER failure is visible in
# a scenario's own assertions: a key that landed somewhere else reads exactly
# like a guide that did not react, and `sky` arriving as `ky` still filters 20
# rows to 3. So both verbs ask the harness where the keyboard is first
# (`ipc focusState`) and exit 3 naming what they found. Two kinds of refusal:
#   hyprlock is up      -- never escapable, no flag, nothing to pass.
#   the guide has not got the keyboard -- escapable with --to-compositor, which
#     must come FIRST (everything after it is wtype's, and wtype's own `--`
#     means "the rest is text") and exists for a chord aimed at the COMPOSITOR
#     rather than at a surface. It is not a way to make a failing scenario pass.
# `type` has no escape hatch: it proves the text reached the GUIDE by reading it
# back, so a keystroke aimed at the compositor has nothing for it to prove.
# The compositor cannot answer "who holds the keyboard" at all -- `hyprctl
# layers` has no such field and `hyprctl activewindow` names a toplevel while
# an overlay is taking keys -- so the question goes to the guide. The numbers
# behind that are in scripts/dev-harness/shell.qml, at harness.focusSnapshot.
#
# Environment: OMARCHY_IPTV_PLUGIN_ROOT overrides which checkout the harness
# loads Service.qml / Guide.qml / BarWidget.qml / bin/omarchy-iptv from
# (default: this repo). That is how a scenario is run against pre-change code
# to prove it fails there before it counts as evidence (CLAUDE.md rule 10).
#
# Everything lives under $OMARCHY_IPTV_HARNESS_DIR (default $XDG_RUNTIME_DIR/omarchy-iptv-harness):
#   root/     scratch Quickshell config root: shell.qml + Commons/ Ui/ symlinks (the `qs` prefix)
#   cache/    XDG_CACHE_HOME  -> cache/omarchy-iptv/{channels,playlist-status,epg-now}.json
#   state/    XDG_STATE_HOME  -> state/omarchy-iptv/state.json
#   runtime/  XDG_RUNTIME_DIR -> runtime/omarchy-iptv/mpv.sock (+ hypr symlink so hyprctl works)
#   fixtures/ generated playlist / test.ts (MPEG-TS, like a live stream; an MP4 with a trailing moov is not seekable over HTTP)
# Never run against a real network stream from here; the fixture uses 127.0.0.1 only.
# The playlist/EPG URL is never printed (it may carry credentials); only
# scheme://host is echoed (S-08). Everything this script starts (fixture
# HTTP server, Quickshell, the harness mpv) is reaped by an EXIT trap, so a
# Ctrl-C or SIGTERM leaves nothing behind; SIGKILL cannot be trapped, so the
# next start also reaps a stale fixture server.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
die() { echo "[run.sh] $*" >&2; exit 2; }
# Which checkout the plugin QML and the helper come from. Defaults to this
# repo; a scenario points it at an exported pre-change tree to show a check
# failing there first.
# C3: this file has no `set -e`, so a failed `cd` left PLUGIN_ROOT EMPTY and
# every later "$PLUGIN_ROOT/bin/omarchy-iptv" and "$PLUGIN_ROOT/Model.js"
# silently became a path at /. Nothing checked it.
PLUGIN_ROOT=$(cd "${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}" 2>/dev/null && pwd)
[[ -n $PLUGIN_ROOT ]] || die "OMARCHY_IPTV_PLUGIN_ROOT=${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT} is not a directory I can enter"
[[ -f $PLUGIN_ROOT/Model.js ]] || die "$PLUGIN_ROOT holds no Model.js; that is not a plugin tree"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
SHELL_DIR=${OMARCHY_PATH:-/usr/share/omarchy}/shell
SERVE_PORT=8765
SERVER_PID=""
QS_PID=""
INSTANCE=${OMARCHY_IPTV_HARNESS_INSTANCE:-}
KEEP_PLAYER=0

# scheme://host of a source URL, "local file" for a path, "(none)" when unset.
source_label() {
  local src=$1 re='^([A-Za-z][A-Za-z0-9+.-]*)://([^@/?#]*@)?([^/:?#]+)'
  if [[ -z $src ]]; then
    echo "(none)"
  elif [[ $src =~ $re ]]; then
    local scheme=${BASH_REMATCH[1],,}
    if [[ $scheme == file ]]; then echo "local file"; else echo "$scheme://${BASH_REMATCH[3]}"; fi
  else
    echo "local file"
  fi
}

fixture_server_pattern() {
  echo "http.server $SERVE_PORT --bind 127.0.0.1 --directory $SCRATCH/fixtures"
}

# The config root of this instance ("" = the default one) and its pid file.
qs_root()    { echo "$SCRATCH/root$INSTANCE"; }
qs_pidfile() { echo "$SCRATCH/qs$INSTANCE.pid"; }

# The PLUGIN's own IpcHandler target, as opposed to `harness`, which is
# shell.qml's: the verbs a user binds (`toggle`, `channel`, `pause`, `back`).
# SPIKE-LIVE-REWIND 12.5 measured what reaching it inside the harness costs --
# the scratch runtime directory AND the absolute Wayland socket path, which is
# exactly what harness_env already exports -- and said run.sh should carry it
# so a scenario does not. F-RWD-14.
#
# The string is joined to two other files by a NAME, with nothing calling it:
# `manifest.json`'s `id`, which the production Service.qml reads into
# `pluginId`, and `shell.qml`'s own `pluginId` literal, which is what the
# harness actually registers. The manifest half is CHECKED below rather than
# trusted. The shell.qml half cannot be read from here without grepping QML
# for a literal, and its failure mode is loud anyway: `qs ipc` refuses a
# target it cannot find instead of answering for the wrong one.
PLUGIN_TARGET="io.github.rmcdavid.iptv"
# Prints the target, or fails with the disagreement named. An UNREADABLE
# manifest falls back to the literal rather than failing, because that is what
# Service.qml's own `pluginId` does (`manifest && manifest.id ? ... : "<lit>"`)
# and a test double -- which is what the harness is -- must not be stricter
# than the thing it stands in for any more than it may be more forgiving.
plugin_target() {
  local id
  id=$(python3 -c 'import json, sys
try:
    print(json.load(open(sys.argv[1])).get("id", ""))
except Exception:
    print("")' "$PLUGIN_ROOT/manifest.json" 2>/dev/null)
  if [[ -n $id && $id != "$PLUGIN_TARGET" ]]; then
    echo "[run.sh] $PLUGIN_ROOT/manifest.json says the plugin id is '$id', this script says '$PLUGIN_TARGET'." >&2
    echo "[run.sh] One of them is the IpcHandler target and run.sh cannot guess which; fix PLUGIN_TARGET here and shell.qml's pluginId together." >&2
    return 2
  fi
  printf '%s\n' "$PLUGIN_TARGET"
}

# The player is a setsid'd grandchild of the helper now (M2-02), so it is not
# in any process group this script owns: it is reaped by its command line,
# which names THIS scratch socket and can never match the live session's.
player_pattern() { echo "input-ipc-server=$SCRATCH/runtime/omarchy-iptv/mpv.sock"; }

reap_player() { pkill -f "$(player_pattern)" 2>/dev/null; return 0; }

cleanup() {
  [[ -n $SERVER_PID ]] && kill "$SERVER_PID" 2>/dev/null
  [[ -n $QS_PID ]] && kill "$QS_PID" 2>/dev/null
  # Belt and braces: only processes bound to THIS scratch dir are matched.
  pkill -f "quickshell -p $SCRATCH/root" 2>/dev/null
  pkill -f "$(fixture_server_pattern)" 2>/dev/null
  # --keep-player is for the restart scenario, which must outlive the shell
  # exactly the way the real player does.
  (( KEEP_PLAYER )) || reap_player
  return 0
}

# C1. Every status here used to be discarded. A failed `cp Model.js` left the
# PREVIOUS run's Model.js in the scratch root while OMARCHY_IPTV_ROOT still
# pointed Service.qml and Guide.qml at the new tree - a silently MIXED tree,
# and on the --baseline path that is rule-11 "evidence" nobody can trust.
# Nothing anywhere verified the copy matched the tree under test.
prepare_root() {
  local root; root=$(qs_root)
  mkdir -p "$root" "$SCRATCH/cache" "$SCRATCH/state" "$SCRATCH/runtime" "$SCRATCH/fixtures" \
    || die "could not create the scratch tree under $SCRATCH"
  ln -sfn "$SHELL_DIR/Commons" "$root/Commons" || die "could not link $SHELL_DIR/Commons"
  ln -sfn "$SHELL_DIR/Ui" "$root/Ui"           || die "could not link $SHELL_DIR/Ui"
  [[ -e $root/Commons && -e $root/Ui ]]        || die "the qs.Commons / qs.Ui links do not resolve"
  cp "$HERE/shell.qml" "$root/shell.qml"       || die "could not copy shell.qml into $root"
  # The harness masks form values with the plugin's own Model.js (state()).
  cp "$PLUGIN_ROOT/Model.js" "$root/Model.js"  || die "could not copy Model.js from $PLUGIN_ROOT"
  qa_same_file "$HERE/shell.qml" "$root/shell.qml" \
    || die "$root/shell.qml does not match the harness shell.qml"
  qa_same_file "$PLUGIN_ROOT/Model.js" "$root/Model.js" \
    || die "$root/Model.js does not match $PLUGIN_ROOT/Model.js: the tree under test is MIXED"
  # hyprctl and Quickshell's Hyprland bits look under $XDG_RUNTIME_DIR/hypr.
  [[ -d $REAL_RUNTIME/hypr ]] && ln -sfn "$REAL_RUNTIME/hypr" "$SCRATCH/runtime/hypr"
  return 0
}

# Start quickshell in its own session so it survives this invocation, and
# record the pid. Used by --detach and by restart-shell; the environment is
# whatever the caller exported (start writes it to last-start.env).
start_detached_shell() {
  local root; root=$(qs_root)
  setsid quickshell -p "$root" >>"$SCRATCH/harness$INSTANCE.log" 2>&1 &
  QS_PID=$!
  echo "$QS_PID" >"$(qs_pidfile)"
  echo "[run.sh] detached shell pid $QS_PID (log $SCRATCH/harness$INSTANCE.log)"
}

# SIGTERM the detached shell and wait for it to go. This is what
# `omarchy restart shell` does to the real one: `quickshell kill` asks it to
# exit, and nothing is sent to the player.
stop_detached_shell() {
  local pidfile pid i; pidfile=$(qs_pidfile)
  pid=$(cat "$pidfile" 2>/dev/null)
  [[ -n $pid ]] || pid=$(pgrep -f "quickshell -p $(qs_root)$" | head -1)
  [[ -n $pid ]] || return 0
  kill -TERM "$pid" 2>/dev/null
  for ((i = 0; i < 50; i++)); do
    kill -0 "$pid" 2>/dev/null || { rm -f "$pidfile"; return 0; }
    sleep 0.1
  done
  kill -KILL "$pid" 2>/dev/null
  rm -f "$pidfile"
  return 0
}

harness_env() {
  # The scratch runtime dir replaces XDG_RUNTIME_DIR, so hand libwayland the
  # absolute socket path (it accepts one) and keep the real DBus address.
  local wl=${WAYLAND_DISPLAY:-wayland-1}
  [[ $wl == /* ]] || wl="$REAL_RUNTIME/$wl"
  export WAYLAND_DISPLAY="$wl"
  export XDG_RUNTIME_DIR="$SCRATCH/runtime"
  export XDG_CACHE_HOME="$SCRATCH/cache"
  export XDG_STATE_HOME="$SCRATCH/state"
  # M2-05. $SCRATCH/bin goes in FRONT of PATH when a scenario has put
  # something there, which is how pip-scenario.sh hands the shell a stub
  # `hyprctl` (scripts/dev-harness/stub-hyprctl.py). That indirection is not
  # a convenience: without it the service would drive the REAL compositor and
  # float, shrink and pin windows in the user's live session. The directory
  # is created by the scenario and by nothing else, so an ordinary harness
  # run is unaffected.
  [[ -d $SCRATCH/bin ]] && export PATH="$SCRATCH/bin:$PATH"
  return 0
}

write_fixture() {
  local live=$1
  sed "s|__LIVE__|$live|g" "$HERE/fixtures/harness.m3u.in" >"$SCRATCH/fixtures/harness.m3u"
}

write_fake_epg() {
  python3 - "$SCRATCH/cache/omarchy-iptv/epg-now.json" <<'PY'
import json, os, sys, time
path = sys.argv[1]
os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
now = int(time.time())
def prog(title, start, stop):
    return {"title": title, "start": start, "stop": stop}
channels = {
    "bbc1.uk": {"now": prog("News at Six", now - 1500, now + 900), "next": prog("Regional News", now + 900, now + 1500)},
    "bbc2.uk": {"now": prog("Gardeners' World", now - 300, now + 3000), "next": prog("Newsnight", now + 3000, now + 4800)},
    "skysports.uk": {"now": prog("Premier League: Arsenal v Spurs", now - 3600, now + 2400), "next": prog("Match Replay", now + 2400, now + 6000)},
    "harness.live": {"now": prog("Test Pattern", now - 60, now + 60), "next": prog("Colour Bars", now + 60, now + 120)},
    "arte.de": {"now": prog("Karambolage", now - 200, now + 1000), "next": prog("Tracks", now + 1000, now + 2800)},
    "expired.uk": {"now": prog("Already Over", now - 7200, now - 3600), "next": prog("Something Later", now + 100, now + 200)},
}
json.dump({"version": 1, "generatedAt": now, "validUntil": now + 300, "sourceHost": "harness", "channels": channels}, open(path, "w"))
os.chmod(path, 0o600)
PY
}

start_server() {
  local video="$SCRATCH/fixtures/test.ts"
  if [[ ! -f $video ]]; then
    echo "[run.sh] generating test video with ffmpeg (lavfi testsrc, 120 s)"
    ffmpeg -loglevel error -y -f lavfi -i "testsrc=size=320x240:rate=15" -f lavfi -i "sine=frequency=440:sample_rate=22050" \
      -t 120 -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 32k -f mpegts "$video" || { echo "[run.sh] ffmpeg failed"; exit 1; }
  fi
  # A previous run killed with SIGKILL could not clean up: reap its server.
  pkill -f "$(fixture_server_pattern)" 2>/dev/null && sleep 0.2
  python3 -m http.server "$SERVE_PORT" --bind 127.0.0.1 --directory "$SCRATCH/fixtures" >/dev/null 2>&1 &
  SERVER_PID=$!
  echo "[run.sh] serving $SCRATCH/fixtures on http://127.0.0.1:$SERVE_PORT (pid $SERVER_PID)"
}

# ---- F-M3-1 half (a). Nothing sends a keystroke without first proving where
# it will land. Both checks below guard `key` and `type`.

# Is the screen locked? Checked before EVERY keystroke and never escapable:
# CLAUDE.md's parallel rule 6 says a key typed at a lock prompt registers as a
# failed unlock attempt, and until now that rule was prose each scenario author
# had to remember -- text-scenario.sh:208 did it, every other scenario did not.
# A rule joined to its callers by nothing is the F-HARNESS-1 and F-RWD-14
# shape, and the repair is the same one: handle it HERE, once.
#
# `-x` matches the process NAME, and nothing else. `-f` matches any command
# line that merely MENTIONS the name, which CLAUDE.md rule 3 records has bitten
# this project three times, once in a brief that was quoting the rule. Measured
# here: with `-f` in place of `-x`, and nothing locked at all, `key` refused --
# the match was an ancestor shell whose own command line contained the word
# `hyprlock`. A check that can refuse every keystroke forever because of what
# some parent process is called is not a check.
screen_locked() { pgrep -x hyprlock >/dev/null 2>&1; }

# How long to wait for the harness to say where the keyboard is. BOUNDED,
# because an unbounded wait is a bug and not patience (rule 3): `qs ipc`
# against an instance that is simply not there fails fast, but a half-dead one
# need not, and the answer to "I cannot tell" is to refuse and say so.
FOCUS_TIMEOUT=${OMARCHY_IPTV_FOCUS_TIMEOUT:-5}

# Refuse unless the harness guide holds the keyboard, naming what was found so
# an operator can tell "the guide is closed" from "another surface has it".
#
# The question goes to the harness over the SAME path `type` already uses for
# numberState, so it reaches the same instance: `ipc` resolves the config root
# from $INSTANCE, which for these verbs comes from the environment
# (OMARCHY_IPTV_HARNESS_INSTANCE) and is inherited by this child.
#
# ONLY the environment variable. `--instance` is a `start` option and is parsed
# nowhere else, so `run.sh --instance 2 key j` is a usage error ("unknown
# option: key", exit 2) and `run.sh key --instance 2 j` passes the flag to
# wtype as TEXT to be typed. That is deliberate, not an oversight: everything
# after `key` belongs to wtype, so a flag of ours there would be ambiguous
# with the argv the caller wants delivered. Routing a second instance is
# `OMARCHY_IPTV_HARNESS_INSTANCE=2 run.sh key j` -- the form
# player-scenario.sh already uses for its second instance's OTHER verbs
# (`ipc2`, `shell-stop`, the `--detach` start); no scenario sends a key to a
# second instance today. An earlier version of this comment said a second
# `--instance` root was "asked about itself", which read as if the flag
# reached these verbs at all; measured all three forms and only the variable
# routes. scripts/qa-lib-test.sh drives them.
#
# The reply is URL-free by construction (booleans, counts, two type tokens),
# so echoing it into the terminal cannot leak a playlist URL (rule 5).
#
# Fails CLOSED. Any answer that is not a readable "yes" refuses, because the
# whole point is that a keystroke into an unknown surface is invisible.
require_guide_focus() {
  local what=$1 reply status verdict diag errfile
  # The two streams are kept APART, and this is the whole finding of the first
  # review of this guard. `2>&1` here fed any diagnostic `qs` wrote on stderr
  # into json.loads, and the guard fails closed, so ONE stray line turned every
  # key and type into exit 3 -- invisibly, because all eleven call sites are
  # `>/dev/null 2>&1` with the status dropped, so the scenario would simply
  # score lower with no cause on screen. That `qs ipc` is noisy in practice is
  # not a guess: twelve scenario wrappers add `2>/dev/null` to it, and the
  # sibling read in the `type` verb below does the same. The diagnostic is still
  # SHOWN on a failure, which `2>/dev/null` alone would have thrown away; it is
  # only kept out of the parser.
  errfile=$(mktemp "${TMPDIR:-/tmp}/omarchy-iptv-focus.XXXXXX") || {
    echo "[run.sh] $what REFUSED: cannot make a temp file to read the harness reply" >&2
    return 1
  }
  reply=$(timeout "$FOCUS_TIMEOUT" "$0" ipc focusState 2>"$errfile")
  status=$?
  diag=$(tr '\n' ' ' <"$errfile")
  rm -f "$errfile"
  if (( status == 124 )); then
    echo "[run.sh] $what REFUSED: the harness did not answer focusState within ${FOCUS_TIMEOUT}s -- giving up rather than typing blind${diag:+ (stderr: $diag)}" >&2
    return 1
  fi
  if (( status != 0 )); then
    echo "[run.sh] $what REFUSED: cannot ask the harness where the keyboard is (qs ipc exit $status): ${diag:-${reply//$'\n'/ }}" >&2
    echo "[run.sh] if no harness is running, start one (run.sh --detach --open); if a harness from BEFORE this change is still up it has no focusState verb, so reap and restart it (run.sh reap)" >&2
    echo "[run.sh] if this key is meant for the COMPOSITOR rather than the guide, pass --to-compositor" >&2
    return 1
  fi
  verdict=$(python3 - "$reply" <<'PY'
import json, sys
raw = sys.argv[1]
try:
    d = json.loads(raw)
except Exception:
    print("no the harness reply was not JSON: " + " ".join(raw.split())[:200])
    sys.exit(0)
if not isinstance(d, dict):
    print("no the harness reply was not a JSON object")
    sys.exit(0)
if not d.get("ok"):
    print("no the harness has loaded no guide (error=%s)" % (d.get("error"),))
    sys.exit(0)
where = ("window=%s open=%s keyboard=%s role=%s item=%s blocked=%s scanned=%s exhausted=%s"
         % (d.get("window"), d.get("open"), d.get("keyboard"), d.get("role"),
            d.get("item"), d.get("blocked"), d.get("scanned"), d.get("exhausted")))
if not d.get("open"):
    print("no the guide is CLOSED, so a key would land in whatever is behind it; " + where)
elif d.get("exhausted") and not d.get("keyboard"):
    print("no the focus walk gave up before it found a focused item, so I cannot tell; " + where)
elif not d.get("keyboard"):
    print("no the guide is open but ANOTHER SURFACE holds the keyboard; " + where)
else:
    print("yes " + where)
PY
)
  if [[ -z $verdict ]]; then
    echo "[run.sh] $what REFUSED: could not read the harness focus reply at all (python3 produced nothing)" >&2
    return 1
  fi
  [[ ${verdict%% *} == yes ]] && return 0
  echo "[run.sh] $what REFUSED: ${verdict#* }" >&2
  echo "[run.sh] pass --to-compositor ONLY if this key is meant for the compositor rather than the guide" >&2
  return 1
}

# The lock refusal, shared by both verbs so the message cannot drift.
refuse_if_locked() {
  screen_locked || return 0
  echo "[run.sh] $1 REFUSED: hyprlock is running. A keystroke now registers as a FAILED UNLOCK ATTEMPT (CLAUDE.md parallel rule 6), so this refusal has no escape hatch." >&2
  return 1
}

cmd=${1:-start}
case $cmd in
  ipc)
    shift
    harness_env
    exec qs ipc -p "$(qs_root)" call harness "$@"
    ;;
  plugin-ipc)
    # F-RWD-14. Identical to `ipc` except the target, which is the plugin's own
    # rather than the harness's. The environment is harness_env's, which is the
    # measured form (SPIKE-LIVE-REWIND 12.5): the scratch runtime directory
    # alone gets "No running instances ... present on the current display",
    # because run.sh hands the shell the ABSOLUTE socket path.
    #
    # It can only ever reach the harness, never the user's live shell: the
    # config root is this scratch root, and the spike measured that the live
    # instance answers the same target name under /usr/share/omarchy/shell.
    #
    # The empty call is refused HERE rather than by `qs`, so a scenario that
    # drops its argument is told what it dropped without needing quickshell
    # installed to find out. Everything past the function name is passed
    # through untouched.
    shift
    (( $# > 0 )) || die "plugin-ipc needs a function name (e.g. plugin-ipc status)"
    if ! target=$(plugin_target); then exit 2; fi
    harness_env
    exec qs ipc -p "$(qs_root)" call "$target" "$@"
    ;;
  shot)
    name=${2:-guide}
    out=$(hyprctl monitors -j | python3 -c 'import json,sys; ms=json.load(sys.stdin); print(next((m["name"] for m in ms if m.get("focused")), ms[0]["name"]))')
    mkdir -p "$SCRATCH/shots"
    grim -o "$out" "$SCRATCH/shots/$name.png" && echo "$SCRATCH/shots/$name.png"
    ;;
  key)
    shift
    # F-M3-1 half (a), the escape hatch. It must come FIRST: everything after
    # it belongs to wtype, and wtype's own `--` means "the rest is text", so a
    # flag of ours appearing later is text the caller asked to TYPE.
    TO_COMPOSITOR=0
    while (( $# > 0 )) && [[ $1 == --to-compositor ]]; do TO_COMPOSITOR=1; shift; done
    (( $# > 0 )) || die "key needs at least one wtype argument (e.g. key j, key -k Escape)"
    # (1) The lock prompt, first and not escapable.
    refuse_if_locked key || exit 3
    # (2) Where the keyboard is. This runs BEFORE the shift primer below,
    # because the primer is ITSELF a keystroke: a guard that ran after it would
    # already have typed into the wrong surface before deciding not to.
    if (( TO_COMPOSITOR )); then
      echo "[run.sh] key --to-compositor: focus guard SKIPPED; this chord goes to whatever holds the keyboard, guide or not" >&2
    else
      require_guide_focus key || exit 3
    fi
    # F-HARNESS-1. The FIRST wtype keystroke into a fresh shell is
    # intermittently swallowed -- 1 fresh shell in 4 during verification, where
    # `sky` arrived as `ky`. A row-count assertion cannot tell the two apart
    # (both filter 20 rows to 3), so the loss reads as a pass.
    #
    # The board's rule for this was prose every scenario author had to remember
    # and apply, which is a rule joined to its callers by nothing. It is handled
    # HERE instead, once, so a scenario cannot get it wrong by forgetting.
    #
    # The primer is a Shift press and release with no other key: it reaches the
    # surface, so whatever is not ready yet becomes ready, and it cannot change
    # any state in the guide. It runs once per shell, keyed to the pid file that
    # `start` rewrites, so a fresh shell primes again and a long scenario does
    # not pay for it on every keystroke.
    #
    # --to-compositor skips it, and that is the point rather than an
    # optimisation. The hatch exists for a chord aimed at whatever holds the
    # keyboard, which is by definition NOT the guide's fresh surface; firing
    # the primer there sent a Shift into a foreign surface and -- worse --
    # recorded the shell as primed, so the next legitimate key into the GUIDE
    # skipped priming and could be the one that gets swallowed. The
    # compensation was spent without ever having reached the surface it
    # compensates for, which reopens F-HARNESS-1. Found by the first review of
    # this guard; scripts/qa-lib-test.sh drives the sequence.
    primed="$SCRATCH/primed$INSTANCE"
    if (( ! TO_COMPOSITOR )) \
       && [[ ! -f $primed || $(cat "$primed" 2>/dev/null) != $(cat "$(qs_pidfile)" 2>/dev/null) ]]; then
      wtype -M shift -m shift 2>/dev/null || true
      cat "$(qs_pidfile)" 2>/dev/null >"$primed" || true
    fi
    exec wtype "$@"
    ;;
  type)
    # F-HARNESS-1, the other half. Types TEXT and then proves it arrived, by
    # reading the query back over IPC rather than counting rows. One retry: the
    # loss is a first-keystroke race, so a reset and a resend clears it, and a
    # second failure is a real defect that must not be retried into silence.
    shift
    want=${1:-}
    if [[ -z $want ]]; then echo "[run.sh] type needs text" >&2; exit 2; fi
    # F-M3-1 half (a). The same two refusals as `key`, and up FRONT: without
    # them `type` enters its retry loop, sends the text TWICE into whatever
    # surface has the keyboard, and then reports a two-attempt failure whose
    # own message says "this is not the first-keystroke race" -- which is true,
    # and still the wrong diagnosis. There is no --to-compositor here: `type`
    # proves the text reached the GUIDE by reading it back, so a chord aimed at
    # the compositor has nothing for it to prove.
    #
    # `"$0" key` below checks again, once per attempt. That is deliberate: the
    # second check catches focus stolen in between -- and its VERDICT is now
    # what `type` ends on. The inner refusal used to be dropped on the loop
    # body, so a steal after the front check fell through to the two-attempt
    # message that this very comment calls the wrong diagnosis, and exited 1
    # rather than 3. A scenario grading `exit 3` as "refused" could not see a
    # focus refusal at all. Found by the first review of this guard.
    #
    # Exit 3 lands on the FIRST inner refusal rather than after a retry: the
    # inner `key` has already said on stderr which of the two refusals it was,
    # a 0.25 s wait does not give the keyboard back, and a second refusal only
    # buries the first. Nothing was typed either way, which is what exit 3
    # means here.
    refuse_if_locked type || exit 3
    require_guide_focus type || exit 3
    for attempt in 1 2; do
      "$0" key -- "$want"
      kstatus=$?
      if (( kstatus == 3 )); then
        echo "[run.sh] type REFUSED on attempt $attempt: the guard refused the keystroke (see the line above); nothing was typed" >&2
        exit 3
      fi
      sleep 0.25
      got=$("$0" ipc numberState 2>/dev/null | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("queryLive",""))
except Exception: print("<unreadable>")' | tr -d '\n')
      if [[ $got == "$want" ]]; then
        echo "[run.sh] typed '$want' (attempt $attempt)"
        exit 0
      fi
      echo "[run.sh] type: sent '$want', surface holds '$got' -- resetting and retrying" >&2
      "$0" ipc query "" >/dev/null 2>&1 || true
      sleep 0.15
    done
    echo "[run.sh] type FAILED: '$want' did not arrive after two attempts; this is not the first-keystroke race" >&2
    exit 1
    ;;
  clean)
    rm -rf "$SCRATCH/cache" "$SCRATCH/state" "$SCRATCH/runtime/omarchy-iptv" "$SCRATCH/shots"
    echo "[run.sh] cleaned $SCRATCH"
    ;;
  scenario)
    shift
    exec "$HERE/sources-scenario.sh" "$@"
    ;;
  player-scenario)
    shift
    exec "$HERE/player-scenario.sh" "$@"
    ;;
  shell-stop)
    stop_detached_shell
    echo "[run.sh] shell$INSTANCE stopped"
    ;;
  restart-shell)
    # The M2-02 acceptance shape: the shell goes away and comes back with the
    # same environment, and NOTHING touches the player. A detached start
    # (--detach) must have written last-start.env.
    if [[ ! -f $SCRATCH/last-start.env ]]; then
      echo "[run.sh] no detached start recorded; use --detach first" >&2
      exit 2
    fi
    stop_detached_shell
    harness_env
    # shellcheck source=/dev/null
    . "$SCRATCH/last-start.env"
    # C2 (iii): come back to the tree --detach recorded, not to whatever this
    # terminal happens to export. Then assert the two agree, because a
    # disagreement is the mixed tree C1 guards the other half of.
    if [[ -n ${OMARCHY_IPTV_PLUGIN_ROOT:-} ]]; then
      PLUGIN_ROOT=$(cd "$OMARCHY_IPTV_PLUGIN_ROOT" 2>/dev/null && pwd) \
        || die "the recorded plugin tree $OMARCHY_IPTV_PLUGIN_ROOT is gone"
    fi
    [[ "$PLUGIN_ROOT" == "${OMARCHY_IPTV_ROOT:-$PLUGIN_ROOT}" ]] \
      || die "restart-shell would mix trees: Model.js from $PLUGIN_ROOT, QML from $OMARCHY_IPTV_ROOT"
    prepare_root
    start_detached_shell
    ;;
  reap)
    stop_detached_shell
    pkill -f "quickshell -p $SCRATCH/root" 2>/dev/null
    pkill -f "$(fixture_server_pattern)" 2>/dev/null
    reap_player
    echo "[run.sh] reaped shell, fixture server and player for $SCRATCH"
    ;;
  start|--*)
    [[ $cmd == start ]] && shift
    OPEN=0 TIMEOUT=15 PLAYLIST="" EPG="" SOURCE2="" SERVE=0 FAKE_EPG=0 VERTICAL=0 SHOW_NAME=true LABEL_MAX=180 KEEP=0 DETACH=0
    ORDER=playlist ENTRY_MS=2000 BAR_NUMBER=true WINDOW=layer
    while (($# > 0)); do
      case $1 in
        --open) OPEN=1 ;;
        --timeout) TIMEOUT=$2; shift ;;
        --playlist) PLAYLIST=$2; shift ;;
        --epg) EPG=$2; shift ;;
        --source2) SOURCE2=$2; shift ;;
        --serve) SERVE=1 ;;
        --fake-epg) FAKE_EPG=1 ;;
        --vertical) VERTICAL=1 ;;
        --no-name) SHOW_NAME=false ;;
        --label-max) LABEL_MAX=$2; shift ;;
        # Rejected here rather than in QML: channelOrder is deliberately
        # forgiving at runtime (an unreadable value means "playlist"), which
        # would turn a typo in a scenario into a silent pass.
        --order) ORDER=$2; shift
                 [[ $ORDER == playlist || $ORDER == number ]] || die "--order takes playlist or number, not '$ORDER'" ;;
        --entry-ms) ENTRY_MS=$2; shift
                 [[ $ENTRY_MS =~ ^[0-9]+$ ]] || die "--entry-ms takes an integer, not '$ENTRY_MS'"
                 (( ENTRY_MS >= 400 && ENTRY_MS <= 5000 )) || die "--entry-ms is 400..5000 (manifest range), got $ENTRY_MS" ;;
        --no-bar-number) BAR_NUMBER=false ;;
        --keep) KEEP=1 ;;
        --keep-player) KEEP_PLAYER=1 ;;
        --detach) DETACH=1; KEEP_PLAYER=1 ;;
        --instance) INSTANCE=$2; shift ;;
        # Harness-only: which window hosts the guide. Rejected here for the
        # same reason as --order: shell.qml compares the string, so a typo
        # would silently run the production window under a compositor that
        # cannot map it and every pixel check after it would be vacuous.
        --window) WINDOW=$2; shift
                 [[ $WINDOW == layer || $WINDOW == floating ]] || die "--window takes layer or floating, not '$WINDOW'" ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
      esac
      shift
    done
    prepare_root
    if (( ! KEEP )); then rm -rf "$SCRATCH/cache" "$SCRATCH/state" "$SCRATCH/runtime/omarchy-iptv"; mkdir -p "$SCRATCH/cache" "$SCRATCH/state"; fi
    # Always reap what we start: normal exit, --timeout, Ctrl-C, SIGTERM.
    # --detach deliberately installs no trap: the shell and the player must
    # outlive this invocation (that is the state `restart-shell` acts on),
    # and `run.sh reap` is then the teardown.
    if (( ! DETACH )); then
      trap cleanup EXIT
      trap 'exit 130' INT
      trap 'exit 143' TERM
    fi
    live="http://127.0.0.1:9/dead/live.m3u8"
    if (( SERVE )); then start_server; live="http://127.0.0.1:$SERVE_PORT/test.ts"; fi
    write_fixture "$live"
    (( FAKE_EPG )) && write_fake_epg
    harness_env
    if [[ -n $SOURCE2 ]]; then
      # A second history record, never fetched (fetchedAt 0): the switch
      # path through a probe. Output is the helper's, hosts only.
      seeded=$(python3 "$PLUGIN_ROOT/bin/omarchy-iptv" state --state-dir "$SCRATCH/state/omarchy-iptv" source add --url "$SOURCE2" --origin cli)
      echo "[run.sh] source2=$(source_label "$SOURCE2") key=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("key", "?"))' "$seeded")"
    fi
    export OMARCHY_IPTV_ROOT="$PLUGIN_ROOT"
    if [[ $PLAYLIST == none ]]; then export OMARCHY_IPTV_PLAYLIST=""
    else export OMARCHY_IPTV_PLAYLIST="${PLAYLIST:-$SCRATCH/fixtures/harness.m3u}"; fi
    export OMARCHY_IPTV_EPG="$EPG"
    export OMARCHY_IPTV_OPEN="$OPEN"
    export OMARCHY_IPTV_VERTICAL="$VERTICAL"
    export OMARCHY_IPTV_SHOW_NAME="$SHOW_NAME"
    export OMARCHY_IPTV_LABEL_MAX="$LABEL_MAX"
    export OMARCHY_IPTV_ORDER="$ORDER"
    export OMARCHY_IPTV_ENTRY_MS="$ENTRY_MS"
    export OMARCHY_IPTV_BAR_NUMBER="$BAR_NUMBER"
    export OMARCHY_IPTV_HARNESS_WINDOW="$WINDOW"
    # scheme://host only: the URL may carry provider credentials (S-08).
    echo "[run.sh] scratch=$SCRATCH timeout=${TIMEOUT}s window=$WINDOW playlist=$(source_label "$OMARCHY_IPTV_PLAYLIST") epg=$(source_label "$OMARCHY_IPTV_EPG")"
    if (( DETACH )); then
      # Record the environment so `restart-shell` can bring the same shell
      # back without re-deriving anything (the fixture server, the cache and
      # the state stay exactly as they are).
      # C2 (i): these were hand-quoted with \"$VALUE\", so a path carrying a
      # $, a backquote, a backslash or a double quote was re-expanded - or
      # EXECUTED - when restart-shell sourced the file. printf %q round-trips.
      # (ii) OMARCHY_IPTV_PLUGIN_ROOT was NOT recorded, while restart-shell
      # sources this file and then calls prepare_root, which copies Model.js
      # from $PLUGIN_ROOT computed from the CALLER's environment. A
      # `run.sh restart-shell` from a plain terminal after a baseline
      # --detach therefore copied the CURRENT repo's Model.js over the
      # baseline's while Service.qml stayed at the baseline.
      {
        qa_env_line OMARCHY_IPTV_PLUGIN_ROOT "$PLUGIN_ROOT"
        qa_env_line OMARCHY_IPTV_ROOT        "$OMARCHY_IPTV_ROOT"
        qa_env_line OMARCHY_IPTV_PLAYLIST    "$OMARCHY_IPTV_PLAYLIST"
        qa_env_line OMARCHY_IPTV_EPG         "$OMARCHY_IPTV_EPG"
        qa_env_line OMARCHY_IPTV_OPEN        "0"
        qa_env_line OMARCHY_IPTV_VERTICAL    "$OMARCHY_IPTV_VERTICAL"
        qa_env_line OMARCHY_IPTV_SHOW_NAME   "$OMARCHY_IPTV_SHOW_NAME"
        qa_env_line OMARCHY_IPTV_LABEL_MAX   "$OMARCHY_IPTV_LABEL_MAX"
        qa_env_line OMARCHY_IPTV_ORDER       "$OMARCHY_IPTV_ORDER"
        qa_env_line OMARCHY_IPTV_ENTRY_MS    "$OMARCHY_IPTV_ENTRY_MS"
        qa_env_line OMARCHY_IPTV_BAR_NUMBER  "$OMARCHY_IPTV_BAR_NUMBER"
        qa_env_line OMARCHY_IPTV_HARNESS_WINDOW "$OMARCHY_IPTV_HARNESS_WINDOW"
        qa_env_line OMARCHY_IPTV_MPV_ARGS    "${OMARCHY_IPTV_MPV_ARGS:-}"
      } >"$SCRATCH/last-start.env"
      start_detached_shell
      exit 0
    fi
    # Background + wait (instead of a pipeline) so the PID is known to cleanup.
    if (( TIMEOUT > 0 )); then
      timeout --signal=TERM --kill-after=3 "$TIMEOUT" quickshell -p "$(qs_root)" > >(sed -u 's/^/[qs] /') 2>&1 &
    else
      quickshell -p "$(qs_root)" > >(sed -u 's/^/[qs] /') 2>&1 &
    fi
    QS_PID=$!
    wait "$QS_PID"
    status=$?
    QS_PID=""
    echo "[run.sh] quickshell exited with $status (124 = timeout, expected)"
    ;;
  *)
    # The whole leading comment block, SCANNED rather than counted. A line
    # range here is a magic number joined to the header by nothing, and the
    # comment that used to sit here asked a human to keep it in step -- which
    # had already failed: `2,51p` stopped inside the scratch-layout list, eight
    # lines short, so the usage had silently stopped naming `runtime/`,
    # `fixtures/`, the 127.0.0.1 rule and what gets reaped. awk stops at the
    # first line that is not a comment, so a new option or paragraph is listed
    # by existing rather than by being counted.
    awk 'NR == 1 { next } /^#/ { print; next } { exit }' "$0"
    exit 2
    ;;
esac
