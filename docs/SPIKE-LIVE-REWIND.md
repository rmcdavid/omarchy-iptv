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

## 11. Second pass, 2026-10-03

**Design pass, the successor to D2, authorised 2026-10-03. Measurement
only; no build. The four open questions in section 8 that a design
depends on, each read as a property AND provoked as a behaviour.**

Same machine, same mpv v0.41.0, same channel for every question but one:
ABC KAAL (1080p), `https://amg01942-amg01942c6-stirr-us-10178.playouts.now.amagi.tv`,
the channel section 4.1 measured its plateau on, reading **4.72 Mbps**
(0.562 MiB/s, slope of `total-bytes`) today against 5.44 on the first pass.
BYU TV (1080p), `https://d13j8jpstr8iqz.cloudfront.net`, is the second
channel in Q1. Both are healthy rows in section 3's table, read by id from
the owner's installed cache (`channels.json` mtime 05:06, unchanged at the
end; the owner's own service rewrote `epg-now.json` at 10:11, not this
lane). Argv: the plugin's own, including `--title=$>IPTV` and the four
directory options `mpv_launch_argv()` carries at dev tip b2f944d, pointed at
this pass's scratch, plus `--vo=null --ao=null` as section 1 justified. The
zap is `apply_channel()`'s wire sequence copied in order -- `pause` off,
`aid`/`sid` auto, `title`, `force-media-title`, the three header properties,
the stash, `loadfile <url> replace`, the stash again, the owner claim --
in `design_pass.py` `zap()`. Five players, pids 2373134, 2374889, 2380538,
2383492, 2386363, each killed by that pid with SIGTERM (mpv exit status 4,
"quit by signal", all five); `pgrep -x mpv` empty at the end;
`pgrep -x quickshell` 2186866 before and after. Sockets lived in
`$XDG_RUNTIME_DIR/lrw2`, removed afterwards; the plugin's own socket
directory was listed once and held only its September files.

One correction to the brief before the numbers: the control slot's watchdog
is **8 s**, `Service.qml:79` `controlTimeoutMs: 8 * 1000`, not 10; the
12 s figure on the same file is `playerTimeoutMs`, the cold-start verb.
Every margin below is stated against 8.

### 11.1 Q1, the zap

Play A 90 s, zap to B exactly as the plugin does, trace
`demuxer-cache-state` four times a second for 31 s, seek, zap back to A.

| moment | `time-pos` | back buffer | `seekable-ranges` | cache end | total | fw | `playlist-playing-pos` / count |
|---|---:|---:|---|---:|---:|---:|---|
| A at 95.0 s, before the zap | 90.83 | **91.2 s** | `[[0.0, 105.983]]` | 107.99 | 57.0 MiB | 8.9 MiB | 0 / 1 |
| B +0.01 s (first read after the `loadfile` reply) | none | none | `[]` | none | none | none | **-1** / 1 |
| B +1.01 s | none | none | `[]` | none | none | none | 0 / 1 |
| B +2.02 s | none | none | `[]` | none | none | none | 0 / 1 |
| B +5.04 s | none | none | `[]` | none | none | none | 0 / 1 |
| B +10.07 s | 4.68 | 4.9 s | `[[0.0, 17.956]]` | 18.42 | 9.9 MiB | 7.2 MiB | 0 / 1 |
| B +20.12 s | 14.75 | 15.1 s | `[[0.0, 27.966]]` | 29.99 | 16.1 MiB | 8.1 MiB | 0 / 1 |
| B +29.93 s | 24.56 | 24.9 s | `[[0.0, 45.951]]` | 47.98 | 25.2 MiB | 11.8 MiB | 0 / 1 |
| A again +5.03 s | 0.89 | 1.1 s | `[[0.0, 1.988]]` | 3.66 | 2.2 MiB | 1.5 MiB | 0 / 1 |

| event | B | A again |
|---|---:|---:|
| `loadfile` reply round trip | 0.1 ms | 0.6 ms |
| first numeric `time-pos` after the reply | **+5.29 s** | +4.28 s |
| first non-empty `seekable-ranges` | +6.04 s | +4.78 s |
| first second of rewindable history | **+6.30 s** | +5.03 s |

| seek | before | 2 s after | 5 s after | moved | verdict |
|---|---:|---:|---:|---:|---|
| B at +30 s, `seek -20 relative` | 25.83 | 5.98 | 8.98 | **19.85 s** | rewound |
| A again at +6 s, `seek -20 relative`, ranges `[[0.0, 5.992]]` | 1.92 | 1.99 | 4.99 | -0.07 s | refused -- it landed on the stream's first keyframe at 1.99, which is where it already was |
| A again at +30 s, `seek -20 relative` | 23.98 | 4.02 | 7.03 | **19.95 s** | rewound |

A's history is gone at the first read after the `loadfile` reply, 10 ms in:
the state is EMPTY, not B's and not A's, and stays empty for the five
seconds the new demuxer takes to open. `playlist-playing-pos` reads -1 for
that first read and the count stays 1 -- `replace` is a replacement, there
is no second entry to seek into. Zapping back to A brings none of A's
91 s: at +5 s its range is `[0.0, 1.988]`. Every loadfile restarts the
demuxer timeline at 0, which is why the judgement in `verdict.py` is a
span test and not an overlap test -- the first version of it said A's
history was visible because `[0, 106]` overlaps `[0, 1.99]`, and the fix
is recorded in the test with the measured reading.

RSS across the zap: 230,132 KiB on A before, 229,960 at B +0.01 s,
302,188 at B +30 s. The old cache is released, not carried.

**Verdict for the designers: a rewind UI resets to zero on every zap, and
the back buffer after a zap is seconds since the `loadfile` reply minus
the demuxer's own start-up, 5 to 6 s here; the first second you can rewind
arrives about 6 s after the zap, and a full 20 s rewind works at +30. A
rewind pressed inside those first seconds lands on the first keyframe
(about 2.0 s) and moves nothing, so the UI must read the range before it
offers the key.**

### 11.2 Q2, pause

(a) 240 s of history then pause; (b) a fresh stream paused at 10 s as the
control; (c) rewind 60 then pause 60; (d) pause 60 then rewind 30 while
still paused. Forward growth is "stopped" when `fw-bytes` holds within
0.5 per cent for three 5 s samples.

| | (a) full back buffer | (b) fresh stream |
|---|---:|---:|
| back buffer at the pause | **241.1 s** | 10.7 s |
| cache total at the pause | 137.2 MiB | 14.2 MiB |
| forward growth stopped after | **265.1 s** | **265.1 s** |
| `fw-bytes` at the stop | **150.0 MiB** | **150.0 MiB** |
| cache total at the stop | 199.6 MiB | 156.1 MiB |
| back buffer at the stop | **93.0 s** | 10.9 s |
| `seekable-ranges` at the stop | `[[147.993, 519.964]]` | `[[0.0, 291.967]]` |
| cache end - `time-pos` at the stop | 279.2 s | 282.8 s |
| process RSS at the stop | 393,804 KiB | 335,500 KiB |
| resumed from the paused point (`time-pos` at +2 s, +5 s) | 240.785 -> 242.787 -> 245.790, **yes** | 10.520 -> 12.522 -> 15.525, **yes** |
| predicted, 150 MiB over 0.562 MiB/s | 267 s | 267 s |

The pause is the same length to the sample with a full back buffer as
with an empty one: **a full back buffer shortens the pause by 0 s**. What
pays is the history. Section 4.2 quoted the manual's rule that free
backward buffer is never donated forward; what the manual does not say is
what happens when the backward buffer is NOT free. Measured: the cache
total reached 199.7 MiB at **120 s** of pause, and from then on the floor
of the range moved one second per paused second -- `[4.016, 375.954]` at
120 s, `[87.999, 459.971]` at 200 s, `[147.993, 519.964]` at 265 s -- until
the back buffer was down to **93 s, which is 49.6 MiB at this bitrate: the
50 MiB `--demuxer-max-back-bytes` the back buffer owns outright.** The
forward buffer reclaims every byte the back buffer had borrowed, and the
rewind window a viewer had before pressing pause is 241 s on the way in
and 93 s on the way out.

| (c) and (d), same player, 120 s of history | reading |
|---|---|
| `seek -60 relative` then pause | 120.74 -> 62.01 -> 65.02, moved 58.73 s, rewound |
| `time-pos` across 60 s paused | 65.018 at 10 s, 65.018 at 60 s, **drift 0.000 s** |
| forward cache across those 60 s | 49.3 MiB -> 75.0 MiB; cache end 155.97 -> 203.99 (kept filling from the rewound point) |
| resume | 65.018 -> 67.020 -> 70.023, **continued from the paused point** |
| pause 60 s, then `seek -30 relative` WHILE PAUSED | 70.02 -> 39.99 one second later, **moved 30.03 s**, still paused (`pause` true before and after) |
| resume | 39.993 -> 42.028 -> 44.998, **continued from the rewound point** |

**Verdict for the designers: pause and rewind compose in both orders --
a rewound pause resumes where it paused, a paused rewind moves the
position while the picture is frozen and resumes there -- but a pause EATS
the history: 265 s of pause at 4.7 Mbps took the window from 241 s to
93 s, and nothing on screen would say so unless the UI reads the floor.
The pause itself is bounded by the forward quota alone, 150 MiB over the
bitrate, with or without history behind it.**

### 11.3 Q3, the watchdog and the seek itself

Fill to the plateau -- reached at 365 s: back buffer 356.9 / 361.0 /
357.0 s over the last three samples, cache total 199.3 / 200.0 / 199.5 MiB,
range `[[44.028, 418.001]]` -- then `seek -300 relative`, then
`get_property time-pos` as the very next command, then thirty 1 s ticks.

| reading | value |
|---|---:|
| `seek -300 relative` reply round trip | **0.10 ms** |
| `get_property time-pos` issued right after, round trip | **0.34 ms** |
| `time-pos` on that first read | 100.617 against 400.617 before: **exactly -300.0 s** |
| `time-pos` advanced 0.5 s past that at | **+1.12 s** after the seek |
| `paused-for-cache` across the 30 ticks | false on all 30 |
| `time-pos` per wall second over 29 intervals | **median 1.001, min 0.967, max 1.002** |
| the 8 s control watchdog against the slowest reply seen | 0.34 ms: a margin of four orders of magnitude |

The seek is not where the watchdog's risk is. Where the risk is, is the
number the UI would show.

| tick | wall s | `time-pos` | cache end | `fw-bytes` | cache end - `time-pos` | (wall - wall0) - (pos - pos0) |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1.12 | 101.15 | 419.99 | **169.1 MiB** | 318.8 | 300.60 |
| 10 | 11.12 | 111.13 | 420.01 | 163.6 MiB | 308.9 | 300.62 |
| 20 | 21.12 | 121.14 | 420.01 | 158.3 MiB | 298.9 | 300.63 |
| 29 | 30.12 | 130.11 | 420.01 | 153.7 MiB | **289.9** | 300.64 |

After a 300 s rewind every byte that was history is now ahead of the
reader: `fw-bytes` reads **169.1 MiB against a 150 MiB forward quota**,
and mpv stops fetching -- **cache end was flat for the whole 30 s, 419.99
to 420.01**, while the live edge on the provider moved 30 s on. So
`cache end - time-pos` counted DOWN, 318.8 to 289.9, one second per second,
while the viewer's real distance behind live did not change at all. A UI
built on that difference would show the gap closing when it is not.

The right-hand column is the number that holds: wall-clock time since the
first frame minus playback time since the first frame, `(wall - wall0) -
(pos - pos0)`, read **300.60 to 300.64 across all thirty ticks** -- a
300 s seek plus 0.6 s of the zero point being the first `time-pos` reading
rather than the exact instant. The same formula over Q2(a)'s pause read
280.1 at the 280 s sample against 279.2 from the cache-end difference,
which agreed there only because the forward fetch had not yet stalled. It
needs no property but `time-pos` and a clock, it is reset at the zap by
the zero point being re-taken at the first `time-pos` after the
`loadfile`, and it counts up while paused and holds while playing, which
is what "behind live" means. Its one residual is the live-edge lead the
demuxer keeps ahead of the reader before any rewind, 13.4 to 21.4 s on
this channel over the fill and jittering with segment arrival, which the
formula counts as zero -- the viewer at the live edge is already that far
behind the provider, and that is the same on every live player.

The stall has a second consequence, observed once and not sized: fetching
resumed when the reader reached the frozen edge (Q4's edge seek below,
`fw-bytes` 17.6 MiB a few seconds later, cache end 461.11), and the
segments for the stalled 50 s were still on the provider's playlist, so
playback continued without a gap. **ASSUMED, not measured: a stall longer
than the provider's playlist window leaves a hole the viewer reaches
later.** On this channel at this bitrate the fetch stalls whenever the
viewer is more than about 265 s behind, which is a condition the window
itself invites.

**Verdict for the designers: the seek and the read after it answer in
under half a millisecond against an 8 s watchdog, and playback is at
1 s/s within 1.1 s; but "seconds behind live" must be computed from the
wall clock and `time-pos`, never from the cache end, because a rewind past
the forward quota freezes the cache end and makes that difference count
down while the real gap holds.**

### 11.4 Q4, the floor, precisely

Same player, still rewound, range `[[44.028, 418.001]]` at the first row.
Absolute seeks; "landed from floor" is `time-pos` one second after the
seek minus `seekable-ranges[0].start` at the moment it was issued.

| target | before | 1 s after | 4 s after | landed from floor | reply | log line | verdict |
|---|---:|---:|---:|---:|---|---|---|
| start + 1 = 45.028 | 131.15 | 45.96 | 48.97 | +1.935 s | success | -- | **landed** |
| start = 44.028 | 48.97 | 45.03 | 48.03 | +1.001 s | success | -- | **landed** |
| start - 1 = 43.028 | 48.03 | 49.03 | 52.04 | (unmoved) | **success** | `Cannot seek in this stream.` | **refused** |
| end - 0.5 = 417.501 (inside, at the frozen edge) | 52.04 | 418.44 | 421.40 | -- | success | -- | landed; fetch resumed, range then `[[80.03, 459.977]]` |
| end + 30 = 489.977 (outside) | 421.44 | 422.44 | 425.41 | (unmoved) | **success** | `Cannot seek in this stream.` | **refused** |

`seekable-ranges[0].start` is the floor exactly: a target at it or one
second above it lands on the first keyframe at or after the target, one to
two seconds up; a target one second below it is dropped. The IPC reply for
a dropped seek is `success`, identical to a seek that worked, and the only
tells are `time-pos` not moving and an **error-level log line, `Cannot seek
in this stream. You can force it with '--force-seekable=yes'`**, written
once per refusal -- the player's log held exactly two, one per refused row
above. `player start` already subscribes to that stream with
`request_log_messages`, so a build can see the refusal rather than infer
it. (Do not take the hint in the message: `--force-seekable` is for files
whose demuxer lies about seekability, and the ranges here are honest.)

The underrun case was not provoked on its own. What was measured is its
degenerate form in Q1: with 1.1 s of history and the reader 1.92 s in,
`seek -20` landed on the first keyframe at 1.99 -- the clamp to a still
cached stream start that section 4.3 described, moving nothing. A range
only ever describes what is cached, so "inside the range but not cached"
is not a state the property can be in; what happens instead is that the
range is a second wide. ASSUMED: a target inside a tiny range behaves as
these rows do -- it lands on the nearest keyframe at or after it.

**Verdict for the designers: clamp every backwards target to
`seekable-ranges[0].start`, expect to land one to two seconds above it,
treat a reply of `success` as no evidence at all, and read the refusal from
`time-pos` or from the error-level log line the player already streams to
the helper.**

### 11.5 What this adds to the findings (no new defect ids; these refine F-RWD-3 and section 8)

- F-RWD-3 is sharper than section 4.3 stated: the refusal is silent on the
  IPC reply but not in the log, and it applies in both directions.
- Section 8's first three questions are closed above. Audio-video sync,
  subtitles, other providers and multi-hour runs remain open.
- One new fact nothing in sections 1-10 anticipated: **pause reclaims the
  rewind window** down to the 50 MiB the back buffer owns, and **a deep
  rewind freezes the live-edge fetch** until the viewer has played the
  forward quota back down. A design that ships rewind beside M2-11's pause
  has to show the floor moving during a pause and must not derive "behind
  live" from the cache end.

### 11.6 Reproducing this

```bash
cd scripts/dev-harness/spikes/live-rewind
python3 -m unittest test_verdict          # 51 assertions, 26 from the first pass
python3 design_pass.py q1   --channels <channels.json> --a 't:ABC.us@KAAL' --b 't:BYUTV.us@SD' \
    --scratch <scratch> --sock-dir "$XDG_RUNTIME_DIR/lrw2" --out <scratch>/q1.json
python3 design_pass.py q2a  ... --a 't:ABC.us@KAAL' --q2-cap 300
python3 design_pass.py q2b  ... --a 't:ABC.us@KAAL' --q2-cap 420
python3 design_pass.py q2cd ... --a 't:ABC.us@KAAL'
python3 design_pass.py q34  ... --a 't:ABC.us@KAAL' --q3-cap 430
```

Q1 and Q2a ran concurrently on separate players, then Q2b and Q2cd; Q34,
the one whose numbers are round-trip timings, ran alone. Wall time 167,
529, 300, 263 and 456 s. Each run was wrapped in `timeout -k 5 <bound>`
and the script traps SIGTERM into the `finally` that reaps mpv by pid, so
a bound that fires still leaves no player behind.

The seven judgements added to `verdict.py` were each seen red. Baseline
**Ran 51 tests ... OK**; eight mutations, each one red:

| mutation of `verdict.py` | result |
|---|---|
| `history_survives` goes back to an overlap test (the false positive this pass made first) | Ran 51, FAILED (failures=1) |
| `resumed_from` stops checking that playback moved on | Ran 51, FAILED (failures=1) |
| `floor_seek_verdict` checks landed before clamped | Ran 51, FAILED (failures=1) |
| `floor_seek_verdict` calls refused only on a strict < 1 s move, which the 1 s read gap defeats | Ran 50, OK until the measured `start-1` reading was added as a test; then Ran 51, FAILED (failures=1) |
| `at_plateau` drops the cap check, so an underrun reads as a plateau | Ran 51, FAILED (failures=1) |
| `tick_rate` invents a rate across a missing reading | Ran 51, FAILED (failures=1) |
| `trend` flips its sign | Ran 51, FAILED (failures=1) |
| `behind_live_seconds` returns pos minus end | Ran 51, FAILED (failures=1) |

The fourth row is the point of the rule: a mutation survived the tests
written from the function's description and died only when a reading the
player had actually produced was pasted in.

## 12. Pre-build measurements, 2026-10-03

**The measurements `docs/M5-01-LIVE-REWIND.md` section 10 says a build
takes before its first commit. Measurement only; no build.** The five in
the brief for this phase: the `demuxer-cache-state` field set (M1), the
refusal detector's threshold (M2), `show-text` on a real window (M3), the
zero-point error (M4) and the harness's reachability (M5). The two that
need the helper verb to exist -- spawn-to-reply of `player seek`, and the
zero-point node across a shell restart -- wait for the helper lane.

Same machine, same mpv v0.41.0, Hyprland 0.56.2, four cores, load average
1.6 at the start. Channels read by id from the owner's installed cache
(`channels.json` mtime 05:06, not written by this lane): ABC KAAL (1080p)
`https://amg01942-amg01942c6-stirr-us-10178.playouts.now.amagi.tv`, A&E
(720p) `http://23.239.31.26:8989`, ACC Digital Network (1080p)
`https://raycom-accdn-firetv.amagi.tv`, BBC Food (1080p)
`https://d1e9r0b71zfwk7.cloudfront.net`, BYU TV (1080p)
`https://d13j8jpstr8iqz.cloudfront.net`, ACE Country Radio KPVM-LD
`https://2-fss-1.streamhoster.com` -- all healthy rows in section 3's
table. Argv: the plugin's own as section 11 built it, plus `--vo=null
--ao=null` for every player but M3's, which ran the real video output with
`--mute=yes` as its one deviation (the plugin passes no audio option and
the owner's speakers are not part of the measurement). Eleven players,
pids 2441822, 2442046, 2442047, 2442048, 2447201, 2447664, 2449063,
2450279, 2451244, 2453976, 2453977, each killed by that pid (mpv exit
status 4 on all eleven); `pgrep -x mpv` empty at the end; `pgrep -x
quickshell` 2186866 before and after. Sockets in `$XDG_RUNTIME_DIR/lrw3`,
empty at the end. M2's three players ran concurrently (load average 2.6);
M3 and M4 overlapped the last two minutes of M1's fill, and the fourth M4
channel overlapped the short M1 run, two players at a time, which is what
section 11 also did. Everything below is `design_pass.py m1`..`m4` with the
judgements in `verdict.py`.

### 12.1 M1, every field of `demuxer-cache-state`

Read on five channels -- ABC KAAL at +30 s and at its plateau (365 s,
`[[6.015, 375.984]]`, 199.0 MiB, byte-rate slope 4.45 Mbps), the three M2
channels at +30 s and at their eviction or cap, BYU TV at +30 s and +41 s
-- and walked by `verdict.enumerate_fields`, which takes a list through its
first element. Sixteen top-level keys, **20 leaves, the same 20 paths with
the same types on every channel at every moment**. Samples are ABC KAAL's.

| path | type | +30 s | plateau | forwarded |
|---|---|---:|---:|---|
| `bof-cached` | bool | `True` | `False` | yes |
| `cache-duration` | float | 16.747 | 16.725 | yes |
| `cache-end` | float | 47.979 | 377.984 | yes |
| `debug-byte-level-seeks` | int | 0 | 0 | no |
| `debug-low-level-seeks` | int | 0 | 0 | no |
| `debug-ts-last` | float | 43542.525 | 43872.554 | no |
| `eof` | bool | `False` | `False` | yes |
| `eof-cached` | bool | `False` | `False` | yes |
| `fw-bytes` | int | 9295312 | 9505744 | yes |
| `idle` | bool | `False` | `False` | yes |
| `raw-input-rate` | int | 1544205 | 1383913 | no |
| `reader-pts` | float | 31.232 | 361.259 | yes |
| `seekable-ranges[].end` | float | 45.988 | 375.984 | yes |
| `seekable-ranges[].start` | float | 0.0 | 6.015 | yes |
| `total-bytes` | int | 27019824 | 208700576 | yes |
| `ts-per-stream[].cache-duration` | float | 16.817 | 16.783 | no |
| `ts-per-stream[].cache-end` | float | 43559.475 | 43889.471 | no |
| `ts-per-stream[].reader-pts` | float | 43542.658 | 43872.688 | no |
| `ts-per-stream[].type` | **str** | `video` | `video` | no |
| `underrun` | bool | `False` | `False` | yes |

**Exactly one leaf is a string: `ts-per-stream[].type`.** The raw replies
kept for BYU TV hold two entries in that list, `video` and `audio` -- mpv's
own stream-type names, one per stream -- and no top-level value is a string
on any of the ten readings. Nothing in the reply is a path, a URL or a
title. The `ts-per-stream[]` timestamps and `debug-ts-last` are PTS in the
stream's own timebase (43,000-odd seconds here), which is why they are not
forwarded: they are not positions on the timeline the helper reports.

**Verdict: the helper forwards these twelve paths and drops the other
eight -- `seekable-ranges[].start`, `seekable-ranges[].end`, `cache-end`,
`reader-pts`, `cache-duration`, `fw-bytes`, `total-bytes`, `underrun`,
`idle`, `eof`, `eof-cached`, `bof-cached` -- and the one string in the
reply never enters it.**

### 12.2 M2, the refusal detector

Three channels, each filled until `seekable-ranges[0].start` left zero
(the stream start evicted, which is the plateau) or 330 s passed, then 36
ABSOLUTE seeks apiece, the mode the design chose: 24 meant to land --
deltas from the current position, clamped inside `[floor + 2, end - 0.5]`
the way the helper will clamp -- then six below the floor and six past the
end. For each seek, `time-pos` before, immediately after the reply, and
1 s later; and the `log-message` events the player sends after
`request_log_messages error`, which is how `player start` already listens.

| | A&E (720p) | ACC Digital Network (1080p) | BBC Food (1080p) |
|---|---:|---:|---:|
| byte-rate slope | 5.80 Mbps | 5.68 Mbps | 4.69 Mbps |
| stream start evicted at | 292 s | 283 s | not within 335 s (192.2 MiB); evicted during the battery |
| range at the fill's end | `[[4.185, 258.005]]` | `[[5.975, 297.967]]` | `[[0.067, 345.187]]` |
| landed seeks | 24 | 24 | 24 |
| immediate read == target, to the millisecond | **24 of 24** | **24 of 24** | **24 of 24** |
| landed abs(after - before) min / median / max | 2.000 / 10.000 / 120.000 | 2.000 / 10.000 / 120.000 | 2.000 / 10.000 / 120.000 |
| landed, read 1 s later minus the immediate read | 0.52 / 1.03 / **5.09** | 0.86 / 0.93 / 0.99 | 0.90 / 0.96 / 1.02 |
| seek reply round trip, median / max | 0.10 / 0.72 ms | 0.11 / 0.16 ms | 0.11 / 0.23 ms |
| immediate read in hand after, median / max | 1.2 / 3.2 ms | 0.6 / 8.5 ms | 0.6 / 23.3 ms |
| log lines on landed seeks | 0 | 0 | 0 |
| refused seeks (target >= 0) | 10 | 11 | 10 |
| immediate read == before, exactly | 10 of 10 | 10 of 11 | 2 of 10 |
| refused abs(after - before) max | **0.000** | **0.033** | **0.033** |
| refused abs(later - before) min / median / max | 0.00 / 1.00 / 1.20 | 1.00 / 1.00 / 1.00 | 0.97 / 1.00 / 1.00 |
| `Cannot seek in this stream` on refused | **10 of 10** | **11 of 11** | **10 of 10** |
| that line parsed by the time of the immediate read | 0 of 10 | 10 of 11 | 9 of 10 |
| refused seeks whose 1 s read had not advanced 0.5 s | **3** | 0 | 0 |
| lines in the player's own log file | 10 | 11 | 10 |

Over all three: **72 landed seeks, 72 immediate reads equal to the target;
31 refused seeks, 31 immediate reads within 0.033 s of the previous
position, 31 log lines, 0 log lines on a landed seek.** The 0.033 is one
frame at 29.97 fps: the position advanced a frame between the two reads.

| not-moved threshold | above the refused max (0.033) | below the smallest landed (2.000) | separates |
|---:|---:|---:|---|
| 0.10 s | 0.067 | 1.900 | yes |
| 0.25 s | 0.217 | 1.750 | yes |
| **0.50 s** | **0.467** | **1.500** | yes |
| 1.00 s | 0.967 | 1.000 | yes |

The smallest landed move is the smallest REQUEST in the battery, 2 s. The
helper's clamp can ask for less -- at floor + 2.3 a `--by -10` clamps to a
0.3 s move -- so the threshold is not a property of mpv alone: **when the
clamped target is within the threshold of the current position, the helper
reports `atFloor` (or `atEdge`) without issuing the seek**, and the seeks it
does issue are at least a threshold long.

Five rows are not in the refused count because they measured something
else. A target below the floor by more than the floor is NEGATIVE, and mpv
reads a negative absolute target as an offset from the END: `-6.462` on
A&E landed at 291.07 with the cache end at 297.41, `-18.022` on ACC at
317.96 against 333.97, `-34.908` on BBC Food at 349.53 against 383.42 --
all five moved, none logged a line.

Findings, each with its id on the day (rule 13):

1. **F-RWD-7. A negative absolute seek target is an offset from the cache
   end, not a refusal.** Five of five such targets moved the viewer to
   within 0.1-2.0 s of `end + target`. The helper's clamp to `floor + 2`
   makes the target non-negative whenever a range exists; when
   `seekable-ranges` is empty the helper must refuse without seeking, never
   compute `position + by` and send it. Suggested P2 against the build: a
   rewind that jumps to the live edge is the opposite of what was pressed.
2. **F-RWD-8. The immediate `time-pos` read is the target echoed, not the
   decoded position; on A&E the decoded landing was up to 5.1 s past it.**
   The read 1 s after a landed seek sat 0.52-5.09 s past the immediate read
   on A&E (720p) against 0.86-1.02 s on the two 1080p channels, so section
   11's "absolute seeks are exact" holds on two of three channels and on
   the third the seek lands on the next keyframe up to four seconds on.
   `applied` in the reply is therefore the request, and the 10 s status
   re-sync is what carries the decoded truth. Suggested P3: a readout
   wobble of a few seconds on some channels, corrected within a tick.
3. **F-RWD-9. The read 1 s later is not a refusal tell, and the log line
   can arrive after the immediate read.** Three of A&E's ten refusals were
   followed by a `time-pos` that did not advance in the next second: the
   stream was underrunning at the live edge (`paused-for-cache`), which a
   detector keyed on "did it advance" would read as a stalled seek. And on
   A&E the refusal line reached the socket after the `time-pos` reply on 10
   of 10 refusals (it was parsed on the next read, up to 1 s later), on the
   other two channels before it on 19 of 21. The detector is the immediate
   read; the log line confirms when the helper drains, and the helper never
   waits for it. Suggested P2 against the build.

**Verdict: the not-moved threshold is 0.5 s on the immediate `time-pos`
read, 0.467 s above the largest refused movement and 1.5 s below the
smallest request; the helper reports `atFloor` before issuing a seek
shorter than that, treats the 1 s read as no evidence, and reads the log
line only as confirmation.**

### 12.3 M3, `show-text` on a real window

ABC KAAL, the plugin's argv with the real video output, tiled by the
compositor at 650x718 beside this session's own window; `osd-level` read
1, mpv's default. The top 70 px of the window (its letterbox band, black
until the OSD draws) captured back to back after each command; the time is
when the capture command RETURNED, an upper bound on the capture instant.
Three runs; the first used the legacy dispatcher spelling and is the
reason the fullscreen leg says what it says.

| | reading |
|---|---|
| `show-text "-1:32 behind live" 3000`, windowed, run 2 | absent at 35 ms, **present at 64 ms**, 85, 100, 134, 164 |
| the same, run 3 | absent at 30, 48, 66 ms, **present at 97 ms**, 118, 133 |
| `hyprctl dispatch fullscreen 0` | `error: ')' expected near '0'` -- a Lua syntax error on this build, exactly Model.js gate G-1; the window stayed 650x718 |
| `hyprctl dispatch 'hl.dsp.window.fullscreen({ window = "address:0x5e594ef65de0" })'` | `ok`; `fullscreen` 2, `fullscreenClient` 2, size 1366x768; held 2.01 s; the same call restored it to 650x718, `fullscreen` 0 |
| `show-text`, fullscreen, output's top 70 px | absent at 88 ms, **present at 168 ms**, 266, 346 |
| `hyprctl layers` while fullscreen | `omarchy-bar` still listed, level 2, 0,0 1366x26 -- mapped |
| the output's top 26 px while fullscreen | video: RMSE 0.10 against the 44 rows below it, 0.20 against the bar band captured windowed (bar band against its own rows below: 0.20) |
| IPC `seek -5 relative`, windowed, no text active, 7.51 -> 2.31 | **no OSD bar, no OSD text of mpv's own** at 117, 210, 315 ms (run 3; 118, 210, 312 ms in run 2) |
| the 3000 ms line, run 3 | still drawn at +3.76 s, gone at +3.85 s; one observation |
| focus and layers after | active window restored by address; `omarchy-bar` listed as before |

**Verdict: the numbers-only line is visible at the default `osd-level`
within about 100 ms windowed and 170 ms fullscreen; a fullscreen player
covers the bar, which stays mapped but is not drawn over the client, so
with the guide closed the line is the only feedback a fullscreen viewer
gets; and an IPC seek draws nothing of mpv's own, so D9's line is not
doubled.** A build that drives the compositor uses the Lua forms
`pipExpression()` already builds; the legacy spelling is a no-op with an
error nobody sees.

### 12.4 M4, the zero-point error

One player, zapping exactly as the plugin does; `time-pos` polled every
50 ms after the `loadfile` reply, `(wall0, pos0)` at the first numeric
value, then one read per second for 60 s. The error is
`(wall - wall0) - (pos - pos0)`, what "behind live" would show on a player
nobody rewound.

| channel | bitrate | first `time-pos` after the reply | `pos0` | error at +60 s | min / max over 60 ticks | from a zero point at tick 5 | `paused-for-cache` ticks | cache end - pos at +60 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ACE Country Radio KPVM-LD | 1.02 Mbps | +1.51 s | 0.095 | **+0.008** | -0.004 / 0.038 | -0.020 | 0 | 8.0 s |
| ABC KAAL (1080p) | 3.98 Mbps | +5.04 s | 0.050 | **+0.007** | -0.024 / 0.021 | +0.012 | 0 | 11.9 s |
| ACC Digital Network (1080p) | 6.14 Mbps | +3.32 s | 0.000 | **-0.031** | -0.041 / 0.000 | -0.022 | 0 | 18.0 s |
| A&E (720p) | 9.66 Mbps | +5.95 s | 0.067 | **+12.903** | 0.300 / 12.903 | +11.123 | **14 of 60** | 0.9 s |

On the three channels that played cleanly the error at a minute is
0.007-0.031 s and never left +/-0.041 s across 180 ticks: section 11.3's
0.60-0.64 was the read gap of a 0.5 s poll, not the zero point. The
fourth channel is a different measurement. A&E ran 0.7-0.9 s ahead of its
cache end the whole minute, underran on 14 of 60 ticks, and the formula
counted every stall: 1.78 s by +5 s, 12.9 s by +60 s. That is a true
distance -- the viewer IS that far behind the edge -- but it grows while
playing, which section 2.3's "holds while playing" does not anticipate.

4. **F-RWD-10. On an underrunning stream "behind live" grows while
   playing, with no rewind pressed.** 12.9 s in a minute on A&E, 14 of 60
   ticks `paused-for-cache`. The number is honest and the 10 s status
   re-sync will show it; what the design has not decided is whether a
   stall-driven count-up is displayed, hinted (`g live` would re-seek to an
   edge the fetch cannot reach) or held back below some bound. Suggested
   P3, a decision rather than a defect, and the one channel in the sample
   that behaves so was also the one with 0.7 MiB of forward cache.

**Verdict: the zero-point error is below 0.05 s on clean streams, so
`BEHIND_LIVE_SHOW_S = 2` has a fifty-fold margin over it; what reaches 2 s
without a keypress is a stalling stream, and that case needs the decision
F-RWD-10 asks for.**

### 12.5 M5, reaching the plugin's IpcHandler inside the harness

`run.sh --detach --playlist <abs path>/tests/fixtures/basic.m3u` under
`OMARCHY_IPTV_HARNESS_DIR=/run/user/1000/lrw3h` (its own scratch, so the
shared harness directory was not touched), with the owner's shell running
throughout. `run.sh ipc` hardcodes the target `harness`, so the plugin's
own target was called by hand.

| command | result |
|---|---|
| `qs ipc -p <h>/root call io.github.rmcdavid.iptv status` | `No running instances for ".../root/shell.qml"` -- the harness registers under ITS runtime directory |
| `XDG_RUNTIME_DIR=<h>/runtime qs ipc -p <h>/root ...` | `No running instances ... present on the current display "wayland/wayland-1"`; it names the harness instance as being on another display, because `run.sh` hands the shell the ABSOLUTE socket path |
| **`XDG_RUNTIME_DIR=<h>/runtime WAYLAND_DISPLAY=/run/user/1000/wayland-1 qs ipc -p <h>/root call io.github.rmcdavid.iptv status`** | **works**: `{"configured":true,"sourceHost":"local file","status":"ready","channels":3,...}` |
| `XDG_RUNTIME_DIR=<h>/runtime qs ipc --any-display -p <h>/root call io.github.rmcdavid.iptv status` | works, same reply |
| `XDG_RUNTIME_DIR=<h>/runtime qs ipc --pid <qs pid> call io.github.rmcdavid.iptv status` | works |
| `qs ipc -p /usr/share/omarchy/shell call io.github.rmcdavid.iptv status`, plain environment | the OWNER's: `"sourceHost":"iptv-org.github.io","channels":1453` -- the two are told apart by what they answer, not by the target name |
| `... show` under the working environment | lists both targets, `harness` and `io.github.rmcdavid.iptv` |

A relative `--playlist` path is refused by the service (`Relative path not
allowed`); the first start used one and read `channels: 0`, which is a
true answer to the wrong question. `run.sh reap` took the harness down
both times; `pgrep -x quickshell` named only 2186866 afterwards.

**Verdict: the plugin's verbs are reachable inside the harness with the
harness's environment -- `harness_env`'s two variables, or `--any-display`
with the runtime directory alone -- and `run.sh` should grow a
`plugin-ipc` subcommand that applies them, so the rewind scenario does not
carry the incantation by hand.**

### 12.6 Reproducing this

```bash
cd scripts/dev-harness/spikes/live-rewind
python3 -m unittest test_verdict          # 68 assertions, 51 from the two earlier passes
python3 design_pass.py m1 --channels <channels.json> --a 't:ABC.us@KAAL' --m-cap 420 \
    --scratch <scratch> --sock-dir "$XDG_RUNTIME_DIR/lrw3" --out <scratch>/m1.json
python3 design_pass.py m2 ... --a 't:AE.us@East' --index 1 --m-cap 330   # x3, concurrently
python3 design_pass.py m3 ... --a 't:ABC.us@KAAL'                          # needs the display
python3 design_pass.py m4 ... --a 't:ACECountryRadio.us@KPVMLD' --b 't:ABC.us@KAAL' --c 't:AE.us@East'
```

Each run under `timeout -k 5 <bound>`; the SIGTERM trap reaps the player
by pid. M3 dispatches to the compositor with the Lua forms, by the window's
address read from `hyprctl -j clients` for the pid this file holds, never
by class, and restores focus and the fullscreen state in its `finally`.
The screenshots are `grim` of a region and are deleted with the scratch.

The six judgements added to `verdict.py` were each seen red. Baseline
**Ran 68 tests ... OK**; eight mutations, each one red:

| mutation of `verdict.py` | result |
|---|---|
| `enumerate_fields` walks every list element, so a path repeats per range | Ran 68, FAILED (failures=1) |
| `string_fields` counts booleans as strings | Ran 68, FAILED (failures=1) |
| `not_moved` is non-strict at the threshold | Ran 68, FAILED (failures=1) |
| `not_moved` answers False (moved) for a missing reading | Ran 68, FAILED (failures=1) |
| `abs_deltas` keeps the sign | Ran 68, FAILED (failures=1) |
| `distribution` takes the upper middle for an even count | Ran 68, FAILED (failures=1) |
| `threshold_margin` flips the refused side | Ran 68, FAILED (failures=3) |
| `zero_point_error` flips its sign | Ran 68, FAILED (failures=2) |

### 12.7 Board rows for `docs/STATUS.md` (this lane does not own that file)

| id | severity | summary | state |
|---|---|---|---|
| F-RWD-7 | P2 | A negative absolute seek target is an offset from the cache END; the helper must never compute one, and must refuse with no range rather than seek | open |
| F-RWD-8 | P3 | The immediate `time-pos` after a seek echoes the target; on A&E the decoded landing was up to 5.1 s past it (keyframe), so `applied` is the request and the status re-sync carries the truth | open |
| F-RWD-9 | P2 | The 1 s-later read is not a refusal tell (3 of 10 underran at the edge) and the refusal log line can arrive after the immediate read (10 of 10 on A&E); the immediate read is the detector | open |
| F-RWD-10 | P3 | On an underrunning stream "behind live" grows while playing with no key pressed (12.9 s in 60 s on A&E); whether a stall-driven count-up is shown is undecided | open |
