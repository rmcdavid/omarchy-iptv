# Splitting `Service.qml` into code-behinds (D-REL-14)

Written 2026-11-24 on `dev` 3200d22, D-REL-14's C5. The split itself is
done and merged on `dev` (C3 on 2026-11-23, C4 and D-REL-15's fix on
2026-11-24) and **unreleased**: v0.20.0, the release on `main`, ships the
one-file `Service.qml`, so no install has run a code-behind yet. Every
figure below was read or run on 3200d22 unless a date says otherwise; the
measurements behind them are in `docs/QA-RESULTS.md` (the sections from "The
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
cut. The service's one text today -- its inline view, below, what the one
file would weigh -- is 449,007 bytes, 9,745 under the ceiling.

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
| `Service.qml` | 230,265 | 47 of its own, 158 forwarders | every property, signal, change handler and object; the state machine; the functions listed below; one import line per code-behind |
| `Service-pip.js` | 20,235 | 23 | picture in picture: the `p` key and its verb, the window and monitor reads, the step plan, the peek, the probe |
| `Service-player.js` | 112,628 | 54 | the detached player: play, stop, zap, the control verbs and their results, the probe and adoption, the socket observer and its lines, the failure notices |
| `Service-rewind.js` | 9,103 | 16 | live rewind: the seek queue and its readout, the track requests, and `togglePause` |
| `Service-sources.js` | 90,674 | 65 | sources: switching, probing, reconcile and adoption, cache jobs, the playlist and guide runs, the bar entry writer, logos, dead-channel marks |

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
else holds one (the lead's call (e)); everything that needs the service's
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
root functions, 158 forwarders and 2,268 root member sites, 34 of 34 cases;
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
makes a closure cannot be moved (`closure`). After the cut:
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
  file).
The readers, the harness and the guards need nothing: they read the import
lines.

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
- **2026-11-24, C5**, this document, and the service's rules in
  `docs/ARCHITECTURE.md` section 9.

## What is not measured

From the D-REL-14 and D-REL-15 rows:
- The host's own plugin registry. Part A's rig ran the host's three loaders
  under the host's `shell.qml` header, with the file watcher off; no
  `PluginRegistry`, `_syncServices` or `rescanPlugins` ran.
- Before the first release that ships a code-behind, the lead's call (d)
  asks two things to be measured or answered, never assumed: a hot reload
  across a version change with code-behinds, in a nested cage (D-REL-6's
  case), and D-REL-9's write order, which Part A measured holding only at
  git's default `checkout.workers=1`.
- D-REL-15's crash needs the Service deleted inside the turn a closure was
  scheduled in; the host destroys a plugin's services in `shell.qml`'s
  `_syncServices` on a disable or a remove (read), and that is not
  measured. Whether a Quickshell Process can deliver an exit to its
  Connections while its Service is being destroyed needs a cage.
- rewind-scenario's desk arm has not run since three of its checks changed
  in C3's lanes (F-HARNESS-129); every live proof of the split ran in a
  nested cage.
- No install has run a code-behind: v0.20.0 ships the one-file service.
