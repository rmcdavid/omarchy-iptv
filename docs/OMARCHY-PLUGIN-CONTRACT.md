# Omarchy plugin contract — research digest (verified on this machine)

Everything below was read from the live install. Sources are cited so you can
re-read them. `$OMARCHY_PATH` = `/usr/share/omarchy` and is READ-ONLY.

## Versions and tooling present

| Thing | Value |
|---|---|
| Omarchy | 4.0.3 (`pacman -Qi omarchy`) |
| Quickshell | 0.3.1 |
| Qt | 6.11.2 (`qt6-declarative`, `qt6-base`) |
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
