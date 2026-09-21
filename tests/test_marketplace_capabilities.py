"""Prove scripts/check-marketplace-capabilities.py catches what it claims to.

CLAUDE.md rule 11: a test written after the code and never seen failing is
decoration. The check itself has a real "before" -- f2d1dbf~1, where both
message strings were still present -- and it goes red there and green at
HEAD. These cases cover the decisions that "before" does not reach: the scan
SURFACE (a rule that flagged docs/ prose would be noise, and noise gets
muted), the comment filter, the negation stripping, and the README fences.

CLAUDE.md rule 12: no case here re-implements a pattern. Every one calls the
shipping module, and the surface cases build a real git repository on disk,
because the surface is computed from git ls-files and a fake index would
prove nothing about the real one.

This file lives under tests/, which is an excluded directory for the
marketplace scan, so the literal vectors below are off its surface. That is
deliberate: the vectors have to be spelled exactly as they appeared or they
are not the regression.
"""

import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKER = os.path.join(ROOT, 'scripts', 'check-marketplace-capabilities.py')
PATTERNS_FILE = os.path.join(ROOT, 'scripts', 'marketplace-capability-patterns.json')

# The script has a hyphen in its name, so it cannot be imported by name.
_s = importlib.util.spec_from_file_location('check_marketplace_capabilities', CHECKER)
checker = importlib.util.module_from_spec(_s)
_s.loader.exec_module(checker)


def patterns():
    import json
    with io.open(PATTERNS_FILE, encoding='utf-8') as fh:
        return checker.Patterns(json.load(fh))


# The two strings that were actually reported, verbatim from f2d1dbf~1, and
# the rewordings that shipped in f2d1dbf.
HISTORIC_PACKAGE_LINE = (
    'bad "qmllint not found at $QT_BIN/qmllint (pacman -S qt6-declarative)"'
)
SHIPPED_PACKAGE_LINE = (
    'bad "qmllint not found at $QT_BIN/qmllint '
    '(it ships in the qt6-declarative package)"'
)
HISTORIC_PRIVILEGE_LINE = (
    'note "mpv is an Omarchy dependency and removing it needs sudo, '
    'so the missing-mpv"'
)
SHIPPED_PRIVILEGE_LINE = (
    'note "mpv is an Omarchy dependency and this pass may not remove it, '
    'so the missing-mpv"'
)


class CapabilityPatterns(unittest.TestCase):
    """The patterns, against single commands."""

    def setUp(self):
        self.p = patterns()

    def ids(self, text):
        return sorted(set(i for i, _ in checker.command_hits(self.p, text)))

    def test_the_historic_package_message_trips(self):
        self.assertEqual(['package-manager'], self.ids(HISTORIC_PACKAGE_LINE))

    def test_the_shipped_package_message_is_clean(self):
        self.assertEqual([], self.ids(SHIPPED_PACKAGE_LINE))

    def test_the_historic_privilege_message_trips(self):
        self.assertEqual(['privilege'], self.ids(HISTORIC_PRIVILEGE_LINE))

    def test_the_shipped_privilege_message_is_clean(self):
        self.assertEqual([], self.ids(SHIPPED_PRIVILEGE_LINE))

    def test_an_elevation_verb_anywhere_in_a_string_trips(self):
        self.assertEqual(['privilege'], self.ids('echo "this needs sudo first"'))

    def test_the_other_elevation_verb_trips(self):
        self.assertEqual(['privilege'], self.ids('echo "ask pkexec"'))

    def test_a_negated_elevation_phrase_is_clean(self):
        # Upstream strips the phrases that mean the opposite of what they
        # contain before it looks. If this port dropped that, the 15 "no
        # sudo" lines this project writes on purpose would all be findings.
        self.assertEqual([], self.ids('echo "no sudo is required"'))
        self.assertEqual([], self.ids('echo "this does not use sudo."'))

    def test_a_negated_phrase_does_not_launder_a_second_use(self):
        self.assertEqual(
            ['privilege'],
            self.ids('echo "no sudo is required"; sudo true'))

    def test_a_package_verb_trips(self):
        self.assertEqual(['package-manager'], self.ids('paru -S mpv'))
        self.assertEqual(['package-manager'], self.ids('apt-get install mpv'))
        self.assertEqual(['package-manager'], self.ids('npm install --global qmllint'))

    def test_the_omarchy_package_verb_trips(self):
        # The first alternative in the package-manager list. It survived the
        # first mutation sweep untested, which is the whole reason rule 11
        # asks for the sweep.
        self.assertEqual(['package-manager'], self.ids('omarchy pkg add mpv'))

    def test_a_fetch_of_this_repository_trips_remote_build(self):
        self.assertEqual(
            ['remote-build'],
            self.ids('curl -sSL https://github.com/rmcdavid/omarchy-iptv/'
                     'archive/main.tar.gz'))

    def test_a_fetch_of_somebody_else_does_not(self):
        # Upstream reports remote-build only when every URL in the command is
        # the submission repository itself; anything else is a different rule
        # that this port does not carry. Over-reporting here would be noise.
        self.assertEqual(
            [],
            self.ids('curl -sSL https://github.com/someone/else/archive/main.tar.gz'))

    def test_a_bare_download_with_no_url_does_not_trip(self):
        self.assertEqual([], self.ids('curl -sSL "$url"'))

    def test_a_service_verb_trips(self):
        self.assertEqual(['service-management'], self.ids('systemctl --user status foo'))

    def test_a_policy_path_trips(self):
        self.assertEqual(['sudoers-modification'], self.ids('cp rule /etc/sudoers.d/iptv'))

    def test_an_unpinned_cargo_git_build_trips_twice(self):
        self.assertEqual(
            ['package-manager', 'remote-build'],
            self.ids('cargo install --git https://example.invalid/x thing'))

    def test_an_inline_comment_does_not_hide_a_package_verb(self):
        # Faithful to upstream, and deliberately asymmetric: the trailing
        # comment is stripped only for the elevation rule, so a package verb
        # in a trailing comment IS reported. Do not "fix" this to be
        # consistent -- consistency with the real scanner is what matters.
        self.assertEqual(['package-manager'], self.ids('true   # pacman -S qt6-declarative'))

    def test_an_inline_comment_does_hide_an_elevation_verb(self):
        self.assertEqual([], self.ids('true   # needs sudo'))


class CommandSequence(unittest.TestCase):
    """Which lines are commands at all."""

    def setUp(self):
        self.p = patterns()

    def sequence(self, text, path='scripts/x.sh'):
        return checker.command_sequence(self.p, text, path)

    def test_a_comment_only_line_is_not_a_command(self):
        # scripts/qa-player-scenarios.sh:33 and
        # scripts/qa-sources-scenarios.sh:23 are exactly this shape and must
        # stay silent, or the check is unusable in the files it guards.
        self.assertEqual([], self.sequence('# sudo.\n'))
        self.assertEqual([], self.sequence('# or sudo; every helper invocation\n'))

    def test_a_slash_comment_only_line_is_not_a_command(self):
        self.assertEqual([], self.sequence('// pacman -S qt6-declarative\n', 'Model.js'))

    def test_a_command_after_a_comment_is_still_a_command(self):
        self.assertEqual([(2, 'true')], self.sequence('# sudo\ntrue\n'))

    def test_a_continued_line_reports_its_first_line(self):
        line, text = self.sequence('true \\\n  && echo sudo\n')[0]
        self.assertEqual(1, line)
        self.assertIn('echo sudo', text)

    def test_readme_prose_is_read_as_a_command(self):
        # The root README has no comment filter upstream: every line of it is
        # a command, prose included.
        self.assertEqual(
            [(1, '# Install')],
            self.sequence('# Install\n', 'README.md'))


class ScanSurface(unittest.TestCase):
    """Which files the marketplace reads, built from a real git index."""

    def setUp(self):
        self.p = patterns()
        self.dir = tempfile.mkdtemp(prefix='marketplace-surface-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        subprocess.run(['git', 'init', '-q', self.dir], check=True)

    def write(self, rel, text='true\n', mode=None):
        path = os.path.join(self.dir, rel)
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        if mode is not None:
            os.chmod(path, mode)
        subprocess.run(['git', '-C', self.dir, 'add', rel], check=True)

    def surface(self):
        return sorted(path for _, path in checker.scan_surface(self.dir, self.p))

    def test_documentation_markdown_is_out_of_scope(self):
        self.write('docs/ARCHITECTURE.md', 'Never use sudo.\n')
        self.assertEqual([], self.surface())

    def test_markdown_outside_docs_is_also_out_of_scope(self):
        self.write('CLAUDE.md', 'Never use sudo.\n')
        self.assertEqual([], self.surface())

    def test_the_root_readme_is_in_scope(self):
        self.write('README.md', 'hello\n')
        self.assertEqual(['README.md'], self.surface())

    def test_the_tests_directory_is_out_of_scope(self):
        self.write('tests/test_x.py', 'x = 1\n')
        self.assertEqual([], self.surface())

    def test_a_json_file_under_scripts_is_out_of_scope(self):
        # This is the property that lets the transcribed patterns live in
        # scripts/marketplace-capability-patterns.json without the checker
        # reporting itself as every capability it guards against.
        self.write('scripts/marketplace-capability-patterns.json', '{}\n')
        self.assertEqual([], self.surface())

    def test_an_extensionless_file_under_bin_is_in_scope(self):
        self.write('bin/omarchy-iptv')
        self.assertEqual(['bin/omarchy-iptv'], self.surface())

    def test_an_executable_file_is_in_scope_whatever_its_extension(self):
        self.write('contrib/thing.example', mode=0o755)
        self.assertEqual(['contrib/thing.example'], self.surface())

    def test_a_shell_script_is_in_scope(self):
        self.write('scripts/check.sh')
        self.assertEqual(['scripts/check.sh'], self.surface())


class ScanPath(unittest.TestCase):
    """isSecurityScanPath itself, decided one path at a time.

    scan_surface carries its own copy of the excluded-directory rule, so a
    surface test cannot tell whether this function still has one. The first
    mutation sweep proved that: deleting the rule here changed nothing any
    test could see. Decide it directly instead."""

    def setUp(self):
        self.p = patterns()

    def test_an_excluded_directory_hides_a_scanned_extension(self):
        self.assertFalse(self.p.is_scan_path('tests/test_x.py'))
        self.assertFalse(self.p.is_scan_path('docs/gen.py'))
        self.assertFalse(self.p.is_scan_path('node_modules/pkg/index.js'))
        self.assertFalse(self.p.is_scan_path('a/fixtures/b.sh'))

    def test_a_scanned_extension_elsewhere_qualifies(self):
        self.assertTrue(self.p.is_scan_path('scripts/check.sh'))
        self.assertTrue(self.p.is_scan_path('Guide.qml'))
        self.assertTrue(self.p.is_scan_path('contrib/bindings.lua'))

    def test_an_unscanned_extension_does_not_qualify(self):
        self.assertFalse(self.p.is_scan_path('CHANGELOG.md'))
        self.assertFalse(self.p.is_scan_path('manifest.json'))
        self.assertFalse(self.p.is_scan_path('contrib/omarchy-menu.jsonc'))

    def test_only_bin_and_scripts_qualify_an_extensionless_file(self):
        self.assertTrue(self.p.is_scan_path('bin/omarchy-iptv'))
        self.assertTrue(self.p.is_scan_path('scripts/thing'))
        self.assertFalse(self.p.is_scan_path('contrib/thing'))
        self.assertFalse(self.p.is_scan_path('scripts/thing.jsonc'))

    def test_a_setup_named_file_qualifies_anywhere(self):
        self.assertTrue(self.p.is_scan_path('contrib/installer.txt'))
        self.assertTrue(self.p.is_scan_path('contrib/uninstall.conf'))

    def test_a_binary_asset_never_qualifies(self):
        self.assertFalse(self.p.is_scan_path('preview.png'))
        self.assertFalse(self.p.is_scan_path('scripts/setup-diagram.png'))
        # The only path on which the binary-asset rule actually decides
        # anything: a setup-named image outside bin/ and scripts/, which the
        # setup-name fallback would otherwise pull onto the surface. The
        # first two vectors above are decided before it and left the rule
        # untested.
        self.assertFalse(self.p.is_scan_path('contrib/installer.png'))

    def test_only_the_root_readme_qualifies_as_documentation(self):
        self.assertTrue(self.p.is_scan_path('README.md'))
        self.assertTrue(self.p.is_scan_path('readme'))
        self.assertFalse(self.p.is_scan_path('docs/README.md'))
        self.assertFalse(self.p.is_scan_path('contrib/README.md'))


class ReadmeFences(unittest.TestCase):
    """A shell-tagged fence in the root README is read as a shell file."""

    def setUp(self):
        self.p = patterns()

    def fences(self, text):
        return checker.readme_shell_fences(self.p, text, 'README.md')

    def test_a_fenced_install_command_is_found_at_its_real_line(self):
        text = '# Usage\n\nRun it:\n\n```bash\npacman -S mpv\n```\n'
        offset, body = self.fences(text)[0]
        self.assertIn('pacman -S mpv', body)
        line, command = checker.command_sequence(self.p, body, 'README.md', offset)[0]
        self.assertEqual(6, line)
        self.assertEqual(
            ['package-manager'],
            sorted(set(i for i, _ in checker.command_hits(self.p, command))))

    def test_a_fence_under_a_development_heading_is_exempt(self):
        text = '# Development\n\n```bash\npacman -S mpv\n```\n'
        self.assertEqual([], self.fences(text))

    def test_an_untagged_fence_is_not_a_shell_file(self):
        text = '# Usage\n\n```\npacman -S mpv\n```\n'
        self.assertEqual([], self.fences(text))


class ThisRepository(unittest.TestCase):
    """The shipping tree, end to end."""

    def test_the_repository_is_clean(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = checker.main(['--root', ROOT])
        self.assertEqual(0, code, buf.getvalue())

    def test_the_checker_reads_itself_and_stays_clean(self):
        # The check file must not trip its own patterns. It is a .py under
        # scripts/, so it is on the surface, so this is observed rather than
        # asserted.
        surface = [path for _, path in checker.scan_surface(ROOT, patterns())]
        self.assertIn('scripts/check-marketplace-capabilities.py', surface)

    def test_the_patterns_file_is_off_the_surface(self):
        surface = [path for _, path in checker.scan_surface(ROOT, patterns())]
        self.assertNotIn('scripts/marketplace-capability-patterns.json', surface)

    def test_the_scan_reads_more_than_a_handful_of_files(self):
        # A scan that reads nothing exits 0. Assert it read the tree.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            checker.main(['--root', ROOT])
        count = int(buf.getvalue().split('file(s)')[0].split(':')[-1].strip())
        self.assertGreaterEqual(count, 25)

    def test_the_floor_is_enforced(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = checker.main(['--root', ROOT, '--min-files', '100000'])
        self.assertEqual(1, code)
        self.assertIn('green for the wrong reason', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
