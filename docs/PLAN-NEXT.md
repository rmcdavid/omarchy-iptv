# PLAN-NEXT: the four design passes, what survived, and the order to build them

Measured against `main` at `43c1b85` (`docs: both accessibility reports filed
upstream`, docs-only on top of the `779d121` the four lanes measured against;
`git show --stat 43c1b85` touches `docs/ACCESSIBILITY-INVESTIGATION.md` and
`docs/STATUS.md` only, so every code citation below still holds). Working tree
clean, nothing committed by this pass, no display used.

---

## 1. Summary for the product owner

Four problems were designed and then attacked by a second reader who re-ran the
numbers. **Two of the four should be built roughly as proposed; two should be
built at about half their proposed size, and the halves being cut are the ones
that would have made the product worse.** The search fix is ready and is the
clearest win for the user - on your own 3,335-channel list, typing `sta` today
reports "3,335 matches" when 67 channels actually match, and puts 133 junk rows
on the first page; the fix removes that on every query at every length. The
low-contrast text finding is real for one of the five dimness levels the guide
uses - the faintest one is unreadable in every installed theme and should be
raised this week - but the larger proposal to recompute dimness per theme was
refused, because it would spend the guide's only working visual hierarchy on
the strength of a calculation that disagrees with the one real screenshot
measurement this project has ever taken. The credential-on-screen-reader fix
was refused in its main part too: the "one small edit" was measured to break
the Xtream login form so badly that a user cannot type their username at all.
And the accessibility test harness works and should be kept, but as a tool the
team runs, not as a gate on every commit, because it would be permanently red
and it certified a data-losing bug as green. **Nothing here needs a decision
you cannot make from the numbers in section 6; the only one with real cost
attached is decision 8.**

---

## 2. The four items

### Item A - the dim rung (low-contrast text in the guide)

**Refuted in part. Split: ship a quarter of it, refuse the rest for now.**

**What was measured, and reproduced by the reviewer**

- The guide uses five dimness levels (0.45, 0.52, 0.58, 0.70, 0.80) plus full.
  Only two exist as named constants (`Model.js:4056-4057`, `var TEXT_DIM =
  0.52` / `var TEXT_FULL = 1`); the rest are bare literals in `Guide.qml`. The
  authority that names all five is `docs/UX.md:613-631`.
- **The 0.45 level is not dim, it is unreadable.** Across all 23 installed
  theme token sets, every single theme falls under the 4.5:1 accessibility
  threshold on at least one of the two surfaces the text can sit on. Worst
  1.98:1, median 3.17:1. It carries the footer status line
  (`Guide.qml:3391`), the footer's verbs (`Guide.qml:531`), the group entry
  count (`Guide.qml:2243`) and the Sources pinned count (`Guide.qml:2329`).
  The reviewer re-derived this independently and agreed.
- The guide has no other hierarchy channel left to spend. The installed
  JetBrainsMono ships exactly four faces and Bold already means "playing"
  (`Guide.qml:2541`); the row height is already pinned at `max(52, 51)`
  (`Guide.qml:248`, `Style.qml:256`). Both sides agree.
- A single fixed raised level cannot work: 0.874 is the smallest alpha that
  clears 4.5:1 in all 23 themes, which is not dimming at all. `Color.muted` as
  an alternative ink is worse (under threshold in 23 of 23). Both rejections
  reproduced.
- The rungs are inherited verbatim from Omarchy's own pickers
  (`/usr/share/omarchy/shell/plugins/menu/Menu.qml:1297, :1317, :1400, :1411`),
  so any fix makes the guide read differently from the menu beside it.

**What the reviewer refuted, and I confirm by my own reading**

- **"BarWidget asks for no rung at all; the dim rung is a guide-only problem"
  is false.** `BarWidget.qml:66` reads `property color glyphColor: root.playing
  || root.hasError ? root.barFg : Qt.darker(root.barFg, 1.55)` - the idle bar
  glyph is dimmed by a different mechanism, named outright at
  `docs/UX.md:663-664`, a line the design cited for something else. Measured by
  the reviewer: under 4.5:1 in 7 of 23 themes. **This is the one element of the
  plugin on screen permanently.** See decision 3.
- **"Nothing on this machine has ever compared a rendered pixel to the computed
  value" is false.** `docs/QA-RESULTS.md:4720-4732` is exactly that comparison,
  taken off screenshots on the reference theme and repeated on a second
  capture. It reports 4.79:1 rendered where the model computes 3.54:1. **On the
  one theme where both numbers exist, the model fails and the screen passes.**
  That single fact is why the larger half of this item must wait.
- Counts: I re-ran the inventory. `Guide.qml` has 30 `opacity:` assignments, of
  which 22 carry a decimal literal and 2 call `Model.rowNoticeEmphasis`
  (`:2504`, `:2560`), for **24 rung-bearing sites, not 28**. Six are boolean
  fades (`:2120, :2687, :2702, :3035, :3050, :3212`).
- The proposed wholesale substitution at `Guide.qml:2455` provably does
  nothing: the line is `opacity: row.hasCursor ? 0.8 : 0.52` and the cursor
  branch is inked with the accent, which no alpha floor can fix (accent at full
  is still under threshold in 8 of 23 themes).
- `Guide.qml:2939` and `Guide.qml:3003` carry the identical expression
  `srow.isSource ? 1 : 0.7` today. The floor would raise the label and exempt
  the glyph, leaving the icon visibly fainter than the text it labels in 20 of
  23 themes - a new inconsistency the design did not see.
- The proposed signature change to `rowNoticeEmphasis` is inert and churns a
  shipped API and eight assertions for nothing.

**Where it would make the product worse - REFUSE this part**

The per-theme floor pays a measured cost: the name-versus-secondary separation
on a non-cursor row drops from a median of 2.86:1 to 2.24:1, and to 1.35:1 in
the worst theme. It pays that on the strength of a model that is off by 1.25
ratio points in the one case we can check, in the direction that says the
screen is fine. And after the floor, all 23 themes land at **exactly 4.50** -
no margin at all - while the proposed test asserts 4.50. That combination can
go green on every layer while the screen is under threshold and the hierarchy
is already spent. **Refuse the floor until the calibration exists.**

**Recommendation**

- **Stage A1, now:** raise the four 0.45 sites only. Zero of 23 themes can
  carry that level; the finding survives the known model error (median 3.17
  plus the worst observed model error of +1.25 is still 4.42, under the line),
  which is exactly what the 0.52 finding does *not* survive (median 3.64-3.80
  plus 1.25 clears it). This is the whole argument for splitting here, and it
  is arithmetic, not taste.
- **Stage A2, next:** calibrate. The method already exists in this repo
  (`docs/QA-RESULTS.md:4720-4732`): sample rendered luminance off screenshots,
  glyph body and peak stroke, repeated for stability. Run it on the reference
  theme plus one light theme at the 10px caption size. Reconcile the model to
  the pixels or record the offset.
- **Stage A3, only after A2:** decide the 0.52 rung, with a target above 4.5,
  not on it.
- **Separately:** file the bar idle glyph as its own defect with the 7 themes
  named.

**Cost.** A1 is four literals in `Guide.qml` plus one amendment to
`docs/UX.md:756-757` and a `docs/STATUS.md` row: under an hour plus review. A2
is a display-lane pass, half a day. A3 is the original half-day estimate
(about 60 lines in `Model.js`, 20 changed lines in `Guide.qml`, ~100 lines of
tests) and is not scheduled here.

---

### Item B - credentials on the accessibility bus (D-A11Y-1)

**Refuted on the parts that carry weight. Split: ship the documentation half,
refuse the product change.**

**What was measured, and reproduced by the reviewer under independent probes**

- The accessible Value of an editable Qt control is its *display* text, so the
  binding at `Guide.qml:3150` is the sink. A revealed URL field publishes full
  credentials; a masked one publishes the masked rendering.
- **`Accessible.passwordEdit` at `Guide.qml:3173` is inert in both
  directions.** Confirmed by two lanes independently, with the Qt header cited
  (`qquickaccessibleattached_p.h:92-93`). `docs/UX-SOURCES.md:1192` asks for a
  name *and* passwordEdit together, which Qt 6.11.2 cannot deliver.
  `docs/UX-SOURCES.md:1165` says the same false thing and must move with it.
- **The password field currently has no label on the bus at all.**
  `Guide.qml:3172` sets `Accessible.description` to `""` whenever the field is
  not maskable, and the password is not maskable, so the placeholder fallback
  cannot fire either. Name empty, description empty.
- The Xtream username is the same secret that `maskUrl` masks one row above and
  publishes raw one row below. This is the indefensible half of D-A11Y-1 and
  both lanes agree.
- `Accessible.ignored` removes a node entirely; a role override empties the
  Value but breaks the field. Both alternatives correctly rejected.

**What the reviewer refuted**

- **"No text events exist on this Qt" is false, and it is load-bearing.** A
  whole-property assignment to `text` - precisely what `Guide.qml:3150` does on
  every mask and every reveal - raises `TextUpdated` carrying the full
  plaintext in both the inserted and the removed payload. It fires on normal
  fields, on the password field whose Value reads as bullets, and on
  `Accessible.ignored` fields alike. So the state the design calls safe leaks
  on the way into itself, the password is not the one safe field, and the
  ruling the design proposes would declare a channel closed that is open.
- **The "one edit, everything for free" claim bricks the form.** I confirmed
  every link in the chain by reading the shipping code: `Model.js:5529` sets
  `revealed` only `if (isUrlField(id))`; `Model.js:5388` rebuilds `revealed` as
  literally `{ playlist, epg }` on every state copy; `Model.js:5607` hardcodes
  the same two keys on submit; `Guide.qml:1702` returns early from
  `fieldEdited` while a field is masked; `Guide.qml:1795-1800` implements
  "masked = fully selected", replacing the whole value on every keystroke. Make
  the username maskable without touching those five sites and **the user types
  `joe` and the field holds `e`.**
- **The proposed sink test is a tautology.** It asserts `Value ==
  fieldDisplay(...)`, with the mutated function on both sides of the equality;
  the reviewer built it and it stayed green with the full credential on the
  sink.
- The proposed one-word edit to `CLAUDE.md` rule 5 would make the rule wrong at
  `Guide.qml:2062-2064`, a plain `Text` with an editable role that publishes
  the search query from `text`, not `displayText`.

**Where it would make the product worse - REFUSE this part**

Masking the Xtream username as scoped makes the login form unusable. Even
plumbed correctly across all five sites it is a regression: the username is the
field a user most often re-reads against a provider email, and a fixed-length
mask means they cannot tell an empty field from a filled one, while the
password directly below shows true-length bullets. **Refuse the username
masking as designed.**

**Recommendation**

- **Ship now (zero UX cost, all measurement-backed):** delete
  `Guide.qml:3173`; correct the false comment at `Guide.qml:3171`; give the
  password its label through `Accessible.description`; amend
  `docs/UX-SOURCES.md:1165` *and* `:1192` in the same commit; fix `CLAUDE.md`
  rule 5 with the correct two-part statement (text-input-derived controls
  publish `displayText`, every other annotated item publishes `text`) and add
  the text-event payload as its own named sink.
- **Refuse** the username change pending decision 8 and a real plumbing
  estimate.
- **Re-ask the server-field question** with the state the code already
  anticipates: a full provider login string pasted into the Xtream server
  field is unmaskable, has no eye button, and publishes forever; and a URL with
  both embedded userinfo and path credentials publishes the path credential in
  the *description* too.

**Cost.** The doc-and-comment half is one session: three changed lines in
`Guide.qml`, four doc rows, one `CLAUDE.md` sentence. The refused half was
estimated at "50-70 lines"; the true cost is five `Model.js` sites plus a UX
ruling plus its own regression tests.

---

### Item C - verify accessibility for real (the AT-SPI harness)

**Not refuted. Accept as a tool; refuse to make it a commit gate.**

**What was measured, and independently reproduced end to end**

- The guide's content instantiates in a plain hidden Qt window, publishes a
  real accessibility tree, and a stdlib-only Python client walks and asserts
  it: 19 checks in 7.5 seconds, trees of 37/43/45 nodes rebuilt from the repo's
  own `Guide.qml`, 54 nodes at 10,000 channels. The reviewer re-ran it and got
  the same numbers twice.
- No new dependency, no global state touched, no window mapped on the
  compositor, `git status` clean before and after. Verified by both lanes.
- It catches D-A11Y-1 at the real sink, where the existing grep
  (`docs/QA-SOURCES.md:243`, literally "A grep") passes cleanly over it.
- It settled `Guide.qml:3173` by mutation, agreeing with item B's independent
  C++ probe. Two lanes, two toolchains, one answer.

**What the reviewer corrected**

- "First time ever" is false - `docs/ACCESSIBILITY-INVESTIGATION.md` 4.6(a)
  already records the credential observed at the sink.
- Three of the five "new defects" are already tracked in the same document the
  design cites throughout; two more rest on a state observation that
  contradicts 4.6(f) without the conflict being raised.
- **The fidelity assertion the whole anti-drift argument rests on does not
  exist** in the prototype. It is described in the present tense and is not
  built.
- BarWidget is not in the harness at all; the checker launches 3 scenarios, not
  4, and the Xtream scenario - the one covering the fields that leak with no
  reveal - is never run.
- The platform matrix was measured through an environment confound that killed
  the processes before any bridge question arose. The conclusion survives a
  clean re-run; the individual readings do not.

**Where it would make the product worse - REFUSE this part**

Two things:

1. **The "validated fix" corrupts user data.** The design's mutation 7 rebinds
   the field text to the masked rendering and reports "19 checks, 0 failures -
   the check confirms the proposed remedy closes it." Traced through the
   shipping code and measured with node: `Guide.qml:1702` only guards while the
   field is *masked*, so on a revealed field the masked string is fed back
   through `onTextChanged` into the stored value, survives sanitisation, and
   validates clean. A user who clicks the eye to check a pasted provider URL
   gets their credentials silently replaced and the source saves with no error.
   The check cannot see it, because absence of a secret is all it asks. **A
   green run there is the check certifying a data-loss bug.**
2. **Wiring it into `scripts/check.sh` blocks every commit.** Its baseline on
   shipping code is deliberately 1 failure. `CLAUDE.md` says never commit a red
   `check.sh`. It would also be the first hard dependency on a live Wayland
   session in a gate that is display-independent today
   (`scripts/check.sh` runs the QML spec offscreen).

**Recommendation**

Land it as `tests/a11y/` plus `scripts/a11y-probe.sh`, run on demand and by the
accessibility lane, output filed in `docs/QA-RESULTS.md`. Build the fidelity
guard **before** trusting the generated copy. Assert the *unconsented* leaks
(Xtream server and username, populated) now; leave the consented-reveal
assertion out until decision 8 is answered. Retire the four greps
(`docs/QA.md:220`, `docs/QA.md:146`, `docs/QA-SOURCES.md:239`,
`docs/QA-SOURCES.md:243`) by pointing them at a dated harness run plus an
UNVERIFIED marker for delivery - which is what the rule asks for - rather than
by gating on a proxy for a surface that publishes nothing to any user today.
Move it into `check.sh` only when the baseline is green *and* a headless route
exists.

**Cost.** ~1,066 lines already written and working, plus 1 to 1.5 days to
productionise: the fidelity assertions, a bounded stability poll in place of
the fixed 1.5s sleep, the missing scenarios, and the BarWidget host. Runtime
7.5s per run, constant in channel count.

---

### Item D - search pollution on a single-group list (D-SG-1)

**Not refuted. Approve the direction; three corrections before it ships.**

**What was measured, and reproduced query-for-query by the reviewer**

- On the subscriber's own 3,335-channel list, every channel sits in one group,
  so every search key ends in the same words. Plain substring containment makes
  every *fragment* of that group name match every channel. I reproduced the
  shape on a synthetic four-channel fixture with the shipping
  `Model.filterChannels`: `st`, `sta`, `unit`, `unite`, `ted`, `nit` all return
  the entire list while the name tier matches 2, 2, 0, 0, 0, 0.
- On the real list: 25 polluted queries at lengths 1-3, all reporting 3,335.
  Inflation up to x833 (`ted` 3,335 reported against 4 real). 10 of them page
  junk into the first 200 rows - 1,533 junk rows - and 10 fire "keep typing"
  when every genuine match already fits the page.
- The group tier still earns its place on a multi-group list: it is the only
  route to 1,000 event channels and to 691 of 833 sports channels. "Drop it"
  is refuted on data.
- The whole-word rule takes the US list from 25 polluted queries to 0 and the
  sports list from 36 to 2, leaving only the groups' own words. Word-*prefix*
  does not work and is correctly rejected.
- Performance stays inside budget: worst keystroke 2.05 -> 2.89 ms at 3,335 and
  6.58 -> 9.98 ms at the 10,000-row budget size. Reproduced.
- Red/green and both mutation proofs reproduce exactly: 6 of 10 checks red
  against today's code, 10 green against the fix, and every check red against
  at least one mutant.

**What the reviewer corrected**

- The query-space total is 7,029, not 6,729 (39+703+3,347 plus 41+619+2,280).
- One figure in the risk section is the wrong query's number (1,007 belongs to
  `pp`, not `ppv`).
- "The floors are exact, not minimums" is wrong about the code:
  `scripts/check.sh:151` is `(( node_checks < NODE_CHECKS_MIN ))` and prints
  "expected at least". The bump from 1302 to 1312 is still right.
- **The pasted test block is red on this project's own gate.** Its expectation
  contains a raw non-ASCII separator, and `tests/Model.test.js` is not in the
  three exemptions at `scripts/check.sh:285-287`; its own header
  (`tests/Model.test.js:4`) states the escape rule, and `Model.js:69` is
  `var SEP = " \u00b7 "`. Paste what actually ran.
- **`groupHalf` is redundant and adds a silent-failure path.** Testing the
  whole search key for the whole word is provably the same test - a token that
  is not a substring of the name cannot be a whole word of the name half, and
  a whole-word match cannot span the name/group junction because tokens contain
  no spaces - and the reviewer confirmed it over 78,248,154 rank decisions with
  0 disagreements. The helper's prefix assumption silently drops every group
  match for any channel whose cached key is not name-prefixed. **Build the
  one-line form, drop the helper and its mutant.**

**Where it would make the product worse - disclose, do not refuse**

Two hidden costs the design did not put in front of you:

1. **A dead zone on the path to the feature's own query.** Typing toward
   "united" goes: `un` 169 rows, `uni` 26, `unit` **No matches**, `unite` **No
   matches**, `united` 3,335. Five queries go from rows to zero. The design
   used exactly this objection to kill a rival candidate ("a worse lie") and
   never checked whether its own rule reproduces it one keystroke earlier. It
   does. I confirmed the mechanism on my synthetic fixture: `unit` and `unite`
   have zero name-tier matches.
2. **Counts stop shrinking as you type.** After the fix a keystroke can
   multiply the result set (`sport` 254 -> `sports` 891, `liv` 64 -> `live`
   1,000), which is the opposite of what the "keep typing" hint promises.
3. The loss on the multi-group list is understated: 44 distinct queries lose
   rows there, a list that had no defect. Mitigated by the group column and by
   one more keystroke, but it belongs in the ruling, not a fixture footnote.

**Recommendation**

Build it, with the reviewer's one-line form, after decision 10 is answered with
those three costs on the table. Showing "No matches" is better than showing
3,335 rows of which 4 are real - but only if you have agreed to it.

**Cost.** ~10 lines in one function in `Model.js`, ten node checks, one floor
bump, four doc edits. About half a day. Runtime cost +0.02 to +0.3 ms per
keystroke typical, +0.84 ms worst case.

---

## 3. Build order

**1. Item D, search (independent, unblocked by anything except decision 10).**
First because it is the only item whose baseline is green, whose blast radius
is one function with one internal caller (`Model.js:1129`) and one test caller,
and whose user-visible win is the largest. It touches no QML, no helper, no
cache format and no second language, so it cannot collide with anything else
in flight.

**2. Item A stage A1, the 0.45 rung (independent).** Four literals. It needs no
new machinery, no per-theme computation and no calibration, because the finding
survives the known model error. Ship it beside D.

**3. Item B doc half (independent of A and D; must precede the rest of the
accessibility work).** Deleting an inert line, correcting a false comment,
labelling the password and fixing the rule 5 wording are pure gain and cost no
UX. They must land before the harness encodes anything, because the harness's
assertions cite the doc rows this commit corrects.

**4. Item C harness, non-credential scenarios (follows 3).** The fidelity guard
first, then the roles/names/states assertions and the BarWidget host. This part
is independent of every policy question.

**5. Item C credential assertions (follows 3 AND decision 8).** Cannot be
written before the policy exists. Writing them first is how a test ends up
encoding an unruled policy - which is what happened in the design pass.

**6. Item A stage A2, calibration (independent, needs the display lane).** Can
run in parallel with 4 and 5; it needs a session, not a code freeze.

**7. Item A stage A3, the 0.52 decision (follows A2 and decision 2).** Not
scheduled until A2 produces a number.

**8. The bar idle glyph (follows decision 3).** Independent of all of the
above; it lives in a file no other item writes.

**Independent of each other:** D, A1, B-doc, C-harness, A2, bar glyph.
**Strictly ordered:** B-doc before C-credential; decision 8 before
C-credential; A2 before A3; decision 10 before D lands.

---

## 4. File ownership, and where two items want the same file

| File | Wanted by | Ruling |
|---|---|---|
| `Model.js` | D (matchRank, ~1077-1090, 5805) and A3 (~4056, 5985) | **Safe to split.** The two regions are 3,000 lines apart with no coupling: D changes a ranking tier, A3 adds contrast helpers. Different lanes may hold them, but whoever lands second rebases and re-runs. A3 is not scheduled yet, so today D owns `Model.js` alone. |
| `Guide.qml` | A1 (four opacity literals), B-doc (`:3171-3173`), A3 (20 substitutions) | **Safe to split today** - A1's four lines and B's three lines do not touch. **Not safe once A3 exists**: A3 rewrites `:3150`-adjacent territory and every rung site. If A3 is ever scheduled, it takes `Guide.qml` alone. |
| `tests/Model.test.js` | D (10 new checks) and A3 (deletes the private contrast helpers, adds ~100 lines) | Serialize. D first; A3 rebases. |
| `scripts/check.sh` | **All four** want `NODE_CHECKS_MIN` raised | **Guaranteed one-line conflict.** The floor is a computed value, not a negotiated one: the last lane to land re-runs `node tests/Model.test.js` and writes the number it actually sees. No lane may lower it. |
| `docs/STATUS.md` | All four want rows | Append-only per lane, one row each, merged by hand. Note `scripts/check-defect-ledger.py` fails the build on any filed id with no row carrying a severity and a state, so a lane that files an id and forgets the row reds the gate. |
| `docs/UX.md` | D (`:196`, `:201` - search tiers) and A1 (`:613-631`, `:756-757` - rung table and footer pair) | Different sections, no overlap. Safe, but both lanes must say so in their briefs. |
| **`docs/UX-SOURCES.md`** | **B (Password row `:1165`, `:1192`; section 6.7) and C (same Password row, same 6.7, plus `:1197` confirm dialog)** | **CONFLICT, and it is the dangerous kind.** |
| **`docs/QA-SOURCES.md`** | **B (rewrite SRC-A11Y-05 at `:243`) and C (rewrite SRC-A11Y-05 at `:243`)** | **CONFLICT, same kind.** |
| `docs/ACCESSIBILITY-INVESTIGATION.md` | B and C both want to close section 5 item 7 and 4.6(b) | Same conflict. |
| `BarWidget.qml` | Bar-glyph item only | Clean. |
| `docs/ARCHITECTURE.md` (`:475`), `docs/QA-RESULTS.md`, `docs/QA.md` | D / A / C respectively | Clean, different rows. |

**The ownership ruling that matters.** Items B and C are not two subjects, they
are one coupling seen from two ends: **B decides what a screen reader is
allowed to receive, and C is the thing that grades it.** Splitting them "B owns
code, C owns tests" cuts straight across that coupling, and the design pass
already shows what happens - C's harness proposed, and certified green, exactly
the fix B had measured and rejected, and C's assertion encodes a reveal policy
nobody has ruled on. **Merge B and C into one accessibility lane with one
owner.** If they must stay separate, then the accessibility lane owns every
accessibility document (`UX-SOURCES.md` 6.7 and 7.1, `QA-SOURCES.md` A11Y and
PRIV rows, `ACCESSIBILITY-INVESTIGATION.md`) and the harness lane owns only
`tests/a11y/` and `scripts/` - and the harness lane may not author a doc row it
is about to assert against.

Note also: item A1 edits `docs/UX.md:756-757`, which is a UX authority row. A
test or implementation lane rewording a product promise so its own change
passes is the authority order backwards; that amendment is the UX owner's,
proposed by A1 with the numbers attached.

---

## 5. What cannot be verified today, and what it means for accepting each item

**Item A.** Nothing about rendered pixels can be checked from this lane, and
the repo's one rendered measurement disagrees with the model by 1.25 ratio
points in the direction that says the screen is fine
(`docs/QA-RESULTS.md:4720-4732`). *For A1 this does not block acceptance*: at
0.45 the median is 3.17 and the worst 1.98, so the finding survives that error
bar across the population. *For A3 it is disqualifying*: at 0.52 the median of
3.64-3.80 plus the same error clears the line, and the proposed fix lands every
theme at exactly 4.50 with a test that asserts 4.50. **Accept A1 on the
numbers. Do not accept A3 without A2.**

**Item B.** Everything measured lives one layer below the accessibility bus -
in Qt's own interface, not on the wire. No assistive technology is installed;
`D-GS-3` (`docs/STATUS.md`) means the shipping window publishes nothing at all
today, and both upstream reports are filed. *The doc half needs none of this*:
that `Guide.qml:3173` is inert and that Qt blanks the name are facts about the
installed Qt, reproduced by two lanes with two independent toolchains. *Any
masking policy does need it*, and the top open question is now whether the
bridge forwards the text-event payload - the channel that survives masking.
**Accept the doc half now. Do not accept a masking policy until that one
measurement exists.**

**Item C.** The harness grades *markup*, never *delivery*. A green run means the
guide's accessibility properties become correct nodes in a plain Qt window; it
does not mean a screen reader can use the shipping guide, because the shipping
window publishes nothing. There is also no headless route on this machine (only
the Wayland platform publishes a tree; no headless compositor and no Xvfb are
installed). **Accept it as a tool. Accepting it as a gate would be accepting a
proxy for a surface that reaches no user today - the original mistake in a more
expensive form.**

**Item D.** Nothing was checked on screen; the header and footer strings quoted
are the real `Model.scopeLabel` and `Model.footerStatus` called from node. *This
barely limits acceptance*, because the model is the product here - the integer
`filterChannels` returns is literally what the footer prints
(`Model.js:1131` -> `Model.js:4283` -> `Guide.qml:697-699`). Two lanes called
the shipping functions independently and got matching numbers. What is still
owed is a live re-run of the QA-RESULTS C6 sequence after the fix. **Accept on
the numbers; schedule the live re-run as confirmation, not as a gate.**

Across all four: nothing here was verified by a grep for a string the
implementation was written to contain, and every claim above that a reviewer
marked unverified is labelled as an assumption in the item that carries it.

---

## 6. Decisions for the product owner

**Decision 1 - Raise the four 0.45 sites.**
Every one of 23 themes is under the 4.5:1 threshold there, worst 1.98:1. The
sites are the footer status, the footer verbs, the group entry count and the
Sources pinned count. Raising them to the 0.70 key rung takes 23 of 23 under to
6 of 23 under; raising them to full takes it to 0 of 23, at the cost of the
group count no longer reading as secondary beside its group name.
**Recommendation: raise all four to 0.70, amend `docs/UX.md:756-757` once to
say the key/verb pair collapses, and record the residual 6 themes as a known
limitation joined to decision 2.** No per-theme machinery, no calibration
needed.

**Decision 2 - The per-theme contrast floor over the 0.52 rung.**
**Recommendation: REFUSE for now.** It spends the guide's only working
hierarchy (median separation 2.86:1 down to 2.24:1, worst theme 1.35:1) on a
model that disagrees with the one screenshot measurement this project has. Run
the calibration pass first; then decide with a target above 4.5, not on it.

**Decision 3 - The bar's idle glyph.**
`BarWidget.qml:66` dims it by a mechanism the contrast design never measured
because it grepped for the wrong thing. Under 4.5:1 in 7 of 23 themes, and it
is on screen permanently, unlike the guide.
**Recommendation: file it as its own defect with the 7 themes named, and fix it
before the guide's 0.52 rung.** Most-seen element, smallest blast radius.

**Decision 4 - The accent ink on the cursor row.**
The channel name and number on the cursor row use the theme accent, which is
under 4.5:1 against its own fill in 8 of 23 themes even at full opacity. No
dimness change can fix it; only changing the ink can, at the cost of the cursor
row losing its accent.
**Recommendation: no change now. Keep it as an open defect and decide it with
decision 2, since both are "what does the cursor row look like".**

**Decision 5 - Ship the accessibility documentation half.**
Delete the inert `Guide.qml:3173`, correct the false comment above it, give the
password its label through `Accessible.description`, amend
`docs/UX-SOURCES.md:1165` and `:1192` (they ask for something Qt 6.11.2 cannot
deliver), and fix `CLAUDE.md` rule 5 with the correct two-part statement plus
the text-event payload as a named sink.
**Recommendation: YES. Pure gain, no UX cost, measured twice independently.**

**Decision 6 - Masking the Xtream username.**
**Recommendation: REFUSE as scoped.** As a single edit it was measured to break
the field - the user types `joe` and it holds `e`. Done properly it is five
`Model.js` sites plus a UX regression (a field the user most often re-reads,
behind a fixed-length mask that hides whether it is even filled). Either accept
the exposure explicitly in the ruling alongside the revealed URL, which is at
least consistent, or commission the full plumb as its own scoped change with
its own tests.

**Decision 7 - The unconsented credential sinks.**
Three states nobody has ruled on: a full provider login string pasted into the
Xtream server field (unmaskable, no eye button, published forever - and
`docs/UX-SOURCES.md:1241` records that users do paste it); a URL carrying both
userinfo and path credentials, where the description publishes the path
credential in full; and path-embedded credentials generally, where `maskUrl` is
an identity so there is no eye button at all.
**Recommendation: rule that these are the defect, and that the user-initiated
reveal is not.** They have no user consent and no affordance; the reveal has
both.

**Decision 8 - What a screen-reader user may hear when they deliberately
reveal.**
This is the ruling that blocks the harness's credential assertions. If a
revealed field must publish nothing, a blind user can never verify a pasted
provider URL and the reveal feature works for sighted users only.
**Recommendation: accept the consented reveal explicitly, with its bound (blur,
Enter, Escape, paste and close all re-mask), and write the bound into
`docs/UX-SOURCES.md` 6.7. Then measure whether the text-event payload crosses
the bus before asserting anything about it.**

**Decision 9 - The accessibility harness: tool or gate.**
**Recommendation: lane tool now, gate later.** Its baseline on shipping code is
red by design, and `CLAUDE.md` forbids committing a red `check.sh`; it would
also be the first hard dependency on a live graphical session in a gate that is
headless today. Retire the four greps by pointing them at a dated harness run
plus an UNVERIFIED marker for delivery. Move it into `check.sh` when the
baseline is green and a headless route exists. **And note for the record: the
harness's "validated" credential fix was measured to silently overwrite the
user's stored credentials and save clean - do not treat a green run there as
approval of a remedy.**

**Decision 10 - Search: a group reachable by its words, not by fragments.**
The fix removes 25 polluted queries, 1,533 junk rows and 10 false hints from
your own list. The cost, disclosed: typing toward a group name passes through a
dead zone (`unit`, `unite` return "No matches" on a list where every row prints
"United States"), result counts can grow as you type, and 44 queries on the
sports list return fewer rows than today.
**Recommendation: YES, with those three costs written into `docs/UX.md:196` as
part of the rule.** Showing 4 real matches beats showing 3,335 rows of which 4
are real - but "No matches" is a worse lie than a wrong number if it arrives
without warning, so the rule must say so out loud.

**Decision 11 - One accessibility lane, not two.**
**Recommendation: merge items B and C under one owner.** They are one coupling:
the policy and the check that grades it. The design pass already produced the
failure this prevents - one lane's harness certified as green the exact change
the other lane had measured and rejected. If they stay separate, the policy
lane owns every accessibility document and the harness lane owns only
`tests/a11y/` and `scripts/`.