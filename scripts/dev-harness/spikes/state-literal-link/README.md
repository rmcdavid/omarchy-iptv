# state-literal-link: the D-STATE-9 measurement, re-runnable

The FileView writes `state.json` through Qt's `QSaveFile` (`atomicWrites:
true`; D-SINK-103's spike, `../state-private`, watched it under gdb), and
`QSaveFile` resolves a link at the path by its LITERAL text: a relative
target is joined to the link's own path and cleaned with `..` read
lexically, hop by hop. The kernel -- and so the FileView's read, the
helper and `ls` -- resolves the same link through the folders as they
really are. Where a folder on the way is itself a link, `..` means two
different folders, so the save can land in a file the plugin never reads
back. Filed as D-STATE-9 by the D-SINK-103 review on 2026-11-14 (measured
there offscreen under gdb on a FileView, not kept); its claims check
reproduced it with a `QSaveFile` probe in scratch, and this is that probe,
kept, with the layout moved into the driver so the shipping helper's `state
private` can run between the layout and the save. `docs/QA-RESULTS.md`
under "D-STATE-9" is the write-up, and "D-STATE-9: the guard" the fix's.

Since the guard (2026-11-21) the spike also holds the helper's reading of a
link to the installed Qt's: for every case, the file the helper says
`QSaveFile` writes (`qt_link_literal`) must be the file `NEW` landed in, and
the helper's verdict (`state_link_split`) must be exactly "the save missed
the file the kernel reads". And the probe now runs UNDER GDB (`handle all
nopass`, debuginfod off), on the private bus as before, so a crash of it is
gdb's to report and never a crash card on the desktop; before 2026-11-21 it
ran bare on the bus.

## The files

| file | what it is |
|---|---|
| `probe.cpp` | saves `NEW` through `QSaveFile(PATH)` (open, write, commit) and prints `QFileInfo::symLinkTarget`, `realpath(3)` and each named file's mode and first line; `--clean HEX...` prints `QDir::cleanPath` of each input instead |
| `measure.sh` | builds the probe against the installed `libQt6Core` (`pkg-config Qt6Core`), lays out each case in a 0700 work folder, runs the probe under gdb on a private D-Bus (`../../private-bus.sh`) with no display variables, and prints a `VERDICT` per case (where the plugin reads, where `NEW` landed and at what mode) and judge.py's `CHECK`; exit 1 when a CHECK fails. `--clean` prints the cleanPath fixture |
| `judge.py` | the helper's half: BEFORE the save, the shipping helper's literal reading and split verdict (read-only, no bytecode written); AFTER it, the `CHECK` line; and the cleanPath corpus and fixture |
| `RESULT-2026-11-14.txt` | the run of the first ten cases on this machine's qt6-base 6.12.0-3 |
| `RESULT-2026-11-15.txt` | the same ten cases again, with that day's driver and the helper as committed: every line after the header the same |
| `RESULT-2026-11-21.txt` | all 27 cases with the guard as its review settled it: 27 CHECKs, 0 failed (the first guard's run, 21 cases, is replaced; docs/QA-RESULTS.md keeps its counts) |
| `RESULT-2026-11-21-baseline.txt` | the same driver over 085a49d, the tree before the guard, all 27 cases: no CHECK (no guard), and `state private` confirming every layout it now refuses; the first ten cases' probe lines are RESULT-2026-11-15.txt's, line for line |

## The cases

The layout for the first ten but `above`: `state -> T/state` (the state
folder is a link), `T/state/state.json -> ../wide/state.json`. The kernel
reads `T/wide/state.json`; `QSaveFile` writes `wide/state.json`, beside the
folder LINK.

| case | layout | measured |
|---|---|---|
| `r600` | real 0600, nothing at the literal location | `NEW` in the literal file, 0600 |
| `r644` | real 0644 (0.19.1's maintainer case, misplaced) | `NEW` in the literal file, 0644 |
| `r600-l644` | real 0600, a 0644 literal file | literal file 0600: the mode is the REAL file's |
| `r644-l600` | real 0644, a 0600 literal file | literal file 0644: the same |
| `none` | no real file (the link dangles), nothing literal | literal file created 0644, the umask's |
| `nodir` | real 0600, no folder at the literal location | `open` fails, No such file or directory: nothing written, the save fails |
| `r644-private` | `r644`, the helper's `state private` first | before the guard: the real file made 0600 (`changed`), the literal file 0600; with it: refused `split-link`, nothing changed |
| `none-private` | `none`, the same | before: the real file created 0600 and empty (`created`), the literal file 0600; with it: refused, nothing created |
| `chain` | `T/state/state.json -> ../a/state.json`, and at the literal `a/state.json` a second link `-> ../wide/state.json` | `NEW` in `wide/state.json`: the second hop read against the FIRST hop's literal folder |
| `above` | `home/.local/state -> data/state` (a linked parent), the state folder real beneath it, `state.json -> ../../x/state.json` | `NEW` in `home/.local/x/state.json`; the plugin reads `data/x/state.json` |
| `plain` | no link at all | the same file; `state private` `kept` |
| `abs` | an absolute link through the linked state folder | the same file; `kept` |
| `rel` | `state.json -> sub/state.json` in a real state folder | the same file; `kept` |
| `inlinked` | `T/state/state.json -> state.real.json` | the same file; `kept` |
| `samedir` | `T/state/state.json -> ../state/state.real.json`: out of the linked folder and back into one of its name | literal `state/state.real.json`, kernel `T/state/state.real.json`: two strings, ONE file; `kept` |
| `sync` | `state.json -> home/Sync/state.json`, `home/Sync -> mnt/data/Sync` (the ~/Sync shape) | the same file by two strings; `kept` |
| `dotdot` | `state.json -> ../../dotfiles/state.json`, no folder climbed out of a link | the same file; `kept` |
| `chain2` | `chain` one folder deeper: `../a/b/state.json`, the literal `a/b/state.json -> ../w/state.json` | `NEW` in `a/w/state.json`: each hop against the PREVIOUS hop's folder, not the first's; refused |
| `hardlink` | `r600` with `wide/state.json` a hard link of the real file | `NEW` in a new inode at `wide/state.json`, the real name keeps `REAL`: one inode, two entries; refused |
| `loop` | the literal `a/state.json -> ../a/state.json` (itself), the kernel reading `T/a/state.json` | `QSaveFile`, past its own bound, wrote over the PATH: the `state.json` link replaced by a regular file holding `NEW`; the helper's reading, past the same bound, is the path too; refused |
| `selfloop` | `state.json -> state.json` | the kernel cannot resolve it either; `QSaveFile` replaced the link with a 0644 file, the file the helper's reading names; `state private` refuses it as `unreachable`, as before |
| `hardlink2` | the review's: `state.json -> ../x/b.json`, `T/x -> R` (absolute), a real `x/b.json -> ../R/a.json`, `R/a.json` a hard link of `R/b.json` | the kernel reads `R/b.json`, `QSaveFile` wrote `NEW` into a new inode at `R/a.json`: ONE folder, two names, one inode, two entries; refused (the first guard counted them one entry and confirmed it) |
| `twofiles2` | the same with `R/a.json` a file of its own | `NEW` in `R/a.json`; refused |
| `chain41` | 41 links on the literal reading (`state.json -> ../l/s0`, `l/s0 -> s1` ... `l/s39 -> T/l/s0`), 2 on the kernel's | `NEW` in `T/l/s0`, the kernel's file; not refused (the first guard stopped at 40 and refused it) |
| `chain127` | the same with 127 | `NEW` in `T/l/s0`: `QSaveFile`'s last; not refused |
| `chain128` | the same with 128 | `QSaveFile` wrote over the PATH, the link replaced by a regular file holding `NEW`, `T/l/s0` kept `REAL`; refused |
| `nonutf8` | `state.json -> b"\xff.json"` in a real folder, `REAL` there | `QSaveFile` read the byte as U+FFFD and wrote `NEW` into a new file of that name (`\xef\xbf\xbd.json`), `\xff.json` kept `REAL`; refused. Printed as `\x` escapes |

So the mode of the misplaced file is the mode of the file the kernel
resolves, read when the save opens (or the umask's when there is none), not
the mode of the file it replaces; since D-SINK-103's `state private` makes
the kernel's file 0600 before every write, the misplaced file is 0600 too.
What stayed was the data loss: every save landed where nothing reads it.
Since the guard `state private` refuses every case the CHECK line marks
`split=yes`, before the write, so nothing is saved there.

## Running it

    TMPDIR=<a short scratch folder> scripts/dev-harness/spikes/state-literal-link/measure.sh [CASE...]
    TMPDIR=<a short scratch folder> scripts/dev-harness/spikes/state-literal-link/measure.sh --clean > tests/fixtures/qt-clean-path.json

The scratch folder must be short (the private bus's socket path has a
100-byte limit, F-HARNESS-104). Needs `g++`, `pkg-config`, the Qt 6 Core
development files (qt6-base ships them), `gdb`, `node` (for the model's
argv) and `python3`; a missing one is a SKIP (exit 77). Holds no display,
starts no compositor and no shell, makes no network request (debuginfod is
off and `DEBUGINFOD_URLS` empty), and touches nothing outside its work
folder, which it removes at exit. Regenerate the cleanPath fixture when Qt
changes, and read the diff before committing it.
