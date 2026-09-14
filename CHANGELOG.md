# Changelog

All notable changes to Omarchy IPTV. Versions follow semver; the plugin
version lives in `manifest.json`.

## 0.3.0 (unreleased)

M2-02, the detached player. Playback no longer belongs to the shell.

### Added
- Playback survives `omarchy restart shell`. The player runs independently
  and the guide reattaches to it, recovering what is playing from the player
  itself. A theme change or installing another plugin also leave it alone.

### Security
- No stream address, credential or header value reaches any command line, on
  any channel including the first. The player starts empty and receives
  everything over a private socket. This closes finding S-03.
- The player no longer inherits your home directory. A screenshot taken with
  its own `s` key used to land in your home folder readable by anyone on the
  machine; it now goes to the plugin's own state directory, readable only by
  you. A resume position saved with `Shift+Q` was doing the same thing and is
  now contained as well.
- Options that hand a stream address to another program, such as enabling the
  download helper, now raise a warning in the guide when you use them. The
  options still work; ruling PO-5 keeps them available deliberately.

### Fixed
- A stop that lost a sequence race used to be a silent no-op, leaving the
  interface idle while the player kept playing.
- A failure the user already saw is no longer reported a second time when the
  guide later reattaches.

### Known limitations
- Removing or disabling the plugin while something is playing no longer
  guarantees the player stops with it. The README gives the command to stop a
  stray one, and logging out always reaps it.
- A stream that fails while the shell is down cannot raise a notification,
  because the notification service is the shell itself. The channel is marked
  as failed in the guide instead, the next time you open it.
- The channel's internal identifier and, on a failure, the channel's name are
  briefly visible to other local accounts in `ps`. No credentials are.

## 0.2.1 (2026-09-14)

Hotfix for two defects that made the Sources feature ineffective on a real
shell. Both were invisible to the automated suite because the dev harness
faked the one call involved.

### Fixed
- Switching to another source, activating a newly added source, and removing
  the active source now take effect immediately. Previously the setting was
  written correctly but the guide kept rendering the previous source, and a
  retry wrongly reported that settings could not be saved. Root cause: the
  Omarchy shell publishes a plugin's bar configuration one write behind, so a
  plugin never receives the echo of its own settings write. The service now
  applies its own write locally and yields to any external change, and the
  behavior is documented in `docs/OMARCHY-PLUGIN-CONTRACT.md`.
- Clearing the playlist URL at runtime clears the channel list and group
  column with it, instead of drawing the setup surface over a stale list.
- The guide surfaces warnings from the guide-data helper, matching the
  existing playlist warnings, with a documented precedence so a warning can
  never hide a failure.

### Changed
- The dev harness now reproduces the host's settings plumbing faithfully. A
  scenario suite that passed 51 of 51 against the broken code fails 23 against
  it after the correction.

## 0.2.0 (2026-09-13)

M2-01 Sources: configure and switch playlists from inside the guide.

### Added
- First-run input in the guide: type or paste a playlist URL or path (and
  an optional EPG URL); the fetch result is shown inline and nothing is saved
  on failure.
- Sources screen (`o` or the `Sources` row): history of playlists with
  label, host, counts, last used; switch (`Enter` / `Space`), add (`a`),
  Xtream Codes login form (`c`), edit (`e`), remove with confirmation (`x`).
- Per-source cache directories, so switching back is instant; the 0.1.0 cache
  is migrated automatically. State file schema v2 with migration.
- CLI parity: `omarchy bar set ... playlistUrl` and `epgUrl` are reflected
  in the history.
- Helper: `cache migrate|remove|prune`, `state source list|add|update|remove`,
  URL validation shared with the guide through one fixture.
- Dev harness: scenario suite and new verbs for the Sources flows.

### Security and privacy
- Clipboard content is treated as data (trimmed, control characters and
  newlines removed, length caps); only `http(s)` and absolute paths are
  accepted with no prefix guessing; saved URLs are masked in the UI and
  never appear in lists, transients, notifications, IPC output, or logs;
  credentials are never truncated silently; history records with control
  characters are dropped.

### Known limitations
- Multi-monitor placement and mouse gestures on the Sources screen were not
  exercised on the reference machine.

## 0.1.0 (2026-09-13)

First release: the M1 scope from `docs/PRODUCT.md`, verified by automated
gates, a harness QA pass (148 of 174 cases, the rest live-shell or mouse
cases), a security review, and a live-shell pass on the reference machine
(install, enable, settings, guide, playback, theme switch, shell restart).

### Added
- Omarchy shell plugin `io.github.rmcdavid.iptv` with three kinds: a bar
  widget (TV glyph, now-playing label, click/scroll actions), a fullscreen
  channel guide overlay (search mode and vim list mode, group column with
  Recent/Favorites/All, EPG now/next rows, favorites and recents), and a
  headless service that owns state and the single mpv instance.
- Stdlib-only Python helper `bin/omarchy-iptv` with subcommands `playlist`,
  `epg`, `play`, `stop`, `status`, `state`: M3U/M3U8 parsing (attributes,
  `#EXTGRP`, `#EXTVLCOPT`, `#KODIPROP`, multi-group titles), XMLTV parsing
  (plain or gzip, streaming, timezone offsets, now/next recompute), mpv JSON
  IPC control, atomic 0600 writes.
- Settings through the Omarchy plugin schema: `playlistUrl`, `epgUrl`,
  `refreshMinutes`, `mpvArgs`, `showChannelName`, `barLabelMaxWidth`,
  `maxRecents`.
- Shell IPC verbs `toggle`, `play`, `stop`, `next`, `previous`, `refresh`,
  `status`.
- Desktop notifications for stream failures, manual refreshes, playlist and
  EPG errors, and a missing mpv.
- `contrib/` snippets for the keybinding, the Omarchy menu row, and window
  rules; a dev harness under `scripts/dev-harness/`; `scripts/check.sh`
  running validate, qmllint, node, python, and QML spec tests.

### Security and privacy
- Process launching is argv-only; playlist-derived headers are validated and
  CR/LF-stripped; URLs never reach notifications, tooltips, console, or IPC
  output beyond scheme and host; the mpv window title disables property
  expansion; downloads have a 60 s deadline, refuse non-http(s) redirects, and
  drop credentials on cross-host redirects; playlists are capped at 50,000
  channels and 2,000 groups.

### Fixed before release
- Group column positions correctly on open and reopen with many groups.
- A player that ignores quit is terminated, then killed, within about four
  seconds; stop clears state immediately; play during shutdown relaunches.
- Playlist warnings (caps, overflow) are shown in the guide footer and in
  the IPC `status` output.
- Browsing with an empty query reaches every channel; only search results
  are capped at 200 rows.
- Setting an EPG URL from empty triggers the fetch immediately.

### Known limitations
- Clearing `playlistUrl` at runtime leaves the previous list drawn under the
  "No playlist configured" text until the guide is reopened (D-LIVE-19).
- The player is started by the shell, so `omarchy restart shell` ends
  playback.
- The first channel's stream URL is visible to other local accounts via `ps`
  for the life of the mpv process (later channels travel over the IPC socket).
- Vertical bars show the glyph only.
- Multi-monitor placement and the third-party replacement-bar path were not
  exercised on the reference machine (single output, stock bar).
