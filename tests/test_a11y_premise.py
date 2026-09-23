"""D-A11Y-1's deferral has an expiry date, and this is it.

Ruling AX2 refused masking the accessible Value of the Sources form fields
because live risk is zero while no Quickshell window publishes an
accessibility tree at all (D-GS-3, quickshell#1144). That reasoning is sound
and it is CONDITIONAL. If an update makes a PanelWindow publish, a revealed
playlist or EPG URL -- and the Xtream server and username, which are not
maskable at all -- publish their credentials to every listener on the session
bus, and the refusal silently stops being safe.

The premise was a comment in three files and an assertion in none: two things
joined by a name, with nothing verifying the join (CLAUDE.md rule 13).

This does not detect the upstream fix. It detects that the MEASUREMENT HAS
EXPIRED, which is cheap and honest. A version change is exactly the moment the
recorded evidence stops describing this machine.
"""
import io
import json
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 'a11y-premise.json')


def installed(pkg):
    """The pacman version of `pkg`, or None when it cannot be determined.

    None means "do not know", never "unchanged": a machine without pacman, or
    without the package, is not evidence that the premise still holds, so the
    test skips rather than passing. A guard that passes when it learned nothing
    is the kind this whole file exists to replace.
    """
    try:
        out = subprocess.run(['pacman', '-Q', pkg], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    parts = out.stdout.decode('utf-8', 'replace').split()
    return parts[1] if len(parts) > 1 else None


class A11yPremiseCase(unittest.TestCase):

    def setUp(self):
        with io.open(FIXTURE, encoding='utf-8') as fh:
            self.fixture = json.load(fh)

    def test_the_fixture_says_what_becomes_live_and_what_to_do(self):
        # The fixture is the thing a person reads when this goes red at some
        # unknown future date, so it has to carry the whole instruction. An
        # expiry guard whose message is "versions differ" teaches nothing.
        for key in ('premise', 'upstream', 'whyItMatters', 'onRed', 'platform'):
            self.assertIn(key, self.fixture)
            self.assertTrue(str(self.fixture[key]).strip(), key)
        self.assertIn('D-A11Y-1', self.fixture['whyItMatters'])
        self.assertIn('a11y-probe.sh', self.fixture['onRed'])

    def test_the_platform_the_premise_was_measured_on_is_still_the_one_here(self):
        stale = []
        checked = 0
        for pkg, recorded in sorted(self.fixture['platform'].items()):
            have = installed(pkg)
            if have is None:
                continue
            checked += 1
            if have != recorded:
                stale.append('%s: measured on %s, installed %s' % (pkg, recorded, have))
        if checked == 0:
            self.skipTest('no package versions readable here; the premise cannot be checked')
        self.assertEqual([], stale, '\n'.join([
            '',
            'The accessibility premise D-A11Y-1 is deferred against was measured on a',
            'platform this machine no longer has:',
        ] + ['  ' + s for s in stale] + [
            '',
            self.fixture['premise'],
            '',
            self.fixture['onRed'],
            '',
            'Do not simply update the versions in tests/fixtures/a11y-premise.json.',
            'Re-measure first: if a PanelWindow now publishes a tree, D-A11Y-1 is LIVE',
            'and the Sources field values carry provider credentials onto the session bus.',
        ]))


if __name__ == '__main__':
    unittest.main()
