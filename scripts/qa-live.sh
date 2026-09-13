#!/bin/bash
# scripts/qa-live.sh -- guarded helper for the live-shell QA runbook (docs/QA.md, section 5).
#
# By default this script only PRINTS the exact commands of each runbook phase.
# Nothing is executed or modified unless --apply is given. The install phase
# refuses to run (in both modes) when the plugin directory already exists,
# unless --force is given. Uninstall additionally asks for confirmation
# unless --force is given. Read-only preflight checks always run.
#
# Usage:
#   scripts/qa-live.sh <phase> [--apply] [--force] [--repo <path-or-git-url>]
#                      [--playlist <url>] [--epg <url>] [--evidence-dir <dir>] [--label <name>]
# Phases:
#   preflight   read-only checks of this machine (versions, keybinding, dirs, network)
#   install     snapshot shell.json, git clone (no symlink), validate, rescan, enable
#   configure   omarchy bar set playlistUrl / epgUrl
#   verify      status IPC, mpv window/process, dirs and modes, no writes in plugin dir
#   evidence    capture journal, qs log, status, redaction grep into the evidence dir
#   uninstall   stop, plugin remove --yes, remove cache/state/runtime dirs, diff shell.json
#   all         preflight, install, configure, verify
#
# Everything this script touches with --apply: ~/.config/omarchy/plugins/<id>,
# ~/.config/omarchy/shell.json (through omarchy plugin enable / omarchy bar set),
# ~/.cache/omarchy-iptv, ~/.local/state/omarchy-iptv, $XDG_RUNTIME_DIR/omarchy-iptv,
# and the evidence directory. It never edits bindings.lua or the menu extension.
set -uo pipefail

ID="io.github.rmcdavid.iptv"
# QA_PLUGINS_DIR exists only so the --force guard can be exercised against a
# scratch directory; leave it unset for a real run.
PLUGINS_DIR="${QA_PLUGINS_DIR:-$HOME/.config/omarchy/plugins}"
PLUGIN_DIR="$PLUGINS_DIR/$ID"
SHELL_JSON="$HOME/.config/omarchy/shell.json"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/omarchy-iptv"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy-iptv"
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$UID}/omarchy-iptv"
EVIDENCE_DIR="${QA_EVIDENCE_DIR:-${TMPDIR:-/tmp}/omarchy-iptv-qa}"
PLAYLIST_URL="https://iptv-org.github.io/iptv/countries/us.m3u"
EPG_URL="https://i.mjh.nz/PlutoTV/us.xml.gz"
REPO=""
LABEL=""
APPLY=0
FORCE=0
PHASE=""

usage() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; }
fail() { echo "qa-live: $*" >&2; exit 1; }
note() { printf '\n## %s\n' "$*"; }

# Print the command; execute it only with --apply.
run() {
  printf '$ %s\n' "$*"
  if (( APPLY )); then "$@"; fi
}

# Read-only command: always executed, output shown.
show() {
  printf '$ %s\n' "$*"
  "$@" 2>&1 | sed 's/^/    /'
}

while (( $# > 0 )); do
  case "$1" in
    preflight|install|configure|verify|evidence|uninstall|all) PHASE="$1"; shift ;;
    --apply) APPLY=1; shift ;;
    --force) FORCE=1; shift ;;
    --repo) REPO="${2:-}"; [[ -n $REPO ]] || fail "--repo needs a value"; shift 2 ;;
    --playlist) PLAYLIST_URL="${2:-}"; [[ -n $PLAYLIST_URL ]] || fail "--playlist needs a value"; shift 2 ;;
    --epg) EPG_URL="${2:-}"; shift 2 ;;
    --evidence-dir) EVIDENCE_DIR="${2:-}"; [[ -n $EVIDENCE_DIR ]] || fail "--evidence-dir needs a value"; shift 2 ;;
    --label) LABEL="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1 (try --help)" ;;
  esac
done
[[ -n $PHASE ]] || { usage; exit 2; }

if [[ -z $REPO ]]; then
  REPO=$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || true)
fi

if (( APPLY )); then
  echo "qa-live: --apply given, commands WILL run"
else
  echo "qa-live: dry run, commands are printed only (add --apply to execute)"
fi

phase_preflight() {
  note "preflight (read-only)"
  show pacman -Q omarchy quickshell hyprland mpv python
  show omarchy theme current
  show hyprctl monitors -j
  printf '$ omarchy menu keybindings --print | grep -E "SUPER (SHIFT|CTRL) \\+ T( |$)"\n'
  if omarchy menu keybindings --print 2>/dev/null | grep -E 'SUPER SHIFT \+ T( |$)' | sed 's/^/    TAKEN: /'; then
    echo "    SUPER SHIFT + T is already bound; pick another key for the runbook"
  else
    echo "    SUPER SHIFT + T is free"
  fi
  omarchy menu keybindings --print 2>/dev/null | grep -E 'SUPER CTRL \+ T( |$)' | sed 's/^/    (expected, Activity) /'
  printf '$ grep -n iptv ~/.config/hypr/bindings.lua ~/.config/omarchy/extensions/omarchy-menu.jsonc\n'
  grep -n -i iptv "$HOME/.config/hypr/bindings.lua" "$HOME/.config/omarchy/extensions/omarchy-menu.jsonc" 2>/dev/null | sed 's/^/    /' || echo "    (no iptv lines yet; add them per README when the runbook says so)"
  printf '$ ls -d %s %s %s %s\n' "$PLUGIN_DIR" "$CACHE_DIR" "$STATE_DIR" "$RUNTIME_DIR"
  for d in "$PLUGIN_DIR" "$CACHE_DIR" "$STATE_DIR" "$RUNTIME_DIR"; do
    if [[ -e $d ]]; then echo "    EXISTS: $d"; else echo "    absent: $d"; fi
  done
  show stat -c '%a %n' "$SHELL_JSON"
  printf '$ jq (is %s already in shell.json?)\n' "$ID"
  jq -r --arg id "$ID" '[.bar.layout[]?[]? | select((.id? // .) == $id)] | length | "    entries in bar.layout: \(.)"' "$SHELL_JSON" 2>/dev/null
  show omarchy plugin list
  printf '$ curl -sI --max-time 10 %s | head -1\n' "$PLAYLIST_URL"
  curl -sI --max-time 10 "$PLAYLIST_URL" | head -1 | sed 's/^/    /'
  if [[ -n $EPG_URL ]]; then
    printf '$ curl -sIL --max-time 10 %s | grep -E "^(HTTP|content-length)" | tail -2\n' "$EPG_URL"
    curl -sIL --max-time 10 "$EPG_URL" | grep -iE '^(HTTP|content-length)' | tail -2 | sed 's/^/    /'
  fi
  echo "repo to clone: ${REPO:-<unknown, pass --repo>}"
  echo "evidence dir:  $EVIDENCE_DIR"
}

phase_install() {
  note "install"
  if [[ -e $PLUGIN_DIR || -L $PLUGIN_DIR ]] && (( ! FORCE )); then
    fail "$PLUGIN_DIR already exists; run 'uninstall' first or pass --force"
  fi
  [[ -n $REPO ]] || fail "no repo to clone; pass --repo <path-or-git-url>"
  run mkdir -p "$EVIDENCE_DIR"
  run install -m 600 "$SHELL_JSON" "$EVIDENCE_DIR/shell.json.before"
  run date -Is
  if (( APPLY )); then date -Is > "$EVIDENCE_DIR/started-at"; fi
  run mkdir -p "$PLUGINS_DIR"
  run git clone -- "$REPO" "$PLUGIN_DIR"
  run omarchy plugin validate "$PLUGIN_DIR"
  run omarchy-shell shell rescanPlugins
  run omarchy plugin enable "$ID"
  printf '$ omarchy plugin list --json | jq ".[] | select(.id == \\"%s\\")"\n' "$ID"
  if (( APPLY )); then omarchy plugin list --json | jq --arg id "$ID" '.[] | select(.id == $id)'; fi
  echo "next: scripts/qa-live.sh configure --apply, then add the keybinding and menu lines from README.md by hand"
}

phase_configure() {
  note "configure"
  run omarchy bar set "$ID" playlistUrl "$PLAYLIST_URL"
  if [[ -n $EPG_URL ]]; then run omarchy bar set "$ID" epgUrl "$EPG_URL"; fi
  printf '$ jq (our entry in shell.json; a private provider URL would print here, so review before pasting into a report)\n'
  if (( APPLY )); then jq --arg id "$ID" '.bar.layout[][] | select(.id == $id)' "$SHELL_JSON"; fi
  echo "wait a few seconds, then: scripts/qa-live.sh verify"
}

phase_verify() {
  note "verify (read-only)"
  show omarchy-shell "$ID" status
  printf '$ hyprctl clients -j | jq ".[] | select(.class == \\"omarchy-iptv\\") | {class, title, pid, workspace: .workspace.name, floating, fullscreen}"\n'
  hyprctl clients -j 2>/dev/null | jq '.[] | select(.class == "omarchy-iptv") | {class, title, pid, workspace: .workspace.name, floating, fullscreen}' | sed 's/^/    /'
  printf '$ pgrep -af -- "--wayland-app-id=omarchy-iptv" (expect at most one line)\n'
  pgrep -af -- '--wayland-app-id=omarchy-iptv' | sed 's/^/    /' || echo "    (no mpv running)"
  for d in "$CACHE_DIR" "$STATE_DIR" "$RUNTIME_DIR"; do
    printf '$ stat -c "%%a %%n" %s %s/*\n' "$d" "$d"
    stat -c '%a %n' "$d" "$d"/* 2>/dev/null | sed 's/^/    /' || echo "    absent: $d"
  done
  printf '$ find %s -newer %s/manifest.json -not -path "*/.git/*" (expect nothing)\n' "$PLUGIN_DIR" "$PLUGIN_DIR"
  find "$PLUGIN_DIR" -newer "$PLUGIN_DIR/manifest.json" -not -path '*/.git/*' 2>/dev/null | sed 's/^/    WROTE: /'
  printf '$ ls -la %s (no symlinks expected)\n' "$PLUGIN_DIR"
  find "$PLUGIN_DIR" -name .git -prune -o -type l -print 2>/dev/null | sed 's/^/    SYMLINK: /'
}

phase_evidence() {
  note "evidence"
  local stamp dir since
  stamp=$(date +%Y%m%d-%H%M%S)
  dir="$EVIDENCE_DIR/${LABEL:-capture}-$stamp"
  since="10 minutes ago"
  [[ -f $EVIDENCE_DIR/started-at ]] && since=$(cat "$EVIDENCE_DIR/started-at")
  run mkdir -p "$dir"
  printf '$ journalctl --user -t omarchy-shell --since "%s" --no-pager > %s/journal.txt\n' "$since" "$dir"
  if (( APPLY )); then journalctl --user -t omarchy-shell --since "$since" --no-pager > "$dir/journal.txt" 2>&1; fi
  printf '$ qs log -p /usr/share/omarchy/shell --tail 300 > %s/qs-log.txt\n' "$dir"
  if (( APPLY )); then qs log -p /usr/share/omarchy/shell --tail 300 2>&1 | sed 's/\x1b\[[0-9;]*m//g' > "$dir/qs-log.txt"; fi
  printf '$ omarchy-shell %s status > %s/status.json\n' "$ID" "$dir"
  if (( APPLY )); then omarchy-shell "$ID" status > "$dir/status.json" 2>&1; fi
  printf '$ omarchy plugin list --json > %s/plugins.json\n' "$dir"
  if (( APPLY )); then omarchy plugin list --json > "$dir/plugins.json" 2>&1; fi
  printf '$ hyprctl clients -j > %s/clients.json ; omarchy theme current > %s/theme.txt\n' "$dir" "$dir"
  if (( APPLY )); then hyprctl clients -j > "$dir/clients.json" 2>&1; omarchy theme current > "$dir/theme.txt" 2>&1; fi
  printf '$ grep -nE "(https?|rtsp|rtmp)://[^ ]*[@?]|password=|username=" %s/journal.txt %s/qs-log.txt (redaction check, expect no output)\n' "$dir" "$dir"
  if (( APPLY )); then
    grep -nE '(https?|rtsp|rtmp)://[^ ]*[@?]|password=|username=' "$dir/journal.txt" "$dir/qs-log.txt" 2>/dev/null && echo "    REDACTION FAILURE above" || echo "    redaction ok"
    printf '$ grep -c "omarchy-iptv" %s/journal.txt (our console lines)\n' "$dir"
    grep -c 'omarchy-iptv' "$dir/journal.txt" | sed 's/^/    /'
    echo "evidence written to $dir"
  fi
}

phase_uninstall() {
  note "uninstall"
  if (( APPLY )) && (( ! FORCE )); then
    if command -v gum >/dev/null 2>&1 && [[ -t 0 && -t 1 ]]; then
      gum confirm "Remove $ID, its cache, state and runtime dirs?" || fail "aborted"
    else
      fail "refusing to uninstall non-interactively without --force"
    fi
  fi
  run omarchy-shell -q "$ID" stop
  run omarchy plugin remove "$ID" --yes
  run rm -rf "$CACHE_DIR" "$STATE_DIR" "$RUNTIME_DIR"
  printf '$ diff <(jq -S . %s/shell.json.before) <(jq -S . %s) (expect no output: the bar entry is gone again)\n' "$EVIDENCE_DIR" "$SHELL_JSON"
  if (( APPLY )) && [[ -f $EVIDENCE_DIR/shell.json.before ]]; then
    diff <(jq -S . "$EVIDENCE_DIR/shell.json.before") <(jq -S . "$SHELL_JSON") && echo "    shell.json restored"
  fi
  printf '$ find ~ -path "*omarchy-iptv*" -not -path "*/omarchy-iptv-qa/*" 2>/dev/null (expect nothing)\n'
  if (( APPLY )); then find "$HOME" -path '*omarchy-iptv*' -not -path '*/omarchy-iptv-qa/*' 2>/dev/null | sed 's/^/    LEFT: /'; fi
  echo "by hand: remove the IPTV line from ~/.config/hypr/bindings.lua and the \"iptv\" entry from ~/.config/omarchy/extensions/omarchy-menu.jsonc if you added them"
  echo "evidence stays in $EVIDENCE_DIR (delete it yourself when the report is filed)"
}

case "$PHASE" in
  preflight) phase_preflight ;;
  install) phase_install ;;
  configure) phase_configure ;;
  verify) phase_verify ;;
  evidence) phase_evidence ;;
  uninstall) phase_uninstall ;;
  all) phase_preflight; phase_install; phase_configure; phase_verify ;;
esac
