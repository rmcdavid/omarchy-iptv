# Changelog

All notable changes to Omarchy IPTV. Versions follow semver; the plugin
version lives in `manifest.json`.

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
