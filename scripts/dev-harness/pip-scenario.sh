#!/bin/bash
# scripts/dev-harness/pip-scenario.sh -- scripted verification of picture in
# picture (M2-05), driven against a STUB compositor so it touches nothing.
#
#   pip-scenario.sh check-tree   the capability preflight ONLY; no display,
#                                no quickshell, no player, no hyprctl.
#                                Run by scripts/check.sh on every commit.
#   pip-scenario.sh [live]       the preflight, then the live half.
#
# WHY THE STUB. Every other scenario in this repo drives the plugin against
# the real thing. This one must not: the feature's whole job is to float,
# shrink, move and pin a window, and a scenario that did that for real would
# rearrange the windows of whoever ran it. `stub-hyprctl.py` goes on PATH in
# front of the real binary (run.sh harness_env), holds its compositor state in
# a JSON file this script seeds, and records the argv of every call. So the
# scenario can assert the exact vectors the service issued AND the exact state
# they produced, with the user's session untouched.
#
# WHAT RUNS WHERE. The decisions -- what geometry the defaults give, what a
# plan contains given a live state, what counts as verified -- are pure and
# live in Model.js, asserted by name in tests/Model.test.js. The fidelity of
# the stub itself is asserted in tests/test_pip.py against the transcript the
# M2-05-00 gate recorded, because a fake that is more forgiving than the real
# compositor is the failure this project has already paid for twice
# (CLAUDE.md rule 10). What is HERE is the half only a running service can
# answer: that it issues those vectors, in that order, at the pid-narrowed
# address, and that it calls the result a success only after reading it back.
#
# STATUS OF THE LIVE HALF, stated plainly. The preflight below has been run
# and has been seen failing against a tree without the seams. The live half
# has NOT been run by the lane that wrote it -- that lane does not hold the
# display, and starting the harness starts a quickshell. Until the display
# lane runs it, these scenarios are "has a runner", not "passes". Do not
# record them as passing on the strength of this file existing.
#
# WHAT IS NOT HERE, and why. Everything the stub cannot honestly model:
# whether Hyprland accepts the Lua dispatch form at all (G-1), whether the
# box survives a real zap (G-4) or a theme switch (G-12), whether a pasted
# static float rule snaps a moved window back (G-5), and what a fullscreen
# work window does to a pinned one (PIP-12). Those are the PIP- matrix, and
# they need the display and a real compositor.
#
# THE FOUR SEAMS THIS HEADER ASKED FOR ARE NOW HERE. They could not be while
# lane V1 was unmerged - asserting the guide's `p` key or the Model.js pure
# layer would have turned scripts/check.sh red on a tree that did not have
# them yet. Integration added them, and four more that only exist because of
# what integration itself decided: PIP15's single dispatch spelling, the
# absence of a fallback to it in either file, and the one name the snapshot
# key has. Both floors went up by eight, not four.
#
# One of the four is NOT written the way this header suggested it. The line
# it proposed was
#     seam "no stand-in survives" "$PLUGIN_ROOT/Service.qml" 'STAND-IN-M2-05-V1' 0
# and `seam` passes when the count is at least `want`, so a `want` of 0 is a
# check that cannot fail: it stays green against a file full of stand-ins, a
# renamed file and an unreadable one alike. That is the shape this project
# has now found four times. Absence is asserted by `absent` below, which
# proves the file is there and readable FIRST and only then that the marker
# is not.
#
# Where a seam points also moved with the code. The plan, the geometry, the
# verification and the two mpv constants are pure logic and now live in
# Model.js, where node and the QML spec call them for real (CLAUDE.md 12);
# what is asserted against Service.qml is that it delegates.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
PLUGIN_ROOT=$(cd "${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}" 2>/dev/null && pwd)
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
FIX="$SCRATCH/fixtures"
LOG="$SCRATCH/pip-scenario.log"
STUB_STATE="$SCRATCH/hypr-state.json"
STUB_CALLS="$SCRATCH/hypr-calls.log"
HARNESS_PID=""
pass=0
fail=0
checks=0

# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"

ok()   { printf 'PASS %s\n' "$*"; pass=$((pass + 1)); }
bad()  { printf 'FAIL %s\n' "$*"; fail=$((fail + 1)); }
check() { checks=$((checks + 1)); if eval "$2"; then ok "$1"; else bad "$1"; fi; }
ipc()  { "$RUN" ipc "$@" 2>/dev/null; }
pf()   { qa_json_field "d$1" "$(ipc pipState)"; }
sf()   { qa_field "d$1" "$(ipc state)"; }

cleanup() {
  if [[ -n $HARNESS_PID ]]; then kill -TERM "$HARNESS_PID" 2>/dev/null; wait "$HARNESS_PID" 2>/dev/null; fi
  return 0
}

# Bounded, and it SAYS it gave up (CLAUDE.md rule 3).
wait_for() {
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ "$("$@")" == "$want" ]] && return 0
    sleep 0.1
  done
  echo "[pip-scenario] gave up waiting ${secs}s for '$want' from: $*" >&2
  return 1
}

# `win <expr over c> [address]`: a field of the window this fake compositor
# holds, as python prints it. Without an address it answers about OUR player
# window, which is the one at the seeded pid. NOWINDOW and NOSTATE are values
# no assertion below will ever match, so a missing state file fails a check
# rather than passing one.
win() {
  python3 -c '
import json, sys
try:
    state = json.load(open(sys.argv[1]))
except Exception:
    print("NOSTATE"); raise SystemExit(0)
want = sys.argv[2]
for client in state.get("clients", []):
    if client.get("address") == want if want.startswith("0x") else client.get("class") == want:
        print(json.dumps(eval(sys.argv[3], {}, {"c": client}))); raise SystemExit(0)
print("NOWINDOW")' "$STUB_STATE" "${2:-0x559c6893d940}" "$1" 2>/dev/null || echo NOSTATE
}

# The foreign client of the same class: PLY-RST-11's reproduced case, a user's
# own `mpv --wayland-app-id=omarchy-iptv`. Every assertion about it is that it
# did not move by so much as a pixel.
FOREIGN_UNTOUCHED='[[12, 38], [650, 718], false, false, ["default-opacity*"]]'
foreign() {
  win "[c['at'], c['size'], c['floating'], c['pinned'], c['tags']]" 0x559c687e09a0
}

# ---------------------------------------------------------------- preflight
#
# `seam <label> <file> <ere> <at least>`: a POSITIVE count, never a `! grep`.
# qa_count answers 0 for a missing or unreadable file, so a tree without the
# file fails here instead of passing an absence test.
seam() {
  local label=$1 file=$2 ere=$3 want=$4
  checks=$((checks + 1))
  local got
  got=$(qa_count "$ere" "$file")
  if (( got >= want )); then ok "$label"; else bad "$label (matched $got, wanted at least $want in ${file#"$PLUGIN_ROOT/"})"; fi
}

# `absent <label> <file> <ere>`: the marker is NOT in the file, and the file
# is really there. Never `seam ... 0`, which passes against anything at all,
# including a file that does not exist. The positive probe first is what
# makes the negative mean something: a non-empty file, then no match.
absent() {
  local label=$1 file=$2 ere=$3
  checks=$((checks + 1))
  if [[ ! -s $file ]]; then
    bad "$label (no such file, or empty: ${file#"$PLUGIN_ROOT/"} - an absence test over nothing proves nothing)"
    return
  fi
  local got
  got=$(qa_count "$ere" "$file")
  if (( got == 0 )); then ok "$label"; else bad "$label (matched $got in ${file#"$PLUGIN_ROOT/"}, wanted none)"; fi
}

preflight() {
  echo "== preflight: can this tree drive picture in picture? (plugin: $PLUGIN_ROOT)"
  # The service's two entry points and the verb a user runs.
  seam "the service answers the guide's p key"            "$PLUGIN_ROOT/Service.qml" '^ *function togglePip\(\)' 1
  seam "the service has one entry point for both surfaces" "$PLUGIN_ROOT/Service.qml" '^ *function requestPip\(mode\)' 1
  seam "the plugin declares the pip IPC verb"             "$PLUGIN_ROOT/Service.qml" 'function pip\(mode: string\): string' 1
  # Read-then-act (PIP10): the compositor is read, and the two toggling steps
  # are behind that read.
  seam "the service reads the compositor"                 "$PLUGIN_ROOT/Service.qml" 'command: \["hyprctl", "-j", "clients"\]' 1
  seam "and reads the monitor it will place the box on"   "$PLUGIN_ROOT/Service.qml" 'command: \["hyprctl", "-j", "monitors"\]' 1
  seam "the float step is behind a live read"             "$PLUGIN_ROOT/Model.js" 'if \(l\.floating !== true\) steps\.push' 1
  seam "the pin step is behind a live read"               "$PLUGIN_ROOT/Model.js" 'if \(l\.pinned !== true\) steps\.push' 1
  # Verification is the definition of success (PIP11).
  seam "success is a readback, in one place"              "$PLUGIN_ROOT/Service.qml" '^ *function pipCheck\(live\)' 1
  seam "and the comparison it makes"                      "$PLUGIN_ROOT/Model.js" '^function pipVerify\(live, intent, expected\)' 1
  seam "a dispatch step reports nothing but its text"     "$PLUGIN_ROOT/Service.qml" '^ *function pipNoteStep\(text, exitCode\)' 1
  # The pure layer the service calls instead of carrying (M2-05-02), and the
  # guide key that reaches it. These four are the seams this file's header
  # asked for once lane V1 had merged.
  seam "Model.js owns the plan"                           "$PLUGIN_ROOT/Model.js" '^function pipPlan\(' 1
  seam "Model.js owns the geometry"                       "$PLUGIN_ROOT/Model.js" '^function pipGeometry\(' 1
  seam "Guide.qml routes the p key"                       "$PLUGIN_ROOT/Guide.qml" 'togglePip\(\)' 1
  absent "no stand-in survives integration"               "$PLUGIN_ROOT/Service.qml" 'STAND-?IN'
  # PIP15: one spelling, chosen from the compositor's own answer, no second
  # arm to fall back to.
  seam "the dispatch spelling is chosen once"             "$PLUGIN_ROOT/Service.qml" 'root\.pipProvider = /configProvider' 1
  absent "and no fallback spelling ships"                 "$PLUGIN_ROOT/Model.js" '"(tagwindow|togglefloating|resizewindowpixel|movewindowpixel|alterzorder)"'
  absent "nor a second builder inside the service"        "$PLUGIN_ROOT/Service.qml" 'pipLegacyDispatch|"(tagwindow|togglefloating|resizewindowpixel|movewindowpixel|alterzorder)"'
  # Addressing, the snapshot, and the mpv half.
  seam "the window is narrowed by the player pid"         "$PLUGIN_ROOT/Service.qml" 'pipFindWindow\(text, root\.playerPid, root\.pipClass\)' 1
  seam "the snapshot lives in the player"                 "$PLUGIN_ROOT/Model.js" 'PIP_SNAPSHOT_KEY = "user-data/omarchy-iptv-pip"' 1
  seam "and the service asks for it by that one name"     "$PLUGIN_ROOT/Service.qml" 'Model\.PIP_SNAPSHOT_KEY' 1
  seam "and is read back after a shell restart"           "$PLUGIN_ROOT/Service.qml" '^ *function pipRequestSnapshot\(sock\)' 1
  # D-PIP-4 / 4.7 step 3. The snapshot above says what the window WAS; this
  # says what it IS, and without it the plugin reported `off` for as long as
  # the user did not press the key. Three seams because it is three things:
  # a read, the two places a player becomes ours, and a pure decision.
  seam "and what it IS is re-derived, not remembered"     "$PLUGIN_ROOT/Service.qml" '^ *function pipApplyPeek\(text\)' 1
  seam "that read runs when a player becomes ours"        "$PLUGIN_ROOT/Service.qml" 'root\.pipPeek\(\)' 2
  seam "and the derivation is pure, so a test can call it" "$PLUGIN_ROOT/Model.js" '^function pipDeriveState\(' 1
  seam "a channel change cannot resize the box"           "$PLUGIN_ROOT/Model.js" 'PIP_MPV_RESIZE_PROP' 4
  seam "status carries the verified state"                "$PLUGIN_ROOT/Service.qml" 'available: root\.pipAvailable' 1
  # Bounds (CLAUDE.md rule 3).
  seam "one bound per compositor round trip"              "$PLUGIN_ROOT/Service.qml" 'id: pipStepWatchdog' 1
  seam "and one on the whole sequence"                    "$PLUGIN_ROOT/Service.qml" 'id: pipSequenceWatchdog' 1
  # The harness itself, and the stub it drives the service against.
  seam "the harness declares the pip verb"                "$HERE/shell.qml" 'function pip\(mode: string\): string' 1
  seam "the harness drives the guide key through the service" "$HERE/shell.qml" 'function pipKey\(\): string' 1
  seam "the harness answers with one pip snapshot"        "$HERE/shell.qml" 'function pipSnapshot\(s\)' 1
  seam "the harness state carries it"                     "$HERE/shell.qml" 'out\.service\.pip = harness\.pipSnapshot\(s\)' 1
  seam "the harness seeds the three settings"             "$HERE/shell.qml" 'pipSizePercent: parseInt' 1
  seam "run.sh puts a scenario bin in front of PATH"      "$HERE/run.sh" 'export PATH="\$SCRATCH/bin:\$PATH"' 1
  seam "the stub compositor exists"                       "$HERE/stub-hyprctl.py" 'STUB_HYPRCTL_STATE' 2
  # The two behaviours that make the design's original failure detection
  # unimplementable. tests/test_pip.py drives both against the gate's
  # transcript; these two lines are what it drives.
  seam "it models the success that means nothing"         "$HERE/stub-hyprctl.py" '^ *if target is None:' 1
  seam "and the action argument that is ignored"          "$HERE/stub-hyprctl.py" '^def float_window\(' 1
  checks=$((checks + 1))
  if [[ -x "$HERE/stub-hyprctl.py" ]]; then ok "the stub compositor is executable"
  else bad "the stub compositor is not executable (chmod +x)"; fi
}

# ------------------------------------------------------------------- live
seed_stub() {
  # One tiled player window at the pid the SERVICE holds, plus a foreign
  # client of the same class at another pid -- PLY-RST-11's case, which is
  # the whole reason the lookup is narrowed by pid.
  local pid=$1
  mkdir -p "$SCRATCH/bin"
  ln -sfn "$HERE/stub-hyprctl.py" "$SCRATCH/bin/hyprctl"
  python3 -c '
import json, sys
pid = int(sys.argv[2])
json.dump({
  "clients": [
    {"class": "omarchy-iptv", "pid": pid, "address": "0x559c6893d940",
     "at": [690, 38], "size": [650, 718], "floating": False, "pinned": False,
     "monitor": 0, "workspace": {"id": 1}, "tags": ["default-opacity*"]},
    {"class": "omarchy-iptv", "pid": pid + 100000, "address": "0x559c687e09a0",
     "at": [12, 38], "size": [650, 718], "floating": False, "pinned": False,
     "monitor": 0, "workspace": {"id": 1}, "tags": ["default-opacity*"]}
  ],
  "monitors": [
    {"id": 0, "name": "eDP-1", "width": 1366, "height": 768, "scale": 1,
     "transform": 0, "reserved": [0, 26, 0, 0], "x": 0, "y": 0}
  ]
}, open(sys.argv[1], "w"), indent=2)' "$STUB_STATE" "$pid"
}

live() {
  echo "== setup (scratch $SCRATCH)"
  "$RUN" clean >/dev/null
  mkdir -p "$FIX" "$SCRATCH/bin"
  sed "s|__LIVE__|http://127.0.0.1:9/dead/live.m3u8|g" "$HERE/fixtures/harness.m3u.in" >"$FIX/harness.m3u"
  : >"$LOG"
  : >"$STUB_CALLS"
  # The stub has to be on PATH before the shell starts, and it needs a state
  # file to exist even for the first availability probe.
  ln -sfn "$HERE/stub-hyprctl.py" "$SCRATCH/bin/hyprctl"
  seed_stub 1
  export STUB_HYPRCTL_STATE="$STUB_STATE"
  export STUB_HYPRCTL_LOG="$STUB_CALLS"
  # PIP15: the provider decides the spelling ONCE, and there is only one
  # spelling. Overriding this to `hyprlang` therefore does not exercise a
  # legacy path - there is none - it exercises the refusal: the service reads
  # the provider, finds a compositor whose dispatch language it does not
  # speak, and takes PiP off the offer. P1 below asserts the lua case, so an
  # override makes P1 fail on purpose; run it only to watch the refusal.
  export STUB_HYPRCTL_PROVIDER=${OMARCHY_IPTV_PIP_PROVIDER:-lua}
  export HYPRLAND_INSTANCE_SIGNATURE=${HYPRLAND_INSTANCE_SIGNATURE:-harness}

  echo "== start harness"
  HARNESS_TIMEOUT=${OMARCHY_IPTV_SCENARIO_TIMEOUT:-300}
  "$RUN" --keep --timeout "$HARNESS_TIMEOUT" --playlist "$FIX/harness.m3u" >>"$LOG" 2>&1 &
  HARNESS_PID=$!
  wait_for 20 30 sf "['channels']" || bad "the fixture playlist never loaded; every check below is about nothing"

  echo "== P1 availability, decided once from the host's own answer"
  wait_for true 10 pf "['available']" || bad "the service never decided PiP was available"
  check "P1: PiP is on offer"                                   '[[ "$(pf "['\''available'\'']")" == true ]]'
  check "P1: and the dispatch spelling came from systeminfo"    '[[ "$(pf "['\''provider'\'']")" == "lua" ]]'
  check "P1: nothing is playing, so it is off"                  '[[ "$(pf "['\''on'\'']")" == false ]]'

  echo "== P2 with no player, the verb refuses rather than starting one"
  r=$(ipc pip toggle)
  check "P2: the answer is a refusal"                           '[[ "$(qa_json_field "d['\''ok'\'']" "$r")" == false ]]'
  check "P2: named nothing_playing"                             '[[ "$(qa_json_field "d['\''error'\''][\"code\"]" "$r")" == "nothing_playing" ]]'
  check "P2: and it issued no dispatch at all"                  '[[ "$(qa_count "dispatch" "$STUB_CALLS")" == 0 ]]'
  check "P2: an unknown mode is refused too"                    '[[ "$(qa_json_field "d['\''error'\''][\"code\"]" "$(ipc pip sideways)")" == "bad_mode" ]]'

  echo "== P3 play a channel, then teach the fake compositor our pid"
  ipc play "t:bbc1.uk" >/dev/null
  wait_for true 20 sf "['playerUp']" || bad "the player never came up; every check below is about nothing"
  pid=$(pf "['playerPid']")
  check "P3: the service learned the player pid from the player itself" '[[ "$pid" =~ ^[0-9]+$ && "$pid" != 0 ]]'
  seed_stub "$pid"
  : >"$STUB_CALLS"

  echo "== P4 pip on: the six steps, the exact geometry, the readback"
  ipc pip on >/dev/null
  wait_for false 10 pf "['applying']" || bad "the sequence never finished"
  check "P4: the service calls it on only after reading it back" '[[ "$(pf "['\''on'\'']")" == true ]]'
  check "P4: with no failure code"                               '[[ "$(pf "['\''reason'\'']")" == "" ]]'
  check "P4: the window floats"                                  '[[ "$(win "c['\''floating'\'']")" == true ]]'
  check "P4: and is pinned, so it follows you"                   '[[ "$(win "c['\''pinned'\'']")" == true ]]'
  check "P4: and carries our tag"                                '[[ "$(win "c['\''tags'\'']")" == *"iptv-pip"* ]]'
  # The defaults on this monitor: 30 percent of 1366 is 410, 16:9 is 230, and
  # the top-right corner clears both the 16 px margin and the 26 px bar.
  check "P4: at the geometry the defaults compute"               '[[ "$(win "c['\''at'\'']")" == "[940, 42]" && "$(win "c['\''size'\'']")" == "[410, 230]" ]]'
  check "P4: the foreign window of the same class is byte-identical" '[[ "$(foreign)" == "$FOREIGN_UNTOUCHED" ]]'

  echo "== P5 every vector, inspected"
  check "P5: every dispatch names our address, never a class"    '[[ "$(qa_count "0x559c6893d940" "$STUB_CALLS")" -ge 6 && "$(qa_count "class:" "$STUB_CALLS")" == 0 ]]'
  check "P5: and never the foreign window's"                     '[[ "$(qa_count "0x559c687e09a0" "$STUB_CALLS")" == 0 ]]'
  check "P5: no URL reached the compositor"                      '[[ "$(qa_count "://" "$STUB_CALLS")" == 0 ]]'
  check "P5: no channel name did either"                         '[[ "$(qa_count "BBC" "$STUB_CALLS")" == 0 ]]'
  check "P5: the sequence ENDED by reading the state back"       '[[ "$(qa_json_field "d['\''argv'\'']" "$(tail -1 "$STUB_CALLS")")" == *"clients"* ]]'
  check "P5: and the foreign window is still untouched"          '[[ "$(foreign)" == "$FOREIGN_UNTOUCHED" ]]'

  echo "== P6 pip on again is not a second application"
  before=$(win "c['at']")
  ipc pip on >/dev/null
  wait_for false 10 pf "['applying']" || bad "the second sequence never finished"
  check "P6: the box has not moved"                              '[[ "$(win "c['\''at'\'']")" == "$before" ]]'
  check "P6: and it is still on"                                 '[[ "$(pf "['\''on'\'']")" == true ]]'

  echo "== P7 pip off returns the window to where the layout had it"
  ipc pip off >/dev/null
  wait_for false 10 pf "['applying']" || bad "the exit never finished"
  check "P7: the service calls it off only after reading it back" '[[ "$(pf "['\''on'\'']")" == false ]]'
  check "P7: the window is tiled again"                          '[[ "$(win "c['\''floating'\'']")" == false ]]'
  check "P7: unpinned"                                           '[[ "$(win "c['\''pinned'\'']")" == false ]]'
  check "P7: untagged"                                           '[[ "$(win "c['\''tags'\'']")" != *"iptv-pip"* ]]'
  check "P7: and back on the rectangle it started from"          '[[ "$(win "c['\''at'\'']")" == "[690, 38]" && "$(win "c['\''size'\'']")" == "[650, 718]" ]]'

  echo "== P8 the guide's key and the verb are the same path"
  ipc pipKey >/dev/null
  wait_for true 10 pf "['on']" || bad "the p key did not enter PiP"
  check "P8: p enters"                                           '[[ "$(win "c['\''floating'\'']")" == true ]]'
  ipc pipKey >/dev/null
  wait_for false 10 pf "['on']" || bad "the p key did not leave PiP"
  check "P8: p leaves"                                           '[[ "$(win "c['\''floating'\'']")" == false ]]'
  check "P8: two toggles return to the starting state"           '[[ "$(win "c['\''at'\'']")" == "[690, 38]" ]]'

  echo "== P9 a window the user popped themselves is not ours to undo"
  python3 -c '
import json, sys
state = json.load(open(sys.argv[1]))
for client in state["clients"]:
    if client["address"] == "0x559c6893d940":
        client["floating"] = True
        client["pinned"] = True
json.dump(state, open(sys.argv[1], "w"), indent=2)' "$STUB_STATE"
  ipc pip off >/dev/null
  wait_for false 10 pf "['applying']" || bad "the no-op exit never finished"
  check "P9: a floating pinned window with no tag of ours is left alone" '[[ "$(win "c['\''floating'\'']")" == true && "$(win "c['\''pinned'\'']")" == true ]]'

  echo "== P10 the window goes away with the player"
  ipc stop >/dev/null
  wait_for false 15 sf "['playerUp']" || bad "the player never went away"
  check "P10: PiP is off"                                        '[[ "$(pf "['\''on'\'']")" == false ]]'
  check "P10: and the pid is forgotten, so nothing can be addressed" '[[ "$(pf "['\''playerPid'\'']")" == 0 ]]'
  check "P10: a toggle now refuses"                              '[[ "$(qa_json_field "d['\''error'\''][\"code\"]" "$(ipc pip toggle)")" == "nothing_playing" ]]'

  echo "== privacy (R12)"
  checks=$((checks + 1))
  qa_answer_lacks '://' "$(ipc pipState)"
  case $? in
    0) ok "the pipState answer carries no URL" ;;
    1) bad "the pipState answer carries a URL" ;;
    *) bad "the IPC did not answer at all: 'no URL' is not evidence" ;;
  esac
  checks=$((checks + 1))
  qa_answer_lacks '://' "$(ipc state)"
  case $? in
    0) ok "the state answer carries no URL" ;;
    1) bad "the state answer carries a URL" ;;
    *) bad "the IPC did not answer at all: 'no URL' is not evidence" ;;
  esac
}

trap cleanup EXIT

case ${1:-live} in
  check-tree) preflight ;;
  live|"")    preflight; live ;;
  *) echo "usage: pip-scenario.sh [check-tree|live]" >&2; exit 2 ;;
esac

# The floor. A check that stops executing must turn the run red rather than
# shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ *(seam|absent) ' pip-scenario.sh         plus 1  -> check-tree
#   grep -cE '^ *(check|seam|absent) ' pip-scenario.sh   plus 3  -> live
# (the 1 is the executable probe, which bumps `checks` by hand; the 3 are that
# probe plus the privacy block's two. The definitions of check() and seam() do
# not match the pattern, and the floor's own bump lands after the count is
# taken.) scripts/qa-lib-test.sh asserts both numbers against this file, so a
# forgotten bump turns check.sh red here rather than on the display lane's
# machine weeks later. Never lower it to make a run green.
if [[ ${1:-live} == check-tree ]]; then
  EXPECTED_CHECKS=38
else
  EXPECTED_CHECKS=75
fi
ran=$checks
checks=$((checks + 1))
if [[ "$ran" == "$EXPECTED_CHECKS" ]]; then
  ok "the scenario ran every check it has ($ran)"
else
  bad "the scenario ran $ran checks, expected $EXPECTED_CHECKS (one stopped executing)"
fi

echo
echo "summary: $pass passed, $fail failed, $checks assertions executed"
(( fail == 0 ))
