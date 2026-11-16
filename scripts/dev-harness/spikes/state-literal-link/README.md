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
under "D-STATE-9" is the write-up.

## The files

| file | what it is |
|---|---|
| `probe.cpp` | saves `NEW` through `QSaveFile(PATH)` (open, write, commit) and prints `QFileInfo::symLinkTarget`, `realpath(3)` and each named file's mode and first line |
| `measure.sh` | builds the probe against the installed `libQt6Core` (`pkg-config Qt6Core`), lays out each case in a 0700 work folder, runs the probe on a private D-Bus (`../../private-bus.sh`) with no display variables, and prints a `VERDICT` per case: where the plugin reads (`read`, realpath), where `NEW` landed and at what mode, and whether that is the same file |
| `RESULT-2026-11-14.txt` | the run of all ten cases on this machine's qt6-base 6.12.0-3 |
| `RESULT-2026-11-15.txt` | the same ten cases again, with this driver and the helper as committed: every line after the header the same |

## The cases

The layout for all but `above`: `state -> T/state` (the state folder is a
link), `T/state/state.json -> ../wide/state.json`. The kernel reads
`T/wide/state.json`; `QSaveFile` writes `wide/state.json`, beside the
folder LINK.

| case | layout | measured (RESULT-2026-11-14.txt) |
|---|---|---|
| `r600` | real 0600, nothing at the literal location | `NEW` in the literal file, 0600 |
| `r644` | real 0644 (0.19.1's maintainer case, misplaced) | `NEW` in the literal file, 0644 |
| `r600-l644` | real 0600, a 0644 literal file | literal file 0600: the mode is the REAL file's |
| `r644-l600` | real 0644, a 0600 literal file | literal file 0644: the same |
| `none` | no real file (the link dangles), nothing literal | literal file created 0644, the umask's |
| `nodir` | real 0600, no folder at the literal location | `open` fails, No such file or directory: nothing written, the save fails |
| `r644-private` | `r644`, the helper's `state private` first | the real file made 0600 (`changed`), the literal file 0600 |
| `none-private` | `none`, the same | the real file created 0600 and empty (`created`), the literal file 0600 |
| `chain` | `T/state/state.json -> ../a/state.json`, and at the literal `a/state.json` a second link `-> ../wide/state.json` | `NEW` in `wide/state.json`: the second hop read against the FIRST hop's literal folder |
| `above` | `home/.local/state -> data/state` (a linked parent), the state folder real beneath it, `state.json -> ../../x/state.json` | `NEW` in `home/.local/x/state.json`; the plugin reads `data/x/state.json` |

So the mode of the misplaced file is the mode of the file the kernel
resolves, read when the save opens (or the umask's when there is none), not
the mode of the file it replaces; since D-SINK-103's `state private` makes
the kernel's file 0600 before every write, the misplaced file is 0600 too.
What stays is the data loss: every save lands where nothing reads it.

## Running it

    TMPDIR=<a short scratch folder> scripts/dev-harness/spikes/state-literal-link/measure.sh [CASE...]

Needs `g++`, `pkg-config`, the Qt 6 Core development files (qt6-base ships
them), `node` (for the model's argv) and `python3`; a missing one is a SKIP
(exit 77). Holds no display, starts no compositor and no shell, and touches
nothing outside its work folder, which it removes at exit.
