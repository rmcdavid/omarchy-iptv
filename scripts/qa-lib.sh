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

# qa_json_field <python-expr over d> <json>: the whole answer, not its
# "service" half. This is what the M2-03 number verbs answer with
# (`numberState`, `number`, `commitNumber`, `cancelNumber`), and the sentinels
# matter more here than anywhere: a harness pointed at a tree WITHOUT those
# verbs answers `{"ok":false,"error":"no_verb","active":null,...}`, and a check
# written as [[ "$(field active)" == "false" ]] would then read "the entry is
# not active" and PASS against a tree that cannot answer at all. NOFIELD is
# not "false", so it fails instead.
qa_json_field() {
  python3 -c '
import json, sys
raw = sys.argv[2]
try:
    d = json.loads(raw)
except Exception:
    print("NOSTATE"); raise SystemExit(0)
try:
    v = eval(sys.argv[1])
except Exception:
    v = None
print(json.dumps(v) if isinstance(v, bool) else ("NOFIELD" if v is None else v))' "$1" "$2" 2>/dev/null \
    || printf '%s\n' "$QA_NO_STATE"
}

# qa_guide_field <python-expr over d> <json>: the GUIDE half of `state()`,
# the half every number-entry scenario reads. NOSTATE when there is no guide
# in the answer at all - an overlay that failed to load answers `null` there,
# and `null` must not be able to satisfy a check.
qa_guide_field() {
  python3 -c '
import json, sys
try:
    d = json.loads(sys.argv[2])["guide"]
except Exception:
    print("NOSTATE"); raise SystemExit(0)
if d is None:
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
# qa_openms <expected-view> <openMs-json>
# The guide's open-budget number, or a refusal. Prints "<ms-csv> <realised>"
# on 0; prints nothing and answers 1 or 2 otherwise.
#
# WHY THIS IS A PREDICATE AND NOT AN ARITHMETIC. `openMs` force-lays-out the
# channel view before it stops the clock, because the delegates are where the
# work is. Until 2026-09-25 it resolved the single literal objectName
# "resultList", and its ONLY caller -- a person reading the JSON -- had no way
# to know whether that resolution succeeded, because the return value was
# discarded and the payload never said. The comment above it asserted the
# opposite: that a changed id would be "visibly wrong rather than quietly
# optimistic". With a second channel view on the way, a run with that view on
# screen would have laid out nothing, created no delegates, and reported a
# fast, plausible number for an empty screen. That is the shape this whole
# file exists to stop: a measurement that cannot fail.
#
# So: a payload with no `view` field is VACUOUS (2), not a number -- that is
# the old instrument's exact payload and it must never be accepted again. A
# payload naming a DIFFERENT view than the caller expected is a failure (1),
# because the number is real but it is not the number that was asked for.
qa_openms() {
  python3 -c '
import json, sys
want, raw = sys.argv[1], sys.argv[2]
try:
    d = json.loads(raw)
except Exception:
    raise SystemExit(2)
if not isinstance(d, dict) or "ms" not in d:
    raise SystemExit(2)
# No `view` key at all is the pre-2026-09-25 instrument. It cannot say what it
# measured, so it did not measure anything we can use.
if "view" not in d:
    raise SystemExit(2)
view = str(d.get("view") or "")
if view == "":
    raise SystemExit(2)          # nothing was forced: no delegates, no number
if want and view != want:
    raise SystemExit(1)          # a real number, for the wrong screen
ms = d.get("ms")
if not isinstance(ms, list) or not ms:
    raise SystemExit(2)
print("%s %s" % (",".join(str(x) for x in ms), d.get("realised", -1)))
' "$1" "$2" 2>/dev/null
}

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

# ------------------------------------------------------------ transcripts

# F-M3-1, half (b). One live run of m3-scenario.sh answered "17 passed, 14
# failed" and WHICH FOURTEEN IS UNKNOWN to this day: the run was backgrounded
# and its output piped through `tail -n 3` by the person running it, so the
# scenario's own evidence -- 31 PASS/FAIL lines naming every decision it had
# just observed -- existed only in a pipe that was then thrown away. The
# scenario was not at fault and no assertion was missing. The EVIDENCE was
# discarded downstream of it.
#
# The fix is that a scenario does not rely on anyone keeping its stdout. It
# writes a transcript, and it PRINTS where. Lifted out of
# rewind-scenario.sh, where it was one scenario's local habit, so that every
# scenario gets it by calling one function and none can forget it.
#
# THREE things here are load-bearing and all three were measured on
# 2026-10-06 (bash 5.3, GNU coreutils tee):
#
#   1. The file is created HERE, by us, before tee opens it, and chmod'd
#      0600. `tee` left to create the file itself uses its own umask: with
#      the usual 0022 the transcript lands at **0644, world-readable**
#      (measured: `exec > >(tee -a f); echo hello` leaves f at 644; the same
#      with `: >f; chmod 0600 f` first leaves it at 600). A scenario's stdout
#      can carry a playlist URL with provider credentials in it --
#      argv-scenario.sh deliberately drives one -- so rule 5 and rule 6 make
#      0600 in a 0700 directory the only acceptable landing place, and this
#      REFUSES rather than writing a transcript into a directory other users
#      can enter.
#
#   2. `-p`, and it is the flag on this line that actually matters. Without
#      it, `tee` exits when its OWN stdout breaks, and the transcript stops
#      at that line -- so `scenario | head -3` truncates the FILE as well as
#      the terminal, which is the exact failure this function exists to
#      prevent. Measured on this machine (GNU coreutils 9.11), a 20-line
#      producer at 0.05 s intervals under `| head -3`: plain `tee -a` left 3
#      of 22 lines in 3 of 3 runs and the scenario aborted at line 3; with
#      `-p` it left 22 of 22 lines with the summary intact, 3 of 3 runs. The
#      first version of this comment audited `-a` in forensic detail and
#      never looked at `-p`, while two sentences in the harness README --
#      "the evidence is on disk whatever happens to the terminal", and a list
#      of `| head` as a bad REPORT -- were false because of it. Found by the
#      first review of this function.
#
#      `-a` itself stays MARKED UNVERIFIED (rule 14): nothing here can go red
#      for it. The reasons usually given are both false, measured -- a
#      truncating `tee` loses nothing from the pipe (3/3 runs, five lines
#      each, all five present), and O_TRUNC does not change a mode, so the
#      0600 above survives either spelling. With the file pre-created and
#      refused if it already exists, `-a` and a plain `tee` are
#      indistinguishable from outside. It is kept because it is the form
#      rewind-scenario.sh shipped and because it makes the deliberate
#      truncation above the only one in the arrangement -- not because any
#      check defends it.
#
#   3. Where the call sits. It must come AFTER argument parsing -- the
#      transcript's name and the directory it lands in are derived from the
#      environment, and a usage error should die as a usage error rather than
#      as a one-line transcript -- and BEFORE the first line of evidence,
#      because everything printed before the `exec` reaches the terminal
#      only. In a scenario with a `check-tree` mode it sits on the LIVE path
#      alone: scripts/check.sh runs the check-tree halves, and a gate step
#      may neither print a path nobody asked for nor leave a file behind.

# The transcript this shell is writing, or "" before qa_transcript_start.
# R18 in rewind-scenario.sh sweeps it for leaked URLs at the end of the run,
# so the NAME of this variable is a join between two files: keep it.
QA_TRANSCRIPT=""

# qa_transcript_dir: where transcripts go by default. The same expression
# every scenario and run.sh use for the harness scratch, plus one directory,
# so a scenario that passes no directory still lands in the right place.
# `run.sh clean` removes cache/, state/, runtime/ and shots/ and not this.
qa_transcript_dir() {
  local runtime=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
  printf '%s\n' "${OMARCHY_IPTV_HARNESS_DIR:-$runtime/omarchy-iptv-harness}/transcripts"
}

# qa_transcript_start <name> [dir]
#   Sends this shell's stdout AND stderr through `tee` into a private
#   transcript, prints the path, and sets QA_TRANSCRIPT to it.
#     0  redirected; QA_TRANSCRIPT names a 0600 file in a 0700 directory
#     2  redirected NOTHING, and said why on stderr
#   Status 2 is never "carry on quietly": a scenario whose evidence cannot
#   be written is the F-M3-1 run again, so every call site is
#   `qa_transcript_start <name> || exit 2`.
#
#   <name> becomes a FILENAME, never a path: it is refused if it could be
#   one. The file is "<name>-<stamp>-<pid>.out" in ONE flat directory, with
#   no per-scenario subdirectory, and that is deliberate -- rewind's R18
#   sweeps the transcript for the ERE `/rewind/` among others, so a
#   transcripts/rewind/ path would make the file's own name a leak hit and
#   turn a privacy check red on itself. scripts/qa-lib-test.sh asserts that
#   the path this produces does not match R18's sweep.
qa_transcript_start() {
  local name=${1-} dir=${2-}
  if [[ ! $name =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    printf 'qa_transcript_start: %s is not a transcript name\n' "${name:-<empty>}" >&2
    return 2
  fi
  [[ -n $dir ]] || dir=$(qa_transcript_dir)
  if ! qa_safe_path "$dir"; then
    printf 'qa_transcript_start: %s is not a safe absolute path\n' "$dir" >&2
    return 2
  fi
  if ! mkdir -p "$dir" 2>/dev/null; then
    printf 'qa_transcript_start: cannot create %s\n' "$dir" >&2
    return 2
  fi
  chmod 0700 "$dir" 2>/dev/null
  # Rule 6, as a refusal rather than a hope, and the two cases differ. A
  # directory we own is TIGHTENED by the chmod above (a pre-existing 0755
  # becomes 0700 and the run goes on). A directory we do not own cannot be,
  # and that is what this refuses: /tmp handed in as the directory is 1777
  # root-owned on every machine this runs on, the chmod fails silently, and
  # without this check the transcript would land where anyone can read it.
  # Measured both ways in scripts/qa-lib-test.sh, which drives /tmp for real.
  local dmode
  dmode=$(stat -c '%a' "$dir" 2>/dev/null)
  if [[ ! $dmode =~ ^[0-7]+$ ]] || (( 0$dmode & 077 )); then
    printf 'qa_transcript_start: %s is mode %s; a transcript needs 0700\n' "$dir" "${dmode:-unknown}" >&2
    return 2
  fi
  # QA_TRANSCRIPT_STAMP exists so the refusal below is TESTABLE. The stamp is
  # second-resolution, so two starts colliding is a timing event, and a check
  # that waits for a timing event is a check that passes 499 runs in 500 and
  # reddens on the 500th for no reason -- scripts/qa-lib-test.sh pins the stamp
  # and drives the collision instead. Nothing else sets it.
  local stamp=${QA_TRANSCRIPT_STAMP:-$(date +%Y%m%d-%H%M%S)}
  local path="$dir/$name-$stamp-$$.out"
  # Never write into a transcript we did not create. The stamp is
  # second-resolution and $$ is one shell, so two starts in the same second
  # from the same shell resolve to the SAME path -- and then one run's
  # evidence is appended into the other's, under a filename that claims to
  # name a single run. Refusing is the only honest answer: there is no second
  # name for a run that already has one.
  if [[ -e $path ]]; then
    printf 'qa_transcript_start: %s already exists; refusing to share a transcript\n' "$path" >&2
    return 2
  fi
  # Created in a subshell under umask 077 so the file is 0600 from its first
  # byte, with no window at 0644, and then chmod'd. The two are DELIBERATELY
  # REDUNDANT, and the mutation table says so: removing either one alone
  # reddens nothing, because the other still gives 0600; removing BOTH turns
  # scripts/qa-lib-test.sh red with the measured 644. The redundancy is kept
  # rather than trimmed because the property is a privacy one and the cost is
  # one line. What it is NOT is a fix for a pre-existing looser mode -- the
  # refusal above makes that path unreachable, and an earlier version of this
  # comment claimed otherwise.
  if ! ( umask 077; : >"$path" ) 2>/dev/null; then
    printf 'qa_transcript_start: cannot write %s\n' "$path" >&2
    return 2
  fi
  chmod 0600 "$path" 2>/dev/null
  QA_TRANSCRIPT=$path
  exec > >(tee -pa "$path") 2>&1
  # Printed AFTER the redirect, so the transcript's first line names itself
  # and the operator sees the same line on the terminal.
  printf '== transcript %s\n' "$path"
  return 0
}

# qa_transcript_sync [secs]
#   A bounded barrier: everything printed so far is ON DISK when this
#   returns 0. Needed because the transcript is written by a tee on the far
#   side of a pipe, and the shell does not wait for it.
#     0  the transcript has caught up
#     1  it had not after <secs>, and said so (never silently)
#     2  vacuous: no transcript was started, so there is nothing to sync
#
#   MEASURED, 2026-10-06, 30 runs per case: a line printed and then read
#   back by a bash BUILTIN was absent 30 of 30 times -- the pipe had not been
#   drained at all. Read back through a `grep` (the fork is itself the delay)
#   it was present 12 of 12 on an idle machine and absent **6 of 30 with the
#   cores oversubscribed twice over**. rewind-scenario.sh's R18 sweeps its
#   own transcript for leaked URLs at the end of the run, which is that exact
#   shape: under load it was sweeping a file that was short of its most
#   recent lines, so a URL printed just before the sweep could go unseen by
#   the check that exists to see it. A privacy sweep that reads a short file
#   is rule 14's shape -- a check that cannot go red for the thing it guards.
qa_transcript_sync() {
  local secs=${1:-5} marker i
  [[ -n ${QA_TRANSCRIPT-} ]] || return 2
  [[ -f $QA_TRANSCRIPT ]] || return 2
  # Non-empty, unique, and carrying nothing a leak sweep could match.
  marker="transcript-sync-$$-$RANDOM$RANDOM"
  printf '== %s\n' "$marker"
  for ((i = 0; i < secs * 20; i++)); do
    grep -qaF -- "$marker" "$QA_TRANSCRIPT" 2>/dev/null && return 0
    sleep 0.05
  done
  # Rule 3: a wait that gives up says so rather than looping on.
  printf 'qa_transcript_sync: gave up after %s s; %s may be short of its last lines\n' \
    "$secs" "$QA_TRANSCRIPT" >&2
  return 1
}
