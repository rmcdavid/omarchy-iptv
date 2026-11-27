#!/bin/bash
# scripts/dev-harness/spikes/barconfig-window/run.sh -- D-HOST-15: whether the
# service the host creates reads default settings until the host's next
# syncPluginApis, and whether a state.json write from them lands, measured on
# the host's own code in a nested headless cage.
#
#   run.sh ARM...        each ARM once, in order (name one twice to run it
#                        twice), each with a fresh decoy HOME; one block of
#                        readings and a verdict per start on stdout
#                        (analyze.py), the logs in the work folder (kept only
#                        with RIGW_KEEP=1)
#   ARM                  <root>-<path>-<fixture>: root a (the host's
#                        `//@ pragma OmarchyLoadPatch`, what the live shell
#                        runs) or b (without it); path below; fixture F, M or
#                        N (fixture.py)
#   RIGW_DEV=<ref>       the dev commit whose ALLOWLIST export is installed,
#                        unchanged (export.py; required)
#   RIGW_BAR=1           the host's own bar in the root (make-root.py --bar)
#   RIGW_WIDGETS=1       the host's first-party bar widgets scanned
#                        (make-root.py --widgets)
#   RIGW_PATCH=0         install without service-log.patch (default 1): the
#                        run that shows the logging changes no state.json
#   RIGW_HOLD=1          THE RED CONTROL: make-root.py --hold-sync, and the
#                        shell started with syncPluginApis held; the rig
#                        releases it RIGW_RELEASE_MS (default 6000) after
#                        the service appears
#   RIGW_SETTLE=<s>      seconds a start is read for after its last step
#                        (default 8)
#   RIGW_LOAD=<n>        n CPU burners (a python busy loop each, at the
#                        rig's nice 10, their pids recorded and ended at
#                        exit) for the whole run: a shell starting while the
#                        machine is busy, as at a login (default 0)
#   RIGW_CACHE=warm      every start of a root at ONE decoy HOME path (made
#                        fresh each time, the plugin copied in with its
#                        files' times kept) over one QML disk cache per root,
#                        so a start after the first compiles nothing, as a
#                        shell started at login over an unchanged install
#                        does; the default, cold, is the reload rig's: a
#                        fresh path and an empty cache per start, as the
#                        first start after an install or an update
#
# PATHS, each the host's own, driven by its own IPC (the calls the omarchy
# commands make) and its own folder watcher:
#   cold     the plugin installed and its entry in shell.json before the
#            shell starts: a cold start of the shell
#   toggle   a cold start, then a disable and an enable the host's way
#            (setPluginEnabled false, then enablePlugin '{}': what
#            omarchy-plugin-disable and omarchy-plugin-enable call); the
#            host's disable splices the entry out, so the enable's entry is
#            `{id}` and its settings are gone (PluginRegistry.qml 588, 557)
#   install  the shell started with the entry in shell.json and no plugin
#            installed; then omarchy-plugin-add's install (a clone into a
#            hidden staging folder, validated, moved into place: its
#            119-147) under the host's live watcher, and its
#            `rescanPlugins` straight after (its 149)
#   enableh  the shell started with the plugin disabled the host's way (no
#            entry: fixture.py), then enablePlugin '{}'
#   enablel  the shell started with the entry present and the id in
#            `disabledPlugins` (a hand-edited shell.json), then
#            enablePlugin '{}', which keeps the entry's settings
#
# WHAT IT READS. The roots are ../codebehind-reload/make-root.py's cut of the
# host's shell.qml (pinned by sha256 there), always with --probe (a logging
# line above shell.qml 958 and 1005 that reads the host's own API cache as
# createScopedPluginShell is about to: "fresh" or "cached") and with
# rig.qml.in as the block (the host's cache, its services, syncPluginApis's
# assignments to this plugin's API, the bar's API, every registry signal,
# each with the stack that made this plugin's API). The service is the
# export's, with service-log.patch applied to the decoy install's copy
# before it is moved into place (console lines only, pinned to 27e2a84's
# Service.qml by sha256: refused otherwise). snap.py reads every state.json
# that lands. analyze.py lays it out per start.
#
# SAFETY. As ../codebehind-reload/run.sh: refuses without gdb, cage, the
# private bus or inotifywait; re-runs itself under ../../private-bus.sh with
# DISPLAY, WAYLAND_DISPLAY, the Hyprland signature, the platform theme and
# the harness folder unset, a private XDG_RUNTIME_DIR and TMPDIR under
# /tmp/claude-1000; one headless cage (pixman, no input devices); every
# quickshell under gdb (debuginfod off, `handle all nopass`, the inferior
# killed at a stop) with decoy HOME, XDG and QML cache folders. No player
# starts: nothing plays, and the service's probes find none on the private
# runtime. First on the shell's PATH, a logging stand-in for hyprctl and for
# EVERY omarchy-* command /usr/bin holds, so nothing the host's bar or the
# plugin runs by name reaches a running shell or the user's files (the bar
# runs `omarchy-bar sync-glass` through `bash -lc`, which keeps PATH's
# order). Every IPC call names the recorded pid; every signal goes to a pid
# this script started or that the process wrote itself, through a pidfd and
# after a command-line check (qa_signal_named). Reads the crash journal
# before and after every shell and stops at once if it moves.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
HARNESS=$(cd "$HERE/../.." && pwd)
RIG=$(cd "$HERE/../codebehind-reload" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
. "$REPO/scripts/qa-lib.sh" || exit 2
PLUGIN_ID=io.github.rmcdavid.iptv
SERVICE_SHA=8e4a2bb8c93e3eb766facf01eb7759845c58064618ef8e365af8d7532f742010
PATCHED_SHA=93302abc9e30c75052554f065c9b460692f6a7df0b1e7c3db557eede860c4571
journal() { journalctl -o json MESSAGE_ID=fc2e22bc6ee647b6b90729ab34a250b1 2>/dev/null | wc -l; }

for tool in gdb cage quickshell inotifywait jq git; do
  command -v "$tool" >/dev/null 2>&1 || { echo "run.sh: refused: $tool is not installed" >&2; exit 2; }
done
[[ -x $HARNESS/private-bus.sh ]] || { echo "run.sh: refused: $HARNESS/private-bus.sh is not there" >&2; exit 2; }

if [[ ${RIGW_INNER:-} != 1 ]]; then
  # ------------------------------------------------------------ outside
  (( $# > 0 )) || { echo "usage: run.sh ARM... (ARM: <a|b>-<cold|toggle|install|enableh|enablel>-<F|M|N>)" >&2; exit 2; }
  for a in "$@"; do
    [[ $a =~ ^[ab]-(cold|toggle|install|enableh|enablel)-[FMN]$ ]] || { echo "run.sh: no arm $a" >&2; exit 2; }
  done
  [[ -n ${RIGW_DEV:-} ]] || { echo "run.sh: RIGW_DEV names the dev commit to export" >&2; exit 2; }
  [[ ${RIGW_RELEASE_MS:-6000} =~ ^[0-9]{1,5}$ ]] || { echo "run.sh: RIGW_RELEASE_MS is a number of ms" >&2; exit 2; }
  [[ ${RIGW_SETTLE:-8} =~ ^[0-9]{1,2}$ ]] || { echo "run.sh: RIGW_SETTLE is a number of seconds" >&2; exit 2; }
  [[ ${RIGW_CACHE:-cold} =~ ^(cold|warm)$ ]] || { echo "run.sh: RIGW_CACHE is cold or warm" >&2; exit 2; }
  [[ ${RIGW_LOAD:-0} =~ ^[0-8]$ ]] || { echo "run.sh: RIGW_LOAD is 0 to 8 burners" >&2; exit 2; }
  base=/tmp/claude-1000
  [[ -d $base && -w $base ]] || base=${TMPDIR:-/tmp}
  top=$(mktemp -d "$base/bcw.XXXXXX") || exit 2
  chmod 700 "$top"
  mkdir -m 700 "$top/rt" "$top/tmp"
  dev=$(git -C "$REPO" rev-parse --verify "$RIGW_DEV^{commit}") || exit 2
  echo "barconfig-window: work $top; export of $dev; bar ${RIGW_BAR:-0} widgets ${RIGW_WIDGETS:-0} patch ${RIGW_PATCH:-1} hold ${RIGW_HOLD:-0} cache ${RIGW_CACHE:-cold} load ${RIGW_LOAD:-0}"
  env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME \
    -u OMARCHY_IPTV_HARNESS_DIR -u AT_SPI_BUS_ADDRESS -u QML_DISK_CACHE_PATH \
    RIGW_INNER=1 RIGW_TOP="$top" RIGW_BUS="$top/bus" RIGW_DEV_SHA="$dev" \
    XDG_RUNTIME_DIR="$top/rt" TMPDIR="$top/tmp" \
    "$HARNESS/private-bus.sh" "$top/bus" 5400 "$0" "$@"
  status=$?
  if [[ ${RIGW_KEEP:-} == 1 ]]; then echo "barconfig-window: kept $top"; else rm -rf -- "$top"; fi
  exit "$status"
fi

# -------------------------------------------------------------- inside
[[ -n ${DBUS_SESSION_BUS_ADDRESS:-} && $DBUS_SESSION_BUS_ADDRESS == *"$RIGW_BUS"* ]] || {
  echo "run.sh: refused: not on the private bus private-bus.sh started at $RIGW_BUS" >&2; exit 2; }
[[ -z ${DISPLAY:-} && -z ${WAYLAND_DISPLAY:-} && -z ${HYPRLAND_INSTANCE_SIGNATURE:-} ]] || {
  echo "run.sh: refused: a display or the Hyprland signature is set" >&2; exit 2; }
WORK=$RIGW_TOP/w
mkdir -m 700 "$WORK" "$WORK/bin" "$WORK/arms"
RT=$XDG_RUNTIME_DIR
J0=$(journal)
echo "crash journal before: $J0"
python3 -I "$HERE/export.py" "$REPO" "$WORK/exp" "$RIGW_DEV_SHA" >"$WORK/exp.json" || exit 2
UPSTREAM=$(jq -r .upstream "$WORK/exp.json")
[[ $(jq -r .serviceSha256 "$WORK/exp.json") == "$SERVICE_SHA" ]] || {
  echo "run.sh: refused: the export's Service.qml is not the one service-log.patch is pinned to ($SERVICE_SHA)" >&2; exit 2; }
echo "export: $(jq -r .commit "$WORK/exp.json" | cut -c1-12) of $(jq -r .dev "$WORK/exp.json" | cut -c1-12) ($(jq -r .allowlist "$WORK/exp.json") files)"
opts=(--probe)
[[ ${RIGW_BAR:-0} == 1 ]] && opts+=(--bar)
[[ ${RIGW_WIDGETS:-0} == 1 ]] && opts+=(--widgets)
[[ ${RIGW_HOLD:-0} == 1 ]] && opts+=(--hold-sync)
python3 -I "$RIG/make-root.py" "$WORK/roots" "$HERE/rig.qml.in" "${opts[@]}" >/dev/null || exit 2
echo "roots: make-root.py ${opts[*]}"
[[ -f $WORK/roots/a/widgets.json ]] && echo "first-party manifests scanned: $(jq -r '.kept | join(" ")' "$WORK/roots/a/widgets.json")"
printf '#!/bin/bash\nprintf "%%s %%s\\n" "$(basename "$0")" "$*" >>"%s/standin.log"\nexit 1\n' "$WORK" >"$WORK/bin/.standin"
chmod 700 "$WORK/bin/.standin"
for f in /usr/bin/omarchy*; do ln -s "$WORK/bin/.standin" "$WORK/bin/${f##*/}"; done
ln -s "$WORK/bin/.standin" "$WORK/bin/hyprctl"
: >"$WORK/standin.log"
echo "stand-ins first on PATH: $(find "$WORK/bin" -type l | wc -l)"

# The nested compositor, as ../codebehind-reload/run.sh starts and stops it.
CAGE_PID="" CAGE_CHILD="" NESTED=""
qa_cage_runtime_fits || exit 2
cat >"$WORK/child.sh" <<CHILD
#!/bin/bash
echo "\$WAYLAND_DISPLAY" >"$WORK/display"
echo \$\$ >"$WORK/child.pid"
exec sleep 5000
CHILD
chmod 700 "$WORK/child.sh"
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
  timeout -k 5 5100 cage -- "$WORK/child.sh" >"$WORK/cage.log" 2>&1 &
CAGE_PID=$!
for ((i = 0; i < 100; i++)); do [[ -s $WORK/display && -s $WORK/child.pid ]] && break; sleep 0.1; done
NESTED=$(cat "$WORK/display" 2>/dev/null); CAGE_CHILD=$(cat "$WORK/child.pid" 2>/dev/null)
[[ -n $NESTED && -n $CAGE_CHILD && -S $RT/$NESTED ]] || { echo "run.sh: cage brought up no display" >&2; exit 2; }
echo "nested display $NESTED (cage $CAGE_PID)"

GDB_PID="" QS="" SNAP_PID="" WATCHER="" ARM="" H="" ROOTDIR="" PLUGINS="" DIR=""
BURNERS=()
BURN='import time
while True: pass  # barconfig-window burner'
# qa_signal_named holds a pid to an argv item that STARTS with the needle,
# so the needle is the burner's whole -c text (a needle from inside it left
# every burner running after its run: lane-dh15m's L runs, 2026-11-27).
stop_burners() {
  local b
  for b in "${BURNERS[@]}"; do qa_stop_named "$b" "$BURN" 5 burner >/dev/null || echo "run.sh: burner $b was not stopped" >&2; done
  BURNERS=()
}
stop_cage() {
  [[ -n $CAGE_CHILD ]] && qa_signal_named TERM sleep "$CAGE_CHILD"
  timeout 10 tail --pid="$CAGE_PID" -f /dev/null 2>/dev/null
  qa_pid_live "$CAGE_PID" && kill -KILL "$CAGE_PID" 2>/dev/null
  wait "$CAGE_PID" 2>/dev/null
}
cleanup() {
  stop_burners
  stop_snap
  stop_qs
  stop_cage
  local j; j=$(journal)
  echo "crash journal after: $j"
}
trap cleanup EXIT

ipc() { timeout 15 quickshell ipc --pid "$QS" call "$@" 2>&1; }
now() { date +%s%3N; }
note() { printf '%s %s\n' "$(now)" "$*" >>"$H/steps.log"; }
check_journal() {
  local j; j=$(journal)
  if [[ $j != "$J0" ]]; then
    echo "CRASH JOURNAL MOVED ($J0 -> $j) in arm $ARM; stopping" >&2
    coredumpctl list --since today --no-pager 2>/dev/null | tail -n 5 >&2
    exit 3
  fi
}
end_gdb() {
  [[ -n $GDB_PID ]] || return 0
  kill -TERM "$GDB_PID" 2>/dev/null
  timeout 15 tail --pid="$GDB_PID" -f /dev/null 2>/dev/null
  qa_pid_live "$GDB_PID" && kill -KILL "$GDB_PID" 2>/dev/null
  wait "$GDB_PID" 2>/dev/null
  note "shell start abandoned, gdb $GDB_PID ended"
  GDB_PID="" QS=""
}
start_qs() {
  local i pid
  local -a hold=()
  [[ ${RIGW_HOLD:-0} == 1 ]] && hold=(RIGW_HOLD_SYNC=1)
  rm -f "$H/qs.pid"
  note "shell starting"
  env -u DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME -u OMARCHY_IPTV_HARNESS_DIR \
    -u QML_DISK_CACHE_PATH -u XDG_CACHE_HOME \
    HOME="$H/home" XDG_CONFIG_HOME="$H/home/.config" XDG_CACHE_HOME="$H/home/.cache" \
    XDG_STATE_HOME="$H/home/.local/state" XDG_DATA_HOME="$H/home/.local/share" \
    QML_DISK_CACHE_PATH="$H/qmlcache" QT_FORCE_STDERR_LOGGING=1 QS_DISABLE_FILE_WATCHER=1 QS_NO_RELOAD_POPUP=1 \
    OMARCHY_PATH="$ROOTDIR" WAYLAND_DISPLAY="$NESTED" QT_QPA_PLATFORM=wayland PATH="$WORK/bin:/usr/bin:/bin" \
    RIG_PID_FILE="$H/qs.pid" "${hold[@]}" \
    nice -n 10 timeout -k 5 900 gdb -batch -nx -ex 'set debuginfod enabled off' -ex 'handle all nopass' -ex run -ex kill \
      --args quickshell -n -p "$ROOTDIR/shell" >>"$H/qs.log" 2>&1 &
  GDB_PID=$!
  for ((i = 0; i < 300; i++)); do [[ -s $H/qs.pid ]] && break; sleep 0.1; done
  pid=$(tr -dc 0-9 <"$H/qs.pid" 2>/dev/null)
  if [[ -z $pid ]] || ! qa_signal_named 0 "$ROOTDIR/shell" "$pid" || [[ $(readlink "/proc/$pid/exe") != */quickshell ]]; then
    echo "run.sh: $ARM: the shell wrote no pid that runs this root within 30 s" >&2
    end_gdb
    return 1
  fi
  QS=$pid
  note "shell up pid=$QS gdb=$GDB_PID"
}
record_watcher() {
  local w
  w=$(ipc rigw watcherPid | tr -dc 0-9)
  [[ -n $w ]] && WATCHER=$w
}
stop_qs() {
  [[ -n $GDB_PID ]] || return 0
  [[ -n $QS ]] && timeout 20 quickshell kill --pid "$QS" >/dev/null 2>&1
  timeout 30 tail --pid="$GDB_PID" -f /dev/null 2>/dev/null
  if qa_pid_live "$GDB_PID"; then
    [[ -n $QS ]] && qa_signal_named KILL "$ROOTDIR/shell" "$QS"
    timeout 10 tail --pid="$GDB_PID" -f /dev/null 2>/dev/null
  fi
  wait "$GDB_PID" 2>/dev/null
  [[ -n $WATCHER ]] && qa_pid_live "$WATCHER" && qa_stop_named "$WATCHER" "$PLUGINS" 5 inotifywait >/dev/null
  note "shell down"
  GDB_PID="" QS="" WATCHER=""
  check_journal
}
start_snap() {
  rm -f "$H/snap.ready"
  python3 -I "$HERE/snap.py" "$H/home/.local/state/omarchy-iptv" "$H/snaps.jsonl" "$H/snap.ready" "$H/play.m3u" &
  SNAP_PID=$!
  local i
  for ((i = 0; i < 100; i++)); do [[ -e $H/snap.ready ]] && return 0; sleep 0.1; done
  echo "run.sh: $ARM: the state watch was not listening within 10 s" >&2
}
stop_snap() {
  [[ -n $SNAP_PID ]] || return 0
  qa_stop_named "$SNAP_PID" "$HERE/snap.py" 5 snap.py >/dev/null
  wait "$SNAP_PID" 2>/dev/null
  SNAP_PID=""
}
# rstate STEP: the rig's reading of the service, kept with the step.
rstate() {
  local m
  m=$(ipc rigw state)
  printf '{"step":"%s","t":%s,"state":%s}\n' "$1" "$(now)" "$(jq -c . <<<"$m" 2>/dev/null || jq -Rc . <<<"$m")" >>"$H/rstate.jsonl"
}
# wait_service SECS: until the host publishes a service for the plugin.
wait_service() {
  local i
  local s
  for ((i = 0; i < $1 * 4; i++)); do
    s=$(ipc rigw state | jq -r .service 2>/dev/null)
    [[ -n $s && $s != none && $s != null ]] && return 0
    [[ -n $WATCHER ]] || record_watcher
    sleep 0.25
  done
  note "no service within $1 s"
  return 1
}
# omarchy-plugin-add's install (its 119-147): a clone into a hidden staging
# folder, validated, patched (this rig's console lines; RIGW_PATCH=0 skips
# it), moved into place.
install_plugin() {
  local stage="$PLUGINS/.add.tmp.$$"
  if [[ ${1:-} == template ]]; then
    # RIGW_CACHE=warm's cold-path install: the template made once (below),
    # copied with its files' times, so Qt's disk cache still holds for it.
    cp -a "$WORK/template" "$stage" || return 1
    note "install move (template)"
    mv "$stage" "$DIR" || return 1
    note "install moved"
    return 0
  fi
  ( export GIT_TERMINAL_PROMPT=0 HOME="$H/home" XDG_CONFIG_HOME="$H/home/.config"
    git clone -q -- "$UPSTREAM" "$stage" ) || return 1
  /usr/share/omarchy/bin/omarchy-plugin-validate "$stage" >/dev/null || return 1
  if [[ ${RIGW_PATCH:-1} == 1 ]]; then
    [[ $(sha256sum <"$stage/Service.qml" | cut -c1-64) == "$SERVICE_SHA" ]] || { echo "run.sh: $ARM: Service.qml is not the pinned one" >&2; return 1; }
    git -C "$stage" apply "$HERE/service-log.patch" || return 1
    [[ $(sha256sum <"$stage/Service.qml" | cut -c1-64) == "$PATCHED_SHA" ]] || { echo "run.sh: $ARM: the patch did not give the pinned result" >&2; return 1; }
  fi
  note "install move"
  mv "$stage" "$DIR" || return 1
  note "install moved"
}
settle() { note "settle $1 s"; sleep "$1"; }
# The red control's release, once the service exists: the held
# syncPluginApis runs as the next registry or widget change would.
release_later() {
  [[ ${RIGW_HOLD:-0} == 1 ]] || return 0
  local ms=${RIGW_RELEASE_MS:-6000}
  sleep "$(printf '%d.%03d' $((ms / 1000)) $((ms % 1000)))"
  rstate before-release
  note "release: $(ipc rigw release)"
}

# Processes that name this start's folder after its shell stopped (the
# service's detached orphan check runs out its grace on its own): waited on
# for 20 s and named, never signalled -- this rig did not record them.
leftovers() {
  local i p left
  for ((i = 0; i < 40; i++)); do
    left=""
    for p in /proc/[0-9]*; do
      [[ ${p#/proc/} == "$$" || ${p#/proc/} == "$BASHPID" ]] && continue
      { tr '\0' ' ' <"$p/cmdline"; } 2>/dev/null | /usr/bin/grep -qF "$H/" && left="$left ${p#/proc/}"
    done
    [[ -z $left ]] && return 0
    sleep 0.5
  done
  echo "   left running after 20 s, naming this start:$left" | tee -a "$H/steps.log"
}

run_arm() {
  ARM=$1
  local root path fixture n=$2 keep=""
  IFS=- read -r root path fixture <<<"$ARM"
  H=$WORK/arms/$ARM.$n; ROOTDIR=$WORK/roots/$root
  if [[ ${RIGW_CACHE:-cold} == warm ]]; then
    keep=$H
    H=$WORK/h
    rm -rf -- "$WORK/h"
    mkdir -m 700 -p "$WORK/qmlcache-$root"
  fi
  mkdir -m 700 -p "$H/home/.config/omarchy/plugins" "$H/qmlcache"
  [[ -n $keep ]] && { rmdir "$H/qmlcache"; ln -s "$WORK/qmlcache-$root" "$H/qmlcache"; }
  PLUGINS=$H/home/.config/omarchy/plugins; DIR=$PLUGINS/$PLUGIN_ID
  : >"$H/qs.log"; : >"$H/steps.log"; : >"$H/rstate.jsonl"; : >"$H/snaps.jsonl"
  printf '#EXTM3U\n#EXTINF:-1 tvg-id="one" group-title="News",One\nhttp://127.0.0.1:9/one.ts\n#EXTINF:-1 tvg-id="two" group-title="News",Two\nhttp://127.0.0.1:9/two.ts\n#EXTINF:-1 tvg-id="three" group-title="Sport",Three\nhttp://127.0.0.1:9/three.ts\n' >"$H/play.m3u"
  python3 -I "$HERE/fixture.py" "$H/home" "$H/play.m3u" "$fixture" "$path" >"$H/fixture.sha" || { echo "run.sh: $ARM: fixture failed" >&2; return 1; }
  cp "$H/home/.config/omarchy/shell.json" "$H/shell.json.start"
  cp "$H/home/.local/state/omarchy-iptv/state.json" "$H/state.json.start"
  echo "== $ARM.$n: root $root ($([[ $root == a ]] && echo pragma || echo no pragma)), path $path, fixture $fixture"
  if [[ $path != install && -n $keep ]]; then install_plugin template || { echo "run.sh: $ARM: the install failed" >&2; return 1; }
  elif [[ $path != install ]]; then install_plugin || { echo "run.sh: $ARM: the install failed" >&2; return 1; }; fi
  start_snap
  start_qs || return 1
  case $path in
    cold)
      wait_service 30 || true
      release_later
      settle "${RIGW_SETTLE:-8}" ;;
    toggle)
      wait_service 30 || true
      settle "${RIGW_SETTLE:-8}"
      rstate first
      note "disable: $(ipc shell setPluginEnabled "$PLUGIN_ID" false)"
      sleep 2
      rstate disabled
      note "enable: $(ipc shell enablePlugin "$PLUGIN_ID" '{}')"
      wait_service 30 || true
      release_later
      settle "${RIGW_SETTLE:-8}" ;;
    install)
      sleep 3
      record_watcher
      rstate before-install
      install_plugin || { echo "run.sh: $ARM: the install failed" >&2; return 1; }
      note "rescan: $(ipc shell rescanPlugins)"
      wait_service 30 || true
      release_later
      settle "${RIGW_SETTLE:-8}" ;;
    enableh|enablel)
      sleep 3
      record_watcher
      rstate before-enable
      note "enable: $(ipc shell enablePlugin "$PLUGIN_ID" '{}')"
      wait_service 30 || true
      release_later
      settle "${RIGW_SETTLE:-8}" ;;
  esac
  rstate end
  stop_qs
  stop_snap
  leftovers
  cp "$H/home/.config/omarchy/shell.json" "$H/shell.json.end"
  cp "$H/home/.local/state/omarchy-iptv/state.json" "$H/state.json.end" 2>/dev/null
  if [[ -n $keep ]]; then mv "$H" "$keep" || return 1; H=$keep; fi
  python3 -I "$HERE/analyze.py" "$H" "$ARM.$n"
}

for ((i = 0; i < ${RIGW_LOAD:-0}; i++)); do
  nice -n 10 python3 -I -c "$BURN" &
  BURNERS+=($!)
done
(( ${#BURNERS[@]} > 0 )) && echo "burners: ${BURNERS[*]}"
if [[ ${RIGW_CACHE:-cold} == warm ]]; then
  # The template the warm cold-path starts copy: the install's own clone,
  # validated and patched as install_plugin does it, made once.
  H=$WORK/tpl; ARM=template; mkdir -m 700 -p "$H"; : >"$H/steps.log"
  PLUGINS=$H; DIR=$WORK/template
  install_plugin || { echo "run.sh: the template install failed" >&2; exit 2; }
fi
declare -A COUNT=()
for arm in "$@"; do
  COUNT[$arm]=$(( ${COUNT[$arm]:-0} + 1 ))
  run_arm "$arm" "${COUNT[$arm]}" || { echo "   arm $arm.${COUNT[$arm]} did not finish"; stop_qs; stop_snap; }
done
echo "stand-in calls: $(wc -l <"$WORK/standin.log")"
sort "$WORK/standin.log" | uniq -c | sed 's/^/   /'
