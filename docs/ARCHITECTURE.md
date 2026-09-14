# Omarchy IPTV -- Architecture

Owner: Software Architect. Status: v0.1, governs M1. Companion documents:
`docs/PRODUCT.md` (locked product decisions, US1-US8) and
`docs/OMARCHY-PLUGIN-CONTRACT.md` (verified facts about the host). Every host
behavior cited below was read from the live install on the machine of
record (Omarchy 4.0.3, Quickshell 0.3.1, Qt 6.11.2, Hyprland 0.56.2,
mpv 0.41.0, Python 3.14.7); line numbers refer to
`/usr/share/omarchy/shell/shell.qml` unless another file is named.

## 1. Stack and rationale

| Layer | Choice | Why |
|---|---|---|
| UI + lifecycle | QML on Quickshell 0.3.1 / Qt 6.11 | The only way to be a native Omarchy plugin: the shell loads our QML into its own process and injects `bar`, `shell`, `manifest`, `settings`, `service`. Theme tokens (`Color.*`, `Style.*`) and the `qs.Ui` kit come for free. |
| Data pipeline | Python 3.14 helper, stdlib only (`bin/omarchy-iptv`) | 10k-channel M3U and multi-MB XMLTV parsing must not run on the shell's UI thread. First-party precedent: `plugins/panels/dropbox/status.py`. No pip, no venv, nothing to install. |
| Player | mpv 0.41 driven over its JSON IPC socket | PRODUCT.md decision 3. mpv is present on every Omarchy install, supports `--input-ipc-server`, `--wayland-app-id`, `--force-window=immediate`, `--title`, `--force-media-title` (verified with `mpv --list-options`). |
| Pure logic | `Model.js` (ES5 style, guarded `module.exports`) | Loaded by both the QML engine and node, so search/grouping/state rules are unit-tested without a shell (precedent: dell-power, tailscale `Model.js`). |
| Tests | node runner, `python3 -m unittest`, `qmltestrunner`, `qmllint`, `omarchy plugin validate` | All present on the machine; node is dev-only (mise) and never a runtime dependency. |

### Is python3 a safe runtime dependency?

Verified: `pacman -Qi python` -> 3.14.7-1, provides `python3`. `pactree -d3
omarchy` shows `omarchy -> uwsm -> python` (plus `python-pyxdg`,
`python-dbus`), and `uwsm` is in `omarchy`'s hard `Depends On`. `yt-dlp`
(present on Omarchy) also requires it. Conclusion: `python3` cannot be
absent on an Omarchy install; the helper needs nothing beyond the standard
library (`json`, `re`, `urllib`, `gzip`, `socket`, `xml.etree`).

## 2. Decisions

| # | Decision | Options considered | Choice | Rationale (with evidence) |
|---|---|---|---|---|
| 1 | Who owns mpv and shared state | (a) bar widget owns everything; (b) overlay owns everything; (c) add a `service` kind | **(c) `kinds: [bar-widget, overlay, service]`, Service.qml is the single state owner** | A bar widget is instantiated once per monitor (`Bar.qml` `ModuleSlot`, `moduleWidgets()`), so (a) would spawn one mpv per screen. The overlay has no path to the widget. A `service` is created exactly once (`ensureService`, lines 901-951), is handed to the overlay directly (`if ("service" in item) item.service = shell.serviceFor(id)`, line 1349) and to the bar widget via `bar.shell.serviceFor(moduleName)`: `Bar.qml:234-237` gives a third-party widget `pluginShellForId(moduleName)` -> `createScopedPluginShell(manifest, id, allowOwnService=true, ...)` (lines 676-681, 739-744) whose `_serviceLookup` returns our own service through `pluginServiceFor` (lines 391-394, 608-610). |
| 2 | How mpv is launched | `Quickshell.execDetached` (fire-and-forget), `Process.startDetached()`, `Process` (attached) | **`Process` attached to the service** | Only `Process` gives `onExited(exitCode, exitStatus)` and stderr, which is how stream failures become "Could not play <channel>" notifications (US3) and how the bar knows playback ended. Single instance falls out of `mpvProc.running`. Cost: mpv dies with the service, i.e. on `omarchy restart shell` (accepted; `keepLoaded: true` keeps the service alive across plugin hot-reloads, `unloadPluginServices` lines 1033-1050). `startDetached` is the M2 escape hatch if "survive shell restart" is ever wanted. |
| 3 | How the overlay is summoned | IPC target on the overlay; `shell summon`; widget-local popup | **Everything goes through `omarchy-shell shell toggle io.github.rmcdavid.iptv`** | For a plugin that is both `bar-widget` and `overlay`, `isBarWidgetPanelPlugin` returns false (lines 1138-1150), so `summon/hide/toggle` route to the overlay `Loader` (lines 1152-1225, 1322-1366). Keybinding and menu entry call that command; the bar widget calls `bar.shell.toggle(moduleName, "{}")`, allowed because `pluginOwnsTarget` matches our own id (lines 385-389, 638-642). The overlay dismisses with `shell.hide(manifest.id)` so `openPanelIds` stays in sync (Emojis.qml pattern). |
| 4 | Search over 10k channels | substring; token AND; fuzzy; QML `SortFilterProxyModel` | **Helper precomputes `searchKey` (lowercase, diacritics folded, ASCII punctuation -> space); QML tokenizes the query, AND-matches every token as a substring, ranks prefix > word-start > substring, and materializes at most 300 rows** | Scanning 10k short strings is a few ms in the QML JS engine; the cost that hurts is `ListModel.append`, so rows are bounded (clipboard does 50). No fuzzy matching: it surprises on channel lists ("bbc" must not match "bbcasino" first). Non-Latin scripts are kept intact so Cyrillic/Arabic lists stay searchable. |
| 5 | EPG | QML parses XMLTV; helper emits full schedule; helper emits now/next | **Helper parses XMLTV (plain or gzip) into `epg-now.json` (now/next per tvg-id); a 5-minute timer re-runs the cheap `epg --now-only` recompute from the cached programme window; downloads honor a TTL** | The overlay never touches XML (US6, "never blocks on EPG"). The file stays small (~100 bytes per channel) even for 10k channels. |
| 6 | Favorites/recents identity | tvg-id; URL; name; hash of both | **`t:<tvg-id>` when that tvg-id is unique in the playlist, else `u:<fnv1a32(url)>`, `#n` suffix for exact duplicates** | tvg-id survives URL/token rotation (Xtream providers), but HD/SD variants often share one tvg-id, so uniqueness is checked per playlist and the URL hash is the fallback. Ids are assigned by the helper (it sees the whole list); `Model.channelId` mirrors the per-row rule. FNV-1a is trivial in both languages and pinned by shared test vectors. |
| 7 | Settings propagation | widget pushes `settings` into the service; service reads `shell.barConfig`; helper reads shell.json | **Service derives its settings from `shell.barConfig` (`Model.findBarEntry`)** | The host refreshes every scoped api's `barConfig` on each shell.json change (`syncPluginApis`, lines 875-881, triggered by `onShellConfigChanged`, lines 67-71), so `omarchy bar set` propagates without a widget instance and regardless of which bar hosts us. Bindings on `playlistUrl`/`epgUrl` re-run the helper (debounced); `refreshMinutes` re-arms the timer; `mpvArgs` applies on next launch. The widget reads only its view-side keys (`showChannelName`) from injected `settings`. |
| 8 | `keepLoaded` | on / off | **on (manifest-wide flag)** | Overlay: window mounted between summons -> open under 150 ms (clipboard/emojis do this). Service: survives `rescanPlugins`, so installing another plugin does not kill playback. Cost: `Service.qml` edits need `omarchy restart shell` (README says so). |
| 9 | Guide keyboard model | j/k as commands; modal; Ctrl-chords | **Letters always filter; arrows or Ctrl+J/K move; Ctrl+F favorite; Ctrl+R refresh; Tab cycles groups; Esc peels filter -> group -> close** | PRODUCT.md asks for both "type to search" and j/k. Search-as-you-type is the first-party overlay convention (clipboard/emojis); plain `f`/`r`/`j`/`k` would eat the first letter of "france 24". Final say is the UX designer's (see Open risks). |
| 10 | Helper error shape | bare string; structured object | **`{"ok": false, "kind": "...", "error": {"code": "...", "message": "..."}}` everywhere** | The guide shows `error.message` verbatim (US1) and can switch on `code`. `Model.parseHelperStatus` upgrades a bare string to the object form, so the stub contract in the task brief still parses. |
| 11 | `#EXTGRP` scope | next entry only; until next `#EXTGRP` | **Persists until the next `#EXTGRP`; `group-title` wins** | Matches VLC's m3u demuxer, which most playlist generators target. |
| 12 | Stream failure semantics | `--idle=yes` + event stream; `--idle=no` + exit code | **`--idle=no`: a failed or ended stream makes mpv exit; non-zero exit and not user-stopped -> critical notification with the last stderr line** | One code path, no long-lived socket reader in M1. Exit 0 (user pressed `q` in mpv, or clean EOF) is silent. A hung mpv is caught by the health check (helper `status` twice failing -> SIGTERM -> one relaunch). |

## 3. Components and data flow

```
 keybinding / menu / bar click                    omarchy bar set <id> key value
   omarchy-shell shell toggle <id>                          |
              |                                    shell.json (0600)
              v                                             |
 +------------------------------ omarchy-shell (Quickshell) --------------------------+
 |                                                                                    |
 |  BarWidget.qml (1 per monitor)      Guide.qml (overlay, keepLoaded)                |
 |    bar.shell.serviceFor(id) ----+     service (injected, shell.qml:1349)           |
 |    label = service.nowPlaying   |       filter -> Model.filterChannels(<=300 rows) |
 |    click/scroll -> service.*    |       Enter  -> service.playId(id)               |
 |                                 v                                                  |
 |  Service.qml (kind service, keepLoaded, 1 per shell)                               |
 |    settings  <- shell.barConfig (Model.findBarEntry)                               |
 |    channels  <- FileView channels.json      (watchChanges + explicit reload)       |
 |    epgNow    <- FileView epg-now.json                                              |
 |    userState <-> FileView state.json        (atomicWrites)                         |
 |    playlistProc: python3 bin/omarchy-iptv playlist --url U --cache-dir C           |
 |    epgProc:      python3 bin/omarchy-iptv epg --url E --cache-dir C [--now-only]   |
 |    controlProc:  python3 bin/omarchy-iptv play --id I --socket S | stop | status   |
 |    mpvProc:      mpv --input-ipc-server=S --wayland-app-id=omarchy-iptv ... -- URL |
 |    IpcHandler:   omarchy-shell io.github.rmcdavid.iptv play|stop|next|prev|refresh |
 +------------------------------------------------------------------------------------+
        |                       |                                   |
        v                       v                                   v
 ~/.cache/omarchy-iptv/   ~/.local/state/omarchy-iptv/   $XDG_RUNTIME_DIR/omarchy-iptv/
   channels.json            state.json                     mpv.sock  <---- mpv process
   playlist-status.json                                                 (title = channel)
   epg-now.json
   epg-status.json
```

### Playlist path

1. `Service.playlistUrl` changes, the refresh timer fires, the bar's middle
   click or `Ctrl+R` calls `refreshPlaylist()` -> 300 ms debounce.
2. `playlistProc` runs the helper (argv only). The helper fetches (20 s
   timeout, 64 MB cap, gzip tolerated), parses, assigns ids, writes
   `channels.json` and `playlist-status.json` atomically (temp file + rename,
   mode 0600, dir 0700) and prints the status JSON.
3. `onExited` calls `channelsFile.reload()` / `playlistStatusFile.reload()`
   explicitly (do not depend on inotify surviving the rename); the
   `watchChanges` bindings additionally catch external edits.
4. `applyChannels` replaces `channels`/`channelIndex`; the guide rebuilds only
   when open. On failure the helper leaves the old cache and marks
   `stale: true`; the guide shows the error text and "(cached)".

### mpv control path

- First play: `mpvProc.command = Model.buildMpvArgv(...)`:
  `mpv --input-ipc-server=$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock
  --wayland-app-id=omarchy-iptv --force-window=immediate --idle=no
  --keep-open=no --title=<name> --force-media-title=<name>
  --msg-level=all=error [--user-agent=.. --referrer=.. --http-header-fields-append=K: V]
  [user mpvArgs] -- <url>`. The URL always follows `--`.
- Zapping while running: helper `play --id <id> --socket <sock>` connects to
  the socket (stdlib `socket`), sends `set_property title/force-media-title`
  and `loadfile <url> replace` (per-channel headers as per-file options), and
  prints `{"ok": true, ...}`.
- Stop: helper `stop` sends `["quit"]`; `stopFallbackTimer` sends SIGTERM
  after 2 s if mpv ignored it. `userStopped` suppresses the notification.
- Health: every 10 s while running, helper `status` (`get_property
  media-title`, `paused`, `idle-active`); two consecutive failures -> SIGTERM
  -> one relaunch of `nowPlaying`.
- Exit: `onExited` clears `nowPlaying`; non-zero code without a user stop ->
  `omarchy-notification-send --app-name IPTV -u critical "Could not play
  <name>" "<last stderr line>"`.
- Window rules (user-side, documented in README M1): `--wayland-app-id`
  lets Hyprland rules target `omarchy-iptv` (float, size, workspace).

## 4. Repository layout

| Path | Purpose |
|---|---|
| `manifest.json` | Plugin manifest: id, three kinds, `keepLoaded`, settings schema/defaults. Validated by `omarchy plugin validate`. |
| `Service.qml` | Headless state owner: settings, caches, state file, helper runs, the mpv `Process`, IPC target. |
| `BarWidget.qml` | Bar entry (per monitor): TV glyph + now-playing label on `WidgetButton`; click/scroll/middle actions call the service. |
| `Guide.qml` | Fullscreen overlay: search, groups, favorites, EPG lines; `open/close/toggle`; dismisses via `shell.hide`. |
| `Model.js` | Pure logic shared by QML and node: normalization, ids, filtering, groups, state, settings lookup, mpv argv, formatting. |
| `bin/omarchy-iptv` | Python 3 helper (executable, stdlib only): `playlist` (done), `epg`, `play`, `stop`, `status`, `state` (stubs). |
| `tests/Model.test.js` | node runner for `Model.js`. |
| `tests/Model.spec.qml` | QtTest spec proving `Model.js` loads in the QML engine. |
| `tests/test_playlist.py` | Parser unit tests (attributes, EXTGRP, VLCOPT, KODIPROP, ids, normalization parity with Model.js). |
| `tests/test_helper.py` | CLI tests: cache writing, stale handling, scheme refusal, stub exit codes. |
| `tests/helper_loader.py` | Imports the extension-less helper as a module. |
| `tests/fixtures/*.m3u` | ASCII playlist fixtures. |
| `scripts/check.sh` | The quality gate: validate, qmllint, node, python, qml spec, ASCII check. |
| `docs/PRODUCT.md`, `docs/OMARCHY-PLUGIN-CONTRACT.md`, `docs/ARCHITECTURE.md`, `docs/UX.md` (designer) | Documents of record. |
| `README.md`, `LICENSE` (MIT), `.gitignore` | User-facing docs and housekeeping. |

Runtime writes go only to `~/.cache/omarchy-iptv/`,
`~/.local/state/omarchy-iptv/` and `$XDG_RUNTIME_DIR/omarchy-iptv/`; never
inside the plugin directory (PRODUCT.md decision 6).

## 5. JSON contracts

All files are UTF-8, written atomically, mode 0600. `version` is bumped on
incompatible changes; readers must tolerate unknown keys.

### `channels.json` (helper -> service)

```json
{
  "version": 1,
  "generatedAt": 1757700000,
  "sourceHost": "provider.example.test",
  "epgUrlHint": "http://provider.example.test/xmltv.php",
  "count": 2,
  "channels": [
    {
      "id": "t:bbc1.uk",
      "name": "BBC One HD",
      "group": "UK",
      "url": "http://provider.example.test/live/u/p/1.m3u8",
      "tvgId": "bbc1.uk",
      "tvgName": "BBC One",
      "logo": "http://logos.example.test/bbc1.png",
      "chno": "1",
      "searchKey": "bbc one hd uk",
      "headers": { "User-Agent": "VLC/3.0.20", "Referer": "http://ref.example.test/" },
      "options": { "vlc:network-caching": "1000", "kodi:inputstream.adaptive.manifest_type": "hls" }
    },
    { "id": "u:3f2a9c11", "name": "Plain", "group": "Ungrouped", "url": "http://...", "searchKey": "plain ungrouped" }
  ]
}
```

Empty optional keys are omitted to keep 10k channels near 2 MB. `headers`
come from `#EXTVLCOPT:http-user-agent|http-referrer` and
`#KODIPROP:inputstream.adaptive.stream_headers`; names are validated
(`^[A-Za-z0-9-]+$`), values have CR/LF stripped. `options` are kept raw for
M2 and are never interpreted by QML.

### `playlist-status.json` / helper stdout for `playlist`

```json
{ "ok": true, "kind": "playlist", "sourceHost": "provider.example.test",
  "fetchedAt": 1757700000, "durationMs": 410, "channelCount": 10234,
  "groupCount": 88, "warnings": ["3 entries skipped: unsupported URL scheme"],
  "stale": false, "error": null }
```

Failure (exit 1), cache kept if it existed:

```json
{ "ok": false, "kind": "playlist", "error": { "code": "network", "message": "could not reach provider.example.test: timed out" },
  "sourceHost": "provider.example.test", "fetchedAt": 1757600000, "stale": true, "durationMs": 20004 }
```

Error codes: `no_source`, `unsupported_scheme`, `unsafe_path`, `not_found`,
`too_large`, `http_<status>`, `network`, `bad_gzip`, `empty_playlist`,
`not_implemented`. Stubs exit 3 with
`{"ok": false, "kind": "<cmd>", "error": {"code": "not_implemented", "message": "not implemented"}}`.

### `epg-now.json` (helper -> service)

```json
{ "version": 1, "generatedAt": 1757700000, "validUntil": 1757700300, "sourceHost": "provider.example.test",
  "channels": {
    "bbc1.uk": { "now": { "title": "News at Six", "start": 1757698200, "stop": 1757700000 },
                 "next": { "title": "Regional News", "start": 1757700000, "stop": 1757700600 } }
  } }
```

Keyed by tvg-id; times are epoch seconds (XMLTV offsets applied by the
helper). `epg-status.json` mirrors the playlist status shape with
`"kind": "epg"`.

### `state.json` (service <-> disk, via `Model.parseState`)

```json
{ "version": 1,
  "favorites": ["t:bbc1.uk", "u:3f2a9c11"],
  "recents": [ { "id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000 } ],
  "lastPlayed": { "id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000 } }
```

`recents` is newest first, capped at `maxRecents`. Favorites keep their
insertion order (that is the order of the Favorites group).

### mpv status (helper `status` stdout, M1 target)

```json
{ "ok": true, "kind": "status", "running": true, "mediaTitle": "BBC One HD",
  "path": "http://...", "paused": false, "idle": false, "mpvVersion": "mpv 0.41.0" }
```

Not running: `{ "ok": false, "kind": "status", "running": false, "error": { "code": "not_running", "message": "mpv socket not reachable" } }`
(the helper also unlinks a stale socket file in that case).

### `play` / `stop` stdout

`{ "ok": true, "kind": "play", "id": "t:bbc1.uk", "name": "BBC One HD" }` or the
error object with codes `not_running`, `unknown_channel`, `ipc_error`.

## 6. Settings schema

Declared in `manifest.json` (`barWidget.schema`), edited with
`omarchy bar set io.github.rmcdavid.iptv <key> <value>`, stored inline on the
bar entry, read by the service through `shell.barConfig`.

| Key | Type | Default | Validation (service side, `Model.js`) |
|---|---|---|---|
| `playlistUrl` | string | `""` | trimmed; the helper accepts `http(s)://`, `file://` or an absolute path and refuses everything else |
| `epgUrl` | string | `""` | same rules; empty disables EPG |
| `refreshMinutes` | integer | 60 | `clampInt(5..1440)` |
| `mpvArgs` | string | `""` | whitespace-split; each token must match `^--[a-z0-9][a-z0-9-]*(=.*)?$`; reserved names (`--input-ipc-server`, `--wayland-app-id`, `--title`, `--force-media-title`, `--idle`, `--script(s)`, `--config-dir`, and their `--no-` forms) are dropped with a console warning. A single string was chosen over a JSON array because `omarchy bar set` writes strings by default and users copy examples from the README. |
| `showChannelName` | boolean | true | widget-only, `!== false` |
| `maxRecents` | integer | 10 | `clampInt(1..50)` |

Credentials caveat: Xtream-style URLs embed username/password. They live in
`shell.json` (mode 0600) and in the helper's argv for a few hundred
milliseconds. The helper never logs or prints a URL (errors carry the host
only), `channels.json` stores `sourceHost` rather than the URL, but stream
URLs inside `channels.json` do contain the credentials (cache dir is 0700,
files 0600). Document this in the README's settings section.

## 7. Error handling, offline behavior, performance

- Every helper failure produces a status object the guide renders as text
  (US1). The bar tooltip shows the same message.
- Offline: the previous `channels.json` stays, `stale: true` makes the guide
  append "(cached)" and the tooltip say "(cached)". The refresh timer keeps
  retrying at `refreshMinutes`; a manual refresh is always allowed.
- EPG failure never blocks the guide: rows simply have no EPG line.
- mpv failure: critical notification naming the channel, bar label clears,
  guide unaffected. A hung mpv is reaped by the health check.
- Service missing (should not happen; e.g. after a manifest edit): widget
  tooltip and guide status line say "service not loaded -- omarchy restart shell".

Performance budget (10k channels):

| Item | Budget | How |
|---|---|---|
| Overlay open | < 150 ms | keepLoaded window; `rebuildDisplay` appends at most 300 rows; channels already parsed in memory |
| Keystroke to redraw | < 30 ms | one linear scan over precomputed `searchKey`s, bounded materialization |
| Helper `playlist` | < 1.5 s for 10k entries on this machine (excluding network) | single pass regex parser, no DOM |
| Helper `epg` | < 4 s for a 50 MB XMLTV | `xml.etree.iterparse`, programmes outside a +-24 h window dropped, gzip streamed |
| `channels.json` | ~2 MB at 10k | omit empty keys, compact separators |
| `epg-now.json` | < 1 MB at 10k | now/next only |
| JSON.parse of channels in QML | ~50 ms, off the open path | happens on file load, not on summon |

## 8. Security standards

1. argv only. `Process.command` and `Quickshell.execDetached` receive arrays;
   never `bash -c` with playlist-derived strings. `Util.execArgv` exists but is
   unnecessary here.
2. Playlist data is data. Nothing from an M3U/XMLTV is ever evaluated,
   interpolated into a shell string, or used as an mpv option name. The URL
   follows `--`; headers become `--user-agent=`, `--referrer=`,
   `--http-header-fields-append=` items with validated names; everything else
   from `#EXTVLCOPT`/`#KODIPROP` is stored, not applied (M1).
3. Stream URLs are allow-listed by scheme (`http https rtmp rtmps rtsp udp rtp
   mms mmsh srt`); `file:`, `plugin:`, `javascript:` and option-looking lines
   (`-...`) are dropped and counted.
4. Source URLs: `http`, `https`, `file` or absolute path only; local files must
   resolve to a regular file outside `/proc`, `/sys`, `/dev`; 64 MB cap;
   20 s network timeout; no redirects to other schemes (urllib default).
5. No writes inside the plugin directory; caches and state are 0700/0600.
6. No symlinks in the repo (validator rejects them); no sudo, no pkexec, no
   network from QML.
7. Credentials: never printed; `sourceHost` instead of URL in caches and
   errors. README warns that `shell.json` and the cache contain them.
8. IPC surface is minimal (`play/stop/next/prev/refresh/status`) and only acts
   on ids from the loaded cache.
9. mpv is started with `--msg-level=all=error`, our own socket path under
   `$XDG_RUNTIME_DIR` (0700 by the session), `--wayland-app-id=omarchy-iptv`.
   User `mpvArgs` cannot override those.

## 9. Coding standards

QML (mirror first-party plugins; see clipboard/emojis, tailscale, dropbox):

- Root `id: root`. Order inside a component: imports, header comment,
  host-injected properties (`shell`, `manifest`, `service`, `bar`,
  `moduleName`, `settings`), readonly derived properties, state properties,
  functions (public API first), signal handlers, then children (models,
  files, timers, processes, IPC, windows).
- Colors and metrics only from `Color.*`, `Style.*`, `Border.*`. A literal
  color requires a `// CONVENTION-EXCEPTION: <reason>` comment on the line
  above; the scaffold has none.
- Fonts: `Style.font.menuFamily` on the overlay, `bar.fontFamily` in the bar.
- Keyboard first: every action reachable without the mouse; mouse selection
  goes through `PointerMoveGate` so hover never fights the keyboard cursor.
- `Accessible.role` / `Accessible.name` on the bar button, the guide card and
  rows.
- No `Quickshell.execDetached` with concatenated strings. Argv arrays only.
- `Text { textFormat: Text.PlainText }` for any user-supplied string.
- Never mutate service arrays in place: assign new arrays/objects so QML
  bindings notice (`root.userState = Model.withFavorites(...)`). The state
  property is called `userState` because `state` is a QQuickItem property.
- Nerd Font glyphs are the only non-ASCII allowed, and only in `.qml` (and the
  README's JSONC snippet). In `.js`/`.py` write `\uXXXX` escapes; `scripts/check.sh`
  enforces it.

`Model.js`:

- Pure functions, `var`/`function` declarations, no ES modules, no
  Quickshell or Qt globals (`Qt.md5` etc. are not available in node).
- Never mutate inputs; return new arrays/objects.
- Every function tolerates `null`/`undefined`.
- Any text-normalization or id change is made in the helper and in
  `Model.js` together, with the shared vectors in both test suites updated.
- `module.exports` guard at the bottom lists every public function.

Python (`bin/omarchy-iptv`):

- Stdlib only, `from __future__ import annotations`, type hints on every
  function, 4-space indent, no globals mutated at runtime.
- `argparse` subcommands; each `cmd_*` returns an exit code; `main()` is the
  only place that calls `sys.exit`.
- Exactly one JSON object on stdout per run; diagnostics on stderr prefixed
  `omarchy-iptv:`; no URLs in any output.
- Raise `HelperError(code, message)` for user-facing failures; let bugs
  traceback (exit 1 with a traceback is a bug report, not a status).
- Atomic writes through `write_json_atomic`; directories via
  `ensure_private_dir`.
- Tests are `unittest`, discoverable with `python3 -m unittest discover -s tests`.

Git:

- Branch `main`; feature branches `feat/<topic>`, `fix/<topic>`.
- Conventional commit subjects (`feat:`, `fix:`, `docs:`, `test:`, `chore:`),
  imperative mood, body explains why. Every commit passes `scripts/check.sh`.
- Version in `manifest.json` follows semver; bump on user-visible change.
- No generated files, caches or screenshots larger than 200 KB in the repo.

## 10. Test strategy

| Layer | What is covered | Exact command |
|---|---|---|
| Manifest | schema, entry points exist, no symlinks, id not reserved | `omarchy plugin validate .` from the repo root |
| QML static | syntax, imports, unqualified access, unknown properties | `mkdir -p /tmp/qmlroot/qs && ln -sfn /usr/share/omarchy/shell/Commons /tmp/qmlroot/qs/Commons && ln -sfn /usr/share/omarchy/shell/Ui /tmp/qmlroot/qs/Ui && /usr/lib/qt6/bin/qmllint -I /tmp/qmlroot -I /usr/lib/qt6/qml Service.qml BarWidget.qml Guide.qml tests/Model.spec.qml` |
| Model (node) | normalization, ids, filtering/ranking, groups, state, settings lookup, mpv argv, formatting | `node tests/Model.test.js` |
| Model (QML engine) | same functions loaded by Qt's JS engine | `QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml` |
| Helper | M3U parsing, attribute edge cases, EXTGRP/VLCOPT/KODIPROP, ids, scheme refusal, cache/status writing, stub exit codes; later XMLTV plain/gz with offsets and the mpv IPC client against a fake socket server | `python3 -m unittest discover -s tests` |
| Everything | all of the above plus an ASCII check | `scripts/check.sh` |

Warnings accepted from qmllint: "unqualified access" and "missing property"
on injected objects (`bar`, `shell`, `service` are `var`); the first-party
tailscale/dropbox widgets produce the same class of warnings. Errors are
never accepted.

Manual QA on the live shell (QA role, machine of record):

1. `git clone <repo> ~/.config/omarchy/plugins/io.github.rmcdavid.iptv`
   (no symlinks), `omarchy-shell shell rescanPlugins`,
   `omarchy plugin enable io.github.rmcdavid.iptv`; confirm
   `omarchy plugin list --json` shows it enabled and `qs log -p
   /usr/share/omarchy/shell --tail 50` has no warnings from our files.
2. US1: set `playlistUrl` to a public list (e.g. an iptv-org country list);
   bar tooltip shows a channel count; set a bogus URL and confirm the guide
   status line shows the helper's error text.
3. US2: `SUPER+SHIFT+T`, bar click and the menu entry all open the guide;
   type, arrows, PgUp/PgDn, Tab groups, Esc.
4. US3: Enter plays in mpv with the channel name as title; Enter on another
   channel reuses the window; a dead stream yields a critical notification
   naming the channel.
5. US4: bar shows the glyph and the name; right click stops; scroll zaps within
   the group; middle click refreshes (status line shows "Refreshing").
6. US5: Ctrl+F toggles; Favorites group is first; play ten channels and check
   Recent; restart the shell and confirm both persist.
7. US6: with an EPG URL, rows show Now/Next; the guide opens before EPG is
   loaded.
8. US7: change `refreshMinutes`, watch the helper re-run; disconnect the
   network and confirm "(cached)".
9. US8: `omarchy plugin remove io.github.rmcdavid.iptv --yes` leaves only the
   cache and state directories.
10. `omarchy theme set <x>` re-skins the guide and bar without restart;
    two monitors show one bar widget each and exactly one mpv.

## 11. Open risks and how the FE dev should handle them

1. FileView + atomic rename: Quickshell's `watchChanges` may drop the watch
   when the helper replaces the file by rename. Mitigation already in the
   scaffold: explicit `reload()` after every helper `onExited`. Verify on
   the live shell; if the watch is lost, keep the explicit reloads and stop
   relying on `onFileChanged`.
2. FileView writes into a missing directory: `mkdirProc` creates the three
   directories at service start (argv `mkdir -p -m 700`). Do not call
   `saveState()` before it has run (first user action is always later).
3. mpv `loadfile` per-file options: mpv 0.41 accepts
   `loadfile <url> replace <index> <options>`; check whether the options
   argument accepts a JSON object over IPC (newer mpv) or only `k=v,k=v`
   (commas in header values then need `%n%` escaping). Prefer setting
   `user-agent`, `referrer`, `http-header-fields` with `set_property` before
   `loadfile` when in doubt.
4. Stale socket after a crash: mpv should bind over a leftover socket file;
   if it does not, have the helper's `status` unlink an unreachable socket
   before the service relaunches mpv.
5. `IpcHandler` target is bound to `manifest.id`; if `manifest` arrives after
   creation the target briefly is the literal fallback string, which is the
   same value. Keep the fallback identical to the manifest id.
6. Service resolution timing: the widget polls `bar.shell.serviceFor` every
   500 ms for 10 s; the overlay re-resolves on every `open()`. If QA sees
   "service not loaded" persisting, log `_services` timing and switch the
   widget to re-resolve on `bar.shell` change as well.
7. Third-party replacement bars hand widgets a service-less facade
   (`Bar.qml:238-242`, README "Widgets rendered by a third-party replacement
   bar"); there the bar shows the glyph only and click still toggles the
   overlay. Accepted limitation; mention in README.
8. Keyboard map conflict (decision 9): if the designer insists on plain `f`
   / `r` / `j` / `k`, implement a "command mode" toggled by `/` or when the
   filter is empty, and document it. Keep `Model.js` untouched.
9. Multi-monitor wheel events: each bar surface has its own widget; wheel
   events reach only the hovered one, so no double-zap. Verify.
10. `refreshTimer.triggeredOnStart` plus `onPlaylistUrlChanged` at startup
    both request a refresh; the 300 ms debounce collapses them. Keep the
    debounce when adding new triggers.
11. EPG size: a 10k-channel XMLTV can exceed 100 MB; the helper must stream
    (`iterparse`) and cap at 64 MB compressed or bail with `too_large`.
12. Vertical bars: the widget shows the glyph only (`vertical` check);
    first-class vertical layout is M2 per PRODUCT.md.

## 12. Product owner rulings (reconciliation with UX.md, 2026-09-12)

These rulings override earlier sections of this document where they differ.
The STATUS.md decisions log mirrors them. UX.md is authoritative for
interaction and visuals; this document is authoritative for data, processes,
and security.

| # | Topic | Ruling |
|---|---|---|
| R1 | Guide keyboard model | UX.md section 3 is authoritative and supersedes decision 9 and open risk 8. Two modes: search mode on open (printable characters filter; Up/Down, PgUp/PgDn, Home/End, Left/Right, Enter, Esc, Tab as in UX 3.2), and list mode entered with Tab or `/` (UX 3.1: j/k/h/l, f, x, s, r, Space, Enter, Esc). No Ctrl chords. Esc clears the query first, then closes. Implement with `PanelKeyCatcher { blocked: searchMode }` and a synthetic filter line (clipboard pattern, no `TextField`). |
| R2 | Settings schema | Keys: `playlistUrl`, `epgUrl`, `refreshMinutes` (default 360, min 15, max 1440, step 15), `mpvArgs`, `showChannelName`, `maxRecents`, and new `barLabelMaxWidth` (integer, default 180, min 60, max 600, step 10, widget-only). The refresh default is raised because providers rate-limit playlist downloads. `Model.js` clamps follow. Settings live on the bar-layout entry read through `shell.barConfig` (decision 7); the README states this, which resolves UX section 8 item 16. |
| R3 | Result cap | 200 rows (UX 2.6) with the footer `First 200 of N - keep typing`. Supersedes 300 in decision 4. |
| R4 | Search key and ranking | `searchKey = fold(name + " " + group)`; the helper must include the group. Terms are ANDed. Ranking tiers per UX 2.5: name starts with the query, then a word in the name starts with it, then name contains it, then group contains it; favorites first inside a tier; playlist order inside that. |
| R5 | Sort and recents | Playlist order for groups and All; Favorites in the order added; Recent most-recent-first, capped by `maxRecents`; a recent is recorded on the play command, not on playback success. Multi-group `A;B;C` lists the channel under the FIRST group with the whole string searchable. |
| R6 | Card and layout | UX 5.1 and 5.2 (card `min(space(960), screen)` by `min(space(620), screen)`, group column `space(200)`, column hidden under `space(720)`). Supersedes the 900 width in the scaffold. |
| R7 | Bar widget | Glyph per state, never color-only: idle U+F0502, playing U+F0567, error U+F0503. On horizontal bars, when `showChannelName`, the name is elided at `Style.space(barLabelMaxWidth)`; vertical bars show the glyph only; the tooltip carries the full name and status (UX 6.3). Left click toggles the guide, right click stops, middle click refreshes, wheel zaps one step per tick via `Util.wheelSteps`. |
| R8 | Model fields the guide binds | Per UX 8.1: per channel `favorite`, `playing` (exactly one true), `failedAt` (session-only HH:MM), `epgNow {title, start, stop}`, `epgNext {title}`, `epgFraction` recomputed on a 30 s tick. Guide state: `mode`, `query`, `scopeId`, `cursorIndex`, `status` (ready, loading, refreshing, cached, error), `statusReason`, `statusHost`, `lastUpdated`, `bannerKind`, `resultTotal`, `nowPlaying {name, group, launchedFrom}`. |
| R9 | Service actions and IPC | Service: `play(id, keepOpen)`, `stop()`, `toggleFavorite(id)`, `removeRecent(id)`, `refresh()`, `zap(delta)` over the zap ring (the list the channel was launched from, UX 3.4; Recent is never a ring), `focusPlayer()` = argv `["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"]`. `IpcHandler` verbs: `toggle`, `play`, `stop`, `next`, `previous` (rename `prev`), `refresh`, `status`. |
| R10 | mpv ownership | Decision 2 stands for M1: attached `Process`, so mpv exits with the shell. The PM's detached-mpv mitigation (risk R3) is deferred to M2. The README documents the limitation. |
| R11 | Stream failure | Non-zero exit without a user stop: notification per UX 6.4, session-only `failedAt` on the channel, alert glyph on its row. |
| R12 | Notifications and privacy | Manual refresh (`r`, middle click, IPC `refresh`) notifies on success and failure; timer refresh notifies only on failure. Never render a playlist or EPG URL beyond scheme and host anywhere: guide, tooltip, notification, console. |
| R13 | Animation and placement | No open/close animation (UX 5.8). The overlay leaves `screen` unset so Hyprland maps it on the focused monitor. |

### 12.1 Amendments after the security review (2026-09-13)

Applied in fix round 1 against `docs/SECURITY-REVIEW.md`:

- S-01: the mpv window title is passed as `$>` + name (property expansion
  disabled for the rest of the string). `force-media-title` is not expanded
  by mpv, so it carries the plain name.
- S-02: `state.json` is created 0600 by the helper verb `state init`
  (`O_EXCL`), which `Service.qml` runs after the directory bootstrap.
- S-04: display names never start with `-`; the failure notification body
  is wrapped in curly quotes so it can never parse as a flag.
- S-05: HTTP reads run under a wall-clock deadline of `max(60 s, 3 x
  --timeout)` (code `timeout`); `Service.qml` watchdogs kill a helper that
  exceeds 180 s and report `helper_timeout` without a URL.
- S-06: redirects to non-http(s) targets are refused (`unsafe_redirect`);
  `Authorization` and `Cookie` are dropped when scheme, host, or port change.
- S-07: `MAX_CHANNELS = 50000`, `MAX_GROUPS = 2000` in the helper, mirrored
  by `Model.prepareChannels`; overflow produces warnings, never an error.
- S-03 is documented in the README (first-play URL visible in `ps`); the M2
  detached/idle mpv rework removes it.
