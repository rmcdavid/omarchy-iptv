# Phase 3: settling the 32

Tiers 3a and 3b, 2026-09-20. Desk work only: no display was used, no live
pass was run, and the subscriber's provider lists were never pointed at.

## What this was

The board carried 32 rows reading `fixed` -- a fix was written and nobody
re-tested it. That single number covered five different situations, which is
why it never got settled: it reads as 32 units of QA work, and it is not.
Every row was re-read against its own cited evidence, then an independent
agent was asked to REFUTE each classification rather than agree with it.

The point of the exercise is not the relabelling. It is that **a false
`verified fixed` retires a row permanently**, so the expensive failure is
optimism, not delay.

## The result

| Tier | Meaning | Rows |
|---|---|---|
| 3a | Free relabel. Already proven; no screen owed. | **11** |
| 3b | Needs data the configured list cannot produce. | **7** |
| 3c | Needs the display; configured list is fine. | **11** |
| 3d | Closes without a test. | **1** |
| unresolved | Could not be settled from the desk. | **2** |

The roadmap estimated about 15 free relabels and about 21 rows needing no
screen. The measured number is 11 free relabels. The estimate was optimistic
in exactly the direction this tier exists to guard against.

## What the adversarial pass caught

Five rows were classified as free relabels and then refuted. Each would have
been recorded as `verified fixed` on the strength of a test that does not
exercise the fix:

| Row | Moved | Why the relabel was wrong |
|---|---|---|
| `D-A11Y-2` | 3a -> 3b | The prior agent's own mutation was too weak and it drew the wrong conclusion from it. They deleted the L8 kit block AND the L7 loop together -- which removes the identifiers the inspect.getsource test greps for, so of course something went red. I ran the mutation that matters instead, on a scratch c... |
| `D-A11Y-4` | 3a -> 3c | The prior agent checked that the narrowing did not lose coverage by counting Accessible.EditableText declarations. That is the wrong denominator, and it is the one check that could not fail. The probe measured exactly THREE roles -- the table at docs/QA-A11Y.md:417-419 has three rows: StaticText, Ed... |
| `D-GS-2` | refuted, tier stands (3b) | The TIER is right but its load-bearing reason is wrong, and the fixture it asks for is twice the size it needs to be. Reason (1) says the epgCarries term 'only decides row height when rowShowsGroup is false, i.e. on a SINGLE-GROUP list or inside a group scope' and then rules the configured source ou... |
| `D-PIP-2` | 3a -> 3c | REFUTED. The 3a claim rests on a circular mutation against the wrong function, and the real defect reintroduces cleanly with the whole suite green. THE DECISIVE MEASUREMENT. D-PIP-2 is a Service.qml WIRING defect: 'Service.qml must not decide dispatch_failed from Process exit status' (QA-RESULTS.md:... |
| `D-QA-09` | 3a -> 3b | The 3a claim covers only HALF the defect the row states. STATUS.md:198 names "Option-looking `#EXTVLCOPT` AND `#KODIPROP` keys" -- two independent `elif _SAFE_OPTION.match(key):` branches in make_channel (bin/omarchy-iptv:768 and :780). Only the EXTVLCOPT branch is exercised. I mutated ONLY the KODI... |
| `D-RUNG-4` | 3a -> 3b | The live pass proves TWO of the five sites the row claims, and one of the three unproven ones CANNOT BE EXERCISED ON THE CONFIGURED LIST AT ALL. I read the whole PO addendum (docs/CONTRAST-RULING.md:514 to the end of the D-RUNG-4 section) and grepped it for 'number', 'confirm', 'dialog', 'rung' and ... |
| `D-SG-1` | 3b -> 3c | This one is wrong and I can show it with numbers. The claim is that the configured 28-group list cannot exhibit the defect or the fix's three accepted costs, so a synthetic single-group list is required. I ran the SHIPPING logic over the live cache twice -- current Model.js, and Model.js from e90472... |

The recurring mechanism is the one CLAUDE.md rule 14 names: an acceptance
criterion that greps for the string the implementation was written to
contain. A test that counts `selectedText: root.selectedText` as literal
text in `Guide.qml`, or asserts on `inspect.getsource(guard_tree)`, cannot
go red for the defect it claims to cover.

## 3b: the fixture matrix

Declared BEFORE anything runs, which is the whole point. Sources:
**A** the configured list (iptv-org, 1,472 channels, 28 groups, tvg-id on
100 per cent); **C** a repo or harness fixture; **D** a synthetic fixture we
must still write. No row needs the subscriber's provider lists, so the whole
pass can run without a credential anywhere near it.

| Row | Tier | Repro source | Why the configured list cannot do it |
|---|---|---|---|
| `D-CHNO-1` | 3b | C fixture-harness.m3u.in | The configured source (iptv-org.github.io, 1,472 channels) carries ZERO channel numbers. Running the shipping code against its cache: Model.buildChnoIndex(channels) returns {hasNumbers:false, count:0, duplicates:0, maxLa... |
| `D-CHNO-2` | 3b | C fixture-harness.m3u.in | Identical to D-CHNO-1 and proved with the same call: Model.buildChnoIndex over the configured cache returns hasNumbers:false / count:0, and Model.numberKeyAction on a digit returns "noNumbers", so no entry ever opens and... |
| `D-GS-2` | 3b | D synthetic | The configured source is iptv-org: 28 groups, so in All scope rowShowsGroup is already true and the EPG term never decides row height; tvg-id on 1,472 of 1,472, so its own guide data matches and carries is true; and epgU... |
| `D-ID-1` | 3b | D | The configured source (origin "migrated", label iptv-org.github.io, 1,472 channels) carries a unique tvg-id on every row, so every id is `t:` under BOTH schemes. Scheme 2 only substitutes `u:` ids with `n:` ids, so there... |
| `D-GS-4` | 3c | A configured | - |
| `D-PIP-4` | 3c | C fixture-harness.m3u.in (scripts/dev-harness/fixtures, play... | - |
| `D-PIP-5` | 3c | C fixture-harness.m3u.in plus the stub's seeded foreign wind... | - |
| `D-PIP-6` | 3c | C fixture-harness.m3u.in served by scripts/dev-harness/run.s... | - |
| `D-QA-04` | 3c | A configured | - |
| `D-RUNG-1` | 3c | A configured | - |
| `D-RUNG-5` | 3c | A configured | - |
| `D-SG-1` | 3c | D synthetic | The configured source has 28 groups, so a search key is mostly channel name and a group fragment can at most pull in that one group. The reported symptom - a fragment matching every channel on the list, the header saying... |
| `F-CHNO-3` | 3c | C fixture-harness.m3u.in | - |

### Fixtures that must be written before the display session

**D-GS-2** -- A pair generated with scripts/gen-playlist.py into a scratch dir (never committed with credentials; hosts stay under .test). (a) NEGATIVE: one playlist, ONE group only (--groups 1, so groupsNarrow is false and epgCarries is the term that decides height), >= 60 channels so the fold is visible, tvg-id on 100% of rows, plus an XMLTV generated with --xmltv and --now $(date +%s) --hours 24 whose channel ids are DISJOINT from every id in the playlist (generate the XMLTV from a second run with a different id prefix, then verify the intersection is empty with a two-line python set check before the pas...

**D-GS-4** -- Not needed for the shape, but the EPG URL must point at an XMLTV that actually loads so the three files exist to be deleted: regenerate one with scripts/gen-playlist.py --xmltv --now $(date +%s) into a scratch dir. tests/fixtures/qa-epg.xml is dated 2026-09-12 and now falls outside the +-24 h window, so it is a poor choice for this.

**D-ID-1** -- A committed pair of local .m3u files plus a seeded state.json, all ASCII, plain http:// or local paths, no userinfo and no credentials (suggested: tests/fixtures/qa-id-rotate/list-v1.m3u, list-v2.m3u, state-seed.json). list-v1.m3u must contain, in one file: 1. ~6 rows with NO tvg-id and a UNIQUE channel name -> legacy id `u:<fnv1a32(url)>`, scheme-2 id `n:<hash(name)>`. These are the rows that must move; six rather than one so `moved N` is a visible count and an off-by-one is legible. 2. ~2 rows whose tvg-id is DUPLICATED across an HD/SD pair (the qa-attrs.m3u shape) -> legacy `u:` because the...

**D-SG-1** -- One playlist, generated into a scratch dir with scripts/gen-playlist.py (URLs stay under the reserved .test TLD; no credentials, unlike the subscriber's list), added to the plugin as a LOCAL FILE PATH: (a) exactly ONE group, whose group-title is a two-word name sharing fragments with ordinary queries - "United States" is the name the measurements and the hint tests already use, so post-process the generated group-title to it if --groups 1 does not yield a multi-word name; (b) >= 3,000 channels so the 200-row cap and the "First 200 of N - keep typing" footer both appear (3,335 reproduces the fi...

## Every row, by tier

### 3a (11)

- **`D-A11Y-3`** The gate really does discover the 32 a11y tests now, and the step bites when one of them breaks.
- **`D-A11Y-5`** The UX.md table correction is in place and true when the shipping function is actually called - but the correction shipped with two line citations that no longer resolve.
- **`D-A11Y-6`** The one accessibility claim this project has confirmed by observation on the real bus - but its wiring citation has rotted and the gate does not protect the binding.
- **`D-CL-1`** The stand-down journal line ended `(intent %d over %d)` and those two numbers are equal by construction, so the diagnostic could never say what it was added to say.
- **`D-GS-1`** The failure notice `Failed HH:MM - Space to retry` rendered at the 0.52 dim rung, putting it under 4.5:1 on the cursor row - the only text on the card under AA and the one that names a key.
- **`D-LIVE-22`** Footer precedence: an EPG/playlist warning outranked the `N channels - cached HH:MM - offline` counts line, hiding the footer's only staleness cue behind a stale cache after a failed refresh.
- **`D-PLY-11`** Eight concurrent `play` calls at a cold player left nowPlaying naming a different channel than the player was on; fixed by the helper standing down when a newer channel is already on a player it just spawned, plus the CL5 shell-side re-appl...
- **`D-PLY-8`** A wedged stop left $XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock behind because the single-shot settle guard looked at 4-8 ms while a killed player stays bound for ~10-25 ms; the bounded re-check fixed it.
- **`D-PLY-9`** player-scenario.sh's log_count returned two lines on a no-match, so the P11 'exactly ONE relaunch' assertion died as an arithmetic expansion and never executed on either tree.
- **`D-QA-10`** Same stale cell as D-QA-09: an assertion naming D-QA-10 by id is in the gate, and the mutant fails on that exact line.
- **`F-CHNO-4`** The board recorded M2-03 as todo with no owner and no evidence after the work had merged; filed as a one-off, it was a class - 32 more ids later drifted off the same way.

### 3b (7)

- **`D-A11Y-2`** guard_tree now runs all four layers and the gate proves it behaviourally, not by reading its own source.
- **`D-CHNO-1`** Duplicate cycling resolved against the LIVE cursor instead of the pre-entry snapshot, so an HD twin was unreachable by number and every commit reported ordinal 1.
- **`D-CHNO-2`** An absent number could silently tune elsewhere: the unambiguous auto-commit on a proper prefix closed the entry and the leftover digits opened a new one that landed somewhere with no error.
- **`D-GS-2`** With guide data configured but no tvg-id matches, every row went to 52 px with a blank second line; the fix decides row height from Model.epgCoverage (data) instead of epgConfigured (setting).
- **`D-ID-1`** A provider password change silently erases every favourite and recent, because ids fall back to a hash of the credentialed stream URL; the scheme-2 fix plus its one-time state migration has never run against data that can actually move a ro...
- **`D-QA-09`** The row says no assertion is tied to it; an assertion naming D-QA-09 by id has been in the gate all along, and it goes red against the pre-fix behaviour.
- **`D-RUNG-4`** Already live-confirmed on rose-pine with a before/after measurement table, and backed by nine node checks that call the shipping cursorInk.

### 3c (11)

- **`D-A11Y-4`** A documentation fix - CLAUDE.md rule 5 now states the measured behaviour, and the narrowed claim resolves in the shipping code.
- **`D-GS-4`** Clearing a source's EPG URL left epg-now.json, epg-status.json and epg-window.txt in its cache, so after a restart epg.configured was false, epg.loaded true and the guide-data warning was back in the footer.
- **`D-PIP-2`** A design defect (deciding dispatch_failed from hyprctl's exit status) that was caught before any code was written and never shipped; the design row is struck, the built code decides success only by compositor readback, and that readback rul...
- **`D-PIP-4`** After a shell restart in PiP the plugin reported status.pip.on false for 30 samples; the pure half of the fix (Model.pipDeriveState/pipDeriveGate) is gate-proven, but nothing executable proves Service.qml actually runs that read on reattach...
- **`D-PIP-5`** focusPlayerArgv focused by class and landed on a stranger's mpv 3 times out of 3; the builder half is now gate-proven at the level of which window the command reaches, but that Service.qml passes the pid-resolved address has only ever been ...
- **`D-PIP-6`** The coverage row whose whole claim is that the harness live half can now pass; that half has never been run by anybody, and the fixing commit says so in its own message.
- **`D-QA-04`** The `toggle` and `previous` IPC verbs ship and are registered on a real shell, but nothing in this repository has ever invoked either one.
- **`D-RUNG-1`** The 0.45 opacity rung was raised to 0.7 at five real sites, but the fix has never been rendered and nothing in the gate touches it.
- **`D-RUNG-5`** The alpha fix is really in BarWidget.qml, but the gate cannot see the wiring at all - the defective Qt.darker can be restored with everything green.
- **`D-SG-1`** On a single-group list every search key ends with the group name, so any substring of it matched ALL channels and the header/footer reported 3,335 matches for a query with 19 real ones; matchRank tier 3 now requires whole words.
- **`F-CHNO-3`** The four harness verbs (number, numberState, commitNumber, cancelNumber) plus the state() extension that scenarios N1-N16/N21-N24 needed did not exist, so those scenarios had a specification and no runner.

### 3d (1)

- **`D-QA-18`** The removed branch was provably a no-op - both arms returned the same object - so there is no behaviour to re-test, and the gate does not cover the HTTP+gzip path either way.

### unresolved (2)

- **`D-PLY-10`** The player wrote mpv's shader cache into ~/.cache/mpv/, outside README `Files it writes`; the containment half is proven twice live, but the documentation half the row was filed under is still wrong at HEAD - and now inverted.
- **`D-QA-17`** Three of the four halves verify by reading, but the fourth is false: the README does NOT document the plugin's own `toggle` verb, and the row's claim that it does was graded by a grep that hits `shell toggle` and `pip toggle`.

## What is still owed

- **3c** is 11 rows and wants one display session. The three extra items the
  roadmap attaches to it (the D-RUNG-6 discriminator, the calibration
  top-up, D-RUNG-7) still ride along.
- **3d** closures beyond the one row found here: D-RUNG-2 and D-PLY-11's
  siblings were not in scope for this pass.
- The 2 unresolved rows below need a decision, not a test.

  - **`D-PLY-10`** The player wrote mpv's shader cache into ~/.cache/mpv/, outside README `Files it writes`; the containment half is proven twice live, but the documentation half the row was filed under is still wrong a...
  - **`D-QA-17`** Three of the four halves verify by reading, but the fourth is false: the README does NOT document the plugin's own `toggle` verb, and the row's claim that it does was graded by a grep that hits `shell...

## Method note

Relabels were applied by a script that replaces only the last table cell and
refuses on anything ambiguous: a row it cannot find, a row it finds twice, a
replacement that is empty, names no state word, is not ASCII, or contains a
pipe. The pipe rule is not fussiness. `scripts/check-defect-ledger.py` splits
a row on a raw pipe, so a code span containing one moves the state cell and
the checker reads a mid-sentence fragment as the state. Escaping it as `\|`
renders correctly and still fools the checker, so the text is written without
pipes instead. The first draft of the apply script also doubled the cell
separator, which shifted every relabelled state one column right while the
gate stayed green -- caught by diffing the per-row cell count against the
baseline, not by the gate.

## Addendum: the two unresolved rows, settled

Both turned out to be defects in `README.md` -- the file a marketplace reviewer
reads -- and both were settled the same day, at the desk.

**D-QA-17.** One of its four halves was not unverified but FALSE. The row
claimed the README carried `previous` and `toggle` in the command list.
`previous` was there; the plugin's own `toggle` verb never was. What the README
documented was the HOST's `omarchy-shell shell toggle <id>` and the `pip
toggle` mode, and the claim had been graded by a grep that hits both of those.
Rule 14 again, and the third instance this pass found. `Service.qml:3758` ships
`function toggle(): string`; it is now documented.

**D-PLY-10.** The interesting one. The containment fix was proven live twice,
so the row looked closeable -- but the fix had made the README wrong in the
opposite direction. The README still listed `~/.cache/mpv/` under Files it
writes, a write that no longer happens, while omitting the two that do. A row
can rot by being fixed.

The correction was written by reading the argv the helper really builds rather
than its docstring: `--gpu-shader-cache-dir` and `--icc-cache-dir` land in
`$XDG_RUNTIME_DIR/omarchy-iptv/shader-cache`, `--watch-later-dir` in
`.../watch-later`, and `--screenshot-dir` under the state directory the README
already documents. Stated as a default rather than a guarantee, because ruling
CL2 leaves both cache paths unreserved so an `mpvArgs` token can still move
them.

## Addendum: the gate could not see the damage this pass did

While relabelling, the apply script emitted a doubled cell separator. Every row
it touched grew an empty cell and its state slid one column right, and
`check.sh` stayed green throughout: the ledger asked for "at least 4" cells and
then read the LAST one, which still held a state word. It was caught by diffing
per-row cell counts against a baseline, which nobody will remember to do.

`scripts/check-defect-ledger.py` now requires exactly four cells and splits on
an UNESCAPED pipe. Both halves are load-bearing: exactness alone would condemn
D-PLY-9, whose Repro cell legitimately quotes shell containing a pipe. Proven
in both directions -- the doubled-separator case is green against the checker as
it shipped and red against the fix.
