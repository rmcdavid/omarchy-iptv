# Omarchy plugin contract — research digest (verified on this machine)

Everything below was read from the live install. Sources are cited so you can
re-read them. `$OMARCHY_PATH` = `/usr/share/omarchy` and is READ-ONLY.

## Versions and tooling present

| Thing | Value |
|---|---|
| Omarchy | 4.0.4-1 (`pacman -Q omarchy`, 2026-10-11; 4.0.3 when this table was first written) |
| Quickshell | 0.3.1 |
| Qt | 6.11.2 (`qt6-declarative`, `qt6-base`, `qt6-wayland`, all 6.11.2 on 2026-10-11) |
| Hyprland | 0.56.2 |
| mpv | 0.41.0 |
| python3 | 3.14.7, stdlib only (no pytest → use `python3 -m unittest`) |
| node | 26.8.1 via mise (dev-only; do not depend on it at runtime) |
| Present | jq, gum, fzf, curl, ffmpeg, wl-copy, yt-dlp, `omarchy-notification-send` |
| Absent | go, rustc, cargo, bun, walker, vlc, bats, shellcheck (socat present here but not guaranteed) |
| Qt tools | `/usr/lib/qt6/bin/{qmllint,qmltestrunner,qml,qmlformat}` (not on PATH) |

## Paths

- Shell source: `/usr/share/omarchy/shell/` → `shell.qml`, `Commons/` (Color,
  Style, Util, Border singletons, module `qs.Commons`), `Ui/` (module `qs.Ui`),
  `services/PluginRegistry.qml` (manifest schema of record), `plugins/` (first-party).
- Docs: `/usr/share/omarchy/shell/README.md`, `/usr/share/omarchy/shell/plugins/README.md`,
  `/usr/share/omarchy/shell/plugins/bar/README.md`.
- User plugins: `~/.config/omarchy/plugins/<plugin-id>/` (git checkout; saving any
  file there hot-reloads plugin code; `omarchy-shell shell rescanPlugins` forces it).
- Config: `~/.config/omarchy/shell.json` (mode 0600). Plugin settings live inline
  on the plugin's entry: bar widgets under `bar.layout.<section>[]`, other kinds
  under `plugins[]`. Third-party enabled ⇔ id present in shell.json.
- Menu extension: `~/.config/omarchy/extensions/omarchy-menu.jsonc` (hot reload).
- Keybindings: `~/.config/hypr/bindings.lua`, e.g.
  `o.bind("SUPER + SHIFT + T", "IPTV", "omarchy-shell shell toggle io.github.rmcdavid.iptv")`.
  Existing overlay bindings for reference: `SUPER CTRL + V` clipboard, `SUPER CTRL + E` emojis.
  Verified: `SUPER SHIFT + T` is FREE; `SUPER CTRL + T` is taken (Activity); `SUPER + T` toggles floating.
  Check conflicts with `omarchy menu keybindings --print` (format is `SUPER CTRL + X`).
- Installed third-party examples to copy patterns from:
  `~/.config/omarchy/plugins/no.koka.uptime-monitor/` (BarWidget.qml + Panel.qml + BarWidget.spec.qml),
  `~/.config/omarchy/plugins/io.github.nipsen.dell-power/` (Model.js + Model.test.js, README has a qmllint recipe at lines ~216-222),
  `~/.config/omarchy/plugins/vm.netspeed/` (bar widget + helper shell script).

## manifest.json (enforced by `omarchy plugin validate <dir>` and PluginRegistry.qml)

- `schemaVersion` must be the JSON number `1`.
- Required: `id`, `name`, `version`, `kinds`, `entryPoints`.
- `id` matches `^[A-Za-z0-9][A-Za-z0-9._-]*$`, no `..`, must NOT start with `omarchy.`.
- `kinds` non-empty array of: `bar`, `bar-widget`, `menu`, `overlay`, `panel`, `service`.
- Each kind needs its entry point key: bar→`bar`, bar-widget→`barWidget`,
  menu→`menu`, overlay→`overlay`, panel→`panel`, service→`service`. Values are
  relative paths, no `..`, must exist. No symlinks anywhere in the folder.
- Optional: `author`, `license`, `description`, `homepage`, `keepLoaded: true`
  (keeps an overlay/service mounted between summons and across hot-reload).
- `barWidget` block: `displayName`, `description`, `category`, `allowMultiple`,
  `defaultSection` (left|center|right), `defaults: {key: value}`, and
  `schema: [{key, type: string|integer|boolean, label, min, max, step, defaultValue}]`.
  Values are edited with `omarchy bar set <id> <key> <value> [--json]` and land inline
  on the shell.json entry; the widget reads them through `settings` / `setting(name, fallback)`.

## What the host injects

- Bar widget entry (extend `qs.Ui` `Panel` for icon+popup, or `BarWidget` for icon-only):
  `bar` (PluginBarApi), `moduleName` (your id), `settings` (inline entry object).
  `Panel` also gives `controller`, `opened`, `open()/close()/toggle()`, `barForeground`,
  `setting()`, `ipcTarget` + `manageIpc` (IpcHandler with open/close/show/hide/toggle).
- `bar` (Ui/PluginBarApi.qml): `foreground`, `barForeground`, `background`, `urgent`,
  `fontFamily`, `position`, `vertical`, `barSize`, `transparent`, `showTooltip(target, text)`,
  `hideTooltip(target)`, `run(command)`, `requestPopout/releasePopout(owner)`,
  `switchPanelFrom(owner, dir)`, `moduleWidgets(id)`, and `bar.shell` (PluginShellApi).
- `shell` (services/PluginShellApi.qml, scoped to your own id): `summon(id, json)`,
  `hide(id)`, `toggle(id, json)`, `isPluginOpen(id)`, `updateEntryInline(id, entry)`
  (persist settings: pass the FULL entry `{id, ...settings, changedKey}`), `serviceFor(id)`.
- Overlay entry: a root `Item` that declares `property var shell: null`,
  `property var manifest: null` (host fills them) and implements
  `open(payloadJson)`, `close()`, `toggle()`. Summoned from anywhere with
  `omarchy-shell shell summon|toggle|hide <id> '<json>'`; from QML via `shell.summon(...)`.
  Dismiss with `shell.hide(manifest.id)` so the host's open-state stays in sync.

## Overlay window recipe (from plugins/clipboard/Clipboard.qml and emojis/Emojis.qml)

```qml
import Quickshell; import Quickshell.Io; import Quickshell.Wayland; import QtQuick
import qs.Commons; import qs.Ui
Item { id: root
  property bool opened: false
  property color background: Color.menu.background   // theme tokens
  property color foreground: Color.menu.text
  property color border: Color.menu.border
  property var borderSpec: Border.surfaceSpec("menu", "border", border, Math.max(1, Style.space(2)))
  property color scrim: Color.menu.scrim
  property color selectedBackground: Color.menu.selectedBackground
  property color selectedText: Color.menu.selectedText
  property string fontFamily: Style.font.menuFamily
  PanelWindow { id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "omarchy-iptv"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore
    Rectangle { anchors.fill: parent; color: root.scrim }   // click-outside closes
    // centered card: Rectangle radius Style.cornerRadius, header with Ui.TextField
    // filter, ListView over a ListModel (displayModel), Ui.PointerMoveGate,
    // Ui.PanelKeyCatcher as keyCatcher with forceActiveFocus() on open.
  }
}
```

Style tokens seen in use: `Style.space(n)`, `Style.spacing.{panelPadding, md,
rowPaddingX, controlPaddingY, popupPadding}`, `Style.font.{family, menuFamily,
body, caption, subtitle, title, display}`, `Style.cornerRadius`, `Style.gapsOut`,
`Style.hoverFillFor(fg, accent)`, `Style.selectedFillFor(fg, accent)`.
Color tokens: `Color.{foreground, background, accent, urgent, muted}`,
`Color.menu.*`, `Color.popups.*`, `Color.bar.*`. Util: `Util.fileUrl(path)`,
`Util.shellQuote(s)`, `Util.alpha(color, a)`. Nerd Font glyphs render in the
menu font (JetBrains Mono Nerd is a hard dependency of omarchy).

## Bar popup recipe (from panels/tailscale/Panel.qml and uptime-monitor/Panel.qml)

`Panel { moduleName: "<id>"; manageIpc: false; KeyboardPanel { anchorItem; owner:
root; bar: root.bar; open: root.opened; focusTarget: keyCatcher; contentWidth:
panel.fittedContentWidth(Style.space(280)); contentHeight:
panel.fittedContentHeight(content.implicitHeight); PanelKeyCatcher { id: keyCatcher;
anchors.fill: parent; onMoveRequested/onActivateRequested/onCloseRequested/onTextKey
… } } }`. Bar icon: a `Text` with a glyph, `MouseArea` with
`acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton`, `onWheel` for scroll.
`PanelKeyCatcher` signals: `moveRequested(dx,dy)` (arrows/hjkl), `activateRequested`
(Enter/Space), `returnRequested`, `closeRequested` (Esc), `deleteRequested` (x),
`tabRequested(dir)`, `textKey(text)`; set `blocked: editor.activeFocus` when a
TextField is focused.

## Process, files, IPC (Quickshell.Io)

- `Process { command: ["prog", "arg"]; running: true; stdout: StdioCollector { onStreamFinished: … this.text } ; onExited: (code, status) => … }`.
  Argv arrays only. Never build `bash -c "… ${untrusted} …"`.
- `Quickshell.execDetached(["mpv", url, …])` for fire-and-forget.
- `FileView { path: …; watchChanges: true; onLoaded: …; text(); setText(s) }` for JSON caches/state.
- `IpcHandler { target: "io.github.rmcdavid.iptv"; function play(url: string): string { … } }`
  reachable as `omarchy-shell io.github.rmcdavid.iptv play <arg>` (`omarchy-shell <target> <fn> [args]`).
- `Quickshell.env("HOME")`, `Quickshell.env("XDG_RUNTIME_DIR")` (= /run/user/1000 here).
- Notifications: `Quickshell.execDetached(["omarchy-notification-send", "Title", "Body"])`.

## Lifecycle commands

```
omarchy plugin validate <dir>                 # schema check (run before every commit)
omarchy plugin list --json                    # discovery + enabled state
omarchy-shell shell rescanPlugins             # hot reload
omarchy plugin enable <id> [placement]        # bar widget goes to defaultSection
omarchy plugin disable <id> ; omarchy plugin remove <id> --yes
omarchy bar set <id> <key> <value> [--json]   # write a setting inline
omarchy-shell shell toggle <id> '{}'          # summon/hide an overlay
omarchy-shell shell listPlugins
omarchy dev ui preview [section]              # qs.Ui component gallery
```

Local install for QA on this machine: copy or `git clone` the repo to
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv/` (no symlinks!), rescan, enable.

## Testing conventions used by existing plugins

- Pure logic in `Model.js`, loaded from QML with `import "Model.js" as Model` and
  from node with `require("./Model.js")` (see how dell-power guards
  `module.exports`; QML `.js` files must not use ES module syntax).
- `node Model.test.js` style runner (console PASS/FAIL, nonzero exit on failure).
- `BarWidget.spec.qml` is a `QtTest` `TestCase`; run with
  `/usr/lib/qt6/bin/qmltestrunner -input <file>`.
- `qmllint` needs the `qs` modules on an import path: `mkdir -p /tmp/qmlroot/qs;
  ln -sfn /usr/share/omarchy/shell/Commons /tmp/qmlroot/qs/Commons; ln -sfn
  /usr/share/omarchy/shell/Ui /tmp/qmlroot/qs/Ui; /usr/lib/qt6/bin/qmllint -I /tmp/qmlroot <file>`.
- Python helpers: `python3 -m unittest discover -s tests`.

## Menu entry snippet (user adds to ~/.config/omarchy/extensions/omarchy-menu.jsonc)

```jsonc
"iptv": {"icon":"󰕧","label":"IPTV","aliases":["tv","iptv"],"action":"omarchy-shell shell toggle io.github.rmcdavid.iptv"},
```

## mpv facts

mpv 0.41 supports `--input-ipc-server=<path>`, `--force-window=immediate`,
`--title=<s>`, `--force-media-title=<s>`, `--profile=<p>` (`low-latency`, `fast`),
`--user-agent`, `--http-header-fields`, `--referrer`, `--hwdec=auto-safe`.
`--wayland-app-id=<s>` is available (verified; default "mpv"), use it for window rules / focus. JSON IPC over the socket: `{"command":["loadfile",url,"replace"]}`,
`["stop"]`, `["quit"]`, `["get_property","media-title"]`, `["observe_property",1,"idle-active"]`.
Drive the socket from the Python helper (stdlib `socket`); socat exists here but is not an omarchy dependency, so do not rely on it.

## Verified host behavior: `barConfig` is published one write behind

Found the hard way in v0.2.0 and confirmed on the live shell (defects
D-LIVE-20 and D-LIVE-21). Any plugin that writes its own settings must know
this.

`shell.updateEntryInline(id, settings)` (shell.qml:1078) compares the proposed
entry with the stored one and returns `false` WITHOUT persisting when nothing
changed (line 1114). A `false` return therefore means "already stored", not
"the write failed". Treating it as a failure produces a spurious error.

On a real change it calls `persistShellConfig` (line 109), which assigns
`shellConfig` and writes the file. `onShellConfigChanged` (line 66) emits
`pluginsChanged()`, a `Connections` block (line 1052) calls `syncPluginApis()`
(line 861), and that assigns every plugin's `shellApi.barConfig` from
`publicBarConfig()` (line 326), which reads the `barConfig` binding declared at
line 116.

The trap: a QML change handler runs BEFORE bindings on the same property
re-evaluate, so `publicBarConfig()` hands out the PREVIOUS bar configuration.
An external change, such as `omarchy bar set` from a terminal, survives this
because the user-config `FileView` re-reads the file and produces a second
`shellConfig` assignment that flushes the first. A plugin's own write produces
no second assignment, because `FileView.setText` does not retrigger its own
watcher, so the plugin NEVER receives the echo of its own write.

Consequence for plugin authors: never wait for the host to echo your own
settings back before updating your UI. Apply your own write locally in the
same turn, and drop that local override as soon as the host reports any value
other than the one you wrote, so external changes still win. Keep the echo
path idempotent so a late or duplicate echo is a no-op.

Evidence: with an instrumented service, one `updateEntryInline` call produced
24 `settingsChanged` notifications, every one carrying the OLD value, and a
switch never observed a cache load within 40 seconds. The behavior is pinned
by `tests/Model.spec.qml::test_hostEchoLagsByOneWrite`, which reproduces it in
both binding declaration orders.

**Upstream status, 2026-10-12.** Reported as omacom/omarchy#11852 on
2026-09-14; confirmed by the maintainers' bot on 2026-10-11 ("reproduced on a
worker built from the Omarchy ISO, running the shell from current quattro")
and FIXED in omacom/omarchy#15082 (open, awaiting maintainer review as of
2026-10-12 00:58 UTC): `publicBarConfig()` reads `shellConfig` directly
through `currentBarConfig()`, so every path that hands a plugin its bar
config publishes the CURRENT one, and the host's new
`test/shell.d/plugin-own-settings-test.sh` reads the value back straight
after the write. `updateEntryInline()` returning `false` for "nothing
changed" is unchanged and documented as such. What this means here, read
against the code rather than assumed: the plugin is correct under BOTH
hosts, because `Model.ownWriteInForce` holds the local override only while
the host still reports the PRE-write value and drops it on any other value
-- the echo of our own write included -- after which `settings` is the host's
copy carrying the same values; the echo path was built idempotent for
exactly this. Round 5 of D-SINK-19 (R16, 2026-10-12) adds a second SHAPE of
own write and it behaves the same way: before the first state load (round
6) and while a state write is parked, in flight or failed the logo toggle
writes `{ showLogos }` alone with the entry's source keys as the host
PUBLISHES them (patch-only; `ARCHITECTURE-SOURCES.md` 4.3; on this
one-write-behind host that copy can be one write old, which is D-SINK-20), and its record is made against the host value exactly as
the full write's is, so under the lagging host the override holds
`showLogos` until the host catches up and lapses on the echo to the same
value, and under the echoing host it is recorded against the already-echoed
value and is inert rather than lapsed -- `inForce true` there is not a
stale override (lane A's DQ-U4). The node driver asserts both shapes for
both hosts (`R16 (lag host)` / `(echo host)`: `the patch-only write is
recognised as our own`, lane-key-u1); the echoing host is still modelled,
not run (D-HOST-4 below). Round 6 pins the other half of rule 9 in that
writer: the funnel composes the owned patch from `settings` -- the host's
publish with our own last write laid over it -- and never from
`hostSettings`, the bare publish. On this host the difference is one write,
and composed from the publish the key mirror's heal after a toggle carried
the PRE-toggle `showLogos` back to disk (D-LOGO-2's shape); that one-token
mutation read node 2,162 / 0 and live 64 / 0 on lane-key-u3, and on
lane-key-v1 it reddens 7 node checks, among them a structural pin over the
call and the driver case `a patch-only toggle on a failed disk, then the key
mirror's heal write once the disk recovers -- showLogos stays as toggled`
under the lagging host (lane A, 2026-10-12). On the echoing host the two
are equal, so the mutation reddens no echo-host case (all seven are the
structural pin or lag-host cases); the code is right under both hosts
without knowing which one it meets. Round 7 (R17, 2026-10-12) found the one
place where that was NOT true, and it is rule 9's exact hazard: an `epgUrl`
left on the entry while no source is active (R12) survived a switch only
because THIS host republished the pre-strip entry one write late and the
next reconcile consumed it. On the echoing host the key mirror's write
stripped it and the host published the stripped entry at once, so nothing
was left to adopt -- the plugin had been depending on the host's lag for its
own state. The fix does not consult the host: the switch and the probe
commit land a pending input on the record becoming active in the same turn
(`Model.adoptPendingEpg`), and every owned write leaves an input nothing has
consumed on the entry (`Model.retiredInputsToKeep`). What is NOT yet true
[amended 2026-10-12, round 7]: `scripts/dev-harness/shell.qml` modelled the
one-write-behind host only until round 7; it now has an echo lever --
`run.sh --host echo` makes `syncPluginApis` publish `shellConfig.bar` at
once, with no intermediate stale publish (a fake that published the old bar
first would hand the plugin this host's accidental rescue on the echoing
host too, more forgiving than either real host), and `ipc hostEntry`
reports `host` -- and key-scenario U5-U7 run on it (lane A, lane-key-w1:
U6 red on `--baseline lane-key-v2`). The other own-write scenarios (E6, the
key-mirror segments, the L toggle) have not run both ways; that, and
re-verifying this section on the first release carrying #15082, is what
remains of D-HOST-4 on the board. The section above stays
as the verified behaviour of every Omarchy up to and including 4.0.4.

## Verified host renderers for the strings the plugin hands over (2026-10-02)

The plugin hands the host five kinds of string, most of them carrying
provider data (field labels are the plugin's own literals), and each is
rendered by a host file the plugin cannot change. Read on omarchy 4.0.4 on
2026-10-02 during D-TEXT-1, and pinned by `tests/test_host_text_format.py`,
which goes red on this machine when a host update changes or removes the
declaration on one of these elements -- each pin is anchored on the
element, by id or by the property that binds the plugin's string. A moved
line stays green: the line numbers below are for the reader, not the test.
A red there is a re-measurement, not a failure of this plugin:

| string | host file | format |
|---|---|---|
| group names, field labels, mpv track titles (`PanelSectionHeader`) | `Ui/PanelSectionHeader.qml:17` | `Text.PlainText` |
| confirm-dialog message, and its button labels (`ConfirmDialog`) | `Ui/ConfirmDialog.qml:72` (message), `:109` (labels) | `Text.PlainText` |
| the bar widget's tooltip | `plugins/bar/Bar.qml:1338` | `Text.PlainText` |
| mpv's window title, the channel name after the first zap | `plugins/bar/widgets/ActiveWindow.qml:32` | `Text.PlainText` |
| a failure toast's summary / body (`omarchy-notification-send`) | `plugins/notifications/components/NotificationCard.qml:166` / `:184` | summary `Text.PlainText`; body `Text.StyledText` behind `NotificationLogic.js` `stripImageTags` |

So a `<b>` in a channel name can restyle a failure toast's body and
nothing else; no host renderer fetches an image out of a plugin string.
The daemon that owns `org.freedesktop.Notifications` here is the shell
itself (`busctl --user status org.freedesktop.Notifications` names the
quickshell pid), not mako or dunst, so Pango markup rules do not apply.


## QML `Image` and Qt's allocation limit on a JPEG behind `sourceSize` (verified 2026-10-09)

Qt 6.11.2. The image allocation limit (`QImageReader::setAllocationLimit`,
`QT_IMAGEIO_MAXALLOC`, default 256 MiB) is consulted when a QML `Image` loads
a file, but for a JPEG with `sourceSize` set it is compared against the image
AFTER libjpeg's scale denominator, not before. Measured by the lead on a
304-byte progressive JPEG whose header declares 20000x20000, through an
`Image` declared as `Guide.qml` declares the row slot (`sourceSize` 44):
`Image.Error` at 5, 7, 10 and 20 MiB; `Image.Ready` and 840 MB peak RSS at
26 MiB and at the default. `ceil(20000/8)^2 * 4` is 23.8 MiB, between the
two. The format's largest side is 65535 and `ceil(65535/8)^2 * 4` is
268,435,456 bytes, exactly the default, so no JPEG the format can express
exceeds the default on this path. The PNG, GIF and WEBP handlers decode at
full size and hand the limit the real number: seven over-bound files of those
types, rewritten headers and honestly huge valid files alike, refused at the
control's 72 MB. `Image` loads a local file by content and not by its name
(`RULING-LOGOS.md`), and offers no property that bounds the dimensions a
header declares; the plugin's bound is in the helper (`ARCHITECTURE.md`
8.12).

**Which cap each figure was measured under, because the two mechanisms give
different answers for the files that exceed them.** The lead's figures above
(2026-10-09) were taken with a user-session memory scope of 1.5 GB around the
Qt process, which SIGKILLs a process at the cap: the 20000x20000 rows
finished under it (840 MB and 1,239 MB) and the two 65500x65500 progressive
rows did not (killed at 1.5 GB, 1.5 s in, peak unmeasured). Everything in
this repository that decodes an over-bound file now runs instead under an
ADDRESS-SPACE rlimit of 2.5 GB on the qml process alone -- util-linux
`prlimit --as=2500000000 -- env QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qml <probe>`,
which sets `RLIMIT_AS` on itself and execs the runtime in place, so the limit
holds exactly that process and the reporter reads `ru_maxrss` from outside it
(harness lane, 2026-10-11). Under `RLIMIT_AS` an allocation the limit cannot
hold fails inside the process and Qt reports `Image.Error` (the probe exits
1) rather than being killed: the grayscale 65500x65500 progressive JPEG is
refused 325 MB in after 0.6 s, the 3-component one at the 72 MB control
before anything is touched. Every other row reproduces to the megabyte under
both (72 control, 839 and 1,239 for the two 20000x20000 progressive bombs,
454 for the 176-byte baseline 65500x65500, 347 for the honestly-huge valid
12000x12000; 36 rows judged from the tree (37 with `--extra`), 0 DIFF, `scripts/dev-harness/spikes/logo-decode-bomb/run.sh`
and its README). The control reads 72 MB at `--as` 1.5, 2.5 and 4.0 GB
alike (lead, 2026-10-11); 2.5 GB is the value because Qt offscreen maps
about a gigabyte of address space before it decodes anything and the
1,239 MB bomb has to fit for the finding to be measured rather than cut off.
The reason the rlimit is the mechanism and not the scope is in
`ARCHITECTURE.md` section 6 (the marketplace capability scan reads the scope
tool's name as a service-management capability in any command line of a tracked .sh/.py/.js/.qml file, or a shell fence of the root README (comment-only lines are skipped, as upstream skips them, and no other .md file is read)).

There is no automated pin on this Qt behaviour, unlike the host text formats
above, but there is a gate that observes the sink on every commit:
`scripts/dev-harness/logo-scenario.sh check-tree`, run by `scripts/check.sh`
with a floor of 33 `PASS` lines, decodes the announced control under the
rlimit and must read `Image.Ready` under 160 MB, and reports which of three
things happened to the 304-byte bomb (withheld and gone, withheld but the
file survived, or announced). A Qt that started scaling PNG during decode
would not redden it, because the shipping helper withholds every bomb before
the probe sees one; re-measure on a Qt bump with
`scripts/dev-harness/spikes/logo-decode-bomb/run.sh`, which judges every row
against a band and exits 1 on a DIFF, recorded under "Fifth maintainer
finding, 2026-10-09" in `docs/QA-RESULTS.md`. The bound covers all four types
so that a change here is not a regression in silence.


## `omarchy-refresh-shell` RESETS the user's config (verified 2026-10-07)

Its name reads like "reload the shell". It is not. Its own header says
`omarchy:summary=Reset shell.json to Omarchy defaults`, and its body is two
lines:

```
omarchy-refresh-config omarchy/shell.json
omarchy-bar defaults
```

Run during the 0.13.0 install update, it replaced `~/.config/omarchy/shell.json`
with the stock file. Measured by diffing against a snapshot taken minutes
earlier: it removed this plugin's bar entry together with its `playlistUrl`,
`epgUrl` and `showLogos` settings, removed three other third-party widgets, and
substituted the default `omarchy.tailscale` and `omarchy.power`. It printed
`"plugins": []` and `Restored the default Omarchy bar` while doing it. The
shell then restarted on its own, because the config write is what triggers a
reload.

**Never use it to restart the shell.** It is a destructive reset of user
configuration, and for a plugin whose settings live in `shell.json` it destroys
exactly the thing the plugin is configured by. Restoring the snapshot and
waiting a few seconds was enough: the running shell re-read the file and the
plugin came back reporting its channels and EPG, with no second restart.

The neighbouring commands, by their own summary lines:

| command | what it says it does |
|---|---|
| `omarchy-refresh-shell` | Reset shell.json to Omarchy defaults |
| `omarchy-launch-shell` | Launch the Omarchy shell with its log kept in the journal |
| `omarchy-restart-app` | Restart an application by killing it and relaunching via uwsm |

**ANSWERED 2026-10-08, and the answer was a command this table did not
list.** `omarchy-restart-shell`, whose own summary is "Restart the Omarchy
shell", is the supported one. Its body contains no reference to `shell.json`,
`omarchy-refresh-config` or `omarchy-bar defaults` at all, and
`omarchy-launch-shell` names it in a comment as the thing that performs a
deliberate stop: "a clean exit is a deliberate stop (omarchy-restart-shell
starts its own replacement)". Used for the 0.13.1 install update it restarted
the shell in 250 ms and left `~/.config/omarchy/shell.json` byte-identical to a
snapshot taken immediately before, with the plugin reporting the new version
and its channels and EPG intact.

So the pair to keep straight is:

| command | what it does |
|---|---|
| `omarchy-restart-shell` | restarts the shell, touches no configuration |
| `omarchy-refresh-shell` | RESETS `shell.json` to Omarchy defaults |

The names differ by one word and the outcomes differ by every plugin setting
the user has. The reason the wrong one was reached for is worth recording: a
listing of `omarchy-restart*` and `omarchy-launch*` was read as if it were
complete when it had been truncated, so the right command was never seen. See
D-HOST-3.

## The host's settings file is named from `$HOME`, not `$XDG_CONFIG_HOME` (verified 2026-10-09)

`/usr/share/omarchy/shell/shell.qml`:

```
line 23:  property string home: Quickshell.env("HOME")
line 32:  readonly property string userConfigPath: home + "/.config/omarchy/shell.json"
```

The file contains no other reference to `XDG_CONFIG_HOME`. So the host writes
`$HOME/.config/omarchy/shell.json` and nothing else, whatever the XDG variable
says.

This matters because D-SINK-18 has the helper change that file's mode. A helper
that derived the path from `$XDG_CONFIG_HOME` would, on a machine where that
variable points elsewhere, tighten a file the host never writes and report
success while the credential went into the host's real file untouched. That is
what the first version did, on the lead's own instruction, and two reviewers
found it independently.

`tests/test_host_config_path.py` makes the join a call rather than a name: it
reads the property out of the host's own source, asserts the expression, asserts
the host still takes its home from `$HOME`, and asserts the helper's path equals
the host's on this machine including with `XDG_CONFIG_HOME` moved. It skips
where Omarchy is not installed, so it constrains this machine and never a CI box.

## The host kit's `TextField` reads the whole clipboard on every change while editable (verified 2026-10-11)

Found during D-CLIP-1 (omarchy-plugin-marketplace#11077). The register of
the sink, the measurements and the plugin's fix are `docs/ARCHITECTURE.md`
section 6; this section holds the HOST and Qt facts the plugin cannot
change and relies on.

**The Qt fact, read at the release tags, not at branch heads.** On the Qt
this machine runs, `QQuickTextInput::q_canPasteChanged()` -- the slot every
`TextInput` connects to `QClipboard::dataChanged` at construction -- is,
in v6.11.2 (`src/quick/items/qquicktextinput.cpp:3010`, code.qt.io `plain`
endpoint, 2026-10-11):

```
    if (!d->m_readOnly) {
        if (const QMimeData *mimeData = QGuiApplication::clipboard()->mimeData())
            canPaste = mimeData->hasText() && !mimeData->text().isEmpty();
    }
```

v6.12.0 (`:3009`) is identical. `text()` reads the entire offer; on Wayland
that is a pipe with a 1 s timeout per read, no total limit and no deadline
(the lead's read of qtbase 6.12 `qwaylanddataoffer.cpp`). `m_readOnly` is
the only switch. History, each date checked against code.qt.io on
2026-10-11: `c82ef988` added the `text()` call on the 6.11 branch
(authored 2026-02-16, committed 2026-02-18, pick of `6c07e2a7`; shipped in
6.11.2); `7d0a433a` removed it (authored 2026-08-29, committed to 6.11 on
2026-09-15, pick of `ef692a52` / `bcbfae67`, `Fixes: QTBUG-149610`). The
`6.11`, `6.12` and `dev` branch heads read `canPaste = mimeData->hasText();`
today; no v6.11.3 tag exists and v6.12.0 carries the read. So the fix lands
here only when Arch ships a Qt built past 2026-09-15 on 6.11, or a 6.12.1;
`pacman -Q qt6-declarative` is the check, and the spec's
`test_readOnlyFieldPremises` keeps the plugin's own field read-only
whatever it says.

**The host fact.** `/usr/share/omarchy/shell/Ui/TextField.qml` (omarchy
4.0.4) is `TextField { ... }` from `QtQuick.Controls` with the kit's chrome
and `echoMode: password ? TextInput.Password : TextInput.Normal`; it never
sets `readOnly`, so every instance is editable unless its caller says
otherwise, and the plugin's field inherits that default. The kit's
`NumberField.qml:80` sets `readOnly: !spin.editable`. Editable instances the
host itself declares (a grep over shape, `TextField {` and `readOnly`,
2026-10-11; which of them exist while their panel is closed is UNVERIFIED):

| host file | line | field |
|---|---|---|
| `plugins/panels/network/Panel.qml` | 1841, 1865 | the passphrase prompts (the precedent D9 cited) |
| `plugins/panels/clock/Panel.qml` | 381, 404 | two fields |
| `plugins/panels/weather/Panel.qml` | 615 | one field |
| `plugins/panels/tailscale/Panel.qml` | 601 | one field |
| `Ui/MultiSelect.qml` | 407 | the filter field |
| `Ui/SearchableDropdown.qml` | 205 | the filter field |
| `plugins/dev-gallery/GalleryPanel.qml` | 1337, 1358 | demo fields |
| `plugins/lock/LockView.qml` | 146 | `readOnly: root.authenticatingPassword` -- editable while LOCKED |
| `plugins/polkit/PolkitAgent.qml` | 323 | `readOnly: root.submitted \|\| root.errorFlash` |

The plugin cannot change any of these; the draft report to Omarchy is the
first quoted block in `docs/ARCHITECTURE.md` section 6's D-CLIP-1 entry.

**What the plugin relies on, measured in the QML spec rather than assumed
(`test_readOnlyFieldPremises`, lane commit 51866a3):** a `readOnly: true`
`TextInput` on Qt 6.11.2 keeps its caret, `cursorRectangle`, selection,
Home / End and `Ctrl+A` native; `Ctrl+C` copies natively (measured by
pasting the copied selection into an editable control under the offscreen
platform, whose clipboard is the test process's own); a mouse click places
the caret and a drag selects, with `selectByMouse` at its default, which is
`true` on this Qt and is what the host's `TextField` inherits (measured on
a dedicated read-only control that no other spec input overlaps -- every
other one sits at (0, 0), where a synthetic click lands on the topmost);
refuses typing, `Backspace` and `Ctrl+V`; parks its caret at the end on
every bound `text` write, synchronously; draws NO caret and never
instantiates a `cursorDelegate`; and delivers `Ctrl+V` and `Shift+Insert`
as `StandardKey.Paste` and `Ctrl+X` / `Shift+Delete` as `StandardKey.Cut`
through `Keys.forwardTo`, a bare `Insert` as neither. At 44b250b this
paragraph already claimed `Ctrl+C` and mouse selection were pinned; they
were true by source and pinned by nothing (rule 14's shape, found by the
adversarial review), and the two pins were added at 51866a3. By the
v6.11.2 source (same file): `paste()` (`:2184`), `cut()` (`:2155`, gated
on `echoMode == Normal` as well, which `Model.cutApplies` mirrors so the
password field's `Ctrl+X` stays the no-op it is natively,
`test_passwordCutIsNativelyANoOp`) and `undo()` (`:2200`) are each gated
on `!m_readOnly`; the programmatic `insert()` (`:2229`) is NOT, so a
read-only input can still be edited by a caller, which is why the plugin
writes the model and never `insert`s. The input-method COMMIT is the same
shape one function over, and belongs beside `insert()` here:
`QQuickTextInputPrivate::processInputMethodEvent` (`:3583`-`:3714`) inserts
the commit string (`:3625`, `internalInsert(event->commitString())`) with
no `m_readOnly` check anywhere in it. What keeps it out is the input
context, not the control: `setReadOnly(true)` clears
`ItemAcceptsInputMethod` (`:729`), `inputMethodQuery(ImEnabled)` returns
that flag (`:2054`), and Qt's compose plugin and the Wayland text-input
path both refuse to compose when it is false
(`qcomposeplatforminputcontext.cpp:72`, `qwaylandinputcontext.cpp:260`).
So "only the plugin edits it" holds for every input context that honours
`ImEnabled`, and would not for one that does not: a commit reaching the
item would change the control's text without the model, and the binding
would silently re-assert the model on the next write. What a dead key
actually does on this rig was measured by the adversarial review under a
nested cage (QT_QPA_PLATFORM=wayland, `wtype -k dead_acute -k e`): the dead
key arrives as a bare press with empty text and the next key as ordinary
text, so the base letter is typed and the accent dropped. A composed
commit from a real IME is still UNVERIFIED by observation: none is
installed on this machine, and QtTest QML cannot construct a
`QInputMethodEvent`.

**What the plugin uses instead.** `wl-paste` 2.3.0 (`wl-clipboard`, present
here) read through wlr-data-control, which needs no keyboard focus, from a
child of the plugin's HELPER and not of the shell (R8, 51866a3): the
helper's `clipboard` verb reads at most 32 KiB of it under a 5 s deadline,
terminates it at the cap, and hands the shell one JSON line of at most
8,192 characters, so the shell never holds the clipboard's size (measured:
+0 MB over a paste of a 100 MB offer, where the shell's own `wl-paste`
child at 44b250b cost it +298..+304 MB and kept most of it). The host does
not provide a clipboard verb of its own; `Quickshell.clipboardText`
(quickshell-core.qmltypes) is the same `QClipboard::text()` read in the same
process and is not used, and the plugin's own unreachable `clipboardText()`
in `Guide.qml` was deleted at 51866a3.

## Verified host behavior: `updateEntryInline` stores every key it is handed, declared or not (verified 2026-10-11)

Why it matters. D-SINK-19 mirrors the active source's key into the bar entry
as `sourceKey`, a key `manifest.json` deliberately does not declare (declaring
it would offer the plugin's own mirror as a user setting with help text). The
recovery path `Model.adoptActiveSource` step 3 -- an install that lost
`state.json`'s pointer but still has its sources finds its way back through
the entry -- rests on the host KEEPING a key it was never told about, and that
premise had been read off the host's source and never measured.

Measured by running the host's OWN function, not a reimplementation of it:
`shell.qml:1078-1117` (`/usr/share/omarchy/shell/shell.qml`, Omarchy 4.0.4-1,
sha256 prefix `4a4b7694e5b9e0bd`) copied by line range into node with stubs
for `Util.canonicalWidgetId`, `Util.isPlainObject` and `persistShellConfig`,
over three stored configurations (the script, `host-undeclared-key.js`, and
its output sit in the docs lane's scratch; re-run it with
`sed -n 1078,1117p /usr/share/omarchy/shell/shell.qml > host-updateEntryInline.js && node host-undeclared-key.js`
after checking the function still ends at line 1117):

- **A. The entry is in `bar.layout` only** (the shape `omarchy plugin enable`
  writes). Handed `{id, sourceKey, showLogos, refreshMinutes}` over a stored
  entry that carried `playlistUrl`, the stored entry became exactly
  `{id, sourceKey, showLogos, refreshMinutes}`: the undeclared key is kept, and
  the key NOT handed over (`playlistUrl`) is GONE rather than emptied. The
  code is `var next = { id: stripped }; for (var k in settings) if (k !== "id")
  next[k] = settings[k]` (`shell.qml:1092-1093`); no schema is consulted. This
  is what lets `Model.entryWith` remove the retired URL keys by omission.
- **B. The same id is ALSO in the top-level `plugins[]` list.** Only the
  `bar.layout` copy is rewritten -- the `plugins[]` loop runs only `if
  (!foundInLayout)` (`shell.qml:1102`) -- and a `plugins[]` copy keeps whatever
  it had, `playlistUrl` included. The plugin never READS that copy (`barConfig`
  is built from `bar`), but no write of ours would remove a credential from
  it. On this machine `plugins` is `[]`, and `omarchy plugin enable` writes
  `{id}` objects into `bar.layout` (`services/PluginRegistry.qml:526`). Whether
  any supported command fills `plugins[]` is UNVERIFIED.
- **C. Handing back exactly what is stored** returns `false` and persists
  nothing (the one-write-behind section above; `shell.qml:1114`).

Two neighbouring facts, read rather than run:

- `omarchy bar set <id> <key> <value>` writes ANY key. `setBarWidget`
  (`services/PluginRegistry.qml:342-380`) finds the entry and does
  `entry[String(key)] = value`; nothing checks the key against the manifest
  schema, so a user can set `sourceKey` by hand (the plugin ignores a value
  naming none of their records, and consults it at all only when `state.json`
  names no source), and `omarchy bar set ... playlistUrl ""` stores an empty
  string, which the plugin treats as a no-op since D-SINK-19.
- `omarchy plugin disable` removes the entry and everything on it, the mirror
  included (`QA.md` TC-INST-05); the plugin's own `state.json` still names the
  active source, so re-enabling does not need the URL again.

## Quickshell `FileView` on this machine: what a reload means (D-SRC-15, measured 2026-10-11)

Not the Omarchy plugin API but the runtime every plugin's `FileView` sits on
(quickshell 0.3.1-1, Qt 6.11.2 as installed; re-measure on a Quickshell
update). Measured by the D-SINK-19 code lane with a purpose-built FileView
probe run by quickshell under a nested headless cage (lane A's
`fv/probe.qml` + `run-probe.sh`, in the lane's scratch directory, not in the
tree) and by the harness lane's key scenario (`scripts/dev-harness/
key-scenario.sh`, segments D and N). The service's `stateFile` is a FileView
with `watchChanges: true`, `atomicWrites: true` and `onFileChanged: reload()`,
and these four facts are what R9-R11 (`ARCHITECTURE-SOURCES.md`, round 3)
are built on:

- **`saved` fires once per `setText` -- for two back-to-back calls, and NOT
  for a burst (corrected 2026-10-12, round 4).** Two `setText` calls back to
  back delivered `saved, fileChanged, saved`; a third delivered `fileChanged,
  saved` (probe summary: `saved=3 failed=0 fileChanged=4 loaded=3`). So
  `setText` returning says nothing about the file. But a counter of `setText`
  calls is NOT the instrument either: lane A's 26-write probe under cage
  (2026-10-12) raised 25 `saved` + 1 `saveFailed`, `textChanged -> Tn`
  preceded every `saved #n text()=Tn`, after a burst of twenty `text()` read
  T19 while T20 was pending, a failed write read its own text and then
  `saveFailed`, and the last content asked for was always written last; the
  service under the same conditions coalesced 20 `setText` into 14 `saved`
  (15 on lane-key-s2), so a signal counter stuck at 5-6 for the rest of the
  session (and on lane-key-s2 read every later foreign reload as "save in
  flight"). "A write is in flight" is therefore decided by CONTENT
  (`Model.stateSaveLanded`: the view's text IS the last text asked for;
  `stateSavesInFlight` is 0 or 1 and keeps its name for the harness), and an
  earlier write's `saved` changes nothing. Whether a replaced queued write can
  ever be the LAST content is unmeasured (the probe and both live runs say
  the last content is always written; a Quickshell source read would settle
  it).
- **A bare chmod reloads, mode changed or not.** A chmod 0644 -> 0600 AND a
  chmod 0600 -> 0600 each delivered `fileChanged` followed by `loaded` with
  the file's text. That is inotify `IN_ATTRIB`, and it is the trigger of
  D-SRC-15: the helper's start-up `state init` chmodded the existing
  `state.json`, the FileView reloaded the PRE-adoption text while the first
  save was still parked, and the parked save then wrote the loss. It is also
  why the helper leaving a 0600 file alone (R10) is belt and braces and not
  the fix.
- **The view's own atomic write fires `fileChanged` too.** In the probe run
  no `loaded` followed it, while the service's `recentSaves` comment assumes
  one can; which it is was not settled (lane A's DQ-A7) and nothing depends
  on it, because `Model.reloadDisposition` ignores an own write by its text and a
  parked or in-flight save by its flag [corrected 2026-10-12, round 7: this
  said "count"; since R13 the in-flight input is 0 or 1, set when a write is
  asked for and cleared by content (`Model.stateSaveLanded`), so it is a flag
  that keeps a counter's name (OQ-C5)].
- **A FileView loaded over a MISSING path does not see the file being
  created by another process.** Over a fresh install (no state directory, no
  file) the helper's `state init` creates `state.json` under the parked
  adoption and no reload fires: `stateReloadsIgnored` reads 0 across the
  whole fresh start and the key scenario's N1-N4 are green on the very tree
  that drops D2. Whether the watch is installed by the first successful load
  or by the first own write is unmeasured (lane B's DQ-B8); a reader of
  `watchChanges` should not assume a missing file is watched.

`saveFailed` exists (`/usr/lib/qt6/qml/Quickshell/Io/quickshell-io.qmltypes:470`)
and its argument is an enum, never a path; until round 3 the service
connected to neither it nor `saved`, so a refused write was silent and the
entry mirror went out anyway (R11 is the gate). Since round 4 (R13, lane-key-t1)
`saveFailed` clears the in-flight flag by content, logs `state.json could not
be written (error N)` on every failure and emits
`sourcesPersistFailed("state_write_failed")` once per failure episode; the
key scenario's F segment drives it with the state directory 0500 under a
running shell (F4: logged with no `://` in the line, signalled exactly once;
lane B on lane-key-t2, 2026-10-12).
