#!/bin/bash
# scripts/dev-harness/spikes/state-literal-link/measure.sh -- D-STATE-9: a
# state.json link whose relative target climbs out of a LINKED folder with
# `..` is saved by QSaveFile to a different file than the one the kernel
# (and so the plugin's read, and the helper) resolves; which file the save
# lands in, which mode it gets, and (since the guard, 2026-11-21) whether the
# shipping helper's reading of the link names that same file.
#
#   measure.sh [CASE...]      the cases below (default: all)
#   measure.sh --clean        print tests/fixtures/qt-clean-path.json:
#                             QDir::cleanPath over judge.py's corpus
#
# The first ten, measured since 2026-11-14 (RESULT-2026-11-14.txt):
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
#     above       the link under a state folder that is a REAL folder whose
#                 PARENT is a link, the target `../../x/state.json` (a
#                 linked ~/.local/state, say)
# Added with the guard (2026-11-21), each with the real `state private` run
# first: layouts it must NOT refuse --
#     plain       no link at all: state.json a regular file
#     abs         an absolute link, through the linked state folder
#     rel         a relative link with no `..`, in a real state folder
#     inlinked    a link inside the linked state folder to a sibling file
#     samedir     a link inside the linked state folder whose `..` climbs out
#                 of it and back into a folder of the same name: two strings,
#                 one file
#     sync        an absolute target through a linked folder (~/Sync ->
#                 /mnt/data/Sync)
#     dotdot      a relative `..` target where no folder it climbs out of is
#                 a link
# -- and layouts it must refuse, beside the ten:
#     chain2      `chain` one folder deeper: T/state/state.json ->
#                 ../a/b/state.json, the literal a/b/state.json ->
#                 ../w/state.json, so the second hop's folder is not the
#                 first's parent (a walk that joined every hop to the first
#                 hop's folder would answer w/state.json)
#     hardlink    r600 with the literal file a HARD link of the real one: one
#                 inode, two entries
#     loop        a literal self-loop at the literal location, where the
#                 kernel resolves the path to a real file
#     selfloop    state.json -> state.json: the kernel cannot resolve it
#                 either (refused by the verb as unreachable, not as split)
# Added by the review of the guard (2026-11-21), each with `state private`:
#     hardlink2   the two readings end in ONE folder under two names that
#                 are hard links: state.json -> ../x/b.json, T/x -> R, a real
#                 x/b.json -> ../R/a.json; the kernel reads R/b.json, the
#                 literal reading R/a.json, one inode (refused)
#     twofiles2   the same with R/a.json a file of its own (refused)
#     chain41     41 links on the literal reading, 2 on the kernel's, ending
#                 at the kernel's file (not refused: QSaveFile follows them)
#     chain127    the same with 127, QSaveFile's last (not refused)
#     chain128    the same with 128: past QSaveFile's bound it writes over
#                 the path itself, replacing the link (refused)
#     nonutf8     state.json -> b"\xff.json" in a real folder: QSaveFile
#                 reads the byte as U+FFFD and writes that name (refused)
#
# The layout, under a 0700 work folder in $TMPDIR (removed at exit), for the
# first ten but `above`:
#   state                 -> T/state   (the state folder is a link)
#   T/state/state.json    -> ../wide/state.json   (relative, climbs with ..)
#   T/wide/state.json     the REAL target: the kernel resolves state.json here
#   wide/state.json       the LITERAL location: state/../wide/state.json
#                         read lexically, as QDir::cleanPath reads it
# probe.cpp, built here against the installed libQt6Core (pkg-config
# Qt6Core), saves `NEW` through QSaveFile and prints every file's mode and
# first line; a VERDICT line names where NEW landed and its mode, against
# where the plugin reads (realpath). judge.py loads the shipping helper (no
# bytecode written) and, BEFORE the save, records its literal reading and
# its split verdict (read-only); AFTER it, a CHECK line asserts that the
# helper's literal file is the one holding NEW, and that its verdict is
# exactly "the save missed the kernel's file" and the case's expectation.
# Each probe runs UNDER GDB (handle all nopass; a crash is then gdb's to
# report, never a crash card) on a private D-Bus (../../private-bus.sh: no
# service directories, its own HOME), with no DISPLAY, WAYLAND_DISPLAY,
# Hyprland signature or platform theme, debuginfod off, and
# QT_QPA_PLATFORM=offscreen (a QCoreApplication loads no platform plugin;
# set all the same). Touches nothing outside its work folder. Exit 1 when a
# CHECK fails. A byte that is not ASCII is printed as a \x escape, so the
# output stays ASCII (nonutf8).
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
for tool in g++ pkg-config gdb node python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP state-literal-link: $tool is not on PATH" >&2; exit 77; }
done
pkg-config --exists Qt6Core || { echo "SKIP state-literal-link: no Qt6Core for pkg-config" >&2; exit 77; }
WORK=$(mktemp -d "${TMPDIR:-/tmp}/dst9.XXXXXX") || exit 2
chmod 700 "$WORK"
trap 'rm -rf -- "$WORK"' EXIT
# shellcheck disable=SC2046 # pkg-config's words are separate flags
g++ -std=c++17 -O1 -fPIC -o "$WORK/probe" "$HERE/probe.cpp" $(pkg-config --cflags --libs Qt6Core) || exit 2
NB=0
under_gdb() {   # ARGS... -> the probe's own lines (two-space or CLEAN), gdb's dropped
  NB=$((NB + 1))
  env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME \
    DEBUGINFOD_URLS= QT_QPA_PLATFORM=offscreen \
    "$ROOT/scripts/dev-harness/private-bus.sh" "$WORK/b$NB" 60 \
    gdb -batch -nx -iex 'set debuginfod enabled off' -ex 'set pagination off' -ex 'handle all nopass' \
      -ex run -ex kill --args "$WORK/probe" "$@" 2>&1 | grep -a -E '^(  |CLEAN )'
}
if [[ ${1:-} == --clean ]]; then
  mapfile -t hexes < <(python3 -I -B "$HERE/judge.py" corpus)
  under_gdb --clean "${hexes[@]}" >"$WORK/clean"
  qt=$(pkg-config --modversion Qt6Core)
  if command -v pacman >/dev/null 2>&1; then qt=$(pacman -Q qt6-base 2>/dev/null || echo "$qt"); fi
  python3 -I -B "$HERE/judge.py" fixture "$WORK/clean" "$qt"
  exit $?
fi
CASES=${*:-r600 r644 r600-l644 r644-l600 none nodir r644-private none-private chain above plain abs rel inlinked samedir sync dotdot chain2 hardlink loop selfloop hardlink2 twofiles2 chain41 chain127 chain128 nonutf8}
private_argv() {   # the model's `state private` argv for state folder $1, one item per line
  node -e 'import(process.argv[1]).then(M => { for (const a of M.statePrivateArgv(process.argv[2], process.argv[3])) process.stdout.write(a + "\n") })' \
    "$ROOT/Model.mjs" "$ROOT/bin/omarchy-iptv" "$1"
}
put() { printf '%s\n' "$2" >"$1"; chmod "$3" "$1"; }
N=0 FAILS=0
for case in $CASES; do
  N=$((N + 1))
  c=$WORK/c$N
  mkdir -m 700 "$c"
  umask 022
  private=no expect=yes
  case $case in
    above)
      mkdir -p "$c/data/state/omarchy-iptv" "$c/data/x" "$c/home/.local/x"
      ln -s "$c/data/state" "$c/home/.local/state"
      ln -s ../../x/state.json "$c/data/state/omarchy-iptv/state.json"
      put "$c/data/x/state.json" REAL 600
      path=$c/home/.local/state/omarchy-iptv/state.json
      files=("$c/data/x/state.json" "$c/home/.local/x/state.json") ;;
    plain)
      private=yes expect=no
      mkdir -m 700 "$c/state"
      put "$c/state/state.json" REAL 600
      path=$c/state/state.json
      files=("$c/state/state.json") ;;
    rel)
      private=yes expect=no
      mkdir -m 700 -p "$c/state/sub"
      put "$c/state/sub/state.json" REAL 600
      ln -s sub/state.json "$c/state/state.json"
      path=$c/state/state.json
      files=("$c/state/sub/state.json") ;;
    sync|dotdot)
      private=yes expect=no
      mkdir -m 700 -p "$c/home/.local/state/omarchy-iptv"
      if [[ $case == sync ]]; then
        mkdir -p "$c/mnt/data/Sync"
        ln -s "$c/mnt/data/Sync" "$c/home/Sync"
        put "$c/mnt/data/Sync/state.json" REAL 600
        ln -s "$c/home/Sync/state.json" "$c/home/.local/state/omarchy-iptv/state.json"
        files=("$c/mnt/data/Sync/state.json")
      else
        mkdir -p "$c/home/.local/dotfiles"
        put "$c/home/.local/dotfiles/state.json" REAL 600
        ln -s ../../dotfiles/state.json "$c/home/.local/state/omarchy-iptv/state.json"
        files=("$c/home/.local/dotfiles/state.json")
      fi
      path=$c/home/.local/state/omarchy-iptv/state.json ;;
    selfloop)
      private=yes expect=no
      mkdir -m 700 "$c/state"
      ln -s state.json "$c/state/state.json"
      path=$c/state/state.json
      files=("$c/state/state.json") ;;
    hardlink2|twofiles2)
      private=yes
      mkdir -m 700 -p "$c/T/state"
      ln -s "$c/T/state" "$c/state"
      mkdir -m 755 "$c/R" "$c/x"
      ln -s "$c/R" "$c/T/x"
      put "$c/R/b.json" REAL 600
      ln -s ../R/a.json "$c/x/b.json"
      if [[ $case == hardlink2 ]]; then ln "$c/R/b.json" "$c/R/a.json"; else put "$c/R/a.json" OTHER 600; fi
      ln -s ../x/b.json "$c/T/state/state.json"
      path=$c/state/state.json
      files=("$c/R/b.json" "$c/R/a.json") ;;
    chain41|chain127|chain128)
      private=yes
      n=${case#chain}
      (( n == 128 )) || expect=no
      mkdir -m 700 -p "$c/T/state"
      ln -s "$c/T/state" "$c/state"
      mkdir -m 755 "$c/T/l" "$c/l"
      put "$c/T/l/s0" REAL 600
      ln -s ../l/s0 "$c/T/state/state.json"
      for ((k = 0; k < n - 2; k++)); do ln -s "s$((k + 1))" "$c/l/s$k"; done
      ln -s "$c/T/l/s0" "$c/l/s$((n - 2))"
      path=$c/state/state.json
      files=("$c/T/l/s0" "$c/T/state/state.json") ;;
    nonutf8)
      private=yes
      mkdir -m 700 "$c/state"
      put "$c/state/"$'\xff'.json REAL 600
      ln -s $'\xff'.json "$c/state/state.json"
      path=$c/state/state.json
      files=("$c/state/"$'\xff'.json "$c/state/"$'\xef\xbf\xbd'.json) ;;
    *)
      mkdir -m 700 -p "$c/T/state"
      mkdir -m 755 "$c/T/wide"
      [[ $case == nodir ]] || mkdir -m 755 "$c/wide"
      ln -s "$c/T/state" "$c/state"
      path=$c/state/state.json
      files=("$c/T/wide/state.json" "$c/wide/state.json")
      link=../wide/state.json
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
          link=../a/state.json
          files=("$c/T/a/state.json" "$c/a/state.json" "$c/wide/state.json") ;;
        chain2)
          private=yes
          mkdir -m 755 -p "$c/T/a/b" "$c/a/b" "$c/a/w" "$c/w"
          put "$c/T/a/b/state.json" REAL 600
          ln -s ../w/state.json "$c/a/b/state.json"
          link=../a/b/state.json
          files=("$c/T/a/b/state.json" "$c/a/b/state.json" "$c/a/w/state.json" "$c/w/state.json") ;;
        abs)
          private=yes expect=no
          put "$c/T/wide/state.json" REAL 600
          link=$c/T/wide/state.json ;;
        inlinked|samedir)
          private=yes expect=no
          put "$c/T/state/state.real.json" REAL 600
          link=state.real.json
          [[ $case == samedir ]] && link=../state/state.real.json
          files=("$c/T/state/state.real.json") ;;
        hardlink)
          private=yes
          put "$c/T/wide/state.json" REAL 600
          ln "$c/T/wide/state.json" "$c/wide/state.json" ;;
        loop)
          private=yes
          mkdir -m 755 "$c/T/a" "$c/a"
          put "$c/T/a/state.json" REAL 600
          ln -s ../a/state.json "$c/a/state.json"
          link=../a/state.json
          files=("$c/T/a/state.json" "$c/a/state.json" "$c/T/state/state.json") ;;
        *) echo "unknown case $case" >&2; exit 2 ;;
      esac
      [[ $case == *-private ]] && private=yes
      ln -s "$link" "$c/T/state/state.json" ;;
  esac
  echo "== CASE $case"
  python3 -I -B "$HERE/judge.py" before "$ROOT" "$path" "$WORK/v$N" || exit 2
  if [[ $private == yes ]]; then
    mapfile -t argv < <(private_argv "$(dirname "$path")")
    reply=$(env -u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QT_QPA_PLATFORMTHEME "${argv[@]}" 2>&1)
    echo "  private rc=$? $reply" | LC_ALL=C sed "s#$c/##g"
  fi
  under_gdb "$path" "${files[@]}" | LC_ALL=C sed "s#$c/##g" >"$WORK/out$N"
  python3 -I -c 'import sys; sys.stdout.write(open(sys.argv[1], "rb").read().decode("ascii", "backslashreplace"))' "$WORK/out$N"
  python3 -I - "$WORK/out$N" "$case" <<'PY'
import sys
# Bytes, not text: a name that is not UTF-8 and the U+FFFD name QSaveFile
# writes for it would read as one name decoded (nonutf8).
lines = open(sys.argv[1], "rb").read().splitlines()
read = next((l.split(None, 1)[1] for l in lines if l.strip().startswith(b"realpath")), b"?").strip()
landed = [l.split()[1] + b":" + l.split()[3] for l in lines if l.strip().startswith(b"FILE") and b"text 'NEW'" in l]
failed = any(b"open failed" in l for l in lines)
where = b"none" if not landed else b" ".join(landed)
same = "n/a" if not landed else ("yes" if any(x.split(b":")[0] == read for x in landed) else "NO")
show = lambda b: b.decode("ascii", "backslashreplace")
print("  VERDICT case=%s read=%s landed=%s same-file=%s%s" % (sys.argv[2], show(read), show(where), same, " open-failed" if failed else ""))
PY
  python3 -I -B "$HERE/judge.py" after "$WORK/v$N" "$WORK/out$N" "$case" "$expect" "$c" || FAILS=$((FAILS + 1))
done
echo "# checks failed: $FAILS"
(( FAILS == 0 ))
