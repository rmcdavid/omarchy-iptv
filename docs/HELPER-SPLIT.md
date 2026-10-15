# Splitting `bin/omarchy-iptv` (D-REL-7): the design, for the owner

Written 2026-10-15 on `dev` c4c7a3e. Nothing here is built yet. The
implementation waits for the owner's word on the three decisions at the end.

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
  bundled binaries.

The cost is one `exec(compile(...))` in a shipped file, which a human
reviewer will read. The stub is about 5 KB, the loader takes no input (fixed
names from the stub's own directory, never a path from argv or the
environment), and its comment says why it exists. A missing or unreadable
part ends the run with one stderr line naming the part and exit status 1,
not a traceback.

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

## Decisions for the owner

1. **Approach A**, the stub and one namespace, over B and C.
2. **The layout**: the directory `bin/helper/` and the 11 parts above, or
   another grouping (fewer, larger parts are equally workable; nothing
   depends on the names).
3. **Sequencing**: after 0.14.1 is cut, or inside it.
