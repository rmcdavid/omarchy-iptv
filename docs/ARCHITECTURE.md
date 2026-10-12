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

Raised 2026-10-09 (D-LOGO-11), and written here in the round that fixes it --
the state of that fix is the board row in `docs/STATUS.md`, not this
paragraph. **The same maintainer, the fifth finding in five days, on the
verification request for the commit that fixed the fourth** (0.13.3, 159da94,
omacom/omarchy-plugin-marketplace#10802): a provider JPEG passes `write_logo`
on content type, magic bytes and the 256 KiB cap, and nothing bounds the
dimensions its header declares, while `Guide.qml` decodes it inside the
long-running shell. **A new class, and naming it is the point: a sink whose
cost is set by a number the bytes do not have to honour.** The byte cap was
the protection the documents named, and it bounds the download: the decoder's
cost is quadratic in the width and height the header states, so 304 bytes
whose SOF says 20000x20000 took a Qt process standing in for the shell to
840 MB, 555 bytes to 1,239 MB, and the 65500x65500 pair past a 1.5 GB cap in
1.5 s (measured by the lead on 2026-10-09 before any lane was briefed, Qt
6.11.2 offscreen, the qml runtime drawing one `Image` declared as the row
slot declares it, capped by a user-session memory scope around the Qt
process alone; the tables are in `docs/QA-RESULTS.md`). The shell itself was
never fed one; that it allocates the same is inference from the probe being
the slot's own declaration. The ratio is 2.9 million to one.
**The cap, re-ruled on 2026-10-11, and why the mechanism matters.** Anything
in this repository that might decode an over-bound image runs under an
ADDRESS-SPACE rlimit on the qml process alone -- util-linux
`prlimit --as=2500000000 -- env QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qml <probe>`,
which sets the limit on itself and execs the runtime in place (measured by
the harness lane: the pid the command runs under is the pid the reporter
spawned) -- and not under the memory scope the first measurement used. Two
reasons, neither taste. `scripts/check-marketplace-capabilities.py`
reproduces the marketplace security baseline over every tracked
`.sh`/`.py`/`.js`/`.qml` file with no allowlist by design, and its
service-management rule matches the scope tool's name in any command line of a tracked .sh/.py/.js/.qml file, or a shell fence of the root README (comment-only lines are skipped, as upstream skips them, and no other .md file is read); the harness lane's first commit carried those
tokens and turned that gate red without noticing, because it ran the gate
before `git add` and the scanner enumerates `git ls-files`. And under the
rlimit an allocation the limit cannot hold is refused inside the process,
so Qt reports `Image.Error` at a measured peak where the scope SIGKILLed it
at the cap with the figure unmeasured. Figures by mechanism, so a reader
knows which is which: under the scope (lead, 2026-10-09) control 72 MB,
the 304-byte 20000x20000 progressive 840 MB, the 555-byte 3-component
1,239 MB, the 176-byte baseline 65500x65500 455 MB, the valid 12000x12000
348 MB, and both 65500x65500 progressive files SIGKILLed at 1.5 GB; under
the rlimit (harness lane, 2026-10-11, `scripts/dev-harness/spikes/logo-decode-bomb/run.sh`,
36 rows judged from the tree, 37 with `--extra` for the lead's valid 12000x12000 file, 0 DIFF) the same rows read 72, 839, 1,239, 454 and 347, and
the two the scope could not measure read `Image.Error` -- the grayscale
65500x65500 refused by the allocator 325 MB in after 0.6 s, the 3-component
one refused at 72 MB before anything was touched. The control is 72 MB at
`--as` 1.5, 2.5 and 4.0 GB alike (lead, 2026-10-11).
**Why Qt's own limit does not catch it, measured rather than argued.** Qt's
image allocation limit (256 MiB by default) IS consulted; bracketing it with
`QT_IMAGEIO_MAXALLOC` puts the threshold between 20 and 26 MiB on that file,
which is `ceil(20000/8)^2 * 4`: the image already divided by libjpeg's
largest scale denominator, because `sourceSize` is set. The format's largest
side is 65535 and `ceil(65535/8)^2 * 4` is exactly 256 MiB, so no JPEG the
format can express exceeds the default on this path. The option added to
keep the decode cheap is the option that disarms the only bound Qt has. PNG,
GIF and WEBP refuse at control memory, rewritten and honestly huge alike,
because their handlers decode at full size and hand the limit the real
number -- an asymmetry that is upstream behaviour, not a property of the
plugin. The contract file carries this as a verified Qt fact with no
automated pin.
**What changed, and where.** Two numbers at the one gate that puts a
provider's bytes into the cache: `write_logo` refuses, after the magic check
and before `ensure_private_dir`, any logo whose header declares a side over
`MAX_LOGO_SIDE` (4096) or more than `MAX_LOGO_PIXELS` (4,194,304), and
refuses a header it cannot read, for all four allowed types, so a refusal
creates nothing on disk -- not the file, not the directory (called on the
shipping function on 2026-10-11: `logo_dimensions`, directory absent). In
the helper and not in QML, for three reasons that are each sufficient:
`Image` has no lever for this, its allocation limit being measured
unreachable above; the helper is the process that is allowed to die and the
shell is not; and a guard in the guide would have to live inside the 150 ms
open budget, where a header parse per visible row is exactly the work
section 7 keeps off that path. The numbers are the cost at the bound: a
4:4:4 progressive JPEG of 4,194,304 px holds 25,165,824 bytes of
coefficients, 24 MiB, the order Qt was already willing to allocate for a
logo (the 23.8 MiB above), and the side cap exists because area alone
admits 65535x64. A 1920x1080 banner passes; 4097x1024, 2048x2049 and
65535x64 do not (called, 2026-10-11). The refusal names a host and the
numbers, never the URL (rule 5). `MAX_LOGO_BYTES` stays, bounding the axis
it always bounded.
**The cache written by 0.13.3 and earlier was never checked, so the fix is
not complete without a sweep.** The guide points an `Image` at a cache file
only when the helper announced that name, FOR THE DIRECTORY IT ANNOUNCED IT
FOR (`Model.logoSlot`, `Model.wallTile`, `Service.qml` `logoHave`), and
there are exactly two `Image` elements in the shipped tree, the wall tile
and the row slot, both fed that way. So the "already on disk" branch of
`logos --fetch` proves each cached file with `logo_file_within_bounds`
BEFORE announcing it; a file that fails is unlinked, not announced, counted
as `swept`, and falls through to the fetch, which refuses the same bytes at
the gate under `reasons.logo_dimensions`. A cached file fails that check
when its header declares a size over the bound, when its header cannot be
read, when its bytes are none of the four allowed types (a file on disk is
not evidence it went through the magic check), and in one case a new
download never reaches, because the download is refused over 256 KiB before
`write_logo` runs: a cached file over 256 KiB whose header is not within
the first 128 KiB, which the second read refuses rather than reading past
the byte cap. The sweep removes a file for each of those. Called on the
lane-R2 helper on 2026-10-11: the 304-byte bomb, a text file, `FF D8 FF`
followed by zeros, and an empty file all answer False, and the 304-byte
64x64 control True; the over-cap case is `LogoSecondReadTest` in
`tests/test_logo_dimensions.py`, a 266,990-byte file whose first 256 KiB
parse as 64x64 and which is refused on size. The summary
replaces `logoHave` rather than adding to it, at 159da94 as now, so a swept
name drops out of the guide at the end of the run. Observed through the
subprocess on 2026-10-11 with a bomb seeded under its hashed name: at
3c8cd65 `swept: 1`, `names: []`, zero files; at 159da94 `cached: 1`, the
name announced, the file still there. The sweep is one header read per
cached file -- `LOGO_HEADER_BYTES`, 128 KiB, and the rest only when the
small read cannot prove a larger file -- through the same parser as the
gate, so for a file the gate wrote the two give one answer: the gate saw
every byte of a download it capped at 256 KiB, and the second read covers
the same bytes under the same cap (the reviewer's 131,445-byte valid 64x64
JPEG whose frame header sits at offset 131,076, four bytes past the first
read, parses as nothing from that read and True from the second; called
2026-10-11). Cost, measured by the helper lane over 5,000 real cached logos
with the page cache warm: the whole `logos --fetch` subprocess went from a
median 375 ms to 601 ms, about 45 us per file, in the helper and off the UI
thread. **Cold cache is unmeasured.**
**The sweep covers the whole cache, not the first 5,000 files a run would
download.** `MAX_LOGO_FILES` used to be checked as a `break` at the top of
the loop, and `fetched` counts new downloads, so in a run that fetched
5,000 new files every cached file later in channel order was neither
validated nor announced -- the guide drew blank slots for logos it already
had and a cached bomb past the cap was never swept, while the comment
beside the sweep claimed the branch was not bounded by the cap (true only
while `fetched < 5000`; the review found the claim). The cap check now sits
BELOW the cached-file branch and `continue`s rather than breaking: a cached
file past the cap is validated and announced, a URL past it is not fetched
this run and is counted in a new summary field, `deferred`, so a run that
stopped short says so. The shell reads only `names` from the summary
(`logoSummaryNames` in `Model.js`), so the field is inert there. Proved by
`LogoFetchCapTest` in `tests/test_logo_dimensions.py`, at the real cap with
a double standing in for the network only: 5,000 new URLs, three files
planted past the cap (two sound, one bomb) and two more URLs after them;
`fetched` 5,000 and exactly the first 5,000 URLs served, `cached` 2 with
both sound names announced, the bomb swept and off disk, `deferred` 3,
5,002 names; then the real helper as a subprocess over the cache that run
left, `cached` 5,002 and the same names. Red against the 995c6be helper
(that one test fails; 85 of 85 green on the fix across tests.test_logo_dimensions and tests.test_logos together, lane commit ddc0a7b; the dimension file alone is 38 at integration).
D-LOGO-12 stays open: the cap bounds fetches per run and nothing yet bounds
what is ON DISK.
**What the fix rests on in the guide, and the blocker the review found
there.** The sweep protects a user only because nothing in the shell decodes
a cache file the helper did not announce -- and at 995c6be the announced set
was a flat `{ name: true }` with no memory of which cache directory it was
announced for. A name is the fnv1a32 of a logo URL, two sources that share a
provider (an Xtream account beside the M3U of the same subscription, which
Sources supports by design) share every URL, and `logoDir` changes on a
source switch while `logoHave` did not: so a name announced for source A
resolved to the SAME file name in source B's directory, a file no fetch had
looked at, which after this fix means a file nobody has bounded. Worse, a
fetch still running for A refused to start one for B, for minutes on a first
enable, so B got no sweep of its own. The repair (lane commit 1a05214) makes
the directory part of the contract: `logoHave` is `{ dir, names }`, tagged
by the service with `logoFetchDir`, the directory the running fetch was
STARTED for and never `activeCacheDir` (`Model.logoHaveSet`); `logoSlot`,
and `wallTile` through it, answer a blank slot for a set tagged for any
other directory, for the old flat shape, and for anything that is not a
tagged set, so a producer still writing the old shape draws nothing
(`logoHaveIsSet`); a
streamed batch merges only into a set for the same directory and otherwise
starts a fresh one, as a COPY, since the rows bind to it
(`logoHaveMerge`); a summary whose `names` is `[]` -- a whole cache swept --
REPLACES the set rather than being ignored for being short, which a
`length > 0` guard used to do (`logoSummaryNames` answers `[]` for it and
`null` for anything that is not the summary); `clearSourceData` resets the
set and the pending batch on every switch; and `fetchLogos` asks
`logoFetchPlan` -- `restart` when a fetch is running for another
directory (signal 15, re-called from `onExited`), `skip` for the same one or
while the setting is off, `start` otherwise -- so the new source gets its
own sweep. `Guide.qml` needed no edit: it hands `have` to Model and never
indexes it. (The five functions new in that commit -- `logoHaveIsSet`,
`logoHaveMerge`, `logoHaveCount`, `logoFetchPlan`, `logoSummaryNames` --
are cited here WITHOUT the `Model.` prefix on purpose: the defect ledger
resolves every `Model.X` citation against this tree's `Model.js`,
and the docs lane's tree predates lane R1's. Once the lanes are merged the
prefix belongs on them, so that check pins the join.) The eight "D-LOGO-11 blocker" checks in `tests/Model.test.js` call each decision (1,903 -> 1,911 node checks, the eighth being check (f) from the integration; with Model.js and Service.qml stashed back to 995c6be the same file prints 10 failures, the eight plus the two re-shaped D-LOGO-8 and M2-04 checks; the lane commit 1a05214 had seven and printed 9). Not observed by any
test: the restart of the live Process on a switch (signal, exit, re-fetch),
which needs the dev harness and is UNVERIFIED. A transient the lane
recorded rather than hid: between a switch and the new playlist loading, a
fetch still running for the OLD directory flushes names tagged for it, blank
in every slot but counted by `ipc status`.
**The gate observes both sinks (harness lane, lane commit e3ffdab).**
`scripts/dev-harness/logo-scenario.sh check-tree` runs the shipping helper
as a subprocess over a loopback https provider and the row slot's `Image`
under the rlimit above, 32 checks plus its own "ran every check" line, in
about 3 s with no bomb decoded; `scripts/check.sh` runs it with a floor of
33 `PASS` lines and `scripts/qa-lib-test.sh` pins that floor to the
scenario's recipe. Observed by the docs lane on 2026-10-11: `check-tree`
33 passed, 0 failed; `--baseline 159da94` 9 passed, 24 failed, K2 reading
`announced rc=0 peak_mb=839` -- the shipped helper announcing the 304-byte
bomb and the probe decoding it. **A skipped gate is red.** A machine without
python3, openssl, util-linux `prlimit` or `/usr/lib/qt6/bin/qml` makes the
scenario exit 77 with the reason as its first line, and `check.sh` treats
77 as a FAIL unless `LOGO_PREFLIGHT_SKIP_OK=1` is set, printing the reason
either way; the first version printed SKIP and went on to `all green`, a
gate that had observed neither sink calling itself green (rule 14's shape).
Details and the mutation table are `docs/QA.md` section 3.2.
**The residuals, each with its size or marked unmeasured.**
- A logo within the bound still costs real memory. Measured by the docs lane
  on 2026-10-11 through the same row-slot probe under the same cap: control
  74.0 MB; a 1920x1080 progressive 4:4:4 JPEG 83.1 MB; 2048x2048 and
  4096x1024 progressive 4:4:4 JPEGs 95.6 and 95.5 MB, so about 21.5 MB over
  control at the bound, consistent with the coefficient arithmetic. That is
  per image; the row slot decodes about twenty asynchronously and how many
  are resident at once is unmeasured, so the sum is not stated.
- The bound is defence in depth for three types and the only bound for one:
  Qt refuses PNG, GIF and WEBP bombs today and the plugin bounds them anyway,
  because a Qt that learns to scale PNG during decode would reopen this in a
  dependency bump, silently.
- A shell not restarted after the upgrade runs the old `Service.qml`,
  `Guide.qml` and `Model.js` until it is. That service invokes the helper by
  path, so the sweep runs on its next fetch -- on cache load, which is shell
  start, a source switch, or a playlist refresh at `refreshMinutes` -- and
  the old service replaces `logoHave` from the summary too (159da94
  `Service.qml:4832`). Until that run, a row scrolling into view decodes
  whatever the old cache holds; a row already drawn has already paid. And
  until the RESTART, the directory tag above is not in place either: the old
  `logoSlot` draws any announced name against whatever `logoDir` is current,
  so the source-switch hole stays open on a shell that has updated and not
  restarted. The README's install section now says to restart with
  `omarchy-restart-shell` after an update, and names `omarchy-refresh-shell`
  as the one not to use (D-HOST-3: it resets `shell.json`). `omarchy plugin
  update` itself ends in a plugin rescan, not a restart, and the guide
  footer reads `Updated`, then `restart the shell to see the new version`,
  until the restart happens (D-HOST-1).
- The real peak of a 65500x65500 progressive JPEG is unmeasured and is not
  claimed. Under the user-session memory scope both were SIGKILLed at
  1.5 GB (lead, 2026-10-09); under the 2.5 GB address-space rlimit the
  allocator refuses the request and Qt reports `Image.Error`, the grayscale
  one at a 325 MB peak after 0.6 s and the 3-component one at 72 MB (harness
  lane, 2026-10-11). What is measured is that the request -- 8.6 GB of
  coefficients for one component, about 12.9 GB for three at 4:2:0 -- is one
  no limit near this size holds; what this machine (`vm.overcommit_memory=0`,
  7.8 GB RAM, 15.4 GB swap) would do with it uncapped is reasoning, not
  measurement.
- `MAX_LOGO_FILES` bounds fetches per run and not the cache. The sweep is no
  longer bounded by it (above), so every cached file for a URL in the current playlist is validated on every
  run; what remains open is the cache's size on disk, which nothing bounds
  (D-LOGO-12, open).
- The windows `LOGO_HEADER_BYTES` and the byte cap leave, stated exactly
  (called on the lane-R2 helper, 2026-10-11). A JPEG whose frame header sits
  past the first 128 KiB costs a second read, not a wrong answer, and the
  comment beside the constant now carries the arithmetic -- a maximal APPn
  segment is 65,537 bytes, two of them put the frame marker at 131,076, so
  the read covers one maximal segment and nearly two, not two. The byte cap
  is enforced on the SECOND read only: a cached file over 256 KiB whose
  header the first read proves within the bound is announced (a 300 KiB
  file with a sound 64x64 header answers True). The shipping gate does not
  write such a file, because `fetch_logo` refuses a download over 256 KiB
  before `write_logo` runs; it is the shape of a file put into the cache by
  something other than this helper, and for it the sweep bounds the
  dimensions and not the bytes. Recorded, not fixed.
**The siblings, asked before closing (engineering rule 15).** Every `Image`
in the four shipped QML files: two, both fed by an announced name, and no
`AnimatedImage`, `icon.source` or SVG anywhere (the lead's census). Every
other number the helper enforces that could bound the wrong axis: one found,
D-LOGO-12. Every other place provider bytes are decoded in the shell: none;
playlist and EPG bytes are parsed in the helper and arrive as JSON.

- Five smaller things the repair round left open, each stated rather than
  rounded away (the review found them recorded in no document):
  1. Turning logos OFF while a fetch is dying sets the same restart flag a
     source switch sets, so OFF-then-ON before the process exits fetches
     again (the plan says "skip" while off, so nothing starts while it is
     off). Confirmed by the lead as intended: it closes a pre-existing gap
     where a quick off/on left no fetch running.
  2. `fetchLogos()` returns `false` on the "restart" plan, where nothing has
     started yet and the re-fetch comes from `onExited` through a debounce
     Timer; no caller reads the value today, and `false` now also means
     "queued".
  3. Once the per-run fetch cap is reached the loop walks the rest of the
     channel list -- one `os.path.exists` per unseen URL, up to
     `MAX_CHANNELS` -- so that cached files past the cap are still validated
     and announced. Untimed; of the order of 10,000 stats at the maximum,
     well under the per-file header read the sweep already costs.
  4. A cached file whose URL has left the playlist is neither checked nor
     swept nor announced -- never drawn, so never decoded, and `cache
     logos-clear` removes it; it is the on-disk growth D-LOGO-12 leaves open.
  5. Twelve of the thirteen scenario scripts (every one but logo-scenario.sh;
     tls-scenario.sh among them, with a tool check for the dirname to sit
     above, where argv-, chno-, chno-entry-, id-rotate-, player- and
     sources-scenario.sh have no tool check at all) keep the
     `HERE=$(dirname ...)`-above-the-tool-checks shape that logo-scenario.sh
     and the spike's run.sh repaired; cosmetic (a shell error line before the
     SKIP reason on a machine with no PATH) and listed for the next harness
     round rather than widened into a security release.
  6. A fetch planned by the 50 ms rerun Timer can start for a source whose
     `channels.json` has not landed yet (the helper then runs over no
     channel list, for milliseconds), and when the playlist lands while that
     helper is still running the `onLoaded` plan reads "skip" for the same
     directory, so that source's logos wait for the next trigger. Narrow,
     fail-closed, and narrower than before this release, when the old fetch
     was never stopped at all. Found by the final review; the live
     observation that would pin it is listed under F-M3-18.

Raised 2026-10-11 (D-CLIP-1), and written here in the round that fixes it --
the state of that fix is the board row in `docs/STATUS.md`, not this
paragraph. **The same maintainer, the sixth finding in five calendar days
(2026-10-07 to 2026-10-11, inclusive), on the verification request for the
commit that fixed the fifth** (0.13.4, d55149b,
omacom/omarchy-plugin-marketplace#11077): the first-run and add-source forms
instantiate editable `qs.Ui.TextField` controls, and a clipboard change makes
Qt read the offer before any `maximumLength` or paste handling applies, with
no total byte limit and no deadline, so a foreign Wayland clipboard producer
can stall or exhaust the shared shell. He was right, with his Qt versions
inverted, which is settled below.
**A new class once more, and naming it is the point: an INPUT sink that
BLOCKS.** Every entry above this one is a place a secret of ours was written
or sent, and each was closed by narrowing where it went. Here nothing of ours
leaves. The exposure runs the other way: a byte stream chosen by any other
program on the desktop is pulled INTO the long-running shell, on its main
thread, synchronously, whenever that program changes the clipboard -- a read
the plugin never asked for, that no user action precedes, and whose size and
duration the producer sets. The sink is not a channel but a SUBSCRIPTION. An
editable `TextInput` connects `QClipboard::dataChanged` to its own
`q_canPasteChanged` at construction, so the cost is paid by existing, not by
being used: focus, visibility and the user's hands have nothing to do with
it. The sink list had only ever asked where our bytes go; it had never asked
what a control we instantiate agrees to receive.
**Mechanism, by the RELEASED sources, read by this lane on 2026-10-11 from
code.qt.io's `plain` endpoint at the tag, not at a branch head.**
`QQuickTextInput::q_canPasteChanged` on v6.11.2
(`src/quick/items/qquicktextinput.cpp:3010`) reads
`canPaste = mimeData->hasText() && !mimeData->text().isEmpty();` under
`if (!d->m_readOnly)`; v6.12.0 (line 3009) is character for character the
same. `text()` is the whole-offer read: on Wayland
`QWaylandMimeData::retrieveData_sys` reads the offer through a pipe, `poll`
with a 1 s timeout per read, 4 KB per read, no total limit and no overall
deadline, and caches the result until the next offer (the lead's read of
qtbase 6.12 `qwaylanddataoffer.cpp`, recorded in `docs/QA-RESULTS.md`
"Sixth maintainer finding"; not re-read here). `m_readOnly` is the only
switch on the slot, in every version of it read.
**Measured, three times, by two lanes, and attributed rather than inferred.**
The lead, on the live session on 2026-10-11 before any lane was briefed
(`docs/QA-RESULTS.md`, the table under "Sixth maintainer finding"): a
throwaway Wayland client (`qml`, never the shell) holding one
`QtQuick.Controls` `TextField` -- the base type the host's `qs.Ui.TextField`
inherits -- and a foreign `wl-copy` offering 100 MB of `text/plain`, resident
set sampled every 100 ms from outside: `readOnly: false` 164 -> 403 MB,
+238 MB, last growth 600 ms after the offer; `readOnly: true` +0; a window
with no field at all +52 MB, which a gdb catchpoint on `pipe2` then showed
was the toolkit starting and not the clipboard -- eighteen `pipe2` stops on
the editable probe, four of them the toolkit's own thread-start pipes that
the no-field run has too, and the other FOURTEEN all after the offer and
every one `QMimeData::text()` called from
`QQuickTextInput::q_canPasteChanged` out of `QPlatformClipboard::emitChanged`
(the signal fires once per mode and `text()` tries two MIME types), and zero
after the offer on the no-field probe. An earlier version of this sentence
said "ten"; the count is from the lead's `gdb-editable.log`, re-counted by
the adversarial review. Lane A, the same three probes unmodified,
INSIDE a nested headless cage so the user's clipboard was never touched (the
run directories under the lane's scratch, `cage-run-{readonly,editable,
probe}`, summarised by this lane from their `rss` and `offer` files):
`readonly.qml` 282 -> 282 MB, +0; `editable.qml` 282 -> 566 MB, +284 MB, its
growth over in four steps at 117, 224, 331 and 438 ms after the offer and
nothing in the 52 samples after; the heartbeat probe 285 -> 489 MB, +204 MB,
with one 4 KB blip at 6,495 ms that an earlier version of this sentence
misattributed to the editable run as "last growth 6.9 s after the offer"
(re-derived from the same `rss` and `offer` files by the adversarial
review; the direction was harmless, the attribution was wrong). The number is
stable across compositors and the sign is the same; the magnitude is about
twice the payload (the bytes and the decoded string) and is NOT a floor,
since the pipe read has no limit at all. One condition lane A found that is
load-bearing for the gate (R7): the cage's headless seat has no keyboard, a
compositor hands `wl_data_device.selection` only to the client with keyboard
focus, and on the first run NOT EVEN the editable probe read (+0 on both);
the sink opened only with a virtual keyboard (`wtype`) held open on the
nested display across the offer. A scenario that omits that passes
vacuously on the baseline.
**Where it came from and where it has gone, every date checked by this lane
against code.qt.io on 2026-10-11.** qtdeclarative `c82ef988` ("QQuickTextInput:
check if text is empty in q_canPasteChanged"; authored 2026-02-16 by Assam
Boudjelthia, committed to the 6.11 branch 2026-02-18 by the cherry-pick bot
as a pick of `6c07e2a7`) ADDED the `text()` call, so that an offer advertising
text with an empty payload reads as not pasteable; it shipped in 6.11.2.
`7d0a433a` ("QQuickTextInput: don't call QMimeData::text() for canPaste
[6.11]"; authored 2026-08-29 by Will Rose, committed to 6.11 on 2026-09-15
as a pick of `ef692a52` and `bcbfae67`, `Fixes: QTBUG-149610`,
`Task-number: QTBUG-121594`) REMOVED it, restoring the format-only check
`QQuickTextEdit` always had, and its message names the harm: blocking on an
unresponsive clipboard owner in a synchronous IPC call. The branch heads of
`6.11`, `6.12` and `dev` all read `canPaste = mimeData->hasText();` today.
The RELEASES do not: v6.11.2 is the newest 6.11 tag (no v6.11.3 exists as of
this reading) and v6.12.0, tagged in the last two weeks, carries the read at
line 3009. So the maintainer's "supported Qt 6.12 path" is right about the
released 6.12.0 and wrong only in implying 6.11.2 is spared: EVERY released
Qt this shell could run on reads, and the removal exists on branches alone.
The Jira page for QTBUG-149610 could not be read without a login and its
status is UNVERIFIED from here; the trailer is cited from the commit.
**What changed (lane A, commit 44b250b on `lane-clip-code`; the line numbers
are that tree's).** The fix is at the SUBSCRIPTION, not at the paste:
`Guide.qml:4779` declares the form `TextField` `readOnly: true`, always --
focused or not, masked or not, revealed or not -- with no binding, because a
binding is a way back. A read-only control still keeps its caret, its
selection, Home / End, `Ctrl+A`, `Ctrl+C` and mouse selection natively
(pinned by `test_readOnlyFieldPremises` in the QML spec -- and that clause
was FALSE for `Ctrl+C` and the mouse at 44b250b, where the spec pinned
neither and both were true by source alone, rule 14's shape, found by the
adversarial review; since 51866a3 `Ctrl+C` is measured by pasting the
copied selection into the editable control and a click and a drag are
measured on a dedicated non-overlapping read-only control, with
`selectByMouse` at the default the host's `TextField` inherits), so the
plugin does the rest itself: `handleFormKey` (`Guide.qml:2667`), which already saw every
key first through `Keys.forwardTo`, applies printable insertion, Backspace,
Delete, their Ctrl word variants and cut to the MODEL value through
`Model.editInsert` / `Model.editDelete` (`Model.js:10484`, `:10500` at
51866a3) and `applyEdit` (`Guide.qml:2737`) writes it back through
`Model.withFormValue` and restores the caret synchronously, because a bound
write parks Qt's caret at the end (measured). The RANGE an edit applies to
-- the selection, or the whole value of a masked field, which is how "a
masked field is fully selected" is implemented -- is `Model.editRangeFor`
(`Model.js:10399`), called at both sites (`Guide.qml:2647` and `:2698`);
at 44b250b that decision sat in `Guide.qml` alone at the two sites and the
whole gate stayed green with the branch deleted (the review's P2, rule 12),
which is why it was lifted. `Ctrl+X` is gated on the field's echo by
`Model.cutApplies` (`Model.js:10411`, `Guide.qml:2706`), so the password
field's cut is the no-op it is natively (Qt's own `cut()` is gated on
`echoMode == Normal`), measured in the spec as
`test_passwordCutIsNativelyANoOp`; at 44b250b it deleted the selection with
nothing on the clipboard to paste back. The word boundary is Qt's own, taken position by
position from a real `TextInput` into `tests/fixtures/form-edit.js`, which the
spec re-measures on every run. Paste is the process path ONLY:
`pasteViaProcess` is `true` (`Guide.qml:593`), `Ctrl+V` and `Shift+Insert`
reach the handler as `StandardKey.Paste` (measured, both), and
`Service.requestClipboard` (`Service.qml:1856`) runs the HELPER, not
`wl-paste`: `Model.clipboardArgv` (`Model.js:10329`) is
`["python3", <helper>, "clipboard"]`, and the helper's `read_clipboard`
(`bin/omarchy-iptv:8100`, R8, lane commit 51866a3) runs
`["wl-paste", "--no-newline", "--type", "text"]` with a pipe on its stdout,
reads at most `MAX_CLIPBOARD_BYTES` = 32,768 bytes from it (8,192 UTF-16
units, `Model.LIMITS.url * 4`, times the 4 bytes a UTF-8 character can
need), terminates the child the moment the cap, EOF or its 5 s deadline
(`CLIPBOARD_TIMEOUT`, `Model.CLIPBOARD_TIMEOUT_MS`, one shared fixture
`tests/fixtures/clipboard.json`) is reached -- SIGTERM, a 1 s grace,
SIGKILL -- and prints ONE JSON line, nothing on stderr, with the text cut at
a character boundary to at most 8,192 units; a timeout, a failed or a
missing `wl-paste` is `{"ok": false, "code": ...}` with no text, and no
error names what the clipboard held. The shell parses that line with
`Model.parseClipboardReply` (`Model.js:10348`; null for anything that is
not an ok reply with a string text, the cut re-applied) and emits
`clipboardText` only then, so a failed paste never clears a field; the
`clipboardWatchdog` `Timer` (`Service.qml:5208`,
`Model.CLIPBOARD_WATCHDOG_MS` = 5,000 + 1,000 + 2,000 = 8,000 ms) is the
OUTER bound and SIGTERMs the helper that has not answered by then -- a
child dies, never the shell. The helper is the process allowed to hold the
bytes briefly and die; the shell holds only the bounded reply. The guide
then runs the text through `Model.sanitizeInput` at the field's
`Model.formCapacity` and `Model.editInsert` over the range
`Model.editRangeFor` returns (`pasteFromProcess`, `Guide.qml:2638`). Qt
draws no caret on a read-only input and never instantiates its
`cursorDelegate` there (measured: dark-pixel count 0 against 20 editable), so
the field draws its own `Rectangle` on the native `cursorRectangle`
(`Guide.qml:4833`, `Style.spacing.hairline` wide, `field.color`, blinking at
half `Application.styleHints.cursorFlashTime`). Nothing in the shell process
asks Qt for the clipboard any more: `Guide.qml`'s `clipboardText()` was kept
unreachable at 44b250b only because `tests/a11y/fidelity.py` pinned its
line, and the two were dropped together at 51866a3 (five transform rules
remain, were six; the a11y test count, 34, is unchanged). Counts: node
1,911 -> 2,026 at 44b250b -> 2,074 at 51866a3; QML spec 73 -> 77 -> 78;
python 1,026 unchanged -> 1,046 (`tests/test_clipboard.py`, the verb as a
subprocess against a stub `wl-paste` that streams, hangs, ignores SIGTERM,
fails or is absent); the red proofs are the two lanes' commit messages.
**The residuals, each with its size or marked.**
- **The host kit's own field is exposed in every host form, and that is
  Omarchy and Quickshell business, upstream.** `Ui/TextField.qml` on omarchy
  4.0.4 inherits Qt Quick Controls `TextField` and never touches `readOnly`.
  A grep over shape on this machine (engineering rule 15; 2026-10-11) finds
  editable `TextField`s at `plugins/panels/network/Panel.qml:1841` and
  `:1865` (the passphrase prompts), `plugins/panels/clock/Panel.qml:381` and
  `:404`, `plugins/panels/weather/Panel.qml:615`,
  `plugins/panels/tailscale/Panel.qml:601`, `Ui/MultiSelect.qml:407`,
  `Ui/SearchableDropdown.qml:205` and the dev gallery; and three that gate
  `readOnly` on something other than "not being edited":
  `Ui/NumberField.qml:80` (`readOnly: !spin.editable`),
  `plugins/lock/LockView.qml:146` (read-only only while authenticating, so
  the LOCKED screen's password field subscribes) and
  `plugins/polkit/PolkitAgent.qml:323`. Which of those exist while their
  panel is closed is UNVERIFIED: the grep finds declarations, not instances.
  The draft report is quoted below; the facts are in
  `docs/OMARCHY-PLUGIN-CONTRACT.md`.
- **The host's Qt is what the user has.** The plugin cannot ship a Qt. When
  a Qt carrying `7d0a433a` reaches this distribution the read stops for the
  host's fields too; the plugin's fields stay read-only regardless (ruling 1
  below says always), because the subscription remains even when its slot
  is cheap, and a rule with a version number in it is the rule the next
  cherry-pick breaks.
- **The read-only field loses input-method composition** (ruling 5, stated
  rather than hidden): dead keys, Compose and CJK input never reach a
  read-only `TextInput`, so accented or non-Latin characters cannot be TYPED
  into the label field. What arrives instead, MEASURED by the adversarial
  review under a nested cage (Qt 6.11.2, QT_QPA_PLATFORM=wayland, `wtype -k
  dead_acute -k e` then `x` into a read-only `TextField` logging
  `Keys.onPressed`): the dead key as a bare press with empty text
  (`Qt::Key_Dead_Acute`), then `e` and `x` as ordinary text -- so the base
  letter is inserted and the accent is dropped, where the same rig's
  editable control received e-acute. Both platform input contexts refuse to
  compose when the item does not accept input method
  (`qcomposeplatforminputcontext.cpp:72`, `qwaylandinputcontext.cpp:260`).
  An earlier version of the QA expectation said the sequence inserts
  NOTHING; it was wrong, and is corrected where it stands (SRC-KEY-03).
  ASCII typing is unaffected; a paste carries any Unicode; URLs, server,
  username and password are ASCII by nature. Native undo (`Ctrl+Z`) is
  gated by `readOnly` as well and is gone with it. The README and
  UX-SOURCES say so.
- **Middle-click paste of the primary selection is gone**, since it was Qt's
  and the control no longer edits; `Ctrl+V` and `Shift+Insert` remain.
- **The primary-selection WRITE is a sink this list had not named, and it
  is pre-existing, user-initiated and unchanged.** `readOnly` gates the
  middle-button PASTE in `QQuickTextInput::mouseReleaseEvent` (v6.11.2) but
  not the left-button half of the same handler: on every left release, when
  the platform supports a selection (Wayland does), the control copies its
  selection to `QClipboard::Selection`. So a drag across a REVEALED
  playlist, EPG or server field publishes the raw credentialed URL to every
  client that reads the primary selection, exactly as it did on d55149b and
  as any Qt text field does; the password field is exempt (`copy()` is a
  no-op under `echoMode` Password), a masked field shows `****` and a
  selection of that is `****`. The host's own clipboard plugin (`wl-paste
  --type text --watch`) reads the CLIPBOARD and not the primary, so it is
  not that reader. Recorded by the adversarial review of 44b250b (source
  read, not measured) so the sink list is complete; not a defect of this
  change and not changed by it. The lesson is the one D-SINK-4 taught, one
  level down: a sink can be opened by code we did not write, and here by a
  gesture, not an API.
- **A USER paste of a huge clipboard pulled the whole offer into the shell
  before the cap** (lane A's DR-1) -- CLOSED by R8 (51866a3), measured both
  ways. At 44b250b and 96f5261 `clipboardProc`'s stdout was a
  `StdioCollector` with `waitForEnd`, so the 8,192-unit cut was applied to a
  string the shell had already received in full: the watchdog bounded TIME,
  not bytes. The adversarial review measured it first (nested cage, the
  harness shell in the first-run form, a 100 MB `wl-copy` on the nested
  display, `Ctrl+V` through the harness, RSS sampled from outside): the
  fixed shell 343 -> 642 MB, +298, and 621 MB (+278) at the end of the
  window, with the retention run flat at 627 MB from +10 s to +30 s -- the
  memory did not come back when the paste completed. Lane A on its own rig,
  the same scenario variant on both trees: 96f5261 before 334 MB, peak 639,
  +304, last growth at +6,883 ms, +292 kept at the end of the window, no
  helper child (the shell ran `wl-paste` itself); 51866a3 before 329, peak
  330, +0, 327 at the end of the window, the clipboard helper seen as the
  shell's child with a peak RSS of 32 MB and gone afterwards, the field
  holding 2,112 characters of the paste (`Model.formCapacity`), so the
  paste landed. The exhaust half of the maintainer's finding is no longer
  reachable by a keypress. What the helper does is in "What changed" above;
  the ruling is (8) below. The scenario variant that measures it is in lane
  A's scratch for the harness round to lift (`DR1`, 20 checks, L9 moved to
  the helper child); at 51866a3 the tree's own `clip-scenario.sh` L9 still
  asks for a `wl-paste` child of the SHELL, which since R8 pins less than
  it says.
- **`wl-paste` is now the paste path and not a fallback**, run by the
  helper's `clipboard` verb, so paste needs `wl-clipboard` on PATH (an
  Omarchy default, present here at 2.3.0); without it the verb answers
  `{"ok": false, "code": "no_wl_paste"}` and the paste changes nothing,
  silently. A `Clipboard unavailable` transient is a UX decision (lane A's
  DR-4: a failed paste stays silent this release), and so is surfacing the
  reply's `truncated` flag, which the verb reports and the shell parses but
  nothing shows (lane A's OQ-4): a clipboard longer than 8,192 characters
  silently keeps its first 8,192, then `formCapacity`.
- **A shell not restarted after the upgrade runs the old `Guide.qml`** and
  keeps the editable field until it is; the README's install section already
  says to restart with `omarchy-restart-shell`.
- **The accessible role stays `Accessible.EditableText` on a control that is
  read-only to Qt.** What the bridge would publish for that (the `readOnly`
  state, the role) is UNVERIFIED and moot while D-GS-3 keeps every node off
  the bus.
**The siblings, asked before closing (engineering rule 15).** The lead's
sweep (R6): `Guide.qml:4779` is the only `TextInput`-derived element in the
shipped QML; the search line is a plain `Text`; the host kit's
`qs.Ui.NumberField` is not used. Lane A's: a grep for
`TextField|TextInput|NumberField|clipboardText|Quickshell\.clipboard` over the
shipped QML finds the one field and, at 44b250b, the one unreachable Qt
clipboard read, deleted at 51866a3; the dev-harness fake and the
accessibility fakes stub `requestClipboard` and never bind `clipboardText`.
This lane's: the host-side list above, which is the same shape in files this
plugin does not own. Lane A's second sweep for R8, "where else does the
shell collect a child's whole output" (`StdioCollector` with `waitForEnd`
over `Service.qml`; `Guide.qml` owns no `Process`): every provider-fed
collector reads a one-line status JSON the helper composes, with the
provider bytes going to a cache file capped at `MAX_SOURCE_BYTES` (64 MiB)
in the helper, under a 180 s, 8 s or 12 s watchdog; the one byte-bound
observation is the `playlist` status line's `warnings` list, one entry per
channel with an option-looking or unsafe-header key and capped only by
`MAX_CHANNELS` (50,000) times the name length, so a hostile playlist can
make the one line `playlistStdout` collects a few MB -- a count cap with a
tail line is the sibling-shaped fix, listed and not done (lane A's OQ-6,
decision requested). Every other subscription a shipped element makes to a
global that any process can change is the question this entry leaves open
as a shape, not as a list: none other is known, and "known" is what the
earlier maintainer-raised entries also said.
**The gate observes the sink (ruling 7; lane B).** A scenario that runs the
REAL `Guide.qml` through the dev-harness fake shell under a nested headless
cage in the harness's `FloatingWindow` mode (the layer-shell window never
maps there, `docs/SPIKE-CAGE-HEADLESS.md`), holds a virtual keyboard on the
nested seat, opens the form, has a foreign producer offer 100 MB of
`text/plain` inside that compositor, and asserts the shell's RSS and an IPC
round-trip unchanged on the fixed tree and the read on `--baseline d55149b`;
its compositor-free half runs in `scripts/check.sh`. It landed as
`scripts/dev-harness/clip-scenario.sh` (824ced4, integrated into `dev` as
85b7fe3 on 2026-10-11): `check-tree` is the probe arm alone, P1-P6 under
`timeout`, reported by the gate as "clip preflight (7 checks)" with
`CLIP_PREFLIGHT_MIN` 7; `live` adds L1-L11 (18 checks) and takes
`--baseline d55149b`. The counts, each from a transcript the run prints as
its first line: the adversarial review on 824ced4, check-tree 7 / 0 (the
editable probe +259 MB, read-only +0, no-field +0, the consumer reading
104,857,600 bytes), live 18 / 0 at +0 MB with the worst IPC round trip
124 ms after a 100 MB offer, baseline 16 / 2 with L4 red at +240 MB (peak
589) and L5 red at 746 ms; its second reviewer's own worktree, fixed +0 MB
/ 146 ms and baseline +264 MB / 729 ms; lane A on 51866a3, live 18 / 0 in
24.8 s with L7 and L8 pasting through the helper verb. The offer in the
gate arm is 100 MB on the tree at 51866a3 and the lead has ruled it drops
to 25 MB there (DR-B1, `CLIP_OFFER_MB`; 100 stays in `live`), the harness
round's change. Two things the review found in the scenario, both the
harness round's and neither on the tree yet: it traps `EXIT` only, so a
`TERM` or `INT` while it waits on a child strands the cage, the detached
shell and a stale nested socket where `player-`, `rewind-` and
`tls-scenario.sh` carry `trap 'exit 130' INT` and `trap 'exit 143' TERM`
(parallel rule 3; rule 15, the siblings had it); and its header's "by
recorded pid" is true of the file and not of the `run.sh reap` it
delegates to, which after the pid-file kill sweeps by patterns anchored to
the harness directory. The specification it met is `docs/QA.md` section
3.3.
**Ruling, as briefed by the lead for this round (numbered 1-7 here; the lane
briefs called them R1-R7).** (1) While the form is open no editable
`TextInput` exists in the shell: every field `readOnly: true`, always.
(2) Paste is the out-of-process path only, capped where it was, with a
bounded child. (3) The password field keeps `echoMode` Password; masking is
unchanged. (4) The edit logic is in `Model.js` and called from node, with
Qt's own word boundary measured, not assumed; the over-cap behaviour is
refused, never cut. (5) The input-method loss is stated where the user reads
and where the design lives. (6) The sibling sweep above. (7) The gate observes
the sink, with the compositor-free half in `check.sh`. (8) Added by the
lead for the second round (R8, after DR-1 was measured): the shell never
holds more than the bounded reply -- the helper's `clipboard` verb runs
`wl-paste` with a pipe, reads at most `MAX_CLIPBOARD_BYTES` and terminates
the child at the cap, EOF or its deadline, prints one JSON object and
nothing on stderr, never logs the text and never names the clipboard
contents in an error; the shell runs it through the same `Process`, parses
with `Model.parseClipboardReply`, keeps its watchdog as the outer bound and
emits `clipboardText` only on ok. The helper is the process allowed to hold
the bytes briefly and die; the shell is not.
**Upstream, drafted here and filed.** Two reports, because the two parties
can each act and neither can act for the other. The Omarchy report went in
as omacom/omarchy#15083 on 2026-10-11, in the form of #12009. The Qt side:
QTBUG-149610 IS this bug (summary "TextInput canPaste is recomputed eagerly
on QClipboard::dataChanged() (2 s stall per focus-in on Wayland)", created
2026-08-29, Closed / Fixed, affected 6.8.8, 6.10.3, 6.11.0-6.11.2 and 6.12.0
Beta3, fix versions 6.8.10, 6.12.1 and 6.13 -- and NO 6.11.x fix version,
although the 6.11 branch carries the commit), read through the tracker's
public REST endpoint the same day. The comment below asks for a 6.11.x fix
version and records the memory-exhaustion half; it waits on a tracker
login, which the lead's tooling does not hold.

> **To Omarchy (omacom/omarchy), against `Ui/TextField.qml` on 4.0.4.**
> `Ui/TextField.qml` inherits Qt Quick Controls `TextField` and leaves
> `readOnly` false, as every caller of it does while a panel is open. On the
> Qt Omarchy ships (6.11.2; released 6.12.0 behaves the same), every editable
> `QQuickTextInput` connects `QClipboard::dataChanged` to
> `q_canPasteChanged()`, which calls `QMimeData::text()` -- the entire offer
> -- synchronously on the shell's main thread, every time ANY client changes
> the clipboard. On Wayland that read is a pipe with a 1 s timeout per read,
> no total limit and no deadline. So while a host panel with an editable
> field is open -- the network passphrase prompt, the clock and weather
> panels, tailscale, `MultiSelect`, `SearchableDropdown`, and the lock
> screen's password field, which is read-only only while authenticating --
> a producer offering N bytes grows `omarchy-shell` by about 2N, and one that
> drips a byte every 900 ms holds its main thread for as long as it likes.
> Measured on 2026-10-11 (Qt 6.11.2, Hyprland 0.56.2, `wl-copy` offering
> 100 MB of text/plain to a throwaway `qml` client): one
> `TextField { readOnly: false }` 164 -> 403 MB within 600 ms of the offer;
> the same with `readOnly: true` +0; a window with no field created no pipe
> after the offer (gdb catchpoint on `pipe2`: zero hits after it, and the
> 52 MB that window grew by is toolkit startup; on the editable field every
> hit after the offer is `QMimeData::text()` called from
> `QQuickTextInput::q_canPasteChanged`). Upstream: qtdeclarative
> `c82ef988` added the read on the 6.11 branch on 2026-02-18 (shipped in
> 6.11.2) and `7d0a433a` removed it on 2026-09-15 (`Fixes: QTBUG-149610`);
> as of 2026-10-11 no released Qt carries the removal. `readOnly` is the only
> switch on the slot in every version. Ask: until a Qt with `7d0a433a`
> ships, keep the kit's fields `readOnly: true` whenever they are not being
> edited (or always, and edit through the key handler the panels already
> have), or bound what the shell will read. The IPTV plugin
> (`io.github.rmcdavid.iptv`) has done the former for its own form after a
> marketplace review raised it (omarchy-plugin-marketplace#11077): every
> field read-only to Qt, editing applied by the plugin, paste through a
> helper process that reads at most 32 KiB of `wl-paste`'s output under a
> deadline and hands the shell one bounded reply. Reproduction: three
> ten-line QML files (editable, read-only, no field) and one `wl-copy`,
> available on request.

> **To Qt, as a comment on QTBUG-149610 (confirmed to be this bug): released 6.11.2 and 6.12.0 read the whole
> clipboard synchronously on every `dataChanged`; please ship `7d0a433a`.**
> `QQuickTextInput::q_canPasteChanged()` in v6.11.2
> (`qquicktextinput.cpp:3010`) and v6.12.0 (`:3009`) evaluates
> `mimeData->hasText() && !mimeData->text().isEmpty()` for every editable
> `TextInput`, on every `QClipboard::dataChanged`, with no user action. On
> Wayland `text()` reads the entire foreign offer through a pipe with a 1 s
> per-read timeout, no total byte limit and no deadline, so any client on
> the seat can grow a Qt Quick application by the size of an offer or hold
> its GUI thread indefinitely, merely by having an editable field exist in
> it. Measured on 6.11.2 with a 100 MB text/plain offer from `wl-copy`: one
> `TextField { readOnly: false }` +238 MB within 600 ms; `readOnly: true`
> +0; attributed by a `pipe2` catchpoint to `QMimeData::text()` called from
> `q_canPasteChanged`. The read arrived in `c82ef988` (6.11, 2026-02-18, a
> pick of `6c07e2a7`) and `7d0a433a` (6.11, 2026-09-15, a pick of `ef692a52`
> / `bcbfae67`) restores the `hasText()`-only check, but no release contains
> it: the newest 6.11 tag is v6.11.2 and v6.12.0 still carries the read. A
> desktop shell written in Qt Quick (Omarchy's, on Quickshell) is exposed in
> every form it opens, including its lock screen's password field. Ask: a
> 6.11.3 and a 6.12.1 carrying the fix, and, if `QTBUG-149610` is not this,
> a tracking bug for the denial-of-service aspect, which the commit message
> describes as a responsiveness issue.

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
| Helper `logos --fetch`, cached-file check | ~45 us per cached file; the whole subprocess 375 -> 601 ms median over 5,000 cached logos, page cache warm (D-LOGO-11, helper lane) | one `LOGO_HEADER_BYTES` read per file, no decode, in the helper; cold cache unmeasured |

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
12. A provider's bytes are bounded on every axis the decoder's cost depends
    on, not only on their count. A byte cap bounds a download; a decoder's
    cost is quadratic in the dimensions the header declares and the bytes
    need not honour them, so `write_logo` also refuses, for all four allowed
    image types, a header that declares a side over 4096 px or more than
    4,194,304 px, or that cannot be read, before anything touches the disk;
    and a cached file is proved the same way before its name is announced,
    because the guide decodes only what the helper names, and only for the
    cache directory it named them for: the announced set carries that
    directory, a set for any other directory draws nothing, and a source
    switch clears it and restarts a fetch still running for the old one
    (D-LOGO-11). Verified by calling the shipping predicate over a header
    fixture, by calling the Model decisions from node, and by observing the
    sweep and the row slot's `Image` through `logo-scenario.sh`; a grep for
    the constant is rule 14's shape and is not the check. Section 6 carries
    the measurement and the residuals.
13. The shell process never subscribes to a global that another process can
    fill. The clipboard is the instance (D-CLIP-1): an editable `TextInput`
    subscribes to `QClipboard::dataChanged` and the released Qt reads the
    whole offer in that slot, so every form field is `readOnly: true`
    always, the plugin applies edits to the model itself, and the one
    clipboard read the plugin makes is user-initiated and out of process:
    the helper's `clipboard` verb reads at most `Model.CLIPBOARD_MAX_BYTES`
    (32 KiB) of a `wl-paste` child's output under `Model.CLIPBOARD_TIMEOUT_MS`
    and answers one bounded JSON line, and the shell -- which holds only
    that reply, never the output -- kills a helper that has not answered by
    `Model.CLIPBOARD_WATCHDOG_MS` and never waits in itself (R8). Verified by calling `Model.editInsert` / `editDelete` from
    node against a word boundary measured on a real `TextInput`, by pinning
    the read-only premises in the QML spec, and by observing the shell's
    memory and an IPC round-trip while a foreign producer offers 100 MB
    inside a nested compositor (section 6's entry; `docs/QA.md` 3.3). A
    grep for `readOnly: true` is rule 14's shape and is not the check.

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
