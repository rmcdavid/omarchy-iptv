# Omarchy IPTV - QA test plan, fixtures and live-shell runbook

Owner: QA. Status: v0.2 (2026-09-13): v0.1 written during M0-08 while the FE
lanes build M1; v0.2 carries the corrections found during the harness pass
(docs/QA-RESULTS.md, defects D-LIVE-nn in docs/STATUS.md). Governs M1.1-01 (functional), M1.1-02 (theme), M1.1-03
(performance), the QA half of M1.1-04 (security evidence), M1.1-06
(regression), REL-01 and REL-02.

Documents of record this plan verifies against: `docs/PRODUCT.md` (US1-US8,
quality bar QB1-QB5), `docs/ARCHITECTURE.md` (sections 5-8, 10, 12 rulings
R1-R13), `docs/UX.md` (sections 3, 4, 6, 7), `docs/PLAN.md` (gates G0-G5,
severities), `docs/QA-ASSETS.md` (public sources). This file is ASCII; where
UX.md writes `...`, `"x"` and ` - ` the implementation must use the real
codepoints listed in UX.md's table (U+2026, U+201C/U+201D, U+00B7). Glyphs are
written as their codepoint (U+F0502 etc., see UX.md 5.5).

Machine of record (verified 2026-09-12): Omarchy 4.0.3, Quickshell 0.3.1,
Hyprland 0.56.2, mpv 0.41.0, Python 3.14.7, node 26.8.1 (mise, dev only),
one monitor `eDP-1` 1366x768 scale 1, current theme `retropc`, shell launched
by `omarchy-launch-shell` through `systemd-cat -t omarchy-shell` (so its
console is in the user journal), `SUPER SHIFT + T` free, `SUPER CTRL + T` =
Activity, no `omarchy-iptv` directories present, `~/.config/omarchy/shell.json`
mode 0600 with `bar.layout.{left,center,right}` entries and an empty
`plugins: []`.

## 0. How to read and execute this plan

- Test case ids are `TC-<AREA>-<nn>`. Areas: INST (install and lifecycle), CFG
  (settings), BRW (browse and keys), PLAY, BAR, FAV (favorites and recents),
  EPG, RFR (refresh and offline), UI (states, microcopy, theme), A11Y, SEC,
  PERF, PARSE (helper parsers), MODEL (Model.js). Security cases are numbered
  `SEC-nn`, performance cases `PERF-nn`.
- "How" column: `A` = automated, with the exact command and file; `M` = manual,
  with the runbook step in section 5 that executes it. `A*` = automated test
  that the FE lanes are expected to add (section 2 lists them); until it lands,
  QA runs the fixture through the helper by hand (section 7 commands). `X` =
  observed at the real sink by the accessibility harness (`tests/a11y/`), which
  is a lane tool and deliberately **not** part of `scripts/check.sh` (PLAN-NEXT
  decision 9); an `X` case is satisfied only by a dated run whose output is
  filed in `docs/QA-RESULTS.md`, never by the harness merely existing. The
  conditions under which the harness would join `scripts/check.sh` are
  proposed, and not implemented, in `docs/UX.md` 7.1a.
- **A criterion may not be a grep for the string the implementation was written
  to contain** (CLAUDE.md rule 14). Four criteria in this plan and in
  `docs/QA-SOURCES.md` were exactly that -- TC-A11Y-01, TC-BAR-11, SRC-A11Y-01,
  SRC-A11Y-05 -- and all four passed for months over a surface that publishes
  nothing to anybody. They are rewritten as `X` cases. Where neither calling
  the shipping logic nor observing the sink is possible, the rule the criterion
  covers is marked UNVERIFIED in the document that states it and stays marked.
- **The dev harness touches nothing the user owns** (F-HARNESS-20). Every
  process `scripts/dev-harness/run.sh` starts -- the nested shell, the helper
  the service spawns, the player the helper forks -- and every scenario
  driver that uses it runs with a scratch `HOME` under the harness directory,
  with `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME` and
  `XDG_STATE_HOME` inside the same tree and `MPV_HOME` / `XCOMPOSEFILE`
  dropped when they name the real home. The shipped code has no override
  for this and gets none: the helper's `config shield` takes the host's
  settings file from `$HOME` because the host does, so the harness moves
  `HOME`. Two theme files are copied in (never linked); nothing else comes
  from the real home. Verified by `tests/test_harness_home.py` (A: the
  shipped helper, Python and mpv asked where their paths land under
  `harness_env`, and a decoy home's 0644 config proven untouched by the
  shield) and, live, by `stat` of the real `~/.config/omarchy/shell.json`
  and `~/.local/state/omarchy-iptv/state.json` before and after a scenario
  run; `scripts/dev-harness/README.md` has the layout.
- Every M case is executed on the live shell after the lanes merge, in the
  order of section 5. Results are recorded in `docs/STATUS.md` (handoff
  format, PLAN.md section 7) as `pass` / `fail D-<n>` / `not run <reason>`
  with the evidence file name from section 5.9.
- A case fails if any expected string, glyph, count, file mode or timing is
  off. Microcopy is compared verbatim against UX.md section 6.
- Severities (PLAN.md section 6): P1 blocks a user story, P2 degrades one,
  P3 cosmetic. Release needs zero open P1/P2.

## 1. Traceability matrix

### 1.1 Test cases

#### Install and lifecycle (US8, G0, G5)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-INST-01 | manifest schema, entry points, no symlinks, id not reserved | A `omarchy plugin validate .` (in `scripts/check.sh`) | exit 0 |
| TC-INST-02 | git clone install (no symlink), validate on the clone | M 5.2 | `omarchy plugin validate ~/.config/omarchy/plugins/io.github.rmcdavid.iptv` exit 0 |
| TC-INST-03 | rescan + enable | M 5.2 | `omarchy plugin list --json` shows `enabled: true`, kinds `bar-widget,overlay,service`; `shell.json` gains exactly `{"id":"io.github.rmcdavid.iptv"}` at the end of `bar.layout.right`; `plugins[]` unchanged |
| TC-INST-04 | console clean on load | M 5.2, 5.9 | no `WARN`/`ERROR` lines mentioning `io.github.rmcdavid.iptv`, `Guide.qml`, `Service.qml`, `BarWidget.qml` or `omarchy-iptv` in the journal after enable |
| TC-INST-05 | disable removes the widget and its settings; re-enable starts clean | M 5.10 (before remove) | after `omarchy plugin disable`, the bar entry (and inline `playlistUrl`) is gone from shell.json, widget gone, `omarchy-shell shell toggle io.github.rmcdavid.iptv` is a no-op, mpv (attached Process) exits; after `enable` the guide shows the not-configured state. Expected host behaviour; README must say settings are lost on disable **[Amended 2026-10-11, D-SINK-19: the entry (and its `sourceKey` mirror) is gone from shell.json after disable, but `state.json` still names the active source, so after `enable` the plugin reads as CONFIGURED on the same playlist and rewrites the entry with `sourceKey`; only the other settings on the entry are lost. Derived from `Model.adoptActiveSource` step 2 over a first reconcile with no URL; UNVERIFIED live. The README says so.]** |
| TC-INST-06 | `omarchy plugin remove --yes` leaves only cache, state, runtime dirs | M 5.10 | `find ~ -path '*omarchy-iptv*'` lists only `~/.cache/omarchy-iptv`, `~/.local/state/omarchy-iptv`, `/run/user/1000/omarchy-iptv`; shell.json identical to the pre-install snapshot |
| TC-INST-07 | nothing written inside the plugin directory at runtime | M 5.7 | `find <plugindir> -newer <plugindir>/manifest.json -not -path '*/.git/*'` prints nothing after a full session |
| TC-INST-08 | `omarchy restart shell` round trip | M 5.4 US5 step 6 | widget back, settings intact, favorites and recents intact, **mpv keeps playing: same pid, same window** (R10 withdrawn by M2-02; observed PLY-RST-01; corrected 2026-09-25, D-QA-19) |
| TC-INST-09 | `keepLoaded` survives `rescanPlugins` | M 5.4 US3 step 7 | `omarchy-shell shell rescanPlugins` while playing: mpv keeps playing, bar label unchanged |
| TC-INST-10 | README uninstall section matches reality | M 5.10 | README commands produce TC-INST-06 result verbatim |

#### Configuration (US1, R2, section 6 of ARCHITECTURE.md)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-CFG-01 | `omarchy bar set ... playlistUrl <url>` fetches without restart | M 5.3, 5.4 US1 | helper runs within ~1 s (journal shows one run, 300 ms debounce); bar tooltip `IPTV - click to open the guide`; guide footer `1,475 channels - updated HH:MM` (count from the live list, thousands separator) **[Amended 2026-10-11, D-SINK-19: and afterwards `jq` of the entry in shell.json shows `sourceKey` = the record's key and NO `playlistUrl`; `state.json` `activeKey` = that key; the file is 0600. The same holds when the value was set while the shell was down (SRC-MIG-14 in QA-SOURCES.md, observed live under cage on lane-key-s2: key-scenario C1-C5); at the first build it was discarded and erased instead, and on the round-2 tree it was lost to the start-up reload (D-SRC-15).]** **[OVERTURNED 2026-10-13, D-SINK-19 round 11 (R21; the owner dropped the route): after the migration `omarchy bar set ... playlistUrl` is refused, so this row is now "adding a source in the guide fetches without restart": first-run form or Sources `a`, paste the URL, `Enter`; the same expectations, and the entry carries `sourceKey` and no URL. The command itself is TC-CFG-14; a URL an older version kept on the entry is TC-CFG-15.]** |
| TC-CFG-02 | HTTP 404 with no cache | M 5.4 US1 step 4 | empty state `Playlist failed to load` / `HTTP 404 Not Found from iptv-org.github.io - check playlistUrl`; hint `r reload - Esc close`; bar glyph U+F0503, tooltip `IPTV - playlist error, open the guide`; notification `Playlist error` / `Could not fetch the playlist (HTTP 404 Not Found). Open the guide for details.` **[Amended 2026-10-13, D-SINK-19 round 12 (R22c): the empty state's line is `HTTP 404 Not Found from iptv-org.github.io - check the source in Sources` (`Guide.qml` `errorCheck` on lane-key-n1); `check playlistUrl` is a FAIL. Seen with the old text on screen by the round-11 live lens on lane-key-m2, whose footer read `r retry - o sources - Esc close` (separators `Model.SEP`). Automated: key-scenario B8 reads the drawn empty state (`kind:error sources:yes retired:no`) and `tests/test_shipped_copy.py` searches every shipped string literal.]** |
| TC-CFG-03 | unresolvable host | M 5.4 US1 step 5 | reason `Could not resolve host` |
| TC-CFG-04 | unsupported source scheme | A `python3 -m unittest discover -s tests` (`tests/test_helper.py::test_refuses_unsupported_scheme`); M optional | code `unsupported_scheme`, guide renders the message |
| TC-CFG-05 | absolute path and `file://` sources | A `tests/test_playlist.py::SourceTest`, `tests/test_helper.py`; M 5.4 US7 (local server) | both load; `sourceHost` = `local file` |
| TC-CFG-06 | `epgUrl` set later, plain and `.gz` | M 5.4 US6 | `epg-now.json` appears; rows get Now/Next; unmatched ids show no EPG line and no error |
| TC-CFG-07 | `refreshMinutes` typing and clamps (R2) | A `node tests/Model.test.js` (`clampInt`); M 5.4 US7 step 1 | `omarchy bar set ... refreshMinutes 30` (string) is parsed; `--json 5` clamps to 15; `--json 99999` to 1440; timer re-arms |
| TC-CFG-08 | `mpvArgs` tokens | A `Model.test.js` (`splitMpvArgs`); M 5.4 US3 step 8 | `--profile=fast --hwdec=auto-safe` appear in `ps -o args=` of mpv; `--input-ipc-server=/tmp/x --title=X --no-idle` are dropped with one console warning naming them |
| TC-CFG-09 | `showChannelName` false | M 5.4 US4 step 7 | glyph only while playing; tooltip keeps the name |
| TC-CFG-10 | `barLabelMaxWidth` 60 vs 600 (R7) | M 5.4 US4 step 8 | label elided at `Style.space(60)`, then almost never elided at 600 |
| TC-CFG-11 | `maxRecents` 3 | M 5.4 US5 step 5 | Recent shows the 3 newest |
| TC-CFG-12 | settings change while the guide is open | M 5.4 US1 step 6 | guide re-renders without restart |
| TC-CFG-13 | credentials never rendered (R12) | see SEC-07 | no URL beyond scheme+host in guide, tooltip, notification, journal |
| TC-CFG-14 | `omarchy bar set ... playlistUrl` / `epgUrl` after the migration is REFUSED (D-SINK-19 R21b, 2026-10-13) | A node `R21e (lag host)` / `(echo host) after the marker, a CLI ...`; H key-scenario X1-X6; M 5.4 US1 step 8 | nothing added, the active source and its guide URL unchanged, one notification `Bar setting ignored` / `<setting> is no longer read from the bar settings and was removed. Add or switch sources in the guide's Sources screen.` (replace id 74016; the same sentence once on the console); `jq` of the entry shows no `playlistUrl`/`epgUrl` after the plugin's next write; the same value set again is not reported again; `grep -c '://'` over the journal and the notification text 0 |
| TC-CFG-15 | a 0.13.x command-line configuration is moved into Sources once (D-SINK-19 R21a, 2026-10-13) | A node `R21e (lag host)` / `(echo host) migration, ...` (one source, two, CLI-only, no-source `epgUrl`, failed write, TERM, downgrade); H key-scenario G1-G5, F, H; M 5.4 US1 step 7 | first start over an entry carrying `playlistUrl` (and `epgUrl`): that playlist is a source and active, the guide URL on it, `state.json` carries `"entryMigrated": true` and `activeKey`, and the entry carries `sourceKey` and no URL once that write has landed; nothing is reported. A guide URL with no source to attach it to: one `Bar setting removed` notification, nothing kept. State directory unwritable at that start: the URL stays on the entry, the next start migrates again |
| TC-CFG-16 | a `state.json` that exists but cannot be read, or does not parse, is never written (D-SINK-19 R22a, 2026-10-13) | A node `R22a (lag host, ...)` / `(echo host, ...)` at a migrated and at a 0.13.x-shaped start and mid-session, `R22b (...)`, the `R22a:` model units; python `StateNeverWrittenUnreadTest` (`tests/test_state.py`); H key-scenario B1-B7; M 5.4 US5 step 7 | over a file that does not parse: the file byte for byte unchanged after the start, an add or a switch and a restart; one critical notification `Saved sources not loaded` naming the file and saying what to do, no `://`; an add or switch refused with `state.json could not be read - nothing is saved until it can be`; the bar entry unchanged. Over a 0000 file or a 0000 state directory left while the shell was down: NO notification, every source and favourite there after the start (the helper's init restores 0600 / 0700 and the start reads the file). Putting a good file back lifts the mode without a restart (B7) [round 15, D-SRC-35: for a regular `state.json`; a symlink whose target went missing mid-session is not seen coming back, and the session stays in the mode until a restart] [round 16, R26a: it is seen now, at the next save or the SECOND source call -- the first is refused and asks for one reload (TC-CFG-30, key-scenario B29)]. `UX-SOURCES.md` 5.10 has the copy for each reason **[Round 13, 2026-10-13 (R23a, R23e): a SECOND episode in the same session is told again, and a favourite refused in it is refused and told (node `R23a (...)`, key-scenario B9 `told:1/2`); and the guide at a no-write start draws `Saved sources not loaded` over the notification's own body, not the first-run form (TC-CFG-17). ~~The mode beginning mid-session AFTER the session's first own save is UNVERIFIED: the measurements disagree~~ (corrected 2026-10-14, D-DOC-8: the variable was whether the state DIRECTORY existed at the first load, and the first session after a fresh install never noticed a damage until R24c re-armed it; that session after an own save is observed by key-scenario B16 (TC-CFG-22), an existing directory before an own save by B5-B7 and B9, and an existing directory AFTER an own save by the committed FileView spike and the round-13 live lens's rig only) [round 15, R25d: and by key-scenario B21 (TC-CFG-28)]]** |
| TC-CFG-17 | the no-write mode has its own guide surface, and every refusal in it says the no-write reason (D-SINK-19 R23e, R23f, 2026-10-13) | A node `R23e: guideSurface ...`, `R23e: firstRunAllowed ...`, `R23e: the Esc / o return from Sources ...`, `R23f: refusalMessage ...`, the R16 structural pin through `Model.refusalMessage`; H key-scenario B11, B12, B13; M 5.4 US5 step 7 | at a no-write start: the alert glyph, `Saved sources not loaded` and the notification's body (`Model.stateUnreadableNotice` for the reason and path), no form and no editable field (B11 `kind:stateUnreadable form:false editable:0 shown:true title:notice prose:notice sent:1`), footer `Esc close`, no `r retry`. The logo toggle in Sources answers `state.json could not be read - nothing is saved until it can be`, never `try omarchy bar set` (B12 `says:no-write advice:none writes:0`). A fresh install still draws the first-run form, and the harness reads ITS copy (B13 `prose:Paste or type your M3U URL or path, then press Enter`). Red on lane-key-n2: B11 `kind:unconfigured form:true`, B12 `advice:bar-set`, B13 the hidden empty state's prose. The pixels are UNVERIFIED on a display |
| TC-CFG-18 | a directory, a FIFO or a socket at the `state.json` path never blocks a start and is never changed (D-SINK-19 R23b, R23d, 2026-10-13) | A python `StateNeverBlocksTest` (`tests/test_state.py`, ten tests, the real helper as a subprocess under a 20 s timeout); H key-scenario B14 | `state init` answers `found: other` at once and chmods nothing that is not a regular file (a directory keeps its mode; round 12 saw one made 0600); every other `state` verb exits 1 with `state.json is not a regular file; nothing was written`; the start enters the no-write mode with `is not a regular file` and leaves no helper behind (B14 `blocked:not-a-file found:present told:1 left:none fifo:600`). Red on lane-key-n2: 9 of 10 python tests (timeouts and chmods), B14 `blocked: found: told:0 left:<pid>` |
| TC-CFG-19 | the start-up `state init` is bounded (D-SINK-19 R23c, 2026-10-13) | A node `R23c: stateInitFound answers "timeout" ...`, `R23c: stateUnreadableNotice("init-timeout") ...`, `R23c (<mode> host): startStateInit arms the init's watchdog ...`, `... the init never answers over <fault> ...`, `... an init that times out AFTER the state loaded leaves the session as it was ...`; H key-scenario B10 | an init that has not answered after 15 s is sent TERM, then KILL 2 s later, is reaped, and the held load blocks with reason `init-timeout`, told once with `could not be checked: the start-up check did not answer and was stopped`; no process is left running the init (B10 `blocked:init-timeout found:timeout helper:yes left:none told:1 stopped:1 file:same watchdog:1`). Red on lane-key-n2: B10 `blocked: found: helper:no(<pid>) left:<pid> told:0`. The 15 s bound is 8.5x the slowest of 80 runs measured on this machine (lane A, 2026-10-13) |
| TC-CFG-20 | another program's write that arrives while the session holds an unsaved change is MERGED, never ignored and never applied blind (D-SINK-19 R24a, D-SRC-22, 2026-10-14) | A node `R24a mergeForeignState: <case>` over the 34 cases of `tests/fixtures/state-merge.json`, `R24a: the fixture covers every field rule ...`, `R24a: over EVERY fixture case, the merge with ours == base IS theirs and the merge with theirs == base IS ours ...`, `R24a / R24c: sameState compares what a reader of the file sees ...`, `R24a: a conflict's console line names the field and the source key, never a URL or a value`, and `R24a (...)` through `tests/service-harness.js` in 16 modes (parked, in flight, failed and a conflict; both hosts; both own-echo modes) | the round-13 data-loss lens's sequence -- a state write fails, an in-app favourite, the condition clears, a hand-run `omarchy-iptv state source add`, another favourite -- ends with BOTH the in-app favourites AND the helper's source in `state.json`; where both sides changed one source or one value the other program's is kept and the console carries `omarchy-iptv: state.json was changed by another program while a change made here was not yet saved; kept the other program's version of ...` (round 15, D-SRC-36: `version of` added) naming the field (and a source's key and field names), never `://`. With nothing held, the foreign file is applied whole, as before. Red on dev: the whole node suite reads 85 failures of 2,459, the R24a share being all 34 cases, the identity, sameState and conflict-line checks and the 16 harness modes; a blind apply or an ignore in place of the merge, 16 each. No live segment (the ruling asked for the table and the harness) [round 15, R25d: key-scenario B19 is now its live segment, and two decisions that survived these checks are pinned (TC-CFG-28); past a cap the merge drops and tells (TC-CFG-26)] |
| TC-CFG-21 | a symbolic link at `state.json` is followed when it leads to a regular file and refused otherwise; a file where the state folder should be is named (D-SINK-19 R24b, D-SRC-23, D-SRC-26, 2026-10-14) | A python `StateSymlinkTest` and `test_every_verb_refuses_a_file_where_the_state_directory_should_be`, `test_init_over_a_dangling_symlink_reports_link_and_creates_nothing` (`tests/test_state.py`, the real helper as a subprocess under a timeout); node `R24b: stateInitFound ...`, `R24b: stateLoadDecision ...`, `R24b: the link sentence names the file and the link, the not-a-dir sentence names the FOLDER's path, ...`, the `R24b (...)` harness pins; the spike `scripts/dev-harness/spikes/filewatch/measure.sh <helper> r24` (sequences V, W, X) | over a link to a regular file every writing `state` verb writes THROUGH it (`ls -l` still shows the link; the target holds the change) and `show` reads through it; over a dangling link, a link into a missing folder, or a link to a directory or a FIFO, every verb exits 1 with `state.json is a symbolic link whose target is missing; nothing was written` (or `... is not a regular file ...`) and the link is untouched, `state init` answers `found: link`, and a shell start blocks with `... is a symbolic link whose target is missing or is not a regular file ... Restore the file it points to, or move the link aside ...`; with a regular file at `~/.local/state/omarchy-iptv`, `state init` answers `found: not-a-dir` with exit 0 and no traceback, the verbs answer `the state folder is not a folder ...`, and the start blocks with `<folder> is not a folder ...`. Red on dev: 9 of 14 new or changed python tests (5 are controls dev passes). No key-scenario segment drives these faults. [Round 15, R25e (D-SRC-29): a running shell notices a write THROUGH the link (the helper's, in place, a `cp` onto the path, a rename onto the target's own path) and NOT a tool that replaces the link or puts a file over it at the state path (`mv`, `sed -i`, `rm` + `cp`, `ln -sfn`), after which it sees nothing more that session; measured by the round-14 lenses' rigs (session scratch), stated in the README, not fixed. Manual check: with the shell running over a linked `state.json`, `mv` an edited copy onto the link's path, then add a favourite in the guide -- the edit is gone from the target (expected, documented); `cp` the same copy onto the path instead -- the edit is kept] [Round 16, R26a (D-SRC-29 closed): the replacement is still unseen when it happens and is seen at the next save, which reads the file first and merges, so the manual check's expectation is REVERSED: after the `mv` and the favourite, `state.json` holds the edit AND the favourite. key-scenario B23-B26 observe it live (TC-CFG-30); the `mv` case is no longer a documented loss] |
| TC-CFG-22 | the first session after a fresh install sees external changes to `state.json` (D-SINK-19 R24c, D-SRC-19, D-DOC-8, 2026-10-14) | A node `R24c (...)` (the dir-absent first session and its identity, 8); H key-scenario B16; the spike `measure.sh <helper> r24` (sequences Q-U) | with the state home present and `omarchy-iptv/` absent at the start, a hand-run `omarchy-iptv state source add` during that first session appears in Sources, survives the next in-app add's save, and garbage then written in place blocks the session as `unparsed` and is told once (B16 `first-load:1 found:absent helper:0 seen:1 add:true file:C,D blocked:unparsed told:1`). Red on dev: B16 `seen:0 file:D blocked: told:0` (the round-13 live lens's reading), 113 / 3 over `--baseline dev` |
| TC-CFG-23 | one bound over the whole start-up check, the KILL observed, and an init that ends itself (D-SINK-19 R24d, R24g, D-SRC-24, D-SRC-25, F-HARNESS-24, 2026-10-14) | A node `R24d (...)` (mkdir inside the bound, 2), `R24g (...)` (a TERM-ignoring init and mkdir, 2 each); python `StateInitDeadlineTest`; H key-scenario B17, B18 | the watchdog arms when `mkdir` starts; an init that ignores TERM is KILLed 2 s later and reaped, the load blocks as `init-timeout`, told once, file untouched (B17 `blocked:init-timeout helper:yes left:none told:1 file:same watchdog:1 killed:1`); a shell stopped 5 s into a held init leaves it alive, reparented to `systemd --user`, and it ends by its own `SIGALRM` 30 s after it started (B18 `at-stop:alive after-deadline:gone left:none`; alone, `Alarm clock`, rc 142, after 30.2 s). Red: B18 on dev (`after-deadline:alive(<pid>)`); B17 only on a tree with the KILL deleted (`spikes/key-mutations/r24g-no-kill.patch`, 115 / 1, `blocked: helper:no(<pid>) left:<pid> told:0`; node 4 of 2,459). A process in uninterruptible sleep on a hung filesystem is reached by no bound; a hung `mkdir` was not reproduced (no FUSE rig) |
| TC-CFG-24 | in the no-write mode nothing the service starts writes `state.json`, and Sources draws no fresh install (D-SINK-19 R24e, R24f, D-SRC-27, D-SRC-28, 2026-10-14) | A node `R24e (...)` (2), `R24f: sourcesRowCount / sourcesRowKind ...`, `R24f: sourcesHeaderRight ...`, `R24f: sourcesAddAllowed ...`, `R24f: footerHints in Sources ...`; H key-scenario B15 | the playlist fetch's argv carries no `--state-dir` while the mode holds; in Sources the header's right slot reads `Saved sources not loaded` (never `No sources`), there are no `Add source` / `Add Xtream login` rows, `a` and `c` open no form and the footer says `state.json could not be read - nothing is saved until it can be`, the footer hints are `Esc back` with no source row, and no editable field exists (B15 `mode:sources header:notice rows:0 addhint:no after-a:sources says:no-write editable:0`). Red on dev: B15 `header:[No sources] rows:2 after-a:sourceEdit says:other`. A fetch already running when the mode begins keeps its argv (open) |
| TC-CFG-25 | a backup put back wins, even a copy of the plugin's own file (D-SINK-19 R25a, D-SRC-30, 2026-10-14) | A node `R25a (<host>, <echo>): FAV BAK DEL RSTB FAV -- ...`, `... FAV BAK UNFAV RSTB FAV ...`, `... controls ...`, `... a coalesced burst of three saves ...` (both hosts, both echo modes); H key-scenario B20; the spike `scripts/dev-harness/spikes/filewatch/measure.sh <helper> r25` | a copy of `state.json` taken after an in-app change's save landed, put back with `cp` after a later in-app remove landed, is APPLIED (reason `file-newer`, never `own-write`), the next in-app save keeps it, and a restart stands on it (B20 `restored:2 records:2 label:after-restore restart:2`); the echo of a save that just landed changes nothing (`unchanged`); a coalesced burst's mid-burst echo is still own. Red on dev: B20 `restored:1 records:1 label:after-restore restart:1`, 118 / 2 over `--baseline dev`; node 16 R25a pins (and `r25a-keep-landed.patch` 16, `r25a-clear-every-saved.patch` 13 / 11). Stated, not a defect: a copy equal to what the file ALREADY holds while an in-app change waits to be saved has no effect |
| TC-CFG-26 | a merge past a cap drops the in-app additions and SAYS so (D-SINK-19 R25b, D-SRC-31, 2026-10-14) | A node `R25b: mergeForeignState at every cap -- ...`, `R25b: mergeDropLines ...; mergeDropNotice ...`, `R25b (<tag>): at 49 sources, an in-app add whose save FAILED, then a hand-run state source add ...`, `R25b (<tag>): at 19 saved searches, an in-app save of a search IN FLIGHT ...` | the other program's 50th source (or 20th saved search, 200th hidden group) keeps its place; the in-app addition past it is dropped, ONE notification `Not every change was kept` (replace id 74018) naming the count and the limit, one journal line per dropped element naming a source by its key; `grep -c '://'` over both 0, no label, query or group name. Red on dev: the R25b pins (2 model, 8 service); `r25b-silent-drop.patch` 8. Not driven live. Outside the merge and still silent: an in-app add whose probe runs when a foreign write takes the 50th place (raised to the lead) |
| TC-CFG-27 | a symbolic link at the state FOLDER is followed or refused, and every folder the helper makes answers in a sentence (D-SINK-19 R25c, D-SRC-32, D-SRC-34, 2026-10-14) | A python `StateFolderLinkTest` (5), `FolderLinkSiblingsTest` (1) in `tests/test_state.py`, the logo folder link in `tests/test_logos.py`, each the real helper as a subprocess under a timeout; node `R25c: ...`, `R25c (<tag>): a start over a state FOLDER link that leads nowhere ...`; the spike `scripts/dev-harness/spikes/folder-link/measure.py <helper>` | over `~/.local/state/omarchy-iptv` linked to a folder: every verb follows it, `state init` and a writing verb make the target 0700, the link stays a link; linked to nothing (or to a file, or a link above it): `state init` `found: folder-link` exit 0 nothing created, every other verb exit 1 `the state folder is a symbolic link whose target is missing or is not a folder; nothing was written` (`show` and `source list` included), the start blocks with `<folder> is a symbolic link whose target is missing or is not a folder (or a folder above it is). ... Restore the folder it points to, or move the link aside ...`; a cache, runtime or logo folder in that shape `folder_unusable`, exit 1, no traceback; a `state.json` link into a 0500 folder `state.json is a symbolic link into a folder that cannot be written (Permission denied); nothing was written`, the folder still 0500. Red on dev: `test_state` 13 failures and 5 errors, `test_logos` 1 error, node 5. No key-scenario segment drives a folder link; whether the watch notices changes through a folder link is unmeasured |
| TC-CFG-28 | the merge is observed: a5 pinned (a7 UNVERIFIED since F-HARNESS-31, below), and live segments for R24a and for the existing-folder session damaged after an own save (D-SINK-19 R25d, F-HARNESS-26, 2026-10-14) | A node `R25d (<tag>): a5 -- ...`, `R25d / F-HARNESS-31 (<tag>): a7, the same-instant residual -- ...` (both hosts, both echo modes); H key-scenario B19, B21 | B19: a failed state write holds an in-app label change, two hand edits in place add and then remove a favourite, a hand-run helper write lands, a second in-app change follows -- both in-app changes and the helper's favourite are in the file, the removed favourite stays removed, and a restart stands on it (`held:true edits:true/true helper:0 merged:3 labels:A=in-app-two,C=in-app-one favs:t:helper.uk restart:in-app-one,in-app-two/t:helper.uk`); B21: an in-app save lands in an existing-folder session, garbage written in place after it is noticed and told once (`blocked:unparsed told:1 file:garbage{`). Green on dev (the behaviour was there, the checks were not); red by mutation: `r25d-a5-base-not-moved.patch` node 4 / 4 on dev and 8 / 8 on this branch, live 119 / 1 (B19 `merged:2 ... favs:t:helper.uk,t:h3.uk`); `r25d-a7-no-inflight-half.patch` node 8 / 8 until F-HARNESS-31, and 0 of 2,565 since: the in-flight half of `behind` was reached only by a foreign load delivered during our write, which the measured FileView did not deliver for a reload asked during our write (30 of 30; a reload asked just before our `setText` and delivered after it is unmeasured), so a7 is UNVERIFIED -- kept as defence, observed by nothing (F-HARNESS-33); `r25d-no-reload-on-change.patch` live 110 / 10 (B21 `blocked: told:0`) |
| TC-CFG-29 | in a MID-session block the Sources header says saving has stopped (D-SINK-19 D-SRC-38, 2026-10-14) | A node `D-SRC-38: sourcesHeaderRight / stateBlockedHeader -- ...`, `D-SRC-38 (structural): the guide hands the header the service's stateLoaded ...`; H key-scenario B22 | after a state loaded and the file was then damaged, Sources lists the session's rows under `Saving has stopped` (B22 `header:Saving has stopped rows:2`); at a no-write START it is still `Saved sources not loaded` (B15). Red on dev: B22 `header:Saved sources not loaded rows:2`. The notification and the guide body keep the notice's title mid-session (a copy question raised to the lead). The pixels are UNVERIFIED on a display |
| TC-CFG-30 | every state save reads `state.json` first: a replaced or re-pointed link, a re-pointed folder link, a link target put back, and a re-pointed folder with nothing in it (D-SINK-19 R26a, D-SRC-29, D-SRC-40, D-SINK-21, D-SRC-35, 2026-10-16) | A node `R26a / R26b: Model.stateSavePlan -- ...`, `R26a (D-SRC-35): Model.stateBlockRecheck -- ...`, and through `tests/service-harness.js` on both hosts and both echo modes `R26a (<tag>): D-SRC-29 -- ...`, `... D-SRC-29 / D-SRC-40 -- ...`, `... D-SINK-21 -- ...`, `... D-SINK-21's file-link sibling -- ...`, `... D-SRC-35 -- ...`, `R26a / R26e (<tag>): D-SRC-35 through a SOURCE verb -- ...`, `R26a (<tag>): the read is BOUNDED -- ...`, `R26a (<tag>): the read's bound is 2 s, from the Timer the tree declares -- ...` (lane-clean-f1: `h.elapse` runs the declared Timer; red on `r26a-watchdog-20ms.patch` and `r26a-watchdog-no-interval.patch`, 4 of 2,565 each, in both echo modes; no live check, because a live read answers in milliseconds and a short bound never fires there), `... the read is SKIPPED while one of our writes is in flight ...`, `... a foreign write that ARRIVES while a save waits for its read IS that read ...`, `R26a (<tag>): key-scenario D3 / W3 stay discriminating -- ...`; H key-scenario B23-B29 | B23-B25 (`mv`, `sed -i`, `rm` + `cp` over a linked `state.json`, a hand edit, then an in-app label edit): `edit:true disk:A=hand-<kind>,C=app-<kind>,favs=t:seed.uk+t:hand.uk memory:A=hand-<kind>,C=app-<kind> old:A=seed,C=c-seven,favs=t:seed.uk`; B26 (`ln -sfn` to another state): `new:A=t2-own,C=app-ln,favs=t:t2.uk old:A=seed,...`; B27 (the folder link re-pointed at another state): `new:A=f2-own,C=app-fl,favs=t:f2.uk`; B28 (at an EMPTY folder): `edit:true created:none holds:[] blocked:absent told:1 next:state_unreadable`; B29 (a link target moved away and back): `away:absent told:1 first:state_unreadable lifted:[] second:true`. Red on dev 1c88877 (`--baseline`, 120 / 9): B23-B27 lose the hand edit (`disk:A=seed`), B28 `created:644 holds:[state.json] blocked: told:0` (D-SINK-21), B29 `lifted:[absent] second:false`; node 64 failures of 2,561 with the tip's tests over dev's `Service.qml`. Red by mutation: `r26a-no-read.patch` live 122 / 7 (B23-B28, B31), node 36 (40 since the 2 s bound's pin joined it); `r26a-no-verb-recheck.patch` live 128 / 1 (B29), node 4. The file-link twin of B28 (a `state.json` link re-pointed at a file that does not exist yet) is node only. FRESH -- a replacement with no save after it -- is unseen until the next save or a restart, stated, not a defect (TC-CFG-32) |
| TC-CFG-31 | no write is issued from inside one of `stateFile`'s handlers, so the merge's save is reported; and the double is no more forgiving than the FileView in the facts it models -- including, since F-HARNESS-31, that the reload a foreign change delivered through the watch (`h.foreign`) raises while one of our writes is in flight delivers nothing (the boot double's init-chmod reload in the exit-first order is still delivered during the migration's write, carrying the base text only and changing no pin: F-HARNESS-31's remainder), so that change is lost to our rename (no plugin-side lock exists against a second process) (D-SINK-19 R26b, R26c, D-SRC-46, F-HARNESS-29, F-HARNESS-31, 2026-10-16) | A node `R26b (structural): the one setText is issued only from a turn of its own -- ...`, and on both hosts and both echo modes `R26b (<tag>): D-SRC-46 -- ...`, `R26b (<tag>): no setText is issued inside any of stateFile's handlers -- ...`, `R26c (<tag>): the double creates a missing file as 0666 & ~umask and keeps an existing file's mode -- ...`, and the four F-HARNESS-31 re-levels `R24a / F-HARNESS-31 (<tag>): IN FLIGHT, the same-instant residual -- ...`, `R25d / F-HARNESS-31 (<tag>): a7, the same-instant residual -- ...`, `R25b / F-HARNESS-31 (<tag>): at 19 saved searches ... in the same instant -- ...` and the census's in-flight leg; H key-scenario B30 | B30 (a save failed and held, the folder given back, a hand-run `state favorite add`): `edit:true held:true helper:0 inFlight:0 saveFailed:false disk:A=seed,C=app-fail,favs=t:seed.uk+t:helper.uk`; the census `counts:[0, 0, 0]` setText calls inside a handler over an unmigrated start, a fresh install and a session with a switch and two foreign writes; the double's modes `["644", "600", "664", "640"]` at umask 022, 077, 002 and over an existing 0640 file. Red on dev: B30 `inFlight:1 saveFailed:true` with the merge on disk. Red by mutation: `r26b-no-defer.patch` live 128 / 1 (B30), node 23 / 21 (echo load / none), 19 / 17 since F-HARNESS-31. Rule 10 shown the other way: dev's own suite with ONLY the new double swapped in reads 2,502 / 12 -- eight R22a unmigrated starts and four R24a IN FLIGHT, which the old double had been forgiving. F-HARNESS-31 (lane-clean-f1): the same-instant loss -- `dropped:1`, the helper's record, favourite or saved search NOT on disk or in memory, ours kept, nothing told, nothing in flight; the census `counts:[0, 0, 0]` with `file:["t:bbc1.uk","t:helper.uk","t:x.uk","t:y.uk"]`. Seen red both ways: the old wants on the drop, 16 of 2,561 in each own-echo mode (the data-loss lens's measurement, reproduced); the new wants on the old double, 16 of 2,561 in each |
| TC-CFG-32 | no periodic reload: an idle shell reads `state.json` not once, and one save reads it once (D-SINK-19 R26d, 2026-10-16) | A node `R26d (<tag>): FRESH, stated -- ...`; H key-scenario B31 | B31: `idle-loads:+0 idle-reads:+0 edit:true save-reads:+1` over 30 s idle and then one in-app save. Its save half is red on dev (`idle-reads:NOFIELD`, no read before a save) and with `r26a-no-read.patch`; its idle half is green on every tree before R26 (none reloads while idle) and is seen red only through `r26d-periodic-reload.patch` (126 / 3, B31 `idle-loads:+15`). No node pin observes the idle half: the harness runs no Timer |
| TC-CFG-33 | no write without a read: a save asked while our write is in flight waits for it and then reads; a read that does not answer is asked once more and then stops saving with reason `read-timeout`, never a blind write (D-SINK-19 R27a, D-SINK-22, 2026-10-20) **[R28a, the same day: the window (c) half is withdrawn -- a read that does not answer keeps the change held and is asked again, never a block (TC-CFG-37); window (a)'s half and the write wait's bound stand]** **[R29a, the same day: R28a's answer is withdrawn too, and window (c) is 0.14.2's again -- no load in 2 s and the save is written without the read, counted and logged (TC-CFG-37 as re-written). Window (a)'s half stands with the ruling's proviso: the write wait releases at 2 s to a read with R26a's own 2 s bound, so a write never reported lets the held save be written without its read 4 s after it was asked, never blocked and never held longer. The `window c` pins this row names are gone; the bound is pinned by `R26a / R29a (<tag>): the read is BOUNDED ...`, `... the read's bound is 2 s ...` and `R27a / R29a (<tag>): the write wait is BOUNDED at 2 s ...`]** | A node `R26a / R26b: Model.stateSavePlan -- ...` (the `wait` answer), and through `tests/service-harness.js` on both hosts and both echo modes `R27a (<tag>): window a -- ...`, `... window a, D-SINK-22 -- ...` (the folder link re-pointed at an EMPTY folder as the first write lands), `... the write wait is BOUNDED at 2 s ...`, `... window c -- a read that never answers ...`, `... window c -- the read-timeout mode is lifted by a later read that ANSWERS ...`, `R27a / R26e (<tag>): window c through a SOURCE verb -- ...`, `R26a / R27a (<tag>): the read is BOUNDED ...` and `... the read's bound is 2 s ...`; H key-scenario B33 | Window a: no reload asked and no write issued while the first write is out; once it lands the held save reads, then writes; over an empty folder no file is created, `absent`, told once (6f1d176: `created:true mode:644 blocked: told:0`). The wait releases at 2,000 ms, not 1,999, to its read, never to a write. Window c: a second read at 2 s, `read-timeout` at 4 s, told once as `Saving has stopped`, the file named, no URL, nothing written, and over an empty folder no file created (6f1d176: `created:true mode:644`); a later answering read lifts it and both changes are written. B33 (`skipped +0`, the wait counted, the second edit on disk) is red on 6f1d176 only through `waited:NOFIELD` -- window (a) does not open from outside the shell on this machine -- and on behaviour through `r27a-wait-never-released.patch` (`--tree`: 134 / 1 by the summary line, B33). Window (b), a re-point between the read's load and its write, is stated and has no check. No live segment stalls a read for 2 s (no way without FUSE or root) |
| TC-CFG-34 | the no-write notice is one Model family: titled `Saving has stopped` for a block that begins mid-session and `Saved sources not loaded` at a start, in the notification, the journal and the guide; every body says changes made now `are not saved until the file can be read again`; the missing-file advice names the link first (D-SINK-19 R27e, D-SRC-42, D-SRC-50, D-SRC-51, 2026-10-20) **[R28e, the same day: the second sentence is now `Sources, favorites and settings changed now are not kept.` at a start and, mid-session, `Favorites and other changes made now are held in this session only: the next such change made here saves them if it finds the file again, but they are dropped if the file comes back by itself first, if a source change is what finds it, or if the shell is stopped.`; each way back is pinned to it]** | A node `R27e: the notice fixture covers every reason ...`, `R27e: every body is the fixture's sentence, word for word ...`, `R27e (D-SRC-51): ...`, `R27e (D-SRC-50): ...`, `R27e (D-SRC-42): the TITLE -- ...`, `R27e (structural): ...`, and through the harness `R27e (<tag>): a block at the START is told as ...` and `R27e / rule 15 (<tag>): the bar-entry refusal's journal line ...`; `tests/fixtures/state-notices.json`; H key-scenario B32 | Every sentence of `tests/fixtures/state-notices.json` is the model's for its reason, both ways. B32: `saving-stopped:1 not-loaded:0 body:1` for a mid-session block (6f1d176: `saving-stopped:0 not-loaded:1 body:0`). M: in a nested cage, re-point a folder link at an empty folder and make one change; the card reads `Saving has stopped` and its advice starts `If it is a symbolic link, point it back`. **[R28e: the fixture holds `bodies.start` (ten reasons) and `bodies.midSession` (the five load kinds); B32's body token reads the mid-session sentence and is red on lane-sweep-c1 and 6f1d176 (`body:0`). The ways back, each through `Service.qml` on both hosts and both echo modes (`R28e (<tag>): the ways back out of a MID-session block ...`, `... at a START no way back keeps ...`): the next favourite finds the file and saves the block's change; the file put back by itself, a source change, or a restart drops it; at a start none keeps it. Those pins are green on c1 and 6f1d176 (the behaviour predates R28); the sentence they bind to is red under a one-sentence mutation (2 per echo mode)]** |
| TC-CFG-35 | the cap is one decision and nothing passes it: the probe commit re-checks it against the state as it is when the probe ends and refuses `too_many`, told; the one-time migration at the cap does not run and never evicts, the entry keeps its URL, told once, and the next reconcile after a removal migrates (D-SINK-19 R27c, R27d, D-SRC-41, D-SRC-44, 2026-10-20) | A node `R27d: Model.sourcesFull -- ...`, `R27d: reconcileSources at the cap -- ...` (2), `R27d: adoptActiveSource MIGRATING at the cap ...`, `R27d: reconcileAction -- heldFull ...`, `R27d: the notice -- ...`, and through the harness `R27c (<tag>): D-SRC-41 -- ...` with its control at 48, `R27d (<tag>): D-SRC-44 -- ...` (3); H key-scenario B35, B36, B37 | R27c: at 49 sources with a hand-run add taking the 50th mid-probe, the result `[false, "Sources is full (50) · remove one first"]`, 50 on disk, the probe's directory removed, a restart drops nothing (6f1d176: 51 committed, the in-app source dropped at restart). R27d: 50 kept and none added, no marker, the entry keeps its URL, `Sources is full` told once and again at a restart, reported `playlistUrl:full`; after one in-app removal (or a hand-run `state source remove`) the entry's URL is a record, ACTIVE, the marker landed and the entry stripped. B35 / B36 / B37 red on 6f1d176 (`same:no d:true marker:true entry:no told:0`; `records:49 told:0`; `probe:ok`). Not covered by any check: a GUIDE URL on the entry beside a held playlist (the round-17 rulings' open item 2) **[R28b and R28e, the same day: the guide URL is now held with the playlist and covered (TC-CFG-38); the form's refusal reads `Sources is full (50) · remove one first`, no host (`R28e: probeFailureLine -- ...`); and the cap is one function in the tree -- `Service.canAddSource` and `Guide.sourcesFull()` call `Model.sourcesFull` (`R28e (structural): ...`)]** **[F1, 2026-10-20 (lane-sweep-f4; round 3's dataloss review, P2): the retry RACED the cap again -- another program filling the freed place before the retry's save had read the file made the merge drop the migrated record while its marker landed, so both URLs left the entry for no record. Wants, through `tests/service-harness.js` on both hosts and both echo modes: `F1 (<tag>): held full, a HAND-RUN ...` -- after the race 50 records, the bar's playlist in none and its guide URL nowhere in the file, NO marker, both URLs on the entry, `migrationHeldFull` true, the R21 oracle true for both, reports `playlistUrl:full` only, the one `Sources is full` card and no 74018; then one more removal moves both in, active, the entry stripped, across a restart; `F1 (<tag>), rule 15: ...` -- another program adds the SAME playlist with no guide URL in the window: the migration re-runs over that record at once, the bar's guide URL on it, marker landed, entry stripped; and the model pin `F1: mergeForeignState -- ...`. Red on lane-sweep-c3 with this lane's test file: 9 checks in each own-echo mode (the four race pins, the four sibling pins -- there the record had no guide URL and the marker landed -- and the model pin). By mutation, ten mutants of the fix, each red in both modes (1 to 8 checks)]** **[D-SRC-64, 2026-10-22 (the 0.15.0 pre-cut live run, `key-20261022-111321-1894575`, 136 / 2 on 7c1d37f with B35 and B38 red on their `entry:` token alone): a hold at the cap PARKS the pair in `state.json` under `migrationPending` and strips the entry in its own write, so B35 wants `entry:no parked:yes` -- the parked URL read two ways by `parked_is`, the helper's `state show` over the run's scratch state folder naming a host and the file holding D's URL exactly, compared and never printed -- and B36 `parked:NOFIELD` once the migration has landed (the pair goes in the marker's write). The token red by driving the committed function over scratch states: no pair `NOFIELD`, another playlist `local file|no`]** |
| TC-CFG-36 | the guide's open is measured with its delegates (D-PERF-1, R27f, 2026-10-20) | A `scripts/dev-harness/open-scenario.sh check-tree` (9, in the gate); H `open-scenario.sh live` (21), with `spikes/open-mutations/slow-delegate.patch` through `--tree` | The instrument settles (a count stable over three frames, no delegate after it), names the presenting view, counts a screen of delegates (13 rows, 21 tiles at 10,000 channels) and moves with the 4 ms-per-delegate mutation (cold list 546 -> 647 ms). The BUDGET line is reported, not graded: rule 7's 150 ms holds warm (34 / 32 ms) and not cold (546 / 580 ms) in the cage's floating window; Hyprland's cold figure is UNVERIFIED (PERF-02) **[R28d, the same day, which replaces the row's wants: 13 rows / 21 tiles were the BUILT delegates, cacheBuffer included -- a screen DRAWS 10 rows and 16 tiles -- and the stable-count rule let a view that fills in late pass. Now: A `open-scenario.sh check-tree` (16 in the gate: D1-D10 drive `HarnessLib.openDrawnSet` over hand-made frames, E1-E4 `openDrawnSettle`, S1 the seam); H `open-scenario.sh live` (30): it settles at the first frame whose drawn set tiles the view (10 rows, 16 tiles; built 13 and 18-21), names the view, counts fewer than it built (L4 / W4), the WARM median is under 150 ms (L6 / W6) and nothing drawn changes after any decision (L7 / W7). Measured (`open-20261020-154123-1999165`, 30 / 0): cold 548 / 534 ms, warm 33 / 31 ms; the cold budget is printed, not graded, and is not met. Red: `late-fill.patch` 28 / 2 (L6, W6; warm 370 / 362 ms); counting every built delegate 18 / 12; each D and E check on a one-decision mutation of the function it drives. `slow-delegate.patch` moves cold summon 93 -> 207 ms and cold realised 548 -> 673 (list)]** **[R29e, the same day: "drawn" reads opacity too -- a delegate counts only at an effective opacity above 0, its own times every ancestor's up to the window -- because round 2's review passed a view faded in over 300 ms at 30 / 0. Not covered, so not claimed: an item stacked over the view, an ancestor's clip, a layer or shader effect, a fade's strength. A `open-scenario.sh check-tree` 19 (D11-D13 added: a screen at opacity 0, one delegate at 0, a screen at 0.3, the last the control for the narrowed claim); D11 and D12 red on the harness-lib that read `visible` alone (17 / 2). H `open-scenario.sh live` 33 / 0 (`open-20261020-192446-2690236`): cold 547 / 547 ms, warm 34 / 32 ms; `spikes/open-mutations/opacity-fade.patch` 31 / 2 (L6, W6 at a warm median of 338 / 341 ms; `open-20261020-192723-2700535`)]** |
| TC-CFG-37 | a read before a save that does not answer within 2 s: the save is written WITHOUT it, counted (`stateVerifyNoLoad`) and logged once (`state.json was not read back within <ms> ms of a save; saving without the read`), as on 0.14.2; nothing is refused, held past the bound or told (D-SINK-19 R29a, 2026-10-20; D-SINK-22 window c, left open by the ruling) **[R29a REPLACES this row's R28a case, which read: the change held, memory the authority, the file read again at 2, 4, 8, 16, 32 and 62 s, then every 30 s, told once at 8 s, "never a blind write and never a drop". Round 2's reviews measured two losses on it (a stalled read answering with a load failure dropped the held change; a stalled read's late answer was the OLD text and the save wrote over another program's write), and the lead withdrew it. The R28a wants below are history; the R29a wants follow them]** | A node, through `tests/service-harness.js` on both hosts and both echo modes: `R28a (<tag>): a read that never answers is asked again at 2, 4, 8, 16, 32 and 62 s ...`, `... the wait ends by OUR OWN WRITE reported late ...`, `... by a SOURCE verb ...`, `... by an in-app source ADD ...`, `... by ANOTHER PROGRAM'S WRITE ...`, `... by the STALLED READ ANSWERING LATE ...`, `... changes made while a save is held JOIN it ...`, `... by the SCHEDULE's re-read answering ...`, `... a RESTART while the save is held is the stated loss ...`, `R27a / R28a (<tag>): the write wait is BOUNDED at 2 s ...`, and R28c's `R28c (<tag>): the write wait's expiry is reset when the slow write LANDS ...`, `... is reported FAILED ...`, `... a held save's read state is reset when the read FINISHES ...` | Over an empty folder: re-reads counted `2000:1 4000:2 8000:3T 16000:4T 32000:5T 62000:6T 92000:7T` (T: told), told once (`Saving is waiting`, the file named, no `://`, replace id 74019), nothing blocked, refused, issued or created, memory holding the change; the read's eventual load failure is `absent`, told once on 74017, no file. Each way the wait ends keeps the change in memory, on disk and across a restart; a restart while held leaves the file exactly as it was and the next session loads it. Red on lane-sweep-c1 (66 of 2,692 in each echo mode with the R28b-e pins), e.g. `memory:false file:false restart:false` and `verb:[false,"state_unreadable"]`; by mutation: silence blocks 44, writes blind 45, clears the held save 44, no join re-read 9, no landing re-read 6, never tell 13, tell at 4 s 14, a flat 2 s schedule 13, re-read while a write is out 4; R28c's resets 4, 4, 12, 4, 4. No live segment: nothing in the cage stalls a FileView read without FUSE or root. The card is UNVERIFIED on a display. **[R29a's wants, lane-sweep-a3: A node through `tests/service-harness.js` on both hosts and both echo modes `R26a / R29a (<tag>): the read is BOUNDED ...` (a reload never delivered leaves the save parked, nothing written, until the watchdog's own handler fires; then saved, counted and logged once), `... the read's bound is 2 s, from the Timer the tree declares ...` (a load 1,999 ms late still decides the save; none given up at 2,000, not before), `R27a / R29a (<tag>): the write wait is BOUNDED at 2 s ...` (written without the read 4 s after it was asked), and `R29a: the stall notice and schedule are withdrawn ...` (no 74019, `notifyArgv("stateReadStalled")` sends nothing; the five names the documents used to cite answered null until F3 deleted them on 2026-10-20, with that half of the pin). Red on lane-sweep-c2 (`noLoad:2` with the save still parked), and by mutation of e5f6d4d: the silent read held past the bound 12, the timeout dropping the save 14, not counted 16, the wait re-arming instead of releasing 12; `r26a-watchdog-20ms.patch` and `r26a-watchdog-no-interval.patch` 8 each. H live with round 2's slow-file rig rebuilt in lane A3's scratch (not a gate; transcript `key-20261020-184229-2540898`): an edit and one asked while its write was out written at +2.0 s and +4.0 s without their reads, no 74019, no 74017, both kept across a restart; a hand-run helper add during the stall kept beside an in-app add; an atomic replace's favourite lost beside a label edit -- each as on 6f1d176. The last is window (c), stated in the README, not fixed]** **[F2 (2026-10-20, round 3's claims reviews): the helper add was kept because it landed after the save went without its read, not because the helper wrote it; one landing within the 2 s bound, or before a later save while the reads stay stalled, is lost like the favourite. Wants, through `tests/service-harness.js` on both hosts and both echo modes: `F2 (<tag>): window (c), stated ...` -- every read stalled; a helper `state source add` and a replace adding a favourite each lost within the bound, kept after it with no later save, lost after it when an in-app edit follows; the in-app favourite kept in all six. Identical on 6f1d176 (a scratch probe through its own `Service.qml`). Red by mutation: the bound holding the save instead of writing it (18 checks, this pin among them), and a harness double whose replace raises a load (24)]** |
| TC-CFG-38 | a migration held at the cap holds the bar's guide URL with its playlist: not adopted onto any record, not reported, not stripped; one card; after a removal both move in together (D-SINK-19 R28b, 2026-10-20) | A node `R28b: adoptActiveSource MIGRATING at the cap ...`, `R28b: reconcileAction -- heldFull makes the guide URL fresh ...`, and through the harness on both hosts and both echo modes `R28b (<tag>): a 0.13.6 install with 50 sources ...`, `R28b (<tag>): the first start of an install whose state names A active but carries no migration marker ...`; H key-scenario B38, B39 | The entry keeps both URLs, a picked source keeps its own guide URL across a restart, each start tells `Sources is full` and never `Bar setting removed`; one removal adds the playlist with the bar's guide URL, active, the entry stripped of both. Live (`key-20261020-155757-2060758`, 136 / 0) green; red on `--baseline 843ae87` (B38 `a-epg:bar`, B39 `d-epg:empty ... a-epg:bar`) and on `--baseline 6f1d176`. By mutation: R4 run on `full` 9, the retry fresh for the playlist only 5 **[R29e, the same day: the card's body now ends `; the bar's playlist then becomes the active source.` (`Model.entryInputNotice("playlistUrl", "full")`), because the removal makes it active over a source picked meanwhile -- which R28b's service pin already holds]** **[D-SRC-64, 2026-10-22: the pair is parked in `state.json` as ONE pair and both URLs leave the entry in the hold's own write, at the first start and again after the restart, so B38 wants `entry:no/no parked:yes/yes` (`parked_is` over the playlist and the guide URL) and B39 `parked:NOFIELD/NOFIELD`; the old `entry:yes/yes` red on 7c1d37f, the 0.15.0 pre-cut live run (TC-CFG-35 has the token's own red)]** |
| TC-CFG-39 | a guide URL that came with an unusable bar playlist is never adopted onto another source: told WITH the playlist in one notice (`Bar setting removed`, reason `invalid-pair`, no URL) and stripped with it, the active source keeping its own guide URL; the same when the unusable playlist was told before and a fresh guide URL arrives before the marker lands (D-SINK-19 R29d, 2026-10-20) | A node `R29d: entryInputNotice(name, "invalid-pair") -- ...`, and through the harness on both hosts and both echo modes `R29d (<tag>): an UNUSABLE bar playlist with a guide URL beside it, A active with its OWN guide URL -- ...`, `R29d (<tag>): the same entry with NO active source -- ...`, `R29d (<tag>), rule 15: the unusable playlist was told about already ...`; `tests/fixtures/active-key.json` (three adopt cases); H key-scenario B40, K1..K3 | A keeps its own guide URL across a restart, one card (`playlistUrl:invalid-pair`), the guide URL in no file, both off the entry; with no active source one card where there were two. Red on lane-sweep-c2 (A's guide URL replaced by the bar's, `aEpg 'E'`; reports `epgUrl:no-source,playlistUrl:invalid`) and by mutation of e5f6d4d: R4 run beside an unusable playlist 13, the seen sibling not handled 5, reported as the old `invalid` 8, the sibling not reported 4. Live (`key-20261020-184353-2546836`, 138 / 0) green; `--baseline lane-sweep-c2` 134 / 4 (K1..K3, B40 `a-epg:bar ... pair:0 file:yes`) and `--baseline 6f1d176` 127 / 11 |

#### Browse (US2, R1, R3, R4, R5, R6, UX 2.x, 3.1, 3.2)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-BRW-01 | open with `SUPER + SHIFT + T` | M 5.3 (binding added by hand), 5.4 US2 | guide opens on the focused monitor; second press closes |
| TC-BRW-02 | open with bar left click; click again closes | M 5.4 US2 | same |
| TC-BRW-03 | open with `omarchy-shell shell toggle io.github.rmcdavid.iptv` | M 5.4 US2 | same; `hide`/`summon` also work |
| TC-BRW-04 | menu entry (optional) | M 5.3 | `omarchy-menu.jsonc` snippet from README opens the guide |
| TC-BRW-05 | opens in search mode, empty query (UX 3, 4.1) | M 5.4 US2 step 2 | header `Search channels...` at placeholder opacity; footer hint `Enter play - Up/Down move - Left/Right group - Tab keys - Esc close`; cursor on row 0, or on the playing channel when it is in the list |
| TC-BRW-06 | default column entry (UX 2.2) | M 5.4 US2 step 2, US5 step 3 | Favorites when it has entries, else All; scope label `All - 1,475 channels` / `Favorites - 6 channels`; Recent hidden while empty; Favorites always present |
| TC-BRW-07 | type to filter (UX 2.6) | M 5.4 US2 step 3 | terms ANDed, case and diacritic insensitive (`TELE quebec` finds `Tele Quebec` spelled with accents), scope label `in All - N matches`, cursor to result 0 |
| TC-BRW-08 | ranking tiers and favorites first (R4, UX 2.5) | A* `Model.test.js` (`filterChannels` tiers 0-3, favorites first, playlist order inside a tier); M spot check with `news` | name-prefix rows first, then word-start, then name-contains, then group-contains |
| TC-BRW-09 | result cap 200 (R3) | M 5.4 US2 step 4 with `index.m3u` or `gen-10k.m3u` | footer `First 200 of N - keep typing`; list has 200 rows |
| TC-BRW-10 | Up/Down wrap, PgUp/PgDn clamp, Home/End (UX 3.1, 3.2) | M 5.4 US2 step 5 | Down on the last row wraps to row 0; PgDn moves visible-1 rows and stops at the end; End/Home jump |
| TC-BRW-11 | Left/Right move the column; query from Recent/Favorites jumps to All and restores on clear (UX 2.7) | M 5.4 US2 step 6 | column highlight moves and wraps; typing on Favorites highlights All; clearing restores Favorites |
| TC-BRW-12 | Esc semantics and host open-state (UX 3.2) | M 5.4 US2 step 7 | Esc with a query clears it (hint changes from `Esc clear` back to `Esc close`); Esc with an empty query closes; afterwards `omarchy-shell shell toggle` opens on the first call (state in sync) |
| TC-BRW-13 | Tab / `/` mode switch (UX 3.1) | M 5.4 US2 step 8 | Tab commits the query and shows `j/k move - h/l group - Enter play - Space preview - f favorite - s stop - r refresh - / search`; `/` returns to search mode with the query preserved |
| TC-BRW-14 | list mode ignores unbound letters | M 5.4 US2 step 9 | `q`, `w`, `e` do nothing; no search starts |
| TC-BRW-15 | digits: ignored in list mode, literal in search mode | M 5.4 US2 step 9 | `4` in list mode: nothing; `4k` in search mode filters |
| TC-BRW-16 | uppercase F/S/R/X act like lowercase | M 5.4 US2 step 9 | same actions |
| TC-BRW-17 | group-scoped search and zero results (UX 2.7, 6.3) | M 5.4 US2 step 10 | on a group: `in <group> - N matches`; no match: `No matches for "sky" in <group>` and `h/l other groups - Home for All`; Home jumps the column to All |
| TC-BRW-18 | zero results in All | M 5.4 US2 step 10 | `No matches for "zzzz"` / `Esc clears the search` |
| TC-BRW-19 | scrim click closes, card click swallowed, hover through PointerMoveGate (UX 5.4, 7.3) | M 5.4 US2 step 11 | one highlighted row at all times; keyboard move then stationary pointer does not steal the cursor |
| TC-BRW-20 | exclusive keyboard focus (PLAN risk R2) | M 5.4 US2 step 12 | with a terminal focused behind, typed letters go to the guide only |
| TC-BRW-21 | group order = playlist order, `Ungrouped` last (UX 2.2, 2.5) | A* `Model.test.js` (`groupChannels`); M | never alphabetised |
| TC-BRW-22 | multi-group `A;B;C` under the first group, searchable by any (R5) | A* `tests/test_playlist.py` with `qa-groups.m3u`; M with `us.m3u` (`Animation;Kids;...` entries) | listed once under `Animation`, found by `kids` |
| TC-BRW-23 | wheel: list scrolls, column moves one entry per tick (UX 7.3) | M 5.4 US2 step 11 | as stated |
| TC-BRW-24 | narrow screen hides the column (UX 5.1, R6), optional | M 5.6 | under `Style.space(720)` card width: column hidden, `h`/`l` still work, scope label is the indicator |
| TC-BRW-25 | summon payload `{"query":"bbc"}` (scaffold feature, optional) | M | query prefilled |

#### Watch (US3, R10, R11, UX 3.1 Enter/Space, 4.7, 6.4, 7.5)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-PLAY-01 | Enter plays, closes, focuses mpv | M 5.4 US3 step 1, 5.7 | exactly one `mpv` with `--wayland-app-id=omarchy-iptv`; `hyprctl clients` shows `class: omarchy-iptv`, `title: <channel name>`; guide hidden; mpv focused |
| TC-PLAY-02 | Enter on another channel reuses the window | M 5.4 US3 step 2, 5.7 | same mpv pid, title changes, no second window |
| TC-PLAY-03 | Enter on the playing row: no reload (UX 8 item 4) | M 5.4 US3 step 3 | stream not restarted (no black frame, `omarchy-shell io.github.rmcdavid.iptv status` unchanged apart from time), guide closes, mpv focused |
| TC-PLAY-04 | Space previews, guide stays open (UX 3.1, 4.7) | M 5.4 US3 step 4 | row name bold, trail glyph U+F040A, footer `U+F040A <name> - s stop`; cues move instantly on the next Space |
| TC-PLAY-05 | dead stream (R11, UX 6.4) | M 5.4 US3 step 5 | notification `Stream failed` / `<name> did not play` (plus ` - <mpv reason>` when known), glyph U+F0503, urgency normal, `-r` id reused; row trail U+F0026 and detail `Failed HH:MM - Space to retry`; cursor stays; bar back to idle glyph |
| TC-PLAY-06 | `s` stops (UX 3.1) | M 5.4 US3 step 6 | footer `Stopped` for 3 s then the count; mpv exits; no notification; bar idle |
| TC-PLAY-07 | user quits mpv (`q`) | M 5.4 US3 step 6 | bar idle, cues clear, no notification (exit 0) |
| TC-PLAY-08 | per-channel headers reach mpv over the socket, never argv | M 5.4 US3 step 8 with `gen-dead.m3u` (2 % entries carry `#EXTVLCOPT`) or `qa-headers.m3u`; A `Model.test.js` (`headerArgs`) | `ps -o args=` shows **no** `--user-agent=`, **no** `--referrer=` and **no** URL; the header values reach mpv only as IPC options (observed PLY-SEC-04; the pre-M2-02 expectation of headers on argv is inverted by S-03; corrected 2026-09-25, D-QA-19) |
| TC-PLAY-09 | hung mpv reaped by the health check (decision 12), optional | M 5.4 US3 step 9 | `kill -STOP <mpv>`: after two failed `status` polls (10 s each) the console logs `mpv unresponsive, restarting player` and mpv is SIGTERMed; the relaunch follows once mpv actually exits (send `kill -CONT` after a SIGSTOP test, mpv traps SIGTERM) |
| TC-PLAY-10 | zapping bursts (UX 1.2) | M 5.4 US3 step 4 | Space three times within 2 s ends on the third channel; no dropped zap, no second mpv |
| TC-PLAY-11 | mpv survives `omarchy restart shell` (R10 withdrawn) | M 5.4 US5 step 6 | same pid, same window, still playing after the restart; the successor shell adopts it (observed PLY-RST-01, PLY-WEAK-03; corrected 2026-09-25, D-QA-19) |
| TC-PLAY-12 | zap in under two seconds of interaction (PRODUCT) | M 5.4 US3 step 1 | open + 3 letters + Enter to first frame under 2 s (stopwatch) |
| TC-PLAY-13 | mpv missing notification `mpv not found` / `Install mpv to play channels.` (critical) | M not runnable here (mpv is an Omarchy dependency); verify by code review of the exit-code path | recorded `not run` |
| TC-PLAY-14 | guide over fullscreen mpv (UX 7.5) | M 5.4 US3 step 10 | overlay draws above; Esc returns; mpv neither paused nor muted |

#### Bar widget (US4, R7, UX 3.3, 3.4, 4.8, 6.3)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-BAR-01 | idle | M 5.4 US4 step 1 | glyph U+F0502 dimmed (`Qt.darker(bar.barForeground, 1.55)`), no label; tooltip `IPTV - click to open the guide` |
| TC-BAR-02 | not configured | M 5.4 US1 step 1 | glyph U+F0502, tooltip `IPTV - no playlist configured` |
| TC-BAR-03 | playing | M 5.4 US4 step 2 | glyph U+F0567 + name elided at `Style.space(barLabelMaxWidth)`; tooltip `Playing <full name>` |
| TC-BAR-04 | error, not playing | M 5.4 US1 step 4 | glyph U+F0503; tooltip `IPTV - playlist error, open the guide` |
| TC-BAR-05 | refreshing | M 5.4 US4 step 5 | tooltip `IPTV - refreshing playlist...` |
| TC-BAR-06 | left click toggles the guide | M 5.4 US4 step 3 | open, click again closes |
| TC-BAR-07 | right click stops | M 5.4 US4 step 4 | mpv exits, idle glyph |
| TC-BAR-08 | middle click refreshes (R12: manual refresh notifies) | M 5.4 US4 step 5 | footer `Refreshing...` then `Refreshed - 1,475 channels`; notification `Playlist refreshed` / `1,475 channels in 38 groups` (counts from the live list), urgency low, glyph U+F0450 |
| TC-BAR-09 | wheel zaps one channel per tick in the zap ring, wraps (UX 3.4) | M 5.4 US4 step 6 | played from Favorites: scroll stays inside Favorites; from a group: inside the group; from Recent: the channel's group; touchpad swipes accumulate (`Util.wheelSteps`) |
| TC-BAR-10 | vertical bar: glyph only, name in tooltip (R7), optional | M 5.6 | `omarchy bar position left`, check, `omarchy bar position top` |
| TC-BAR-11 | accessible names (UX 7.1) | X bar scenarios of the accessibility harness, dated run filed in `docs/QA-RESULTS.md` "Accessibility harness runs". **Not** a grep: the old criterion was `grep -n 'Accessible' BarWidget.qml`, which is two lines the widget was written to contain and cannot go red (rule 14) | The harness instantiates `BarWidget.qml` in a plain hidden Qt window, walks the AT-SPI tree and reads back the node for each of the three states: exactly one `push button`, whose **name** is `IPTV, idle` / `IPTV, playing <name>` (`IPTV, playing channel <n>, <name>` when numbered, M2-03 section 11) / `IPTV, playlist error`, the three names distinct, and no Private-Use glyph codepoint inside any published name. **Markup only.** Delivery of these names to an assistive technology is UNVERIFIED and currently impossible (D-GS-3) |
| TC-BAR-12 | third-party replacement bar facade (ARCH risk 7) | not testable here | recorded `not run`, README mentions the limitation |

#### Favorites and recents (US5, R5, R8, UX 2.2, 3.1 f/x)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-FAV-01 | `f` toggles favorite | M 5.4 US5 step 1 | lead star U+F04CE appears; footer `Added to Favorites` / `Removed from Favorites` for 3 s |
| TC-FAV-02 | Favorites entry always present; empty state | M 5.4 US5 step 2 | `No favorites yet` / `Press f on any channel to pin it here` |
| TC-FAV-03 | Favorites order = order added; first after Recent | M 5.4 US5 step 3 | as stated |
| TC-FAV-04 | `f` inside Favorites removes the row, cursor clamps | M 5.4 US5 step 3 | as stated |
| TC-FAV-05 | `x` / `X` / Delete | M 5.4 US5 step 4 | in Recent removes (`Removed from Recent`); in Favorites unfavorites; elsewhere no-op |
| TC-FAV-06 | Recent list rules | A `Model.test.js` (`pushRecent`: newest first, de-duplicated, capped); M 5.4 US5 step 5 | hidden while empty; replay moves to top; cap `maxRecents` |
| TC-FAV-07 | recent recorded on the play command even when the stream fails (R5) | M 5.4 US3 step 5 | the dead channel is in Recent |
| TC-FAV-08 | persistence across shell restart; file modes | M 5.4 US5 step 6, 5.7 | favorites and recents survive `omarchy restart shell`; `~/.local/state/omarchy-iptv` 0700, `state.json` 0600 |
| TC-FAV-09 | corrupt `state.json` | A `Model.test.js` (`parseState`; since 2026-10-13 `R22a: stateLoadKind ...` and the `R22a (... host, ... start): garbage` / `empty` harness pins); M 5.4 US5 step 7 | ~~empty state, no crash, file rewritten on next change~~ **[Amended 2026-10-13, D-SINK-19 round 12 (R22a): the opposite. The file is never rewritten while it does not parse: no crash, one critical notification `Saved sources not loaded` (`... is not a valid state file. Nothing is saved until it can be read, ...`), the guide on its first-run form (nothing loaded, so no channels to favourite), an add from that form refused with `state.json could not be read - nothing is saved until it can be`, and the file byte for byte as it was afterwards. "Rewritten on next change" is how a start erased every source until round 12 (TC-CFG-16).]** |
| TC-FAV-10 | ids stable across refresh (decision 6) | A `tests/test_playlist.py` (`assign_ids`), `qa-attrs.m3u`; M 5.4 US7 | favorites still favorites after `r` |
| TC-FAV-11 | click on the lead slot toggles without playing (UX 2.4, 7.3) | M 5.4 US5 step 1 | star toggles, nothing plays |

#### EPG (US6, decision 5, UX 2.4, 5.6)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-EPG-01 | guide never blocks on EPG | M 5.4 US6 step 1 | guide opens instantly after `epgUrl` is set; footer `Guide data loading...` / neutral banner until `epg-now.json` lands |
| TC-EPG-02 | row content with EPG | M 5.4 US6 step 2 | detail `Now: X - Next: Y`, right meta `until HH:MM` (24 h local), progress hairline fraction = elapsed/duration |
| TC-EPG-03 | channel without EPG data | M 5.4 US6 step 3 | no `Now:`/`Next:` segments, no `until`; single-line rows inside a group when EPG is not configured |
| TC-EPG-04 | EPG failure is soft | M 5.4 US6 step 4 | banner `Guide data unavailable (<reason>) - channels still work - r retry`; notification `Guide data error` / `Could not fetch the EPG (<reason>). Channels still work.` low; playback unaffected |
| TC-EPG-05 | plain and gzip give identical output | A* `tests/test_epg.py` with `qa-epg.xml` and `qa-nonascii/qa-epg.xml.gz` | byte-identical `epg-now.json` (apart from `generatedAt`) |
| TC-EPG-06 | timezone offsets and formats | A* `tests/test_epg.py` (clock pinned to T0 = 1789244100) | per the fixture comment: `bbc1.uk` now `Six O'Clock News` stop 1789245000; `cnn.us` now `The Lead`; `halfhour.test` now `Half Hour Offset`; `notz.test` treated as UTC; `short.test` 12-digit accepted |
| TC-EPG-07 | overlap, gap, no-stop, far, orphan, no-programme channel | A* `tests/test_epg.py` | overlap: now = latest start <= T0 (`Overlap B`), next `After Overlap`; gap: no now, next `Starts Later`; nostop: now `No Stop Attribute` with stop = next start; `far.test` absent (outside +-24 h); `orphan.test` keyed or ignored, never a crash; `nochannel.test` absent |
| TC-EPG-08 | 30 s tick and 5 min recompute (R8, decision 5) | M 5.4 US6 step 5 | `until` and fraction advance; `epg --now-only` runs every 5 min (journal), no download before the TTL |
| TC-EPG-09 | unicode titles | A* `tests/test_epg.py` (`unicode.test`); M with `gen-real.xml` | character references decoded; rows render |
| TC-EPG-10 | `too_large`, `bad_gzip`, HTTP errors | A* `tests/test_epg.py` | error object with the code; `epg-status.json` written; old `epg-now.json` kept |
| TC-EPG-11 | matching restricted to playlist ids, `@SD` style ids | A* `tests/test_epg.py` (`00sReplay.us@SD`) | id with `@` matched verbatim |
| TC-EPG-12 | large EPG does not stall typing | PERF-04, PERF-03 | as in section 4 |

#### Refresh and offline (US7, R12, decision 7)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-RFR-01 | `r` refreshes playlist and EPG | M 5.4 US7 step 2 | footer `Refreshing...` then `Refreshed - N channels`; notification `Playlist refreshed` low |
| TC-RFR-02 | timer refresh is silent on success | M 5.4 US7 step 1 (15 min wait, optional) | helper run in the journal at +15 min, no notification |
| TC-RFR-03 | offline with cache (banner, footer, notification) | M 5.4 US7 steps 3-4 (local server stopped) | banner `U+F0026 Playlist refresh failed (Connection refused) - showing cached copy from HH:MM - r retry`; footer `N channels - cached HH:MM - offline`; notification `Playlist error` / `Could not fetch the playlist (Connection refused). Using cached copy from HH:MM.` normal |
| TC-RFR-04 | debounce: two triggers within 300 ms = one run | M 5.4 US7 step 5 | journal shows one helper invocation |
| TC-RFR-05 | refresh does not interrupt playback | M 5.4 US7 step 2 | mpv untouched |
| TC-RFR-06 | startup offline uses the cache | M 5.4 US7 step 6 | after `omarchy restart shell` with the server down the guide renders from cache immediately, then the banner appears |
| TC-RFR-07 | list changes while the guide is open | M 5.4 US7 step 7 | rows rebuild, cursor index clamped |
| TC-RFR-08 | playlist parsed but empty (`qa-empty.m3u` served) | M 5.4 US7 step 8 | `Playlist has no channels` / `Parsed 0 channels from <host> - check the URL points at an M3U`; previous cache kept and marked stale |
| TC-RFR-09 | not an M3U (`qa-not-m3u.html` served) | M 5.4 US7 step 8 | reason `Not an M3U file` (helper code `not_a_playlist`, D-QA-13; the guide must map that code, D-LIVE-03) |
| TC-RFR-10 | stale cache marked in bar tooltip | M 5.4 US7 step 3 | tooltip carries `(cached)` or the footer does (UX 6.3 puts it in the footer; either is acceptable, both is best) |

#### States, microcopy, theme (UX 4.x, 5.x, 6.x, QB1)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-UI-01 | not configured (UX 4.4, 6.3) | M 5.4 US1 step 1 | `No playlist configured`; `Set your M3U URL or path, then press r to load it:`; command box `omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>`; `Optional EPG:  omarchy bar set io.github.rmcdavid.iptv epgUrl <url>  (converted; not kept in shell.json)`; `Both are inputs: the URL moves to ~/.local/state/omarchy-iptv/state.json; other settings live in ~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv)`; column hidden; hint `r reload - Esc close`; glyph U+F0502; click on the box copies (`wl-paste`) and footer `Copied` **[Amended 2026-10-12, D-SINK-19 round 3: the EPG line and the "where" line are the strings `Guide.qml` ships on lane-key-s1 (`unconfiguredEpg`, `unconfiguredWhere`; two spaces before the parenthesis, as shipped), ruled by the lead to the exact text the review's truth lens gave. Until that round they read `Optional EPG:  omarchy bar set io.github.rmcdavid.iptv epgUrl <url>` and `Settings live in ~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv)`, presenting the URL keys as stored settings. The command box is unchanged because a click COPIES it. Both Texts wrap (`wrapMode: Text.WordWrap` over `parent.width`); how the longer lines wrap at the shipped width is UNVERIFIED on a display.]** **[Amended 2026-10-13, D-SINK-19 round 11 (R21): the command box, its click-to-copy, the `Copied` transient and the `Optional EPG` line are DELETED (a URL set that way is refused after the migration). Expected now: `No playlist configured`; `Add your M3U URL or path in Sources, with its EPG URL if you have one`; `Sources and their URLs are kept in ~/.local/state/omarchy-iptv/state.json; other settings live in ~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv)`; column hidden; glyph U+F0502; nothing to click. UX.md 4.4.]** |
| TC-UI-02 | loading, no cache (UX 4.5) | M 5.4 US1 step 2 | glyph U+F01D8, `Loading playlist...`, `Fetching from iptv-org.github.io` (host only), hint `Esc close`; never shown when a cache exists |
| TC-UI-03 | error with cache (banner, UX 4.6) and without cache | M 5.4 US7 step 3, US1 step 4 | banner spec (height `Style.space(28)`, urgent tint, glyph U+F0026, 140 ms fade); empty error state with glyph U+F0503 |
| TC-UI-04 | now-playing cues (UX 4.7) | M 5.4 US3 step 4 | bold name + U+F040A + footer, column unchanged |
| TC-UI-05 | theme switch, guide closed and open (QB1, QB3) | M 5.5 | `omarchy theme set tokyo-night`, `catppuccin-latte`, back to `retropc`: overlay and bar re-skin live, no restart, no new journal warnings |
| TC-UI-06 | no hardcoded colors (UX 5.9) | A `grep -nE '#[0-9a-fA-F]{3,8}\b|"white"|"black"|Qt\.rgba\(' *.qml` | only lines with `CONVENTION-EXCEPTION` |
| TC-UI-07 | fonts from tokens | A `grep -n 'font.family' *.qml` | only `Style.font.menuFamily`, `bar.fontFamily`, `root.fontFamily` bound to those |
| TC-UI-08 | animations (UX 5.8) | M 5.4 US2 step 1 | no open/close fade; banner 140 ms; label width 180 ms |
| TC-UI-09 | footer hints per mode (UX 6.2) | M 5.4 US2 steps 2, 3, 8 | four exact strings |
| TC-UI-10 | scope labels (UX 6.1) | M 5.4 US2 | `Favorites - 6 channels`, `All - 1,475 channels`, `Recent - 3 channels`, `<group> - N channels`, `in All - 14 matches`, `in <group> - 9 matches` |
| TC-UI-11 | glyph codepoints (UX 5.5) | A `grep -nP '[\x{F0000}-\x{FFFFF}]' *.qml` and eyeball | U+F0502 idle, U+F0567 playing, U+F0503 error, U+F04CE favorite, U+F040A playing row, U+F0026 failed, U+F01D8 loading, U+F0450 refresh |
| TC-UI-12 | microcopy centralised (UX 5.9) | A `ls Copy.js` or `grep -n 'readonly property var copy' Guide.qml` | one place; strings match UX 6 |
| TC-UI-13 | qmllint clean, console clean | A `scripts/check.sh` (qmllint step); M 5.9 | 0 errors; only baseline warnings recorded in README |
| TC-UI-14 | card geometry (R6, UX 5.1) | M visual + `grep -n 'space(960)\|space(620)\|space(200)\|space(720)' Guide.qml` | tokens present, card centred, no resize while open |

#### Accessibility and ergonomics (UX 7)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-A11Y-01 | roles and names (UX 7.1) | X guide scenarios of the accessibility harness, dated run filed in `docs/QA-RESULTS.md` "Accessibility harness runs". **Not** a grep: the old criterion was `grep -n 'Accessible\.' Guide.qml BarWidget.qml`, 58 lines the two files were written to contain, and it passed for the whole life of the project while nothing the guide declares reached any screen reader (rule 14, D-GS-3) | Per row of UX 7.1, the node is present in the walked tree with the stated role and the stated name: Dialog `IPTV guide`, EditableText `Search channels` (with its **value** and description equal to the typed query), List `Groups` / `Channels in <scope>`, ListItem per row carrying the suffixes of UX 7.1 that the scenario's fixture populates, AlertMessage banner, StaticText footer, Button bar. A row of UX 7.1 that no scenario populates is marked UNVERIFIED there and is not claimed here. **Markup only.** Delivery is UNVERIFIED (D-GS-3) |
| TC-A11Y-02 | no colour-only status (UX 7.2) | M review during 5.4 | every state has a glyph or word |
| TC-A11Y-03 | hit targets (UX 7.3) | M 5.4 US2 step 11 | rows full width >= `Style.space(38)`, lead slot >= 28 px square |
| TC-A11Y-04 | multi-monitor (UX 7.4, PLAN A7/R12) | M 5.6 | not verifiable on this machine; procedure recorded for a two-monitor run |
| TC-A11Y-05 | focus and mpv (UX 7.5) | covered by TC-PLAY-01/03/14 | |
| TC-A11Y-06 | performance ergonomics (UX 7.6) | PERF-02, PERF-03 | |

#### Parsers and model (QB2)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-PARSE-01 | `#EXTINF` quoted/bare attributes, commas in titles, durations | A `tests/test_playlist.py::ExtinfTest` (exists); A* with `qa-attrs.m3u` | see section 7 expected values |
| TC-PARSE-02 | `#EXTGRP` persistence and clearing, `group-title` wins | A `test_attributes_fixture` (exists); A* `qa-groups.m3u` | `Sports`, `Sports`, `Movies`, `News`, `Ungrouped` |
| TC-PARSE-03 | multi-group first segment for display, whole string in `searchKey` (R5) | A* `qa-groups.m3u` | `Animation` / `multi group channel animation kids religious` (D-QA-03 until fixed) |
| TC-PARSE-04 | `#EXTVLCOPT` / `#KODIPROP` mapping, scope, no leak | A `test_vlcopt_does_not_leak_to_next_entry` (exists); A* `qa-headers.m3u` | section 7 |
| TC-PARSE-05 | duplicate tvg-id, exact duplicate URL ids | A `test_attributes_fixture`; A* `qa-attrs.m3u` | `u:<hash>` for both HD/SD; `u:cc5a0021` and `u:cc5a0021#2` |
| TC-PARSE-06 | BOM + CRLF | A `test_crlf_and_bom` (exists); A* `qa-nonascii/qa-bom-crlf.m3u` | 3 channels, no `\r` in URLs, `#EXTGRP` persists across CRLF |
| TC-PARSE-07 | unicode names, folding, non-Latin kept | A `NormalizationTest` (exists); A* `qa-nonascii/qa-unicode.m3u` | section 7 |
| TC-PARSE-08 | scheme allow-list | A `test_attributes_fixture` (3 skipped); A* `qa-schemes.m3u` | 13 allowed (14 until D-QA-07), 21 skipped, 2 orphans |
| TC-PARSE-09 | empty playlist and HTML page | A `test_empty_playlist_is_an_error` (exists); A* `qa-empty.m3u`, `qa-not-m3u.html` | `empty_playlist`; `not_a_playlist` (lane A's code name for the D-QA-13 case; v0.1 wrote `not_m3u`) |
| TC-PARSE-10 | 10k parse time and cache size | PERF-01 | |
| TC-PARSE-11 | XMLTV plain/gz/offsets | TC-EPG-05..11 | |
| TC-MODEL-01 | normalisation and id vectors shared with the helper | A `node tests/Model.test.js`, `tests/Model.spec.qml`, `tests/test_playlist.py::test_fold_table_matches_model_js` (exist) | identical vectors |
| TC-MODEL-02 | filter ranking, cap, favorites-first (R3, R4) | A* `Model.test.js` | |
| TC-MODEL-03 | groups, zap ring, `nextInGroup` wrap (R9, UX 3.4) | A `Model.test.js` (exists, extend for ring by launch list) | |
| TC-MODEL-04 | state parse/toggle/recents, tolerant of garbage | A `Model.test.js` (exists) | |
| TC-MODEL-05 | settings lookup and clamps (R2) | A `Model.test.js` (`findBarEntry`, `clampInt`; extend for 360/15/1440 and `barLabelMaxWidth`) | |
| TC-MODEL-06 | mpv argv: reserved, `--no-` forms, case (D-QA-11), URL after `--`, headers | A `Model.test.js` (exists, extend) | |
| TC-MODEL-07 | Model.js loads in the Qt engine | A `QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml` (exists) | 8+ PASS |
| TC-MODEL-08 | Guide/BarWidget specs (PLAN M1-17) | A* `qmltestrunner -input tests/Guide.spec.qml`, `tests/BarWidget.spec.qml` | states render from fixture JSON, key routing |

### 1.2 User stories -> test cases

| Story | Test cases |
|---|---|
| US1 Configure | TC-CFG-01..13, TC-UI-01, TC-UI-02, TC-UI-03, TC-BAR-02, TC-BAR-04, SEC-07, SEC-08, SEC-12 |
| US2 Browse | TC-BRW-01..25, TC-UI-09, TC-UI-10, TC-BRW-22, PERF-02, PERF-03 |
| US3 Watch | TC-PLAY-01..14, TC-INST-09, SEC-03, SEC-05, SEC-06, SEC-13, SEC-17 |
| US4 Now playing | TC-BAR-01..12, TC-CFG-09, TC-CFG-10 |
| US5 Favorites and recents | TC-FAV-01..11, TC-INST-08, TC-CFG-11 |
| US6 EPG | TC-EPG-01..12, TC-CFG-06, PERF-04 |
| US7 Refresh | TC-RFR-01..10, TC-CFG-07, TC-BAR-05, TC-BAR-08 |
| US8 Install and uninstall | TC-INST-01..10, SEC-14, SEC-15, SEC-16 |

### 1.3 Rulings R1-R13 -> test cases

| Ruling | Test cases |
|---|---|
| R1 keyboard model (search mode on open, Tab or `/` to list mode, no Ctrl chords, Esc peels) | TC-BRW-05, 10, 12, 13, 14, 15, 16, TC-UI-09 |
| R2 settings schema (refreshMinutes 360/15/1440, barLabelMaxWidth 180/60/600) | TC-CFG-07, TC-CFG-10, TC-MODEL-05, D-QA-05 |
| R3 result cap 200 with `First 200 of N - keep typing` | TC-BRW-09, TC-MODEL-02 |
| R4 searchKey = fold(name + " " + group), AND terms, four tiers, favorites first | TC-BRW-07, TC-BRW-08, TC-MODEL-01, TC-MODEL-02, TC-PARSE-07 |
| R5 sort and recents; multi-group first segment | TC-BRW-21, TC-BRW-22, TC-FAV-03, TC-FAV-06, TC-FAV-07, TC-PARSE-03 |
| R6 card and layout | TC-UI-14, TC-BRW-24 |
| R7 bar glyphs per state, label elision, wheel steps | TC-BAR-01..05, TC-BAR-09, TC-BAR-10, TC-CFG-10 |
| R8 model fields the guide binds (`failedAt`, `epgFraction` 30 s tick, guide state) | TC-PLAY-05, TC-EPG-02, TC-EPG-08, TC-UI-03 |
| R9 service actions and IPC verbs (`toggle play stop next previous refresh status`) | 5.8 IPC checks, TC-BAR-09, D-QA-04 |
| R10 mpv attached to the service (dies with the shell) -- **withdrawn by M2-02, the player is detached** | TC-PLAY-11, TC-INST-08 (both inverted 2026-09-25, D-QA-19) |
| R11 stream failure: notification, **persisted** `failedAt` (amended 2026-09-24), alert glyph | TC-PLAY-05, TC-FAV-07 |
| R12 manual refresh notifies, timer only on failure; never render URLs beyond scheme+host | TC-BAR-08, TC-RFR-01, TC-RFR-02, TC-RFR-03, SEC-07, TC-CFG-13 |
| R13 no animation, no `screen` set (focused monitor) | TC-UI-08, TC-A11Y-04 |

### 1.4 UX.md sections 3, 4, 6, 7 -> test cases

| UX section | Item | Test cases |
|---|---|---|
| 3 (intro) | opens in search mode; footer shows mode | TC-BRW-05, TC-UI-09 |
| 3.1 | `j`/Down, `k`/Up wrap | TC-BRW-10, TC-BRW-13 |
| 3.1 | `l`/Right, `h`/Left column wrap | TC-BRW-11, TC-BRW-13 |
| 3.1 | PgDn/PgUp clamp, End/Home | TC-BRW-10 |
| 3.1 | Enter (play, close, focus; no reload on the playing row) | TC-PLAY-01, TC-PLAY-03 |
| 3.1 | Space (preview, stay open) | TC-PLAY-04, TC-PLAY-10 |
| 3.1 | `f`/`F` | TC-FAV-01, TC-FAV-04, TC-BRW-16 |
| 3.1 | `x`/`X`/Delete | TC-FAV-05 |
| 3.1 | `s`/`S` | TC-PLAY-06 |
| 3.1 | `r`/`R` | TC-RFR-01 |
| 3.1 | `/`, Tab, Shift+Tab | TC-BRW-13 |
| 3.1 | Esc (clear committed query, else close) | TC-BRW-12 |
| 3.1 | `0`-`9`, Shift+Enter reserved, other letters ignored | TC-BRW-14, TC-BRW-15 |
| 3.2 | printable appends, re-filter, cursor 0 | TC-BRW-07 |
| 3.2 | Backspace, Ctrl+Backspace, Ctrl+U | TC-BRW-07 (step 3 includes them) |
| 3.2 | Down/Up, Right/Left, PgDn/PgUp/Home/End | TC-BRW-10, TC-BRW-11 |
| 3.2 | Enter, Tab, Esc | TC-PLAY-01, TC-BRW-13, TC-BRW-12 |
| 3.3 | `SUPER + SHIFT + T`, left/right/middle click, scroll, hover | TC-BRW-01, TC-BAR-06, TC-BAR-07, TC-BAR-08, TC-BAR-09, TC-BAR-01..05 |
| 3.4 | zap ring by launch list | TC-BAR-09 |
| 4.1 | default guide | TC-BRW-05, TC-BRW-06, TC-EPG-02 |
| 4.2 | searching, scope jumped to All | TC-BRW-11, TC-UI-10 |
| 4.3 | row with EPG / without / failed | TC-EPG-02, TC-EPG-03, TC-PLAY-05 |
| 4.4 | not configured | TC-UI-01 |
| 4.5 | loading | TC-UI-02 |
| 4.6 | error with cache (banner) and without | TC-UI-03, TC-RFR-03, TC-CFG-02 |
| 4.7 | now playing cues | TC-UI-04 |
| 4.8 | bar states, vertical bar | TC-BAR-01..05, TC-BAR-10 |
| 6.1 | guide labels | TC-UI-10, TC-EPG-02, TC-PLAY-05, TC-PLAY-06, TC-RFR-01, TC-FAV-01, TC-FAV-05, TC-BRW-09, TC-EPG-01 |
| 6.2 | footer hints | TC-UI-09 |
| 6.3 | empty, loading, error states; bar tooltips | TC-UI-01, TC-UI-02, TC-UI-03, TC-RFR-08, TC-RFR-09, TC-FAV-02, TC-BRW-17, TC-BRW-18, TC-BRW-24, TC-BAR-01..05 |
| 6.4 | notifications | TC-PLAY-05, TC-BAR-08, TC-RFR-03, TC-CFG-02, TC-EPG-04, TC-PLAY-13, SEC-07 |
| 7.1 | accessible roles and names | TC-A11Y-01, TC-BAR-11 |
| 7.2 | no colour-only status | TC-A11Y-02 |
| 7.3 | hit targets, wheel behaviour | TC-A11Y-03, TC-BRW-23 |
| 7.4 | multi-monitor | TC-A11Y-04 |
| 7.5 | focus and the mpv window | TC-PLAY-01, TC-PLAY-03, TC-PLAY-07, TC-PLAY-14 |
| 7.6 | performance ergonomics | PERF-02, PERF-03 |

## 2. Automated test inventory expected from the FE lanes

Exact commands (all present on the machine of record; run from the repo root):

```
scripts/check.sh                                                     # everything below plus the ASCII gate
omarchy plugin validate .                                            # G0 manifest
mkdir -p /tmp/qmlroot/qs && ln -sfn /usr/share/omarchy/shell/Commons /tmp/qmlroot/qs/Commons \
  && ln -sfn /usr/share/omarchy/shell/Ui /tmp/qmlroot/qs/Ui \
  && /usr/lib/qt6/bin/qmllint -I /tmp/qmlroot -I /usr/lib/qt6/qml Service.qml BarWidget.qml Guide.qml tests/*.qml
node tests/Model.test.js                                             # G1 model (node 26 via mise, dev only)
python3 -m unittest discover -s tests                                # G1 helper
python3 -m unittest discover -s tests -v 2>&1 | tail -3              # count
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Guide.spec.qml      # M1-17
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/BarWidget.spec.qml  # M1-17
```

Scaffold baseline on 2026-09-12 (commit 7a26b6d): 61 node checks, 28 python
tests, 8 qml PASS, `check.sh: all green`. qmllint warnings accepted:
unqualified access / missing property on injected `bar`, `shell`, `service`.

What QA expects each suite to contain when M1 lands (a missing item is a
P3 "coverage" defect unless it guards a P1/P2 behaviour):

| Suite (owner) | Expected cases | Fixture |
|---|---|---|
| `tests/test_playlist.py` (lane A) | existing 20 + `qa_groups` (R5 first segment, EXTGRP persist/clear, empty EXTGRP, padded/leading-semicolon groups), `qa_attrs` (url-tvg beats x-tvg-url, bare and uppercase attributes, repeated attribute = last wins, duplicate tvg-id -> url hashes, `#2` suffix, empty title never uses the URL [D-QA-02], tvg-name fallback, broken EXTINF, blank line before URL, tab-separated attributes, lost first EXTINF), `qa_headers` (UA/referrer, VLCOPT before EXTINF, bare CR stripped, percent-encoded CRLF stripped, bad header name dropped + warning, metacharacters verbatim, option-looking key rejected [D-QA-09], empty value dropped [D-QA-10], uppercase key, no leak after a skipped URL), `qa_schemes` (allow-list incl. mpv pseudo-protocols, empty host [D-QA-07], orphans counted), `qa_empty`, `qa_not_m3u` [D-QA-13], `qa_unicode` (fold vectors incl. NFD [D-QA-08], non-Latin kept, emoji round trip), `qa_bom_crlf` | `tests/fixtures/qa-*.m3u`, `tests/fixtures/qa-nonascii/*.m3u` |
| `tests/test_helper.py` (lane A) | existing 7 + `too_large` on a sparse 65 MB file (`truncate -s 65M`), `unsafe_path` for `/proc/self/environ` and a symlink into `/proc`, `/dev/zero` refused, gzip bomb capped [D-QA-06], `--timeout` honoured against a listening-but-silent socket, status file written on every failure, `fetchedAt` carried over when stale | synthetic in tmp |
| `tests/test_epg.py` (lane A, new) | clock pinned to T0 (a `--now` flag or env var is the recommended seam): plain vs gz identical; offsets +0100/-0500/+0530/none/12-digit; overlap, gap, nostop, far (+-24 h window), orphan, nochannel; `@SD` ids; unicode; `epg-now.json` shape (`version`, `generatedAt`, `validUntil`, `channels.<id>.now/next`); `--now-only` recompute without fetch; `too_large` (64 MB cap on the compressed download AND on inflated bytes), `bad_gzip`, HTTP errors; XML entity expansion does not explode (SEC-19); restrict to playlist ids when `channels.json` exists | `tests/fixtures/qa-epg.xml`, `tests/fixtures/qa-nonascii/qa-epg.xml.gz`, generated `gen-*.xml.gz` |
| `tests/test_mpv_ipc.py` (lane A, new) | fake `AF_UNIX` server: `play` sends `set_property title`, `set_property force-media-title`, per-file header options, `loadfile <url> replace`; `stop` sends `quit`; `status` parses `media-title`, `paused`, `idle-active`; `not_running` unlinks a stale socket; `ipc_error` on garbage; `unknown_channel` when the id is not in `channels.json`; never prints the URL | synthetic |
| `tests/test_state.py` (lane A, only if the `state` subcommand ships) | dump/favorite/recent round trip, atomic write, corrupt file tolerated **[2026-10-13, D-SINK-19 round 12 (R22a): corrupt file REFUSED -- every verb but `init` exits 1 with `state_unreadable` and writes nothing, `init` reports `found` and never rewrites an existing file (`StateNeverWrittenUnreadTest`)]** | synthetic |
| `tests/Model.test.js` (lane B) | existing 61 + tiers 0-3 with favorites first and playlist order inside a tier; cap 200 + `truncated`; `tokenize` folds the query; `groupChannels` order (Recent, Favorites always, All, groups in first-seen order, `Ungrouped` last); zap ring by launch list (Favorites/group/All, Recent -> channel's group, wrap); `pushRecent` cap/dedupe/replay-to-top; `parseState` garbage; `clampInt` 360/15/1440 and 180/60/600; `splitMpvArgs` reserved incl. `--no-` forms and case [D-QA-11]; `headerArgs` drops CR/LF and empty values; `buildMpvArgv` order (reserved first, headers, user args, `--`, url); `formatClock` 24 h; `formatEpgLine` expired now; `elide`; every UX 6 string present in `Copy.js` | none |
| `tests/Model.spec.qml` (exists) | keep the vectors in sync with node | none |
| `tests/Guide.spec.qml`, `tests/BarWidget.spec.qml` (lane B, M1-17) | states from fixture JSON (not configured, loading, error+cache, error no cache, empty favorites, no matches), footer hints per mode, key routing search vs list mode, `Accessible.name` composition, bar label elision at `barLabelMaxWidth`, glyph per state, click routing with a fake `bar` | `tests/fixtures/qa-*.json` may be added by lane B with the qa- prefix if needed (coordinate with QA) |

Coverage check QA runs after the merge:

```
grep -c 'def test_' tests/test_*.py
node tests/Model.test.js | grep -c '^ok'
grep -o 'qa-[a-z-]*\.\(m3u\|xml\|gz\|html\)' tests/test_*.py tests/*.js tests/*.qml | sort | uniq -c   # every fixture referenced
```

D-SINK-19 (2026-10-11), automated half, all in the gate: `node tests/Model.test.js`
runs the shared fixture `tests/fixtures/active-key.json` -- `parse` (18 cases,
also run by `tests/test_state.py::test_active_key_runs_the_shared_fixture`),
`remove` (5, also `test_remove_runs_the_shared_fixture`), `resolve` (6), `adopt`
(23 in round 2, the R1 order, both refusals, the consumed echo, the R4 EPG
rules; 25 since round 3, with `epgConsumed` pinned on every case and the
`R4/R12` flip) and `order` (8, the R5 write plan) -- plus the `D-SINK-19
migration 1..6`, `R1 (review P1)`, `R7` and `P3 sibling` checks;
`tests/Model.spec.qml` `test_guideSurfaceClearedPlaylist` carries the R2
compare inside the Qt engine. Lane A measured 16 node checks and 1 qml compare
red against the first build (f275bde) and the rest red by mutation. Round 3
(lane-key-s1, 2026-10-12; D-SRC-15, lead rulings R9-R12) adds the fixture
sections `reload` (10, `R9: reloadDisposition over every reload case`),
`flush` (8, `R11: entryFlushDisposition over every flush case`) and
`snapshot` (5, `R12: epgSnapshotAfter over every snapshot case`), three
structural pins that read `Service.qml` (`R9 (structural)`: the disposition is
asked first in `applyUserState`; `R11 (structural)`: the parked save is issued
before the entry flush is settled and `flushPendingEntry` has one call site;
`R12 (structural)`: the EPG snapshot moves after `adoptActive`), and two
python tests that run the helper's `state init` as a subprocess over a 0600
and a 0644 file (`ctime_ns` equal, then greater). Seen red by lane A: 10 node
failures over an export of lane-key-r2 (`2125 checks, 10 failure(s)`), one
python failure (`test_init_leaves_a_file_already_0600_alone`), and each
structural pin red under its own mutation (the two `onExited` lines swapped;
`flushPendingEntry` called straight from `onExited`; R9 narrowed to own-write
only; the EPG snapshot always moving). Counts on lane-key-s2: node 2125
checks, python 1056 tests, qml 78. The LIVE half is `QA-SOURCES.md`
SRC-MIG-11..17 and SRC-RM-10: the harness repair (R6) and the scenarios (R7)
landed in `scripts/dev-harness/key-scenario.sh` (lane-key-r2, then
lane-key-s2), and the rows carry the measured counts -- 49 / 0 forward on
lane-key-s2, 36 / 13 over `--baseline lane-key-r2` -- with what each segment
observes and what none does. Round 4 (lane-key-t1, 2026-10-12; lead rulings
R13-R15 after the third review graded the dirsReady-route entry write as a
P1) grows the `order` section to 13 cases (`savesInFlight`, `saveFailed`;
`R5/R13: pointerWritePlan over every \`order\` case ... the entry never gets
ahead of a state save that has not landed`, plus a full-cube check), the
`flush` section to 11 (a save in flight outranks a stale failure), adds a
service-order DRIVER that runs the shipping decisions in `Service.qml`'s
order under both host shapes with the FileView's signals queued and a
coalescing disk (seven `R13 (lag host)` / `R13 (echo host)` checks each:
the CLI set and the start-up adoption with `state.json` unwritable keep the
URL on the entry and re-adopt it on the next start; a writable disk holds the
entry until `saved` and writes it exactly once; a switch on an unwritable
disk returns `ok` and `state_write_failed` follows; a refused mirror is
logged and not signalled; a burst of coalesced writes still lands; a landed
write clears the sticky flag), `Model.countReload` checks (`R15`), and three
structural pins (`R13 (structural)`: the plan is handed the in-flight count
and the sticky failure; `R13 (structural, SR25 as amended)`: the failure is
signalled from `onSaveFailed` and never returned; `R14 (structural)`: the
ignore branch RETURNS and `saveState` parks before `dirsReady`; `R15
(structural)`: the count precedes the decision and the exit warning exists).
Seen red by lane A: the same test files over an export of lane-key-s2 read
`2146 checks, 21 failure(s)` with the P1 driver's `urlStillStored:false,
entryWrites:1 ... fileSources:2` (the loss, not a missing symbol), and each
pin red under its own one-line mutation (fifteen, listed in the lane report:
the `return` deleted, the park deleted, the in-flight branch of the plan
deleted, the failure checked before in-flight, `Model.stateSaveLanded` returning
true, the count moved after the decision, among them). Counts on lane-key-t1:
node 2146 / 0, python 1056, qml 78 (neither extended). The live half on
lane-key-t2 is SRC-MIG-16..21: 62 / 0 forward, 54 / 8 over `--baseline
lane-key-s2`, 38 / 24 over `--baseline lane-key-r2`. Round 5 (lane-key-u1,
2026-10-12; lead ruling R16 after the fourth review measured the logo toggle
-- the entry writer's second caller, which R13 had not gated -- stripping
the URL a failed state write had left on the entry as the only copy) adds
the fixture section `ownedWrite` (8 cases, the whole cube of the three
flags; `R16: ownedWriteMode over every \`ownedWrite\` case ...` and the
cube check), `R16: entryWith with keepRetired ...`, extends the
service-order driver with `setShowLogos` under both host shapes (five `R16
(lag host)` / `(echo host)` checks each: a failed state write then the
toggle keeps `playlistUrl` and names the file's own pointer at every entry
write; the patch-only write is recognised as our own under both hosts; a
parked save that fails then the toggle; a failed switch then the toggle,
and the heal with nothing outstanding; heal, failed switch, toggle), a
structural pin (`R16 (structural)`: `setShowLogos` asks the decision with
the three flags, writes `showLogos` alone with `keepRetired` on `patch`,
the funnel hands it to `Model.entryWith`, the mirror never passes it) and the
two round-4-P2 pins (`Model.persistFailureMessage` renders THE reason's sentence
over every reason `Service.qml` emits, none naming a URL, only
`persist_failed`'s naming `omarchy bar set`; the guide hands the reason
through on both surfaces). Seen red by lane A: the same test files over an
export of lane-key-t2 read `2162 checks, 17 failure(s)` -- the sixteen R16
titles with the driver's got being the loss (`urlKept:false`, the mirror
on the memory key, two records after the restart) plus the D-SINK-19
funnel pin re-levelled to `writeOwnedEntry`'s fourth parameter -- and
twelve one-decision mutations on copies of the committed tree each
reddening at least one check. Counts on lane-key-u1: node 2162 / 0 (+16),
python 1056, qml 78 (neither extended; the `ownedWrite` section has no
Python mirror, so node is its one consumer). The live half on lane-key-u2
is SRC-MIG-22 (L1/L2 inside F) and SRC-MIG-23 (the harness's own repairs):
64 / 0 forward on 63 lettered checks, 60 / 4 over `--baseline lane-key-t2`
(L1, L2, F6, F7), 54 / 10 over `--baseline lane-key-s2`, 38 / 26 over
`--baseline lane-key-r2`, 39 / 25 over `--baseline f275bde`, 58 / 6 and 59
/ 5 for the two mutation patches through `--tree`; `qa-lib-test.sh` 435 /
0 (+15); `check-tree` 11 / 0 (lane B's transcripts, 2026-10-12). Round 6
(lane-key-v1 78ff442, 2026-10-12; R16 amended after the fifth review found
the one state the three flags could not name, before the first state load)
re-levels the `ownedWrite` section to 16 cases, the cube of
`Model.ownedWriteMode`'s four inputs (`stateLoaded` first, then the three
save flags; the cube check's title now ends `the decision takes the four
inputs and nothing else`), adds four service-order driver cases under each
host shape (`R16 (lag host), round 6:` / `(echo host), round 6:` -- the
toggle BEFORE the first state load on a writable and an unwritable disk; a
patch-only toggle and then the key mirror's heal, `showLogos` staying as
toggled; a switch while the directories are not ready, then a toggle; a
switch, then a toggle before `saved`), re-levels the structural pin to the
four inputs, and adds `R16 / D-LOGO-2 (structural, round 6): writeOwnedEntry
composes the owned patch from root.settings, the own-write overlay, and
never from root.hostSettings`, the driver composing from whichever token
`Service.qml` names there. Seen red by lane A: the same test files over
lane-key-u3's code read `2171 checks, 5 failure(s)` (the fixture, the cube,
the pre-load case under both hosts, the structural pin; the driver's got is
the loss, `urlKept:false mirror:"" patched:0`), and one-decision mutations
on an export of 78ff442 read 4 red with `stateLoaded` ignored, 4 with
`savePending` ignored, 4 with `savesInFlight` ignored (the two routes the
cube alone had pinned), 7 with the funnel composing from `hostSettings`
(round 5: 0), and 1 each with the service handing `stateLoaded: true` or
omitting it. Counts on lane-key-v1: node 2171 / 0 (+9; 25 `ok   R16`
lines), python 1057 (one test from `dev`), qml 78; `qa-lib-test.sh` 441 / 0
(+6, `pointerState` now omitting a field the tree lacks, and `run.sh clean`
reporting a failed `rm`; run by the gate with `OMARCHY_IPTV_HARNESS_DIR`
unset). The live half is SRC-MIG-22 and SRC-MIG-23's round-6 brackets: 64 /
0 forward, 39 / 25 over `--baseline f275bde` with the `held` half of W1, W3,
W5, F2 and F5 now `NOFIELD` (lane A's transcripts). No lettered check
observes the pre-load toggle: no harness reaches that window. Round 7
(lane-key-w1 2ccbb74, 2026-10-12; lead ruling R17 after the sixth review
found an `epgUrl` R12 leaves on the entry with no source active stripped by
any heal write, invisible to every earlier matrix because their oracle
checked playlist inputs only) adds the fixture section `retiredKeep` (20
cases, the lead's whole cube of playlist and EPG x held and unheld x an
active record or none, run through `Model.retiredInputsToKeep`), unit pins
for `Model.entryWith` with `keep` and for `adoptPendingEpg`, six
service-order driver cases under each host shape (`R17 (lag host)` / `R17
(echo host)`: E1 no active source, the toggle, then a switch; E2 remove the
active source, a CLI `epgUrl`, the toggle; E3 a switch alone; E4 the in-app
first add; X1 and X2 the snapshot clause), two structural pins (the funnel
hands the keep decision to `Model.entryWith` on every owned write; the
switch and the probe commit adopt before their save and the mirror, the
remove does not) and the rule-15 pin `R17 / rule 15: the input audit` over
every owned write the driver makes -- 19 `ok   R17` lines, SRC-MIG-24 and
SRC-MIG-25. Seen red by lane A: the same test files over c2218f0 (lane-key-v2's
code plus `dev`) read `2191 checks, 16 failure(s)`, the driver failing on
the loss itself and the audit naming 8 lost EPG writes; eleven one-decision
mutations each red (1 to 10 checks). Counts on lane-key-w1: node 2191 / 0
(+19; read again by lane C on lane-key-w2), python 1057, qml 78;
`qa-lib-test.sh` 443 / 0 (+2, the `run.sh --host` lever; the
default-directory pin now unsets `OMARCHY_IPTV_HARNESS_DIR` itself). The
live half is key-scenario segment U, U1-U4 on the lagging fake host and
U5-U7 on the echoing one: 71 / 0 forward on 70 lettered checks, 66 / 5 over
`--baseline lane-key-v2` (U2, U3, U4, U6, U7), lane A's transcripts under
the scenario's own nested cage. The in-app add with an EPG pending is
observed in node only [round 8: live too, key-scenario A1 and A2]. Round 8
(lane-key-x1 1f8bd1b, 2026-10-12; lead ruling R18 after the seventh review
found a whitespace-wrapped input never counted as consumed, and a refused
`playlistUrl` beside a pending EPG looping the lagging host at about 3,000
entry writes a second -- neither visible to any check, because no driver
case carried a refused or a whitespace-wrapped value) adds unit pins for
the one normaliser (`Model.entryInputForm`, a 34-case agreement property
between reconcile's "fresh" and the sink's "consumed", and the
control-character sibling its search found), for the settling funnel
(`entryWriteNeeded` [deleted 2026-10-13, R22e], `Model.sameOwnWrite`) and for the add form's
guide URL winning (`adoptPendingEpg` with `formEpg`); the `retiredKeep`
fixture grows 20 -> 28 (whitespace beside a non-empty snapshot); the
service-order driver gains refused and whitespace-wrapped cases under
three wrappings and both host shapes, runs every sequence to quiescence
under a bound, fails one that does not settle (`R18c: every service-order
sequence in this file reached quiescence under the bound -- no LOOP`), and
re-runs reconcile on every own-write reassignment as QML does (rule 10: it
had done so only on a content change, which is why the loop never reached
node); and the input audit now reaches refused and superseded values and
counts them apart -- 45 `ok   R18` lines, SRC-MIG-26, SRC-MIG-27 and
SRC-MIG-28. Seen red by lane A: the same test files over lane-key-w2's code
read `2236 checks, 41 failure(s)`; one-decision mutations 19 (the raw
snapshot compare), 11 (the settling funnel removed), 7, 4, 6, 6, 1, 1 and
1. Counts on lane-key-x1: node 2236 / 0 (+45; read again by lane C on
lane-key-x2), python 1057, qml 78, `qa-lib-test.sh` 443 / 0. The live half
is key-scenario segments K (the loop window on both hosts), Z (whitespace)
and A (the in-app add through `ipc addSource`): 79 / 0 forward on 78
lettered checks, 73 / 6 over `--baseline lane-key-w2` (K1, K3, Z1, Z2, Z3,
A2), lane A's transcripts under the scenario's own nested cage. Round 9
(lane-key-y1 690a888, 2026-10-12, on the chain as it landed on the split
model; lead ruling R19 after the eighth review found R18's write skip
coming back after a publish A -> B -> A on the lagging host, and R18d
superseding a CLI `epgUrl` set after the add form was submitted -- neither
visible to any check, because no check re-set an identical value and the
oracle's supersede exemption compared the time of the supersede, not of
the inputs) adds unit pins for the guide URL held in the state
(`pendingEpgOf`, `Model.parseState` and `Model.cloneState` carrying
it), for the one by-time comparison (`epgByTime`,
`applyPendingEpg`, the add and edit stamps), for the guide URL in
force (`Model.activeEpgUrlOf`, the a12 read lifted out of `Service.qml`
under rule 12) and for the owed mirror (`Model.owedMirrorAction`,
D-SRC-18); service-order driver cases under both host shapes for A -> B ->
A on the logo, refused and EPG routes, the probe race in both orders, the
edit route in both orders, the S5 `known` branch three ways, a restart
between the input and the move in both orders, the re-set not re-stamped,
and D-SRC-18; two structural pins; an input audit that counts the state's
held guide URL as held and a supersession only by a LATER time; and the
`adopt` fixture 25 -> 32 -- 38 `ok   R19` lines, SRC-MIG-29 to SRC-MIG-32.
Seen red by lane A: the same test files over lane-key-y0's code read `2266
checks, 52 failure(s)`; sixteen one-decision mutations, fifteen red (1 to
41 checks) and one argued equivalent (the held clause in
`Model.retiredInputsToKeep`, 0); the 308258f fix's own pin 3 red before it.
Counts on lane-key-y1: node 2268 / 0 (read again by lane C on
lane-key-y2), python 1135, qml 78, `qa-lib-test.sh` 454 / 0. The live half
is key-scenario segments Y (A -> B -> A), Q (the probe race), V (the edit
route) and H (D-SRC-18 at the sink), with U, K and A re-read for the held
guide URL: 86 / 0 forward on 85 lettered checks, 74 / 12 over `--baseline
lane-key-y0` (U1, U2, U5, K1, K2, K3, Y1, Y2, Y3, Q1, V1, H1), lane A's
transcripts under the scenario's own nested cage. Round 10 (lane-key-z1,
2026-10-12; lead ruling R20 after the ninth review found the helper's own
state writer erasing the held guide URL, D-SRC-20, the lagging host's
patch-only logo write re-carrying a refused credential that then beat a
later edit, D-SINK-20, and a funnel decision -- R19a's -- with no
behavioural observer, a skip one line before the compose reading node 2268
/ 0 and live 86 / 0) makes three joins checks. One fixture,
`tests/fixtures/state-keys.json`, run by both the node suite and
`tests/test_state.py`, and a node check that every key the service can
serialise is in its vocabulary, which the helper is then tested to emit
exactly (rule 12, and rule 15 as a check rather than a search). A harness,
`tests/service-harness.js`, that compiles `Service.qml`'s own functions,
bindings and FileView handlers and runs them against fakes, so the funnel's
decisions are driven as they ship and not only mirrored by a regex-bound
driver (rule 12 again, one level up: the mirror passed with the shipping
path broken). And the defect ledger checks each `Model.` citation against
what `Model.mjs` exports (rule 13), not merely that the name is declared in
some part. 51 `ok   R20` lines; SRC-MIG-33 to SRC-MIG-36. Seen red: the same
test files over lane-key-y2's code read `2319 checks, 23 failure(s)` and
`test_state.py` 41 tests with 2 failures and 4 errors, all six new (re-run
by lane C); lane A's one-decision mutants on the tip, R20a-R20c, 1 to 13
node failures each, the helper's 1 to 4 python failures each, and the
round-9 lens's S1b and S13 now 1 and 2 where they read 0; the ledger with
its three waivers emptied, rc 1 with three problems on lane-key-z1 and rc
0 on lane-key-z2, where the documents re-cite the three names bare. Counts
on lane-key-z1: node 2319 / 0, python 1143, qml 78, `qa-lib-test.sh` 455 /
0, and the floors level with them. The live half is key-scenario Y4 (two
toggles in a row) and L2 re-wanted (the patched write keeps the only copy,
not an empty retired key): 87 / 0 forward on 86 lettered checks, 86 / 1
(Y4) over the S1b export, and 87 / 0 over `--baseline lane-key-y2`, because
no key-scenario segment observes R20a, R20b or R20c at the sink; those were
observed live only by the round-9 lens's own driver under lane A's cage,
red on lane-key-y2 and clean on lane-key-z1. Round 11 (lane-key-m1, 2026-10-13; the product owner's decision to drop
the `omarchy bar set` URL route, and lead ruling R21, which OVERTURNS R12,
R17b, R18d, R19b, R19c, R20b and R20c) DELETES rather than adds: the
pending guide URL, the set times, the active-move adoption, the add-form
supersede, the persisted consumed-input snapshot and the landed-state patch
rule, with seventeen model exports, their fixture sections and cases, the
regex-mirrored service-order driver and every R12/R17b/R18d/R19b/R19c/R20b/
R20c pin above -- those sentences are the record, and the names in them that
are no longer exports are cited without the prefix. In their place, 93
`ok   R21` lines, each calling the shipping code: the migration marker
(`Model.entryMigratedOf`, `Model.withEntryMigrated`, carried by every
reducer and by the helper on the shared fixture), the two-phase keep
(`Model.retiredInputsToKeep` over the landed marker, the rewritten
`retiredKeep` section), the session record and the notice
(`Model.entryInputsSeenAfter`, `Model.entryInputNotice`, the notification's
own replace id), and R21e through `tests/service-harness.js` under both
host shapes -- the migration on a 0.13.5-shaped install (one source, two,
a CLI-only config with no state file, an `epgUrl` with no source, a failed
write then a restart, a second URL inside the window, a TERM before the
landing, the downgrade to 0.13.6 and back), every post-marker CLI value
(valid known, valid unknown, refused, whitespace-wrapped; mid-session,
while the shell was down, twice) refused, reported once and off the stored
entry within one owned write, and the round-3-to-10 data-loss sequences
reinterpreted (a post-migration CLI URL is a REFUSED input, counted apart,
never a loss); plus a data-loss matrix at 2 operations over 11 (3 with
`IPTV_MATRIX_LEN=3`, 2,662 runs). Python: 3 new `test_state.py` tests and
the shared fixture's eight `entryMigrated` cases; `test_defect_ledger.py`
one, for the printed withdrawn-symbol waiver. Seen red by lane A (one
decision each, on a copy of the tip, of 2,261 node checks): always
migrating 64, keep after the marker 86, `entryInputSeen` never true 49, no
marker 30, the marker read off memory 2, no strip 31, no notification 48,
the keep off memory's marker 3, `cloneState` dropping the marker 6, a
truthy marker 5, the input fallback restored 1, a no-source guide URL not
reported 4, any name through the notice 1, the strip writing memory's key 1,
membership instead of the last value 3, no report loop 61; the helper
dropping the marker 3 python failures, reading it truthily 1, stamping a
set time 1; the harness section 81 of 94 red with the same test files over
lane-key-z2's code. Counts on lane-key-m1's tip 7d52e16: node 2,261 / 0
(the floor lowered from 2,319 with the reason in `scripts/check.sh`), python
1,153, `qa-lib-test.sh` 472, the key preflight 11, the text format guard 58
(61 before: three deleted copy `Text`s). The live half is key-scenario G1-G5
(the migration, the real v0.13.6 helper dropping the marker, the
re-upgrade) and X1-X6 (the refusal at the sink, the notification sink
included), with F and H driven through a migration whose write fails and U,
K, Z, A, Y2, Y3, Q and V moved to the new contract: 98 / 0 forward on 97
lettered checks, 68 / 30 over `--baseline lane-key-z2`; sources-scenario
66 / 0; logo-scenario 33 / 0 (lane A's transcripts, nested headless cages
on a private D-Bus with no service directories). TC-CFG-14 and TC-CFG-15
are the manual rows. Round 12 (lane-key-n1, 2026-10-13; lead ruling R22,
after the round-11 data-loss lens found a migrated install's `state.json`
that could not be read at the start written over with an empty state) adds
the load classification, called for real: `R22a: FileViewError's order`
(the enum read from the installed qmltypes), `R22a: stateLoadKind ...`,
`R22a: stateInitFound ...`, `R22a: stateLoadDecision ...`, `R22a:
stateWriteGate ...` and `R22a: stateUnreadableNotice ...`; the R16 and R14
structural pins widened to the five-input `ownedWriteMode` and to
`saveState` asking `Model.stateWriteGate` first; and, through
`tests/service-harness.js` under both host shapes, every fault -- a 0000
file, a 0000 directory, a foreign-owned file or directory, a directory at
the path, garbage, an empty file -- at a migrated start and at a
0.13.x-shaped start, in three orders of the init against the load, plus
the same faults mid-session, a probe that ends in the no-write mode, a
migration whose write failed followed by a reload that is not a state, a
fresh install whose init failed, and the real `startCacheLayout` on a fresh
install and on the unreadable-directory start (`R22a (...)`, `R22b
(...)`; the harness delivers each load through `stateFile`'s own handlers
with the measured error numbers and RUNS the cache layout, which it used to
stub). R22e's absence pin, and R22c's `tests/test_shipped_copy.py` (every
string literal in every shipped code file, 3 tests). Python: 12
`test_state.py` tests in `StateNeverWrittenUnreadTest` (the init's `found`
per fault and that it never rewrites a file it could not parse, by bytes,
mtime, ctime and inode; every verb refusing each fault; a missing file still
fresh; the D-ID-1 remap writing nothing), and 2 in `test_defect_ledger.py`
for R22d. Seen red by lane A, one decision at a time on an export of the
tip: 17 node mutants from 1 to 54 failures each (three that survived the
first pass got pins in 4fdb37c and then read 4, 2 and 2), 4 python mutants
(8 to 46 failing subtests), the ledger's unused-waiver failure removed 1;
and the whole suite pointed at lane-key-m2's code reads 2,354 checks, 86
failures -- exactly the 86 R22 harness pins, every older check green there.
Counts on lane-key-n1's tip 6172d8a: node 2,354 / 0, python 1,170,
`qa-lib-test.sh` 472, the key preflight 11. The live half is key-scenario
B1-B8: 106 / 0 forward on 105 lettered checks and 97 / 9 over `--baseline
lane-key-m2` (B1-B8, and N1 for its new field only); sources-scenario
66 / 0; logo-scenario 33 / 0 (lane A's transcripts, under the same cage and
private bus). TC-CFG-16 and TC-FAV-09 are the manual rows.

Round 13 (lane-key-p1, 2026-10-13; lead ruling R23, after the round-12
lenses: the notice's re-arm checked by nothing, a FIFO at `state.json`
hanging the init and every verb, the init unbounded, a directory at the path
chmod-ed 0600, the logo refusal advising `omarchy bar set`, a no-write start
drawing the first-run form, and two mislabelled instruments). Node, +18:
`R23a (...)`, two no-write episodes in one session through
`tests/service-harness.js`, the second told and an in-app favourite in it
refused and told (4); `R23c (...)`, the init's watchdog armed, a timeout at
each fault blocking as `init-timeout` and told once with nothing written, and
the loaded-then-timeout control, per host (8), and the model units
`R23c: stateInitFound ...` and `R23c: stateUnreadableNotice("init-timeout")
...` (2); `R23e: guideSurface ...`, `R23e: firstRunAllowed ...`, `R23e: the
Esc / o return from Sources ...` (3); `R23f: refusalMessage ...` (1). The
harness gains `ownEcho` ("load" | "none", R23g: the real FileView was
measured delivering its own-save echo only sometimes), and `scripts/check.sh`
runs the whole node suite a second time with it off. Python, +10:
`StateNeverBlocksTest`, the real helper as a subprocess under a timeout over
a FIFO, a socket, a directory, a file where the state directory should be and
a symlink to a 0000 file. Seen red: on lane-key-n2's helper with a 3 s
timeout, 9 of 10 (30 failing subtests); on lane-key-n2's `Service.qml` and
model, 6 of 2,372 node checks (the R23c harness pins; the control green); one
decision at a time on an export, P1-P4 in the helper 11, 16, 3 and 1 of 62
`test_state` tests, N2-N11 in the model and service 5, 5, 2, 4, 4, 1, 1, 1, 1
and 1 of 2,372; P5, the init's `found` override from the descriptor, 0 --
equivalent but for a rename race, kept and raised. The R23a re-arm cannot be
seen red on lane-key-n2 (the line existed; only its check did not), so it is
seen red through `scripts/dev-harness/spikes/key-mutations/
r23a-no-rearm.patch`: node 4 of 2,358 in both echo modes. The `ownEcho:
"none"` run has NOT been seen red -- no pin fails without the echo, which is
R23g's finding, not a proven check. Counts on lane-key-p1's tip bb5b2de: node
2,372 / 0 (and 2,372 / 0 with the echo off), python 1,180, `qa-lib-test.sh`
472, the key preflight 11. The live half is key-scenario B9-B14: 112 / 0
forward on 111 lettered checks (`key-20261014-043943-514380`), 107 / 5 over
`--baseline lane-key-n2` (B10-B14; `key-20261014-044420-538071`), 111 / 1
with each of `r23a-no-rearm.patch` (B9 `told:1/1`) and
`r23e-editable-field.patch` (B13 `editable:2`, the control that shows the
new `ipc editable` census can count); sources-scenario 66 / 0 under an outer
headless cage on a private bus; logo-scenario 33 / 0. TC-CFG-17 to 19 and
US5 step 7 are the manual rows. The ledger's withdrawn-symbol waivers went
to 0 with their last citations (R23i, lane-key-p2): `test_defect_ledger.py`'s
census test now asserts the empty set and was red against the script with
the three waivers.

Round 14 (lane-key-q1, 2026-10-14; lead ruling R24, after the round-13
lenses: a foreign write ignored and then written over while a save was held
(D-SRC-22), a dangling symlink at `state.json` read as absent and replaced
(D-SRC-23), the documents' wrong reload condition (D-DOC-8), and seven P3s).
Node, +87 (2,372 -> 2,459, the same with the own echo off): the merge's 34
fixture cases and its identity, `sameState` and conflict-line checks; R24a
through `tests/service-harness.js` in 16 modes; R24b, R24c, R24d, R24e and
R24g harness pins; the R24b and R24f model units; and the structural pins
the round re-pointed. The harness double now models the measured FileView
(a view first loaded over a missing directory is unarmed until `reload()`;
rule 10) and a process that ignores TERM. Python, +14 (1,180 -> 1,194):
`StateSymlinkTest`, `StateInitDeadlineTest` and the not-a-dir verb test in
`tests/test_state.py`, the real helper as a subprocess; and
`PrivateBusIsolatesHome` in `tests/test_harness_home.py` (F-HARNESS-25).
Seen red: the suite on a `git archive dev` export reads 85 of 2,459 (every
new check but R24g's four, the D-SRC-15 base-reload control and the R24c
double check, which dev passes and which were seen red by mutation instead:
`r24g-no-kill.patch` 4, `matchesBase: false` 8, an always-armed double 2);
the python tests against dev's helper 9 of 14 red and 5 controls green;
`PrivateBusIsolatesHome` 2 of 2. One bookkeeping check, "the fixture covers
every field rule", was not seen red (it reddens only if fixture cases are
deleted). Counts on lane-key-q1's tip c6315d1: node 2,459 / 0 both ways,
python 1,194, `qa-lib-test.sh` 472, the key preflight 11, qml spec 78. The
live half is key-scenario B15-B18: 116 / 0 forward on 115 lettered checks
(`key-20261014-095236-969838`, 342.5 s), 113 / 3 over `--baseline dev`
(B15, B16, B18; `key-20261014-095838-996891`), 115 / 1 with
`r24g-no-kill.patch` (B17; `key-20261014-100528-1027361`); sources-scenario
66 / 0, logo-scenario 33 / 0, each under a nested headless cage on a private
bus. TC-CFG-20 to 24 are the rows. No manual row is added: TC-CFG-21's
symlink cases can be run by hand on a scratch `--state-dir` exactly as
`tests/test_state.py` runs them, and nothing in this round was looked at on a
display.

Round 15 (lane-key-k1, 2026-10-14; lead ruling R25, after the round-14
lenses: a backup of the plugin's own file ignored on its way back
(D-SRC-30), a merge cutting the in-app additions at a cap silently
(D-SRC-31), a dangling link at the state FOLDER (D-SRC-32), two merge
decisions no check observed (F-HARNESS-26), a symlinked `state.json` that a
replacing tool leaves unwatched, stated and not fixed (D-SRC-29), and the
P3s and false statements the 0.14.0 bar forbids). Node, +43 (2,459 ->
2,502, the same with the own echo off): 36 through `tests/service-harness.js`
(on both hosts and both echo modes: R25a x4, R25d a5 and a7, R25c x1, R25b
x2), 2 for the D-DOC-11 double, 5 model pins (R25c, D-SRC-38 x2, R25b x2).
The double models what was measured: a dangling link whose target's folder
exists does NOT fail the view's save (it creates the target), one into a
missing folder does, and so does a link at the state folder (rule 10).
Python, +8 (1,194 -> 1,202): `StateFolderLinkTest` 5, `FolderLinkSiblingsTest`
1, the F-HARNESS-27 alarm 1, the logo folder link 1. Seen red: the tip's
`tests/` on a `git archive dev` export reads 36 of 2,502 in both echo
modes, and the double pin 2 against dev's double; the a5, a7, R25a, R25b and
d3 mutation patches under `spikes/key-mutations/` read 4 / 4, 8 / 8, 16 /
16 and 13 / 11, 8 / 8, 10 / 10 (echo load / none); python against dev's
helper `test_state` 13 failures and 5 errors, `test_logos` 1 error; the
F-HARNESS-27 pin red with the disarm deleted. The live half is key-scenario
B19-B22: 120 / 0 forward on 119 lettered checks (`key-20261014-153026-1723779`,
385.9 s), 118 / 2 over `--baseline dev` (B20, B22;
`key-20261014-144201-1513141`), 119 / 1 with `r25d-a5-base-not-moved.patch`
(B19), 110 / 10 with `r25d-no-reload-on-change.patch` (B21 among every
segment that needs a reload); sources-scenario 66 / 0 and logo-scenario 33
/ 0, each under a nested headless cage on a private bus. TC-CFG-25 to 29 are
the rows; TC-CFG-21 gains a manual check of the link's limit, the one thing
this round documents rather than fixes. Nothing in this round was looked at
on a display.

Round 16 (lane-clean-a1, 2026-10-16; lead ruling R26, after phase 1 of the
clean-up: lane S measured D-SINK-21 real -- a state-folder link re-pointed
at an empty folder, then one in-app change, and the save CREATED a 0644
`state.json` holding the session's sources and a credentialed URL, with
nothing told; lane W measured what the FileView does to a replaced or
re-pointed link and found D-SRC-46, a write issued inside `stateFile`'s own
`onLoaded` that never raises `saved`; lane H repaired the two always-red
chno scenarios, F-HARNESS-21 and F-HARNESS-22, and found F-HARNESS-30, a
TERM-only player reap that left six players spinning). Node, +59 (2,502 ->
2,561, the same with the own echo off): the R26 pins, the plan and the
recheck tables, the R26b structural pin, and the re-levelled checks
(R11, R13, R14 / R22a, R15, R21e, R24a IN FLIGHT, R25a, R25b IN FLIGHT,
R25d a7: each with a sentence naming why its premise moved). The double
models the measured FileView (R26c, F-HARNESS-29). Python unchanged
(1,229). `qa-lib-test.sh` 472 -> 500 (lane H: `qa_served_fixture`,
`qa_listener_owned`, the R12 needle, `qa_reap_players`) -> 505 (lane A:
the `run.sh reap` pin, the patch counts). Seen red: the tip's tests over
dev 1c88877's `Service.qml` read 64 of 2,561; dev's own suite with only
the new double swapped in, 12 of 2,502; the four R26 mutation patches under
`spikes/key-mutations/` 36, 23 / 21 and 4 in node, and live 122 / 7, 128 /
1, 128 / 1 and 126 / 3; and `run.sh reap` against a TERM-ignoring stand-in
player, alive and silent on dev, ended with `sending KILL` on the tip. The
live half is key-scenario B23-B31: 129 / 0 forward on 128 lettered checks
(`key-20261016-084228-582473`), 120 / 9 over `--baseline 1c88877`
(B23-B31); chno 46 / 0 and chno-entry 78 / 0 (lane H, three runs each on
two trees), sources 66 / 0, logo 33 / 0, each under a nested headless cage
on a private bus. player-scenario P1-P12 and rewind R13 / R14 read the real
compositor and a seat keyboard and cannot run in a cage; they read the
same reds on dev under the same rig. TC-CFG-30 to 32 are the rows;
TC-CFG-21's manual check of the link's limit is reversed (the edit is now
kept). The transcripts are in lane A's session scratch directory, not the
tree. Nothing in this round was looked at on a display.

Round 16's merge fixes (lane-clean-f1, 2026-10-16, after the phase-2
reviews). F-HARNESS-31: the double dropped no reload that a foreign change
raises while one of our writes is in flight, which the measured FileView
does (30 of 30); it does now, and the sixteen pins that passed only on the
forgiving shape -- R24a IN FLIGHT, R25d a7, R25b's in-flight saved search,
R26b's census, each x 4 -- are re-levelled to the same-instant loss, each
with a sentence naming why its premise changed and what still observes the
concern (none deleted). Node 2,561 -> 2,565 (both echo modes): the read's
2 s bound, observed through the Timer the tree declares (F4). Mutations:
the two new watchdog patches 4 / 4 each; `r25d-a7-no-inflight-half.patch`
8 -> 0 (no node pin reaches the half it deletes any more; the clause is
kept, the question is the lead's), `r25a-clear-every-saved` 14 / 12 -> 6 /
4, `r25b-silent-drop` 8 -> 4, `r26b-no-defer` 23 / 21 -> 19 / 17;
`d3-save-parked` 162 -> 170 and `r14-no-return` 145 -> 149 (the re-levelled
a7 pins go red on both, and the bound pin on d3), `r26a-no-read` 36 -> 40
(the bound pin); the other eight unchanged. `qa-lib-test.sh` 505 unchanged
(the patch-apply pin and the folder count re-counted to seventeen).

Round 17 (lane-sweep-a1, 2026-10-20; lead ruling R27 over D-SINK-22,
D-SRC-41, -42, -44, -48, -50, -51 and D-PERF-1). Node 2,572 -> 2,634 in both
echo modes: the R27a-e pins (TC-CFG-33 to 35) and the re-levelled burst
pins of R13 and R25a (no burst forms any more: no write is issued while
another is out). Python 1,293 and the qml spec 78 unchanged.
`qa-lib-test.sh` 513 -> 515. The double drops the service's own `reload()`
while one of our writes is queued, as the view does. Seen red: the tip's
node tests over 6f1d176 read 71 of 2,626 in each echo mode; one-decision
mutations of the tree from 4 to 68 each. Live, each under a nested headless
cage on a private bus: key-scenario 134 / 0 forward
(`key-20261020-131102-1636986`), 130 / 5 over `--baseline 6f1d176` with the
134 lettered checks of that day (B32, B33, B35, B36, B37; B34, a burst
check green on both trees, has since been dropped and is printed as a
measurement); sources 66 / 0, logo 33 / 0; open-scenario 21 / 0 (TC-CFG-36,
PERF-02's note). R27b measured, built nothing (0 of 608). The transcripts
are in lane A's session scratch directory, not the tree. Nothing in this
round was looked at on a display.

Round 18 (lane-sweep-a2 2bed7c2, 2026-10-20; lead ruling R28 after round
17's reviews, two P1 data losses). Node 2,634 -> 2,692 in both echo modes:
the R28a pins (TC-CFG-37), R28b's (TC-CFG-38), R28c's three resets, and
R28e's copy and ways-back pins (TC-CFG-34, 35). Python 1,293 and the qml
spec 78 unchanged; `qa-lib-test.sh` 515 unchanged; open preflight 9 -> 16
(TC-CFG-36). Seen red: the final node suite over lane-sweep-c1 read 66 of
2,692 in each echo mode, over 6f1d176 112; one-decision mutations of the
tree from 1 to 45 each (the ARCHITECTURE-SOURCES round-18 rulings list
them). Live, each under a nested headless cage on a private bus:
key-scenario 136 / 0 forward (`key-20261020-155757-2060758`), 133 / 3 over
`--baseline 843ae87` (B32, B38, B39) and 129 / 7 over `--baseline 6f1d176`
(B32, B33, B35-B39); sources 66 / 0; open-scenario 30 / 0, and 28 / 2
under `late-fill.patch`. The transcripts are in lane A2's session scratch
directory, not the tree. Nothing in this round was looked at on a display.

Round 19 (lane-sweep-a3 50d440c, 2026-10-20; lead ruling R29 after round
18's reviews, which withdraws R27a's window-(c) answer and all of R28a's
stall machinery). Node 2,692 -> 2,651 -> 2,664 in both echo modes: R28a's
pins out (2 model, 9 x 4 harness) and R28c's read-state reset (1 x 4), one
withdrawal pin in, R26a's two bound pins back to 6f1d176's answer (TC-CFG-33,
TC-CFG-37 as re-written); then R29d's three harness pins (3 x 4) and its
notice pin (TC-CFG-39). Python 1,293, the qml spec 78 and `qa-lib-test.sh`
515 unchanged; open preflight 16 -> 19 (TC-CFG-36), key preflight 11 -> 12
(S4: `init_pids` answers this run's own `--state-dir` only). Seen red: the
final node suite over lane-sweep-c2 read 33 of 2,664 in each echo mode, over
6f1d176 99. Live, each under a nested headless cage on a private bus:
key-scenario 138 / 0 forward (`key-20261020-184353-2546836`), 134 / 4 over
`--baseline lane-sweep-c2` (K1..K3, B40) and 127 / 11 over `--baseline
6f1d176`; sources 66 / 0; open-scenario 33 / 0, and 31 / 2 under
`opacity-fade.patch`; the slow-file rig as TC-CFG-37 says. The transcripts
are in lane A3's session scratch directory, not the tree. Nothing in this
round was looked at on a display.

## 3. Security test cases (ARCHITECTURE.md section 8, PLAN gate G4)

Run from the repo root (static) and on the live shell (dynamic). Expected
output is empty unless stated.

| ID | Standard | How | Expected |
|---|---|---|---|
| SEC-01 | 8.1 argv only, no shell strings | A `grep -rnE 'bash -c|sh -c|shell=True|os\.system|subprocess\.(call|run|Popen)\([^\[]|execDetached\("|command: "|\beval\(' --include='*.qml' --include='*.js' --include='*.py' --include='omarchy-iptv' . \| grep -v '^./tests/' \| grep -v '^./docs/'` | nothing (the helper is invoked with `["python3", helperPath, ...]`, mpv with `Model.buildMpvArgv`, notifications with an array) |
| SEC-02 | 8.6 no sudo/pkexec | A `grep -rnE 'sudo|pkexec|doas' --include='*.qml' --include='*.js' --include='*.py' --include='omarchy-iptv' . \| grep -v '^./tests/' \| grep -v '^./docs/'` | nothing |
| SEC-03 | 8.2 header injection with CR/LF | A* `qa-headers.m3u` (`cr.test`, `kodicrlf.test`); A `Model.test.js` (`headerArgs` drops values containing `\r`/`\n`); M TC-PLAY-08 | `channels.json` values contain no CR/LF (bare CR -> space, `%0D%0A` -> spaces); mpv argv shows one `--user-agent=` item |
| SEC-04 | 8.2 header names validated | A* `qa-headers.m3u` (`Bad%0AName` dropped, warning `dropped header with unsafe name for ...`) | as stated |
| SEC-05 | 8.3 stream scheme allow-list | A* `qa-schemes.m3u` | allowed: http https rtsp udp rtp rtmp rtmps mms mmsh srt, uppercase scheme, padded line, option-looking suffix inside the line; dropped and counted: file, bare path, `~`, relative, ftp, plugin, javascript, data, `--script=`, `--`, edl, mf, av, lavf, fd, memory, ytdl, smb, dvd, null, protocol-relative; `http://` with no host must be dropped too (D-QA-07) |
| SEC-06 | 8.2 no URL on any command line; option-looking lines never reach mpv | A `tests/test_player.py` argv tests against `tests/fixtures/player-argv.json`; M `ps -o args= -p $(pgrep -f wayland-app-id=omarchy-iptv)` | every mpv argv token after index 0 begins with `--`, there is no trailing `--` and no URL anywhere on the command line (observed PLY-SEC-01; the pre-M2-02 expectation of `--` then the URL is inverted by S-03; corrected 2026-09-25, D-QA-19) |
| SEC-07 | 8.7, R12 URL redaction at every sink | A: enumerate sinks with `grep -nE 'console\.(log|warn|error|info)|notify\(|showTooltip|tooltipText|statusLine|lastError|stderr|stdout|emit\(|sys\.stderr' Service.qml Guide.qml BarWidget.qml bin/omarchy-iptv` and check each argument cannot carry a URL (current sinks: `Service.qml` `notify()` body from `mpvStderrTail` [D-QA-01], `lastError` -> `Guide.statusLine` and IPC `status` [D-QA-01, D-QA-15], `console.warn("omarchy-iptv playlist:", stderr)` (helper stderr carries host only, but local paths [D-QA-12]), `BarWidget.tooltip` (`error.message`), channel `name` [D-QA-02]); M 5.9: `grep -nE '(https?|rtsp|rtmp)://[^ ]*[@?]|password=|username=' journal.txt qs-log.txt` and the notification history (`omarchy-shell notifications showHistory`) after TC-PLAY-05 with a credentialed dead URL from `qa-attrs.m3u` (`http://user:secret@stream.example.test/...`) | no match anywhere |
| SEC-08 | 8.4 local source path rules | A* `tests/test_helper.py`: `/proc/self/environ` -> `unsafe_path`, `/dev/zero` -> `too_large` (reads at most 64 MB + 1), `/sys/...` -> `unsafe_path`; M `omarchy bar set ... playlistUrl /proc/self/environ` | error rendered, no traceback, no hang **[Amended 2026-10-13, D-SINK-19 round 11: the manual half goes through the Sources form (`a`, `/proc/self/environ` in `Playlist`), which refuses it with the `unsafe_path` sentence; `omarchy bar set` is refused before any validation after the migration (TC-CFG-14).]** |
| SEC-09 | 8.4 symlink to a forbidden path | A* `ln -s /proc/self/environ $tmp/list.m3u` -> `unsafe_path` (realpath check) | as stated |
| SEC-10 | 8.4 `file:///etc/passwd` as the *source* | A `qa-schemes.m3u` covers the *stream* case; as a source it is the user's own readable file: parses to 0 channels -> `empty_playlist` | not a defect; document |
| SEC-11 | 8.4 size caps | A* sparse 65 MB file -> `too_large` in well under a second (`truncate -s 65M`); gzip bomb: `python3 -c "import gzip,sys; sys.stdout.buffer.write(gzip.compress(b'#EXTM3U\n'+b'\0'*(100<<20)))" > bomb.m3u.gz` (about 100 KB) as playlist and as EPG source -> `too_large`, RSS stays under 300 MB (D-QA-06 until fixed) | as stated |
| SEC-12 | 8.4 source schemes | A `tests/test_playlist.py::SourceTest::test_refuses_other_schemes` (exists): ftp, relative, javascript, empty; add `data:`, `//host/x` (protocol-relative), `FILE:///etc/hosts` (uppercase scheme is accepted today; decide and pin) | refused or pinned |
| SEC-13 | 8.9, section 6 reserved `mpvArgs` | A `Model.test.js` (exists); extend: `--INPUT-IPC-SERVER=x` [D-QA-11], `--no-title`, `--script-opts=x` allowed, `--include=/path` (loads an mpv config that can override reserved options; user's own trust level, document as a known limitation or add to the reserved list) | reserved names dropped with one console warning |
| SEC-14 | 8.5 file modes and locations | M 5.7 `stat -c '%a %n'` | `~/.cache/omarchy-iptv` 700, files 600; `~/.local/state/omarchy-iptv` 700, `state.json` 600; `/run/user/1000/omarchy-iptv` 700, `mpv.sock` owned by the user; nothing under the plugin dir |
| SEC-15 | 8.5 no writes inside the plugin directory | M 5.7 `find` | nothing |
| SEC-16 | 8.6 no symlinks in the repo | A `omarchy plugin validate .`; `find . -name .git -prune -o -type l -print` | nothing |
| SEC-17 | 8.8 IPC acts only on cached ids | M 5.8: `omarchy-shell io.github.rmcdavid.iptv play 'http://evil.example.test/x'` and `play '--script=/tmp/x'` | reply `unknown`, nothing launched |
| SEC-18 | 8.6 no network from QML | A `grep -rnE 'XMLHttpRequest|fetch\(|Qt\.openUrlExternally|WebSocket' *.qml Model.js` | nothing |
| SEC-19 | XMLTV entity expansion / external entities | A* small XML with a 10x10 nested entity (`<!ENTITY a "aaaa..."><!ENTITY b "&a;&a;...">`) and an external entity `<!ENTITY x SYSTEM "file:///etc/passwd">` as EPG source | parse error or bounded memory; external entity never read (`xml.etree` does not resolve them); `bad_xml`/`network` style error surfaced |
| SEC-20 | 8.4 redirects | A* mock `http://` source that redirects to `file:///etc/passwd` and to `ftp://` | `urllib` refuses non-http redirects -> `network` error; https -> http downgrade is allowed by urllib (document) |
| SEC-21 | credentials in `channels.json` (section 6 caveat) | M 5.7 | file 0600 in a 0700 dir; README settings section warns that `shell.json` and the cache contain the provider credentials **[Amended 2026-10-11, D-SINK-19: the README now counts two files the plugin owns (`state.json`, the cache) and one it does not own that a URL only passes through (`shell.json`, from the user's own `omarchy bar set` or an install upgrading into this version, until the plugin's next write); `grep -c playlistUrl ~/.config/omarchy/shell.json` is 0 after any owned write, and the sentence "Nothing else ... writes either URL anywhere but the two files of its own" is checked against the count in the same section]** |
| SEC-22 | 8.12 a logo's declared dimensions are bounded (D-LOGO-11) | A `tests/test_logo_dimensions.py` calls the shipping `logo_dimensions` / `logo_within_bounds` / `logo_file_within_bounds` / `write_logo` / `cmd_logos` over `tests/fixtures/logo-dimensions.json` (56 header cases at integration (55 at lane commit ddc0a7b, up from 44 at 995c6be): all four types, the boundary shapes 4096x1024, 4097x1024, 2048x2049 and their transposes, an EXIF thumbnail before the real frame header, a 64x65535 column, a two-frame GIF); M section 3.2 observes both sinks through `scripts/dev-harness/logo-scenario.sh` | every over-bound or unreadable header refused with `logo_dimensions` and nothing created on disk; a cached file that is over the bound, unreadable, not one of the four types, or over the byte cap with its header past the first read, swept and never announced, past the per-run fetch cap included; the within-bound control reaches `Image.Ready` at control memory |
| SEC-23 | 8.13 the shell never subscribes to the clipboard (D-CLIP-1) | A `node tests/Model.test.js` (the D-CLIP-1 block: `editInsert` / `editDelete` / `wordBoundary` over `tests/fixtures/form-edit.js`, 115 checks at lane commit 44b250b, +48 at 51866a3 for R8: `clipboardArgv`, 17 `parseClipboardReply` vectors from `tests/fixtures/clipboard.json`, `clipboardCut`, `editRangeFor`, `cutApplies`), `tests/test_clipboard.py` (20 tests at 51866a3: the helper's `clipboard` verb run as a subprocess against a stub `wl-paste` on PATH that streams 4 MiB, hangs, ignores SIGTERM, fails or is absent -- the byte cap, the deadline, the kill grace, the character-boundary cut, an empty stderr and a reaped child are each observed, never grepped) and `qmltestrunner tests/Model.spec.qml` (`test_formEditBoundaries`, `test_formEditDeletes`, `test_formEditCap`, `test_readOnlyFieldPremises`, `test_passwordCutIsNativelyANoOp`, which re-measure Qt's word boundary and pin that a read-only input never edits itself); M section 3.3 observes the sink | the model edits agree with a real `TextInput` position by position; the form field reads `readOnly: true` and Qt draws no caret on it; under a foreign 100 MB offer inside a nested compositor the shell's RSS and an IPC round-trip are unchanged on the fixed tree and the read shows on `--baseline d55149b` |
| SEC-24 | 8.14 every text a channel keeps is bounded by a constant (D-M3U-1) | A `tests/test_m3u_bounds.py` calls the shipping `parse_m3u` over a few KB per field, never a large payload: a ~4 KB `#EXTGRP` followed by six short entries (every channel's `group` 128 and `searchKey` at most 1,025 code points for that ASCII line, the group a prefix of the line, one warning), a 4 KB `group-title`, 60 groups in one value (16 kept), a 4 KB title and `tvg-name` (cut at 512), a 4 KB `tvg-id` (dropped, not cut), a 4 KB `#EXTVLCOPT` user agent (dropped; the entries after it carry no headers or options), a 4 KB `#KODIPROP` header value, 40 options (16 kept), a 4 KB stream URL (entry skipped), logo, channel number and `url-tvg` (dropped), 60 per-channel warnings (20 listed and a count), every field long at once (the channel's JSON under the sum of the caps); `#EXTGRP` still persists to the next one; no cap fires on any of the 23 playlist fixtures; `parse_m3u` over lines and over the whole text agree on every fixture and on invalid UTF-8, a BOM, CRLF and gzip | each channel comes out within its caps, each kind counted once in `warnings`; seen red against 0.14.2 (85206f2) |
| SEC-25 | 8.15 the parsing verbs run under a memory limit (D-M3U-1) | A `tests/test_m3u_bounds.py` runs the helper as a SUBPROCESS (the limit is the process's; a helper imported by a test sets none): `OMARCHY_IPTV_MEMORY_LIMIT_MB=8` on `playlist` over a credentialed loopback URL and on `epg` over `epg-basic.xml`, and 24 on a 10,000-entry playlist (about 0.9 MB) which the default then admits; the verb run through `runpy` as the program leaves `RLIMIT_DATA` at 512 MiB; the variable cannot raise it; a `MemoryError` placed inside `parse_m3u` / `parse_xmltv` is one sentence in process; a local source parses under an outside 75 MiB address-space limit; the prebuilt TLS context verifies, and a self-signed server is refused with no request sent. M the real service under a nested cage on a private bus: a 10,000-channel source loads, and with the variable at 24 the service reports `Source too large` | exit 1, one JSON line, code `too_large`, a message naming the host only, no `Traceback` on stderr, no credential on either stream, no `channels.json` or `epg-window.txt` written; seen red against 0.14.2 (85206f2) |

### 3.1 TLS verification on the player (D-SINK-13)

What is under test, and why the obvious test is not one. The standard is
`ARCHITECTURE.md` section 8.10 and the specification is
`ARCHITECTURE-PLAYER.md` 4.15: five layers, of which the base-argv token is the
one a test naturally reaches for and the one that proves least. Asserting that
`--tls-verify=yes` appears somewhere in the argv array is a restatement of the
line that was written to contain it -- engineering rule 14 -- and it stays green
against the three bypasses the lead measured, all of which PLAY a self-signed
certificate while that assertion passes. A plan for this feature has to ask two
different questions, and neither of them is "is the token there".

**Question one: does the composition still end with it?** This is pure logic and
belongs with the existing argv vectors, called rather than mirrored (rule 12:
one fixture, both implementations). The cases that matter are the composed argv
with hostile user `mpvArgs` -- `--tls-verify=no`, `--no-tls-verify`,
`--profile=whatever`, and a legitimate `--tls-ca-file=/path` -- where what is
asserted is the LAST element of the result, plus the reserved-set behaviour for
the two direct spellings and the warning the user gets for them, plus the
mirrors agreeing. A case worth having for its own sake: a bare `--` is rejected
by the argument filter, so nothing can turn the trailing token into a filename;
the lead measured that by calling `filter_mpv_args`, and a vector pins it.

**Question two: does a real TLS peer refuse?** That is the sink, and only
observing it answers 8.10. The shape is a local TLS server, one certificate
self-signed and one signed by a generated CA, and a player that is expected to
refuse the first, to refuse it still when the user's `mpvArgs` try all three
bypasses, and to play the second when the user names that CA with
`--tls-ca-file`. A control run against a public host with verification on and
with no TLS options at all must fail identically, which is what makes the fix
safe to ship rather than merely strict. Per engineering rule 11 the same checks
are run with a baseline flag against the pre-fix ref and must go RED there; a
TLS scenario that has never been seen failing proves nothing, and this is the
one feature where it can fail green in three separate ways.

Ownership and evidence. The harness scenario and its file name are the harness
lane's to name and to confirm here -- do not cite a path for it from this
document until that lane has landed one, because a scenario joined to a plan by
a name nobody checked is engineering rule 13's failure mode. The lead's own
measurements, which the two questions above are derived from and which no lane
may restate as its own work, are the D-SINK-13 row in `docs/STATUS.md` and the
write-up in `docs/QA-RESULTS.md`. Anything that needs a real player window, a
running shell, or the live install belongs to whoever holds the display.

### 3.2 A provider logo's declared dimensions (D-LOGO-11)

What is under test. The standard is `ARCHITECTURE.md` section 8.12 and the
ruling is `RULING-LOGOS.md` rule 7: a logo is refused at `write_logo` when its
header declares a side over 4096 px or more than 4,194,304 px, or when the
header cannot be read, for all four allowed types; and the cached-file branch
of `logos --fetch` proves a file's header before announcing its name, removing
what fails. The obvious test is not one, for the reason 3.1 gives: asserting
that `MAX_LOGO_SIDE` is 4096 restates the line written to contain it. Nor is
the byte cap a proxy -- the lead's table has 304 bytes costing 840 MB -- so a
plan that checked file sizes would stay green against the finding.

**Question one: does the gate refuse on the header alone?** Pure logic,
called rather than mirrored. `tests/test_logo_dimensions.py` runs the 56 header cases of `tests/fixtures/logo-dimensions.json` through the shipping
parsers and the shipping predicate; the cases that carry the weight are the
boundary shapes a wrong comparison operator gets wrong (4096x1024 exactly on
both bounds, 4097x1024 one pixel over one bound, 2048x2049 inside both side
checks and over the area), the unreadable headers that are refusals rather
than passes, and `write_logo` on a bomb creating nothing on disk, not even
the directory. Fifteen mutations of the shipping functions each redden at
least one test (the fb2acdc commit message carries the counts; python
986 -> 1015).

**Question two: does the shipping path leave the shell at control memory?**
That is the sink, and only observing it answers 8.12. What the harness
scenario must observe, through the real `logos --fetch` subprocess and a
playlist whose logos are served by a local TLS server (logos are `https` only
by rule 3, so the server the TLS scenario already builds is the shape):

- The bombs are refused: over-bound headers of all four types, rewritten and
  honestly huge, counted under `reasons.logo_dimensions` in the summary, with
  none of their names in `names` and no file of theirs under `logos/`.
- A bomb seeded into the cache before the run, under the name the helper
  would give it, is swept: `swept` counts it, the file is gone afterwards, and
  its name is absent from `names`. Observed by this section's author on
  2026-10-11 through the subprocess at 3c8cd65 (`swept: 1`, `names: []`, zero
  files) and at the shipped 159da94 (`cached: 1`, the name announced, the file
  still there), which is the RED the baseline arm must reproduce.
- The positive control is within the bound, is fetched, is announced, and
  reaches `Image.Ready` through an `Image` declared as `Guide.qml` declares
  the row slot, at control memory. Peak RSS is read as `ru_maxrss` of the Qt
  process, and the cap wraps the Qt process ONLY: a cap around the reporter
  takes the measurement with it when a bomb is refused or killed. The cap is
  an ADDRESS-SPACE rlimit of 2.5 GB on the qml process alone (util-linux
  `prlimit --as=2500000000 -- env QT_QPA_PLATFORM=offscreen
  /usr/lib/qt6/bin/qml <probe>`, which sets the limit on itself and execs
  the runtime in place), and NOT a user-session memory scope, which is what
  the lead's first measurement used: the marketplace capability scan
  (`scripts/check-marketplace-capabilities.py`, no allowlist by design)
  reads the scope tool's name as a service-management capability in any command line of a tracked .sh/.py/.js/.qml file, or a shell fence of the root README (comment-only lines are skipped, as upstream skips them, and no other .md file is read), and under the rlimit an over-bound decode is
  a clean allocator refusal (`Image.Error`, exit 1) where the scope killed
  the process with the figure unmeasured.
- The `--baseline 159da94` arm must go RED (engineering rule 11): the same
  bombs announced in `names`, the seeded bomb kept, and, if the arm also
  observes the sink, the probe over control memory or refused at the cap.

What the scenario must not do: decode an over-bound image anywhere but under
that cap, build a corpus of more than a few megabytes in the shared scratch
directory, or touch the live install, its cache, or the network.

Ownership and evidence, VERIFIED on 2026-10-11 by this section's author
running the scenario from the harness lane's worktree at lane commit e3ffdab
(`lane-logo-r3`; the earlier text here marked the name UNVERIFIED at 3c8cd65,
where no file of that name existed). `scripts/dev-harness/logo-scenario.sh`
exists and observes both sinks: the helper as the subprocess the service
runs, over a loopback https provider with a self-signed certificate
(`spikes/logo-decode-bomb/serve-and-fetch.py`, the helper as its child with
`SSL_CERT_FILE` pointed at the certificate, nothing detached), and the
shell's `Image` as `spikes/logo-decode-bomb/probe-tmpl.qml` declares it,
under the rlimit above. The corpus comes from
`spikes/logo-decode-bomb/make-corpus.py`, stdlib only, 32 files. What it
answered on this machine:

- `bash scripts/dev-harness/logo-scenario.sh check-tree` (the gate's arm: no
  transcript, no bomb decoded): `logo-scenario: 33 passed, 0 failed`, 33
  `PASS` lines, which is the scenario's 32 checks plus its own "ran every
  check it has (32)" line, in about 3 s. K1 reads `ready control-memory`
  (under 160 MB) and K2 reads `withheld-and-gone`.
- `bash scripts/dev-harness/logo-scenario.sh --baseline 159da94` (the live
  arm, transcript first line per parallel rule 7): `9 passed, 24 failed`.
  V1, V2, C1, C2, C3, C4, T2 and K1 pass as controls, and the ninth PASS line is the scenario's own "ran every check it has (32)" floor; P1..P10, S1, G1, F1,
  F2, R1, R2, R3, E1, E2, E3, M1, M2, T1 and K2 go red, and K2's line reads
  `announced rc=0 peak_mb=839` -- the finding at the sink, the shipped
  0.13.3 helper announcing the 304-byte bomb and the row slot decoding it to
  839 MB under the rlimit. That is the RED this section asked for.
- The gate: `scripts/check.sh` runs the `check-tree` arm under the banner
  `scripts/dev-harness/logo-scenario.sh check-tree (D-LOGO-11)` with a floor
  of `LOGO_PREFLIGHT_MIN=33` `PASS` lines, and `scripts/qa-lib-test.sh`
  asserts that floor equals the scenario's `EXPECTED_CHECKS` plus one (388
  checks there, up from 385). A machine without python3, openssl, util-linux
  `prlimit` or `/usr/lib/qt6/bin/qml` makes the scenario exit 77 with the
  reason as its first line, and the gate treats 77 as RED unless
  `LOGO_PREFLIGHT_SKIP_OK=1` is set in the environment; the SKIP reason is
  printed either way. The first version of the gate step printed the SKIP
  and went on to `all green`, so a machine with no qml runtime reported a
  green gate having observed neither sink (the harness lane's finding 2;
  proof: `LOGO_QML_BIN=/nonexistent ./scripts/check.sh` exits 1 with the one
  FAIL on this step, and with `LOGO_PREFLIGHT_SKIP_OK=1` exits 0 with the
  SKIP line -- the lane's run, not re-run here).
- Mutations the lane ran against the scenario, each reddening it (the
  lane's counts, 2026-10-11): the helper's sweep unlink made a no-op, K2
  reads `withheld-but-file-survived`, 21 passed 12 failed; one `ck` line
  commented out, the floor line fails `ran 31 checks, expected 32`; one bomb
  dropped from the corpus list, S1, G1, R1, R2 and the floor red (27/5) and
  the `qa-lib-test.sh` recipe join red; the check.sh floor moved to 34, the
  join red; the scenario dropped from `qa-lib-test.sh`'s gate list,
  `ran 387 checks, expected 388`.

Three of the numbers above are this author's own run (33/0, 9/24, K2
`peak_mb=839`); the rest are the harness lane's report at e3ffdab and are
attributed to it. The lead's own measurements, which the two questions are
derived from, are the D-LOGO-11 row in `docs/STATUS.md` and "Fifth
maintainer finding, 2026-10-09" in `docs/QA-RESULTS.md`; the per-type
sibling table there is why question two runs all four types and not JPEG
alone. The re-measured table under the rlimit, 36 rows judged from the tree (37 with `--extra`) and 0 DIFF
against the lead's figures except the two 65500x65500 progressive rows the
scope could not measure, is `scripts/dev-harness/spikes/logo-decode-bomb/README.md`.

### 3.3 The clipboard as an input the shell blocks on (D-CLIP-1)

What is under test. The standard is `ARCHITECTURE.md` section 8.13 and the
lead's ruling 1 (section 6's D-CLIP-1 entry): no editable `TextInput` exists
in the shell while the plugin's form is open, because on the released Qt
(6.11.2 here; 6.12.0 the same) an editable `QQuickTextInput` answers every
`QClipboard::dataChanged` by reading the WHOLE offer -- `QMimeData::text()`,
a Wayland pipe with a 1 s per-read timeout, no total limit and no deadline
-- synchronously on the shell's main thread, with no user action. The
obvious test is not one, for the reason 3.1 and 3.2 give: asserting that
`Guide.qml` contains `readOnly: true` restates the line written to contain
it, and a grep cannot see a binding that flips it, a second field added
without it, or a Qt that moves the read somewhere `readOnly` does not gate.

**Question one: does the plugin edit the field the way Qt would have?** Pure
logic, called rather than mirrored, and measured against Qt rather than
read from it. Lane A's `tests/fixtures/form-edit.js` is a transcript of a
real `TextInput`: `Ctrl+Left` / `Ctrl+Right` at every position of 24 strings
on a read-only input and `Ctrl+Backspace` / `Ctrl+Delete` on an editable
one, generated once and re-measured by `test_formEditBoundaries` on every
spec run, so a Qt whose boundary changes reddens the spec and not only the
fixture. Node holds `Model.wordBoundary`, `editInsert` and `editDelete` to
the same table (115 checks). The cases that carry the weight are the
separator set character by character (`@` in `user:p@ss@h`, which is also
the userinfo lesson of D-SINK-1 and D-SINK-17), the forward space-skip, the
surrogate pair taken whole, the insert fitted to the CAPACITY rather than to
the limit (Qt refuses one key at `maximumLength` and truncates a longer
insert; the field's capacity is the limit plus slack so an over-limit value
reaches the validator as `too_long`, SR18), and the two recorded divergences
pinned on BOTH sides (`Ctrl+Delete` over a selection; `Delete` over a
combining mark). `test_readOnlyFieldPremises` pins what the handler rests
on: a read-only input never edits itself under typing, `Backspace` or
`Ctrl+V`; navigation, `Shift`-selection, Home / End and `Ctrl+A` stay
native; `selectionStart` / `selectionEnd` follow the caret; `Ctrl+V` and
`Shift+Insert` both reach `Keys.forwardTo` as Paste and `Ctrl+X` /
`Shift+Delete` as Cut, a bare `Insert` as neither; a bound write re-renders
synchronously and parks Qt's caret at the end; Qt draws NO caret on a
read-only input (`cursorVisible` false, no `cursorDelegate` instantiated),
which is why the form draws its own; and, since 51866a3, `Ctrl+C` copies
natively (the selection pasted back into the editable control reads `ell`)
and a mouse click places the caret while a drag selects, on a dedicated
read-only control at `y: 120` that no other spec input overlaps, with
`selectByMouse` at the default the host's `TextField` inherits. The last
two were CLAIMED as pinned at 44b250b and were not (the review's rule-14
finding); the spec of that commit sent no `Key_C` and no mouse event.
`test_passwordCutIsNativelyANoOp` (51866a3) pins Qt's own gate: `Ctrl+X`
with `ecr` selected leaves `secret` on a Password control and `set` on a
Normal one, which is what `Model.cutApplies` mirrors. The spec's
`cleanup()` resets `maximumLength` and the shared controls after EVERY
test, so a red `test_formEditCap` no longer leaks its cap of 5 into
`test_formEditDeletes` as a second, misleading failure about
`Ctrl+Backspace` (the review's P3). Seen red (the lanes' counts, in their
commit messages): against f9144f5's `Model.js` 114 of the 115 node checks
fail (the one that passes reads only the fixture); `@` dropped from the
separator set 5 node / 2 spec; the forward space-skip dropped 13 / 2; the
insert cap dropped 5 node; the premise control made editable -- the
defect's own shape -- 4 spec failures including "one key at the cap is
refused" and "Qt draws no caret on a read-only input". For the second
round: `editRangeFor` with the masked branch removed (the review's
mutation, now reachable) 4 node failures where the gate had stayed green;
`cutApplies` with the echo gate removed 1 node / 1 spec; `selectByMouse:
false` on the pinned control 1 spec; the read-only control given a
`Keys.onPressed` that accepts `StandardKey.Copy` 1 spec; the insert cap
removed from `editInsert` with the new `cleanup()` 1 spec
(`test_formEditCap` alone) against 2 with the old spec; the 48 new node
checks against 96f5261's `Model.js` 47 failures (the 48th pins
`CLIPBOARD_TIMEOUT_MS`, which already existed); `tests/test_clipboard.py`
against 96f5261's helper 20 of 20 red (no verb), and one mutation per
decision in the verb -- the byte cap removed 4, `reap_child` never
terminating 4 failures and 3 errors, the decoder finalised at the cap 1,
the child's stderr inherited 14, the timeout reply carrying the partial
text 3.

**Question two: does a foreign clipboard change leave the SHELL alone?**
That is the sink, and only observing it answers 8.13. What the scenario
must observe, through the REAL `Guide.qml` hosted by the dev-harness fake
shell (`scripts/dev-harness/shell.qml`) under a nested headless cage
(`docs/SPIKE-CAGE-HEADLESS.md`, `docs/QA-HEADLESS-2026-09-21.md`; the
recipe `id-rotate-scenario.sh` follows, `OMARCHY_IPTV_HEADLESS_ONLY=1` so a
run aimed at the live display is refused):

- The guide must MAP, which under cage means the harness's
  `OMARCHY_IPTV_HARNESS_WINDOW=floating` mode: cage has no layer shell and
  the production `PanelWindow` never maps there, and a window that never
  maps never holds keyboard focus.
- The nested seat must have a keyboard. Lane A measured (2026-10-11, its
  `cage-probe.sh`) that the cage's headless seat has none, that a
  compositor hands `wl_data_device.selection` only to the client with
  keyboard focus, and that on a first run NOT EVEN the editable control
  read (+0 on both probes); a virtual keyboard (`wtype -s 12000 ''`) held
  open on the NESTED display across the offer reproduced the lead's
  numbers (+284 MB editable, +0 read-only). The baseline arm must therefore
  prove the editable read HAPPENS before the fixed arm's +0 means anything;
  a scenario that cannot show red on `--baseline d55149b` has not opened
  the sink and passes vacuously.
- The form is open (first-run, `--playlist none`, which is the state the
  maintainer named), then a FOREIGN producer on the nested display --
  `wl-copy --type text/plain` fed by `python3 -c` writing 100 MB, never a
  file in the shared scratch -- offers once. The user's clipboard is never
  touched: the producer lives on the cage's socket, and `wl-paste
  --list-types` on the live session reads the same before and after.
- Asserted on the fixed tree: the shell's RSS, sampled from outside every
  100 ms, within noise of its pre-offer value through at least the window
  in which the baseline grows (the lead saw the last growth 600 ms after
  the offer; lane A's editable probe under cage 438 ms, in four steps --
  the 6.9 s this line once quoted was a 4 KB blip in the heartbeat probe's
  run, not the editable one's, re-derived by the review from the raw
  samples), and an IPC round-trip (`ipc status`
  or the harness's `state()`) answering within its usual time while the
  offer is up -- the stall is the maintainer's other half and RSS alone
  does not see it. Asserted on `--baseline d55149b`: the growth, by at
  least the payload, which is the RED this section asks for.
- The paste path still works: `Ctrl+V` through the virtual keyboard with a
  small offer puts the sanitized text in the field, and an offer that
  sanitizes to nothing or a `wl-paste` that fails leaves the field as it
  was. A dripping producer (one byte per 900 ms) is OPTIONAL and, if run,
  must show the helper answering `timeout` at its 5 s deadline with the
  `wl-paste` child gone and the shell's IPC still answering (since R8 the
  child is the helper's; the shell's 8 s watchdog is the outer bound).
- Since R8 (51866a3), the user-initiated paste is bounded in BYTES and the
  scenario must observe that too: a `Ctrl+V` over the 100 MB offer leaves
  the shell's RSS within noise, the clipboard helper is seen as the shell's
  child and is gone afterwards, and the field holds `formCapacity`
  characters of the paste. Lane A's scratch variant of the scenario does
  this (two `DR1` checks, 20 in all, with L9 asking for no `omarchy-iptv
  clipboard` child of the shell rather than no `wl-paste` child, which
  since R8 pins less than it says): 96f5261 `FAIL DR1 ... grew +304 MB`,
  51866a3 `PASS DR1 ... unchanged` with the helper peaking at 32 MB. On the
  tree at 51866a3 the scenario does not yet carry it; lifting it is the
  harness round's.
- Cleanup bounded and by pid, honestly described: the qml and wtype pids
  read from the files they wrote, the cage under `timeout`, the detached
  shell by the pid `run.sh` recorded; the scenario file itself has no
  `pkill -f` (the shape `scripts/qa-sources-scenarios.sh:160` has and this
  scenario must not copy), and the `run.sh reap` it delegates to sweeps,
  after the pid-file kill, by patterns anchored to the harness directory
  (`quickshell -p <harness>/root`, the fixture server, the mpv socket
  path), which cannot match the scenario's own shell or the user's
  `quickshell -n -p /usr/share/omarchy/shell` -- so the header's "by
  recorded pid" is true of the file and not of the reap, and should say
  so. `INT` and `TERM` must be trapped as `player-`, `rewind-` and
  `tls-scenario.sh` trap them (`exit 130` / `exit 143`), because bash runs
  no `EXIT` trap when a signal kills it while it waits on a foreground
  child: at 824ced4 the scenario traps `EXIT` only and a `timeout -s TERM`
  on a live run left the cage, the detached shell, a `sleep 120` and the
  nested `wayland-0` socket behind (the review's P2; the harness round's
  fix). No stale nested `wayland-0` socket left behind.

What the scenario must not do: run `wl-copy` on the user's session, run
`wtype` outside the nested display, leave a producer or a cage alive, write
the 100 MB payload to the shared scratch, or touch the live install.

Ownership and evidence. The scenario is `scripts/dev-harness/clip-scenario.sh`
(the harness lane, 824ced4 on `lane-clip-harness`, integrated into `dev` as
85b7fe3 on 2026-10-11; `OMARCHY_IPTV_HEADLESS_ONLY=1`, the harness's
floating-window mode, `wtype` held on the nested seat). `check-tree` is the
probe arm P1-P6 under `timeout -k 5 70`, the gate step
"scripts/dev-harness/clip-scenario.sh check-tree (D-CLIP-1)" with
`CLIP_PREFLIGHT_MIN` 7, printed as "clip preflight (7 checks)"; `live` adds
L1-L11 (18 checks) and the `--baseline <ref>` lever; both check their own
count (`EXPECTED_CHECKS` 6 and 17) so a dropped line is a failure. The
counts, each from the transcript a run prints as its first line. This
author's own, on the docs lane's tree at 2b3e847 (lane-clip-r1 51866a3 plus
documents), live mode, 2026-10-11: 18 passed / 0 failed in 29.3 s, the
consumer reading 104,857,600 bytes, the shell 348 -> 348 MB (+0) after the
100 MB offer, twelve IPC round trips with the worst at 105 ms, L7 pasting
10 bytes and L8 landing 2,112 characters through the helper verb, nothing
left behind (no cage, no second quickshell, no `wl-paste` but the host's
`--watch`, no harness scratch directory); transcript
`/run/user/1000/omarchy-iptv-clip/transcripts/clip-20261011-182035-3389538.out`,
and the gate's own check-tree arm on the same commit "clip preflight (7
checks)". The rest are other runs, attributed: the adversarial review of
824ced4, check-tree
7 / 0 (the editable probe +259 MB, read-only +0, no-field +0, the consumer
reading 104,857,600 bytes), live 18 / 0 with the shell at +0 MB and the
worst of twelve IPC round trips 124 ms after a 100 MB offer, `--baseline
d55149b` 16 / 2 with L4 red at +240 MB (peak 589) and L5 red at 746 ms,
and the full gate exiting 0 in 2 m 42 s; its mutations every one red
(`readOnly` flipped back in a copy, L4 `+252 MB` and L5 `793 ms`; a P line
dropped, `ran 5 checks, expected 6`; an L line dropped, `ran 16, expected
17`); the review's second reviewer from its own worktree, fixed +0 MB /
146 ms and baseline +264 MB / 729 ms; lane A's live run on 51866a3, 18 / 0
in 24.8 s with L7 and L8 pasting through the helper verb. The baseline's
L4 has read +240, +254, +264 and +297 MB over the runs recorded, about 2.5x
the payload and never inside the 16 MB band; the scenario's footer quotes
`+254..+297`, which the review's +240 fell under, and should say the range
seen. The user-paste number (DR-1, R8) is in the bullet above and in
`ARCHITECTURE.md` section 6: +298 / +304 MB on the first fix, +0 on 51866a3.
The lead's three probes on the live session and lane A's re-run of them
under cage, of a throwaway `TextField` and not of `Guide.qml`, remain the
attribution of the mechanism and are cited as such in `ARCHITECTURE.md`
section 6.

## 4. Performance gate (PLAN G3, ARCHITECTURE.md section 7, QB4)

Inputs: `https://iptv-org.github.io/iptv/index.m3u` (11,041 entries, 2.5 MB)
and, offline, `scripts/gen-playlist.py --channels 10000 --groups 120 --seed 1
--epg-ids 0.6 --out /tmp/omarchy-iptv-qa/gen-10k.m3u --xmltv
/tmp/omarchy-iptv-qa/gen-10k.xml.gz --hours 24` (deterministic: m3u sha256
`63061a85cd2183f67a0b009c6f8cb9891b59af2c54bdf0db5ad1fb8ff18c50fe`, 1,844,026
bytes, 10,000 channels, 120 group strings;
RE-PINNED 2026-09-23: the previous hash `0aa5acc2...` at 1,841,211 bytes predates
M2-03, which made the generator emit `tvg-chno` on every entry. Determinism was
re-verified rather than assumed -- two runs with the same flags are byte-identical
-- so the old hash was stale, not a regression, and anyone re-running this gate
against it would have started by chasing a fixture that was fine; XMLTV 41.3 MB inflated, 5,840
channels, 266,474 programmes). Never commit generated files.

Baseline measured on the scaffold helper (2026-09-12, this machine): `playlist`
on `gen-10k.m3u` -> `durationMs: 505`, wall 0.64 s, `channels.json` 2,579,498
bytes (over the ~2 MB budget because the synthetic profile fills `tvgName`,
`logo`, `chno`; re-measure with `index.m3u`). A pure `xml.etree.iterparse`
pass over the 41 MB gz takes 1.6 s in Python 3.14 here, so the 4 s EPG budget
leaves room for the now/next projection.

| ID | Budget | Procedure | Record |
|---|---|---|---|
| PERF-01 | helper `playlist` < 1.5 s for 10k (ARCH), < 1 s (PLAN G3) | `time python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv playlist --url /tmp/omarchy-iptv-qa/gen-10k.m3u --cache-dir /tmp/omarchy-iptv-qa/cache`; read `durationMs`; repeat with a local copy of `index.m3u` (`curl -o /tmp/omarchy-iptv-qa/index.m3u https://iptv-org.github.io/iptv/index.m3u`) | both numbers, `channels.json` size, `groupCount` |
| PERF-02 | overlay open < 150 ms with the 10k cache | Method A (IPC round trip, includes the synchronous `open()` work but not the frame): with `playlistUrl` set to the 10k file and the guide closed, run `for i in 1 2 3 4 5; do t0=$(date +%s%N); omarchy-shell shell toggle io.github.rmcdavid.iptv '{}'; t1=$(date +%s%N); echo open $(( (t1-t0)/1000000 )) ms; sleep 1; t0=$(date +%s%N); omarchy-shell shell toggle io.github.rmcdavid.iptv '{}'; t1=$(date +%s%N); echo close $(( (t1-t0)/1000000 )) ms; sleep 1; done` and the baseline `for i in 1 2 3 4 5; do t0=$(date +%s%N); omarchy-shell shell ping; t1=$(date +%s%N); echo $(( (t1-t0)/1000000 )); done`; open time = median(open) - median(ping). Method B (frame): ask lane B for an opt-in debug line (`OMARCHY_IPTV_DEBUG=1` or a `debug` setting) that logs `console.info("omarchy-iptv guide open <ms since epoch>")` at the top of `open()` and once after the first frame (`Qt.callLater` chained twice after `visible = true`, or the window's `frameSwapped`); read both from `journalctl --user -t omarchy-shell`. Method C (perception): open the clipboard (`SUPER CTRL + V`) and the guide alternately; the guide must not feel slower | median and max of 5 opens, method used **[2026-10-20, R27f (D-PERF-1): method A ends when the summon returns, so it cannot see the delegates being made, and the IPC client's own start-up noise is larger than what is left -- measured beside the async instrument at 10,000 channels it read about 0 ms (-7 to 6) while the open realised its first screen in 546 ms (list) and 580 ms (wall) cold and 34 / 32 ms warm. The open's number is `scripts/dev-harness/open-scenario.sh live` (TC-CFG-36): rule 7's budget holds warm and NOT cold in the cage's floating window; on Hyprland the cold figure is UNVERIFIED.]** **[2026-10-20, R28d: with the instrument counting only what is drawn, interleaved the same way, method A read a median of -2 / -4 ms while the open realised 548 / 534 ms cold and 33 / 31 ms warm (`open-20261020-154123-1999165`)]** **[2026-10-20, R29e: drawn now also means painted above opacity 0; the open realised 547 / 547 ms cold and 34 / 32 ms warm (`open-20261020-192446-2690236`), so rule 7's budget still holds warm and not cold (TC-CFG-36)]** |
| PERF-03 | keystroke to redraw < 30 ms, no dropped keys, 40 ms coalescing allowed | with the guide open on the 10k cache: `wtype -d 20 'alpha news channel'` then `wtype -d 0 'zzzzzzzzzzzzzzzzzzzz'` (20 keys, no delay); every character must appear in the header in order and the scope label must settle on the right count; no `WARN` in the journal. Micro-benchmark of the pure filter: `node -e 'const M=require("./Model.js");const c=JSON.parse(require("fs").readFileSync(process.env.HOME+"/.cache/omarchy-iptv/channels.json")).channels;for(const q of ["a","news","alpha news","zz"]){const t=process.hrtime.bigint();for(let i=0;i<50;i++)M.filterChannels(c,q,200);console.log(q,Number(process.hrtime.bigint()-t)/50/1e6,"ms")}'` (run from the plugin dir after the merge; the node file must expose `filterChannels`) | ms per query, dropped keys yes/no |
| PERF-04 | helper `epg` < 4 s for a 50 MB XMLTV, RSS < 300 MB | `python3 - <<'EOF'` wrapper (GNU `time` is not installed): `import resource,subprocess,time;t=time.monotonic();p=subprocess.run(["python3","<plugindir>/bin/omarchy-iptv","epg","--url","/tmp/omarchy-iptv-qa/gen-10k.xml.gz","--cache-dir","/tmp/omarchy-iptv-qa/cache"]);print("exit",p.returncode,"wall %.2fs"%(time.monotonic()-t),"maxrss MB",resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024)`; then `ls -l /tmp/omarchy-iptv-qa/cache/epg-now.json` (< 1 MB at 10k) and `time ... epg --now-only ...` (recompute, expected well under 1 s); repeat with the Pluto gz (955,717 bytes) | wall, RSS, file size |
| PERF-05 | shell memory | `ps -o rss= -p $(pgrep -f 'quickshell -n -p /usr/share/omarchy/shell')` before enabling, after the 10k cache loads, after 20 guide opens | three RSS values (informational, no budget) |
| PERF-06 | zap under 2 s of interaction | stopwatch from `SUPER + SHIFT + T` to the first mpv frame on a live channel (`us.m3u`) after typing three letters and Enter; try three channels | seconds, channel used |
| PERF-07 | refresh does not stall the shell | while the 10k helper runs (`r`), move the cursor and type; the bar clock keeps ticking | pass/fail |

Record all numbers in `docs/STATUS.md` (M1.1-03 evidence) with the commit id
of the plugin under test.

## 5. Live-shell runbook (this machine)

`scripts/qa-live.sh` prints every command of phases 5.1, 5.2, 5.3, 5.7, 5.9
and 5.10 and only executes them with `--apply`; it refuses `install` when the
plugin directory exists unless `--force`, and refuses a non-interactive
`uninstall --apply` unless `--force`. The steps below are the source of truth;
the script is a convenience.

### 5.0 Preconditions and what the pass changes on this machine

- The lead has merged both FE lanes and `scripts/check.sh` is green at the
  commit under test; note the commit id (`git -C <repo> rev-parse --short HEAD`).
- Files touched during the pass: `~/.config/omarchy/plugins/io.github.rmcdavid.iptv`
  (git clone), `~/.config/omarchy/shell.json` (one entry `{"id":
  "io.github.rmcdavid.iptv", ...settings}` appended to `bar.layout.right` by
  `omarchy plugin enable`, keys added by `omarchy bar set`), `~/.cache/omarchy-iptv`,
  `~/.local/state/omarchy-iptv`, `/run/user/1000/omarchy-iptv`, and the
  evidence directory `/tmp/omarchy-iptv-qa`. Optional, by hand and reverted
  in 5.10: one line in `~/.config/hypr/bindings.lua`, one entry in
  `~/.config/omarchy/extensions/omarchy-menu.jsonc`. Nothing under
  `/usr/share/omarchy` is touched.
- Restore path: `omarchy plugin remove io.github.rmcdavid.iptv --yes` removes
  the bar entry (PluginRegistry.setEnabled false splices it out) and the clone;
  the snapshot `shell.json.before` proves the file is back to its pre-install
  content; the three runtime directories are deleted by hand.
- Where the shell console goes on this machine: `journalctl --user -t
  omarchy-shell` (durable, timestamps; the shell is started with
  `systemd-cat -t omarchy-shell`), `qs log -p /usr/share/omarchy/shell --tail
  200` (same lines, coloured, from `/run/user/1000/quickshell/by-pid/<pid>/log.log`),
  `qs log -p /usr/share/omarchy/shell -f` to follow during a test. Our lines
  are prefixed `omarchy-iptv`. Helper stderr lands there through
  `console.warn("omarchy-iptv playlist:", ...)`.

### 5.1 Preflight (read-only)

```
scripts/qa-live.sh preflight
```

Expect: versions as in the header of this file; `SUPER SHIFT + T is free`;
no `omarchy-iptv` directories; `entries in bar.layout: 0`; playlist HEAD
`HTTP/2 200`; EPG resolves through two 302s to `raw.githubusercontent.com`
with `content-length: 955717` (the helper must follow redirects; `urllib`
does by default). Record the current theme (`retropc`).

### 5.2 Install (TC-INST-01..04)

```
export REPO=/home/ricky/Projects/omarchy-iptv           # or the git URL of the merge commit
scripts/qa-live.sh install --apply --repo "$REPO"
```

which runs: snapshot `shell.json` (0600) to `/tmp/omarchy-iptv-qa/shell.json.before`,
`git clone -- "$REPO" ~/.config/omarchy/plugins/io.github.rmcdavid.iptv`
(never a symlink; the validator rejects them), `omarchy plugin validate <dir>`,
`omarchy-shell shell rescanPlugins`, `omarchy plugin enable io.github.rmcdavid.iptv`
(bar widget lands in `right`, the manifest default), `omarchy plugin list --json`.

Expected: `Enabled io.github.rmcdavid.iptv`; the JSON row shows `"enabled":
true`, `"kinds": ["bar-widget","overlay","service"]`; `jq '.bar.layout.right[-1]'
~/.config/omarchy/shell.json` prints `{"id":"io.github.rmcdavid.iptv"}`; the
bar shows the idle glyph U+F0502 at the right; `journalctl --user -t
omarchy-shell --since "$(cat /tmp/omarchy-iptv-qa/started-at)"` has no WARN/ERROR
from our files (TC-INST-04). Also run `omarchy-shell shell listPlugins | jq
'.[] | select(.id=="io.github.rmcdavid.iptv")'`.

### 5.3 Configure (TC-CFG-01, TC-BRW-01, TC-BRW-04)

```
scripts/qa-live.sh configure --apply                       # us.m3u + Pluto EPG
# or by hand:
omarchy bar set io.github.rmcdavid.iptv playlistUrl https://iptv-org.github.io/iptv/countries/us.m3u
omarchy bar set io.github.rmcdavid.iptv epgUrl https://i.mjh.nz/PlutoTV/us.xml.gz
```

**[Round 11, 2026-10-13 (D-SINK-19 R21; the owner dropped the `omarchy bar
set` URL route): the two by-hand lines above are WITHDRAWN.** On this version a
fresh install migrates (with nothing to migrate) at its first start, and a URL
set with `omarchy bar set` afterwards is refused, reported and removed
(TC-CFG-14). Configure in the guide instead: open it, and in the first-run form
paste `https://iptv-org.github.io/iptv/countries/us.m3u` into `Playlist` and
`https://i.mjh.nz/PlutoTV/us.xml.gz` into `EPG`, then `Enter`;
`scripts/qa-live.sh configure` now prints exactly that step and runs no
`omarchy bar set`. Throughout 5.4, every step that sets `playlistUrl` or
`epgUrl` with `omarchy bar set` is done the same way: "set `playlistUrl` X" is
an edit of the active source's `Playlist` with `e` in Sources (or `a` for a
new source), and "set `epgUrl` X" an edit of its `EPG`. The settings
`refreshMinutes`, `mpvArgs`, `showChannelName`, `barLabelMaxWidth` and
`maxRecents` are still set with `omarchy bar set` as written.]**

Then add, by hand, the README one-liners (they are user-side files; revert
them in 5.10):

```
# ~/.config/hypr/bindings.lua
o.bind("SUPER + SHIFT + T", "IPTV", "omarchy-shell shell toggle io.github.rmcdavid.iptv")
# ~/.config/omarchy/extensions/omarchy-menu.jsonc (hot reload)
"iptv": {"icon":"<U+F0567>","label":"IPTV","aliases":["tv","iptv"],"action":"omarchy-shell shell toggle io.github.rmcdavid.iptv"},
```

If the lead prefers not to touch `bindings.lua`, run TC-BRW-01 as
`omarchy-shell shell toggle io.github.rmcdavid.iptv` and mark the keybinding
row `not run (binding not installed)`.

Note the EPG: Pluto ids are 24-hex Pluto ids, iptv-org `tvg-id`s are
`Name.us`, so matching is partial by design (QA-ASSETS.md). For a fully
matched EPG use the generator: `playlistUrl /tmp/omarchy-iptv-qa/gen-real.m3u`
and `epgUrl /tmp/omarchy-iptv-qa/gen-real.xml` produced by
`scripts/gen-playlist.py --profile realistic --channels 1500 --groups 40 --seed 7
--multi-group 0.25 --out /tmp/omarchy-iptv-qa/gen-real.m3u --xmltv
/tmp/omarchy-iptv-qa/gen-real.xml` (omit `--now` so the window is centred on
the current hour; the URLs are `.test` hosts and will fail to play, which is
fine for EPG rows).

### 5.4 Story checklists

Record each numbered step as pass/fail with the TC ids in brackets.
Microcopy in backticks is verbatim from UX.md section 6 (with the real
codepoints for `...`, quotes and the middle dot).

#### US1 Configure (TC-CFG-*, TC-UI-01..03, TC-BAR-02/04)

1. Before setting `playlistUrl` (do this once, right after 5.2): hover the
   widget -> tooltip `IPTV - no playlist configured`; open the guide ->
   `No playlist configured`, body `Set your M3U URL or path, then press r to
   load it:`, command box `omarchy bar set io.github.rmcdavid.iptv playlistUrl
   <url>`, `Optional EPG:  omarchy bar set io.github.rmcdavid.iptv epgUrl <url>  (converted; not kept in shell.json)`,
   `Both are inputs: the URL moves to ~/.local/state/omarchy-iptv/state.json; other settings live in ~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv)`,
   no group column, hint `r reload - Esc close`, glyph U+F0502; click the box,
   `wl-paste` prints the command, footer `Copied` [TC-UI-01, TC-BAR-02].
   (Since D-SINK-19 the command is an input: after step 2 the entry carries
   `sourceKey` and no `playlistUrl`; see TC-CFG-01 as amended. The two lines
   after the box are the round-3 strings; before 2026-10-12 they read
   `Optional EPG:  omarchy bar set ... epgUrl <url>` and `Settings live in
   ~/.config/omarchy/shell.json (entry ...)`.)
2. Set `playlistUrl` (5.3) with the guide open: within a second the state
   becomes `Loading playlist...` / `Fetching from iptv-org.github.io` (host
   only) with hint `Esc close` [TC-UI-02], then the list renders; footer
   `1,475 channels - updated HH:MM` (count as of the live list; it drifts);
   tooltip `IPTV - click to open the guide` [TC-CFG-01, TC-CFG-12].
3. `journalctl --user -t omarchy-shell --since -2m | grep omarchy-iptv`: one
   helper run, no URL in any line [TC-CFG-13].
4. `omarchy bar set io.github.rmcdavid.iptv playlistUrl https://iptv-org.github.io/iptv/countries/nope.m3u`;
   with a cache present: banner `U+F0026 Playlist refresh failed (HTTP 404 Not
   Found) - showing cached copy from HH:MM - r retry`, footer `1,475 channels -
   cached HH:MM - offline`, notification `Playlist error` / `Could not fetch the
   playlist (HTTP 404 Not Found). Using cached copy from HH:MM.`; then
   `rm -rf ~/.cache/omarchy-iptv/*` and press `r`: empty state `Playlist failed
   to load` / `HTTP 404 Not Found from iptv-org.github.io - check playlistUrl`
   [round 12, 2026-10-13 (R22c): `... - check the source in Sources`; the
   old text is a FAIL],
   hint `r reload - Esc close`, glyph U+F0503, bar glyph U+F0503 and tooltip
   `IPTV - playlist error, open the guide`, notification body `... Open the
   guide for details.` [TC-CFG-02, TC-UI-03, TC-BAR-04].
5. `omarchy bar set io.github.rmcdavid.iptv playlistUrl https://does-not-exist.invalid/x.m3u`
   -> reason `Could not resolve host` [TC-CFG-03].
6. Restore the US list (5.3); confirm the guide, still open, recovers without
   restart [TC-CFG-12].
   **[Round 11, 2026-10-13: steps 1, 2, 4 and 5 go through the guide (5.3's
   round-11 note): step 1's body is TC-UI-01 as amended, with no command box
   to click; steps 4 and 5 edit the active source's `Playlist` with `e`.
   Steps 7 and 8 are new.]**
7. Migration (TC-CFG-15), only on a machine upgrading from 0.13.6 or earlier
   with a URL on the entry: before the first restart onto this version,
   `jq '.bar.layout[][] | select(.id=="io.github.rmcdavid.iptv")'
   ~/.config/omarchy/shell.json | grep -c '"playlistUrl"'` reads 1; after
   `omarchy-restart-shell` and a few seconds, 0, with `sourceKey` present,
   the source in Sources and active, `jq .entryMigrated
   ~/.local/state/omarchy-iptv/state.json` `true`, and no notification.
8. Refusal (TC-CFG-14): `omarchy bar set io.github.rmcdavid.iptv playlistUrl
   https://iptv-org.github.io/iptv/countries/fr.m3u`: one notification `Bar
   setting ignored`, the guide still on the US list, no `fr` row in Sources,
   the `grep -c '"playlistUrl"'` above back to 0 within a second; the same
   command again raises no second notification.

#### US2 Browse (TC-BRW-*, TC-UI-08..10)

1. Open with `SUPER + SHIFT + T`; close with the same key. Open with a left
   click on the widget; close with a click. `omarchy-shell shell toggle
   io.github.rmcdavid.iptv` twice. No fade in or out [TC-BRW-01..03, TC-UI-08].
2. On open: header `Search channels...`, scope label `All - 1,475 channels`
   (or `Favorites - N channels` once favorites exist), column `Favorites`,
   `All`, `GROUPS`, groups in playlist order with counts, `Recent` absent
   until something played; footer hint `Enter play - Up/Down move -
   Left/Right group - Tab keys - Esc close`; cursor on row 0 [TC-BRW-05,
   TC-BRW-06, TC-BRW-21, TC-UI-09, TC-UI-10].
3. Type `news`: label `in All - N matches`, hint changes to `... Left/Right
   narrow - Tab keys - Esc clear`; type ` sp` (space, letters): fewer rows
   (AND); Backspace, Ctrl+Backspace (word), Ctrl+U (clear) behave; type `TELE`
   then a channel with an accented name should match its unaccented spelling
   (the US list has few; use `gen-real.m3u` or `qa-nonascii/qa-unicode.m3u`
   as a local playlist to prove `tele` finds `Tele Quebec` with accents)
   [TC-BRW-07].
4. With `index.m3u` or `gen-10k.m3u` as playlist, type `a`: footer `First 200
   of N - keep typing`, exactly 200 rows [TC-BRW-09].
5. Down from the last row wraps to the first; Up from the first wraps to the
   last; PgDn moves by visible rows minus one and stops at the end; End, Home
   [TC-BRW-10].
6. Right/Left move the column highlight (wraps at both ends); on Favorites,
   start typing -> highlight jumps to All; clear the query -> back to
   Favorites [TC-BRW-11].
7. With a query: Esc clears it, guide stays; Esc again closes. Then
   `omarchy-shell shell toggle io.github.rmcdavid.iptv` opens on the first
   call (host state in sync) [TC-BRW-12].
8. Type `spo`, press Tab: query committed, hint `j/k move - h/l group - Enter
   play - Space preview - f favorite - s stop - r refresh - / search`; j/k/h/l
   move; `/` returns to search mode with `spo` still in the header; Shift+Tab
   also enters search mode [TC-BRW-13].
9. In list mode press `q`, `w`, `e`, `4`: nothing happens; press `F`, `S`,
   `R`, `X`: same as lowercase. In search mode `4k` filters [TC-BRW-14..16].
10. Move the column to a real group, type `zzzz`: `No matches for "zzzz" in
    <group>` with `h/l other groups - Home for All`; press Home: column jumps
    to All; clear, on All type `zzzz`: `No matches for "zzzz"` / `Esc clears
    the search` [TC-BRW-17, TC-BRW-18].
11. Mouse: hover moves the cursor only after the pointer moves; move with keys,
    leave the pointer still over another row: the cursor stays; click the scrim:
    closes; click inside the card on empty space: nothing; wheel over the list
    scrolls, over the column moves the selection one per tick; the lead slot
    (star column) is clickable [TC-BRW-19, TC-BRW-23, TC-A11Y-03].
12. Focus a terminal, open the guide over it, type `ls` and Enter: the terminal
    receives nothing; the guide filtered and (if a match) played [TC-BRW-20].
13. Find a multi-group entry in the US list (`grep -c 'group-title="[^"]*;'
    /tmp/omarchy-iptv-qa/us.m3u` after `curl -o`), e.g. `Animation;Kids`: it
    is listed once under `Animation` and found by typing `kids` [TC-BRW-22].

#### US3 Watch (TC-PLAY-*, TC-INST-09)

1. Search a live channel (news channels on the US list usually work), Enter:
   guide closes, exactly one mpv window appears with the channel name as title,
   focused. Stopwatch from the key to the first frame [TC-PLAY-01, TC-PLAY-12].
   Verify in 5.7.
2. Reopen, Enter on a different live channel: same window (same pid in
   `hyprctl clients -j`), title changes [TC-PLAY-02].
3. Reopen, cursor is on the playing row (bold, glyph U+F040A); Enter: no
   reload (no black frame; `omarchy-shell io.github.rmcdavid.iptv status` shows
   the same channel), guide closes, mpv focused [TC-PLAY-03].
4. Reopen, Space on three different rows within two seconds: guide stays open,
   the cues (bold + U+F040A + footer `U+F040A <name> - s stop`) move each time,
   playback ends on the third; still one mpv [TC-PLAY-04, TC-PLAY-10, TC-UI-04].
5. Dead stream: use `gen-dead.m3u` (`scripts/gen-playlist.py --channels 200
   --groups 5 --seed 3 --dead 0.5 --out /tmp/omarchy-iptv-qa/gen-dead.m3u`; half
   the URLs point at `127.0.0.1:9`, connection refused) or a `qa-attrs.m3u`
   entry. Enter on a dead row: notification `Stream failed` / `<name> did not
   play` (plus ` - <reason>`), glyph U+F0503, urgency normal; a second failure
   replaces the toast (`-r`); guide row shows U+F0026 and `Failed HH:MM - Space
   to retry`; the cursor did not move; the channel is in Recent; bar back to
   U+F0502 [TC-PLAY-05, TC-FAV-07]. Check SEC-07 now: the notification and the
   journal contain no URL (`qa-attrs.m3u` has `http://user:secret@...`; the
   body must not show `user:secret`).
6. Play a live channel, press `s`: footer `Stopped` for 3 s, mpv gone, bar
   idle, no notification. Play again, press `q` inside mpv: bar idle, cues
   clear, no notification [TC-PLAY-06, TC-PLAY-07].
7. Play, then `omarchy-shell shell rescanPlugins`: playback continues, bar
   label unchanged (keepLoaded service) [TC-INST-09].
8. `omarchy bar set io.github.rmcdavid.iptv mpvArgs '--profile=fast --hwdec=auto-safe --input-ipc-server=/tmp/x --title=X --no-idle'`;
   stop and play again; `ps -o args= -p $(pgrep -f 'wayland-app-id=omarchy-iptv')`
   shows `--profile=fast --hwdec=auto-safe`, none of the reserved ones, the
   URL last after `--`; journal has one warning naming the three dropped tokens.
   With `gen-dead.m3u` entries that carry `#EXTVLCOPT`, argv shows
   `--user-agent=Mozilla/5.0 (X11; Linux x86_64) gen-playlist/1.0` as one item
   [TC-CFG-08, TC-PLAY-08, SEC-06]. Reset: `omarchy bar set io.github.rmcdavid.iptv mpvArgs ''`.
9. Optional: `kill -STOP $(pgrep -f wayland-app-id=omarchy-iptv)`; within ~30 s
   (two 10 s health polls) the console logs `mpv unresponsive, restarting
   player` and mpv gets SIGTERM. mpv installs a SIGTERM handler, so a
   SIGSTOPped mpv stays stopped with the signal pending (v0.1 wrongly said
   `kill -CONT` is not needed): run `kill -CONT <pid>` yourself, then check
   that mpv exits and the channel is relaunched once [TC-PLAY-09].
10. Make mpv fullscreen (`f` in mpv), open the guide: it draws above; Esc:
    mpv still fullscreen, not paused, not muted [TC-PLAY-14].

#### US4 Now playing (TC-BAR-*, TC-CFG-09/10)

1. Idle: glyph U+F0502 dimmed, no label, tooltip `IPTV - click to open the
   guide` [TC-BAR-01].
2. Playing: glyph U+F0567, name elided at the default width, tooltip `Playing
   <full name>`; the label width animates (180 ms) when the name changes
   [TC-BAR-03].
3. Left click opens, left click closes [TC-BAR-06].
4. Right click stops [TC-BAR-07].
5. Middle click: tooltip `IPTV - refreshing playlist...` while running, footer
   `Refreshing...` then `Refreshed - 1,475 channels`, notification `Playlist
   refreshed` / `1,475 channels in 38 groups` (live counts), low urgency,
   glyph U+F0450 [TC-BAR-05, TC-BAR-08].
6. Play from a group, scroll down/up over the widget: next/previous channel in
   that group, one per tick, wraps at both ends; play from Favorites (need 2+):
   scroll stays in Favorites; play from Recent: ring is the channel's group.
   On the touchpad a slow two-finger swipe changes one channel, not several
   [TC-BAR-09].
7. `omarchy bar set io.github.rmcdavid.iptv showChannelName false --json`:
   glyph only while playing, tooltip still has the name; set back `true --json`
   [TC-CFG-09].
8. `omarchy bar set io.github.rmcdavid.iptv barLabelMaxWidth 60 --json`: heavy
   elision; `600 --json`: full name; back to `180 --json` [TC-CFG-10].
9. Hover: tooltip text matches the state table in UX 6.3 for every state seen
   so far [TC-BAR-01..05].

#### US5 Favorites and recents (TC-FAV-*, TC-INST-08)

1. On a row press `f`: star U+F04CE in the lead slot, footer `Added to
   Favorites` (3 s); `f` again: star gone, `Removed from Favorites`. Click the
   lead slot of another row: star toggles, nothing plays [TC-FAV-01, TC-FAV-11].
2. Move the column to Favorites while empty: `No favorites yet` / `Press f on
   any channel to pin it here` [TC-FAV-02].
3. Favorite three channels in the order C, A, B: Favorites lists C, A, B;
   reopen the guide: it opens on Favorites (`Favorites - 3 channels`); press
   `f` on A: A leaves, cursor stays on the same index (B) [TC-FAV-03, TC-FAV-04,
   TC-BRW-06].
4. Play two channels; Recent appears first in the column with `Recent - 2
   channels`; on a Recent row press `x`: `Removed from Recent`; in Favorites
   press Delete: unfavorites; on All press `x`: nothing [TC-FAV-05].
5. Play channel A, then B, then A: Recent is A, B (A moved to the top, no
   duplicate). `omarchy bar set io.github.rmcdavid.iptv maxRecents 3 --json`,
   play four channels: Recent shows three; reset to `10 --json` [TC-FAV-06,
   TC-CFG-11].
6. `omarchy restart shell`: mpv keeps playing, same pid (R10 withdrawn; corrected 2026-09-25, D-QA-19), the widget comes back,
   favorites and recents are intact, `playlistUrl` intact [TC-FAV-08,
   TC-INST-08, TC-PLAY-11].
7. `omarchy-shell io.github.rmcdavid.iptv stop`; `printf 'garbage' >
   ~/.local/state/omarchy-iptv/state.json`; `omarchy restart shell`: guide opens
   with empty Favorites/Recent, no crash, one warning at most; favorite
   something: the file is valid JSON again [TC-FAV-09].
   **[Round 12, 2026-10-13 (D-SINK-19 R22a): copy the real file aside FIRST
   (`cp -p ~/.local/state/omarchy-iptv/state.json /tmp/state.keep`, a
   private copy: it holds your provider URLs), then the garbage. Expected now:
   no crash; one critical notification `Saved sources not loaded` /
   `/home/<you>/.local/state/omarchy-iptv/state.json is not a valid state
   file. Nothing is saved until it can be read, ...`; the guide opens on
   `No playlist configured` (nothing was loaded, so there is nothing to
   favourite); pasting a playlist there is refused with `state.json could not
   be read - nothing is saved until it can be`; and afterwards
   `cat` of the file still prints `garbage` -- nothing was written over it
   [TC-FAV-09, TC-CFG-16]. **[Round 13, 2026-10-13 (R23e): the guide no
   longer opens on `No playlist configured` here. Expected now: the alert
   glyph, `Saved sources not loaded` and the notification's own body, no
   form and no field, footer `Esc close`; in Sources (`o` -- no check has
   observed `o` from this surface yet, so record what it does), `g` (logos)
   answers `state.json could not be read - nothing is saved until it can be`,
   not `try omarchy bar set` [TC-CFG-17].]** **[Round 14, 2026-10-14
   (R24f): `o` was observed opening Sources from this surface by the
   round-13 live lens. Expected in Sources now: the header's right slot
   reads `Saved sources not loaded`, not `No sources`; no `Add source` or
   `Add Xtream login` row; `a` and `c` open no form and answer `state.json
   could not be read - nothing is saved until it can be`; footer `Esc back`
   [TC-CFG-24].]** **[Round 17, 2026-10-20 (R27e): the body's second
   sentence now reads `Sources, favorites and settings changed now are not
   saved until the file can be read again.`, and a block that begins while
   the shell is running is titled `Saving has stopped` [TC-CFG-34].]**
   **[Round 18, 2026-10-20 (R28e): at this start it reads `Sources,
   favorites and settings changed now are not kept.`; a block that begins
   while the shell is running reads `Favorites and other changes made now
   are held in this session only: ...` instead [TC-CFG-34].]** Then `cat /tmp/state.keep >
   ~/.local/state/omarchy-iptv/state.json` (in place, so the shell's watch
   reloads it): the guide comes back with every source and favourite, no
   restart needed; `rm /tmp/state.keep`.]**
8. `stat -c '%a %n' ~/.local/state/omarchy-iptv ~/.local/state/omarchy-iptv/state.json`
   -> `700`, `600` [TC-FAV-08, SEC-14].

#### US6 EPG (TC-EPG-*)

1. With `epgUrl` empty, clear the cache dir, set `epgUrl` (Pluto) and open the
   guide immediately: it opens at once; footer `Guide data loading...` (or the
   neutral banner) until `epg-now.json` appears (`ls -l ~/.cache/omarchy-iptv`)
   [TC-EPG-01].
2. With the generator pair from 5.3 (`gen-real.m3u` + `gen-real.xml`): rows
   show `Now: <title> - Next: <title>`, right meta `until HH:MM` (local 24 h),
   the hairline fills proportionally; a group with EPG uses two-line rows
   [TC-EPG-02].
3. Back on `us.m3u` + Pluto: most rows have no `Now:`/`Next:` and no `until`
   (ids do not match by design); inside a group with no EPG the rows are
   single-line [TC-EPG-03].
4. `omarchy bar set io.github.rmcdavid.iptv epgUrl https://i.mjh.nz/PlutoTV/nope.xml.gz`
   [round 11: edit the active source's `EPG` to that URL with `e` in Sources
   instead; `omarchy bar set` is refused, TC-CFG-14] then `r`: banner `Guide data unavailable (HTTP 404 Not Found) - channels
   still work - r retry`, notification `Guide data error` / `Could not fetch the
   EPG (HTTP 404 Not Found). Channels still work.` low; playing still works
   [TC-EPG-04]. Restore the EPG URL.
5. Leave the guide open on `gen-real` for 90 s: `until` stays, the hairline
   grows (30 s tick); `journalctl --user -t omarchy-shell -f` shows an
   `epg --now-only` run after 5 min and no download before the TTL
   [TC-EPG-08].
6. Automated checks TC-EPG-05..07, 09..11 run in `python3 -m unittest discover
   -s tests`; if `tests/test_epg.py` is missing, run the helper by hand with the
   clock pinned (whatever seam lane A provides) and compare with the expected
   values in the fixture comment.

#### US7 Refresh (TC-RFR-*, TC-CFG-07)

1. `omarchy bar set io.github.rmcdavid.iptv refreshMinutes 30` (string), then
   `--json 5` (clamps to 15), then `--json 99999` (1440): no error, the timer
   re-arms (journal, or the IPC `status` if it exposes the interval); leave it
   at `15 --json` and note the time; a silent helper run appears at +15 min
   [TC-CFG-07, TC-RFR-02].
2. Play a channel, press `r`: footer `Refreshing...` then `Refreshed - N
   channels`, notification `Playlist refreshed` low, playback untouched
   [TC-RFR-01, TC-RFR-05].
3. Offline simulation without touching the network settings: `cd
   /tmp/omarchy-iptv-qa && python3 -m http.server 8765 --bind 127.0.0.1` (serving
   `gen-10k.m3u`), `omarchy bar set io.github.rmcdavid.iptv playlistUrl
   http://127.0.0.1:8765/gen-10k.m3u` [round 11: add it in Sources with `a`
   instead], wait for the load, stop the server
   (Ctrl+C), press `r`: banner `U+F0026 Playlist refresh failed (Connection
   refused) - showing cached copy from HH:MM - r retry`, footer `10,000 channels
   - cached HH:MM - offline`, notification `Playlist error` / `Could not fetch
   the playlist (Connection refused). Using cached copy from HH:MM.`, tooltip
   or footer says cached [TC-RFR-03, TC-RFR-10, TC-UI-03].
4. Restart the server, `r`: banner disappears (140 ms fade), footer back to
   `updated HH:MM` [TC-RFR-03].
5. Press `r` twice within 300 ms (or `r` then middle click): the journal shows
   one helper run [TC-RFR-04].
6. Stop the server, `omarchy restart shell`, open the guide immediately: the
   cached list renders at once, then the banner appears after the failed
   refresh [TC-RFR-06].
7. With the guide open and the cursor on row 50, serve a different file
   (`gen-real.m3u` renamed over `gen-10k.m3u`), press `r`: rows rebuild, the
   cursor is clamped, no crash [TC-RFR-07].
8. Serve `qa-empty.m3u` and `qa-not-m3u.html` in turn (copy them into the
   served directory, point `playlistUrl` at them): `Playlist has no channels`
   / `Parsed 0 channels from 127.0.0.1 - check the URL points at an M3U`, then
   the `Not an M3U file` reason (helper code `not_a_playlist`; at f03fef2 the
   guide shows the raw helper sentence instead, D-LIVE-03); the previous cache
   is kept and marked stale [TC-RFR-08, TC-RFR-09].
9. Restore `playlistUrl` to the US list.

#### US8 Install and uninstall

Covered by 5.2 (install) and 5.10 (uninstall); REL-01 repeats 5.2 from a clean
state with the README commands verbatim, REL-02 repeats 5.10.

### 5.5 Theme switch (TC-UI-05, M1.1-02)

```
current=$(cat ~/.local/state/omarchy/current/theme.name)      # retropc on this machine
omarchy theme set tokyo-night        # guide closed: bar re-skins; open the guide: menu tokens applied
omarchy theme set catppuccin-latte   # light theme, guide OPEN while switching: card, scrim, selected row, banner tint all change live
omarchy theme set "$current"
journalctl --user -t omarchy-shell --since -5m | grep -iE 'warn|error' | grep -v 'Qt.atob'
```

Expected: no restart needed, no new warnings (the `Qt.atob` deprecation lines
are pre-existing host noise, see the journal before install), the bar glyph
dimming tracks the new bar foreground, the empty-state glyph uses
`Color.menu.selectedText`. `omarchy theme set` accepts either `Tokyo Night`
or `tokyo-night` (it lowercases and dash-joins). Run at least three themes
(`omarchy theme list` has 23).

### 5.6 Multi-monitor, vertical bar, narrow screen (TC-A11Y-04, TC-BAR-10, TC-BRW-24)

- This machine has one monitor (`eDP-1`, PLAN A7), so TC-A11Y-04 is recorded
  `not run`. On a two-monitor machine: focus a window on monitor 2, press
  `SUPER + SHIFT + T`: the guide appears on monitor 2 only (no `screen` set,
  R13); each monitor shows one bar widget with the same state; scroll over
  either widget zaps once (ARCH risk 9); `pgrep -fc wayland-app-id=omarchy-iptv`
  is 1.
- Vertical bar (optional): `omarchy bar position left`; the widget shows the
  glyph only, name in the tooltip; `omarchy bar position top` restores.
- Narrow screen (optional): `hyprctl keyword monitor eDP-1,1366x768@60,0x0,2`
  halves the logical width to 683 px, under `Style.space(720)`: the column
  hides, `h`/`l` still change the scope label; `hyprctl reload` restores the
  configured mode.

### 5.7 mpv window and file checks (TC-PLAY-01/02, SEC-14, SEC-15)

```
scripts/qa-live.sh verify
# or by hand
hyprctl clients -j | jq '.[] | select(.class == "omarchy-iptv") | {class, title, pid, workspace: .workspace.name, floating, fullscreen}'
pgrep -af -- '--wayland-app-id=omarchy-iptv'                 # at most one line
ps -o args= -p "$(pgrep -f -- '--wayland-app-id=omarchy-iptv')" | tr ' ' '\n'   # argv items, URL last after --
stat -c '%a %n' ~/.cache/omarchy-iptv ~/.cache/omarchy-iptv/* ~/.local/state/omarchy-iptv ~/.local/state/omarchy-iptv/* /run/user/1000/omarchy-iptv /run/user/1000/omarchy-iptv/*
find ~/.config/omarchy/plugins/io.github.rmcdavid.iptv -newer ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/manifest.json -not -path '*/.git/*'
find ~/.config/omarchy/plugins/io.github.rmcdavid.iptv -name .git -prune -o -type l -print
```

Expected: `class` `omarchy-iptv`, `title` = channel name (also visible in
`hyprctl activewindow`), one pid, dirs 700 and files 600, the two `find`s
print nothing.

### 5.8 IPC verbs (R9, TC-BAR-09, SEC-17)

```
omarchy-shell io.github.rmcdavid.iptv status | jq .          # JSON: configured, channels, playing, nowPlaying (name, group; no URL expected, see D-QA-15), playlist status
omarchy-shell io.github.rmcdavid.iptv toggle                  # guide open/close (R9; scaffold lacks it, D-QA-04)
omarchy-shell io.github.rmcdavid.iptv play t:CNN.us           # an id from ~/.cache/omarchy-iptv/channels.json -> "ok"
omarchy-shell io.github.rmcdavid.iptv next                    # zap ring +1
omarchy-shell io.github.rmcdavid.iptv previous                # zap ring -1 (R9 name; scaffold has prev, D-QA-04)
omarchy-shell io.github.rmcdavid.iptv refresh                 # manual refresh -> notification
omarchy-shell io.github.rmcdavid.iptv stop
omarchy-shell io.github.rmcdavid.iptv play 'http://evil.example.test/x'   # "unknown", nothing launched
omarchy-shell io.github.rmcdavid.iptv play '--script=/tmp/x'              # "unknown"
qs ipc -n -p /usr/share/omarchy/shell show | grep -A9 'target io.github.rmcdavid.iptv'   # the verb list
```

### 5.9 Evidence capture

```
scripts/qa-live.sh evidence --apply --label us3-play        # journal since install, qs log tail, status, plugins, clients, theme, redaction grep
grim -o eDP-1 /tmp/omarchy-iptv-qa/tc-brw-05.png             # screenshot of the guide (grim captures layer surfaces)
omarchy-shell notifications showHistory                     # notification texts for 6.4 checks
journalctl --user -t omarchy-shell -f | grep --line-buffered omarchy-iptv   # follow during a step
```

Every failed step gets: the TC id, the screenshot, the journal excerpt and
the exact command that reproduces it, in the defect row (section 6).

### 5.10 Cleanup and uninstall (TC-INST-05, TC-INST-06, TC-INST-10, REL-02)

```
omarchy plugin disable io.github.rmcdavid.iptv               # TC-INST-05: entry and inline settings leave shell.json; widget gone; mpv exits
omarchy plugin enable io.github.rmcdavid.iptv                # comes back unconfigured (host semantics; README must warn)
scripts/qa-live.sh uninstall --apply                         # asks for confirmation (gum); --force skips it
# or by hand
omarchy-shell -q io.github.rmcdavid.iptv stop
omarchy plugin remove io.github.rmcdavid.iptv --yes          # disables (removes the bar entry), deletes the clone, rescans
rm -rf ~/.cache/omarchy-iptv ~/.local/state/omarchy-iptv /run/user/1000/omarchy-iptv
diff <(jq -S . /tmp/omarchy-iptv-qa/shell.json.before) <(jq -S . ~/.config/omarchy/shell.json)   # no output
find ~ -path '*omarchy-iptv*' -not -path '*/omarchy-iptv-qa/*'                                   # no output
```

Then remove by hand the `bindings.lua` line and the `omarchy-menu.jsonc`
entry added in 5.3, and delete `/tmp/omarchy-iptv-qa` once the report is
filed. `omarchy plugin remove` on a git checkout deletes it outright (no
backup); a non-git folder would be moved to `.<id>.bak.<stamp>` instead.

### 5.11 M3: hidden groups and the track picker (`scripts/dev-harness/m3-scenario.sh`)

Thirty checks over the harness IPC and real keys, against a REAL mpv playing
a generated 90 s file with two audio tracks (eng, titled; spa) and one srt
subtitle, served from 127.0.0.1. H1-H6 hide a group, watch it move under
HIDDEN, search past it, read it back from `state.json`, unhide it, and
repeat the hide with a real `x` through PanelKeyCatcher. T1-T6 ask the
player with the helper's own verb, open the picker with `t`, switch audio
and subtitles and confirm each switch on the real player by asking it
separately, drive Esc / t / j as real keys, and prove a stop clears the
rows. `--baseline v0.8.0` runs the same checks against that tree: 7 pass
(regression guards asserting an absence: H1, H2c, H5a, H5b, H6b, T5a, T5d)
and 23 fail. `--shots` writes `m3-hidden.png` and `m3-tracks.png` to the
scratch shots directory. Holds the display; the overlay must have keyboard
focus for the six real-key checks (see QA-RESULTS, M3 live pass).

## 6. Defect reporting

Template (one row in `docs/STATUS.md` "Defects", details in the handoff note):

```
D-<n> | P1/P2/P3 | <task id> | <TC id>: <one-line repro> | open
### D-<n> (<TC id>, <area>)  P<sev>  found <date> at <commit>
Steps: 1. ... 2. ...
Expected (doc + section): ...
Actual: ...
Evidence: /tmp/omarchy-iptv-qa/<label>/... , screenshot, journal lines
Notes: suspected file:line, workaround
```

Severity rule of thumb (PLAN.md section 6): P1 = a story cannot be completed
(guide will not open, nothing plays, settings not read, credentials leaked
to a third party); P2 = the story works but a documented behaviour is wrong
or degraded (wrong key, wrong grouping, a URL shown on screen, missing
notification); P3 = cosmetic or wording, or a hardening item with no
user-visible effect today.

### 6.1 Pre-filed defects from the scaffold review (commit 7a26b6d, 2026-09-12)

Found by reading the scaffold and running the qa- fixtures through it; not
fixed by QA (FE lanes own the code). Re-verify each after the merge; close
the ones the lanes already addressed.

| ID | Sev | Where | Finding | Suggested fix |
|---|---|---|---|---|
| D-QA-01 | P2 SEC | `Service.qml` `mpvProc.onExited` / `rememberStderr` / `notify()` | mpv's own error line contains the stream URL (verified: `mpv --msg-level=all=error -- 'http://user:secretpass@127.0.0.1:9/...'` prints `Failed to open http://user:secretpass@127.0.0.1:9/live/user/secretpass/123.ts.`); the last stderr line becomes the critical notification body and `lastError` (guide status line, IPC `status`). Violates R12 and UX 6.4 | body per UX 6.4 (`<name> did not play`), append a reason only after replacing every `scheme://[^ ]+` with the host; keep raw stderr out of `lastError` |
| D-QA-02 | P2 SEC | `bin/omarchy-iptv` `make_channel` (`name = title or tvg-name or url`) | an empty `#EXTINF` title makes the raw stream URL the channel name (fixture `qa-attrs.m3u`, entry `#EXTINF:-1,` + `http://user:secret@...`): rendered in the guide row, bar label, tooltip, notifications and persisted in `state.json` recents | fall back to `tvg-id`, then `Channel <n>` (or the URL host), never the URL |
| D-QA-03 | P2 FUNC | `bin/omarchy-iptv` `make_channel` | multi-group `group-title="Animation;Kids;Religious"` is kept whole as the display group; R5 requires the first segment (full string stays in `searchKey`, which already works). Effect: `gen-10k.m3u` with 10 % multi-group entries yields 1,068 groups instead of ~120; the US list gets phantom groups | split on `;`, take the first non-empty trimmed segment, `Ungrouped` if none |
| D-QA-04 | P2 FUNC | `Service.qml` `IpcHandler` | verbs are `play stop next prev refresh status`; R9 requires `toggle` and `previous`; README documents the same list | add `toggle`, rename `prev` to `previous` (keep `prev` as an alias if cheap) |
| D-QA-05 | P3 | `Service.qml` settings, `README.md` table | `refreshMinutes` default 60 / min 5 in code and README vs R2 and `manifest.json` (360 / 15 / 1440); `barLabelMaxWidth` not read | align clamps with R2; add `barLabelMaxWidth` to the widget |
| D-QA-06 | P3 SEC | `bin/omarchy-iptv` `decode_text` | `gzip.decompress` has no inflated-size cap: a 100 KB gzip bomb inflates to 100 MB+ in memory (64 MB cap applies to the compressed download only); same risk for the EPG path when implemented | stream through `gzip.GzipFile(...).read(MAX_SOURCE_BYTES + 1)` and raise `too_large` |
| D-QA-07 | P3 | `bin/omarchy-iptv` `parse_m3u` / `stream_scheme` | `http://` with no host passes the allow-list (`qa-schemes.m3u`, `bad-empty-host`); mpv fails at play time with a confusing notification | require a non-empty `netloc` for http/https/rtsp/rtmp/mms/srt |
| D-QA-08 | P3 | `bin/omarchy-iptv` `normalize_text`, `Model.js` `normalizeText` | decomposed accents (NFD, `Cafe` + U+0301) are not folded (`qa-nonascii/qa-unicode.m3u`, `nfd.test`), so `cafe` matches only by substring luck; playlists exported from macOS tools are NFD | NFKD-normalise then drop U+0300-U+036F in both implementations (shared vectors) |
| D-QA-09 | P3 | `bin/omarchy-iptv` `_SAFE_OPTION` | option-looking `#EXTVLCOPT` keys such as `--script` are stored as `options["vlc:--script"]` (`qa-headers.m3u`, `optkey.test`); stored only in M1, but M2 may apply options | reject keys starting with `-` with a warning |
| D-QA-10 | P3 | `bin/omarchy-iptv` `make_channel`, `Model.js` `headerArgs` | empty `#EXTVLCOPT:http-user-agent=` yields `headers.User-Agent: ""` and an empty `--user-agent=` argv item | drop empty header values |
| D-QA-11 | P3 | `Model.js` `splitMpvArgs` | the token regex is case-insensitive but the reserved lookup is not: `--INPUT-IPC-SERVER=x` is accepted; mpv then exits 1 (`option not found`), surfacing as a stream failure instead of the documented console warning | lowercase-only regex (mpv option names are lowercase) |
| D-QA-12 | P3 | `bin/omarchy-iptv` `read_local_source` | error messages embed the resolved local path (`playlist file not found: /home/...`, `refusing to read /proc/...`); UX 6.3 wants `File not found`; ARCH 9 says no URLs/paths in output | user-facing message without the path; path on stderr only |
| D-QA-13 | P3 | `bin/omarchy-iptv` `cmd_playlist` | an HTML login page (`qa-not-m3u.html`) is reported as `empty_playlist` / `no playable channels found`; UX 6.3 distinguishes `Not an M3U file` | new code when neither `#EXTM3U` nor any `#EXTINF` is present (shipped as `not_a_playlist` in f03fef2; `Model.statusReason` still only knows `not_m3u`, D-LIVE-03) |
| D-QA-14 | P3 | `BarWidget.qml` | label elided at 24 characters (`Model.elide`) instead of `Style.space(barLabelMaxWidth)`; single glyph for all states (R7 wants U+F0502 / U+F0567 / U+F0503); tooltips differ from UX 6.3 | lane B scope (M1-11); listed so the matrix has an owner |
| D-QA-15 | P3 | `Service.qml` IPC `status` | returns `nowPlaying.url` (full stream URL with provider credentials) on the console; R12 says never beyond scheme+host. ARCH section 5 lists `path` in the mpv status contract, so this needs a PO ruling | return `host` instead of `url`, or redact to scheme+host |
| D-QA-16 | P3 | `Service.qml` `notify()`, `mpvProc.onExited` | headline `Could not play <name>`, urgency `critical`, glyph U+F0567 for every notification; UX 6.4: `Stream failed` / `<name> did not play`, normal, glyph U+F0503, `-r <id>`; refresh/EPG notifications absent | lane B scope (M1-14) |
| D-QA-17 | P3 | `README.md` | keyboard map is the ARCH draft (Ctrl chords, Tab cycles groups), settings table wrong (see D-QA-05), no mention that `omarchy plugin disable` drops inline settings (TC-INST-05), no `previous`/`toggle` verbs | update with UX 3 and R2/R9 (M1-18) |
| D-QA-18 | P3 | `bin/omarchy-iptv` `read_http_source` | the `Content-Encoding: gzip` branch is dead code (both branches return `data`); harmless because `decode_text` sniffs the magic bytes | remove or make it meaningful |

Observations that are not defects (recorded so nobody re-files them):
`#EXTINF` without a comma yields the trailing text as the title; an unquoted
`group-title=News Sports` yields group `News` and a title starting with
`Sports,` (VLC does the same); the en dash U+2013 is kept in `searchKey`
because only ASCII punctuation collapses (`qa-unicode.m3u`, `ard.de`);
`file:///etc/passwd` as the *source* parses to `empty_playlist` (the user's
own file); `url-tvg` beats `x-tvg-url` on the `#EXTM3U` line; a second
`#EXTINF` before any URL replaces the first (the first is lost silently).

## 7. Fixture catalogue

All fixtures are synthetic, deterministic, and small (largest 7 KB). Unit
tests never touch the network (QA-ASSETS.md). ASCII-only files live in
`tests/fixtures/`; files that must contain UTF-8 or binary bytes live in
`tests/fixtures/qa-nonascii/` because `scripts/check.sh` greps every regular
file directly under `tests/fixtures/` for non-ASCII bytes and skips
subdirectories (`[[ -f $file ]] || continue`). Regenerate nothing by hand: the
files are the source of truth; `qa-epg.xml.gz` is the byte-exact gzip twin of
`qa-epg.xml` (no filename, mtime 0, level 9; `python3 -c "import
gzip;print(gzip.open('tests/fixtures/qa-nonascii/qa-epg.xml.gz').read()==open('tests/fixtures/qa-epg.xml','rb').read())"`
prints `True`).

Run any M3U through the helper without tests:

```
python3 bin/omarchy-iptv playlist --url "file://$PWD/tests/fixtures/qa-groups.m3u" --cache-dir /tmp/omarchy-iptv-qa/cache-qa
jq -c '.channels[] | {id, name, group, searchKey, headers}' /tmp/omarchy-iptv-qa/cache-qa/channels.json
```

| File | Purpose | Expected (scaffold behaviour today in brackets where it differs) |
|---|---|---|
| `qa-groups.m3u` | multi-group `A;B;C`, `#EXTGRP` persistence and clearing, `group-title` precedence, padding, leading semicolon, no group | 10 channels; groups per R5: `Animation` [`Animation;Kids;Religious`, D-QA-03], `UK \| SPORTS`, `Sports`, `Sports`, `Movies`, `News`, `Ungrouped`, `Padded`, `Leading Semicolon` [`;Leading Semicolon`], `Ungrouped`; `searchKey` of the first is `multi group channel animation kids religious` |
| `qa-attrs.m3u` | `#EXTM3U` hints, bare/uppercase/repeated/empty attributes, duplicate tvg-id HD/SD, exact duplicate URL, commas in titles, float/zero durations, broken `#EXTINF`, empty title with credentialed URL, logo schemes, tabs, blank line before URL, lost first `#EXTINF`, 300-char title | 22 channels; `epgUrlHint` = `http://epg.example.test/guide.xml.gz`; ids `t:espn.us`, `u:a3d5424f`, `u:8e5692d2` (HD/SD), `u:cc5a0021` and `u:cc5a0021#2`; `chno` `12`; `Broken EXTINF Without Comma` is the title; `Name From tvg-name`; the empty-title entry must not be named after the URL [it is, D-QA-02]; `Logo File Scheme Dropped` has no `logo`; `Upper` group; `Second` wins for the repeated attribute; empty `group-title` -> `Ungrouped`; `t:spaced.id`; `Second Of Two EXTINF Is Kept` |
| `qa-headers.m3u` | `#EXTVLCOPT` UA/referrer/other, `#KODIPROP` stream/manifest headers and options, option line before `#EXTINF`, bare CR (0x0D) inside a value, percent-encoded CRLF, unsafe header name, shell metacharacters, option-looking key, empty value, uppercase key, no leak past a skipped URL | 11 channels, warnings `dropped header with unsafe name for KODIPROP Percent Encoded CRLF And Bad Name` and `1 entries skipped: unsupported URL scheme`; `vlc.test` headers `User-Agent`/`Referer` + `options.vlc:network-caching`; `clean.test` no headers; `before.test` `Before/1.0`; `cr.test` `Evil/1.0 X-Injected: yes` (single line); `kodi.test` three headers + two `kodi:` options; `kodicrlf.test` `X-Inject: a  X-Evil: b`, `X-Ok: 1`, `Bad\nName` dropped; `meta.test` value verbatim; `optkey.test` UA `--script=/tmp/evil.lua` as a value only [and `options.vlc:--script`, D-QA-09]; `emptyua.test` no header [empty header, D-QA-10]; `case.test` `Upper/1.0`; `afterskip.test` no headers |
| `qa-schemes.m3u` | allow-listed schemes, case, whitespace, option-looking suffix inside the line, every dropped scheme including mpv pseudo-protocols, orphan URL lines | 13 allowed [14: `http://` accepted, D-QA-07]; warnings `21 entries skipped: unsupported URL scheme`, `2 URL lines without #EXTINF skipped` |
| `qa-empty.m3u` | valid header, no entries | exit 1, code `empty_playlist`, guide `Playlist has no channels` |
| `qa-not-m3u.html` | provider login page instead of a playlist | exit 1, code `not_a_playlist` (verified at f03fef2; v0.1 expected the name `not_m3u`); the fake `#EXTINF` inside `<p>` is not an entry |
| `qa-epg.xml` | XMLTV: +0100 / -0500 / +0530 / no offset / 12-digit timestamps, overlap, gap, missing stop, far-future/past, orphan programme, channel without programmes, `@SD` id, character references for non-ASCII, `&amp;`, `<desc>`/`<category>`/`<episode-num>`/`<icon>` ignored | 27 programmes, 12 channels; expected now/next at T0 = 1789244100 listed in the file header comment (TC-EPG-06/07) |
| `qa-nonascii/qa-epg.xml.gz` | gzip twin of `qa-epg.xml` (deterministic) | identical `epg-now.json` (TC-EPG-05) |
| `qa-nonascii/qa-unicode.m3u` | UTF-8 names and groups: French, Polish, German (en dash, sharp s), Russian, Arabic, Japanese, emoji, NFC vs NFD, uppercase accent, non-ASCII URL path | 11 channels; `searchKey`s `tele quebec quebec`, `tvp lodz polska`, `das erste <U+2013> strasse deutschland`, Cyrillic/Arabic/CJK lowercased and kept, `emoji <U+1F4FA> channel fun`, `cafe nfc normalisation`, `cafe nfd normalisation` [`cafe<U+0301> nfd ...`, D-QA-08], `ecole uppercase accent normalisation`; ids `t:<tvg-id>` |
| `qa-nonascii/qa-bom-crlf.m3u` | UTF-8 BOM, CRLF, trailing spaces, blank CRLF line, `#EXTGRP` across CRLF, `#EXTVLCOPT` across CRLF, no final newline | 3 channels, groups `CRLF`, `Persisted`, `Persisted`; no `\r` in any URL; `crlf2.test` UA `CRLF/1.0` |
| `basic.m3u`, `attributes.m3u` (ARCH, existing) | scaffold parser tests | unchanged |
| generated (never committed) | `scripts/gen-playlist.py` outputs for PERF-* and offline runs (`gen-10k.m3u`, `gen-10k.xml.gz`, `gen-real.m3u`, `gen-real.xml`, `gen-dead.m3u`) | see section 4 and 5.3 |

Out of scope on purpose: lone-CR (classic Mac) line endings, UTF-16
playlists, `#EXTINF` with `tvg-id` containing quotes, playlists larger than
64 MB (covered by a sparse file in SEC-11, not a fixture).

## 8. Open questions for the lead before the live pass

1. Merge state: both lanes merged into `main` with `scripts/check.sh` green;
   which commit id do I test? Is `Copy.js` (UX 5.9) present so the microcopy
   greps work?
2. Keybinding and menu lines: may QA add the two README one-liners to
   `~/.config/hypr/bindings.lua` and `omarchy-menu.jsonc` for TC-BRW-01/04 (and
   remove them in 5.10), or should those rows stay `not run`?
3. EPG-matched playlist: the public pairs in QA-ASSETS.md match only
   partially; the generator pair (`gen-real.m3u` + `gen-real.xml`) matches
   fully but its streams are dead. Is there a real playlist + XMLTV pair with
   matching ids for TC-EPG-02 on a live stream, or is the generator pair
   acceptable for the EPG rows and `us.m3u` for playback?
4. Clock seam for EPG tests: `tests/test_epg.py` needs the helper's notion of
   "now" pinned to T0 (a `--now <epoch>` flag on `epg`, or an env var).
   Which one did lane A implement?
5. D-QA-15 ruling: may the IPC `status` verb print the stream URL, or only
   the host?
6. Theme names for TC-UI-05: `tokyo-night` and `catppuccin-latte` (one dark,
   one light) plus `retropc` (current) unless you prefer others.
7. The optional destructive checks (TC-PLAY-09 `kill -STOP`, TC-BAR-10 bar
   position, TC-BRW-24 monitor scale): run them or skip?
