# Omarchy IPTV - QA plan for live rewind (M5-01)

Owner: QA (lane Q). Status: v0.2 (2026-10-03). v0.1 was written against
`dev` tip `2d7df1f` with `docs/M5-01-LIVE-REWIND.md` approved on all twelve
decisions; v0.2 adds **section 9**, the health exemption (ruling D10) and the
instrument that can go red for a missing one, for F-RWD-18, and re-labels R14
as a control on R13's burst rather than evidence for D10.
The scenario has been RUN on that tree plus this lane's own files (section 6:
red on every check that needs the feature) and has NOT yet been run on the
integrated tree; the lead runs it green after lanes H, S and M merge, and
the counts from that run belong in `docs/QA-RESULTS.md`, not here.

Documents of record: `docs/M5-01-LIVE-REWIND.md` (sections 2.1-2.7 are the
specification, section 4 the acceptance, section 9 the rulings D1-D12),
`docs/SPIKE-LIVE-REWIND.md` (sections 1-7 and 11 the evidence, section 12
the pre-build measurements M1-M5), `CLAUDE.md` engineering rules 10-14, and
`docs/QA-PLAYER.md` for the method codes and the harness conventions this
plan inherits (`A` automated, `H` harness scenario, `L` live shell).

This file is ASCII. U+00B7 (the middle dot in `paused · 0:42 behind live`)
is written ` - ` in quoted microcopy; glyphs are codepoints (U+F02DA).
Numbers quoted as "measured" come from runs on this machine on 2026-10-03
(Omarchy, Quickshell 0.3.1, mpv 0.41.0, ffmpeg with libx264 and drawtext,
Python 3.14.7, four cores, load average about 2 during the runs); numbers
quoted as "designed" come from the design and were not measured here.

## 0. How to read and execute this plan

- Check ids are `R0`-`R17`, one per numbered block of
  `scripts/dev-harness/rewind-scenario.sh`; a block holds one or more
  assertions and the run prints one `PASS`/`FAIL` line per assertion.
- Three files carry it, all QA tooling, none on the plugin's allowlist:
  `scripts/dev-harness/rewind-scenario.sh` (the runner),
  `scripts/dev-harness/fixtures/rewind-probe.py` (the player's own socket:
  every "moved" is read there, never from the reply under test),
  `scripts/dev-harness/fixtures/rewind-sweep.py` (the /proc sweep that
  counts helper runs during the held key). `fixtures/rewind.m3u.in` is the
  two-channel playlist template.
- Run it with a bound, holding the display:

  ```bash
  timeout -k 10 480 scripts/dev-harness/rewind-scenario.sh
  timeout -k 10 480 scripts/dev-harness/rewind-scenario.sh --baseline 2d7df1f
  python3 scripts/qa-stub-mpv.py --self-test
  ```

  It reaps everything it starts (the harness shell, the player, two ffmpeg
  processes by pid, the fixture server by the pid `ss` reports for the
  listener, the exported baseline, the scratch) on exit, Ctrl-C and SIGTERM.
- Exit 0 only when every assertion passed AND the assertion count equals
  the floor at the end of the file (`EXPECTED_CHECKS`, currently 78 plus the
  floor line itself): a check that stops executing turns the run red
  instead of shortening it (player-scenario.sh's D-PLY-9 rule).
- A sentinel is never a pass. The helper's reply is read through
  `qa_json_field` (NOSTATE for no or unparseable output, NOFIELD for an
  absent field), the service through `qa_field`, and the numeric predicates
  `near` and `ge` answer "2" for anything that is not a number, which no
  expected value matches. Against a tree without the verb every reply is
  NOSTATE and every rewind field NOFIELD, which is section 6.
- Severities follow `docs/PLAN.md` section 6. For this feature: **P1** a
  seek that moves the position without saying so, or says it moved when
  it did not (the silent refusal the spike measured, F-RWD-3); a URL in any
  reply, log line or OSD text; a held key that trips the health restart.
  **P2** a readout that reads 0 where it should be absent (D-DEAD-1's
  shape); a clamp not reported; `behindLive` that does not count up while
  paused or does not survive a shell restart. **P3** tolerances and wording.

## 1. The names this scenario joins to the other lanes

The scenario was written against the names in the lead's brief while lanes
H (helper and Model), S (service, guide, bar, harness) and M (documents)
wrote them. Every join is by NAME (rule 13), so each one is listed with
where the scenario reads it; a drift is a red check, not a silent pass.

| Join | Written by | Read by the scenario as |
|---|---|---|
| `player seek --socket S --by N` and `--live` | H | `seek()` in the runner; R1-R5, R15 |
| reply fields `ok`, `kind: "seek"`, `mode: "by"/"live"`, `requested`, `applied`, `clamped`, `clampedTo`, `refused`, `atFloor`, `atEdge` | H | `rf 'd["..."]'` |
| reply object `rewind.{position, floor, ceiling, history, ahead, behindLive, zeroed, paused, pausedForCache, entryId}` | H | `rf 'd["rewind"]["..."]'` on the seek reply |
| service `property var rewind` (null until the player says) | S | `state().service.rewind`, through `rw <field>` and `snap rewind` |
| snapshot fields `playbackStateText`, `barLabel` | S (harness) | `snap <key>`: service half, then guide half, then `widget()`, then top level (**assumed placement**) |
| harness verbs `back(n)`, `forward(n)`, `live()` | S (harness) | `ipc back 10`, `ipc live` |
| plugin IPC verbs `back(seconds)`, `forward(seconds)`, `live()`, JSON replies | S | `pipc back 10` with the harness environment (SPIKE 12.5) |
| plugin IPC verb `pause()` answering `paused`/`playing`/`busy` | shipped | `pause_toggle`, retried on `busy` |
| guide key `b` in list mode | S | `run.sh key -d 60 -- bbbb...` (20 presses) |
| footer hint pairs `b back`, `w forward`, `g live` | H/S | `snap keyboardMap` contains `b=back`, `w=forward`, `g=live` (**assumed** that the `?` map carries them, design 2.5) |
| bar glyph U+F02DA while behind live | S | `widget().glyph` equals the UTF-8 bytes F3 B0 8B 9A (**assumed** the widget's `glyph` is the one that changes) |
| `BEHIND_LIVE_SHOW_S = 2`, step 10 | H | `SHOW_S`, `STEP` in the runner |
| intent counter `playSeq`, lock record `seq`, `healthSkips` | shipped | as `player-scenario.sh` P11 reads them |

The three joins marked **assumed** are the ones the lead's integration run
is most likely to have to re-spell; each is one line in the runner.

## 2. The local stream, and what mpv does with it (measured)

`ffmpeg -re` from `lavfi testsrc` (640x360 at 25 fps, a `drawtext` clock
`%{pts:hms}` burned into the centre of the picture so a rewind is visible
as a position to a person watching the window) and a `sine` tone, libx264
ultrafast with a keyframe every 2 s, nominal 1000 kbps video plus 64 kbps
AAC, muxed as HLS with 2 s segments, a 6-entry sliding playlist and
`delete_segments`, served by a quiet `ThreadingHTTPServer` on
`127.0.0.1:8771`. A second stream (480x270, 660 Hz) is channel B for the
zap. Both run for 540 s and are killed by pid at the end; the playlist
never carries `EXT-X-ENDLIST` during the run.

Measured on real mpv 0.41 with the plugin's own base argv (headless
`--vo=null --ao=null` for the measurement, the spike's justified deviation;
the scenario itself uses the real window), `seekable` false,
`partially-seekable` false, `demuxer-via-network` true, `file-format` hls:

| run | cache | reading |
|---|---|---|
| M-A | mpv defaults | history grew at **1.000 s per s** over 40 s (0.383 -> 36.383, ten samples 4 s apart), floor 0.0 throughout, `ahead` 3.6 s constant (the HLS live edge is three segments behind the playlist end), no underrun |
| M-A | defaults | raw `seek -10 relative`: 40.46 -> 30.46, moved exactly -10.0, 1.04 s later 31.50 (continued) |
| M-A | defaults | raw `seek -100000 relative` with the start still cached: landed at **0.0** (the clamp of spike 4.3), continued |
| M-B | `--demuxer-max-back-bytes=2MiB --demuxer-max-bytes=4MiB` | history 1 s/s until **t=30-35 s**, then a plateau of **30.3-31.3 s** with the floor stepping 4-6 s every 5 s sample: 4.0, 10.0, 14.0, 20.0, 24.0, 30.0, ... 44.0 at t=75; `total-bytes` **6.0 MiB** exactly (the two options summed), `fw-bytes` 0.86 MiB |
| M-B | small | raw `seek -100000 relative` after eviction: reply success, **moved 0.0**, 1.5 s later still advancing: the silent drop |
| M-B | small | raw absolute `floor - 1`: success, moved 0.04 (unmoved) |
| M-B | small | raw absolute `floor + 2` where the floor had been read **six seconds earlier**: success, unmoved -- the floor had stepped past the target in between. Three `Cannot seek in this stream` lines in the player log, one per dropped seek |

Consequences built into the scenario: the raw floor controls read the
floor and seek in one probe call; R4 waits for the floor to have moved
(bounded 60 s) before it asserts the drop, because at floor 0.0 mpv clamps
rather than drops and the control would misread a clamp; and the scenario
runs the player with the shrunken cache through the plugin's own `mpvArgs`
setting (`OMARCHY_IPTV_MPV_ARGS`, which `--demuxer-max-*` passes since it
is unreserved on purpose, design section 3), so the plateau arrives at
about 33 s and the whole run fits in four minutes. The byte rate on the
wire is about 170 KiB/s (5.14 MiB of history over 30.4 s), 1.4 Mbps,
against the 1.06 Mbps nominal: MPEG-TS overhead and the ultrafast encoder.
At mpv's 200 MiB default this stream's window would be about 1,200 s and
the floor would not move inside any run of reasonable length.

Everything in the table was observed on the socket by
`fixtures/rewind-probe.py`; the runner's R0 re-measures the growth rate
on every run (12 s at 2 s, tolerance 0.2 s/s) as the control that the
stream is live-like before any seek is judged.

## 3. The checks

"Red on 2d7df1f" is what the brief required and section 6 recorded: the
helper verb, the service property, the harness verbs and the plugin verbs
are all absent there. "Observes" names the sink read; nothing is accepted
by a grep for a string the implementation was written to contain (rule 14).

| id | what it observes | how | red on 2d7df1f | tolerance |
|---|---|---|---|---|
| pre | time-pos advancing on A; the shrunken cache on the player's argv (`/proc/<pid>/cmdline`) | probe `wait`; `qa_cmdline` | no (controls) | -- |
| R0 | history grows at ~1 s/s on this player | probe `measure 12 2` | no (control) | rate 1.0 +/- 0.2 |
| R1 | `--by -10`: reply kind/ok/mode/applied/refused; time-pos on the socket moved -10; the reply's `rewind.position` agrees; `behindLive` ~10; playback continues | `seek`, probe `range`, probe `wait` | yes (8 of 9; "continues" is a control) | moved +/- 2.5 s, position +/- 2.5 s |
| R2 | `--by 10` from 20 behind moves +10, `behindLive` ~10 | same | yes | +/- 2.5 s |
| R3 | `--live`: `mode live`, `atEdge`, `ahead` <= 1 s, 0 <= `behindLive` < 2, the socket's `ahead` <= 1 | `seek --live`, probe `range` | yes | -- |
| R4 | the floor has been evicted (control); raw `seek -100000 relative` replies success and moves 0 (control: mpv alone drops it); `--by -100000` replies `clamped true`, `refused false`, `clampedTo` ~ floor + 2, time-pos lands there, `applied` is the whole history not the request, playback continues | probe `seek` then `seek --by`, probe `range` | **yes, the required one** (6 of 10; 4 controls) | clampedTo and landing +/- 6.5 s (the floor steps 4-6 s), applied +/- 2.5 s |
| R5 | at the floor, `--by -10` replies `atFloor true` and does not move 10; `behindLive` >= 20 | `seek --by -10`, probe `range` | yes (2 of 3) | moved > -8 s |
| R6 | no helper reply and no harness log line carries `://`, `127.0.0.1:8771`, `live.m3u8` or `/rewind/` | `qa_leak_scan` with a control pattern on each capture | yes for the replies (vacuous capture is a FAIL); the log half is a control | -- |
| R7 | harness `back 10` answers ok; service `rewind.behindLive` ~10; `playbackStateText` matches `0:(08-13) behind live`; plugin `back 10` answers JSON ok and the readout follows to ~20; the hint pairs name b/w/g | `ipc back`, `rw`, `snap`, `pipc back` | yes | +/- 2.5 s |
| R8 | `barLabel` ends in `-0:17`..`-0:24`; the widget glyph is U+F02DA | `snap barLabel`, `widget().glyph` | yes | -- |
| R9 | right after `zap 1`: `rewind` is JSON null (not 0, not undefined) and the text is ""; then B plays on the same pid; the readout returns with 0 <= `behindLive` < 2 and the text "" (positive control) | `ipc zap`, `snap rewind`, `rw` | yes (4 of 6) | -- |
| R10 | pause through the plugin verb; `back 10` while paused moves the socket position -10 with `pause` true; `behindLive` rises ~3 over 3 s; the text starts `paused`; resume continues from the rewound point | `pause_toggle`, probe `range`, `rw`, probe `wait` | yes (3 of 7) | delta 3 +/- 1.5 s, resume +/- 4 s |
| R11 | `back 10` then pause: the position holds (two reads 2 s apart); `behindLive` rises; resume continues from the held point | same | yes (1 of 5; the holds are controls) | hold +/- 0.25 s |
| R12 | `behindLive` known before `run.sh restart-shell` (>= 5); the new shell recovers playing, the same pid, and `behindLive` within 4 s of the value before | `rw`, `run.sh restart-shell` | yes (2 of 4) | +/- 4 s |
| R13 | guide open in list mode; 20 `b` presses 60 ms apart through wtype; >= 1 helper `seek` run (control); FEWER runs than presses; `behindLive` >= 20 afterwards (the capped sum on a ~30 s window) | `rewind-sweep.py`, `rw` | yes (3 of 4) | -- |
| R14 | with seeks issued (control): same player pid, `playSeq` delta 0, lock `seq` delta 0, `healthSkips` 0, still playing. A CONTROL ON R13's BURST AND NOTHING MORE -- it was written as the evidence for ruling D10 and cannot be; see section 9 | `player_seq`, `lock_seq`, `svc` | yes through the control (1 of 6) | -- |
| R15 | five timed `player seek --by -4`: spawn-to-reply median <= 300 ms; the last reply is `ok true` | `date +%s%N` around `seek` | yes for the reply half; the timing half passes on 2d7df1f because argparse fails fast (198 ms), which is why the two are paired | median <= 300 ms |
| R16 | ruling D10 on a PREPARED TREE whose helper sleeps before exec-ing the real one: over a quiet window, that the sampler runs, that health ticks are visible to it, and that `healthBusy` is TRUE while a status HOLDS the slot (the negative control); over a busy window of alternating presses, that `healthBusy` is FALSE for every sample where a seek holds the slot, that `controlRunning` says it is held, that a tick landed on a running seek, and that `healthSkips`, the player pid and `playSeq` never moved | `ipc healthWatch` / `ipc healthLog` sampling the service's own properties at 100 ms inside the shell process; `fixtures/slow-helper.py` | yes, through the sentinels -- `healthBusy` and `controlRunning` do not exist before lane S, and an absent property answers the string `undefined`, never `false` | seek samples >= 100 of ~320; status runs during the busy window < 3 |
| R17 | two seek-queue decisions the slow tree makes observable at all: a press while a seek holds the slot answers `queued` with `pending` equal to THIS press's own size, and a press during the stop ladder is refused `nothing_playing` | `svc controlKind`, `ipc back`, `ipc stop` | yes (no verb, no state) | -- |
| floor | the assertion count equals `EXPECTED_CHECKS` | -- | no | exact |

## 4. Budgets

- **Per-press path**: the probe's own 300 ms bound (design section 4;
  148-161 ms measured for the probe). R15 measures the helper's
  spawn-to-reply for `player seek` from the runner's shell, median of five,
  and prints all five. On 2d7df1f the verb is absent and argparse exits in
  175-200 ms, which is the interpreter's start-up alone; the real number
  arrives with lane H. The sweep in R13 also prints each seek run's
  lifetime at 20 ms sampling, for information.
- **Coalescing** : R13 counts runs against presses and R14 reads the intent
  counter from both sides of the lock, the way P11 does, because that is the
  number a second relaunch moves. **The health exemption (D10) is NOT in
  those two checks** -- it was claimed there and was never observable there.
  Section 9 is the exemption, and R16 is where it is measured.
- **The 150 ms guide open is untouched** by this feature and this scenario
  does not measure it; `ipc openMs` (PERF-01) remains the instrument and
  the lead's integration gate runs it.
- **The OSD line** (D9) is NOT observed by this scenario: `show-text`
  visibility needs a screenshot and was measured once in SPIKE 12.3
  (visible by 64-97 ms windowed, 168 ms fullscreen). The no-`$` property of
  the composer is lane H's shared-fixture test (`tests/fixtures/rewind-osd.json`).
  Until something observes the line on the real window in the integrated
  tree, D9 is **UNVERIFIED** by harness evidence (rule 14).

## 5. The stub mpv

`scripts/qa-stub-mpv.py` is the stand-in the service's logic tests and
PLY-H17/H18 use. It was more forgiving than mpv in every way that matters
to a seek feature: no `time-pos`, no `demuxer-cache-state`, and any verb
it did not know "succeeded". It now carries a clock-driven timeline per
`loadfile` and the measured semantics (the file's docstring lists them;
section 2 and SPIKE 11.1, 11.2, 11.4 and 12.2 are the measurements):
`seek` always replies `success`; inside the range `time-pos` moves to the
target exactly; below an evicted floor or past the end it does not move;
while the start is cached an over-long relative seek lands at 0.0; a
negative absolute target seeks from the cache end; `pause` freezes
`time-pos` while the floor keeps moving once the window is full; every
`loadfile` restarts the timeline and returns `playlist_entry_id`;
`demuxer-cache-state` carries only the twelve numeric leaves of M1.

Rule 10 and 11 evidence. `python3 scripts/qa-stub-mpv.py --self-test`:
baseline **Ran 14 tests ... OK**. Six mutations of the shipping functions,
each applied to a scratch copy and run against the same cases:

| mutation of `qa-stub-mpv.py` | result |
|---|---|
| M-STUB-1 a target below the floor is clamped to the floor instead of dropped | Ran 14, FAILED (failures=2): `test_seek_below_the_floor_replies_success_and_does_not_move`, `test_overlong_relative_seek_is_dropped_once_the_start_is_evicted` |
| M-STUB-2 a target past the end lands | Ran 14, FAILED (failures=1): `test_seek_past_the_end_replies_success_and_does_not_move` |
| M-STUB-3 pause stops the cache end growing (a pause no longer eats the history) | Ran 14, FAILED (failures=1): `test_pause_freezes_time_pos_and_eats_the_history` |
| M-STUB-4 loadfile keeps the previous channel's timeline | Ran 14, FAILED (failures=1): `test_loadfile_restarts_the_timeline_and_discards_the_history` |
| M-STUB-5 a negative absolute target is taken literally | Ran 14, FAILED (failures=1): `test_negative_absolute_target_seeks_from_the_cache_end` |
| M-STUB-6 `demuxer-cache-state` forwards a string leaf | Ran 14, FAILED (failures=1): `test_cache_state_has_only_the_twelve_allowlisted_leaves_and_no_strings` |

The stub's existing consumer still passes on the changed file:
`scripts/qa-player-scenarios.sh run cold --apply` (PLY-H17 and PLY-H18
phase A, no display) **20 pass, 0 fail**.

What the stub does NOT model, deliberately: the 1-2 s keyframe landing
above a floor target (the decoded drift after the landing, F-RWD-8),
underruns, and the 5 s start-up before the first `time-pos`
(`STUB_STARTUP_S`, default 0 so the existing scenarios are not slowed). A
service test that needs the start-up gap sets the variable.

**Corrected after integration (2026-10-03).** This section first said the
stub emits no `log-message` on a refusal and that the immediate read
echoes the target. Both were overtaken by F-RWD-15: mpv's reply to `seek`
means queued, the position moves and the `seek` event goes out afterwards,
and a dropped seek is followed by the error-level refusal line on the
connections that subscribed. The stub now does exactly that -- the move is
deferred until the reply has been written, the `seek` event follows a
landed seek, the refusal line follows a dropped one only on a subscribed
connection -- and its self-test is 17 cases (14 here, two for the
followups, one for the ordering), each seen red by a named mutation
(`docs/QA-RESULTS.md`, the review round). The six mutations in the table
above were run against the 14-case file.

## 6. The run on 2d7df1f plus this lane's files (red, as required)

The runs on the integrated tree -- 72/7 on the first, the two defects that
run found (F-RWD-15 in the helper, F-HARNESS-3 in this scenario) and 79/0
after them -- are in `docs/QA-RESULTS.md`, "the rewind scenario on the
integrated tree".

Third and final run of the finished runner, 2026-10-03, display held,
`pgrep -x quickshell` 2186866 before and after, `pgrep -xc mpv` and
`pgrep -xc ffmpeg` 0 after, port 8771 free, nothing left under `/tmp`.
Exit status 1.

```
== plugin tree /home/ricky/Projects/omarchy-iptv-wt-q   scratch /run/user/1000/omarchy-iptv-harness
== play A and wait for the window to fill
PASS the player is playing A (time-pos advancing; positive control)
PASS the shrunken cache reached the player's argv (control for R4)
== R0 the stream control
PASS R0 history grows at ~1 s/s on the local stream (0.999)
   R0 at the plateau: history 26.96 floor 0.0
== R1 back 10
FAIL R1 the reply is a seek reply (got 'NOSTATE', want 'seek')
FAIL R1 ok (got 'NOSTATE', want 'true')
FAIL R1 mode by (got 'NOSTATE', want 'by')
FAIL R1 applied -10 (NOSTATE)
FAIL R1 not refused (got 'NOSTATE', want 'false')
FAIL R1 time-pos moved back by 10 on the socket (before 27.12, after 27.4)
FAIL R1 the reply's position agrees with the socket
FAIL R1 the reply reports ~10 s behind live
PASS R1 playback continues from the rewound point
== R2 forward 10 (from 20 behind)
FAIL R2 ok (got 'NOSTATE', want 'true')
FAIL R2 applied +10
FAIL R2 time-pos moved forward by 10 on the socket (before 28.44, after 28.72)
FAIL R2 the reply reports ~10 s behind live
== R3 live
FAIL R3 mode live (got 'NOSTATE', want 'live')
FAIL R3 atEdge (got 'NOSTATE', want 'true')
FAIL R3 ahead <= 1 s (NOSTATE)
FAIL R3 behindLive below the display threshold (NOSTATE)
FAIL R3 the socket agrees it is at the edge
== R4 the over-long seek: mpv drops it, the helper clamps it (MUST be red on 2d7df1f)
PASS R4 control: the floor has been evicted (floor 2.0 > 0)
PASS R4 control: mpv alone replies success to seek -100000
PASS R4 control: and does not move (moved 0.0)
PASS R4 control: playback carries on
FAIL R4 the helper says clamped (got 'NOSTATE', want 'true')
FAIL R4 and not refused (got 'NOSTATE', want 'false')
FAIL R4 clampedTo is the floor plus the margin (floor 4.0..4.0, clampedTo NOSTATE)
FAIL R4 time-pos landed near the floor on the socket (before 32.92, after 33.24)
FAIL R4 applied is the whole history, not the request (NOSTATE)
PASS R4 playback continues from the floor
== R5 at the floor
FAIL R5 atFloor reported (got 'NOSTATE', want 'true')
PASS R5 no false 10 s movement (before 34.08, after 34.36)
FAIL R5 the reply reports a behindLive near the whole window (NOSTATE)
== R6 no URL anywhere
FAIL R6 helper replies: leak or vacuous capture (status 2; 6 lines)
PASS R6 the harness log carries neither a URL nor the fixture host
== R7 the service readout through the harness and the plugin verbs
FAIL R7 the harness verb back answers (got 'NOSTATE', want 'true')
FAIL R7 service rewind.behindLive ~10 (NOFIELD)
FAIL R7 playbackStateText says so (undefined)
FAIL R7 the plugin IPC verb back answers JSON ok (got 'NOSTATE', want 'true')
FAIL R7 and the readout followed it (~20, NOFIELD)
FAIL R7 the hint pairs name the keys (b back, w forward, g live)
== R8 the bar
FAIL R8 barLabel carries -m:ss outside the name (undefined)
FAIL R8 the bar glyph is the history glyph U+F02DA while behind live
== R9 a zap resets the readout to ABSENT, never 0
FAIL R9 rewind is null right after the zap (not 0, not undefined) (got 'undefined', want 'null')
FAIL R9 playbackStateText is empty right after the zap (got 'undefined', want '')
PASS R9 now playing B
PASS R9 the same player
FAIL R9 the readout comes back with numbers at live (NOFIELD; positive control)
FAIL R9 and the text is empty at live (got 'undefined', want '')
== R10 pause, then rewind
PASS R10 paused through the plugin verb
PASS R10 still paused on the socket
FAIL R10 the position moved back 10 while paused (before 31.4, after 31.4)
FAIL R10 behindLive counts UP while paused (NOFIELD -> NOFIELD)
FAIL R10 playbackStateText says paused (undefined)
PASS R10 resumed
PASS R10 playback resumed from the rewound point (31.52 vs 31.4)
== R11 rewind, then pause
PASS R11 paused
PASS R11 the position holds while paused (33.44, 33.44)
FAIL R11 behindLive counts up (NOFIELD -> NOFIELD)
PASS R11 resumed
PASS R11 resumed from the held position (33.56 vs 33.44)
== R12 restart the shell while behind live
FAIL R12 behindLive known before the restart (NOFIELD; positive control)
PASS R12 the new shell recovered now-playing
PASS R12 the same player pid
FAIL R12 behindLive recovered from the player (NOFIELD -> NOFIELD)
== R13 a held key is coalesced
PASS R13 the guide is open in list mode
FAIL R13 the helper ran for the presses at all (0 runs; positive control)
FAIL R13 fewer helper runs than presses: coalesced (0 < 20)
FAIL R13 the position reflects the capped sum (behind NOFIELD >= 20, window ~30)
   R13 seek helper lifetimes ms (20 ms sampling): []
== R14 and never trips the health restart
FAIL R14 positive control: seeks were issued (0)
PASS R14 the same player pid
PASS R14 the intent counter did not move
PASS R14 the lock record did not move
PASS R14 healthSkips is 0
PASS R14 still playing
== R15 the per-press budget
PASS R15 player seek spawn-to-reply median 198 ms within 300 (runs: 199 196 198 197 200)
FAIL R15 and the replies were real (ok true on the last)
PASS the scenario ran every check it has

== rewind-scenario: 31 passed, 48 failed, 79 assertions executed
```

Two earlier runs of the runner on the same tree found three defects in the
runner itself, fixed before this one: R0 read NOSTATE because
`probe measure 12` ran under a flat 12 s `timeout`; R4 could race the
eviction (the floor was 2.0 when it ran, and at 0.0 mpv clamps instead of
dropping, which the control would misread); and the pause checks read
`time-pos` within half a second of the pause, where mpv's position creeps
0.12-0.16 s while the audio drains (the spike's 0.000 s drift was measured
from 10 s in). The pause verb also answered `busy` once, mid health-tick,
and is now retried a bounded five times.

## 7. Observations for the lead, with the ids the lead assigned at integration

- **F-RWD-11. The HLS lead and `live`.** On this stream the reader sits 3.6 s behind
  the cache end at the live edge (three segments, the HLS rule). A `--live`
  seek to `ceiling - 0.5` therefore moves the reader 3.1 s AHEAD of where
  the zero point says live is, so the formula `(wall - wall0) - (pos - pos0)`
  reads about -3 unless the helper clamps it at 0. R3 asserts
  0 <= `behindLive` < 2; a negative reading is a finding against the helper,
  not against the stream, and the spike's channels (13-21 s of lead,
  SPIKE 11.3) would show it larger.
- **F-RWD-12. Eviction is quantised.** The floor on a 2 s-segment stream moves in
  4-6 s steps, not continuously. The design's +2.0 s margin is fine when
  the read and the seek are milliseconds apart (the helper's shape), and
  wrong when they are seconds apart (section 2's third raw seek). Anything
  that caches the floor across a throttle window should re-read it.
- **F-RWD-13. `time-pos` creeps after a pause** by 0.12-0.16 s in the first
  half-second. A service test that asserts "holds while paused" at frame
  precision immediately after the flip will flake.
- **F-RWD-14. `run.sh ipc` hardcodes target `harness`** (SPIKE 12.5). This runner
  reaches the plugin's own IpcHandler with its own `pipc`; a `plugin-ipc`
  subcommand on `run.sh` (lane S's file) would let every scenario share it.
- **The stub self-test lives in the stub** (no id: done at integration).
  `tests/` was not this lane's to open, so the cases run through
  `--self-test`; `scripts/check.sh` now runs that command as its own step
  with a floor of 14 cases.

## 8. Not covered here

The bounded live pass on three of the owner's channels (design section 4's
last gate: zap reset, both pause orders, the floor refusal, reattach, the
held key) is the lead's, on the integrated tree. Audio-video sync and
subtitles after a cache seek (design 7), a fetch stall longer than a
provider's playlist window, and the window over hours remain the spike's
open items. The OSD line is section 4's UNVERIFIED entry.

## 9. The health exemption (ruling D10), and why R14 could not see it

Added 2026-10-03 by the QA lane for **F-RWD-18**. Everything in this section
was measured on this machine on that day; the three runs and their counts are
at the end.

### 9.1 What D10 is

`docs/M5-01-LIVE-REWIND.md` ruling D10: **a seek run does not count as busy
for the health tick's three-strikes restart.** The mechanism it modifies is
`Service.qml`'s `healthTimer`: every `healthCheckMs` (10 s) it asks
`Model.healthTick(healthSkips, busy)`; three consecutive busy ticks
(`HEALTH_SKIPS_BEFORE_RESTART`) mean `player restart --from term`. The
restart exists to catch a helper that never returns. A slot re-occupied
every few hundred milliseconds by a sub-second verb under a held `b` is the
benign case it must not punish, so the `busy` argument excludes a run whose
kind is `seek`.

### 9.2 Why R14 could not go red for a missing exemption

R14 asserts that after R13's burst the player pid, `playSeq`, the lock
record and `healthSkips` are all unmoved. Three strikes need the slot found
busy on three consecutive 10 s ticks, i.e. a 20 s span at minimum. R13's
burst is twenty presses 60 ms apart - about 1.2 s - and the measured helper
lifetimes are 208-246 ms. **No restart could fire in that window whether or
not the exemption exists**, so every R14 assertion passed for a reason that
has nothing to do with D10. That is CLAUDE.md rule 14's shape exactly: a
check that cannot go red for the failure it guards is not a check. R14 stays
in the scenario, re-labelled as a control on R13's burst; D10 moved to R16.

### 9.3 The instrument: a wider window, not a luckier sample

Two problems had to be solved, and both are about time.

**The decision is only visible while the slot is held**, and a healthy
`player seek` run holds it for about 220 ms (R15's median, five runs:
213-230 ms). One `run.sh ipc state` round trip is of the same order, so a
shell-side poll samples the window by coincidence. Fixed by sampling INSIDE
the shell process: `ipc healthWatch <ms>` arms a 100 ms `Timer` in
`scripts/dev-harness/shell.qml` that tallies the service's own
`healthBusy`, `controlRunning` and `controlKind`; `ipc healthLog` returns the
tally. Measured sampling fidelity: 280 samples over a 28 000 ms window and
320-321 over 32 000 ms, i.e. the full 100 ms cadence with no drops, on every
run.

**A 220 ms run cannot be caught by a 10 s tick on purpose.** Fixed by making
runs long: `scripts/dev-harness/fixtures/slow-helper.py` sleeps
`OMARCHY_IPTV_SLOW_MS` (4000) and then `execv`s the REAL helper with the
same argv, for the verbs in `OMARCHY_IPTV_SLOW_VERBS` (`seek,status`) only.
It is not a stub: every reply the service parses is the shipped helper's,
only later. R16 stages the tree under test into a scratch directory with
`bin/omarchy-iptv` replaced by it (`bin/omarchy-iptv.real` beside it),
restarts the harness against that tree, and drives presses. The service
spawns `python3 <root>/bin/omarchy-iptv ...`, which is why the stand-in has
to be python and not shell. 4000 ms is chosen under the service's own
`controlTimeoutMs` (8 s): past that the control watchdog terminates the
helper and the slot frees for a reason that is not the exemption.

Measured effect: each seek run holds the slot 3.9-4.2 s, the gap between
runs is the 300 ms `seekThrottle` plus about 100 ms of turnaround, and the
duty cycle over a 32 s window is 294-296 seek samples of 320-321, i.e.
91-92 per cent.

### 9.4 What R16 observes, and why each observation is deterministic

A **quiet window** (28 s, no presses at all):

- the sampler ran: >= 200 samples (280 measured);
- health ticks are visible to it: >= 2 status runs. Measured 3, at
  101/201, 10200/10501, 20200/20501 ms - the 10 s cadence, and the only
  periodic `status` the service has (the health tick is the sole caller
  besides `askPlayerStatus`, which only a pause refusal starts);
- **the negative control**: `healthBusy` is TRUE on >= 20 samples where a
  `status` HOLDS the slot (126-129 measured). Without this, "a seek is not
  busy" would be satisfied by a predicate hard-wired to `false`;
- and never FALSE, and never the sentinel, on such a sample;
- `healthBusy` is FALSE on >= 20 samples with the slot idle (151-152
  measured) and never TRUE there;
- `controlRunning` answered a boolean on every sample, never the sentinel.

A **busy window** (32 s, presses driven back to back, alternating `back 3`
and `forward 3` so the position hovers and never walks into the floor -
`seekBy` refuses `at_floor` locally and spawns nothing, which would collapse
the duty cycle for a reason that has nothing to do with the tick):

- **the control, read from `controlKind`, which every tree has**: a seek was
  really in flight when sampled, >= 100 samples (294-296 measured). This is
  deliberately not keyed on the reducer lane's names, so a red `healthBusy`
  check names the missing join and not a missing seek;
- **the D10 predicate**: `healthBusy` is FALSE on >= 100 samples where a
  seek HOLDS the slot, never TRUE for a running seek, never the sentinel;
- `controlRunning` says the slot IS held on >= 100 of those samples;
- **a tick landed on a running seek**: fewer `status` runs than the 3 ticks
  the window spans. The deduction: a tick that finds the slot held issues no
  status, because `runControl` refuses one while `controlProc.running`;
  a tick that finds it free always issues one. Measured **0 status runs** in
  32 s on all three runs - all three ticks landed on a running seek.
  This is the check that makes the next one non-vacuous, and it is
  arithmetic, not luck: at 91 per cent duty the chance of all three ticks
  landing in a 300-400 ms gap is about 1 in 10^3;
- **the D10 consequence**: `healthSkips` never left 0, `healthSkips` was
  readable on every sample, the player pid is the one from before the window,
  and `playSeq` did not move.

Two assertions in this set pass VACUOUSLY on a tree with no `healthBusy`
property ("never true for a running seek", "never true with the slot idle"):
with every sample in the sentinel bucket, the "true" count is 0. They are
conjuncts of the checks beside them, which cannot pass on such a tree, and
they earn their keep on a tree that HAS the property - run C below reddens
the first of them with 296.

### 9.5 Why the `healthBusy` checks are keyed on the slot being HELD

`controlKind` outlives `controlProc.running` by about one sampler tick at
the end of every run: the `Process` has exited and its `StdioCollector` is
still draining (`waitForEnd: true`), so `running` is already false while the
kind still names the run that just finished - and `healthBusy` is correctly
false there, because nothing IS running. Measured: 2 samples of 128 over
three status runs, on the first run against a tree carrying the reducer
lane's names. The first version of the status check was keyed on the kind
alone and reddened on that handover rather than on the decision; it is the
one check this round re-points, onto a tally narrowed to
`controlRunning === true`. For the two seek checks the same move is a
STRENGTHENING - they now also require `controlRunning` to say the slot is
held. Nothing shipped reads `controlKind` as liveness (`runControl`, the
control watchdog and the health predicate all guard on `running`), so this
is recorded as a property of the instrument's key and **not filed as a
defect**; if the lead reads it as one it needs an id and a board row, which
this lane cannot write.

### 9.6 The prepared-tree technique, with the commands

`--tree <dir>` points the scenario at a directory the way `--baseline <ref>`
points it at a commit. It is how a NAMED MUTATION of a file this lane does
not own is proved red: export the tree, edit the export, run against it.
Nothing in the repository is modified.

```bash
SCR=$(mktemp -d)              # the two mutated trees
for t in B C; do mkdir -p "$SCR/tree-$t"; git archive HEAD | tar -x -C "$SCR/tree-$t"; done
# tree B: the reducer lane's two names stood in, WITH the D10 exemption.
#   after `property string controlKind: ""` in Service.qml, insert
#     readonly property bool controlRunning: controlProc.running
#     readonly property bool healthBusy: controlProc.running && root.controlKind !== "seek"
#   and make the health timer read the property:
#     var tick = Model.healthTick(root.healthSkips, root.healthBusy)
# tree C: the same, with the exemption REMOVED:
#     readonly property bool healthBusy: controlProc.running

scripts/dev-harness/rewind-scenario.sh                     # A: this branch
scripts/dev-harness/rewind-scenario.sh --tree "$SCR/tree-B"  # B: exemption present
scripts/dev-harness/rewind-scenario.sh --tree "$SCR/tree-C"  # C: exemption gone
```

Each run holds the display for about seven minutes and reaps everything it
starts. R16 restarts the harness against its own slow-helper tree, so
`last-start.env` would end up naming a directory the run then deletes; the
EXIT trap removes the record with the tree, and `run.sh restart-shell` after
a run says "no detached start recorded" rather than dying on a missing tree.

### 9.7 The three runs

Verbatim summary lines, all on `scripts/dev-harness/rewind-scenario.sh` at
`3e26c68` plus the cleanup-only commit after it (which runs after the last
check and cannot move a count; run A was re-measured on the final tree,
runs B and C at `3e26c68`):

| run | tree | result |
|---|---|---|
| A | this branch, no reducer-lane names | `== rewind-scenario: 98 passed, 7 failed, 105 assertions executed` |
| B | named mutation: stand-in `healthBusy`/`controlRunning`, exemption PRESENT | `== rewind-scenario: 105 passed, 0 failed, 105 assertions executed` |
| C | named mutation: stand-in names, exemption REMOVED | `== rewind-scenario: 100 passed, 5 failed, 105 assertions executed` |
| A' | this branch again, on the final tree | `== rewind-scenario: 96 passed, 9 failed, 105 assertions executed` |

A' is run A repeated after the cleanup-only commit. Its nine red are run A's
seven, unchanged and identical in their counts, plus TWO PRE-EXISTING checks
that flaked - `R9 playbackStateText is empty right after the zap` (got
`0:16 behind live`) and `R10 behindLive counts UP while paused` (12.187 ->
12.187, no movement at all). Both passed on runs A, B and C and failed on
A' alone, i.e. once in four runs; section 9.9 hands them to the lead.

**Run A**, the seven red, all of them the missing join and none of them D10:

```
FAIL R16 NEGATIVE control: healthBusy is TRUE while a status helper HOLDS the slot (0 samples >= 20)
FAIL R16 and never the sentinel while a status helper runs (got '126', want '0')
FAIL R16 control: healthBusy is false with the slot idle (0 samples >= 20)
FAIL R16 controlRunning answers a boolean, never the sentinel (quiet window) (got '280', want '0')
FAIL R16 D10: healthBusy is FALSE for every sample where a seek HOLDS the slot (0, of 294 by kind)
FAIL R16 D10: and never the sentinel for a running seek (got '294', want '0')
FAIL R16 controlRunning says the slot IS held while the kind is seek (0 >= 100)
```

Every control around them was green on the same run: 294 seek samples of
321, 0 status runs across 3 ticks, `healthSkips` 0, pid and `playSeq`
unmoved. So the instrument worked and only the subject was absent - which is
the state a check that cannot see its subject must report (rule 10).

**Run C**, the five red - this is the proof the new checks can go red for a
missing exemption:

```
FAIL R16 D10: healthBusy is FALSE for every sample where a seek HOLDS the slot (0, of 296 by kind)
FAIL R16 D10: and never true for a running seek (got '296', want '0')
FAIL R16 D10: healthSkips never left 0 across the busy window (got '2', want '0')
FAIL R16 the player was not restarted (same pid as before the window) (got '2970409', want '2968431')
FAIL R16 the intent counter did not move across the busy window (got '1', want '0')
```

Without the exemption **the three-strikes restart actually fired**: the
sampler saw `healthSkips` reach 2 and then the player pid change, which is
`Model.healthTick` returning `restart` on the third busy tick and resetting
the counter. Every control and every negative control on run C was green, so
the five reds are the decision and nothing else. Run B, the same tree with
the exemption put back, is 105 of 105.

### 9.8 What is still UNVERIFIED here (rule 14)

- **The exemption on a REAL 220 ms seek run.** R16 measures the predicate and
  its consequence on runs stretched to 4 s. Ruling D10's benign case is a
  held key at the repeat rate, and the scenario cannot place a 10 s tick on a
  220 ms run on purpose. The step from "the predicate is right" to "the
  restart never fires under a held key" is `Model.healthTick`, which is node
  tested, plus R13/R14 on real runs; that chain is argued, not observed, and
  is marked UNVERIFIED until something observes it.
- **The third strike with the exemption in place.** Run C shows the restart
  firing without the exemption. Nothing shows that three ticks on a seek-held
  slot leave the counter at 0 for thirty seconds rather than for the one
  window measured; the busy window spans 3 ticks and `healthSkips` was 0 at
  all 321 samples, which is the same statement over 32 s and not over a
  longer run.
- **The handover window's size.** 2 samples of 128 bounds it at roughly one
  to two sampler ticks (100-200 ms). It was not measured at finer resolution
  and the number will move with load.

### 9.9 For the lead: two things that need an id and a board row (no defect ids here - see the note)

This lane owns `docs/QA-REWIND.md` and does not own `docs/STATUS.md`. An id
filed in a document with no row on the board makes
`scripts/check-defect-ledger.py` report a problem (verified: a probe id in
this file produced "<id> is filed in docs/QA-REWIND.md but has no row in
docs/STATUS.md" - the probe id is written `<id>` here rather than spelled,
because spelling it would file it), which is the join rule 13 exists to
enforce. So both items
below are described here and handed to the lead in the lane report; the lead
assigns the id and writes the row, and this file gets the id back.

- **R9 and R10 flake, once in four runs.** On run A' only, `R9
  playbackStateText is empty right after the zap` read `0:16 behind live`
  and `R10 behindLive counts UP while paused` read 12.187 twice, three
  seconds apart, i.e. no movement. Neither is about this round's change:
  both are M5-01 checks on M5-01 code, both green on runs A, B and C, and
  nothing in this round touches the zap reset or the paused count-up. Two
  readings: either the guide's reset and the service's 1 Hz count-up are
  genuinely late under load, which is a product finding, or the two checks
  sample too soon after the event, which is a scenario finding. The data
  cannot tell them apart yet, so the item is "two checks that flake" and the
  next step is to re-run A a few times and record the rate. Until then every
  run of this scenario can come back red on these two for a reason the
  reader will mistake for F-RWD-18.
- **The control slot's kind outlives its running flag** by about one sampler
  tick (section 9.5). Measured, understood, and harmless to everything
  shipped - recorded because the next check keyed on `controlKind` as a
  liveness proxy will be wrong in the same way this one was.
