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

**Most of that list has shipped. See the roadmap below, which replaces it.**

## Roadmap (product owner, 2026-09-15, supersedes the M2 list above)

Ten releases, v0.1.0 to v0.7.0. Of the original M2 list, the Xtream helper,
multiple playlists, channel numbers and picture in picture are all shipped, and
the detached player and the guide at provider scale were added along the way.
What follows is what is actually left, in the order I would take it.

### 1. The two upstream reports, which gate real work

Neither is ours to fix and both block something:

| Report | Blocks |
|---|---|
| [quickshell#1144](https://github.com/quickshell-mirror/quickshell/issues/1144) | Nothing this plugin declares reaches a screen reader, so every accessibility rule we have written is unobservable, and D-A11Y-1's credential exposure stays latent |
| [omacom/omarchy#12009](https://github.com/omacom/omarchy/issues/12009) | The host shell carries no accessibility information at all, so even a fixed framework leaves the desktop unusable with a reader |

Nothing to build. Watch, and keep the harness ready for the day the first one
lands, because that is the day D-A11Y-1 stops being latent and becomes live.

### 2. Settle the thirty-one unverified fixes

Thirty-one board rows read `fixed` rather than `verified fixed`: a commit
repairs them and no test ran afterwards. That is structural, not sloppiness.
The QA record stopped being written three releases ago while four releases
shipped over it. One pass re-running the original repros settles most of them,
and it costs one session that holds the display. It should ride with the next
release rather than being scheduled alone.

### 3. Finish the contrast family

Four open rungs, and the calibration that unblocked them is done:

- **D-RUNG-6 (P2)** the bar's real surface is not what any fixture models, so
  its ceiling is about 2.25:1 and no icon in it can be made readable. Needs a
  fixture MEASURED from the running bar, and then a decision about whether our
  glyph should diverge from every other widget to be legible. It may also be
  worth reporting to Omarchy, since it affects every bar widget and not ours.
- **D-RUNG-7 (P3)** the runtime picks a different cursor ink than the model
  computes, in the safe direction. One probe printing three resolved tokens
  settles it.
- **D-RUNG-2 (P3)** the guide's dim second line. REFUSED with numbers and
  recorded as accepted risk. Reopen only against the conditions in
  `docs/CONTRAST-RULING.md`.
- **D-RUNG-5 (P3)** light-theme dimming inversion, narrowed but not closed.

### 4. Features, ranked by what the measurements say

- **M2-08 vertical bar layout.** Small, cosmetic, no blocker. The cheapest
  remaining thing a user would notice.
- **M2-04 channel logos.** Measured across the subscriber's own four playlists:
  1,396 of 5,221 channels carry one, 27 per cent, all from a single
  third-party host. It would be the first feature to fetch remote images on the
  user's behalf. Needs a privacy ruling before any design work, and the design
  has to lead with the three-in-four placeholder case.
- **M2-06 recording via ffmpeg.** Large. A second long-lived child process with
  a different lifecycle from the player, files of unbounded size outside the
  cache, and its own failure surface.
- **M2-07 catch-up and timeshift.** BLOCKED, and not on effort. Not one of the
  5,221 channels available here advertises catch-up, so not a single acceptance
  case could be verified against real data. Building it against fixtures alone
  is how the v0.2.0 defects happened.

### 5. Standing, not scheduled

- **D-PIP-3 (P3)** the player window renders translucent because our app id
  misses the host's media-opacity exemption, which matches on class.
- **The accessibility harness** needs the rest of its open items from
  `docs/QA-A11Y.md` section 9 before any filed run counts as evidence. Four
  acceptance criteria currently name it and none is satisfied.

### What is deliberately NOT on this list

No multi-monitor work: there is one output here, so nothing could be verified.
No packaging or distribution: the plugin installs from a git clone and that has
worked for ten releases. No settings UI beyond Sources: every remaining setting
is a number a user sets once.

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

Amended 2026-09-14, after rank 1 was built. v0.3.0 is now rank 1 alone, the
detached player, and channel numbers and picture in picture move to v0.4.0.
The reason is that rank 1 is finished, verified and independently valuable: it
removes the limitation users hit most and closes a security finding. Holding it
back to travel with two unrelated features would delay a real benefit and
bundle three feature's worth of risk into one release, for no gain. Smaller
releases, shipped when the work is done, beat planned bundles.

Standing constraints for every M2 lane, unchanged from M1: theme tokens only,
argv-only process launching, stdlib-only Python helper, no sudo, no writes
inside the plugin directory, URLs redacted to hosts at every sink, and the
overlay open budget of 150 ms with a 10,000 channel list.
