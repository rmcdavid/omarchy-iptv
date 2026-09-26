#!/bin/bash
# scripts/dev-harness/m3-scenario.sh -- live verification of M3-01 (hide
# groups) and M3-02 (audio and subtitle picker) through the harness IPC and
# real keys, against a REAL mpv playing a generated file with two audio
# tracks and one subtitle. Opens real windows for ~60 s and reaps everything
# it starts. Holds the display: run it from the lane that owns it.
#
#   H1  the column lists the fixture's groups, nothing hidden
#   H2  x on a row in a group hides that group: it moves under HIDDEN, All
#       shrinks, the transient says so, the scope stays put
#   H3  search from All does not find a hidden channel
#   H4  the hidden name is on disk (state.json) in the shape both readers accept
#   H5  x on the hidden group brings it back
#   H6  the real key path: `x` through PanelKeyCatcher, not the IPC verb
#   T1  the helper's own verb against the real player lists three tracks and
#       no external-filename (the sink, observed)
#   T2  t opens the picker; the rows are what mpv reported, the cursor sits on
#       the selected audio track
#   T3  Enter on the other audio track: the panel AND the real player agree
#   T4  the subtitle on, then Off
#   T5  real keys: Esc closes, t reopens, j moves, t closes
#   T6  stop clears the tracks; t while idle says nothing is playing
#
# Evidence rule (CLAUDE.md 10): --baseline <git-ref> exports that tree and
# runs the same checks. Measured against v0.8.0 on 2026-09-26: 7 pass and
# 23 fail. The seven are regression guards that assert an ABSENCE and so
# hold on both trees -- H1, H2c, H5a, H5b, H6b, T5a, T5d -- and the other
# twenty-three are the evidence.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
FIX="$SCRATCH/fixtures"
SOCK="$SCRATCH/runtime/omarchy-iptv/mpv.sock"
STATE="$SCRATCH/state/omarchy-iptv/state.json"
PLUGIN_ROOT=${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}
BASELINE=""; EXPORT_DIR=""; SHOTS=0
while (( $# )); do
  case $1 in
    --baseline) BASELINE=$2; shift ;;
    --shots) SHOTS=1 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac; shift
done
if [[ -n $BASELINE ]]; then
  EXPORT_DIR=$(mktemp -d /tmp/omarchy-iptv-m3-baseline.XXXXXX)
  git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR" || { echo "cannot export $BASELINE"; exit 2; }
  PLUGIN_ROOT=$EXPORT_DIR
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT
fi
PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL $1${2:+ -- $2}"; }
ipc() { "$RUN" ipc "$@" 2>/dev/null; }
# gf <python expr over g> / sf <python expr over s>: one field of state().
gf() { python3 -c 'import json,sys
try: g=json.loads(sys.argv[2])["guide"]; print(json.dumps(eval(sys.argv[1])))
except Exception as e: print("NOSTATE")' "$1" "$(ipc state)"; }
sf() { python3 -c 'import json,sys
try: s=json.loads(sys.argv[2])["service"]; print(json.dumps(eval(sys.argv[1])))
except Exception as e: print("NOSTATE")' "$1" "$(ipc state)"; }
# wait_gf <expr> <json-expected> <tries>: bounded poll, 0.25 s apart.
wait_gf() { local i; for ((i=0;i<$3;i++)); do [[ $(gf "$1") == "$2" ]] && return 0; sleep 0.25; done; return 1; }
wait_sf() { local i; for ((i=0;i<$3;i++)); do [[ $(sf "$1") == "$2" ]] && return 0; sleep 0.25; done; return 1; }
shot() { (( SHOTS )) && "$RUN" shot "$1" >/dev/null 2>&1; true; }
cleanup() {
  "$RUN" reap >/dev/null 2>&1
  # A --baseline run starts its player from the EXPORTED helper, and the reap
  # above did not always reach it (seen twice: mpv still running after the
  # run). Stop it by the socket with THIS tree's helper, which is the
  # designed door -- never by process name, which would reach the user's own
  # mpv, and never by pattern, which can match the shell running it.
  python3 "$ROOT/bin/omarchy-iptv" player stop --socket "$SOCK" >/dev/null 2>&1
  [[ -n $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
}
trap cleanup EXIT

if pgrep -x hyprlock >/dev/null; then echo "screen is locked; refusing to type"; exit 2; fi
command -v ffmpeg >/dev/null || { echo "ffmpeg missing"; exit 2; }

# ---- fixture: 90 s, two audio tracks (eng titled, spa) and an srt subtitle
mkdir -p "$FIX"
if [[ ! -s $FIX/tracks.mkv ]]; then
  printf '1\n00:00:00,000 --> 00:01:30,000\nharness subtitle\n' >"$FIX/tracks.srt"
  ffmpeg -loglevel error -y -f lavfi -i "testsrc=size=320x240:rate=15" \
    -f lavfi -i "sine=frequency=440:sample_rate=22050" -f lavfi -i "sine=frequency=660:sample_rate=22050" \
    -i "$FIX/tracks.srt" -t 90 -map 0:v -map 1:a -map 2:a -map 3:s \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 32k -c:s srt \
    -metadata:s:a:0 language=eng -metadata:s:a:0 title="English commentary" \
    -metadata:s:a:1 language=spa -metadata:s:s:0 language=eng "$FIX/tracks.mkv" || { echo "ffmpeg failed"; exit 2; }
fi
cat >"$FIX/m3.m3u" <<'M3U'
#EXTM3U
#EXTINF:-1 tvg-id="alpha" group-title="News",Alpha News
http://127.0.0.1:8765/tracks.mkv
#EXTINF:-1 tvg-id="bravo" group-title="Religious",Bravo Faith
http://127.0.0.1:8765/tracks.mkv
#EXTINF:-1 tvg-id="charlie" group-title="Religious",Charlie Faith
http://127.0.0.1:8765/tracks.mkv
#EXTINF:-1 tvg-id="delta" group-title="Movies",Delta Movies
http://127.0.0.1:8765/tracks.mkv
M3U

"$RUN" reap >/dev/null 2>&1
"$RUN" --detach --serve --open --timeout 0 --playlist "$FIX/m3.m3u" >/dev/null 2>&1 || { echo "harness did not start"; exit 2; }
wait_gf 'g["rows"]' 4 80 || { fail "startup" "guide never showed 4 rows: $(ipc state | head -c 400)"; exit 1; }
ipc mode >/dev/null   # search -> list

# ---- H: hidden groups
[[ $(gf 'g["scopeKinds"]') == '["favorites:Favorites", "all:All", "header:GROUPS", "group:News", "group:Religious", "group:Movies"]' ]] \
  && pass "H1 column lists the groups, nothing hidden" || fail "H1" "$(gf 'g["scopeKinds"]')"
ipc setScope "g:Religious" >/dev/null; sleep 0.3
ipc remove >/dev/null; sleep 0.4
k=$(gf 'g["scopeKinds"]'); a=$(gf '[x for x in g["scopes"] if x.startswith("all=")]'); t=$(gf 'g["footer"]'); sc=$(gf 'g["scopeId"]'); r=$(gf 'g["rows"]')
if [[ $k == '["favorites:Favorites", "all:All", "header:GROUPS", "group:News", "group:Movies", "header:HIDDEN", "hidden:Religious"]' && $a == '["all=2"]' ]]; then pass "H2a Religious moved under HIDDEN, All 4 -> 2"; else fail "H2a" "$k $a"; fi
[[ $t == *"Hid Religious"*"2 channels"*"HIDDEN"* ]] && pass "H2b the transient says what happened and where it went" || fail "H2b" "$t"
[[ $sc == '"g:Religious"' && $r == 2 ]] && pass "H2c the scope stays on the group, its rows still there" || fail "H2c" "$sc $r"
shot m3-hidden
ipc setScope all >/dev/null; sleep 0.2
[[ $(gf 'g["rows"]') == 2 ]] && pass "H3a All is two rows" || fail "H3a" "$(gf 'g["rows"]')"
ipc query faith >/dev/null; sleep 0.3
[[ $(gf 'g["rows"]') == 0 ]] && pass "H3b search from All does not find a hidden channel" || fail "H3b" "$(gf 'g["rows"]')"
ipc query "" >/dev/null; sleep 0.2
disk=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])).get("hiddenGroups")))' "$STATE" 2>/dev/null)
[[ $disk == '["Religious"]' ]] && pass "H4 the name is on disk" || fail "H4" "$disk"
ipc setScope "g:Religious" >/dev/null; sleep 0.2
[[ $(gf 'g["rows"]') == 2 ]] && pass "H5a the hidden group is still a scope with its rows" || fail "H5a" "$(gf 'g["rows"]')"
ipc remove >/dev/null; sleep 0.4
k=$(gf 'g["scopeKinds"]'); h=$(gf 'g["hiddenGroups"]'); t=$(gf 'g["footer"]')
[[ $k == '["favorites:Favorites", "all:All", "header:GROUPS", "group:News", "group:Religious", "group:Movies"]' && $h == '[]' ]] && pass "H5b x on it brings it back" || fail "H5b" "$k $h"
[[ $t == *"Showing Religious"* ]] && pass "H5c and says so" || fail "H5c" "$t"
# H6: the real key. Cursor is on Bravo in g:Religious (list mode).
"$RUN" key x >/dev/null 2>&1; sleep 0.5
[[ $(gf 'g["hiddenGroups"]') == '["Religious"]' ]] && pass "H6a a real x through the catcher hides" || fail "H6a" "$(gf 'g["hiddenGroups"]')"
"$RUN" key x >/dev/null 2>&1; sleep 0.5
[[ $(gf 'g["hiddenGroups"]') == '[]' ]] && pass "H6b and a second real x unhides" || fail "H6b" "$(gf 'g["hiddenGroups"]')"

# ---- T: the picker, against a real mpv
ipc setScope all >/dev/null; sleep 0.2
ipc activate true >/dev/null
wait_sf 's["playerUp"]' true 80 || fail "T0" "player never came up: $(ipc state | head -c 600)"
sleep 1.5
raw=$(python3 "$PLUGIN_ROOT/bin/omarchy-iptv" player tracks --socket "$SOCK" 2>/dev/null | tail -n 1)
ids=$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(json.dumps([t["type"]+str(t["id"])+("*" if t["selected"] else "") for t in d["tracks"]]), d["running"])' "$raw" 2>/dev/null)
[[ $ids == '["audio1*", "audio2", "sub1"] True' ]] && pass "T1a the helper lists the real player's three tracks" || fail "T1a" "$ids"
[[ $raw != *external-filename* && $raw == *"English commentary"* ]] && pass "T1b the reply carries the title and no filename field" || fail "T1b" "$raw"
ipc listKey t >/dev/null
wait_sf 's["tracksState"]' '"ready"' 40 || fail "T2" "tracks never ready: $(sf 's')"
rows=$(gf 'g["trackRows"]'); cur=$(gf 'g["trackCursor"]'); name=$(gf 'g["trackCursorName"]'); intr=$(gf 'g["inTracks"]')
[[ $intr == true && $rows == '["header:Audio", "track:English commentary*", "track:Spanish", "header:Subtitles", "track:Off*", "track:English"]' ]] && pass "T2a t opens the picker on what mpv reported" || fail "T2a" "$intr $rows"
[[ $cur == 1 && $name == '"English commentary, English, aac, audio, selected, 1 of 4"' ]] && pass "T2b the cursor opens on the selected audio track, named for the bus" || fail "T2b" "$cur $name"
shot m3-tracks
ipc trackMove 1 >/dev/null; sleep 0.2
[[ $(gf 'g["trackCursor"]') == 2 ]] && pass "T3a j moves to Spanish" || fail "T3a" "$(gf 'g["trackCursor"]')"
ipc trackSelect >/dev/null
wait_sf 's["tracks"]' '["audio1", "audio2*", "sub1"]' 40 && pass "T3b Enter: the panel shows mpv switched to Spanish" || fail "T3b" "$(sf 's["tracks"]')"
raw=$(python3 "$PLUGIN_ROOT/bin/omarchy-iptv" player tracks --socket "$SOCK" 2>/dev/null | tail -n 1)
[[ $raw == *'"id": 2, "type": "audio", "selected": true'* ]] && pass "T3c and the real player agrees, asked separately" || fail "T3c" "$raw"
[[ $(gf 'g["trackCursor"]') == 2 ]] && pass "T3d the cursor stayed on what was chosen" || fail "T3d" "$(gf 'g["trackCursor"]')"
ipc trackMove 1 >/dev/null; ipc trackMove 1 >/dev/null; sleep 0.2
[[ $(gf 'g["trackCursor"]') == 5 ]] && pass "T4a two more j: past Off to the subtitle" || fail "T4a" "$(gf 'g["trackCursor"]')"
ipc trackSelect >/dev/null
wait_sf 's["tracks"]' '["audio1", "audio2*", "sub1*"]' 40 && pass "T4b the subtitle turns on" || fail "T4b" "$(sf 's["tracks"]')"
[[ $(gf 'g["trackRows"]') == *'"track:Off"'*'"track:English*"'* ]] && pass "T4c Off is no longer marked" || fail "T4c" "$(gf 'g["trackRows"]')"
ipc trackMove -1 >/dev/null; sleep 0.2; ipc trackSelect >/dev/null
wait_sf 's["tracks"]' '["audio1", "audio2*", "sub1"]' 40 && pass "T4d Off turns it off" || fail "T4d" "$(sf 's["tracks"]')"
# T5: real keys through the catcher
"$RUN" key -k Escape >/dev/null 2>&1; sleep 0.4
[[ $(gf 'g["inTracks"]') == false && $(gf 'g["mode"]') == '"list"' ]] && pass "T5a a real Esc closes the picker to the list" || fail "T5a" "$(gf 'g["mode"]')"
"$RUN" key t >/dev/null 2>&1; sleep 0.6
[[ $(gf 'g["inTracks"]') == true ]] && pass "T5b a real t reopens it" || fail "T5b" "$(gf 'g["mode"]')"
wait_sf 's["tracksState"]' '"ready"' 40
c0=$(gf 'g["trackCursor"]'); "$RUN" key j >/dev/null 2>&1; sleep 0.3; c1=$(gf 'g["trackCursor"]')
[[ $c0 == 2 && $c1 == 4 ]] && pass "T5c reopened on the selected track (Spanish); a real j steps over the header to Off" || fail "T5c" "$c0 -> $c1"
"$RUN" key t >/dev/null 2>&1; sleep 0.4
[[ $(gf 'g["inTracks"]') == false ]] && pass "T5d a real t closes it" || fail "T5d" "$(gf 'g["mode"]')"
ipc stop >/dev/null; sleep 0.8
[[ $(sf 's["tracksState"]') == '"idle"' && $(sf 's["tracks"]') == '[]' ]] && pass "T6a stop clears the tracks" || fail "T6a" "$(sf 's["tracksState"]') $(sf 's["tracks"]')"
ipc listKey t >/dev/null; sleep 0.3
[[ $(gf 'g["inTracks"]') == false && $(gf 'g["footer"]') == *"Nothing is playing"* ]] && pass "T6b t while idle says nothing is playing" || fail "T6b" "$(gf 'g["inTracks"]') $(gf 'g["footer"]')"

# ---- P: the 0.9.0 preflight repairs, each against the defect it fixes.
#
# A CHANNEL CHANGE HERE IS `ipc play <id>`, NEVER `zap` and never the cursor.
# The first draft used zap and both of its checks were VACUOUS: the ring is
# the playing channel's own group (launchScope), that group had one member,
# so zap was a no-op, no loadfile happened, and "the tracks did not change"
# passed for a reason with nothing to do with what was being tested. The
# second draft moved the cursor and activated, and the channel did not
# change either. Naming the id removes the question.
ipc setScope all >/dev/null; sleep 0.3
ipc move 0 >/dev/null; sleep 0.2
"$RUN" key x >/dev/null 2>&1; sleep 0.6   # cursor is on Alpha News in All
hid=$(gf 'g["hiddenGroups"]')
[[ $hid == '["News"]' ]] && pass "P1a x in All hides the cursor row group" || fail "P1a" "$hid"
rows=$(gf 'g["rows"]')
[[ $rows == 3 ]] && pass "P1b All drops to the three remaining channels" || fail "P1b" "$rows"
ipc setScope "g:News" >/dev/null; sleep 0.3
ipc remove >/dev/null; sleep 0.5
hid=$(gf 'g["hiddenGroups"]')
[[ $hid == '[]' ]] && pass "P1c and unhiding from the HIDDEN entry restores it" || fail "P1c" "$hid"

# P2 the picker survives a channel change instead of claiming nothing plays
ipc setScope all >/dev/null; sleep 0.3
ipc play t:alpha >/dev/null
wait_sf 's["playerUp"]' true 80 || fail "P2-setup" "no player"
for i in $(seq 1 40); do [[ $(sf 's["nowPlaying"]["id"]') == '"t:alpha"' ]] && break; sleep 0.25; done
sleep 1.5
ipc listKey t >/dev/null
wait_sf 's["tracksState"]' '"ready"' 40 || fail "P2-setup" "tracks not ready"
ipc play t:charlie >/dev/null
for i in $(seq 1 40); do [[ $(sf 's["nowPlaying"]["id"]') == '"t:charlie"' ]] && break; sleep 0.25; done
now=$(sf 's["nowPlaying"]["id"]')
[[ $now == '"t:charlie"' ]] && pass "P2a the channel really changed under the open picker" || fail "P2a" "$now"
wait_sf 's["tracksState"]' '"ready"' 60 && pass "P2b the open picker re-asked the player" || fail "P2b" "$(sf 's[\x27tracksState\x27]')"
msg=$(gf 'g["trackMessage"]'); intr=$(gf 'g["inTracks"]')
[[ $intr == true && $msg == '""' ]] && pass "P2c the panel stays open and claims nothing false" || fail "P2c" "$intr $msg"

# P3 a channel change resets the track choice (mpv keeps aid/sid otherwise)
ipc trackMove 1 >/dev/null; sleep 0.3; ipc trackSelect >/dev/null
wait_sf 's["tracks"]' '["audio1", "audio2*", "sub1"]' 40 || fail "P3-setup" "selection did not take"
ipc play t:alpha >/dev/null
for i in $(seq 1 40); do [[ $(sf 's["nowPlaying"]["id"]') == '"t:alpha"' ]] && break; sleep 0.25; done
wait_sf 's["tracksState"]' '"ready"' 60 || fail "P3-setup" "not ready after the change"
tr=$(sf 's["tracks"]')
[[ $tr == '["audio1*", "audio2", "sub1"]' ]] && pass "P3 the track choice did not follow the channel, as the README says" || fail "P3" "$tr"
"$RUN" key -k Escape >/dev/null 2>&1; sleep 0.3

echo "m3-scenario: $PASS passed, $FAIL failed"
(( FAIL == 0 ))
