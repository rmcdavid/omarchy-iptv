# Splitting `Service.qml` into code-behinds (D-REL-14)

Written 2026-11-24 on `dev` 3200d22, D-REL-14's C5. The split itself is
done and merged on `dev` (C3 on 2026-11-23, C4 and D-REL-15's fix on
2026-11-24) and **unreleased**: v0.20.0, the release on `main`, ships the
one-file `Service.qml`, so no install has run a code-behind yet. Every
figure below was read or run on 3200d22 unless a date says otherwise (the
section on updates was measured the same day with 3200d22's export; the
tree this document was merged on, branch c5d, differs from 3200d22's
service in `Service.qml`'s header comments only); the measurements behind
them are in `docs/QA-RESULTS.md` (the sections from "The
lead's follow-ups to lane-ply78 and the D-REL-14 design" to "D-REL-15:
merged") and the plan and the lead's calls are on the D-REL-14 row of
`docs/STATUS.md`. This is the service's counterpart of
`docs/HELPER-SPLIT.md` (D-REL-7) and of the model's rules in
`docs/ARCHITECTURE.md` section 9 (D-REL-5).

## Why

`scripts/release.py check` holds every shipped file at or under 448 KiB
(`FILE_CEILING`, 458,752 bytes), 64 KiB below the marketplace scanner's
per-file limit of 512 KiB (`SCANNER_FILE_LIMIT`). A file over the scanner's
limit stops the automated security baseline, and then no verification
request can be approved; the one-file `Model.js` crossed it at 0.13.5
(D-REL-5), and the helper was split before it could (D-REL-7). The service
was next. `Service.qml`, read from git:

| tree | date | bytes | under the ceiling |
|---|---|---|---|
| v0.14.3 | 2026-10-21 | 323,837 | 134,915 |
| v0.16.0 | 2026-11-01 | 379,207 | 79,545 |
| v0.19.1 | 2026-11-13 | 398,480 | 60,272 |
| 81afa9f, D-REL-14 filed | 2026-11-21 | 444,947 | 13,805 |
| v0.20.0 (released, one file) | 2026-11-22 | 446,973 | 11,779 |
| 8e3bbac, C3 merged | 2026-11-23 | 409,149 | 49,603 |
| 76297fe, C4 merged | 2026-11-24 | 229,117 | 229,635 |
| 3200d22, this document | 2026-11-24 | 230,265 | 228,487 |

It grew 46,467 bytes in the eight days after 0.19.1, the player rounds of
November (D-PLY-39 to -76) most of it, so a few more rounds would have
reached the ceiling and `release.py check` would then have refused the
cut. The service's one text on 3200d22 -- its inline view, below, what
the one file would weigh -- is 449,007 bytes, 9,745 under the ceiling. On
c5d, after the header's comments were re-worded, `Service.qml` is 231,016
bytes and the view 449,758, 8,994 under it.

The plan was chosen on 2026-11-21 from three read-only designs and a judge
(QA-RESULTS "The lead's follow-ups to lane-ply78 and the D-REL-14 design"):
- lifting pure logic into the model saves about 7.6 KB, because the code
  barely moves;
- moving the long comments into an anchored document saves about 150 KB, but
  parts the reasoning from the code it explains, joined only by anchors
  (CLAUDE.md rule 13's shape), and is not a domain split;
- child QML components needed 462 call sites rewritten, new qmllint
  suppressions, every key-mutation patch on `Service.qml` regenerated, and
  `release.py`'s runtime reader taught to see sibling types.

The domain split's own fallback was taken: classic JavaScript
code-behinds, functions moved byte for byte, every call site left as it
was.

## The layout

| file | bytes | functions | what it holds |
|---|---|---|---|
| `Service.qml` | 233,196 | 47 of its own, 162 forwarders | every property, signal, change handler and object; the state machine; the functions listed below; one import line per code-behind |
| `Service-pip.js` | 20,539 | 24 | picture in picture: the `p` key and its verb, the window and monitor reads, the step plan, the peek, the probe |
| `Service-player.js` | 112,935 | 55 | the detached player: play, stop, zap, the control verbs and their results, the probe and adoption, the socket observer and its lines, the failure notices |
| `Service-rewind.js` | 9,410 | 17 | live rewind: the seek queue and its readout, the track requests, and `togglePause` |
| `Service-sources.js` | 90,982 | 66 | sources: switching, probing, reconcile and adoption, cache jobs, the playlist and guide runs, the bar entry writer, logos, dead-channel marks |

**[2026-11-25, D-REL-16, lane-l3a: the bytes and counts re-read on the l3stamp branch. Each code-behind's first function is now its build stamp, and `Service.qml` carries their four forwarders beside its own `buildStamp`; see "Adding a code-behind".]**

Each code-behind is mode 100644 and on `ALLOWLIST` in `scripts/release.py`
(47 files on this tree); `release.py check` reads 47 files and 26 runtime
sources, the largest now `Guide.qml` at 310,448 bytes.

**What stays on the root, and why.**
- Everything that is not a function: properties, signals, change handlers
  and objects (the FileViews, Processes, Timers, the socket's Component, the
  IpcHandler). A code-behind holds functions and nothing else; the readers
  refuse any other line in one (`stray`, below).
- 44 functions the move never named: the state machine and the state file's
  functions (`startStateInit` through `settleEntryFlush`, and
  `requestStateMode` through `tellStateSaveRefused`), `notify` and its three
  helpers, `runHelper`, `str`, `hostForRecord`, `resultField`,
  `probeRecord`, `withKey`, `withoutKey`, the favourite, hidden-group,
  saved-search and recents editors, `refresh`, `nowPlayingSummary`,
  `statusSummary` and `recheckBuild`. The 16 key-mutation patches that edit
  `Service.qml` (`scripts/dev-harness/spikes/key-mutations/`) all land in
  these functions and in object handlers (C4's scan), so they apply
  unchanged.
- `applyOrder` and `tuneByNumber`, by the lead's call (c): the chno
  mutations `flip-refetches.patch` and `unknown-plays.patch` take their
  context from them. A scratch cut that moved them too left 28 of the 30
  mutation patches applying, those two refused (C4, call (m)). The rule C4
  was cut to: a function a patch's hunk reaches, its three lines of context
  included, stays on the root, or the move regenerates that patch in the
  same commit, red first.
- `persistActiveLater`, by D-REL-15: a function that must outlive its call
  is made on the root (below).

## How a code-behind runs

`Service.qml` imports each one by a line after the model's import, in name
order:

```
import "Model.mjs" as Model
import "Service-pip.js" as ServicePip
import "Service-player.js" as ServicePlayer
import "Service-rewind.js" as ServiceRewind
import "Service-sources.js" as ServiceSources
```

A code-behind is classic JavaScript with no `.pragma library` and no
`.import` line: a non-library script, which the QML engine evaluates in the
scope of the component that imports it. That is the host kit's own pattern:
the host's `shell.qml` imports `services/AuthServiceStore.js` the same way,
and that file's own first comment says why it is not `.pragma library`,
because each importing component gets a private instance of it (read in
`/usr/share/omarchy/shell`, Omarchy 4.5.0). What such a file reaches was
measured, not assumed:
- by the design's judge, in plain qml 6.12 under gdb (2026-11-21): the
  root, its properties read bare, its ids, the `Model` import, a namespaced
  QML import, root methods, property writes, signals and its own sibling
  functions, with `Qt.callLater` deduplicating through a forwarder;
- by Part A (2026-11-22), which loaded a four-code-behind prototype of
  9ed04be the host's way, under the host's `shell.qml` header with and
  without the load patch's pragma, in a nested headless cage on a private
  bus: 0 warnings from the plugin's files and 0 JavaScript errors; moved
  functions ran at start-up with Quickshell objects in reach
  (`Quickshell.env`, `Quickshell.processId`), `Commons` reached from a
  code-behind, and the code-behinds were still alive in
  `Component.onDestruction`; key-scenario.sh live read 141 passed, 0 failed
  on the base and on the prototype, name for name;
- by C3's and C4's live proofs, in nested headless cages under
  `scripts/dev-harness/private-bus.sh`, the release step's way:
  rewind-scenario's cage arm 113 passed, 0 failed (R15 a named skip) and
  key-scenario.sh live 141 of 141 on each move, and pip-scenario live 84 of
  84 on C4's, each PASS list its parent's name for name. One-decision
  mutants made inside the code-behinds reddened in the live run the checks
  they had reddened before the move: in `Service-rewind.js`,
  `applySeekPlan`'s readout clear (C3) R9's two and `togglePause`'s flip
  (C4) R10's and R11's; in `Service-player.js`, `play()` without its
  `clearRewind` R9's two; in `Service-pip.js`, `pipApplyPeek` without its
  `pipOn` write P11's two. So the live shell runs those three.
  `Service-sources.js`'s mutants were node ones (`clearSourceData` without
  its `logoHave` clear, `removeSource` without its cache removal), red on
  the checks they reddened before.

**The host's load patch.** The host's `shell.qml` opens with `//@ pragma
OmarchyLoadPatch`, which makes Omarchy's build of Quickshell rewrite a
plain `import QtQuick` to `import QtQuick 6.11` in the QML files it scans
and serve the rewritten text through its URL interceptor
(`docs/OMARCHY-PLUGIN-CONTRACT.md`, "The host's load patch", D-HOST-9).
Part A measured what it serves for this layout: under the pragma, the three
QML entry points only, compiled as `qs:///...`; the four code-behinds
compile from `file://`, as `Model.mjs` and `model/*.mjs` do. A code-behind
has no imports of its own and runs under `Service.qml`'s, which the patch
pins, so every guard judges a code-behind under `Service.qml`'s imports
(`release.py`'s `shipped_code`, below), and the qt revision guard
(D-HOST-10) holds its Qt types and members to the pin as it holds the
QML's.

**The forwarder.** Each moved function leaves one line at its old place,
at the root's two-space indent:

```
  function pipConfig() { return ServicePip.pipConfig() }
  function adoptActive(playlist, epg, plan) { return ServiceSources.adoptActive(playlist, epg, plan) }
```

The call repeats the header's argument list, the arguments are plain names
(no default, no pattern: repeated in a call they would be an assignment or
an object, not the value passed), and they are the moved function's own.
The root keeps the member, so every caller -- the guide, the bar, the IPC
verbs, the host, `root.X(...)` inside the service and inside a code-behind
-- calls it as before, and `Qt.callLater(root.X)` folds through the
forwarder as it folded the function. The function's body, with the
contiguous `//` lines directly above its header, is in the code-behind at
the same two-space indent; a comment block separated from the header by a
blank line is not the function's and does not move with it.

**The inline view.** `Service.qml` with each import line of a code-behind
dropped and each forwarder line replaced by its function's text from the
code-behind is the one-file `Service.qml` a move was cut from, byte for
byte, plus whatever was edited since. Every text pin on a function reads
this view, so moving a function moves no pin; `--verify` compares it;
qmllint lints it. `python3 scripts/split-service.py --inline` prints it.
It drops a code-behind's own header and the loose `//` comments between
its functions.

## The one list, and its readers

The import lines in `Service.qml` are the list of code-behinds. Nothing
else holds one (the lead's call (e)) **[2026-11-24, lane-settle-c5d: that is, no tool or reader keeps a list of its own: `ALLOWLIST`, test_release.py's `must_ship`, test_service_files.py's `CODE_BEHINDS`, qa-lib-test.sh's file list and CLAUDE.md, which "Adding a code-behind" below has you update, do hold one, and `ALLOWLIST` and those pins are checked against the import lines (`release.py check` refuses an import off the allowlist and an allowlisted file nothing imports)]**; everything that needs the service's
files or its text asks a reader:
- `scripts/service_files.py` (python): `service_files`, `service_names`,
  `service_text` (the view), and for the gate `inline_origins` and
  `service_view` (each view line's file and line). Its command line is
  `service_files.py names|files|text <plugin root or Service.qml>`.
- `tests/service-files.js` (node): `serviceFiles`, `serviceNames`,
  `serviceText`, and `serviceSet`, the file set the node harness boots
  (`{ service, files }`). The two readers agree byte for byte: one shared
  fixture, `tests/fixtures/service-split/` (a `Service.qml`, one
  code-behind `Service-demo.js`, its view `inline.txt`, and 51 cases in
  `cases.json`), runs in both, and each engine's tests run the other's
  command line over this tree and the fixture. Both split lines at "\n"
  only, keep a "\r" as text, and refuse bytes that are not UTF-8.
- `qa_service_files` and `qa_service_text` in `scripts/qa-lib.sh` ask the
  python reader and print nothing, exit 1, on a refusal, so a seam counted
  over the service is never a count over nothing. key-scenario's and
  rewind-scenario's slow trees copy the files `qa_service_files` names.
- `scripts/release.py`: `check()` follows `Service.qml`'s imports from the
  three entry points, so a code-behind missing from `ALLOWLIST` is red, and
  so is one listed that nothing imports; `code_behinds_of` and
  `shipped_code` hand each code-behind, with `Service.qml` as its importer,
  to the nine guards of the shipped code (model members, model regex, trim
  shapes, README notices, theme names, colour literals, metric literals, Qt
  revisions, text format). `shipped_code` raises for an `ALLOWLIST` `.js`
  that is no code-behind `Service.qml` declares, so a script no guard would
  read fails every guard closed.
- `tests/service-harness.js`'s `bootService`, `scripts/split-service.py`
  and `scripts/qmllint-count.py --service`, each below.

The dev harness's own shell (`scripts/dev-harness/shell.qml`, started by
`run.sh`) loads `Service.qml` in place over `file://` and the engine
resolves its code-behinds itself: Part A's 78 harness loads of the
prototype logged no line naming a code-behind.

A tree whose `Service.qml` declares nothing reads as `[Service.qml]` and its
own text, and a tree from before D-REL-5 keeps `import "Model.js" as Model`
as the model's import rather than a code-behind (F-HARNESS-123), so every
`--baseline` export of an older tree reads as it did.

## What `split-service.py --check` refuses

The gate's "service split guard" runs `scripts/split-service.py --check`
over the tree and then over its own 34 cases
(`tests/fixtures/service-split/check-cases.json`), so the step goes red when
the judge stops judging. On this tree it reads 5 files, 4 code-behinds, 47
root functions, 162 forwarders and 2,268 root member sites, 34 of 34 cases;
`scripts/check.sh` floors the sites at 2,200 and the cases at 34. Every
refusal is one line naming its kind.

First, whatever the readers refuse, by the readers' kinds:

| kind | refused | what it keeps true |
|---|---|---|
| `declaration` | a line importing a `.js`, in either quote, that is not exactly `import "<file>.js" as <Qualifier>`, or whose file and qualifier are not `Service-<domain>.js` and `Service<Domain>` (the domain lower-case letters and digits) | every reader sees every code-behind; no spelling drops one in silence |
| `module` | an ES-module import that is not exactly `import "Model.mjs" as Model` | a module's forwarders would stay root text and its body unread |
| `declared-twice` | a file or a qualifier declared twice | one file, one qualifier |
| `missing` | `Service.qml` or a declared code-behind is not there | a copy of the tree that leaves a code-behind behind is a service that cannot load |
| `encoding` | a file that is not UTF-8 | the readers read what the engine reads, never a replacement |
| `function-twice` | a code-behind declaring one function twice | each forwarder names one function |
| `unbalanced` | a code-behind function with no closing brace | every function has an end the view can cut at |
| `stray` | a code-behind line outside every function that is neither blank nor a `//` comment (a statement, `.pragma`, `.import`, a function at another indent, `function F (`); text after a function's closing brace on its line; a line terminator JavaScript reads and the readers do not (a CR not before an LF, U+2028, U+2029) | the view holds every line the engine runs; nothing runs at import, outside every forwarder |
| `not-exact` | a forwarder-shaped line for a declared qualifier that is not exactly its function's | a forwarder passes what it was given, to the function of its own name |
| `no-function` | a forwarder to a function its code-behind lacks | every forwarder reaches a body |
| `forwarded-twice` | two forwarders for one function | one forwarder, one old place, per function |
| `unforwarded` | a code-behind function no forwarder names | nothing in a code-behind is unreachable from the root |

Then, on top of their verdict:

| kind | refused | what it keeps true |
|---|---|---|
| `function-twice` | a name declared twice at the root's indent of `Service.qml`, forwarders included (two code-behinds holding one name), or of the view (a header at the root's indent inside another code-behind function, which the engine nests) | one member per name |
| `undeclared` | a `*.js` or `*.mjs` beside `Service.qml` that it does not import as a code-behind, but the model's own (`Model.mjs`; `Model.js` on a tree from before D-REL-5) | a script loaded by a spelling the readers cannot see (`/* c */ import "x.js" as X`) is refused, not loaded unread; a script another QML file imports is refused too, until a split of that file teaches this judge its importer |
| `qualifier` | a code-behind's qualifier named anywhere but its forwarders and its import | a body calling `ServicePip.F(` past the root is code the view cannot hold, and it would skip the harness's stand-ins for root functions |
| `scope` | `this` or `arguments` in a code-behind | the forwarder calls the function on the code-behind and passes only the names it lists, so both read otherwise than on the root |
| `sibling` | a code-behind naming one of its own functions unqualified | whether that is the sibling or the root's forwarder is the engine's scope order, and `Qt.callLater` folds by the function it is handed; say `root.F` |
| `closure` | a function a code-behind makes inside its functions (below) | D-REL-15 |
| `member` | a `root.N`, `root?.N`, `root["N"]` or `root?.["N"]`, in `Service.qml` or a code-behind, where N is no member of the root: its properties and aliases and their change signals, its signals and functions, and what its type (`Item`) and that type's prototypes carry in the installed qmltypes | undefined at run time; qmllint only ever warned about it, and read no moved body until the gate linted the view (F-GATE-29), so this makes it a refusal over every file; an id is no member (`root.<id>` reads undefined) |
| `unjudged` | `root[<expression>]` or `root?.[<expression>]` | no reading of the source can say what it reads |
| `scan` | the tokenizer losing its place in a file | nothing is judged past what was not read |

`--cut` refuses in addition, and writes nothing when it does: `tree` (the
service files differ from REV's, or something is already at a new
code-behind's path), `name` (no root function, a forwarder already, named
twice, arguments that are not plain names, code after the closing brace),
`domain` (not lower-case letters and digits, a domain naming no function,
a qualifier declared for another file, or a `Service.qml` that does not
import the model exactly once for a new import to follow), and
`round-trip` (the cut's view is not REV's); and anything `--check`'s
judge refuses in the result. `--verify` reports a
`git` problem when REV cannot be read.

**The closure rule (D-REL-15).** Measured with qml probes under gdb on
2026-11-24, on a replica of C3's `adoptActive`, which handed
`Qt.callLater` a fresh `function() { root.persistActive(key) }`: with the
Service deleted after the call was scheduled and before it ran, the root's
copy logged `TypeError: Cannot call method 'persistActive' of null` and
the code-behind's copy was a SIGSEGV inside libQt6Qml, with and without
`pragma ComponentBehavior: Bound` and an ES-module import. The shipped text
itself, driven beside a stand-in, read `ReferenceError: root is not
defined`, and the spike's other shapes show what decides between the two:
a closure whose making function read the root first reads that
ReferenceError (shape `oldread`), one whose maker looked nothing up first
crashes, even when an outside holder calls it directly (`heldbare`), and
one connected to an outside object's signal can crash too (`connect`). Which closure crashes cannot be read off the source, so the
guard refuses them all. Allowed:
- the immediate callback of a call to a method named `filter`, `map`,
  `forEach`, `some`, `every`, `find`, `findIndex`, `reduce`,
  `reduceRight`, `sort` or `flatMap`, whose callback runs before the method
  returns (the guard reads the method's name and cannot know its receiver;
  an `async` callback is not allowed);
- a function excused by `// CLOSURE-EXCEPTION: <reason>` on the line it
  starts on or in the unbroken run of `//` lines directly above, the reason
  saying why nothing can call it once its Service is gone (the guard reads
  that a reason is there, not what it says; one inside a string, a
  template, a regular expression or a `/* */` comment is no comment). One
  stands on the tree: `startCacheLayout`'s `onDone` in
  `Service-sources.js`, held only by `root.cacheQueue` and
  `root.cacheJob`.

A function that must outlive its call is made in a root function of
`Service.qml`. `persistActiveLater(key)` is the model: `adoptActive` calls
it, and it does `Qt.callLater(function() { root.persistActive(key) })` on
the root, where a deleted Service makes it log a TypeError, as before the
split. It is not `Qt.callLater(root.persistActive, key)`, because
`Qt.callLater` folds calls of one function before the next turn into one,
with the last call's arguments (measured), so two adoptions in a turn would
persist only the second key. Handing `Qt.callLater` a root method from a
code-behind (`Qt.callLater(root.X)`, seven sites) is fine: after the
deletion it is skipped. Not read by the guard, and not measured:
`Function(...)`, `.bind(...)`, `eval` of a text that makes a function, and
what the shared tokenizer misreads (`of`, `await` or `yield` used as a
variable before a `/`); no code-behind holds any of them. The measurement
is re-runnable from `scripts/dev-harness/spikes/codebehind-calllater/`
(`run.sh`, fifteen shapes in both forms, and `shipped.sh`, every qml under
gdb; `RESULT-2026-11-24.txt`).

## Editing, moving a function, adding a code-behind

**Editing.** Edit a moved function in its code-behind, never its
forwarder. A change to its arguments changes the header there and the
forwarder here together (`not-exact` otherwise). A new function goes where
its domain lives: written in the code-behind with its forwarder added to
`Service.qml`, or written on the root; `--check` holds the pair. Call a
function of the same code-behind as `root.F(...)` (`sibling`). Nothing but
functions goes in a code-behind, and nothing that makes a function that
may outlive its call.

**Moving a function** is a commit of its own, cut by the script from a
clean tree and proved against its parent, never done by hand:

```
python3 scripts/split-service.py --cut --from HEAD --domain <domain> <function>...
python3 scripts/split-service.py --cut --from HEAD --map moves.json   # {"<domain>": ["<function>", ...], ...}
python3 scripts/split-service.py --verify --from-git HEAD
python3 scripts/split-service.py --check
```

`--cut` moves each named root function of REV's `Service.qml`, with the
`//` lines directly above it, to the end of `Service-<domain>.js` (after a
generated header for a new file), leaves its forwarder at its old place,
and declares a new code-behind among the import lines. It verifies before
it writes: the result must pass `--check`'s judge and its view must be
REV's byte for byte; then it runs `--verify` against REV. A function that
makes a closure cannot be moved (`closure`) **[2026-11-24, lane-settle-c5d: one that makes a closure the guard refuses: a synchronous Array method's callback and one a `CLOSURE-EXCEPTION` comment excuses pass, and `startCacheLayout`, whose `onDone` carries such a comment, was moved]**. After the cut:
- `git apply --check` all 30 mutation patches under
  `scripts/dev-harness/spikes/` (18 of them edit `Service.qml`);
  qa-lib-test.sh's "all nineteen key-mutation patches still apply" and "all
  eight chno-mutation patches still apply" are the gate's half. A patch
  that no longer applies means the function stays, or its patch is
  regenerated in the same commit, red first (call (c)).
- The functions append in file order, so a comment that points up or down
  at a function now in another file reads the wrong way. Re-word it in a
  commit of comment lines only, and show it is one: the views with every
  `//` line dropped are equal, and `--verify` is red against the cut and
  green against the re-word (C3's 9967571, C4's 65f5d3d).
- Keep one live mutant inside each code-behind the move makes, red in a
  live scenario (the lead's call at C3's close), and run
  rewind-scenario's cage arm and key-scenario.sh live, as C3 and C4 did.
- Re-measure every count; the records go on the D-REL-14 row and in
  `docs/QA-RESULTS.md`.

**Adding a code-behind** is a `--cut` with a new domain. Beside it, in the
same commit:
- the new file on `ALLOWLIST` in `scripts/release.py`, with
  `tests/test_release.py`'s `must_ship` and its stand-in `Service.qml`
  declaring it (rule 10), as C3 and C4 did;
- the pins that name this tree's files, among them node's "D-REL-14 C4: on
  this tree the service is Service.qml and its four code-behinds" and
  "D-REL-14: the node and python readers agree on this tree",
  `tests/test_service_files.py`'s `CODE_BEHINDS`, and qa-lib-test.sh's
  file list, each seen red both ways (C4 flipped them from three files to
  five);
- CLAUDE.md's list of code-behinds and its allowlist count (the lead's
  file);
- **[2026-11-25, D-REL-16, lane-l3a]** its build stamp, three things,
  which `scripts/build_stamps.py --check` (the gate's "build stamp guard",
  and `release.py check`) is red without:
  - the stamp function, the FIRST function of the new file, directly after
    its header, `  function buildStamp<Domain>() { return "N.N.N" }` with
    the domain as its qualifier spells it (`Service-pip.js`'s is
    `buildStampPip`) and the version of the last cut, the value every other
    file's row in `BUILD_FILES` holds for a file that has not changed
    since. It leads because `--cut` appends a moved function at the end; a
    stamp anywhere but first is `form`, one named for another domain `name`;
  - its forwarder in `Service.qml`, beside the other four under the root's
    own `buildStamp`: `  function buildStampPip() { return
    ServicePip.buildStampPip() }`. The readers allow nothing but functions in
    a code-behind and refuse one no forwarder names (`unforwarded`), and the
    qualifier may be named nowhere else (`qualifier`), so the forwarder is
    the one way the service reads it;
  - its row in `model/build.mjs`'s `BUILD_FILES`: a new runtime file is
    reached by `release.py`'s runtime_files, so the table without its row
    is `table`. The block is the one place a hand edit is the step: add the
    row at the file's place in load order (`build_stamps.py --json` prints
    that order) in the form of the rows around it, with the stamp's value;
    `--cut` refuses a tree `--check` refuses, so it writes values, never a
    missing row.
  The stamp function makes no closure (D-REL-15): it returns a literal.
The readers, the harness and the guards need nothing more: they read the
import lines.

## How qmllint sees the service (F-GATE-29)

qmllint does not follow a script import, and given a code-behind it checks
its syntax alone: a block-scoped `var` and an unknown name draw nothing
(measured on 6.12.0). So the gate lints the view, which is the scope the
moved bodies run in. `scripts/qmllint-count.py --service` builds the view,
stages it as `Service.qml` beside the other entries of `Service.qml`'s
folder (a regular `.qml` and the `qmldir` copied, everything else linked),
lints it, and names each entry at the file and line it stands on, through
`service_files.inline_origins`; check.sh's `gate_qmllint_view` prints the
counts and fails on any error. `Model` members are not judged there:
check-model-members already reads each code-behind under `Service.qml`'s
imports. On this tree:

```
scripts/check.sh --qmllint-file Service.qml   # Service.qml: 0 errors, 9 warning(s) + 134 on Model members
scripts/check.sh --qmllint-view Service.qml   # the view: 0 errors, 46 warning(s) + 387 on Model members
```

The view's 433 entries are what the one-file `Service.qml` read before C3
(bd65241, under the same model); 290 of them are read only through the
view.

## How the node harness runs it

`tests/service-harness.js` compiles the service's own functions and runs
them against fakes of what QML supplies. `bootService` takes the file set
from `serviceSet(where)` (or, as before the split, one text), asks the
readers first, and refuses what they refuse (rule 10: a split the shell
would not load does not boot). Each code-behind's functions are then
compiled in the same scope as the root's, a `with` over one proxy that
resolves the ids, `root`, `Model`, `Qt`, `console`, `Date` and each
qualifier, and otherwise the root's members, into the object its qualifier
names; and
`Service.qml`'s own functions, the forwarders among them, onto the root. So
what runs is the forwarder and the code-behind, as in the shell, and
`STUBBED` and `unstub` act on the root's member, the forwarder. What only
`--check` refuses (a code-behind naming its own function unqualified,
among others) still boots, and reads there as the root's member; the gate's
guard holds that shape, not the harness. Its `Qt.callLater` folds as Qt
6.12.0 was measured to fold (F-HARNESS-130). The boots of the shipping
service in `tests/Model.test.js` and `tests/proto-run.mjs` pass the file
set, and the suite's pins on the service's text read `serviceText`, the
view.

## Updates and hot reloads across a version change (call (d))

The lead's call (d) asked, before the first release that ships a
code-behind, for a hot reload across a version change to be measured in a
nested cage, and for D-REL-9's write order to be measured or answered
above git's default `checkout.workers=1`. lane-reload-d measured both on
2026-11-24 (branch reload-d, merged with this section). Everything below is
that measurement unless it says "read". The rig is
`scripts/dev-harness/spikes/codebehind-reload/` (`run.sh`; its record,
every arm as printed, is `RESULT-2026-11-24.txt` there); the reading is
QA-RESULTS "D-REL-14: call (d), a version change with code-behinds
(lane-reload-d, 2026-11-24)".

**What was run.** The host's own loader, reload, disable and enable code,
cut from its `shell.qml` (Omarchy 4.5.0-3, sha256 pinned) by line range,
byte for byte, with two adaptations named in its output (`firstPartyDir`
points at an empty folder, so no first-party plugin or service starts; the
orphan reaper's `pgrep -f` is `true`) **[2026-11-24, lane-settle-c5d: the reaper's adaptation is in the copied `services/PluginRegistry.qml`, 708-715 (make-root.py's `REAPER`), not in `shell.qml`]**. The folder watcher
(`PluginRegistry.qml` 726-745) and its 150 ms debounce are the host's,
unchanged, and the shell starts the way the live launcher starts it
(`QS_DISABLE_FILE_WATCHER=1`). It ran in one nested headless cage on
`scripts/dev-harness/private-bus.sh`, every quickshell under gdb, on two
roots: a, with the load patch's pragma, and b, without it. The plugin was
installed the way `omarchy-plugin-add` installs it, from a scratch
upstream, and updated by `omarchy-plugin-update`'s own git step run by
argv (`fetch`, then `merge --ff-only FETCH_HEAD`, then validation). Three
builds, each committed onto the last as `release.py` does:

| build | what it is | version |
|---|---|---|
| C0 | 1321aff, `main`: 0.20.0, one `Service.qml` | 0.20.0 |
| C1 | 3200d22's `ALLOWLIST` export by `release.py`'s own `build_tree`: four code-behinds | 0.99.0 |
| C2 | C1 with `Service-player.js`'s `socketAttached` renamed and `Service.qml`'s forwarder calling the new name, so any pair of a C1 file and a C2 file throws on every call, `status` included **[2026-11-24, lane-settle-c5d: only the pair of `Service.qml` and `Service-player.js` throws, one from each build; another mixed pair, C1's `Service-pip.js` beside C2's others, runs and reads as mixed only by its mark]** | 0.99.1 |

C1 and C2 carry an inert mark in `Service.qml`, each code-behind,
`Guide.qml` and `BarWidget.qml` (C0's mark is that it has none), and the
rig reads each running object's QML type name, which a component compiled
again changes **[2026-11-24, lane-settle-c5d: unverified, and not what the verdicts rest on. Across a restart a new text kept its number (Guide_QMLTYPE_121 was C1 before a restart and C2 after) and the same stale text got a new one (Service_QMLTYPE_146 then 148, each holding the cache's C1 `Service.qml`, in the race arms below); within one process no recompile was ever reached. The verdicts are the marks, read by calling into the running objects]**. A deliberately mixed tree reads as mixed (h1, below), so the
all-old readings are not a readout that cannot go red.

**After `omarchy plugin update`, with the shell running.** C0 to C1 and C1
to C2, both roots: the old build kept running, whole, through the watcher's
reload (which began 150.6-154.5 ms after git's last write) and then
through `rescanPlugins`.
- The service is the same object: it is keepLoaded, so the host's
  `unloadPluginServices` carried it over and `_syncServices` handed it the
  new manifest.
- The guide and the bar are new items, made from the cached old
  components: the same `_QMLTYPE_` numbers as before the update, the old
  marks.
- Nothing mixed. Across C1 to C2 the service ran C1's `Service.qml` and C1's
  four code-behinds, and no TypeError appeared although C2's forwarder on
  disk names a function C1's file lacks. The plugin's files logged nothing
  at either reload, in either root: no error, no `Script ... unavailable`.
- The model stayed old too: `status`'s `build.running`, which is
  `Model.PLUGIN_VERSION`, read the old version.
- The plugin says so once the guide opens (D-HOST-1): before that, `status`
  read the running and on-disk versions alike, because the replaced
  manifest's watch never fires (D-HOST-2); at the open `recheckBuild` read
  the new manifest, `stale` became true, and the footer read "Updated ·
  restart the shell to see the new version".
- After a restart the new build ran everywhere, clean: ready with three
  channels, the starred channel and the bar entry's `refreshMinutes` 120
  kept.

That is what D-REL-6 measured on 2026-10-12 for a one-file service, now
measured with code-behinds on Quickshell 0.3.2: an update does not reload
the plugin's code, and the code-behinds change nothing about that.

**A disable and an enable, without a restart.** After each update the rig
disabled and enabled the plugin the host's way (`setPluginEnabled` false,
then `enablePlugin`, the calls `omarchy-plugin-disable` and `-enable`
make, read in them),
twice, in both roots. Each new service instance was the OLD build's type
and text, `Service.qml` and every code-behind together (C0's type with no
marks; C1's type with all five marks C1), ready with three channels, with
no error and no crash. Before the second enable the rig collected garbage,
loaded 8,000 components the type loader had never seen, and made and let
go a control component of its own, then rewrote the control's file: the
enable still made the old type, and the control came back with its first
text. So no path the rig drove released a component once it was loaded,
and D-REL-6's mixed shape (a cached file beside a fresh one) was not
reached by an update, a reload or a toggle. Why the engine keeps the
component was not read in the Qt sources. Two things beside it:
- A Service with live code-behinds was destroyed by each disable (four
  times) and at every C1 or C2 shell's exit, with no fault. Whether a
  deferred call was pending at that moment was not observed, so D-REL-15's
  crash condition stays unmeasured (below).
- The host's disable removes the bar entry and the enable puts back only
  its id, so `refreshMinutes` went from 120 to the default 360 (D-QA-17,
  known); the playlist survived because start-up had moved it into
  `state.json`.

**D-REL-9's write order.** The update's merge was timed by an inotify watch
on the plugins folder, on the clock the rig's events use.

| `checkout.workers` | runs | the closes | writes |
|---|---|---|---|
| 1, git's default | 14 (8 updates, 6 half-tree completions) | index order every time: `BarWidget.qml`, `Guide.qml`, `Service-pip.js`, `Service-player.js`, `Service-rewind.js`, `Service-sources.js`, `Service.qml`, `manifest.json`, `model/build.mjs` (of the files named); every code-behind closed before `Service.qml` was created | 5.3-5.8 ms inside a 38-47 ms merge, no gap above 1.4 ms |
| 4, by `-c checkout.workers=4 -c checkout.thresholdForParallelism=1` on the merge | 2 | interleaved; `Service.qml` was created before `Service-rewind.js` closed, and in one run before `Service-player.js` too | 7.4-8.4 ms, gaps up to 3.9 ms |
| 4, by the same two settings in the decoy HOME's `~/.gitconfig` | 1 | not index order (`manifest.json` and `model/build.mjs` before `Service-player.js`), so the user's setting reached the update's git; `Service.qml` happened to close last | 10.7 ms, a gap of 5.4 ms |

**[2026-11-24, lane-settle-c5d: "created" in the four-worker row is a CREATE, a file still being written. With the unlinks read too (three more four-worker runs, `-c` on both roots and `~/.gitconfig` on root a, and the recheck's three), git's main process unlinks every changed file before any worker creates one, so `Service.qml` is absent for 5.1-5.8 ms (8.2 ms in one race), and h4's shape, below, occurred in 3 of the 15 four-worker runs lane-settle-c5d measured, for 0.1-1.1 ms each (`Service.qml` closed before `Service-player.js` or `Service-rewind.js` was created or closed), and in none of the six before. Four workers' longer window is h0, below, at a length 0.20.0's one-file updates also have. At one worker each file is unlinked just before it is written, so h0 there is under 0.1 ms. RESULT-2026-11-24-race.txt; QA-RESULTS "D-REL-14: call (d), settled (lane-settle-c5d, 2026-11-24)"]** **[2026-11-24, lane-fix-c5d: under a concurrent start the absence is longer: 5.5-14.6 ms in the 19 four-worker races of recheck-c5ds-measure's run logs (14.6 in its M1, where git and the starting shell shared the two cores), so 5.1-14.6 ms with this lane's; and a duration under about 2 ms, h4's 0.1-1.1 ms and h0's under 0.1 ms among them, is a difference of watch.py's read stamps, not a kernel time (watch.py's docstring)]**

Read in `omarchy-plugin-update` and `omarchy-plugin-add`: they pass git no
`-c` option, export only `GIT_TERMINAL_PROMPT` and `GIT_SSH_COMMAND`, and
leave HOME, XDG_CONFIG_HOME and every `GIT_CONFIG_*` alone, so a user's git
configuration sets the worker count (`~/.gitconfig` measured above;
`$XDG_CONFIG_HOME/git/config` and `/etc/gitconfig` by git's own rules,
not run). The update writes in place a second
time on a failed validation, its rollback `git reset --hard ORIG_HEAD`
(read, not run). `plugin add` has no such window: it clones into a hidden
staging folder, which the watcher ignores, and moves it into place (read).

What reads the window: no reload the host makes. In all 17 writes the
watcher's events arrived during the writes, each restarting the 150 ms
debounce, `reloadPlugins` began 150.6-154.5 ms after the last write, and
every reload served cached components; the only plugin file a reload reads
is `manifest.json`, read by the scan after the last write. A load the cache
does not serve does read it: a shell starting or relaunched, or the plugin
loaded for the first time, inside git's 5-11 ms of writes. How often that
happens was not measured. **[2026-11-24, lane-settle-c5d: the window is not git's span alone but the time between the shell's reads of the files, measured by timing those reads at a cold start (both roots, every arm since): on root a, the host's, the load patch's scanner reads `Service.qml` at the first load and the engine reads the code-behinds about 0.66 s later (the first 658.7-696.8 ms and the last 668.8-707.1 ms after it in five arms of this lane's, the first 664 ms after it in the recheck's), so an update whose writes land anywhere in that interval mixes them, at one worker or four; on root b the engine reads `Service.qml` and then the code-behinds, the first 4.7-4.8 ms and the last 15.3-15.5 ms after it (three arms), and holds `Service.qml`'s text 75-106 ms before it saves the compiled unit, which is the cache's window below]** **[2026-11-24, lane-fix-c5d: in four arms, not five: a-12-r, a-12-w-c4, a-12-w-g4 and a-12-h1, as RESULT-2026-11-24-race.txt's Q8 and QA-RESULTS Q8's table list them]** What it then runs, measured on half trees made
by hand in the shapes the order passes through, each started cold and then
completed under the live watcher, rescanned, disabled and enabled, and
restarted:

| half tree | the window it stands for | cold start | until the restart |
|---|---|---|---|
| h1: C2's code-behinds beside C1's `Service.qml` | one worker, the code-behinds written and `Service.qml` not yet **[2026-11-24, lane-settle-c5d: and on root a any worker count, across the 0.66 s above. The hand-made tree took only the four code-behinds, where one worker has by then also written `BarWidget.qml`, `Guide.qml` and `README.md`; the rig's h1 now takes every changed file before `Service.qml` in byte order, and its re-run on both roots gave the same mix beside C2's guide and bar]** | a MIX, C1's `Service.qml` with C2's code-behinds; `status` throws "TypeError: Property 'socketAttached' of object [object Object] is not a function" | the same mixed type at every reload, rescan and enable; nothing told the user before the tree completed, and after it the footer read "Updated" |
| h4: C2's `Service.qml`, `Service-player.js` not there | four workers **[2026-11-24, lane-settle-c5d: seen: the shape occurred in 3 of the 15 four-worker runs lane-settle-c5d measured, for 0.1-1.1 ms each (`Service.qml` closed before `Service-player.js` or `Service-rewind.js` was created or closed), and in none of the six before]** | no service: "Script file://.../Service-player.js unavailable"; the guide and the bar load without it, the footer empty | the host retried at every scan and at the enable, and each retry failed with the same line |
| a-01-h4: C1's `Service.qml`, no code-behind yet | the first code-behind release at four workers **[2026-11-24, lane-settle-c5d: as h4, at the first code-behind release's four new files; not run as a race]** | no service: "Script file://.../Service-pip.js unavailable" | as h4 |
| h0: `Service.qml` unlinked | any worker count; 0.20.0's own updates have it **[2026-11-24, lane-settle-c5d: under 0.1 ms at one worker; 5.1-8.2 ms at four, every changed file unlinked first]** **[2026-11-24, lane-fix-c5d: 5.1-14.6 ms at four with recheck-c5ds-measure's 19 races]** | no service: "Service.qml: No such file or directory" | as h4 |

Every retry got back the component the engine kept from the first load,
failed or mixed, and only a restart recovered. So the stickiness is not new
(h0 is 0.20.0's), but code-behinds widen what a cold load can read: h1 at
one worker for any release that changes a function across `Service.qml`
and a code-behind, and h4 at more. Filed as D-REL-16. **[2026-11-24, lane-settle-c5d: "only a restart recovered" holds for these hand-made trees, which were complete on disk before the shell compiled them. In a real race on root b the restart does not recover, because Qt's disk cache keeps the old code under the new file's checksum ("Real races", below); and code-behinds widen the window mostly by h1, at any worker count on root a, and by a code-behind's own unlink at four workers (h0's shape for that file), far more than by h4's moment of 0.1-1.1 ms]** **[2026-11-24, lane-fix-c5d: on either root, not root b alone: Service.qml's unit on root b, and on root a a code-behind's, which 7 of lane-settle-c5d's 28 root-a races and 3 of recheck-c5ds-measure's 22 fired at `Service.qml` left poisoned past two restarts ("Real races", below)]** Under the load
patch's pragma `Service.qml` compiles as `qs://` and its code-behinds as
`file://`, and the patch's scanner follows a code-behind's import and logs
a missing one as "Ignoring unresolvable import", so on root a a missing
code-behind is reported twice.

**Real races (lane-settle-c5d, 2026-11-24).** The half trees above are
complete on disk before the shell compiles them, so they cannot show what
a write landing DURING the compile does. The rig's race arm (`x`) runs the
update's own `merge --ff-only` into a cold start, fired at the starting
shell's first open of a chosen file and a chosen delay after it, and reads
the marks and Qt's disk cache after the race, after two restarts and after
a recovery; `cache.py` reads each cache file's checksum and code against
the builds' texts. Its record is `RESULT-2026-11-24-race.txt` beside the
rig, and its reading QA-RESULTS "D-REL-14: call (d), settled (lane-settle-c5d, 2026-11-24)".

What the cache does, read in Qt 6.12's private headers and measured: a
unit compiled at run time is saved in content-hash mode, with the checksum
of the source as it reads when the unit is SAVED (`qv4compileddata_p.h`
1220-1231, 1635-1647), and a later start accepts the unit while that
checksum matches. So a write that lands between the engine's read of a
file and the save of its unit leaves the old code under the new file's
checksum, and every later start runs it. The cache is
`$XDG_CACHE_HOME/quickshell/qmlcache` (`~/.cache/quickshell/qmlcache` by
default), one file per source. On root b every QML file and script is
cached, and `Service.qml`'s unit is saved 75-106 ms after its read; on root
a the load patch serves the QML files through `qs:` from its scanner's
text and no unit of theirs is written, while the code-behinds and the
model are cached as on root b, each unit saved 0.2-5 ms after its read. **[2026-11-24, lane-fix-c5d: in a quiet cold start (a-12-r). Under a concurrent merge on this 2-core machine the poisoned units' read-to-save gap was about 9-10 ms **[2026-11-25, D-DOC-38: a lower bound, about 10 ms or more, read off the two poisoned units whose opens were logged]**: recheck-c5ds-measure's A641-c4 `Service-player.js`, the engine's last open before git's unlink +668.9 ms after the trigger, the unlink +669.0, git's close +676.6, the save +678.0 (cache.py's whole milliseconds; +678.4 as that recheck read the mtime); and the settle's S1-633 `Service-player.js` as that recheck read its record, open +672.4, unlink +677.7, save +682.0. Unpoisoned races reached 6-8 ms (its A637 and A652-c4)]**

| root | races | after two restarts | recovered by |
|---|---|---|---|
| b, merge at `Service.qml`'s first read, C1 to C2 | 2 here, 2 in the recheck | all 4 poisoned `Service.qml`: C1's code under C2's checksum, beside C2's code-behinds; `status` throws the TypeError at every start | the cache folder removed and a restart (1); the C3 update and a restart (1) |
| b, the same, C0 to C1 (the first code-behind release) | 2 here, 1 in the recheck | all 3 poisoned `Service.qml`: C0's code beside C1's model; `build.running` equals `onDisk`, `stale` is false, nothing shown | the C2 update and a restart (1); the cache folder removed and a restart (1) |
| a, merge 615-665 ms after the scanner's read of `Service.qml`, one worker and four | 24 | 5 poisoned a code-behind (`Service-player.js` 4 times, the TypeError at every start; `Service-sources.js` once, silent); 3 loaded no service at the race (a code-behind read while git had it unlinked) and 16 ran a mix or the old build, each recovered by the restart | the cache folder removed and a restart (5 of 5) |
| a, the same, with a later update for recovery | 4 | 2 poisoned (`Service-rewind.js`, `Service-sources.js`) | the C3 update and a restart (2 of 2) |

So on today's host a cold start that overlaps an update can leave a mix
that survives restarts, and D-REL-16 is P2. The window on root a is the
0.66 s between the scanner's read of `Service.qml` and the engine's reads
of the code-behinds, at one worker or four; what poisons a unit is a
code-behind's write in the 0.2-5 ms between its read and its save. **[2026-11-24, lane-fix-c5d: 0.2-5 ms in a quiet cold start and up to about 10 ms under a concurrent merge (above)]** **[2026-11-25, D-DOC-38: a lower bound, about 10 ms or more, read off the two poisoned units whose opens were logged]** The
model's units are saved the same way (not raced: they are read 650 ms
before the code-behinds, nearer the plugin's first open than a merge fired
from the plugin folder can reach), so a release that changes a model part
is exposed on either root, and has been since the model was split
(D-REL-5, 0.13.6). **[2026-11-24, lane-fix-c5d: raced since, and a merge does reach the model. recheck-c5ds-measure fired the race arm on root a at the starting shell's first open of `manifest.json`, the first plugin file it opens (`RIG_RACE_FILE=manifest.json RIG_RACE_DELAY_MS=0`, its runs M1 to M5, 10 races). At four workers 2 of 5 (M1, M2) unlinked `model/build.mjs` before the engine loaded the model, and the log reads "Script file://<plugin>/model/build.mjs unavailable", then "service plugin load failed ... Model.mjs unavailable", "Plugin widget io.github.rmcdavid.iptv failed: qs://<plugin>/BarWidget.qml:5:1: Script file://<plugin>/Model.mjs unavailable" and "Guide.qml[7:1]: Script file://<plugin>/Model.mjs unavailable": no bar, no guide and no service until a restart, which recovered all three; no unit was saved for build.mjs, so nothing was poisoned. At one worker 5 of 5, and at four the other 3, the merge finished before the code-behinds were read and h1's mix ran (C1's `Service.qml` with C2's code-behinds, `status` throwing), recovered by the restart; build.mjs's unit was saved 2.5-4 ms before git unlinked it **[2026-11-25, D-DOC-38: 2.4-16.3 ms over the 8 races that saved a unit (one worker M1 2.5, M2 16.3, M3 7.0, M4 3.6, M5 7.6; four workers M3-c4 4.4, M4-c4 5.4, M5-c4 2.4), each a difference across the rig's two clocks, so by as little as about 2.5 ms (recheck-c5dt-records)]** (M1: saved +31.0, unlinked +33.5 ms after the trigger), so a poisoned MODEL unit was missed by that margin, not reached. On root b with the same trigger (its BM, 2 races) `BarWidget.qml`'s unit was poisoned 2 of 2 (read +1.7 to +2.1, git's close +27.8 to +44.0, saved +127 to +129 ms; C1's code under C2's checksum ed680d80..), a silent mix of C1's bar beside C2's service and guide after two restarts. The no-plugin outcome is not the code-behinds': every release rewrites `model/build.mjs` (its `PLUGIN_VERSION`), so 0.20.0's own four-worker updates have it too **[2026-11-25, D-DOC-38: inferred from the mechanism, not raced on 0.20.0]**. And the exposure does not date from the split: at v0.13.5 `Service.qml` read `import "Model.js" as Model`, a script cached the same way. It holds since at least the Qt 6.12 host update (2026-10-31); whether Qt before 6.12 validated a unit compiled at run time by time stamp or by content was not read]**

**What a user must do.** Restart the shell after `omarchy plugin update`
(`omarchy-restart-shell`), as the README's Updating paragraph and every
release's notes already ask. Until then the old build runs, whole and
unmixed, and the guide's footer says "Updated" once it opens. A disable and
an enable is no substitute: it makes the old build's service again. If the
shell started, restarted or first loaded the plugin while the update was
writing it (D-REL-16), it may run no service, or a mixed pair whose calls
throw, until it is restarted once more after the update has finished.
With no service the guide opens with an empty footer; with a mixed pair
nothing the plugin shows says so before the update finishes. The
code-behinds ask nothing of the user that 0.20.0 did not: the same
restart, and the same second restart after a load inside the window,
whose shapes they widen. **[2026-11-24, lane-settle-c5d: three corrections. Not every release's notes ask: of CHANGELOG.md's 46 sections 13 do, 0.13.4 to 0.14.2 and 0.15.0 to 0.20.0 (0.14.3's do not, 0.13.3's say no restart is needed, and none from 0.1.0 to 0.13.2 asks). A second restart is not always enough: where a race poisoned Qt's disk cache ("Real races", above), every start runs the mix again, on root b for `Service.qml` and on root a, today's host, for a code-behind. What recovers is removing the cache folder, `$XDG_CACHE_HOME/quickshell/qmlcache` (`~/.cache/quickshell/qmlcache` by default), and restarting, or a later update that rewrites the poisoned file; the README's Troubleshooting says so, and its Updating paragraph says the guide and the bar stay loaded too and that a disable and an enable loads nothing new. And with a mixed pair no build reading tells the user, so the lead's call L3, a build stamp in every shipped file the service, the guide and the bar load, read with D-HOST-1's, is the next step before the first release that ships a code-behind]** **[2026-11-24, lane-fix-c5d: two more. A shell that starts while a four-worker update has the model unlinked can load nothing of the plugin: no bar entry, no guide, no service (recheck-c5ds-measure's M1 and M2, above); a restart recovers it, and the README's Troubleshooting names a plugin missing from the bar. And, the lead's call under the owner's standing authority of 2026-11-09, L3 gains two sentences: a stale reading right after a fresh start can only mean a race or a poisoned cache, so the stamp's notice names the cache removal (the README's Troubleshooting step) when it reads stale at start-up, rather than only asking for a restart, which cannot clear a poisoned unit; and the stamp cannot speak in the four-worker model outcome, where no bar, guide or service loads, so only the README reaches that user. The first release that ships a code-behind carries a release-notes line naming the cache removal, an item for that cut (D-REL-16)]**

**[2026-11-25, D-REL-16's L3, on the l3stamp branch (lane-l3a, lane-l3b): the plugin now says which of these a user is in, below.]** After an update under a running shell the guide's footer and the bar's tooltip say `Updated`, `restart the shell to see the new version`, from the update's own rescan (D-HOST-16) rather than once the guide opens. A shell that loaded files of two builds, or a build already behind the disk at its first reading, says `Loaded mid-update`, with the QML cache's removal: `rm -rf ~/.cache/quickshell/qmlcache && omarchy-restart-shell` (the README's Troubleshooting step; the tooltip names the folder from `$QML_DISK_CACHE_PATH` or an absolute `$XDG_CACHE_HOME` when set). With no service the guide's body and the bar's tooltip add the cache step after the restart, and the bar's accessible name says `IPTV, service not loaded` (D-A11Y-14). With no plugin loaded nothing of the plugin can speak: the README and the cut's notes are all that reach that user. UNVERIFIED until the caged arms (QA-RESULTS "D-REL-16, L3's reading and words (lane-l3b, 2026-11-25)").

**What it changed.** No shipped code: the ordinary update path showed no
failure, so no fix was made; whether that meets call (d) is the lead's
call (lane-reload-d proposed that it does). The rig and its record are the
measurement's only files. Filed: D-REL-16 and F-HARNESS-131 (the heavy
lock's descriptor inherited by a process that outlived a run, found while
building the rig, whose own runs use `flock -o`). D-REL-6, D-REL-9 and
D-REL-14 carry dated brackets. The join brought two texts to the
measurement: `Service.qml`'s header comment no longer gives keepLoaded as
the whole reason a restart is needed, and the README's development line
**[2026-11-24, lane-settle-c5d: a bullet of the README's Troubleshooting list, beside which this lane added one on a raced cache; the "## Development" section was not touched]**
names the guide, the bar and the model beside the service, since none of
them reloads either. D-REL-16's options and their costs are in
lane-reload-d's result, for the lead. **[2026-11-24, lane-settle-c5d: the lead's calls on them, under the owner's standing authority of 2026-11-09: call (d) is met for the ordinary update path (L1); D-REL-16 is rewritten from the real races and is P2 (L2); the build stamp is the next step, a release-notes line is the cut's, and upstream reports wait on the owner (L3). No shipped code changed here either: comment lines in Service.qml and Service-rewind.js, the README and the documents]**

## What the build stamps tell (D-REL-16, L3)

Every runtime file carries a build stamp (ARCHITECTURE.md (dev branch)
section 9, "Build stamps"), and the service reads them (section 9, "The
reading"). For a code-behind that means three things beside what
"Adding a code-behind" above lists.

- **What the service collects.** `ownBuildStamps()` reads Service.qml's own
  stamp, each code-behind's `buildStamp<Domain>()` through its forwarder,
  and `Model.BUILD_STAMP_AGGREGATOR`, each in try/catch: a code-behind from
  before the stamps, or one whose forwarder throws, reads `"?"`, which is no
  build's row, so the mix reads "cache". A new code-behind's stamp must be
  added there too, or its file is never judged; the node suite boots one
  file set per code-behind the service declares with that file's stamp of
  another build and goes red for any it does not read (tests/Model.test.js,
  "D-REL-16: a Service-X.js of another build ...").
- **What answers in a mix.** `buildReply()` and the IPC `build` verb read
  the `buildCheck` binding and nothing that throws, so they answer in the
  measured TypeError mix (C2's Service.qml beside C1's Service-player.js),
  where `status` throws at `socketAttached()`. Both are root functions of
  Service.qml, as D-REL-15 asks of anything that must outlive a call.
- **What the reload rig reads.** candidates.py's `bump()` cuts every build's
  stamps against the build it updates from (lane-l3a), rig.qml.in's `marks`
  carries the `build` reply and the views' notice, tooltip and name, and
  analyze.py prints them beside the marks and says whether the stamps agree
  with them (`agree` lines; a notice that does not fit the marks is a
  finding). `RIG_RECOVER=clear-live` removes the cache folder while the
  shell runs and then restarts, the README's order. None of it has run in a
  cage yet: the arms are the display lane's.

## History

- **2026-11-21.** D-REL-14 filed at 444,947 bytes; the design panel and the
  plan above, with a growth hold of about 5 KB per item until the first
  move merged.
- **2026-11-22, C1, the readers** (lane 1, branch relsplit-1, merged in
  3492785). Part A measured the host's load of a four-code-behind prototype
  and answered go (the lead's call (a): the layout is classic-JS
  code-behinds; child components are not pursued). The readers and their
  shared fixture: a27b90c, its settle 76bff05 and the fix pass's 332556d.
  No shipped file changed.
- **2026-11-22, C2, the splitter and its guards** (lane 2, relsplit-2,
  merged in 977a633). `split-service.py`'s four modes and its cases, the
  readers' name and module rules, `bootService`'s file set, `shipped_code`
  under the nine guards, and the gate step. No shipped file changed.
- **2026-11-23, C3, the first move** (relsplit-3, merged in 8e3bbac).
  20ee9da gave rewind-scenario its cage arm first; 6660f73 cut the M5-01
  region, 36 functions and 40,680 bytes, into `Service-rewind.js` (rewind's
  15) and `Service-sources.js` (source switching's 21), and `Service.qml`
  went from 446,973 to 409,024 bytes; 9967571 re-worded two comments.
  1418903 then linted the view (F-GATE-29).
- **2026-11-24, C4, the rest** (relsplit-4, merged in 76297fe). 080b70f cut
  122 functions and 189,976 bytes -- pip's 23 into `Service-pip.js`,
  player's 54 into `Service-player.js`, sources' other 44 and
  `togglePause` after C3's -- and `Service.qml` went from 409,149 to
  228,886 bytes; 65f5d3d re-worded eight comments; b0b74cc added a node
  check of `togglePause` through its forwarder.
- **2026-11-24, D-REL-15** (drel15, merged in e1f2268). e1e376e built
  `adoptActive`'s deferred persist on the root (`persistActiveLater`);
  2e249e8 added the `closure` refusal, and b0fd7a4 its test over every
  code-behind; 4f20e5f held the deferral and its order in node; 04fa5e4
  made the harness's `Qt.callLater` fold as Qt's does (F-HARNESS-130);
  8a5490d kept the spike.
- **2026-11-24, call (d)** (lane-reload-d, branch reload-d: 9d40778 and
  0dbc3d0 the rig, 2f62745 its record, ab92fe4 the board). A hot reload
  across a version change with code-behinds and D-REL-9's write order
  above one worker, measured (the section above); D-REL-16 and
  F-HARNESS-131 filed. No shipped file changed.
- **2026-11-24, C5** (lane-c5-docs, branch c5-docs: 20113e8 this
  document, 31f61dc the service's rules in `docs/ARCHITECTURE.md` section
  9, 1f6275f the plans' greps and restart rules, a6ae342 `Service.qml`'s
  header and the README's development line). Both branches were merged on
  c5d (lane-join-c5d), which wrote the section on updates and corrected
  the header and the development line to call (d)'s measurement.
- **2026-11-24, call (d) settled** (lane-settle-c5d, on c5d: 81de1af,
  4f21014, a86d1a4 and c598733 the race arm, the open watch, `cache.py`
  and the faithful h1; a7c95bf and 86cc65c two comments; the README; the
  records). The three rechecks' findings measured and answered: real races
  on both roots, a poisoned disk cache on each, D-REL-16 made P2;
  D-DOC-37 and F-HARNESS-131 fixed.
- **2026-11-24, the settle's rechecks** (lane-fix-c5d, on c5d). The two
  read-only rechecks of the settle (recheck-c5ds-records,
  recheck-c5ds-measure) blocked on four text findings and raised nits;
  each answered with a dated bracket here, in QA-RESULTS, STATUS and the
  race record: a poisoned code-behind outlives restarts on root a too, a
  merge fired at the first `manifest.json` read reaches the model, and the
  poisoning window is about 10 ms under a concurrent merge **[2026-11-25, D-DOC-38: a lower bound, about 10 ms or more, read off the two poisoned units whose opens were logged]**. The rig's
  restarts are checked and its two clocks stated; `RIG_QMLCACHE=home`
  added. F-GATE-30 filed and fixed: constraint 3, the helper's standard
  library rule, had no gate check (tests/test_helper_stdlib.py).

## What is not measured

From the D-REL-14, D-REL-15 and D-REL-16 rows:
- The host's WHOLE shell. Call (d)'s rig ran the host's own registry,
  watcher, `_syncServices`, `rescanPlugins`, disable and enable, but
  without the bar, the other plugins and the first-party services
  (`firstPartyDir` kept them out). Whether a real shell's engine ever
  releases a plugin's component over a long session was not reached, and
  why the rig's never did was not read in the Qt 6.12 sources.
- Any player across an update: nothing played, attached or zapped in call
  (d)'s arms, so the old and new player code-behinds ran only their
  start-up probes.
- D-REL-16's window in a real race: the half trees were made by hand in
  the shapes git's measured order passes through, not timed by git; how
  often a cold load falls inside the window; root b's h0 and first-release
  h4; `/etc/gitconfig` (read, not run); and `omarchy plugin remove` then
  `add` without a restart, which no arm drove. **[2026-11-24, lane-settle-c5d: real races are measured since ("Real races" above). Still not: how often a real cold start overlaps an update; a race against a model part's unit; a race at the first code-behind release on root a; any player across a mixed or poisoned build; and `~/.cache/quickshell/qmlcache` with `XDG_CACHE_HOME` unset (read in QStandardPaths' rule; the rig always sets it to a decoy)]** **[2026-11-24, lane-fix-c5d: two of these are measured since. A race against the model: reached at four workers with no plugin loaded, a poisoned model unit missed by 2.5-4 ms **[2026-11-25, D-DOC-38: 2.4-16.3 ms over the 8 races that saved a unit (one worker M1 2.5, M2 16.3, M3 7.0, M4 3.6, M5 7.6; four workers M3-c4 4.4, M4-c4 5.4, M5-c4 2.4), each a difference across the rig's two clocks, so by as little as about 2.5 ms (recheck-c5dt-records)]**, and the bar's unit poisoned on root b ("Real races", above). And the folder with `XDG_CACHE_HOME` unset: recheck-c5ds-measure ran the rig with that variable unset as well (its one-line variant, now the rig's `RIG_QMLCACHE=home`), and the shell put its 23 units in `$HOME/.cache/quickshell/qmlcache` of the decoy HOME; of 8 races on root a (its U641, U643, U646 and U649, one worker and four) 2 were poisoned past two restarts, and removing that folder and restarting recovered both, all C2 and ready. `omarchy-launch-shell` starts `quickshell -n -p "$OMARCHY_PATH/shell"` with no cache setting, and nothing under /usr/share/omarchy nor any string of /usr/bin/quickshell names QML_DISK_CACHE_PATH, QML_DISABLE_DISK_CACHE or qmlcache (read again by lane-fix-c5d). Not run: the README removes the folder while the shell runs, the rig with it stopped, which is benign by the mechanism (a running shell saves a unit only after a fresh compile, from the disk's current text). Still not measured: how often a real cold start overlaps an update, a race at the first code-behind release on root a, and any player across a mixed or poisoned build]**
- D-REL-15's crash needs the Service deleted inside the turn a closure was
  scheduled in. Call (d)'s disables destroyed a Service with live
  code-behinds four times with no fault, but whether a deferred call was
  pending then was not observed, so that condition is not measured.
  Whether a Quickshell Process can deliver an exit to its Connections
  while its Service is being destroyed needs a cage.
- rewind-scenario's desk arm has not run since three of its checks changed
  in C3's lanes (F-HARNESS-129); every live proof of the split ran in a
  nested cage.
- No install has run a code-behind: v0.20.0 ships the one-file service.
