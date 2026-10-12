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
| D1 | Where the active source lives | (a) shell.json entry (today); (b) state.json `activeKey`; (c) both | **(a) unchanged: `playlistUrl` / `epgUrl` on the bar entry** (M2-SOURCES decision 1) | `updateEntryInline` replaces the entry with `{id} + settings` in a clone of `shellConfig`, then `persistShellConfig` sets `shellConfig = payload` synchronously and writes the file with an atomic `FileView` (lines 1078-1112, 109-114, `userConfigFile` 134-141). `onShellConfigChanged` (67-71) fires `pluginsChanged()`, whose `Connections` handler calls `syncPluginApis()` (1053-1058), which reassigns `shellApi.barConfig` (879) -- the same object our `settings` binding already reads (`Service.qml:56`). So a write from QML propagates to the service in the same event loop turn, with no file watcher in the path, and `omarchy bar set` arrives through the identical chain (`omarchy-bar:361` -> IPC `setBarWidget` 1654-1663 -> `PluginRegistry.setBarWidget` -> `shellConfigMutator` -> `mutateShellConfig` 162-166 -> `persistShellConfig`). Storing an `activeKey` in state would create a second writer for one fact. **Amended 2026-10-09 (D-SINK-18): this row is now understood to be the ROOT of that defect, and the choice it records is no longer the one that would be made today.** Identifying the active source by its URL means a provider credential MUST live in the host's `shell.json` for the plugin to know which source is active -- a file this plugin does not own, whose packaged default is 0644, and whose writer the lead measured on 2026-10-09 to preserve whatever mode it finds (0644 in, 0644 out, content changed), so the plugin cannot assume the container is private. The reasoning above is not wrong about its own question: a second writer for one fact is a real cost, and the shell.json entry really is the one place the host and `omarchy bar set` already agree on. What it never weighed is that this particular fact IS the credential, so the cheapest identifier available was also the one that forced the secret into the borrowed container. **The containment that ships now is the mode shield** (`ARCHITECTURE.md` section 6, D-SINK-18; standard 11): the helper's `config shield` makes that one file deny group and other BEFORE a URL is persisted into it, and a persist that carries a URL is refused when it cannot. That narrows who can read the file; it does not stop the credential being there, and it is not presented as the answer. **The answer is to name the active source by its KEY and keep the URL only in the plugin's own 0600 state, and that is FILED SEPARATELY by the lead with its own id and its own round -- do not start it from a D-SINK-18 lane.** It is a migration rather than a patch: `Service.qml:199-201` still says the active source is `playlistUrl` / `epgUrl` on the bar entry, `activeSourceKey` (`Service.qml:247`) IDENTIFIES the active source by matching that URL against `state.json`, `state.json` has no `activeKey` at all (section 2.1), and the change touches a documented configuration surface that `omarchy bar set` and D16 both write through. The id of that filing is not assigned in this round and is UNVERIFIED from this document: read it off the board in `docs/STATUS.md`. **Continued 2026-10-09 (D-SINK-19): the filing is D-SINK-19, and the product owner approved it the same day as a release of its own; built 2026-10-11 in two rounds, the second after an adversarial review of the first.** This row's choice becomes **(b)**: the active source is named by `activeKey` in `state.json` (section 2.1), read through `Model.activeKeyOf`, and the bar entry carries the source's key (`sourceKey`) in place of its URLs. The cost this row weighed and chose against -- a second writer for one fact -- is REAL and is now accepted rather than argued away, because the fact being written is a credential and the borrowed container is the wrong place to keep one; `Model.pointerWritePlan` orders the two writers (state first, entry waits for a parked state save). The rulings that carry it are SR35-SR40 at the end of this document, each with its 2026-10-11 amendment where the review overturned part of it; the original text above stands as written, because a decision edited to read as though it always said this teaches nobody anything. |
| D2 | Where the history lives | (a) state.json v2; (b) extra keys on the shell.json entry; (c) a file in the plugin dir | **(a) `state.json` version 2, key `sources`** (M2-SOURCES decision 2) | Already 0600 in a 0700 dir (S-02 fixed: `state init`, `Service.qml:933-953`), already read and written by both QML (`Model.parseState`) and the helper (`normalize_state`, `bin/omarchy-iptv:1557-1576`). shell.json is host-owned and schema-declared (manifest `barWidget.schema`); the plugin dir is never written at runtime (PRODUCT.md decision 6). |
| D3 | Reconciling settings with history | (a) service observes settings; (b) helper scans shell.json; (c) guide-only | **(a) `Model.reconcileSources` runs in the service on state load and on every `playlistUrl` / `epgUrl` change** | The service already re-evaluates `settings` on every shell.json change (decision 7, `Service.qml:53-68`, `onPlaylistUrlChanged` 671-678). Reconcile is pure and idempotent: a URL already in history bumps `lastUsed` (only when the active key actually changed) and adopts a changed `epgUrl`; an unknown URL is added with a host-derived label and `origin: "cli"` (S5). No helper run, no extra IPC. **Amended 2026-10-11 (D-SINK-19, round 2).** `Model.reconcileSources` is still the function that adopts a URL, and SR8 still holds for a URL the service has not consumed; what sits in front of it now is `Model.reconcileAction` (what a settings change MEANS: `adopt`, `migrate`, `ignore`, with `adoptEpg` decided independently) and `Model.adoptActiveSource` (what the active source IS: a fresh entry URL first, then the state's key, then the entry's mirror, then nothing), both pure and node-tested; `Service.reconcile` only moves the snapshot and hands the plan on. Two things this row said are no longer true: "on every `playlistUrl` / `epgUrl` change" -- an EMPTY value is a no-op now, not a change the plugin acts on, since the plugin itself empties those keys on every write; and the adopted key is now written INTO the returned state (R2), where this row's first version returned it as an out-param only and the service never wrote it. What this row never claimed and the project had quietly come to rely on is also gone: the URL in `shell.json` was an accidental SECOND COPY of the active source, so a lost `state.json` was rebuilt from it on the next start. It is not any more, `Model.sourceKey` is one-way, and the README says so (SR39 cost 3). |
| D4 | Source identity and key | identity: raw string / normalized URL; key: fnv1a32 / fnv1a64 / sha256[:16] | **Identity = normalized playlist URL (section 3.1). Key = `fnv1a32(normalized)`, 8 lowercase hex, suffixed `-2`, `-3`... if that key is already used by a different URL** | `fnv1a32` exists in both languages with pinned vectors (`Model.js:194-229`, `bin/omarchy-iptv:269-275`); channel ids already use it. sha256 in QML JS would mean ~60 new lines of hand-rolled hashing in `Model.js` (no `Qt.sha256` in node, no `crypto` in the Qt engine). 32 bits is enough because the key is only a directory name: identity is the URL string, lookups compare URLs, and the suffix rule makes a collision harmless. P(collision) at the 50-source cap is ~3e-7. **Amended 2026-10-11 (D-SINK-19). Half of this row is overturned and the half matters, so read the split before you cite it.** **IDENTITY IS NOT OVERTURNED**: identity is still the normalized playlist URL, the key is still `fnv1a32(normalized)` through `Model.sourceKey` with the same suffix rule, duplicates are still detected on the normalized URL (SR14) through `Model.findSourceByUrl`, and nothing in section 3.1 moves. What is overturned is the clause "32 bits is enough **because the key is only a directory name**", because the key is no longer only a directory name: it is now what NAMES the active source, in `state.json`'s `activeKey` and on the host's bar entry as `sourceKey` (D1 as continued, SR35). The two consequences are different questions and are answered separately in SR36 -- collisions are unaffected, because lookups still compare URLs and `Model.findSource` matches a key only within the user's own records, while DISCLOSURE is new, because a key in a file other local accounts can read is a 32-bit confirmation of a guessed URL. This row was not wrong. It answered the question it was asked; what M2 never asked is which CONTAINER the identifier has to live in and who owns that container, and it took the fourth maintainer finding in four days to ask it. |
| D5 | Per-source cache layout | (a) `<cacheDir>/sources/<key>/` with the existing names; (b) prefixed files in one dir; (c) key in the file names | **(a) `~/.cache/omarchy-iptv/sources/<key>/{channels.json, playlist-status.json, epg-now.json, epg-status.json, epg-window.txt}`** | The helper takes `--cache-dir` on `playlist`, `epg` and `play` (`bin/omarchy-iptv:1641,1647,1659`) and derives every file name from it, so no helper contract changes (section 5 shapes untouched). The service's four cache `FileView`s only need a different `path` prefix (`Service.qml:710-755`). Migration: a new helper verb `cache migrate` renames the legacy files from `<cacheDir>/` into `sources/<key>/` once (section 2.3). |
| D6 | Cache removal and pruning | (a) `rm -rf` argv from QML; (b) helper verb; (c) leave orphans | **(b) helper verbs `cache remove --key K` (on removal, S7) and `cache prune --keep K...` (once per service start; also ages EPG files of inactive sources)** | The helper validates the key (`^[0-9a-f]{8}(-[0-9]{1,3})?$`), builds the path with `os.path.join` under `sources/`, refuses anything whose realpath escapes, deletes only the five known file names plus temp files and then `rmdir`s -- no recursive delete of unknown content. QML never composes a delete. |
| D7 | What `switch` does | commit first vs fetch first | **Warm source (`fetchedAt > 0`): commit immediately, redraw from cache, refresh in the background if stale. Never-fetched source: probe first (D8)** | S3 asks for an instant redraw; a source with a cache can always be shown. Steps and budget in section 4.5. |
| D8 | Adding a source (S1, S8) | (a) write settings, let the normal refresh fail; (b) fetch into the new dir, commit on success | **(b) probe-then-commit through a dedicated `sourceProbeProc`** | S8: "a fetch failure keeps the previous active source and shows the reason". With (a) the failing URL would already be active and the guide would show the error empty state. With (b) the previous source keeps playing and refreshing; the new record stays in history with `fetchedAt: 0` and a session-only error so the user can edit and retry. Same code path for S1 (no previous source). |
| D9 | How paste reaches the field | (a) Qt clipboard through a `qs.Ui` `TextField`; (b) `Quickshell.clipboardText`; (c) `wl-paste` via `Process` argv | **(a) primary: real `TextField`s (locked decision 5) get Ctrl+V / Shift+Insert from `QQuickTextInput` (`QKeySequence::Paste`) through Qt's Wayland clipboard; (c) `["wl-paste", "--no-newline", "--type", "text"]` is the fallback behind one function** | Precedent in the shell: the network panel's passphrase `TextField`s sit on a layer-shell surface with keyboard focus (`Ui/KeyboardPanel.qml:98`, `plugins/panels/network/Panel.qml:1841-1870`) and users paste passphrases there; `Ui/TextField.qml:18` is a Qt Quick Controls `TextField`. Qt receives `wl_data_device.selection` when our surface has keyboard focus, which the guide holds exclusively while open (`Guide.qml:617`). Verified here: `wl-paste --list-types` works from a background process (wlr-data-control, no focus needed), so (c) is a reliable fallback; `Quickshell.clipboardText` (quickshell-core.qmltypes:998-1002) is the same Qt clipboard as (a) and is only useful for a synthetic field. The harness scenario H4 (section 8.4) verifies (a) on the live shell; if it pastes empty, Lane 1 flips `pasteViaProcess` to true. Either way the pasted text is data: sanitized by `Model.sanitizeInput` before it enters the field (section 6). **Overturned 2026-10-11 (D-CLIP-1): (a) is withdrawn and (c) is the ONLY path -- `pasteViaProcess` is `true` for good (`Guide.qml:592` on lane commit 44b250b), and not because H4 pasted empty.** The reasoning above was right about its own question and silent on a cost nobody priced: a real `TextField` does not merely RECEIVE the Wayland clipboard on a paste, it SUBSCRIBES to it, and on the released Qt 6.11.2 (and 6.12.0) that subscription reads the whole offer into `omarchy-shell` synchronously on every clipboard change by any application, with a 1 s per-read timeout and no total limit (`docs/ARCHITECTURE.md` section 6, D-CLIP-1; measured +238 MB inside 600 ms of a 100 MB offer, +0 with `readOnly: true`). Locked decision 5 still holds -- the fields ARE real `TextField`s, for the kit's chrome, caret, selection and navigation -- but they are `readOnly: true` always, the plugin applies every edit to the model itself (`Model.editInsert` / `editDelete`, with Qt's word boundary measured into `tests/fixtures/form-edit.js`), and paste is `Service.requestClipboard`: since R8 (51866a3) the helper's `clipboard` verb, which runs the argv above with a pipe, reads at most 32 KiB from it (`Model.CLIPBOARD_MAX_BYTES`: 8,192 UTF-16 units x 4 bytes) under a 5 s deadline, terminates the child at the cap, EOF or the deadline, and prints one JSON line the shell parses with `Model.parseClipboardReply`, emitting the text only on an ok reply; the shell's 8 s `Model.CLIPBOARD_WATCHDOG_MS` is the outer bound and kills a helper that has not answered. The shell holds only the reply, never the output (measured +0 MB over a paste of a 100 MB offer, against +298..+304 MB when the shell ran `wl-paste` itself at 44b250b). `Quickshell.clipboardText` (b) is the same read as (a) in the same process and is likewise withdrawn; `Guide.qml`'s `clipboardText()` survived at 44b250b only as the line the accessibility fidelity transform pinned, unreachable, and both were deleted at 51866a3. The precedent cited -- the network panel's passphrase fields -- is not a counter-argument but the same exposure in the host, reported upstream. |
| D10 | Xtream URL construction | build in QML / in helper | **`Model.xtreamUrls` (JS only; the helper never builds Xtream URLs)** | Rules in section 3.4: server normalized to `scheme://host[:port][/base]` **an explicit scheme is REQUIRED** -- `xtreamUrls` refuses a bare host with `server_scheme`, "Server must start with http:// or https://", and no caller prepends one. This row said "default `http://` when no scheme -- Xtream panels are plain http on :8080 far more often than not" until 2026-10-07, when D-DOC-7 found the code had never done that. The refusal is the safer behaviour and it is the shipped one: the plugin does not choose cleartext for a user who did not ask for it. A user who types `http://` still gets it, with the password in a cleartext query string, which is D-SINK-14, `get.php?username=U&password=P&type=m3u_plus&output=ts` and `xmltv.php?username=U&password=P`, values percent-encoded with the RFC 3986 unreserved set so node, the Qt engine and Python `quote(safe="")` agree. Saved as a normal source (`origin: "xtream"`); the password exists only inside the URL. |
| D11 | URL validation shared with the helper | duplicate rules / one spec | **One algorithm, `Model.validateSourceUrl` and helper `validate_source_url`, pinned by `tests/fixtures/source-urls.json` read by both suites; `resolve_source` calls the Python one** | The helper's `resolve_source` (`bin/omarchy-iptv:544-558`) already defines the accepted set (`~`/`/` paths, `http(s)://` with a host, `file://`); the JS side mirrors it and both gain the same two additions: a 2,048-character cap (`too_long`) and refusal of control characters (`bad_url`). The guide rejects inline (S8) with the same code the helper would return. |
| D12 | Masking for display | host only / mask query / mask all | **Lists: label + host (`Model.hostOf`). Edit field: `Model.maskUrl` = `scheme://[***@]host[:port]/path?name=***&...` with every query value masked except `type` and `output`; a reveal key shows the raw URL; paths shown as-is** | M2-SOURCES decision 4. Credentials of Xtream and most providers are query values or userinfo; parameter names and the path let the user recognise the URL. Local paths are the user's own filesystem. |
| D13 | Length caps | -- | **URL 2,048; label 64; Xtream server 512, username/password 256 each; state `sources` 50 records** | Provider URLs are 100-300 characters; 2,048 is the common practical URL cap and bounds the helper's `OMARCHY_IPTV_URL` environment value (it bounded argv until D-SINK-8) and state.json (50 x ~600 B = 30 KB). `TextField.maximumLength` enforces the same numbers in the UI. |
| D14 | Favorites / recents across sources | per source / global | **Global, keyed by channel id (PRODUCT.md M1, ARCHITECTURE decision 6), unchanged** | `t:<tvg-id>` ids are shared by design (a favorite survives a provider switch when the tvg-id matches); `u:<hash>` ids are source-specific by nature. The guide already filters both lists against the loaded index (`Model.countFavorites`, `channelsForScope`), so entries of another source are invisible, not broken. Recents stay bounded by `maxRecents`; favorites are user-driven. Documented in the README; no per-source scoping in v0.2. |
| D15 | Helper surface | new `source` subcommand / extend `state` / new `cache` | **Extend `state` (v2 aware, URL-redacted output) and add one `cache` subcommand with `migrate`, `remove`, `prune` actions. No `state source ...` verbs** | Section 5 contracts untouched. The service does every history mutation in QML; the helper only touches the filesystem where QML must not (`rm`, `rename`, mode bits). `state show` must stop printing URLs once records carry them (section 2.4). |
| D16 | Invalid values set by CLI | run the helper anyway / synthesize | **The service never runs the helper for a `playlistUrl` that fails `validateSourceUrl`; it synthesizes `playlistStatus` from the validation result (like `helperTimeoutStatus`, `Service.qml:422-430`) and leaves `activeCacheDir` empty** | The helper would refuse with the same code; skipping it avoids creating a directory for garbage and keeps the guide's existing error empty state with a reason and no host. Same for `epgUrl` -> `epgStatus`. |

## 2. Data model

### 2.1 `state.json` version 2

```json
{
  "version": 2,
  "cacheLayout": 2,
  "activeKey": "d990c2e4",
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
| `hiddenGroups` | array of strings, max 200 | M3-01 (0.9.0). Group names, trimmed, de-duplicated, first occurrence wins; additive and optional like `savedSearches` and `session`, no version bump. Read by `Model.hiddenGroupList` and `normalize_hidden_groups` against one fixture. Taught to all three whitelists (`parseState`, `cloneState`, `normalize_state`) on the day it was added. |
| `activeKey` | string | D-SINK-19 (2026-10-09; built 2026-10-11). The key of the active source, matching the `key` rule below; **this file is where the active source is NAMED** (SR35), and `Model.activeKeyOf` reads it instead of matching a URL against the records. Additive and optional at version 2 exactly as `hiddenGroups` was: a file without it reads as no active source, an older build drops it on its next save, `Model.STATE_VERSION` stays **2**, and it is taught to all three whitelists (`Model.parseState`, `Model.cloneState`, `normalize_state`) through a type test, not `str()` -- the shared fixture `tests/fixtures/active-key.json` (sections `parse`, 18 cases, and `remove`, 5, run by BOTH suites; `resolve` 6, `adopt` 23 and `order` 8 by node) found `str()` coercing the number `12345678` into a valid-looking key on one side only. A value naming no record in `sources[]` resolves to `""` on every read and is CLEARED in the file by `Model.removeSource` and by `Model.adoptActiveSource` step 4, never left as a stale pointer (R3). |
| `sources[]` | array, max 50 | Ordered by `addedAt`; the UI sorts by `lastUsed` desc [UX-ASSUMPTION]. **After D-SINK-19 this array is the ONLY copy of the source list** (SR39 cost 3): `shell.json` no longer holds the active URL, so there is nothing left to rebuild a lost record from. |
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

**Amended 2026-10-11 (D-SINK-19, round 2): a fourth step, no version bump,
and it IS step 3 seen from the other side.** A bar entry carrying a playlist
URL together with a state that has no `activeKey` is the pre-D-SINK-19 shape
(0.13.5 and earlier). On the first reconcile of a service `Model.reconcileAction`
answers `adopt` for any URL on the entry, and `Model.adoptActiveSource` step 1
hands it to `Model.reconcileSources` exactly as step 3 above always did: a URL
the history knows makes that record active (its key is `Model.sourceKey` of
the normalized URL, the same key that already names the cache directory, so
the existing cache is FOUND rather than refetched); a URL it does not know is
ADDED, with origin `migrated` on the very first v2 run and `cli` after, and at
the 50-source cap the least-recently-used non-active record is evicted and its
cache directory removed -- the same rule as any CLI adoption (risk R3). The
first version of this paragraph said the step "creates no record and deletes
none"; that was false against the code and is withdrawn. "Must not lose a
source" (SR38) is graded as "keeps the count it went in with" over a two-source
state, one active and one not. The adopted key is written INTO the state
(`Model.withActiveKey`), the state is saved, and the entry is rewritten with
`sourceKey` and WITHOUT the URL keys (`Model.entryWith` drops
`Model.RETIRED_SETTINGS`), in that order: `Model.pointerWritePlan` makes the
entry write wait for a state save parked behind the start-up directories, so
a shell that dies between the two leaves the URL still on the entry -- the
idempotent old shape, adopted again next time -- and never a record nobody
points at (R5). It is idempotent: a second run finds the URL consumed (the
host keeps publishing the plugin's own strip one write behind, rule 9) and
the state's own key answering, and writes nothing. **Amended 2026-10-12
(D-SRC-15, round 3).** R5 covered the shell DYING between the writes; the
uninterrupted first start lost the pointer anyway on the round-2 tree,
because the helper's start-up `state init` chmodded the existing file, the
`stateFile` FileView reloaded on it, and `applyUserState` replaced the
adoption with the pre-adoption text while the save was still parked (the
mechanism and the measurement are in SR38's amendment and in `QA-RESULTS.md`
"D-SRC-15"). With R9-R11 (lane-key-s1) a reload never replaces in-memory
state that is newer than the file, the helper leaves a 0600 file alone, and
the entry mirror is written only once the parked save has landed. The step
as described here is OBSERVED on lane-key-s2, not inferred: `key-scenario.sh`
D1-D3 (the adoption parked, the key surviving `dirsReady` in memory and in
the file, the chmod-fired reload ignored -- the file is seeded 0644 on purpose
so R9 has to decide), M1-M6 (two records in, two out, the entry carrying the
key and no URL), J1-J3 (the second start writes nothing), 49 / 0 forward and
36 / 13 on `--baseline lane-key-r2`. The created-file shape (no `state.json`,
N1-N4) is a control on both trees: a FileView loaded over a missing path never
sees the helper's create. What no scenario observes is said so: the state
directory being unwritable at that start (R11's `drop` path) and a downgrade
followed by an upgrade (below). **Round 4 (2026-10-12, R13-R15; lane-key-t1
bb06540 under lane-key-t2's harness):** the same step read through the
round-4 harness (61 lettered checks) is 62 / 0 forward, 54 / 8 on `--baseline
lane-key-s2` (D3, W3, W6, F3-F7 -- round 4's own checks) and 38 / 24 on
`--baseline lane-key-r2` (lane B's transcripts); D3 now reads the chmod
reload's reason (`save-parked`) off a per-reason counter rather than a total
the own-write echo satisfied. The state directory unwritable at START is
still unobserved; unwritable under a RUNNING shell with the directories
ready is F1-F7 (`QA-SOURCES.md` SRC-MIG-18). **Round 5 (2026-10-12, R16;
lane-key-u1 under lane-key-u2's harness, 63 lettered checks):** 64 / 0
forward, 60 / 4 on `--baseline lane-key-t2` (L1, L2, F6, F7 -- the logo
toggle on the failed disk, SRC-MIG-22), 54 / 10 on `--baseline lane-key-s2`,
38 / 26 on `--baseline lane-key-r2`, 39 / 25 on `--baseline f275bde` (lane
B's transcripts). **Round 6 (2026-10-12; lane-key-v1 78ff442, the same 63
lettered checks):** 64 / 0 forward and 39 / 25 on `--baseline f275bde`, the
same letters, with the `held` half of W1, W3, W5, F2 and F5 now reading
`NOFIELD` there because `pointerState` omits a field the tree lacks (lane
A's transcripts). The round-6 code change -- a logo toggle BEFORE the first
state load writes the logo setting alone -- is observed in node and the
review's drivers, not here: no harness reaches that window (4.3). Step 1 above is unaffected
-- a v1 file still reads as `sources = []` -- and the downgrade sentence in it
has a consequence worth following through: the older build's `parseState`
drops `activeKey` on its next save, its `entryWith` copies every own key of
the entry so `sourceKey` SURVIVES on it (the older build does not own that
key), and its `ownedEntryPatch` writes `playlistUrl` beside it when the user
picks a source -- so a downgrade followed by an upgrade presents a MIXED
shape, a fresh URL beside a stale mirror, which step 1 resolves to the URL:
the source picked while downgraded is the one that comes back, and the owned
write strips the URL again. Derived from both builds' code (1a8dccd for the
older one) and pinned by the node suite's adopt cases; **UNVERIFIED BY ME** as
an observation, since nobody has run a downgrade and an upgrade back to back.

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

- `default_state()` -> `{"version": 2, "cacheLayout": 0, "favorites": [], "recents": [], "lastPlayed": null, "sources": []}` -- plus, since they were added, `"session": null`, `"savedSearches": []` and `"hiddenGroups": []`, in that order (a python test pins the key order against what the service writes).
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
| `emptyState()` | `{version: 2, cacheLayout: 0, favorites: [], recents: [], lastPlayed: null, sources: []}` plus `session: null`, `savedSearches: []`, `hiddenGroups: []` |
| `parseState(text)` | v1 or v2 text -> v2 object (section 2.2), records validated |
| `cloneState(st, patch)` | new state with `patch` keys replacing; used by every existing reducer |
| `withCacheLayout(st, n)` | `cacheLayout` set |
| `addSource(st, fields, nowSec)` | `{ ok, code, message, state, key }`; `fields = { playlistUrl, epgUrl, label, origin }`; codes `empty`, `too_long`, `bad_url`, `unsupported_scheme`, `unsafe_path`, `duplicate` (returns the existing `key`), `too_many` |
| `updateSource(st, key, fields, nowSec)` | `{ ok, code, message, state, key, urlChanged, replacedKey }`; label -> `labelCustom: true`; a changed playlist URL yields a NEW record (`key` new, `replacedKey` old, `fetchedAt: 0`, label/addedAt copied) and leaves the old one in place until the service confirms the probe (section 4.6); `unknown_source` |
| `removeSource(st, key)` | `{ state, removed }` (`removed` = record or null). **D-SINK-19 round 2 (R3): removing the ACTIVE record clears `activeKey` in the state it returns**, so the file never names a record it no longer holds; the helper's `remove_source_record` has done the same since the key existed, and the shared fixture's `remove` cases run both |
| `touchSource(st, key, nowSec)` | `lastUsed` bumped |
| `withSourceStats(st, key, status)` | `fetchedAt`, `channelCount`, `groupCount` from a parsed `ok` playlist status |
| `reconcileSources(st, playlistUrl, epgUrl, previousActiveKey, nowSec, origin, opts)` | `{ state, changed, activeKey, added, evicted, invalid }` (D3; `invalid` = validation result when `playlistUrl` is set but invalid; `evicted` = LRU keys dropped beyond `MAX_SOURCES`, never the active one). **D-SINK-19 round 2 (R2): the adopted key is written INTO `state` through `Model.withActiveKey`**, on the known-URL path and on the added path; `activeKey` stays as an out-param for callers that read it |
| *`activeSourceKey(st, playlistUrl)`* | **GONE (D-SINK-19).** It was the one function whose job was "name the active source from a URL", and it is deleted rather than left behind with no caller (the comment above `Model.reconcileSources` in `Model.js` says why). Identity by URL survives where it belongs, in `findSourceByUrl`. The active source is the rows below |
| `activeKeyText(value)` | the value as a key, or `""`: a STRING matching the key grammar, trimmed; a number, a list or anything else is `""`, which is also what the helper's `normalize_active_key` answers (shared fixture, `parse`) |
| `activeKeyOf(st)` | the state's `activeKey` when it names a record in `sources[]`, else `""`. The one resolver; `configured` is `activeKeyOf(state) !== ""` |
| `activeSourceRecord(st)` | that record, or null |
| `withActiveKey(st, key)` | the state with `activeKey` set (or cleared); the SAME object when nothing moves, so `changed` stays honest |
| `reconcileAction({ first, force, playlist, epg, lastPlaylist, lastEpg })` | `{ act, adoptUrl, adoptEpg, playlistChanged, epgChanged }`: `act` is `adopt` for a non-empty playlist input this service has not consumed (first reconcile, or different from the snapshot), `migrate` for a first or forced reconcile with no fresh URL, `ignore` otherwise; `adoptEpg` is the same rule for the EPG input, independently (R1, R4) |
| `adoptActiveSource(st, entry, nowSec, origin, { adoptUrl, adoptEpg })` | `{ state, key, changed, moved, adoptedUrl, adoptedEpg, invalid, added, evicted, writeEntry }`: resolves the active source in the order fresh entry URL -> state key -> entry mirror -> nothing (R1), attaches a fresh EPG input to the active record on any path, reports an invalid input without touching the key, and says whether the entry must be rewritten (it still holds a URL, or its mirror disagrees). `moved` -- a DIFFERENT source than before -- is the only thing that resets the status line |
| `pointerWritePlan({ keyMoved, dirsReady, savePending, savesInFlight, saveFailed })` | `{ steps, entryWaits }` with `steps` drawn from `save-state`, `defer-state`, `write-entry`, `write-entry-after-saved`, `wait-entry`: the state is saved before the entry is written, and the entry WAITS for the state save to LAND on every route (R5, then R13 on 2026-10-12): `write-entry` is immediate only when nothing of ours is outstanding -- no save parked, none in flight, the last one not failed -- otherwise the key is held and `Model.entryFlushDisposition` settles it from the FileView's `saved` / `saveFailed`; `Service.persistActive` executes the steps, and `stateInitProc`'s exit, `saved` and `saveFailed` settle a held entry. `savesInFlight` and `saveFailed` are round-4 inputs (lane-key-t1; `Model.pointerWritePlan`); the shared fixture's `order` section has 13 cases since round 4 (8 before) |
| `stateSaveLanded(viewText, askedText)` | R13 (lane-key-t1; `Model.stateSaveLanded`): whether the write the service last asked for is the one the FileView has just reported on -- the view's text IS the last text asked for, and that text is non-empty. "Landed" is read by CONTENT, not by counting `saved` signals, because a burst coalesces queued writes and a replaced one raises nothing (10 warm switches: 20 `setText`, 14 `saved` on lane-key-t1, 15 on lane-key-s2; lane A, 2026-10-12, `OMARCHY-PLUGIN-CONTRACT.md`) |
| `countReload(counts, reason)` | R15 (lane-key-t1; `Model.countReload`): the reload counter by reason -- a NEW object (a `property var` mutated in place raises no change signal) with `reason`'s count incremented, keyed by the string `Model.reloadDisposition` answered, so the counter cannot name a reason the decision does not; the service's `stateReloadsByReason`, reported through the harness's `pointerState` |
| `ownedWriteMode({ stateLoaded, savePending, savesInFlight, saveFailed })` | R16 (lane-key-u1; `Model.ownedWriteMode`): what an owned-entry write that is NOT the key mirror may carry -- `{ mode, reason }`, `patch` with `save-parked` / `save-in-flight` / `save-failed` whenever one of the three flags is raised, `heal` with `settled` otherwise; the three flags and nothing else (fixture section `ownedWrite`, 8 cases, the whole cube). **Amended 2026-10-12 (round 6, lane-key-v1 78ff442): a FOURTH input, `stateLoaded`, checked first -- anything but `true` answers `patch` with `state-not-loaded`, because before the first state load memory is the empty state and no save flag is raised, so the three flags alone answered `heal` there and a logo toggle stripped a URL set while the shell was down (the fifth review's data-loss P2). `heal` now means loaded AND nothing outstanding; the four inputs and nothing else; the `ownedWrite` section is 16 cases, the four-input cube.** |
| `persistFailureMessage(reason)` | R16 (lane-key-u1; `Model.persistFailureMessage`): the sentence for THE reason `sourcesPersistFailed` carried, over `Model.PERSIST_FAILURE_REASONS` (`state_write_failed`, `config_unsafe`, `persist_failed`); an unknown reason falls back to `persist_failed`'s sentence; what the guide renders on the result line and in the footer |
| `invalidInputBlocks(invalid, activeKey)` | whether a refused input becomes the guide's error state: only when there is no active source to show instead (D16, narrowed) |
| `sourceRows(st, activeKey, nowSec, errors)` | UI rows, sorted `active` first then `lastUsed` desc [UX-ASSUMPTION]: `{ key, label, host, kind, active, channelCount, groupCount, lastUsed, lastUsedText, fetched, epgConfigured, origin, errorReason }` -- no URL field, ever |
| `sourceForEdit(st, key)` | `{ key, label, labelCustom, kind, host, playlistUrl, epgUrl, playlistMasked, epgMasked, origin }` or null -- the only function that hands a URL to the guide |
| `sourcesSummary(st, activeKey)` | IPC list `{ key, label, host, active, channelCount, lastUsed }` |
| `entryWith(entry, patch, opts)` | full bar entry for `updateEntryInline`: every own key of `entry` copied EXCEPT `Model.RETIRED_SETTINGS` (`playlistUrl`, `epgUrl`, D-SINK-19), `patch` applied, `id` forced. Since R16 (round 5) `opts.keepRetired` true carries the retired keys over UNCHANGED -- the patch-only logo write while a state write is outstanding, and since round 6 before the first state load; "unchanged" is as the host PUBLISHES them, which on the host that publishes one write behind can be a copy one write old (D-SINK-20); the default is still removal, which is what the mirror and the settled toggle use. The host stores `{id}` plus exactly what it is handed, so a dropped key is GONE from the file rather than emptied; any owned write heals an entry left by an older build |
| `ownedEntryPatch(effective, overrides)` | every key in `OWNED_SETTINGS` (`sourceKey`, `showLogos` since D-SINK-19) at the value it should hold after this write (D-LOGO-2); the one place that decides what a write carries |
| `entryShieldDecision(shieldState, patch)` | the D-SINK-18 gate asked of the ENTRY about to be written: `persist` when the patch carries no URL-bearing key (every shipping write), `refuse` / `defer` when it does |
| `cacheStale(status, refreshMinutes, nowSec)` | true when `status.ok !== true`, `fetchedAt` missing/0, or `nowSec - fetchedAt >= refreshMinutes * 60` |
| `sourceReason(code)` | user-facing sentence per result code (section 4.3); `statusReason` gains the same codes |

## 4. Service.qml contract (Lane 2 provides, Lane 1 consumes; frozen)

### 4.1 Properties (read-only for the guide)

| Property | Type | Meaning |
|---|---|---|
| `sources` | var (array) | `Model.sourceRows(userState, activeSourceKey, nowSec, sourceErrors)`; re-evaluated on state, settings, error and `nowSec` changes |
| `activeSourceKey` | string | `Model.activeKeyOf(userState)` since D-SINK-19: the state's `activeKey` when it names a record, `""` otherwise. It used to be the key of the record matching the entry's `playlistUrl`; the entry no longer carries one. `configured` is this being non-empty |
| `activeSourceLabel` | string | label of that record, else `sourceLabel` (host) as today |
| `activeCacheDir` | string | `sourceCacheDir(cacheDir, activeSourceKey)` when `stateLoaded && cacheReady`, else `""` |
| `sourceCount` | int | `userState.sources.length` |
| `canAddSource` | bool | `sourceCount < MAX_SOURCES && !probing` |
| `stateLoaded`, `cacheReady` | bool | startup gates (section 4.4) |
| `probing` | bool | a `sourceProbeProc` run is in flight |
| `probingKey` | string | its key (`""` otherwise) |
| `switching` | bool | between a committed switch and the new cache's first load/failure |
| `sourceErrors` | var (object) | session-only `{ key: reason }` from failed probes, URL-free (`Model.statusReason`) |
| `settingsInvalid` | var or null | validation result when the `playlistUrl` INPUT is set but invalid (D16). Since D-SINK-19 it is the guide's error state only when there is no active source to show instead (`Model.invalidInputBlocks`); over a working source the refusal goes to the console and the source is left alone |

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
  while a change was needed (risk R2). **Amended 2026-10-12 (round 4, R13;
  SR25 as amended):** the codes are `state_write_failed` (the plugin's own
  `state.json` could not be written -- the FileView's `saveFailed`, raised
  ONCE per failure episode, the flag being sticky until a later write
  lands), `config_unsafe` (D-SINK-18) and `persist_failed`, which no
  shipping write raises any more: a refused KEY mirror (no host object, no
  writable bar entry) is logged by the one writer and repaired on the next
  start, never signalled, and both callers of that writer on lane-key-t1
  pass `announce` false (the logo toggle reports through its return value).
  `Service.lastPersistFailure` keeps the last code for the harness.
  **Round 5 (2026-10-12, R16, lane-key-u1):** the guide renders the
  sentence for THE reason it is handed -- `Model.persistFailureMessage` over
  `Model.PERSIST_FAILURE_REASONS`, an unknown reason
  falling back to `persist_failed`'s -- and the comment beside the signal in
  `Service.qml` says what the code does: both callers of the entry writer
  pass `announce` false, `persist_failed` is raised only for a caller that
  does not, and the refused logo write reports through its return value
  (DQ-C7 closed).

### 4.3 Actions and result shape

Every action returns `{ ok: bool, code: string, message: string, key: string }`
synchronously (`key` = the record concerned, `""` when none). Codes:

`ok`, `empty`, `too_long`, `bad_url`, `unsupported_scheme`, `unsafe_path`,
`duplicate` (key = existing record; the guide offers "switch instead"
[UX-ASSUMPTION]), `too_many`, `busy` (a probe or switch is in flight),
`unknown_source`, `not_ready` (state not loaded yet), `bad_server`,
`bad_credentials`, `persist_failed`, `config_unsafe` (D-SINK-18: the host's
`shell.json` could not be made private, so the URL was withheld rather than
written into a file other accounts can read; a distinct code from
`persist_failed` because the two sentences give opposite advice -- that one
sends the user to `omarchy bar set`, which is exactly what must not happen
with a credentialed URL). **`state_write_failed` (2026-10-12, round 4, R13):**
`Could not write state.json - check ~/.local/state/omarchy-iptv` -- the one
failure a switch, a remove or an adoption can have since the state write IS
the switch; never returned by a call (the write is issued synchronously and
the FileView reports on it later), always through `sourcesPersistFailed`.
Names a directory, never a URL and never `omarchy bar set`. The sentence is
in `Model.sourceErrorMessage`. **Round 5 (R16, lane-key-u1 b42b5ab):**
`Guide.showPersistFailed(reason)` renders `Model.persistFailureMessage` of the reason --
the reason's own sentence -- on the form's result line while a form is open
and in the footer otherwise; until then the guide rendered `persist_failed`'s
copy for every code, so a failed write in `~/.local/state` sent the user to
`omarchy bar set` (lane A's DQ-T1, the round-4 review's P2). Pinned by two
node checks, both red over an export of lane-key-t2: the routing read off
`Guide.qml` (the reason handed through, the message composed on both
surfaces, never `persist_failed`'s sentence by name) and the copy for every
reason `Service.qml` emits (derived from the service source; none names a
URL and only `persist_failed`'s names `omarchy bar set`, the fallback for an
unknown reason). The rendered line is UNVERIFIED on a display: no scenario
reads it. `persist_failed`'s sentence is still shown for one thing, through
the toggle's return value rather than the signal: a LOGO write the host
refuses outright, where `omarchy bar set` is sound advice because that write
carries no credential (DQ-U5). Asynchronous outcomes
(fetch errors) arrive through `sourceProbeFinished` with the helper's codes
(`network`, `http_403`, `not_a_playlist`, `timeout`, ...).

| Action | Behaviour |
|---|---|
| `addSource({ playlistUrl, epgUrl, label, origin })` | sanitize -> validate both URLs -> duplicate check (`findSourceByUrl`) -> cap check -> `Model.addSource` -> `saveState()` -> probe (section 4.6). Returns `ok` with the new key as soon as the probe starts. `origin` defaults to `"guide"`. |
| `updateSource(key, { label, playlistUrl, epgUrl })` | label only: state + save. `epgUrl`: validate, record update (since D-SINK-19 the record is the only store of a guide URL, so nothing is persisted to the entry for it). `playlistUrl` changed: `Model.updateSource` creates the replacement record, then a probe with `replaceKey`; on success the old record is removed, its cache removed, and the switch committed if the old one was active; on failure nothing else changes and the replacement record is dropped again. |
| `removeSource(key)` | `busy` if that key is probing. Removes the record, saves, queues `cache remove`, and if it was active `persistActive("")` (S7: back to the first-run state; playback, if any, continues). Since D-SINK-19 the state write is what clears the active source (`Model.removeSource` clears the pointer, R3); the entry mirror can still fail and is reported, but a stale mirror naming a removed record resolves to no active source. **[Corrected 2026-10-12: "cannot be refused" was an absolute the code did not support -- `FileView` has a `saveFailed` signal and round 2 connected to nothing, so an unwritable state directory refused the write silently while the entry mirror still went out. Since R11 (lane-key-s1) the service reads `saved` / `saveFailed`, counts writes in flight, and an entry mirror that WAITED for a parked save is written only once that save has landed; a remove or switch made with the directories already ready still writes the entry straight after `setText` (DQ-A2, the ungated sibling, listed as open). The failure path -- an unwritable state directory -- is UNVERIFIED live: no scenario makes the directory unwritable.]** **[Round 4, 2026-10-12 (R13): the sibling is closed -- the entry waits for the state write to land on the dirsReady route too (`Model.pointerWritePlan`'s `write-entry-after-saved`), and a refused mirror is logged, never reported as the removal failing: the call reports `ok` on the state write being ISSUED (SR25 as amended), and that write's failure arrives later as `sourcesPersistFailed("state_write_failed")`. The failure path is OBSERVED under a running shell: key-scenario F1-F7 on lane-key-t2 (the state directory 0500 with the dirs ready, a CLI set and then a switch: URL still on the entry, file untouched, the failure signalled once, the next start re-adopting; F3-F7 red on `--baseline lane-key-s2`). Unwritable at START stays unobserved, and F drives no remove on the failed disk (lane B).]** |
| `switchSource(key)` | no-op `ok` when already active; never-fetched (`fetchedAt === 0`) -> probe with commit; else section 4.5. **[2026-10-12, round 4 (R13): reports `ok` on the state write being issued -- the state write IS the switch; a later `saveFailed` arrives as `sourcesPersistFailed("state_write_failed")`; a refused mirror is logged (`no writable bar entry for the settings change`) and repaired on the next start, never `persist_failed`. `sources-scenario.sh`'s SR25 block moved to this contract on lane-key-t2: 66 / 0 under cage (lane B, 2026-10-12).]** |
| `buildXtreamSource({ server, username, password, label })` | `Model.xtreamUrls` -> `addSource({..., origin: "xtream", label: label or host})`. The password is never stored outside the URL and never logged. |
| `sourceForEdit(key)` | `Model.sourceForEdit(userState, key)`; the only way the guide obtains a URL; the guide binds it to the edit field only, never to a list delegate. |
| `retrySource(key)` | probe again a record with `fetchedAt === 0` (S8 retry) [UX-ASSUMPTION that the form has a retry affordance]. |

`persistActive(playlistUrl, epgUrl)` (internal): builds
`Model.entryWith(Model.findBarEntry(shell.barConfig, pluginId), { playlistUrl, epgUrl })`,
compares with the current settings (skip when equal) and calls
`shell.updateEntryInline(pluginId, entry)` (`services/PluginShellApi.qml:62-64`,
scoped to our own id at `shell.qml:648-653`). A `false` return while a change
was needed emits `sourcesPersistFailed("persist_failed")` (risk R2).

**Amended 2026-10-11 (D-SINK-19, round 2).** The signature is `persistActive(key)`,
`""` to clear. It sets the key in the state and runs `Model.pointerWritePlan`'s
steps: save the state (or park it behind `stateInitProc` when the directories
are not ready yet), then mirror the key into the entry through
`persistEntryKey` -> `Model.entryShieldDecision` -> `writeActive` ->
`writeOwnedEntry`, which is the ONLY `updateEntryInline` call in `Service.qml`
(the node suite counts the call sites) and records the own-write as
`Model.ownWriteOf(hostSettings, Model.ownedEntryPatch(settings, overrides))`.
The entry handed over is `Model.entryWith(...)` of the host's entry with
`Model.ownedEntryPatch` applied, so it carries `sourceKey` and `showLogos`, no
URL, and nothing the plugin does not own is lost. An entry write that waits for
a parked state save is `pendingEntryKey`, flushed by `stateInitProc`'s exit
AFTER the parked save -- **since R11 (2026-10-12, lane-key-s1): after that save
has LANDED.** `stateInitProc`'s exit records the helper's exit code
(`stateInitOk`), issues the parked save and calls `settleEntryFlush`, which
asks `Model.entryFlushDisposition` (`none` | `wait` | `flush` | `drop`); `stateFile`'s
`saved` and `saveFailed` call it again, so the flush happens on `saved` with
the in-flight count at zero, and `drop` (the helper failed, or the save did)
clears the held key, leaves the entry untouched and logs the reason with no
URL. `flushPendingEntry` has ONE call site, `settleEntryFlush`.
**Amended 2026-10-12 (round 4, R13-R15, lane-key-t1 bb06540).** The hold is no longer the parked route's
alone: `Model.pointerWritePlan` is handed `savesInFlight` and `saveFailed` beside
the three earlier inputs, answers `write-entry-after-saved` whenever a save
is issued by the plan, in flight (the deferred `persistActive` after
`adoptActive`'s own save -- "nothing moved" with a write still in the air
was the round-3 review's P1) or failed, and `write-entry` only when nothing
of ours is outstanding; `persistActive` holds the key on that step and calls
`settleEntryFlush` at once, so a hold over a save in flight waits for
`saved` and a hold over a stale failure with nothing in flight drops
immediately (the URL stays on the entry). A hold is ACCEPTED, not refused:
`persistActive` returns true with nothing written to the host yet. "In
flight" is decided by CONTENT: `saveState` keeps the text it asked for
(`lastSaveText`, deliberately never reported) and sets `stateSavesInFlight`
to 1; `saved` and `saveFailed` clear it only when `Model.stateSaveLanded` says the
view's text IS that text, because a burst of writes coalesces and a replaced
write raises no `saved` (a signal-counting version stuck at 5 of 20 and every
later hold waited for ever; lane A, measured live on lane-key-s2 and on its
first round-4 build). `saveFailed` logs `state.json could not be written`
(the error is an enum) on every failure and emits
`sourcesPersistFailed("state_write_failed")` once per episode (the flag is
sticky until a later write lands). `writeActive` passes `announce` false,
so a refused mirror is logged by the one writer (`no writable bar entry for
the settings change`) and repaired on the next start
(`Model.adoptActiveSource` step 2 rewrites a mirror that disagrees with the
state). `applyUserState` counts every reload by reason through
`Model.countReload` BEFORE deciding (`stateReloadsByReason`, R15), and
`Component.onDestruction` warns, with no URL, when `pendingEntryKey` is
still held at exit (DQ-B9). Structural pins in `tests/Model.test.js`: the
ignore branch RETURNS and `saveState` parks before `dirsReady` (R14), the
plan is handed both new inputs, and the failure is signalled from
`onSaveFailed` and never returned by `removeSource` / `switchSource`.
**Amended 2026-10-12 (round 5, R16, lane-key-u1 b42b5ab).** `persistActive` is not the only path onto the
host entry. `writeOwnedEntry(overrides, what, announce, keepRetired)` is the
one funnel in front of `updateEntryInline` and it has TWO callers:
`writeActive`, the key mirror, which R13 gated, and `setShowLogos`, the logo
toggle (`g` in the guide's Sources view, the consent's confirm), which R13
did not -- and the round-4 data-loss lens measured the second one losing the
record the first had just protected. The toggle wrote `{ sourceKey:
<memory>, showLogos }` with no plan and no disposition, and `Model.entryWith`
dropped the retired URL keys on every owned write by design, so after a
failed state write -- the URL on the entry being the ONLY copy of the input,
which is R13's whole reason for leaving it there -- one toggle moved the
mirror to a key the file did not have and took the URL off; the record then
existed nowhere durable and the next start lost it. Live under a nested cage
on lane-key-t2: the stored entry after the toggle named the in-memory key
with `playlistUrl` gone, `state.json` still the old key, the restart found
no record anywhere; at the Model layer 4 of 4 routes under both host shapes
and 308 of 4,392 driven sequences, all four that end with a logo toggle;
pre-existing on every D-SINK-19 tree, and reachable by an ordinary user
action on a disk the plugin had already reported as broken. R16: an
owned-entry write that is NOT the key mirror writes only the fields it owns
while anything of ours is outstanding. `ownedWriteMode({ savePending,
savesInFlight, saveFailed })` -- the three flags and nothing else [round 6:
four inputs, `stateLoaded` first; the amendment below] -- answers
`patch` (reason `save-parked`, `save-in-flight` or `save-failed`) or `heal`
(`settled`). On `patch`, `setShowLogos` logs `logo setting written alone;
the bar entry's source keys are left as they are (<reason>)` and writes
`{ showLogos }` with `keepRetired` true: `Model.entryWith` carries `playlistUrl`
and `epgUrl` over unchanged and `Model.ownedEntryPatch` takes `sourceKey` from
`settings` -- the host's own value, never memory's. On `heal` it writes as
before, every owned key at its effective value, the retired keys dropped.
Healing the entry (the key from memory, the retired fields stripped) is the
mirror's job and happens only once the file agrees with memory, through
`writeActive` under R13; the mirror never passes `keepRetired`. The
own-write record (rule 9, `Model.ownWriteOf`) is made against the host value
on both branches, so the patch-only write is recognised as ours: under the
lagging host the override holds `showLogos` until the host catches up and
lapses on the echo to the same value with nothing written and nothing
re-adopted; under the echoing host it is recorded against the already-echoed
value and is inert rather than lapsed (DQ-U4, the shape since D-LOGO-2).
Observed: sixteen node checks on lane-key-u1 -- the `ownedWrite` fixture
section (8 cases, the whole cube, the mode `patch` exactly when any flag is
raised; 16 cases since round 6), `Model.entryWith` with `keepRetired`, the R13 service-order driver
extended with `setShowLogos` under both host shapes (five cases each, every
entry write audited against the file's own pointer at the moment of the
write, the lens's L12), a structural pin over `setShowLogos`, the funnel and
the override, the copy check and the Guide routing pin -- 17 red over an
export of lane-key-t2 (the driver's got there is the loss itself:
`urlKept:false`, the mirror on the memory key, two records after the
restart) and 0 on lane-key-u1 (node 2,162); twelve one-decision mutations
each reddening at least one check; the lens's own drivers over the fixed
tree 4 -> 0 losses and 308 -> 0 of 4,392. At the sink: key-scenario L1/L2
inside F on lane-key-u2 (64 / 0; `--baseline lane-key-t2` 60 / 4 with L1
`stored:<C> playlistUrl:no`, L2 `keys:0 alone:0`, and F6/F7 restarting over
that entry finding no record for the input -- lane B's transcripts,
2026-10-12; SRC-MIG-22). The residual, DQ-U1, measured in the driver and the
lens's simulator and not live [round 6: observed live since, by the fifth
review's live lens, and on the board as D-SINK-20; the amendment below]:
under a host that publishes one write behind,
a patch-only toggle right after a heal carries the URL the heal removed BACK
onto the stored entry, because the host still published it and the patch
keeps what the host publishes [round 6: this said "holds", one word off];
it is the file's own active record's URL
(`sourceKey` comes from the override, the healed key, so the mirror still
names the file's pointer), re-adopted idempotently at the next start;
nothing enters the file the host did not publish and no record is lost; the
echoing host has no such lag. The D-SINK-18 sentence beside the toggle --
"this write can only ever take a credential OUT of that file" -- is
therefore stated for the heal write only. The sibling search lane A ran is
written out under the round-5 rulings below.
**Amended 2026-10-12 (round 6, lane-key-v1 78ff442, lane A; the fifth
review, two lenses over lane-key-u3).** Three corrections to the paragraph
above. (1) The decision takes FOUR inputs:
`Model.ownedWriteMode({ stateLoaded, savePending, savesInFlight, saveFailed })`,
`stateLoaded` checked first, anything but `true` answering `patch` with
`state-not-loaded`. Before `stateFile`'s first load `userState` is the empty
state, `activeSourceKey` is `""` and no save flag is raised, so the three
flags answered `heal` and a toggle in the start-up window wrote
`{ sourceKey: "", showLogos }` and stripped a URL set while the shell was
down -- its only copy. The data-loss lens measured 3 of 4 host/disk
combinations losing the record at the Model layer (pre-existing on every
D-SINK-19 tree) and graded it P2 on reachability: nothing on the guide's
path waits for the load (`openSources` needs `serviceReady`, `toggleLogos`
`inSources`), but under the lens's own cage the harness's first IPC answer
arrived 1,657 ms after detach with the state already loaded (74 s, loaded,
with a 1.3 MB state file), so no harness reaches the window and a human has
the shell's start-up window. The gate is in the service, where the write is
decided: `setShowLogos` hands `root.stateLoaded` beside the three flags, and
a caller that omits it gets `patch` -- the write that cannot lose a record
(lane A's OQ-V1, the lead's to confirm). (2) The patch-only write carries
the retired keys over as the host PUBLISHES them. On the host that publishes
one write behind (through 4.0.4) that copy can still hold a URL our last heal
stripped, and the patch writes it back onto the stored entry until the next
owned write strips it again: D-SINK-20 (P3), observed live by the fifth
review's live lens under cage with the fake host modelling the lag, and
bounded by its data-loss lens -- every re-carried URL was the user's own
input one write earlier and already a record in the 0600 state file, and
the echoing host never re-carries. The narrowing that looks obvious, keeping
the retired keys only while no own-write override is in force, strips the
only copy of an input whose state write failed -- the round-4 P1 back
through this writer -- and is NOT the fix; the `Service.qml` comment beside
the toggle, which said the patch put into the file "nothing the file does
not already hold", now says this and cites D-SINK-20. (3) What the funnel
composes the patch FROM is pinned: `writeOwnedEntry` builds it with
`Model.ownedEntryPatch` over `root.settings` -- the host's publish with our
own last write laid over it (rule 9) -- and never over `root.hostSettings`;
composed from the publish, the mirror's heal after a toggle carries the
PRE-toggle `showLogos` back on the lagging host (D-LOGO-2's shape), and that
one-token mutation read node 2,162 / 0 and live 64 / 0 on lane-key-u3.
Observed on lane-key-v1 (lane A, 2026-10-12): node 2,171 / 0 (+9: four
service-order driver cases under both host shapes -- the toggle before the
first load on a writable and an unwritable disk, a patch toggle and then
the mirror's heal, a switch while the directories are not ready and then a
toggle, a switch and then a toggle before `saved` -- and a structural pin
that `settings` and not `hostSettings` composes the patch in that call),
the fixture's `ownedWrite` section 16 cases, the four-input cube; the same
test files over lane-key-u3's code read 5 failures (the fixture, the cube,
the pre-load case under both hosts, the four-input structural pin), the
driver failing on the loss itself (`urlKept:false mirror:"" patched:0`,
no record anywhere after the restart); one-decision mutations on an export
of 78ff442 -- `stateLoaded` ignored 4 red, `savePending` ignored 4,
`savesInFlight` ignored 4 (the parked and in-flight routes had been pinned
by the cube alone, the review's P3), the funnel composing from
`hostSettings` 7, the service handing `stateLoaded: true` or omitting it 1
each (the structural pin); and the review's own drivers over lane-key-v1:
the pre-load proof 3 -> 0 losses, its 48,312-run matrix 3,939 -> 21
problems, the 21 being D-SINK-20's runs. Not observed live, said so: the
pre-load toggle (above), and the parked and in-flight toggles (node only;
key-scenario L drives `save-failed`).
Its four callers: `removeSource` (`""`), `switchSource`,
the probe commit (`newKey`, which differs from `rec.key` when a colliding record
appeared through the CLI during the probe) and `adoptActive`, deferred through
`Qt.callLater` because the host's settings must never be written from inside
their own change notification. `Service.applyOwnWrite` and `ownWriteForKey` (once a `Model.js` export; cited without the prefix because the ledger's symbol scan rightly refuses a bare citation of a symbol that no longer exists),
which nothing ever called, are deleted.
**Gated since D-SINK-18**: when the pair carries a non-empty URL the write
happens only after `config shield` has reported that `shell.json` denies group
and other -- private BEFORE the write, which is the fix -- otherwise the call
returns `false` and emits `sourcesPersistFailed("config_unsafe")`. A pair of
two empty strings is never gated, so `removeSource`'s `persistActive("", "")`
always proceeds. Before the shield's first run has exited the pair is held in
one slot and resolved by that exit; `persistActive` returns `true` for a held
pair, meaning accepted-not-refused, and nothing has been written at that
point. The full
entry is passed because `updateEntryInline` replaces the entry wholesale
(1093-1098): keys we do not own (`refreshMinutes`, `mpvArgs`, ...) survive
only because `Model.entryWith` copies them.

### 4.4 Startup sequence

1. `Component.onCompleted`: `mkdirProc` (`mkdir -p -m 700` of `cacheDir`,
   `cacheDir/sources`, `stateDir`, `runtimeDir`) -> `stateInitProc`
   (`state init`, now v2) -> `dirsReady`. Alongside it, and deliberately NOT
   in that chain: `config shield` (D-SINK-18). It touches none of the plugin's
   own directories and must not wait on them, and it is first among the things
   that have to happen before a URL can be persisted rather than merely early
   -- a persist arriving before its first exit is held, not written. Running
   it unconditionally here is also what repairs an install whose `shell.json`
   is already 0644 with a URL in it, at the next shell start rather than at
   the next source change.
2. `stateFile.onLoaded` -> `applyUserState` -> `stateLoaded = true` ->
   `reconcile()`. **[Amended 2026-10-12, D-SRC-15 (R9): `applyUserState`
   asks `Model.reloadDisposition` FIRST and returns on anything but `apply`. The
   `stateFile` FileView has `watchChanges: true`, and `onFileChanged` reloads
   on the service's own atomic write AND on a bare chmod of the file, mode
   changed or not (measured on a FileView probe, 2026-10-11); the helper's
   `state init` in step 1 is that chmod when the file is not 0600 (R10), and
   it arrives while the first save is still parked behind `dirsReady`. Applied,
   it replaced the adopted key and record with the pre-adoption file and the
   parked save wrote the loss (key-scenario D2 on lane-key-r2). Ignored:
   `own-write`, `save-parked`, `save-in-flight` (counted per `setText` in
   round 3; since R13 decided by CONTENT, `Model.stateSaveLanded`, because a burst
   coalesces `saved`), `save-failed`; applied: the first load and a file genuinely newer
   (a CLI `state ...` write with nothing of ours outstanding). An ignored
   reload runs neither `reconcile` nor `startCacheLayout`; the count is
   `stateReloadsIgnored` and, since R15, `stateReloadsByReason` -- one number
   per reason, which is what key-scenario D3 reads (`save-parked`). Step 1's `state init` exit also records
   `stateInitOk` and, after issuing the parked save, settles the held entry
   mirror (R11, the persistActive amendment in 4.3).]**
3. `reconcile()` (also from `onPlaylistUrlChanged`, `onEpgUrlChanged`):
   `Model.reconcileSources(userState, playlistUrl, epgUrl, activeSourceKey, now)`;
   on `changed` assign `userState`, `saveState()`; for each `evicted` key
   queue `cache remove`; set `settingsInvalid`. `activeSourceKey` is a
   binding on `userState` + `playlistUrl`, so it updates here.
   **[Amended 2026-10-11, D-SINK-19 round 2: `reconcile(force)` builds a
   plan with `Model.reconcileAction` over the INPUT pair and the snapshot of
   the last reconcile, moves the snapshot on every path, returns on an
   `ignore` plan with no fresh EPG, and otherwise calls `adoptActive`, which
   runs `Model.adoptActiveSource` over the state and the entry
   (`playlistUrl`, `epgUrl`, `sourceKey`), saves the state when it changed,
   queues `cache remove` for each evicted key, surfaces an invalid input
   through D16 only when it blocks, and, when the entry still holds a URL or
   its mirror disagrees, schedules `persistActive(out.key)` through
   `Qt.callLater`. `activeSourceKey` is a binding on `userState` alone.]**
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
| 2. `persistActive(rec.url, rec.epgUrl)` -- since D-SINK-19 `persistActive(key)`, state first and then the entry mirror, carrying the key and no URL -- -> `updateEntryInline`: two `JSON.parse(JSON.stringify(shellConfig))` of a few-KB object + one pretty `stringify` + `FileView.setText` (async) | host, lines 1078-1112, 109-114 | ~1-3 ms. The D-SINK-18 gate adds no process to this step: the verdict is already in hand from the startup run or the previous write's re-arm, and the decision is a pure function. The re-arm run starts AFTER the write and is not on the switch's path. The one exception is a persist issued before the shield's first exit, which is held until it: the shield starts at `Component.onCompleted`, so in practice that means a switch in the first moments of a shell start and not an ordinary one. The wait is a `python3` start, which section 6 of `ARCHITECTURE.md` measured at 98-113 ms idle for this file before any import; the verb's own work on top of that has not been timed, so the total is UNVERIFIED |
| 3. `shellConfig` assignment -> `onShellConfigChanged` -> `pluginsChanged()` -> `syncPluginApis()` -> `shellApi.barConfig` -> our `settings` binding -> `playlistUrl` / `epgUrl` change -> `reconcile()` (no-op) -> `activeSourceKey` -> `activeCacheDir` | host + service | < 1 ms. **Since D-SINK-19 this row is no longer on the switch's path at all**: `activeSourceKey` and `activeCacheDir` rebind from the STATE assignment in step 1, in the same turn, and the host's echo (which the plugin never receives for its own write, rule 9) changes nothing |
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
time (`busy`). Command: `Model.playlistProbeArgv(helperPath, sourceCacheDir(cacheDir, key))`,
with `rec.url` in the process environment as `OMARCHY_IPTV_URL`
(`sourceProbeProc.environment = Model.fetchEnvironment(rec.url)` immediately
before `running = true`) and not on the command line -- it rode argv as
`--url` until D-SINK-8, 2026-10-01.
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

**Amended 2026-10-11 (D-CLIP-1): the paragraph above describes a native path
that no longer exists.** The fields are `readOnly: true` always, so Qt
neither receives `Ctrl+V` nor edits anything; `pasteInto` is the only paste,
it runs on `StandardKey.Paste` (`Ctrl+V` and `Shift+Insert` both, measured
through `Keys.forwardTo`), it asks the service rather than owning a
`Process`, and the answer arrives through the `clipboardText(text)` signal
into `pasteFromProcess`, which sanitizes at `Model.formCapacity(id)` and
inserts through `Model.editInsert` over the range `Model.editRangeFor`
returns (the selection, or the whole of a masked value -- lifted out of
`Guide.qml` at 51866a3 so node reaches the decision). The `maximumLength`
on the control still mirrors the capacity but bounds nothing by itself,
because the control never edits; the bounds are the helper's 32 KiB /
8,192-unit cut on the `wl-paste` read (R8), re-applied by
`Model.parseClipboardReply`, and the guide's `sanitizeInput`. The
`field.insert(...)` call named above is gone with the native path -- not
because a read-only input refuses it (v6.11.2's `insert()` has no
`readOnly` guard, read at `qquicktextinput.cpp:2229`; `paste()`, `cut()` and
`undo()` do) but because the model is the value now: a `field.insert` would
edit the control's copy and the next bound write would overwrite it.

## 6. Security and privacy rules for the input surface

1. Clipboard and typed text are data. `Model.sanitizeInput` strips
   `[\u0000-\u001f\u007f-\u009f]` (so a multi-line paste collapses to one
   line), trims, and caps (URL 2,048; label 64; Xtream server 512, user and
   password 256). `TextField.maximumLength` mirrors the caps so a 16 KB paste
   never allocates a 16 KB string in a binding. Text is `Text.PlainText`
   everywhere it is rendered (coding standard; `StyledText` stays reserved
   for the plugin's own hint strings, `Guide.qml:1281`). **[Amended
   2026-10-11, D-CLIP-1: `maximumLength` no longer bounds anything by itself,
   because Qt never edits the field. A paste is cut by the service at
   `LIMITS.url * 4` (8,192 UTF-16 units) and then by `sanitizeInput` at the
   field's `formCapacity`; a typed or pasted insert is fitted to that
   capacity by `Model.editInsert`, and what exceeds the field's limit still
   reaches the validator as `too_long` rather than being cut silently
   (SR18). What the shell held in memory for a user-initiated paste of a
   huge clipboard before that cut, at 44b250b, was the service's
   `StdioCollector` string, the whole output, bounded in time by the
   watchdog and not in bytes -- lane A's DR-1, measured at +298..+304 MB
   and mostly kept over a 100 MB offer, and CLOSED by R8 (51866a3): the
   helper's `clipboard` verb reads at most `Model.CLIPBOARD_MAX_BYTES`
   (32 KiB) and the shell holds only its one-line reply, +0 MB over the
   same paste.]**
2. Scheme allow-list: `http`, `https`, `file`, absolute or `~` paths --
   the helper's `SOURCE_SCHEMES` (`bin/omarchy-iptv:61`) -- enforced by
   `validateSourceUrl` before any state write and again by
   `validate_source_url` inside `resolve_source`. Local paths under
   `/proc`, `/sys`, `/dev` are refused in both places; realpath, regular
   file, 64 MB cap stay in `read_local_source`.
3. No shell anywhere: every process is an argv array (`playlist`, `cache`,
   `state`, `clipboard` -- and inside that verb `wl-paste`, a
   `subprocess.Popen` of `CLIPBOARD_ARGV` with no shell); the URL is not an argv item at all but travels in
   the helper's environment as `OMARCHY_IPTV_URL` (D-SINK-8; `--url` stays
   for a human running the helper by hand); keys follow `--key` /
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
   only inside the URL string in state.json and shell.json **[since
   D-SINK-19: in state.json only; the plugin writes no URL into shell.json]**.
5. Files: `state.json` stays 0600 (created by `state init`, S-02; `FileView`
   keeps an existing mode); `sources/` and every `sources/<key>/` are 0700
   (`mkdir -p -m 700` and `ensure_private_dir`); every helper write is the
   existing `O_EXCL` temp + `chmod 0600` + `os.replace`. Removal deletes
   known file names only. **The host's `shell.json` is not in that list and
   was the gap (D-SINK-18, 2026-10-09).** The parenthesis above gives the
   reason `state init` exists -- `FileView` keeps an existing mode -- and the
   same sentence is true of the file the host persists our active URLs into,
   whose packaged default is 0644. Since the plugin cannot create that file,
   it does the other half: the helper's `config shield` denies group and other
   on `$XDG_CONFIG_HOME/omarchy/shell.json` (default `~/.config`) BEFORE a URL
   is persisted into it, on a file descriptor opened `O_NOFOLLOW`, reading the
   mode back from the kernel, and refuses rather than writes when it cannot.
   Exactly that one file: no parent directory is touched, because a 0600 file
   is sufficient whatever the directory modes are and `~/.config` is shared
   with everything on the system. Specified in `ARCHITECTURE.md` section 6.
   **[Amended 2026-10-11, D-SINK-19: the plugin no longer persists a URL
   into that file at all -- the entry carries the active source's key -- so
   the shield's job is now the two routes a URL still takes into it, the
   user's own `omarchy bar set` and an install upgrading into this release,
   and the gate in front of a persist is asked of the entry being written
   (`Model.entryShieldDecision`). SR40.]**
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
   (0600, 0700 dir), shell.json holds the active one (0600 **because the
   plugin makes it so before each write, not because it arrives that way** --
   D-SINK-18; this clause asserted 0600 as a property of the file and it is a
   property of one machine), each
   `channels.json` holds stream URLs (0600). README settings section gains
   the sentence, and now also says what the plugin changes about `shell.json`
   and what happens when it cannot. Removing a source deletes its cache and
   record; the
   shell.json entry is cleared when it was active -- and that clearing persist
   carries no URL, so it is never gated by the shield: an exposed file must
   still be emptiable, or the fix would hold the credential in place.
   **[Amended 2026-10-11, D-SINK-19: `state.json` holds every URL AND names
   the active source (`activeKey`); the shell.json entry holds the active
   source's KEY and no URL, on every write the plugin makes; removing the
   active source clears `activeKey` in the file (R3) and mirrors `""` into
   the entry. The README counts the files that hold a credential as two the
   plugin owns and one it does not own that a URL only passes through.]**
9. Concurrency bounds: one probe, one playlist refresh, one EPG run, one
   cache job at a time; each helper under the 180 s watchdog; at most 50
   sources; `cache prune` argv carries at most 50 keys.

7. The shell process never reads the clipboard, and no element it
   instantiates subscribes to it (D-CLIP-1, added 2026-10-11). Every form
   `TextField` is `readOnly: true` always, which is the one switch on
   `QQuickTextInput`'s `dataChanged` slot; the plugin edits the model value
   itself; the only clipboard read is `Service.requestClipboard`, the
   helper's `clipboard` verb as argv, which reads at most
   `Model.CLIPBOARD_MAX_BYTES` of a `wl-paste` child under
   `Model.CLIPBOARD_TIMEOUT_MS` and answers one bounded line, the shell's
   `Model.CLIPBOARD_WATCHDOG_MS` the outer bound, run on a user paste and
   never on a change (R8).
   The register of the sink, the measurement and the residuals is
   `docs/ARCHITECTURE.md` section 6; the gate is `docs/QA.md` 3.3.

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
| Model (node) | Lane 1 | `sanitizeInput`, every `source-urls.json` case through `validateSourceUrl`, `sourceKey` vectors, `allocateSourceKey` with a forced collision (a record pre-assigned the colliding key), `defaultSourceLabel` dedupe and caps, `maskUrl` vectors, `xtreamUrls` vectors and the percent-encoding vector, `parseState` v1 -> v2 (favorites/recents preserved, `cacheLayout 0`), every reducer carrying `sources`, `Model.reconcileSources` (known URL: no add, `lastUsed` only on key change, `epgUrl` adoption; unknown: add with `origin cli`; invalid; eviction at 51 never evicts the active), `addSource` codes, `updateSource` replacement semantics, `removeSource`, `withSourceStats`, `sourceRows` has no `url` key, `sourcesSummary` JSON contains no `://`, `Model.entryWith` keeps foreign keys, `cacheStale` | `node tests/Model.test.js` |
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
| H4 | Paste (D9) | `wl-copy -- "<fixture path>"` then `run.sh key -M ctrl v -m ctrl` and again with `-M shift -k Insert -m shift`; also `wl-copy` of a two-line string with a tab | field shows the path both ways; the multi-line paste arrives as one line (control chars stripped). If empty -> flip `pasteViaProcess`, re-run **[Superseded 2026-10-11, D-CLIP-1: `pasteViaProcess` is `true` for good and there is no native path to compare it with; the steps still apply and the expectation is the same text through `wl-paste`. The sink itself is observed by the scenario in `docs/QA.md` 3.3.]** |
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
| R2 | `updateEntryInline` round trip and no-op cases. It is synchronous in memory (lines 109-114) so latency is not the issue; it returns `false` when nothing changed and, silently, when the entry is a bare string (`Util.canonicalWidgetId(arr[i].id)` on a string is `""`, 1093; `omarchy plugin enable` writes `{id}` objects, `services/PluginRegistry.qml:526`, so only hand-edited files hit this). `mutateShellConfig` is not offered to non-bar plugins (654-656). | `persistActive` compares before calling and treats `false` as failure only when a change was needed; on failure it emits `sourcesPersistFailed` (the guide shows "Could not save settings; run `omarchy bar set ...`" [UX-ASSUMPTION]) and, as a fallback, runs `["omarchy", "bar", "put", pluginId]` then `["omarchy", "bar", "set", pluginId, "playlistUrl", url]` argv once (the CLI path normalizes the entry into an object; `PluginRegistry.setBarWidget` refuses non-objects with "widget entry must be an object"). Verified on this machine: the entry is an object. **[Amended 2026-10-12, round 4 (R13, SR25 as amended): the fallback argv never shipped (SR25), and a refused mirror is no longer a failure at all -- the state write is the switch, the refusal is logged and repaired at the next start; `sourcesPersistFailed` now carries the STATE write's failure, `state_write_failed`.]** |
| R3 | CLI sets `playlistUrl` to a URL not in history / to an invalid value / to an empty string. | D3 adds it (S5); D16 synthesizes the status for invalid values and never runs the helper; an empty string yields the first-run state without touching history. Eviction at the 50 cap drops the least recently used non-active record and its cache, `console.warn` with the key only. **[Amended 2026-10-11, D-SINK-19 round 2: an empty string is a NO-OP (R1/R4) -- the plugin itself empties the URL keys on every write, so an empty input cannot also be a command; the first-run state is reached by removing the source. An invalid value leaves a working source alone and is D16's error state only when there is none (`Model.invalidInputBlocks`). A value equal to the last one adopted is the host's unechoed copy of the plugin's own strip and is not read again. (A sentence that stood here until 2026-10-12 -- "so re-setting the SAME URL in one session after removing that source takes effect at the next shell start" -- was refuted by the review's data-loss lens: the owned write after the remove strips the stale echo and moves the snapshot, so the re-set value is fresh and adopted at once, on the lagging host and the echoing one alike; SR37 as amended.)]** |
| R4 | Hash collisions (32-bit key). | Identity is the URL; `allocateSourceKey` suffixes; both lookups (`findSourceByUrl`, `findSource`) are tested with a forced collision; the helper only ever sees keys. |
| R5 | Cache disk usage grows with history (EPG windows can reach tens of MB per source). | 50-record cap; startup prune ages EPG files of inactive sources after 24 h and deletes orphan directories; removal deletes immediately; typical footprint stays a few MB per source. |
| R6 | Two helpers at once (probe + refresh) double CPU/network for a moment. | Both bounded (64 MB, 180 s); one probe at a time; probes are user-initiated; acceptable. |
| R7 | Qt clipboard on the layer-shell overlay pastes empty in some compositor states (focus race right after open). | H4 verifies on Hyprland 0.56.2; the `wl-paste` argv fallback is one constant away and works without focus (wlr-data-control, verified). **[Moot 2026-10-11, D-CLIP-1: the Qt clipboard is not read at all; the "fallback" is the path. The risk that replaced it is a missing or stalled `wl-paste`, answered by the helper's deadline and `no_wl_paste` reply, the shell's outer watchdog, and a paste that changes nothing on failure.]** |
| R8 | 10k+ switch over the 150 ms budget in the V4 engine (estimate 100-130 ms). | H8 measures; the prepared-cache LRU (section 4.5) is the ready mitigation; the 50,000-channel cap bounds the worst case. |
| R9 | `refreshTimer.triggeredOnStart` becomes false (freshness-driven first fetch). | Documented in README/CHANGELOG; H1/H6 cover "fresh cache -> no fetch" and "stale -> fetch"; `r` and middle click still force a fetch. |
| R10 | The helper's `state` verbs rewrite state.json while the service holds a newer in-memory copy (both writers existed in M1; `stateFile.watchChanges` reloads the file, `Service.qml:757-766`). | Unchanged M1 behaviour; the helper carries `sources` through, so a CLI `favorite add` can no longer drop history; the service reload after `fileChanged` re-runs reconcile. |
| R11 | Playing channel absent from the new source after a switch. | Playback continues; zap yields nothing; `Enter` on another channel replaces as today. Documented. |
| R12 | Credentials now also in state.json. | 0600/0700 as before, README sentence, `public_state()` redaction, harness and journal checks in 8.5. **[Amended 2026-10-11, D-SINK-19: credentials ONLY in state.json and the cache, and state.json is the only copy of the source list (SR39 cost 3). The README tells the user what a backup of that file carries.]** |

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
# the container the host config is (D-SINK-18, 2026-10-09). Read-only, and the
# three facts the shield exists for. The lead's own FileView mode probe and the
# cp-under-umask reproduction are NOT here: they need a display and a scratch
# tree, and the measurements are carried by the D-SINK-18 row on the board.
# Re-read on 2026-10-09 by the docs lane: 700 / 755 / 755 / 600 and 644,
# matching the lead's table.
stat -c '%a %U %n' ~ ~/.config ~/.config/omarchy ~/.config/omarchy/shell.json
stat -c '%a %U %n' /usr/share/omarchy/config/omarchy/shell.json   # 644 root: the packaged default
grep -n 'cp -f' /usr/share/omarchy/bin/omarchy-refresh-config     # lines 32-33, 42: default -> user config
# and the verb that answers for it, run against a SCRATCH config so the real
# file is never touched (it prints a verdict and two modes, never the contents):
XDG_CONFIG_HOME=<scratch>/config python3 bin/omarchy-iptv config shield
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
| SR25 | SRC-DEC-15 | Persist failure copy on the result line: `Could not save settings - try omarchy bar set`. No argv CLI fallback in M2-01 (signal only; fallback deferred). The harness stubs nothing. **Amended 2026-10-12 (D-SINK-19 round 4, R13; overturned in part, not rewritten -- the text above is the 2026-10-09 record and stands as it was):** since D-SINK-19 the state write IS the switch, so `persist_failed` as "the switch failed because the host refused the entry" has no referent: a refused KEY mirror is logged (`no writable bar entry for the settings change`) and repaired on the next start by the adopt path, and is never reported on the result line, because that copy sent the user to `omarchy bar set` for a switch that had already happened. The failure a switch, a remove or an adoption CAN have is its own state write failing, reported from the FileView's `saveFailed` as `sourcesPersistFailed("state_write_failed")` with the copy `Could not write state.json - check ~/.local/state/omarchy-iptv` -- a directory, never a URL and never `omarchy bar set`. The harness still stubs nothing: `failPersist` removes `updateEntryInline`, and the moved checks assert that the switch COMPLETES (`ok`, active moved, switching released), that the stored mirror is unchanged, that the log line appeared and that nothing was signalled (`sources-scenario.sh` 66 / 0 under cage on lane-key-t2, lane B, 2026-10-12; the same harness over an export of dev 93bbd5d reads 62 / 4, the four reds being exactly the moved checks). SR33's reservation of the copy for a genuine failure stands; the genuine failure is now the state write, with its own code. What the Guide renders for that code is lane A's DQ-T1 (4.3). **Round 5 (2026-10-12, R16): closed -- `Guide.showPersistFailed(reason)` renders the reason's own sentence through `Model.persistFailureMessage`, pinned at the code by two node checks and UNVERIFIED on a display (4.3; `UX-SOURCES.md` 5.5, which also records once-per-episode signalling as a decision with its consequence).** |
| SR26 | SRC-DEC-16 | Enter is the retry. Rows never show error text, only `not loaded yet`; the result line shows the reason when a retry fails. `errorReason` stays on the view object for the result line. |
| SR27 | SRC-DEC-17 | SR4 stands (`type` and `output` visible). The UX wireframes 3.1.2, 3.3.1, and 4.4 are to be read with those two values un-masked; the lead fixes the wireframes in a docs pass. |
| SR28 | SRC-DEC-18 | One spelling everywhere: `Not an M3U playlist`. |
| SR29 | SRC-DEC-19 | `Model.LIMITS` is canonical; named constants may alias it. |
| SR30 | SRC-DEC-20 | At the v0.2.0 release the installed clone's `origin` is re-pointed to `https://github.com/rmcdavid/omarchy-iptv.git` so `omarchy plugin update` behaves as for any user. |
| SR31 | SRC-DEC-21 | The harness gains verbs `cancelProbe`, `editMasked(id)` (masked strings only), `signals()`, `state()` exposing the form fields (masked values and lengths, focus, mode, returnMode), and `failPersist` to simulate a persist failure. |
| SR32 | SRC-DEC-22 | List order: the active source first, then by `lastUsedAt` descending, then never-used sources in the order added. UX 5.2 adopts this sentence. |

## Reconciliation rulings, round 3 (product owner, 2026-09-14, after the D-LIVE-20/21 fix)

The live fix for D-LIVE-20 and D-LIVE-21 invalidated two earlier rulings.
These replace them.

| # | Replaces | Ruling |
|---|---|---|
| SR33 | SR25 | A `false` return from `shell.updateEntryInline` means the value was already stored, not that the write failed (shell.qml:1114). It must never surface as an error. The copy `Could not save settings - try omarchy bar set` is reserved for a genuine failure: no host object, or a bar entry that is not writable. A plugin applies its own write locally in the same turn and drops that override as soon as the host reports any other value, so an external `omarchy bar set` still wins. The echo path stays idempotent. The reason is recorded in `OMARCHY-PLUGIN-CONTRACT.md`: the host publishes `barConfig` one write behind and a plugin never receives the echo of its own write. **[2026-10-12: see SR25 as amended -- the genuine failure the copy was reserved for is now the plugin's own state write, with its own code and copy; a bar entry that is not writable is logged and repaired at the next start, not surfaced.]** |
| SR34 | SR31 | The dev harness fake must reproduce the host's plumbing exactly, including declaration order, comparing before persisting, returning `false` without persisting when nothing changed, and giving the writer no echo of its own write. A fake that is more forgiving than the host is a defect in the harness. The `failPersist` verb now removes the function entirely to simulate a genuine failure, since returning `false` no longer means failure. The verbs `setStored` and `hostEntry` are added. Any scenario suite that passes against known-broken code is not evidence; a fidelity change must be accompanied by a scenario that fails against the pre-fix code, and the before and after counts belong in the report. |

Standing rule from this incident, added to `CLAUDE.md`: never wait for the
host to echo your own write back before updating your own UI.

## D-CLIP-1 rulings (lead, 2026-10-11; numbered R1-R7 in the lane briefs, which is not this file's risk table)

Raised against the shipped 0.13.4 (omarchy-plugin-marketplace#11077) and
measured before any lane was briefed (`docs/QA-RESULTS.md`, "Sixth
maintainer finding"). These override D9, section 5's paste paragraph,
section 6 rule 1's `maximumLength` sentence, H4 and R7 above, each of which
is amended where it stands.

1. While the plugin form is open, NO editable `TextInput` exists in the
   shell: every form field is `readOnly: true`, always, focused or not,
   masked or not. Editing is the plugin's own: `handleFormKey` implements
   printable insertion, `Backspace`, `Delete`, `Ctrl+Backspace`,
   `Ctrl+Delete` over the model value, with the caret and selection the
   read-only control still maintains natively; navigation, selection, Home /
   End, `Ctrl+A` and mouse selection stay native.
2. Paste is the out-of-process path ONLY: `pasteViaProcess` true, `Ctrl+V`
   and `Shift+Insert` to `Service.requestClipboard`, `wl-paste --type text`
   as argv, cut at `Model.LIMITS.url * 4`, the child bounded by a watchdog
   that kills the CHILD, never the shell. Tightened by R8 (second round,
   51866a3, after DR-1 measured the shell taking the whole output in): the
   `wl-paste` child is the HELPER's, the helper reads at most
   `Model.CLIPBOARD_MAX_BYTES` under `Model.CLIPBOARD_TIMEOUT_MS` and
   answers one bounded JSON line, and the shell never holds more than that
   reply.
3. The password field keeps `echoMode` Password; `readOnly` does not change
   masking; `fieldDisplay` / `maskUrl` are unchanged.
4. Pure logic lives in `Model.js` and is called from node: `editInsert`,
   `editDelete`, `wordBoundary`, with Qt's own word boundary MEASURED on a
   real `TextInput` rather than assumed; `sanitizeTyping` and `formCapacity`
   apply as before, and an insert that would exceed the cap is refused with
   the existing over-cap behaviour, never cut.
5. Stated loss, not hidden: input-method composition does not reach a
   read-only `TextInput`, so accented characters cannot be typed into the
   label field; ASCII typing is unaffected; paste carries any Unicode.
   Recorded in the README and in UX-SOURCES.
6. Rule 15 sweep: `Guide.qml`'s form field is the only `TextInput`-derived
   element in the shipped QML; the search line is a plain `Text`; the host
   kit's `NumberField` is unused. Lane A and the docs lane extended it
   (`docs/ARCHITECTURE.md` section 6, "the siblings").
7. The gate observes the sink, not a string: a scenario runs the real
   `Guide.qml` under a nested headless cage, offers 100 MB of `text/plain`
   from a foreign producer inside that compositor, and asserts the shell's
   RSS and an IPC round-trip unchanged on the fixed tree and the read on
   `--baseline d55149b`; its compositor-free half runs in `scripts/check.sh`
   (`docs/QA.md` 3.3; landed as `scripts/dev-harness/clip-scenario.sh` at
   824ced4: live 18 / 0 at +0 MB, baseline 16 / 2 with L4 at +240 MB and L5
   at 746 ms, "clip preflight (7 checks)" in the gate).

## Reconciliation rulings, round 4 (product owner, 2026-10-09, D-SINK-19; amended 2026-10-11 and four times on 2026-10-12, after five adversarial reviews)

D-SINK-19 moves where the active source is NAMED. The product owner approved
it on 2026-10-09 as a release of its own, having been shown the three costs in
SR39 and accepted them. The first build (lane-key-code, e618fce) was reviewed
adversarially on 2026-10-11 by three lenses and found not shippable -- six P1
findings across the three, one of them refuted on measurement, the worst being
a CLI `playlistUrl` set while the shell was down that was discarded and then
erased from `shell.json` -- and the lead ruled R1-R8 for the repair. The
second build (lane-key-r2, r3) was reviewed the same way the same night and
found not shippable for one P1 the harness lane had measured live, D-SRC-15
(SR38 as amended), and for THIS document: five of the six rows below had
their 2026-10-09 text edited in place under a preamble that said otherwise.
The lead ruled R9-R12 on 2026-10-12, and R13-R15 later the same day after the
third review graded the one route R11 had not gated (the entry written with
the directories ready, before the state write landed) as a P1 and measured it
live; and R16 after the fourth review measured R13's own fix losing the
record through the second caller of the entry writer, the logo toggle, which
R13 had not gated; and R16 was amended after the fifth review (round 6) for
the one state its three flags could not name, before the first state load. The rows below now carry the 2026-10-09
ruling VERBATIM as lane-key-docs (55502af) recorded it -- the one copy that
predates both reviews -- and, where a review overturned part of it, dated
amendments beneath saying what the code on this tree does instead; nothing is
rewritten to read as though it always said this, and a reader comparing a row
against `git show lane-key-docs:docs/ARCHITECTURE-SOURCES.md` finds the
original as a prefix. D1, D3 and D4 above carry the same discipline.

Every row here belongs to D-SINK-19, which has a board row in `docs/STATUS.md`
and is therefore an id the defect-ledger check can see; every `Model.*` name
cited below is written bare, because the same script's symbol scan sees a
backtick-delimited `Model.<name>` and nothing else inside the backticks, so a
citation written as a call with its argument is invisible to it. Measured by
the docs lane on 2026-10-09: a synthetic id turned the check red, a renamed
symbol inside a bare citation turned it red, the same rename inside a call
citation did not. The SR numbers themselves are still joined to nothing -- 40
of them, cited from 29 tracked files, and no script validates the register;
that is rule 13's failure one register along from the defect ids, reported to
the lead rather than given an id this lane cannot put a board row behind.

| # | Replaces | Ruling |
|---|---|---|
| SR35 | D1, in part | **Where the active source is named.** The authority is `activeKey` in `state.json` (section 2.1), a file the plugin owns at 0600 inside a 0700 directory. `activeSourceKey` reads it; it no longer identifies the active source by matching a URL against the records. The bar entry carries the source's KEY, so the host's config still names what is playing and `omarchy bar set` still has a surface to write to, and once the plugin has settled that entry carries no playlist or EPG URL. The state is the authority and the entry is a mirror. What a hand-edited key on the entry does when the state names a different one is the code lane's to settle in this round and is **UNVERIFIED** from this document: read it off `Service.qml`. **Settled 2026-10-11 (R1, R3), after the adversarial review of the first build:** `activeSourceKey` is deleted rather than left with no caller (the comment above `Model.reconcileSources` says why); the state is read through `Model.activeKeyOf`, and the key the entry carries is named `sourceKey`. The state's key wins whenever it names a record; the entry's `sourceKey` is consulted only when the state names none (`Model.adoptActiveSource` step 3); a key naming no record is `""` on every read and is cleared in the file by `Model.removeSource` and by step 4, never a stale pointer. A hand-edited `omarchy bar set ... sourceKey <k>` is accepted by the host like any key -- READ off the host, not run: `setBarWidget` at `services/PluginRegistry.qml:342-380` ends `entry[String(key)] = value` with no schema lookup (`OMARCHY-PLUGIN-CONTRACT.md`, "read rather than run"; the half that WAS measured is `updateEntryInline` keeping an undeclared key through its own rewrite) -- and is ignored by the plugin unless it names a record and the state names none. |
| SR36 | D4, in part | **Identity is preserved; the "only a directory name" clause is not.** Identity stays the normalized playlist URL and the key stays `Model.sourceKey` of that normalized URL, with the suffix rule (D4 as amended). Collisions are unaffected: lookups still compare URLs, and `Model.findSource` matches a key only inside the user's own records, so the 50-source analysis in D4 still holds. Disclosure is new and is stated with its size rather than waved at: the key cannot be turned into a URL, `fnv1a32` being one-way and the only direction this project computes, but it IS a 32-bit CONFIRMATION of a guessed URL -- someone who can read the entry and can guess a candidate can hash the guess and check it. That is far less than the credential and it is not nothing. The key was always printed and always user-visible (the cache directory names it, `cache remove --key K` takes it, the README tells the user to `ls` them), but inside containers the plugin owns at 0700; what D-SINK-19 adds is a key in a file whose packaged default is 0644. So nothing here says the exposure is CLOSED: it is reduced from the credential itself to a check on a guess. *Unchanged by the review, 2026-10-11.* |
| SR37 | nothing; **extends SR8** | **CLI parity is preserved, and becomes input-only.** `omarchy bar set io.github.rmcdavid.iptv playlistUrl "<url>"` still adopts: the same `Model.validateSourceUrl` with `origin: "cli"`, reconciled into the history with a derived label and `origin: "cli"` (SR8, D3, SR11), an invalid value still synthesizing an error status and never running the helper (D16). `epgUrl` is treated the same way. SR8's sentence stands unchanged; this row only says what happens next. Once adopted, the plugin sets the active key and rewrites the entry with the key and without the URLs, so the value the user set is an INPUT and not a stored setting: set it, read the file back, and it is not there. That is SR39 cost 1, it is a documented behaviour rather than a bug, and the README says so at both places it shows the command. **Overturned in part 2026-10-11 (R1, R4), after the review found the first build DISCARDING the input on every first or forced reconcile:** "still adopts" holds for a URL this service has not consumed -- the first reconcile of a service (the shell start, which is where a value set while the shell was down arrives) and any value different from the one it last saw -- whether or not the reconcile was forced (`Model.reconcileAction`); a value equal to the last one adopted is the host's unechoed copy of the plugin's own strip (rule 9) and is not read again, else a state reload would resurrect a source the user had just removed. `epgUrl` likewise: a fresh non-empty value is attached to the ACTIVE record on any reconcile that sees it, an `ignore` plan included (D-SRC-02 stays closed), and stripped by the same owned write. The EMPTY value is a no-op for both keys: `omarchy bar set ... playlistUrl ""` and `... epgUrl ""` are WITHDRAWN as clear levers; the Sources screen and the helper's `state source` verbs clear. An invalid value is still D16 -- reported, never run -- but leaves a working source exactly as it was (`Model.invalidInputBlocks`), and is stripped from the entry too, because a refused value can still carry a credential. The README says all of this at both places it shows the command and in its settings table. **Amended 2026-10-12 (round 3, R12): an input is never stripped unadopted.** Round 2 stripped an `epgUrl` set while NO source was active in the same owned write that could not attach it, so the value was gone with no copy anywhere (review P2); it now stays on the entry until a source exists and a later reconcile attaches it to that source, and the service's EPG snapshot moves only for an input that reached a record (`Model.epgSnapshotAfter` on lane-key-s1; the fixture case `R4/R12: an EPG input with no active source to land on is not adopted AND NOT STRIPPED` flipped from `writeEntry` true to false). One sentence round 2 wrote under this row's name is WITHDRAWN: "re-setting the SAME URL in one session after removing that source waits for the next shell start". The review's data-loss lens walked the shipping functions in the service's order on both host shapes (the one-write-behind host and the echoing one, omacom/omarchy#15082): the owned write that follows the remove strips the stale echo from the entry and moves the service's snapshot, so the re-set value differs from it and is adopted at once. The "not consumed" rule above stands; the cost attributed to it did not exist. |
| SR38 | nothing | **The migration.** Section 2.2's fourth step. A bar entry with a URL and a state with no `activeKey` is the old shape: derive the key with `Model.sourceKey`, write `activeKey`, rewrite the entry with the key and without the URLs. Idempotent, and it must not lose a source -- it names a record that already exists, creating none and deleting none. The rewrite goes through `updateEntryInline`, so rule 9 governs it: the plugin applies its own write locally in the same turn and never waits for an echo it will not receive, `false` means "already stored" and never surfaces as an error (SR33), and `Model.ownedEntryPatch` must name EVERY key the plugin owns. Adding a key and removing two is a change to exactly the machinery D-LOGO-2 was filed against, which named only some owned keys and wrote stale values back. The migration is silent and needs nothing from the user -- deliberately, and that same invisibility is the whole reason SR39 cost 2 LOOKS like data loss, which is why the two are documented together and not as separate warnings. **Overturned in part 2026-10-11 (R1, R5, R7):** "creating none and deleting none" was false against the code. The migration IS the adopt path (`Model.adoptActiveSource` step 1 -> `Model.reconcileSources`): a URL the history knows makes that record active; one it does not know is ADDED (`migrated` on the very first v2 run, `cli` after), and at the 50 cap the least-recently-used non-active record is evicted with its cache, as any CLI adoption. "Must not lose a source" is therefore graded as "keeps the count it went in with" over a TWO-source state, one active and one not (node: `R7: the migration keeps the source count it went in with`, seen red by mutation; the harness half is lane B's). The two writes are ordered by `Model.pointerWritePlan` (R5): state first, entry waits for a parked state save, so an INTERRUPTED migration leaves the old shape and never a pointer-less record -- R5's claim, about the shell dying between the two writes; see the next amendment for the uninterrupted start. **Amended 2026-10-12 (D-SRC-15, round 3, R9-R11).** R5 ordered the two writes, and the UNinterrupted first start still lost the pointer on the round-2 tree: the helper's start-up `state init` chmodded the existing `state.json`, the service's `stateFile` FileView reloaded on that `IN_ATTRIB` (mode changed or not -- measured on a FileView probe, a chmod 0600 -> 0600 delivers `fileChanged` and a `loaded` with the file's text), `applyUserState` was handed the pre-adoption text while the adoption's save was still parked behind `dirsReady`, `Model.stateOnLoad` kept only the session record, and the parked save then wrote the key-less state while the entry flush stripped the URL with `sourceKey ""`. Found live by the harness lane on 2026-10-11 (key-scenario 32 / 12 on lane-key-r2, sources-scenario 46 / 22; 66 / 0 on dev) and reproduced by two review lenses; the D-SRC-15 row in `STATUS.md` and the section of that name in `QA-RESULTS.md` carry the measurement. So the migration this row describes is what the tree does ONLY with R9-R11 in it, and it is observed rather than argued: on lane-key-s2 (3c5e473, lane-key-s1's code under lane B's harness) `key-scenario.sh live` reads 49 passed / 0 failed, and 36 / 13 over `--baseline lane-key-r2` with D2, D3, M1, M3, M5, C1-C5, E1, O5 and O6 red -- everything that rests on an adoption made at start-up; `sources-scenario.sh` under cage reads 63 / 3, the three pinning the pre-round-2 contract (DQ-A4 / DQ-B7), not this. R9: a reload never replaces in-memory state that is newer than the file -- `Model.reloadDisposition` (lane-key-s1) is asked FIRST in `applyUserState` and answers `ignore` for the service's own write echoed back, a save parked, a save in flight (one `saved` per `setText`, measured, so it is a counter and not a flag) or a failed save, and `apply` for the first load and for a file that is genuinely newer; an ignored reload runs neither the reconcile nor the cache layout, and the count is `stateReloadsIgnored`, which the harness reads (D3: the file seeded 0644 so the chmod fires, `ignored:yes`). R10: the helper stats first and chmods only when the mode differs -- belt, not fix, because a same-mode chmod reloads too, and a 0644 file still gets the chmod and the reload R9 absorbs. R11: the entry mirror that waited for the parked save is written only once that save has LANDED (the FileView's `saved`, not `setText` returning) and the helper's `state init` exited 0; on either failure the entry is left exactly as it is -- the URL on it is the only copy of a source whose state write did not land -- and a line with no URL in it is logged (`Model.entryFlushDisposition`; the order in `stateInitProc`'s exit is pinned by a structural check that reads `Service.qml`). Two bounds on the claim. The created-file shape (no `state.json` at all) was written by one round-2 lens as dropping the same way and is MEASURED not to: a FileView loaded over a missing path never sees the helper's create, N1-N4 are green on the dropping tree and `stateReloadsIgnored` reads 0 across a fresh start, so the fresh install was never exposed and the existing-file shape -- every upgrade -- was. And the sibling the data-loss lens found is covered by the same flag rather than by a second mechanism: `cacheReady` is set before `dirsReady`, so an IPC switch or remove in that window parks a save, and the reload that follows is ignored; a scenario that drives it is nobody's yet. **Amended 2026-10-12 (round 4, R13-R15).** Two corrections to the amendment above and one closure. "One `saved` per `setText`" was measured for two back-to-back writes and does NOT hold for a burst (10 warm switches: 20 `setText`, 14 `saved` on lane-key-t1, 15 on lane-key-s2; a 26-write FileView probe: 25 `saved` + 1 `saveFailed`, `text()` tracking the write that STARTED -- lane A, 2026-10-12, under cage), so "in flight" is decided by content (`Model.stateSaveLanded`) and `stateSavesInFlight` is 0 or 1; the signal-counting version stuck above zero after a burst and, on lane-key-s2, read every later foreign reload as "save in flight" (lane A's DQ-T4: D-SRC-16, P2, a sibling of D-SRC-15 fixed on lane-key-t1 by the content rule and unreleased; cited by id since round 6, once the board row existed). The ignore counter is BY REASON (`stateReloadsByReason`, R15), because the plain total was satisfied by the own-write echo that follows every start and could not go red for the chmod reload D3 names (the round-3 review's P2). And the sibling "nobody's yet" is observed: key-scenario W1-W6 on lane-key-t2 (an IPC switch and then a remove inside the slow start-up window over a 0644 file; W2 and W6 red on `--baseline lane-key-r2`, W3/W6 reading NOFIELD on lane-key-s2 for the counter it lacks). Counts on lane-key-t2 (lane B's transcripts, 2026-10-12): 62 / 0 forward, 54 / 8 on `--baseline lane-key-s2`, 38 / 24 on `--baseline lane-key-r2`. |
| SR39 | nothing | **The three costs, accepted by the owner on 2026-10-09, each of which is documented in the README in plain language.** (1) `omarchy bar set ... playlistUrl` is input only: adopted, then replaced by the key, and the value is gone when the user looks again (SR37). (2) **Downgrading breaks the setup.** An older build looks for the URL on the bar entry, finds none, and reports the plugin as not configured. Nothing is lost -- the sources are still in `state.json`, and the recovery path already exists in the older build: an unconfigured guide opens the first-run form (`Model.openFirstRun`), which carries the `Saved sources (n)` link row into the Sources screen, which is scenario 3.1.6 in `UX-SOURCES.md` and the transition at its line 261. That it is the OLD build's own affordance is what makes the recovery possible at all, and it is read off the shipped code and the UX spec rather than exercised, because this lane holds no display -- but it LOOKS like data loss, and it looks like data loss precisely because the migration was invisible. The release notes and the README say so plainly; softening it is how a user with a working install comes to believe the update ate it. (3) **Losing `state.json` becomes fatal to the source list.** Today the URL in `shell.json` is an accidental backup: wipe the state file and `Model.reconcileSources` re-adopts the URL and rebuilds the record (D3). After this there is nothing to rebuild from and the key is one-way. This is the cost the owner was asked about by name and accepted; it is not softened anywhere, and the README does not tell the user to copy the file around without also saying that the copy carries their provider credentials. **Amended 2026-10-11:** the round trip back up is a MIXED shape (section 2.2 as amended): the older build leaves `sourceKey` on the entry and writes the newly picked `playlistUrl` beside it, and `Model.adoptActiveSource` step 1 resolves that to the URL, so the source picked while downgraded is the one that comes back -- the first build put the stale mirror first and silently reverted the user's choice. Derived from both builds' code; the live round trip is UNVERIFIED. Cost (3) stands exactly as written above: the only change round 2 made to it is tense -- the URL in `shell.json` WAS the accidental backup -- and that is not a second cost (trimmed 2026-10-12 after the round-3 review found it stated twice). |
| SR40 | nothing | **The mode shield stays, and so does the gate in front of a persist.** After this change the plugin's own persists carry a key and no URL, so `Model.persistCarriesSecret` answers "no secret" on every ordinary path and the gate stops firing there. That is the change working, not the gate becoming dead code, and it is not a reason to delete either half. Four reasons, in order of how much they cost if ignored: (i) `omarchy bar set` is still a write of a URL into that file, made by the HOST on the user's instruction, which the plugin cannot gate at all -- the shield is the only thing that tightens the container around a write the plugin does not make; (ii) an install upgrading into this release still has a URL in `shell.json` until the migration's rewrite lands, and the shield runs on the startup path unconditionally, which is D-SINK-18 residual 3 and F-M3-16's lesson that the artifact needs the fix as much as the derivation does; (iii) the key is still a confirmation oracle (SR36), so a private container is still worth having; (iv) a predicate that answers correctly for a write nobody makes today is how the next feature that does write one gets gated by construction instead of by somebody remembering rule 5. The precise post-change behaviour of that predicate and of the deferred-persist slot is the code lane's and is **UNVERIFIED BY ME**: read it off `Model.js` and `Service.qml`. **Settled 2026-10-11:** the gate's question is asked of the ENTRY about to be written -- `Model.entryShieldDecision` over `Model.ownedEntryPatch` -- which answers `persist` for every shipping write (no URL-bearing key is owned) and `refuse` or `defer` the moment a URL-bearing key is written again, whoever writes it; the deferred slot holds `{ sourceKey }`. The guide's `config_unsafe` sentence (`Settings file could not be made private`, with the chmod) is therefore unreachable from any write this version makes, and the README says so rather than documenting a message nobody can see. The shield's re-arm after every owned write and its unconditional startup run are unchanged. |

### D-SINK-19 round 2 rulings (lead, 2026-10-11; numbered R1-R8 in the lane briefs, which is not this file's risk table)

Issued after the adversarial review of the first build; each names where it
landed on this tree. R1: a URL on the entry is adopted before any key is
trusted -- `Model.reconcileAction` (`adopt` / `migrate` / `ignore`) and the
order of `Model.adoptActiveSource`; built on the "not consumed" reading (lane
A's DR-1, recorded in SR37). R2: `Model.reconcileSources` writes the adopted
key into the state it returns. R3: `Model.removeSource` clears the pointer and
`Model.activeKeyOf` validates on every read. R4: a fresh `epgUrl` input is
attached to the active record on any reconcile, an empty one is a no-op, the
CLI clear lever is withdrawn. R5: `Model.pointerWritePlan`, state before
entry, the entry waits for a parked save; `Service.persistActive` executes it
and `stateInitProc`'s exit flushes `pendingEntryKey` after the parked save
(since R11, once that save has LANDED). R6: the harness instrument reads
`sourceKey` first and the URL hash second, named candidates only -- lane B,
landed on lane-key-r2 (a66d760) and carried by lane-key-s2 (3c5e473):
`scripts/dev-harness/harness-lib.js`, driven by `key-scenario.sh check-tree`
in the gate (11 checks) and by `qa-lib-test.sh`. R7: a two-source migration
fixture asserting the count it went in with (node, landed), an
interrupted-order scenario, a CLI-set-while-down scenario and a remove-active
scenario (harness, lane B, landed as the segments of
`scripts/dev-harness/key-scenario.sh live`; rows SRC-MIG-11..17, SRC-CLI-09 and SRC-RM-10
in `QA-SOURCES.md` carry the measured counts). R8: this document round. The
P3 siblings closed with it: `Model.cloneState` reads the key through
`Model.activeKeyText`; `Service.applyOwnWrite` and `ownWriteForKey` (once a `Model.js` export; cited without the prefix because the ledger's symbol scan rightly refuses a bare citation of a symbol that no longer exists) are
deleted with their six assertions; the status-line reset is keyed to `moved`;
the fixture's prose names only sections it has, and a check makes that join a
call.

### D-SINK-19 round 3 rulings (lead, 2026-10-12; R9-R12, on top of R1-R8, which stand)

Issued after the second adversarial review (three lenses over lane-key-r2 and
lane-key-r3, 2026-10-11) found D-SRC-15 live and reproduced it twice. Each
names where it landed on lane-key-s1 (3d2d8e7, lane A) and lane-key-s2
(3c5e473, lane B, the harness).
R9: a file reload NEVER replaces in-memory state that is newer than the file
-- `Model.reloadDisposition` (`apply` | `ignore`, with the reason), fixture section
`reload` (10 cases), asked first in `Service.applyUserState`; while a save is
parked (`stateSavePending`) or in flight (`stateSavesInFlight`, a counter: one
`saved` per `setText`, measured) or the last save failed, the reload is
ignored and runs neither `reconcile(true)` nor `startCacheLayout`; the sibling
(an IPC switch or remove before `dirsReady`, since `cacheReady` comes first)
parks a save and is covered by the same flag. R10: `init_state_file` stats
first and chmods only when the mode is not already 0600 -- belt and braces,
not the fix (a 0644 file still gets the chmod and the service must survive the
reload by R9; measured by `tests/test_state.py` running the verb as a
subprocess over a 0600 file and a 0644 file: `ctime_ns` equal for the first,
greater for the second). R11: `stateInitProc`'s exit gates the entry flush on
the helper's exit code AND on the parked save having landed (`FileView`'s
`saved` / `saveFailed`, read; `Model.entryFlushDisposition`, fixture section `flush`,
8 cases); on failure the entry is NOT rewritten -- the URL stays on it as the
backup it accidentally is -- and a warning with no URL is logged; the ORDER
(save, then entry) has a structural pin in `tests/Model.test.js` that reads
`Service.qml`, so swapping the two lines reddens. R12: an input is never
stripped unadopted -- an `epgUrl` set with no active source stays on the entry
until a source exists and adopts it (`Model.epgSnapshotAfter`, fixture section
`snapshot`, 5 cases; the adopt case `R4/R12` flipped from `writeEntry` true to
false). Also ruled and landed: the two older empty-state strings in
`Guide.qml` (`unconfiguredEpg`, `unconfiguredWhere`) moved to the text in
`UX.md` 6.3 and `UX-SOURCES.md` 3.1.1; the helper's `state source update`
warning rewritten for the overturned D-SRC-11 design (the record is the only
store, the bar-entry setting is an input, `--url` re-keys and moves
`activeKey`, and the one caveat is R9: a shell write parked or in flight at
that moment wins); the dead `first ||` term in `Model.reconcileAction` removed
with a comment and a check; and lane A's round-2 cost sentence (re-setting the
same URL after a remove waits for the next shell start) withdrawn from every
document that carried it (SR37 as amended; `ARCHITECTURE.md` section 6;
`QA-SOURCES.md` SRC-CLI-02; the README). Counts, from lane B's transcripts
on lane-key-s2: `key-scenario.sh live` 49 passed / 0 failed; `--baseline
lane-key-r2` 36 / 13; `check-tree` 11 / 0; `sources-scenario.sh` under cage
63 / 3 (46 / 22 on lane-key-r2, 66 / 0 on dev); node 2125 checks, python 1056
tests, qml 78. What this round leaves open is listed with its owner in the
lane reports, not here: the dirsReady-path entry write (`Model.pointerWritePlan`'s
`save-state`, `write-entry`) is NOT gated on the save landing (DQ-A2); the
three sources-scenario reds pin the pre-round-2 SR25 contract (DQ-A4 /
DQ-B7); a CLI `state ...` write landing inside a parked or in-flight shell
save is lost to the shell's save, by R9 as ruled (the helper's warning says
so; not measured live); and `stateSaveFailed` is sticky until a later save
lands, so after a failed write every reload is ignored for the session.
**[Round 4 closed the first two of these: R13 gates the dirsReady route, and
SR25 is amended above with the three checks moved. The last two stand as
ruled.]**

### D-SINK-19 round 4 rulings (lead, 2026-10-12; R13-R15, on top of R1-R12, which stand)

Issued after the third adversarial review (three lenses over lane-key-s2 and
lane-key-s3, 2026-10-12) graded lane A's own open question DQ-A2 as a P1 and
measured it live: with the directories READY, `persistActive` wrote the entry
straight after `setText` and before the FileView reported, so a state write
that failed then (an unwritable `~/.local/state`, a full disk) had already
stripped the URL from the host's file -- the record existed in memory only
and the input had no copy anywhere. R11 had gated the parked route only.
Each ruling names where it landed on lane-key-t1 (bb06540, lane A) and
lane-key-t2 (712329c and f54f408, lane B, the harness).
R13: the entry mirror is written only after the state write it depends on
has LANDED, on EVERY route -- `Model.pointerWritePlan` grows the
`write-entry-after-saved` step and takes `savesInFlight` and `saveFailed`
(fixture section `order`, 13 cases); `Model.entryFlushDisposition` is the one
decision, a save parked or in flight outranking a stale failure (fixture
section `flush`, 11 cases); `switchSource` and `removeSource` keep reporting
SYNCHRONOUSLY on the state write being ISSUED (the state write IS the
switch); a later `saveFailed` logs with no URL and emits
`sourcesPersistFailed("state_write_failed")`, once per failure episode; a
REFUSED mirror is logged, never reported as the switch failing; on any
failure the URL stays on the entry as the backup it accidentally is, and
the next start re-adopts it (R1). "Landed" is by content (`Model.stateSaveLanded`),
because a burst coalesces `saved` (SR38 as amended). R14: the two service
decisions get structural pins in `tests/Model.test.js` (the D-SINK-18
shape): the ignore branch of `applyUserState` RETURNS before `Model.stateOnLoad`,
and `saveState` parks (sets the flag) before `dirsReady`; each seen red by
deleting the line. R15: the reload counter counts BY REASON --
`stateReloadsByReason`, one number per `Model.reloadDisposition` reason through
`Model.countReload`, exposed on the harness's `pointerState` -- and key-scenario
D3 asserts the `save-parked` reason; a shell exiting with `pendingEntryKey`
still held logs one warning with no URL (DQ-B9). Also ruled: SR25 is
AMENDED (dated, overturned-not-rewritten, above); D16-as-narrowed is the
ruling -- an invalid CLI value keeps the active source and synthesizes the
error only when nothing else is showable -- and `sources-scenario.sh`'s
three checks moved to that contract, with the `already stored` weak check
fixed while there (it seeds `sourceKey` on the stored side and asserts the
host's `nothing changed (already stored)` line counted from a mark); the
README's "before release" sentence states the fact alone since round 5 --
run under a headless compositor on 2026-10-12, the check count, the command
-- and promises no release step, because the round-4 wording ("run again
before each cut") named a step no script runs; the pre-cut live run is a
step of the release recipe in `CLAUDE.md`, the lead's, and each run is
recorded in `QA-RESULTS.md`. Counts, each with where it was measured: node 2146 checks /
0 on lane-key-t1 (+21 over lane-key-s2's 2125; the same test files over an
export of lane-key-s2 read 21 failures, the P1 driver's `urlStillStored:
false ... fileSources:2` among them -- lane A); python 1056, qml 78
(unchanged); `key-scenario.sh live` on lane-key-t2 62 / 0, `--baseline
lane-key-s2` 54 / 8 (D3, W3, W6 for the counter s2 lacks; F3-F7 the loss at
the sink), `--baseline lane-key-r2` 38 / 24, `--baseline f275bde` 39 / 23,
and two throwaway mutations of this code through the same harness
(`Model.reloadDisposition`'s save-parked clause deleted 56 / 6; the R14 `return`
deleted 57 / 5 with D3 GREEN beside D2/W2 red -- the counter observes the
decision, the sink is D2, the `return` is the structural pin); `check-tree`
11 / 0; `sources-scenario.sh` 66 / 0 under cage, 62 / 4 for this harness
over an export of dev 93bbd5d (lane B's transcripts, 2026-10-12). What this
round leaves open, with its owner in the lane reports: the Guide's copy for
`state_write_failed` (DQ-T1, the Guide owner); the counter-leak sibling's
D-id and the `one saved per setText` sentence in the lead's files (DQ-T4);
the state directory unwritable at START (R11's `drop`), a remove on a failed
disk, a `saved` for an EARLIER write arriving while a later one is pending
and then fails, and a CLI `state ...` write inside a parked or in-flight
shell save -- none observed live, said so in `QA-SOURCES.md`; R11 keeps
init-failed outranking a landed save, deliberately (DQ-T5); a start over a
matching key still parks a save every time (a round-3 remark, not
investigated); the two mutation branches are deleted at integration
(DQ-B10); and `key-scenario.sh`'s SRC-MIG-11/12 citations carry an "on
lane-key-s3" note until this document's branch lands (DQ-B11).
**[Round 5 closed three of these: the Guide renders the reason (DQ-T1, R16's
second half); the mutations are patch files under
`scripts/dev-harness/spikes/key-mutations/` run through `--tree`, and the
branches are the lead's to delete (DQ-B10); the "on lane-key-s3" notes are
gone on lane-key-u2 (DQ-B11). The counter-leak sibling is D-SRC-16 on the
board, cited by id since round 6 (DQ-T4). The rest stand.]**

### D-SINK-19 round 5 rulings (lead, 2026-10-12; R16, on top of R1-R15, which stand)

Issued after the fourth adversarial review (two lenses over lane-key-t2
f54f408 and lane-key-t3 734b06b, 2026-10-12) found one P1 by the data-loss
lens, and it is rule 15 again, this time inside the fix: `writeOwnedEntry`
has two callers, R13 gated `writeActive`, and the other --
`Service.setShowLogos`, the logo toggle -- wrote `{ sourceKey:
root.activeSourceKey, showLogos }` from MEMORY with no plan and no
disposition while `Model.entryWith` stripped `playlistUrl` and `epgUrl` on every
owned write by design. So after a failed state write -- the exact state R13
now leaves correctly, the URL kept on the entry as the only copy, the
failure signalled -- one logo toggle rewrote the entry to the in-memory key
and stripped the URL; the record existed nowhere durable and the next start
lost it. Measured live on the committed lane-key-t2 (the stored entry after
the toggle naming B with `playlistUrl` gone, `state.json` still A, the
restart finding no B anywhere) and at the Model layer (4 of 4 routes under
both host shapes; 308 of 4,392 driven sequences, every one of them a
sequence ending in a logo toggle); pre-existing on every D-SINK-19 tree; and
invisible to 2,146 node checks, 11 check-tree, 62 / 0 live and 66 / 0
sources, because nothing drove a toggle after a failed write (the review's
P2). Each ruling names where it landed on lane-key-u1 (b42b5ab, lane A, the
code) and lane-key-u2 (04c82dc, lane B, the harness).

R16. An owned-entry write that is NOT the key mirror writes only the fields
it owns. While a state write is parked, in flight or failed, the logo toggle
patches `showLogos` alone and leaves `sourceKey`, `playlistUrl` and `epgUrl`
exactly as the host publishes them [round 6: the ruling as issued said
"holds"; on the host that publishes one write behind the two differ by one
write, and that difference is D-SINK-20]; healing the entry (the key from memory, the
retired fields stripped) is the key mirror's job and happens only once the
file agrees with memory, through `writeActive` under R13. When nothing is
outstanding the toggle heals as before. ONE Model decision says which --
`Model.ownedWriteMode`, which takes the three flags and nothing else and names its
reason [amended 2026-10-12, round 6: four inputs, `stateLoaded` first, and
`patch` before the first state load; see the round-6 rulings] -- and the entry builder has a mode that preserves the retired fields
(`Model.entryWith` with `keepRetired`); the own-write override (rule 9,
`Model.ownWriteOf` / `Model.ownWriteInForce`) recognises the patch-only
write as ours. Pins that CALL the writer: the node driver's "failed save,
then setShowLogos" under both host shapes, asserting the stored entry keeps
`playlistUrl` and that at every `updateEntryInline` the entry's key equals
the file's own pointer (the lens's L12 audit), red on lane-key-t2; and a
live segment after F5 (`ipc open`; `ipc sourcesKey enter`; `ipc sourcesKey
g`; `ipc sourcesKey confirm`; `hostEntry`), red on lane-key-t2. Where it
landed: `Model.js` (`Model.ownedWriteMode`; `entryWith(entry, patch, opts)`;
`Model.RETIRED_SETTINGS`'s comment re-stated under R16), `Service.qml`
(`setShowLogos` asks the decision with the three flags -- four since round 6 -- logs `logo setting
written alone; the bar entry's source keys are left as they are (<reason>)`
on `patch` and writes `{ showLogos }` with `keepRetired`; `writeOwnedEntry`
takes `keepRetired` as its fourth parameter and hands it to `Model.entryWith`, the
override record unchanged and unconditional), `tests/Model.test.js` (sixteen
checks, 4.3 above) and `tests/fixtures/active-key.json` (section
`ownedWrite`, the 8-case cube, 16 cases since round 6; run by node only -- no Python mirror of the
decision exists, so the fixture has one consumer).

The sibling search, lane A's, over SHAPE and across every `.qml` file (rule
15), each place named as gated or cleared: `grep -rn 'updateEntryInline(\|
writeOwnedEntry(\|pendingPersist\|activeSourceKey, showLogos\|sourceKey: '
--include=*.qml .` -> `Service.qml` holds the ONLY `.updateEntryInline(`
call, inside `writeOwnedEntry` (the funnel; the D-SINK-19 structural pin
holds it at one). Its callers: `writeActive` -- GATED, reached only through
`persistEntryKey`, which `persistActive` reaches only on the plan's
`write-entry` step under R13 (nothing parked, in flight or failed) or on
`settleEntryFlush`'s `flush` after `saved`; `setShowLogos`'s two branches --
NOW GATED by `Model.ownedWriteMode`, the writer this round is about. The deferred
shield flush (`pendingPersist`, set under `CONFIG_DEFER` and flushed by
`onConfigShieldExit` into `writeActive(pending.sourceKey)`) -- CLEARED by
calling `Model.entryShieldDecision`: a key-only or `showLogos`-only patch
answers `persist` against `UNKNOWN`, `PRIVATE` and `EXPOSED` alike, so
`CONFIG_DEFER` never sets `pendingPersist` for a shipping write (it is
reachable only for a patch carrying `playlistUrl` or `epgUrl`, which no
shipping write composes), and the key it would carry was gated at the
write-entry step. `persistEntryKey`'s patch -- the input to the shield
decision, not a write, on the same gated path. `adoptActive`'s `entry` --
READS the host's settings as input, writes nothing. `Guide.qml` -- no entry
write at all (`toggleLogos` / `confirmLogos` call `service.setShowLogos`;
nothing else names either function). `Bar.qml`, the player and every other
`.qml` -- none. `scripts/dev-harness/shell.qml`'s `updateEntryInline` is the
fake HOST's receiving side, not a writer; `tests/Model.spec.qml`'s hits are
test literals. The helper never writes `shell.json` (the config shield
chmods it). The user's own `omarchy bar set` is the one remaining writer
and is their hand (SR8). A second search for the copy: `grep -n
'sourcesPersistFailed(' Service.qml` -> three emitters (`config_unsafe`,
`persist_failed` only when `announce !== false`, `state_write_failed`), all
in `Model.PERSIST_FAILURE_REASONS`, which the new node check derives from the
service source and asserts; `sourceErrorMessage("persist_failed")` in
`Guide.qml` -> `toggleLogos` / `confirmLogos` rendering it for a `false`
return of `setShowLogos`, a host entry that cannot be rewritten for a LOGO
write, which carries no credential, so `try omarchy bar set` is honest
there -- CLEARED, left as is (DQ-U5). A third, for the fourth parameter:
`grep -rn 'writeOwnedEntry' scripts/ tests/*.py` -> nothing pins the
signature outside `tests/Model.test.js`, which was re-levelled.

Also ruled, with where each landed: the Guide routes the REASON --
`onSourcesPersistFailed(reason)` renders the copy for THAT reason through
`Model.persistFailureMessage`, in `Model.js` under rule 12 with `persist_failed`
as the fallback for an unknown reason, and a node test over every reason the
service can emit asserts that no copy carries a URL or `omarchy bar set`
except `persist_failed`'s own (lane-key-u1; 4.3 above, `UX-SOURCES.md`
5.5). Once-per-episode signalling STANDS, recorded in `UX-SOURCES.md` 5.5
as a decision with its consequence (a second switch on the failed disk
reports `ok` and shows nothing; the journal line is per failure). The
init-failed drop stands as recorded (DQ-T5). The harness, on lane-key-u2:
`cleanup()` restores the state directory's mode on every exit and `run.sh
clean` tolerates a read-only directory (a TERM inside F used to leave it
0500 with `rm -rf` failing; measured both ways); F gets its own `log_mark`
before the switch, so F5's halves are the switch's own (`signalled` wants 0
since that mark); `qa_json_field` prints `NULL` for a present null and
`NOFIELD` only for an absent key, every want that meant null in
`scripts/dev-harness` and `qa-lib-test` reading `NULL` after a rule-15
sweep of the `NOFIELD` wants (the W3/F2/F5 `held` wants among them;
`qa_field` / `qa_guide_field` keep the one-sentinel fold, DQ-B15); the two
mutation branches are replaced by patch files under
`scripts/dev-harness/spikes/key-mutations/`, applied to an EXPORT and run
through the new `--tree DIR` lever, with `qa-lib-test.sh` proving each still
applies (the lead deletes the branches); the README states the fact alone
and promises no release step, the lead adding the pre-cut live run to the
release recipe in `CLAUDE.md` and recording each run in `QA-RESULTS.md`; the
stale `Service.qml` comment beside the signal moved to the truth (DQ-C7);
the "on lane-key-s3" notes beside the SRC-MIG-11/12 citations are gone,
because this chain carries the renumbered rows; and the counter-leak
sibling on lane-key-s2 (after a switch burst every foreign reload was
ignored for the session, fixed on lane-key-t1 by the content rule,
unreleased) is D-SRC-16 (P2), boarded at integration; SRC-MIG-19 and SR38
cite it by id since round 6, and round 5 described it rather than cite it
because the ledger refuses an id with no row (measured on lane-key-u3, rc
1), which a documents lane does not route around.

Counts, each with where it was measured. Node 2,162 checks / 0 on
lane-key-u1 (+16 over lane-key-t2's 2,146; the same test files over an
export of lane-key-t2 read 17 failures, the sixteen R16 titles and the
funnel pin re-levelled to the fourth parameter; lane A); python 1,056, qml
78 (neither extended); harness predicates 435 / 0 on lane-key-u2 (+15; lane
B). Live, from the transcripts (lane B, lane-key-u2, 2026-10-12, 63 lettered
checks): `key-scenario.sh live` 64 / 0; `--baseline lane-key-t2` 60 / 4 (L1
`stored:<C> file:<A> memory:<C> playlistUrl:no`, L2 `keys:0 alone:0`, F6
`record:0`, F7 `records:2`); `--baseline lane-key-s2` 54 / 10 (round 4's
eight plus L1, L2); `--baseline lane-key-r2` 38 / 26; `--baseline f275bde`
39 / 25; the two mutations as patch files through `--tree` 58 / 6 and 59 /
5 (the same letters as the round-4 branches, D3 green beside D2 red on the
second); `check-tree` 11 / 0; `sources-scenario.sh` 66 / 0 under cage;
`logo-scenario.sh live` 33 / 0; a TERM inside F leaving the state directory
0700 and the harness directory removable (rc 0). Lane A's own live runs on
lane-key-u1 under cage: key 62 / 0 on the round-4 harness, the lens's driver
storing A with `playlistUrl` KEPT and the restart adopting B, sources 66 /
0, logo 33 / 0. What this round leaves open, with its owner: the lag
residual of the patch-only write, measured in the driver and the simulator
only (DQ-U1, stated in 4.3); the re-prefixing of the round-3/4/5 symbols
after the merge (DQ-U3, DQ-C10); the echo-host override being inert rather
than lapsed (DQ-U4, a remark); the `persist_failed` copy for a refused logo
write (DQ-U5, honest, left); `qa_field` / `qa_guide_field`'s one-sentinel
fold and chno-entry's N8 (DQ-B15); `run.sh clean` not reporting an `rm` that
fails for another reason (DQ-B17); the SRC-MIG citations in `key-scenario.sh`
able to point at L once SRC-MIG-22 exists (DQ-B18, done in that row's
direction here); the two long baseline runs exceeding a 600 s foreground
call together (DQ-B19); and, unchanged from round 4, the state directory
unwritable at START, a remove on a failed disk, a `saved` for an EARLIER
write arriving while a later one is pending and then fails, and a CLI
`state ...` write inside a parked or in-flight shell save -- none observed
live, said so in `QA-SOURCES.md`.
**[Round 6 closed or moved four of these: the lag residual is D-SINK-20 on
the board and observed live (DQ-U1); the round-3/4/5 symbols are cited with
the `Model.` prefix and the "cited bare until the merge" notes are gone
(DQ-U3, DQ-C10, DQ-C14); `run.sh clean` reports a failed `rm` and exits 1
(DQ-B17); `qa_field` / `qa_guide_field` stay unsplit, each recorded BY NAME
in `scripts/qa-lib.sh` with the want that blocks it (DQ-B15: player-scenario
P14's `.get(...)` want for `qa_field`, and for `qa_guide_field` an instrument
that folds too, so a split could not go red). The rest stand. Not on this
list but closed the same day: the pre-cut live run is in `CLAUDE.md`'s
release recipe on `dev`, the lead recording each run in `QA-RESULTS.md`
(DQ-C15).]**

### D-SINK-19 round 6 rulings (lead, 2026-10-12; R16 amended, on top of R1-R16, which stand)

Issued after the fifth adversarial review (two lenses over lane-key-u3
04cbceb, 2026-10-12), both of which read the chain as mergeable with no P1.
This round closes their P2s and the cheap P3s and nothing else. The items
are lettered C1-C4 (code), H1-H3 (harness) and D1 (documents) in the lane
briefs, which is not key-scenario's C1-C5. Code and harness landed together
on lane-key-v1 (78ff442, lane A, on top of 268a881, a conflict-free merge
of `dev` at a576e01; d592ee6 is the harness README's counts); the documents
on lane-key-v2 (lane C).

C1 (the data-loss lens's P2). R16 is amended: `Model.ownedWriteMode` takes a
FOURTH input, `stateLoaded`, and answers `patch` with reason
`state-not-loaded` before the first state load; the service passes it; the
`ownedWrite` fixture section is the 16-case four-input cube; the structural
pin that read "the three flags and nothing else" is re-levelled to the four
inputs; and a service-order driver case fires `setShowLogos` before the
first `applyUserState` under both host shapes, red on lane-key-u3 (4.3's
round-6 amendment carries the mechanism and every count). Lane A made the
absent input fail safe: anything but `true` is "not loaded". What an ABSENT
input should answer is the lead's (lane A's OQ-V1): over this tree the
lens's unadapted three-flag simulator reads 1,029 problems in 48,312 runs,
none of them a loss and all of them a heal that never comes, so a caller
that forgets the input leaves a URL on `shell.json` longer rather than lose
a record.

C2 (the data-loss lens's second P2, a weak check). Nothing pinned that
`writeOwnedEntry` composes the owned patch from `root.settings`, the
own-write overlay, rather than `root.hostSettings`; the one-token mutation
reverted a toggle at the next owned write under the lagging host (D-LOGO-2's
shape) with node 2,162 / 0 and live 64 / 0. Now a structural pin
(`settings` appears in that call and `hostSettings` does not) and a driver
case (a patch-only toggle on a failed disk, then the key mirror's heal
write once the disk recovers: `showLogos` stays as toggled on the stored
entry, in `settings` and after a restart), the driver composing from
whichever token `Service.qml` names in that line. Under the mutation, 7 red:
the pin; the named case under lag; the pre-load, parked and in-flight cases
under lag; and two earlier R16 lag cases, which now compose from the
shipping token.

C3 (P3). The parked-only and in-flight-only toggle routes were pinned by the
fixture cube alone. One driver case each, under both host shapes ("switch
while the dirs are not ready, then toggle"; "switch, then toggle before the
FileView's `saved`"), each pair red when `Model.ownedWriteMode` ignores
`savePending` or `savesInFlight` respectively (4 red each, with the
fixture and the cube); the got shows the mirror moving ahead of the file.

C4 (P3). The `Service.qml` comment beside the toggle said the patch-only
write "puts into the file nothing the file does not already hold"; on the
lagging host it can re-carry a stripped URL for one write. It now says what
is true, cites D-SINK-20, and warns against the narrowing that would reopen
the round-4 P1 (4.3, the round-6 amendment, item 2).

H1 (the live lens's P2). The round-5 `NULL` / `NOFIELD` split never saw an
absent field, because `ipc pointerState` folded `undefined` to null before
the reader ran, so `held:NULL` was green on f275bde, a tree with no
`pendingEntryKey` at all. `pointerState` is now `HarnessLib.pointerStateOf`,
which OMITS a property the service does not have; `qa-lib-test.sh` drives it
through `qa_json_field` (+6 pins, 435 -> 441; with the fold put back into
`pointerStateOf`, 439 / 2); the `qa-lib.sh` comment is true; and live on
`--baseline f275bde` the held half of W1, W3, W5, F2 and F5 reads `NOFIELD`
where round 5 read `NULL` (39 / 25 in both rounds -- the same letters,
because each of those checks was already red there for its other halves).
Rule 15 over `qa_field` and `qa_guide_field` (DQ-B15): neither is split, and
why is written into `scripts/qa-lib.sh` by name. `qa_field`'s split would
move player-scenario P14's want (`d['failedAt'].get('t:live1') == NOFIELD`,
where `.get` turns an absence into None, so the split would invert it), and
P14 needs the player arm; `qa_guide_field` reads `state()`'s guide half,
which folds too, so a split there could not go red for the absence it would
be named for. About fifty other `=== undefined ? null` folds in
`scripts/dev-harness/shell.qml` (`state()`, the snapshot helpers,
`chnoIndex`) are unchanged for the same reason. A correction to round 5's
record: chno-entry's live half is IPC-only and runs headless, so a keyboard
was not what blocked N8 (lane A's OQ-V3).

H2 (the live lens's P3). The gate runs `qa-lib-test.sh` under
`env -u OMARCHY_IPTV_HARNESS_DIR`, because one pin asserts the DEFAULT
transcript directory and went red over a green tree when the variable was
exported (with it exported, the old invocation 440 / 1 and the new 441 / 0;
lane A). The two load-sensitive timing tests -- the 10,000-entry parse
budget in `tests/test_playlist.py` and the player stub's real-socket seek
in `scripts/qa-stub-mpv.py --self-test` -- print one line on failure saying
the number is load-dependent and how to re-run that test alone before
reading it as a tree defect; the assertions and the budget do not move.

H3 (P3, DQ-B17). `run.sh clean` checks `rm`'s status: it prints `clean
FAILED` and exits 1 instead of `cleaned` with 0 (lane-key-u3's `run.sh`
under the new pin: 440 / 1).

D1. This document round, on lane-key-v2: R16's amendment, dated (4.3, the
3.5 table, the round-5 ruling); "as the host holds them" corrected to "as
the host publishes them" with D-SINK-20 cited wherever it stood; D-SRC-16
cited by id (SR38, `QA-SOURCES.md` SRC-MIG-19, the round-4 and round-5
subsections, `ARCHITECTURE.md` section 6), now that the board row exists on
this tree; the mutations described as patch files through `--tree`
wherever a document still described branches (DQ-B16); and every round-2
to round-5 `Model.js` symbol these documents cite re-prefixed, the "cited
bare until the merge" notes dropped (DQ-C14), the ledger resolving every
one. DQ-C15 is closed on `dev`: `CLAUDE.md`'s release recipe carries the
pre-cut live run, and the lead records each run in `QA-RESULTS.md`.

Counts, each with where it was measured. Lane A on lane-key-v1, 2026-10-12:
node 2,171 / 0 (`grep -c '^ok   R16'` 25, was 16); python 1,057; qml 78;
harness predicates 441 / 0; the gate 0 on 78ff442 and on d592ee6. Live,
from lane A's transcripts under a nested headless cage on lane-key-v1:
`key-scenario.sh live` 64 / 0; `--baseline f275bde` 39 / 25 with the held
half `NOFIELD`; `sources-scenario.sh` 66 / 0; `logo-scenario.sh live` 33 /
0. The fifth review's own instruments over lane-key-v1 (lane A, the lens's
drivers with one token added to hand the new input): the pre-load proof 3
-> 0 losses; the matrix 48,312 runs, 3,939 -> 21 problems, all 21 of them
D-SINK-20's.

What this round leaves open, with its owner: D-SINK-20 (P3, a recorded
residual; the correct narrowing needs to know whether the last LANDED state
text holds a record for the published URL, a round of its own); the
absent-input answer (OQ-V1, the lead); `qa_field`, `qa_guide_field` and the
other folds in `shell.qml` (recorded by name, above); `Model.js` over the
marketplace scanner's 512 KiB per-file limit (D-REL-5; 572,623 bytes on
lane-key-v1, the split script re-run over this file at integration); the
pre-load, parked and in-flight toggles observed in node and not live; and,
unchanged, the state directory unwritable at START, a remove on a failed
disk, a `saved` for an EARLIER write arriving while a later one is pending
and then fails, a CLI `state ...` write inside a parked or in-flight shell
save, and the echoing host (modelled, D-HOST-4).
