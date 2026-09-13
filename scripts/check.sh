#!/bin/bash
# scripts/check.sh -- the whole quality gate for omarchy-iptv, in one command.
#   1. omarchy plugin validate   (manifest schema, entry points, no symlinks)
#   2. qmllint on every .qml     (qs.Commons / qs.Ui mapped through /tmp/qmlroot)
#   3. node tests                (tests/Model.test.js)
#   4. python tests              (python3 -m unittest discover -s tests)
#   5. QML spec                  (qmltestrunner on tests/Model.spec.qml)
#   6. ASCII check on code files (glyphs are allowed in .qml only)
# Exit status is non-zero if any gate fails. qmllint *warnings* are reported
# but do not fail the gate (the first-party widgets trigger the same
# unqualified-access / missing-property warnings); qmllint *errors* do.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
QMLROOT=${QMLROOT:-/tmp/qmlroot}
QT_BIN=${QT_BIN:-/usr/lib/qt6/bin}
QML_IMPORTS=${QML_IMPORTS:-/usr/lib/qt6/qml}
SHELL_DIR=${OMARCHY_PATH:-/usr/share/omarchy}/shell
fail=0

step() { printf '\n== %s\n' "$*"; }
ok()   { printf 'ok   %s\n' "$*"; }
bad()  { printf 'FAIL %s\n' "$*"; fail=1; }

step "omarchy plugin validate $ROOT"
if omarchy plugin validate "$ROOT"; then ok "manifest valid"; else bad "manifest invalid"; fi

step "qmllint (imports: $QMLROOT, $QML_IMPORTS)"
mkdir -p "$QMLROOT/qs"
ln -sfn "$SHELL_DIR/Commons" "$QMLROOT/qs/Commons"
ln -sfn "$SHELL_DIR/Ui" "$QMLROOT/qs/Ui"
if [[ ! -x "$QT_BIN/qmllint" ]]; then
  bad "qmllint not found at $QT_BIN/qmllint (pacman -S qt6-declarative)"
else
  for file in "$ROOT"/*.qml "$ROOT"/tests/*.qml; do
    [[ -f $file ]] || continue
    output=$("$QT_BIN/qmllint" -I "$QMLROOT" -I "$QML_IMPORTS" "$file" 2>&1)
    lint_status=$?
    errors=$(grep -c -E '^Error:|: error:|Error at' <<<"$output")
    (( lint_status == 0 )) || errors=$(( errors + 1 ))
    warnings=$(grep -c -E 'Warning:|: warning:' <<<"$output")
    if (( errors > 0 )); then
      bad "$(basename "$file"): $errors error(s), $warnings warning(s)"
      printf '%s\n' "$output"
    else
      ok "$(basename "$file"): 0 errors, $warnings warning(s)"
      if [[ ${CHECK_VERBOSE:-0} == 1 && -n $output ]]; then printf '%s\n' "$output"; fi
    fi
  done
fi

step "node tests/Model.test.js"
if command -v node >/dev/null 2>&1; then
  if node "$ROOT/tests/Model.test.js"; then ok "node tests"; else bad "node tests"; fi
else
  bad "node not found (dev-only dependency: mise use node)"
fi

step "python3 -m unittest discover -s tests"
if (cd "$ROOT" && python3 -m unittest discover -s tests); then ok "python tests"; else bad "python tests"; fi

step "qmltestrunner tests/Model.spec.qml"
if [[ -x "$QT_BIN/qmltestrunner" ]]; then
  if QT_QPA_PLATFORM=offscreen "$QT_BIN/qmltestrunner" -input "$ROOT/tests/Model.spec.qml" >/tmp/omarchy-iptv-qmltest.log 2>&1; then
    ok "qml spec ($(grep -c '^PASS' /tmp/omarchy-iptv-qmltest.log) passed)"
  else
    bad "qml spec"; cat /tmp/omarchy-iptv-qmltest.log
  fi
else
  bad "qmltestrunner not found at $QT_BIN/qmltestrunner"
fi

step "ascii check (code files)"
ascii_bad=0
for file in "$ROOT"/Model.js "$ROOT"/bin/omarchy-iptv "$ROOT"/manifest.json "$ROOT"/scripts/check.sh "$ROOT"/tests/*.py "$ROOT"/tests/*.js "$ROOT"/tests/fixtures/* "$ROOT"/docs/ARCHITECTURE.md; do
  [[ -f $file ]] || continue
  if LC_ALL=C grep -n -P '[^\x00-\x7F]' "$file" >/dev/null; then
    printf 'non-ASCII bytes in %s:\n' "$file"; LC_ALL=C grep -n -P '[^\x00-\x7F]' "$file" | head -5
    ascii_bad=1
  fi
done
if (( ascii_bad )); then bad "ascii check"; else ok "ascii check"; fi

printf '\n'
if (( fail )); then echo "check.sh: FAILED"; exit 1; fi
echo "check.sh: all green"
