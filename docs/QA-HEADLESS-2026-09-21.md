# QA headless pass, 2026-09-21: five rows under cage

Observe-only lane, branch `dev` at 6ac08ef. Everything ran inside a nested
headless `cage` on its own display; the live session (`wayland-1`, quickshell
pid 1058) was never used: the guard printed `WAYLAND_DISPLAY=wayland-0` before
every `run.sh`, `qs ipc` and scenario call and refused `wayland-1`; the user's
pid and the `wayland-1` socket mtime (2026-09-20 14:05:36) are unchanged at the
end. Scratch: `/tmp/claude-1000/obs/` (`h1`..`h5`, `logs/`, `cage/`). Hosts in
fixtures are under `.test` or loopback; no credential anywhere.

This file records what was observed. It does not relabel `docs/STATUS.md`;
the lead does.

## Recipe used (SPIKE-CAGE-HEADLESS.md, followed as written)

```
env -u WAYLAND_DISPLAY -u DISPLAY WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
  setsid nohup timeout -k 5 2400 cage -- sh -c 'echo NESTED=$WAYLAND_DISPLAY > $O/cage/env; ...; exec sleep 2300' &
N=$(sed -n 's/^NESTED=//p' $O/cage/env)         # wayland-0 (read from the child, not assumed)
env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY=$N OMARCHY_IPTV_HARNESS_DIR=$H scripts/dev-harness/run.sh ...
env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY=/run/user/1000/$N XDG_RUNTIME_DIR=$H/runtime \
  qs ipc -p $H/root call io.github.rmcdavid.iptv <verb>      # the plugin's own IpcHandler
```

cage pid 750819, child 750820, nested display `wayland-0`, env file within
0.2 s. A stub `hyprctl` (`exit 1`) sat on `$H/bin` for h1-h4; h5 used the
shipping `stub-hyprctl.py` the PiP scenario installs itself. Every harness was
ready (IPC `service.status == ready`) 2.0-2.3 s after launch, with the three
`Failed to initialize layershell integration` warnings the spike documents.
Teardown: SIGTERM to cage's child 750820; the child and cage were gone within
0.1 s each and `wayland-0` was removed. A second cage (pid 776048, display
`wayland-2`, started 08:36) belongs to another lane and was left alone.

## 1. D-ID-1: the running helper's argv -- PARTIAL, and it found the next defect

Setup: `run.sh clean`; `tests/fixtures/qa-id-rotate/state-seed.json` copied to
`$H/state/omarchy-iptv/state.json`, mode 0600, 728 bytes, BEFORE the start;
`run.sh --keep --detach --playlist <repo>/tests/fixtures/qa-id-rotate/list-v1.m3u`
(a local file source). A bounded watcher (`pswatch.sh`, 30 s) ran
`ps -eo pid,args | grep -F 'bin/omarchy-iptv playlist'` in a loop, dropping
its own `$$`/`$BASHPID` and the grep; no `pgrep -f`. The helper lives about
160 ms on this list (measured 0.155-0.161 s standalone), the loop turned
1,525 iterations in 30 s, and it caught the process on 7 consecutive
iterations (86-92).

The ACTIVE fetch, as the shell spawned it (pid 751874, then 762285 on
`refresh`), verbatim:

```
/usr/bin/python3 /home/ricky/Projects/omarchy-iptv/bin/omarchy-iptv playlist \
  --url /home/ricky/Projects/omarchy-iptv/tests/fixtures/qa-id-rotate/list-v1.m3u \
  --cache-dir /tmp/claude-1000/obs/h1/cache/omarchy-iptv/sources/a09054b7 \
  --state-dir /tmp/claude-1000/obs/h1/state/omarchy-iptv
```

The PROBE (`ipc addSource <repo>/tests/fixtures/qa-id-rotate/list-v2.m3u "" "Probe v2"`,
pid 764770), verbatim, with NO `--state-dir`:

```
/usr/bin/python3 /home/ricky/Projects/omarchy-iptv/bin/omarchy-iptv playlist \
  --url /home/ricky/Projects/omarchy-iptv/tests/fixtures/qa-id-rotate/list-v2.m3u \
  --cache-dir /tmp/claude-1000/obs/h1/cache/omarchy-iptv/sources/bad74aea
```

The helper reported, through the shipping stderr sink into the harness log
(`WARN qml: omarchy-iptv playlist: omarchy-iptv: playlist: moved 8 saved
channel reference(s) onto id scheme 2`): N = 8. `channels.json` carried the
scheme-2 ids (`n:de152e0a`, `n:99ad941e`, `n:d8cf1772`, ... four `t:`, four
`u:`). So the Service.qml join is correct on both call sites: SETTLED for the
argv half of the residue.

What the same observation then showed, and this is the part that matters:

- `state.json` after the fetch was 0600, 1107 bytes, mtime 08:29:06.773, and
  carried the SEED's legacy ids: `favorites` still
  `u:9712e180, t:hotel.test, n:d8cf1772, u:36f90b72, u:4a0e659f, u:402cf731, u:58b2a668, u:e2ffd78c`,
  plus `cacheLayout: 2`, `session: null`, and a `sources` record with
  `fetchedAt` and `channelCount: 16`. Those last three are the SERVICE's own
  write (`handlePlaylistExit -> applyPlaylistStatus -> adoptSourceStats ->
  saveState()`), from the `userState` it loaded before the helper ran.
- `ipc refresh` 3 minutes later: the helper reported `moved 8` AGAIN (log
  line 22). A second identical move proves the file on disk had reverted to
  the legacy ids after the first migration. After that refresh the file was
  rewritten again (mtime 08:32:05.72) and again holds the `u:` ids.
- The in-memory view agrees with the stale file, not with the helper: the
  guide's Favorites scope resolves 4 rows (`favorites=4` in `scopes`; cursor
  on `Hotel TV`) both before and after the refresh. The remapped state would
  resolve 7 (the README's arithmetic: 8 -> 7 after the merge, all 7 present in
  v1's channels.json).
- Service.qml contains no `stateFile.reload()` after a fetch and no call to
  `Model.channelIdRemap` / `Model.remapStateIds`; the only route for the
  helper's rewrite into memory is the `FileView { watchChanges: true }` on
  `state.json`, which the code itself does not trust across the helper's
  atomic rename for `channels.json` (Service.qml 2452, "do not rely on
  inotify surviving the helper's atomic rename"). Two of two fetches lost the
  rewrite; the switch back to v1 (`switchSource a09054b7`) reused the cache
  and spawned no helper, so it gave no third sample.

So the migration runs, writes, and is overwritten by the shell's own save on
the same fetch, every time observed. On disk and in memory the user's
favourites stay on the ids the fix exists to move them off. The terminal
fixture could not see this because nothing in it is the shell. This is the
observation the row said only `ps` during a live fetch could make, and it
made it. Not relabelled here; filed for the lead as the D-ID-1 residue's
answer: argv correct, effect lost.

Evidence: `/tmp/claude-1000/obs/logs/ps-active.txt`, `ps-refresh.txt`,
`ps-probe.txt`, `h1-state-ready.json`; `/tmp/claude-1000/obs/h1/harness.log`
(lines 16 and 22); `/tmp/claude-1000/obs/h1/state/omarchy-iptv/state.json`.

## 2. D-QA-04: `toggle` and `previous` invoked for the first time -- SETTLED

`qs ipc -p $H/root show` lists `target io.github.rmcdavid.iptv` with
`toggle`, `previous`, `next`, `play`, `channel`, `pip`, `stop`, `refresh`,
`status`. Against harness h1 (qs 751342), guide closed first:

```
toggle #1: opened before=False reply='ok' after=True
toggle #2: opened before=True  reply='ok' after=False
toggle #3: opened before=False reply='ok' after=True
toggle #4: opened before=True  reply='ok' after=False
previous (nothing playing) -> 'nothing playing'
next     (nothing playing) -> 'nothing playing'
```

Player half, harness h2 with `--serve` (ffmpeg test stream on
127.0.0.1:8765). Real mpv came up on the nested display without any
setting change (pid 774781, `socketAttached true`; its stderr showed
gpu-next falling back after `VK_ERROR_SURFACE_LOST_KHR`, harmless). Two
findings about the verb's semantics, both by design and both observed:

- `previous` inside the one-channel `Harness` group answered `ok` and
  `nowPlaying` stayed `Harness Live` (`Model.zapRing` rings over the
  channel's own group when launched from IPC; `nextInGroup` wraps to itself).
- a dead-URL channel (`t:bbc1.uk`) cleared `nowPlaying` within 0.5 s (mpv
  `connection refused` -> end-file), so `previous` right after it answered
  `nothing playing`.

With a three-row local playlist whose rows all point at the served stream
(`Zap One/Two/Three`, one group), player pid 775616 throughout:

```
play t:zap.one -> ok        nowPlaying Zap One (1)
previous -> ok              nowPlaying Zap Three (3)   (wrap)
previous -> ok              nowPlaying Zap Two (2)
next     -> ok              nowPlaying Zap Three (3)
stop     -> ok              playing False, nowPlaying None
```

`previous` returns `ok` and moves `nowPlaying`; the same player is reused
(loadfile over IPC, pid unchanged). Nothing blocked it.

## 3. F-CHNO-3: `chno-entry-scenario.sh live` -- PARTIAL (runs headless; the failures are the scenario's)

The scenario is IPC-only (no `wtype`), so it ran to completion under cage:
exit 1, `41 passed, 34 failed, 73 assertions executed`, floor met
(`ran every check it has (72)`). Every failure is a number-entry check
(N1, N2 footer, N13, CN21, N8, N5-N7, N10-N12, N16, N3, N4, N9, N14, N22).

Cause, observed on a fresh harness with the same fixture: the guide opens in
`mode: search` (`Model.guideState` at Model.js:1772 returns `mode: "search"`,
and `Guide.open()` never changes it), and the harness `number` verb routes
through `handleSharedKey`, whose `root.listMode` guard keeps digits literal
in search mode (that is N16's rule). The scenario never calls `ipc mode`
before its first `ipc number`; its N16 block calls `ipc mode` expecting to
ENTER search mode, i.e. it assumes list mode at open. That assumption is
false on every display, not only under cage.

With `ipc mode` first, headless:

```
mode at open: search; after 'ipc mode': list
number 1   -> active True, buffer 1, kind prefix, label 101, cursor BBC One HD   (N1)
number 0   -> active True, buffer 10, kind prefix, label 101                     (N1)
number 300 -> active False, cursor Harness Live, transient 'Channel 300 ...', resume True   (N13, CN21)
after 2.4 s -> buffer '', transient still names 300 / Harness Live               (N2)
number 7.1 -> cursor BBC News after the window                                   (N11)
```

Blocked pending the floating-window mode: nothing in this file; the guide's
model is fully driveable. Still live-only by the scenario's own header: N15
(real key events), N21 (resize + screenshot), N24 (theme re-skin). N3/N4/N9
(play a dead-URL channel, then read `nowPlaying.chno`) will also be timing-
sensitive anywhere, since `nowPlaying` clears within 0.5 s of mpv's refusal
(section 2). Evidence: `/tmp/claude-1000/obs/logs/chno-live.out`.

## 4. D-GS-4: EPG cache files follow the cleared URL -- SETTLED

Harness h4: `gen-playlist.py --profile realistic --channels 30 --epg-ids 1.0
--xmltv gen.xml --now <epoch> --hours 3`; `run.sh --detach --playlist gen.m3u
--epg gen.xml`. Active key `ac6237de`, `status.epg = {configured true,
loaded true}`. Under `cache/omarchy-iptv/sources/ac6237de/`:

```
BEFORE  epg-now.json 600 4543 B   epg-status.json 600 285 B   epg-window.txt 600 7050 B
ipc updateSource ac6237de '{"epgUrl":""}'  -> ok   (persistActive -> onActiveEpgUrlChanged -> cache epg-clear)
AFTER   all three ABSENT; status.epg = {configured false, loaded false}; hostEntry stored=published=ac6237de
```

`run.sh restart-shell`: new shell ready in 0.2 s, `loaded false`, footer
`warning` empty, the three files still absent. `configured` read `true`
after the restart only because the harness re-seeds `OMARCHY_IPTV_EPG` from
`last-start.env` line 4 (the fake host does not persist the cleared entry
across `restart-shell`); the row's symptom was `configured false / loaded
true` with the warning back, and neither half recurs.

The inactive path too: a second source with its own XMLTV (`ebe0280e`) was
added (auto-switched, three files present at 600), the active source
switched back to `ac6237de`, then `updateSource ebe0280e '{"epgUrl":""}'`:
all three files under `sources/ebe0280e/` gone.

## 5. D-PIP-4/5/6: `pip-scenario.sh live` -- SETTLED for 4 and 6, PARTIAL for 5 (one check, not the code)

Ran headless against the shipping `stub-hyprctl.py` (the scenario installs
it on `$H/bin` and sets `HYPRLAND_INSTANCE_SIGNATURE=harness` itself); real
mpv on the served stream, detached shell, restart included. Result:
`83 passed, 1 failed, 84 assertions executed`, floor met. Per step:

| Step | Result |
|---|---|
| preflight | all seams pass |
| P1 availability from `systeminfo` (lua) | pass |
| P2 refusal with no player, no dispatch | pass |
| P3 the service learned the player pid from the player (the D-PIP-6 cascade point) | pass |
| P4 six steps, geometry `[940, 42]` / `[410, 230]`, readback, foreign window byte-identical | pass |
| P5 every vector: our address (51 argv lines), never `class:` (0), no URL, no name, ends in readback | pass except the one below |
| P5 "and never the foreign window's" | FAIL, see note |
| P6 idempotent on | pass |
| P7 off restores `[690, 38]` / `[650, 718]` | pass |
| P8 guide key == verb | pass |
| P11 (D-PIP-4) new shell derives `on` after `restart-shell`, window and foreign window untouched, exit restores | pass |
| P9 user-floated window left alone | pass |
| P10 window goes with the player, pid forgotten, toggle refuses | pass |
| privacy: no `://` in `pipState` or `state` | pass |

The one FAIL: `qa_count "0x559c687e09a0" hypr-calls.log == 0`. The stub log
holds 60 JSON lines (`argv`, `rc`, `out`); the foreign address occurs on 20
of them, every one the `out` of a `-j clients` readback that echoes the
seeded clients list, and on 0 argv lines. `qa_count` greps whole lines, so
the check counts the compositor's answers as if they were commands. The
behaviour D-PIP-5 fixed holds (no dispatch at the stranger, and P4/P11 read
it byte-identical); the check needs to count argv only. Not a code regression.
Evidence: `/tmp/claude-1000/obs/logs/pip-live.out`,
`/tmp/claude-1000/obs/h5/hypr-calls.log`.

## What could not be done here

- A third D-ID-1 sample through `switchSource`: the switch reused the cache
  and spawned no fetch. Two samples (startup, refresh) both lost the rewrite.
- The guide "rendering the merged favourite once" (the row's other residue):
  the merged state never reaches the guide, per section 1, so there was
  nothing to render; and the window does not map under cage anyway.
- The chno scenario's own summary as a pass: it needs `ipc mode` after open
  (or a list-mode payload) before it can be evidence on any display.

## Process notes

- Every wait was bounded and reported (`wait_for`, the watcher's `.done`,
  the `seq 1 N` polls); no `pgrep -f`; kills by pid or by `run.sh reap`
  scoped to the scratch dir. Transient `quickshell` pids seen next to 1058
  during runs were the harness shells (751342, 771446, 773881, 775448,
  784256, 788102, 788729, 788993) and `qs ipc` clients; all gone at the end,
  0 processes bound to `/tmp/claude-1000/obs`.
- Nothing under `~/.config`, `~/.cache`, `~/.local/state` was read for
  writing or written; every helper call carried `--cache-dir` / `--state-dir`
  under the scratch tree. No repo file other than this one was written.
