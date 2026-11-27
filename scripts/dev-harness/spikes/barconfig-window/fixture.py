#!/usr/bin/env python3
"""scripts/dev-harness/spikes/barconfig-window/fixture.py -- one start's
decoy HOME: the host's shell.json and the plugin's state.json.

  fixture.py HOME PLAYLIST FIXTURE PATH

FIXTURE (the bar entry and the state; the playlist is PLAYLIST, a local
three-channel file named by its absolute path, so nothing is fetched):
  F  the measurement: an entry carrying playlistUrl and maxRecents 25, and a
     state.json holding 15 recents and NO migration marker (`entryMigrated`,
     Model.entryMigratedOf) and no sources, as an install from before the
     marker holds it (0.13.x named the active source by the entry's URL,
     D-SINK-19 round 11): so the first reconcile over the state migrates,
     Model.reconcileAction answering "adopt" over the entry's URL or
     "migrate" over an entry read as empty, and Model.adoptActiveSource
     setting the marker either way.
  M  control: F with the marker present (`entryMigrated: true`), so the
     entry's playlistUrl is a retired input whatever the window does, and
     only the recents can move.
  N  control: F with maxRecents absent from the entry, so 10, the default,
     is the entry's own value and a trim to 10 is right.
PATH (where the entry is, for the path run.sh drives):
  cold, toggle, install   the entry in the layout's right section
  enableh                 no entry anywhere: the plugin disabled the host's
                          way (setPluginEnabled false splices the entry out,
                          PluginRegistry.qml 588), so the host's enable
                          inserts `{id}` alone and the settings are gone
  enablel                 the entry in the layout AND the id in
                          `disabledPlugins` (PluginRegistry.qml 160, 166-169,
                          a hand-edited shell.json: the host writes that list
                          only for first-party plugins and clones), so the
                          enable keeps the entry and its settings
Writes HOME/.config/omarchy/shell.json and HOME/.local/state/omarchy-iptv/
state.json (folders 0700, files 0600), and prints the state's text's
sha256. Python 3 standard library only.
"""
import hashlib
import json
import os
import sys

PLUGIN_ID = "io.github.rmcdavid.iptv"
FIXTURES = ("F", "M", "N")
PATHS = ("cold", "toggle", "install", "enableh", "enablel")
RECENTS = 15


def write_private(path, text):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def shell_config(playlist, fixture, path):
    entry = {"id": PLUGIN_ID, "playlistUrl": playlist, "refreshMinutes": 120}
    if fixture != "N":
        entry["maxRecents"] = 25
    right = [] if path == "enableh" else [entry]
    config = {"version": 1,
              "bar": {"layout": {"left": [], "centerBegin": [], "center": [], "centerEnd": [], "right": right}},
              "plugins": []}
    if path == "enablel":
        config["disabledPlugins"] = [PLUGIN_ID]
    return config


def state(fixture):
    recents = [{"id": "r%02d" % n, "name": "Recent %d" % n, "at": 1764000000 - 60 * n} for n in range(1, RECENTS + 1)]
    st = {"version": 2, "cacheLayout": 2, "favorites": [], "recents": recents, "lastPlayed": recents[0],
          "session": None, "sources": [], "savedSearches": [], "hiddenGroups": []}
    if fixture == "M":
        st["entryMigrated"] = True
    return st


def main(argv):
    if len(argv) != 5 or argv[3] not in FIXTURES or argv[4] not in PATHS:
        raise SystemExit("usage: fixture.py HOME PLAYLIST {F,M,N} {%s}" % ",".join(PATHS))
    home, playlist, fixture, path = argv[1:]
    if not os.path.isabs(playlist):
        raise SystemExit("fixture.py: PLAYLIST must be an absolute path")
    write_private(os.path.join(home, ".config", "omarchy", "shell.json"),
                  json.dumps(shell_config(playlist, fixture, path), indent=2) + "\n")
    text = json.dumps(state(fixture), indent=2) + "\n"
    write_private(os.path.join(home, ".local", "state", "omarchy-iptv", "state.json"), text)
    print(hashlib.sha256(text.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    main(sys.argv)
