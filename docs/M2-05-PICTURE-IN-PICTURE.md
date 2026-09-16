# Omarchy IPTV -- Picture in picture (M2-05)

Owner: Software Architect. Status: v0.1, governs M2-05, rank 3 of the M2 scope
decision (`docs/PRODUCT.md`), shipping in v0.3.0. Supersedes nothing; it fills
the slot `docs/PLAN-M2.md:112-120` reserves and it revises two lines of that
plan (section 9).

Companions, authoritative where this document is silent: `docs/PLAN-M2.md`
(lanes, gates, risks MR10 and MR12), `docs/ARCHITECTURE-PLAYER.md` (the
detached player; section 5 requirements 1-11 are the invariants this feature
must not break; section 12 rulings; section 13 amendment), `docs/UX.md`
(keyboard model in 3, microcopy in 6), `docs/M2-03-CHANNEL-NUMBERS.md` (the
list-mode key machine this feature extends), `docs/QA-PLAYER.md` (the PLY-
matrix a PiP pass must not regress), `CLAUDE.md` (constraints 2, 4, 6, 10-12
and "Never touch").

Conventions are the house ones: `Color.*` / `Style.*` tokens only, ASCII in
`.js` and `.py`, `[ASSUMPTION]` marks anything not proven on this machine, and
every such assumption appears in the GATE table in section 3 with the command
that settles it.

**Provenance.** Three read-only investigations were run (Hyprland surface,
Omarchy precedent, mpv/player surface) and each was attacked by a skeptic. This
design is built only on claims that survived both passes. Section 2.5 lists the
claims that did **not** survive, because two of them are attractive and would
otherwise be rebuilt from scratch by the first lane that reads the raw notes.

---

## 0. Decisions at a glance

| Topic | Decision |
|---|---|
| Mechanism | One-off Hyprland **dispatchers** addressed to a resolved window address, run as argv through a `Process`. No window rule, no `hyprctl keyword`, no `hyprctl eval`, no config file written. |
| Why not the player | Wayland denies a client both halves of PiP. `xdg_toplevel` has no placement request and no stacking request; mpv binds no layer shell. The player-side route is impossible, not merely awkward (2.1). |
| Player-side job | Exactly one: `auto-window-resize=no` while in PiP, so a channel change does not resize the box out from under the user. Written over the socket the shell already holds. |
| Addressing | `class == "omarchy-iptv"` **and** `pid == the player pid the service already knows**, resolved to `address:0x...`, validated against `/^0x[0-9a-f]{1,16}$/`. Never class alone (a foreign mpv already reproduces as a second client, `docs/QA-PLAYER.md:124`). |
| Dispatch spelling | Lua form first (`hyprctl dispatch "hl.dsp.window.float({ window = \"address:0x..\", action = \"toggle\" })"`), legacy form as the fallback, exactly the shape every Omarchy helper uses. Gate G-1 settles which one actually runs here. |
| State of record | The compositor. "Am I in PiP?" is answered by reading `floating`, `pinned` and the `iptv-pip` tag out of `hyprctl -j clients`, never by a remembered boolean. |
| Previous state | A snapshot `{at, size, floating, pinned, monitor, workspace}` stored **inside the player** at `user-data/omarchy-iptv-pip`. Its lifetime is exactly the window's lifetime; it survives a shell restart and a channel change, and it needs no new file and no state schema change. |
| Restore | Read live state, then act. If the window was tiled before PiP, unpin and unfloat and let the layout take it. If it was floating before PiP, unpin and put the rectangle back. Never a blind toggle. |
| Always on top | **Not on offer.** Hyprland 0.56.2 has no always-on-top rule and no such property. `pin` means "show on every workspace of this monitor"; `alter_zorder top` is a one-shot raise. Copy must not promise otherwise (2.4). |
| Key | `p` in list mode toggles PiP. `Shift+Enter` is **dropped** for v0.3.0 - the shipped `PanelKeyCatcher` swallows Return and emits no modifier, so it is unreachable (open question 1). |
| Other surfaces | New IPC verb `pip <on\|off\|toggle>`; an optional contrib keybinding. No new bar mouse gesture (open question 2). |
| Settings | `pipCorner` (string, `top-right`), `pipSizePercent` (integer 15-60, `30`), `pipMargin` (integer 0-200, `16`). All clamped in `Model.js`. |
| User configuration | **None required.** PiP needs nothing in `~/.config/hypr`. The only contrib line worth pasting is the pre-existing opacity rule, and its `size` line is fixed on the way past (section 7). |
| Helper | **Unchanged.** No Python lane in this feature. |
| Lanes | V1 `Model.js` + `Guide.qml` + `BarWidget.qml` + tests; V2 `Service.qml` + `manifest.json` + `contrib/` + `README.md` + harness. No shared file. A gate lane runs first and holds the display. |

---

## 1. What the user gets

You are watching a channel and you want to keep watching it while you work.
Press `p` in the guide. The player window becomes a small window in the corner
of your screen, it follows you between workspaces, and it stays out of the
tiling layout so your other windows lay themselves out as if it were not there.
Press `p` again and the player goes back to where it was.

That is the whole feature. Specifically:

- **What you press.** `p` in the guide's list mode. From anywhere else,
  `omarchy-shell io.github.rmcdavid.iptv pip toggle`, which you can bind to a
  key yourself (section 7).
- **What happens.** The player window floats, shrinks to a corner box sized
  from your monitor, and is pinned so it follows you across workspaces. The
  footer says `Picture in picture on`.
- **What puts it back.** `p` again, or `pip off`. The window returns to the
  layout it came from. Stopping playback also ends it, because the window it
  was applied to is gone.
- **What it does not do.** It does not keep the player above every other
  window. If you focus another floating window on top of it, that window is on
  top. Hyprland has no always-on-top for us to ask for. The honest description
  is "a small window that stays with you", not "always on top".
- **If nothing is playing.** `p` says `Nothing playing` and does nothing else.

Changing channel while in PiP keeps the box. Restarting the shell while in PiP
leaves the window exactly where it is - the compositor owns it, not us - and the
guide picks the state back up.

---

## 2. The mechanism decision

### 2.1 The player cannot do this alone, and it is not close

The brief asks us to prefer a player-side route if one exists, because it needs
no compositor cooperation and no user configuration. It does not exist. PiP is
two things - a window in a chosen place, and a window that stays visible - and
Wayland denies a client both.

- **Position.** `/usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml`
  gives `xdg_toplevel` exactly these requests: destroy, set_parent, set_title,
  set_app_id, show_window_menu, move, resize, set_max_size, set_min_size,
  set_maximized, unset_maximized, set_fullscreen, unset_fullscreen,
  set_minimized. `move` and `resize` are interactive drags that need an input
  serial. There is no programmatic placement. `man mpv`, `--geometry`, Note
  (Wayland): "Wayland does not allow a client to position itself so this option
  will only affect the window size." `--screen` carries the same note.
- **Stacking.** There is no stacking request in xdg-shell either.
  `strings -a /usr/bin/mpv | grep -c '^zwlr_layer_shell_v1$'` is **0**, while
  the same grep over `/usr/bin/Hyprland` is non-zero: the overlay layer exists
  on this compositor and mpv cannot reach it. mpv's only stay-on-top code paths
  are the X11 `_NET_WM_STATE_ABOVE` one and the Windows layered one.
- **And the failure is silent.** On a headless mpv 0.41.0 on this machine,
  `set_property ontop true`, `ontop-level "system"`, `on-all-workspaces true`,
  `title-bar false` and `show-in-taskbar false` **all** return
  `error: "success"` with the new value readable back, on a platform where the
  manual says three of them are macOS/Windows/X11 only. A PiP built on an IPC
  reply as proof of effect would pass its own tests and fail on the desktop.
  This is exactly the failure mode this project has twice paid for.
- **Embedding is closed too.** `--wid` documents X11, win32 and Android only.
  The libmpv render API would work on Wayland but requires the shell to own the
  player in-process, which contradicts the detached player, the private socket
  and the survive-a-shell-restart requirement. Recorded as rejected here so it
  is not re-proposed.

What the player **can** do is size its own surface (`--autofit`,
`--window-scale`), which is useless on its own because a tiled window's size
belongs to the compositor and a floating window's placement still does not
exist. And it can stop fighting us, which is the one player-side job we do take
(4.6).

### 2.2 Window rules cannot do it either, and we do not need them

A rule - whether pasted into `~/.config/hypr`, pushed with `hyprctl keyword`, or
registered at runtime with `hyprctl eval` + `hl.window_rule(...)` - is the wrong
instrument for a window that is already on screen. Registering a rule does not
restyle an existing window: `Desktop::Rule::CRuleEngine::updateAllRules()`
reaches only `propertiesChanged`, which reaches only `applyDynamicRule`. Beyond
that, each route fails a project constraint:

- A config file under `~/.config/hypr` is the user's, and `CLAUDE.md` "Never
  touch" makes it read-only for us.
- `~/.local/state/omarchy/toggles/hypr/` is loaded as executable Lua by
  `/usr/share/omarchy/default/hypr/toggles.lua:4-17`, is outside the three paths
  `CLAUDE.md` constraint 6 permits, and that directory's own comment records it
  as a past code-injection vector.
- `hyprctl keyword` is documented dead under a Lua config provider (`man
  hyprctl`: "This will not work if your config provider is lua (refer to
  eval)"), and this machine reports `configProvider: lua`.
- `hyprctl eval` is arbitrary Lua assembled by interpolation. Omarchy has
  already shipped a security migration for exactly that shape
  (`/usr/share/omarchy/migrations/1787618700.sh`), and anything it could give us
  a rule can give us - which is nothing, for a window already mapped.

None of this matters, because dispatchers do the job directly and Omarchy ships
two examples of them driving a window the caller did not spawn.

### 2.3 What we use

Addressed dispatchers, read-then-act, the same shape Omarchy uses for its own
webcam overlay:

- `/usr/share/omarchy/bin/omarchy-capture-webcam-resize:31-57,143-149` resolves
  a window out of `hyprctl clients -j`, does the scale/transform arithmetic by
  hand, and dispatches `resize`/`move` against `address:0x..` for a window the
  user is not focused on. This is our template.
- `/usr/share/omarchy/bin/omarchy-hyprland-window-pop` is the apply/put-back
  precedent: float, resize, move-or-center, pin, alter_zorder top, tag; and on
  the way out it **reads `.pinned` first** (line 12) and branches, rather than
  blind-toggling. We copy that discipline. We do **not** copy its verbs (2.5).

Every window dispatcher in 0.56.2 takes an optional `window` selector - the
binary's own argument-error strings spell it: `hl.window.resize: expected no
args, a table { x, y, relative?, window? }`, `hl.window.alter_zorder: expected a
table { mode, window? }`, `hl.window.tag: expected a table { tag, window? }` -
so nothing needs focus and nothing needs to be on the active workspace. That is
the answer to the brief's central question: **yes, a program can float, resize,
move and pin a window it did not spawn, with no config file edit and nothing
gated** (`ecosystem:enforce_permissions` reads `{"bool": false, "set": false}`,
`hyprctl configerrors` is empty, both sockets are owned by the user).

The cost is not the dispatch sequence, which is about ten lines. The cost is
pid-narrowed addressing, a snapshot with the right lifetime, read-before-act on
two independent booleans, scale/transform/reserved arithmetic for a monitor
nobody here can test on, and a Lua interpolation boundary. That is the feature;
budget for it (section 9).

### 2.4 What "picture in picture" does not mean here

Hyprland 0.56.2 has no always-on-top window rule and no such dynamic property.
A search of the binary for `ontop`, `alwaysontop`, `always_on_top`, `stayontop`
and `keep_above` finds only `above_lock` (a **layer** rule) and
`alterzorder`/`bring_to_top`. What we have is:

- `pin`: the window appears on every workspace of its monitor. Floating only.
- `alter_zorder { mode = "top" }`: a one-shot raise within the floating stack.

So a floating window focused after ours can cover it. The README and the footer
copy must say "stays with you", never "always on top".

### 2.5 Claims from the investigations that are WRONG and must not be built on

| Claim seen in the raw notes | Why it is wrong | What to do instead |
|---|---|---|
| "`omarchy-hyprland-window-pop` uses `resizewindowpixel` / `movewindowpixel`" | It does not. Lines 29, 32 and 34 are `resizeactive exact W H`, `moveactive X Y` and `centerwindow` - **active-window** dispatchers with no selector parameter. It gets away with it because it only ever acts on `hyprctl activewindow -j` (line 11). Copied literally into a plugin that must not focus the player, it resizes and moves whatever the user is working in. | Take the legacy spelling from `omarchy-capture-webcam-resize:143-149` instead: `resizewindowpixel "exact W H,address:0x.."` and `movewindowpixel "exact X Y,address:0x.."` - note the comma. |
| "`hyprctl getprop <w> float` returns `prop not found`, therefore a rule cannot touch a mapped window" | The inference is invalid: the same probe returns `prop not found` for `tile`, `maximize`, `pseudo`, `no_initial_focus` (all real rule effects) and for `ontop`, `alwaysontop`, `above` (not anything at all). `getprop` only reports absence from the setprop table. | We do not use rules anyway. Where the question does bite - a user's pasted float rule re-applying on a commit or a title change - it is gate G-5, not a settled fact. |
| "`docs/UX.md` and `docs/M2-03-CHANNEL-NUMBERS.md` disagree on the key" | They do not. `docs/M2-03-CHANNEL-NUMBERS.md:329-330` reads "`p` stays free for M2-05 picture in picture, and `Shift+Enter` stays reserved for it (UX.md 3.1)". | No ruling needed on the conflict. A ruling **is** needed on `Shift+Enter`, for a different reason: it is unreachable (open question 1). |
| "mpv `--ontop` might work; book display time to find out" | It cannot. No stacking request in xdg-shell, no layer shell in the mpv binary, no Wayland stay-on-top code. | Gate G-9 exists only to confirm the negative cheaply, not to discover an option. |
| "The player window is translucent right now; the opacity defect is live" | Not observed. `hyprctl -j clients` returns one client and it is not ours; `pgrep -x mpv` is empty. The rule chain reasoning is sound but no `omarchy-iptv` window has existed during any investigation. | Treat as an inference. Gate G-11 settles it with one command once a player window exists. |
| "Omarchy's helpers are argv helpers" | Every one of them runs `hyprctl dispatch "<interpolated Lua>"` first and only falls back to the classic dispatcher on failure. On this machine the Lua arm is what runs. | Our primary spelling is the Lua form. The "argv only" commitment in `docs/PLAN-M2.md:77` (A5) is about process launching and is still honoured: one argv vector, no shell. The Lua string is a separate boundary and gets its own rule (4.11). |
| "mpv's IPC has no error channel" / "`osd-width` answers `property unavailable` with no VO" | Both wrong. An unknown property returns `property not found` and a malformed value returns `unsupported format for accessing property`; what mpv does **not** report is platform semantics. And `osd-width`/`osd-height` return `success` with value **0** when there is no VO - a readback check written to the original description fails open. | Never verify a window property by its `set_property` reply. Verify by `hyprctl -j clients`. `current-window-scale` is the only mpv readback that fails closed. |

Two further corrections, in our favour:

- `hyprctl reload` destroys Lua globals and eval-registered rules
  (`Config::Lua::CConfigManager::reload()` calls `reinitLuaState()`). Irrelevant
  to us, because dispatched window state lives on the window, not in Lua. A
  theme switch therefore cannot un-PiP the user. Gate G-12 confirms it live.
- A window's title change reaches only `applyDynamicRule`
  (`CWindow::onUpdateMeta` -> `propertiesChanged`), so the per-zap retitle does
  not by itself re-run static rule effects. What is **not** established is
  `CWindow::commitWindow()`'s call to `readStaticRules(true)`, which a playing
  video reaches constantly. That is gate G-5, framed as "on a commit", not "on a
  title change".

---

## 3. GATE - what must be proven before any lane writes code

This project has twice shipped on an assumption about host behaviour that was
false, and both times a probe would have caught it in minutes. **No lane opens
an editor until this table is green.** It is task M2-05-00 (section 9), it is
owned by the lane that holds the display, and its results are appended to
`docs/QA-RESULTS.md` and mirrored into section 13 of this file.

Setup for every item that needs a window: one channel playing, then
`ADDR=$(hyprctl -j clients | python3 -c 'import json,sys;print([c["address"] for c in json.load(sys.stdin) if c["class"]=="omarchy-iptv"][0])')`.

| # | Assumption | Exact command | Pass | A failure forces |
|---|---|---|---|---|
| G-1 | The Lua dispatch form works, and we learn whether the legacy form still does | `hyprctl dispatch 'hl.dsp.window.tag({ window = "address:'"$ADDR"'", tag = "+iptv-probe" })'; echo "lua rc=$?"; hyprctl -j clients \| grep -c iptv-probe; hyprctl dispatch tagwindow +iptv-probe2 "address:$ADDR"; echo "legacy rc=$?"; hyprctl -j clients \| grep -c iptv-probe2` then remove both with the `-` forms | Lua form: rc 0 and the tag appears | If the **Lua** form fails, the whole design fails and PiP is refused on this compositor. If the **legacy** form fails (expected: `hyprctl dispatch` wraps its argument as `return hl.dispatch(<arg>)` under a Lua provider), then `Model.focusPlayerArgv()` is **already broken in shipping code** - file it as a defect and fix it in the same wave (open question 8) - and the legacy fallback ships only for other users' non-Lua Hyprlands |
| G-2 | The player's window is findable by class **and** pid, and the pid the service holds is the pid Hyprland reports | `hyprctl -j clients \| python3 -c 'import json,sys;[print(c["class"],c["pid"],c["address"],c["floating"],c["pinned"],c["tags"]) for c in json.load(sys.stdin)]'` against `omarchy-shell io.github.rmcdavid.iptv status` | Exactly one client whose `class` is `omarchy-iptv` and whose `pid` equals the player pid | If Hyprland reports a different pid (a wrapper process), the service must resolve by `initialClass` + a single-match rule and PiP refuses when the match is ambiguous |
| G-3 | `float` and `pin` semantics: are they toggle-only, or do they accept an action? | `hyprctl dispatch 'hl.dsp.window.float({ window = "address:'"$ADDR"'", action = "set" })'; hyprctl -j clients \| grep -A2 "$ADDR"` (read `floating`), then the same with `action = "unset"`, then `hl.dsp.window.pin({ window = ..., action = "set" })` | Either result is acceptable; we need to know which | Design already assumes toggle-only and reads before acting, so a failure changes nothing. A **pass** lets `Model.pipPlan` emit fewer steps; it is an optimisation, not a dependency |
| G-4 | A channel change does not move or resize the PiP box once `auto-window-resize=no` is set | In PiP, record `at`/`size` from `hyprctl -j clients`; zap between two channels of visibly different resolutions (e.g. a 1080p and a 576p entry); re-read | `at` and `size` unchanged across both zaps | If it still moves, add `keepaspect-window=no` to the PiP-on command set and re-test; if it still moves, re-apply geometry after each `start-file` event (the service already sees them, `Model.routePlayerEvent`) |
| G-5 | A surface commit does not re-apply a user's static float rule and snap a user-moved window back | With `contrib/windows.lua`'s float line pasted into `~/.config/hypr` **by the user on a scratch config**, enter PiP, drag the window, let 30 s of video play, zap once; re-read `at` | Position stays where the user put it | If static effects re-apply on commit, the contrib float rule and PiP are incompatible: document that users who float the player by rule should not paste the `size`/`center` half, and add a note to `README.md` |
| G-6 | `user-data/omarchy-iptv-pip` survives a `loadfile ... replace` and is readable by a second client (headless; no window) | `mpv --no-config --idle=yes --vo=null --ao=null --force-window=no --input-ipc-server=/tmp/g6.sock & PID=$!` then over the socket: `set_property user-data/omarchy-iptv-pip {"active":true,"at":[1,2]}`, `loadfile <small local file> replace`, reconnect a **new** client, `get_property user-data/omarchy-iptv-pip`; `kill $PID` | The object reads back identical after the load, from a client that connected afterwards | If it does not survive a load, the snapshot moves to `$XDG_RUNTIME_DIR/omarchy-iptv/pip.json` (0600, permitted by `CLAUDE.md` constraint 6) written by the service |
| G-7 | `hyprctl --batch` works with Lua dispatch (an optimisation, not a dependency) | `hyprctl --batch "dispatch hl.dsp.window.tag({ window = \"address:$ADDR\", tag = \"+b1\" }) ; dispatch hl.dsp.window.tag({ window = \"address:$ADDR\", tag = \"+b2\" })"; hyprctl -j clients \| grep -c 'b1\|b2'` | Both tags appear | Fall back to the sequential queue, which is the design's default anyway. Do not adopt `--batch` unless it is green |
| G-8 | `hyprctl` exists and Hyprland is reachable from the shell's environment | `which hyprctl; echo $HYPRLAND_INSTANCE_SIGNATURE; ls -l "$XDG_RUNTIME_DIR/hypr/"` | Binary on PATH, signature non-empty | PiP is hidden: the `p` key says `Picture in picture needs Hyprland`, the IPC verb returns `{"ok":false,"error":{"code":"no_compositor"}}` |
| G-9 | Confirm the negative: mpv cannot raise itself (cheap, read-only) | `strings -a /usr/bin/mpv \| grep -cE '^zwlr_layer_shell_v1$'` (expect 0); optionally press `T` on the live player window and confirm `hyprctl -j clients` is unchanged | 0, and no observable change | A non-zero count would mean a newer mpv links layer-shell; re-open 2.1 before designing anything else |
| G-10 | `reserved` is `[left, top, right, bottom]` and a top-corner PiP clears the bar | `hyprctl -j monitors \| python3 -c 'import json,sys;m=json.load(sys.stdin)[0];print(m["reserved"],m["scale"],m["transform"])'` and `hyprctl -j layers \| grep -B5 omarchy-bar` | `[0, 26, 0, 0]` with the bar at the top, level 2, 1366x26 - i.e. 26 is in slot 2 | If the order is different, `Model.pipGeometry`'s fixture changes and its unit test changes with it. The arithmetic is pure and fixture-driven precisely so this is a one-line correction |
| G-11 | Whether the player window is translucent under the Omarchy defaults (inference only, never observed) | With a channel playing: `hyprctl -j clients \| python3 -c 'import json,sys;[print(c["class"],c["tags"]) for c in json.load(sys.stdin)]'`; look for `default-opacity` | Records the fact either way | If it is tagged, `README.md` gains one sentence pointing at `contrib/windows.lua:7`, and open question 5 is answered from evidence rather than reasoning |
| G-12 | A theme switch does not disturb PiP | In PiP: `omarchy theme set <another theme>`; re-read `at`, `size`, `floating`, `pinned` | Unchanged | If it does, the design is wrong about dispatched state living on the window; stop and redesign |
| G-13 | `Shift+Enter` is unreachable in list mode (already established by reading, kept here so the ruling has a citation) | `sed -n '36,80p' /usr/share/omarchy/shell/Ui/PanelKeyCatcher.qml` | Signals at :38-44 carry no modifier; the `Qt.Key_Return` branch at :71 emits `returnRequested()` + `activateRequested()` and sets `event.accepted = true` | Already failed. `Shift+Enter` is dropped for v0.3.0 (open question 1) |

G-1, G-2, G-3, G-4, G-5, G-11 and G-12 need the display and a playing channel.
G-6 is headless and opens no window. G-7 needs the display. G-8, G-9, G-10 and
G-13 are read-only and any lane may run them.

---

## 4. Design

### 4.1 The seams this plugs into

| Seam | Site | What PiP adds |
|---|---|---|
| Player pid | `Model.parsePlayerProbe` already returns `pid` (`Model.js:2713-2728`); `player start` also emits it (`bin/omarchy-iptv:3113`) and `Model.parseHelperStatus` (`Model.js:1905-1925`) passes unknown keys through | `Service.qml` records `root.playerPid` from both |
| Player socket | `Service.qml:1659-1663` `socketWrite`, already used at `:1667-1676` | Two writes at PiP-on, two at PiP-off |
| Window identity | `--wayland-app-id=omarchy-iptv` on the launch argv (`Model.js:2403`, `bin/omarchy-iptv:2126`), fixed at surface creation | Unchanged, and must stay unchanged |
| Process launching | `Service.qml:2799-2806` (`whichProc`) is the shipped `which` pattern; `playerProc` at `:2900-2910` is the shipped stdout pattern | A new `hyprProc` of the same shape |
| List-mode letters | `Guide.qml:1008-1021` `handleListLetter` | `p` / `P` |
| IPC verbs | `Service.qml:2953-2985` | `pip(mode)` |

### 4.2 Resolving the window

```
Model.pipFindWindow(clientsJson, pid, "omarchy-iptv")
  -> { ok, address, at, size, floating, pinned, monitor, workspaceId, tags }
```

Rules, all in the pure function so they are unit-testable:

1. Parse `hyprctl -j clients` output. Never throw; garbage returns `ok:false`.
2. Keep entries whose `class === "omarchy-iptv"` **and** `pid === playerPid`.
3. Zero matches -> `ok:false, reason:"no_window"`. More than one -> also
   `ok:false, reason:"ambiguous"`; PiP refuses rather than guessing.
4. `address` must match `/^0x[0-9a-f]{1,16}$/` or the result is `ok:false`.
5. Tags are compared with a trailing `*` stripped: a rule-applied tag reads back
   as `"default-opacity*"` on this machine, a dispatched one does not.

Narrowing by pid is not optional. `docs/QA-PLAYER.md:124` (PLY-RST-11,
`[corrected b16b479]`) records the reproduced case: a user's own
`mpv --wayland-app-id=omarchy-iptv` makes `hyprctl clients` read **2**. Focusing
a stranger's window is a nuisance; floating, shrinking, pinning and moving it is
damage.

### 4.3 The transitions

`Model.pipPlan(live, snapshot, geometry, intent)` returns an ordered array of
argv vectors. Pure, ES5, no side effects, fixture-tested. `Service.qml` runs the
array through one `Process`, one vector at a time, with a bounded watchdog.

**Enter** (`intent === "on"`), given `A` = validated address:

| Step | Condition | Lua form (primary) | Legacy fallback |
|---|---|---|---|
| 1 | `live.floating === false` | `hl.dsp.window.float({ window = "address:A", action = "toggle" })` | `togglefloating address:A` |
| 2 | always | `hl.dsp.window.resize({ window = "address:A", x = W, y = H })` | `resizewindowpixel "exact W H,address:A"` |
| 3 | always | `hl.dsp.window.move({ window = "address:A", x = X, y = Y })` | `movewindowpixel "exact X Y,address:A"` |
| 4 | `live.pinned === false` | `hl.dsp.window.pin({ window = "address:A" })` | `pin address:A` |
| 5 | always | `hl.dsp.window.alter_zorder({ window = "address:A", mode = "top" })` | `alterzorder "top,address:A"` |
| 6 | always | `hl.dsp.window.tag({ window = "address:A", tag = "+iptv-pip" })` | `tagwindow "+iptv-pip,address:A"` |

**Exit** (`intent === "off"`):

| Step | Condition | Lua form |
|---|---|---|
| 1 | always | `hl.dsp.window.tag({ window = "address:A", tag = "-iptv-pip" })` |
| 2 | `live.pinned === true && snapshot.pinned !== true` | `hl.dsp.window.pin({ window = "address:A" })` (toggles off) |
| 3 | `snapshot.floating === true` | `hl.dsp.window.resize({ ... x = snapshot.size[0], y = snapshot.size[1] })` then `hl.dsp.window.move({ ... x = snapshot.at[0], y = snapshot.at[1] })` |
| 3' | `snapshot.floating !== true && live.floating === true` | `hl.dsp.window.float({ window = "address:A", action = "toggle" })` |

Order matters: unpin before unfloat, because `pin` applies to floating windows.
This is the order `omarchy-hyprland-window-pop:24-25` uses.

Every conditional above reads `live`, which is re-read from
`hyprctl -j clients` immediately before the plan is built - never from a
remembered boolean. The user has `SUPER + T` and `SUPER + O` bound live and can
change `floating` and `pinned` behind our back at any moment.

The legacy fallback runs only when the Lua form exits non-zero, which is why
this path needs a `Process` and not `Quickshell.execDetached` (which returns
void and cannot report failure). If G-1 shows the legacy arm is unreachable on a
Lua provider, the fallback still ships for users on an hyprlang Hyprland; it is
three extra entries in a table, it is fixture-tested, and it costs nothing.

### 4.4 Geometry

```
Model.pipGeometry(monitor, opts) -> { x, y, w, h }
```

`monitor` is one entry of `hyprctl -j monitors`; `opts` is
`{ corner, sizePercent, margin }` after clamping. The arithmetic, copied from
`omarchy-capture-webcam-resize:46-57,137-141` because that is the code that
works on hardware we cannot test on:

1. Logical size: `lw = round(width / scale)`, `lh = round(height / scale)`.
   `hyprctl monitors` reports **physical** pixels.
2. If `(transform % 2) === 1`, swap `lw` and `lh`.
3. Usable rectangle, in **global layout coordinates** (dispatcher `move` takes
   global coordinates; only rule expressions use per-monitor `monitor_w`):
   `x0 = x + reserved[0] + margin`, `y0 = y + reserved[1] + margin`,
   `x1 = x + lw - reserved[2] - margin`, `y1 = y + lh - reserved[3] - margin`.
4. `w = clamp(round(lw * sizePercent / 100), 240, x1 - x0)`;
   `h = round(w * 9 / 16)`; if `h > y1 - y0`, clamp `h` and recompute `w` from
   it. Both are floored to even integers.
5. Corner: `top-right` -> `(x1 - w, y0)`, `top-left` -> `(x0, y0)`,
   `bottom-right` -> `(x1 - w, y1 - h)`, `bottom-left` -> `(x0, y1 - h)`.

Two notes. The bar's reserved strip is **not** automatic for a
dispatch-placed window - Omarchy's own `pip.lua:11` dodges it with a
`monitor_h*0.04` inset that is 30 px against a 26 px strip on this display, four
pixels of luck. We subtract `reserved` explicitly. And the box is 16:9 by
convention: a 4:3 channel letterboxes inside it, which is correct and expected,
and avoids fighting mpv's own aspect handling.

On this machine (`eDP-1`, 1366x768, scale 1, transform 0, reserved
`[0, 26, 0, 0]`) the defaults give a 410x230 box at `(932, 42)`. Omarchy's own
600x338 would be 44 percent of this screen in both axes, and
`omarchy-hyprland-window-pop`'s 1300x900 default is taller than the display -
which is why the size is a percentage of the monitor, not a constant.

### 4.5 Where the previous state lives

The compositor remembers what the window **is**. Nothing remembers what it
**was** unless we write it down, and the thing we write it to must have exactly
the window's lifetime: it must survive a shell restart, survive a channel
change, and disappear when the window does.

That thing is the player. At PiP-on the service writes, over the socket it
already holds:

```
["set_property", "user-data/omarchy-iptv-pip",
   { "active": true, "at": [x, y], "size": [w, h],
     "floating": false, "pinned": false,
     "monitor": 0, "workspace": 1, "v": 1 }]
```

and at PiP-off it writes `{ "active": false, "v": 1 }`.

This costs no new file, no `state.json` schema change (so no Python mirror
change and no `STATE_VERSION` bump), and no write outside the plugin's
directories - in fact no write to disk at all. `user-data/omarchy-iptv` and
`user-data/omarchy-iptv-owner` are already the reattach mechanism
(`docs/ARCHITECTURE-PLAYER.md` 4.6), and the helper never touches a third key,
so `apply_channel` (`bin/omarchy-iptv:2763`) cannot clobber it on a zap. G-6
proves that before a line is written.

Reading it back is needed in exactly one case - the shell restarted while in
PiP and the user then exits - so it is a single `get_property` with a request id
routed by a new `Model.parsePlayerReply(line)`, issued from `onPlayerAttached`
alongside the two subscriptions already there. If the read fails or answers
`active:false`, exit degrades to "unpin and unfloat and let the layout take it",
which is what `omarchy-hyprland-window-pop` does unconditionally. Degraded,
never stuck.

### 4.6 On a channel change

Two things change on a zap: the title (`set_property title` /
`force-media-title`, `docs/ARCHITECTURE-PLAYER.md` 4.9 steps a-b) and possibly
the video resolution.

- The title change does not concern the compositor state we set: we address by
  `address:`, never by `title:`, and a title change reaches only
  `applyDynamicRule`. The one residual risk is a static rule re-applying on a
  **commit**, which only bites users who pasted the optional float rule - gate
  G-5.
- The resolution change does concern us. mpv's `--auto-window-resize` defaults
  to `yes` ("mpv will automatically resize itself if the video's size changes"),
  so the next zap would have mpv request a size derived from the new stream.
  **This is the one job the compositor cannot do for us.** At PiP-on the service
  writes `["set_property", "auto-window-resize", false]`; at PiP-off it writes
  back the value `Model.pipRestoreAutoResize(mpvArgs)` derives from the user's
  own `mpvArgs` tokens (their explicit value if they set one, otherwise mpv's
  default `true`). That keeps the restore deterministic without a read, and it
  is pure and unit-testable.

`--auto-window-resize` is deliberately **not** added to `MPV_RESERVED`
(`Model.js:142-162`): that list exists for identity and URL-leak reasons
(`docs/ARCHITECTURE-PLAYER.md` requirement 8), and taking a knob away from the
user is a worse outcome than the narrow overlap handled above.

### 4.7 On a shell restart

The player outlives the shell; so does the window; so does everything we
dispatched. After `omarchy restart shell`:

1. The service's existing reattach runs (`player probe`,
   `docs/ARCHITECTURE-PLAYER.md` 4.5) and now also records `root.playerPid`.
2. Once the socket attaches, `onPlayerAttached` issues the snapshot read (4.5).
3. The first PiP question (is it on?) is answered without either: read
   `hyprctl -j clients` and look for `floating && pinned && tag "iptv-pip"`.

So the guide shows the right state, `p` still toggles correctly, and exiting
restores the real previous geometry if the snapshot read answered, or unfloats
if it did not. Nothing is stranded in a corner with nothing that knows how to
put it back - which is precisely the failure the naive "remember a boolean"
design produces.

### 4.8 When the user changes the window themselves

Read-then-act covers all of it, because we never trust memory:

| The user does | PiP-off then does |
|---|---|
| Drags or resizes the PiP box | Restores to the snapshot (or unfloats), from wherever the box now is |
| Presses `SUPER + T` (unfloat) | `live.floating` is false, so no float toggle is emitted; PiP is simply off |
| Presses `SUPER + O` (Omarchy's own float+pin) | `live.pinned` is true and `live.floating` is true; we unpin only if the snapshot says it was not pinned before. A window the user popped themselves and we never PiP'd carries no `iptv-pip` tag, so `p` treats it as "enter", not "exit" |
| Fullscreens a work window over the PiP | Not established: `binds:allow_pin_fullscreen` reads `{"bool": false, "set": false}`. Recorded as a live-pass observation (PIP-12), not a pass/fail |
| Closes the player window | The player exits; the existing end-of-playback path runs; PiP state evaporates with the window |
| Stops playback while in PiP | `stop()` runs the shipped ladder; no floating leftover window is possible because the window is gone. This is `docs/PLAN-M2.md:267` verbatim |

### 4.9 With more than one monitor

Unverifiable here: one output, `eDP-1`, though `card1-DP-1`, `card1-HDMI-A-1`
and `card1-HDMI-A-2` exist, so the user can attach one at any time. The design
is therefore written so the arithmetic is right where it cannot be exercised:

- PiP uses the monitor the window is **currently** on (`.monitor` from the
  client entry), looked up in `hyprctl -j monitors` by `id`.
- `Model.pipGeometry` does the scale division, the transform swap and the
  `reserved` subtraction unconditionally, and is fixture-tested with a 2x-scaled
  monitor, a 1.5x-scaled monitor, a transform-1 monitor and a monitor at a
  non-zero `x`/`y` - none of which exist on this machine. This is the only way
  to get multi-monitor correctness out of a single-monitor lab.
- `pin` is a per-monitor concept. A pinned window follows the user across the
  workspaces **of its monitor**. Moving the PiP to another monitor is out of
  scope for v0.3.0.
- What happens when the monitor holding a pinned PiP is unplugged is **not
  established** and stays a documented limitation, consistent with
  `docs/PLAN-M2.md:79-81` (A6) and MR12 at `:225`.

### 4.10 Failure and degradation

| Condition | Behaviour |
|---|---|
| `which hyprctl` fails, or no `HYPRLAND_INSTANCE_SIGNATURE` | `root.pipAvailable = false`; `p` answers `Picture in picture needs Hyprland`; the IPC verb returns `{"ok":false,"error":{"code":"no_compositor"}}` |
| Nothing playing | `Nothing playing`. PiP never starts a player |
| No matching window, or more than one | `{"ok":false,"error":{"code":"no_window"\|"ambiguous"}}` and a footer line. Never act on a guess |
| A dispatch step exits non-zero after the fallback | **WITHDRAWN by ruling PIP11 (section 13). Do not implement this row.** It was written believing an exit status could detect a failed dispatch. The gate measured otherwise: `hyprctl` returns 0 for every dispatch aimed at an address that does not exist, and reports a genuine refusal as `warning:` text on stdout, still with rc 0. A non-zero rc means only that our own Lua string failed to parse. Detecting failure this way was filed as **D-PIP-2 (P2)** before any code was written. The shipped rule is a compositor readback, defined in exactly one place, `Model.pipVerify`. The original wording is kept, struck, because a lane that read this row alone would walk straight back into the defect |
| The socket is dead when the mpv half is written | `socketWrite` already returns false (`Service.qml:1660`, rule C7). The compositor half still applies; the box may jump on the next zap. Recorded, not fatal |
| Watchdog | The queue is bounded: at most 8 steps, each with a 2 s watchdog, matching the shipped `playerWatchdog` pattern. No unbounded wait anywhere (CLAUDE.md "Working in parallel" rule 3) |

### 4.11 Security: the one new interpolation boundary

The Lua dispatch form puts a string inside one argv item, and that string is
evaluated by the compositor. That is a genuine new sink and it gets a written
rule, because Omarchy has already shipped a security migration for exactly this
bug (`/usr/share/omarchy/migrations/1787618700.sh`: a device name interpolated
into `hyprctl eval`).

**Only two kinds of value may ever be interpolated into a Lua dispatch string:**

1. A window address that has matched `/^0x[0-9a-f]{1,16}$/`. The regex is applied
   in `Model.pipFindWindow` (`Model.js:3412`) and applied **again** by
   `Model.pipAddressSelector` on every dispatch path that builds a window
   argument (`Model.js:3315`, `:3685`), so a future caller cannot route around
   it. **Until 2026-09-16 this row named a Model function called
   pipLuaDispatch, written without backticks here so the citation check does
   not flag this correction, and no such function has ever existed in any
   commit** -- an acceptance criterion
   grading a name nobody had checked. The double application it asserts is
   real; only the name was invented. Found by the citation check that
   `scripts/check-defect-ledger.py` gained in phase 0.
2. Integers produced by `Math.floor` inside `Model.pipGeometry`, re-checked to be
   finite and within `[-100000, 100000]`.

Everything else is a compile-time constant in `Model.js`: the class name, the
tag name, the verb names, the corner keywords. **No playlist-derived value -
channel name, group, title, URL, chno - may appear in a dispatch string, ever.**
There is no code path that would want one; the rule exists so none is added.

This is consistent with, not an exception to, `docs/ARCHITECTURE-PLAYER.md:781`
requirement 9 (which is about process launching: no `bash -lc`, no shell `eval`,
no `hyprctl exec_cmd`) and `CLAUDE.md` constraint 2 (no shell, no interpolation
into a **command**). It nonetheless deserves a PO ruling on the record - open
question 7.

MR10 (`docs/PLAN-M2.md:223`) applies: PiP adds a footer line and an IPC reply.
Neither carries a URL by construction, and both go through the same privacy
sweep in the same commit.

---

## 5. UI and copy

**List mode key** (`Guide.qml:1008-1021`, one line):

```js
else if (t === "p" || t === "P") root.togglePip()
```

`p` is free: `docs/M2-03-CHANNEL-NUMBERS.md:329-330` reserved it, and the digit
machine returns early for digits before letters are dispatched.

`Shift+Enter` is **not** implemented. `/usr/share/omarchy/shell/Ui/PanelKeyCatcher.qml:71`
handles `Qt.Key_Return`, emits `returnRequested()` and `activateRequested()`
with no modifier argument (signals at `:38-44`), and sets
`event.accepted = true` with `Keys.priority: Keys.BeforeItem` - so the guide
never sees the modifier in list mode. See open question 1.

**Footer copy** (UX.md section 6 style, ASCII stand-ins as usual):

| Situation | Line |
|---|---|
| PiP on | `Picture in picture on` |
| PiP off | `Picture in picture off` |
| Nothing playing | `Nothing playing` |
| No compositor | `Picture in picture needs Hyprland` |
| Window not found / ambiguous | `Cannot find the player window` |
| Dispatch failed | `Hyprland refused the window change` |

**Hint line** in list mode gains `p pip` in the existing hint rhythm.

**Bar widget**: the tooltip gains one line, `Picture in picture: on`, when it is
on. No new mouse gesture (open question 2).

**Glyph state**: the bar's TV glyph does not change. PiP is a window state, not a
playback state, and the bar already carries playback truth.

**No notification.** PiP is a foreground, user-initiated, instantly visible
action; a toast for it would be noise (UX.md 6.4's rule).

---

## 6. Settings

Added to `manifest.json` in the shipped style - `defaults` block plus a `schema`
entry, exactly as `channelOrder` / `numberEntryMs` / `barShowChannelNumber` were
added for M2-03.

```json
"pipCorner": "top-right",
"pipSizePercent": 30,
"pipMargin": 16
```

```json
{
  "key": "pipCorner",
  "type": "string",
  "label": "Picture-in-picture corner: top-right, top-left, bottom-right, bottom-left"
},
{
  "key": "pipSizePercent",
  "type": "integer",
  "label": "Picture-in-picture width (percent of the monitor)",
  "min": 15,
  "max": 60,
  "step": 5,
  "defaultValue": 30
},
{
  "key": "pipMargin",
  "type": "integer",
  "label": "Picture-in-picture margin from the screen edge (px)",
  "min": 0,
  "max": 200,
  "step": 4,
  "defaultValue": 16
}
```

`Model.pipOptions(config)` clamps all three and falls back to the defaults for
anything unrecognised, the same way `channelOrder` is handled; the guide and the
service both read the one entry. The README settings table gains three rows.

**Nothing must go into the user's own configuration for PiP to work.** That is
worth stating plainly, because it is the answer to the brief's second question:
the mechanism is available with no edit to `~/.config/hypr`, no `hyprctl
keyword`, and no reload.

---

## 7. Contrib

`contrib/windows.lua` is unrelated to PiP but is touched in this wave because
M2-05-04 already owns it and it currently ships a line that is very likely
broken. Current file:

```lua
o.window("omarchy-iptv", { tag = "-default-opacity" })
-- o.window("omarchy-iptv", { float = true, size = "1280 720", center = true })
```

`size` as a **string** matches nothing in Omarchy's own vocabulary - every rule
uses a two-element table (`apps/pip.lua:7` `size = { 600, 338 }`,
`apps/webcam-overlay.lua:4`, `apps/system.lua:4` and `:28`) - and the installed
type stub cannot catch it (`HL.WindowRuleSpec` at
`/usr/share/hypr/stubs/hl.meta.lua:597-601` declares only `enabled`, `match` and
`name`). The bare-string first argument **is** correct: the last function in
`/usr/share/omarchy/default/hypr/helpers.lua` maps a string match onto
`rules.match.class`. Replacement:

```lua
-- Omarchy IPTV: optional window rules for the mpv player window.
-- Add to ~/.config/hypr/looknfeel.lua (or any file loaded by hyprland.lua).
-- Picture in picture does NOT need any of this; the plugin drives the window
-- at runtime with hyprctl and writes nothing to your config.

-- Keep video fully opaque (Omarchy applies a default opacity to windows).
o.window("omarchy-iptv", { tag = "-default-opacity" })

-- Optional: always float the player at a fixed size, centered.
-- o.window("omarchy-iptv", { float = true, size = { 1280, 720 }, center = true })
```

Two caveats to carry into the README: the paste target (`looknfeel.lua` is
required at `hyprland.lua:22`, **after** `default.hypr.windows` has already
registered `opacity = "0.985 0.96"` at `:25`, whereas Omarchy's own files always
strip the tag earlier) - whether the late paste wins has never been tested here,
and it is not PiP's job to settle it; and the float line plus gate G-5.

`contrib/bindings.lua` gains one commented optional line:

```lua
-- o.bind("SUPER + SHIFT + P", "IPTV picture in picture", "omarchy-shell io.github.rmcdavid.iptv pip toggle")
```

The README should also say that stock Omarchy's `SUPER + O` already floats and
pins the focused window, so a user who wants this once needs nothing from us.

---

## 8. What must not break

Every row is an existing, proven invariant. A PiP change that touches any of
them is rejected, not negotiated.

| Invariant | Where it is pinned | How PiP stays clear of it |
|---|---|---|
| Exactly one player instance, one window | `docs/ARCHITECTURE-PLAYER.md` 5 req 1; `docs/QA-PLAYER.md` PLY-RST-12 | PiP execs nothing, spawns nothing, and never calls `player start`. `hyprctl clients` count is asserted before and after every PIP- case |
| Fixed class `omarchy-iptv`, title = channel name | req 3 | PiP never writes `wayland-app-id` (a runtime write may re-send `set_app_id`) and never writes `title` or `force-media-title`. It reads `class`, it does not set it |
| The player survives a shell restart and the shell reattaches | req 11 | PiP adds one `get_property` inside the existing `onPlayerAttached`, and nothing to the probe. 4.7 |
| Stop escalates and never orphans | req 4 | `stop()` is untouched. PiP has no teardown of its own: the window dying is the teardown |
| No stream address on any command line | req 9, section 6 | PiP argv contains a window address, integers and constants. Section 4.11 makes that a rule with a regex, twice |
| The user's own mpv key bindings stay live | `docs/ARCHITECTURE-PLAYER.md` 5 req 10 amendment, PO-11 | PiP writes two mpv properties (`auto-window-resize`, one `user-data` key). No `--no-config`, no input-conf change, no binding touched. `Alt+0/1/2`, `f` and `T` keep working, and read-then-act means using them cannot desynchronise us |
| Settings are declared in the manifest schema | `docs/ARCHITECTURE.md` 6 | Three keys, section 6, clamped in `Model.js` |
| No sudo; argv vectors only, never a shell | CLAUDE.md 2 and 4 | One `Process` with a `command` array. Never `bar.run()` (`PluginBarApi.qml:84-86` -> `Bar.qml:841-845` -> `Util.qml:53-55` is `bash -lc`), never `Util.execArgv` (also `bash -lc`, just data-safe) |
| The plugin writes only its three paths | CLAUDE.md 6 | PiP writes **no file at all**. Not `~/.config`, not `~/.local/state`, not `~/.cache`, not `/usr/share/omarchy` |
| Guide opens in under 150 ms on the 10k cache | CLAUDE.md 7, MR9 | PiP does no work at load time and nothing per channel row |
| URL redaction at every sink | CLAUDE.md 5, MR10 | The footer line and the IPC reply are constants plus booleans. Privacy sweep in the same commit |

---

## 9. Work plan and file ownership

Revises `docs/PLAN-M2.md:112-120`: one task is added (M2-05-00) and one is
re-estimated (M2-05-02, S -> M, for the reasons in 2.3).

| ID | Title | Owner | Deps | Effort | Display | Acceptance |
|---|---|---|---|---|---|---|
| M2-05-00 | **Gate pass**: run every row of section 3, record results in `docs/QA-RESULTS.md`, append them to section 13 here | QA (+ARCH for the appendix) | M2-02-05 | S | **yes** | Every gate row green or its failure branch chosen in writing. No lane starts before this |
| M2-05-01 | PO + UX ruling batch PIP1..PIPn (the numbered questions in section 12) | PO + UX | 00 | S | no | Rulings appended to this file and mirrored in the STATUS.md decisions log |
| M2-05-02 | `Model.js` pure layer: `pipOptions`, `pipFindWindow`, `pipGeometry`, `pipPlan`, `pipLuaDispatch`/`pipLegacyDispatch`, `pipMpvCommands`, `pipRestoreAutoResize`, `parsePlayerReply`; fixtures | FE, lane V1 | 01 | M | no | `node tests/Model.test.js` covers section 10.1 in full, each case shown red against a mutation |
| M2-05-03 | `Guide.qml` + `BarWidget.qml`: `p`, footer line, hint, tooltip line | FE, lane V1 | 02 | S | no (qmllint + spec only) | `p` calls through to the Model functions; hints and copy per section 5 |
| M2-05-04 | `Service.qml` + `manifest.json`: `hyprProc` queue, `playerPid`, snapshot write/read, `togglePip()`, IPC `pip` verb, three settings | FE, lane V2 | 02 | M | no | Harness scenario passes headless against a stub `hyprctl`; `omarchy plugin validate .` exit 0 |
| M2-05-05 | `contrib/windows.lua` fix + `contrib/bindings.lua` line + README (settings rows, keyboard map, the "not always on top" sentence, the Hyprland version pin per MR12) | FE, lane V2 | 04 | S | no | The documented rule pastes in verbatim and is valid Lua by Omarchy's own vocabulary |
| M2-05-06 | QA live pass: PIP-01..PIP-14 (section 10.4), privacy sweep, evidence root | QA | 03, 04, 05 | M | **yes** | Zero open P1/P2; `docs/PLAN-M2.md:263-267` DoD met |

**File ownership.** Lanes run in separate worktrees. A diff touching an unowned
file is rejected (`CLAUDE.md` "Working in parallel" rule 1).

| Lane | May write | May read | Must not open |
|---|---|---|---|
| Gate (M2-05-00) | `docs/QA-RESULTS.md` | everything | every source file in the repo |
| V1 (M2-05-02, -03) | `Model.js`, `Guide.qml`, `BarWidget.qml`, `tests/Model.test.js`, `tests/Model.spec.qml`, `tests/fixtures/pip-*.json` | `Service.qml`, `manifest.json`, docs | `Service.qml`, `bin/omarchy-iptv`, `contrib/*`, `README.md`, `scripts/dev-harness/*` |
| V2 (M2-05-04, -05) | `Service.qml`, `manifest.json`, `contrib/windows.lua`, `contrib/bindings.lua`, `README.md`, `scripts/dev-harness/*` | `Model.js`, `Guide.qml`, docs | `Model.js`, `Guide.qml`, `BarWidget.qml`, `tests/*` |
| QA (M2-05-06) | `docs/QA-RESULTS.md`, `docs/STATUS.md` | everything | every source file |

V1 merges first, V2 second (`docs/PLAN-M2.md:156-157`), because V2 consumes
V1's pure functions. No shims survive the merge; the integration grep and a
green `scripts/check.sh` prove it (MR5).

**Which parts need the display.** Only M2-05-00 and M2-05-06. Everything else -
all of `Model.js`, all of `Guide.qml`, all of `Service.qml`, the harness, the
contrib files, the README - is written and tested headless. That is deliberate:
the display is a single serialised resource (MR7), and the two tasks that need
it are the first and the last.

---

## 10. Test plan

### 10.1 Unit, `node tests/Model.test.js` (lane V1)

```bash
node tests/Model.test.js
```

| Function | Cases |
|---|---|
| `pipOptions` | each corner accepted; unknown corner -> default; percent 0, 14, 15, 30, 60, 61, 1e9, "abc", null -> clamped; margin likewise |
| `pipGeometry` | all four corners on the 1366x768 reserved-`[0,26,0,0]` fixture; a 3840x2160 scale-2 monitor; a 2560x1440 scale-1.5 monitor; `transform: 1` (axes swapped); a monitor at `x:1920, y:-360`; a monitor so small the 16:9 box must shrink; assert every output is an integer and inside the usable rect |
| `pipFindWindow` | one match; two clients same class, one our pid; class match wrong pid; no clients; malformed JSON; tags read with and without the trailing `*`; `address` not matching the regex -> `ok:false` |
| `pipPlan` | enter from tiled; enter from already floating; enter from floating+pinned (user popped it with `SUPER + O`); exit with snapshot floating; exit with snapshot tiled; exit when the user already unfloated; exit when the user already unpinned; exit with **no** snapshot (degraded path); assert step order (unpin before unfloat) in every exit case |
| `pipLuaDispatch` | rejects `0xdead; os.execute("x")`, `0xDEAD` (uppercase), `address:0x1`, `0x` + 17 hex digits, `""`, `null`; accepts `0x559c687e09a0`; a non-finite or out-of-range coordinate is rejected |
| `pipMpvCommands` / `pipRestoreAutoResize` | on -> `auto-window-resize=false` plus the snapshot write; off -> restore `true` with empty `mpvArgs`; restore `false` when the user passed `--auto-window-resize=no`; restore `true` when they passed `--auto-window-resize=yes`; `--no-auto-window-resize` handled |
| `parsePlayerReply` | a valid reply object; an event line (must not be mistaken for a reply); garbage; a reply for an unknown request id |

Per `CLAUDE.md` 11, each new case is shown red against a deliberate mutation of
the shipping function before it is accepted. The three mutations to report:
delete the `reserved` subtraction in `pipGeometry`; swap the unpin/unfloat order
in `pipPlan`; relax the address regex to `/^0x/`.

### 10.2 QML spec, `tests/Model.spec.qml` (lane V1)

```bash
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
```

The same pure functions exercised from QML's V4 engine, because that is the
engine that actually runs them (ES5-only, no `Array.prototype.find`, no template
literals). One case per function is enough; this catches engine differences, not
logic.

### 10.3 Headless service, harness (lane V2)

```bash
scripts/dev-harness/run.sh --scenario pip --timeout 120
```

A `pip-scenario.sh` with a stub `hyprctl` on `PATH` (the harness already exports
its own `XDG_RUNTIME_DIR`, `run.sh:93`, so it can never signal the live player)
that prints canned `clients`/`monitors` JSON and records the argv of every
dispatch. Asserts: the dispatch sequence and its order; that the address in
every vector is the pid-matched one; that nothing playlist-derived appears in
any vector (`grep -c '://'` is 0 and the channel name does not appear); that two
`pip toggle` calls return to the starting state; that `pip` with no player
returns `nothing_playing`; that a non-zero exit from the Lua form triggers the
legacy form exactly once per step.

### 10.4 Live pass, PIP- matrix (lane QA, holds the display)

Snapshot first, restore last (`CLAUDE.md` rule 5, QA-SOURCES 9.1/9.7 pattern):
`shell.json`, `~/.local/state/omarchy-iptv`, `~/.cache/omarchy-iptv`, the plugin
HEAD. Check `pgrep -x hyprlock` before any keystroke (rule 6).

Helper for every case:

```bash
CLIENTS='hyprctl -j clients | python3 -c "import json,sys;[print(c[\"class\"],c[\"pid\"],c[\"address\"],c[\"at\"],c[\"size\"],c[\"floating\"],c[\"pinned\"],c[\"tags\"]) for c in json.load(sys.stdin)]"'
COUNT='hyprctl -j clients | python3 -c "import json,sys;print(sum(1 for c in json.load(sys.stdin) if c[\"class\"]==\"omarchy-iptv\"))"'
```

| Case | What | Assertion |
|---|---|---|
| PIP-01 | `pip on` from a tiled player | `floating:true`, `pinned:true`, tag `iptv-pip`, `at`/`size` equal `Model.pipGeometry`'s computed values for this monitor |
| PIP-02 | `pip off` | back to `floating:false`, `pinned:false`, no tag; the other windows retile |
| PIP-03 | Same, with the contrib float line pasted (scratch config) | exit restores the previous rectangle, not the tiling layout |
| PIP-04 | Zap between two channels of different resolutions while in PiP | `at` and `size` unchanged (this is gate G-4 re-run as a regression) |
| PIP-05 | `omarchy restart shell` while in PiP | the window does not move; within 2 s the guide reports PiP on; `pip off` then restores correctly (or degrades to unfloat and says so) |
| PIP-06 | Drag the PiP box, then `pip off` | restores, no jump to a stale remembered rectangle before restoring |
| PIP-07 | `SUPER + O` on the player while in PiP, then `pip off` | no inverted state; the window ends unfloated and unpinned |
| PIP-08 | `stop` while in PiP | count goes 1 -> 0; no floating leftover; `docs/PLAN-M2.md:267` |
| PIP-09 | `omarchy theme set <other>` while in PiP | geometry, floating and pinned unchanged (gate G-12 as a regression) |
| PIP-10 | Open the guide over the PiP window | guide draws above (it is a layer-shell overlay); `Esc` returns; PiP untouched |
| PIP-11 | A foreign `mpv --wayland-app-id=omarchy-iptv` running (windowed, per PLY-RST-11) | `pip on` acts on **ours** only: the foreign window's `at`/`size`/`floating`/`pinned` are byte-identical before and after |
| PIP-12 | `SUPER + F` a work window while in PiP | **observation only**, recorded not filed: `binds:allow_pin_fullscreen` is false here and the outcome is not established |
| PIP-13 | Privacy sweep | `omarchy-shell io.github.rmcdavid.iptv status \| grep -c '://'` is 0; `journalctl --user -t omarchy-shell --since -30min \| grep omarchy-iptv \| grep -c '://'` is 0 |
| PIP-14 | One window throughout | `$COUNT` is exactly 1 at every step of every case above |

### 10.5 What a test can prove, and what it cannot

**A unit test proves**, and proves completely: the geometry arithmetic on
monitors that do not exist here (scale, transform, offset, reserved); the plan's
step order and its conditionals; the address regex; every clamp; the mpv restore
value derived from `mpvArgs`; that no playlist-derived string can reach a
dispatch vector. This is where multi-monitor correctness comes from, and it is
the only place it can come from on this machine.

**A harness run proves**: the service issues the right vectors in the right
order, recovers from a failing step, and returns to the starting state after two
toggles. With a stub `hyprctl` it proves nothing about Hyprland.

**Only a live pass can prove**: that Hyprland accepts the Lua dispatch form at
all (G-1); that `float`/`pin` behave as the plan assumes (G-3); that the box
survives a zap (G-4) and a theme switch (G-12); that a pasted static rule does
not snap a moved window back (G-5); that the bar does not cover a top-corner PiP
(G-10); and what a fullscreen work window does to a pinned one (PIP-12).

**Nothing available to this project can prove**: any multi-monitor behaviour;
what happens when the monitor holding a pinned PiP is unplugged; behaviour on
any Hyprland other than 0.56.2 with `configProvider: lua`. These are documented
limitations in the README, pinned to a version exactly as Quickshell already is
(MR12).

---

## 11. Documented limitations for the README

1. Picture in picture needs Hyprland. Verified on Hyprland 0.56.2 with a Lua
   config provider; other versions are untested.
2. The player is not "always on top". Hyprland has no such state. The PiP window
   floats and follows you between workspaces; another floating window you focus
   afterwards can cover it.
3. Multi-monitor placement is untested. PiP uses the monitor the player is on
   and does the scale and rotation arithmetic, but no second monitor was
   available.
4. PiP does not survive stopping playback. Play again and press `p` again.

---

## 12. Open questions for the product owner

Each is a ruling to be appended as PIP1..PIP9 in section 13.

1. **`Shift+Enter` is unreachable in list mode.**
   `/usr/share/omarchy/shell/Ui/PanelKeyCatcher.qml:71` swallows Return, emits
   two signals with no modifier, and accepts the event before the guide's own
   handler can see it (signals at `:38-44`). `docs/UX.md:275` reserves
   `Shift+Enter` for "play in a floating picture-in-picture window".
   **Recommendation:** drop `Shift+Enter` for v0.3.0, ship `p` alone, and amend
   `docs/UX.md:275` to say the reservation was released because the host key
   catcher cannot deliver it. Revisit only if Omarchy adds modifiers to those
   signals.

2. **How the bar exposes PiP.** `docs/PLAN-M2.md:118` says "the bar exposes the
   same action", but left click opens the guide, right click stops, middle click
   refreshes and scroll zaps - every gesture is taken, and PiP is not worth
   displacing one. **Recommendation:** no new bar gesture; a tooltip line when
   PiP is on, plus the IPC verb and the optional contrib bind. Amend
   `docs/PLAN-M2.md:118` accordingly.

3. **Does PiP survive stop and replay?** The window it was applied to is gone,
   so re-applying means remembering an intent across a window lifetime.
   **Recommendation:** no. Predictable beats clever; the user presses `p` again.

4. **Defaults.** 30 percent of monitor width, top-right, 16 px margin - 410x230
   at `(932, 42)` on this 1366x768 display. Omarchy's own PiP constant (600x338)
   would be 44 percent of this screen in both axes. **Recommendation:** accept
   the percentage-based defaults; do not adopt Omarchy's pixel constants.

5. **The opacity fix: contrib paste or runtime `setprop`?** The player is
   probably rendered at `0.985 / 0.96` because `default/hypr/windows.lua:6,25`
   tags every window and the anchored media-opacity rules at `apps/system.lua:40-51`
   do not match `omarchy-iptv`. This is an inference; gate G-11 settles it. The
   runtime alternative is `hyprctl setprop address:0x.. opaque true` as part of
   PiP-on - `opaque` is a real dynamic property on this build.
   **Recommendation:** keep it a contrib paste with the `size` syntax fixed;
   do **not** bolt an unrelated opacity fix onto PiP, where it would need its own
   restore path. If G-11 confirms the translucency, file it as its own small
   defect.

6. **Should the guide auto-enter PiP when it closes over a playing channel?**
   **Recommendation:** no. PiP is explicit or it is a surprise.

7. **The Lua interpolation boundary.** PiP builds a Lua expression inside one
   argv item, evaluated by the compositor, with a regex-validated address and
   integers only (4.11). `docs/ARCHITECTURE-PLAYER.md:781` requirement 9 is about
   process launching and does not name `hyprctl dispatch`, but the neighbourhood
   is close enough that a silent judgement call is the wrong move.
   **Recommendation:** allow it, on the record, with 4.11's two-value rule quoted
   in the ruling and enforced twice in `Model.js`.

8. **`Model.focusPlayerArgv()` is probably already broken.**
   `Model.js:2945-2947` emits the legacy form `hyprctl dispatch focuswindow
   class:omarchy-iptv`; this machine runs `configProvider: lua`, where
   `hyprctl dispatch` wraps its argument as `return hl.dispatch(<arg>)` and the
   legacy name lookup lives on an unreachable branch. `tests/Model.test.js:455`
   mirrors the constant and cannot see it (the exact `CLAUDE.md` 12 failure).
   Gate G-1 settles it. **Recommendation:** if G-1 confirms, file it as a P2
   defect and fix it inside lane V1 in this wave - the fix is the same
   `pipLuaDispatch` builder, applied to focus.

9. **Plan revisions.** Add M2-05-00 (gate) and re-estimate M2-05-02 from S to M.
   **Recommendation:** accept; the ten-line dispatch sequence is not the feature,
   and `docs/PLAN-M2.md:77`'s "cheap now" reads as true only for the mechanism,
   not for the correctness around it.

---

## 13. Rulings and gate results (appended after M2-05-00 and M2-05-01)

*Empty. The gate lane appends the G-1..G-13 results table here with the exact
command output for each row; the PO appends PIP1..PIP9 here and mirrors them in
`docs/STATUS.md`. No lane writes code against this section while it is empty.*

## 13. Product owner rulings (2026-09-14)

Design accepted. The investigations mattered: three skeptics found twenty-three
wrong claims between them, including the belief that the player could do this
by itself. It cannot, and that is now proven rather than assumed.

| # | Ruling |
|---|---|
| PIP1 | Drop the modified-Enter shortcut and ship the single key. The host's own key handling swallows that key and reports no modifier, so the shortcut is not merely awkward, it is undeliverable. Amend the interaction spec to say the reservation was released and why, so nobody re-reserves it. |
| PIP2 | No new bar gesture. Every gesture is already spoken for and this feature is not worth displacing one. A tooltip line when it is on, the command verb, and an optional keybinding snippet are enough. |
| PIP3 | Picture in picture does not survive stopping and replaying. The window it applied to is gone, and remembering an intent across a window's lifetime to re-apply it later is the kind of cleverness that surprises people. Press the key again. |
| PIP4 | Take the proportional defaults, not Omarchy's fixed pixel size, which would occupy nearly half of this display in both directions. A box sized from the monitor is right on a laptop and right on a large screen. |
| PIP5 | Do not bolt the opacity fix onto this feature. It is an unrelated defect, and attaching it here would give it a restore path it has no business needing. If the gate confirms the player is being rendered translucent, file it as its own small defect and fix it on its own terms. |
| PIP6 | The guide never enters picture in picture by itself. It is explicit or it is a surprise. |
| PIP7 | The compositor expression is allowed, on the record, with a hard boundary. Only two kinds of value may ever enter it: a window address matched against the strict pattern, and integers already clamped to their ranges. No channel name, no playlist text, no free-form setting value, no string from any source the user or a provider controls, ever. Enforce it at construction and again at the call, and write a test that proves a hostile value is refused rather than escaped. This is adjacent enough to the argument-vector rule that a silent judgement call would have been wrong, which is why it is written down. |
| PIP8 | If the gate confirms the focus command is already broken, it is a defect of this wave and gets fixed here. Its test mirrors the constant instead of calling the code, so it passes while the shipped path fails. That is precisely the trap the project rules name, found again in already-released code, and it is worth more than the feature that uncovered it. |
| PIP9 | Mine, not asked. The honest description of this feature is a small window that follows you, not a window that stays on top. The compositor offers no always-on-top and we will not imply one. Any copy that promises it is wrong, and the limitation belongs in the README beside the others rather than only in this document. |

## 14. Corrections after the gate (product owner, 2026-09-14)

The gate proved most of this design and broke four pieces of it. Where the
gate and this document disagree, the gate wins: it ran the commands.

| # | Correction |
|---|---|
| PIP10 | The action argument is ignored. Float and pin toggle unconditionally, and asking to unset one on a tiled window floats it instead. Every such step must read the live state and act conditionally, never issue a blind instruction. The gate's own check gave a false pass here by starting from a state where the bug is invisible, which is worth remembering: a probe can confirm something that is not true if it only tries the easy direction. |
| PIP11 | Exit codes cannot detect failure. The compositor reports success for a dispatch aimed at a window that does not exist, and refusals arrive as text on standard output with a success code. The design's failure detection is unimplementable as written. Detect by reading the state back and comparing it against what was asked for, which the design already does for the restore path; extend that to be the only definition of success anywhere in this feature. |
| PIP12 | The worked example's coordinates are wrong. The formula and the live result agree with each other and not with the document. Correct the example rather than the formula. |
| PIP13 | The translucency is confirmed, so ruling PIP5 now applies for real: it is its own small defect, fixed on its own terms, and it does not get attached to this feature. |

### The defect this gate found in released software

The command that focuses the player window has not worked since v0.3.0, at
four call sites. It fails silently because nothing reads its result.

Its test is the part worth dwelling on. The test is green against the broken
code and red against the working fix, because it mirrors the constant the code
emits instead of exercising the path that uses it. A test in that shape does
not merely fail to catch the bug. It defends it: a developer who fixed the code
correctly would see a red suite and conclude they had broken something.

This is the fourth time this project has found a check that could not fail, and
the first time one has actively protected a defect. Rule 12 already forbids a
test that mirrors logic it could call. The fix for the command and the rewrite
of its test both belong in this wave, and the test must be shown red against
the broken code before it counts.

## 15. Ruling PIP14 (product owner, 2026-09-14)

Carry the player-side property that stops a channel change resizing the box.
Without it the feature breaks on the single most common thing a user does
while in picture in picture, which is change channel: the small window would
resize itself to whatever the next stream's dimensions happen to be, and the
carefully placed corner box would jump. It is one property set over a socket
the shell already holds, and it is restored on exit like everything else.

A feature that survives every exotic case and breaks on the ordinary one is
not finished.

## 16. Rulings PIP15 to PIP17 (product owner, 2026-09-14)

| # | Ruling |
|---|---|
| PIP15 | The dispatch spelling is chosen ONCE, by asking the compositor which configuration provider it runs, not by trying one form and falling back on failure. The gate established that the other form is a syntax error here, so a fallback is a guaranteed second failure, and it could never fire anyway because the return code cannot tell us anything. Amend section 4.3. A fallback that cannot be triggered and would not work if it were is worse than no fallback: it reads like safety. |
| PIP16 | My file-ownership split was wrong and this is my error, not the lane's. I gave the manifest to one lane and the test that pins the manifest against the model to the other, so the settings could not be declared by either without turning the gate red. Ownership must follow the coupling, not the subject matter: two files that a test asserts about each other are one unit. Integration lands them together. I am recording this because the ownership rule has otherwise worked well all project, and this is the shape that defeats it. |
| PIP17 | The unsettled gate item stays unsettled and is documented as such in the contributed snippet and the README, rather than being quietly presented as compatible. We have not established that behaviour, and a snippet that implies otherwise would be us guessing on the user's behalf in their own configuration file. |

## 17. Corrections after integration (product owner, 2026-09-14)

- Sections 4.3 and 4.10 are amended for ruling PIP15: there is no fallback
  spelling. The compositor is asked once which configuration provider it runs,
  and a provider that cannot parse the modern form takes this feature off the
  offer entirely rather than offering something that will fail.
- The only genuinely missing handover function was the monitor finder. The
  verifier, the on/off predicate and both snapshot helpers already existed
  under different names, which is worth noting because the request list read as
  four missing functions and was one.
- The feature's availability depends on the compositor's configuration
  provider, not merely on its version. The README says so.

### What integration caught, and why it is the step that earns its keep

Seven rules had been implemented separately by the two lanes. Three disagreed.

One would have left the toggle inverted after the user moved workspaces,
because the two implementations disagreed about whether being pinned is part of
being in picture in picture. One left a latent mismatch in how a marker is
read. And the third is the instructive one: the guide listened for an outcome
the service does not emit, and the interface layer silently tolerates a handler
for a signal that does not exist, so the footer was wired to nothing at all and
no test, gate or reviewer would have seen it. There is now a test comparing
every handler name against the signals that actually exist.

That is the fifth silent no-op this project has found in its own work. The
pattern is consistent enough to name: wherever two things are connected by a
NAME rather than by a call, nothing checks the connection, and the failure is
invisible rather than loud.
