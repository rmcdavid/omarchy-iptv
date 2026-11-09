#!/usr/bin/env python3
"""Export the install artifact from `dev` onto `main`.

WHY THIS EXISTS. `omarchy plugin add` is a whole-repository `git clone`, with no
file allowlist, and the marketplace validates default-branch HEAD. For the
life of this project that meant everything on `main` landed in every user's
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv/`: the design documents,
the QA harness, a script that with --apply installs and removes the plugin,
and CLAUDE.md -- a root-level agent instruction file that any coding agent
opened inside that directory would read as its own instructions. The
marketplace reviewer found that last one on 2026-09-20 (issue #7374) and was
right to. So `main` is now the artifact and nothing else, and `dev` is where
the work happens.

THE RULE. What ships is an ALLOWLIST, spelled out file by file below. Not a
denylist: a denylist ships whatever nobody thought to exclude, and the whole
lesson here is that nobody thought. Adding a file to the artifact means
editing ALLOWLIST, and `release.py check` (run by check.sh) proves the list is
whole: every runtime import resolves inside it, every manifest entry point is
on it, the README points at nothing outside it, and no agent-instruction
filename is on it.

HOW A RELEASE HAPPENS. `release.py build`, on a clean `dev` whose local `main`
holds every commit origin's `main` does and no merge commit it lacks, for a
version origin has no tag for, in a clone that reads and pushes origin at one
URL (D-REL-13), after a green
gate: build a git tree holding exactly the allowlisted blobs at their current
`dev` content, validate it with `omarchy plugin validate` from an extracted
copy, commit it onto `main` with `main`'s current tip as parent, and tag it.
Nothing is pushed; that is a separate, deliberate step, and one atomic push
(`git push --atomic origin dev main vX.Y.Z`). `main` stays linear
because `omarchy-plugin-update` fast-forwards (`git merge --ff-only`), so a
rewritten `main` would strand every install.

Python 3 standard library only. Every subprocess is an argv list.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import posixpath
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_files  # noqa: E402  the model's files, read from Model.mjs (D-REL-5)
import helper_files  # noqa: E402  the helper's files, read from its stub (D-REL-7)

RELEASE_BRANCH = 'main'
DEV_BRANCH = 'dev'
# Where RELEASE_BRANCH is pushed, and what a cut must be able to fast-forward
# (D-REL-13, remote_main_problems).
RELEASE_REMOTE = 'origin'

# Exactly what a user needs and nothing they do not. Explicit paths, no globs.
ALLOWLIST = (
    'manifest.json',
    'README.md',
    'LICENSE',
    'CHANGELOG.md',
    'preview.png',
    'BarWidget.qml',
    'Guide.qml',
    'Service.qml',
    # D-REL-5: the model, as ES modules. Model.mjs re-exports the public names
    # from the parts under model/, which scripts/split-model.mjs cut out of the
    # one-file Model.js when that file outgrew the marketplace scanner's
    # per-file limit. check() follows every import and re-export line from
    # the QML entry points down, so a part missing here is red and a module
    # listed here that nothing loads is red too.
    'Model.mjs',
    'model/build.mjs',
    'model/text.mjs',
    'model/channels.mjs',
    'model/browse.mjs',
    'model/state.mjs',
    'model/settings.mjs',
    'model/logos.mjs',
    'model/player.mjs',
    'model/mpv.mjs',
    'model/rewind.mjs',
    'model/pip.mjs',
    'model/privacy.mjs',
    'model/epg.mjs',
    'model/contrast.mjs',
    'model/view.mjs',
    'model/sources.mjs',
    'model/source-records.mjs',
    'model/form-edit.mjs',
    # D-REL-7: the helper, as a stub that shields and then compiles these
    # parts, in the order its HELPER_PARTS lists, into its own namespace
    # (scripts/split-helper.py cut them from the one-file helper when it
    # neared FILE_CEILING). check() reads that list out of the stub, so a part
    # the stub loads that is missing here is red, and so is one listed here
    # that the stub does not load.
    'bin/omarchy-iptv',
    'bin/helper/01-core.py',
    'bin/helper/02-sources.py',
    'bin/helper/03-io-playlist.py',
    'bin/helper/04-epg.py',
    'bin/helper/05-ipc-logos.py',
    'bin/helper/06-failed.py',
    'bin/helper/07-player.py',
    'bin/helper/08-player-verbs.py',
    'bin/helper/09-cache.py',
    'bin/helper/10-state.py',
    'bin/helper/11-cli.py',
    'contrib/bindings.lua',
    'contrib/omarchy-menu.jsonc',
    'contrib/windows.lua',
)

# D-REL-5. The marketplace's automated security baseline refuses to scan any
# non-executable file over `securityFileByteLimit = 512 * 1024` bytes
# (scripts/security-baseline-limits.mjs in omacom/omarchy-plugin-marketplace;
# scripts/security-github-snapshot.mjs throws `security-baseline-scan-limit`),
# and a baseline that cannot complete is a verification request nobody can
# approve. Model.js passed at 0.13.4 with 2,105 bytes to spare and crossed it
# at 0.13.5, and nothing here could have gone red for it: the gate proved the
# allowlist whole, never that the artifact was one the marketplace can read.
# So every file on the allowlist, the executable helper included, is held to a
# ceiling 64 KiB below the scanner's number, and the gate goes red first.
# The executable is held on purpose. The scanner's size refusal treats mode
# 100755 differently, but not as an exemption: it reads the first 4 KiB of
# an oversized executable, and unless those bytes show a binary format (ELF,
# PE, Mach-O or a NUL) it throws the same scan-limit error, so a text helper
# over the limit fails the whole baseline exactly as Model.js did (measured
# by the 0.13.6 pre-cut review against a port of the scanner; an earlier
# version of this comment said the helper would ship UNREAD, which was
# wrong). Do not exempt executables here; tests/test_release.py goes red if
# anyone does.
SCANNER_FILE_LIMIT = 512 * 1024
FILE_CEILING = 448 * 1024

# Files a coding agent discovers and obeys automatically. None may ship, and
# the assertion is by NAME so a future edit to ALLOWLIST cannot sneak one in.
AGENT_INSTRUCTION_NAMES = (
    'CLAUDE.md', 'CLAUDE.local.md', 'AGENTS.md', 'AGENT.md', 'GEMINI.md',
    '.cursorrules', '.clinerules', '.windsurfrules', '.rules',
    '.github/copilot-instructions.md',
)

# Directories that are development-only by construction, plus every
# directory an agent tool treats as its own rule store. A name guard is
# narrower than the real convention set, so the allowlist stays explicit
# paths and any dot-directory at the root is dev-only regardless.
DEV_ONLY_DIRS = ('docs', 'tests', 'scripts', '.claude', '.github', '.cursor',
                 '.windsurf', '.clinerules', '.roo', '.junie', '.amazonq',
                 '.kiro')

# The three QML entry points: the runtime surface starts here, and check()
# follows what they load. A QML file names a local file with `import "<file>"`
# or Qt.resolvedUrl; an ES module (the model, D-REL-5) with `import ... from`,
# `export ... from` and a bare `import "<file>"`, a classic script with
# `.import "<file>" as X`. Every reference resolves against the directory of
# the file that makes it, as the engine resolves it.
#
# EVERY quoting the engine accepts, not the one the generator writes:
# measured 2026-10-12 on Qt 6.11.2 (qmltestrunner), `import 'a.mjs' as A` in
# QML, `import { b } from './b.mjs'` in a module and `.import 'c2.js' as C2`
# in a classic script all load. The first version matched double quotes on
# a `}`-led line only, and a hand-written single-quoted import of an
# unlisted file passed this check (the round-1 lens); only split-model's
# column-0 rule happened to catch it. A module statement may also span
# lines, so a specifier is taken from any line that starts like one.
RUNTIME_SOURCES = ('BarWidget.qml', 'Guide.qml', 'Service.qml')
RUNTIME_REF = re.compile(
    r"""^\s*import\s+(['"])([^'"\n]+)\1|Qt\.resolvedUrl\(\s*(['"])([^'"\n]+)\3\s*\)""", re.M)
MODULE_STATEMENT = re.compile(r'^\s*(?:import\b|export\b|from\b|\}|\.import\b)')
MODULE_SPECIFIER = re.compile(
    r"""(?:(?<![\w$])from|(?<![\w$.])import|^\s*\.import)\s*(['"])([^'"\n]+)\1""")
# A dynamic import cannot be followed by reading the text, so it is refused
# rather than skipped: what the resolver cannot see, it cannot prove ships.
DYNAMIC_IMPORT = re.compile(r'(?<![\w$.])import\s*\(')
MODULE_SUFFIXES = ('.mjs', '.js')

# A README on the artifact must not point at anything that is not there.
README_DEV_REF = re.compile(
    r'(?<![/\w.-])(?:docs|tests|scripts)/[\w./-]+|(?<![/\w.-])CLAUDE\.md\b')

# Nor may the shipped SOURCES, comments included. 0.7.1 shipped 34 comments
# citing CLAUDE.md by name and 36 naming docs/, tests/ or scripts/ paths that
# do not exist in an install (D-REL-2). A reader who greps the plugin for
# CLAUDE finds them first, and a cited path that cannot be opened is a
# citation to nothing. The helper's --help text was one of them. The model's
# modules join these as check() reaches them.
SHIPPED_SOURCES = RUNTIME_SOURCES + ('bin/omarchy-iptv',)

# Nor may ANY shipped file name `Model.js`, which no install has had since
# the model became Model.mjs and its parts (D-REL-5). Round 1 of the split
# left 34 such citations in the artifact -- "the value lives in Model.js",
# "must match Model.js" -- each one D-REL-2's shape, a pointer to nothing, and
# README_DEV_REF could not see them. Say "the model" or `Model.mjs`. History
# may name the old file, and says it is history by naming the commit:
# `Model.js at 422c8e1` (or `at commit <sha>`), seven to forty hex digits.
# Nothing looser counts, because "was" and "used to" are exactly the words a
# present-tense citation acquires when someone wants the gate quiet. The
# D-SINK-19 chain brings more of them at integration; this is what finds them.
MODEL_JS_NAME = re.compile(r'(?<![\w$-])Model\.js(?![\w-])')
MODEL_JS_HISTORY = re.compile(r'(?<![\w$-])Model\.js at (?:commit )?[0-9a-f]{7,40}(?![\w-])')

# Nor may shipped PROSE hand the user a command that does not exist. The
# helper lives in the plugin directory and is on nobody's PATH, so a bare
# `omarchy-iptv <subcommand>` in the README or the CHANGELOG is an
# instruction that exits 127 on every install. It was verified on 2026-09-14
# (QA-PLAYER.md PLY-WEAK-05), fixed in place the same day, given no id and no
# board row, and reappeared in two more shipped files within eleven days --
# once in README.md, shipped from v0.7.6, and once in CHANGELOG.md, caught by
# review the day before it would have (D-REL-3). The subcommand names are
# read from the helper's own parser so this list cannot drift from it.
SHIPPED_PROSE = ('README.md', 'CHANGELOG.md')
# The CHANGELOG's top heading, which must agree with manifest.json at the
# moment of the cut. `build` reads the version from the manifest alone, so
# nothing tied the two together: 0.8.0 shipped a changelog dated the day
# before the release, and a cut made without editing the heading would ship
# an artifact whose own changelog says "(unreleased)". Found by the 0.9.0
# preflight, which also found that the same unguarded step produced the
# 0.8.0 date.
CHANGELOG_HEADING = re.compile(r'^## +([0-9]+\.[0-9]+\.[0-9]+) +\((.+?)\)\s*$', re.M)
ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')

HELPER_SUBCOMMAND = re.compile(r'sub\.add_parser\("([a-z-]+)"')
HELPER_PATH_FORM = ('python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/'
                    'bin/omarchy-iptv')


def helper_subcommands(helper_source):
    return sorted(set(HELPER_SUBCOMMAND.findall(helper_source)))


def bare_helper_invocations(text, subcommands):
    """(line, matched text) for every `omarchy-iptv <subcommand>` that is not
    reached through a path. A `/` before the name is a path, `=` is an option
    value such as --wayland-app-id=omarchy-iptv, and a word or dot character
    is part of some other name. A bare name with no subcommand after it, such
    as the window class, is a name and not an instruction."""
    if not subcommands:
        return []
    pattern = re.compile(
        r'(?<![\w./=~-])omarchy-iptv\s+(?:%s)\b'
        % '|'.join(re.escape(sub) for sub in subcommands))
    # Scanned as one text, not line by line: README prose wraps at eighty
    # columns, and `omarchy-iptv` at the end of one line with `player stop`
    # at the start of the next is the same instruction to a reader and
    # invisible to a per-line scan. The reported line is where the name is.
    return [(text.count('\n', 0, m.start()) + 1, ' '.join(m.group(0).split()))
            for m in pattern.finditer(text)]


class ReleaseError(Exception):
    pass


def git(root, *args, check=True, env=None):
    proc = subprocess.run(['git', '-C', root] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=env)
    if check and proc.returncode != 0:
        raise ReleaseError('git %s: %s' % (
            ' '.join(args), proc.stderr.decode('utf-8', 'replace').strip()))
    return proc.stdout.decode('utf-8', 'replace')


def tracked(root):
    return set(p for p in git(root, 'ls-files', '-z').split('\0') if p)


def read(root, rel):
    with open(os.path.join(root, rel), encoding='utf-8') as fh:
        return fh.read()


# ---------------------------------------------------------------- check ----

def changelog_problems(root, strict, today=None):
    """The top CHANGELOG heading against manifest.json, at the cut.

    Only `build` calls this, and it calls it AFTER the tag and no-op guards,
    so a cut re-run the day after a failure reports the reason it failed
    rather than today's date. `check` is about the allowlist being whole and
    runs against synthetic trees carrying no release sections at all, which
    is why this is not part of it.

    `strict=False` returns nothing. That arm exists so the tests can state
    that drafting a release -- a heading ahead of the manifest, or an
    undated one -- is not an error outside the cut.

    At the cut the heading must name THIS version and carry TODAY's date.
    Requiring the date rather than merely a date is the point: 0.8.0 shipped
    a section dated 2026-09-25 and was cut on the 26th, because the heading
    was written on one day and the build run on the next, and nothing
    compared them. A heading still saying "(unreleased)" fails the same
    check, which is the other half of the same unguarded step.
    """
    problems = []
    try:
        version = json.loads(read(root, 'manifest.json'))['version']
        text = read(root, 'CHANGELOG.md')
    except Exception as error:               # unreadable is someone else's problem
        return ['could not read manifest.json / CHANGELOG.md: %s' % error]
    m = CHANGELOG_HEADING.search(text)
    if not m:
        return ['CHANGELOG.md has no "## <version> (<date>)" heading']
    heading, when = m.group(1), m.group(2).strip()
    if not strict:
        return problems
    if heading != version:
        problems.append('CHANGELOG.md leads with %s but manifest.json says %s; '
                        'the artifact would carry the wrong release notes' % (heading, version))
    stamp = today or datetime.date.today().isoformat()
    if not ISO_DATE.match(when):
        problems.append('CHANGELOG.md %s is dated %r; a released section is dated YYYY-MM-DD '
                        '(today is %s)' % (heading, when, stamp))
    elif when != stamp:
        problems.append('CHANGELOG.md %s is dated %s and the cut is %s; date the section on '
                        'the day it ships' % (heading, when, stamp))
    return problems


# D-A11Y-1's dated exception. On 2026-10-31 the accessibility premise
# tripwire (tests/test_a11y_premise.py) fired on a system update whose
# Quickshell carries the upstream fix, so D-A11Y-1 -- provider credentials on
# the session bus -- is treated as live. The product owner let unrelated work
# land on dev under a narrow exception recorded in the fixture, on the
# condition that NOTHING ships while it stands. The test honours the exception;
# this is the condition.
# [2026-11-01: D-A11Y-1 fixed (75cc827) and the exception removed; the guard
# stays, for a reopened row.]
A11Y_PREMISE_FIXTURE = 'tests/fixtures/a11y-premise.json'


def premise_exception_problems(root):
    """Why the cut must stop for the accessibility premise; [] when it need not.

    Only `build` calls this, for the reason `changelog_problems` gives: `check`
    runs in the everyday gate, and the exception exists precisely so that the
    gate can be green while it stands. Refusing in `check` would turn every
    gate red and undo the owner's decision; refusing in `build` makes the cut
    impossible and nothing else.

    An unreadable fixture refuses too. The real tree always carries it (the
    premise test reads it), so a cut that cannot see it cannot see whether the
    exception stands, and deleting the file is not a way past the condition.
    """
    try:
        data = json.loads(read(root, A11Y_PREMISE_FIXTURE))
    except Exception as error:               # missing, unreadable, or not JSON
        return ['%s could not be read (%s), so nothing shows whether the D-A11Y-1 '
                'exception stands, and a cut that cannot see it does not ship.'
                % (A11Y_PREMISE_FIXTURE, error)]
    if not isinstance(data, dict):
        return ['%s is not a JSON object, so nothing shows whether the D-A11Y-1 '
                'exception stands, and a cut that cannot see it does not ship.'
                % A11Y_PREMISE_FIXTURE]
    if 'exception' in data:
        return ['%s carries the dated exception for D-A11Y-1, and no release is cut '
                'while it stands: fix D-A11Y-1, then remove the exception and '
                're-measure the premise per its onRed.' % A11Y_PREMISE_FIXTURE]
    return []


# D-REL-13. `build` parents the release commit on the LOCAL main and never
# looked at the remote. On 2026-11-08 the owner added a file through GitHub's
# web UI, which commits to the default branch, and origin's main moved past
# the 0.18.0 release (dc402e7 -> ce68db5) while every clone's main stayed
# behind. A cut made then would have parented the new release on dc402e7, and
# the remote's ruleset (no non-fast-forward, no bypass) refuses that push --
# but only at push time, after the cut has already moved the local main and
# written the tag. The same ruleset refuses a force push too (one that got
# through, with the ruleset lifted, would strand every install, since
# `omarchy-plugin-update` is `git merge --ff-only`), so what an unguarded cut
# costs is a refused push and a local main and tag to unwind by hand. So the
# cut asks the remote first, and refuses.
#
# It asks about the tag the cut writes in the same call. A tag origin already
# has (a web-UI release, a push from another clone, or a push that was not
# atomic) makes the release step's atomic push refused whole, and leaves the
# local main and tag to unwind by hand. A plain push would move origin's main
# and refuse the tag, and the GitHub Release, which `gh release create
# --verify-tag` makes from origin's tag, would then name the wrong commit. So
# that refuses too.
#
# What it asks must be what the push meets. So it refuses a clone whose origin
# is pushed somewhere other than where ls-remote reads (a pushurl, a
# pushInsteadOf, several urls, all of which push and only the first of which
# ls-remote reads) or that maps a push onto other refs (remote.origin.push);
# it compares the two mains in the object graph the server has, with replace
# refs and a grafts file switched off; and a local main that is ahead passes
# only when what it adds holds no merge commit, because main stays linear and
# origin's ruleset refuses a merge there whatever the fast-forward says.
#
# It READS ONLY: `git ls-remote`, never a fetch, and nothing that writes a
# ref, an object or the config, so a refusal leaves the clone exactly as it
# was and the releaser runs the fetch themselves. A remote that cannot be
# asked refuses too, for premise_exception_problems' reason: a cut that
# cannot see whether it can be pushed does not ship. There is no flag that
# skips it. What it cannot see is a commit that lands on origin AFTER it
# asks. The ruleset still refuses main then, but a push that is not atomic
# sends the other refs anyway: measured against a local bare origin,
# `git push origin dev main vX.Y.Z` published dev and the tag while main was
# rejected. So the release step pushes with
# `git push --atomic origin dev main vX.Y.Z`, which refused all three
# together. After a non-atomic push the tag is on origin at a cut that is not
# on its main, and deleting the local tag is not enough: the fetch that brings
# main in brings that tag back, and this guard refuses a tag origin has, so a
# person deals with the published tag before anything is cut again.
REMOTE_TIMEOUT = 60                          # seconds; a remote that hangs is a refusal

# What the guard's git runs with, beside the caller's own environment, which it
# keeps. No prompt of any kind: GIT_TERMINAL_PROMPT=0 alone does not stop one,
# because git runs an askpass program (GIT_ASKPASS, core.askPass or
# SSH_ASKPASS) BEFORE it consults that variable -- measured, the program ran
# twice, user name and password -- and an empty GIT_ASKPASS is the one value
# that stops all three (ls-remote also carries credential.interactive=false,
# which stops git's prompt again in every git the remote helper starts, and
# ssh is told never to use one). Nothing fetched to answer a question about
# an object: a partial clone would. And the server's object graph, not this
# clone's view of it: a replace ref or a grafts file can give a commit a
# parent it does not have, which merge-base and rev-list honour and the
# server does not; GIT_GRAFT_FILE names a path that cannot exist, since
# /dev/null is no directory (GIT_NO_REPLACE_OBJECTS does not reach grafts).
_GUARD_ENV = {
    'GIT_TERMINAL_PROMPT': '0',
    'GIT_ASKPASS': '',
    'SSH_ASKPASS_REQUIRE': 'never',
    'GIT_NO_LAZY_FETCH': '1',
    'GIT_NO_REPLACE_OBJECTS': '1',
    'GIT_GRAFT_FILE': os.path.join(os.devnull, 'grafts'),
}

# A remote URL can carry a credential in its userinfo, and git's own messages
# can print the URL, so a message quoted from git loses everything between
# `scheme://` and the LAST `@` before the host (D-SINK-1's lesson).
_URL_USERINFO = re.compile(r'([A-Za-z][A-Za-z0-9+.-]*://)[^/\s]*@')
# What ls-remote prints is the hex id git's own client parsed, SHA-1 or
# SHA-256, so through git this never refuses. It is kept because the id is
# then handed to cat-file and merge-base, which would read anything else as a
# revision expression (`main` would pass as its own ancestor). Only a test
# double that answers for git reaches it
# (test_an_answer_that_is_not_a_commit_id_is_refused).
_OBJECT_ID = re.compile(r'^(?:[0-9a-f]{40}|[0-9a-f]{64})$')


def _git_detail(stderr):
    """git's first message line, with any URL userinfo dropped, for a refusal."""
    for line in stderr.decode('utf-8', 'replace').splitlines():
        line = _URL_USERINFO.sub(r'\1', line.strip()).rstrip('.')
        if line:
            return line
    return 'no message'


def _ask_remote(argv, env):
    """Run `argv`, the one command that talks to the remote, bounded by
    REMOTE_TIMEOUT, as a CompletedProcess. It runs in a session of its own,
    with no terminal to prompt on, and when it does not answer in time, or
    the cut is interrupted, the whole process group is killed: killing git
    alone left its remote helper and the prompt it had opened running,
    reparented, and once that prompt returned the helper opened a second one,
    after the cut had been refused (measured with a prompt that waited 25 s).
    A process that leaves the group itself is out of reach. Raises
    subprocess.TimeoutExpired once the group is killed."""
    with subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, env=env, start_new_session=True) as proc:
        try:
            out, err = proc.communicate(timeout=REMOTE_TIMEOUT)
        except BaseException:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raise
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def remote_main_problems(root, tag_name=None):
    """Why the cut must stop because RELEASE_REMOTE's RELEASE_BRANCH holds a
    commit the local one lacks, because the local one holds a merge commit
    the remote's lacks, because RELEASE_REMOTE already has the tag `tag_name`
    the cut would write, or because what is asked here is not where the push
    goes; [] when it need not (D-REL-13). With no `tag_name` (an untagged
    cut) only the branch is asked about.

    Only `build` calls this, after the clean-tree, branch and premise guards
    and before the allowlist check and the gate re-run, so a cut that could
    not be pushed stops in seconds and before anything is written.

    It passes when the remote has no such tag and its branch IS the local
    one, or is an ancestor of it with no merge commit between them: an
    earlier cut not pushed yet still fast-forwards. Anything else is one
    sentence that says what to run, and none of them says to force a push,
    which the remote refuses and every install would pay for if it got
    through.
    """
    ref = 'refs/heads/%s' % RELEASE_BRANCH
    tag_ref = 'refs/tags/%s' % tag_name if tag_name else None
    asked = [ref] + ([tag_ref] if tag_ref else [])
    remote_branch = "%s's %s" % (RELEASE_REMOTE, RELEASE_BRANCH)
    fetch = 'git fetch %s %s:%s' % (RELEASE_REMOTE, RELEASE_BRANCH, RELEASE_BRANCH)
    listing = 'git ls-remote %s %s' % (RELEASE_REMOTE, ' '.join(asked))
    nothing_shows = ('nothing shows whether %s holds a commit the local %s lacks%s, and a cut '
                     'that cannot see it does not ship'
                     % (remote_branch, RELEASE_BRANCH,
                        ' or whether %s already has the tag %s' % (RELEASE_REMOTE, tag_name)
                        if tag_name else ''))
    unseen = 'so ' + nothing_shows
    env = dict(os.environ, **_GUARD_ENV)

    def run(args):
        return subprocess.run(['git', '-C', root] + args, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    # Asked by name first: `git ls-remote origin` with no such remote reads
    # `origin` as a path, relative to wherever git happens to be.
    read_at = run(['remote', 'get-url', '--all', RELEASE_REMOTE])
    if read_at.returncode != 0:
        return ['this clone has no remote named %r, %s: add it and cut again.'
                % (RELEASE_REMOTE, unseen)]
    # ls-remote reads the first url; a push goes to every pushurl, or to every
    # url when there is none, each rewritten by pushInsteadOf. get-url applies
    # both rewritings, so one line, the same both ways, is the only answer
    # that makes what is read here the place the push lands.
    pushed_at = run(['remote', 'get-url', '--push', '--all', RELEASE_REMOTE])
    urls = read_at.stdout.splitlines()
    if pushed_at.returncode != 0 or pushed_at.stdout.splitlines() != urls or len(urls) != 1:
        return ['%s is not read and pushed at one and the same URL (git remote get-url --all '
                '%s and git remote get-url --push --all %s print different lines, or more '
                'than one), so what ls-remote reads need not be where the push lands and %s: '
                'give %s one URL for both and cut again.'
                % (RELEASE_REMOTE, RELEASE_REMOTE, RELEASE_REMOTE, nothing_shows,
                   RELEASE_REMOTE)]
    # A push refspec of the remote's own maps `git push origin main` onto
    # whatever ref it names (measured: refs/heads/main:refs/heads/elsewhere
    # pushed main to elsewhere), so the refs asked about would not be the ones
    # the release step moves. git config --get-all answers 1 for "not set".
    mapped = 'remote.%s.push' % RELEASE_REMOTE
    if run(['config', '--get-all', mapped]).returncode != 1:
        return ['%s has a push refspec of its own (%s), so the release push need not land on '
                'the refs asked about here and %s: unset it and cut again.'
                % (RELEASE_REMOTE, mapped, nothing_shows)]
    # push.default `upstream`, or its old name `tracking`, maps a branch named
    # bare on the push command line onto its branch.<name>.merge (measured on
    # git 2.56.0: `git push --atomic origin main` sent main to
    # refs/heads/elsewhere). git maps only when branch.main.remote is set and
    # main tracks exactly one branch; this refuses without asking either, so
    # it also refuses two configurations that would map nothing. `--get` reads
    # the last value, the one git uses.
    default = run(['config', '--get', 'push.default']).stdout.decode('utf-8', 'replace').strip()
    if default in ('upstream', 'tracking'):
        tracked = run(['config', '--get-all', 'branch.%s.merge' % RELEASE_BRANCH])
        for merge in tracked.stdout.decode('utf-8', 'replace').splitlines():
            merge = merge.strip()
            if merge and merge not in (ref, RELEASE_BRANCH):
                return ['push.default is %s and the local %s tracks %s (branch.%s.merge), so '
                        'the release push need not land on the refs asked about here and %s: '
                        'set push.default to simple, or have %s track %s, and cut again.'
                        % (default, RELEASE_BRANCH, merge, RELEASE_BRANCH, nothing_shows,
                           RELEASE_BRANCH, ref)]
    try:
        listed = _ask_remote(['git', '-c', 'credential.interactive=false', '-C', root,
                              'ls-remote', RELEASE_REMOTE] + asked, env)
    except subprocess.TimeoutExpired:
        return ['%s did not answer within %d s, %s: fix the remote or the network and '
                'cut again.' % (listing, REMOTE_TIMEOUT, unseen)]
    if listed.returncode != 0:
        return ['%s failed (%s), %s: fix the remote or the network and cut again.'
                % (listing, _git_detail(listed.stderr), unseen)]
    # The pattern is a TAIL match at a slash boundary, so a branch named
    # x/refs/heads/main is printed beside the real one, and either may come
    # first. Only the exact name decides, for the tag as for the branch. (With
    # a pattern, an annotated tag's peeled `^{}` line is not printed, so what
    # the tag's line carries may be a tag object, and the sentence names no id.)
    remote_sha = ''
    tagged = False
    for line in listed.stdout.decode('utf-8', 'replace').splitlines():
        sha, _, name = line.partition('\t')
        name = name.strip()
        if name == ref:
            remote_sha = sha.strip()
        elif tag_ref and name == tag_ref:
            tagged = True
    if tagged:
        return ['%s already has the tag %s, so the tag this cut writes could not be pushed '
                'and the GitHub Release would be made from that tag, not this cut: bump the '
                'manifest.json version, or have a person look at that tag, before cutting.'
                % (RELEASE_REMOTE, tag_name)]
    if not remote_sha:
        return ['%s has no %s, so nothing shows what a cut would be pushed over and there '
                'is no %s there to fast-forward: find out what happened to it before cutting.'
                % (RELEASE_REMOTE, ref, RELEASE_BRANCH)]
    if not _OBJECT_ID.match(remote_sha):
        return ['%s answered %r for %s, which is not a commit id, %s: look at the remote '
                'before cutting.' % (listing, remote_sha[:80], ref, unseen)]
    short = remote_sha[:12]
    # Whether the local main is behind or has diverged is not known until the
    # commit is here, so this names the fetch that is right either way: it
    # leaves the local main alone, where `main:main` is refused when the two
    # have diverged, and it names the branch, because a plain `git fetch
    # origin` fetches only what the clone's fetch refspec maps, and a clone
    # made with --single-branch -b dev (or --depth, which implies it) maps dev
    # alone: that fetch never brought main, and the refusal repeated. Named on
    # the command line, main is fetched whatever the refspec (the
    # remote-tracking ref moves too when the refspec has one). The next cut
    # then says which it is.
    if run(['cat-file', '-e', '%s^{commit}' % remote_sha]).returncode != 0:
        return ['%s is at %s, a commit this clone does not have, so a release cut onto the '
                'local %s could not be pushed: run git fetch %s %s and cut again.'
                % (remote_branch, short, RELEASE_BRANCH, RELEASE_REMOTE, RELEASE_BRANCH)]
    local = run(['rev-parse', '-q', '--verify', '%s^{commit}' % ref])
    local_sha = local.stdout.decode('utf-8', 'replace').strip()
    if local.returncode != 0 or not local_sha:
        return ['this clone has no local %s, so a release has nothing to be cut onto: run '
                '%s and cut again.' % (RELEASE_BRANCH, fetch)]
    if local_sha == remote_sha:
        return []
    # How main is settled without a merge: the local one set to the remote's,
    # which a person does once nothing on it needs keeping (an unpushed cut is
    # cut again). The local tag of such a cut is the existing-tag refusal's.
    settle = 'git update-ref %s %s' % (ref, short)

    def cannot_compare(failed):
        return ['git could not compare %s at %s with the local %s at %s (%s), so nothing '
                'shows that a cut here could be pushed: look at both before cutting.'
                % (remote_branch, short, RELEASE_BRANCH, local_sha[:12],
                   _git_detail(failed.stderr))]
    behind = run(['merge-base', '--is-ancestor', remote_sha, local_sha])
    if behind.returncode == 0:
        # The local main is ahead. It fast-forwards, and that is not enough:
        # a merge commit in what it adds is refused by origin's ruleset at
        # push time, after the cut has written main and the tag.
        added = run(['rev-list', '--min-parents=2', '%s..%s' % (remote_sha, local_sha)])
        if added.returncode != 0:
            return cannot_compare(added)
        merges = added.stdout.decode('utf-8', 'replace').split()
        if not merges:
            return []                        # ahead and linear: it fast-forwards
        return ['the local %s at %s holds a merge commit, %s, that %s at %s lacks, and %s '
                'stays linear (%s ruleset refuses a merge commit there), so a release cut '
                'onto the local %s could not be pushed: a person must look at what it holds '
                'and set the local %s to %s with %s before cutting again.'
                % (RELEASE_BRANCH, local_sha[:12], merges[0][:12], remote_branch, short,
                   RELEASE_BRANCH, "%s's" % RELEASE_REMOTE, RELEASE_BRANCH, RELEASE_BRANCH,
                   "%s's" % RELEASE_REMOTE, settle)]
    ahead = run(['merge-base', '--is-ancestor', local_sha, remote_sha])
    if behind.returncode == 1 and ahead.returncode == 0:
        return ['%s is at %s, ahead of the local %s at %s, so a release cut onto the local '
                '%s could not be pushed: run %s and cut again.'
                % (remote_branch, short, RELEASE_BRANCH, local_sha[:12], RELEASE_BRANCH,
                   fetch)]
    if behind.returncode == 1 and ahead.returncode == 1:
        return ['%s at %s and the local %s at %s have diverged, each holding a commit the '
                'other lacks, so no release cut here can be pushed and %s would be refused: '
                'a person must compare the two and settle %s with no merge commit, which '
                '%s ruleset refuses there, by setting the local %s to %s with %s before '
                'anything is cut.'
                % (remote_branch, short, RELEASE_BRANCH, local_sha[:12], fetch,
                   RELEASE_BRANCH, "%s's" % RELEASE_REMOTE, RELEASE_BRANCH,
                   "%s's" % RELEASE_REMOTE, settle)]
    return cannot_compare(behind if behind.returncode != 1 else ahead)


def check(root, out=sys.stdout):
    """Prove the allowlist is whole. Returns a list of problems."""
    problems = []
    have = tracked(root)
    allow = set(ALLOWLIST)

    largest = (0, '')
    for path in ALLOWLIST:
        if path not in have:
            problems.append('%s is on the allowlist but is not tracked' % path)
        elif os.path.isfile(os.path.join(root, path)):
            size = os.path.getsize(os.path.join(root, path))
            largest = max(largest, (size, path))
            if size > FILE_CEILING:
                problems.append(
                    '%s is %d bytes, over the %d-byte ceiling (448 KiB); the marketplace '
                    'scanner refuses a file over %d bytes and the verification request '
                    'could not be approved (D-REL-5) -- split it'
                    % (path, size, FILE_CEILING, SCANNER_FILE_LIMIT))
        top = path.split('/')[0]
        if top in DEV_ONLY_DIRS or (top.startswith('.') and '/' in path):
            problems.append('%s is under a development-only directory' % path)
        if path in AGENT_INSTRUCTION_NAMES or os.path.basename(path) in AGENT_INSTRUCTION_NAMES:
            problems.append('%s is an agent instruction file and may not ship' % path)

    # Every file the runtime loads from its own directory must ship, followed
    # from the QML entry points through every module they import.
    reached = runtime_files(root, have, allow, problems)
    for path in ALLOWLIST:
        if path.endswith(MODULE_SUFFIXES) and path not in reached:
            problems.append(
                '%s is on the allowlist but nothing the plugin loads imports it'
                % path)

    # D-REL-7. The helper the service runs is a stub that compiles the parts
    # its HELPER_PARTS names, so those must ship and nothing else under
    # bin/helper/ may: a part missing from the artifact is a helper that
    # cannot start on any install, and the split's prototype passed every
    # other check here while shipping exactly that.
    helper_parts = []
    if helper_files.STUB in have:
        try:
            helper_parts = helper_files.part_paths(root)
        except helper_files.HelperLayoutError as error:
            problems.append('%s' % error)
        for rel in helper_parts:
            if rel not in allow:
                problems.append(
                    '%s loads %s, which is not on the allowlist: the artifact would ship a '
                    'helper that cannot start (D-REL-7)' % (helper_files.STUB, rel))
        for rel in ALLOWLIST:
            if rel.startswith(helper_files.PART_DIR + '/') and rel not in helper_parts:
                problems.append(
                    '%s is on the allowlist but %s does not load it (D-REL-7)'
                    % (rel, helper_files.STUB))

    # D-HOST-1. Model.PLUGIN_VERSION travels with the LOADED QML; the version
    # in manifest.json travels with the DIRECTORY. The plugin compares them at
    # runtime to notice that a hot reload left an older component mounted, and
    # tells the user to restart. That comparison is only meaningful if the two
    # agree at release time, so this proves it -- otherwise every install would
    # show the notice permanently, or none ever would.
    if 'manifest.json' in have and model_files.AGGREGATOR in have:
        actual = json.loads(read(root, 'manifest.json')).get('version')
        try:
            model = model_files.model_source(root)
        except (IOError, model_files.ModelLayoutError) as error:
            model = ''
            problems.append('the model is unreadable: %s' % error)
        m = re.search(r'var\s+PLUGIN_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]', model)
        # An unreadable model is already a problem above; there is no
        # version to compare, and reading m.group of None here used to turn
        # that message into a traceback that never printed it.
        if not model:
            pass
        elif not m:
            problems.append('the model declares no PLUGIN_VERSION; D-HOST-1\'s stale-build notice cannot work')
        elif m.group(1) != actual:
            problems.append(
                'Model.PLUGIN_VERSION is %s but manifest.json says %s; every install would show the '
                'restart notice forever' % (m.group(1), actual))

    # Every manifest entry point must ship.
    if 'manifest.json' in have:
        manifest = json.loads(read(root, 'manifest.json'))
        for kind, path in (manifest.get('entryPoints') or {}).items():
            if path not in allow:
                problems.append(
                    'manifest entry point %s = %r is not on the allowlist'
                    % (kind, path))

    # The README ships as-is, so it may not name what does not.
    if 'README.md' in have:
        text = read(root, 'README.md')
        # A github URL can legitimately name the dev branch's files.
        text = re.sub(r'https?://\S+', '', text)
        for m in README_DEV_REF.finditer(text):
            problems.append(
                'README.md names %r, which is not on the artifact; point at '
                'the dev branch by URL instead' % m.group(0))
        # The README states a version in prose and the manifest states it as
        # data; the artifact shipped once with 0.7.0 beside 0.7.1. A stated
        # version must match; a README that states none is not asked to.
        stated = re.search(r'\bStatus:\s*v(\d+\.\d+\.\d+)', text)
        if stated and 'manifest.json' in have:
            actual = json.loads(read(root, 'manifest.json')).get('version')
            if stated.group(1) != actual:
                problems.append(
                    'README.md says Status: v%s but manifest.json says %s'
                    % (stated.group(1), actual))

    # A blank line inside a markdown table splits it, and the halves render as
    # paragraphs of punctuation. README.md's settings table shipped as THREE
    # tables for an unknown time -- four rows, then ten lines of pipes -- and
    # three separate adversarial prose passes read past it, because they were
    # reading the text and this is a defect in the SHAPE. A user skimming for
    # a setting sees a broken page and stops.
    for doc in SHIPPED_PROSE:
        if doc not in have:
            continue
        rows = read(root, doc).split('\n')
        for n, line in enumerate(rows):
            if line.strip() or n == 0 or n + 1 >= len(rows):
                continue
            if rows[n - 1].startswith('| ') and rows[n + 1].startswith('| '):
                problems.append(
                    '%s:%d is a blank line INSIDE a table; it splits the table '
                    'and the rows below render as text' % (doc, n + 1))

    # Shipped prose may not tell the user to run what they cannot.
    try:
        subcommands = (helper_subcommands(helper_files.helper_source(root))
                       if helper_files.STUB in have else [])
    except (OSError, helper_files.HelperLayoutError):
        subcommands = []                  # already a problem above
    for doc in SHIPPED_PROSE:
        if doc not in have:
            continue
        for n, hit in bare_helper_invocations(read(root, doc), subcommands):
            problems.append(
                '%s:%d tells the user to run %r, and omarchy-iptv is not on '
                'PATH; spell it %s (D-REL-3)' % (doc, n, hit, HELPER_PATH_FORM))

    # Shipped sources may not cite what does not ship, even in a comment.
    helper_sources = tuple(p for p in helper_parts if p in allow)
    for src in SHIPPED_SOURCES + helper_sources + tuple(p for p in reached if p not in SHIPPED_SOURCES):
        if src not in have:
            continue
        for n, line in enumerate(read(root, src).splitlines(), 1):
            m = README_DEV_REF.search(line)
            if m:
                problems.append(
                    '%s:%d names %r, which does not exist in an install; cite '
                    'the rule or the document by name and say it is on the dev '
                    'branch' % (src, n, m.group(0)))

    # Nor may any of them name the model file that no longer exists.
    for path in ALLOWLIST:
        if path not in have or not os.path.isfile(os.path.join(root, path)):
            continue
        try:
            text = read(root, path)
        except UnicodeDecodeError:
            continue  # preview.png
        for n, line in enumerate(text.splitlines(), 1):
            if len(MODEL_JS_NAME.findall(line)) > len(MODEL_JS_HISTORY.findall(line)):
                problems.append(
                    '%s:%d names Model.js, which no install has (D-REL-5); say "the model" or '
                    'Model.mjs, or for history name the commit: "Model.js at <sha>"' % (path, n))

    out.write('release allowlist: %d files, %d runtime sources scanned, largest %s at %d '
              'of %d bytes\n'
              % (len(ALLOWLIST), len(reached), largest[1] or '-', largest[0], FILE_CEILING))
    return problems


def module_refs(src, text, problems):
    """Every file a module or classic script names in a static import, in
    any quoting; a dynamic import is a problem, since nothing here can say
    what it loads. Comment lines are not code."""
    refs = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith(('//', '/*', '*')):
            continue
        if MODULE_STATEMENT.match(line):
            refs += [m.group(2) for m in MODULE_SPECIFIER.finditer(line)]
        if DYNAMIC_IMPORT.search(line):
            problems.append('%s:%d imports dynamically; the allowlist cannot be proven whole '
                            'over a load it cannot read -- import statically' % (src, n))
    return refs


def runtime_files(root, have, allow, problems):
    """Every tracked file the plugin loads, in the order it is reached: the
    QML entry points, then whatever they import, transitively. A reference to
    a local file that is not on the allowlist is appended to `problems`."""
    reached = []
    queue = [src for src in RUNTIME_SOURCES if src in have]
    while queue:
        src = queue.pop(0)
        if src in reached:
            continue
        reached.append(src)
        text = read(root, src)
        refs = [m.group(2) or m.group(4) for m in RUNTIME_REF.finditer(text)]
        if src.endswith(MODULE_SUFFIXES):
            refs += module_refs(src, text, problems)
        for ref in refs:
            if ref.startswith('qs.') or '://' in ref:
                continue  # a host module or an absolute URL, not a file
            target = posixpath.normpath(posixpath.join(posixpath.dirname(src), ref))
            if target.startswith('../') or target == '..' or target.startswith('/'):
                problems.append('%s loads %r, which is outside the plugin directory' % (src, ref))
                continue
            if target not in allow:
                problems.append(
                    '%s loads %r at runtime and it is not on the allowlist'
                    % (src, ref))
                continue
            if target.endswith(MODULE_SUFFIXES) and target in have and target not in reached:
                queue.append(target)
    return reached


# ---------------------------------------------------------------- build ----

def current_branch(root):
    return git(root, 'rev-parse', '--abbrev-ref', 'HEAD').strip()


def build_tree(root, source_ref):
    """A tree object holding exactly the allowlisted blobs from source_ref."""
    index = tempfile.NamedTemporaryFile(prefix='release-index-', delete=False)
    index.close()
    env = dict(os.environ, GIT_INDEX_FILE=index.name)
    try:
        git(root, 'read-tree', '--empty', env=env)
        for path in ALLOWLIST:
            line = git(root, 'ls-tree', source_ref, '--', path).strip()
            if not line:
                raise ReleaseError('%s is missing from %s' % (path, source_ref))
            meta, _ = line.split('\t', 1)
            mode, kind, sha = meta.split()
            if kind != 'blob':
                raise ReleaseError('%s is a %s, expected a file' % (path, kind))
            git(root, 'update-index', '--add', '--cacheinfo',
                '%s,%s,%s' % (mode, sha, path), env=env)
        return git(root, 'write-tree', env=env).strip()
    finally:
        os.unlink(index.name)


def tree_paths(root, tree):
    return set(p for p in git(root, 'ls-tree', '-r', '--name-only', '-z', tree)
               .split('\0') if p)


def validate_tree(root, tree):
    """omarchy plugin validate, against an extracted copy of the tree."""
    where = tempfile.mkdtemp(prefix='release-validate-')
    try:
        archive = subprocess.run(['git', '-C', root, 'archive', tree],
                                 stdout=subprocess.PIPE, check=True).stdout
        subprocess.run(['tar', '-x', '-C', where], input=archive, check=True)
        proc = subprocess.run(['omarchy', 'plugin', 'validate', where],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            raise ReleaseError('omarchy plugin validate rejected the artifact:\n'
                               + proc.stdout.decode('utf-8', 'replace'))
    finally:
        shutil.rmtree(where, True)


def build(root, gate_already_green=False, validate=True, tag=True,
          trailers=(), out=sys.stdout, today=None):
    if git(root, 'status', '--porcelain').strip():
        raise ReleaseError('the working tree is dirty; commit or stash first')
    if current_branch(root) != DEV_BRANCH:
        raise ReleaseError('releases are cut from %r, and this is %r'
                           % (DEV_BRANCH, current_branch(root)))
    # After the clean-tree guard, so the fixture read is the committed one, and
    # before the gate re-run, so a cut that cannot ship stops in a second
    # rather than after the whole gate.
    blocked = premise_exception_problems(root)
    if blocked:
        raise ReleaseError(' '.join(blocked))
    # The version names the tag, and the origin guard below asks about that
    # tag, so it is read here and not after the gate. A manifest that cannot
    # give one refuses in a sentence rather than a traceback; the allowlist
    # check used to be what spoke first about a missing manifest.
    try:
        version = json.loads(read(root, 'manifest.json'))['version']
    except (OSError, ValueError, KeyError, TypeError) as error:
        detail = ('%s: %s' % (type(error).__name__, error)).rstrip('.')
        raise ReleaseError('could not read the version from manifest.json (%s), so the cut '
                           'cannot name its tag or ask origin about it: fix it and cut again.'
                           % detail)
    tag_name = 'v%s' % version
    # D-REL-13: before the allowlist check and the gate re-run too, so a cut
    # that could not be pushed stops in seconds, and long before the refs
    # below are written. It reads only; a refusal leaves the clone as it was.
    behind = remote_main_problems(root, tag_name if tag else None)
    if behind:
        raise ReleaseError(' '.join(behind))
    problems = check(root, out=out)
    if problems:
        raise ReleaseError('the allowlist is not whole:\n  ' + '\n  '.join(problems))
    if not gate_already_green:
        gate = subprocess.run([os.path.join(root, 'scripts', 'check.sh')],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if gate.returncode != 0:
            raise ReleaseError('check.sh is red; a release never ships a red gate:\n'
                               + gate.stdout.decode('utf-8', 'replace')[-2000:])

    dev_sha = git(root, 'rev-parse', 'HEAD').strip()
    old_main = git(root, 'rev-parse', 'refs/heads/%s' % RELEASE_BRANCH).strip()

    if tag:
        existing = git(root, 'rev-parse', '-q', '--verify',
                       'refs/tags/%s^{commit}' % tag_name, check=False).strip()
        if existing:
            raise ReleaseError('tag %s already exists at %s; bump manifest.json '
                               'version first' % (tag_name, existing[:12]))

    # AFTER the tag and version guards above, so a cut re-run the day after a
    # failure reports the reason it failed rather than the date it is now.
    # And under its own banner: a changelog problem is not an allowlist
    # problem, and the releaser reading "the allowlist is not whole" about a
    # date goes looking in the wrong file.
    notes = changelog_problems(root, strict=True, today=today)
    if notes:
        raise ReleaseError('the release notes do not match this cut:\n  ' + '\n  '.join(notes))

    tree = build_tree(root, dev_sha)
    got = tree_paths(root, tree)
    if got != set(ALLOWLIST):
        raise ReleaseError('built tree does not match the allowlist: extra %s, '
                           'missing %s' % (sorted(got - set(ALLOWLIST)),
                                           sorted(set(ALLOWLIST) - got)))
    if tree == git(root, 'rev-parse', '%s^{tree}' % old_main).strip():
        raise ReleaseError('nothing to release: main already holds this exact artifact')
    if validate:
        validate_tree(root, tree)

    message = ('release: %s\n\nExported from %s@%s by scripts/release.py. '
               'The artifact is the %d allowlisted files and nothing else; '
               'development documents, tests, tooling and agent instruction '
               'files stay on %s.\n' % (version, DEV_BRANCH, dev_sha[:12],
                                        len(ALLOWLIST), DEV_BRANCH))
    for t in trailers:
        message += '\n%s' % t
    new = git(root, 'commit-tree', tree, '-p', old_main, '-m', message).strip()
    git(root, 'update-ref', 'refs/heads/%s' % RELEASE_BRANCH, new, old_main)
    if tag:
        git(root, 'tag', '-a', tag_name, new, '-m', 'release %s' % version)
    out.write('%s: %s -> %s (%s)\n' % (RELEASE_BRANCH, old_main[:12], new[:12], tag_name if tag else 'untagged'))
    for path in ALLOWLIST:
        out.write('  %s\n' % path)
    return new


# ----------------------------------------------------------------- main ----

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check', help='prove the allowlist is whole (run by check.sh)')
    b = sub.add_parser('build', help='export dev onto main and tag it; does not push')
    b.add_argument('--gate-already-green', action='store_true',
                   help='skip re-running check.sh (you just ran it)')
    b.add_argument('--no-validate', action='store_true',
                   help='skip omarchy plugin validate (tests only)')
    b.add_argument('--no-tag', action='store_true')
    b.add_argument('--trailer', action='append', default=[],
                   help='a trailer line for the release commit message')
    parser.add_argument('--root', default=None)
    args = parser.parse_args(argv)
    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        if args.cmd == 'check':
            problems = check(root)
            for p in problems:
                print('  ' + p)
            return 1 if problems else 0
        build(root, gate_already_green=args.gate_already_green,
              validate=not args.no_validate, tag=not args.no_tag,
              trailers=args.trailer)
        return 0
    except ReleaseError as e:
        print('release: REFUSED. %s' % e)
        return 1


if __name__ == '__main__':
    sys.exit(main())
