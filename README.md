# Omarchy IPTV

Live TV that feels like it shipped with Omarchy: one keystroke opens a
theme-native channel guide, type to find a channel, Enter plays it in mpv.

Status: scaffold (M1 in progress). See `docs/PRODUCT.md` for the locked
product vision and `docs/ARCHITECTURE.md` for the design and standards.

## Requirements

- Omarchy 4.x (Quickshell shell with the plugin system), Hyprland
- `mpv` on PATH (0.41 or newer)
- `python3` (already a hard dependency of Omarchy through `uwsm`)
- A playlist you are entitled to use (M3U/M3U8 URL or local file) and,
  optionally, an XMLTV EPG URL (plain or `.gz`)

## Install

```bash
omarchy plugin add <git-url-of-this-repo> --enable
omarchy bar set io.github.rmcdavid.iptv playlistUrl "https://example.test/get.php?username=U&password=P&type=m3u_plus"
omarchy bar set io.github.rmcdavid.iptv epgUrl "https://example.test/xmltv.php?username=U&password=P"
```

The plugin id is `io.github.rmcdavid.iptv`; the bar widget lands in the
right section by default (`omarchy bar move io.github.rmcdavid.iptv --section center`
to move it). Enabling the widget enables the guide overlay and the
background service too; all three are one plugin.

Settings live inline on the widget's entry in `~/.config/omarchy/shell.json`
(mode 0600; note that playlist URLs from paid providers embed credentials).

| Key | Type | Default | Meaning |
|---|---|---|---|
| `playlistUrl` | string | `""` | `http(s)://` URL or absolute path of the M3U/M3U8 playlist |
| `epgUrl` | string | `""` | XMLTV URL (plain or gzip), optional |
| `refreshMinutes` | integer 5-1440 | `60` | playlist refresh interval |
| `mpvArgs` | string | `""` | extra mpv options, space separated `--key=value` tokens (e.g. `--profile=low-latency --hwdec=auto-safe`) |
| `showChannelName` | boolean | `true` | show the channel name next to the TV glyph on horizontal bars |
| `maxRecents` | integer 1-50 | `10` | size of the Recent group |

## Keybinding

Add to `~/.config/hypr/bindings.lua` (`SUPER + SHIFT + T` is free on a stock
Omarchy; `SUPER + CTRL + T` is Activity):

```lua
o.bind("SUPER + SHIFT + T", "IPTV", "omarchy-shell shell toggle io.github.rmcdavid.iptv")
```

## Menu entry

Add to `~/.config/omarchy/extensions/omarchy-menu.jsonc` (hot reloads):

```jsonc
"iptv": {"icon":"󰕧","label":"IPTV","aliases":["tv","iptv"],"action":"omarchy-shell shell toggle io.github.rmcdavid.iptv"},
```

## Using it

Bar widget: left click opens the guide, right click stops playback, scroll
wheel zaps to the previous/next channel in the current group, middle click
refreshes the playlist. Hover for the status tooltip.

Guide (draft keyboard map, final map in `docs/UX.md`):

| Key | Action |
|---|---|
| letters | filter by channel name and group (search-as-you-type) |
| Up / Down, Ctrl+K / Ctrl+J | move the cursor |
| PgUp / PgDn, Home / End | page / jump |
| Tab / Shift+Tab | next / previous group (Favorites and Recent are pinned first) |
| Enter | play the selected channel in mpv |
| Ctrl+F | toggle favorite |
| Ctrl+R | refresh the playlist now |
| Esc | clear the filter, then the group, then close |

Shell IPC (usable from any keybinding or script):

```bash
omarchy-shell shell toggle io.github.rmcdavid.iptv        # open/close the guide
omarchy-shell io.github.rmcdavid.iptv play t:bbc1.uk       # play a channel id
omarchy-shell io.github.rmcdavid.iptv next                 # zap
omarchy-shell io.github.rmcdavid.iptv stop
omarchy-shell io.github.rmcdavid.iptv status               # JSON
```

## Files it writes

- `~/.cache/omarchy-iptv/` - `channels.json`, `playlist-status.json`, `epg-now.json` (safe to delete)
- `~/.local/state/omarchy-iptv/state.json` - favorites, recents, last played
- `$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock` - mpv IPC socket while playing

Nothing inside the plugin directory is written at runtime.

## Troubleshooting

- "No playlist configured": run the `omarchy bar set ... playlistUrl` line above.
- Error text in the guide's status line comes straight from the helper; run
  `python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv playlist --url <url>`
  to see the same JSON in a terminal.
- Shell console: `qs log -p /usr/share/omarchy/shell --tail 100`.
- After editing `Service.qml` run `omarchy restart shell` (keepLoaded services
  do not hot-reload).

## Uninstall

```bash
omarchy plugin remove io.github.rmcdavid.iptv
rm -rf ~/.cache/omarchy-iptv ~/.local/state/omarchy-iptv   # optional
```

Removal leaves only those two directories behind, plus the keybinding and
menu lines you added by hand.

## Development

```bash
scripts/check.sh                       # validate + qmllint + node + python + qml spec
node tests/Model.test.js
python3 -m unittest discover -s tests
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
omarchy plugin validate .
```

For live testing copy or clone the repo to
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv/` (no symlinks), then
`omarchy-shell shell rescanPlugins` and `omarchy plugin enable io.github.rmcdavid.iptv`.

## License

MIT, see `LICENSE`.
