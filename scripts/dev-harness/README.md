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
start also reaps a stale fixture server. The player is ended by pid --
TERM, a bounded 5 s wait, then KILL and a final look (`qa_reap_players` in
`scripts/qa-lib.sh`, F-HARNESS-30) -- because a served player under a cage
that is going away ignores TERM, and six once spun for most of an hour. The playlist/EPG source is echoed
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
  `chno-entry-scenario.sh`, `pip-scenario.sh`, `id-rotate-scenario.sh`,
  `logo-scenario.sh`, `clip-scenario.sh` and `key-scenario.sh` in
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
  home/      HOME (0700)     -> home/.config/omarchy/shell.json, seeded 0644 every start
             XDG_CONFIG_HOME -> home/.config, XDG_DATA_HOME -> home/.local/share
             + home/.local/state/omarchy/current/theme/{colors,shell}.toml, COPIED
  cache/     XDG_CACHE_HOME  -> cache/omarchy-iptv/{channels,playlist-status,epg-now}.json
  state/     XDG_STATE_HOME  -> state/omarchy-iptv/state.json
  runtime/   XDG_RUNTIME_DIR -> runtime/omarchy-iptv/mpv.sock (+ hypr -> real hypr dir)
  fixtures/  generated harness.m3u (and test.ts with --serve)
  shots/     screenshots from `run.sh shot`
  qs.pid, server.pid  the detached shell's and the fixture server's RECORDED pids,
             which `run.sh reap` and the EXIT trap end by pid -- TERM, a bound,
             KILL -- never by a `pkill -f` pattern (F-HARNESS-32)
  transcripts/  one 0600 file per scenario run (0700 dir); NOT removed by
                `run.sh clean`, because it is the run's evidence (F-M3-1)
```

**The harness has its own HOME (F-HARNESS-20).** The service runs the
helper's `config shield` at every start, and the helper takes the host's
settings file from `$HOME/.config/omarchy/shell.json` -- deliberately, because
the host does, and with no override flag, variable or path argument, by
ruling. Until 2026-10-13 the harness redirected the XDG directories and left
`HOME` real, so every harness run (the gate's `clip-scenario.sh check-tree`
included) aimed that chmod at the developer's own config. It now gives every
process it starts a scratch home, through ONE function, `qa_harness_home` in
`scripts/qa-lib.sh`, which `run.sh`'s `harness_env` calls and which every
scenario driver that uses `run.sh` calls too, for its own helper runs and
probes:

- `HOME`, `XDG_CONFIG_HOME` and `XDG_DATA_HOME` inside `home/`;
  `XDG_CACHE_HOME` and `XDG_STATE_HOME` are `cache/` and `state/` as before.
- `MPV_HOME` and `XCOMPOSEFILE` are dropped when they name a path in the real
  home (they bypass `HOME`); set anywhere else they are kept, which is how
  `tls-scenario.sh` hands mpv its own profile directory.
- `PATH` is inherited unchanged: programs on it are executed, never written.
- What the harness takes from the real home, measured rather than assumed, is
  two theme files: the host's `Color` singleton paints from
  `$HOME/.local/state/omarchy/current/theme/colors.toml` and `shell.toml`
  (and an optional `$HOME/.config/omarchy/shell.toml`), so those are COPIED,
  dereferenced, 0600, on every start. Never a symlink: a link into the real
  home is a way for a harness write to reach the user's files. Fonts need
  nothing (the Nerd Font and the fontconfig that selects it are system-wide;
  `fc-match monospace` answers `JetBrainsMono Nerd Font` under an empty home).
- `tests/test_harness_home.py` runs `harness_env` and the seeding functions
  out of `run.sh` against a decoy "real" home with a 0644 `shell.json` and
  asks the SHIPPED helper, Python and mpv where they would read and write;
  the decoy's mode, mtime and ctime must not move. On the harness before this
  it fails 9 of its 10 cases, the decoy going 0644 -> 0600.
- The same question was put to every process the GATE starts, by running
  `scripts/check.sh` whole with a decoy `HOME` and decoy XDG directories and
  listing what landed there. Three steps wrote into the home they were given
  -- on an ordinary run, the developer's real one, on every commit: the clip
  and logo check-trees (a mesa shader cache, `QtProject/Qml Runtime`,
  `fcitx/dbus`, from cage and the QML probes the drivers start) and the
  `qml spec` step (`qmltestrunner/qmlcache`). Each now runs with a home inside
  its own temporary directory, removed at exit, and the same decoy run leaves
  the decoy empty.

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
scripts/dev-harness/run.sh --playlist /x.m3u --source-key d990c2e4 --keep   # the entry a host holds after
                                                     # `omarchy bar set playlistUrl` beside the mirror (D-SINK-19);
                                                     # since R21 a migration input until the marker lands, refused after
scripts/dev-harness/run.sh --host echo --keep         # the host that echoes a plugin's own write at once (#15082, D-HOST-4)
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
$H shot search            # grim screenshot -> shots/search.png -- REFUSES unless the guide
                          #   has the keyboard (F-HARNESS-12); `shot --any-surface player`
                          #   is the deliberate shot of whatever is up (the flag comes first)
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

`shot` asks the same question (F-HARNESS-12). It grades PIXELS, and a human
reads its file as proof, so a capture of a surface that is not the guide's
was the one failure the verb could not see -- the keystroke class, on the
verb whose output is read as evidence. It refuses with exit 3 and `key`'s
wording unless `ipc focusState` says the guide holds the keyboard;
`shot --any-surface <name>`, flag first, is the deliberate shot of whatever
is up (the player window). No lock refusal: nothing is typed. Which OUTPUT
the guide is on is not asserted (`focusState` carries no output name; the
focused monitor is captured, as before). `m3-scenario.sh`, its one caller,
prints a refusal as a FAIL line instead of discarding both streams.
`scripts/qa-lib-test.sh` drives the decision with `qs`, `hyprctl` and `grim`
stubbed; it was red on the run.sh before this (a closed guide captured).

`type` and `--to-compositor` are **prompt-and-gate-only** (F-HARNESS-6): no
scenario calls either, because no scenario enters text through the keyboard
(m3's search check is driven over `ipc query`, and its `key` calls are
command keys), and `--to-compositor` has no caller by construction. Both are
pinned by `qa-lib-test.sh`'s decision table (`type` refuses before its retry
loop and ends on the guard's verdict after a mid-type steal; the hatch is
positional and skips the primer). A caller would be an ADDED segment, not a
replacement: a display lane giving m3 an H3c that enters search by keystroke
and `type`s the query is the one check that reddens when `type` stops
proving arrival.

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
$H ipc set playlistUrl /path   # `omarchy bar set`: read once, by the migration; REFUSED after it (D-SINK-19 R21)
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

`state().guide.form` masks with the plugin's own model, which `run.sh`
copies into the scratch root next to `shell.qml` -- `Model.mjs` and every
part under `model/` it names (D-REL-5), each compared with the tree under
test, or the one-file `Model.js` of a tree from before the split, with the
staged shell's import pointed at it; a raw form value never reaches the
terminal.

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
`set playlistUrl`, refused since R21, then the same playlist added in the app), H11 (duplicate), H12 (label / EPG edits, `editMasked`),
H7 (remove the active source), a `failPersist` switch (SR25) and privacy
greps over the log and IPC output. It prints one PASS/FAIL line per check and a summary; the
harness log is `$SCRATCH/scenario.log`.

### Channel numbers (M2-03)

`chno-scenario.sh` covers the service side: the `channel` IPC verb (which
PLAYS, ruling CN1), the index counts, `channelOrder`, and the bar's number
slot. Guide digit entry is Lane A's and is not in it. Both chno scenarios
play every row from run.sh's own fixture server (`--serve`, port 8765, which
must be free and is asserted to be this harness's), and under a nested cage
they need `WLR_RENDERER=gles2` for mpv (F-HARNESS-21/22).

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
(8765 is `--serve`, 8766 is `argv-scenario.sh`, 8773 and 8774 are
`tls-scenario.sh`), generates a playlist of 40
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

### TLS: the stream's peer is a sink (D-SINK-13), and an adopted player is the same sink (D-SINK-16)

```bash
scripts/dev-harness/tls-scenario.sh --rig-only            # NO display, no plugin; ~20 s (plus one ffmpeg run, cached)
scripts/dev-harness/tls-scenario.sh                       # holds the display; seven harnesses, ~6 min
scripts/dev-harness/tls-scenario.sh --baseline <pre-fix>   # the pre-D-SINK-13 tree: S1 and S3 play, and the GET is logged
scripts/dev-harness/tls-scenario.sh --baseline <0.13.0>    # S1..S5 pass and S6 reds: D-SINK-16 on its own
scripts/dev-harness/tls-scenario.sh --pre-tls <ref>        # which tree launches S6's pre-update player (default b731882^)
```

mpv was launched with no TLS verification while the helper supplied provider
headers and HTTPS stream URLs, so an on-path attacker could impersonate the
provider, replace the media and collect the credentials in the URL
(the marketplace maintainer on #10323, against the shipped 0.12.1; the lead's
measurements, including the four ways the fix can be undone, are in
`QA-RESULTS`). The fix is four layers -- the token in the base argv, the same
token re-asserted as the LAST token after the user's `mpvArgs`,
`--tls-verify` reserved in both spellings, and `--tls-ca-file` deliberately
left unreserved -- and this scenario observes all four at the sink.

It watches from the ATTACKER's side. One python process holds two TLS
listeners: `127.0.0.1:8773` with a self-signed certificate (the attacker) and
`127.0.0.1:8774` with one signed by a CA the run generates (the provider). Both
answer every GET with a 60 s MPEG-TS and log one line per request -- method,
port, path, `User-Agent` and whether an `Authorization` header arrived, as a
BOOLEAN and never its value. A GET of a channel's path is an attacker holding
the bytes, the URL's credentials and the provider header; no GET is an attacker
holding nothing. Each segment has its own channel path, so the log
attributes per segment, and each runs its own harness because `mpvArgs` is read
at launch (`OMARCHY_IPTV_MPV_ARGS`). Two paths are served differently, and only
two: S6's stage channel and the rig's own `stagectl.ts` get a body written in
pieces a second apart, with a line per piece and a line when the connection
ends, because a single-write response makes an ONGOING fetch invisible and S6 has
to ask whether an already-open stream kept being fed. No new port: 8773 and 8774
are the same two.

G1-G10 are the rig, and they run in both modes: `openssl verify` both ways and
four `curl`s, so that the CA-signed certificate is known to verify against this
run's CA and NOT against the system store before any stream plays, and both
servers are known to serve the media before any zero is read as a refusal. G9
and G10 then make the paced body's two signals fire where no display is needed:
a client reads for four seconds (pieces logged), walks away, and the attacker
sees the connection END.
S1 is the plain case (refused). S2 is the positive control and runs BEFORE the
case it de-vacuums: the CA is named ONLY inside an mpv profile, so a stream that
plays proves mpv read this run's config and applied the profile. S3 is the
profile bypass -- `--profile=evil` with `tls-verify=no` in it -- which plays
without the trailing re-assertion and must refuse with it. S4 is the documented
escape, `--tls-ca-file` on `mpvArgs`. S5 reads `/proc/<pid>/cmdline` of the
player that is actually playing: both reserved spellings absent, `--profile` and
`--tls-ca-file` present (the control -- the attack and the escape really were
delivered), the LAST token `--tls-verify=yes`, and the token twice over.

S6 is D-SINK-16, and it is the only segment that is not about how a player is
LAUNCHED. The marketplace maintainer raised it against the shipped 0.13.0 on
#10389, hours after it went out and on the verification request for that very
commit: the reattach path adopts a player that is already running without
migrating its TLS setting, and the helper then sends new provider headers and new
credentialed URLs into that same process. It is staged in two shells. The first
is the harness run against the PRE-UPDATE TREE -- exported with the same
`git archive | tar -x` `--baseline` uses, chosen by `--pre-tls` and defaulting to
`b731882^` (0.12.1, zero occurrences of `tls-verify` or `stream-lavf-o` in either
mirror) -- so the pre-update argv is composed by the code that composed it, never
written down here; what this scenario writes down is the assertion that the
RUNNING player's `/proc/<pid>/cmdline` carries no TLS token of any spelling. Then
that shell is stopped the way `omarchy restart shell` stops the real one, the
player is left alone, and a shell from the tree under test comes up on the same
socket, cache and state and adopts it through `player probe` and `applyProbe`.
Four questions follow, all at the attacker's log: the adoption happened at all
(`qa_adopted` -- the service names the staged player's pid, or that player is
gone, and NOT that it named one of its own, which would mean the segment
re-tested S1); the already-open stream stopped being fed (`qa_stream_stopped`
over the paced body, where the wait giving up IS the finding); the attacker
logged no new request across the adoption, which is what reds if the properties
are migrated AFTER the reload instead of before it; and a zap issued after the
adoption reaches him not at all. Then a control that passes on both trees: a zap
to the CA-signed provider still plays. The mechanism S6 rests on was measured by
the LEAD over a real IPC socket on 2026-10-07 (`tls-verify` reads False on such a
player, `set_property` True succeeds and reads back, the next loadfile of the
attacker's URL fetches nothing, attacker GETs 1 -> 0 on the same process, with a
plain-http positive control still playing) and is cited, not re-taken. What is
NOT measured by anyone is whether an already-open stream picks the change up for
its ongoing fetches, which is why the ruling re-establishes the channel and why
S6 reads the connection ending rather than assuming it does.

The profile cases need an mpv config and the user's own is not ours to write, so
the scenario points `MPV_HOME` at a directory under its own work tree and
deletes it; `HOME` is the harness's own (see "The harness has its own HOME"),
and `qa_harness_home` keeps an `MPV_HOME` that names no path in the real home.
It sends no keystroke. The verdict every
segment turns on is `qa_outcome` in `scripts/qa-lib.sh`, so that the one
decision in here that needs no display is driven by `scripts/qa-lib-test.sh`
for real rather than extracted.

**The live half has not been run by the lane that wrote it** -- that lane holds
no display, and every live segment starts a quickshell and an mpv window. What
HAS been run, on 2026-10-07: `--rig-only`, 9 passed / 0 failed; all four
argument refusals (exit 2, no transcript); and the port refusal with a decoy
listener on 8773, which refused and left the decoy alive and still listening
(F-HARNESS-14). Counting only `TLSREFUSED` saw 0 of the 2 handshake refusals
`curl` provoked and counting `TLSERROR` as well saw 2 of 2, which is why the
refusal count is reported and never asserted.

**S6 has not been run end to end by anybody.** The lane that added it holds no
display either, and S6 needs two quickshells and a real mpv. What HAS been run on
2026-10-07, same machine: `--rig-only` on the tree with S6 in it, 11 passed / 0
failed, G9 logging 4 pieces to a client that read for 4 s and G10 seeing that
connection end; the three `--pre-tls` refusals (exit 2, no transcript, including
`--pre-tls --rig-only` not eating the next flag as a ref); and `--rig-only`
against the tree BEFORE the change, 9 passed / 0 failed, which is the other half
of the count. G9 and G10 were then each seen RED by mutation: with the paced path
list emptied, both fail and the close wait reports giving up; with only the
`CLOSED` line removed, G9 passes and G10 fails. `qa_adopted` and
`qa_stream_stopped`, the two decisions S6 turns on, are driven for real by
`scripts/qa-lib-test.sh` (335 checks) with the naive forms of each shown passing a
run where nothing was adopted and a run where the attacker kept being fed; three
mutations of those two functions took that step from 335/0 to 333/2 each time.
A live run should expect roughly six minutes rather than four, and on the tree as
it stands -- the fix for D-SINK-16 is not in it yet -- S6's two discriminators are
expected RED: that is the finding, reproduced, and it is what the forward run has
to flip once the fix lands.

### Live rewind (M5-01)

```bash
timeout -k 10 900 scripts/dev-harness/rewind-scenario.sh                     # holds the display; ~7 min since R16
timeout -k 10 900 scripts/dev-harness/rewind-scenario.sh --baseline 2d7df1f  # the pre-rewind tree: every check but R0 red
timeout -k 10 900 scripts/dev-harness/rewind-scenario.sh --tree /path/to/tree # any prepared tree: how R16 was proven red (F-RWD-18)
python3 scripts/qa-stub-mpv.py --self-test                                   # the stub's seek semantics, no socket, no display
```

`qa-stub-mpv.py` also answers the two TLS properties the way a real player does
(D-SINK-16): `tls-verify` reads **False** on a player launched without it, not
"property unavailable", and `stream-lavf-o` reads `{}` -- both measured by the
lead over a real socket. A stub that answered "unavailable" would be LESS
forgiving than mpv in the direction that hides a defect, pushing a caller that
asserts TLS before loading down its refusal path on every run. `STUB_REFUSE_PROPS`
is the fault injection for the other side: a named property's `set_property` is
refused AND its value is left alone, so a caller's cannot-be-made-safe branch is
reachable from a test. mpv's error TEXT for that case is not measured by anyone,
so the stub injects `property unavailable` and the header says plainly that a
caller must branch on `error != "success"` and not on those words.

`rewind-scenario.sh` runs REAL mpv against a LOCAL live-like stream and
drives the helper verb `player seek`, the service, the bar and the guide
key `b` through the harness; the plan with every check named is
`docs/QA-REWIND.md`. The stream is two HLS playlists with a sliding window
(ffmpeg `-re` from lavfi, 6 x 2 s segments, a burned-in clock in the
picture) served from the scenario's own loopback server on `127.0.0.1:8771`
(8765 is `--serve`, 8766 `argv-scenario.sh`, 8767 `text-scenario.sh`, 8773 and
8774 `tls-scenario.sh`). mpv reads it as it reads a provider's channel --
`seekable` false,
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

### Logos: a header is not a size (D-LOGO-11)

```
scripts/dev-harness/logo-scenario.sh check-tree            # no display, loopback only; run by check.sh
scripts/dev-harness/logo-scenario.sh                       # the same checks, with a transcript
scripts/dev-harness/logo-scenario.sh --baseline 159da94    # the red run: the shipped 0.13.3
```

A provider logo's header chose how much memory the shell allocated: 304
bytes declaring 20000x20000 took the row slot's `Image` to 840 MB (the fifth
maintainer finding, `docs/QA-RESULTS.md` 2026-10-09). The fix is in the
helper -- a dimension bound at `write_logo` and a sweep of the cache the
shipped releases wrote unchecked -- and this scenario observes it at BOTH
sinks rather than at a string. The helper runs as the subprocess the service
runs, `logos --fetch --cache-dir <scratch>`, against a provider that is
`spikes/logo-decode-bomb/serve-and-fetch.py`: an https server with a
self-signed certificate in a thread of that process, the helper as its
child, nothing detached and nothing to kill. The corpus comes from
`spikes/logo-decode-bomb/make-corpus.py` (stdlib only, so the gate depends
on nothing installed). Then whatever the helper ANNOUNCED is handed to the
shell's `Image`, declared exactly as `Guide.qml` declares the row slot, under
an address-space rlimit of 2.5 GB (util-linux `prlimit --as`) on the qml
process alone -- an rlimit rather than a service-manager memory scope,
because the marketplace capability scan reads the scope tool's name as
service management anywhere in a tracked file, and because under the rlimit
an over-bound decode is a clean allocator refusal rather than a kill.

Thirty-two checks and the floor: the verb exists (V1); the rig's names are
the helper's names (V2); the 512x512 logo is fetched, announced, written and
reaches `Image.Ready` at 72 MB (C1, K1 -- the positive control, because a
scenario where everything is refused passes against a helper that refuses
everything); a file at the bound exactly is accepted (C2); a sound cached
file is announced with no request (C3); a 64x64 JPEG carrying a whole
thumbnail JPEG in its APP1 is accepted (C4, so a parser that refused every
APP1 could not pass the bomb below for the wrong reason); ten planted bombs
are swept (P1..P10, S1) -- the seven from the first round plus the three a
reviewer crafted against the parser: an EXIF thumbnail with its own 64x64
SOF before the real 20000x20000 one, a 64x65535 column whose pixel count is
UNDER the bound by 64, and a two-frame GIF whose second frame declares
65500x65500 -- refetched once each (G1), refused under
`reasons.logo_dimensions` with nothing on disk (F1, F2, R1..R3); the two
bounds are driven apart (E1, E2) and an unreadable header is refused rather
than passed (E3); the summary carries both numbers (M1, M2); the refusal
text names a host and no URL (T1, T2); and the 304-byte bomb never reaches
the sink (K2, whose evidence line says which of `withheld-and-gone`,
`withheld-but-file-survived` or `announced` it saw). On `--baseline 159da94`
it reads 9 passed, 24 failed, and K2's red line carries `rc=0 peak_mb=839`:
the finding, observed. check-tree never decodes a bomb, even capped; the
840 MB arm is the baseline's, for a human.

The tool checks (python3, openssl, prlimit, the qml binary) run before any
external command, so an empty PATH prints the SKIP reason and nothing else,
and the exit is 77. `scripts/check.sh` treats that 77 as RED unless
`LOGO_PREFLIGHT_SKIP_OK=1` is set, printing the reason either way: a gate
that observed neither sink is not green by default. `LOGO_QML_BIN` overrides
the qml path, which is how that branch is driven on a machine that has qml.

### Clipboard: an editable field is a reader (D-CLIP-1)

```
scripts/dev-harness/clip-scenario.sh check-tree            # the probe arm, inside a nested cage; run by check.sh
scripts/dev-harness/clip-scenario.sh                       # the probe arm, then the real Guide.qml, with a transcript
scripts/dev-harness/clip-scenario.sh --baseline d55149b    # the red run: the shipped 0.13.4
```

Every editable QtQuick `TextInput` subscribes to `QClipboard::dataChanged`,
and on the released Qt 6.11.2 that slot calls `QMimeData::text()`, which on
Wayland reads the whole foreign offer through a pipe -- 1 s timeout per
read, no total limit, no deadline -- synchronously, on the main thread of
the process that owns the field: for this plugin, `omarchy-shell`, whenever
the first-run or add-source form is open and any application changes the
clipboard (the sixth maintainer finding, `docs/QA-RESULTS.md` 2026-10-11).
The fix is `readOnly: true` on every form field -- `readOnly` is the one
switch on that slot -- with the plugin editing the model value itself and
paste going through `wl-paste` as a bounded child. This scenario observes
the sink, in two arms, both inside a nested headless cage on a display of
its own (`docs/SPIKE-CAGE-HEADLESS.md`), so the user's clipboard is never
offered to, read from or replaced:

* **The probe arm** (check-tree): the lead's three probes, verbatim from
  `spikes/clip-offer/` (an editable `TextField`, a read-only one, a window
  with no field), each started on the nested display, offered 100 MB of
  `text/plain` by `wl-copy` on that display, and sampled for resident set
  from outside. The editable probe grows by the payload or more (P3: +235
  to +305 MB, 2.3 to 3.0x; it is the CONTROL that the rig delivers offers
  at all), the read-only probe and the no-field window by nothing (P4, P5,
  +0 every run); a consumer on that display receives every byte (P2); the
  display is cage's and not the caller's (P1); and every process started is
  gone by its recorded pid with the socket removed (P6). About 13 s.
* **The shell arm** (live): the fake shell with the real `Guide.qml` and
  `Service.qml` under the same cage in the floating window, started with no
  playlist so the guide opens straight into the first-run form with the
  playlist field focused -- confirmed over IPC (L1, L2). Typing through
  `run.sh key` lands in the model value of the read-only field (L3, the
  positive control). Then the same producer offers 100 MB: the shell's RSS
  is sampled 1 s before and 3 s after, concurrently with twelve IPC round
  trips timed from the instant of the offer. On the fixed tree the growth is
  +0 MB (L4, band 16) and the slowest round trip 96..159 ms (L5, bound 400,
  the first call carrying a process cold start); on `--baseline d55149b` L4
  reads +254..+297 MB with a peak of 600..642 MB and L5 catches a 673..685
  ms call when one lands inside the read, which the twelve back-to-back
  calls did on every run measured and are not promised to -- L4 is the
  discriminator, L5 the stall half of the finding when timing allows. The
  offer alone changes nothing in the field (L6); Shift+Insert and Ctrl+V
  both paste through the process path, the second landing a 5,000-byte
  offer at exactly `Model.formCapacity("playlist")` read from the tree
  under test by calling it (L7, L8; on the baseline Qt's own paste truncates
  to the same number, so both are controls); no `wl-paste` child of the
  shell survives the answer (L9); the harness log carries no run of the
  payload (L10); and the shell, the keyboard, the producer and the
  compositor are gone (L11). About 25 s in all.

**The seat.** cage's headless seat has no keyboard, and a compositor hands
`wl_data_device.selection` only to the client holding keyboard focus, so
with nothing on the seat not even the editable probe reads (+0 on both;
found by lane A re-running the lead's rig under cage). The scenario holds a
virtual keyboard (`wtype -s`) open on the nested display across every offer;
P3 is asserted in both arms so that a +0 elsewhere means "did not read" and
never "was never offered". `wl-copy` also maps a surface of its own for an
instant to obtain a serial, and a chord sent in that instant is refused by
`run.sh key`'s focus guard rather than typed into it; and a producer
restarted within milliseconds of the previous one's death leaves the guide
with no focus item at all until the next surface maps (2 runs in 10). Every
chord therefore waits on the harness's own `focusState` first, and when it
is not held, nudges it back with a `wl-paste -l` on the nested display
(measured: back within 100 ms, every time) and says so in the transcript.

The tool checks (cage, wl-copy, wl-paste, wtype, python3, node, the qml
binary) run before any external command and exit 77 with the reason, as does
a cage that brings up no display within 10 s. `scripts/check.sh` treats that
77 as RED unless `CLIP_PREFLIGHT_SKIP_OK=1` is set, printing the reason
either way. `CLIP_CAGE_BIN` and `CLIP_QML_BIN` override the two binaries;
`scripts/qa-lib-test.sh` drives the 77 path through the first and asserts
that no transcript lands. The scenario uses its own harness directory
(`$XDG_RUNTIME_DIR/omarchy-iptv-clip`), not the shared one, so a display
lane's running harness is never reaped by a clip run.

### The bar entry names a key, not a URL (D-SINK-19)

```
scripts/dev-harness/key-scenario.sh check-tree            # the instrument arm, node only; run by check.sh
scripts/dev-harness/key-scenario.sh                       # the instrument arm, then the real Service.qml under cage, with a transcript
scripts/dev-harness/key-scenario.sh --baseline 6f1d176      # the R27 red run: 0.14.2's code, the helper split on top (130 / 5 with 134 lettered checks: B32, B33, B35, B36, B37; B34 since dropped)
scripts/dev-harness/key-scenario.sh --baseline 1c88877      # the R26 red run: round 15's code and 0.14.1 (120 / 9: B23-B31, read before write)
scripts/dev-harness/key-scenario.sh --baseline lane-key-m2  # the round-12 red run: round 11's code (97 / 9: B1-B8, and N1 for its new field only)
scripts/dev-harness/key-scenario.sh --baseline lane-key-z2  # the round-11 red run: round 10's code (68 / 30 under the 97-check harness: G1, G2, G5, F4, U1-U7, K1-K3, Z1-Z3, A1, Y2, Y3, Q1, Q2, V1, H1, X1-X6; eight of them NOFIELD-only)
scripts/dev-harness/key-scenario.sh --baseline lane-key-y2  # round 10's baseline is NOT a red run: round 9's code reads 87 / 0, because no segment observes R20a-R20c at the sink (Y4 reds only the S1b export)
scripts/dev-harness/key-scenario.sh --baseline lane-key-y0  # the round-9 red run: round 8's code (74 / 12 before Y4 existed: U1, U2, U5, K1-K3, Y1-Y3, Q1, V1, H1)
scripts/dev-harness/key-scenario.sh --baseline lane-key-w2  # the round-8 red run: round 7's code (73 / 6 before Y, Q, V, H existed: K1, K3, Z1, Z2, Z3, A2)
scripts/dev-harness/key-scenario.sh --baseline lane-key-v2  # the round-7 red run: round 6's code (66 / 5 before K, Z, A existed: U2, U3, U4, U6, U7)
scripts/dev-harness/key-scenario.sh --baseline lane-key-t2  # the round-5 red run: round 4's code (60 / 4 before U existed: L1, L2, F6, F7)
scripts/dev-harness/key-scenario.sh --baseline lane-key-s2  # the round-4 red run: round 3's code (54 / 10: D3, W3, W6, F3..F7, L1, L2)
scripts/dev-harness/key-scenario.sh --baseline lane-key-r2  # the red run: the tree D-SRC-15 was found on (38 / 26)
scripts/dev-harness/key-scenario.sh --baseline f275bde      # the earlier red run: the first build (39 / 25; O2 its one discriminator)
scripts/dev-harness/key-scenario.sh --tree "$cp"            # a PREPARED export: spikes/key-mutations/README.md has the recipe
```

D-SINK-19 takes the provider URL off the host's bar entry: the entry
carries `sourceKey`, an 8-hex pointer, and `state.json` carries
`activeKey`; `omarchy bar set ... playlistUrl` is an INPUT that is adopted
and then removed from the entry by the plugin's own write [round 11,
2026-10-13, R21: only by the one migration, while the landed `state.json`
lacks `entryMigrated`; after it the value is refused, reported once and
removed -- the round-11 subsection below]. Two things in
this directory had to move with it.

* **The instrument (lead ruling R6).** `hostEntry` -- the verb every
  `sources-scenario.sh` check about the one-write-behind host grades
  through -- derived both sides' keys by hashing the entry's `playlistUrl`,
  which is the one thing the change takes off the entry, so on the very
  tree it had to grade it read `""` on both sides. `entryKey` now lives in
  `harness-lib.js`, which `shell.qml` imports beside `Model.js` and
  `run.sh` stages the same way, and node can `require` it: `sourceKey`
  first, the URL hash second, **named candidates only**. A first repair
  (never merged) iterated every own value of the entry and would have
  reported a user's `mpvArgs` of `deadbeef` as the active source. The
  check-tree arm drives the function from node with the tree's own
  `Model.js` (I1-I7) and pins the three seams that keep `shell.qml`,
  `hostEntry` and `run.sh` reading through it (S1-S3); `hostEntry` also
  reports each side's key NAMES (`storedKeys`, `publishedKeys`), never
  values, so a scenario can see the retired URL keys leave the stored entry.
  `run.sh --source-key KEY` seeds the mirror on the entry (`""` allowed),
  which is how a scenario presents the entry a host would hold after an
  earlier shell wrote it; absent, the entry carries no such key, which is
  the 0.13.5 shape (rule 10: the seed never carries a key the plugin has
  not written). `ipc pointerState` reports where the two writes of a
  pointer change stand (`dirsReady`, `stateSavePending`, the held
  `pendingEntryKey`, the in-memory `activeKey`) and, since D-SRC-15, the
  service's own accounting of the file against memory
  (`stateSavesInFlight`, `stateSaveFailed`, `stateInitOk`,
  `stateReloadsIgnored`, and since round 4 `stateReloadsByReason`, one
  number per `Model.reloadDisposition` reason: numbers and booleans, never
  a URL -- the service's `lastSaveText` beside them is the state.json text
  and is deliberately not reported), every field optional. Since round 6
  a field the tree under test does not have is OMITTED rather than
  reported as null (`HarnessLib.pointerStateOf` in `harness-lib.js`, which
  `qa-lib-test.sh` drives), so the reader answers NOFIELD for it; before,
  a pre-change tree published a present null and was indistinguishable
  from a service holding nothing.
* **The scenarios (R7).** The live arm runs the real `Service.qml` under a
  nested cage, IPC only, over ten seeded starts, each from its own
  `state.json`, caches and entry so a red is attributable to one ruling:
  the start-up adoption watched across `dirsReady` from inside with the
  file seeded at 0644 so the helper's chmod fires the reload R9 has to
  absorb, read off the per-reason counter (D; `save-parked`, because the
  plain ignored total is satisfied by the own-write echo after every start
  and could not go red for the chmod reload -- the round-3 review's P2),
  a fresh install with no state
  directory, file or cache (N), the two-source migration asserting the
  count it went in with (M), the idempotent second start (J), a
  `playlistUrl` and an `epgUrl` set while the shell was down (C, E; the
  review's P1 and R4), removing the active source (R; R3), and the
  interrupted order -- a NEW URL on the entry with the service's `state
  init` held for seconds by `fixtures/slow-helper.py` so the shell can be
  SIGKILLed between the parked state save and the entry mirror, then
  restarted over the entry as the host held it, `--source-key` passed only
  when the entry observed stored carries that NAME (O; R5, the review's
  P2); since round 4 (2026-10-12) the D-SRC-15 SIBLING, an IPC switch and
  then a remove made inside that same slow window over a 0644 file so the
  chmod reload lands after the call (W; lifted from the round-3 lens's
  scratch driver, the fixture's named case now observed live), and the
  round-3 P1 at the sink: the state directory made 0500 under a running
  shell with the dirs ready, then a CLI `playlistUrl` and a switch, which
  must leave the URL on the entry, the file untouched and one
  `sourcesPersistFailed("state_write_failed")`, and the next start must
  re-adopt what the failed write left there (F; R13); and since round 5
  the LOGO TOGGLE on that same failed disk (L; R16): the guide opened over
  IPC and driven through `ipc sourcesKey` (`enter`, `g`, `confirm` -- the
  harness verb that calls the guide's own handlers, no keystroke), which
  must patch `showLogos` alone and leave the URL and the FILE's mirror on
  the stored entry, and F6 then restarts over the entry as the host stored
  it after the toggle. F5's counts are taken from the switch's own log
  mark and L's from the toggle's (F2's drop line used to pre-satisfy
  F5's `left:yes`). `cleanup()` records
  the live shell's children by parent pid before it reaps, so a TERM
  inside the O window takes the sleeping slow helper with it (proven
  inside O, D and N; `qa-lib-test.sh` pins the seam), and gives the state
  directory its mode back on every exit, because a TERM inside F used to
  leave it 0500 and `rm -rf` of the harness directory then stopped on
  `state.json` (`run.sh clean` now tolerates that directory too; both
  measured in round 5; since round 6 a `clean` whose `rm` still fails
  says so and exits 1 instead of printing `cleaned`). The one window
  outside that seam, a TERM between `--detach` returning and `qs.pid`
  being read, is ended by the nested compositor going away rather than by
  `reap` (which is gated off there); the round-3 review measured it.
  `qa_json_field` answers `NULL` for a key that is present and null and
  `NOFIELD` only for one that is absent, so a `held:NULL` want cannot be
  met by a tree with no `pendingEntryKey` at all (round 4's P3; the three
  `held:` wants say NULL) -- true only since round 6, when `pointerState`
  stopped folding an absent property to null: the round-5 split was at the
  reader alone, and `held:NULL` was green on f275bde (the round-5 live
  lens's P2).

**What the first run found (2026-10-11, lane-key-r1 at f84ee50), now
D-SRC-15.** The key adopted at the first start was dropped when the
helper's start-up `state init` chmodded the EXISTING `state.json`: the
chmod is an inotify `IN_ATTRIB` on the file the service's `FileView`
watches (mode changed or not), the reload handed `applyUserState` the
pre-adoption text, `Model.stateOnLoad` kept only the session record, the
parked save then wrote the key-less state and the entry flush stripped the
URL with `sourceKey ""`. Measured by polling `pointerState` at 50 ms
(+1489 ms adopted and parked, +1909 ms dropped) and attributed by repeating
it with a helper whose `state init` does nothing (the key survives).
lane-key-s1 (R9-R12) closes it: a reload never replaces memory that is
newer than the file, the helper leaves a 0600 file alone, the entry waits
for the save to land. Counts from the transcripts, 2026-10-11, on the
round-3 harness (48 lettered checks): the forward run on lane-key-s2
(lane-key-s1's code) **49 passed, 0 failed**; `--baseline lane-key-r2`
**36 passed, 13 failed** (D2, D3, M1, M3, M5, C1-C5, E1, O5, O6). On the
round-4 harness (61 lettered checks: W1-W6 and F1-F7 added, D3 by
reason), 2026-10-12: the forward run on lane-key-t2 (lane-key-t1's code,
R13-R15) **62 passed, 0 failed**; `--baseline lane-key-s2` **54 passed, 8
failed** (D3, W3, W6 for the per-reason counter s2 lacks; F3, F4, F5, F6,
F7 -- the dirsReady-route state write failing strips the URL from the
stored entry, moves the mirror and loses the input, no record for it after
the restart); `--baseline lane-key-r2` **38 passed, 24 failed** (the 13
above plus W2, W3, W4, W6 -- the in-window switch and remove dropped by
the same reload -- and F1-F7); `--baseline f275bde` **39 passed, 23
failed**, O2 still its one discriminator against every later tree, the
rest instrument absences and the start-up-adoption reds. Two mutations of
this tree's code through the same harness: `Model.reloadDisposition`'s
save-parked clause deleted reads 56 / 6 (D2, D3, W2, W3, W4, W6; the
counter reads `file-newer` and `save-parked` is absent) and
`applyUserState`'s R14 `return` deleted reads 57 / 5 (D2, W2, W3, W4, W6
-- and D3 green, because a counter observes the decision and not the
sink; the `return` is pinned structurally in `tests/Model.test.js`). The
two mutations are PATCH FILES under `spikes/key-mutations/` (round 5; the
round-4 throwaway branches are retired, cited nowhere, and the lead's to
delete), applied to an export and run
through `--tree`; `qa-lib-test.sh` proves each still applies.

**Round 5 (2026-10-12, R16; 63 lettered checks: L1, L2 added).** The
round-4 data-loss lens found rule 15's shape in R13 itself: the logo
toggle is `writeOwnedEntry`'s SECOND caller, mirrored the in-memory key
with no gate and stripped the URL, so in exactly the state F leaves one
`g` + confirm in Sources lost the record. L drives that toggle inside F.
Counts from the transcripts on the round-5 harness: the forward run on
lane-key-u2 (lane-key-u1's code, R16) **64 passed, 0 failed**;
`--baseline lane-key-t2` **60 passed, 4 failed** (L1 `stored:<C>
playlistUrl:no`, L2 `keys:0 alone:0`, and F6/F7 restarting over that
entry find no record for B); `--baseline lane-key-s2` **54 passed, 10
failed** (round 4's eight plus L1, L2); the two patches through `--tree`
read **58 / 6** and **59 / 5**, the same letters as above.
Two things the first measurement corrected: E1 had been red
on every tree because its own `want` was wrong (`kind=x` where
`Model.maskUrl` masks every query value, by calling it on dev, lane-key-r2
and lane-key-s1 alike), and the created-file shape (no `state.json` at
all), which the round-2 live lens wrote down as dropping "the same way",
does NOT drop: N2-N4 are green on `--baseline lane-key-r2` and
`stateReloadsIgnored` reads 0 across the whole fresh start, because a
`FileView` loaded over a missing path never sees the helper's create. N
stays as the control for the one start every new user makes.
`sources-scenario.sh` under cage read 63 passed, 3 failed on lane-key-s2
(46 / 22 on lane-key-r2; 66 / 0 on dev): the three pinned behaviour round
2 changed on purpose. The lead ruled on 2026-10-12 and the three checks
moved to the ruled contract in round 4, **66 passed, 0 failed** under cage
on lane-key-t2: an invalid CLI value is reported (`settingsInvalid`),
logged as ignored, and keeps the active source and its channels (D16 as
narrowed by D-SINK-19 -- the old check wanted the guide blanked); a host
that cannot write our entry refuses only the MIRROR, which is logged (`no
writable bar entry for the settings change`), left for the next start to
repair, and never raised as `persist_failed` for a switch that has already
happened (SR25 as amended: `persist_failed` is now the state write
failing, reported from the FileView as `state_write_failed`, which
`key-scenario.sh` F observes).

**Round 6 (2026-10-12; no lettered check added, 63 as before).** The
round-5 live lens found the NULL/NOFIELD split blind to an absent
`pointerState` field: the verb folded `undefined` to null, so on f275bde
(no `pendingEntryKey`) W3, F2 and F5 read `held:NULL` and that half of
each was green. `pointerState` now omits what the tree lacks
(`harness-lib.js`, `pointerStateOf`, driven by `qa-lib-test.sh`). Counts
from the transcripts on lane-key-v1 (78ff442): the forward run **64
passed, 0 failed**, the three `held:` reads NULL as before; `--baseline
f275bde` **39 passed, 25 failed**, the same letters as round 5, and the
held half is now red on its own: W1, W3, W5, F2 and F5 read
`held:NOFIELD` (`held:[NOFIELD]` in W5) where the round-5 transcript read
`held:NULL`. [Round 7, the round-6 live lens's P3: "red on its own" says
more than this run shows. Every one of those checks also differs from its
want in another half on f275bde, so the live run shows the held half is no
longer satisfied, not that it alone would redden a check; that it alone
does is proven at the instrument, `qa-lib-test.sh` reading 439 / 2 with the
round-5 fold put back.] `sources-scenario.sh` **66 / 0** and `logo-scenario.sh live`
**33 / 0** under a nested headless cage on the same tree. Two gate-side
repairs the same round: `check.sh` runs `qa-lib-test.sh` with
`OMARCHY_IPTV_HARNESS_DIR` unset, because one pin asserts the DEFAULT
transcript directory and an exported variable reddened it over a green tree
(the old invocation 440 / 1, the new 441 / 0 with it exported); and the two
load-sensitive timing tests the gate runs (the 10,000-entry parse budget in
`tests/test_playlist.py`, the stub's real-socket seek in `qa-stub-mpv.py
--self-test`) say on failure that the number is load-dependent and how to
re-run that one test alone, with the assertion and the budget unchanged.
No lettered check observes the round-6 code change (a logo toggle before
the first state load, which no harness reaches), so lane A did not run
`--baseline lane-key-u3`; the round-6 live lens did, and it reads **64
passed, 0 failed** (transcript key-20261012-122314-1907775.out, 72.7 s),
as expected: no lettered check separates u3 from v1.

**[Round 11: R17b, which U observed, is OVERTURNED by R21; U1-U7 now observe a guide URL set after the migration being refused.]** **Round 7 (2026-10-12; U1..U7 added, 63 -> 70).** The round-6 data-loss
lens found an input no oracle had covered: an `epgUrl` R12 leaves on the
entry while no source is active, stripped by any heal write (the logo
toggle on the lagging host, observed live by the lens; the switch alone on
the echoing host). R17a keeps a retired input on the entry until it is
consumed, R17b lands a pending EPG on the record a switch or an in-app add
makes active. Segment U lifts the lens's `epg-child.sh`: U1..U4 on the
lagging host through the toggle and then the switch, U5..U7 on the echoing
fake host (`run.sh --host echo`, the lever above) through the switch alone.
Counts from the transcripts on lane-key-w1 (2ccbb74), under the scenario's
own nested cage: the forward run **71 passed, 0 failed** (83.7 s);
`--baseline lane-key-v2` **66 passed, 5 failed** -- U2, U3, U4, U6, U7, with
U1 and U5 green as the controls they are and nothing outside U moved.
`sources-scenario.sh` **66 / 0** and `logo-scenario.sh live` **33 / 0**
under a nested headless cage on the same tree. `qa-lib-test.sh` now unsets
`OMARCHY_IPTV_HARNESS_DIR` inside its default-directory pin itself (a bare
run with the variable exported read 442 / 1 with the old line, 443 / 0 with
the new one), and pins the `--host` lever (443 checks).

**[Round 11: R18d, which A2 observed, is OVERTURNED by R21; K, Z and A now observe refused values settling, the whitespace-wrapped refusal and the in-app add with no competing value.]** **Round 8 (2026-10-12; K1..K3, Z1..Z3, A1, A2 added, 70 -> 78).** The
round-7 data-loss lens reproduced two P1s live with drivers of its own,
and this scenario carried no refused and no whitespace-wrapped value at
all. K lifts its `loop-child.sh`: a refused `playlistUrl` (an ftp:// URL
with a credential) beside an `epgUrl` R12 keeps, the shell's entry writes
(the harness log's `updateEntryInline` lines) and its own CPU ticks
(utime + stime of the recorded pid) counted over a 5 s window opening 2 s
after the shell settles; at most 2 writes and 50 ticks is "settled". Z
lifts `resurrect-child.sh` and `MODE=badws`: a whitespace-wrapped CLI
playlist adopted then removed (Z1, Z2), and a whitespace-wrapped refused
credential beside a working source (Z3). A drives the in-app add's probe
commit through `ipc addSource`, with no guide URL in the form (A1, R17b's
commit half, which the round-7 live lens found no segment reaching) and
with one (A2, the lead's OQ-W3 ruling, R18d). Counts from the transcripts
on lane-key-x1 (7a429cd), under the scenario's own nested cage: the
forward run **79 passed, 0 failed** (133.0 s; every K window read 0
writes and 0 ticks); `--baseline lane-key-w2` **73 passed, 6 failed** --
K1 (17,414 writes, 596 ticks), K3 (19,943 / 637), Z1, Z2, Z3, A2, with K2
and A1 green as the controls they are and nothing outside K, Z and A
moved. Through `--tree` over 7a429cd with one decision removed: the keep
decision comparing the raw entry value against the snapshot again, 75 / 4
(K3, Z1, Z2, Z3 -- K3 reads `settled` and keeps the credential, because
the write-settling half alone stops the loop); the funnel's two settling
decisions removed, 78 / 1 (K1, 14,256 / 601); the probe commit no longer
handing the form's guide URL over, 78 / 1 (A2). `sources-scenario.sh`
**66 / 0** (the 10k switch median 33 ms) and `logo-scenario.sh live`
**33 / 0** under a nested headless cage on the same tree.

**[Round 11: R19b and R19c, which this paragraph's U, Q and V observe, are OVERTURNED by R21; those segments now observe the refusal and the in-app forms (the round-11 subsection).]** **Round 9 (2026-10-12, R19; Y1..Y3, Q1, Q2, V1, H1 added, 78 -> 85; U, K and A re-read).** Both round-8 lenses
found the write skip R18b added coming back after a publish A -> B -> A on
the lagging host, live, and the data-loss lens found the add form's guide
URL superseding a CLI epgUrl set AFTER the form was submitted (and the
same on the edit form). Y lifts the lens's `aba-child.sh` (T=logo, bad,
epg) and starts, as that driver does, over an entry carrying A's URL: over
the harness seed's in-place empty `playlistUrl` / `epgUrl` the first
restore differs by those two keys and Y1/Y3 were green on the tree that
has the defect (measured). Q lifts `race-child.sh`: the probe is held open
by a local listener that answers after 4 s, its pid read from the listener
(`ss -ltnp`) and killed by that pid, in both orders. V lifts `T=edit`. H is
D-SRC-18 at the sink, with F's lever (the state directory 0500 under the
running shell). U, K and A now read `held:` from state.json: R19b holds a
guide URL with no source to land on there and takes it off the entry.
Counts from the transcripts on lane-key-y1 (42850dc), under the scenario's
own nested cage: the forward run **86 passed, 0 failed** (205.2 s; every K
window 0 writes and 0 ticks); `--baseline lane-key-y0` **74 passed, 12
failed** -- U1, U2, U5, K1, K2, K3, Y1, Y2, Y3, Q1, V1, H1, with A1, A2 and
Q2 green as its controls; the two key-mutation patches through `--tree`
**80 / 6** and **81 / 5**, the same letters as before. `sources-scenario.sh`
**66 / 0** (the 10k switch median 35 ms) and `logo-scenario.sh live`
**33 / 0** under a nested headless cage on the same tree. `qa-lib-test.sh`
goes 453 -> 454: three existing wants move with the scenario (the key path
6 -> 9, the restarts 5 -> 7, the U..P log marks 1 -> 3), and one new pin
reads that `cleanup()` kills Q's slow listener by the pid read from the
listener (`ss -ltnp`) rather than by a pattern (parallel rule 3). The
documents of round 9 (lane-key-y2) re-read each count above from lane A's
transcripts: `-181012` 86 PASS / 0 FAIL, `-181343` 74 / 12 with exactly the
twelve letters named, `-182219` 80 / 6 (D2, D3, W2, W3, W4, W6) and
`-182602` 81 / 5 (D3 green).

**[Round 11: R20b and R20c are OVERTURNED by R21; Y4 and L2 stand, L2's want now the R21a keep.]** **Round 10 (2026-10-12, R20; Y4 added, 85 -> 86; L2 re-wanted).** The
ninth review's data-loss lens found a one-decision mutant of R19a, S1b (a
write skipped when its patch equals the lagging host's publish, one line
before the compose), green in node (2,268 / 0) and live (86 / 0) while the
second of two consecutive in-app logo toggles was ignored; Y1 re-sets
`showLogos` from the CLI between its two toggles and so never toggles twice
in a row. Y4 does: ON (the guide's own `g` then `confirm`), then OFF with
nothing between, and reads the stored entry's `showLogos` through a new
`ipc hostEntry` field, `storedShowLogos` (`HarnessLib.storedOwnedValue`,
which `qa-lib-test.sh` drives rather than greps). L2's want moved: R20c
makes the patch-only logo write keep only a valid input the last landed
state does not hold, and the harness seed's EMPTY `epgUrl` is no input, so
L2 now asks for `playlistUrl` (the only copy) and `sourceKey` beside
`showLogos`, read from the write's `keys:` list and its `playlist (set)`
mark, and no longer for `epgUrl`. Counts from lane A's transcripts on
lane-key-z1, under the scenario's own nested cage (harness directories
`/run/user/1000/omarchy-iptv-za-<n>`, removed after), re-read by the
documents lane: the first forward run, on 92395c4 under the old L2 want,
**86 passed, 1 failed** -- L2 `keys:0` with every other L and F check
green (`key-20261012-210503-3375256`); forward on 0d407e5, the tip's code,
**87 passed, 0 failed** (`-211001-3410753`, 232.2 s; Y4
`on1:true/1 off2:false/2 stored:false`); `--baseline lane-key-y2` **87 /
0** (`-211409-3439299`) -- round 10's repairs have no red segment here, and
were observed at the sink only by the round-9 lens's own driver
(`r9-child.sh`, in the session scratch) under lane A's cage; the S1b export
through `--tree` **86 / 1**, Y4 `got [on1:false/0 off2:false/0
stored:false]` (`-211919-3462671`). `sources-scenario.sh` **66 / 0**,
`logo-scenario.sh live` **33 / 0** and `tls-scenario.sh` **48 / 0** (in a
cage rendered with `WLR_RENDERER=gles2`, which mpv needs there; a pixman
cage asserts in `vo_x11_init`, measured in round 9). `qa-lib-test.sh` goes
454 -> 455: two wants move with the scenario and one new pin drives
`storedOwnedValue`. The two key-mutation patches were not re-run through
`--tree` this round, and the counts the scenario's header quotes for them
(58 / 6 and 59 / 5) and its baseline narrative, which describes
lane-key-y0's reds whatever `--baseline` names, predate rounds 8 to 10.

**The weak already-stored check, fixed in round 4.** 'a switch the host
already stores is not reported as a persist failure' means to make the
fake's `updateEntryInline` take its `!dirty` branch (the host's "already
stored", `false` as success). The first version pre-set `playlistUrl` on
the stored entry, which no D-SINK-19 write can match, so the branch's log
line `updateEntryInline: nothing changed (already stored)` (shell.qml, the
only place the string exists) never appeared on any tree and the check
passed on `ok` alone -- rule 14's shape, found by the round-2 live lens.
It now seeds `sourceKey` on the stored side (`ipc setStored sourceKey
<key>`) and waits for one MORE of that line than the log held before, so
an earlier line cannot satisfy it; `qa-lib-test.sh` pins the seed and the
wait.

#### Round 11 (R21): one migration, then nothing on the entry is an input

The product owner dropped the `omarchy bar set` URL route on 2026-10-13. The
bar entry's `playlistUrl` and `epgUrl` are read while the state the service
last saw LAND does not carry `entryMigrated`, and refused after it: never
adopted, reported once per value (a desktop notification and the console,
the sentence Model.entryInputNotice composes from the setting's name), and
stripped by the next owned write. key-scenario.sh follows: `seed <key>
migrated` writes the marker; G observes it landing, the REAL 0.13.6 helper
(the v0.13.6 tag) dropping it, and the re-upgrade migrating again; X observes
the refusal at the sink -- the notification is the stand-in
`omarchy-notification-send` shell_arm puts in front of PATH, whose log is the
scenario's own scratch. F and H observe a migration whose write fails from
the start through `fixtures/disk-gone-after-init.py` (the state directory
loses `w` the moment `state init` has run; taking it away before the start
does nothing, because init chmods the directory back to 0700). U, K, Z, A,
Y2, Y3, Q and V observe the refusal where they observed round 9's held
guide URL. `pointerState` derives `landedMigrated` and `memoryMigrated` and
reports `entryInputReports` (names and reasons, never a value). Measured on
lane-key-m1: 98 / 0 forward (97 lettered checks and the floor line), 68 / 30
on `--baseline lane-key-z2`; sources-scenario 66 / 0 and logo-scenario 33 / 0
under a nested cage on the same tree.

#### Round 12 (R22): a state that did not load is never written

The round-11 data-loss lens found a migrated install whose `state.json`
could not be read at the start losing every record to an empty state
written over it, and the same through a state directory that cannot be
entered (the cache layout's save, on 0.13.6 too). What Quickshell's
FileView reports was measured first, one FileView per case in a nested
headless cage: FileNotFound for a missing file AND for a file inside a
0000 or 0600 directory, PermissionDenied for a 0000 file, NotAFile for a
directory or FIFO at the path, `loaded` for an empty or garbage file -- so
the helper's `state init` now reports what it FOUND before it repairs any
mode, and only its `absent` makes a FileNotFound a fresh install.
key-scenario.sh's B segment lifts the lens's `lf-child.sh`: B1-B4 the two
repairable faults at a migrated start (the records survive, and a second
start stands on them), B5-B7 a file that does not parse (the no-write mode:
nothing written, the entry left exactly as it is, one notification, lifted
by putting the file back), B8 the guide's fetch-failure hint as drawn
(`state`'s new `emptyTitle` / `emptyProse` / `errorCheck`). N1 now asserts
the init's verdict (`found:absent`) where it observed the adoption parked.
`pointerState` adds `stateWriteBlocked`, `stateLoadKind`, `stateInitFound`
and `stateWritesRefused` (reasons and counts). The node harness
(tests/service-harness.js) delivers loads through stateFile's own handlers
with the measured error numbers, models the init's reply and repairs as
tests/test_state.py pins the real helper doing them, and RUNS the cache
layout. Measured on lane-key-n1: 106 / 0 forward (105 lettered checks and
the floor line), 97 / 9 on `--baseline lane-key-m2`; sources-scenario
66 / 0 and logo-scenario 33 / 0 under a nested cage.
[Documents lane, 2026-10-13: the two key-scenario counts re-read from lane
A's transcripts, `key-20261013-161816-835970` (106 PASS, 0 FAIL) and
`key-20261013-162220-859113` (97 PASS, 9 FAIL: N1 and B1-B8). Both ran on
4fdb37c, whose plugin files are the tip's. The FileView probe is lane A's,
not in this tree (`lane-n1/fvprobe/` in the session's scratch directory);
its table is in `docs/OMARCHY-PLUGIN-CONTRACT.md`, which is the place to
re-measure it after a Quickshell update. B's observers are the user's view
in `docs/UX-SOURCES.md` 5.10 and the rows SRC-MIG-40..43 and SRC-ERR-10 in
`docs/QA-SOURCES.md`.]

#### Round 13 (R23): the no-write mode's loose ends

key-scenario.sh B9..B14, under the scenario's own nested cage on a private
session bus (`private-bus.sh`, committed this round: a `dbus-daemon` from a
config with no service directories, CLAUDE.md working-in-parallel 6b; the
round-12 copy lived in /tmp and went with the reboot). B9 two no-write
episodes in one session with no own save between, reached by in-place
writes the FileView reloads, each told (R23a). B10 the start-up `state
init` held 60 s by O's slow tree over a file that does not parse: the
service's watchdog stops it at 15 s, `init_pids` (an exact-argv scan of
/proc, never a pattern) finds nothing left running it, and the start
blocks as `init-timeout` (R23c). B11 a no-write start draws the
notification's own words and no form, and `ipc editable` -- a census of
editable text inputs under the guide, new this round -- reads 0 (R23e,
D-CLIP-1). B12 the logo toggle there says the no-write reason (R23f). B13 a
fresh install's drawn copy is the first-run form's (R23h: `state`'s
`emptyTitle` / `emptyProse` now report what is DRAWN, with `emptyShown`,
`firstRunHead` and `stateBlocked` beside them). B14 a FIFO at state.json
(R23b). Counts are the summary line's (R23h): forward 112 / 0;
`--baseline lane-key-n2` 107 / 5 (B10..B14 red; B9 green there, because
the line it guards existed and only its check did not); `--tree` with
`spikes/key-mutations/r23a-no-rearm.patch` 111 / 1 (B9, `told:1/1`), and
with `r23e-editable-field.patch` 111 / 1 (B13, `editable:2`: the census
sees the form's two fields once they are editable). sources-scenario 66 / 0
under an outer headless cage on a private bus, logo-scenario 33 / 0.

The FileView's watch was MEASURED this round, because the round-12 lenses
reported it lost after the view's own first save and the node harness
delivered a reload on every external change (R23g):
`spikes/filewatch/measure.sh` runs one FileView declared as stateFile is,
in a nested cage on a private bus, through 16 sequences of own saves,
helper renames, in-place writes, chmods and restarts; the result it printed
is kept beside it. Every external change raised a reload, before or after
any number of own saves and across a restart; the own save's reload
delivers a load only sometimes (never for a lone save at idle; under load,
or with a later write queued, it lands with the view's own text). The real
Service.qml, driven the same way idle and under six busy loops on four
cores, agreed. So tests/service-harness.js keeps its hand-delivered
external reloads and makes the own-write echo a lever, `ownEcho` "load" |
"none", and scripts/check.sh runs the node suite both ways (2372 / 0
each). The lost watch the lenses reported (D-SRC-19's mechanism) did not
reproduce in any sequence here. [Corrected 2026-10-14, D-DOC-8: this said
"the difference is not known". The round-13 live lens found it -- every
sequence above starts with the state directory PRESENT, and the lenses'
rigs started with it absent, the first session after a fresh install,
where the view raises nothing all session; round 14 measured it in this
spike (set `r24`) and R24c re-arms that session. See Round 14 below.]

[Annotated by the round-13 documents lane (lane-key-p2), 2026-10-14. The
transcripts behind the counts above, in lane A's session scratch directory:
forward `key-20261014-043943-514380` (112 / 0, 277 s), `--baseline
lane-key-n2` `key-20261014-044420-538071` (107 / 5, 294 s),
`r23a-no-rearm.patch` `key-20261013-214109-138686` (111 / 1),
`r23e-editable-field.patch` `key-20261013-230141-283957` (111 / 1),
logo-scenario `logo-20261014-043540-501342`. The real-service half of the
watch measurement (lane A's `svcwatch.sh`) is NOT in this tree: only the bare
FileView spike is. So the mid-session no-write mode AFTER an own save rests on
one uncommitted instrument against the round-12 data-loss lens's opposite
reading, and is UNVERIFIED (rule 14) until a committed scenario observes it;
B9 covers the half with no own save. `docs/ARCHITECTURE-SOURCES.md`'s
round-13 rulings hold the decision request.] [2026-10-14, round 14: the
"opposite reading" was the dir-absent session (above). B16 now observes the
mode beginning after an own save in that session; for a session whose
directory already existed, after an own save, the committed spike and the
round-13 live lens's rig observe it, and no key-scenario segment does.]
[2026-10-14, round 15: B21 observes that last one now (Round 15 below).]

#### Round 14 (R24): the merge, the fresh session's watch, the KILL and the init's own deadline

key-scenario.sh B15..B18, each under the scenario's own nested cage on a
private session bus (`private-bus.sh`). B15 a no-write START's Sources
screen: the header's right slot is the notice's title (`Model.
stateUnreadableNotice`), no Add rows, no add hint, and `a` opens no form,
says the no-write reason and leaves no editable field (R24f). B16 the
FRESH install's first session in the production shape -- `run.sh` makes
XDG_STATE_HOME and `h clean` removes `omarchy-iptv/` under it -- where a
hand-run `state source add` is seen, kept through the next in-app add's
save, and garbage written in place after that save is noticed and told once
(R24c). B17 a start-up init that IGNORES TERM is KILLed and reaped, the
load blocking as `init-timeout` (R24g; the watchdog line and the kill line
are both read from the log). B18 the shell stopped 5 s into a held init:
the init outlives the shell, reparented to `systemd --user`, and ends by its
own SIGALRM deadline, polled by its recorded pid to its start plus 36 s
(R24d). `left:` in B17 and B18 is `init_pids`, the exact-argv scan of
/proc; whatever it finds goes to ORPHANS and the scenario's cleanup kills it
by pid. Counts are the summary line's, the floor 115 lettered checks:
forward 116 / 0 (`key-20261014-095236-969838`, 342.5 s, on lane-key-q1
318af7f); `--baseline dev` (ced1bd1) 113 / 3, B15 `header:[No sources]
rows:2 after-a:sourceEdit says:other`, B16 `seen:0 file:D blocked: told:0`
and B18 `after-deadline:alive(<pid>)` (`key-20261014-095838-996891`); B17 is
green there, because dev had the KILL, and is seen red through `--tree`
with `spikes/key-mutations/r24g-no-kill.patch`: 115 / 1, `blocked:
helper:no(<pid>) left:<pid> told:0` (`key-20261014-100528-1027361`). B15's
`addhint` token cannot go red at row 0 (dev's Add-row hints carry no ` add`
either); its other tokens can. sources-scenario 66 / 0 and logo-scenario
33 / 0, each as the child of a nested headless cage on a private bus. The
transcripts are in lane A's session scratch directory, not the tree. The
R24a merge has no live segment: the ruling asked for the fixture table and
`tests/service-harness.js`, and the data-loss lens's WF FAV WOK HADD FAV
runs there on both hosts, both echo modes, parked, in flight and failed.
[2026-10-16, F-HARNESS-31: in flight it now LOSES the helper's record, the
measured view's same-instant loss; parked and failed still keep both.]
[Round 15: B19 is the merge's live segment now, and two of its decisions
that survived every check above are pinned (Round 15 below).]

What changed in the rigs:
- `fixtures/slow-helper.py` gains `OMARCHY_IPTV_SLOW_IGNORE_TERM=1` (a
  slowed verb ignores SIGTERM; SIG_IGN survives the exec, so the real
  helper ignores it too) and `OMARCHY_IPTV_SLOW_AT=inside` (instead of
  sleeping before the real helper, run it in this process with its first
  `lstat()` of a `state.json` held -- a hung filesystem made deterministic --
  so the real verb's own code, its alarm included, is what is held; the
  helper is loaded with bytecode off from the scenario's scratch copy, so no
  `__pycache__` is written). Measured alone with `SLOW_AT=inside` and
  `SLOW_MS=60000`: `state init` died `Alarm clock` (rc 142) after 30.2 s.
- `private-bus.sh` hands its command a HOME of its own (F-HARNESS-25):
  HOME, XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_CACHE_HOME and XDG_STATE_HOME
  inside `DIR/home`, removed with DIR at exit; MPV_HOME and XCOMPOSEFILE
  dropped; XDG_RUNTIME_DIR left alone (the nested socket and the quickshell
  instance registry live there). A scenario run under it therefore sees the
  scratch home as HOME; lane A's runs passed
  `OMARCHY_IPTV_HARNESS_REAL_HOME=$HOME` so that `run.sh`'s theme copy
  (`seed_scratch_theme`, through `qa_harness_real_home`) still reads the
  real theme, read-only:
  `OMARCHY_IPTV_HARNESS_REAL_HOME=$HOME scripts/dev-harness/private-bus.sh
  /run/user/1000/omarchy-iptv-q1-b2 2400 env
  OMARCHY_IPTV_HARNESS_DIR=/run/user/1000/omarchy-iptv-q1-2
  scripts/dev-harness/key-scenario.sh live`. `tests/test_harness_home.py`
  `PrivateBusIsolatesHome` runs `private-bus.sh` for real with a probe, and
  the filewatch spike with a stand-in `cage` that records the environment it
  is handed, each against a decoy home, and was red against dev's scripts (2
  of 2).
  Lane A also compared the real home before and after every cage run (the
  mesa shader cache's mtime, the `~/.config` and `~/.cache` listings):
  unchanged.
- `spikes/filewatch/measure.sh <helper> r24` is a second sequence set (Q..X,
  below in Spikes); `spikes/key-mutations/` gains `r24g-no-kill.patch`, and
  `d3-save-parked.patch` and `r14-no-return.patch` are re-made because R24a
  moved their hunks (the same decision broken, the same comment).
- The node double (`tests/service-harness.js`): a boot with no file and no
  fault starts `dirAbsent` and UNARMED, as measured; `reload()` arms it once
  the file exists; `h.foreign()` and the own-write echo reach only an armed
  view; the init's creation raises a load only when armed; `dirPresent:
  true` gives the other shape; and it decides what a TERM-ignoring process
  does, so the KILL is observed (rule 10: an always-armed double fails the 2
  R24c double checks).

#### Round 15 (R25): the restore, the merge observed, the existing folder after an own save, and the mid-session header

key-scenario.sh B19..B22, each under the scenario's own nested cage on a
private session bus. B19 (R25d, F-HARNESS-26), the R24a merge's first live
observation: after the start-up init has run (it makes the state folder
0700 again, so taking `w` away before it measured nothing on the first
try, `held:false merged:0`), the folder loses `w`, so the in-app label
change's atomic save fails and is HELD; two hand edits IN PLACE (an
existing 0600 file needs no folder `w`) add a favourite and remove it again
inside that one window -- the round-14 lens's a5 -- then a hand-run helper
write lands (and makes the folder 0700 again), then a second in-app change;
both in-app changes and the helper's favourite must be in the file, the
removed favourite must stay removed, and a restart stands on all of it.
B20 (R25a, D-SRC-30): a copy of `state.json` taken after an in-app save
LANDED, put back with `cp` after an in-app remove landed: the restore is
applied, kept by the next save and by a restart. B21 (R25d): the
EXISTING-folder session damaged after an own save -- a migrated install
starts, an in-app change's save lands, then garbage is written in place:
noticed and told once. B22 (D-SRC-38): that block's Sources header reads
`Saving has stopped`, the rows still there. Counts are the summary line's,
the floor 119 lettered checks: forward 120 / 0
(`key-20261014-153026-1723779`, 385.9 s, load 1.9-2.3, on lane-key-k1
0ccea19; also 120 / 0 on b10b5b6, `key-20261014-143514-1482764`);
`--baseline dev` (002662d) 118 / 2, B20 `restored:1 records:1
label:after-restore restart:1` and B22 `header:Saved sources not loaded
rows:2` (`key-20261014-144201-1513141`); B19 and B21 are green there,
because round 14 had the behaviour and lacked the checks, and are seen red
through `--tree`: `spikes/key-mutations/r25d-a5-base-not-moved.patch` 119 /
1 (B19 `merged:2 ... favs:t:helper.uk,t:h3.uk`,
`key-20261014-144904-1545059`) and `r25d-no-reload-on-change.patch` 110 /
10 (B21 `blocked: told:0`, with D3, W3, W6, B7, B9, B16, B19, B20 and B22,
every segment that needs a reload; `key-20261014-151410-1653892`).
sources-scenario 66 / 0 and logo-scenario 33 / 0, each as the child of a
nested headless cage on a private bus. The printed footer of a `--baseline`
/ `--tree` run now leads with round 15's sentence and says of every older
round's that it was measured on that round's tree (F-HARNESS-28: round 14
had left it naming round 13's reds under a run whose reds were B15, B16
and B18). The transcripts are in lane A's session scratch directory, not
the tree. R25a's a7 half (a foreign write that already carries the
in-flight save) has no live segment -- its window is milliseconds -- and
is pinned in node; R25b's caps and R25c's folder link are not driven live
(the first needs 49 records seeded, the second a link the scenario does
not build); no segment drives a symlinked `state.json` at all, so the
link's limit (R25e) rests on the round-14 lenses' rigs. [Round 16: B23-B29
drive a linked `state.json` and a linked state folder now (Round 16
below).]

What changed in the rigs:
- The scenario's cage is handed 1500 s (was 500): a mutated tree whose
  waits all time out (`r25d-no-reload-on-change.patch`) ran 1007 s, and every
  segment after the cage's end read NOSTATE -- a red for the wrong reason.
  Still inside `private-bus.sh`'s 2400 s.
- `spikes/filewatch/measure.sh <helper> r25` is a third sequence set:
  bursts and spreads of the view's own `setText` (2, 3, 5, 10 texts; 0, 2
  and 5 ms apart), idle and under busy loops, with `shell.qml` logging every
  signal in order through new `burst` / `spread` IPC, to learn what TEXT
  each echo carries (R25a, rule 10). `RESULT-2026-10-14-r25.txt`: 85 echoes
  over 100 bursts, each the latest `saved`'s text; none stale, none
  superseded, none while a later text was asked. A `Timer` of interval 0
  never fired in that rig, so the 0 ms spread is a `Qt.callLater` chain.
- `spikes/folder-link/measure.py <helper>` (new): the helper as a
  subprocess (`python3 -B -I`, timeout 30) over a symbolic link at each
  folder `ensure_private_dir` makes -- the state folder (to a 0755 folder, a
  0500 folder, an empty folder, nothing, a file), a cache folder, the cache's
  `sources/`, the runtime folder -- and a `state.json` link into a 0500
  folder; it prints each verb's exit, code and message and what is at the
  paths before and after. `RESULT-2026-10-14.txt` holds dev's run and
  lane-key-k1's. It needs no display and runs in a temporary directory under
  `$SCR` (or the default temp directory).
- `spikes/key-mutations/` gains `r25a-keep-landed.patch`,
  `r25a-clear-every-saved.patch`, `r25b-silent-drop.patch`,
  `r25d-a5-base-not-moved.patch`, `r25d-a7-no-inflight-half.patch` and
  `r25d-no-reload-on-change.patch` (its README's table says what each breaks
  and what goes red), and `d3-save-parked.patch` is re-made once more
  because R25a's `unchanged` arm moved its hunk.
- The node double (`tests/service-harness.js`), D-DOC-11 and rule 10: the
  fault `dangling-link` is now a dangling link whose target's FOLDER exists,
  and the view's save over it SUCCEEDS and creates the target, after which
  the link leads somewhere (the round-14 lenses' C6 and Z9); the measured
  failure is `dangling-link-nodir` (sequence X: the folder missing); and
  `folder-link` is a link at the state folder that leads nowhere -- found
  `folder-link` by the init, the save failing for want of a folder. It was
  `blocksWrite` for every dangling link until round 15, more forgiving of
  the plugin than the FileView is in the common case.
- `tests/test_state.py` and `tests/test_source.py`: their in-process
  `run()` disarms the helper's init alarm after every call, so a module run
  alone under load is no longer killed by its own `SIGALRM` (F-HARNESS-27).

#### Round 16 (R26): read before write, no write inside a load, and the reap

key-scenario.sh B23..B31, each under the scenario's own nested cage on a
private session bus, are lane W's service rig made checks (lane-clean-a1,
2026-10-16). Every segment seeds the state with custom labels and one
favourite, arranges a link (`flink`: `state.json` a link to `links/T1`,
`T2` holding another state; `dlink`: the state FOLDER a link to
`links/F1`, `F2` holding another state, `F3` an EMPTY folder made by plain
`mkdir` under the scenario's umask; `dir`: the plain folder), starts the
shell, does one thing the watch cannot see, then makes one in-app change
through `ipc updateSource` and reads the file, memory and the old target.
B23-B25 (S29): the linked `state.json` replaced by `mv`, `sed -i` and `rm`
+ `cp`, each carrying a hand edit -- both edits kept, the old target
untouched. B26 (S29-ln): the link re-pointed with `ln -sfn` at `T2` --
`T2` keeps its own label and favourite and takes the edit, and memory is
`T2`'s. B27 (S40): the folder link re-pointed at `F2` -- the same. B28
(S21, D-SINK-21): at `F3` -- nothing created, `blocked:absent`, `told:1`,
the call `ok` and the next `state_unreadable`. B29 (S35, D-SRC-35): a
link's target moved away (the mode, told) and back (unseen) -- the first
source call refused, its re-read lifts the mode, the second lands. B30
(INLOAD, D-SRC-46): a save failed and held (the folder 0500), the folder
given back, a hand-run `state favorite add` -- the merge's save is reported,
`inFlight:0 saveFailed:false`. B31 (IDLE, R26d): 30 s of an idle shell
loads the file not once, and one save reads it once. FRESH, a replacement
with no save after it, has no check: it is the stated gap, and B31 is what
proves no timer covers it. Counts are the summary line's, the floor 128
lettered checks: forward 129 / 0 (`key-20261016-084228-582473`, on
lane-clean-a1 5ee0e5f; 129 / 0 on 3003ca8 too); `--baseline 1c88877` 120 /
9, exactly B23-B31 (B28 `created:644 holds:[state.json] blocked: told:0`);
through `--tree`, `r26a-no-read.patch` 122 / 7 (B23-B28, B31),
`r26b-no-defer.patch` 128 / 1 (B30), `r26a-no-verb-recheck.patch` 128 / 1
(B29), `r26d-periodic-reload.patch` 126 / 3 (B31 `idle-loads:+15`, and B28
and B29, which the timer answers first); `d3-save-parked.patch` now reads
76 / 53 with D3 and W3 still red (`save-parked:NOFIELD`), because every
in-app save waits behind a read whose base load only `save-parked` keeps
from being applied over the change. One `r26a-no-read` run is VOID and is
not cited: `key-scenario.sh` was edited while that run read it, and bash
reads a script by offset (`line 2730: wn: command not found`, earlier
segments run again); it was ended by its recorded pid and re-run clean.
Do not edit a scenario while a run of it is going. The transcripts are in
lane A's session scratch directory, not the tree.

What changed in the rigs:
- `run.sh reap` and `run.sh`'s own exit end the player through
  `qa_reap_players` (F-HARNESS-30): TERM, a bounded 5 s wait, KILL by pid
  and a final look. A served player under a cage that is going away
  ignores TERM, and phase 1 of this work left six of them spinning at 42-52
  % of a core each for 35-48 minutes. `scripts/qa-lib-test.sh` pins it
  against a TERM-ignoring stand-in mpv: `run.sh reap` ends it and says
  `sending KILL`; 1c88877's `run.sh` left it alive and said nothing. The
  six `--serve` scenarios that end through `run.sh reap` (player, m3,
  rewind, pip, tls, text) and the two chno scenarios, which kill their
  `run.sh` by pid and call `qa_reap_players` themselves, are all covered.
  The helper's own `player stop` is another path and already escalates to
  SIGKILL (quit, TERM at 2 s, then KILL; read, not changed).
- The chno scenarios play every row from `run.sh`'s fixture server
  (`--serve`, port 8765, asserted to be this harness's own by
  `qa_listener_owned`) and compare a play token, the channel id and the
  service's `player.seq` (F-HARNESS-21, F-HARNESS-22; lane H, squashed into
  86d8265). Their mutation patches and the seen-red table are under
  `spikes/chno-mutations/`. The R12 privacy needle is
  `QA_URL_PAST_HOST_ERE`, which matches a URL with something after its
  host, so a compliant `scheme://host` redaction is not read as a leak;
  `sources-scenario.sh`, `pip-scenario.sh` and `id-rotate-scenario.sh` still
  carry the bare `://` needle (not migrated).
- `spikes/key-mutations/` gains the four R26 patches above, and
  `r25a-keep-landed.patch` and `r25a-clear-every-saved.patch` are re-made
  because R26b wrapped `onSaved`'s body (the same decisions broken).
- The node double (`tests/service-harness.js`, R26c, F-HARNESS-29) models
  what lane W and lane S measured on a bare FileView: a `setText` inside the
  view's own load is "silent" (no `saved`, the echo delivered),
  `handlerWrites` counts writes made inside any of its handlers, a save that
  creates the file sets `mode` to 0666 & ~`umask` and one over an existing
  file keeps it, and `h.replace(change)` changes the disk and unarms the
  watch with no load delivered; `h.verifyWatchdog()` runs the read's
  watchdog from its own text. Dev's suite with only this double swapped in
  reads 12 of 2,502 red: the old double was more forgiving than the view.
  [lane-clean-f1, 2026-10-16: two more. F-HARNESS-31 -- `h.foreign`
  delivers nothing while one of our writes is queued (lane W's `inflight`,
  30 of 30), counted in `h.droppedForeign`; sixteen pins that passed on
  the forgiving shape are re-levelled to the same-instant loss (16 of 2,561
  red both ways). F4 -- `h.elapse(ms)` moves the clock and fires the read's
  watchdog at the interval the tree's `Service.qml` declares (Qt's default
  1000 ms when none), so the 2 s bound is pinned; `r26a-watchdog-20ms` and
  `r26a-watchdog-no-interval` under `spikes/key-mutations/` are its reds.]
- The FileView measurements R26 rests on (`spikes/filewatch-links/`,
  `measure.sh` with sets `links`, `inload`, `inflight`, `timing`, a service
  rig and its results) are committed on branch `lane-clean-w-probe` and
  are NOT in this tree; lane S's probe is in the session's scratch
  directory. The contract's eighth FileView fact records what they printed.

#### Round 17 (R27): no write without a read, the cap, and the notice's words

key-scenario.sh B32, B33 and B35-B37 (lane-sweep-a1, 2026-10-20), each
under the scenario's own nested cage on a private session bus.
- B32 (R27e, D-SRC-42): a block that begins MID-session is told as `Saving
  has stopped`: `saving-stopped:1 not-loaded:0 body:1`. Its body said
  changes made now are not saved until the file can be read again; R28e
  replaced that sentence (true of one way back out of the block, false of
  three), and B32 now reads the mid-session sentence that names them.
- B33 (R27a window a, D-SINK-22): the harness's `editDuringWrite` makes a
  label edit and a second one while the first write is OUT; the second
  waits for it to land and then reads -- `skipped +0`, the wait counted,
  the second edit on disk. On 6f1d176 at idle it is red only through its
  field (`waited:NOFIELD`), because the first write had landed by the
  deferred turn. That is LOAD-DEPENDENT, and this paragraph said "window (a)
  does not open from outside the shell" until round 1's live review ran the
  baseline at load 5-8 and saw it open: `skipped:+1`, a write without its
  read, red on behaviour (`key-20261020-135918-1751390`). So window (a)
  does open from outside the shell under load; the node pins time it
  either way. It is seen red on behaviour
  through `spikes/key-mutations/r27a-wait-never-released.patch` (`--tree`:
  134 / 1 by the summary line, B33, the held edit never written).
- The burst (R27a's measurement, printed, not graded): `burst_run` makes N
  label edits a turn apart through `ipc burst` and reads `ipc burstResult`
  and the read counter. It was a check, B34, and read green on 6f1d176 AT
  IDLE and through the mutation alike, so it was dropped (rule 11); the
  letter is unused. "It could not go red" was load-dependent too: under
  load (round 1's review, load 5-8) 6f1d176's bursts of 5, 10 and 20 made 3,
  5 and 7 writes with only 2, 4 and 6 reads, which the dropped check would
  have read red, while lane-sweep-c1's read as many as it wrote (1/1, 2/2,
  3/3, 6/6). A check that is red only under load is not a gate, so it stays
  a printed measurement. Final run: bursts of 2,
  5, 10 and 20 landed 7, 11, 20 and 29 ms after the first edit with 1, 2, 4
  and 7 writes and as many reads (6f1d176: 7, 9, 19, 36 ms; 1, 2, 4, 7
  writes).
- B35 and B36 (R27d, D-SRC-44): a 0.13.6 install with 50 sources and the
  entry's URL not among them -- the migration does not run (none evicted,
  none added, no marker, the entry keeps its URL, `Sources is full` told
  once, `playlistUrl:full`); then one record removed in Sources, and the
  next reconcile migrates the URL into the freed place, ACTIVE, the marker
  landed, the entry stripped. On 6f1d176: `same:no d:true marker:true
  entry:no told:0` and `records:49 told:0`.
- B37 (R27c, D-SRC-41): 49 records, an in-app add whose probe runs while a
  hand-run `state source add` takes the 50th -- the commit refuses
  `too_many`, 50 on disk with the hand-run one among them, a restart drops
  nothing. On 6f1d176: `probe:ok`, the 51st committed.
- Counts are the summary line's, the floor 133 lettered checks: forward 134
  / 0 (`key-20261020-131102-1636986`, 479.9 s, on lane-sweep-a1 070cd35);
  `--baseline 6f1d176` 130 / 5 with B34 still in it (B32, B33, B35, B36,
  B37), so 129 / 5 now. Not live: window (b), a re-point timed inside a
  write, and window (c), a read stalled for 2 s (no way without FUSE or
  root); the node pins time both. The transcripts are in lane A's session
  scratch directory, not the tree.

What changed in the rigs:
- `tests/service-harness.js` drops the service's own `reload()` while one
  of our writes is queued (`droppedReloads`), as the view does (30 of 30):
  R27a's expired write wait can ask for a read then. Against 6f1d176 alone
  it turns nothing red (2,572 / 0 in both echo modes), because that tree
  never reloads while a write is out.
- `spikes/key-mutations/` gains `r27a-no-wait.patch` (node only, not run
  live) and `r27a-wait-never-released.patch`; four older patches are re-made
  for R27a's moved context, the same decisions broken (their node counts are
  in that folder's README).
- `spikes/filewatch/measure.sh` gains set `r27b` and
  `RESULT-2026-10-20-r27b.txt`: R27b's mitigation recovered 0 of 608
  (the contract's eighth fact).

#### Round 18 (R28): a stalled read keeps the change, a held migration keeps both URLs

lane-sweep-a2, 2026-10-20, on lane-sweep-c1 (R28, the lead's ruling after
round 1's two P1s).
- R28a has NO live segment, as R27a's window (c) had none: nothing in the
  cage stalls a FileView read for 2 s without FUSE or root (a FIFO at the
  path is `not-a-file` and answers at once, round 1's review). Its pins are
  node's, through the shipping Service.qml on both hosts and both echo
  modes, one per way the wait ends (our own late write, a source verb, an
  in-app add, another program's write, the stalled read answering, the
  schedule's re-read) and the restart's stated loss. [Round 19 (R29a): R28a
  and those pins are withdrawn; round 2's live review then DID stall a
  FileView read, with a FUSE passthrough of its own (scratch, not the
  tree), and found R28a writing over another program's change -- Round 19
  below.]
- `tests/service-harness.js`: `stateVerifyWatchdog`'s interval is a
  BINDING now (`root.stateVerifyBoundMs`, the schedule's bound), so the
  double reads it from its own text at every `restart()` and arms the Timer
  with the interval it has then, as QML does. [Round 19 (R29a) withdrew
  R28a and put the literal `interval: 2000` back; the double reads either.]
- B32 reads R28e's mid-session sentence.
- B38 and B39 (R28b): a 0.13.6 install at 50 sources whose entry carries
  the playlist D AND a guide URL, A carrying a guide URL of its own; A
  picked and the shell restarted over the entry the plugin left: the entry
  keeps both, A's own guide URL stands, each start tells `Sources is full`
  and never `Bar setting removed`; then one record removed, and D moves in
  WITH the bar's guide URL, the entry stripped of both.
- `spikes/key-mutations/r26a-watchdog-20ms.patch` and
  `r26a-watchdog-no-interval.patch` are re-made for the binding interval,
  the same decisions broken. [Round 19: re-made again for the literal
  interval, with `r27a-wait-never-released.patch`; node counts in that
  folder's README.]
- Counts are the summary line's, the floor 135 lettered checks: forward
  136 / 0 (`key-20261020-155757-2060758`, 492.4 s, at c06f436);
  `--baseline 843ae87` (lane-sweep-c1) 133 / 3, B32, B38 `a-epg:bar` and
  B39 `d-epg:empty ... a-epg:bar` (`key-20261020-161525-2136277`);
  `--baseline 6f1d176` 129 / 7, B32, B33 (`waited:NOFIELD` at load 2-3),
  B35-B37, and B38 / B39, the migration having evicted and run at the
  first start (`key-20261020-160609-2096379`). `sources-scenario.sh` 66 / 0
  (`sources-20261020-161452-2134037`). The transcripts are in lane A2's
  session scratch directory, not the tree.

#### Round 19 (R29): back to R26a's bound, the pair, and two harness fixes

lane-sweep-a3, 2026-10-20, on lane-sweep-c2 (R29, the lead's ruling after
round 2's reviews).
- R29a withdraws R28a (and R27a's window c): a save whose read has no load
  within 2 s is written without it, counted (`stateVerifyNoLoad`) and
  logged, as on 0.14.2. R28a's four counters (`stateVerifySilences`,
  `stateVerifySecondReads`, `stateReadStalls`, `stateVerifyRereads`) left
  `POINTER_FIELDS` with it; the Round 18 bullets above describe a tree that
  no longer exists. Window a stays, with the ruling's proviso: the read the
  held save is released to has R26a's bound, so it never waits longer.
- The proviso was checked live with round 2's slow-file rig (its FUSE
  passthrough, mode Q: only quickshell's read() of state.json stalls),
  rebuilt over this tree in the lane's scratch (`a3-slow`, not the tree):
  an edit, and a second asked while the first one's write is OUT
  (`editDuringWrite`), with every read stalled. The FUSE log reads: read
  stall at +0, w-one written at +2.0 s (no load: `saving without the read`),
  the second edit's read stalled at +2.0 s, w-two written at +4.0 s; no
  74019, no 74017, nothing blocked, both labels across a restart (twice,
  2002 / 2001 and 2103 / 2022 ms; the unstalled control the same with no
  watchdog line). Round 2's HS5 (an in-app add and a hand-run helper add
  during the stall) keeps both on this tree, as on 6f1d176; HS7 (an atomic
  replace adding a favourite during the stall, beside a label edit) loses
  the favourite, as on 6f1d176 -- D-SINK-22's window c, left open and
  documented by the ruling. Transcript `key-20261020-184229-2540898`.
  [F2, 2026-10-20: the two differ by WHEN the other program wrote, not by which program it was -- the FUSE log has the helper's rename 1.7 s after the shell's write without its read and the replace's 1.4 s before it; a helper add within the 2 s bound, or before a later save while the reads stay stalled, is lost the same way (round 3's live review: a helper add followed 1 s later by a label edit, lost 3 of 3 on lane-sweep-c3 and on 6f1d176; node `F2 (<tag>): window (c), stated ...`)]
- B40 (R29d): a 0.13.6 install whose state names A active, A carrying its
  own guide URL, and the bar entry holding an unusable playlistUrl with a
  guide URL beside it -- A keeps its own, one card names the pair, the
  guide URL is in no file, both leave the entry. K1..K3 read
  `playlistUrl:invalid-pair` (one notice) where they read
  `epgUrl:no-source,playlistUrl:invalid`.
- S4 (R29e): `init_pids` requires this run's own `--state-dir` in the argv
  it matches, so a second harness over the same tree's helper no longer
  reads as `left:` in B14 -- and no longer has its helper KILLED by the
  reaps after B10 and B18, which kill what `init_pids` returns. Seen red on
  the unscoped scanner in check-tree (`got:<both pids>`).
- Counts are the summary line's, the floor 137 lettered checks: forward 138
  / 0 (`key-20261020-184353-2546836`, 575.9 s, at e5f6d4d, load 4-6 while
  a gate ran); `--baseline lane-sweep-c2` 134 / 4, K1..K3 (`reports:
  epgUrl:no-source,playlistUrl:invalid`) and B40 (`a-epg:bar ... pair:0
  file:yes`), `key-20261020-190233-2645772`; `--baseline 6f1d176` 127 / 11,
  the same four and B32, B33 (`waited:NOFIELD`), B35..B39
  (`key-20261020-185340-2605786`). `sources-scenario.sh` 66 / 0
  (`sources-20261020-185340-2605788`). The transcripts are in the lane's
  session scratch directory, not the tree.

### The open, measured with its delegates (D-PERF-1, R27f; R28d)

```
scripts/dev-harness/open-scenario.sh check-tree                                         # the instrument arm, node only; run by check.sh (19 checks)
scripts/dev-harness/private-bus.sh <dir> 1800 scripts/dev-harness/open-scenario.sh live  # the instrument arm, then the shell arm under its own nested cage
scripts/dev-harness/private-bus.sh <dir> 1800 scripts/dev-harness/open-scenario.sh live --tree <export>   # e.g. an export carrying spikes/open-mutations/late-fill.patch
```

`openMs` (the IPC verb every open figure before 2026-10-20 came from)
force-lays-out the channel view in the turn of the summon and stops its
clock there, so the view has not made its delegates when it looks
(D-PERF-1). `openAsync <list|wall>` starts the clock, summons and RETURNS;
a probe Item the harness parents into the guide's window samples the
PRESENTING view on every `frameSwapped` and asks for the next frame.

R28d (2026-10-20) changed what a sample is. R27f counted every delegate in
the view's contentItem, the cacheBuffer's off-screen ones included (13 rows
and 21 tiles where 10 and 16 are drawn), settled on a count stable over
three frames, and so trailed the drawn screen and passed a view that drew
six rows and filled the rest 300 ms later (round 1's live review). Now a
sample is `HarnessLib.openDrawnSet`: the delegates that are shown, whose
EFFECTIVE opacity is above 0 (R29e: each delegate's own times every
ancestor's up to the window, which `openSample` computes), and that
intersect the view's visible area, and whether they TILE it (contiguous,
nothing missing above, nothing missing below, a grid row whole), measured
against the rows the guide has (its `rowCount`, not the view's count). The
open is realised at the first frame whose drawn set is complete
(`openDrawnSettle`), and the instrument samples 600 ms more, counting
frames whose drawn set changed. `openAsyncResult` answers `running` or
`done` with the summon time, `realisedMs`, `count` (drawn), `built` (every
delegate at the decision), `builtMax` (the most in any frame), and
`changedAfter`. Bounded by 400 frames and 6,000 ms: a run that does not
settle says so in `endedBy`, never a number. A warm open is a CLOSED guide
summoned again (the verb refuses an open guide). Nothing in the product
changes.

The instrument arm drives `openDrawnSet` over thirteen hand-made frames
(D1-D13: a list screen under its cacheBuffer, a gap, a screen filled in
part, a guide that ends on screen, a row missing above, a grid's full rows,
a grid row half-filled, a grid that ends on screen, a hidden delegate, an
empty view, and since R29e a screen at opacity 0, one delegate at opacity 0,
and a screen at 0.3) and `openDrawnSettle` over four (E1-E4), and checks the seam in
`shell.qml` (S1). Each D and E check was seen red on a one-decision
mutation of the function it drives (no "below" test: D3; no gap test: D2,
D9; no "above" test: D5; a grid row not required whole: D7; every built
delegate counted: D1, D2, D5, D6, D9; hidden delegates counted: D9; the
LAST complete frame taken: E1, E3, E4; no tail comparison: E3; opacity
not read: D11, D12). What "drawn" does NOT cover, so no sentence should
claim it: an item stacked over the view, an ancestor's clip narrower than
the view, a layer or shader effect, and a fade's strength -- a delegate is
drawn from its first frame above opacity 0, however faint (D13). The shell
arm grades the instrument (L1-L5 for the list, W1-W5 for the wall: it ran
its tail out, named the view, settled cold and warm, counted a drawn
screen and fewer than the view built, measured after the summon), the
WARM budget (L6, W6: the median warm realised time under 150 ms), and that
nothing drawn changed after any decision (L7, W7). The cold budget is
printed on the BUDGET line, ungraded: the first open of a session is over
150 ms, and that is a product finding for the lead. The legacy `openMs` is
printed beside the cold trace and graded by nothing: round 1's L6 said it
"realised fewer delegates" than the async instrument, which was true only
of the built count; against the drawn screen it reads 10 rows (the same)
and 18 tiles (two more).

`OPEN_CHANNELS` (10000), `OPEN_COLD` (3 shells per view) and `OPEN_WARM`
(8 opens per shell) set the run; each warm open is interleaved with
PERF-02's method A (`open` round trip minus the median `ping`).

Measured 2026-10-20 by lane-sweep-a2 at c06f436 (transcripts in that lane's
session scratch directory, copied 0600; load 1.7-3.0 unless stated):
- forward, 10,000 channels (`open-20261020-154123-1999165`): 30 passed, 0
  failed. List cold realised median 548 ms (540-549), wall cold 534
  (519-537); list warm 33 (27-41), wall warm 31 (27-39); summon 93 / 91
  cold, 12 / 12 warm; drawn 10 rows and 16 tiles, built 13 and 18-21;
  method A median -2 / -4 ms (it cannot see the open). The run before it
  at 2f846b7 (`open-20261020-153505-1977171`) read 526 / 540 cold and 32 /
  31 warm, 30 / 0.
- 40 channels, the control (`open-20261020-155426-2050158`): 30 / 0; cold
  450 / 440, warm 21 / 21, summon 25 / 23 cold and 1 warm. So about 440 ms
  of a cold open is the first show of the guide's window in the cage and
  does not depend on channel count; 10,000 channels add about 100 ms to the
  cold realised time and about 70 ms to the cold summon.
- `late-fill.patch` (`open-20261020-154400-2009476`): 28 passed, 2 failed --
  L6 and W6, warm median 370 / 362 ms; the cold traces show the six-row
  frame refused as `below` before the filled one. (The run before
  L4's comparison moved to `builtMax`, `open-20261020-153752-1987563`, read
  L4 red too, for a reason it does not name: the list drew ten rows a
  frame before it built its three cacheBuffer rows.)
- `openDrawnSet` counting every built delegate, in a copy of the harness
  (`open-20261020-154651-2020565`): 18 passed, 12 failed -- D1, D2, D5, D6,
  D9, L4 (13 of 13) and every W check (a grid's cacheBuffer row is never
  whole, so the wall never settles).
- `slow-delegate.patch` (`open-20261020-155149-2039814`, load 3.7-6.7): 30
  / 0; cold summon 93 -> 207 ms (list) and 91 -> 191 (wall), cold realised
  548 -> 673 and 534 -> 628, warm unchanged at 32. The cold summon grows
  because a cold summon builds delegates synchronously, the hidden view's
  among them.
- R29e (lane-sweep-a3 at e5f6d4d, load 1.4-3.5): forward
  (`open-20261020-192446-2690236`) 33 / 0 -- list cold realised median 547
  ms (546-558), wall 547 (519-572); warm 34 (27-45) and 32 (29-39); drawn
  10 and 16, built 13 and 18-21. `opacity-fade.patch`
  (`open-20261020-192723-2700535`): 31 / 2, L6 and W6 at a warm median of
  338 / 341 ms, where the instrument that read `visible` alone passed the
  same mutation at 33 / 38 (round 2's live review).
So rule 7's 150 ms holds warm and not cold in the cage's floating window;
the production layer-shell surface on Hyprland is UNVERIFIED.

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
intact.

**The echoing host, as a lever (`run.sh --host echo`; D-HOST-4, D-SINK-19
round 7).** omacom/omarchy#15082 makes `publicBarConfig()` read
`shellConfig` directly, so a host carrying it publishes a plugin's own
write at once. The default stays the lagging host above, and every
scenario written against it is unchanged. `--host echo` makes
`syncPluginApis` read `shellConfig.bar` instead of the stale binding, from
the same handler, with NO intermediate stale publish: a fake that handed
the plugin the previous bar first and the current one after would give it
the lagging host's accidental rescue on the echoing host too, more
forgiving than either real host (rule 10) -- which is exactly the rescue
that hid the round-6 data-loss lens's P1 on today's host. `ipc hostEntry`
reports `host: "lag" | "echo"`, so a scenario can assert the lever took;
`run.sh` refuses any other value at the parse and records the variable in
`last-start.env`, and `qa-lib-test.sh` pins both. Only `key-scenario.sh`'s
U5..U7 run on it so far [round 8: and K2, K3, the loop window on the
echoing host]; the other own-write scenarios (E6, the key
mirror, the logo toggle) running both ways is the rest of D-HOST-4. `ipc hostEntry` shows the two sides, and the scenario's
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
- `spikes/logo-decode-bomb/run.sh`: how much memory the row logo slot's
  `Image` allocates for a file whose header declares a size its bytes never
  deliver (D-LOGO-11). The corpus is generated (`make-corpus.py`, stdlib
  only: 32 files, every declared dimension an argument in the call), each
  row is a fresh offscreen qml process under a 2.5 GB address-space rlimit
  (util-linux `prlimit --as`), and every row is judged against a band so a
  Qt that changes the answer is a red exit. Its README holds the table: 72
  MB control, 840 MB for 304 bytes, 1,239 MB for 555, a clean allocator
  refusal for the 65500 progressive pair (Image.Error at 325 MB and at 72
  MB, where a user-session memory scope measured earlier had SIGKILLed
  both), PNG/GIF/WEBP at control memory, and the `QT_IMAGEIO_MAXALLOC`
  bracket that puts the threshold at ceil(dim/8)^2 x 4. It decodes bombs on
  purpose and is never part of the gate; `logo-scenario.sh check-tree` is.
- `spikes/filewatch/measure.sh <helper> [set]`: what Quickshell's FileView
  does to its WATCH (D-SINK-19 rounds 13 and 14). One FileView declared
  exactly as the service's `stateFile` (`shell.qml` beside it), a fresh shell
  per sequence, 1.5 s a step, run under `private-bus.sh` (so a nested cage on
  a private D-Bus with no service directories, and a scratch home). The
  default set is round 13's 16 sequences of own saves, helper renames,
  in-place writes, chmods and restarts (`RESULT-2026-10-13.txt`: every
  external change seen); set `r24` is round 14's (`RESULT-2026-10-14-r24.txt`,
  two runs, dev's helper and lane-key-q1's): Q, the state directory absent at
  the first load -- nothing seen all session; R, S, T, R2, one `reload()` (or a
  path reset) after the start-up `mkdir`/`init` re-arms it for good; U, the
  directory present and the file absent -- the creation seen without help; V
  and W, a valid symlink at the path -- the view's own save writes through
  it, dev's helper replaced it and the view then saw nothing, lane-key-q1's
  writes through and every write is seen; X, a dangling link -- the view's
  save raises `saveFailed` [round 15, D-DOC-11: X's link leads into a
  folder that does not exist; with the target's folder present the same
  save succeeds and CREATES the target, measured by the round-14 lenses' own
  rigs (C6, Z9), and the double now models both]. Set `r25` is round 15's
  (`RESULT-2026-10-14-r25.txt`): what text each echo of a burst of own saves
  carries -- always the latest `saved`'s. The default set is named `r23g`. Needs cage;
  not part of the gate (`tests/test_harness_home.py` runs it with a stand-in
  `cage` only to check where it writes).
- `spikes/folder-link/measure.py <helper>`: what the helper does over a
  symbolic link at each folder it makes private (D-SINK-19 round 15, R25c):
  the helper as a subprocess, no display, one line per verb with its exit,
  code and message and what is at the paths before and after.
  `RESULT-2026-10-14.txt` holds dev 002662d's run and lane-key-k1's: a link
  that leads to a folder is followed and that folder made 0700; one that
  leads nowhere was an empty listing (exit 0) or a traceback before, and is
  a sentence with exit 1 after. Not part of the gate; the python tests
  (`StateFolderLinkTest`, `FolderLinkSiblingsTest`) are.
- `spikes/clip-offer/`: the lead's D-CLIP-1 rig, verbatim -- three probe
  windows (`editable.qml`, `readonly.qml`, `nofield.qml`) and the gdb
  catchpoint on `pipe2` (`gdb.cmds`) that attributed the read to
  `QQuickTextInput::q_canPasteChanged -> QMimeData::text()`. Its README
  holds the lead's table under the user's compositor and the same three rows
  re-measured under a nested cage, with the seat requirement that makes the
  measurement non-vacuous. `clip-scenario.sh check-tree` IS the re-run and
  is part of the gate; the gdb half is for a human.
