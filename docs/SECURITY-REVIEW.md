# Omarchy IPTV -- Security review (gate G4)

Owner: Software Architect. Task M1.1-04. Reviewed: `main` at commit
`f03fef2` (lane A merge; the working tree at `52ecb40` differs only in
docs/STATUS.md). Date: 2026-09-12. Machine of record (Omarchy 4.0.3,
Quickshell 0.3.1, mpv 0.41.0, Python 3.14.7 / expat 2.8.4).

Scope: every line of `bin/omarchy-iptv`, `Model.js`, `Service.qml`,
`Guide.qml`, `BarWidget.qml`, `manifest.json`, `contrib/*`,
`scripts/dev-harness/*` (dev-only), read against ARCHITECTURE.md section 8,
rulings R9/R11/R12, PRODUCT.md decision 8 and the QA.md `SEC-*` cases.
Method: static review plus local experiments in a scratch directory
(helper run in-process with peak-RSS measurement; an idle `mpv --no-config
--vo=null --ao=null` on a private socket for IPC semantics; a throw-away
Quickshell instance with its own `XDG_RUNTIME_DIR` for `FileView` write
modes). No plugin code was modified, nothing was installed, no network
stream was played. Line numbers below refer to the files at `f03fef2`.

## Verdict

**PASS WITH FINDINGS.** No P1. One P2 (S-01: a playlist-controlled channel
name is property-expanded by mpv into the window title, so a title such as
`${path}` renders the stream URL with credentials on screen, against R12).
It is a two-line fix and must land before release (PLAN.md: zero open
P1/P2). Seven P3 hardening items, none blocking. The design goals of section
8 (argv only, playlist data is data, scheme allow-lists, private files,
redaction at every sink, minimal IPC) are implemented and held up under the
abuse cases below.

## Findings

| ID | Sev | Where | Finding | Why it matters / scenario | Recommended fix | Blocks release |
|---|---|---|---|---|---|---|
| S-01 | P2 SEC | `Model.js:960-961` (`--title=` / `--force-media-title=`), `bin/omarchy-iptv:1345-1346` (`set_property title`) | The channel name is passed verbatim as mpv's `--title`. mpv expands `${property}` references in `--title` (man mpv: "Properties are expanded"; `title` is re-expanded on every title update, so the IPC path is affected too). Verified on this machine: `expand-text "BBC ${options/input-ipc-server}"` -> `BBC /run/user/1000/.../t.sock`; `${path}` expands to the playing URL once a file is loaded. | A playlist entry titled `${path}` (or `${stream-open-filename}`, `${playlist/0/filename}`) puts the full stream URL, including Xtream credentials, into the mpv window title: visible in the Hyprland title bar, `hyprctl clients`, the Activity/window switcher, screen shares and screenshots. R12: "never render a playlist or EPG URL beyond scheme and host anywhere". The name also reaches `force-media-title`, which is not expanded (verified), and the bar/guide, which never expand. | Prefix the title with mpv's raw marker, `"$>" + name` (verified: `expand-text "$>${options/input-ipc-server}"` returns the literal text), or replace every `$` with `$$`; do it in `Model.buildMpvArgv` and in helper `cmd_play` (`title` only; `force-media-title` may stay raw). Add a node test (`--title=$>${path}`) and a `tests/test_mpv.py` case. | Yes (P2) |
| S-02 | P3 SEC | `Service.qml:556-565` (`stateFile`, `atomicWrites: true`), `Service.qml:286-293` | Quickshell's `FileView` creates a NEW file with mode 0644 (verified: `new.json` -> `644`; an existing 0600 file keeps 0600; the write follows a symlinked target). ARCHITECTURE.md 8.5 promises 0600. The helper's own writes are 0600 (verified `channels.json`, `playlist-status.json`, `epg-*`, `state.json` via the `state` subcommand). | `state.json` holds channel names and ids only, inside a 0700 directory created by `mkdirProc` (`Service.qml:657`), so nothing is exposed today; it is a documented-behaviour mismatch and a foot-gun if the directory mode is ever loosened. | Either create `state.json` through the helper on first run (`state show` already writes nothing; add `state init` that writes the default state 0600) so `FileView` inherits 0600, or run `["chmod", "600", path]` after the first `onSaved`. Update ARCHITECTURE.md 8.5 to say the directory, not the file, is the boundary for `FileView` writes. | No |
| S-03 | P3 SEC | `Model.js:970-971` (`--`, URL), `Service.qml:399-406` (`mpvProc.command`) | The first channel's stream URL (and header values) sit in mpv's argv for the whole life of the mpv process (`/proc/<pid>/cmdline` is 0444 here, `/proc` mounted without `hidepid`), i.e. `ps aux` shows the credentialed URL for hours, even after zapping to other channels over IPC. ARCHITECTURE.md section 6 only acknowledges the helper's argv "for a few hundred milliseconds". | Other local accounts on the same machine can read it. Omarchy is a single-user desktop, so the practical exposure is low, but it is the one place the credential leaves the 0600/0700 boundary. | M2 (with the detached-mpv rework, R10): start mpv with `--idle=once` (or `--playlist=<0600 file in the runtime dir>`) and `loadfile` the first channel over IPC like every later one, so no URL is ever in argv. M1: document in README's settings section next to the shell.json warning. | No |
| S-04 | P3 | `Model.js:989` (`streamFailed` body), `Model.js:261-267` (`displayName`) | The notification body starts with the channel name. `omarchy-notification-send` (verified, it uses `busctl`, not `notify-send`) treats a body matching `--glyph=*`, `--urgency=*`, `--app-name=*`, `--icon=*`, `--expire-time=*`, `--image=*` or `--replace-id=*` as an option: `--urgency=x did not play` -> "Unknown urgency", exit 1, no toast (verified); `--icon=x did not play` -> a toast without the channel name. | A playlist author can suppress the "Stream failed" notification for any channel (UX 6.4 / R11 degraded on hostile input). No code execution, no other flags are reachable because the body always carries ` did not play`. | Never let a rendered name start with `-`: in `displayName`, strip leading `-`/whitespace (or fall back to `Channel <n>`), and quote the name in the body (`"<name>" did not play`). Same guard protects future `--exec` use of the wrapper. | No |
| S-05 | P3 | `bin/omarchy-iptv:560-561` (`urlopen(timeout)` + `response.read()`), `Service.qml:231-238` (no watchdog on `playlistProc`/`epgProc`) | `--timeout` is a per-socket-operation timeout, not a deadline. A server that trickles bytes keeps the helper alive indefinitely (verified: with `--timeout 3` a 2-s-per-line server held the helper 14 s and returned ok). The service never kills a running helper and `refreshPlaylist()` refuses to start another while one runs. | A slow or hostile provider parks the plugin in "refreshing" until `omarchy restart shell`; manual `r` is silently queued. Memory stays bounded (64 MB cap). | Read in chunks under a wall-clock deadline (e.g. `max(timeout, 60) s` total) in `read_http_source`; optionally a service-side timer that SIGTERMs a helper older than, say, 120 s and reports `Timed out`. | No |
| S-06 | P3 | `bin/omarchy-iptv:533-560` (`split_userinfo` -> Basic `Authorization`; default `urlopen` redirect handler) | `urllib.request` re-sends every request header except `Content-*` on redirects and accepts `ftp://` targets (verified in `/usr/lib/python3.14/urllib/request.py`: `redirect_request`, "http, https or ftp"). A `http://user:pass@provider/` source that 302s to another host sends the user's provider credentials to that host; a redirect to `ftp://` is fetched via the FTP handler. `file:` redirects are refused (QA SEC-20 holds for `file:`, not for `ftp:`). | Userinfo-style URLs are rare (Xtream puts credentials in the query string, which is forwarded by design); the receiving host is chosen by the provider, so the leak needs a provider that redirects to a third party. | Install a `HTTPRedirectHandler` subclass that drops `Authorization` when the host changes and refuses non-http(s) targets; or refuse redirects entirely when the source had userinfo. Update QA SEC-20 wording. | No |
| S-07 | P3 | `bin/omarchy-iptv:421-473` (no channel cap), `Service.qml:275-280` (`JSON.parse` on the UI thread), `Guide.qml:290-293` (`groupModel` one row per group) | The only bound on `channels.json` is the 64 MB source cap; a 64 MB playlist of 40-byte entries is ~1.5 M channels and a ~300 MB `channels.json` parsed on the shell thread. `displayModel` is capped at 200 rows (`Model.js:335-362`, verified), but `groupModel` grows with the number of distinct groups (10k channels x unique groups = 10k `ListModel.append`s on every signature change). | Denial of service of the shell (freeze/OOM) by a hostile or broken provider. Real lists top out around 11k channels / 1k groups (QA's `index.m3u`). | Cap channels (e.g. 50,000, `warnings`: "N entries beyond the cap skipped") and groups shown in the column (e.g. first 1,000, rest reachable by search) in the helper; the guide then needs no change. | No |
| S-08 | P3 (dev-only) | `scripts/dev-harness/run.sh:153` (`echo ... playlist=$OMARCHY_IPTV_PLAYLIST`), `scripts/dev-harness/shell.qml:86` (`updateEntryInline` logs the whole entry), `run.sh:92,160` (`python3 -m http.server`) | The harness prints the playlist URL to the terminal and logs the full settings entry (which carries `playlistUrl`/`epgUrl`) if the host calls `updateEntryInline`; a hard kill of `run.sh` (SIGKILL) leaves the fixture `http.server` on 127.0.0.1:8765 running. Nothing in `scripts/dev-harness/` is referenced by `manifest.json`, so none of it can be mistaken for runtime. | A developer who points the harness at a real provider leaves credentials in terminal scrollback. | Log `(set)`/`(none)` like `Component.onCompleted` already does (`shell.qml:227`); `trap` the server pid on EXIT; README already says "never run against a real network stream". | No |

## Checklist

### 1. Process launching is argv-only -- PASS

Every process is an argv array: `Service.qml:314` (playlist helper), `:325`,
`:330` (epg helper), `:338` (`["python3", helperPath].concat(args)` where
`args` are literal verbs plus `--id <id>`, `--socket`, `--cache-dir`),
`:399` (`Model.buildMpvArgv`), `:657` (`["mkdir","-p","-m","700",...]`),
`:666` (`["which","mpv"]`), `:226` (`Model.focusPlayerArgv()` constant),
`:251` (`Model.notifyArgv`), `Guide.qml:469` (`["wl-copy", text]`, text is
a constant built from `manifest.id`). Grep for `bash -c|sh -c|shell=True|
os.system|subprocess|execDetached("|eval(|new Function` over the shipped
files: no hits (only `tests/test_helper.py` uses `subprocess.run` with a
list). Helper ids passed to `--id` always start with `t:`/`u:`
(`bin/omarchy-iptv:488-491`), so no id can be parsed as an option; the
playlist URL is the user's own and follows `--url`.

### 2. mpv argv and `mpvArgs` filtering -- PASS with S-01

`Model.js:950-973`: the URL is the last item after a literal `--`; the
node fuzz `buildMpvArgv({url:"--script=/tmp/evil.lua"})` yields
`[..., "--", "--script=/tmp/evil.lua"]` (mpv treats it as a file name).
`--ytdl=no` (`:966`) keeps yt-dlp out of every dead-URL attempt.
`splitMpvArgs` (`:917-930`): tokens must match
`^--[a-z0-9][a-z0-9-]*(=.*)?$` (lowercase only, so D-QA-11 is fixed:
`--INPUT-IPC-SERVER=/x` rejected), reserved names and their `--no-` forms are
dropped (`--no-title` rejected, verified), a bare `--`, `--=x`, non-option
words and whitespace-split values are rejected, so a token can never add or
split an argument.

Honest weighing: `mpvArgs` lives in the user's 0600 `shell.json`; nothing a
playlist or a third party controls reaches it, so the reserved list protects
the service's invariants, not a trust boundary. Of the options asked about,
all exist in mpv 0.41 (verified with `--list-options`) and all pass the
filter except `--script`, `--scripts`, `--config-dir`, `--input-ipc-client`:
`--include=<conf>` silently bypasses the whole reserved list (a config file
can set `input-ipc-server`, `title`, `idle`); `--script-opts`,
`--load-scripts`, `--input-conf`, `--ytdl-raw-options=exec=...` (only with a
user-supplied `--ytdl=yes`), `--o=`/`--of`/`--ofopts` (writes an output
file), `--log-file` (writes a log that contains the full URL, world-readable
under umask 022), `--dump-stats`, `--gpu-shader-cache-dir`,
`--screenshot-directory`, `--sub-file`, `--audio-file`, `--playlist` are
all the user's own choices with no cross-user or cross-trust effect.
Recommendation: add only `--include` (it defeats the list's purpose); list
the rest as documented "your own risk" in README. The S-01 title expansion
is the only playlist-controlled string that mpv interprets.

### 3. Playlist-derived headers -- PASS

Parser: `#EXTVLCOPT` keys are lowercased, only `http-user-agent` and
`http-referrer` become headers (`bin/omarchy-iptv:362-369`); `#KODIPROP`
`inputstream.adaptive.{stream,manifest}_headers` go through `parse_qsl`, names
must match `^[A-Za-z0-9-]+$` (`:96`, `:378`), values have CR and LF replaced
by spaces (`clean_header_value`, `:315-316`); empty values are dropped
(D-QA-10 fixed); option-looking keys are refused with a warning (D-QA-09
fixed, `:97`, `:370-373`). Run of `tests/fixtures/qa-headers.m3u` through the
helper into a scratch cache: 11 channels; `cr.test` -> `User-Agent:
"Evil/1.0 X-Injected: yes"` (single line); `kodicrlf.test` -> `X-Inject: "a
X-Evil: b"`, `X-Ok: "1"`, `Bad\nName` dropped with warning `dropped header
with unsafe name for ...`; `meta.test` value kept verbatim (`$(id)`, backticks,
`;`, `|`, `>` are inert in argv); `optkey.test` UA `--script=/tmp/evil.lua`
stored as a value only; a scan of `channels.json` found zero CR/LF bytes in
any header name or value.

To mpv: launch path `Model.headerArgs` (`Model.js:934-946`) re-validates the
name and drops any value containing CR/LF, emitting `--user-agent=`,
`--referrer=`, `--http-header-fields-append=Name: value` (mpv: `-append`
"does not interpret escapes", so commas stay inside one item, verified via
IPC round trip). IPC path `header_properties` (`bin/omarchy-iptv:1303-1327`)
always sets all three of `user-agent` (falling back to
`option-info/user-agent/default-value`, which returned `libmpv` on this mpv),
`referrer` (`""`) and `http-header-fields` (`[]`), so nothing leaks from the
previous channel; tampered header names/values in a cache are filtered again
here (verified: `{"Bad\nName":"v","X-Ok":"a\r\nb"}` -> `X-Ok: a  b` only).

### 4. Local sources -- PASS

`resolve_source` (`bin/omarchy-iptv:496-510`) accepts only `http(s)://`
with a host, `file://` (host part ignored) and `/`- or `~`-prefixed paths;
`read_local_source` (`:518-530`) realpaths, refuses `/proc/`, `/sys/`,
`/dev/` prefixes, requires a regular file (`isfile`), checks size before
reading and reads at most 64 MB + 1. Scratch results (exit code, wall time,
peak RSS): `/proc/self/environ`, `file:///proc/self/environ`, a symlink to it,
`/dev/zero`, `/dev/stdin`, `/sys/kernel/...` -> `unsafe_path` in 30 ms, 16
MB; a FIFO -> `not_found` instantly (no open, no hang); `truncate -s 65M` ->
`too_large` without reading; a 64 MB sparse file -> read and rejected
`not_a_playlist` in 90 ms, 144 MB; a 200 KB gzip inflating to 200 MB ->
`too_large` at 64 MB, 144 MB RSS (playlist path materialises 64 MB + 1; EPG
path streams through `CappedReader`, 82 MB RSS); a gzip-inside-gzip is
inflated one layer only. `/etc/passwd` and `FILE:///etc/hostname` are the
user's own readable files and yield `not_a_playlist` (QA SEC-10, SEC-12:
uppercase scheme accepted; pin it). Errors carry the base name only
(D-QA-12 fixed).

XMLTV: `xml.etree.iterparse` on system expat 2.8.4 with amplification
protection on by default. A 10x10 nested-entity file -> `bad_xml: limit on
input amplification factor ... breached` in 90 ms / 32 MB; a quadratic
blowup (50 KB entity x 20,000) -> same, 25 MB; `<!ENTITY x SYSTEM
"file:///etc/hostname">` -> `bad_xml: undefined entity` (never read); a
parameter entity plus external DTD at `127.0.0.1:9` -> ignored, no
connection attempted. 10k channels x 50 programmes (65 MB) -> ok in 5.3 s,
183 MB RSS, 14 MB private window; `--now-only` recompute 93 ms / 56 MB.
500k programmes on one channel inside the window -> 3.7 s, 115 MB (the
`EPG_MAX_PER_CHANNEL` cap applies after collection; acceptable under the 64
MB input cap). `root.clear()` after every element keeps the tree flat.
Timeouts: HTTP 20 s per operation (see S-05), IPC 2 s with a deadline
(`:1218-1238`).

### 5. URL and credential exposure (R12) -- PASS with S-01, S-03

Sinks enumerated and checked:

- `console.*`: `Service.qml:354, 368` (`Model.statusReason`, a table
  lookup or `scrubUrls(message)`), `:358` constant, `:397` rejected
  `mpvArgs` tokens (user's own text), `:677, :689` helper stderr through
  `Model.redactUrls`. The helper already redacts every stderr line
  (`log()`, `:195-196`), every error message (`error_payload`, `:679`) and
  even crash tracebacks (`:1555-1557`).
- Notifications: `Model.notifyArgv` (`Model.js:983-1002`) bodies are
  `name + fixed text + scrubUrls(reason)`; verified `"Failed to open
  http://u:p@h/x"` -> `Failed to open h`.
- Bar tooltip: `Model.barTooltip` (`:1170-1178`) shows the name or fixed
  text, never a reason.
- Guide: banner/empty-state/footer use `statusReason`, `statusHost`
  (`Model.hostOf` -> host only), `lastUpdated`; every user string is
  `Text.PlainText` (`Guide.qml:656, 674, 718, 793, 809, 914, 929, 949, 966,
  982, 1115, 1128, 1151, 1202`; `BarWidget.qml:173`); the one `StyledText`
  (`Guide.qml:1220`) renders only the plugin's own hint strings.
- IPC `status`: `statusSummary` (`Service.qml:255-271`) carries
  `sourceHost`, `nowPlaying {id,name,group,launchedFrom,since}`,
  `lastError` (redacted) -- no URL (D-QA-15 fixed).
- mpv stderr/stdout: `rememberStderr` (`:413-420`) redacts each line before
  it is kept; the notification and `lastError` use the redacted tail
  (D-QA-01 fixed).
- Channel names: helper never falls back to the URL (`:335`, D-QA-02
  fixed); `Model.displayName` (`:257-267`) additionally rejects URL-shaped
  names (`http://u:p@h/x` -> `Channel 3`). A name like `user:pw@host/x`
  passes; it is the playlist's own text.
- `state.json`: `recordPlayed`/`pushRecent` store `{id, name, at}` only.
- Cache: `channels.json` stores stream URLs (documented caveat, 0600/0700,
  README lines 45-50 warn); `epg-window.txt` stores titles and a truncated
  SHA-256 of the EPG URL (`source_key`, `:806-808`), not the URL.
- Helper stdout: status objects carry `sourceHost` (`local file` for paths)
  and `warnings` built from channel names.
- Window title: S-01. Process argv: S-03.

Redaction fuzz: helper `redact_urls` and `Model.redactUrls` both reduce
`http://user:secretpass@127.0.0.1:9/live/...` to the host,
`...get.php?username=a@b.com&password=x` to `host`, and the ffmpeg-quoted
`'http://cdn.test/seg1.ts?token=abc'` to `cdn.test`; IPv6 `http://[::1]:8080/`
becomes `[` (cosmetic). Text without a scheme is not touched, which matches
what mpv and urllib print.

Files and directories: helper writes are `O_EXCL` temp + `chmod 0600` +
`os.replace` in a directory forced to 0700 (`:631-647`, `:152-157`);
verified `700` dir, `600` files for every cache and status file and for
`state.json` written by the `state` subcommand. `mkdirProc`
(`Service.qml:657`) creates the three directories 0700 before any write.
mpv creates its socket `srw-------` inside the 0700 runtime directory
(verified); `/run/user/1000` is itself 0700, so no other account can reach
the IPC socket. Stale socket: mpv binds over a leftover socket file
(verified) and helper `status` unlinks one that refuses connections
(`:1379-1398`, verified: `removed stale socket file`). `XDG_RUNTIME_DIR`
unset falls back to `~/.cache/omarchy-iptv/omarchy-iptv/mpv.sock` in both
QML and helper (path doubles, harmless, and the service always passes
`--socket`). S-02 covers the `FileView` mode.

### 6. IPC surface -- PASS

`IpcHandler` (`Service.qml:718-740`): `toggle`, `play`, `stop`, `next`,
`previous`, `refresh`, `status` (R9). `play(id)` accepts an id from
`channelIndex` or a URL that matches a cached channel via `Model.findByUrl`
(`Model.js:238-244`); anything else returns `unknown` and launches nothing.
The service never invokes helper `play --url`; the helper's own `--url` path
still allow-lists schemes before connecting (verified: `file:`, `/etc/passwd`,
`javascript:`, `edl://`, `mf://`, `lavf://`, `http://` (no host) ->
`unsupported_scheme`; `--script=/tmp/x` -> argparse usage error). A tampered
cache entry with a `file:` or option-looking URL is refused by helper `play`
(`:1342`); the QML launch path (`launchMpv`) does not re-check the scheme but
the URL follows `--`, and the cache is the user's own 0700 directory
(hardening item below). `refresh` runs the helper with fixed `--cache-dir`;
no verb takes a path. Overlay `open(payloadJson)` (`Guide.qml:223-241`)
parses with `Model.parseJsonObject` (try/catch, object only) and uses only
string-typed `scope`, `group`, `query`; all three end in `PlainText` labels.
Any local process can call the verbs and `summon`, which is the Quickshell
model for every plugin; no verb escalates beyond what that process could do
with `omarchy bar set`.

### 7. File writes -- PASS with S-02

Helper: atomic temp+rename, symlinks on the target are replaced not
followed (`os.replace`), the temp name is random with `O_EXCL`, paths come
from `--cache-dir`/`--state-dir` (always passed by the service) or XDG with
`~` fallback (`:119-149`). Nothing writes inside the plugin directory at
runtime (`helperPath` is only executed); the only files under `bin/` and
`tests/` that appear at dev time are gitignored `__pycache__` from the unit
tests, absent from a `git clone` install. `FileView` (state) follows a
symlinked target and creates 0644 (S-02), and auto-creates a missing parent
directory (verified), so `mkdirProc` ordering (`dirsReady`, `:286-293`) is
the belt and braces it claims to be. `XDG_RUNTIME_DIR` unset: covered in 5.

### 8. Denial of service / resources -- PASS with S-05, S-07

Caps: 64 MB source (download and local), 64 MB inflated (playlist via
`GzipFile.read(MAX+1)`, EPG via `CappedReader`), `EPG_MAX_TITLE` 200,
`EPG_MAX_PER_CHANNEL` 400, `EPG_VALID_MAX` 300 s. `displayModel` <= 200 rows
in both the empty-query and search branches (`Model.js:340, 355-360`);
`groupModel` unbounded (S-07). Timers (`Service.qml:569-651`): refresh
`refreshMinutes` (clamped 15-1440, `triggeredOnStart`) and
`onPlaylistUrlChanged` both go through a 300 ms debounce with a single
in-flight helper and one queued rerun (`:231-247`, `:467-470`); EPG
recompute every 5 min only while `epgLoaded`; `epgTick` 30 s only rebuilds
the guide while open; health check 10 s only while mpv runs and skips when a
control call is in flight; focus retries capped at 6; `pendingPlayId`
collapses a zap burst to one call (`:164-171`, `:386-392`). Helper `play`
re-reads `channels.json` (2 MB at 10k) per zap: tens of ms. No overall
fetch deadline (S-05).

### 9. Supply chain / integrity -- PASS

`omarchy plugin validate .` exits 0; `find -type l` outside `.git`/`.claude`:
none; `manifest.json` entry points are relative, no `..`, `keepLoaded`
declared. QML imports only `Quickshell*`, `QtQuick`, `qs.Commons`, `qs.Ui`
and the local `Model.js`; no `XMLHttpRequest`, `fetch`, `WebSocket`,
`Qt.openUrlExternally`, `eval` or `Function` constructors anywhere; no
`import` from a URL. Helper is stdlib only (`json re gzip zlib urllib
socket xml.etree hashlib unicodedata`). `contrib/*` are three one-liners the
user pastes (`o.bind(...)`, a menu row, a window rule) with constant
commands. `check.sh` creates symlinks under `/tmp/qmlroot` for `qmllint`
only (lint reads, never executes); a pre-planted `/tmp/qmlroot` by another
account could at most make lint fail.

### 10. Other observations

- Screenshot / screen-share exposure: the guide shows names, groups, EPG
  titles and `scheme://host` at most; the bar shows the name; the mpv title
  is the name (S-01 aside). `epg-window.txt` is helper-private and has no
  QML reader.
- The dev harness does not leave mpv behind (`pkill -f input-ipc-server=<scratch
  socket>` on exit, `run.sh:162`) but can leave the fixture HTTP server on a
  hard kill and prints the playlist URL (S-08). Its IpcHandler target is
  `harness`, distinct from the plugin id, so it cannot be confused with the
  runtime target.
- Logging of stdin: nothing reads stdin; helper `stderr` for control calls
  is collected and discarded (`Service.qml:697`), playlist/EPG stderr is
  logged after redaction.
- `Model.statusReason` maps `not_m3u` but the helper emits `not_a_playlist`
  (`bin/omarchy-iptv:706`), so the guide shows the raw (host-only) sentence
  instead of "Not an M3U file"; functional P3 for QA/FE, not a security
  issue.
- Helper `internal` errors redact URLs in the traceback but not local paths
  (`:1555`); only reachable through a bug.

## Hardening (non-blocking, no defect ids)

1. Add `--include` to `MPV_RESERVED` (`Model.js:62-72`); document that
   `mpvArgs` is trusted input and that `--log-file`, `--o` etc. are the
   user's own risk.
2. `launchMpv` (`Service.qml:395`): refuse to start when
   `Model.looksLikeUrl`-style scheme check fails (mirror `is_stream_url`), so a
   tampered cache never reaches mpv even via argv.
3. `ensure_private_dir` re-asserts 0700 on cache and state on every write;
   the runtime directory is only created by `mkdir -p -m 700`, which leaves
   a pre-existing looser directory alone. Add a `chmod` there too, or have
   helper `status` fix it.
4. Redact local paths (`/home/...`) in `main()`'s traceback output as well.
5. Pin `FILE:///...` (uppercase) as accepted in a test (QA SEC-12).
6. QA SEC-20: reword "urllib refuses non-http redirects" to "refuses
   `file:`/other schemes; `ftp:` is accepted" (S-06).

## Positive observations

- Argv everywhere, in QML and Python; the URL is always the last item after
  `--`; `--ytdl=no` removes the yt-dlp subprocess from every dead-URL zap.
- Stream schemes are allow-listed at parse time and again at `play`; option
  lines, `file:`, mpv pseudo-protocols and host-less URLs are dropped and
  counted.
- Header names validated and CR/LF stripped in both languages, and every
  header property is reset per channel over IPC.
- Every file the helper writes is 0600 in a 0700 directory, atomically;
  mpv's socket is 0600 inside the 0700 runtime directory; stale sockets are
  handled by both mpv and the helper.
- `/proc`, `/sys`, `/dev`, FIFOs, symlinks, oversize and gzip-bomb sources
  are refused cheaply (30 ms, 16 MB) and expat's amplification limit makes
  entity attacks a `bad_xml` error; external entities are never resolved.
- Redaction is applied at the source (helper `log`/`error_payload`/
  traceback) and again at every QML sink; channel names can never be URLs;
  IPC `status` is URL-free by construction.
- `omarchy-notification-send` is driven with a replace-id and fixed
  headline; the wrapper itself uses `busctl -- ...`, not `notify-send`.
- 244 node checks, 127 Python tests and 16 QML checks pin the parsers, the
  argv builder and the IPC client against a fake mpv.

## Commands used (scratch directory, all reproducible)

```
python3 run_helper.py playlist --url file://$PWD/tests/fixtures/qa-headers.m3u --cache-dir <scratch>
python3 run_helper.py playlist --url /proc/self/environ|/dev/zero|<symlink>|<fifo>|<sparse 65M> --cache-dir <scratch>
python3 -c "import gzip;open('bomb.m3u.gz','wb').write(gzip.compress(b'#EXTM3U\n'+b'\0'*(200<<20)))"
python3 run_helper.py epg --url <laughs.xml|external.xml|quad.xml|pe.xml|big.xml> --cache-dir <scratch> --now 1789214400 --force
mpv --no-config --idle=yes --force-window=no --vo=null --ao=null --input-ipc-server=/run/user/1000/oisr/t.sock --title='${path}'
  -> expand-text "${options/input-ipc-server}" / "$>..." / "$$..." ; set_property title ; get_property option-info/user-agent/default-value
qs -p <scratch root> with FileView{atomicWrites:true}.setText(...)  (XDG_RUNTIME_DIR redirected)  -> stat -c %a
omarchy-notification-send --app-name IPTV -u normal -r 74011 "Stream failed" "--urgency=x did not play"  -> exit 1
grep -rnE 'bash -c|sh -c|shell=True|os\.system|subprocess|execDetached\("|command: "|\beval\(|new Function' ...
omarchy plugin validate . ; find . -path ./.git -prune -o -type l -print
```
