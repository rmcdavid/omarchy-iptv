"""Three documents state facts about `shell.json`'s mode and the host's
backup copies of it, and one states the Sources form's caps; each join is by
a NAME (a script and a line number, a file name template, a number copied
from the code), which rule 13 says nothing verifies unless something calls
it. This does (D-SINK-37, D-DOC-22, D-DOC-23, D-DOC-24, 2026-10-22):

- the contract's Config line and its `omarchy-refresh-shell` backup
  paragraph, and ARCHITECTURE.md's D-SINK-18 residuals 2 and 4, cite host
  scripts by line; every citation must be one this file knows, and the line
  on this machine must carry the command the sentence attributes to it;
- the README and the contract name the two backup files; the names are
  derived here from the scripts' own templates, not copied;
- UX-SOURCES 2.3's caps are read from `model/sources.mjs`.

OMARCHY_BIN_DIR and OMARCHY_SHELL_DIR point the host half at a copy, which is
how it was proven red (one command changed on a copy of
omarchy-reinstall-configs); OMARCHY_IPTV_DOC_ROOT points the document half at
another tree, which is how the three document pins were proven red against
fe40b2c, the tree before the sentences were written. A red after an Omarchy
update is a re-measurement request (the citations are this machine's,
omarchy 4.0.4-1), not a plugin defect.
"""
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("OMARCHY_IPTV_DOC_ROOT", os.path.dirname(HERE))
HOST_BIN = os.environ.get("OMARCHY_BIN_DIR", "/usr/share/omarchy/bin")
HOST_SHELL = os.environ.get("OMARCHY_SHELL_DIR", "/usr/share/omarchy/shell")

# (script, line) -> the command the documents attribute to that line. A
# citation the documents make that is not here fails as unknown, so a new
# line number in a sentence needs a pin beside it.
EXPECT = {
    ("omarchy-refresh-config", 22): r'backup_config_file="\$user_config_file\.bak\.\$\(date \+%s\)"',
    ("omarchy-refresh-config", 32): r'cp -f "\$user_config_file" "\$backup_config_file"',
    ("omarchy-refresh-config", 33): r'cp -f "\$default_config_file" "\$user_config_file"',
    ("omarchy-refresh-config", 36): r'rm "\$backup_config_file"',
    ("omarchy-refresh-config", 42): r'cp -f "\$default_config_file" "\$user_config_file"',
    ("omarchy-reinstall-configs", 19): r"^cp -af /etc/skel/\. ~/$",
    ("omarchy-upgrade-to-quattro", 390): r"backup_suffix=\$\(date \+%Y%m%d%H%M%S\)",
    ("omarchy-upgrade-to-quattro", 1654): r'cp -af "\$file" "\$file\.omarchy-upgrade-to-quattro\.\$BACKUP_SUFFIX\.bak"',
    ("omarchy-upgrade-to-quattro", 1727): r'cmp -s "\$source" "\$target"',
    ("omarchy-upgrade-to-quattro", 1730): r'backup_config_file "\$target"',
    ("omarchy-upgrade-to-quattro", 1731): r'rm -f "\$target"',
    ("omarchy-upgrade-to-quattro", 1735): r'cp -P "\$source" "\$target"',
    ("omarchy-upgrade-to-quattro", 1750): r'cp -P "\$source_path" "\$target_path"',
    ("omarchy-upgrade-to-quattro", 2373): r"run_as_user_omarchy omarchy-bar defaults",
    ("omarchy-shell-config", 57): r"_SHELL_CONFIG_TMP=\$\(mktemp\)",
    ("omarchy-shell-config", 58): r"jq .* >\"\$_SHELL_CONFIG_TMP\"",
    ("omarchy-shell-config", 59): r'mv "\$_SHELL_CONFIG_TMP" "\$CONFIG_FILE"',
    ("omarchy-bar", 152): r"^\s*commit ",
    ("omarchy-bar", 154): r"^\s*commit ",
    ("omarchy-bar", 176): r"^\s*commit ",
    ("omarchy-bar", 203): r"^\s*commit ",
    ("omarchy-bar", 213): r"^\s*commit ",
    ("omarchy-bar", 216): r"^\s*commit ",
    ("omarchy-bar", 361): r"omarchy-shell shell setBarWidget",
    ("omarchy-refresh-shell", 9): r"^omarchy-bar defaults$",
    ("omarchy-plugin-enable", 85): r"omarchy-shell shell enablePlugin",
    ("shell.qml", 136): r"path: shell\.userConfigPath",
    ("shell.qml", 137): r"watchChanges: true",
    ("shell.qml", 138): r"atomicWrites: true",
}

# Citations the Config line must make, whatever else it says: the four
# paths that leave a 0644 file, the CLI writer, and the FileView route.
REQUIRED_CONFIG_CITATIONS = {
    ("omarchy-refresh-config", 42),
    ("omarchy-reinstall-configs", 19),
    ("omarchy-upgrade-to-quattro", 1735),
    ("omarchy-shell-config", 57),
    ("omarchy-shell-config", 59),
    ("omarchy-bar", 361),
    ("shell.qml", 138),
}
REQUIRED_BACKUP_CITATIONS = {
    ("omarchy-refresh-config", 32),
    ("omarchy-upgrade-to-quattro", 1654),
}

SCRIPTS = sorted(set(name for name, _ in EXPECT))
CITATION_RE = re.compile(r"`(" + "|".join(re.escape(s) for s in SCRIPTS) + r"):(\d[\d,\s-]*)`")


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def doc(rel):
    return read(os.path.join(ROOT, rel))


def host_lines(script):
    base = HOST_SHELL if script.endswith(".qml") else HOST_BIN
    return read(os.path.join(base, script)).split("\n")


def citations(text):
    """Every (script, line) a passage cites as `script:N`, `script:N,M` or
    `script:N-M` (a range cites each line in it)."""
    found = set()
    for m in CITATION_RE.finditer(text):
        script = m.group(1)
        for part in m.group(2).split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                lo, hi = part.split("-", 1)
                for n in range(int(lo), int(hi) + 1):
                    found.add((script, n))
            else:
                found.add((script, int(part)))
    return found


def passage(text, start, end, what):
    i = text.find(start)
    if i == -1:
        raise AssertionError("%s: cannot find %r" % (what, start))
    j = text.find(end, i + len(start))
    if j == -1:
        raise AssertionError("%s: cannot find %r after %r" % (what, end, start))
    return text[i:j]


class HostCitationCase(unittest.TestCase):
    """The script lines the documents cite carry the commands they say."""

    def setUp(self):
        if not os.path.isfile(os.path.join(HOST_BIN, "omarchy-refresh-config")):
            self.skipTest("no Omarchy under %s; the host half cannot be checked here" % HOST_BIN)

    def check_passage(self, text, required, what):
        cited = citations(text)
        unknown = sorted(c for c in cited if c not in EXPECT)
        self.assertEqual([], unknown, "%s cites lines this test has no pin for: %r" % (what, unknown))
        missing = sorted(required - cited)
        self.assertEqual([], missing, "%s no longer cites %r" % (what, missing))
        wrong = []
        for script, n in sorted(cited):
            lines = host_lines(script)
            line = lines[n - 1] if n - 1 < len(lines) else ""
            if re.search(EXPECT[(script, n)], line) is None:
                wrong.append("%s:%d is %r, expected /%s/" % (script, n, line.strip(), EXPECT[(script, n)]))
        self.assertEqual([], wrong, "\n".join([
            "",
            "A host line %s cites no longer carries the command the sentence" % what,
            "attributes to it. Re-measure before moving the citation:",
        ] + ["  " + w for w in wrong]))

    def test_contract_config_line_cites_the_scripts_at_the_commands_they_carry(self):
        text = passage(doc("docs/OMARCHY-PLUGIN-CONTRACT.md"),
                       "- Config: `~/.config/omarchy/shell.json`", "\n- Menu extension:",
                       "the contract's Config line")
        self.assertIsNone(re.search(r"shell\.json` \(mode 0\d{3}\)", text),
                          "the contract states the mode as a host constant again (D-DOC-22)")
        self.check_passage(text, REQUIRED_CONFIG_CITATIONS, "the contract's Config line")

    def test_contract_backup_paragraph_cites_the_two_copy_lines(self):
        text = passage(doc("docs/OMARCHY-PLUGIN-CONTRACT.md"),
                       "**It also leaves a copy of the old file beside the new one",
                       "\n\nThe neighbouring commands, by their own summary lines:",
                       "the contract's backup paragraph")
        self.check_passage(text, REQUIRED_BACKUP_CITATIONS, "the contract's backup paragraph")

    def test_architecture_residuals_cite_the_scripts_at_the_commands_they_carry(self):
        text = passage(doc("docs/ARCHITECTURE.md"),
                       "2. *Loosened after a write.*", "**The siblings, asked before closing (engineering rule 15).** What else does",
                       "ARCHITECTURE.md D-SINK-18 residuals 2-4")
        self.check_passage(text, REQUIRED_BACKUP_CITATIONS | {("omarchy-reinstall-configs", 19), ("omarchy-shell-config", 57)},
                           "ARCHITECTURE.md D-SINK-18 residuals 2-4")


class BackupNameCase(unittest.TestCase):
    """The backup file names the README and the contract give are the
    scripts' own templates with a placeholder where the script puts a
    timestamp."""

    def setUp(self):
        if not os.path.isfile(os.path.join(HOST_BIN, "omarchy-refresh-config")):
            self.skipTest("no Omarchy under %s; the host half cannot be checked here" % HOST_BIN)

    def templates(self):
        refresh = read(os.path.join(HOST_BIN, "omarchy-refresh-config"))
        m = re.search(r'backup_config_file="\$user_config_file(\.[\w.]*?)\$\(date \+%s\)"', refresh)
        self.assertIsNotNone(m, "omarchy-refresh-config no longer builds its backup name as the test reads it")
        refresh_re = r"shell\.json" + re.escape(m.group(1)) + r"<\w+>"
        quattro = read(os.path.join(HOST_BIN, "omarchy-upgrade-to-quattro"))
        m = re.search(r'cp -af "\$file" "\$file(\.[\w.-]*?)\$BACKUP_SUFFIX(\.\w+)"', quattro)
        self.assertIsNotNone(m, "omarchy-upgrade-to-quattro no longer builds its backup name as the test reads it")
        quattro_re = r"shell\.json" + re.escape(m.group(1)) + r"<\w+>" + re.escape(m.group(2))
        return refresh_re, quattro_re

    def assert_names(self, text, what):
        refresh_re, quattro_re = self.templates()
        self.assertIsNotNone(re.search(refresh_re, text), "%s does not name the omarchy-refresh-config backup /%s/" % (what, refresh_re))
        self.assertIsNotNone(re.search(quattro_re, text), "%s does not name the upgrade backup /%s/" % (what, quattro_re))

    def test_readme_settings_names_both_backups_beside_the_count_of_files(self):
        text = passage(doc("README.md"), "## Settings", "\n## ", "README Settings")
        self.assertIn("counted: **two files", text)
        self.assert_names(text, "README Settings")
        self.assertIn("ls -l ~/.config/omarchy/shell.json*", text)

    def test_readme_troubleshooting_names_both_backups_with_the_chmod(self):
        text = passage(doc("README.md"), "## Troubleshooting", "\n## ", "README Troubleshooting")
        self.assert_names(text, "README Troubleshooting")
        self.assertIn("chmod 600 ~/.config/omarchy/shell.json.bak.*", text)

    def test_contract_names_both_backups(self):
        text = passage(doc("docs/OMARCHY-PLUGIN-CONTRACT.md"),
                       "## `omarchy-refresh-shell` RESETS the user's config", "\n## ", "the contract's refresh-shell section")
        self.assert_names(text, "the contract's refresh-shell section")


class FormCapCase(unittest.TestCase):
    """UX-SOURCES 2.3's caps are the model's numbers."""

    def model_caps(self):
        src = doc("model/sources.mjs")
        caps = {}
        for name in ("MAX_SOURCE_URL", "MAX_LABEL", "MAX_XTREAM_SERVER", "MAX_XTREAM_FIELD"):
            m = re.search(r"^var %s = (\d+)$" % name, src, re.M)
            self.assertIsNotNone(m, "model/sources.mjs no longer declares %s as a bare number" % name)
            caps[name] = int(m.group(1))
        return caps

    def test_ux_sources_2_3_caps_are_the_models(self):
        caps = self.model_caps()
        text = passage(doc("docs/UX-SOURCES.md"), "### 2.3 Text fields", "\n### 2.4", "UX-SOURCES 2.3")
        m = re.search(r"Cap at the field's limit \(`LIMITS\.url` ([\d,]+),\s*`LIMITS\.label` ([\d,]+), `LIMITS\.server` ([\d,]+), `LIMITS\.user` / `LIMITS\.pass`\s*([\d,]+)", text)
        self.assertIsNotNone(m, "UX-SOURCES 2.3 no longer states the caps in the sentence this test reads")
        stated = [int(g.replace(",", "")) for g in m.groups()]
        self.assertEqual([caps["MAX_SOURCE_URL"], caps["MAX_LABEL"], caps["MAX_XTREAM_SERVER"], caps["MAX_XTREAM_FIELD"]], stated,
                         "UX-SOURCES 2.3 states caps the model does not have (url, label, server, user/pass)")


if __name__ == "__main__":
    unittest.main()
