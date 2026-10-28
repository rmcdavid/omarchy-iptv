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
| D1 | Where the active source lives | (a) shell.json entry (today); (b) state.json `activeKey`; (c) both | **(a) unchanged: `playlistUrl` / `epgUrl` on the bar entry** (M2-SOURCES decision 1) | `updateEntryInline` replaces the entry with `{id} + settings` in a clone of `shellConfig`, then `persistShellConfig` sets `shellConfig = payload` synchronously and writes the file with an atomic `FileView` (lines 1078-1112, 109-114, `userConfigFile` 134-141). `onShellConfigChanged` (67-71) fires `pluginsChanged()`, whose `Connections` handler calls `syncPluginApis()` (1053-1058), which reassigns `shellApi.barConfig` (879) -- the same object our `settings` binding already reads (`Service.qml:56`). So a write from QML propagates to the service in the same event loop turn, with no file watcher in the path, and `omarchy bar set` arrives through the identical chain (`omarchy-bar:361` -> IPC `setBarWidget` 1654-1663 -> `PluginRegistry.setBarWidget` -> `shellConfigMutator` -> `mutateShellConfig` 162-166 -> `persistShellConfig`). Storing an `activeKey` in state would create a second writer for one fact. **Amended 2026-10-09 (D-SINK-18): this row is now understood to be the ROOT of that defect, and the choice it records is no longer the one that would be made today.** Identifying the active source by its URL means a provider credential MUST live in the host's `shell.json` for the plugin to know which source is active -- a file this plugin does not own, whose packaged default is 0644, and whose FileView writer (the shell's own, the one behind plugin settings and `omarchy bar set`; the host's CLI writer `omarchy-shell-config commit()` rewrites it 0600, D-DOC-23) the lead measured on 2026-10-09 to preserve whatever mode it finds (0644 in, 0644 out, content changed), so the plugin cannot assume the container is private. The reasoning above is not wrong about its own question: a second writer for one fact is a real cost, and the shell.json entry really is the one place the host and `omarchy bar set` already agree on. What it never weighed is that this particular fact IS the credential, so the cheapest identifier available was also the one that forced the secret into the borrowed container. **The containment that ships now is the mode shield** (`ARCHITECTURE.md` section 6, D-SINK-18; standard 11): the helper's `config shield` makes that one file deny group and other BEFORE a URL is persisted into it, and a persist that carries a URL is refused when it cannot. That narrows who can read the file; it does not stop the credential being there, and it is not presented as the answer. **The answer is to name the active source by its KEY and keep the URL only in the plugin's own 0600 state, and that is FILED SEPARATELY by the lead with its own id and its own round -- do not start it from a D-SINK-18 lane.** It is a migration rather than a patch: `Service.qml:199-201` still says the active source is `playlistUrl` / `epgUrl` on the bar entry, `activeSourceKey` (`Service.qml:247`) IDENTIFIES the active source by matching that URL against `state.json`, `state.json` has no `activeKey` at all (section 2.1), and the change touches a documented configuration surface that `omarchy bar set` and D16 both write through. The id of that filing is not assigned in this round and is UNVERIFIED from this document: read it off the board in `docs/STATUS.md`. **Continued 2026-10-09 (D-SINK-19): the filing is D-SINK-19, and the product owner approved it the same day as a release of its own; built 2026-10-11 in two rounds, the second after an adversarial review of the first.** This row's choice becomes **(b)**: the active source is named by `activeKey` in `state.json` (section 2.1), read through `Model.activeKeyOf`, and the bar entry carries the source's key (`sourceKey`) in place of its URLs. The cost this row weighed and chose against -- a second writer for one fact -- is REAL and is now accepted rather than argued away, because the fact being written is a credential and the borrowed container is the wrong place to keep one; `Model.pointerWritePlan` orders the two writers (state first, entry waits for a parked state save). The rulings that carry it are SR35-SR40 at the end of this document, each with its 2026-10-11 amendment where the review overturned part of it; the original text above stands as written, because a decision edited to read as though it always said this teaches nobody anything. |
| D2 | Where the history lives | (a) state.json v2; (b) extra keys on the shell.json entry; (c) a file in the plugin dir | **(a) `state.json` version 2, key `sources`** (M2-SOURCES decision 2) | Already 0600 in a 0700 dir (S-02 fixed: `state init`, `Service.qml:933-953`), already read and written by both QML (`Model.parseState`) and the helper (`normalize_state`, `bin/omarchy-iptv:1557-1576`). shell.json is host-owned and schema-declared (manifest `barWidget.schema`); the plugin dir is never written at runtime (PRODUCT.md decision 6). |
| D3 | Reconciling settings with history | (a) service observes settings; (b) helper scans shell.json; (c) guide-only | **(a) `Model.reconcileSources` runs in the service on state load and on every `playlistUrl` / `epgUrl` change** | The service already re-evaluates `settings` on every shell.json change (decision 7, `Service.qml:53-68`, `onPlaylistUrlChanged` 671-678). Reconcile is pure and idempotent: a URL already in history bumps `lastUsed` (only when the active key actually changed) and adopts a changed `epgUrl`; an unknown URL is added with a host-derived label and `origin: "cli"` (S5). No helper run, no extra IPC. **Amended 2026-10-11 (D-SINK-19, round 2).** `Model.reconcileSources` is still the function that adopts a URL, and SR8 still holds for a URL the service has not consumed; what sits in front of it now is `Model.reconcileAction` (what a settings change MEANS: `adopt`, `migrate`, `ignore`, with `adoptEpg` decided independently) and `Model.adoptActiveSource` (what the active source IS: a fresh entry URL first, then the state's key, then the entry's mirror, then nothing), both pure and node-tested; `Service.reconcile` only moves the snapshot and hands the plan on. Two things this row said are no longer true: "on every `playlistUrl` / `epgUrl` change" -- an EMPTY value is a no-op now, not a change the plugin acts on, since the plugin itself empties those keys on every write; and the adopted key is now written INTO the returned state (R2), where this row's first version returned it as an out-param only and the service never wrote it. What this row never claimed and the project had quietly come to rely on is also gone: the URL in `shell.json` was an accidental SECOND COPY of the active source, so a lost `state.json` was rebuilt from it on the next start. It is not any more, `Model.sourceKey` is one-way, and the README says so (SR39 cost 3). **Amended 2026-10-13 (round 11, R21; the owner withdrew the `omarchy bar set` URL route).** The service reconciles the bar entry's URLs into the history only during the one migration of a 0.13.x install (R21a); once the migration marker has landed a `playlistUrl` or `epgUrl` change on the entry adopts nothing and is refused (R21b). `Model.reconcileSources` is unchanged and is still the migration's adoption. |
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
| D14 | Favorites / recents across sources | per source / global | **Global, keyed by channel id (PRODUCT.md M1, ARCHITECTURE decision 6), unchanged** | `t:<tvg-id>` ids are shared by design (a favorite survives a provider switch when the tvg-id matches); `u:<hash>` ids are source-specific by nature. The guide already filters both lists against the loaded index (countFavorites, internal to `model/browse.mjs`, and `channelsForScope`) [cited bare since 2026-10-12, D-SINK-19 round 10 R20e: `Model.mjs` does not export it, so the prefixed name would be undefined from QML], so entries of another source are invisible, not broken. Recents stay bounded by `maxRecents`; favorites are user-driven. Documented in the README; no per-source scoping in v0.2. |
| D15 | Helper surface | new `source` subcommand / extend `state` / new `cache` | **Extend `state` (v2 aware, URL-redacted output) and add one `cache` subcommand with `migrate`, `remove`, `prune` actions. No `state source ...` verbs** | Section 5 contracts untouched. The service does every history mutation in QML; the helper only touches the filesystem where QML must not (`rm`, `rename`, mode bits). `state show` must stop printing URLs once records carry them (section 2.4). |
| D16 | Invalid values set by CLI | run the helper anyway / synthesize | **The service never runs the helper for a `playlistUrl` that fails `validateSourceUrl`; it synthesizes `playlistStatus` from the validation result (like `helperTimeoutStatus`, `Service.qml:422-430`) and leaves `activeCacheDir` empty** | The helper would refuse with the same code; skipping it avoids creating a directory for garbage and keeps the guide's existing error empty state with a reason and no host. Same for `epgUrl` -> `epgStatus`. **Amended 2026-10-13 (round 11):** reachable only by a migration value; it is also reported once (`Model.entryInputNotice`, reason `invalid`) and stripped. After the migration an invalid value is refused like any other, reported as `retired`, and never reaches the status at all. |

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
| `entryMigrated` | `true`, optional | D-SINK-19 round 11 (R21a, 2026-10-13; lane-key-m1 15896f1). THE MIGRATION MARKER: present, and exactly the JSON boolean `true`, once the one migration of a 0.13.x install has adopted what its bar entry carried; absent otherwise -- never `false`, so a state that has not migrated serializes as it did before. Read through `Model.entryMigratedOf` (`=== true`: the string `"true"`, `1`, a list holding `true` are no marker, the `activeKey` coercion lesson) and set through `Model.withEntryMigrated` in the SAME state write as the adoption (`Model.adoptActiveSource` with `migrating`). The service asks it of the LANDED state (`Service.landedState`), never memory: until a write carrying it has landed the bar entry's `playlistUrl` and `epgUrl` are migration inputs and every owned write keeps them on the entry (R21a); once it has, they are refused, reported once and stripped (R21b). Additive at version 2 on the `activeKey` precedent, no version bump; taught to `Model.parseState`, `Model.cloneState` and the helper's `normalize_state` (`normalize_entry_migrated`, `raw is True`) on the same day over the shared fixture `tests/fixtures/state-keys.json` (eight `entryMigrated` cases, both suites), and covered by R20a's check that the helper preserves every key the service writes. An OLDER build drops it with every key it does not know: 0.13.6 then writes its active URL back onto the entry, and the re-upgrade migrates again over it (key-scenario G4, with the REAL helper of the v0.13.6 tag: `rc:0 marker:absent activeKey:absent records:2`; G5). |
| `pendingEpg` | object `{ url, seenAt }`, optional | **WITHDRAWN 2026-10-13 (round 11, R21d; the round-11 rulings at the end of this file).** The key, its readers and writers and the helper's preservation of it are deleted, and both readers drop it from a file an earlier build of this chain wrote (shared fixture `tests/fixtures/state-keys.json`, `round 9 and 10 keys are dropped by both readers ...`). The text below is the round-9 and round-10 description, kept as written; the names in it are cited without the `Model.` prefix because they are no longer exports. D-SINK-19 round 9 (R19b, 2026-10-12; lane-key-y1 690a888). A guide URL input -- `omarchy bar set ... epgUrl` -- that arrived while NO source was active, HELD here, in this 0600 file, rather than on the bar entry in `shell.json`, where R12 had kept it for as long as no source existed. `url` is the normalized guide URL, validated as a CLI EPG value (a value that does not validate, or is empty, reads as nothing pending: `pendingEpgRecord`); `seenAt` is when the service first saw the input, in MILLISECONDS (`Date.now()`), which R19c compares with a record's `epgSetAt`. ABSENT, not null, when nothing is pending, so a state with nothing pending serializes exactly as it did before R19; additive at version 2 on the `hiddenGroups` / `activeKey` precedent, no version bump. A later input replaces an earlier one, and the next active move clears it whichever value wins (`applyPendingEpg`). Read through `pendingEpgOf`, written through `withPendingEpg`, and taught to `Model.parseState` and `Model.cloneState`. **NOT taught to the helper's `normalize_state`**, the third whitelist, which rebuilds the file from the keys it knows: any helper write of the file (`state favorite add|remove`, `state clear-recents`, the `state source` verbs, the one-time id remap [round 10: wrong about the remap -- `remap_state_file` edits the RAW document (`updated = dict(raw)`) precisely to stay clear of this whitelist, and the round-9 integration lens measured a call over a file carrying both keys keeping them: `moved 1 favorites ['z1'] pendingEpg kept True epgSetAt [1760000000000]`; the remap was never one of these routes]) erases it, and the input then exists nowhere -- the `savedSearches` lesson again. Open, with no id yet (lane A's report, 2026-10-12; `bin/` is another lane's): the fix is the helper's whitelist plus a shared fixture run by both suites [round 10: it is D-SRC-20 (P1, the chain only) on the board since the round-9 reviews, and R20a closes it on lane-key-z1]. **Amended 2026-10-12 (round 10, R20a; lane-key-z1 5b21950, lane A).** The helper keeps it: `normalize_state` carries `pendingEpg` through `normalize_pending_epg`, the mirror of `pendingEpgRecord` -- validated, never invented: `url` must BE a string (a list is no pending value on either side, the `activeKey` lesson one key along; the model's reader was tightened to match, `str()` having read `["http://h/g.xml"]` as that URL) that validates as a CLI guide URL to something non-empty, and `seenAt` is coerced the model's way and clamped at 0. Both readers run ONE fixture, `tests/fixtures/state-keys.json` (the `savedSearches` precedent): `tests/test_state.py` and `tests/Model.test.js` each run its value cases (node `R20a (shared fixture, both readers): pendingEpg ...`, eight of them). The helper's `state` verbs print it as `{ epgHost, seenAt }` (`public_state`), the host and never the value, because the helper's stdout is a rule-5 sink and that printer had never met a URL outside a record (`test_r20a_stdout_carries_the_held_guide_urls_host_never_the_url`). Observed at the sink by the round-9 lens's own driver under lane A's nested cage (`r9-child.sh T=helper HELPER_RESTART=1`): on lane-key-z1 the file still reads `pendingEpg=E` after a real `state favorite add` and the restart lands E on A (`RESULT helper: E is kept`); on lane-key-y2 `THE CLI GUIDE URL E EXISTS NOWHERE` (both outputs re-read by the documents lane, `lane-a-z1/live/helper-*.out` in the session scratch). |
| `entryInputs` | object `{ playlistUrl?, epgUrl? }`, optional; each slot `{ digest, at, stripped? }` | **WITHDRAWN 2026-10-13 (round 11, R21d; the round-11 rulings at the end of this file).** The key, its readers and writers and the helper's preservation of it are deleted, and both readers drop it from a file an earlier build of this chain wrote (shared fixture `tests/fixtures/state-keys.json`, `round 9 and 10 keys are dropped by both readers ...`). The text below is the round-9 and round-10 description, kept as written; the names in it are cited without the `Model.` prefix because they are no longer exports. D-SINK-19 round 10 (R20b, 2026-10-12; lane-key-z1 5b21950, lane A). WHAT THE SERVICE HAS ALREADY CONSUMED FROM THE BAR ENTRY, one slot per retired input (`Model.RETIRED_SETTINGS`). Until round 10 the only record of it was in memory (`Service.reconciledPlaylistUrl`, `reconciledEpgUrl`), so a restart began with every value on the entry fresh and adopted it again, seen NOW: a guide URL left there by a failed write (D-SRC-18) or written back by the lagging host's patch-only logo toggle (D-SINK-20's restart half) replaced a later in-app edit that had landed. `digest` is `entryInputDigest` of the consumed value: two FNV-1a 32-bit passes over the setting name and the value's ONE form (`Model.entryInputForm`), 16 lowercase hex digits -- a digest and never the value, because a REFUSED input is consumed too and can carry a credential the plugin strips from `shell.json` on purpose (rule 5), and the only question ever asked of a slot is whether the entry's value is THIS one (a collision makes one fresh input read as consumed, about 2^-64 per comparison; lane A's arithmetic). `at` is when it was consumed, in ms, recorded as R20b rules and decided on by nothing. `stripped: true` once an owned write has handed the host an entry WITHOUT that value (`entryInputsAfterWrite`); from then on the same value on the entry at the next start is the user setting it AGAIN -- an `omarchy bar set ... playlistUrl A` made while the shell was down -- and is fresh, which the lagging host, whose publish never shows our strip, would otherwise hide. The slot moves with its snapshot (`entryInputsAfterMove`), and the first reconcile after a start seeds the snapshot from it (`entryInputSeed`). It is NOT saved for its own sake: it rides the next state save, because a save issued for the slot alone held the strip behind it (R13) and reproduced the hidden re-set 308258f fixed (lane A: the R19c re-stamp case went red with an eager save). Absent when no slot is set; additive at version 2 on the `pendingEpg` precedent; read through `entryInputsOf` and `entryInputsRecord`, written through `withEntryInputs`; taught to `Model.parseState`, `Model.cloneState` (the seventh key that whitelist carries) and the helper's `normalize_state` (`normalize_entry_inputs`, which refuses a digest that is not 16 lowercase hex digits and never computes one) on the same day and the same shared fixture, and printed by the helper as it is, digests only, on the `activeKey` precedent. What a digest of a refused credential is, held in this 0600 file: a 64-bit confirmation oracle for a guess, the class `What REMAINS` item 1 in `ARCHITECTURE.md` section 6 describes for the 32-bit key in `shell.json`, and never a way back to the value. |
| `sources[]` | array, max 50 | Ordered by `addedAt`; the UI sorts by `lastUsed` desc [UX-ASSUMPTION]. **After D-SINK-19 this array is the ONLY copy of the source list** (SR39 cost 3): `shell.json` no longer holds the active URL, so there is nothing left to rebuild a lost record from. |
| `key` | string | `^[0-9a-f]{8}(-[0-9]{1,3})?$`, unique in the array; the cache directory name. |
| `url` | string, 1-2048 | Normalized playlist URL (section 3.1); unique in the array; **the identity**. Carries provider credentials; the file is 0600 (README note, same class as shell.json). **Reader parity (D-SINK-23, second half; the lead's ruling, 2026-10-24).** Both readers validate a STORED `url` as origin `cli` and keep the VALIDATED form, and both DROP a record whose `url` does not validate: the helper's `normalize_source` always did (`validate_source_url`, a `state: dropped source <key> (invalid url: <code>)` line), and `Model.normalizeSourceRecord` kept the text as written with length and control checks only, so a hand-edited file -- which the README invites -- held a URL the two mirrors read, keyed and redacted differently (`http://HOST.test?password=x` was one record to the shell and `http://host.test/?password=x` to the helper). The cost, stated: a hand-edited record the shell used to keep and the helper already dropped on its next write (`http://h.test:abc/`, `./list.m3u`, a bare host, `ftp://`, `/proc/...`) is now dropped by the shell too, journaled by key (`parseState`), never by URL; a `~/path` reads as `file` in both. Shared fixture `tests/fixtures/state-reader-urls.json`, run by `Model.parseState` in `tests/Model.test.js` and by `normalize_state` in `tests/test_helper.py`. |
| `epgUrl` | string, 0-2048 | Normalized EPG URL or `""`. Same parity rule as `url` (D-SINK-23): validated on read in both mirrors, a value that does not validate is CLEARED and the record kept (the same fixture pins it). |
| `epgSetAt` | epoch MILLISECONDS, optional | **WITHDRAWN 2026-10-13 (round 11, R21d; the round-11 rulings at the end of this file).** The key, its readers and writers and the helper's preservation of it are deleted, and both readers drop it from a file an earlier build of this chain wrote (shared fixture `tests/fixtures/state-keys.json`, `round 9 and 10 keys are dropped by both readers ...`). The text below is the round-9 and round-10 description, kept as written; the names in it are cited without the `Model.` prefix because they are no longer exports. D-SINK-19 round 9 (R19c). When this record's guide URL was last SET: by the add form at SUBMIT time (`Service.addSource` hands `Date.now()` to `Model.addSource`, which stamps it only when the form carries a guide URL), by the edit form when the edit CHANGES the guide URL (`Model.updateSource`; the form re-sends every field, so a label-only edit is not a guide-URL input, and a playlist-URL edit carries the stamp to the replacement record), by the adoption of a CLI input beside an active source (`Model.adoptActiveSource` with the input's `seenAt`; an input equal to the guide URL the record already holds is not re-stamped, 308258f), or by a pending value that wins (`epgByTime`). Absent when 0: a record written before R19 has none and reads as 0, older than any stamped input (`epgSetAtOf`), and a record that never had one serializes exactly as before (`Model.normalizeSourceRecord`). Milliseconds from the wall clock on both sides, so a clock stepped backwards between two inputs inverts their order -- recorded, not handled (lane A's reading (e)). Not taught to the helper's `normalize_source` either: a helper write resets every record's stamp to 0, so a value held later wins over an in-app edit at the next active move (the open item in the `pendingEpg` row) [round 10: D-SRC-20, closed by R20a, below]. **Amended 2026-10-12 (round 10, R20a; lane-key-z1 5b21950).** `normalize_source` carries `epgSetAt` when it is above 0, coerced as `Model.normalizeSourceRecord` coerces it, and absent otherwise (shared fixture: `epgSetAt kept on a record`, `coerced (1e3 -> 1000)`, `0, negative or junk is absent, never 0`, `junk text is absent`). The helper is also the third route that SETS a guide URL, which round 9's R19c search named and left unstamped: `state source add --epg-url` stamps it, and `state source update --epg-url` stamps it only when the guide URL CHANGES, as `Model.updateSource` does, in milliseconds (`--now` seconds times 1000, else the wall clock; `test_r20a_a_guide_url_the_helper_sets_is_stamped_with_its_time_and_an_unchanged_one_is_not`). That the helper's explicit-input route should stamp is lane A's reading of "never invented" as applying to the readers, for the lead to confirm. |
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
cache directory removed -- the same rule as any CLI adoption (risk R3)
[round 17, 2026-10-20, R27d (D-SRC-44): no longer. At the cap the step does
not run: nothing is added or evicted, the marker is not set, the entry keeps
its URL and the user is told once (`Sources is full`); the next reconcile
after a removal migrates. The round-17 rulings] [round 18, 2026-10-20,
R28b: and a guide URL on the entry beside that playlist is held WITH it --
not attached to any record, not reported, not stripped -- and moves in
with it after the removal. The round-18 rulings] [round 19, 2026-10-20,
R29d: and a guide URL beside a playlist that does not validate is attached
to no record either -- it used to replace the active record's own -- but
reported with it in one notice (`invalid-pair`) and stripped with it. The
round-19 rulings] [round 7 of the bounds sweep, 2026-10-22, D-SRC-64, the
owner's decision: WHERE THE HELD URLS REST. A migration held at the cap no
longer keeps them on the bar entry. The hold writes both -- the playlist and
the guide URL beside it -- into `state.json` (the plugin's own 0600 file)
under a key of the migration's own, `migrationPending: { playlistUrl,
epgUrl }` (`Model.migrationPendingOf`, `Model.withMigrationPending`, the
helper's `normalize_migration_pending`; the shared state-keys fixture holds
both readers to it, and every `state` verb prints it as hosts only): not a
source record, never counted against the cap, never a Sources row, and never
beside the marker (the pair says the migration is still to run, the marker
that it ran). The owned write that follows that state write's LANDING takes
both off the entry (`Model.retiredInputsToKeep`'s third input, the landed
pair: a retired key whose value is the parked one is redundant), so the entry
carries a URL only until the hold's own write lands -- not for the life of
the hold, and not re-carried by every owned write whatever the D-SINK-18
shield answered, which is what the #14748 review measured (`Q4 heldExposed`:
three URL-bearing hand-overs under an exposed verdict, zero refusals; now
zero hand-overs carry one). The pair is the migration's input whenever the
entry carries no playlist URL (`Model.reconcileAction`'s `parked`): the retry
a removal asks for, a foreign load, a restart mid-hold. A playlist the ENTRY
brings during the hold (a hand `omarchy bar set playlistUrl <any>`, the
parked one included) wins over the parked playlist, as the entry is read
until the marker lands (R21), and the parked GUIDE URL rides with it
whenever the entry carries none: the re-park at the cap keeps it beside the
entry's playlist, a landing puts it on that playlist's record, and an entry
guide URL, when present, wins [round 8, 2026-10-22, the round 7 recheck's
P2 #1: the first cut read the guide URL from the stripped entry on that path
and re-parked `{ entry playlist, "" }`, losing the only copy unreported;
pinned on both hosts and both echo modes, red on the round 7 merge]. It lands exactly as
the entry's copy did -- into a new record once a place is free, or onto a
record another program added for the same playlist meanwhile (a hand-run
`state source add`; that record then takes the parked guide URL as its own
when it differs, R4) -- and is dropped in the same state write that sets the
marker; it is also dropped when the retry refuses the playlist as invalid
(reported, marker set, as the entry's copy was); it is never dropped
otherwise, because a drop without a landing would lose the only copy. A hold
whose state write FAILED leaves the entry as it is (the keep rule reads the
landed state): the entry is the backup until a later save lands the pair
(after which the mirror the failed save left owing, R19d, strips it) or the
next start re-adopts it, R21e's shape. A merge that holds the migration
again (F1's "full" and "changed") re-parks the pair from the record it
dropped, so the retry has an input although the entry is empty; ours' pair
stands over theirs' in a merge, because memory is the only place the
credential is sure to be. F1's card and sentence stay true: both move in
together after a removal. An OLDER build's helper drops the key with the
marker, the downgrade the D-SINK-19 ruling accepts. Pinned through
`tests/service-harness.js` on both hosts and both echo modes, the review's
`Q4 heldExposed` sequence among them, and in the model; red on fe40b2c]. The
first version of this paragraph said the step "creates no record and deletes
none"; that was false against the code and is **WITHDRAWN 2026-10-11**. "Must not lose a
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

**Amended 2026-10-13 (round 11, R21; lane-key-m1 15896f1, b52e745).** The
fourth step is now the ONLY place the bar entry's URLs are read, and it runs
once per install. `Model.reconcileAction` answers `adopt` for a playlist URL
on the entry only while it is MIGRATING -- the state as last confirmed on disk
(`Service.landedState`) does not carry `entryMigrated` (section 2.1) -- and
`Model.adoptActiveSource` sets the marker in the same state it returns, so the
marker rides the adoption's own write and the entry's strip waits for that
write to land (R13, unchanged). A start over a state that already carries the
marker reads NOTHING from the entry: a URL there is refused, reported once
(`Model.entryInputNotice`) and stripped by the next owned write (R21b). A
guide URL on the entry with no source to attach it to is reported and
stripped, never held (R21c). Inside the window -- the migration has run and
its write has not landed -- a value is fresh unless it is the one this session
saw LAST (`Model.entryInputLast`; b52e745 fixed a first build in which a user
setting B and then the migration's own A again lost the second A). The
downgrade-then-upgrade sentence above is now partly OBSERVED: key-scenario G4
runs the REAL helper of the v0.13.6 tag over a migrated file (`state favorite
add`: `rc:0 marker:absent activeKey:absent records:2`), and G5 restarts the
current service over the entry 0.13.6 would leave (its URL back on it) and
reads the migration running again -- A active, the marker back, the URL
stripped, nothing reported. 0.13.6's own SERVICE was not run; that it, too,
drops the marker is read off its `cloneState` (v0.13.6 tag, a whitelist that
names neither `activeKey` nor `entryMigrated`), not observed.

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
  `state init` therefore creates a v2 file on fresh installs (`init_state_file`, `bin/omarchy-iptv:1579-1598`). [Round 12, 2026-10-13 (R22a): it reports what it FOUND at the path before it created or chmod-ed anything (`found`: `absent`, `file`, `other` or `unreadable`), never rewrites a file that exists, and every other `state` verb refuses a file that exists and cannot be read or parsed (`state_unreadable`) instead of writing the empty default over it.]
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

`sanitizeInput(text, max)`, the boundary rule for a NAME (the label, the
Xtream username and password): `str(text)` with every character in
`[\u0000-\u001f\u007f-\u009f]` removed (CR, LF, TAB included), leading and
trailing ASCII space and NBSP (`\u00a0`) trimmed, then truncated to `max`
UTF-16 units. Applied at a name field's boundary (paste, submit) and inside
`validateLabel` and `xtreamUrls` (for the username and password).

`sanitizeUrlInput(text, max)`, the boundary rule for a URL (the playlist,
the EPG, the Xtream server; **D-SRC-63, R32a''', 2026-10-22**): one leading
byte-order mark dropped (SR15), the six ASCII whitespace characters and
NBSP trimmed off both ENDS (a trailing newline from `wl-copy`, a
tab-indented line), then truncated to `max` UTF-16 units -- and NOTHING
inside the text deleted, because a URL reader REFUSES what the name rule
deleted: `sanitizeInput` served the URL fields until R32a''' and rewrote
them, so `http://u:pa<TAB>ss@h.test/x` validated as the password `pass`
in both mirrors and the user learned of it only as a wrong-password
failure, and `http://h.test/x<LF>http://evil.test/` validated as ONE url,
`http://h.test/xhttp://evil.test/`, which nobody typed. Chosen per field
by `Model.sanitizeFieldInput(field, text, max)` on a paste
(`Guide.qml`'s `pasteFromProcess`) and on submit (`formSubmitValues`);
applied inside `validateSourceUrl`, `sourceUrlWarning`, `xtreamUrls` (the
server) and on the CLI path (`entryInputForm`, `reconcileSources`, where
"no input" -- a value of whitespace or control characters alone, R18a --
is still judged by `sanitizeInput`'s emptiness). `editInsert` inserts
text as given: typed text has been through `typedText` (Qt's own
acceptance rule, no control character ever types) and a paste through
`sanitizeFieldInput`. The helper's `_sanitize_url_input` is the mirror.

`validateSourceUrl(text)` -> `{ ok, code, message, kind, url, host }`:

1. `s = sanitizeUrlInput(text, MAX_SOURCE_URL + 1)`; `""` -> `empty`;
   length > 2048 -> `too_long`; any control character
   (`[\u0000-\u001f\u007f-\u009f]`) anywhere in `s` -> `bad_url`
   (D-SRC-63: refused, never deleted; both state readers drop a record
   whose url holds one, so accepting it would store a source the next load
   discards). A decoded `file:` path is checked again in step 2
   (`file:///a%09b` decodes to a tab).
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
   (never sent). Whitespace anywhere in the rest -> `bad_url`, where
   "whitespace" is the READER's class: the union of JS `\s`, Python `\s`
   and U+FEFF (`Model.URL_SPACE_CODES`, the helper's `URL_SPACE_CHARS`, 30
   code points pinned by `tests/fixtures/url-whitespace.json`). Since
   D-SRC-63 the boundary deletes none of them, so every member is REFUSED --
   but by two checks, not one (D-DOC-24): the 10 control members (tab, LF,
   VT, FF, CR, U+001C..U+001F, U+0085) are refused by step 1's control check
   before the scheme is read and never reach this line, in either mirror
   (the helper names a tab as whitespace in its message, as this check
   would); the 20 non-control members reach this check and are refused
   here. Either way a tab, a line break, an information separator or
   U+0085 inside a password is `bad_url` and not a rewritten password.
   `url = scheme://[userinfo@]host[:port]path[?query]`, `host` as computed.
   **D-SINK-25 / D-SINK-27, ruling R32a (2026-10-21, round 3).** No URL is
   refused for an `@` after its authority, in either mirror. A password
   holding an unencoded `/`, `?` or `#` ends the authority early, and the
   string then READS as host = the username, port = the password's prefix:
   `http://user:2024/ab@host.test/list.m3u` is accepted as host `user`, port
   2024, labelled `user:2024` -- the RFC reading, which every standard parser
   gives and which is where a fetch goes. Round 2's refusal of that shape
   (`passwordReadAsPort`, lane-bounds-s, never shipped) also refused an
   Xtream `/playlist/<email>/<pass>/m3u_plus` link and a WebDAV link on a
   non-default port, both stored and working, and the helper dropped such a
   source on the first normalize after the upgrade (D-SINK-27); it is
   **WITHDRAWN 2026-10-22 (D-SINK-27)**. The display sinks (`hostPortOf`, `deriveLabel`, `sourceLabel`,
   `hostOf`) and validation show and use the RFC host, so a stored
   `http://host.test:25461/playlist/me@mail.test/pw/m3u_plus` resolves,
   normalizes and labels as `host.test:25461` exactly as before -- and the
   typo shape labels as its username, which is why the FORM WARNS rather
   than guesses. **R32a' (2026-10-22, round 4)**: the question "is this
   dotless RFC host a username, with the real host after a later `@`?" is
   ONE predicate, `Model.urlHostWithheld(text)` (the helper's
   `host_withheld`): the RFC host, read from the TYPED text (a fragment
   counts: normalization drops it), is not a bracketed literal and has no
   dot, and an `@` follows the authority before any URL whitespace.
   **R32a'' (2026-10-22, round 5)** gives it a second arm, under the same
   later-`@` condition: the authority carries a NON-NUMERIC port -- a `:`
   after its last `@` whose text, up to the next `;`, `=` or `&`, is
   non-empty and not all digits -- so `http://user.name:pa/ss@h.test/x`
   (a dotted username, which the first arm cannot see, D-SINK-35) and
   `http://me@mail.test:pa/ss@h.test/x` hold it, and so does a dotted host
   with a bad port and a later `@` (`http://h.test:pa/me@x.test/y`), which
   was the one invalid shape that drew the bare refusal under R32a'. A
   numeric port is not it (`http://user.name:2024/ab@host.test/x` reads as
   host `user.name`, port 2024, validates and prints `user.name`: the
   residual, stated); an EMPTY port is an RFC shape (`http://user:/ab@host.test`
   validates) and is not non-numeric; a bracketed literal is never withheld.
   It is computed independently of validation and has three customers:
   - a value that VALIDATES as http(s) draws the warning line,
     `Model.sourceUrlWarning(text)` -> `WARN_AT_AFTER_AUTHORITY` ("The host
     before the first / has no dot and an @ follows it. If a password holds
     /, ? or #, write them as %2F, %3F and %23."), rendered by
     `Model.formWarningLine(form)` over the playlist, then the EPG field, or
     the Xtream server, while the value warrants it (UX-SOURCES 4.3, 5.4);
     submit proceeds. A LAN name draws it too (`http://nas:8000/files/me@home/x`),
     and `localhost` gets no exemption: a sentence, not a refusal;
   - a value that does NOT validate and holds the predicate -- the ruling's
     own example `http://myuser:pa#ss@cdn.test/x`, which reads as port `pa`
     and is refused `invalid` -- gets the refusal WITH the encoding sentence
     appended (`Model.ENCODE_SENTENCE`: "Invalid URL - check the host. If a
     password holds /, ? or #, write them as %2F, %3F and %23."), for the
     playlist, the EPG field and the Xtream server alike, so the user who
     typed the typo the warning exists for is told how to fix it on the
     error line that wins over the warning (lane-bounds-s2's recheck P2);
   - the free-text redactors WITHHOLD the host when it holds (below).
   The shared fixture carries the readings for both mirrors and a `warn`
   flag that is the predicate: node reads it as the warning (a value that
   validates) or the appended sentence (one that does not), the QML spec the
   same, and the python mirror runs `host_withheld` over every flagged case.

   **Free-text redaction under R32a'** (`Model.redactUrls` through
   `Model.runHostParts`, the helper's `redact_urls` through
   `run_host_parts`). A free-text sink -- an mpv error, a helper line, a
   notification body -- must never carry a credential, and the host is a
   courtesy. The host is the RFC one, exactly as validation reads it: the
   authority ends at the first `/`, `?`, `#` or URL whitespace, its userinfo
   at the LAST `@` within it (D-SINK-1), and the printed host is cut at the
   first `:` (a port), `;`, `=` or `&` (a parameter delimiter, so a
   neighbouring query parameter never prints, D-SINK-23:
   `http://h.test?u=me@b.test&p=SECRET` prints `h.test`); a bracketed
   literal is the host up to its `]`, or nothing. **The RUN** -- where the
   URL stops inside the text -- and the authority end at the SAME class in
   both mirrors, and that class is the six ASCII DELIMITERS: space, tab,
   LF, CR, FF, VT (`Model.URL_DELIMITER_CODES` / `isUrlDelimiterAt`, the
   helper's `URL_DELIMITER_CHARS`; **R32a''', 2026-10-22, D-SINK-36**).
   Every other whitespace or control code point is URL text: a password
   holding U+FEFF, NBSP, U+2028, U+0085 or U+001C..U+001F stays inside the
   run, its authority ends at the `@`, and the HOST prints. A reader
   refuses, a redactor delimits: the union of JS `\s`, Python `\s` and
   U+FEFF (30 code points, `Model.URL_SPACE_CODES`, the helper's
   `URL_SPACE_CHARS`) is what validation REFUSES, and both lists are pinned
   by `tests/fixtures/url-whitespace.json` over the whole Unicode range in
   both suites, each asserting its engine's `\s` sits strictly between
   them. Until R32a'' the helper ended the run at Python `\s` plus `'"<>`
   and the authority at Python `\s` plus U+FEFF, and the model ended its
   run at JS `\s`: three classes, so a password holding U+FEFF printed the
   username in the helper (D-SINK-32), and one holding `'` printed the
   username AND the tail `'ss@prov.test/...` (D-SINK-33). R32a'' ended
   both at the union, and each mirror then took the other's worse case: the
   helper printed `http://myuser<U+FEFF>ss@prov.test/live/1.ts` where
   0.14.3 printed the host (D-SINK-36) -- the wider the class that ends the
   run, the more of a password a redactor copies through, which is why the
   redactor's class is the narrowest one that still ends a URL at a word
   boundary in an error line. `'`, `"`, `<` and `>` never end a run; they
   are sentence punctuation, and both
   mirrors strip `.,;:!?)]'"<>` off the run's end and put it back after the
   host (a `]` is kept when the run holds a `[`), so the model prints
   `Failed to open h.test.` where it used to drop the `.` and the helper
   prints `'http://h.test'` for a quoted URL. When the predicate above
   holds -- a dotless host, or a non-numeric port, with an `@` after the
   authority -- the host is
   WITHHELD and the one token `[host withheld]` prints in its place
   (`Model.HOST_WITHHELD`, the helper's `HOST_WITHHELD`; the model prints the
   bare token as it prints a bare host, the helper `scheme://[host withheld]`
   as it prints `scheme://host`). So `http://myuser:pa#ss@cdn.test/x` redacts
   to `[host withheld]`: never `myuser`, the username the RFC reading prints
   (D-SINK-28, round 2), and never `cdn.test`, the host after the later `@`
   that round 3's last-`@`-of-the-run scan printed -- because that same scan,
   on an `@` INSIDE a path or query credential, printed a password TAIL where
   0.14.3 printed the host: `http://prov.test/live/U5ER/P4@SSW0RD/1.ts` ->
   `SSW0RD`, `get.php?username=me@mail.test&password=p@ssw0rd` -> `ssw0rd`,
   on mpv's error line into the journal and the notification (D-SINK-29, the
   lead's ruling misreading the base; never shipped). Under R32a' both print
   the host, `prov.test` and `host.test`, and an Xtream
   `/playlist/<email>/<pass>/m3u_plus` link prints its server, not the
   email's domain. THE COSTS, stated: a dotless intranet URL with a path `@`
   (`http://nas:8000/files/me@home/x`) and a `localhost` URL with one are
   withheld, in free text only; the Sources row, the label and validation
   still show `nas` and `localhost`. One of the six DELIMITERS inside a
   password ends the run, so `http://myuser:pa ss@cdn.test/x` prints
   `myuser ss@cdn.test/x` in both mirrors -- the username and the
   password's tail -- and so does a tab, LF, CR, FF or VT in the same place
   (D-SINK-34, accepted and confined to those six by R32a'''); U+FEFF,
   U+0085, U+001C..U+001F, U+2028 or NBSP in the same place prints the host
   in both mirrors (under R32a'' they split the run too, and under 0.14.3
   each mirror split at its own `\s` and printed the host for the other's).
   A dotted username before a digits-only password prefix prints as the
   host (`http://user.name:2024/ab@host/x` -> `user.name`, D-SINK-35's
   residual). The fixture pins every one of these outputs exactly (`js`,
   `py`, `accepted`), so the cost is seen on every run rather than
   described. The nameless-channel fallback in the
   helper's play path (`fallback_channel_name`, D-SINK-31) uses the same
   predicate and names such a channel `Stream`. One shared fixture,
   `tests/fixtures/redaction-vectors.json`, holds both mirrors to the
   free-text rule (`host`, the token included) and the display sinks to the
   RFC host (`rfcHost`, `displayMustNotAppear`) where the two differ -- and
   under R32a' they differ ONLY by withholding or by an accepted cost,
   which the node suite asserts.
   The sink path is pinned as well as the function: the helper's player
   suite drives mpv's error line for the P1's URL into the `player start`
   reply's reason, and the node suite drives that reason shape through
   `Service.handleControlResult` to the `play failed:` journal line and
   through `Service.raiseStreamFailure` to the notification argv.
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
"/srv/tv/local.m3u" + LF                                            -> ok file "/srv/tv/local.m3u"   (a trailing line break is an edge, trimmed)
TAB + "http://h.test/x" + CR LF                                     -> ok http "http://h.test/x"     (the six ASCII whitespace characters and NBSP are trimmed off both ends)
"http://h.test/a" + NUL + "b"                                       -> bad_url                       (D-SRC-63: a control character INSIDE is refused, never deleted; it read "http://h.test/ab" until R32a''')
"http://u:pa" + TAB + "ss@h.test/x"                                 -> bad_url                       (D-SRC-63: it validated as the password "pass")
"http://h.test/x" + LF + "http://evil.test/"                        -> bad_url                       (D-SRC-63: it collapsed to ONE url, "http://h.test/xhttp://evil.test/")
"/srv/tv/a" + TAB + "b.m3u" / "file:///srv/a%09b.m3u"               -> bad_url                       (a control character in a path, raw or decoded)
""  /  "   "  /  LF TAB                                             -> empty
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
| `parseState(text)` | v1 or v2 text -> v2 object (section 2.2), records validated **Amended 2026-10-12 (round 9, R19b/R19c): carries `pendingEpg` (normalized, absent when nothing valid is pending) and each record's `epgSetAt` (absent when 0), so a state with neither parses and serializes exactly as before.** **Amended 2026-10-12 (round 10, R20b): carries `entryInputs` (`entryInputsRecord`, slot by slot, absent when no slot validates); and since R20a a `pendingEpg` whose `url` is not a string is no pending value.** **Amended 2026-10-13 (round 11, R21d): carries `entryMigrated` (exactly `true`, else absent) and no longer `pendingEpg`, `entryInputs` or a record's `epgSetAt`; a file an earlier build of this chain wrote is read without them.** |
| `cloneState(st, patch)` | new state with `patch` keys replacing; used by every existing reducer **Amended 2026-10-12 (round 9, R19b): the sixth key this whitelist is taught, `pendingEpg`, on the day it was added, carried only when a valid one is pending.** **Amended 2026-10-12 (round 10, R20b): the seventh key, `entryInputs`, on the day it was added, on the same terms -- carried only when a slot is set.** **Amended 2026-10-13 (round 11, R21d): the keys round 9 and 10 taught it are withdrawn with their machinery, and the marker `entryMigrated` is taught on the day it was added, carried only when it is `true` (lane A's mutant M9, `cloneState` drops the marker: 6 of 2,261 red).** |
| `withCacheLayout(st, n)` | `cacheLayout` set |
| `sourcesFull(state)` | R27c / R27d (round 17, 2026-10-20; `Model.sourcesFull`): THE CAP, one decision -- true when the state holds `MAX_SOURCES` (50) records or more; an empty or missing state has room. Asked by `addSource` (`too_many`), by the service's probe commit against the state as it is when the probe ends (D-SRC-41: a hand-run `state source add` may have taken the last place meanwhile; refused `too_many`, told through `sourceProbeFinished`, nothing recorded, the probe's cache directory removed), and by `reconcileSources` (`full`, never an eviction, D-SRC-44). The guide's own gate on the Add rows and `a` / `c` (`Guide.qml` `sourcesFull()`, SR24) compares `sourceCount` with `Model.LIMITS.sources`, the same constant, and is not this function **[Round 18, 2026-10-20, R28e: no longer -- round 1's review found a third comparison, `Service.canAddSource` (`sourceCount < Model.LIMITS.sources`), and both it and `Guide.sourcesFull()` now call this function over the service's `userState`, so the cap is one decision in the tree as the comment says. `parseState` and `mergeForeignState` share the constant and not the question: they TRUNCATE a list already over the cap that something else wrote, and say so in a comment]** |
| `addSource(st, fields, nowSec)` | `{ ok, code, message, state, key }`; `fields = { playlistUrl, epgUrl, label, origin }`; codes `empty`, `too_long`, `bad_url`, `unsupported_scheme`, `unsafe_path`, `duplicate` (returns the existing `key`), `too_many` **Amended 2026-10-12 (round 9, R19c, lane-key-y1): `fields.epgSetAt` (ms) is the moment the form was SUBMITTED, handed by `Service.addSource`; the new record carries it as `epgSetAt` only when the form carries a guide URL, so a blank field sets nothing and a pending input still lands on it (E4).** **Amended 2026-10-13 (round 11, R21d): `fields.epgSetAt` is gone; the record carries no set time whatever the caller hands it (`R21d: no reducer writes a set time ...`). The in-app forms are sequential, so the form's guide URL is simply the record's.** **Round 17, 2026-10-20 (R27c): the cap is `Model.sourcesFull(state)`, the one decision the probe commit asks too.** |
| `updateSource(st, key, fields, nowSec)` | `{ ok, code, message, state, key, urlChanged, replacedKey }`; label -> `labelCustom: true`; a changed playlist URL yields a NEW record (`key` new, `replacedKey` old, `fetchedAt: 0`, label/addedAt copied) and leaves the old one in place until the service confirms the probe (section 4.6); `unknown_source` **Amended 2026-10-12 (round 9, R19c): `fields.epgSetAt` (ms) stamps the guide URL only when the edit CHANGES it; the service always hands `Date.now()` and never a caller's own value, and a playlist-URL change carries the stamp to the replacement record.** **Amended 2026-10-13 (round 11, R21d): `fields.epgSetAt` is gone, as in `addSource`.** |
| `removeSource(st, key)` | `{ state, removed }` (`removed` = record or null). **D-SINK-19 round 2 (R3): removing the ACTIVE record clears `activeKey` in the state it returns**, so the file never names a record it no longer holds; the helper's `remove_source_record` has done the same since the key existed, and the shared fixture's `remove` cases run both |
| `touchSource(st, key, nowSec)` | `lastUsed` bumped |
| `withSourceStats(st, key, status)` | `fetchedAt`, `channelCount`, `groupCount` from a parsed `ok` playlist status |
| `reconcileSources(st, playlistUrl, epgUrl, previousActiveKey, nowSec, origin, opts)` | `{ state, changed, activeKey, added, evicted, invalid }` (D3; `invalid` = validation result when `playlistUrl` is set but invalid; `evicted` = LRU keys dropped beyond `MAX_SOURCES`, never the active one). **D-SINK-19 round 2 (R2): the adopted key is written INTO `state` through `Model.withActiveKey`**, on the known-URL path and on the added path; `activeKey` stays as an out-param for callers that read it **Round 17, 2026-10-20 (R27d, D-SRC-44): `{ state, changed, activeKey, added, full, invalid }` -- at `MAX_SOURCES` an unknown URL is NOT added and NOTHING is evicted: `full` is true and the state comes back as it was; a URL already among the 50 still resolves. `evicted` is gone, and with it the service's `cache remove` loop. Until R27 the least recently used non-active record was evicted, its URL the only copy, with a journal line only.** |
| *`activeSourceKey(st, playlistUrl)`* | **GONE (D-SINK-19).** It was the one function whose job was "name the active source from a URL", and it is deleted rather than left behind with no caller (the comment above `Model.reconcileSources` in `Model.js` says why). Identity by URL survives where it belongs, in `findSourceByUrl`. The active source is the rows below |
| `activeKeyText(value)` | the value as a key, or `""`: a STRING matching the key grammar, trimmed; a number, a list or anything else is `""`, which is also what the helper's `normalize_active_key` answers (shared fixture, `parse`) |
| `activeKeyOf(st)` | the state's `activeKey` when it names a record in `sources[]`, else `""`. The one resolver; `configured` is `activeKeyOf(state) !== ""` |
| `activeSourceRecord(st)` | that record, or null |
| `withActiveKey(st, key)` | the state with `activeKey` set (or cleared); the SAME object when nothing moves, so `changed` stays honest |
| `reconcileAction({ first, force, playlist, epg, lastPlaylist, lastEpg })` | `{ act, adoptUrl, adoptEpg, playlistChanged, epgChanged }`: `act` is `adopt` for a non-empty playlist input this service has not consumed (first reconcile, or different from the snapshot), `migrate` for a first or forced reconcile with no fresh URL, `ignore` otherwise; `adoptEpg` is the same rule for the EPG input, independently (R1, R4). **Amended 2026-10-12 (round 8, R18a, lane-key-x1 1f8bd1b): both sides are compared through `Model.entryInputForm` -- "changed" is "the forms differ", and "non-empty" is the form's text -- so a value that differs from the snapshot only in surrounding whitespace, scheme or host case, the default port or an embedded control character is NOT fresh, and a value of whitespace or control characters alone is no input. Until round 7 both sides were trimmed by `Model.settingsFrom` and agreed by accident; now they agree with `Model.retiredInputsToKeep` by construction (a 34-case property, round-8 rulings below).** **Amended 2026-10-12 (round 10, R20b): also hands `first` back as it came, because `Model.adoptActiveSource` judges an EPG input equal to the held one by the held one's time only on the first reconcile after a start.** **Amended 2026-10-13 (round 11, R21a/R21b; lane-key-m1 15896f1, b52e745): the signature is `reconcileAction({ first, force, migrating, playlist, epg, seen })` -> `{ act, adoptUrl, adoptEpg, refused, report, migrating }`, and the round-2 snapshot arguments are gone. `migrating` is `!Model.entryMigratedOf(landedState)`. MIGRATING, a value is fresh unless it is the one `seen` holds LAST for its setting (`Model.entryInputLast`, R1's snapshot); `act` is `adopt` for a fresh playlist URL, `migrate` for a first or forced reconcile with nothing to adopt, `ignore` otherwise; `adoptEpg` likewise. MIGRATED, nothing is adopted: every retired key that carries a value (by `Model.entryInputForm`) is in `refused`, and the ones `seen` has not seen at all (`Model.entryInputSeen`) are in `report`. `seen` is `Service.entryInputsSeen`, in memory only (R21b). Lane A's mutants (of 2,261): always migrating 64, membership instead of the last value 3.** **Round 17, 2026-10-20 (R27d): `heldFull` -- this session's migration found Sources full -- makes a MIGRATING playlist URL fresh again whatever `seen` says, so the reconcile a removal asks for tries it once more; the guide URL is not made fresh by it.** **Round 18, 2026-10-20 (R28b): it makes the guide URL fresh too, so the retry adopts the two together (R21); with only the playlist fresh the guide URL read as seen, the migrated record got none, and the strip that followed took it off the entry (lane A's mutation "retry fresh for the playlist only": 5 red in each echo mode).** |
| `adoptActiveSource(st, entry, nowSec, origin, { adoptUrl, adoptEpg })` | `{ state, key, changed, moved, adoptedUrl, adoptedEpg, invalid, added, evicted, writeEntry }`: resolves the active source in the order fresh entry URL -> state key -> entry mirror -> nothing (R1), attaches a fresh EPG input to the active record on any path, reports an invalid input without touching the key, and says whether the entry must be rewritten (it still holds a URL, or its mirror disagrees). `moved` -- a DIFFERENT source than before -- is the only thing that resets the status line. **Amended 2026-10-12 (round 8, R18a): the playlist input is `Model.entryInputForm`'s text and the EPG input its whole form, so an EPG of control characters alone is no input and never replaces the active record's guide URL with the empty one it used to validate as (the sibling R18a's search found). `writeEntry` is still asked from the entry as published, stale copy included -- the same answer heals a value D-SINK-20's patch-only write re-carried -- and a write that would change nothing the host stores is declined in the funnel (`entryWriteNeeded`, R18b).** **Amended 2026-10-12 (round 9, R19b/R19c, lane-key-y1 690a888): `opts.seenAt` (ms) is when the service saw the inputs. A held `pendingEpg` meets the record that is active after step 1-4 BEFORE R4 runs, so an input seen in this same reconcile lands on top of the result (`applyPendingEpg`). R4's adoption stamps the record's `epgSetAt` with `seenAt` and does not re-stamp a guide URL the record already holds. With NO active source a valid EPG input is held as `pendingEpg` and CONSUMED (`epgConsumed` true, so the owned write that follows the save strips it), and a refused one is consumed as refused (lane A's reading (a)); R12's "not adopted and not stripped" is overturned. The result gains `pendedEpg`, `refusedEpg`, `pendingApplied` and `pendingSuperseded`, which the service logs by setting and key name.** **Amended 2026-10-12 (round 10, R20b; lane-key-z1 5b21950 and 92395c4): `opts.atStart`.** At a START, an EPG input EQUAL to the guide URL the state already holds as pending is that same input, still on the entry because its strip never landed, and is judged with its `seenAt`, never with now: if the active record's guide URL is later it loses (`epgByTime`), and a value held again keeps its first `seenAt`. This closes the round-9 data-loss lens's P3 (the pending E lost to a later G by time and was then adopted as the latest input in the same call). NOT in session: there the service SAW the entry change to that value, the user setting it again, a later explicit input (R19c); the in-session reading, lane-key-z1's first build, was measured wrong by the round-9 lens's own matrix (`EPG:OLD:init` 4 and `EPG:OLD:cli` 2 at length 2, a CLI re-set of the held value losing to an older record time) and withdrawn in 92395c4. Usually the start never reaches this branch, because the consumed slot (`entryInputs`) proves the value spent; it is the start over a file an earlier build wrote, with no slot. **Amended 2026-10-13 (round 11, R21; lane-key-m1 15896f1): `opts` is `{ adoptUrl, adoptEpg, migrating }`, each false when absent, so a caller with no plan reads no URL at all. The round-9 and round-10 options (`seenAt`, `atStart`) and results (`pendedEpg`, `pendingApplied`, `pendingSuperseded`, the `epgConsumed` / `epgEcho` entry rule) are withdrawn. A guide URL the plan adopts with NO record to land on is `noSourceEpg` (R21c: reported and stripped, never held); one that does not validate is `refusedEpg`; `migrating` sets the marker in the state returned (`Model.withEntryMigrated`; `marked` says whether this call set it); `writeEntry` is true whenever the entry carries a retired key or its mirror disagrees. Lane A's mutant M4, no marker set by the migration: 30 red.** **Round 17, 2026-10-20 (R27d): `evicted` is replaced by `full` -- step 1 found Sources full; resolution continues at step 2 as for an invalid value, and the marker is NOT set when `full`, so the entry funnel keeps the URL (`retiredInputsToKeep`) and the next reconcile after a removal migrates (`reconcileAction`'s `heldFull`). The R4 guide-URL block still runs on the step-2 key: with a fresh entry guide URL it is attached to whatever source step 2 resolved, which is not the entry's playlist -- measured by the documents lane, raised to the lead (the round-17 rulings).** **Round 18, 2026-10-20 (R28b): A HELD MIGRATION HOLDS BOTH URLS. With `full`, the R4 block does not run: the entry's guide URL is not adopted onto any record, not refused, not reported `no-source`, and is held beside its playlist (on the entry until D-SRC-64; in `state.json`'s parked pair since, 2.2); the result gains `heldEpg` (the entry carries a guide URL held with it). Round 1 measured both losses the step-2 attachment caused, through the shipping `Service.qml`: a source picked meanwhile had its own guide URL replaced by the bar's at the next start, and "Remove one" migrated the playlist with no guide URL and stripped the bar's. Lane A's mutation "R4 runs on full": 9 red in each echo mode.** **Round 19, 2026-10-20 (R29d): A GUIDE URL THAT CAME WITH AN UNUSABLE PLAYLIST IS NEVER ADOPTED ONTO ANOTHER SOURCE. The R4 block does not run either when the playlist beside the guide URL is unusable -- the one step 1 just refused (`invalid`), or, when the entry's playlist was seen and so not adopted again, one that does not validate (`entryPlaylistUnusable`, the test `reconcileSources` makes) -- and the result gains `epgWithInvalid`. Until R29d the `invalid` branch put the entry's guide URL on the step-2 record, replacing the active source's own (round 2's review, `Aepg: "BAR"`, on 6f1d176, 0.14.2 and lane-sweep-c2 alike). Called on lane-sweep-c3: an `ftp://` or bare `http://` playlist beside a guide URL, A active with its own, gives `epgWithInvalid: true, adoptedEpg: false` and A's guide URL unchanged; lane-sweep-c2 gives `adoptedEpg: true` and A's the bar's. Lane A3's mutations: R4 beside an unusable playlist 13 red, the seen sibling not handled 5.** |
| `pointerWritePlan({ keyMoved, dirsReady, savePending, savesInFlight, saveFailed })` | `{ steps, entryWaits }` with `steps` drawn from `save-state`, `defer-state`, `write-entry`, `write-entry-after-saved`, `wait-entry`: the state is saved before the entry is written, and the entry WAITS for the state save to LAND on every route (R5, then R13 on 2026-10-12): `write-entry` is immediate only when nothing of ours is outstanding -- no save parked, none in flight, the last one not failed -- otherwise the key is held and `Model.entryFlushDisposition` settles it from the FileView's `saved` / `saveFailed`; `Service.persistActive` executes the steps, and `stateInitProc`'s exit, `saved` and `saveFailed` settle a held entry. `savesInFlight` and `saveFailed` are round-4 inputs (lane-key-t1; `Model.pointerWritePlan`); the shared fixture's `order` section has 13 cases since round 4 (8 before) |
| `stateSaveLanded(viewText, askedText)` | R13 (lane-key-t1; `Model.stateSaveLanded`): whether the write the service last asked for is the one the FileView has just reported on -- the view's text IS the last text asked for, and that text is non-empty. "Landed" is read by CONTENT, not by counting `saved` signals, because a burst coalesces queued writes and a replaced one raises nothing (10 warm switches: 20 `setText`, 14 `saved` on lane-key-t1, 15 on lane-key-s2; lane A, 2026-10-12, `OMARCHY-PLUGIN-CONTRACT.md`) |
| `countReload(counts, reason)` | R15 (lane-key-t1; `Model.countReload`): the reload counter by reason -- a NEW object (a `property var` mutated in place raises no change signal) with `reason`'s count incremented, keyed by the string `Model.reloadDisposition` answered, so the counter cannot name a reason the decision does not; the service's `stateReloadsByReason`, reported through the harness's `pointerState` |
| `ownedWriteMode({ stateLoaded, savePending, savesInFlight, saveFailed })` | R16 (lane-key-u1; `Model.ownedWriteMode`): what an owned-entry write that is NOT the key mirror may carry -- `{ mode, reason }`, `patch` with `save-parked` / `save-in-flight` / `save-failed` whenever one of the three flags is raised, `heal` with `settled` otherwise; the three flags and nothing else (fixture section `ownedWrite`, 8 cases, the whole cube). **Amended 2026-10-12 (round 6, lane-key-v1 78ff442): a FOURTH input, `stateLoaded`, checked first -- anything but `true` answers `patch` with `state-not-loaded`, because before the first state load memory is the empty state and no save flag is raised, so the three flags alone answered `heal` there and a logo toggle stripped a URL set while the shell was down (the fifth review's data-loss P2). `heal` now means loaded AND nothing outstanding; the four inputs and nothing else; the `ownedWrite` section is 16 cases, the four-input cube.** **Amended 2026-10-13 (round 12, R22a; lane-key-n1 16a3bc9): a FIFTH input, `blocked` (the no-write mode's reason), checked before every other, and a third answer, `none` with reason `state-unreadable`: in the no-write mode no owned write is made at all, the patch included, because the entry may hold the only copy of an input the unread file could not tell us about (`R16 / R22a: the fixture covers the whole five-input cube ...`).** |
| `stateLoadKind(result)`, `STATE_LOAD_ERRORS` | R22a (round 12, lane-key-n1 16a3bc9; `Model.stateLoadKind`, `Model.STATE_LOAD_ERRORS`): what one load of `state.json` IS. `result` is `{ loaded: true, text }` from `onLoaded` or `{ loaded: false, error }` from `onLoadFailed`; the answer is `loaded` (the text parses as a JSON object), `unparsed` (read and not one, an empty file included), or the failure's kind by Quickshell's `FileViewError` number -- 1 `io-error`, 2 `absent`, 3 `permission`, 4 `not-a-file` -- and `io-error` for any number the table does not know, never `absent` by default. The numbers are the enum's declaration order, measured (the round-12 rulings) and pinned against the installed qmltypes |
| `stateInitFound(text, exitCode, timedOut)` | R22a (`Model.stateInitFound`): the helper's start-up `state init` reply -> `absent` only for the init's own `found: absent`, [round 14, R24b: `link` and `not-a-dir` for the init's own answers of those names; round 15, R25c: `folder-link` too, a link at the state FOLDER, or above it, that dangles or leads to something that is not a folder;] `present` for `file`, `other` or `unreadable`, `unknown` for a failed exit, no reply, another verb's reply or a reply without the field. The one witness that tells a missing file from a file inside a directory the FileView cannot search, which it reports identically (FileNotFound) |
| `stateLoadDecision({ kind, loadedBefore, initFound, retried })` | R22a (`Model.stateLoadDecision`): `{ act, reason }` for a load that is not `loaded` -- `apply` for a state; mid-session (`loadedBefore`) `block` at once; at a start `wait` until the init answers, `fresh` ONLY when the load is `absent` and the init found `absent`, else `retry` once (the init restores the 0000 modes it finds) and then `block`, with reason `absent-unconfirmed` for a FileNotFound the init contradicts [round 14, R24b: after the one re-read, an init that answered `link` or `not-a-dir` blocks with THAT reason instead of `absent-unconfirmed`; round 15, R25c: and `folder-link`] |
| `stateWriteGate({ blocked, loaded, dirsReady })` | R22a / R22b (`Model.stateWriteGate`): the one gate `Service.saveState` asks first -- `refuse` in the no-write mode whatever else is true, `park` before any state has loaded or before the directories are ready, `write` otherwise. Before R22a a save made with the directories ready and the load still outstanding wrote the empty default over the file |
| `stateSavePlan(ctx)`, ~~`stateVerifyTimeoutAct(ctx)`~~ (withdrawn, R29a) | R26a / R26b, amended by R27a (round 17, 2026-10-20, D-SINK-22; `Model.stateSavePlan`, and `stateVerifyTimeoutAct` until R29a withdrew it). `stateSavePlan` answers each save `join`, `park`, `refuse`, `verify`, `defer`, `write` (the round-16 rulings) or, since R27a, `wait`: one of our writes is in flight (`inFlight > 0`) and the wait has not expired, so nothing is issued; the FileView's `saved` or `saveFailed` for that write ends the wait (`Service.endStateWriteWait`) and asks for the save again from a turn of its own, which reads. Every save asked during the wait is the same held save. A wait not ended within 2 s (`stateWriteWaitWatchdog`) sets `waitExpired`, and the held save goes to its read, which the view drops while the write is out, so the read's own bound decides. `write` is answered only to the verify's finish (`verifyDone`); the R26 branch that wrote from a deferred turn while a write was in flight, skipping the read, is gone. `stateVerifyTimeoutAct({ retried })`: the read's 2 s bound fired -- `retry` (ask for the load once more, the bound again) the first time, `block` (the R22 no-write mode, reason `read-timeout`, the save refused) the second. Never a write: until R27 the watchdog wrote without the read **[Round 18, 2026-10-20, R28a: `block` is gone, and with it `read-timeout`. `stateVerifyTimeoutAct({ silences, silentMs, told })` -> `{ act: "retry", boundMs, tell }` always: `silences` counts this held save's silent reads, this one included; `boundMs` is the next read's bound, `stateReadBoundMs(silences)`; `tell` is true once `silentMs` reaches `STATE_READ_TELL_MS` (8000) and the user has not been told about this held save. The save stays parked (`stateSavePending` and `stateVerifyPending` stay set), memory the authority, and every save asked meanwhile joins it (`join`). The name is R27a's, kept because the documents and the defect ledger cite it]** **[Round 19, 2026-10-20, R29a: `stateVerifyTimeoutAct` is withdrawn with R28a's hold; what fires the bound decides nothing in the model any more. `Service.finishStateVerify(true)` is 6f1d176's R26a body word for word: the save is written without its read, counted (`stateVerifyNoLoad`) and logged, `state.json was not read back within <ms> ms of a save; saving without the read`. The name survived in `model/state.mjs` as an inert stub that answered null while the documents were re-cited, and was DELETED with the other four on 2026-10-20 (lane-sweep-f4, F3): no longer declared or exported. `stateSavePlan` is unchanged, `wait` included: an expired wait releases the held save to its read, which the view drops while the write is out, and R26a's bound then writes without it, 4 s after it was asked -- never blocked, never held longer]** |
| `stateUnreadableNotice(reason, path, midSession)` | R22a (`Model.stateUnreadableNotice`): `{ title, body }`, the ONE sentence the user is told once per no-write episode, as a critical notification (replace id 74017) and on the console -- `Saved sources not loaded` / `<path> <what>. Nothing is saved until it can be read, so sources, favorites and settings changed now are not kept. <fix>`, composed from the reason and the path alone, never a URL; the six reasons and their text are in the round-12 rulings and `UX-SOURCES.md` 5.10 [round 14 added `link` and `not-a-dir` and split `absent`; round 15 adds `folder-link`, which names the FOLDER: `<folder> is a symbolic link whose target is missing or is not a folder (or a folder above it is)` / `Restore the folder it points to, or move the link aside, then run omarchy restart shell.`] **Round 17, 2026-10-20 (R27e, D-SRC-42, D-SRC-50, D-SRC-51): the title is `Saved sources not loaded` (`STATE_BLOCK_TITLE_START`) for a block that begins at a start and `Saving has stopped` (`STATE_BLOCK_TITLE_MID`) for one that begins after a state loaded; the body is `<path> <what>. Sources, favorites and settings changed now are not saved until the file can be read again. <fix>` (`STATE_BLOCK_UNSAVED`); `absent`'s `<fix>` leads with `STATE_BLOCK_LINK_FIRST`, `link` and `folder-link` say point it back; R27a adds `read-timeout`. Every sentence is in `tests/fixtures/state-notices.json`; the round-12 table below carries the current copy.** **Round 18, 2026-10-20 (R28e, R28a): the body's second sentence differs between the two. At a start it is `STATE_BLOCK_UNSAVED_START`, `Sources, favorites and settings changed now are not kept.` -- nothing has loaded, so the load that lifts the block is applied over such a change on every way back. Mid-session it is `STATE_BLOCK_UNSAVED` (R27e's name, kept for the documents that cite it), `Favorites and other changes made now are held in this session only: the next such change made here saves them if it finds the file again, but they are dropped if the file comes back by itself first, if a source change is what finds it, or if the shell is stopped.` -- R27e's "not saved until the file can be read again" was true of one way back and false of three (round 1's review, measured live and through the shipping `Service.qml`). `read-timeout` is withdrawn (R28a); a reason the function does not know reads `io-error`'s `<what>` and `<fix>`. The fixture holds `bodies.start` (ten reasons) and `bodies.midSession` (the five load kinds), word for word.** |
| `stateUnreadableJournal(reason, path, midSession)` | R27e (round 17, 2026-10-20; `Model.stateUnreadableJournal`): the console line for the same episode, `<title>: <body>` of `stateUnreadableNotice`, so the journal is titled as the notification is (D-SRC-42). `Service.blockStateWrites` logs it as `omarchy-iptv: <line>` and hands the notification `midSession` = `stateLoaded` |
| ~~`STATE_READ_BOUNDS_MS`, `STATE_READ_TELL_MS`, `stateReadBoundMs(silences)`~~ | **WITHDRAWN 2026-10-20 (round 19, R29a): there is no schedule. The three names were inert stubs in `model/state.mjs` that answered null until no document cited them in the `Model.` form, and were DELETED on 2026-10-20 (lane-sweep-f4, F3); `stateVerifyWatchdog`'s interval is the literal `2000` again. What follows is R28a's, history.** R28a (round 18, 2026-10-20): the held save's read schedule. `STATE_READ_BOUNDS_MS` is `[2000, 2000, 4000, 8000, 16000, 30000]`; `stateReadBoundMs(n)` is the bound of the read asked after `n` silences, the last entry for every `n` past the end, and 2000 for `n` of 0 or anything that is not a positive number. So a silent file is read again at 2, 4, 8, 16, 32 and 62 s after the save first asked, then every 30 s, for as long as the change is held: the interval is bounded, the number of re-reads is not. `Service.stateVerifyWatchdog`'s interval is the binding `stateVerifyBoundMs`, set from this before each restart. `STATE_READ_TELL_MS` is 8000, the third silence on this schedule |
| ~~`stateReadStalledNotice(path)`~~ | **WITHDRAWN 2026-10-20 (round 19, R29a): no notice is sent for a read that does not answer; `notifyArgv("stateReadStalled")` returns null, `NOTIFY_IDS` has no `stateReadStalled`, and 74019 is retired, not reused (a comment in `model/build.mjs` says so). The name was an inert stub that answered null until no document cited it in the `Model.` form, and was DELETED on 2026-10-20 (lane-sweep-f4, F3). No shipped copy carries the sentence below. What follows is R28a's, history.** R28a (round 18, 2026-10-20): `{ title, body }`, told ONCE per held save when its reads have been silent for `STATE_READ_TELL_MS`, as a normal-urgency notification with its own replace id 74019 (`NOTIFY_IDS.stateReadStalled`; it refuses nothing, so it neither replaces nor is replaced by the no-write card on 74017) and on the console as `omarchy-iptv: <title>: <body>`: `Saving is waiting` / `<path> has not answered for 8 seconds when it was read before a save. The change is kept in this session and saved when the file answers; if the shell is stopped first, it is lost.` Composed from the path and the constant alone, never a URL. The told flag is reset when the read finishes, with the silence count and the bound, in `finishStateVerify` and nowhere else (R28c) |
| `stateBlockedHeader(reason, path, midSession)` | D-SRC-38 (round 15; `Model.stateBlockedHeader`): the no-write mode's SHORT form, for the Sources header's right slot (`Model.sourcesHeaderRight(n, stateBlocked, path, midSession)`): `""` with no reason; `Saving has stopped` when the block began MID-session (a state had loaded, so the rows under it are the session's and still play; `Guide.qml` hands it `service.stateLoaded`); otherwise `Model.stateUnreadableNotice`'s title, `Saved sources not loaded`. One function, the notice copy family **Round 17, 2026-10-20 (R27e): it is now simply `stateUnreadableNotice(reason, path, midSession).title` -- the header, the notification and the journal take one word.** |
| `sameState(a, b)`, `stateCanonical(state)` | R24a / R24c (round 14; `Model.sameState`, `Model.stateCanonical`): whether two states -- objects, or the texts of files -- are the same state as a reader of the file sees it: each read through `parseState`, then serialized with its keys sorted at every depth. So the helper's compact JSON and the service's indented JSON of one state compare equal, and the init's empty default equals `parseState("")` (pinned). What `Service.applyUserState` hands `Model.reloadDisposition` as `matchesBase` [and, since round 15 (R25a), as `memoryMatchesBase`, `sameState(userState, landedState)`: with nothing held, a reload whose text is the base over a memory that is the base changes nothing and is ignored as `unchanged` -- the echo of the save that just landed, a chmod, an identical rewrite] |
| `mergeForeignState(base, ours, theirs)` | R24a (round 14; `Model.mergeForeignState`): `{ state, conflicts }` [round 15, R25b: `{ state, conflicts, dropped }`], THE three-way merge of a FOREIGN write into a session that holds a change the file does not. Sets (`favorites`, `hiddenGroups`, `savedSearches`) merge; `sources` merge by key; `recents`, `activeKey`, `lastPlayed`, `session`, `cacheLayout` are taken whole; `entryMigrated` is set if either side has it [2026-10-20, F1 (lane-sweep-f4): except when it is OURS ALONE and the record the migration added -- `opts.migrationKey`, `Service.migrationAddedKey` -- did not land as ours: dropped at the cap (`migrationHeld` "full": the record is not counted in `dropped.sources`, and an `activeKey` naming it goes back to theirs) or replaced by theirs' version of the same playlist (`migrationHeld` "changed"). Then the marker is not carried, the entry keeps both URLs, the service logs `Model.migrationHeldAgainLine(why)` (no key, no URL), sets `migrationHeldFull`, and the reconcile the merge runs retries at once: over "changed" it migrates onto theirs' record, the bar's guide URL with it; over "full" it is held under the one `Sources is full` card until a removal. The signature is `mergeForeignState(base, ours, theirs, opts)`, `{ state, conflicts, dropped, migrationHeld }`]; a conflict goes to theirs and is reported as `{ field, key, fields }` with no value. The field table is in the round-14 rulings; the fixture is `tests/fixtures/state-merge.json` [round 15, R25b (D-SRC-31): the caps are applied INSIDE the merge, not left to `parseState`: theirs keeps its place and what goes past `MAX_SOURCES` (50), `MAX_SAVED_SEARCHES` (20) or `MAX_HIDDEN_GROUPS` (200) is always ours' additions, dropped and returned as `dropped` -- `sources` the keys, `savedSearches` and `hiddenGroups` counts; and the sets are built on THEIRS, theirs' order first, which the function's comment now says (D-SRC-37)] |
| `mergeDropLines(dropped)`, `mergeDropNotice(dropped)` | R25b (round 15; `Model.mergeDropLines`, `Model.mergeDropNotice`): what a merge that dropped anything at a cap tells. The journal: one line per dropped element, `state.json was changed by another program while a change made here was not yet saved; the source <key> added here was not kept (the limit is 50 sources)`, `...; a saved search made here was not kept (the limit is 20 saved searches)`, `...; a group hidden here was not kept (the limit is 200 hidden groups)` -- a source by its key, the others as themselves, never a query or a group name. The user, ONCE per merge (notification, replace id 74018, normal urgency): `Not every change was kept` / `Another program changed state.json while a change made here was not yet saved, and together they went past a limit. The other program's version was kept, and <N> source(s) added here (the limit is 50 sources) [and ...] was/were not kept. Make room, then add it/them again.` -- counts and constants only. `null` and `[]` when nothing was dropped |
| `mergeConflictLine(conflict)` | R24a (round 14; `Model.mergeConflictLine`): the console line for one conflict, `state.json was changed by another program while a change made here was not yet saved; kept the other program's version of <field>` or `... kept the other program's version of the source <key> (<field names>)` -- never a URL or a value [round 15, D-SRC-36: `version of` added; the line read `kept the other program's the source <key>` until then] |
| `stateSaveOutcome({ viewText, lastSaveText, recentSaves })` | D-SRC-39 (2026-10-24, P23 lane A; `Model.stateSaveOutcome`): what a `saved` / `saveFailed` report means for the BASE, from the burst record -- `{ landed, last, state, remaining }`; `last` is `stateSaveLanded`, and a `saved` whose text is an EARLIER member of `recentSaves` is a landing whose `state` becomes `landedState` with the record trimmed to the texts after it. Both outcome handlers take it. |
| `mergeLeavesNothingUnsaved(merged, theirs, { savesInFlight })` | D-SRC-43 (2026-10-24; `Model.mergeLeavesNothingUnsaved`): true when the merge IS theirs and no write of ours is in flight -- `mergeForeignText` then clears `stateSaveFailed` and `recentSaves`. The owed entry mirror is still paid by the next landed save. |
| `mergeConflictNotice(conflicts)`, `MERGE_CONFLICT_TITLE`, `mergeConflictSentence(conflict)` | D-SRC-33 (2026-10-24; `Model.mergeConflictNotice`): `{ title: "Settings merged", body }` -- one sentence per conflict, `<The source <key> (<fields>) \| The active source \| The recent list \| ...> kept the other program's version.`; a field name and a key, never a value; null for none. Raised once per merge through `Service.notify("mergeConflict", ...)`, composed into the 74020 argv by `Model.notifyArgv`'s `mergeConflict` branch (`model/privacy.mjs`, normal urgency, the alert glyph). The lane's first tip had the event, the id and the notice but no branch, so the sink got null and the user nothing; the branch landed on 2026-10-24 (P23 lane A2) with a node check that CALLS `notifyArgv("mergeConflict", ...)` and one that reads the argv off the harness's `execDetached` -- both red before it (rule 13: an event name and an id are a join by name until a call makes it one). |
| `probeCommitPlan({ commit, mode, key, newKey, activeKey })`, `probeCommitState(state, plan, newKey)` | D-SRC-14 (2026-10-24; `Model.probeCommitPlan`): `{ wasActive, act: "switch" \| "reload" \| "none" }` decided against the active key BEFORE the probe commit publishes; `probeCommitState` folds the new key into that state when the active source was edited, so no published state lacks an active source. |
| `stateModeArgv(helperPath, stateDir)`, `stateModeReply(text)` | D-SRC-49 / D-SINK-22 (b)(c) (2026-10-24; `Model.stateModeArgv`): the argv of the helper's `state mode`, run after every landed save on `stateModeProc`; `stateModeReply` reads its one line -> `{ folder, file }` of `changed` \| `kept`, null for anything else. |
| `lastErrorAfterStatus(lastError, previousReason, nextStatus)` | D-SRC-52 (2026-10-24; `Model.lastErrorAfterStatus`): a good playlist status clears exactly the sentence the replaced status composed (captured before the reassignment) and nothing else; a failed one writes its reason. |
| `stateLoadDecision(...)`, the `initRetried` input and the `reinit` act | D-REL-8 (2026-10-24; `Model.stateLoadDecision`): an `unknown` init verdict with `initRetried` false answers `{ act: "reinit" }` before any re-read; the service re-runs `state init` once (`stateInitRetry`, 1 s) and sets the flag. `timeout` still blocks at once. |
| `persistFailureMessage(reason)` | R16 (lane-key-u1; `Model.persistFailureMessage`): the sentence for THE reason `sourcesPersistFailed` carried, over `Model.PERSIST_FAILURE_REASONS` (`state_write_failed`, `config_unsafe`, `persist_failed`); an unknown reason falls back to `persist_failed`'s sentence; what the guide renders on the result line and in the footer |
| `invalidInputBlocks(invalid, activeKey)` | whether a refused input becomes the guide's error state: only when there is no active source to show instead (D16, narrowed) |
| `sourceRows(st, activeKey, nowSec, errors)` | UI rows, sorted `active` first then `lastUsed` desc [UX-ASSUMPTION]: `{ key, label, host, kind, active, channelCount, groupCount, lastUsed, lastUsedText, fetched, epgConfigured, origin, errorReason }` -- no URL field, ever |
| `sourceForEdit(st, key)` | `{ key, label, labelCustom, kind, host, playlistUrl, epgUrl, playlistMasked, epgMasked, origin }` or null -- the only function that hands a URL to the guide |
| `sourcesSummary(st, activeKey)` | IPC list `{ key, label, host, active, channelCount, lastUsed }` |
| `entryWith(entry, patch, opts)` | full bar entry for `updateEntryInline`: every own key of `entry` copied EXCEPT `Model.RETIRED_SETTINGS` (`playlistUrl`, `epgUrl`, D-SINK-19), `patch` applied, `id` forced. Since R16 (round 5) `opts.keepRetired` true carries the retired keys over UNCHANGED -- the patch-only logo write while a state write is outstanding, and since round 6 before the first state load; "unchanged" is as the host PUBLISHES them, which on the host that publishes one write behind can be a copy one write old (D-SINK-20); the default is still removal, which is what the mirror and the settled toggle use. The host stores `{id}` plus exactly what it is handed, so a dropped key is GONE from the file rather than emptied; any owned write heals an entry left by an older build. **Amended 2026-10-12 (round 7, R17a, lane-key-w1 2ccbb74): `opts.keep`, an array of retired key names, carries THOSE over on any write, heal included, and anything but an array keeps nothing extra; the funnel passes `Model.retiredInputsToKeep`'s answer on every owned write, so a retired key is dropped only when it is consumed. "Any owned write heals an entry left by an older build" still holds, because that build's URL is adopted -- a record then holds it -- before the write.** **Amended 2026-10-12 (round 10, R20c): the service no longer passes `keepRetired`; the patch-only write hands `keep` the answer of `patchInputsToKeep`, and `keepRetired` stays for a caller that means "every one".** **Amended 2026-10-13 (round 11, R21b): the service hands `keep` the answer of `Model.retiredInputsToKeep` on EVERY owned write, the patch-only one included; patchInputsToKeep is withdrawn. Once the migration marker has landed that answer is empty, so every owned write strips the retired keys.** |
| `retiredInputsToKeep(entry, state, consumed)` | R17a (lane-key-w1; `Model.retiredInputsToKeep`): the retired keys an owned write must leave on the entry, a NEW array on every call. `playlistUrl` is kept unless a record holds it -- compared the way adoption compares: sanitized, validated as a CLI value, normalized, then looked up over every record -- or it equals `consumed.playlistUrl`; `epgUrl` is kept unless the ACTIVE record holds it (validated as an EPG URL; with no active record nothing holds it) or it equals `consumed.epgUrl`; an empty value is never kept; a retired key the function does not know is kept whenever it is non-empty. `consumed` is the service's two snapshots (`reconciledPlaylistUrl`, `reconciledEpgUrl`), which move only for a value reconcile adopted or refused -- the snapshot clause, lane A's reading of the ruling (round-7 rulings below). Fixture section `retiredKeep`, 20 cases. **Amended 2026-10-12 (round 8, R18a, lane-key-x1 1f8bd1b): the ENTRY value goes through `Model.entryInputForm` before any comparison, the snapshot clause and the held clauses alike. Round 7 compared it raw against a snapshot `Model.settingsFrom` had trimmed, so a value with surrounding whitespace -- which `omarchy bar set` stores as typed -- never matched its own snapshot (the seventh review's P1-A). "An empty value" now means an empty form: whitespace or control characters alone. The snapshot clause is confirmed (OQ-W1, R18d). 28 fixture cases.** **Amended 2026-10-12 (round 9, R19b): a guide URL equal to the state's `pendingEpg` is HELD, as one on the active record is. Lane A's mutation removing that clause reddens nothing (m8), argued equivalent: every non-empty fresh input is consumed when reconcile sees it, so the snapshot clause already covers any value the state holds; kept because R19b names it.** **Amended 2026-10-12 (round 10, R20c): asked on every owned write EXCEPT the patch-only one, which asks `patchInputsToKeep` over the LANDED state instead (the row below).** **Overturned in part 2026-10-13 (round 11, R21a/R21b; lane-key-m1 15896f1): the signature is `retiredInputsToKeep(entry, landed)` -- `landed` is `Model.entryMigratedOf` over `Service.landedState` -- and the answer no longer depends on records, snapshots or validation: every retired key the entry carries while `landed` is not `true`, none once it is, a NEW array either way. A caller that does not know answers false and keeps them, which is the write that cannot lose a record. The fixture section `retiredKeep` is rewritten for the two phases. Lane A's mutants: keeps after the marker 86 red; the keep decided off memory's marker 3.** |
| `patchInputsToKeep(entry, landed, consumed)` |**WITHDRAWN 2026-10-13 (round 11, R21d): no longer exported, no caller; the row is kept as round 9 and 10 wrote it, its names cited without the prefix.**  R20c (round 10, lane-key-z1 5b21950; `patchInputsToKeep`): the retired keys the PATCH-ONLY write (`Service.setShowLogos` under `Model.ownedWriteMode`'s `patch`) may carry back from the published entry, a NEW array. A value that is no input is not kept. A REFUSED value is kept only while the service's own snapshot (`consumed`) does not hold it -- before the first state load nothing has been reconciled, so its report is not lost with it -- and stripped once reported. A valid value is kept unless the LANDED state holds it: `landed` is `Service.landedState`, the state the last LANDED save serialised (`lastSaveState`, promoted when `stateFile`'s `saved` reports that text) or the file as it was loaded, never memory, because memory is what a failed write was carrying and the disk is what survives. The landed state holds a value when its consumed slot carries the value's digest (it was consumed and that consumption is on disk, so whatever it became is durable), when a record has that playlist URL, or, for the guide URL, when the ACTIVE record has it or it is the pending one. With no landed state at all (`landed` null, before the first load) every valid value is kept, R16's answer. Lane A's mutants on the tip (of 2,319): keep every one 3, decide from memory not disk 4 (exactly the two round-4 harness cases, `R20c (... host) round-4 P1` and `round 6's C1`), strip every valid one 13, no slot clause 1, a reported refused value kept 1. |
| `adoptPendingEpg(state, key, epgInput, lastEpg, nowSec, opts)` |**WITHDRAWN 2026-10-13 (round 11, R21d): no longer exported, no caller; the row is kept as round 9 and 10 wrote it, its names cited without the prefix.**  R17b (lane-key-w1; `adoptPendingEpg`): `{ state, pending, consumed, adopted }` -- whether a FRESH EPG input (`Model.reconcileAction`'s `adoptEpg` against the snapshot) lands on record `key` as if it were already active, through `Model.adoptActiveSource`. The state returned differs from `state` only in that record's `epgUrl`, and no key moves. `consumed` has R4's meaning (adopted, already held, or refused by validation) and is what `epgSnapshotAfter` moves the snapshot on; a key naming no record consumes nothing, so the input stays pending (R12). Called by `Service.adoptPendingEpgOnto` from `switchSource` and the probe commit. **Amended 2026-10-12 (round 8, R18d, lane-key-x1 1f8bd1b): `opts.formEpg` is the guide URL an in-app ADD's form carried, typed or derived by an Xtream add; a non-empty one (by its form) marks the pending input `superseded` -- also `consumed`, so the snapshot moves onto it and the commit's own mirror write strips it -- and adopts nothing, the record keeping the form's value. An empty `formEpg` supersedes nothing. The result gains `superseded`.** **Overturned in part 2026-10-12 (round 9, R19c, lane-key-y1 690a888): the signature is now `adoptPendingEpg(state, key, epgInput, lastEpg, nowMs)` -- `opts.formEpg` and the form-wins rule are GONE. A fresh input still on the entry is first held as reconcile would hold it, seen at `nowMs`; then the held value meets record `key` through `applyPendingEpg`: it lands iff its `seenAt` is LATER than the record's `epgSetAt` (absent = 0), otherwise the record keeps its own, and either way it is cleared. The result is `{ state, pending, consumed, refused, adopted, superseded, cleared }`; `superseded` now means the record's own, LATER, guide URL won.** |
| `pendingEpgRecord(raw)`, `pendingEpgOf(st)`, `withPendingEpg(st, rec)` |**WITHDRAWN 2026-10-13 (round 11, R21d): no longer exported, no caller; the row is kept as round 9 and 10 wrote it, its names cited without the prefix.**  R19b (round 9, lane-key-y1 690a888; `pendingEpgRecord`, `pendingEpgOf`, `withPendingEpg`): the held guide URL (section 2.1). `pendingEpgRecord` normalizes a raw value to `{ url, seenAt }` or null (the URL validated as a CLI EPG value; `seenAt` a non-negative integer of ms); `pendingEpgOf` reads the state's; `withPendingEpg` sets it, or clears it with `null`, and returns the SAME state object when nothing changes, so a caller's "did the state move" stays an identity test, as `Model.withActiveKey`'s does **Amended 2026-10-12 (round 10, R20a): `url` must BE a string, as the helper's `normalize_pending_epg` requires (shared fixture, `pendingEpg with a url that is not a string is no pending value (never str() of a list)`; lane A's mutant Z17, `str()` put back, reddens 1).** |
| `entryInputDigest(name, value)`, `entryInputRecord(raw)`, `entryInputsRecord(raw)`, `entryInputsOf(st)`, `withEntryInputs(st, slots)` |**WITHDRAWN 2026-10-13 (round 11, R21d): no longer exported, no caller; the row is kept as round 9 and 10 wrote it, its names cited without the prefix.**  R20b (round 10, lane-key-z1 5b21950; `entryInputDigest`, `entryInputRecord`, `entryInputsRecord`, `entryInputsOf`, `withEntryInputs`): the consumed-input slots (section 2.1). `entryInputDigest` is `""` for a value that is no input (`Model.entryInputForm`'s text empty), else 16 hex digits over the setting name and the value's one form. `entryInputRecord` validates one slot (null unless the digest is 16 lowercase hex digits; `at` coerced and clamped; `stripped` only when it is the boolean `true`); `entryInputsRecord` the whole key over `RETIRED_SETTINGS`, null when no slot survives; `entryInputsOf` the slots or `{}`; `withEntryInputs` returns the SAME object when nothing changes, `withPendingEpg`'s contract, so a caller's "did the state move" stays an identity test. Shared fixture with the helper's `normalize_entry_input(s)`: `entryInputs kept slot by slot, stripped only when true`, `... drops a slot whose digest is not 16 lowercase hex digits, and an unknown slot`, `... with no valid slot is absent`, `... stripped must be the boolean true`. |
| `entryInputSeed(st, name, value)`, `entryInputsAfterMove(st, name, before, after, nowMs)`, `entryInputsAfterWrite(st, entry)` |**WITHDRAWN 2026-10-13 (round 11, R21d): no longer exported, no caller; the row is kept as round 9 and 10 wrote it, its names cited without the prefix.**  R20b (round 10; `entryInputSeed`, `entryInputsAfterMove`, `entryInputsAfterWrite`): how the slots move. `entryInputSeed` is the snapshot a FIRST reconcile starts from -- the entry's own value when its slot carries that digest and is not stripped, `""` (every value fresh, the pre-round-10 start) otherwise; `Service.reconcile` seeds `reconciledPlaylistUrl` / `reconciledEpgUrl` from it when `reconciled` is false. `entryInputsAfterMove` sets a slot when a snapshot moves to a value, removes it when the input goes away, and changes nothing when no form changes; the service calls it at the end of every reconcile and where `Service.adoptPendingEpgOnto` moves the EPG snapshot. `entryInputsAfterWrite` marks `stripped` every slot whose value the entry an owned write just handed over no longer carries, and clears the mark on one it carries again; `Service.writeOwnedEntry` calls it after every hand-over. Lane A's one-decision mutants on the tip (node, of 2,319 checks): no seed 4, no slot move 5, no stripped mark 1, the seed ignoring `stripped` 1, `Model.cloneState` dropping the key 5. |
| `epgSetAtOf(rec)`, `epgByTime(st, key, url, setAt)`, `applyPendingEpg(st, key)` |**WITHDRAWN 2026-10-13 (round 11, R21d): no longer exported, no caller; the row is kept as round 9 and 10 wrote it, its names cited without the prefix.**  R19c (round 9; `epgSetAtOf`, `epgByTime`, `applyPendingEpg`): THE ONE COMPARISON. `epgSetAtOf` is a record's `epgSetAt` as a number, 0 for absent or junk. `epgByTime` lands `url`, set at `setAt`, on record `key` iff `setAt` is LATER than the record's own -- an EQUAL time is not later -- answering `{ state, won }`, the same state when it loses or names no record; the S5 `known` branch of the probe commit uses it for the add form's guide URL (OQ-X3 ruled). `applyPendingEpg` meets the held value with record `key` through it and clears the held value either way: `{ state, applied, superseded, cleared }`; nothing held, or no such record, moves nothing |
| `activeEpgUrlOf(record, input, pending)` | R19 / a12 (round 9; `Model.activeEpgUrlOf`): `Service.activeEpgUrl`'s decision, lifted so node calls it (rule 12; the eighth review's a12 mutation reverted the inline read and nothing went red). Beside a record: the record's guide URL, unless the input is SOMETHING that does not validate, which is returned as it is so the helper reports it (D16); an input of whitespace or control characters alone is no input and the record's value stands (R18a; D-SRC-17). With no record: the input on the entry when there is one (it is about to be held), else the held `pendingEpg` URL, else `""` **Amended 2026-10-13 (round 11, R21): `activeEpgUrlOf(record)`, the record's own guide URL and nothing else -- the entry input and the held value are no fallback any more (`R21: activeEpgUrlOf is the record's own guide URL ...`; mutant M11, the input fallback restored: 1 red).** |
| `owedMirrorAction({ owed, pendingKey, savePending, savesInFlight, saveFailed })` | R19d (round 9; `Model.owedMirrorAction`): `rewrite` or `none`. A held key mirror DROPPED because its state save failed (`Model.entryFlushDisposition`, `save-failed`) leaves a debt (`Service.entryMirrorOwed`); the first save to LAND with no key held, no save parked, none in flight and none failed pays it with one key mirror through the funnel, deferred by `Qt.callLater` from the FileView's `saved`, for the key active then. A heal clears the debt itself, because it strips everything consumed. D-SRC-18 is what this settles |
| `entryInputText(value)`, `entryInputForm(name, value)`, `sameEntryInput(name, a, b)` | R18a (round 8, lane-key-x1; `Model.entryInputText`, `Model.entryInputForm`, `Model.sameEntryInput`): THE ONE NORMALISER for a value read from the bar entry's two input keys. `Model.entryInputText` is `Model.settingsFrom`'s own trim, named (every `\s` at either edge). `Model.entryInputForm` is that, then `sanitizeInput` (control characters out, the cap), then validation as a CLI value of kind `name` (`epgUrl` validates as an EPG URL), and answers `{ text, ok, url, form }`: `form` is the validated URL when it passes and the sanitized text when it does not, so a refused value is one value whatever its spacing; `text` "" means NO input. Two values are the same input exactly when their forms are equal. Every comparison of an entry value -- against a snapshot, a record or another entry value -- goes through it: `Model.settingsFrom`, `Model.reconcileAction`, `Model.adoptActiveSource`, `Model.retiredInputsToKeep`, `adoptPendingEpg`'s `formEpg`, and `Service.activeEpgUrl`'s "the input does not validate" read. Nothing here is a URL the caller did not already hold **Amended 2026-10-13 (round 11): kept (R21d keeps R18a's normaliser); its callers are now `Model.settingsFrom`, `Model.reconcileAction`, `Model.adoptActiveSource`, `Model.entryInputSeen`, `Model.entryInputLast` and `Model.entryInputsSeenAfter`; adoptPendingEpg's `formEpg` and `Service.activeEpgUrl`'s input read are withdrawn.** |
| `entryWriteNeeded(id, entry, published, lastWrite)`, `entryWriteRecord(id, entry, published)`, `hostEntryForm(id, entry)` | R18b (round 8, lane-key-x1; entryWriteNeeded, entryWriteRecord, hostEntryForm, all three now deleted): would handing `entry` to `updateEntryInline` change what the host STORES? `hostEntryForm` is the object the host compares, `{ id }` then the entry's other keys in order; the host's answer is `JSON.stringify` of it against the stored entry (`shell.qml` `updateEntryInline`, 1094 for a layout entry, 1107 for a plugins entry). The stored entry is estimated: while the publish is still exactly the one that stood when this service last wrote (`lastWrite.published`), it is what that write handed over (`lastWrite.stored`); once the publish moves -- our own echo or anybody's write -- it is the publish. So a write this declines is one the host would have answered `false` to, and the estimate never waits for an echo (rule 9). `entryWriteRecord` is what the funnel records after every write it makes (`Service.lastEntryWrite`); deliberately RAW JSON, not normalised, because it mirrors the host's own byte comparison and a write that strips a whitespace-only value changes bytes **RETIRED 2026-10-12 (round 9, R19a): no shipped caller.** The funnel no longer skips a write on this estimate (the round-9 rulings below say why); `updateEntryInline`'s own answer is the dirty check. The three stay declared only because this table and three other documents cite them by name and the ledger resolves each citation against the model; the round-9 text cites them without the prefix for that reason, and deleting them is a code change that must reword these citations in the same commit. **DELETED 2026-10-13 (round 12, R22e; lane-key-n1 dab2b56): all three are gone from model/settings.mjs and from `Model.mjs`, pinned absent (`R22e: hostEntryForm, entryWriteRecord and entryWriteNeeded are gone ...`); cited bare everywhere from this round.** **Last citations removed 2026-10-13 (round 13, R23i; lane-key-p2): the three prefixed names that stood at the head of this row were the last citations the ledger's three R22e withdrawn-symbol waivers covered, and they went bare in the same commit that deleted those waivers from `scripts/check-defect-ledger.py`, because an unused waiver is red (R22d). The ledger now lists 0 withdrawn-symbol waivers, so a new `Model.`-prefixed citation of any of the three, in any document, is red as an unresolved name.** |
| `sameOwnWrite(a, b)` | R18b (round 8, lane-key-x1; `Model.sameOwnWrite`): the own-write record the funnel would assign against the one in force -- equal when both are absent, or when `base` and `value` carry the same keys with strictly equal values (`undefined` is not `""`). That is exactly what `Model.ownWriteInForce` and `Model.settingsWithOwnWrite` read, so an equal record is one no binding can tell apart and reassigning it is the re-trigger and nothing else; the funnel reassigns `ownWrite` only when this answers false **Round 9 (R19a): now the ONE clause that settles the cycle -- with the skip gone, an owned write the host answers `false` to re-triggers nothing because the record is not reassigned. Lane A's mutation m2 shows it is no longer load-bearing for the loop (no LOOP with it removed, because R19b took away the loop's precondition, an EPG input that stayed fresh on the entry forever); it is kept and pinned (m2 reddens 4 checks).** |
| `entryMigratedOf(st)`, `withEntryMigrated(st)` | R21a (round 11, lane-key-m1 15896f1; `Model.entryMigratedOf`, `Model.withEntryMigrated`): the migration marker (section 2.1). `Model.entryMigratedOf` is true exactly when `st.entryMigrated === true`; `Model.withEntryMigrated` returns the state with it set, the SAME object when it already is, so a caller's "did the state move" stays an identity test. Mutants M10 (`parseState` reads a truthy marker) 5 red, P1/P2 in the helper (drops it; reads it truthily) 3 and 1 red in `tests/test_state.py` |
| `entryInputSeen(seen, name, value)`, `entryInputLast(seen, name, value)`, `entryInputsSeenAfter(seen, values)`, `MAX_SEEN_INPUTS` | R21b (round 11; `Model.entryInputSeen`, `Model.entryInputLast`, `Model.entryInputsSeenAfter`, `Model.MAX_SEEN_INPUTS`): the session's in-memory, ORDERED record of every value it has migrated or refused off the entry, by setting, each as its one form (`Model.entryInputForm`). `Model.entryInputSeen` asks "seen at all" (after the marker: report once); `Model.entryInputLast` asks "the most recent one" (inside the migration window: R1's snapshot); `Model.entryInputsSeenAfter` moves every non-empty value to the end of its list, a NEW object when anything moves and the SAME object otherwise, at most `Model.MAX_SEEN_INPUTS` (32) values a setting, the oldest dropped -- a value that old reports once more if it comes back, never an adoption. Nothing here is persisted: the persisted snapshot of round 10 (R20b) is what it replaces. Mutant M3, `entryInputSeen` never true: 49 red; M16, freshness by membership instead of the last value: 3 |
| `entryInputNotice(name, reason)` | R21b / R21c (round 11; `Model.entryInputNotice`): THE ONE REPORT of a value taken off the bar entry without being adopted, `{ title, body }`, composed from the setting's NAME and the reason (`retired`, `no-source`, `invalid`) and never from the value (rule 5); a name that is not one of the two retired settings reads `A URL setting`. The texts are in the round-11 rulings at the end of this file and in `UX-SOURCES.md` 5. `Model.notifyArgv`'s `entryInputRefused` event renders the same sentence with replace id 74016; `Service.reportEntryInput` also logs it to the console. Mutants M7, no notification: 48 red; M13, any name passed through: 1 **Round 17 (R27d) added the reason `full` (`Sources is full`), and round 18 (R28b, 2026-10-20) changed its body, because the guide URL beside the held playlist is now held with it: `The playlist set on the bar, and its guide URL if one is set, were not moved into Sources: Sources already holds 50 sources, the most it can. Remove one in the guide's Sources screen and the bar's playlist and its guide move in together.` On that path no `Bar setting removed` card is sent any more, so nothing on 74016 is replaced by it in the same turn (round 1's review saw the two share the id)** **Round 19, 2026-10-20 (R29e): the `full` body now ends `; the bar's playlist then becomes the active source.` (round 2's live review: a source picked meanwhile is not the active one after "Remove one"). R29d added the reason `invalid-pair`, `Bar setting removed`, one sentence for an unusable playlist AND the guide URL set beside it, both removed: from the playlist's side `playlistUrl in the bar settings was not a usable URL and was removed, with the epgUrl beside it. Add or edit sources in the guide's Sources screen.`; from the guide URL's, when the playlist was told about before, `epgUrl in the bar settings came with a playlistUrl that was not a usable URL, and was removed with it. Add or edit sources in the guide's Sources screen.` The setting names are composed from `RETIRED_SETTINGS`, never written beside a verb, so `tests/test_shipped_copy.py` reads the same rule here as everywhere** |
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
  `Service.lastPersistFailure` used to keep the last code "for the harness";
  it was REMOVED on 2026-10-24 (D-SRC-67, P23 lane A's second finding,
  removed by lane A2): set at the three
  failure sites and cleared by D-SRC-43, read by nothing -- not the guide,
  not the model, not the IPC summary, and by the harness only in the one
  check written to the D-SRC-43 row's words. The reason travels as the
  signal's argument and nowhere else; a node check pins that no shipped
  source names the property.
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
the reason's own sentence [round 13, R23f: through `Model.refusalMessage(reason,
stateWriteBlocked, "persist")`, which is that outside the no-write mode and
the `state_unreadable` sentence inside it] -- on the form's result line while a form is open
and in the footer otherwise; until then the guide rendered `persist_failed`'s
copy for every code, so a failed write in `~/.local/state` sent the user to
`omarchy bar set` (lane A's DQ-T1, the round-4 review's P2). Pinned by two
node checks, both red over an export of lane-key-t2: the routing read off
`Guide.qml` (the reason handed through, the message composed on both
surfaces, never `persist_failed`'s sentence by name) and the copy for every
reason `Service.qml` emits (derived from the service source; none names a
URL and only `persist_failed`'s names `omarchy bar set`, the fallback for an
unknown reason). The rendered line is UNVERIFIED on a display: no scenario
reads it [round 7, OQ-C3: the TEXT the guide binds is OBSERVED -- the
round-5 live lens read `Model.persistFailureMessage` of `state_write_failed`
through the harness as the footer's transient and as the add form's result
line on lane-key-u3, no URL and no `omarchy bar set` in either; the pixels
stay UNVERIFIED]. `persist_failed`'s sentence is still shown for one thing, through
the toggle's return value rather than the signal: a LOGO write the host
refuses outright, where `omarchy bar set` is sound advice because that write
carries no credential (DQ-U5). Asynchronous outcomes
(fetch errors) arrive through `sourceProbeFinished` with the helper's codes
(`network`, `http_403`, `not_a_playlist`, `timeout`, ...).

| Action | Behaviour |
|---|---|
| `addSource({ playlistUrl, epgUrl, label, origin })` | sanitize -> validate both URLs -> duplicate check (`findSourceByUrl`) -> cap check -> `Model.addSource` -> `saveState()` -> probe (section 4.6). Returns `ok` with the new key as soon as the probe starts. `origin` defaults to `"guide"`. **[Round 7, 2026-10-12 (R17b): the probe commit that makes the new record active lands a pending EPG input on it before the save and before the mirror, so the first source added in the app takes a guide URL set while none was active -- REPLACING the form's own EPG field when the two differ (lane A's OQ-W3, open). Observed in node only (driver case E4 under both host shapes); no live segment adds a source in the app with an EPG pending.]** **[Round 8, 2026-10-12 (R18d, OQ-W3 ruled; lane-key-x1): the form's guide URL WINS. The probe commit of an ADD whose own record is kept hands the form's `epgUrl` -- typed, or the `xmltv.php` an Xtream add derived -- to `Service.adoptPendingEpgOnto`, and a non-empty one supersedes the pending CLI value: the record keeps the form's value, the pending value is stripped by the commit's own mirror write, and the service logs `the guide URL in the add form supersedes a pending input (epgUrl); the bar entry drops it`, the key name only. A blank form EPG adopts the pending value as R17b did. In S5's `known` branch (the CLI added the same playlist while the probe ran) the commit keeps the CLI's record, which does not carry the form's EPG, so nothing is handed and the pending value is adopted (lane A's OQ-X3, open). Observed live now: key-scenario A1 (no form EPG) and A2 (a form EPG), through the harness `addSource` verb with two saved sources and none active; red A2 on `--baseline lane-key-w2`.]** **[Round 9, 2026-10-12 (R19c, lane-key-y1): R18d's form-wins rule is OVERTURNED. `addSource` stamps the form's guide URL with the SUBMIT time (`Date.now()`, handed to `Model.addSource`) and the probe commit hands `Service.adoptPendingEpgOnto` nothing but the key: at the commit the LATER of the held CLI value and the form's guide URL wins, so a CLI `epgUrl` set while the probe runs beats the form (live Q1) and one set before the submit loses to it (Q2, and A2 as re-read). The S5 `known` branch is ruled (OQ-X3): the form's guide URL lands on the kept CLI record through `epgByTime` iff it was set later than what that record holds, and a held value is then judged against the result. Log lines name the setting and the source key, never a URL: `a pending guide URL (epgUrl) lands on source <key>` or `... is superseded: source <key> keeps the one set later`.]** **[Round 11, 2026-10-13 (R21; lane-key-m1): the three bracketed rulings above are OVERTURNED -- R17b and R18d by R21d, R19c by R21c and R21d. There is no pending guide URL for a commit to land, no set time and no supersede: the probe commit keeps the form's guide URL as the record's and hands nothing else on (`Service.adoptPendingEpgOnto` deleted). A CLI `epgUrl` set while the probe runs is REFUSED once the migration marker has landed, and the form's guide URL lands with the record and survives a restart (`R21e (lag host)` / `(echo host) the add form's race ...`; key-scenario Q, moved to the new contract). S5's `known` branch can no longer arise from a CLI value after the migration: a URL on the entry is not adopted.]** |
| `updateSource(key, { label, playlistUrl, epgUrl })` | label only: state + save. `epgUrl`: validate, record update (since D-SINK-19 the record is the only store of a guide URL, so nothing is persisted to the entry for it). `playlistUrl` changed: `Model.updateSource` creates the replacement record, then a probe with `replaceKey`; on success the old record is removed, its cache removed, and the switch committed if the old one was active; on failure nothing else changes and the replacement record is dropped again. **[Round 9, 2026-10-12 (R19c): the guide URL an edit CHANGES is stamped now (`Date.now()`; `Model.updateSource` stamps only a change), so a guide URL typed into the edit form while an older CLI value is held is the later input and stands at the switch (live V1; the eighth review's P2, which R18d's sibling search had cleared because there is no add form). The IPC `updateSource` routes through the same call.]** |
| `removeSource(key)` | `busy` if that key is probing. Removes the record, saves, queues `cache remove`, and if it was active `persistActive("")` (S7: back to the first-run state; playback, if any, continues). Since D-SINK-19 the state write is what clears the active source (`Model.removeSource` clears the pointer, R3); the entry mirror can still fail and is reported, but a stale mirror naming a removed record resolves to no active source. **[Corrected 2026-10-12: "cannot be refused" was an absolute the code did not support -- `FileView` has a `saveFailed` signal and round 2 connected to nothing, so an unwritable state directory refused the write silently while the entry mirror still went out. Since R11 (lane-key-s1) the service reads `saved` / `saveFailed`, counts writes in flight, and an entry mirror that WAITED for a parked save is written only once that save has landed; a remove or switch made with the directories already ready still writes the entry straight after `setText` (DQ-A2, the ungated sibling, listed as open). The failure path -- an unwritable state directory -- is UNVERIFIED live: no scenario makes the directory unwritable.]** **[Round 4, 2026-10-12 (R13): the sibling is closed -- the entry waits for the state write to land on the dirsReady route too (`Model.pointerWritePlan`'s `write-entry-after-saved`), and a refused mirror is logged, never reported as the removal failing: the call reports `ok` on the state write being ISSUED (SR25 as amended), and that write's failure arrives later as `sourcesPersistFailed("state_write_failed")`. The failure path is OBSERVED under a running shell: key-scenario F1-F7 on lane-key-t2 (the state directory 0500 with the dirs ready, a CLI set and then a switch: URL still on the entry, file untouched, the failure signalled once, the next start re-adopting; F3-F7 red on `--baseline lane-key-s2`). Unwritable at START stays unobserved, and F drives no remove on the failed disk (lane B).]** **[Round 7, 2026-10-12 (R17): removing the ACTIVE record adopts nothing -- with no active record a pending `epgUrl` stays on the entry (R12), and since R17a the mirror's write that follows the remove keeps it there, because no active record holds it; the first source to become active afterwards takes it (driver case E2 under both host shapes, lane-key-w1).]** **[Round 9, 2026-10-12 (R19b): with no active record a CLI `epgUrl` set after the remove is HELD in the state as `pendingEpg` and taken off the entry by the R13-gated write that follows its save, no longer kept on the entry; the first source to become active afterwards meets it by time (R19c). E2 is re-read for `held` (`R17 (... host) E2 (R19b)`).]** |
| `switchSource(key)` | no-op `ok` when already active; never-fetched (`fetchedAt === 0`) -> probe with commit; else section 4.5. **[2026-10-12, round 4 (R13): reports `ok` on the state write being issued -- the state write IS the switch; a later `saveFailed` arrives as `sourcesPersistFailed("state_write_failed")`; a refused mirror is logged (`no writable bar entry for the settings change`) and repaired on the next start, never `persist_failed`. `sources-scenario.sh`'s SR25 block moved to this contract on lane-key-t2: 66 / 0 under cage (lane B, 2026-10-12).]** **[Round 7, 2026-10-12 (R17b): a pending EPG input -- set while no source was active and still on the entry -- lands on the record becoming active in the same turn, after `Model.touchSource` and before `saveState` and `persistActive` (`Service.adoptPendingEpgOnto`); a never-fetched switch reaches the same through the probe commit. Observed live: key-scenario U3 on the lagging fake host and U6 on the echoing one (lane A's transcripts on lane-key-w1, 71 / 0; U3 and U6 red on `--baseline lane-key-v2`).]** |
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
before, every owned key at its effective value, the retired keys dropped
[round 7: the CONSUMED retired keys dropped, R17a; the amendment below].
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
(lane A's OQ-V1, the lead's to confirm [round 7: confirmed, R17c]). (2) The patch-only write carries
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
**Amended 2026-10-12 (round 7, R17, lane-key-w1 2ccbb74, lane A; the sixth
review, two lenses over lane-key-v2).** The funnel decides which retired
keys survive, for every caller. `writeOwnedEntry` asks
`Model.retiredInputsToKeep` over the published entry, `userState` and the
two snapshots (`reconciledPlaylistUrl`, `reconciledEpgUrl`) on every owned
write and passes the answer to `Model.entryWith` as `keep`, beside
`keepRetired`: a retired key leaves the entry only when it is consumed -- a
record holds it (any record for the playlist, the ACTIVE record for the
EPG) or the service already adopted or refused that value -- and a heal
that keeps one logs the key names, never a value. So "on `heal` ... the
retired keys dropped" above now reads "the CONSUMED retired keys dropped",
for the logo toggle's heal and the key mirror alike. The state the
paragraphs above could not name was R12's own: an `epgUrl` left on the entry
on purpose while no source is active, which the toggle's heal stripped on
the lagging host and the mirror's heal after a switch or an in-app first add
stripped on the echoing host, the value then existing nowhere (the sixth
review's P1). The other half is in the actions: `switchSource` and the
probe commit land a pending EPG input on the record becoming active before
the save and the mirror (`adoptPendingEpg`; the rows above). Every
pin, mutation and count is under the round-7 rulings below.
**Amended 2026-10-12 (round 8, R18, lane-key-x1 1f8bd1b, lane A; the
seventh review, two lenses over lane-key-w2).** The funnel now declines a
write that changes nothing, and that is what lets the cycle settle. After
composing the entry, `writeOwnedEntry` asks `entryWriteNeeded` with
its own record of its last write (`lastEntryWrite`); when the host would
answer `false` it returns success without calling `updateEntryInline`,
without logging the keep warning, and without touching `ownWrite`. When it
does write, it records `entryWriteRecord` and reassigns `ownWrite`
only when `Model.sameOwnWrite` says the record differs from the one in
force. Before this, a no-op write still REASSIGNED `ownWrite`, `settings`
re-evaluated, `onSettingsChanged` ran reconcile, and reconcile asked for
the same write from the lagging host's stale publish -- every event-loop
turn (the seventh review's P1-B). And the keep decision compares the entry
value through `Model.entryInputForm`, so a whitespace-wrapped value is
consumed when its trimmed self is (P1-A). The fixed points, path by path,
are under the round-8 rulings below.
**Amended 2026-10-12 (round 9, R19, lane-key-y1 690a888, lane A; the eighth
review, two lenses over lane-key-x2).** The skip in the paragraph above is
OVERTURNED (R19a), not rewritten: `writeOwnedEntry` hands EVERY owned write
to `updateEntryInline` and takes the host's answer as the dirty check,
`false` from a writable entry being "already stored" and success (rule 9).
The skip estimated the stored entry from `lastEntryWrite` while the publish
equalled the one recorded at the last write, and on the lagging host a
publish that goes A -> B -> A (an `omarchy bar set` that restores the
earlier entry exactly) brought that record back, so writes the host would
have stored were skipped: an in-app logo OFF, the strip of a re-set refused
credential, the strip of a re-set guide URL. `lastEntryWrite` is gone. The
own-write record is still reassigned only when `Model.sameOwnWrite` says it
differs, and that alone settles the cycle. The keep warning moved back in
front of the hand-over. When the host answers `false` the funnel returns
before re-arming the D-SINK-18 shield, because nothing was written. A heal
also clears `Service.entryMirrorOwed` (R19d, below). And the input the
paragraph about R12 above describes no longer waits on the entry: with no
active source a guide URL is held in `state.json` (R19b), so it is CONSUMED
and the heal that follows its save strips it. Every pin and count is under
the round-9 rulings below.
**Amended 2026-10-12 (round 10, R20c and R20b, lane-key-z1 5b21950, lane A;
the ninth review, two lenses over lane-key-y2).** The patch-only write no
longer carries every retired key the host publishes. It keeps one only when
it is a valid input the LAST LANDED state does not hold
(`patchInputsToKeep` over `Service.landedState`, the state the last
landed save serialised or the file as loaded) and strips the rest: a value
a record, the held guide URL or a consumed slot in that state already
holds, and a refused value already reported. On the lagging host that is
what D-SINK-20 was: the publish one write behind still carried a URL our
own heal had stripped, the toggle wrote it back, and -- the round-9
data-loss lens's re-grade -- a REFUSED credential that no record holds came
back too and stayed in `shell.json` for the session, because no owned write
follows once the failure clears; R19d's sibling search had cleared this
writer because "the next heal pays it", and in that sequence no heal
comes. The narrowing D-SINK-20's record calls WRONG, "keep the retired keys
only while no own-write override is in force", stays wrong, and the
difference is what each decides FROM: the override is the HOST's state and
says nothing about whether the value is stored anywhere else, so it
stripped the only copy of an input whose state write had failed; this asks
the plugin's own DISK, and strips a value only when the file, as last
confirmed written, already holds it -- which is exactly not the round-4
P1's case. And after EVERY owned write the funnel marks a consumed slot
whose value the handed-over entry no longer carries as stripped
(`entryInputsAfterWrite`, R20b), riding the next save. Every pin and
count is under the round-10 rulings below.
**Amended 2026-10-13 (round 11, R21; lane-key-m1 15896f1, lane A).** The
keep decision is no longer about consumption at all. `writeOwnedEntry` asks
`Model.retiredInputsToKeep(published, Model.entryMigratedOf(landedState))`
on every owned write, heal and patch alike, and hands the answer to
`Model.entryWith` as `keep`: every retired key the entry carries while the
migration marker has not landed, none once it has. The two round-7 snapshots,
the R19b held guide URL, R20b's slot marking after each write and R20c's
landed-state patch rule are **WITHDRAWN 2026-10-13 (round 11, R21d)**, and the paragraphs above that
describe them stand as the record of rounds 7-10. What the plugin does with
a value found on the entry after the marker is not this funnel's question:
`reconcile` refuses and reports it (R21b) and `stripEntryInputs` asks for
the patch-only write that takes it off, which the empty keep makes a strip.
D-SINK-20's re-carry cannot happen after the marker, because the patch-only
toggle keeps nothing; before it, it keeps the migration's input, which is
the round-4 P1's protection and what R21a asks for.
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
   (a CLI `state ...` write with nothing of ours outstanding [round 12, R22f's
   search: that write never arrives -- the FileView raises no reload on the
   helper's atomic rename, D-SRC-19 -- so `apply` for a newer file is reached
   by a write in place, such as an editor's or key-scenario B7's restore]
   [round 14, 2026-10-14: the bracket before this one is withdrawn. A
   helper rename IS reloaded (R23g's spike, every sequence), and the one
   session that saw nothing -- the state directory absent at the first
   load, the first session after a fresh install -- is re-armed by R24c;
   key-scenario B16 sees a hand-run `state source add` there. And R24a
   narrows the ignore list: a held save ignores a reload only when its text
   is the BASE (`Service.landedState`, `Model.sameState`); any other text is
   FOREIGN and is merged (`merge`, reasons `foreign-save-parked`,
   `foreign-save-in-flight`, `foreign-save-failed`), never ignored]
   [round 15, 2026-10-14, R25a (D-SRC-30): and `own-write` is narrowed to
   a text STILL IN FLIGHT -- `Service.recentSaves` is the burst asked for
   since the last save that landed, cleared when one lands -- so a copy of
   an earlier own save put back later is another writer's and is applied or
   merged like any other; with nothing held, a reload equal to the base over
   a memory equal to the base is ignored as `unchanged`]). An ignored
   reload runs neither `reconcile` nor `startCacheLayout`; the count is
   `stateReloadsIgnored` and, since R15, `stateReloadsByReason` -- one number
   per reason, which is what key-scenario D3 reads (`save-parked`). Step 1's `state init` exit also records
   `stateInitOk` and, after issuing the parked save, settles the held entry
   mirror (R11, the persistActive amendment in 4.3).]** **[Amended
   2026-10-13, D-SINK-19 round 12 (R22a; lane-key-n1 16a3bc9): step 2 is
   `stateFile.onLoaded` AND `onLoadFailed` -> `stateLoadArrived` ->
   `Model.stateLoadKind`, and only a load that parses as a state reaches
   `applyUserState`. `onLoadFailed` used to call `applyUserState("")`, so a
   file that could not be read was applied as an EMPTY state, migrated,
   marked and written over the real one (the round-11 data-loss lens's
   P1). A FileNotFound is a fresh install only when step 1's `state init`
   reports `found: absent`, which is why step 1's exit now also records the
   init's verdict and decides a held load (`Model.stateInitFound`,
   `Model.stateLoadDecision`); any other failure gets one re-read after the
   init and then the no-write mode. The FileView measurement and the rest
   are in the round-12 rulings.]** **[Amended 2026-10-24, D-REL-8 (P23,
   lane A): an init that answered NOTHING READABLE -- `unknown`: exit 0 with
   no `state init` line (the empty stub git leaves for milliseconds
   mid-update) or a non-zero exit (a partial stub, the old stub refusing new
   parts) -- is run ONCE MORE, a second later, under the start-up watchdog
   again (`stateLoadDecision`'s `reinit` act, `initRetried`,
   `stateInitRetry`); a second `unknown` takes the re-read-then-block path
   above. A timed-out init is never re-run (R23c).]**
3. `reconcile()` (also from `onPlaylistUrlChanged`, `onEpgUrlChanged`):
   `Model.reconcileSources(userState, playlistUrl, epgUrl, activeSourceKey, now)`;
   on `changed` assign `userState`, `saveState()`; for each `evicted` key
   queue `cache remove` [round 17, R27d: nothing is evicted any more and the
   loop is deleted]; set `settingsInvalid`. `activeSourceKey` is a
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
   **[Amended 2026-10-27, D-SRC-69: the prune is QUEUED here and its list
   is decided when it RUNS, at dirsReady at the earliest -- every record and
   the active key of that moment, plus the folder of a probe not yet handled
   (`Model.pruneArgs`). Until then the list was this step's, and an in-app
   add made between cacheReady and dirsReady lost its folder to the prune
   (mid-write the add was dropped; once committed, the added, active source
   showed 0 channels for the session). ARCHITECTURE.md section 8 item 17
   has the guarantee a probe in flight now has.]**

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
time (`busy`). **[Amended 2026-10-27, D-SRC-69: a probe asked for while a
cache job decided before it RUNS and could take its folder -- a prune that
does not keep it, a removal of that key (`Model.probeWaitsFor`) -- is held
until that job exits: `probing` is true and the helper starts at the job's
exit; the watchdog bounds the wait, and a cancel ends a held probe at once.
In the usual case nothing runs and the probe starts as before.]** Command: `Model.playlistProbeArgv(helperPath, sourceCacheDir(cacheDir, key))`,
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
  **[Amended 2026-10-27, D-SRC-71: the signal carries ONE object, as SR3
  has it, and Service.qml lists its fields beside the declaration: `{ ok,
  id, channelCount, groupCount, reason, host, cancelled, replacedId, code }`.
  A failure carries `code` -- the helper's error code through
  `Model.statusCode(status)`, `helper_timeout` when the probe's watchdog
  stopped it, or the plugin's own refusal at the commit (R28e:
  `too_many`, `state_unreadable`, `unknown_source`); a success and a cancel
  carry none. `host` is the record's (`Service.hostForRecord`), never a
  URL. The guide composes the line through `Model.probeFailureLine` ->
  `Model.failureFromHost`: a code on `PROBE_LOCAL_REFUSALS` (model/
  sources.mjs) reads the reason alone, any other `<reason> from <host>`,
  and a local file the reason alone whatever its code. Since D-SRC-73
  (the same day) `folder_unusable` is on that list and has its own
  sentence, and the `playlist` verb answers it for a cache folder that is
  a link to nothing, as every other verb that writes into the folder
  does (ARCHITECTURE.md section 8 item 17 names which verbs do and which
  answer otherwise).]**

### 4.7 Cache helper queue

One `cacheProc` `Process` plus a FIFO of `{ args, onDone }` (`migrate`,
`remove`, `prune`); the next job starts from `onExited`. Output is parsed
with `parseHelperStatus(text, "cache")`; failures are `console.warn`ed with
the code and action only. Nothing waits on the queue except `cacheReady`
(migrate). **[Amended 2026-10-27, D-SRC-69: what a job deletes is decided
when it runs (`Model.cacheJobArgs`, from `runNextCacheJob`), not when it
is queued. A prune is queued as `["prune"]` and built from the state, the
active key and the probe in flight of that moment; a `remove --key K` is
dropped when a probe is writing into K or started into K after the removal
was asked for (each job carries `sourceProbeSeq` at its queue, each key the
count of the last probe started into it), and a removal asked for by a
probe's own exit still runs (SR7, SR23). `migrate` and `epg-clear` run as
queued: neither deletes what a probe writes. The guarantee is stated in
ARCHITECTURE.md section 8 item 17 and the rule-15 search is recorded with
D-SRC-69 in QA-RESULTS.]** **[Amended 2026-10-27, D-SRC-70:
and a `remove --key K` is dropped when K is the ACTIVE key when it runs
(`Model.cacheJobDrop` answers "active"), so a cancel's removal no longer
takes the active source's own folder (SR7 as amended). Every deliberate
removal of a folder that was active is queued after the state that moves the
pointer off it is published: `removeSource` (the pointer cleared, R3) and the
commit of a URL edit of the active source, whose old folder's removal used to
be queued before the commit published the new key and is now queued after it.]**

### 4.8 IPC

`statusSummary()` gains `activeSource: { key, label, host } | null` and
`sources: Model.sourcesSummary(userState, activeSourceKey)`; no new verbs
(R9 keeps the surface minimal; switching from the command line is
`omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>`, which now also
records the source, S5). **[Round 11, 2026-10-13 (R21b): withdrawn. A URL set
that way is read once, by the migration of a 0.13.x install, and refused after
it; switching is the Sources screen, and the IPC surface still takes no URL
and gains no verb.]** `omarchy-shell io.github.rmcdavid.iptv status` stays
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

1. Clipboard and typed text are data. For a NAME field (the label, the
   Xtream username and password) `Model.sanitizeInput` strips
   `[\u0000-\u001f\u007f-\u009f]` (so a multi-line paste collapses to one
   line), trims, and caps (label 64; user and password 256). For a URL
   field (the playlist, the EPG, the Xtream server) `Model.sanitizeUrlInput`
   trims the six ASCII whitespace characters and NBSP off the ends, caps
   (URL 2,048; server 512), and deletes NOTHING inside: a control character
   or whitespace inside a URL is refused by `validateSourceUrl`, never
   deleted into a different URL (**D-SRC-63, R32a''', 2026-10-22**: a tab
   in a password became the password `pass`, and a two-line paste became
   one URL nobody typed), with the ONE stated exception of **R33a (round 7,
   2026-10-22)**: a PASTE into a URL field joins its lines first -- CR and
   LF removed, nothing else -- before that rule, because a URL wrapped by a
   mail client is a paste the form must take (`Model.sanitizePasteInput`,
   the guide's `pasteFromProcess`; a tab, U+0085 or U+2028 inside the paste
   still reaches the validator and is refused there, with the sentence that
   names it, R33b). So "a multi-line paste collapses to one line" is true
   again of a URL field's paste and false of nothing else: the submit path
   joins nothing (a value in the field cannot hold a line break). The Xtream
   username and password refuse a control character the same way since
   **D-SRC-65 (R33c)**, never delete it (`xtreamUrls`, codes `user_control`
   and `pass_control`). `Model.sanitizeFieldInput` picks the rule by
   field (3.1). `TextField.maximumLength` mirrors the caps so a 16 KB paste
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
   keeps an existing mode **[and, since 2026-10-24 (D-SRC-49, D-SINK-22
   windows b and c; P23 lane A), is made 0600 again by the helper's `state
   mode` after every save that LANDS, from `stateFile.onSaved` on its own
   bounded Process -- a file the user put at the path at 0644, or one a save
   created at the umask's mode after a re-point, is private within the
   stub's start rather than until the next shell start; one interpreter
   start per landed save, `ARCHITECTURE.md` section 5's 2026-10-24
   amendment]**); `sources/` and every `sources/<key>/` are 0700
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
   (`Model.entryShieldDecision`). SR40.]** **[Round 11, 2026-10-13: both routes
   still exist -- the host writes whatever `omarchy bar set` hands it -- but a
   URL the user sets that way now stays only until the plugin's next owned
   write strips it (R21b), so the shield guards a file a URL passes through,
   not one it rests in.]**
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
   sources; `cache prune` argv carries at most 50 keys. **[2026-10-27,
   D-SRC-69: at most 51 -- the 50 records and, during a URL edit at the
   cap, the new folder its probe writes into, which the prune now keeps.]**

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
| Guide open | unchanged < 150 ms | Sources rows derive from `userState.sources` in memory (<= 50 records); no file or helper access on open; the group column gains one row. **[2026-10-20, R27f: the budget itself is not met by a cold open in the cage, sources or not -- 546 ms list, 580 ms wall at 10,000 channels, about 450 ms of it the first show of the window -- and is met warm (34 / 32 ms); the round-17 rulings have the table]** **[2026-10-20, R28d: re-measured with an instrument that counts only what is DRAWN -- 548 ms list, 534 ms wall cold, 33 / 31 ms warm, about 440 ms of the cold figure the first show of the window whatever the channel count; the round-18 rulings have the table]** **[2026-10-20, R29e: drawn now also means painted above opacity 0 (each delegate's own times every ancestor's): 547 ms list, 547 ms wall cold, 34 / 32 ms warm; the round-19 rulings]** |
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
3. `omarchy bar set io.github.rmcdavid.iptv playlistUrl <us.m3u>` while the Sources screen is open: the row appears/activates without reopening. **[Round 11, 2026-10-13 (R21b): withdrawn as written. On an install whose migration has landed the command is REFUSED: no row appears, the active source does not change, one `Bar setting ignored` notification names the Sources screen, and the value is gone from `shell.json` after the plugin's next write. The live check is that, with `grep -c '://'` over the notification log and the journal reading 0.]**
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
| SR3 | Signals | `sourceProbeFinished({ok, id, channelCount, groupCount, reason, host})`, `sourcesChanged()`, `sourceSwitched(id)`, `sourceRemoved(id)`, `sourcesPersistFailed(reason)`. `reason` is already redacted. **[Amended 2026-10-27, D-SRC-71; the ruling's decision is unchanged: a FAILED `sourceProbeFinished` also carries `code`, which decides whether the guide's line names `host` (`Model.failureFromHost` over `PROBE_LOCAL_REFUSALS`: a failure on this machine reads the reason alone). The object has carried `cancelled` and `replacedId` since before this amendment (section 4.6 as amended lists the fields).]** |
| SR4 | Mask rule | Fixed token `****` (UX) replaces userinfo, the fragment, and every query value except the non-secret keys `type` and `output` (this document's exception); scheme, host, port, path, and query keys stay visible; local paths are never masked. Reveal is `Ctrl+R` or the eye button, re-masked on blur, save, cancel, and paste. |
| SR5 | Limits | This document's caps are canonical: playlist/EPG URL 2048, label 64, server 512, username/password 256, 50 sources. `Model.LIMITS` carries them and UX copy quotes them. |
| SR6 | Validation codes | The code list in UX-SOURCES.md 5.4 is canonical for user-facing errors; the shared JSON fixture (tests/fixtures/source-urls.json) uses those codes and both the JS validators and the Python mirror must pass it. |
| SR7 | Probe semantics | Add, playlist-URL edits, and switching to a never-fetched source probe into the source's own cache dir and commit only on success (D7/D8, S8). Label and EPG edits commit immediately. Cancel aborts the probe and discards the new cache dir. **[Amended 2026-10-27, D-SRC-70, the owner's decision; the ruling stands as written: "the new cache dir" is read as it says. A re-check of the ACTIVE source -- a never-fetched one, added again from the form, which the guide retries -- probes into the active source's own folder, which is not new, and its cancel no longer takes it: a `cache remove --key K` is dropped when K is the active key at the moment it runs (`Model.cacheJobDrop`), the way the prune always keeps that key (D-SRC-07). The discard of a new folder -- a cancelled add, a cancelled URL edit's replacement folder -- is unchanged, and so are the deliberate removals of a folder that was active, which are asked for after the pointer has moved (4.7).]** |
| SR8 | CLI parity | `omarchy bar set ... playlistUrl` reconciles into the history with a derived label and `origin: cli`; an invalid value synthesizes an error status and never runs the helper (D16). **OVERTURNED 2026-10-13 (round 11, R21; the owner's decision): CLI parity is withdrawn.** The adoption described here runs only as the one migration of a 0.13.x install's bar entry (R21a); after it a URL set with `omarchy bar set` is refused, reported once and removed (R21b), and a source is added or changed in the Sources screen only. |
| SR9 | Favorites and recents | Global, keyed by channel id, unchanged (D14). |
| SR10 | Lanes | Lane 1: `Model.js`, `Guide.qml`, `tests/Model.test.js`, `tests/Model.spec.qml`, `tests/fixtures/source-urls.json`. Lane 2: `Service.qml`, `bin/omarchy-iptv`, `tests/test_*.py`, `scripts/dev-harness/*`. Both build against the interface in this document; the product owner merges Lane 1 first. |

## Reconciliation rulings, round 2 (product owner, 2026-09-13, answering QA-SOURCES.md section 10)

| # | Answers | Ruling |
|---|---|---|
| SR11 | SRC-DEC-01 | `~` paths: the CLI path (`omarchy bar set`, origin `cli`) keeps accepting and expanding them (no regression from 0.1.0); the forms refuse them with the UX `relative_path` message. `validateSourceUrl(text, {kind, origin})` takes `origin` (`form` default, `cli`). The fixture pins both contexts. **Amended 2026-10-13 (round 11, R21):** the CLI context survives only for the migration -- a `~` path a 0.13.x install kept on its bar entry is still accepted and expanded when it is migrated; after the migration no `omarchy bar set` value is validated at all, because none is adopted. |
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

## Reconciliation rulings, round 4 (product owner, 2026-10-09, D-SINK-19; amended 2026-10-11 and eight times on 2026-10-12, after nine adversarial reviews)

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
the one state its three flags could not name, before the first state load;
and R17 followed the sixth review (round 7), for the input R12 leaves on
the entry on purpose, which any heal write stripped; and R18 followed the
seventh (round 8), for two P1s on the round-7 build -- a value with
surrounding whitespace that never counted as consumed, and a refused value
beside a pending guide URL that looped the lagging host; and R19 followed
the eighth (round 8), for R18's own write skip coming back after a publish
A -> B -> A and for a pending guide URL superseded by a form submitted
BEFORE it; and R20 followed the ninth (round 9's two lenses over
lane-key-y2), for the helper's own state writer erasing the held guide URL
(D-SRC-20), for the lagging host's patch-only logo write re-carrying a
refused credential that then beat a later edit at the next start (D-SINK-20,
re-graded P2), and for a funnel decision nothing observed by behaviour. The rows below now carry the 2026-10-09
ruling VERBATIM as lane-key-docs (55502af) recorded it -- the one copy that
predates both reviews -- and, where a review overturned part of it, dated
amendments beneath saying what the code on this tree does instead; nothing is
rewritten to read as though it always said this, and a reader comparing a row
against `git show lane-key-docs:docs/ARCHITECTURE-SOURCES.md` finds the
original as a prefix. D1, D3 and D4 above carry the same discipline. **[Round 11, 2026-10-13: the product owner withdrew the `omarchy bar set` URL route (R21, the last rulings in this file). SR37 is overturned, SR38 ends at a marker, SR39 cost 1 is replaced and SR40 reason (i) shortened, each by a dated amendment at the end of its row; R12, R17b, R18d, R19b, R19c, R20b and R20c are overturned and marked where they stand.]**

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
| SR37 | nothing; **extends SR8** | **CLI parity is preserved, and becomes input-only.** `omarchy bar set io.github.rmcdavid.iptv playlistUrl "<url>"` still adopts: the same `Model.validateSourceUrl` with `origin: "cli"`, reconciled into the history with a derived label and `origin: "cli"` (SR8, D3, SR11), an invalid value still synthesizing an error status and never running the helper (D16). `epgUrl` is treated the same way. SR8's sentence stands unchanged; this row only says what happens next. Once adopted, the plugin sets the active key and rewrites the entry with the key and without the URLs, so the value the user set is an INPUT and not a stored setting: set it, read the file back, and it is not there. That is SR39 cost 1, it is a documented behaviour rather than a bug, and the README says so at both places it shows the command. **Overturned in part 2026-10-11 (R1, R4), after the review found the first build DISCARDING the input on every first or forced reconcile:** "still adopts" holds for a URL this service has not consumed -- the first reconcile of a service (the shell start, which is where a value set while the shell was down arrives) and any value different from the one it last saw -- whether or not the reconcile was forced (`Model.reconcileAction`); a value equal to the last one adopted is the host's unechoed copy of the plugin's own strip (rule 9) and is not read again, else a state reload would resurrect a source the user had just removed. `epgUrl` likewise: a fresh non-empty value is attached to the ACTIVE record on any reconcile that sees it, an `ignore` plan included (D-SRC-02 stays closed), and stripped by the same owned write. The EMPTY value is a no-op for both keys: `omarchy bar set ... playlistUrl ""` and `... epgUrl ""` are WITHDRAWN as clear levers; the Sources screen and the helper's `state source` verbs clear. An invalid value is still D16 -- reported, never run -- but leaves a working source exactly as it was (`Model.invalidInputBlocks`), and is stripped from the entry too, because a refused value can still carry a credential. The README says all of this at both places it shows the command and in its settings table. **Amended 2026-10-12 (round 3, R12): an input is never stripped unadopted.** Round 2 stripped an `epgUrl` set while NO source was active in the same owned write that could not attach it, so the value was gone with no copy anywhere (review P2); it now stays on the entry until a source exists and a later reconcile attaches it to that source, and the service's EPG snapshot moves only for an input that reached a record (`epgSnapshotAfter` on lane-key-s1; the fixture case `R4/R12: an EPG input with no active source to land on is not adopted AND NOT STRIPPED` flipped from `writeEntry` true to false). One sentence round 2 wrote under this row's name is WITHDRAWN: "re-setting the SAME URL in one session after removing that source waits for the next shell start". The review's data-loss lens walked the shipping functions in the service's order on both host shapes (the one-write-behind host and the echoing one, omacom/omarchy#15082): the owned write that follows the remove strips the stale echo from the entry and moves the service's snapshot, so the re-set value differs from it and is adopted at once. The "not consumed" rule above stands; the cost attributed to it did not exist. **Amended 2026-10-12 (round 7, R17), after the sixth review's data-loss lens found R12 kept only by the callers that happened to know about it.** "Never stripped unadopted" was enforced nowhere: nothing records that an EPG input is waiting, so with the state loaded and nothing outstanding `Model.ownedWriteMode` answers `heal` and `Model.entryWith` dropped every retired key -- through the logo toggle on the lagging host (observed live on lane-key-v2 by the lens: LOST with the toggle, KEPT without), and through a switch or an in-app first add on the echoing host with no toggle at all, because `reconcile()` never runs on an active-key move and the mirror's heal stripped the entry before anything had attached the value. R17a moves R12 to the sink: an owned write strips a retired input only when it is CONSUMED (`Model.retiredInputsToKeep`, asked by the funnel on every owned write, heal and patch alike, and handed to `Model.entryWith` as `keep`). R17b: `switchSource` and the probe commit land a pending EPG input on the record becoming active in the same turn (`adoptPendingEpg`), before the save and before the mirror; `removeSource` of the active record leaves it pending. So "until a source exists and a later reconcile attaches it" now reads "until a source becomes active, by any route". Every pin and count is under the round-7 rulings below. **Amended 2026-10-12 (round 8, R18), after the seventh review found two P1s on the round-7 build.** Every value read from the entry is compared the way adoption compares it (`Model.entryInputForm`), so a URL pasted with a trailing space or newline -- which `omarchy bar set` stores as typed -- is consumed, refused or adopted exactly as its trimmed self, and a value of whitespace or control characters alone is no input; a write that changes nothing the host stores is not made, so a refused `playlistUrl` beside a pending guide URL settles instead of looping; and a guide URL the in-app add form carries wins over a pending CLI `epgUrl`, which is then superseded and stripped (R18d; with no guide URL in the form, the pending one is adopted as above). Every pin and count is under the round-8 rulings below. **Amended 2026-10-12 (round 9, R19), after the eighth review found R18's write skip coming back after a publish A -> B -> A and R18d superseding a CLI `epgUrl` set after the form was submitted.** Three readings above are overturned. "It now stays on the entry until a source exists" (R12) is replaced by R19b: with no active source a valid `epgUrl` is held in `state.json` as `pendingEpg`, and stripped from the entry by the same R13-gated owned write that strips every consumed input, so it is never stripped unadopted and never kept in `shell.json` while it waits; a refused one is reported and stripped as beside an active source. "A write that changes nothing the host stores is not made" is replaced by R19a: every owned write is handed to the host, whose answer is the dirty check, and the cycle settles because the own-write record is reassigned only when it differs. "A guide URL the in-app add form carries wins" is replaced by R19c: every record carries `epgSetAt`, set by the add form at submit, by the edit form, or by adoption, and at an active move the LATER of the held input and the record's own guide URL wins. Every pin and count is under the round-9 rulings below. **Amended 2026-10-12 (round 10, R20b), after the ninth review found an entry value re-adopted at a start as though it were new.** "Read when it arrives and at every shell start" now has a memory: `state.json` records, per input, a DIGEST of the value the service last consumed from the entry (`entryInputs`, section 2.1), so a value still on the entry that the state proves consumed and not stripped since -- left there by a failed write, or written back by the lagging host -- is not adopted again at the next start, seen now, over a later in-app edit. A value the plugin HAS stripped and the user then sets again while the shell is down is read as new, as before. Every pin and count is under the round-10 rulings below. **OVERTURNED 2026-10-13 by the product owner (D-SINK-19 drops the `omarchy bar set` URL route; R21, the round-11 rulings at the end of this file).** "CLI parity is preserved" no longer holds. `omarchy bar set ... playlistUrl` and `... epgUrl` are read ONCE per install, by the migration of a 0.13.x install's bar entry (R21a), and on an install whose migration has landed they are REFUSED: never adopted, whatever the value, reported once with a message naming the Sources screen (`Model.entryInputNotice`), and removed from `shell.json` by the plugin's next owned write (R21b). SR8's CLI adoption therefore survives only as the migration's mechanism. Every amendment above -- the "not consumed" reading, R12, R17, R18, R19 and R20b -- is the record of the route the owner withdrew; the sentences that describe a CLI input being held, timed, superseded or remembered across a restart describe nothing the tree does now. The in-app Sources form is the only way to add or change a source. | |
| SR38 | nothing | **The migration.** Section 2.2's fourth step. A bar entry with a URL and a state with no `activeKey` is the old shape: derive the key with `Model.sourceKey`, write `activeKey`, rewrite the entry with the key and without the URLs. Idempotent, and it must not lose a source -- it names a record that already exists, creating none and deleting none. The rewrite goes through `updateEntryInline`, so rule 9 governs it: the plugin applies its own write locally in the same turn and never waits for an echo it will not receive, `false` means "already stored" and never surfaces as an error (SR33), and `Model.ownedEntryPatch` must name EVERY key the plugin owns. Adding a key and removing two is a change to exactly the machinery D-LOGO-2 was filed against, which named only some owned keys and wrote stale values back. The migration is silent and needs nothing from the user -- deliberately, and that same invisibility is the whole reason SR39 cost 2 LOOKS like data loss, which is why the two are documented together and not as separate warnings. **Overturned in part 2026-10-11 (R1, R5, R7):** "creating none and deleting none" was false against the code. The migration IS the adopt path (`Model.adoptActiveSource` step 1 -> `Model.reconcileSources`): a URL the history knows makes that record active; one it does not know is ADDED (`migrated` on the very first v2 run, `cli` after), and at the 50 cap the least-recently-used non-active record is evicted with its cache, as any CLI adoption. "Must not lose a source" is therefore graded as "keeps the count it went in with" over a TWO-source state, one active and one not (node: `R7: the migration keeps the source count it went in with`, seen red by mutation; the harness half is lane B's). The two writes are ordered by `Model.pointerWritePlan` (R5): state first, entry waits for a parked state save, so an INTERRUPTED migration leaves the old shape and never a pointer-less record -- R5's claim, about the shell dying between the two writes; see the next amendment for the uninterrupted start. **Amended 2026-10-12 (D-SRC-15, round 3, R9-R11).** R5 ordered the two writes, and the UNinterrupted first start still lost the pointer on the round-2 tree: the helper's start-up `state init` chmodded the existing `state.json`, the service's `stateFile` FileView reloaded on that `IN_ATTRIB` (mode changed or not -- measured on a FileView probe, a chmod 0600 -> 0600 delivers `fileChanged` and a `loaded` with the file's text), `applyUserState` was handed the pre-adoption text while the adoption's save was still parked behind `dirsReady`, `Model.stateOnLoad` kept only the session record, and the parked save then wrote the key-less state while the entry flush stripped the URL with `sourceKey ""`. Found live by the harness lane on 2026-10-11 (key-scenario 32 / 12 on lane-key-r2, sources-scenario 46 / 22; 66 / 0 on dev) and reproduced by two review lenses; the D-SRC-15 row in `STATUS.md` and the section of that name in `QA-RESULTS.md` carry the measurement. So the migration this row describes is what the tree does ONLY with R9-R11 in it, and it is observed rather than argued: on lane-key-s2 (3c5e473, lane-key-s1's code under lane B's harness) `key-scenario.sh live` reads 49 passed / 0 failed, and 36 / 13 over `--baseline lane-key-r2` with D2, D3, M1, M3, M5, C1-C5, E1, O5 and O6 red -- everything that rests on an adoption made at start-up; `sources-scenario.sh` under cage reads 63 / 3, the three pinning the pre-round-2 contract (DQ-A4 / DQ-B7), not this. R9: a reload never replaces in-memory state that is newer than the file -- `Model.reloadDisposition` (lane-key-s1) is asked FIRST in `applyUserState` and answers `ignore` for the service's own write echoed back, a save parked, a save in flight (one `saved` per `setText`, measured, so it is a counter and not a flag) or a failed save, and `apply` for the first load and for a file that is genuinely newer; an ignored reload runs neither the reconcile nor the cache layout, and the count is `stateReloadsIgnored`, which the harness reads (D3: the file seeded 0644 so the chmod fires, `ignored:yes`). R10: the helper stats first and chmods only when the mode differs -- belt, not fix, because a same-mode chmod reloads too, and a 0644 file still gets the chmod and the reload R9 absorbs. R11: the entry mirror that waited for the parked save is written only once that save has LANDED (the FileView's `saved`, not `setText` returning) and the helper's `state init` exited 0; on either failure the entry is left exactly as it is -- the URL on it is the only copy of a source whose state write did not land -- and a line with no URL in it is logged (`Model.entryFlushDisposition`; the order in `stateInitProc`'s exit is pinned by a structural check that reads `Service.qml`). Two bounds on the claim. The created-file shape (no `state.json` at all) was written by one round-2 lens as dropping the same way and is MEASURED not to: a FileView loaded over a missing path never sees the helper's create, N1-N4 are green on the dropping tree and `stateReloadsIgnored` reads 0 across a fresh start, so the fresh install was never exposed and the existing-file shape -- every upgrade -- was. And the sibling the data-loss lens found is covered by the same flag rather than by a second mechanism: `cacheReady` is set before `dirsReady`, so an IPC switch or remove in that window parks a save, and the reload that follows is ignored; a scenario that drives it is nobody's yet. **Amended 2026-10-12 (round 4, R13-R15).** Two corrections to the amendment above and one closure. "One `saved` per `setText`" was measured for two back-to-back writes and does NOT hold for a burst (10 warm switches: 20 `setText`, 14 `saved` on lane-key-t1, 15 on lane-key-s2; a 26-write FileView probe: 25 `saved` + 1 `saveFailed`, `text()` tracking the write that STARTED -- lane A, 2026-10-12, under cage), so "in flight" is decided by content (`Model.stateSaveLanded`) and `stateSavesInFlight` is 0 or 1; the signal-counting version stuck above zero after a burst and, on lane-key-s2, read every later foreign reload as "save in flight" (lane A's DQ-T4: D-SRC-16, P2, a sibling of D-SRC-15 fixed on lane-key-t1 by the content rule and unreleased; cited by id since round 6, once the board row existed). The ignore counter is BY REASON (`stateReloadsByReason`, R15), because the plain total was satisfied by the own-write echo that follows every start and could not go red for the chmod reload D3 names (the round-3 review's P2). And the sibling "nobody's yet" is observed: key-scenario W1-W6 on lane-key-t2 (an IPC switch and then a remove inside the slow start-up window over a 0644 file; W2 and W6 red on `--baseline lane-key-r2`, W3/W6 reading NOFIELD on lane-key-s2 for the counter it lacks). Counts on lane-key-t2 (lane B's transcripts, 2026-10-12): 62 / 0 forward, 54 / 8 on `--baseline lane-key-s2`, 38 / 24 on `--baseline lane-key-r2`. **Amended 2026-10-13 (round 11, R21a; lane-key-m1).** The migration now ENDS: it writes the marker `entryMigrated` (section 2.1) in the same state write as the adoption, and the service reads the entry's URLs only while the LANDED state lacks it. Everything above about the order of the two writes, the parked save, the landing gate and the reload stands, and applies to that one migration. Observed live by key-scenario G1-G3 (the marker lands WITH the adoption, nothing is reported, the entry is stripped after the landing) and, for a migration whose write fails from the start, F and H through `fixtures/disk-gone-after-init.py` (the state directory loses `w` the moment `state init` has run, because init chmods it back to 0700 otherwise -- the first live run with the directory chmodded before the start was 88 / 10 for that reason). | |
| SR39 | nothing | **The three costs, accepted by the owner on 2026-10-09, each of which is documented in the README in plain language.** (1) `omarchy bar set ... playlistUrl` is input only: adopted, then replaced by the key, and the value is gone when the user looks again (SR37). (2) **Downgrading breaks the setup.** An older build looks for the URL on the bar entry, finds none, and reports the plugin as not configured. Nothing is lost -- the sources are still in `state.json`, and the recovery path already exists in the older build: an unconfigured guide opens the first-run form (`Model.openFirstRun`), which carries the `Saved sources (n)` link row into the Sources screen, which is scenario 3.1.6 in `UX-SOURCES.md` and the transition at its line 261. That it is the OLD build's own affordance is what makes the recovery possible at all, and it is read off the shipped code and the UX spec rather than exercised, because this lane holds no display -- but it LOOKS like data loss, and it looks like data loss precisely because the migration was invisible. The release notes and the README say so plainly; softening it is how a user with a working install comes to believe the update ate it. (3) **Losing `state.json` becomes fatal to the source list.** Today the URL in `shell.json` is an accidental backup: wipe the state file and `Model.reconcileSources` re-adopts the URL and rebuilds the record (D3). After this there is nothing to rebuild from and the key is one-way. This is the cost the owner was asked about by name and accepted; it is not softened anywhere, and the README does not tell the user to copy the file around without also saying that the copy carries their provider credentials. **Amended 2026-10-11:** the round trip back up is a MIXED shape (section 2.2 as amended): the older build leaves `sourceKey` on the entry and writes the newly picked `playlistUrl` beside it, and `Model.adoptActiveSource` step 1 resolves that to the URL, so the source picked while downgraded is the one that comes back -- the first build put the stale mirror first and silently reverted the user's choice. Derived from both builds' code; the live round trip is UNVERIFIED. Cost (3) stands exactly as written above: the only change round 2 made to it is tense -- the URL in `shell.json` WAS the accidental backup -- and that is not a second cost (trimmed 2026-10-12 after the round-3 review found it stated twice). **Amended 2026-10-13 (round 11, R21; the owner's decision).** Cost (1) is REPLACED. `omarchy bar set ... playlistUrl` is no longer an input at all once the migration has landed: it is refused, reported (`Bar setting ignored`, naming the Sources screen) and removed, and the README says so where it used to show the command. Cost (2) stands, with one consequence spelled out: 0.13.6 drops the migration marker, so a re-upgrade migrates again over the URL 0.13.6 put on the entry, and the source picked while downgraded is the one that comes back (key-scenario G4-G5, with the real v0.13.6 helper). Cost (3) stands exactly as written. | |
| SR40 | nothing | **The mode shield stays, and so does the gate in front of a persist.** After this change the plugin's own persists carry a key and no URL, so `Model.persistCarriesSecret` answers "no secret" on every ordinary path and the gate stops firing there. That is the change working, not the gate becoming dead code, and it is not a reason to delete either half. Four reasons, in order of how much they cost if ignored: (i) `omarchy bar set` is still a write of a URL into that file, made by the HOST on the user's instruction, which the plugin cannot gate at all -- the shield is the only thing that tightens the container around a write the plugin does not make; (ii) an install upgrading into this release still has a URL in `shell.json` until the migration's rewrite lands, and the shield runs on the startup path unconditionally, which is D-SINK-18 residual 3 and F-M3-16's lesson that the artifact needs the fix as much as the derivation does; (iii) the key is still a confirmation oracle (SR36), so a private container is still worth having; (iv) a predicate that answers correctly for a write nobody makes today is how the next feature that does write one gets gated by construction instead of by somebody remembering rule 5. The precise post-change behaviour of that predicate and of the deferred-persist slot is the code lane's and is **UNVERIFIED BY ME**: read it off `Model.js` and `Service.qml`. **Settled 2026-10-11:** the gate's question is asked of the ENTRY about to be written -- `Model.entryShieldDecision` over `Model.ownedEntryPatch` -- which answers `persist` for every shipping write (no URL-bearing key is owned) and `refuse` or `defer` the moment a URL-bearing key is written again, whoever writes it; the deferred slot holds `{ sourceKey }`. The guide's `config_unsafe` sentence (`Settings file could not be made private`, with the chmod) is therefore unreachable from any write this version makes, and the README says so rather than documenting a message nobody can see. The shield's re-arm after every owned write and its unconditional startup run are unchanged. **Amended 2026-10-13 (round 11, R21b).** Reason (i) stands with a shorter tail: the host still writes whatever `omarchy bar set` hands it, the plugin cannot gate that, and the shield is still the only thing that tightens the container around it; what changes is that the URL no longer stays -- the next owned write strips it whatever it is. Reasons (ii)-(iv) stand. **Amended 2026-10-22 (D-DOC-23, the #14748 review).** Reason (i)'s "the only thing that tightens the container" is narrowed to the `omarchy bar set` write ITSELF: that write lands through the shell's FileView writer, which keeps whatever mode it finds, and nothing but the shield tightens the file around it. The host's own `omarchy bar defaults` and the other `omarchy bar` layout commands rewrite the same file 0600 through `omarchy-shell-config commit()` (`mktemp` then `mv`; measured 0644 -> 0600 under umask 022 and 077) -- a literal second tightener, `omarchy bar position` included, which rewrites a file still holding a URL `omarchy bar set` put there -- but not around that write, and nobody is directed to rely on them. No decision in this row changes. | |

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

**[Round 11, 2026-10-13: R12 is OVERTURNED by R21c -- a guide URL on the entry at the migration with no source to guide is reported and stripped, never held -- and R9-R11 stand for the one migration (R21a). The text below is unchanged.]**

Issued after the second adversarial review (three lenses over lane-key-r2 and
lane-key-r3, 2026-10-11) found D-SRC-15 live and reproduced it twice. Each
names where it landed on lane-key-s1 (3d2d8e7, lane A) and lane-key-s2
(3c5e473, lane B, the harness).
R9: a file reload NEVER replaces in-memory state that is newer than the file
-- `Model.reloadDisposition` (`apply` | `ignore`, with the reason), fixture section
`reload` (10 cases), asked first in `Service.applyUserState`; while a save is
parked (`stateSavePending`) or in flight (`stateSavesInFlight`, a counter: one
`saved` per `setText`, measured [round 8, the OQ-C5 sibling: since R13 it is
0 or 1, set when a write is asked for and cleared by CONTENT through
`Model.stateSaveLanded`, so a flag that keeps a counter's name]) or the last save failed, the reload is
ignored [round 14, R24a: only when its text is the base the service last
knew on disk; a FOREIGN text in that window is three-way merged by
`Model.mergeForeignState`, because "ignored" let a hand-run helper write be
written over by the next save that landed (D-SRC-22)] and runs neither `reconcile(true)` nor `startCacheLayout`; the sibling
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
`Service.qml`, so swapping the two lines reddens. [Round 11: R12 OVERTURNED by R21c.] R12: an input is never
stripped unadopted -- an `epgUrl` set with no active source stays on the entry
until a source exists and adopts it (`epgSnapshotAfter`, fixture section
`snapshot`, 5 cases; the adopt case `R4/R12` flipped from `writeEntry` true to
false) [round 9: the on-entry half is OVERTURNED by R19b -- with no active
source a valid input is held in `state.json` as `pendingEpg` and taken off
the entry by the same R13-gated write; "never stripped unadopted" stands,
because the copy in the state is written before the strip; the round-9
rulings below]. Also ruled and landed: the two older empty-state strings in
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

**[Round 11, 2026-10-13: R13 is NARROWED to the migration by R21a -- the entry waits for the state write to land, and until the migration marker has landed with it every owned write keeps the retired keys; after that every owned write strips them (R21b). R14 and R15 stand. The text below is unchanged.]**

Issued after the third adversarial review (three lenses over lane-key-s2 and
lane-key-s3, 2026-10-12) graded lane A's own open question DQ-A2 as a P1 and
measured it live: with the directories READY, `persistActive` wrote the entry
straight after `setText` and before the FileView reported, so a state write
that failed then (an unwritable `~/.local/state`, a full disk) had already
stripped the URL from the host's file -- the record existed in memory only
and the input had no copy anywhere. R11 had gated the parked route only.
Each ruling names where it landed on lane-key-t1 (bb06540, lane A) and
lane-key-t2 (712329c and f54f408, lane B, the harness).
[Round 11: R13 narrowed to the migration, R21a.] R13: the entry mirror is written only after the state write it depends on
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

**[Round 11, 2026-10-13: R16, as amended in round 6, stands for the migration window and is NARROWED by R21a/R21b: the patch-only write still writes `showLogos` alone while a state write is outstanding or before the first load, but which retired keys it carries is `Model.retiredInputsToKeep` over the landed marker -- all of them before it, none after. The text below is unchanged.]**

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

[Round 11: R16 narrowed by R21a/R21b.] R16. An owned-entry write that is NOT the key mirror writes only the fields
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
input should answer is the lead's (lane A's OQ-V1) [round 7: confirmed as
landed, fail safe, R17c]: over this tree the
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
absent-input answer (OQ-V1, the lead) [round 7: confirmed, R17c];
`qa_field`, `qa_guide_field` and the
other folds in `shell.qml` (recorded by name, above); `Model.js` over the
marketplace scanner's 512 KiB per-file limit (D-REL-5; 572,623 bytes on
lane-key-v1, the split script re-run over this file at integration); the
pre-load, parked and in-flight toggles observed in node and not live; and,
unchanged, the state directory unwritable at START, a remove on a failed
disk, a `saved` for an EARLIER write arriving while a later one is pending
and then fails, a CLI `state ...` write inside a parked or in-flight shell
save, and the echoing host (modelled, D-HOST-4) [round 7: `run.sh --host
echo` makes the fake host echo, and key-scenario U5-U7 run on it; the other
own-write scenarios have not run both ways yet, which is D-HOST-4's second
half] [round 8: K2 and K3 run on it too, the loop window on the echoing
host].

### D-SINK-19 round 7 rulings (lead, 2026-10-12; R17, on top of R1-R16, which stand)

**[Round 11, 2026-10-13: R17b is OVERTURNED (R21d: there is no pending guide URL for an active move to adopt; adoptPendingEpg and `Service.adoptPendingEpgOnto` are deleted). R17a's sink rule is NARROWED by R21a: what an owned write keeps is decided by the migration marker, not by consumption. R17c stands. The text below is unchanged; its withdrawn names are cited without the prefix.]**

Issued after the sixth adversarial review (two lenses over lane-key-v2
2c50b41, 2026-10-12). The live-instrument lens read the chain mergeable.
The data-loss lens found one P1, older than round 6 and present on every
D-SINK-19 tree it drove (lane-key-t2, lane-key-u3 and lane-key-v2 each lose
the same 6 cases in its driver). R12 keeps an `epgUrl` the user sets while
NO source is active on the bar entry, because nothing can consume it, and
the README promised it stays there until the first source exists and is
attached to that one then. The plugin recorded that state nowhere: with the
state loaded and nothing outstanding `Model.ownedWriteMode` answers `heal`,
and `Model.entryWith` dropped the input because it is in
`Model.RETIRED_SETTINGS`, so the value was then on no record and off the
entry. Two routes. The logo toggle on today's lagging host, observed live by
the lens on lane-key-v2 with its own driver under a nested cage (LOST with
the toggle, KEPT without). And a `switchSource` or an in-app first add on
the echoing host (omacom/omarchy#15082) with no toggle at all, measured in
the lens's simulator: the key mirror's heal stripped the entry before any
reconcile had seen an active record beside the input, because `reconcile()`
runs from `applyUserState`, `onSettingsChanged` and `onShellChanged` and
never on an active-key move; on the lagging host the stale publish happened
to rescue it, which is exactly what rule 9 says a write must never depend
on. Five rounds of matrices missed it because their oracle checked PLAYLIST
inputs only: with an EPG oracle (the lens's L17) added and nothing else
changed, the EPG scenarios read 2,327 losses in 7,084 runs on lane-key-v2.
Code and harness landed on lane-key-w1 (2ccbb74, lane A, on top of c2218f0,
a conflict-free merge of `dev` at ab545f4; 0590e88 the harness README's
counts; 9d82724 the input audit widened to every setting the entry
carries); the documents on lane-key-w2 (lane C).

[Round 11: R17a narrowed to the migration marker, R21a.] R17a, THE SINK. An owned write strips a retired input from the entry only
when it is CONSUMED. One Model decision,
`Model.retiredInputsToKeep(entry, state, consumed)`, names the retired keys
to keep: `playlistUrl` when it is non-empty and no record holds it, compared
the way adoption compares (sanitized, validated as a CLI value, normalized,
then looked up over every record); `epgUrl` when it is non-empty and the
ACTIVE record does not hold it, no active record included. The funnel,
`writeOwnedEntry`, asks it over the published entry, the in-memory state and
the service's two snapshots on EVERY owned write, heal and patch alike, and
hands the answer to `Model.entryWith` as `keep`; a heal write that keeps
something logs `the bar entry keeps an input no source has adopted yet
(<key names>)`, names only and never a value. This is R12 moved from the
callers to the sink -- the shape R13 and R16 each had to learn twice -- so no
current or future writer can strip an unadopted input. A retired key the
decision does not know is kept whenever it is non-empty, so a key added to
`Model.RETIRED_SETTINGS` later fails safe.

The snapshot clause is a reading of R17a that goes past its literal text,
and it is lane A's, for the lead to rule (lane A's OQ-W1) [round 8:
confirmed, R18d; and compared through the one normaliser, R18a]: a value equal to
the service's own snapshot of what it already consumed
(`reconciledPlaylistUrl`, `reconciledEpgUrl`) is strippable too, although no
record holds it now. The ruling says "only when a record holds that value".
On the lagging host the published entry still carries a URL our own heal
stripped, and once its record is gone the bare rule carries it back: a CLI
playlist adopted and then its source removed is re-adopted at the next start
-- a removed source resurrected -- and a CLI EPG adopted onto A followed by
a switch to B lands A's guide URL on B (D-SRC-10's shape). Measured by lane
A on lane-key-w1: with the clause removed, the driver cases X1 and X2 go red
under the lagging host (3 red with the fixture), and the review's matrix
over that mutation reads 1,060 problems (1,032 of them L15, a removed source
resurrected) against 21 with it. The same clause decides refused values
(lane A's OQ-W2): a value that failed validation is consumed -- reported
(D16) and moved into the snapshot by reconcile -- and is stripped as before,
because a refused value can still carry a credential (rule 5); the
service-order driver's input audit counts such writes apart, and reads none
[round 8: confirmed, R18d -- and "reads none" was the gap: no driver case
carried a refused value at all, and a refused value wrapped in whitespace
was NOT stripped, the seventh review's P1-A; the audit now reaches refused
values and wants them reached, R18c].

[Round 11: R17b OVERTURNED, R21d.] R17b, THE ACTIVE MOVE ADOPTS. `switchSource` and the probe commit (the
in-app add, a URL edit, the never-fetched switch, and `retrySource` through
both) consume a pending EPG input onto the record becoming active in the
SAME turn, through `Service.adoptPendingEpgOnto` and
`adoptPendingEpg`, which asks the two decisions reconcile asks
(`Model.reconcileAction` for "fresh against the snapshot",
`Model.adoptActiveSource` for validation and the record): after
`Model.touchSource`, before `saveState`, and before `persistActive` writes the
mirror; the EPG snapshot moves only through `epgSnapshotAfter`. Never
by waiting for a host publish to trigger a reconcile (rule 9). The probe
commit adopts only when it makes a DIFFERENT record active; an inactive edit
or a retry of the active source leaves a pending input where it is.
`removeSource` of the active record does not adopt: with no active record
the input stays pending (R12), and R17a keeps it on the entry through the
mirror's write that follows the remove. A pending input REPLACES a guide URL
the record already had, as reconcile's adoption always has (R4) -- including
the EPG field of an in-app add's own form when the two differ, which is lane
A's OQ-W3 and open [round 8: ruled the other way, R18d -- the form's guide
URL wins and the pending value is superseded] [round 9: both readings are
OVERTURNED -- the pending input waits in the state, not on the entry (R19b),
and at the move the LATER of it and the record's own guide URL wins, by
time (R19c); the round-9 rulings below].

R17c. OQ-V1 is confirmed: an absent `stateLoaded` means "not loaded", so
`Model.ownedWriteMode` answers `patch`. It fails safe: a caller that forgets
the input leaves a URL on the entry longer and never loses a record. The
round-6 sentences that left it to the lead are bracketed where they stand.

Pins that call the shipping code, on lane-key-w1 (lane A); `QA-SOURCES.md`
carries them as SRC-MIG-24 (the input and its live segment) and SRC-MIG-25
(the audit), and SRC-CLI-09 and SRC-MIG-22 as round-7 brackets. The decision's
fixture, section `retiredKeep` in `tests/fixtures/active-key.json`, 20
cases: the lead's whole cube (playlist and EPG x held and unheld x an
active record or none), the snapshot clause, refused values, whitespace
compared the way adoption compares [round 8: of the HELD clause only --
both whitespace cases had an empty snapshot, and the snapshot clause
compared the raw entry value, the seventh review's P1-A; 28 cases since
R18c], and no records at all; with a cube
check that every corner reads "kept exactly when unheld". `Model.entryWith`
with `keep`. `adoptPendingEpg` alone. Service-order driver cases under
both host shapes: E1, no active source, an EPG set while the shell was
down, the toggle, then a switch -- the EPG ends on the switched-to record;
E2, remove the active source, a CLI `epgUrl`, the toggle -- the EPG survives
the toggle and the restart and the first switch after lands it; E3, no
toggle, a switch; E4, the in-app first add with an EPG pending; X1 and X2
for the snapshot clause. Two structural pins: `R17a (structural): the
funnel asks Model.retiredInputsToKeep over the published entry, the
in-memory state and BOTH snapshots, and hands the answer to entryWith on
every owned write -- heal and patch alike, not behind a condition -- logging
key names only`, and `R17b (structural): switchSource and the probe commit
adopt a pending EPG before their saveState and before persistActive;
removeSource does not; ...`. And the rule-15 pin, which is this round's
lesson -- the data-loss instrument must have an oracle for EVERY input the
entry can carry, not for the one the last defect was about: the
service-order driver now AUDITS every owned entry write it makes, asserting
that no input value the stored entry carried before the write is absent
afterwards from both the entry and every record in the file, and that no
other user setting changes (`R17 / rule 15: the input audit ...`, 78
audited writes on lane-key-w1). That audit is the pin that would have
caught this in round 2: over lane-key-v2's code it reads 8 lost EPG writes
across E1-E4 under both hosts, among them the momentary strip in the
lagging host's E3 that the stale publish later rescued. Live, key-scenario
segment U (U1-U7), lifted from the lens's driver: U1-U4 the toggle and then
the switch on the lagging fake host, U5-U7 the switch alone on the echoing
one, through a new lever, `run.sh --host echo` -- D-HOST-4's first half: the
fake publishes `shellConfig.bar` at once with NO intermediate stale publish,
so it is not more forgiving than either real host (rule 10), and `ipc
hostEntry` reports which host ran.

Counts, each with where it was measured. Lane A on lane-key-w1: node 2,191
/ 0, 19 `ok   R17` lines (read again on lane-key-w2 by lane C: `2191
checks, 0 failure(s)`, 19); the same test files over c2218f0 (lane-key-v2's
code plus `dev`) 2,191 / 16 -- the R16 structural pin re-levelled to the new
`Model.entryWith` line, 4 R17 unit pins, the 8 E1-E4 driver cases (lag and echo),
the 2 R17 structural pins and the input audit -- the driver failing on the
loss itself (echo E1: the EPG on no record and off the entry, the audit
naming the heal write that lost it), and X1 and X2 green there because
lane-key-v2 strips unconditionally. One-decision mutations of the shipping
code, each reddening at least one check: the bare rule without the snapshot
clause 3; the EPG held by any record rather than the active one 2; the
playlist compared raw 1; `Model.entryWith` ignoring `keep` 6; `Model.entryWith`
dropping every other setting 10, the audit among them; the funnel handing
an empty `keep` 7; `keep` on the patch branch only 6; the switch not
adopting 5; the probe commit not adopting 3; the switch adopting after
`persistActive` 5; `adoptPendingEpg` ignoring the snapshot 2. The
harness: `qa-lib-test.sh` 443 / 0 (+2 pins for the `--host` lever, 441 / 2
against lane-key-v2's `run.sh` and `shell.qml`); key-scenario's floor 63 ->
70 lettered checks. Live, lane A's transcripts under the scenario's own
nested headless cage on 2ccbb74: forward 71 / 0
(`key-20261012-130320-2002054.out`, 83.7 s; U2 `logos:true writes:1 alone:0
epgUrl:yes kept:1 on:none`, U3 `ok:true on:<A> file:<A> stored:<A>
epgUrl:no`, U6 `on:<A> stored:<A> published:<A> epgUrl:no/no`); `--baseline
lane-key-v2` 66 / 5 (`key-20261012-130450-2008881.out`): U2 `epgUrl:no
kept:0`, U3 `on:none`, U4 and U7 a restart standing on A with no EPG, U6
`on:none` on the echoing host; U1 and U5 green as the controls, nothing
outside U moved. `sources-scenario.sh` 66 / 0 and `logo-scenario.sh live`
33 / 0 under a nested cage on the same tree. The sixth review's own
instruments, adapted by lane A to hand the new decision (each adaptation
gated on the tree having the symbol): the EPG proof 6 -> 0 losses; the EPG
subset of the matrix 7,084 runs, 2,327 -> 0 (L17); the full matrix 51,238
runs, 2,348 -> 21, the 21 being D-SINK-20's runs (the lens's own refuted
L12p cluster), with the playlist re-carry counters identical on both trees,
so R17a added no playlist re-carry. The gate 0 on every lane-key-w1 commit.

Also closed this round, the review's P3s. `scripts/qa-lib-test.sh` owns its
environment: the default-directory pin unsets `OMARCHY_IPTV_HARNESS_DIR`
itself, so a bare run with the variable exported reads 443 / 0 where the
old line read 442 / 1, and the gate's `env -u` stays as belt and braces.
The harness README's "nobody has measured" sentence carries the round-6
live lens's `--baseline lane-key-u3` 64 / 0. `OMARCHY-PLUGIN-CONTRACT.md`'s
FileView bullet says `Model.reloadDisposition` ignores a parked or in-flight
save by its FLAG, not its count (OQ-C5: in flight is 0 or 1 since R13 and
cleared by content). And the text the guide binds for a persist failure is
OBSERVED through the harness -- the round-5 live lens read
`Model.persistFailureMessage` of `state_write_failed` both as the footer's
transient and as the add form's result line, with its `guide-copy.sh` on
lane-key-u3 (no URL, no `omarchy bar set`, no fixture path in either) --
while the rendered pixels stay UNVERIFIED (OQ-C3; 4.3 above, `UX-SOURCES.md`
5.5, `QA-SOURCES.md` SRC-ERR-07).

What this round leaves open, with its owner: the snapshot clause and the
refused-value reading of R17a (OQ-W1, OQ-W2, the lead) [round 8: both
confirmed, R18d]; which EPG wins when
an in-app add's form carries its own while a CLI EPG is pending (OQ-W3, the
lead and UX) [round 8: ruled, R18d, the form's]; the unconfigured empty state's caption `Optional EPG: ...
(converted; not kept in shell.json)` (`Guide.qml` `unconfiguredEpg`, a line
of the unconfigured empty state), which is exactly the state in which R12 KEEPS
the value in `shell.json` until a source becomes active (`UX.md` 4.4,
`UX-SOURCES.md` 3.1.1; a copy decision for the Guide's owner, raised here
rather than resolved) [round 9: resolved by the code, R19b -- the value is
held in `state.json` and off the entry once that write lands, so the
caption is true]; the second half of D-HOST-4, the other own-write
scenarios (E6, the key-mirror segments, the L toggle) run both ways on the
echo lever; the in-app add with a pending EPG, observed in node (E4) and
not live [round 8: observed live, key-scenario A1 and A2, with two saved
sources and none active; the add into an EMPTY list stays node only]; D-SINK-20, unchanged (the full matrix's 21); `Model.js` at 580,454
bytes on lane-key-w1, over the marketplace scanner's 512 KiB per-file limit
(D-REL-5, the other workflow's split re-run over this file at integration);
and whether this P1 takes an id of its own -- it is recorded under
D-SINK-19, and the board is the lead's.

### D-SINK-19 round 8 rulings (lead, 2026-10-12; R18, on top of R1-R17, which stand)

**[Round 11, 2026-10-13: R18d is OVERTURNED (R21c, R21d: the in-app forms are the only inputs after the migration and they are sequential, so nothing supersedes anything). R18a's normaliser is KEPT; R18b's skip was already retired by R19a; R18c's quiescence check stands, but its service-order driver (the regex mirror of `Service.qml` in `tests/Model.test.js`) is deleted, its R13 sequences re-run on `Service.qml`'s own functions through `tests/service-harness.js`. The text below is unchanged.]**

Issued after the seventh adversarial review (two lenses over lane-key-w2
dea7e0c, 2026-10-12). The live-instrument lens read the chain mergeable. The
data-loss lens closed round 6's P1 -- on lane-key-w2 the R12 EPG input is
lost by no route, on either host shape or any failure plan, 0 losses in its
39,000-run matrix per host where c2218f0 reads 328 (echo) and 224 (lag) --
and found two P1s, each reproduced live under its own nested cage with a
driver of its own (`loop-child.sh`, `resurrect-child.sh`).

P1-A, introduced by round 7. `Model.retiredInputsToKeep`'s snapshot clause
compared the PUBLISHED entry's value raw against the service's snapshot, and
the snapshot comes from `Model.settingsFrom`, which trims. `omarchy bar set`
does not trim: the host's `/usr/share/omarchy/bin/omarchy-bar` hands the
value to `jq --arg` as typed. So a value with surrounding whitespace -- a
pasted URL with a trailing space or newline -- never counted as consumed,
and the clause round 7 added so that a stripped value could not come back
was dead for it. A refused value, which can carry a credential (rule 5),
stayed in `shell.json` and every heal wrote it back; a CLI playlist adopted
and then its source removed was carried back onto the stored entry by the
remove's own mirror write and re-adopted, active, at the next start
(observed live by the lens: `removed source X RESURRECTED`); and on the
echoing host a pending EPG beside such a value looped (18,941 entry writes
and 632 CPU ticks in 5 s, the lens's `loop-badwsepg-echo-t1.out`). With the
one-line trim the node suite read 2,191 / 0, exactly as without it: nothing
could see it, which was the review's P2.

P1-B, older: on the chain since before round 7, and absent from `dev`, which
carries no D-SINK-19 code. On the lagging host an EPG input left pending
(R12, no active source) beside a REFUSED `playlistUrl` looped. The heal
stripped the refused value from the STORED entry, but the host kept
publishing the pre-write entry, so every reconcile had `Model.adoptActiveSource`
answer `writeEntry` true from the stale copy; `adoptActive` queued
`Qt.callLater(persistActive)`; the write that followed was one the host
answered `false` to, nothing having changed -- and `writeOwnedEntry` still
REASSIGNED `ownWrite`, which re-evaluated `settings`, fired
`onSettingsChanged` and ran reconcile again, every event-loop turn. Live on
the lagging fake host: 15,003 entry writes and 549 CPU ticks in 5 s on
lane-key-w2 and 18,814 / 525 on c2218f0; 0 / 0 for each half alone and on
the echoing host (the lens). A user reaches it with an `omarchy bar set ...
epgUrl` while no source is active and a mistyped `playlistUrl` (an `ftp://`
URL, say). The credential token appeared 0 times in the harness log.

R18a, ONE NORMALISER. Every comparison of a value read from the bar entry --
against a snapshot, a record or another entry value -- goes through the one
normalisation adoption uses. `Model.entryInputText` is `Model.settingsFrom`'s
own trim, now named. `Model.entryInputForm(name, value)` is that, then
`Model.sanitizeInput` (control characters out, the cap), then validation as a CLI
value of that kind (`Model.validateSourceUrl`), and answers `{ text, ok, url, form }`: `form` is the
validated URL when it passes and the sanitized text when it does not, and
`text` "" means NO input. Two values are the same input exactly when their
forms are equal (`Model.sameEntryInput`). `Model.settingsFrom`,
`Model.reconcileAction` (fresh is "the forms differ", adopt only when the text
is non-empty), `Model.adoptActiveSource` (the playlist's text, the EPG's
whole form), `Model.retiredInputsToKeep` (the snapshot clause and the held
clauses alike) and `Service.activeEpgUrl`'s "the input does not validate"
read all compare through it. So "fresh" in reconcile and "consumed" at the
sink cannot disagree about a value, and a 34-case property asserts that they
do not, for every input kind and wrapping. Two behaviour changes follow, and
they are recorded here rather than left implied (lane A's OQ-X4): a re-set
that differs only in spacing, scheme or host case, the default port, or an
embedded control character is the SAME input -- not fresh, not re-adopted,
and stripped by the next heal; and a value of whitespace or control
characters alone is NO input everywhere, where round 7 kept it on the entry
for good and the next heal now strips it.

The search R18a asked for found a sibling (lane A's OQ-X1; it has no id,
because the board is the lead's and the ledger refuses an id with no row)
[round 9: the board now carries it as D-SRC-17, fixed on lane-key-x1 and
never shipped]:
an `epgUrl` of control characters alone (a BEL, `\u0007`) validated as the
EMPTY guide URL, and `Model.adoptActiveSource` replaced the active record's
guide URL with "" -- against R4, "an empty EPG input is a no-op". Lane A
confirmed it on lane-key-w2 (`{adoptEpg:true, consumed:true,
recordEpg:""}`; on lane-key-x1 `{adoptEpg:false, consumed:false}`, the
record's URL kept); routing the EPG through its form fixes it, and it is
pinned.

The comparisons R18a's search visited, in `Model.js` and `Service.qml`
(lane A's search, by shape: every read of `playlistUrl` / `epgUrl` off an
entry, an input or `settings`, and every `findBarEntry`, `barConfig`,
`inputEpgUrl` and snapshot read in the QML). NORMALISED: the keep decision's
snapshot clause (P1-A) and its held clauses; `Model.reconcileAction`'s
`playlistChanged` / `epgChanged` and its emptiness test; `Model.adoptActiveSource`'s
playlist text and EPG form; `adoptPendingEpg`, through those two, and
its `formEpg` emptiness; `Service.activeEpgUrl`; and `Service.reconcile` and
`adoptPendingEpgOnto`, which read `settings`, i.e. `Model.entryInputText`.
CLEARED, with the reason: `Model.adoptActiveSource`'s `writeEntry` emptiness
tests read trimmed `settings` values and must keep asking, because that
request is the heal for D-SINK-20's re-carried value (a no-op request is
then declined by R18b); the `sourceKey` comparison is `Model.activeKeyText` on
both sides; `Model.ownWriteInForce` and `Model.settingsWithOwnWrite` compare
owned keys only, both sides from `Model.settingsFrom`; `Model.ownWriteOf`
compares nothing; `Model.sameOwnWrite` is deliberately strict, because it
must equal what the bindings read; `entryWriteNeeded` is deliberately
RAW JSON, because it mirrors the host's own byte comparison and normalising
it would skip a write that changes bytes (stripping a whitespace-only value,
say); `Model.entryFlushDisposition` reads flags and a key, no entry value;
`epgSnapshotAfter` is an emptiness test on a trimmed value; the funnel's
raw `published` feeds only the keep decision (normalised), `Model.entryWith`
(a copy) and `entryWriteNeeded` (raw by design); `Service.pipConfig` only
clamps; `Model.sourceView` reads a record, not the entry; and `Guide.qml`
and `BarWidget.qml` read no entry value.

R18b, THE CYCLE SETTLES. [Round 9: decision (1) below, the write skip, is
OVERTURNED by R19a -- on the lagging host a publish A -> B -> A brought
`Service.lastEntryWrite` back and the funnel skipped writes the host would
have stored; decision (2), `Model.sameOwnWrite`, stands and alone settles
the cycle; OQ-X2 is moot. The text is kept as the round-8 ruling read.] A
write that changes nothing changes nothing. Two
decisions in the funnel, both in `Model.js` so the node driver calls what
`Service.qml` calls. (1) `entryWriteNeeded(id, entry, published,
lastWrite)` answers the host's own dirty check -- `JSON.stringify` of
`{ id }` plus the entry's other keys against the stored entry, key order
included (`/usr/share/omarchy/shell/shell.qml` `updateEntryInline`, the
comparison at 1094 for a layout entry and 1107 for a plugins entry, read on
this machine) -- against the stored entry as the plugin can know it: its own
last write (`Service.lastEntryWrite`, recorded by `entryWriteRecord`
after every write it makes) while the publish is still exactly the one that
stood when it was made, and the publish once it has moved (our own echo, or
anybody's write). A write it declines is one the host would have answered
`false` to, and the funnel returns success, which is what that `false`
means (rule 9). (2) `Model.sameOwnWrite(a, b)`: the funnel reassigns
`ownWrite` only when the record it would assign differs from the one in
force, by strict key and value equality over `base` and `value` -- exactly
what `Model.ownWriteInForce` and `Model.settingsWithOwnWrite` read, so an
equal record is one no binding can tell apart and reassigning it is the
re-trigger and nothing else. The keep warning moved after the skip, so a
write not made logs nothing. Neither half waits for an echo: the estimate
is the plugin's own record of its own write, dropped the moment the host
publishes anything else, so the code is the same under both hosts and the
echo path stays idempotent.

How lane A reads R18b's second clause, for the lead to confirm (lane A's
OQ-X2): "no decision asks for an entry write whose result equals the stored
entry" is implemented in the ONE funnel and not in
`Model.adoptActiveSource`. The reconcile/adopt decision still asks from the
stale published copy, and has to: the same `writeEntry` from a stale,
non-fresh `playlistUrl` is what heals a value D-SINK-20's patch-only write
re-carried onto the stored entry. The funnel then declines exactly the
writes the host would answer `false` to.

The fixed points, path by path, from `onSettingsChanged`, `onShellChanged`
and the FileView signals to a write or a reassignment that can re-trigger
one of them (rule 15; lane A's search `grep -n 'root.ownWrite =|updateEntryInline(|stateFile.setText|Qt.callLater|root.saveState()'`
over `Service.qml`):
- `ownWrite` is assigned in two places: in the funnel, now only when the
  record differs; and to null in `onHostSettingsChanged`, only when a
  non-null record lapses, so once per write.
- `updateEntryInline`: one call, now only when the host would store
  something new. On the echoing host its publish re-runs reconcile once, and
  the next request is estimated against the moved publish and declined; on
  the lagging host the publish does not move, so the request is estimated
  against `lastEntryWrite` and declined.
- `Qt.callLater(persistActive)`: only from `adoptActive`'s `writeEntry`, and
  it reaches the funnel above.
- `saveState`, 19 call sites. The ones a signal can reach: `adoptActive`
  only when the state object changed (a consumed input is not fresh again);
  `applyUserState` only on `stateOnLoad`'s write answer, whose own reload is
  then ignored as our own write; `adoptSourceStats` only when the record
  lacks the stats; `noteSessionOutcome` only when something changed;
  `startCacheLayout` once; `onMaxRecentsChanged` only when the trim changed
  the state; `stateInitProc`'s exit once; `persistActive` only when the key
  moved; `adoptIdScheme` once per remap.
- `stateFile`'s `saved` / `saveFailed` -> `settleEntryFlush`: a one-shot
  pending key, through the funnel.
- `onShellChanged`: once per injection. `onConfigShieldExit`: a one-shot
  `pendingPersist`; its rerun is a debounce timer that writes nothing, and a
  declined write no longer re-arms the shield.

R18c, QUIESCENCE IS A CHECK. The service-order driver in
`tests/Model.test.js` runs every sequence to quiescence under a bound
(`SETTLE_BOUND`, 400 deferred calls or entry writes) and throws `LOOP` past
it, and a suite-wide check, `R18c: every service-order sequence in this
file reached quiescence under the bound -- no LOOP`, is red if any sequence
did. The driver had been more forgiving than QML (rule 10): it re-ran
reconcile only when the own-write record's CONTENT changed, where QML
re-evaluates `settings` on any reassignment -- which is why P1-B never
reached node. It now reconciles on every reassignment. The input audit
(`R17 / R18c / rule 15: the input audit -- ... refused and superseded values
counted apart, and both kinds reached`) now carries refused values and
whitespace-wrapped variants of every input kind; it normalises with its own
spelling (trim, sanitize, validate), not by calling the code under test;
and it counts a refused value stripped once reported (OQ-W2, confirmed) and
a value superseded by a later explicit input (R18d) apart from a loss, with
a want that each kind -- refused, superseded, and the writes R18b declines --
was actually reached. The `retiredKeep` fixture grows from 20 to 28 cases:
whitespace beside a NON-EMPTY snapshot (a refused value; a removed source
wrapped in a tab and a newline; the first source's EPG in NBSP and an em
space after a switch; the spacing on the snapshot side; fresh against
another value; held under an em space; pending beside another snapshot) and
two no-input values (whitespace alone, control characters alone).

[Round 11: R18d OVERTURNED, R21c/R21d.] R18d. OQ-W1 is confirmed: the snapshot clause stays. OQ-W2 is confirmed: a
refused value is stripped once reconcile has reported it. OQ-W3 is ruled: a
guide URL the in-app ADD form carries -- typed, or derived by an Xtream add
(its `xmltv.php`) -- WINS over a pending CLI `epgUrl`, because the user's
later explicit input for the same slot supersedes the earlier one.
`adoptPendingEpg` takes `opts.formEpg`; a non-empty one marks the
pending input `superseded`, which counts as consumed -- the EPG snapshot
moves onto it (`epgSnapshotAfter`) and the commit's own mirror write
strips it from the entry -- and adopts nothing, the record keeping the
form's value. The service logs `the guide URL in the add form supersedes a
pending input (epgUrl); the bar entry drops it`, the key name and never a
URL. The data-loss oracle counts a value superseded by a later explicit
input for the same slot as not lost. With no guide URL in the form, R17b
adopts the pending value as before. Only the probe commit of an ADD whose
own record is kept hands the form's guide URL over; an edit, a retry and a
never-fetched switch probe have no add form and hand nothing. One branch is
open (lane A's OQ-X3, the lead and UX): in S5's `known` branch -- the CLI
added the same playlist URL while the add's probe ran -- the commit keeps
the CLI's record, which does not carry the form's guide URL (pre-existing S5
behaviour), so nothing is handed and the pending CLI value is adopted as
before. Handing it would strip the pending value too, and the user's two
EPG inputs would then both exist nowhere. [Round 9: R18d's form-wins rule is
OVERTURNED by R19c. It asked nothing about WHEN either input was made, so a
CLI `epgUrl` set while the add's probe ran -- after the submit -- was dropped
although it was the later input (the eighth review's P1-B, live), and the
oracle's supersede exemption covered exactly that case. OQ-X3 is ruled: the
form's guide URL lands on the kept record in the `known` branch by time,
through `epgByTime`. The confirmations of OQ-W1 and OQ-W2 stand.]

Pins on lane-key-x1 (1f8bd1b code and node, lane A; 7a429cd the live
segments; 1565973 their counts), each calling the shipping code, 45
`ok   R18` titles. Units: `R18a: entryInputForm is settingsFrom's trim, then
sanitize, then validation ...`; `R18a: reconcileAction's 'not fresh' and
retiredInputsToKeep's 'consumed' agree for every input kind (valid,
refused, removed) under every wrapping ...` (the 34-case property);
`R18a, the sibling its search found: an EPG input of control characters
alone is NO input ...`; `R18b: entryWriteNeeded answers the host's own
dirty check against the STORED entry as this service can know it ...`;
`R18b: sameOwnWrite is equality over exactly what ownWriteInForce and
settingsWithOwnWrite read ...`; `R18d: adoptPendingEpg with the add form's
own guide URL ...`. Service-order driver cases under both host shapes
(`R18c (lag host)` / `R18c (echo host)`): P1-B with no state file, and with
saved sources and none active; P1-A under three wrappings (two spaces each
side, a tab and a newline, NBSP and an em space), each as a refused value
beside a pending EPG, as a refused value set mid-session beside an active
source, in X1's shape (a CLI playlist adopted, its source removed, a
restart), and as a valid EPG beside the active source and pending with none;
a refused EPG, active and pending; `R18b (... host): writes that change only
the RETIRED keys ... reassign no own-write record after the first`; and
`R18d (... host) OQ-W3`, typed and the Xtream add. Two structural pins,
`R18b (structural): the funnel asks Model.entryWriteNeeded against its own
last-write record BEFORE handing the entry to the host ...` and `R18d
(structural): the probe commit hands adoptPendingEpgOnto the form's guide
URL only for an ADD whose own record is kept ...`, and the suite-wide
no-LOOP check. Live, key-scenario segments K, Z and A (floor 70 -> 78;
`qa-lib-test.sh`'s restart-over-observed pin 4 -> 5 for Z, 443 checks):
K1..K3 lift the lens's `loop-child.sh` -- two saved sources, none active, an
`epgUrl` R12 holds and a REFUSED `playlistUrl` (an `ftp://` URL with a
credential), with the entry writes (the harness log's `updateEntryInline`
lines) and the shell pid's utime+stime counted over a 5 s window opening
2 s after the shell settles, "settled" being at most 2 writes and 50 ticks:
K1 the lagging host, K2 the echoing host on the bare value (a control), K3
the echoing host with the value wrapped in whitespace. Z1..Z3 lift
`resurrect-child.sh` and `MODE=badws`: a whitespace-wrapped CLI playlist
adopted and then removed leaves no `playlistUrl` on the stored entry (Z1)
and the restart does not resurrect it (Z2); a whitespace-wrapped refused
credential beside a working source leaves the stored entry and the source
stays active (Z3). A1 and A2 drive the in-app add's probe commit through
`ipc addSource`, two saved sources and none active with a CLI `epgUrl`
pending: with no guide URL in the form the pending one lands on the new
record (A1, R17b's commit half, which the round-7 live lens found no
segment reaching); with the form's own, the form's wins, the pending value
is on no record and off the stored entry, and the log names the key once
(A2, R18d). The entry's values are never printed: key names from
`hostEntry`, the record's EPG compared inside python.

Counts, each with where it was measured. Lane A on lane-key-x1: node 2,236
/ 0 (+45; read again on lane-key-x2 by lane C: `2236 checks, 0
failure(s)`, 45 `ok   R18` lines), python 1,057, qml spec 78,
`qa-lib-test.sh` 443 / 0, key preflight 11; the gate rc 0 on 1f8bd1b and on
1565973. The same test files over lane-key-w2's code: 2,236 / 41. One-decision
mutations of the shipping code, each a full copy with the node suite run:
the snapshot clause raw again (P1-A) 19 red; R18b removed, both halves
(P1-B) 11; the write skip alone 7; the `Model.sameOwnWrite` guard alone 4 --
not a loop on its own once the skip exists, so it has no live observer of
its own; `Model.reconcileAction` comparing trimmed text instead of forms 1
(the property's same-form pairs); the control-character sibling reverted 1;
R18d in `Model.js` 6, in `Service.qml` 6; the held clause made raw 1 (the
fixture). Live, lane A's transcripts under the scenario's own nested
headless cage on 7a429cd: forward 79 / 0 (`key-20261012-144939-2296398.out`,
133.0 s; every K window 0 writes and 0 ticks); `--baseline lane-key-w2` 73 /
6 (`key-20261012-145158-2305352.out`): K1 `LOOP` (17,414 writes and 596
ticks in 5 s), K3 `LOOP` on the echoing host with the credential kept
(19,943 / 637, `playlistUrl:yes`), Z1 `playlistUrl:yes`, Z2 `records:1
active:[<B>]` -- the removed source back and active -- Z3 `playlistUrl:yes`,
A2 `form:none pending:<D>`; K2 and A1 green as the controls, nothing
outside K, Z and A moved. Through `--tree`, one decision removed from
7a429cd: the raw snapshot compare 75 / 4 (K3, Z1, Z2, Z3, `-145629`; K3
reads `settled` and keeps the credential, because R18b alone stops the
loop); both R18b decisions 78 / 1 (K1, 14,256 / 601, `-145922`); the probe
commit not handing the form's guide URL 78 / 1 (A2, `-150136`).
`sources-scenario.sh` 66 / 0 (the 10k switch median 33 ms) and
`logo-scenario.sh live` 33 / 0 under a nested cage on the same tree. The
seventh review's own instruments, adapted by lane A (three hunks in its
simulator, each gated on the tree having the symbol, so over lane-key-w2 it
reproduces the lens's numbers exactly; and the R18d supersede exemption in
its matrix's oracle): the matrix, 39,000 runs per cell, reads 0 in every
cell on lane-key-x1 against lane-key-w2's lag 120 (the loop), echo 0,
whitespace lag 4,034, whitespace echo 4,004; the loop proof reads `ok, 1
entry writes` in every case on both hosts where lane-key-w2's two lag cases
read `LOOP`; the B1-B3 proofs (resurrection, the refused value, A's EPG on
B) and the OQ-W3 proof are clean on both hosts. With the state init
failing, both trees read the same 34 re-adoptions per host, which are R11's
by design (the review refuted them). Rule 7 on the same tree, the guide
opened over a 10,000-channel generated playlist under the cage, 10 opens x 3
shells: medians 101.5 / 89 / 81.5 ms on lane-key-x1 against 102 / 86.5 /
87.5 ms on lane-key-w2. The first, cold open of a fresh shell measured 163
ms on lane-key-x1 and 173 ms on lane-key-w2 -- over 150 on both trees, and
not moved by this round.

What this round leaves open, with its owner: R18b's second clause as lane A
implemented it, in the funnel rather than in the adopt decision (OQ-X2, the
lead); S5's `known` branch and the form's guide URL (OQ-X3, the lead and
UX); whether the cold first open of a fresh shell is inside rule 7's
150 ms budget, measured over it on both trees (OQ-X6, the lead); an id for
the control-character sibling (OQ-X1, the lead's board); the
`Model.sameOwnWrite` guard, which has no live observer of its own; the
in-app add into an EMPTY source list with an EPG pending, still node only
(E4; A1 and A2 seed two saved sources); the unconfigured empty state's
caption (OQ-C6, unchanged); the rest of D-HOST-4 -- K2 and K3 now run on the
echo lever beside U5-U7, and E6, the key-mirror segments and the L toggle
have not run both ways; D-SINK-20, unchanged; the documents of this round
are lane-key-x2's and nothing was run live by that lane; and `Model.js` at
589,114 bytes on lane-key-x1, further over the marketplace scanner's
524,288-byte per-file limit (D-REL-5; the other workflow's split re-run over
this file at integration). [Round 9: OQ-X2 is moot and OQ-X4 accepted
(R19e); OQ-X3 is ruled (R19c); OQ-X6 is measured as PERF-02 defines the
budget (R19e, below); OQ-X1 is D-SRC-17; the in-app add into an empty
source list is still node only; and the chain landed on the split model as
lane-key-y0 c017d24, so the model is `Model.mjs` and its parts.]

### D-SINK-19 round 9 rulings (lead, 2026-10-12; R19, on top of R1-R18, which stand except where R19 replaces them)

**[Round 11, 2026-10-13: R19b and R19c are OVERTURNED (R21c, R21d: no `pendingEpg`, no `epgSetAt`, no latest-by-time rule). R19a (no skip; `Model.sameOwnWrite` settles the cycle) is KEPT; R19d's owed mirror stands for the migration window (pinned, `R21e (...) D-SRC-18 at the migration`); R19e stands (the normaliser readings and the OQ-X6 budget method are not about the withdrawn route). The text below is unchanged; its withdrawn names are cited without the prefix.]**

Issued after the eighth adversarial review (two lenses over lane-key-x2
a4a3935, 2026-10-12). The chain then landed on `dev`'s split model as
lane-key-y0 (c017d24: `Model.js` cut into `Model.mjs` and its parts, the
chain's three `Model.js` comment citations reworded first), and round 9 was
built on that as lane-key-y1 (690a888 the code, 19f3d0b to 7d9f519 the
scenario, one fix and its pin). Both lenses closed round 7's P1s on
lane-key-x2: the write loop (LOOP 0 in 571,000 runs of the data-loss lens's
matrix, against 2,774 on lane-key-w2) and the whitespace hole (RZ 0; the
refused-value cases 774 -> 4 per host, those four being the new defect).
They found:

P1-A, both lenses, live. R18b's write skip. `writeOwnedEntry` returned
early when `entryWriteNeeded` said the host already stored the entry,
judged from `Service.lastEntryWrite` while the publish equalled the publish
recorded at the last write. On the lagging host the publish recorded right
after a write is the PRE-write entry, and an `omarchy bar set` that restores
exactly that entry (`PluginRegistry.setBarWidget` does `entry[key] = value`
in place, so any entry the plugin has written once is reproduced exactly)
publishes the write and then the restored entry: A -> B -> A. The record
compared equal again although the host now stored A, and the next action
whose entry equalled the last write was skipped. Three consequences, each
observed live under a nested cage on the lagging fake host, and clean on
lane-key-w2 and on the echoing host. An in-app logo OFF after `omarchy bar
set ... showLogos true` did nothing: the guide said `logos off`, logos
stayed on and were fetched, also after a restart (`in-app toggle OFF #2:
guide showLogos=True entry writes +0`). A refused credentialed
`playlistUrl` set again stayed in `shell.json` for the rest of the session:
the live lens saw it survive 30 s, a guide open and close and a refresh
(`after set #3: ... stored playlistUrl true ... hand-overs 2`), and only
the next start removed it. And an `epgUrl` set twice for the active source
stayed on the entry and replaced a later in-app guide URL edit at the next
start (`after restart: ... record epg=E`). The node suite (2,236 / 0) and
key-scenario (79 / 0) were green over all three: no check re-set an
identical value, and the input audit ran only at writes that were made, so
a skipped write was never audited. The code's own comment on
`onHostSettingsChanged` stated the rule the record broke, for the override
("a host value that later returns to what it was when we wrote must not
resurrect a spent override"); `lastEntryWrite` was the sibling not given it
(rule 15).

P1-B, the data-loss lens, live. R18d superseded a pending CLI `epgUrl` set
AFTER the add form was submitted, while the probe ran: the later input E
ended on no record and off the entry (`E ... on record: no-record; F on
record: <key>`; lane-key-w2 kept E and lost F, so neither tree kept the
later value). R18d asked nothing about when either input was made, and the
oracle's supersede exemption, keyed on the time of the supersede rather
than of the form's submission, covered exactly this case. P2, the same
principle on the EDIT form: a guide URL typed into the edit form while an
older CLI `epgUrl` was pending was replaced by the older one at the switch
(`switch to A: ... A.epg=E`); R18d's sibling search had cleared the edit
route because "there is no add form", and the edit form has a guide URL
field. P2 (a12): reverting `Service.activeEpgUrl` to its round-7 read
reddened nothing, node or live, and is not equivalent -- the two reads
differ on an input of control characters alone, which does sit on the
entry until the next write. P3, already on the board as D-SRC-18: an input
left on the entry because its state write failed is re-adopted at the next
start over a later in-app edit that landed.

R19a, NO SKIP ON AN ESTIMATE. The funnel never skips a write on an estimate
of what the host stores. Every owned write is handed to `updateEntryInline`
and the host's own answer is the dirty check -- `false` from a writable
entry is "already stored", which is success (rule 9) -- and the own-write
record is reassigned only when `Model.sameOwnWrite` says it differs, which
alone settles the cycle. `Service.lastEntryWrite` is gone. `entryWriteNeeded`,
`entryWriteRecord` and `hostEntryForm` have no shipped caller and are pinned
as having none (`R19a (structural)`); they stay declared only because the
round-8 text in this file and three other documents cite them, and they are
cited here without the `Model.` prefix so that the commit that deletes them
has only the round-8 citations to reword. The keep warning is back in
front of the hand-over, and when the host answers `false` the funnel returns
before re-arming the D-SINK-18 shield, because nothing was written. With
the skip AND `Model.sameOwnWrite` both removed there is still no loop, in
node (lane A's m2), in the lens's loop proof or in the matrix: R19b took
away the loop's precondition, an EPG input that stayed fresh on the entry
forever. `Model.sameOwnWrite` is kept and pinned anyway (m2 reddens 4).
OQ-X2 is moot.

Rule 15 for R19a, lane A's search for any other "last seen" estimate keyed
on a value that can recur (`property .* (last|prev|recent|reconciled|seen|known)`
over `Service.qml`, `Guide.qml` and `BarWidget.qml`, plus every comparison
of a remembered value against a fresh one). `lastEntryWrite`: removed.
`ownWrite`: cleared -- `onHostSettingsChanged` drops it on any publish other
than its base, so it cannot come back. `reconciledPlaylistUrl` /
`reconciledEpgUrl`: cleared -- they move on every reconcile and track the
previous publish, so A -> B -> A re-adopts A, which is right because A is a
later explicit input; the one way a value comes back without a user act is
D-SINK-20's patch-only re-carry, already filed. `recentSaves`, own-write
reload detection by text: OPEN, low severity -- a foreign write byte-identical
to one of the last 8 pretty-printed saves is ignored, so memory overwrites a
user's restore of an older `state.json`; the helper writes compact JSON and
cannot match it, so only a hand edit can [round 15, 2026-10-14: closed
by R25a (D-SRC-30), and "low" and "only a hand edit" were both too kind --
a COPY of the plugin's own file, which the README advises keeping, is
byte-identical to one of those saves, and the round-14 data-loss lens put
one back after an in-app remove and watched the next save write over it
(FAV BAK DEL RSTB FAV). `recentSaves` now holds only the texts still in
flight; the round-15 rulings below]. `lastSaveText` /
`Model.stateSaveLanded`: cleared -- a save sequence A, B, A' can read as
landed early, but the content then equals memory, and a key mismatch
resolves through R1 step 2. `preparedLru` (keyed by `channels.json` text)
and `logoHave` (tagged by directory): cleared, correct by content.
`lastEndFile`, `previousPlaying`, `lastFailedId`, `lastError`: per event,
never compared against a recurring entry value.

[Round 11: R19b OVERTURNED by R21c; `pendingEpg` deleted, R21d.] R19b, A PENDING GUIDE URL LIVES IN THE STATE. An `epgUrl` input that no
record can take -- no source is active -- is adopted into `state.json` as
`pendingEpg { url, seenAt }` (section 2.1), never into `shell.json`, and
stripped from the entry by the same R13-gated owned write that strips every
consumed input, so it counts as held (`Model.retiredInputsToKeep`). This
REPLACES R12's on-entry pending state, which kept a possibly credentialed
URL -- an Xtream `xmltv.php` carries the account -- in a file the plugin
does not own for as long as no source existed; R12's principle, never
stripped unadopted, stands, because the state copy is written before the
strip. `Model.adoptActiveSource` holds a valid input and consumes a refused
one as refused (reported and written out, as beside an active source;
lane A's reading (a)). A later input replaces an earlier one. The service
logs `no source is active; the guide URL input (epgUrl) is held in the state
for the next one`, setting names only. `Service.activeEpgUrl` reads the held
URL when there is no record (`Model.activeEpgUrlOf`, below), so the guide's
fallback is unchanged. The whitelist trap, rule 15's other shape:
`Model.parseState`, `Model.cloneState` and `Model.normalizeSourceRecord` are
taught the two new keys, and copySourceRecord and replaceSource (both internal to
`model/source-records.mjs`, cited bare since round 10's R20e because
`Model.mjs` exports neither), `Model.withSourceStats`, `Model.touchSource` and `Model.updateSource`'s
replacement record already carry `epgSetAt` by copying whole records. The
helper's `normalize_state` / `normalize_source` are NOT taught them: every
helper write of the file erases `pendingEpg` and every `epgSetAt`. Open, no
id yet; `bin/` is not this round's. [Round 10: D-SRC-20 on the board,
closed on lane-key-z1 by R20a; the remap was never among these writes.]

[Round 11: R19c OVERTURNED; `epgSetAt` deleted, R21d.] R19c, THE LATEST EXPLICIT INPUT WINS, BY TIME. Every record carries
`epgSetAt` (ms, persisted; section 2.1), set when its guide URL is set: by
the add form at SUBMIT time -- `Service.addSource` hands `Date.now()` to
`Model.addSource` at the moment it is called, never at the probe's commit --
by the edit form when it changes the guide URL (`Model.updateSource`), or by
adoption with the input's `seenAt` (`Model.adoptActiveSource`). At an active
move -- a switch, an add's commit, an edit-then-switch, the S5 `known`
branch -- the held value lands on the newly active record iff its `seenAt`
is LATER than the record's `epgSetAt` (absent = 0; an equal time is not
later), and otherwise the record keeps its own (`epgByTime`,
`applyPendingEpg`); either way the held value is cleared, with a log
line naming the setting and the source key only (`a pending guide URL
(epgUrl) lands on source <key>`, or `... is superseded: source <key> keeps
the one set later`). `Service.adoptPendingEpgOnto(key)` takes the key and
nothing else; the R18d form-wins argument is gone. OQ-X3 is ruled: in the
`known` branch the form's guide URL lands on the kept CLI record with its
submit time through `epgByTime` iff it is later than what that record
holds, and a held input is then judged against the result. A CLI `epgUrl`
beside an ACTIVE source is adopted onto it as before (R4), stamped with its
`seenAt`. Records written before R19 have no `epgSetAt` and read as 0.
Lane A's readings, for the lead to confirm: (b) the `known`-branch landing
also applies to a playlist-URL EDIT whose new URL the CLI added during the
probe, through the same call; (c) the edit form stamps only a guide URL it
CHANGES, because the form re-sends every field, so re-typing the same URL
does not move its time; (d) a re-set equal to the guide URL the active
record already holds is not re-stamped (308258f) -- no held value can be
waiting while a source is active, and the state write a re-stamp costs
deferred the strip behind R13 and hid a later re-set of the same value
(found by the round-9 matrix; pinned, 3 red before the fix); (e) times are
`Date.now()` on both sides, so a wall clock stepped backwards between two
inputs inverts their order.

Rule 15 for R19c, every place a guide URL is set. Stamped: the add form
(`Service.addSource`; `buildXtreamSource` routes through it, so an Xtream
login's `xmltv.php` is stamped at submit), the edit form
(`Service.updateSource`; the IPC `updateSource` routes through it), CLI
adoption beside an active source, a held value that wins, and the S5
`known` branch. Not stamped: `Model.reconcileSources`' new CLI-added record,
which never carries a guide URL (step 1 passes `adoptEpg` false); and the
helper's `state source add|update --epg-url` (`bin/`, the open item above)
[round 10: stamped since R20a, in ms, `update` only on a change].

R19d, D-SRC-18, SETTLED under R19c for the shape on the board. The order of
the input and the later edit IS known, in memory; what was missing was the
write that would have recorded it after the failure. So a held key mirror
dropped because its save failed (`Model.entryFlushDisposition`,
`save-failed`) now leaves a debt, `Service.entryMirrorOwed`, and the first
later save to LAND with nothing held, parked, in flight or failed pays it
with one key mirror through the funnel (`Model.owedMirrorAction`, deferred
from the FileView's `saved` by `Qt.callLater`), which strips everything
consumed; a heal clears the debt itself. Observed live (key-scenario H1:
the failed adoption leaves the input on the entry, the later edit's save
lands, the owed mirror takes the input off, and the restart stands on the
edit; red on `--baseline lane-key-y0`), in node under both hosts
(`R19d (... host) D-SRC-18`) and by the lens's `trace-lf` (`after restart:
file A.epg=G`). Where the order cannot be known: the shell dying in the one
`Qt.callLater` between that landing and the owed mirror -- the next start
then re-adopts the input, seen "now", because the write that would have
recorded its time is the one that failed. [Round 10: knowable now. R20b
writes down what the service consumed, so that start finds the input's
digest in the landed file and does not adopt it again; node `R20b (lag
host)` and `(echo host) D-SRC-18: ... the shell dies before the owed mirror
runs`, red on lane-key-y2.] And the lens matrix still reads
LF 6 (lag) and 4 (echo) at length 3, every one with state saves held and
every other save failing (`cliE|cliE2 > editActiveEpg > editB_epg`); lane-key-y0
reds on the same combinations, so they are R13's save-failure class rather
than this shape, recorded rather than settled. The rest of R19d's search:
`Model.entryFlushDisposition`'s `drop init-failed` is not made owed, because with
the start-up `state init` failing no save can land anyway; and the logo
toggle in patch mode keeps the retired keys by design (R16), and the next
heal pays. [Round 10: that clearance was false. The round-9 data-loss lens
measured the sequence in which no heal follows (a failed write, the toggle,
then the failure clearing), re-graded D-SINK-20 to P2, and R20c repairs the
writer.]

R19e. OQ-X2 is moot under R19a. OQ-X4 is accepted: a value equal to another
under the one normaliser is the same input, and a value of whitespace or
control characters alone is no input -- the two behaviour changes R18a's
text records stand as ruled. OQ-X6: the 150 ms budget is the OPEN WORK as
PERF-02 in `QA-RESULTS.md` defines it, the `ipc toggle` round trip minus
the IPC round trip. Measured that way by lane A on 10,000 generated
channels under a nested cage at load about 1.6-1.8, three fresh shells per
tree, the IPC round trip taken as the median of five `ipc widget` calls
(59-60 ms): the cold first open is 164, 162 and 159 ms of open work on
lane-key-y1 and 165, 156 and 161 ms on lane-key-y0; the warm medians are 88,
93 and 90 ms (max 102) on lane-key-y1 and 87, 88 and 86 ms on lane-key-y0.
So by the ruling's own definition the cold first open is OVER the budget on
both trees, by 6 to 15 ms, the warm open is inside it, and round 9 moves
neither. Whether the cold open needs a defect id is the board's. [It is
F-PERF-2 (P3) since the round-9 reviews, which read 158-162 ms cold on both
chain trees; round 10 measured `dev` the same way, R20g below.]

a12, rule 12. `Service.activeEpgUrl` is now one call,
`Model.activeEpgUrlOf(record, input, pending)`, which node calls (`R19 /
a12: activeEpgUrlOf ...`): beside a record an input of whitespace or
control characters alone is no input and the record's guide URL stands
(D-SRC-17's shape, R18a); an input that is something and does not validate
is returned as it is, so the helper reports it (D16); with no record, the
input on the entry, else the held URL. Lane A's m9, the inline read back,
reddens 1. Its search found no other inline read: `Guide.qml` and
`BarWidget.qml` read no entry input.

Pins on lane-key-y1, each calling the shipping code, 38 `ok   R19` titles.
Units: `R19b (R12 until round 9): an EPG input with NO active source is
HELD in the state as pendingEpg and consumed ...`; `R19b: the EPG set
before any source is held at the first reconcile ...`; `R19c:
adoptPendingEpg over a value HELD in the state -- it lands iff its seenAt is
LATER ...`; `R19c: epgByTime ...`; `R19b/R19c: parseState and cloneState
carry pendingEpg ...`; `R19c: addSource stamps the form's guide URL with
the submit time ...`; `R19 / a12: activeEpgUrlOf ...`; `R19d:
owedMirrorAction ...`. Service-order driver cases under both host shapes
(`R19a (lag host)` / `(echo host)` and the same for R19c and R19d): A -> B
-> A on the logo, the refused and the EPG routes; the probe race, form
first and CLI first; the edit route in both orders; the S5 `known` branch
with no CLI EPG, with one set after the submit, and with one set before it;
a restart between the input and the move, in both orders, the times read
back from the file; the re-set not re-stamped with every state write in
flight (308258f); and D-SRC-18. Two structural pins, `R19a (structural):
the funnel hands EVERY owned write to the host ...` and `R19c (structural):
the probe commit hands adoptPendingEpgOnto nothing but the key ...`. The
input audit (`R17 / R18c / R19 / rule 15: the input audit -- ...`) now
counts the state's held guide URL as held and a supersession only by a
LATER time, and wants declined hand-overs and moves seen. The `adopt`
fixture section grows from 25 to 32 cases, two R12 cases rewritten as R19b.
Removed, with notes left in their place: the R18d form-wins unit and the
`entryWriteNeeded` unit; and the two round-8 structural pins, `R18b
(structural)` and `R18d (structural)`, are replaced by the R19a and R19c
ones (the driver still binds the funnel's lines, now through `R19`). Live, key-scenario segments Y, Q, V and H (floor 78
-> 85; `qa-lib-test.sh` 453 -> 454 with a pin that the slow listener is
killed by its recorded pid): Y lifts the lens's `aba-child.sh` (Y1 the logo
route, Y2 the refused route, Y3 the EPG route), starting, as that driver
does, over an entry carrying A's URL -- written first over the harness
seed, Y1 and Y3 were green on lane-key-y0, which has the defect (1a88ab2);
Q lifts `race-child.sh`, the probe held open by a local listener that
answers after 4 s, its pid read from `ss -ltnp` and killed by that pid (Q1
form first, Q2 CLI first); V lifts `T=edit`; H is D-SRC-18 at the sink with
F's lever (the state directory 0500 under the running shell). U, K and A
now read `held:` from `state.json`.

Counts, each with where it was measured. Lane A on lane-key-y1: node 2,268
/ 0 (+32 over lane-key-y0's 2,236), python 1,135, qml spec 78,
`qa-lib-test.sh` 454 / 0, the key preflight 11, 745 declarations in 18
parts and 636 names exported from `Model.mjs`; the gate rc 0 on 19f3d0b,
42850dc and 7d9f519. The same test files over lane-key-y0's code: 2,266 /
52. One-decision mutations of the shipping code, each a full copy with the
node suite run, on 19f3d0b's code (2,266 checks): the skip put back 6 red;
`Model.sameOwnWrite` removed 4, with no loop; the held input not counted as
held 37; an equal time winning 3; the held value always winning 17; no
submit stamp 12; no owed mirror 2 (D-SRC-18 on both hosts); the held clause
removed from `Model.retiredInputsToKeep` 0, argued equivalent above; the
a12 inline read 1; no by-time landing in the `known` branch 5; the edit
stamping an unchanged URL 1; no edit stamp 6; `seenAt` 0 28; the held value
not cleared 41; `Model.parseState` dropping `pendingEpg` 7; reconcile not
applying the held value 6. The 308258f pin was red against 19f3d0b's model
part (2,268 / 3). Live, lane A's transcripts under the scenario's own
nested headless cage: forward on 42850dc 86 / 0
(`key-20261012-181012-2900687.out`, 205.2 s; every K window 0 writes and 0
ticks; no credential token in the harness log); `--baseline lane-key-y0` 74
/ 12 (`key-20261012-181343-2916616.out`): U1, U2, U5, K1, K2, K3 read the
EPG still on the entry and not held, Y1 `off2:true/0`, Y2 `after:no no
yes`, Y3 `twice:E/yes ... after:<A>/E`, Q1 `during:no/<key> ... on:F`, V1
`on:E`, H1 `landed:false/yes ... after:<A>/E`, with A1, A2 and Q2 green as
the controls; the two key-mutation patches through `--tree` 80 / 6
(`-182219`: D2, D3, W2, W3, W4, W6) and 81 / 5 (`-182602`: D2, W2, W3, W4,
W6), the letters their README names. `sources-scenario.sh` 66 / 0 (the 10k
switch median 35 ms) and `logo-scenario.sh live` 33 / 0 under a nested
cage on the same tree. The eighth review's instruments, adapted by lane A
(the simulator loads `Model.mjs` and carries round 9's `Service.qml` hunks,
gated on the tree having `pendingEpgOf` and `Model.owedMirrorAction`;
the matrix counts a guide URL held in the file as present, and an earlier
input superseded at an active move by a later in-app edit as superseded):
on lane-key-y0 they reproduce every round-8 finding and the length-2 matrix
reads lag 24 and echo 16 (78,540 runs per host); on lane-key-y1 every
proof reads ok on both hosts and the length-2 matrix reads 0 and 0. At
length 3 (206,780 runs per host, a 14-operation subset chosen by lane A to
match the lens's run count, the lens having recorded no list) lane-key-y0
reads lag 623 and echo 420, lane-key-y1 lag 64 and echo 51, every one with
state saves held; 56 (lag) and 43 (echo) are combinations lane-key-y0 also
reds on -- the identical re-set while its strip is held, and R13's
save-failure class -- and 8 per host are new, all one shape (below). LOOP 0
everywhere; the logo route 0, against lane-key-y0's 10.

What this round leaves open, with its owner. The helper's whitelists
(`normalize_state`, `normalize_source`) erase `pendingEpg` and `epgSetAt`
on every helper write of the file -- an input then exists nowhere, or a
held value later beats an in-app edit; it needs an id, a shared fixture and
a helper change (the lead's board, then the helper's lane) [round 10:
D-SRC-20, closed by R20a]. A new
reachability of an R13 residual (lane A): RZ, saves held and every other
one failing, `cliP_A > removeActive > cliE` -- R19b makes holding a guide
URL a state write, and when that later write fails, R13 drops the remove's
mirror, a CLI playlist URL stays on the entry and is re-adopted at the next
start, so a removed source comes back. The user was told the write failed
(`state_write_failed`); whether a failed hold should leave the remove's
strip in place, deciding by landed content rather than by the last save, is
the lead's. `recentSaves` matching a hand-restored older `state.json` (low,
above) [round 15: closed by R25a]. The cold first guide open over 150 ms of open work on both trees
(R19e). Deleting the three retired functions, which needs the round-8
citations reworded in the same commit. Lane A's readings (a) to (e), and
whether to keep the held clause m8 shows equivalent. The in-app add into an
EMPTY source list with a guide URL held, still node only (E4). D-SINK-20,
unchanged [round 10: re-graded P2 by the round-9 data-loss lens and
repaired by R20c]. And the documents of this round are lane-key-y2's, a documents
lane that ran nothing live; every live count above is lane A's, re-read
from its transcripts.

### D-SINK-19 round 10 rulings (lead, 2026-10-12; R20, on top of R1-R19, which stand except where R20 replaces them)

**[Round 11, 2026-10-13: R20b and R20c are OVERTURNED (R21b's in-memory record replaces the persisted `entryInputs`; the patch-only write keeps the retired keys while the migration marker has not landed and none after). R20a's key check is KEPT and now covers the marker; R20d's behavioural service harness and R20e's ledger rule are KEPT. The text below is unchanged; its withdrawn names are cited without the prefix.]**

Issued after the ninth adversarial review: two lenses, the data-loss lens
and the integration-and-live lens, over lane-key-y2 (e29068c), the round-9
candidate. Round 10 was built as lane-key-z1 by lane A on lane-key-y2 with
`dev` b594b12 merged in (81c6d8a, 0 conflicts): 5b21950 (R20a-R20d), 75d53e7
(R20e), 6ae222e (key-scenario Y4), 0d822ba (R20f), 92395c4 (an R20b
correction), 0d407e5 (key-scenario L2 re-wanted), f9eda77 (two
`Service.qml`-level R20b cases) and 3e3acb2 (three helper docstrings
re-cited). The documents are lane-key-z2's, which also merges `dev` 7c571a9
(the 0.13.6 release; c99df0c, one conflict, the python floor, resolved to
the merged tree's measured 1,143). Both lenses held everything round 9 aimed
at -- round 8's routes red on lane-key-y0 and clean on lane-key-y2, no LOOP
at any length, the split cut byte for byte -- and the ids they raised are
on the board in `docs/STATUS.md`, filed in `docs/QA-RESULTS.md` under "the
D-SINK-19 round-9 reviews".

D-SRC-20 (P1, the chain only; both lenses, live). R19b moved the only copy
of a guide URL set with no source active into `state.json` as `pendingEpg`,
and the helper's `normalize_state` / `normalize_source` are whitelists that
knew neither it nor `epgSetAt`: a hand-run `omarchy-iptv state favorite
add` (or `clear-recents`, or a `state source` verb) followed by a shell
restart before the service saved again left the user's CLI guide URL in no
entry, no record and no state -- "THE CLI GUIDE URL E EXISTS NOWHERE" under
a nested cage on lane-key-y2, where lane-key-y0, which kept the value on the
entry, kept it. The round-9 documents had recorded it as open with no id,
against rule 13. D-SRC-19 (P3, shipped) is why it needs a restart: the
service's `stateFile` FileView does not reload after the helper's atomic
rename (its reload counter did not move), so memory hides the helper's write
and the next service save writes memory over it [round 14, 2026-10-14: that
rig's session shape was the one that never reloads -- the state directory
absent at the first load (the round-13 live lens) -- and R24c re-arms it; in
every other session the rename is reloaded (R23g)]. D-SINK-20, re-graded P2 by
the data-loss lens: its record bounded the lagging host's patch-only
re-carry to a URL a record already held and the next owned write stripped,
and live on lane-key-y0 and lane-key-y2 both bounds failed -- a refused
`ftp://` credential no record holds was re-carried and stayed in
`shell.json` for the session, because no owned write follows once the
failure clears, and at the next start the re-carried value was seen as new
and replaced a later in-app guide URL edit that had landed (`RESULT recarry
E: THE LATER IN-APP EDIT F IS REPLACED BY THE OLDER CLI VALUE`). F-PERF-2
(P3): by PERF-02's method the cold first open read 158-162 ms on both chain
trees under a nested cage, and `dev` had not been measured the same way.
Without ids of their own, under D-SINK-19's row as every earlier round's
were: a P2 that R19a's decision had no behavioural observer (the lens's
mutant S1b, a skip on the publish estimate one line before the compose,
read node 2,268 / 0 and live 86 / 0 while the second of two consecutive
in-app logo toggles was ignored on the lagging host; S13, the add form
stamped at the commit, read node 0 and was caught only live, Q1); a P2 that
the gate's floors were still `dev`'s, 193 node checks and 12 python tests
below the tree; and three P3s -- a restart re-stamping an entry input that
`state.json` already proved older, two citations (`copySourceRecord`,
`replaceSource`) of names `Model.mjs` does not export, and the one-time id
remap wrongly listed among the helper writes that erase `pendingEpg`. The
round-8 ids stand as the board has them: D-SRC-17 (an `epgUrl` of control
characters alone cleared the active guide URL; fixed on lane-key-x1, pinned
by `R18a, the sibling its search found: ...` and `R19 / a12: activeEpgUrlOf
...`, both green on lane-key-z1) is untouched by round 10, and D-SRC-18 is
below.

R20a, THE HELPER KEEPS WHAT THE SERVICE WRITES. The ruling: `normalize_state`
and `normalize_source` preserve `pendingEpg` and `epgSetAt`, validated and
never invented, with ONE shared fixture run by `tests/test_state.py` and the
node suite, and rule 15 as a CHECK rather than a search -- a test that every
key the service's state serialiser can emit, top level and per record, is
one the helper preserves or one listed, with its reason, as service-only,
red the day someone adds a key to one side. Built: the helper mirrors
`pendingEpgRecord` (`normalize_pending_epg`), `entryInputRecord`
and `entryInputsRecord` (`normalize_entry_input`,
`normalize_entry_inputs`, for R20b's new key), and carries `epgSetAt` in
`normalize_source` (section 2.1 has each rule). The fixture is
`tests/fixtures/state-keys.json`: the vocabulary, a document carrying every
key, and 16 value cases. The check is node `R20a: the keys the service can
serialise (<shape>) are exactly the shared fixture's, which the helper
preserves`, one per shape (top, source, played, savedSearch, pendingEpg,
entryInputs, entryInput), `R20a: the fixture's document carries every
listed key, and parseState plus the service's serialiser keep every one of
them`, and `R20a: every Model call Service.qml hands the state to is either
driven by the key check or named as a reader`, which reads the shipping
`Service.qml` by shape and fails on a new call not listed; the python side
is `test_r20a_the_helper_emits_exactly_the_shared_vocabulary`. Two things
rode along. `public_state`, the helper's printer, prints the held guide URL
as its host (`epgHost`), never the value: teaching the reader alone would
have put that URL on the stdout of every `state` verb, a rule-5 sink. And
`state source add|update --epg-url` now stamps `epgSetAt` in ms, `update`
only on a change, closing round 9's R19c search's open route. Seen red
(lane A's one-decision mutants on the tip): the model emitting a new
top-level key 2 node failures, among them `... (top) ...`; the helper
emitting one 4 python failures, among them the vocabulary test; the helper
dropping `pendingEpg` 3 failures and 1 error, dropping `epgSetAt` the same;
the helper printing the held URL 1; `str()` back in the model's reader 1.
The same test files over lane-key-y2's code, re-run by the documents lane
in a `git archive` of e29068c: node `2319 checks, 23 failure(s)`, and
`test_state.py` 41 tests, 2 failures and 4 errors, all six the new tests.
At the sink: the round-9 lens's own driver under lane A's nested cage
(`r9-child.sh T=helper HELPER_RESTART=1`) reads `RESULT helper: E is kept`
on lane-key-z1 and `... EXISTS NOWHERE` on lane-key-y2; the lens's
length-2 matrix with its helper write made REAL (lane A's
`matrix9-real.js`, which runs the tree's own `bin/omarchy-iptv` as `python3
-I` on a 0700 directory in the lane scratch; 15 operations, 19,200 runs per
host) reads 0 problems on both hosts on lane-key-z1 and 192 per host on
lane-key-y2 (`PEND:helper` 190, `EPG:LOST:init:helper` 2). The lens's
unmodified `matrix9.js` reads the same on every tree, because its
`helperWrite` operation deletes the two keys itself, as lane-key-y2's
whitelist did. D-SRC-20 is closed on the chain by R20a; its board state is
the lead's.

The remap correction. Round 9's documents listed "the one-time id remap"
among the helper writes that erase `pendingEpg`. It does not:
`remap_state_file` edits the RAW document, precisely to stay clear of the
whitelist, and the round-9 integration lens measured a call over a file
carrying both keys keeping them (section 2.1 has the line). The remap's own
docstring was wrong too, in the other direction, and is corrected in
5b21950: it said the service "already asks for" `state source add`
mid-session and that "the service's FileView reloads state.json and
Model.stateOnLoad merges it". The service spawns no `state` verb but `init`,
and the FileView does not reload (D-SRC-19). For the remap that is harmless
by construction: the service's active-source fetch is the one call site that
passes `--state-dir` (D-ID-1), and the service remaps its own memory onto the
same scheme when it applies the list (`Service.adoptIdScheme`, D-ID-3), so
its next save agrees. A hand-run `state` verb has no such twin, and
D-SRC-19 stays open; round 10 changes nothing in the service's reload.
[Round 14, 2026-10-14: "the FileView does not reload" held only for a
session whose state directory did not exist at its first load; R24c
re-arms that session, R24a merges a helper write that arrives while a save
is held, and the docstring now says so.]

[Round 11: R20b OVERTURNED by R21b's in-memory record; `entryInputs` deleted, R21d.] R20b, THE CONSUMED SNAPSHOT SURVIVES A RESTART. The ruling: what the
service has already consumed from the entry -- the in-memory reconciled
playlist and guide snapshots -- is persisted in `state.json` with the time
it was consumed, and at a start an entry input equal to it is not fresh; an
entry input equal to the state's `pendingEpg` is judged with that `seenAt`,
never with now. Built: `entryInputs` (section 2.1), one slot per input
holding a DIGEST of the consumed value and never the value, because a
refused input is consumed too and can carry a credential; the first
reconcile after a start seeds the snapshots from it
(`entryInputSeed`); every snapshot move moves its slot
(`entryInputsAfterMove`, in `Service.reconcile` and
`Service.adoptPendingEpgOnto`); every owned write marks a slot whose value
the handed-over entry no longer carries as `stripped`
(`entryInputsAfterWrite`), so the same value set again while the shell
is down is fresh. The slot and the mark RIDE the next state save rather
than costing one: a save issued for the slot alone held the strip behind it
(R13) and reproduced the hidden re-set 308258f fixed (lane A: the R19c
re-stamp case went red with an eager save). The second half of the ruling
is `opts.atStart` on `Model.adoptActiveSource` (section 3.5), and lane A
applied it at the FIRST reconcile after a start only, not in session: the
first build applied it in session too, and the round-9 lens's own matrix
read `EPG:OLD:init` 4 and `EPG:OLD:cli` 2 at length 2 (a CLI re-set of the
held value, made in session, judged with the held value's OLD `seenAt` and
losing to an older record time), where lane-key-y2 reads 0; 92395c4
restricts it and the matrix returns to lane-key-y2's 574 / 12 on both hosts.
In session the service SAW the entry change, which is the user setting it
again, a later explicit input under R19c. That reading is lane A's, for the
lead to confirm. Does it settle D-SRC-18 and the restart half of D-SINK-20?
By the lens instruments, yes. The one window R19d could not cover -- the
edit's save LANDS and the shell dies before the owed mirror's
`Qt.callLater` -- is now driven through `Service.qml`'s own functions, `R20b
(lag host)` and `(echo host) D-SRC-18: E adopted onto A on a failing disk
stays on the entry; the edit to F lands and the shell dies before the owed
mirror runs -- the restart does not adopt E again ...`, red on lane-key-y2
and green on lane-key-z1; and live, the lens's `r9-child.sh T=recarry X=E`
under lane A's cage reads `after restart: ... file A epg=F` and `RESULT
recarry E: the in-app edit F stands` on lane-key-z1, against `file A epg=E`
and `... REPLACED BY THE OLDER CLI VALUE` on lane-key-y2. The round-9
data-loss lens's P3, the restart re-stamp, is closed twice: by the slot (E
is not fresh at the start) and, for a file an earlier build wrote with no
slot, by the at-start held time (`R20b (lag host)` and `(echo host) P3 at a
start, through Service.qml: ... the start makes A active and G stands`, red
with no `atStart` passed). Seen red: lane A's mutants on the tip, of 2,319
node checks -- no seed 4, no slot move 5, no stripped mark 1, the seed
ignoring `stripped` 1, no held-time rule 4, the held-time rule in session 4,
`Service.qml` passing no `atStart` 2, `Model.cloneState` dropping the key 5
(the no-`atStart` mutant here and R20c's slot-clause mutant first read 0; a
case was added for each and each was then seen red). The residual, lane A's and the lead's to
give an id or not: because the slot and the mark ride the next save, a strip
followed by no save at all, then a restart, then the same value set again
while the shell is down, ignores that re-set. Every in-app act that makes
such a re-set mean something -- a switch, an edit, a remove -- saves, so the
window is an edit made inside the consumption save's flight.

[Round 11: R20c OVERTURNED beyond "keep while the migration has not landed", R21a/R21b.] R20c, THE PATCH-ONLY WRITE STRIPS WHAT IS REFUSED OR LANDED. The ruling:
while a state write is outstanding the logo toggle keeps a retired key ONLY
when it is a valid input the LAST LANDED state does not hold (a record,
`pendingEpg`, or the consumed snapshot); a refused value, already reported,
and a value the landed state holds are stripped; the round-4 P1 stays
closed, proved with the round-4 sequences; and the wrong narrowing in
D-SINK-20's record stays wrong, with the reason. Built:
`patchInputsToKeep` (section 3.5) over `Service.landedState`, the
state the last landed save serialised or the file as it was loaded. One
reading departs from the ruling's letter, lane A's for the lead to confirm:
a REFUSED value the service has not yet reconciled -- before the first
state load nothing has been -- is kept, so its report is not lost with it;
"ONLY when valid" read literally would strip it unreported. Why this
narrowing is right where the other was wrong: the override narrowing decided
from the HOST (is an own-write override in force), which says nothing about
whether the value is stored anywhere else, and so stripped the only copy of
an input whose state write failed; this one decides from the DISK -- the
state the last landed save serialised, or the file as loaded -- and strips
a value only when that file already holds it. The round-4 sequences keep
their URL: `R20c (lag host)` and `(echo host) round-4 P1: CLI playlistUrl
NEW on a failing disk, then the logo toggle -- the patch-only write KEEPS
NEW (the landed state holds no record of it), and the next start adopts it`
and `... round 6's C1: a URL set while the shell was down, the toggle BEFORE
state.json loads -- no landed state, so the patch-only write keeps NEW, and
the load adopts it`; the mirrored driver's R16 failed-disk cases; and live,
key-scenario L1, L2, F6 and F7. Lane A's mutant deciding from memory
rather than disk reddens exactly the two round-4 harness cases (4
failures). L2's want moved (0d407e5): until round 10 it asked for `epgUrl`
on the patched write too, because R16 kept every retired key, the harness
seed's EMPTY `epgUrl` included; R20c keeps only a valid input the landed
state does not hold and an empty value is no input, and lane-key-z1's first
live run under the old want read `keys:0` with every other L and F check
green (`key-20261012-210503-3375256`). The new want, `playlistUrl` (the only
copy) and `sourceKey` beside `showLogos`, is still red on lane-key-t2 by
construction, where L1 read `playlistUrl:no`. Live at the sink, the lens's
driver under lane A's cage: `T=recarry X=BADE` (a refused credential) reads
`stored epgUrl=no` after the toggle, after the label edit that lands and 5 s
later on lane-key-z1, and `stored epgUrl=yes` all three times on
lane-key-y2; `X=E` reads `stored epgUrl=no` after the toggle on lane-key-z1
and `yes` on lane-key-y2. Seen red, of 2,319: keep every one 3, decide from
memory 4, strip every valid one 13, no slot clause 1, a reported refused
value kept 1; and the D-SINK-20 cases (`R20c (lag host) D-SINK-20: CLI
epgUrl E ...`, `... BADE ...`, `... the slot clause ...`) are among the 23
red on lane-key-y2's code. Is D-SINK-20 closed? As filed, by the
instruments, yes: the session half (the re-carry) by R20c and the restart
half (an entry value seen as new) by R20b. What remains is the patch-only
write KEEPING a valid value the last landed state does not hold, which is
the only copy the round-4 P1 lost, and is the design rather than a
re-carry. Closing the board row is the lead's, after the round-10 lenses.

R20d, BEHAVIOURAL OBSERVERS FOR THE FUNNEL. The ruling: node cases that
DRIVE `writeOwnedEntry`'s decision rather than regex-matching it -- two
consecutive in-app toggles on the lagging host, the second taking effect,
and the add form stamped at submit against at commit -- and a live segment
for the double toggle, each red under the round-9 lens's S1b and S13.
Built: `tests/service-harness.js`, which compiles `Service.qml`'s own root
functions, bindings and `FileView` handlers from the shipping text and runs
them against fakes (`R20d (harness): every Service.qml function and binding
the harness runs compiled from the shipping text`), so `writeOwnedEntry`,
`setShowLogos`, `persistActive`, `settleEntryFlush`, `reconcile`,
`adoptActive`, `addSource`, `startProbe` and `handleProbeExit`,
`updateSource`, `switchSource` and `stateFile`'s `saved` and `saveFailed`
are now driven as they ship rather than mirrored; the cases are `R20d (lag
host)` and `(echo host): two consecutive in-app logo toggles -- the SECOND
takes effect ...` and `... the add form is stamped at SUBMIT ...` both
ways; and key-scenario Y4 (two in-app toggles in a row, nothing between,
the second taken and handed to the host; `hostEntry.storedShowLogos`
through `HarnessLib.storedOwnedValue`, pinned by `qa-lib-test.sh`). Seen
red under the lens's mutants, re-anchored by lane A on the tip with the same
decision: S1b 1 node failure (the lag double toggle), where round 9 read 0,
and live Y4 `got [on1:false/0 off2:false/0 stored:false]`, 86 / 1
(`key-20261012-211919-3462671`), where round 9 read 86 / 0; S13 2 (both
hosts' add-stamp case), where round 9 read 0; S1 1; S3 14. Y4 is green on
`--baseline lane-key-y2` (87 / 0, `key-20261012-211409-3439299`): it
observes the S1b decision, which lane-key-y2 gets right, and the lens's
own `T=toggle2` reads `#2: guide showLogos=False writes 3` on both trees as
its control. The mirrored service-order driver stays, as the wider sequence
model, with its R17-R20 regex bindings; it is no longer the only observer of
the funnel's decisions, and retiring its bindings one family at a time for
the harness is a separate change (lane A's open question).

R20e, DOCS CITE WHAT QML CAN CALL. The ruling: a citation with the `Model.`
prefix names a name `Model.mjs` exports, the ledger checks citations against the
aggregator's public names, seen red, and internal helpers are cited bare
with their part named. Built (75d53e7): `scripts/check-defect-ledger.py`
checks each distinct `Model.*` name cited (245 on lane-key-z1, 251 on
lane-key-z2 with this round's) against the names `Model.mjs` exports and
prints `symbol citations: 245 distinct Model.*
names checked, each against the names Model.mjs exports`, with a waiver list
for the three citations that predated the rule, all in this file, and a
census line. Seen red by lane A: the tree with the waivers emptied, rc 1,
three problems naming copySourceRecord and replaceSource (part
`model/source-records.mjs`) and countFavorites (part `model/browse.mjs`).
This lane re-cites all three bare with their part (D14 above, and round 9's
R19b paragraph), so the waivers are unused: the census line then names them
as unused and to be deleted, which is not red, because the commit that
removes a citation belongs to a lane that may not edit the script, and the
deletion is the next owner of `scripts/check-defect-ledger.py`'s. The same
rule over the helper: `bin/omarchy-iptv`'s docstrings cited
hostPortOf, labelKey and MPV_HANDOFF with the `Model.` prefix, none of them
exported, and now cite hostPortOf and labelKey (`model/sources.mjs`) and MPV_HANDOFF
(`model/mpv.mjs`) bare (3e3acb2).

R20f, FLOORS LEVEL with the committed tree. `scripts/check.sh` reads
`NODE_CHECKS_MIN` 2319 and `PY_TESTS_MIN` 1143 (0d822ba, f9eda77), the
counts on lane-key-z1's tip; `qa-lib-test.sh` 455; key-scenario
`EXPECTED_CHECKS` 86. The merge of `dev` 7c571a9 on lane-key-z2 left them
level: `dev` had levelled its python floor to 1126 for its own tree, and the
merged tree runs 1,143 python tests and 2,319 node checks, measured on the
merge before it was committed.

R20g, F-PERF-2 MEASURED. The ruling: the cold and warm opens by PERF-02's
method on `dev` HEAD and on the tree, interleaved, same cage, load reported,
and whether the chain moved them, with a profile or a bisect over the
y-chain commits if it did. Measured by lane A: the `ipc toggle` round trip
minus the median `ipc widget` round trip, 10,000 generated channels,
interleaved in ONE nested cage per set, the load printed beside every run,
1-minute load 1.8-4.5 (`perf-a.out`, `perf-b.out`, `perf-c.out` in lane A's
scratch, re-read by the documents lane). `dev` (b594b12), 11 runs: cold 159,
159, 161, 163, 165, 165, 167, 169, 170, 176, 178 ms of open work, median
165; warm median 92. lane-key-z1, 11 runs: cold 159, 161, 162, 168, 169,
169, 180, 185, 188, 194, 245, median 169; warm median 92. lane-key-y2, 3
runs: cold 162, 163, 222; warm medians 69-93. The chain does not move the
warm open, and moves the cold median by 4 ms, inside the run-to-run spread;
the cold open is over 150 ms on `dev` itself by this method under the cage,
so F-PERF-2's over-budget reading is not the chain's. lane-key-z1 has a
heavier cold tail, 4 of 11 above `dev`'s maximum of 178, each arriving
singly under a load spike from other cages on the machine; with the medians
unmoved there was no profile and no bisect. Whether the cold open should be
measured below a load of 1 is lane A's question, and the board's.

Rule 15, lane A's searches. R20a, by the shape "a reader or writer that
rebuilds the state document from a whitelist": taught `normalize_state`,
`normalize_source`, `public_state` (the printer), `Model.parseState` and
`Model.cloneState`; cleared `remap_state_file` (edits the raw document),
`init_state_file` (never rewrites an existing file), `Model.addSource` and
`Model.reconcileSources` (build NEW records), `Model.updateSource`'s
replacement and replaceSource (copy whole records); and the key check
replaces the search from here on. R20b, by "session-only memory that decides
freshness across a restart": persisted `reconciledPlaylistUrl` and
`reconciledEpgUrl`; cleared as session-only by design `ownWrite` (the host
publishes fresh at a start), `recentSaves`, `pendingEntryKey` and
`lastSaveText`; `entryMirrorOwed`, R19d's debt, is lost at a restart and the
slot now covers its consequence. R20c, by "a writer that composes from the
publish": `writeOwnedEntry` is the only one (D-LOGO-2); the heal composes
from the publish too, but only when nothing is outstanding, where memory
equals disk. R20d, by "a `Service.qml` decision guarded only by a regex
binding": the functions listed above are now driven; the mirrored driver's
R17-R20 binding flags remain. R20e, by "a prefixed citation naming something QML
cannot call", over every tracked file and not only the ledger's backticked
markdown: the three in this file, the three in the helper, and two outside
any ruling's files and outside the ledger's corpus (not backticked),
barGlyphAlpha in `docs/CONTRAST-RULING.md` and somethingRemoved in
`docs/CLEANUP-PLAN.md`, each written with the prefix, left to their owners.
This lane's own search, over the nine files it owns, by the shape
`(?<![\w.])Model\.[A-Za-z_$][\w$]*` whether backticked or not, against
`Model.mjs`'s exports: 178 hits before, of which 175 are file names
(`Model.mjs`, `Model.js`, `tests/Model.test.js`, `tests/Model.spec.qml`) or a placeholder
letter, and the other three are the three above; 0 after, file names
apart. And for statements round 10 made false, by the shapes "not taught",
"no id yet", "erases", "id remap", "next heal pays", "re-carr", "cannot be
known", "seen now" and "unchanged" beside D-SINK-20: each hit in the nine
files is bracketed where round 10 changed it (the 2.1 rows, 4.3, SR37, the
round-9 R19b, R19c, R19d, R19e and open-list paragraphs here; the matching
places in `ARCHITECTURE.md`, `UX-SOURCES.md`, `UX.md`, `QA-SOURCES.md`,
`QA.md`, the contract and the harness README) and left where it was about
another subject.

Pins on lane-key-z1, each calling the shipping code: 51 `ok   R20` titles
in the node suite -- the 16 shared-fixture value cases, the 9 key-check
titles, the harness self-check, and the R20b, R20c and R20d cases under
both host shapes named above -- and 6 R20a tests in `tests/test_state.py`
(41 in the file) and 2 R20e cases in `tests/test_defect_ledger.py` (47).

Counts, each with where it was measured. lane-key-z1's tip 3e3acb2, lane
A's gate log (rc 0, load 2.35 at the start and 2.85 at the end): node 2,319
/ 0, python 1,143, qml spec 78, `qa-lib-test.sh` 455, the key preflight
11, 754 declarations in 18 parts and 645 names exported from `Model.mjs`,
245 cited names each against the exports with the waiver census `3 listed,
3 in use`, the board 329 rows with 0 disagreements, the release allowlist 31
files with `bin/omarchy-iptv` the largest at 419,526 of 458,752 bytes. An
earlier gate on 0d822ba exited 1 at load 5.3 on one timing test
(`test_10k_entries_parse_and_write_under_one_second`, 1,203 ms) that passed
three times alone. Live, lane A's transcripts under nested headless cages
(harness directories `/run/user/1000/omarchy-iptv-za-<n>`, all removed),
re-read by the documents lane: key-scenario forward on 0d407e5 (the code of
the tip; the later commits touch only tests, `check.sh` and helper
docstrings) 87 passed, 0 failed, 86 lettered checks and the "ran every
check" line (`key-20261012-211001-3410753`, 232.2 s; Y4 `on1:true/1
off2:false/2 stored:false`); `--baseline lane-key-y2` 87 / 0 (`-211409`);
the S1b export 86 / 1, Y4 (`-211919`); `sources-scenario.sh` 66 / 0
(`sources-20261012-212317`), `logo-scenario.sh live` 33 / 0
(`logo-20261012-212345`, on f9eda77), `tls-scenario.sh` in a gles2 cage 48
/ 0 (`tls-20261012-212348`). The two key-mutation patches were not re-run
through `--tree` this round.

NOT observed by a shipped live scenario, said so: R20a, R20b and R20c.
`--baseline lane-key-y2` is green, so no segment of key-scenario goes red
for D-SRC-20, the D-SRC-18 window or D-SINK-20; their live observations are
the round-9 lens's own driver (`r9-child.sh`, in the session scratch, not in
the repository), run under lane A's cage on both trees, with a leak scan of
0 in every run. Their gate-borne observers are the node cases, of which 23
are red on lane-key-y2's code, and the python tests. Nor run live this
round: chno-entry, player, rewind, clip and id-rotate, whose check-tree
preflights ran in the gate.

What this round leaves open, with its owner. The board states of D-SRC-20
(closed by R20a), D-SINK-20 (closed as filed) and D-SRC-18 (settled for the
window R19d left), the lead's, after the round-10 lenses. D-SRC-19, the
service not reloading a helper write, unchanged and open [round 14: re-scoped
by the round-13 live lens to the first session after a fresh install, and
re-armed there by R24c]. The residual of
R20b's riding slot, above, the lead's to give an id or not. Lane A's
readings, for the lead to confirm: the at-start-only held time (R20b), the
refused value kept before the first load (R20c), the helper's
explicit-input route stamping `epgSetAt` (R20a), and the digest slot's
design (`{ digest, at, stripped }`, `at` recorded and decided on by
nothing). The unused waivers in `scripts/check-defect-ledger.py`, to delete.
The two `Model.X` citations outside the ledger's corpus, to their owners.
F-PERF-2's measurement at a quiet load. Retiring the mirrored driver's
regex bindings for the harness. The R13-class residuals round 9 recorded
(RZ `cliP_A > removeActive > cliE`, LF 6 and 4 at length 3) and
`recentSaves`, unchanged [round 15: closed by R25a]. And the documents of this round are
lane-key-z2's, a documents lane that ran nothing live; every live count
above is lane A's, re-read from its transcripts and outputs, and the two
counts over lane-key-y2's code were re-run by this lane.

### D-SINK-19 round 11 rulings (product owner and lead, 2026-10-13; R21, which OVERTURNS R12, R17b, R18d, R19b, R19c, R20b and R20c and narrows R13, R16 and R17a to the migration)

**The owner's decision, 2026-10-13 (the decisions log in `docs/STATUS.md`).**
D-SINK-19 drops the `omarchy bar set` URL route. Ten repair rounds did not
converge -- P1s per round from round 3: 1, 1, 0, 1, 2, 2, 1, 3 -- and every P1
since round 3 was triggered by a URL arriving on the bar entry from the
command line; each fix added state (an input held on the entry, a held input
in the state, set times, a persisted snapshot of consumed inputs, landed-state
keep rules) that the next review broke. The in-app Sources form becomes the
only way to add or change a source. At the first start of the new version the
URLs a 0.13.x install keeps on its bar entry are moved once into the private
state file; after that a `playlistUrl` or `epgUrl` set with `omarchy bar set`
is refused with a message pointing to Sources and removed from `shell.json`.
Round 11 deletes the pending, timing and re-set machinery rather than adding
to it. This is an OVERTURN, not a rewrite: the overturned rulings above keep
their text, each marked where it stands, so a reader comparing this file with
`git show lane-key-z2:docs/ARCHITECTURE-SOURCES.md` finds every earlier word.

**The lead's ruling, R21.**

R21a, ONE MIGRATION. The bar entry's `playlistUrl` and `epgUrl` are read as
INPUT only while the LANDED state does not carry the migration marker. The
marker is `entryMigrated`, a boolean in `state.json` (section 2.1), read
through `Model.entryMigratedOf` (exactly `=== true`) and set through
`Model.withEntryMigrated`, which returns the SAME object when it is already
set. It is one of the keys the helper's `normalize_state` preserves
(`normalize_entry_migrated`, the mirror, `raw is True`), taught on the same
day over the shared fixture `tests/fixtures/state-keys.json`. 0.13.6's helper
and service rebuild the file from the keys they know and drop it, so a
downgrade followed by a re-upgrade runs the migration again over what 0.13.6
wrote to the entry -- the source picked while downgraded is the one that
comes back -- and that is correct, not a leak. The migration adopts exactly
as before round 11 (R1, R4 with an active source, R9-R11), the marker rides
the SAME state write (`Model.adoptActiveSource` with `migrating`), and the
entry is stripped only once that write has landed (R13). While it has not
landed every owned write keeps the retired keys (R13, R14-R16 as they stand).
"Landed" is `Service.landedState`, the state the last LANDED save serialised
or the file as loaded, NEVER memory: memory carries the marker from the
moment the migration runs, and a write that fails leaves the disk without
it.

R21b, AFTER THE MARKER HAS LANDED, NOTHING ON THE ENTRY IS AN INPUT. A
`playlistUrl` or `epgUrl` found on the bar entry is REFUSED: never adopted,
whatever it is -- a valid URL naming a known record, an unknown one, a value
that does not validate, a value wrapped in whitespace; reported ONCE per
value with a message that names Sources and never the value
(`Model.entryInputNotice`, rule 5); and stripped by the next owned write
(`Service.stripEntryInputs`, the patch-only shape, deferred by
`Qt.callLater`). Every owned write -- heal or patch, the key mirror, the logo
toggle, the logo heal -- strips the retired keys unconditionally once the
marker has landed (`Model.retiredInputsToKeep`, which answers every retired
key the entry carries while the marker has not landed and none once it has),
which also ends D-SINK-20's re-carry: the patch-only toggle on the lagging
host keeps nothing, so it cannot write back a value the heal stripped. A
value equal to one this session has already migrated or refused is not
reported again: `Service.entryInputsSeen` is an IN-MEMORY, ordered record by
setting (`Model.entryInputsSeenAfter`; `Model.entryInputSeen` asks "seen at
all", after the marker; `Model.entryInputLast` asks "seen LAST", inside the
migration window; at most `Model.MAX_SEEN_INPUTS` values a setting, the
oldest dropped), nothing persisted, so the lagging host's stale publish of a
stripped value neither re-adopts nor re-reports, and a restart starts it
empty and reports whatever the entry still carries once more.

R21c, a guide URL on the entry at the migration with NO source to attach it
to is reported (`no-source`) and stripped, never held: it never had a
playlist to guide (`Model.adoptActiveSource`'s `noSourceEpg`). The in-app
forms are the only other inputs, and they are sequential, so no time or order
rule exists any more.

R21d, DELETE, do not leave dead. Withdrawn from the model, the service, the
helper and the tests, with their fixtures, harness segments and mutation
patches: `pendingEpg` and its helper preservation; `epgSetAt` and the
latest-by-time rule; the active-move adoption of a pending guide URL; the
add-form supersede rule; the persisted `entryInputs` snapshot;
`patchInputsToKeep`'s landed-state rules beyond "keep while the migration
has not landed". The seventeen `Model.mjs` exports that existed only for
them are gone, and every document in this round cites them WITHOUT the
`Model.` prefix from here on, because the ledger resolves a prefixed citation
against the exports and a withdrawn name is not one: adoptPendingEpg,
applyPendingEpg, entryInputDigest, entryInputRecord, entryInputSeed,
entryInputsAfterMove, entryInputsAfterWrite, entryInputsOf,
entryInputsRecord, epgByTime, epgSetAtOf, epgSnapshotAfter,
patchInputsToKeep, pendingEpgOf, pendingEpgRecord, withEntryInputs and
withPendingEpg. KEPT: the key mirror (D-SINK-19 itself); R1, R9-R11, R13 and
R14-R16 for the migration; R18a's normaliser (`Model.entryInputForm`); R19a
(no skip; `Model.sameOwnWrite` settles the cycle); rule 9 tolerance; R20a's
check that the helper preserves every key the service writes, now with the
marker; R20d's behavioural service harness (`tests/service-harness.js`);
R20e's ledger rule; and the D-SRC-15/16 fixes.

R21e, PINS that call the shipping code, on lane-key-m1. Node (the 93 checks
titled `R21`): the migration on a 0.13.5-shaped install on both host shapes
(`R21e (lag host)` and `(echo host)`: one source, two sources, a CLI-only
config with no `state.json`, an `epgUrl` with no playlist, a failed migration
write then a restart, a failed write and then a second URL in the same
session, a TERM before the write lands, the strip in the same turn the write
lands, a downgrade to 0.13.6 then a re-upgrade); after the marker, a CLI
`playlistUrl` (valid and known, valid and unknown, refused, whitespace-wrapped)
and `epgUrl` (valid, refused, whitespace-wrapped), each set mid-session,
while the shell was down and twice, on both host shapes -- refused, reported
once, gone from the stored entry after at most one owned write; the round-3
to round-10 data-loss sequences reinterpreted under the new contract (round
4's P1 and round 6's C1 at the migration, D-SRC-18 at the migration, round
10's `startre`/`heldre` and `switchtoggle`, the add form's race, D-SINK-20's
re-carry, round 7's P1-B); and the data-loss matrix (`R21e: the data-loss
matrix ...`, 2 operations over 11, both host shapes, a restart after each;
3 with `IPTV_MATRIX_LEN=3`: 2,662 runs) in which a post-migration CLI URL is
a REFUSED input, counted apart and never a loss, and no migration input and
no in-app input is lost. Python: `test_r21a_a_helper_write_keeps_the_migration_marker`,
`test_r21a_an_unmigrated_file_stays_unmigrated_and_no_helper_verb_invents_the_marker`,
`test_r21d_a_guide_url_the_helper_sets_carries_no_set_time` and the
`entryMigrated` cases of the shared state-keys fixture. Live:
`scripts/dev-harness/key-scenario.sh` G1-G5 (the migration marker landing
with the adoption, the strip after it, the REAL v0.13.6 helper dropping the
marker, the re-upgrade migrating again) and X1-X6 (a URL set while the shell
was down, mid-session, again, whitespace-wrapped, the notification sink, the
echoing host), F and H through a migration whose write fails from the start
(`fixtures/disk-gone-after-init.py`), and U, K, Z, A, Y2, Y3, Q and V moved to
the new contract.

**The refusal message as shipped** (`Model.entryInputNotice(name, reason)`;
a desktop notification through `omarchy-notification-send` with app name
`IPTV`, urgency `normal`, the alert glyph and replace id 74016, so a second
report replaces the first on screen; the same body on the console as
`omarchy-iptv: <body>`; `name` is the setting's name, and anything that is not
one of the two reads `A URL setting`, so no caller can route a value in):

| Reason | Title | Body |
|---|---|---|
| `retired` (after the marker) | `Bar setting ignored` | `<setting> is no longer read from the bar settings and was removed. Add or switch sources in the guide's Sources screen.` |
| `no-source` (R21c, at the migration) | `Bar setting removed` | `epgUrl was removed from the bar settings: no source was set up for it to guide. Add the source with its EPG URL in the guide's Sources screen.` |
| `invalid` (a migration value that does not validate) | `Bar setting removed` | `<setting> in the bar settings was not a usable URL and was removed. Add or edit sources in the guide's Sources screen.` |

The guide itself shows nothing for a refusal (the active source and the
channel list are untouched); an `invalid` migration value with no source to
fall back on still reaches the guide's error state through D16 as before.
The guide's unconfigured state and first-run form no longer offer an
`omarchy bar set` command to copy (`unconfiguredCommand`, `unconfiguredEpg`,
`firstRunTerminal`, `copyCommand` and its `Copied` transient are deleted);
`UX.md` 4.4 and `UX-SOURCES.md` 3.1.1 carry the shipped text.

**What each overturned ruling became** (lane A's deletion inventory,
re-read against the tree by this lane):

- R12 (an EPG input never stripped unadopted, kept on the entry): OVERTURNED
  by R21c. epgSnapshotAfter and its fixture `snapshot` section, and
  adoptActiveSource's epgConsumed / epgEcho rule, deleted. "Never stripped
  unadopted" survives only inside the migration window, as R21a's keep.
- R17b (the active move adopts a pending guide URL): OVERTURNED; there is no
  pending guide URL. adoptPendingEpg, `Service.adoptPendingEpgOnto` and their
  calls in `switchSource` and the probe commit deleted. R17a's keep (an owned
  write strips a retired input only when it is consumed) is NARROWED to R21a:
  `Model.retiredInputsToKeep(entry, landed)` keeps every retired key until
  the marker lands and none after; the `consumed` snapshot argument is gone.
- R18d (the add form supersedes a pending CLI guide URL): OVERTURNED (already
  replaced by R19c in round 9); its driver cases deleted.
- R19b (a pending guide URL lives in the state as `pendingEpg`): OVERTURNED
  by R21c. pendingEpgRecord, pendingEpgOf, withPendingEpg, the helper's
  `normalize_pending_epg` and `public_state.pendingEpg`, the `cloneState` /
  `parseState` carry and `Model.activeEpgUrlOf`'s held fallback deleted;
  `Model.activeEpgUrlOf` is now the record's own guide URL and nothing else.
- R19c (the latest explicit input wins, by time): OVERTURNED; the in-app
  forms are sequential. `epgSetAt` deleted everywhere, with epgSetAtOf,
  epgByTime and applyPendingEpg, the helper's stamps and `now_ms`.
- R20b (the consumed snapshot persisted as `entryInputs`): OVERTURNED by
  R21b's in-memory record. entryInputDigest, entryInputRecord,
  entryInputsRecord, entryInputsOf, withEntryInputs, entryInputSeed,
  entryInputsAfterMove and entryInputsAfterWrite, the helper's
  `normalize_entry_input(s)` and `ENTRY_INPUT_SLOTS`, and the service's
  `reconciledPlaylistUrl` / `reconciledEpgUrl` deleted.
- R20c (the patch-only write keeps what the landed state does not hold):
  OVERTURNED beyond "keep while the migration has not landed".
  patchInputsToKeep and `writeOwnedEntry`'s `keepRetired` branch deleted (the
  parameter is `patchOnly` and gates only the owed-mirror reset).
- KEPT and why: `Service.landedState`, because R21a asks it for the marker;
  `hostEntryForm`, `entryWriteRecord` and `entryWriteNeeded`,
  R19a's retired estimate, outside R21d's list and still cited [round 12,
  2026-10-13: deleted by R22e, the round-12 rulings]; the
  `spikes/key-mutations` patches `d3-save-parked` and `r14-no-return` (R9 and
  R14, which `qa-lib-test.sh` proves still apply); the service-order driver's R13
  sequences, re-run on `Service.qml`'s own functions through
  `tests/service-harness.js` (the regex-mirrored driver that modelled the
  withdrawn rules is deleted).

**Consequences for the board, the lead's to record.** D-SRC-20 (the helper
erasing `pendingEpg` and `epgSetAt`) has no keys left to erase. D-SINK-20
ends at the marker: the patch keeps nothing (pinned, `R21e (...) a refused
value is stripped by the logo toggle's patch-only write too`). D-SRC-18
survives only inside the migration window and is pinned there (`R21e (...)
D-SRC-18 at the migration`). D-SRC-17 is unchanged (R18a's normaliser is
kept).

**Counts, lane-key-m1's tip 7d52e16 (lane A's report, the gate re-run by
this lane on its own tip below).** Node 2,261 checks (2,319 at the merged
`af1e7d6`: 180 titles deleted or renamed, 121 added; `NODE_CHECKS_MIN` lowered
with the reason in `scripts/check.sh`); python 1,153; `qa-lib-test.sh` 472;
the key preflight 11; the text format guard 58 blocks (61 before: the three
deleted copy Texts); a11y 35; the ledger's withdrawn-symbol census `17
listed, 17 in use` on lane-key-m1 and, after this documents round, `17
listed, 0 in use` with all seventeen named as unused, to delete. Live, under
nested headless cages on a private D-Bus with no service directories
(CLAUDE.md working-in-parallel 6b): key-scenario 98 / 0 forward
(`key-20261013-050330-58599`, `key-20261013-054734-223578`), 68 / 30 on
`--baseline lane-key-z2` (`key-20261013-050726-82628`: G1, G2, G5, F4,
U1-U7, K1-K3, Z1-Z3, A1, Y2, Y3, Q1, Q2, V1, H1, X1-X6); sources-scenario
66 / 0 (`sources-20261013-055250-250025`); logo-scenario 33 / 0. The adapted
round-10 data-loss lens (LEN 2, 23 operations, 5 initial states, both host
shapes): 11,040 runs a host shape, 0 refused-adopted, unreported, linger,
lost-marker or loop; on lane-key-z2 the migrated slice reads 461 problems
of 1,104 runs, here 0.

**Residuals, stated rather than rounded to zero, each the lead's to rule
on.** (1) Inside the migration window only, a re-set of the value the entry
already carries is a no-op: it cannot be told from the host's stale publish
of it, the entry not changing. The window normally closes at the first state
write that lands; a failing disk keeps it open (the lens: 10 runs a host
shape, all with saves held). (2) If the host cannot be written as the
migration's write lands, a URL is left behind a landed marker, and the next
start reports it once as refused although a record holds it (pinned); one
spurious report against stripping a value a record holds silently. (3) If the
migration's write failed, a guide URL reported `no-source` is still on the
entry (R21a keeps everything until the marker lands), and a `playlistUrl` set
before the next start lands it on the new playlist (the lens's
`EPG:OLD:init`, 1 run); R21c's "reported and stripped" waits for the landing.
(4) The channel is a notification and a console line; the guide shows
nothing. (5) `manifest.json` still declares `playlistUrl` and `epgUrl` as
settings with labels [corrected 2026-10-14, D-DOC-9: a parenthesis here said
`omarchy bar set` "therefore still offers them"; it does not depend on the
declaration -- `cmd_set` in `/usr/share/omarchy/bin/omarchy-bar` consults
none and the host stores any key (the round-13 manifest measurement)], and
the guide's fetch-failure line still ends `check playlistUrl`
(`Guide.qml` `errorCheck`); both are code, outside this documents lane, and
are raised to the lead rather than changed here. [Round 12, 2026-10-13: the
hint now ends `check the source in Sources` (R22c, lane-key-n1 74f9a01); the
manifest declarations stand, open item 5 of the round-12 rulings.]

Rule 15, this lane's searches over the nine files it owns. By the shape "an
instruction to set a source URL from the command line" (`bar set` beside
`playlistUrl` or `epgUrl`, and the prose "from a terminal", "on the command
line", "CLI"): every hit is either rewritten for R21 (the README, the UX
wireframes and copy tables, the settings tables) or a historical ruling,
measurement or test row left as written and marked. By the shape "a document
naming the withdrawn machinery as current" (`pendingEpg`, `epgSetAt`,
`entryInputs`, `held`, `pending`, `set last`, `later wins`, `fingerprint`,
`consumed`): each current-tense hit is marked or rewritten. By the shape "a
prefixed citation of a withdrawn export": every one de-prefixed. And by the
shape "a version number that names the last build to name the source by
URL": the README said 0.13.5 where the last such release is 0.13.6
(ca5a3a5), fixed at each place.

### D-SINK-19 round 12 rulings (lead, 2026-10-13; R22, on top of R1-R21, which stand)

**What the round-11 lenses found, on lane-key-m2 (12429dc).** Both lenses
read 0 problems under R21's own oracle -- the data-loss lens over about
71,000 sequences a host shape (10,108 at length 2, 61,516 at length 3) run
through `Service.qml`'s own functions, the live lens over the real upgrade
from a 0.13.6 install -- and neither matrix ever started from a
`state.json` that fails to load. That is where the P1 was.

- P1-A (the data-loss lens, live under a nested headless cage on a private
  D-Bus, both host shapes). A MIGRATED install whose `state.json` could not
  be read when the shell started (chmod 0000 while it was down) lost every
  record. `stateFile.onLoadFailed` called `applyUserState("")`; the empty
  stand-in carries no marker, so reconcile migrated it and
  `Model.withEntryMigrated` marked it changed; the save parked behind
  `dirsReady`; the helper's start-up `state init` restored the mode, which
  raised the reload carrying the REAL text; `Model.reloadDisposition`
  ignored that reload because a save was parked (R9); and the parked save
  wrote an empty state plus the marker over the real file. The marker then
  stopped any later migration, so the loss was permanent: `RESULT file: THE
  RECORDS ARE GONE (records=0, were 2)` on the lagging and the echoing host
  alike, where lane-key-z2 and dev 4740a50 (0.13.6) kept both records over
  the same sequence. A file that does not parse took the same road. Its
  sibling, OLDER than R21: a state DIRECTORY chmod 0000 lost the records on
  lane-key-z2 too, through the cache layout's save -- which the node harness
  could not see, because it stubbed `startCacheLayout` as "the layout is
  current" (rule 10).
- P1-B (the live lens, a screenshot inside the cage): the guide's
  fetch-failure line ended `check playlistUrl` (`Guide.qml` `errorCheck`),
  sending a user whose provider is down to the one setting R21 refuses;
  `UX.md` 4.6 and 6.3 and `QA.md` TC-CFG-02 and US1 step 4 prescribed that
  text, so the QA plan would have graded it a pass.
- P2 (both lenses): the ledger's 17 withdrawn-symbol and 3
  unexported-citation waivers were all unused and still honoured, so a NEW
  stale citation in a waived document passed the gate.
- P3: the helper's `state source update --help` still said the running
  shell's `playlistUrl` / `epgUrl` setting owns the active source's URL;
  key-scenario.sh's round-7-to-10 header described the pending guide URL's
  adoption as live and cited a withdrawn export; its lane-key-z2 baseline
  footer miscounted which reds were NOFIELD-only; and hostEntryForm,
  entryWriteRecord and entryWriteNeeded were still exported with no caller.

**The lead's ruling, R22.**

R22a, A STATE THAT DID NOT LOAD IS NEVER WRITTEN. Only "the file does not
exist" means a fresh install (and lets the migration run). Any other load
failure -- permission, not a regular file, an I/O error -- and any text that
does not parse as a state, puts the service in a no-write mode for the
session: every state write is refused, the migration does not run and no
marker is set, the entry is left exactly as it is (it may hold the only copy
of an input), and the user is told once, by one model function that names
the file and what to do and never a URL. A later successful load lifts it.
Measure what Quickshell's FileView reports for each case before deciding how
to tell them apart; the helper's `state init` must never rewrite a file it
could not parse.

R22b, RULE 15 AS A LIST. Every writer of `state.json`, in the service and in
the helper, obeys R22a, each listed with how; the node harness drives the
load failures through the REAL `startCacheLayout`; the unreadable-directory
sibling is measured on dev (0.13.6, shipped) as well as on the tree.

R22c, the guide's fetch-failure hint points to Sources, not to a setting,
and no shipped string anywhere tells the user to set `playlistUrl` or
`epgUrl`, proved by a search of every shipped file.

R22d, an unused ledger waiver is itself a failure; the unused ones go.

R22e, the three exports R19a retired with no caller are deleted, and the
documents cite them bare with their part, or not at all.

R22f, the P3s.

**What Quickshell's FileView reports, measured before anything was decided
(lane-key-n1, lane A, 2026-10-13).** quickshell 0.3.1-1 and Qt 6.11.2 as
installed (Arch), one FileView per case, under a nested headless cage on a
private D-Bus with HOME and the XDG directories redirected to a scratch
tree. The probe and its log (`lane-n1/fvprobe/run.sh`, `qs.log`) are in the
session's scratch directory, not in this tree; this lane read the log. The
error argument is `qs::io::FileViewError`
(`/usr/lib/qt6/qml/Quickshell/Io/quickshell-io.qmltypes`): Success 0,
Unknown 1, FileNotFound 2, PermissionDenied 3, NotAFile 4.

| What is at the path | What the FileView reports |
|---|---|
| nothing: no file, no parent directory, or a dangling symlink | `loadFailed` 2, FileNotFound |
| a file with mode 0000, or 0200 | `loadFailed` 3, PermissionDenied |
| a directory, or a FIFO | `loadFailed` 4, NotAFile |
| a file inside a directory of mode 0000, or of mode 0600 | `loadFailed` 2, FileNotFound -- exactly what a fresh install reports |
| an empty file | `loaded`, text of length 0 |
| a file of garbage | `loaded`, the garbage |

Once the modes were put back: the 0000 file raised `fileChanged` and
loaded; a missing file, once created, raised `fileChanged` and loaded; the
0000 DIRECTORY raised no `fileChanged` at all (`inotify_add_watch ...
failed: (Permission denied)` in the log) until an explicit `reload()`, after
which it loaded and the watch worked. So the FileView alone cannot tell a
fresh install from a directory it cannot search, and nothing it does later
tells it either. The witness is the helper: `state init` now `lstat()`s the
path BEFORE it repairs any mode (`state_path_found` in `bin/omarchy-iptv`)
and its reply carries `found` -- `absent` (ENOENT, a missing parent
included), `file` (a regular file, or a symlink to one), `other` (a
directory, a FIFO, a dangling symlink) or `unreadable` (the lstat itself
failed: the directory cannot be searched) [round 13, R23b: for a FIFO the
init never got that far on this tree -- it read the file BEFORE the lstat
and blocked in `open()` until killed (both round-12 lenses, measured; 0.13.6
the same). Since lane-key-p1 0fbdd47 the lstat comes first and every read
goes through a non-blocking opener, so a FIFO or a socket answers `other` at
once (`StateNeverBlocksTest`)]. `tests/test_state.py`
`StateNeverWrittenUnreadTest` pins `found` for an absent file, a 0000 file,
a 0000 directory, a directory at the path and a dangling symlink against the
real helper run as a subprocess. The table above joins the service to
Quickshell by NUMBER, so the node suite reads the installed qmltypes and goes
red if the enum's order moves (`R22a: Model.STATE_LOAD_ERRORS names
FileViewError's values by their position in the installed Quickshell's
enum`; rule 13).

**What the tree does (lane-key-n1: the helper ec7d00f, the service and model
16a3bc9, the probe exit 4fdb37c).**

- Every load of `state.json` arrives at `Service.stateLoadArrived`, from
  `onLoaded` and `onLoadFailed` alike, and is classified before anything is
  applied. `Model.stateLoadKind` answers `loaded` (the text parses as a JSON
  object), `unparsed` (read, and not one -- an empty file included, since
  nothing the plugin writes is empty), `absent` (2), `permission` (3),
  `not-a-file` (4) or `io-error` (1, and any number the table does not know:
  never `absent` by default). Only `loaded` reaches `applyUserState`, and it
  is what lifts the no-write mode.
- Any other kind goes to `Model.stateLoadDecision({ kind, loadedBefore,
  initFound, retried })`: `apply`; `fresh` -- FileNotFound AND the init's
  `found` is `absent`, the one load failure that is an empty state the
  migration may run on; `wait` -- the start-up init has not answered, so
  nothing is applied or written; `retry` -- one `reload()` after the init,
  because the init restores the 0000 modes it finds (the file to 0600, the
  directory to 0700), which is how both of the lens's cases now recover with
  nothing reported; `block`. Mid-session (`loadedBefore`) a load that is not
  a state blocks at once and memory stands: a reload never replaces memory
  with a state that did not load.
- `Model.stateInitFound(stdout, exitCode)` reads the init's reply: `absent`
  only for the init's own `absent`; `present` for `file`, `other` or
  `unreadable`; `unknown` for a failed exit, no reply, or a helper that
  predates the field. A FileNotFound whose witness is `unknown` is NOT a
  fresh install: it is re-read once and then blocks (reason `absent`), and a
  FileNotFound the init contradicts blocks as `absent-unconfirmed`.
- The no-write mode is `Service.stateWriteBlocked`: `""` while writes are
  allowed, else the reason. `saveState` asks `Model.stateWriteGate({
  blocked, loaded, dirsReady })` before anything else: `refuse` in the mode
  (counted in `stateWritesRefused`, which the harness reads); `park` before
  any state has loaded or before the directories are ready -- before R22a a
  save made with the directories ready and the load still outstanding wrote
  the empty default over the file; `write` otherwise. In the mode no owned
  bar-entry write is made (`writeOwnedEntry` returns at its top,
  `Model.ownedWriteMode` answers `none`, `Model.entryFlushDisposition` drops a
  held mirror with reason `state-unreadable`); reconcile returns at once, so
  the migration does not run, nothing is reported and nothing is stripped;
  `sourcesReady` and `removeSource` answer `state_unreadable`; and a probe
  that ENDS in the mode, having started before it, records nothing (added in
  4fdb37c, after a surviving mutation found the probe committing in memory
  and reporting success). The user is told once per episode
  (`stateBlockTold`); a load that IS a state lifts the mode
  (`liftStateBlock`, one console line naming the reason, never a path's
  contents) and re-arms the notice for a later episode [round 13, R23a: no
  check saw that re-arm until the round-12 data-loss lens deleted it (0 of
  2,354 node failures); it is now pinned in node and observed live by
  key-scenario B9].
- The helper's half. `state init` never rewrites a file that exists: the
  create is `O_EXCL` and the existing branch only chmods [round 13, R23d:
  and only a regular file; it used to chmod whatever was there, a directory
  included], so a state it
  could not parse is left byte for byte -- pinned over garbage, an empty
  file, `[1,2]`, non-text and a 0000 file, by bytes, mtime, ctime and inode
  (`test_init_never_rewrites_a_file_it_could_not_parse`). Every other `state`
  verb, the read-only `show` and `source list` included, reads through
  `read_state_strict`, which answers the empty default ONLY for a file that
  does not exist and otherwise refuses -- exit 1, code `state_unreadable`,
  nothing written.

Lane A's readings where R22a is silent, recorded as built and raised to the
lead to confirm rather than settled here [CONFIRMED by the lead on
2026-10-13 and settled from that date; the round-13 rulings below]: an EMPTY `state.json` counts as
"does not parse" and blocks; a FileNotFound in the middle of a session (the
file deleted, or its directory made unreadable) blocks rather than counting
as fresh, because the FileView reports the unreadable directory the same
way; and a block at a start gets one re-read after the init, so a 0000 file
or a 0000 directory -- the lens's two cases -- recovers silently. One change
a hand-run CLI user will see: `state show` and `state source list` over a
file that does not parse now exit 1 with `state_unreadable`, where they used
to print an empty state.

**The user-facing copy as shipped** [round 17, 2026-10-20, R27e: the
title, the body's second sentence and the three link `<fix>`es below are
round 17's, and `read-timeout` is R27a's; `tests/fixtures/state-notices.json`
holds every sentence verbatim and node pins the model to it both ways]
[round 18, 2026-10-20, R28e and R28a: the body's second sentence is now
one of two, and `read-timeout` is withdrawn -- below] [round 19,
2026-10-20, R29a: and stays withdrawn; nothing else in this table moves]
(`Model.stateUnreadableNotice(reason,
path, midSession)` in model/state.mjs; a desktop notification through
`omarchy-notification-send` with app name `IPTV`, urgency `critical`, the
alert glyph and replace id 74017, `NOTIFY_IDS.stateUnreadable`; the same body
on the console as `omarchy-iptv: <title>: <body>`, R27e). The title is `Saved sources not
loaded` for a block that begins at a start and `Saving has stopped` for one
that begins after a state loaded (R27e). The body is `<path> <what>.
<unsaved> <fix>`, where `<unsaved>` is, at a start, `Sources, favorites and
settings changed now are not kept.` (`STATE_BLOCK_UNSAVED_START`) and, for a
block that begins after a state loaded, `Favorites and other changes made
now are held in this session only: the next such change made here saves
them if it finds the file again, but they are dropped if the file comes
back by itself first, if a source change is what finds it, or if the shell
is stopped.` (`STATE_BLOCK_UNSAVED`; R28e). Until R27e both read `Nothing
is saved until it can be read, so sources, favorites and settings changed
now are not kept.`; from R27e until R28e both read `Sources, favorites and
settings changed now are not saved until the file can be read again.`,
which named the one way back on which a mid-session change is kept and
none of the three on which it is dropped. `<path>` is
`<stateDir>/state.json` (on a default install
`~/.local/state/omarchy-iptv/state.json`, spelled out in full) and the
sentence is composed from the reason and the path alone:

| Reason | `<what>` | `<fix>` |
|---|---|---|
| `permission` | `is not readable (permission denied)` | `Make it readable with chmod 600 on that file, then run omarchy restart shell.` |
| `not-a-file` | `is not a regular file` | `Move whatever is at that path aside, then run omarchy restart shell.` |
| `unparsed` | `is not a valid state file` | `Restore it from a backup, or move it aside to start with no sources, then run omarchy restart shell.` |
| `absent-unconfirmed` (at a start: the FileView found nothing and the helper found something) [round 14, R24b: until then `absent` shared this row] | `could not be found, or its folder could not be read` | `Make the folder readable with chmod 700, then run omarchy restart shell.` |
| `absent` (mid-session; round 14, R24b: its own `<fix>`, because the helper is not asked mid-session and the FileView reports a broken symlink and an unreadable folder alike; round 17, R27e, D-SRC-50: the link pointed BACK, first) | `could not be found, or its folder could not be read` | `If it is a symbolic link, point it back at the folder or file that holds your state; otherwise make the folder readable with chmod 700. Then run omarchy restart shell.` |
| `link` (round 14, R24b: the helper's init found a symlink whose target is missing or is not a regular file; round 17, R27e) | `is a symbolic link whose target is missing or is not a regular file` | `Point it back at the file that holds your state, or move the link aside, then run omarchy restart shell.` |
| `not-a-dir` (round 14, R24b: the helper's init found something that is not a folder where the state folder, or one above it, should be; `<path>` is then the FOLDER's) | `is not a folder (a file is at that path, or at one above it)` | `Move whatever is at that path aside, then run omarchy restart shell.` |
| `folder-link` (round 15, R25c, D-SRC-32: the helper's init found a symbolic link at the state folder, or at a folder above it, that dangles or leads to something that is not a folder; `<path>` is then the FOLDER's; round 17, R27e) | `is a symbolic link whose target is missing or is not a folder (or a folder above it is)` | `Point it back at the folder that holds your state, or move the link aside, then run omarchy restart shell.` |
| `io-error`, or anything else | `could not be read` | `Check the file and its folder, then run omarchy restart shell.` |
| `init-timeout` (round 13, R23c: the start-up `state init` did not answer within 15 s and was stopped) | `could not be checked: the start-up check did not answer and was stopped` | `Make sure a regular file, or nothing, is at that path, then run omarchy restart shell.` |
| ~~`read-timeout`~~ (round 17, R27a, D-SINK-22 window c: the read before a save did not answer within 2 s, twice; always mid-session). **WITHDRAWN 2026-10-20 (round 18, R28a): a read that does not answer is no block; the save stays held and the file is read again (`stateReadStalledNotice`, the round-18 rulings) [round 19, R29a: that hold and notice are withdrawn too, and the reason stays withdrawn -- a read with no load within 2 s lets its save be written without it, as on 0.14.2]. The reason no longer exists, and a load failure the stalled read finally answers with blocks under that load's own row** | ~~`did not answer when it was read before a save (twice, 2 seconds each)`~~ | ~~`The next change made here reads it again, and saving resumes if it answers. If it keeps stopping, check the disk or folder that holds it, then run omarchy restart shell.`~~ |

A source call refused in the mode answers code `state_unreadable` with
`state.json could not be read · nothing is saved until it can be`
(`Model.sourceErrorMessage`; the middle dot is `Model.SEP`). The helper's
refusal is one of `state.json could not be read (<strerror>); nothing was
written`, `state.json is not UTF-8 text; nothing was written` and `state.json
is not a valid state file; nothing was written` [round 13, R23b: and `state.json
is not a regular file; nothing was written` for a directory, a FIFO or a
socket at the path]. `omarchy restart shell` is
the Omarchy CLI's own verb (`omarchy restart --help` lists it on this
machine, read 2026-10-13). `UX-SOURCES.md` 5.10 is what the user sees.

**R22b, every writer of `state.json`, re-read against lane-key-n1 by this
lane.** The service writes the file in exactly one place, the
`stateFile.setText` inside `saveState`, behind the gate above, and
`saveState` has 19 call sites: `play` (the session and the recents),
`toggleFavorite`, `toggleHiddenGroup`, `saveSearch`, `forgetSearch`,
`removeRecent`, `updateSource`, `removeSource`, `switchSource` (the three
source verbs are also refused up front with `state_unreadable`),
`adoptIdScheme` (D-ID-3), `applyUserState`'s replay of the session record,
`adoptSourceStats`, `noteSessionOutcome`, `persistActive` (the D-SRC-15/16
key-mirror plan, whose held mirror `Model.entryFlushDisposition` drops in the
mode), `handleProbeExit` (the add's commit, refused at the exit since
4fdb37c), `adoptActive` (reconcile's migration, which does not run in the
mode), `startCacheLayout` (it runs only after a state has been applied, and
its save goes through the gate), `onMaxRecentsChanged`, and `stateInitProc`'s
exit flush of a parked save. The owned bar-entry writers -- `writeActive`,
the logo patch and heal, `stripEntryInputs` -- all reach the host through
`writeOwnedEntry`, which refuses at its top. In the helper, the writers are
`state favorite add` / `remove`, `clear-recents`, `source add` / `update` /
`remove` (all through `read_state_strict`), `state init` (`O_EXCL`, chmod
only) and the `playlist --state-dir` D-ID-1 remap (`remap_state_file`,
which only ever wrote a dict it had read and is now pinned:
`test_the_d_id_1_remap_writes_nothing_over_a_file_it_could_not_parse`). The
node harness (`tests/service-harness.js`) delivers each load through
`stateFile`'s OWN handlers with the measured error numbers, models the
init's reply and its mode repair as `tests/test_state.py` pins the real
helper doing them, and RUNS `startCacheLayout`, `queueCacheJob` and
`runNextCacheJob` (rule 10; `schedulePrune` stays stubbed and writes no
state).

**R22c-R22f, what changed.** R22c: `errorCheck` is `check the source in
Sources` (74f9a01), the guide publishes what its empty state draws
(`emptyTitleText`, `emptyProseText`) [round 13, R23h: it published the
empty state's copy even while that state was hidden behind the first-run
form, which draws other words; since lane-key-p1 418e01e it publishes what
is DRAWN] and the harness's `state` verb carries
them with the copy's `errorCheck`, and `tests/test_shipped_copy.py` searches
every string literal in every allowlisted code file for an instruction to set
either key (on lane-key-m2 it named the guide's hint and the helper's
`--epg-url` help; on lane-key-n1 nothing). R22d (dab2b56): an unused waiver
is a failure that names it, and the twenty went. R22e (dab2b56): the three
functions are deleted from model/settings.mjs and from `Model.mjs` and
pinned absent (`R22e: hostEntryForm, entryWriteRecord and entryWriteNeeded
are gone ...`). The documents cite them bare from this round, with ONE
exception: the three prefixed citations in this file's reducer-table row for
them (section 3.5, marked there) are the last uses of the ledger's three
R22e waivers, and removing them without deleting those waivers in the same
commit turns the ledger red (R22d). `scripts/check-defect-ledger.py` is not
a documents-lane file, so that last step -- three citations de-prefixed and
three waiver entries deleted, together -- is the lead's to make; it was run
green in a throwaway export by this lane. R22f: the helper's `--url` and
`--epg-url` help, its run-time warning and the comment above them now say
what D-SRC-19 measured (a running shell does not re-read the file after a
helper write, so its next save wins) [round 13: lane A's R23g measurement
did NOT reproduce that -- the real `Service.qml` applied a helper rename as
`file-newer`, idle and under load -- and the round-12 live lens's `rename.out`
did; the disagreement is the round-13 rulings' decision request 1, and the
help text is unchanged until it is decided] [round 14: decided by
measurement -- the variable was the state directory at the first load --
and the help text, the warning and the docstring now say a running shell
re-reads the file and keeps the write (R24c)]; key-scenario.sh's round-7 and round-9
header paragraphs are marked withdrawn; its baseline footer counts EIGHT
NOFIELD-only reds on lane-key-z2 (F4, U2, K2, K3, Q2, V1, Y2, Z3), not seven.

**The shipped release, said plainly.** 0.13.6 (dev 4740a50) LOSES records
through an unreadable state directory: measured live by lane A under a
nested cage on a private bus, a migrated source A plus a source B added in
the app, the state directory chmod 0000 while the shell was down -- after
the start `state.json` held one record, and still one after a second start.
B was gone with everything else in the file; A survived only because 0.13.6
re-adopts it from the URL its bar entry still carries. The unreadable-FILE
variant survives on 0.13.6, as the round-11 lens measured. Separately, the
shipped helper's `state favorite add` over a truncated `state.json` and over
a 0000 one exits 0 and leaves an empty state plus that one favourite: lane A
measured it, and this lane re-measured it on 2026-10-13 from `git show
dev:bin/omarchy-iptv` in a scratch state directory (a record with a
credentialed URL and the favourite `t:keep`; afterwards `sources` 0 and
`favorites ['t:x']`, exit 0, in both cases), while the lane-key-n1 helper
refused both with `state_unreadable`, exit 1, the truncated file byte for
byte as it was and the 0000 file's record and favourite intact.

**Counts, lane-key-n1's tip 6172d8a (lane A's report; the gate re-run by
this lane on its own tip).** Node 2,354 checks (2,261 before: 86 harness
pins, 6 model unit pins, 1 R22e absence pin); python 1,170 (1,153 before: 12
in test_state, 3 test_shipped_copy, 2 test_defect_ledger); `qa-lib-test.sh`
472; the key preflight 11; the key scenario's live floor 97 -> 105 (B1-B8);
the text format guard 58; a11y 35; qml spec 78. The ledger: unexported-
citation waivers `0 listed, 0 in use`, withdrawn-symbol `3 listed, 3 in use`.
Live, every run under a nested headless cage on a private D-Bus with no
service directories (lane A, transcripts in its scratch directory):
key-scenario 106 / 0 forward (`key-20261013-161816-835970`; B1 `records:2
active:<KA> marker:true mode:600 told:0`, B3 `records:2 layout:2 dir:700
found:present`, B5 `file:same blocked:unparsed add:state_unreadable
switch:state_unreadable told:1 path:1 urls:0`, B6 `keys:same writes:0`, B7
`blocked: switch:true file:<KC>`, B8 `kind:error sources:yes retired:no`)
and 97 / 9 on `--baseline lane-key-m2` (`key-20261013-162220-859113`: B1-B8,
and N1 for its new field alone, `found:NOFIELD`); sources-scenario 66 / 0;
logo-scenario 33 / 0. Mutation: every new check was seen red (17 node
mutants and 4 python, one at a time; three that survived the first pass --
the reconcile gate, the `writeOwnedEntry` gate, the once-per-episode notice
-- got pins in 4fdb37c and then read 4, 2 and 2). Against lane-key-m2 under
the new harness the node suite reads 86 failures, exactly the 86 R22 harness
pins, with every pre-existing check green there, so the double is not more
forgiving than the code it replaced (rule 10). The round-11 lens's own R21
matrix (`rk11.js` at length 2, the real v0.13.6 helper for the downgrade)
reads the same 65 problems a host shape on this tree as on lane-key-m2, all
the pre-existing D-SRC-19 class, and 0 of every other class.

**Open for the lead (not defects; the board's ids are the lead's to
assign).** [Round 13: (2) is done (R23i, lane-key-p2 fbb61f8); (3) is
confirmed by the lead; (4) is decided by R23e, the guide's own no-write
surface; (5) is measured and still the lead's (the round-13 rulings). (1)
stands.] (1) Rule 13: the 0.13.6 losses above -- the unreadable-directory
start, and the helper verbs writing over a state they could not read --
need `D-` ids and rows on `docs/STATUS.md`, which no lane this round owns;
so do the cache-file siblings of the same shape (the helper's `failed.json`
and status writers read tolerantly and regenerate by design, holding no user
data), if the lead wants them recorded. (2) The last R22e step (above):
whose file `scripts/check-defect-ledger.py` is. Until it is made, the
`entryWriteNeeded` waiver still names four documents where only this one
cites it, so a new prefixed citation in `ARCHITECTURE.md`, the contract or
`QA.md` would pass -- the R22d hazard in miniature. (3) Lane A's three
readings above, and the CLI behaviour change. (4) A no-write START leaves
`stateLoaded` false, so the guide opens on the first-run form whose submit is
refused; the notification is the only place that says why. Whether the
guide gets its own surface is a UX decision (`UX-SOURCES.md` 5.10). (5)
`manifest.json` still declares `playlistUrl` and `epgUrl` with labels
(round 11's residual 5, the half R22c did not reach; R22c's search covers
string literals in code, and the manifest's labels describe the settings
rather than instruct anyone to set them).

Rule 15, this lane's searches over the nine documents it owns. By the shape
"a failed or unparsable state described as an empty state that is then
written": `QA.md` TC-FAV-09, US5 step 7 and the `tests/test_state.py`
inventory row, and `QA-SOURCES.md` SRC-MIG-08, SRC-HELP-04, SRC-CLI-07 and
the fixture note, all amended to the no-write mode; nothing in the README,
the UX documents or the contract said it. By the shape "the start-up
sequence or the load path described as `onLoaded -> applyUserState` with
`onLoadFailed` as an empty state": section 4.4 step 2 here and
`ARCHITECTURE.md` section 5 and R9, amended; the contract's FileView section
gains the load-failure table. By the shape "a document that says the running
shell picks up a helper `state` write" (R22f's, applied to documents): the
R9 lists here (4.4 step 2) and in `ARCHITECTURE.md` say `apply` covers "a
CLI `state ...` write with nothing of ours outstanding", which D-SRC-19
measured never arrives; both are bracketed [round 14: the brackets are
withdrawn in turn -- it arrives, in the first session after an install too
since R24c]. By the shape "the fetch-failure
hint as `check playlistUrl`": `UX.md` 4.6 and 6.3, `QA.md` TC-CFG-02 and US1
step 4, and this file's round-11 residual 5, amended; the `docs/QA-RESULTS.md`
and `docs/STATUS.md` hits are records of runs that read the old text and are
not this lane's files. By the shape "a prefixed citation of an R22e name":
every one de-prefixed but the three named above; the quoted titles of the
deleted R18b tests (round-8 rows here and in `QA-SOURCES.md` SRC-MIG-26) are
quotations of names that no longer run, and the ledger does not read them as
citations, so they are left as quoted.

### D-SINK-19 round 13 rulings (lead, 2026-10-13; R23, on top of R1-R22, which stand)

**What the round-12 lenses found, on lane-key-n2 (3c2ba57).** The
data-loss lens read 0 problems over about 240,000 sequences (21,280 at
length 1 over ten load-failure kinds, 80,864 at length 2, 111,132 at length
3, 28,824 re-run with a corrected oracle; its `rk12.js`, session scratch),
through `Service.qml`'s own load handlers, the real helper and the real
0.13.6 helper. The live lens found no P1 or P2 and verified the upgrade from
0.13.6 with the real `omarchy-plugin-update`. What they left:

- P2 (the data-loss lens). `liftStateBlock` resets `stateBlockTold`, which is
  what makes a second no-write episode in one session get told -- and
  nothing checked it. Its mutant X13 (that one line deleted) read 0 of 2,354
  node failures and passed live (B5-B7 hold one episode); in the second
  episode an in-app favourite was refused and the user never told.
- P3-1 (the data-loss lens, live, its `lf-child-text.sh`). After the
  session's first own save (an in-app add), an in-place truncation, emptying
  or garbage write raised no reload: `-- damaged: blocked= add=ok
  file=CHANGED told=0 urls=0`, so the mode never began and the next save
  wrote memory over the damaged file (nothing lost: memory held it). With
  no own save since the start the same damage blocked (`blocked=unparsed
  add=state_unreadable file=same told=1`). The node harness delivered a
  reload on every external change (rule 10).
- P3-2 (both lenses). A FIFO at `state.json`: `state init`, `state show`
  and `state favorite add` each blocked in `open()` (rc 124 under `timeout`),
  because the init read the file before its lstat witness; the service waited
  on the init with no watchdog, the user was never told, and every start left
  an orphaned helper reparented to the session manager. The same on 0.13.6.
- P3-3 (the live lens). In the no-write mode the logo toggle answered `Could
  not save settings · try omarchy bar set` (`Guide.qml` `toggleLogos` /
  `confirmLogos` mapped every `false` to `persist_failed`).
- P3-4 (the live lens). `state init` chmod-ed a DIRECTORY at the state path
  0755 -> 0600, making it unsearchable, while the README said the plugin had
  not touched it. Pre-existing (dev's `init_state_file` has the same branch).
- P3-5 (the live lens). A no-write start drew the first-run form (`No
  playlist configured`), whose submit is refused; only the notification
  said why.
- P3-6 (the live lens). key-scenario.sh stated lane-key-m2's baseline as 96 /
  9 in its header and 97 / 9 in its footer (lettered checks against summary
  lines, one unlabelled); the harness's `emptyTitle` / `emptyProse`, called
  "the empty state as DRAWN", read the hidden empty state's prose while the
  first-run form drew `firstRunProse`.
- Left by the round-12 lanes: R22e's last step (below, R23i), whose prepared
  patch was lost when the machine rebooted on 2026-10-13 and `/tmp` (a tmpfs)
  went with it.

**The lead's ruling, R23.**

R23a. The re-arm is pinned. A node pin through `Service.qml`'s own functions
(`tests/service-harness.js`): two no-write episodes in one session, the
second told again, and an in-app input refused in the second episode refused
AND told. A live segment in key-scenario.sh: two episodes with no own save
between them, two notices. Both seen red with the reset line deleted, through
a mutation patch file.

R23b. The helper never opens a state path in a way that can block, and never
reads one that is not a regular file (or a symlink to one). One shared opener
for every state read, race-free (a non-blocking open, then `fstat` S_ISREG),
answering `other` for `init` and `state_unreadable` with exit 1 for the
verbs, the file left untouched. Pins run the real helper as a subprocess with
a timeout. Rule 15 over every `open()` of a path a user or another program
can replace, each with a verdict.

R23c. The service never waits on the init forever: `stateInitProc` gets a
watchdog in the shape of the service's other helper runs, its bound chosen
from the init's measured duration idle and under load with the margin
stated. A timeout kills AND reaps the helper and decides as the no-write
mode with its own reason (one more reason in `Model.stateUnreadableNotice`),
told once.

R23d. `init_state_file` never chmods anything that is not a regular file.
Rule 15 over every chmod in the helper, each with a verdict.

R23e. The no-write mode has its own guide surface. While `stateWriteBlocked`
is set the guide does NOT draw the first-run form: it draws an empty state
whose title and prose come from `Model.stateUnreadableNotice` for the current
reason and path -- ONE source of copy with the notification -- with no
editable field (D-CLIP-1). The Sources screen stays reachable as it is.
Pinned through the model and through the harness, red on lane-key-n2.

R23f. Every refusal in the no-write mode says the no-write reason: the logo
toggle and every other Guide path that maps a service `false` to generic copy
route through a Model decision that answers the `state_unreadable` sentence
while `stateWriteBlocked` is set. `ownedWriteMode` stays `none` in the mode.

R23g. Rule 10 for the file model. Measure what the real FileView does to its
watch after its own save, the helper's atomic rename, an external in-place
write and a restart; make `tests/service-harness.js` deliver reloads exactly
as measured; rewrite or report every pin that relied on a reload reality
would not deliver. Do NOT change the service's watch behaviour: D-SRC-19 is
its own work, and its scope is whatever is measured.

R23h. Instruments: key-scenario.sh states its baselines in one named unit;
the harness's drawn-copy fields report what is DRAWN, and a check reads them.

R23i. R22e finished: the one commit that removes the last three prefixed
citations and their three withdrawn-symbol waivers together.

**Confirmed by the lead (2026-10-13), settled from this date.** Round-12 lane
A's three readings where R22a was silent, recorded in the round-12 rulings
above as "built and raised", are now rulings: (1) an EMPTY `state.json` does
not parse and blocks; (2) a FileNotFound in the middle of a session blocks
(the FileView reports an unreadable directory the same way); (3) a block at a
start gets one re-read after the init, so a 0000 file or a 0000 directory
recovers with no notice, because the init's mode repair fixes it.

**Measure only, nothing changed: can `manifest.json` stop declaring
`playlistUrl` and `epgUrl`?** Lane A read the host as installed (omarchy
4.0.4-1) and this lane re-read the same lines on 2026-10-14. An undeclared
key on a bar entry still reaches a third-party plugin's `barConfig`:
`/usr/share/omarchy/shell/shell.qml` 326-328 is `function publicBarConfig()
{ return JSON.parse(JSON.stringify(shell.barConfig || {})) }`, a deep clone
filtered by nothing, which `barConfigFor` (330-333) hands to a plugin that is
not first-party, and `plugins/bar/BarModel.js` `entrySettings` (10-17) copies
every key but `id`. `omarchy bar set` accepts an undeclared key: `cmd_set` in
`/usr/share/omarchy/bin/omarchy-bar` (333-361) passes it to `omarchy-shell
shell setBarWidget`, and `services/PluginRegistry.qml` (342-379) checks only
the location and that the entry is an object, then `entry[String(key)] =
value` (379). The manifest's `defaults` are never written to an entry (a put
entry is created as `{ id: key }`, PluginRegistry.qml 526), and the only host
reads of `schema` and `defaults` are the registration at shell.qml 1406-1408.
The live proof already exists: `sourceKey` is not declared in `manifest.json`
and the plugin writes and reads it through `barConfig` today. What would have
to change: `tests/test_manifest.py`
`test_the_shipped_seven_keys_are_untouched` asserts both keys in `defaults`
and `schema`. Answer: on this host the migration does not depend on the
declaration. The lead decides; nothing is changed this round.

**What the tree does (lane-key-p1, lane A: 0fbdd47 R23b/R23d, d5cd45c R23g,
418e01e R23a/c/e/f, 7a39498 and bb5b2de the live segments and the census; on
lane-key-n2 merged with dev e7b1275 as 86e9800).**

- R23a. The reset line stands as it was; what is new is its check. Node:
  `R23a (<mode> host, mid-session, <between> between): TWO no-write episodes
  -- the lift re-arms the notice, so the second episode is told again, and an
  in-app favourite refused in it is refused AND told`, four pins. Live:
  key-scenario B9, two episodes reached by in-place writes the FileView
  reloads, with no own save between them (`episodes:unparsed/[]/unparsed
  told:1/2 path:2 add:state_unreadable file:same urls:0`). Seen red through
  `scripts/dev-harness/spikes/key-mutations/r23a-no-rearm.patch`: node 4 of
  2,358, the same 4 with the own-write echo off; live 111 / 1, B9 `told:1/1`
  (`key-20261013-214109-138686`). On lane-key-n2 both are green, because the
  line existed there and only its check did not.
- R23b. One opener, `open_regular` in `bin/omarchy-iptv`: `O_RDONLY |
  O_NONBLOCK | O_NOCTTY | O_CLOEXEC`, then `fstat` of the descriptor that was
  opened; anything but S_ISREG raises `NotRegularFile` (an `OSError`, so
  every tolerant reader that answers `None` for an unreadable file answers
  `None` for this), and a socket, which cannot be opened at all (ENXIO), is
  reported the same way. `state init` takes its lstat witness first and then
  reads through the opener; a regular file swapped for something else between
  the two is `other`. Every other verb refuses through `read_state_strict`
  with exit 1, code `state_unreadable` and `state.json is not a regular file;
  nothing was written`. Python: `StateNeverBlocksTest`, ten tests, each
  running the real helper as a subprocess with a 20 s timeout -- the init over
  a FIFO and over a socket answers `other` at once and leaves it, every verb
  refuses a FIFO, a socket and a directory as not a regular file, the D-ID-1
  remap reads a FIFO without blocking. Against lane-key-n2's helper with a 3 s
  timeout: 9 of 10 failed (30 failing subtests: the FIFO, socket and
  directory timeouts for init and every verb, and the chmods R23d removes);
  the control, a symlink to a 0000 file, green. Live: key-scenario B14 (`blocked:not-a-file
  found:present told:1 left:none fifo:600`), red on lane-key-n2 (`blocked:
  found: told:0 left:<pid>`, the hung helper killed by pid afterwards).
- R23c. `Service.startStateInit` arms `stateInitWatchdog`
  (`stateInitTimeoutMs`, 15 s) every time it starts the init; on expiry it
  logs `omarchy-iptv: state init exceeded 15 s, terminating it`, sets
  `stateInitTimedOut`, sends TERM, and `stateInitKill`
  (`stateInitKillGraceMs`, 2 s) sends KILL if the run is still alive. The
  exit handler stops both timers, counts the run as failed (`stateInitOk`
  false) and hands the flag to `Model.stateInitFound(stdout, exitCode,
  timedOut)`, which answers `timeout`; `Model.stateLoadDecision` then blocks a
  load that was WAITING on the init with reason `init-timeout` (no retry:
  nothing a re-read could fix). A load that had already been applied when the
  init timed out is left as it was: no block, no notice, the init counted as
  failed (lane A's reading, raised below). The bound, from the real `state
  init` timed on this 4-core machine on 2026-10-13 over a fresh directory and
  an existing file alternately (lane A's `inittime.py`, session scratch):
  idle, 30 runs, 214-215 ms; six busy loops (1.5x oversubscribed, load about
  3), 30 runs, median 543, p90 817, max 968 ms; twelve (3x, load 7.7), 20
  runs, median 1,246, p90 1,575, max 1,769 ms. 15 s is 8.5 times the worst of
  those and 70 times idle; a false timeout costs one session in the no-write
  mode, told, with nothing lost. Live: key-scenario B10, the init held 60 s
  by a deliberately slow tree over a file that does not parse
  (`blocked:init-timeout found:timeout helper:yes left:none told:1 stopped:1
  file:same watchdog:1`; `left:none` is an exact-argv scan of /proc, never a
  pattern), red on lane-key-n2 (`blocked: found: helper:no(<pid>) left:<pid>
  told:0`). Node: `R23c: stateInitFound answers "timeout" ...`, `R23c:
  stateUnreadableNotice("init-timeout") is its own sentence ...`, and per
  host `R23c (<mode> host): startStateInit arms the init's watchdog ...`, `...
  the init never answers over <fault> ...`, `... an init that times out AFTER
  the state loaded leaves the session as it was ...`. Pointed at lane-key-n2's
  `Service.qml` and model: 6 of 2,372 failed, all R23c harness pins; the
  loaded-then-timeout pin is a control and green there.
- R23d. `chmod_if_kind(path, mode, kind)` opens the path `O_PATH` (no
  permission needed on the target, never opens a FIFO or a device), decides
  the kind by `fstat`, and chmods through `/proc/self/fd/N`, so a rename
  between the check and the change cannot redirect it; a mode already right
  is not touched (a chmod is an inotify `IN_ATTRIB` on what the shell
  watches); no `/proc` means no repair, never a chmod by name. `init_state_file`
  repairs only S_ISREG; `ensure_private_dir` only S_ISDIR. The atomic writers
  and the init's create `fchmod` their own descriptor. Python:
  `test_init_never_chmods_a_directory_at_the_path`, `..._a_fifo_at_the_path`,
  `test_init_still_repairs_a_symlink_to_a_0000_file`,
  `test_init_never_chmods_a_file_where_the_state_directory_should_be`.
- R23e. `Model.guideSurface` answers `stateUnreadable` for an unconfigured
  guide while `stateBlocked` is set (`setup` false, no saved-sources link, no
  rows); `Model.firstRunAllowed({ serviceReady, configured, stateBlocked })`
  is the one decision the guide asks before opening into the first-run form
  -- on open, on a `configured` or `stateWriteBlocked` flip while open, and on
  the Esc / `o` return from Sources (`Model.closeSources`, `Model.onEscape`).
  The empty state's glyph is the alert glyph, its title and prose are
  `Model.stateUnreadableNotice(stateBlocked, Service.stateFilePath)` -- the
  notification's own words -- and its footer drops `r retry` (a refresh cannot
  make the file readable). A guide that still HAS channels mid-session keeps
  them: memory stands and plays, and the refusals say why (R23f; lane A's
  reading, raised below). If the mode begins while the first-run form is
  showing (an init that answered late), the guide leaves the form for the
  surface. Node: `R23e: guideSurface ...`, `R23e: firstRunAllowed ...`, `R23e:
  the Esc / o return from Sources ...`; mutations of each read 1 failure.
  Live: key-scenario B11 (`kind:stateUnreadable form:false editable:0
  shown:true title:notice prose:notice sent:1`), red on lane-key-n2
  (`kind:unconfigured form:true editable:0 shown:NOFIELD`). `editable:0` is
  the harness's new census (`ipc editable`, the editable text inputs under the
  guide), which was seen counting through
  `spikes/key-mutations/r23e-editable-field.patch`: B13 `editable:2`
  (`key-20261013-230141-283957`, 111 / 1).
- R23f. `Model.refusalMessage(code, blocked, kind)`: while `blocked` is set,
  `Model.sourceErrorMessage("state_unreadable")` whatever the code;
  otherwise `Model.persistFailureMessage(code)` for `kind` `"persist"` and
  `Model.sourceErrorMessage(code)` for any other kind. `toggleLogos` (off),
  `confirmLogos` (on) and `showPersistFailed` go through it. Node `R23f:
  refusalMessage ...`, and the R16 structural pin re-pointed to it. Live:
  key-scenario B12 (`says:no-write advice:none writes:0`), red on lane-key-n2
  (`says:other advice:bar-set`).
- R23g. Measured, below. `tests/service-harness.js` gains `ownEcho`
  (`"load"` | `"none"`, from its options or `IPTV_HARNESS_OWN_ECHO`) and
  `scripts/check.sh` runs the node suite a second time with it off: 2,372 / 0
  both ways. No existing pin relied on a reload the real FileView was not
  measured to deliver, so none was rewritten. The `none` run has not been seen
  red: no pin fails without the echo, which is the finding, not a check proven
  (rule 11).
- R23h. key-scenario.sh states every count in one named unit (the summary
  line's) and its header says which; the harness's `state` verb reports
  `emptyTitle` / `emptyProse` as DRAWN -- the first-run form's head when it
  shows, else the empty state when it shows, else nothing -- with
  `emptyShown`, `firstRunHead`, `firstRunForm`, `stateBlocked` and
  `footerHints` beside them. Live: key-scenario B13, a fresh install's drawn
  copy (`form:true editable:0 ... prose:Paste or type your M3U URL or path,
  then press Enter`), red on lane-key-n2 (`prose:Add your M3U URL or path in
  Sources...`, the hidden empty state's).
- R23i (this lane, lane-key-p2 fbb61f8). The reducer-table row's three
  prefixed names went bare and the three waivers went, in one commit; each
  half alone is red (docs half: `withdrawn-symbol waivers: 3 listed, 0 in
  use` and three "unused" problems; script half: three `Model.<name> is cited
  in docs/ARCHITECTURE-SOURCES.md and resolves in no source file`). The
  ledger reads `withdrawn-symbol waivers: 0 listed, 0 in use` and 244 symbol
  citations (247 before: the three were the difference). The round-12
  hazard is closed: entryWriteNeeded cited with the `Model.` prefix in `QA.md`
  now reads rc 1, where it read rc 0 under the waiver.

**What FileView does to its watch (R23g), measured 2026-10-13 by lane A.**
quickshell 0.3.1 and Qt 6.11.2 as installed, in a nested headless cage on a
private D-Bus with no service directories (`scripts/dev-harness/
private-bus.sh`, committed this round). Instrument 1 is
`scripts/dev-harness/spikes/filewatch/measure.sh`: one FileView declared
exactly as `stateFile` is (`watchChanges`, `atomicWrites`, `printErrors:
false`, `onFileChanged: reload()`), 16 sequences each on a fresh shell over
a fresh file, 1.5 s per step, at load 1.31; its printed result is kept
beside it as `RESULT-2026-10-13.txt`, so the measurement is re-runnable.

| Step | `fileChanged` | a load delivered | a later in-place write still seen |
|---|---|---|---|
| (iii) an external in-place write (`>`: truncate, empty, garbage, good content) | yes | yes, every time | yes |
| (ii) the helper's atomic rename (`state favorite add`) | yes | yes | yes |
| a chmod | yes | yes | yes |
| (i) the view's OWN `setText` save, alone, at idle | yes, with `saved` | NO: 0 of 16 lone saves, and 0 in a burst of 2-3 own saves | yes |
| an own save with an external write queued right behind it | yes | yes, with the later text | yes |
| (iv) a restart | -- | the first load | yes |

In EVERY sequence, an in-place write after any number of own saves, helper
renames, chmods or a restart was still seen: the watch was never lost.
Instrument 2 is the real `Service.qml` under the dev harness in a cage (lane
A's `svcwatch.sh`, session scratch, NOT committed; its output
`svcwatch-1..4.txt` read by this lane): at idle, after an in-app add's own
write, in-place garbage, empty and truncated writes each blocked the session
(`unparsed`) and a restore lifted it; a helper rename (`os.replace`, and
`state source add`) was applied as `file-newer`. With six busy loops on four
cores (load 2.6 -> 7.6) the same results held, and the own write DID deliver
a load carrying its own text, counted `own-write`. Logged event order: at
idle `setText, setText, saved, fileChanged, saved` and no load; under load
`saved, saved, fileChanged, load(own=true)`. So the own echo is
timing-dependent, which is why the harness now runs both ways.

**The measurements disagreed, and the variable was found after this round
(corrected 2026-10-14, D-DOC-8: this paragraph used to make the session's
own saves the variable and to give D-SRC-19's scope as none).** The
round-12 data-loss lens measured, live, NO reload after an in-place damage
that followed the session's first own save (P3-1 above); the round-12 live
lens measured NO reload after the helper's atomic `state source add` (its
`rename.out`: the reload counter stayed `{'first-load': 1}`); and D-SRC-19
itself was filed on the round-9 data-loss lens's measurement of the same.
Lane A's two instruments above, idle and under load, reproduced neither --
and every one of lane A's rigs started with the state DIRECTORY present.
The round-13 live lens isolated the variable on lane-key-p2 and on a 0.13.6
export alike, alternating the two shapes (its `case_watchvar` and
`case_prodfresh`, session scratch): with the directory present when
`stateFile` first loaded, every external change reloaded, own saves or not
(3 of 3 helper `source add`, 3 of 3 recoveries from a 0000 file or
directory); with it ABSENT -- the production fresh-install shape, the state
home present and `omarchy-iptv/` under it absent -- the reload counter
stayed `{"first-load": 1}` all session, the own echo included, a helper
`source add` was unseen and then written over by the next in-app save, and
garbage written in place BEFORE any save was not noticed. That is the shape
the earlier lenses' rigs had. The lead's ruling (1) of 2026-10-14 settled it
on that measurement, and round 14 reproduced it in the committed spike
(sequence Q) and fixed it (R24c). As things now stand:
- D-SRC-19's scope was the first session after a fresh install: neither none
  nor "after the first own save". On lane-key-q1 that session is re-armed by
  one `stateFile.reload()` after the start-up check (R24c) and observed by
  key-scenario B16; the board state is the lead's.
- The mid-session no-write mode is observed live with no own save before
  it (B5-B7 round 12, B9 round 13) and, in the fresh-install session, after
  an own save (B16, round 14). In a session whose directory already existed,
  AFTER an own save, it is observed by the committed spike
  (`RESULT-2026-10-13.txt`, every sequence) and by the round-13 live lens's
  rig (`case_episodes`: after an in-app add, garbage in place gave
  `blocked:unparsed told:1`), and by no key-scenario segment [round 15:
  key-scenario B21 observes it].
- 0.13.6 shares the dir-absent behaviour (the lens's export, and its
  `stateFile` declaration is identical); it has no R24c.
- The helper's own text now says what was measured (R24c, round 14).

**The no-write copy, as shipped on lane-key-p1.** One more reason in
`Model.stateUnreadableNotice`; the round-12 table above carries it as its
own row:

| Reason | `<what>` | `<fix>` |
|---|---|---|
| `init-timeout` (R23c) | `could not be checked: the start-up check did not answer and was stopped` | `Make sure a regular file, or nothing, is at that path, then run omarchy restart shell.` |

The guide's no-write surface draws `Saved sources not loaded` over the same
body as the notification (R23e). Every refusal the guide shows in the mode
reads `state.json could not be read · nothing is saved until it can be`
(R23f). The helper adds one refusal, `state.json is not a regular file;
nothing was written`. `UX-SOURCES.md` 5.10 is what the user sees.

**Rule 15, lane A's searches (lane-key-p1), recorded here so the next person
inherits them.**
- Every `open()` in the helper of a path a user or another program can
  replace (R23b). Routed through `open_regular`: `state.json` for `state
  init`, every other verb and the D-ID-1 remap; every cache JSON
  `read_json` reads (`channels.json`, `failed.json`, `playlist-status.json`,
  `epg-status.json`, the indexes); the EPG window cache (`load_window`); a
  cached logo (`_read_logo_prefix`); the player lock record
  (`read_lock_file`); a local playlist or EPG file (`read_local_source`,
  whose `isfile` check a swap could outrun). Left as they are, with why: the
  player lock's `O_CREAT | O_RDWR` open (`acquire_lock`; on Linux `O_RDWR`
  does not block on a FIFO, and its fchmod is now gated on S_ISREG); the
  config shield's open of `shell.json` (already `O_NONBLOCK | O_NOFOLLOW`,
  refused by fstat unless a regular file the euid owns); the cache walk's
  directory opens (`O_DIRECTORY` fails at once on anything else); the atomic
  writers' temporary files (created `O_EXCL` in a 0700 directory);
  `manifest.json` in the plugin directory, `/proc/<pid>/*`, `os.devnull`, and
  the urllib openers (network, not paths). The list also sits in a comment
  above `NotRegularFile`.
- Every chmod in the helper (R23d; lane-key-n2 line numbers): 703 and 707,
  `ensure_private_dir` -- now S_ISDIR only, and 707 was a SIBLING defect: it
  chmod-ed whatever sat at the state-directory path, so a regular file there
  came out 0700, executable (pinned, mutation P4 1 failure); 2117 and 2140,
  the temporary files -- now `fchmod` on the creating descriptor; 7922, the
  init's repair -- the defect itself, now S_ISREG only on an `O_PATH`
  descriptor; 7928, the init's create -- `fchmod`; 5120, the player lock --
  gated on S_ISREG; 8161, the config shield -- already gated on S_ISREG and
  owner, cleared.
- Every Guide path that maps a service result to copy (R23f). Routed through
  `Model.refusalMessage`: `toggleLogos`, `confirmLogos`, `showPersistFailed`.
  Cleared, because they render the service's own code, which is
  `state_unreadable` in the mode: `switchSource`, the add / update form's
  submit (`failForm`), `removeSource`, `retrySource`. Cleared as not
  refusals of a state write: `not_ready`, `unknown_source`, `too_many`, and
  the player verbs (`togglePause`, `seek`, `requestTracks`), which write no
  state. NOT changed, raised below: `toggleFavoriteAt`, `saveCurrentSearch`
  and `removeAt` (recent, hide, forget) apply in memory and show their
  success copy; their state write is refused silently and counted in
  `stateWritesRefused`.
- Harness pins that relied on a reload the real FileView would not deliver
  (R23g): none. Other drawn-copy readers (R23h): B8 reads the error kind,
  where the drawn copy and the empty state's agree; `emptyTitle` and
  `emptyProse` have no other reader in `scripts/`.

**Mutation, lane A (one decision at a time in a `git archive` export, the
whole suite counted).** Helper, of 62 `test_state` tests: P1 `O_NONBLOCK`
removed 11 failed; P2 the S_ISREG refusal removed 16; P3 the init's repair
chmods any kind 3 (directory, FIFO, socket); P4 `ensure_private_dir` chmods
any kind 1; P5 the init's `found` override from the descriptor removed 0 --
equivalent unless a rename races between the lstat and the open, so no
deterministic test reaches it; kept as a defensive line and raised below.
Node, of 2,372: N2 `stateInitFound` ignores `timedOut` 5; N3
`stateLoadDecision` without the timeout line 5; N4 `startStateInit` does not
arm the watchdog 2; N5 the exit handler does not pass the flag 4; N6 the
watchdog does not set it 4; N7 no `init-timeout` sentence 1; N8 `guideSurface`
ignores the mode 1; N9 `firstRunAllowed` ignores it 1; N10 `closeSources`
ignores it 1; N11 `refusalMessage` ignores it 1.

**Counts.** On lane-key-n2 merged with dev (86e9800): node 2,354; python
1,170; `qa-lib-test.sh` 472; key preflight 11; key-scenario's live floor 105
lettered checks, summary 106 / 0; qml spec 78; a11y 35; text format guard
58; ledger 247 citations, 337 board rows, withdrawn-symbol waivers 3 / 3. On
lane-key-p1 bb5b2de (lane A's report; `./scripts/check.sh` all green on
7a39498 and on bb5b2de, about 204 s each at load 0.3-2.1): node 2,372 (+18:
4 R23a, 10 R23c, 3 R23e, 1 R23f), and 2,372 again with the own-write echo
off; python 1,180 (+10, `StateNeverBlocksTest`); `qa-lib-test.sh` 472 (the
patch-apply check now covers four patches); key preflight 11; key-scenario
live floor 111 (B9-B14), forward 112 / 0 in 277 s
(`key-20261014-043943-514380`), `--baseline lane-key-n2` 107 / 5 in 294 s,
B10-B14 red (`key-20261014-044420-538071`); sources-scenario 66 / 0 under an
outer headless cage on a private bus; logo-scenario 33 / 0
(`logo-20261014-043540-501342`); qml spec 78, a11y 35, text format guard 58.
Every live run under a nested headless cage on a private D-Bus with no
service directories; transcripts in lane A's session scratch directory. On
lane-key-p2: at fbb61f8 (R23i) the ledger read 244 citations, 337 rows,
withdrawn-symbol waivers 0 / 0; at the lane's documents tip, 247 citations
(this section cites three names no document cited before, `closeSources`,
`firstRunAllowed` and `refusalMessage`, each resolving), 337 rows, 0 / 0.

**Open for the lead (decision requests, not defects; the board's ids are the
lead's).**
- (1) The FileView watch measurements disagree (above); D-SRC-19's scope,
  the mid-session condition and the helper's help text wait on it.
  [Settled 2026-10-14 by the lead's ruling (1), on the round-13 live lens's
  measurement: the variable is the state directory at the first load. R24c
  acts on it; the paragraph above is corrected.]
- (2) (lane A's reading of R23c): an init that times out AFTER the state
  loaded leaves the session as it was (no block, no notice, the init counted
  as failed, which gates the entry flush). Confirm, or rule that a timeout
  always blocks.
- (3) (lane A's reading of R23e): the no-write surface replaces only the
  UNCONFIGURED body; a mid-session block keeps its rows. Confirm.
- (4) (R23f): a favourite, a hidden group, a saved or forgotten search
  and a removed recent apply in memory and show success copy in the mode;
  only the once-per-episode notice says changes now are not kept. Should
  those transients say "not kept" too?
- (5) (R23e, "Sources stays reachable as it is"): reachability did not
  change, but a no-write START has 0 sources in memory, so the footer does
  not offer `o sources` there (the same gate that hid the first-run form's
  `Saved sources` link). The `o` key itself is not gated on the count
  (`Guide.qml` `handleListLetter`), but no check observes `o` on that surface
  -- UNVERIFIED; the harness reaches Sources there through `ipc sourcesKey
  enter` (B12). Should the surface offer Sources explicitly? [Settled
  2026-10-14, the lead's ruling (5): `o` reaches Sources from the no-write
  surface -- the round-13 live lens drove `ipc mode` then `ipc listKey o` and
  it opened Sources (session scratch, not a committed check) -- and what
  that screen drew is D-SRC-28, fixed by R24f.]
- (6) the P5 line (init's `found` from the descriptor), reachable only
  by a rename race. Keep or drop.
- (7) the manifest answer above.
- Rule 13: the round-12 open item (1) -- `D-` ids and board rows for the
  0.13.6 losses -- is not touched by this round; `docs/STATUS.md` is not
  this lane's.

### D-SINK-19 round 14 rulings (lead, 2026-10-14; R24, on top of R1-R23, which stand)

**What the round-13 lenses found, on lane-key-p2 (f4f86de), now on `dev`
(efde249).** No P1. Three P2s that block 0.14.0, each boarded on 2026-10-14:
D-SRC-22 (a hand-run helper write that arrives while a save of the
session's is parked, in flight or has failed is reloaded, IGNORED, and then
written over by the next save that lands, while the helper answered `ok:
true`; 0.13.6 applies every reload and drops the in-app change instead --
one of the two is always silent); D-SRC-23 (a dangling symlink at
`state.json` reads as "absent" to every hand-run verb, which then replaces
the link, while `state init` calls the same path `other`; in a running shell
the helper's write lifts the block and a marker-less file can adopt a
refused entry URL); D-DOC-8 (the round-13 documents gave the session's own
saves as the condition for noticing an external change; the round-13 live
lens measured that the variable is whether the state DIRECTORY existed when
`stateFile` first loaded -- D-SRC-19 as re-scoped). P3s: D-SRC-24 (a shell
stopped inside the init's watchdog leaves the hung init orphaned under
`systemd --user`), D-SRC-25 (`mkdirProc` unwatched, the init's watchdog
armed only after it), D-SRC-26 (a dangling link, or a file where the state
directory should be, advised `chmod 700` on a folder that is fine; the init
over the second printed a traceback), D-SRC-27 (the D-ID-1 remap writing
`state.json` in the no-write mode), D-SRC-28 (the Sources screen in the
no-write mode drawing a fresh install), D-DOC-9 (two "`omarchy bar set`
still offers" sentences), D-DOC-10 (the README's "nothing of yours is lost"
too strong for a hand edit), F-HARNESS-24 (the KILL half of R23c observed by
nothing), F-HARNESS-25 (the filewatch spike writing caches into the real
home).

**The lead's ruling, R24 (2026-10-14).**

R24a. D-SRC-22: A FOREIGN WRITE IS MERGED, NEVER IGNORED AND NEVER APPLIED
BLIND. The service keeps a BASE, the state it last knew to be on disk (the
text it loaded, or its last save that LANDED). A reload whose text is neither
the base nor a text the service itself asked to write is FOREIGN. While the
session holds a change the file does not (a save parked, in flight or
failed), a foreign reload is three-way merged by ONE pure function,
`mergeForeignState(base, ours, theirs)`; the result becomes memory, the
foreign text becomes the base, and a save is asked for whenever the result
differs from what is on disk. Field rules: favorites, savedSearches and
hiddenGroups are sets; sources are records by key (a record BOTH changed is
a conflict); recents and the scalars (activeKey, lastPlayed, session,
cacheLayout) take theirs when theirs changed since the base and ours did
not; entryMigrated is true if either side has it. A CONFLICT GOES TO THEIRS
(the foreign write is the later act, and the in-app side was already told
its save failed), logged one line per conflict with the key and the field,
never a URL. With no change held a foreign reload is applied as before,
which is the merge with ours == base (prove they agree). The R22 no-write
mode is untouched. Pinned with a fixture table and through
`tests/service-harness.js` on both host shapes, both own-echo modes, for
parked, in flight and failed; the data-loss lens's WF FAV WOK HADD FAV keeps
BOTH the in-app favourite and the helper's record; red on dev.

R24b. D-SRC-23 and D-SRC-26: ONE ANSWER PER PATH. A symlink at the state
path is FOLLOWED when its target is a regular file, for reads and writes,
and REFUSED like any non-regular path (every verb exit 1, file and link
untouched) when it dangles or points at anything else. Measure first what
the helper's writer and the FileView's save each do to a VALID link; a
writer that replaces a valid link is a defect (fix the helper's: temporary
file beside the target, renamed onto it); if the FileView's save replaces
it, report and stop. The shell's copy for a dangling link and for a regular
file where the state DIRECTORY should be names what is at which path; `state
init` answers the second cleanly. Pins run the real helper as a subprocess
with a timeout, red on dev.

R24c. D-SRC-19 and D-DOC-8: THE FIRST SESSION SEES EXTERNAL CHANGES TOO.
Measure, in a nested cage on a private bus with the production fresh shape,
what re-arms `stateFile`'s watch once the start-up mkdir / init has created
the directory -- an explicit `stateFile.reload()` first -- and ship the one
measured to work, proving the reload it causes is the identity under R24a.
Model the dir-absent first session in the harness as measured (rule 10);
add a live segment, red on dev; fix the helper's own sentences that say the
shell does not re-read `state.json`. If nothing re-arms the watch, say so
and the documents state the dir-absent condition instead.

R24d. D-SRC-24 and D-SRC-25: ONE BOUND OVER THE WHOLE START-UP CHECK. The
watchdog arms when mkdir starts and covers mkdir and the init alike (TERM,
then KILL); and the init bounds ITSELF (`signal.alarm` at the top of the
verb, a deadline longer than the service's, the default action), so a shell
that stops first leaves nothing running past it. Measured with the
slow-helper fixture; state plainly what no bound reaches.

R24e. D-SRC-27: in the no-write mode the playlist fetch does not hand the
helper the state directory; pinned, red on dev.

R24f. D-SRC-28: in the no-write mode the Sources header carries the R23e
notice title (one source of copy, `Model.stateUnreadableNotice`), no Add rows
are drawn, and `a` opens no form; pinned through the model and the harness,
red on dev.

R24g. F-HARNESS-24: the KILL half observed -- a TERM-ignoring init in the
harness double and in a live fixture, seen red with the KILL deleted.
F-HARNESS-25: the filewatch spike and `private-bus.sh` run with a scratch
HOME and XDG directories, and `tests/test_harness_home.py` is taught them.

R24h. D-DOC-8, D-DOC-9, D-DOC-10: the documents lane states the condition
lane A MEASURED after R24c (rule 14: what no check observes is UNVERIFIED),
drops the two "still offers" sentences and narrows "nothing of yours is
lost".

KEPT: `manifest.json` keeps declaring `playlistUrl` and `epgUrl` through
0.14.0 (lead ruling (7) of 2026-10-14). The other round-13 lead rulings in
the `docs/STATUS.md` decisions log for 2026-10-14 stand.

**What the tree does (lane-key-q1, lane A: 3db244c the helper half of R24b
and R24d and the D-SRC-19 sentences; c078ef3 R24a, R24c, the service and
double halves of R24d and R24g, the model half of R24b, R24e, R24f; 152e3a6
key-scenario B15-B18, the spike's r24 set, `private-bus.sh`'s scratch home;
318af7f the floors; c6315d1 the live counts).**

- R24a. `Model.reloadDisposition` takes one more input, `matchesBase`
  (`Model.sameState(text, landedState)`), and answers `apply` | `ignore` |
  `merge`. The base is `Service.landedState`: the text loaded, the last save
  that landed, or the last foreign text merged. First load: apply. Own write
  (the text is in `recentSaves`): ignore [round 15, R25a (D-SRC-30):
  `recentSaves` was the last eight texts written, so a copy of one put back
  later was ignored too; it is now only the burst still in flight, cleared
  as a save lands -- the round-15 rulings]. Nothing held: apply, reason
  `file-newer`. A change held (`save-parked`, `save-in-flight`,
  `save-failed`) and the text equal to the base: ignore, for the reason it
  is held -- R9 as it was, and the D-SRC-15 start-up chmod reload is exactly
  this branch. A change held and any other text: `merge`, reason
  `foreign-<held>` (`foreign-save-parked`, `foreign-save-in-flight`,
  `foreign-save-failed`), counted per reason like every other.
  `Service.mergeForeignText` calls `Model.mergeForeignState(landedState,
  userState, parseState(text))`, logs one `Model.mergeConflictLine` per
  conflict, sets the base to theirs and memory to the merge, asks for a save
  when the merge differs from theirs -- or when a save of ours is still in
  flight and differs from the merge, because it would land after theirs --
  and then runs what every applied state runs (the session outcome,
  `reconcile(true)`, the cache layout). "Equal" is `Model.sameState`: both
  sides through `parseState`, the service's own reader, then serialized with
  sorted keys (`Model.stateCanonical`), so the helper's compact JSON and the
  service's indented JSON of one state compare equal.
  The field rules, all in `mergeForeignState` (`model/state.mjs`):

  | Field | Rule | A conflict |
  |---|---|---|
  | `favorites`, `hiddenGroups`, `savedSearches` | a SET: theirs, in theirs' order, minus what ours removed since the base, plus ours' additions after (a saved search is named by its folded terms, as `parseState` de-duplicates it) | none: two sets merge |
  | `sources` | RECORDS BY KEY: a change by one side only is applied; ours' own adds, removals and changes stand | both changed one record differently; one changed it and the other removed it; both added one key with different records -- THEIRS wins (the record theirs holds, or the removal theirs made) |
  | `recents`, `activeKey`, `lastPlayed`, `session`, `cacheLayout` | WHOLE: theirs when theirs changed since the base, else ours | both changed it, differently -- theirs |
  | `entryMigrated` | true if either side has it | none |

  The result is read through `parseState` once more, so its caps and
  de-duplication apply to a merge as to a file [round 15, R25b (D-SRC-31):
  the caps were the silent half -- `parseState` stops at a cap, which cut
  the in-app additions with no line and no notice; they are applied inside
  the merge now, theirs first, and what is dropped is logged and told].
  The console line, verbatim from the model for a record: `omarchy-iptv:
  state.json was changed by another program while a change made here was
  not yet saved; kept the other program's version of the source 1a2b3c4d
  (label, url)` -- the field NAMES that differed, never a value -- and for a
  whole field `... kept the other program's version of activeKey` [round
  15, D-SRC-36: `version of` added in the model and in every quotation; on
  lane-key-q1 the line read `kept the other program's the source ...`]. Pinned: `tests/fixtures/state-merge.json`, 34
  cases (every field rule, every conflict kind, the identities, the
  data-loss lens's WF FAV WOK HADD as a case); node `R24a mergeForeignState:
  <case>` over each, `R24a: the fixture covers every field rule and every
  kind of conflict ...`, `R24a: over EVERY fixture case, the merge with ours
  == base IS theirs and the merge with theirs == base IS ours ...` (the
  "prove they agree" half, with ONE pinned exception, open question 1
  below), `R24a / R24c: sameState compares what a reader of the file sees
  ...`, `R24a: a conflict's console line names the field and the source key,
  never a URL or a value`; and `R24a (<host>, <echo>, <held>)` through
  `tests/service-harness.js` in 16 modes -- parked, in flight, failed and a
  conflict, on both host shapes and both own-echo modes -- where WF FAV WOK
  HADD FAV keeps both the in-app favourite and the helper's record. No live
  segment: the ruling asked for the table and the harness, and both exist
  [round 15, R25d (F-HARNESS-26): two of the merge's decisions survived
  every one of those checks; they are pinned now, and key-scenario B19 is
  the merge's live segment].
- R24b. The helper: `state_file_target(path)` answers the file a `state` verb
  reads and writes -- the path itself for nothing there or a regular file;
  the link's TARGET (`os.path.realpath`, once `lstat` and `stat` prove a link
  to a regular file) for a valid symlink; an `HelperError("state_unreadable")`
  for a link that dangles, leads into a missing folder, or leads to a
  directory or a FIFO, and for a file where the state folder should be
  (`lstat` answers ENOTDIR). `write_state_file` writes at the path or THROUGH
  the link: a 0600 `O_EXCL` temporary file beside the target, renamed onto
  it, and a target folder that is not the plugin's is neither created nor
  chmod-ed. Every verb's write and the D-ID-1 remap go through the pair.
  `state init` answers `found: link` for a link it will not follow and
  `found: not-a-dir` (exit 0, `created: false`, no traceback) for a file
  where the folder should be. The refusals, verbatim: `state.json is a
  symbolic link whose target is missing; nothing was written`, `state.json
  is not a regular file; nothing was written` (a link to a directory or a
  FIFO), `the state folder is not a folder (a file is at its path, or above
  it); nothing was written`; exit 1 each, the link untouched. The model:
  `Model.stateInitFound` maps `link` and `not-a-dir` to themselves (`file`,
  `other` and `unreadable` stay `present`), and `Model.stateLoadDecision`,
  for a FileNotFound load (which is what the FileView reports for both,
  measured by the round-13 claims lens), re-reads once and then blocks WITH
  that reason. `Model.stateUnreadableNotice` gains two rows and splits a
  third (the round-12 table above, amended): `link` -- `is a symbolic link
  whose target is missing or is not a regular file` / `Restore the file it
  points to, or move the link aside, then run omarchy restart shell.`;
  `not-a-dir` -- the FOLDER's path, `is not a folder (a file is at that
  path, or at one above it)` / `Move whatever is at that path aside, then run
  omarchy restart shell.`; and a mid-session `absent`, now apart from the
  start-up `absent-unconfirmed`, ends `If it is a symbolic link, restore the
  file it points to; otherwise make the folder readable with chmod 700. Then
  run omarchy restart shell.`, because mid-session the helper is not asked
  and the FileView cannot tell a broken link from an unreadable folder.
  Python (`tests/test_state.py`, the real helper as a subprocess under a
  timeout): `StateSymlinkTest` -- a valid link written THROUGH by every
  writing verb and surviving, read through, the favourite landing in the
  target; a dangling link, a link into a missing folder, and a link to a
  directory or a FIFO refused by every verb; init's `link` and `file`
  answers; the remap leaving a dangling link alone -- and
  `test_every_verb_refuses_a_file_where_the_state_directory_should_be`,
  `test_init_over_a_dangling_symlink_reports_link_and_creates_nothing`.
  Node `R24b: stateInitFound ...`, `R24b: stateLoadDecision ...`, `R24b: the
  link sentence names the file and the link, the not-a-dir sentence names
  the FOLDER's path, neither advises chmod 700 ...`, and `R24b (...)`
  harness pins over the two faults. No key-scenario segment drives either
  fault; the notification for them is observed only through the model and
  the harness.
- R24c. Measured first (below), then shipped: `Service.decideStateLoad`'s
  `fresh` branch calls `stateFile.reload()` after `applyUserState("")`. The
  reload it causes carries the init's created text (or a save of ours), and
  `Model.sameState` of the init's empty default and `parseState("")` is
  true (pinned), so with a save of ours held it is ignored as the base and
  with none it is applied over an equal memory: the identity R24a asks for.
  `tests/service-harness.js` now models the measured view: a boot with no
  file and no fault starts `dirAbsent` and UNARMED; `reload()` arms it once
  the file exists; `h.foreign()` delivers a change only while armed, and so
  does the own-write echo; the init's creation raises a load only when
  armed; `dirPresent: true` gives the other shape. Node `R24c (...)`, the
  fresh session and its identity (8). Live: key-scenario B16 -- the
  production fresh shape, XDG_STATE_HOME present and `omarchy-iptv/` under
  it absent -- `first-load:1 found:absent helper:0 seen:1 add:true file:C,D
  blocked:unparsed told:1`: a hand-run `state source add` seen, kept through
  the next in-app add's save, and garbage written in place after that save
  noticed and told once. On dev it reads `seen:0 file:D blocked: told:0`,
  which is the round-13 live lens's reading reproduced. The helper's own
  sentences now say what was measured: the `remap_state_file` docstring, the
  comment above the setting-owned warning, the `state source update --url`
  and `--epg-url` help (`A running shell re-reads state.json after this and
  keeps it`), and `setting_owned_warnings` (`A running omarchy-shell re-reads
  state.json after this write and keeps the <field> it wrote. If the same
  source was changed in the guide and that change was not saved yet, this
  write wins for that source. The guide's Sources screen edits the same
  record inside the shell.`).
- R24d. `Service.startStartupCheck` clears `stateInitTimedOut`, starts
  `mkdirProc` and arms `stateInitWatchdog` (15 s) at once; the watchdog and
  `stateInitKill` (2 s) act on whichever of `mkdirProc` and `stateInitProc`
  is running and log `omarchy-iptv: start-up mkdir exceeded 15 s, terminating
  it` or `... state init exceeded 15 s ...`, then `... ignored the terminate
  signal, killing it`; a mkdir the watchdog stopped never starts the init and
  is decided at once as the timed-out check (`stateInitExited(-1)`, reason
  `init-timeout`). The helper's `state init` arms `signal.alarm` with
  `STATE_INIT_DEADLINE` (30 s, the default action, nothing handles it)
  BEFORE it names the path; 30 s is past the service's 15 + 2. Measured by
  lane A with the slow-helper fixture holding the init inside the helper's
  own first `lstat` (`OMARCHY_IPTV_SLOW_AT=inside`, `SLOW_MS=60000`): `state
  init` ended by `Alarm clock` (rc 142) after 30.2 s, writing no
  `__pycache__`. Live: key-scenario B18, the shell stopped 5 s into a held
  init -- `held init ... alive (parent 827)`, `systemd --user`, then
  `at-stop:alive after-deadline:gone left:none`; on dev `after-deadline:
  alive(<pid>)`, killed by the scenario's cleanup. Python
  `StateInitDeadlineTest`: a held init dies of its own alarm, the deadline
  is past the service's bound, no other verb arms it. What no bound
  reaches, stated in `Service.qml` and the helper: a process in
  uninterruptible sleep on a hung filesystem takes no signal until the
  kernel lets go -- the service's TERM and KILL and the helper's alarm
  alike. A hung `mkdir` was not reproduced (no FUSE rig); the mkdir half of
  the bound is pinned in the harness (`R24d (...)`, 2), not observed live.
- R24e. `Model.fetchStateDir(stateDir, blocked)` is `""` while the service is
  in the no-write mode, so `Model.playlistFetchArgv` omits `--state-dir` and
  the helper's remap touches no state file; `Service.runPlaylistHelper`
  passes it. Node `R24e (...)` (2), and the id-rotate seam reads the
  directory through it. A fetch already running when the mode begins keeps
  the argv it was started with (open question 3).
- R24f. `Model.sourcesRowCount(n, stateBlocked)` and `Model.sourcesRowKind(i,
  n, stateBlocked)` draw no Add rows in the mode; `Model.sourcesAddAllowed`
  is false there, and `a`, `c` and Enter on an Add row open no form and say
  `state.json could not be read · nothing is saved until it can be` in the
  footer (`Guide.qml` `addRefused`, through `Model.refusalMessage`); the
  header's right slot is `Model.sourcesHeaderRight(n, stateBlocked, path)`,
  the notice's own TITLE, `Saved sources not loaded`, where it read `No
  sources`; `Model.footerHints` in Sources drops `a add` and `c Xtream` --
  `Esc back` alone with no source row, `j/k move - Enter switch - e edit - x
  remove - g logos on - Esc back` on one. Node `R24f: sourcesRowCount /
  sourcesRowKind ...`, `R24f: sourcesHeaderRight ...`, `R24f:
  sourcesAddAllowed ...`, `R24f: footerHints in Sources ...`. Live:
  key-scenario B15 at a no-write START (`mode:sources header:notice rows:0
  addhint:no after-a:sources says:no-write editable:0`), red on dev
  (`header:[No sources] rows:2 after-a:sourceEdit says:other`); its
  `addhint` token does not discriminate at row 0, the others do. A
  MID-session block, where Sources still lists the records memory holds, is
  pinned in node only [round 15: observed by B22, its header `Saving has
  stopped` since D-SRC-38].
- R24g. The harness double now decides what a TERM-ignoring process does,
  so the KILL is observed: `R24g (...)`, an init and a mkdir that ignore the
  TERM (2 each), red only with the KILL deleted
  (`scripts/dev-harness/spikes/key-mutations/r24g-no-kill.patch`: 4 of
  2,459, `hung (the kill was not sent)`). Live: key-scenario B17, the
  slow-helper fixture ignoring SIGTERM (`OMARCHY_IPTV_SLOW_IGNORE_TERM=1`),
  `blocked:init-timeout helper:yes left:none told:1 file:same watchdog:1
  killed:1`; green on dev, which had the KILL, and red on the patched tree
  (`blocked: helper:no(<pid>) left:<pid> told:0`). F-HARNESS-25:
  `scripts/dev-harness/private-bus.sh` hands its command HOME and the XDG
  directories inside its own directory and removes them after;
  `tests/test_harness_home.py` `PrivateBusIsolatesHome` runs `private-bus.sh`
  for real with a probe, and the filewatch spike with a stand-in `cage` that
  records its environment, each against a decoy home, and is red against
  dev's scripts (2 of 2, `HOME=... is not the scratch home`). Lane A also checked
  the real home before and after every cage run this round: the mesa shader
  cache's mtime and the `~/.config` and `~/.cache` listings unchanged.
- R24h. This section, and the corrections below.

**What FileView does over a missing directory and over a symlink (R24b,
R24c), measured 2026-10-14 by lane A.** quickshell 0.3.1 and Qt 6.11.2 as
installed, `scripts/dev-harness/spikes/filewatch/measure.sh <helper> r24`,
one FileView declared exactly as `stateFile` is, in a nested headless cage
on a private D-Bus, 1.5 s a step; two runs at load 1.2-1.7, the first with
dev's helper and the second with lane-key-q1's, both printed into
`RESULT-2026-10-14-r24.txt` beside it. `absent` is the production fresh
shape (the state home present, `omarchy-iptv/` under it absent); `mkinit`
is the start-up `mkdir -p` and `state init`.

| Sequence | Start | What happened |
|---|---|---|
| Q | absent | after `mkinit` NOTHING raised anything: the init's creation, a helper rename, an in-place write and an in-place garbage write each `fileChanged+0 loaded+0` -- the round-13 live lens's session, reproduced |
| R | absent | one explicit `reload()` after `mkinit` gave `loaded+1`, and every later helper, in-place and garbage write gave `fileChanged+1 loaded+1` |
| S | absent | resetting the path instead of `reload()` re-armed it too; not needed, not shipped |
| T, R2 | absent | the re-arm held across a later own save, before or after a helper write |
| U | directory present, no file | the init's creation was seen without help, and everything after it |
| V | a valid symlink | the view's OWN save wrote THROUGH it (`at-path:symlink`, the target holding the 50 bytes); dev's helper then REPLACED the link with a regular file (`at-path:regular`), after which the view saw nothing more (`fileChanged+0`, the helper's write and a later in-place write alike); lane-key-q1's helper kept the link and every write was seen (`fileChanged+1 loaded+1 view==disk:yes at-path:symlink`) |
| W | a valid symlink | the same difference with the helper first |
| X | a dangling symlink | the view's own save raised `saveFailed` and left the link [round 15, D-DOC-11: X's link led into a folder that did not exist. With the target's folder PRESENT the same save SUCCEEDS and creates the target through the link -- `saved+1`, the link left a link (the round-14 data-loss lens's C6 and Z9, two runs; the round-15 rulings). "A dangling link fails the save" holds only for the missing folder] |

So the FileView's own save does not replace a link, and by R24b nothing
changes on the service's side. Q, R, S, T and U do not depend on the helper
and read the same in both runs.

**D-DOC-8, corrected where it stood (2026-10-14).** The round-13 sentences
that made the session's own saves the variable were wrong and are corrected
in place, not appended to: this file's round-13 section (the paragraph on
the disagreeing measurements and decision request 1), `ARCHITECTURE.md`
section 5 and its section-11 risk 1, the README's Troubleshooting entry for
a file damaged under a running shell, `UX-SOURCES.md` 5.10 item 4, the
contract's FileView facts four and six, `QA.md` TC-CFG-16, `QA-SOURCES.md`
SRC-MIG-41, -44 and -47, and the harness README's round-13 notes. Each now
says what was measured, with the run that measured it: before R24c the
variable was whether the state directory existed when `stateFile` first
loaded (the round-13 live lens on lane-key-p2 and on a 0.13.6 export;
spike sequence Q); since R24c every session re-arms or never lost the watch,
observed for the fresh-install session by key-scenario B16 -- after an own
save included -- and for an existing directory with no own save by B5-B7
and B9. The existing-directory session AFTER an own save is observed by the
committed spike (`RESULT-2026-10-13.txt`, every sequence) and by the
round-13 live lens's rig (session scratch), and by no key-scenario segment
[round 15, R25d: key-scenario B21 observes it now -- an in-app save lands,
then garbage written in place is noticed and told once].
D-DOC-9: this file's round-11 open item (5) and the README's `playlistUrl`
row no longer say `omarchy bar set` "still offers" the keys. D-DOC-10: the
README says what a hand edit costs.

**Rule 15, lane A's searches (lane-key-q1), recorded so the next person
inherits them.**
- The D-SRC-22 shape (a reload ignored, then written over): every FileView in
  `Service.qml` the service writes with `setText`. Only `stateFile`.
  `manifestFile`, `channelsFile`, `failedFile`, `playlistStatusFile`,
  `epgFile` and `epgStatusFile` are written by the helper only and applied on
  every load, with no ignore branch: cleared.
- The D-SRC-23 shape (a writer that replaces a symlink, or reads a dangling
  one as absent): every `write_json_atomic` / `write_text_atomic` caller in
  the helper. Fixed: `state.json` for all five verb writes and the D-ID-1
  remap. Left: the cache JSONs, logos, the EPG window and `failed.json`,
  which live in the plugin's own 0700 cache directories, where a rename over
  a link replaces the plugin's own cache. Already guarded: the config shield
  (`O_NOFOLLOW`) and the player lock (`fchmod` gated on S_ISREG). The tolerant
  `read_json` readers answer `None` for a dangling link and no write follows.
- The D-SRC-26 shape (a file where a directory should be): the init answers
  `not-a-dir` and every verb refuses it. NOT re-checked: the cache writers'
  `ensure_private_dir` over a file at a cache directory [round 15, R25c:
  checked, every caller -- a file there, or a link that leads nowhere, is
  now `folder_unusable` with a sentence and exit 1 where it was a
  traceback; the round-15 rulings list each].
- The D-SRC-24/25 shape (an unbounded start-up process): every process
  `Component.onCompleted` starts. `mkdirProc` is inside the one bound now.
  `configShieldProc`, `whichProc` and the `hypr*` probes neither open the
  state path nor gate the load (the round-13 claims lens cleared them too).
  `cacheProc` has no watchdog but runs only after `dirsReady` and gates
  nothing: left.
- Found and left, the KILL half's sibling: every other watchdog -- playlist,
  EPG, control, probe, player, the three PiP steps, logo, clipboard -- sends
  TERM only. The helper never ignores TERM today (the default disposition;
  the clipboard verb's handler reaps its child and exits), so nothing is
  stranded, but nothing would end a TERM-ignoring helper there.
- The R24c shape (a FileView whose directory may be absent at its first
  load): the cache FileViews are reloaded explicitly after every helper run,
  `manifestFile` is reloaded explicitly, and `failedFile` has no other writer
  and its in-memory map is authoritative: cleared.
- The R24e shape (a spawn handed `--state-dir`): only the active playlist
  fetch (fixed) and the init, which never rewrites an existing file. The
  probe carries none.
- The R24f shape (an add affordance in the no-write mode): `openAddForm` and
  `openXtreamForm` are the only form openers -- the Sources letters, Enter on
  an Add row, the form's Xtream link, the footer's Xtream button -- and all
  pass `addRefused`. `Service.addSource` already refused with
  `state_unreadable`.
- Mutation patches whose hunks R24a moved: `d3-save-parked.patch` and
  `r14-no-return.patch` re-made, the same decision broken with the same
  comment.

**This lane's search, by shape, over the documents (rule 15, R24h).**
- "The running shell does not re-read `state.json` after a helper write"
  (D-SRC-19 as filed): every hit in the nine files this lane writes. The
  statements of CURRENT behaviour are corrected or bracketed with round 14's
  measurement: `ARCHITECTURE.md` section 5 R9's bracket, section 5's round-13
  amendment, section 11 risk 1; this file's 4.4 step 2 bracket and its
  round-9, round-10 and round-12 records (each bracketed rather than
  rewritten, because they record what was believed then); the contract's
  FileView facts; the harness README's round-13 note. Cleared as history
  that already says it was later contradicted: the round-12 R22f paragraph,
  which carries its round-13 bracket and now a round-14 one.
- "A reload is ignored while a save is held" (R9 as written): `ARCHITECTURE.md`
  section 5 R9, this file's 4.4 step 2 and its round-3 R9 record, the
  contract's own-write fact: each bracketed with R24a's base rule.
- "`absent` and `absent-unconfirmed` share the folder sentence": this file's
  round-12 table (amended above) and `UX-SOURCES.md` 5.10's table (split).
- "Sources stays reachable as it is" / "Sources lists nothing" in the
  no-write mode: `UX-SOURCES.md` 5.10 item 2, 2.2, 5.3; `QA.md` US5 step 7.
- "`omarchy bar set` still offers" (D-DOC-9): the README's `playlistUrl` row
  and this file's round-11 item (5), both corrected. The contract's round-11
  bracket said it too and carries round 13's correction beside it; it is
  reworded so the wrong half no longer stands alone.
- "Nothing of yours is lost" (D-DOC-10): the README's Troubleshooting only;
  no other file in this lane's set promises it.
- Numbers carried from round 13 that round 14 moved: the README's harness
  count (112 -> 116, the summary line), the gate's floors (2,372 -> 2,459
  node, 1,180 -> 1,194 python), key-scenario's lettered floor (111 -> 115).

**Seen red (lane A).** Node, the round-14 suite against a `git archive dev`
export (ced1bd1): 2,459 checks, 85 failures (tip 2,459 / 0) -- all 34 merge
cases, the identity, `sameState` and conflict-line checks, R24a in all 16
harness modes, R24c's fresh-session and identity checks (8), R24d's mkdir
(2), R24e (2), the R24b faults (4), the R24b and R24f model checks (3 and
4), and the R9, R15, R11, D-ID-1, R22a-notice and R23c/R24d structural
pins the round re-pointed. Green on dev and seen red by mutation instead:
R24g's four, through `r24g-no-kill.patch` (4 of 2,459, exactly those four);
the D-SRC-15 base-reload control, through `matchesBase: false` (8: those
four and R24c's four identity checks); the R24c double check, through an
always-armed double (2, and one README check that scratch copy could not
find). Replacing the merge branch with a blind apply reads 16 failures, and
with an ignore 16, the same set: every R24a harness pin. One bookkeeping
check ("the fixture covers every field rule") was not seen red; it reddens
only if fixture cases are deleted. Python against dev's helper: of 14 new
or changed `test_state` tests, 9 red (the dangling link, the link into a
missing folder, the valid link's write-through, the favourite in the target,
init's `link` twice, the not-a-dir init, the alarm, the deadline constant)
and 5 controls green there (read-through, a link to a directory or a FIFO,
the remap leaving a dangling link, no other verb arming the alarm, every
verb refusing not-a-dir); `PrivateBusIsolatesHome` 2 of 2. Live:
`--baseline dev` 113 / 3 (B15, B16, B18), and `--tree` with
`r24g-no-kill.patch` 115 / 1 (B17).

**Counts.** On dev ced1bd1: node 2,372 (and 2,372 with the own echo off);
python 1,180; qml spec 78; `qa-lib-test.sh` 472; key preflight 11;
key-scenario's live floor 111 lettered checks (`EXPECTED_CHECKS`), summary
112. On lane-key-q1 c6315d1 (lane A's report; `./scripts/check.sh` all
green on the tip at load 2.4, and on 3db244c, c078ef3 and 318af7f): node
2,459, and 2,459 with the echo off; python 1,194 (+12 `test_state`, +2
`test_harness_home`); qml spec 78; `qa-lib-test.sh` 472; key preflight 11;
`node scripts/split-model.mjs --check` 762 declarations in 18 parts;
key-scenario live floor 115 (B15-B18), forward 116 / 0 in 342.5 s on
318af7f (`key-20261014-095236-969838`), `--baseline dev` 113 / 3
(`key-20261014-095838-996891`), the no-kill tree 115 / 1
(`key-20261014-100528-1027361`); sources-scenario 66 / 0 and logo-scenario
33 / 0, each as the child of a nested headless cage on a private bus. The
gate's floors: `NODE_CHECKS_MIN` 2,459, `PY_TESTS_MIN` 1,194. Every live run
under a nested headless cage on a private D-Bus with no service
directories; the transcripts are in lane A's session scratch directory, not
the tree.

**Open for the lead (decision requests, not defects; the board's ids are the
lead's).**
- (1) The marker. "entryMigrated is true if either side has it" keeps a
  marker the base had and theirs dropped (an older writer -- 0.13.6's helper
  -- rewrote the file); "applied as today when nothing is held" drops it. So
  `merge(base, base, theirs) == theirs` fails for exactly that case. Lane A
  kept both rules literally (nothing held applies theirs; a held change
  keeps the marker) and the identity test names the one exception rather
  than hiding it. Which rule wins?
- (2) A dangling link that appears MID-session still reads as `absent` (the
  helper is not asked mid-session); its sentence now names both causes.
  Should a mid-session load failure re-run `state init` for the exact reason?
- (3) R24e gates `--state-dir` at the spawn: a no-write episode that begins
  while an active fetch is already running does not stop that fetch's remap
  (narrow -- the remap writes only a file it can parse, moves ids at most
  once per file). Left.
- (4) In the conflict pin, a hand-run `source remove` of the source the
  session had switched to clears `activeKey`, and reconcile then stands on
  the entry's mirror (A), as it already did. Intended after a foreign
  removal?
- (5) `mergeForeignText` runs the session outcome like the apply path; the
  harness stubs it, so the `session` field's merge is pinned in the fixture
  and not through the service.
- (6) Every watchdog but the start-up one is TERM-only (the sibling above).
- (7) This lane's: the Sources header in a MID-session block reads `Saved
  sources not loaded` over the records memory still lists and plays. It is
  the one source of copy R24f asked for; whether the header should say
  something narrower there ("not saved", say) is a copy decision, not made
  here [round 15: decided as D-SRC-38 -- `Saving has stopped`, through
  `Model.stateBlockedHeader`; observed by key-scenario B22].
- (8) This lane's: the existing-directory session AFTER an own save is
  observed by the committed spike and a lens rig but by no key-scenario
  segment (above). A B-segment that seeds the directory, makes an in-app add
  and then damages the file would close it [round 15: B21 is that segment].
- Rule 13: the round-12 open item (1) -- ids for the 0.13.6 losses -- is
  still not this lane's to close.

### D-SINK-19 round 15 rulings (lead, 2026-10-14; R25, on top of R1-R24, which stand)

**What the round-14 lenses found, on lane-key-q2 (116308b), now on `dev`
(002662d).** No P1. Five P2s, each boarded on 2026-10-14: D-SRC-29 (a
symlinked `state.json` goes unwatched once a tool replaces the link or the
entry at the path -- `jq` and `mv`, GNU `sed -i`, `rm` and `cp`, a backup put
back with `mv`, `ln -sfn` -- and the next save writes memory over the change,
while the round-14 README promised that case worked); D-SRC-30 (a backup
the user copied from the plugin's own file, put back after a later in-app
change, was ignored as the service's own write and then written over);
D-SRC-31 (a merge at the caps dropped the app's new source at 50, or saved
search at 20, silently, while the README promised both sides' new sources
are kept); D-SRC-32 (R24b's dangling-link rule missed its folder-level
sibling: over a dangling link at `~/.local/state/omarchy-iptv`, `state show`
and `source list` printed an empty state with exit 0 and the writers and
the init ended in a traceback); F-HARNESS-26 (two R24a decisions, a5 and a7,
survived the node suite in both echo modes, and the merge had no live
segment). P3s: D-DOC-11, D-SRC-33, F-HARNESS-27, F-HARNESS-28, D-SRC-34,
D-SRC-35, D-SRC-36, D-SRC-37, D-SRC-38. Every one is classified on the board
as present in 0.13.6 too, except where the round-14 code made the promise
that turned it false.

**The 0.14.0 ship bar (the owner's, 2026-10-14).** No P1; nothing worse than
0.13.6 (`main` ca5a3a5); no promise in a shipped or project document that the
code does not keep. Everything else is filed and does not block. This round
was meant to make 0.14.0 cuttable, so its scope was fixed: the five P2s and
the false statements below, and nothing else; a new finding is reported with
evidence and not fixed.

**The lead's ruling, R25 (2026-10-14).**

R25a. D-SRC-30: AN ECHO IS ONLY A TEXT STILL IN FLIGHT. A reload is the
service's own echo only when its text is one the service asked to write and
has not yet seen land (the burst since the last landed save -- D-SRC-16's
coalescing is why that can be more than one text); `recentSaves` is narrowed
to exactly that, cleared as each save lands. A text equal to an own save that
has already landed and been superseded is ANOTHER WRITER'S (a backup put
back) and goes through R24a: merged while a change is held, applied when none
is. Pin the lens's sequence FAV, BAK, DEL, RSTB, FAV (the restore must win)
through `tests/service-harness.js` on both hosts and echo modes, AND prove a
coalesced burst's mid-burst echo is still recognised (rule 10: measure, do
not assume, what text a burst's echoes carry); red on dev.

R25b. D-SRC-31: A MERGE NEVER DROPS SILENTLY. When the merged result exceeds
MAX_SOURCES or the saved-search cap, theirs keeps its place (the later
writer, as for a conflict) and the app's additions past the cap are dropped
AND the user is told once (a notification naming how many and the cap, never
a URL or a label) with one journal line per dropped key. One Model function
decides it; pinned, red on dev.

R25c. D-SRC-32: THE STATE FOLDER GETS THE FILE'S RULE. A symlink at the state
folder is followed when it leads to a directory and refused when it dangles
or leads to anything else: every verb exit 1 with a sentence, untouched;
`state init` answers a `found` value the model maps to its own copy. MEASURE
what `ensure_private_dir`'s chmod does through a valid folder link and decide
by the R24b principle (never change what the user's link points at without
saying so; if it chmods the target, say where in the README). Rule 15: every
`ensure_private_dir` caller (the cache folders, the runtime socket folder,
the logo folder) over a dangling link, each with a verdict. Pins run the real
helper as a subprocess with a timeout; red on dev.

R25d. F-HARNESS-26: THE MERGE IS OBSERVED. Node pins that go red for the
round-14 data-loss lens's mutants a5 (the base not moved to theirs after a
merge) and a7 (the in-flight half of the re-save decision), shown red on
mutation patches kept under `spikes/key-mutations/`; a live key-scenario
segment for R24a (a failed state write, then a hand-run helper write: both
changes survive the next save AND a restart; plus the restore of R25a); and a
live segment for the existing-folder session damaged after an own save. Red
on dev where the defect lives, on the mutation otherwise.

R25e. D-SRC-29: STATE THE LINK'S LIMIT, DO NOT FIX IT THIS ROUND. Measured: a
writer that replaces the link or the entry at the path (`mv`, `sed -i`,
`rm` + `cp`, `ln -sfn`) leaves the view unwatched and the next save writes
over the change; one explicit `reload()` re-arms it. That lever is filed for
a later release. This round, every document that mentions a symlinked
`state.json` says exactly what is noticed (writes through the link, in
place, and the helper's) and what is not (a tool that replaces the link or
the file behind it), and what to do (edit the target in place, or restart
the shell straight after such a tool and before using the guide). Lane A adds
the matching sentence to the helper's own help text if it mentions links.

The false statements the bar forbids, each to be fixed where it stands:
D-DOC-11 (contract fact seven and the harness double's dangling-link save:
with the target's folder present the save CREATES the target; model what was
measured, rule 10); D-SRC-35 (the README's "putting a good copy back in place
is enough on its own", read for a link whose target came back); F-HARNESS-28
(key-scenario's printed `--baseline` footer); D-SRC-36 (the conflict journal
line as quoted in the README and UX-SOURCES: the grammar fixed in the model
and every quotation together); D-SRC-37's docstring, which stated a set order
the code does not keep. Cheap and allowed, and only these: F-HARNESS-27
(`test_state`'s in-process init must not leave `SIGALRM` armed in the test
runner); D-SRC-34 (a sentence instead of a traceback when writing through a
link into an unwritable folder); D-SRC-38 (in a MID-session block the
Sources header says saving has stopped, not that sources were not loaded --
one Model function, the notice copy family).

**What the tree does (lane-key-k1, lane A: 56a30d5 the model and service
half of R25a, R25b, R25d's node pins, D-SRC-36, D-SRC-37 and D-SRC-38;
1d8599f the helper half of R25c with its rule-15 callers, D-SRC-34,
D-DOC-11's double, F-HARNESS-27; a800bd5 and b10b5b6 key-scenario B19-B22;
0ccea19 the counts, F-HARNESS-28 and the cage lifetime).**

- R25a. `Service.recentSaves` is the burst of texts asked for since the last
  save that LANDED: `saveState` appends each text it asks for (capped at
  eight only so a run of failed saves cannot grow it for ever), and
  `stateFile`'s `saved`, in the branch that sees the last text asked for
  land (`Model.stateSaveLanded`), clears it. So a reload whose text is an
  own save that already landed and was superseded is not `own-write`; it is
  foreign, and R24a decides it. The echo of the save that just landed now
  arrives with nothing held and carries the base itself, which the old
  eight-text record had swallowed as `own-write`; `Model.reloadDisposition`
  gains one input, `memoryMatchesBase` (`sameState(userState,
  landedState)`), and one arm: nothing held, the text the base and memory
  the base -- ignore, reason `unchanged`. With memory NOT the base (the
  no-write mode refused a change and a good copy was then put back) the
  same text is applied as `file-newer`, as before. Pinned through
  `tests/service-harness.js` on both hosts and both echo modes: `R25a
  (<host>, <echo>): FAV BAK DEL RSTB FAV -- ...` (the restore applied as
  `file-newer`, never `own-write`, and the next save keeps it), `... FAV BAK
  UNFAV RSTB FAV ...` (a favourite removed in-app after the backup comes
  back), `... controls ...` (a backup taken before any own save; the landed
  echo ignored as `unchanged`) and `... a coalesced burst of three saves --
  the mid-burst echo carries the first text while the third is in flight and
  is still recognised as own-write ...`. Live: key-scenario B20 (`restored:2
  records:2 label:after-restore restart:2`). What it rests on is measured
  (below).
- R25b. `Model.mergeForeignState` applies the caps itself, where it knows
  whose element is whose: theirs' records, searches and groups first (theirs
  alone is within every cap -- it was read through `parseState`), then ours'
  additions; what goes past `MAX_SOURCES` (50), `MAX_SAVED_SEARCHES` (20) or
  `MAX_HIDDEN_GROUPS` (200) -- the third is rule 15's sibling, found and
  fixed -- is always ours' additions, at the tail, and is returned as
  `dropped` (`sources`: the keys; `savedSearches` and `hiddenGroups`:
  counts, because a query and a group name are the user's or the provider's
  text). `Service.mergeForeignText` logs `Model.mergeDropLines(dropped)`, one
  `omarchy-iptv: ...` line per element, and when there is any sends ONE
  notification, `Model.mergeDropNotice(dropped)` through
  `Model.notifyArgv("mergeDropped", ...)`, replace id 74018, normal urgency.
  The text, verbatim: journal `state.json was changed by another program
  while a change made here was not yet saved; the source <key> added here
  was not kept (the limit is 50 sources)` (and `...; a saved search made here
  was not kept (the limit is 20 saved searches)`, `...; a group hidden here
  was not kept (the limit is 200 hidden groups)`); notification `Not every
  change was kept` / `Another program changed state.json while a change made
  here was not yet saved, and together they went past a limit. The other
  program's version was kept, and 1 source added here (the limit is 50
  sources) was not kept. Make room, then add it again.` -- plural and joined
  with `and` when more than one kind or element was dropped. Node: `R25b:
  mergeForeignState at every cap -- ...`, `R25b: mergeDropLines ...;
  mergeDropNotice ...`, and through the harness on both hosts and echo modes
  `R25b (<tag>): at 49 sources, an in-app add whose save FAILED, then a
  hand-run state source add ...` and `R25b (<tag>): at 19 saved searches, an
  in-app save of a search IN FLIGHT and a foreign write adding another ...`.
  No live segment: reaching a cap live needs 49 records seeded, which the
  ruling did not ask for.
- R25c. The helper: `broken_folder_link(directory)` answers the first
  component of the state folder's path that exists, when it is a symbolic
  link that does not lead to a folder; `cmd_state` asks it before anything
  else. `state init` answers `found: folder-link`, `created: false`, exit 0,
  nothing created; every other verb exits 1, `state_unreadable`, `the state
  folder is a symbolic link whose target is missing or is not a folder;
  nothing was written` -- `show` and `source list` included, which printed
  an empty listing with exit 0 before. `ensure_private_dir` refuses the same
  shapes for EVERY caller with `FolderUnusable` (an `OSError`, so a caller
  that already downgrades one to a warning keeps doing so), which `main()`
  reports as code `folder_unusable`, `<path> is a symbolic link whose target
  is missing or is not a folder; nothing was written` or `<path> is not a
  folder; nothing was written`, exit 1, never a traceback. A link at a
  folder that DOES lead to a folder is followed, and the folder it leads to
  is made 0700 (measured, below; decided: it is the plugin's own folder,
  wherever the user put it, so it gets rule 6's mode, and the README says
  so). The model: `Model.stateInitFound` passes `folder-link` through,
  `Model.stateLoadDecision` re-reads once and then blocks with it, and
  `Model.stateUnreadableNotice` gains its row (the round-12 table above),
  naming the FOLDER. Python, the real helper as a subprocess under a
  timeout: `StateFolderLinkTest` (`test_a_dangling_folder_link_is_refused_by_every_verb_and_left_alone`,
  `test_init_answers_folder_link_creates_nothing_and_exits_0`,
  `test_a_link_above_the_folder_is_refused_by_show`,
  `test_a_valid_folder_link_is_followed_by_every_verb_and_its_target_made_0700`,
  `test_d_src_34_a_file_link_into_a_folder_that_cannot_be_written_is_a_sentence`),
  `FolderLinkSiblingsTest` (`test_each_caller_answers_a_sentence_and_writes_nothing`)
  and `test_r25c_a_logo_folder_link_that_leads_nowhere_is_a_sentence_and_nothing_is_written`
  in `tests/test_logos.py`; node `R25c: stateInitFound passes folder-link
  through; ...` and `R25c (<tag>): a start over a state FOLDER link that leads
  nowhere ...` on both hosts and echo modes. No key-scenario segment drives a
  folder link.
- R25d. Node, through the harness on both hosts and echo modes: `R25d
  (<tag>): a5 -- while a failed save is held, the helper adds a favourite
  and then removes it again: the second write is compared with the base the
  FIRST moved it to ...` and `R25d (<tag>): a7 -- a foreign write that
  already carries the in-flight favourite plus another lands first: ... the
  merge is saved again ...`, each red on its mutation patch
  (`spikes/key-mutations/r25d-a5-base-not-moved.patch`, 4 of 4 pins;
  `r25d-a7-no-inflight-half.patch`, the four a7 pins and the in-flight R25b
  saved-search pin). Live, key-scenario B19-B22, each in the scenario's own
  nested cage on a private bus. B19, R24a's first live observation: the
  state folder loses `w` under the running shell, so the in-app label
  change's save fails and is HELD; two hand edits IN PLACE (a 0600 file needs
  no folder `w`) add a favourite and remove it again inside that one window,
  which is a5's shape; a hand-run helper write lands (and makes the folder
  0700 again); a second in-app change follows -- both in-app changes and the
  helper's favourite are in the file, the favourite the hand edits removed
  stays removed, and a restart stands on all of it (`held:true
  edits:true/true helper:0 merged:3 labels:A=in-app-two,C=in-app-one
  favs:t:helper.uk restart:in-app-one,in-app-two/t:helper.uk`). a7's window
  is milliseconds wide and is pinned in node only, as the ruling allows. B20
  is R25a's restore. B21, the existing-folder session damaged after an own
  save: a migrated install starts, an in-app change's save LANDS, then
  garbage is written in place -- noticed and told once (`blocked:unparsed
  told:1 file:garbage{`). B22, the same block's Sources header (`header:Saving
  has stopped rows:2`).
- R25e. Not fixed, as ruled; the documents state the limit (below). The
  helper's own help text (`state --help` and the module help) mentions no
  symbolic link, so it gains no sentence.
- D-DOC-11. `tests/service-harness.js` models what was measured: a fault
  `dangling-link-nodir` (the target's folder missing) fails the view's save,
  and `dangling-link` (the folder present) SUCCEEDS and creates the target,
  after which the link leads somewhere; `folder-link` fails it, because there
  is no folder for the temporary file. Pinned `D-DOC-11 (<host> host, the
  double): ...`, red against dev's double on both hosts.
- D-SRC-34. `write_state_file` turns an `OSError` writing THROUGH a link into
  `state_unwritable`, `state.json is a symbolic link into a folder that
  cannot be written (Permission denied); nothing was written`, exit 1, the
  temporary file removed and the folder's mode unchanged (and `state.json
  could not be written (...); nothing was written` at the path itself).
- D-SRC-36. `Model.mergeConflictLine` reads `... kept the other program's
  version of the source <key> (<fields>)` and `... kept the other program's
  version of activeKey`.
- D-SRC-37. `mergeForeignState`'s comment states the set rule the code keeps:
  theirs' elements in theirs' order, minus what ours removed since the base,
  then ours' additions -- the same SET as "ours, plus what theirs added,
  minus what theirs removed", in theirs' ORDER. The rest of D-SRC-37 (a merge
  can leave `activeKey` naming a source the other side removed or re-keyed,
  with no conflict line; `failedProc` and `whichProc` unbounded) is filed and
  not this round's. [2026-10-24, P23 lane A: both halves fixed. (a) a merged
  pointer naming no merged record falls back to no active source IN THE
  STATE, the way `source remove` and `Model.removeSource` clear it (R3), and
  the fall-back is a conflict `{ field: "activeKey", key, fields:
  ["removed"] }` whose journal line says `... version of activeKey (the
  source <key> it named is gone, so no source is active)`. (c) `failedProc`,
  `whichProc`, `cacheProc`, `configShieldProc` and the two PiP start-up
  probes each have a TERM-only watchdog at `helperTimeoutMs`
  (`ARCHITECTURE.md` section 5's 2026-10-24 amendment).]
- D-SRC-38. `Model.stateBlockedHeader(reason, path, midSession)`: `Saving has
  stopped` in a block that began after a state loaded, the notice's title
  otherwise; `Model.sourcesHeaderRight` takes the fourth argument and
  `Guide.qml` hands it `service.stateLoaded`. Node `D-SRC-38:
  sourcesHeaderRight / stateBlockedHeader -- ...` and `D-SRC-38
  (structural): the guide hands the header the service's stateLoaded ...`;
  live B22. The notification and the guide body keep the start's title in a
  mid-session block (open question 2 below).
- F-HARNESS-27. `tests/test_state.py`'s in-process `run()` disarms the
  helper's init alarm after every call, and so does the second in-process
  runner rule 15 found, `tests/test_source.py`'s; pinned
  `test_f_harness_27_an_in_process_init_leaves_no_alarm_in_the_test_runner`
  (red with the disarm deleted: `AssertionError: 30 != 0`).
- F-HARNESS-28. key-scenario's printed `--baseline` / `--tree` footer leads
  with round 15's sentence (B20 and B22 red on dev; B19 and B21 seen red by
  mutation), and every older sentence names the tree it was measured on and
  says "were". The cage's lifetime is 1500 s, inside `private-bus.sh`'s 2400
  s: a mutated tree whose waits all time out outlived 500 s and read
  NOSTATE, a red for the wrong reason.

**What a burst's echoes carry (R25a), measured 2026-10-14 by lane A.**
`scripts/dev-harness/spikes/filewatch/measure.sh <helper> r25`, the committed
`shell.qml` FileView with an ordered signal log and `burst` / `spread` IPC,
in a nested headless cage on a private D-Bus; two runs (REPS 3 with 8 busy
loops, load 1.2-7.2; REPS 4 with 12, load 1.6-10.2), printed into
`RESULT-2026-10-14-r25.txt`. Run 1's 0 ms spreads used a `Timer` of interval
0 that never fired, and run 2 replaced it with a `Qt.callLater` chain. Over
the 100 bursts that saved, 85 echoes (a `loaded` after the view's own
`setText`): every one carried the text of the latest `saved` before it; STALE
0 (an earlier text of the burst after the last text's `saved`), superseded 0,
and none arrived while a later text of the burst was already asked (0 of 85).
Every in-turn burst raised one `saved` per `setText` -- no coalescing in this
rig, where the 26-write probe of 2026-10-12 saw some. So clearing
`recentSaves` when the last text lands cannot mistake a stale echo for
another writer's. The node double is MORE adversarial than the measurement
(rule 10 allows that direction): in coalesce mode it delivers an echo after
every `saved`, mid-burst included, and the coalesced-burst pin shows that
echo still reads as own-write; `spikes/key-mutations/r25a-clear-every-saved.patch`
(clear on every `saved`) turns it foreign.

**What `ensure_private_dir` does through a link at a folder (R25c), measured
2026-10-14 by lane A.** `scripts/dev-harness/spikes/folder-link/measure.py
<helper>`, the helper as a subprocess (`python3 -B -I`, timeout 30), dev's
helper and lane-key-k1's, printed into `RESULT-2026-10-14.txt` beside it:

| Shape | dev 002662d | lane-key-k1 |
|---|---|---|
| a link to a 0755 folder: `show`, `source list` | followed; the folder's mode unchanged | the same |
| a link to a 0755 folder: `init`, `favorite add` | followed; the TARGET made 0700; the link left a link | the same |
| a link to a 0500 folder: `favorite add` | succeeds; the target made 0700 | the same |
| a dangling folder link: `show`, `source list` | exit 0 with an EMPTY state | exit 1, `state_unreadable` |
| a dangling folder link: `init` | `FileNotFoundError` traceback, `internal` | `found: folder-link`, `created: false` |
| a dangling folder link: `favorite add`, `clear-recents` | traceback, `internal` | exit 1, `state_unreadable` |
| a folder link to a FILE: `show`, `favorite add` / `init` | exit 1, the not-a-dir sentence / `not-a-dir` | exit 1, `state_unreadable` / `found: folder-link` |
| a `state.json` link into a 0500 folder: `favorite add` (D-SRC-34) | `PermissionError` traceback, `internal` | exit 1, `state_unwritable`, the folder still 0500 |
| a cache folder dangling: `cache migrate`, `cache prune`, `failed mark` | traceback, `internal` | exit 1, `folder_unusable` |
| the cache's `sources/` dangling: `cache migrate` | exit 0, silently | exit 1, `folder_unusable` |
| a cache folder or the runtime folder linked to a 0755 folder: `failed mark`, `cache migrate`, `player stop` | followed; the target made 0700 | the same |
| the runtime folder dangling: `player stop` | traceback, `internal` | exit 1, `folder_unusable` |

The logo folder (`write_logo`) is pinned in `tests/test_logos.py`;
`ensure_player_dirs` (screenshots, watch-later, shader cache) keeps turning
an `OSError` into a warning, `FolderUnusable` included. A dangling link ABOVE
the state folder (an `XDG_STATE_HOME` that is a link) is `broken_folder_link`'s
too, and pinned.

**What the FileView does when a link at `state.json` is REPLACED (R25e),
measured by the round-14 data-loss and claims lenses.** Their rigs are in
the session scratch directory, not in the tree: a bare FileView declared as
`stateFile` (`fvlinks.sh`, `fvlinks2.sh`) and a scratch copy of the
filewatch spike with a set `rk`, each in a nested headless cage on a private
bus, and the real `Service.qml` driven live (`probe14.sh`); load 2.2-5.6.

| Sequence | Start | What happened |
|---|---|---|
| C8, C9, C11 | a link to a file | a regular file `mv`'d over the PATH (the `jq` + `mv` idiom), `rm` + `cp`, or the target in the same folder: `changed:0` for that write and for a later in-place write of the path; the next own save wrote memory over it |
| C10 (control) | a regular file | a regular file `mv`'d over it: `changed:1 loaded:2` -- seen |
| C1, C1b, Z4, Z6, Z6b | a link to a file | the link re-pointed (`ln -sfn`) to a new target: nothing raised for the relink, for a later helper write or for an in-place write to the new target; the next own save replaced the new target's contents with the session's memory |
| Z7 | a link to a file | re-pointed, then ONE explicit `reload()`: `loaded+1`, and every later helper and in-place write seen (`fileChanged+1 loaded+1`) |
| Z1, Z2, Z3, Z5 (control) | a link to a file | an in-place edit of the TARGET, a rename onto the TARGET's own path, own saves: all seen |
| M1-M3 (control) | a regular file | moved into a dotfiles folder mid-session and linked back (`mv` + `ln`, or `cp` + `ln`): helper and in-place writes seen afterwards |
| Z8 | a link to a file | the target removed (`fileChanged+1 loadFailed+1`: the session blocks as `absent`), then restored: `fileChanged+0 loaded+0`, and a later helper write too -- never seen again (D-SRC-35) |
| Z9, C6 | a link to a file | the target removed with its folder kept, then an own save: `saved+1`, the target CREATED through the link (D-DOC-11) |

So a replacement at the PATH -- of the link, or by a file over the link --
leaves the view watching something that is no longer there; a write to the
TARGET's own path, in place or by rename, is seen. 0.13.6 loses the same edits,
and its own helper also replaced the link. The lever (one `reload()`
re-arms, Z7) is filed for a later release; nothing in the tree re-arms the
view after a replacement it cannot see.

**False statements corrected where they stood (lane-key-k2, the documents
lane).**
- D-SRC-29 (R25e) and D-SRC-35: the README's `state.json` entry under "Files
  it writes", its Troubleshooting bullets on a symbolic link, on a file
  changed while the shell runs and on "Saved sources not loaded";
  `UX-SOURCES.md` 5.10 items 5 and 6; the contract's fact seven;
  `ARCHITECTURE.md` section 5's round-14 amendment and security standard 5;
  `QA.md` TC-CFG-16 and TC-CFG-21; `QA-SOURCES.md` SRC-MIG-49. Each now says
  what is noticed (the helper's writes, a write through the link, an edit of
  the target in place or by a rename onto the target's own path), what is
  not (a tool that replaces the link or puts a file over it: `mv`, `sed -i`
  on the link's path, `rm` and `cp`, `ln -sfn`), and what to do (edit the
  target in place, put a backup back with `cp`, or restart the shell
  straight after such a tool and before using the guide); and that a link
  whose target went missing is not noticed coming back.
- D-DOC-11: the contract's fact seven, this file's round-14 sequence X, the
  harness README's set `r24` note; the double was lane A's.
- D-SRC-36: every quotation of the conflict line -- the README, `UX-SOURCES.md`
  5.10 item 8, this file's round-14 section and its model table, `QA.md`
  TC-CFG-20.
- D-SRC-30's promise ("a backup put back is re-read"): it is now true, and
  the one case where a restore has no effect is stated where the promise is
  (a copy equal to what the file already holds while a change made here
  waits to be saved: the README and `UX-SOURCES.md` 5.10 item 8).
- D-SRC-31's promise ("both sides' new sources are kept"): the README and
  `UX-SOURCES.md` 5.10 item 8 now add the caps and the notice.
- The round-14 records that said no key-scenario segment observes the
  existing-folder session after an own save, or the merge (`UX-SOURCES.md`
  5.10 item 4, `QA.md` TC-CFG-16 and TC-CFG-20, `QA-SOURCES.md` SRC-MIG-41,
  -44 and -48, this file's round-14 section, the harness README's round-13
  and round-14 notes): bracketed with B21 and B19.
- The README's harness count (116 -> 120, the summary line).

**Rule 15, lane A's searches (lane-key-k1), recorded so the next person
inherits them.**
- R25a's shape (an own text treated as an echo after it was superseded):
  `recentSaves` is the only record of own texts and `applyUserState` its
  only reader. `lastSaveText` is compared with the view's text only in
  `onSaved` and `onSaveFailed`, the landing, which is not an echo test:
  cleared. The other FileViews are written by the helper only and have no
  own-write test: cleared.
- R25b's shape (a cap applied silently after a merge): in
  `mergeForeignState`, `sources`, `savedSearches` and `hiddenGroups`; the
  third FIXED as the sibling. Favourites have no cap; `recents` and the
  whole-field values are taken whole, not added: cleared. The round-14
  reviewer's transient (a 51st record in memory while a URL edit's probe
  runs): cleared -- the edit keeps the replacement in `probeEdit`, never in
  `userState`, and its commit removes the old record first. A NEW finding in
  the same shape outside the merge, not fixed (open question 1 below).
- R25c's shape (a link at a folder that leads nowhere): every
  `ensure_private_dir` caller, through the real helper; the table above.
  A regular file in the chain is a sentence too now (`is not a folder`),
  where it was a `NotADirectoryError` traceback; the state verbs keep the
  existing `not-a-dir`. The D-ID-1 remap over a dangling folder: `read_json`
  answers `None` and nothing is written (unchanged, cleared).
- D-SRC-34's shape (a write refused in a folder that is not chmod-ed): only
  `write_state_file` writes with `private_dir` false; every other
  `write_json_atomic` caller is in the plugin's own folders, which
  `ensure_private_dir` repairs: cleared.
- D-DOC-11's shape (the dangling-link save stated wider than measured): the
  double and `measure.sh`'s `dangle` wording corrected; the RESULT files are
  records of what was measured and are accurate.
- D-SRC-36: `mergeConflictLine` is the only composer and no code quotes the
  old string. D-SRC-38: `sourcesHeaderRight` is the only header composer; the
  guide body's notice and the notification keep the start's title (open
  question 2). F-HARNESS-27: the second in-process runner,
  `tests/test_source.py`'s, fixed the same way. F-HARNESS-28: the footer is
  the only printed text that cites a red.

**This lane's search, by shape, over the documents (rule 15).**
- "A symlinked `state.json` is noticed whatever writes it" (D-SRC-29): every
  sentence in the nine files this lane writes that names a symbolic link at
  the state path, or promises that another program's change is re-read --
  the README (the "Files it writes" entry, three Troubleshooting bullets and
  the helper-refusal bullet's "picked up by the running shell"),
  `UX-SOURCES.md` 5.10 items 5, 6 and 8, `UX.md` 6.1's round-14 bracket and
  6.3's row, the contract's facts six and seven, `ARCHITECTURE.md` section 5
  and security standard 5, `QA.md` TC-CFG-21, `QA-SOURCES.md` SRC-MIG-49, the
  harness README's set `r24` note. Corrected where a sentence promised more
  than the measurement; cleared where it already named only the helper's
  writes (contract fact seven's last sentences, the R24b records).
- "Putting a good copy back is enough" (D-SRC-35): the README's no-write
  bullet and `UX-SOURCES.md` 5.10 item 5 (corrected); `QA.md` TC-CFG-16
  ("putting a good file back lifts the mode", B7: a regular file, true as
  written; narrowed to say so).
- "A dangling link fails the view's save" (D-DOC-11): the contract, this
  file's sequence X, the harness README's set `r24` note, `ARCHITECTURE.md`'s
  round-14 amendment (which says only that the init answers `link`:
  cleared).
- "A merge keeps both sides" (D-SRC-31): the README, `UX-SOURCES.md` 5.10 item
  8, `QA.md` TC-CFG-20, this file's round-14 merge rules (bracketed);
  `ARCHITECTURE.md` section 5's round-14 amendment (bracketed).
- "Sources in a mid-session block reads `Saved sources not loaded`"
  (D-SRC-38): `UX-SOURCES.md` 3.2.6 and 5.10 item 4, `UX.md` 6.3, the README's
  no-write bullet, `QA-SOURCES.md` SRC-MIG-52.
- "A state folder that is a link" (R25c): none of the nine files said
  anything about it before this round; the README, `UX-SOURCES.md` 5.10 items
  1 and 6, `UX.md` 6.3, `ARCHITECTURE.md` security standard 5 and `QA.md` /
  `QA-SOURCES.md` now do. Whether the shell's watch notices changes when the
  FOLDER is a link has not been measured, and the documents say so rather
  than extending the file link's facts to it. [Integration, 2026-10-14:
  measured since by both round-15 data-loss and claims lenses, 2026-10-14: through a valid folder link the service sees a helper write, a temp-and-rename edit and an in-place edit, and keeps all three; re-pointing the folder link (`ln -sfn`) raises nothing, nor does a later edit in the new folder, and the next own save writes the session's state into the new folder's `state.json` (D-SRC-40, the folder twin of D-SRC-29); the README, UX-SOURCES 5.10 and the contract now say so.]
- Numbers round 15 moved: the README's harness count (116 -> 120), the
  gate's floors (2,459 -> 2,502 node, 1,194 -> 1,202 python), key-scenario's
  lettered floor (115 -> 119).

**Seen red (lane A).** Node, the tip's `tests/` in a `git archive dev`
export: 2,502 checks, 36 failures in both echo modes (tip 2,502 / 0) -- R25a's
four pins on all four host and echo shapes (16), R25b's two service pins (8),
R25c's folder-link start (4), the R25b model pins (2), R25c's model pin (1),
D-SRC-38's (2), the reload fixture's R9 and R15 (2) and the conflict-line
grammar (1). The D-DOC-11 double pin is red against dev's
`tests/service-harness.js` on both hosts (2). Green on dev and seen red by
mutation instead (`spikes/key-mutations/`, applied to an export; failures
with own echo `load` / `none`): `r25d-a5-base-not-moved` 4 / 4, exactly the
a5 pins; `r25d-a7-no-inflight-half` 8 / 8, the a7 pins and the in-flight
R25b saved-search pin; `r25a-keep-landed` 16 / 16, every R25a pin;
`r25a-clear-every-saved` 13 / 11, among them the coalesced-burst pin with the
echo on; `r25b-silent-drop` 8 / 8, every R25b service pin;
`d3-save-parked` (re-made, R25a moved its hunk) 10 / 10, the D-SRC-15 pins
as before. Python, the tip's `tests/` against dev's helper: `test_state` 13
failures and 5 errors, all in `StateFolderLinkTest` and
`FolderLinkSiblingsTest`; `test_logos`'s logo-folder pin errors (no
`FolderUnusable`); the valid-folder-link test is a control dev passes, which
shows that behaviour unchanged. Live: `--baseline dev` 118 / 2 (B20
`restored:1 records:1 label:after-restore restart:1`, B22 `header:Saved
sources not loaded rows:2`; `key-20261014-144201-1513141`); `--tree` with
`r25d-a5-base-not-moved.patch` 119 / 1 (B19 `merged:2 ...
favs:t:helper.uk,t:h3.uk`: the favourite the second hand edit removed is
written back; `key-20261014-144904-1545059`); `--tree` with
`r25d-no-reload-on-change.patch` 110 / 10 (B21 `blocked: told:0`, with D3,
W3, W6, B7, B9, B16, B19, B20 and B22, every segment that needs a reload;
`key-20261014-151410-1653892`).

**Counts.** On dev 002662d: node 2,459 (the same with the own echo off);
python 1,194; qml spec 78; `qa-lib-test.sh` 472; key preflight 11;
key-scenario's live floor 115 lettered checks, summary 116. On lane-key-k1
0ccea19 (lane A's report; `./scripts/check.sh` all green on the tip at load
about 2.2, and on 56a30d5 and 1d8599f): node 2,502 (+43: 36 through the
service harness, 2 for the D-DOC-11 double, 5 model pins), the same with the
echo off; python 1,202 (+8: `StateFolderLinkTest` 5, `FolderLinkSiblingsTest`
1, the F-HARNESS-27 alarm 1, the logo folder link 1); qml spec 78;
`qa-lib-test.sh` 472; key preflight 11; `node scripts/split-model.mjs
--check` 766 declarations in 18 parts; key-scenario live floor 119
(B19-B22), forward 120 / 0 in 385.9 s at load 1.9-2.3
(`key-20261014-153026-1723779`; 120 / 0 on b10b5b6 too,
`key-20261014-143514-1482764`); sources-scenario 66 / 0 and logo-scenario
33 / 0, each as the child of a nested headless cage on a private bus. The
gate's floors: `NODE_CHECKS_MIN` 2,502, `PY_TESTS_MIN` 1,202. Every live run
under a nested headless cage on a private D-Bus with no service directories;
the real home's mesa shader cache mtime and `~/.config` / `~/.cache` listings
were unchanged across every run. The transcripts are in lane A's session
scratch directory, not the tree.

**Open for the lead (decision requests and new findings with evidence; the
board's ids are the lead's).**
- (1) A NEW finding, R25b's shape outside the merge, not fixed (lane A,
  `lane-k1/probe51.js` over the tip's `Service.qml` through
  `tests/service-harness.js`, both hosts). At 49 sources an in-app add passes
  the cap check; if a hand-run `state source add` takes the 50th place while
  the add's probe runs, that foreign write is applied (nothing is held yet),
  and the probe's commit then appends the in-app record: memory and the file
  hold 51 (`memory=51 file-records=51`), and the next start's `parseState`
  keeps 50 and drops the in-app source silently (`after-restart=50
  Z-after-restart=false warnings-naming-Z=0`). 0.13.6 does the same.
  Suggested P3; the fix is one guard at the commit, which already has a
  `too_many` code. The documents promise a notice only for a MERGE that
  passes a limit, which is what the code keeps, and the README and
  `UX-SOURCES.md` 5.10 item 8 name this case as not covered yet, so no
  document promises what the code does not do.
- (2) D-SRC-38 changed the Sources header only, as ruled; in a MID-session
  block the guide body's notice and the notification still use the start's
  title, `Saved sources not loaded`. Should they follow?
- (3) A restore equal to the CURRENT base while an in-app save is held (an
  in-app change lands, a copy is taken, the next change's save fails, the
  copy is put back): the text matches the base, so it is ignored as
  `save-failed`, and the held change wins at the next landed save. The disk
  never moved, so nothing the user wrote is lost, but the restore has no
  effect. The README and `UX-SOURCES.md` now say so; acceptable as stated?
- (4) A dangling `sources/` link under the cache root: `cache migrate`
  answered exit 0 over it and now refuses (`folder_unusable`, exit 1), so the
  start-up cache layout reports a failed migrate there. Every later fetch
  failed in a traceback on both trees anyway. Confirm this is not "worse
  than 0.13.6".
- (5) This lane's: whether the watch notices external changes when the state
  FOLDER (not the file) is a link was not measured; the documents state the
  folder link's behaviour for the helper and the start-up block only.
- (6) This lane's, two small slips in lane A's files (not this lane's to
  edit): `key-scenario.sh` calls B21 "D-DOC-9's half" where the open half it
  closes was D-DOC-8's (round-14 open item 8); and
  `spikes/key-mutations/README.md` says `r25a-keep-landed.patch` is caught
  by "key-scenario's B19 restore", where the restore segment is B20 (and
  cites "16 of 2491", a count from before the tip's 2,502).
- The round-14 open questions (1)-(6) stand as asked; (7) and (8) are
  answered above (D-SRC-38, B21).

### D-SINK-19 round 16 rulings (lead, 2026-10-16; R26, on top of R1-R25, which stand)

**What phase 1 of the clean-up found (three lanes, 2026-10-15 and
2026-10-16, each in a nested headless cage on a private D-Bus).**
- The sink lane (S) measured D-SINK-21 real, on the real `Service.qml` at
  dev 1c88877 (whose `Service.qml` is 0.14.0's byte for byte) and on 0.13.6
  (7c571a9): the state-folder link re-pointed while the shell ran at an
  EMPTY folder made by plain `mkdir` (0755), then one in-app label change --
  a new `state.json` at 0644, owner the user, holding the session's whole
  state with a source's credentialed guide URL, the folder left 0755, and
  nothing told (no block, no failed save, no notification, no journal
  line); a second save kept it 0644; the next start made the folder 0700
  and the file 0600. Its sibling (rule 15): a `state.json` LINK re-pointed
  at a file that did not exist yet, in an existing 0755 folder -- the save
  created the target at 0644 with the credential, on both trees. Who can
  read it: another account only through folders it can enter -- not inside
  this machine's 0700 home (`HOME_MODE 0700`, the user's group has no other
  members); not tried as another uid, which needs sudo. A bare FileView
  creates a missing file at 0666 & ~umask whatever `atomicWrites` says and
  keeps an existing file's mode; the user's shell runs at umask 0022. The
  lane measured a blocking peek (a second FileView, `blockLoading`, waited
  on inside `saveState`) closing both routes: 3 of 3 sink checks green
  where both shipped trees read 0 of 3.
- The watch lane (W) measured what the FileView does to a replaced or
  re-pointed link (the contract's eighth fact) and five ways to close
  D-SRC-29, D-SRC-40, D-SINK-21 and D-SRC-35 on the real `Service.qml`: A
  and A2 (an asynchronous read before every save), B (a periodic reload),
  C and C2 (a synchronous read). B cannot close the data loss -- at 10 s
  with a 1 s gap every segment was lost as on dev, a 0644 file with the
  secret included -- and costs 360 reloads an hour idle at 10 s, 1,800 at
  2 s. C2 closes all four on the first call but blocks the GUI thread on
  file I/O for every save (up to 29 ms measured under load; unbounded on a
  hung filesystem, which R23c and R24d treat as in scope). A2 closes them
  without blocking and D-SRC-35 on the second call. The lane also found
  D-SRC-46: a `setText` issued inside `stateFile`'s own `onLoaded` writes
  the file and never raises `saved` (16 of 16), so after an R24a merge's
  save the session read `stateSavesInFlight` 1 and `stateSaveFailed` true
  for good -- live on dev, and hidden by the node double (F-HARNESS-29).
- The harness lane (H) repaired the two always-red chno scenarios
  (F-HARNESS-21: the pre-Sources cache path, a wrapping `move -99`, dead
  stream URLs; F-HARNESS-22: N9's pair straddling a dead stream's clear),
  chno 46 / 0 and chno-entry 78 / 0 three times each on two trees, and
  found F-HARNESS-30: `run.sh`'s player reap sent TERM only, and six
  served players that ignored it spun for 35-48 minutes at 42-52 % of a
  core each.

**The lead's ruling, R26 (2026-10-16).**

R26a. ASYNCHRONOUS READ-BEFORE-WRITE (lane W's A2; lane S's blocking peek
and C2 are NOT taken: the shell never blocks its GUI thread on file I/O, the
R23c / R24d stance, and the peek does not merge). Every state save the gate
allows first reloads `state.json` and decides on what it finds through the
existing dispositions: the base -> write; a foreign text -> the R24a merge,
then write; a load failure -> the R22 no-write mode, nothing written, told
once. A save asked for inside any load is parked and deferred. The read is
skipped while one of our own writes is in flight. A 2 s watchdog: no load
-> save as today, counted and logged. Reasons met during the verify are
counted as `pre-save-*`. This closes D-SINK-21 (a 0644 `state.json` in a
re-pointed empty folder, measured real), D-SRC-29 (every replacement kind),
D-SRC-40 and D-SINK-21's file-link sibling; D-SRC-35 closes on the second
call (the first source call after the target returns is refused and lifts
the mode) -- accepted and stated.

R26b. NEVER `setText` INSIDE A FileView HANDLER. D-SRC-46 (new, P2, shipped
in 0.14.0): a `setText` issued inside `stateFile`'s `onLoaded` writes the
file but never raises `saved` (16 of 16 measured), so after an R24a merge's
save `stateSavesInFlight` stays 1 and `stateSaveFailed` stays true. The
deferral (`Qt.callLater`) fixes it. Rule 15: every `setText` and every write
in `Service.qml` reached from a FileView handler, listed with a verdict.
Pinned (the merge's save clears inFlight and saveFailed) and live (INLOAD).

R26c. RULE 10 FOR THE DOUBLE (F-HARNESS-29, new): `tests/service-harness.js`
models what was measured -- `setText` inside a load is silent (no `saved`;
the echo delivered), a save that creates the file creates it 0666 & ~umask
(0644 at umask 022) and keeps an existing file's mode, a re-point raises
nothing. Its red: the improved double goes red on the old `saveState`.
[lane-clean-f1, 2026-10-16, F-HARNESS-31 (the round-16 data-loss lens's
P2): the double still delivered the reload a FOREIGN change raises while
one of our writes was in flight, which the measured view does not
(`inflight-1.txt`, 30 of 30), and sixteen pins passed only because of it.
It drops that load now (`h.foreign`, counted in `droppedForeign`); the
sixteen -- R24a IN FLIGHT, R25d a7, R25b's in-flight saved search and
R26b's census, each x 4 -- are re-levelled to what the view does: a change
another program lands in the same instant as one of our writes is lost,
on this tree and on 0.14.1 alike, with no plugin-side lock against a
second process. Seen red both ways: the old wants on the new double, 16 of
2561 in each own-echo mode; the new wants on the old double, 16 of 2561.
`r25d-a7-no-inflight-half.patch` is now reddened by no node pin (8 -> 0):
the half it deletes is reached only by a foreign load during our write,
which the view does not deliver; whether any other load can reach it is
unmeasured.]

R26d. NO PERIODIC TIMER. A replacement with no save after it stays unseen
until the next save or a restart, and nothing is lost meanwhile because
nothing writes; the documents state it (FRESH), and an IDLE live segment
proves 0 reloads while idle.

R26e. Source verbs keep answering synchronously when their write is ISSUED
(R13); a write the verify then refuses is told by the R22 notification, and
the next call answers `state_unreadable`. Stated, not changed.

R26f. THE RE-LEVELS. The checks A2 turns red because their premise changed
are each re-levelled with a sentence naming why the premise changed and
what now observes the original concern; none is deleted to green;
key-scenario D3 and W3 stay discriminating (a verify does not satisfy the
save-parked count).

R26g. LIVE SEGMENTS in `key-scenario.sh`: S29-mv, S29-sed, S29-rmcp,
S29-ln, S40, S21 (no file created, `blocked=absent`, `told:1`), S35, INLOAD,
IDLE; each seen red three ways (the reload removed from `saveState`; the
deferral removed; the verb recheck removed), the mutation patches kept
under `spikes/key-mutations/`.

R26h. THE HARNESS. Lane H's branch taken whole, squashed into one green
commit. F-HARNESS-30 (new): every `--serve` scenario (player, m3, rewind,
pip, tls, text, chno, chno-entry) goes through `qa_reap_players` (TERM, a
bounded wait, KILL by pid, confirmed). The helper's own `player stop`
already escalates to SIGKILL (the D-LIVE-17 ladder): confirmed by reading,
`bin/` not changed.

R26i. The documents: the README's link and folder-link paragraphs say what
is now noticed and when (at the next save), FRESH, the first refused call
after a target returns, and that after re-pointing a folder link and
restarting, the NEW folder is what loads; the contract gains the measured
FileView facts; R26 as a dated ruling (this section).

**What the tree does (lane-clean-a1, lane A: 86d8265 lane H's branch
squashed; 5d193f2 R26a-c, the model, `Service.qml`, the double, the node
pins and the re-levels; 5ee0e5f R26g-h, key-scenario B23-B31, the four
mutation patches, `run.sh`'s reap).**
- R26a. `Model.stateSavePlan(ctx)` (in `model/state.mjs`) answers each
  save `join` (a read is already out: it decides this save too), `park`
  (no state loaded, or the directories not ready), `refuse` (the no-write
  mode and nothing a re-read can lift now: `init-timeout`, or the call IS
  the verify's own finish, or it runs inside a load, which is that read),
  `verify` (reload first), `defer` (ask again from a turn of its own) or
  `write`. A write is answered only to the verify's finish
  (`verifyDone`), or to a deferred turn (`writeTurn`) while one of our
  writes is in flight -- when the read is skipped, because the view drops
  a reload then (30 of 30) and the disk is that write. [Round 17,
  2026-10-20, R27a (D-SINK-22 window a): the second half is gone; such a
  save is answered `wait` and reads once that write has landed.] `Service.saveState`
  carries the answer out: `verify` sets `stateSavePending` and
  `stateVerifyPending`, calls `stateFile.reload()` and restarts
  `stateVerifyWatchdog` (2000 ms); whatever load arrives,
  `stateLoadArrived` decides it through the existing dispositions and,
  with the handler depth back at 0, `Qt.callLater(finishStateVerifyLater)`;
  `finishStateVerify` refuses the parked save if the load set a no-write
  mode (counted in `stateWritesRefused`) and otherwise issues it once. A
  load met during the read is counted as `pre-save-<reason>` in
  `stateReloadsByReason`, so D3 and W3 need a genuine `save-parked`.
  `Model.stateBlockRecheck` asks for one reload when a source verb
  (`sourcesReady`, so add, edit, switch and retry; and `removeSource`)
  meets a liftable mode -- not `init-timeout`, not inside a load, not while
  a read is out; the verb is refused either way. The counters for the
  harness: `stateVerifies`, `stateVerifyNoLoad` (the watchdog's),
  `stateVerifySkipped`, `stateVerifyRetries`, `stateSavesDeferred`,
  `stateVerifyMsMax`. The watchdog's console line: `state.json was not read
  back within <n> ms of a save; saving without the read`. [Round 17, R27a
  (window c): the watchdog no longer saves. Its first firing asks for the
  load once more (`... of a save; reading it once more`), its second puts
  the session in the no-write mode `read-timeout` (`... of a save, twice;
  nothing is written until a read answers`).] [Round 18, R28a: no block.
  Every firing keeps the save held and asks for the load again with the
  schedule's next bound: `state.json was not read back within <n> ms of a
  save; the change is kept and the file is read again, waiting <bound>
  ms`.] [Round 19, R29a: back to this bullet as written -- the watchdog
  saves without the read and logs `state.json was not read back within <n>
  ms of a save; saving without the read`, counted in `stateVerifyNoLoad`;
  6f1d176's body word for word (the round-19 rulings).]
- R26b. `stateInHandler` counts the depth inside `stateFile`'s handlers --
  `stateLoadArrived` (both load handlers) and `onSaved` / `onSaveFailed`,
  each in a `try` / `finally` -- and a save asked for at depth > 0 is
  `defer`red through `Qt.callLater(saveDeferredState)`. `stateFile.setText`
  is reached only below the plan's `write`, and the two flags that let a
  call write are raised only in `finishStateVerify` (entered only from
  `Qt.callLater` and the watchdog's Timer) and `saveDeferredState`
  (entered only from `Qt.callLater`). The rule-15 search is below.
- R26c. The double, as the contract's eighth fact describes it; pinned
  `R26c (<tag>): the double creates a missing file as 0666 & ~umask and
  keeps an existing file's mode ...` (`["644", "600", "664", "640"]`).
- R26d. No timer reloads `stateFile`. Node `R26d (<tag>): FRESH, stated --
  ...` (the replacement unseen, nothing written, the next save merges);
  live B31.
- R26e. Unchanged code, stated in the README and `UX-SOURCES.md` 5.10 items
  4 and 5; observed by B28 (`edit:true ... next:state_unreadable`).
- R26f. The re-levels, each with its sentence in the test or the script:
  R11 (structural: the `onSaved` window 400 -> 700 characters, the landed
  branch unchanged); R14 / R22a `parksBeforeDirs` (the gate is now one
  input of the plan; the pin matches the plan's join / park and refuse
  branches); R15 (the counted name now carries the `pre-save-` prefix,
  still one count before the decision); R13's burst x2 (saves in one turn
  join one read, so the burst is built behind a write in flight); R25a's
  coalesced burst x4 (the saves a turn apart); R21e D-SRC-18 at the
  migration x2 (the edit's read let finish before the save lands and the
  shell dies); R24a IN FLIGHT x4 and R25d a7 x4 (the read let finish so
  the save IS in flight when the helper write lands); R25b's saved search
  IN FLIGHT x4 (the same, and it now asserts `inFlight:1` -- it had passed
  with the save merely parked, found by running every existing patch on
  the new tree); key-scenario's live floor 119 -> 128; `qa-lib-test.sh`
  500 -> 505; `check.sh`'s `NODE_CHECKS_MIN` 2,502 -> 2,561;
  `KEY_PREFLIGHT_MIN` stays 11. D3 and W3 still go red under
  `d3-save-parked.patch` (`save-parked:NOFIELD`).
- R26g. key-scenario B23-B31 (the harness README's Round 16 has each
  segment's want). B23-B25 S29 `mv` / `sed` / `rmcp`, B26 S29-ln, B27 S40,
  B28 S21, B29 S35, B30 INLOAD, B31 IDLE.
- R26h. `run.sh`'s `reap_player` calls `qa_reap_players` on its scratch
  directory; the helper's `player stop` read (quit, TERM at 2 s, then
  SIGKILL), not changed.

**The measurements R26 rests on.** The contract's eighth FileView fact
(`OMARCHY-PLUGIN-CONTRACT.md`): a `setText` inside `onLoaded` raises no
`saved` (16 of 16); a created file is 0666 & ~umask and an existing one
keeps its mode; a re-point raises nothing; one `reload()` re-arms; a reload
while an own write is in flight delivers no load (30 of 30); a reload costs
median 2-4 ms, max 10, at 8 KB and 160 KB. Lane W's rig is committed on
branch `lane-clean-w-probe` (`scripts/dev-harness/spikes/filewatch-links/`
with `results/`) and is NOT in this tree; `Service.qml`'s R26a comment and
key-scenario's B header cite it by that branch. Lane S's probe and the
peek patch are in the session's scratch directory.

**False statements corrected where they stood (lane-clean-c1, the
documents lane).** Each sentence below said, as of 0.14.0 and correctly
then, that a replacement or a re-point is never noticed and the next save
writes over it, or that a returned target is never seen; each now says
what R26 does, and keeps what 0.14.0 did as the past.
- README: the `state.json` entry under "Files it writes"; Troubleshooting's
  **Saved sources not loaded** bullet ("anything else needs the restart",
  narrowed to `init-timeout`, with the read at the next save and the
  second source call), the `state.json` link bullet (what is noticed at
  once, what at the next save, FRESH, `ln -sfn` to another file and to a
  missing one, the two narrow exceptions, the past 0644 file), the folder
  link bullet (a re-point decided at the next save, an empty folder stops
  saving with nothing created, and after a restart the NEW folder is what
  loads), the "file changed while running" bullet's link parenthesis, the
  helper-refusal bullet's "unless another tool replaced a link"; and the
  harness count (120 -> 129, 2026-10-16).
- `UX-SOURCES.md` 5.10: the heading; item 4 (the mode can begin at a save,
  B28); item 5 (it ends at the next save, D-SRC-35 on the second call,
  B29); item 6's two round-15 brackets (D-SRC-29 and D-SRC-40 closed).
- The contract: the facts list's bracket, fact seven's "this plugin does
  not call one", and a bracket on fact seven's sentences about the service;
  the eighth fact.
- `ARCHITECTURE.md`: section 5's round-15 "the link's limit is stated, not
  fixed" bracketed; section 5's round-16 amendment; security standard 5's
  "state is 0600", which the service's own save did not keep (D-SINK-21);
  risk 1's round-15 bracket.
- `QA.md`: TC-CFG-16's and TC-CFG-21's round-15 brackets -- TC-CFG-21's
  manual check expected the `mv` edit to be LOST, and now expects it kept;
  the round-16 record; TC-CFG-30 to 32. `QA-SOURCES.md`: SRC-MIG-41's and
  SRC-MIG-49's round-15 brackets; SRC-MIG-58 to 60.
- `scripts/dev-harness/README.md`: round 15's "no segment drives a
  symlinked `state.json`" bracketed; the Round 16 record. Lane A had already
  added the reap paragraph, the chno `--serve` note and the `--baseline
  1c88877` line.

**This lane's search, by shape, over the documents (rule 15).**
- "A replacement or re-point at the state path is never noticed, and the
  next save writes over it" (D-SRC-29, D-SRC-40): grep over the nine files
  for `ln -sfn`, `re-point`, `replaces the link`, `straight after`, `not
  noticed`, `D-SRC-29`, `D-SRC-40`, `filed, R25e` and `does not call one`.
  Corrected: every hit above. Cleared: this file's round-14 and round-15
  records (records of what was measured then, true of that tree), the
  contract's table rows for the bare view (still true of the view), the
  `ln -sfn` command lines in `QA.md`, `QA-SOURCES.md`, `ARCHITECTURE.md`
  and the contract (qmllint's import roots, a playlist fixture), and SR30
  (the clone's `origin`).
- "A returned target, or a repair, is never seen" (D-SRC-35, D-DOC-13):
  `coming back`, `target came back`, `restart`. Corrected: the README's
  no-write and link bullets, `UX-SOURCES.md` 5.10 item 5, `QA.md`
  TC-CFG-16, `QA-SOURCES.md` SRC-MIG-41, the contract's D-DOC-13 sentence
  (bracketed: the case was not driven against the new tree; it is the same
  read over a `permission` block, which `Model.stateSavePlan` answers
  `verify`). The README's "anything else needs the restart" was wider than
  D-SRC-35: the documents lane called the shipping `Service.qml` through
  `tests/service-harness.js` for a start block (`permission`,
  `absent-unconfirmed`, `unparsed`) and a mid-session one (`permission`,
  `absent`, `unparsed`), each repaired with no signal: on the tip a
  favourite lifts every one and a source call lifts it on the second try;
  on dev's `Service.qml` (with the same double) none lifts. The favourite
  made at that moment is KEPT in the mid-session shapes and NOT kept at a
  start (the file's state is applied over it); the README says both.
- "A state file the service writes is 0600" (D-SINK-21's shape: a mode
  promise the view's own create does not keep): the README's "Files it
  writes" (`state.json` "mode 0600"; true of every file the plugin now
  writes, since the service no longer asks the view to create one),
  `ARCHITECTURE.md` security standard 5 (bracketed) and rule 6 of the
  project instructions (not this lane's file; true of the tree now but for
  the watchdog's residual, reasoned and not measured, in `ARCHITECTURE.md`
  section 5's round-16 amendment). [lane-clean-f1, 2026-10-16: not true
  without three exceptions, each now stated where the sentence stands --
  a save asked while our previous write is in flight skips its read; a
  re-point landing between the read's load and the write it allows; the
  2 s watchdog firing -- each of which still asks the view to create the
  0644 file, measured through the node double over the shipping
  `Service.qml` (both hosts, both echo modes); and a 0644 file the user
  put at the path (`mv`, `rm` + `cp`) is written into at its own mode
  until the next start's `state init`.]
- "The watch is the only way the session learns of a change" (R26d's
  shape): `UX-SOURCES.md` 5.10 item 4 ("the mode begins when the FileView
  delivers the reload": bracketed, it can begin at a save now); the
  harness README's round notes (records, cleared).
- Counts round 16 moved: the README's harness count (120 -> 129); the
  harness README and `QA.md` records carry node 2,561, `qa-lib-test.sh`
  505 and the live floor 128.

**Seen red (lane A).** Node: the tip's tests over dev 1c88877's
`Service.qml` read 64 of 2,561, among them the fourteen R26 harness pins
in all four host and echo shapes (56) and the R26b structural pin; dev's own suite with only
the new double swapped in, 12 of 2,502 (eight R22a unmigrated starts, four
R24a IN FLIGHT: D-SRC-46 surfacing in existing checks). By mutation:
`r26a-no-read.patch` 36; `r26b-no-defer.patch` 23 / 21 (echo load / none);
`r26a-no-verb-recheck.patch` 4. Live: `--baseline 1c88877` 120 / 9, exactly
B23-B31 (the transcripts in lane A's scratch); `--tree` with
`r26a-no-read.patch` 122 / 7, `r26b-no-defer.patch` 128 / 1,
`r26a-no-verb-recheck.patch` 128 / 1, `r26d-periodic-reload.patch` 126 / 3,
`d3-save-parked.patch` 76 / 53. `qa-lib-test.sh`'s `run.sh reap` pin red
against 1c88877's `run.sh` (the deaf player alive, nothing said).

**Counts.** On dev 1c88877: node 2,502 in both echo modes; python 1,229;
qml spec 78; `qa-lib-test.sh` 472; key preflight 11; key-scenario's live
floor 119 lettered checks, summary 120. On lane-clean-a1 5ee0e5f (lane A's
report): node 2,561 / 0 in both echo modes; python 1,229; qml spec 78;
`qa-lib-test.sh` 505 / 0; harness predicates 505; key preflight 11;
key-scenario live 129 / 0 (128 lettered checks and the floor,
`key-20261016-084228-582473`); sources 66 / 0, logo 33 / 0, chno 46 / 0,
chno-entry 78 / 0; player 76 / 9 and rewind 110 / 4, the same reds as dev
under the same rig (P1-P12 read the real `hyprctl clients`; R13 / R14 count
key presses, and a cage's seat has no keyboard). `./scripts/check.sh` on
5ee0e5f exits 1 on the defect ledger alone: D-SRC-46, F-HARNESS-29 and
F-HARNESS-30 are cited and have no row on `docs/STATUS.md`; with the three
rows added uncommitted the same commit reads "all green".

**Open for the lead (decision requests and findings with evidence; the
board's ids are the lead's).**
- (1) The board rows for D-SRC-46, F-HARNESS-29 and F-HARNESS-30, and the
  closures of D-SINK-21, D-SRC-29, D-SRC-35 and D-SRC-40 (and F-HARNESS-21
  and F-HARNESS-22), are `STATUS.md`'s, which neither lane A nor this lane
  writes; until they land the gate is red on the ledger only.
- (2) D-SRC-47 (lane A's finding; the id given on lane-clean-f1,
  2026-10-16): R25a's own-write record keeps
  eight texts, and a burst of more than eight writes made a turn apart
  while the first is in flight pushes the first text out, so its echo is
  merged as foreign and can undo the last in-app change (ten switches a
  turn apart ended on B, not A). It predates R26 and is rarer under it.
- (3) Lane A's: under R26 `d3-save-parked.patch` loses every in-app save
  (53 live reds, not 6). Should the `save-parked` clause get a dedicated
  live check beyond D3 and W3?
- (4) This lane's: lane W's `spikes/filewatch-links/` is cited by
  `Service.qml`, key-scenario and these documents and lives only on
  `lane-clean-w-probe`. Merge it (its `results/` included) so the citation
  resolves on `dev`, or keep it as a branch reference?
- (5) This lane's: "after re-pointing a folder link to an EMPTY folder and
  restarting, the guide starts with no sources, like a fresh install" is
  lane S's observation on its peek patch, not re-run on lane-clean-a1. R26
  changes no start-up LOAD (only how a save is issued), so the README
  states it; a live segment (B28 followed by a restart) would observe it.
- (6) This lane's: in a no-write START, a favourite made once the file is
  readable again lifts the mode but is not kept -- the file's state is
  applied over it -- where a mid-session block keeps it (the probe above).
  Consistent with the notification ("changed now are not kept"); the
  README says it. Acceptable as stated?
- (7) This lane's: the absent row's `<fix>` (`If it is a symbolic link,
  restore the file it points to; otherwise make the folder readable with
  chmod 700. Then run omarchy restart shell.`) is what B28's user reads
  after re-pointing a folder link at an empty folder; neither half fits
  that case, and since R26 the restart is no longer the only way out. A
  copy question; the notice is `Model.stateUnreadableNotice`, not this
  lane's.
- (8) This lane's: `a` and `c` in Sources are refused by the guide
  (`Model.sourcesAddAllowed`) without asking the service for a reload, so
  pressing them never lifts a mode a returned file could lift; every other
  source change does. Worth a recheck there too?
- (9) The README names "up to and including 0.14.0" for the old behaviour.
  That is right if R26 ships as 0.14.1, the manifest's version on
  lane-clean-a1; if 0.14.1 is cut without R26 it must read 0.14.1.
  [lane-clean-f1, 2026-10-16: 0.14.1 is dev 1c88877's code, which carries
  no R26, so the README, `UX-SOURCES.md` and the contract now say "up to and
  including 0.14.1".]

### D-SINK-19 round 17 rulings (lead, 2026-10-20; R27, on top of R1-R26, which stand except where R27 replaces them)

**What the round began from.** The board's open rows after 0.14.2
(`docs/STATUS.md`): D-SINK-22 (three narrow windows in which the service's
own save can still create a 0644 `state.json` holding provider URLs),
D-SRC-41 (an in-app add's probe at 49 sources while a hand-run add takes the
50th: 51 committed, the in-app one dropped silently at the next start),
D-SRC-42 (a mid-session block announced as `Saved sources not loaded`),
D-SRC-44 (the one-time migration at 50 sources evicts the least recently
used source, the only copy of its URL), D-SRC-48 (a change another program
writes in the same instant as one of our saves is lost), D-SRC-50 (after a
folder link is re-pointed at an empty folder, the notice's advice leads to
a fresh, empty start), D-SRC-51 (the notice says changes made now "are not
kept", which is false on one way back) and D-PERF-1 (the open-budget
instrument has never measured the open with its delegates in it).

**The lead's ruling, R27 (2026-10-20).**

R27a. D-SINK-22: NO WRITE WITHOUT A READ. Two of its three windows close:
(a) a save asked while our previous write is in flight no longer skips its
read -- it waits for that write to land, then reads, then writes; (c) a read
that does not answer within its bound is retried once, never followed by a
blind write; if the retry is silent too, the session takes the R22 no-write
mode with its own reason (`read-timeout`: one Model sentence, names the
file, no URL, told once), lifted by a later read that answers. [Round 18,
2026-10-20: R28a REPLACES this half of (c). The no-write mode lost the
change it held when it lifted (round 1's two reviews), so a silent read now
keeps the save parked and reads again on a bounded schedule, and
`read-timeout` is withdrawn. The round-18 rulings.] [Round 19,
2026-10-20: R29a withdraws R28a's answer as well and this half of (c) with
it -- a read with no load in 2 s lets its save go ahead without it, as
R26a did; half (a) stands. The round-19 rulings.] Window (b), a
re-point between the read's load and its write, stays: milliseconds,
documented. Measure what the waits cost a burst of saves (latency,
coalescing) and that D-SRC-16's and R25a's echo handling still hold.
Pinned through `tests/service-harness.js` on both hosts and echo modes; a
live segment if a re-point can be timed inside a write in the cage, else
say why not.

R27b. D-SRC-48: MEASURE THE MITIGATION, THEN DECIDE. One re-read after our
own `saved` when a change was signalled during the write: measure on the
real FileView (`spikes/filewatch`) whether it ever recovers a change that
R26a's read before the NEXT save does not already recover. If it recovers
nothing new, build nothing and say so with the runs (the lead marks the row
accepted); if it does, build it under R27a's rules.

R27c. D-SRC-41: the probe commit re-checks `MAX_SOURCES` against the state
as it is NOW (after any merge) and refuses with `too_many`, told, instead of
committing a 51st record the next start drops. Rule 15: every other path
that adds a record (the migration, a helper write merged in, the Xtream
form) against the cap.

R27d. D-SRC-44: THE MIGRATION NEVER EVICTS. At 50 sources with an entry URL
not among them, the one-time migration does not run: the entry keeps its
URL (`shell.json` is 0600 under the D-SINK-18 shield), the marker is not
set, and the user is told once (a notification: the sources are full,
remove one in Sources and the bar's playlist moves in; no URL, no label of
the entry); the next reconcile after a removal migrates. Pinned; the
round-11 R21 oracle (an entry URL ends in a record or is reported) still
holds. [2026-10-22, D-SRC-64, round 7 of the bounds sweep: the held URL and
its guide URL now rest in `state.json`'s parked pair and the entry is
stripped once that write has landed; section 2.2 has the rule, and the
oracle reads "in a record, in the parked pair, or reported".]

R27e. THE NOTICE WORDING (D-SRC-42, D-SRC-50, D-SRC-51), one Model function
family with the R23e / R25 copy: a block that begins MID-SESSION is titled
`Saving has stopped` in the notification and the journal (the start-up
reasons keep `Saved sources not loaded`); the body says changes made now
"are not saved until the file can be read again" (true on every way back),
not "are not kept" [round 18, R28e: true of the words only; on three of the
four ways back out of a mid-session block the change is dropped, and the
sentence now says which -- the round-18 rulings]; and the advice for a file or folder that has gone
missing names the link case first ("if it is a symbolic link, point it back
at the folder or file that holds your state"). Every sentence pinned; the
README and `UX-SOURCES.md` quote them verbatim (lane C).

R27f. D-PERF-1: AN ASYNC OPEN INSTRUMENT, in the harness only
(`scripts/dev-harness/shell.qml` and its IPC; no product change): the clock
starts at the summon, the event loop runs until the PRESENTING view has
realised its first screen of delegates (a count stable over consecutive
frames, or the frame after the last delegate completes -- measure which
settles), and it reports the summon time, the realised time and the count.
Prove it can fail with a mutation that delays delegate creation. Measure
the open at 10,000 channels, list and wall, cold and warm, in the cage's
floating-window mode, interleaved with PERF-02's method; state plainly
whether rule 7's 150 ms budget holds, and if it does not, file the defect
with the numbers and change nothing in the product this round.

**What the tree does (lane-sweep-a1, 070cd35, from `dev` 6f1d176; lane A's
report, each claim below re-checked by this lane by calling the model or
reading the code at that commit).**
- R27a. `Model.stateSavePlan` answers `wait` while one of our writes is in
  flight (the model table above has the whole plan). `Service.saveState`
  holds the save (`stateSavePending`, `stateWriteWaiting`, counted in
  `stateSavesWaited` and `stateWriteWaits`); the `saved` or `saveFailed` of
  that write calls `endStateWriteWait(false)`, which asks for the save again
  through `Qt.callLater(saveDeferredState)`, where it reads and then
  writes. `stateWriteWaitWatchdog` (2000 ms) bounds the wait and releases
  the held save to its read, never to a write (lane A's addition; the ruling
  names no bound). Window (c): `stateVerifyWatchdog` (2000 ms) firing asks
  `stateVerifyTimeoutAct` -- `retry` reloads once more and restarts
  the bound; `block` calls `blockStateWrites("read-timeout")` and refuses
  the save. The mode is lifted like any reason a load can lift: the next
  save reads (plan `verify`), a source verb is refused once and asks for one
  reload (`Model.stateBlockRecheck`), and `stateLoadArrived` lifts it on a
  load that is a state. [Round 18: `blockStateWrites` set
  `stateSavePending` false, so the load that lifted the block was applied
  over memory and the held change was lost on every lift but the next
  in-app change's -- our own late echo, a source verb's re-read, another
  program's write, the stalled read answering. The two round-1 reviews
  measured it through the shipping `Service.qml` on both hosts and both
  echo modes; 0.14.2 kept every such change. R28a replaced it.] [Round 19:
  and R29a replaced R28a's answer with R26a's -- the round-19 rulings.] Window (b) is unchanged and is stated in
  `Model.stateSavePlan`'s comment. `stateFile.setText` remains the only
  writer, reached only through the plan's `write`, which only the verify's
  finish gets.
- R27b. Measured, nothing built (below).
- R27c. The probe commit asks `Model.sourcesFull(st)` for a URL not already
  recorded; full -> `cache remove` of the probe's directory, one journal
  line (`the new source was not added: Sources is full (50)`), and
  `sourceProbeFinished` with `ok: false`, `code: too_many`, `reason` the
  `too_many` sentence. The guide's form shows it through
  `Model.probeFailureLine` as `Sources is full (50) · remove one first from
  <host>` [round 18, R28e: without the host now -- `Sources is full (50) ·
  remove one first`]. `Model.addSource` asks the same function.
- R27d. `reconcileSources` answers `full` at the cap and never evicts; the
  service's eviction loop is deleted. `adoptActiveSource` sets `full`, does
  not set the marker, and resolves the active source from step 2.
  `Service.adoptActive` sets `migrationHeldFull` and reports
  `playlistUrl:full` once a session (`Model.entryInputNotice("playlistUrl",
  "full")`, id 74016); `removeSource` queues `retryHeldMigration`, which
  runs `reconcile(true)` with `heldFull` so the URL is fresh again.
- R27e. `Model.stateUnreadableNotice(reason, path, midSession)`,
  `stateUnreadableJournal`, `stateBlockedHeader` and the four
  `STATE_BLOCK_*` constants; the service hands `midSession` = `stateLoaded`
  when the block begins, and `Guide.qml`'s `stateNotice` passes the
  service's `stateLoaded`. Rule 15 (lane A): the bar-entry refusal's journal
  line now says `saving to state.json has stopped` in a mid-session block.
  `tests/fixtures/state-notices.json` holds every sentence for one path.
- R27f. `shell.qml`'s `openAsync` / `openAsyncResult`, `HarnessLib.openSettle`,
  `scripts/dev-harness/open-scenario.sh` (check-tree arm in the gate, 9
  checks; live arm 21). The harness README's open-scenario section has the
  rule and the commands.

**The measurements R27 rests on (lane A's runs; transcripts in lane A's
session scratch directory, not the tree).**
- R27a, the burst (key-scenario's printed measurement, not a check: the
  check it was, B34, read green on 6f1d176 and through the mutation, so it
  could not go red for what it named, rule 11). Bursts of 2, 5, 10 and 20
  label edits a turn apart landed 7, 11, 20 and 29 ms after the first edit
  with 1, 2, 4 and 7 writes and as many reads; on 6f1d176 7, 9, 19 and 36
  ms with 1, 2, 4 and 7 writes. The wait costs nothing measurable here,
  because a write lands inside a turn on this machine. In node, three saves
  a turn apart make 2 writes and 2 reads (6f1d176: 3 writes, 1 read), and
  twelve never hold more than one text in R25a's own-write record
  (6f1d176 fills all eight) -- so D-SRC-47's overflow can no longer happen,
  pinned (`R27a (<tag>): D-SRC-47's mechanism -- ...`). D-SRC-16's and
  R25a's echo pins are green on both hosts and both echo modes.
- R27a, live: key-scenario B33 (a second change asked while the first
  write is out waits and then reads; `skipped +0`). On 6f1d176 B33 is red
  only through its new field (`waited:NOFIELD`): on this machine the first
  write had always landed by the deferred turn, so window (a) does not open
  from outside the shell; seen red on behaviour through
  `spikes/key-mutations/r27a-wait-never-released.patch` (`--tree`: 134
  lettered checks, 133 passed, 1 failed, B33). No live segment times a
  re-point inside a write, for the same reason, and none stalls a read for
  2 s (no way without FUSE or root); the node pins time both.
- R27b. `spikes/filewatch/measure.sh` set `r27b`, two runs, 240 and 368
  trials (`RESULT-2026-10-20-r27b.txt`): a writer changes the file at a set
  delay while the probe saves, by rename and in place, with and without the
  mitigation, and a read one second later stands in for R26a's next read.
  The mitigation recovered a change the later read did not in **0 of 608**.
  The change landed during our write in 25 trials; in 20 our rename had
  replaced it, which no read recovers (D-SRC-48 itself, on every tree, as
  in the 196 trials where it landed before our write began); the
  mitigation's read loaded it in 4 and the later read in all 4; in 9
  trials (4 during our write, 5 after it) it survived on disk unseen by the
  view on its own, and the later read loaded it in all 9. Nothing built;
  the row is the lead's to mark accepted. [Round 18, R28e: this bullet read
  "30" and "21" until round 1's review recounted the raw lines of the
  RESULT file -- 25 `C@during`, 20 of them `C-survived:no`, 5 survived;
  196 before our write and 387 after it was saved, 196 + 25 + 387 = 608.
  The RESULT file's VERDICT carried the same miscount and is corrected
  there. The headline, 0 of 608, and the verdict stand.]
- R27f, the open budget, at 10,000 channels in the cage's floating-window
  mode, 3 cold shells and 24 warm opens per view, interleaved with PERF-02
  method A (transcript `open-20261020-123554-1529605`, 21 passed, 0
  failed):

  | Open | Summon median | Realised median (range) | Delegates |
  |---|---|---|---|
  | list, cold | 95 ms | 546 ms (541-552) | 13 |
  | wall, cold | 94 ms | 580 ms (538-620) | 21 |
  | list, warm | 12 ms | 34 ms (29-40) | 13 |
  | wall, warm | 12 ms | 32 ms (29-43) | 21 |

  [Round 18, R28d: the "Delegates" column counts every delegate the view
  had BUILT, its cacheBuffer's off-screen ones included; a screen at this
  size DRAWS 10 rows and 16 tiles. The settle rule (a count stable over
  three frames) therefore trailed the drawn screen and let a view that drew
  six rows and filled the rest 300 ms later pass L1-L5 (round 1's live
  review). The round-18 rulings re-measure the open with the drawn count.]

  **Rule 7's 150 ms budget does NOT hold for the first open of a session,
  and holds for every later one.** On a cold open the two settle rules
  always agreed (the frame after the last delegate is the first frame of
  the stable count); a warm open creates no delegate, so only the stable
  count settles it. PERF-02's method A read about 0 ms (-7 to 6): it ends
  when the summon returns, and the IPC client's own start-up noise is
  larger than what is left, so it cannot see this cost. A 40-channel
  control (`open-20261020-124019-1545245`) read 452 ms cold for the list
  and 495 for the wall against 21 and 22 warm: about 450 ms of the cold
  open is the first show of the guide's window in the cage, whatever the
  channel count; the 10,000 channels cost about 70 ms of summon and about
  90 ms of realised time. The floating xdg window under cage is not the
  production layer-shell surface, so the cold figure on Hyprland is
  UNVERIFIED. The instrument moved with
  `spikes/open-mutations/slow-delegate.patch` (4 ms per delegate;
  `open-20261020-123804-1537394`): cold list 546 -> 647 ms, cold wall 580
  -> 640, cold summon 95 -> 207, warm unchanged at 34 (a warm open creates
  no delegate). The legacy `openMs` still under-counts a cold open (10 rows
  against 13, 18 tiles against 21) [round 18, R28d: an under-count of the
  BUILT delegates only; against what is drawn `openMs` reads the same 10
  rows and two more than the 16 tiles. What it misses is the frames up to
  the first drawn screen, not the delegates]. The defect R27f asks to be filed is the
  board's (`docs/STATUS.md`, the lead's); lane A proposed the next free
  `D-PERF` number. Nothing in the product changed.

**Documents corrected (lane-sweep-c1, the documents lane).** Each sentence
below was true of 0.14.2 and is now history or wrong.
- README: the counted-files paragraph and the "Files it writes" entry (three
  windows -> one; a read that does not answer stops saving rather than
  writes over); the migration paragraph (the 50-source case, `Sources is
  full` verbatim, and what is not covered); the Sources paragraph (nothing
  removes a source to make room); the no-write bullet (both titles, the
  body's new second sentence, the `read-timeout` cause, the advice list,
  the link-first sentence, the read-timeout way back); the link bullet (one
  exception, the two past windows, the dangling link's new `<fix>`); the
  folder-link bullet (the `<fix>`, `Saving has stopped`); the merge bullet's
  "Not covered yet" for D-SRC-41, now the refusal; the harness count
  (129 -> 134, 2026-10-20).
- `UX-SOURCES.md`: 5.10's heading, introduction, item 1 (titles, body,
  table, example), item 2's wireframe, item 4 and item 5 (brackets); 5.9's
  `full` row and its record; 5.5's probe-commit refusal.
- `UX.md`: 4.4 and 6.3 brackets; 6.4 gains the two notifications it never
  listed (74017 and the `full` card on 74016).
- This file: the migration paragraph of section 2.2, the reconcile step of
  section 4, the model table (`sourcesFull`, `stateSavePlan` /
  `stateVerifyTimeoutAct`, `stateUnreadableJournal`, and the
  `addSource`, `reconcileSources`, `adoptActiveSource`, `reconcileAction`,
  `stateUnreadableNotice` and `stateBlockedHeader` rows), the round-12 copy
  table, R26's "what the tree does" brackets, and this section.
- `ARCHITECTURE.md`: section 5's round-16 "what remains" and security
  standard 5 (the windows), the migration line in section 4 (eviction),
  and the performance budget table (measured, R27f).
- `OMARCHY-PLUGIN-CONTRACT.md`: the eighth fact's "what R26 builds" (the
  in-flight skip and the watchdog's blind save are gone).
- `QA.md`: TC-CFG-33..36 and PERF-02's note; `QA-SOURCES.md`: SRC-MIG-61..64,
  SRC-CLI-05, SRC-SEC-10 and SRC-PERF-04 brackets.
- `scripts/dev-harness/README.md`: the open-scenario section, the Round 17
  record and the `--baseline 6f1d176` line.

**This lane's search, by shape (rule 15).**
- "The plugin can create a 0644 `state.json` in N windows" and "a save
  goes ahead without its read": grep over the nine files for `three narrow`,
  `three windows`, `without the read`, `2 s bound`, `within 2 seconds`,
  `in flight`, `D-SINK-22`. Corrected: every hit in the README, this file's
  table and R26 record (bracketed), `ARCHITECTURE.md` and the contract.
  Cleared: the round-16 records (true of that tree) and the `2 s` of the
  read's own bound, which stands.
- "Changes made now are not kept" (D-SRC-51) and the old title (D-SRC-42):
  grep for `not kept`, `Saved sources not loaded`, `Nothing is saved until
  it can be read`. Corrected: the README bullet, `UX-SOURCES.md` 5.10 items
  1, 2, 4 and 5, `UX.md` 6.3, this file's copy table and model row,
  `QA.md`'s manual steps that quote the body (bracketed). Cleared: `Not
  every change was kept` and `was not kept (the limit is ...)` (R25b's
  merge notice, true: those records are dropped), `not kept in shell.json`
  (a deleted caption's history), the README's "At a start it is not kept"
  (true: the file's state is applied over it) and every `Saved sources not
  loaded` that describes a block at a START.
- "Restore the file / folder it points to" (D-SRC-50): grep `points to`.
  Corrected: README (two quotes, one summary), `UX-SOURCES.md` 5.10,
  this file's copy table. None left that quotes the old `<fix>`.
- "At the cap the least recently used source is evicted" (D-SRC-44): grep
  `evict`, `least.recently`, `LRU`. Corrected: this file's section 2.2,
  section 4 step 3, the model table; `QA-SOURCES.md` SRC-CLI-05 and
  SRC-SEC-10; `ARCHITECTURE.md`'s migration line. Cleared: logo, EPG and
  rewind-buffer evictions (other mechanisms) and the round-1 to round-16
  records.
- "A source added during a hand-run add at 49 is dropped at the next start"
  (D-SRC-41): grep `Not covered yet`, `51st`. Corrected: the README.
  Cleared: SR24 and SRC-ERR-05 (the add form's own refusal, unchanged).
- "The open budget is met / measured" (D-PERF-1): grep `150 ms`, `open
  budget`, `openMs`, `PERF-02`. Corrected: `ARCHITECTURE.md`'s budget row,
  `QA.md` PERF-02, `QA-SOURCES.md` SRC-PERF-04, the harness README. Cleared:
  the README (no open figure), `UX.md`'s wall delegate counts and
  `cacheBuffer` row (paint and delegate measurements of their own, dated),
  and this file's switch-redraw budget (not an open); bracketed: this
  file's section 6 "Guide open | unchanged < 150 ms" row.
- Not changed: section 1's "inside the 150 ms budget" (a switch redraw, not
  an open) and the round-8 to round-10 records of a cold open over 150 ms
  by PERF-02's method (true of their method; R27f's table supersedes them).
- Every sentence this lane added about what the plugin does was checked by
  calling the model at 070cd35 (`Model.stateUnreadableNotice`,
  `stateUnreadableJournal`, `stateBlockedHeader`, `stateSavePlan`,
  `stateVerifyTimeoutAct`, `stateBlockRecheck`, `reloadDisposition`,
  `sourceErrorMessage`, `probeFailureLine`, `entryInputNotice`,
  `reconcileSources`, `adoptActiveSource`, `reconcileAction`), by driving the
  shipping `Service.qml` through `tests/service-harness.js` (the held
  migration with a bar guide URL, below), by reading `Service.qml` /
  `Guide.qml` at 070cd35, or against lane A's transcripts named above.

**Seen red (lane A, by its report).** Against 6f1d176 the new node suite
read 71 failures of 2,626 in each own-echo mode, spread over every R27
pin; by one-decision mutation of the tree, from 4 to 68 failures each (the
plan without the wait 19, the watchdog writing blind 12, the second silence
not blocking 16, `saved` not releasing the wait 15, the probe commit
without the cap 4, full still marking 13, full not told 8). Live,
key-scenario `--baseline 6f1d176` read 130 passed, 5 failed (B32, B33,
B35, B36, B37) with 134 lettered checks then (B34 has since been dropped).
open-scenario's check-tree O1..O7 were red on two `openSettle` mutations.

**Counts.** On 6f1d176: node 2,572 in both own-echo modes, python 1,293,
qml spec 78, harness predicates 513, model declarations 773; key-scenario
live under the new harness 130 / 5. On lane-sweep-a1 070cd35: node 2,634,
python 1,293, qml spec 78, `qa-lib-test.sh` 515, open preflight 9 (new),
key preflight 11, model declarations 780; key-scenario live 134 / 0
(`key-20261020-131102-1636986`, 479.9 s), sources 66 / 0, logo 33 / 0,
open 21 / 0. Floors: `NODE_CHECKS_MIN` 2,572 -> 2,634, `OPEN_PREFLIGHT_MIN`
9 (new), `qa-lib-test.sh` 513 -> 515.

**Open for the lead (decision requests and findings with evidence; the
board's ids and states are the lead's).**
- (1) The board: D-SINK-22 narrowed to window (b); D-SRC-41, D-SRC-42,
  D-SRC-44, D-SRC-50 and D-SRC-51 fixed on lane-sweep-a1; D-SRC-47 can no
  longer happen (pinned); D-SRC-48's mitigation measured to recover nothing
  (accepted, by R27b); D-PERF-1's instrument built; and the cold-open
  budget defect R27f asks to be filed.
- (2) A finding in R27d, measured by this lane through the shipping
  `Service.qml` (`tests/service-harness.js`, both hosts) and not covered by
  any pin: the held migration does not hold the entry's GUIDE URL with its
  playlist. An install updated from 0.13.6 (no `activeKey`) with 50
  sources, the entry carrying a playlist not among them AND a guide URL:
  no source is active (the guide is unconfigured); the guide URL is reported
  `no-source` (`Bar setting removed`, "was removed") but stays on the
  entry; when a removal lets the playlist in, its record gets NO guide URL
  and the entry is stripped of both. And if the user picks a source A
  meanwhile (from the setup form's `Saved sources`), the next start's
  reconcile attaches the bar's guide URL to A, replacing A's own -- the
  only copy of it -- with no line (`afterRestart: active A, A's guide URL
  is the bar's`, both hosts). The cause: `adoptActiveSource` runs the R4
  guide-URL block on the step-2 key when step 1 answered `full`. On
  6f1d176 the same start evicted the least recently used source (D-SRC-44)
  and put the guide URL on the bar's playlist, so this is new in R27d's
  shape, narrower than what it replaced, and silent. The README states it
  as not covered. [Round 18: confirmed by both round-1 reviews as a P1 and
  fixed by R28b; the guide URL is held with the playlist and moves in with
  it.]
- (3) A copy finding: the probe commit's refusal reaches the form through
  `Model.probeFailureLine`, which appends ` from <host>`, so it reads
  `Sources is full (50) · remove one first from tv.example.net`. Its
  sibling (rule 15) is older: the same commit's `state_unreadable` refusal
  reads `state.json could not be read · nothing is saved until it can be
  from <host>`. A service-side refusal is not a fetch failure. [Round 18,
  R28e: fixed for both, and for `unknown_source`: a result that carries one
  of those codes reads its sentence alone (`PROBE_LOCAL_REFUSALS` in model/sources.mjs).]
- (4) A UX question that follows from R27d: while the migration is held on
  a 0.13.6 upgrade the guide opens unconfigured over 50 saved sources, and
  the `Sources is full` card does not say a source can be picked meanwhile.
  When one is removed, the bar's playlist becomes the ACTIVE source, over
  whatever the user picked (pinned: `active:true` after the removal).
- (5) Lane A's rulings to confirm: the 2 s bound on the write wait
  (`stateWriteWaitWatchdog`), which the ruling does not name; and the
  `link` / `folder-link` `<fix>` changed to "point it back" beyond the
  `absent` sentence the ruling quotes (`absent-unconfirmed` left as it was).
- (6) Rule 13: the README and `UX-SOURCES.md` quote the fixture's sentences
  verbatim, and nothing checks that join; this lane checked it once by
  script at 070cd35 (every notice fragment the two files quote is a
  substring of a model sentence). A test that reads both files for each
  fixture sentence would make it a call; `tests/` is not this lane's.
- (7) Rule 15, the cap: the guide gates `a`, `c` and the Add rows with its
  own `sourcesFull()` (`sourceCount < Model.LIMITS.sources`), not
  `Model.sourcesFull`; the same constant, so not a defect today, but the
  one cap decision R27c names is two functions. [Round 18, R28e: three --
  `Service.canAddSource` was the third, which a round-1 review found -- and
  now one: all three call `Model.sourcesFull`.]

### D-SINK-19 round 18 rulings (lead, 2026-10-20; R28, on top of R1-R27, which stand except where R28 replaces them)

[Round 19, 2026-10-20: R29 WITHDRAWS R28a, R28c's three resets of a held
save's read (the state they reset is gone), and R28a's notice; R28b,
R28c's write-wait resets, R28d and R28e stand, R28e minus every sentence
about the removed stall. This record is history wherever it describes
R28a's tree. The round-19 rulings, next.]

**What the round began from.** Round 17's candidate (lane-sweep-a1 070cd35
and the documents on lane-sweep-c1 843ae87) held live in everything R27 set
out to do, and three reviews found it NOT MERGEABLE on two P1s, both new
data loss against `dev` 6f1d176, both measured through the shipping
`Service.qml` on both hosts and both echo modes:
- R27a's window (c) put the session in the R22 no-write mode
  (`read-timeout`) after two silent reads, and `blockStateWrites` set the
  held save aside. When a load then lifted the block -- our own write's
  echo reported late, the re-read a source verb asks for, another program's
  write, the stalled read answering -- `Model.reloadDisposition` saw nothing
  held and applied the disk over memory: the change was gone from memory
  and file, an in-app source add whose probe had succeeded included
  (`addOk:true ... inMemAfter:false onDisk:false` in 6 of 8 host, echo and
  next-act cases). It needs no user action with own-echo `load`: a write
  of ours reported after about 6 s is enough. 0.14.2 kept every such change.
- R27d's held migration did not hold the entry's GUIDE URL: with step 1
  answering `full`, `adoptActiveSource` still ran the R4 guide-URL block on
  the step-2 key. A source the user picked meanwhile had its own guide URL
  replaced by the bar's at the next start (its only copy; live on c1,
  `after restart: A-epg:BAR`); "Remove one" migrated the playlist with no
  guide URL and stripped the bar's; and the `Bar setting removed` card said
  the URL was removed while it stayed on the entry, overwritten at once by
  `Sources is full` on the same replace id.

Beside them: two R27a resets no check held (deleted, node read 2,634 / 0 in
both echo modes); the open instrument counting off-screen delegates and
passing a view that fills in late; R27b's breakdown miscounted (30 and 21
for 25 and 20); the open-mutations README's claim that the summon time does
not grow under `slow-delegate.patch`; the probe-commit refusal reading
`Sources is full (50) · remove one first from 127.0.0.1`; the cap decided in
three places under a comment calling it one; the mid-session notice's "not
saved until the file can be read again" against the ways back on which the
change is dropped; and two load-dependent sentences in the harness README.

**The lead's ruling, R28 (2026-10-20), replacing the parts of R27 they
break.**

R28a **[WITHDRAWN 2026-10-20 by R29a, round 19]**. A STALLED READ IS NOT A NO-WRITE BLOCK. After a silent read the save
STAYS PARKED with memory as the authority; the read is retried on a bounded
backoff (the schedule stated); there is never a blind write and never a
drop; when a read answers, R26a's dispositions decide (the base -> write;
another program's text -> the R24a merge, then write; a load failure ->
R22). If the reads stay silent past a stated time the user is told once (one
Model sentence, names the file, no URL: the change is kept in the session
and saved when the file answers; a shell stopped first loses it). Saving
other changes meanwhile coalesces into the same parked save. Pins on every
path that ends the wait (own echo, a source verb, a foreign write, a late
answer, a restart), both hosts, both echo modes: the held change survives
each, red on lane-sweep-c1. The `read-timeout` reason and its copy go, or
are re-used only if the stalled read answers with a load FAILURE.

R28b. A HELD MIGRATION HOLDS BOTH URLS. With the migration held at the cap
(step 1 `full`), the entry's `epgUrl` is held on the entry WITH its
`playlistUrl`: no R4 adoption onto any record, no strip, no "removed"
report; the notice says the bar's playlist and its guide move in once a
source is removed; after a removal the migration takes both together (R21).
Pinned: a picked source keeps its own guide URL across a restart, and
"Remove one" loses nothing; red on lane-sweep-c1.

R28c. THE TWO UNPINNED RESETS -- the write wait's expiry reset when a write
lands, and the read's "asked once more" reset when it finishes, or their
R28a successors -- each go red in node, both echo modes, when a mutation
deletes it.

R28d. THE OPEN INSTRUMENT COUNTS WHAT IS DRAWN: only delegates that
intersect the presenting view's visible area, stopping at the first frame
after that set is complete, with a late-fill mutation that goes red.
Re-measure the 10,000-channel open (list and wall, cold and warm,
interleaved with PERF-02's method) and report it. No product code changes.

R28e. THE MISCOUNTS AND round 1's P3s: R27b's breakdown everywhere it is
quoted; the open-mutations README and `open-scenario.sh`'s header; the
probe-commit refusal's host; the cap in one place, or the comment saying
three; the mid-session sentence against the ways back; and the
load-dependent sentences.

**What the tree does (lane-sweep-a2, 2bed7c2, on lane-sweep-c1; lane A's
report, each behaviour claim below re-checked by this lane on 2bed7c2 by
calling the model, by driving the shipping `Service.qml` through
`tests/service-harness.js`, or by reading the code).**
- R28a. `Service.finishStateVerify(true)` -- the watchdog fired with no
  load -- no longer blocks or writes. It counts the silence
  (`stateVerifySilences`), asks `stateVerifyTimeoutAct({ silences,
  silentMs, told })`, which always answers `retry` with the next bound,
  sets `stateVerifyBoundMs` (the watchdog's interval is that binding),
  reloads and restarts the watchdog; `stateSavePending` and
  `stateVerifyPending` stay set, so whatever load comes is decided by
  R26a's dispositions with the change held, and every save asked meanwhile
  is plan `join`. The schedule is `STATE_READ_BOUNDS_MS`, `[2000,
  2000, 4000, 8000, 16000, 30000]`: re-reads at 2, 4, 8, 16, 32 and 62 s
  after the save first asked, then every 30 s (called:
  `stateReadBoundMs(0..8)` summed gives 2000, 4000, 8000, 16000, 32000,
  62000, 92000, 122000, 152000). The interval is bounded, the count of
  re-reads is not. A read is also asked at once (`rereadStateVerify`,
  from a turn of its own, never inside a `stateFile` handler and never
  while a write of ours is out) when a change joins a held save after a
  silence, and when one of our writes is reported (`onSaved`, and
  `onSaveFailed` when the text landed): a read asked while our write was
  out was dropped by the view (F-HARNESS-31). At the third silence, 8 s
  (`STATE_READ_TELL_MS`), the user is told once for this held save
  (`stateReadStalledNotice`, id 74019, urgency normal; on the
  console as `omarchy-iptv: <title>: <body>`): `Saving is waiting` /
  `<path> has not answered for 8 seconds when it was read before a save.
  The change is kept in this session and saved when the file answers; if
  the shell is stopped first, it is lost.` Each silence logs `state.json
  was not read back within <ms> ms of a save; the change is kept and the
  file is read again, waiting <bound> ms`, and the answer after one
  `state.json answered <ms> ms after a save asked for it; the change held
  meanwhile is decided now`. `read-timeout` is gone from `Service.qml` and
  the model; a load FAILURE the stalled read answers with blocks under
  that load's own reason (over an empty folder, `absent`, told once on
  74017, no file created).
- R28b. `adoptActiveSource` skips the R4 block when `full` and sets
  `heldEpg`; `reconcileAction` makes BOTH URLs fresh under `heldFull`; the
  `full` notice is re-worded (below). Driven through the shipping
  `Service.qml` on 2bed7c2 by this lane (round 1's probes, retargeted), both
  hosts: a 0.13.6-shaped state at 50 sources with the entry carrying a new
  playlist and a guide URL tells `Sources is full` alone (no `Bar setting
  removed`), reports `playlistUrl:full` alone, keeps both URLs on the
  entry and source A's own guide URL; one removal adds the playlist WITH
  the bar's guide URL, ACTIVE, the entry stripped of both; A picked and
  the shell restarted, A's guide URL is still its own (`afterRestart:
  ... Aepg: OWN ... entryEpg: true`). On lane-sweep-c1 the same probes read
  `newEpg: ""` and `Aepg: BAR`.
- R28c. The three resets of a held save's read (the silence count, the
  bound and the told flag) are made in `finishStateVerify`'s answered
  branch and nowhere else, and the write wait's expiry
  (`stateWriteWaitExpired`) is reset in `onSaved` and in `onSaveFailed`.
  Each deletion is red in node in both echo modes (below).
- R28d. `scripts/dev-harness/shell.qml`'s `openSample` / `openFrame` and
  `HarnessLib.openDrawnSet` / `openDrawnSettle`: a delegate is counted when
  it is shown and intersects the view's visible area, and the open is
  realised at the first frame whose drawn set TILES that area against the
  guide's `rowCount` (contiguous, nothing missing above or below, a grid
  row whole); the instrument then samples 600 ms more and counts frames
  whose drawn set changed. The live arm grades the warm median against
  150 ms (L6 / W6) and no change after any decision (L7 / W7); L4 compares
  the drawn count with the most the view built. The cold budget and the
  legacy `openMs` are printed, not graded. New mutation:
  `spikes/open-mutations/late-fill.patch` (both views' model is
  `min(rowCount, 6)` until 300 ms after `open()`). The harness README's
  open-scenario section has the rule. No product code changed.
- R28e. `Model.probeFailureLine(reason, host, kind, code)` drops `from
  <host>` when `code` is one of `PROBE_LOCAL_REFUSALS` in model/sources.mjs (`too_many`,
  `state_unreadable`, `unknown_source`), refusals the plugin made itself;
  the service's probe results carry `code`, and both `Guide.qml` call
  sites pass it. Called: `Sources is full (50) · remove one first` and
  `state.json could not be read · nothing is saved until it can be` with a
  host and those codes; `HTTP 404 Not Found from tv.example.net` for a
  fetch failure, unchanged. `Service.canAddSource` and `Guide.sourcesFull()`
  call `Model.sourcesFull`. The no-write body's second sentence is
  `STATE_BLOCK_UNSAVED_START` at a start and `STATE_BLOCK_UNSAVED`
  mid-session (the round-12 copy table above). The RESULT file, the
  open-mutations README, `open-scenario.sh`'s header and the harness
  README's Round 17 record are corrected in lane A's files.

**What the new mid-session sentence describes, and does not change (lane
A's measurement through `Service.qml`, both hosts and both echo modes; R22's
behaviour, the same on 6f1d176).** In a block that begins after a state
loaded, a change made in the block -- a favourite, a hidden group, a saved
search -- is saved if the NEXT such change's own read finds the file again
(R26a); it is dropped if the file comes back by itself first (a backup put
back, a `chmod 600`: the view sees it and the load is applied), if the
change that finds it is a source change (refused once, and its re-read
applies the file), or if the shell is stopped. R28e made the sentence say
so; whether a change made in an R22 block should be held like R28a's is
lane A's open question for the lead, below.

**The measurements R28 rests on (lane A2's runs; transcripts in that lane's
session scratch directory, copied 0600, not the tree).**
- R28a has no live segment, as R27a's window (c) had none: nothing in the
  cage stalls a FileView read without FUSE or root (a FIFO at the path is
  `not-a-file` and answers at once, round 1's live review). The node pins
  are the evidence, through the shipping `Service.qml` on both hosts and
  both echo modes (`R28a (<tag>): ...`): the schedule over an EMPTY folder
  (re-reads at 2, 4, 8, 16, 32, 62 and 92 s, told once at 8 s, nothing
  blocked, refused, written or created, and the read's eventual `absent`
  blocked and told); the wait ended by our own write reported at 6.5 s; by
  a source verb (`updateSource` answers ok, not `state_unreadable`); by an
  in-app add whose probe succeeds; by another program's write (merged); by
  the stalled read answering late; by the schedule's re-read; three
  changes joining one write; and a restart while held (the file unchanged,
  and the notice said a stopped shell loses it). Every keeping path is
  also checked after a restart. Round 1's own lens scripts, retargeted at
  2bed7c2, read every change kept on all four host and echo combinations
  (re-run by this lane: the two favourites with the first write reported
  at 6.5 s, `mem` and `file` both; the in-app add, `inMemAfter:true
  onDisk:true` in all 8 cases; the source verb, `first:"ok"` with the
  favourite on disk).
- key-scenario live, each under its own nested cage on a private bus:
  forward 136 passed, 0 failed (`key-20261020-155757-2060758`, 492.4 s);
  `--baseline 843ae87` (lane-sweep-c1) 133 / 3, B32, B38 `a-epg:bar`, B39
  `d-epg:empty ... a-epg:bar` (`key-20261020-161525-2136277`);
  `--baseline 6f1d176` 129 / 7, B32, B33 (`waited:NOFIELD` at load 2-3),
  B35-B37, B38, B39 (`key-20261020-160609-2096379`). B38 / B39 are R28b's
  live segments: a 0.13.6 install at 50 sources whose entry carries the
  playlist D and a guide URL, A with a guide URL of its own; A picked and
  the shell restarted, A's own guide URL stands, each start tells
  `Sources is full` and never `Bar setting removed`; one record removed, D
  moves in with the bar's guide URL. `sources-scenario.sh` 66 / 0
  (`sources-20261020-161452-2134037`).
- R28d, the open, at 10,000 channels in the cage's floating window, 3 cold
  shells and 24 warm opens per view, interleaved with PERF-02 method A
  (tip c06f436, `open-20261020-154123-1999165`, 30 passed, 0 failed, load
  2-3):

  | Open | Summon median | Realised median (range) | Drawn | Built at the decision |
  |---|---|---|---|---|
  | list, cold | 93 ms | 548 ms (540-549) | 10 rows | 13 |
  | wall, cold | 91 ms | 534 ms (519-537) | 16 tiles | 18-21 |
  | list, warm | 12 ms | 33 ms (27-41) | 10 rows | 13 |
  | wall, warm | 12 ms | 31 ms (27-39) | 16 tiles | 21 |

  **Rule 7's 150 ms holds for every warm open and does NOT hold for the
  first open of a session.** On every cold open the first frame swapped
  already drew the whole screen, so the cold time is the first frame, and
  the instrument now stops there instead of trailing the cacheBuffer.
  Method A read a median of -2 / -4 ms: it cannot see the open. The run
  before, at 2f846b7 (`open-20261020-153505-1977171`), read 526 / 540 cold
  and 32 / 31 warm. A 40-channel control (`open-20261020-155426-2050158`,
  30 / 0): 450 / 440 ms cold, 21 / 21 warm, summon 25 / 23 cold -- about
  440 ms of a cold open is the first show of the guide's window in the
  cage whatever the channel count; 10,000 channels add about 100 ms to the
  cold realised time and about 70 ms to the cold summon. The floating xdg
  window under cage is not the production layer-shell surface, so the cold
  figure on Hyprland is UNVERIFIED. `late-fill.patch`
  (`open-20261020-154400-2009476`): 28 / 2, L6 and W6 red, warm median 370
  / 362 ms, the six-row frame refused as `below` in both cold traces.
  `openDrawnSet` counting every BUILT delegate, in a copy of the harness
  (`open-20261020-154651-2020565`): 18 / 12. `slow-delegate.patch`
  (`open-20261020-155149-2039814`, load 3.7-6.7): 30 / 0, cold summon 93
  -> 207 ms (list) and 91 -> 191 (wall), cold realised 548 -> 673 and 534
  -> 628, warm unchanged at 32: a cold summon builds delegates
  synchronously, the hidden view's among them, so the summon grows too.

**Seen red (lane A2, by its report).** The final node suite over
lane-sweep-c1's `Service.qml` and model: 66 failures of 2,692 in each own-echo
mode, on behaviour (R28a's ways read `read-timeout` and the change lost; the
source verb `state_unreadable`; R28b's `aEpg:"E"` after a restart and
`newEpg:"-"` after a removal; R28c's three; the probe line). Over 6f1d176:
112 of 2,692 in each. One-decision mutations of 2bed7c2, failures per echo
mode, identical in both: silence blocks (R27a's shape) 44, silence writes
blind 45, silence clears the held save 44, no join re-read 9, no landing
re-read 6, never tell 13, tell at 4 s 14, a flat 2 s schedule 13, re-read
while a write is out 4; R28c -- expiry not reset in `onSaved` 4, nor in
`onSaveFailed` 4, silences not reset 12, bound not reset 4, told not reset
4; R28b -- R4 runs on `full` 9, retry fresh for the playlist only 5; R28e --
`probeFailureLine` ignores `code` 5, a commit result without `code` 4,
`canAddSource` back to its own compare 1 (the structural pin; the
behaviour is identical), one sentence for start and mid-session 2; the
re-made `r26a-watchdog-20ms.patch` and `r26a-watchdog-no-interval.patch` 24
each. open-scenario's check-tree D1-D10 and E1-E4 were each red on a
one-decision mutation of the function they drive (the harness README lists
them). Not seen red: the R28e ways-back service pins (green on c1 and
6f1d176 alike: they pin behaviour that predates the round; the copy they
bind to is red under the one-sentence mutation), and the S1 seam (a
structural check).

**Counts.** On 2bed7c2: node 2,692 in both own-echo modes (2,634 on
lane-sweep-c1), python 1,293, qml spec 78, `qa-lib-test.sh` 515, open
preflight 16 (9), key preflight 11, model declarations 786 (780).
Floors: `NODE_CHECKS_MIN` 2,634 -> 2,692, `OPEN_PREFLIGHT_MIN` 9 -> 16,
key-scenario's live `EXPECTED_CHECKS` 133 -> 135 (B38, B39),
open-scenario's 8 -> 15 (check-tree) and 20 -> 29 (live).

**Documents corrected (lane-sweep-c2, the documents lane).** Each was
true of lane-sweep-c1 or of an earlier tree and is now history or wrong.
- README: the migration paragraph (the guide URL held with the playlist,
  the `Sources is full` body, and its "Not covered yet" for the guide URL
  withdrawn); the `state.json` entry under "Files it writes" (a read that
  does not answer keeps the change); the no-write bullet (both second sentences, the
  `read-timeout` cause and advice and its way back gone); a new
  troubleshooting bullet, `Saving is waiting`; the link bullet (the
  stalled read, the past window's account); the merge bullet's
  probe-commit refusal (no host); the harness count (134 -> 136).
- `UX-SOURCES.md`: 5.5's probe-commit row; 5.9's `full` row and its
  record; 5.10's introduction, item 1 (the two second sentences, the
  `read-timeout` row withdrawn, the example), item 2's wireframe, items 4
  and 5 (brackets), and a new item for the stalled read.
- `UX.md`: 4.4's bracket; 6.4's no-write row, the `full` card, and the new
  `Saving is waiting` card on 74019.
- This file: section 2.2's migration paragraph, the model table
  (`sourcesFull`, `reconcileAction`, `adoptActiveSource`,
  `stateSavePlan` / `stateVerifyTimeoutAct`, `stateUnreadableNotice`,
  `entryInputNotice`, and new rows for the read schedule and
  `stateReadStalledNotice`), section 6's open row, the round-12 copy table,
  the R26 record's watchdog line, and the round-17 record (bracketed where
  R28 overturns it: window (c),
  R27e's "true on every way back", R27c's quote, R27b's counts, the open
  table's delegate column and the `openMs` sentence, open items 2, 3 and 7).
- `ARCHITECTURE.md`: section 5's round-17 amendment (window c), section 4's
  migration line, the failure-modes entry, and the open-budget row.
- `OMARCHY-PLUGIN-CONTRACT.md`: the eighth fact (the watchdog's answer
  and R27b's counts).
- `QA.md`: TC-CFG-33 to TC-CFG-36 re-graded, TC-CFG-37 and TC-CFG-38 new
  (R28a, R28b), PERF-02's note, the manual step that quotes the body, and
  the round-18 record. `QA-SOURCES.md`: SRC-MIG-61 to SRC-MIG-64 and
  SRC-PERF-04, SRC-MIG-65 and SRC-MIG-66 new.
- `scripts/dev-harness/README.md`: lane A2's Round 18 record and its
  re-written open-scenario section stand as that lane left them, checked
  against its report; the Round 17 record's "not live: window (c)" stays
  true of R28a and is not changed.

**This lane's search, by shape (rule 15).**
- "A read that does not answer stops saving": grep over the nine files for
  `read-timeout`, `twice, 2 seconds`, `window (c)`, `window c`, `once
  more`, `saving resumes if it answers`, `stops saving`, `did not answer`.
  Corrected: every hit that states it as current (the README's three, this
  file's model and copy tables, `UX-SOURCES.md` 5.10, `ARCHITECTURE.md`,
  the contract, `QA.md`, `QA-SOURCES.md`). Cleared: the round-17 records
  (bracketed, history), D-CLIP-1's "1 s per-read timeout" (the clipboard),
  and the start-up check's `did not answer` (`init-timeout`, which stands).
- "Not saved until the file can be read again" and its paraphrases: grep
  `until the file can be read`, `not saved until`, `true on every way
  back`. Corrected: the README bullet, `UX-SOURCES.md` 5.10 items 1, 2, 4
  and 5, `UX.md` 4.4 and 6.4, this file's tables and R27e (bracketed),
  `ARCHITECTURE.md`'s failure-modes entry, `QA.md` TC-CFG-34 and its manual
  step. Cleared: `nothing is saved until it can be` -- the source-call
  refusal's sentence, unchanged.
- "The bar's guide URL beside a held playlist": grep `no-source`, `Bar
  setting removed`, `moves in`, `Not covered`, `guide URL`, `guide-data
  URL`, `heldFull`. Corrected: the README migration paragraph,
  `UX-SOURCES.md` 5.9, `UX.md` 6.4, this file's model rows and open item
  2, `QA.md` TC-CFG-35, `QA-SOURCES.md` SRC-MIG-63. Cleared: the
  `no-source` row itself, which still holds when step 1 is not `full` and
  no source is active (not driven by this lane; the model's branch is
  unchanged), and the `invalid` branch, which still attaches the entry's
  guide URL to the step-2 record (lane A's open question 2, below).
- "From `<host>`" on a refusal: grep `from <host>`, `from 127`, `remove one
  first`. Corrected: README, `UX-SOURCES.md` 5.5, `QA-SOURCES.md`
  SRC-MIG-62, this file's R27c and open item 3. Cleared: every fetch
  failure's `<reason> from <host>` (UX 5.5, `UX.md`, QA's TC-RFR-08), which
  keeps the host.
- The open instrument's claims: grep `13 rows`, `21 tiles`, `13 |`,
  `under-count`, `a screen of delegates`, `openMs`, `summon`, `stable over
  three`, `546`, `580`. Corrected: `ARCHITECTURE.md`'s budget row, `QA.md`
  TC-CFG-36 and PERF-02, `QA-SOURCES.md` SRC-PERF-04, this file's section-6
  row and R27f table (bracketed). Cleared: `UX.md`'s dated delegate and
  paint measurements (their own instruments), and the round-8 to round-10
  records.
- R27b's counts: grep `in 30 trials`, `21 of the 30`, `of the 30`, `30
  that landed`. Corrected: this file's R27b bullet and the contract's
  eighth fact. No other quote.
- The cap's places: grep `LIMITS.sources`, `MAX_SOURCES`, `one decision`,
  `sourcesFull`. Corrected: this file's `sourcesFull` row and open item 7,
  `QA.md` TC-CFG-35. Cleared: SR24's row and SRC-SEC-10 (the add form's
  own refusal, by the same function now).
- Every quoted notice in the nine files was checked against the model on
  2bed7c2 by a one-off script that composes the corpus from
  `stateUnreadableNotice`, `stateUnreadableJournal` and `stateBlockedHeader`
  for every reason both ways, `stateReadStalledNotice`, `entryInputNotice`
  for each reason, `sourceErrorMessage` and `probeFailureLine`, and finds
  each quote's pieces in order (session scratch, not the tree).

**Open for the lead (decision requests and evidence; the board's ids and
states are the lead's, and none is cited here).** [Round 19: R29 answers
(3) with R29d and (7)'s copy half with R29e; (4) and (5) went with R28a;
(2) stands, now reached only by a read that answers with a load failure
within its 2 s bound, as on 0.14.2; (1) and (6) are carried below.]
- (1) The board: the two round-1 P1s fixed on lane-sweep-a2 (R28a, R28b);
  R28c's two resets pinned; R27b's miscount, the open-mutations claim, the
  probe line's host and the three-place cap corrected (R28e); D-PERF-1's
  instrument re-made (R28d); and the cold-open budget defect R27f asked to
  be filed, still unfiled -- about 530-550 ms at 10,000 channels and about
  445 ms at 40 in the cage (round 1 proposed the next free `D-PERF`
  number).
- (2) Lane A's open question 1, rule 15 over R28a: should "never a drop"
  extend to R22 mid-session blocks? Today a change made in one is dropped
  on three ways back (above), on 6f1d176 and 0.14.2 too, because
  `blockStateWrites` sets `stateSavePending` false. R28e fixed the words;
  holding the change so the lifting load merges it is a behaviour change.
- (3) Lane A's open question 2, a sibling of R28b: when the bar's playlist
  is INVALID, `adoptActiveSource` still adopts the entry's guide URL onto
  the step-2 record and can replace that record's own guide URL; 6f1d176
  does the same.
- (4) Lane A's open question 3: a held change cannot survive a shell
  stopped while it is held, because nothing writes without its read; the
  restart pin asserts the stated loss and nothing worse. To confirm.
- (5) Lane A's choices to confirm: the stall notice's own id (74019, not
  74017), once per held save (reset when its read finishes), its title,
  and the schedule and the 8 s tell time.
- (6) Rule 13, carried from round 17: the README and `UX-SOURCES.md` quote
  `tests/fixtures/state-notices.json` word for word and no check joins
  them; this lane checked the join once, by script.
- (7) Round 17's UX question (4) stands: at a held migration on a 0.13.6
  upgrade the guide opens unconfigured over 50 saved sources, and when
  one is removed the bar's playlist becomes the ACTIVE source over whatever
  the user picked (driven: `active: NEW` after the removal with A picked).

### D-SINK-19 round 19 rulings (lead, 2026-10-20; R29, on top of R1-R28, which stand except where R29 withdraws them)

**What the round began from.** Round 18's candidate (lane-sweep-a2 2bed7c2
and the documents on lane-sweep-c2 2bb1237) held both round-1 P1s fixed as
measured, and three reviews read it, one MERGEABLE and two NOT:
- A P1, live, with a real stalled `state.json` (round 2's live review built
  a FUSE passthrough that stalls only quickshell's `read()` of the file):
  while R28a waited on a stalled read, another program renamed a new
  `state.json` into place; the stalled read answered with the file as it
  was when it was ASKED, and the held save wrote over the other program's
  change -- a helper `state source add` or a favourite, gone on disk and
  across a restart, 4 of 4 runs. 6f1d176 kept it in the same HS4 / HS5
  shapes, 2 of 2, because its blind write at 2 s replaced the stalled
  reader and the rename then raised a fresh read. The node double handed
  back a fresh load the real FileView never delivers (rule 10). The
  platform fact is in `OMARCHY-PLUGIN-CONTRACT.md`'s FileView section.
- A P2, twice: a stalled read that answered with a load FAILURE turned the
  held change into an R22 change, dropped on three of the four ways back,
  while the `Saving is waiting` card promised it "saved when the file
  answers", `QA.md` TC-CFG-37 said "never a drop" and `QA-SOURCES.md`
  SRC-MIG-65 "every way the wait ends keeps the change" (21,952 runs per
  tree: 1,200 losses on c2, 0 on 6f1d176 and 0.14.2).
- A P2 in `UX.md` 4.4: its round-18 bracket said the not-loaded surface is
  only drawn at a start; it is drawn mid-session too, titled `Saving has
  stopped` (`Model.guideSurface` with the service's own fields).
- P3s: the untold restart window grew from under 2 s to under 8 s; three
  R28a / R28b guards survived deletion; R28b's sibling -- an INVALID bar
  playlist with a guide URL beside it put that guide URL on the active
  source in place of its own, the same on 6f1d176 and 0.14.2; the open
  instrument counted a view painted at opacity 0 as drawn (a 300 ms fade
  passed at 30 / 0); `init_pids` matched another harness's helper over the
  same tree (B14 `left:<their pid>`); the `full` card did not say which
  source ends active after "Remove one"; and four copy remarks (the "at
  once" re-read, the README's "until a source is removed the guide opens on
  its setup form" beside a picked source, two red commits left in branch
  history, round 18's open items with no ids).

**The lead's ruling, R29 (2026-10-20), which descopes part of R27 and R28.**

R29a. BACK TO R26a'S BOUND FOR A SILENT READ. R27a's window-(c) change and
all of R28a's stall machinery -- the parked save past the bound, the
backoff schedule, the re-reads, the `Saving is waiting` notice and id
74019, the `read-timeout` reason -- come OUT: a save whose read does not
answer within its 2 s bound is written as R26a wrote it, counted and
logged. Why: it only matters when the filesystem does not answer a read for
two seconds, and each attempt to hold the change across that stall produced
a new silent loss (round 1: the lifted block dropped it; round 2, live with
a slow FUSE file: the late answer is the OLD text and the save then
overwrites another program's write). D-SINK-22's window (c) therefore
stays, documented, as it is on 0.14.2. KEEP R27a window (a) -- a save asked
while our previous write is in flight waits for it to land, then reads --
PROVIDED it never waits on a read past the bound (re-checked with round 2's
slow-file rig).

R29b. KEEP AND FINISH: R27c (the cap re-checked at the probe commit), R28b
(a held migration holds both URLs), R27e / R28e's notice wording minus every
sentence about the removed stall (no shipped copy may promise "saved when
the file answers"), R28c's pins for the decisions that remain, R28d's open
instrument. Remove the pins and patches of what R29a removes, and re-level
what moved, each with a sentence.

R29c. THE ROUND-2 TEXT P2s: `UX.md` 4.4's bracket that says the not-loaded
surface is drawn only at a start; any README / `UX-SOURCES.md` / QA sentence
about the stall or "never a drop" that R29a makes false.

R29d. THE R28b SIBLING: a guide URL that came with an unusable playlist is
never adopted onto another source; it is reported with the playlist (one
notice, no URL) and stripped with it. Pinned, red on lane-sweep-c2.

R29e. Round 2's cheap P3s: the open instrument considers opacity (and says
what covers it) or narrows the claim; `init_pids` scoped to the scenario's
own harness; the held migration's notice says which source ends active
after "Remove one". The others stay recorded.

**What the tree does (lane-sweep-a3 50d440c, on lane-sweep-c2; lane A3's
report, each behaviour claim below re-checked by this lane on lane-sweep-c3
-- the same code -- by calling the model or driving the shipping
`Service.qml` through `tests/service-harness.js`).**
- R29a. `Service.finishStateVerify` is 6f1d176's R26a body again: from the
  watchdog (`stateVerifyWatchdog`, `interval: 2000`, the literal again) the
  save is written without its read, counted in `stateVerifyNoLoad` and
  logged `state.json was not read back within <ms> ms of a save; saving
  without the read`. Gone: `rereadStateVerify`, the re-reads on a joining
  change and in `onSaved` / `onSaveFailed`, the notice and its
  `NOTIFY_IDS` entry and `notifyArgv` branch, the schedule and its four
  counters (`stateVerifySilences`, `stateVerifySecondReads`,
  `stateReadStalls`, `stateVerifyRereads`) and R28c's read-state resets;
  `read-timeout` stays withdrawn. Kept: R27a window (a), `stateSavePlan`'s
  `wait`, `endStateWriteWait` and `stateWriteWaitWatchdog` (2000 ms), with
  the proviso pinned: a write never reported releases the held save to its
  read at 2 s, the view drops that read while the write is out, and at
  R26a's bound the save is written without it, 4 s after it was asked --
  never blocked, never held longer. Five names stay in `model/state.mjs` as
  inert stubs that answer null -- `STATE_READ_BOUNDS_MS`,
  `STATE_READ_TELL_MS`, `stateReadBoundMs`, `stateVerifyTimeoutAct`,
  `stateReadStalledNotice` -- only because the documents cited them in the
  `Model.` form and the defect ledger joins every such citation to an
  export. This lane re-cited every one of them bare (below), so no document
  depends on them any more. 74019 is retired, not reused (`model/build.mjs`
  says so). Called on c3: the five answer null, `notifyArgv
  ("stateReadStalled", ...)` returns null, and `NOTIFY_IDS` ends at
  `mergeDropped: 74018`. [F3, 2026-10-20: the five stubs are DELETED on
  lane-sweep-f4, with their pin's stub half.] Re-run of round 2's load-failure probes
  (`pfail.js`, `p1.js`) on c3: at the stall the favourite is already on
  disk (written blind at 2 s, `file: true`, no notice), and every way back
  after the file goes bad and comes back -- by itself, the next favourite, a
  source verb, a restart -- reads `memOne: true, fileOne: true`, as on
  6f1d176; the R22 block the failure starts is told once (`Saving has
  stopped`).
- R29d. `Model.adoptActiveSource` skips the R4 block when the playlist
  beside the guide URL is unusable: the one step 1 just refused, or, when
  the entry's playlist was seen and so not adopted again, one that does not
  validate (`entryPlaylistUnusable`, the test `reconcileSources` makes).
  The result says `epgWithInvalid`; the service reports
  `entryInputNotice(<name>, "invalid-pair")`, one card, no URL, and the
  owned write strips both once the marker lands. Called on c3 with A active
  and carrying its own guide URL, the entry an `ftp://` or a bare `http://`
  playlist beside a bar guide URL: `epgWithInvalid: true, adoptedEpg:
  false`, A's own guide URL unchanged; the seen sibling (`adoptUrl: false`)
  the same. The same call on lane-sweep-c2: `adoptedEpg: true`, A's guide
  URL the bar's. With no active source there is now one notice where there
  were two. The two sentences, from the model:
  `playlistUrl in the bar settings was not a usable URL and was removed,
  with the epgUrl beside it. Add or edit sources in the guide's Sources
  screen.` and `epgUrl in the bar settings came with a playlistUrl that
  was not a usable URL, and was removed with it. Add or edit sources in the
  guide's Sources screen.`, both titled `Bar setting removed`; the setting
  names are composed from `RETIRED_SETTINGS` (a first draft wrote them as
  literals beside the verbs and `tests/test_shipped_copy.py` went red).
- R29e. (1) `scripts/dev-harness/shell.qml`'s `openSample` multiplies each
  delegate's opacity by every ancestor's up to the window, and
  `HarnessLib.openDrawnSet` counts a delegate at effective opacity 0 as not
  drawn; what "drawn" still does NOT cover is stated in the harness README
  (an item stacked over the view, an ancestor's clip, a layer or shader
  effect, a fade's strength -- a delegate counts from its first frame above
  0, D13). (2) `init_pids` requires the run's own `--state-dir` in the argv
  it matches; preflight S4 starts two stand-ins and only this run's may be
  named. (3) The `full` body ends `; the bar's playlist then becomes the
  active source.` -- called on c3: `The playlist set on the bar, and its
  guide URL if one is set, were not moved into Sources: Sources already
  holds 50 sources, the most it can. Remove one in the guide's Sources
  screen and the bar's playlist and its guide move in together; the bar's
  playlist then becomes the active source.`
- R29b's copy: no shipped file carries `Saving is waiting`, `saved when the
  file answers` or `never a drop` as current behaviour (the README's
  troubleshooting bullet is deleted; lane A3 checked its own files).
- R29c: `UX.md` 4.4 corrected where it stands. Called on c3 (round 2's
  `p3.js`): a loaded state with no active source, then a seen write of
  `{garbage`: `Model.guideSurface` answers `stateUnreadable`, titled
  `Saving has stopped`, `midSession: true`.

**The measurements R29 rests on (lane A3's runs; transcripts in that lane's
session scratch directory, copied 0600, not the tree).**
- R29a's proviso, live, with round 2's slow-file rig rebuilt over the tree
  (FUSE mode Q), nested headless cage on `private-bus.sh`
  (`key-20261020-184229-2540898`): an edit, and a second asked while the
  first one's write was out, every read stalled -- w-one written at +2.0 s
  without its read, the second edit's read stalled at +2.0 s and w-two
  written at +4.0 s (`not read back within 2002 / 2001 ms`; a second run
  2103 / 2022); no 74019, no 74017, nothing blocked, both labels across a
  restart. The control with no stall reached the same end state with no
  watchdog line. Window (c) as on 0.14.2 with the same rig: HS5 (an in-app
  add and a hand-run helper add during the stall) keeps both; HS7 (an
  atomic replace adding a favourite beside a label edit) loses the
  favourite and keeps the label, as on 6f1d176. [F2, 2026-10-20: the two differ by WHEN the other program wrote, not by which program it was -- the FUSE log has the helper's rename 1.7 s after the shell's write without its read and the replace's 1.4 s before it; a helper add within the 2 s bound, or before a later save while the reads stay stalled, is lost the same way (round 3's live review: a helper add followed 1 s later by a label edit, lost 3 of 3 on lane-sweep-c3 and on 6f1d176; node `F2 (<tag>): window (c), stated ...`)]
- key-scenario: forward 138 / 0 (`key-20261020-184353-2546836`, 575.9 s,
  load 4-6); `--baseline lane-sweep-c2` 134 / 4, K1..K3 (`reports:
  epgUrl:no-source,playlistUrl:invalid`) and B40 (`a-epg:bar ... pair:0
  file:yes`), `key-20261020-190233-2645772`; `--baseline 6f1d176` 127 / 11,
  those four and B32, B33 (`waited:NOFIELD`), B35..B39
  (`key-20261020-185340-2605786`). `sources-scenario.sh` 66 / 0
  (`sources-20261020-185340-2605788`).
- open-scenario at 10,000 channels: forward 33 / 0
  (`open-20261020-192446-2690236`, load 1.4-3.5): list cold realised median
  547 ms (546-558), wall 547 (519-572); warm 34 (27-45) and 32 (29-39);
  drawn 10 and 16, built 13 and 18-21. `opacity-fade.patch` (the review's
  mutation, kept in `spikes/open-mutations/`): 31 / 2, L6 and W6 red at a
  warm median of 338 / 341 ms (`open-20261020-192723-2700535`), where
  R28d's instrument passed it at 30 / 0. Rule 7's 150 ms still holds warm
  and not cold in the cage's floating window; the layer-shell figure on
  Hyprland is UNVERIFIED.

**Seen red (lane A3, by its report).** The final tests over lane-sweep-c2's
product code: 33 failures of 2,664 in each own-echo mode -- R29a's bound
pins and the write-wait bound (3 x 4; on c2 the save stays parked,
`noLoad:2`), R28c's `onSaveFailed` pin (4), the withdrawal pin, the R14 /
R22a structural pin, R29d's three service pins (3 x 4; A's guide URL the
bar's, `aEpg 'E'`), the pair notice and the shared fixture's adopt check,
and R29e's sentence. Over 6f1d176: 99 of 2,664; there R26a's "bound is 2 s"
pin is GREEN, as it should be, because R29a restores that behaviour. One
decision mutated at a time in e5f6d4d (failures per echo mode, the same in
both): the silent read held past the bound 12, the timeout dropping the
save 14, the timeout not counted 16, window (a)'s wait re-arming instead of
releasing 12, expiry not reset in `onSaved` 4 and in `onSaveFailed` 4, R4
beside an unusable playlist 13, the seen sibling not handled 5, reported as
the old `invalid` 8, the sibling not reported 4; `r26a-watchdog-20ms.patch`
and `r26a-watchdog-no-interval.patch` 8 each, `r27a-wait-never-released.patch`
and `r27a-no-wait.patch` 31 each. S4 against the unscoped `init_pids` 11 / 1
(`got:<both pids>`); D11 and D12 against the harness-lib that read
`visible` alone 17 / 2, D13 green there (the control for the narrowed
claim). Not seen red: the S1 seam (structural) and the stub-inertness pin
(red only on c2, where the names were live).

**Counts.** On 50d440c: node 2,664 in both own-echo modes (2,692 on
lane-sweep-c2: -41 for R29a's deletion, +13 for R29d), python 1,293, qml
spec 78, `qa-lib-test.sh` 515, open preflight 19 (16), key preflight 12
(11), model declarations 787 in 18 parts (786). Floors: `NODE_CHECKS_MIN`
2,692 -> 2,651 -> 2,664, `KEY_PREFLIGHT_MIN` 11 -> 12, `OPEN_PREFLIGHT_MIN`
16 -> 19, key-scenario's `EXPECTED_CHECKS` 10 -> 11 (check-tree) and 135 ->
137 (live), open-scenario's 15 -> 18 and 29 -> 32. Release: 42 files,
`Service.qml` 331,465 of 458,752 bytes.

**Documents corrected (lane-sweep-c3, the documents lane).** Each sentence
below was true of lane-sweep-c2 and is false on lane-sweep-a3, or was false
already (R29c).
- README: the credentials paragraph's windows (one -> two); the migration
  paragraph (the `invalid-pair` notice and what 0.14.2 did; the `full` body
  verbatim; a picked source is what the guide opens on, until "Remove one"
  makes the bar's playlist active; the harness count 136 -> 138); the
  `state.json` entry (the 2 s read back among the ways another program's
  change can be lost; two windows); the no-write bullet's cross-reference;
  the `Saving is waiting` bullet DELETED; the link bullet (two windows, the
  2 s one quoting the journal line, the R27 / R28 builds that never shipped
  in one sentence); the folder-link bullet's window counts; the
  same-instant limit (window (c) and HS5 / HS7); the `Bar setting removed`
  bullet (the pair).
- `UX-SOURCES.md`: 5.9's two `invalid-pair` rows, the `full` row, and two
  round-19 records (R29e, R29d); 5.10's introduction, item 1's withdrawn row,
  item 5's two brackets (the round-18 one, and the round-16 "three windows"
  record), and item 9 re-written to R29a with R28a's account as history.
- `UX.md`: 4.4's two brackets (R29c), 6.3's not-loaded row, 6.4's `full`
  card and the `Saving is waiting` card struck as withdrawn.
- This file: section 2.2, the model table (`adoptActiveSource`,
  `stateSavePlan` / `stateVerifyTimeoutAct`, the schedule row and
  `stateReadStalledNotice` struck as withdrawn, `entryInputNotice`),
  section 6's open row, the round-12 copy table's header bracket and
  withdrawn row, the R26a record's watchdog line, the R27a record (twice),
  and the round-18 record (a header bracket, R28a marked withdrawn, its open
  items answered); every `Model.`-prefixed citation of the five stubbed
  names re-cited bare.
- `ARCHITECTURE.md`: section 5's round-17 amendment (two brackets, and
  D-SRC-47's "can no longer happen" qualified: a write the view never
  reports lets the next save be written blind 4 s after it was asked, while
  the first may still be out), the round-18 amendment marked withdrawn, a
  round-19 amendment; section 4's migration line and the `epgUrl` row
  (R29d); the failure-modes entry; the open-budget row (R29e's instrument
  and figures); the start-up section's windows bracket.
- `OMARCHY-PLUGIN-CONTRACT.md`: the eighth fact (R29a's answer, three
  brackets) and a new FileView fact -- a read stalled in the filesystem
  answers with the file as it was when asked, and a rename while it is out
  raises no new read -- from round 2's live review's FUSE log.
- `QA.md`: TC-CFG-33 (bracket), TC-CFG-36 (R29e), TC-CFG-37 RE-WRITTEN to
  R29a's case with R28a's as history, TC-CFG-38 (R29e), TC-CFG-39 new
  (R29d), PERF-02's note, and the round-19 record. `QA-SOURCES.md`:
  SRC-MIG-61 (bracket), SRC-MIG-65 re-written, SRC-MIG-66 (R29e),
  SRC-MIG-67 new (R29d), SRC-PERF-04.
- `scripts/dev-harness/README.md`: the Round 18 record (two brackets).
  Lane A3's Round 19 record and open-scenario section stand as it left
  them, checked against its report.

**This lane's search, by shape (rule 15).**
- "A read that does not answer keeps the change / is asked again / is
  told": grep over the nine files for `Saving is waiting`, `74019`,
  `file answers`, `never a drop`, `never a blind`, `never blind`, `held
  save`, `kept held`, `read again`, `schedule`, `8 seconds`, `8 s`,
  `STATE_READ`, `stateReadBoundMs`, `stateVerifyTimeoutAct`,
  `stateReadStalled`, `stateVerifySilences`, `rereadStateVerify`. Corrected:
  every hit stating it as current (the README's four places, `UX.md` 6.4,
  `UX-SOURCES.md` 5.10 item 9, `ARCHITECTURE.md` section 5 and its
  failure-modes entry, the contract's eighth fact, `QA.md` TC-CFG-33 / 37,
  `QA-SOURCES.md` SRC-MIG-61 / 65, this file's model table). Cleared as
  history, each now under an R29 bracket: the round-18 record, R28a's
  table rows, the harness README's Round 18 record. Cleared as other
  meanings: the player's and mpv's "stall" (`UX.md` 4.x, rewind), D-CLIP-1's
  "1 s per-read timeout", the init check's `did not answer` (which stands).
- "How many windows a save can be written without its read": grep `narrow
  window`, `one window`, `the window`, `windows`, `three windows`, `two
  windows`, `window (c)`, `window c`, `0644`, `umask`. Corrected: the
  README (credentials paragraph, `state.json` entry, the three link
  bullets), `UX-SOURCES.md` item 5's round-16 record, `ARCHITECTURE.md`
  section 5 and the start-up bracket, the contract. Cleared: section 5's
  round-16 "What remains" (three windows, bracketed by the amendments after
  it, which now end at two) and the README's channel-cache sentences.
- "Another program's change written over by a save without its read":
  grep `can be lost`, `same instant`, `written over`, `read back within 2`.
  Corrected: the README's `state.json` entry and its same-instant limit.
  Cleared: `ARCHITECTURE.md`'s "What remains" (already says so).
- "The guide URL beside an unusable playlist": grep `not a usable`,
  `invalid`, `no-source`, `Bar setting removed`, `R4`, `step-2`, `guide
  URL`, `epgUrl`. Corrected: the README migration paragraph and
  troubleshooting bullet, `UX-SOURCES.md` 5.9, this file's section 2.2 and
  `adoptActiveSource` / `entryInputNotice` rows, `ARCHITECTURE.md`'s
  migration line and `epgUrl` row, QA's new rows. Cleared: `QA.md`
  TC-CFG-15 and the D16 rows (the playlist's own refusal, unchanged), and
  the `no-source` row (now only a guide URL with no playlist at all; lane
  A3's reading of the model, which this lane's call agrees with).
- "Which source is active after Remove one" and "the guide opens on its
  setup form": grep `becomes the active`, `ACTIVE source`, `setup form`,
  `opens unconfigured`, `whichever source`. Corrected: the README migration
  paragraph, the `full` body everywhere it is quoted (README, `UX.md`,
  `UX-SOURCES.md`, this file). Cleared: round 17's and 18's records
  (history; the R29e record follows them).
- "The not-loaded surface is drawn only at a start": grep `only drawn`,
  `only ever drawn`, `at a start`. Corrected: `UX.md` 4.4 (two brackets) and
  6.3. Cleared: `UX-SOURCES.md` 5.10 item 2 ("At a start, the guide draws
  the no-write surface"), which says when it is drawn at a start, not that
  it is drawn only then.
- "What the open instrument counts": grep `drawn`, `intersect`, `opacity`,
  `visible area`. Corrected: `ARCHITECTURE.md`'s budget row, `QA.md`
  TC-CFG-36 and PERF-02, `QA-SOURCES.md` SRC-PERF-04, this file's section-6
  row. Cleared: lane A3's harness README section.
- Every notice quoted in the nine files was checked against the model on
  c3 by a one-off script (session scratch, not the tree) that composes
  `entryInputNotice` for every reason and both names, the two no-write
  sentences and every `stateUnreadableNotice`, and counts each sentence
  whitespace-normalised in each file; the old `full` body (ending `move in
  together.`) survives only inside history brackets.

**Open for the lead (decision requests, no defect ids: the board's ids and
states are the lead's, and none is cited here).**
- (1) [Done on lane-sweep-f4, 2026-10-20 (F3): the five are deleted.] The five inert stubs. No document cites them in the `Model.` form
  any more (on c3 a `git grep` for the five names after `Model.` finds
  only the withdrawal pin in `tests/Model.test.js`, which calls them to
  prove they answer null), so the integration can delete them, their
  export lines in `model/state.mjs` (and the generated `Model.mjs` through
  `split-model.mjs --relink`) and that pin's stub half, with the ledger
  green -- a code change this lane may not make. Bare citations of the
  names remain in history records. Re-counted by `pfail.js` on c3, the
  four ways back above are kept 8 of 8 each (two faults, two hosts, two
  echo modes).
- (2) 74019 is retired and not reused (lane A3's comment in
  `model/build.mjs`). The documents say so where the card is struck; no
  reserved-id list exists to add it to.
- (3) R29d's reason `invalid-pair` and its two sentences are new copy,
  quoted verbatim above. With no active source one notice now replaces two
  (K1..K3 `playlistUrl:invalid-pair`); the ruling's "one notice" is read
  as covering that case. To confirm.
- (4) D-SINK-22's window (c) stays open by this ruling and the documents
  state it (the README, `UX-SOURCES.md` 5.10 item 9, `ARCHITECTURE.md`
  section 5), with HS7's loss measured on this tree as on 6f1d176. It has
  no board id of its own beyond D-SINK-22; if the board closes D-SINK-22
  on window (a), window (c) needs one. [2026-10-24, P23 lane A: windows (b)
  and (c) are NARROWED, not closed -- the save that creates the file at
  0644 still can, and the repair the landing asks for (`state mode`,
  D-SRC-49) makes it 0600 within the helper's start; the exposure is those
  milliseconds, no longer the session. R29a's descope of the stalled-read
  handling is untouched: nothing here touches a read path or a save path.]
- (5) The R22 question carried from round 18 (2): a change made in a
  mid-session block is dropped on three ways back, as on 0.14.2. R29a
  removes the stall door into it; a read that answers with a load failure
  within 2 s still opens it.
- (6) The cold open, about 547 ms at 10,000 channels in the cage, is still
  unfiled (round 1 proposed the next free `D-PERF` number); the warm open
  holds at 32-34 ms.
- (7) Rule 13, carried: the README and `UX-SOURCES.md` quote
  `tests/fixtures/state-notices.json` and `Model.entryInputNotice` word for
  word, and no check joins them; this lane checked the join once, by
  script.

### D-SINK-19 round 19, the fourth sweep (lane-sweep-f4, 2026-10-20; the lead's F1-F4 from round 3's three reviews of lane-sweep-c3)

**What the lead asked for.** Four items from the reviews of lane-sweep-c3
(4925696), named F1 to F4 in the lead's brief (lane labels, not board ids):
F1, P2, the held-full migration's retry losing both URLs; F2, P2, the
documents' claim that a hand-run `state source add` survived a stalled
read; F3, P2, the five inert stub exports; F4, four P3s (an unpinned
decision in R29d and three sentences).

**F1. THE MIGRATION RIDES ITS RECORD.** The retry after a removal migrated
the bar's playlist and guide URL into memory with the marker; another
program filled the freed place before that save's read answered; the merge
kept theirs and dropped the migrated record at the cap; the marker survived
the merge and landed; and the owned write stripped both URLs off the
entry. Neither was in any record, and the user was told only
`1 source added here (the limit is 50 sources) was not kept. Make room,
then add it again.`, about a source they had not added. Round 3's dataloss
review measured it with `pcap.js` on all four host and echo combinations of
c3 and of c2; 6f1d176 evicts silently instead. Now
`Model.mergeForeignState(base, ours, theirs, opts)` takes
`opts.migrationKey`, the key of the record this session's migration added
(`Service.migrationAddedKey`, set when the marker is set, "" when the
migration added no record), and when the marker is OURS ALONE and that
record did not land as ours the marker is not carried and
`migrationHeld` says why: "full" (dropped at the cap; not counted among
`dropped.sources`, so no 74018, and an `activeKey` naming it goes back to
theirs) or "changed" (rule 15's sibling below). The service logs
`Model.migrationHeldAgainLine(why)` (no key, no URL), sets
`migrationHeldFull`, and the reconcile the merge already runs retries at
once -- over "full" it is held again under the one `Sources is full` card
(`adoptActive` tells it, once a session), so the next removal retries it;
over "changed" it migrates onto the record theirs added.
- Measured: `pcap.js` on this tree, every combination:
  `{"fired":true,"n":50,"newInFile":false,"eInFile":false,"marked":false,"entryPl":true,"entryEpg":true,"notes":["74016"],"reports":["playlistUrl:full"]}`
  (on c3 `marked:true`, `entryPl:false`, `entryEpg:false`, notes 74016 and
  74018).
- Pinned through `tests/service-harness.js` on both hosts and both echo
  modes: `F1 (<tag>): held full, a HAND-RUN ...` (the race, then one more
  removal moves both in, across a restart; the R21 oracle on both URLs)
  and `F1 (<tag>), rule 15: ...`; in the model `F1: mergeForeignState --
  ...` (seven cases, among them an in-app add dropped beside the migrated
  record still reported, no `migrationKey`, theirs carrying the marker,
  and the migrated record removed HERE before it landed, which stands and
  is never retried).
- Seen red on lane-sweep-c3 with this tree's test file: 9 of 2,678 checks
  in each own-echo mode, the four race pins, the four sibling pins and the
  model pin. Ten mutants of the fix, each red in both modes: the
  service not recording the key (8), not passing it (8), not setting
  `migrationHeldFull` in the merge (8), the "changed" branch removed (5),
  the record still counted dropped (5), the marker carried regardless (5),
  the `activeKey` not restored (1), theirs' marker ignored (1), the "ours
  holds the record" guard removed (1), the journal line ignoring its
  reason (1).
- An in-app removal has no such window: its retry joins the removal's own
  read, and a probe whose hand-run add fires at the first read that finds a
  place free never fired on that path (`fired:false`; the helper refuses
  `too_many` at 50, so no read in between can see a free place).

**F2. WINDOW (C) IS DECIDED BY WHEN, NOT BY WHO.** The README, `UX-SOURCES.md`
5.10 item 9, `ARCHITECTURE.md` section 5's round-19 amendment, the round-19
record above and `QA.md` TC-CFG-37 contrasted a helper add that was kept
with a replaced favourite that was lost. Lane A3's own FUSE log
(`a3-slow/run1.out`) has the helper's rename 1.7 s AFTER the shell's write
without its read (599234291 -> 599235999) and the replace's 1.4 s BEFORE
it (599265697 -> 599267127); round 3's live review lost a helper add
followed 1 s later by an in-app label edit 3 of 3 on c3 and 3 of 3 on
6f1d176; and its node probe lost a helper-style add landing within the
bound. The measured rule, now stated in each of those places: with the
reads stalled, another program's write is lost when it lands within the
read's 2 s bound or before a later save of the shell's while the reads
stay stalled, and kept when it lands after that save with no later save --
whichever program wrote it. Pinned: `F2 (<tag>): window (c), stated ...`
(a helper add and a replace, each within, after, and after-then-edit; the
in-app favourite kept in all six), identical on 6f1d176 by the same probe
over its own `Service.qml`; red on a mutant whose bound holds the save
instead of writing it (18 checks) and on a double whose replace raises a
load (24).

**F3.** The five stubs are deleted from `model/state.mjs` and from
`Model.mjs` through `split-model.mjs --relink` (`check ok`, 783
declarations in 18 parts), with the stub half of the R29a pin; the rows
that called them inert stubs say they were deleted, and no document cites
any of them in the `Model.` form.

**F4.**
- R29d's `{ origin: "cli" }` in `entryPlaylistUnusable` is pinned, through
  `Model.adoptActiveSource` (the function is not public):
  `F4 / R29d: a guide URL arriving beside a playlist already seen ...`,
  seven playlist values; red with `"guide"` (1 check in each mode).
- The README's 0.14.2 parenthetical now gives the no-active case (two
  notices: the playlist's and the guide URL's `no-source`), measured by
  round 3's `adopt.mjs` on a `git archive` of v0.14.2:
  `noactive {"invalid":true,"noSourceEpg":true}`, and 0.14.2's
  `Service.qml` reports each.
- The README's `Bar setting removed` bullet quotes both `invalid-pair`
  sentences, counted against `Model.entryInputNotice` by a scratch script
  (the playlist's twice in the README, the guide URL's once), and says
  twice in the one case the R29d rule-15 pin shows (`playlistUrl:invalid`
  then `epgUrl:invalid-pair`).
- `ARCHITECTURE.md`'s open-budget row gives its load (1.40 as the run
  started, 1.4-3.5 over it) and the heavy-load figures from round 3's live
  review (`open-20261020-210029-2957576`, load 10.37: warm median 120 /
  126 ms, max 158 / 217; cold 2,354 / 2,291), and says the budget is not
  met under heavy load.

**Rule 15, what was searched.** For F1, every place a merge or a cap can
remove a record ours added while something that depends on it survives:
`mergeForeignState`'s cap truncation (fixed), its conflict branch for a
record both sides added (the sibling, fixed as "changed"), its branch for
a record theirs removed (cleared: a record ours ADDED is not in the base,
so theirs cannot remove it; and a migration that resolved to an EXISTING
record theirs then removed is the user's own removal of that source, whose
guide URL goes with it as any removal's does -- recorded below), the
probe commit's cap (R27c, already re-checks), `parseState`'s cap on a load
(theirs alone, no marker of ours), and the saved-search and hidden-group
caps (no marker depends on them). For F2, every document sentence that
contrasts the helper with the replace: the five named, the round-19
record's HS5 / HS7 sentence and the harness README's (bracketed), and
`OMARCHY-PLUGIN-CONTRACT.md`'s FileView fact (cleared: it states the
timing). For F3, `git grep` for the five names: only history rows remain,
each now saying deleted.

**Open for the lead (decision requests, no defect ids: the board's ids are
the lead's).**
- (1) A migration that resolved to an existing record which another
  program removes in the read window lands its marker; the bar's guide URL
  adopted onto that record goes with it, told by the merge's conflict
  line only. Recorded as the user's removal, not fixed; to confirm.
- (2) Rule 13, carried from round 19's item (7): no check joins the
  README's and `UX-SOURCES.md`'s quotes to the model; this lane counted
  them once, by script.
- (3) Round 3's other P3s were not in the brief and are untouched: R29b's
  `else if (out.adoptedUrl)` still survives deletion (now also reached by
  the "changed" retry, where it clears `migrationHeldFull`), and window
  (a)'s untold 4 s.
