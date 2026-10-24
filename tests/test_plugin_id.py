"""The plugin id is ONE string, declared in manifest.json, and every literal
copy of it is a join by name that nothing used to check (F-HARNESS-4,
CLAUDE.md rule 13).

The host resolves the plugin by `manifest.json`'s `id`: the IpcHandler
target, the bar entry, `omarchy-shell shell toggle <id>`, the install
directory. Service.qml and Guide.qml read the id from the manifest and fall
back to a literal; BarWidget.qml's `moduleName` IS a literal, with no
manifest behind it at all; the dev harness registers the literal in
shell.qml and names it in run.sh (where only the manifest half was checked,
by `plugin_target`); the node service harness, the live-QA script, two
scenarios' seeded host configs, two python fixtures and the two
accessibility host stand-ins carry it too. A rename that reaches the
manifest and misses one of these shows up as `qs ipc` finding no target, a
bar widget the host cannot place, or a fixture that stops matching -- never
as anything naming the cause.

Each site below is found by the SHAPE of its line and asserted to carry the
manifest's id, naming the file on failure; the number of matches per site is
asserted too, so a line that moves or disappears is red rather than vacuous
(rule 14). Seen red on a9d20f9 with BarWidget.qml's `moduleName` changed in
a scratch copy (the shipped join nothing checked) and with run.sh's seeded
config id changed.

Not listed, and why: tests/Model.test.js, scripts/dev-harness/key-scenario.sh
(line 921) and scripts/qa-lib-test.sh (line 303) hand the literal to a model
function as BOTH sides of a comparison, so they are fixtures of the
function and not joins to the manifest; tests/test_shipped_copy.py feeds
the literal to a README parser as sample text; comments and the README are
prose.
"""

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (file, pattern with ONE capture group for the id, expected match count)
SITES = [
    ('Service.qml',
     r'readonly property string pluginId: manifest && manifest\.id \? String\(manifest\.id\) : "([^"]+)"', 1),
    ('Guide.qml',
     r'readonly property string pluginId: manifest && manifest\.id \? String\(manifest\.id\) : "([^"]+)"', 1),
    ('BarWidget.qml', r'^\s*moduleName: "([^"]+)"', 1),
    ('scripts/dev-harness/shell.qml', r'readonly property string pluginId: "([^"]+)"', 1),
    ('scripts/dev-harness/run.sh', r'^PLUGIN_TARGET="([^"]+)"', 1),
    # The seeded scratch host config (seed_scratch_config) and the
    # config-mode scenario's own seed: the bar entry the service looks up
    # by id.
    ('scripts/dev-harness/run.sh', r'"right":\[\{"id":"([^"]+)"\}\]', 1),
    ('scripts/dev-harness/config-mode-scenario.sh', r'"right":\[\{"id":"([^"]+)"\}\]', 1),
    ('scripts/dev-harness/sources-scenario.sh', r'updateEntryInline ([a-z0-9.]+) keys:', 1),
    ('scripts/qa-live.sh', r'^ID="([^"]+)"', 1),
    ('tests/service-harness.js', r'^const PID = "([^"]+)"', 1),
    ('tests/test_harness_home.py', r'SEED_BODY = \'.*"id":"([^"]+)"', 1),
    ('tests/test_config_shield.py', r'"center":\[\{"id":"([^"]+)"', 2),
    ('tests/a11y/host_src.qml', r'item\.manifest = \{ id: "([^"]+)" \}', 1),
    ('tests/a11y/host_guide.qml', r'item\.manifest = \{ id: "([^"]+)" \}', 1),
    # What the user binds: the host resolves `omarchy-shell shell toggle <id>`
    # and `omarchy-shell <id> <verb>` by the manifest id. Every occurrence.
    ('contrib/bindings.lua', r'omarchy-shell (?:shell toggle )?([a-z0-9]+\.[a-z0-9.]+)', 8),
    ('contrib/omarchy-menu.jsonc', r'omarchy-shell shell toggle ([a-z0-9]+\.[a-z0-9.]+)', 1),
    # The install directory is named after the id, and release.py's check
    # matches the README's helper instruction against this form.
    ('scripts/release.py', r"HELPER_PATH_FORM = \('python3 ~/\.config/omarchy/plugins/([^/]+)/'", 1),
]


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


class PluginIdJoin(unittest.TestCase):
    def setUp(self):
        self.id = json.loads(read('manifest.json'))['id']

    def test_the_manifest_id_is_a_reverse_dns_name(self):
        self.assertRegex(self.id, r'^[a-z0-9]+(\.[a-z0-9-]+)+$')

    def test_every_literal_site_carries_the_manifest_id(self):
        for rel, pattern, count in SITES:
            with self.subTest(file=rel):
                found = re.findall(pattern, read(rel), re.M)
                self.assertEqual(len(found), count,
                                 '%s: expected %d site(s) of the plugin id by shape, found %d' % (rel, count, len(found)))
                for value in found:
                    self.assertEqual(value, self.id,
                                     '%s names the plugin id as %r, manifest.json says %r' % (rel, value, self.id))

    def test_no_other_reverse_dns_literal_hides_in_a_checked_file(self):
        """A rename that lands a NEW id beside an old one in a checked file
        is caught by the shape, not only by the sites listed."""
        for rel in sorted({s[0] for s in SITES}):
            with self.subTest(file=rel):
                for m in re.finditer(r'io\.github\.[a-z0-9-]+\.[a-z0-9-]+', read(rel)):
                    self.assertEqual(m.group(0), self.id, '%s carries %r beside %r' % (rel, m.group(0), self.id))


if __name__ == '__main__':
    unittest.main()
