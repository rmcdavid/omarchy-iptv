#!/bin/bash
# scripts/dev-harness/run.sh -- smoke-test the plugin without installing it.
#
#   run.sh [options]                 start the harness (foreground, killed after --timeout)
#   run.sh ipc <fn> [args...]        call the running harness (IpcHandler target "harness")
#   run.sh shot [name]               screenshot the focused output into the scratch dir
#   run.sh key <wtype args...>       send keys to the focused surface (wtype)
#   run.sh clean                     wipe the scratch dirs (cache, state, runtime)
#
# Options for start:
#   --open              open the guide right after load
#   --timeout N         kill quickshell after N seconds (default 15; 0 = no limit)
#   --playlist SRC      playlist URL/path (default: generated fixture with dead local URLs; "none" = unconfigured)
#   --epg URL           EPG URL (default: none)
#   --serve             serve a generated test video on 127.0.0.1:8765 and point the
#                       fixture's "Harness Live" channel at it (exercises the mpv path locally)
#   --fake-epg          drop a synthetic epg-now.json into the scratch cache (guide EPG rows)
#   --vertical          fake a vertical bar
#   --no-name           showChannelName=false
#   --label-max N       barLabelMaxWidth
#   --keep              keep the scratch cache/state between runs (default wipes cache+state)
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
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
SHELL_DIR=${OMARCHY_PATH:-/usr/share/omarchy}/shell
SERVE_PORT=8765
SERVER_PID=""
QS_PID=""

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

cleanup() {
  [[ -n $SERVER_PID ]] && kill "$SERVER_PID" 2>/dev/null
  [[ -n $QS_PID ]] && kill "$QS_PID" 2>/dev/null
  # Belt and braces: only processes bound to THIS scratch dir are matched.
  pkill -f "quickshell -p $SCRATCH/root" 2>/dev/null
  pkill -f "$(fixture_server_pattern)" 2>/dev/null
  pkill -f "input-ipc-server=$SCRATCH/runtime/omarchy-iptv/mpv.sock" 2>/dev/null
  return 0
}

prepare_root() {
  mkdir -p "$SCRATCH/root" "$SCRATCH/cache" "$SCRATCH/state" "$SCRATCH/runtime" "$SCRATCH/fixtures"
  ln -sfn "$SHELL_DIR/Commons" "$SCRATCH/root/Commons"
  ln -sfn "$SHELL_DIR/Ui" "$SCRATCH/root/Ui"
  cp "$HERE/shell.qml" "$SCRATCH/root/shell.qml"
  # hyprctl and Quickshell's Hyprland bits look under $XDG_RUNTIME_DIR/hypr.
  [[ -d $REAL_RUNTIME/hypr ]] && ln -sfn "$REAL_RUNTIME/hypr" "$SCRATCH/runtime/hypr"
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
    exec qs ipc -p "$SCRATCH/root" call harness "$@"
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
  start|--*)
    [[ $cmd == start ]] && shift
    OPEN=0 TIMEOUT=15 PLAYLIST="" EPG="" SERVE=0 FAKE_EPG=0 VERTICAL=0 SHOW_NAME=true LABEL_MAX=180 KEEP=0
    while (($# > 0)); do
      case $1 in
        --open) OPEN=1 ;;
        --timeout) TIMEOUT=$2; shift ;;
        --playlist) PLAYLIST=$2; shift ;;
        --epg) EPG=$2; shift ;;
        --serve) SERVE=1 ;;
        --fake-epg) FAKE_EPG=1 ;;
        --vertical) VERTICAL=1 ;;
        --no-name) SHOW_NAME=false ;;
        --label-max) LABEL_MAX=$2; shift ;;
        --keep) KEEP=1 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
      esac
      shift
    done
    prepare_root
    if (( ! KEEP )); then rm -rf "$SCRATCH/cache" "$SCRATCH/state" "$SCRATCH/runtime/omarchy-iptv"; mkdir -p "$SCRATCH/cache" "$SCRATCH/state"; fi
    # Always reap what we start: normal exit, --timeout, Ctrl-C, SIGTERM.
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    live="http://127.0.0.1:9/dead/live.m3u8"
    if (( SERVE )); then start_server; live="http://127.0.0.1:$SERVE_PORT/test.ts"; fi
    write_fixture "$live"
    (( FAKE_EPG )) && write_fake_epg
    harness_env
    export OMARCHY_IPTV_ROOT="$ROOT"
    if [[ $PLAYLIST == none ]]; then export OMARCHY_IPTV_PLAYLIST=""
    else export OMARCHY_IPTV_PLAYLIST="${PLAYLIST:-$SCRATCH/fixtures/harness.m3u}"; fi
    export OMARCHY_IPTV_EPG="$EPG"
    export OMARCHY_IPTV_OPEN="$OPEN"
    export OMARCHY_IPTV_VERTICAL="$VERTICAL"
    export OMARCHY_IPTV_SHOW_NAME="$SHOW_NAME"
    export OMARCHY_IPTV_LABEL_MAX="$LABEL_MAX"
    # scheme://host only: the URL may carry provider credentials (S-08).
    echo "[run.sh] scratch=$SCRATCH timeout=${TIMEOUT}s playlist=$(source_label "$OMARCHY_IPTV_PLAYLIST") epg=$(source_label "$OMARCHY_IPTV_EPG")"
    # Background + wait (instead of a pipeline) so the PID is known to cleanup.
    if (( TIMEOUT > 0 )); then
      timeout --signal=TERM --kill-after=3 "$TIMEOUT" quickshell -p "$SCRATCH/root" > >(sed -u 's/^/[qs] /') 2>&1 &
    else
      quickshell -p "$SCRATCH/root" > >(sed -u 's/^/[qs] /') 2>&1 &
    fi
    QS_PID=$!
    wait "$QS_PID"
    status=$?
    QS_PID=""
    echo "[run.sh] quickshell exited with $status (124 = timeout, expected)"
    ;;
  *)
    sed -n '2,30p' "$0"
    exit 2
    ;;
esac
