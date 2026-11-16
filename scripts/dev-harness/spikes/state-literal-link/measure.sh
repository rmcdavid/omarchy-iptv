#!/bin/bash
# scripts/dev-harness/spikes/state-literal-link/measure.sh -- D-STATE-9: a
# state.json link whose relative target climbs out of a LINKED folder with
# `..` is saved by QSaveFile to a different file than the one the kernel
# (and so the plugin's read, and the helper) resolves; which file the save
# lands in, and which mode it gets.
#
#   measure.sh [CASE...]
#     r600        the real target 0600, nothing at the literal location
#     r644        the real target 0644 (0.19.1 saved over it as it was)
#     r600-l644   the real target 0600, a 0644 file at the literal location
#     r644-l600   the real target 0644, a 0600 file at the literal location
#     none        no real target, nothing at the literal location
#     nodir       the real target 0600 and NO folder at the literal location
#     r644-private  r644 with the shipping helper's `state private` run
#                 first, the argv Model.statePrivateArgv builds (D-SINK-103)
#     none-private  none, the same
#     chain       a second link at the literal location: two hops, the
#                 second read against the FIRST hop's literal folder
#                 (RESULT-2026-11-14.txt; asked here, not assumed)
#     above       the link under a state folder that is a REAL folder whose
#                 PARENT is a link, the target `../../x/state.json` (a
#                 linked ~/.local/state, say)
#     (default: all)
#
# The layout, under a 0700 work folder in $TMPDIR (removed at exit), for
# every case but `above`:
#   state                 -> T/state   (the state folder is a link)
#   T/state/state.json    -> ../wide/state.json   (relative, climbs with ..)
#   T/wide/state.json     the REAL target: the kernel resolves state.json here
#   wide/state.json       the LITERAL location: state/../wide/state.json
#                         read lexically, as QDir::cleanPath reads it
# probe.cpp, built here against the installed libQt6Core (pkg-config
# Qt6Core), saves `NEW` through QSaveFile and prints every file's mode and
# first line; a VERDICT line names where NEW landed and its mode, against
# where the plugin reads (realpath). Each probe runs on a private D-Bus
# (../../private-bus.sh: no service directories, its own HOME), with no
# DISPLAY, WAYLAND_DISPLAY, Hyprland signature or platform theme, and
# QT_QPA_PLATFORM=offscreen (a QCoreApplication loads no platform plugin;
# set all the same). Touches nothing outside its work folder.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
for tool in g++ pkg-config node python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP state-literal-link: $tool is not on PATH" >&2; exit 77; }
done
pkg-config --exists Qt6Core || { echo "SKIP state-literal-link: no Qt6Core for pkg-config" >&2; exit 77; }
CASES=${*:-r600 r644 r600-l644 r644-l600 none nodir r644-private none-private chain above}
WORK=$(mktemp -d "${TMPDIR:-/tmp}/dst9.XXXXXX") || exit 2
chmod 700 "$WORK"
trap 'rm -rf -- "$WORK"' EXIT
# shellcheck disable=SC2046 # pkg-config's words are separate flags
g++ -std=c++17 -O1 -fPIC -o "$WORK/probe" "$HERE/probe.cpp" $(pkg-config --cflags --libs Qt6Core) || exit 2
private_argv() {   # the model's `state private` argv for state folder $1, one item per line
  node -e 'import(process.argv[1]).then(M => { for (const a of M.statePrivateArgv(process.argv[2], process.argv[3])) process.stdout.write(a + "\n") })' \
    "$ROOT/Model.mjs" "$ROOT/bin/omarchy-iptv" "$1"
}
put() { printf '%s\n' "$2" >"$1"; chmod "$3" "$1"; }
N=0
for case in $CASES; do
  N=$((N + 1))
  c=$WORK/c$N
  mkdir -m 700 "$c"
  umask 022
  if [[ $case == above ]]; then
    mkdir -p "$c/data/state/omarchy-iptv" "$c/data/x" "$c/home/.local/x"
    ln -s "$c/data/state" "$c/home/.local/state"
    ln -s ../../x/state.json "$c/data/state/omarchy-iptv/state.json"
    put "$c/data/x/state.json" REAL 600
    path=$c/home/.local/state/omarchy-iptv/state.json
    files=("$c/data/x/state.json" "$c/home/.local/x/state.json")
  else
    mkdir -m 700 -p "$c/T/state"
    mkdir -m 755 "$c/T/wide"
    [[ $case == nodir ]] || mkdir -m 755 "$c/wide"
    ln -s "$c/T/state" "$c/state"
    path=$c/state/state.json
    files=("$c/T/wide/state.json" "$c/wide/state.json")
    case $case in
      r600|nodir) put "$c/T/wide/state.json" REAL 600 ;;
      r644|r644-private) put "$c/T/wide/state.json" REAL 644 ;;
      r600-l644) put "$c/T/wide/state.json" REAL 600; put "$c/wide/state.json" LITERAL 644 ;;
      r644-l600) put "$c/T/wide/state.json" REAL 644; put "$c/wide/state.json" LITERAL 600 ;;
      none|none-private) ;;
      chain)
        mkdir -m 755 "$c/T/a" "$c/a"
        put "$c/T/a/state.json" REAL 600
        ln -s ../wide/state.json "$c/a/state.json"
        files=("$c/T/a/state.json" "$c/a/state.json" "$c/wide/state.json") ;;
      *) echo "unknown case $case" >&2; exit 2 ;;
    esac
    if [[ $case == chain ]]; then
      ln -s ../a/state.json "$c/T/state/state.json"
    else
      ln -s ../wide/state.json "$c/T/state/state.json"
    fi
  fi
  echo "== CASE $case"
  if [[ $case == *-private ]]; then
    mapfile -t argv < <(private_argv "$(dirname "$path")")
    reply=$(env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME "${argv[@]}" 2>&1)
    echo "  private rc=$? $reply" | sed "s#$c/##g"
  fi
  env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME QT_QPA_PLATFORM=offscreen \
    "$ROOT/scripts/dev-harness/private-bus.sh" "$WORK/b$N" 30 "$WORK/probe" "$path" "${files[@]}" 2>&1 \
    | grep -v '^private-bus.sh: bus pid' | sed "s#$c/##g" >"$WORK/out$N"
  cat "$WORK/out$N"
  python3 -I - "$WORK/out$N" "$case" <<'PY'
import sys
lines = open(sys.argv[1], encoding="utf-8", errors="replace").read().splitlines()
read = next((l.split(None, 1)[1] for l in lines if l.strip().startswith("realpath")), "?").strip()
landed = [l.split()[1] + ":" + l.split()[3] for l in lines if l.strip().startswith("FILE") and "text 'NEW'" in l]
failed = any("open failed" in l for l in lines)
where = "none" if not landed else " ".join(landed)
same = "n/a" if not landed else ("yes" if any(x.split(":")[0] == read for x in landed) else "NO")
print("  VERDICT case=%s read=%s landed=%s same-file=%s%s" % (sys.argv[2], read, where, same, " open-failed" if failed else ""))
PY
done
