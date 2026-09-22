# Changelog

All notable changes to Omarchy IPTV. Versions follow semver; the plugin
version lives in `manifest.json`.

## Unreleased

### Fixed
- **A single "runs forever" programme no longer wipes the whole guide.** Some
  providers mark a 24/7 stream as ending in the year 9999. One such entry was
  enough to corrupt the cached guide data for *every* channel on that source,
  so Now/Next simply vanished everywhere — with nothing reported, and
  refreshing rebuilt the same broken file. A subtler version of the same fault
  made a long-running programme look like it had finished years ago. (D-EPG-1)
- **Section labels are readable on every theme.** The headings above the group
  list and beside each form field were dimmed by a method that darkens rather
  than fades, which on light themes made them *darker* than the text they sit
  above -- so the heading came out bolder than the body instead of quieter.
  On three themes they were also simply too faint to read comfortably. They
  now fade toward the background, by an amount chosen per theme so a heading
  stays about as much quieter than the body text as it always looked.
  (D-RUNG-9)
- **Clicking a channel's number no longer toggles its favourite.** The
  favourite hit target was meant to start at the star slot, but the position
  it was given was rejected at build time and silently fell back to the row's
  left edge, so on a playlist with channel numbers the number column sat
  inside it. (D-CHNO-6)

## 0.7.3 (2026-09-22)

Selection you can actually see, and a favorites bug whose fix the last two
changelogs had already claimed. Everything visual here was measured on a real
screen across all twenty-three installed themes rather than computed and hoped
for.

### Changed
- **The cursor row is marked by a 2 px mark, and the accent now means
  "active" rather than "where you are".** The mark in the left gutter was
  always there; what changed is that it is now the whole answer on the channel
  list, the Sources list gained one, and the theme accent moved to the two
  places that mean a choice: which group is filtering the list, and which
  button a confirm dialog has selected. The mark is defined by brightness
  rather than colour, so it works on every theme and in greyscale.
- **The selected source row is finally visible.** The Sources list marked its
  cursor with a background tint alone, which on every installed theme is too
  faint to count as a marker, next to a border that every theme ships zero
  pixels wide. On the two action rows, and on any source that was not the
  active one, nothing at all showed which row `x remove` would act on.
- **The programme progress bar is easier to see.** It was drawn in the theme
  accent, a colour too close to the track it sits in: on nineteen of the
  twenty-three installed themes it fell below the visibility threshold for a
  graphical indicator, and no amount of brightening the accent could fix it on
  every theme. It is now drawn in the regular text colour, which clears the
  threshold everywhere. It no longer carries the accent hue. (D-RUNG-10)
- **Small counts and the footer line are bold**, which makes them readable on
  themes where they were previously below the accessibility threshold, without
  making them louder.

### Fixed
- **The selected group name was hard to read on eight themes.** It was drawn
  in the raw theme accent over the selection tint, which on eight of the
  twenty-three installed themes falls below the readability threshold, worst
  at 2.80:1. It now uses an ink calibrated per theme, clearing the threshold
  on all twenty-three while keeping the accent exactly as it was on the
  fifteen that never had a problem. Theme colours that carry transparency are
  now blended against the surface beneath them before the guide checks
  readability, so the check measures what you actually see. (D-RUNG-13,
  D-RUNG-15)
- **Favorites and recents now actually survive a provider credential change.**
  0.7.1 and 0.7.2 said they did, and the helper's half was right: it moved
  every saved reference onto the name-keyed scheme. But the shell then wrote
  the state it had loaded before the helper ran straight back over the file,
  on every fetch, so on a playlist without `tvg-id` the migration never took
  hold and a password rotation still orphaned favorites. The shell now moves
  its own copy of the state onto the new scheme whenever a channel list is
  applied, so its writes agree with the helper's. Found by observing the
  running plugin rather than the helper alone. (D-ID-3)

## 0.7.2 (2026-09-21)

The first release through the new pipeline, closing the three things the
marketplace review opened and held back so the reviewed code stayed
byte-identical.

### Fixed
- **The helper now reports the plugin's real version.** `bin/omarchy-iptv
  --version` and the User-Agent on every outbound request had said 0.2.0
  since 0.2.0; a constant nobody joined to the manifest. The version is now
  read from `manifest.json` beside the helper, and a test fails if the two
  ever differ. (D-REL-1)
- **One collection for the empty-state hint's group names.** The guide and
  its search fixture each carried a copy of the loop that decides which
  group names the hint may offer; now both call `Model.groupNamesForHint`,
  and the node suite pins its two shapes. (D-SG-2)

### Changed
- Comments in the shipped code no longer cite `CLAUDE.md` or `docs/`,
  `tests/` and `scripts/` paths that do not exist in an install; they name
  the engineering rule and the `dev` branch instead, and the release check
  now refuses a shipped source that names a dev-only path. (D-REL-2)

## 0.7.1 (2026-09-20)

A password change no longer empties your favorites, and what gets installed is
only the plugin.

### Fixed
- **Favorites and recents survive a provider credential change.** On a
  playlist with no `tvg-id`, a channel's identity used to be a hash of its
  stream URL, and that URL carries the account password, so rotating it
  silently orphaned every favorite and recent. Identity is now keyed by the
  channel's name where no `tvg-id` exists, and saved state is remapped on the
  first load after upgrade. (D-ID-1; live confirmation of the migration on an
  installed plugin is still owed, and is tracked on the board.)
- The README now documents the plugin's own `toggle` IPC verb, which was
  shipped but never listed; only the host's `shell toggle` and the `pip
  toggle` mode were.
- The README's list of files the plugin writes was wrong in both directions:
  it named `~/.cache/mpv/`, which the player has not written since the
  containment fix, and omitted the runtime `shader-cache` and `watch-later`
  directories it does.

### Changed
- **The published branch is the install artifact only.** `omarchy plugin add`
  clones the whole repository, so until now every install carried the design
  documents, the QA harness, developer scripts, and a root-level agent
  instruction file that a coding agent opened inside the plugin directory
  would obey. A marketplace reviewer found the last of those. `main` now
  holds an explicit allowlist of thirteen files exported from `dev` by a
  release script, and a gate check proves that list is whole. Updating an
  existing install fast-forwards to the lean tree and removes the rest.
- Two developer-script messages were reworded so they no longer read as
  invocations. No executed instruction changed; a gate check keeps the
  phrasing that way.

## 0.7.0 (2026-09-15)

Search tells the truth, and the text you read is readable.

### Changed
- **A group is found by its words, not by fragments of them.** On a playlist
  where every channel sits in one group, typing `sta` used to report every
  channel on the list as a match, because the group name was part of what each
  channel was searched against. On a real 3,335-channel list that happened for
  25 different queries, put over 1,500 irrelevant rows on the first page, and
  told you to keep typing when every genuine match already fitted on screen.
  Now a term that only appears in the group has to match a whole word there:
  `sta` reports 67, which is how many there are.
  Three consequences, all deliberate. Typing toward a group name passes through
  a gap where nothing matches yet, so the empty state names the group you are
  heading for rather than just saying no matches. A count can now grow as you
  type, when the extra letter completes a group word. And on a playlist with
  many groups, some searches return fewer rows than before; the group column
  still reaches those channels and one more keystroke brings them back.
- **The faintest text in the guide is no longer unreadable.** The footer status
  and hints, the group counts and the Sources count were drawn at a dimness
  that falls below the readable contrast threshold in every one of the 23
  installed themes, worst case by more than half. They are now drawn at the
  same level as the key names beside them, which means key names no longer
  stand out from the verbs; that trade is the cost of the footer being legible
  at all.

### Fixed
- **The bar icon, the one part of this plugin that is always on screen, was the
  least readable thing in it.** When idle it was below the readable threshold
  in 7 of the 23 installed themes. It is now clear of it in all 23, with the
  icon still visibly quieter than when something is playing on every dark
  theme.
  **Correction, 2026-09-15: the second sentence is wrong and this note is left
  in place rather than rewritten.** The measurement behind it modelled the bar
  as using the theme's own text colour. A capture of the running bar shows it
  draws at roughly half that, so its text tops out near 2.25:1 and no icon in
  it reaches the readable threshold, ours included. What the change did achieve
  is real and is confirmed on screen: the idle icon is no longer *bolder* than
  the playing one. Filed as D-RUNG-6.
- The password field in the Sources form had no label for a screen reader at
  all. It has one now. The property that was supposed to protect it turned out
  to do nothing on this version of Qt, in either direction, so it is gone and
  the documentation no longer promises it.

### Notes
- A comment in the code claimed a screen reader never receives your playlist
  URL. That was true of one channel and false of another: the value of a text
  field is published as well, so a revealed URL and the Xtream server and
  username are exposed. Nothing reaches a screen reader on this desktop at all
  today, for a separate reason reported upstream, so this is latent rather than
  live. The obvious fix was measured to break the Xtream login form outright
  and was refused; the proper repair is scheduled to land with the upstream fix.
- Two accessibility reports were filed upstream this release: one against
  Quickshell, whose windows publish nothing to assistive technology, and one
  against Omarchy, whose shell carries no roles or names at all.

## 0.6.0 (2026-09-15)

The guide at real provider scale. Mostly subtraction.

### Changed
- Rows show a second line only when it carries something that differs between
  them. On a playlist where every channel sits in one group, that line was the
  same text on every row, so it is gone and you see twelve channels at a time
  instead of nine. Walking a 3,335-channel list drops from 417 page presses to
  304.
- The group column no longer lists a group that contains everything, since
  choosing it narrows nothing. The column itself stays, with Recent, Favourites,
  All and Sources.
- The header shows where you are rather than repeating a total the footer
  already carries.
- The cursor no longer parks flush against the bottom edge, so you can always
  see there is more below. This is Omarchy's own behaviour from its menu.

### Fixed
- The failed-channel notice was hard to read on the selected row, which is the
  one place it matters, being the text that names the key to retry. It is now
  the most legible text on the row in every installed theme.
- Clearing a guide-data URL now removes its cache, so a warning it produced
  cannot come back after a restart.

### Notes
- The second line returns when guide data actually matches your playlist, not
  merely when a guide URL is set. Providers vary a great deal in whether their
  channels carry the identifiers that make that match possible.

## 0.5.0 (2026-09-14)

Picture in picture.

### Added
- Press `p` in the guide to shrink the player into a corner and keep watching
  while you work. Press it again to put it back exactly where it was, whether
  that was tiled, floating, or floating and pinned. The small window follows
  you across workspaces, and changing channel does not resize it.
- A new command does the same from outside the guide:
  `omarchy-shell io.github.rmcdavid.iptv pip toggle`. Three settings control
  the corner, the size as a share of your monitor, and the margin.

### Fixed
- The command that focuses the player window had not worked since 0.3.0, at
  four places, and failed silently because nothing read its result. It also
  identified the window by class alone, so with a second player open it would
  focus the wrong one. Both are fixed.

### Notes
- Picture in picture needs Hyprland configured with its Lua provider, which is
  the Omarchy default. Elsewhere the feature reports itself unavailable rather
  than half working.

## 0.4.0 (2026-09-14)

Channel numbers and numeric tuning.

### Added
- Type a channel number in the guide to jump to it. Digits select the channel
  and Enter plays it, so a mistyped number costs nothing. Subchannels like
  `7.1` work, and both the period and comma keys act as the separator because
  the numpad decimal differs by keyboard layout.
- A new command tunes straight to a number without opening the guide:
  `omarchy-shell io.github.rmcdavid.iptv channel 101`. Bind it to a key to
  change channel the way a television does.
- Channel numbers are read from the three attribute names providers use, and
  shown in the guide and the bar. A new setting sorts the list by number
  instead of the provider's order.
- If your playlist carries no channel numbers, typing a digit says so rather
  than ignoring you.

### Known limitations
- Re-typing the same number within the digit window reads as one longer
  number and reports a miss. It is visible and recoverable with one keypress,
  and it is the cost of never tuning you somewhere you did not ask for.

## 0.3.1 (2026-09-14)

### Fixed
- Changing channel immediately after the player starts no longer leaves the
  guide naming one channel while a different one plays. The starting player
  stands down when it finds a newer choice already applied, and the guide
  re-applies what you asked for rather than relabelling itself to match.
- Stopping a player that has stopped responding no longer leaves its socket
  file behind.
- The player's shader cache is kept inside the plugin's own directory instead
  of the cache directory shared with your other use of mpv.

### Internal
- A test-harness check that had never executed was repaired, and an audit
  found sixteen more checks in this project's own tooling that could report
  success without testing anything. All are fixed, each proven by reproducing
  the false all-clear and then showing it refused.

## 0.3.0 (2026-09-14)

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
