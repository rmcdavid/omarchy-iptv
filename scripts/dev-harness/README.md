# Dev harness

A standalone Quickshell config that loads `Service.qml`, `Guide.qml` and
`BarWidget.qml` straight from this repo with fake `shell`, `manifest`, `bar`
and `settings` objects, plus scratch XDG directories, so the plugin can be
smoke-tested without installing it into `~/.config/omarchy/plugins`.

Running it opens real windows (a thin fake bar strip at the top of the
screen and, on `--open`, the guide overlay) on the current Wayland session.
Keep runs short; `run.sh` kills Quickshell after `--timeout` seconds
(default 15). An `EXIT` trap reaps everything it started (the fixture HTTP
server, Quickshell and any harness mpv) on a normal exit, the timeout,
Ctrl-C or SIGTERM; a SIGKILL of `run.sh` cannot be trapped, so the next
start also reaps a stale fixture server. The playlist/EPG source is echoed
as `scheme://host` only and `updateEntryInline` logs the entry's keys, never
its values: a real provider URL would carry credentials into the terminal
scrollback.

## Every scenario writes a transcript. Never summarise one from a tail.

**Read this before you run a scenario, and before you report what one said.**

Every `*-scenario.sh` in this directory calls `qa_transcript_start` (in
`scripts/qa-lib.sh`) and prints the path it is writing to, as its first line:

```
== transcript /run/user/1000/omarchy-iptv-harness/transcripts/m3-20261006-201455-48213.out
```

That file is the run's evidence. It holds every `PASS`/`FAIL` line, every
diagnostic, stderr as well as stdout, and it outlives the run: it is 0600, in
a 0700 directory under the harness scratch, and `run.sh clean` does not remove
it. **Report from the transcript, not from the terminal.** If you want the
headline, read the summary line out of the transcript; if you want to know
which checks failed, `grep '^FAIL' <the path it printed>`.

### Why this rule exists, and what it cost

On 2026-09-26 one live run of `m3-scenario.sh` answered **17 passed, 14
failed** -- and *which fourteen is still unknown*. The scenario was not at
fault and no assertion was missing. The run was backgrounded and its output
was piped through `tail -n 3`, so the 31 lines naming every decision it had
just observed existed only in a pipe that was then thrown away. All that
survived was a count. The row is F-M3-1; this half of it is (b).

Three things follow, and the first two are the ones people get wrong:

1. **`tail`, `| head`, `2>&1 | grep -c PASS` and "it printed 17/14" are not
   reports.** A scenario's output is the finding. Summarising it from a tail
   discards the finding and keeps the arithmetic, which is the one part
   nobody can act on.
2. **Backgrounding a scenario is fine; losing its stdout is not.** The
   transcript is what makes a backgrounded run safe to background -- the
   evidence is on disk whatever happens to the terminal.
3. **Do not re-invent this per scenario.** Before F-M3-1 the pattern lived in
   exactly one file, `rewind-scenario.sh`, as its own local habit, and the run
   that lost its evidence was a different scenario. `scripts/qa-lib-test.sh`
   now counts the *population*: every scenario in the glob must source
   `qa-lib.sh` above the call and then call
   `qa_transcript_start <name> || exit 2` exactly once, so the next scenario
   added here cannot be the one that forgets. (Both halves earn their keep:
   wiring this up, `m3-scenario.sh` got the call without the `.` line, which
   is `command not found` followed by `exit 2` -- a scenario that refuses to
   run, complaining about a missing command rather than a missing transcript.)

### Writing a scenario

```bash
. "$ROOT/scripts/qa-lib.sh"
...
qa_transcript_start <name> || exit 2     # after the preflight, before the first evidence
```

* The call sits **after** argument parsing and the refusals that exit before
  anything starts (a refusal is one line on stderr, not a transcript), and
  **before the first line of evidence** -- including the line that names which
  tree is under test, because a transcript that cannot say that is evidence
  for nothing. Both halves bite, and the first was false here while this page
  asserted it: `rewind-scenario.sh` opened the transcript above four of its
  own `--baseline` / `--tree` refusals and `player-scenario.sh` above one, so
  a mistyped lever printed a path and left an almost-empty file behind. Both
  validate above the call now and print the line that *names* the tree below
  it. `scripts/qa-lib-test.sh` drives both refusal paths and asserts that no
  transcript lands, so this bullet is observed rather than promised.
* In a scenario with a **`check-tree` mode** the call goes on the `live|""`
  arm of the dispatch, never above it. `scripts/check.sh` runs
  `chno-entry-scenario.sh`, `pip-scenario.sh` and `id-rotate-scenario.sh` in
  `check-tree` mode on every commit, and a gate step may neither print a path
  nobody asked for nor leave a file behind. It goes on that arm *above*
  `preflight`, so a live run's transcript covers both halves -- the summary at
  the bottom counts both, and a transcript holding one of them cannot be
  summarised from.
* `<name>` is a filename, not a path: it is refused if it could be one, and
  the file lands flat as `<name>-<stamp>-<pid>.out` with no per-scenario
  subdirectory. That is deliberate. `rewind-scenario.sh`'s R18 sweeps the
  transcript for leaked URLs and `/rewind/` is one of the patterns it sweeps
  for, so a `transcripts/rewind/` path would make the file's own name a leak
  hit and turn a privacy check red on itself.
* A **background process the scenario starts inherits the transcript pipe**
  unless it redirects **both** its own stdout and its own stderr; one that did
  not would keep `tee` alive after the run. Redirect them to a file rather
  than to `/dev/null` where a traceback would be worth having. This page used
  to say every scenario here already did -- naming the harness, the fixture
  servers and the sweepers -- while four starts did not, and two of them were
  the sweepers: `argv-scenario.sh`'s and `rewind-scenario.sh`'s redirected
  neither stream, `rewind-scenario.sh`'s `ffmpeg` only stderr and
  `sources-scenario.sh`'s silent listener only stdout. So the sentence is a
  count now, not a claim: `scripts/qa-lib-test.sh` scans every `&`-terminated
  line in every `*-scenario.sh` and fails if any of them leaves a stream
  attached (11 starts, 0 unredirected; 4 of the 11 before this).
* **The transcript is a sink (CLAUDE.md rule 5).** A scenario's stdout can
  carry a playlist URL with provider credentials in it --
  `argv-scenario.sh` drives a synthetic one on purpose -- so the transcript is
  0600 in a 0700 directory, and `qa_transcript_start` **refuses** rather than
  writing into a directory group or other can enter -- *both* halves of that,
  driven separately: a 0750 and a 0705 directory the run cannot tighten are
  each refused in `scripts/qa-lib-test.sh`, which is what makes the mask
  itself observed and not just the existence of a check. Left to create its
  own file, `tee` would use its own umask and leave the transcript at 0644,
  world-readable; that is measured there too, driving the unsafe form for real
  at an explicit umask 022, and the 0600 the shipped form produces is asserted
  at three umasks because it comes from creating the file ourselves rather
  than from whatever the caller happened to have set.

### Reading your own transcript inside a scenario

The transcript is written by a `tee` on the far side of a pipe and the shell
does not wait for it, so a scenario that scans its own transcript is scanning
a file that may be short of its most recent lines. Measured 2026-10-06, 30
runs per case: a line printed and then read back by a bash builtin was absent
**30 of 30 times**; read back through a `grep`, where the fork is itself the
delay, it was present 12 of 12 on an idle machine and absent **6 of 30 with
the cores oversubscribed twice over**. `rewind-scenario.sh`'s R18 is exactly
that shape -- a privacy sweep over its own transcript -- so under load it
could sweep a short file and miss the URL it exists to catch.

Call the barrier first. It is bounded and it says so when it gives up:

```bash
qa_transcript_sync 5 || bad "the transcript did not catch up; the sweep below reads a short file"
qa_leak_scan 'PASS|FAIL' "$LEAK_ERE" "$QA_TRANSCRIPT"
```

## How `qs.Commons` / `qs.Ui` resolve (Quickshell 0.3.1)

Quickshell maps the `qs` import prefix to the **config root** (the
directory given to `quickshell -p`). `run.sh` therefore builds a scratch
root under `$XDG_RUNTIME_DIR/omarchy-iptv-harness/root/` containing a copy
of `shell.qml` and two symlinks, `Commons -> /usr/share/omarchy/shell/Commons`
and `Ui -> /usr/share/omarchy/shell/Ui`. Files loaded from outside that root
(the plugin's own QML, referenced by absolute `file://` URLs) still resolve
`import qs.Commons` because the mapping is engine-wide -- the same mechanism
the real shell uses for third-party plugins. No symlinks are ever created
inside the plugin folder (the validator rejects them).

`QML_IMPORT_PATH`-style mapping (`/tmp/qmlroot/qs/{Commons,Ui}`) is only
used by `scripts/check.sh` for `qmllint`; Quickshell itself needs the root
layout above.

## Scratch layout and environment

```
$OMARCHY_IPTV_HARNESS_DIR   (default $XDG_RUNTIME_DIR/omarchy-iptv-harness)
  root/      shell.qml + Commons/ Ui/ symlinks
  cache/     XDG_CACHE_HOME  -> cache/omarchy-iptv/{channels,playlist-status,epg-now}.json
  state/     XDG_STATE_HOME  -> state/omarchy-iptv/state.json
  runtime/   XDG_RUNTIME_DIR -> runtime/omarchy-iptv/mpv.sock (+ hypr -> real hypr dir)
  fixtures/  generated harness.m3u (and test.ts with --serve)
  shots/     screenshots from `run.sh shot`
  transcripts/  one 0600 file per scenario run (0700 dir); NOT removed by
                `run.sh clean`, because it is the run's evidence (F-M3-1)
```

Because `XDG_RUNTIME_DIR` is redirected, `run.sh` exports `WAYLAND_DISPLAY`
as the absolute socket path (libwayland accepts that) and symlinks the real
`hypr/` directory so `hyprctl` keeps working. `run.sh ipc` re-exports the
same runtime dir so `qs ipc` can find the instance.

**Two IPC targets, two subcommands.** The harness shell declares its own
`IpcHandler` under the target `harness` -- the inspection verbs (`state`,
`widget`, `numberState`, `query`, ...) that exist only here -- and the plugin's
`Service.qml` declares its own under `io.github.rmcdavid.iptv`, the verbs a
user actually binds. `run.sh ipc <fn>` reaches the first,
`run.sh plugin-ipc <fn>` the second; both apply the same environment, because
reaching either needs the scratch `XDG_RUNTIME_DIR` **and** the absolute
Wayland socket path (`SPIKE-LIVE-REWIND.md` 12.5 measured each variant,
including the two that fail). `plugin-ipc` can only ever reach the harness: the
config root it passes is the scratch root, and the live install answers the
same target name under a different one. Before it existed every scenario
needing a plugin verb carried the incantation by hand (F-RWD-14).

Environment read by `shell.qml` (all set by `run.sh`): `OMARCHY_IPTV_ROOT`,
`OMARCHY_IPTV_PLAYLIST`, `OMARCHY_IPTV_EPG`, `OMARCHY_IPTV_OPEN`,
`OMARCHY_IPTV_VERTICAL`, `OMARCHY_IPTV_SHOW_NAME`, `OMARCHY_IPTV_LABEL_MAX`,
`OMARCHY_IPTV_MPV_ARGS`.

## Usage

```bash
scripts/dev-harness/run.sh --open                    # fixture playlist, guide opens, 15 s
scripts/dev-harness/run.sh --open --fake-epg         # + synthetic epg-now.json in the cache
scripts/dev-harness/run.sh --open --serve --timeout 40   # local test video on 127.0.0.1:8765
scripts/dev-harness/run.sh --open --playlist /nonexistent.m3u --keep   # error banner over a kept cache
scripts/dev-harness/run.sh --open --vertical         # glyph-only bar widget
scripts/dev-harness/run.sh --open --order number      # channelOrder=number (M2-03)
scripts/dev-harness/run.sh --open --entry-ms 3000 --no-bar-number
scripts/dev-harness/run.sh --open --window floating   # harness-only window mode (headless cage)
scripts/dev-harness/run.sh ipc state                 # the harness's own target
scripts/dev-harness/run.sh plugin-ipc status         # the plugin's target: the verbs a user binds
scripts/dev-harness/run.sh plugin-ipc back 10        # argv is passed through untouched
scripts/dev-harness/run.sh clean
```

`run.sh` with no recognised subcommand prints its own header block and exits
2; the header is scanned to the first non-comment line rather than cut at a
line number, so a new option is listed by existing.

### Headless: `--window floating`

In production the guide is a `PanelWindow` on the layer-shell Overlay layer
with exclusive keyboard focus. A compositor with no `zwlr_layer_shell_v1` --
the headless `cage` of `docs/SPIKE-CAGE-HEADLESS.md` -- never maps it, so
under cage the guide answered over IPC but no pixel and no keystroke ever
reached it. `--window floating` hosts the same content in a `FloatingWindow`
(an xdg toplevel, which cage fullscreens and hands the keyboard to), so
`grim` captures it and `wtype` reaches it. Measured inside cage: the guide
maps 2.3 s after launch, the capture carries the shell-resolved
`Color.menu.background` on half a million pixels, and `wtype` filters the
rows through the guide's own search path.

The switch is `Guide.qml`'s `harnessFloatingWindow`, a plain property with
the production default; `shell.qml` hands it in as an INITIAL property
through `Loader.setSource` when `OMARCHY_IPTV_HARNESS_WINDOW=floating`, so
the guide's window `Loader` decides once at creation and the layer-shell
`Component` is never instantiated in floating mode (its `WlrLayershell`
attached properties are a creation error on a platform without the
protocol). Nothing in the real shell sets it, and it is not a setting.
`ipc theme` reports the resolved tokens and which window the loaded guide
says it has, so a capture is checked against the running value.

What does not transfer: focus semantics. The floating window has ordinary
toplevel focus, not the exclusive layer-shell focus, so cases about focus
itself stay on the real shell; cases about what is painted and what a key
does to the model run here.

The first keystroke can be lost (F-HARNESS-1 on the board). Measured by the
verifier: the FIRST `wtype` keystroke into a fresh floating shell is
intermittently dropped -- 1 of 4 fresh shells received `sky` as `ky` -- and
a row count cannot tell the two apart, because `sky` and `ky` both filter
the 20 fixture rows to 3. So a headless keystroke scenario must:

1. assert the exact query string read back over IPC (`ipc state`, the
   `guide.query` field), never a row count;
2. before grading, either send a throwaway key first, or reset with
   `ipc query ""` and retry the typing once.

`run.sh key` and `run.sh type` now carry both of those, once, so a scenario
cannot get it wrong by forgetting: `key` sends one Shift press per shell before
its first real key (keyed to the pid file, so a fresh shell primes again), and
`type` reads the query back and retries once. `--to-compositor` deliberately
skips the primer -- its chord is not aimed at the guide's fresh surface, and
firing the primer there used to mark the shell primed and leave the next real
key unprotected. The list above stays because it is still what a scenario
asserting a keystroke by hand has to do.

Drive a running harness from another terminal:

```bash
H=scripts/dev-harness/run.sh
$H ipc open '{}'          $H ipc close        $H ipc toggle
$H ipc query sky          $H ipc mode         $H ipc move 1      $H ipc scope 1
$H ipc setScope favorites $H ipc activate true  # Space semantics (keep open)
$H ipc favorite           $H ipc remove       $H ipc stop        $H ipc refresh
$H ipc zap 1              $H ipc set showChannelName false
$H ipc state              # JSON dump of guide + service state
$H ipc widget             # JSON dump of the bar widget (glyph, label, number, tooltip)
$H ipc channel 101        # M2-03: tune by channel number; the service's own verb
$H ipc chnoIndex          # M2-03: { hasNumbers, count, duplicates, maxLabelLen }
$H ipc tooltip            # last tooltip text the widget asked the bar to show
$H ipc pip toggle         # M2-05: the service's own verb (on | off | toggle)
$H ipc pipKey             # M2-05: the guide's p key, through the same entry point
$H ipc pipState           # M2-05: { available, on, applying, reason, provider, playerPid }
$H ipc focusState         # F-M3-1: where the keyboard is -- { ok, open, keyboard, role, item,
                          #   blocked, window, scanned, exhausted }. What `key` and `type` ask.
$H key -k Tab             # real key events via wtype -- REFUSES unless the guide has the keyboard
$H key j j f              # e.g. list mode: down, down, favorite
$H key --to-compositor -k F13   # a chord for the COMPOSITOR: skips the focus check (not the lock one)
$H type sky               # type text and prove it arrived, by reading the query back
$H shot search            # grim screenshot -> shots/search.png
```

### `key` and `type` refuse rather than type blind (F-M3-1 half (a))

`run.sh key` uses `wtype`, which delivers real key events through the
compositor -- to whatever surface holds the keyboard, which on a bad day is
the terminal the scenario runs in, the editor behind it, or a lock prompt,
where every keystroke registers as a failed unlock attempt. Neither failure is
visible in a scenario's own assertions: a key that landed elsewhere reads
exactly like a guide that did not react, and `sky` arriving as `ky` still
filters 20 rows to 3. So both verbs ask first and **exit 3** naming what they
found, rather than typing into an unknown surface. Two refusals:

* **`hyprlock` is up.** Never escapable, no flag. `pgrep -x hyprlock` -- `-x`,
  the process *name*, because `-f` matched an ancestor shell whose command line
  merely contained the word and refused every keystroke with nothing locked.
* **The guide has not got the keyboard.** Asked over `ipc focusState`, which
  walks the guide for the deepest `activeFocus` item; `activeFocus`, not
  `focus`, because a window that loses activation keeps `focus` true while the
  keys go elsewhere. The reply distinguishes "the guide is CLOSED", "another
  surface holds the keyboard" and "the walk gave up, so I cannot tell"
  (`exhausted`), and it fails **closed**: anything unreadable refuses.
  Escapable with `--to-compositor`, which **must come first** -- everything
  after it belongs to `wtype`, whose own `--` means "the rest is text" -- and
  which exists for a chord aimed at the compositor, not for making a failing
  scenario pass. It skips the focus check only, never the lock one, and it also
  skips the F-HARNESS-1 shift primer, so it cannot spend the guide's priming on
  a foreign surface.

`type` has no `--to-compositor`: it proves the text reached the *guide* by
reading the query back, so a chord aimed at the compositor has nothing for it
to prove. It also carries the F-HARNESS-1 compensation so a scenario cannot
forget it: the first `wtype` keystroke into a fresh shell is intermittently
swallowed (1 fresh shell in 4), so `key` sends one Shift press per shell
before the first real key, and `type` asserts the query it read back and
retries once. A steal *after* the front check ends on the guard's verdict too
-- exit 3, nothing typed -- not on a two-attempt failure message.

Operationally: `OMARCHY_IPTV_FOCUS_TIMEOUT` (default 5 s) bounds the wait for
the reply and a timeout refuses rather than typing blind; a harness started
*before* this change has no `focusState` verb, so `run.sh reap` and restart it
or every key refuses; and `--instance` does **not** reach `key` or `type` --
route a second instance with `OMARCHY_IPTV_HARNESS_INSTANCE=2`, because a flag
after `key` is argv for `wtype` to type. The decision table is driven in
`scripts/qa-lib-test.sh` against a stubbed transport.

### Sources (M2-01)

The fake `updateEntryInline` applies the entry to the fake `barConfig`
exactly like the host does (full-entry replace, `id` forced, `false` when
nothing changed), so `switchSource` / `addSource` round-trip through the
same settings binding the service uses in the real shell. The log line
still names the entry's keys only. Source signals
(`sourceProbeFinished`, `sourceSwitched`, `sourceRemoved`,
`sourcesPersistFailed`) are logged as `[harness] ...` lines; their payloads
are URL-free by contract.

Service actions over IPC (arguments may carry a URL or path; results never
do; pass `""` for an argument you do not need):

```bash
$H ipc addSource /path/or/url "" ""        # -> {"ok":true,"code":"ok","message":"","id":"<key>"}
$H ipc addSource http://h/x.m3u http://h/e.xml "My label"
$H ipc updateSource <key> '{"label":"NAS"}'            # label / epgUrl commit at once
$H ipc updateSource <key> '{"playlistUrl":"/new.m3u"}' # probes first, re-keys on success
$H ipc switchSource <key>      $H ipc retrySource <key>     $H ipc removeSource <key>
$H ipc cancelProbe             # while probing: discards the probe's cache dir
$H ipc xtream http://127.0.0.1:8765 user 'pa ss'       # -> addSource of the built URLs
$H ipc sources                 # JSON of service.sources (id/label/host/kind/counts, no URL)
$H ipc editMasked <key>        # the edit-form view with playlistMasked / epgMasked only (alias: sourceEdit)
$H ipc signals                 # the last 20 source signal payloads (sourceProbeFinished, sourceSwitched,
                               #   sourceRemoved, sourcesPersistFailed, configuredChanged), oldest first
$H ipc failPersist true        # takes updateEntryInline off the shell api (a host that cannot write
                               #   our entry) until `failPersist false`; a false RETURN is not a failure
$H ipc activeCache             # cache/omarchy-iptv/sources/<key> of the active source
$H ipc set playlistUrl /path   # CLI parity: reconciles into the history (origin cli)
$H ipc setStored playlistUrl /path  # `set` without the user-config re-read: the host stores the value
                               #   but has not published it, so the plugin still sees the previous one
$H ipc hostEntry               # {"stored":"<key>","published":"<key>"}: what the host has stored for our
                               #   entry vs what it has handed the plugin. They differ by one write.
$H ipc state                   # + activeSourceKey, cacheReady, probing, switching, sourceErrors, settingsInvalid,
                               #   canAddSource; guide: returnMode, sourceCursor(Kind), formFocus, formActive,
                               #   formProbing, sourcesNotice (the Sources result line: a failed switch probe),
                               #   sourcesProbeText (`Fetching from <host>...` while a switch probes),
                               #   invalidSettingsText (UX 5.4 sentence for a CLI-invalid playlistUrl),
                               #   footerHint (tags stripped) and `form` (kind, origin, sourceId, focus, error,
                               #   values as { value: masked, length, masked, revealed } per field; credentials are ****)
```

`state().guide.form` masks with the plugin's own `Model.js`, which `run.sh`
copies into the scratch root next to `shell.qml`; a raw form value never
reaches the terminal.

`run.sh --source2 SRC` seeds the history with a second, never-fetched
record before start (helper `state source add`), so `switchSource` takes
the probe path. `OMARCHY_IPTV_DEBUG=1` makes the service log
`omarchy-iptv switch <ms>` per switch (measured from `switchSource` to the
new `channels.json` being applied).

`run.sh scenario` runs `sources-scenario.sh`: a scripted pass over H1
(migration from a v0.1 cache + v1 state), H5 (add failure keeps the active
source and saves nothing, SR23), H2 (add, probe, switch), H6/H8 (five
switches each way against a generated 10k list, median must stay under
150 ms), probe cancel (a silent loopback server), H9 (CLI parity through
`set playlistUrl`), H11 (duplicate), H12 (label / EPG edits, `editMasked`),
H7 (remove the active source), a `failPersist` switch (SR25) and privacy
greps over the log and IPC output. It prints one PASS/FAIL line per check and a summary; the
harness log is `$SCRATCH/scenario.log`.

### Channel numbers (M2-03)

`chno-scenario.sh` covers the service side: the `channel` IPC verb (which
PLAYS, ruling CN1), the index counts, `channelOrder`, and the bar's number
slot. Guide digit entry is Lane A's and is not in it.

```bash
scripts/dev-harness/chno-scenario.sh check-tree   # no display, no quickshell
scripts/dev-harness/chno-scenario.sh              # preflight, then the live half
```

`check-tree` asks whether the tree under test (`OMARCHY_IPTV_PLUGIN_ROOT`,
default this repo) has the seams the live half drives. It exists because a
harness pointed at a tree without the verb answers `no_verb` or an empty
string, and half the live checks would then be VACUOUS rather than red. It
is also how a lane without the display shows the scenario detecting the
feature's absence: run it against an export of the pre-change tree and it
fails 12 of its 14 checks. It proves the code is present, never that it
works.

#### Driving digit entry (the four verbs of ruling CN23)

```bash
$H ipc number 101      # feeds "1", "0", "1" through the guide's own key router
$H ipc number "10<"    # "<" is Backspace
$H ipc number "7,1"    # both separators; anything that is not a digit, "." ","
                       #   or "<" is refused as {"ok":false,"error":"bad_key"}
$H ipc numberState     # { active, buffer, kind, label, targetName, matches, ordinal,
                       #   scopeId, cursorIndex, query, cursorId, resume, hasNumbers,
                       #   numberWidth, cursorIndexLive, cursorName, cursorChno, transient }
$H ipc commitNumber true false   # Enter (play, close);  true true = Space (play, keep open)
$H ipc cancelNumber              # Esc
$H ipc state           # guide gains hasNumbers, channelOrder, numberEntry, numberWidth
```

`number` goes through `handleSharedKey`, the guide's real router for these
keys, so the listMode guard is exercised rather than stepped over: a digit
sent while the guide is in search mode opens no entry, exactly as on a
keyboard. Every answer is the same snapshot shape, and every field is `null`
on a tree that has none of this - which is why the scenarios read them through
`qa_json_field` rather than bare, so an absent verb fails a check instead of
satisfying it.

`resume` is ruling CN21's window: after an unambiguous number auto-commits,
the buffer stays armed for `numberEntryMs` and the next digit continues it.
`active false` with `resume true` is the state D-CHNO-2 turns on.

```bash
scripts/dev-harness/chno-entry-scenario.sh check-tree   # no display; run by check.sh
scripts/dev-harness/chno-entry-scenario.sh              # preflight, then the live half
```

`chno-entry-scenario.sh` is the runner scenarios N1-N16 never had. Its
preflight runs in `scripts/check.sh` on every commit and fails 15 of its 20
checks against an export of the pre-CN23 tree. **Its live half has not been
run by the lane that wrote it** (that lane does not hold the display), so
until the display lane runs it those scenarios have a runner rather than a
result. N15, N21, N23 and N24 are deliberately not in it; the file's header
says why for each.

`fixtures/harness.m3u.in` carries the numbers the scenario asserts on: 15 of
its 20 rows are numbered, including the duplicate pair 501, the subchannels
7.1 and 7.2, `8-1` (which normalizes to 8.1), `0042` (to 42), a non-numeric
`N/A` that is deliberately NOT a number, and one row for each of the two
alias attributes of ruling CN11.

### Channel id migration at the sink (D-ID-3)

```bash
scripts/dev-harness/id-rotate-scenario.sh check-tree   # no display, no quickshell
scripts/dev-harness/id-rotate-scenario.sh              # preflight, then the live half
```

The helper moves `state.json` onto id scheme 2 when the active fetch carries
`--state-dir` (D-ID-1), and until D-ID-3 the shell wrote the state it had
loaded before the fetch straight back over that file on the same fetch. Every
earlier proof drove the helper alone; this scenario drives the SHELL, over
IPC only (no `wtype`, no screenshot), so it runs under a nested headless cage
(`docs/SPIKE-CAGE-HEADLESS.md`) as well as live. It seeds
`tests/fixtures/qa-id-rotate/state-seed.json` at 0600 after `run.sh clean`,
starts on `list-v1.m3u`, and asserts what only a running shell can answer:
the guide's Favorites scope resolves 7 rows (4 was the defect), read by name
through the guide's own rows; `state.json` holds the migrated ids at 0600;
`moved` appears exactly once in the harness log after the first fetch and
still exactly once after `ipc refresh`; the file is byte-stable across that
refresh except `sources[].fetchedAt`, the one field a successful fetch
rewrites; and after `addSource list-v2.m3u` (the rotated URLs) five
favourites still resolve by name, with the two D-ID-2 accepted-limit rows
named as the ones that cannot. Against dev's `Service.qml` before the fix it
answers 4 rows and two `moved` lines; the counts are on the D-ID-3 row of
`docs/STATUS.md`. Set `OMARCHY_IPTV_HEADLESS_ONLY=1` to make it refuse
`wayland-1`.

### Picture in picture (M2-05)

```bash
scripts/dev-harness/pip-scenario.sh check-tree   # no display, no quickshell; run by check.sh
scripts/dev-harness/pip-scenario.sh              # preflight, then the live half
```

This is the one scenario that must NOT drive the real thing. The feature's
job is to float, shrink, move and pin a window, so a scenario that reached
the live compositor would rearrange the session of whoever ran it -- and
would still pass. `stub-hyprctl.py` goes on PATH in front of the real binary
(`run.sh harness_env` prepends `$SCRATCH/bin` when a scenario has put
something there), holds its compositor state in a JSON file the scenario
seeds, and records the argv of every call. Nothing else in the harness
creates that directory, so an ordinary run is unaffected.

The stub is seeded twice: once before the shell starts, so the availability
probe has something to read, and again with the pid the service actually
holds once a player is up. That second seeding is the point of the exercise:
the window is resolved by class AND pid, and the fixture carries a second
client of the same class at a different pid -- PLY-RST-11's reproduced case,
a user's own `mpv --wayland-app-id=omarchy-iptv`. Every case asserts that
foreign window is byte-identical afterwards.

`tests/test_pip.py` is where the stub's own fidelity is pinned, against the
transcript the M2-05-00 gate recorded in `docs/QA-RESULTS.md`. Read that
file before changing any behaviour here: two of the things it models are
counter-intuitive and load-bearing. A dispatch aimed at a window that does
not exist answers `ok` with exit status 0 and changes nothing, and a real
refusal arrives as `warning:` text on stdout, also with exit status 0. That
is why nothing in this feature branches on an exit status, and why success
is defined only as reading the state back (ruling PIP11). The other is that
the `action` argument is ignored -- float and pin toggle whatever you ask
for, and asking to unset one on a tiled window floats it (ruling PIP10).

**The live half has not been run by the lane that wrote it** (that lane does
not hold the display, and starting the harness starts a quickshell), so
until the display lane runs it these scenarios have a runner rather than a
result. Its preflight runs in `scripts/check.sh` on every commit and scores
1 passed / 27 failed against an export of the pre-M2-05 tree. The file's
header lists the seams that join the preflight when lane V1 merges, and
what is deliberately absent because only a real compositor can answer it.

### Text format: a channel name is not a request (D-TEXT-1)

```bash
scripts/dev-harness/text-scenario.sh                     # holds the display; ~35 s
scripts/dev-harness/text-scenario.sh --baseline 2d3cee3  # the shipped tree: T3 and T4 go red
```

The wall caption rendered provider text under Qt's AutoText default, so an
`<img src="http://...">` in a channel name made the shell GET it (found by
the marketplace maintainer on #9628; the measurement is in `QA-RESULTS`
"Marketplace finding at 2d3cee3"). This scenario observes the sink on the
shipping `Guide.qml`: it runs its own logging server on `127.0.0.1:8767`
(8765 is `--serve`, 8766 is `argv-scenario.sh`), generates a playlist of 40
probe names carrying a per-run token in each path plus one plain control,
starts the harness with the guide closed, opens it in list view, switches
to the wall through a real `Ctrl+G` (`wtype -M ctrl g -m ctrl`) and reads
the server's log at each step. T1 and T2 are controls (the count loaded,
the delegates each view holds, the cursor name still carrying the tag); T3
and T4 are the zeros; T5 proves the server logs by making a request of its
own; T6 reads the harness log.

The control behind T2 is `ipc realised <view>`, which counts the delegates
a named channel view holds right now without re-opening the guide (-1 for
a name that is not a channel view). `channelWall` has `visible:
root.wallView` with a live model, so its first page of captions is laid
out on every open, wall showing or not; T2 asserts that on the LIST open
`resultList` holds its rows AND the hidden `channelWall` already holds
its captions, and T3's zero is measured against that count. The first
draft read the counts from `openMs`, which re-opens the guide (doubling
every request in the baseline's log) and reports 1 for a hidden wall, the
number its own comment calls what an empty view looks like.

Against 2d3cee3 on this screen: 4 passed, 2 failed -- after the LIST open
`resultList` held 16 delegates and the hidden `channelWall` 25, and the
server had logged 25 requests for 25 distinct names, one per hidden
caption; after the real `Ctrl+G` `channelWall` showed 21 and the log held
26 for 26; `User-Agent: Mozilla/5.0`; 0 requests before the first open.
The same tree with `textFormat: Text.PlainText` on the caption: 0 and 0,
6 passed, 0 failed.

### Live rewind (M5-01)

```bash
timeout -k 10 900 scripts/dev-harness/rewind-scenario.sh                     # holds the display; ~7 min since R16
timeout -k 10 900 scripts/dev-harness/rewind-scenario.sh --baseline 2d7df1f  # the pre-rewind tree: every check but R0 red
timeout -k 10 900 scripts/dev-harness/rewind-scenario.sh --tree /path/to/tree # any prepared tree: how R16 was proven red (F-RWD-18)
python3 scripts/qa-stub-mpv.py --self-test                                   # the stub's seek semantics, no socket, no display
```

`rewind-scenario.sh` runs REAL mpv against a LOCAL live-like stream and
drives the helper verb `player seek`, the service, the bar and the guide
key `b` through the harness; the plan with every check named is
`docs/QA-REWIND.md`. The stream is two HLS playlists with a sliding window
(ffmpeg `-re` from lavfi, 6 x 2 s segments, a burned-in clock in the
picture) served from the scenario's own loopback server on `127.0.0.1:8771`
(8765 is `--serve`, 8766 `argv-scenario.sh`, 8767 `text-scenario.sh`). mpv
reads it as it reads a provider's channel -- `seekable` false,
`file-format` hls, history growing one second per second -- which was
measured before the scenario was written (QA-REWIND section 2). The
player's cache is shrunk to 2 MiB back + 4 MiB forward through the plugin's
own `mpvArgs` setting (`OMARCHY_IPTV_MPV_ARGS`, recorded in
`last-start.env` so `restart-shell` carries it), because R4 needs an
EVICTED floor and at the 200 MiB default the floor would not move for
twenty minutes at this bitrate.

Every "moved" is read off the player's own socket by
`fixtures/rewind-probe.py` (request-id matched; a `socat | head -1` can
hand back an event instead of the reply), never from the reply under test.
The raw floor controls read the floor and seek in ONE probe call: the
floor on this stream evicts in 4-6 s steps, and a seek aimed at a floor
read six seconds earlier was refused during development. The held-key
check counts helper runs with `fixtures/rewind-sweep.py`, a /proc sweep
keyed on the helper's exact path (the argv-scenario lesson), and reads the
intent counter the way `player-scenario.sh` P11 does. The plugin's own IPC
verbs (`back`, `forward`, `live`, `pause`) are reached with the harness
environment (`XDG_RUNTIME_DIR=<scratch>/runtime WAYLAND_DISPLAY=<absolute
socket> qs ipc -p <scratch>/root call io.github.rmcdavid.iptv ...`), the
form SPIKE-LIVE-REWIND 12.5 measured. That incantation is now
`run.sh plugin-ipc` (F-RWD-14) and the scenario's own `pipc` is the last copy
of it; the form stays recorded here because it is what the subcommand does,
and a scenario debugging a dead target needs to see it.

`scripts/qa-stub-mpv.py` learned seek semantics for the service's logic
tests, no more forgiving than mpv 0.41 as measured: `seek` always replies
`success`; a target inside the range moves `time-pos` exactly; below an
evicted floor or past the end it does not move; while the start is still
cached an over-long RELATIVE seek lands at 0; a negative absolute target
seeks from the cache end; `pause` freezes `time-pos` while the floor keeps
moving once the window is full; every `loadfile` restarts the timeline;
`demuxer-cache-state` carries only the twelve numeric leaves the helper
forwards. Its `--self-test` pins each rule against a fake clock and each
case was seen red by a named mutation (QA-REWIND section 5). The
PLY-H17/H18 cold half (`qa-player-scenarios.sh run cold --apply`) still
passes 20/20 on the changed stub.

### The fake host publishes one write behind (D-LIVE-20 / D-LIVE-21)

`shell.qml` here reproduces the real host's config plumbing in its shape
**and its declaration order**: `shellConfig`, then the change handler that
republishes every plugin api (`/usr/share/omarchy/shell/shell.qml:66` ->
`pluginsChanged` -> `syncPluginApis` -> `publicBarConfig`), then the
`barConfig` binding that handler reads (shell.qml:109). A QML change handler
runs before the bindings that depend on the same property are re-evaluated,
so what a plugin is handed is the **previous** bar. An external write gets a
second assignment when the user-config FileView re-reads the changed file
and so lands promptly; a plugin's own `updateEntryInline` is the last
assignment there is, and the host's own `FileView.setText` does not
re-trigger its watcher, so its echo never arrives at all.

The earlier fake fed the plugin's own write straight back into
`fakeShell.barConfig`, which is exactly what the real host does not do: it
masked both P1 defects through two QA passes. Keep the ordering above
intact. `ipc hostEntry` shows the two sides, and the scenario's
`== D-LIVE-20` block asserts that a switch takes effect **while** the
published bar still names the previous source. Against a service that waits
for the echo that block fails, along with H2, H6/H8 and H7.

Pitfalls seen in the QA and fix passes: `wtype space` types the letters
s-p-a-c-e (use `wtype -k space`); `wtype -d 0` is rejected (`-d 1` works);
chords are `wtype -M ctrl u -m ctrl` (there is no `-k ctrl+u`); and a
`pkill -f`/`pgrep -f` whose pattern also appears in your own shell's
command line matches (and kills) that shell, so bracket one character of
the pattern (`quickshell -p .../roo[t]`). The AF_UNIX socket path is limited
to ~108 bytes: keep `OMARCHY_IPTV_HARNESS_DIR` short.

## What the fixture contains

`fixtures/harness.m3u.in` has 20 channels in 9 groups, 15 of them
numbered (M2-03; see the section above) (multi-group
`Animation;Kids;Religious`, an ungrouped pair, diacritics, Cyrillic, an
`#EXTVLCOPT` user agent). Every stream URL points at `127.0.0.1:9` (TCP
discard, connection refused) so mpv fails within a second and exercises the
failure path; `--serve` swaps the first channel for a generated local video
so the success path (window, title, health checks, stop) can be watched.

The diacritics and the Cyrillic are the point of two of those rows
(`Tele-Quebec`, `Pervyj kanal`, spelled in full in the file), and they are
also why `scripts/check.sh` is currently RED. The ASCII gate used to iterate a
hand-maintained list that silently skipped every directory, so this file and
`tests/fixtures/qa-player/qa-player.m3u` had never been scanned; the widened
gate scans them and reports them. CLAUDE.md rule 8 covers `.js` and `.py`
sources, not playlist fixtures, so the likely resolution is to name these two
in the gate's visible exclusion list beside `*/nonascii/*` - but that is one
ruling covering a file in another lane's tree as well as this one, and
narrowing a scan on a lane's own initiative is exactly what the cleanup round
forbids. Left red on purpose, with the decision raised rather than taken.

Note: while Lane A's helper `play` / `stop` / `status` subcommands are stubs
(`not_implemented`, exit 3) the service treats their answers as "unknown"
(no health failure counted), zapping while mpv runs logs the stub error,
and stop falls back to SIGTERM after 2 s.

## Spikes under `spikes/`

Measurements a contract rests on, kept so "measured" means "re-runnable".
None is part of the gate.

- `spikes/process-environment.qml`: how Quickshell's `Process.environment`
  merges, replaces and unsets (D-SINK-8). `timeout 20 quickshell -p
  scripts/dev-harness/spikes 2>&1 | grep SPIKE`; needs a Wayland display.
- `spikes/text-autotext-img/run.sh`: whether laying out a `Text` whose
  string carries `<img src="http://...">` makes the process GET it, per
  `textFormat` (D-TEXT-1). Offscreen (`QT_QPA_PLATFORM=offscreen`,
  qmltestrunner), its own logging server on a free loopback port, nine
  cases (tag first and last, the caption's elided shape, invisible,
  PlainText, StyledText, RichText, `<b>` only, entity-escaped), and the
  run is compared with the table in its header, so a Qt that changes the
  answer is a red exit rather than a stale comment. On Qt 6.11.2 every
  format but PlainText fetches, with `Mozilla/5.0` as the client.
