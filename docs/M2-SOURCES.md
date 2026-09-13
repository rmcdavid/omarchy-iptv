# M2-01 Sources: product requirements

Owner: Product Owner. Status: v0.1, governs the first M2 lane. Builds on
`docs/PRODUCT.md` (all M1 decisions still apply) and the 0.1.0 release.

## One-liner

Configure and switch playlists from inside the guide: type or paste a
playlist (and optional EPG) URL, keep a history of sources, switch between
them instantly, and never touch a terminal.

## Why

US1 (configure) is the only M1 story that drops the user to a command line,
and provider URLs are long and credentialed. The user asked for exactly this
after the first install. Omarchy already has the primitives: inline text
editing in panels (network passphrase, the uptime-monitor plugin's URL editor)
and `shell.updateEntryInline` to persist settings from QML.

## Locked decisions

1. The active source stays where it is today: `playlistUrl` / `epgUrl` on the
   plugin's entry in `shell.json`. The Sources screen writes them through
   `shell.updateEntryInline`; `omarchy bar set` keeps working and the two
   stay consistent (the service observes settings changes and records them).
2. The source history lives in the state file (`state.json`, schema bumped
   to version 2, still 0600), never in the plugin directory or shell.json.
3. Each source gets its own cache directory keyed by a stable hash of its
   playlist URL, so switching back is instant. Removing a source deletes its
   cache. The helper gains whatever flag it needs to target a per-source
   cache dir; the JSON contracts of section 5 do not change shape.
4. Privacy rules from R12 extend to this screen: the list shows a label and
   the host only; the full URL is visible only inside the edit field the user
   opened, with the query string masked until a reveal key is pressed;
   credentials never reach notifications, logs, tooltips, or IPC output.
5. Input is real keyboard text entry inside the overlay with paste support
   (Ctrl+V / Shift+Insert from the Wayland clipboard). Pasted text is trimmed,
   newlines removed, length capped. Only http(s) URLs and absolute paths are
   accepted, validated the same way the helper validates them.
6. Xtream Codes support is a form on the same screen (server URL, username,
   password) that builds the `get.php?...&type=m3u_plus&output=ts` and
   `xmltv.php` URLs and saves them as a normal source. No provider logins,
   no API calls beyond the fetch.
7. No playlist editing, no per-channel overrides, no cloud sync.

## User stories (must)

- S1 First run: the "No playlist configured" state contains the input.
  Paste or type the playlist URL, optionally an EPG URL, press Enter; the
  guide fetches and shows the result inline ("1,475 channels in 28 groups"
  or the error reason and host) without leaving the overlay.
- S2 Sources screen: reachable from a `Sources` row at the bottom of the
  group column and from one key in list mode. Lists every known source with
  label, host, channel count, last used. Enter switches to it; keys for add,
  edit, remove (with confirm), and back. Everything keyboard-first, mouse
  works too.
- S3 Switching: choosing a source updates shell.json, swaps the cache, and
  redraws the guide from that source's cache immediately, then refreshes in
  the background if the cache is older than `refreshMinutes`.
- S4 Labels: a source gets a default label from the host (or the file name)
  and the user can rename it in the edit form.
- S5 CLI parity: `omarchy bar set ... playlistUrl <u>` adds or updates the
  matching source in the history with a host-derived label.
- S6 Xtream form: server, username, password to a saved source; the form
  never shows the password after saving (edit shows the built URL masked).
- S7 Removal: removing a source deletes its cache directory and, if it was
  active, clears the active settings and returns to the first-run state.
- S8 Errors: an invalid URL is rejected inline with the reason; a fetch
  failure keeps the previous active source and shows the reason.

## Quality bar

Same as M1: `omarchy plugin validate`, qmllint at baseline, unit tests for
all new model and helper logic (state v2 migration, source hashing, label
derivation, URL validation, Xtream URL building, masking), harness
verification with screenshots for every state, a QA pass including a
security review of the new input surface (no shell, no eval, clipboard
content treated as data, length caps, redaction at every sink), and a live
check on the reference machine. The guide open budget (150 ms) and the
10k-channel behavior must not regress.

## Handoffs

Product Owner -> UX designer (docs/UX-SOURCES.md) and Architect
(docs/ARCHITECTURE-SOURCES.md) in parallel -> Product Owner reconciles ->
FE lane(s) -> QA -> Product Owner accepts -> tag v0.2.0.
