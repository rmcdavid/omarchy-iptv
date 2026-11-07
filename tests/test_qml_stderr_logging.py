"""F-HARNESS-101 (2026-11-06): no qml or qmltestrunner this repository
starts may log to the user's journal.

Run without a tty and without QT_FORCE_STDERR_LOGGING=1, Qt's message
handler writes to journald, so an offscreen probe's output -- synthetic so
far, never a credential, but a sink all the same (CLAUDE.md rule 5) --
landed in the owner's user journal, mixed with the shell's own lines the
live checks read: 104 lines from 8 processes on 2026-11-06 (measured by the
host-round map). Every place that starts one sets the variable, and this
holds the repository to it: a file that names a qml runtime binary outside a
comment must also name QT_FORCE_STDERR_LOGGING. A file-level reading, so it
cannot tell two launches in one file apart; the per-launch search, and the
files it cleared, are in the lane write-up.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("OMARCHY_IPTV_DOC_ROOT", os.path.dirname(HERE))
LAUNCH = re.compile(r"/usr/lib/qt6/bin/qml(?:testrunner)?\b|\bqmltestrunner\b|\$\{?QML_BIN\b|\bQML_BIN\s*=|\$QT_BIN/qml(?:testrunner)?\b")
COMMENT = re.compile(r"^\s*(?:#|//)")


def scanned():
    for top in ("scripts", "tests"):
        for dirpath, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = sorted(d for d in dirs if d not in ("__pycache__", "node_modules"))
            for name in sorted(files):
                if name.endswith((".py", ".sh", ".js", ".mjs")):
                    yield os.path.join(dirpath, name)


class QmlStderrLoggingCase(unittest.TestCase):

    def test_every_file_that_starts_qml_forces_stderr_logging(self):
        starters, bad = [], []
        for path in scanned():
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            code = "\n".join(l for l in text.split("\n") if not COMMENT.match(l))
            if not LAUNCH.search(code):
                continue
            rel = os.path.relpath(path, ROOT)
            starters.append(rel)
            if "QT_FORCE_STDERR_LOGGING" not in code:
                bad.append(rel)
        self.assertGreaterEqual(len(starters), 10, "the scan found only %r" % starters)
        self.assertEqual([], bad, "these start qml or qmltestrunner and never set QT_FORCE_STDERR_LOGGING=1, "
                                  "so a run with no tty logs to the user's journal (F-HARNESS-101)")


if __name__ == "__main__":
    unittest.main()
