# first-open: where the first guide open's ~440 ms goes (D-PERF-2)

2026-10-24, on `dev` a2ce3ab, in the nested headless cage on a private
D-Bus, 4 cores, Quickshell 0.3.1, Qt 6.11.2, mesa 26.2.2, cage 0.3.1. A
MEASUREMENT spike: no product file changed; the two probes beside this file
are dev-only and ship nothing (`release.py check` green on the branch).

The owner's question: the first guide open of a shell session costs about
440 ms more than every later one (D-PERF-2: cold 548 / 534 ms against warm
33 / 31 at 10,000 channels; a 40-channel control 450 / 440). WHERE does it
go, so the owner can choose between a hidden pre-warm, a cheaper first show,
or accepting it with numbers.

## The answer in one paragraph

Measured, not argued: of the ~450 ms between the summon's return and the
first swapped frame at 10,000 channels in the cage, about **240 ms is the
cage's software renderer (llvmpipe) JIT-compiling shaders in the first
`eglSwapBuffers`, into a shader cache the dev harness WIPES at every shell
start** -- a property of the measurement rig, not of the plugin, and not a
cost the owner's desktop pays (its mesa and Quickshell pipeline caches are
persistent and its GPU is Intel iris, not llvmpipe). With the caches kept,
the whole cold open at 10,000 channels is **308 ms (298-318, n=5)**, against
540 (501-582, n=9) with them wiped, and it decomposes as: the guide's own
synchronous summon, 88 ms (channel-dependent: 26 at 40 channels, 2 at none);
the per-window floor any Quickshell window pays on its first show, about
140 ms (QRhi and GL context ~45, first frame ~55-70, window creation and map
~50), measured on a bare window with one Rectangle; and 40-60 ms the
instruments do not attribute. Fonts and glyphs are not where it goes: the
distance-field atlas for the guide's whole glyph set is 7-8 ms. Of the three
levers, the only one that moves the first VISIBLE open is a hidden pre-warm
of the guide's OWN window with its content DRAWN (opacity 0.01 in the probe;
opacity 0 does not compile the text material and the next visible show
stays cold): the next show is then 21-42 ms instead of 166-411, for the cost
of one cold show during shell start-up and the memory a mapped window keeps.
Destroying and re-creating the window would cost 118 ms a time even warm, so
what the plugin does today (one window object, `visible` toggled) is right.
Recommendation: (1) correct the record first -- D-PERF-2's "about 440 ms"
is about 210 ms in the cage once the caches are warm, and UNMEASURED on the
desktop GPU; the harness should keep or seed the shader cache across cold
shells so a cold figure means what the desktop pays; (2) if the owner wants
the first open inside rule 7's 150 ms, the lever that works is the drawn
hidden pre-warm of the guide's window at shell start, which needs a product
change to keep the pre-warm from taking keyboard focus on the overlay layer;
(3) otherwise accept it with numbers: about 300 ms once per shell session at
10,000 channels, of which about 90 is the guide's and the rest is Qt's and
the compositor's.

## Method

Everything ran under `scripts/dev-harness/private-bus.sh` in a headless
`cage` (`WLR_BACKENDS=headless WLR_RENDERER=pixman`), this script's own
cage, started and stopped by the pids it recorded; the user's shell (pid
2062603) was the only `quickshell` left after every run. Timing figures are
`Date.now()` deltas inside the QML process, so the clocks are the open
instrument's own (`shell.qml` `openAsync`); every figure carries the
one-minute load average beside it. All runs had `QSG_INFO=1` and
`QT_LOGGING_RULES="qt.scenegraph.time.*=true;qt.scenegraph.general=true;qt.opengl.diskcache=true;qt.rhi.general=true"`,
so the scene graph's own split of each frame (sync / render / swap), the
GUI thread's wait on the render thread (`blockedForSync`), the renderer, the
pipeline-cache seeding and the glyph-cache timings are in the transcripts.

Transcripts (rule 7; 0600 under a 0700 directory, on the runtime tmpfs):

| run | transcript | what |
|---|---|---|
| reference | `/run/user/1000/omarchy-iptv-open/transcripts/open-20261024-221459-776712.out` | `open-scenario.sh live`, default arms, 33 passed / 0 failed, load 1.74 at start |
| probe + harness | `/run/user/1000/omarchy-iptv-first-open/transcripts/first-open-20261024-222940-835707.out` | `run.sh --arm all --reps 3`: the 14 probe processes and the first 9 harness shells (the two `--keep` shells of this run inherited the empty playlist's cache and are void) |
| harness | `/run/user/1000/omarchy-iptv-first-open/transcripts/first-open-20261024-223831-867239.out` | `run.sh --arm harness --reps 3`, keep shells placed after a 10k shell |
| harness | `/run/user/1000/omarchy-iptv-first-open/transcripts/first-open-20261024-224350-877696.out` | the same again, three keep shells |

Two rigs:

- `floor.qml`, a bare Quickshell config driven over IPC by `run.sh`:
  a `FloatingWindow` 1280x720 with one `Rectangle` (`rect`), the same with
  one `Text` in the guide's font alias `monospace` (`text`), the same with
  the guide's whole Nerd Font glyph set at the two icon sizes and an ASCII
  sample at every text size the guide uses (`glyphs`), and a `PanelWindow`
  (`panel`). A show is `visible = true` to the first `frameSwapped` of the
  window's `QQuickWindow`, then 500 ms of counting frames. Windows are
  created before they are shown, as the guide's is; `destroy` + `create`
  re-creates one; `opacity` sets the content's opacity for the pre-warm
  lever. RSS is read from `/proc/<pid>/status` between steps. The probe gets
  a shader-cache directory of its own (`XDG_CACHE_HOME`), wiped before the
  processes labelled fresh and kept for the rest.
- the dev harness (`scripts/dev-harness/run.sh --detach --window floating`)
  with the REAL `Service.qml` and `Guide.qml` over `gen-playlist.py`
  fixtures: one cold `openAsync list` and one warm per shell, the drawn-set
  instrument's `summonMs`, the `at` of its first sampled frame and its
  `realisedMs`, RSS before and after; at 10,000 channels (400 groups, seed
  1), at 40, and over a header-only `#EXTM3U` (no row is realised, the
  instrument ends by time, its first frame is what is read). The harness
  wipes `$SCRATCH/cache` at every start unless `--keep`, and
  `XDG_CACHE_HOME` points there, so a plain shell starts with COLD mesa and
  Qt pipeline caches; the `--keep` shells follow a 10k shell with its cache.

What `swap` means here. The cage's compositor renders with pixman and the
client's EGL finds no GPU (`MESA-EGL: failed to get driver name for fd -1`),
so Qt's QRhi runs on `llvmpipe (LLVM 22.1.8, 256 bits)`. llvmpipe
rasterises and JIT-compiles its shader variants lazily, at the flush inside
`eglSwapBuffers`, so the renderloop's `swap=` figure is where both the
compile and the draw land. That is the cage; the owner's desktop is Intel
HD Graphics 520 under iris, where a frame's cost is on the GPU and the
shader compile is cached in `~/.cache/mesa_shader_cache` (788 files,
6.3 MB on this machine) and `~/.cache/quickshell/qtpipelinecache-*/`
(present, touched 2026-10-23). Nothing here measured the desktop: this
lane had no display.

## Figures

Every figure is milliseconds, median (min-max), n, with the one-minute load
average range over the samples. "First frame" is the time to the first
swapped frame; for the guide it equals `realisedMs` on every settled open
but one (keep-1 of the third run: first frame 318, realised 362 -- its first
frame drew the screen in part and the second completed it).

### M2 The guide, cold, decomposed (harness arm, floating window, list view)

| case | cold first frame | summon (sync) | warm first frame | RSS over the cold open | load |
|---|---|---|---|---|---|
| 10,000 ch, caches wiped (the D-PERF-2 condition) | **540 (501-582) n=9** | 88 (66-99) | 39 (37-47) | +85 MB | 1.7-3.1 |
| 10,000 ch, caches KEPT from the previous shell | **308 (298-318) n=5** | 88 (87-98) | 34 (31-37) | +85 MB | 2.4-3.4 |
| 40 ch, caches wiped | 470 (460-478) n=9 | 26 (25-30) | 25 (20-30) | +91 MB | 2.7-3.4 |
| 0 ch (header-only M3U), caches wiped | 384 (356-389) n=9 | 2 (1-2) | 24 (20-31) | +72 MB | 3.0-4.8 (the instrument's own 6 s frame loops) |
| reference `open-scenario.sh live`, 10k | list 539 (504-568) n=3, wall 516 (502-549) n=3 | 88 / 76 | 34 / 36 | - | 1.7 at start |

The reference run's cold traces show the shape: the FIRST frame the
instrument sees is at +504 ms (list) / +516 (wall) with the screen already
drawn (10/13, 16/18). Nothing is painted and then filled in; the time goes
before any frame swaps.

The render thread's first frame of the guide's window, from the scene
graph's own timing (one shell each; the others read the same within 10 ms):

| case | `blockedForSync` (GUI thread) | first frame: total = sync + render + swap |
|---|---|---|
| 10k, caches wiped | 361 ms | 311 = 11 + 17 + 283 |
| 10k, caches kept | 111 / 118 ms | 71 = 10 + 13 + 47; 74 = 11 + 14 + 48 |
| 40 ch, wiped | 358 ms | 309 = 12 + 17 + 279 |
| 0 ch, wiped | 315 ms | 265 = 9 + 8 + 247 |

`blockedForSync` minus the frame is the QRhi and GL context creation for the
window: 40-50 ms in every case. Glyphs on the guide's first frame: 82 + 57
distance-field glyphs prepared in 7-8 ms (rendering 3-5, upload 3-4). The
bar's `PanelWindow` is created too (no layer shell here, so it never maps)
and costs its own QRhi at shell start, 51-65 ms of `blockedForSync`, so
the guide's window is the process's SECOND QRhi, as it is on the desktop.

### M1 The floor (probe arm, `floor.qml`)

| what | first frame | n | load |
|---|---|---|---|
| `rect`, first window of the process, caches FRESH | 306 | 1 (P1) | 2.30 |
| `rect`, first window of the process, caches kept | 160, 156 | 2 (P2, P3) | 2.0-2.3 |
| `rect`, shown again (warm) | 17 (17-17) | 3 | 2.0-2.3 |
| `text` as the FIRST window, caches fresh / kept | 389 / 155, 173 | 1 / 2 (T1 / T2, T3) | 2.0 |
| `glyphs` as the FIRST window, caches fresh / kept | 402 / 164 | 1 / 1 (G1 / G2) | 2.1-2.3 |
| `text` as the SECOND window (after rect), fresh / kept | 234 / 139, 137 | 1 / 2 | 2.0-2.3 |
| `glyphs` as the THIRD window | 137 (136-145) | 3 | 2.0-2.3 |
| `text` DESTROYED and re-created, shown again | 118 (117-119) | 3 | 2.0-2.3 |
| `panel` (`PanelWindow`, no layer shell in the cage) | 83 (70-84), one frame, never mapped | 3 | 2.0-2.3 |

The render thread's first frame of the bare rectangle: caches fresh
`161 = 0 + 9 + 151`, GUI blocked 218; caches kept `54 = 0 + 0 + 53`, GUI
blocked 109. So the floor of a first window with warm caches is about 160:
~55 QRhi and context, ~54 first frame (the swap is llvmpipe drawing
1280x720; steady-state idle frames read `swap=31-35` throughout), ~50 the
window's creation and the compositor's configure and map. A second window in
the same process pays ~140 (its own QRhi and first frame; the context's
one-time work is not repeated). The pipeline cache: the second process
reads `Seeded pipeline cache with 1-2 program binaries` from
`quickshell/qtpipelinecache-x86_64-little_endian-lp64/qqpc_opengl` (7-20
KB); mesa's cache holds 23 files, 2.1 MB after one process.

RSS (llvmpipe, so the numbers are the cage's, not the desktop's): the idle
probe process 193-199 MB; +120 MB on the first shown window; +70-80 MB on
each further 1280x720 window shown; hiding returns none of it. The harness
shell: 435 MB with 10,000 channels held, +85 MB over the cold open, +1-3 MB
over a warm one.

### M3 Fonts and glyphs

Small. The whole guide glyph set at 14 and 11 px plus ASCII at 10-28 px is
89 distance-field glyphs, prepared in 4-6 ms (rendering 2-3, upload 2-3) on
every run; the guide's own first frame prepares 82 + 57 in 7-8 ms. What the
`text` and `glyphs` windows add over the bare rectangle is the TEXT
MATERIAL's shaders, not the glyphs: as the first window with fresh caches
389-402 against 306 (+80-100, llvmpipe compiling the distance-field
material), with kept caches 155-173 against 156-160 (+0-15). Font loading
itself (fontconfig alias, FreeType) is inside those few milliseconds.

### M4 The levers, measured

| lever | figure | against | cost |
|---|---|---|---|
| (a) hidden pre-warm, SAME window, content drawn at opacity 0.01 (W1) | next visible show 32 (21-42) n=3 | the cold first show 166-411 | the cold show itself at shell start (166-175 kept-cache, 411 fresh, on the render thread); the window's memory stays (+120 MB in the cage, llvmpipe); one mapped frame on the overlay layer, which on Hyprland has exclusive keyboard focus unless the pre-warm is given `keyboardFocus: None`, and `layersIn` animates it (product change) |
| (a') hidden pre-warm at opacity 0 (W0) | next visible show 161 with caches fresh; 36-37 kept (n=3: 161, 36, 37) | 166-264 cold | at opacity 0 the scene graph culls the content: the text material is not compiled, so with cold caches the visible show pays it; only a DRAWN pre-warm warms |
| (a'') pre-warm of a DIFFERENT window | the `text` window after a `glyphs` pre-warm 125-131 (119-153) n=6 | 137-139 without | the per-window QRhi and first frame do not transfer; the pre-warm must be the guide's own window object |
| (b) shader disk cache | 10k cold 308 (298-318) n=5 with the caches kept against 540 (501-582) n=9 wiped: -232 ms; probe rect 156-160 against 306 | - | nothing for the plugin: the desktop's caches persist (`~/.cache/mesa_shader_cache`, `~/.cache/quickshell/qtpipelinecache-*`); the HARNESS wipes them at every start, so every cold figure on record (D-PERF-2's included) was taken with cold caches |
| (c) keep the window object, toggle `visible` (what Guide.qml does: the Loader builds one window at completion, `visible: root.opened`, `keepLoaded` on) | warm toggle 17 (probe), 34-39 (guide at 10k) | destroy + re-create 118 (117-119) n=3 | keep as is; a re-created window pays a new QRhi and first frame every time |

## Attribution table

The cage's cold 10,000-channel open, median 540 ms with the caches wiped
(the condition every recorded figure was taken under) and 308 with them
kept:

| part | wiped | kept | how it was read |
|---|---|---|---|
| the guide's own synchronous summon (`rebuildDisplay`, both channel views' delegates) | 88 | 88 | `summonMs`; 26 at 40 channels, 2 at none |
| llvmpipe shader JIT in the first swap | ~240 | 0 | first-frame `swap` 283 against 47-48 |
| QRhi + GL context for the guide window | ~50 | ~42 | `blockedForSync` minus the frame |
| the first frame with warm shaders (sync + render + swap; glyph atlas 7-8 inside it) | ~72 | ~72 | the kept shells' first frame; the bare rectangle's is 54 |
| the floor's window creation, configure and map | ~50 | ~50 | probe rect kept: 158 total minus 109 blocked |
| unexplained | ~40 | ~56 | the remainder: the instrument's IPC and cross-thread signal latency, polish, the harness's own sampling |
| of which fonts and glyphs | 7-8 | 7-8 | `qt.scenegraph.time.glyph` |

So the floor (a bare second window in a warm process, ~140 with warm
caches) explains about 140 of the kept 308; the guide adds its 88 ms summon,
about 20 ms of a heavier first frame, and ~56 unattributed. With the caches
wiped the floor itself is ~290 of the 540, and the extra is the JIT.

## What this spike hands the lead (no defect ids: a spike files none)

- The cage's cold open figure is about 45 per cent a software-renderer
  JIT into a cache the harness wipes per start. A cold figure that means
  what the desktop pays needs `open-scenario.sh`'s shell arm to keep or seed
  `$SCRATCH/cache` across its cold shells (or to copy the previous shell's
  `mesa_shader_cache` and `quickshell/qtpipelinecache-*` in). The D-PERF-2
  row's "about 440 ms ... the window's first show" is about 210 in the cage
  with warm caches, and the desktop figure is UNMEASURED by any instrument
  (the 2026-10-23 corroboration is two frames per open, coarse to 450 ms).
- The empty-view control runs at load 3-4.8 because the instrument never
  settles over 0 rows and pokes frames for 6 s; its figures carry that load.
- `qs ipc call <target> show ...` and `hide` are parsed as `qs ipc`
  subcommands, so an IpcHandler function cannot be named either; the probe's
  verbs are `present` / `dismiss`.

## Re-running

    scripts/dev-harness/private-bus.sh /run/user/1000/fo-bus 3000 \
        scripts/dev-harness/spikes/first-open/run.sh --arm all --reps 3

The bus directory must be short (a unix socket path; a scratchpad path was
"Socket name too long"). `--arm probe` and `--arm harness` run one arm.
Nothing here grades: read the transcript it prints first.
