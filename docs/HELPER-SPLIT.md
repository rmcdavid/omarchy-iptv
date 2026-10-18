# Splitting `bin/omarchy-iptv` (D-REL-7): the design, for the owner

Written 2026-10-15 on `dev` c4c7a3e. **Decided and built the same day**: the
owner chose A, this layout, and "after 0.14.1 is cut" (the decisions log),
later moved to after 0.14.2. The first build was on branch
`lane-helper-split` (38f12eb, e73cdce), cut from the helper as it stood
before 0.14.1; it never reached `dev`. **Rebuilt on today's `dev` on
2026-10-17** as branch `lane-split-s1`, for merge onto `dev` after review:
the parts cut afresh from 0.14.2's
one-file helper (1ecfd9d, 447,660 bytes) at the same eleven banners, and
the branch's tooling carried over (QA-RESULTS "D-REL-7: the helper split,
rebuilt on today's dev"). The table below is the prototype's; at this cut
the stub is 6,502 bytes and the parts 15,926 to 70,864, the largest still
`08-player-verbs.py` (9,137 and 15,926 to 70,864 since the follow-up's
fixes on 2026-10-17: the checking loader, whose list gives each part's
length and CRC-32; the per-part last lines of the review's first fix are
gone). The next release's notes should say the helper is now several files
and the window before the shield is about 30 ms, not about a tenth of a
second, and what an update to it can meet (the last section).

## Why now

`release.py check` holds every shipped file under 448 KiB (458,752 bytes),
64 KiB below the marketplace scanner's per-file limit, because a file over
that limit stops the automated security baseline and no request can be
approved (D-REL-5). The executable is held too: the scanner reads the first
4 KiB of an oversized executable, and a text helper fails exactly as
`Model.js` did. The helper's size, release by release:

| | bytes | change |
|---|---|---|
| 0.13.6 | 410,678 | |
| 0.14.0 | 438,533 | +27,855 |
| 0.14.1 (prepared) | 445,263 | +6,730 |

13,489 bytes of headroom are left: a release the size of 0.14.0 does not
fit. The 0.14.0 pre-cut record already said the split was due.

## The choice: one namespace, several files

**A (recommended): a small stub that compiles the parts into its OWN module
namespace, in a fixed order.** `bin/omarchy-iptv` keeps its docstring, the
`from __future__` line, `import sys`, `shield_environment()` and the
`SHIELDED = ...` call, then compiles each file named in a literal tuple,
`HELPER_PARTS`, from `bin/helper/` into `globals()` with
`exec(compile(source, path, "exec", dont_inherit=True), namespace)`, and
ends with the `if __name__ == "__main__"` guard it has today. The parts are
the current file's body cut at its own section banners, in order, each with
a generated header (a comment saying what it is, and its own
`from __future__ import annotations`, because a future import binds one
compilation unit).

What that buys, each point measured or read rather than assumed:

- **Behaviour identical by construction.** One global namespace, the same
  names, the same definition order: the parts with their headers stripped
  concatenate to today's body byte for byte. There is no `global` statement
  anywhere in the helper, and `__file__` is the stub's (the parts run in
  its namespace), read in two places: the loader, for the parts, and
  `_manifest_version`, for the manifest. Both resolve it through
  `realpath`, so a symlink to the stub finds both; `_manifest_version` used
  `abspath` until the follow-up, so `--version` through such a symlink
  printed `0.0.0+unknown` while the verbs ran, as the one-file helper's did.
  **Behaviour, not bytecode** (the identity lens of the review, 2026-10-17):
  CPython 3.14 compiles an attribute call on a module differently when the
  module was bound by an import in the SAME compilation unit -- a method load
  there, `LOAD_ATTR` and then `PUSH_NULL` here, because the imports now live
  in `01-core.py` and the calls in the other parts. That is 248 call sites,
  and exception-table offsets, stack sizes and one `EXTENDED_ARG` width move
  with them; class `__firstlineno__` values move with the line numbers. For a
  module object the two forms do the same thing (`ModuleType`'s own
  attribute lookup sends the method form through plain `getattr`), and that
  is measured, not argued: with those two differences normalised, 0 of 320
  code objects differ from the one-file 1ecfd9d at b80c7ff (and only the
  shield docstring at c46ce50); the module namespace is the same 488 names
  with equal values; and a 129-step corpus of every verb the service runs
  gives byte-identical stdout, stderr, exit codes and written files on the
  whole tree and on the allowlist-only export. Nobody should expect
  `co_code` to match byte for byte.
- **Every consumer that runs or imports the helper is untouched.** The
  service and the model run `python3 <plugin>/bin/omarchy-iptv <verb>`; the
  README names the same path; `tests/helper_loader.py` loads the stub with
  `SourceFileLoader`, and the stub fills that module. A throwaway prototype
  of exactly this layout (11 parts, cut by script) passed 1,225 of the 1,229
  python tests unchanged: two failures are the text readers listed below,
  and two were the prototype's own one-commit git repository, which lacks
  the commits `test_harness_shell_model.py` looks up.
- **The tests' 22 monkeypatches keep working.** Tests replace
  `helper.fetch_logo`, `helper._sleep`, `helper.find_player` and eight other
  names on the module and expect callers to see the double. In one
  namespace they do; with real modules a caller in another part would keep
  the original.
- **No bytecode is written.** `compile()` of source text writes no `.pyc`,
  so the plugin directory stays read-only at runtime (constraint 4), as it is
  today for a script run as `__main__`.
- **The shield moves ahead of compiling the body (D-SINK-9).** The window
  in which a same-uid process can read a fetch verb's environment is the
  interpreter starting and compiling what precedes the shield. Measured by
  the D-SINK-9 method (a same-uid reader polling `/proc/<pid>/environ` every
  0.2 ms from the moment `Popen` returns), 12 interleaved runs per tree,
  twice, load average about 2.5: today 138 and 148 ms median (132.8-211.6),
  the prototype 28 and 29 ms (24.3-86.0, one outlier). The whole `--version`
  run was no slower: 241 and 248 ms today, 206 and 213 ms split. CLAUDE.md
  has carried "a split stub ... reaches about 25 ms" as the unbuilt floor
  since 2026-10-01; this is that floor.
- **The scanner sees nothing new.** The parts are `.py`, which the baseline
  scans, and this repository's port of it reads 0 capability hits over the
  prototype's 108 files. The marketplace's current baseline scripts were
  re-read on 2026-10-15 (analysis, policy, scope, snapshot, scanner): no rule
  concerns `exec`, `compile` or dynamic code; they cover download-and-execute,
  unpinned remote git, sudo and pkexec, installers, services, sudoers and
  bundled binaries. **What does change is which rules read the code**
  (the marketplace lens, 2026-10-17): in 0.14.2 the whole helper was one
  extensionless 100755 file, which the baseline treats as RUNTIME and reads
  with its pipe-to-shell, cargo, shared-temp and remote-git rules but not its
  launcher-literal expansion (that is applied to `.py`, `.qml`, `.js`,
  `.mjs`, `.cjs`, `.desktop` and `.service` only); the parts are 100644
  `.py` files, so about 440 KB of helper code is now read under the `.py`
  launcher-literal rules instead. Not a way round the scan, and measured so
  nobody has to take that on trust: an independent port of the baseline,
  transcribed from scripts byte-identical at marketplace HEAD 621d14d,
  passes the c46ce50 export with findings `[]` and capabilities `[]`, as
  the marketplace recorded for 0.14.2's one file, and passes it again with
  all eleven parts re-marked 100755; the launcher-literal regex matches 5
  calls across the parts (two in 05, two in 08, one in 11), none of whose
  arguments contains curl, wget, git or cargo. Re-run on this lane's
  export (the stub with its checking loader, the parts with their last
  lines): `passed`, `[]`, `[]`, 38 files scanned, both with the parts as
  100644 and re-marked 100755.

The cost is one `exec(compile(...))` in a shipped file, which a human
reviewer will read. The stub is about 9 KB, the loader takes no input (fixed
names from the stub's own directory, found through `realpath` so a symlink
to the stub works as the one file did, never a path from argv or the
environment), and its comment says why it exists. A damaged part ends the
run before anything runs: see "A damaged part" below.

**B: real Python modules with imports** (the shape D-REL-5 gave the JS
model). Rejected: it changes semantics rather than layout. A name imported
from another part is bound at import time, so the tests' monkeypatches stop
reaching callers in other parts; it needs generated import lines across
about 9,000 lines and a checker for the hazards that brings; and it cannot
be proved byte for byte.

**C: keep one file on `dev` and concatenate at release.** It moves the
problem rather than solving it: the shipped file is the one the scanner
limits.

## Layout (the prototype's, for the owner to amend)

Contiguous runs of today's file, cut at its existing banners, by domain:

| part | bytes | what it holds |
|---|---|---|
| `bin/omarchy-iptv` (stub, 100755) | 5,325 | docstring, shield, `HELPER_PARTS`, loader, `main` guard |
| `bin/helper/01-core.py` | 56,171 | imports, constants, paths, redaction, normalization |
| `bin/helper/02-sources.py` | 36,285 | the source records |
| `bin/helper/03-io-playlist.py` | 21,723 | atomic IO, the playlist fetch and parse |
| `bin/helper/04-epg.py` | 55,940 | XMLTV, the window, the now line |
| `bin/helper/05-ipc-logos.py` | 41,272 | the legacy mpv IPC verbs, logos |
| `bin/helper/06-failed.py` | 19,877 | dead-channel marks |
| `bin/helper/07-player.py` | 45,128 | the detached player: discovery, lock, spawn, connection |
| `bin/helper/08-player-verbs.py` | 70,646 | the channel, the verbs, tracks, rewind |
| `bin/helper/09-cache.py` | 15,708 | the per-source cache |
| `bin/helper/10-state.py` | 44,101 | `state.json` |
| `bin/helper/11-cli.py` | 34,120 | the config shield, the clipboard, the parser, `main` |

The largest part is 70,646 bytes, so each has room to grow about six-fold
before the ceiling. The parts are mode 100644. The allowlist grows from 31
files to 42.

## What else changes

1. **`scripts/release.py`.** The 11 parts join `ALLOWLIST` and
   `SHIPPED_SOURCES`, so the citation and `Model.js` scans read them;
   `helper_subcommands` reads every helper file, not the stub. A new
   resolver reads `HELPER_PARTS` out of the stub with `ast.literal_eval` and
   requires each part on the allowlist and present, and every allowlisted
   `bin/helper/` file named by the stub. The need is demonstrated: on the
   prototype, `release.py check` is green while the artifact it would build
   ships without its parts.
2. **`scripts/split-helper.py`, new, stdlib.** `--write --from-git <rev>`
   cuts the one-file helper at named banners; `--verify --from-git <rev>`
   proves stub head, parts without headers and stub tail equal the file at
   `<rev>` byte for byte; `--check`, which the gate runs, proves
   `HELPER_PARTS` and `bin/helper/` agree both ways, every part carries the
   header and compiles, and every part is under the ceiling.
3. **`scripts/check.sh`** runs `split-helper.py --check` and gains the new
   tests in its python floor.
4. **The three readers of the helper's TEXT.** `tests/test_state.py` takes
   `inspect.getsource(helper)` (the whole module) to count one idiom;
   `tests/test_release.py` reads `bin/omarchy-iptv` for the parser;
   `tests/test_shipped_copy.py` names `bin/omarchy-iptv` alone as shipped
   code. All three read the stub plus the parts, through one function.
5. **The harness's slow trees.** `key-scenario.sh` and `rewind-scenario.sh`
   copy the helper alone to `bin/omarchy-iptv.real` under a slow wrapper;
   they copy the parts beside it, through a new `qa_helper_files` in
   `scripts/qa-lib.sh` (the `qa_model_files` shape, with its own
   `qa-lib-test.sh` cases). The stub resolves its parts from its own
   directory, so `omarchy-iptv.real` finds them there.
6. **Shipped comments citing a helper line** (`Service.qml` "bin/omarchy-iptv:3029",
   `model/epg.mjs` "bin/omarchy-iptv:234-236") name the function or the
   constant instead. Dated citations in `docs/` stay as they are.
7. **CLAUDE.md** (the branch section's allowlist count, constraint 5's
   D-SINK-9 window figures, the release recipe) and
   `docs/ARCHITECTURE.md` (how the helper is laid out and how a part is
   added).

## How it will be proved

- `split-helper.py --verify --from-git <rev>` byte for byte against the
  one-file helper it was cut from.
- `./scripts/check.sh` green; the python suite, node checks and qml spec
  unchanged in count except the new tests; the logo, key, sources and argv
  scenarios reading the same before and after, the live key arm under the
  nested headless cage on a private bus.
- The window re-measured by the 0.2 ms reader, interleaved with the
  one-file helper under the same load, and the argv scenario's S4b relative
  bound still passing.
- Every new check seen red first: the resolver against today's
  `release.py` (the prototype's green check is the red run); the split
  script's decisions by mutation (a part left out of `HELPER_PARTS`, a stray
  file in `bin/helper/`, a missing header, a part over the ceiling).

## Sequencing

0.14.1 is prepared on `dev` and not cut, and `release.py build` exports
whatever `dev` holds. If the split lands on `dev` first, it ships inside
0.14.1. The recommendation is to cut 0.14.1 as prepared, a single security
fix the maintainer is waiting on, and land the split straight after for the
next release, behind a pre-cut lens that re-reads the marketplace baseline
as 0.13.6's did.

## A damaged part, and what an in-place update can meet (2026-10-17)

The review of the split (identity lens, P2) found that the first loader
caught `OSError` only and ran each part as it read it: a part with a syntax
error or a NUL byte gave a traceback, and an EMPTY part compiled to nothing,
so with `05-ipc-logos.py` empty `state init`, `playlist`, `epg`, `failed
mark` and `cache prune` exited 0 and wrote their files, and with
`02-sources.py` empty some verbs ran and others died on a `NameError`. A
truncated one-file helper always lost `main`, its last definition, and so
ran no verb at all; the split had made a damaged install able to run half a
helper.

**The rule now:** the stub reads and checks all eleven parts, and only then
runs them. A part that is missing, unreadable, not a regular file, empty,
not the part the stub's list names (cut off, altered, or of another
release), not text (a NUL byte, or not UTF-8) or does not compile, or a file
in `bin/helper/` that `HELPER_PARTS` does not name (a bytecode directory, a
part a newer release added; a name starting with `.`, such as an editor's
swap file, is ignored), ends the run before any part executes,
with one JSON object on stdout -- `{"ok": false, "part": "05-ipc-logos.py",
"error": {"code": "helper_damaged", "message": "bin/helper/05-ipc-logos.py
is empty; reinstall the plugin"}}` -- the same sentence as its one stderr
line, and exit status 1, as every other helper failure. The service maps the
code to "Plugin files damaged (05-ipc-logos.py) . reinstall the plugin"
(`Model.helperDamagedReason`, which shows the part only when it has a part's
shape) and routes it exactly as the empty stdout it replaces: "cannot tell"
on the status branch, never a health strike (`Model.helperCannotTell`), and
`unknown` on the play branch.

**The record, in the stub** (the follow-up, 2026-10-17). Each entry of
`HELPER_PARTS` is a part's name, length and CRC-32 --
`("05-ipc-logos.py", 42179, 0x848354c6),` -- and the stub recomputes both
before any part runs: a part cut off, changed under it, or of another
release does not match. The first fix put a last line in each part instead
(`# end of 05-ipc-logos.py: 42179 bytes above, crc32 848354c6`), which told
a cut-off part from a whole one but checked each part only against itself,
so a helper spawned while an update was rewriting the parts could run whole
parts of two releases (below). The record moved into the stub and the last
lines are gone: one witness, in the one file git writes after the parts.
Every edit to a part therefore changes the stub, and `split-helper.py
--seal` rewrites the entries; `--check` (the gate) is red until it has, and
`--verify` names the entries that differ from the cut. A checksum and a
length rather than a cryptographic digest, on purpose: whoever can rewrite
a part can rewrite the stub beside it, so no digest stored there could
authenticate anything; it detects DAMAGE and a MIX. CRC-32 catches every
truncation and every error burst up to 32 bits, two releases of a part agree
on both by chance about once in four billion, and `zlib` is cheap where
`hashlib` is deliberately imported late (`01-core.py`). Each part is opened
without blocking and refused unless it is a regular file (as R23b gave
`state.json`), so a FIFO in a part's place no longer stalls the start until
something writes to it. A name in `bin/helper/` starting with `.` is
ignored by the stub and by `--check` alike: an editor's swap or lock file
cannot be a part, and refusing it stopped the dev tree's helper while a
part was open in vim. Anything else the list does not name is refused,
`__pycache__` included.

**CRLF is read as LF** (P1 of the follow-up's review). `omarchy plugin add`
is a plain `git clone` and `omarchy-plugin-update` a `git fetch` and `git
merge --ff-only`; both honour a user's `core.autocrlf=true`, and `main`
ships no `.gitattributes`, so on such a machine every part arrives with CRLF.
Python compiles CRLF source exactly as LF, so the part is not damaged; but
the first fix's last line was over the raw bytes, so every verb refused --
`--version`, `state init`, `failed mark`, `player probe` -- where 0.14.2 and
f14c8ac ran, and reinstalling cloned the same thing again. The length, the
CRC and the compiled text are now taken over the part with CRLF read as LF,
in the stub and in `split-helper.py` alike. No part, and not the stub,
holds a CR byte of its own (measured 2026-10-17: 0 in each of the twelve
files), so the normalised text of any checkout is the committed blob; and
were one ever added, both sides would still agree, because both read the
same normalised text. `tests/test_split_helper.py` clones a scratch upstream
under a scratch HOME whose `.gitconfig` sets `autocrlf = true`, for an add
and for a fast-forward update, checks the clone really is CRLF, and runs the
verbs; it fails against lane-split-f1 with that review's reply.

The sibling search (rule 15), run rather than reasoned, over a tree whose 41
shipped text files were rewritten with CRLF exactly as autocrlf writes them
(the rest of the tree left LF), the whole gate run over it:
- *What an install runs* reads CRLF unchanged: the stub (above); `omarchy
  plugin validate` over the manifest; qmllint parses the five QML files with
  0 errors; the qml spec, which imports `Model.mjs` and its parts through the
  QML engine, passes 78 of 78; node imports the CRLF `Model.mjs` (654
  exports) from a real autocrlf clone. Nothing else in an install reads its
  own files.
- *The gate's judges of shipped files*: `split-helper.py --check` passes
  and reports the same sizes (they are counted over the normalised text);
  `release.py check`, the capability scan and the text-format guard pass.
  `release.py`'s size ceiling counts the bytes on disk, so under CRLF it
  counts one byte more per line (Service.qml 330,175 against 323,837):
  it can refuse a file early, never pass one that is over, and the ceiling
  sits 64 KiB under the scanner's limit; left as it is.
- *Dev-only readers that break on CRLF*, recorded rather than fixed: 29 node
  checks (15 in a real autocrlf clone, where the fixtures are CRLF too) that pin the text of `Guide.qml`, `Service.qml` or the helper with
  `\n` in a pattern; `split-model.mjs --check` ("not a generated export
  line"); and `qa_model_files` in `scripts/qa-lib.sh`, so 34 harness
  predicates, `run.sh` (three python tests), and the check-tree preflights
  that find the model through it. They cannot matter alone: a real
  `core.autocrlf=true` clone of `dev` checks out the shell scripts with CRLF
  too, and `scripts/check.sh` then stops at its first line (`/bin/bash^M:
  bad interpreter`). A developer with that setting needs a `.gitattributes`
  on `dev`, which is a decision for the lead, not a fix to each reader.
  Two cases in `tests/test_split_helper.py` built their upstream and their
  damages from the checkout's bytes and failed there; they now start from
  the committed text, and pass in that tree.

**What an in-place update can meet, step by step** (re-measured
2026-10-17 for the next CHANGELOG). `omarchy-plugin-update` is `git fetch`
and `git merge --ff-only FETCH_HEAD`. Under inotify, in a scratch clone,
git writes each changed file IN PLACE -- `DELETE`, `CREATE`, `CLOSE_WRITE`,
one file after another, no temporary file and no rename -- in index order:
`Model.mjs`, `README.md`, `Service.qml`, then everything under `bin/`
(`bin/helper/` before `bin/omarchy-iptv`, since `h` sorts before `o`), then
`model/`. A new file is only created, never deleted first. Each state below
was then rebuilt in a copy and three spawns run in it (`--version`, `state
init`, `failed mark`, isolated, in an empty home):

*The one-time step, 0.14.2 to the split* (0.14.2's single file is replaced by
the stub, and the eleven parts arrive first). While the parts are created
-- each one empty, half written or whole -- the helper in place is still
0.14.2's one file, which never reads `bin/helper/`: every spawn runs 0.14.2
in full and writes as it always did. Then `bin/omarchy-iptv` itself is
deleted and recreated: a spawn there meets NO file (`python3: can't open
file`, exit 2, nothing on stdout), an EMPTY file (exit 0, nothing on stdout)
or a PARTIAL stub (a `SyntaxError` traceback, exit 1, nothing on stdout).
None of the three runs a verb or writes anything, and the service reads
each as the empty stdout it already handles ("cannot tell", never a health
strike). Once the stub is whole, the split runs. So this update needs
nothing from the checks, and gets nothing from them either: they ship with
it.

*Every later update* (here a parts-only release, `write_json_atomic` moved
from `03-io-playlist.py` to `09-cache.py`, which is the robust lens's
case). While the parts are rewritten, the stub in place is the OLD one: a
part missing, empty, half written, or whole but of the new release is
refused by it with the `helper_damaged` reply -- before any part runs,
nothing written. With the old loader that last state, both new parts whole
under the old stub, ran: the lens measured `failed mark` creating its cache
directories and then dying on `NameError: name 'write_json_atomic' is not
defined`, and `state init` writing `state.json`. Then the stub is rewritten
in place, with the same three outcomes as above (no file, empty, partial),
none of which runs a verb. A partial stub cannot run one: of every byte
prefix of the stub that compiles, none calls `main` and none calls
`_load_parts` without the whole loader and the whole list (a test, run over
every prefix). Once the stub is whole, the new release runs. A rig racing
four threads of `failed mark` against 300 real `git reset --hard` cycles
between the two releases (load average 2.5-4.3) gave 131 spawns: 30 ran
(ok), 98 were refused (`03-io-playlist.py` 70, `09-cache.py` 28), 2 met an
empty stub and 1 no stub; 0 tracebacks, 0 `NameError`, and `git status
--short --ignored` empty afterwards. A user who sees "Plugin files damaged"
in that moment sees it clear when the update finishes; one parallel
checkout (`checkout.workers`) that wrote the stub before a part would meet
the same refusal from the other side, since a new stub refuses an old part
too (tested both ways).

**Its cost to the D-SINK-9 window.** The checks run after the shield, but
the stub is compiled whole before its first statement runs, so its size is
in the window: compile median 0.56 ms at f14c8ac (6,502 bytes), 0.98 ms
with the first checking loader (8,236), 1.19 ms now (9,137), 300 runs
interleaved at load 3.9. The window itself was measured at about 28 ms
with the first checking loader against 27 ms at f14c8ac (the robust lens,
two interleaved sets of 30), so the extra 0.2 ms here is within its noise,
not zero.

**Still not caught, recorded.** The stub's own rewrite, as above: the
service gets no answer for those few milliseconds, which it already
handles, but the stub cannot check anything while it is not whole. And
`Service.qml` and `Model.mjs` are written BEFORE the helper in the same
update (index order), so for those milliseconds new QML can call the old
helper; nothing in the helper can see that.

## Decisions for the owner

1. **Approach A**, the stub and one namespace, over B and C.
2. **The layout**: the directory `bin/helper/` and the 11 parts above, or
   another grouping (fewer, larger parts are equally workable; nothing
   depends on the names).
3. **Sequencing**: after 0.14.1 is cut, or inside it.
