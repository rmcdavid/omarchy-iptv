"""D-A11Y-1's deferral has an expiry date, and this is it.

Ruling AX2 refused masking the accessible Value of the Sources form fields
because live risk is zero while no Quickshell window publishes an
accessibility tree at all (D-GS-3, quickshell#1144). That reasoning is sound
and it is CONDITIONAL. As of 2026-09-25 the cause is confirmed fixed upstream
at quickshell-mirror/quickshell@916a0dd and is NOT in any release, so the
premise still holds -- but its expiry is now a known commit rather than an
unknown date (investigation section 10).

If an update makes a PanelWindow publish, a revealed playlist or EPG URL -- and
the Xtream server and username, which are not maskable at all -- publish their
credentials to every listener on the session bus, and the refusal silently stops
being safe.

The premise was a comment in three files and an assertion in none: two things
joined by a name, with nothing verifying the join (CLAUDE.md rule 13).

This does not detect the upstream fix. It detects that the MEASUREMENT HAS
EXPIRED, which is cheap and honest. A version change is exactly the moment the
recorded evidence stops describing this machine.

THE EXCEPTION (2026-10-31). The tripwire fired on that day's system update, as
designed, and the installed Quickshell carries 916a0dd, so D-A11Y-1 is treated
as LIVE. The product owner decided that it stays open and is fixed separately,
and that meanwhile a NARROW, DATED exception lets unrelated work land on dev
while NOTHING ships. The exception is data in the fixture (`exception`), and
this file honours it only:

  * on exactly the platform it names, every package read and equal -- an
    unreadable package is not a match, and a newer one is a new platform the
    recorded evidence does not describe;
  * while the board row it is tied to, D-A11Y-1, reads open -- the day the row
    reads fixed, the exception has ended and is red until it is removed and
    the premise re-measured per `onRed`;
  * when it is whole: every field present, nothing this file does not read,
    the product owner's, dated no later than today, and naming the 916a0dd
    check and the probe run as its evidence.

Honoured, the platform test SKIPS with the reason rather than passing. A pass
would count "the premise holds" on a machine where it does not, which is the
one claim this file exists to stop anyone making; a skip is counted in the
gate's summary line and carries its reason under -v. scripts/release.py build
refuses to cut while the exception is present, so the skip cannot ship.
"""
import datetime
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'tests', 'fixtures', 'a11y-premise.json')
BOARD = os.path.join(ROOT, 'docs', 'STATUS.md')

# The board is read by the staleness checker's own parse, called rather than
# copied (CLAUDE.md rule 12): the state of a row is its last cell after the one
# trailing empty, and a second parser here could disagree with it in silence.
# Loading a module from a path can leave scripts/__pycache__ behind, which is
# ignored, but the test that owns that checker turns writing off too.
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location(
    'check_board_staleness_premise',
    os.path.join(ROOT, 'scripts', 'check-board-staleness.py'))
board = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(board)

# The one row an exception may be tied to: the deferral this premise guards.
# Tying it to any other open row would let it outlive the fix it waits for.
PREMISE_ROW = 'D-A11Y-1'
AUTHORITY = 'the product owner'
EXCEPTION_FIELDS = ('authorisedBy', 'date', 'boardRow', 'platform', 'evidence', 'why')
# Each piece of evidence must name what onRed told the reader to check.
EVIDENCE_FIELDS = (('upstreamFix', '916a0dd'), ('probe', 'a11y-probe.sh'))
ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
# A row is open when its state cell LEADS with the word, emphasis allowed --
# "**open, half shipped.**", "open, upstream", "**reopened**". The board's
# convention puts the state word first, and every closing state leads with
# another word ("fixed on dev", "verified fixed", "withdrawn"), so a row that
# says "fixed" anywhere first is not open, whatever follows.
# The word ends at anything but a letter or digit, not at \b: an underscore
# is a word character, so \b would not end `_open_`.
OPEN_STATE = re.compile(r'^[*_`\s]*(?:re)?open(?:ed)?(?![A-Za-z0-9])', re.I)


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


def read_board():
    with io.open(BOARD, encoding='utf-8') as fh:
        return fh.read()


def row_state(board_text, ident):
    """(open?, state cell) for `ident`'s row; (False, None) when it has none."""
    state = board.board_states(board_text).get(ident)
    if state is None:
        return False, None
    return bool(OPEN_STATE.match(state)), state


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def exception_problems(fixture, board_text, today):
    """Why the fixture's exception may not be honoured; [] when it may.

    No exception at all is [] too: the premise is then judged exactly as it
    was before the exception existed. Judged wherever the file runs, before
    any version is read, so a machine without pacman still goes red on an
    exception that has ended or was never whole.
    """
    if 'exception' not in fixture:
        return []
    exc = fixture['exception']
    if not isinstance(exc, dict):
        return ['`exception` is a %s, not an object' % type(exc).__name__]
    problems = []
    for key in EXCEPTION_FIELDS:
        if key not in exc:
            problems.append('`exception` has no `%s`' % key)
    for key in sorted(set(exc) - set(EXCEPTION_FIELDS)):
        problems.append('`exception` carries `%s`, which this test does not read; '
                        'a reader would take it for a condition, and nothing '
                        'checks it' % key)

    if 'authorisedBy' in exc and exc['authorisedBy'] != AUTHORITY:
        problems.append('`exception.authorisedBy` is %r; only %s may let work '
                        'land past a live credential sink'
                        % (exc['authorisedBy'], AUTHORITY))

    if 'date' in exc:
        when = exc['date']
        day = None
        if isinstance(when, str) and ISO_DATE.match(when):
            try:
                day = datetime.date(*(int(p) for p in when.split('-')))
            except ValueError:
                day = None
        if day is None:
            problems.append('`exception.date` is %r, not a YYYY-MM-DD date' % (when,))
        elif day > today:
            problems.append('`exception.date` %s is after today, %s; an '
                            'authorisation is dated the day it was given'
                            % (when, today.isoformat()))

    if 'boardRow' in exc:
        row = exc['boardRow']
        if row != PREMISE_ROW:
            problems.append('`exception.boardRow` is %r; the exception can be tied '
                            'only to %s, the row this premise defers'
                            % (row, PREMISE_ROW))
        else:
            is_open, state = row_state(board_text, row)
            if state is None:
                problems.append('docs/STATUS.md has no %s row, so nothing shows '
                                'the exception still stands' % row)
            elif not is_open:
                problems.append(
                    '%s no longer reads open on the board (its state reads %r), so '
                    'the exception has ended: remove `exception` from '
                    'tests/fixtures/a11y-premise.json and re-measure the premise '
                    'per onRed' % (row, state[:60]))

    if 'platform' in exc:
        plat = exc['platform']
        if not isinstance(plat, dict):
            problems.append('`exception.platform` is a %s, not an object'
                            % type(plat).__name__)
        else:
            want = sorted(fixture['platform'])
            if sorted(plat) != want:
                problems.append('`exception.platform` names %s; it must name exactly '
                                'the packages `platform` does, %s, so that no package '
                                'drops out of the comparison' % (sorted(plat), want))
            empty = [k for k in sorted(plat) if not _text(plat[k])]
            if empty:
                problems.append('`exception.platform` has no version for %s'
                                % ', '.join(empty))
            if plat == fixture['platform']:
                problems.append('`exception.platform` is the platform the premise was '
                                'measured on, so it excuses nothing; if `platform` was '
                                'moved to this machine, onRed says re-measure first')

    if 'evidence' in exc:
        ev = exc['evidence']
        if not isinstance(ev, dict):
            problems.append('`exception.evidence` is a %s, not an object'
                            % type(ev).__name__)
        else:
            for key, must in EVIDENCE_FIELDS:
                if not _text(ev.get(key)):
                    problems.append('`exception.evidence` has no `%s`' % key)
                elif must not in ev[key]:
                    problems.append('`exception.evidence.%s` does not name %s, which '
                                    'is what onRed says to check' % (key, must))
            for key in sorted(set(ev) - set(k for k, _ in EVIDENCE_FIELDS)):
                problems.append('`exception.evidence` carries `%s`, which this test '
                                'does not read' % key)

    if 'why' in exc and not _text(exc['why']):
        problems.append('`exception.why` says nothing')
    return problems


def exception_covers(fixture, have):
    """True when the exception names a platform and EVERY package of it was
    read here at exactly the version it names. None, the "do not know" of
    installed(), is never a match: an exception is honoured on a platform this
    file has seen, not on one it failed to read."""
    exc = fixture.get('exception')
    if not isinstance(exc, dict) or not isinstance(exc.get('platform'), dict):
        return False
    plat = exc['platform']
    return bool(plat) and all(have.get(pkg) == ver for pkg, ver in plat.items())


def describe(platform):
    return ', '.join('%s %s' % (pkg, platform[pkg]) for pkg in sorted(platform))


def excused(fixture, have):
    exc = fixture['exception']
    return ('%s premise expired on this platform (%s) and excused by the exception '
            '%s authorised on %s while %s is open; scripts/release.py build refuses '
            'to cut while it stands'
            % (PREMISE_ROW, describe(dict((p, have[p]) for p in exc['platform'])),
               exc['authorisedBy'], exc['date'], PREMISE_ROW))


def not_covered(fixture, have):
    """What a red run says about an exception that does not reach this machine."""
    exc = fixture.get('exception')
    if not isinstance(exc, dict) or not isinstance(exc.get('platform'), dict):
        return []
    misses = ['  %s: excepted %s, installed %s'
              % (pkg, ver, have.get(pkg) or 'unreadable')
              for pkg, ver in sorted(exc['platform'].items()) if have.get(pkg) != ver]
    return [
        '',
        'The exception authorised on %s covers exactly %s, and not this machine:'
        % (exc.get('date'), describe(exc['platform'])),
    ] + misses + [
        'An exception is not moved to a new platform by editing its versions: the',
        'evidence it records was taken on that one platform and no other.',
    ]


def judge_premise(case, fixture, have, board_text, today):
    """The whole decision the platform test makes, given what it read.

    `case` is the TestCase whose assertions decide, so the synthetic cases
    below drive this exact path -- the assertEqual that goes red and the
    skipTest that excuses -- rather than a copy of it (rule 12).
    """
    problems = exception_problems(fixture, board_text, today)
    case.assertEqual([], problems, '\n'.join([
        '',
        'tests/fixtures/a11y-premise.json carries an exception for %s that cannot'
        % PREMISE_ROW,
        'be honoured:',
    ] + ['  ' + p for p in problems] + [
        '',
        'The exception is the product owner\'s, dated and narrow: it covers one exact',
        'platform while %s reads open, and no release is cut while it stands.'
        % PREMISE_ROW,
    ]))
    stale = []
    checked = 0
    for pkg, recorded in sorted(fixture['platform'].items()):
        have_it = have.get(pkg)
        if have_it is None:
            continue
        checked += 1
        if have_it != recorded:
            stale.append('%s: measured on %s, installed %s' % (pkg, recorded, have_it))
    if checked == 0:
        case.skipTest('no package versions readable here; the premise cannot be checked')
    if stale and exception_covers(fixture, have):
        case.skipTest(excused(fixture, have))
    case.assertEqual([], stale, '\n'.join([
        '',
        'The accessibility premise D-A11Y-1 is deferred against was measured on a',
        'platform this machine no longer has:',
    ] + ['  ' + s for s in stale] + [
        '',
        fixture['premise'],
        '',
        fixture['onRed'],
        '',
        'Do not simply update the versions in tests/fixtures/a11y-premise.json.',
        'Re-measure first: if a PanelWindow now publishes a tree, D-A11Y-1 is LIVE',
        'and the Sources field values carry provider credentials onto the session bus.',
    ] + not_covered(fixture, have)))


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
        # The trigger became precise on 2026-09-25: the fix is a known commit
        # in an unreleased Quickshell (investigation section 10). A guard that
        # fires saying only "versions moved" makes the reader re-derive that
        # page; one that names the commit does not. Asserted here because a
        # fixture value nothing checks is a comment.
        self.assertIn('916a0dd', self.fixture['upstream'])
        self.assertIn('916a0dd', self.fixture['onRed'])
        # The row an exception may be tied to is the row the fixture says the
        # premise defers; PREMISE_ROW and this sentence are joined by a name.
        self.assertIn(PREMISE_ROW, self.fixture['whyItMatters'])

    def test_the_platform_the_premise_was_measured_on_is_still_the_one_here(self):
        have = dict((pkg, installed(pkg)) for pkg in self.fixture['platform'])
        # The board is read only when there is an exception to judge, so a
        # fixture without one behaves exactly as it did before exceptions.
        board_text = read_board() if 'exception' in self.fixture else ''
        judge_premise(self, self.fixture, have, board_text, datetime.date.today())


# The platform the premise was measured on and the one the 2026-10-31 exception
# names, written out so these cases survive the exception's removal from the
# real fixture and any later re-measure of its `platform`.
MEASURED = {'quickshell': '0.3.1-1', 'qt6-base': '6.11.2-3', 'at-spi2-core': '2.60.6-1'}
EXCEPTED = {'quickshell': '0.3.2.r7.g2b4501a-1', 'qt6-base': '6.12.0-3',
            'at-spi2-core': '2.62.1-1'}
TODAY = datetime.date(2026, 10, 31)


def board_with(state, ident=PREMISE_ROW):
    return ('# Status\n\n## Defects\n\n'
            '| ID | Sev | Task | Repro | State |\n'
            '|---|---|---|---|---|\n'
            '| D-A11Y-6 | P3 | M2-01 | the empty state | **open** |\n'
            '| %s | P3 | M2-01 Sources | the accessible Value | %s |\n'
            '\n## Decisions\n\n| %s | P1 | x | y | fixed |\n' % (ident, state, ident))


OPEN_BOARD = board_with('**open, half shipped.** The masking is refused.')


class ExceptionCase(unittest.TestCase):
    """The exception's narrowness, driven through the platform test's own path."""

    def fixture(self, **changes):
        with io.open(FIXTURE, encoding='utf-8') as fh:
            real = json.load(fh)
        out = dict((k, real[k]) for k in ('premise', 'upstream', 'whyItMatters', 'onRed'))
        out['platform'] = dict(MEASURED)
        out['exception'] = {
            'authorisedBy': 'the product owner',
            'date': '2026-10-31',
            'boardRow': 'D-A11Y-1',
            'platform': dict(EXCEPTED),
            'evidence': {
                'upstreamFix': 'the installed quickshell contains 916a0dd',
                'probe': 'scripts/a11y-probe.sh: 84 checks, 7 failures',
            },
            'why': 'unrelated work may land; nothing ships',
        }
        out['exception'].update(changes)
        return out

    def outcome(self, fixture, have, board_text=OPEN_BOARD, today=TODAY):
        case = unittest.TestCase()
        try:
            judge_premise(case, fixture, have, board_text, today)
        except unittest.SkipTest as skip:
            return 'skip', str(skip)
        except AssertionError as red:
            return 'red', str(red)
        return 'pass', ''

    def assertRed(self, got, *words):
        self.assertEqual('red', got[0], got[1])
        for w in words:
            self.assertIn(w, got[1])

    # -- honoured, and only just ----------------------------------------

    def test_the_exception_is_honoured_on_exactly_its_platform_while_the_row_is_open(self):
        verdict, reason = self.outcome(self.fixture(), dict(EXCEPTED))
        self.assertEqual('skip', verdict, reason)
        for words in ('D-A11Y-1 premise expired', 'the product owner', '2026-10-31',
                      'quickshell 0.3.2.r7.g2b4501a-1', 'qt6-base 6.12.0-3',
                      'at-spi2-core 2.62.1-1', 'release.py build refuses'):
            self.assertIn(words, reason)

    def test_without_the_exception_the_same_platform_is_red_as_designed(self):
        fixture = self.fixture()
        del fixture['exception']
        self.assertRed(self.outcome(fixture, dict(EXCEPTED), board_text=''),
                       'measured on 0.3.1-1, installed 0.3.2.r7.g2b4501a-1',
                       'Do not simply update the versions')

    def test_a_different_version_of_any_one_package_is_red(self):
        for pkg in sorted(EXCEPTED):
            with self.subTest(pkg=pkg):
                have = dict(EXCEPTED, **{pkg: EXCEPTED[pkg] + '.1'})
                self.assertRed(self.outcome(self.fixture(), have),
                               'and not this machine',
                               '%s: excepted %s, installed %s.1'
                               % (pkg, EXCEPTED[pkg], EXCEPTED[pkg]))

    def test_one_package_back_on_the_measured_version_is_still_red(self):
        # A mixed platform is neither the measured one nor the excepted one.
        have = dict(EXCEPTED, quickshell=MEASURED['quickshell'])
        self.assertRed(self.outcome(self.fixture(), have),
                       'quickshell: excepted 0.3.2.r7.g2b4501a-1, installed 0.3.1-1')

    def test_an_unreadable_package_is_not_a_match(self):
        have = dict(EXCEPTED, **{'at-spi2-core': None})
        self.assertRed(self.outcome(self.fixture(), have),
                       'at-spi2-core: excepted 2.62.1-1, installed unreadable')

    def test_the_measured_platform_passes_with_the_exception_present(self):
        self.assertEqual(('pass', ''), self.outcome(self.fixture(), dict(MEASURED)))

    def test_nothing_readable_still_skips_for_that_reason(self):
        have = dict((p, None) for p in MEASURED)
        verdict, reason = self.outcome(self.fixture(), have)
        self.assertEqual('skip', verdict, reason)
        self.assertIn('no package versions readable', reason)

    # -- ended -----------------------------------------------------------

    def test_a_row_that_reads_fixed_ends_the_exception(self):
        for state in ('**fixed on dev** (lane-a11y): masked', 'verified fixed',
                      'withdrawn on dev', 'fixed, the row was open until today'):
            with self.subTest(state=state):
                self.assertRed(
                    self.outcome(self.fixture(), dict(EXCEPTED), board_with(state)),
                    'D-A11Y-1 no longer reads open', 'the exception has ended',
                    'remove `exception`', 're-measure the premise per onRed')

    def test_an_ended_exception_is_red_on_the_measured_platform_too(self):
        # Its end is judged wherever it exists, not only where it is used.
        self.assertRed(self.outcome(self.fixture(), dict(MEASURED),
                                    board_with('fixed on dev')),
                       'the exception has ended')

    def test_an_ended_exception_is_red_where_no_version_is_readable(self):
        have = dict((p, None) for p in MEASURED)
        self.assertRed(self.outcome(self.fixture(), have, board_with('fixed on dev')),
                       'the exception has ended')

    def test_a_board_with_no_row_ends_the_exception(self):
        self.assertRed(self.outcome(self.fixture(), dict(EXCEPTED),
                                    '# Status\n\n## Defects\n\nnothing\n'),
                       'docs/STATUS.md has no D-A11Y-1 row')

    def test_the_open_states_the_board_writes_are_open(self):
        for state in ('**open, half shipped.**', 'open', 'open, upstream',
                      '**reopened**', '_open_ as a product-backlog item'):
            with self.subTest(state=state):
                self.assertEqual((True, state), row_state(board_with(state), PREMISE_ROW))
        for state in ('fixed on dev', 'verified fixed (was open)', 'accepted, open question',
                      'openly fixed', ''):
            with self.subTest(state=state):
                self.assertEqual((False, state), row_state(board_with(state), PREMISE_ROW))

    def test_the_row_parse_reaches_the_real_board(self):
        # The exception and the board are joined by an id; prove the join
        # finds the real row, whatever state it is in today.
        self.assertIsNotNone(row_state(read_board(), PREMISE_ROW)[1])

    # -- malformed -------------------------------------------------------

    def test_an_exception_missing_any_field_is_red(self):
        for key in EXCEPTION_FIELDS:
            with self.subTest(key=key):
                fixture = self.fixture()
                del fixture['exception'][key]
                self.assertRed(self.outcome(fixture, dict(EXCEPTED)),
                               'cannot', '`exception` has no `%s`' % key)

    def test_a_malformed_exception_is_red(self):
        cases = [
            ({'extra': 'covers 6.13 too'}, '`exception` carries `extra`'),
            ({'authorisedBy': 'the lead'}, "`exception.authorisedBy` is 'the lead'"),
            ({'date': '31 October 2026'}, 'not a YYYY-MM-DD date'),
            ({'date': '2026-02-30'}, 'not a YYYY-MM-DD date'),
            ({'date': 20261031}, 'not a YYYY-MM-DD date'),
            ({'date': '2026-11-01'}, 'is after today'),
            ({'boardRow': 'D-A11Y-6'}, "`exception.boardRow` is 'D-A11Y-6'"),
            ({'platform': ['quickshell']}, '`exception.platform` is a list'),
            ({'platform': dict((k, v) for k, v in EXCEPTED.items() if k != 'qt6-base')},
             'must name exactly the packages'),
            ({'platform': dict(EXCEPTED, mesa='26.0.0-1')}, 'must name exactly the packages'),
            ({'platform': dict(EXCEPTED, quickshell=' ')},
             '`exception.platform` has no version for quickshell'),
            ({'platform': dict(MEASURED)}, 'so it excuses nothing'),
            ({'evidence': 'trust me'}, '`exception.evidence` is a str'),
            ({'evidence': {'probe': 'scripts/a11y-probe.sh'}},
             '`exception.evidence` has no `upstreamFix`'),
            ({'evidence': {'upstreamFix': 'contains 916a0dd'}},
             '`exception.evidence` has no `probe`'),
            ({'evidence': {'upstreamFix': 'contains the fix', 'probe': 'a11y-probe.sh'}},
             '`exception.evidence.upstreamFix` does not name 916a0dd'),
            ({'evidence': {'upstreamFix': '916a0dd', 'probe': 'ran the probe'}},
             '`exception.evidence.probe` does not name a11y-probe.sh'),
            ({'evidence': {'upstreamFix': '916a0dd', 'probe': 'a11y-probe.sh',
                           'waiver': 'qt 6.13'}}, '`exception.evidence` carries `waiver`'),
            ({'why': '  '}, '`exception.why` says nothing'),
        ]
        for change, words in cases:
            with self.subTest(change=change):
                self.assertRed(self.outcome(self.fixture(**change), dict(EXCEPTED)), words)

    def test_an_exception_that_is_not_an_object_is_red(self):
        fixture = self.fixture()
        fixture['exception'] = 'the product owner said so'
        self.assertRed(self.outcome(fixture, dict(EXCEPTED)), '`exception` is a str')

    def test_a_malformed_exception_is_red_where_no_version_is_readable(self):
        have = dict((p, None) for p in MEASURED)
        self.assertRed(self.outcome(self.fixture(authorisedBy='the lead'), have),
                       '`exception.authorisedBy`')

    def test_an_empty_or_null_exception_is_red_wherever_it_runs(self):
        # The cut refuses on the key alone (tests/test_release.py), and this
        # test must not read an empty value as "no exception" either: on the
        # measured platform, or where nothing is readable, a falsy exception
        # would otherwise pass or skip in silence.
        unreadable = dict((p, None) for p in MEASURED)
        for value in ({}, None, '', [], 0, False):
            for have in (dict(MEASURED), unreadable):
                with self.subTest(value=value, have=have):
                    fixture = self.fixture()
                    fixture['exception'] = value
                    self.assertRed(self.outcome(fixture, have),
                                   'cannot', '`exception`')

    # -- the platform test's own reads -----------------------------------

    def run_platform_test(self, fixture, have, board_text):
        """The platform test itself, not judge_premise: with the fixture, the
        package versions and the board it reads replaced, so what it READS is
        what decides. Restores the two names whatever happens."""
        case = A11yPremiseCase(
            'test_the_platform_the_premise_was_measured_on_is_still_the_one_here')
        case.fixture = fixture
        swapped = {'installed': lambda pkg: have.get(pkg),
                   'read_board': lambda: board_text}
        saved = dict((name, globals()[name]) for name in swapped)
        globals().update(swapped)
        try:
            case.test_the_platform_the_premise_was_measured_on_is_still_the_one_here()
        except unittest.SkipTest as skip:
            return 'skip', str(skip)
        except AssertionError as red:
            return 'red', str(red)
        finally:
            globals().update(saved)
        return 'pass', ''

    def test_the_platform_test_judges_what_it_reads(self):
        # judge_premise is driven above with a board and versions handed to
        # it; this proves the platform test hands it the board and the pacman
        # versions it READ, not a forgiving board or the exception's own list.
        verdict, reason = self.run_platform_test(self.fixture(), dict(EXCEPTED), OPEN_BOARD)
        self.assertEqual('skip', verdict, reason)
        self.assertRed(self.run_platform_test(self.fixture(), dict(EXCEPTED),
                                              board_with('fixed on dev')),
                       'the exception has ended')
        self.assertRed(self.run_platform_test(self.fixture(),
                                              dict(EXCEPTED, **{'qt6-base': '6.12.1-1'}),
                                              OPEN_BOARD),
                       'qt6-base: excepted 6.12.0-3, installed 6.12.1-1')


if __name__ == '__main__':
    unittest.main()
