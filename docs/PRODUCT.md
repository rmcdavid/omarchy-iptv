# Omarchy IPTV — Product Vision & Requirements

Owner: Product Owner (team lead). Status: v0.1, governs milestone M1 (MVP).
Machine of record: Omarchy 4.0.3, Quickshell 0.3.1, Hyprland 0.56.2, mpv 0.41.

## One-liner

Live TV that feels like it shipped with Omarchy: one keystroke opens a
theme-native channel guide, type to find a channel, Enter plays it in mpv.

## Why

Omarchy users already have mpv, a keyboard-first desktop, and a real shell
plugin system (`~/.config/omarchy/plugins/<id>/`). Nothing today turns an M3U
playlist into a first-class, keyboard-driven TV experience that respects the
active theme. Existing Linux IPTV apps are heavy GTK/Qt/Electron programs that
ignore Hyprland/Omarchy conventions.

## Target user

- An Omarchy user with a legitimate IPTV source: a self-hosted Tvheadend /
  Plex / Jellyfin / Channels DVR M3U, a free public list (iptv-org, Pluto TV,
  Samsung TV Plus style M3Us), or a paid provider that hands out M3U + XMLTV
  URLs (including Xtream-Codes-style `get.php` / `xmltv.php` URLs).
- Keyboard-first. Expects vim keys, instant search, no mouse required.
- Wants to zap: search → Enter → watching, with under two seconds of interaction.

## Non-goals for v1

- No bundled content, channel lists, or provider accounts. Bring your own playlist.
- No DVR/recording, catch-up, VOD library, or multi-view. Backlog.
- No custom video renderer. mpv is the player; we drive it, we do not replace it.
- No bespoke settings GUI beyond what Omarchy's plugin settings schema gives us.

## Product decisions, locked for M1

1. Delivery form: a native Omarchy shell plugin (`manifest.json` + QML) installed
   with `omarchy plugin add <git-url> --enable`. Plugin id `io.github.rmcdavid.iptv`,
   display name "IPTV". The id is a one-line rename if published elsewhere.
2. Kinds: `bar-widget` + `overlay` (plus `service` only if the architect needs a
   persistent state owner). Bar widget = TV glyph + now-playing label. Overlay =
   fullscreen channel guide modeled on Omarchy's clipboard/emoji pickers
   (search-as-you-type, j/k, Enter).
3. Playback: exactly one mpv instance, driven over mpv's JSON IPC socket, so a
   channel change reuses the window and the bar can show now-playing and stop
   it. Never spawn a second player window.
4. Sources: one M3U/M3U8 playlist URL or local path, plus an optional XMLTV EPG
   URL (plain or gzip). Configured through the manifest settings schema (stored
   inline in shell.json, which is mode 0600). Xtream-style providers work by
   pasting their `get.php?...&type=m3u_plus` and `xmltv.php` URLs; a helper that
   builds those URLs from server/user/pass is M2.
5. Data pipeline: fetching and parsing happen outside QML in a stdlib-only
   Python 3 helper (precedent: the first-party dropbox plugin ships `status.py`).
   QML reads compact JSON caches. A 10k-channel playlist must not stall the shell.
6. Locations: config lives in shell.json (plugin settings); cache in
   `~/.cache/omarchy-iptv/`; favorites and recents in `~/.local/state/omarchy-iptv/`.
   Nothing inside the plugin directory is written at runtime.
7. Theme: every color comes from `Color.*` / `Style.*` tokens (menu surface for
   the overlay, bar tokens for the widget). No hardcoded colors except a
   documented `CONVENTION-EXCEPTION` comment.
8. Security: the plugin never uses sudo, never executes playlist content, and
   never interpolates playlist-derived strings into `bash -c`. URLs and headers
   from `#EXTVLCOPT` / `#KODIPROP` go to mpv or curl as argv items only.
9. Install flow: `omarchy plugin add <url> --enable`, set `playlistUrl`, press the
   key. Keybinding and menu entry are documented one-liners the user adds,
   because the Omarchy installer never runs plugin code.

## User stories, M1 (must)

- US1 Configure. Set playlist URL and optional EPG URL; the plugin fetches and
  caches; the bar shows a ready state. A failure shows a clear error inside the
  guide, not only on the console.
- US2 Browse. Open the guide with a keybinding (`SUPER + SHIFT + T`, verified free on this
  machine; `SUPER + CTRL + T` is already Activity) or by clicking the bar widget. Channels are
  grouped; filter by group; type to search name and group; j/k and arrows;
  PgUp/PgDn; Esc closes.
- US3 Watch. Enter plays the selected channel in mpv with the channel name as
  the window title. Enter on another channel switches inside the same window.
  A stream failure raises a desktop notification naming the channel.
- US4 Now playing. The bar widget shows a TV glyph and, on horizontal bars, the
  channel name. Left click = guide, right click = stop, scroll = previous/next
  channel in the current group, middle click = refresh playlist.
- US5 Favorites and recents. `f` toggles favorite; a Favorites group is pinned
  first; the last 10 played channels appear under Recent; both persist.
- US6 EPG. With an EPG URL set, rows show "Now: … until 21:30" and "Next: …".
  The guide never blocks on EPG loading.
- US7 Refresh. The playlist refreshes every N minutes (setting) and on `r`. A
  stale cache is used when offline, with a visible "cached" hint.
- US8 Install and uninstall. `omarchy plugin add …` works, `omarchy plugin
  validate .` passes, removal leaves only the cache and state directories, and
  the README says so.

## M2 (should, after M1 ships)

Xtream Codes URL helper, multiple playlists, channel numbers and numeric zap,
channel logos, catch-up, picture-in-picture mode via hyprctl float + pin,
recording via ffmpeg, first-class layout on vertical bars.

## Quality bar (definition of done for M1)

- `omarchy plugin validate .` passes. `qmllint` is clean with the `qs` modules
  mapped. No console warnings on load or on theme switch.
- Unit tests cover the parsers (M3U with `#EXTINF` attributes, `#EXTGRP`,
  `#EXTVLCOPT`, `#KODIPROP`; XMLTV plain and gzip, with timezone offsets) and the
  model logic (search, grouping, favorites, recents). The README documents the
  exact commands. All green.
- Manual QA on the live shell on this machine: install into
  `~/.config/omarchy/plugins/`, enable, exercise every user story with a real
  public playlist; `omarchy theme set <x>` re-skins the overlay without restart.
- Performance: the overlay opens in under 150 ms with a 10k-channel cache and
  typing stays responsive (filtering is bounded to displayed rows or done off
  the UI thread).
- Docs: README covers install, settings, keybinding and menu snippets, the
  keyboard map, troubleshooting, and uninstall.

## Team and handoffs

Product Owner → Project Manager (plan) ‖ Software Architect (ARCHITECTURE.md +
scaffold) ‖ UI/UX Designer (UX.md) → Front-end Developer builds M1 → QA verifies
against this document → Product Owner accepts.

## M2 scope decision (product owner, 2026-09-14)

v0.1.0 shipped the MVP and v0.2.0 shipped Sources (M2-01), which absorbed the
"multiple playlists" and "Xtream helper" backlog items. This section sets the
order for the rest of M2 so the team does not have to re-litigate it per lane.

Ranking rule: remove a shipped limitation before adding a feature; prefer work
that a real IPTV viewer feels every session over work that looks good in a
screenshot; prefer cheap items that become cheap only after a dependency lands.

| Rank | Item | Why now | Gate |
|---|---|---|---|
| 1 | M2-02 detached player | Removes the top known limitation (playback dies with `omarchy restart shell`) and closes security finding S-03 (stream URL on the command line). Everything else in the player area is easier afterwards. | Design doc `docs/ARCHITECTURE-PLAYER.md`, then lanes, then a live pass. |
| 2 | M2-03 channel numbers and numeric zap | The classic television interaction. Providers already ship `tvg-chno`, the helper already parses it into `chno`, and the guide reserves the digit keys. High value for the smallest new surface. | Digits select, a timeout commits, unknown numbers report it. |
| 3 | M2-05 picture in picture | Cheap once the player is detached: a Hyprland float/pin/resize rule applied over IPC to a window we no longer own as a child. Ships as a keybinding and a guide action. | Works with the detached player; no second window. |
| 4 | M2-04 channel logos | Real polish, but it is the first feature that fetches third-party images. Needs a disk cache, a size cap, a per-source directory, and a decision about contacting logo hosts at all (a privacy question, since logo URLs sit on the provider's CDN). Ships behind a setting, default on. | Cache under the source's cache dir, capped; no request without a configured playlist; guide stays inside the open budget. |
| 5 | M2-08 first-class vertical bar layout | Small, self-contained, and the only place the bar widget is knowingly degraded (glyph only). | Renders correctly in all four bar positions. |
| 6 | M2-06 recording, M2-07 catch-up and timeshift | Deferred out of v0.3.0. Both are large: recording needs storage management, naming, disk-full handling and a library surface; catch-up is provider-specific and cannot be tested without a provider that supports it. Revisit once 1 to 5 have shipped and real usage says which one matters. | Not scheduled. |

v0.3.0 is ranks 1 to 3. Ranks 4 and 5 ship in v0.4.0 unless a lane finishes
early. Ranks 6 stay in the backlog with no date.

Standing constraints for every M2 lane, unchanged from M1: theme tokens only,
argv-only process launching, stdlib-only Python helper, no sudo, no writes
inside the plugin directory, URLs redacted to hosts at every sink, and the
overlay open budget of 150 ms with a 10,000 channel list.
