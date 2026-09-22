# QA-A11Y -- the accessibility harness

## 1. What this is, and what it is not

This harness instantiates the plugin's own QtQuick content inside a plain,
hidden Qt window, lets Qt's AT-SPI bridge publish an accessibility tree for it
on a private D-Bus, and walks that tree from a stdlib-only Python client,
asserting roles, names, descriptions, values and declared states. **It proves
that our markup becomes real accessibility nodes with the right words on them.
It does not prove that any of it reaches a screen reader, and on this desktop
none of it does** -- no window Quickshell creates publishes a tree at all
(D-GS-3, quickshell issue 1144), so the shipping guide announces nothing to
anything today. Those are two different claims and this document never merges
them. It is also **not a gate**: PLAN-NEXT decision 9 keeps it out of
`scripts/check.sh`, its baseline on shipping code is deliberately red, and the
AT-SPI half needs a live graphical session. Read every green below as "the
markup composes and publishes correctly in a window the user never sees" and
nothing more. Three separate attack passes each broke shipping code and watched
this harness report its exact documented baseline; section 6 lists every way
that is still possible.

## 2. Where it lives

| Piece | Path | Tracked |
|---|---|---|
| Fidelity guard, scanner, its tests and its mutation runner | `/home/ricky/Projects/omarchy-iptv/tests/a11y/fidelity.py`, `qmlscan.py`, `test_fidelity.py`, `mutate_guard.py` | yes (ad6cddc, 7fb838a) |
| Bus client, walker, settle poll | `scratchpad/probe/atspi.py`, `dbusmin.py`, `walk.py`, `settle.py` | **no** |
| Tree generators | `scratchpad/probe/make_tree.py`, `make_bartree_lane2.py` | **no** |
| Hosts (the QML that drives a scenario) | `scratchpad/probe/host_lane2.qml`, `barhost_lane2.qml`, `host_src.qml`, `barhost_src.qml` | **no** |
| Checkers | `scratchpad/probe/check_lane2.py` (64 checks), `check_a11y.py` (19, the prototype) | **no** |
| Mutation runners and self-tests | `scratchpad/probe/mutate_lane2.py`, `mutate.py`, `selftest_settle_lane2.py`, `restless.qml` | **no** |

The scratchpad path is
`/tmp/claude-1000/-home-ricky-Projects-omarchy-iptv/9cfaeb3a-a965-43a6-9f12-4d9f27f8402a/scratchpad/probe`.
It is session-scoped and will not survive. **Everything in the "no" rows is one
`rm -rf` away from being a receipt for a run nobody can repeat** -- which is
exactly the status this document assigns to the twelve OBSERVED-ONCE rows in
`docs/UX.md` 7.1. Open item 12.

## 3. How to run it, and what a run costs

Text-only, needs no display, no D-Bus, no Qt:

```
python3 tests/a11y/test_fidelity.py                      # 29 cases, ~7.3 s, green on shipping code
python3 tests/a11y/mutate_guard.py                       # 13 mutations of the guard itself
python3 tests/a11y/fidelity.py --print-transform         # the declared transform, as data
python3 tests/a11y/fidelity.py \
    --pair Guide.qml=<tree>/GuideProbe.qml \
    --copy Model.js=<tree>/Model.js \
    --kit /usr/share/omarchy/shell/Ui=<tree>/qs/Ui \
    --kit /usr/share/omarchy/shell/Commons=<tree>/qs/Commons   # exits 1 on any drift
```

Needs a real graphical session (Wayland platform plugin; see section 7):

```
cd <probe>
python3 make_tree.py && python3 make_bartree_lane2.py
python3 check_lane2.py            # 64 checks, ~17 s, 3 failures expected (the baseline below); a fourth, L2-SC-02, seen 2026-09-21, is D-A11Y-7
python3 mutate_lane2.py           # 24 mutations, each a full regenerate + run
python3 selftest_settle_lane2.py  # the waits, proven both ways, ~20 s
python3 check_a11y.py             # the prototype, 19 checks, ~3.9 s, 1 failure (see open item 11)
```

**What a run costs, measured.** One `dbus-daemon` started by `walk.py` from its
own rewritten `bus.conf`, addressed to the child through `AT_SPI_BUS_ADDRESS`
only; one QML child per scenario; both killed **by pid** in a `finally`. No
window is mapped (`hyprctl` client count 1 before, 1 across 8 polls during, 1
after). No session-bus or gsettings change --
`org.gnome.desktop.interface toolkit-accessibility` reads `false` before and
after, `org.a11y.Status IsEnabled` stays `false`. The user's shell is never
restarted (pid stable; use `pgrep -x quickshell`, **not** `pgrep -f`, see open
item 16). Child stdout goes to a file, not an unread pipe.

Node counts, reproduced independently by an attacker: bar 3, first run 33,
no-match query 34, query 35, banner 37, Xtream 45, 10,000 channels 54.
**Since 2026-09-22 these are enforced, not merely recorded.** Every guide
scenario carries a floor on its own node count (`TREE_FLOOR` in
`check_bus.py`), asserted as `L2-TREE-<scenario>`. D-A11Y-7 is why: the probe
copy's window lost its size, both ListViews lost their viewport, and the suite
reported 63 of 64 green over a tree with one channel row and no group entries.
That regression now produces seven named failures saying the tree collapsed,
instead of one that looks like a string defect. They are FLOORS: a tree may
gain nodes, never lose them. Raise one when a scenario grows; never lower one
to make a run green. Baseline is now **72 checks, 3 failures**.

**Re-measured 2026-09-22 and each is one higher** -- 34 / 35 / 36 / 38 / 46 /
55, bar still 3 -- consistently across all six guide scenarios. The drift
predates the D-A11Y-7 harness regression: running the probe at `be7fc3c^`
gives the same +1, so a node was added to every guide scenario some time after
2026-09-15 and the record was never updated. The figures above are the
2026-09-15 record; the parenthesised set is what the probe produces today.
Anyone comparing should use the newer set. The
prototype's three guide scenarios are 37 / 43 / 43 (the design's "45" for the
revealed form is stale -- decision 5 deleted `Accessible.passwordEdit` and two
nodes with it). Settle is a bounded stability poll (12 s deadline, 40 polls, 3
consecutive identical walks), 0.21-0.61 s per scenario, replacing a fixed 1.5 s
sleep whose margin had never been measured.

## 4. Every assertion, by scenario, as what a user would hear

Baseline failures are marked **RED**. They are red because the code is wrong,
not because the harness is.

### 4.1 Harness self-checks (must be green before any result is readable)

| Id | What it means | Note |
|---|---|---|
| `L2-RUN-<scenario>` | the tree stopped moving inside the poll budget | see section 6, it has never observed instability |
| `L2-MARK-<scenario>` | the probe reported its own final state before we walked | bounded, reports giving up |
| `L2-FIDELITY` | the generated copy the guide scenarios grade is still the shipping `Guide.qml` | import failure is recorded as a FAILURE, never a skip |
| `L2-FID-BAR` | every tracked QML that declares accessibility is graded by a scenario | joined by a call (`fidelity.ungraded_surfaces`), not by a name (rule 13) |

### 4.2 Bar widget -- idle, playing, error

"IPTV, idle" / "IPTV, playing channel 101, BBC One HD" / "IPTV, playlist error".

- `L2-BAR-01-*` one button node, not two.
- `L2-BAR-02-*` the name equals `Model.barAccessibleName` called for real. (Self-oracled -- section 6.)
- `L2-BAR-03` the channel number is spoken as words, "channel 101" (M2-03 8.1).
- `L2-BAR-04-*`, `L2-BAR-07` the three R7 codepoints U+F0502 / U+F0567 / U+F0503, distinct.
- `L2-BAR-05-*` no node hands a Private-Use glyph to a reader. (Narrower than its label -- section 6.)
- `L2-BAR-06` the three states are three distinct announcements.

### 4.3 First run

- `L2-FR-01` a new user lands on a Dialog called "Set up a playlist" -- not an unnamed box.
- `L2-FR-02` the one field that matters is an EditableText called "Playlist URL or path".
- `L2-FR-03` the empty field reads back as empty, **not** as its placeholder.
- `L2-FR-04` the submit control is announced as "Load".

The first-run title and prose are absent from the bus; the investigation's
"nothing readable at all" is overstated for the form path and correct for the
prose.

### 4.4 Banner and footer

- `L2-BAN-01` the failure a user must act on is an AlertMessage carrying its text.
- `L2-BAN-05` with nothing wrong, the banner announces **nothing** (differential; a bare existence check would pass over a banner that shouts always).
- `L2-BAN-02` the footer status reaches the bus as a StaticText.
- `L2-BAN-03` a reader is told **in words** that the data is stale ("cached", "offline") and is not told so when it is fresh.
- `L2-BAN-04` no provider credential rides along on the failure text.

### 4.5 Active query, and a query that matches nothing

- `L2-Q-01` the search line is an EditableText called "Search channels".
- `L2-Q-02` it reads back what was typed, not the placeholder.
- `L2-Q-03` UX 7.1's `description` = the current query holds on the bus.
- `L2-Q-04` the matching row is announced with its place in the filtered list. (Self-oracled.)
- `L2-Q-05` **RED.** When nothing matches, something on the bus must say so. Nothing does: the "No matches" surface is an unannotated `Text`, so a screen-reader user hears an empty list and no reason.

### 4.6 Ten thousand channels

- `L2-SC-01` the channel list is still a named List.
- `L2-SC-02` the group entry counts in words. (Label overclaims; see section 6.)
- `L2-SC-03` a row still carries its position. (Label overclaims; see section 6.)
- `L2-SC-04` virtualisation is visible on the bus and bounded -- a reader reaches a window of rows, never 10,000.

### 4.7 Xtream form -- the unconsented sinks (decision 7)

Populated by the scenario with three distinct tokens and **no user action**.

- `L2-XT-01` the form is a Dialog called "Add Xtream login".
- `L2-XT-02` / `L2-XT-03` the server and username fields are named "Server URL" and "Username".
- `L2-XT-04` the password field carries its label through `Accessible.description` (decision 5, shipped).
- `L2-XT-05` **RED.** The provider login pasted into the unmaskable Server field reaches the accessibility bus in full, as the field's accessible Value. First time D-A11Y-1 has been *observed at the sink* rather than reasoned about from source.
- `L2-XT-06` **RED.** The Xtream username likewise.
- `L2-XT-07` green: the password plaintext does not reach the bus; `echoMode` publishes bullets. Asserted so it cannot regress silently.
- `L2-XT-08` / `L2-XT-09` **the anti-false-green pair.** What the user typed is still in the form, character for character, digest and length equal, before and after the walk. This is not a policy about the bus, so no ruling can dissolve it: *observing must not mutate*.
- `L2-XT-10` the fields are still announced by name in the same run the credential check passes, so deleting the node is not a way to pass. (Redundant with 02/03 -- section 6.)
- `L2-XT-11` **RED.** Eye buttons on a form where no field is maskable publish "Hide query" with `checked=true`. UX-SOURCES 7.1 rules that `checked` *means revealed*; `Guide.qml:3242` binds `Accessible.checked: !fieldRow.masked`, and `masked` is false both when a field is revealed and when it was never maskable. (Contested -- open item 15.)

**Nothing anywhere asserts what a deliberately revealed field may publish.**
PLAN-NEXT decision 8 is unanswered. Verified three ways: no reveal drive in the
hosts, no reveal assertion in the checkers, and the `masked`/`maskable`
readbacks are collected and asserted on by nothing.

### 4.8 Prototype guide scenarios (`check_a11y.py`, 19 checks)

Guide card Dialog "IPTV guide"; search line; group column List "Groups"; group
entry with `selected` on exactly the selected entry; channel list "Channels in
All"; channel row name and `focused` on the cursor row; footer StaticText;
pinned Sources Button; Sources List; action rows; "Edit <label>" / "Remove
<label>" buttons; form Dialog; playlist and label fields; Cancel / Save; and a
credential sweep per scenario. These are the only observations behind twelve
OBSERVED-ONCE rows. **This checker should be retired in favour of
`check_lane2.py`** -- open item 11.

## 5. The fidelity guard

The harness grades a *generated copy* of `Guide.qml`, rehosted out of a
`PanelWindow` into a plain `Window`. The whole anti-drift argument rests on
proving that copy still matches what ships. That assertion was described in the
present tense in the design and **did not exist**; it does now.

**What it checks.** The transform is declared as data -- five contiguous block
rules with rationales -- and that same table is the executable transform, so a
generator and a checker cannot drift into two truths. Eight layers: L1 no
changed line may contain `Accessible.` at all; L2 every added or removed line
attributed to a declared rule with exact counts, and a rule that *stops* firing
is red too; L3 projection equality after exactly one declared attachment rename
(the `PanelWindow` inside `Component { id: layerHost }` -> a plain `Window`, the Loader and the reparented content kept; `tests/a11y/make_tree.py` obtains the copy by calling `fidelity.apply_transform`, so the generator and the guard share one rule set); L4 elements the transform adds declare
no accessibility; L5 the shipping file declares no accessibility on the element
being rehosted; L6 verbatim copies byte-identical; L7 inventory of surfaces
nobody grades; L8 the copied host UI kit byte-identical except four declared
patches. The scanner extracts the *accessibility projection*: every
`Accessible.*` binding and `Accessible.announce()`, **plus every other binding
on the same element**, each tagged with its attachment path. The sibling half is
load-bearing, not thoroughness: Qt publishes an editable field's accessible
Value from its `text:` binding, so the sink D-A11Y-1 leaks from is not spelled
`Accessible.` at all.

**What forced drift proved.** Drift was caused on real generated trees, not
read about:

- a declaration dropped from the copy only -- RED at L1+L2+L3, "1 declaration(s) lost";
- a declaration added to the copy only -- RED, "1 gained";
- a declaration **moved to a different element with byte-identical text** -- invisible to a line diff, caught by L3 via the attachment path, "3 lost, 3 gained";
- a non-accessibility line changed in the copy -- RED at L2 residual + L3;
- `tree/Model.js` drifted -- RED at L6;
- the prototype's own worked example, the proposed credential remedy that rebinds `text:` to the masked rendering: `check_a11y.py` reports **19 checks, 0 failures** over silent credential replacement, the guard reports **2 findings** and names the line and the element. Reproduced verbatim by an attacker.
- unplanned: while another lane was mid-mutation in the shared tree, a guard run caught their in-flight `Accessible.name: ""` and named it at `Guide.qml:3106`.

`mutate_guard.py`: baseline green over 29 cases, 13 mutations, **all 13 killed**.
Every layer is load-bearing (L3 off kills 9 cases; dropping the sibling bindings
kills 4; dropping the attachment point kills 5). The runner fails safe: run from
outside the repo it prints "BASELINE IS RED, every result below is unreadable"
rather than reporting kills over a broken baseline.

**What it cannot carry across.** An `Accessible.*` declaration on the
`PanelWindow` itself (L5 turns its arrival red rather than quietly regrading).
Any AT-SPI state that comes from the runtime rather than a declaration --
`showing`, `visible`, `active`, real Qt focus -- because the window is never
mapped and the layer-shell `keyboardFocus` line is deleted. Accessibility that
comes from a **type** rather than a declaration: `Ui/TextField.qml` is a
Controls TextField and publishes a role and a value of its own; only L8 and the
bus can see that. The two clipboard calls are stubbed and theme values come from
a shim. It evaluates no bindings: two expressions that differ only in something
it cannot evaluate compare as text, and a pure reordering within one element
reads as drift. A deliberate harness mutation *is* drift by definition, so
mutation runs must declare themselves.

**And the limit nobody stated in the design:** the guard proves the copy matches
the source. **It can never prove the source is right.** An accessibility
regression made in `Guide.qml` propagates into the regenerated copy and is green
by construction. Anti-drift is not anti-defect. See open items 1, 6, 7, 8.

## 6. The mutation evidence

### 6.1 Mutations that went red at the named assertion

| Broken | Went red |
|---|---|
| bar name no longer from the composer | `L2-BAR-02` (x3), `L2-BAR-03`, `L2-BAR-06` |
| bar role Button -> StaticText | `L2-BAR-01` (x3) + 5 more |
| error glyph collapsed onto idle | `L2-BAR-04-error`, `L2-BAR-07` |
| glyph handed over as the name | `L2-BAR-05` (x3) |
| form dialog loses its name | `L2-FR-01`, `L2-XT-01` |
| field labels removed | `L2-FR-02`, `L2-XT-02`, `L2-XT-03`, `L2-XT-10` |
| submit verb stops being "Load" | `L2-FR-04` |
| empty field reads back its placeholder | `L2-FR-03` |
| banner role downgraded, or silenced | `L2-BAN-01` |
| banner announced when nothing is wrong | `L2-BAN-05` (the differential is live) |
| a source URL rides the failure text | `L2-BAN-04` |
| footer unannounced / stale no longer said in words | `L2-BAN-02`, `L2-BAN-03` |
| search line loses its name, or reads the placeholder, or drops `description` | `L2-Q-01`, `L2-Q-02`, `L2-Q-03` |
| channel list List -> Grouping | `L2-SC-01` |
| password label replaced by its value | `L2-XT-04`, `L2-XT-07` |
| **the proposed credential remedy, verbatim** | `L2-XT-09` RED (the masked string is fed back through `onTextChanged` and replaces what the user typed) **while** `L2-XT-05` turns GREEN, plus `L2-FIDELITY` red independently. The prototype scored this remedy 19/0. Two independent routes now score it a failure. |
| the guard's own eight layers and scanner faculties | 13 of 13 killed |
| `accessibleCard` blanked (the guide card announces nothing) | **nothing that ships.** Retired greps byte-identical, node suite 1331 checks 0 failures, QML spec 66 passed, fidelity guard 29 OK. Only an AT-SPI observation catches it, and that row is OBSERVED-ONCE. |
| `Model.barAccessibleName` returns "" | node suite, 2 failures -- the COMPOSED layer doing exactly what COMPOSED claims and no more |

Two honesty findings surfaced by running the mutations rather than writing them:
a footer check that compared name to value was **tautological** (a StaticText's
published text *is* its accessible name on Qt 6.11.2) and was replaced with the
stale-in-words differential; and `mutate_guard.py` was counting *unapplied*
mutations as kills, which was hiding one.

### 6.2 Assertions that survived every mutation -- these assert nothing, or less than their label

- `L2-XT-08` (EARLY vs LATE digest divergence) -- never seen red. It is a second net behind `L2-XT-09`; the bug class is proven caught, this particular check is not.
- `L2-RUN-*` and `L2-MARK-*` -- proven only at the settle layer by the self-test, never by an end-to-end mutation. Also: across all nine scenarios the poll always reports "settled after 3 walks", which is the floor. **It has never once observed the tree moving.** The real waiting is done by the marker wait.
- `L2-BAR-02`, `L2-Q-04`, `L2-SC-02`, `L2-SC-03`, and the prototype's row-name and `focused` checks -- **self-oracled.** `model_says()` shells out to node against the repo's `Model.js`; the tree instantiates a byte-identical copy of that same file. They are `Model.f(x) == Model.f(x)` in two processes. They prove the **join** (the string became a node), which is a real advance over the 17 unit assertions, and they can never disagree about the **words**. Measured: the shipping `Model.js` was rewritten so the bar says "nothing on" and "tv broke", the thousands separator was removed, and the row total was deleted -- **64 checks, 4 failures, the exact documented baseline, zero new failures.**
- `L2-SC-02`'s "thousands separated" and `L2-SC-03`'s "row N of 10,000" -- nothing asserts a comma, and only the substring ", row " is literal. Both mutations above stayed green.
- `L2-XT-10` -- a restatement over the same two lists `L2-XT-02` and `L2-XT-03` already assert. It inflates the count by one; it is not an independent net.
- `L2-BAR-05` -- its label ("no node hands a private-use glyph to a reader") is broader than it can observe: the bar tree is three nodes and the glyph's Text carries no `Accessible` markup, so it can fire only on the one mutation that assigns the glyph to the name.
- `test_fidelity.py`'s 29 cases as invoked in the docs -- `generated()` is `fidelity.apply_transform(source())` graded against the same `TRANSFORM_RULES` the transform executed: a value compared to a function of itself. **Re-checked this pass at `tests/a11y/test_fidelity.py:45-51`.** An unvetted rule added to the table passed all 29 while renaming a node on the bus. `A11Y_GENERATED=<real copy>` makes it real (6 failures over a genuinely drifted copy) but appears only in the module docstring.

### 6.3 Mutations that NOTHING caught

Each was applied to shipping code and measured, not argued.

1. `rowIndex: row.index` -> `rowIndex: 0`: every realised row announces "row 1 of 10,000". Green in `check.sh` (382 python, 1331 node, 66 QML spec, 83/83 ledger), `test_fidelity.py`, `guard_tree`, and **all four** scale assertions.
2. Xtream `fieldAccessibleName` server/username labels swapped: the bus announces a full provider login under the name "Username" and a username under "Server URL". 64 checks, 4 failures, byte-identical baseline. Root cause: **no assertion binds a name to the value on the same node** -- `pick()` searches a flattened list, `leaks()` reports only role and sink.
3. `visible: false` on the guide card (the element containing the whole UI): the tree is **byte-identical**, 54 nodes, every criterion green over a UI that draws nothing.
4. `visible: false` on the source row's Edit/Remove Row: those buttons are gone for every user; "Action buttons" stays green.
5. `Accessible.focused: true` on every channel row and `Accessible.selected: true` on every group: the list is unusable to a reader; output identical. `any()` and `one()` are existence tests; nothing asserts uniqueness.
6. Reverting decision 5 (deleting the password field's `Accessible.description`): green in the prototype checker *and* in the guard. Believed caught by `L2-XT-04`, which the attacker did not run -- **one measurement needed** (open item 8).
7. `echoMode: TextInput.Password` hard-wired into the tree's copy of the host kit's `TextField.qml`: **the artifact's one credential failure flipped from red to green**, and `guard_tree()` returned 0 findings. Only the CLI with `--kit` caught it.
8. Duplicating a field, dialog, row or group -- a reader hears everything twice -- passes, because there is no cardinality assertion on the guide (the bar has one).

Two of these (3, 4) share a root cause with the ghost nodes in section 7: the
probe window is never mapped, so Qt never prunes invisible subtrees.

## 7. What it still cannot verify, and why

1. **Delivery.** Nothing this plugin declares reaches assistive technology on this desktop. A plain Qt 6.11.2 window publishes `ChildCount 1`; a Quickshell `PanelWindow` publishes 0, and so does a Quickshell `FloatingWindow` -- so it is not a layer-shell problem. Filed upstream as quickshell issue 1144 and tracked as D-GS-3. **The harness proves our side would be correct if the host were. It cannot prove a user can hear anything, and today a user cannot.**
2. **Tree membership, not just states.** In a never-shown window exactly 1 of 54 nodes carries `SHOWING`/`VISIBLE`, and it is the `application` node. The walked tree is strictly *larger* than the tree a real client would traverse: six "Edit"/"Remove" buttons where at most two can be on screen, and a numeric-entry alert whose element is `visible: false`. Every existence assertion in this harness can pass on a ghost. This is the mechanism behind mutations 3 and 4 above.
3. **Rule 5's second sink is entirely unmeasured.** The client is method-call-only; `grep -rn AddMatch` across the whole probe finds nothing. It subscribes to **no** AT-SPI signal. Qt emits `object:text-changed:insert` carrying the inserted characters on every keystroke into a text input, and the Xtream server field is unmaskable -- so a remedy that masks the Value and leaves the insert payload alone would score green here, against the wrong sink.
4. **Announcement.** `Accessible.announce()` has zero call sites in the product; nothing tests whether a state change is announced as opposed to merely readable on navigation.
5. **Focus order, reading order, parent-child structure, uniqueness.** `depth` is collected and read by no assertion; "focus", "parent" and "order" do not appear in the checker. Two nodes simultaneously report `focused` in the query scenario and three in the Xtream one; nothing looks.
6. **Type-derived publishing.** What a Controls `TextField` publishes of its own accord is observable only on the bus, and the kit copy is gated only from the CLI (open item 1).
7. **Real key handling.** The form is driven through the shipping `setFieldValue`, not synthetic key events.
8. **Headlessness.** `offscreen`, `minimal` and `vnc` publish no accessibility at all (20 s give-up, no Qt connection). No nested compositor is installed (Xvfb, weston, cage, sway, wayfire, labwc all absent). A headless route does not exist by switching platform plugins; a nested compositor is the route, and it would also restore the `showing` discriminator.
9. **Deliberately revealed fields.** Out of scope by ruling until decision 8 is answered.
10. **Geometry.** `SRC-A11Y-04` (hit targets) is deliberately still a grep: a token in the source is weak evidence about geometry, but it is evidence about something the source decides. `grep Accessible.` was evidence about nothing.

## 8. The four retired greps, and what replaces them

| Case | Was | Is now |
|---|---|---|
| TC-A11Y-01 (`docs/QA.md`) | `A grep -n 'Accessible\.' Guide.qml BarWidget.qml` -- 58 lines the two files were written to contain | `X` guide scenarios of this harness, per-row against UX 7.1, satisfied only by a dated run filed in `docs/QA-RESULTS.md` "Accessibility harness runs" |
| TC-BAR-11 (`docs/QA.md`) | `A grep -n 'Accessible' BarWidget.qml` | `X` bar scenarios: one button node, the three names distinct, the three R7 glyphs, no Private-Use codepoint in a published name |
| SRC-A11Y-01 (`docs/QA-SOURCES.md`) | `A grep -n 'Accessible\.' Guide.qml` -- 56 lines | `X` Sources and form scenarios, per-row against UX-SOURCES 7.1 |
| SRC-A11Y-05 (`docs/QA-SOURCES.md`) | the single word `grep`, over a sink it does not read, still demanding `Accessible.passwordEdit: true` -- a property decision 5 had already deleted. Stale **and** blind | `X` Xtream and form scenarios, reading the accessible **Value**, in **two halves, both required**: (a) no node carries the server, username or password token in any of name, description or value, with the fields populated and **no user action**; (b) the field is undamaged -- digest, length and content equal before and after. Half (b) exists because absence of a secret achieved by destroying the data is a failed run |

A new `X` class was added to the How-column legend in both plans with rule 14
stated inline. Eight standing `pass` rows in `docs/QA-RESULTS.md` (`:143`,
`:217`, `:1048`, `:1052`, `:1065`, and carry-forwards at `:606`, `:788`,
`:1773`) are **retracted in place**, not deleted, and now read `not run`. The
board looks worse than it did and is accurate for the first time. Thirty-nine
rows across `docs/UX.md` 7.1, `docs/UX-SOURCES.md` 7.1 and
`docs/M2-03-CHANNEL-NUMBERS.md` 8.1 carry OBSERVED (18) / OBSERVED-ONCE (12) /
COMPOSED (10) / UNVERIFIED (15) markers.

**Runs filed as of 2026-09-15: none. All four cases are UNSATISFIED.**

## 9. Open items

**Blocking any citation of a run as evidence**

1. `fidelity.guard_tree()` -- the one-call gate the handoff tells the harness to adopt -- calls only `check_pair` and `check_copy`. L7 (`ungraded_surfaces`) and L8 (`check_kit`) are reachable only from the CLI. Re-verified this pass at `tests/a11y/fidelity.py:456-481`. A swapped host kit flipped the one credential failure green with `guard_tree` returning 0 findings. **Fold both into `guard_tree`, or delete `guard_tree` and make the CLI the only entry point.** Owner: `tests/a11y` (fidelity lane). Three lines.
2. Every self-oracled check needs a second, literal assertion taken from the ruled table, so `Model.f()` is never the only witness to what `Model.f()` should say. Keep the `Model.js` unit tests as the separate proof that the composer is right. Owner: harness lane (`check_lane2.py`).
3. Assert name **and** value on the same node, plus cardinality, so a swapped or duplicated label cannot pass. Owner: harness lane.
4. Either subscribe to `object:text-changed`, or state plainly in the criteria that half of CLAUDE.md rule 5 is ungraded. A masking remedy will otherwise be certified green against the wrong sink. Owner: harness lane; scope question to the product owner.
5. Record in the criteria and in `docs/UX.md` 7.1 that node presence in a never-shown window is insensitive to rendering and to pruning, so **no filed run may be read as evidence that a surface is reachable.** Owner: QA (this document + the criteria), with the nested-compositor question to the product owner.

**Harness and guard gaps**

6. `TRANSFORM_RULES` is constrained by nothing: all 29 cases and all 13 mutations target layers and scanner faculties, none poisons the table. Add at least one mutation that does, and stop presenting 29/13 as evidence about the table. Owner: fidelity lane.
7. `docs/QA-RESULTS.md` "What a filed run must contain" item 3 names `tests/a11y/test_fidelity.py` as the fidelity evidence. As documented that invocation is the tautological one. **Repoint it at `guard_tree(<the tree this run graded>)` or at the `L2-FIDELITY` check id.** One line. Owner: QA (docs).
8. Reverting decision 5 was green in the prototype checker and in the guard. `L2-XT-04` should catch it; that has not been measured. One run. Owner: harness lane.
9. `mutate_lane2.py` can only edit files inside `tree/`, and every `Model.js` tree edit trips `L2-FIDELITY`'s digest anyway -- so the suite has **no mode that mutates a shipping file and regenerates**, which is precisely the mode rule 11 asks for and the mode that exposes the shared oracle. Add it, and give mutation runs a flag so the guard does not call them drift. Owner: harness lane.
10. `mutationProof` lines for the three `Model.js` tree mutations omit `L2-FIDELITY` from their newly-red lists. Correct them when the suite lands. Owner: harness lane.

**Wrong red, and a checker to retire**

11. The prototype's single baseline failure is the `editform_revealed` scenario -- the deliberate reveal, which decision 8 leaves unruled and which nothing may assert on. Meanwhile decision 7's ruled sinks were unasserted there. The artifact's deliberately-red baseline therefore encoded an unruled policy while the ruled one had no assertion. `check_lane2.py` fixes this (`L2-XT-05`/`06` red, nothing about reveal). **Retire `check_a11y.py` rather than repair it**, and re-home the twelve OBSERVED-ONCE rows onto landed scenarios. Owner: harness lane + product owner.

**The harness is not in the repo**

12. Everything except `tests/a11y/` lives in a session scratchpad that will not survive. Move the walker, settle poll, generators, hosts, checkers and mutation runners into `tests/a11y/` (per PLAN-NEXT section 4 the harness lane owns that directory and `scripts/`), and add a README line: **copy the tree out before measuring** -- the shared directory was written by two lanes concurrently during this round and produced one reading that was green only because a mutation had been overwritten. Owner: harness lane.
13. Decision 9 is over-applied to `test_fidelity.py`: it is pure text, needs no display, D-Bus or Qt, runs in about 7 s and is green on shipping code. Decision 9's stated reasons (a deliberately red baseline, a first hard dependency on a live graphical session) reach the AT-SPI half and not this. **Ruling wanted on putting `test_fidelity.py` alone into `scripts/check.sh`**, so the guard's own proof cannot rot unnoticed. Owner: product owner.

**Document errors found by attack**

14. `docs/UX.md:896` marks the channel row's position "**UNVERIFIED.** Never promised here and never delivered." Both clauses are false, and I re-verified all of it this pass: promised at `docs/UX-GUIDE-AT-SCALE.md:768` and `:865` (ruling D5); delivered at `Model.js:4198-4217` (`node -e` gives `Channel 7, row 8 of 10,000`); asserted in `tests/Model.test.js`; observed on the bus on every realised row; and named by `docs/STATUS.md:173` itself. **Correct the row, and add the `, row N of M` suffix to UX 7.1's channel-row name cell** -- a harness built strictly to that table would assert a name the shipping code does not produce. Owner: UX. This is rule 13 drift inside the table written to end rule 13 drift.
15. `L2-XT-11` is contested. One pass calls it vacuous ("no field on the Xtream form is maskable, and the eye button is `visible: fieldRow.maskable`, so it is never instantiated"); the baseline contradicts that, since the check is **red**, which requires a non-empty eye-button list -- consistent with a `visible: false` Item still being created and still published in an unpruned tree. **One measurement settles it.** Either way its severity depends on whether an AT reaches a not-showing node, which item 5 covers. Owner: harness lane.
16. CLAUDE.md rule 5's second half ("any other annotated item publishes its text") is wrong on Qt 6.11.2, measured with a purpose-built probe: role StaticText publishes its accessible **name** as its AT-SPI Text and its own `text` property never reaches the bus; role EditableText publishes its `text` and ignores the name. This **narrows** the sink list and explains why the exposure is confined to editable fields. Owner: CLAUDE.md / architecture.
17. The lane briefs' own `pgrep -f 'quickshell -n -p ...'` **self-matches**: it returns two pids, the second being the shell running `pgrep`, and it changes between invocations. This is the exact hazard CLAUDE.md records two incidents about. The stable form is `pgrep -x quickshell`. Owner: PM (propagate into the briefs).

**Product rulings wanted**

18. The eye button's `checked` conflates "revealed" with "never maskable" (`Guide.qml:3242`). Two-character fix (`fieldRow.maskable && !fieldRow.masked`), worth doing only once item 5 settles whether a not-showing node is reachable. Owner: UX + product owner.
19. The bar announces "IPTV, idle" for both idle and "no playlist configured", while the tooltip distinguishes five states. The code matches the spec; **the spec is the gap**, and the one state that requires user action is the one a screen-reader user cannot hear. A UX 7.1 amendment, not a code change. Nothing is asserted about it. Owner: UX.
20. Decision 8 (what a deliberately revealed field may publish) is unanswered and blocks the "description = masked rendering (always)" row. Owner: product owner.
21. Four surfaces are declared in the code and absent from UX 7.1 (`Guide.qml:2053` confirm Dialog, `:2107` header Heading, `:2319` pinned Sources Button, `:2658` numeric-zap AlertMessage) -- an undocumented promise nobody grades. The numeric-zap strings are QML literals with no builder and no scenario: the one row with no evidence of any kind, and CLAUDE.md rule 12 says lift them into `Model.js`. Owner: UX (the rows), harness lane (the lift).
22. Four candidate defects have no `docs/STATUS.md` row and cannot be filed as ids without one (`check-defect-ledger.py` goes red): the guide card's own name caught by nothing that ships; `Accessible.focused` on the cursor row and `Accessible.selected` on the group entry caught by nothing that ships; `Model.sourceAccessibleName` never observed becoming a node in any landed scenario; the numeric-zap literals. Owner: whoever owns STATUS.md.

**Process**

23. Two lanes edited `walk.py` in **one working tree**, not separate worktrees as CLAUDE.md requires; the edits are backwards compatible but need one deliberate merge, not a silent overwrite. And commit `beb1eed` ("test(contrast)...") swept up another lane's uncommitted `docs/QA.md` and `docs/QA-SOURCES.md` via `git commit -a`. Those hunks are correctly attributed to the docs lane, and lanes sharing a worktree must stage **by path**. Owner: PM.
## 10. What the lead changed after the attack (product owner, 2026-09-15)

Every one of the three lanes was attacked, and **all three attackers succeeded**
in showing the lane's own work could report success while the thing it verifies
was broken. Twelve tautologies between them. That is the correct outcome for an
adversarial pass and the wrong outcome to ship, so the following were fixed
before anything was pushed. Four are filed as defects.

**D-A11Y-2, the gate that ran half of itself.** `guard_tree()` is documented as
the one call a harness gates itself on, and it called four of its eight layers.
`check_kit` (L8) and `ungraded_surfaces` (L7) were reachable from the command
line alone. The reviewer swapped the host kit underneath a generated copy and
turned a real credential failure green with `guard_tree` reporting nothing.

That is the load-bearing case, not an edge one: the guide's form fields **are**
host components, so the credential this harness hunts is published by
`Ui/TextField.qml`'s own accessibility rather than by anything `Guide.qml`
declares. A guard blind to the kit is blind to the leak.

Fixed. `guard_tree` runs all four layers. The kit must be graded unless the
caller passes `kit=False` deliberately, because an unstated missing kit was
exactly the silence that hid this. L7 gained an allow-list, `UNGRADED_ACCEPTED`,
so it reports drift rather than restating a state we already know; adding a name
there is a decision that needs a board row. Three tests pin it, one of which
asserts by inspection that the entry point calls every layer it has.

**D-A11Y-3, thirty-two tests the gate could not see.** The lane landed 32 python
tests in `tests/a11y/` and `scripts/check.sh` ran none of them:
`unittest discover -s tests` does not recurse into a directory that is not a
package, so the asserted suite count stayed at exactly the 382 it had been
before the tests existed, and the gate stayed green.

This is the fourth silent no-op this project has found and the first to land in
pushed code. `check.sh` now runs `discover -s tests/a11y` explicitly with its
own asserted floor.

**That reverses part of decision 9, deliberately.** The fidelity half is in the
gate; the AT-SPI half stays out. Decision 9's two stated reasons were a
deliberately red baseline and a first hard dependency on a live graphical
session. Neither reaches `test_fidelity.py`: it is pure text, needs no display,
no D-Bus and no Qt, runs in about seven seconds, and is green on shipping code.
A guard whose own proof can rot unnoticed is not a guard.

**D-A11Y-4, a security rule that was wrong.** CLAUDE.md rule 5 had been extended
to say any annotated item publishes its `text` to the accessibility bus. A probe
on the real bus says otherwise, and the measurement is worth keeping:

| Declared role | Accessible name | What the AT-SPI text body carries |
|---|---|---|
| `StaticText` | published | **the name**; the element's own `text` never reaches the bus |
| `EditableText` | published | **the element's `text`** |
| `Button` | published | no text interface at all |

So the exposure is confined to elements declared editable, which is the form
fields and the search line at `Guide.qml:2088`. The rule now says that. Being
wrong in the safe direction is still being wrong, and an over-broad security
rule gets ignored rather than followed.

The live pass of 2026-09-21 extended this table to all eight roles `Guide.qml`
declares, on the real bus: `docs/QA-RESULTS.md`, "Live pass 2026-09-21, segment
A", section 6. Heading behaves like StaticText (a Text interface carrying the
name); AlertMessage, List, ListItem and Dialog carry no text interface; and the
search line's placeholder reaches the bus as its value when the query is empty.

**D-A11Y-5, rule 13 drift inside the table written to end it.** `docs/UX.md` 7.1
marked the channel row's `row N of M` announcement UNVERIFIED, "never promised
here and never delivered". Both clauses were false: promised under ruling D5,
delivered at `Model.js:4213-4215`, wired at `Guide.qml:2452`, asserted in the
node suite. A harness built strictly to that table would have asserted the
absence of a string the shipping code produces.

### Two process failures, which are the lead's

**The lanes shared one working tree.** They were launched without worktree
isolation, committed to `main` directly while the lead was also committing, and
one lead commit swept two documents into itself that the lead had neither
written nor read, under a message describing something else. It was pushed. A
concurrent tree also produced one reading that was green only because a second
lane had overwritten a mutation. CLAUDE.md gains rule 4b.

**A brief written by the lead contained the exact hazard it was quoting.**
`pgrep -f 'quickshell -n -p ...'` matches the shell running it, returns two
pids, and changes between invocations. CLAUDE.md has warned about this since two
earlier incidents; the stable form, now named there, is `pgrep -x quickshell`.

### Where this leaves the four retired criteria

Unchanged and honest: **no run has been filed, so all four are UNSATISFIED.**
Section 8 is not a claim that accessibility is verified. It is a claim that the
criteria now name something that could verify it, which is what rule 14 asks
for, and the board reads worse than it did because it is accurate for the first
time.

The harness's own AT-SPI half is still in a session scratchpad and will not
survive. Moving it into `tests/a11y/` is open item 12 and is the next thing
here, ahead of any filed run.

## 11. The harness is in the repo, and it found something on its first run

Open item 12 said everything but the fidelity guard lived in a session
scratchpad that would not survive. It is now in `tests/a11y/`, with the lane
numbers stripped out of the filenames, the hardcoded home directory replaced by
a path derived from the file's own location, and the generated tree moved out
of the repo into a temporary directory.

`scripts/a11y-probe.sh` runs the whole thing: build the tree, refuse to measure
if it has drifted, walk the bus. See `tests/a11y/README.md`.

**Two defects in the guard were fixed on the way in**, both of them the same
shape as everything else this project keeps finding.

`guard_tree` graded the host kit by handing `check_kit` the entire shell
directory at once. `check_kit` derives its patch-list prefix from the basename
of the directory it is given, so it compared four hundred unrelated host files
against a copy holding two subdirectories and reported every *declared* patch as
undeclared. It now grades each section the copy actually has. Caught by running
it, not by reading it.

### The baseline, and what it means

    64 checks, 3 failures

| Check | What it says |
|---|---|
| `L2-XT-05` | the provider login pasted into the unmaskable Server field reaches the bus |
| `L2-XT-06` | the Xtream username reaches the bus |
| `L2-XT-11` | contested; see open item 15 |

The first two are **D-A11Y-1, confirmed at the real sink** rather than inferred
from reading code. They are the exposure the product owner ruled is the defect
(decision 7), as against the deliberate reveal, which nothing here asserts on
because decision 8 is unanswered.

### D-A11Y-6, and the first claim this project has verified by observation

The first run reported a fourth failure, `L2-Q-05`: *when nothing matches,
something on the bus should say so*. Measured with 0 rows, 0 nodes naming the
query. Reading the code confirmed it: **the entire empty state carried no
accessibility markup at all** -- no matches, first run, loading, error, no
favourites. At the one moment the screen is nothing but an explanation, a
screen-reader user heard silence.

Ruling SG1 had just sharpened this from latent into real. Whole-word group
matching creates a dead zone where a query legitimately matches nothing, and the
empty state becomes the only thing explaining the screen. A hint was added there
for the eye in 0.7.0; there was no equivalent for the ear.

Fixed, and then **verified at the sink**: the same tree went from 4 failures to
3. Every `grep Accessible.` criterion this project ever ran passed cleanly over
this defect for months, because the markup they searched for was never there to
find. That is the whole argument for rule 14, and this is the first time it has
paid for itself.
