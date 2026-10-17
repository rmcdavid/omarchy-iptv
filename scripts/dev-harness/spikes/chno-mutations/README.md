# chno-mutations: what the repaired chno checks were seen red against

F-HARNESS-21 (`chno-scenario.sh` red 6-8 checks on every tree) and
F-HARNESS-22 (`chno-entry-scenario.sh` N9 red by chance) were repaired on
2026-10-15 (lane-clean-h). Neither scenario was wrong about the plugin; each
was reading something that was not what its check named:

| cause | checks it reddened | repair |
|---|---|---|
| the cache path from before Sources, `cache/omarchy-iptv/channels.json` | "playlist order is the shipped order", "there is a cache to compare against", "the flip rewrote no cache" | the directory `ipc activeCache` answers, asserted to lie under `cache/omarchy-iptv/sources/`; the file's identity is inode, nanosecond mtime, size and hash, read after a bounded settle |
| `move -99` WRAPS (`moveCursorBy(delta, true)`): on 20 rows it is +1, so "the top" was row 1 | "number order puts the lowest number first" | `park_top` moves by minus the cursor index; the check asserts index 0 |
| every stream was DEAD (127.0.0.1:9): mpv exits about 1.4 s after a tune and the service clears nowPlaying on its own | chno: "it did not change what is playing" and the three N20 bar checks; chno-entry: N9, and N3/N4 under load (rule 15) | every row served by run.sh's fixture server (`qa_served_fixture`), the listener asserted to be this harness's (`qa_listener_owned`), a tuned stream asserted to HOLD for 3 s, and the what-is-playing checks compare the play token (id and play sequence) |

Rule 11 says every repaired check is seen red on code that carries the
failure it names. These are one-decision mutations, kept as patch files the
way `../key-mutations/` keeps its own. Never apply one to a working tree:
export, apply in the export, point the scenario at it.

| patch | what it breaks | red under the repaired instrument |
|---|---|---|
| `order-ignored.patch` | `orderChannels` (model/channels.mjs) ignores `channelOrder number` | chno: "number order puts the lowest number first" (`row 0: Harness Live`), 45/1 |
| `order-always-number.patch` | `orderChannels` ignores `channelOrder playlist` | chno: "playlist order is the shipped order" (`row 0: Sky News; cache[0]: Harness Live`), 45/1 |
| `flip-refetches.patch` | `onChannelOrderChanged` also re-fetches (Service.qml) | chno: "the flip rewrote no cache, so no helper ran" (new inode and hash), 45/1 |
| `unknown-plays.patch` | `tuneByNumber` tunes the last row before refusing an unknown number | chno: "it did not change what is playing" (`t:ru1 5 -> t:pl1 6`) and, following from it, the three N20 bar checks (the bar shows 1001), 42/4 |
| `bar-no-number.patch` | BarWidget never learns the playing number | chno: the three N20 bar checks, 43/3 |
| `bar-ignores-setting.patch` | BarWidget ignores `barShowChannelNumber` | chno: "barShowChannelNumber false drops it from the bar", 45/1 |
| `miss-plays-cursor.patch` | `commitNumberEntry` (Guide.qml) plays the row under the cursor on a miss with play | chno-entry: "N9: it says which number, and plays nothing new" (`t:skysports.uk 3 -> t:skyfootball.uk 4`) and "N9: and the guide is still open", 76/2 |
| `dead-fixture.patch` | INSTRUMENT mutation on `scripts/qa-lib.sh`: `qa_served_fixture` leaves the dead rows dead, the pre-repair fixture | chno: "a tuned channel stays playing" (`t:bbc1.uk 2->NONE 2`) and the three N20 bar checks, 42/4; chno-entry: "N3: and it stays playing" and N9 (`t:skysports.uk 3 -> NOFIELD`, the straddle itself), 76/2. Also driven on a copy of the library in `scripts/qa-lib-test.sh` |

All eight apply to the tree they are checked in with; `scripts/qa-lib-test.sh`
runs `git apply --check` on each, so a refactor that moves a hunk is a red
gate, not a silently stale patch.

The checks with no plugin decision behind them were seen red otherwise:
"there is a cache to compare against" by the unrepaired instrument on every
tree (it read the pre-Sources path); the listener check by `qa-lib-test.sh`
against a real listener named for another directory.

## Running one

```bash
cp=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-chno-mut.XXXXXX")
git archive HEAD | tar -x -C "$cp"
( cd "$cp" && git apply "$OLDPWD/scripts/dev-harness/spikes/chno-mutations/order-ignored.patch" )
OMARCHY_IPTV_PLUGIN_ROOT="$cp" scripts/dev-harness/chno-scenario.sh live   # under a nested cage, rule 6b
rm -rf "$cp"
```

For `dead-fixture.patch` run the export's OWN scenario
(`"$cp"/scripts/dev-harness/chno-scenario.sh`), since the patch is to the
instrument. Both scenarios need a nested headless cage on a private bus
(`../../private-bus.sh`) with `WLR_RENDERER=gles2`, because the served
streams are really played. The fixture server's port is run.sh's fixed
8765; a second harness holding it makes the listener check red rather than
letting a play from someone else's server count.

Measured 2026-10-15 on lane-clean-h, load average 6.7-15 (three lanes on four
cores); the per-run transcripts are named in the lane's report.
