# scripts/dev-harness/spikes/codebehind-calllater/gdbrun.sh -- sourced by
# run.sh and shipped.sh: the ONE way this spike starts qml (under gdb), the
# crash journal's count, and how a run's output reads.
QML=/usr/lib/qt6/bin/qml
GDB=$(command -v gdb) || { echo "codebehind-calllater: refused: gdb is not installed, and this spike starts qml only under gdb" >&2; exit 2; }
[[ -x $QML ]] || { echo "codebehind-calllater: refused: $QML is not there" >&2; exit 2; }

spike_journal() { journalctl -o json MESSAGE_ID=fc2e22bc6ee647b6b90729ab34a250b1 2>/dev/null | wc -l; }

# spike_run_qml DIR FILE OUT: FILE (a .qml in DIR) under gdb -- debuginfod
# off, every signal stopped and not passed, the inferior killed at the stop,
# so a SIGSEGV is caught there and no core is written -- offscreen, with no
# display, Hyprland signature or session bus, decoy HOME, XDG and runtime
# folders under OUT's folder; its output in OUT; gdb's exit status.
spike_run_qml() {
  local dir=$1 file=$2 out=$3 d
  d=$(dirname "$out")
  mkdir -p "$d/home" "$d/cache" "$d/config" "$d/state" "$d/data" "$d/qmlcache" "$d/rt"
  chmod 700 "$d/rt"
  ( cd "$dir" && env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME \
      -u OMARCHY_IPTV_HARNESS_DIR -u DBUS_SESSION_BUS_ADDRESS \
      HOME="$d/home" XDG_CACHE_HOME="$d/cache" XDG_CONFIG_HOME="$d/config" XDG_STATE_HOME="$d/state" \
      XDG_DATA_HOME="$d/data" XDG_RUNTIME_DIR="$d/rt" TMPDIR="$d" QML_DISK_CACHE_PATH="$d/qmlcache" \
      QML_DISABLE_DISK_CACHE=1 QT_FORCE_STDERR_LOGGING=1 QT_QPA_PLATFORM=offscreen \
      timeout 60 "$GDB" -batch -nx -iex 'set debuginfod enabled off' -ex 'handle all nopass' -ex run -ex kill \
      --args "$QML" "$file" ) >"$out" 2>&1
}

# spike_verdict OUT: sets SPIKE_VERDICT to "SIGSEGV", or to the errors
# logged and what ran ("TypeError x2", "ran: PERSIST k1,PERSIST k2",
# "nothing ran", ...), with "; no END" when the probe never reached its end,
# and SPIKE_DETAIL to the crash frame or the first error's text.
spike_verdict() {
  local o=$1 v="" err te ran
  SPIKE_DETAIL=""
  if /usr/bin/grep -q 'received signal SIGSEGV' "$o"; then
    SPIKE_DETAIL=$(/usr/bin/grep -m1 -E '^0x[0-9a-f]+ in ' "$o" | sed -E 's/^0x[0-9a-f]+ //')
    SPIKE_VERDICT="SIGSEGV"
    return
  fi
  for err in TypeError ReferenceError; do
    te=$(/usr/bin/grep -c "$err" "$o")
    if (( te > 0 )); then
      v="${v:+$v, }$err x$te"
      [[ -n $SPIKE_DETAIL ]] || SPIKE_DETAIL=$(/usr/bin/grep -m1 "$err" "$o" | sed -E "s/^.*($err)/\\1/")
    fi
  done
  ran=$(/usr/bin/grep -oE '^qml: (PERSIST [^ ]+|PING|LABEL .*)' "$o" | sed 's/^qml: //' | paste -sd, -)
  [[ -n $ran ]] && v="${v:+$v; }ran: $ran"
  [[ -z $v ]] && v="nothing ran"
  /usr/bin/grep -q '^qml: END' "$o" || v="$v; no END"
  SPIKE_VERDICT=$v
}
