#!/bin/bash
# scripts/dev-harness/spikes/codebehind-reload/run.sh -- D-REL-14's call (d):
# a hot reload across a version change with code-behinds, and D-REL-9's write
# order, measured on the host's own plugin loader in a nested headless cage.
#
#   run.sh [ARM...]      every arm below (or those named); one block of marks
#                        and verdicts per arm on stdout, the logs in the work
#                        folder (kept only with RIG_KEEP=1). An arm takes 40 s
#                        to 90 s; run a few at a time under the heavy lock,
#                        with `flock -o` so nothing it starts holds the lock.
#   RIG_DEV=<ref>        the dev tree C1 is exported from (default HEAD)
#   RIG_C0=<ref>         the released artifact (default main)
#   RIG_RACE_FILE=<file> an x arm's trigger: the plugin file whose first
#                        open by the starting shell fires the merge
#                        (default Service.qml)
#   RIG_RACE_DELAY_MS=<n> an x arm waits n ms after that open (default 0)
#   RIG_RECOVER=clear|update  an x arm, after its two restarts: remove the
#                        QML disk cache's folder and restart, or publish
#                        the next build, update under the running shell and
#                        restart (default neither)
#   RIG_QMLCACHE=xdg     start the shell without QML_DISK_CACHE_PATH, so Qt
#                        puts its disk cache where it would for a user, in
#                        the decoy HOME (default: the arm's own qmlcache
#                        folder through QML_DISK_CACHE_PATH)
#
# WHAT IT MEASURES. candidates.py builds C0 (the release, one Service.qml),
# C1 (dev's ALLOWLIST export: Service.qml and four code-behinds), C2 (C1
# with one function renamed across Service.qml and Service-player.js) and C3
# (C2 with only its marks and version moved, the race arms' later update),
# each carrying a mark in every file that can mix (C0's mark is that it has
# none).
# make-root.py cuts the host's shell.qml down to the code that loads,
# reloads, disables and enables a plugin -- byte for byte, the cuts and two
# adaptations named there -- and runs it as the quickshell root (a: with the
# host's `//@ pragma OmarchyLoadPatch`, b: without it), with the host's
# folder watcher live, under the live launcher's QS_DISABLE_FILE_WATCHER=1.
# The plugin is installed the way `omarchy plugin add` installs it (a clone
# into a hidden staging folder, validated, moved into place) in a decoy
# HOME, from a scratch upstream, with a bar entry naming a three-channel
# playlist file. Each update arm starts the shell, waits for the service to
# read three channels, stars one, publishes the next build, and runs
# omarchy-plugin-update's own git step by argv (fetch, merge --ff-only,
# validate: /usr/share/omarchy/bin/omarchy-plugin-update 9-10, 43-75),
# timed by an inotify watch of the plugins folder beside the shell's own
# events, lets the host's watcher reload, then rescanPlugins (the update's
# last step), opens the guide, and then:
#   r  restarts the shell and reads it all again
#   t  a disable and an enable the host's way (setPluginEnabled false,
#      enablePlugin), twice; before the second enable the engine collects
#      garbage and loads 8000 components it has never seen, beside a control
#      component of the rig's own whose file is rewritten after the release
#   w  nothing more (the write-order arms)
# A race arm (x) runs the update INTO a cold start: the update's own
# `merge --ff-only` (with the arm's git workers) fires when the starting
# shell first opens RIG_RACE_FILE, RIG_RACE_DELAY_MS after it, from a helper
# whose pid is recorded, while both watches time the shell's reads and git's
# writes; then it reads the marks and Qt's disk cache (cache.py), opens the
# guide, restarts twice (reading the cache after each) and recovers as
# RIG_RECOVER says.
# A half-tree arm instead makes by hand a tree a shell starting inside the
# update's write window would read, starts the shell COLD on it, completes
# the tree (`git reset --hard FETCH_HEAD`) under the live watcher, rescans,
# toggles once and restarts:
#   h1 git's order at one worker, caught just before it unlinks the old
#      Service.qml: every changed file that sorts before Service.qml in byte
#      order (the index's, which one worker writes in) taken from the new
#      build -- the bar, the guide, the README and the four code-behinds for
#      12 -- every file the update deletes deleted, and Service.qml and what
#      sorts after it (manifest.json, model/, bin/) the old build's
#   h4 a shape four workers could leave: the new Service.qml complete while
#      Service-player.js is not there (for 01, no code-behind is there yet).
#      No measured run has produced it: in every four-worker run Service.qml
#      closed after every code-behind (analyze.py prints the h4 line)
#   h0 git between unlinking Service.qml and writing it again: sub-ms at one
#      worker, and at four the main process unlinks every changed file
#      before the workers create any, so Service.qml is absent for some ms
# Every arm but h keeps an open watch over the first cold start (x: through
# the race), so analyze.py prints the shell's first read of each file.
# ARMS: <root>-<from><to>-<mode>[-<git>], root a or b, 01 (C0 to C1) or 12
# (C1 to C2), mode r, t, w, x, h1, h4 or h0, git c4 (`-c checkout.workers=4 -c
# checkout.thresholdForParallelism=1` on the merge) or g4 (the same two
# settings in the decoy HOME's ~/.gitconfig, which the update does not
# override).
#
# SAFETY. Refuses without gdb, cage, the private bus or inotifywait. Re-runs
# itself under ../../private-bus.sh (a session bus that activates nothing),
# with DISPLAY, WAYLAND_DISPLAY, the Hyprland signature, the platform theme
# and the harness folder unset, a private XDG_RUNTIME_DIR and TMPDIR under
# /tmp/claude-1000, and starts one headless cage (pixman, no input devices)
# there. Every quickshell runs under gdb (debuginfod off, `handle all
# nopass`, the inferior killed at a stop), with decoy HOME, XDG and QML
# cache folders. Starts no player: the service's own start-up probes find
# none on the private runtime. hyprctl and omarchy-notification-send are
# logging stand-ins first on PATH. Every IPC call names the recorded pid
# (--pid); every signal goes to a pid this script started or that the
# process wrote itself, through a pidfd and after a command-line check
# (qa_signal_named). Reads the crash journal before and after every shell
# and stops at once if it moves.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
HARNESS=$(cd "$HERE/../.." && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
. "$REPO/scripts/qa-lib.sh" || exit 2
ARMS_ALL="a-01-r b-01-r a-12-r b-12-r a-01-t b-01-t a-12-t b-12-t a-12-w-c4 b-12-w-c4 a-12-w-g4 a-12-h1 b-12-h1 a-12-h4 b-12-h4 a-01-h4 a-01-h0 a-12-x b-12-x a-01-x b-01-x"
PLUGIN_ID=io.github.rmcdavid.iptv
journal() { journalctl -o json MESSAGE_ID=fc2e22bc6ee647b6b90729ab34a250b1 2>/dev/null | wc -l; }

for tool in gdb cage quickshell inotifywait jq git; do
  command -v "$tool" >/dev/null 2>&1 || { echo "run.sh: refused: $tool is not installed" >&2; exit 2; }
done
[[ -x $HARNESS/private-bus.sh ]] || { echo "run.sh: refused: $HARNESS/private-bus.sh is not there" >&2; exit 2; }

if [[ ${RIG_INNER:-} != 1 ]]; then
  # ------------------------------------------------------------ outside
  for a in "$@"; do
    [[ $a =~ ^[ab]-(01|12)-(r|t|w|x|h0|h1|h4)(-(c4|g4))?$ ]] || { echo "run.sh: no arm $a (arms: $ARMS_ALL)" >&2; exit 2; }
  done
  [[ ${RIG_RACE_DELAY_MS:-0} =~ ^[0-9]{1,4}$ ]] || { echo "run.sh: RIG_RACE_DELAY_MS is not a number of ms below 10000" >&2; exit 2; }
  [[ ${RIG_RECOVER:-none} =~ ^(none|clear|update)$ ]] || { echo "run.sh: RIG_RECOVER is none, clear or update" >&2; exit 2; }
  [[ ${RIG_QMLCACHE:-arm} =~ ^(arm|xdg)$ ]] || { echo "run.sh: RIG_QMLCACHE is arm or xdg" >&2; exit 2; }
  [[ ${RIG_RACE_FILE:-Service.qml} =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ && ${RIG_RACE_FILE:-} != *..* ]] || {
    echo "run.sh: RIG_RACE_FILE is a plugin file's relative path" >&2; exit 2; }
  base=/tmp/claude-1000
  [[ -d $base && -w $base ]] || base=${TMPDIR:-/tmp}
  top=$(mktemp -d "$base/cbr.XXXXXX") || exit 2
  chmod 700 "$top"
  mkdir -m 700 "$top/rt" "$top/tmp"
  dev=$(git -C "$REPO" rev-parse --verify "${RIG_DEV:-HEAD}^{commit}") || exit 2
  c0=$(git -C "$REPO" rev-parse --verify "${RIG_C0:-main}^{commit}") || exit 2
  echo "codebehind-reload: work $top; C0 $c0, C1 from $dev"
  env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME \
    -u OMARCHY_IPTV_HARNESS_DIR -u AT_SPI_BUS_ADDRESS -u QML_DISK_CACHE_PATH \
    RIG_INNER=1 RIG_TOP="$top" RIG_BUS="$top/bus" RIG_DEV_SHA="$dev" RIG_C0_SHA="$c0" \
    XDG_RUNTIME_DIR="$top/rt" TMPDIR="$top/tmp" \
    "$HARNESS/private-bus.sh" "$top/bus" 5400 "$0" "$@"
  status=$?
  if [[ ${RIG_KEEP:-} == 1 ]]; then echo "codebehind-reload: kept $top"; else rm -rf -- "$top"; fi
  exit "$status"
fi

# -------------------------------------------------------------- inside
[[ -n ${DBUS_SESSION_BUS_ADDRESS:-} && $DBUS_SESSION_BUS_ADDRESS == *"$RIG_BUS"* ]] || {
  echo "run.sh: refused: not on the private bus private-bus.sh started at $RIG_BUS" >&2; exit 2; }
[[ -z ${DISPLAY:-} && -z ${WAYLAND_DISPLAY:-} && -z ${HYPRLAND_INSTANCE_SIGNATURE:-} ]] || {
  echo "run.sh: refused: a display or the Hyprland signature is set" >&2; exit 2; }
WORK=$RIG_TOP/w
mkdir -m 700 "$WORK" "$WORK/bin" "$WORK/trim" "$WORK/arms"
RT=$XDG_RUNTIME_DIR
J0=$(journal)
echo "crash journal before: $J0"
python3 -I "$HERE/candidates.py" "$REPO" "$WORK/cand" "$RIG_C0_SHA" "$RIG_DEV_SHA" >"$WORK/cand.json" || exit 2
UPSTREAM=$(jq -r .upstream "$WORK/cand.json")
declare -A BUILD=([0]=$(jq -r .commits.C0 "$WORK/cand.json") [1]=$(jq -r .commits.C1 "$WORK/cand.json")
                 [2]=$(jq -r .commits.C2 "$WORK/cand.json") [3]=$(jq -r .commits.C3 "$WORK/cand.json"))
echo "builds: C0 ${BUILD[0]:0:12}  C1 ${BUILD[1]:0:12}  C2 ${BUILD[2]:0:12}  C3 ${BUILD[3]:0:12} (allowlist $(jq -r .allowlist "$WORK/cand.json") files)"
python3 -I "$HERE/make-root.py" "$WORK/roots" "$HERE/rig.qml.in" >/dev/null || exit 2
for ((i = 0; i < 8000; i++)); do printf 'import QtQml\nQtObject { objectName: "t%d" }\n' "$i" >"$WORK/trim/T$i.qml"; done
printf '#!/bin/bash\nprintf "%%s\\n" "$*" >>"%s/hyprctl.log"\nexit 1\n' "$WORK" >"$WORK/bin/hyprctl"
printf '#!/bin/bash\nprintf "%%s\\n" "$*" >>"%s/notify.log"\n' "$WORK" >"$WORK/bin/omarchy-notification-send"
chmod 700 "$WORK/bin/hyprctl" "$WORK/bin/omarchy-notification-send"
: >"$WORK/hyprctl.log"; : >"$WORK/notify.log"

# The nested compositor, as key-scenario.sh starts and stops it: its child
# records the display and its own pid, and ending the child ends cage.
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

GDB_PID="" QS="" WATCH_PID="" OPEN_PID="" RACE_PID="" WATCHER="" ARM="" H="" ROOTDIR="" PLUGINS="" DIR=""
stop_cage() {
  [[ -n $CAGE_CHILD ]] && qa_signal_named TERM sleep "$CAGE_CHILD"
  timeout 10 tail --pid="$CAGE_PID" -f /dev/null 2>/dev/null
  qa_pid_live "$CAGE_PID" && kill -KILL "$CAGE_PID" 2>/dev/null
  wait "$CAGE_PID" 2>/dev/null
}
cleanup() {
  stop_race
  stop_watch
  stop_open_watch
  stop_qs
  stop_cage
  local j; j=$(journal)
  echo "crash journal after: $j"
}
trap cleanup EXIT

# A client is never timed out while the shell may still write its reply:
# under gdb's `handle all nopass` the SIGPIPE that write raises stops the
# shell and gdb's `kill` ends it (seen once, with a 15 s bound on a 4000-load
# call). The load calls are batched and get a minute each.
ipc() { timeout 15 quickshell ipc --pid "$QS" call "$@" 2>&1; }
ipc_long() { timeout 60 quickshell ipc --pid "$QS" call "$@" 2>&1; }
now() { date +%s%3N; }
note() { printf '%s %s\n' "$(now)" "$*" >>"$H/steps.log"; }
# marks STEP: the rig's reading of every running object, kept with the log
# line it was taken at.
marks() {
  local m lines
  m=$(ipc rig marks)
  lines=$(wc -l <"$H/qs.log")
  printf '{"step":"%s","t":%s,"logLine":%s,"marks":%s}\n' "$1" "$(now)" "$lines" \
    "$(jq -c . <<<"$m" 2>/dev/null || jq -Rc . <<<"$m")" >>"$H/marks.jsonl"
}
check_journal() {
  local j; j=$(journal)
  if [[ $j != "$J0" ]]; then
    echo "CRASH JOURNAL MOVED ($J0 -> $j) in arm $ARM; stopping" >&2
    coredumpctl list --since today --no-pager 2>/dev/null | tail -n 5 >&2
    exit 3
  fi
}
start_qs() {
  local i pid
  local -a qmlcache=(QML_DISK_CACHE_PATH="$H/qmlcache")
  [[ ${RIG_QMLCACHE:-arm} == xdg ]] && qmlcache=()
  rm -f "$H/qs.pid"
  note "shell starting"
  env -u DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME -u OMARCHY_IPTV_HARNESS_DIR \
    -u QML_DISK_CACHE_PATH \
    HOME="$H/home" XDG_CONFIG_HOME="$H/home/.config" XDG_CACHE_HOME="$H/home/.cache" \
    XDG_STATE_HOME="$H/home/.local/state" XDG_DATA_HOME="$H/home/.local/share" \
    "${qmlcache[@]}" QT_FORCE_STDERR_LOGGING=1 QS_DISABLE_FILE_WATCHER=1 QS_NO_RELOAD_POPUP=1 \
    OMARCHY_PATH="$ROOTDIR" WAYLAND_DISPLAY="$NESTED" QT_QPA_PLATFORM=wayland PATH="$WORK/bin:/usr/bin:/bin" \
    RIG_PID_FILE="$H/qs.pid" RIG_TRIM_DIR="$WORK/trim" \
    nice -n 10 timeout -k 5 900 gdb -batch -nx -ex 'set debuginfod enabled off' -ex 'handle all nopass' -ex run -ex kill \
      --args quickshell -n -p "$ROOTDIR/shell" >>"$H/qs.log" 2>&1 &
  GDB_PID=$!
  for ((i = 0; i < 300; i++)); do [[ -s $H/qs.pid ]] && break; sleep 0.1; done
  pid=$(tr -dc 0-9 <"$H/qs.pid" 2>/dev/null)
  # The pid the process wrote itself, held to its command line and its exe.
  if [[ -z $pid ]] || ! qa_signal_named 0 "$ROOTDIR/shell" "$pid" || [[ $(readlink "/proc/$pid/exe") != */quickshell ]]; then
    echo "run.sh: $ARM: the shell wrote no pid that runs this root within 30 s" >&2
    return 1
  fi
  QS=$pid
  note "shell up pid=$QS gdb=$GDB_PID"
}
# The host's folder watcher, by the pid its Process reports, recorded once
# the service is up: a shell that dies before stop_qs can ask leaves it
# running (and holding whatever its parents held open; one of this rig's
# held the heavy lock for twenty minutes before this was recorded early).
record_watcher() {
  local w
  w=$(ipc rig watcherPid | tr -dc 0-9)
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
  # The host's watcher outlives a shell that did not stop gracefully
  # (PluginRegistry.qml 694-699, 719-720); end ours by the pid it reported.
  [[ -n $WATCHER ]] && qa_pid_live "$WATCHER" && qa_stop_named "$WATCHER" "$PLUGINS" 5 inotifywait >/dev/null
  note "shell down"
  GDB_PID="" QS="" WATCHER=""
  check_journal
}
start_watch() {
  rm -f "$H/watch.ready"
  python3 -I "$HERE/watch.py" "$PLUGINS" "$H/watch.log" "$H/watch.ready" writes &
  WATCH_PID=$!
  local i
  for ((i = 0; i < 100; i++)); do [[ -e $H/watch.ready ]] && return 0; sleep 0.1; done
  echo "run.sh: $ARM: the write watch was not listening within 10 s" >&2
}
stop_watch() {
  [[ -n $WATCH_PID ]] || return 0
  qa_stop_named "$WATCH_PID" "$HERE/watch.py" 5 watch.py >/dev/null
  wait "$WATCH_PID" 2>/dev/null
  WATCH_PID=""
}
# The shell's reads (watch.py's opens), over a cold start.
start_open_watch() {
  rm -f "$H/open.ready"
  python3 -I "$HERE/watch.py" "$PLUGINS" "$H/open.log" "$H/open.ready" opens &
  OPEN_PID=$!
  local i
  for ((i = 0; i < 100; i++)); do [[ -e $H/open.ready ]] && return 0; sleep 0.1; done
  echo "run.sh: $ARM: the open watch was not listening within 10 s" >&2
}
stop_open_watch() {
  [[ -n $OPEN_PID ]] || return 0
  qa_stop_named "$OPEN_PID" "$HERE/watch.py" 5 watch.py >/dev/null
  wait "$OPEN_PID" 2>/dev/null
  OPEN_PID=""
}
# An x arm's helper: waits (bounded) for the starting shell's first open of
# RIG_RACE_FILE, waits RIG_RACE_DELAY_MS, and runs the update's merge. Its
# pid is recorded; it ends on its own, its inotifywait bounded at 120 s.
race_start() {
  local -a g=(git)
  [[ $1 == c4 ]] && g=(git -c checkout.workers=4 -c checkout.thresholdForParallelism=1)
  local file=${RIG_RACE_FILE:-Service.qml} delay=${RIG_RACE_DELAY_MS:-0} i
  [[ -f $DIR/$file ]] || { echo "run.sh: $ARM: $file is not in the installed tree" >&2; return 1; }
  ( export GIT_TERMINAL_PROMPT=0 HOME="$H/home" XDG_CONFIG_HOME="$H/home/.config"
    git -C "$DIR" fetch --quiet origin HEAD ) || return 1
  : >"$H/race.err"
  (
    export GIT_TERMINAL_PROMPT=0 HOME="$H/home" XDG_CONFIG_HOME="$H/home/.config"
    timeout 120 inotifywait -e open "$DIR/$file" >/dev/null 2>>"$H/race.err" || exit 9
    printf '%s race open\n' "$(date +%s%3N)" >>"$H/steps.log"
    if (( delay > 0 )); then sleep "$(printf '%d.%03d' $((delay / 1000)) $((delay % 1000)))"; fi
    printf '%s merge start\n' "$(date +%s%3N)" >>"$H/steps.log"
    "${g[@]}" -C "$DIR" merge --ff-only FETCH_HEAD >/dev/null 2>&1
    rc=$?
    printf '%s merge end\n%s merge rc=%s\n' "$(date +%s%3N)" "$(date +%s%3N)" "$rc" >>"$H/steps.log"
  ) &
  RACE_PID=$!
  for ((i = 0; i < 100; i++)); do /usr/bin/grep -q "Watches established" "$H/race.err" && break; sleep 0.1; done
  note "race armed on $file +$delay ms, helper $RACE_PID"
}
stop_race() {
  [[ -n $RACE_PID ]] || return 0
  timeout 130 tail --pid="$RACE_PID" -f /dev/null 2>/dev/null
  wait "$RACE_PID" 2>/dev/null
  RACE_PID=""
}
# Qt's disk cache: where it is for this arm, what it holds (cache.py), and
# its removal, the way a user would remove it.
cache_root() { if [[ ${RIG_QMLCACHE:-arm} == xdg ]]; then printf '%s\n' "$H/home/.cache"; else printf '%s\n' "$H/qmlcache"; fi; }
cache_read() {
  printf '  [cache %s]\n' "$1" >>"$H/cache.txt"
  python3 -I "$HERE/cache.py" "$(cache_root)" "$WORK/cand.json" "$DIR" >>"$H/cache.txt" 2>&1
}
clear_cache() {
  local d
  local -a dirs
  mapfile -t dirs <<<"$(python3 -I "$HERE/cache.py" "$(cache_root)" "$WORK/cand.json" "$DIR" --dirs)"
  for d in "${dirs[@]}"; do
    [[ -n $d ]] || continue
    if [[ $d != "$H/"* ]]; then note "cache folder $d is not the arm's; left"; continue; fi
    rm -rf -- "$d"
    note "cache folder removed: ${d#"$H/"}"
  done
}
# wait_ready SECS: until the service reads three channels.
wait_ready() {
  local i m
  for ((i = 0; i < $1 * 2; i++)); do
    m=$(ipc rig marks)
    [[ -n $WATCHER ]] || record_watcher
    [[ $(jq -r '.status.channels // 0' <<<"$m" 2>/dev/null) == 3 ]] && return 0
    sleep 0.5
  done
  note "not ready within $1 s"
  return 1
}
# wait_scan AFTER SECS: until the shell logs a scan finished after AFTER (ms)
# and is not reloading.
wait_scan() {
  local after=$1 i t
  for ((i = 0; i < $2 * 10; i++)); do
    t=$(/usr/bin/grep -aoE 'RIG-EVENT [0-9]+ scanFinished' "$H/qs.log" | awk '{print $2}' | tail -n 1)
    if [[ -n $t ]] && (( t > after )) && [[ $(jq -r .reloading <<<"$(ipc rig marks)" 2>/dev/null) == false ]]; then return 0; fi
    sleep 0.1
  done
  note "no scan within $2 s after $after"
  return 1
}
# Processes that name this arm's folder after its shell stopped (the
# service's detached orphan check runs out its grace on its own): waited on
# for 20 s and named, never signalled -- this rig did not record them.
leftovers() {
  local i p left
  for ((i = 0; i < 40; i++)); do
    left=""
    for p in /proc/[0-9]*; do
      [[ ${p#/proc/} == "$$" || ${p#/proc/} == "$BASHPID" ]] && continue
      tr '\0' ' ' <"$p/cmdline" 2>/dev/null | /usr/bin/grep -qF "$H/" && left="$left ${p#/proc/}"
    done
    [[ -z $left ]] && return 0
    sleep 0.5
  done
  echo "   left running after 20 s, naming this arm:$left" | tee -a "$H/steps.log"
}
publish() { git -C "$UPSTREAM" update-ref refs/heads/main "${BUILD[$1]}"; note "published C$1"; }
# omarchy-plugin-update's update_one, its git lines by argv with its own
# exports (omarchy-plugin-update 9-10, 43-75; its rescan, 131, is run.sh's next step).
update_step() {
  local -a g=(git)
  [[ $1 == c4 ]] && g=(git -c checkout.workers=4 -c checkout.thresholdForParallelism=1)
  (
    export GIT_TERMINAL_PROMPT=0
    export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -oBatchMode=yes}"
    export HOME="$H/home" XDG_CONFIG_HOME="$H/home/.config"
    git -C "$DIR" fetch --quiet origin HEAD || exit 11
    [[ $(git -C "$DIR" rev-parse HEAD) == $(git -C "$DIR" rev-parse FETCH_HEAD) ]] && exit 12
    printf '%s merge start\n' "$(date +%s%3N)" >>"$H/steps.log"
    "${g[@]}" -C "$DIR" merge --ff-only FETCH_HEAD >/dev/null 2>&1 || exit 13
    printf '%s merge end\n' "$(date +%s%3N)" >>"$H/steps.log"
    /usr/share/omarchy/bin/omarchy-plugin-validate "$DIR" >/dev/null || exit 14
    printf '%s validate end\n' "$(date +%s%3N)" >>"$H/steps.log"
  )
}

# toggle: a disable and an enable the host's way (omarchy-plugin-disable's
# setPluginEnabled false, omarchy-plugin-enable's enablePlugin), read after
# each, under STEP.
toggle() {
  ipc shell setPluginEnabled "$PLUGIN_ID" false >/dev/null; sleep 2
  marks "$1-disable"
  ipc shell enablePlugin "$PLUGIN_ID" '{}' >/dev/null
  wait_ready 30 || true
  marks "$1-enable"
  ipc shell summon "$PLUGIN_ID" '{}' >/dev/null; sleep 2
  marks "$1-open"
}
# restart [SECS]: stop the shell gracefully, start it again, and wait up to
# SECS (90) for three channels.
restart() {
  stop_qs
  restart_up "$@"
}
# restart_up [SECS]: the second half, for a step between the two.
restart_up() {
  start_qs || return 1
  wait_ready "${1:-90}" || echo "   not ready after the restart"
  marks restart
  ipc shell summon "$PLUGIN_ID" '{}' >/dev/null; sleep 2
  marks restart-open
}
# The release, then a toggle: the engine collects garbage and loads 8000
# components it has never seen, so one nothing references any more can
# leave the type loader's cache. The control is a component of the rig's
# own, made and let go before, its file rewritten after: a type compiled
# again reads the new text under a new _QMLTYPE_ number, a cached one not.
release_toggle() {
  local first loaded=0 n
  ipc shell setPluginEnabled "$PLUGIN_ID" false >/dev/null; sleep 2
  marks second-disable
  mkdir -p "$H/control"
  printf 'import QtQml\nQtObject { property string v: "one" }\n' >"$H/control/Probe.qml"
  note "control before: $(ipc rig control "$H/control/Probe.qml")"
  ipc rig collect >/dev/null; sleep 1
  for ((first = 0; first < 8000; first += 500)); do
    n=$(ipc_long rig load "$first" 500 | tr -dc 0-9); loaded=$((loaded + ${n:-0}))
  done
  note "loaded $loaded new components"
  ipc rig collect >/dev/null; sleep 1
  printf 'import QtQml\nQtObject { property string v: "two" }\n' >"$H/control/Probe.qml.new"
  mv "$H/control/Probe.qml.new" "$H/control/Probe.qml"
  note "control after: $(ipc rig control "$H/control/Probe.qml")"
  marks released
  ipc shell enablePlugin "$PLUGIN_ID" '{}' >/dev/null
  wait_ready 30 || true
  marks second-enable
  ipc shell summon "$PLUGIN_ID" '{}' >/dev/null; sleep 2
  marks second-open
}

# A half-written tree, made by hand, that a COLD start reads (the shell
# started inside the update's write window): h1 is git's order at one
# checkout worker caught between the code-behinds and Service.qml (the TO
# build's code-behinds beside the FROM build's Service.qml); h4 is the
# interleave at four workers (the TO build's Service.qml written while
# Service-player.js is not there yet); h0 is the moment, at any worker
# count, when git has unlinked Service.qml and not yet written it again
# (0.20.0's own updates have it). Then the tree is completed
# (`git reset --hard FETCH_HEAD`, omarchy-plugin-update's own rollback verb,
# here run forward) under the live watcher, rescanned, toggled, restarted.
half_tree() {
  local cb
  ( export GIT_TERMINAL_PROMPT=0 HOME="$H/home" XDG_CONFIG_HOME="$H/home/.config"
    git -C "$DIR" fetch --quiet origin HEAD ) || return 1
  case $1 in
    h1) # Every path the update deletes, then every changed path before
        # Service.qml in byte order (the index's order, which one worker
        # writes in), from FETCH_HEAD.
        local p
        local -a gone changed took=()
        mapfile -t gone <<<"$(git -C "$DIR" diff --name-only --no-renames --diff-filter=D HEAD FETCH_HEAD)"
        for p in "${gone[@]}"; do [[ -n $p ]] && rm -f -- "${DIR:?}/$p" && took+=("-$p"); done
        mapfile -t changed <<<"$( { git -C "$DIR" diff --name-only --no-renames --diff-filter=d HEAD FETCH_HEAD; echo Service.qml; } | LC_ALL=C sort -u)"
        for p in "${changed[@]}"; do
          [[ -n $p ]] || continue
          [[ $p == Service.qml ]] && break
          mkdir -p -- "$(dirname -- "$DIR/$p")"
          git -C "$DIR" show "FETCH_HEAD:$p" >"$DIR/$p" || return 1
          took+=("$p")
        done
        note "half tree h1 took ${took[*]}" ;;
    h4) git -C "$DIR" show FETCH_HEAD:Service.qml >"$DIR/Service.qml" || return 1
        rm -f "$DIR/Service-player.js" ;;
    h0) rm -f "$DIR/Service.qml" ;;
  esac
  note "half tree $1 made"
}

run_arm() {
  ARM=$1
  local root pair mode git from to t0 rc
  IFS=- read -r root pair mode git <<<"$ARM"
  from=${pair:0:1} to=${pair:1:1}
  H=$WORK/arms/$ARM; ROOTDIR=$WORK/roots/$root
  mkdir -m 700 -p "$H/home/.config/omarchy/plugins" "$H/home/rig-no-first-party" "$H/qmlcache"
  PLUGINS=$H/home/.config/omarchy/plugins; DIR=$PLUGINS/$PLUGIN_ID
  : >"$H/qs.log"; : >"$H/steps.log"; : >"$H/marks.jsonl"; : >"$H/watch.log"
  printf '#EXTM3U\n#EXTINF:-1 tvg-id="one" group-title="News",One\nhttp://127.0.0.1:9/one.ts\n#EXTINF:-1 tvg-id="two" group-title="News",Two\nhttp://127.0.0.1:9/two.ts\n#EXTINF:-1 tvg-id="three" group-title="Sport",Three\nhttp://127.0.0.1:9/three.ts\n' >"$H/play.m3u"
  jq -n --arg id "$PLUGIN_ID" --arg pl "$H/play.m3u" \
    '{version: 1, bar: {layout: {left: [], centerBegin: [], center: [], centerEnd: [], right: [{id: $id, playlistUrl: $pl, refreshMinutes: 120}]}}, plugins: []}' \
    >"$H/home/.config/omarchy/shell.json"
  [[ $git == g4 ]] && printf '[checkout]\n\tworkers = 4\n\tthresholdForParallelism = 1\n' >"$H/home/.gitconfig"
  # omarchy-plugin-add's install (its 11-12, 119-147): a clone into a hidden
  # staging folder, validated, moved into place.
  publish "$from"
  ( export GIT_TERMINAL_PROMPT=0 HOME="$H/home" XDG_CONFIG_HOME="$H/home/.config"
    git clone -q -- "$UPSTREAM" "$PLUGINS/.add.tmp.$$" && \
    /usr/share/omarchy/bin/omarchy-plugin-validate "$PLUGINS/.add.tmp.$$" >/dev/null && \
    mv "$PLUGINS/.add.tmp.$$" "$DIR" ) || { echo "run.sh: $ARM: the install failed" >&2; return 1; }
  local extra=""
  [[ $mode == x ]] && extra=", the merge at the first open of ${RIG_RACE_FILE:-Service.qml} +${RIG_RACE_DELAY_MS:-0} ms, recover ${RIG_RECOVER:-none}"
  [[ ${RIG_QMLCACHE:-arm} == xdg ]] && extra="$extra, Qt's own cache folder"
  echo "== $ARM: root $root ($([[ $root == a ]] && echo pragma || echo no pragma)), C$from -> C$to, mode $mode${git:+, git $git}$extra"
  publish "$to"
  if [[ $mode == x ]]; then
    start_open_watch
    start_watch
    race_start "$git" || return 1
    start_qs || return 1
    stop_race
    note "race done"
    wait_ready 40 || echo "   not ready after the race"
    marks race-start
    stop_watch
    stop_open_watch
    cache_read race
    ipc shell summon "$PLUGIN_ID" '{}' >/dev/null; sleep 2
    marks race-open
    restart 60
    cache_read restart-1
    restart 60
    cache_read restart-2
    case ${RIG_RECOVER:-none} in
      clear)
        stop_qs
        clear_cache
        restart_up 60
        cache_read cleared ;;
      update)
        publish $((to + 1))
        start_watch
        t0=$(now)
        update_step "$git"; rc=$?
        note "update rc=$rc"
        wait_scan "$t0" 15
        t0=$(now)
        ipc shell rescanPlugins >/dev/null
        wait_scan "$t0" 15
        stop_watch
        marks updated
        restart 60
        cache_read updated ;;
    esac
  elif [[ $mode == h0 || $mode == h1 || $mode == h4 ]]; then
    half_tree "$mode" || { echo "run.sh: $ARM: the half tree failed" >&2; return 1; }
    start_open_watch
    start_qs || return 1
    wait_ready 20 || echo "   not ready on the half tree"
    stop_open_watch
    marks half-start
    start_watch
    t0=$(now)
    printf '%s merge start\n' "$(now)" >>"$H/steps.log"
    git -C "$DIR" reset -q --hard FETCH_HEAD; rc=$?
    printf '%s merge end\n' "$(now)" >>"$H/steps.log"
    note "completed rc=$rc"
    wait_scan "$t0" 15
    marks completed-watcher
    t0=$(now)
    ipc shell rescanPlugins >/dev/null
    wait_scan "$t0" 15
    stop_watch
    marks completed-rescan
    toggle completed
    restart 30
  else
    start_open_watch
    start_qs || return 1
    wait_ready 90 || echo "   not ready at start"
    stop_open_watch
    ipc rig favorite >/dev/null; sleep 1.5
    marks start
    start_watch
    t0=$(now)
    update_step "$git"; rc=$?
    note "update rc=$rc"
    wait_scan "$t0" 15
    marks watcher-reload
    t0=$(now)
    ipc shell rescanPlugins >/dev/null
    wait_scan "$t0" 15
    stop_watch
    marks rescanPlugins
    ipc shell summon "$PLUGIN_ID" '{}' >/dev/null; sleep 2
    marks guide-open
    case $mode in
      r) restart ;;
      t) toggle first; release_toggle ;;
    esac
  fi
  stop_qs
  leftovers
  cp "$H/home/.config/omarchy/shell.json" "$H/shell.json.end"
  cp "$H/home/.local/state/omarchy-iptv/state.json" "$H/state.json.end" 2>/dev/null
  python3 -I "$HERE/analyze.py" "$H" "$ARM"
}

ARMS=("$@")
(( ${#ARMS[@]} > 0 )) || read -r -a ARMS <<<"$ARMS_ALL"
for arm in "${ARMS[@]}"; do
  run_arm "$arm" || echo "   arm $arm did not finish"
done
