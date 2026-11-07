"""Run the HOST's own JavaScript in Qt's own engine, for the host tripwires.

The notification host's grammar (Markup.js, Security.js, Detect.js,
Delivery.js, Store.js) is `.pragma library` QML JavaScript with `.import`
lines, which node cannot load as written and which a copy in a test would
only mirror (CLAUDE.md rule 12). So a tripwire that pins what the host DOES
loads those files where they are installed, through `qml` offscreen, the
engine the shell itself runs, and reads back one JSON line.

Nothing reaches the desktop or the user's journal: offscreen, a private HOME
and XDG dirs, no DISPLAY or Wayland socket, QT_FORCE_STDERR_LOGGING=1 (without
it a qml run with no tty logs to journald, F-HARNESS-101), a core limit of
zero and a timeout. A probe must never call anything that opens a URL or runs
a command (Security.openExternalUrl, Util.exec*): those are pinned in the
source, never run.
"""
import json
import os
import shutil
import subprocess
import tempfile

QML = os.environ.get("QML_BIN", "/usr/lib/qt6/bin/qml")
MARK = "HOSTV4 "

PROBE = """import QtQuick
%s
QtObject {
  Component.onCompleted: {
    var out = (function () {
%s
    })()
    console.log("%s" + JSON.stringify(out))
    Qt.exit(0)
  }
}
"""


def available():
    return os.path.isfile(QML) and os.access(QML, os.X_OK) and shutil.which("prlimit") is not None


def file_url(path):
    return "file://" + os.path.abspath(path)


def run(imports, body, timeout=60):
    """Evaluate `body` (the inside of a JS function that returns a JSON-able
    value) with `imports` ({alias: absolute path of a .js file}) and return
    what it returned. Raises AssertionError with the run's output on any
    failure, so a probe that cannot load is red, never a skip."""
    work = tempfile.mkdtemp(prefix="omarchy-iptv-hostv4-")
    try:
        home = os.path.join(work, "home")
        os.makedirs(home, mode=0o700)
        lines = []
        for alias, path in sorted(imports.items()):
            if not os.path.isfile(path):
                raise AssertionError("the host file %s is not there" % path)
            lines.append('import "%s" as %s' % (file_url(path), alias))
        probe = os.path.join(work, "probe.qml")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write(PROBE % ("\n".join(lines), body, MARK))
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": home,
               "XDG_CONFIG_HOME": home + "/.config", "XDG_CACHE_HOME": home + "/.cache",
               "XDG_DATA_HOME": home + "/.local/share", "XDG_STATE_HOME": home + "/.local/state",
               "XDG_RUNTIME_DIR": home, "QT_QPA_PLATFORM": "offscreen", "QT_FORCE_STDERR_LOGGING": "1"}
        done = subprocess.run(["prlimit", "--core=0", "--", QML, probe], cwd=work, env=env,
                              capture_output=True, text=True, timeout=timeout)
        text = done.stdout + done.stderr
        found = [l.split(MARK, 1)[1] for l in text.splitlines() if MARK in l]
        if done.returncode != 0 or len(found) != 1:
            raise AssertionError("the host probe did not answer (rc %d):\n%s" % (done.returncode, text[-1500:]))
        return json.loads(found[0])
    finally:
        shutil.rmtree(work, True)
