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
| 4 | Search over 10k channels | substring; token AND; fuzzy; QML `SortFilterProxyModel` | **Helper precomputes `searchKey` (lowercase, diacritics folded, ASCII punctuation -> space); QML tokenizes the query, AND-matches every token as a substring, ranks prefix > word-start > substring, and materializes at most 300 rows** | **Measured 2026-09-23 and this reasoning was backwards (F-PERF-1).** Scanning 10k short strings costs **159-212 ms** in the QML JS engine, not a few ms -- five to seven times the 30 ms keystroke budget. The cost was not `ListModel.append` and not the ranker (2.9 ms over all 10,000): it was a SECOND fold the ranker needs, the name alone, which was never precomputed the way `searchKey` is, so the guide folded 10,000 strings on every keystroke. With `nameKey` emitted by the helper the same calls are 11-64 ms. Rows are still bounded, which remains right; it was simply never the part that hurt. No fuzzy matching: it surprises on channel lists ("bbc" must not match "bbcasino" first). Non-Latin scripts are kept intact so Cyrillic/Arabic lists stay searchable. |
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
 |    playlistProc: python3 bin/omarchy-iptv playlist --cache-dir C                   |
 |                  with OMARCHY_IPTV_URL=U in its environment, never in argv         |
 |    epgProc:      python3 bin/omarchy-iptv epg --cache-dir C [--now-only]           |
 |                  with OMARCHY_IPTV_URL=E in its environment ({} for --now-only)    |
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
2. `playlistProc` runs the helper (argv only; the URL rides in its
   environment as `OMARCHY_IPTV_URL`, section 6, D-SINK-8). The helper
   fetches (20 s timeout, 64 MB cap, gzip tolerated), parses, assigns ids,
   writes `channels.json` and `playlist-status.json` atomically (temp file +
   rename, mode 0600, dir 0700) and prints the status JSON.
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
| `mpvArgs` | string | `""` | whitespace-split; each token must match `^--[a-z0-9][a-z0-9-]*(=.*)?$`; reserved names (`--input-ipc-server`, `--wayland-app-id`, `--title`, `--force-media-title`, `--idle`, `--script(s)`, `--config-dir`, `--load-scripts`, `--tls-verify`, `--stream-lavf-o`, and their `--no-` forms) are dropped with a console warning. This list is the M1 set plus the three later entries worth naming here; `MPV_RESERVED` in `Model.js` and its python mirror are the current list and `ARCHITECTURE-PLAYER.md` 4.12 is the register of why each name is on it. The two TLS entries are opposites and 4.15 is where that is specified: `--tls-verify` is the one entry the reserved list does not make safe by itself (D-SINK-13), and `--stream-lavf-o` is the one the reserved list is the only way to close (D-SINK-15). A single string was chosen over a JSON array because `omarchy bar set` writes strings by default and users copy examples from the README. |
| `showChannelName` | boolean | true | widget-only, `!== false` |
| `maxRecents` | integer | 10 | `clampInt(1..50)` |

Credentials caveat: Xtream-style URLs embed username/password. They live in
`shell.json` (mode 0600 only because the plugin now makes it so before it
writes one: the packaged default is 0644 and the host's writer keeps whatever
mode it finds, which is D-SINK-18 below -- this line said 0600 flatly for the
life of the project and was describing one machine), in `state.json`
(mode 0600; the Sources history
keeps each source's URLs, D-SINK-6) and, for the life of a fetch, in the
helper's environment as `OMARCHY_IPTV_URL` -- readable through
`/proc/<pid>/environ` by root only, because the fetch verbs make themselves
non-dumpable first (D-SINK-9). They are not on the
helper's argv: they were, for a few hundred milliseconds per fetch, until
D-SINK-8 below. The helper never logs or prints a URL (errors carry the host
only), `channels.json` stores `sourceHost` rather than the URL, but stream
URLs inside `channels.json` do contain the credentials (cache dir is 0700,
files 0600). Documented in the README's settings section.

Amended 2026-09-22 (D-SINK-3). The argv exposure above is transient and was
reasoned about; a second one was not. The README's own install instructions
told the user to set a credentialed URL with `omarchy bar set`, which writes it
into shell history PERMANENTLY -- a strictly worse exposure than the one this
paragraph accepts, created by our own documentation. The install section now
sends a paid provider to the in-app form, which reaches neither argv nor the
shell, and the settings section names both escapes. `/proc/<pid>/cmdline` is
world-readable where `/proc/<pid>/environ` is not, so an environment variable
would be a real improvement over argv if this is ever revisited; it is recorded
here rather than changed, because moving it touches the helper's interface and
the transient exposure is the one already accepted.

Closed 2026-10-01 (D-SINK-8). A marketplace maintainer reviewing the shipped
0.9.1 artifact (omacom/omarchy-plugin-marketplace#8998) reported the argv
exposure the paragraph above accepts, which is the "if this is ever
revisited" the amendment was waiting for -- met from outside the project.
What changed: the service sets the environment variable `OMARCHY_IPTV_URL`
on the helper process at the three spawns that carry a URL -- the playlist
fetch, the EPG fetch and the source probe -- by assigning
`<proc>.environment = Model.fetchEnvironment(<url>)` immediately before
`running = true`, every time. `fetchEnvironment` returns
`{ OMARCHY_IPTV_URL: url }` for a non-empty string and `{}` for an empty,
null or undefined one, and the `epg --now-only` recompute, which carries no
URL, assigns `{}`. The re-assignment is load-bearing: measured on Quickshell
0.3.1 / Qt 6.11, `Process.environment` merges with the inherited environment
(PATH and HOME survive), re-assigning it on the same object replaces the
previous value, and a null value unsets an inherited variable, so a URL from
one run cannot persist into a later run that sets `{}`. The argv builders no
longer take a URL -- `playlistFetchArgv(helperPath, cacheDir, stateDir)`,
`playlistProbeArgv(helperPath, cacheDir)` and the new
`epgFetchArgv(helperPath, cacheDir, nowOnly)` in place of the inline EPG
argv -- and none keeps an ignored `url` parameter, because a parameter
nobody reads is a trap. The helper's `playlist` and `epg` verbs read `--url`
when given, else `OMARCHY_IPTV_URL`, once, at the top of the verb, into a
local used everywhere the argument was; `playlist` with neither is a
`bad_url` status emitted as JSON, not an argparse usage exit, because the
service cannot switch on a usage exit. `--url` stays for a human running the
helper by hand, in their own shell and their own argv. Redaction is
unchanged: the helper prints neither the variable nor any URL beyond scheme
and host.

Why environ is the route. `/proc/<pid>/cmdline` is readable by every uid on
an ordinary proc mount; that was the exposure. `/proc/<pid>/environ` is
readable, in the kernel's terms, by any process that passes a ptrace-read
check against the target: while the target is dumpable that is every
process running as the same uid, plus root -- which is why the fetch verbs
call `shield_environment()` (PR_SET_DUMPABLE 0) before reading the variable.
Non-dumpable, a same-uid reader gets EACCES and only root reads it -- from
before the helper imports anything but `sys`; the window before that is the
interpreter starting and compiling the file, 98-113 ms idle at
sub-millisecond resolution (median 105 ms over twelve runs, 2026-10-01) and
264-634 ms under a doubled CPU load (the final review's measurement; `scripts/dev-harness/argv-scenario.sh` reads it
at 50 ms sampling and bounds it against an in-run control rather than an
absolute number), readable by same-uid processes only, and shortenable to
about 25 ms by a stub that shields before compiling the body, which this
project has not done -- and the
kernel writes no core for it either, which closes a second, durable sink:
`systemd-coredump` stores a dumpable crash's whole environment in the
journal as `COREDUMP_ENVIRON`, readable by the journal groups. Both
measured on this machine on 2026-10-01 (D-SINK-9). Before the shield the
boundary was the same one as the three 0600 files the URL already rests in;
with it, a fetch narrows the boundary rather than widening it. The
alternatives the amendment weighed, a pipe and a temp file, each
trade the exposure for a different one; an environment variable's own
residual is inheritance by child processes, and that is nil here because the
helper's `playlist` and `epg` verbs download with `urllib` and start no
child, so the URL ends at the helper. That makes the helper's no-subprocess
shape load-bearing for this sink, which is why engineering rule 5 now says
so.

Closed 2026-10-02 (D-TEXT-1). The same maintainer, reviewing the shipped
0.9.2 artifact (omacom/omarchy-plugin-marketplace#9628), reported that a
channel name keeps its markup through the helper and `Model.displayName`
and reaches the channel-wall caption, where Qt renders it. He was right:
`parse_extinf` / `make_channel` and `displayName` strip leading dashes and
whitespace and nothing else, and the caption `Text` (`text: tile.name`,
inside `channelWall`) declared no `textFormat`, so Qt's `AutoText` default
applied. Measured on Qt 6.11.2 offscreen against a logging server:
AutoText resolves to StyledText, and an `<img src="http://...">` anywhere
in the name is fetched at text layout on creation, with
`User-Agent: Mozilla/5.0`, silently, visible or not, parented or not; an
https `src` draws a SYN to port 443 from the QML process; StyledText and
RichText fetch too (a failed transfer's full URL reached stderr once, in a
scene that also held an https `<img>` toward a non-routable host -- not for
the RichText 404 alone, bisected); `Text.PlainText` is the only format that
makes no request. Neither entity
escaping nor URL redaction closes it: AutoText decodes `&lt;img ...&gt;`
back into a tag, and `redact_urls` leaves `<img src="http://h">`,
well-formed and fetchable. The exposure was every guide open, not only the
wall: `channelWall` is `visible: root.wallView` over a live
`model: root.rowCount`, and a GridView realises its first page of
delegates by geometry whether or not it is shown. What that bypassed is
the consent gate of the logo feature: logos are off by default, and the
`g` key on the Sources screen counts the third-party hosts and waits for
agreement before the first fetch -- a tag in a channel name fetched from
any host the playlist author named, logos off, nobody asked, from the
`omarchy-shell` process. What changed: the caption declares
`textFormat: Text.PlainText` -- at the sink, not in the two parser
functions the reviewer named, because a name must display its literal
characters, a stripper can manufacture a tag out of two halves, and EPG
titles never pass through the name cleaner; `scripts/check-text-format.py`
runs in `scripts/check.sh` so that no `Text` or `Label` ships with its
format undeclared again; `scripts/dev-harness/text-scenario.sh` opens the guide in list view
and in wall view over a playlist whose names carry `<img src>` probes and
asserts the logging server saw nothing, with `--baseline <ref>` to show
the same checks red against 2d3cee3; the measurement is re-runnable from
`scripts/dev-harness/spikes/text-autotext-img/`. The rule itself has been
in section 9 since the scaffold; its acceptance was a grep that could not
see a missing line (F-TEXT-2), the shape engineering rule 14 had already
named and refused.

Raised 2026-10-07 (D-SINK-13), and written here in the round that fixes it --
the state of the fix is the board row in `docs/STATUS.md`, not this paragraph.
The same maintainer again, the third finding in three weeks, this time
against the shipped 0.12.1
(omacom/omarchy-plugin-marketplace#10323): the player was launched without TLS
verification while the helper supplies the provider headers and the `https`
stream URL, so an on-path attacker could impersonate the provider, replace the
media, and collect the credentials carried in the URL and in those headers.
He was right. **A new class of sink, and that is the lesson of this one.**
Every exposure in this register until now was a place the URL was WRITTEN --
an argv, an environment variable, a file, a bus, a text layout -- and each was
closed by narrowing who could read it locally. This one is not local at all:
the URL and the headers were sent, correctly and only over TLS, to a peer
nobody authenticated. An enumeration of local sinks could be complete, and was,
and the system was still wrong. **The mechanism, named rather than hand-waved**:
mpv's own `--tls-verify` is a flag whose default is `no` (mpv v0.41.0 here), so
mpv passes `tls_verify=0` to FFmpeg and the certificate is not checked. mpv does
not "ignore certificates" -- it was asked not to look, and the base argv is what
asked. **The scope is exactly one sink.** The helper's own playlist, EPG and
probe fetches already refuse a self-signed certificate -- measured,
`[SSL: CERTIFICATE_VERIFY_FAILED] ... self-signed certificate`, redacted to the
host, which is rule 5 holding -- because `urllib` verifies by default and
nothing in the helper disables it (a grep for `_create_unverified`, `CERT_NONE`,
`check_hostname=False`, `verify=False` and `--insecure` over `bin/omarchy-iptv`
returns nothing). So the precise claim is "the plugin verified TLS everywhere
except the one place it handed the stream to mpv", never "it now verifies
everywhere". And "verified" means "checked the certificate on a TLS
connection": whether a connection is TLS at all is a separate question, and the
answer is not uniformly yes -- `SOURCE_SCHEMES` and `STREAM_SCHEMES` both
accept plain `http`, which is D-SINK-14, filed the same day and not settled by
this round. Verification and transport are two decisions and this entry is only
about the first. **What changed: five layers, specified in
`ARCHITECTURE-PLAYER.md` 4.15** -- `--tls-verify=yes` in the base argv where a
reader looks; the same token re-asserted as the FINAL element of the composed
argv, after the user's `mpvArgs`, which is the layer that actually binds,
because a later command-line token beats an earlier one and a user `--profile`
carries arbitrary options out of their own mpv config (all three bypasses
measured playing without the trailing token and refused with it);
`--tls-verify` reserved in both the `=no` and the `--no-` forms, so a direct
attempt is refused loudly instead of silently outvoted by the layer above it;
`--tls-ca-file` left unreserved as the targeted escape, measured working
behind the re-assertion; and `--stream-lavf-o` reserved, the one layer only
the reserved list can supply, because it forwards `key=value` past mpv to
libavformat where FFmpeg's own `tls_verify` reaches the same decision and our
last token does not outvote it -- measured playing the attacker's stream with
BOTH `tls-verify` tokens in place, in all six spellings, and found by all
three adversarial reviewers independently against a fix already measured
working at the sink (D-SINK-15). `--profile` is deliberately not reserved,
because the re-assertion makes it harmless and profiles are a legitimate mpv
feature.
**The residual, named rather than implied.** The sink itself has none once the
layers are in: a certificate chaining to neither the system store nor a CA the
user named aborts the connection. What is accepted is the COST, which is not
free for everybody: a provider presenting a self-signed certificate no longer
plays, and that user must name their provider's CA with `--tls-ca-file`
instead of switching verification off for every provider at once. That is a
smaller blast radius for the same capability, it is the reason the escape is
shaped this way, and the README says so in the user's own words. Established
by measurement on 2026-10-07 before any lane was briefed, against a local TLS
server with a self-signed certificate and with one signed by a generated CA,
driven by the real shipped argv rather than a retyped one, with `curl` as the
control; the evidence is the D-SINK-13 row in `docs/STATUS.md` and the write-up
in `docs/QA-RESULTS.md`.

Raised 2026-10-07 (D-SINK-16), hours after the fix above shipped, and written
here in the round that fixes it -- the state of that fix is the board row in
`docs/STATUS.md`, not this paragraph. **The same maintainer, the same
exposure, a second finding, posted on the verification request for the very
snapshot that was supposed to have closed it** (0.13.0, 5d527d7,
omacom/omarchy-plugin-marketplace#10389): the reattach path adopts an existing
player without migrating its TLS setting, and the helper then sends new
provider headers and new credentialed URLs into that same process, so a player
started before the update goes on making unverified HTTPS requests after it.
**Why it survived the first fix.** Every one of the five layers above is a
layer on the launch argv, and argv is fixed at exec: there is no layer among
them that can reach a process already running. Adoption is not an edge case
either -- a player surviving a shell restart is the designed behaviour of
M2-02 and the reason the feature exists -- so the one path that meets an
older player was the one path the fix could not touch. **We had this, and we
described it too kindly.** D-PLY-25 was filed the same day as the first fix,
by our own review, and it said a player adopted across an update keeps the
options it was launched with until it is stopped; the remedy it produced was a
README sentence telling the user to stop and start the player. The maintainer
named the half that filing missed: the plugin does not merely leave the old
player alone, it keeps FEEDING it, new headers and new credentialed URLs on
every zap, into a process that authenticates nobody. That is a live feed, not
a stale setting, and the difference changes both the severity and the remedy --
a user advisory was the wrong answer to a thing the product does by itself.
**That is the lesson, and it is D-SINK-8's lesson in a new costume.** An
accepted residual written in our own words is invisible to a review that only
checks whether the documents agree with the decision, because the words agree
with themselves; what nobody re-asks is whether the decision was right.
D-SINK-8 was the same shape (a transient argv exposure, reasoned about,
accepted, and closed only when someone outside asked why), and it was the same
maintainer who asked both times -- #8998 then #10389, as the two board rows
record. A residual in our own words can be
the same defect described too kindly, and the tell is a remedy that asks the
USER to do something about a behaviour that is ours.
**What is measured**, by the lead on 2026-10-07 before any lane was briefed,
over a real IPC socket against a local server with a self-signed certificate:
`tls-verify` is readable over the socket and reads False on a player launched
the way 0.12.1 launched one, and a `loadfile` of the attacker URL put the GET
in the attacker's log; `set_property tls-verify True` answers success, reads
back True, and the next `loadfile` of that same URL fetched nothing -- GETs 1
before and 0 after on the SAME process, with a positive control proving the
migrated player still plays. A stale `stream-lavf-o` clears the same way. So
runtime migration works, and the fix rests on that rather than on an argument:
`apply_channel` asserts both properties before every load and REFUSES the load
if they cannot be made safe (the one element of that sequence that is not best
effort), and adoption migrates, reads back, re-establishes the current
channel, and stops the player rather than feeding it when the read-back is not
clean. Specified in `ARCHITECTURE-PLAYER.md` 4.5.1, with 4.15's table carrying
the two new layers.
**What remains, named rather than implied.** Whether a stream ALREADY OPEN
picks the change up for its ongoing fetches is UNMEASURED -- the probe used a
short file, not a segmented live stream -- which is exactly why adoption
reloads instead of trusting the set to reach the open connection; the reload
may be dropped on a measurement of a real live stream and on nothing else.
The cost is not nothing: one visible rebuffer on the upgrade that crosses this
version, and a stopped player when the properties cannot be set, which is
playback the user did not ask to lose. One ordering gap is accepted and
recorded in 4.5.1: when a user's own play supersedes the adoption reply, a
player that could not be secured is refused any further load but is not
stopped by that path. And the scope sentence from the entry above still holds
unchanged -- this is verification, not transport, and whether a connection is
TLS at all remains D-SINK-14.

Raised 2026-10-09 (D-SINK-18), and written here in the round that fixes it --
the state of that fix is the board row in `docs/STATUS.md`, not this
paragraph. **The same maintainer, the fourth finding in four days, and the
fourth posted on the verification request for the commit that closed the
previous one** (against the shipped 0.13.2, eb7fdff,
omacom/omarchy-plugin-marketplace#10735): adding or switching a source stores
the playlist and EPG URLs in `~/.config/omarchy/shell.json` through
`persistActive` -> `updateEntryInline`, the supported upgrade path can create
that file 0644, and the host's atomic writer preserves whatever mode it finds,
so a provider credential comes to rest in a file other local accounts can read
whenever the directories above it are searchable. He was right.
**A new class again, and naming it is the point: this is not a sink but a
CONTAINER.** Every entry above this one is a place the URL was written or sent
-- an argv, an environment variable, a session bus, a text layout, a TLS
connection to a peer nobody authenticated -- and each was closed by narrowing
who could read or impersonate that one channel. Here nothing leaked. The
plugin asked the host to store a setting, the host stored it, in the host's
own file, exactly as designed. What was never checked is the WALLS of the box
the secret was put in, because the box was not ours. So an enumeration of
sinks can be complete, and was, and the credential still sat in a
world-readable file -- the same shape as D-SINK-13 one step further out: the
list was the right list and the question was the wrong question.
**Measured by the lead on 2026-10-09 before any lane was briefed. This lane
holds no display and cites those measurements rather than restating them as
its own.** The packaged default `/usr/share/omarchy/config/omarchy/shell.json`
is 0644, and `omarchy-refresh-config` copies it with `cp -f`: reproduced into
a scratch directory, reading the real source read-only, a fresh copy is 644
under umask 022 and 600 under umask 077, while a copy onto an EXISTING file
keeps that file's mode. A purpose-built Quickshell `FileView` probe with
`atomicWrites: true`, the setting `shell.qml:138` uses, left a 0644 file at
0644 and a 0600 file at 0600, with the content changed both times: the atomic
rename neither resets the mode to the writer's umask nor tightens it. On this
machine the file is 0600, but `~/.config` and `~/.config/omarchy` are both
0755, so only the home directory's own 0700 stands between it and another
account -- and a 0755 home is the default on many systems. The conclusion is
the one sentence that matters: **the plugin cannot assume the file it is
writing a secret into is private.**
**It is every source, and Xtream is only the case that always carries a
credential.** `persistActive`'s callers are `addSource` and the source switch,
the two ordinary paths; `buildXtreamSource` reaches them through `addSource`
like anything else. A plain `https://user:pass@host/list.m3u`, a provider URL
carrying the credential as a path token (`/live/USER/PASS/123.ts`, an ordinary
IPTV shape) and an Xtream `get.php?username=U&password=P` land there alike.
The report named the narrowest instance and the finding is wider than the
report, which is the third time in four days that measuring the claim found
more than reading it.
**What makes it a defect rather than a design** is the contrast with the
plugin's own files. `state.json` holds the same URLs at 0600 inside a 0700
directory, each `channels.json` likewise, and standard 5 has said so since M1.
The plugin was careful with every container it owns and careless with the one
it borrows -- and the borrowed one is the container this document's own
credentials caveat pointed at, describing it as 0600 because that is what one
machine happened to be.
**What changed, and the ORDERING is the whole fix.** The plugin takes
responsibility for the container it puts a secret into: the file is made
private BEFORE a URL goes into it, never afterwards, because a tightening that
follows the write is a window with a credential sitting in it. QML cannot
chmod, so the work is a helper verb, `config shield`, and the service gates
every persist that carries a URL on its verdict:
- The verb takes **no path argument and has no override flag**. It computes
  the one file it may touch from the environment -- `$XDG_CONFIG_HOME`, else
  `~/.config`, with a relative `$XDG_CONFIG_HOME` ignored as the XDG spec
  requires, which matters more here than for `cache_dir` because this value
  feeds a chmod -- and joins the two constant names `omarchy/shell.json`. A
  verb that chmods whatever path it is handed is a capability this plugin has
  no reason to own and the first thing a reviewer looks for.
- It operates on a **file descriptor, not a name**, which is D-LOGO-10's
  lesson applied to a chmod: `O_NOFOLLOW` refuses a symlink at open,
  atomically, and yields a handle on the inode that was checked; `O_NONBLOCK`
  is load-bearing rather than hygiene, because a FIFO at that path would make
  a plain `O_RDONLY` block for ever on the service's startup path; `fstat`
  decides regular-file and ownership by the invoking euid; `fchmod` clears
  exactly `0o077`, leaving the owner bits and the setuid/setgid/sticky bits
  alone; a second `fstat` READS BACK what the kernel stored rather than
  trusting the mode that was asked for; and a final `lstat` asks whether that
  inode is still the one at the path, because the host's own writer renames a
  new file over it and a verdict about a replaced inode is a true statement
  about the wrong file. A `replaced` verdict is retried, three times, a bound
  and not patience. The file is opened read-only and never read.
- Its output is one JSON object: a verdict, two octal modes, an attempt count
  and the file's last two path components. Never the contents, never the
  absolute path (which carries the user's name), never a URL. That is rule 5
  holding over a new verb rather than being remembered about one later.
- The verdict is read **fail-closed**, and that is the shape of the reader:
  private is concluded only when the run said so three ways at once (`ok`,
  `private`, and the verdict string), so a crashed helper, empty output, an
  unparseable line, any of the verb's other verdicts (`absent`, `symlink`,
  `foreign`, `not_regular`, `replaced`, `error`) and -- the case it is really
  written for -- a verdict string this version has never heard of all read as
  exposed. A helper that learns a new verdict cannot have it read as safe by
  an older guide. The two mirrors agree about that vocabulary by a CALL and
  not by a name (rule 13): one shared JSON fixture lists every verdict and
  which of them mean private, the python suite asserts it against the
  helper's own tuple and the node suite against the reader's.
- The decision in front of a persist is a pure function in `Model.js`,
  unit-tested from node rather than stranded in a QML component (rule 12),
  and it answers three ways: **persist** when the file is known private or
  the write carries no URL, **refuse** when it is known not private, **defer**
  when no run has answered yet. `defer` exists for exactly one window --
  QML cannot block on a `Process`, and the shield is started on the service's
  startup path, so a persist arriving before its first exit must neither write
  blind nor fail a user whose file is probably fine. It is held in one slot,
  collapsed to the last intent, and resolved in the shield's exit handler.
  The two function names are deliberately NOT cited here: they land with the
  code lane's commit in this round, and the gate's symbol check settles
  whether a `Model.*` name in a document resolves, so a document written in a
  worktree where it does not yet exist would be asserting something the check
  cannot grade. Read them off `Model.js`.
- **A persist that carries no URL is never gated**, and that is deliberate
  rather than convenient: `removeSource` persists `("", "")`, and if an
  exposed file could block that, a user whose `shell.json` is 0644 could not
  remove the credential sitting in it. The fix would be holding the defect in
  place.
- Any non-empty URL triggers the gate. Not "does this URL look like it has a
  password in it": a path token is a credential as surely as a query value is,
  which is why rule 5 treats whole URLs as secrets instead of trying to find
  the secret inside one.
- The refusal is **surfaced, not swallowed**: `sourcesPersistFailed` carries
  the new code `config_unsafe`, the guide shows
  `Settings file is readable by other users -- chmod 600
  ~/.config/omarchy/shell.json`, and a deferred persist that is later refused
  unwinds the switch the caller opened. The sentence deliberately does NOT
  reuse `persist_failed`, which sends the user to `omarchy bar set` -- that
  would answer a credential exposure by writing the credential into the
  user's shell history for ever, the durable form rule 5 refuses.
**The scope is deliberately one file, and the ruling says so.** Nothing looks
at, reports or acts on the mode of `~/.config` or `~/.config/omarchy`. A 0600
file is sufficient whatever the directory modes are; `~/.config` is shared
with everything on the system and tightening it is not this plugin's to do;
and the verb reports no directory mode either, because a number in the output
is an invitation to act on it. `O_NOFOLLOW` covers the last component only --
a symlinked `~/.config`, which is what every dotfile manager builds, is
followed on purpose, since refusing it would break ordinary installs. The
bound on that is the operation itself: this only ever SUBTRACTS group and
other bits from a regular file the invoking euid owns, so the worst a
redirected call can achieve is making one of the user's own files private. It
cannot disclose anything and it cannot grant anything.
**The residual, with its size rather than a claim of zero.** The check is not
atomic with the write, and cannot be: the verdict comes from a process exit,
the write happens later in the QML event loop, and the mode could be loosened
in between. Three windows, each stated as the code makes it rather than as a
measurement this lane could take:
1. *Verified-then-written.* On the immediate path the state was established by
   an earlier run -- the startup shield, or the re-arm after the previous
   write -- so the gap is however long the shell has been running since that
   run, not a sub-millisecond race. On the deferred path the write happens
   inside the shield's own exit handler, one event-loop turn after the
   read-back. Both are derived from the code; neither interval has been timed,
   and the wall-clock figure is UNVERIFIED because it is a property of the
   user's session rather than of the program.
2. *Loosened after a write.* A URL already in the file becomes readable again
   the moment something changes the mode back, and nothing tells a plugin that
   happened: there is no watcher on the file's mode, by choice. The cost is
   named rather than minimised -- the credential stays readable by other local
   accounts until the next persist or the next shell start re-runs the shield.
   The containing fact, and it is a real one, is that the supported command
   which can produce a 0644 `shell.json` produces it by CREATING the file, and
   a newly created file carries the package default contents and therefore no
   URL (`cp -f` onto an existing file keeps that file's mode); what remains is
   a mode changed by hand, or by a tool nobody here has enumerated. The
   mitigation is the re-arm: the shield runs again after every successful
   write and after the logo toggle's write, so the gate in front of the next
   persist is answering about the file as it is now rather than as it was at
   login.
3. *Installs that are already exposed.* The shield runs on the startup path
   unconditionally, independent of `mkdirProc`'s chain and independent of
   whether any persist happens, so an install whose `shell.json` is 0644 with
   a URL already in it is tightened at the next shell start rather than at the
   next source change. That is F-M3-16's lesson one defect later: repairing
   only the path that writes new secrets would have left every affected
   install exposed indefinitely, and the artifact needs the fix as much as the
   derivation does.
**The siblings, asked before closing (engineering rule 15).** What else does
this plugin put into a container it does not own? Swept over the tree at
982b693 and stated as cleared or not:
- **`updateEntryInline`, the second call site.** There are exactly two on
  `dev`: `persistActive` and the logo toggle. `ownedEntryPatch` names every
  owned key, `playlistUrl` and `epgUrl` included (D-LOGO-2, and the reason it
  does), so the logo toggle writes the provider URLs into the host config too.
  Found by this sweep and not by the report. It is deliberately NOT gated: the
  values it writes come from `root.settings`, which is what the host already
  stores, so it puts nothing in the file that is not in it already, and
  refusing a logo toggle would cost a feature for no privacy gained. It does
  get the re-arm.
- **Every helper write.** Each is the existing `O_EXCL` temp + 0600 +
  `os.replace` into a directory the helper creates 0700 through
  `ensure_private_dir`, so no other borrowed container takes a URL. Cleared.
- **mpv's own directories.** The shader/ICC cache and the watch-later records
  are pointed at `$XDG_RUNTIME_DIR/omarchy-iptv/`, a directory the plugin
  creates and owns, instead of `~/.cache/mpv/` and `~/.local/state/mpv/`,
  which it does not. Already true before this round; it is the same principle
  one feature along, which is why it reads as consistent rather than as luck.
  `$XDG_RUNTIME_DIR` itself is a container the plugin does not own and does
  not tighten; it is 0700 by the session, which is the one borrowed container
  that is private by construction. Cleared, with the caveat that
  `--screenshot-dir` stays unreserved by ruling (PO-5), so a user can still
  send screenshots into a container of their own choosing.
- **The host's notification and OSD surfaces** are not containers and are
  already in this register as sinks; nothing new. Cleared.
The root cause is not the mode at all: it is that the active source is
identified by its URL on the bar entry, so a credential has to live in the
host's config for the plugin to know which source is active.
`ARCHITECTURE-SOURCES.md` D1 records that, and the migration to a key is filed
separately by the lead; the shield is the containment, not the answer.

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
   errors. README warns that `shell.json` and the cache contain them, and
   says plainly what the plugin changes about `shell.json` so that a user
   meets that fact in the README rather than in `ls -l`.
8. IPC surface is minimal (`play/stop/next/prev/refresh/status`) and only acts
   on ids from the loaded cache.
9. mpv is started with `--msg-level=all=error`, our own socket path under
   `$XDG_RUNTIME_DIR` (0700 by the session), `--wayland-app-id=omarchy-iptv`.
   User `mpvArgs` cannot override those.
10. Every network peer is authenticated, the player included. The helper's
    fetches verify by default through `urllib` and nothing disables it; the
    player is given `--tls-verify=yes`, because mpv's own default for that flag
    is `no` and it passes `tls_verify=0` to FFmpeg when left alone. Reserving
    the option name is not the guarantee: user `mpvArgs` land after the base
    argv, a later token wins, and `--profile` can carry the setting
    indirectly, so the composed argv ENDS with `--tls-verify=yes` and the
    reserved entry exists to make a direct attempt audible. `--stream-lavf-o`
    is reserved because it reaches the same decision past mpv, in libavformat,
    where the composed argv's last token has no vote (D-SINK-15). The one
    supported escape is `--tls-ca-file`, deliberately unreserved. **And none of
    that reaches a player this shell did not launch**, because argv is fixed at
    exec while adoption is a designed path, so the standard holds only with the
    two IPC layers added by D-SINK-16: every load asserts the properties on the
    process about to receive the URL and refuses to load if they cannot be made
    safe, and adoption migrates an older player, reads the properties back, and
    re-establishes the channel rather than letting an unverified connection
    continue. Measured, specified and costed in `ARCHITECTURE-PLAYER.md` 4.15
    and 4.5.1 (D-SINK-13, D-SINK-15, D-SINK-16); a check that only greps the
    base argv for the token cannot see the layer that binds, which is
    engineering rule 14's shape, so it is verified by composing the argv with
    hostile `mpvArgs`, by taking the decision from a read-back rather than from
    a write that answered success, and by observing a refusal from a real TLS
    peer.
11. A secret goes only into a container this plugin has made private, and that
    includes a container it does not own. Standard 5 covers the plugin's own
    files; D-SINK-18 is what happens when the same credential goes into the
    host's `shell.json`, whose packaged default is 0644 and whose writer keeps
    whatever mode it finds. So the mode of that one file is checked and
    tightened BEFORE a URL is written into it -- the helper's `config shield`,
    a verb with no path argument that operates on a file descriptor rather
    than a name -- and a persist that carries a URL is REFUSED when it cannot
    be, surfaced to the user with the chmod rather than with `omarchy bar
    set`. Exactly one file: the parent directories are not touched, because a
    0600 file is sufficient whatever they allow and `~/.config` is shared with
    everything on the system. A persist that carries no URL is never gated, so
    clearing the active source always works. The check is not atomic with the
    write and is not claimed to be; section 6's entry carries the three
    windows and their sizes. Verified by observing the real mode of a scratch
    file through `$XDG_CONFIG_HOME` -- a mode is observable, so rule 14 admits
    no grep here.

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
- `Text { textFormat: Text.PlainText }` on EVERY `Text` and `Label`, the
  plugin's own glyphs included, and above all on anything from outside:
  channel names, group names, EPG titles, hosts, reasons, labels.
  Why: Qt's default, `Text.AutoText`, reads the string for markup and FETCHES
  an `<img src>` at text layout, on creation, visible or not (D-TEXT-1,
  measured on Qt 6.11.2 on 2026-10-02; the wall caption shipped without this
  line from 0.8.0 through 0.9.2). `scripts/check-text-format.py`, run by
  `scripts/check.sh` under "text format guard", fails the gate on a `Text`
  that leaves `textFormat` undeclared; `scripts/dev-harness/text-scenario.sh`
  observes the sink itself, over a playlist whose names carry `<img src>`
  probes and a logging server that must record nothing. `Text.StyledText` is
  allowed only for the plugin's own strings, with
  `// MARKUP-EXCEPTION: <reason>` on the line directly above the `textFormat`
  line and a test that what it renders composes from literals.
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
| R8 | Model fields the guide binds | **AMENDED 2026-09-24: `failedAt` is no longer session-only and no longer HH:MM.** It is an epoch second, it persists in the per-source cache (`sources/<key>/failed.json`, not `state.json`), and the row renders it as a clock for a failure today and a date for an older one. The rest of the row stands. Original: Per UX 8.1: per channel `favorite`, `playing` (exactly one true), `failedAt` (session-only HH:MM), `epgNow {title, start, stop}`, `epgNext {title}`, `epgFraction` recomputed on a 30 s tick. Guide state: `mode`, `query`, `scopeId`, `cursorIndex`, `status` (ready, loading, refreshing, cached, error), `statusReason`, `statusHost`, `lastUpdated`, `bannerKind`, `resultTotal`, `nowPlaying {name, group, launchedFrom}`. |
| R9 | Service actions and IPC | Service: `play(id, keepOpen)`, `stop()`, `toggleFavorite(id)`, `removeRecent(id)`, `refresh()`, `zap(delta)` over the zap ring (the list the channel was launched from, UX 3.4; Recent is never a ring), `focusPlayer()` = argv `["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"]`. `IpcHandler` verbs: `toggle`, `play`, `stop`, `next`, `previous` (rename `prev`), `refresh`, `status`. |
| R10 | mpv ownership | **WITHDRAWN: M2-02 detached the player (`docs/ARCHITECTURE-PLAYER.md` records "R10 closed"), and the README no longer states the limitation.** Left here with its marker because an unamended withdrawn ruling sat in this table for two milestones with its QA traceability row still asserting it, which is what this marker exists to stop. Original: Decision 2 stands for M1: attached `Process`, so mpv exits with the shell. The PM's detached-mpv mitigation (risk R3) is deferred to M2. The README documents the limitation. |
| R11 | Stream failure | **AMENDED 2026-09-24 by the product owner: the mark PERSISTS.** Non-zero exit without a user stop: notification per UX 6.4, a `failedAt` epoch on the channel stored in that source's cache, alert glyph on its row. The mark is dropped when the channel next plays, when its id is absent from the current playlist, when it ages out, and when the source is removed. It is deliberately NOT in `state.json`: channel ids are global across sources, so a state-level map would mark another provider's working channel, and it would fall inside D-ID-1's id-rotation blast radius, which that defect's row records as excluded precisely because this was session-only. Original ruling: session-only `failedAt` on the channel. |
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
