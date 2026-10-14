#!/bin/bash
# scripts/dev-harness/private-bus.sh -- run one command on a PRIVATE session
# D-Bus that can activate nothing (CLAUDE.md, working in parallel 6b).
#
#   private-bus.sh DIR SECONDS CMD [ARGS...]
#
# DIR is a short directory this script creates (0700) for the bus config and
# socket and removes afterwards; it must not exist yet. SECONDS bounds CMD
# (timeout -k 5): an unbounded run is a bug (rule 3). CMD inherits the
# environment with DBUS_SESSION_BUS_ADDRESS pointing at the private bus and
# the accessibility bus variables removed.
#
# Why this exists. A nested cage started under plain `dbus-run-session` gets
# the STANDARD service directories, so D-Bus activation starts desktop
# portals inside the nested session: on 2026-10-13 a lane's throwaway rig
# crashed two portal instances that way and the user's real
# xdg-document-portal.service exited with status 21 (F-M3-21). The config
# below is tests/a11y/run_private_bus.py's shape: a session bus with a
# listen address and an allow-all policy and NO <servicedir>,
# <standard_session_servicedirs/> or <includedir>, so nothing on it can be
# activated. The round-12 lanes' copy of this lived in /tmp and was lost in
# the 20:17 reboot; this one is committed.
#
# The daemon is started --nofork, its pid is the one Bash recorded for the
# process it started (no setsid wrapper), and it is killed by that pid on
# every exit, INT and TERM included. Nothing is matched by pattern.
#
# F-HARNESS-25 (round 13): CMD also gets a HOME of its own. The first version
# passed the caller's HOME and XDG directories through, so the committed
# filewatch spike's cage and quickshell wrote a mesa shader cache and
# fcitx/dbus into the developer's real ~/.cache and ~/.config (content-free,
# but CLAUDE.md makes those directories read-only for repo work). HOME,
# XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_CACHE_HOME and XDG_STATE_HOME now point
# inside DIR/home, which goes with DIR at exit; MPV_HOME and XCOMPOSEFILE are
# dropped. XDG_RUNTIME_DIR is left alone: the nested compositor's socket and
# the quickshell instance registry live there, and it is not a home.
# tests/test_harness_home.py runs this script with a probe and observes it.
set -u
if (( $# < 3 )); then
  echo "usage: private-bus.sh DIR SECONDS CMD [ARGS...]" >&2
  exit 2
fi
DIR=$1 SECS=$2
shift 2
if [[ -e $DIR ]]; then
  echo "private-bus.sh: $DIR exists; refusing to reuse it" >&2
  exit 2
fi
mkdir -m 700 -p "$DIR" || exit 2
BUS_PID=""
cleanup() {
  local i
  if [[ -n $BUS_PID ]] && kill -0 "$BUS_PID" 2>/dev/null; then
    kill -TERM "$BUS_PID" 2>/dev/null
    for ((i = 0; i < 50; i++)); do kill -0 "$BUS_PID" 2>/dev/null || break; sleep 0.1; done
    kill -0 "$BUS_PID" 2>/dev/null && kill -KILL "$BUS_PID" 2>/dev/null
    wait "$BUS_PID" 2>/dev/null
  fi
  rm -rf -- "$DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cat >"$DIR/bus.conf" <<CONF
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:dir=$DIR</listen>
  <policy context="default">
    <allow send_destination="*" eavesdrop="true"/>
    <allow eavesdrop="true"/>
    <allow own="*"/>
  </policy>
</busconfig>
CONF
if grep -Eq 'servicedir|includedir' "$DIR/bus.conf"; then
  echo "private-bus.sh: the bus config names a service directory; refusing" >&2
  exit 2
fi
/usr/bin/dbus-daemon --config-file "$DIR/bus.conf" --nofork --print-address=3 3>"$DIR/address" &
BUS_PID=$!
for ((i = 0; i < 50; i++)); do [[ -s $DIR/address ]] && break; sleep 0.1; done
ADDR=$(head -n 1 "$DIR/address" 2>/dev/null)
if [[ -z $ADDR ]]; then
  echo "private-bus.sh: dbus-daemon printed no address within 5 s" >&2
  exit 2
fi
echo "private-bus.sh: bus pid $BUS_PID at $ADDR" >&2
HOME_DIR=$DIR/home
mkdir -m 700 -p "$HOME_DIR/.config" "$HOME_DIR/.local/share" "$HOME_DIR/.cache" "$HOME_DIR/.local/state" || exit 2
env -u AT_SPI_BUS_ADDRESS -u QT_LINUX_ACCESSIBILITY_ALWAYS_ON -u MPV_HOME -u XCOMPOSEFILE \
  DBUS_SESSION_BUS_ADDRESS="$ADDR" HOME="$HOME_DIR" XDG_CONFIG_HOME="$HOME_DIR/.config" \
  XDG_DATA_HOME="$HOME_DIR/.local/share" XDG_CACHE_HOME="$HOME_DIR/.cache" XDG_STATE_HOME="$HOME_DIR/.local/state" \
  timeout -k 5 "$SECS" "$@"
status=$?
exit "$status"
