# Omarchy IPTV -- Architecture: Sources (M2 lane 1)

Owner: Software Architect. Status: v0.1, governs M2-01 (docs/M2-SOURCES.md
locked decisions 1-7, stories S1-S8). Companion documents: docs/ARCHITECTURE.md
(sections 3, 5, 6, 8, 12 stay in force; this document only adds to them),
docs/SECURITY-REVIEW.md (the bar the new input surface must meet),
docs/UX-SOURCES.md (designer, written in parallel; authoritative for
interaction and visuals -- everything below tagged [UX-ASSUMPTION] is a guess
the designer may overrule as long as the Service/Model contracts hold).

Machine of record: Omarchy 4.0.3, Quickshell 0.3.1, Qt 6.11.2, Python
3.14.7, wl-clipboard 2.3.0, `main` at 765e2df (v0.1.0 installed and live).
Line numbers refer to `/usr/share/omarchy/shell/shell.qml` unless another
file is named; plugin files are cited at 765e2df. Every host claim was read
from the live install; the FileView claims in section 9 were verified with a
window-less scratch Quickshell instance (commands in appendix B). Nothing
under ~/.config or /usr/share/omarchy was modified.

## 0. Summary

- The active source keeps living on the plugin's `shell.json` entry
  (`playlistUrl`, `epgUrl`), written from QML through
  `shell.updateEntryInline` and observed through `shell.barConfig` exactly as
  today. The history of sources lives in `state.json` (schema version 2,
  still 0600), one record per normalized playlist URL.
- A source is identified by its normalized playlist URL; its cache directory
  is `~/.cache/omarchy-iptv/sources/<key>/` where `key` is `fnv1a32(url)`
  (8 hex digits, suffixed `-2`, `-3` on the theoretical collision). The five
  existing file names live unchanged inside that directory, so the helper
  only needs the `--cache-dir` it already has.
- Switching = one `updateEntryInline` (synchronous in-process, line 112) +
  rebinding the four cache `FileView` paths (auto reload, verified) + the
  guide's existing rebuild. Warm 10k-channel switch is ~100-130 ms in the
  QML engine, inside the 150 ms budget; a background refresh follows only
  when the cache is older than `refreshMinutes`.
- Adding a source fetches into its own directory first and commits to
  `shell.json` only on success (S8), so a bad URL never displaces a working
  source. Removing one deletes its directory through a new helper verb.
- The Sources screen never reads playlist content: it renders state records
  (label, host, counts) only. URLs are visible in the edit field alone,
  query values masked until revealed; no URL reaches lists, logs, IPC,
  notifications, or helper stdout.

## 1. Decisions

| # | Decision | Options | Choice | Rationale (evidence) |
|---|---|---|---|---|
| D1 | Where the active source lives | (a) shell.json entry (today); (b) state.json `activeKey`; (c) both | **(a) unchanged: `playlistUrl` / `epgUrl` on the bar entry** (M2-SOURCES decision 1) | `updateEntryInline` replaces the entry with `{id} + settings` in a clone of `shellConfig`, then `persistShellConfig` sets `shellConfig = payload` synchronously and writes the file with an atomic `FileView` (lines 1078-1112, 109-114, `userConfigFile` 134-141). `onShellConfigChanged` (67-71) fires `pluginsChanged()`, whose `Connections` handler calls `syncPluginApis()` (1053-1058), which reassigns `shellApi.barConfig` (879) -- the same object our `settings` binding already reads (`Service.qml:56`). So a write from QML propagates to the service in the same event loop turn, with no file watcher in the path, and `omarchy bar set` arrives through the identical chain (`omarchy-bar:361` -> IPC `setBarWidget` 1654-1663 -> `PluginRegistry.setBarWidget` -> `shellConfigMutator` -> `mutateShellConfig` 162-166 -> `persistShellConfig`). Storing an `activeKey` in state would create a second writer for one fact. |
| D2 | Where the history lives | (a) state.json v2; (b) extra keys on the shell.json entry; (c) a file in the plugin dir | **(a) `state.json` version 2, key `sources`** (M2-SOURCES decision 2) | Already 0600 in a 0700 dir (S-02 fixed: `state init`, `Service.qml:933-953`), already read and written by both QML (`Model.parseState`) and the helper (`normalize_state`, `bin/omarchy-iptv:1557-1576`). shell.json is host-owned and schema-declared (manifest `barWidget.schema`); the plugin dir is never written at runtime (PRODUCT.md decision 6). |
| D3 | Reconciling settings with history | (a) service observes settings; (b) helper scans shell.json; (c) guide-only | **(a) `Model.reconcileSources` runs in the service on state load and on every `playlistUrl` / `epgUrl` change** | The service already re-evaluates `settings` on every shell.json change (decision 7, `Service.qml:53-68`, `onPlaylistUrlChanged` 671-678). Reconcile is pure and idempotent: a URL already in history bumps `lastUsed` (only when the active key actually changed) and adopts a changed `epgUrl`; an unknown URL is added with a host-derived label and `origin: "cli"` (S5). No helper run, no extra IPC. |
| D4 | Source identity and key | identity: raw string / normalized URL; key: fnv1a32 / fnv1a64 / sha256[:16] | **Identity = normalized playlist URL (section 3.1). Key = `fnv1a32(normalized)`, 8 lowercase hex, suffixed `-2`, `-3`... if that key is already used by a different URL** | `fnv1a32` exists in both languages with pinned vectors (`Model.js:194-229`, `bin/omarchy-iptv:269-275`); channel ids already use it. sha256 in QML JS would mean ~60 new lines of hand-rolled hashing in `Model.js` (no `Qt.sha256` in node, no `crypto` in the Qt engine). 32 bits is enough because the key is only a directory name: identity is the URL string, lookups compare URLs, and the suffix rule makes a collision harmless. P(collision) at the 50-source cap is ~3e-7. |
| D5 | Per-source cache layout | (a) `<cacheDir>/sources/<key>/` with the existing names; (b) prefixed files in one dir; (c) key in the file names | **(a) `~/.cache/omarchy-iptv/sources/<key>/{channels.json, playlist-status.json, epg-now.json, epg-status.json, epg-window.txt}`** | The helper takes `--cache-dir` on `playlist`, `epg` and `play` (`bin/omarchy-iptv:1641,1647,1659`) and derives every file name from it, so no helper contract changes (section 5 shapes untouched). The service's four cache `FileView`s only need a different `path` prefix (`Service.qml:710-755`). Migration: a new helper verb `cache migrate` renames the legacy files from `<cacheDir>/` into `sources/<key>/` once (section 2.3). |
| D6 | Cache removal and pruning | (a) `rm -rf` argv from QML; (b) helper verb; (c) leave orphans | **(b) helper verbs `cache remove --key K` (on removal, S7) and `cache prune --keep K...` (once per service start; also ages EPG files of inactive sources)** | The helper validates the key (`^[0-9a-f]{8}(-[0-9]{1,3})?$`), builds the path with `os.path.join` under `sources/`, refuses anything whose realpath escapes, deletes only the five known file names plus temp files and then `rmdir`s -- no recursive delete of unknown content. QML never composes a delete. |
| D7 | What `switch` does | commit first vs fetch first | **Warm source (`fetchedAt > 0`): commit immediately, redraw from cache, refresh in the background if stale. Never-fetched source: probe first (D8)** | S3 asks for an instant redraw; a source with a cache can always be shown. Steps and budget in section 4.5. |
| D8 | Adding a source (S1, S8) | (a) write settings, let the normal refresh fail; (b) fetch into the new dir, commit on success | **(b) probe-then-commit through a dedicated `sourceProbeProc`** | S8: "a fetch failure keeps the previous active source and shows the reason". With (a) the failing URL would already be active and the guide would show the error empty state. With (b) the previous source keeps playing and refreshing; the new record stays in history with `fetchedAt: 0` and a session-only error so the user can edit and retry. Same code path for S1 (no previous source). |
| D9 | How paste reaches the field | (a) Qt clipboard through a `qs.Ui` `TextField`; (b) `Quickshell.clipboardText`; (c) `wl-paste` via `Process` argv | **(a) primary: real `TextField`s (locked decision 5) get Ctrl+V / Shift+Insert from `QQuickTextInput` (`QKeySequence::Paste`) through Qt's Wayland clipboard; (c) `["wl-paste", "--no-newline", "--type", "text"]` is the fallback behind one function** | Precedent in the shell: the network panel's passphrase `TextField`s sit on a layer-shell surface with keyboard focus (`Ui/KeyboardPanel.qml:98`, `plugins/panels/network/Panel.qml:1841-1870`) and users paste passphrases there; `Ui/TextField.qml:18` is a Qt Quick Controls `TextField`. Qt receives `wl_data_device.selection` when our surface has keyboard focus, which the guide holds exclusively while open (`Guide.qml:617`). Verified here: `wl-paste --list-types` works from a background process (wlr-data-control, no focus needed), so (c) is a reliable fallback; `Quickshell.clipboardText` (quickshell-core.qmltypes:998-1002) is the same Qt clipboard as (a) and is only useful for a synthetic field. The harness scenario H4 (section 8.4) verifies (a) on the live shell; if it pastes empty, Lane 1 flips `pasteViaProcess` to true. Either way the pasted text is data: sanitized by `Model.sanitizeInput` before it enters the field (section 6). |
| D10 | Xtream URL construction | build in QML / in helper | **`Model.xtreamUrls` (JS only; the helper never builds Xtream URLs)** | Rules in section 3.4: server normalized to `scheme://host[:port][/base]` (default `http://` when no scheme -- Xtream panels are plain http on :8080 far more often than not; documented), `get.php?username=U&password=P&type=m3u_plus&output=ts` and `xmltv.php?username=U&password=P`, values percent-encoded with the RFC 3986 unreserved set so node, the Qt engine and Python `quote(safe="")` agree. Saved as a normal source (`origin: "xtream"`); the password exists only inside the URL. |
| D11 | URL validation shared with the helper | duplicate rules / one spec | **One algorithm, `Model.validateSourceUrl` and helper `validate_source_url`, pinned by `tests/fixtures/source-urls.json` read by both suites; `resolve_source` calls the Python one** | The helper's `resolve_source` (`bin/omarchy-iptv:544-558`) already defines the accepted set (`~`/`/` paths, `http(s)://` with a host, `file://`); the JS side mirrors it and both gain the same two additions: a 2,048-character cap (`too_long`) and refusal of control characters (`bad_url`). The guide rejects inline (S8) with the same code the helper would return. |
| D12 | Masking for display | host only / mask query / mask all | **Lists: label + host (`Model.hostOf`). Edit field: `Model.maskUrl` = `scheme://[***@]host[:port]/path?name=***&...` with every query value masked except `type` and `output`; a reveal key shows the raw URL; paths shown as-is** | M2-SOURCES decision 4. Credentials of Xtream and most providers are query values or userinfo; parameter names and the path let the user recognise the URL. Local paths are the user's own filesystem. |
| D13 | Length caps | -- | **URL 2,048; label 64; Xtream server 512, username/password 256 each; state `sources` 50 records** | Provider URLs are 100-300 characters; 2,048 is the common practical URL cap and bounds argv and state.json (50 x ~600 B = 30 KB). `TextField.maximumLength` enforces the same numbers in the UI. |
| D14 | Favorites / recents across sources | per source / global | **Global, keyed by channel id (PRODUCT.md M1, ARCHITECTURE decision 6), unchanged** | `t:<tvg-id>` ids are shared by design (a favorite survives a provider switch when the tvg-id matches); `u:<hash>` ids are source-specific by nature. The guide already filters both lists against the loaded index (`Model.countFavorites`, `channelsForScope`), so entries of another source are invisible, not broken. Recents stay bounded by `maxRecents`; favorites are user-driven. Documented in the README; no per-source scoping in v0.2. |
| D15 | Helper surface | new `source` subcommand / extend `state` / new `cache` | **Extend `state` (v2 aware, URL-redacted output) and add one `cache` subcommand with `migrate`, `remove`, `prune` actions. No `state source ...` verbs** | Section 5 contracts untouched. The service does every history mutation in QML; the helper only touches the filesystem where QML must not (`rm`, `rename`, mode bits). `state show` must stop printing URLs once records carry them (section 2.4). |
| D16 | Invalid values set by CLI | run the helper anyway / synthesize | **The service never runs the helper for a `playlistUrl` that fails `validateSourceUrl`; it synthesizes `playlistStatus` from the validation result (like `helperTimeoutStatus`, `Service.qml:422-430`) and leaves `activeCacheDir` empty** | The helper would refuse with the same code; skipping it avoids creating a directory for garbage and keeps the guide's existing error empty state with a reason and no host. Same for `epgUrl` -> `epgStatus`. |

## 2. Data model

### 2.1 `state.json` version 2

```json
{
  "version": 2,
  "cacheLayout": 2,
  "favorites": ["t:bbc1.uk", "u:3f2a9c11"],
  "recents": [ { "id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000 } ],
  "lastPlayed": { "id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000 },
  "sources": [
    {
      "key": "d5977d8a",
      "url": "https://iptv-org.github.io/iptv/countries/us.m3u",
      "epgUrl": "",
      "kind": "http",
      "label": "iptv-org.github.io",
      "labelCustom": false,
      "origin": "migrated",
      "addedAt": 1757700000,
      "lastUsed": 1757790000,
      "fetchedAt": 1757789500,
      "channelCount": 1475,
      "groupCount": 28
    },
    {
      "key": "d990c2e4",
      "url": "http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts",
      "epgUrl": "http://provider.example.test/xmltv.php?username=u&password=p",
      "kind": "http",
      "label": "Provider",
      "labelCustom": true,
      "origin": "xtream",
      "addedAt": 1757750000,
      "lastUsed": 1757750000,
      "fetchedAt": 1757750004,
      "channelCount": 10234,
      "groupCount": 88
    },
    {
      "key": "b0eed9fb",
      "url": "/srv/tv/local.m3u",
      "epgUrl": "",
      "kind": "file",
      "label": "local.m3u",
      "labelCustom": false,
      "origin": "cli",
      "addedAt": 1757760000,
      "lastUsed": 1757760000,
      "fetchedAt": 0,
      "channelCount": 0,
      "groupCount": 0
    }
  ]
}
```

| Field | Type | Rule |
|---|---|---|
| `version` | 2 | `Model.STATE_VERSION`; readers accept 1 (migrate) and 2; unknown -> empty state (existing rule). |
| `cacheLayout` | 0 or 2 | 2 once `cache migrate` has run (section 2.3). 0 (or missing) means "legacy files may still sit in `<cacheDir>/`". |
| `favorites`, `recents`, `lastPlayed` | unchanged | Exactly the v1 shapes (ARCHITECTURE.md section 5). |
| `sources[]` | array, max 50 | Ordered by `addedAt`; the UI sorts by `lastUsed` desc [UX-ASSUMPTION]. |
| `key` | string | `^[0-9a-f]{8}(-[0-9]{1,3})?$`, unique in the array; the cache directory name. |
| `url` | string, 1-2048 | Normalized playlist URL (section 3.1); unique in the array; **the identity**. Carries provider credentials; the file is 0600 (README note, same class as shell.json). |
| `epgUrl` | string, 0-2048 | Normalized EPG URL or `""`. |
| `kind` | `"http"` or `"file"` | From validation. |
| `label` | string, 1-64 | Sanitized (section 6); default from `Model.defaultSourceLabel`. |
| `labelCustom` | bool | True once the user renamed it; reconcile never overwrites a custom label. |
| `origin` | `"guide"`, `"xtream"`, `"cli"`, `"migrated"` | Informational (the edit form can show "Built from Xtream"). |
| `addedAt`, `lastUsed`, `fetchedAt` | epoch seconds | `fetchedAt` is 0 until the first successful `playlist` run; `fetchedAt > 0` means "has a cache" (D7). |
| `channelCount`, `groupCount` | int >= 0 | Copied from the last successful `playlist-status.json` of that source (`Model.withSourceStats`), so the list shows counts without opening N status files. |

Every reducer that builds a new state object (`recordPlayed`, `withFavorites`,
`removeRecent`, `trimRecents`, `Model.js:749-796`) currently rebuilds
`{version, favorites, recents, lastPlayed}` and would drop `sources`; they
all go through one `Model.cloneState(st, patch)` in v2 (Lane 1). The helper's
`normalize_state` (`bin/omarchy-iptv:1557-1576`) likewise carries `sources`
and `cacheLayout` through `favorite add|remove` and `clear-recents`, otherwise
one CLI call would erase the history.

### 2.2 Migration v1 -> v2 (state)

`Model.parseState(text)` and helper `normalize_state(raw)`:

1. `version` 1 or missing: read `favorites`, `recents`, `lastPlayed` as today;
   `sources = []`; `cacheLayout = 0`. Nothing is rewritten until the next
   save, so a downgrade to 0.1.0 still reads the file (it ignores unknown
   keys: `Model.parseState` only picks known keys; `normalize_state` too).
2. `version` 2: also read `sources` (records failing the field rules above
   are dropped; duplicate `url` or `key` keeps the first) and `cacheLayout`.
3. Seeding the active source: the service calls `Model.reconcileSources`
   once `stateFile` has loaded (section 4.4). With `playlistUrl` set and no
   matching record, a record is added with `origin: "migrated"` (on the very
   first v2 run) or `"cli"` (later), label from the host. The first
   `saveState()` after that writes version 2. Favorites and recents are
   untouched.

### 2.3 Cache layout and migration (files)

```
~/.cache/omarchy-iptv/                       0700 (mkdirProc, Service.qml:926)
  sources/                                   0700 (mkdirProc adds it)
    d5977d8a/                                0700 (helper ensure_private_dir)
      channels.json  playlist-status.json    0600 (unchanged shapes, section 5)
      epg-now.json   epg-status.json         0600
      epg-window.txt                         0600 (helper-private)
    d990c2e4/ ...
  channels.json, playlist-status.json, ...   legacy location, gone after migrate
~/.local/state/omarchy-iptv/state.json       0600 (v2)
$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock       unchanged
```

`cache migrate --cache-dir C [--key K]` (helper, idempotent):

- With `--key K`: for each of the five names, if `C/<name>` exists and
  `C/sources/K/<name>` does not, `os.replace` it (same filesystem, atomic);
  if the target exists the legacy file is deleted. Creates `C/sources/K`
  0700. Leftover `.tmp-*` in `C` are deleted.
- Without `--key`: legacy files are deleted (no source to attribute them to).
- Output: `{"ok":true,"kind":"cache","action":"migrate","key":"K","moved":["channels.json","playlist-status.json"],"removed":[]}`.

The service runs it exactly once per state file (`cacheLayout !== 2`), then
saves `cacheLayout: 2`. On this machine the legacy files are the
iptv-org `us.m3u` cache (1,475 channels, 0600) and will move into
`sources/d5977d8a/`.

`cache remove --cache-dir C --key K`: deletes the five files and `.tmp-*`
inside `C/sources/K`, then `rmdir`; unknown files make it leave the directory
and report `{"ok":true,"kind":"cache","action":"remove","key":"K","removed":[...],"kept":["foo.bin"]}`.
Missing directory -> `ok: true, removed: []`.

`cache prune --cache-dir C --keep K1 [K2 ...] [--active K] [--epg-max-age SECONDS]`:
removes every `C/sources/<dir>` whose name is a valid key and not in
`--keep` (same file-by-file rule as `remove`; directories with unknown files
are reported, not forced), and, for kept non-active keys, deletes
`epg-window.txt`, `epg-now.json`, `epg-status.json` older than
`--epg-max-age` (the service passes 86400). Directory names that are not
valid keys are ignored and reported under `"skipped"`. Output:
`{"ok":true,"kind":"cache","action":"prune","removed":["1a2b3c4d"],"agedEpg":["d990c2e4"],"skipped":[]}`.

Key validation (`^[0-9a-f]{8}(-[0-9]{1,3})?$`) plus `os.path.realpath(target).startswith(realpath(C/sources) + "/")`
guards every action; a failing key is `{"ok":false,"kind":"cache","error":{"code":"bad_key","message":"invalid cache key"}}`
(exit 1). No path from argv is ever echoed (R12 hygiene: messages carry base
names only, like `read_local_source`).

### 2.4 `state` subcommand in v2

- `default_state()` -> `{"version": 2, "cacheLayout": 0, "favorites": [], "recents": [], "lastPlayed": null, "sources": []}`.
  `state init` therefore creates a v2 file on fresh installs (`init_state_file`, `bin/omarchy-iptv:1579-1598`).
- Every `state` action prints `state` through `public_state()`: each source
  record is emitted with `url` and `epgUrl` replaced by `host` (`source_host`)
  and `epgHost`, because helper stdout is a sink that must never carry a URL
  (ARCHITECTURE.md section 9 coding standards; `test_stderr_and_stdout_never_contain_the_url`).
  Example: `{"ok":true,"kind":"state","action":"show","state":{"version":2,"cacheLayout":2,"favorites":[],"recents":[],"lastPlayed":null,"sources":[{"key":"d5977d8a","host":"iptv-org.github.io","epgHost":"","kind":"http","label":"iptv-org.github.io","labelCustom":false,"origin":"migrated","addedAt":1757700000,"lastUsed":1757790000,"fetchedAt":1757789500,"channelCount":1475,"groupCount":28}]}}`.
- `tests/test_state.py` `EMPTY` (line 16) and the `CliContractTest.SUBCOMMANDS`
  tuple (`tests/test_helper.py:154`) gain the v2 shape and `"cache"`.

### 2.5 Unchanged contracts

`channels.json`, `playlist-status.json`, `epg-now.json`, `epg-status.json`,
`play`/`stop`/`status` stdout keep their section 5 shapes byte for byte. The
helper's `playlist`/`epg`/`play` verbs are invoked with
`--cache-dir <activeCacheDir>` instead of `--cache-dir <cacheDir>`
(`Service.qml:436, 448, 453, 224, 532, 896`); nothing else changes in those
verbs. `resolve_source` gains the two validation rules of D11 (new codes
`too_long`, `bad_url` -- `bad_url` already exists for a host-less URL at
`bin/omarchy-iptv:554`).

## 3. Model.js contract (Lane 1 provides, Lane 2 consumes; frozen)

All functions are pure, ES5, null-safe, ASCII-only, listed in
`module.exports`, exercised by `tests/Model.test.js` and `tests/Model.spec.qml`.

Constants: `STATE_VERSION = 2`, `CACHE_LAYOUT = 2`, `MAX_SOURCES = 50`,
`MAX_SOURCE_URL = 2048`, `MAX_LABEL = 64`, `MAX_XTREAM_SERVER = 512`,
`MAX_XTREAM_FIELD = 256`, `SOURCES_DIR = "sources"`,
`MASK_CLEAR_PARAMS = ["type", "output"]`.

### 3.1 `sanitizeInput(text, max)` and `validateSourceUrl(text)`

`sanitizeInput(text, max)`: `str(text)` with every character in
`[\u0000-\u001f\u007f-\u009f]` removed (CR, LF, TAB included), leading and
trailing ASCII space and NBSP (`\u00a0`) trimmed, then truncated to `max`
UTF-16 units. Applied at the field boundary (paste, typing, the harness) and
again inside `validateSourceUrl`.

`validateSourceUrl(text)` -> `{ ok, code, message, kind, url, host }`:

1. `s = sanitizeInput(text, MAX_SOURCE_URL + 1)`; `""` -> `empty`;
   length > 2048 -> `too_long`.
2. `s` starts with `/` or `~` -> `kind: "file"`, `url: s` (no `~`
   expansion, no slash collapsing: the CLI and the screen store the same
   string; the helper expands `~` when it reads). A prefix of `/proc/`,
   `/sys/`, `/dev/` (or exactly those) -> `unsafe_path` (the helper's
   `read_local_source` remains authoritative at fetch time).
3. Otherwise `s` must match `^([A-Za-z][A-Za-z0-9+.-]*):(.*)$`; no scheme ->
   `unsupported_scheme` ("Use http(s)://, file:// or an absolute path"; no
   `https://` auto-prefix -- the uptime monitor's guess would silently turn
   a typo into a network request).
4. `file:` -> the rest must start with `//`; the authority up to the next
   `/` is ignored (like `url2pathname(urlsplit(v).path)`,
   `bin/omarchy-iptv:561-563`); the path is percent-decoded
   (`decodeURIComponent`, a throw -> `bad_url`), must start with `/`, then
   step 2 applies. `file:///srv/tv/local.m3u` and `/srv/tv/local.m3u` are the
   same source.
5. `http` / `https` (scheme lowercased; `HTTP://` accepted like the helper):
   the rest must start with `//` (`bad_url`); authority = up to the first
   `/`, `?` or `#`; userinfo = part before the last `@` (kept verbatim);
   host = `[...]` IPv6 literal or everything before the last `:`; host must
   be non-empty and contain no whitespace (`bad_url`), lowercased; port must
   be digits (`bad_url`), dropped when empty or the scheme default (80/443);
   path `""` -> `/`, otherwise verbatim (no re-encoding, no dot-segment
   removal); query verbatim (order, case and encoding preserved -- provider
   tokens are case-sensitive), a bare `?` dropped; fragment dropped
   (never sent). Whitespace anywhere in the rest -> `bad_url`.
   `url = scheme://[userinfo@]host[:port]path[?query]`, `host` as computed.
6. Anything else (`ftp:`, `data:`, `javascript:`, `rtsp:`) -> `unsupported_scheme`.

Vectors (in `tests/fixtures/source-urls.json`, consumed by node, the QML
spec and `tests/test_source.py`; `expect.url` is the normalized form):

```
" HTTP://Provider.Example.TEST:80/get.php?username=u&password=p " -> ok http "http://provider.example.test/get.php?username=u&password=p"
"https://iptv-org.github.io:443/iptv/countries/us.m3u#x"          -> ok http "https://iptv-org.github.io/iptv/countries/us.m3u"
"http://h.test"                                                     -> ok http "http://h.test/"
"http://u:p@h.test:8080/x?y=1"                                      -> ok http "http://u:p@h.test:8080/x?y=1"
"http://[::1]:8080/list.m3u"                                        -> ok http "http://[::1]:8080/list.m3u"
"FILE:///srv/tv/local.m3u"                                          -> ok file "/srv/tv/local.m3u"
"file://host/srv/tv/a%20b.m3u"                                      -> ok file "/srv/tv/a b.m3u"
"~/tv/list.m3u"                                                     -> ok file "~/tv/list.m3u"
"/srv/tv/local.m3u" + LF                                            -> ok file "/srv/tv/local.m3u"   (newline stripped)
"http://h.test/a" + NUL + "b"                                       -> ok http "http://h.test/ab"    (control char stripped)
""  /  "   "                                                        -> empty
"provider.test/list.m3u"                                            -> unsupported_scheme
"ftp://h.test/x" / "javascript:alert(1)" / "data:text/plain,x"      -> unsupported_scheme
"http:///x" / "http://h .test/" / "http://:80/" / "http://h.test:abc/" -> bad_url
"file:relative.m3u" / "file:///%zz"                                 -> bad_url
"/proc/self/environ" / "file:///dev/zero" / "/sys"                  -> unsafe_path
"http://h.test/" + "a" x 2048                                       -> too_long
```

Helper mirror: `validate_source_url(text) -> (ok, code, message, kind, url)`
in `bin/omarchy-iptv`, called by `resolve_source`; the Python test loads
the same JSON fixture. A value the guide accepted is therefore never refused
by the helper for a syntactic reason; the helper keeps the runtime refusals
(`not_found`, `unsafe_path` after realpath, `too_large`, ...).

### 3.2 Keys and labels

- `sourceKey(url)` = `fnv1a32(url)`; vectors:
  `https://iptv-org.github.io/iptv/countries/us.m3u` -> `d5977d8a`,
  `http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts` -> `d990c2e4`,
  `http://provider.example.test:8080/get.php?...` -> `85ac744a`,
  `/srv/tv/local.m3u` -> `b0eed9fb` (computed with the shipped `fnv1a32`).
- `allocateSourceKey(sources, url)`: the record whose `url === url` ->
  its key; else `base = sourceKey(url)`, then `base`, `base-2`, `base-3`...
  until no record uses it. Deterministic given the list, so a re-add after a
  removal gets the same key unless a colliding record appeared in between.
- `findSource(sources, key)`, `findSourceByUrl(sources, url)` -> record or null.
- `defaultSourceLabel(url, kind, existingLabels)`: http -> host as computed
  (lowercase, no `www.` stripping); file -> last path segment (`local.m3u`),
  `"local file"` when empty; then ` (2)`, ` (3)` while the label is taken;
  capped at 64.
- `sourceCacheDir(cacheDir, key)` = `cacheDir + "/sources/" + key`; `""`
  when either input is empty or the key fails the regex.
- `formatAgo(nowSec, atSec)` -> `"just now"`, `"12 min ago"`, `"3 h ago"`,
  `"2 d ago"`, `""` for 0 [UX-ASSUMPTION on wording].

### 3.3 Masking

`maskUrl(url)`:
- `kind file` -> returned unchanged.
- http(s): `scheme://` + (`***@` when userinfo present) + `host[:port]` +
  `path` + (`?` + each `name=value` with the value replaced by `***`, except
  names in `MASK_CLEAR_PARAMS`; a name without `=` is kept; `&` order
  preserved).
- Vectors: `http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts`
  -> `http://provider.example.test/get.php?username=***&password=***&type=m3u_plus&output=ts`;
  `http://u:p@h.test:8080/x?token=abc&flag` -> `http://***@h.test:8080/x?token=***&flag`;
  `https://iptv-org.github.io/iptv/countries/us.m3u` -> unchanged.
- `hostOf`, `sourceLabel`, `redactUrls` (`Model.js:1138-1165`) keep their
  behaviour and remain the only functions allowed on list rows, footers,
  tooltips, notifications and console lines.

### 3.4 Xtream

`xtreamUrls({ server, username, password })` -> `{ ok, code, message, playlistUrl, epgUrl, host }`:

1. `server = sanitizeInput(server, MAX_XTREAM_SERVER)`; empty -> `bad_server`.
   No scheme -> prefix `http://`. Must then validate as `http(s)` through
   `validateSourceUrl` (so userinfo, IPv6, ports, `bad_url` rules are shared);
   a query or fragment on the server -> `bad_server`; userinfo -> `bad_server`.
   Trailing slashes stripped; a trailing `/get.php`, `/xmltv.php`,
   `/player_api.php` or `/c` (the web-player path users paste) is stripped
   once. Remaining path is the base (`http://h.test:8080` or
   `http://h.test/xtream`).
2. `username`, `password` = `sanitizeInput(x, MAX_XTREAM_FIELD)`; either
   empty -> `bad_credentials`.
3. `enc(v)` = `encodeURIComponent(v)` plus `!`, `'`, `(`, `)`, `*` percent-encoded
   uppercase, i.e. only `A-Za-z0-9-._~` survive (equals Python `quote(v, safe="")`;
   vector `a b!*'()~-._/@:+` -> `a%20b%21%2A%27%28%29~-._%2F%40%3A%2B`).
4. `playlistUrl = base + "/get.php?username=" + enc(U) + "&password=" + enc(P) + "&type=m3u_plus&output=ts"`,
   `epgUrl = base + "/xmltv.php?username=" + enc(U) + "&password=" + enc(P)`,
   `host` = the server host. Parameter order is fixed so the same account
   always yields the same key.
5. Vectors: `("Provider.Example.TEST:8080/", "u", "p")` ->
   `http://provider.example.test:8080/get.php?username=u&password=p&type=m3u_plus&output=ts`
   and `.../xmltv.php?username=u&password=p`; `("https://h.test/c", "a b", "p&q")` ->
   `https://h.test/get.php?username=a%20b&password=p%26q&type=m3u_plus&output=ts`;
   `("h.test/get.php?x=1", ...)` -> `bad_server`; `("", ...)` -> `bad_server`;
   `("h.test", "", "p")` -> `bad_credentials`.

### 3.5 State reducers (all return new objects; `sources` always carried)

| Function | Returns |
|---|---|
| `emptyState()` | `{version: 2, cacheLayout: 0, favorites: [], recents: [], lastPlayed: null, sources: []}` |
| `parseState(text)` | v1 or v2 text -> v2 object (section 2.2), records validated |
| `cloneState(st, patch)` | new state with `patch` keys replacing; used by every existing reducer |
| `withCacheLayout(st, n)` | `cacheLayout` set |
| `addSource(st, fields, nowSec)` | `{ ok, code, message, state, key }`; `fields = { playlistUrl, epgUrl, label, origin }`; codes `empty`, `too_long`, `bad_url`, `unsupported_scheme`, `unsafe_path`, `duplicate` (returns the existing `key`), `too_many` |
| `updateSource(st, key, fields, nowSec)` | `{ ok, code, message, state, key, urlChanged, replacedKey }`; label -> `labelCustom: true`; a changed playlist URL yields a NEW record (`key` new, `replacedKey` old, `fetchedAt: 0`, label/addedAt copied) and leaves the old one in place until the service confirms the probe (section 4.6); `unknown_source` |
| `removeSource(st, key)` | `{ state, removed }` (`removed` = record or null) |
| `touchSource(st, key, nowSec)` | `lastUsed` bumped |
| `withSourceStats(st, key, status)` | `fetchedAt`, `channelCount`, `groupCount` from a parsed `ok` playlist status |
| `reconcileSources(st, playlistUrl, epgUrl, previousActiveKey, nowSec)` | `{ state, changed, activeKey, added, evicted, invalid }` (D3; `invalid` = validation result when `playlistUrl` is set but invalid; `evicted` = LRU keys dropped beyond `MAX_SOURCES`, never the active one) |
| `activeSourceKey(st, playlistUrl)` | key of the record matching the normalized URL, else `""` |
| `sourceRows(st, activeKey, nowSec, errors)` | UI rows, sorted `active` first then `lastUsed` desc [UX-ASSUMPTION]: `{ key, label, host, kind, active, channelCount, groupCount, lastUsed, lastUsedText, fetched, epgConfigured, origin, errorReason }` -- no URL field, ever |
| `sourceForEdit(st, key)` | `{ key, label, labelCustom, kind, host, playlistUrl, epgUrl, playlistMasked, epgMasked, origin }` or null -- the only function that hands a URL to the guide |
| `sourcesSummary(st, activeKey)` | IPC list `{ key, label, host, active, channelCount, lastUsed }` |
| `entryWith(entry, patch)` | full bar entry for `updateEntryInline`: every own key of `entry` copied, `patch` applied, `id` forced |
| `cacheStale(status, refreshMinutes, nowSec)` | true when `status.ok !== true`, `fetchedAt` missing/0, or `nowSec - fetchedAt >= refreshMinutes * 60` |
| `sourceReason(code)` | user-facing sentence per result code (section 4.3); `statusReason` gains the same codes |

## 4. Service.qml contract (Lane 2 provides, Lane 1 consumes; frozen)

### 4.1 Properties (read-only for the guide)

| Property | Type | Meaning |
|---|---|---|
| `sources` | var (array) | `Model.sourceRows(userState, activeSourceKey, nowSec, sourceErrors)`; re-evaluated on state, settings, error and `nowSec` changes |
| `activeSourceKey` | string | key of the record matching `playlistUrl`, `""` when unconfigured or invalid |
| `activeSourceLabel` | string | label of that record, else `sourceLabel` (host) as today |
| `activeCacheDir` | string | `sourceCacheDir(cacheDir, activeSourceKey)` when `stateLoaded && cacheReady`, else `""` |
| `sourceCount` | int | `userState.sources.length` |
| `canAddSource` | bool | `sourceCount < MAX_SOURCES && !probing` |
| `stateLoaded`, `cacheReady` | bool | startup gates (section 4.4) |
| `probing` | bool | a `sourceProbeProc` run is in flight |
| `probingKey` | string | its key (`""` otherwise) |
| `switching` | bool | between a committed switch and the new cache's first load/failure |
| `sourceErrors` | var (object) | session-only `{ key: reason }` from failed probes, URL-free (`Model.statusReason`) |
| `settingsInvalid` | var or null | validation result when `playlistUrl` is set but invalid (D16), for the empty state |

Existing properties (`configured`, `status`, `channels`, `playlistStatus`,
`epg*`, `nowPlaying`, ...) keep their meaning and now describe the active
source.

### 4.2 Signals

- `sourceProbeFinished(string key, bool ok, string reason, int channelCount, int groupCount)`
  -- after an add/edit/never-fetched-switch probe; on `ok` the switch has
  already been committed. S1's inline "1,475 channels in 28 groups" comes
  from here (`Model.pluralChannels` + groups).
- `sourceSwitched(string key)` -- the new source's cache (or its absence)
  has been applied to `channels`.
- `sourceRemoved(string key, bool wasActive)`.
- `sourcesPersistFailed(string code)` -- `updateEntryInline` returned false
  while a change was needed (risk R2).

### 4.3 Actions and result shape

Every action returns `{ ok: bool, code: string, message: string, key: string }`
synchronously (`key` = the record concerned, `""` when none). Codes:

`ok`, `empty`, `too_long`, `bad_url`, `unsupported_scheme`, `unsafe_path`,
`duplicate` (key = existing record; the guide offers "switch instead"
[UX-ASSUMPTION]), `too_many`, `busy` (a probe or switch is in flight),
`unknown_source`, `not_ready` (state not loaded yet), `bad_server`,
`bad_credentials`, `persist_failed`. Asynchronous outcomes (fetch errors)
arrive through `sourceProbeFinished` with the helper's codes
(`network`, `http_403`, `not_a_playlist`, `timeout`, ...).

| Action | Behaviour |
|---|---|
| `addSource({ playlistUrl, epgUrl, label, origin })` | sanitize -> validate both URLs -> duplicate check (`findSourceByUrl`) -> cap check -> `Model.addSource` -> `saveState()` -> probe (section 4.6). Returns `ok` with the new key as soon as the probe starts. `origin` defaults to `"guide"`. |
| `updateSource(key, { label, playlistUrl, epgUrl })` | label only: state + save. `epgUrl`: validate, record update, and when `key === activeSourceKey` also `persistActive(rec.url, epg)`. `playlistUrl` changed: `Model.updateSource` creates the replacement record, then a probe with `replaceKey`; on success the old record is removed, its cache removed, and the switch committed if the old one was active; on failure nothing else changes and the replacement record is dropped again. |
| `removeSource(key)` | `busy` if that key is probing. Removes the record, saves, queues `cache remove`, and if it was active `persistActive("", "")` (S7: back to the first-run state; playback, if any, continues). |
| `switchSource(key)` | no-op `ok` when already active; never-fetched (`fetchedAt === 0`) -> probe with commit; else section 4.5. |
| `buildXtreamSource({ server, username, password, label })` | `Model.xtreamUrls` -> `addSource({..., origin: "xtream", label: label or host})`. The password is never stored outside the URL and never logged. |
| `sourceForEdit(key)` | `Model.sourceForEdit(userState, key)`; the only way the guide obtains a URL; the guide binds it to the edit field only, never to a list delegate. |
| `retrySource(key)` | probe again a record with `fetchedAt === 0` (S8 retry) [UX-ASSUMPTION that the form has a retry affordance]. |

`persistActive(playlistUrl, epgUrl)` (internal): builds
`Model.entryWith(Model.findBarEntry(shell.barConfig, pluginId), { playlistUrl, epgUrl })`,
compares with the current settings (skip when equal) and calls
`shell.updateEntryInline(pluginId, entry)` (`services/PluginShellApi.qml:62-64`,
scoped to our own id at `shell.qml:648-653`). A `false` return while a change
was needed emits `sourcesPersistFailed("persist_failed")` (risk R2). The full
entry is passed because `updateEntryInline` replaces the entry wholesale
(1093-1098): keys we do not own (`refreshMinutes`, `mpvArgs`, ...) survive
only because `entryWith` copies them.

### 4.4 Startup sequence

1. `Component.onCompleted`: `mkdirProc` (`mkdir -p -m 700` of `cacheDir`,
   `cacheDir/sources`, `stateDir`, `runtimeDir`) -> `stateInitProc`
   (`state init`, now v2) -> `dirsReady`.
2. `stateFile.onLoaded` -> `applyUserState` -> `stateLoaded = true` ->
   `reconcile()`.
3. `reconcile()` (also from `onPlaylistUrlChanged`, `onEpgUrlChanged`):
   `Model.reconcileSources(userState, playlistUrl, epgUrl, activeSourceKey, now)`;
   on `changed` assign `userState`, `saveState()`; for each `evicted` key
   queue `cache remove`; set `settingsInvalid`. `activeSourceKey` is a
   binding on `userState` + `playlistUrl`, so it updates here.
4. If `userState.cacheLayout !== 2`: queue `cache migrate --cache-dir C
   [--key activeSourceKey]`; on exit `userState = withCacheLayout(2)`,
   `saveState()`, `cacheReady = true`. Else `cacheReady = true` at once.
5. `activeCacheDir` becomes non-empty -> the four cache `FileView` paths rebind ->
   Quickshell reloads them (verified, section 9 R1) -> `applyChannels`,
   `applyPlaylistStatus`, `applyEpgNow`, `applyEpgStatus` as today.
6. `playlistStatusFile.onLoaded` / `onLoadFailed` with `pendingFreshness`
   set: `Model.cacheStale(...)` -> `refreshPlaylist(true)` and, when
   `epgUrl !== ""`, `refreshEpg(true)` (the helper's own TTL makes a fresh
   window a ~40-90 ms recompute, `needs_refetch`, `bin/omarchy-iptv:1102-1113`).
   `refreshTimer.triggeredOnStart` becomes `false`: the first fetch is now
   driven by cache freshness, not by service start (a fresh cache after
   `omarchy restart shell` is no longer re-downloaded; US7 timer semantics
   otherwise unchanged).
7. Once per start, after `cacheReady`: queue `cache prune --cache-dir C
   --keep <every key> --active <activeSourceKey> --epg-max-age 86400`.

Helper invocations of `playlist`, `epg` (both modes) and `play --id` use
`--cache-dir root.activeCacheDir` and return early while it is `""`.
`runPlaylistHelper` additionally returns early while `settingsInvalid`.

`onActiveCacheDirChanged`: when the new value is `""`, clear `channels`,
`channelIndex`, `channelsMeta`, `playlistStatus`, `playlistWarnings`,
`epgNow`, `epgMeta`, `epgLoaded`, `epgStatus`, `lastError` in memory (an
empty `FileView` path emits neither `loaded` nor `loadFailed`, verified);
otherwise set `pendingFreshness = true` and reset the same fields to the
"nothing known yet" values so a stale reason never survives a switch
(`onPlaylistUrlChanged` already does this for the status, `Service.qml:671-678`).

### 4.5 Switch, step by step, with the budget (warm cache, 10k channels)

| Step | Where | Cost |
|---|---|---|
| 1. `switchSource(key)`: guards, `switching = true`, `userState = touchSource(...)`, `saveState()` (async atomic write of ~30 KB) | service | < 1 ms |
| 2. `persistActive(rec.url, rec.epgUrl)` -> `updateEntryInline`: two `JSON.parse(JSON.stringify(shellConfig))` of a few-KB object + one pretty `stringify` + `FileView.setText` (async) | host, lines 1078-1112, 109-114 | ~1-3 ms |
| 3. `shellConfig` assignment -> `onShellConfigChanged` -> `pluginsChanged()` -> `syncPluginApis()` -> `shellApi.barConfig` -> our `settings` binding -> `playlistUrl` / `epgUrl` change -> `reconcile()` (no-op) -> `activeSourceKey` -> `activeCacheDir` | host + service | < 1 ms |
| 4. Four `FileView` paths rebind; Quickshell reads the new files (2 MB `channels.json`) | Quickshell | ~5-10 ms (2 ms for a small file in the scratch run) |
| 5. `channelsFile.onLoaded` -> `applyChannels`: `parseChannels` + `prepareChannels` + `indexById` | service | node: 11-17 + 10-32 + 3-6 ms; Qt V4 is 2-3x slower: ~60-90 ms |
| 6. `channelsChanged` -> guide `scheduleRebuild` (40 ms debounce above 2,000 channels) -> `rebuildDisplay`: `scopeEntries` (~10 ms node / ~20 ms V4 at 400 groups) + `groupModel` rebuild + integer row model | guide | ~30 ms |
| 7. `switching = false`, `sourceSwitched(key)` from `channelsFile.onLoaded` / `onLoadFailed` | service | -- |
| 8. `playlistStatusFile.onLoaded` -> freshness -> optional background refresh (300 ms debounce, helper 1-2 s, banner-free) | service | off the redraw path |

Total ~100-130 ms at 10k in the Qt engine, ~20 ms at the 1,475-channel
list on this machine. Measured by scenario H8 (section 8.4). If QA measures
over 150 ms at 10k, the optional optimisation is a two-entry in-memory LRU
of prepared `{channels, channelIndex, channelsMeta}` keyed by source key so
switching back skips step 5 entirely; not built unless needed.

Playback across a switch: mpv is untouched; `nowPlaying` stays; the zap
ring re-resolves against the new `channels` and simply yields nothing when
the playing channel's group is absent (`Model.zapRing` -> `nextInGroup([])`
-> null). Documented behaviour, no new code.

### 4.6 Probe (add, edit, never-fetched switch)

`sourceProbeProc` is a second `Process` with the same stdout/stderr
collectors, redaction (`Model.redactUrls` on stderr) and 180 s watchdog as
`playlistProc` (`Service.qml:965-977, 833-846`), so a running refresh of the
active source never blocks adding another one and vice versa. One probe at a
time (`busy`). Command: `["python3", helperPath, "playlist", "--url", rec.url, "--cache-dir", sourceCacheDir(cacheDir, key)]`.
On exit:

- `ok`: `userState = withSourceStats(state, key, status)`; when a
  `replaceKey` is set, `removeSource(replaceKey)` + queue `cache remove`;
  `saveState()`; `persistActive(rec.url, rec.epgUrl)` when the probe was
  meant to commit (always for add and never-fetched switch; for edit only
  when the replaced record was active) -> the switch then follows section
  4.5; emit `sourceProbeFinished(key, true, "", channelCount, groupCount)`.
- failure or watchdog: `sourceErrors[key] = Model.statusReason(status)`
  (URL-free); the record keeps `fetchedAt: 0`; a replacement record from an
  edit is dropped again (old record intact); the previous active source is
  untouched (S8); emit `sourceProbeFinished(key, false, reason, 0, 0)`. No
  notification (the user is looking at the form) [UX-ASSUMPTION].

### 4.7 Cache helper queue

One `cacheProc` `Process` plus a FIFO of `{ args, onDone }` (`migrate`,
`remove`, `prune`); the next job starts from `onExited`. Output is parsed
with `parseHelperStatus(text, "cache")`; failures are `console.warn`ed with
the code and action only. Nothing waits on the queue except `cacheReady`
(migrate).

### 4.8 IPC

`statusSummary()` gains `activeSource: { key, label, host } | null` and
`sources: Model.sourcesSummary(userState, activeSourceKey)`; no new verbs
(R9 keeps the surface minimal; switching from the command line is
`omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>`, which now also
records the source, S5). `omarchy-shell io.github.rmcdavid.iptv status` stays
URL-free by construction.

## 5. What the guide needs (for docs/UX-SOURCES.md)

Inputs the Sources screens bind or call (all above): `service.sources`,
`service.activeSourceKey`, `service.canAddSource`, `service.probing`,
`service.probingKey`, `service.switching`, `service.settingsInvalid`,
`service.sourceForEdit(key)`, the five actions, the four signals,
`Model.maskUrl`, `Model.sourceReason(code)`, `Model.formatAgo`,
`Model.sanitizeInput`, `Model.validateSourceUrl` (for live inline
validation while typing, optional).

Fields [UX-ASSUMPTION unless M2-SOURCES fixes them]: first-run state (S1):
playlist URL, optional EPG URL, Enter submits (`addSource`), result line
from `sourceProbeFinished`. Sources list (S2): rows from `service.sources`
(label, host, `channelCount`, `lastUsedText`, active marker, error marker
when `errorReason !== ""`), reached from a `Sources` row at the bottom of the
group column and one list-mode key that is not already taken (`f s r x /`
are; UX picks), Enter = `switchSource`, keys for add / edit / remove
(confirm through `qs.Ui` `ConfirmDialog`) / back. Edit form (S4, S6): label,
playlist URL (`playlistMasked` shown, raw `playlistUrl` after the reveal
key; the field is a `qs.Ui` `TextField` so paste works), EPG URL (same),
save = `updateSource`. Xtream form (S6): server, username, password
(`TextField { password: true }`, `Ui/TextField.qml:24`), label ->
`buildXtreamSource`; after saving, edit shows the built URLs masked and
never the password field again. Keyboard: `PanelKeyCatcher { blocked: <a TextField has activeFocus> }`
exactly like the network panel (`plugins/panels/network/Panel.qml:989-996`),
so the guide's list-mode letters never fire while typing; Esc in a field
cancels the form (`Keys.onEscapePressed`).

Paste: `TextField`s receive Ctrl+V and Shift+Insert natively (D9). One
function `pasteInto(field)` exists in Guide.qml for the fallback path only
(`Process { command: ["wl-paste", "--no-newline", "--type", "text"] }`,
`StdioCollector`, then `field.insert(field.cursorPosition, Model.sanitizeInput(text, max))`),
enabled by a constant `pasteViaProcess` that ships `false` unless H4 fails.
Both paths run the pasted text through `Model.sanitizeInput` and the
`maximumLength` cap before it becomes field text.

## 6. Security and privacy rules for the input surface

1. Clipboard and typed text are data. `Model.sanitizeInput` strips
   `[\u0000-\u001f\u007f-\u009f]` (so a multi-line paste collapses to one
   line), trims, and caps (URL 2,048; label 64; Xtream server 512, user and
   password 256). `TextField.maximumLength` mirrors the caps so a 16 KB paste
   never allocates a 16 KB string in a binding. Text is `Text.PlainText`
   everywhere it is rendered (coding standard; `StyledText` stays reserved
   for the plugin's own hint strings, `Guide.qml:1281`).
2. Scheme allow-list: `http`, `https`, `file`, absolute or `~` paths --
   the helper's `SOURCE_SCHEMES` (`bin/omarchy-iptv:61`) -- enforced by
   `validateSourceUrl` before any state write and again by
   `validate_source_url` inside `resolve_source`. Local paths under
   `/proc`, `/sys`, `/dev` are refused in both places; realpath, regular
   file, 64 MB cap stay in `read_local_source`.
3. No shell anywhere: every process is an argv array (`playlist`, `cache`,
   `state`, `wl-paste`); the URL follows `--url`; keys follow `--key` /
   `--keep` and match `^[0-9a-f]{8}(-[0-9]{1,3})?$` before they become a
   path. No `omarchy bar set` subprocess on the normal path (D1 writes
   in-process); the CLI fallback of risk R2 is argv too.
4. Redaction at every sink, extended: list rows and IPC carry `host`
   (`Model.hostOf`); the edit field carries `maskUrl` until revealed;
   `sourceErrors` and `sourceProbeFinished.reason` come from
   `Model.statusReason` (host-only messages, `bin/omarchy-iptv:793-801`);
   probe stderr is `redactUrls`ed before `console.warn`; `console.*` lines
   added by this feature name keys, labels, hosts and codes only; helper
   `state` stdout is `public_state()`; the harness logs entry keys only
   (S-08 pattern kept). Notifications: none added. The Xtream password is
   never a property of its own after `buildXtreamSource` returns; it lives
   only inside the URL string in state.json and shell.json.
5. Files: `state.json` stays 0600 (created by `state init`, S-02; `FileView`
   keeps an existing mode); `sources/` and every `sources/<key>/` are 0700
   (`mkdir -p -m 700` and `ensure_private_dir`); every helper write is the
   existing `O_EXCL` temp + `chmod 0600` + `os.replace`. Removal deletes
   known file names only.
6. IPC: `status` gains `sources` (label/host/key/counts) and `activeSource`;
   no verb takes a URL or a path; no new verbs.
7. Hostile playlist vs the Sources screen: nothing. The screen renders
   state records the user created (labels the user typed, hosts computed
   from URLs the user entered, counts coerced to numbers by
   `parseHelperStatus`). It never reads `channels.json`, channel names,
   groups, or the `#EXTM3U url-tvg` hint (`epgUrlHint` is deliberately not
   surfaced in v0.2). A hostile *label* (`${path}`, `--urgency=x`) is
   PlainText on screen and never reaches mpv or `omarchy-notification-send`.
8. Credentials at rest: `state.json` now holds every known playlist/EPG URL
   (0600, 0700 dir), shell.json holds the active one (0600), each
   `channels.json` holds stream URLs (0600). README settings section gains
   the sentence. Removing a source deletes its cache and record; the
   shell.json entry is cleared when it was active.
9. Concurrency bounds: one probe, one playlist refresh, one EPG run, one
   cache job at a time; each helper under the 180 s watchdog; at most 50
   sources; `cache prune` argv carries at most 50 keys.

## 7. Performance

| Item | Budget | How |
|---|---|---|
| Switch redraw (warm cache) | < 150 ms at 10k | Section 4.5: synchronous in-process settings write, FileView auto reload, existing load path; no helper on the redraw path; optional prepared-LRU if measured over budget |
| Guide open | unchanged < 150 ms | Sources rows derive from `userState.sources` in memory (<= 50 records); no file or helper access on open; the group column gains one row |
| Sources screen open | < 10 ms | `Model.sourceRows` over <= 50 records; a `ListModel` of <= 50 rows |
| Helper runs on open | 0 | none added; probes run only on add/edit/never-fetched switch, `cache` jobs only at start and on removal |
| state.json | <= ~35 KB | 50 x ~600 B records + favorites/recents |
| Disk | typical 5 sources x ~3 MB; worst 50 x ~16 MB | inactive sources keep `channels.json` + `playlist-status.json` (<= ~2 MB at 10k, `MAX_CHANNELS` 50,000 bounds it); their EPG files are aged out after 24 h by the startup prune and re-fetched on switch |
| Startup extra | one `cache migrate` (first v2 run only) + one `cache prune` per shell start | ~40 ms python startup each, serialized, off the UI thread |

## 8. Work split, interface freeze, test plan

### 8.1 Lanes and file ownership

| Lane | Owns | Must not touch |
|---|---|---|
| Lane 1: Model + Guide | `Model.js` (section 3 functions, `STATE_VERSION 2`, reducers through `cloneState`, `statusReason` additions), `Guide.qml` (first-run input, Sources list, edit and Xtream forms, masking/reveal, paste, `Sources` column row, key bindings per UX-SOURCES.md), `tests/Model.test.js`, `tests/Model.spec.qml`, `tests/fixtures/source-urls.json` (author) | `Service.qml`, `bin/omarchy-iptv`, python tests, harness |
| Lane 2: Service + helper + harness | `Service.qml` (section 4), `bin/omarchy-iptv` (`validate_source_url`, state v2, `public_state`, `cache` subcommand, `resolve_source` caps), `tests/test_source.py` (new), `tests/test_state.py`, `tests/test_helper.py`, `scripts/dev-harness/shell.qml` + `run.sh` (new IPC verbs; `updateEntryInline` must now APPLY the entry to `fakeShell.barConfig` instead of only logging it, keeping the keys-only log), `manifest.json` version bump at release | `Model.js`, `Guide.qml` |

Order: Lane 1 lands `Model.js` + fixture first (a day-one PR
`feat(model): source logic`), because Lane 2's `Service.qml` calls it; until
then Lane 2 codes against section 3 and may keep a throwaway stub outside
the repo. Lane 2 lands the helper and `Service.qml` next; Lane 1's
`Guide.qml` lands last against the real service. `BarWidget.qml`, the
manifest schema and `README.md` need no change for the feature (README and
CHANGELOG are PO/FE docs tasks at release).

### 8.2 Frozen interfaces

1. Section 3 function names, argument order and result keys.
2. Section 4.1-4.3 property names, signal signatures, action names and
   result codes.
3. Section 2.1 state schema and section 2.3 helper output shapes.
4. `tests/fixtures/source-urls.json` case format:
   `[{ "input": "...", "ok": true, "kind": "http", "url": "...", "host": "..." }, { "input": "...", "ok": false, "code": "bad_url" }]`.

A change to any of these needs a note in this file and a message to the
other lane before the code lands.

### 8.3 Automated tests per layer (exact commands)

| Layer | Owner | What | Command |
|---|---|---|---|
| Model (node) | Lane 1 | `sanitizeInput`, every `source-urls.json` case through `validateSourceUrl`, `sourceKey` vectors, `allocateSourceKey` with a forced collision (a record pre-assigned the colliding key), `defaultSourceLabel` dedupe and caps, `maskUrl` vectors, `xtreamUrls` vectors and the percent-encoding vector, `parseState` v1 -> v2 (favorites/recents preserved, `cacheLayout 0`), every reducer carrying `sources`, `reconcileSources` (known URL: no add, `lastUsed` only on key change, `epgUrl` adoption; unknown: add with `origin cli`; invalid; eviction at 51 never evicts the active), `addSource` codes, `updateSource` replacement semantics, `removeSource`, `withSourceStats`, `sourceRows` has no `url` key, `sourcesSummary` JSON contains no `://`, `entryWith` keeps foreign keys, `cacheStale` | `node tests/Model.test.js` |
| Model (Qt engine) | Lane 1 | the same vectors for `validateSourceUrl`, `sourceKey`, `maskUrl`, `xtreamUrls`, `parseState` (proves `decodeURIComponent`, `encodeURIComponent`, `normalize` behave in V4) | `QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml` |
| Helper | Lane 2 | `validate_source_url` over the shared fixture; `resolve_source` refuses `too_long` and control chars without echoing the URL; `playlist --cache-dir <tmp>/sources/k` writes 0600 files in a 0700 dir; `state init` writes v2; `favorite add` on a v1 file writes v2 and keeps a pre-existing `sources` list intact; `state show` output has no `url`/`epgUrl` keys and no `://`; `cache migrate` moves the five names, is idempotent, deletes legacy files without `--key`; `cache remove` deletes only known names, keeps unknown files, tolerates a missing dir; `cache prune` keeps listed keys, ages EPG files of non-active keys, skips non-key dirs; `bad_key` for `../x`, `abc`, `d5977d8a/..`; `CliContractTest.SUBCOMMANDS` includes `cache`; exactly one JSON line on stdout | `python3 -m unittest discover -s tests` |
| Gate | both | validate, qmllint, node, python, QML spec, ASCII | `scripts/check.sh` |

### 8.4 Harness scenarios (Lane 2 adds the verbs; QA runs them)

New harness IPC verbs (target `harness`): `addSource(playlistUrl, epgUrl, label)`,
`updateSource(key, json)`, `removeSource(key)`, `switchSource(key)`,
`xtream(server, username, password)`, `sources()` (JSON of `service.sources`),
`activeCache()` (path), plus `state()` extended with `activeSourceKey`,
`probing`, `switching`, `sourceErrors`. `run.sh` gains `--source2 SRC`
(a second generated fixture) and prints only `scheme://host`.

| # | Scenario | Steps | Expect |
|---|---|---|---|
| H1 | Migration from a v1 install | `run.sh clean`; seed the scratch cache with a v0.1 layout (`python3 bin/omarchy-iptv playlist --url <fixture> --cache-dir $SCRATCH/cache/omarchy-iptv`) and a v1 `state.json` with favorites; `run.sh --open --keep` | `state.json` version 2, favorites kept, one `sources[]` record `origin migrated`; files moved to `cache/omarchy-iptv/sources/<key>/`; legacy files gone; guide shows the same channels; screenshot `sources-migrated` |
| H2 | First run (S1) | `run.sh --playlist none --open`; `run.sh key` to type a fixture path, Enter | inline `N channels in G groups`; `sources()` has one record; `activeCache()` under `sources/`; screenshot `sources-first-run` |
| H3 | Invalid input (S8) | type `ftp://x`, `provider.test/list`, `/proc/self/environ`, a 3,000-char string, Enter each | inline reason per code, no state record, no helper run (journal has no `playlist:` line); screenshot `sources-invalid` |
| H4 | Paste (D9) | `wl-copy -- "<fixture path>"` then `run.sh key -M ctrl v -m ctrl` and again with `-M shift -k Insert -m shift`; also `wl-copy` of a two-line string with a tab | field shows the path both ways; the multi-line paste arrives as one line (control chars stripped). If empty -> flip `pasteViaProcess`, re-run |
| H5 | Add + fetch failure keeps the active source (S8) | with a working source active, `addSource` of `http://127.0.0.1:9/x.m3u` | `sourceProbeFinished(false, "Connection refused")`, active key unchanged, guide list still populated, record listed with an error marker; screenshot `sources-add-failed` |
| H6 | Switch (S3) | two sources fetched; `switchSource(k2)`; `switchSource(k1)` | `state()` shows the other key active, channels count changes, `activeCache()` changes, `updateEntryInline` logged with keys only; no helper run when the cache is younger than `refreshMinutes` (journal); screenshot `sources-list` |
| H7 | Remove active (S7) | `removeSource(<active>)` | first-run empty state, `sources/<key>/` gone, other dirs intact, `updateEntryInline` logged with `playlist (none)` |
| H8 | Switch timing (PERF) | 10k fixture as source 2 (`scripts/gen-playlist.py --channels 10000 --groups 400 --out ...`); `OMARCHY_IPTV_DEBUG=1` makes `switchSource` and `channelsFile.onLoaded`/guide rebuild log `console.info("omarchy-iptv switch <ms>")`; run 5 switches each way | median under 150 ms; report median/max |
| H9 | CLI parity (S5) | `run.sh ipc set playlistUrl <fixture2>` while the guide is open | new record `origin cli`, label = host/file name, becomes active, first fetch runs (no cache yet) |
| H10 | Xtream (S6) | `xtream("127.0.0.1:8765", "user", "pa ss")` with `--serve` hosting a `get.php` fixture route | built URL masked in the edit form (`username=***&password=***&type=m3u_plus&output=ts`), password never in `state()` output or the terminal; screenshot `sources-xtream` |
| H11 | Duplicate / cap | `addSource` of an existing URL (case-changed host, default port); 51st add | `duplicate` with the existing key; `too_many` |
| H12 | Edit URL (S4) | `updateSource(k, {"playlistUrl": <fixture3>})` success and failure variants | success: new key, old dir removed, label kept; failure: old record and cache intact, error shown |

### 8.5 Live QA on the machine of record (after install)

1. Upgrade in place (`git -C ~/.config/omarchy/plugins/io.github.rmcdavid.iptv pull`, `omarchy restart shell`): guide shows the iptv-org list as before; `python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.local/state/omarchy-iptv/state.json")));print(d["version"],d["cacheLayout"],[(s["key"],s["label"],s["channelCount"]) for s in d["sources"]])'` prints `2 2 [('d5977d8a', 'iptv-org.github.io', 1475)]`; `find ~/.cache/omarchy-iptv -maxdepth 2 -exec stat -c '%a %n' {} +` shows `700` dirs, `600` files, no legacy files at the top level.
2. S1-S8 through the real overlay with the assets of docs/QA-ASSETS.md (a second iptv-org country list as source 2), screenshots per state.
3. `omarchy bar set io.github.rmcdavid.iptv playlistUrl <us.m3u>` while the Sources screen is open: the row appears/activates without reopening.
4. `omarchy-shell io.github.rmcdavid.iptv status | grep -c '://'` -> 0;
   `journalctl --user -t omarchy-shell --since -30min | grep omarchy-iptv | grep -c '://'` -> 0 after the full pass.
5. Security cases (new QA ids SEC-22..SEC-30): control-char and 16 KB
   pastes; `javascript:`, `data:`, `ftp:`, `/dev/zero`, `/proc/self/environ`
   refused inline; a label `--urgency=critical ${path}` renders literally
   and no notification fires; `state.json` mode `600` after five saves;
   `python3 bin/omarchy-iptv cache remove --cache-dir ~/.cache/omarchy-iptv --key ../../x`
   -> `bad_key` and nothing deleted; the Xtream password absent from
   `journalctl`, `ps`, IPC status and `state show`; removing the active
   source deletes exactly its directory (`ls ~/.cache/omarchy-iptv/sources`
   before/after).
6. Regression: the M1 live runbook (QA.md section 5) subset for US2-US7,
   the 10k open budget (PERF-02) and PERF-03.

## 9. Open risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | `FileView` path swapping. Verified on Quickshell 0.3.1 (appendix B): a `path` change reloads automatically (2 ms for a small file), a missing path fires `loadFailed` (error 2), `watchChanges` follows the new path (an atomic replace of the new file fired `fileChanged` and reloaded), BUT between `pathChanged` and `loaded` the view still reports `loaded: true` and `text()` of the OLD file, and an empty path fires nothing. | Only ever apply content from `onLoaded`/`onLoadFailed` (already the rule); never read `text()` on a path change; clear in-memory data explicitly when the path becomes `""`; `switching` refuses a second switch until the first load/failure arrives, so a stale read of the previous file cannot be attributed to the new source. |
| R2 | `updateEntryInline` round trip and no-op cases. It is synchronous in memory (lines 109-114) so latency is not the issue; it returns `false` when nothing changed and, silently, when the entry is a bare string (`Util.canonicalWidgetId(arr[i].id)` on a string is `""`, 1093; `omarchy plugin enable` writes `{id}` objects, `services/PluginRegistry.qml:526`, so only hand-edited files hit this). `mutateShellConfig` is not offered to non-bar plugins (654-656). | `persistActive` compares before calling and treats `false` as failure only when a change was needed; on failure it emits `sourcesPersistFailed` (the guide shows "Could not save settings; run `omarchy bar set ...`" [UX-ASSUMPTION]) and, as a fallback, runs `["omarchy", "bar", "put", pluginId]` then `["omarchy", "bar", "set", pluginId, "playlistUrl", url]` argv once (the CLI path normalizes the entry into an object; `PluginRegistry.setBarWidget` refuses non-objects with "widget entry must be an object"). Verified on this machine: the entry is an object. |
| R3 | CLI sets `playlistUrl` to a URL not in history / to an invalid value / to an empty string. | D3 adds it (S5); D16 synthesizes the status for invalid values and never runs the helper; an empty string yields the first-run state without touching history. Eviction at the 50 cap drops the least recently used non-active record and its cache, `console.warn` with the key only. |
| R4 | Hash collisions (32-bit key). | Identity is the URL; `allocateSourceKey` suffixes; both lookups (`findSourceByUrl`, `findSource`) are tested with a forced collision; the helper only ever sees keys. |
| R5 | Cache disk usage grows with history (EPG windows can reach tens of MB per source). | 50-record cap; startup prune ages EPG files of inactive sources after 24 h and deletes orphan directories; removal deletes immediately; typical footprint stays a few MB per source. |
| R6 | Two helpers at once (probe + refresh) double CPU/network for a moment. | Both bounded (64 MB, 180 s); one probe at a time; probes are user-initiated; acceptable. |
| R7 | Qt clipboard on the layer-shell overlay pastes empty in some compositor states (focus race right after open). | H4 verifies on Hyprland 0.56.2; the `wl-paste` argv fallback is one constant away and works without focus (wlr-data-control, verified). |
| R8 | 10k+ switch over the 150 ms budget in the V4 engine (estimate 100-130 ms). | H8 measures; the prepared-cache LRU (section 4.5) is the ready mitigation; the 50,000-channel cap bounds the worst case. |
| R9 | `refreshTimer.triggeredOnStart` becomes false (freshness-driven first fetch). | Documented in README/CHANGELOG; H1/H6 cover "fresh cache -> no fetch" and "stale -> fetch"; `r` and middle click still force a fetch. |
| R10 | The helper's `state` verbs rewrite state.json while the service holds a newer in-memory copy (both writers existed in M1; `stateFile.watchChanges` reloads the file, `Service.qml:757-766`). | Unchanged M1 behaviour; the helper carries `sources` through, so a CLI `favorite add` can no longer drop history; the service reload after `fileChanged` re-runs reconcile. |
| R11 | Playing channel absent from the new source after a switch. | Playback continues; zap yields nothing; `Enter` on another channel replaces as today. Documented. |
| R12 | Credentials now also in state.json. | 0600/0700 as before, README sentence, `public_state()` redaction, harness and journal checks in 8.5. |

## Appendix A. `tests/fixtures/source-urls.json` (excerpt, authored by Lane 1)

```json
[
  { "input": " HTTP://Provider.Example.TEST:80/get.php?username=u&password=p ", "ok": true, "kind": "http", "url": "http://provider.example.test/get.php?username=u&password=p", "host": "provider.example.test" },
  { "input": "FILE:///srv/tv/local.m3u", "ok": true, "kind": "file", "url": "/srv/tv/local.m3u", "host": "" },
  { "input": "provider.test/list.m3u", "ok": false, "code": "unsupported_scheme" },
  { "input": "/proc/self/environ", "ok": false, "code": "unsafe_path" },
  { "input": "http://h .test/", "ok": false, "code": "bad_url" },
  { "input": "", "ok": false, "code": "empty" }
]
```

## Appendix B. Verification commands (scratch directory, reproducible)

```
# host persistence path
sed -n 109,114p /usr/share/omarchy/shell/shell.qml          # persistShellConfig: sync in-memory, async atomic file write
sed -n 1078,1112p /usr/share/omarchy/shell/shell.qml        # updateEntryInline: full-entry replace, object entries only
sed -n 1654,1663p /usr/share/omarchy/shell/shell.qml        # IPC setBarWidget (omarchy bar set) -> PluginRegistry.setBarWidget
sed -n 55,140p /usr/share/omarchy/bin/omarchy-shell-config  # commit(): jq + mv + `omarchy-shell shell reloadConfig`
# clipboard
grep -n clipboardText /usr/lib/qt6/qml/Quickshell/quickshell-core.qmltypes
timeout 3 wl-paste --list-types                             # works from a background process (no focus)
# FileView semantics (no windows; scratch XDG_RUNTIME_DIR; absolute WAYLAND_DISPLAY)
FV_DIR=<scratch>/data XDG_RUNTIME_DIR=<scratch>/run WAYLAND_DISPLAY=/run/user/1000/wayland-1 timeout 15 qs -p <scratch>/root/shell.qml
#   -> pathChanged then loaded ~2 ms later; loadFailed 2 for a missing path; fileChanged after os.replace on the new path; "" path: no signal
# timing (node, 10k synthetic channels): parseChannels 11-17 ms, prepareChannels 10-32 ms, indexById 3-6 ms, scopeEntries 9-11 ms
# hashes: node -e 'console.log(require("./Model.js").fnv1a32("https://iptv-org.github.io/iptv/countries/us.m3u"))'  -> d5977d8a
# encoding parity: python3 -c 'import urllib.parse;print(urllib.parse.quote("a b!*()~-._/@:+",safe=""))' vs node encodeURIComponent + [!'()*]
```

## Reconciliation rulings (product owner, 2026-09-13)

`docs/UX-SOURCES.md` is authoritative for interaction and visuals; this
document is authoritative for storage, processes, and security. Where the
two use different names, the following applies and both lanes code to it.

| # | Topic | Ruling |
|---|---|---|
| SR1 | Identifiers | The state file keeps this document's field names (`key`, `url`, `epgUrl`, `lastUsed`, `fetchedAt`, ...). The guide never reads state objects directly: the service exposes `sources[]` as view objects built by one pure function `Model.sourceView(stateSource, activeKey, nowSec)` with the UX 8.1 names: `id` (= `key`), `label`, `kind` (`url`, `file`, `xtream`), `host` (derived, never a URL), `hasEpg`, `channelCount` (`-1` when never fetched), `groupCount`, `cachedAt` (= `fetchedAt`), `lastUsedAt` (= `lastUsed`), `active`. The service also exposes `activeSourceId`. |
| SR2 | Service actions | `addSource({label, playlistUrl, epgUrl, kind})`, `updateSource(id, fields)`, `removeSource(id)`, `switchSource(id)`, `buildXtreamSource({server, username, password, label})` (the Xtream form submit), `sourceForEdit(id)` (the only call that returns full URLs, used to populate the edit form), `retrySource(id)`, and `cancelProbe()` (from UX 8.1; add it). Return shape `{ok, code, message, id}`. Booleans `probing` and `switching`. |
| SR3 | Signals | `sourceProbeFinished({ok, id, channelCount, groupCount, reason, host})`, `sourcesChanged()`, `sourceSwitched(id)`, `sourceRemoved(id)`, `sourcesPersistFailed(reason)`. `reason` is already redacted. |
| SR4 | Mask rule | Fixed token `****` (UX) replaces userinfo, the fragment, and every query value except the non-secret keys `type` and `output` (this document's exception); scheme, host, port, path, and query keys stay visible; local paths are never masked. Reveal is `Ctrl+R` or the eye button, re-masked on blur, save, cancel, and paste. |
| SR5 | Limits | This document's caps are canonical: playlist/EPG URL 2048, label 64, server 512, username/password 256, 50 sources. `Model.LIMITS` carries them and UX copy quotes them. |
| SR6 | Validation codes | The code list in UX-SOURCES.md 5.4 is canonical for user-facing errors; the shared JSON fixture (tests/fixtures/source-urls.json) uses those codes and both the JS validators and the Python mirror must pass it. |
| SR7 | Probe semantics | Add, playlist-URL edits, and switching to a never-fetched source probe into the source's own cache dir and commit only on success (D7/D8, S8). Label and EPG edits commit immediately. Cancel aborts the probe and discards the new cache dir. |
| SR8 | CLI parity | `omarchy bar set ... playlistUrl` reconciles into the history with a derived label and `origin: cli`; an invalid value synthesizes an error status and never runs the helper (D16). |
| SR9 | Favorites and recents | Global, keyed by channel id, unchanged (D14). |
| SR10 | Lanes | Lane 1: `Model.js`, `Guide.qml`, `tests/Model.test.js`, `tests/Model.spec.qml`, `tests/fixtures/source-urls.json`. Lane 2: `Service.qml`, `bin/omarchy-iptv`, `tests/test_*.py`, `scripts/dev-harness/*`. Both build against the interface in this document; the product owner merges Lane 1 first. |

## Reconciliation rulings, round 2 (product owner, 2026-09-13, answering QA-SOURCES.md section 10)

| # | Answers | Ruling |
|---|---|---|
| SR11 | SRC-DEC-01 | `~` paths: the CLI path (`omarchy bar set`, origin `cli`) keeps accepting and expanding them (no regression from 0.1.0); the forms refuse them with the UX `relative_path` message. `validateSourceUrl(text, {kind, origin})` takes `origin` (`form` default, `cli`). The fixture pins both contexts. |
| SR12 | SRC-DEC-02 | One heuristic in Model.js, mirrored in Python: leading `//` -> `scheme`; text that looks like a host (contains `.` or `:` before any `/`, or contains `/` after a host-like token) -> `scheme`; otherwise -> `relative_path`. |
| SR13 | SRC-DEC-03 | `unsafe_path` stays synchronous with the message `Path not allowed`. |
| SR14 | SRC-DEC-04 | Duplicates are detected on the normalized URL (D4). |
| SR15 | SRC-DEC-05 | Adopt every parity fix QA listed: reject ports above 65535, bracket literals that are not valid IPv6 (`[hex:.%25]`), U+200B-U+200D, U+2060, U+FEFF, and backslashes in the authority; normalize numeric ports (leading zeros stripped, default ports dropped); `sanitizeInput` strips a leading U+FEFF. Vectors go into `tests/fixtures/source-urls.json` and both validators must pass them. |
| SR16 | SRC-DEC-06 | No auto-prefix anywhere: an Xtream server without `http(s)://` is `server_scheme`. D10's prefixing is withdrawn. |
| SR17 | SRC-DEC-07 | New code `server_userinfo`: `Server must not contain a username or password - enter them below`. |
| SR18 | SRC-DEC-08 | Credentials are never silently truncated: over-cap username/password/server produce `user_too_long` / `pass_too_long` / `server_too_long` (new code, `Server too long - max 512 characters`). `sanitizeInput` caps only labels and free text; URLs over cap are `too_long`. |
| SR19 | SRC-DEC-09 | Derived labels include `:port` when the port is non-default (UX 5.6). |
| SR20 | SRC-DEC-10 | `www.` is stripped from derived labels (UX 5.6). |
| SR21 | SRC-DEC-11 | Duplicate derived labels get ` 2`, ` 3` suffixes, compared case-insensitively (UX 5.6). |
| SR22 | SRC-DEC-12 | The label cap (64) counts Unicode code points in both languages (JS `[...s].length`, Python `len`). Enforced on write (forms and CLI); the helper truncates to the cap on read without error. |
| SR23 | SRC-DEC-13 | A failed add or first-run probe saves nothing (UX 1.2); the form keeps its values so re-submitting is the retry. An existing never-fetched record (CLI origin) stays with `not loaded yet`, and Enter on it retries. |
| SR24 | SRC-DEC-14 | `too_many` copy: `Sources is full (50) - remove one first`; at the cap the `Add source` and `Add Xtream login` rows and the `a`/`c` keys show that message instead of opening a form. |
| SR25 | SRC-DEC-15 | Persist failure copy on the result line: `Could not save settings - try omarchy bar set`. No argv CLI fallback in M2-01 (signal only; fallback deferred). The harness stubs nothing. |
| SR26 | SRC-DEC-16 | Enter is the retry. Rows never show error text, only `not loaded yet`; the result line shows the reason when a retry fails. `errorReason` stays on the view object for the result line. |
| SR27 | SRC-DEC-17 | SR4 stands (`type` and `output` visible). The UX wireframes 3.1.2, 3.3.1, and 4.4 are to be read with those two values un-masked; the lead fixes the wireframes in a docs pass. |
| SR28 | SRC-DEC-18 | One spelling everywhere: `Not an M3U playlist`. |
| SR29 | SRC-DEC-19 | `Model.LIMITS` is canonical; named constants may alias it. |
| SR30 | SRC-DEC-20 | At the v0.2.0 release the installed clone's `origin` is re-pointed to `https://github.com/rmcdavid/omarchy-iptv.git` so `omarchy plugin update` behaves as for any user. |
| SR31 | SRC-DEC-21 | The harness gains verbs `cancelProbe`, `editMasked(id)` (masked strings only), `signals()`, `state()` exposing the form fields (masked values and lengths, focus, mode, returnMode), and `failPersist` to simulate a persist failure. |
| SR32 | SRC-DEC-22 | List order: the active source first, then by `lastUsedAt` descending, then never-used sources in the order added. UX 5.2 adopts this sentence. |
