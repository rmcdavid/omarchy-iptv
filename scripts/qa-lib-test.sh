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
# Pure bash plus python3/jq. No harness, no display, no network, under a
# second. Run by scripts/check.sh.
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

# ============================================================== the floor

# CLAUDE.md rule 11, applied to this file: if a section stops executing, the
# summary must say so rather than printing a smaller number nobody reads.
# Raise this when you add a check; never lower it to make a run green.
EXPECTED=148
section "summary"
printf '%d passed, %d failed\n' "$pass" "$fail"
if (( pass + fail != EXPECTED )); then
  printf 'FAIL qa-lib-test ran %d checks, expected %d (a section stopped executing)\n' \
    "$((pass + fail))" "$EXPECTED"
  fail=$((fail + 1))
fi
(( fail == 0 ))
