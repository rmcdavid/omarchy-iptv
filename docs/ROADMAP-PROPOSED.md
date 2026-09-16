## Overview

Ten releases in four days. The product works. What does not work is the record of it: the board says 31 fixes shipped with no test afterwards, and four of its rows turn out to be not merely unverified but wrong. Correcting that is a day of desk work and it changes what two later phases even are, so it goes first.

**Phase 0 - Tell the truth. One day, no screen needed.** Correct four wrong board rows, retire two competing roadmaps that disagree with each other, and add one automatic check that catches this class of drift. Delivers: a board a stranger can trust.

**Phase 1 - One question for you. One command, yours to run or refuse.** Every stream address in your playlists has the shape of a provider API this plugin has never asked anything. If it answers, it supplies channel numbers, logos, real categories, guide data and a stable channel identity - five backlog items resolved or reframed by one request. It sends your subscription credentials to your own provider, so no agent will run it. Delivers: a yes, a no, or a shrug.

**Phase 2 - Fix channel identity. Small.** A routine provider password change silently erases every favourite and recent you have. Measured on your own list: 1 of 3,335 channels keeps its identity. Delivers: saved things that survive.

**Phase 3 - Settle the 31. One desk day, then one or two screen sessions.** About 21 of them need no screen at all and go into the automatic gate so they cannot rot again. The rest ride one bounded live pass. Delivers: a real number instead of a headline.

**Phase 4 - One new feature: saved searches. Medium.** You already built this by hand in a text editor. Delivers: the guide remembering a search that worked.

**Standing, in parallel:** harden the accessibility harness. It needs no screen and blocks nobody.

---

## 1. What this roadmap replaces, and why

`docs/PRODUCT.md` section "Roadmap (product owner, 2026-09-15)" is current and is
superseded by this document. Four of its premises did not survive re-measurement
by four role lanes and by this pass:

| Its claim | Measured |
|---|---|
| "Four open rungs" in the contrast family | One open question, three bookkeeping actions. D-RUNG-5's fix shipped at `62e7d39` and the row still reads `open`; D-RUNG-3's row describes `Model.BAR_IDLE_DARKEN` at factor 1.25 and floor 4.71, a symbol that exists in no source file - the shipping code is `BarWidget.qml:72`, `Util.alpha(root.barFg, Model.BAR_IDLE_ALPHA)` at 0.86. Verified this pass by grep and by reading both files |
| D-RUNG-6: "the ceiling on the real bar is about 2.25:1" | Its stated mechanism does not reproduce. Three lanes independently checked `/usr/share/omarchy/default/themed/shell.toml.tpl` and found `[bar] text = {{ foreground }}` and `[menu] text = {{ foreground }}` - the same key into both sections. I confirmed the template. The rendered deficit solves to alpha 0.5031 / 0.5000 / 0.5000, one half on all three channels, and the project's own calibration fixture already documents the peak-pixel method under-reading thin strokes |
| M2-08 vertical bar is "the cheapest remaining thing a user would notice" | `~/.config/omarchy/shell.json` has bar position `top`. A vertical bar is 28 px wide, `BarWidget.qml` already suppresses the label and the number there, and the only extra thing that layout could show is a channel number, of which this provider ships zero |
| M2-04 logos: "the design has to lead with the three-in-four placeholder case" | The 27 per cent is the whole file. Coverage by decile of the list they browse, in playlist order, is 99, 67, 38, 14, 3, 0, 0, 0, 0, 0. The first 200 rows are 199 of 200 covered. The design problem is a cliff, not a placeholder majority |

One more fact frames everything below and is not in any current document.
**The plugin has never been pointed at the subscriber's provider lists.**
`~/.local/state/omarchy-iptv/state.json` holds one source, origin `migrated`,
label `iptv-org.github.io`; its cache holds 1,472 channels in 28 groups with a
`tvg-id` on 1,472 of 1,472. Verified this pass. Every "what the subscriber sees"
sentence in the current roadmap describes files that are configured nowhere.

---

## 2. Measurements this roadmap rests on

Re-run in this pass through the shipping parser (`bin/omarchy-iptv parse_m3u`,
`assign_ids`) and the shipping `Model.js`, not re-implemented.

| Fact | Value |
|---|---|
| Channels | USChannels 3,335 in **one** group; SportsPPVAll 1,833 in two (1,000 + 833); Kids 48; Default 5. Total 5,221 |
| Attribute keys present across all 5,221 `#EXTINF` lines | Exactly four: `tvg-id`, `tvg-name`, `tvg-logo`, `group-title` |
| `tvg-id` | 1 of 3,335 on the main list; 274 of 5,221 overall (the sports list is 14 per cent, so "no EPG" is true of the main list, not the subscription) |
| `tvg-chno`, `catchup`, `catchup-source`, `catchup-days`, `timeshift`, `tvg-rec` | Zero, on all four lists. Not unset - **absent by construction**, since only four keys exist |
| Logos | 737 of 3,335, 1,396 of 5,221, from exactly **one** host |
| Channel id survival under a provider password rotation | **1 of 3,335 (0.03 per cent).** 3,334 rows are keyed `u:<fnv1a32(url)>`. Names are 100 per cent identical across the same rotation |
| `Model.filterChannels(prep, "baton rouge")` over the real 3,335 | `rows 4, total 4`, and they are exactly the four Baton Rouge channels |
| `Model.filterChannels(prep, "pluto")` | `rows 200, total 2227, truncated true` |
| Unknown scope kind, silent failures | `Model.launchScope('l:X', '', row)` returns `g:United States`; `Model.channelsForScope(prep,'l:X',st)` returns 0 rows; `Model.fallbackScope(entries,'l:X')` returns `all`. No throw, no warning |
| Baseline | `node tests/Model.test.js` 1,345 checks, 0 failures at `c22647c`, tree clean |

Nothing was written to a tracked file, no display was held, no shell was
restarted, and `~/.config`, `~/.cache` and `~/.local/state` were read only.

---

## 3. The sequenced plan

Two lanes run at once and no more. A **desk lane** (no display) and a **display
lane**. The accessibility harness is the one substantial third workstream that
needs a graphical session but takes no display lock - QA measured
`hyprctl` client count at 1 before, during and after, with the shell never
restarted - so it can run beside either.

### Phase 0 - Board truth, and one check that keeps it true
*Desk lane. Size S. Blocks: every estimate in phases 3 and 4.*

1. Rewrite D-RUNG-3's state cell to the shipping alpha implementation. Its
   contrast figure stays unasserted until phase 3 settles D-RUNG-6.
2. Move D-RUNG-5 from `open` to `fixed, not live-confirmed`. Two node checks
   already assert it across 23 themes.
3. `STATUS.md:291` "Fourteen rows read fixed" - the count is 32.
4. `STATUS.md:299` "D-SG-1 still open" - its own row at line 206 says fixed
   under ruling SG1 with 20 node checks and all 6 mutants caught.
5. Retire `docs/PLAN-NEXT.md` (all four items shipped or refused) and reduce
   `STATUS.md`'s "Next up" to a pointer. Three ranked lists currently disagree.
6. Extend `scripts/check-defect-ledger.py`: every backticked `Model.X` in
   tracked markdown must resolve in a shipping source file. Of 118 citations,
   116 resolve; the two that do not are `BAR_IDLE_DARKEN` and `pipLuaDispatch`,
   the second of which is an **acceptance criteria row grading a function that
   never existed**.

Why first: three of the four corrections change what the contrast family is, so
sizing phase 3 before this produces a plan for a board that does not exist. The
ledger check's own docstring says "It does not check that a state is TRUE." This
closes the cheapest slice of that gap, and it catches two real drifts today.

### Phase 1 - The provider API question
*Yours. One command. Blocks: the shape of phases 2 and 5.*

Every one of the 5,221 stream addresses has the same shape: one host, two
constant path segments, then a numeric id, with 5,218 of 5,221 final segments
being pure integers. That is the layout of a well-known provider panel whose
API this plugin has never called - `grep -n player_api bin/omarchy-iptv` returns
nothing, and `ARCHITECTURE-SOURCES.md:360` strips that path from a pasted
server address.

If it answers, it reports per channel: a channel number, a logo, a category, an
archive flag, and **a credential-independent stream id**. That resolves or
reframes M2-07 (currently blocked for want of test data), M2-04 (logo source),
M2-03 (inert for lack of numbers), the single-group problem (real categories),
and phase 2's identity fix, which becomes nearly free.

**This is a decision for you, not an action for us.** The request carries your
subscription credentials. No agent on this team will send them anywhere. If you
say no, three items stay correctly closed and we have lost nothing.

### Phase 2 - Channel identity
*Desk lane. Size S if phase 1 answers, M if not. Blocks: phase 4, and anything that ever persists a channel reference.*

`bin/omarchy-iptv:855` assigns `t:<tvg-id>` only when that id is unique, else
`u:<fnv1a32(url)>`. On the main list that is 3,334 of 3,335 rows keyed by a hash
of an address containing the account password. I simulated a rotation on the
real file, re-ran the shipping `assign_ids`, and diffed: **1 id survives.**
Favourites, recents, `lastPlayed` and the player's `session` record all key on
it. A routine provider password change silently empties every one of them, with
no error and nothing for the user to understand.

This is not on the board. File it as P2 whether or not the rest of this roadmap
is approved. With a stream id from phase 1 it is a key swap. Without, the
fallback is a name-plus-group hash plus a one-time remap of favourites and
recents - additive state, no version bump.

### Phase 3 - Settle the 31, in three tiers
*Desk lane, then display lane. Size: one desk day, then one or two screen sessions of about an hour each.*

The headline is one number covering five different problems.

**3a. Free relabels (about 15 rows, desk, S).** Four already carry their own
live confirmation in their state cell (D-PLY-8 "10 of 10 runs", D-PLY-10 "~120
player starts", D-A11Y-6 "verified at the sink", D-RUNG-4 "seen on a real
screen"). Seven were re-proven by the green gate this pass. Four are
documentation with nothing to re-test.

**3b. Declare the fixture matrix before anything runs (desk, S). This is the
step that prevents the expensive failure.** D-SG-1's repro requires a
single-group list. D-GS-2's requires guide data configured against no matching
ids. **Neither can occur on the 28-group, fully-id'd list the plugin is
actually configured with.** A pass run "as it sits" files both as verified
having never seen the defect, and a false "verified fixed" retires a row
permanently. Per row, write which of the four lists supplies its repro.

**3c. One display session (about 8 to 12 rows, M-L).** D-CHNO-1, D-CHNO-2,
D-GS-1, D-GS-2, D-PIP-2, D-PIP-4, D-PIP-5, D-SG-1, D-LIVE-22, plus D-QA-04 -
two shipped IPC verbs, `toggle` and `previous`, that **nothing in this
repository has ever invoked**. Carry three extra items in the same session
because they want the same screen and the same theme switches:

- **The D-RUNG-6 discriminator.** Capture a thick host glyph (the clock) and our
  Nerd Font glyph in the same frame with no theme switch in the preceding two
  seconds, and read the pixel distribution rather than the single peak. If both
  show the deficit, the method is the defect and a P2 plus an upstream report
  evaporate. If only ours does, it is a stroke-weight problem and no token work
  will fix it. Either answer retires work someone would otherwise do.
- **The calibration top-up.** `CONTRAST-RULING.md` Step 2 required rose-pine
  plus one dark theme plus one sample at alpha 0.6 to 0.9 before any further
  contrast change. `tests/fixtures/contrast-calibration.json` holds 6 samples,
  two themes, alphas 0.52 and 1.0 only. Zero rose-pine samples - and rose-pine
  is the binding theme for both shipped floors. Step 3 shipped anyway.
- **D-RUNG-7.** One probe printing three resolved tokens.

**3d. Closures, not tests (desk, S).** D-RUNG-2 closes as accepted: Step 4's own
condition was "only if decision 2 goes to `menu.text`", and decision 2 shipped
as Option A at `a48d791`. D-PLY-11 closes as accepted on reachability - its own
row records 1 of 8 parallel bursts, 0 of 6 targeted, 0 of 4 serial, against a
concurrency the single-threaded QML guide cannot produce. And
`CONTRAST-RULING.md`'s "What none of this fixes" holds at least six measured
findings with no id, one of which that document itself calls a D-RUNG-2 site the
row never listed. Rule 13 says whoever writes a finding mints its id.

**The structural fix matters more than the pass.** 303 of 494 case rows across
`QA.md`, `QA-SOURCES.md` and `QA-PLAYER.md` require the display. That ratio, not
discipline, is why the QA record stopped. Two things change it: keep lifting
pure logic into `Model.js` so it can be called rather than watched (that is what
made D-SG-1 and D-GS-2 settleable from a terminal this week), and **one pacman
command from you** - install `cage` (extra/cage 0.3.1) so we can spike whether
quickshell runs headless. If it does, a large slice of tier 3 becomes tier 1
forever. We cannot install it; rule 4 forbids sudo.

Also: pick one home for live evidence. "No re-test" sometimes means "the test
ran and was filed in a topic document the board does not read" - `7afb586` is a
live pass from this week whose evidence landed in `CONTRAST-RULING.md`.

### Phase 4 - The feature
See section 4. Depends on phase 2 (identity) and on phase 0 (an honest board).
Does **not** depend on phase 3's display session.

### Standing, in parallel
- **Accessibility harness hardening** (`QA-A11Y.md` section 9 items 2, 3, 6, 9,
  10): a second literal assertion beside every self-oracled check; name and
  value and cardinality on the same node; a mutation that poisons
  `TRANSFORM_RULES`; a mutation mode that edits a shipping file and regenerates.
  None of it waits on upstream. The day upstream lands, this is the difference
  between a first run that is evidence and one that is a demo.
- **D-PIP-3, one cheap experiment.** `/usr/share/omarchy/default/hypr/apps/system.lua`
  exempts media players by an anchored class regex our app id can never match -
  that half is as the README says. But `pip.lua:2` tags any window whose
  **title** matches `(Picture.?in.?[Pp]icture)` and then applies
  `-default-opacity` and `opacity = "1 1"`. The helper already writes the window
  title over IPC on every channel change (`bin/omarchy-iptv:2773`). Verified
  this pass. One line to try. It also forces float, pin, 600x338 and a move,
  which would contend with our own dispatches, so it needs one measured display
  pass and is cheap to abandon.

---

## 4. The new features

Two proposals were built and each was judged by three adversarial reviewers who
re-ran the numbers. **One is recommended, redirected. One is dropped.**

### RECOMMENDED: saved searches

Judges: **6 / 8 / 6** (repeat-use lens, data lens, cost-to-own lens).

**The evidence.** `Default.m3u` is five channels. All five are present inside
the 3,335-channel list, matched by the provider's own stream id and by name. The
shipping `Model.filterChannels` returns exactly those four Baton Rouge rows for
the single term `baton rouge`, and the two terms `baton rouge` + `new orleans`
return seven rows covering five of five. I reproduced all of this. It is the
only proposal on any lane whose demand can be read out of something the user
already did rather than out of convention: they wrote a saved query in a text
editor because the guide gave them no syntax for one.

**Why a term and not a list of ids.** A term keys on names, and names are the
only field in this provider's data that survives: 1 of 3,335 ids survive a
password rotation, 3,335 of 3,335 names do. A term also picks up channels the
provider adds later, and it works across bouquets where the same brand is
spelled differently.

**Why the obvious rival fails.** Name-derived facets in the group column were
proposed independently by the UX and QA lanes. Measured against the real list
they yield 18 facets, **none** naming the user's market, and drop their four
local channels into a bucket of about 485 rows called `us`. A term gets them to
four. Facets stay deferred behind the `axis.narrows` gate.

**The redirect, which is why this is recommended and the proposal as written is
not.** Judge 1 (6/10) measured what this costs the user **today**: their five
curated channels reach row 1 in 2, 3, 2, 9 and 5 keystrokes, and 72 per cent of
a sampled 3,335 rows land in the top three within four keystrokes. So a new
fifth scope in the group column is not faster than typing, and the shipped
competitor - Favorites, one keystroke, already pinned first - reads `[]` after
ten releases. Judge 3 (6/10) then priced the scope machinery and I reproduced
all three of its silent failures: an unknown scope id returns the 3,335-row
group ring from `launchScope`, zero rows from `channelsForScope`, and `all` from
`fallbackScope`, with no error in any of the three.

So: **save a search into Favorites, do not mint a fifth scope.** Favorites is
already in `scopeSurface`, `launchScope` and the zap ring, so none of those
silent paths is touched. There is no name prompt, no `LISTS` header, and no
contradiction with ruling SR9. And it fills, for the first time, the ranker the
product already has: the UX lane measured that feeding the four channels this
user has actually played through the unmodified shipping `filterChannels` moves
`abc` from rank 11 to 1, `cbs` from 8 to 1, `nbc` from 24 to 1. That measurement
came from a role survey, not from an adversarial judge, and is labelled
accordingly - but it is one argument at `Guide.qml:731` and it works whether or
not anybody ever saves a search.

**The interaction.** After a search that returned the right rows, one modified
key (bare letters must stay literal - `handleSearchKey` at `Guide.qml:1189`
routes every printable character into the query) saves the current query. The
confirmation shows the live row count for the terms as typed, so a bad term is
visible in the moment rather than discovered later: `baton rouge` shows 4, and
`no tv` shows 75 because `tv` matches everything. Saved terms evaluate at load
and their rows appear in Favorites alongside explicitly starred channels.
Nothing about the search box, the row, the footer or the player changes.

**What it costs.** None of the four axes this project's real costs live on: no
new process, no new file format, no new network call, no new long-lived
resource. `Model.js` gains one pure evaluator. `state.json` gains one optional
key, additive on the precedent of the nullable `session` key. Measured runtime
across the three lanes: between 2 and 13 ms for ten terms at 10,000 channels,
against a 150 ms open budget. The spread is itself a finding - the three lanes
measured `prepareChannels` at 5.36, 21.5 and 26.3 ms on the same machine - so
treat the budget framing as soft and re-measure before quoting it.

**Four constraints the measurements impose. All four are build-order, not taste.**

1. **Do not use `filterChannels` as the membership oracle.** It is ranked and
   capped: `pluto` returns `rows 200, total 2227`. A saved term's rows and its
   count would disagree by an order of magnitude. Worse, its slot arithmetic is
   `rank*2 + (fav ? 0 : 1)`, so a saved set built on it silently reorders when
   you favourite something inside it. Add a separate pure predicate; leave
   `filterChannels` as the ranked display function. This is *less* coupling than
   the proposal has, not more.
2. **Bound it.** `MAX_SAVED`, `MAX_TERMS`, name length, on the `MAX_SOURCES 50` /
   `MAX_LABEL 64` precedent. The whole perf argument is stated "for ten terms",
   a bound that does not exist in the design.
3. **Teach both whitelists.** `normalize_state` rebuilds from `default_state()`
   and copies only keys it knows; `Model.parseState` is a second independent
   whitelist in a second language. Judge 3 proved the trap live: writing a state
   document with the new key and then running one `favorite add` through the
   real CLI erased it, exit 0, `"ok": true`, no warning. One shared JSON fixture,
   per the rule for any rule implemented in both JS and Python, and a rule-10
   round-trip run first against the un-taught writer to show it erases.
4. **Acceptance asserts counts from calling the real evaluator**, never a grep:
   `baton rouge` exactly 4 and exactly those ids; the two-term union exactly 7
   covering five of five; `no tv` exactly 75 so the explosion case is pinned.
   Note that `no tv` through the shipping helper is 75 and through a naive parse
   is 76, so that assertion pins helper parsing too - state it. Mutation proofs
   (the code is new, so there is no "before"): drop the de-duplication, reverse
   term order, invert the ordering, and show each red first.

### DROPPED: "other feeds"

Judges: **6 / 6 / 5.** A one-key ring of every alternate feed of the channel
under the cursor. Well argued, genuinely evidenced - their hand-made five-row
file really does carry two feeds of one station - and it should not be built.

**All three judges independently found the same fatal flaw, and I reproduced it.**
The proposal's cost case rests on "needs no new index": look siblings up by
feeding a cleaned name back through `filterChannels`, claimed at 100 per cent
recall. Measured, recall splits on the branch: name-formed clusters 100 per
cent, **call-sign clusters 16.7 to 56.6 per cent** depending on the judge's
normalisation. I seeded the proposal's own marquee row - their local NBC
affiliate, the row used as its single best demand evidence - and the lookup
returns **one row, itself**. The feature would print "No other feeds for this
channel" on the exact row that justifies it. It is also asymmetric: seeding one
member of a pair returns two, seeding the other returns one. The call-sign
branch is what raises main-list coverage from about 3.5 to about 6.7 per cent,
so the branch and the zero-index implementation cannot both ship.

Two more, each sufficient on its own. **Every alternate is on one host.** All
5,221 addresses resolve to a single hostname with a single path shape, and every
cluster has all its members there - so the failure modes that actually take a
reseller feed down mid-game take all six alternates with it. And **splitting
clusters by whether members differ in a provider feed letter or only in a
quality token** (transcodes of one ingest, which die together) puts the
rescue-capable surface at 19 per cent of the sports list and **0.57 per cent of
the 3,335-row list the user browses**, against a headline of 35 per cent.

**What dropping it buys.** A scarce display session is not spent proving a
feature that appears on 10 to 16 rows of the 1,472-channel list the plugin is
actually configured with. No second new scope kind, and therefore none of the
silent-failure surface documented above. And the half of its value that is real
is available for almost nothing: `Service.qml:272` marks `failedAt` session-only,
so which of six competing feeds is dead is re-learned after every
`omarchy restart shell`. Persisting it with an age-out reuses the recents write
path and the render path that already exists - `Model.rowFailedMeta`,
`Model.rowDetail`, the alert glyph at `Guide.qml:2596` and the `, failed`
suffix in `rowAccessibleName` all ship today. Take that. Leave the clustering.

---

## 5. Refused and deferred, with the numbers

Restated so nobody re-proposes these from memory.

**M2-07 catch-up and timeshift - stop calling it blocked, call it a decision.**
Zero of 5,221 channels carry `catchup`, `catchup-source`, `catchup-days`,
`timeshift` or `tvg-rec`. Stronger than that: across all 5,221 `#EXTINF` lines
exactly four attribute keys exist, so these are absent by construction, not
unset. Not one acceptance case could be verified against real data. "Blocked"
implies someone is waiting; nobody is. Reopen **only** if phase 1's probe
reports an archive flag.

**M2-04 logos - deferred pending a privacy ruling, and the ruling needs the
right number in front of it.** 1,396 of 5,221 carry a logo, resolving to 622
distinct images, sampled at a median of 7.6 KB, so the cache is about 5.6 MB.
All 1,396 come from **one** third-party host, verified this pass. The design
figure that matters is not 27 per cent but the decile curve: 99, 67, 38, 14, 3,
0, 0, 0, 0, 0. Two facts gate any work. It would be the first feature to fetch
remote images on the user's behalf, and that host would learn which channels
they render and when. And done the obvious way - a QML `Image` bound to a remote
address - it breaks the cleanest security property this codebase has: **QML
makes zero network requests today**, and every byte from the network passes one
hardened `urlopen` with a redirect guard, a timeout, a size cap and redaction.
If it is ever built, it fetches through the helper into the per-source cache and
QML loads `file://` paths.

**M2-08 vertical bar layout - dropped from the ranked list.** Bar position is
`top`, verified. A vertical bar is 28 px wide, the label and number are already
suppressed there, and the only remaining affordance is a channel number, of
which this provider ships zero. Park it undated; reopen on request.

**M2-06 recording - re-sized down, and still not scheduled.** The board calls it
"a second long-lived child process... ffmpeg". Measured, it is one mpv runtime
property: `--stream-record` already sits in `Model.js:160` of `MPV_RESERVED`
with the comment "writes the stream itself to disk", and the plugin already owns
the socket and already writes properties on every channel change. So it costs
**one** of the four axes, not four - but that axis is a file of unbounded size
outside the cache, it needs a product-owner ruling to reverse a shipped privacy
refusal, and mpv warns that switching streams during recording may break the
file, which collides head-on with a plugin whose core verb is zapping. Policy
decision before build. Nothing in the user's data or state suggests demand.

**D-RUNG-2, the refused contrast floor - close it as accepted.** Not a fix, a
closure its own governing ruling already authorised: Step 4 says "only if
decision 2 goes to `menu.text`... otherwise the board row closes as accepted",
and decision 2 shipped as Option A (`Model.cursorInk`, 7 refs in `Model.js`, 9
in the node suite, `a48d791`). Record the accepted risk, and mint an id for the
one site the row never listed - the non-cursor channel number at 0.52, under
4.5:1 in 20 of 23 themes with a floor of 2.33.

**Anything EPG-shaped - refused for this provider, with a second reason nobody
has recorded.** 1 of 3,335 on the main list, and `bin/omarchy-iptv:1244`/`:1379`
match programmes on `tvgId` alone with no name fallback, so an XMLTV feed could
match at most one channel. But QA ran the project's own documented XMLTV asset
against the **installed** list, where id coverage is 1,472 of 1,472, and it
matched **0**, with 8,837 programmes parsed and dropped. There is no dataset on
this machine where the shipped guide-data feature renders a single line. That is
not on the board and should be: US6 is an M1 must.

**EPG reconstructed from channel names - measured dead before proposal.** The
sports list puts events in the name, so it looks free. 253 of 1,833 rows carry a
usable time, in five incompatible formats, and 187 of the 440 timestamps are the
provider's own 2098-12-31 placeholder. Recorded here so it is not proposed again.

**A second window - refused on arrival, permanently.** No placement request, no
stacking request, and mpv binds no layer shell. Already paid for at
`ARCHITECTURE-PLAYER` M2-05 section 2.1 and gate G-9.

**Merging the four sources into one list.** `channels.json` is per source, ids
are assigned per source, and ruling SR9 makes favourites global by id - so a
merged view shows un-deduplicable twins and favourites that highlight one twin.
Kids shares 0 of 48 stream ids with the main list. A data-model rebuild wearing
a small feature's clothes.

**Automatic failover between feeds.** Recreates the 0.4.0 defect class by
another door, and moves the viewer to a worse feed without consent.

**Pause and rewind from mpv's back buffer - not refused, but not ranked.** Every
property it needs exists on the installed mpv 0.41.0 and it touches zero of the
four cost axes, which makes it attractive. It is unranked because nothing
measured argues for it - the demand is inferred from convention - and the one
measurement that would size it (whether these streams are seekable inside the
demuxer cache, and at what bitrate) requires playing a credentialed stream. If
phase 1's probe happens, take that reading in the same sitting.

---

## 6. Risks

1. **The re-test pass run against the wrong configuration.** The single most
   expensive outcome available, because a false "verified fixed" retires a row
   permanently. At least two repros cannot occur on the installed list. Phase 3b
   exists solely to prevent it.
2. **Believing D-RUNG-6's conclusion without settling it.** "No icon in the bar
   can be made readable" is a claim about a permanently visible element, drawn
   from one capture, taken after a theme switch, using a method the project's own
   fixture documents as under-reading thin strokes, with a deficit that solves to
   exactly one half. Note the contrast family splits cleanly and the board does
   not say so: the **guide** fixture is corroborated (D-RUNG-4 predicted 2.80 and
   the screen measured 2.78), and only the **bar** fixture is in doubt.
3. **Board rows that are untrue rather than unverified.** A reader sizing the
   contrast work today reads a symbol, a factor and a floor that do not ship.
4. **Credential-derived identity, unfiled.** Phase 2. Also poisons every future
   feature that persists a channel reference.
5. **Silent failure on any new scope kind.** Reproduced three ways. Whatever is
   built, a scope-consumer audit is a ten-minute grep and it is not optional.
6. **State writer erasure.** Two whitelists, two languages, seven CLI write
   paths, fourteen `saveState()` sites. A tolerant test double will not catch it.
7. **Fixture provenance.** Any fixture derived from these playlists comes from a
   credentialed export in a scratchpad, cannot be regenerated after a rotation,
   and `origin` is a public remote - committing raw names publishes about 5,221
   provider channel names. Settle this with the product owner **before** design.
8. **D-A11Y-1 changes from harmless to live with no commit of ours.** The day
   quickshell#1144 lands, a provider login and username publish in full on the
   accessibility bus. The obvious masking was already measured to corrupt the
   Xtream form under ruling AX2, so there is no fix in hand. Design any remedy
   against the harness, not against the source, and ship nothing until it passes
   the undamaged-field pair as well as the masking pair.
9. **Stacking changes on one surface.** Logos change row height, which is the
   exact surface D-GS-2's unverified fix just changed. Two unverified changes on
   one surface is the pattern that produced the contrast family.

### The two upstream dependencies nobody here controls

| Report | What it blocks | State |
|---|---|---|
| [quickshell#1144](https://github.com/quickshell-mirror/quickshell/issues/1144) | Nothing this plugin declares reaches a screen reader. Every accessibility acceptance criterion is unobservable, so any criterion written today would be a grep, which rule 14 forbids. D-A11Y-1 stays latent | Open, filed 2026-09-15, zero comments |
| [omacom/omarchy#12009](https://github.com/omacom/omarchy/issues/12009) | The host shell carries no accessibility information at all, so even a fixed framework leaves the desktop unusable with a reader. Larger than ours | Open, filed 2026-09-15, zero comments |

Neither is ours to fix and neither should be waited on. The harness hardening in
section 3 is the correct meanwhile-work precisely because it needs neither.

---

## 7. What would make this roadmap wrong

Eight assumptions, none verified, each with the measurement that would settle it.

1. **Name churn across playlist refreshes is unmeasured.** This is the biggest
   one, because the whole saved-search premise is "names are the key that
   survives" - and that is proven only against a credential rotation, not
   against a provider re-issuing its catalogue. There is exactly one snapshot of
   each list and the cache holds no history, so nobody can prove it today.
   **Capture a second fetch of the main list now** so the diff can run in a week.
   It costs nothing to start and it could overturn phase 4 entirely.
2. **Nobody has seen this product running against this data.** The live install
   is the public 1,472-channel, 28-group, fully-id'd list. Every user-shaped
   claim here - the single group, the missing guide data, the missing numbers -
   is about files configured nowhere. It cuts both ways: it means the provider
   data is the right target, and it means `favorites: []` is weak evidence of
   taste and strong evidence only that the plugin has not been used in anger.
3. **The provider API is a hypothesis from address shape, not a fact.** Phase 1
   is built on it. If it does not answer, phase 2 gets bigger and three deferred
   items stay deferred.
4. **D-RUNG-6's real mechanism is unknown.** Three lanes falsified the stated
   one. The alternative - that the peak-pixel method under-reads thin strokes -
   is untested. One capture decides it.
5. **No contrast number may be set in the alpha 0.53 to 0.99 band, on any
   surface, until the calibration top-up lands.** The fixture has zero samples
   there and zero on rose-pine, which is the binding theme for both shipped
   floors. Applying the known proportional optimism to the floors that already
   shipped leaves both above 4.5, so this blocks new targets, not old ones.
6. **Every performance number here was taken in node's V8, not QtQml.** They are
   floors, not ceilings, and the three lanes disagree by 5x on the same
   function. Re-measure before any of them is quoted as a budget.
7. **Whether alternate feeds are independent origins is unknown** - it is the
   measurement that would have decided the dropped proposal, and it is worth
   taking in the same sitting as phase 1 if that goes ahead.
8. **`scripts/check-defect-ledger.py` says in its own docstring that it cannot
   check whether a row's state is true.** Phase 0 closes the cheapest slice of
   that. The rest stays open, and three of this pass's four board errors came
   through it - all three specified by a commit's own build order and skipped.

**The one-line argument.** The 31 is not one problem, it is five: about 15 cost
nothing, four should be closed rather than tested, about 21 need no screen at
all, and the dozen that remain will produce false greens unless the source
configuration is declared per row first. Nothing new should be built on top of a
board that is wrong about itself - and once it is right, the feature worth
building is the one the user already built by hand.