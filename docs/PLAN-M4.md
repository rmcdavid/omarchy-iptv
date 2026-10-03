# M4 plan: make the guide a guide

**Status: APPROVED 2026-10-02 with M4-03 dropped.** The milestone is M4-01,
M4-02 and M4-04. M4-03 (hidden channels) moves to M5 behind the
channel-identity repair D-ID-4. Recording is refused for this round; live
rewind gets a measurement pass and no build. Repair 4 of M4-01 (the
per-source time offset) is sequenced after the other three and taken only if
the acceptance run shows a guide arriving in the wrong timezone.

Research pass 2026-10-02: six clients (TiviMate, IPTV Smarters Pro, XCIPTV,
Sparkle TV, Kodi with its PVR stack, MYTVOnline3), three cross-cutting sweeps
(why people switch, Linux desktop and keyboard-driven viewing, what everyone
complains about), and an inventory of our own plugin. Twenty-two candidates
survived deduplication; twenty-five were discarded with reasons. Four lanes
scored every candidate independently: product, architecture, interaction,
test.

## 0. The finding that reorders everything (D-EPG-2)

**Our guide data has never rendered a single line on any dataset on this
machine, and that is a defect against an M1 must (US6), not a feature gap.**
`docs/ROADMAP-PROPOSED.md` section 5 recorded this on 2026-09-16 and said
plainly that it was not on the board and should be. It still was not. It has
an id now.

Re-measured today against the installed source and the project's own
documented XMLTV asset (`https://i.mjh.nz/PlutoTV/us.xml.gz`, 427 channel
declarations):

| matcher | channels that would show a programme |
|---|---|
| what ships: exact `tvg-id` | **0 of 1,453** |
| exact id, after stripping the `@SD` feed suffix | 0 of 1,453 |
| normalised channel NAME | **232 of 1,453** |
| id or name | 232 of 1,453 |

The first ten name matches are `00s Replay -> 00s Replay`,
`48 Hours (1080p) -> 48 Hours`, `ALLBLK Gems (720p) -> ALLBLK Gems`: the
guide and the playlist agree on the name and disagree on the id, because the
playlist carries iptv-org ids (`00sReplay.us@SD`) and the guide carries
Pluto's own (`673247127d5da5000817b4d6`). Ambiguity is small: 3 of 424 guide
names and 5 of 1,453 of ours collide after normalising, so a rule of "match
only when the normalised name is unique on both sides" is available and
cheap.

A second, independent number: across the 180,681 entries of the published
guide index, 582 of our 1,453 channels are covered by a guide under their
exact `channel@feed` id and **735 under the bare channel id** -- so the feed
suffix alone costs 153 channels, 26 per cent of what id matching could reach.
Both repairs are real and they are not the same repair.

The owner's own install has **no guide URL set at all**, zero favourites,
zero saved searches, zero hidden groups. Any feature ranked on "users love
the grid guide" would be built for someone who is not the owner, over data
that renders nothing.

## 1. What the research says people actually want

Three features are named first by users of every client, in this order:
the **grid guide** (channels down, time across, walk it programme by
programme), **catch-up/archive**, and **recording**. Then: **manual channel
and group ordering**, **per-channel EPG overrides**, **several guide sources
merged**, and **live rewind** -- the one feature the research found people
switching to an admittedly worse application to get.

Our position on each is already settled by measurement, and the plan does not
reopen them except where noted:

- **Catch-up/archive: closed, not deferred.** Zero of 5,221 channels carry
  `catchup`, `catchup-source`, `catchup-days`, `timeshift` or `tvg-rec`;
  exactly four attribute keys exist across every `#EXTINF` line, so these are
  absent by construction. Reopen only if a provider probe reports an archive
  flag.
- **Grid guide: gated, not refused.** A grid over a matcher that matches
  nothing draws an empty lattice. It is downstream of section 0 and of
  programme detail, and Kodi's own grid is reported laggy at 40 to 100
  channels against our budget of 10,000. Not in M4.
- **Recording: a policy decision, not an engineering one.** It is one mpv
  property we already own (`--stream-record`, currently in `MPV_RESERVED`
  with the comment "writes the stream itself to disk"), so the cost is small
  -- but shipping it reverses a privacy refusal this project already made and
  shipped, writes a file of unbounded size outside our three directories
  (engineering rule 6), makes a provider-derived string into a filename for
  the first time, and mpv documents that switching streams during recording
  may break the file, which collides with a plugin whose core verb is
  zapping. See decision D3.
- **Live rewind: measured on 2026-10-03, and the project's belief was wrong.**
  This paragraph first said the feature was refused by arithmetic and that a
  disk buffer was unavailable because `$XDG_RUNTIME_DIR` is a tmpfs; the
  measurement pass D2 authorised found rewind available on 31 of 32 channels
  that played, inside a window the plugin already pays for, and that mpv's
  disk cache lives wherever `--demuxer-cache-dir` points, not in the runtime
  directory (F-RWD-2). The evidence is `docs/SPIKE-LIVE-REWIND.md`; the
  design is `docs/M5-01-LIVE-REWIND.md`. The disk option stays refused there,
  on its real grounds: it writes the stream to disk every second into a file
  no tool can show, which is D3's shape by another door.

## 2. Proposed M4, four items

Ranked by the four lanes' combined score, filtered by what the measurements
support. Costs: small = days, medium = a lane, large = a milestone.

### M4-01 The guide renders (medium) -- fixes D-EPG-2

Four repairs to one pipeline, in this order, each independently gradeable:

1. **Normalise the feed suffix** on both sides before comparing ids
   (`Name.us@SD` and `Name.us` are the same channel). +153 channels of
   possible id coverage, measured.
2. **Fall back to a normalised channel name** when no id matches, and only
   when the normalised name is unique on both sides. 0 -> 227 measured on the
   frozen inputs (the proposal said 232 from a research probe that normalises
   slightly differently from the shipping key; the ceiling on these inputs is
   229). Precision is the acceptance criterion, not recall: a wrong programme
   on a channel is worse than a blank row, and the precision half of this
   criterion has NOT been run -- see the 2026-10-03 review.
3. **Read the guide URL the playlist declares** (`#EXTM3U url-tvg`) and
   default a source's empty guide URL to it, saying in Sources where it came
   from. `channels.json` already carries `epgUrlHint`, so this is nearly
   free, and it is the one repair that could fix the owner's own install
   without them typing anything.
4. **A per-source time offset** in hours and minutes, for guides that arrive
   in the wrong timezone. Independent of the other three; do not merge it
   with them in implementation.

Acceptance is a count that moves off a measured floor of zero on real data
already on this machine, plus a precision check on a hand-labelled sample.
Shared JSON fixture, both implementations run it (the rule for a rule
implemented twice).

### M4-02 Programme detail (small)

Carry description, category and episode data through the helper instead of
dropping them, and show them for the highlighted programme in a panel that
reuses the track-picker geometry on a free key. The XMLTV is already parsed
and the fields are already being discarded. This is what users describe when
they praise a grid: not the lattice, but reading what the thing is. It is
also the home the manual-override and reminder features would need later.

### M4-03 Hide individual channels (small)

The `x` gesture that hides a group, applied to one row. Already named and
deliberately left out of M3 (`docs/PLAN-M3.md` section 4), every hard
decision settled by the group precedent, pure `Model.js`. It is the only
curation that does anything at all on the shape the owner actually browses,
3,335 channels in one group. Needs ruling D4 on the key collision.

### M4-04 A keyboard map in the guide (small)

One key, `?`, an overlay listing every key, generated from the same tables
the footer hints are built from so that it cannot drift. We have an unusually
rich key grammar and nothing in the product shows it; the footer hint row is
at its structural limit at fifteen segments and elides from the left. This is
the only item in the whole research that is purely about being keyboard-first,
which is our entire pitch.

## 3. What must happen first, and is not a feature

**Channel identity (D-ID-4), already on the board and already accepted.**
Four candidates persist a reference to a channel -- hidden channels, manual
ordering, per-channel EPG overrides, per-channel playback adjustments -- and
all four silently attach to the wrong channel when a provider rotates its
URLs, which was measured at 1 of 3,335 ids surviving a password rotation.
M4-03 is one of those four. Either it ships after the identity repair, or it
ships knowing that.

## 4. Decisions for the product owner

- **D1.** Approve M4 as "make the guide a guide": M4-01 through M4-04, in
  that order, with M4-01 shipping alone if the milestone has to be cut short.
- **D2.** Authorise a single measurement pass on live rewind before any
  design: read `seekable` and `partially-seekable` across the installed list,
  and the demuxer back-buffer window at a measured bitrate. It is the
  highest-demand item in the research and we have one contradictory reading.
  Measurement only; no build.
- **D3.** Recording: refuse, defer, or authorise a privacy reversal with a
  written scope (where files go, how the filename is derived, what happens
  when the user zaps mid-recording). Engineering rule 6 needs an amendment
  either way.
- **D4.** `x` on a channel row currently hides its GROUP. For M4-03 it should
  re-point to the channel, with group hiding moving to the group column,
  because the interaction document forbids splitting the two with Shift.
  Confirm, or name the alternative.
- **D5.** The owner's install has no guide URL. Either set one so M4-01 can
  be verified against the owner's own usage, or accept that its acceptance
  runs against fixtures and the installed list only.

## 5. Refused in this pass, with the reason, so nobody re-proposes them

Cloud sync and accounts (no account surface, no server). Multiview and a
second window (refused on arrival, three layers). Merging sources into one
list (ids are per source, favourites are global by id). Automatic failover
(recreates the 0.4.0 defect class and moves the viewer without consent). A
PIN or parental lock (settled 2026-09-26: the useful half is hiding, a PIN on
a single-user desktop is theatre). VOD and series libraries (needs the Xtream
player API that phase 1 proved absent here). Casting and re-streaming (a new
durable sink for a credentialed address). Logo lookup from any host the
playlist does not name (RULING-LOGOS). A sports fixture browser (needs a
third-party feed and an account). Remappable keys (the demand is a set-top-box
remote's, and does not transfer to a keyboard).

Already ours at or beyond the depth the research calls table stakes, worth
saying once: favourites, groups with hiding, search-as-you-type, channel
numbers with numeric zap, recents, an audio and subtitle picker, picture in
picture, several switchable sources, dead-channel marking, per-stream HTTP
headers, a manual refresh with a visible interval, no ads, and no account.
