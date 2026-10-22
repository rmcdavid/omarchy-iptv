# epg11-store: the D-EPG-11 measurement, re-runnable

What the long-running shell holds from `epg-now.json`, and what it costs to
hold it the new way. Until D-EPG-11 the service `JSON.parse`d the file whole
and kept `doc.channels` by reference: about 7 KiB of resident memory a
channel, rebuilt on every 5-minute recompute. The store
(`Model.parseEpgNowStore`) keeps the file's text and a null-prototype index
of `[offset, length]` into it, and a row parses ONE entry when it asks
(`Model.epgEntry`). This directory holds the probe that measured both
shapes on V4, so "measured" means "re-runnable" and not "remembered", the
way `logo-decode-bomb/` and `text-autotext-img/` do.

The ruling is R31a-h (D-EPG-11, 2026-10-22); the block it lives in is
`docs/ARCHITECTURE.md` section 8, item 16 (dev branch), the D-EPG-7 entry
on what the shell holds from the guide data, which carries the figures
below. Nothing here ships: `scripts/` is not on the
release allowlist, and `scripts/release.py check` proves the list whole.

## The files

| file | what it is |
|---|---|
| `epg11-probe.qml` | the SINK, as the shell has it: an XHR over `file://` reads the file into a JS string (the `FileView` the service uses holds the text the same way, bytes plus a UTF-16 QString), then one of five modes holds or times a state over it. `text` holds the string alone; `parse` holds it AND `Model.parseEpgNow(text).channels`, what `Service.qml` held before this round; `store` holds it AND `Model.parseEpgNowStore(text)`; `time` holds nothing and times both parsers over the file `reps` times; `tick` holds the store and runs `reps` 30 s ticks of 13 rows (`epgEntry` + `epgFields`) and one panel (`programmeDetail`). A hold mode prints `PROBE HOLD` once the state is built and keeps it for `holdMs` so the runner can sample RSS from outside |
| `run-probe.py` | runs the probe ONCE under `prlimit --as=4000000000` around the qml process alone, with a copy of a tree's `Model.mjs` and `model/` in a temporary directory (the tree is never written into, and `--tree` takes a `git archive` export of another commit for a baseline). Samples `/proc/<pid>/status` every 50 ms; prints the probe's lines and one `RESULT` line: `steady_rss_kb` is the median VmRSS while the state is held, `peak_sample_kb` the largest sample, `ru_maxrss_kb` the child's rusage. Exit 0 on the probe's 0, 1 otherwise, 77 when the machine cannot run it |
| `add-detail.py` | the post-pass that gives every programme of a `gen-playlist.py` XMLTV an ordinary 200-character description, a category and an episode number, so `now` AND `next` carry the three detail fields `EPG_DETAIL_FIELDS` names. Deterministic: the text is a function of the programme's position. `gen-playlist.py`'s own XMLTV carries a sparse `<desc>` and no category or episode, which is why this exists |

## The inputs, and how they are generated

Every file the probe reads was written by the SHIPPING HELPER, never by
hand. For N in 1000, 2000, 4000, 10000, with one clock for the generator
and the helper so two runs write the same bytes (`CLOCK=1792650028` is the
one used on 2026-10-22; any epoch second works):

```
python3 scripts/gen-playlist.py --channels N --epg-ids 1.0 --seed 1 --now $CLOCK \
    --out IN/gN.m3u --xmltv IN/gN.xml                       # add --hours 2 at 10000, see below
python3 scripts/dev-harness/spikes/epg11-store/add-detail.py IN/gN.xml IN/dN.xml
mkdir -p IN/cN
python3 bin/omarchy-iptv playlist --url IN/gN.m3u --cache-dir IN/cN
python3 bin/omarchy-iptv epg --url IN/dN.xml --cache-dir IN/cN --now $CLOCK
```

`IN/cN/epg-now.json` is the file. `--epg-ids 1.0` gives every channel a
tvg-id so the guide covers the whole playlist (the default 0.6 would leave
four rows in ten without data, and the measurement is of rows that have
some); `--seed 1` is the generator's default and is stated so the bytes
are reproducible (the 1,000-channel file written this way on 2026-10-22 is
sha256 `97a84250fa3a8e288f3f637f3c0811f1615a05eaf3ab76fb89980c4061faad8e`,
635,912 bytes, 975 lines, 973 entries; the generator duplicates about 3% of
ids as HD/SD twins, which is why N channels give fewer entries). With
detail on every programme and the default 12 h half-window, the 10,000
channel XMLTV is over the helper's 64 MB input cap (`MAX_SOURCE_BYTES`)
and is refused, so the 10k guide is generated at `--hours 2` (44,393
programmes, 19.9 MB); `epg-now.json` holds now/next only, so its size and
the shell's holding depend on the channel count and not on the window,
and the 10k figures stand on the same footing as the others. A
titles-only file (the generator's XMLTV without the post-pass) is about 190
bytes a channel; the detail-bearing one about 650.

The one-channel baseline file is the 1,000-channel file's header line, its
first fragment line (without the trailing comma) and `}}`.

## Running it

```
python3 scripts/dev-harness/spikes/epg11-store/run-probe.py store IN/c1000/epg-now.json
python3 scripts/dev-harness/spikes/epg11-store/run-probe.py text  IN/c10000/epg-now.json
python3 scripts/dev-harness/spikes/epg11-store/run-probe.py parse IN/c10000/epg-now.json
python3 scripts/dev-harness/spikes/epg11-store/run-probe.py time  IN/c10000/epg-now.json --reps 10
python3 scripts/dev-harness/spikes/epg11-store/run-probe.py tick  IN/c10000/epg-now.json --reps 2000 --now-sec $CLOCK
python3 scripts/dev-harness/spikes/epg11-store/run-probe.py parse IN/c4000/epg-now.json --tree /path/to/an/export/of/2bb05c6
```

A per-channel figure is a SLOPE between two sizes (the 2,000 and 4,000
channel files, or 4,000 and 10,000), not one file over the baseline: Qt
offscreen's own footprint is about 74 MiB and moves by a megabyte between
runs. Timing modes print milliseconds per call and microseconds per tick
from `Date.now()`, so `reps` is chosen to be readable in whole
milliseconds. It is for a human at a terminal, never for the gate: a hold
run takes about three seconds, a 2,000-tick run about four.

## What was measured, on what (2026-10-22)

Qt 6.11.2 (`Qml Runtime 6.11.2`, qt6-declarative), `QT_QPA_PLATFORM=offscreen`,
Linux 7.2.5, util-linux `prlimit`, the one-minute load average 2.7-2.9 for
the timing runs. Resident figures are `steady_rss_kb` of the `RESULT` line;
the tree under test is lane-epg11 at `9e58749` (the same model as the
merged code) and the base is a `git archive 2bb05c6` export. Files as
above, detail on every programme.

Per channel, as the slope between the 2,000 and 4,000 channel files, two
passes each:

| held | KiB a channel | at 10,000 channels (9,708 entries) |
|---|---|---|
| text alone | 1.83-1.91 | 93.0 MiB |
| text + the parsed map (`parseEpgNow`, what the service held) | 7.13-7.18 | 146.8 MiB |
| text + the store (`parseEpgNowStore`) | 2.50-2.56 | 99.9 MiB |
| (empty baseline) | | 74.3 MiB |

so 7.2-7.4 KiB a channel for the old shape at 10,000 against about 2.6 for
the store, the index about 0.7 KiB of it; +70 MiB against +25 over the
baseline. The first cut of the walker sliced a `line` string per channel
and read 3.7-4.0 KiB a channel: the slices' UTF-16 copies sat in the held
RSS, and walking by offset is what brought it to 2.5. The round's
performance lens reproduced every slope within 0.2 KiB on its own inputs
and probe (text 1.76-1.90, parse 7.16-7.40, store 2.42-2.67).

Time, at 10,000 channels:

| what | base (parsed map) | store |
|---|---|---|
| `applyEpgNow`'s parse, ms a call (10 calls, three passes) | 188-212 (`parseEpgNow`) | 26-30 (`parseEpgNowStore`: the lane 25.5-27.7, the lens 26.2-29.6) |
| the 30 s tick: 13 rows + the panel, us a tick (2,000 ticks, three passes) | 270-280 | 575-585 |
| a scroll realising every one of the 9,708 rows once, ms | 134-145 | 345-348 |

The tick is 2.1x the base's, about 0.3 ms moved onto each 30 s tick. Each
`epgEntry` is a JSON.parse of one line of about 650 bytes and materialises
the ~7 KiB of objects the old map held for that entry plus a UTF-16 slice,
so a tick is about 110-120 KiB of garbage: measured NOT retained. The held
RSS after 200 / 500 / 2,000 / 8,000 ticks (gc before the hold) read 117 /
118 / 252 / 216 MiB, non-monotonic, and the old map path reaches the same
248 MiB after 8,000 ticks of its own, so that is V4's collector high-water
and not the store (the performance lens's `rev-perf/timing.log`). The
base's tick and the scroll are the lens's figures; the lane measured the
store's tick only.

The whole-shell budget (rule 7) with a 10,000-channel guide held is
`scripts/dev-harness/open-scenario.sh live` under `OPEN_EPG=1`, in the
nested headless cage on a private bus, not this probe: warm open medians
36-54 ms on both trees across six runs, the cold open over 150 ms on both
(the known D-PERF-2 shape) and not moved by this round.

## Re-run check

One run from the committed tree (lane-epg11-f at `a8dafbd`, 2026-10-22,
load average 1.43), `store` mode over the 1,000-channel file above
(sha256 `97a84250...`, regenerated by the commands in this README and
byte-identical to the lane's), so a later run has a figure to read against:

```
  qml: PROBE mode=store chars=635912 hasStore=true
  qml: PROBE store_ms=4 entries=973 legacy=false sharesText=true
  qml: PROBE HOLD entries=973
  qml: PROBE DONE
RESULT tree=wt-epg11-f mode=store file=epg-now.json rc=0 steady_rss_kb=77772 peak_sample_kb=77772 ru_maxrss_kb=78152 held_samples=53 wall_ms=3828
```

The lane's two passes the same day read 77,860 and 78,152 KiB steady for
the same file (its `rss-matrix.log`), the text alone 76,092-76,160, the
parsed map 80,472-80,652, over a one-channel baseline of 74,260-74,544. A
re-run that reads within a few megabytes of 77.8 MiB steady, 973 entries,
`legacy=false` and `sharesText=true` is the same measurement; a store that
no longer shares the V4 string, or an entry count that moves, is a change
worth a look before the figures above are repeated.
