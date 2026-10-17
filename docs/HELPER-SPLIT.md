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
`08-player-verbs.py` (8,236 and 15,982 to 70,927 since the review's fixes on
2026-10-17: the checking loader, and a last line in every part). The next release's notes should say the helper is now
several files and the window before the shield is about 30 ms, not about a
tenth of a second.

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
  anywhere in the helper and nothing reads `__file__` but
  `_manifest_version`, which resolves the same way from the stub.
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
reviewer will read. The stub is about 8 KB, the loader takes no input (fixed
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
runs them. A part that is missing, unreadable, empty, cut off, not text
(a NUL byte, or not UTF-8) or does not compile, or a file in `bin/helper/`
that `HELPER_PARTS` does not name (a bytecode directory, an editor's swap
file, a part a newer release added), ends the run before any part executes,
with one JSON object on stdout -- `{"ok": false, "part": "05-ipc-logos.py",
"error": {"code": "helper_damaged", "message": "bin/helper/05-ipc-logos.py
is empty; reinstall the plugin"}}` -- the same sentence as its one stderr
line, and exit status 1, as every other helper failure. The service maps the
code to "Plugin files damaged (05-ipc-logos.py) . reinstall the plugin"
(`Model.helperDamagedReason`, which shows the part only when it has a part's
shape) and routes it exactly as the empty stdout it replaces: "cannot tell"
on the status branch, never a health strike (`Model.helperCannotTell`), and
`unknown` on the play branch.

**The witness.** A cut-off part is told from a whole one by its last line,
which `split-helper.py` writes and the stub recomputes:
`# end of 05-ipc-logos.py: 42179 bytes above, crc32 848354c6` (the line as
it stands at this change; it moves with every edit). A file cut
off anywhere has lost that line, and a file whose bytes changed under it no
longer matches it. A checksum and a length rather than a cryptographic
digest, on purpose: the line sits in the file it describes, so anyone able
to rewrite the part can rewrite the line, and no digest stored there could
authenticate anything; it detects DAMAGE. CRC-32 catches every truncation
and every error burst up to 32 bits, and `zlib` is already loaded by
`01-core.py`, where `hashlib` is deliberately imported late. The length is
for a human comparing two copies. `--check` (the gate) refuses a part whose
last line does not match, `--verify` compares the parts with it, and
`--seal` rewrites every part's last line, and the loader, after an ordinary
edit to a part.

**What git does during an update, measured.** `omarchy-plugin-update` is
`git merge --ff-only`. Under inotify, in a scratch install, for three
updates (0.14.2's one file to the split, the split to this change, and a
parts-only release after it): git writes each changed file IN PLACE --
`DELETE`, `CREATE`, `CLOSE_WRITE`, one file after another, no temporary
file and no rename -- and in index order, so every `bin/helper/` part is
written before `bin/omarchy-iptv` (`h` sorts before `o`), which agrees with
the live lens's upgrade of a running 0.14.2 shell. So a helper the shell
spawns DURING an update can meet a part missing (between the unlink and the
create), empty (just created) or cut off (being written), while the stub in
place is the OLD one. A rig spawning `state show` on four threads through
300 parts-only updates of a scratch install (load average about 4, the gate
running beside it) met that window in 5 of 94 runs with this stub, every
one refused with the JSON object (`05-ipc-logos.py is empty` 3, `is cut
off or altered` 1, `10-state.py is empty` 1), and in 7 of 94 with
f14c8ac's: three `NameError: name 'cmd_state' is not defined` tracebacks
(an empty `10-state.py` that compiled to nothing), three `SyntaxError`
tracebacks over a part cut off mid-docstring, and one `cannot read` line
with nothing on stdout. A `--version` run of the same rig met it 6 times
in 91, all refused. The install's `git status --short --ignored` was empty
after every run.

**What it does not catch, recorded rather than fixed.** Each part is
checked against ITSELF. A spawn that lands between two parts being
rewritten can read one part from the old release and one from the new,
each whole, and the stub cannot tell. No name is bound in two parts (the
identity lens's AST scan of all eleven), so a mismatch most likely fails
loud on a missing name rather than running a wrong one, but that is
reasoned, not measured; the rig above cannot see a mix, because both of
its releases answer alike. Two things narrow it: an update that ADDS a part
writes it while the old stub is in place, and the old stub refuses the
file it does not name, until the new stub lands; and the update that
brings this change in is itself applied by f14c8ac's stub, which has none
of these checks, so the first update after it is the first one the
checks guard.

## Decisions for the owner

1. **Approach A**, the stub and one namespace, over B and C.
2. **The layout**: the directory `bin/helper/` and the 11 parts above, or
   another grouping (fewer, larger parts are equally workable; nothing
   depends on the names).
3. **Sequencing**: after 0.14.1 is cut, or inside it.
