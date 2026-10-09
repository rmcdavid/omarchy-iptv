# Omarchy IPTV

Live TV that feels like it shipped with Omarchy: one keystroke opens a
theme-native channel guide, type to find a channel, Enter plays it in mpv.

Status: v0.13.3. Shipped so far: the MVP guide, Sources, the detached player
that keeps playing across a shell restart, channel numbers with numeric
tuning, picture in picture, pausing live TV and winding it back a few
minutes, a guide that remembers which
channels did not work, a channel wall that shows your channels as a grid of
tiles -- their logos if you have turned those on, their names either way --
hiding the groups you never want to see, and an audio and subtitle picker
for streams that carry more than one language. 0.8.0 gave the guide its
channel wall and 0.7.10 gave it pause and the dead-channel marks; the
releases that went to real provider scale, search accuracy and readable
contrast were 0.6.0 and 0.7.0, and the ones between built the Sources
screen, saved searches and channel logos.
`CHANGELOG.md` has the release notes.

This branch is the install artifact and nothing else: what `omarchy plugin
add` clones is exactly what the plugin needs to run. The design documents,
the product roadmap, the live build status, the tests and the tooling all live
on the `dev` branch, https://github.com/rmcdavid/omarchy-iptv/tree/dev, and contributors should start there.

The plugin ships no content. Bring a playlist you are entitled to use.

## Requirements

- Omarchy 4.x (the Quickshell shell with the plugin system) on Hyprland
- `mpv` 0.41 or newer on PATH (installed by default)
- `python3` (already a hard dependency of Omarchy through `uwsm`)
- An M3U/M3U8 playlist URL or local file, and optionally an XMLTV EPG URL
  (plain or `.gz`). Xtream-style providers: paste their
  `get.php?...&type=m3u_plus` and `xmltv.php?...` URLs.

## Install

```bash
omarchy plugin add https://github.com/rmcdavid/omarchy-iptv.git --enable
```

Then click the TV icon that appears in your bar — left click opens the guide —
and it starts on a form that asks for your playlist. **Add a paid
provider there, not on the command line.** The form masks what you type, and
nothing you enter reaches your shell history. `Add Xtream login` takes the
server, username and password as separate fields.

If you want to point it at a free, public playlist to try it out, that has no
credentials in it and a command line is fine:

```bash
omarchy bar set io.github.rmcdavid.iptv playlistUrl "https://iptv-org.github.io/iptv/countries/us.m3u"
```

The plugin id is `io.github.rmcdavid.iptv`. Enabling it places the bar widget
in the right section (`omarchy bar move io.github.rmcdavid.iptv --section center`
to move it) and enables the guide overlay and the background service too;
all three are one plugin.

Then add the keybinding and, optionally, the menu entry and window rules
from `contrib/` (the Omarchy installer never runs plugin code, so these are
one-line copies you make yourself):

- `contrib/bindings.lua` -> `~/.config/hypr/bindings.lua` (`SUPER + SHIFT + T` opens the guide; commented examples bind rewind, forward and back-to-live on `SUPER + SHIFT + H` / `L` / `R`, and pause, picture in picture and channel up/down on chords that are free on a stock Omarchy)
- `contrib/omarchy-menu.jsonc` -> `~/.config/omarchy/extensions/omarchy-menu.jsonc` (an `IPTV` row in the Omarchy menu)
- `contrib/windows.lua` -> `~/.config/hypr/looknfeel.lua` (keep the player opaque, optionally float it)

## Settings

Settings live inline on the widget's entry in `~/.config/omarchy/shell.json`
and are edited with `omarchy bar set io.github.rmcdavid.iptv <key> <value>`.
The guide, the bar widget, and the service all read that one entry. Playlist
and guide-data URLs from paid providers embed credentials, and they rest in
three files, readable only by you: that `shell.json` entry, the channel cache,
and `~/.local/state/omarchy-iptv/state.json`, which keeps the Sources history
and each source's URLs. The last two are the plugin's own files and it creates
them mode 0600. `shell.json` is not — it belongs to the shell, it can arrive
readable by everyone on the machine, and the plugin makes it private before it
puts a URL in it, which is the next paragraph. They are never shown or logged
beyond their host name. Two sentences in this file used to say two files,
which mattered because the third is the one you might think safe to copy into
a dotfiles repository.

**One permission the plugin changes on a file that is not its own.**
`shell.json` is the shell's settings file, shared by every bar widget you
have, and it does not always arrive private. The copy Omarchy ships is
readable by everyone on the machine; a `shell.json` created from it keeps
whatever your umask gives it, which is usually readable by everyone too, and
rewriting a file that already exists leaves its permissions alone — so a
machine that started out readable stays readable. Your provider URL goes into
that file, so before the plugin writes one it takes group and other access
away from that single file: on an ordinary 644 file that leaves it 600, which
is what `chmod 600 ~/.config/omarchy/shell.json` would do. Your own access is
not changed.
If the file is already private, nothing is changed and nothing is said.
Nothing else is touched: not `~/.config` or `~/.config/omarchy`, which are
shared with everything on your system and are not the plugin's business, not
any other file, and not one byte inside `shell.json`. A file only you can read
is enough on its own, whatever the directories around it allow.
If it cannot be made private — the file belongs to another account, or it is a
symlink, or the permissions will not change — then the source is **not saved**
and the guide says `Settings file is readable by other users`, with the command
to run yourself. Losing the setting is the better of the two outcomes. This is
not a one-off repair: the file can be recreated readable again later, by
`omarchy-refresh-config` among other things, and nothing tells a plugin when
that happens, so the check runs at every shell start and again before each
write. Between those moments the plugin is not watching, and a URL already in
the file would stay readable until the next one.

One place they can escape that, worth knowing, and one that used to:

- **Your shell history.** Setting a credentialed URL with `omarchy bar set`
  writes the whole thing into `~/.bash_history` or `~/.zsh_history`, where it
  stays until you remove it. Use the in-app form instead — that is what it is
  for. If you have already done it, `history -d` the line and check the file.
- **The process list, no longer.** Earlier releases passed that URL to the
  helper as a command-line argument when fetching your playlist or your guide
  data, and a command line is readable by every account on the machine from
  `/proc` for as long as the process runs. Both URLs carry your credentials
  on an Xtream provider: the playlist URL and the `xmltv.php` guide URL are
  built from the same username and password. A marketplace reviewer asked
  why that was accepted, and it is not any more: the plugin now hands the
  URL to the helper in its environment, as `OMARCHY_IPTV_URL`, which `/proc`
  then refuses to everyone but root -- not other accounts, and not other
  programs running as you either -- before it loads anything else. The
  moment between the helper starting and that point is the only window
  left: about a tenth of a second on an idle machine, longer on a busy one,
  and readable in that moment by programs running as you alone, never by
  other accounts. The helper's command line no longer
  carries it. That is true of all three fetches that take a URL -- your
  playlist, your guide data, and the check the Sources screen makes before it
  accepts a source. Nothing else on the plugin's side writes
  either URL anywhere but the three files above.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `playlistUrl` | string | `""` | `http(s)://` URL or absolute path of the M3U/M3U8 playlist |
| `epgUrl` | string | `""` | XMLTV URL (plain or gzip), optional. If your playlist names its own guide and you leave this empty, that one is used and the Sources screen says so. Channels are matched by id and, when the ids do not agree, by name -- which is usually what happens, because playlists and guides rarely come from the same place |
| `refreshMinutes` | integer 15-1440 | `360` | playlist and EPG refresh interval (providers rate-limit playlist downloads; keep it high) |
| `mpvArgs` | string | `""` | extra mpv options, space-separated `--key=value` tokens, e.g. `--profile=low-latency --hwdec=auto-safe`. Options that would write your stream address somewhere durable are refused, and so is `--load-scripts`: the plugin's player loads no mpv scripts, because one of them publishes your playlist URL on the desktop message bus. `--demuxer-cache-unlink-files` is refused too, because with it turned off a copy of the stream can outlive the player at a path nobody listed, and `--cache-on-disk` is accepted with a warning in the guide's footer, because it writes the stream to your disk for as long as a channel plays. The one lever on how far back you can rewind is `--demuxer-max-back-bytes`, which is deliberately not refused: it costs RAM, about 35 to 80 MiB per minute of history at the bitrates this was measured on (4.7 to 10 Mbps), so thirty minutes is 1 to 2.4 GiB per player, and the plugin does not set it for you. `--tls-verify` is refused as well, because the player must check your provider's certificate; a provider whose certificate is self-signed or signed by a private CA is served by `--tls-ca-file=/path/to/ca.pem`, which is accepted -- see below |
| `showChannelName` | boolean | `true` | show the channel name next to the TV glyph on horizontal bars |
| `barLabelMaxWidth` | integer 60-600 | `180` | width (px) at which the bar label is cut with an ellipsis |
| `maxRecents` | integer 1-50 | `10` | size of the Recent list |
| `channelOrder` | string | `playlist` | `playlist` keeps the provider's order; `number` sorts by channel number when the playlist has them |
| `numberEntryMs` | integer 400-5000 | `2000` | how long to wait between digits before jumping |
| `barShowChannelNumber` | boolean | `true` | show the channel number in the bar |
| `showLogos` | boolean | `false` | show channel logos. Off until you turn it on, because logos are fetched from the third-party hosts your playlist names -- see below |
| `pipCorner` | string | `top-right` | which corner the picture-in-picture box sits in: `top-right`, `top-left`, `bottom-right`, `bottom-left` |
| `pipSizePercent` | integer 15-60 | `30` | width of the box as a percentage of the monitor (a proportion, so it is right on a laptop and on a large screen) |
| `pipMargin` | integer 0-200 | `16` | gap between the box and the screen edge, in pixels |

**Channel logos are off by default, and turning them on tells you the cost first.** Logos are hosted by third parties named in your playlist, not by this plugin, so showing them means fetching pictures from whoever the playlist author pointed at. On the list this was measured against that was 63 different hosts, one of them covering two thirds of the channels. Nothing is contacted until you say so: press `g` on the Sources screen and the guide tells you how many hosts it would contact and which one gets the most, counted from your own cached playlist without making a single request. Turning it back off is one keypress and no dialog, and it stops a fetch already in progress -- but the pictures it already downloaded stay on disk, because a cache you might want again in a minute should not be thrown away by a toggle. When you do want the space back, `python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv cache logos-clear --key <key>` deletes one source's logos and nothing else: its channel list, its guide data and the source itself are untouched. `ls ~/.cache/omarchy-iptv/sources/` names the keys. Logos are `https` only, fetched once and cached under `~/.cache/omarchy-iptv/`, never re-fetched while the file is there, and a logo request carries none of your playlist's credentials, headers or query string -- a redirect to a non-`https` host is refused rather than followed. A channel with no logo gets empty space rather than a placeholder box, and the column is not drawn at all on a list that has none. The same helper's `logos` subcommand prints that survey from the command line and makes no request. Names, groups, guide titles and every other string the plugin itself draws from a playlist or a guide feed are drawn as plain text (the strings it hands to the shell are drawn by the shell as plain text too, except the body of a failure toast, which the shell's notification card draws behind its own image-tag stripper), so a playlist cannot route around that switch by hiding a picture tag inside a channel name. One caption on the channel wall did let it through: a marketplace reviewer reported that against 0.9.2, and 0.9.3 closes it.

One warning about `mpvArgs`. Options are filtered, and the ones the plugin
needs for itself are refused, but a few legitimate options change where your
stream address ends up. In particular `--ytdl=yes`, the documented way to play
links that are not direct streams, hands the full address to a separate
program, and that program puts it on its own command line where other local
accounts can read it for as long as it runs. The plugin keeps the option
available because it is the only way some sources work. Use it knowing the
cost, and prefer a direct stream address when you have one.

**The player checks your provider's certificate.** Up to and including 0.12.1
it did not. mpv leaves its own `--tls-verify` off unless something turns it
on, so the player asked FFmpeg not to check, and anyone able to sit between you
and an `https` provider could have presented their own certificate, served you
their own video, and kept the username and password your stream address and
your provider's headers carry. A marketplace maintainer reported it; it is on
now. Verification is set in the player's own options and set AGAIN as the very
last option, after yours, so an ordinary token of yours cannot switch it back
off -- not `--tls-verify=no`, and not a `--profile` naming a profile in your
own mpv config that turns it off, which is why that second one is there and is
not a duplicate to be tidied away. One kind of token the last word cannot
reach, because it configures the media library rather than the player:
`--stream-lavf-o` forwards settings straight through, and it is refused for
that reason.

`--tls-verify` and `--stream-lavf-o` are refused rather than quietly
overridden. Be aware of where that refusal goes: it is written to the shell's
log, not shown to you in the guide, so if a token of yours seems to do nothing,
that log is where to look.

If a player is already running when you update, the plugin does not leave it
that way. The first time the new shell picks that player up it turns
verification on inside it and then tunes your channel again, because the
stream already open was opened without it -- so expect one short rebuffer,
once, and nothing for you to do. If that player will not accept the change it
is stopped instead of being handed your stream address again: press Enter on
the channel and a fresh, verified player starts.

The cost, because it is not free for everyone: a provider whose certificate is
self-signed, or signed by a CA your system does not already trust, stops
playing until you name that CA with `--tls-ca-file=/path/to/ca.pem` in
`mpvArgs`. That is the supported way round it, and it is deliberately the only
one -- trusting one named CA is a far smaller exposure than switching
verification off for every provider you ever add. The plugin's own playlist and
guide downloads over `https` always verified; this was the player, and only the
player.

## Using it

Press `SUPER + SHIFT + T` (or click the TV glyph in the bar). The guide opens
in search mode: type part of a channel or group name, `Enter` plays it in mpv
and closes the guide. Press `Tab` (or `/`) to switch to list mode, where the
vim keys and single-letter commands are live.

Guide keys (the full map is section 3 of the UX spec on the `dev` branch):

| Mode | Key | Action |
|---|---|---|
| search | letters, digits, space | filter channel name and group |
| search | Up / Down, PgUp / PgDn, Home / End | move the cursor. On the channel wall Up / Down move a whole row of tiles |
| search | Left / Right | in the list: previous / next group in the column. On the channel wall there is no group column, and they move the cursor one tile |
| search | Enter | play and close; Esc clears the query, then closes |
| search | Ctrl+S | save this search into Favorites: its channels join your starred ones, and the confirmation says how many rows Favorites gained -- which is fewer than the search matched if you had already starred some of them |
| search | Tab or Shift+Tab | switch to list mode (query stays) |
| list | j / k | move the cursor. On the channel wall: move a whole row of tiles |
| list | h / l | change group. On the channel wall there is no group column, and they move the cursor one tile |
| both | Ctrl+G | switch between the channel list and the channel wall: a grid of tiles showing each channel's name, and its logo if channel logos are on. Works either way -- logos are off by default and the wall does not need them |
| list | Enter | play, close, focus the player |
| list | Space | play and keep the guide open (zap while watching) |
| list | f | toggle favorite |
| list | x | remove whatever put this row here. In Recent: forget the recent. In Favorites: unfavorite it if you starred it, or -- if a saved search put it there -- forget that whole search, which takes its other rows with it; the confirmation says which search and how many channels. Anywhere else: hide the group this channel is in. Hidden groups move to a HIDDEN section at the bottom of the group column; go there and press `x` again to bring one back |
| list | s | stop playback |
| list | `0`-`9` | type a channel number to jump to it. It selects the channel; press Enter to play |
| list | `.` or `,` | subchannel separator, for numbers like `7.1`. Both keys work, because the numpad decimal differs by keyboard layout |
| list | c | pause or resume the live stream. The pause lasts until mpv's forward buffer fills, about four and a half minutes on the 4.7 Mbps channel it was measured on, less on a higher bitrate; a long pause also spends the rewind window, see `b`. Bind a key to `omarchy-shell io.github.rmcdavid.iptv pause` to reach it while the guide is closed |
| list | b | go back ten seconds in what already played. Live TV here is rewindable inside the buffer mpv keeps anyway: how far depends on the channel's bitrate and is shown, never promised -- the bar tooltip says `up to 6:52 back` from the last reading, and when you hit the floor the footer says so instead of silently doing nothing. Offered only while something plays and the player has history to go back into |
| list | w | forward ten seconds, towards live. Offered only while you are behind live |
| list | g | back to live. After a deep rewind this lands at the edge of what was buffered and says how far behind that still is; it never reloads the channel on its own, because that would throw the whole window away. Enter on the row is the reload |
| list | t | while something plays: choose the audio track and the subtitles. A small panel lists what the stream carries; `j`/`k` move, `Enter` selects, `Esc` closes. List mode only -- in search mode `t` is just a letter you are typing |
| list | i | read what is on: a panel over the list with the programme's name, the channel it is on, when it runs, its category and episode where the guide gives them, the description, and what is on next. `j`/`k` scroll it, `Esc` closes. Needs guide data for that channel |
| both | ? | every key, in one overlay, built from the same table the hint row is built from -- so a key the plugin learns cannot be missing from the list. `Esc` closes. In search mode it opens on the empty query, where a first-time reader is most likely to press it |
| list | p | picture in picture: shrink the player into a corner, or put it back |
| list | r | refresh playlist and EPG now |
| list | / or Tab | back to search mode; Esc clears the query, then closes |

Lists: Recent and Favorites are pinned at the top of the group column, then
All, then every group in playlist order, with Ungrouped last. A group you hide
with `x` leaves All, the group list and search, and sits dimmed under HIDDEN at
the bottom of the column until you bring it back; your starred favorites,
your recents and channel numbers still reach its channels, because those are
things you chose one at a time. A saved search does not: a saved search is a
search, and search does not look inside a hidden group. Browsing with an
empty query reaches every channel in the list; only search results are capped
at 200 rows (the footer says `keep typing`). With an EPG configured, rows show
what is on now, when it ends, and what is next. If a guide-data fetch fails,
a banner stays until the next successful fetch while the old data keeps
working. Pressing `r` before a playlist is configured just says
`Set a playlist first`.

Bar widget: left click opens or closes the guide, right click stops
playback, the scroll wheel zaps through the list the channel was started
from, middle click refreshes. Hover for the full channel name.

Shell IPC verbs, usable from any keybinding or script:

```bash
omarchy-shell shell toggle io.github.rmcdavid.iptv       # open / close the guide
omarchy-shell io.github.rmcdavid.iptv toggle             # the same thing, as the plugin's own verb
omarchy-shell io.github.rmcdavid.iptv play t:bbc1.uk      # play a channel id from the cache
omarchy-shell io.github.rmcdavid.iptv next                # zap forward
omarchy-shell io.github.rmcdavid.iptv previous            # zap back
omarchy-shell io.github.rmcdavid.iptv channel 101         # tune straight to channel 101
omarchy-shell io.github.rmcdavid.iptv pip toggle          # picture in picture on / off
omarchy-shell io.github.rmcdavid.iptv pause               # pause / resume live TV
omarchy-shell io.github.rmcdavid.iptv back 30             # rewind 30 s; JSON reply. The argument is required by the shell's IPC: `back ""` is the 10 s step, a bare `back` is refused before it reaches the plugin
omarchy-shell io.github.rmcdavid.iptv forward 30          # forward 30 s (default 10); JSON reply
omarchy-shell io.github.rmcdavid.iptv live                # back to live; JSON reply
omarchy-shell io.github.rmcdavid.iptv stop
omarchy-shell io.github.rmcdavid.iptv refresh
omarchy-shell io.github.rmcdavid.iptv status              # JSON
```

## Pause and rewind

Press `c` in the guide's list mode to pause live TV, and `c` again to carry
on from where you stopped -- you are then watching a little behind live. The
bar shows a paused glyph and says so in its tooltip. The pause lasts until
mpv's forward buffer fills: about four and a half minutes on the 4.7 Mbps
channel it was measured on, less on a higher bitrate.

Press `b` to go back ten seconds in what already played, `w` to come forward
ten, and `g` to return to live. Live TV is rewindable here because mpv keeps
a buffer of what it has already shown, on the settings the plugin already
passes -- nothing is recorded, nothing is written to disk, and the plugin
does not enlarge anything. How far back that buffer reaches depends on the
channel's bitrate, so the number is per channel and the guide shows it rather
than promising it: the bar reads `-1:32` while you are behind live, the
footer says `1:32 behind live` ahead of the channel name, and the bar
tooltip adds `up to 6:52 back` from the last reading. After each seek the
player itself draws the same number for three seconds, so a rewind is
visible in fullscreen with the bar hidden; `--osd-level=0` in `mpvArgs`
turns that line off. On the public list this was measured against, the
window on mpv's defaults ran from about two and a half minutes to over
eighteen, with half the channels above six minutes, and 31 of the 32 channels
that played rewound eighteen to twenty of the twenty seconds asked of them; your provider will
differ. Two things
worth knowing. A long pause spends the window, at one second of history per
paused second once the buffer is full, and the number on the bar shows it.
And when you ask for more than the buffer holds the plugin goes as far as it
can and says so (`As far back as it goes`); mpv on its own would have done
nothing in silence. A channel change starts a fresh buffer, so there is no
rewinding into the previous channel.

Because you usually want all of this while watching rather than while
browsing, every one of these is also on the plugin's IPC: `pause`, `back
[seconds]`, `forward [seconds]` and `live`, each replying in JSON so a refusal
is reported rather than a false success. `contrib/bindings.lua` carries
commented examples on `SUPER + SHIFT + H` (back), `SUPER + SHIFT + L`
(forward) and `SUPER + SHIFT + R` (live), with the step as the verb's
argument.

## Picture in picture

Press `p` in the guide's list mode while something is playing. The player
window floats, shrinks to a corner box sized from your monitor, and is pinned
so it follows you between workspaces; your other windows lay themselves out as
if it were not there. Press `p` again and it goes back where it came from,
including the exact rectangle if it was floating before.

From outside the guide, `omarchy-shell io.github.rmcdavid.iptv pip toggle`
(also `pip on` and `pip off`). `contrib/bindings.lua` has a commented line
that binds it to `SUPER + SHIFT + I`; an earlier copy suggested
`SUPER + SHIFT + P`, which stock Omarchy already uses for Google Photos.

Nothing goes into your Hyprland configuration for this. The plugin asks the
compositor at runtime and writes no file at all.

Changing channel keeps the box where it is. So does switching theme, and so
does `omarchy restart shell` -- the window belongs to the compositor, not to
the shell, and the guide picks the state back up. Stopping playback ends it,
because the window it was applied to is gone; play again and press `p` again.

**It is not "always on top".** Hyprland has no such window state, so there is
none to ask for. What you get is a small window that stays with you: it floats
above the tiling layout and follows you across workspaces, but another
floating window you focus afterwards can cover it. Anything that promised you
a window nothing can cover would be wrong.

Three settings control the box (see the Settings table): which corner, how
wide as a percentage of the monitor, and the margin from the screen edge.

Known limits:

- Verified on Hyprland 0.56.2 with a Lua config provider. Other versions are
  untested; without Hyprland the key says so and does nothing.
- Multi-monitor placement is untested. PiP uses the monitor the player is on
  and does the scale and rotation arithmetic, but no second monitor was
  available to try it on. What happens when you unplug the monitor holding a
  pinned box is not established either.
- If you have pasted the optional float rule from `contrib/windows.lua`, see
  the caveat in that file: whether a static size rule re-applies underneath
  PiP has not been measured.

## Sources (playlists inside the guide)

You no longer need the terminal to configure a playlist. On first run the
guide shows an input: type or paste (`Ctrl+V`) a playlist URL or absolute
path, optionally an EPG URL, and press `Enter`. The guide fetches it and
shows the result inline (`1,475 channels in 28 groups`, or the reason it
failed). Nothing is saved if the fetch fails, and nothing is saved if the
shell's settings file cannot be made private first (see Settings above).

Press `o` in list mode (or pick the `Sources` row at the bottom of the group
column) to open the Sources screen: every playlist you have used, with its
label, host, channel count, and when it was last used. Each source keeps its
own cache, so switching back is instant.

| Key | Action |
|---|---|
| `j` / `k` | move |
| `Enter` | switch to the source and return to the guide |
| `Space` | switch and stay on the list |
| `a` | add a source (URL or path) |
| `c` | add an Xtream Codes login (server, username, password); the URLs are built for you |
| `e` | edit label, playlist URL, or EPG URL |
| `x` | remove the source and its cache (asks first) |
| `g` | channel logos on or off. Turning them on tells you first how many third-party hosts it would contact, and waits for you to agree |
| `Esc` | back to the guide |

In a form: `Tab` moves between fields, `Ctrl+V` or `Shift+Insert` pastes,
`Ctrl+U` clears the field, `Enter` saves, `Esc` cancels. Saved URLs are shown
masked (`password=****`); press `Ctrl+R` or the eye button to reveal one
while editing. Only `http://`, `https://`, and absolute paths are accepted,
and no prefix is guessed.

`omarchy bar set ... playlistUrl` still works and shows up in the Sources
list as well; the two stay in sync. Up to 50 sources are kept.

One caveat if you keep **two lists from the same provider** — a full one and a
filtered one, say. Favourites are shared across sources on purpose, and a
channel is normally recognised by the id its provider gives it. When a playlist
does not give its channels ids, the plugin has to recognise them by name
instead, and a channel whose name is unique in one of your two lists but shared
in the other (an HD and an SD version, typically) can lose its star from one of
them when you switch. Star it again on the list you are using. Playlists that
carry channel ids — most do — are not affected at all.

## Playback notes

- One mpv window, class `omarchy-iptv`, titled with the channel name.
  Switching channels reuses it.
- Streams that carry more than one audio language, or subtitles, can be
  switched from the guide: `t` in list mode while the channel plays. The
  choice lasts as long as the channel does: changing channel goes back to
  whatever the new stream says is its own default, because a track number
  means something different on every stream. Remembering a preferred
  *language* is a different feature and is not here yet.
- Playback survives `omarchy restart shell`. The player runs on its own and
  the guide reattaches to it, so a restart, a theme change or installing
  another plugin all leave what you are watching alone.
- A stream that fails shows a desktop notification naming the channel, and
  the guide marks it until the channel plays again. A channel that simply
  ends is silent: the window closes and nothing is reported, because nothing
  went wrong.
- Stop clears the bar and guide immediately. If mpv ignores the quit request
  it is terminated, and if it ignores that too it is killed, within about
  four seconds. Playing a channel while the old player is still shutting
  down starts a fresh player once it has exited.
- No stream address, credential or header value ever reaches **the player's**
  command line. The player starts empty and receives all of it over a private
  socket only you can read. Two things are briefly visible to other local
  accounts in `ps`: the channel's internal identifier while a change is being
  issued, and the channel's name while a failure notification is being sent.
  Your playlist URL and your guide-data URL, each of which on an Xtream
  provider carries your username and password, no longer appear anywhere on
  a command line the plugin starts: they reach the helper in its
  environment, which other accounts cannot read, as described under "The
  process list, no longer" above. This sentence has been wrong twice: it
  said "any command line", which denied all four things then visible, and
  then said "three things", which omitted the guide-data URL. A list that
  counts itself has to be counted; the two items that mattered came off this
  one because the exposure itself is now closed, not merely disclosed.
- Two consequences of the player being independent, both deliberate. If you
  remove or disable the plugin while something is playing, the player is no
  longer guaranteed to stop with it. Disabling the plugin does stop it, in
  about seven seconds. Removing it does not, because the files are deleted
  moments before the stop can run. See Uninstall for how to reap a stray
  player, or simply log out, which always reaps it. And a stream that fails while the shell is down
  cannot raise a notification, because the notification service is the shell
  itself; the channel is marked as failed in the guide instead, the next time
  you open it.
- Channel names are shown verbatim except that leading dashes are stripped
  and mpv property expansion is disabled for the window title.
- The player window is rendered slightly translucent under the Omarchy
  defaults. Omarchy exempts media players from its default opacity by class
  name, and ours is `omarchy-iptv` rather than `mpv`, so the exemption misses
  it. The first line of `contrib/windows.lua` fixes it.
- The player's own keys work. mpv's normal key bindings are live on the
  player window, and two of them write files. `s` saves a screenshot to
  `~/.local/state/omarchy-iptv/screenshots/`, and `Shift+Q` saves a resume
  position under `$XDG_RUNTIME_DIR/omarchy-iptv/watch-later/`, which is
  cleared when you log out. Both are readable only by you. Screenshots used
  to land in your home directory readable by anyone on the machine; to put
  them somewhere else, add `--screenshot-dir=/path` to `mpvArgs`. mpv's own
  arrow keys seek inside the same buffer the guide's `b` and `w` use; the
  bar's behind-live number catches up with them on its next ten-second
  status read rather than at once.

## Limits

- Playlists are capped at 50,000 channels and 2,000 groups; extra channels
  are skipped and extra groups fold into Ungrouped. The guide footer shows
  `Playlist warning: ...` after such a load, and the warnings are also in
  `~/.cache/omarchy-iptv/playlist-status.json` and in the output of
  `omarchy-shell io.github.rmcdavid.iptv status`.
- Downloads (playlist and EPG) must finish within 60 seconds; redirects to
  anything but http(s) are refused and credentials are dropped when a
  redirect changes host.

## Picture in picture settings

Press `p` in the guide's list mode to shrink the player into a corner of your
screen and keep watching while you work. Press it again to put it back. From
outside the guide, `omarchy-shell io.github.rmcdavid.iptv pip toggle` does the
same and can be bound to a key.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `pipCorner` | string | `top-right` | which corner the small window sits in |
| `pipSizePercent` | integer 15-60 | `30` | its width as a share of the monitor |
| `pipMargin` | integer 0-200 | `16` | gap from the screen edge, in pixels |

Two honest notes. It is not "always on top" in the sense of a window state you
can ask for, because Hyprland has none. What you get is a small window that
floats above the tiling layout and follows you across workspaces. In testing it
stayed on top through focusing other windows, raising them explicitly and
fullscreening them, but since nothing guarantees that, treat it as reliable in
practice rather than promised. And the feature needs Hyprland configured with
its Lua provider, which is the Omarchy default; on any other provider it reports
itself unavailable rather than half working.

## Files it writes

- `~/.cache/omarchy-iptv/sources/<key>/` : one directory per source with
  `channels.json`, `playlist-status.json`, `epg-now.json`, `epg-status.json`
  (safe to delete; rebuilt on refresh). A 0.1.0 single cache is migrated on
  first start.
- `~/.local/state/omarchy-iptv/state.json` : favorites, recents, last
  played, your saved searches, the groups you have hidden, the player
  session record, and the Sources history including their URLs (mode 0600). Channels that failed to play are
  **not** kept here: they belong to the source that carried them, and live in
  that source's cache directory below
- `~/.cache/omarchy-iptv/sources/<source>/failed.json` : which channels of
  that source failed to play, and when (mode 0600). This is what lets the
  guide tell you a channel did not work last time instead of making you press
  Enter to find out. A mark is dropped when the channel plays again, when it
  is a fortnight old, when the channel leaves your playlist, and when you
  remove the source
- `~/.local/state/omarchy-iptv/screenshots/` : screenshots you take with the
  player's own `s` key (mode 0600)
- `$XDG_RUNTIME_DIR/omarchy-iptv/` : the player's private socket (`mpv.sock`)
  while it is running, a small lock file (`player.lock`, one line, no
  address) used to guarantee only one player exists, and
  two directories that exist only until you log out -- `shader-cache` for
  mpv's compiled shaders and ICC profiles, and `watch-later` for its resume
  records. Both would otherwise land in `~/.cache/mpv/` and
  `~/.local/state/mpv/`, outside this list; the player is pointed at the
  runtime directory instead so nothing durable accumulates in your home.
  A shader cache is content-free and is not keyed to what you watched.
  This is a default rather than a guarantee: neither path is reserved, so
  an `mpvArgs` token of your own can still send them elsewhere.

One file in this list is not the plugin's:

- `~/.config/omarchy/shell.json` : the shell's own settings file, which holds
  this plugin's entry along with every other widget's. The plugin writes its
  entry through the shell, the same way any widget does, and it changes one
  thing about the file itself — the permissions, so that only your account can
  read it, because your playlist and guide-data URLs are stored there. Not the
  contents beyond its own entry, and not the directories around it. See
  Settings above for what happens when that cannot be done.

Nothing inside the plugin directory is written at runtime.

## Troubleshooting

- "No playlist configured": the guide opens on a form that asks for your
  playlist -- paste it there. That form masks what you type and the value
  never reaches your shell history, which `omarchy bar set` cannot avoid;
  use the command line only for a free public list you do not mind storing
  in plain text.
- "Settings file is readable by other users": the guide would not save your
  source, because it could not make `~/.config/omarchy/shell.json` private and
  your provider URL would have gone into a file other accounts can read.
  `ls -l ~/.config/omarchy/shell.json` first. If it is yours and a regular
  file, `chmod 600 ~/.config/omarchy/shell.json` and add the source again.
  If it belongs to another account or is a symlink, the plugin refuses to
  change it rather than guess, and that is yours to sort out.
- The guide's status line shows the helper's own error text (host name only,
  never the URL). To see the same JSON in a terminal, for a free list:
  `python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv playlist --url <url>`.
  Do not do this with a URL that carries your provider username and
  password: typed at a prompt it is written to your shell history for good
  (see Settings above), and so is a `OMARCHY_IPTV_URL=... python3 ...`
  prefix -- an earlier version of this paragraph recommended exactly that,
  which was the shell-history exposure wearing a different coat. If you must
  run it by hand with a paid provider, let the shell read the URL without
  echoing or recording it, then forget it: `read -rs OMARCHY_IPTV_URL &&
  export OMARCHY_IPTV_URL`, run the command without `--url`, then
  `unset OMARCHY_IPTV_URL`. Or just use the guide, which is what it is for.
- Shell console: `qs log -p /usr/share/omarchy/shell --tail 100`.
- After editing `Service.qml` run `omarchy restart shell` (kept-loaded
  services do not hot-reload).

## Uninstall

```bash
omarchy plugin disable io.github.rmcdavid.iptv
omarchy plugin remove io.github.rmcdavid.iptv
rm -rf ~/.cache/omarchy-iptv ~/.local/state/omarchy-iptv   # optional
rm -rf "$XDG_RUNTIME_DIR/omarchy-iptv"                     # optional, cleared at logout anyway
```

Disable first. Disabling stops a running player; removing on its own deletes
the plugin's files moments before its own stop can run, which leaves the
player playing with no way to stop it from the plugin.

If a player is already stranded, this needs nothing installed. Look first,
then kill:

```bash
pgrep -af -- '^mpv .*--wayland-app-id=omarchy-iptv'
```

```bash
pkill -f -- '^mpv .*--wayland-app-id=omarchy-iptv'
```

Keep the `^mpv ` at the start of the pattern. Without it the pattern also
matches the shell you paste it into, and kills that too. Logging out reaps a
stranded player regardless.

Removal leaves only those directories behind, plus the keybinding, menu,
and window-rule lines you added by hand.

Note on disabling: `omarchy plugin disable io.github.rmcdavid.iptv` removes
the widget entry from the bar, and the settings stored on that entry go with
it. After re-enabling, run the `omarchy bar set` lines again. Favorites and
recents live in the state directory and survive.

Third-party replacement bars: Omarchy hands widgets on a replacement bar a
service-less facade, so there the widget shows the TV glyph only; clicking
it still opens the guide and playback works from the guide.

## Development

Development happens on the `dev` branch:
https://github.com/rmcdavid/omarchy-iptv/tree/dev. It carries everything this
branch deliberately does not -- the design and QA documents, the test suites,
the gate script, the dev harness, and the agent instruction file. The gate and
the QA runbook there say how to run and test the plugin. `main` is produced
from `dev` by the release exporter there; nothing is committed to `main` by
hand, and only an explicit allowlist of files is ever exported, which is why a
fresh install contains no documentation beyond this file and the changelog.

## License

MIT, see `LICENSE`.
