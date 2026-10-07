#!/bin/bash
# scripts/qa-lib-test.sh -- the rule-11 evidence for scripts/qa-lib.sh.
#
# Every predicate in the library replaces a check that could not fail. This
# file proves each one BOTH ways, in the order CLAUDE.md rule 11 asks for:
#
#   1. construct the condition that made the old check silently pass or
#      silently die, and show the new predicate refuses it;
#   2. remove that condition and show the new predicate passes.
#
# Where the old form is one line, it is reproduced here verbatim (`old_*`) and
# asserted to misbehave, so the evidence does not depend on anyone's memory of
# what the bug was.
#
# Bash plus python3/jq, and `node` for the one section that drives shell.qml's
# own focusWalk by extracting it (the gate already depends on node for
# tests/Model.test.js). No harness, no display, no network. A few seconds
# rather than one: three sections now RUN something -- run.sh against a stubbed
# transport, and two scenarios' refusal paths, which start nothing. Run by
# scripts/check.sh.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
# shellcheck source=scripts/qa-lib.sh
. "$HERE/qa-lib.sh"

TMP=$(mktemp -d "${TMPDIR:-/tmp}/qa-lib-test-XXXXXX")
trap 'rm -rf "$TMP"' EXIT

pass=0
fail=0
ok()  { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad() { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
is()  { if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1 (got '$2', want '$3')"; fi; }
ck()  { if eval "$2"; then ok "$1"; else bad "$1"; fi; }
# st <label> <want-status> <cmd...>
st()  {
  local label=$1 want=$2 got
  shift 2
  "$@" >/dev/null 2>&1
  got=$?
  is "$label" "$got" "$want"
}

section() { printf '\n-- %s\n' "$*"; }

# ============================================================ qa_count (B4)

section "qa_count / D-PLY-9: the counting helper that returned two lines"

LOG="$TMP/harness.log"
: >"$LOG"

# The shipped form, verbatim from player-scenario.sh:149.
old_log_count() { grep -acE "$1" "$LOG" 2>/dev/null || echo 0; }

is "the shipped helper answered a no-match with TWO lines" \
   "$(old_log_count 'no-such-pattern' | wc -l)" "2"
is "and the value it produced was 0 newline 0" \
   "$(printf '%q' "$(old_log_count 'no-such-pattern')")" "$(printf '%q' "$(printf '0\n0')")"
# The kill: a failed arithmetic EXPANSION means bash never runs the command at
# all - so neither `pass` nor `fail` moved, and the run carried on and exited
# 0. The probe below has to be a subshell precisely BECAUSE `|| ran=no` would
# not run either: there is no in-band way to notice this from bash.
before=$(old_log_count 'no-such-pattern')
ran=$( { printf 'yes:%s\n' "$(( 1 - before ))"; } 2>/dev/null )
is "so the command consuming it never executed (this is what skipped the check)" \
   "${ran:-no}" "no"
ran=$( { printf 'yes:%s\n' "$(( 1 - $(qa_count 'no-such-pattern' "$LOG") ))"; } 2>/dev/null )
is "with qa_count the same command DOES execute" "${ran:-no}" "yes:1"

is "qa_count answers a no-match with exactly one line" \
   "$(qa_count 'no-such-pattern' "$LOG" | wc -l)" "1"
is "qa_count answers a no-match with 0" "$(qa_count 'no-such-pattern' "$LOG")" "0"
is "qa_count on a missing file is 0, one line" \
   "$(qa_count 'anything' "$TMP/not-here.log" | wc -l)" "1"
is "qa_count on a missing file is 0" "$(qa_count 'anything' "$TMP/not-here.log")" "0"

printf 'omarchy-iptv: mpv unresponsive, restarting player\n' >>"$LOG"
is "qa_count counts a match" "$(qa_count 'mpv unresponsive, restarting player' "$LOG")" "1"
printf 'noise\nomarchy-iptv: mpv unresponsive, restarting player\n' >>"$LOG"
is "qa_count counts both matches" "$(qa_count 'mpv unresponsive, restarting player' "$LOG")" "2"
printf 'omarchy-iptv: mpv unresponsive, restarting player' >>"$LOG"   # no trailing newline
is "qa_count does not undercount an unterminated last line" \
   "$(qa_count 'mpv unresponsive, restarting player' "$LOG")" "3"

# And now the assertion D-PLY-9 killed, driven end to end: it must MOVE a
# counter in both directions.
: >"$LOG"
b=$(qa_count 'mpv unresponsive, restarting player' "$LOG")
printf 'omarchy-iptv: mpv unresponsive, restarting player\n' >>"$LOG"
is "the P11 relaunch delta is computable and correct (one relaunch)" \
   "$(( $(qa_count 'mpv unresponsive, restarting player' "$LOG") - b ))" "1"
printf 'omarchy-iptv: mpv unresponsive, restarting player\n' >>"$LOG"
is "and a SECOND relaunch makes that same expression say 2, not die" \
   "$(( $(qa_count 'mpv unresponsive, restarting player' "$LOG") - b ))" "2"

# ====================================================== sentinels (F1)

section "sentinels / F1: tooling failure must not look like a service answer"

STATE_OK="$TMP/state-ok.json"
printf '{"session":{"id":"t:live1"}}\n' >"$STATE_OK"
printf '{"favorites":[]}\n' >"$TMP/state-nosession.json"
printf 'not json at all\n' >"$TMP/state-broken.json"

is "qa_session_id reads a real record" "$(qa_session_id "$STATE_OK")" "t:live1"
is "a missing state file is NOFILE, not ''" "$(qa_session_id "$TMP/gone.json")" "NOFILE"
is "an unparseable state file is NOFILE, not ''" "$(qa_session_id "$TMP/state-broken.json")" "NOFILE"
is "a parsed file with no record is NOSESSION" "$(qa_session_id "$TMP/state-nosession.json")" "NOSESSION"

STATE_JSON='{"service":{"playing":true,"nowPlaying":{"id":"t:live1"},"failedAt":{}}}'
is "qa_field reads a value" "$(qa_field "d['nowPlaying']['id']" "$STATE_JSON")" "t:live1"
is "qa_field renders a bool as JSON" "$(qa_field "d['playing']" "$STATE_JSON")" "true"
is "an absent field is NOFIELD, not ''" "$(qa_field "d['failedAt'].get('t:live1')" "$STATE_JSON")" "NOFIELD"
is "a dead IPC (empty answer) is NOSTATE, not ''" "$(qa_field "d['playing']" "")" "NOSTATE"
is "an unparseable answer is NOSTATE, not ''" "$(qa_field "d['playing']" "garbage")" "NOSTATE"

# The P14 shape. `is "... raises no second mark" "$(svc ...)" ""` demanded
# exactly the value every failure mode of the tooling produced.
old_field() { python3 -c '
import json, sys
try: d = json.loads(sys.argv[2])["service"]
except Exception: print(""); raise SystemExit(0)
try: v = eval(sys.argv[1])
except Exception: v = None
print(json.dumps(v) if isinstance(v, bool) else ("" if v is None else v))' "$1" "$2" 2>/dev/null; }
is "the old helper answered a DEAD IPC with exactly the expected ''" \
   "$(old_field "d['failedAt'].get('t:live1')" "")" ""
ck "so the P14 assertion passed with no service behind it at all" \
   '[[ "$(old_field "d['\''failedAt'\''].get('\''t:live1'\'')" "")" == "" ]]'
ck "the same assertion against qa_field now FAILS on a dead IPC" \
   '[[ "$(qa_field "d['\''failedAt'\''].get('\''t:live1'\'')" "")" != "NOFIELD" ]]'
ck "and still PASSES when the service really answers 'no mark'" \
   '[[ "$(qa_field "d['\''failedAt'\''].get('\''t:live1'\'')" "$STATE_JSON")" == "NOFIELD" ]]'

section "qa_json_field / qa_guide_field (M2-03 CN23: the number verbs)"

# What a tree WITH the four verbs answers, and what one without them answers.
# The second shape is the whole reason these predicates exist: every field is
# null, so a check written against a bare value would read the absence as the
# answer and pass against a harness that cannot drive the feature at all.
NUM_OK='{"ok":true,"error":"","active":true,"buffer":"10","kind":"prefix","label":"101","targetName":"BBC One HD","matches":1,"ordinal":1,"scopeId":"all","cursorIndex":3,"query":"","resume":false,"hasNumbers":true}'
NUM_NOVERB='{"ok":false,"error":"no_verb","active":null,"buffer":null,"kind":null,"label":null,"targetName":null,"matches":null,"ordinal":null,"scopeId":null,"cursorIndex":null,"query":null,"resume":null,"hasNumbers":null}'
STATE_GUIDE='{"guide":{"cursorIndex":3,"hasNumbers":true,"numberEntry":{"active":false,"buffer":"","resume":true}},"service":{"playing":false}}'
STATE_NOGUIDE='{"guide":null,"service":{"playing":false}}'

is "qa_json_field reads a value"          "$(qa_json_field "d['buffer']" "$NUM_OK")" "10"
is "qa_json_field renders a bool as JSON" "$(qa_json_field "d['active']" "$NUM_OK")" "true"
is "a number the entry really reports"    "$(qa_json_field "d['cursorIndex']" "$NUM_OK")" "3"
is "a tree without the verb answers NOFIELD, not false" "$(qa_json_field "d['active']" "$NUM_NOVERB")" "NOFIELD"
is "and the error it carries is readable" "$(qa_json_field "d['error']" "$NUM_NOVERB")" "no_verb"
is "a dead IPC is NOSTATE, not ''"        "$(qa_json_field "d['active']" "")" "NOSTATE"
is "an unparseable answer is NOSTATE"     "$(qa_json_field "d['active']" "{oops")" "NOSTATE"
# The bug shape this prevents, written out: `active` null reading as inactive.
old_number_field() { python3 -c '
import json, sys
try: d = json.loads(sys.argv[2])
except Exception: print(""); raise SystemExit(0)
try: v = eval(sys.argv[1])
except Exception: v = None
print(json.dumps(v) if isinstance(v, bool) else ("" if v is None else v))' "$1" "$2" 2>/dev/null; }
ck "a bare reader answers the no-verb tree with '', which an 'is it off?' check accepts" \
   '[[ "$(old_number_field "d['\''active'\'']" "$NUM_NOVERB")" != "true" ]]'
ck "qa_json_field refuses to let that count as an answer" \
   '[[ "$(qa_json_field "d['\''active'\'']" "$NUM_NOVERB")" == "NOFIELD" ]]'
ck "and still reports a real 'not active' as false" \
   '[[ "$(qa_json_field "d['\''active'\'']" "{\"active\":false}")" == "false" ]]'

is "qa_guide_field digs into the guide half"   "$(qa_guide_field "d['cursorIndex']" "$STATE_GUIDE")" "3"
is "it reaches the nested entry"               "$(qa_guide_field "d['numberEntry']['resume']" "$STATE_GUIDE")" "true"
is "a guide that never loaded is NOSTATE"      "$(qa_guide_field "d['cursorIndex']" "$STATE_NOGUIDE")" "NOSTATE"
is "a state() answer without a guide key is NOSTATE" "$(qa_guide_field "d['cursorIndex']" '{"service":{}}')" "NOSTATE"
is "a dead IPC is NOSTATE here too"            "$(qa_guide_field "d['cursorIndex']" "")" "NOSTATE"
is "a pre-M2-03 guide answers NOFIELD for the new key" "$(qa_guide_field "d['hasNumbers']" '{"guide":{"cursorIndex":3}}')" "NOFIELD"

ck "qa_value rejects the empty string"  '! qa_value ""'
ck "qa_value rejects NOSTATE"           '! qa_value "$QA_NO_STATE"'
ck "qa_value rejects NOFIELD"           '! qa_value "$QA_NO_FIELD"'
ck "qa_value rejects NOFILE"            '! qa_value "$QA_NO_FILE"'
ck "qa_value rejects NOSESSION"         '! qa_value "$QA_NO_SESSION"'
ck "qa_value accepts a real answer"     'qa_value "t:live1"'

# ======================================================== qa_cmdline (A5)

section "qa_cmdline / A5: an empty pid used to read the KERNEL command line"

old_cmdline_of() { tr '\0' ' ' <"/proc/$1/cmdline" 2>/dev/null; }
kernel=$(old_cmdline_of "")
ck "the shipped helper with an empty pid returned the kernel command line" \
   '[[ -n "$kernel" ]]'
# The six S-03 sweeps at :253-257 against that value, verbatim in shape:
ck "so 'no URL on the command line' passed against it"        '[[ "$kernel" != *"://"* ]]'
ck "so 'no credential on the command line' passed against it" '[[ "$kernel" != *"s3cr3tpw"* ]]'
st "qa_cmdline refuses an empty pid"        1 qa_cmdline ""
st "qa_cmdline refuses a non-numeric pid"   1 qa_cmdline "abc"
st "qa_cmdline refuses a pid that is gone"  1 qa_cmdline 99999999
st "qa_cmdline reads a live process"        0 qa_cmdline "$$"
ck "and what it read is this shell's own argv" '[[ "$(qa_cmdline $$)" == *bash* ]]'

# ======================================================== qa_leak_scan (A1)

section "qa_leak_scan / A1: 'redaction ok' on a capture that caught nothing"

J="$TMP/journal.txt"; Q="$TMP/qs-log.txt"
LEAK='(https?|rtsp|rtmp)://[^ ]*[@?]|password=|username='
: >"$J"; : >"$Q"
# The shipped form, verbatim in shape from qa-live.sh:186.
old_sweep() { grep -nE "$LEAK" "$J" "$Q" 2>/dev/null && echo "REDACTION FAILURE" || echo "redaction ok"; }
is "the shipped sweep called two EMPTY captures 'redaction ok'" "$(old_sweep)" "redaction ok"
st "qa_leak_scan calls that vacuous, not clean" 2 qa_leak_scan 'omarchy-iptv' "$LEAK" "$J" "$Q"

printf 'journalctl: Failed to add match: Invalid argument\n' >"$J"
is "the shipped sweep called a FAILED journalctl 'redaction ok'" "$(old_sweep)" "redaction ok"
st "qa_leak_scan still calls it vacuous" 2 qa_leak_scan 'omarchy-iptv' "$LEAK" "$J" "$Q"

st "qa_leak_scan is vacuous when a capture file is missing" \
   2 qa_leak_scan 'omarchy-iptv' "$LEAK" "$TMP/no-journal.txt" "$Q"

printf 'omarchy-shell[1]: omarchy-iptv: playlist http://host (3 channels)\n' >"$J"
printf 'omarchy-iptv: guide opened\n' >"$Q"
st "with a real capture and no leak it passes" 0 qa_leak_scan 'omarchy-iptv' "$LEAK" "$J" "$Q"

printf 'omarchy-shell[1]: omarchy-iptv: playlist http://u:p@host/x.m3u?token=1\n' >>"$J"
st "and it FAILS the moment a credential appears" 1 qa_leak_scan 'omarchy-iptv' "$LEAK" "$J" "$Q"
# A leak on a line that is not ours is still a leak in our evidence bundle.
printf 'someone-else: http://u:p@host/x\n' >"$J"
st "a leak on an unlabelled line still fails, given a live capture" \
   1 qa_leak_scan 'omarchy-iptv' "$LEAK" "$J" "$Q"
# But with nothing of ours anywhere, there is no evidence either way.
: >"$Q"; printf 'someone-else: http://u:p@host/x\n' >"$J"
st "a capture holding none of our lines is vacuous, never 'ok'" \
   2 qa_leak_scan 'omarchy-iptv' "$LEAK" "$J" "$Q"

# =================================================== qa_leak_on_labelled (A4)

section "qa_leak_on_labelled / A4: the Sources privacy sweep"

SL="$TMP/scenario.log"
LABELS='sourceProbeFinished|sourceSwitched|updateEntryInline'
: >"$SL"
old_labelled() { ! grep -E "$LABELS" "$SL" | grep -qE "://"; }
ck "the shipped sweep PASSED on an empty log"  'old_labelled'
st "qa_leak_on_labelled calls that vacuous"    2 qa_leak_on_labelled "$LABELS" '://' "$SL"

printf 'some other line http://user:pw@host/x\n' >"$SL"
ck "the shipped sweep PASSED on a log leaking a URL on an unlabelled line" 'old_labelled'
st "qa_leak_on_labelled is still vacuous there (no labelled line to judge)" \
   2 qa_leak_on_labelled "$LABELS" '://' "$SL"

printf 'omarchy-iptv sourceSwitched {"id":"584a58e5"}\n' >>"$SL"
st "with a labelled line present and clean, it passes" 0 qa_leak_on_labelled "$LABELS" '://' "$SL"
printf 'omarchy-iptv sourceProbeFinished {"url":"http://u:p@host/x"}\n' >>"$SL"
st "and it fails when a labelled line leaks" 1 qa_leak_on_labelled "$LABELS" '://' "$SL"

st "qa_answer_lacks calls an empty IPC answer vacuous" 2 qa_answer_lacks '://' ""
st "qa_answer_lacks passes a real answer with no URL"  0 qa_answer_lacks '://' '{"service":{"channels":20}}'
st "qa_answer_lacks fails a real answer carrying one"  1 qa_answer_lacks '://' '{"url":"http://h/x"}'

# =================================================== qa_json_normalized (A3)

section "qa_json_normalized / A3: 'shell.json restored' from two failed jq runs"

BEFORE="$TMP/shell.json.before"; AFTER="$TMP/shell.json"
old_restore() { diff <(jq -S . "$BEFORE" 2>/dev/null) <(jq -S . "$AFTER" 2>/dev/null) >/dev/null 2>&1 && echo "shell.json restored" || echo "differs"; }
# Both jq calls failing is the false all-clear: two empty substitutions
# compare equal and the phase reports the user's config restored.
rm -f "$BEFORE" "$AFTER"
is "the shipped diff reported 'restored' when BOTH jq runs failed" "$(old_restore)" "shell.json restored"
st "qa_json_normalized refuses a missing file"       1 qa_json_normalized "$BEFORE"
printf '{"bar": oops\n' >"$BEFORE"; printf '{"bar": oops\n' >"$AFTER"
is "the same all-clear on two MALFORMED files" "$(old_restore)" "shell.json restored"
st "qa_json_normalized refuses malformed JSON"       1 qa_json_normalized "$BEFORE"
: >"$BEFORE"; : >"$AFTER"
is "and on two EMPTY files (jq exits 0 printing nothing)" "$(old_restore)" "shell.json restored"
st "qa_json_normalized refuses an empty file"        1 qa_json_normalized "$BEFORE"
printf '{"bar":{"layout":[[{"id":"x"}]]}}\n' >"$AFTER"
cp "$AFTER" "$BEFORE"
st "qa_json_normalized accepts a real snapshot"      0 qa_json_normalized "$BEFORE"
ck "and two real snapshots compare equal"            '[[ "$(qa_json_normalized "$BEFORE")" == "$(qa_json_normalized "$AFTER")" ]]'
printf '{"bar":{"layout":[[{"id":"x"},{"id":"io.github.rmcdavid.iptv"}]]}}\n' >"$AFTER"
ck "and a real difference is still seen"             '[[ "$(qa_json_normalized "$BEFORE")" != "$(qa_json_normalized "$AFTER")" ]]'

# ======================================================== qa_tree_count (A2)

section "qa_tree_count / A2: 'no writes in the plugin dir' for a dir that is not there"

PDIR="$TMP/plugin"
old_writes() { find "$PDIR" -newer "$PDIR/manifest.json" 2>/dev/null | wc -l; }
is "the shipped find printed no hits for a MISSING plugin directory" "$(old_writes)" "0"
st "qa_tree_count refuses a missing directory" 1 qa_tree_count "$PDIR"
mkdir -p "$PDIR"
printf '{}\n' >"$PDIR/manifest.json"
printf 'x\n' >"$PDIR/Model.js"
ck "qa_tree_count counts what a find would actually examine" '(( $(qa_tree_count "$PDIR") >= 3 ))'

# ========================================================= qa_same_file (C1)

section "qa_same_file / C1: a failed cp leaves the previous run's tree in place"

printf 'new tree\n' >"$TMP/src.js"
printf 'PREVIOUS RUN\n' >"$TMP/dst.js"
st "qa_same_file sees a stale copy"          1 qa_same_file "$TMP/src.js" "$TMP/dst.js"
st "qa_same_file sees a missing copy"        1 qa_same_file "$TMP/src.js" "$TMP/never.js"
cp "$TMP/src.js" "$TMP/dst.js"
st "qa_same_file accepts a good copy"        0 qa_same_file "$TMP/src.js" "$TMP/dst.js"

# ====================================================== qa_wait_nonempty (C6)

section "qa_wait_nonempty / C6: the port file read after a flat sleep"

: >"$TMP/silent.port"
st "an empty port file is a timeout, not an empty port" 1 qa_wait_nonempty "$TMP/silent.port" 1
( sleep 0.3; printf '41234\n' >"$TMP/silent.port" ) &
st "and a port that arrives late is waited for"        0 qa_wait_nonempty "$TMP/silent.port" 5
wait
is "the port read after the wait is the real one" "$(cat "$TMP/silent.port")" "41234"

# ========================================================= qa_case_arm (D1)

section "qa_case_arm / D1: a capability gate satisfied by the header comment"

RUNSH="$TMP/run.sh"
cp "$ROOT/scripts/dev-harness/run.sh" "$RUNSH"
st "the real run.sh parses --detach"  0 qa_case_arm "$RUNSH" "--detach"
st "the real run.sh parses clean"     0 qa_case_arm "$RUNSH" "clean"
# Delete the parser arm, keep the header comment that documents it.
grep -v '^ *--detach) DETACH=1; KEEP_PLAYER=1 ;;$' "$RUNSH" >"$RUNSH.cut" && mv "$RUNSH.cut" "$RUNSH"
ck "the option is GONE from the parser" '! grep -qE "^[[:space:]]*--detach\) DETACH" "$RUNSH"'
ck "but the header comment still mentions it" 'grep -q -- "--detach" "$RUNSH"'
ck "the shipped gate (bare grep) still reported it present" 'grep -q -- "--detach" "$RUNSH"'
st "qa_case_arm reports it MISSING"   1 qa_case_arm "$RUNSH" "--detach"

# ================================================= qa_defines_function (D3)

section "qa_defines_function / D3: a gate satisfied by a comment"

CMT="$TMP/commented.js"
printf '// validateSourceUrl and xtreamUrls used to live here\n' >"$CMT"
ck "the shipped gate (bare name grep) passed on the comment alone" \
   'grep -qE "validateSourceUrl|xtreamUrls" "$CMT"'
st "qa_defines_function does not"     1 qa_defines_function "$CMT" "validateSourceUrl"
printf 'function validateSourceUrl(raw) { return raw }\n' >>"$CMT"
st "and it passes on a real definition" 0 qa_defines_function "$CMT" "validateSourceUrl"

# ========================================================== qa_env_line (C2)

section "qa_env_line / C2: an environment file that re-expands what it records"

hostile='/tmp/qa $(id -u) `id -u` "q" \back'
printf 'export NASTY="%s"\n' "$hostile" >"$TMP/old.env"
# shellcheck source=/dev/null
( NASTY=""; . "$TMP/old.env"; printf '%s\n' "$NASTY" ) >"$TMP/old.out"
ck "the shipped hand-quoted line did NOT round-trip the value" \
   '[[ "$(cat "$TMP/old.out")" != "$hostile" ]]'
ck "it executed the command substitution it carried" \
   'grep -q "$(id -u)" "$TMP/old.out"'
# F4: the same data reaching `bash -c` as text. The snippets bake $SCRATCH in
# at print time, so the defence this round is to refuse a path that is code.
printf 'echo INJECTED > %s/pwned\n' "$TMP" >"$TMP/payload"
evil="$TMP/s\$(sh $TMP/payload)dir"
rm -f "$TMP/pwned"
bash -c "ls $evil >/dev/null 2>&1" 2>/dev/null || true
ck "a scratch path carrying \$(...) IS executed by the shipped sh_step shape" \
   '[[ -f "$TMP/pwned" ]]'
st "qa_safe_path refuses it"                    1 qa_safe_path "$evil"
st "qa_safe_path refuses a quote"               1 qa_safe_path "/tmp/a\"b"
st "qa_safe_path refuses a backquote"           1 qa_safe_path '/tmp/a`b'
st "qa_safe_path refuses a semicolon"           1 qa_safe_path "/tmp/a;rm -rf ."
st "qa_safe_path refuses a relative path"       1 qa_safe_path "scratch"
st "qa_safe_path accepts an ordinary scratch dir" 0 qa_safe_path "/run/user/1000/omarchy-iptv-qa-player"

qa_env_line NASTY "$hostile" >"$TMP/new.env"
# shellcheck source=/dev/null
( NASTY=""; . "$TMP/new.env"; printf '%s\n' "$NASTY" ) >"$TMP/new.out"
is "qa_env_line round-trips it byte for byte" "$(cat "$TMP/new.out")" "$hostile"

# ============================== the assertion-count floor (B4, D-PLY-9 (b))

section "the floor / B4: a check that stops executing must turn the run red"

PS="$ROOT/scripts/dev-harness/player-scenario.sh"
FRAME="$TMP/frame.sh"
# The shipped counters, extracted verbatim - not a copy of them.
sed -n '/^ok()  { printf/,/^ck()  { checks=/p' "$PS" >"$FRAME"
is "the counting frame was extracted from the real scenario" \
   "$(qa_count '^(is|ck)\(\)' "$FRAME")" "2"

# Drive the P11 assertion, in its real shape, under BOTH helpers.
# The counters are reported from an EXIT trap, because the whole point is that
# the statement AFTER the dead expansion may not run either.
: >"$TMP/p11.log"; rm -f "$TMP/p11.count"
(
  pass=0; fail=0; checks=0
  trap 'printf "%s %s %s\n" "$checks" "$pass" "$fail" >"$TMP/p11.count"' EXIT
  # shellcheck source=/dev/null
  . "$FRAME"
  old_lc() { grep -acE "$1" "$TMP/p11.log" 2>/dev/null || echo 0; }
  before=$(old_lc 'mpv unresponsive')
  printf 'omarchy-iptv: mpv unresponsive, restarting player\n' >>"$TMP/p11.log"
  is "P11 exactly ONE relaunch" "$(( $(old_lc 'mpv unresponsive') - before ))" "1"
) >/dev/null 2>&1
is "with the shipped helper the P11 assertion moved no counter at all" \
   "$(cat "$TMP/p11.count" 2>/dev/null)" "0 0 0"

: >"$TMP/p11.log"
ran_new=$(
  pass=0; fail=0; checks=0
  # shellcheck source=/dev/null
  . "$FRAME"
  SCRATCH=$TMP
  new_lc() { qa_count "$1" "$TMP/p11.log"; }
  before=$(new_lc 'mpv unresponsive')
  printf 'omarchy-iptv: mpv unresponsive, restarting player\n' >>"$TMP/p11.log"
  is "P11 exactly ONE relaunch" "$(( $(new_lc 'mpv unresponsive') - before ))" "1" >/dev/null
  printf '%s %s\n' "$checks" "$pass"
)
is "with qa_count it executes, and passes on one relaunch" "$ran_new" "1 1"
: >"$TMP/p11.log"
ran_two=$(
  pass=0; fail=0; checks=0
  # shellcheck source=/dev/null
  . "$FRAME"
  new_lc() { qa_count "$1" "$TMP/p11.log"; }
  before=$(new_lc 'mpv unresponsive')
  printf 'omarchy-iptv: mpv unresponsive, restarting player\n' >>"$TMP/p11.log"
  printf 'omarchy-iptv: mpv unresponsive, restarting player\n' >>"$TMP/p11.log"
  is "P11 exactly ONE relaunch" "$(( $(new_lc 'mpv unresponsive') - before ))" "1" >/dev/null
  printf '%s %s\n' "$checks" "$fail"
)
is "and FAILS on a second relaunch at the healthy player" "$ran_two" "1 1"

# The floor itself: the arithmetic at the end of the scenario, in isolation.
floor_verdict=$(
  pass=0; fail=0; checks=0
  # shellcheck source=/dev/null
  . "$FRAME"
  checks=81                     # one assertion silently skipped, as D-PLY-9 did
  ran=$checks
  is "the harness ran every check it has" "$ran" "82" >/dev/null
  printf '%s\n' "$fail"
)
is "the floor turns the run RED when one check does not execute" "$floor_verdict" "1"
floor_ok=$(
  pass=0; fail=0; checks=0
  # shellcheck source=/dev/null
  . "$FRAME"
  checks=82
  ran=$checks
  is "the harness ran every check it has" "$ran" "82" >/dev/null
  printf '%s\n' "$fail"
)
is "and stays green when they all do" "$floor_ok" "0"

# And keep the floor honest: it must equal the assertions the file has. One
# grep here means a forgotten bump turns check.sh red on THIS machine rather
# than the display lane's, weeks later.
declared=$(grep -oE '^EXPECTED_CHECKS=[0-9]+' "$PS" | head -1 | cut -d= -f2)
top=$(qa_count '^(is|ck) ' "$PS")            # includes the floor's own line
inloop=$(qa_count '^[[:space:]]+(is|ck) ' "$PS")   # P14's `for again in 1 2`
is "the player floor matches the assertions that scenario actually has" \
   "$declared" "$(( top - 1 + 2 * inloop ))"

# ================== qa_delta, and the P11 assertion CL10 repointed (D-PLY-9)

section "qa_delta / CL10: the one-relaunch property, on a counter both trees have"

# The counter comes back over IPC, so it has many more ways to answer
# non-numerically than a grep has. Every one of them used to be the D-PLY-9
# shape all over again.
is "qa_delta on two readings is the difference" "$(qa_delta 7 8)" "1"
is "qa_delta counts a second relaunch as 2" "$(qa_delta 7 9)" "2"
is "qa_delta is one line" "$(qa_delta 7 9 | wc -l)" "1"
is "a NOFIELD reading is NODELTA, not an arithmetic death" "$(qa_delta NOFIELD 9)" "NODELTA"
is "an empty reading is NODELTA too" "$(qa_delta "" 9)" "NODELTA"
is "and NODELTA is not a value" "$(qa_value NODELTA && echo yes || echo no)" "no"
st "qa_delta reports VACUOUS on a non-numeric side" 2 qa_delta NOFIELD 9
# The kill, again: the naked arithmetic stops bash from running the command
# the substitution belongs to, so neither counter moves. qa_delta cannot.
ran=$( { printf 'yes:%s\n' "$(( 9 - $(printf 'NOFIELD\n') ))"; } 2>/dev/null )
is "the naked arithmetic on a NOFIELD reading skips its command entirely" "${ran:-no}" "no"
ran=$( { printf 'yes:%s\n' "$(qa_delta "$(printf 'NOFIELD\n')" 9)"; } 2>/dev/null )
is "with qa_delta the command runs and carries the sentinel" "$ran" "yes:NODELTA"

# Now the assertion itself, taken VERBATIM out of the shipped scenario rather
# than retyped here, and driven against the counter readings each tree
# produces. Wave two measured the fixed tree live three times
# (docs/QA-RESULTS.md D4): status.player.seq delta 1, player.lock seq delta 1.
# A tree that leaves the delivered relaunch queued fires a second
# `player restart` at the player it has just respawned, so both read 2.
P11SEQ="$TMP/p11-seq.sh"
grep -E '^(before11=|beforelock11=|is "P11 exactly ONE relaunch|is "P11 and the player lock)' "$PS" >"$P11SEQ"
is "the P11 seq assertion was extracted from the real scenario, all four lines" \
   "$(qa_count '.' "$P11SEQ")" "4"
is "and it reads the counter, not the journal" \
   "$(qa_count 'log_count' "$P11SEQ")" "0"

# <series file> holds the successive readings one per line; the stub pops one
# per call, which is exactly how the scenario reads it (before, then after).
p11_run() {
  local seqs=$1 locks=$2
  (
    pass=0; fail=0; checks=0
    # shellcheck source=/dev/null
    . "$FRAME"
    printf '%s\n' "$seqs" >"$TMP/seq.cursor"
    printf '%s\n' "$locks" >"$TMP/lock.cursor"
    pop() { local f=$1 v; v=$(head -1 "$f"); sed -i 1d "$f"; printf '%s\n' "$v"; }
    player_seq() { pop "$TMP/seq.cursor"; }
    lock_seq()   { pop "$TMP/lock.cursor"; }
    # shellcheck source=/dev/null
    . "$P11SEQ" >/dev/null
    printf '%s %s %s\n' "$checks" "$pass" "$fail"
  )
}
is "at this tree the counter reads one relaunch and the check PASSES" \
   "$(p11_run "$(printf '4\n5')" "$(printf '4\n5')")" "2 2 0"
is "at the older tree it reads two and the SAME check FAILS" \
   "$(p11_run "$(printf '4\n6')" "$(printf '4\n6')")" "2 0 2"
is "a shell that answers NOFIELD fails the check instead of skipping it" \
   "$(p11_run "$(printf 'NOFIELD\nNOFIELD')" "$(printf 'NOFILE\nNOFILE')")" "2 0 2"

SS="$ROOT/scripts/dev-harness/sources-scenario.sh"
sdeclared=$(grep -oE '^EXPECTED_CHECKS=[0-9]+' "$SS" | head -1 | cut -d= -f2)
is "the sources floor matches the assertions that scenario actually has" \
   "$sdeclared" "$(( $(qa_count '^check ' "$SS") + $(qa_count '^checks=[$][(][(]checks' "$SS") - 1 ))"

# M2-03's scenario, the third suite, and the first with TWO floors: it runs
# either the preflight alone (no display, no quickshell) or the preflight plus
# the live half, and a single number could not cover both. Same rule as the
# other two: one grep here means a forgotten bump turns check.sh red on this
# machine rather than on the display lane's, weeks later.
CS="$ROOT/scripts/dev-harness/chno-scenario.sh"
# Non-vacuity first. Both `is` lines below compare two computed strings, and
# two EMPTY strings are equal - so a renamed variable or a moved file would
# "pass" both. Assert the declarations exist before comparing them.
is "the chno scenario declares exactly two floors" \
   "$(qa_count '^ *EXPECTED_CHECKS=[0-9]+$' "$CS")" "2"
cdeclared_tree=$(grep -oE 'EXPECTED_CHECKS=[0-9]+' "$CS" | sed -n 1p | cut -d= -f2)
cdeclared_live=$(grep -oE 'EXPECTED_CHECKS=[0-9]+' "$CS" | sed -n 2p | cut -d= -f2)
# The preflight is seam lines only; the live half adds every `check` line plus
# the privacy block's two hand-written bumps (the `checks=$((checks + 1))`
# inside seam() and the floor's own bump land outside this count). The two
# recount recipes are written in the scenario's own footer; these are them.
is "the chno check-tree floor matches the preflight it actually has" \
   "$cdeclared_tree" "$(qa_count '^ *seam ' "$CS")"
is "the chno live floor matches the assertions that scenario actually has" \
   "$cdeclared_live" "$(( $(qa_count '^ *(check|seam) ' "$CS") + 2 ))"
# A floor is only worth having if the runner it guards can be seen going red.
# The scenario's verdict is the same arithmetic the player's is, so drive it
# here with the chno numbers rather than trusting that it reads the same.
chno_floor_verdict=$(
  pass=0; fail=0; checks=0
  # shellcheck source=/dev/null
  . "$FRAME"
  ran=$(( cdeclared_live - 1 ))          # one live check silently skipped
  is "the scenario ran every check it has" "$ran" "$cdeclared_live" >/dev/null
  printf '%s\n' "$fail"
)
is "one skipped chno check turns that run RED" "$chno_floor_verdict" "1"

# M2-03 ruling CN23's runner, the fourth suite. Same two-floor shape as the
# chno one, and the same reason for asserting it here: scripts/check.sh runs
# its check-tree half on every commit, so a forgotten bump is caught on this
# machine rather than on the display lane's.
CE="$ROOT/scripts/dev-harness/chno-entry-scenario.sh"
is "the chno-entry scenario exists and declares exactly two floors" \
   "$(qa_count '^ *EXPECTED_CHECKS=[0-9]+$' "$CE")" "2"
edeclared_tree=$(grep -oE 'EXPECTED_CHECKS=[0-9]+' "$CE" | sed -n 1p | cut -d= -f2)
edeclared_live=$(grep -oE 'EXPECTED_CHECKS=[0-9]+' "$CE" | sed -n 2p | cut -d= -f2)
# The recipes are written in that file's footer; these are them. The +1 is the
# run.sh option probe, which bumps `checks` by hand; the live half adds the
# privacy block's two.
is "the chno-entry check-tree floor matches the preflight it actually has" \
   "$edeclared_tree" "$(( $(qa_count '^ *seam ' "$CE") + 1 ))"
is "the chno-entry live floor matches the assertions that scenario actually has" \
   "$edeclared_live" "$(( $(qa_count '^ *(check|seam) ' "$CE") + 3 ))"
# And check.sh's own floor for the preflight must match what the preflight
# prints: 20 assertions plus its "ran every check" line. A floor above what
# the runner can produce would make the gate permanently red; one below it
# would let a section stop executing.
is "check.sh's preflight floor matches the scenario's own" \
   "$(grep -oE 'CHNO_ENTRY_MIN:-[0-9]+' "$ROOT/scripts/check.sh" | cut -d- -f2)" "$(( edeclared_tree + 1 ))"

# M2-05's runner, the fifth suite. Same two-floor shape and the same reason.
PS5="$ROOT/scripts/dev-harness/pip-scenario.sh"
is "the pip scenario exists and declares exactly two floors" \
   "$(qa_count '^ *EXPECTED_CHECKS=[0-9]+$' "$PS5")" "2"
pdeclared_tree=$(grep -oE 'EXPECTED_CHECKS=[0-9]+' "$PS5" | sed -n 1p | cut -d= -f2)
pdeclared_live=$(grep -oE 'EXPECTED_CHECKS=[0-9]+' "$PS5" | sed -n 2p | cut -d= -f2)
# The +1 is the stub's executable probe, which bumps `checks` by hand; the
# live half adds the privacy block's two. `absent` counts with `seam`: it is
# the same kind of tree assertion, written so that an absence test proves the
# file is there first (a `seam ... 0` would pass against a deleted file).
is "the pip check-tree floor matches the preflight it actually has" \
   "$pdeclared_tree" "$(( $(qa_count '^ *(seam|absent) ' "$PS5") + 1 ))"
is "the pip live floor matches the assertions that scenario actually has" \
   "$pdeclared_live" "$(( $(qa_count '^ *(check|seam|absent) ' "$PS5") + 3 ))"
# And no absence is ever asserted with a `want` of 0, which `seam` treats as
# "at least none" and can therefore never fail. This is the fifth check-that-
# cannot-fail this project has had to remove; it is worth one line to stop
# the sixth.
is "no seam in the pip scenario asserts a count of zero" \
   "$(qa_count '^ *seam .* 0$' "$PS5")" "0"
is "check.sh's pip preflight floor matches the scenario's own" \
   "$(grep -oE 'PIP_PREFLIGHT_MIN:-[0-9]+' "$ROOT/scripts/check.sh" | cut -d- -f2)" "$(( pdeclared_tree + 1 ))"
# And the one thing that makes the pip scenario safe to run at all: it drives
# a STUB compositor, put in front of PATH by run.sh. A scenario that lost
# that line would float, shrink and pin windows in the session of whoever ran
# it, and it would still pass.
is "the pip scenario never reaches the real compositor" \
   "$(qa_count 'ln -sfn "\$HERE/stub-hyprctl.py" "\$SCRATCH/bin/hyprctl"' "$PS5")" "2"
is "and run.sh is what puts it in front of PATH" \
   "$(qa_count 'export PATH="\$SCRATCH/bin:\$PATH"' "$ROOT/scripts/dev-harness/run.sh")" "1"

# D-PIP-6. check.sh runs the preflight and only the preflight, which is
# right: the live half starts a quickshell and a real player, and no gate may
# do that. What is NOT right is a live half that answers 63 PASS 11 FAIL in a
# file nobody runs, which is what it did. It cannot be run from here, so what
# is asserted from here is the shape that makes its silence honest.
is "the pip scenario refuses to start a live half it cannot run" \
   "$(qa_count '^requires_live\(\) \{' "$PS5")" "1"
is "and the live half is gated on that answer rather than merely offered it" \
   "$(qa_count '^ *if ! requires_live; then' "$PS5")" "1"
is "a skip says so with a status of its own, never 0" \
   "$(qa_count '^LIVE_SKIP=77$' "$PS5")" "1"
is "and a red preflight is still a failure, skip or no skip" \
   "$(qa_count 'fail == 0 \)\) \|\| exit 1' "$PS5")" "1"
# The cause D-PIP-6 turned out to be: the live half played a channel whose
# URL is a dead local port, mpv exits under --idle=once, and every check
# after P3 asserted about a player that was gone. The fixture's one channel
# with a real stream behind it is what it plays now, served by run.sh the way
# player-scenario.sh has always done it.
is "the live half plays the channel that has a real stream behind it" \
   "$(qa_count 'ipc play "t:harness.live"' "$PS5")" "1"
is "and asks run.sh to serve one, detached so a restart can be tested" \
   "$(qa_count '"\$RUN" --detach --serve' "$PS5")" "1"
is "no scenario here plays a dead URL and then asserts about the player" \
   "$(qa_count 'ipc play "t:(bbc|itv|sky|dw|arte|zdf|kids|expired)' "$PS5")" "0"

section "qa_openms: the open-budget number, and the payload that could not fail"

# The condition that used to make this check pass silently, driven for real.
# Before 2026-09-25 openMs resolved the literal objectName "resultList",
# DISCARDED the result, and emitted a payload with no field naming what it had
# forced. With a second channel view on screen it would have laid out nothing
# and reported a fast number for an empty grid. So the old payload -- byte for
# byte what the instrument used to print -- must be VACUOUS here, never a pass.
OLD_PAYLOAD='{"ms":[91,88,90],"rows":1462,"logoColumn":true,"showLogos":true}'
NEW_PAYLOAD='{"ms":[91,88,90],"rows":1462,"logoColumn":true,"showLogos":true,"view":"resultList","realised":13}'
WRONG_VIEW='{"ms":[12,11,12],"rows":1462,"view":"channelWall","realised":0}'
NOTHING_FORCED='{"ms":[12,11],"rows":1462,"view":"","realised":-1}'

qa_openms "resultList" "$OLD_PAYLOAD" >/dev/null 2>&1
is "the pre-2026-09-25 payload is VACUOUS, not a number" "$?" "2"

qa_openms "resultList" "$NEW_PAYLOAD" >/dev/null 2>&1
is "a payload that names the view it forced is a pass" "$?" "0"
is "and it yields the timings and the realised delegate count" \
   "$(qa_openms 'resultList' "$NEW_PAYLOAD")" "91,88,90 13"

qa_openms "resultList" "$WRONG_VIEW" >/dev/null 2>&1
is "a real number for the WRONG screen is a failure, not a pass" "$?" "1"

qa_openms "resultList" "$NOTHING_FORCED" >/dev/null 2>&1
is "forcing nothing is vacuous even though the ms array is populated" "$?" "2"

qa_openms "resultList" 'not json' >/dev/null 2>&1
is "unreadable output is vacuous" "$?" "2"

# And the instrument itself: the two properties the predicate rests on.
SH="$ROOT/scripts/dev-harness/shell.qml"
is "layoutView returns WHICH view it forced, not a bool" \
   "$(qa_count 'return names\[i\]' "$SH")" "1"
is "and openMs USES that return rather than discarding it" \
   "$(qa_count 'forced = harness.layoutView' "$SH")" "1"
is "the old single-literal lookup is gone" \
   "$(qa_count 'findById\(g, "resultList", 0\)' "$SH")" "0"
is "the payload carries the view it measured" \
   "$(qa_count 'view: forced' "$SH")" "1"

section "qa_transcript_start / F-M3-1 (b): the evidence a run leaves behind"

# F-M3-1: a live run of m3-scenario.sh answered "17 passed, 14 failed" and
# WHICH FOURTEEN IS UNKNOWN, because the run was backgrounded and its output
# piped through `tail -n 3`. No check was missing. The evidence was discarded
# by the person running it. So the predicate under test here is not a
# comparison -- it is "the run wrote its evidence down, somewhere private, and
# said where".
#
# Each case below RUNS a throwaway scenario, because the function's whole
# effect is on a real file descriptor: a test that only read qa-lib.sh would
# be rule 14's shape exactly.

TDIR="$TMP/tr"
# scen <name> <dir> <body...> : a one-off scenario that calls the real
# function and then does what the body says. Its own stdout is discarded;
# every assertion below reads the TRANSCRIPT or the file system.
scen() {
  local name=$1 dir=$2
  shift 2
  {
    printf '#!/bin/bash\nset -uo pipefail\n. %q\n' "$HERE/qa-lib.sh"
    printf 'qa_transcript_start %q %q || exit 2\n' "$name" "$dir"
    printf '%s\n' "$@"
  } >"$TMP/scen.sh"
  bash "$TMP/scen.sh"
}

# ---- 1. it redirects for real, and the transcript holds what the run printed
rm -rf "$TDIR"
scen run1 "$TDIR" 'echo "PASS first"' 'echo "FAIL second" >&2' \
  'printf "%s\n" "$QA_TRANSCRIPT" >"'"$TMP"'/path1"' >/dev/null 2>&1
T1=$(cat "$TMP/path1" 2>/dev/null)
ck "the run named its own transcript" '[[ -n $T1 && -f $T1 ]]'
is "stdout reached the transcript" "$(qa_count '^PASS first$' "$T1")" "1"
is "and STDERR reached it too, which is where a scenario's diagnostics go" \
   "$(qa_count '^FAIL second$' "$T1")" "1"
is "the transcript's first line names the transcript (a file that identifies itself)" \
   "$(head -1 "$T1" | grep -c "^== transcript $T1\$")" "1"

# ---- 2. the mode. THIS is the condition that makes the transcript safe to
# exist at all: a scenario's stdout can carry a playlist URL with provider
# credentials (argv-scenario.sh drives one on purpose), so rule 5 and rule 6
# make 0600-in-0700 the only acceptable landing place. The shipped form that
# does NOT do this is one line, so it is driven here verbatim.
is "the transcript is 0600" "$(stat -c '%a' "$T1")" "600"
is "and its directory is 0700" "$(stat -c '%a' "$(dirname "$T1")")" "700"
# The control runs under an EXPLICIT umask, and that is a repair, not a
# flourish. It used to inherit the caller's, and the mode it asserts is
# `0666 & ~umask` -- so this step went red under `umask 077` (600) and under
# `umask 002` (664), reddening scripts/check.sh for a reason with nothing to do
# with the tree. check.sh does not normalise the umask. Found by the first
# review of this file, measured both ways.
old_tee_transcript() {   # tee left to create the file itself
  ( umask 022; bash -c 'exec > >(tee -a "$1"); echo hello' _ "$1" ) >/dev/null 2>&1
  local i
  for ((i = 0; i < 40; i++)); do [[ -s $1 ]] && break; sleep 0.05; done
}
rm -f "$TMP/old.out"
old_tee_transcript "$TMP/old.out"
is "a tee left to create its own file leaves the transcript WORLD-READABLE (at the common umask 022)" \
   "$(stat -c '%a' "$TMP/old.out")" "644"
ck "which is why the file is created here, under umask 077, before tee opens it" \
   '[[ $(stat -c "%a" "$T1") == 600 && $(stat -c "%a" "$TMP/old.out") == 644 ]]'
# And the property that matters is umask-INDEPENDENT, which is the whole point
# of creating the file ourselves: the explicit 0600 holds whatever the caller's
# umask is. Asserted at three, including the two that reddened the step above.
for _um in 022 077 002; do
  _umdir=$TMP/um$_um; mkdir -p "$_umdir"
  _umpath=$( ( umask "$_um"; bash -c '
    export OMARCHY_IPTV_HARNESS_DIR="$1"; source "$2"
    qa_transcript_start "umask'"$_um"'" >/dev/null 2>&1 || exit 9
    printf "%s\n" "$QA_TRANSCRIPT"' _ "$_umdir" "$HERE/qa-lib.sh" ) | tail -1 )
  is "the transcript is 0600 under umask $_um, because we create it and do not let tee" \
     "$(stat -c '%a' "$_umpath" 2>/dev/null)" "600"
done

# ---- 2b. the BROKEN PIPE, which is the failure this whole function exists to
# prevent and which nothing here could see until the first review of it. A
# `tee` whose own stdout breaks EXITS, and the transcript stops at that line --
# so `scenario | head -3` truncated the FILE as well as the terminal, and the
# harness README's "the evidence is on disk whatever happens to the terminal"
# was false. `tee -p` (GNU --output-error=warn-nopipe) is what makes it true.
# Measured here for real: a 12-line producer through `| head -3`.
_pipedir=$TMP/pipe; mkdir -p "$_pipedir"
cat >"$TMP/pipe-scn.sh" <<'PIPE_SCN'
export OMARCHY_IPTV_HARNESS_DIR="$1"
. "$2"
qa_transcript_start "pipeprobe" || exit 9
printf '%s
' "$QA_TRANSCRIPT" >"$3"
for _i in 1 2 3 4 5 6 7 8 9 10; do echo "body $_i"; sleep 0.05; done
echo "SUMMARY REACHED"
PIPE_SCN
bash "$TMP/pipe-scn.sh" "$_pipedir" "$HERE/qa-lib.sh" "$TMP/pipe-path" 2>/dev/null | head -3 >/dev/null
_pipepath=$(cat "$TMP/pipe-path" 2>/dev/null)
qa_wait_file() { local f=$1 pat=$2 n=${3:-40} i; for ((i = 0; i < n; i++)); do grep -q "$pat" "$f" 2>/dev/null && return 0; sleep 0.05; done; return 1; }
qa_wait_file "$_pipepath" '^SUMMARY REACHED$' 60
ck "a transcript survives a broken pipe: the run's SUMMARY is on disk although the terminal got 3 lines" \
   'grep -q "^SUMMARY REACHED$" "$_pipepath"'
is "and every body line is there too, not just the three the pipe took" \
   "$(qa_count '^body ' "$_pipepath")" "10"

# ---- 3. it REFUSES rather than writing somewhere the transcript would be
# readable. /tmp is 1777 and owned by root on every machine this runs on, so
# the chmod cannot fix it -- which is the case the mode check exists for.
# Listed BEFORE and AFTER rather than counted, because a mutation of the
# refusal makes this case write a world-readable transcript into /tmp -- the
# exposure the case is about -- and a red run must not leave it lying there.
# The difference of the two listings is the only file we may delete: a `$$`
# pattern would be wrong (the transcript carries the pid of the throwaway
# scenario's shell, not this one's) and a bare `refuse-*.out` glob is somebody
# else's file to lose.
find /tmp -maxdepth 1 -name 'refuse-*.out' 2>/dev/null | sort >"$TMP/refuse.before"
scen refuse /tmp 'echo "THIS LINE MUST NOT EXIST"' >/dev/null 2>&1
st=$?
find /tmp -maxdepth 1 -name 'refuse-*.out' 2>/dev/null | sort >"$TMP/refuse.after"
leaked=$(comm -13 "$TMP/refuse.before" "$TMP/refuse.after")
is "a directory group or other can enter is refused, with status 2" "$st" "2"
is "and no transcript was created there" "${leaked:-none}" "none"
[[ -z $leaked ]] || printf '%s\n' "$leaked" | while IFS= read -r f; do rm -f "$f"; done

# ---- 4. the name is a FILENAME, never a path, and never empty
for badname in '../escape' '/abs' 'has space' '' '.hidden'; do
  ( . "$HERE/qa-lib.sh"; qa_transcript_start "$badname" "$TDIR" ) >/dev/null 2>&1
  is "a transcript name of '${badname:-<empty>}' is refused" "$?" "2"
done
( . "$HERE/qa-lib.sh"; qa_transcript_start ok 'relative/dir' ) >/dev/null 2>&1
is "a relative directory is refused" "$?" "2"
( . "$HERE/qa-lib.sh"; qa_transcript_start ok '/tmp/a;rm -rf b' ) >/dev/null 2>&1
is "a directory carrying shell text is refused (qa_safe_path, F4/C2)" "$?" "2"

# ---- 5. a refusal must redirect NOTHING. A function that refused and left
# the shell redirected would be the worst of both: no transcript, and the
# operator's terminal silent.
out=$( { . "$HERE/qa-lib.sh"; qa_transcript_start bad/name "$TDIR" 2>/dev/null; echo "still on stdout"; } )
is "a refused start leaves stdout where it was" "$out" "still on stdout"
is "and leaves QA_TRANSCRIPT empty, so nothing downstream reads a stale path" \
   "$( . "$HERE/qa-lib.sh"; qa_transcript_start bad/name "$TDIR" >/dev/null 2>&1; printf '[%s]' "$QA_TRANSCRIPT")" "[]"

# ---- 5b. two runs never share one transcript. The stamp is second-resolution
# and $$ is one shell, so a second start in the same second resolves to the
# same path; appending one run's evidence into another's, under a filename
# that claims to name a single run, is F-M3-1's failure with extra steps.
# The stamp is PINNED, so the collision is driven rather than waited for: two
# starts in the same second is a timing event, and a check that waits for one
# passes 499 runs in 500 and reddens on the 500th for no reason. (Measured the
# flaky way first, and it duly flaked.)
rm -rf "$TDIR/twice"
( export QA_TRANSCRIPT_STAMP=pinned
  scen twice "$TDIR/twice" 'echo "PASS the first run"' \
    'qa_transcript_start twice "'"$TDIR"'/twice"; printf "%s" "$?" >"'"$TMP"'/twicest"' \
    >/dev/null 2>&1 )
is "a second start onto the same path is refused" "$(cat "$TMP/twicest" 2>/dev/null)" "2"
is "the pinned stamp made both calls choose one path (control)" \
   "$(ls "$TDIR"/twice/twice-pinned-*.out 2>/dev/null | wc -l)" "1"
is "and the first run's transcript still holds its own evidence" \
   "$(qa_count '^PASS the first run$' "$(ls "$TDIR"/twice/twice-pinned-*.out 2>/dev/null | head -1)")" "1"
is "there is exactly one transcript, not two sharing a name" \
   "$(ls "$TDIR"/twice/*.out 2>/dev/null | wc -l)" "1"

# ---- 6. THE JOIN THE NAMING CARRIES. rewind-scenario.sh's R18 sweeps the
# transcript for leaked URLs with the ERE below, and `/rewind/` is one of its
# alternatives. A transcript at transcripts/rewind/<file> would therefore make
# the file's OWN PATH a leak hit and turn a privacy check red on itself -- a
# join by name between a filename pattern in qa-lib.sh and an ERE in a
# scenario. So it is asserted by running R18's real predicate over a real
# transcript written under the real name.
#
# ONE assertion defends that join -- the `0` below -- and its counter-case. A
# mutation that interposes a per-scenario subdirectory reddens four checks here
# (measured: 229 passed, 4 failed), but three of the four are the `twice`
# collision case above losing its `ls .../twice/twice-pinned-*.out` glob, which
# says nothing about the join. Recorded because the opposite was written down:
# the count was read as four assertions defending it.
R18_LEAK='://|127\.0\.0\.1:8771|live\.m3u8|/rewind/'
rm -rf "$TDIR/r18"
scen rewind "$TDIR/r18" 'echo "PASS R1 back 10"' \
  'printf "%s\n" "$QA_TRANSCRIPT" >"'"$TMP"'/path18"' >/dev/null 2>&1
T18=$(cat "$TMP/path18" 2>/dev/null)
ck "a transcript was written under the name rewind" '[[ -n $T18 && -f $T18 ]]'
qa_leak_scan 'PASS|FAIL' "$R18_LEAK" "$T18" >/dev/null 2>&1
is "R18's own sweep reads it as CLEAN: the transcript's path is not a leak hit" "$?" "0"
# And the counter-case, so the assertion above is not passing for want of a
# sweep: the same ERE over the same file with one URL in it is a FAILURE.
printf 'PASS something http://user:secret@127.0.0.1:8771/a/live.m3u8\n' >>"$T18"
qa_leak_scan 'PASS|FAIL' "$R18_LEAK" "$T18" >/dev/null 2>&1
is "and the same sweep over the same transcript DOES catch a real URL" "$?" "1"

# ---- 7. nothing lands in the repository. The gate runs three scenarios in
# check-tree mode on every commit; a transcript under $ROOT would show up as
# untracked in the git status the next release depends on.
D=$( . "$HERE/qa-lib.sh"; qa_transcript_dir )
ck "the default transcript directory is absolute" '[[ $D == /* ]]'
ck "and is not inside the repository ($D)" '[[ $D != "$ROOT"/* ]]'
ck "it is under the harness scratch, which run.sh clean does not remove" \
   '[[ $D == */omarchy-iptv-harness/transcripts ]]'
is "OMARCHY_IPTV_HARNESS_DIR moves it, the way it moves every other scratch path" \
   "$(OMARCHY_IPTV_HARNESS_DIR=/run/user/0/elsewhere bash -c '. "$1/qa-lib.sh"; qa_transcript_dir' _ "$HERE")" \
   "/run/user/0/elsewhere/transcripts"

section "qa_transcript_sync: the sweep that read a file tee had not finished"

# MEASURED 2026-10-06, 30 runs per case. A line printed and then read back by
# a bash BUILTIN was absent 30 of 30 times: the transcript is written by a tee
# on the far side of a pipe and the shell does not wait for it. Read back
# through a `grep` -- where the fork is itself the delay -- it was present
# 12 of 12 idle and absent 6 of 30 with the cores oversubscribed twice over.
# rewind-scenario.sh's R18 sweeps its own transcript at the end of the run,
# which is exactly that shape: under load it swept a file short of its most
# recent lines, so a URL printed just before the sweep could go unseen by the
# check that exists to see it.
#
# The builtin-read case is the deterministic one, so it is what is driven
# here: WITHOUT the barrier the line is absent, WITH it the line is there.
rm -rf "$TDIR/sync"
scen sync "$TDIR/sync" \
  'printf "NO-BARRIER-MARKER\n"' \
  'l=""; read -r l <"$QA_TRANSCRIPT" 2>/dev/null; printf "%s" "$l" >"'"$TMP"'/nobarrier"' \
  'qa_transcript_sync 5; printf "%s" "$?" >"'"$TMP"'/syncst"' \
  'l=""; while read -r x; do l=$x; done <"$QA_TRANSCRIPT"; printf "%s" "$l" >"'"$TMP"'/withbarrier"' \
  >/dev/null 2>&1
is "without the barrier the just-printed line is NOT on disk yet" \
   "$(cat "$TMP/nobarrier" 2>/dev/null)" ""
is "qa_transcript_sync answers 0" "$(cat "$TMP/syncst" 2>/dev/null)" "0"
ck "and after it the transcript has caught up, marker and all ($(cat "$TMP/withbarrier" 2>/dev/null))" \
   '[[ $(cat "'"$TMP"'/withbarrier" 2>/dev/null) == *transcript-sync-* ]]'

# A sync with no transcript is VACUOUS, never 0. The whole library exists
# because "clean" was being reported over nothing at all.
( . "$HERE/qa-lib.sh"; qa_transcript_sync 1 ) >/dev/null 2>&1
is "a sync with no transcript started is vacuous (2), not a pass" "$?" "2"
: >"$TMP/never-written.out"
( . "$HERE/qa-lib.sh"; QA_TRANSCRIPT="$TMP/never-written.out"; qa_transcript_sync 1 ) >/dev/null 2>&1
is "a sync whose marker never lands gives up with 1, bounded (rule 3)" "$?" "1"
is "and says so rather than looping on" \
   "$( . "$HERE/qa-lib.sh"; QA_TRANSCRIPT="$TMP/never-written.out"; qa_transcript_sync 1 2>&1 >/dev/null | grep -c 'gave up')" "1"
# The marker itself must not be able to trip a leak sweep: it goes INTO the
# transcript every time, on a file R18 then sweeps.
MARKERS=$( . "$HERE/qa-lib.sh"; QA_TRANSCRIPT="$TMP/never-written.out"; qa_transcript_sync 1 2>/dev/null )
is "the sync marker carries nothing R18's sweep would match" \
   "$(printf '%s\n' "$MARKERS" | grep -cE "$R18_LEAK")" "0"

section "F-M3-1 (b): EVERY scenario writes a transcript, not just the one"

# This is the half the defect row is about. The pattern existed in exactly ONE
# scenario -- rewind-scenario.sh, as its own local habit -- and the run that
# lost its evidence was m3-scenario.sh. A rule that lives in one file is a
# rule the next file is written without, which is why this counts the
# POPULATION rather than asserting the shape of any one file.
SCEN_FILES=( "$ROOT"/scripts/dev-harness/*-scenario.sh )
is "there are scenarios to check (control: the glob resolved)" \
   "$(( ${#SCEN_FILES[@]} > 0 ? 1 : 0 ))" "1"
missing=""
late=""
unsourced=""
for f in "${SCEN_FILES[@]}"; do
  n=$(qa_count '^ *qa_transcript_start [A-Za-z0-9._-]+ \|\| exit 2$' "$f")
  [[ $n == 1 ]] || missing="$missing ${f##*/}($n)"
  # A call is not a call unless the definition is reachable from it. Three of
  # these scenarios did not source the library at all, and `qa_transcript_start
  # m3 || exit 2` in one of them is `command not found` followed by `exit 2`:
  # the scenario refuses to run, and it refuses with a message about a missing
  # command rather than about a missing transcript. Caught here while writing
  # this, which is the whole argument for counting the population.
  src=$(grep -nE '^ *\. +"\$ROOT/scripts/qa-lib\.sh"' "$f" | head -1 | cut -d: -f1)
  call=$(grep -nE '^ *qa_transcript_start ' "$f" | head -1 | cut -d: -f1)
  [[ -n $src && -n $call && $src -lt $call ]] || unsourced="$unsourced ${f##*/}"
  # In a scenario with a check-tree mode the call must sit BELOW the `live|""`
  # label: scripts/check.sh runs the check-tree halves on every commit, and a
  # gate step may neither print a path nobody asked for nor leave a file
  # behind. Scenarios with no such mode have no label and are not in scope.
  lbl=$(grep -nE '^ *live\|"" *\)' "$f" | head -1 | cut -d: -f1)
  if [[ -n $lbl ]]; then
    call=$(grep -nE '^ *qa_transcript_start ' "$f" | head -1 | cut -d: -f1)
    [[ -n $call && $call -gt $lbl ]] || late="$late ${f##*/}"
  fi
done
is "every scenario opens a transcript, exactly once, and exits if it cannot" \
   "${missing:-none}" "none"
is "and sources qa-lib.sh ABOVE the call, so the call resolves to a function" \
   "${unsourced:-none}" "none"
is "and in a check-tree scenario the call sits on the live arm only" \
   "${late:-none}" "none"
# The three the gate runs, named, because those are the ones where a stray
# transcript would land on every commit.
for g in chno-entry pip id-rotate; do
  lbl=$(grep -nE '^ *live\|"" *\)' "$ROOT/scripts/dev-harness/$g-scenario.sh" | head -1 | cut -d: -f1)
  ck "$g-scenario.sh (run by check.sh in check-tree mode) has a live arm to gate on" '[[ -n $lbl ]]'
done
# And the one that lost its evidence, by name, so this cannot be refactored
# into a rule that happens to exclude it again.
is "m3-scenario.sh, the run F-M3-1 happened to, writes one" \
   "$(qa_count '^qa_transcript_start m3 \|\| exit 2$' "$ROOT/scripts/dev-harness/m3-scenario.sh")" "1"
# rewind-scenario.sh's R18 must sweep the SHARED transcript now, not the
# $WORK/run.out its own cleanup() deletes.
RW="$ROOT/scripts/dev-harness/rewind-scenario.sh"
is "R18 sweeps the shared transcript" "$(qa_count 'qa_leak_scan .PASS\|FAIL. .*"\$QA_TRANSCRIPT"' "$RW")" "1"
is "and the run.out it used to sweep, which cleanup deletes, is gone" \
   "$(qa_count 'RUNOUT' "$RW")" "0"
is "R18 syncs before it sweeps" "$(qa_count '^if qa_transcript_sync ' "$RW")" "1"

# ============================================================== the floor

# ================================ the focus guard's decision table (F-M3-1 a)

section "run.sh key/type: the focus guard, decided from a stubbed reply"

# The first review of the guard found that NOTHING in the gate could go red for
# any of it: the lane's red proofs were real but lived in a rig that left with
# the lane, so the next author to delete the `open` check or swap `activeFocus`
# for `focus` would get a green gate. This section is that gap closed.
#
# What it exercises is run.sh's own DECISION from a reply, not whether
# focusSnapshot measures the reply correctly -- `qs` is stubbed, so the
# transport is not under test here. The live half (a real Quickshell answering
# focusState) is in docs/QA-RESULTS.md with the day's measurements; it cannot
# run in the gate, which holds no display.
#
# run.sh derives its ROOT from its own path, so the REAL file is executed and
# only the two programs it shells out to are stubbed on PATH. Nothing here can
# reach the live install or a harness the operator has running: the scratch
# directory is this test's $TMP.
FG=$TMP/fg; mkdir -p "$FG/bin" "$FG/h/root"; : >"$FG/h/root/shell.qml"
cat >"$FG/bin/wtype" <<'FG_WTYPE'
#!/bin/bash
echo "$@" >>"$WTYPE_LOG"
FG_WTYPE
chmod +x "$FG/bin/wtype"

# $1 = what the stub qs writes to stdout, $2 = a line for stderr ("" for none),
# $3 = the stub's exit code. Writes the reply, then runs the verb. Every call
# the stub receives is logged, so the ROUTING (which config root was asked) is
# observable and not just the verdict.
fg_stub() {
  { printf '#!/bin/bash\n'
    printf 'printf "%%s\\n" "$*" >>%q\n' "$FG/qs.argv"
    [[ -n $2 ]] && printf 'echo %q >&2\n' "$2"
    printf 'cat <<%s\n%s\nSTUB_EOF\n' "'STUB_EOF'" "$1"
    printf 'exit %s\n' "$3"
  } >"$FG/bin/qs"
  chmod +x "$FG/bin/qs"
}
# Runs `run.sh <verb...>` against the stub and echoes "<exit> <wtype-calls>".
# fg_run starts from an UNPRIMED shell (F-HARNESS-1's per-shell state);
# fg_run_keep leaves whatever the previous call left, which is how the primer's
# bookkeeping across two invocations is observed.
fg_run_keep() {
  : >"$FG/wtype.log"
  : >"$FG/qs.argv"
  WTYPE_LOG=$FG/wtype.log PATH="$FG/bin:$PATH" OMARCHY_IPTV_HARNESS_DIR=$FG/h \
    timeout 20 "$ROOT/scripts/dev-harness/run.sh" "$@" >"$FG/out" 2>&1
  printf '%s %s\n' "$?" "$(wc -l <"$FG/wtype.log")"
}
fg_run() {
  rm -f "$FG"/h/primed*
  fg_run_keep "$@"
}
FG_OPEN='{"ok":true,"error":"","open":true,"keyboard":true,"role":"catcher","item":"PanelKeyCatcher","blocked":false,"window":"layer","scanned":326,"exhausted":false}'
# The two integers in that reply are the lead's live reading of the real guide
# on 2026-10-06 (220 visits closed, 326 open), not invented ones -- but nothing
# in this section MEASURES them: `qs` is a stub, so every field here is a value
# this file chose. Read them as the inputs to a decision, never as evidence
# about the guide's tree.

# A focused guide passes, and the key reaches wtype. Two calls, not one: the
# F-HARNESS-1 shift primer is the first, the caller's key the second.
fg_stub "$FG_OPEN" "" 0
is "a focused guide passes and the key reaches wtype" "$(fg_run key j)" "0 2"
is "and the argv is passed through untouched" "$(tail -1 "$FG/wtype.log")" "j"

# THE P1 REGRESSION. The guard used to read stdout and stderr together, so one
# diagnostic line from qs made every key refuse -- invisibly, because every
# call site drops the status. This is the check that goes red if the streams are
# ever merged again.
fg_stub "$FG_OPEN" "QSDIAG: a diagnostic on stderr" 0
is "a diagnostic on qs's STDERR does not turn a focused guide into a refusal" "$(fg_run key j)" "0 2"

fg_stub "${FG_OPEN/\"open\":true/\"open\":false}" "" 0
is "a CLOSED guide refuses and types nothing" "$(fg_run key j)" "3 0"
ck "and the refusal says which of the two it was" 'grep -q "the guide is CLOSED" "$FG/out"'

fg_stub "${FG_OPEN/\"keyboard\":true/\"keyboard\":false}" "" 0
is "an open guide whose keyboard is elsewhere refuses" "$(fg_run key j)" "3 0"
ck "and says so, rather than naming the closed case" 'grep -q "ANOTHER SURFACE holds the keyboard" "$FG/out"'

# A focused Sources field is still the guide: role is reported, never refused on.
fg_stub "${FG_OPEN/\"role\":\"catcher\"/\"role\":\"other\"}" "" 0
is "a focused form field is still the guide and passes" "$(fg_run key j)" "0 2"

fg_stub '{"ok":false,"error":"no_guide","open":false,"keyboard":false}' "" 0
is "no loaded guide refuses" "$(fg_run key j)" "3 0"

fg_stub 'not json at all' "" 0
is "an unreadable reply fails CLOSED" "$(fg_run key j)" "3 0"

fg_stub '' "QSFAIL: no running instances" 255
is "a transport failure refuses" "$(fg_run key j)" "3 0"
ck "and the diagnostic is still shown, not swallowed" 'grep -q "QSFAIL: no running instances" "$FG/out"'

# A walk that GAVE UP is not a walk that found nothing. keyboard=false with
# exhausted=true must not be rendered as the confident "another surface has
# it": the bound was hit, so the honest answer is "I cannot tell". Both halves
# of the message are asserted, because the two cases differ only in the words.
fg_stub "${FG_OPEN/\"keyboard\":true,\"role\":\"catcher\",\"item\":\"PanelKeyCatcher\",\"blocked\":false,\"window\":\"layer\",\"scanned\":326,\"exhausted\":false/\"keyboard\":false,\"role\":\"none\",\"item\":\"\",\"blocked\":null,\"window\":\"layer\",\"scanned\":326,\"exhausted\":true}" "" 0
is "a walk that EXHAUSTED its bound refuses" "$(fg_run key j)" "3 0"
ck "and says it cannot tell, not that another surface has the keyboard" \
   'grep -q "the focus walk gave up" "$FG/out" && ! grep -q "ANOTHER SURFACE" "$FG/out"'

# The escape hatch skips the FOCUS check only, and it is positional: wtype's
# own `--` means the rest is text, so our flag may only lead.
fg_stub "${FG_OPEN/\"open\":true/\"open\":false}" "" 0
is "a --to-compositor AFTER -- is text to be typed, not a flag" "$(fg_run key -- --to-compositor)" "3 0"

# ...and the hatch skips the F-HARNESS-1 PRIMER too, which is the point rather
# than an optimisation. The hatch aims a chord at whatever holds the keyboard,
# which is by definition not the guide's fresh surface; the primer used to fire
# into it anyway AND record the shell as primed, so the next legitimate key into
# the guide skipped priming -- F-HARNESS-1's compensation spent without ever
# having reached the surface it compensates for. ONE wtype call, not two, and
# the next real key still pays for the primer. The three run in sequence and
# the middle one reads the state the first left.
is "--to-compositor sends although the guide is closed, and sends ONLY the chord" \
   "$(fg_run key --to-compositor -k Escape)" "0 1"
ck "the hatch leaves the shell UNPRIMED, so the priming is not burnt" '[[ ! -f $FG/h/primed ]]'
fg_stub "$FG_OPEN" "" 0
is "so the next real key into the guide still primes (primer + key)" "$(fg_run_keep key j)" "0 2"

# WHICH INSTANCE the guard asks about. Only the environment variable routes
# these verbs; `--instance` is a `start` option and is parsed nowhere else.
# The comment above require_guide_focus used to read as if the flag worked
# here, which is the claim these three drive.
mkdir -p "$FG/h/root2"; : >"$FG/h/root2/shell.qml"
fg_stub "$FG_OPEN" "" 0
is "OMARCHY_IPTV_HARNESS_INSTANCE routes the guard and the key goes through" \
   "$(OMARCHY_IPTV_HARNESS_INSTANCE=2 fg_run key j)" "0 2"
is "and it is the SECOND config root that was asked about focus" \
   "$(grep -c -- "-p $FG/h/root2 call harness focusState" "$FG/qs.argv")" "1"
is "--instance before the verb is a usage error, not a routed guard" "$(fg_run --instance 2 key j)" "2 0"
ck "and it says which word it could not place" 'grep -q "unknown option: key" "$FG/out"'
is "--instance AFTER key is wtype's text, like every other word there" \
   "$(fg_run key --instance 2 j; tail -1 "$FG/wtype.log")" "0 2
--instance 2 j"

# `type` refuses UP FRONT, so a steal cannot cost two sends into a foreign
# surface and a message blaming the first-keystroke race. The stub is set HERE
# rather than inherited from the case above: every case in this table states
# its own reply, so inserting one cannot silently change another's input.
fg_stub "${FG_OPEN/\"open\":true/\"open\":false}" "" 0
is "type refuses before its retry loop, so nothing is sent twice" "$(fg_run type sky)" "3 0"

# And a steal AFTER the front check ends on the GUARD's verdict. The inner
# `"$0" key` refusal used to be dropped on the loop body, so `type` fell
# through to the two-attempt message that run.sh's own comment calls the wrong
# diagnosis, and exited 1 -- so a scenario grading exit 3 as "refused" could
# not see a focus refusal at all. The stub answers focused for the FRONT check
# and stolen for every call after it.
{ printf '#!/bin/bash\n'
  printf 'printf "%%s\\n" "$*" >>%q\n' "$FG/qs.argv"
  printf 'n=$(cat %q 2>/dev/null || echo 0); n=$((n + 1)); printf "%%s" "$n" >%q\n' "$FG/n" "$FG/n"
  printf 'if (( n > 1 )); then cat <<%s\n%s\nSTUB_EOF\nelse cat <<%s\n%s\nSTUB_EOF\nfi\n' \
    "'STUB_EOF'" "${FG_OPEN/\"keyboard\":true/\"keyboard\":false}" "'STUB_EOF'" "$FG_OPEN"
} >"$FG/bin/qs"
chmod +x "$FG/bin/qs"
rm -f "$FG/n"
is "a steal after the front check refuses with 3 and types nothing" "$(fg_run type sky)" "3 0"
ck "and the diagnosis is the guard's, not the two-attempt message" \
   'grep -q "type REFUSED" "$FG/out" && ! grep -q "did not arrive after two attempts" "$FG/out"'

# ============ shell.qml focusWalk: the two bounds, driven for real (F-M3-1 a)

section "shell.qml focusWalk: a bound that gives up says so"

# The guard's verdict above is decided from a REPLY. This decides the reply.
# focusWalk is plain JavaScript inside a QML object, so it cannot be reached
# from a bash predicate and it cannot be reached from the qml spec either (that
# runs the plugin's Model.js, not the harness shell). What can be done without a
# display is to take the function's own TEXT out of shell.qml and run it -- the
# shipping characters, not a copy of its decisions -- over trees built here.
# Both bounds are read out of the file the same way, so a bound that moves moves
# the test with it; a bound that is RENAMED fails the extraction loudly rather
# than passing vacuously.
#
# What this catches: `exhausted` is what tells run.sh "I gave up" apart from
# "nothing is focused", and run.sh renders the second as the confident "ANOTHER
# SURFACE holds the keyboard". The depth bound used to return without setting it
# while the comment above it promised that could not happen.
cat >"$TMP/focuswalk.js" <<'FW_JS'
var fs = require('fs');
var src = fs.readFileSync(process.argv[2], 'utf8');
var start = src.indexOf('\n  function focusWalk(');
if (start < 0) { console.log('EXTRACT-FAIL function focusWalk'); process.exit(0); }
var end = src.indexOf('\n  }\n', start);
if (end < 0) { console.log('EXTRACT-FAIL focusWalk body'); process.exit(0); }
var body = src.slice(start + 1, end + 4);
// The bound as a named property, or -- for a tree that still spells it inline --
// the literal in the condition, so this runs against before-code as well.
function bound(name, inlineRe) {
  var m = src.match(new RegExp('readonly\\s+property\\s+int\\s+' + name + ':\\s*(\\d+)'));
  if (m) return parseInt(m[1], 10);
  m = body.match(inlineRe);
  if (m) return parseInt(m[1], 10);
  console.log('EXTRACT-FAIL bound ' + name);
  process.exit(0);
}
var harness = { focusScanBudget: bound('focusScanBudget', /scanned\s*>=\s*(\d+)/),
                focusDepthCap: bound('focusDepthCap', /depth\s*>\s*(\d+)/) };
harness.focusWalk = eval('(' + body.trim() + ')');
function chain(n) {   // n nested Items, only the deepest with activeFocus
  var node = { activeFocus: true, children: [] };
  for (var i = 1; i < n; i++) node = { activeFocus: false, children: [node] };
  return node;
}
function walk(root) {
  return harness.focusWalk(root, 0, { leaf: null, depth: -1, scanned: 0, exhausted: false });
}
var s = walk(chain(8));
console.log('SHALLOW leaf=' + (s.leaf !== null) + ' depth=' + s.depth + ' exhausted=' + s.exhausted);
var d = walk(chain(harness.focusDepthCap + 5));
console.log('DEEP leaf=' + (d.leaf !== null) + ' exhausted=' + d.exhausted);
var n = walk({ activeFocus: false, children: [null, null], item: null, contentItem: null });
console.log('NULLS leaf=' + (n.leaf !== null) + ' exhausted=' + n.exhausted);
var wide = { activeFocus: false, children: [] };
for (var i = 0; i < harness.focusScanBudget + 10; i++) wide.children.push({ activeFocus: false, children: [] });
var b = walk(wide);
console.log('BUDGET exhausted=' + b.exhausted + ' scanned=' + b.scanned);
FW_JS
FW=$(node "$TMP/focuswalk.js" "$ROOT/scripts/dev-harness/shell.qml" 2>&1)
fwline() { printf '%s\n' "$FW" | grep "^$1 " | head -1; }
is "the real guide path (8 levels) finds the leaf and did NOT give up" \
   "$(fwline SHALLOW)" "SHALLOW leaf=true depth=7 exhausted=false"
is "a leaf past the DEPTH cap reports exhausted, so 'I gave up' is not 'nothing is focused'" \
   "$(fwline DEEP)" "DEEP leaf=false exhausted=true"
is "a branch that simply ENDS is not giving up (a null child must not set exhausted)" \
   "$(fwline NULLS)" "NULLS leaf=false exhausted=false"
is "and the NODE budget reports it too, at the budget" \
   "$(fwline BUDGET)" "BUDGET exhausted=true scanned=$(grep -oE 'focusScanBudget: [0-9]+' "$ROOT/scripts/dev-harness/shell.qml" | grep -oE '[0-9]+')"

# =========== qa_transcript_start: the directory mode the REFUSAL actually sees

section "qa_transcript_start: the directory-mode mask, group and other apart"

# The refusal reads `(( 0$dmode & 077 ))`, and qa-lib.sh's comment and the
# harness README both state the property as "refuses a directory group OR other
# can enter". Only /tmp was driven, which is 1777 and trips every candidate
# mask, so two thirds of that sentence had nothing behind it: weakening the mask
# to `& 007` (the group half deleted) or `& 002` (only world-WRITABLE refused,
# so a 0750 directory belonging to someone else is accepted) left this file at
# 213 passed, 0 failed. Rule 14's shape inside a privacy check. Found by the
# first review of this function.
#
# The case the mask is for is a directory we cannot TIGHTEN -- our own is
# chmod 0700'd two lines above the check, which is why /tmp was the only case
# anyone could reach. So `chmod` is shadowed by a function that fails, which is
# exactly what the real chmod does on a directory we do not own, and stricter
# than it in every other way (rule 10). The mode is then genuinely read by
# `stat` and genuinely judged by the shipping condition.
cat >"$TMP/mode-probe.sh" <<'MODE_PROBE'
#!/bin/bash
set -uo pipefail
. "$1"
chmod() { return 1; }   # a directory this run cannot tighten
qa_transcript_start probe "$2" >/dev/null 2>&1
printf '%s %s\n' "$?" "$(ls -A "$2" | wc -l)"
MODE_PROBE
mode_probe() {   # mode_probe <octal-mode> -> "<status> <files-in-dir>"
  local d=$TMP/dm$1
  rm -rf "$d"; mkdir -p "$d"; command chmod "0$1" "$d"
  bash "$TMP/mode-probe.sh" "$HERE/qa-lib.sh" "$d"
}
is "a 0750 directory we cannot tighten is refused, and nothing is written there" \
   "$(mode_probe 750)" "2 0"
is "a 0705 directory we cannot tighten is refused too (the OTHER half)" \
   "$(mode_probe 705)" "2 0"
# The control, so the two refusals are not passing for want of a working
# function: 0700 goes through WITH the chmod still dead, which also isolates the
# umask half of the deliberately redundant 0600 (the chmod cannot be what made
# it private here).
is "and a 0700 directory is accepted with the same chmod dead" "$(mode_probe 700)" "0 1"
is "the transcript it wrote is 0600 from the umask alone" \
   "$(stat -c '%a' "$(ls "$TMP"/dm700/* 2>/dev/null | head -1)" 2>/dev/null)" "600"

# ============ the transcript opens after the REFUSALS, observed at the sink

section "scenarios: a refusal leaves no transcript"

# qa-lib.sh item 3, the harness README and two scenarios' own comments all say
# the call sits after the refusals that exit before anything starts. Four of
# rewind-scenario.sh's exited BELOW it (the two-levers conflict, a --tree that
# cannot be entered, a --tree that is not a plugin tree, a --baseline git cannot
# export) and one of player-scenario.sh's did, so a mistyped lever printed a
# path and left an almost-empty file behind. Found by the first review.
#
# Observed at the sink: the real scenario is run with a bad lever against a
# throwaway harness directory, and the transcript directory must not exist
# afterwards. Robust to machine state on purpose -- if the preflight above
# refuses first (a locked screen, a busy port) that is also a refusal and must
# also leave nothing. The ORDER check below cannot be made vacuous that way, so
# the two together are not.
# `ss` is stubbed to report no listeners, and that is a SAFETY measure, not a
# convenience. rewind-scenario.sh installs its EXIT trap above these refusals,
# and its cleanup reads the pid holding port 8771 out of `ss -ltnp` and KILLS
# it -- so a gate step that drove the real `ss` would kill a fixture server a
# live rewind pass was using, on every commit. The stub also makes the preflight
# deterministic: it never refuses for "port in use" and so always reaches the
# refusals under test. Nothing here depends on what `ss` can see. The harness
# directory is a throwaway under $TMP, so every other path cleanup touches
# (`run.sh reap`'s patterns, $FIX, last-start.env) resolves inside it.
tr_refuse() {   # tr_refuse <scenario> <args...> -> "<status> <transcripts>"
  local s=$1; shift
  local d=$TMP/trr$$-$RANDOM
  mkdir -p "$TMP/safebin"
  { printf '#!/bin/bash\n'
    printf 'printf "%%s\\n" "$*" >>%q\n' "$TMP/ss.argv"
    printf 'exit 0\n'
  } >"$TMP/safebin/ss"
  chmod +x "$TMP/safebin/ss"
  : >"$TMP/ss.argv"
  PATH="$TMP/safebin:$PATH" OMARCHY_IPTV_HARNESS_DIR=$d \
    timeout 120 "$ROOT/scripts/dev-harness/$s" "$@" >/dev/null 2>&1
  printf '%s %s\n' "$?" "$(ls -1 "$d/transcripts" 2>/dev/null | wc -l)"
}
is "rewind-scenario.sh --baseline X --tree Y refuses and writes no transcript" \
   "$(tr_refuse rewind-scenario.sh --baseline HEAD --tree /tmp)" "2 0"
is "rewind-scenario.sh --tree <not a plugin tree> likewise" \
   "$(tr_refuse rewind-scenario.sh --tree /etc)" "2 0"
is "player-scenario.sh --baseline <no such ref> likewise" \
   "$(tr_refuse player-scenario.sh --baseline no-such-ref-for-a-test)" "2 0"

# A refusal must not reap somebody else's port either, and that one bites
# hardest on the refusal that exists to protect it. rewind-scenario.sh installs
# its EXIT trap above these refusals and its cleanup reads the pid holding 8771
# out of `ss -ltnp` and kills it, so a refusal that started NOTHING killed
# whoever was there -- including on "port 8771 is already in use". Measured with
# a decoy listener: the decoy was gone after `--tree /etc`; with the ownership
# guard it survives, and survives the port-in-use refusal too.
#
# Observed here without binding anything: the kill is reachable only through
# `ss -ltnp`, and the stub above logs every `ss` call, so a run that refuses
# must make none. (`kill` is a bash builtin, so it cannot be stubbed on PATH --
# the call that precedes it can.)
tr_refuse rewind-scenario.sh --tree /etc >/dev/null
is "a refusing rewind run never asks which pid holds the port, so it kills nobody" \
   "$(qa_count '[-]ltnp' "$TMP/ss.argv")" "0"
ck "control: the run really did reach cleanup (it asked about the port at all)" \
   '(( $(qa_count "[-]ltn" "$TMP/ss.argv") >= 1 ))'

# And the order in the file, which no machine state can make vacuous.
tr_line() { grep -n "$2" "$ROOT/scripts/dev-harness/$1" | head -1 | cut -d: -f1; }
tr_last() { grep -n "$2" "$ROOT/scripts/dev-harness/$1" | tail -1 | cut -d: -f1; }
ck "rewind's transcript call sits BELOW every one of its tree refusals" \
   '(( $(tr_line rewind-scenario.sh "^qa_transcript_start rewind") > $(tr_last rewind-scenario.sh "could not export \$BASELINE") ))'
ck "and below the two-levers refusal" \
   '(( $(tr_line rewind-scenario.sh "^qa_transcript_start rewind") > $(tr_line rewind-scenario.sh "are the same lever") ))'
ck "player's sits below its export refusal" \
   '(( $(tr_line player-scenario.sh "^qa_transcript_start player") > $(tr_line player-scenario.sh "could not export \$BASELINE") ))'

# ======== every background start redirects both streams (the README's claim)

section "scenarios: a background start does not keep tee alive"

# README.md said "Every scenario here already redirects its harness, its fixture
# servers and its sweepers". Four starts did not, and two of them were the
# sweepers the sentence names: argv-scenario.sh's and rewind-scenario.sh's
# redirected neither stream, rewind's ffmpeg redirected stderr only and
# sources-scenario.sh's silent listener stdout only. A background process that
# does not redirect inherits the transcript pipe and keeps `tee` alive past the
# run. Counted over the POPULATION rather than asserted in prose, so the next
# scenario added here cannot be the one that forgets.
bg_unredirected=0
bg_total=0
while IFS= read -r hit; do
  bg_total=$((bg_total + 1))
  line=${hit#*:}
  # stderr first: `2>`, `2>>` or `&>`. Then STRIP those spellings and ask
  # whether any `>` is left -- that is stdout. Written this way because the
  # obvious regex for "a > not preceded by 2" matches the SECOND > of `2>>`,
  # which read rewind's ffmpeg start (stderr only) as fully redirected and left
  # one of the four findings invisible. Measured both ways against the
  # pre-change tree: 3 flagged with the regex, 4 with this.
  has_out=0; has_err=0
  [[ $line == *"2>"* || $line == *"&>"* ]] && has_err=1
  stripped=${line//2>>/ }; stripped=${stripped//2>/ }; stripped=${stripped//&>/ }
  [[ $stripped == *">"* ]] && has_out=1
  if (( ! has_out || ! has_err )); then
    bg_unredirected=$((bg_unredirected + 1))
    printf '     unredirected background start: %s\n' "$hit"
  fi
done < <(grep -nE '[^&|]&[[:space:]]*$' "$ROOT"/scripts/dev-harness/*-scenario.sh)
ck "there are background starts to judge at all (control: $bg_total found)" '(( bg_total >= 8 ))'
is "every background start in every scenario redirects BOTH streams" "$bg_unredirected" "0"

# ============ qa_min_skipped: a duty-cycle floor that does not relax

section "qa_min_skipped: a control that keeps its strength when the window grows"

# rewind-scenario.sh's R16 asserted "at least one of the TICKS health ticks
# landed on a running seek" while TICKS went 3 -> 6 with the busy window
# (F-RWD-25). That is 1-in-3 becoming 1-in-6: the control at half strength,
# under a note saying the bound "follows on its own" -- true as arithmetic,
# false as a statement about strength. Found by the first review of the
# transcript change. The floor is proportional now, and it lives here rather
# than in the scenario so its strength is observed without a display.
is "three ticks demand one skipped, which is what R16 shipped with" "$(qa_min_skipped 3)" "1"
is "six demand two, so the 62 s window is as strong as the 32 s one was" "$(qa_min_skipped 6)" "2"
is "nine demand three" "$(qa_min_skipped 9)" "3"
is "and one still demands one: a floor of zero would be no control at all" "$(qa_min_skipped 1)" "1"
is "a non-integer is refused rather than silently floored" "$(qa_min_skipped NOFIELD)" "$QA_NO_DELTA"
st "and says so with 2" 2 qa_min_skipped NOFIELD
# The JOIN, and it is a name join rather than a call -- said plainly, because
# rule 14 does not let a grep stand in for an observation. The six assertions
# above observe the shipping arithmetic for real; what no gate step can observe
# is R16 USING it, since R16 needs a player, a stream and a display. A live
# rewind pass is the only thing that observes that, and until one runs the two
# lines below are bookkeeping that catches a revert, not evidence of strength.
is "R16's floor comes from qa_min_skipped, not a second copy of the arithmetic" \
   "$(qa_count 'SKIP_MIN=\$\(qa_min_skipped' "$ROOT/scripts/dev-harness/rewind-scenario.sh")" "1"
is "and the constant-1 bound it replaced is not still there beside it" \
   "$(qa_count 'ge "\$\(\(TICKS - 1\)\)"' "$ROOT/scripts/dev-harness/rewind-scenario.sh")" "0"

# CLAUDE.md rule 11, applied to this file: if a section stops executing, the
# summary must say so rather than printing a smaller number nobody reads.
# Raise this when you add a check; never lower it to make a run green.
# 165 -> 213 on 2026-10-06: F-M3-1 half (b), the 48 assertions for
# qa_transcript_start / qa_transcript_sync and for the population of scenarios
# that call them. scripts/check.sh reports this step's count and sets no floor
# of its own on it, so this number is the only floor the transcript
# assertions have.
# 213 -> 216 the same day, at integration: the mode control now runs under an
# explicit umask instead of the caller's, and the property that actually holds
# -- 0600 because we create the file rather than letting tee create it -- is
# asserted at three umasks including the two that used to redden this step.
# 233 -> 268 the same day, repairing the closing round's P3s: the focus guard's
# exhausted verdict, which instance the guard asks about, the primer the
# --to-compositor hatch used to burn and the mid-type steal that ended on the
# wrong diagnosis; shell.qml's focusWalk bounds, driven by extracting the real
# function; the directory-mode mask with group and other driven apart; the
# refusals that must leave no transcript (and the port-holder a refusing run
# must not kill, found while verifying them); the background starts that must
# redirect both streams; and qa_min_skipped.
EXPECTED=270
section "summary"
printf '%d passed, %d failed\n' "$pass" "$fail"
if (( pass + fail != EXPECTED )); then
  printf 'FAIL qa-lib-test ran %d checks, expected %d (a section stopped executing)\n' \
    "$((pass + fail))" "$EXPECTED"
  fail=$((fail + 1))
fi
(( fail == 0 ))
