#!/bin/bash
# scripts/dev-harness/spikes/logo-decode-bomb/run.sh -- the measurement that
# D-LOGO-11 rests on, kept so "measured" means "re-runnable":
#
#   scripts/dev-harness/spikes/logo-decode-bomb/run.sh [--only a,b,...]
#       [--extra <file> ...] [--with-encoder] [--no-bracket] [--keep]
#
# How much memory does the shell's row logo slot allocate for a logo whose
# HEADER declares a size its BYTES never deliver? One Image per run, declared
# as Guide.qml declares the slot (probe-tmpl.qml), pointed at one file from
# the corpus make-corpus.py builds, run offscreen under an ADDRESS-SPACE
# RLIMIT of 2.5 GB (util-linux `prlimit --as`) on the qml process ONLY, so
# that a bomb is refused by the allocator inside the probe and never reaches
# the desktop. peakrun.py reports the child's exit status and its ru_maxrss.
# Every row is a fresh process; nothing is shared.
#
# WHY AN RLIMIT AND NOT A SERVICE-MANAGER SCOPE. The lead's first measurement
# (2026-10-09) capped the probe with a user-session memory scope at 1.5 GB,
# and the two 65500x65500 progressive rows ended in a SIGKILL at the cap. Two
# things are wrong with that for a file under scripts/: the marketplace
# capability scan reads the scope tool's name as service management wherever
# it appears in a tracked file, comment or not, and the harness lane's first
# commit turned that gate red with six such lines; and a kill is a worse
# answer than a refusal. Under RLIMIT_AS the allocator says no to a request
# the limit cannot hold, Qt reports Image.Error, and the probe exits 1 at a
# measured peak -- the same figures everywhere else (72 MB control, 840 MB
# for the 304-byte bomb, 1,239 MB for the 555-byte one), re-measured
# 2026-10-11 and tabled in README.md with the scope figures beside them.
#
# The `expect` column is a BAND, not a number: peak RSS moves a few MB
# between runs, so each row is judged against a band wide enough for that
# and narrow enough that a Qt which learns to scale PNG during decode, or a
# libjpeg that stops honouring the SOF, shows up as DIFF rather than vanishing
# into a retake. A row's band is one of:
#     ready<150      Image.Ready at control memory (the controls, the good logo)
#     error<150      Image.Error at control memory (the handlers that decode
#                    full-size and hand Qt's limit the real number, and a
#                    request the rlimit refuses before anything is touched)
#     ready>N        Image.Ready after resident-setting more than N MB (the finding)
#     error>N        Image.Error after resident-setting more than N MB: the
#                    allocator refused inside the rlimit, part way in
#
# Needs: python3, util-linux prlimit and /usr/lib/qt6/bin/qml (exit 77
# without them, with the reason). No display, no network, nothing shipped is
# loaded. Writes under a mktemp directory it removes unless --keep.
set -uo pipefail
QML_BIN=${LOGO_QML_BIN:-/usr/lib/qt6/bin/qml}
# RLIMIT_AS in bytes on the qml process alone; logo-scenario.sh uses the same
# number and says why it is address space rather than resident set.
CAP_AS=2500000000
ONLY=""
EXTRA=()
WITH_ENCODER=""
BRACKET=1
KEEP=0
while (($# > 0)); do
  case $1 in
    --only) [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--only needs a name list" >&2; exit 2; }; ONLY=$2; shift ;;
    --extra) [[ -f ${2:-} ]] || { echo "--extra needs an existing file, got '${2:-}'" >&2; exit 2; }; EXTRA+=("$(realpath "$2")"); shift ;;
    --with-encoder) WITH_ENCODER=--with-encoder ;;
    --no-bracket) BRACKET=0 ;;
    --keep) KEEP=1 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
# Tool checks before any external command (builtins only up to here), so an
# empty PATH prints the reason and nothing else.
for tool in python3 prlimit; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP: $tool is not on PATH" >&2; exit 77; }
done
[[ -x $QML_BIN ]] || { echo "SKIP: $QML_BIN is not here (qt6-declarative)" >&2; exit 77; }
prlimit --as=$CAP_AS -- true 2>/dev/null \
  || { echo "SKIP: prlimit cannot set an address-space limit of $CAP_AS on this machine" >&2; exit 77; }
HERE=${BASH_SOURCE[0]%/*}
[[ $HERE == "${BASH_SOURCE[0]}" ]] && HERE=.
HERE=$(cd "$HERE" && pwd)

WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-logobomb.XXXXXX") || exit 2
chmod 0700 "$WORK"
cleanup() { (( KEEP )) && { echo "== kept $WORK"; return; }; rm -rf "$WORK"; }
trap cleanup EXIT

echo "== corpus"
if ! python3 "$HERE/make-corpus.py" "$WORK/corpus" ${ONLY:+--only "$ONLY"} $WITH_ENCODER; then
  echo "make-corpus failed" >&2; exit 2
fi
for f in "${EXTRA[@]+"${EXTRA[@]}"}"; do cp "$f" "$WORK/corpus/"; done

# probe <file> <sourceSize> [maxalloc MiB] -> "rc=<n> peak_mb=<n> wall_ms=<n>"
probe() {
  local file=$1 size=$2 alloc=${3:-} qml out line
  qml="$WORK/probe-$$-$RANDOM.qml"
  sed -e "s|__PATH__|$file|" -e "s|__SOURCE_SIZE__|$size|" "$HERE/probe-tmpl.qml" >"$qml"
  # The ONLY invocation that keeps the desktop safe: the rlimit wraps the
  # qml process alone (prlimit execs the command in place, measured: the
  # pid it runs under is the pid peakrun spawned). Wrapping the reporter too
  # would make a refused allocation in the reporter the end of the
  # measurement.
  out=$(PEAKRUN_TIMEOUT=90 python3 "$HERE/peakrun.py" prlimit --as=$CAP_AS -- \
          env QT_QPA_PLATFORM=offscreen ${alloc:+QT_IMAGEIO_MAXALLOC=$alloc} "$QML_BIN" "$qml" 2>&1)
  line=$(printf '%s\n' "$out" | grep -a '^PEAKRUN ' | tail -1)
  local rc kb ms
  rc=$(printf '%s' "$line" | sed -n 's/.*rc=\(-\{0,1\}[0-9]*\).*/\1/p')
  kb=$(printf '%s' "$line" | sed -n 's/.*peak_rss_kb=\([0-9]*\).*/\1/p')
  ms=$(printf '%s' "$line" | sed -n 's/.*wall_ms=\([0-9]*\).*/\1/p')
  [[ -n $rc && -n $kb ]] || { printf 'rc=NA peak_mb=NA wall_ms=NA\n'; return; }
  printf 'rc=%s peak_mb=%d wall_ms=%s\n' "$rc" "$((kb / 1024))" "$ms"
}

outcome() {   # rc -> word
  # -9 would be a kill from OUTSIDE the probe (the kernel's OOM killer, or a
  # hand): no band expects it, so it is always a DIFF with a name.
  case $1 in 0) echo ready ;; 1) echo error ;; 2) echo timeout ;; -9) echo killed ;; *) echo "rc$1" ;; esac
}

judge() {     # <band> <rc> <peak_mb> -> MATCH | DIFF
  local band=$1 rc=$2 mb=$3
  case $band in
    'ready<150')  [[ $rc == 0 && $mb -lt 150 ]] ;;
    'error<150')  [[ $rc == 1 && $mb -lt 150 ]] ;;
    'ready>'*)    [[ $rc == 0 && $mb -gt ${band#ready>} ]] ;;
    'error>'*)    [[ $rc == 1 && $mb -gt ${band#error>} ]] ;;
    *)            false ;;
  esac && echo MATCH || echo DIFF
}

# The rows. name | sourceSize | band. Files absent from the corpus (an --only
# subset, or an encoder file nobody supplied) are reported as "absent" and
# never judged, so a partial run cannot read as a full one.
ROWS=(
  "ctl-base-64.jpg            44  ready<150"
  "ctl-prog-64.jpg            44  ready<150"
  "ctl-prog-rgb-64.jpg        44  ready<150"
  "ctl-png-64.png             44  ready<150"
  "ctl-gif-64.gif             44  ready<150"
  "ctl-webp-64.webp           44  error<150"
  "good-512.png               44  ready<150"
  "good-1920x1080.png         44  ready<150"
  "edge-at-bound.jpg          44  ready<150"
  "edge-at-bound.png          44  ready<150"
  "valid-prog-12k.jpg         44  ready>250"
  "enc-prog-12000.jpg         44  ready>250"
  "bomb-base-20000.jpg        44  ready<150"
  "bomb-base-65500.jpg        44  ready>300"
  "bomb-prog-20000.jpg        44  ready>700"
  "bomb-prog-20000.jpg       223  ready>700"
  "bomb-prog-rgb-20000.jpg    44  ready>1000"
  "bomb-prog-65500.jpg        44  error>200"
  "bomb-prog-rgb-65500.jpg    44  error<150"
  "bomb-png-20000.png         44  error<150"
  "bomb-png-65500.png         44  error<150"
  "valid-png-20000.png        44  error<150"
  "valid-png-65500.png        44  error<150"
  "bomb-gif-20000.gif         44  error<150"
  "bomb-gif-65500.gif         44  error<150"
  "valid-gif-canvas-20000.gif 44  error<150"
  "valid-gif-canvas-65500.gif 44  error<150"
  "bomb-webp-16383.webp       44  error<150"
  "ctl-exif-thumb-64.jpg      44  ready<150"
  "bomb-exif-thumb-20000.jpg  44  ready>700"
  "bomb-column-64x65535.jpg   44  error<150"
  "bomb-gif-second-frame-65500.gif 44 ready<150"
)

echo
echo "== the table (rlimit AS=$CAP_AS bytes on the qml process only; sourceSize is the slot's: 44 row, 223 wall)"
printf '%-28s %5s %9s %-12s %8s %8s %8s %s\n' file size bytes declares outcome peak_mb wall_ms verdict
diff_rows=0; judged=0
for row in "${ROWS[@]}"; do
  read -r name size band <<<"$row"
  file="$WORK/corpus/$name"
  if [[ ! -f $file ]]; then
    printf '%-28s %5s %9s %-12s %8s\n' "$name" "$size" - - absent
    continue
  fi
  bytes=$(stat -c %s "$file")
  # The generator knows what its own files declare; an --extra file (the
  # lead's encoder-made 12000x12000 JPEG) is labelled as what it is rather
  # than read, because reading a header here would be a second parser beside
  # the helper's, and the column is for the reader.
  declares=$(python3 "$HERE/make-corpus.py" --list | awk -v n="$name" '$1 == n { print $3 }')
  [[ -n $declares ]] || declares="(extra)"
  r=$(probe "$file" "$size")
  rc=${r#rc=}; rc=${rc%% *}
  mb=${r#*peak_mb=}; mb=${mb%% *}
  ms=${r##*wall_ms=}
  v=$(judge "$band" "$rc" "$mb")
  judged=$((judged + 1)); [[ $v == DIFF ]] && diff_rows=$((diff_rows + 1))
  printf '%-28s %5s %9s %-12s %8s %8s %8s %s (expect %s)\n' "$name" "$size" "$bytes" "${declares:-?}" "$(outcome "$rc")" "$mb" "$ms" "$v" "$band"
done

if (( BRACKET )) && [[ -f $WORK/corpus/bomb-prog-20000.jpg ]]; then
  echo
  echo "== QT_IMAGEIO_MAXALLOC bracket on bomb-prog-20000.jpg at sourceSize 44"
  echo "   ceil(20000/8)^2 * 4 = 2500^2 * 4 = 23.8 MiB: Qt's limit is compared against the image"
  echo "   already divided by libjpeg's largest scale denominator, so the threshold sits between 20 and 26"
  printf '%-8s %8s %8s %s\n' MiB outcome peak_mb verdict
  for alloc in 5 7 10 20 26 30; do
    r=$(probe "$WORK/corpus/bomb-prog-20000.jpg" 44 "$alloc")
    rc=${r#rc=}; rc=${rc%% *}
    mb=${r#*peak_mb=}; mb=${mb%% *}
    if (( alloc <= 20 )); then band='error<150'; else band='ready>700'; fi
    v=$(judge "$band" "$rc" "$mb")
    judged=$((judged + 1)); [[ $v == DIFF ]] && diff_rows=$((diff_rows + 1))
    printf '%-8s %8s %8s %s (expect %s)\n' "$alloc" "$(outcome "$rc")" "$mb" "$v" "$band"
  done
fi

echo
echo "logo-decode-bomb: $judged rows judged, $diff_rows DIFF (qt6 $("$QML_BIN" --version 2>/dev/null | head -1 || echo unknown))"
(( diff_rows == 0 && judged > 0 ))
