# Contrast ruling: D-RUNG-2, D-RUNG-4, D-RUNG-5

Architect's ruling for the product owner, 2026-09-15. Read-only pass at
`25132d2`, tree clean, display never touched. Every figure below was
recomputed independently from `tests/fixtures/menu-contrast.json` (23 installed
themes) and `tests/fixtures/contrast-calibration.json` with a Python
implementation of WCAG 2.1 luminance, sRGB compositing and CIE L\*, written for
this pass rather than reused from the lanes. Where my figure and a lane's
figure disagree, mine is stated and the lane's is named, because this project
has already lost a day to a number nobody audited.

### Measurement rule, learned 2026-09-21

Three things the live pass of 2026-09-21 settled about the method above, which
every later measurement follows (evidence: `docs/QA-RESULTS.md`, "Live pass
2026-09-21, segment A", sections 1, 3 and 4):

1. **Capture the bar with the guide CLOSED.** The open guide's PanelWindow
   paints `Color.menu.scrim`, the background at alpha 0.5, over the whole
   screen, the bar included. A bar crop taken through it on this pass
   reproduces the D-RUNG-6 reading: the rose-pine bar crop peaks at
   `#a8a3b3`, 2.25, the addendum's figure to the byte, and
   `Model.colorOver(text, background, 0.5)` predicts each such reading one
   unit off in one channel (`#a9a3b3`, 2.24, for that pair; catppuccin's
   clock through the scrim `#757a91`, 3.87, against a predicted `#767a91`,
   3.87). On a settled closed-guide frame the host clock
   reaches its full text token (11.34) and our idle glyph its 0.86 rung (8.69
   against a model 8.72). D-RUNG-6 was a capture through the scrim, which
   settles the question the addendum's correction left open (section 3).
2. **The model's error is size-dependent.** 11 to 14 px text on the card
   renders within 0.10 of the model and the 28 px glyph and the bar glyph within 0.03
   (including the two shipped sites between alpha 0.6 and 0.9), but every
   10 px regular-weight caption renders 0.17 to 0.79 below it, 11 to 13 per
   cent of the ratio, while bold 10 px does not lose it. Hence F-CAL-1:
   fixture rows carry a `sizeClass`, captions get a relative tolerance, every
   other class keeps `maxAbsError` (section 1). Three text rows ON THE CURSOR
   FILL (tokyo-night 0.52, catppuccin 1.0 and 0.52) sit 0.17 to 0.25 off,
   beyond the text class: that residual is F-CAL-2, pinned by name in the
   fixture rather than absorbed by a tolerance, because the pass measured a
   different string on each surface and could not separate the surface from
   the glyphs. Until a pass measures one string on both surfaces, "within
   0.10" is a card figure.
3. **The cursor fill carries an alpha the model drops.**
   `Color.menu.selectedBackground` is `Util.alpha(foreground, 0.08)`,
   uncomposited, and `Model.qmlRgb` reads r, g, b and ignores a, so
   `cursorInk` receives the text colour as its fill and returns text on every
   theme. That is D-RUNG-13, and it is why the "after" ink in the addendum's
   table sits nearer the menu text than the 0.69 mix (section 4). Hand the
   model a composited fill, or it is modelling a colour that never paints.

## In one paragraph

Three separate dimming defects were designed and attacked. **Two are worth
shipping and one is not.** The bar's permanently-visible idle icon is dimmed by
an operation that makes it *brighter* instead of dimmer on five light themes,
including an exact no-op on `white`; the fix is simple, cheap, proven, and
should go first. The channel name and number on the highlighted row of the
guide are painted in the theme's accent colour, which is too faint to read
against its own highlight on eight themes and much worse on the number; that
fix should ship too, with four amendments, and it needs one small addition -- a
coloured rule down the left edge of the highlighted row -- because the
highlight itself is far too faint to say "this row is selected" on its own.
The third change, brightening the small grey second line under every channel
name, **should be refused**: it computes as a fix and behaves as one on twenty
themes, but on the three themes with the least colour range to spend it either
inverts the highlighted row or dims so little that it is invisible -- it would
pass every test and make the guide flatter. Nothing here has been seen on a
real screen yet, so the last action is a short capture session on two named
themes before anything else in this family is changed.

## What each lane asked for, and what the reviewers did to it

| Item | Design | Reviewer verdict | This ruling |
|---|---|---|---|
| **D-RUNG-5** bar idle glyph | Replace `Qt.darker` with alpha toward the real background at 0.86 | **Not refuted.** Ship with four corrections | **Accept**, ships first |
| **D-RUNG-4** cursor-row accent | Adaptive ink mix to a 4.70 floor, plus the number rung to full | **Not refuted.** Ship with four amendments | **Accept**, plus one addition (the selection mark) |
| **D-RUNG-2** the 0.52 rung | Per-theme contrast floor at 4.80 | Design **refused it itself**; reviewer accepted the refusal with seven corrections | **Refuse.** One carve-out ships |

---

## D-RUNG-5 -- the bar's idle glyph. ACCEPT.

**What was measured.** At the shipped `Qt.darker(barFg, 1.25)` the idle glyph is
*bolder than or equal to* the active one on 5 of 23 themes: catppuccin-latte
9.10 idle against 7.06 active, rose-pine 8.74 against 6.66, lupine 16.61
against 15.43, flexoki-light 19.01 against 18.62, and `white` 21.00 against
21.00, an exact tie because darkening pure black does nothing. `Qt.darker`
reduces HSV value, which moves the ink *away* from a pale background. On the 18
dark themes it works: separation 1.54x to 1.61x, median 1.58x.

The proposed operation is `Util.alpha(barFg, 0.86)` -- carry the ink toward
whatever is really behind it. Floor 4.77:1 (rose-pine, the binding theme at
6.66:1 of total range), 0 of 23 under 4.5:1, 0 of 23 inverted. The alpha table
reproduces exactly: 0.84 -> 4.56, 0.85 -> 4.66, 0.86 -> 4.77, 0.87 -> 4.88.

**Recommendation.** Ship it, one rule for all themes, no light/dark branch. A
branch would have an arm that runs on 5 of 23 themes and never on this machine,
which is an untested arm.

**Contrast gained.** 5 inverted themes become 0; the floor goes from a defect to
4.77 computed, about 4.56 to 4.62 rendered once the calibrated optimism is
subtracted. `white` dims for the first time, 21.00 -> 15.58. On light themes
the separation goes from 0.77x-1.00x (inverted or nil) to 1.35x-1.54x, so this
is the one change in the family that *adds* hierarchy where there was none.

**Hierarchy lost.** Stated honestly, which the design did not: on the 18 dark
themes -- including this machine's live catppuccin -- the separation falls from
1.58x to a median of 1.30x (range 1.250x to 1.381x, not the "1.25-1.41" the
design printed; 1.41 is catppuccin-latte, a light theme that leaked into the
dark bucket), and the CIE L\* gap falls from **15.6 to 9.2**. The design's
headline of "14.8 to 9.3" is the all-23 median, and it is depressed by counting
the five inverted themes' backwards gap as if it were dimming. The honest
framing is: the permanently-visible glyph carries more ink all day on the 18
themes where today's behaviour is correct, to repair five the user may not run.
That is affordable here and nowhere else, because ruling R7 gives every state
its own codepoint (verified: `Model.barGlyph` returns three distinct glyphs), so
the dimming is decorative, and because the bar has no name-versus-secondary
channel to spend.

**Reviewer.** Not refuted; four corrections, and one of them matters. The
design's boldest claim -- that mixing toward the ground never raises contrast on
a pair starting above 2.22:1 -- is a property of eight hand-picked inks, not of
the operation. I reproduced the counterexample myself: `#0000ff` on `#ffff00`
starts at 8.00:1 and rises to **8.33:1** at alpha 0.86. Scope the sweep to the
44 theme foreground/background colours, which is exactly the set
`omarchy-bar-text-color` can pick from, and the claim comes back true and far
stronger. This is the same error the design congratulates itself for catching,
committed one step further along.

**Corrections that must not enter the record wrong.** The comment destined for
`Model.js` says the accent fails in 15 themes at fill alpha 0.25; it is 19. The
`docs/STATUS.md` D-RUNG-5 row quotes "11.00 idle against 7.06" and "10.76
against 6.66" as measured at the shipped factor; those are the values at the
**retired** 1.55 -- at the shipped 1.25 they are 9.10 and 8.74. The defect is
still real and still 5 themes; only the magnitudes are overstated.

---

## D-RUNG-4 -- the accent ink on the cursor row. ACCEPT, with an addition.

**What was measured.** The accent on its own cursor fill, at full opacity, is
under 4.5:1 in **8 of 23** themes: rose-pine 2.7969, miasma 3.2612, nord
3.7720, catppuccin-latte 3.8650, solitude 4.0454, lupine 4.1461, osaka-jade
4.1520, white 4.2616. Not nine. everforest computes **4.8026** and was counted
at its two-decimal rounding of 4.80 by the D-RUNG-2 lane; that error and its
consequences are dealt with below.

The cursor fill is `menu.text` at alpha 0.08 and measures **1.115 to 1.230:1**
against the row fill in 23 of 23 themes, against WCAG 1.4.11's 3:1 for a state
indicator. There is no border: the generated `shell.toml` ships
`menu.selected-border` but no width, and both `Guide.qml:231` and the host's
`Menu.qml:95` pass a fallback width of 0. So the accent ink is, today, the only
thing that says which row is selected. Raising the fill is counterproductive
and monotonically so: the failing count goes 8 -> 19 at alpha 0.25 -> 23 at
0.50, because the fill moves toward the foreground and the accent sits between.

The guide's own invention is worse than what it inherited. `Guide.qml:2483` is
`opacity: row.hasCursor ? 0.8 : 0.52` on the channel number. The accent at 0.8
over the cursor fill is under 4.5:1 in **16 of 23** themes, floor 2.23, and no
ink can rescue it -- catppuccin-latte, everforest and rose-pine would need the
accent mixed away entirely for the number alone.

**Recommendation.** Ship `Model.cursorInk` -- return `Color.menu.selectedText`
unchanged where it already clears 4.70 against its own composited fill (15 of
23 themes, byte-identical on screen), else the least mix toward
`Color.menu.text`, in hundredths, that does. I reproduce the eight mix
fractions exactly (white 0.07, lupine 0.11, solitude 0.15, osaka-jade 0.18, nord
0.30, catppuccin-latte 0.35, miasma 0.42, rose-pine 0.70) and the resulting
floor of **4.7025**. Ship the number rung to full opacity alongside it; that is
forced, not chosen.

Four amendments before merge, all from the review and all confirmed here:

1. **`Guide.qml:2050` passes `selectedText: root.selectedText` to the host's
   `ConfirmDialog`,** whose selected non-destructive button draws
   `selected ? root.selectedText : root.foreground` over `root.selectedBackground`
   (`ConfirmDialog.qml:101,112`) -- the identical surface pair, failing in the
   identical eight themes, one keypress from the remove-source dialog. The
   design's gate asserts "zero surviving `hasCursor ? root.selectedText`" and
   reports clean over it. Pass `cursorInk` there and add the fifth counter.
2. **The number needs `max(0.8, alpha)` semantics or, better, the full-opacity
   rung the design already proposes.** Do not bind the site to a shared alpha
   that is below 0.8 in 20 of 23 themes; that would *dim* the focused row's
   number during numeric zap.
3. **Fix three figures before they set.** The cost retention median is **76.7
   percent** (mean 72.1), not 84 -- 84 is the upper-middle of eight, and the
   error runs in the direction that flatters the design. The number column's
   headline "2.23 -> 4.70" folds two changes into one delta; isolating the rung
   decision, the mixed ink still leaves **16 of 23** under 4.5 at opacity 0.8
   with a floor of **3.25**, so the honest figure is 3.25 -> 4.70. And the
   progress-hairline side observation (claimed 13 of 23, floor 1.88) does not
   reproduce under any compositing either reviewer or I could construct.
4. **Repoint the duplicated WCAG arithmetic in the same commit**, not as a
   "should". See the build order.

> **SUPERSEDED 2026-09-21 by product-owner ruling.** Three clauses of this
> section no longer describe what ships. (1) The mark is drawn in
> `Color.menu.text`, NOT `cursorInk`, and is pinned there. (2) It does not lie
> on the card: measured on screen, rose-pine x238 card / x239-240 mark / x241
> fill, so its right edge and both rounded ends abut the FILL, which is the
> neighbour that governs it -- against the fill the text token measures 5.94 at
> the floor and the raw accent would measure 2.80. (3) The cursor row's text is
> no longer inked at all: the mark means CURSOR and the accent means ACTIVE.
> The reasoning below is preserved as written because the decision it records
> was correct on the evidence available; what changed is that the evidence was
> computed against a fill that had never painted (D-RUNG-13).

**The addition, and it is the architect's call rather than a lane's.** Add a
selection mark -- a left rule, drawn in `cursorInk`, sited **outside** the
selected fill so it lies on the card. Measured: `cursorInk` against the card
background clears 3:1 in 23 of 23 with a floor of **5.286**. The raw accent
against the card is 3.136, which clears on paper and sits on the line once the
model's optimism is applied; and against the *cursor fill* the accent is
**2.797**, under 3:1, in the same theme that is worst on every other axis. So
the geometry is load-bearing: rule outside the fill, inked with `cursorInk`, or
the 3:1 claim is false.

**Contrast gained.** Cursor-row name and number: 8 of 23 under 4.5:1 becomes 0
of 23, floor 4.70 computed, about 4.65 rendered -- and note that this fix lives
at **full opacity**, where the calibration's measured error is smallest (0.4 to
1.1 percent, against 2 to 4.5 percent at 0.52). It is the best-supported target
in the family. The number column on the cursor row goes from 16 of 23 under
4.5:1 to 0 of 23. With the mark, the guide gets its first WCAG 1.4.11 state
indicator in its history: 5.29 against a fill that has been at 1.12-1.23:1
since v0.1.0.

**Hierarchy lost.** The accent desaturates in eight themes and in one of them
badly. CIE76 distance from `menu.text` retained: white 93 percent, lupine 90,
osaka-jade 84, solitude 84, nord 70, catppuccin-latte 67, miasma 57, **rose-pine
31**. Measured the way the eye actually works -- can I tell the cursor row's ink
from an ordinary row's ink -- the contrast between the two inks falls in all
eight, and on rose-pine from 2.12:1 to **1.26:1**. Fifteen themes pay nothing at
all. The second cost is documentary: `docs/M2-03-CHANNEL-NUMBERS.md:677` promises
the number renders dimmer than the name on the cursor row; it will now match it.
Nothing semantic is lost -- the number is subordinate by being digits in a
right-aligned digit column -- but the promise must be withdrawn in the same
commit. **The mark is what makes the rose-pine cost affordable:** once selection
is carried by a 5.29:1 rule, the ink separation falling to 1.26 stops being
load-bearing, and the design's one unanswerable objection ("a judgement about
perception that no arithmetic settles") becomes a judgement nothing depends on.

**Reviewer.** Not refuted. Every load-bearing figure reproduced to the
hundredth, the red proof was re-run rather than believed (8 red before, 0 after,
eight mutants rebuilt from scratch and all caught), and the fixture itself was
audited against the theme files on disk -- 22 of 23 exact, retropc alone having
no `colors.toml` and not among the eight.

---

## D-RUNG-2 -- the 0.52 rung. REFUSE.

**What was measured.** The 0.52 rung computes under 4.5:1 in **20 of 23** themes
on at least one fill -- 40 of the 46 theme-surface pairs, floor 2.24 (rose-pine
on the cursor fill), median 3.80 on the row fill and 3.64 on the cursor fill.
Real, reproduced to the hundredth, and no longer blocked on measurement since
section 16 withdrew the 1.25 claim. The site inventory is seven, not the three
the board names: five bare literals at `Guide.qml` 2128, 2483, 2700, 3025, 3058
plus two `Model.TEXT_DIM` bindings at 2532 and 2588.

**Recommendation: refuse the per-theme floor.** Not because the finding is
unreal, and not on measurement. Four reasons, in descending order of force.

**1. It inverts the row the user is looking at, and no target avoids it.** With
the accent still inking the cursor-row name, a floor at 4.80 makes the detail
line *more legible than the channel name* on 9 of 23 themes (8 accent failures
plus vantablack, which already inverts today at 5.63 secondary against 5.53
name). everforest escapes by 0.003 ratio points, and the model is optimistic, so
on a screen it is likely 10. Lowering the target does not save it: inversions run
9 at 4.5, 5 at 4.0, 3 at 3.5, 2 at 3.0. The binding constraint is the accent,
not the rung.

**2. And D-RUNG-4's fix does not unblock it.** This is the one piece of
arithmetic neither lane computed, and it is the spine of this ruling. With
`cursorInk` shipped at its 4.70 floor and the secondary driven to 4.80, the
cursor row **still inverts in 9 of 23 themes**, because the mix stops at 4.70
and the floor overshoots it. To get zero inversions with a mixed accent you need
an ink floor near 5.8, at which point the mix moves 13 of 23 themes and
rose-pine retains 11 percent of its accent distance -- the accent is gone in all
but name. Only `menu.text` at full makes a 4.80 floor safe (zero inversions,
name floor 5.94, and vantablack's pre-existing inversion closes with it). "Ship
them together" is therefore not enough; the *ink identity of the cursor row*
has to change, which is a divergence from the menu convention recorded at
`docs/UX.md:655-661` and a product-owner ruling.

**3. In the three themes that need it most, the fix is the option it
rejects.** The design rejects a single higher fixed rung by calling a CIE L\*
step of 8.4 "literally invisible dimming". Its own per-theme floor delivers
**6.2 on rose-pine, 7.9 on catppuccin-latte, 9.3 on everforest** -- the three
themes whose total range is under 7.4, and two of them the light themes a
daylight user picks. By `S x H = F`, which I confirmed is an exact identity
(max deviation 3.55e-15), a theme with 6.66 of range cannot buy 4.80 of
legibility and a visible step out of the same number. It *is* candidate (b)
there, at candidate (a)'s complexity.

**4. The margin is thinner than claimed, and lands where nothing was
measured.** The 4.80 target is the right shape and correctly above the line.
But its "0.30 of headroom" treats the calibration error as a flat 0.15 ratio
points, when the fixture's own explanation -- partial pixel coverage -- implies
a deficit in effective alpha, and the six samples confirm it varies: 2 to 4.5
percent relative at alpha 0.52, under 1.2 percent at full. The remedy puts 20 of
23 themes at alphas 0.57 to 0.90, a region with **zero calibration samples**.
Under a proportional reading a computed 4.80 renders near 4.59 to 4.66. Still
above 4.5 -- so the target survives -- but the headroom is roughly 0.1, not
0.30, and the proposed margin check passes by exact floating-point equality at
`4.5 + 2 * 0.15 == 4.8`, an assertion satisfied *at* a boundary in the lane
whose thesis is never to sit on one.

**Corrections to the record.** The design's central sentence -- "under 4.80 in 9
of 23 themes" -- is wrong; it is 8, and the 9 inversions are 8 accent failures
plus vantablack. Its inversion ladder mixes accent-failure counts with inversion
counts and is off by one at three of four rungs. Candidate (b) needs alpha
**0.9038** to clear 4.80 on both fills, not 0.95 -- it is by definition the
maximum of the design's own per-theme alphas -- and leaves a step of 6.43 median
/ 5.17 worst, not 3.3 / 2.7, so the rejected option's cost was inflated about
twofold. Its rejection still stands on the corrected numbers, 6.4 against 24.1.
And the carve-out, the one thing called shippable today, is costed against the
wrong surface: the numeric-zap chip carries its own fill
(`Style.normalFillFor`, foreground at alpha 0.04, `Style.qml:82,154`), so the
true range is **2.29-5.69 at 0.52 and 6.29-19.78 at full**, not 2.24-5.66 and
6.66-21.00. That is the wrong-surface error class this lane exists to catch,
committed inside the lane that names it.

**What ships now anyway.** The carve-out: `Guide.qml:2700`, the `- no match`
word in the numeric-zap chip, goes to full opacity. It is the sole signal that a
typed number matched nothing, UX 7.2 mandates the word and not a tint, GS8
already lifted the failure notice to full for that identical reason, and its
only competitor in the chip is the number buffer at 16px full opacity with no
accent anywhere near it. Floor 6.29. Zero inversion risk.

**Contrast that would have been gained.** 40 of 46 theme-surface pairs under
4.80 become 0, alpha 0.52-0.904 with a median of 0.652, three themes untouched
(hackerman, last-horizon, vantablack -- which is why the floor must be
`max(TEXT_DIM, needed)`; without the clamp vantablack would be *dimmed* from
0.52 to 0.47).

**Hierarchy that would have been lost.** On the 29 non-cursor rows: name-versus-
secondary ink ratio 2.86 -> 2.09 median, 2.33 -> 1.26 worst; CIE L\* step 32.8
-> 24.1 median, 26.6 -> 6.2 worst. On the cursor row: inversion in 9 of 23, the
primary content becoming the least legible text in its own row.

**What would have to change for this to be worth revisiting.** All four, and in
this order:

- **The cursor-row name stops being accent-inked** (decision 2 below goes to
  `menu.text`, with the accent surviving as the non-text mark). Without this,
  no target above 3.0 leaves the cursor row intact.
- **Per-surface alpha is re-costed rather than left rejected on a figure that
  does not exist.** The design dismissed it on "14 of 23", which neither
  reviewer nor I can reproduce under any reading. Sized for the row fill alone
  it holds the ink ratio at **2.34 median (worst 1.39)** and the L\* step at
  **27.8 median (worst 8.8)**, against 2.09 / 24.1 / 6.2 for the single alpha --
  materially better on the 29 rows that are not the cursor. Under a row-sized
  alpha the cursor fill lands at 4.14 floor, clearing 4.5 in 8 of 23 and 4.0 in
  23 of 23, so it needs the cursor row solved first, which is the same
  dependency.
- **A calibration sample exists at an alpha between 0.6 and 0.9.** One `grim`
  capture closes it, and the live pass already owes one.
- **The remedy survives its own standard in rose-pine and catppuccin-latte.** If
  the step there is still 6 to 8 L\*, the fix is invisible dimming in the themes
  that need it, and the right answer is to accept those themes explicitly rather
  than to move them.

---

## The shared primitive: no, and this is worth being blunt about

**Dimming toward the background instead of toward black does not answer more
than one of these, and lanes 1 and 2 must not redesign around it.** Mixing a
foreground toward the background in sRGB by `(1-a)` is arithmetically identical
to drawing it at opacity `a` over that background -- that is the definition of
alpha compositing, and I verified the identity holds exactly. So every opacity
rung in the guide **already performs this operation**. The bar was the only site
in this plugin dimming toward *black*, which is precisely why it was the only
site that could invert. Switching operations moves D-RUNG-2 by exactly zero
(0.52 opacity already is 0.48 toward the background), and D-RUNG-4 is worse than
unaffected: its accent is under 4.5:1 at full opacity, so no dimming operation of
any kind can reach it and mixing toward the background makes it strictly worse.

This is not the thing that gets contrast and hierarchy at once. Nothing found
here is. `S x H = F` is an identity, so among remedies that move only the dim
rung, every ratio point of legibility bought costs exactly its proportion of
hierarchy. The only way to get both is to **change what the ink is or what the
row is**, which is what the cursor-row mark does: it adds a channel (a
non-text rule at 5.29:1) that no opacity arithmetic can produce.

**Two things do generalise, and they should be written down as rules.**

1. **The calibrated-target derivation.** Choose any constant so that
   `floor - contrast-calibration.maxAbsError > 4.5`, reading the tolerance from
   the fixture rather than restating it, so that widening the tolerance to hide
   a bad model breaks the decision as well as its own check. That gives section
   16's "above 4.5, never on it" an arithmetic definition. Amend it with what
   the samples actually show: the error is proportional to alpha, so a
   translucent target needs more margin than a full-opacity one, and no target
   should be set in an alpha region the fixture has never sampled.
   **Amended again 2026-09-22, and the first version of this amendment was
   itself wrong.** It said the live display and headless cage rasterise text
   differently and that tolerance must therefore be drawn per environment, on
   the strength of a -0.376 against -0.048 split. That split was confounded with
   size class, and the rows underneath it were a different BUILD, not a different
   environment (F-CAL-3 withdrawn, F-CAL-4). What stands:
   - A row records the **build** that rendered it, not only the environment. The
     variable that broke this was which component the process had loaded, and a
     correct-looking `env` did not catch it.
   - A target may still only be certified against **live** rows: cage is a test
     convenience and nobody looks at it.
   - Whether the two environments differ is **UNKNOWN**, in either direction. The
     peak-pixel statistic is a MAX over a glyph run, so it saturates to the 8-bit
     composite as soon as one pixel is fully covered. Its resolution is one LSB,
     about 0.05 ratio points on these backgrounds, and it is blind by
     construction to hinting, subpixel positioning and scale -- the very
     mechanisms an environment difference would act through. Any figure quoted
     finer than 0.05 from this method is spurious precision; D-RUNG-14 once
     rested on -0.0007.
   - Therefore **no target may be set on a margin under about 0.15**, the
     fixture's own tolerance, and a decision that needs finer resolution needs a
     different instrument: the coverage distribution over the run, not its
     maximum.

3. **Contrast is not monotonic in the parameter, and nothing may assume it is.**
   D-RUNG-16 and D-RUNG-17, 2026-09-23. `colorOver` and `colorMix` interpolate
   in gamma space and `relativeLuminance` is convex, so a blend sits below the
   line between its endpoints and the contrast curve can peak in the interior:
   `#c50236` over `#20f91e` reads 4.3973 at 0.70, **4.7318 at 0.83** and 4.2580
   at 1.00. Two consequences, and both were live in this codebase in three
   places:
   - **Never short-circuit on the endpoint.** "If full opacity cannot clear the
     target, nothing can" returns a failing answer with a passing one two steps
     away.
   - **Never fall back to the endpoint.** It is an arbitrary pick and can be the
     worst option available. Fall back to the parameter that maximises contrast.
   Search for a target with `alphaForContrast` or `mixForContrast` and do not
   write a third copy of either loop -- the bug outlived its own discovery by a
   day precisely because the search existed twice and only the newer copy was
   audited. And note WHY it survived: no installed theme can reach either
   branch, so nothing tested them. An unreachable branch is an untested one, and
   in a file this heavily asserted that is where the next one will be too.

2. **One arithmetic, called by both sides.** The WCAG formula currently lives
   only in `tests/Model.test.js:669-693`, which was fine while nothing shipped a
   decision made with it. Two of these changes do. `relativeLuminance`,
   `contrastRatio`, `colorOver` and `colorMix` move into `Model.js` and the
   existing GS8, D-RUNG-3, D-RUNG-5 and calibration checks stop keeping a private
   copy. `colorOver` is the load-bearing half: `menu.selected-background` is not
   a colour, it is `menu.text` carrying alpha 0.08, and a version that forgets
   that passes nothing.

---

## Build order

Sequential. Not one of these steps may run in a parallel worktree, because every
one of them writes `Model.js` and `tests/Model.test.js` and the coupling is the
arithmetic, not the subject matter.

**Step 0 -- the arithmetic lift.** Move `relativeLuminance` / `contrastRatio` /
`colorOver` / `colorMix` into `Model.js`; repoint the existing checks off their
private copies. No behaviour change, no count change, one commit. It goes first
because both remaining fixes make a shipping decision with this arithmetic and
rule 12 forbids two implementations of it in one repo.

**Step 1 -- D-RUNG-5, the bar.** `Util.alpha(barFg, Model.barGlyphAlpha(...))`
at 0.86. Includes the sweep rewritten over the 44 theme inks, the honest
dark-theme cost (15.6 -> 9.2), the `docs/STATUS.md` figure correction, and
`docs/UX.md:682`, which still names the retired 1.55. Gate: `scripts/check.sh`
green, `qmltestrunner`, plus the QML spec case -- the node suite cannot see a
value the QML engine coerced from a string.

**Step 2 -- the live pass and calibration top-up.** Before any further contrast
change. Capture **rose-pine** (the binding theme for both the bar floor at 4.77
and the cursor floor at 4.70) and one high-range dark theme, with the playing and
idle bar glyphs in the same frame, and one sample at an alpha between 0.6 and
0.9. Add the rows to `tests/fixtures/contrast-calibration.json`. Three contrast
changes are now stacked and none has been seen on a screen.

**Step 3 -- D-RUNG-4, the cursor row, as one commit.** `cursorInk`, the number
rung to full, the `ConfirmDialog` site at `Guide.qml:2050`, the selection mark,
the `docs/M2-03-CHANNEL-NUMBERS.md:677` withdrawal, the host-divergence ruling,
and the `- no match` carve-out riding along so one capture covers it.

**Step 4 -- D-RUNG-2.** Only if decision 2 goes to `menu.text`, and only after
the per-surface option is re-costed against the corrected numbers. Otherwise the
board row closes as accepted, with the accepted risk named.

## File ownership, and every file more than one item wants

| File | Wanted by | Ruling |
|---|---|---|
| `Model.js` | **0, 1, 3, 4** | Sequential only. Whoever holds the step owns the whole file for that step. Never split by constant |
| `tests/Model.test.js` | **0, 1, 3, 4** | Step 0 rewrites the block step 1 edits, so **steps 0 and 1 are the same owner**. Splitting them puts the lift and the bar's retired checks in two hands over the same lines |
| `Guide.qml` | **3, 4** | Same owner. Step 4's floor binds the same seven sites step 3 rewires; two owners would produce two half-answers, which is what the board already said about splitting D-RUNG-2 from D-RUNG-4 |
| `docs/UX.md` | **1** (line 682, bar glyph), **3** (lines 655-661, menu convention) | Different paragraphs, same file, sequential. Step 3 is the one that diverges from the convention and must say so in the convention's own paragraph |
| `docs/UX-GUIDE-AT-SCALE.md` | **1, 3, 4** | Append a new section per step. Do not edit sections 15 or 16; correct them by superseding, the way 16 superseded 15 |
| `docs/STATUS.md` | **1, 3, 4** | Every step moves a row. Step 1 also corrects the D-RUNG-5 row's two figures and adds a pointer to the D-RUNG-3 row saying its factor no longer ships |
| `scripts/check.sh` | **1, 3** | Both move `NODE_CHECKS_MIN` / `QML_SPEC_MIN`. Whoever lands second re-reads rather than re-deriving |
| `tests/fixtures/contrast-calibration.json` | **2**, read by **1, 3, 4** | Only the display-holding lane writes it. Everything else reads `maxAbsError` by call, never by transcription |
| `BarWidget.qml`, `tests/Model.spec.qml`, `tests/a11y/make_hosts.py` | **1** only | Clean |
| `docs/M2-03-CHANNEL-NUMBERS.md` | **3** only | Clean |

## What none of this fixes

- **F-HOST-1 -- Omarchy's own desktop.** `Menu.qml:1242,1284,1326` and `Clipboard.qml:508`
  draw the identical `hasCursor ? Color.menu.selectedText : foreground` over the
  identical fill and fail in the identical eight themes. The launcher and the
  clipboard picker stay as they are. The guide either diverges or waits; this
  ruling chooses to diverge and to say so. The upstream repair belongs to
  `menu.selected-text` in `/usr/share/omarchy/default/themed/shell.toml.tpl`,
  which is package-owned and read-only from here -- file the observation, do not
  write the file.
- **F-RUNG-8 -- The selected fill is still not a state indicator** at 1.115-1.230:1 against
  3:1, in 23 of 23 themes, with no border in any of them. Only the mark
  (decision 3) changes that, and only on the guide's own rows.
- **D-RUNG-9 -- The host's section headers.** `Ui/PanelSectionHeader.qml:18` is
  `Qt.darker(foreground, 1.4)`, instantiated at `Guide.qml:2230` (the GROUPS
  header) and `3173` (Sources form labels): under 4.5:1 in 3 of 23 (everforest
  3.80, gruvbox 4.25, tokyo-night 4.28) and bolder-or-tied than body text in the
  same five light themes, `white` an exact tie again. Same defect class as
  D-RUNG-5, inherited rather than invented, and untouched here.
- **D-RUNG-10, D-RUNG-11, D-RUNG-12 -- Three adjacent guide sites.** The cursor-row EPG progress hairline (D-RUNG-10, under
  3:1 in 15 of 23 by my computation, floor 1.80 -- worse than the design
  claimed, and its 13/1.88 reproduces under no compositing), the empty-state and
  first-run glyphs at 28px (under the large-text 3:1 in 2 of 23, rose-pine 2.42,
  miasma 2.97; D-RUNG-11), and the **non-cursor** channel number at 0.52 (D-RUNG-12, under 4.5:1 in 20
  of 23, floor 2.33), which is a D-RUNG-2 site the board's row never listed.
- **F-UX-1 -- The guide has no scrollbar.** `grep -c ScrollBar Guide.qml` returns 0, so the
  header scope label (`All - 1,204 of 3,335`) is the only position indicator on a
  3,335-row list. Refusing D-RUNG-2 leaves that string at 0.52. It was
  classified as ambient; it is read.
- **Contrast is not legibility.** Nothing here touches the 11px detail line, the
  10px caption, the pinned row height, or the four installed font faces. The
  guide's hierarchy will still be carried by 14px against 11px, line position,
  and Bold meaning "playing".
- **Every finding above now carries an id** (minted 2026-09-21 in phase 3d,
  each with a `docs/STATUS.md` row, severity and state, in the same commit --
  rule 13). The read-only pass that wrote this section minted none,
  deliberately; the desk pass that closed the board did. "Contrast is not
  legibility" is an observation about method, not a defect, and stays unfiled.

## Decisions

**1. Ship the bar fix (D-RUNG-5) at alpha 0.86, one rule for all themes.**
*Recommend: yes.* Cost: the 18 dark themes, including this machine's live
catppuccin, lose dimming range -- separation 1.58x to 1.30x, L\* gap 15.6 to
9.2 -- on the one element of this plugin that is on screen permanently. Gain: 5
inverted or tied themes become 0, the floor becomes 4.77, and `white` dims for
the first time.

**2. The cursor row's name ink.** Option A: `cursorInk`, the adaptive mix to
4.70, which leaves 15 themes byte-identical and desaturates 8. Option B:
`Color.menu.text` at full, which is a 5.94 floor, zero inversions, and the only
option under which D-RUNG-2 could ever be fixed.
*Recommend: A.* Cost: rose-pine keeps 31 percent of its accent distance and its
ink separation from an ordinary row falls from 2.12:1 to 1.26:1; eight themes
diverge from the Omarchy menu beside them; and D-RUNG-2 stays closed. B's main
prize is a fix this ruling refuses on independent grounds, so it is not worth
changing all 23 themes to buy.

**3. Add a non-text selection mark -- a left rule, in `cursorInk`, sited outside
the selected fill.** *Recommend: yes, in the same commit as decision 2.* Cost:
1 to 2 px of row content width to reserve, and a divergence from the host menu
on all 23 themes rather than 8. Gain: the first WCAG 1.4.11 state indicator this
guide has ever had, floor 5.29 against the card; it is what makes decision 2's
rose-pine cost affordable; and it is the prerequisite if the product owner ever
wants route B, so shipping it now avoids a second unseen contrast change later.

**4. Cursor-row channel number: 0.8 to full opacity.** *Recommend: yes; it is
forced.* At 0.8 the number is under 4.5:1 in 16 of 23 themes with the raw accent
and still 16 of 23 with the mixed ink, and three themes cannot be rescued by any
ink. Cost: `docs/M2-03-CHANNEL-NUMBERS.md:677`'s promise that the number is
dimmer than the name on the cursor row is withdrawn; subordination is carried by
the right-aligned digit column, by being digits, and by weight on a playing row.

**5. D-RUNG-2, the 0.52 rung: refuse the per-theme floor.** *Recommend: refuse,
and record the accepted risk on the board rather than leaving the row "open".*
Cost, stated plainly so the acceptance is honest: 20 of 23 themes keep a detail
line -- the EPG text, the reason the product exists -- computing 3.80 and 3.64
at the medians and 2.24 at the worst, along with the header scope label, the
Sources detail line, and the non-cursor channel number at a 2.33 floor. Reopen
only against the four conditions listed above.

**6. Ship the carve-out: `- no match` at full opacity.** *Recommend: yes, riding
with decision 2's commit.* Cost: none measurable -- floor 6.29 on the chip's own
fill, no accent in the chip, a 1.6x size step against its competitor. It is the
GS8 argument applied to the one place UX 7.2 mandates a word and not a tint.

**7. Rule explicitly on the host divergence.** *Recommend: accept it and name
the eight themes in the ruling, then file the upstream observation against
`menu.selected-text`.* Cost: the guide's cursor row reads differently from the
menu next to it -- in 8 themes for the ink, in all 23 for the mark. The
alternative is accepting the guide's own worst contrast site on the grounds that
somebody else's code has a milder version of it.

**8. Make the live pass a gate, not a follow-up.** *Recommend: yes -- no further
contrast change in this family merges before it.* Cost: one session from a lane
that holds the display. It must capture rose-pine, not `white` or
catppuccin-latte: rose-pine is the binding theme at 4.77 and 4.70, where the
others sit at 5.00 and 15.58 and prove nothing about the floor. The alpha region
0.6-0.9 has never been sampled and two of these fixes land in it.

**9. File the unnamed findings as one batch.** *Recommend: yes, with the
step-1 commit.* Cost: roughly nine new P3 rows on the board -- the host section
headers, the progress hairline, the empty-state glyphs, the `ConfirmDialog`
site, the non-cursor number column, vantablack's pre-existing cursor-row
inversion, and the guide's missing scrollbar -- each with a severity and a
state. They will make the board look worse. They are already true.
---

## Addendum: the live pass, and what it changed (product owner, 2026-09-15)

PO decision 8 made the live pass a gate rather than a follow-up. It ran on
rose-pine, the binding theme, and it earned that status twice.

### D-RUNG-4 is confirmed, defect and fix both

Captured with `grim` on the running shell, same crop before and after:

| | ink | measured | model said |
|---|---|---|---|
| cursor-row name, before | `#5d94a0` | **2.78:1** | 2.80 |
| cursor-row name, after | `#59537e` | **5.83:1** | 4.72 |
| selection mark, on the card | `#575279` | **5.98:1** | 5.30 |

The defect modelled almost perfectly. The fix overshoots its target in the safe
direction, and the ink the runtime chose is nearer the menu text than the 0.69
mix the model computes. That disagreement is filed as **D-RUNG-7** rather than
enjoyed, because the previous item on this page is what happens when a model
and a runtime quietly disagree.

### D-RUNG-6: the bar was never the surface we modelled

The same pass found that `tests/fixtures/menu-contrast.json`, which every
contrast conclusion on this project has been drawn from, does not describe the
bar. Measured on rose-pine: the bar's own full-strength text renders at
**2.25:1**, where the model says 6.66. The ceiling on the real bar is about
2.25, so no icon in it can reach 4.5:1, ours included.

The mechanism is now known and is worth writing down, because it invalidates a
premise rather than a number. **There is a generated
`~/.local/state/omarchy/current/theme/shell.toml`** that sets `[bar] text` and
`[menu] text` explicitly, and it is regenerated on every theme switch. The
fixture was built from `colors.toml`. For the menu the two agree, which is why
the guide's numbers reproduce to two decimals. For the bar they do not.

An earlier grep for bar overrides looked in `/usr/share/omarchy/themes/` and
`~/.config/omarchy/themes/` and found none. The file is in neither place.
**That grep is why the false claim shipped**, and it is the same failure this
project has now hit in four different costumes: a search that looked where the
thing was not, and returned nothing, and was read as evidence of absence.

### What this means for anything built on that fixture

Every threshold claim drawn from `menu-contrast.json` is valid for the MENU
surface and unproven for any other. D-RUNG-1 and D-RUNG-2 are menu-surface
claims and stand. D-RUNG-3's bar claim did not and is withdrawn. Before the
next contrast decision on a surface that is not the guide's own rows, build a
fixture for that surface by measuring it, not by deriving it.

### Correction to the addendum above (product owner, 2026-09-15)

**The mechanism given above for D-RUNG-6 is wrong**, and it is left in place
rather than rewritten so the error is visible.

I wrote that a generated `shell.toml` sets `[bar] text` and `[menu] text` to
different values, and that the fixture matched one and not the other. Three
review lanes checked the template at
`/usr/share/omarchy/default/themed/shell.toml.tpl` and I confirmed it: it writes
`[bar] text = {{ foreground }}` and `[menu] text = {{ foreground }}`. **The same
key into both sections.** I read a colour under `[bar]` in the generated output
and called it an override. It is the theme foreground, identical to the menu's.

The observation stands: the bar's text measured 2.25:1 on rose-pine where the
model says 6.66. The rendered deficit solves to alpha 0.5031, 0.5000 and 0.5000
on the three channels, which points at something drawing bar content at half
opacity rather than at any token. But two innocent explanations are now live and
neither is excluded. The capture may have caught the 420 ms `barForeground`
animation mid-flight. Or the peak-pixel method may have under-read a thin glyph
stroke, which the calibration fixture in this very repository already documents
it doing by 7 to 9 per cent on small text.

So the P2 may evaporate. What does not evaporate is the lesson, and it is the
same one twice in one day: **I reasoned from a file I had found to a mechanism I
had not tested.** The first time, a grep in two directories missed a file in a
third and I read absence as evidence. The second time I found the file and
misread what was in it. Both times the conclusion was stated with more
confidence than the evidence carried.
