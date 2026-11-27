#!/usr/bin/env python3
"""scripts/dev-harness/spikes/codebehind-reload/make-root.py -- the rig's two
quickshell roots, built from the HOST'S OWN TEXT.

  make-root.py OUT RIG_BLOCK [--bar] [--widgets] [--probe] [--hold-sync]

Copies /usr/share/omarchy/shell to OUT/a/shell and OUT/b/shell and writes, as
each copy's shell.qml, the host's shell.qml cut to the parts that load, reload,
disable and enable a plugin, with the rig's own block (RIG_BLOCK, rig.qml.in)
before its closing brace. Root a is the host's lines 1-13 byte for byte, the
`//@ pragma OmarchyLoadPatch` first among them; root b is the same without
that one line, which is the root an unpatched Quickshell runs. Nothing is run
here. The host files are pinned by sha256 (omarchy 4.5.0-3): an update to
any of them refuses until this list is read against it again.

KEPT, byte for byte, from /usr/share/omarchy/shell/shell.qml:
   1-23    the header (imports, pragma) through ShellRoot's two registries
  27-241   config: home, paths, shell.json FileViews and their loaders,
           Component.onCompleted (one line adapted, below), the bar ids
 279-1093  services: serviceHost, the plugin API types and factories
           (createScopedPluginShell 602, syncPluginApis 886), ensureService
           930, _syncServices 982, unloadPluginServices 1062, and the
           registry and widget-registry Connections
1102-1591  updateEntryInline 1107, panels (summon 1181, the panel
           Instantiator 1387 with its keepLoaded overlay Loader),
           syncPluginWidgets 1446, reloadPlugins 1517, finishPluginReload
           1529, the localPluginChanged and scanFinished Connections 1539,
           loadPluginWidget 1566
1747-1939  the `shell` ShellIpc target: rescanPlugins 1796,
           setPluginEnabled 1815 (omarchy-plugin-disable's call), enablePlugin
           1819 (omarchy-plugin-enable's call), summon, listPlugins; the rig's
           block goes in before line 1939, the root's closing brace
LEFT OUT: 24-26 (AppLibrary, BrightnessKeys, BackgroundIntro: launchers,
  brightness keys, the boot intro), 242-278 (the bar itself: Bar.qml and the
  bar-option Loaders, the session's bar), 1094-1101 (the AppLibrary
  Connections), 1592-1746 (global shortcuts registered with Hyprland, the
  omarchy-shell socket server, the image-selector IPC).
ADAPTED, each named on its line in the output with "RIG ADAPTATION":
  shell.qml 165  pluginRegistry.firstPartyDir points at an empty folder
                 (home + "/rig-no-first-party"), so the scan finds no
                 first-party plugin and _syncServices starts none of the
                 session's services (lock, idle, notifications, polkit, ...);
                 the scan, the registry and every function above are
                 otherwise the host's
  services/PluginRegistry.qml 708-715  reapOrphanedPluginWatchers's command,
                 a `pgrep -f` over every inotifywait on the machine, becomes
                 ["true"]: the rig kills its own watcher by the pid it records
                 (rig.qml.in's `watcherPid`, run.sh's record_watcher); onExited still starts the watcher
                 and the first rescan, as the host's does
The folder watcher (PluginRegistry.localPluginWatcher, inotifywait -m -r on
the plugins folder, 726-745) and its debounce (shell.qml's 150 ms
localPluginReloadTimer, 69-73) are the host's, unchanged.

OPTIONS (lane-dh15m, 2026-11-27, for ../barconfig-window/, D-HOST-15). With
none the output is the same, byte for byte, as without this paragraph.
  --bar        keeps 242-278 as well: the host's own bar (defaultBarComponent
               making plugins/bar/Bar.qml, defaultBarLoader, pluginBarLoader),
               so the bar's widget host asks for a plugin's API in the host's
               order. Its PanelWindows meet a cage with no layer shell.
  --widgets    leaves shell.qml 165 as the host wrote it (the first-party
               folder is the copy's own plugins/) and, in each copy, renames
               every first-party manifest that does not declare kinds
               exactly ["bar-widget"] to NAME.rig-off, but plugins/bar's
               own (omarchy.bar, kind bar), so the scan finds the host's
               first-party bar widgets -- each a component the shell compiles
               and registers, and each registration a syncPluginApis -- and
               no first-party service, overlay, panel or menu.
  --probe      LOGGING ONLY: inserts a call to the rig block's
               rigwBeforeApi(key, manifest, where) on its own line above
               shell.qml 958 (ensureService's `inst.shell = ...`) and above
               1005 (_syncServices's `kept.shell = ...`), which reads the
               host's API cache (_pluginShellApis and its descriptors) as
               createScopedPluginShell is about to, and logs it. The block
               must define rigwBeforeApi.
  --hold-sync  THE RED CONTROL: inserts, as syncPluginApis's (886) first
               statement, a return while the block's rigHoldSync is true, so
               a service's API keeps the barConfig createObject's property
               map gave it until the block releases it. The block must
               define rigHoldSync.
Each inserted line is named on itself with "RIG ADAPTATION".
"""
import hashlib
import json
import os
import re
import shutil
import sys

HOST = "/usr/share/omarchy/shell"
DEFAULTS = "/usr/share/omarchy/config/omarchy/shell.json"
PINS = {
    "shell.qml": "d6d99af10ca020ca2c578bc7f67bf674d954efc206012a71af6769c662c37c37",
    "services/PluginRegistry.qml": "3acf0f442fd8da5b9acd1eaf4cd19b7617cbe22d29bedb22e5a3bd527a8421d1",
}
KEEP = ((1, 23), (27, 241), (279, 1093), (1102, 1591), (1747, 1938))
CLOSE = 1939
FIRST_PARTY_OLD = "    pluginRegistry.firstPartyDir = shell.firstPartyPluginsDir\n"
FIRST_PARTY_NEW = ("    pluginRegistry.firstPartyDir = shell.home + \"/rig-no-first-party\""
                   "  // RIG ADAPTATION: shell.qml 165\n")
REAPER = (708, 715)
REAPER_NEW = "    watcherReaper.command = [\"true\"]  // RIG ADAPTATION: PluginRegistry.qml 708-715\n"
OPTIONS = ("--bar", "--widgets", "--probe", "--hold-sync")
BAR = (242, 278)
# Lines the options insert ABOVE a host line, each held to that line's text.
PROBE_AT = {
    958: ("      if (\"shell\" in inst) inst.shell = shell.pluginShellFor(manifest)\n",
          "      shell.rigwBeforeApi(key, manifest, \"ensureService\")  // RIG ADAPTATION (logging only): above shell.qml 958\n"),
    1005: ("          if (kept && \"shell\" in kept) kept.shell = shell.pluginShellFor(m)\n",
           "          shell.rigwBeforeApi(id, m, \"kept\")  // RIG ADAPTATION (logging only): above shell.qml 1005\n"),
}
SYNC_AT = 886
SYNC_OLD = "  function syncPluginApis() {\n"
SYNC_NEW = ("    if (shell.rigHoldSync === true) { shell.rigNote(\"syncPluginApis held\"); return }"
            "  // RIG ADAPTATION (red control): shell.qml 886\n")
WIDGET_ONLY = ["bar-widget"]


def lines_of(rel):
    path = os.path.join(HOST, rel)
    with open(path, "rb") as fh:
        data = fh.read()
    got = hashlib.sha256(data).hexdigest()
    if got != PINS[rel]:
        raise SystemExit("make-root.py: %s is %s, not the pinned %s; read the kept ranges against it again"
                         % (path, got, PINS[rel]))
    return data.decode("utf-8").splitlines(keepends=True)


def keep_ranges(opts):
    if "--bar" not in opts:
        return KEEP
    out = []
    for first, last in KEEP:
        out.append((first, last))
        if last == BAR[0] - 1:
            out.append(BAR)
    return tuple(out)


def root_text(shell, block, pragma, opts=()):
    out = []
    for first, last in keep_ranges(opts):
        for n in range(first, last + 1):
            line = shell[n - 1]
            if n == 1 and not pragma:
                continue
            if n == 165:
                if line != FIRST_PARTY_OLD:
                    raise SystemExit("make-root.py: shell.qml 165 is not the line this adapts")
                if "--widgets" not in opts:
                    line = FIRST_PARTY_NEW
            if "--probe" in opts and n in PROBE_AT:
                if line != PROBE_AT[n][0]:
                    raise SystemExit("make-root.py: shell.qml %d is not the line --probe goes above" % n)
                out.append(PROBE_AT[n][1])
            out.append(line)
            if "--hold-sync" in opts and n == SYNC_AT:
                if line != SYNC_OLD:
                    raise SystemExit("make-root.py: shell.qml %d is not syncPluginApis's first line" % n)
                out.append(SYNC_NEW)
    out.append(block)
    out.append(shell[CLOSE - 1])
    return "".join(out)


def widgets_only(plugins_dir):
    """--widgets: rename, under a copy's plugins/, every first-party manifest
    whose kinds are not exactly ["bar-widget"] (plugins/bar's own excepted),
    as the scan finds them (find -mindepth 2 -maxdepth 3, manifest.json or
    *.manifest.json). Returns the ids kept and the ids switched off."""
    kept, off = [], []
    for dirpath, dirnames, filenames in os.walk(plugins_dir):
        depth = os.path.relpath(dirpath, plugins_dir).count(os.sep) + 1
        if dirpath == plugins_dir or depth > 2:
            continue
        for name in sorted(filenames):
            if name != "manifest.json" and not name.endswith(".manifest.json"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            if manifest.get("kinds") == WIDGET_ONLY or (manifest.get("id") == "omarchy.bar"
                                                        and os.path.relpath(path, plugins_dir) == "bar/manifest.json"):
                kept.append(manifest.get("id"))
            else:
                os.rename(path, path + ".rig-off")
                off.append(manifest.get("id"))
    return sorted(kept), sorted(off)


def main(argv):
    if len(argv) < 3 or any(a not in OPTIONS for a in argv[3:]) or len(set(argv[3:])) != len(argv[3:]):
        raise SystemExit("usage: make-root.py OUT RIG_BLOCK [--bar] [--widgets] [--probe] [--hold-sync]")
    out, block_path, opts = argv[1], argv[2], tuple(argv[3:])
    if os.path.exists(out):
        raise SystemExit("make-root.py: %s exists; refusing to reuse it" % out)
    shell = lines_of("shell.qml")
    registry = lines_of("services/PluginRegistry.qml")
    if shell[CLOSE - 1] != "}\n" or len(shell) != CLOSE:
        raise SystemExit("make-root.py: shell.qml does not end at line %d" % CLOSE)
    if not registry[REAPER[0] - 1].startswith("    watcherReaper.command = [\"bash\", \"-c\",") \
            or "\"watcher-reaper\", registry.pluginsDir]" not in registry[REAPER[1] - 1]:
        raise SystemExit("make-root.py: PluginRegistry.qml %d-%d is not the reaper's command" % REAPER)
    with open(block_path, encoding="utf-8") as fh:
        block = fh.read()
    for opt, name in (("--probe", "rigwBeforeApi"), ("--hold-sync", "rigHoldSync")):
        if opt in opts and not re.search(r"\b(function|property bool) %s\b" % name, block):
            raise SystemExit("make-root.py: %s needs a block that defines %s" % (opt, name))
    registry_text = "".join(registry[:REAPER[0] - 1] + [REAPER_NEW] + registry[REAPER[1]:])
    for name, pragma in (("a", True), ("b", False)):
        dest = os.path.join(out, name, "shell")
        shutil.copytree(HOST, dest, symlinks=True)
        with open(os.path.join(dest, "shell.qml"), "w", encoding="utf-8") as fh:
            fh.write(root_text(shell, block, pragma, opts))
        if "--widgets" in opts:
            kept, off = widgets_only(os.path.join(dest, "plugins"))
            with open(os.path.join(out, name, "widgets.json"), "w", encoding="utf-8") as fh:
                json.dump({"kept": kept, "off": off}, fh, indent=1)
        with open(os.path.join(dest, "services", "PluginRegistry.qml"), "w", encoding="utf-8") as fh:
            fh.write(registry_text)
        # The host's defaults, where defaultsFile (shell.qml 134-145) reads
        # them: $OMARCHY_PATH/config/omarchy/shell.json, OMARCHY_PATH being
        # OUT/<root> for the rig.
        os.makedirs(os.path.join(out, name, "config", "omarchy"))
        shutil.copyfile(DEFAULTS, os.path.join(out, name, "config", "omarchy", "shell.json"))
    print(out)


if __name__ == "__main__":
    main(sys.argv)
