# Spike: live rewind

**Decision D2 of `docs/PLAN-M4.md`, run 2026-10-03. Measurement only; no
build.** Authorised 2026-10-02: "read `seekable` and `partially-seekable`
across the installed list, and the demuxer back-buffer window at a measured
bitrate."

**Verdict first: live rewind works here, on 31 of the 32 channels that
played, with a median window of 411 seconds on mpv's shipped defaults, and
the reading that killed it was of the wrong property.** The feature the
research named as the one people switch applications to get is available on
this machine today. What it costs is memory, and that bill can be moved to
disk -- measured, below.

The number in `docs/PLAN-M4.md` section 1 ("of 22 live streams on 21
providers, exactly one reported itself seekable"), in `docs/UX.md:376`,
`Model.js:4430`, `Service.qml:350` and `bin/omarchy-iptv:4801`, is not
wrong about what it measured. It is a true reading of a property that does
not decide the question.

## 1. What was measured, and against what

| | |
|---|---|
| Source | the owner's own installed source, `~/.cache/omarchy-iptv/sources/d5977d8a/channels.json`, 1,453 channels, `sourceHost` `iptv-org.github.io`. Read from the frozen copy in the acceptance scratch; the live cache was never written |
| Sample | 34 channels, **27 of the list's 28 groups**, **34 distinct URL hosts**, chosen by `select_channels.py` -- deterministic, round-robin over groups by size, at most one channel per host and at most two rounds per group |
| Player | mpv v0.41.0, the plugin's own base argv copied from `mpv_launch_argv()` at dev tip 64fa114, first channel delivered over IPC by `loadfile` exactly as the service does it |
| Credentials | none. This playlist is the public iptv-org US list. URLs are still printed scheme-and-host only (requirement 5) |
| Harness | `scripts/dev-harness/spikes/live-rewind/` |

Deviations from shipping, both deliberate:

- The 34-channel sweep ran `--vo=null --ao=null`. Thirty-four windows in
  sequence would have taken the owner's display for the length of the pass,
  and neither output touches the demuxer cache. **This was then checked**: a
  second run of three of the same channels with the real video output
  reached the same verdict on all three, and produced the decoded frames in
  section 5.
- The sweep adds no mpv options the plugin does not already pass. The
  buffer experiments in section 4 add `--demuxer-max-back-bytes`,
  `--demuxer-max-bytes`, `--cache-on-disk` and `--demuxer-cache-dir`, which
  is what they are for.

Nothing of the owner's was written. No `omarchy` command was run and the
installed helper was never imported. The live plugin's socket directory was
listed once, at the end, to show it still held only its own
September files; this spike's sockets lived in a directory of their own.
No mpv was killed by name, and `pgrep -x mpv` reported none left at the end
while `pgrep -x quickshell` still named the owner's shell, pid unchanged.

One thing in the owner's cache did change during the pass and it was not
this lane: `epg-now.json` and `epg-status.json` were rewritten at 08:06 by
the owner's own running service on its refresh interval. `channels.json` was
not touched, and this pass read its frozen copy rather than that file.

## 2. The properties say no. All of them.

| reading | count |
|---|---|
| channels sampled | 34 |
| played | **32** |
| failed to play (stream faults, not seek faults) | 2 |
| `seekable` true | **0 of 32** |
| `partially-seekable` true | **0 of 32** |
| `demuxer-cache-state.seekable-ranges` non-empty | **32 of 32** |

`partially-seekable` is the property D2 asked for, on the reasoning that it
"is the property that actually decides whether a back-buffer seek works".
It is not. It read `False` on every channel that played, including every
channel that then rewound. Reading it instead of `seekable` would have
produced the same wrong answer with more confidence behind it.

The property that tracks the truth is **`demuxer-cache-state.seekable-ranges`**,
and the fact that settles it is the seek itself.

## 3. The seek

Each channel: play, let the buffer fill for 35 s, read `time-pos`, issue
`seek -20 relative`, read `time-pos` 2 s later, read it again 3 s after
that. A rewind is recorded only when the position moved back by at least
1 s **and** then advanced by at least 0.5 s. A forward jump is never a
rewind however large it is.

| outcome | count |
|---|---|
| rewound 20 s and kept playing | **31 of 32** |
| refused | 1 of 32 |
| moved back but stalled | 0 |
| player lost | 0 |

Achieved movement on the 31: **18.0 s to 19.9 s** against a requested 20 s.

The single refusal, 30A Georgia Hollywood Review, was a stream underrunning
at that instant -- `demuxer-cache-duration` 0.725 s, no back buffer to
speak of. A second, deliberately over-long seek on the same player
**did** rewind it, by 3.0 s. So 32 of 32 playable channels rewound by some
amount; 31 of 32 rewound by the full 20 s.

The two that never played are ordinary dead channels, and the player said
so: BBC Kids, `Failed to open <host>/playlist.m3u8`; ABC News Live 1,
`No video or audio streams selected`. Neither is evidence about seeking.

### Per channel

| # | channel | group | host | `seekable` | `partially-seekable` | back buffer at 35 s | -20 s seek | moved | steady rate | default window |
|---:|---|---|---|---|---|---:|---|---:|---:|---:|
| 1 | ABC KAAL (1080p) | General | https://amg01942-amg01942c6-stirr-us-10178.playouts.now.amagi.tv | `False` | `False` | 36.2 s | **rewound** | 19.8 s | 5.44 Mbps | 291 s |
| 2 | 30A Georgia Hollywood Review (720p) | Entertainment | https://30a-tv.com | `False` | `False` | n/a | **refused** | -2.0 s | 1.56 Mbps | 1072 s |
| 3 | 3ABN English | Religious | https://3abn.bozztv.com | `False` | `False` | 36.2 s | **rewound** | 18.9 s | 2.65 Mbps | 624 s |
| 4 | BHTV10 (720p) | Undefined | https://cdn3.wowza.com | `False` | `False` | 36.4 s | **rewound** | 19.3 s | 3.76 Mbps | 413 s |
| 5 | 00s Replay | Movies | https://jmp2.uk | `False` | `False` | 36.2 s | **rewound** | 18.8 s | 2.59 Mbps | 634 s |
| 6 | 48 Hours (1080p) | Series | https://dai.google.com | `False` | `False` | 36.1 s | **rewound** | 19.7 s | 6.08 Mbps | 258 s |
| 7 | ACTV (United States) | Legislative | https://castus-vod-dev.s3.amazonaws.com | `False` | `False` | 36.2 s | **rewound** | 18.2 s | 2.08 Mbps | 782 s |
| 8 | ABC News Live 1 (720p) | News | https://abcnews-streams.akamaized.net | - | - | - | **did not play** | - | - | - |
| 9 | ACC Digital Network (1080p) | Sports | https://raycom-accdn-firetv.amagi.tv | `False` | `False` | 36.0 s | **rewound** | 19.7 s | 6.15 Mbps | 255 s |
| 10 | ACE Country Radio KPVM-LD | Music | https://2-fss-1.streamhoster.com | `False` | `False` | 36.4 s | **rewound** | 18.0 s | 1.51 Mbps | 1105 s |
| 11 | BBC Kids (720p) | Kids | https://dmr1h4skdal9h.cloudfront.net | - | - | - | **did not play** | - | - | - |
| 12 | BATV Educational Channel | Education | https://livestream.telvue.com | `False` | `False` | 36.1 s | **rewound** | 19.7 s | 2.30 Mbps | 713 s |
| 13 | AFV (720p) | Comedy | https://linear-12.frequency.stream | `False` | `False` | 35.8 s | **rewound** | 18.5 s | 2.53 Mbps | 650 s |
| 14 | Atlas (480p) | Documentary | https://cdn.whiplash.cc | `False` | `False` | 36.4 s | **rewound** | 18.0 s | 2.36 Mbps | 690 s |
| 15 | ARTFLIX Movie Classics (720p) | Classic | https://amogonetworx-artflix-1-nl.samsung.wurl.tv | `False` | `False` | 36.1 s | **rewound** | 18.6 s | 3.21 Mbps | 511 s |
| 16 | AMP 2 (720p) | Culture | https://dlttx48mxf9m3.cloudfront.net | `False` | `False` | 36.5 s | **rewound** | 18.0 s | 4.07 Mbps | 397 s |
| 17 | Antiques Road Trip (1080p) | Lifestyle | https://amg02333-pbs-amg02333c1-samsung-au-1253.playouts.now.amagi.tv | `False` | `False` | 36.0 s | **rewound** | 19.8 s | 5.06 Mbps | 322 s |
| 18 | Animation+ (1080p) [Geo-blocked] | Animation | https://pb-ioe9d0fpkd6pp.akamaized.net | `False` | `False` | 35.5 s | **rewound** | 18.3 s | 4.91 Mbps | 329 s |
| 19 | AKC TV (1080p) | Outdoor | https://broadcast.blivenyc.com | `False` | `False` | 7.0 s | **rewound** | 4.7 s | n/a | n/a |
| 20 | Ameritrade (1080p) [Not 24/7] | Business | https://tdameritrade-vizio.amagi.tv | `False` | `False` | 35.9 s | **rewound** | 19.6 s | 5.14 Mbps | 308 s |
| 21 | Gem Shopping Network (720p) | Shop | https://amg01460-gemshoppingnetw-gem-ono-x662c.amagi.tv | `False` | `False` | 36.1 s | **rewound** | 18.8 s | 4.37 Mbps | 378 s |
| 22 | BBC Food (1080p) | Cooking | https://d1e9r0b71zfwk7.cloudfront.net | `False` | `False` | 36.1 s | **rewound** | 19.0 s | 5.56 Mbps | 284 s |
| 23 | Beach TV Florida & Alabama (720p) | Travel | http://media4.tripsmarter.com:1935 | `False` | `False` | 36.3 s | **rewound** | 19.0 s | 4.08 Mbps | 398 s |
| 24 | Choppertown (720p) | Auto | https://linear-11.frequency.stream | `False` | `False` | 34.8 s | **rewound** | 18.6 s | 3.85 Mbps | 417 s |
| 25 | AMG TV (1080p) | Family | https://2-fss-2.streamhoster.com | `False` | `False` | 36.2 s | **rewound** | 19.8 s | 4.69 Mbps | 346 s |
| 26 | AccuWeather NOW (1080p) | Weather | https://cdn-ue1-prod.tsv2.amagi.tv | `False` | `False` | 35.9 s | **rewound** | 19.6 s | 5.04 Mbps | 315 s |
| 27 | Better Life Nature Channel (480p) | Relax | https://tgn.bozztv.com | `False` | `False` | 35.9 s | **rewound** | 18.6 s | 1.52 Mbps | 1088 s |
| 28 | ABC KERO-TV (720p) | General | https://aegis-cloudfront-1.tubi.video | `False` | `False` | 35.9 s | **rewound** | 19.7 s | 4.03 Mbps | 411 s |
| 29 | A&E (720p) | Entertainment | http://23.239.31.26:8989 | `False` | `False` | 25.2 s | **rewound** | 18.2 s | 10.27 Mbps | 157 s |
| 30 | ABHP TV (480p) | Religious | https://vietprocast.app | `False` | `False` | 34.3 s | **rewound** | 19.8 s | 2.42 Mbps | 681 s |
| 31 | BYU TV (1080p) | Undefined | https://d13j8jpstr8iqz.cloudfront.net | `False` | `False` | 36.2 s | **rewound** | 19.9 s | 5.20 Mbps | 299 s |
| 32 | 24 Hour Free Movies (720p) | Movies | https://d1j2u714xk898n.cloudfront.net | `False` | `False` | 95300.0 s | **rewound** | 18.0 s | 3.04 Mbps | 528 s |
| 33 | All Weddings WE tv | Series | https://amc-allweddings-1-us.xumo.wurl.tv | `False` | `False` | 36.0 s | **rewound** | 18.5 s | 5.14 Mbps | 314 s |
| 34 | ATL 26 | Legislative | https://securestream11.champds.com | `False` | `False` | 36.1 s | **rewound** | 19.6 s | 1.79 Mbps | 916 s |

"Back buffer at 35 s" is `reader-pts` minus the start of the seekable range
the reader sits in -- the history behind the play head, not the width of the
range, which also covers the forward cache and is the wider and more
flattering number. "Default window" is section 4's model applied to that
channel's own measured byte rate; it is an estimate, and section 4 says how
far it can be trusted.

One channel is an outlier worth naming rather than averaging away: 24 Hour
Free Movies reported a back buffer of **95,300 s**. That entry is not a live
stream at all but a long VOD playlist served from the same list, and it is
rewindable end to end.

## 4. The window: how far back, and what it costs

### 4.1 The default is not 50 MiB

`--demuxer-max-back-bytes` defaults to 50 MiB, and the obvious arithmetic is
50 MiB over the bitrate. That arithmetic is wrong by four times, because
`--demuxer-donate-buffer` defaults to `yes` and lets the back buffer take
the forward buffer's quota as well.

Measured directly. ABC KAAL (1080p), 520 s of playback on mpv's defaults,
`demuxer-cache-state` sampled every 20 s:

| t (s) | back buffer (s) | cache total (MiB) |
|---:|---:|---:|
| 20 | 21.1 | 19.2 |
| 100 | 101.1 | 64.1 |
| 200 | 201.2 | 116.0 |
| 300 | 301.2 | 169.4 |
| 340 | 341.1 | 189.1 |
| **360** | **357.1** | **199.8** |
| 400 | 357.0 | 199.2 |
| 460 | 353.1 | 199.7 |
| 520 | 355.1 | 200.0 |

The back buffer grows one second per second until the cache total reaches
**exactly 200.0 MiB** -- `--demuxer-max-back-bytes` 50 MiB plus
`--demuxer-max-bytes` 150 MiB -- and then holds. The plateau is
**353 s to 359 s**: on this channel, on defaults, **you can rewind just
under six minutes.** A `seek -120 relative` at that point moved the position
back **118.8 s** and playback continued.

### 4.2 The model, and its calibration

window_seconds = (max_back_bytes + max_bytes) / byte_rate - forward_cache_seconds

Byte rate taken as the slope of `total-bytes` over time, not from
`raw-input-rate`, which is instantaneous and reads high during the opening
burst fill -- on this same channel it read 508,897 B/s where the slope says
556,600 B/s.

mpv's own manual describes this rule and the measurement matches it: the
back buffer "may use up memory up to the sum of the forward and back buffer
options, minus the active size of the forward buffer", and "free backward
buffer is never donated to the forward buffer".

- **Predicted 358 s, measured plateau 359.1 s. Error -0.3 per cent.**
- Second point, an order of magnitude down: with 8 MiB back and 16 MiB
  forward the same channel plateaued at a cache total of 23.0-24.0 MiB and a
  back buffer of 27-31 s, median 29 s, against a predicted 30 s.

Two plateaus an eight-fold apart, both inside a second of the model. The
per-channel "default window" column is that model, and across the 31
channels with usable byte samples:

| | seconds |
|---|---:|
| minimum | 157 |
| 25th percentile | 314 |
| **median** | **411** |
| 75th percentile | 681 |
| maximum | 1,105 |

All 31 are at or above 120 s. 25 of 31 are at or above 300 s.

### 4.3 An over-long seek is refused, not clamped

This is the sharp edge and a UI has to know it. When the target of a
backwards seek lies before the cached range:

- while the **start of the stream is still cached**, mpv clamps to it. On
  the 35 s sweep a `seek -100000 relative` landed at about 2.0 s, i.e. the
  beginning of the session, on every channel that had one.
- once the start has been **evicted**, the same seek is **refused outright**.
  Measured twice: the 8/16 MiB run (29 s of buffer, `seek -60` -> position
  moved *forward* 2.0 s) and the 520 s default run (`seek -100000` ->
  forward 2.0 s). Playback simply carried on at the live edge.

So mpv will not clamp a rewind to what it has. Anything built on this has to
read the window and clamp to it, and has to be able to say "that is as far
back as I have".

### 4.4 The bill is memory, and it can be moved to disk

On defaults the window costs up to **200 MiB of resident memory per
player**, on a box with 7.6 GiB total. That is the real objection, and it is
the one `docs/PLAN-M4.md` reached for: "a disk buffer is not available:
`$XDG_RUNTIME_DIR` here is a 782 MiB tmpfs in RAM".

The premise is wrong. mpv's disk cache does not live in `$XDG_RUNTIME_DIR`;
it lives wherever `--demuxer-cache-dir` points, and engineering rule 6
already gives this plugin a directory on real storage,
`~/.cache/omarchy-iptv/`.

Measured, same channel, `--demuxer-max-back-bytes=1GiB --cache-on-disk=yes
--demuxer-cache-dir=<btrfs path>`, 240 s:

| t (s) | back buffer (s) | cache in memory (MiB) | process RSS (MiB) |
|---:|---:|---:|---:|
| 30 | 31.1 | 1.0 | 166.3 |
| 120 | 121.0 | 2.8 | 169.0 |
| 240 | 241.0 | 5.2 | 171.4 |

Four minutes of history for **5.1 MiB of RSS growth**, against the 200 MiB
the in-memory configuration charges for six. A `seek -120 relative` moved
back 118.6 s; a further over-long seek moved back 123.0 s more.

Where the bytes went, verified rather than assumed, because
`du` on the cache directory reports zero: mpv creates
`mpv-cache-<hex>.dat` there and **unlinks it immediately**. Read through
`/proc/<pid>/fd` at 90 s of playback the open-but-deleted file held
**53,030,741 bytes** across 103,576 blocks, and `/var/tmp` usage had grown
**33,152 KiB**. The file disappears when the process does. It is invisible
to `ls` and it is still a real write to the user's disk, every second, for
as long as a channel plays -- which is a product decision, not a technical
one.

## 5. The picture, not the number

A position that moves is not a picture that continues. Three of the sampled
channels were replayed with the real video output and screenshotted through
mpv's own `screenshot-to-file video`: once at the live edge, once two
seconds after a `seek -20 relative`, once five seconds after that.

All three rewound (18.7 s, 18.8 s, 19.0 s). Nine frames came back, all
decoded video. On 00s Replay the three frames are three different moments of
the same film -- the post-seek frame is a point in the shot the live-edge
frame had already passed, and the third frame has moved on to the next shot.
That is playback continuing from a rewound position, not a frozen last
frame.

## 6. Findings

Five, each with an id on the day it was written (requirement 13). The board
rows are in section 9; this lane does not own `docs/STATUS.md`.

1. **F-RWD-1. Four shipping files state that live streams are not seekable,
   and the property they rest on is not the one that decides it.**
   `docs/UX.md:376`, `Model.js:4430-4432`, `Service.qml:350` and
   `bin/omarchy-iptv:4801-4803` and `:5862` all carry some form of "1 of 22
   measured" / "the streams are not seekable". Measured today: `seekable` is
   `False` on 32 of 32 channels that played **and 31 of those 32 rewound 20
   seconds anyway**. The sentences are a true reading with a false
   conclusion attached, and one of them is in a `--help` string a user
   reads. Suggested P2: they are not a crash, but they are the reason this
   feature was closed, and they would mislead the next person to look.

2. **F-RWD-2. `docs/PLAN-M4.md` refuses a disk buffer on a premise that does
   not hold.** It says "a disk buffer is not available: `$XDG_RUNTIME_DIR`
   here is a 782 MiB tmpfs in RAM". mpv's disk cache goes wherever
   `--demuxer-cache-dir` points, and engineering rule 6 already gives this
   plugin `~/.cache/omarchy-iptv/`, which is on btrfs here with 439 GiB
   free. Measured in section 4.4: 241 s of history for 5.1 MiB of RSS.
   Suggested P3: a planning document, not shipped code, but it closed an
   option that is open.

3. **F-RWD-3. mpv refuses an over-long backwards seek rather than clamping
   it, once the start of the stream has left the cache.** Measured twice
   (section 4.3). A rewind UI that asks for more than the buffer holds gets
   nothing at all -- not a partial seek, not an error the user sees, just
   playback continuing at the live edge. Anything built on this has to read
   the window and clamp itself. Suggested P2 against any future build, not
   against shipped code.

4. **F-RWD-4. The default back buffer is 200 MiB, not the 50 MiB the option
   name implies.** `--demuxer-donate-buffer` defaults to `yes` and lets the
   back buffer take `--demuxer-max-bytes` as well. Any sizing arithmetic in
   this project that starts from 50 MiB is four times low. (The M2-11 pause
   measurement is NOT affected and was checked: 315 s on a ~3.8 Mbps stream
   is 150 MiB, the forward quota, and the donation runs back-from-forward,
   not forward-from-back.) Suggested P3: documentation.

5. **F-RWD-5. mpv's on-disk cache file is unlinked the moment it is created,
   so the plugin's disk footprint would be invisible to `ls` and `du`.**
   At 90 s of playback the deleted-but-open file held 53,030,741 bytes and
   filesystem usage had grown 33,152 KiB, while the directory listed empty.
   If a disk-backed rewind is ever built, the only honest way to show the
   user what it is using is `/proc/<pid>/fd`, and the only way to reclaim it
   is to stop the player. Suggested P3 against any future build.

## 7. Verdict, and what a build would cost

**Live rewind is not dead here. It is available on 31 of 32 playable
channels -- 97 per cent of what played, 91 per cent of the 34 sampled -- for
a median of 411 seconds on settings the plugin already passes.**

The arithmetic that `docs/PLAN-M4.md` section 1 called a refusal was
arithmetic about the wrong quantity. The feature the research ranked highest
among the ones we do not have is the one we almost have by accident.

What it would cost, with the parts named:

- **Free today.** The window itself. Every measurement above was taken with
  the plugin's own argv plus `--vo=null`; no option was added to make the
  seek work.
- **Small.** A `seek -N relative` IPC verb beside the `pause` verb M2-11
  already shipped, the same socket, the same request-id discipline. Two
  keys, a footer hint, an accessible name per R7.
- **Small, and mandatory.** Reading the window and clamping to it
  (F-RWD-3), plus telling the user where the floor is. A rewind that
  silently does nothing at the edge of the buffer is worse than no rewind.
- **A decision, not engineering.** Whether to raise
  `--demuxer-max-back-bytes`. Leaving it alone costs nothing and gives a
  median 411 s. Raising it in memory costs RAM linearly on a box already at
  4.8 of 7.6 GiB. Moving it to disk costs almost no RAM and writes the
  stream to the user's disk continuously -- which is the same privacy
  question `docs/PLAN-M4.md` D3 refused for recording, arriving by a
  different door and deserving the same answer from the same person.
- **Unknown.** The interaction with zapping, with pause, and with the
  10 s watchdog. See section 8.

Recommendation to the product owner: this is an M5 headline, and the
decision needed now is only D2's successor -- whether a design pass is
authorised. Nothing in this document is a build.

## 8. What this pass did not measure (no defect ids; these are open questions, not faults)

- Rewind across a channel change. The player is reused; whether the buffer
  survives a `loadfile` was not tested, and the answer decides whether a
  rewind UI has to blank itself on every zap.
- Rewind plus pause. `--demuxer-donate-buffer` lets the back buffer hold the
  forward quota, and pause needs the forward quota to grow. A viewer who
  rewinds and then pauses may get a shorter pause than M2-11's 315 s, or a
  shorter rewind. Untested, and the two features would ship together.
- The watchdog. `statusHealthy` judges "running and answering". A player
  seeking inside its cache answers; whether it ever stops answering long
  enough to trip a restart was not provoked.
- Audio-video sync and subtitle behaviour after a cache seek.
- Any provider other than this one public list. 34 hosts is wide for one
  list and says nothing about a credentialed provider's packaging.
- Whether the window holds over hours. The longest single run here was
  520 s.

## 9. Board rows for `docs/STATUS.md` (this lane does not own that file)

| id | severity | summary | state |
|---|---|---|---|
| F-RWD-1 | P2 | Four shipping files conclude "not seekable" from `seekable`, which 31 of 32 rewinding channels report `False` | open |
| F-RWD-2 | P3 | `docs/PLAN-M4.md` refuses a disk buffer on the wrong directory; `--demuxer-cache-dir` is configurable | open |
| F-RWD-3 | P2 | mpv refuses rather than clamps an over-long backwards seek; a build must clamp itself | open |
| F-RWD-4 | P3 | Default back buffer is 200 MiB, not 50 MiB, via `--demuxer-donate-buffer` | open |
| F-RWD-5 | P3 | mpv's on-disk cache file is unlinked at creation; disk use invisible to `ls` and `du` | open |

## 10. Reproducing this

```bash
cd scripts/dev-harness/spikes/live-rewind
python3 -m unittest test_verdict                 # 26 assertions over the judgements
python3 select_channels.py <channels.json> --want 34 > /tmp/sample.json
python3 sweep.py /tmp/sample.json \
    --scratch <scratch dir> --sock-dir "$XDG_RUNTIME_DIR/lrw" \
    --out /tmp/out.json --soak 35
```

`--sock-dir` must be short: AF_UNIX caps a path near 108 bytes, the
scratchpad path alone is 104, and mpv's only complaint is
`Could not create IPC socket`, which looks exactly like a dead stream.

`--windowed --screenshot-dir D` replaces `--vo=null` with the real output
and writes the three frames of section 5. `--back-bytes`, `--forward-bytes`
and repeated `--extra=--option=value` drive section 4.

Process discipline, because this spike starts dozens of players next to a
running `quickshell` the owner is using: every mpv is tracked by the pid the
harness holds and killed by that pid, SIGTERM then SIGKILL, each wait
bounded and each give-up reported. Nothing is matched by name or command
line.

`test_verdict.py` was seen red before it was kept. Baseline **Ran 26 tests
... OK**; six mutations of `verdict.py`, each one red:

| mutation of `verdict.py` | result |
|---|---|
| `property_claim` loses its `partially-seekable` branch (the M2-11 bug) | Ran 26, FAILED (failures=1) |
| `seek_verdict` takes `abs()`, so a forward jump counts as a rewind | Ran 26, FAILED (failures=1) |
| `back_window_seconds` drops the `* 8`, mistaking bytes for bits | Ran 26, FAILED (failures=1) |
| `seekable_range_span` returns 0.0 for an absent key instead of None | Ran 26, FAILED (failures=1) |
| `summarise` counts a claim for a channel that never played | Ran 26, FAILED (failures=1) |
| `back_span_seconds` returns the whole range instead of the history behind the reader | Ran 26, FAILED (failures=2) |

The judgement functions are separated from the measurement for exactly that
reason: a rule that cannot be run against a hand-written reading is a rule
nobody has checked (requirement 14). The window model in section 4.2 is held
to the same standard -- it is not asserted, it is checked against two
directly observed plateaus an eight-fold apart, and the error is reported.
