#!/bin/bash
# scripts/dev-harness/config-mode-scenario.sh -- D-SINK-18: the container the
# plugin puts a provider URL into must be private BEFORE the URL goes in.
#
# THE FINDING. `Service.qml`'s persistActive writes playlistUrl and epgUrl into
# the host bar entry, and the host persists that to ~/.config/omarchy/shell.json
# -- a file the plugin does not own. The packaged default is 0644 and the host's
# atomic FileView writer preserves whatever mode the file already has. Both
# MEASURED by the lead on 2026-10-09 with a purpose-built FileView probe and
# recorded in docs/QA-RESULTS.md under "Fourth maintainer finding"; this lane
# holds no display, could not retake them, and cites them rather than claiming
# them. Raised by HANCORE-linux on omacom/omarchy-plugin-marketplace#10735
# against the shipped 0.13.2, his fourth finding in four days.
#
# WHAT THIS SCENARIO CANNOT OBSERVE, SAID FIRST. The harness's own fake host
# models the config IN MEMORY: scripts/dev-harness/shell.qml:655,
#   function persistShellConfig(nextConfig) {
#     fakeHost.shellConfig = JSON.parse(JSON.stringify(nextConfig))
#   }
# -- one deep copy, no FileView, no file. That is deliberate (the fake
# reproduces the host's ORDERING so the one-write-behind echo cannot be masked
# again, D-LIVE-20/21), and it means NO scenario in this repository can watch
# the host write a URL into shell.json. So this scenario does not pretend to.
# It observes the half that is real and observable: the helper verb, driven as
# a subprocess against a scratch XDG_CONFIG_HOME, with the file's mode read by
# stat. The other half -- that Service.qml GATES persistActive on the verb's
# answer -- is a QML decision, and the note at the foot of this file says what
# a live half would have to observe and why it is not written here yet.
#
# HOW MUCH OF THE ORDERING THIS REACHES, AND HOW MUCH IT DOES NOT. "Tighten,
# then write" and "write, then tighten" reach the same end state on a container
# that CAN be tightened, so an end-state check over the happy path passes both,
# and sampling the file for the transient is a race (F-HARNESS-15). The
# counterfactual is the discriminator: a container that can NEVER be made
# private. Correct code refuses it and the credential is never written.
#
# But the refusal this scenario can observe is the verb's, and the ORDERING
# proper is not the verb's to get wrong -- the helper never writes a URL, so
# "write, then tighten" is a decision in Service.qml about when to call this
# and whether to honour the answer. R1 therefore observes the ENABLING half:
# that the verb does not answer yes over a container it could not make
# private, which is what a caller would rely on. The half R1 does NOT see is
# persistActive running first, or running anyway. That is the live half's, and
# the foot of this file says so rather than letting R1 imply a coverage it
# does not have. The mutation table found that overclaim: the mutation first
# written to prove R1 saw the ordering turned out to be unreachable code,
# because lstat does not resolve a symlink and the reference implementation
# refuses at ISREG before any chmod runs. It reddened nothing, and the claim
# in this paragraph is what changed as a result.
#
#   V1  the helper HAS the verb                      (a name join made a call)
#   M1  a 0644 config is private afterwards, rc 0
#   M2  a 0640 config -- group only -- is private afterwards
#   M3  a 0604 config -- other only -- is private afterwards
#   M4  a 0600 config is left UNTOUCHED: bytes, mode, mtime AND ctime
#   R1  a container that can never be made private is REFUSED       <- ordering
#   R2  rc 0 is never answered over a path that is not a private regular file
#   R3  a path offered as an ARGUMENT is not the path it touches
#   S1  nothing it printed carries the synthetic credential   (rule 5)
#   C1  the developer's own ~/.config/omarchy/shell.json is byte- and
#       mode-identical to the stamp taken before the first check ran
#
# READ V1 BEFORE READING ANY OTHER LINE OF A RED RUN. On a tree where the verb
# does not exist the helper answers status 2 to everything, and a status 2 is
# indistinguishable from a refusal: R1, R2, R3 and S1 all PASS, vacuously,
# because nothing ran. Against dev at 982b693 this scenario reads "6 passed, 5
# failed" and the five are V1 and M1-M4. Those four passes are not evidence of
# anything and V1's failure is what says so. The mutation table below is what
# proves R1, R2, R3 and S1 can go red once there IS a verb -- without it they
# would be exactly the check-that-cannot-fail this repository keeps finding.
#
# M2 and M3 exist apart on purpose. A 0640 shell.json is exactly as exposed to
# everyone in the owning group as a 0644 one is to the world, and the
# qa_transcript_start lesson is that a privacy mask graded against one mode
# (1777 /tmp, which trips every candidate mask) is a mask never under test.
#
# WHY M4 WATCHES ctime. Measured in this worktree on 2026-10-09: `chmod 0600`
# on a file that is ALREADY 0600 leaves the bytes and mtime byte-identical and
# moves ctime every single time -- three chmods, one mtime, three ctimes. So
# the obvious pair to watch, content and mtime, cannot go red for a needless
# chmod of an already-private file. ctime is the only clock that sees it, and
# that is rule 14 inside this scenario rather than quoted at it.
#
# GRADING IT (CLAUDE.md rule 11). The verb belongs to another lane and did not
# exist when this was written, so there is no "before" to run against and the
# rule says to mutate instead. spikes/config-mode/stub-config-verb.py is a
# reference implementation of the lead's ruling with one decision switchable
# off at a time; --helper points this scenario at it. The table, every entry
# measured by running it:
#
#   STUB_MUTATION         reddens   because
#   none                  nothing   the reference answer
#   no-chmod              M1 M2 M3  reports success, changes nothing
#   world-only            M2        mask 007: a 0640 file reads as private
#   group-only            M3        mask 070: a 0604 file reads as private
#   unconditional-chmod   M4        chmods an already-private file (ctime)
#   accept-unshieldable   R1 R2     answers 0 over a container it did not shield
#   any-path              R3        honours the argument and chmods the decoy
#   leak-url              S1        prints the URL it was handed
#
# The stub is NOT a shim and takes no part in a real run: with no --helper this
# scenario drives bin/omarchy-iptv and nothing else. The stub grades the
# questions; it never answers them.
#
# SAFETY. Every check runs against its own scratch XDG_CONFIG_HOME under a
# mktemp work directory. The developer's own ~/.config/omarchy/shell.json is
# stamped before the first check and asserted untouched as C1 -- a check, not a
# comment, because this is a scenario whose whole subject is changing the mode
# of a file in ~/.config. The verb is NEVER invoked without XDG_CONFIG_HOME
# set, so its HOME fallback is never exercised against the real file; that path
# is the one thing here left deliberately unobserved.
#
# Holds no display: starts no quickshell, no mpv, sends no keystroke, and reads
# nothing from the live install.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
# 77 is this project's "this machine cannot run that half", as pip-scenario.sh
# uses it. `live` is accepted and SKIPPED rather than rejected, because the
# live half is a real thing that is missing, and a usage error would read as
# though it had never been thought about. The note at the foot says what it
# would observe.
LIVE_SKIP=77
MODE=${1:-check-tree}
case $MODE in
  check-tree) shift || true ;;
  live)
    echo "SKIP config-mode live: not written yet. The service had no call to the" >&2
    echo "     D-SINK-18 verb when this scenario was written, so a live half would" >&2
    echo "     have had to invent the API it then asserted. See the foot of this" >&2
    echo "     file for what it must observe once that seam lands." >&2
    exit "$LIVE_SKIP" ;;
  -*) MODE=check-tree ;;
  *) echo "usage: config-mode-scenario.sh [check-tree|live] [--helper <path>] [--verb '<words>']" >&2; exit 2 ;;
esac
HELPER="$ROOT/bin/omarchy-iptv"
# The verb, as one place to change it. CLAUDE.md rule 13: this scenario and the
# helper are joined by a NAME, nothing calls across the join, and a name only a
# human copies is a name that eventually stops being copied -- so V1 makes the
# join a call and says which name it looked for when it is not there.
VERB="config shield"
while (( $# )); do
  case $1 in
    --helper) HELPER=${2:-}; shift
      [[ -n $HELPER && -f $HELPER ]] || { echo "--helper needs an existing file, got '${HELPER:-<empty>}'" >&2; exit 2; } ;;
    --verb) VERB=${2:-}; shift
      # Refused rather than defaulted: a dropped value here would leave VERB
      # empty and every check below would grade an argument-less helper run,
      # which is a green nobody asked for. The tls lane's --pre-tls refusals
      # exist for the same reason.
      [[ -n $VERB && $VERB =~ ^[a-z][a-z-]*([[:space:]][a-z][a-z-]*)*$ ]] \
        || { echo "--verb takes lowercase verb words, got '${VERB:-<empty>}'" >&2; exit 2; } ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

# CLAUDE.md parallel rule 7, and F-M3-1: the evidence does not live in whoever
# remembered to keep stdout. Printed first, so the transcript names itself.
qa_transcript_start config-mode || exit 2

WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-cfgmode.XXXXXX") || exit 2
chmod 0700 "$WORK"
# F-HARNESS-14: cleanup is guarded on a flag set only once this process owns
# something worth cleaning. A removal above an argument refusal is how a lane
# once killed whatever else held its port; here the equivalent harm is rm -rf
# over a path the refusal never created.
OWN_WORK=1
cleanup() { (( OWN_WORK )) && [[ -n ${WORK:-} && -d $WORK ]] && rm -rf "$WORK"; }
trap cleanup EXIT

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL $1${2:+ -- $2}"; }
# One assertion, one line, so the floor at the foot can be counted by recipe.
ck() { local label=$1 got=$2 want=$3; [[ $got == "$want" ]] && pass "$label: $want" || fail "$label" "got [$got], want [$want]"; }

# The synthetic credential. Unique per run, letters and digits only, so a hit
# anywhere in the verb's output is this run's and nothing else's. It travels in
# OMARCHY_IPTV_URL, which is where the service puts a real one (D-SINK-8).
TOKEN="c$$$RANDOM"
PROBE_URL="http://u$TOKEN:p$TOKEN@127.0.0.1/list.m3u"
OUT="$WORK/out"; ERR="$WORK/err"; ALL="$WORK/all"
: >"$ALL"

# The developer's own config, resolved the way the helper resolves it but from
# the OUTER environment, which this scenario never modifies: the overrides
# below travel to the child through `env` and leave this shell's own
# XDG_CONFIG_HOME alone. Read-only, by stamp, and never passed to the verb.
REAL_CONFIG="${XDG_CONFIG_HOME:-${HOME:-/nonexistent}/.config}/omarchy/shell.json"
REAL_BEFORE=$(qa_file_stamp "$REAL_CONFIG")
echo "== real config $REAL_CONFIG"
echo "== real config before: mode $(qa_mode_private "$REAL_CONFIG") stamp ${REAL_BEFORE:0:16}..."

# A fresh scratch XDG_CONFIG_HOME holding one shell.json at <mode>. Each check
# gets its own, so one check's chmod cannot be the next one's starting point.
# Returns the directory to use as XDG_CONFIG_HOME.
mkcfg() {
  # Declared apart: one `local a=$1 b="$a"` evaluates b before a exists, and
  # under `set -u` that is an unbound-variable abort inside a command
  # substitution, which surfaces as "cannot create a scratch config" and not
  # as the real cause. Cost this scenario one run to find.
  local name=$1 mode=$2
  local dir="$WORK/$name"
  mkdir -p "$dir/omarchy" || return 1
  printf '%s\n' '{"version":1,"bar":{"layout":{"left":[],"center":[],"right":[{"id":"io.github.rmcdavid.iptv"}]}}}' \
    >"$dir/omarchy/shell.json" || return 1
  chmod "$mode" "$dir/omarchy/shell.json" || return 1
  printf '%s\n' "$dir"
}

# Drive the verb once. XDG_CONFIG_HOME is always passed explicitly -- never
# inherited, never unset -- so no run of this scenario can reach the real file
# through the helper's HOME fallback. Prints "rc=<n>"; stdout and stderr land in
# $OUT and $ERR and are appended to $ALL for S1 to sweep at the end.
shield() {
  local cfg=$1; shift
  local rc
  # argv only (rule 2): the verb words are split deliberately and nothing here
  # is interpolated into a shell string.
  # shellcheck disable=SC2086
  env "XDG_CONFIG_HOME=$cfg" "OMARCHY_IPTV_URL=$PROBE_URL" \
    python3 "$HELPER" $VERB "$@" >"$OUT" 2>"$ERR"
  rc=$?
  cat "$OUT" "$ERR" >>"$ALL"
  printf 'rc=%d\n' "$rc"
}

echo "== helper $HELPER   verb '$VERB'   mutation ${STUB_MUTATION:-<unset>}"

# ---- V1: the verb exists. A CAPABILITY probe, not an acceptance criterion:
# every mode assertion below is observed with stat, and this one line exists so
# that a missing verb reads as "the helper has no 'config shield'" instead of
# nine confusing mode failures. argparse answers an unknown subcommand with
# status 2 and "invalid choice" on stderr, which is what this distinguishes.
v1cfg=$(mkcfg v1 0644) || { echo "FAIL V1 -- cannot create a scratch config"; exit 2; }
v1rc=$(shield "$v1cfg")
if [[ $v1rc == "rc=2" ]] && grep -qa "invalid choice\|unknown verb\|unrecognized arguments" "$ERR"; then
  v1="absent"
else
  v1="present"
fi
ck V1 "$v1" "present"

# ---- M1: the packaged default's mode, which is the whole finding.
m1cfg=$(mkcfg m1 0644) || exit 2
m1rc=$(shield "$m1cfg")
ck M1 "$m1rc $(qa_mode_private "$m1cfg/omarchy/shell.json")" "rc=0 private"

# ---- M2 / M3: the mask's two halves, driven apart.
m2cfg=$(mkcfg m2 0640) || exit 2
m2rc=$(shield "$m2cfg")
ck M2 "$m2rc $(qa_mode_private "$m2cfg/omarchy/shell.json")" "rc=0 private"

m3cfg=$(mkcfg m3 0604) || exit 2
m3rc=$(shield "$m3cfg")
ck M3 "$m3rc $(qa_mode_private "$m3cfg/omarchy/shell.json")" "rc=0 private"

# ---- M4: an already-private container is left completely alone. The stamp is
# taken, then a bounded pause, so that a chmod during the run lands on a
# DIFFERENT nanosecond than the stamp -- without it a fast enough no-op and a
# fast enough chmod would be indistinguishable and the check would be the kind
# that cannot go red.
m4cfg=$(mkcfg m4 0600) || exit 2
m4before=$(qa_file_stamp "$m4cfg/omarchy/shell.json")
sleep 0.05
m4rc=$(shield "$m4cfg")
ck M4 "$m4rc $(qa_file_untouched "$m4cfg/omarchy/shell.json" "$m4before")" "rc=0 untouched"

# ---- R1: the ordering, as the counterfactual. A container that can NEVER be
# made private: shell.json is a symlink to itself, so every chmod and every
# resolution answers ELOOP whatever the implementation tries. No root, no
# foreign file, nothing in /usr touched -- and unlike a merely ABSENT file
# there is no defensible design under which this one succeeds, so the refusal
# is deterministic and not a matter of taste. Correct code refuses here and the
# caller never persists; write-then-tighten has already written the credential
# by the time it finds out, which is why this is the ordering check.
r1dir="$WORK/r1"
mkdir -p "$r1dir/omarchy" || exit 2
ln -s "shell.json" "$r1dir/omarchy/shell.json" || exit 2
r1rc=$(shield "$r1dir")
[[ $r1rc == "rc=0" ]] && r1="accepted" || r1="refused"
ck R1 "$r1" "refused"

# ---- R2: rc 0 is never answered over a path that is not a private regular
# file. Stated as an implication rather than as a required refusal, because a
# verb that CREATES the file at 0600 when it is missing is a defensible reading
# of the ruling -- `state state init` already does exactly that for
# state.json -- and this lane does not get to widen the ruling into a choice
# the owner did not make. What is not defensible either way is answering 0 over
# something nobody shielded. Driven over a DANGLING symlink, where both designs
# are legitimate and only the dishonest answer fails.
r2dir="$WORK/r2"
mkdir -p "$r2dir/omarchy" || exit 2
ln -s "$r2dir/omarchy/nowhere.json" "$r2dir/omarchy/shell.json" || exit 2
r2rc=$(shield "$r2dir")
if [[ $r2rc != "rc=0" ]]; then
  r2="refused"
elif [[ -f $r2dir/omarchy/shell.json && $(qa_mode_private "$r2dir/omarchy/shell.json") == private ]]; then
  r2="refused"   # it answered 0 AND there is now a private regular file there
else
  r2="claimed"
fi
ck R2 "$r2" "refused"

# ---- R3: the path is computed, not accepted. A decoy at 0644 is offered as an
# argument while XDG_CONFIG_HOME points somewhere else entirely; whatever the
# verb does with the argument, the decoy must still be exposed afterwards. This
# is the check that the helper "computes the one path it is allowed to touch
# from the environment and refuses anything else".
r3cfg=$(mkcfg r3 0600) || exit 2
DECOY="$WORK/decoy.json"
printf '%s\n' '{"decoy":true}' >"$DECOY" || exit 2
chmod 0644 "$DECOY" || exit 2
# The status is PRINTED, not asserted: whether an offered path is a refusal
# (status) or simply ignored (no status at all) is the code lane's choice, and
# the property that is not theirs to choose is that the decoy is not touched.
r3rc=$(shield "$r3cfg" "$DECOY")
echo "   R3 the verb answered $r3rc to an offered path; what matters is the decoy below"
ck R3 "$(qa_mode_private "$DECOY")" "both"

# ---- S1: rule 5 at this sink. Everything the verb wrote to either stream,
# across every run above, swept for the synthetic credential and for the probe
# URL's userinfo. The verb has no business holding a URL at all; this is the
# check that it never printed the one the environment carried.
if grep -qa -- "$TOKEN" "$ALL"; then
  s1="leaked"
  echo "   S1 evidence: $(grep -a -o -- ".\{0,24\}$TOKEN.\{0,12\}" "$ALL" | head -2 | tr '\n' ';')"
else
  s1="clean"
fi
ck S1 "$s1" "clean"

# ---- C1: the developer's own config, untouched. The one check whose failure
# means this scenario broke somebody's desktop rather than found a defect.
REAL_AFTER=$(qa_file_stamp "$REAL_CONFIG")
if [[ $REAL_BEFORE == "$QA_NO_FIELD" ]]; then
  # No real config on this machine is not a pass and not a defect: it is a run
  # with nothing to protect, and saying so beats claiming either. It still
  # fails the check, because a C1 that passes when it measured nothing is the
  # vacuous pass this project keeps finding.
  c1="no-real-config(before=$REAL_BEFORE,after=$REAL_AFTER)"
else
  c1=$(qa_file_untouched "$REAL_CONFIG" "$REAL_BEFORE")
fi
# One line at column zero so the floor recipe at the foot can count it.
ck C1 "$c1" "untouched"
echo "== real config after: mode $(qa_mode_private "$REAL_CONFIG") stamp ${REAL_AFTER:0:16}..."

# The floor. A check that stops executing must turn the run red rather than
# quietly shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ck [A-Z]' config-mode-scenario.sh
# Every assertion is ONE line at column zero whose label is uppercase, so the
# definition of ck() does not match and the floor's own assertion -- which is
# not a `ck` line -- cannot count itself. Never lower it to make a run green.
EXPECTED_CHECKS=10
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  pass "the scenario ran every check it has ($ran)"
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi

echo "config-mode-scenario: $PASS passed, $FAIL failed (helper $HELPER, verb '$VERB', mutation ${STUB_MUTATION:-<unset>})"
# WHAT A LIVE HALF WOULD HAVE TO OBSERVE, and why it is not here. The property
# this scenario cannot reach is that Service.qml GATES persistActive on the
# verb's answer: on a refusal, no URL reaches the bar entry and
# sourcesPersistFailed carries a reason. The harness can show it -- the service
# spawns the real helper, which really chmods $XDG_CONFIG_HOME/omarchy/
# shell.json (run.sh now isolates and seeds that, at 0644, so an ordinary
# harness run exercises the tightening instead of reaching into the
# developer's own config) -- and updateEntryInline is already logged with keys
# only. What is missing is the seam itself: at the time this was written the
# service had no call to the verb, so a live half would have had to invent the
# API it then asserted. It belongs in the display lane's hands once that seam
# lands, and it is named here so the gap is a line someone reads rather than a
# silence.
(( FAIL == 0 ))
