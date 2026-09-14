#!/bin/bash
# scripts/dev-harness/run.sh -- smoke-test the plugin without installing it.
#
#   run.sh [options]                 start the harness (foreground, killed after --timeout)
#   run.sh ipc <fn> [args...]        call the running harness (IpcHandler target "harness")
#   run.sh shot [name]               screenshot the focused output into the scratch dir
#   run.sh key <wtype args...>       send keys to the focused surface (wtype)
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
#   --keep              keep the scratch cache/state between runs (default wipes cache+state)
#   --detach            start in the background and return (no EXIT trap): the shell survives
#                       this invocation, which is what `restart-shell` needs. Reap with `reap`.
#   --instance NAME     a second config root (root<NAME>) sharing the same cache / state /
#                       runtime dirs: two services, one runtime directory, one player
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

cmd=${1:-start}
case $cmd in
  ipc)
    shift
    harness_env
    exec qs ipc -p "$(qs_root)" call harness "$@"
    ;;
  shot)
    name=${2:-guide}
    out=$(hyprctl monitors -j | python3 -c 'import json,sys; ms=json.load(sys.stdin); print(next((m["name"] for m in ms if m.get("focused")), ms[0]["name"]))')
    mkdir -p "$SCRATCH/shots"
    grim -o "$out" "$SCRATCH/shots/$name.png" && echo "$SCRATCH/shots/$name.png"
    ;;
  key)
    shift
    exec wtype "$@"
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
        --keep) KEEP=1 ;;
        --keep-player) KEEP_PLAYER=1 ;;
        --detach) DETACH=1; KEEP_PLAYER=1 ;;
        --instance) INSTANCE=$2; shift ;;
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
    # scheme://host only: the URL may carry provider credentials (S-08).
    echo "[run.sh] scratch=$SCRATCH timeout=${TIMEOUT}s playlist=$(source_label "$OMARCHY_IPTV_PLAYLIST") epg=$(source_label "$OMARCHY_IPTV_EPG")"
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
    sed -n '2,45p' "$0"
    exit 2
    ;;
esac
