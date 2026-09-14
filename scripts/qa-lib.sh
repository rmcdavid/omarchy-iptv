#!/bin/bash
# scripts/qa-lib.sh -- the predicates this project's test tooling asserts on.
#
# WHY THIS FILE EXISTS. The M2-02 verification pass found a harness assertion
# that had never executed: a counting helper returned two lines on a no-match,
# the arithmetic consuming it died as an expansion error, and bash ran neither
# the pass nor the fail. Seventeen more places in scripts/ had the same shape -
# a check that cannot fail, a sweep that is clean because the file it sweeps is
# empty, a comparison whose two sides are both empty because the tool that
# produced them is gone. CLAUDE.md rule 11: a check that has never been seen
# failing is decoration.
#
# Every function here is a predicate with THREE outcomes, not two:
#     0  the thing held, and we saw the evidence that lets us say so
#     1  the thing did not hold
#     2  VACUOUS - there was no evidence either way (empty capture, missing
#        file, dead IPC). A vacuous answer is never a pass.
#
# CLAUDE.md rule 12: the logic lives here, where scripts/qa-lib-test.sh calls
# it for real, rather than being reimplemented inside a scenario a test cannot
# reach. Source it as:  . "<repo>/scripts/qa-lib.sh"
#
# Sourcing this file defines functions and touches nothing else.

# ---------------------------------------------------------------- counting

# qa_count <ere> <file>
# ALWAYS prints exactly one line holding one non-negative integer, and always
# succeeds - a missing, empty or unreadable file counts 0. This is D-PLY-9:
# `grep -acE ... || echo 0` prints "0\n0" on a no-match, because grep -c prints
# its own 0 AND exits 1, so both sides of the || run. The two-line value then
# kills any $(( )) that consumes it, and a failed arithmetic EXPANSION stops
# bash from running the command at all - no pass, no fail, exit 0.
# `| wc -l` is the idiom player-scenario.sh already uses for player_count, and
# GNU grep terminates its last output line even on unterminated input, so it
# cannot undercount.
qa_count() {
  grep -aE -- "$1" "$2" 2>/dev/null | wc -l | tr -d ' '
}

# qa_count_multi <ere> <file>...  total matches across several files.
qa_count_multi() {
  local ere=$1 f total=0
  shift
  for f in "$@"; do total=$(( total + $(qa_count "$ere" "$f") )); done
  printf '%s\n' "$total"
}

# ------------------------------------------------------------- sentinels

# The tooling must never answer a question with the same value a healthy run
# would produce. `field` printing "" on a dead IPC is indistinguishable from
# "the service says this is unset", and three P14 assertions demanded exactly
# "". These sentinels are non-empty and are not a legal service value.
QA_NO_STATE=NOSTATE      # the IPC did not answer, or answered unparseable JSON
QA_NO_FIELD=NOFIELD      # it answered, and the field is absent or null
QA_NO_FILE=NOFILE        # the file is missing or unparseable
QA_NO_SESSION=NOSESSION  # the file parsed, and it holds no session record
QA_NO_DELTA=NODELTA      # one side of a before/after pair was not a number

# qa_value <answer>: true only for a real answer - not empty, not a sentinel.
# Use this wherever a check used to say [[ -n "$x" ]].
qa_value() {
  case ${1-} in
    "" | "$QA_NO_STATE" | "$QA_NO_FIELD" | "$QA_NO_FILE" | "$QA_NO_SESSION" | "$QA_NO_DELTA") return 1 ;;
  esac
  return 0
}

# qa_delta <before> <after>: the difference between two counter readings.
#   0  both sides were integers; the difference is on stdout
#   2  VACUOUS - a side was empty, a sentinel or anything else non-numeric;
#      QA_NO_DELTA is on stdout, which no expected value will ever match
# ALWAYS prints exactly one line and ALWAYS succeeds as a substitution, which
# is the whole point: `$(( $(counter) - before ))` dies as an arithmetic
# EXPANSION the moment the counter answers NOFIELD or "", and a failed
# expansion stops bash from running the `is` whose word it was - no pass, no
# fail, exit 0. That is D-PLY-9 exactly, and a counter read over IPC has far
# more ways to answer non-numerically than a grep does.
qa_delta() {
  local before=${1-} after=${2-}
  if [[ $before =~ ^-?[0-9]+$ && $after =~ ^-?[0-9]+$ ]]; then
    printf '%s\n' "$(( after - before ))"
    return 0
  fi
  printf '%s\n' "$QA_NO_DELTA"
  return 2
}

# qa_field <python-expr over d> <json>: the service half of the harness state.
# Prints NOSTATE when the JSON is not there, NOFIELD when the expression does
# not resolve, booleans as JSON, everything else as python prints it.
qa_field() {
  python3 -c '
import json, sys
raw = sys.argv[2]
try:
    d = json.loads(raw)["service"]
except Exception:
    print("NOSTATE"); raise SystemExit(0)
try:
    v = eval(sys.argv[1])
except Exception:
    v = None
print(json.dumps(v) if isinstance(v, bool) else ("NOFIELD" if v is None else v))' "$1" "$2" 2>/dev/null \
    || printf '%s\n' "$QA_NO_STATE"
}

# qa_session_id <state.json>: the session record a later shell would read.
qa_session_id() {
  python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("NOFILE"); raise SystemExit(0)
s = d.get("session")
if not isinstance(s, dict) or not s.get("id"):
    print("NOSESSION"); raise SystemExit(0)
print(s["id"])' "$1" 2>/dev/null || printf '%s\n' "$QA_NO_FILE"
}

# ------------------------------------------------------------ /proc reads

# qa_cmdline <pid>: the process command line, space separated.
# An EMPTY pid used to collapse /proc/$1/cmdline to /proc//cmdline, which the
# kernel resolves to /proc/cmdline - so six "no secret on mpv's argv" checks
# were comparing the secrets against the KERNEL command line and passing.
qa_cmdline() {
  local pid=${1-}
  [[ $pid =~ ^[0-9]+$ ]] || return 1
  [[ -r /proc/$pid/cmdline ]] || return 1
  local cmd
  cmd=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null) || return 1
  [[ -n $cmd ]] || return 1
  printf '%s\n' "$cmd"
}

# ------------------------------------------------------- privacy sweeps

# qa_leak_scan <control-ere> <leak-ere> <file>...
#   0 clean, and the control proves the capture holds what we were sweeping
#   1 a leak (printed) - anywhere in the capture, not only on our own lines
#   2 vacuous: a file is missing, unreadable or EMPTY, or the control matched
#     nothing anywhere, so the capture is not evidence of anything
# A1: `grep -nE '<leak>' journal.txt qs-log.txt && echo FAILURE || echo ok`
# printed "redaction ok" for an empty file, for a journalctl that failed and
# wrote only an error, and for a capture window that caught nothing.
qa_leak_scan() {
  local control=$1 leak=$2
  shift 2
  local f hits
  for f in "$@"; do
    [[ -f $f && -r $f && -s $f ]] || return 2
  done
  [[ $(qa_count_multi "$control" "$@") -gt 0 ]] || return 2
  hits=$(grep -naE -- "$leak" "$@" 2>/dev/null)
  [[ -z $hits ]] || { printf '%s\n' "$hits"; return 1; }
  return 0
}

# qa_leak_on_labelled <label-ere> <leak-ere> <file>
# The A4 shape: sweep only the lines that carry one of the labels, and refuse
# to call it clean when there are no such lines. `! grep -E <labels> log |
# grep -qE '://'` passed on an empty log AND on a log leaking a URL on a line
# that carried no label.
qa_leak_on_labelled() {
  local label=$1 leak=$2 file=$3 hits
  [[ -f $file && -r $file ]] || return 2
  [[ $(qa_count "$label" "$file") -gt 0 ]] || return 2
  hits=$(grep -aE -- "$label" "$file" 2>/dev/null | grep -naE -- "$leak")
  [[ -z $hits ]] || { printf '%s\n' "$hits"; return 1; }
  return 0
}

# qa_answer_lacks <needle-ere> <answer>
#   0 the answer is non-empty and does not carry the needle
#   1 it carries it
#   2 the answer is empty - the IPC is dead, which is not evidence of anything
qa_answer_lacks() {
  local needle=$1 answer=$2
  [[ -n $answer ]] || return 2
  grep -qE -- "$needle" <<<"$answer" && return 1
  return 0
}

# --------------------------------------------------------- file evidence

# qa_json_normalized <file>: sorted JSON on stdout, or status 1 and nothing.
# A3: diff <(jq -S . before) <(jq -S . after) exits 0 when BOTH jq calls fail,
# so "shell.json restored" printed on a missing snapshot or a malformed file.
qa_json_normalized() {
  local file=$1 out
  [[ -s $file ]] || return 1
  out=$(jq -S . "$file" 2>/dev/null) || return 1
  [[ -n $out ]] || return 1
  printf '%s\n' "$out"
}

# qa_tree_count <dir> [find args...]: how many paths a find under <dir>
# examined. Status 1 when the directory is not there - A2's `find $PLUGIN_DIR
# -newer ...` printed nothing for a directory that did not exist, and "no
# writes inside the plugin directory" read as proven.
qa_tree_count() {
  local dir=$1
  shift
  [[ -d $dir ]] || return 1
  find "$dir" "$@" 2>/dev/null | wc -l | tr -d ' '
}

# qa_same_file <src> <dst>: byte-identical, both present. C1 discarded the
# status of the cp that stages the tree under test, so a failed copy left the
# PREVIOUS run's Model.js in place while the rest of the tree moved on.
qa_same_file() {
  local src=$1 dst=$2
  [[ -f $src && -f $dst ]] || return 1
  cmp -s "$src" "$dst"
}

# qa_wait_nonempty <file> <secs>: poll for a file with content in it.
# C6 read a background server's port file after a flat `sleep 0.3` and built
# http://127.0.0.1:/slow.m3u out of the empty answer.
qa_wait_nonempty() {
  local file=$1 secs=$2 i
  for ((i = 0; i < secs * 10; i++)); do
    [[ -s $file ]] && return 0
    sleep 0.1
  done
  return 1
}

# --------------------------------------------------- capability probes

# qa_case_arm <file> <token>: does <file> PARSE this option, rather than merely
# mention it? D1 used a bare `grep -q -- --detach run.sh`, which the file's own
# header comment satisfies, so deleting the case arm left the gate green.
qa_case_arm() {
  local file=$1 token=$2
  # Only option/verb spellings, so the token is its own ERE (- is literal).
  [[ $token =~ ^[A-Za-z0-9_-]+$ ]] || return 2
  grep -qE "^[[:space:]]*${token}\)" "$file"
}

# qa_defines_function <file> <name>: `function <name>(` - an anchor a comment
# mentioning the name does not satisfy.
qa_defines_function() {
  grep -qE "function[[:space:]]+$2[[:space:]]*\(" "$1"
}

# ------------------------------------------------------------- shell env

# qa_safe_path <path>: true only for a path that cannot act as shell text.
# F4/C2: these scripts interpolate an environment-supplied scratch path into
# `bash -c` snippets and into a sourced env file. Until every snippet takes its
# data as argv, the defence is to refuse data that could be code: quotes,
# backquotes, $, \, ;, &, |, <, >, (), {}, *, ?, newline.
qa_safe_path() {
  local p=${1-}
  [[ -n $p ]] || return 1
  [[ $p == /* ]] || return 1
  [[ $p != *[\'\"\`\$\\\;\&\|\<\>\(\)\{\}\*\?]* ]] || return 1
  [[ $p != *$'\n'* ]] || return 1
  return 0
}

# qa_env_line <NAME> <value>: one `export NAME=<quoted>` line that a later
# `.` re-reads as the same bytes. C2 wrote export X="$value" by hand, so a
# path carrying $, a backquote, a backslash or a double quote was re-expanded
# - or executed - when restart-shell sourced it.
qa_env_line() {
  printf 'export %s=%q\n' "$1" "$2"
}
