# Omarchy IPTV

Live TV that feels like it shipped with Omarchy: one keystroke opens a
theme-native channel guide, type to find a channel, Enter plays it in mpv.

Status: v0.14.2. Shipped so far: the MVP guide, Sources, the detached player
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
screen, saved searches and channel logos. 0.14.0 takes your provider URLs
out of the desktop shell's settings file and keeps them in the plugin's own,
0.14.1 stores PNG channel logos with only what drawing them needs, and
0.14.2 reads `state.json` before every save and closes two findings about
GIF logos and guide-data files.
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
- `wl-paste` (package `wl-clipboard`, installed by default): pasting into the
  in-app form runs it, see Sources below
- An M3U/M3U8 playlist URL or local file, and optionally an XMLTV EPG URL
  (plain or `.gz`). Xtream-style providers: paste their
  `get.php?...&type=m3u_plus` and `xmltv.php?...` URLs.

## Install

```bash
omarchy plugin add https://github.com/rmcdavid/omarchy-iptv.git --enable
```

Then click the TV icon that appears in your bar — left click opens the guide —
and it starts on a form that asks for your playlist. **That form is the way
to add a playlist**: type or paste its URL or path, optionally a guide-data
(EPG) URL, and press `Enter`. The form masks what you type, and nothing you
enter reaches your shell history. `Add Xtream login` takes the server,
username and password as separate fields. To try the plugin with a free,
public list, paste one into the same form, for example
`https://iptv-org.github.io/iptv/countries/us.m3u`. More sources are added,
switched, edited and removed on the Sources screen (`o` in the guide; see
**Sources** below).

**Setting a playlist from the command line is gone.** Earlier versions took
`omarchy bar set io.github.rmcdavid.iptv playlistUrl "<url>"` (and `epgUrl`)
as a way to hand the plugin a playlist. This version does not read either
setting any more, with one exception: if you set one up that way on 0.13.6 or
earlier, the first shell start on this version moves it into your Sources
list once, makes it the active source, and takes the URL out of the shell's
settings file. You do not need to do anything, and you do not need your URL
again. After that, a `playlistUrl` or `epgUrl` set with `omarchy bar set` is
ignored and removed, and a notification says so — see **Bar setting
ignored** under Troubleshooting.

The plugin id is `io.github.rmcdavid.iptv`. Enabling it places the bar widget
in the right section (`omarchy bar move io.github.rmcdavid.iptv --section center`
to move it) and enables the guide overlay and the background service too;
all three are one plugin.

**Updating.** `omarchy plugin update io.github.rmcdavid.iptv` fetches the new
version, and then **restart the shell with `omarchy-restart-shell`**. The
update rewrites the plugin's files on disk, but the running shell keeps the
background service it already loaded until it is restarted, and the guide's
footer says `Updated`, then `restart the shell to see the new version`, while
that is the case. This matters for the logo update described under Settings: until
the shell restarts, the old service is the one talking to the new helper, so
the cache sweep runs but the guide-side guard that keeps one source's logo
list from being drawn against another source's files is not in place yet.
Do not reach for `omarchy-refresh-shell`: its name reads like a reload, and it
RESETS your shell configuration to Omarchy's defaults, which removes this
plugin's settings together with every other change you made to the bar
(measured on 2026-10-07 and recorded on the `dev` branch at
https://github.com/rmcdavid/omarchy-iptv/tree/dev; `omarchy-restart-shell`
left the configuration byte-identical on 2026-10-08).

Then add the keybinding and, optionally, the menu entry and window rules
from `contrib/` (the Omarchy installer never runs plugin code, so these are
one-line copies you make yourself):

- `contrib/bindings.lua` -> `~/.config/hypr/bindings.lua` (`SUPER + SHIFT + T` opens the guide; commented examples bind rewind, forward and back-to-live on `SUPER + SHIFT + H` / `L` / `R`, and pause, picture in picture and channel up/down on chords that are free on a stock Omarchy)
- `contrib/omarchy-menu.jsonc` -> `~/.config/omarchy/extensions/omarchy-menu.jsonc` (an `IPTV` row in the Omarchy menu)
- `contrib/windows.lua` -> `~/.config/hypr/looknfeel.lua` (keep the player opaque, optionally float it)

## Settings

Settings live inline on the widget's entry in `~/.config/omarchy/shell.json`
and are edited with `omarchy bar set io.github.rmcdavid.iptv <key> <value>`
— every setting in the table below except the two URLs, which are not
settings any more: your playlists and their guide-data URLs are kept in
Sources, and added or changed only in the guide.
The guide, the bar widget, and the service all read that one entry. Playlist
and guide-data URLs from paid providers embed credentials. Where they rest,
counted: **two files, both the plugin's own, readable only by you** —
`~/.local/state/omarchy-iptv/state.json`, which keeps your source list, each
source's URLs and which source is active, and the channel cache under
`~/.cache/omarchy-iptv/sources/<key>/`, whose `channels.json` carries the
stream addresses — each created mode 0600 inside a directory only you can
enter (one exception, a narrow window of a few milliseconds in which a save
can create `state.json` at your umask's mode, usually 0644, until the next
shell start corrects it, is under Troubleshooting). They are never shown or logged beyond their host name. The shell's
`shell.json` is **no longer one of them**. Up to and including 0.13.6 the
active source was identified by its URL on that entry, so the count was three
and the third was a file the plugin does not own; now the entry carries a short
code naming the active source, and the plugin never writes a URL into that
file. A URL still passes through it in two cases, both covered under the next
heading: the one an install updated from 0.13.6 or earlier still has in it
until the first shell start on this version moves it into Sources and takes it
out, and one you put there yourself with `omarchy bar set`, which the plugin
does not read and removes on its next write. This paragraph has been wrong before — two
sentences once said two files when there were three — so the count here is
re-derived for this version rather than copied: two the plugin owns and keeps
a URL in, and one it does not own that a URL only passes through.

**What the plugin stores, and three things to know about it.** Moving your URL
out of the shell's settings file costs three things, and none of them is
obvious when it happens to you:

- **A URL set on the command line is not read; the one you already had is
  moved, once.** The first shell start on this version reads the
  `playlistUrl` and `epgUrl` an earlier version kept on the widget's entry,
  adds that playlist to your sources (or finds it there), makes it the
  active one, attaches the guide-data URL to it, and records in the plugin's
  own file that this has been done. Only once that file has been written,
  and the write confirmed back to the plugin, are the two URLs taken off the
  entry. If the write fails — `~/.local/state` not writable, a full disk —
  your URLs are left where they were rather than taken away (turning channel
  logos on or off meanwhile leaves them too), the source is in effect for
  this session only, the shell's journal says `state.json could not be
  written`, and the next shell start moves them again. A guide-data URL with
  no active source to attach it to is not kept anywhere: there is nothing for
  it to guide, so it is removed with a notification saying to add the source with
  its EPG URL in Sources. If Sources already holds 50 sources and the
  playlist is not one of them, nothing is moved and no source is removed to
  make room: the playlist stays on the entry, nothing is marked as done, and
  a notification titled **Sources is full** says `The playlist set on the bar
  was not moved into Sources: Sources already holds 50 sources, the most it
  can. Remove one in the guide's Sources screen and the bar's playlist moves
  in.` (once a session, and again at each shell start while it lasts).
  Remove one -- in Sources, or with the helper's `state source remove` -- and
  the playlist is added and becomes the active source. Up to and including
  0.14.2 the least recently used source was removed to make room, with only
  a journal line, and its URL went with it. Not covered yet: an install
  updated from 0.13.6 records no active source, so until then the guide opens
  on its setup form (its `Saved sources` link lists the 50); a guide-data URL
  on the entry beside that playlist is reported as removed but stays on the
  entry, is NOT attached to the playlist when it moves in (add it again with
  `e` in Sources), and if you pick a source meanwhile, the next shell start
  puts it on THAT source in place of the source's own guide-data URL.
  From then on the plugin does not read either setting
  at all. Set one with `omarchy bar set` and the plugin adds nothing, switches
  nothing and changes nothing about the source you are watching: it removes
  the value from the entry on its next write — usually at once — and shows one
  notification, `Bar setting ignored`, saying the setting is no longer read
  and to add or switch sources in the guide's Sources screen. The
  notification names the setting, never the URL; setting the same value again
  in the same session does not notify again, and a value still there at the
  next shell start is reported once more and removed. Spaces around a value
  make no difference. Use the Sources screen instead; it is the only place a
  source is added or changed. Builds of this change that never shipped kept
  reading the command line, and ten rounds of review kept finding ways for a
  URL set there to be lost or to come back; the owner withdrew the route
  rather than add an eleventh. The move, the refusal and the notification
  are exercised on every commit's test tree under both kinds of Omarchy host
  (today's, and one carrying the settings fix awaiting review upstream), and
  live, under a headless compositor, by the harness scenario on the `dev`
  branch (134 checks, 2026-10-20).
- **Going back to an older version makes the plugin look unconfigured.** An
  older build looks for the URL on the widget's entry, does not find one, and
  says you have no playlist. Your sources are all still in `state.json`: open
  the guide, and on the form it shows you follow the `Saved sources` link and
  pick one. You do not need to find your URL again. It looks like the update
  ate your setup only because the conversion happened silently, with nothing
  to confirm and nothing for you to do — that is the same invisibility working
  for you on the way up and against you on the way down. Update again and the
  source you picked while on the older version is the one that comes back:
  the older build does not keep this version's record that the move has been
  done, so the first start after updating moves the URL the older build put
  on the entry once more, and takes it out again.
- **Your source list now lives in one file only.** `state.json` is the only
  copy. Before this version the URL in `shell.json` was an accidental second
  copy, so deleting the state file left the plugin able to rebuild the active
  source from it on the next start; now there is nothing to rebuild from, and
  the code on the entry cannot be turned back into a URL. Delete or lose
  `state.json` and you have lost the list, and you add your sources again by
  hand. If you decide to keep a copy of that file, remember what is in it: your
  provider URLs, with your username and password inside them. Treat the copy
  the way you would treat the password.

The code on the entry is made from the URL by a one-way hash. It cannot be
turned back into the URL; what it can do is confirm a guess — someone who can
read the file and already holds a candidate URL can hash it and compare. That
is far less than the URL itself and it is not nothing, which is why the
permission change in the next paragraph stays.

**One permission the plugin changes on a file that is not its own.**
`shell.json` is the shell's settings file, shared by every bar widget you
have, and it does not always arrive private. The copy Omarchy ships is
readable by everyone on the machine; a `shell.json` created from it keeps
whatever your umask gives it, which is usually readable by everyone too, and
rewriting a file that already exists leaves its permissions alone — so a
machine that started out readable stays readable. The plugin no longer puts
your provider URL in that file, but one can still get in: an install updated
from 0.13.6 or earlier has one in it until the first shell start on this
version moves it into Sources and takes it out, and you can still put one there
yourself with `omarchy bar set`, which the plugin does not read and removes on
its next write. So the plugin still takes group and other access away from that single
file — at every shell start, and again after each of its own writes: on an
ordinary 644 file that leaves it 600, which is what
`chmod 600 ~/.config/omarchy/shell.json` would do. Your own access is
not changed.
If the file is already private, nothing is changed and nothing is said.
Nothing else is touched: not `~/.config` or `~/.config/omarchy`, which are
shared with everything on your system and are not the plugin's business, not
any other file, and not one byte inside `shell.json`. A file only you can read
is enough on its own, whatever the directories around it allow.
If it cannot be made private — the file belongs to another account, or it is a
symlink, or the permissions will not change — the plugin will not write a URL
into it, and says `Settings file could not be made private`, with the command
to run yourself. Since this version's own writes carry no URL, nothing this
version does can produce that message any more; the check still runs, and the
refusal is kept for the write that would. What the check cannot cover either
way is `omarchy bar set`: that write is the shell's, not the plugin's, and it
lands whatever the permissions are, for as long as it takes the plugin to
notice and remove it. This is
not a one-off repair: the file can be recreated readable again later, by
`omarchy-refresh-config` among other things, and nothing tells a plugin when
that happens, so the check runs at every shell start and again before each
write. Between those moments the plugin is not watching, and a URL already in
the file would stay readable until the next one.

One place they can escape that, worth knowing, and one that used to:

- **Your shell history.** Setting a credentialed URL with `omarchy bar set`
  writes the whole thing into `~/.bash_history` or `~/.zsh_history`, where it
  stays until you remove it — and this version does not even read it, so it
  buys you nothing. Use the in-app form, which is the only way to add a source
  now. If you did it on an earlier version, the URL itself has been moved into
  Sources, but the history line is still there: `history -d` it and check the
  file.
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
  left: about three hundredths of a second, measured with other work
  running, and longer on a busier machine, readable in that moment by
  programs running as you alone, never by other accounts. The helper's
  command line no longer carries it. That is true of all three fetches that take a URL -- your
  playlist, your guide data, and the check the Sources screen makes before it
  accepts a source. Nothing else on the plugin's side writes
  either URL anywhere but the two files of its own named above; the shell's
  settings file gets one only from your own `omarchy bar set`, never from the
  plugin, and loses it again on the plugin's next write.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `playlistUrl` | string | `""` | **Not a setting any more**. Read once, at the first shell start on this version, to move a playlist an earlier version was given this way into Sources; after that a value set here adds nothing and switches nothing: it is removed from the entry on the plugin's next write, with one `Bar setting ignored` notification. Add, switch and remove playlists on the Sources screen |
| `epgUrl` | string | `""` | **Not a setting any more**, on the same terms as `playlistUrl`: read once, at the first start on this version, and attached to the source that becomes active then (removed, with a `Bar setting removed` notification, when there is none); ignored and removed after that. A source's guide-data URL is set in the add or edit form on the Sources screen (`a`, `e`), and cleared there |
| `sourceKey` | string | `""` | written by the plugin, not by you: the short code naming the active source, the one that names its cache directory under `~/.cache/omarchy-iptv/sources/`. The plugin's own `state.json` is the authority; this is a mirror it falls back to only when that file names no source, and a code that names none of your sources is ignored. It is not among the plugin's declared settings, so `omarchy bar set` shows no help for it, though it writes it like any other key |
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

**Channel logos are off by default, and turning them on tells you the cost first.** Logos are hosted by third parties named in your playlist, not by this plugin, so showing them means fetching pictures from whoever the playlist author pointed at. On the list this was measured against that was 63 different hosts, one of them covering two thirds of the channels. Nothing is contacted until you say so: press `g` on the Sources screen and the guide tells you how many hosts it would contact and which one gets the most, counted from your own cached playlist without making a single request. Turning it back off is one keypress and no dialog, and it stops a fetch already in progress -- but the pictures it already downloaded stay on disk, because a cache you might want again in a minute should not be thrown away by a toggle. When you do want the space back, `python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv cache logos-clear --key <key>` deletes one source's logos and nothing else: its channel list, its guide data and the source itself are untouched. `ls ~/.cache/omarchy-iptv/sources/` names the keys. Logos are `https` only, fetched once and cached under `~/.cache/omarchy-iptv/`, never re-fetched while the file is there, and a logo request carries none of your playlist's credentials, headers or query string -- a redirect to a non-`https` host is refused rather than followed. Each logo file is capped at 256 KiB, and that cap bounds the download and nothing about what drawing the picture costs: an image decoder works from the size the file's header declares, the bytes do not have to honour it, and a logo of a few hundred bytes can claim to be 20,000 pixels square and cost the shell hundreds of megabytes to draw (a marketplace reviewer reported that against 0.13.3; the measurements are on the `dev` branch at https://github.com/rmcdavid/omarchy-iptv/tree/dev). So a logo is also refused when its header declares a side over 4096 pixels or more than 4,194,304 pixels in all, and a header that cannot be read is refused too. For a GIF the size that counts is the whole area its frames reach, because the decoder places each frame at the position the file gives it: a one-pixel frame placed thousands of pixels from the corner counts as that whole area, and a GIF that declares an empty picture area or an empty frame is refused (a marketplace reviewer reported that against 0.14.1). Those two numbers are not arbitrary: at the bound, the costliest JPEG layout allowed holds about 24 MiB of decoder coefficients, which is the order of memory a logo could already cost before any of this, and a 1920x1080 provider banner passes with room to spare. A PNG can also carry text, colour profiles and other data beside its picture, some of it compressed, and the decoder expands that whatever the file's size suggests (a marketplace reviewer reported that against 0.13.6). So a PNG logo is stored with only what drawing it needs -- its image data and its small colour and transparency settings, copied unchanged, so the picture is the same -- and the rest is dropped; a PNG whose structure cannot be read from start to end is not stored at all. JPEG, GIF and WEBP logos carry nothing the decoder expands beside their pictures and are stored as they arrive. Logos cached by an earlier version were never checked this way, so each one is checked on the next fetch and removed when it fails the same check a new download gets: its header declares a size over the bound, its header cannot be read, its bytes are not one of the four image types the plugin accepts (JPEG, PNG, GIF, WEBP), it is a PNG whose structure cannot be read or that is larger than the 256 KiB cap, or it is larger than the cap with its header past the first 128 KiB the check reads (a file no download of the plugin's own could have left there). A cached PNG that passes is rewritten in place with only what drawing it needs, under the same name. You may see a logo disappear, and it comes back only if the provider's file passes when it is fetched again. The check is a read of each cached file in the helper process (its header, and the whole file for a PNG), never a decode, and it is not limited to the first 5,000 files a run would download: every cached file for a logo named in the current playlist is checked on every fetch (a file whose address has left the playlist is neither checked nor announced, so it is never drawn; `cache logos-clear` removes it). A channel with no logo gets empty space rather than a placeholder box, and the column is not drawn at all on a list that has none. The same helper's `logos` subcommand prints that survey from the command line and makes no request. Names, groups, guide titles and every other string the plugin itself draws from a playlist or a guide feed are drawn as plain text (the strings it hands to the shell are drawn by the shell as plain text too, except the body of a failure toast, which the shell's notification card draws behind its own image-tag stripper), so a playlist cannot route around that switch by hiding a picture tag inside a channel name. One caption on the channel wall did let it through: a marketplace reviewer reported that against 0.9.2, and 0.9.3 closes it.

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
failed). Nothing is saved if the fetch fails. A source you add here is kept in
the plugin's own file, not in the shell's settings file (Settings above says
what changed and what it costs).

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

**How these fields take input, and why.** They look like the shell's own
text boxes, but Qt does not edit them: the plugin handles every keystroke
itself -- typing, `Backspace`, `Delete`, their `Ctrl` word variants, cut --
and the control only draws the result, your caret and your selection. Paste
is `Ctrl+V` or `Shift+Insert` only. It asks the plugin's helper to run
`wl-paste` as a separate process; the helper reads at most 32 KiB of what
comes back, stops the read there, gives up after 5 seconds, and hands the
shell at most 8,192 characters. The shell itself never holds more than that
reply: measured with a 100 MB clipboard, one paste left the shell's memory
unchanged, where the first version of this fix had the shell take the whole
clipboard in and keep about 300 MB of it. A paste changes nothing if the
helper or `wl-paste` fails, and nothing is written anywhere else.
Middle-click paste of the primary selection no longer works in these
fields. The reason is the Qt the shell runs on, 6.11.2: an editable Qt text
field reads the ENTIRE clipboard, inside the shell process and on its main
thread, every time any program on your desktop changes the clipboard, with
no size limit and no deadline, whether or not you are typing in it. Qt
added that read on its 6.11 branch in February
2026 (commit `c82ef988`) and removed it in September 2026 (`7d0a433a`), after
6.11.2 was cut; as of 2026-10-11 no released Qt carries the removal, and
6.12.0 reads too. A read-only field does not subscribe to that read, so every
field in these forms is read-only to Qt and editable only through the plugin.
A marketplace reviewer raised it against 0.13.4. One loss, stated plainly:
input-method composition (dead keys, Compose, CJK input) does not reach a
read-only field, so accented or non-Latin characters cannot be TYPED into the
label field: a dead key followed by a letter inserts the plain letter (an
acute dead key then `e` types `e`), measured. Plain ASCII typing is
unaffected, and pasting carries any character.

The Sources screen is the only place a source is added, switched, edited or
removed. `omarchy bar set ... playlistUrl` and `... epgUrl` no longer reach
it: a playlist an earlier version was given that way is moved into this list
once, at the first shell start on this version, and after that a value set
that way is removed from the shell's settings file with a `Bar setting
ignored` notification and changes nothing here (Settings above has the
detail). A guide-data URL belongs to its source: set it in the add form, or
later with `e`, and clear it there. If your playlist names its own guide and
the source has none, that one is used and the Sources screen says so.
Channels are matched to the guide by id and, when the ids do not agree, by
name -- which is usually what happens, because playlists and guides rarely
come from the same place. Up to 50 sources are kept, and this list is the
only copy of them. Nothing ever removes a source to make room: at 50, `a`,
`c` and the Add rows say `Sources is full (50) · remove one first` instead
of opening a form; a playlist that another program adds while yours is
being checked can take the last place, and yours is then refused the same
way when its check ends (Troubleshooting); and a playlist an earlier
version kept on the bar waits there until there is room (Settings above).

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
- A guide-data file that defines XML entities of its own (an `<!ENTITY ...>`
  declaration inside its `<!DOCTYPE ...>`) is refused with `refused the EPG:
  it declares an XML entity, which XMLTV feeds never do`. A size limit on
  the download cannot bound what such definitions expand to, and XMLTV
  files never contain them; the usual `<!DOCTYPE tv SYSTEM "xmltv.dtd">`
  line is fine (a marketplace reviewer reported this against 0.14.1).

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
  session record, which source is active, and the Sources history including
  their URLs (mode 0600; a file you put there yourself -- a `mv` of an
  edited copy, or `rm` and `cp` -- keeps the mode it came with, 0644 say,
  through the plugin's saves until the next shell start makes it 0600).
  **This is the only copy of your source list and of
  your provider URLs**: lose it and you add your sources again by hand, and a
  copy you keep carries your provider username and password inside the URLs
  (Settings above says what that means for a backup). If the file is there
  but cannot be read, or is damaged, the plugin writes nothing to it until it
  can be read again, rather than replacing it with an empty one (see
  Troubleshooting). If another program changes it while the shell is
  running -- one of the helper's `state` commands, an edit, a backup put
  back, even a copy of the plugin's own file taken earlier -- the plugin
  re-reads it and keeps both its own unsaved changes and the other
  program's (Troubleshooting says what happens when both changed the same
  thing, or together went past a limit, and the cases where the other
  program's change can be lost: one written in the same instant as one of
  the plugin's own saves, and a backup put back that the plugin takes for
  the file it last knew). It may be a symbolic link to a
  regular file kept elsewhere, a dotfiles folder say: the plugin and its
  helper write through the link and leave it in place, and a link that
  leads nowhere is refused rather than replaced (except in one narrow
  window Troubleshooting names, where a save can create the file it points
  to). A tool that REPLACES the
  link, or puts a file over it, while the shell is running is not noticed
  at once; the plugin reads the file again before each save it makes, so it
  notices at its next save and keeps both that change and its own, unless
  the two land in the same instant; if that read does not answer at all
  (twice, 2 seconds each), the plugin writes nothing and says so
  (Troubleshooting says what is noticed, when, and what to do). The folder
  `~/.local/state/omarchy-iptv` may be a symbolic link too: the plugin
  follows it and makes the folder it leads to private (0700), as it does
  its own, and a folder link that leads nowhere is refused the same way.
  Pointed somewhere else while the shell runs, it is noticed the same way,
  at the next save; pointed at an empty folder, it makes the plugin stop
  saving rather than start a new `state.json` there -- outside one narrow
  window, which Troubleshooting's bullet on links names.
  Channels that failed to play are
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
  read it. Your playlist and guide-data URLs are no longer stored there (the
  entry carries a short code for the active source instead), so that
  permission change is now a guard for a URL arriving by another route — an
  install updated from an older version until its first start moves the URL
  into Sources, or your own `omarchy bar set`, which the plugin removes on its
  next write — rather than for the plugin's own writing. Not the contents beyond its own entry,
  and not the directories around it. See Settings above for what happens when
  that cannot be done.

Nothing inside the plugin directory is written at runtime.

## Troubleshooting

- "No playlist configured": the guide opens on a form that asks for your
  playlist -- paste it there, or open Sources (`o`) and add it with `a` or
  `c`. That form masks what you type and the value never reaches your shell
  history. There is no command-line way to add one any more.
- A notification titled **Bar setting ignored** (for example `playlistUrl is
  no longer read from the bar settings and was removed. Add or switch sources
  in the guide's Sources screen.`): a playlist or guide-data URL was set on
  the widget's entry with `omarchy bar set`, or by a script that still does
  that. This version does not read those settings: nothing was added, the
  source you are watching did not change, and the value has been taken out of
  `~/.config/omarchy/shell.json`. Add the playlist in the guide instead.
  The notification names the setting and never the URL. If a script keeps
  setting it, the notification comes back each time the value changes, and
  once at every shell start while the value is there; and if the URL carried
  a password, remove the command from your shell history too (Settings
  above).
- A notification titled **Bar setting removed**: seen at most once, at the
  first start after updating, when the configuration an earlier version kept
  on the widget's entry could not be moved into Sources whole. `epgUrl was
  removed from the bar settings: no source was set up for it to guide` means
  you had a guide-data URL set but no playlist active, so there was nothing
  to attach it to; add the source with its EPG URL in Sources. `... was not a
  usable URL and was removed` means the old value was not one the plugin
  accepts (a typo, a scheme it does not take); add the source again in
  Sources.
- **Plugin files damaged (05-ipc-logos.py) · reinstall the plugin** (any
  part name): the helper is `bin/omarchy-iptv` and the eleven files under
  `bin/helper/` beside it, and it checks all of them before it does
  anything. One of them is missing, unreadable, empty, cut off, not what
  the release wrote or from another release, or that folder holds a file
  the release did not put there (a hidden one, such as an editor's swap
  file, is ignored), so the helper refused to run rather than run half of
  itself, and nothing was changed. Seen once during `omarchy plugin
  update`, it is the update caught half written and clears by itself
  when the update finishes; if it stays, disable,
  remove and add the plugin again (Install and Uninstall). Your sources,
  favorites and guide data are kept outside the plugin and are not touched.
- Paste does nothing in a form: the plugin pastes by having its helper run
  `wl-paste`, so that must be installed (`wl-clipboard`, an Omarchy
  default). The helper reads at most 32 KiB of the clipboard and gives up
  after 5 seconds; the field keeps at most 8,192 characters of that, and
  then its own limit applies. Accented characters typed through dead keys
  arrive as the plain letter (the accent is dropped) and an input method
  does not reach the fields at all; paste them instead (see Sources above
  for why).
- "No playlist configured" right after going back to an older version: the
  older build looks for your playlist URL on the widget's entry, and this
  version moved it into `~/.local/state/omarchy-iptv/state.json`. Nothing is
  lost and you do not need your URL again: on the form the guide shows you,
  follow the `Saved sources` link and pick the source. Settings above has the
  detail, including what happens when you update again.
- A notification titled **Saved sources not loaded** when it happens as
  the shell starts, or **Saving has stopped** when it begins while the shell
  is running and your sources are already listed (for example
  `/home/you/.local/state/omarchy-iptv/state.json is not a valid state file.
  Sources, favorites and settings changed now are not saved until the file
  can be read again. ...`; the shell's journal gets the title and the same
  sentence), and the guide showing that same title and
  sentence where it would otherwise show its setup form: the file that holds
  your sources is there but could not be read -- its permissions, something
  other than a file at that path, a symbolic link that leads nowhere (at the
  file, or at its folder), a file where its folder should be, or contents
  that are not a state file -- or
  the plugin's start-up check of it did not answer within 15 seconds and was
  stopped, or, while the shell was running, the plugin's read of the file
  before a save did not answer (`... did not answer when it was read before
  a save (twice, 2 seconds each)`). The plugin has not changed the file and will write nothing to
  it until it can be read again, because it may be the only copy of your sources and
  provider URLs; earlier versions read such a file as empty and saved an
  empty one over it. Adding, editing, switching or removing a source, and
  turning channel logos on or off, answers `state.json could not be read ·
  nothing is saved until it can be`. A favourite, a hidden group or a saved
  search still changes on screen, but is not saved while this lasts. When
  this began while the shell was already running, it is saved only if the
  plugin finds the file readable again at one of its own saves (the next
  change you make in the guide); if the plugin sees the file come back
  first -- a good copy put back in place, a `chmod 600`, or the re-read your
  first source change makes -- it takes the file as it is and drops the
  change made meanwhile. At a start it is not kept. The Sources screen (`o`)
  shows the notification's title where it would count your sources, offers
  no `Add source` or `Add Xtream login` rows, and `a` or `c` answers with that refusal instead of opening
  a form. The notification's last sentence says what to do for the case you
  hit: `chmod 600` on the file, `chmod 700` on its folder, move whatever is
  at the path aside, point a symbolic link back at the file or folder that
  holds your state, make sure a regular file or nothing is there, restore
  the file from a backup, or check the disk or folder that holds it -- then
  `omarchy restart shell`. When a file or folder has gone missing while the
  shell runs, it names the link case first (`If it is a symbolic link,
  point it back at the folder or file that holds your state; otherwise make
  the folder readable with chmod 700.`), because a restart with a link
  still on an empty folder starts there with no sources, like a fresh
  install. After a read that did not answer, the next change you make in
  the guide reads the file again, and if it answers, saving resumes and
  that change and the ones made meanwhile are saved. When `state.json` is a
  regular file and only its contents or its permissions were wrong,
  putting a good copy back in place (or the `chmod 600`) is enough on its
  own: the plugin notices and carries on with your sources. Whatever the
  cause, it also reads the file again each time it would save -- a
  favourite, a hidden group, any change the guide keeps -- and at the
  first source change you try (switching, editing, retrying or removing a
  source), which is refused once more while it looks: if the file can be
  read by then, saving resumes and the next source change goes through.
  That is how it notices a `state.json` link's target put back, a folder
  made readable again, or a fix it was not told about. A favourite made at
  that moment is kept when your sources had loaded before the problem
  began; at a start that could not read the file it is not, as the
  notification said. `a` and `c` in Sources are refused by the guide
  itself and do not make it look. When the start-up check did not answer
  (`could not be checked`), the plugin's saves do not read the file again,
  but a good copy put back in place (`cp`, not `mv`) while the shell runs
  is noticed and ends it too; the restart is always a way out. A file or
  folder you left at mode 0000 while the shell was not running is NOT this
  case: the plugin restores the usual permissions at the next start, reads
  the file and says nothing.
- A directory or a named pipe (FIFO) at
  `~/.local/state/omarchy-iptv/state.json`: the case above, with `is not a
  regular file`. The plugin leaves it exactly as it is -- it no longer
  changes a directory's permissions there, and a named pipe no longer makes
  every shell start wait for ever on a helper that never finishes. Move it
  aside and restart the shell. (A socket there is refused by the helper the
  same way; which sentence the notification then shows has not been
  checked.)
- `state.json` as a symbolic link (into a dotfiles folder, say): it works
  while the link leads to a regular file -- the plugin and its `state`
  commands read and write the file it points to and leave the link in
  place. Up to and including 0.13.6 the helper's `state` commands replaced
  such a link with a plain file, and in the test that measured it the
  running shell then noticed none of the later changes to the file. While
  the shell is running, it notices AT ONCE a change made THROUGH the link:
  the helper's `state` commands, an edit that writes the file in place, a
  backup put back with `cp`, and an edit of the target file at its own
  path (in place, or by an editor that saves a new file there). A tool that
  REPLACES the link, or puts a file over it, at
  `~/.local/state/omarchy-iptv/state.json` -- `mv` of an edited copy or a
  backup onto that path (the usual `jq ... > tmp && mv tmp state.json`),
  `sed -i` on that path, `rm` and `cp`, or `ln -sfn` to point the link at
  another file -- is NOT noticed at once, because the shell's file watcher
  loses track of the path without a word. It is noticed at the plugin's
  next save -- a change in the guide, a channel played, a refresh that
  updates a source's channel count -- which reads the file first: your
  edit is kept and the change that made the save is added to it, as for
  any other program's change (the bullet on a file changed while the shell
  is running), and from then on changes are noticed at once again. After
  `ln -sfn` to another state file, THAT file is what the guide shows and
  saves to from then on, with the change that made the save added; the
  file the link used to lead to is left as it was. If the link now leads
  to a file that does not exist, nothing is created there, outside the
  narrow window below: the plugin stops saving and says so (**Saving has
  stopped**; the **Saved sources not loaded** bullet above).
  Until that next save the guide shows what it had and writes nothing, so
  nothing is lost; run `omarchy restart shell` to see the change straight
  away. One narrow exception, a window of milliseconds: a re-point that
  lands between the plugin's read of the file and the write that read
  allows is not seen by that write. Then a replacement is written over as
  before, and a link re-pointed at a file that does not exist, or a folder
  link at a folder with no `state.json`, gets a new one created there,
  holding your sources and provider URLs, at 0644 under the usual umask
  022 -- so after re-pointing a link, check the new place with `ls -l` and
  `chmod 600` a `state.json` you did not expect. Up to and including
  0.14.2 there were two more such windows: a save asked for while the
  plugin's previous save was still being written did not read the file
  first, and a save whose read had not answered within 2 seconds went
  ahead without it (the journal said `saving without the read`). Now a
  save asked for while the previous one is being written waits for it to
  land and then reads the file; and a read that does not answer is asked
  for once more, and if it is silent again the plugin writes nothing and
  stops saving (**Saving has stopped**, `... did not answer when it was
  read before a save (twice, 2 seconds each)`, the journal saying
  `state.json was not read back within ... ms of a save, twice; nothing is
  written until a read answers`) until a later read answers. (Up to and
  including 0.14.1 that next
  save wrote what the
  shell held over the change instead -- into the new file, after `ln
  -sfn` -- and a link pointed at a file that did not exist yet got a new
  `state.json` there holding your sources and provider URLs, with
  permissions that let other accounts read it (0644 under the usual umask
  022) wherever the folders above it let them in. If you did that, check
  the new file with `ls -l` and `chmod 600` it.) If the link
  leads nowhere (its target moved, or sits on a drive not mounted yet) or to
  something that is not a file, the plugin writes nothing and says `... is
  a symbolic link whose target is missing or is not a regular file ...
  Point it back at the file that holds your state, or move the link
  aside`; every `state`
  command but `state init` refuses it (exit 1), `state init` answers
  `found: link` (exit 0), and none of them touches the link. A link that breaks
  while the shell is running is reported as `could not be found, or its
  folder could not be read`, with advice for both causes, the link first,
  because the plugin cannot tell them apart then; putting the target back is noticed
  at the next save or source change, as the **Saved sources not loaded**
  bullet says (the first source change after it is refused once more,
  the next goes through), and `omarchy restart shell` works too. If the link leads into a
  folder you cannot write, a `state` command says `state.json is a symbolic
  link into a folder that cannot be written (Permission denied); nothing
  was written` and changes nothing: the plugin never changes the
  permissions of the folder a `state.json` link leads into.
- The folder `~/.local/state/omarchy-iptv` as a symbolic link: the plugin
  follows it, and at every shell start (and every `state` command that
  writes) makes the folder it leads to private, mode 0700, the same as its
  own folder -- that folder is where your sources and provider URLs are
  kept, wherever you put it. If the folder link leads nowhere, or to
  something that is not a folder (or a folder above it does), the plugin
  writes nothing and says `... is a symbolic link whose target is missing
  or is not a folder (or a folder above it is). ... Point it back at the
  folder that holds your state, or move the link aside, then run omarchy
  restart shell.`,
  naming the folder; every `state` command but `state init` refuses it
  (exit 1, `the state folder is a symbolic link whose target is missing or
  is not a folder; nothing was written`), `state init` answers `found:
  folder-link` (exit 0), and none of them touches the link. Changes to
  `state.json` inside a linked folder are noticed like any other (measured
  2026-10-14). Re-pointing the folder link itself while the shell runs is
  not noticed at once; it is noticed at the next save, which reads the
  `state.json` the link now leads to. If there is one, it is kept (outside
  the window above), the change that made the save is added to it, and that is what the guide
  shows and saves to from then on; the folder the link used to lead to is
  left as it was. The file keeps the permissions it has until the next
  shell start makes the folder 0700 and the file 0600. If the new folder
  holds no `state.json` (an empty folder, say), nothing is created there,
  outside the window the bullet above names: the plugin stops saving, and
  says so once (**Saving has stopped**, `... could not be found, or its
  folder could not be read. ... If it is a symbolic link, point it back at
  the folder or file that holds your state; otherwise ...`). The change you just
  made still shows, and its source change answered as done, but it is not
  saved while the link points there, and the next source change is
  refused with `state.json could not be read · nothing is saved until it
  can be`. Point the link back and the next save picks your file up again,
  writes into it the change you made meanwhile, and saving resumes; if a
  source change comes first, it is refused once, its re-read picks your
  file up as it is (the change made meanwhile is dropped), and the next
  source change goes through; or
  restart the shell -- after a restart the folder the link leads to NOW is
  what loads, so an empty one starts with no sources, like a fresh
  install, until you point the link back and restart again. (Up to and
  including 0.14.1 the next save after a re-point wrote what the shell
  held into the new folder: over its `state.json` if it had one, and into
  a new one if it did not -- holding your sources and provider URLs, with
  permissions that let other accounts read it (0644 under the usual umask
  022) wherever the folders above it let them in, and with nothing said;
  the next shell start made it 0600.) The
  plugin's cache folder, `~/.cache/omarchy-iptv`, and its runtime folder
  under `$XDG_RUNTIME_DIR` may be links too, and are followed. A linked
  runtime folder is made private (0700) whenever the player is started or
  stopped. A linked cache folder keeps its own mode -- the shell makes it
  0700 only through the one-time cache migration at a fresh install's first
  start, which an install already on the per-source layout never runs
  again, and a helper command run by hand without `--cache-dir` does too
  -- while every folder the plugin makes inside it is 0700 and every file
  0600; make the linked folder 0700 yourself if you want its listing
  private too.
  A plain file where the folder should be gets `... is not a folder (a
  file is at that path, or at one above it)`: move it aside and restart.
- The file changed while the shell is running -- by hand, by a backup put
  back, or by one of the helper's `state` commands: the plugin re-reads it
  (for a `state.json` that is a symbolic link, a change made through the
  link at once, and one that replaced the link at the next save: see the
  bullet on links above). If the new contents are a state
  it takes them -- a backup you put back wins over what the guide had
  saved, even when it is a copy of the plugin's own file from earlier in
  the session -- and when it has a change of its own not saved yet (a save
  that failed, or one still waiting to be written) it keeps both sides,
  except in the instant its own save is being written (the limit at the
  end of this bullet): your new
  favourite AND the source a `state source add` just added, say. Where both
  changed the same source, or the same setting (which source is active,
  the recent list), the other program's version wins, because it was
  written later; the shell's journal gets one line for each such case,
  `state.json was changed by another program while a change made here was
  not yet saved; kept the other program's version of ...`, naming the
  setting, or the source's short code and the fields that differed --
  never a URL or a value. If keeping both would go past a limit (50
  sources, 20 saved searches, 200 hidden groups), the other program's
  version keeps its place and what was added in the guide past the limit
  is not kept: a notification titled **Not every change was kept** says how
  many and which limit (never a name or a URL), and the journal gets one
  line for each, naming a source by its short code; make room and add it
  again. A source added in the guide while its URL is still being checked,
  when another program adds the 50th source in that moment, is refused
  when the check ends: nothing is added, the form stays open with what you
  typed and says `Sources is full (50) · remove one first from <host>`
  (the provider's host; a file on disk shows the sentence alone), and the
  journal says `the new source was not
  added: Sources is full (50)`. Up to and including 0.14.2 the guide kept
  it for the session and the next shell start dropped it without a word.
  One case where a backup put
  back has no effect: while a save of the plugin's has failed or is still
  under way, a backup identical to the file as the plugin last knew it is
  taken for nothing having happened, and the change made in the guide is
  then saved over it. Usually that is exactly what the file already held;
  after a rare burst of saves whose first was written and a later one
  failed, it can be the file from one save earlier. If the new contents are NOT a state -- a broken hand edit, a
  truncated copy -- the plugin keeps the channels and sources it is
  showing, writes nothing, and behaves as above until the file is fixed, so
  your broken edit is still in the file for you to repair. For a regular
  `state.json` this is measured for every kind of session this version
  has, the first session after a fresh install included: up to and
  including 0.13.6 that first session never noticed the file change at all,
  so a `state` command run in it was not seen and the next save wrote over
  it. One limit: a change ANY other program writes in the same instant as
  one of the plugin's own saves -- a hand edit, a helper `state` command,
  a backup put back -- can be lost: the plugin's save lands over it, and
  the shell's file reader does not re-read the file while that save is
  being written (measured), so the plugin never sees it. Nothing in the
  plugin can lock the file against another program. Edit the file by hand
  with the shell stopped, keep a copy first (it holds your provider URLs),
  then `omarchy restart shell`.
- `state.json is not a valid state file; nothing was written` (or `state.json
  could not be read (...); nothing was written`, `state.json is not a
  regular file; nothing was written`, `state.json is a symbolic link whose
  target is missing; nothing was written`, or `the state folder is not a
  folder (a file is at its path, or above it); nothing was written`) from
  the helper's `state` commands run by hand: the same protection on the
  command line -- every `state` command except `state init` refuses a
  `state.json` it cannot read or parse, or that is neither a regular file
  nor a symbolic link to one (exit 1), instead of writing over it, and none
  of them waits on a named pipe. Run while the shell is running, a `state`
  command that succeeds is picked up by the running shell, as above -- at
  once, or, if another tool replaced a `state.json` link earlier in that
  session, at the shell's next save (the bullet on links). Two more refusals carry a sentence of their own (exit 1), where 0.13.6 ended in a traceback, printed an empty state (`state show` and `state source list` over the folder link), or replaced the link with a plain file:
  `the state folder is a symbolic link whose target is missing or is not a
  folder; nothing was written` (the folder link above), and `state.json is
  a symbolic link into a folder that cannot be written (...); nothing was
  written`. The helper's other commands answer a folder of the plugin's
  that is a link leading nowhere, or a file where one of its folders should
  be, with `<folder> is a symbolic link whose target is missing or is not a
  folder; nothing was written` or `<folder> is not a folder; nothing was
  written` (exit 1) when they would write there. `player start` refuses a
  broken runtime folder the same way; over a broken state folder it warns
  that it could not create its screenshot folder and plays anyway. Commands
  with nothing to write there answer as if the folder were empty.
- "state.json could not be written" in the shell's journal: the plugin could
  not save its own file, `~/.local/state/omarchy-iptv/state.json`. The source
  you added or switched to is in effect for this session only. If this
  happens at the first start after updating from 0.13.6 or earlier, the URL
  that version kept on the widget's entry is deliberately left there until a
  save succeeds, so it is moved again at the next shell start — turning
  channel logos on or off in between leaves it there too. Check that the directory exists, is yours and is writable
  (`ls -ld ~/.local/state/omarchy-iptv`) and that the disk is not full.
- "Settings file could not be made private": the plugin would not write a URL
  into `~/.config/omarchy/shell.json`, because it could not make that file
  private and the URL would have gone into a file other accounts can read.
  This version's own writes carry no URL, so nothing it does produces this
  message; it is here for a shell still running an older service until you
  restart it. `ls -l ~/.config/omarchy/shell.json` first. If it is yours and a
  regular file, `chmod 600 ~/.config/omarchy/shell.json` and add the source
  again. If it belongs to another account or is a symlink, the plugin refuses
  to change it rather than guess, and that is yours to sort out.
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
it — the refresh interval, mpv options and the rest; set those again after
re-enabling. Your sources, which one is active, favorites and recents all live
in the state directory and survive, so the guide comes back on the same
playlist without being told the URL again.

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
