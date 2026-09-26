"""Prove scripts/release.py ships exactly what it says and refuses what it must.

CLAUDE.md rule 11: a new check has no "before", so it is proven by mutation.
Rule 12: every case builds a real git repository and runs the real module.

The must-ship set in must_ship() is written out BY HAND, on purpose, rather
than read from release.ALLOWLIST. A test that asserted "the tree equals the
allowlist" would stay green if someone deleted bin/omarchy-iptv from the
allowlist; this one goes red. Verified: drop that entry and
test_the_artifact_holds_exactly_what_the_plugin_needs fails.
"""

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    'release', os.path.join(ROOT, 'scripts', 'release.py'))
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


def must_ship():
    return {
        'manifest.json', 'README.md', 'LICENSE', 'CHANGELOG.md', 'preview.png',
        'BarWidget.qml', 'Guide.qml', 'Service.qml', 'Model.js',
        'bin/omarchy-iptv',
        'contrib/bindings.lua', 'contrib/omarchy-menu.jsonc', 'contrib/windows.lua',
    }


MUST_NOT_SHIP = ('CLAUDE.md', 'docs/PRODUCT.md', 'tests/test_x.py',
                 'scripts/check.sh', '.gitignore')


class ReleaseCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='release-test-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 't@example.invalid')
        self.git('config', 'user.name', 'test')
        # A first main commit with the full tree, standing in for the history
        # before the split; then dev branches from it.
        for path in sorted(must_ship() | set(MUST_NOT_SHIP)):
            self.write(path, 'content of %s\n' % path)
        self.write('manifest.json', '{"version": "0.9.9", "entryPoints": '
                   '{"barWidget": "BarWidget.qml", "overlay": "Guide.qml", '
                   '"service": "Service.qml"}}\n')
        self.write('Service.qml', 'import "Model.js" as Model\n'
                   'x: Qt.resolvedUrl("bin/omarchy-iptv")\n')
        # D-HOST-1: the runtime compares this against manifest.json to notice a
        # hot reload that left an older component mounted, so the check demands
        # it and the double must carry it. A double more forgiving than the
        # real tree is what rule 10 forbids.
        self.write('Model.js', 'var PLUGIN_VERSION = "0.9.9"\n')
        self.write('README.md', 'Copy `contrib/bindings.lua`. See the dev branch: '
                   'https://example.invalid/tree/dev/docs/UX.md\n')
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'before the split')
        self.git('checkout', '-q', '-b', 'dev')

    def git(self, *args):
        return subprocess.run(['git', '-C', self.dir] + list(args), check=True,
                              stdout=subprocess.PIPE).stdout.decode()

    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)

    def commit_all(self, msg='change'):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', msg)

    def build(self):
        return release.build(self.dir, gate_already_green=True, validate=False,
                             tag=True, out=io.StringIO())

    def main_tree(self):
        return set(p for p in self.git('ls-tree', '-r', '--name-only', '-z',
                                       'main').split('\0') if p)

    # -- what ships ------------------------------------------------------

    def test_the_artifact_holds_exactly_what_the_plugin_needs(self):
        self.build()
        self.assertEqual(must_ship(), self.main_tree())

    def test_no_agent_instruction_file_and_no_dev_directory_ships(self):
        self.build()
        tree = self.main_tree()
        for path in MUST_NOT_SHIP:
            self.assertNotIn(path, tree)
        for name in release.AGENT_INSTRUCTION_NAMES:
            self.assertNotIn(name, tree)
        self.assertFalse([p for p in tree if p.split('/')[0] in release.DEV_ONLY_DIRS])

    def test_main_stays_linear_so_installs_can_fast_forward(self):
        old = self.git('rev-parse', 'main').strip()
        new = self.build()
        self.assertEqual(old, self.git('rev-parse', 'main^').strip())
        self.assertEqual(new, self.git('rev-parse', 'main').strip())
        self.assertEqual(new, self.git('rev-parse', 'v0.9.9^{commit}').strip())

    def test_the_artifact_carries_dev_content_not_stale_main_content(self):
        self.write('Model.js', 'new model\nvar PLUGIN_VERSION = "0.9.9"\n')
        self.commit_all()
        self.build()
        blob = self.git('show', 'main:Model.js')
        self.assertEqual('new model\nvar PLUGIN_VERSION = "0.9.9"\n', blob)

    # -- refusals --------------------------------------------------------

    def test_a_dirty_tree_is_refused(self):
        self.write('Model.js', 'uncommitted\nvar PLUGIN_VERSION = "0.9.9"\n')
        with self.assertRaisesRegex(release.ReleaseError, 'dirty'):
            self.build()

    def test_a_release_from_the_wrong_branch_is_refused(self):
        self.git('checkout', '-q', 'main')
        with self.assertRaisesRegex(release.ReleaseError, "cut from 'dev'"):
            self.build()

    def test_a_missing_allowlisted_file_is_refused(self):
        self.git('rm', '-q', 'contrib/windows.lua')
        self.commit_all()
        with self.assertRaisesRegex(release.ReleaseError, 'not tracked'):
            self.build()

    def test_nothing_new_is_refused(self):
        self.build()
        # bump the version so the tag does not collide, change nothing else
        self.write('manifest.json', self.git('show', 'dev:manifest.json')
                   .replace('0.9.9', '1.0.0'))
        # D-HOST-1: a real release bumps BOTH, and the check refuses a tree
        # where they disagree -- otherwise every install shows the restart
        # notice forever. Bumping only the manifest here would be testing a
        # release that could not ship.
        self.write('Model.js', self.git('show', 'dev:Model.js')
                   .replace('0.9.9', '1.0.0'))
        self.commit_all()
        # manifest.json IS on the allowlist, so this is a real change; make
        # the no-change case for real by building twice at the same content
        self.build()
        with self.assertRaisesRegex(release.ReleaseError, 'already exists'):
            self.build()

    def test_an_existing_tag_at_another_commit_is_refused(self):
        self.git('tag', 'v0.9.9', 'main')
        with self.assertRaisesRegex(release.ReleaseError, 'already exists'):
            self.build()

    # -- the allowlist check that runs in the gate ------------------------

    def test_a_clean_tree_passes_check(self):
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_a_runtime_import_outside_the_allowlist_is_a_problem(self):
        self.write('Guide.qml', 'import "Extra.js" as Extra\n')
        self.write('Extra.js', 'x\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("loads 'Extra.js'" in p for p in problems), problems)

    def test_a_readme_that_names_a_dev_file_is_a_problem(self):
        self.write('README.md', 'Start with `docs/PRODUCT.md` and `CLAUDE.md`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('docs/PRODUCT.md' in p for p in problems), problems)
        self.assertTrue(any('CLAUDE.md' in p for p in problems), problems)

    def test_a_readme_url_into_the_dev_branch_is_fine(self):
        self.write('README.md',
                   'https://github.com/x/y/blob/dev/docs/PRODUCT.md\n')
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    # -- D-REL-3: shipped prose may not run the helper bare ---------------

    HELPER_WITH_PARSER = ('sub.add_parser("player")\nsub.add_parser("logos")\n'
                          'sub.add_parser("cache")\n')

    def test_shipped_prose_that_runs_the_helper_bare_is_a_problem(self):
        """PLY-WEAK-05, verified 2026-09-14: the README told the user to run
        `omarchy-iptv player stop`, and omarchy-iptv is on nobody's PATH."""
        self.write('bin/omarchy-iptv', self.HELPER_WITH_PARSER)
        self.write('README.md', 'If one is left behind, run `omarchy-iptv player stop`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("README.md:1 tells the user to run 'omarchy-iptv player'" in p
                            and 'not on PATH' in p for p in problems), problems)

    def test_the_changelog_ships_too_and_is_scanned_too(self):
        """The third instance, 2026-09-25: fixed in the README and written
        again into the CHANGELOG in the same change."""
        self.write('bin/omarchy-iptv', self.HELPER_WITH_PARSER)
        self.write('CHANGELOG.md', '- Run `omarchy-iptv cache logos-clear --key <key>`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('CHANGELOG.md:1' in p and 'D-REL-3' in p for p in problems), problems)

    def test_the_path_form_and_the_names_that_are_not_commands_are_fine(self):
        self.write('bin/omarchy-iptv', self.HELPER_WITH_PARSER)
        self.write('README.md',
                   'Run `python3 ~/.config/omarchy/plugins/x/bin/omarchy-iptv player stop`.\n'
                   'One mpv window, class `omarchy-iptv`, titled with the channel name.\n'
                   "pkill -f -- '^mpv .*--wayland-app-id=omarchy-iptv'\n"
                   'Cached under `~/.cache/omarchy-iptv/sources/<key>/logos/`.\n'
                   "The same helper's `logos` subcommand prints that survey.\n")
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_the_subcommand_list_comes_from_the_helper_not_from_a_copy(self):
        """A helper that declares no parser makes the scan inert rather than
        wrong; one that declares `frobnicate` makes `omarchy-iptv frobnicate`
        a problem without anyone editing the check."""
        self.assertEqual([], release.bare_helper_invocations('run omarchy-iptv player stop', []))
        self.write('bin/omarchy-iptv', 'sub.add_parser("frobnicate")\n')
        self.write('README.md', 'Try `omarchy-iptv frobnicate` and `omarchy-iptv player stop`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("'omarchy-iptv frobnicate'" in p for p in problems), problems)
        self.assertFalse(any("'omarchy-iptv player'" in p for p in problems), problems)

    def test_the_scan_catches_every_line_that_actually_shipped(self):
        """The three real instances, verbatim, against the real helper's
        parser. README bullet 6 at 05a0d3a~1 (2026-09-14, PLY-WEAK-05);
        README line 101 as shipped in v0.7.6 through v0.7.10; and the
        CHANGELOG line written on 2026-09-25 and caught before it shipped."""
        with open(os.path.join(ROOT, 'bin', 'omarchy-iptv'), encoding='utf-8') as fh:
            subs = release.helper_subcommands(fh.read())
        self.assertIn('player', subs)
        self.assertIn('logos', subs)
        shipped = (
            # README.md:164 at 21487f7
            "  longer guaranteed to stop with it; run `omarchy-iptv player stop`, or log",
            # README.md:100 as shipped in v0.7.6
            'can see exactly what enabling them would cost your privacy: `omarchy-iptv logos` reads the cached playlist and prints which hosts it would contact and',
            # CHANGELOG.md, 2026-09-25, before review
            "  `omarchy-iptv cache logos-clear --key <key>`, with `ls ~/.cache/omarchy-iptv/sources/`",
        )
        for line in shipped:
            self.assertEqual(1, len(release.bare_helper_invocations(line, subs)), line)
        # and the wrapped form a per-line scan cannot see
        wrapped = "if one is left behind, run `omarchy-iptv\n  player stop`, or log out."
        self.assertEqual([(1, 'omarchy-iptv player')], release.bare_helper_invocations(wrapped, subs))

    def test_a_blank_line_inside_a_shipped_table_is_a_problem(self):
        """README.md's settings table shipped as three tables: two blank lines
        split fourteen rows into 4 + 4 + 6, and the last ten rendered as
        paragraphs of pipes. Three adversarial prose passes read past it,
        because they were reading the text and this is a defect in the shape."""
        self.write('README.md', 'Settings:\n\n| Key | Type |\n|---|---|\n'
                                '| `a` | string |\n\n| `b` | string |\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('README.md:6 is a blank line INSIDE a table' in p
                            for p in problems), problems)

    def test_a_blank_line_after_a_table_ends_it_and_is_fine(self):
        self.write('README.md', '| Key | Type |\n|---|---|\n| `a` | string |\n\nProse after.\n')
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_a_readme_version_that_disagrees_with_the_manifest_is_a_problem(self):
        """The artifact shipped once saying Status: v0.7.0 beside a 0.7.1 manifest."""
        self.write('README.md', 'Status: v0.9.8. Copy `contrib/bindings.lua`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('Status: v0.9.8 but manifest.json says 0.9.9' in p
                            for p in problems), problems)

    def test_a_readme_version_that_matches_the_manifest_is_fine(self):
        self.write('README.md', 'Status: v0.9.9. Copy `contrib/bindings.lua`.\n')
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_a_shipped_source_that_cites_a_dev_path_is_a_problem(self):
        """D-REL-2: 0.7.1 shipped 70 comments naming CLAUDE.md, docs/, tests/
        or scripts/ -- citations to files that do not exist in an install."""
        self.write('Model.js', '// see docs/UX.md section 3 and CLAUDE.md rule 12\n'
                   'var PLUGIN_VERSION = "0.9.9"\n')
        self.write('bin/omarchy-iptv', '#!/usr/bin/env python3\n# pinned by tests/fixtures/x.json\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("Model.js:1 names 'docs/UX.md'" in p for p in problems), problems)
        self.assertTrue(any("bin/omarchy-iptv:2 names 'tests/fixtures/x.json'" in p for p in problems), problems)

    def test_a_shipped_source_naming_the_rule_and_the_branch_is_fine(self):
        self.write('Model.js', '// engineering rule 12 (dev branch); UX.md section 3 on the dev branch\n'
                   'var PLUGIN_VERSION = "0.9.9"\n')
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_a_manifest_entry_point_outside_the_allowlist_is_a_problem(self):
        self.write('manifest.json', '{"version": "0.9.9", "entryPoints": '
                   '{"overlay": "Other.qml"}}\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('Other.qml' in p for p in problems), problems)


if __name__ == '__main__':
    unittest.main()
