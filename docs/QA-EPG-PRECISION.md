# Precision audit of the M4-01 name fallback, 2026-10-03

`docs/PLAN-M4.md` M4-01 repair 2 states the acceptance criterion for the
whole repair:

> Precision is the acceptance criterion, not recall: a wrong programme on a
> channel is worse than a blank row.

The M4 round moved `matched` from **0** to **227 of 1,453** on the frozen real
inputs and graded nothing about the 227. The review of 2026-10-03 recorded
that as unmet rather than quietly dropping it. This document runs it.

**Verdict in one line: of the 227 pairs, 226 are right and 1 is wrong**, and
the wrong one is wrong by a rule this project already wrote down and did not
point the matcher at. The repair costs exactly that pair and nothing else,
measured end to end, and it recovers ten channels of index coverage on the
way.

## 1. Method

Three things make this an audit rather than a restatement of the matcher.

**The run is the shipping verb, on the frozen inputs, reproduced.** The same
command the M4 acceptance used:

```
OMARCHY_IPTV_URL=<frozen guide> bin/omarchy-iptv epg --cache-dir <fresh> --force --now 1791015219
```

It answered `matched 227, matchedById 0, matchedByFeed 0, matchedByName 227,
nameIndexed 1443, nameDroppedPlaylist 10, nameDroppedGuide 4, epgChannels 227,
programmeCount 2877, nowCount 227`, and `epg-now.json` came out **byte
identical** to the frozen artifact of the integration run. So the pairs judged
below are the pairs that shipped, not a re-derivation of them.

**The pair list is proven complete against the shipping output.** The verb
reports counts but not which guide channel won which row, so the 227 pairs
were reconstructed by calling the shipping `build_alias` and `epg_name_key`
and replaying the shipping `<display-name>` selection. The reconstruction is
not trusted: the set of playlist keys it produces was compared with the set of
channel keys in `epg-now.json`. **227 == 227, nothing in either difference.**

**The question is not whether the pairs match the rule.** By construction
every pair has equal normalised keys, so asking that proves nothing. The
question is whether the rule married two DIFFERENT channels, and answering it
needs an identifier the matcher never reads.

### 1.1 The oracle: an identifier outside the name

The installed source is the iptv-org US list and the guide is Pluto's. Where
iptv-org carries a Pluto channel it streams it from an address containing
**Pluto's own channel id** (`https://jmp2.uk/plu-<24 hex>.m3u8`), and some rows
carry the same id in their logo address. The guide declares each channel under
that same id. **The matcher reads neither** -- it joins on the display name and
the id strategies contributed 0 of the 227. So when the programme that lands on
a row is the programme of the channel whose id that row's own URL names, two
independent identifiers agree, and the agreement was not produced by the thing
being tested. That is the rule-14 shape: observed at the sink, judged by
something else.

The oracle is directional and this document does not pretend otherwise.
Agreement is strong evidence the pair is one channel. Disagreement is weak
evidence of error, because an iptv-org URL can carry an id Pluto has since
re-issued. So disagreement is split:

| grade | meaning |
|---|---|
| **A confirmed** | the guide channel id is one the row itself carries |
| **B not contradicted** | the row's id is not a channel in this guide at all, and the guide id matched is claimed by no other row -- consistent with Pluto re-issuing an id |
| **C contradicted** | the row's id names a DIFFERENT channel that this guide also declares, so the guide itself distinguishes them and the match crossed them |
| **D no identifier** | the row streams from another distributor and carries no Pluto id; judged by name and by the programme |

## 2. The counts

| | pairs | A confirmed | B not contradicted | C contradicted | D no identifier |
|---|---|---|---|---|---|
| **what shipped** | **227** | **153** | **9** | **0** | **65** |

Asked the second way, over the names rather than the ids:

| name evidence | pairs |
|---|---|
| raw names identical after the plain fold, no marker strip needed | 126 |
| differ ONLY by a resolution or codec marker the key strips | 101 |
| differ by a bracket span the key strips | **0** |
| differ by anything else at all | **0** |
| whole matched key is one generic word (`movies`, `news`, `comedy`...) | **0** |
| matched key is a single token of any kind | 20 |

And the judgement the brief asks for:

| grade | pairs |
|---|---|
| obviously right | **226** |
| needs a human | **0** on the question "is this the right channel"; see section 5 for the narrower question the inputs cannot settle |
| **wrong** | **1** |

## 3. The one wrong pair: D-EPG-5

| | |
|---|---|
| playlist | `Bloomberg TV (1080p)`, `tvg-id="BloombergTV.us@US"`, group `Business`, streamed from an unbranded address |
| guide | `54ff7ba69222cb1c2624c584`, `<display-name>Bloomberg TV+</display-name>` |
| what landed | `Latitude`, a Bloomberg Originals series |

iptv-org's `BloombergTV.us` is Bloomberg Television. The guide's channel is
Bloomberg TV+, and the guide says so itself: its `<desc>` opens
"Bloomberg TV+ is a live 24-hour global business and financial news channel".
Two services, one name after the fold.

**The project already holds the rule that separates them and the matcher does
not use it.** `normalize_id_text` exists precisely because `+` and `*` are, in
the helper's own words, "the difference between two channels rather than noise
inside one". `epg_name_key` folds on `normalize_text`, where `+` becomes a
space. Of the 227 pairs, exactly **one** is equal under `normalize_text` and
unequal under `normalize_id_text`, and it is this one. That is the whole of the
precision failure on these inputs: one pair, found by a rule the repository
was already carrying.

The same fold has a recall half, and it is larger than the precision half.
`nameDroppedPlaylist` is 10, and all ten channels are `+` pairs:

| colliding key | the two channels the fold merges |
|---|---|
| `news12 hudson valley` | `News12+ Hudson Valley (1080p) [Geo-blocked]`, `News12 Hudson Valley [Geo-blocked]` |
| `news12 long island` | `News12+ Long Island (1080p) [Geo-blocked]`, `News12 Long Island (1080p) [Geo-blocked]` |
| `news12 new jersey` | `News12+ New Jersey (1080p) [Geo-blocked]`, `News12 New Jersey [Geo-blocked]` |
| `news12 new york` | `News12+ New York (1080p) [Geo-blocked]`, `News12 New York (1080p)` |
| `tennis channel 2` | `Tennis Channel +2 (720p)`, `Tennis Channel 2 (1080p)` |

Every one of them is two distinct under `normalize_id_text`. So the fold that
produced the wrong pair is the same fold that threw ten channels away rather
than guess between them: one root cause, both failure directions.

### 3.1 The rule that excludes it, and its measured cost

The rule: **build `epg_name_key` on `normalize_id_text` instead of
`normalize_text`**, keeping the marker strip exactly as it is. One line. It is
not a new rule; it is pointing the matcher at the fold the project already
reserved for "two channels or one".

Measured end to end through the shipping verb on the frozen inputs, not
reasoned about:

| | `matched` | `nameIndexed` | `nameDroppedPlaylist` | A | B | C | D |
|---|---|---|---|---|---|---|---|
| what shipped | 227 | 1,443 | 10 | 153 | 9 | 0 | 65 |
| `epg_name_key` on `normalize_id_text` | **226** | **1,453** | **0** | **153** | **9** | **0** | **64** |

The cost is **one pair, and it is the wrong one**: the set difference between
the two runs is exactly `{BloombergTV.us@US}` in one direction and empty in the
other. Not one confirmed pair, not one uncontradicted pair, nothing else moves.
The gain is `nameIndexed` 1,443 to 1,453 and `nameDroppedPlaylist` 10 to 0 --
the ten channels above become distinguishable, and although none of them finds a
counterpart in THIS guide they are available to any other.

A product owner can act on that: the repair has no measured downside on these
inputs.

## 4. The pairs the oracle did not confirm, in full

### 4.1 The nine B pairs: our id is not in this guide

For each, the Pluto id the playlist row carries is **not** declared anywhere in
this guide's 427 channels, and the guide id that was matched is claimed by no
other playlist row -- so these are not two channels competing, they are one
channel under two ids across time. The programme that landed is right for the
channel in all nine.

| playlist | our id | guide id and name | what landed |
|---|---|---|---|
| `Best of Dr Phil` | `666815f2...` | `60f760bb...` `Best of Dr. Phil` | `Dr. Phil` |
| `CBS News 24/7 (720p)` | `6350fdd2...` | `5a6b92f6...` `CBS News 24/7` | `The Daily Report` |
| `Forensic Files` | `62e92392...` | `5bb1af6a...` `Forensic Files` | `Forensic Files` |
| `Garfield and Friends` | `677f9275...` | `60faf9dd...` `Garfield and Friends` | `Garfield Specials` |
| `Misterios sin resolver` | `5f610042...` | `5f4d882d...` `Misterios sin resolver` | `Misterios sin resolver` |
| `Nash Bridges (720p)` | `666021cc...` | `6675c742...` `Nash Bridges` | `Nash Bridges` |
| `RiffTrax (720p)` | `68222b9c...` | `58d947b9...` `RiffTrax` | `RiffTrax: The Retrievers` |
| `The Price Is Right: The Barker Era (720p)` | `64c220e1...` | `5f7791b8...` same | `The Price Is Right` |
| `Tiny House Nation (720p)` | `6540ff4f...` | `601a0342...` `Tiny House Nation` | `Tiny House Hunting` |

### 4.2 The 65 D pairs: no identifier on our side

These 65 rows do not stream from Pluto at all. Their hosts are the FAST
syndicators and broadcaster CDNs -- 5 from Tubi, 8 from the CBS News local
feeds, the rest from Amagi, Wurl, Frequency, Akamai and CloudFront endpoints,
plus two bare-IP addresses. One is the wrong pair of section 3. For the other
64, the brand is unambiguous (`Midsomer Murders`, `MST3K`, `QVC2`, `Shop LC`,
`Doctor Who Classic`, the eight `CBS News <city>` rows, and so on) and the
programme that landed fits the channel in every case. 39 of the 65 have a
programme whose title or description shares a distinctive token with the
channel name; the other 26 were read individually and all 26 are coherent
(`Nosey` showing `The Maury Show`, `Judge Nosey` showing `People's Court`,
`Revry` showing `Mapplethorpe`, `Women's Sports Network` showing `LPGA Golf`).

The narrower question these inputs cannot settle is in section 5.

## 5. What was looked for and not found, so the absence means something

The brief for this audit named four failure shapes. Each was searched for
mechanically over all 227 pairs, and here is what would have shown one:

1. **A name generic enough to belong to two broadcasters.** Searched by
   reducing each matched key to its tokens and testing it against a list of
   30 generic channel words. **0 pairs** have a key that is one generic word.
   20 pairs have a single-token key and all 20 are distinctive marks
   (`Gunsmoke`, `MST3K`, `QVC2`, `Degrassi`, `FailArmy`, `PokerGO`...). A
   guide declaring a bare `Movies` or `Comedy` against our `Movies` row would
   have shown here; this guide declares none.
2. **Raw names differing by more than the markers the matcher strips.** Each
   pair's two raw names were folded WITHOUT the strip and compared, and the
   spans the strip removed were then classified. 126 pairs need no strip at
   all; the other 101 differ only by a resolution or codec marker
   (`(1080p)`, `(720p)`); **0** differ by a bracket span and **0** by
   anything else. A pair married by discarding real words would have shown as
   a removed span that is not a marker.
3. **A playlist group contradicting the guide programme.** The full
   group-by-category matrix of all 227 pairs was read. No absurdity:
   `Movies` rows carry `Movie`, `Horror`, `Western`, `Science fiction`;
   `Sports` rows carry `Sports`; `Music` rows carry `Classical` and `Latino`.
   Every one of the 22 `Kids`, `Family` and `Animation` rows was listed with
   its title and read individually -- `Peppa Pig` showing `Peppa Pig`,
   `Nick Jr. Pluto TV` showing `PAW Patrol`, `Forever Kids` showing
   `All Dogs Go To Heaven`. **A kids channel matched to a guide full of
   thrillers would have shown here and none did.**
4. **A programme that looks wrong for the channel.** Every one of the 74
   pairs the oracle did not confirm (9 B + 65 D) was read with its title,
   category, description and group. One reads wrong and it is named below as
   F-EPG-9.

And the result the oracle itself produced, which is the strongest of them:
**C = 0.** On the shipped matcher there is not a single pair where the row's
own Pluto id names a different channel that this guide also declares. The
guide distinguishes 427 channels; the matcher crossed none of them. That
number is not vacuous -- section 6.2 shows a candidate loosening where it
becomes 1.

## 6. Findings

### 6.1 Defects and findings this audit files

1. **D-EPG-5: the fold that merges two channels is the one the matcher uses.**
   `epg_name_key` folds on `normalize_text`, which turns `+` into a space,
   while the project's own `normalize_id_text` keeps `+` and `*` "because they
   are the difference between two channels rather than noise inside one". On
   the frozen inputs this produces one wrong pair (`Bloomberg TV` married to
   the guide's `Bloomberg TV+`, section 3) and drops ten channels as
   ambiguous that are not ambiguous at all (five `+` pairs, section 3). The
   repair is one line and its measured cost is the wrong pair and nothing
   else (section 3.1). Suggested P2.

2. **F-EPG-7: a country qualifier the key keeps costs 27 confirmed pairs.**
   88 of the 1,453 installed names carry a `(United States)`, which
   `_EPG_NAME_NOISE` does not strip, and 31 of those rows carry a Pluto id
   this guide declares -- so the oracle names a correct pair that the key
   refuses. This is recall, not precision, and it is reported here because it
   was measured on the way and because the obvious loosening is NOT free:
   see 6.2. Suggested P3, a decision rather than a repair.

3. **F-EPG-8: a missing space is not a distribution marker.** The guide
   declares `TennisChannel 2` as one word where the playlist writes
   `Tennis Channel +2 (720p)`. The oracle says they are the same channel
   (`681109b6...` both sides). Neither the shipping key nor the D-EPG-5
   repair closes a missing space, so the repair must not be credited with it.
   Recorded so it is not rediscovered as a regression. Suggested P3.

4. **F-EPG-9: right brand, and the schedule is a different playout.**
   `Fox Weather (720p)` streams the broadcaster's own 24/7 feed and matched
   the guide's `FOX Weather`; what landed is
   `Fox Nation: PARK'D Death Valley / Channel Islands`, a travel series, with
   `Park'd Places` next. The channel is right and the schedule is Pluto's
   playout of it, which is not the playout our URL opens. This is the only
   row of the 227 where the programme itself argues the two feeds differ, and
   it is the visible instance of a class the frozen inputs cannot size: 64 of
   the 227 rows stream from a different distributor than the guide describes,
   and a syndicated FAST channel typically has one playout per platform. What
   would settle it is not another fixture -- it is one channel on a real
   screen with a clock, which is a live pass. Suggested P3.

5. **F-EPG-10: the bracket branch of the matching key is unexercised.**
   `_EPG_NAME_NOISE` strips `\[[^\]]*\]`, arbitrary bracket content, on both
   sides. 142 of the 1,453 playlist names carry such a span (`[Not 24/7]` 82,
   `[Geo-blocked]` 60) and **0 of the 427 guide display-names do**, so **0 of
   the 227 matched pairs exercised the branch**. It is therefore an unmeasured
   risk rather than a realized one, and the risk is real in shape: unlike the
   resolution markers, the branch discards content it has not inspected, so a
   guide writing `Channel [East]` against our `Channel [West]` would be
   married with no evidence either way. Narrowing it to the markers that
   actually occur would cost nothing measurable on these inputs. Suggested
   P3. The fixture added by this audit is its only coverage.

### 6.1.1 The five board rows these ids need, and why they are not here

`scripts/check-defect-ledger.py` requires every id written into a tracked
markdown file to carry a row in `docs/STATUS.md` "## Defects", and that is
engineering rule 13 working as designed -- an id a human is expected to copy
is an id that eventually stops being copied. **This lane does not own
`docs/STATUS.md`**, so the rows below are handed over rather than written, and
the ledger check reports exactly five problems against this branch until they
land. The five problems ARE this hand-off; nothing else on the gate is red.

```
| D-EPG-5 | P2 | M4-01 | docs/QA-EPG-PRECISION.md 3 (frozen inputs, matched 227) | open |
| F-EPG-7 | P3 | M4-01 | docs/QA-EPG-PRECISION.md 6.1 item 2 and 6.2 | open, decision |
| F-EPG-8 | P3 | M4-01 | docs/QA-EPG-PRECISION.md 6.1 item 3 | open |
| F-EPG-9 | P3 | M4-01 | docs/QA-EPG-PRECISION.md 6.1 item 4 (needs a live pass) | open |
| F-EPG-10 | P3 | M4-01 | docs/QA-EPG-PRECISION.md 6.1 item 5 | open |
```

The alternative -- dropping the ids so the branch is green -- is the exact
failure engineering rule 13 was written for and that D-REL-3 cost this project
eleven days and two shipped recurrences. A finding written as a remark is the
same defect with worse odds, so the ids stay and the conflict is raised
instead of resolved silently.

### 6.2 The cost of the F-EPG-7 loosening, measured rather than guessed

The tempting repair for F-EPG-7 is to let `_EPG_NAME_NOISE` strip any
parenthetical instead of only the known markers. Run end to end on the frozen
inputs, alone and combined with the D-EPG-5 repair:

| rule | `matched` | A | B | **C** | D | `nameIndexed` | `nameDroppedPlaylist` |
|---|---|---|---|---|---|---|---|
| what shipped | 227 | 153 | 9 | **0** | 65 | 1,443 | 10 |
| D-EPG-5 repair alone | 226 | 153 | 9 | **0** | 64 | 1,453 | 0 |
| strip any parenthetical | 256 | 180 | 9 | **1** | 66 | 1,441 | 12 |
| both | 255 | 180 | 9 | **1** | 65 | 1,451 | 2 |

So the loosening buys 27 oracle-confirmed pairs and **breaks C = 0**. The one
contradicted pair it introduces:

`Pluto TV Reality (United States)` streams `69fa3faa...`, which this guide
declares as **`Pluto TV Pride`**. The loosening matches it to the guide's
separate `Pluto TV Reality` channel, `5d8bf0b0...`. Both channels are in the
guide under their own ids, so the guide itself says they are two, and the
match puts one's schedule on the other's stream. That is the exact failure
the acceptance criterion forbids, and it is worth 1 pair against 27.

This is a product-owner trade, not a lane's call, and the audit's position is:
take the D-EPG-5 repair now, because its cost is measured at zero correct
pairs; hold F-EPG-7 until the one contradicted pair can be excluded, which the
oracle cannot do inside the matcher because `plu-<hex>` in a stream URL is
specific to one provider's list and one guide.

## 7. The check this audit adds, and its mutation proof

The audit above is a one-off. What a gate can run is in
`tests/test_epg_match.py::EpgPrecisionTest` (8 cases) over a new fixture
triple, `tests/fixtures/epg-precision.{m3u,xml,json}`. Every playlist row is
copied verbatim from the installed list with its real `tvg-id`, group and
Pluto id, and every guide channel id, display-name, programme title and time
is copied from the frozen asset; two declarations that are not, are labelled
on the line.

The oracle travels into the fixture with the data: the test asserts that the
title reaching `epg-now.json` on each row is the title the guide carries for
the channel whose id that row's URL names. The fixture's own invariant is a
test of its own, so a doctored fixture cannot pass.

Rule 11, each mutation run on its own against the whole suite in an isolated
copy of the worktree, helper restored in between. Baseline in that copy: **752
tests, 0 failures** (5 errors in `test_marketplace_capabilities`, an artifact
of copying the tree out of git, present before and after every mutation).

| mutation of the shipping function | whole suite | of which `EpgPrecisionTest` |
|---|---|---|
| `epg_name_key` loses the marker strip (`-> normalize_text`) | failures=13 | **4** |
| `_EPG_NAME_NOISE` strips any parenthetical (the F-EPG-7 loosening) | failures=3 | **3** |
| `epg_name_key` folds on `normalize_id_text` (the D-EPG-5 repair) | failures=4 | **4** |

The second and third rows are the point. **Every failure the suite produces
for either of those two changes is in the new class** -- 3 of 3 and 4 of 4 --
so before this fixture existed the F-EPG-7 loosening and the D-EPG-5 repair
could each land with the gate green and nothing saying which pairs had moved.
That is the same shape as the M4 round's blocker 2, one level up: the
milestone's headline repair was revertible with the gate green, and its
acceptance criterion was unobservable with the gate green.

The third row also means `test_the_plus_that_separates_two_channels_is_folded_away`
goes red WHEN D-EPG-5 IS FIXED, which is deliberate and is stated in its
docstring: the repair lane flips the assertion, moves the fixture's
`crossChannel` block into `unmatched`, and re-levels `status.matched` from 6
to 5. A characterisation test for an open defect is a tripwire, not a claim
that the behaviour is right.

Suite counts: python **752 tests OK** (744 -> 752).

## 8. Reproducing this

The frozen inputs live under the session scratchpad and are not committed:
`channels.json` (the installed 1,453-channel source) and `pluto-us.xml.gz`
(the project's own documented XMLTV asset, pulled 2026-10-03). With both in
place:

```
OMARCHY_IPTV_URL=<guide> bin/omarchy-iptv epg --cache-dir <fresh> --force --now 1791015219
```

reproduces `matched 227` and an `epg-now.json` byte identical to the frozen
one. The grading above is a reconstruction of the pair list from the shipping
`build_alias`, `epg_name_key` and `<display-name>` selection, checked against
`epg-now.json`'s key set; the Pluto ids are read out of `channels.json`'s own
`url` and `logo` fields and out of the guide's `<channel id=...>`.

## Repair applied, 2026-10-03

`epg_name_key` now folds on `normalize_id_text` rather than `normalize_text`.
The audit recommended it, measured its cost, and wrote the test that would go
red when it landed; this is that landing.

End to end through the shipping verb on the frozen inputs, clock pinned:

| | before | after |
|---|---|---|
| matched | 227 | **226** |
| by name | 227 | 226 |
| nameIndexed | 1,443 | **1,453** |
| nameDroppedPlaylist | 10 | **0** |
| nameDroppedGuide | 4 | 4 |

The set difference is exactly `{BloombergTV.us@US}` leaving, with nothing
joining in its place on this guide: the repair costs the one wrong pair and
nothing else. The ten channels the fold had denied are back in the index --
four News12/News12+ regional pairs and Tennis Channel 2 / Tennis Channel +2 --
and on a guide that declares them they will now match.

On the audit fixture the shape is visible in one line: the wrong Bloomberg
pair leaves and News12 Long Island arrives, so `matched` stays at six while
its membership changes. The two tests written to assert the defect were
flipped to assert the repair, and `test_nothing_matched_beyond_the_oracle`
lost its wrong-pair exemption. The returned row is declared in its own
fixture block rather than added to the oracle, because the oracle confirms a
pair by an identifier the matcher never saw and this pair has none: a row
that is right by reading must not be able to hide among rows that are right
by evidence.

Reverting the single word turns four precision checks red.

---

# Part II: an oracle that survives the matcher reading the id, 2026-10-04

Part I (sections 1-8) graded the matcher with an identifier the matcher never
read: the guide declares each channel under a 24-hex Pluto id, and the
playlist row carries that id in its own stream or logo address. F-EPG-9
recorded the obvious consequence -- that a better matching strategy is
sitting unused in the data -- and the matcher lane is now implementing it.

The moment it lands, **the oracle of Part I becomes the matcher's own
input**. Every pair matched by id would be graded "A confirmed" by
construction: a check that cannot go red, which is engineering rule 14's
exact shape and the shape that let D-GS-3 live for months. Part II builds the
replacement, states honestly how strong it is, and re-grades.

## 9. Corrections to Part I, measured

Three numbers and one attribution in Part I do not survive re-measurement on
the same frozen inputs. They are corrected here rather than quietly
overwritten.

1. **F-EPG-13: the matcher reaches 226 pairs, not 227.** Part I's headline is
   227 because it was written before its own recommended repair landed. The
   "Repair applied" note records 227 -> 226, but sections 2, 5, 6 and 7 still
   read 227 throughout, and the task brief for this round inherited 227 from
   them. Measured on the dev tip (9ae43cf) through the shipping verb:
   `matched 226, matchedById 0, matchedByFeed 0, matchedByName 226,
   nameIndexed 1453, nameDroppedPlaylist 0, nameDroppedGuide 4,
   epgChannels 226, programmeCount 2864, nowCount 226`. Read Part I's 227 as
   226 everywhere except section 3 and 3.1, which are explicitly about the
   before state. Suggested P3, documentation.
2. **F-EPG-13 (same finding): `(United States)` occurs 87 times, not 88.**
   Counted two ways over `channels.json`: `'(United States)' in name` and a
   parenthetical census that found no other spelling of it. 87 of 1,453.
   The F-EPG-7 row on the board says 88.
3. **F-EPG-13 (same finding): the Bloomberg prose is a `<programme>` `<desc>`,
   not a `<channel>` `<desc>`.** Section 3 says "the guide says so itself:
   its `<desc>` opens ...". The frozen guide declares **zero** channel-level
   `<desc>` elements; all 8,799 `<desc>` elements hang off `<programme>`. The
   quoted sentence is real and is at
   `<programme channel="54ff7ba6..." start="20261003000000 +0000">`, repeated
   in slot after slot, which is how a FAST channel describes itself. The
   substance of D-EPG-5 is unaffected -- but the location matters, because
   the grader below reads that prose, and a reader following Part I would
   look in the wrong element and conclude the signal is not there.

## 10. The grader

`scripts/dev-harness/spikes/epg-oracle/schedule_oracle.py` (dev branch).
It answers **confirmed / contradicted / unknown** for any proposed pairing of
a playlist row with a guide channel, and it reads **no id**: not the guide's
`<channel id>`, not the hex token in a stream address, not the hex token in a
logo address. `id_oracle()` is the only function in the file that touches
one, it is called only to be compared with the new grader, and no grading
path reaches it.

### 10.1 The one rule that keeps it from being a second grep

> **The name is never a confirming arm.**

Every pair the name matcher produces has equal names by construction. A
grader that confirms on name similarity therefore confirms 100% of them and
can never go red -- it would be rule 14's failure wearing a different hat.
So names drive exactly one thing here, contradiction, and confirmation comes
only from the programme schedule, which the matcher does not open.

This is not an argument, it is measured. The script carries the forbidden
grader behind `--name-oracle` so its numbers can be shown:

| grader | today's 226 | the 227 that shipped before D-EPG-5 | 65 hand-read pairings |
|---|---|---|---|
| **name equality under the matcher's own key** | **226 confirmed, 0 unknown** | **227 confirmed**, including the known-wrong Bloomberg pair | 44/44 right pairs confirmed, **0 false confirmations, 0 false contradictions** |
| **the schedule grader (default)** | 90 confirmed, 136 unknown, 0 contradicted | 90 confirmed, 136 unknown, **1 contradicted -- the Bloomberg pair** | 26/44 confirmed, 0 false confirmations, 0 false contradictions, **1 wrong pair caught** |

The forbidden grader scores a perfect 226 of 226 and a flawless zero-error
calibration. Point it at the code that actually shipped a wrong pair and it
confirms the wrong pair too (`--calibrate --name-oracle --helper <b2f944d^>`
reports `falseConfirmations: 1`, the Bloomberg row). That is what "a check
that cannot go red" looks like when you finally make it go red.

### 10.2 The arms, and why two of them are off

| arm | kind | what it reads | default | measured |
|---|---|---|---|---|
| **E1 title echo** | confirm | a programme TITLE repeats a token of our row's name that **no other guide channel's display-name uses** | **on** | 90 of 226; **0 false confirmations on 452 pairings that are wrong by construction** |
| **E3 category fit** | confirm | >=80% of the schedule's categories fit our row's group, under a table declared before measuring | **off** | +34 confirmations, but **7 false confirmations on random negatives and 28 on nearest-name negatives**, and 3 of 21 on the hand sample |
| **C1 prose marker** | contradict | a programme DESCRIPTION spells our brand with a distinguishing marker our row does not carry | on | 1 of 227 pre-repair (the Bloomberg pair), 0 of 226 today, 0 false contradictions on the hand sample |
| **C2 marker sibling** | contradict | our markers differ from the guide channel's AND the guide declares a sibling carrying ours | on | 0 of 226 today; fires 11 times on random negatives and 6 on nearest, all correct |
| **category clash** | contradict | no category of the schedule fits our group | **off** | fires twice on the 226 and **both are false** (`50 Cent Action` and `Hallmark Movies & More`, group `Movies` against categories `Entertainment/Series`) |

The two arms that are off are off because of those numbers and not because
of taste; `--category-fit` and `--strict-categories` turn them on so the
measurement is reproducible rather than asserted.

### 10.3 The threshold sweep, so E1's rarity gate is not a magic number

E1 requires the echoed token to be rare among the guide's own display-names.
How rare is a knob (`--echo-max-census`), and a second knob
(`--echo-min-tokens`) asks how many of our name's tokens must land in one
title. Both were swept against both negative sets:

| census | min tokens | E1 confirms (of 226) | E1 false confirmations, random | E1 false confirmations, nearest |
|---|---|---|---|---|
| **1** | **1** | **90** | **0** | **0** |
| 1 | 2 | 35 | 0 | 0 |
| 2 | 1 | 105 | 0 | 14 |
| 2 | 2 | 55 | 0 | 5 |
| 3 | 1 | 111 | 0 | 20 |
| 3 | 2 | 60 | 0 | 7 |
| no limit | 1 | 118 | 1 | 40 |
| no limit | 2 | 77 | 0 | 10 |

Census 1 -- "no other guide channel uses this word in its name" -- is the
only setting with zero false confirmations on the hard negatives, and it is
the default. The cost is real and is stated as a cost: census 3 would confirm
21 more pairs and buy 20 false confirmations doing it. The nearest-name
negatives it fails on are the instructive ones: `Antiques Road Trip` against
`Antiques Roadshow UK` (both schedules say "Antiques"), and
`Beverly Hillbillies` against `Beverly Hills 90210` (both say "Beverly").

## 11. What this oracle cannot see

Stated first, because an oracle whose limits are in an appendix gets quoted
without them.

1. **The stream is not in the data, so the oracle grades the LABEL and not
   the FEED.** Everything here is read from `channels.json` and the XMLTV
   file. Neither contains one byte of what the row's URL actually plays. A
   row whose name, group and brand all say "X" while its address streams Y
   is invisible to this oracle by construction. That is not a gap that
   another fixture closes; it is a live pass. **UNVERIFIED and unverifiable
   from the frozen inputs.**
2. **Two channels carrying the same playout are indistinguishable by
   schedule.** Measured rather than asserted, in 11.1.
3. **A confirmation is evidence about the brand, not about the playout.**
   F-EPG-9 (Part I, section 6.1 item 4) is exactly this: `Fox Weather` is the
   right brand and Pluto's playout of it is not the playout our URL opens.
   E1 would confirm such a pair and be right about the only thing it claims.
   **The oracle cannot grade playout identity. UNVERIFIED.**
4. **`unknown` is 136 of 226 and that is the honest figure.** It is not an
   error rate; it is the share of pairs for which these inputs hold no
   independent evidence at all. Reporting 90 confirmed where Part I reported
   226 right is not a regression in the matcher, it is the removal of
   evidence that was never independent in the first place.
5. **The hand sample is 65 pairings, read by one reader, on one day.** Its
   judgements are recorded in the script (`HAND_SAME`, `HAND_DIFFERENT`) with
   a one-line reason each, so a second reader can disagree with a specific
   row rather than with a number.

### 11.1 Simulcast clusters, measured

A schedule oracle's blind spot is two channels with one playout. The
measurement, over all 427 guide channels (every one of which carries
programmes; 8,799 in total, median about 20 per channel):

| signature | clusters | channels in one | of those, matched today |
|---|---|---|---|
| **exact** -- same (start time, title) sequence | **4** | **8** | **0** |
| **title order** -- same title sequence, times free | **5** | **10** | **2** |

The four exact clusters are three pairs of DUPLICATE declarations
(`CBS News New York`, `CBS News Los Angeles`, `CBS News Texas` -- each
declared twice under two different ids, which is also why
`nameDroppedGuide` is 4) and one genuine simulcast of two differently named
channels, `Murder, She Wrote` and `Universal Action`. **None of the eight is
matched by today's matcher**, so no pair that ships today rests on a
distinction the schedule cannot make.

The weaker signature catches one more cluster and this one matters:
`The Walking Dead en espanol` and `The Walking Dead Universe` run the same
titles in the same order at different times, and **both are matched**. For
those two pairs the title evidence is identical on either channel, so E1
confirms both and cannot say which row belongs to which. Their names do
distinguish them -- and the name is not allowed to confirm, which is the
rule paying its own cost. **Those two pairs are marked UNVERIFIED on the
question of which of the two feeds they are.**

## 12. Calibration

### 12.1 How the sample was drawn

`--sample 44` prints an **id-blind** worksheet: the strata are computed from
the oracle's own verdict, simulcast-cluster membership, whether the folded
key is a single token, and whether the key needed a marker strip -- all
features the id cannot see -- and the worksheet carries no id for the reader
to look up. Quotas are fixed in the script rather than derived from the
population, deliberately over-weighting the hard strata: every `contradicted`
pair, every `simulcast` pair, 16 `unknown`, then 8 each of `single-token`,
`marker-stripped` and `plain`. A uniform draw of 44 from 226 would have been
mostly `plain` and would have measured nothing. Seed 20261004.

That gives 44 real pairs. It cannot measure false CONFIRMATIONS, and the
reason is itself a result: **every one of the 44 reads as the same channel to
a human**, so the shipping pairing contains no negative to be wrong about.
Specificity therefore needs pairings that are wrong by construction, and the
sample adds 21:

- **20 nearest-name negatives**: each row against the guide channel whose
  name is closest to it without being its partner (`difflib`, stdlib,
  deliberately not the matcher's key). These are sibling brands and
  same-city news bulletins -- the hardest wrong pairings the data offers.
  All 20 were read, not assumed: all 20 are genuinely different channels.
  Contamination check, because a "negative" could accidentally be a true
  duplicate: **0 of 226 nearest picks is an exact-simulcast twin of the true
  partner**, and 2 are title-order twins (the Walking Dead pair, each
  other's nearest) -- both graded `unknown`, so neither touches the
  false-confirmation count.
- **1 real negative**: `BloombergTV.us@US` against the guide's
  `Bloomberg TV+`, the pairing the matcher actually made before D-EPG-5.

### 12.2 Measured error

`--calibrate` on the dev tip:

| | read as the SAME channel (44) | read as DIFFERENT channels (21) |
|---|---|---|
| grader says **confirmed** | 26 | **0 false confirmations** |
| grader says **contradicted** | **0 false contradictions** | 1 caught |
| grader says **unknown** | 18 | 20 |

And over the two constructed negative sets in full (452 pairings wrong by
construction, `--negatives`): **0 confirmed**, 17 contradicted (11 random,
6 nearest, all correct), 435 unknown. **False confirmation rate 0.0000 on
both sets.**

With `--category-fit` on, the same calibration reports **3 false
confirmations of 21** for 7 more right pairs confirmed -- consistent with the
7/28 on the constructed sets, and the reason that arm is off.

The shape of the error is the honest headline: **this oracle's cost is
silence, not wrongness.** It says nothing about 18 of 44 pairs a human can
read correctly, and in 517 graded pairings across every set it never once
confirmed a pairing a human called wrong.

### 12.3 Every arm seen red (rule 11)

A grader nobody has broken is decoration. Three named mutations, each
disabling exactly one arm of `grade_pair`, each run against the whole set of
measurements:

| grader | `--calibrate` false confirmations | wrong pair caught | `--grade` on the pre-D-EPG-5 helper | `--negatives` contradictions (random / nearest) |
|---|---|---|---|---|
| **as written** | **0** of 21 | **1** | 90 confirmed, 136 unknown, **1 contradicted** | 11 / 6 |
| **M-G1** -- prose-marker arm disabled | **1** | **0** | **91 confirmed, 0 contradicted** | 11 / 6 |
| **M-G2** -- marker-sibling arm disabled | 0 | 1 | 90 / 136 / 1 | **0 / 0** |
| **M-G3** -- title-echo arm disabled | 0 | 1 | **0 confirmed**, 227 unknown | 11 / 6 |

M-G1 is the row that matters. Remove the arm that reads the guide's own prose
and the grader does not merely fall silent on the Bloomberg pair -- it
**confirms** it, because the channel's titles do repeat the word "Bloomberg".
So the arm is not a decoration on top of a safe default; it is the only thing
standing between this grader and a false confirmation on the one pairing the
matcher is known to have got wrong. M-G2 shows the sibling arm is the whole
of the grader's sensitivity on constructed negatives, and M-G3 shows
title-echo is the whole of its coverage.

## 13. The re-grade of today's 226

| | pairs | schedule: confirmed | contradicted | unknown |
|---|---|---|---|---|
| **what ships today (9ae43cf)** | **226** | **90** | **0** | **136** |
| the 227 that shipped before D-EPG-5 | 227 | 90 | **1** | 136 |

Against the id oracle of Part I, on the same 226 pairs:

| | id: A confirmed | id: B not contradicted | id: C contradicted | id: D no identifier |
|---|---|---|---|---|
| schedule: **confirmed** | 48 | 7 | 0 | **35** |
| schedule: **unknown** | 105 | 2 | 0 | 29 |
| schedule: contradicted | 0 | 0 | 0 | 0 |

Three numbers in that table are the whole answer to "where do the two
graders disagree".

1. **42 pairs are confirmed by the schedule and NOT by the id** (7 B + 35
   D). The schedule oracle is not a weaker copy of the id oracle; it reaches
   into the classes where the id oracle is blind by definition. 35 of them
   are rows that do not stream from Pluto at all, which no amount of
   id-reading will ever grade.
2. **105 pairs are confirmed by the id and not by the schedule.** The id
   oracle is the stronger of the two where it applies, and nothing here
   argues otherwise -- but it is the one that stops being independent
   tomorrow.
3. **F-EPG-12: 31 pairs are confirmed by NEITHER oracle** (2 unknown/B + 29
   unknown/D). These have no independent evidence in the frozen inputs at
   all. Part I graded all 31 "obviously right" by reading the name and the
   programme; that reading is a human's, it is not recorded per-row, and it
   is not reproducible. This is the project's real blind spot on EPG
   precision and it has never been stated as a number. Suggested P3.

Where the two oracles **contradict** each other: nowhere on today's 226.
Where they disagree on the one known-wrong pair, the schedule oracle is
right and the id oracle is blind: the Bloomberg pair is graded **D, no
identifier** by the id oracle -- its row carries no Pluto token -- and
**contradicted** by the schedule oracle, from the guide's own prose. D-EPG-5
was found by a human reading that prose; it is now found by a script.

## 14. The three open findings, settled with numbers

### 14.1 F-EPG-7: is the one contradicted pair real?

**Under this oracle, no -- and under the id oracle it is not established
either.** Measured, by re-running the whole pipeline with
`_EPG_NAME_NOISE` loosened to strip any parenthetical (a named mutation of
the shipping function, graded through `--helper`):

| | pairs | id A | id B | id **C** | id D | schedule confirmed | schedule **contradicted** |
|---|---|---|---|---|---|---|---|
| today | 226 | 153 | 9 | **0** | 64 | 90 | **0** |
| strip any parenthetical | **255** | 180 | 9 | **1** | 65 | 104 | **0** |

The loosening adds 29 pairs (26 id-A, 2 id-D, 1 id-C), which is Part I's
"+27 confirmed" plus the two it did not count. The schedule oracle confirms
14 more and **contradicts none of the 29**, including the C pair.

Then the C pair itself, which is the entire measured cost of the loosening:

- The row is `Pluto TV Reality (United States)`. Its **stream** address
  carries a token the guide declares as **`Pluto TV Pride`**. Its **logo**
  address carries a **different** token, which this guide does not declare
  at all. So the row's two identifiers disagree, and the grade depends on
  which one you read: **C by the stream, B by the logo.**
- That is not a one-off. `--id-split` measures it: of the 1,453 playlist
  rows, **105 carry a 24-hex token in both the stream and the logo address,
  and on 47 of them the two tokens are different channels** -- 45%. On the
  226 shipping pairs, 79 carry both and **32 disagree**. On the 255-pair
  loosened run, 96 carry both and 43 disagree.
(Note on the id: this finding was written as F-EPG-11 by the lane that found
it, on the same day the matcher lane coined F-EPG-11 for the address strategy
itself. Two lanes, one afternoon, one number -- the join-by-name failure rule
13 names, arriving by the one route the ledger cannot catch, because neither
id existed in a tracked document while either lane was working. The lead gave
this one F-EPG-14 at integration, the matcher's keeps F-EPG-11 because it is
embedded in shipped code comments and test names, and the next round that
spawns parallel lanes hands each a reserved block of ids.)

- **F-EPG-14: "the playlist row already carries that id" is two oracles, not
  one, and they disagree 45% of the time where both exist.** Part I's grade
  table reads the stream first and the logo only as a fallback, which is a
  choice no sentence in Part I defends. Every C grade, and therefore the
  whole stated cost of the F-EPG-7 loosening, rests on that choice.
  Suggested P2 -- it is the evidence base of an open product-owner decision.
- What would settle it: opening that one row and seeing whether Pride or
  Reality plays. A live pass, the same answer F-EPG-9 needs. **Until then
  the cost of the F-EPG-7 loosening is UNVERIFIED, not 1.**

The audit's position is unchanged in direction and weaker in confidence
than Part I's: 27 oracle-confirmed and 14 schedule-confirmed pairs against
one pair whose wrongness cannot currently be established either way.

### 14.2 F-EPG-8: is the Tennis Channel pair the same channel?

**The schedule says it is a tennis channel and refuses to say which of three
rows it is, and the obvious fix gets it wrong.** The numbers:

- The guide declares **exactly one** channel whose name contains "tennis":
  `TennisChannel 2`. Its whole published schedule is six programmes --
  `Tennis Today`, three `Tennis Today Live`, two `Day 1` -- so E1 confirms
  the brand (the token `tennis` appears in no other guide display-name,
  census 1).
- The playlist carries **three** tennis rows: `Tennis Channel (1080p)`,
  `Tennis Channel 2 (1080p)`, `Tennis Channel +2 (720p)`. Only the `+2` row
  carries a Pluto token at all, and it is the guide's.
- One guide schedule against three candidate rows means a schedule oracle
  has nothing to choose with. **UNVERIFIED on which row, by this oracle.**
- The obvious name fix is worse than nothing. A named mutation that collapses
  every space in `epg_name_key` (so `tennischannel2` joins `tennis channel
  2`) adds 4 pairs -- `Estrella TV`, `News12 New York`, `Newsmax 2` and
  **`Tennis Channel 2 (1080p)` -> `TennisChannel 2`**. It hands the guide
  channel to the row that carries **no** id while the row that carries the
  guide's **own** id stays blank. The schedule oracle confirms it (it is a
  tennis channel) and is right about the only thing it claims; the id says
  the pairing is on the wrong one of two rows. So F-EPG-8 stays recorded and
  not fixed, and the reason is now a measurement: **any space-insensitive
  key resolves this 1-in-2 the wrong way on these inputs.** It is reachable
  only by the id, which is the matcher lane's work, not a name rule.

### 14.3 F-EPG-10: does any guide declaration carry a bracket span?

**No, and removing the branch costs exactly zero pairs.**

- Playlist names carrying `[...]`: **142 of 1,453** (`[Not 24/7]` 82,
  `[Geo-blocked]` 60, and nothing else).
- Guide display-names carrying `[...]`: **0 of 427** counting only the first
  declaration, and **0** counting every `<display-name>` of every channel.
- A named mutation of the shipping function that deletes the `\[[^\]]*\]`
  alternative from `_EPG_NAME_NOISE` entirely produces **226 pairs, the same
  226 pairs** -- the pairing sets are identical, the set difference is empty
  in both directions, and the grade distribution is unchanged (90 confirmed,
  136 unknown, 0 contradicted; id 153 A / 9 B / 64 D). So the branch's
  contribution on these inputs is zero in both directions: it is needed by
  no pair and it breaks no pair.
- What WOULD exercise it: a guide that writes a bracket span in a
  display-name. Nothing in the project's documented XMLTV assets does. The
  branch is reachable only through the playlist side, where it strips 142
  names, and the risk Part I described is intact -- the branch discards
  content it has not inspected, so a guide writing `Channel [East]` against
  our `Channel [West]` would be married with no evidence either way, and the
  C2 marker-sibling arm above would NOT catch it because `east`/`west`
  inside brackets are stripped before the marker set is read.
- The repair Part I suggested -- narrow the pattern to the two markers that
  occur -- is now measured at **zero cost** on the frozen inputs. That is a
  product-owner decision with no downside in the data, like D-EPG-5's.

## 15. Findings this part files

Each gets its id on the day it is written (rule 13). **This lane does not own
`docs/STATUS.md`**, so the rows are handed to the lead and
`scripts/check-defect-ledger.py` reports exactly three problems against this
branch until they land. Dropping the ids to make the gate green is the
D-REL-3 failure and is not on the table.

1. **F-EPG-14: the id oracle is two oracles and they disagree 45% of the
   time.** 105 of 1,453 rows carry a 24-hex token in both the stream and the
   logo address; on 47 of them the two name different channels. Part I's
   grading reads the stream first and the logo as a fallback without saying
   so, and the single C grade that is the whole measured cost of the F-EPG-7
   loosening is C by the stream and B by the logo. Suggested P2: it is the
   evidence base of an open decision. Section 14.1.
2. **F-EPG-12: 31 of the 226 shipping pairs are confirmed by no oracle at
   all.** 2 have an id this guide does not declare, 29 have no id; and the
   schedule says nothing about any of them. Part I graded them right by a
   human reading that was not recorded per row. This is the project's actual
   residual on EPG precision and it has never been a number. Suggested P3.
   Section 13.
3. **F-EPG-13: three numbers and one element name in Part I do not survive
   re-measurement.** 227 is 226 after Part I's own repair landed; 88 is 87;
   and the Bloomberg prose is a `<programme>` `<desc>` in a guide that
   declares no channel-level `<desc>` at all. The first of these propagated
   into the task brief for this round. Suggested P3, documentation.
   Section 9.

```
| F-EPG-14 | P2 | M4-01 | docs/QA-EPG-PRECISION.md 14.1 and 15 (frozen inputs, --id-split) | open |
| F-EPG-12 | P3 | M4-01 | docs/QA-EPG-PRECISION.md 13 and 15 | open |
| F-EPG-13 | P3 | M4-01 | docs/QA-EPG-PRECISION.md 9 and 15 | open, documentation |
```

## 16. How to run it

The frozen inputs are not committed: `channels.json` (the owner's parsed
1,453-channel source) and `pluto-us.xml.gz` (the project's documented XMLTV
asset, pulled 2026-10-03). With both in place, from a worktree root:

```
F=<directory holding channels.json and pluto-us.xml.gz>
S=scripts/dev-harness/spikes/epg-oracle/schedule_oracle.py

# 1. reconstruct the shipping pairing and PROVE the reconstruction at the sink
mkdir -p /tmp/c && cp $F/channels.json /tmp/c/
OMARCHY_IPTV_URL="file://$F/pluto-us.xml.gz" \
  python3 bin/omarchy-iptv epg --cache-dir /tmp/c --force --now 1791015219
python3 $S --channels $F/channels.json --guide $F/pluto-us.xml.gz \
  --pairs --now-json /tmp/c/epg-now.json      # sinkCheckPassed: true

# 2. grade it
python3 $S --channels $F/channels.json --guide $F/pluto-us.xml.gz --grade

# 3. grade the grader
python3 $S --channels $F/channels.json --guide $F/pluto-us.xml.gz --calibrate
python3 $S --channels $F/channels.json --guide $F/pluto-us.xml.gz --negatives

# 4. the limits, the clusters, the three findings, the old oracle's self-audit
python3 $S --channels $F/channels.json --guide $F/pluto-us.xml.gz --clusters
python3 $S --channels $F/channels.json --guide $F/pluto-us.xml.gz --findings
python3 $S --channels $F/channels.json --guide $F/pluto-us.xml.gz --id-split
```

**Pointing it at the NEW matcher.** Two ways, and the first is better because
it needs nothing from this lane:

```
# the matcher as a whole, from any revision of the helper
git show <rev>:bin/omarchy-iptv > /tmp/helper-new.py
python3 $S --helper /tmp/helper-new.py --channels $F/channels.json \
  --guide $F/pluto-us.xml.gz --grade
python3 $S --helper /tmp/helper-new.py --channels $F/channels.json \
  --guide $F/pluto-us.xml.gz --calibrate

# or a pairing the new matcher emits, as JSON {"pairs": [[tvgId, guideCid], ...]}
python3 $S --channels $F/channels.json --guide $F/pluto-us.xml.gz \
  --grade --pairings /tmp/new-pairs.json
```

`--helper` reconstructs that helper's pairing by calling ITS `build_alias`,
`epg_name_key`, `match_xmltv_channel` and `claim_channel` (rule 12: the
grader never restates the matcher's logic), so an id-matching matcher is
graded exactly like a name-matching one. The reconstruction replays only
`parse_xmltv`'s bookkeeping around those calls, and `--pairs --now-json`
proves the replay against the shipping `epg-now.json`: same 226 keys, same
programme title on every one.

What the lead gets from running `--grade` on the new matcher that he cannot
get from the id oracle: a `contradicted` count that is **still able to be
nonzero** after the matcher reads the id, because no arm of this grader reads
one. Expect `matchedById` to rise and the schedule oracle's `confirmed` to
stay near 90 and its `contradicted` to stay at 0; a `contradicted` above zero
is the pair to look at, and `--grade --dump` names it.

**Budget (rule 7).** This part changed no shipping code -- `git diff 9ae43cf`
on the branch touches only the new spike -- so the helper's budgets cannot
have moved, and the figure is reported rather than assumed: the shipping
`playlist` verb parses a synthetic 10,000-channel list in **549, 558, 559 and
569 ms** over four runs on this machine, against the 1-second budget, and the
frozen `epg` run reports `durationMs 566`. The grader itself is not shipped
and runs the whole 226-pair grade in 0.72 s.
