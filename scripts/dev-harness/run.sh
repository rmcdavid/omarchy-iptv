#!/bin/bash
# scripts/dev-harness/run.sh -- smoke-test the plugin without installing it.
#
#   run.sh [options]                 start the harness (foreground, killed after --timeout)
#   run.sh ipc <fn> [args...]        call the running harness (IpcHandler target "harness")
#   run.sh plugin-ipc <fn> [args...] call the PLUGIN's own IpcHandler inside the harness
#                                    (target io.github.rmcdavid.iptv): toggle, stop, next,
#                                    previous, refresh, play, channel, pip, pause, back,
#                                    forward, live -- the verbs a user binds (F-RWD-14)
#   run.sh shot [--any-surface] [name]
#                                    screenshot the focused output into the scratch dir.
#                                    REFUSES, exit 3, unless the harness guide holds the
#                                    keyboard (F-HARNESS-12); --any-surface, first, is the
#                                    deliberate shot of whatever is up (the player window)
#   run.sh key [--to-compositor] <wtype args...>
#                                    send keys to the guide (wtype). REFUSES, exit 3,
#                                    unless the harness guide holds the keyboard, and
#                                    always refuses while hyprlock is up (F-M3-1)
#   run.sh type <text>               type text and PROVE it arrived (F-HARNESS-1). Same
#                                    two refusals; no --to-compositor (see below)
#   run.sh clean                     wipe the scratch dirs (cache, state, runtime)
#   run.sh scenario                  scripted Sources verification (sources-scenario.sh)
#   run.sh player-scenario           scripted detached-player verification (player-scenario.sh)
#   run.sh restart-shell             kill the detached harness shell and start a new one with
#                                    the same environment, leaving the player alone (M2-02)
#   run.sh shell-stop                SIGTERM the detached harness shell and wait for it
#   run.sh reap                      kill the detached shell, the fixture server and the
#                                    harness player (what the foreground EXIT trap does)
#
# Options for start:
#   --open              open the guide right after load
#   --timeout N         kill quickshell after N seconds (default 15; 0 = no limit)
#   --playlist SRC      playlist URL/path (default: generated fixture with dead local URLs; "none" = unconfigured)
#   --epg URL           EPG URL (default: none)
#   --source2 SRC       seed the source history (state.json v2) with a second, never-fetched
#                       source before start (helper `state source add`); printed as scheme://host
#   --serve             serve a generated test video on 127.0.0.1:8765 and point the
#                       fixture's "Harness Live" channel at it (exercises the mpv path locally)
#   --fake-epg          drop a synthetic epg-now.json into the scratch cache (guide EPG rows)
#   --vertical          fake a vertical bar
#   --no-name           showChannelName=false
#   --label-max N       barLabelMaxWidth
#   --order ORDER       channelOrder: playlist (default) or number (M2-03)
#   --entry-ms N        numberEntryMs, the channel-number entry timeout
#   --no-bar-number     barShowChannelNumber=false
#   --keep              keep the scratch cache/state between runs (default wipes cache+state)
#   --seed-cache DIR    after the default wipe, copy DIR's contents into the scratch cache
#                       (XDG_CACHE_HOME), so a COLD shell starts over a cache the caller chose
#                       while the plugin's own cache and state are wiped as usual. What it is
#                       for (F-HARNESS-44): a mesa shader cache warmed once by a throwaway
#                       shell, so a cold open pays the plugin's cold costs and not llvmpipe's
#                       shader JIT. Prints what it seeded (files, bytes). Not with --keep: the
#                       two are the same lever, and the start refuses both
#   --detach            start in the background and return (no EXIT trap): the shell survives
#                       this invocation, which is what `restart-shell` needs. Reap with `reap`.
#   --instance NAME     a second config root (root<NAME>) sharing the same cache / state /
#                       runtime dirs: two services, one runtime directory, one player
#   --window MODE       layer (default): the production PanelWindow + layer-shell. floating: host
#                       the guide in a FloatingWindow (xdg toplevel) so it maps under a compositor
#                       with no layer-shell, e.g. headless cage (docs/SPIKE-CAGE-HEADLESS.md). Harness-only.
#   --source-key KEY    seed `sourceKey` on the bar entry at KEY ("" allowed), the mirror the
#                       plugin writes since D-SINK-19; absent, the entry carries no such key, which
#                       is the 0.13.5 shape. With --playlist it presents the entry a host holds
#                       after `omarchy bar set ... playlistUrl` while the shell was down
#   --host MODE         lag (default): the fake host publishes barConfig one write behind, as
#                       every Omarchy through 4.0.4 does. echo: it publishes what it stores at
#                       once, as omacom/omarchy#15082 does (D-HOST-4's lever; rule 9 names both)
#
# Why `key` and `type` refuse (F-M3-1 half (a)). wtype types into whatever
# surface holds the keyboard, which on a bad day is the terminal the scenario is
# running in, the editor behind it, or -- worst -- a lock prompt, where every
# keystroke registers as a failed unlock attempt. NEITHER failure is visible in
# a scenario's own assertions: a key that landed somewhere else reads exactly
# like a guide that did not react, and `sky` arriving as `ky` still filters 20
# rows to 3. So both verbs ask the harness where the keyboard is first
# (`ipc focusState`) and exit 3 naming what they found. Two kinds of refusal:
#   hyprlock is up      -- never escapable, no flag, nothing to pass.
#   the guide has not got the keyboard -- escapable with --to-compositor, which
#     must come FIRST (everything after it is wtype's, and wtype's own `--`
#     means "the rest is text") and exists for a chord aimed at the COMPOSITOR
#     rather than at a surface. It is not a way to make a failing scenario pass.
# `type` has no escape hatch: it proves the text reached the GUIDE by reading it
# back, so a keystroke aimed at the compositor has nothing for it to prove.
# The compositor cannot answer "who holds the keyboard" at all -- `hyprctl
# layers` has no such field and `hyprctl activewindow` names a toplevel while
# an overlay is taking keys -- so the question goes to the guide. The numbers
# behind that are in scripts/dev-harness/shell.qml, at harness.focusSnapshot.
# "The guide has the keyboard" is TWO observations since F-M3-24 (2026-10-26),
# and the first alone was not true: an item inside the guide holds Qt's
# activeFocus (`keyboard`), AND the guide's window is active (`windowActive`,
# Qt's Window.active, which follows the compositor's keyboard enter/leave).
# Under a headless cage, which has no layer-shell, the production guide
# window never maps; its key catcher still read activeFocus true, the guard
# passed, and every real key went to nothing or to the player's window
# (mpv's sub-delay moved). A false `windowActive` refuses with the tag
# $QA_KEY_WINDOW_INACTIVE in the message, which is the one refusal a
# scenario may report as SKIP (qa_key); a missing one refuses as "cannot
# tell". UNVERIFIED on the live desktop: that Hyprland's exclusive keyboard
# focus on the guide's layer surface reads windowActive true has been read
# in Qt's activation path, not observed, because this lane may not open a
# window there; the first desk run of a keyed scenario observes it.
#
# Environment: OMARCHY_IPTV_PLUGIN_ROOT overrides which checkout the harness
# loads Service.qml / Guide.qml / BarWidget.qml / bin/omarchy-iptv from
# (default: this repo). That is how a scenario is run against pre-change code
# to prove it fails there before it counts as evidence (CLAUDE.md rule 10).
# OMARCHY_IPTV_HARNESS_KEEP_DISPLAY=1 keeps the caller's DISPLAY for what this
# starts, on the desk only; by default it is dropped, and so is
# HYPRLAND_INSTANCE_SIGNATURE when WAYLAND_DISPLAY is a nested compositor
# (F-HARNESS-47; harness_env says why).
#
# Everything lives under $OMARCHY_IPTV_HARNESS_DIR (default $XDG_RUNTIME_DIR/omarchy-iptv-harness):
#   root/     scratch Quickshell config root: shell.qml + Commons/ Ui/ symlinks (the `qs` prefix)
#   home/     HOME            -> home/.config/omarchy/shell.json, seeded 0644 (D-SINK-18), and
#                                a COPY of the two theme files the host palette reads
#                                (F-HARNESS-20; see harness_env and qa_harness_home)
#             XDG_CONFIG_HOME -> home/.config, XDG_DATA_HOME -> home/.local/share
#   cache/    XDG_CACHE_HOME  -> cache/omarchy-iptv/{channels,playlist-status,epg-now}.json
#   state/    XDG_STATE_HOME  -> state/omarchy-iptv/state.json
#   runtime/  XDG_RUNTIME_DIR -> runtime/omarchy-iptv/mpv.sock (and no hypr/: prepare_root says why, F-HARNESS-48)
#   fixtures/ generated playlist / test.ts (MPEG-TS, like a live stream; an MP4 with a trailing moov is not seekable over HTTP)
#   qs<N>.pid, server.pid  the detached shell's and the fixture server's RECORDED pids: what
#             `reap` and the EXIT trap end, by pid, with TERM then KILL (F-HARNESS-32);
#             nothing here is ended by a `pkill -f` pattern
# Never run against a real network stream from here; the fixture uses 127.0.0.1 only.
# The playlist/EPG URL is never printed (it may carry credentials); only
# scheme://host is echoed (S-08). Everything this script starts (fixture
# HTTP server, Quickshell, the harness mpv) is reaped by an EXIT trap, so a
# Ctrl-C or SIGTERM leaves nothing behind; SIGKILL cannot be trapped, so the
# next start also reaps a stale fixture server.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
die() { echo "[run.sh] $*" >&2; exit 2; }
# Which checkout the plugin QML and the helper come from. Defaults to this
# repo; a scenario points it at an exported pre-change tree to show a check
# failing there first.
# C3: this file has no `set -e`, so a failed `cd` left PLUGIN_ROOT EMPTY and
# every later "$PLUGIN_ROOT/bin/omarchy-iptv" and "$PLUGIN_ROOT/Model.js"
# silently became a path at /. Nothing checked it.
PLUGIN_ROOT=$(cd "${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}" 2>/dev/null && pwd)
[[ -n $PLUGIN_ROOT ]] || die "OMARCHY_IPTV_PLUGIN_ROOT=${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT} is not a directory I can enter"
# D-REL-5: Model.mjs and model/ since the split; a --baseline tree from before
# it carries the one-file Model.js, and either is a plugin tree.
qa_model_files "$PLUGIN_ROOT" >/dev/null \
  || die "$PLUGIN_ROOT holds no readable model (Model.mjs and its parts, or a pre-split Model.js); that is not a plugin tree"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-harness}
SHELL_DIR=${OMARCHY_PATH:-/usr/share/omarchy}/shell
SERVE_PORT=8765
SERVER_PID=""
QS_PID=""
INSTANCE=${OMARCHY_IPTV_HARNESS_INSTANCE:-}
KEEP_PLAYER=0

# scheme://host of a source URL, "local file" for a path, "(none)" when unset.
source_label() {
  local src=$1 re='^([A-Za-z][A-Za-z0-9+.-]*)://([^@/?#]*@)?([^/:?#]+)'
  if [[ -z $src ]]; then
    echo "(none)"
  elif [[ $src =~ $re ]]; then
    local scheme=${BASH_REMATCH[1],,}
    if [[ $scheme == file ]]; then echo "local file"; else echo "$scheme://${BASH_REMATCH[3]}"; fi
  else
    echo "local file"
  fi
}

fixture_server_pattern() {
  echo "http.server $SERVE_PORT --bind 127.0.0.1 --directory $SCRATCH/fixtures"
}

# The config root of this instance ("" = the default one) and its pid file.
qs_root()    { echo "$SCRATCH/root$INSTANCE"; }
qs_pidfile() { echo "$SCRATCH/qs$INSTANCE.pid"; }

# The PLUGIN's own IpcHandler target, as opposed to `harness`, which is
# shell.qml's: the verbs a user binds (`toggle`, `channel`, `pause`, `back`).
# SPIKE-LIVE-REWIND 12.5 measured what reaching it inside the harness costs --
# the scratch runtime directory AND the absolute Wayland socket path, which is
# exactly what harness_env already exports -- and said run.sh should carry it
# so a scenario does not. F-RWD-14.
#
# The string is joined to two other files by a NAME, with nothing calling it:
# `manifest.json`'s `id`, which the production Service.qml reads into
# `pluginId`, and `shell.qml`'s own `pluginId` literal, which is what the
# harness actually registers. The manifest half is CHECKED below rather than
# trusted. The shell.qml half cannot be read from here without grepping QML
# for a literal, and its failure mode is loud anyway: `qs ipc` refuses a
# target it cannot find instead of answering for the wrong one.
PLUGIN_TARGET="io.github.rmcdavid.iptv"
# Prints the target, or fails with the disagreement named. An UNREADABLE
# manifest falls back to the literal rather than failing, because that is what
# Service.qml's own `pluginId` does (`manifest && manifest.id ? ... : "<lit>"`)
# and a test double -- which is what the harness is -- must not be stricter
# than the thing it stands in for any more than it may be more forgiving.
plugin_target() {
  local id
  id=$(python3 -c 'import json, sys
try:
    print(json.load(open(sys.argv[1])).get("id", ""))
except Exception:
    print("")' "$PLUGIN_ROOT/manifest.json" 2>/dev/null)
  if [[ -n $id && $id != "$PLUGIN_TARGET" ]]; then
    echo "[run.sh] $PLUGIN_ROOT/manifest.json says the plugin id is '$id', this script says '$PLUGIN_TARGET'." >&2
    echo "[run.sh] One of them is the IpcHandler target and run.sh cannot guess which; fix PLUGIN_TARGET here and shell.qml's pluginId together." >&2
    return 2
  fi
  printf '%s\n' "$PLUGIN_TARGET"
}

# The player is a setsid'd grandchild of the helper now (M2-02), so it is not
# in any process group this script owns: it is reaped by its command line,
# which names THIS scratch socket and can never match the live session's
# (qa_reap_players: `pgrep -x mpv`, then the `input-ipc-server=` argument).
# F-HARNESS-30 (R26h, 2026-10-16): TERM, a bounded wait, then KILL by pid and
# a final look -- qa_reap_players (scripts/qa-lib.sh), never `pkill -f` with
# TERM alone. A served player under a cage that is going away ignores TERM:
# phase 1 of the R26 work left six of them spinning for 35-48 minutes at
# 42-52 % of a core each. Every scenario that ends with `run.sh reap`, and
# run.sh's own exit, comes through here. The helper's own `player stop` is a
# different path and already escalates to SIGKILL (the D-LIVE-17 ladder).
reap_player() {
  local dir=$SCRATCH reply rung pid
  [[ $dir == /* ]] || dir=$PWD/$dir
  # F-HARNESS-45: the designed door FIRST. `player stop` over THIS harness's
  # socket runs the D-LIVE-17 ladder inside the helper -- quit over IPC,
  # SIGTERM at 2 s, SIGKILL at 4 s, each against the pid the helper finds by
  # the socket token in argv and re-verifies before signalling -- and
  # reports the rung that ended it; a player that answers IPC leaves on the
  # quit and is signalled by nobody. The sweep below stays as the backstop
  # for a player the helper cannot see or a stop that did not run (no
  # helper, or a part the stub refused): it ends nothing twice, because a
  # pid the ladder ended is no longer there to match. Bounded by the
  # ladder's own timeline plus `timeout`'s word. scripts/qa-lib-test.sh
  # drives this against a stand-in that records which door ended it.
  reply=$(timeout -k 2 20 python3 "$PLUGIN_ROOT/bin/omarchy-iptv" player stop --socket "$dir/runtime/omarchy-iptv/mpv.sock" 2>/dev/null)
  rung=$(qa_json_field "d['rung']" "$reply" 2>/dev/null); pid=$(qa_json_field "d['pid']" "$reply" 2>/dev/null)
  [[ $rung =~ ^(quit|term|kill)$ ]] && echo "[run.sh] player stop over the socket ended pid $pid at rung $rung" >&2
  qa_reap_players "$dir"
  return 0
}

# F-HARNESS-32. The fixture server's pid, RECORDED when start_server starts
# it (its own direct child, no setsid, so `$!` is the listener and not a
# wrapper) in $SCRATCH/server.pid, which is how `reap` in a LATER invocation
# can end it by pid rather than by the `pkill -f` pattern that used to sit
# here. The pid is trusted only while its command line still carries this
# scratch directory's server pattern (qa_cmdline), so a recycled pid is never
# signalled -- the still_the_player discipline, one process over.
server_pidfile() { echo "$SCRATCH/server.pid"; }
stop_recorded_server() {
  local pidfile pid cmd; pidfile=$(server_pidfile)
  pid=$(cat "$pidfile" 2>/dev/null)
  if [[ -n $pid ]] && cmd=$(qa_cmdline "$pid") && [[ $cmd == *"$(fixture_server_pattern)"* ]]; then
    qa_stop_pid "$pid" 5 "fixture server"
  fi
  rm -f "$pidfile"
  return 0
}

cleanup() {
  # F-HARNESS-32: by recorded pid, TERM then KILL after a bound (qa_stop_pid,
  # scripts/qa-lib.sh), never a `pkill -f` pattern -- what this did not
  # start it cannot end. The foreground shell sits under `timeout`, so the
  # quickshell beneath it is found by PARENT and exact name (never `-f`) and
  # ended too, or a KILL on the wrapper would orphan it.
  stop_recorded_server
  if [[ -n $QS_PID ]]; then
    local inner; inner=$(pgrep -P "$QS_PID" -x quickshell 2>/dev/null | head -1)
    qa_stop_pid "$QS_PID" 5 "harness shell"
    [[ -n $inner ]] && qa_stop_pid "$inner" 5 "quickshell under the timeout wrapper"
  fi
  # --keep-player is for the restart scenario, which must outlive the shell
  # exactly the way the real player does.
  (( KEEP_PLAYER )) || reap_player
  return 0
}

# D-SINK-18. The scratch stand-in for ~/.config/omarchy/shell.json, seeded at
# the mode the PACKAGED default carries -- 0644, measured off
# /usr/share/omarchy/config/omarchy/shell.json by the lead on 2026-10-09 --
# rather than at the mode this machine happens to hold. The harness's own
# shell.qml models the host config IN MEMORY (persistShellConfig: one deep
# copy, no FileView), so nothing here READS this file; it exists because the
# service runs the helper's `config shield` at every start, the helper
# computes that file from $HOME exactly as the host does (host_config_path),
# and the shield needs a container to act on. It sits under the harness's own
# HOME (F-HARNESS-20): until then it sat under XDG_CONFIG_HOME, which the
# shield IGNORES since the D-SINK-18 repair, so the seed was a decoy nothing
# touched while the shield was aimed at the developer's real file. Seeding the
# exposed mode means an ordinary harness run exercises the tightening rather
# than inheriting a pass.
#
# It carries NO playlistUrl and NO epgUrl, which is what lets a scenario tell
# a URL ARRIVING from a URL that was always there.
#
# Re-seeded on every prepare_root so one run cannot inherit the mode the
# previous run's fix left behind, which would make the second run's green
# mean nothing.
seed_scratch_config() {
  local cfg="$SCRATCH/home/.config/omarchy/shell.json"
  mkdir -p "$(dirname "$cfg")" || die "could not create the scratch host config directory"
  printf '%s\n' '{"version":1,"bar":{"layout":{"left":[],"center":[],"right":[{"id":"io.github.rmcdavid.iptv"}]}}}' \
    >"$cfg" || die "could not seed the scratch host config at $cfg"
  chmod 0644 "$cfg" || die "could not seed the scratch host config mode"
  return 0
}

# F-HARNESS-20. The ONE thing the scratch home is given from the real one,
# measured rather than assumed. The host's Color singleton (linked in below as
# qs.Commons) paints from $HOME/.local/state/omarchy/current/theme/colors.toml
# and shell.toml, plus an optional $HOME/.config/omarchy/shell.toml override;
# with HOME moved and nothing provided, the harness would render in Color's
# built-in fallback palette instead of the developer's theme, which is a
# different picture from every run before this one. So those files -- and
# nothing else from the theme directory -- are COPIED, dereferenced, at 0600.
# Never a symlink: a link into the real home is a path by which a write in
# the harness reaches the user's files, and tests/test_harness_home.py asserts
# the scratch home holds none.
# What the harness does NOT need from the real home, measured 2026-10-13 under
# a scratch HOME: fonts (fc-match monospace answers JetBrainsMono Nerd Font
# from /usr/share/fonts and /etc/fonts; this machine has no ~/.local/share/
# fonts, ~/.fonts or ~/.config/fontconfig at all), the Style singleton's
# fontconfig and window-gaps FileViews (both optional and watched, both absent
# here), and mpv's config (the harness player was already kept off the
# developer's ~/.config/mpv by XDG_CONFIG_HOME, and must not pick up a
# legacy ~/.mpv through HOME either).
# Re-seeded on every prepare_root, like the host config, so an edit to the
# copy cannot outlive the run that made it.
seed_scratch_theme() {
  local real src dst f
  [[ -n $SCRATCH && $SCRATCH != / ]] || die "the scratch directory is empty"
  real=$(qa_harness_real_home "$SCRATCH")
  dst="$SCRATCH/home/.local/state/omarchy/current/theme"
  rm -rf "$SCRATCH/home/.local/state/omarchy/current" "$SCRATCH/home/.config/omarchy/shell.toml" \
    || die "could not clear the previous scratch theme"
  [[ -n $real ]] || return 0
  src="$real/.local/state/omarchy/current/theme"
  mkdir -p "$dst" || die "could not create the scratch theme directory"
  for f in colors.toml shell.toml; do
    [[ -f $src/$f ]] || continue
    cp -L -- "$src/$f" "$dst/$f" || die "could not copy the theme's $f"
    chmod 0600 "$dst/$f" || die "could not set the scratch theme's $f mode"
  done
  if [[ -f $real/.config/omarchy/shell.toml ]]; then
    mkdir -p "$SCRATCH/home/.config/omarchy" || die "could not create the scratch host config directory"
    cp -L -- "$real/.config/omarchy/shell.toml" "$SCRATCH/home/.config/omarchy/shell.toml" \
      || die "could not copy the user's shell.toml override"
    chmod 0600 "$SCRATCH/home/.config/omarchy/shell.toml" || die "could not set the shell.toml copy's mode"
  fi
  return 0
}

# C1. Every status here used to be discarded. A failed `cp Model.js` left the
# PREVIOUS run's Model.js in the scratch root while OMARCHY_IPTV_ROOT still
# pointed Service.qml and Guide.qml at the new tree - a silently MIXED tree,
# and on the --baseline path that is rule-11 "evidence" nobody can trust.
# Nothing anywhere verified the copy matched the tree under test.
prepare_root() {
  local root; root=$(qs_root)
  mkdir -p "$root" "$SCRATCH/cache" "$SCRATCH/state" "$SCRATCH/runtime" "$SCRATCH/fixtures" \
    "$SCRATCH/home/.config/omarchy" \
    || die "could not create the scratch tree under $SCRATCH"
  chmod 0700 "$SCRATCH/home" || die "could not make the scratch home private"
  seed_scratch_config
  seed_scratch_theme
  ln -sfn "$SHELL_DIR/Commons" "$root/Commons" || die "could not link $SHELL_DIR/Commons"
  ln -sfn "$SHELL_DIR/Ui" "$root/Ui"           || die "could not link $SHELL_DIR/Ui"
  [[ -e $root/Commons && -e $root/Ui ]]        || die "the qs.Commons / qs.Ui links do not resolve"
  # The harness's own pure logic (entryKey, D-SINK-19 R6), which shell.qml
  # imports beside the model and key-scenario.sh drives from node. It is the
  # harness's file, not the tree under test's, so it is staged from $HERE
  # whatever the model's layout.
  cp "$HERE/harness-lib.js" "$root/harness-lib.js" || die "could not copy harness-lib.js into $root"
  qa_same_file "$HERE/harness-lib.js" "$root/harness-lib.js" \
    || die "$root/harness-lib.js does not match the harness harness-lib.js"
  # The harness masks form values with the plugin's own model (state()), so
  # the model is staged beside shell.qml: every file qa_model_files names --
  # Model.mjs and the parts under model/ since D-REL-5 -- each copied and each
  # compared, after the previous run's copies are removed so a part the tree
  # under test does not have cannot linger. A tree from before the split has
  # the one-file Model.js; the staged shell.qml then imports that name, its
  # one changed line asserted, because the harness shell itself names
  # Model.mjs.
  [[ -n $root && $root != / ]] || die "the scratch config root is empty"
  rm -rf "$root/model" "$root/Model.mjs" "$root/Model.js" || die "could not clear the previous model from $root"
  local -a model_files=()
  local f rel
  mapfile -t model_files < <(qa_model_files "$PLUGIN_ROOT")
  (( ${#model_files[@]} > 0 )) || die "$PLUGIN_ROOT holds no readable model"
  for f in "${model_files[@]}"; do
    rel=${f#"$PLUGIN_ROOT/"}
    mkdir -p "$root/$(dirname "$rel")" || die "could not create $root/$(dirname "$rel")"
    cp "$f" "$root/$rel" || die "could not copy $rel from $PLUGIN_ROOT"
    qa_same_file "$f" "$root/$rel" \
      || die "$root/$rel does not match $PLUGIN_ROOT/$rel: the tree under test is MIXED"
  done
  if [[ ${model_files[0]} == "$PLUGIN_ROOT/Model.mjs" ]]; then
    cp "$HERE/shell.qml" "$root/shell.qml"     || die "could not copy shell.qml into $root"
    qa_same_file "$HERE/shell.qml" "$root/shell.qml" \
      || die "$root/shell.qml does not match the harness shell.qml"
  else
    sed 's#^import "Model.mjs" as Model$#import "Model.js" as Model#' "$HERE/shell.qml" >"$root/shell.qml" \
      || die "could not stage shell.qml for a pre-split tree"
    [[ $(diff "$HERE/shell.qml" "$root/shell.qml" | grep -c '^[<>]') == 2 ]] \
      || die "$root/shell.qml differs from the harness shell.qml by more than its model import"
  fi
  # F-HARNESS-48 (2026-10-26): NO `runtime/hypr`. hyprctl and Quickshell's
  # Hyprland module find an instance at $XDG_RUNTIME_DIR/hypr/<signature>/,
  # and this script used to link the scratch runtime's `hypr` to the real
  # one "so hyprctl works". It never did at the default harness directory:
  # through the link the socket path is 123 bytes, past sun_path's 108, so
  # hyprctl could not connect (exit 4, measured read-only by lane-fm324);
  # through a 106-byte path it answered the owner's live Hyprland 0.56.2. A
  # link that works only by accident of a path's length is a bridge to the
  # owner's compositor for any shorter OMARCHY_IPTV_HARNESS_DIR, and
  # nothing here needs it: the harness's real-compositor calls (`shot`'s
  # `hyprctl monitors`) run in run.sh's own environment, never under this
  # runtime directory, and every scenario that exercises the service's
  # hyprctl puts stub-hyprctl.py on $SCRATCH/bin. A link left by an older
  # run.sh is removed, so an existing scratch tree loses it too.
  # tests/test_harness_display.py connects through the path it used to make.
  if [[ -L $SCRATCH/runtime/hypr ]]; then
    rm -f -- "$SCRATCH/runtime/hypr" || die "could not remove the stale $SCRATCH/runtime/hypr link"
  fi
  [[ -e $SCRATCH/runtime/hypr ]] && die "$SCRATCH/runtime/hypr exists and is not the link an older run.sh made; refusing to start a harness that could find a compositor there"
  return 0
}

# The scratch cache between prepare_root and the shell's start: wiped (the
# default), kept (--keep), or wiped and then SEEDED from a directory
# (--seed-cache DIR, F-HARNESS-44). The seed is copied with its modes and
# times, and what landed is printed -- a count and a byte total, read back
# from the scratch and not from the source -- so a scenario's transcript
# records it. tests/test_harness_shader_seed.py runs this function over a
# decoy scratch and asserts the plugin's cache is gone, the stale shader
# cache is gone, and the seed is present byte for byte.
reset_scratch_cache() {
  local files bytes
  if (( KEEP )); then
    echo "[run.sh] cache kept"
    return 0
  fi
  rm -rf "$SCRATCH/cache" "$SCRATCH/state" "$SCRATCH/runtime/omarchy-iptv" \
    || die "could not wipe the scratch cache and state under $SCRATCH"
  mkdir -p "$SCRATCH/cache" "$SCRATCH/state" || die "could not re-create the scratch cache and state"
  if [[ -z ${SEED_CACHE:-} ]]; then
    echo "[run.sh] cache wiped"
    return 0
  fi
  cp -a -- "$SEED_CACHE/." "$SCRATCH/cache/" || die "could not seed the scratch cache from $SEED_CACHE"
  files=$(find "$SCRATCH/cache" -type f | wc -l)
  bytes=$(find "$SCRATCH/cache" -type f -printf '%s\n' | awk '{ b += $1 } END { print b + 0 }')
  echo "[run.sh] cache seeded from $SEED_CACHE: $files files, $bytes bytes"
  return 0
}

# Start quickshell in its own session so it survives this invocation, and
# record the pid. Used by --detach and by restart-shell; the environment is
# whatever the caller exported (start writes it to last-start.env).
start_detached_shell() {
  local root; root=$(qs_root)
  setsid quickshell -p "$root" >>"$SCRATCH/harness$INSTANCE.log" 2>&1 &
  QS_PID=$!
  echo "$QS_PID" >"$(qs_pidfile)"
  echo "[run.sh] detached shell pid $QS_PID (log $SCRATCH/harness$INSTANCE.log)"
}

# SIGTERM the detached shell and wait for it to go. This is what
# `omarchy restart shell` does to the real one: `quickshell kill` asks it to
# exit, and nothing is sent to the player.
stop_detached_shell() {
  local pidfile pid; pidfile=$(qs_pidfile)
  pid=$(cat "$pidfile" 2>/dev/null)
  [[ -n $pid ]] || { rm -f "$pidfile"; return 0; }
  # F-HARNESS-32: the TERM / bounded wait / KILL ladder that sat inline here
  # is qa_stop_pid now (scripts/qa-lib.sh), shared with the fixture server
  # and the foreground shell. The pid is the one start_detached_shell
  # recorded, and ONLY that: the `pgrep -f` fallback for a shell with no pid
  # file is gone, because a shell this script did not record is one it
  # cannot tell from another harness's. The shell is not our child (an
  # earlier invocation started it), which is why the ladder polls `kill -0`
  # and never `wait`s.
  qa_stop_pid "$pid" 5 "detached harness shell"
  rm -f "$pidfile"
  return 0
}

harness_env() {
  # The scratch runtime dir replaces XDG_RUNTIME_DIR, so hand libwayland the
  # absolute socket path (it accepts one) and keep the real DBus address.
  local wl=${WAYLAND_DISPLAY:-wayland-1}
  [[ $wl == /* ]] || wl="$REAL_RUNTIME/$wl"
  # F-HARNESS-47 and -48 (2026-10-26). Nothing this script starts -- the
  # shell, the helper the service spawns, the player the helper forks -- may
  # inherit a display or a compositor IPC that is not the harness's own
  # target, and the target is WAYLAND_DISPLAY. Decided here, on the caller's
  # target, before anything below rewrites the runtime directory.
  #
  # DISPLAY is dropped ALWAYS. A caged run used to inherit the caller's
  # `:0`, the owner's Xwayland, and mpv's VO probe tries `x11vk` after
  # `waylandvk` loses its surface (QA-RESULTS "F-HARNESS-45"), so a player
  # started toward a cage could map its window on the owner's real desktop.
  # Nothing in the harness or the plugin needs an X display, searched
  # 2026-10-26: no DISPLAY, x11, Xwayland, xdotool, xprop, xclip, xsel or
  # xrandr in Service.qml, Guide.qml, BarWidget.qml, bin/helper/ or model/
  # (only the D-PLY-27 comments that describe mpv's probe); the launch argv
  # is Wayland-first (`--wayland-app-id`, and `--gpu-sw=yes` since D-PLY-27);
  # the harness's own tools are wtype, grim, wl-copy and hyprctl; the
  # session's QT_QPA_PLATFORM is `wayland;xcb`, so without DISPLAY the xcb
  # fallback has no screen to open behind a Wayland failure. The one way to keep it is
  # OMARCHY_IPTV_HARNESS_KEEP_DISPLAY=1, honoured only when the target is the
  # session's own compositor (on a nested one the caller's DISPLAY is by
  # construction another display, so asking is refused, not ignored).
  #
  # HYPRLAND_INSTANCE_SIGNATURE is dropped when the target is NESTED
  # (qa_target_nested, scripts/qa-lib.sh: anything but the socket the
  # signature's own lock file names). It is what points hyprctl and
  # Quickshell's Hyprland module at a compositor, and a cage is not one. On
  # the desk it stays: there the target IS that instance.
  #
  # Belt and braces, on purpose: the five cage `h()` lines (key-, logo-,
  # open-, clip-scenario and spikes/first-open) still say `env -u
  # HYPRLAND_INSTANCE_SIGNATURE`, the cage starters `env -u DISPLAY`, and the
  # rigs both. With this function dropping both for a nested target those
  # are no longer the containment, and they stay as a second layer.
  # tests/test_harness_display.py drives this function and reads both.
  local nested=0
  qa_target_nested "$wl" "$REAL_RUNTIME" && nested=1
  (( nested )) && unset HYPRLAND_INSTANCE_SIGNATURE
  if [[ ${OMARCHY_IPTV_HARNESS_KEEP_DISPLAY:-0} == 1 ]]; then
    (( nested )) && die "OMARCHY_IPTV_HARNESS_KEEP_DISPLAY=1, and the target $wl is not the session's own compositor: the caller's DISPLAY is another display than the one this harness drives (F-HARNESS-47). Keep it only on the desk."
  else
    unset DISPLAY
  fi
  export WAYLAND_DISPLAY="$wl"
  export XDG_RUNTIME_DIR="$SCRATCH/runtime"
  # F-HARNESS-45 (2026-10-25): a player under a nested headless cage. mpv
  # 0.41.0's automatic VO probe ABORTS on a compositor that can serve no
  # hardware GL or Vulkan context: `waylandvk` loses its surface, `x11vk`
  # fails -- with the cage's lazy Xwayland (no DRI3) or with no DISPLAY at
  # all -- the wayland EGL context comes up on llvmpipe and is refused as a
  # software renderer WITHOUT releasing its Wayland state, whose pointer
  # shares a union with `vo->x11` since mpv a310a65d, and the next context,
  # `x11egl`, trips `vo_x11_init: Assertion '!vo->x11' failed`
  # (video/out/x11_common.c:679; mpv-player/mpv#17190, fixed on master by
  # a58dd8ac4, in no release as of 2026-10-26; D-DOC-26 for the first
  # version of this comment, which blamed x11vk): SIGABRT in the `vo` thread about 5 s after
  # the launch, a 6 MB core, a "Process crashed: mpv" card on the user's
  # REAL desktop, and the service relaunches it, so again every ~5.5 s for
  # as long as a play intent stands (30 dumps and 7 cards on 2026-10-25,
  # from the liveproofs rig running m3 and pip inside a cage). Measured on a
  # WLR_RENDERER=pixman cage with the plugin's own argv shape, both with the
  # cage's DISPLAY and without one (QA-RESULTS "F-HARNESS-45"). Unsetting
  # DISPLAY does not change it. `--gpu-sw=yes` does: the probe then ACCEPTS
  # the llvmpipe context and the player comes up (gpu-next, vo-configured,
  # idle, answering IPC). `--vo=wlshm` is NOT an alternative: forced
  # windowed and idle it sends wl_viewport.set_destination with a zero size
  # and the compositor disconnects it (exit 0, no window). `--ao=null`
  # keeps the cage's player off the user's sound server: the same argv run
  # under the user's runtime directory resolved `current-ao` to
  # `pipewire-0`, the user's own, with the tone audible.
  # The lever is the user's own, mpvArgs through OMARCHY_IPTV_MPV_ARGS, and
  # the two tokens go BEHIND whatever the caller set -- never when the
  # caller already named `--gpu-sw` or `--ao`, whose word wins as a user's
  # would. When: the caller says so (OMARCHY_IPTV_HARNESS_SOFTWARE_GPU=1,
  # which every scenario's `h()` sets beside WAYLAND_DISPLAY=$NESTED), or
  # the environment says the compositor renders with pixman
  # (WLR_RENDERER=pixman: a cage's child inherits it from the cage's own
  # environment and no live session carries it -- the shape in which the
  # rig ran a whole scenario INSIDE the cage's child). A caller that sets
  # the variable to anything but 1 has said no. A live session's player
  # gets nothing from here. tests/test_harness_cage_player.py drives this
  # function and the shipped helper's filter over the result.
  # D-PLY-27 (the owner's decision, 2026-10-26): the shipped BASE argv now
  # carries `--gpu-sw=yes` itself (`mpv_launch_argv` in bin/helper/07-player.py
  # and Model.buildMpvArgv, after the two cache directories and before the
  # first `--tls-verify=yes`), so on the current tree the lever's
  # `--gpu-sw=yes` is a second copy of a base token, with the same value, in
  # the user's section, and the cage's player comes up without it: observed
  # by lane-dply27 the same day, one m3 cell under the pixman cage on the
  # private bus with this half of the lever withheld
  # (OMARCHY_IPTV_HARNESS_SOFTWARE_GPU=0 and `--ao=null` as the caller's own
  # token), vo-configured true over the player's socket and the coredump
  # journal +0. The lever STAYS, for two reasons: `--baseline <ref>` runs a
  # scenario against an OLDER tree whose base argv lacks the token (every
  # release through 0.15.0), and `--ao=null` is the lever's own job on every
  # tree -- the base argv does NOT carry it, because a user's player must
  # have sound.
  if [[ -z ${OMARCHY_IPTV_HARNESS_SOFTWARE_GPU+x} && ${WLR_RENDERER:-} == pixman ]]; then
    export OMARCHY_IPTV_HARNESS_SOFTWARE_GPU=1
  fi
  if [[ ${OMARCHY_IPTV_HARNESS_SOFTWARE_GPU:-0} == 1 ]]; then
    local args=${OMARCHY_IPTV_MPV_ARGS:-}
    if [[ " $args " != *" --gpu-sw"* && " $args " != *" --no-gpu-sw "* ]]; then args="${args:+$args }--gpu-sw=yes"; fi
    if [[ " $args " != *" --ao="* ]]; then args="${args:+$args }--ao=null"; fi
    export OMARCHY_IPTV_MPV_ARGS="$args"
  fi
  # F-HARNESS-20, and this one is a SAFETY isolation, not a convenience. The
  # D-SINK-18 comment that stood here said exporting XDG_CONFIG_HOME kept the
  # helper's chmod away from the developer's ~/.config/omarchy/shell.json.
  # It stopped being true the day the D-SINK-18 repair made the helper take
  # that file from $HOME, as the host does -- and the service runs the shield
  # at EVERY start, so every harness run since aimed it at the live config
  # (it changed nothing on the machine that found it only because that file
  # was already 0600). The fix is HERE and not in the helper, by ruling: no
  # override flag, no variable the shipped code reads, no path argument. The
  # harness gives the processes it starts -- quickshell, the helper the
  # service spawns, mpv the helper forks -- a HOME of their own, with
  # XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_CACHE_HOME and XDG_STATE_HOME inside
  # the scratch tree beside it, and MPV_HOME / XCOMPOSEFILE dropped when they
  # point into the real home. qa_harness_home (scripts/qa-lib.sh) is the one
  # definition; every scenario driver calls it too, so the driver's own
  # helper runs resolve the same way. tests/test_harness_home.py runs this
  # function and asks the SHIPPED helper where its paths land.
  qa_harness_home "$SCRATCH" || die "could not give the harness its own HOME under $SCRATCH"
  # M2-05. $SCRATCH/bin goes in FRONT of PATH when a scenario has put
  # something there, which is how pip-scenario.sh hands the shell a stub
  # `hyprctl` (scripts/dev-harness/stub-hyprctl.py). That indirection is not
  # a convenience: without it the service would drive the REAL compositor and
  # float, shrink and pin windows in the user's live session. The directory
  # is created by the scenario and by nothing else, so an ordinary harness
  # run is unaffected.
  [[ -d $SCRATCH/bin ]] && export PATH="$SCRATCH/bin:$PATH"
  return 0
}

write_fixture() {
  local live=$1
  sed "s|__LIVE__|$live|g" "$HERE/fixtures/harness.m3u.in" >"$SCRATCH/fixtures/harness.m3u"
}

write_fake_epg() {
  python3 - "$SCRATCH/cache/omarchy-iptv/epg-now.json" <<'PY'
import json, os, sys, time
path = sys.argv[1]
os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
now = int(time.time())
def prog(title, start, stop):
    return {"title": title, "start": start, "stop": stop}
channels = {
    "bbc1.uk": {"now": prog("News at Six", now - 1500, now + 900), "next": prog("Regional News", now + 900, now + 1500)},
    "bbc2.uk": {"now": prog("Gardeners' World", now - 300, now + 3000), "next": prog("Newsnight", now + 3000, now + 4800)},
    "skysports.uk": {"now": prog("Premier League: Arsenal v Spurs", now - 3600, now + 2400), "next": prog("Match Replay", now + 2400, now + 6000)},
    "harness.live": {"now": prog("Test Pattern", now - 60, now + 60), "next": prog("Colour Bars", now + 60, now + 120)},
    "arte.de": {"now": prog("Karambolage", now - 200, now + 1000), "next": prog("Tracks", now + 1000, now + 2800)},
    "expired.uk": {"now": prog("Already Over", now - 7200, now - 3600), "next": prog("Something Later", now + 100, now + 200)},
}
# The shape the helper's write_epg_now writes (D-EPG-11, R31b): the header
# line ending in ,"channels":{ then ONE channel fragment per line with a
# trailing comma except the last, then }}. Valid JSON as before; the shell
# indexes it by line and parses one entry when a row asks. A fake in the old
# one-line shape would still load, through the legacy path, and so would
# prove nothing about the shipping one.
meta = {"version": 1, "generatedAt": now, "validUntil": now + 300, "sourceHost": "harness"}
head = json.dumps(meta, separators=(",", ":"))[:-1] + ',"channels":{\n'
lines = [json.dumps(cid) + ":" + json.dumps(entry, separators=(",", ":")) for cid, entry in channels.items()]
with open(path, "w") as fh:
    fh.write(head + ",\n".join(lines) + "\n}}\n")
os.chmod(path, 0o600)
PY
}

start_server() {
  local video="$SCRATCH/fixtures/test.ts"
  if [[ ! -f $video ]]; then
    echo "[run.sh] generating test video with ffmpeg (lavfi testsrc, 120 s)"
    ffmpeg -loglevel error -y -f lavfi -i "testsrc=size=320x240:rate=15" -f lavfi -i "sine=frequency=440:sample_rate=22050" \
      -t 120 -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 32k -f mpegts "$video" || { echo "[run.sh] ffmpeg failed"; exit 1; }
  fi
  # A previous run killed with SIGKILL could not clean up: end its server by
  # the pid it recorded (F-HARNESS-32; this was a `pkill -f` pattern).
  stop_recorded_server
  python3 -m http.server "$SERVE_PORT" --bind 127.0.0.1 --directory "$SCRATCH/fixtures" >/dev/null 2>&1 &
  SERVER_PID=$!
  printf '%s\n' "$SERVER_PID" >"$(server_pidfile)"
  echo "[run.sh] serving $SCRATCH/fixtures on http://127.0.0.1:$SERVE_PORT (pid $SERVER_PID)"
}

# ---- F-M3-1 half (a). Nothing sends a keystroke without first proving where
# it will land. Both checks below guard `key` and `type`.

# Is the screen locked? Checked before EVERY keystroke and never escapable:
# CLAUDE.md's parallel rule 6 says a key typed at a lock prompt registers as a
# failed unlock attempt, and until now that rule was prose each scenario author
# had to remember -- text-scenario.sh:208 did it, every other scenario did not.
# A rule joined to its callers by nothing is the F-HARNESS-1 and F-RWD-14
# shape, and the repair is the same one: handle it HERE, once.
#
# `-x` matches the process NAME, and nothing else. `-f` matches any command
# line that merely MENTIONS the name, which CLAUDE.md rule 3 records has bitten
# this project three times, once in a brief that was quoting the rule. Measured
# here: with `-f` in place of `-x`, and nothing locked at all, `key` refused --
# the match was an ancestor shell whose own command line contained the word
# `hyprlock`. A check that can refuse every keystroke forever because of what
# some parent process is called is not a check.
screen_locked() { pgrep -x hyprlock >/dev/null 2>&1; }

# How long to wait for the harness to say where the keyboard is. BOUNDED,
# because an unbounded wait is a bug and not patience (rule 3): `qs ipc`
# against an instance that is simply not there fails fast, but a half-dead one
# need not, and the answer to "I cannot tell" is to refuse and say so.
FOCUS_TIMEOUT=${OMARCHY_IPTV_FOCUS_TIMEOUT:-5}

# Refuse unless the harness guide holds the keyboard, naming what was found so
# an operator can tell "the guide is closed" from "another surface has it".
#
# The question goes to the harness over the SAME path `type` already uses for
# numberState, so it reaches the same instance: `ipc` resolves the config root
# from $INSTANCE, which for these verbs comes from the environment
# (OMARCHY_IPTV_HARNESS_INSTANCE) and is inherited by this child.
#
# ONLY the environment variable. `--instance` is a `start` option and is parsed
# nowhere else, so `run.sh --instance 2 key j` is a usage error ("unknown
# option: key", exit 2) and `run.sh key --instance 2 j` passes the flag to
# wtype as TEXT to be typed. That is deliberate, not an oversight: everything
# after `key` belongs to wtype, so a flag of ours there would be ambiguous
# with the argv the caller wants delivered. Routing a second instance is
# `OMARCHY_IPTV_HARNESS_INSTANCE=2 run.sh key j` -- the form
# player-scenario.sh already uses for its second instance's OTHER verbs
# (`ipc2`, `shell-stop`, the `--detach` start); no scenario sends a key to a
# second instance today. An earlier version of this comment said a second
# `--instance` root was "asked about itself", which read as if the flag
# reached these verbs at all; measured all three forms and only the variable
# routes. scripts/qa-lib-test.sh drives them.
#
# The reply is URL-free by construction (booleans, counts, two type tokens),
# so echoing it into the terminal cannot leak a playlist URL (rule 5).
#
# Fails CLOSED. Any answer that is not a readable "yes" refuses, because the
# whole point is that a keystroke into an unknown surface is invisible.
require_guide_focus() {
  local what=$1 reply status verdict diag errfile target=nested players="" dir=$SCRATCH p c
  # The two streams are kept APART, and this is the whole finding of the first
  # review of this guard. `2>&1` here fed any diagnostic `qs` wrote on stderr
  # into json.loads, and the guard fails closed, so ONE stray line turned every
  # key and type into exit 3 -- invisibly, because all eleven call sites are
  # `>/dev/null 2>&1` with the status dropped, so the scenario would simply
  # score lower with no cause on screen. That `qs ipc` is noisy in practice is
  # not a guess: twelve scenario wrappers add `2>/dev/null` to it, and the
  # sibling read in the `type` verb below does the same. The diagnostic is still
  # SHOWN on a failure, which `2>/dev/null` alone would have thrown away; it is
  # only kept out of the parser.
  errfile=$(mktemp "${TMPDIR:-/tmp}/omarchy-iptv-focus.XXXXXX") || {
    echo "[run.sh] $what REFUSED: cannot make a temp file to read the harness reply" >&2
    return 1
  }
  reply=$(timeout "$FOCUS_TIMEOUT" "$0" ipc focusState 2>"$errfile")
  status=$?
  diag=$(tr '\n' ' ' <"$errfile")
  rm -f "$errfile"
  if (( status == 124 )); then
    echo "[run.sh] $what REFUSED: the harness did not answer focusState within ${FOCUS_TIMEOUT}s -- giving up rather than typing blind${diag:+ (stderr: $diag)}" >&2
    return 1
  fi
  if (( status != 0 )); then
    echo "[run.sh] $what REFUSED: cannot ask the harness where the keyboard is (qs ipc exit $status): ${diag:-${reply//$'\n'/ }}" >&2
    echo "[run.sh] if no harness is running, start one (run.sh --detach --open); if a harness from BEFORE this change is still up it has no focusState verb, so reap and restart it (run.sh reap)" >&2
    echo "[run.sh] if this key is meant for the COMPOSITOR rather than the guide, pass --to-compositor" >&2
    return 1
  fi
  # F-HARNESS-54 (1): what the refusal can SAY about an inactive window. Which
  # compositor the key would go to (the desk or a nested one, the predicate
  # harness_env acts on), and whether this harness's own player is up -- the
  # surface that took the keyboard when the floating guide lost it under a
  # cage (QA-RESULTS "F-M3-24"). Its pid, never its argv: the command line
  # is read only to match this scratch's socket.
  qa_target_nested "${WAYLAND_DISPLAY:-wayland-1}" "$REAL_RUNTIME" || target=desk
  [[ $dir == /* ]] || dir=$PWD/$dir
  for p in $(pgrep -x mpv 2>/dev/null); do
    c=$(qa_cmdline "$p") || continue
    [[ $c == *"input-ipc-server=$dir/runtime/omarchy-iptv/mpv.sock"* ]] && players="${players:+$players,}$p"
  done
  verdict=$(python3 - "$reply" "$QA_KEY_WINDOW_INACTIVE" "$target" "$players" <<'PY'
import json, sys
raw = sys.argv[1]
try:
    d = json.loads(raw)
except Exception:
    print("no the harness reply was not JSON: " + " ".join(raw.split())[:200])
    sys.exit(0)
if not isinstance(d, dict):
    print("no the harness reply was not a JSON object")
    sys.exit(0)
if not d.get("ok"):
    print("no the harness has loaded no guide (error=%s)" % (d.get("error"),))
    sys.exit(0)
where = ("window=%s open=%s keyboard=%s role=%s item=%s blocked=%s scanned=%s exhausted=%s windowActive=%s windowVisible=%s"
         % (d.get("window"), d.get("open"), d.get("keyboard"), d.get("role"),
            d.get("item"), d.get("blocked"), d.get("scanned"), d.get("exhausted"),
            d.get("windowActive"), d.get("windowVisible")))
# F-M3-24: `keyboard` is Qt's own item focus, and an item keeps activeFocus
# in a window the compositor never mapped -- measured under a headless cage,
# where the guide's layer window cannot map, with the guard passing and the
# key reaching nothing, or the player's window. `windowActive` is the
# window's activation, which Qt takes from the compositor's keyboard
# enter/leave. Absent or null is "cannot tell" and refuses too (fail closed),
# but without the tag: only an observed `false` is the class a scenario may
# turn into a SKIP (qa_key, QA_KEY_SKIP_INACTIVE).
active = d.get("windowActive")
if not d.get("open"):
    print("no the guide is CLOSED, so a key would land in whatever is behind it; " + where)
elif active is None:
    print("no the harness did not say whether the guide's WINDOW holds the compositor's keyboard "
          "(no windowActive in its reply: a harness started before F-M3-24? reap and restart it), "
          "so I cannot tell; " + where)
elif active is not True:
    # F-HARNESS-54 (1): worded by window kind and keyboard. The cage hint
    # belongs to the one case it fixes -- the production LAYER window on a
    # nested compositor, which cannot map it -- and was given to a guide
    # already floating, and to a desk FAIL, where it is wrong advice.
    kind, target, players = d.get("window"), sys.argv[3], sys.argv[4]
    msg = ("the compositor has not given the guide's WINDOW the keyboard (%s): Qt reports the %s window "
           "inactive, so a key would go to whatever the compositor focused" % (sys.argv[2], kind))
    msg += (", whatever item inside the guide holds focus" if d.get("keyboard")
            else ", and no item inside the guide holds focus either")
    if kind == "floating":
        if players:
            msg += (". The floating window is mapped and another toplevel took the keyboard: this harness's "
                    "player is up (mpv pid %s), and a compositor that focuses its newest toplevel, as cage "
                    "does, gave it to the player's window when that mapped" % players)
        else:
            msg += (". The floating window is mapped and another toplevel holds the keyboard; no player of "
                    "this harness is up, so it is not this harness's player window")
    elif kind == "layer" and target == "nested":
        msg += (". Under a compositor with no layer-shell (headless cage) the production guide window never "
                "maps; start the harness with --window floating there")
    elif kind == "layer":
        msg += (". This is the session's own compositor, which has layer-shell, so the open guide's layer "
                "window should hold the keyboard: this is the guide failing to take it, not the display")
    print("no " + msg + "; " + where)
elif d.get("exhausted") and not d.get("keyboard"):
    print("no the focus walk gave up before it found a focused item, so I cannot tell; " + where)
elif not d.get("keyboard"):
    print("no the guide is open but ANOTHER SURFACE holds the keyboard; " + where)
else:
    print("yes " + where)
PY
)
  if [[ -z $verdict ]]; then
    echo "[run.sh] $what REFUSED: could not read the harness focus reply at all (python3 produced nothing)" >&2
    return 1
  fi
  [[ ${verdict%% *} == yes ]] && return 0
  echo "[run.sh] $what REFUSED: ${verdict#* }" >&2
  echo "[run.sh] pass --to-compositor ONLY if this key is meant for the compositor rather than the guide" >&2
  return 1
}

# The lock refusal, shared by both verbs so the message cannot drift.
refuse_if_locked() {
  screen_locked || return 0
  echo "[run.sh] $1 REFUSED: hyprlock is running. A keystroke now registers as a FAILED UNLOCK ATTEMPT (CLAUDE.md parallel rule 6), so this refusal has no escape hatch." >&2
  return 1
}

cmd=${1:-start}
case $cmd in
  ipc)
    shift
    harness_env
    exec qs ipc -p "$(qs_root)" call harness "$@"
    ;;
  plugin-ipc)
    # F-RWD-14. Identical to `ipc` except the target, which is the plugin's own
    # rather than the harness's. The environment is harness_env's, which is the
    # measured form (SPIKE-LIVE-REWIND 12.5): the scratch runtime directory
    # alone gets "No running instances ... present on the current display",
    # because run.sh hands the shell the ABSOLUTE socket path.
    #
    # It can only ever reach the harness, never the user's live shell: the
    # config root is this scratch root, and the spike measured that the live
    # instance answers the same target name under /usr/share/omarchy/shell.
    #
    # The empty call is refused HERE rather than by `qs`, so a scenario that
    # drops its argument is told what it dropped without needing quickshell
    # installed to find out. Everything past the function name is passed
    # through untouched.
    shift
    (( $# > 0 )) || die "plugin-ipc needs a function name (e.g. plugin-ipc status)"
    if ! target=$(plugin_target); then exit 2; fi
    harness_env
    exec qs ipc -p "$(qs_root)" call "$target" "$@"
    ;;
  shot)
    shift
    # F-HARNESS-12. `shot` grades PIXELS, and a human reads its file as
    # proof, so a capture of a surface that is not the guide's was the one
    # failure the verb could not see -- the same class F-M3-1 closed for
    # keystrokes. It asks the same question `key` asks, over `ipc
    # focusState`, and refuses with the same exit 3 and the same wording
    # (scripts/qa-lib-test.sh drives the decision). `--any-surface` is the
    # deliberate shot of whatever is up -- the player window, the
    # compositor -- and must come first, like `--to-compositor`. No lock
    # refusal: nothing is typed. The monitor is the focused one, as before;
    # `focusState` carries no output name, so which OUTPUT the guide is on
    # is not asserted here (recorded rather than invented).
    ANY_SURFACE=0
    while (( $# > 0 )) && [[ $1 == --any-surface ]]; do ANY_SURFACE=1; shift; done
    name=${1:-guide}
    if (( ANY_SURFACE )); then
      echo "[run.sh] shot --any-surface: focus guard SKIPPED; this captures whatever is on the focused output, guide or not" >&2
    else
      require_guide_focus shot || exit 3
    fi
    out=$(hyprctl monitors -j | python3 -c 'import json,sys; ms=json.load(sys.stdin); print(next((m["name"] for m in ms if m.get("focused")), ms[0]["name"]))')
    mkdir -p "$SCRATCH/shots"
    grim -o "$out" "$SCRATCH/shots/$name.png" && echo "$SCRATCH/shots/$name.png"
    ;;
  key)
    shift
    # F-M3-1 half (a), the escape hatch. It must come FIRST: everything after
    # it belongs to wtype, and wtype's own `--` means "the rest is text", so a
    # flag of ours appearing later is text the caller asked to TYPE.
    TO_COMPOSITOR=0
    while (( $# > 0 )) && [[ $1 == --to-compositor ]]; do TO_COMPOSITOR=1; shift; done
    (( $# > 0 )) || die "key needs at least one wtype argument (e.g. key j, key -k Escape)"
    # (1) The lock prompt, first and not escapable.
    refuse_if_locked key || exit 3
    # (2) Where the keyboard is. This runs BEFORE the shift primer below,
    # because the primer is ITSELF a keystroke: a guard that ran after it would
    # already have typed into the wrong surface before deciding not to.
    if (( TO_COMPOSITOR )); then
      echo "[run.sh] key --to-compositor: focus guard SKIPPED; this chord goes to whatever holds the keyboard, guide or not" >&2
    else
      require_guide_focus key || exit 3
    fi
    # F-HARNESS-1. The FIRST wtype keystroke into a fresh shell is
    # intermittently swallowed -- 1 fresh shell in 4 during verification, where
    # `sky` arrived as `ky`. A row-count assertion cannot tell the two apart
    # (both filter 20 rows to 3), so the loss reads as a pass.
    #
    # The board's rule for this was prose every scenario author had to remember
    # and apply, which is a rule joined to its callers by nothing. It is handled
    # HERE instead, once, so a scenario cannot get it wrong by forgetting.
    #
    # The primer is a Shift press and release with no other key: it reaches the
    # surface, so whatever is not ready yet becomes ready, and it cannot change
    # any state in the guide. It runs once per shell, keyed to the pid file that
    # `start` rewrites, so a fresh shell primes again and a long scenario does
    # not pay for it on every keystroke.
    #
    # --to-compositor skips it, and that is the point rather than an
    # optimisation. The hatch exists for a chord aimed at whatever holds the
    # keyboard, which is by definition NOT the guide's fresh surface; firing
    # the primer there sent a Shift into a foreign surface and -- worse --
    # recorded the shell as primed, so the next legitimate key into the GUIDE
    # skipped priming and could be the one that gets swallowed. The
    # compensation was spent without ever having reached the surface it
    # compensates for, which reopens F-HARNESS-1. Found by the first review of
    # this guard; scripts/qa-lib-test.sh drives the sequence.
    primed="$SCRATCH/primed$INSTANCE"
    if (( ! TO_COMPOSITOR )) \
       && [[ ! -f $primed || $(cat "$primed" 2>/dev/null) != $(cat "$(qs_pidfile)" 2>/dev/null) ]]; then
      wtype -M shift -m shift 2>/dev/null || true
      cat "$(qs_pidfile)" 2>/dev/null >"$primed" || true
    fi
    exec wtype "$@"
    ;;
  type)
    # F-HARNESS-1, the other half. Types TEXT and then proves it arrived, by
    # reading the query back over IPC rather than counting rows. One retry: the
    # loss is a first-keystroke race, so a reset and a resend clears it, and a
    # second failure is a real defect that must not be retried into silence.
    shift
    want=${1:-}
    if [[ -z $want ]]; then echo "[run.sh] type needs text" >&2; exit 2; fi
    # F-M3-1 half (a). The same two refusals as `key`, and up FRONT: without
    # them `type` enters its retry loop, sends the text TWICE into whatever
    # surface has the keyboard, and then reports a two-attempt failure whose
    # own message says "this is not the first-keystroke race" -- which is true,
    # and still the wrong diagnosis. There is no --to-compositor here: `type`
    # proves the text reached the GUIDE by reading it back, so a chord aimed at
    # the compositor has nothing for it to prove.
    #
    # `"$0" key` below checks again, once per attempt. That is deliberate: the
    # second check catches focus stolen in between -- and its VERDICT is now
    # what `type` ends on. The inner refusal used to be dropped on the loop
    # body, so a steal after the front check fell through to the two-attempt
    # message that this very comment calls the wrong diagnosis, and exited 1
    # rather than 3. A scenario grading `exit 3` as "refused" could not see a
    # focus refusal at all. Found by the first review of this guard.
    #
    # Exit 3 lands on the FIRST inner refusal rather than after a retry: the
    # inner `key` has already said on stderr which of the two refusals it was,
    # a 0.25 s wait does not give the keyboard back, and a second refusal only
    # buries the first. Nothing was typed either way, which is what exit 3
    # means here.
    refuse_if_locked type || exit 3
    require_guide_focus type || exit 3
    for attempt in 1 2; do
      "$0" key -- "$want"
      kstatus=$?
      if (( kstatus == 3 )); then
        echo "[run.sh] type REFUSED on attempt $attempt: the guard refused the keystroke (see the line above); nothing was typed" >&2
        exit 3
      fi
      sleep 0.25
      got=$("$0" ipc numberState 2>/dev/null | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("queryLive",""))
except Exception: print("<unreadable>")' | tr -d '\n')
      if [[ $got == "$want" ]]; then
        echo "[run.sh] typed '$want' (attempt $attempt)"
        exit 0
      fi
      echo "[run.sh] type: sent '$want', surface holds '$got' -- resetting and retrying" >&2
      "$0" ipc query "" >/dev/null 2>&1 || true
      sleep 0.15
    done
    echo "[run.sh] type FAILED: '$want' did not arrive after two attempts; this is not the first-keystroke race" >&2
    exit 1
    ;;
  clean)
    # $SCRATCH/home goes too (D-SINK-18, F-HARNESS-20): a clean that left it
    # behind would leave the mode the last run's shield tightened, and the
    # next run's green would be inherited rather than earned. prepare_root
    # re-seeds the host config at 0644 and re-copies the theme.
    # $SCRATCH/config is the pre-F-HARNESS-20 location, removed so an old
    # scratch tree does not keep a decoy nothing reads.
    # key-scenario.sh's F segment takes `w` off the state directory under
    # the running shell; a run signalled inside it left the directory 0500,
    # and `rm -rf` then stopped on state.json ("Permission denied", the
    # directory left behind -- round-4 live review). Everything under these
    # paths is the tree harness_env points into $SCRATCH -- this harness's
    # own scratch -- so give it back its modes first. The chmod is confined
    # to those paths, never the directory itself.
    chmod -R u+rwX "$SCRATCH/cache" "$SCRATCH/state" "$SCRATCH/home" "$SCRATCH/config" \
      "$SCRATCH/runtime/omarchy-iptv" "$SCRATCH/shots" 2>/dev/null
    # DQ-B17: the rm's own status is the verb's answer. This printed
    # `cleaned` with rc 0 whatever rm did, so a directory it could not
    # remove (a parent left without `w`, which the chmod above deliberately
    # does not touch) read as clean and the next run inherited it.
    if ! rm -rf "$SCRATCH/cache" "$SCRATCH/state" "$SCRATCH/home" "$SCRATCH/config" \
         "$SCRATCH/runtime/omarchy-iptv" "$SCRATCH/shots"; then
      echo "[run.sh] clean FAILED: could not remove everything under $SCRATCH (rm reported the paths above)" >&2
      exit 1
    fi
    echo "[run.sh] cleaned $SCRATCH"
    ;;
  scenario)
    shift
    exec "$HERE/sources-scenario.sh" "$@"
    ;;
  player-scenario)
    shift
    exec "$HERE/player-scenario.sh" "$@"
    ;;
  shell-stop)
    stop_detached_shell
    echo "[run.sh] shell$INSTANCE stopped"
    ;;
  restart-shell)
    # The M2-02 acceptance shape: the shell goes away and comes back with the
    # same environment, and NOTHING touches the player. A detached start
    # (--detach) must have written last-start.env.
    if [[ ! -f $SCRATCH/last-start.env ]]; then
      echo "[run.sh] no detached start recorded; use --detach first" >&2
      exit 2
    fi
    stop_detached_shell
    harness_env
    # shellcheck source=/dev/null
    . "$SCRATCH/last-start.env"
    # C2 (iii): come back to the tree --detach recorded, not to whatever this
    # terminal happens to export. Then assert the two agree, because a
    # disagreement is the mixed tree C1 guards the other half of.
    if [[ -n ${OMARCHY_IPTV_PLUGIN_ROOT:-} ]]; then
      PLUGIN_ROOT=$(cd "$OMARCHY_IPTV_PLUGIN_ROOT" 2>/dev/null && pwd) \
        || die "the recorded plugin tree $OMARCHY_IPTV_PLUGIN_ROOT is gone"
    fi
    [[ "$PLUGIN_ROOT" == "${OMARCHY_IPTV_ROOT:-$PLUGIN_ROOT}" ]] \
      || die "restart-shell would mix trees: the model from $PLUGIN_ROOT, QML from $OMARCHY_IPTV_ROOT"
    prepare_root
    start_detached_shell
    ;;
  reap)
    # F-HARNESS-32: the detached shell by its pid file, the fixture server by
    # its pid file, the player by its socket argument -- each with TERM, a
    # bound and KILL -- and no `pkill -f` pattern anywhere in this script.
    stop_detached_shell
    stop_recorded_server
    reap_player
    echo "[run.sh] reaped shell, fixture server and player for $SCRATCH"
    ;;
  start|--*)
    [[ $cmd == start ]] && shift
    OPEN=0 TIMEOUT=15 PLAYLIST="" EPG="" SOURCE2="" SERVE=0 FAKE_EPG=0 VERTICAL=0 SHOW_NAME=true LABEL_MAX=180 KEEP=0 DETACH=0 SEED_CACHE=""
    ORDER=playlist ENTRY_MS=2000 BAR_NUMBER=true WINDOW=layer SOURCE_KEY="" SOURCE_KEY_SET=0 HOST_MODE=lag
    while (($# > 0)); do
      case $1 in
        --open) OPEN=1 ;;
        --timeout) TIMEOUT=$2; shift ;;
        --playlist) PLAYLIST=$2; shift ;;
        --epg) EPG=$2; shift ;;
        --source2) SOURCE2=$2; shift ;;
        --serve) SERVE=1 ;;
        --fake-epg) FAKE_EPG=1 ;;
        --vertical) VERTICAL=1 ;;
        --no-name) SHOW_NAME=false ;;
        --label-max) LABEL_MAX=$2; shift ;;
        # Rejected here rather than in QML: channelOrder is deliberately
        # forgiving at runtime (an unreadable value means "playlist"), which
        # would turn a typo in a scenario into a silent pass.
        --order) ORDER=$2; shift
                 [[ $ORDER == playlist || $ORDER == number ]] || die "--order takes playlist or number, not '$ORDER'" ;;
        --entry-ms) ENTRY_MS=$2; shift
                 [[ $ENTRY_MS =~ ^[0-9]+$ ]] || die "--entry-ms takes an integer, not '$ENTRY_MS'"
                 (( ENTRY_MS >= 400 && ENTRY_MS <= 5000 )) || die "--entry-ms is 400..5000 (manifest range), got $ENTRY_MS" ;;
        --no-bar-number) BAR_NUMBER=false ;;
        --keep) KEEP=1 ;;
        # F-HARNESS-44. Refused here for the same reason as --order: a seed
        # directory that does not exist would start a shell over a wiped
        # cache and print a cold figure under the wrong condition.
        --seed-cache) SEED_CACHE=$2; shift
                 [[ -n $SEED_CACHE && -d $SEED_CACHE ]] || die "--seed-cache takes a directory, not '$SEED_CACHE'" ;;
        --keep-player) KEEP_PLAYER=1 ;;
        --detach) DETACH=1; KEEP_PLAYER=1 ;;
        --instance) INSTANCE=$2; shift ;;
        # Harness-only: which window hosts the guide. Rejected here for the
        # same reason as --order: shell.qml compares the string, so a typo
        # would silently run the production window under a compositor that
        # cannot map it and every pixel check after it would be vacuous.
        # D-SINK-19. Validated here for the same reason as --order: the fake
        # seeds the string as given, and a key that is not one would present
        # an entry no host write can produce (Model.activeKeyText refuses it
        # on the way in, so the plugin would read "" and a scenario a pass).
        --source-key) SOURCE_KEY=$2; SOURCE_KEY_SET=1; shift
                 [[ $SOURCE_KEY == "" || $SOURCE_KEY =~ ^[0-9a-f]{8}(-[0-9]+)?$ ]] || die "--source-key takes an 8-hex source key or \"\", not '$SOURCE_KEY'" ;;
        # Rejected here for the same reason as --order: shell.qml compares the
        # string, so a typo would silently run the lagging host.
        --host) HOST_MODE=$2; shift
                 [[ $HOST_MODE == lag || $HOST_MODE == echo ]] || die "--host takes lag or echo, not '$HOST_MODE'" ;;
        --window) WINDOW=$2; shift
                 [[ $WINDOW == layer || $WINDOW == floating ]] || die "--window takes layer or floating, not '$WINDOW'" ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
      esac
      shift
    done
    # F-HARNESS-20: the environment FIRST, so the fixture server and ffmpeg
    # below run under the scratch HOME like everything else this starts.
    (( KEEP )) && [[ -n $SEED_CACHE ]] && die "--keep and --seed-cache are the same lever; pass one"
    harness_env
    prepare_root
    reset_scratch_cache
    # Always reap what we start: normal exit, --timeout, Ctrl-C, SIGTERM.
    # --detach deliberately installs no trap: the shell and the player must
    # outlive this invocation (that is the state `restart-shell` acts on),
    # and `run.sh reap` is then the teardown.
    if (( ! DETACH )); then
      trap cleanup EXIT
      trap 'exit 130' INT
      trap 'exit 143' TERM
    fi
    live="http://127.0.0.1:9/dead/live.m3u8"
    if (( SERVE )); then start_server; live="http://127.0.0.1:$SERVE_PORT/test.ts"; fi
    write_fixture "$live"
    (( FAKE_EPG )) && write_fake_epg
    if [[ -n $SOURCE2 ]]; then
      # A second history record, never fetched (fetchedAt 0): the switch
      # path through a probe. Output is the helper's, hosts only.
      seeded=$(python3 "$PLUGIN_ROOT/bin/omarchy-iptv" state --state-dir "$SCRATCH/state/omarchy-iptv" source add --url "$SOURCE2" --origin cli)
      echo "[run.sh] source2=$(source_label "$SOURCE2") key=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("key", "?"))' "$seeded")"
    fi
    export OMARCHY_IPTV_ROOT="$PLUGIN_ROOT"
    if [[ $PLAYLIST == none ]]; then export OMARCHY_IPTV_PLAYLIST=""
    else export OMARCHY_IPTV_PLAYLIST="${PLAYLIST:-$SCRATCH/fixtures/harness.m3u}"; fi
    export OMARCHY_IPTV_EPG="$EPG"
    export OMARCHY_IPTV_OPEN="$OPEN"
    export OMARCHY_IPTV_VERTICAL="$VERTICAL"
    export OMARCHY_IPTV_SHOW_NAME="$SHOW_NAME"
    export OMARCHY_IPTV_LABEL_MAX="$LABEL_MAX"
    export OMARCHY_IPTV_ORDER="$ORDER"
    export OMARCHY_IPTV_ENTRY_MS="$ENTRY_MS"
    export OMARCHY_IPTV_BAR_NUMBER="$BAR_NUMBER"
    export OMARCHY_IPTV_HARNESS_WINDOW="$WINDOW"
    export OMARCHY_IPTV_SOURCE_KEY="$SOURCE_KEY"
    export OMARCHY_IPTV_SOURCE_KEY_SET="$SOURCE_KEY_SET"
    export OMARCHY_IPTV_HARNESS_HOST="$HOST_MODE"
    # scheme://host only: the URL may carry provider credentials (S-08).
    echo "[run.sh] scratch=$SCRATCH timeout=${TIMEOUT}s window=$WINDOW host=$HOST_MODE playlist=$(source_label "$OMARCHY_IPTV_PLAYLIST") epg=$(source_label "$OMARCHY_IPTV_EPG")"
    if (( DETACH )); then
      # Record the environment so `restart-shell` can bring the same shell
      # back without re-deriving anything (the fixture server, the cache and
      # the state stay exactly as they are).
      # C2 (i): these were hand-quoted with \"$VALUE\", so a path carrying a
      # $, a backquote, a backslash or a double quote was re-expanded - or
      # EXECUTED - when restart-shell sourced the file. printf %q round-trips.
      # (ii) OMARCHY_IPTV_PLUGIN_ROOT was NOT recorded, while restart-shell
      # sources this file and then calls prepare_root, which copies Model.js
      # from $PLUGIN_ROOT computed from the CALLER's environment. A
      # `run.sh restart-shell` from a plain terminal after a baseline
      # --detach therefore copied the CURRENT repo's Model.js over the
      # baseline's while Service.qml stayed at the baseline.
      {
        qa_env_line OMARCHY_IPTV_PLUGIN_ROOT "$PLUGIN_ROOT"
        qa_env_line OMARCHY_IPTV_ROOT        "$OMARCHY_IPTV_ROOT"
        qa_env_line OMARCHY_IPTV_PLAYLIST    "$OMARCHY_IPTV_PLAYLIST"
        qa_env_line OMARCHY_IPTV_EPG         "$OMARCHY_IPTV_EPG"
        qa_env_line OMARCHY_IPTV_OPEN        "0"
        qa_env_line OMARCHY_IPTV_VERTICAL    "$OMARCHY_IPTV_VERTICAL"
        qa_env_line OMARCHY_IPTV_SHOW_NAME   "$OMARCHY_IPTV_SHOW_NAME"
        qa_env_line OMARCHY_IPTV_LABEL_MAX   "$OMARCHY_IPTV_LABEL_MAX"
        qa_env_line OMARCHY_IPTV_ORDER       "$OMARCHY_IPTV_ORDER"
        qa_env_line OMARCHY_IPTV_ENTRY_MS    "$OMARCHY_IPTV_ENTRY_MS"
        qa_env_line OMARCHY_IPTV_BAR_NUMBER  "$OMARCHY_IPTV_BAR_NUMBER"
        qa_env_line OMARCHY_IPTV_HARNESS_WINDOW "$OMARCHY_IPTV_HARNESS_WINDOW"
        qa_env_line OMARCHY_IPTV_SOURCE_KEY     "$OMARCHY_IPTV_SOURCE_KEY"
        qa_env_line OMARCHY_IPTV_SOURCE_KEY_SET "$OMARCHY_IPTV_SOURCE_KEY_SET"
        qa_env_line OMARCHY_IPTV_HARNESS_HOST   "$OMARCHY_IPTV_HARNESS_HOST"
        qa_env_line OMARCHY_IPTV_MPV_ARGS    "${OMARCHY_IPTV_MPV_ARGS:-}"
      } >"$SCRATCH/last-start.env"
      start_detached_shell
      exit 0
    fi
    # Background + wait (instead of a pipeline) so the PID is known to cleanup.
    if (( TIMEOUT > 0 )); then
      timeout --signal=TERM --kill-after=3 "$TIMEOUT" quickshell -p "$(qs_root)" > >(sed -u 's/^/[qs] /') 2>&1 &
    else
      quickshell -p "$(qs_root)" > >(sed -u 's/^/[qs] /') 2>&1 &
    fi
    QS_PID=$!
    wait "$QS_PID"
    status=$?
    QS_PID=""
    echo "[run.sh] quickshell exited with $status (124 = timeout, expected)"
    ;;
  *)
    # The whole leading comment block, SCANNED rather than counted. A line
    # range here is a magic number joined to the header by nothing, and the
    # comment that used to sit here asked a human to keep it in step -- which
    # had already failed: `2,51p` stopped inside the scratch-layout list, eight
    # lines short, so the usage had silently stopped naming `runtime/`,
    # `fixtures/`, the 127.0.0.1 rule and what gets reaped. awk stops at the
    # first line that is not a comment, so a new option or paragraph is listed
    # by existing rather than by being counted.
    awk 'NR == 1 { next } /^#/ { print; next } { exit }' "$0"
    exit 2
    ;;
esac
