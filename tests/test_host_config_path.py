"""D-SINK-18: the helper and the HOST must name the same settings file.

`config shield` changes the mode of one file, and it has to be the one the
host actually writes. That join is a NAME -- the helper builds a path, the
host builds a path, and nothing compares them -- which is the failure rule 13
describes. The first version of the helper derived it from $XDG_CONFIG_HOME
and said in its docstring that the host honoured that variable. The host does
not: it reads $HOME and appends a literal path. On a machine where
$XDG_CONFIG_HOME pointed elsewhere, the shield would have tightened a file the
host never writes, reported success, and left the credential exposed.

This test makes the join a call on the host's own source, the way
tests/test_host_text_format.py pins the host's renderers. It is skipped where
the host is not installed, so it constrains this machine and never a CI box
that has no Omarchy.
"""
import os
import re
import unittest

from helper_loader import load_helper

helper = load_helper()

HOST_SHELL_QML = "/usr/share/omarchy/shell/shell.qml"


class HostConfigPathTest(unittest.TestCase):
    def _source(self):
        if not os.path.isfile(HOST_SHELL_QML):
            self.skipTest("no Omarchy shell at %s" % HOST_SHELL_QML)
        with open(HOST_SHELL_QML, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def test_the_host_builds_its_config_path_from_home_and_a_literal(self):
        """Anchored on the property, not on a line number, so a moved line
        stays green and a CHANGED one does not."""
        source = self._source()
        match = re.search(
            r"property\s+string\s+userConfigPath:\s*(.+)", source)
        self.assertIsNotNone(match, "userConfigPath is gone from the host shell")
        expr = match.group(1).strip()
        self.assertEqual(expr, 'home + "/.config/omarchy/shell.json"',
                         "the host changed how it names its settings file; "
                         "host_config_path() in bin/omarchy-iptv must follow it")

    def test_the_host_reads_home_rather_than_xdg_config_home(self):
        """The reason the helper may not use $XDG_CONFIG_HOME. If the host ever
        starts honouring it, this goes red and the helper should follow."""
        source = self._source()
        self.assertIsNotNone(
            re.search(r'property\s+string\s+home:\s*Quickshell\.env\("HOME"\)', source),
            "the host no longer takes its home from $HOME")
        self.assertNotIn("XDG_CONFIG_HOME", source,
                         "the host now mentions XDG_CONFIG_HOME; re-read how it "
                         "builds userConfigPath before trusting host_config_path()")

    def test_the_helper_agrees_with_the_host_on_this_machine(self):
        """The two paths, built the two different ways, compared."""
        self._source()
        home = os.environ.get("HOME") or os.path.expanduser("~")
        self.assertEqual(helper.host_config_path(),
                         os.path.join(home, ".config", "omarchy", "shell.json"))

    def test_a_moved_xdg_config_home_does_not_move_the_shielded_file(self):
        """The case that would have shipped: the helper must ignore it."""
        self._source()
        home = os.environ.get("HOME") or os.path.expanduser("~")
        want = os.path.join(home, ".config", "omarchy", "shell.json")
        saved = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = "/tmp/not-where-the-host-writes"
        try:
            self.assertEqual(helper.host_config_path(), want)
        finally:
            if saved is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = saved


if __name__ == "__main__":
    unittest.main()
