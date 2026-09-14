#!/bin/bash
# scripts/check.sh -- the whole quality gate for omarchy-iptv, in one command.
#   1. omarchy plugin validate   (manifest schema, entry points, no symlinks)
#   2. qmllint on every .qml     (qs.Commons / qs.Ui mapped through $QMLROOT),
#                                INCLUDING the dev-harness fake (CLAUDE.md 10)
#   3. node tests                (tests/Model.test.js)
#   4. python tests              (python3 -m unittest discover -s tests)
#   5. QML spec                  (qmltestrunner on tests/Model.spec.qml)
#   6. harness predicates        (scripts/qa-lib-test.sh)
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
QML_SPEC_MIN=${QML_SPEC_MIN:-47}
NODE_CHECKS_MIN=${NODE_CHECKS_MIN:-954}
PY_TESTS_MIN=${PY_TESTS_MIN:-260}
QMLLINT_FILES_MIN=${QMLLINT_FILES_MIN:-5}

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
  case $rel in
    */nonascii/*|tests/fixtures/qa-nonascii/*) continue ;;   # deliberately non-ASCII, by name
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

printf '\n'
if (( fail )); then echo "check.sh: FAILED"; exit 1; fi
echo "check.sh: all green"
