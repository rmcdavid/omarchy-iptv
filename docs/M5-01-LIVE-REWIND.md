# M5-01 design: live rewind

**Status: APPROVED 2026-10-03, every recommendation in section 9 taken as
ruled ("Go with your recommendations on all twelve and build it"). The
build takes section 10's measurements before its first commit.**

Design pass authorised 2026-10-03 as the successor to decision D2 in
`docs/PLAN-M4.md`. Evidence: `docs/SPIKE-LIVE-REWIND.md` sections 1-7 (the
first pass) and section 11 (the second pass, taken for this design). Four
role lanes and a critic argued the shape; where they disagreed the critic's
resolution is recorded here with its reason, and where a lane's claim did not
survive a read of the code it is listed in section 11 rather than quietly
dropped.

## 0. Decisions at a glance

| | |
|---|---|
| What ships | Rewind, forward and back-to-live inside the buffer mpv already keeps on the plugin's own argv. No new option, no setting, no disk. |
| Where the window comes from | mpv's default cache: back buffer plus donated forward quota, 200 MiB, measured plateau 353-359 s; median predicted window 411 s across the owner's source, minimum 157 s. |
| The verb | `player seek` in the helper, beside `player pause`, same socket, same request ids, same single control slot. The helper clamps; QML never does cache arithmetic. |
| The number | "behind live" = `(wall - wall0) - (pos - pos0)`, zero point re-taken at the first `time-pos` after each `loadfile`, stored on the player keyed by the entry id the stash already carries. Not `cache end - time-pos`, which is wrong after a deep rewind (section 2.3). |
| Keys | Guide list mode `b` back 10 s, `w` forward 10 s, `g` back to live. IPC verbs `back [seconds]`, `forward [seconds]`, `live`. Bindings suggested on SUPER+SHIFT+H / L / R, which are free on stock Omarchy. |
| Feedback | The bar carries a glyph and `-m:ss`; the footer carries one state line; the player carries a numbers-only OSD line (owner decision D9). A clamp is always said, never silent. |
| Privacy | No new sink for the default window. `--demuxer-cache-unlink-files` joins the reserved list; `--cache-on-disk` gets the PO-10 footer warning. Enlarging the buffer, in RAM or on disk, is refused this round (D2, D3). |
| Zap | Every `loadfile` restarts the timeline at zero and discards the history; the readout resets with it. Measured, not assumed. |
| Pause | One feature. Pause and rewind compose in both orders; a long pause reclaims the window from the back buffer at one second per paused second, and the design shows that. `c` and the `pause` verb are unchanged. |
| Out | Any buffer enlargement, an automatic re-tune on `live`, a scrub bar, thumbnails, position across a zap, catch-up, recording. |

## 1. What the measurements settled

Everything below is from the spike, sections 3, 4 and 11, on the owner's own
installed source through mpv 0.41.0 with the plugin's argv.

**Rewind exists, and the properties that said otherwise were the wrong ones.**
`seekable` and `partially-seekable` read false on all 32 channels that played.
31 of 32 rewound 20 s on a relative seek and kept playing, verified by watching
`time-pos` move and then advance. `demuxer-cache-state.seekable-ranges` is the
property that tracks the truth, non-empty on 32 of 32.

**The window is large and already paid for.** `--demuxer-donate-buffer`
defaults to yes, so the back buffer takes the forward quota: the cache total
plateaus at exactly 200 MiB and the back buffer at 353-359 s on the reference
channel. The model `(max_back + max_bytes) / byte_rate - forward_seconds`
lands within 0.3 per cent at two plateaus an eight-fold apart. Across the 31
channels with usable byte samples: minimum 157 s, median 411 s, maximum
1,105 s; all at or above 120 s, 25 of 31 at or above 300 s.

**A zap resets everything (section 11, Q1).** Ten milliseconds after the
`loadfile` reply the previous channel's 91 s of history is gone and the
timeline restarts at zero; `time-pos` first appears about 5.3 s later and the
first rewindable second about 6.3 s after the zap. Zapping back does not
bring the old history. Never compare positions across a `loadfile`.

**Pause and rewind compose, and a pause eats the window (Q2).** A full back
buffer shortens a pause by zero seconds: forward growth stopped at 265 s with
241 s of history and with 10 s, exactly the 150 MiB forward quota. What pays
is the history: once the total hits 200 MiB the floor moves one second per
paused second, from 241 s down to 93 s, the 50 MiB the back buffer owns
outright. Rewind then pause held the position with zero drift and resumed from
it; pause then rewind moved 30.03 s with the picture frozen and resumed from
the rewound point.

**The seek is instant and the watchdog is not in play (Q3).** A 300 s
backwards seek replied in 0.10 ms and the next `time-pos` read, 0.34 ms later,
already read exactly 300.0 s less. Playback resumed within 1.12 s at a median
1.001 s per second. The control-slot watchdog is 8 s.

**`cache end - time-pos` is the wrong number (Q3).** After a deep rewind mpv
stops fetching once the forward buffer is full, the cache end freezes, and
that difference counts DOWN while the real gap holds. The number that holds is
`(wall - wall0) - (time-pos - pos0)`: 300.60-300.64 across thirty ticks while
playing, counting up while paused.

**The floor is exact and the refusal is silent (Q4).** `seekable-ranges[0].start`
is the floor. A seek to the floor lands 1-2 s above it, on the next keyframe,
and plays. A seek one second below it is dropped with the reply `success`,
`time-pos` carrying on, and one error-level log line, `Cannot seek in this
stream`, which `player start` already receives. A build clamps every
backward target to the floor plus a margin, treats `success` as no evidence,
and reads the refusal from `time-pos` or the log line.

## 2. Design

### 2.1 The helper verb

`player seek --socket <s> --by <seconds>` and `player seek --socket <s> --live`,
beside `player pause`, with the same request-id discipline and `probe_client`.
In one run it reads `time-pos` and `demuxer-cache-state`, clamps, issues one
ABSOLUTE seek (mpv's default for absolute is exact, section 11 Q4), reads
`time-pos` again, and replies. A backward target is clamped to
`seekable-ranges[r].start + 2.0`; a forward target to the range end minus
0.5 s; `--live` targets the range end minus 0.5 s. A reply of `success` from
mpv is not evidence of movement: `moved` is the difference of the two
`time-pos` reads, and a request that did not move is reported as refused with
the floor it hit.

One reply schema, carried by `seek`, and the same `rewind` object added to the
`status`, `pause` and `probe` replies so the service's existing ticks carry the
numbers without a new process:

```
{ "ok": true, "kind": "seek", "mode": "by" | "live",
  "requested": -10, "applied": -10, "clamped": false, "clampedTo": null,
  "refused": false, "atFloor": false, "atEdge": false,
  "rewind": { "position": 400.6, "floor": 44.0, "ceiling": 418.0,
              "history": 356.6, "ahead": 17.4, "behindLive": 300.6,
              "zeroed": true, "paused": false, "pausedForCache": false,
              "entryId": 7 } }
```

Numbers and booleans only. Nothing in this reply is a string from the stream,
and `path` is never echoed; the existing status reply emits `pathHost` and
this one emits nothing of the kind at all. The field set of
`demuxer-cache-state` is enumerated on the real player before the first
commit (section 10) so the allowlist the helper forwards is built from an
observed reply.

### 2.2 The zero point, and where it lives

`behindLive` needs a `(wall0, pos0)` taken at the first `time-pos` after each
`loadfile`. It lives on the player, in a third sibling `user-data` node,
`user-data/omarchy-iptv-rewind`, beside the two the detached-player design
already uses, keyed by the `entryId` the stash already captures from the
`loadfile` reply (`bin/omarchy-iptv` apply_channel). A zap changes the entry
id, so a stale zero point is invalid by construction; a shell restart recovers
it from the player exactly as pause state is recovered today, because the
player is authoritative. The helper writes it lazily from `status`, `pause` or
`seek`, whichever first sees a numeric `time-pos` for the current entry.

"No zero point yet" is `null`, never zero. This project's D-DEAD-1 is the
record of what an empty value read as "known and zero" costs; the readout is
absent until the player has something to say.

**Amended at integration (F-RWD-11).** A reading AHEAD of the zero point
moves it. The point is taken where the reader first sits after a `loadfile`,
and the reader sits behind the cache end there by the HLS lead: 3.6 s on the
QA stream, 13-21 s on the owner's channels (spike 11.3). A `live` seek lands
at the cache end, past that point, and the formula then reads negative --
not "ahead of live", which nobody can be, but "the edge was further on than
first observed". Left alone, the `back 10` that follows read 7 behind on a
stream with a 3 s lead and 0 on one with a 20 s lead, under a transient that
said "Back 10 s". So the helper re-takes `(wall0, pos0)` at any reading
whose behind-live is negative, on the verbs that write (`status`, `pause`,
`seek`); the probe, which never writes, returns the raw reading and the
shell clamps it at 0 for display. The invariant the reader can rely on:
`behindLive` from a writing verb is never negative, and a `back 10` after
`live` reads 10.

### 2.3 The service

State: `rewind` (the reply object or `null`), cleared in `play()` beside
`paused`, refreshed by every reply that carries it. The keypress path goes
through the one control slot. Presses are COALESCED: a press while a seek is
in flight adds to a pending sum, capped at the last-read `history` so a sum
past the floor is never asked for, and the next run is throttled 300 ms from
the previous reply. Seek runs are exempt from the health tick's busy count
(`busy = controlProc.running && controlKind !== "seek"`): the three-strikes
restart guards a helper that never returns, which the 8 s control watchdog
now terminates, and a slot re-occupied every few hundred milliseconds by a
sub-second verb is the benign case it must not punish. `drainPendingPlay()`
runs on every path of the new branch (the D-PLY-24 lesson).

"Behind live" counts up only while paused, at 1 Hz. Not on the `nowSec` tick,
which this sentence first named: that tick is 30 s (`epgTickMs`) and re-derives
every EPG fraction on the guide, so a 1 Hz tick on it would re-render the whole
list once a second to move one number. The service runs a dedicated 1 Hz timer
that is live only while paused with a reading to count from (found by the
service lane; stated here so the design and the tree agree). The count-up is
driven by the service's OWN `paused`, the flag the bar's pause glyph and the
footer's "paused" word read, not by the `paused` field of the last reply: the
first integration required both, and in the 100 ms between the optimistic
flip on `c` and the pause reply the glyph said paused while the number held.
One source of truth. While playing the number holds on a healthy stream, so
nothing re-renders. On a stream
that underruns it grows by the stall, with no key pressed (F-RWD-10, 12.9 s in
a minute on one 9.7 Mbps channel), and it is shown unchanged: the viewer is
that far behind, and a number that hid a stall would be the silent failure
this feature was designed never to commit. The 10 s status tick re-syncs
it from the player, which also absorbs seeks made with mpv's own arrow keys,
which are live in the player window today (`--input-default-bindings`
defaults to yes and the plugin passes no override).

### 2.4 Keys and verbs

| Surface | Back | Forward | Live |
|---|---|---|---|
| Guide, list mode | `b` | `w` | `g` |
| IPC verb | `back [seconds]` | `forward [seconds]` | `live` |
| Suggested binding | SUPER+SHIFT+H | SUPER+SHIFT+L | SUPER+SHIFT+R |

The letters are vim's: word back, word forward, go to the end. All three are
free in list mode; uppercase folds like `F`/`S`/`R`/`X`. In search mode they
are query text, as `c` is, which is why the verbs are the surface a watcher
actually uses: rewinding is done with the guide CLOSED, the pause lesson. The
verbs are words like `pause`, `pip`, `channel`; the argument is a positive
integer, so no sign has to survive `omarchy-shell <id> <verb>`, and it is the
user's own step size, which removes any case for a setting. Replies are JSON
like `channel` and `pip`: a refusal is reported, never a false success (CN15).

Step size per guide press: 10 s, one size. The "lands 1-2 s above the target"
reading that argued for 15 s was a read-gap artefact; absolute seeks land on
their target. The first rewindable second arrives about 6 s after a zap and
the median window is 411 s, so 10 s reaches a missed sentence in one to
three taps and a held key covers the rest.

`live` after a rewind deeper than the forward quota (about 265 s at 4.7 Mbps)
seeks to the cache edge and says what remains, `At the edge of the buffer ·
0:27 behind live`. It does not re-tune: the fetch resumes from the frozen edge
with no gap (Q3, Q4), and only a `loadfile` reaches the provider's edge, at
the cost of the whole window. Discarding six minutes of history on a threshold
the viewer never asked for is the one silent action this feature must not
take. Enter on the row remains the reload.

### 2.5 What the user sees

The bar, the only plugin surface visible with the guide closed, gains a
fourth holder after the name, outside the name's elide budget, as the channel
number is: a monospaced `-m:ss`. The glyph is the history glyph U+F02DA while
playing behind live and the pause glyph while paused; the number is shared.

```
playing at live    ▶ 7 BBC One
playing behind     ⟲ 7 BBC One -1:32
paused at live     ⏸ 7 BBC One -0:42        (counting up)
paused behind      ⏸ 7 BBC One -5:12        (counting up)
```

One composer, `Model.playbackStateText({paused, behindS})`, yields `""`,
`1:32 behind live` or `paused · 0:42 behind live`; the footer status line
(`Model.footerStatus` takes it as `playbackState` and rides it after the
name), the bar tooltip (`Model.barTooltip`, `behindS` and `historyS`) and the
bar's accessible name (`Model.barAccessibleName`, spoken through
`Model.spokenSpan`: "1 minute 32 seconds behind live") all call it. The 3 s
transient is `Model.seekTransientText(reply, fallback)` and the glyph is
`Model.barGlyph({..., behindLive})`: every sentence and symbol the feature
shows is a function a test calls (rule 12), none is composed in QML. The tooltip adds the window from the last read:
`up to 6:52 back`. On a channel whose window is 7 s the number is 0:07, not a
promise.

The footer transient (3 s, the slot `Stopped` uses): `Back 10 s · 1:32 behind
live`; at the floor, `As far back as it goes · 6:52 behind live`; at the edge,
`Live`. Footer hints: `b back` whenever something plays and the last range
read is non-empty, `w forward` and `g live` only while behind live, because a
hint that does nothing is the lie the footer was just redesigned to stop
telling. The `?` map picks them up from the same table.

With the guide closed and the player fullscreen, the bar may be hidden, and a
JSON-IPC seek shows no OSD bar of mpv's own. So the player carries one
numbers-only line through `show-text`, composed in Model.js, with a test that
the composer's output never contains `$` -- `show-text` property-expands,
which is the whole reason `--osd-msg1..3` are reserved, so the rule is
"nothing provider-controlled through it", not "no OSD". The user's own
`--osd-level=0` turns it off. This is owner decision D9, and if taken the OSD
joins engineering rule 5's sink list the day it ships.

No desktop notification: M2-03 6.5 and the PiP ruling both refuse a toast for
a foreground action the user initiated.

### 2.6 The reserved list

`--demuxer-cache-unlink-files` joins `MPV_RESERVED` in both mirrors. The
privacy-relevant switch is not whether mpv caches on disk but whether the file
outlives the process: with `whendone` or `no` a copy of the stream survives at
a path the plugin never listed, which is `--stream-record`'s class, and that
option is already reserved. `--cache-on-disk` itself is a user choosing their
own disk, the PO-5 shape, and gets the PO-10 footer warning: "writes the
stream to disk while it plays".

### 2.7 The sentences that change

Seven sites in five shipped files say live streams cannot be wound back:
`README.md` (the `c` row and the playback note), `Model.js` (the pause
comment), `Service.qml` (the pause comment), `bin/omarchy-iptv` (the pause
verb's docstring and the `--help` string) and `contrib/bindings.lua`; plus
`docs/UX.md` 3.1 on the dev branch. All change in the same release as the
feature (D11): a README that denies a feature the release carries is D-LOGO-7
again, and one that promises a feature the release lacks is the same defect
reversed.

`contrib/bindings.lua` also suggests SUPER+SHIFT+C, SUPER+SHIFT+P and
SUPER+SHIFT+COMMA for pause, picture-in-picture and previous channel, and
stock Omarchy binds all three (Calendar, Google Photos, and the utilities
file). That is shipped today and is F-RWD-6; the rewind bindings above were
chosen from the chords that are actually free (H J K L Q R U V Z I).

## 3. Privacy

Rewind inside the default window adds no sink. The 200 MiB cache fills on the
plugin's own argv whether or not anyone seeks; the seek crosses the private
0600 socket with no address in it; nothing forks, nothing is written, nothing
reaches a bus; every new output is a number or a boolean. The one step that is
still assumed, that no field of `demuxer-cache-state` carries a path, is
closed by reading one reply on the real player before the first commit.

Enlarging the window is a different question and it is the owner's. In RAM it
costs linearly on a box reading about 3 GiB available: thirty minutes is 1 to
2.4 GiB per player at these bitrates, and it is reachable today by pasting
`--demuxer-max-back-bytes` into `mpvArgs`, which is unreserved on purpose. On
disk it writes the stream to `~/.cache/omarchy-iptv/` every second at 1.8 to
4.5 GiB per hour into a file mpv unlinks at creation, invisible to `ls` and
`du`, which is D3's refused shape arriving by another door with no honest
disclosure instrument. Both are refused for this round (D2).

## 4. Acceptance

Rule 14 governs: nothing here is accepted by a grep. The stub mpv is more
forgiving than mpv in two measured ways and cannot accept a seek feature
(rule 10); it is taught seek semantics no more forgiving than mpv -- `success`
with no movement below the floor or past the end -- for the service's logic
tests only, and a shared clamp fixture is run by node and python.

The harness scenario runs REAL mpv against a LOCAL live-like stream (an HLS
playlist with a sliding window at a known bitrate, served from the scenario's
own process, so the window is predictable and the run is offline), with checks
R0-R15 from the QA lane, each observed: a seek moves `time-pos` by the request
within tolerance and playback continues; an over-long seek is CLAMPED by the
helper and the reply says so where mpv alone drops it silently -- the check
that MUST be red against today's tree; a zap resets the readout to absent,
not zero; pause then rewind and rewind then pause; a shell restart recovers
`behindLive` from the player; no reply carries a URL; a held key stays inside
the control slot, coalesces, and never trips the health restart. Budgets: the
per-press path through the control slot stays within the 300 ms the probe
already meets (148-161 ms measured), and nothing touches the 150 ms guide
open. The last gate is a bounded live pass on three of the owner's channels
covering the zap reset, both pause orders, the floor refusal, reattach and the
held key.

## 5. Out of scope

A buffer enlargement in RAM or on disk; an automatic re-tune on `live`; a
scrub bar or thumbnails; position surviving a zap; any change to `c` or the
`pause` verb; catch-up, archive and recording (D3 stands); a configurable
step size.

## 6. Size and lanes

Medium: a milestone with four lanes in separate worktrees, the helper lane
landing first with the reply schema frozen. Helper and Model (the verb, the
clamp, the zero point, the composers, the shared fixture); Service, guide and
bar (state, coalescing, keys, readout, OSD, the health exemption, and
ownership of `tests/Model.spec.qml`); QA (the local stream, the scenario, the
stub's seek semantics); documents (the seven sentences, rule 5, UX 3.1 and
4.8, README, CHANGELOG).

## 7. Risks

- A fetch stall after a deep rewind longer than the provider's playlist
  window: one 50 s stall left no gap on one channel; longer stalls are
  provider-dependent and unmeasured.
- The underrun case was seen only in its degenerate form (a rewind in the
  first seconds lands on the first keyframe and moves nothing); the hint is
  gated on a non-empty range, which covers it, but it was not provoked.
- Audio-video sync and subtitles after a cache seek were not examined on a
  real video output.
- One public list, 34 hosts, no credentialed provider.
- Whether the window holds over hours: the longest run is 529 s.

## 8. What this design does not touch

Pause (M2-11) keeps its key, its verb and its measured bound; the design adds
the `live` exit it has lacked since 0.7.10 and shows the window a pause
consumes. Channel identity (D-ID-4) is untouched, because rewind persists no
per-channel reference. Nothing joins the 13-file allowlist.

## 9. Decisions for the product owner

- **D1.** Rewind inside the default window ships with no consent gate.
  Recommended: yes.
- **D2.** The window: mpv's defaults, a RAM-size setting, or a disk buffer.
  Recommended: defaults, with the README naming the `mpvArgs` lever and its
  cost per minute; the RAM setting is a costed follow-on only if use says
  411 s is short; disk is refused this round.
- **D3.** Reserve `--demuxer-cache-unlink-files` and warn on `--cache-on-disk`.
  Recommended: yes.
- **D4.** One feature with pause, `c` and `pause` unchanged, three new verbs.
  Recommended: yes.
- **D5.** Guide keys `b` / `w` / `g`. Recommended: yes.
- **D6.** Verbs `back [seconds]` / `forward [seconds]` / `live`, positive
  argument, JSON replies. Recommended: yes.
- **D7.** Step size 10 s, one size, no setting. Recommended: yes.
- **D8.** `live` after a deep rewind seeks to the cache edge and says what
  remains; it never re-tunes on its own. Recommended: yes.
- **D9.** A numbers-only OSD line on the player via `show-text`, composed in
  Model.js with a no-`$` test, joining rule 5's sink list. Recommended: yes;
  the alternative is a rewind that is invisible in fullscreen.
- **D10.** Seek runs are exempt from the health tick's busy count.
  Recommended: yes.
- **D11.** The seven "cannot rewind" sentences change in the same release.
  Recommended: yes.
- **D12.** M5-01 is the milestone headline, independent of D-ID-4, four
  lanes, helper first. Recommended: yes.

## 10. Measurements a build takes before its first commit

- Enumerate every field of `demuxer-cache-state` on the real player and
  confirm none carries a path or URL; build the helper's allowlist from that
  reply.
- The refusal detector's threshold: the post-seek `time-pos` read over at
  least 20 landed and 10 refused seeks on three channels.
- `show-text` on a windowed player with the plugin's argv: visible at the
  default `--osd-level`, visible in fullscreen, and whether a fullscreen mpv
  hides the bar under this Hyprland.
- Spawn-to-reply time of `player seek` idle and under load, and the achieved
  movement when the key is held 30 s with the throttle; no health restart.
- The zero-point error across several channels and bitrates (0.60-0.64 s
  measured once), to set the 2 s display threshold.
- The zero-point node written and read back across a real `omarchy restart
  shell`, with the number continuous across it.
- Whether the plugin's IpcHandler verbs are reachable from the harness, since
  `run.sh` hardcodes the harness target.

## 11. Claims that did not survive the critic

Recorded so the next reader does not inherit them.

- "A seek lands 1-2 s above its target" was a read-gap artefact; absolute
  seeks are exact by mpv's default, and the 15 s step argument built on it
  fell with it.
- "The status reply echoes `path`" is false; it emits `pathHost`.
- "Four shipping files say rewind is impossible" is seven sites in five.
- Two lanes minted the same id for different findings; the lead assigns ids.
- A proposed zero-point path nested under the existing stash contradicted
  ARCHITECTURE-PLAYER 4.6's deliberate choice of sibling nodes.
- A proposed harness lookup by `pgrep -f input-ipc-server=` is the pattern
  class this project's parallel rule 3 forbids; the helper already reports
  the player's pid.
- The brief's "10 s watchdog" is 8 s in the tree; the margin is four orders
  of magnitude either way.

## 12. Integration amendments, 2026-10-03

What the integrated tree settled that the lanes, each blind to the others'
files, could not. Each is in the section it amends; this is the list.

1. **`coalesceSeek` with no range read yet is NO cap** (2.3). The helper
   lane read null as "cap at 0", so the first press after a zap -- before any
   reply carried a range -- answered "queued, pending 0" and ran nothing: a
   false success (CN15). The service lane's QML spec asserted -10 and was
   red on the integrated tree (69 passed, 1 failed, line 1904); the node
   suite now pins both readings' vectors to -10.
2. **The paused count-up follows the service's `paused`** (2.3), not the
   reply's field; spec line 1910 was the second red (300.6 against 310.6).
3. **F-RWD-11, the zero point moves to a reading ahead of it** (2.2). Found
   by the QA lane on the local stream (QA-REWIND section 7) before any
   helper existed to show it; fixed in the helper at integration with two
   tests seen red against the helper lane's commit.
4. **Every sentence and glyph is a Model function** (2.5): `barGlyph` takes
   `behindLive`, `footerStatus` takes `playbackState`, `barTooltip` and
   `barAccessibleName` take `behindS` / `historyS`, and `seekTransientText`
   replaces 25 lines of Guide.qml. The service lane had composed these in QML
   because Model.js was closed to it and said so (rule 12 debt, paid here).
   Six node checks were seen red against the helper lane's Model.js.
5. **The tooltip's window line needs a window**: `up to 0:00 back` in the
   first instant after a zap promised what `b` cannot do.
6. **The player stub's self-test runs in the gate** (`scripts/check.sh`,
   floor 14 cases), so the stub that refuses like mpv cannot drift silently
   back to one that clamps.
