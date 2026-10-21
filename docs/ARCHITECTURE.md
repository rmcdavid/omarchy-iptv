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
| Pure logic | `Model.mjs` and the parts under `model/` (ES modules since D-REL-5; ES5-style `var`/`function` declarations inside) | Loaded by both the QML engine (`import "Model.mjs" as Model`) and node (`require` or `import`), so search/grouping/state rules are unit-tested without a shell. It was the one-file `Model.js` (precedent: dell-power, tailscale) until that file outgrew the marketplace scanner's 512 KiB per-file limit; section 9 has the rules the split adds. |
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
| `Model.mjs` | The model's public surface: re-exports every public name from the part that declares it. Header comment and generated export lines only. |
| `model/*.mjs` | Pure logic shared by QML and node, one part per domain: normalization, ids, filtering, groups, state, settings, logos, mpv argv, the player, picture in picture, privacy, EPG, contrast, the guide view, sources, form editing. Cut from the one-file `Model.js` by `scripts/split-model.mjs` (D-REL-5). |
| `bin/omarchy-iptv` | Python 3 helper (executable, stdlib only), every verb's entry point. Since D-REL-7 a stub: the docstring, the D-SINK-9 shield, and a generated loader that compiles the parts into its own namespace. |
| `bin/helper/NN-*.py` | The helper's body, cut by domain at its section banners (core, sources, IO and playlist, EPG, IPC and logos, dead-channel marks, the player, its verbs, cache, state, CLI). Not modules: compiled in the stub's order into one namespace. |
| `tests/Model.test.js` | node runner for the model (`Model.mjs`). |
| `tests/Model.spec.qml` | QtTest spec proving the model loads in the QML engine. |
| `tests/test_playlist.py` | Parser unit tests (attributes, EXTGRP, VLCOPT, KODIPROP, ids, normalization parity with the model). |
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
`"kind": "epg"`. A feed that declares an XML entity is refused as
`bad_xml` with one sentence and no URL, before ElementTree reads a byte of
it (D-EPG-6, security standard 2); a `<!DOCTYPE tv SYSTEM "xmltv.dtd">`
line without an internal subset is accepted as it always was.

### `state.json` (service <-> disk, via `Model.parseState`)

```json
{ "version": 1,
  "favorites": ["t:bbc1.uk", "u:3f2a9c11"],
  "recents": [ { "id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000 } ],
  "lastPlayed": { "id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000 } }
```

`recents` is newest first, capped at `maxRecents`. Favorites keep their
insertion order (that is the order of the Favorites group).

The block above is the version-1 shape and is kept for the fields it shows;
version 2, with the Sources history, is specified in `ARCHITECTURE-SOURCES.md`
2.1. Amended 2026-10-11 (D-SINK-19): version 2 also carries `activeKey`, the
key of the active source, additive with no version bump on the `hiddenGroups`
precedent -- and it is the field whose absence un-configures the plugin, since
`state.json` is now the ONLY place the active source is named. It is read
through `Model.activeKeyOf`, which answers `""` for a key naming no record in
`sources[]`, and it is taught to all three whitelists (`Model.parseState`,
`Model.cloneState`, the helper's `normalize_state`), each through a type test
rather than a string coercion, because the shared fixture found `str()` turning
the number `12345678` into a valid-looking key on one side and not the other.
Amended 2026-10-12 (D-SINK-19 round 9, R19b/R19c; lane-key-y1): version 2
also carries `pendingEpg { url, seenAt }`, a guide URL input held while no
source is active, absent when nothing is pending, and each source record an
optional `epgSetAt` (ms, when its guide URL was set), both additive with no
version bump and both absent in a file that has neither, so such a file
serializes exactly as before. They are taught to `Model.parseState` and
`Model.cloneState` (read through `pendingEpgOf` and
`epgSetAtOf`) and NOT to the helper's `normalize_state` /
`normalize_source`, so any helper write of the file erases them -- the first
state keys added to fewer than all three whitelists, recorded as open in
`ARCHITECTURE-SOURCES.md` 2.1 rather than called fixed. [Round 10: that
was D-SRC-20, a P1 on the chain -- a hand-run `state favorite add` and a
restart left a CLI guide URL nowhere -- and it is closed.] Amended
2026-10-12 (D-SINK-19 round 10, R20a/R20b; lane-key-z1): the helper's
`normalize_state` and `normalize_source` now carry `pendingEpg` and
`epgSetAt`, validated and never invented, on ONE shared fixture
(`tests/fixtures/state-keys.json`) both suites run; and a node check holds
every key the service can serialise, top level and per record, to that
fixture's vocabulary, so a key added to one reader and not the other is a
red gate on the day it is added. Version 2 also carries `entryInputs`, a
DIGEST per bar-entry input of the value the service last consumed (never
the value), with when and whether an owned write has since stripped it --
so a restart no longer reads every value still on the entry as new --
additive and absent when empty, and taught to all three whitelists on the
day it was added. The helper's `state` verbs print the held guide URL as
its host only. Amended 2026-10-13 (D-SINK-19 round 11, R21; the product owner dropped
the `omarchy bar set` URL route): `pendingEpg`, `epgSetAt` and `entryInputs`
are WITHDRAWN with the machinery that wrote them (R21d), and both readers drop
them from a file an earlier build of the chain wrote. Version 2 carries one
new optional key instead, `entryMigrated`: exactly `true` once the one
migration of a 0.13.x install has adopted what its bar entry carried, absent
otherwise, read through `Model.entryMigratedOf` and set through
`Model.withEntryMigrated` in the same write as the adoption, taught to all
three whitelists on the day it was added (`normalize_entry_migrated` in the
helper) and held to R20a's key check. An older build drops it, which is why a
downgrade and a re-upgrade migrate again; `ARCHITECTURE-SOURCES.md` 2.1 and
the round-11 rulings are the detail.

How the file is READ, amended 2026-10-13 (D-SINK-19 round 12, R22a;
lane-key-n1): a load is classified before anything is applied, and a state
that did not load is never written. What Quickshell's `FileView` reports was
measured first (quickshell 0.3.1-1, Qt 6.11.2, one FileView per case under a
nested headless cage, lane A, 2026-10-13): `loadFailed` with FileNotFound
(2) for a missing file, a missing parent or a dangling symlink -- AND for a
file inside a directory of mode 0000 or 0600; PermissionDenied (3) for a
0000 or 0200 file; NotAFile (4) for a directory or a FIFO at the path;
`loaded` for an empty file and for garbage. So FileNotFound does not mean
"no file", and the one party that can tell a fresh install from an
unreadable directory is the helper's start-up `state init`, which now
reports what it found before it repaired any mode (`found`: `absent`,
`file`, `other`, `unreadable`). `Model.stateLoadKind` names the load
(`loaded`, `unparsed`, `absent`, `permission`, `not-a-file`, `io-error`);
only `loaded` is applied; FileNotFound is a fresh install -- an empty
state the migration may run on -- only when the init found `absent`; any
other outcome at a start is re-read once after the init (which restores a
0000 file to 0600 and a 0000 directory to 0700) and then puts the service in
the no-write mode for the session: every state write and every owned
bar-entry write is refused, the migration does not run, and the user is
told once (`Model.stateUnreadableNotice`, a notification naming the file
and what to do, never a URL). A load that IS a state lifts it. Mid-session,
a reload that is not a state blocks at once and memory stands. The helper's
`state` verbs other than `init` refuse such a file the same way
(`state_unreadable`, exit 1, nothing written), where they used to write the
empty default over it. `ARCHITECTURE-SOURCES.md`'s round-12 rulings carry
the table, the decision and every writer.

Amended 2026-10-13 (D-SINK-19 round 13, R23; lane-key-p1, lane A). Five
things changed about loading and one was measured:
- The helper never blocks on the state path and never reads anything but a
  regular file there (R23b): every read goes through one opener,
  `open_regular` (`O_NONBLOCK`, then `fstat` S_ISREG on the descriptor), so a
  FIFO or a socket at `state.json` is `found: other` at once instead of an
  init that hung in `open()` for ever (on 0.13.6 too), and every other `state`
  verb refuses it with `state.json is not a regular file; nothing was
  written`, exit 1. Its mode repair touches only a regular file, and the
  directory repair only a directory (R23d), so a directory at the path is no
  longer made 0600.
- The service never waits on the init for ever (R23c): `stateInitWatchdog`
  TERMs it after `stateInitTimeoutMs` (15 s) and `stateInitKill` KILLs it 2 s
  later, and a load waiting on it blocks with its own reason, `init-timeout`.
  The bound is 8.5 times the slowest of 80 timed runs of the real init on
  this 4-core machine (idle 214-215 ms; 3x oversubscribed, load 7.7, max
  1,769 ms; 2026-10-13, lane A).
- The notice is re-armed by every lift, so a second episode in one session
  is told again; that was always the code and is now pinned (R23a).
- In the no-write mode an unconfigured guide draws the notice's own words
  instead of the first-run form (R23e), and every refusal there says the
  no-write reason (R23f). `UX-SOURCES.md` 5.10.
- What the FileView does to its WATCH (R23g), measured by lane A in a nested
  headless cage on a private D-Bus with one FileView declared as `stateFile`
  is (`scripts/dev-harness/spikes/filewatch/measure.sh`, its result kept
  beside it as `RESULT-2026-10-13.txt`; 16 sequences, each on a fresh shell
  over a fresh file, at load 1.31):

  | After | `fileChanged` | load delivered | later in-place write seen |
  |---|---|---|---|
  | an external in-place write (truncate, empty, garbage, good content) | yes | yes, every time | yes |
  | the helper's atomic rename (`state favorite add`) | yes | yes | yes |
  | a chmod | yes | yes | yes |
  | the view's own `setText` save, alone, at idle | yes, with `saved` | no (0 of 16; 0 in a burst of 2-3) | yes |
  | an own save with an external write queued behind it | yes | yes, with the later text | yes |
  | a restart | -- | the first load | yes |

  The real `Service.qml` driven the same way (lane A's `svcwatch.sh`, session
  scratch, not committed) agreed idle and under six busy loops on four cores,
  except that under load the own save DID deliver a load carrying its own
  text (counted `own-write`): the own echo is timing-dependent, so the node
  harness now models it both ways (`ownEcho`, and `scripts/check.sh` runs the
  node suite twice). [Corrected 2026-10-14, D-DOC-8: this paragraph used to
say the result contradicted three earlier measurements -- the round-9
data-loss lens (a helper rename raised no reload, D-SRC-19), the round-12
live lens (the same, its `rename.out`) and the round-12 data-loss lens (an
in-place damage after the session's first own save raised no reload) -- and
that the no-write mode beginning mid-session after an own save was
UNVERIFIED until decided.] The round-13 live lens found what differed: the
state DIRECTORY at `stateFile`'s first load. Every one of lane A's rigs
started with it present, and there every external change reloads, own saves
or not; the earlier rigs started with it absent -- the production
fresh-install shape, `~/.local/state` present and `omarchy-iptv/` under it
absent -- and there the view raised nothing for the whole session, the own
echo included (live on lane-key-p2 and on a 0.13.6 export, alternating the
two shapes). The lead ruled on that measurement on 2026-10-14 and round 14
fixed it (next amendment).

Amended 2026-10-14 (D-SINK-19 round 14, R24; lane-key-q1, lane A). The
watch, the merge, the symlink and the bound:
- The first session after a fresh install sees external changes (R24c).
  Measured in the committed spike (`scripts/dev-harness/spikes/filewatch/
  measure.sh <helper> r24`, `RESULT-2026-10-14-r24.txt`, nested headless
  cage on a private D-Bus, two runs at load 1.2-1.7): with the directory
  absent at the first load, nothing after the start-up `mkdir -p` and `state
  init` raised a signal -- the init's creation, a helper rename, an in-place
  write, in-place garbage (sequence Q); ONE explicit `reload()` after them
  re-armed the view and every later change was seen (R, and after an own
  save, T and R2); with the directory present and no file, the init's
  creation was seen without help (U). So `decideStateLoad`'s `fresh` branch
  calls `stateFile.reload()`, and the reload it causes is the identity:
  `Model.sameState` of the init's empty default and `parseState("")` is
  true. The node harness models the unarmed view (rule 10). Observed live by
  key-scenario B16 (`seen:1 file:C,D blocked:unparsed told:1`; on dev
  `seen:0 file:D blocked: told:0`).
- A foreign write is merged, never ignored and never applied blind (R24a,
  D-SRC-22). The service keeps a BASE, `landedState`: the text it loaded, its
  last save that LANDED, or the last foreign text it merged. A reload whose
  text is the base (`Model.sameState`) or one of the service's own writes is
  ignored while a save is parked, in flight or failed, as R9 had it [round
  15, R25a: "own" now means still in flight -- next amendment]; any
  other text in that window is FOREIGN -- a hand-run helper `state` verb, a
  restore -- and `Model.mergeForeignState(base, ours, theirs)` three-way
  merges it: sets for favourites, hidden groups and saved searches, records
  by key for sources, whole values for recents, `activeKey`, `lastPlayed`,
  `session` and `cacheLayout`, `entryMigrated` kept if either side has it,
  and a CONFLICT (both sides changed one record, or one value, differently)
  goes to the foreign write, logged one line per conflict by key and field
  name (`Model.mergeConflictLine`, never a URL or a value). The result is
  memory, the foreign text becomes the base, and a save is asked for when
  the result is not what is on disk. With nothing held a foreign reload is
  applied whole, as before. `ARCHITECTURE-SOURCES.md`'s round-14 rulings
  carry the field table and the fixture. [Round 15, R25b: the caps were
  applied by `parseState` after the merge and cut the in-app additions
  silently; next amendment.]
- One answer per state path (R24b, D-SRC-23, D-SRC-26). A symlink at
  `state.json` is followed when it leads to a regular file -- for reads, and
  for writes, which land THROUGH it: a 0600 temporary file beside the target,
  renamed onto it, so the link survives -- and refused with exit 1 and
  nothing written when it dangles or leads to anything else. Measured first:
  the FileView's own save over a valid link writes through it and keeps it
  (spike sequence V), and dev's helper replaced the link with a regular file
  and the running view then saw none of its later writes (V, W). `state
  init` answers `link` for a link it will not follow and `not-a-dir` for a
  file where the state directory should be (no traceback), and each has its
  own notice sentence instead of the folder-permission one. [Round 15: "the
  link survives" is true of the plugin's and the helper's writes. A tool of
  the user's that REPLACES the link, or puts a file over it, is not seen by
  the running view, which then sees nothing more that session (R25e,
  D-SRC-29; next amendment).]
- One bound over the whole start-up check (R24d, D-SRC-24, D-SRC-25): the
  15 s watchdog arms when `mkdir` starts and TERMs, then KILLs, whichever of
  `mkdir` and `state init` is running; and `state init` arms `SIGALRM` for 30
  s (`STATE_INIT_DEADLINE`, default action) before it names the path, so a
  shell that stops first leaves nothing running past that (measured: a held
  init ended by `Alarm clock`, rc 142, after 30.2 s; key-scenario B18). The
  KILL half is observed now (B17, and seen red without it, R24g). Neither
  reaches a process in uninterruptible sleep on a hung filesystem.
- In the no-write mode the playlist fetch is handed no `--state-dir`
  (`Model.fetchStateDir`, R24e, D-SRC-27), so the D-ID-1 remap cannot write
  the file the session refuses to write; and the Sources screen draws the
  notice's title and no Add rows (R24f, D-SRC-28; `UX-SOURCES.md` 5.10)
  [round 15, D-SRC-38: `Saving has stopped` instead of the title in a block
  that began mid-session].

Amended 2026-10-14 (D-SINK-19 round 15, R25; lane-key-k1, lane A). The echo,
the caps, the state folder and the link's limit:
- An echo is only a text still in flight (R25a, D-SRC-30). `recentSaves` was
  the last eight texts the service wrote, so a backup the user had copied
  from the plugin's own file, put back after a later in-app change landed,
  was ignored as an echo and the next save wrote over it (the round-14
  data-loss lens). It is now the burst asked for since the last save that
  LANDED, cleared as one lands; an older own text coming back is another
  writer's, applied or merged under R24a. What it rests on is measured
  (spike set `r25`, `RESULT-2026-10-14-r25.txt`): 85 echoes over 100
  bursts, each carrying the text of the latest `saved`, none a superseded
  one. The landed save's own echo now arrives with nothing held and is
  ignored as `unchanged` (`Model.reloadDisposition`'s new input
  `memoryMatchesBase`). Observed live by key-scenario B20.
- A merge never drops silently (R25b, D-SRC-31). `Model.mergeForeignState`
  applies the caps itself -- theirs first, so what goes past 50 sources, 20
  saved searches or 200 hidden groups is always the in-app additions --
  and returns what it dropped; the service logs one line per element
  (`Model.mergeDropLines`, a source by its key) and tells the user once per
  merge (`Model.mergeDropNotice`, notification 74018, counts and limits
  only). An in-app add whose probe is still running when a foreign write
  takes the 50th place is outside the merge and is still dropped silently at
  the next start (a new finding, raised to the lead).
- The state folder gets the file's rule (R25c, D-SRC-32). A symlink at the
  state folder, or above it, that dangles or leads to something that is not
  a folder is refused by every `state` verb (exit 1, a sentence) and named by
  `state init` (`found: folder-link`), which the model maps to its own
  notice; `ensure_private_dir` refuses the same shapes for every caller --
  the cache folders, the runtime socket folder, the logo folder -- as
  `folder_unusable`, never a traceback. A folder link that leads to a folder
  is followed and the folder it leads to is made 0700 (measured, spike
  `folder-link`; security standard 5).
- The link's limit is stated, not fixed (R25e, D-SRC-29). Measured by the
  round-14 lenses: a writer that replaces whatever is at the state path --
  the link, or a file over it (`mv`, `sed -i`, `rm` + `cp`, `ln -sfn`) --
  leaves the view watching nothing for the rest of the session, and the next
  save writes memory over the change; a write through the link, in place or
  by a rename onto the target's own path, is seen; a target that went
  missing is not seen coming back (D-SRC-35). One explicit `reload()`
  re-arms the view; that lever is filed for a later release. The README
  says what is noticed and what to do (edit the target in place, or restart
  the shell straight after such a tool). The contract's seventh FileView
  fact has the table. [Round 16, R26a: fixed -- the lever is pulled before
  every save; next amendment.]
- The merge is observed live (R25d, F-HARNESS-26): key-scenario B19 (a held
  failed save, two hand edits in place and a helper write inside it, both
  in-app changes and the helper's favourite kept through a restart), and
  B21, the existing-folder session damaged after an own save.

Amended 2026-10-16 (D-SINK-19 round 16, R26; lane-clean-a1, lane A). Read
before write:
- Every save reads first (R26a; closes D-SRC-29, D-SRC-40, D-SINK-21 and
  its file-link twin; D-SRC-35 on the second call). The FileView's watch is
  lost WITHOUT a signal when the path is replaced or re-pointed (the
  contract's eighth fact), so the session's next save was the first it
  learned of it, and it wrote memory over the change, over the other state
  the link now named, or CREATED `state.json` in an empty re-pointed folder
  at 0666 & ~umask, 0644 here, holding every source URL (D-SINK-21,
  measured by the sink lane on 1c88877 and on 0.13.6). Now a save the gate
  allows reloads `state.json` and waits for that load, which is decided by
  the dispositions every load already has: the base -> written; a foreign
  text -> merged (R24a), then written; not a state -> the R22 no-write mode,
  nothing written, told once. `Model.stateSavePlan` decides each call --
  join a read already out, park, refuse, verify, defer, write -- and
  `Service.saveState` carries it out. The read is skipped while one of the
  service's own writes is in flight (the view drops a reload then, measured
  30 of 30, and the disk is that write); a load met during the read is
  counted as `pre-save-<reason>`, so key-scenario's D3 and W3, which need a
  genuine `save-parked` reload, are not satisfied by the read; and
  `stateVerifyWatchdog` bounds it -- no load in 2 s, the save goes without
  it, counted (`stateVerifyNoLoad`) and logged once. A refused save re-reads
  too, unless the reason is `init-timeout`, and a source verb meeting the
  mode asks for one reload (`Model.stateBlockRecheck`): that verb is refused
  and, if the file is back, the next call lands (R26e: a verb answers when
  its write is ISSUED; one the read then refuses is told by the R22
  notification, and the next call answers `state_unreadable`). Cost: one
  asynchronous reload per save, 6-11 ms at most on the real service over a
  state of about 3 KB, and the GUI thread never blocks on file I/O (the
  R23c / R24d stance; the blocking peek and the synchronous variant were
  measured and not taken). Observed live by key-scenario B23-B29.
- No write from inside a handler (R26b, D-SRC-46). A `setText` issued
  inside `stateFile`'s own `onLoaded` writes the file and raises no `saved`
  (measured 16 of 16), so after an R24a merge saved from inside its load
  the session read a write in flight and a failed save for good (0.14.0
  and 0.14.1).
  Every write is now issued from a turn of its own (`Qt.callLater`):
  `finishStateVerify` is entered only from `Qt.callLater` and the
  watchdog's Timer, `saveDeferredState` only from `Qt.callLater`, and a call
  from inside any of `stateFile`'s handlers is deferred (`stateInHandler`
  counts the depth). `stateFile.setText` is the one FileView write in the
  shipped files; it is reached from five handlers of three views
  (`channelsFile`'s two, `playlistStatusFile`'s `onLoaded`, `stateFile`'s
  own), every one through the plan's "write". Observed live by B30.
- The double is the measured FileView (R26c, F-HARNESS-29): a `setText`
  inside a load is silent, a created file is 0666 & ~umask, an existing
  file keeps its mode, a replacement or a re-point raises nothing; and
  (F-HARNESS-31, lane-clean-f1) the reload a foreign change raises while
  one of our writes is in flight delivers nothing, so that change is lost
  to our rename, as on the real view (30 of 30).
- No periodic reload (R26d). A replacement with no save after it is
  unseen until the next save or a restart (FRESH); nothing writes
  meanwhile, so nothing is lost. A timer would leave a window of one
  period in which a save still writes over the change or creates the
  0644 file, and reads the file for ever (lane W: at 10 s, 360 reloads an
  hour idle). B31 observes 0 loads in 30 s idle.
- What remains, stated: three windows in which a save is still written
  without a read that would have stopped it, so a replacement in the
  window is written over and a path that has just lost its file (a link
  re-pointed at a missing file, a folder link at an empty folder) gets the
  file created at 0666 & ~umask, holding the URLs -- a save asked while
  our previous write is in flight (its read skipped; the re-point landing
  between the two renames); a re-point landing between the read's load
  and the write it allows (the asynchronous write is issued from the next
  turn); and the watchdog's save, which goes without its read, so a
  replacement in that 2 s goes unseen as before R26 (a missing file
  answers the read with `loadFailed` before the watchdog fires, so this
  one needs a load that never comes). All three are reproduced through
  the node double over the shipping `Service.qml` on lane-clean-f1 (both
  hosts, both echo modes, `created:true mode:644 holdsUrl:true`; a control
  re-point with no window `created:false blocked:[absent]`) and by the
  round-16 data-loss lens's simulator (identically on 0.14.0); none is
  driven live. The watchdog's 2 s itself is pinned since lane-clean-f1
  (node "the read's bound is 2 s", red on `interval: 20` and with the line
  deleted). A change another program lands in the same instant as one of
  our writes is lost (F-HARNESS-31: the view drops the reload it raises).
  A 0644 file the user put at the path is written into at its own mode
  until the next start's `state init` makes it 0600. And D-SRC-47: R25a's
  own-write record keeps eight texts, so a burst of more than eight writes
  a turn apart while the first is in flight can push the first out and
  read its echo as foreign (lane A, found while re-levelling R13; the id
  given on lane-clean-f1).
- [Amended 2026-10-20 (D-SINK-19 round 17, R27a; lane-sweep-a1). Two of the
  three windows are closed and the third is the one that remains: NO WRITE
  WITHOUT A READ. [Round 19, R29a: no longer -- window (a)'s closure
  stands, window (c) is open again as on 0.14.2, so two remain; the
  round-19 amendment below.] A save asked while our previous write is in flight now
  WAITS (`Model.stateSavePlan` answers `wait`) until that write's `saved` or
  `saveFailed`, then reads and writes from a turn of its own; the wait has
  its own 2 s bound (`stateWriteWaitWatchdog`), which releases the save to
  its read, never to a write. The read's 2 s watchdog no longer saves: it
  asks for the load once more, and a second silence puts the session in the
  R22 no-write mode with reason `read-timeout`, told once (`Saving has
  stopped`, `... did not answer when it was read before a save (twice, 2
  seconds each)`), lifted by a later read that answers [round 18, R28a: no
  longer -- the lift lost the held change; a silent read now keeps it held
  and reads again, the amendment below] [round 19, R29a: and that is
  withdrawn too -- a silent read's save goes ahead without it after 2 s,
  the last amendment below]. What remains is
  window (b), a re-point landing between the read's load and the write it
  allows, a turn apart: milliseconds, stated in `Model.stateSavePlan`'s
  comment and the README. Pinned through the node double over the shipping
  `Service.qml` on both hosts and both echo modes (`R27a (<tag>): ...`, six
  pins, among them window (a) with the folder link re-pointed at an empty
  folder as the first write lands -- no file created, `absent`, told once --
  and window (c) over an empty folder -- no file created, `read-timeout`
  [R28a: `absent` once the read answers] [R29a: the window-(c) pins went
  with R28a's; the four R27a pins on the tree are window (a)'s, D-SRC-47's
  mechanism, window (a) over an empty folder, and the write wait's bound,
  `R27a / R29a (<tag>): ...`]);
  live by key-scenario B33. A consequence, pinned: no write is issued while
  another is out, so R25a's record never holds more than one text and
  D-SRC-47's overflow can no longer happen [round 19, R29a: only while our
  writes are reported within 4 s -- a write the view never reports
  releases the held save to its read at 2 s, the view drops that read
  while the write is out, and at R26a's bound the save is written without
  it, 4 s after it was asked, while the first may still be out (pinned:
  `R27a / R29a (<tag>): the write wait is BOUNDED at 2 s ...`); so a long
  run of unreported writes could still reach D-SRC-47]. The same-instant loss (D-SRC-48)
  stands: R27b measured the one mitigation proposed for it and it
  recovered nothing a later read does not (0 of 608 trials,
  `spikes/filewatch/RESULT-2026-10-20-r27b.txt`).]
- [Amended 2026-10-20 (D-SINK-19 round 18, R28a; lane-sweep-a2; WITHDRAWN
  the same day by round 19, R29a, the next amendment -- this one is
  history). Window
  (c)'s answer above is withdrawn: a read that is silent twice no longer
  puts the session in the no-write mode. That mode set the held save aside,
  so the load that lifted it -- our own write's echo reported late, a
  source verb's re-read, another program's write, the stalled read
  answering -- was applied over memory and the change was lost, an in-app
  source add included (both round-1 reviews, through the shipping
  `Service.qml`). Now a silent read keeps the save PARKED with memory as the
  authority, every save asked meanwhile joins it, and the file is read
  again with the bound R28a's schedule gave: at 2, 4, 8, 16, 32
  and 62 s after the save asked, then every 30 s, and at once when a change
  joins or one of our writes is reported. Still no write without a read:
  whatever load answers is decided by R26a's dispositions (the base ->
  write; another program's text -> the merge, then write; a load that is
  not a state -> the R22 mode with that load's own reason). After 8 s of
  silence the user is told once (`Saving is waiting`, 74019); a shell
  stopped while the change is held loses it, and the notice says so.
  `read-timeout` is gone. Pinned through the node double on both hosts and
  both echo modes, one pin per way the wait ends, each red on
  lane-sweep-c1; no live segment (nothing in the cage stalls a read).
  Window (b) is unchanged.]
- [Amended 2026-10-20 (D-SINK-19 round 19, R29a, the lead's ruling;
  lane-sweep-a3). BACK TO R26a'S BOUND FOR A SILENT READ: R27a's window-(c)
  answer and all of R28a's are withdrawn. A save whose read has no load
  within 2 s (`stateVerifyWatchdog`, `interval: 2000`) is written without
  it, counted (`stateVerifyNoLoad`) and logged (`state.json was not read
  back within <ms> ms of a save; saving without the read`), word for word
  6f1d176's R26a body; there is no schedule, no re-read, no notice, and id
  74019 is retired, not reused. Why (the ruling): it only matters when the
  filesystem does not answer a read for two seconds, and each attempt to
  hold the change across that stall made a new silent loss -- round 1, the
  lifted block dropped it; round 2, the late answer to a read stalled on a
  slow FUSE file was the OLD text, so the save then wrote over another
  program's write made during the stall (4 of 4 live runs; 6f1d176 kept it
  in the same shapes, 2 of 2), and a stalled read that answered with a load
  failure turned the held change into an R22 change. So window (c) STAYS,
  documented, as it is on 0.14.2: a replacement made while the read is
  stalled is written over, and a path that has just lost its file can get
  one created at 0666 & ~umask (the "What remains" bullet above). Window
  (a)'s answer is KEPT with the ruling's proviso: the wait for our own
  write has its 2 s bound and the read it releases to has R26a's, so a save
  is never held past 4 s and never blocked (pinned: `R27a / R29a (<tag>):
  the write wait is BOUNDED at 2 s ...`). Window (b) is unchanged. So two
  windows remain, (b) and (c). Measured live on lane-sweep-a3 with round
  2's slow-file rig rebuilt over the tree (transcript
  `key-20261020-184229-2540898`): writes at +2.0 s and +4.0 s without their
  reads, nothing blocked, nothing told; a helper `state source add` during
  the stall kept, an atomic replace adding a favourite lost -- as on
  6f1d176. Pinned in node through the shipping `Service.qml` on both hosts
  and both echo modes (`R26a / R29a (<tag>): the read is BOUNDED ...` and
  `... the read's bound is 2 s ...`), red on lane-sweep-c2 (`noLoad:2`, the
  save still parked). The rulings are at the end of
  `ARCHITECTURE-SOURCES.md` (round 19).]

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

| Key | Type | Default | Validation (service side, the model) |
|---|---|---|---|
| `playlistUrl` | string | `""` | trimmed; the helper accepts `http(s)://`, `file://` or an absolute path and refuses everything else. **Amended 2026-10-11 (D-SINK-19): an INPUT, not a stored setting.** A value here that this service has not consumed -- the first reconcile of a service, or a value different from the one it last saw -- is validated and adopted through `Model.reconcileSources` exactly as a CLI value always was (SR8; SR37 in `ARCHITECTURE-SOURCES.md` as amended), the adopted record becomes the active one, and the plugin then rewrites the entry WITHOUT this key (`Model.RETIRED_SETTINGS`, dropped by `Model.entryWith`), so reading the entry back does not show it. A refused value is reported (D16, narrowed by `Model.invalidInputBlocks` to the case with no active source to show instead) and stripped too. An empty value is a no-op: it is the steady state after the plugin's own strip, not a command. The plugin itself never writes a URL here any more **Overturned 2026-10-13 (D-SINK-19 round 11, R21; the owner's decision): NOT a setting and NOT an input any more, except once.** The value here is read only by the migration of a 0.13.x install, while the LANDED state lacks `entryMigrated` (R21a); once that marker has landed, a value found here is REFUSED -- never adopted, whatever it is -- reported once (`Model.entryInputNotice`, a notification and the console, never the value) and stripped by the next owned write (R21b). It stays declared in `manifest.json` (that file is outside the documents lane; raised to the lead). Everything above is the record of rounds 1-10. |
| `epgUrl` | string | `""` | same rules. Input-only on the same terms: a fresh non-empty value is attached to the ACTIVE record on any reconcile that sees it (an `ignore` plan included) and stripped from the entry by the same owned write; an empty value is a no-op, and the CLI clear lever is withdrawn -- the Sources screen or `state source update` clears a guide URL (D-SINK-19 round 2, R4). "Empty disables EPG" is now a statement about the RECORD's `epgUrl`, not about this key. **Round 3 (R12, 2026-10-12): never stripped unadopted.** A value set while NO source is active stays on this key (the guide reads it as its fallback) until a source exists and the reconcile that brings it attaches the value to that source; only then is it taken off the entry. Round 2 stripped it in the same write with no copy anywhere. **Round 7 (R17, 2026-10-12): "until a source becomes active", by any route, and enforced at the sink.** Every owned write leaves this key on the entry unless the ACTIVE record holds the value or the service already consumed it (`Model.retiredInputsToKeep`, handed to `Model.entryWith` by the one funnel); a switch or an in-app add that makes a record active lands a pending value on it in the same turn (`adoptPendingEpg`), replacing a guide URL the record had. Until round 7 the logo toggle's heal, and on the echoing host the key mirror's heal after a switch, stripped it with no copy anywhere (the sixth review's P1). **Round 8 (R18, 2026-10-12): compared the way adoption compares, and an add form's own guide URL wins.** The value is read through `Model.entryInputForm` everywhere it is compared, so surrounding whitespace (which `omarchy bar set` stores as typed) does not make it a different value, and a value of whitespace or control characters alone is no input -- it never empties a record's guide URL. A pending value meets an in-app add whose form carries a guide URL of its own (typed, or an Xtream add's `xmltv.php`): the form's wins, and the pending value is superseded and stripped by that commit (R18d). **Round 9 (R19, 2026-10-12): held in the state, and the input set last wins.** A value set while NO source is active no longer waits on this key: it is held in `state.json` as `pendingEpg { url, seenAt }` and taken off the entry by the same R13-gated owned write that strips every consumed input (R19b, overturning R12's on-entry pending state; a refused one is reported and stripped). R18d's form-wins rule is overturned too (R19c): every record carries `epgSetAt`, set by the add form at SUBMIT, by the edit form when it changes the guide URL, or by adoption with the input's `seenAt`, and at the move that makes a record active the held value lands iff it was seen LATER than the record's own was set (`epgByTime`, `applyPendingEpg`); either way it is cleared. Records written before R19 read as 0 **Overturned 2026-10-13 (round 11, R21), on the same terms as `playlistUrl`.** At the migration a value is attached to the source that becomes active, or, with no source to attach it to, reported (`no-source`) and stripped, never held (R21c); after the marker it is refused, reported once and stripped. **Round 19 (R29d, 2026-10-20): not when it came with an unusable playlist.** A value set beside a `playlistUrl` that does not validate is attached to no source -- until R29d it replaced the active record's own guide URL -- and is reported WITH the playlist in one notice (`Bar setting removed`, reason `invalid-pair`) and stripped with it (`Model.adoptActiveSource`'s `epgWithInvalid`; `ARCHITECTURE-SOURCES.md`, round 19). A record's guide URL is set and cleared only in the Sources forms (or the helper's `state source` verbs). R12, R17b, R18d, R19b, R19c and R20b, recorded above, are overturned. |
| `sourceKey` | string | `""` | D-SINK-19. Written by the plugin, never derived from user input: `Model.activeKeyText` of the active source's key, 8 lowercase hex with D4's suffix rule, mirrored into the entry by every owned write (`Model.OWNED_SETTINGS` is `["sourceKey", "showLogos"]`). NOT the authority -- `state.json`'s `activeKey` is -- and consulted only when the state names no record (`Model.adoptActiveSource` step 3); a value naming none of the user's records reads as absent. Deliberately NOT declared in `manifest.json` (`barWidget.defaults` and `schema` do not name it): declaring it would offer the mirror as a user setting with help text. The host keeps an undeclared key through its own rewrite -- MEASURED on 2026-10-11 (the host's `updateEntryInline` run in node over its own source, `OMARCHY-PLUGIN-CONTRACT.md`) -- and `omarchy bar set` writes any key without a schema check -- READ, not run: `setBarWidget` at `services/PluginRegistry.qml:342-380` ends `entry[String(key)] = value` with no schema lookup (the contract's "read rather than run" list). The recovery path rests on both; a round-2 sentence here called both measured and the contract entry it cited said otherwise for the second. Not a credential: SR36 states what it is (a 32-bit confirmation of a guessed URL) |
| `refreshMinutes` | integer | 60 | `clampInt(5..1440)` |
| `mpvArgs` | string | `""` | whitespace-split; each token must match `^--[a-z0-9][a-z0-9-]*(=.*)?$`; reserved names (`--input-ipc-server`, `--wayland-app-id`, `--title`, `--force-media-title`, `--idle`, `--script(s)`, `--config-dir`, `--load-scripts`, `--tls-verify`, `--stream-lavf-o`, and their `--no-` forms) are dropped with a console warning. This list is the M1 set plus the three later entries worth naming here; `MPV_RESERVED` in the model and its python mirror are the current list and `ARCHITECTURE-PLAYER.md` 4.12 is the register of why each name is on it. The two TLS entries are opposites and 4.15 is where that is specified: `--tls-verify` is the one entry the reserved list does not make safe by itself (D-SINK-13), and `--stream-lavf-o` is the one the reserved list is the only way to close (D-SINK-15). A single string was chosen over a JSON array because `omarchy bar set` writes strings by default and users copy examples from the README. |
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

Amended 2026-10-11 (D-SINK-19). **`shell.json` comes off that list as a place
the plugin PUTS a credential, and stays on it as a place one passes through.**
The plugin no longer writes a URL into the bar entry at all: the entry carries
the active source's key (`sourceKey`, the settings table above), and
`Model.entryWith` drops `playlistUrl` and `epgUrl` from every write it makes.
So the paragraph above reduces, for the plugin's own writes, to `state.json`
(which now also names the active source), the fetch environment for the life of
a fetch, and the stream URLs inside each `channels.json` -- every one a file or
a process the plugin creates itself, 0600 inside 0700, or an environment the
fetch verbs make non-dumpable. Two things keep the sentence from being
absolute, and both are bounded rather than denied: a URL the USER sets with
`omarchy bar set` is written there by the host before the plugin can do
anything about it, and is removed on adoption [round 11, R21b: removed
UNADOPTED once the migration has landed -- the window is the same, the value
is refused rather than adopted] rather than never arriving (the
window is from the host's write to the plugin's next owned write: one
reconcile and one `Qt.callLater` while the shell runs, the whole downtime plus
the first start's reconcile when it was not); and an install upgrading into
this release has one in the file until the migration's first owned write
lands. The mode shield (D-SINK-18) is what covers both windows and it stays for
that reason -- SR40 in `ARCHITECTURE-SOURCES.md` records the reasoning,
including why the gate in front of a persist now asks about the entry being
written (`Model.entryShieldDecision`) and answers `persist` on every shipping
path. "The URL is no longer stored" would be the wrong sentence and is not the
one above: the credential IS stored, in the plugin's own 0600 file, which is
the whole point of the change. The README counts the files the same way: two
the plugin owns, one it does not own that a URL only passes through.

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
interpreter starting and compiling what precedes the shield: with the whole
helper in one file, 98-113 ms idle at sub-millisecond resolution (median 105
ms over twelve runs, 2026-10-01) and 264-634 ms under a doubled CPU load (the
final review's measurement; `scripts/dev-harness/argv-scenario.sh` reads it
at 50 ms sampling and bounds it against an in-run control rather than an
absolute number); since D-REL-7 the helper is a stub that shields before
compiling its parts, and the window is 22.9-40.1 ms (medians 27.0 and 27.1)
against 136.8-164.0 ms (medians 148.4 and 148.2) for 0.14.2's one-file
helper, 12 interleaved runs each, twice, under a load average of 3.1-3.7
(2026-10-17).
Readable by same-uid processes only -- and the
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
- The decision in front of a persist is a pure function in the model,
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
  cannot grade. Read them off the model (`Model.mjs` and its parts).
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
  `dev`: `persistActive` and the logo toggle. `Model.ownedEntryPatch` names every
  owned key, `playlistUrl` and `epgUrl` included (D-LOGO-2, and the reason it
  does), so the logo toggle writes the provider URLs into the host config too.
  Found by this sweep and not by the report. It is deliberately NOT gated: the
  values it writes come from `root.settings`, which is what the host already
  stores, so it puts nothing in the file that is not in it already, and
  refusing a logo toggle would cost a feature for no privacy gained. It does
  get the re-arm. **Amended 2026-10-12 (D-SINK-19 round 5, R16):** still
  not gated by the shield, and now gated on what it CARRIES. D-SINK-19 made
  "any owned write heals the entry" strip the retired URL keys on this
  write too, and R13 made a failed state write leave the URL on the entry
  as the only copy of the input -- so one logo toggle after a failed write
  mirrored the in-memory key and took that copy off, and the next start
  found the record nowhere (the round-4 review's P1, measured live under
  cage on lane-key-t2 and at the Model layer on every D-SINK-19 tree; rule
  15's shape inside R13's own fix, since `writeOwnedEntry` has two callers
  and R13 gated one). While a state write is parked, in flight or failed
  the toggle now writes `showLogos` alone and leaves `sourceKey` and the
  URL keys as the host publishes them (`Model.ownedWriteMode`,
  `Model.entryWith` with `keepRetired`) -- and, since round 6 (2026-10-12),
  before the first state load too, `stateLoaded` being the decision's
  fourth input; with the state loaded and nothing outstanding it heals as
  before [round 7, R17a: and a heal takes off only a CONSUMED retired key,
  so an `epgUrl` R12 left on the entry while no source is active survives
  it; round 8, R18a: "consumed" is decided on the value as adoption reads
  it, so a whitespace-wrapped value is consumed when its trimmed self is,
  and R18b: a heal that would change nothing the host stores is not made
  at all] [round 9, R19a: that skip is OVERTURNED -- every heal is handed
  to the host, whose answer is the dirty check; and R19b: an `epgUrl` set
  while no source is active is held in `state.json`, so it is consumed and
  the heal strips it]. "It can only ever take a credential out" is true of the heal
  branch only. "It puts nothing in the file that is not in it already" is
  true of the heal branch, and of the patch branch only as "nothing the
  host did not publish": on the host that publishes one write behind, a
  patch right after a heal puts back, for one write, a URL the heal had
  just stripped (D-SINK-20, below; `ARCHITECTURE-SOURCES.md` 4.3) [round
  10, R20c: no longer -- the patch keeps a retired key only when it is a
  valid input the plugin's last LANDED state does not hold, and strips a
  value that state holds and a refused value already reported, so it puts
  back nothing the plugin's own file already has or refused]. [round 11, 2026-10-13, R21a/R21b: the question is no longer about values.
  Before the migration marker has landed the patch keeps every retired key
  the entry carries -- the migration's input is the only copy while its
  write is outstanding -- and once it has landed every owned write, this one
  included, keeps none, so it can put nothing back; `Model.retiredInputsToKeep`].
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

Raised 2026-10-09 (D-SINK-19), built 2026-10-11 in two rounds, and written
here in the round that built it -- the state of the change is the board row in
`docs/STATUS.md`, not this paragraph. **The first finding in this run that came
from inside the project, and it came from the one place rule 15 says to
look.** It is the sibling sweep at the end of the entry above, whose closing
sentence is "the root cause is not the mode at all", given an id, a round and
a release of its own instead of being left as a remark at the bottom of
somebody else's fix.

**What the exposure was.** Not a new leak: the same credential in the same
file, named by its cause rather than by its symptom. The active source was
identified by its URL, so the URL had to be on the bar entry for the plugin to
know which source was playing: at 65ec1b8, the last tree before the change,
`Service.qml:199-201` said so in terms, `Service.qml:247` derived the active
key by matching that URL against the records in `state.json`, and `state.json`
had no `activeKey` of its own. The host persists that entry into
`~/.config/omarchy/shell.json`, whose packaged default is 0644 and whose
writer preserves whatever mode it finds. Every source reached it, not only
Xtream: a `https://user:pass@host/list.m3u`, a provider URL carrying the
credential as a path token, and a `get.php?username=U&password=P` alike.

**What D-SINK-18 contained.** The mode shield in the entry above: a real
narrowing that shipped in 0.13.3, and a narrowing of WHO CAN READ the file
rather than of what is in it.

**Why containment was not the end of it.** Three reasons, none of them a
criticism of the shield. A mode is a property of the file rather than of the
plugin: anything may reset it and nothing tells a plugin that happened, which
is residual 2 of the entry above. The shield defends a container the plugin
does not own, so its correctness depends on facts about somebody else's
software that were measured once, on one machine, on one day. And the question
the shield answers -- "is this box private?" -- is downstream of the question
that should never have had this answer: "why is the secret in that box at
all?" A containment whose premise is that the credential belongs there is
re-raised every time the premise is re-examined, and it was, four times in
four days.

**What changed, as the code on this tree does it.** The active source is
named by its KEY. `state.json` gains `activeKey`, additive at
`Model.STATE_VERSION` 2 on the `hiddenGroups` precedent with no version bump,
taught to all three whitelists and read through `Model.activeKeyOf`, which
refuses a key naming no record (section 5 above). `configured` is "there is an
active source" rather than "the entry holds a URL" (`Service.qml:170`). The
bar entry carries `sourceKey`, a mirror of that key, and NO URL:
`Model.OWNED_SETTINGS` is `["sourceKey", "showLogos"]`,
`Model.RETIRED_SETTINGS` is `["playlistUrl", "epgUrl"]`, and `Model.entryWith`
DROPS the retired keys from every write [round 7, R17a: every CONSUMED retired
key -- one a record holds or the service already consumed; an input nothing
has adopted stays, `Model.retiredInputsToKeep`; round 8: "consumed" compared
through `Model.entryInputForm`, R18a] [round 11, R21: every retired key while
the one migration's write has not landed, none after it], so the key is removed from the stored
entry rather than emptied -- the host builds the stored entry as `{id}` plus
exactly what it is handed, measured on 2026-10-11 and recorded in
`OMARCHY-PLUGIN-CONTRACT.md`. There is now exactly ONE call of
`updateEntryInline` in `Service.qml` (`writeOwnedEntry`; the node suite counts
the call sites). Identity is NOT changed: still the normalized URL, the key
still `Model.sourceKey` of it and still the cache directory name, so no cache
is rebuilt. The function whose job was "name the active source from a URL" is
deleted rather than left behind with no caller; the comment above
`Model.reconcileSources` says why.

**[Round 11, 2026-10-13: the product owner withdrew this input path (R21,
below). What this paragraph and its bullets describe now runs ONCE, as the
migration of a 0.13.x install, and after the migration marker has landed a
URL on the entry is refused, reported and stripped. The text is kept as the
record of rounds 2-10.]** **The input path, which the first build got wrong and the adversarial review
caught (lead rulings R1-R5, 2026-10-11).** `playlistUrl` and `epgUrl` on the
entry are INPUTS, and the first build read them in the wrong order: its
resolver trusted the state's key before it looked at the entry, every first or
forced reconcile went that way, and the owned write that followed stripped the
URL out of `shell.json` -- so a `omarchy bar set ... playlistUrl` made while
the shell was down was discarded and then erased, and a configured install
never moved its active source on the CLI path at all. Reproduced by calling
the shipping functions in the service's order, not argued. What the tree does
now, with each decision lifted into `Model.js` so node can call it (rule 12):
- `Model.reconcileAction` decides what a settings change MEANS. `adopt` when
  the entry carries a playlist URL this service has not consumed -- the first
  reconcile of a service, or a value different from the snapshot of the last
  one -- whether or not the reconcile was forced; `migrate` on a state load or
  a first reconcile with no fresh URL; `ignore` otherwise, including the input
  going empty, which is the steady state after the plugin's own strip.
  `adoptEpg` is decided the same way and independently.
- `Model.adoptActiveSource` resolves in this order, and the order is the
  whole decision: (1) a fresh entry `playlistUrl`, validated -- valid goes
  through `Model.reconcileSources` exactly as a CLI value always has (a known
  URL becomes active; an unknown one is added with origin `cli`, or `migrated`
  on the very first v2 run; at the 50 cap the least-recently-used non-active
  record is evicted and its cache directory removed [2026-10-20, R27d,
  D-SRC-44: no longer -- at the cap step (1) answers `full`, nothing is added
  or evicted, the marker is not set, the entry keeps its URL and the user
  is told once (`Sources is full`); the next reconcile after a removal
  migrates] [2026-10-20, R28b: the entry's `epgUrl` is held with it, not
  attached to the step-2 record, and the migration after a removal takes
  both]), invalid is reported and
  the key is left exactly as it was [2026-10-20, R29d: and the entry's
  `epgUrl` beside an invalid playlist is not attached to the step-2 record
  either -- until R29d it replaced that record's own guide URL -- but
  reported with the playlist in one notice (`invalid-pair`) and stripped
  with it; `epgWithInvalid` in the result]; (2) the state's `activeKey` when it
  names a record; (3) the entry's `sourceKey` when it names a record; (4)
  nothing, and a dangling key is cleared rather than left for the next reader.
  Then a fresh EPG input is attached to whichever record is now active, on
  every path, an `ignore` plan included, so D-SRC-02 stays closed.
  `Model.reconcileSources` writes the adopted key INTO the state it returns
  (R2); `Model.removeSource` of the active record clears the pointer in the
  state it returns (R3), as the helper's `remove_source_record` already did.
- Why "not consumed" and not "every reconcile" (lane A's DR-1, accepted as
  built): the strip is the plugin's own write, which the host never echoes
  (rule 9), so the host keeps publishing the adopted URL until somebody else
  writes. A state reload is a forced reconcile, and reading that stale URL
  again would re-add and re-activate a source the user had just removed
  through `state source remove`. A cost was written here in round 2 --
  "re-setting the SAME URL in one session after removing it is `ignore` until
  the next shell start" -- and it was FALSE: the review's data-loss lens walked
  the shipping functions in the service's order over both host shapes, and
  the owned write that follows the remove strips the stale echo from the entry
  and moves the service's snapshot (on the one-write-behind host the published
  entry falls back to the previous stored one, which carries no URL; on the
  echoing host, omacom/omarchy#15082, the snapshot is `""` at once), so the
  re-set value differs from the snapshot and is adopted. Withdrawn 2026-10-12
  from every document that carried it; measured at the Model layer in node,
  not live.
- An input is never stripped unadopted (R12, round 3). An `epgUrl` set while
  NO source is active cannot be attached to anything, and round 2 stripped it
  in the same owned write anyway -- the user's value gone with no copy (review
  P2). Now it stays on the entry, the guide reads it as its fallback meanwhile,
  the service's EPG snapshot moves only for an input that reached a record
  (`epgSnapshotAfter`, lane-key-s1), and the
  reconcile that brings the first source adopts it; `writeEntry` is asked of
  `epgConsumed`, not of "the entry carries an EPG". The same already held for
  `playlistUrl` by R1. **[Round 7 (R17, 2026-10-12): R12 held only in the
  write that could not attach the value. Every LATER owned write stripped it
  -- the logo toggle's heal, and on the echoing host the key mirror's heal
  after a switch or an in-app first add, before any reconcile saw an active
  record beside it -- so R12 now lives at the sink and the active move adopts;
  the round-7 paragraph below.]** **[Round 8 (R18d): an in-app add whose form
  carries its own guide URL is the one move that does NOT adopt a pending
  value: the form's wins and the pending value is superseded; the round-8
  paragraph below.]** **[Round 9 (R19b, R19c): the on-entry half of R12 is
  OVERTURNED -- with no active source the value is held in `state.json` as
  `pendingEpg` and taken off the entry by the same R13-gated write, so the
  guide's fallback reads the held URL (`Model.activeEpgUrlOf`); and so is
  R18d's form-wins rule -- at any move the input set LATER wins, by time;
  the round-9 paragraph below.]**
- The empty input is a no-op, and that is a lever withdrawn rather than lost
  quietly: `omarchy bar set ... playlistUrl ""` and `... epgUrl ""` no longer
  clear anything, because an entry the plugin itself empties on every write
  cannot also be a command to empty the configuration. The Sources screen and
  the helper's `state source` verbs are where a source or a guide URL is
  cleared (R4). The stale `Service.qml` comment that said the CLI clear still
  arrived on `onActiveEpgUrlChanged` is rewritten.
- Write order (R5). A move of the active source is two writes, the key into
  `state.json` and the mirror into the entry, and the mirror write is the one
  that takes the URL OUT of the entry. `Model.pointerWritePlan` fixes the
  order: state first, and the entry WAITS when the state save is parked
  behind the start-up directories (`stateInitProc`'s exit writes the parked
  state and only then the entry). An interrupted migration therefore leaves,
  at worst, the URL still on the entry -- the idempotent old shape,
  re-adopted on the next run -- and never a record nobody points at. The
  first build wrote the entry ungated through `Qt.callLater` while the state
  save could still be deferred.

**The start that was NOT interrupted lost it anyway (D-SRC-15), and round 3
(lead rulings R9-R12, 2026-10-12) is what the tree does now.** R5 ordered
the two writes for a shell that dies between them; the harness lane then ran
the ordinary, uninterrupted first start live under a nested cage and the
adopted pointer was gone (key-scenario 32 / 12 on lane-key-r2, the pre-existing
sources scenario 46 / 22 against 66 / 0 on dev). The mechanism, measured and
attributed with a helper whose `state init` does nothing: the helper's
start-up `state init` ran `os.chmod(path, 0o600)` on the EXISTING `state.json`;
that is an inotify `IN_ATTRIB` on the file the service's `stateFile` FileView
watches (`watchChanges: true`, `onFileChanged: reload()`), and a FileView
probe shows a chmod 0600 -> 0600 reloading too; `applyUserState` was handed
the PRE-adoption text, which was not in `recentSaves` because the first save
was parked behind `dirsReady`; `Model.stateOnLoad` keeps only the session
record of the in-memory state; so the adopted key and any NEW record were
replaced by the file, the parked save then wrote the key-less state and the
entry flush stripped the URL with `sourceKey ""`. A 0.13.5 install with one
source came up unconfigured with the URL gone; a URL set while the shell was
down was lost outright. The shape is OLDER than D-SINK-19 -- any in-memory
change before `dirsReady` was lost on that reload -- and the URL left on the
entry recovered a known record by accident until D-SINK-19 removed the backup.
The sibling, found by the data-loss lens: `startCacheLayout` sets `cacheReady`
BEFORE `dirsReady`, so an IPC switch or remove in that window was undone by the
same reload while its `cache remove` still deleted the directory.
What the tree does now, on lane-key-s1 (3d2d8e7):
- R9. A reload NEVER replaces in-memory state that is newer than the file.
  `Model.reloadDisposition` is asked first in `applyUserState`: `apply` for the
  first load and for a file that is genuinely newer (a CLI `state ...` write
  with nothing of ours outstanding [round 12, R22f's search: that write never
  arrives, because the FileView raises no reload on the helper's atomic
  rename (D-SRC-19); a newer file is applied when it is written in place]
  [round 13, R23g: lane A's measurement contradicts the bracket above -- the
  real `Service.qml` applied a helper rename as `file-newer`, idle and under
  load -- while the round-9 and round-12 lenses measured no reload; section
  5's round-13 amendment, and undecided] [round 14: decided -- the lenses' rigs started
  with the state directory absent, the one session that never reloads, and
  R24c re-arms it; and while a save is held a reload is ignored only when
  its text is the base, a FOREIGN text being merged (R24a)];
  and since round 12 (R22a) only a load that parses as a state reaches
  `applyUserState` at all -- a failed load is no longer applied as an empty
  state); `ignore` for the service's own write
  echoed back, a save parked behind `dirsReady`, a save in flight
  (`stateSavesInFlight`, counted up before `setText` and down on the
  FileView's `saved` / `saveFailed` -- one `saved` per `setText`, measured, so
  a counter and not a flag; **since R13 (round 4) 0 or 1, cleared by CONTENT
  through `Model.stateSaveLanded`, because a burst coalesces `saved`**), or a save
  that failed. An ignored reload runs
  neither `reconcile(true)` nor `startCacheLayout`, and the count
  `stateReloadsIgnored` is what the harness reads (**since R15,
  `stateReloadsByReason`, one number per reason, is what D3 reads**). The sibling is covered by
  the same flag: the switch or remove before `dirsReady` parks a save, so the
  reload that follows is ignored.
- R10. The helper leaves a file that is already 0600 alone (`init_state_file`
  stats first). Belt and braces, not the fix: a 0644 file still gets the
  chmod, and the service must survive that reload by R9 -- which the key
  scenario forces by seeding the file 0644 on purpose (D3 reads the ignore
  off the counter).
- R11. `stateInitProc`'s exit gates the entry flush on the helper's exit code
  AND on the parked save having LANDED -- the FileView's `saved`, not
  `setText` returning (`Model.entryFlushDisposition`: `none` | `wait` | `flush` |
  `drop`). On failure the entry is NOT rewritten, so the URL stays on it as
  the backup it accidentally is, and a warning with no URL is logged. The
  order (save, then entry) is pinned by a structural check that reads
  `Service.qml`, the D-SINK-18 shape. **R13 (round 4, below) extends the
  gate to the route with the directories ready.**
Observed, not inferred: on lane-key-s2 `key-scenario.sh live` reads 49 passed
/ 0 failed and 36 / 13 over `--baseline lane-key-r2` (D2, D3, M1, M3, M5,
C1-C5, E1, O5, O6 -- everything that rests on an adoption made at start-up);
`sources-scenario.sh` under cage 63 / 3, the three pinning the pre-round-2
SR25 contract rather than this. One assertion from the round-2 review is
REFUTED by the same measurement and is recorded as a control: the created-file
shape (no `state.json` at all) does not drop, because a FileView loaded over a
missing path never sees the helper's create (N1-N4 green on the dropping tree,
`stateReloadsIgnored` 0 across a fresh start). Not observed, said so: the
state directory unwritable at start (R11's `drop`), and a CLI `state ...`
write landing inside a parked or in-flight shell save, which R9 as ruled
loses to the shell's save (the helper's warning says so).

**Round 4 (lead rulings R13-R15, 2026-10-12), after the third review measured
lane A's own DQ-A2 live.** R11 gated the parked route only. With the
directories READY, `persistActive` wrote the entry straight after `setText`
and before the FileView reported, so a state write that failed then (an
unwritable `~/.local/state`, a full disk) had already stripped the URL from
the host's file: the record existed in memory only and the input had no copy
anywhere -- a loss D-SINK-19 created, closed on one of its two routes, and
recorded by the lane as a question rather than a defect. The lens's rule (an
input lost or stripped unadopted is a blocker) is the right one, and the
lesson is the one `CLAUDE.md` carries for D-SINK-16: a residual in our own
words can be the same defect, softened. What the tree does on lane-key-t1
(bb06540):
- R13. The entry mirror is written only after the state write it depends on
  has LANDED, on every route: `Model.pointerWritePlan` takes `savesInFlight` and
  `saveFailed`, answers `write-entry-after-saved` whenever a save is issued,
  in flight or failed, and `write-entry` only with nothing outstanding; the
  held key is settled by `Model.entryFlushDisposition` from `saved` / `saveFailed`,
  a save parked or in flight outranking a STALE failure. `switchSource` and
  `removeSource` report `ok` on the state write being ISSUED (the state write
  IS the switch); its failure arrives later as
  `sourcesPersistFailed("state_write_failed")`, once per episode, with no
  URL; a REFUSED mirror is logged and repaired on the next start, never
  reported as the switch failing (SR25 as amended in
  `ARCHITECTURE-SOURCES.md`). "Landed" is by CONTENT (`Model.stateSaveLanded`):
  one `saved` per `setText` held for two back-to-back writes and not for a
  burst -- 10 warm switches issued 20 `setText` and raised 14 `saved` on this
  tree, 15 on lane-key-s2 (a 26-write probe: 25 `saved` + 1 `saveFailed`,
  `text()` tracking the write that started; lane A under cage, 2026-10-12)
  -- and the signal-counting first version stuck at 5 of 20 for the rest of
  the session, which on lane-key-s2 also read every later foreign reload as
  "save in flight" (lane A's DQ-T4: D-SRC-16, P2, a D-SRC-15 sibling fixed on
  lane-key-t1 by the content rule, unreleased; cited by id since round 6,
  once the board row existed).
- R14. The two decisions only the live arm could see have structural pins in
  `tests/Model.test.js`: the ignore branch of `applyUserState` RETURNS, and
  `saveState` parks (sets the flag) before `dirsReady`; each seen red by
  deleting the line.
- R15. The reload counter counts BY REASON -- `stateReloadsByReason`, one
  number per `Model.reloadDisposition` reason through `Model.countReload`, exposed on
  the harness's `pointerState` -- because the plain total was satisfied by
  the own-write echo that follows every start and could not go red for the
  chmod reload D3 names; and a shell exiting with `pendingEntryKey` still
  held logs one warning with no URL (DQ-B9).
Observed, not inferred, on lane-key-t2 (lane B, 2026-10-12, the transcripts
named in its report): `key-scenario.sh live` 62 / 0 (61 lettered checks);
`--baseline lane-key-s2` 54 / 8 -- D3 and W3/W6 for the counter s2 lacks,
F3-F7 the loss at the sink (the stored entry read with NO `playlistUrl` and
the mirror moved, no `state_write_failed`, no record for the input after the
restart, two records not three); `--baseline lane-key-r2` 38 / 24;
`--baseline f275bde` 39 / 23; two throwaway mutations of this code,
`Model.reloadDisposition`'s save-parked clause deleted 56 / 6 (D2, D3, W2-W4, W6)
and the R14 `return` deleted 57 / 5 (D3 GREEN beside D2/W2 red: the counter
observes the decision, the sink is D2, and the `return` is the structural
pin; since round 5 the two mutations are patch files under the harness's
`spikes/key-mutations/`, applied to an export and run through
`key-scenario.sh --tree`, 58 / 6 and 59 / 5 on 63 lettered checks on
lane-key-u2; nothing cites the two branches any more, and they are the
lead's to delete); `sources-scenario.sh` 66 / 0 under cage with the three
checks on the ruled contract (62 / 4 for the same harness over an export of dev 93bbd5d,
exactly the four moved checks). Node 2146 / 0 on lane-key-t1 (+21; the same
files over an export of lane-key-s2: 21 failures, the P1 driver reading
`urlStillStored:false ... fileSources:2`), python 1056, qml 78. Still not
observed, said so: the state directory unwritable at START (R11's `drop`),
a remove on a failed disk (F drives the CLI set and a switch), a `saved` for
an EARLIER write arriving while a later one is pending and then fails, and a
CLI `state ...` write inside a parked or in-flight shell save.

**Round 5 (lead ruling R16, 2026-10-12), after the fourth review measured
R13's own fix losing the record through the writer R13 had not gated.**
`writeOwnedEntry` has two callers. R13 gated `writeActive`, the key mirror.
The second, `setShowLogos` -- the logo toggle, `g` in the guide's Sources
view and the consent's confirm -- wrote `{ sourceKey: <memory>, showLogos }`
with no plan and no disposition, and `Model.entryWith` stripped `playlistUrl` and
`epgUrl` on every owned write by design ("any owned write heals an old
entry, including the logo toggle"). So in exactly the state R13 now leaves
on purpose -- a failed state write, the URL kept on the entry as the only
copy, the failure signalled -- one toggle rewrote the entry to a key the
file did not have and took the URL off; the record then existed nowhere
durable and the next start lost it. Measured live under a nested cage on
lane-key-t2 (the stored entry after the toggle named the in-memory key with
`playlistUrl` GONE, `state.json` still the old key, the restart found no
record anywhere) and at the Model layer (4 of 4 routes under both host
shapes; 308 of 4,392 driven sequences, all of them the four that end with a
logo toggle, 0 in the other 4,084); pre-existing on every D-SINK-19 tree,
and invisible to 2,146 node checks, 11 check-tree, 62 / 0 live and 66 / 0
sources, because nothing drove a toggle after a failed write. The lesson is
rule 15 one layer in: the round-3 P1 was fixed in one of two callers of the
same funnel, and the search for the sibling has to be run over the FIX as
well as over the defect. R16, as landed on lane-key-u1 (b42b5ab, lane A): an owned-entry write that is
NOT the key mirror writes only the fields it owns while anything of ours is
outstanding -- `Model.ownedWriteMode` takes the three flags (`savePending`,
`savesInFlight`, `saveFailed`) and nothing else [four inputs since round 6,
below] and answers `patch` or `heal`; on `patch` the toggle writes `showLogos` alone with `keepRetired`,
so `sourceKey`, `playlistUrl` and `epgUrl` stay exactly as the host
publishes them [round 6: this said "holds"; on the lagging host the two
differ by one write, D-SINK-20], and the entry is healed only by `writeActive` under R13 once the file
agrees with memory; the own-write override recognises the patch as ours
under both host shapes. Observed: sixteen node checks (the `ownedWrite`
fixture section, the driver extended with `setShowLogos` under both host
shapes auditing every entry write against the file's own pointer, the
structural and copy pins), 17 red over an export of lane-key-t2 and 0 on
lane-key-u1 (node 2,162), twelve one-decision mutations each reddening at
least one; the lens's own drivers 4 -> 0 losses and 308 -> 0 of 4,392; at
the sink, key-scenario L1/L2 inside F: 64 / 0 on lane-key-u2 and 60 / 4 on
`--baseline lane-key-t2` (L1 `stored:<C> playlistUrl:no`, L2 `keys:0
alone:0`, F6/F7 restarting over that entry find no record -- lane B's
transcripts, 2026-10-12). The same ruling routes the persist failure's
REASON to the guide (`Model.persistFailureMessage`; the round-4 review's P2) and
keeps once-per-episode signalling as a decision with its consequence
(`UX-SOURCES.md` 5.5). The residual, measured in the driver and not live [observed live since,
by the fifth review; D-SINK-20 on the board]:
under a host that publishes one write behind, a patch-only toggle right
after a heal carries the URL the heal removed BACK onto the stored entry;
it is the file's own active record's URL, re-adopted idempotently at the
next start, nothing enters the file the host did not publish and no record
is lost, and the echoing host has no such lag (DQ-U1).

**Round 6 (2026-10-12, lane-key-v1 78ff442, lane A), after the fifth
review read the chain mergeable with no P1 and found the one state R16's
three flags could not name.** Before `stateFile`'s first load memory is the
empty state and no save flag is raised, so `Model.ownedWriteMode` answered
`heal` and a logo toggle in the start-up window wrote `sourceKey ""` and
stripped a URL set while the shell was down -- its only copy (3 of 4
host/disk combinations at the Model layer; no harness reaches the window,
the lens's first IPC answer arriving with the state already loaded). R16 is
amended: the decision takes a fourth input, `stateLoaded`, and answers
`patch` (`state-not-loaded`) before the first load; anything but `true`
counts as not loaded. The same round pins what the funnel composes the
patch FROM -- `root.settings`, the own-write overlay of rule 9, and never
`root.hostSettings`, whose one-token mutation reverted a toggle on the
lagging host with node 2,162 / 0 and live 64 / 0 -- and drives the parked
and in-flight toggles in node, which only the fixture cube had pinned.
Observed on lane-key-v1: node 2,171 / 0 (+9), the `ownedWrite` fixture 16
cases, 5 red with the same tests over lane-key-u3's code (the driver
failing on the loss, `urlKept:false mirror:""`), the four one-decision
mutations of the decision and the funnel each red (4, 4, 4, 7); the
review's own drivers 3 -> 0 losses and 3,939 -> 21 problems of 48,312, the
21 being D-SINK-20's. The residual DQ-U1 is now D-SINK-20 on the board and
observed live (the fifth review's live lens under cage, the fake host
modelling the lag). Harness half: `ipc pointerState` omits a field the tree
lacks, so a `held:NULL` want is red on a tree without the field (on
`--baseline f275bde` W1, W3, W5, F2 and F5 read `held:NOFIELD`, 39 / 25;
forward 64 / 0, lane A's transcripts). Detail in `ARCHITECTURE-SOURCES.md`
4.3 and its round-6 rulings.

**Round 7 (2026-10-12, lead ruling R17; lane-key-w1 2ccbb74, lane A), after
the sixth review's data-loss lens found an input no oracle had covered for
five rounds.** R12 keeps an `epgUrl` set while NO source is active on the
entry, and nothing recorded that state: with the state loaded and nothing
outstanding `Model.ownedWriteMode` answers `heal`, and `Model.entryWith`
dropped every retired key, so the logo toggle on the lagging host stripped
it (observed live on lane-key-v2 by the lens, LOST with the toggle and KEPT
without) and, on the echoing host, the key mirror's heal after a switch or
an in-app first add stripped it with no toggle at all, because `reconcile()`
never runs on an active-key move. The value then existed nowhere. Every
earlier matrix checked playlist inputs only; with an EPG oracle added the
lens read 2,327 losses in 7,084 EPG runs on lane-key-v2. R17a puts R12 at
the sink: the one funnel asks `Model.retiredInputsToKeep` on every owned
write, heal and patch alike, and hands the answer to `Model.entryWith`, so a
retired input leaves the entry only when it is consumed -- a record holds it
(any record for the playlist, the ACTIVE record for the EPG) or the service
already adopted or refused that value (the snapshot clause, lane A's reading
of the ruling: without it the lagging host's stale publish carries a stripped
URL back after its record is gone, resurrecting a removed source at the next
start). R17b: `switchSource` and the probe commit land a pending EPG on the
record becoming active in the same turn, before the save and the mirror
(`adoptPendingEpg`), never waiting for a host publish to trigger a
reconcile (rule 9); `removeSource` leaves it pending. R17c confirms that an
absent `stateLoaded` means "not loaded". The rule-15 lesson is the
instrument's: the service-order driver now audits every owned entry write
for EVERY input the entry carries -- no value on the stored entry before a
write may be absent afterwards from both the entry and every record -- and
that audit reads 8 lost writes over lane-key-v2's code. Observed on
lane-key-w1 (lane A): node 2,191 / 0, 2,191 / 16 with the same tests over
lane-key-v2's code; key-scenario segment U live under cage, 71 / 0 forward
and 66 / 5 on `--baseline lane-key-v2` (U2, U3, U4 on the lagging fake host,
U6, U7 on the echoing one through the new `run.sh --host echo` lever); the
lens's own instruments 6 -> 0 losses and 2,327 -> 0 EPG problems. Detail in
`ARCHITECTURE-SOURCES.md` 4.3 and its round-7 rulings.

**Round 8 (2026-10-12, lead ruling R18; lane-key-x1 1f8bd1b, lane A), after
the seventh review's data-loss lens found two P1s, each reproduced live.**
P1-A was round 7's own: the keep decision compared the published entry's
value raw against a snapshot `Model.settingsFrom` had trimmed, and `omarchy
bar set` stores a value as typed (`jq --arg`), so a URL pasted with a
trailing space was never consumed -- a refused credential stayed in
`shell.json`, a removed source was re-adopted at the next start (observed
live), and on the echoing host a pending EPG beside it looped. P1-B was
older, on the chain since before round 7 and absent from `dev`: on the
lagging host a refused `playlistUrl` beside a pending EPG looped at about
3,000 no-op entry writes a second with the shell's CPU saturated, because
the funnel REASSIGNED its own-write record even for a write the host
answered `false` to, and the reassignment re-ran reconcile, which asked
for the same write from the stale publish. R18a: one normaliser,
`Model.entryInputForm` (trim, sanitize, validate as a CLI value of that
kind), through which every comparison of an entry value goes -- reconcile's
"fresh", the sink's "consumed", adoption itself -- so they cannot
disagree; its search found a sibling, an EPG of control characters alone
that emptied the active record's guide URL. R18b: a write that changes
nothing changes nothing -- the funnel declines a write the host would
answer `false` to (`entryWriteNeeded` in model/settings.mjs [withdrawn by
R19a in round 9 and deleted by R22e in round 12], estimating the stored entry
from its own last write while the publish has not moved, never waiting for
an echo) and reassigns the own-write record only when it differs
(`Model.sameOwnWrite`). R18c: quiescence is a check -- the node driver runs
every sequence to a bound and fails one that does not settle, and it now
re-runs reconcile on every reassignment as QML does, where it had done so
only on a content change (rule 10: the double was more forgiving than the
real thing, which is why P1-B never reached node). R18d: the snapshot
clause and the refused-value reading are confirmed, and a guide URL an
in-app add's form carries wins over a pending CLI `epgUrl`, which is then
superseded and stripped by that commit, logged by key name. Observed on
lane-key-x1 (lane A): node 2,236 / 0, 2,236 / 41 with the same tests over
lane-key-w2's code; key-scenario segments K (the loop window on both
hosts), Z (whitespace-wrapped inputs) and A (the in-app add through the
harness) live under cage, 79 / 0 forward and 73 / 6 on `--baseline
lane-key-w2` (K1 17,414 entry writes and 596 CPU ticks in 5 s, K3 19,943 /
637, Z1, Z2, Z3, A2); the lens's own matrix 0 in every cell where
lane-key-w2 reads 120 (lag), 4,034 and 4,004 (whitespace). Detail in
`ARCHITECTURE-SOURCES.md` 4.3 and its round-8 rulings.

**Round 9 (2026-10-12, lead ruling R19; lane-key-y1 690a888, lane A, on
the chain as it landed on the split model, lane-key-y0 c017d24), after the
eighth review found R18's own write skip and R18d's form rule each losing
a later input.** P1-A, both lenses, live: on the lagging host a publish
that goes A -> B -> A (an `omarchy bar set` that restores the earlier entry
exactly) brought the funnel's record of its last write back, and the skip
it fed declined writes the host would have stored -- an in-app logo OFF did
nothing, a refused credential set again stayed in `shell.json` for the rest
of the session, an `epgUrl` set twice later replaced an in-app guide URL
edit. P1-B: a CLI `epgUrl` set while an in-app add's probe ran, AFTER the
form was submitted, was superseded by the earlier form and ended nowhere;
the same principle on the edit form. R19a: no skip on an estimate -- every
owned write is handed to the host and `updateEntryInline`'s answer is the
dirty check; `Model.sameOwnWrite` alone settles the cycle. R19b: a guide
URL no record can take is held in the 0600 `state.json` as `pendingEpg`,
never in `shell.json`, and stripped by the same R13-gated write, replacing
R12's on-entry pending state. R19c: every record carries `epgSetAt`, set at
the add form's submit, at an edit that changes the guide URL, or at
adoption, and at an active move the input set LATER wins. R19d: D-SRC-18 is
settled for its board shape by an owed mirror -- a key mirror dropped
because its save failed is paid by the next save that lands
(`Model.owedMirrorAction`). The a12 read is now `Model.activeEpgUrlOf`,
called by node. Observed on lane-key-y1 (lane A): node 2,268 / 0, 2,266 /
52 with the same tests over lane-key-y0's code; key-scenario segments Y
(A -> B -> A on three routes), Q (the probe race, both orders), V (the
edit route) and H (D-SRC-18 at the sink) live under cage, 86 / 0 forward
and 74 / 12 on `--baseline lane-key-y0`; the lens's length-2 matrix 0 on
both hosts where lane-key-y0 reads 24 and 16. Open: the helper's state
whitelists are not taught `pendingEpg` or `epgSetAt`, so a helper write of
the file erases them [D-SRC-20; closed in round 10]. Detail in
`ARCHITECTURE-SOURCES.md` 2.1, 3.5, 4.3 and its round-9 rulings.

**Round 10 (2026-10-12, lead ruling R20; lane-key-z1, lane A, after the
ninth review's two lenses over lane-key-y2).** D-SRC-20 (P1): the helper's
state writer dropped the held guide URL and every set time, and a restart
then left the user's CLI `epgUrl` nowhere (live under cage). D-SINK-20,
re-graded P2: on the lagging host the patch-only logo write re-carried a
refused credential that no record holds, it stayed in `shell.json` for the
session, and at the next start the re-carried value, seen as new, replaced a
later in-app edit that had landed (live). D-SRC-19 (P3, shipped): the
service never reloads a helper `state` write [round 14: re-scoped to the
first session after a fresh install by the round-13 live lens, and re-armed
there by R24c]. F-PERF-2 (P3): the cold first
open over 150 ms with `dev` unmeasured. R20a: the helper keeps what the
service writes, on one shared fixture, with a check over every key the
service can serialise. R20b: what the service has consumed from the entry is
persisted (`entryInputs`, digests), so a value the state proves consumed is
not adopted again at a start, and an input equal to the held guide URL is
judged at a start with the time it was first seen; this settles D-SRC-18's
last window (the shell dying between the edit's save and the owed mirror)
and D-SINK-20's restart half. R20c: the patch-only write strips what the
last LANDED state holds and what was refused and reported, and keeps only a
valid input that state does not hold -- deciding from the plugin's disk,
where the narrowing D-SINK-20's record warned against decided from the
host and stripped the only copy. R20d: `tests/service-harness.js` runs
`Service.qml`'s own functions in node, and drives the funnel's decisions
(two consecutive toggles, the add stamped at submit); key-scenario Y4 is
the live double toggle. R20e: a `Model.` citation must name something
`Model.mjs` exports. R20f: floors level (node 2319, python 1143). R20g:
`dev` measured interleaved with the chain -- cold medians 165 and 169 ms,
warm 92 and 92, over 11 runs each at load 1.8-4.5 -- so the chain moves
neither and the cold reading is not the chain's. Observed on lane-key-z1
(lane A): node 2,319 / 0, and 2,319 / 23 with the same test files over
lane-key-y2's code (re-run by the documents lane); key-scenario 87 / 0
forward with 86 lettered checks; the round-9 lens's own drivers under cage
red on lane-key-y2 and clean on lane-key-z1 for D-SRC-20, D-SRC-18 and
D-SINK-20. No shipped live scenario goes red on lane-key-y2 for those
three; their gate-borne observers are the node and python tests. Detail in
`ARCHITECTURE-SOURCES.md` 2.1, 3.5, 4.3 and its round-10 rulings.

**Round 11 (2026-10-13, the product owner's decision and lead ruling R21;
lane-key-m1, lane A).** Ten repair rounds did not converge -- P1s per round
from round 3: 1, 1, 0, 1, 2, 2, 1, 3 -- and every P1 since round 3 was
triggered by a URL arriving on the bar entry from the command line, each
fix adding state the next review broke. The owner dropped the route: the
in-app Sources form is the only way to add or change a source. R21a: one
migration. The entry's `playlistUrl` and `epgUrl` are read as input only
while the LANDED state lacks the marker `entryMigrated` (section 5); the
migration adopts as before (R1, R4, R9-R11), the marker rides the same state
write, and the entry is stripped once that write has landed (R13), every
owned write keeping the retired keys until then. 0.13.6 drops the marker, so
a downgrade and re-upgrade migrate again, correctly. R21b: after the marker
nothing on the entry is an input -- a value there is refused, reported once
per value (`Model.entryInputNotice`: a notification and a console line naming
the Sources screen, never the value) and stripped by the next owned write;
every owned write strips the retired keys unconditionally, which ends
D-SINK-20's re-carry; an in-memory record of what the session has handled
(`Model.entryInputsSeenAfter`) keeps the lagging host's stale publish from
re-adopting or re-reporting. R21c: a guide URL at the migration with no
source to attach it to is reported and stripped, never held. R21d: the
pending guide URL, the set times, the active-move adoption, the add-form
supersede rule, the persisted consumed-input snapshot and the landed-state
patch rules are DELETED, with seventeen `Model.mjs` exports, their fixtures,
tests and harness segments. R21e: pins that call the shipping code (93 node
checks titled `R21`, three python tests and the shared fixture's marker
cases) and live key-scenario segments G1-G5 (the migration, the real 0.13.6
helper's downgrade, the re-upgrade) and X1-X6 (the refusal at the sink, the
notification included). Observed on lane-key-m1: node 2,261 / 0; python
1,153; key-scenario 98 / 0 forward and 68 / 30 on `--baseline lane-key-z2`;
sources-scenario 66 / 0. R12, R17b, R18d, R19b, R19c, R20b and R20c are
overturned, not rewritten: every paragraph above stands as the record, and
the rulings, the deletion inventory and the residuals are in
`ARCHITECTURE-SOURCES.md`'s round-11 rulings.

**Round 12 (2026-10-13, lead ruling R22; lane-key-n1, lane A).** The
round-11 data-loss lens found, live on both host shapes, that a MIGRATED
install whose `state.json` could not be read at the start had an empty state
written over it -- every source, credential and favourite gone, and the
marker on disk so nothing ever migrated again. The failed load was applied as
an empty state, the migration ran on it and marked it, the save parked
behind the start-up directories, the helper's mode repair raised the reload
carrying the real text, R9 ignored that reload because a save was parked,
and the parked save landed. Its sibling is older than D-SINK-19's last
round: a state DIRECTORY that cannot be entered reads to the FileView
exactly like a fresh install, and the cache layout's save wrote the empty
default over the file -- on 0.13.6 (dev 4740a50) too, measured live by lane
A: an in-app source gone, the one the bar entry still carried re-adopted.
R22a: a state that did not load is never written; only "the file does not
exist", confirmed by the helper's `state init` (section 5, as amended),
is a fresh install; anything else is re-read once and then holds the
session in a no-write mode -- no state write, no owned entry write, no
migration, the entry left exactly as it is, the user told once. R22b: every
writer is listed and goes through one gate (`Model.stateWriteGate` in
`saveState`; `read_state_strict` in the helper), and the node harness runs
the REAL cache layout instead of a stub (rule 10). R22c: the guide's
fetch-failure hint names Sources (`check the source in Sources`), and
`tests/test_shipped_copy.py` proves no shipped string tells the user to set
`playlistUrl` or `epgUrl`. R22d: an unused ledger waiver is red. R22e: the
three R19a functions are deleted. R22f: the helper's help text, the
scenario's header and its baseline footer are corrected. Observed on
lane-key-n1: node 2,354 / 0; python 1,170; key-scenario 106 / 0 forward and
97 / 9 on `--baseline lane-key-m2` (B1-B8 red there: `records:0` at a
migrated start over a 0000 file and over a 0000 directory, a file that does
not parse replaced at the start, the hint reading `check playlistUrl`);
sources-scenario 66 / 0, logo-scenario 33 / 0. The measurement, the
decision table, the copy and the open items are in
`ARCHITECTURE-SOURCES.md`'s round-12 rulings.

**Round 13 (lead ruling R23, 2026-10-13), after the round-12 lenses.** The
data-loss lens read 0 problems over about 240,000 sequences and the live lens
no P1 or P2, and they left one P2 and six P3s. The P2: the lift's re-arm of
the no-write notice was checked by nothing (deleting it was 0 of 2,354 node
failures), so a second episode's refused input could go untold; R23a pins it
in node and live (key-scenario B9). The P3s: a FIFO at `state.json` hung
`state init` and every `state` verb in `open()`, the service waited on the
init with no bound and every start orphaned a helper (R23b, one
non-blocking opener for every state read; R23c, a 15 s watchdog that kills,
reaps and blocks with reason `init-timeout`); `state init` chmod-ed a
directory at the path to 0600 (R23d, repairs only a regular file); the logo
toggle in the no-write mode advised `omarchy bar set` (R23f,
`Model.refusalMessage`); a no-write start drew the first-run form whose
submit is refused (R23e, the notice's words as the guide's own surface, no
editable field); and the harness's counts and drawn-copy fields were
mislabelled (R23h). R23g measured the FileView's watch (section 5, as
amended) and found it contradicting three earlier measurements, which is
left to the lead. R23i removed the ledger's last three withdrawn-symbol
waivers with their citations. Observed on lane-key-p1 bb5b2de: node 2,372 /
0 (and 2,372 / 0 with the own-write echo off); python 1,180; key-scenario
112 / 0 forward and 107 / 5 on `--baseline lane-key-n2` (B10-B14 red there;
B9 seen red only through its mutation patch, because the line it guards
existed); sources-scenario 66 / 0, logo-scenario 33 / 0.

**What REMAINS, with its size rather than a claim of zero.** The exposure is
NOT closed. Three things remain, and the first is the one to quote:
1. *The key is a confirmation oracle.* It is `fnv1a32` of the normalized URL,
   32 bits, one-way, and it still sits in a file that can be 0644. It cannot
   be turned into a URL. It CAN be used to check a guess: another local
   account that reads the entry and guesses a candidate URL -- a provider's
   published `get.php` shape, a username it already knows, a password from a
   list -- hashes the candidate and compares. That is much less than handing
   over the credential and it is not nothing, and it is the reason the shield
   is kept rather than retired (SR40; `Model.entryShieldDecision` states the
   trade in code). [Round 10: `state.json`, 0600, now also holds a 64-bit
   DIGEST of each bar-entry input the service consumed (`entryInputs`,
   R20b), a refused one included -- a confirmation oracle of the same
   kind for that value, in the plugin's own private file rather than in
   `shell.json`, and never a way back to it.] [Round 11: no longer --
   `entryInputs` is withdrawn (R21d), and what the session has handled is
   held in memory only.]
2. *The input path.* `omarchy bar set ... playlistUrl` is still supported and
   is still a write of a credential into that file, made by the host on the
   user's instruction, at a moment the plugin cannot gate. The plugin removes
   it on adoption; it does not prevent its arrival. The window runs from the
   host's write to the plugin's next owned write -- one reconcile and one
   `Qt.callLater` while the shell runs, the whole downtime plus the first
   start's reconcile when it was not. Bounded in events; its wall-clock size
   is a property of the user's session and is UNVERIFIED. The README says the
   value is converted and will not be there afterwards, which is the only
   honest version of "it still works". [Round 7: an `epgUrl` set while NO
   source is active stays on the entry by design (R12), and since R17a every
   owned write keeps it there, so its window is bounded by the user's next
   activation of a source and not by any write of ours -- in time it is
   unbounded. The README says it waits on the entry. The shield
   tightens `shell.json` at every start and re-arms after every owned write
   (D-SINK-18); an EPG URL can carry the same
   credential as the playlist (an Xtream `xmltv.php` does).] [Round 8: a
   REFUSED value -- the shape a typo takes -- is stripped by the first owned
   write after reconcile reports it, whatever spacing it was typed with; on
   the round-7 build a refused value wrapped in whitespace stayed for good
   (R18a, the seventh review's P1-A). A pending `epgUrl` that an in-app
   add's own guide URL supersedes still leaves the entry with that add's
   commit (R18d), so the window above is unchanged: it ends at the next
   source activated by any route.] [Round 9: the unbounded half is CLOSED.
   A valid `epgUrl` set while no source is active is held in the plugin's
   own 0600 `state.json` (R19b) and taken off the entry by the same
   R13-gated write as any consumed input, so its window in `shell.json` is
   the playlist's -- one reconcile, the state save landing, one
   `Qt.callLater` -- and no longer the user's next activation of a source;
   a refused one is stripped the same way. If that save fails the value
   stays on the entry, as a playlist does, until a later save lands (R13,
   and R19d's owed mirror). And a value set AGAIN is stripped again: the
   round-8 build skipped that strip on the lagging host after a publish
   A -> B -> A and left a re-set credential in `shell.json` until the next
   start (R19a). Measured by lane A's key-scenario U, K, Y and H, under a
   nested cage.] [Round 10: and once stripped it stays stripped. On the
   lagging host the patch-only logo write put a stripped URL -- a refused
   credential included -- back for the rest of the session (D-SINK-20,
   re-graded P2); R20c strips what the last landed state holds and what was
   refused and reported. Observed by the round-9 lens's own driver under
   lane A's cage: `stored epgUrl=no` after the toggle on lane-key-z1, `yes`
   for the session on lane-key-y2.] [Round 11, 2026-10-13: the route is
   WITHDRAWN (R21). `omarchy bar set ... playlistUrl` is no longer supported:
   after the one migration a value set that way is refused, never adopted,
   reported once and stripped by the next owned write, which on a running
   shell is the `Qt.callLater` that follows the reconcile. So the window
   above is unchanged in shape -- from the host's write to the plugin's next
   owned write -- and still not something the plugin can prevent, but it is
   now the whole of the value's life, for a valid URL and a refused one
   alike, and never ends with the URL adopted into anything. Every owned
   write strips the retired keys once the marker has landed, so nothing is
   re-carried (D-SINK-20 ends there). Inside the migration window a
   migration input whose save fails stays on the entry as its only copy,
   which is R13's design and the one case in which a URL rests in
   `shell.json` for longer than one write.]
3. *Installs upgrading into this release.* Their `shell.json` holds a URL
   until the first owned write on the new version, which the migration itself
   issues on the first reconcile (a URL on the entry makes `writeEntry` true).
   The shield runs on the startup path unconditionally, so the container is
   tightened at that start whether or not the write lands -- F-M3-16's
   lesson, that the artifact needs the fix as much as the derivation does.
A fourth, smaller, and measured on 2026-10-11 (`OMARCHY-PLUGIN-CONTRACT.md`,
case B; the docs lane's DQ-2, recorded here as a residual rather than fixed):
**a `plugins[]` copy of the entry is never rewritten by an owned write.** When
the plugin's id ALSO appears in the host's top-level `plugins[]` list,
`updateEntryInline` rewrites only the `bar.layout` copy (its `plugins[]` loop
runs only `if (!foundInLayout)`), so a URL in a `plugins[]` copy stays there
through every write of ours, the migration's included, and the mode shield is
the only thing between it and another account. The plugin never READS that
copy, so nothing is adopted from it either. On this machine that list is
empty and `omarchy plugin enable` writes to `bar.layout`; whether any
supported command fills `plugins[]` is UNVERIFIED, which is why this is not
in the README.
A fifth, the smallest, recorded on 2026-10-12 as D-SINK-20 (P3; round 6 of
the repair, never shipped): **on the host that publishes one write behind
(Omarchy through 4.0.4), a patch-only logo toggle can put a just-stripped
URL back into `shell.json` for one write.** R16's patch carries the entry's
URL keys over as the host PUBLISHES them, and after a heal write has
stripped a URL the user set with `omarchy bar set`, the published copy
still carries it; the next owned write strips it again. Observed live by
the fifth review under cage with the fake host modelling the lag, and
bounded by its data-loss lens: in 48,312 driven sequences every re-carried
URL was the user's own input one write earlier and already a record in the
0600 state file, and the echoing host (omacom/omarchy#15082) never
re-carries. The shield keeps the file 0600 meanwhile (D-SINK-18). The
obvious narrowing -- keep the retired keys only while no own-write override
is in force -- strips the only copy of an input whose state write failed,
the round-4 P1 back through the same writer, and is not the fix; the
correct one needs to know whether the last LANDED state text holds a record
for the published URL. [Round 10: re-graded P2 by the round-9 data-loss
lens -- both bounds above failed live: a refused credential no record
holds was re-carried, and no owned write followed, so it stayed for the
session and replaced a later edit at the next start. R20c is that correct
narrowing, deciding from the state the last landed save serialised, and
R20b closes the restart half. D-SINK-20 is closed as filed, the board's
state the lead's; `ARCHITECTURE-SOURCES.md` round-10 rulings.] [Round 11: and after the migration it cannot happen at all -- the
patch-only write keeps no retired key once the marker has landed (R21b;
node `R21e (...) a refused value is stripped by the logo toggle's
patch-only write too`). R20c's landed-state rule is withdrawn with it.]

**The costs, accepted by the product owner on 2026-10-09 before the work was
briefed, restated after the review as what the code does.** (1) `omarchy bar
set ... playlistUrl` is input-only, on the "not consumed" terms above.
[Round 11: replaced -- it is read once, by the migration, and refused after
it (R21).] (2) A
DOWNGRADE reports the plugin as not configured, because an older build looks
for a URL that is no longer there, and it looks like data loss precisely
because the migration was silent; the older build's own `Saved sources (n)`
link is the recovery. The round trip back up is a MIXED shape, not the old
one: the older build's `entryWith` copies every own key of the entry, so
`sourceKey` survives on it; its `ownedEntryPatch` writes the newly picked
`playlistUrl` beside that stale key; and the older `parseState` drops
`activeKey` on its next save. Step 1 above resolves that to the URL -- the
source picked while downgraded is the one that comes back -- and the owned
write that follows strips the URL again. Derived from both builds' code
(1a8dccd for the older one) and pinned by the node suite's adopt cases; the
live round trip is UNVERIFIED. [Round 11: under R21 the re-upgrade migrates
again, because 0.13.6 drops `entryMigrated`; observed with the REAL helper
of the v0.13.6 tag rewriting the file and the current service restarting
over 0.13.6's entry (key-scenario G4, G5). 0.13.6's own service was not
run.] (3) `state.json` becomes the only copy of the
source list, where the URL in `shell.json` used to be an accidental backup
that `Model.reconcileSources` could rebuild a record from. All three are in
the README in plain language, none of them softened.

**The siblings, asked before closing (rule 15), in two sweeps.** The first
sweep's shape is not "what writes to a file we do not own" -- that was
D-SINK-18's -- but "what FACT does this plugin identify by a value that is
itself a secret", since an identifier has to live wherever the fact is named.
Swept over the tree at 65ec1b8:
- **`epgUrl` on the bar entry.** Not a new discovery, but named because the
  fix can get it wrong: a migration that moves `playlistUrl` and forgets
  `epgUrl` leaves the same credential behind in the same place, and on an
  Xtream provider the `xmltv.php` URL is built from the same username and
  password. Both are retired keys; both move.
- **The cache directory name.** Already a key and not a URL (D4/D5). The
  precedent the fix follows. Cleared.
- **Logo cache filenames.** Already `fnv1a32(url)` -- `logo_filename` in the
  helper, whose docstring is explicit that the provider's path never reaches
  the filesystem. Cleared.
- **Favorites, recents, `lastPlayed`, `failed.json`.** Keyed by channel id,
  never by a URL (a `failed.json` row is `{id, at}`). Cleared.
- **The player session record, the player lock file, the mpv socket and the
  runtime directory.** A channel id and a name; `{schema, seq, verb, at}`;
  constant names under a directory the plugin owns. Cleared.
The second sweep, 2026-10-11, over the repair itself, by the shapes the review
found: "where else is the active key derived", "where else does a record leave
the list", "who else reads the input pair". `Model.parseState` dropping
invalid records and `Model.reconcileSources` evicting at the cap can both
leave the file's `activeKey` dangling -> `Model.activeKeyOf` validates on
every read (fixture section `resolve`). The helper's `remove_source_record`
and its id-remap already clear or carry the pointer; unchanged, now run by the
shared fixture. The probe-commit edit of the ACTIVE source (`Service.qml:4005`)
removes the old record and adds the new one before `persistActive(newKey)`,
and already resolved the intermediate state to `""` at the merge base, so R3
changes nothing there (lane A's DR-5; left for whoever holds the display). The
readers of the input pair are `inputPlaylistUrl`, `inputEpgUrl`,
`activeEpgUrl`'s fallback to the input for the one case that has no record
(kept, and the fixture records it), and `Service.reconcile`, the plan's only
consumer. The `cloneState` whitelist coerced a non-string key where
`Model.activeKeyText` had been fixed -- the same site one function away -- and is
fixed with it. Nothing the two sweeps reached identifies a fact by a
credential, and the scope of that claim is stated rather than implied: a read
over the one `updateEntryInline` call site, the state and cache writers, the
helper's file-name derivations and the runtime directory's contents. It is not
a proof of absence.

**What this lane did not verify.** This is the docs lane; it holds no display.
It has not run the shell, the migration, a downgrade or an upgrade; it cites
the lead's 2026-10-09 mode measurements, lane A's node and FileView-probe
evidence and lane B's transcripts (2026-10-11) rather than restating them as
its own, and the one measurement it took itself is the host's
`updateEntryInline` run in node over the host's own source
(`OMARCHY-PLUGIN-CONTRACT.md`). The harness instrument that observes the
migration live landed under R6 (lane-key-r2, carried by lane-key-s2), and the
live counts quoted in this entry are read from the transcripts lane B's report
names, not re-run here. Two live halves remain UNVERIFIED by anyone: the
downgrade-then-upgrade round trip, and an unwritable state directory at
start-up (R11's `drop`).

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
(`logoSummaryNames` in the model), so the field is inert there. Proved by
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
resolves every `Model.X` citation against this tree's model (every part `Model.mjs` names, since D-REL-5),
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
  `Guide.qml` and model until it is. That service invokes the helper by
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
  dimensions and not the bytes. Recorded, not fixed -- except for a PNG,
  which since D-LOGO-13 is read under the cap plus one and swept (below).
**The siblings, asked before closing (engineering rule 15).** Every `Image`
in the four shipped QML files: two, both fed by an announced name, and no
`AnimatedImage`, `icon.source` or SVG anywhere (the lead's census). Every
other number the helper enforces that could bound the wrong axis: one found,
D-LOGO-12. A second axis this round did not ask about -- what a file
carries BESIDE its pixels, which the byte cap bounds only compressed -- was
raised from outside against 0.13.6 (D-LOGO-13, below). Every other place
provider bytes are decoded in the shell: none; playlist and EPG bytes are
parsed in the helper and arrive as JSON.

**D-LOGO-13: the canonical PNG (fixed on `dev` 2026-10-15, the owner's
"option 1" of 2026-10-13).** Raised by the same maintainer against the
shipped 0.13.6 on omacom/omarchy-plugin-marketplace#11315: `write_logo`
proved a logo's type, magic and header and then cached the provider's bytes
unchanged, and a PNG carries more than pixels. zTXt, iTXt and iCCP are
compressed; libpng inflates them in `png_read_info`, before a row is decoded
and whatever `sourceSize` says; and Qt keeps the result -- `qpnghandler.cpp`
at v6.11.2 calls `png_get_text` after `png_read_info` and again after
`png_read_end`, and turns `png_get_iCCP` into a `QColorSpace`. libpng's only
ceiling is its compiled default (libpng(3), and `pnglibconf.h` here:
`PNG_USER_CHUNK_MALLOC_MAX` 8,000,000 bytes for any chunk but IDAT, inflated;
`PNG_USER_CHUNK_CACHE_MAX` 1,000 stored text and unknown chunks, applied
separately to the info and end structs), and Qt sets neither limit: neither
setter is in QtGui's import table or the handler's source. All of that is
READ, from the 6.11.2 and 1.6.58 sources and the installed headers and
binaries; none of it was measured, by decision -- the fix is judged by what
it keeps and drops, which ordinary images prove completely.
**What changed.** `canonical_png` walks the chunk list and inflates nothing.
It keeps IHDR, PLTE, IDAT and IEND, and tRNS, gAMA, cHRM and sRGB when each
has its spec length (4, 32 and 1 bytes; tRNS 2 for greyscale, 6 for
truecolour, 1 to the palette's size for a palette image, never with alpha),
is the first of its kind to be kept, and is in its place (before IDAT; gAMA, cHRM and
sRGB before PLTE too). A colour chunk that fails any of those is dropped,
because libpng ignores it as well. Everything else goes: tEXt, zTXt, iTXt,
iCCP, eXIf, pHYs, tIME, bKGD, APNG's acTL, fcTL and fdAT, private chunks.
None of them changes a pixel the guide draws: Qt applies a file's gamma
only when the reader is given one (default 0.0), and Qt Quick converts
colours only when an `Image` sets `colorSpace`, which none in the guide does
(`qpnghandler.cpp` and `qquickpixmapcache.cpp` at v6.11.2).
Kept chunks are copied whole, so the IDAT bytes and the pixels are the
provider's and a canonical file comes back byte for byte. It refuses
(None) a file whose walk cannot be proved: a bad CRC on any chunk, dropped
ones included; a chunk past the end or no IEND; anything after IEND; more
than 4,096 chunks (`MAX_PNG_CHUNKS`); IHDR not first, not 13 bytes or
repeated; no IDAT or IDAT split by another chunk; a second, late or
mis-sized PLTE; any other critical chunk, which libpng refuses too.
`write_logo` runs it after the D-LOGO-11 bound and before
`ensure_private_dir`, so a refusal -- `logo_chunks`, a host and no URL,
counted under `refusedOnPolicy` -- still creates nothing on disk. The
cached-file branch of `logos --fetch` asks `canonical_logo_file` after
`logo_file_within_bounds`: a canonical PNG (or another type) is announced as
it stands, a PNG with other chunks is rewritten in place through
`write_bytes_atomic` (0600) and then announced, counted in a new summary
field, `rewritten`, as well as in `cached`, and one that cannot be walked is
swept and falls through to the fetch. That read stops at the byte cap plus
one, so a cached PNG over 256 KiB can never walk to its IEND and is swept:
the window the D-LOGO-11 residuals above record ("a 300 KiB file with a
sound 64x64 header answers True") is closed for PNG and left as it was for
the other three types. Measured cost (2026-10-15, 5,000 cached 220x120 PNG
logos of about 10 KB, page cache warm, medians of five): `logos --fetch`
725-735 ms at e6abcc5, 815-872 ms now; the difference is the second read and
the CRC pass, which is about 9.5 us per 10 KB on this zlib. The read moved
from a buffered file object to `os.read`, which halves the read (about 30
to 14 us a file); with the buffered read it was 1,003-1,069 ms. The
one-time rewrite of 5,000 files cost 1,626 ms. **Why JPEG, GIF and WEBP are untouched**, read in the same Qt
sources: the JPEG handler saves COM, APP1 and APP2 at their raw length
(`jpeg_save_markers(..., 0xFFFF)`), uses EXIF for the orientation tag only
and concatenates ICC segments, so nothing is inflated; the GIF handler is
Qt's own decoder, its comment-extension case is compiled out and every
extension but NETSCAPE looping is skipped; the WEBP handler reads the ICCP
chunk as raw bytes and nothing else ("consider parsing EXIF and/or XMP" is a
`###` note). In all three what Qt keeps is bounded by the file's own bytes.
**Verified by** `tests/test_logo_chunks.py` (27 tests over ordinary 2x2
images carrying a short Comment, a short iTXt and zTXt, an iCCP the size of
a plain sRGB profile, eXIf and a private chunk): on e6abcc5 23 of the 27 are
red -- 18 of them errors, the calls to a function that did not exist yet --
and the four controls green; every one of 37 deliberate breaks of
the shipping code (each refusal, each keep rule, the rewrite, the count, the
byte-capped read) reddens at least one; and the 27th observes the sink, Qt
6.11.2's own reader in a QML `Image` offscreen, drawing the canonical file
and the original identically for an RGBA, a palette and a greyscale image,
red when the canonical form drops the second IDAT or the tRNS.
`logo-scenario.sh check-tree` reads 33 / 0 unchanged: its corpus PNGs are
already canonical. **Residuals.** A picture a running shell has already
decoded stays decoded until the restart; the rewrite is of the file, not of
Qt's pixmap cache. And IDAT is still a compressed stream: libpng inflates
it into the rows the D-LOGO-11 dimensions bound, and inflates any data past
the last row into a fixed stack buffer and discards it (`png_read_IDAT_data`
with no output, 1.6.58), so the cost of such trailing data is CPU on Qt's
image-loading thread, not memory; it is read, not measured.

**D-LOGO-14: a GIF canvas is an edge, not a size (fixed on `dev`
2026-10-16).** Raised by the same maintainer against the shipped 0.14.1 on
omacom/omarchy-plugin-marketplace#11892: `_gif_dimensions` took the larger
of the logical screen and each frame's WIDTH and HEIGHT, ignored each frame's
left and top, and accepted a zero logical screen. Qt's handler
(`qgifhandler.cpp`, identical at v6.11.2 and on qtbase's `dev`, read and not
run) sizes a screen side that is zero from the first image descriptor's
`newleft + newwidth` and `newtop + newheight`, then allocates that canvas,
before anything is scaled; its own limits are `width * height < 16384^2`
pixels and the 256 MiB allocation limit, so a 1x1 frame at 8190,8190 under a
0x0 screen is an 8191x8191 ARGB canvas just under both, which the helper had
read as 1x1. A later frame does not enlarge the canvas (Qt clips it to
`swidth`/`sheight`), and the reader does not rely on that. **What changed.**
The canvas the reader returns is the largest of the logical screen and every
frame's right edge (left + width) and bottom edge (top + height), over the
whole walk to the trailer; a logical screen with a zero side, or a frame
with one, makes the header unreadable, which the bound already refuses
(R4). The existing bounds then apply to that canvas unchanged, at
`write_logo` and in the cached-file sweep alike. **Verified by**
`GifCanvasTest` in `tests/test_logo_dimensions.py`, seven tests over GIFs of
35 to 65 bytes built in the test: on bf075ca six red and the control green,
on the fix seven green, and each of six one-decision mutants (no left
offset, no top offset, a zero screen allowed, a zero screen height allowed,
a zero frame allowed, a zero frame height allowed) reddens at least one.
Nothing was decoded and nothing measured. **The other three types, read for
the same shape** (a declared size a decoder may enlarge from another field):
none has one. PNG: Qt allocates from `png_get_IHDR`, and the canonical form
keeps no other chunk that names a size. JPEG: libjpeg-turbo 3.2.0's
`get_sof` refuses a zero height (the DNL form) and a second SOF, and Qt's
`scale_num` is `qBound(1, qCeil(8/f), 8)` over a denominator of 8, so libjpeg
is never asked to enlarge. WEBP: libwebp 1.6.0's demuxer refuses a frame
whose offset plus size passes the VP8X canvas and requires a still frame to
equal it (`CheckFrameBounds`), Qt allocates the canvas and each frame from
the demuxer's numbers, and the VP8 header's two scale bits are stored and
never applied (`vp8_dec.c`). The searches are in `docs/QA-RESULTS.md`.

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
- `state.json` exists but cannot be read, or does not parse (2026-10-13,
  D-SINK-19 round 12, R22a): nothing is written to it for the session, the
  bar entry is left as it is, and one critical notification
  (`Saved sources not loaded`, `Model.stateUnreadableNotice`) names the file
  and what to do [2026-10-20, R27e: titled `Saving has stopped` when the
  block begins after the sources loaded, and the body says changes made now
  "are not saved until the file can be read again"; R27a adds the reason
  `read-timeout`, a read before a save that did not answer twice]
  [2026-10-20, R28e and R28a: the body says changes made now `are not
  kept` at a start, and mid-session names the ways back on which they are
  kept or dropped (`UX-SOURCES.md` 5.10 item 1); `read-timeout` is
  withdrawn -- a read that does not answer keeps the change held and is
  asked again, told once as `Saving is waiting`] [2026-10-20, R29a: that
  hold and its notice are withdrawn as well; a read that does not answer
  within 2 s lets its save go ahead without it, counted and logged, as on
  0.14.2, and nothing is told (section 5, the round-19 amendment)]. It used to be read as an empty state and saved over, which
  is how a start could erase every source (section 5, as amended).
  [Round 13, 2026-10-13 (R23): the guide's body is then that notice's own
  words, never the first-run form, and every refusal says the no-write
  reason; a directory, a FIFO or a socket at the path is refused at once and
  left untouched; and a start-up check that does not answer within 15 s is
  stopped, reaped, and treated as this case with reason `init-timeout`.]

Performance budget (10k channels):

| Item | Budget | How |
|---|---|---|
| Overlay open | < 150 ms | keepLoaded window; `rebuildDisplay` appends at most 300 rows; channels already parsed in memory. **Measured 2026-10-20 (R28d, D-PERF-1's async instrument as re-made, `scripts/dev-harness/open-scenario.sh`: the clock stops at the first frame whose presenting view DRAWS a whole screen, 10 rows or 16 tiles, counting only delegates that are shown, intersect its visible area and -- since R29e the same day -- are painted at an effective opacity above 0, each delegate's own times every ancestor's up to the window; not covered, so not claimed: an item stacked over the view, an ancestor's clip, a layer or shader effect, and a fade's strength) at 10,000 channels in the cage's floating window, at a light load (a one-minute load average of 1.40 on 4 cores as the run started, 1.4-3.5 over it as the round-19 record gives it): met by every open after the first (warm, realised median 34 ms list / 32 ms wall on R29e's instrument, max 45 / 39, `open-20261020-192446-2690236`; R28d's read 33 / 31, max 41), NOT met by the first open of a session (cold, realised median 547 ms list / 547 ms wall on R29e's; R28d's 548 / 534), about 440 ms of which a 40-channel control shows too (the first show of the window in the cage). Under heavy load the budget is NOT met: at a one-minute load average of 10.37 as the run started (round 3's live review, `open-20261020-210029-2957576`, the same code) the warm median still is (120 ms list / 126 ms wall, so L6 and W6 pass) but not every warm open (max 158 / 217 ms), and the cold open is a median of 2,354 ms list / 2,291 ms wall, about four times the light-load figure. On Hyprland's layer-shell surface the cold figure is UNVERIFIED. R27f's figures the same day (546 / 580 cold, 34 / 32 warm) counted delegates built off screen as well and trailed the drawn screen. Every open figure recorded before 2026-10-20 came from `openMs`, whose clock stops in the turn of the summon, before the first frame (D-PERF-1); it did lay out the on-screen delegates (10 rows, as drawn), so what it missed is the frames up to the first drawn screen. A guide that faded its views in would have passed R28d's instrument (round 2's review: 30 / 0 under a 300 ms opacity-0 mutation); R29e's reads it red (`spikes/open-mutations/opacity-fade.patch`, L6 and W6 at a warm median of 338 / 341 ms). The round-18 and round-19 rulings in `ARCHITECTURE-SOURCES.md` have the tables** |
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
   Nor may an XMLTV feed define text for the parser to expand: ElementTree
   expands the entities a document declares in its internal subset, and the
   64 MiB cap bounds only the input, so `EntityRefusingReader` runs the
   prolog through its own expat parser, refuses any entity declaration,
   general or parameter, and hands the parse nothing until that parser has
   reached the root's start tag (D-EPG-6; XMLTV declares none). Verified by
   calling `parse_xmltv` and the `epg` verb over small documents, plain and
   gzip.
3. Stream URLs are allow-listed by scheme (`http https rtmp rtmps rtsp udp rtp
   mms mmsh srt`); `file:`, `plugin:`, `javascript:` and option-looking lines
   (`-...`) are dropped and counted.
4. Source URLs: `http`, `https`, `file` or absolute path only; local files must
   resolve to a regular file outside `/proc`, `/sys`, `/dev`; 64 MB cap;
   20 s network timeout; no redirects to other schemes (urllib default).
5. No writes inside the plugin directory; caches and state are 0700/0600.
   [2026-10-14, D-SINK-19 round 14, R24b: one stated exception to "the
   state directory is 0700". When the user has made `state.json` a symlink to
   a regular file elsewhere (a dotfiles folder), the helper's `state` verbs
   write THROUGH it: the temporary file is still created 0600 with `O_EXCL`
   and renamed onto the target, but the target's folder is the user's and is
   neither created nor chmod-ed, so whatever mode the user gave it stands.
   The service's own FileView save already wrote through such a link
   (measured, spike set `r24` sequence V). A link that dangles or leads to
   anything but a regular file is refused and nothing is written.]
   [2026-10-14, round 15: that folder's mode can refuse the write, and the
   refusal is a sentence, `state_unwritable`, never a traceback (D-SRC-34).
   And the opposite case is NOT an exception: when the user has made the
   state FOLDER itself a symlink (to a folder elsewhere), the folder it leads
   to IS the plugin's state folder, so `state init` and every writing verb
   make it 0700 through the link, as they do the folder they create
   (measured, `scripts/dev-harness/spikes/folder-link/RESULT-2026-10-14.txt`:
   0755 and 0500 both come out 0700, the link left a link; the same for a
   linked runtime folder under `player stop` (and, measured by the round-15
   independent check with a stand-in mpv, `player start`). Of the shell's
   own calls only `cache migrate` makes a linked cache folder 0700 (`failed
   mark` makes 0700 the per-source folder it is given, and a hand-run verb
   without `--cache-dir` the cache folder itself), and an install already at
   cache layout 2 never runs it again, so a linked cache folder keeps its
   own mode after the upgrade; the README says so [corrected at the round-15
   integration, D-DOC-15 and D-DOC-18: this said "the same for a linked
   cache or runtime folder" unqualified]). Decided by R24b's principle -- never
   change what the user's link points at without saying so -- and said in the
   README. A folder link that dangles or leads to anything but a folder is
   refused and nothing is written (R25c).]
   [2026-10-16, round 16, R26a (D-SINK-21): "state is 0600" was not kept by
   the service's own save. A FileView save that CREATES its file creates it
   0666 & ~umask -- 0644 at the shell's umask 022 -- whatever `atomicWrites`
   says (measured); the helper writes 0600, and its start-up `state init`
   repairs the mode once per start, but the service's own save is the
   view's. So a state-folder link
   re-pointed mid-session at an empty folder, or a `state.json` link
   re-pointed at a file that did not exist yet, got a 0644 `state.json`
   holding every source URL at the next save, unnoticed (measured on
   1c88877 and 0.13.6; readable by another account only where the folders
   above it can be entered -- not inside this machine's 0700 home). Since
   R26a every save reads `state.json` first and a load that finds nothing
   refuses the save (the R22 `absent` mode), so the service never asks the
   view to create the file -- outside three windows of milliseconds (a
   save asked while our previous write is in flight skips its read; a
   re-point landing between the read's load and the write; the 2 s
   watchdog firing), in which it still does (section 5's round-16
   amendment, "What remains"; lane-clean-f1). [2026-10-20, round 17, R27a:
   one window remains, the re-point between the read's load and the write;
   the other two are closed (section 5's round-17 amendment).] [2026-10-20,
   round 19, R29a: two remain -- the re-point, and the 2 s watchdog's save
   without its read, open again as on 0.14.2; only the save asked while our
   write is in flight stays closed (section 5's round-19 amendment).] A save over an existing file keeps that file's
   mode, so a re-pointed folder holding a 0644 `state.json` keeps 0644
   until the next start makes it 0600 (measured by the sink lane through a
   restart).]
6. No symlinks in the repo (validator rejects them); no sudo, no pkexec, no
   network from QML.
7. Credentials: never printed; `sourceHost` instead of URL in caches and
   errors. README warns that `state.json` and the cache contain them (since
   D-SINK-19 the two files the plugin owns, counted in the README), that
   `shell.json` only has one passing through it, and
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
    whatever mode it finds. Since D-SINK-19 the plugin writes NO secret into
    that container -- the entry carries the active source's key -- and this
    standard is kept in full for the two routes a URL still takes into it
    (the user's own `omarchy bar set`, and an install upgrading into this
    release), with the gate asked of the entry about to be written
    (`Model.entryShieldDecision`) so that it fires again the moment a
    URL-bearing key is written by anyone. So the mode of that one file is
    checked and
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
    "Every axis" was written about the header's dimensions, and a PNG has a
    second: what it carries beside its pixels, some of it compressed and
    inflated by libpng while it reads the header, which the byte cap bounds
    only compressed (D-LOGO-13). So a PNG is cached only in a canonical form
    holding IHDR, PLTE, IDAT, IEND and the four small colour chunks at their
    spec lengths, its IDAT bytes untouched, and a PNG whose chunk list cannot
    be walked is not cached at all; a cached PNG is announced only once it is
    canonical. Verified by calling `canonical_png`, `write_logo` and `logos
    --fetch` over ordinary images, and by observing Qt draw the canonical
    file and the original identically.
    And a declared size is not the only number a decoder sizes from: Qt's GIF
    handler builds a zero logical screen from the first frame's left+width
    and top+height (D-LOGO-14). So a GIF's canvas is the largest of the
    logical screen and every frame's right and bottom edge, and a zero
    screen or a zero frame is refused. Verified by calling `logo_dimensions`,
    `write_logo` and `logo_file_within_bounds` over GIFs of a few dozen bytes
    built in the test.
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

The model, `Model.mjs` and `model/*.mjs` (ES modules since D-REL-5,
2026-10-12; until then the one-file `Model.js`):

- `Model.mjs` is the public surface and nothing else: a header comment and
  `export { ... } from "./model/<part>.mjs"` lines naming every public
  function and constant, ALL of it generated by `scripts/split-model.mjs`
  (the header since round 2 of D-REL-5; until then it was the one-file
  model's header carried over, which said "No ES module syntax" and
  `import "Model.js" as Model` on the day both stopped being true). The code lives in the parts under `model/`,
  one per domain. QML imports `Model.mjs` (`import "Model.mjs" as Model`), so
  every `Model.X` call site and every `Model.X` citation is unchanged.
- `scripts/split-model.mjs` cut the parts out of the one-file `Model.js` and
  is the judge of them afterwards: `scripts/check.sh` runs its `--check`, and
  `--relink` rewrites a part's generated import and export lines after an
  edit adds a call across parts. A new part is a line in
  `scripts/model-parts.json`, a line in `Model.mjs` (relink writes it) and an
  entry in `ALLOWLIST` in `scripts/release.py`; the gate is red until all
  three agree.
- Pure functions, `var`/`function` declarations at the top level, no
  Quickshell or Qt globals (`Qt.md5` etc. are not available in node).
- **Init locality.** A top-level initializer reads only declarations of its
  own part, directly or through a same-part function it calls. Parts import
  each other in cycles, and an initializer that reads another part's binding
  across a cycle gets `undefined`, silently -- measured on 2026-10-12 under
  node, qmltestrunner and Quickshell in a nested cage. References across
  parts live in function bodies, which run after every part has evaluated.
- **Declared first.** A `var` sits above every function of its own part that
  names it. A classic script never cared, and a module does: Quickshell logs
  `qt.qml.usedbeforedeclared`, with the module's file:// URL, on every load
  for each such use (measured 2026-10-12, two of them at the cut). The script
  refuses the shape and never reorders code; the remedy is the manifest,
  putting the `var` in another part so it is an import.
- **No shared mutable state.** No code assigns to or mutates a top-level
  binding after evaluation. One module instance is shared by every component
  that imports it, where a classic script was copied per component, so a
  write would leak between components; an imported binding is read-only
  anyway.
- Never mutate inputs; return new arrays/objects.
- Every function tolerates `null`/`undefined`.
- Any text-normalization or id change is made in the helper and in the model
  together, with the shared vectors in both test suites updated.
- Every shipped file stays at or under 448 KiB: `release.py check` enforces
  it with 64 KiB of margin below the marketplace scanner's 512 KiB per-file
  limit, which the one-file model crossed at 0.13.5 (D-REL-5).
- Anything in Python or shell that needs the model's FILES reads the part
  list from `Model.mjs`: `scripts/model_files.py` in Python, `qa_model_files`
  in `scripts/qa-lib.sh` in shell. Never a second list.

**The helper's parts (D-REL-7).** `bin/omarchy-iptv` is a stub that makes the
process non-dumpable (D-SINK-9) and then compiles `bin/helper/NN-*.py`, in
the order its `HELPER_PARTS` tuple lists -- each entry the part's name, its
length and its CRC-32 -- into its own namespace with
`exec(compile(source, path, "exec", dont_inherit=True), namespace)`. One
namespace is the design, not a shortcut (docs/HELPER-SPLIT.md weighs it
against real modules): the parts are one module's globals in one definition
order, so a function in any part sees every name, and a test that replaces
`helper.fetch_logo` replaces it for every caller. The rules that follow:
- A part's top-level code may use names from the parts BEFORE it, as in one
  file; a later part's names exist only inside function bodies that run
  after loading. A violation is a NameError the first time anything loads
  the helper, which every helper test does.
- Each part opens with the generated header (what it is, and its own
  `from __future__ import annotations`, which binds one compilation unit).
  The stub's entry for it, `("05-ipc-logos.py", 42179, 0x848354c6),`, is
  the length and CRC-32 of the part's text with CRLF read as LF, and the
  stub recomputes both before any part runs: a part cut off, changed, or
  from another release does not match. The entry lives in the STUB, not in
  the part (the follow-up to the split's review, P2a), because an update
  writes the parts before the stub: an old stub then refuses every new part
  rather than run two releases at once. CRLF is read as LF because `git
  clone` and `git merge` honour a user's `core.autocrlf=true` and `main`
  ships no `.gitattributes`; Python compiles such a part unchanged, so it is
  not damage (P1 of that review: an entry over the raw bytes refused every
  verb on such a checkout). A checksum, not a digest: whoever can rewrite a
  part can rewrite the stub beside it, so it detects damage and a mix and
  cannot authenticate. Every edit to a part therefore changes the stub:
  `split-helper.py --seal` rewrites the entries after an ordinary edit,
  and `--check` is red until it has.
- The loader is generated text: `scripts/split-helper.py --check` (the gate)
  goes red on an edit to it, or on the loader anywhere but directly after the
  shield. A new part is a file with the header, an entry added to the tuple
  in the generated shape (`    ("12-x.py", 1, 0x00000000),`, then `--seal`
  fills in its length and CRC-32 and regenerates the loader), and its path
  added to `ALLOWLIST`, which `release.py check` cross-checks against the
  tuple both ways.
- The loader takes no input -- fixed names, its own directory, found
  through `realpath(__file__)` so a symlink to the stub works as the one file
  did -- and `compile()` writes no bytecode, so the plugin directory stays
  read-only at runtime (constraint 4).
- **All parts are checked before any runs** (the split's review, P2). A part
  missing, unreadable, not a regular file (each is opened without blocking,
  so a FIFO in a part's place cannot stall the start), empty, not matching
  its entry, not text, or not compiling, or any entry in `bin/helper/` the
  tuple does not name (a name starting with `.` excepted: an editor's swap
  file cannot be a part, and `--check` exempts the same names), ends the run
  before a single part executes, so no verb can run or write with half a
  helper, or with parts of two releases. The
  refusal is one JSON object on stdout, code `helper_damaged` with the
  part's name and no `kind` (the caller's stands), its message as the one
  stderr line, exit 1. `Model.helperDamagedReason` is its sentence
  ("reinstall the plugin", naming only a well-shaped part) and it routes as
  the empty stdout it replaced, `no_output`: never a health strike
  (`Model.helperCannotTell`), and `unknown` on the play branch, from
  `Model.playFailureVerdict` through `PLAY_UNREADABLE` (`Model.playFork`
  decides start, queue or zap from the player state and never sees it).
  `tests/fixtures/helper-damaged.json` joins the stub's real replies to
  the mapping. During an in-place update git rewrites each changed part in
  place (unlink, create, write) and every part before the stub, so a helper
  spawned then meets a part missing, empty, cut off or of the next release
  beside the old stub, and is refused; while the stub itself is rewritten
  it meets no stub, an empty one or a partial one, none of which runs a
  verb (docs/HELPER-SPLIT.md, "What an in-place update can meet", has the
  measurements step by step).
- **Behaviour identical, bytecode not.** CPython 3.14 compiles a call on a
  module bound by an import in ANOTHER compilation unit as `LOAD_ATTR` then
  `PUSH_NULL` rather than a method load: 248 call sites, because the
  imports are in `01-core.py`. Same behaviour for a module object, and
  measured as such: a 129-step corpus of every verb the service runs is
  byte for byte the one-file helper's.
- **The marketplace scanner reads the parts as `.py`.** The one-file helper
  was an extensionless executable, read under the baseline's runtime rules;
  the parts are 100644 `.py` and read under its launcher-literal rules
  instead. The outcome is the same, measured with an independent port of
  the baseline: `passed`, no findings, no capabilities, with the parts as
  shipped and re-marked executable.
- Anything that needs the helper's FILES reads the tuple from the stub:
  `scripts/helper_files.py` in Python (by `ast`, never by running the stub),
  `qa_helper_parts` in shell. A pin that used to read the one file reads
  `helper_files.helper_source`, the stub and every part in order.
- `split-helper.py --verify --from-git 1ecfd9d` on the commit that cut it
  (b80c7ff, on `lane-split-s1`) proves that helper is 1ecfd9d's one file --
  0.14.2's, 447,660 bytes -- byte for byte; edits since then, the stub's
  shield docstring first among them, are ordinary edits, and the parts are
  never cut again. Since the entries moved into the stub (2026-10-17, the
  follow-up's P2a) `--verify --from-git 85206f2` reports two differences
  and names them: "bin/omarchy-iptv differs from the cut (in its head and
  loader, at the entry for 01-core.py only)" and "bin/helper/01-core.py
  differs from the cut (from line 38)". The head differs by that docstring;
  01-core.py by `_manifest_version`, which now resolves the manifest
  through `realpath` as the loader resolves the parts, so `--version`
  through a symlink to the stub prints the plugin's version; the loader by
  that part's entry. The other ten parts and the tail are the cut's byte for
  byte.

**What the cut dropped, recorded (D-REL-5 round 2, R4).** The one-file
`Model.js` opened with the header below and closed with a CommonJS export
guard that carried nine comment lines. Neither survives the cut: the
aggregator's header is generated, and the generated export lines replace the
guard. `split-model.mjs --write` and `--verify` read every dropped line out
of the monolith they cut and go red on any that is not a whole line of THIS
section, so a later monolith with a new guard comment -- the D-SINK-19
chain's, at integration -- cannot lose it silently. Record it here, or move
what it says next to the code it is about.

The header, verbatim as it stood at `dev` ab545f4 (the last commit that had
the file). Still true of the parts: no QML, no I/O, no timers, no Quickshell
APIs; `var` and `function` at the top level; safe on null and undefined;
normalization byte-compatible with the helper, pinned by shared vectors;
ASCII with `\uXXXX` escapes; the section 12 rulings it lists. No longer true:
"No ES module syntax" (the parts are ES modules), and the two load lines,
which now name `Model.mjs`.

```
// Model.js -- pure logic for io.github.rmcdavid.iptv.
//
// Rules (see ARCHITECTURE.md (dev branch), "Coding standards"):
//   - No QML, no I/O, no timers, no Quickshell APIs. Inputs in, values out.
//   - ES5-style functions and `var`: this file is loaded by the QML engine
//     (`import "Model.js" as Model`) and by node (`require("./Model.js")`).
//     No ES module syntax, no top-level `const`/`let` exports.
//   - Every function must be safe on null/undefined input.
//   - Text normalization here MUST stay byte-for-byte compatible with
//     `normalize_text` / `search_key` / `fnv1a32` in bin/omarchy-iptv; the
//     helper writes searchKey/id into channels.json and the guide only
//     normalizes the query. Model.test.js (dev branch tests) and test_playlist.py (dev branch tests)
//     pin the shared vectors.
//   - ASCII only. Nerd Font glyphs and typographic characters are written
//     as \uXXXX escapes (surrogate pairs for the supplementary plane).
//
// Rulings applied (ARCHITECTURE.md (dev branch) section 12): R2 settings clamps,
// R3 result cap 200, R4 search key + ranking tiers, R5 first-group placement
// and recents on the play command, R7 bar glyphs, R8 model fields, R9 zap
// ring, R11 session-only failedAt, R12 notification privacy.
```

The comment lines inside the export guard, each a label over the exports
that followed it. Seven are section labels whose sections are the parts
now; the two-line D-STATE-1 note says why `playedRecord` (in `model/state.mjs`) is
public at all, and it stays true: the shared fixture calls the record rule
directly, not only through `parseState`.

```
// ---- channel numbers (M2-03)
// D-SINK-18
// D-SINK-16: the adopted player's two readings and the verdict over them
// ---- detached player (M2-02)
// M5-01 live rewind
// ---- picture in picture (M2-05)
// D-STATE-1: exported so the shared fixture can call the record rule
// directly, not only through parseState.
// ---- sources (M2-01)
```

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
   relying on `onFileChanged`. [2026-10-13, D-SINK-19 round 13 (R23g):
   measured both ways and not settled. Lane A's FileView spike
   (`scripts/dev-harness/spikes/filewatch/`) and the real service in a cage
   saw the watch survive every rename, own save, chmod and restart; the
   round-9 and round-12 lenses saw a helper rename raise no reload
   (D-SRC-19). Section 5's round-13 amendment.] [2026-10-14, round 14: the
   difference was the state DIRECTORY at the first load. A FileView loaded
   while its directory did not exist watches nothing all session; one
   explicit `reload()` once the directory exists re-arms it, and the
   service now makes that call after the start-up check (R24c, measured in
   the same spike, set `r24`). A rename or an in-place write is otherwise
   seen. Section 5's round-14 amendment.] [2026-10-14, round 15: "a rename
   is seen" holds for a rename onto the watched file's own path. With
   `state.json` a symlink, a rename or any replacement at the LINK's path is
   never seen, nor anything after it (R25e, D-SRC-29; section 5's round-15
   amendment); filed, and stated in the README.] [2026-10-16, round 16
   (R26a): the service now reloads `stateFile` before every save, so such a
   replacement is decided at the next save and the watch is re-armed by
   that reload; a periodic reload is refused (R26d). Section 5's round-16
   amendment.]
2. FileView writes into a missing directory: `mkdirProc` creates the three
   directories at service start (argv `mkdir -p -m 700`). Do not call
   `saveState()` before it has run (first user action is always later). [2026-10-14, round 14: and a FileView
   that first loaded while its directory was missing does not WATCH the file
   once the directory exists -- not even the init's creation of it -- until
   it is reloaded explicitly (R24c, measured); the service reloads
   `stateFile` once after the start-up check for exactly this. Since R24d one
   15 s watchdog bounds `mkdirProc` and the init together.]
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
    (`iterparse`) and cap at 64 MB compressed or bail with `too_large`. The
    cap bounds input, not expansion, so a feed that declares an entity is
    refused (D-EPG-6, security standard 2).
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
  [2026-10-13, D-SINK-19 round 12 (R22a): the verb also reports what it
  found at the path before it touched anything (`found`), which the service
  reads to tell a fresh install from a directory it cannot search, and it
  never rewrites a file that exists, whatever it holds.] [Round 13 (R23b,
  R23d): it never blocks on the path (a non-blocking open checked by
  `fstat`), and its 0600 repair touches only a regular file -- a directory at
  the path used to be made 0600, unsearchable; the service bounds it with a
  15 s watchdog (R23c).]
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
