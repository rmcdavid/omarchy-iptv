#!/bin/bash
# scripts/dev-harness/spikes/state-private/measure.sh -- D-SINK-103: what
# mode Quickshell's FileView with atomicWrites gives state.json and every
# temporary it writes through, and whether the helper's `state private`
# run BEFORE the write keeps a new credential out of every file another
# account could read.
#
#   measure.sh [ORDER] [CASE...]
#   measure.sh timed [N] [CASE...]
#     ORDER  fix   `state private` before the write, the write only on its
#                  confirmed reply, `state mode` after it (D-SINK-103)
#            base  the write, then `state mode` (0.19.1's order)
#            both  (default) each case in both orders
#     CASE   new        nothing at the path, the state folder 0700
#            e644       a valid state.json with no credential at 0644 (a
#                       backup restored with cp, say)
#            e600       the same at 0600 (the steady state)
#            link644    state.json a link into a folder other accounts can
#                       enter (0755), its target a 0644 state with no
#                       credential: the marketplace maintainer's case
#            linkabsent the same link, its target not there yet
#            (default: all five)
#     timed  no gdb: each case N times (default 12) in each order, watched
#            from outside by ../../mode-observer.py (inotify, a snapshot of
#            every file after every batch of events), which prints how long
#            a file holding the new credential was readable by group or
#            other (`span`, ms) -- the window the after-save repair leaves,
#            at this machine's load
#
# Runs shell.qml (one FileView declared as Service.qml's stateFile is) under
# gdb -- ptrace_scope is 1 here, so the probe is gdb's child -- offscreen, on
# a PRIVATE D-Bus (../../private-bus.sh, CLAUDE.md 6b), with no DISPLAY,
# WAYLAND_DISPLAY or Hyprland signature, in a 0700 work folder under
# $TMPDIR that is removed at exit. gdb stops the probe at the writer's
# syscalls -- the open of its temporary (flags, mode), every fchmod, the
# link of the temporary under a name, the rename -- and at each process
# spawn (the helper runs before and after the write), and at each stop
# snap.py lists every file in the state folder and the link's folder with
# its mode and whether it holds the marker. A line `EXPOSED` is a file
# holding the new credential with a group or other bit, seen while the
# probe was stopped: what another account could read at that instant.
# The helper and the argv are this tree's, built through the model
# (Model.statePrivateArgv, Model.stateModeArgv), so the join is a call.
#
# Holds no display, sends no key, starts no compositor and touches nothing
# outside its work folder; the helper's state folder is the work folder's.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
for tool in gdb quickshell node python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP state-private: $tool is not on PATH" >&2; exit 77; }
done
ORDERS="fix base"
TIMED=0 REPEAT=12
case ${1:-both} in
  fix|base) ORDERS=$1; shift ;;
  both) (( $# )) && shift ;;
  timed) TIMED=1; shift; [[ ${1:-} =~ ^[0-9]+$ ]] && { REPEAT=$1; shift; } ;;
esac
CASES=${*:-new e644 e600 link644 linkabsent}
HELPER=${HELPER:-$ROOT/bin/omarchy-iptv}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/d103.XXXXXX") || exit 2
chmod 700 "$WORK"
trap 'rm -rf -- "$WORK"' EXIT
mkdir -m 700 "$WORK/cfg" "$WORK/rt"
cp "$HERE/shell.qml" "$WORK/cfg/shell.qml"
MARKER=D103SECRET$RANDOM
argv_of() {   # the model's argv for verb $1 over state folder $2, as JSON
  node -e 'import(process.argv[1]).then(M => { const f = process.argv[2] === "private" ? M.statePrivateArgv : M.stateModeArgv; process.stdout.write(JSON.stringify(f(process.argv[3], process.argv[4]))) })' \
    "$ROOT/Model.mjs" "$1" "$HELPER" "$2"
}
SEED='{"version":2,"cacheLayout":2,"favorites":["t:restored.uk"],"recents":[],"sources":[],"activeKey":""}'
N=0
run_case() {
  local order=$1 case=$2 c pre="[]" post state wide file
  N=$((N + 1))
  c=$WORK/c$N
  state=$c/state wide=$c/wide file=$c/state/state.json
  mkdir -p "$c"; mkdir -m 700 "$state"; mkdir -m 755 "$wide"
  case $case in
    new) ;;
    e644) printf '%s\n' "$SEED" >"$file"; chmod 644 "$file" ;;
    e600) printf '%s\n' "$SEED" >"$file"; chmod 600 "$file" ;;
    link644) printf '%s\n' "$SEED" >"$wide/state.json"; chmod 644 "$wide/state.json"; ln -s "$wide/state.json" "$file" ;;
    linkabsent) ln -s "$wide/state.json" "$file" ;;
    *) echo "unknown case $case" >&2; return 2 ;;
  esac
  post=$(argv_of mode "$state")
  [[ $order == fix ]] && pre=$(argv_of private "$state")
  if (( TIMED )); then
    local obs=$c/obs i rc
    python3 -I "$ROOT/scripts/dev-harness/mode-observer.py" "$obs" "$MARKER" "$state" "$wide" >"$c/obs.log" 2>&1 &
    local obs_pid=$!
    for ((i = 0; i < 50; i++)); do [[ -s $obs ]] && break; sleep 0.1; done
    env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME \
      XDG_RUNTIME_DIR="$WORK/rt" QT_QPA_PLATFORM=offscreen QML_DISK_CACHE_PATH="$WORK/qmlcache" \
      PROBE_FILE="$file" PROBE_MARKER="$MARKER" PROBE_PRE="$pre" PROBE_POST="$post" \
      "$ROOT/scripts/dev-harness/private-bus.sh" "$WORK/b$N" 60 /usr/bin/quickshell -p "$WORK/cfg" >"$c/qs.log" 2>&1
    rc=$?
    sleep 0.3
    kill -TERM "$obs_pid" 2>/dev/null; wait "$obs_pid" 2>/dev/null
    echo "   TIMED case=$case order=$order rc=$rc $(sed "s#$MARKER#<marker>#g" "$obs")"
    rm -rf -- "$c"
    return 0
  fi
  echo "== CASE $case ORDER $order"
  python3 -I "$HERE/snap.py" before "$MARKER" "$c" "$state" "$wide" | sed 's/^/   /'
  local snap="python3 -I $HERE/snap.py"
  cat >"$c/gdb.x" <<EOF
set pagination off
set confirm off
handle SIGPIPE nostop noprint pass
handle SIG32 nostop noprint pass
handle SIG33 nostop noprint pass
handle SIGCHLD nostop noprint pass
catch syscall openat
condition \$bpnum \$rax == -38 && \$_regex((char*)\$rsi, ".*/c$N/.*")
commands
  silent
  printf "OPENAT %s flags=0x%x mode=0%o\n", (char*)\$rsi, \$rdx, \$r10
  continue
end
catch syscall fchmod
condition \$bpnum \$rax == -38
commands
  silent
  printf "FCHMOD fd=%d mode=0%o\n", \$rdi, \$rsi
  shell $snap fchmod $MARKER $c $state $wide
  continue
end
catch syscall linkat
condition \$bpnum \$rax == -38
commands
  silent
  printf "LINKAT %s\n", (char*)\$r10
  shell $snap linkat $MARKER $c $state $wide
  continue
end
catch syscall rename renameat renameat2
condition \$bpnum \$rax == -38
commands
  silent
  printf "RENAME\n"
  shell $snap rename $MARKER $c $state $wide
  continue
end
catch syscall clone3
condition \$bpnum \$rax == -38 && ((*(unsigned long long *)\$rdi) & 0x10000) == 0
commands
  silent
  printf "SPAWN\n"
  shell $snap spawn $MARKER $c $state $wide
  continue
end
catch syscall clone vfork fork
condition \$bpnum \$rax == -38 && (\$rdi & 0x10000) == 0
commands
  silent
  printf "SPAWN\n"
  shell $snap spawn $MARKER $c $state $wide
  continue
end
run
EOF
  env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME \
    XDG_RUNTIME_DIR="$WORK/rt" QT_QPA_PLATFORM=offscreen QML_DISK_CACHE_PATH="$WORK/qmlcache" DEBUGINFOD_URLS= \
    PROBE_FILE="$file" PROBE_MARKER="$MARKER" PROBE_PRE="$pre" PROBE_POST="$post" \
    "$ROOT/scripts/dev-harness/private-bus.sh" "$WORK/b$N" 90 \
    gdb -batch -nx -x "$c/gdb.x" --args /usr/bin/quickshell -p "$WORK/cfg" 2>&1 \
    | sed 's/\x1b\[[0-9;]*m//g' | grep -a -E '^(OPENAT|FCHMOD|LINKAT|RENAME|SPAWN|SNAP)| PROBE ' \
    | sed "s#$WORK/##g; s#$MARKER#<marker>#g" >"$c/log"
  python3 -I "$HERE/snap.py" after "$MARKER" "$c" "$state" "$wide" >>"$c/log"
  sed 's/^/   /' "$c/log"
  python3 -I - "$c/log" "$case" "$order" <<'PY'
import sys
path, case, order = sys.argv[1:4]
exposed, stops, seen, final = [], 0, 0, "none"
for line in open(path, encoding="utf-8", errors="replace"):
    w = line.split()
    if w and w[0] in ("OPENAT", "FCHMOD", "LINKAT", "RENAME", "SPAWN"):
        stops += 1
    if not w or w[0] != "SNAP" or w[2] == "link":
        continue
    when, mode, holds, name = w[1], int(w[2], 8), w[4] == "1", w[5]
    if when not in ("before", "after"):
        seen += 1
    if holds and mode & 0o077:
        exposed.append("%s:%s:%03o" % (when, name.split("/", 1)[-1], mode))
    if when == "after" and holds:
        final = "%03o" % mode
print("   VERDICT case=%s order=%s stops=%d files-seen=%d exposed=%d final=%s%s"
      % (case, order, stops, seen, len(exposed), final, (" EXPOSED " + " ".join(exposed)) if exposed else ""))
PY
}
for order in $ORDERS; do
  for case in $CASES; do
    if (( TIMED )); then
      for ((r = 0; r < REPEAT; r++)); do run_case "$order" "$case"; done
    else
      run_case "$order" "$case"
    fi
  done
done
