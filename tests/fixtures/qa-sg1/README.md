# tests/fixtures/qa-sg1/

Fixtures for **D-SG-1** (docs/STATUS.md "## Defects", fixed under ruling SG1;
docs/QA-PHASE3.md tier 3c, "D synthetic"). Run by `tests/test_fixture_sg1.py`,
which `python3 -m unittest discover -s tests` and `scripts/check.sh` pick up
with no wiring.

The defect: a search key is `name + " " + group`, so on a list whose every row
sits in ONE group every key ends with the same words, and tier 3 of
`Model.matchRank` let any FRAGMENT of those words through. `st`, `sta`, `ted`,
`ited`, `unit` each reported the whole list; the header and footer repeated the
number. The fix requires every term found only in the group half to be a WHOLE
WORD there (`Model.containsAllWords`). The configured 28-group source cannot
show either the defect or the fix's accepted costs, which is why these exist.

- `single-group.m3u` - the committed list: 50 rows, all in `United States`,
  hand-readable, with names chosen so that the fragment queries have a
  non-trivial number of genuine matches (`USA STARZ ...`, `STATE TV`,
  `UNITED SPORTS`, `LIMITED EDITION TV`). The file's header comment lists the
  expected count per query. Every URL is under the reserved `.test` TLD.
- `verify.js` - the python-drives-node seam. Takes a `channels.json` (the
  HELPER's output, so the key format is the shipping one, never guessed), the
  shipping `Model.js`, an optional pre-fix `Model.js`, and queries; runs the
  guide's search path (`parseChannels`, `prepareChannels`, `buildChnoIndex`,
  `scopeSurface`, `channelsForScope`, `effectiveScope`, `filterChannels`,
  `groupWordHint`, in the order Service.qml and Guide.qml call them) and prints
  `{query: {pre, post, preTruncated, postTruncated, postRows, hint}}`.
- `README.md` - this file.

The two 3,335-row lists are NOT committed. The test generates them into a
`tempfile.mkdtemp()` with `scripts/gen-playlist.py --seed 1` (byte-identical,
digest asserted), rewrites the single-group one's title to `United States`,
and parses each with `bin/omarchy-iptv playlist --cache-dir <scratch>`. The
pre-fix ranking is likewise BUILT at test time: a scratch copy of `Model.js`
with the one line ruling SG1 changed put back to the substring test.

## By hand

    S=$(mktemp -d)
    python3 bin/omarchy-iptv playlist --url "$PWD/tests/fixtures/qa-sg1/single-group.m3u" --cache-dir "$S"
    sed 's/if (containsAllWords(text, tokens)) return 3/if (containsAll(text, tokens)) return 3/' Model.js > "$S/Model-pre-fix.js"
    node tests/fixtures/qa-sg1/verify.js "$S/channels.json" Model.js "$S/Model-pre-fix.js" st sta ted ited unit starz

## What was measured

Committed list, 50 rows in one group:

| query | pre-fix | shipping | why |
|---|---|---|---|
| `st` | 50 | 11 | five STARZ, two STATE, FIRST, HISTORY, TASTEMADE, WESTERNS |
| `sta` | 50 | 7 | five STARZ, two STATE |
| `ted` | 50 | 4 | UNITED SPORTS x2, ANIMATED, LIMITED |
| `ited` | 50 | 3 | UNITED SPORTS x2, LIMITED |
| `unit` | 50 | 2 | UNITED SPORTS x2 |
| `starz` | 5 | 5 | not a fragment of the group name; unchanged |
| `state` -> `states` | 50, 50 | 2 -> 50 | UX 2.6 cost 2: the count grows when the word completes |
| `united stat` | 50 | 0, hint `United States` | UX 2.6 cost 1: the dead zone, and the empty state names the group |

Generated, 3,335 rows in one group (`--channels 3335 --groups 1 --seed 1`,
sha256 `9b6cb8d1...`):

| query | pre-fix | shipping |
|---|---|---|
| `st` | 3335, "First 200 of 3,335" | 302, "First 200 of 302" |
| `sta` | 3335 | 90 |
| `ted` / `ited` / `tes` | 3335 | 0 |
| `unit` / `unite` / `stat` / `state` | 3335 | 0, hint `United States` |
| `es` / `ni` | 3335 | 312 / 104 |
| `starz` | 0 | 0 |
| `states` / `united` / `united states` | 3335 | 3335 |

Generated control, 3,335 rows in 26 groups (`--groups 26 --seed 1`, sha256
`910400e0...`), UX 2.6 cost 3, fewer rows than before:

| query | pre-fix | shipping |
|---|---|---|
| `port` | 631 | 110 |
| `istor` | 510 | 100 |
| `atur` | 360 | 85 |
| `ew` | 377 | 120 |
| `cienc` | 216 | 102 |
| `utdoor` | 366 | 97 |
| `lassic` | 238 | 101 |
| `sports` / `news` / `history` | 631 / 377 / 510 | unchanged |
| `roup` | 3335 | 0 |

That last row is a finding of its own: the generator writes `Group NNN <Noun>`
on every title, so the word `Group` is shared by all 26 and a fragment of it
reproduced the defect on a multi-group list. The condition is a word common to
every key's group half; one group is only the commonest way to get there.

## By hand, at scale

The display session wants the 3,335-row list as a local file path
(docs/QA-PHASE3.md). It is deterministic, so it need not be committed:

    S=$(mktemp -d)
    python3 scripts/gen-playlist.py --channels 3335 --groups 1 --seed 1 --out "$S/gen.m3u"
    sha256sum "$S/gen.m3u"    # 9b6cb8d10d0e8c6a92915364f9924d12b5430f79636cf490eb0f129ce040adc9
    sed 's/group-title="Group 001 Comedy"/group-title="United States"/' "$S/gen.m3u" > "$S/united-states.m3u"
    python3 bin/omarchy-iptv playlist --url "$S/united-states.m3u" --cache-dir "$S"

Then add `$S/united-states.m3u` as a source from inside the guide.

## What still needs a screen

The numbers above are what the guide is TOLD. Not settled here, and not to be
cited as if it were: the header and footer strings composed from them, the
empty state rendering the hint while typing toward the sole group name, and
per-keystroke responsiveness in the QML engine at 3,335 rows.

The `groupNames` the hint sees are collected by `Model.groupNamesForHint`,
which Guide.qml `rebuildGroups` and verify.js both call (D-SG-2, closed in
0.7.2); the node suite pins its two shapes.
