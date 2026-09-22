# The guide at real provider scale: design (M2-09)

Owner: UI/UX. Status: v1.0, the design to be built. Governs the M2-09 lane.
Binding input: `docs/M2-09-GUIDE-AT-SCALE.md`. Where this document and UX.md
disagree, the open questions at the end are the decision requests; nothing
here is resolved silently.

All figures below were re-measured read-only against the shipping `Model.js`
and `Guide.qml` at v0.5.0, the subscriber's real playlists, the public
caches, and the live install's own cache at
`~/.cache/omarchy-iptv/sources/d5977d8a`. Every pixel figure is for this
machine's real configuration: eDP-1 1366x768 @1, `Style.gapsOut` 5,
`base-size 12`, spacing scale 1.0 (so `Style.space(px) == px`), `monospace`
resolving to JetBrainsMono Nerd Font at a uniform 0.600 em advance.
The rendered separator is `Model.SEP`; this document writes it ` - ` the way
`docs/UX.md` does.

---

## 1. The decision, and why

Four designs were produced independently and each was walked by three
judges: is it faster, is it learnable, is it buildable. Across twelve
judgements only three cleared the bar and twenty-six findings were rated
fatal. The decision below is built out of what survived that, not out of
what read well.

**Three things the judges agreed on, unanimously or near enough:**

1. **The single best idea in the whole batch is not an addition.** All four
   designs, independently, arrived at porting `revealCursor` from Omarchy's
   own canonical picker (`/usr/share/omarchy/shell/plugins/menu/Menu.qml`
   :640-661) into the guide's `scrollToCursor` (`Guide.qml:652-654`). Nine
   of twelve judgements named it "bestIdea" or "graft unconditionally". It
   is fifteen lines, zero pixels, zero budget, house code, with the defect
   named verbatim in the house comment: *"Contain alone parks the cursor row
   flush with the viewport edge, hiding the neighbor entirely and losing the
   fold affordance."* The guide has exactly the bare
   `positionViewAtIndex(..., ListView.Contain)` that comment warns against,
   in two places.

2. **The one measurable keystroke win is a deletion.** On the subscriber's
   3,335-channel list the row's second line renders one distinct string
   across all 3,335 rows. I confirmed it: distinct `Model.rowDetail` values
   at scope All are 1 on `USChannels` (`["United States"]`), 1 on `Kids`
   (`["US Kids"]`), 2 on `SportsPPVAll`, 28 on public-US, 30 on
   public-everything. Deleting a line that carries zero bits takes
   `rowHeight` from `detailRowHeight` 52 to `singleRowHeight` 38
   (`Guide.qml:234-236`), 9 visible rows to 12 (+33%), `pageSize()` 8 to 11,
   and the walk across 3,335 rows from 417 PageDowns to 304 (-27%). It costs
   no pixels, no key, no new component, and it is the only change any judge
   scored as reducing keypresses at zero cost.

3. **The change all four designs converged on -- moving the repeated
   bracketed prefix out of the scan line -- is a measured regression on the
   primary task, and every judge who tested it found the same thing.** The
   prefix is not dead text. I re-ran it: the subscriber's list has 2,410
   rows (72.3%) opening with a bracketed run, across **16 distinct tokens**,
   not one; 2,227 share the seven characters `(PLUTO ` and then diverge into
   eleven countries. Strip or demote the run and 1,092 of 3,335 rows collide
   on their remaining stem. Browsing hides this; search concentrates it.
   Against the shipping `filterChannels`: `ufc` returns 10 rows, **1
   distinct stem**; `fifa` 10 rows, **1 distinct stem**; `one piece` 5 rows,
   **1 distinct stem**. Today those rows are separable at the first glyph.
   After the change every visible row reads the same word and the only
   discriminator sits hundreds of pixels right, at `Style.font.bodySmall`
   and opacity 0.52. The product owner's own framing ("2,217 names begin
   with the same bracketed token") invites the one fix the data forbids.

**Two things the judges found that changed the shape of the design:**

4. **Every design that touched row height broke the failed-channel notice,
   and none of them noticed.** `detailText.visible` binds `rowsHaveDetail`
   (`Guide.qml:2390`, `:362`), and `Model.rowDetail` (`Model.js:3871-3884`)
   is the only place `Failed HH:MM - Space to retry` is built. UX.md:181,
   UX.md:739 and ruling 9 (UX.md:896) all mandate that string, and UX 7.2
   requires the glyph and the words together. Suppress the detail line and
   the retry affordance disappears; keep a failure term in the predicate and
   the first dead stream re-heights 3,335 rows under the cursor, mid-session,
   with no user action. **This design takes neither horn.** The failure
   notice moves to the row's right meta slot on single-line rows -- a slot
   `Guide.qml:2338` already blanks on failure, so it is free exactly when it
   is needed. `rowsHaveDetail` then loses its failure term entirely and
   `anyFailedInScope` (`Guide.qml:365-374`, a loop stranded in QML) is
   deleted. Row height becomes a pure function of scope kind, group axis and
   EPG: stable for the whole session, in every shape, better than today.

5. **Hiding the group column is not licensed by the argument that justifies
   it.** The argument is that the lone group entry duplicates All -- and it
   does: `Model.channelsForScope(ch, "g:United States")` is element-for-
   element `channelsForScope(ch, "all")`, verified. But `columnHost`
   (`Guide.qml:2031`) also carries Recent, Favorites and the pinned Sources
   button, none of which claim anything about groups, and `moveScopeBy`
   still drives them. Hiding it costs mouse users every pointer route to
   those scopes, costs screen-reader users the `accessibleGroups` list and
   `sourcesRowAccessibleName`, contradicts UX 1.3 principle 3, and buys 219
   px of width that measurement says is worthless: **0 of 3,335 subscriber
   names elide at the current 627 px name slot, and 0 elide at 846 px.**
   Width is not the scarce resource. Height and keystrokes are.

**Therefore.** This lane ships five changes, four of them deletions or
reuses of code that already exists, and refuses the row-prefix treatment
with the search-collision numbers attached. It answers problem 1 by making
the column stop claiming a narrowing step it does not provide, problem 2
with a number in a slot that already holds a number plus the house fold
affordance, and problem 3 by the only means the data permits -- giving each
row more of the screen rather than rearranging what is on it.

It does **not** make a 2,693-channel group faster to page. That is stated
plainly here and raised as open question 7, because the honest answer to it
is a second navigation axis, which the scope doc excludes.

---

## 2. Approaches considered

| Approach | Verdict | Grafted | Left behind, and why |
|---|---|---|---|
| **Subtract** ("Earn or Yield") -- one predicate, `groupChannels(list).length >= 2`, gates the column, the detail line and the h/l ring; prefix moves to a 99 px right gutter; header count becomes a ruler | Cleared 1 of 3 lenses, 7 fatal findings. Best-measured submission in the batch; almost every number reproduced exactly | **The gate itself**, which is the spine of this design: one measured fact deciding whether the group axis narrows anything, provably equivalent to "every group is a strict subset of All" because `groupChannels` never emits an empty group. **The detail-line deletion.** **The header count becoming a position.** Its deep-link analysis, which found that `Model.fallbackScope` (`Model.js:1325-1337`) sends a vanished group scope to Favorites, not All | The 99 px tag gutter (search collapses 41% of tagged rows onto identical left edges); hiding the whole column (takes Favorites, Recent and Sources with it); the fixed pixel gutter (`chars * 6.59375` is a literal in a tokens-only repo) |
| **Open** ("Tag, not prefix") -- keep the column, suppress the zero-information detail line, delete the duplicate column entry, port `revealCursor`, put position only in the accessible name | Cleared 1 of 3, 7 fatal | **D4, the `revealCursor` port**, which every judge on every lane named as the thing to take first. **D3, dropping the duplicate column entry while keeping the column** -- the correct, narrow reading of the redundancy argument, and this design's largest single correction to Subtract. **D5, `row N of M` in `Model.rowAccessibleName`** (`Model.js:3889-3897` announces no index today, so a screen-reader user is told strictly less than the eye). And its **negative result on width**, which killed the "reclaim a fifth of the card" direction outright | D1, the tag slot (same collision evidence); its predicate `groupCount > 1` as written, which flips in both directions and would put a blank 14 px line on every row inside every group of a well-grouped playlist |
| **Adaptive** ("Fit to Shape") -- one probe, three latched verdicts, a new `g` key, a proportional rail | Cleared 1 of 3, 9 fatal | **Its three governing rules, adopted verbatim as section 3.1 of this design**: keys never adapt, adaptation only subtracts, and the shape latches and never moves under the user's hands. **Its measurement of the column's own position problem** -- 32 entries in a 469 px / 14-entry viewport with no scrollbar anywhere in `Guide.qml`, `General (275)` at column row 21, 18 `l` presses from All -- which is why `positionColumn` gets the peek too, not just `scrollToCursor`. **Its identification of `anyFailedInScope` as the hazard** | The `g` key (`groupModel` and `moveScope` read one `scopeList` array, so `g` reveals either an empty column or an entry the keyboard cannot reach); the rail (see section 5.4); the strided-sample prefix probe |
| **Search-first** ("Confirmation Surface") -- land on Recent, make the first keystroke narrow by matching name-only, suppress the constant detail line, lead the row with the stem | Cleared 0 of 3, 10 fatal | **Its negative results, which are the most valuable output of the whole batch and are banked here so nobody re-spends the day**: four alternative rankers (stem-start tier, tier-3 suppression, shortest-name-first, all three) moved the median keystrokes-to-target by **zero** -- ranking is not the lever; and search is already good on real intent words (`espn` 8 matches, `hbo` 10, `nfl` 6, `cartoon` 3, right answer in the top three every time). **Its refusal to add a teaching hint**, measured rather than asserted | C-1 (landing on Recent): a 2-press swap, a no-op on the subscriber's own playlists because their channel ids do not resolve against stored recents, and it contradicts UX 1.3 principle 2. C-2 (group-blind matching): measured **inert** -- `filterChannels` drains tier-3 buckets last (`Model.js:1128-1140`), so removing group-only matches can never promote anything; roughly 15,000 probes changed the target's position zero times |

Nothing a loser got right is dropped. The three items above that no design
proposed -- the meta-slot failure notice, the `scopeSurface` single-pass
constraint, and the refusal of the rail on thumb-size grounds -- come from
the judges' fatal findings and are marked as such where they appear.

---

## 3. The design

### 3.1 Governing rules

Adopted from the Adaptive submission, which stated them better than I would
have, and they are what make a surface that varies with its data learnable.

- **R-A. Keys never adapt.** `j k h l Enter Space f s r p / o Tab Esc
  PgUp PgDn Home End Delete` and the `0-9 . ,` number machine do exactly the
  same thing on every playlist. This lane adds no key, removes no key,
  rebinds no key, and introduces no Ctrl chord. The two-mode model (UX 3,
  R1) is untouched. Only which keys the footer *advertises*, and what verb
  it uses for one of them, varies -- which is already true today for
  `0-9 channel` and `p pip`, with the codebase's own justification at
  `Model.js:4096-4099`.
- **R-B. Adaptation only ever subtracts, and it only subtracts what is
  provably empty.** A user who learned the many-groups surface finds the
  one-group surface to be a strict subset of it. Nothing appears on a
  degenerate playlist that a rich one would not also have shown.
- **R-C. The shape is decided before the first frame and never moves under
  the user's hands.** The group axis is measured in `rebuildGroups()`, which
  `rebuildDisplay()` calls first and which `open()` calls before the card is
  composed. A refresh that lands while the guide is open updates rows, never
  geometry. No layout element appears, vanishes or changes height while
  someone is looking at it -- and after the change in 3.5, that is true of a
  playback failure too, which is *not* true today.

### 3.2 What is on screen

Five changes. Four are deletions or reuses.

**D1 -- The group axis is measured once, from data the guide already
computes.**

`Model.scopeSurface(channels, state)` returns `{ entries, axis }` in a
single pass. `axis` is `{ count, narrows, soleGroup }`, where
`narrows === (count >= 2)`. `Model.scopeEntries` becomes a thin wrapper
(`scopeSurface(...).entries`) so its eight existing callers and tests keep
passing byte-identically.

This is one function because it must be. `scopeEntries` already calls
`groupChannels` internally, and `groupChannels` is not cheap at scale: node
median of 25 runs gives 2.63 ms at 3,335 channels, 10.30 ms at 11,039, and
**37.33 ms at 50,000** (`Model.MAX_CHANNELS`), with `scopeEntries` itself at
17.71 ms on the 11,039 list. A second independent pass over the channel
array to answer "how many groups" would roughly double that on a path the
150 ms open budget already runs. `rebuildGroups()` (`Guide.qml:555-580`)
guards on `groupsDirty` and caches `scopeList`, so this runs once per
channel-set change and never on a keystroke.

Measured verdict on every real shape: subscriber US 3,335/1 group ->
`narrows: false`; subscriber Kids 48/1 -> false; subscriber sports 1,833/2
(1,000 and 833) -> true; public US 1,472/28 -> true; public everything
11,039/30 -> true; live cache 1,472/28 -> true. A playlist with no
`group-title` at all collapses to one synthesised `Ungrouped` group
(`Model.js:1188`) and is caught without a special case.

**D2 -- The column keeps its width and its job; it loses only the entry that
lies.**

When `axis.narrows` is false, `scopeSurface` omits the `GROUPS` header and
the single group entry. Everything else in `columnHost` stays exactly as it
is: the same 219 px (`columnWidth` 200 + `normalBorderWidth` 1 +
`contentMargin` 18), the same Recent / Favorites / All block, the same
pinned Sources button, the same click targets, the same accessibility tree.
`listHost.width` (`Guide.qml:2220`) does not change. Nothing is reclaimed,
because measurement says there is nothing to reclaim.

Measured consequence on the subscriber's list: `scopeEntries` goes from
`[Favorites 0, All 3,335, GROUPS, United States 3,335]` to
`[Favorites 0, All 3,335]`, and the `h`/`l` ring from
`["favorites", "all", "g:United States"]` to `["favorites", "all"]`. The
removed stop provably returned an element-identical array to All and cost a
synchronous full `rebuildDisplay` to produce a list already on screen.

A deep link or IPC payload naming that group must not fall through
`Model.fallbackScope`, which returns `favorites > 0 ? SCOPE_FAVORITES :
SCOPE_ALL` (`Model.js:1325-1337`) and would land a subscriber with one
favourite in a one-row list when they asked for three thousand. New pure
function: `Model.requestedScope(entries, scopeId, axis)` returns `SCOPE_ALL`
when the requested scope is a group scope, `axis.narrows` is false, and
`scopeName(scopeId) === axis.soleGroup`; otherwise it defers to
`fallbackScope` unchanged. This was found by a judge as a false safety proof
in the Subtract submission and is repaired here rather than inherited.

**D3 -- Rows are single-line wherever the group line would be a constant.**

Lifted out of QML per CLAUDE.md rule 12:

```
Model.rowsHaveDetail({ scopeIsGroup, groupsNarrow, epgConfigured })
  === (!scopeIsGroup && groupsNarrow) || epgConfigured

Model.rowShowsGroup({ scopeIsGroup, groupsNarrow })
  === !scopeIsGroup && groupsNarrow
```

`Guide.qml:362` and `Guide.qml:2250` become one-line calls into these.
This is UX 2.4 applied, not amended: the rule already says two-line rows
apply "whenever the detail line has content for this list ... a mixed list
such as Recent / Favorites / All / search results **where the group name is
meaningful**". On a playlist whose 3,335 rows all read `United States` it is
not meaningful.

The predicate **strictly dominates** today's `!scopeIsGroup`. Truth table
over every reachable combination:

| Scope | `groupsNarrow` | EPG | Today | This design |
|---|---|---|---|---|
| All / Recent / Favorites, one-group playlist | false | off | 52 px | **38 px** |
| All / Recent / Favorites, multi-group playlist | true | off | 52 px | 52 px |
| Inside a group, multi-group playlist | n/a (`scopeIsGroup`) | off | 38 px | 38 px |
| Any scope, EPG configured | any | on | 52 px | 52 px |

One cell changes. No shape loses a row.

**D4 -- The failure notice moves to whichever line the row has.**

This is the repair for the fatal flaw all three judge panels found, and it
is the only part of this design that no submission proposed.

The row's right meta slot (`Guide.qml:2333-2350`) renders `until HH:MM`,
and its text binding already evaluates to `""` when `row.failedAt !== ""` --
the slot is deliberately empty on a failed row. So:

```
meta.text:  row.failedAt !== "" && !root.rowsHaveDetail
              ? Model.rowFailedMeta(row.failedAt)
              : (row.until !== "" && row.failedAt === "" ? "until " + row.until : "")
```

with `Model.rowFailedMeta(at)` returning `"Failed " + at + SEP + "Space to
retry"` -- the exact words `rowDetail` already builds, from one shared
constant. The natural-width, no-`implicitWidth`-binding construction of the
meta slot is preserved verbatim (the D-LIVE-01 hazard note at
`Guide.qml:2341-2344` still applies and is still obeyed).

Two consequences, both good:

- The mandated string and the alert glyph survive together, on both row
  heights, satisfying UX.md:181, UX.md:739, ruling 9 and UX 7.2.
- `rowsHaveDetail` no longer has a failure term, so **`anyFailedInScope`
  (`Guide.qml:365-374`) is deleted**: 10 lines of stranded QML logic and a
  loop over the failed map on every binding evaluation, gone. Row height
  stops depending on session-mutable state. This removes a mid-session
  re-height that **ships today** inside every group scope -- one dead stream
  currently takes a group's rows from 38 px to 9-visible 52 px with no user
  action.

Cost, measured: the notice is 29 characters at `Style.font.caption` 10 =
174 px, leaving the name slot 445 px = 53 characters at `Style.font.title`
14 on the failed row only. 16 of 3,335 subscriber names, 47 of 1,472
public-US names and 320 of 1,833 sports names are longer than that and would
elide **on a row that has actually failed**. That is the whole price, and it
is smaller than either alternative.

**D5 -- The fold peeks, and the header counts.**

*The peek.* `Model.revealOffset({ itemY, itemHeight, contentY,
viewportHeight, originY, contentHeight, peek, index, count })` returns the
new `contentY`. Pure arithmetic, node-testable, lifted out of QML rather
than the verbatim port three submissions proposed (a judge was right that
copying Menu.qml's fifteen lines into `Guide.qml` is precisely the stranded
interface logic rule 12 forbids; Menu.qml is Omarchy's file and not bound by
this repo's rule, the copy would be).

`scrollToCursor` (`Guide.qml:652-654`) and the `Contain` branch of
`positionColumn` (`Guide.qml:644-650`) call `positionViewAtIndex(...,
Contain)` as today, then assign `Model.revealOffset(...)`. `peek` is
`Math.round(rowHeight * 0.55)` for the list -- 21 px at 38 px rows, 29 px at
52 -- and `Math.round(groupEntryHeight * 0.55)` = 18 px for the column,
matching `Menu.qml:106`. Unconditional: every playlist shape, both lists.
The `positionViewAtBeginning()` branch for pinned scopes is untouched.

It lands exactly right against `pageSize()`: at 38 px rows `pageSize()` is
11 and 12 rows fit, so with the peek 11 rows are fully visible and the 12th
is the clipped bridge. A PageDown advances precisely one screenful of
readable rows and the partial row is the seam, not a duplicated overlap.

The existing 28 px edge scrims (`Guide.qml:2516-2546`) carry direction and
already track hidden distance. They do not carry magnitude and they never
will; at 38 px rows a flush-parked cursor row would sit 74% inside the
bottom scrim, which is the other reason the peek is not optional.

*The count.* `Model.scopeLabel` gains the cursor's position when, and only
when, the list is longer than the viewport -- the scrollbar condition, which
needs no learning and is exactly when the scrims are live:

| State | Header right slot |
|---|---|
| No query, list fits | `Favorites - 6 channels` (unchanged) |
| No query, list overflows | `All - 1,204 of 3,335` |
| Query, results fit | `in All - 8 matches` (unchanged) |
| Query, results overflow | `in All - 14 of 200` |

One rule: **when the list is longer than the viewport, the count becomes a
position, and the noun goes away.** The noun's presence is what tells you
which form you are reading. The first number is the 1-based cursor row,
never the viewport -- the cursor is what the keyboard moves, and binding a
Flickable's `contentY` into a Model call would put string formatting on
every frame of a wheel flick.

Width, measured at the caption-10 advance of 6.0 px/char:
`All - 3,335 channels` is 20 chars / 120 px and `All - 1,204 of 3,335` is 20
chars / 120 px -- identical. `All - 1 of 3,335` is 16 / 96, so the label's
left edge moves by up to 24 px across the cursor's travel (30 px under a
query, `in All - 8 matches` 108 px to `in All - 3 of 8 matches` 138 px).
`searchLine` and `headerTitle` anchor their right edge to `scopeLabel.left`
(`Guide.qml:1927`, `:1947`), so that reflow is real in layout and invisible
on screen: both are left-anchored and elide right, and the query would have
to reach roughly 80 characters before the clipping point mattered. To bound
it against a pathological theme, `scopeLabel` gains
`width: Math.min(implicitWidth, parent.width * 0.42)` and
`elide: Text.ElideLeft` -- eliding left so the numbers, which are the
changing part, survive and the scope name, which the column also shows, is
what gives way.

Under a query the footer keeps `First 200 of 2,227 - keep typing`
(`Model.js:4050`) and the header says `in All - 14 of 200`. Two different
true facts: how far into the listed rows you are, and how many matched. The
position goes in the header and never in the footer, because
`Model.footerStatus` (`Model.js:4037-4057`) is a ten-rung priority ladder in
which `playingName` outranks the counts -- so while something is playing,
which is the most common reason to open the guide, that slot already reads
`{U+F040A} (PLUTO USA) Comedy Central - s stop` -- and because the list-mode
hint line already measures 114 chars / 684 px against a
`parent.width * 0.7` = 644 px cap and already elides `j/k move` off its
left.

**D6 -- The footer stops advertising an axis that is not there.**

`Model.footerHints` gains a gated flag the way `hasNumbers` and
`pipAvailable` are gated. When the ring holds only pinned entries, the
list-mode pair `["h/l", "group"]` becomes `["h/l", "scope"]` and the
search-mode-no-query pair `["Left/Right", "group"]` (`Model.js`, the final
return) becomes `["Left/Right", "scope"]`. The pair is never dropped,
because the key still does something real -- it rings Recent / Favorites /
All. `scope` and `group` are both five characters, so the 684 px hint line
does not change width by a single pixel. The search-mode-with-query branch
already reads `Left/Right narrow` and is untouched.

### 3.3 Wireframes

Legend (Nerd Font glyphs by codepoint; the wireframes use ASCII markers):

| Marker | Renders as | Codepoint |
|---|---|---|
| `*` | favorite star | U+F04CE `nf-md-star` |
| `P` | playing | U+F040A `nf-md-play` |
| `!` | failed this session | U+F0026 `nf-md-alert` |
| `(H)` | Recent entry marker | U+F02DA `nf-md-history` |
| `(S)` | pinned Sources row | U+F0411 `nf-md-playlist_play` |
| `>` | cursor row / selected column entry | (selected-row fill + border, not a glyph) |
| `~~` | clipped row peeking past the fold | (the D5 peek) |

**Shape A -- one group of 3,335.** Subscriber `USChannels`, scope All, no
EPG. Column 219 px, list host 701 px, rows 38 px, 12 visible + 1 clipped,
`pageSize()` 11.

```
+---------------------------------------------------------------------------+
| Search channels                                        All - 1,204 of 3,335|
+------------------+--------------------------------------------------------+
| (H) Recent     6 |     US News12 Hudson Valley (FHD)                       |
|     Favorites  0 |  *  Lifetime                                            |
| >   All    3,335 |     (PLUTO USA) One Piece                               |
|                  |     US CBS (KLFY) (D)                                   |
|                  | >   (PLUTO UK) Matlock                                  |
|                  |     USA  FOX NEWS                                       |
|                  |     (PLUTO Denmark) FailArmy                            |
|                  |  !  (PLUTO USA) Comedy Cen  Failed 07:12 - Space to retry|
|                  |     US ABC (WPVI) (D)                                   |
|                  |     (PLUTO Latin) UFC                                   |
|                  |     (PLUTO Sweden) FIFA+                                |
|                  |  P  US NBC (WCAU) (D)                                   |
|  --------------  |  ~~ (PLUTO Norway) World Poker Tour ~~~~~~~~~~~~~~~~~~~~|
| (S) Sources      |                                                         |
+------------------+--------------------------------------------------------+
| 3,335 channels - updated 07:12   j/k move - h/l scope - Enter play - ...   |
+---------------------------------------------------------------------------+
```

No `GROUPS` header. No `United States 3,335` row that returns the same array
as All. No `United States` printed 3,335 times down the second line. The
prefix stays exactly where the provider put it, at full opacity, because it
is the only thing telling `(PLUTO UK) Matlock` from `(PLUTO USA) Matlock`.
The failed row carries its notice in the meta slot and did not change the
height of anything.

**Shape B -- two groups.** Subscriber `SportsPPVAll`, 1,833 channels, groups
of 1,000 and 833, scope All. `axis.narrows` is true, so **nothing changes
except D5 and D6-not-firing**: rows stay 52 px, 9 visible, `pageSize()` 8,
the group name on the detail line is a real choice of two.

```
+---------------------------------------------------------------------------+
| Search channels                                          All - 412 of 1,833|
+------------------+--------------------------------------------------------+
|     Favorites  3 |  *  UFC 300 Main Card                                   |
| >   All    1,833 |     PPV Live Events                                     |
|                  |                                                         |
| GROUPS           | >   Sky Sports Main Event                     until 21:00|
|   PPV Live 1,000 |     US Sports - Now: Premier League - Next: MNF         |
|   US Sports  833 |                                                         |
|                  |     (IT) (DZ) Serie A 1                                 |
|                  |     PPV Live Events                                     |
|                  |                                                         |
|                  |     ESPN Deportes                                       |
|  --------------  |     US Sports                                           |
| (S) Sources      |  ~~ NBA League Pass 4 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~|
+------------------+--------------------------------------------------------+
| 1,833 channels - updated 07:12   j/k move - h/l group - Enter play - ...   |
+---------------------------------------------------------------------------+
```

The hint still reads `h/l group`, because here it is one. This is also the
one list where names genuinely truncate -- 194 of 1,833 exceed the 627 px
name slot today, and 194 still do after this lane. That is stated in
section 5 and not dressed up.

**Shape C -- many small groups.** Public US, 1,472 channels. The scope doc's
table says 73 groups / largest 270; the artefact on disk measures **28
groups / largest 275**, and the live install's own cache agrees. See open
question 1. Either way `axis.narrows` is true and the row treatment is
byte-identical to v0.5.0. What this shape gains is the peek -- in the
column as well as the list, because the column has its own fold problem:
31 selectable entries plus a header at 32 px each in a 469 px viewport is
14 visible, there is no `ScrollBar` or `ScrollIndicator` anywhere in
`Guide.qml`, and `General (275)` sits at column row 21, below the fold, 18
`l` presses from All, with nothing on screen saying those entries exist.

```
+---------------------------------------------------------------------------+
| Search channels                                        All - 1,204 of 1,472|
+------------------+--------------------------------------------------------+
|     Favorites  2 |  *  ABC News Live                                       |
| >   All    1,472 |     News                                                |
|                  |                                                         |
| GROUPS           |     Bloomberg TV+                                       |
|   News        61 |     News                                                |
|   Sports      44 |                                                         |
|   Movies      98 |  P  CBS News Bay Area                                   |
|   Music       27 |     News                                                |
|   Kids        18 |                                                         |
|   Religious  118 | >   CNN International                         until 20:30|
|   Weather      9 |     News - Now: The Lead - Next: The Situation Room      |
|   Legislative 12 |                                                         |
|   Outdoor      7 |     Court TV                                            |
|  ~~ Comedy  14 ~~|     Legal                                               |
|  --------------  |                                                         |
| (S) Sources      |  ~~ C-SPAN ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~|
+------------------+--------------------------------------------------------+
| 1,472 channels - updated 07:12   j/k move - h/l group - Enter play - ...   |
+---------------------------------------------------------------------------+
```

The two `~~` rows are the only visible difference from v0.5.0 on this
playlist, plus the header's count becoming a position. Every other binding
this design touches evaluates to the today branch, by construction rather
than by tuning.

### 3.4 Keyboard map

Complete, both modes. Nothing is added. The two columns to read are the last
two.

| Key | Mode | Action | Changed by this lane? |
|---|---|---|---|
| `j` / `Down` | list | cursor down, wraps | Lands with 21 px of the next row peeking instead of flush (D5). Same index, same wrap |
| `k` / `Up` | list | cursor up, wraps | Same |
| `Up` / `Down` | search | cursor down/up | Same |
| `h` / `Left` | both | previous scope in the column ring | **Ring is one stop shorter on a playlist whose only group duplicates All.** Same action, same silent wrap (`Model.moveScope`). No row becomes unreachable: the removed stop returned the identical array to All |
| `l` / `Right` | both | next scope in the column ring | Same |
| `PgDn` / `PgUp` | both | move by `pageSize()`, clamped, one-row overlap | `pageSize()` is 11 instead of 8 on a one-group playlist, because the rows got shorter. Arithmetic on `resultList.height / (rowHeight + rowSpacing)`, not a changed rule |
| `Home` | both | row 0 (and the list-mode-with-query exception at `Guide.qml:1017-1022`) | Unchanged |
| `End` | both | last row | Unchanged |
| `Enter` | both | play the cursor row | Unchanged |
| `Space` | both | preview / retry a failed row | Unchanged. The `Space to retry` copy that names it survives on both row heights (D4) |
| `f` | list | toggle favorite | Unchanged |
| `s` | list | stop | Unchanged |
| `r` | list | refresh | Unchanged |
| `p` | list | picture in picture | Unchanged |
| `/` | list | to search mode | Unchanged |
| `o` | list | Sources | Unchanged. Still reachable, still on screen, because the column is not hidden |
| `0-9` `.` `,` | list | number entry machine (M2-03) | Unchanged. `numberWidth` is still 0 on every real playlist measured here |
| `Tab` / `Backtab` | both | switch mode | Unchanged |
| `Esc` | both | clear query, else close (the existing ladder) | Unchanged |
| every printable key | search | literal (UX 8 #17) | Unchanged |
| any Ctrl chord | -- | none exists, none added (R1) | Unchanged |

Footer wording, the only keyboard-visible text change: `h/l group` becomes
`h/l scope`, and `Left/Right group` becomes `Left/Right scope`, when the
ring holds only pinned entries. Same character count, so the hint line's
existing left-elision is neither fixed nor worsened by this lane.

### 3.5 Exact behaviour at each shape

| | sub-US 3,335 / 1 | sub-kids 48 / 1 | sub-sports 1,833 / 2 | pub-US 1,472 / 28 | pub-all 11,039 / 30 | inside `General` 2,693 |
|---|---|---|---|---|---|---|
| `axis.narrows` | false | false | true | true | true | true |
| Column width | 219 px | 219 px | 219 px | 219 px | 219 px | 219 px |
| `GROUPS` header + group rows | **dropped** | **dropped** | kept (2) | kept (28) | kept (30) | kept |
| h/l ring length | 3 -> **2** | 2 -> **1** (\*) | unchanged | unchanged | unchanged | unchanged |
| Row height | 52 -> **38 px** | 52 -> **38 px** | 52 px | 52 px | 52 px | 38 px (today's) |
| Visible rows | 9 -> **12** | 9 -> **12** | 9 | 9 | 9 | 12 |
| `pageSize()` | 8 -> **11** | 8 -> **11** | 8 | 8 | 8 | 11 |
| PgDn to the end | 417 -> **304** | 6 -> **4** | 229 | 184 | 1,379 | 244, **unchanged** |
| Detail line | dropped (1 distinct value) | dropped (1) | kept (2) | kept (28) | kept (30) | already absent |
| Names | **unchanged** | unchanged | unchanged | unchanged | unchanged | unchanged |
| Failure notice | meta slot | meta slot | detail line | detail line | detail line | **meta slot** (was detail line, and no longer re-heights the list) |
| Header | `All - 1,204 of 3,335` | `US Kids - 48 channels` (fits, no position) | `All - 412 of 1,833` | `All - 1,204 of 1,472` | `All - 1,204 of 11,039` | `General - 1,204 of 2,693` |
| Footer hint | `h/l scope` | `h/l scope` | `h/l group` | `h/l group` | `h/l group` | `h/l group` |
| Peek | yes, list + column | yes | yes | yes, and the column needs it (31 entries, 14 visible) | yes | yes |

(\*) On a one-group playlist with no recents and no favourites the ring
holds one stop, All. `h`/`l` then wrap onto the scope they are already on
and nothing moves -- which is honest, not dead: the same key on the same
playlist grows a second stop the moment a channel is favourited. The footer
still advertises it because it still works.

The bottom-right cell is the one the scope doc cares most about and the one
this lane does least for. Inside the 2,693-channel group of the public list,
rows are already 38 px, the column is already correct, and this design
returns no space and saves no keypresses -- 244 PageDowns before, 244 after.
It gets the peek and the header position and nothing else. See open
question 7.

---

## 4. Visual specification

Token-only. No new colour, no new emphasis level, no new metric, no
`CONVENTION-EXCEPTION` comment needed anywhere in this lane. The palette at
`/usr/share/omarchy/shell/Commons/Color.qml` has seven menu colours and no
dim-text token, so de-emphasis is opacity, exactly as UX 5.3 already
specifies.

| Element | Token | Weight / opacity | Status |
|---|---|---|---|
| Header scope label, including the new position segment | `Style.font.caption` | opacity 0.52 | Existing rung (UX 5.3), existing element, new text |
| Header scope label width cap | `parent.width * 0.42`, `elide: Text.ElideLeft` | -- | New binding on an existing element |
| Channel name | `Style.font.title` | `Font.Normal`; `Font.Bold` only when playing | **Unchanged. Not split, not dimmed, not reordered** |
| Right meta, `until HH:MM` | `Style.font.caption` | opacity 0.52, right aligned | Unchanged |
| Right meta, `Failed HH:MM - Space to retry` on a single-line row | `Style.font.caption` | opacity 0.52, right aligned | New content in an existing slot, same token, same construction (natural width, no `implicitWidth` binding, neighbours anchor on `visible`) |
| Detail line | `Style.font.bodySmall` | opacity 0.52 | Unchanged where it renders; absent where it would be a constant |
| Trail glyph, failed | `Style.font.icon`, U+F0026 | opacity 0.8 | Unchanged |
| Row heights | `detailRowHeight` 52 / `singleRowHeight` 38 / `rowSpacing` 4 | -- | Unchanged tokens; the predicate choosing between them changes |
| Column | `columnWidth` `Style.space(200)`, `groupEntryHeight` 32 | -- | Unchanged |
| Scroll edge fades | `Style.space(28)`, `Color.menu.background` to transparent | opacity tracks hidden distance | Unchanged |
| Cursor peek | `Math.round(rowHeight * 0.55)`, `Math.round(groupEntryHeight * 0.55)` | -- | Derived from existing tokens, matching `Menu.qml:106` |
| Footer status / hints | `Style.font.caption` | 0.45, keys 0.7 | Unchanged |

Every new string is `textFormat: Text.PlainText`. The one `StyledText` in
`Guide.qml` is our own footer microcopy and stays the only one;
`ARCHITECTURE.md:336` forbids rich text for provider strings and this lane
adds no provider string to any new element.

### Microcopy (everything new, in full)

| Where | String | Notes |
|---|---|---|
| Header, browsing, list overflows | `All - 1,204 of 3,335` | 1-based cursor index, `Model.formatCount` on both numbers, `Model.SEP` between name and count |
| Header, browsing, list fits | `Favorites - 6 channels` | Unchanged from today |
| Header, query, results overflow | `in All - 14 of 200` | No noun. The footer carries `First 200 of 2,227 - keep typing` |
| Header, query, results fit | `in All - 8 matches` | Unchanged from today |
| Row meta, single-line, failed | `Failed 07:12 - Space to retry` | Identical words to `Model.rowDetail`, built from one shared helper so the two can never drift |
| Footer hint, list mode, pinned-only ring | `h/l scope` | Was `h/l group`. Same five characters |
| Footer hint, search mode, empty query, pinned-only ring | `Left/Right scope` | Was `Left/Right group` |
| Accessible name, channel row | `..., row 1,204 of 3,335` | Appended last, after the failure state, so a user who only wants the name hears it first |

No banner, no notice, no "what's new", no tooltip, no onboarding string.
A footer hint that describes whatever is on screen is the house answer and
is cheaper than a notice.

---

## 5. What this costs

### 5.1 What is lost outright

- **A scope a user may have learned.** `l` no longer reaches
  `United States` on the subscriber's list; the entry is gone from the
  column and the ring. It returned the identical 3,335 objects in the
  identical order, so nothing is lost but a habit -- and habits are real.
  A user who had drilled into it and closed the guide reopens in All.
- **Discoverability of the group concept on a one-group playlist.** With
  the `GROUPS` header gone, nothing on that playlist says groups exist.
  Switch to a grouped source and a `GROUPS` section appears with no
  explanation. The column itself never moves or resizes, which bounds this
  to a section header rather than a fifth of the card materialising.
- **`United States` under every row.** Informationally free -- one distinct
  value across 3,335 rows -- but a user who liked seeing it loses it, and a
  playlist with a multi-value `group-title` (`A;B;C`) that collapses to one
  primary group hides secondaries the detail line never showed anyway.
- **14 px of row height on a one-group playlist, permanently, unless EPG is
  configured.** If the user adds an XMLTV URL, `epgConfigured` makes
  `rowsHaveDetail` true again and the whole density win evaporates: 12
  visible rows go back to 9, `pageSize()` back to 8. This is stated because
  no submission stated it: **the headline "+33% visible rows" is a property
  of an install with no EPG, not a property of this design.** The live
  install has `epgUrl` empty today, which is why it was never hit.
- **A fully visible row at the fold.** The peek gives up `rowPeek +
  rowSpacing` = 25 px so the next row keeps peeking. At 38 px rows the 12
  visible become 11 full plus one clipped. The honest headline is therefore
  9 full rows becoming 11 full rows plus a visible seam, not 9 becoming 12.
- **The name slot on a failed single-line row.** 174 px goes to the failure
  notice, leaving 445 px; 16 of 3,335 subscriber names, 47 of 1,472
  public-US names and 320 of 1,833 sports names are long enough to elide
  there. Only on a row that has actually failed, and only until it plays.

### 5.2 Screen space taken from the channel list

**None. Net, this lane gives the list three rows and takes nothing.**

- Column: 219 px, unchanged on every shape.
- Header: the position segment replaces a count in a slot that already held
  a count. Measured identical width at four digits (120 px either way) and
  never wider than the widest form of what it replaces plus 6 px.
- Footer: no rung added, no hint pair added, one verb swapped for another of
  the same length.
- Row: no slot added. The failure notice goes in a slot that was already
  reserved and already blank on failure.
- Rail / scrollbar / minimap / A-Z index / section headers / tick marks:
  none. See 5.4.
- Returned to the list: 14 px per row on a one-group playlist, which is
  three more channels on screen and 113 fewer PageDowns across 3,335 rows.

### 5.3 What a user who liked the old behaviour will miss

- Mouse users lose one click target (the `United States` column row).
  Everything else they can click today they can still click.
- Anyone who navigated *by provider* -- "show me the PLUTO Denmark
  channels" -- is exactly as well off as today and no better. The prefix
  work that would have helped them is refused, and no facet replaces it.
  Search remains the answer: `denmark` returns 227, `peacock` 30, `espn` 8.
- Anyone who had learned that a failed channel makes its group's rows taller
  will find that it no longer does. That is a removal of a surprise, but it
  is a change.
- Anyone who reads the header as a channel count will find it reading a
  position on any list longer than the screen, and will have to look at the
  footer for the total on the shapes where the header no longer carries it.

### 5.4 Deliberate refusals, with the measurement that decided each

| Refused | Measured reason |
|---|---|
| Moving or dimming the repeated bracketed prefix | 16 distinct tokens, not one. 1,092 of 3,335 rows collide on their stem. Against the shipping search: `ufc` 10 rows / 1 distinct stem, `fifa` 10 / 1, `one piece` 5 / 1. Search is where the collisions gather, and search is the thing the scope doc protects |
| Deleting the prefix | Same 1,092 collisions, but unrecoverable |
| Hiding the group column | 0 of 3,335 names elide at 627 px and 0 at 846 px, so the 219 px is unusable width; and the column carries Recent, Favorites and Sources |
| Adaptive column width | Longest label across all five real lists is 17-20 characters; the reclaim is about 50 px, and a width that varies per playlist is the unpredictable kind of adaptation |
| A proportional scrollbar or rail | **At 3,335 rows in a 514 px viewport the honest thumb is 1.89 px. At 11,039 rows it is 0.43 px.** A thumb that small conveys nothing; clamping it to a readable minimum makes it lie about position. No Omarchy keyboard surface has one |
| A new key (`g`, or anything else) | `groupModel` and `moveScope` read one `scopeList` array, so a key that reveals a hidden column reveals either an empty column or an entry the keyboard cannot reach. R-A |
| A smarter ranker | Four alternative rankers measured by a losing submission moved median keystrokes-to-target by **zero**, because `filterChannels` already drains group-only matches last. Banked so nobody re-spends it |
| Group-blind matching on a one-group playlist | Measured inert across ~15,000 probes: the target's position never changed. It buys a header count and costs two UX rulings |
| Opening on Recent | A 2-press swap from All, and a no-op on the subscriber's own playlists because their channel ids do not resolve against stored recents. Contradicts UX 1.3 principle 2 |
| Section headers / A-Z rail / prefix facets | Playlist order is the provider's order and this lane may not change it (UX 2.5). 16 prefix families fragment into roughly a thousand runs. And a facet column is the "new navigation concept" the scope doc excludes |

---

## 6. Performance

Nothing in this lane touches `filterChannels`, `matchRank`, `searchKey`,
`nameKey`, the four ranking tiers or the 200-row cap. The per-keystroke path
is byte-identical, and that is a hard requirement, not an aspiration.

Nothing structural moves: the channel list stays an integer model
(`model: root.rowCount`, `Guide.qml:2230`) so setting the row set stays
O(1); row height stays one uniform root property so `contentHeight` is exact
and `pageSize()` stays arithmetic; `cursorIndex === ListView index ===
currentRows index` survives, which roughly twenty call sites assume. No
role-carrying `ListModel`, no `ListView.section`, no interleaved non-channel
rows, no variable row heights. No change to parsing, caching or the helper,
so no JS/Python JSON-fixture parity obligation is created.

### 6.1 Must be measured before a line is written

| # | Measurement | Budget | Why |
|---|---|---|---|
| P1 | `Model.scopeSurface` vs today's `Model.scopeEntries`, node and offscreen `qmltestrunner`, at 1,472 / 3,335 / 11,039 / 50,000 channels | **Must be within noise of today.** Today, node median of 25: `scopeEntries` 1.88 ms at 1,472, 4.25 ms at 3,335, 17.71 ms at 11,039. `groupChannels` alone is 37.33 ms at 50,000 | This is the whole buildability question. If `scopeSurface` scans the array twice instead of once it doubles a pass that is already the most expensive thing on the open path |
| P2 | Guide open, end to end, with the 11,039-channel cache loaded, before and after | **Under 150 ms** (CLAUDE.md rule 7). PERF-02 currently measures 65-75 ms | The open path runs `initialScope` and `rebuildGroups`; this lane adds work to the second |
| P3 | Same at `Model.MAX_CHANNELS` = 50,000 | Under 150 ms, or the lane changes shape | `groupChannels` at 50,000 is 37 ms in node and the QML JS engine runs 3-4x slower; the guard is that `rebuildGroups` caches on `groupsDirty` and runs once per channel-set change |
| P4 | `filterChannels('e')` and `filterChannels('espn')` at 3,335 and 11,039, before and after | **Bit-identical timing and bit-identical results.** Today, node: 2.26 ms and 7.33 ms for `'e'` | Regression guard. If this number moves at all, something touched the hot path that should not have |
| P5 | The one-time re-layout when `rowHeight` changes 52 -> 38 at 3,335 rows | Under one frame (16 ms) at the 60 Hz the shell composites at | It happens on a scope change, which already re-heights today, but it now also happens once at open on a one-group playlist |
| P6 | `resultList.itemAtIndex(cursorIndex)` null rate when `scrollToCursor` is called synchronously from `moveCursorBy`, `setScope` and `onHeightChanged` | **Zero nulls over a 300-page walk**, or the peek gets an explicit `Qt.callLater` | `Menu.qml` only ever calls `revealCursor` inside `Qt.callLater` after a model change. An intermittent fold affordance is worse than a consistent absence |
| P7 | Delegate cost with the meta slot carrying the failure notice, 12 instantiated rows | Under 0.05 ms for the visible list | One `Text` binding gains a branch; it should be unmeasurable, and if it is not, something re-entered width through `implicitWidth` (D-LIVE-01) |

All QML timings from `QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner`
against a `Model.js` whose md5 matches the shipping file, on an idle machine.
Treat them as a floor, not as the live shell under load.

### 6.2 What forces a redesign

- **P1 shows `scopeSurface` costing measurably more than `scopeEntries`.**
  Then the axis must be derived from the entries array after the fact rather
  than alongside it, and the `soleGroup` name has to reach
  `Model.requestedScope` some other way.
- **P3 exceeds 150 ms at 50,000.** Then the axis must be computed by the
  helper at parse time and carried in the cache, which turns a UI lane into
  a data-format change and a Python/JS parity obligation. That is a
  different lane and must be raised, not absorbed.
- **P6 shows nulls.** Then either the peek is wrapped in `Qt.callLater`,
  which means the viewport settles one frame after the cursor moves and must
  be checked for visible lag, or it is dropped from the synchronous call
  sites and the fold affordance becomes partial -- which is a reason to stop
  and re-decide, not a reason to ship it partial.
- **The live pass shows a row-height pop on open** on a one-group playlist
  (the first frame composed at 52 px before `rebuildGroups` has run). The
  default for `groupAxis.narrows` is `true` -- the shipped behaviour, never
  a value invented from `undefined` (CLAUDE.md rule 10) -- so the failure
  mode is a visible collapse, not a wrong layout. If it pops, the axis has
  to be resolved before `open()` returns rather than inside
  `rebuildDisplay`.
- **P4 moves.** Stop. Something is on the keystroke path that this design
  says is not.

---

## 7. Accessibility

**The rule, and it governs every element in this document:** nothing in the
guide is conveyed by colour alone or by position alone. Every state has a
glyph or a word in addition to any tint, and every spatial cue has a text
equivalent that a screen reader reaches. This is UX 1.3 principle 4 and UX
7.2, and this lane is the first one that could plausibly have broken it.

| Fact | Visual carrier | Text carrier | Position/colour-only? |
|---|---|---|---|
| Where you are in the list | The peek at the fold; the edge scrims | `All - 1,204 of 3,335` in the header, and `, row 1,204 of 3,335` appended to `Model.rowAccessibleName` | No. The peek is the only purely spatial cue and the header and the accessible name both state the same fact in words |
| More rows exist below | The peek; the bottom scrim | The header position; the footer total | No |
| A channel failed | Alert glyph U+F0026 in the trail slot | `Failed HH:MM - Space to retry`, on the detail line or in the meta slot depending on row height | No. This is the one UX 7.2 pairing that every competing design broke |
| Which scope is selected | Column selection fill and border | The header scope label; `Model.rowAccessibleName` is reached through a list whose `Accessible.name` names the scope | No |
| The group axis does not narrow | The `GROUPS` section is absent | The footer reads `h/l scope` rather than `h/l group` | No |
| A channel is playing | U+F040A + `Font.Bold` | `, playing` in the accessible name; the footer status line | No |
| A channel is a favourite | U+F04CE | `, favorite` in the accessible name | No |

Specifics for this lane:

- `Model.rowAccessibleName` gains `, row N of M` **last**, after the failure
  state, so a user stepping rows hears the name first and the position after.
  Under a query `M` is `root.rowCount`, capped at `Model.MAX_ROWS_DEFAULT`
  200, which matches what the header says and what the list actually holds;
  the true match total stays in the footer where it is today. This is a real
  tax -- a screen-reader user hears the position on every `j`/`k` -- and it
  is accepted because today they are told strictly less about position than
  the eye is, which UX 7.2 does not permit once a visual position cue exists.
- The group column, the `accessibleGroups` list and the
  `sourcesRowAccessibleName` Sources row are **not** removed on any shape.
  This is the single largest reason the column is kept.
- The failure notice moving between the detail line and the meta slot does
  not change what a screen reader hears: `rowAccessibleName` already appends
  `, failed` from `o.failedAt` and does not read either slot. The visual
  carrier moves; the spoken carrier does not.
- Nothing in this lane introduces a colour, an opacity rung, or an emphasis
  level that does not already exist in UX 5.3.
- Open item: a live Orca pass must confirm the toolkit's own
  position-in-set for the instantiated delegates (the list holds roughly
  12-20 `ListItem`s behind `cacheBuffer`, not 3,335) does not double-announce
  against the appended string. This cannot be proven from a test. See 9.5.

---

## 8. Work plan and file ownership

**The unit rule.** Two files that a test asserts about each other are one
unit and must be owned by one lane. A diff touching an unowned file is
rejected (CLAUDE.md, Working in parallel, rule 1). In this repo that makes
the following indivisible:

- `Model.js` + `tests/Model.test.js` + `tests/Model.spec.qml` -- the node
  suite and the QML spec both call the same pure functions and the floors in
  `scripts/check.sh` count both.
- `Guide.qml` + `Model.js` -- any decision lifted out of a QML binding into
  a pure function is asserted through `Model.js`, so the QML change and the
  function it calls cannot be split across lanes.
- `docs/UX.md` + this file -- the amendments in section 9 land in UX.md in
  the same commit as the code that implements them.

Therefore this lane is **one lane, not two**, and it owns:

| File | Access | What changes |
|---|---|---|
| `Model.js` | write | `scopeSurface`, `groupAxis` shape, `requestedScope`, `rowsHaveDetail`, `rowShowsGroup`, `rowFailedMeta`, `revealOffset`; `scopeEntries` becomes a wrapper; `scopeLabel` gains the position form; `rowAccessibleName` gains the index; `footerHints` gains the ring-verb gate |
| `Guide.qml` | write | `rowsHaveDetail` and `showGroup` call into Model; `anyFailedInScope` **deleted**; `meta.text` branch; `scrollToCursor` and `positionColumn` call `revealOffset`; `scopeLabel` width cap and elide; `rebuildGroups` stores the axis; `footerHintText` passes the gate |
| `tests/Model.test.js` | write | node assertions for every new pure function and every changed one |
| `tests/Model.spec.qml` | write | QML-side assertions for the same functions, in the engine that ships them |
| `scripts/check.sh` | write | raise `QML_SPEC_MIN` (61), `NODE_CHECKS_MIN` (1249), `PY_TESTS_MIN` (357 -- unchanged, no helper change) in the same commit |
| `docs/UX.md` | write | the amendments approved under section 9 |
| `docs/STATUS.md` | write | board entry, decisions log |
| `docs/QA.md` | write | the live-pass script from section 9.2 |
| `Service.qml`, `BarWidget.qml`, `bin/omarchy-iptv`, `manifest.json` | **read only** | Nothing here needs them. If a change appears to, stop: it means the axis is being pushed into the cache, which is open question 6 and a different lane |
| `~/.config`, `~/.cache`, `~/.local/state`, `/usr/share/omarchy`, the installed plugin | **read only** | CLAUDE.md, Never touch. `Menu.qml` is read for the algorithm and never modified |

**Sequence.** Six steps, each green on `scripts/check.sh` before the next.

1. **Measure first.** P1 and P4 from section 6, against `Model.js` as
   shipped, recorded in the commit message. If P1 fails, stop and re-shape.
2. **`Model.js` pure functions plus their tests**, with each test shown red
   against a deliberate mutation of the shipping predicate before it is
   shown green (CLAUDE.md rule 11). No `Guide.qml` change yet, so the guide
   still behaves exactly as v0.5.0 at this commit.
3. **D4, the failure notice and the deletion of `anyFailedInScope`.** This
   goes *before* the row-height change, deliberately: it must be possible to
   demonstrate that a failed channel still says `Failed HH:MM - Space to
   retry` while row heights are still the shipped ones.
4. **D3, the row-height predicate**, wired to the Model functions. P5.
5. **D1 + D2 + D6**, the axis, the column entries and the footer verb.
6. **D5**, the peek and the header position. P6, P7.

**Integration.** No shims (rule 4): a grep proving zero stubs, plus a green
`check.sh`. The live pass (section 9.2) snapshots `shell.json`, the state
directory and the cache first and restores the exact end state (rule 5), and
checks `pgrep -x hyprlock` before any keystroke (rule 6).

---

## 9. Test plan

### 9.1 What a test can prove

All of these are pure, node- and QML-reachable, and every one must be shown
red against a mutation first.

| Assertion | Fixture |
|---|---|
| `scopeSurface(ch).axis.narrows` is false at 1 group, true at 2 and at 28, for a group-less list that synthesises `Ungrouped`, and for an empty list | Real parsed caches plus the existing synthetic fixtures |
| `scopeSurface(ch).entries` omits the `GROUPS` header and the group row iff `!narrows`, and is element-identical to today's `scopeEntries` when `narrows` | The existing five-group fixture must not change, which is the regression guard for the eight shipped `scopeEntries` tests |
| `scopeSurface` calls `groupChannels` exactly once (instrument and count) | Any fixture. This is P1 as an assertion, not a benchmark |
| `requestedScope(entries, "g:United States", axis)` returns `SCOPE_ALL` when the axis does not narrow and the name matches the sole group, **including when Favorites is non-empty** | The exact case `fallbackScope` gets wrong |
| `requestedScope` defers to `fallbackScope` unchanged in every other case | D-LIVE-07 regression guard |
| `rowsHaveDetail` truth table, all eight combinations of the three inputs | -- |
| `rowShowsGroup` truth table | -- |
| `rowsHaveDetail` never reads a failure flag -- the function has three parameters and adding a fourth breaks the test | Guards against the re-height hazard returning |
| `rowFailedMeta("07:12")` and `rowDetail({failedAt:"07:12"})` produce the same words from the same constant | Guards against the two drifting |
| `scopeLabel` for all four forms, at the boundary where the list stops overflowing, and with a 200-capped query | -- |
| `rowAccessibleName` appends `row N of M` last, after `, failed` | -- |
| `footerHints` returns `h/l scope` / `Left/Right scope` iff the ring is pinned-only, `h/l group` / `Left/Right group` otherwise, and the character count of the joined line is unchanged | Guards the 684 px hint line |
| `revealOffset` arithmetic: overhang at the bottom, underhang at the top, clamped to `originY` and to `originY + contentHeight - height`, index 0 and index `count-1` no-ops, a viewport taller than the content | Synthetic; this is the whole ported algorithm as data |
| `filterChannels` results and ranking are byte-identical before and after, across every single letter and a corpus of real name-prefix queries on all five playlists | The strongest regression guard in the plan, because search is what the scope doc protects |
| Every shipped `scopeEntries`, `fallbackScope`, `rowDetail`, `scopeLabel`, `rowAccessibleName` and `footerHints` test passes unchanged | -- |

### 9.2 What only a live pass on a real playlist can prove

One lane holds the display; this list is its script. Snapshot first, restore
after.

1. **No row-height pop on open** on the subscriber's `USChannels`. The card
   must compose at 38 px, not compose at 52 and collapse. This is R-C and no
   test reaches it.
2. **No column pop.** The `GROUPS` section must be absent from the first
   frame on a one-group playlist, not appear-then-vanish.
3. **The peek is present on every cursor move, not most of them.** Walk 300
   PageDowns and 300 `j` presses through the 11,039-channel list and confirm
   the fold never parks flush. This is P6 and it is the single most likely
   thing to be quietly wrong.
4. **The peek in the column** on the 28-group public list: `General` must
   become reachable-looking, not appear to be the last entry.
5. **The failure notice is legible in the meta slot** at the real font, on a
   real dead stream, on the cursor row and off it. Colour is `root.foreground`
   at 0.52, and on the selected row that is unselected foreground over
   `Color.menu.selectedBackground` -- this needs an eye, not a test.
6. **The header position does not read as motion in the periphery** while
   holding `j`. If a digit flickering in the top-right corner is distracting,
   that is a finding and it is cheap to reverse.
7. **`searchLine` does not visibly reflow** as the header count gains and
   loses a digit. Predicted invisible; must be seen.
8. **Orca**: a screen-reader pass stepping rows, confirming `row N of M`
   does not double-announce against the toolkit's own position-in-set, and
   that the failure state is still announced.
9. **Theme sweep.** `omarchy theme set` across the installed themes,
   confirming no literal and no assumption about `base-size 12` or spacing
   scale 1.0 has leaked in. Every metric in this lane is a token or derived
   from one; this is the proof.
10. **Two sources in one session.** Switch `USChannels` -> `SportsPPVAll` ->
    public US and back, confirming that what changes between them is only
    row height, the `GROUPS` section and one footer verb -- and that nothing
    changes while the guide is open across a refresh.
11. **The four tasks, timed, on the subscriber's list**: a known channel by
    name; a half-remembered one; discovery with no name; return to what was
    watched yesterday. Before and after. This is the bar, and it is the one
    thing no unit test can answer.

### 9.3 What this plan deliberately does not claim

No test in it proves the guide is faster. The measured, code-caused gains
are: three more rows on screen and 113 fewer PageDowns on a one-group
playlist with no EPG; one wasted `h`/`l` stop and its synchronous rebuild
removed; a fold that says more exists; and a number that says how far in.
Everything larger that was on offer failed measurement.

---

## 10. Open questions for the product owner

**Q1. The scope doc's group counts do not match the artefacts on disk.
Which is canonical?**
The doc's table says public-US 1,472 channels / 73 groups / largest 270 and
public-everything 11,039 / 183 / 2,641. Measured through the shipping
`Model.groupChannels`: the caches in the session scratchpad give **28 / 275**
and **30 / 2,693**, and the live install's own cache agrees at 28. The
channel counts match the doc exactly, and neither file carries a multi-value
`group-title`, so this is not a splitting difference -- they are two
different snapshots. The 183-group file does exist
(`scratchpad/m209/scale-11039.m3u`, 183 distinct `group-title` values,
largest `Undefined` at 2,641) and reproduces the doc's table.
*Recommendation:* adopt the on-disk caches as the working artefacts, because
they are what the live install actually has, **and** run the full test
matrix against `scale-11039.m3u` before merge. The axis verdict is identical
either way (28, 30, 73 and 183 are all >= 2), and the doc's argument gets
stronger, not weaker: even the 30-group snapshot contains a single group of
2,693. Raising this rather than picking silently, per CLAUDE.md.

**Q2. Amend UX 2.4's slot table so the right meta slot carries
`Failed HH:MM - Space to retry` on a single-line row?**
Today UX.md:181 puts that string only on the detail line, and UX.md:179
scopes the meta slot to `until HH:MM`. Without this amendment, any change
that suppresses the detail line deletes the retry affordance -- which is
what every competing design did, and which UX 7.2 and ruling 9 forbid.
*Recommendation:* approve. It costs one row in a table, it keeps the glyph
and the words paired on both row heights, and it lets row height stop
depending on session state -- which is an improvement over what ships.

**Q3. Amend UX 2.3 so a group that is not a strict subset of All is not
listed in the column or the h/l ring?**
UX 1.3 principle 3 ("the group column is always visible") is honoured -- the
column stays, at its full width, with Recent, Favorites, All and Sources.
What is dropped is the `GROUPS` header and a single entry that returns an
element-identical array to the entry above it.
*Recommendation:* approve, worded as a property of the data rather than a
special case: *a group entry is listed when choosing it narrows the list.*

**Q4. Amend UX 6.1 so the header's count becomes a position when the list
is longer than the viewport?**
`All - 3,335 channels` becomes `All - 1,204 of 3,335`; the total stays in
the footer counts line, which already reads `3,335 channels - updated 07:12`.
*Recommendation:* approve. It is the keyboard-tool convention, it costs zero
pixels at four digits, and the alternative slot (`footerStatus`) is a
ten-rung ladder where `playingName` already outranks the counts.

**Q5. Does `Model.rowAccessibleName` gain `row N of M`, and is `M` the
capped 200 under a query?**
Today it announces no index at all, so a screen-reader user is told strictly
less about position than the eye -- which is only acceptable while the eye
is told nothing either, and after Q4 it is not. Under a query `M = 200` is
what the header says and what the list holds; the true match total is in the
footer.
*Recommendation:* approve as specified, subject to the Orca pass in 9.2.8.
If Orca double-announces against the toolkit's own position-in-set, drop the
appended string and re-open this.

**Q6. May the group axis be computed at parse time and cached, if P3 fails
at 50,000 channels?**
`groupChannels` costs 37 ms in node at `MAX_CHANNELS`, which is 110-150 ms
in the QML engine. Today it already runs on that path and is cached by
`groupsDirty`, so this design adds nothing -- but it also leaves no headroom.
Moving the count into the cache means a helper change and a JS/Python parity
fixture, i.e. a different lane.
*Recommendation:* do **not** pre-authorise it. Measure P3 first. If it
fails, raise it as a separate lane rather than absorbing a data-format change
into a UX lane. Note that the helper already computes a `groupCount` for its
own notification (`Model.js:3732` reads it), by a different rule
(`split_groups` splits `A;B;C`, `Model.primaryGroup` keeps the first), so
the two would have to be reconciled before either is trusted as a layout
input.

**Q7. This lane returns nothing for a 2,693-channel group. Accept?**
Inside the public list's largest group, rows are already single-line, the
column is already correct, and this design changes 244 PageDowns to 244
PageDowns. Problem 1 as stated has two halves -- "the column duplicates All"
and "choosing a 2,641-channel group narrows nothing" -- and this lane
answers only the first. The honest fix for the second is a second narrowing
axis inside a group, which is exactly the "new navigation concept" the scope
doc excludes.
*Recommendation:* accept, and close problem 1 at *the column never claims a
narrowing step it does not provide.* If the second half is wanted, commission
it as its own scoped decision with the exclusion lifted -- do not let it in
through this lane's side door, which is how three of the four submissions
ended up proposing a facet column they had also argued against.

**Q8. Accept the refusal of problem 3?**
The scope doc ranks it third of three and it is the only one this lane does
not touch at all. The measurement says the repeated prefix is not one token
but sixteen, that it is the sole discriminator for 1,092 of 3,335 rows, and
that moving it makes the *search* result screen -- `ufc`, `fifa`,
`one piece` -- collapse to a single repeated word. The only benefit anyone
measured for moving it was a typing benefit that turned out to be available
today with no code change at all, because the shipping search matches
substrings anywhere.
*Recommendation:* accept the refusal on this evidence, or commission a
separate, narrow study that measures *scanning* -- fixations to find a named
row in a twelve-row window -- rather than typing. That is the one claim for
the treatment nobody has tested, and it is the only ground on which it could
still be right.

## 11. Product owner rulings (2026-09-15)

Design accepted. Before the rulings, the finding that matters most.

**I was wrong, and the measurement proves it.** I wrote the scope around three
problems, and the third was that rows waste their most scanned space because
two thirds of the subscriber's channel names open with the same token. Every
designer independently reached for the obvious fix, and the judges killed it
with data I did not have. That leading run is not one token, it is sixteen, and
seven shared characters before they diverge into eleven countries. Strip or
demote it and a thousand rows collide on what remains. Worse, browsing hides
the damage while search concentrates it: a search today returns rows separable
at the first glyph, and after the change every visible row would read the same
word with the only difference hundreds of pixels to the right, smaller and
dimmer. My own framing invited the one change the data forbids. It is refused,
and the numbers are recorded beside the refusal so nobody re-proposes it.

Ruling on the questions, in order.

| # | Ruling |
|---|---|
| GS1 | Adopt the on-disk caches as the working artefacts, since they are what the install actually holds, and run the full matrix against the 183-group file before merge. Raising the discrepancy rather than quietly picking one was right. The conclusion survives either way, which is the point worth noting: an argument that only works with one snapshot is not an argument. |
| GS2 | Approve. The failure notice moves to the slot that is free precisely when a channel has failed. Every competing design deleted the retry affordance without noticing, which is a good reminder that a change to layout is a change to behaviour. Row height ceasing to depend on session state is worth more than the feature that exposed it. |
| GS3 | Approve, worded as the property of the data rather than a special case: a group is listed when choosing it narrows the list. The column stays at full width with its other entries. Hiding it would have cost mouse and screen-reader users every route to Recent, Favourites and Sources to buy back width that measurement says is not scarce, since no name elides even at the current slot. |
| GS4 | Approve. Position replaces a total that the footer already carries, so it costs nothing and removes a duplication. |
| GS5 | Approve as specified, subject to the screen-reader pass. A blind user being told less about position than a sighted one was tolerable only while neither was told anything, and after this change it would not be. If the toolkit already announces position, drop the addition and reopen. |
| GS6 | Do not pre-authorise caching the group axis. Measure first. If it fails, it is a separate lane, because a data-format change absorbed quietly into an interface lane is how two implementations of one rule end up disagreeing, which has already cost this project twice. Note the helper computes a similar count by a different rule; those must be reconciled before either is trusted. |
| GS7 | Accept. This lane does not make a 2,693-channel group faster to page, and says so plainly rather than implying otherwise. The honest fix is a second narrowing axis, which the scope excludes deliberately. Half the problem solved and stated is worth more than all of it claimed. |

Two things I want carried into the build.

Four of the five changes are deletions or reuse of code Omarchy already ships,
including fifteen lines lifted from its own picker whose comment describes the
exact defect the guide has, in two places. That is the shape of a good answer
here, and a lane that finds itself adding a component should stop and re-read
this section.

The single measurable win is removing a line that carries no information: on
the subscriber's list the second line of every row renders one identical string
across all 3,335 rows. Deleting it buys a third more visible rows and a quarter
fewer page presses, at zero cost. Most of the value in this lane comes from
taking things away.

## 12. Corrections after the build (product owner, 2026-09-15)

Where this document and the shipped code disagree, the code is right.

- Section 3.2 wrote one binding out as interface-layer code. That is stranded
  logic a test can only mirror, which the project rules forbid, and lifting it
  is what let the lane actually verify the claim the change rests on: a failed
  row's meta slot was already blank, so the notice moves into space that is
  free exactly when it is needed.
- The design said one function could become a wrapper so its callers stayed
  byte-identical. Its only real caller is the guide, so that was self
  contradictory, and the two changes had to land together. Splitting them
  would have left a window where a deep link to a sole group falls into a
  one-row Favourites, which is the defect the other half exists to prevent.
- Minor re-measurements moved slightly and changed nothing: fourteen distinct
  bracketed tokens rather than sixteen, and 1,062 stem collisions rather than
  1,092. The refusal stands on the same footing.
- The test floors this document named were already stale before the lane
  started, which is its own small lesson about floors.

### The caveat that matters to a user [SUPERSEDED, see section 14]

The density win is a property of an install with NO guide data. The second
line is deleted because it renders one identical string on every row, which is
true when there is nothing else to put there. Configure an XMLTV source and
that line carries what is on now and next, which varies per row, so it returns
and the visible rows go back from twelve to nine. That is correct behaviour,
not a regression, but it means the improvement is largest for exactly the
setup this was measured on and smaller for someone with guide data. Say so in
the README rather than advertising a number that depends on an empty field.

### A lane raised, not absorbed

Opening the guide on a maximum-size playlist takes about 291 milliseconds
against a 150 millisecond budget. It is pre-existing and this work neither
caused nor worsened it, measuring 295 before. Ruling GS6 forbade absorbing a
data-format change here, and the lane stopped, which was right. It also
established that the obvious fix would not have worked: caching the group axis
removes only about a third of the cost, and the larger half is the open path
building the same index four times over. Worth knowing before anyone spends a
lane on the wrong half.

## 13. Rulings after the live pass (product owner, 2026-09-15)

| # | Ruling |
|---|---|
| GS8 | Fix the contrast before release. The failure notice on a selected row measures below the accessibility threshold, and of everything on the card it is the one piece of text that names a key the user is supposed to press. Text that tells someone what to do must be the most legible thing on the row, not the least. |
| GS9 | My caveat was wrong and the fix is better than the documentation. I wrote that configuring guide data correctly returns the second line and reverses the density win. On this provider the line comes back BLANK on every row, because almost no channel carries an identifier to match guide data against. So the user loses three rows and gains nothing, which is not correct behaviour, it is the original defect wearing a different hat. Apply the rule the lane already established: the line exists when it carries something that varies, and guide data being configured is not the same as guide data being present. Decide on the data, not the setting. |
| GS10 | The empty accessibility tree is not ours to fix here and is bigger than this feature. The shell publishes nothing at all with the guide open, so no screen reader can announce anything, which means every accessibility rule this project has written is currently unobservable in practice. Investigate it as its own item, establish whether it is the shell, the toolkit or how the plugin builds its surfaces, and if it belongs upstream report it the way we reported the settings defect. Ruling GS5 stays open until something can actually be heard. |
| GS11 | Clearing a guide URL must remove its cache, for the same reason removing a source does. A setting the user cleared should not come back after a restart because a file outlived it. |

One note for the record. The pass called the cursor peek the change it would
keep if it could keep only one. That change is fifteen lines of arithmetic
lifted from Omarchy's own picker, whose source comment describes the exact
defect this guide had. The most valuable thing in this lane was already
written, in this codebase's own house style, and nobody had looked.

## 14. Corrections after the fixes (product owner, 2026-09-15)

Section 12's caveat is superseded and was wrong in the way that mattered. The
second row line does not return when guide data is CONFIGURED. It returns when
guide data MATCHES the playlist, which is a different thing and the only one a
user can feel. On the subscriber's provider the two differ completely: almost
no channel carries an identifier to match against, so the old rule gave them a
blank line on every row and cost them three rows for nothing. The README's
density claim must not be hedged with the old caveat.

### A finding larger than the lane that found it

While measuring the notice's contrast across all 23 installed themes, the lane
found that the dim rung used for ambient text throughout the guide, the times
and the now-and-next line, is itself below the accessibility threshold in 20 of
those 23 themes. That is not this feature. It is a project-wide decision made
early and never measured, and it affects text a user reads constantly.

It gets its own item, for the same reason the accessibility tree did: absorbing
it here would mean changing the look of every surface inside a release about
list density, with no measurement of the alternatives and no live check of how
it reads. Measure it properly, decide the rung once, and apply it everywhere.

Two accessibility findings in one pass, neither caused by this work, both
invisible until someone measured rather than looked. The rules were written
down long ago; nothing had ever checked them.

## 15. The rungs, measured and split (product owner, 2026-09-15)

Section 14 sent the dim rung to its own item. It was measured, a fix was
designed, and a reviewer attacked the design. The result is a split: one rung
ships, one is refused with numbers, and two more elements turned up that the
design had not looked at. Four ids, so each can be decided on its own evidence.

The guide uses five dimness levels, 0.45, 0.52, 0.58, 0.70 and 0.80, plus full.
Only two are named constants; the rest are bare literals. All five are
inherited verbatim from Omarchy's own pickers, so any change makes the guide
read differently from the menu beside it.

| Id | Element | Measured | Outcome |
|---|---|---|---|
| **D-RUNG-1** | The 0.45 rung: footer status, footer verbs, group entry count, Sources pinned count | Under 4.5:1 in **23 of 23** themes, worst 1.98:1, median 3.17:1 | **Raised to 0.7** (ruling SG2). 23 of 23 under becomes 6 of 23 |
| **D-RUNG-2** | The 0.52 rung: detail line, header scope label, right-hand meta | Computes under 4.5:1 in **20 of 23** themes | **Refused for now.** See below |
| **D-RUNG-3** | The bar's idle glyph, dimmed by `Qt.darker(barFg, 1.55)` | Under 4.5:1 in **7 of 23** themes | Open, and ahead of D-RUNG-2 in the queue |
| **D-RUNG-4** | The accent ink on the cursor row (historical) | Under 4.5:1 in **8 of 23** themes at FULL opacity | Fixed under SG4, then superseded 2026-09-21: the accent left the cursor row entirely and a 2 px mark carries the cursor. See STATUS D-RUNG-4, D-RUNG-13, D-RUNG-15 |

### Why one rung moved and the other did not

The difference is arithmetic, not taste, and it rests on the single most
useful measurement in this repository.

`docs/QA-RESULTS.md:4720-4732` is the only place where a rendered pixel and a
computed value have ever been compared on this project. On the reference theme
the model computes 3.54:1 and the screen measures 4.79:1 glyph-body and 7.13:1
peak, repeated on a second capture. **On the one case where both numbers exist,
the model fails and the screen passes, by about 1.25 ratio points.**

So the model understates. Apply that error as a margin:

- 0.45 has a median of 3.17. Even 3.17 plus 1.25 is 4.42, still under the
  threshold. The finding survives the error, so the rung moves.
- 0.52 has a median of 3.64 to 3.80. Plus 1.25 it clears comfortably. The
  finding does NOT survive the error, so the rung stays until somebody
  calibrates.

### What the refusal bought

A per-theme contrast floor over the 0.52 rung was designed and costed. It was
refused, and the reasons are worth keeping because they are the shape of a fix
that passes a test while making the product worse.

1. **It spends the only hierarchy the guide has left.** The
   name-versus-secondary separation on a non-cursor row falls from a median of
   2.86:1 to 2.24:1, and to 1.35:1 in the worst theme. There is nowhere else to
   put that hierarchy: the installed font ships four faces and Bold already
   means "playing", and the row height is pinned.
2. **It would pay that on the number that is known to be wrong**, in the
   direction that says the screen is already fine.
3. **It leaves no margin.** After the floor all 23 themes land at exactly 4.50,
   and the proposed test asserted 4.50. Every rendering effect nobody has
   checked, antialiasing on a 10-pixel stem, hinting, gamma, moves the real
   figure off that line, and the suite could not tell. Green on every layer,
   under threshold on screen, hierarchy already spent.

The next step is the calibration pass, not the fix. The method already exists
here: sample rendered luminance off screenshots, glyph body and peak stroke,
repeated for stability. Run it on the reference theme and one light theme at
the caption size, then reconcile the model to the pixels or record the offset.
Then decide the 0.52 rung with a target above 4.5, never on it.

### The one the design never looked at

D-RUNG-3 is the bar's idle glyph. The contrast design ruled the bar widget out
by searching it for `opacity:` and finding none; the bar dims by a different
mechanism entirely, one named outright in a UX row the design cited for
something else. It is under threshold in 7 themes and it is **the only part of
this plugin that is on screen permanently**. It goes ahead of the guide's 0.52
rung for that reason, and it lives in a file no other item writes.

Which is the same lesson as section 14, arriving by a different route: the
measurement was not wrong, the search for what to measure was.

### D-RUNG-3 shipped, and a fifth finding fell out of it

The bar's idle glyph moved from a darkening factor of 1.55 to 1.25, taking 7
themes under the threshold to none, with a floor of 4.71 rather than a value
sitting on 4.5. The factor now lives in `Model.BAR_IDLE_ALPHA` so a test calls
the shipping number instead of transcribing it.

The dimming loses range: the active glyph now reads about 1.57 times the
contrast of the idle one instead of 2.32. That is affordable **here and nowhere
else in this plugin**, because ruling R7 already requires a different glyph per
state. The dimming is decorative; the state is in the glyph.

Writing the test found **D-RUNG-5**. The check first asserted that the idle
glyph is dimmer than the active one in every theme, and it went red. On a light
theme, darkening the ink moves it away from a pale background, so the idle
glyph renders BOLDER than the active one: catppuccin-latte measured 11.00 idle
against 7.06 active, rose-pine 10.76 against 6.66. On the `white` theme they
are identical at 21.00, because darkening pure black does nothing.

That inverts the documented intent, it predates this change, and this change
narrows it rather than causing it. It is filed rather than absorbed, because
the real repair is to dim toward the BACKGROUND instead of toward black, which
is a different operation and belongs with the calibration pass.

The assertion was right about the world and wrong about the code. That is the
most useful kind of red.

## 16. The calibration, and the number that was never real (product owner, 2026-09-15)

Section 15 refused the per-theme contrast floor for three reasons and blocked
it on a calibration pass. That pass has now run. **One of the three reasons was
wrong, and it was wrong in a way worth recording, because it was wrong for
nearly a day and it changed a decision.**

### What was measured

The guide was opened on the live shell and captured with `grim`, twice on the
dark reference theme and once on a light one. For each sample, a tight crop
around the text; the modal colour of that crop is the background; the single
most-contrasting pixel in it is the fully-covered glyph stroke. The two
captures of the same theme agreed to two decimals.

| Theme | Surface | Rung | Model says | Screen says | Error |
|---|---|---|---|---|---|
| retropc | cursor row | 0.52 | 3.54 | 3.40 | -0.14 |
| retropc | normal row | 0.52 | 3.53 | 3.42 | -0.11 |
| retropc | normal row | full | 10.82 | 10.78 | -0.04 |
| catppuccin-latte | cursor row | 0.52 | 2.28 | 2.18 | -0.10 |
| catppuccin-latte | normal row | 0.52 | 2.38 | 2.33 | -0.05 |
| catppuccin-latte | normal row | full | 7.06 | 6.98 | -0.08 |

The predicted ink colours matched the measured pixels almost exactly as well:
the model said the dim rung on retropc renders `#896004` and the screen showed
`#826004`; it said full opacity renders `#ffb000` and the screen showed
`#feb000`.

**The model is accurate to within 0.14 ratio points**, on a dark theme and a
light one, at two opacities.

### Where 1.25 came from

Section 15 said the model reads about 1.25 ratio points low, on the strength of
`docs/QA-RESULTS.md:4720-4732`, which reported a rendered 4.79 where the model
computed 3.54. That comparison was not of the same thing.

The string measured was the failure notice, `! Failed 08:13 - Space to retry`.
It begins with a **glyph, drawn at opacity 0.8**, not at the 0.52 text rung.
On retropc, opacity 0.8 computes to **7.13** - which is, to the hundredth, the
figure that pass reported as its peak stroke. Its "glyph-body 4.79" sits
between the values for 0.62 and 0.7, consistent with a partially covered pixel
of that same 0.8 glyph.

So the old pass measured the glyph and compared it against a number computed
for the words. Nothing was wrong with either measurement; they were of
different things, and the mismatch was read as an error in the model.

**The claim is withdrawn.** It is pinned by
`tests/fixtures/contrast-calibration.json` and five checks, so it cannot come
back as folklore. One of those checks fails if a future lane widens the
tolerance to make a bad model pass, which is the obvious way to lose this
again.

### What this changes, and what it does not

**Reason 2 of the refusal is withdrawn.** The model can be trusted, so the
finding that the 0.52 rung is under threshold in 20 of 23 themes is real and
D-RUNG-2 is not blocked on measurement any more.

**Reason 3 is stronger than it was.** Every one of the six samples came in
BELOW its predicted value, never above. The model is slightly optimistic. A
design that computes exactly 4.50, as the refused one did, therefore renders at
roughly 4.40 on screen: under the threshold, on every theme, while every test
reports green. That is no longer a worry about unmeasured rendering effects. It
is measured, and it has a sign.

**Reason 1 is untouched.** Raising the rung still costs the guide its only
working hierarchy channel, dropping the name-versus-secondary separation from a
median of 2.86:1 to 2.24:1. That is a design question, not a measurement one,
and it is now the *only* thing standing between D-RUNG-2 and a fix.

### The ruling

D-RUNG-2 is unblocked and goes back for a redesign with two binding
constraints: **target above 4.5, never on it**, the way the bar glyph was given
a 4.71 floor; and **state the hierarchy cost at that higher target**, because a
higher target makes the separation loss worse, not better, and the previous
design costed it at the wrong number.

The lesson generalises past contrast. Two numbers that disagree are not
evidence that one is wrong until somebody has checked they are measurements of
the same thing. A day of work rested on a comparison nobody had audited, and it
looked exactly like diligence.
