#!/bin/bash
# scripts/check.sh -- the whole quality gate for omarchy-iptv, in one command.
#   1. omarchy plugin validate   (manifest schema, entry points, no symlinks)
#   2. qmllint on every .qml     (qs.Commons / qs.Ui mapped through $QMLROOT),
#                                INCLUDING the dev-harness fake (CLAUDE.md 10)
#   3. node tests                (tests/Model.test.js)
#   4. python tests              (python3 -m unittest discover -s tests)
#   5. QML spec                  (qmltestrunner on tests/Model.spec.qml)
#   6. harness predicates        (scripts/qa-lib-test.sh)
#   6b. chno-entry preflight     (scripts/dev-harness/chno-entry-scenario.sh check-tree)
#   7. ASCII check on code files (glyphs are allowed in .qml only)
# Exit status is non-zero if any gate fails. qmllint *warnings* are reported
# but do not fail the gate (the first-party widgets trigger the same
# unqualified-access / missing-property warnings); qmllint *errors* do.
#
# EVERY COUNT THIS FILE PRINTS IS ALSO ASSERTED. A runner that exits 0 having
# executed nothing is the failure this whole cleanup round is about: the gate
# used to print `ok   qml spec (0 passed)` and stay green, and an emptied
# tests/ directory made `Ran 0 tests ... OK`. Raise a floor when you add
# tests; never lower one to make a run green.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# E4: QMLROOT was a fixed /tmp/qmlroot and the mkdir and both ln statuses were
# discarded. If that directory exists owned by someone else the symlink
# refresh fails silently and qmllint resolves qs.Commons / qs.Ui against
# whatever is planted there - the import root of the entire lint gate.
CHECK_TMP=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-check-XXXXXX")
trap 'rm -rf "$CHECK_TMP"' EXIT
QMLROOT=${QMLROOT:-$CHECK_TMP/qmlroot}
QT_BIN=${QT_BIN:-/usr/lib/qt6/bin}
QML_IMPORTS=${QML_IMPORTS:-/usr/lib/qt6/qml}
SHELL_DIR=${OMARCHY_PATH:-/usr/share/omarchy}/shell
fail=0

# Recorded expected counts. These are floors, not decoration: each runner
# below is capable of exiting 0 having run nothing at all.
#
# All three of the suite floors had fallen behind what the suites actually run
# -- python 260, node 954, the qml spec 47, against the numbers below -- so
# between a fifth and a half of each suite could have stopped executing with
# the gate still green. Raised to what M2-03 leaves behind. Raise a floor when
# you add tests; never lower one to make a run green.
#
# M2-05 integration raises all three to exactly what the suites now run, so a
# suite that stops executing even one case is red here rather than quietly
# smaller. Adding a test means bumping the number in the same commit; that is
# the intended cost.
QML_SPEC_MIN=${QML_SPEC_MIN:-61}
NODE_CHECKS_MIN=${NODE_CHECKS_MIN:-1249}
PY_TESTS_MIN=${PY_TESTS_MIN:-357}
QMLLINT_FILES_MIN=${QMLLINT_FILES_MIN:-5}
# The M2-03 entry preflight: 20 seams plus its own "ran every check" line.
CHNO_ENTRY_MIN=${CHNO_ENTRY_MIN:-21}
# The M2-05 picture-in-picture preflight: 34 seams (integration added the
# four the scenario's header reserved for a merged lane V1, and four more for
# PIP15's single dispatch spelling and the snapshot key's one name), the
# stub's executable probe, and its own "ran every check" line.
PIP_PREFLIGHT_MIN=${PIP_PREFLIGHT_MIN:-39}

step() { printf '\n== %s\n' "$*"; }
ok()   { printf 'ok   %s\n' "$*"; }
bad()  { printf 'FAIL %s\n' "$*"; fail=1; }

step "omarchy plugin validate $ROOT"
if omarchy plugin validate "$ROOT"; then ok "manifest valid"; else bad "manifest invalid"; fi

step "qmllint (imports: $QMLROOT, $QML_IMPORTS)"
mkdir -p "$QMLROOT/qs" || bad "could not create the qmllint import root $QMLROOT"
ln -sfn "$SHELL_DIR/Commons" "$QMLROOT/qs/Commons" || bad "could not link qs.Commons into $QMLROOT"
ln -sfn "$SHELL_DIR/Ui" "$QMLROOT/qs/Ui" || bad "could not link qs.Ui into $QMLROOT"
[[ -d $QMLROOT/qs/Commons && -d $QMLROOT/qs/Ui ]] || bad "qs.Commons / qs.Ui do not resolve under $QMLROOT"
if [[ ! -x "$QT_BIN/qmllint" ]]; then
  bad "qmllint not found at $QT_BIN/qmllint (pacman -S qt6-declarative)"
else
  linted=0
  # E2: the list was "$ROOT"/*.qml and "$ROOT"/tests/*.qml, so
  # scripts/dev-harness/shell.qml - the fake EVERY scenario in this repo runs
  # against, and the thing CLAUDE.md rule 10 says must never be more forgiving
  # than the real host - was never linted. A QML error there leaves this gate
  # green while every harness scenario fails to start.
  #
  # The harness fake imports "Model.js", which run.sh stages beside it in the
  # scratch root. Lint it the way it actually runs, or the import warning is
  # noise and the Model.* calls are never resolved at all.
  stage="$CHECK_TMP/dev-harness"
  mkdir -p "$stage"
  for f in "$ROOT"/scripts/dev-harness/*.qml; do
    [[ -f $f ]] || continue
    cp "$f" "$stage/" || bad "could not stage $(basename "$f") for linting"
  done
  ln -sfn "$ROOT/Model.js" "$stage/Model.js"
  for file in "$ROOT"/*.qml "$ROOT"/tests/*.qml "$stage"/*.qml; do
    [[ -f $file ]] || continue
    linted=$(( linted + 1 ))
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
  # `[[ -f $file ]] || continue` means an unmatched glob lints NOTHING while
  # the gate reports green. Count what was actually linted.
  if (( linted < QMLLINT_FILES_MIN )); then
    bad "qmllint examined $linted file(s), expected at least $QMLLINT_FILES_MIN"
  else
    ok "qmllint examined $linted file(s)"
  fi
fi

step "node tests/Model.test.js"
if command -v node >/dev/null 2>&1; then
  node_log="$CHECK_TMP/node.log"
  if node "$ROOT/tests/Model.test.js" >"$node_log" 2>&1; then
    cat "$node_log"
    # The runner prints "<n> checks, <m> failure(s)". An emptied or renamed
    # test file exits 0 having asserted nothing; assert the count.
    node_checks=$(grep -oE '^[0-9]+ checks' "$node_log" | head -1 | grep -oE '^[0-9]+')
    if [[ -z $node_checks ]]; then
      bad "node tests printed no check count at all"
    elif (( node_checks < NODE_CHECKS_MIN )); then
      bad "node tests ran $node_checks checks, expected at least $NODE_CHECKS_MIN"
    else
      ok "node tests ($node_checks checks)"
    fi
  else
    cat "$node_log"; bad "node tests"
  fi
else
  bad "node not found (dev-only dependency: mise use node)"
fi

step "python3 -m unittest discover -s tests"
py_log="$CHECK_TMP/python.log"
if (cd "$ROOT" && python3 -m unittest discover -s tests) >"$py_log" 2>&1; then
  cat "$py_log"
  # `Ran 0 tests ... OK` exits 0. A tests/ directory that stops being
  # discoverable is invisible without this.
  py_tests=$(grep -oE '^Ran [0-9]+ test' "$py_log" | head -1 | grep -oE '[0-9]+')
  if [[ -z $py_tests ]]; then
    bad "python tests printed no test count at all"
  elif (( py_tests < PY_TESTS_MIN )); then
    bad "python ran $py_tests tests, expected at least $PY_TESTS_MIN"
  else
    ok "python tests ($py_tests tests)"
  fi
else
  cat "$py_log"; bad "python tests"
fi

step "qmltestrunner tests/Model.spec.qml"
if [[ -x "$QT_BIN/qmltestrunner" ]]; then
  qml_log="$CHECK_TMP/qmltest.log"
  if QT_QPA_PLATFORM=offscreen "$QT_BIN/qmltestrunner" -input "$ROOT/tests/Model.spec.qml" >"$qml_log" 2>&1; then
    # E1: this used to be `ok "qml spec ($(grep -c '^PASS' ...) passed)"` - the
    # count interpolated into a message, the grep's status discarded inside
    # the argument. A runner that exits 0 having executed ZERO test functions
    # printed `ok   qml spec (0 passed)` and the gate stayed green, while
    # CLAUDE.md and docs/QA-PLAYER.md cite the number as evidence.
    qml_passed=$(grep -c '^PASS' "$qml_log")
    if (( qml_passed < QML_SPEC_MIN )); then
      bad "qml spec ran $qml_passed test function(s), expected at least $QML_SPEC_MIN"
      cat "$qml_log"
    else
      ok "qml spec ($qml_passed passed)"
    fi
  else
    bad "qml spec"; cat "$qml_log"
  fi
else
  bad "qmltestrunner not found at $QT_BIN/qmltestrunner"
fi

step "scripts/qa-lib-test.sh (the harness predicates)"
# The tooling this project tests itself with is tested here. Every predicate
# is driven against the condition that used to make its check pass silently.
if bash "$ROOT/scripts/qa-lib-test.sh" >"$CHECK_TMP/qalib.log" 2>&1; then
  ok "harness predicates ($(grep -c '^PASS' "$CHECK_TMP/qalib.log") checks)"
  if [[ ${CHECK_VERBOSE:-0} == 1 ]]; then cat "$CHECK_TMP/qalib.log"; fi
else
  bad "harness predicates"; cat "$CHECK_TMP/qalib.log"
fi

step "scripts/dev-harness/chno-entry-scenario.sh check-tree (M2-03 CN23)"
# The number-entry scenarios had no runner for a whole milestone, and nothing
# in this gate would have said so. The preflight half needs no display and no
# quickshell, so it runs here on every commit: if the four harness verbs or
# the seams they drive disappear, the gate goes red on this machine rather
# than on the display lane's, weeks later. It proves the code is present,
# never that it works - only the live half does that.
chno_log="$CHECK_TMP/chno-entry.log"
if bash "$ROOT/scripts/dev-harness/chno-entry-scenario.sh" check-tree >"$chno_log" 2>&1; then
  chno_checks=$(grep -c '^PASS' "$chno_log")
  if (( chno_checks < CHNO_ENTRY_MIN )); then
    bad "chno-entry preflight ran $chno_checks checks, expected at least $CHNO_ENTRY_MIN"
    cat "$chno_log"
  else
    ok "chno-entry preflight ($chno_checks checks)"
    if [[ ${CHECK_VERBOSE:-0} == 1 ]]; then cat "$chno_log"; fi
  fi
else
  bad "chno-entry preflight"; cat "$chno_log"
fi

step "scripts/dev-harness/pip-scenario.sh check-tree (M2-05)"
# The same preflight discipline for picture in picture, and for a sharper
# reason: PiP is the first feature here whose correctness depends on how a
# program OUTSIDE the plugin answers, so the seams that must exist are
# scattered across Service.qml, the harness fake and the stub compositor.
# This half needs no display, no quickshell and no hyprctl -- it proves the
# code is present, never that it works. Only the live half does that.
pip_log="$CHECK_TMP/pip-scenario.log"
if bash "$ROOT/scripts/dev-harness/pip-scenario.sh" check-tree >"$pip_log" 2>&1; then
  pip_checks=$(grep -c '^PASS' "$pip_log")
  if (( pip_checks < PIP_PREFLIGHT_MIN )); then
    bad "pip preflight ran $pip_checks checks, expected at least $PIP_PREFLIGHT_MIN"
    cat "$pip_log"
  else
    ok "pip preflight ($pip_checks checks)"
    if [[ ${CHECK_VERBOSE:-0} == 1 ]]; then cat "$pip_log"; fi
  fi
else
  bad "pip preflight"; cat "$pip_log"
fi

step "ascii check (code files)"
# E3: the list was hand-maintained, and `[[ -f $file ]] || continue` dropped
# directories - so scripts/gen-playlist.py (a .py source, which CLAUDE.md rule
# 8 covers), every scripts/*.sh, everything under scripts/dev-harness/ and
# every fixture SUBdirectory went unscanned. The gate was green partly by
# accident: tests/fixtures/qa-nonascii/ was skipped because it is a directory,
# not because anyone excluded it.
#
# Driven from git ls-files now, with the deliberate non-ASCII trees excluded
# BY NAME so the exclusion is visible rather than incidental.
ascii_bad=0
ascii_scanned=0
while IFS= read -r -d '' rel; do
  # Product owner ruling, 2026-09-14. The gate exists so that SOURCE stays
  # ASCII: escapes stay escapes and no tool silently rewrites a byte. A data
  # fixture that carries non-ASCII is the opposite case - carrying it IS what
  # it tests, because channel names are Cyrillic, Japanese and accented Latin
  # in the real world. So fixtures are exempt, but only BY NAME, one line per
  # file with the reason. A directory-wide glob would let the next file in
  # slip past unnoticed, which is how this gate was quietly green before.
  case $rel in
    */nonascii/*|tests/fixtures/qa-nonascii/*) continue ;;       # a whole tree, named for the purpose
    tests/fixtures/qa-player/qa-player.m3u) continue ;;          # channel names in German, Japanese and a check mark
    scripts/dev-harness/fixtures/harness.m3u.in) continue ;;     # channel names in French and Russian
  esac
  file="$ROOT/$rel"
  [[ -f $file ]] || continue
  ascii_scanned=$(( ascii_scanned + 1 ))
  if LC_ALL=C grep -n -P '[^\x00-\x7F]' "$file" >/dev/null; then
    printf 'non-ASCII bytes in %s:\n' "$rel"; LC_ALL=C grep -n -P '[^\x00-\x7F]' "$file" | head -5
    ascii_bad=1
  fi
done < <(git -C "$ROOT" ls-files -z -- \
           '*.js' '*.py' '*.json' 'bin/*' 'scripts/*.sh' 'scripts/dev-harness/*' \
           'tests/fixtures/*' 'docs/ARCHITECTURE.md')
if (( ascii_scanned == 0 )); then
  bad "ascii check scanned no files at all (is this a git checkout?)"
elif (( ascii_bad )); then
  bad "ascii check ($ascii_scanned files scanned)"
else
  ok "ascii check ($ascii_scanned files scanned)"
fi

step "control-byte check (source files, .qml included)"
# M2-03 integration. A raw NUL in tests/Model.test.js and tests/Model.spec.qml
# made grep treat both as BINARY and skip them silently: `grep -c chno
# tests/Model.test.js` answered 0 for a file with 34 of them. The whole
# integration criterion for this milestone is "a grep for the stand-in markers
# returns nothing", and that proof was unsound while a tracked source file was
# invisible to grep. Escapes carry the same bytes into the string and stay
# greppable.
#
# This is NOT the ASCII check and does not overlap it: it covers .qml too
# (where rule 8 deliberately allows non-ASCII glyphs) and it looks only for C0
# controls other than tab/newline/CR, plus DEL.
ctrl_bad=0
ctrl_scanned=0
while IFS= read -r -d '' rel; do
  case $rel in
    *.gz|*.png|*.jpg) continue ;;                               # binary by definition
  esac
  file="$ROOT/$rel"
  [[ -f $file ]] || continue
  ctrl_scanned=$(( ctrl_scanned + 1 ))
  # -a is load-bearing: without it grep SKIPS the file the moment it holds a
  # NUL, which is exactly the file this check exists to find.
  if LC_ALL=C grep -a -q -P '[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]' "$file" 2>/dev/null; then
    printf 'raw control bytes in %s (write them as \\uXXXX escapes)\n' "$rel"
    ctrl_bad=1
  fi
done < <(git -C "$ROOT" ls-files -z -- '*.js' '*.py' '*.qml' '*.json' '*.sh' 'bin/*' 'scripts/dev-harness/*')
if (( ctrl_scanned == 0 )); then
  bad "control-byte check scanned no files at all"
elif (( ctrl_bad )); then
  bad "control-byte check ($ctrl_scanned files scanned)"
else
  ok "control-byte check ($ctrl_scanned files scanned)"
fi

printf '\n'
if (( fail )); then echo "check.sh: FAILED"; exit 1; fi
echo "check.sh: all green"
