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
