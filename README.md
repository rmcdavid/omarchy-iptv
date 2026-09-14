# Omarchy IPTV

Live TV that feels like it shipped with Omarchy: one keystroke opens a
theme-native channel guide, type to find a channel, Enter plays it in mpv.

Status: v0.2.0. The MVP and the Sources feature have shipped; `CHANGELOG.md`
has the release notes. `docs/PRODUCT.md` holds the product vision and the
roadmap, `docs/ARCHITECTURE.md` the design and standards, `docs/UX.md` the
interaction and visual spec, and `docs/STATUS.md` the live build status.
Contributors should start with `CLAUDE.md`.

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
omarchy bar set io.github.rmcdavid.iptv playlistUrl "https://iptv-org.github.io/iptv/countries/us.m3u"
omarchy bar set io.github.rmcdavid.iptv epgUrl "https://example.test/xmltv.php?username=U&password=P"
```

The plugin id is `io.github.rmcdavid.iptv`. Enabling it places the bar widget
in the right section (`omarchy bar move io.github.rmcdavid.iptv --section center`
to move it) and enables the guide overlay and the background service too;
all three are one plugin.

Then add the keybinding and, optionally, the menu entry and window rules
from `contrib/` (the Omarchy installer never runs plugin code, so these are
one-line copies you make yourself):

- `contrib/bindings.lua` -> `~/.config/hypr/bindings.lua` (`SUPER + SHIFT + T` opens the guide)
- `contrib/omarchy-menu.jsonc` -> `~/.config/omarchy/extensions/omarchy-menu.jsonc` (an `IPTV` row in the Omarchy menu)
- `contrib/windows.lua` -> `~/.config/hypr/looknfeel.lua` (keep the player opaque, optionally float it)

## Settings

Settings live inline on the widget's entry in `~/.config/omarchy/shell.json`
(mode 0600) and are edited with `omarchy bar set io.github.rmcdavid.iptv <key> <value>`.
The guide, the bar widget, and the service all read that one entry. Playlist
URLs from paid providers embed credentials: they stay in that file and in the
channel cache, both readable only by you, and are never shown or logged
beyond their host name.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `playlistUrl` | string | `""` | `http(s)://` URL or absolute path of the M3U/M3U8 playlist |
| `epgUrl` | string | `""` | XMLTV URL (plain or gzip), optional |
| `refreshMinutes` | integer 15-1440 | `360` | playlist and EPG refresh interval (providers rate-limit playlist downloads; keep it high) |
| `mpvArgs` | string | `""` | extra mpv options, space-separated `--key=value` tokens, e.g. `--profile=low-latency --hwdec=auto-safe` |
| `showChannelName` | boolean | `true` | show the channel name next to the TV glyph on horizontal bars |
| `barLabelMaxWidth` | integer 60-600 | `180` | width (px) at which the bar label is cut with an ellipsis |
| `maxRecents` | integer 1-50 | `10` | size of the Recent list |

## Using it

Press `SUPER + SHIFT + T` (or click the TV glyph in the bar). The guide opens
in search mode: type part of a channel or group name, `Enter` plays it in mpv
and closes the guide. Press `Tab` (or `/`) to switch to list mode, where the
vim keys and single-letter commands are live.

Guide keys (full map in `docs/UX.md` section 3):

| Mode | Key | Action |
|---|---|---|
| search | letters, digits, space | filter channel name and group |
| search | Up / Down, PgUp / PgDn, Home / End | move the cursor |
| search | Left / Right | previous / next group in the column |
| search | Enter | play and close; Esc clears the query, then closes |
| search | Tab or Shift+Tab | switch to list mode (query stays) |
| list | j / k, h / l | move the cursor / change group |
| list | Enter | play, close, focus the player |
| list | Space | play and keep the guide open (zap while watching) |
| list | f | toggle favorite |
| list | x | remove from Recent, or unfavorite in Favorites |
| list | s | stop playback |
| list | r | refresh playlist and EPG now |
| list | / or Tab | back to search mode; Esc clears the query, then closes |

Lists: Recent and Favorites are pinned at the top of the group column, then
All, then every group in playlist order, with Ungrouped last. Browsing with an
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
omarchy-shell io.github.rmcdavid.iptv play t:bbc1.uk      # play a channel id from the cache
omarchy-shell io.github.rmcdavid.iptv next                # zap forward
omarchy-shell io.github.rmcdavid.iptv previous            # zap back
omarchy-shell io.github.rmcdavid.iptv stop
omarchy-shell io.github.rmcdavid.iptv refresh
omarchy-shell io.github.rmcdavid.iptv status              # JSON
```

## Sources (playlists inside the guide)

You no longer need the terminal to configure a playlist. On first run the
guide shows an input: type or paste (`Ctrl+V`) a playlist URL or absolute
path, optionally an EPG URL, and press `Enter`. The guide fetches it and
shows the result inline (`1,475 channels in 28 groups`, or the reason it
failed). Nothing is saved if the fetch fails.

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
| `Esc` | back to the guide |

In a form: `Tab` moves between fields, `Ctrl+V` or `Shift+Insert` pastes,
`Ctrl+U` clears the field, `Enter` saves, `Esc` cancels. Saved URLs are shown
masked (`password=****`); press `Ctrl+R` or the eye button to reveal one
while editing. Only `http://`, `https://`, and absolute paths are accepted,
and no prefix is guessed.

`omarchy bar set ... playlistUrl` still works and shows up in the Sources
list as well; the two stay in sync. Up to 50 sources are kept.

## Playback notes

- One mpv window, class `omarchy-iptv`, titled with the channel name.
  Switching channels reuses it.
- Playback survives `omarchy restart shell`. The player runs on its own and
  the guide reattaches to it, so a restart, a theme change or installing
  another plugin all leave what you are watching alone.
- A stream that fails or ends shows a desktop notification naming the
  channel; the guide marks the row until the channel plays again.
- Stop clears the bar and guide immediately. If mpv ignores the quit request
  it is terminated, and if it ignores that too it is killed, within about
  four seconds. Playing a channel while the old player is still shutting
  down starts a fresh player once it has exited.
- No stream URL ever reaches the player's command line. It starts empty and
  every channel, header and title travels over a private socket that only you
  can read, so `ps` shows nothing about what you are watching.
- Two consequences of the player being independent, both deliberate. If you
  remove or disable the plugin while something is playing, the player is no
  longer guaranteed to stop with it; run `omarchy-iptv player stop`, or log
  out, if one is left behind. And a stream that fails while the shell is down
  cannot raise a notification, because the notification service is the shell
  itself; the channel is marked as failed in the guide instead, the next time
  you open it.
- Channel names are shown verbatim except that leading dashes are stripped
  and mpv property expansion is disabled for the window title.

## Limits

- Playlists are capped at 50,000 channels and 2,000 groups; extra channels
  are skipped and extra groups fold into Ungrouped. The guide footer shows
  `Playlist warning: ...` after such a load, and the warnings are also in
  `~/.cache/omarchy-iptv/playlist-status.json` and in the output of
  `omarchy-shell io.github.rmcdavid.iptv status`.
- Downloads (playlist and EPG) must finish within 60 seconds; redirects to
  anything but http(s) are refused and credentials are dropped when a
  redirect changes host.

## Files it writes

- `~/.cache/omarchy-iptv/sources/<key>/` : one directory per source with
  `channels.json`, `playlist-status.json`, `epg-now.json`, `epg-status.json`
  (safe to delete; rebuilt on refresh). A 0.1.0 single cache is migrated on
  first start.
- `~/.local/state/omarchy-iptv/state.json` : favorites, recents, last
  played, and the Sources history including their URLs (mode 0600)
- `$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock` : mpv IPC socket while playing

Nothing inside the plugin directory is written at runtime.

## Troubleshooting

- "No playlist configured": run the `omarchy bar set ... playlistUrl` line above.
- The guide's status line shows the helper's own error text (host name only,
  never the URL). To see the same JSON in a terminal:
  `python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv playlist --url <url>`
- Shell console: `qs log -p /usr/share/omarchy/shell --tail 100`.
- After editing `Service.qml` run `omarchy restart shell` (kept-loaded
  services do not hot-reload).

## Uninstall

```bash
omarchy plugin remove io.github.rmcdavid.iptv
rm -rf ~/.cache/omarchy-iptv ~/.local/state/omarchy-iptv   # optional
rm -rf "$XDG_RUNTIME_DIR/omarchy-iptv"                     # optional, cleared at logout anyway
```

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

```bash
scripts/check.sh                       # validate + qmllint + node + python + qml spec
#   qmllint baseline: only missing-property / unqualified access on host-injected
#   objects and Style/Color children, uncreatable-type for PanelWindow, and
#   signal-handler-parameters on Process.onExited are accepted; anything else fails review
node tests/Model.test.js
python3 -m unittest discover -s tests
/usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
omarchy plugin validate .
```

For live testing clone the repo to
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv/` (no symlinks allowed
inside a plugin folder), then `omarchy-shell shell rescanPlugins` and
`omarchy plugin enable io.github.rmcdavid.iptv`. `docs/QA.md` has the full
runbook.

## License

MIT, see `LICENSE`.
