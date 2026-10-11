# logo-decode-bomb: the D-LOGO-11 measurement, re-runnable

A provider logo chooses how much memory the shell allocates. A JPEG whose
header declares 20000x20000 over a 64x64 scan is 304 bytes; the shell's row
logo slot resident-sets 840 MB decoding it. This directory holds the rig
that measured that, so "measured" means "re-runnable" and not "remembered".

Raised by the marketplace maintainer on omacom/omarchy-plugin-marketplace#10802
against the shipped 0.13.3 (`159da94`). The lead's write-up, with the ruling
on the fix, is `docs/QA-RESULTS.md` under "Fifth maintainer finding,
2026-10-09". The fix is `fb2acdc` (bound the declared dimensions in the
helper; sweep the cache); the scenario that observes it at both sinks is
`scripts/dev-harness/logo-scenario.sh`, which is built from the files here.

## The files

| file | what it is |
|---|---|
| `make-corpus.py` | the corpus, from code: 32 files, stdlib only. Every declared dimension is an argument in the call, so "304 bytes buy 840 MB" is visible in the source rather than asserted here. `--list` prints the table; `--only a,b` builds a subset; `--with-encoder` adds the two files that need ImageMagick. Four of the 32 are a reviewer's shapes (an EXIF thumbnail before the real frame header, with its control; a 64x65535 column; a two-frame GIF), kept because each one passed a mutation of the helper's parser |
| `probe-tmpl.qml` | the SINK: one `Image` declared as `Guide.qml` declares the row logo slot (asynchronous, cache, `sourceSize` 44, PreserveAspectFit, mipmap). `__PATH__` and `__SOURCE_SIZE__` are substituted; 223 is the wall tile, whose only difference is that number. Exit 0 Ready, 1 Error, 2 the 20 s timer |
| `peakrun.py` | runs a child, prints its exit status and `ru_maxrss` on one `PEAKRUN` line. The limit wraps the CHILD only, never this reporter |
| `run.sh` | reproduces the table below and the `QT_IMAGEIO_MAXALLOC` bracket, every row judged against a band, under `prlimit --as=2500000000` around the qml process alone |
| `serve-and-fetch.py` | the provider for the scenario: an https server with a self-signed certificate in a thread, the shipping helper as its child with `SSL_CERT_FILE` pointed at the certificate; nothing detached, nothing to kill by pattern. Its `refusal` verb calls `logo_dimension_refusal` from the tree under test |

## The invocation that keeps the desktop safe

```
python3 peakrun.py prlimit --as=2500000000 -- \
    env QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qml <probe.qml>
```

This is the ONLY form anything here uses to decode a file that might be over
the bound. `prlimit` (util-linux) sets RLIMIT_AS on itself and execs the
command in place (measured 2026-10-11: the pid the command runs under is the
pid `peakrun.py` spawned), so the limit holds exactly the qml process, an
allocation the limit cannot hold is refused inside it, and `peakrun.py`
reads its rusage from outside the limit. `run.sh` and `logo-scenario.sh`
both run `prlimit --as=2500000000 -- true` first and exit 77 if it fails.

The limit is ADDRESS SPACE, not resident set, and 2.5 GB rather than 1.5:
Qt offscreen maps about a gigabyte before it decodes anything (the 72 MB
control is resident set), the 840 MB and 1,239 MB bombs must fit so that the
finding is measured rather than cut off, and the 65500x65500 headers ask for
8.6 GB and 12.9 GB of coefficients, which no limit near this size holds.
Measured at `--as=1500000000`, `2500000000` and `4000000000`, the control is
72 MB at all three.

### Why an rlimit, and not a service-manager scope

The lead's first measurement, 2026-10-09, capped the probe with a
user-session memory scope at 1.5 GB, and the harness lane's first commit
(`8f10bae`) reproduced the table under the same scope. Two things were
wrong with that for files under `scripts/`:

- `scripts/check-marketplace-capabilities.py` reproduces the marketplace's
  security baseline over every tracked `.sh`/`.py`/`.js`/`.qml` file, and
  its service-management rule matches the scope tool's name wherever it
  appears -- a comment and a README line included -- with no allowlist by
  design. The first commit carried six such lines and turned that gate red,
  unnoticed, because the gate had been run over an untracked tree (the
  scanner enumerates `git ls-files`).
- A kill is a worse answer than a refusal. Under the scope the two
  65500x65500 progressive rows ended in SIGKILL at the cap with the figure
  unmeasured; under RLIMIT_AS the allocator refuses the request, Qt reports
  `Image.Error`, and the probe exits 1 at a measured peak.

Every other row reproduces to the megabyte under both mechanisms (the
figures measured earlier under the scope: 72 control, 840 for the 304-byte
bomb, 1,239 for the 555-byte one, 454 for the 176-byte baseline 65500, 347
for the honestly-huge valid 12000x12000). What changed is only the two rows
the scope could not measure.

## What was measured, on what

Qt 6.11.2 (`Qml Runtime 6.11.2`, qt6-declarative), `QT_QPA_PLATFORM=offscreen`,
Linux 7.2.5, 7.8 GB RAM, `vm.overcommit_memory=0`, util-linux `prlimit`.
Peak RSS is `ru_maxrss` of the qml process, in MB (KiB / 1024). The lead
measured the table first, on 2026-10-09, on files crafted by hand in the
lead's scratch directory, under a user-session memory scope; the harness
lane re-measured every row on 2026-10-11 on the files `make-corpus.py`
generates, under the scope, and then re-measured EVERY row again the same
day under the rlimit, with `run.sh`, in one run of 27 s: 37 rows judged,
0 DIFF. The JPEG fixtures are byte-identical to the lead's (checked with
`cmp`: the controls, the four 20000 bombs and the two 65500 progressive
bombs); the PNG, GIF and WEBP fixtures are not byte-identical (a different
deflate level, an unclever LZW, a filler body) and declare the same sizes,
which is the only thing the measurement depends on. The reviewer's four
shapes are rebuilt here from the same segment builders (the EXIF thumbnail is
a whole 176-byte baseline JPEG inside the APP1, where the reviewer's is a
375-byte 3-component one; the column and the GIF declare the same sizes).

One row was NOT generated: the valid 12000x12000 progressive JPEG (`ready
347`) is the lead's `valid-prog-12k.jpg`, 706,780 bytes, encoder-made,
passed to `run.sh --extra`. `make-corpus.py` cannot make a valid JPEG of
that size without an encoder, and says so; `--with-encoder` builds
`enc-prog-12000.jpg` with ImageMagick when it is installed, and the row
reads `absent` otherwise rather than being quietly skipped.

### The table (`run.sh --extra <valid-prog-12k.jpg>`, 2026-10-11, under the rlimit)

```
file                          size     bytes declares      outcome  peak_mb  wall_ms verdict
ctl-base-64.jpg                 44       176 64x64           ready       72      241 MATCH (expect ready<150)
ctl-prog-64.jpg                 44       304 64x64           ready       72      329 MATCH (expect ready<150)
ctl-prog-rgb-64.jpg             44       555 64x64           ready       72      203 MATCH (expect ready<150)
ctl-png-64.png                  44        84 64x64           ready       72      190 MATCH (expect ready<150)
ctl-gif-64.gif                  44      2355 64x64           ready       72      266 MATCH (expect ready<150)
ctl-webp-64.webp                44        58 64x64           error       72      231 MATCH (expect error<150)
good-512.png                    44       334 512x512         ready       72      257 MATCH (expect ready<150)
good-1920x1080.png              44      2090 1920x1080       ready       80      266 MATCH (expect ready<150)
edge-at-bound.jpg               44       304 4096x1024       ready       76      250 MATCH (expect ready<150)
edge-at-bound.png               44      4145 2048x2048       ready       92      263 MATCH (expect ready<150)
valid-prog-12k.jpg              44    706780 (extra)         ready      347      804 MATCH (expect ready>250)
enc-prog-12000.jpg              44         - -              absent
bomb-base-20000.jpg             44       176 20000x20000     ready      106      403 MATCH (expect ready<150)
bomb-base-65500.jpg             44       176 65500x65500     ready      454     1899 MATCH (expect ready>300)
bomb-prog-20000.jpg             44       304 20000x20000     ready      839     1301 MATCH (expect ready>700)
bomb-prog-20000.jpg            223       304 20000x20000     ready      839     1318 MATCH (expect ready>700)
bomb-prog-rgb-20000.jpg         44       555 20000x20000     ready     1239     1662 MATCH (expect ready>1000)
bomb-prog-65500.jpg             44       304 65500x65500     error      325      629 MATCH (expect error>200)
bomb-prog-rgb-65500.jpg         44       555 65500x65500     error       72      229 MATCH (expect error<150)
bomb-png-20000.png              44        84 20000x20000     error       71      220 MATCH (expect error<150)
bomb-png-65500.png              44        84 65500x65500     error       71      240 MATCH (expect error<150)
valid-png-20000.png             44     48685 20000x20000     error       71      221 MATCH (expect error<150)
valid-png-65500.png             44    521403 65500x65500     error       71      256 MATCH (expect error<150)
bomb-gif-20000.gif              44      2355 20000x20000     error       71      227 MATCH (expect error<150)
bomb-gif-65500.gif              44      2355 65500x65500     error       71      258 MATCH (expect error<150)
valid-gif-canvas-20000.gif      44      2355 20000x20000     error       71      216 MATCH (expect error<150)
valid-gif-canvas-65500.gif      44      2355 65500x65500     error       71      261 MATCH (expect error<150)
bomb-webp-16383.webp            44        58 16383x16383     error       71      221 MATCH (expect error<150)
ctl-exif-thumb-64.jpg           44       362 64x64           ready       71      217 MATCH (expect ready<150)
bomb-exif-thumb-20000.jpg       44       490 20000x20000     ready      839     1394 MATCH (expect ready>700)
bomb-column-64x65535.jpg        44       176 64x65535        error       71      235 MATCH (expect error<150)
bomb-gif-second-frame-65500.gif    44      4690 65500x65500     ready       71      242 MATCH (expect ready<150)
```

`ctl-webp-64.webp` reads `error` by design: `make-corpus.py` builds a WEBP
CONTAINER whose VP8 frame header declares the size over a body that is not a
keyframe, which is enough to drive a header parser and not enough to reach
`Image.Ready`. No WEBP here is a sink positive control; the PNG is.

Read against the lead's table: 72 control (lead 72); 840 for the 304-byte
progressive 20000x20000 (lead 840); 1,239 for the 555-byte 3-component one
(lead 1,239); 454 for the 176-byte baseline 65500x65500 (lead 455); 347 for
the honestly-huge valid 12000x12000 (lead 348). The two 65500 progressive
rows are the ones the rlimit changes: the grayscale one is REFUSED by the
allocator 325 MB in (Qt reports `Image.Error`, rc 1, 0.6 s), and the
3-component one is refused before anything is touched (72 MB, control
memory), where the user-session memory scope measured earlier SIGKILLed
both at 1,553 MB resident, 1.3-1.5 s in. The 65500 figure is still NOT
measured and is not claimed -- what is measured is that the request is one
no limit near this size can hold, and that under this limit it is refused
rather than killed. PNG, GIF and WEBP refuse at control memory as rewritten
headers AND as honestly huge valid files, because their handlers decode
full size and hand Qt's allocation limit the real number. JPEG is the only
one of the four the decoder can scale, and that is exactly why it is the
only one exposed.

The reviewer's shapes, at the sink: the EXIF-thumbnail bomb costs the same
839 MB as the plain 304-byte bomb -- the thumbnail buys the attacker
nothing at the sink and everything at a naive header reader; the 64x65535
column is refused by Qt at control memory; and the two-frame GIF reaches
`Image.Ready` at control memory because Qt decodes the first frame only.
That last row is why the helper walks every frame rather than trusting
the sink's behaviour: whether a Qt that decoded the second frame would
clip it to the canvas is unmeasured, and R4 makes unproven a refusal.

The wall tile (`sourceSize` 223) costs the same 839 MB as the row slot on
the same file: the bomb is the coefficient buffer, not the output.

### The `QT_IMAGEIO_MAXALLOC` bracket (`bomb-prog-20000.jpg`, sourceSize 44)

```
MiB       outcome  peak_mb
5           error       72
7           error       72
10          error       72
20          error       72
26          ready      839
30          ready      839
```

and the Qt 6 default of 256 MiB is the `ready 839` row above. The threshold
sits between 20 and 26 MiB. `ceil(20000 / 8)` is 2500, and 2500 x 2500 x 4 is
23.8 MiB: the limit is compared against the image already divided by
libjpeg's largest scale denominator, 8, which `sourceSize` lets the decoder
use. The format's own maximum dimension is 65535; `ceil(65535 / 8)` is 8192,
and 8192 x 8192 x 4 is 268,435,456 bytes, which is exactly 256 MiB -- the
default limit, to the byte. No JPEG the format can express can exceed Qt's
default allocation limit on this path. The option added to keep the decode
cheap is the option that disarms the only bound Qt has.

## Running it

```
scripts/dev-harness/spikes/logo-decode-bomb/run.sh                 # 32 rows + the bracket, ~30 s
scripts/dev-harness/spikes/logo-decode-bomb/run.sh --only bomb-prog-20000.jpg,ctl-prog-64.jpg --no-bracket
scripts/dev-harness/spikes/logo-decode-bomb/run.sh --extra <an encoder-made jpeg>
python3 scripts/dev-harness/spikes/logo-decode-bomb/make-corpus.py --list
```

`run.sh` exits 0 on 0 DIFF, 1 otherwise, 77 when the machine cannot run it
(python3, util-linux `prlimit` or the qml binary missing, or the rlimit
refused). It decodes bombs on purpose, under the limit: it is for a human at
a terminal, never for the gate. The gate runs `logo-scenario.sh check-tree`,
which builds its corpus from the same generator, runs the shipping helper at
it, and decodes only what the helper announced -- on the fixed tree, the
good logo and nothing else.
