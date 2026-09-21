# tests/fixtures/qa-gs2/

Fixtures for board row **D-GS-2** (docs/STATUS.md; ruling GS9 in
docs/UX-GUIDE-AT-SCALE.md; fixed at 9d236d5 with follow-up ef6c307): with
guide data configured but no `tvg-id` matches, every guide row went to
two-line height with a BLANK second line -- density spent on white space,
three visible rows lost. The fix decides the second line on the DATA
(`Model.epgCoverage(channels, epgMap).carries`) instead of the setting
(`epgConfigured`). The board row ends "No QA re-test"; this directory is
what makes that re-test possible from a terminal, without a subscriber list.

Why nothing already committed could show it: the configured list has 28
groups, so `rowShowsGroup` is already true in All scope and the EPG term
never decides, and a `tvg-id` on 100% of its rows, matched by its own guide.
The repro needs ONE group and guide ids DISJOINT from the playlist.

- `verify.js` - the bridge from python to Model.js (CLAUDE.md rule 12).
  Takes `<Model.js> <channels.json> <epg-now.json> <nowSec>`, walks the exact
  path Service.qml and Guide.qml take (`parseChannels`, `prepareChannels`,
  `scopeSurface`, `parseEpgNow`, `epgCoverage`, `rowsHaveDetail`,
  `rowShowsGroup`, `epgFields`, `rowDetail`) and prints one JSON verdict.
  The Model.js path is an argument so the test can run the same verdict
  against a scratch copy carrying the PRE-FIX decision.
- `qa-gs2-one-group.m3u` - the shape, small enough to read: eight rows, one
  group, a `tvg-id` on every row, ids `ch00001.test`..`ch00008.test`. Those
  are the ids the synthetic profile of `scripts/gen-playlist.py` assigns by
  index, so a generated guide matches this list and a realistic-profile
  guide is disjoint from it. `tests/test_fixture_gs2.py` asserts that shape
  and runs the negative and positive cases on it, rather than trusting it.
- The 60-row list and the three XMLTVs are NOT committed.
  `tests/test_fixture_gs2.py` generates them into a `mkdtemp()` on every run
  with `--now` set to the current time, so the guide window is always
  current (`tests/fixtures/qa-epg.xml` went stale exactly that way). The
  helper (`bin/omarchy-iptv playlist`, then `epg`) builds the `epg-now.json`
  the guide would load; nothing hand-builds the map.

## The three cases, and the numbers the test records

All three share one playlist: synthetic profile, 60 channels, ONE group,
`--epg-ids 1.0` (a `tvg-id` on every row), no twins, no headers.

| case | XMLTV | helper `matched` | `epgCoverage` | `rowsHaveDetail` | detail lines |
|---|---|---|---|---|---|
| (a) negative | realistic-profile run, ids `CamelName.cc` -- intersection with the playlist asserted EMPTY, case-insensitively | 0 | 60/60 with id, 0 matched, carries false | false | 60 blank, 0 filled |
| (b) positive | the playlist's own `--xmltv` | 60 | 60 matched, carries true | true | 60 filled |
| (c) boundary | a `--channels 1` run: exactly `ch00001.test` | 1 | 1 matched, carries true | true | 1 filled, 59 blank |

Case (c) is the original complaint at 1/N instead of 0/N. The test RECORDS
what the shipping code says there; it decides no policy. If a ruling ever
sets a threshold, that test is the number that changes.

The pre-fix reproduction (`test_prefix_decision_reproduces_the_defect`)
copies Model.js into the scratch directory, puts back the one line 9d236d5
changed (`o.epgConfigured === true` where `o.epgCarries === true` now
stands) and runs case (a) against the copy: `rowsHaveDetail` true with 60
blank detail lines, which is D-GS-2 exactly. The tracked file is never
touched.

## To look at the generated files by hand

Into a scratch directory, never into the repo:

    NOW=$(date +%s)
    python3 scripts/gen-playlist.py --profile synthetic --channels 60 --groups 1 \
        --epg-ids 1.0 --dupes 0 --headers 0 --multi-group 0 --seed 1 \
        --out /tmp/gs2/one-group.m3u --xmltv /tmp/gs2/match.xml --now "$NOW" --hours 24
    python3 scripts/gen-playlist.py --profile realistic --channels 60 --groups 1 \
        --epg-ids 1.0 --dupes 0 --headers 0 --multi-group 0 --seed 2 \
        --out /tmp/gs2/disjoint-source.m3u --xmltv /tmp/gs2/disjoint.xml --now "$NOW" --hours 24
    python3 scripts/gen-playlist.py --profile synthetic --channels 1 --groups 1 \
        --epg-ids 1.0 --dupes 0 --seed 1 \
        --out /tmp/gs2/one-source.m3u --xmltv /tmp/gs2/one-match.xml --now "$NOW" --hours 24

## What the terminal settles, and what still needs a screen

Settled here, from the shipping functions: the coverage counts, the
`rowsHaveDetail` verdict for all three cases, the row-by-row detail text
(blank on every row in the negative case), the helper's own `matched` count
along the same data, and that the pre-fix decision turns the negative case
into two-line rows with nothing to print.

Still needs a screen: the pixel consequence -- 38 px versus 52 px rows,
visible rows 12 versus 9, pageSize 11 versus 8 -- and that a source switch
re-measures the verdict rather than inheriting the previous source's. Both
are Guide.qml layout, reachable only by the display lane's live pass.
