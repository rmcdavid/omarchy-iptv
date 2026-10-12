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

HOW A RELEASE HAPPENS. `release.py build`, on a clean `dev`, after a green
gate: build a git tree holding exactly the allowlisted blobs at their current
`dev` content, validate it with `omarchy plugin validate` from an extracted
copy, commit it onto `main` with `main`'s current tip as parent, and tag it.
Nothing is pushed; that is a separate, deliberate step. `main` stays linear
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
import subprocess
import posixpath
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_files  # noqa: E402  the model's files, read from Model.mjs (D-REL-5)

RELEASE_BRANCH = 'main'
DEV_BRANCH = 'dev'

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
    'bin/omarchy-iptv',
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
# The executable is held on purpose, although the scanner's size refusal
# skips mode 100755: an oversized executable is probed as a binary instead
# of being scanned, so exempting it here would let the helper ship UNREAD by
# the baseline, which is a hole and not a pass. Do not align this with the
# scanner's exemption; tests/test_release.py goes red if it is.
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
    subcommands = (helper_subcommands(read(root, 'bin/omarchy-iptv'))
                   if 'bin/omarchy-iptv' in have else [])
    for doc in SHIPPED_PROSE:
        if doc not in have:
            continue
        for n, hit in bare_helper_invocations(read(root, doc), subcommands):
            problems.append(
                '%s:%d tells the user to run %r, and omarchy-iptv is not on '
                'PATH; spell it %s (D-REL-3)' % (doc, n, hit, HELPER_PATH_FORM))

    # Shipped sources may not cite what does not ship, even in a comment.
    for src in SHIPPED_SOURCES + tuple(p for p in reached if p not in SHIPPED_SOURCES):
        if src not in have:
            continue
        for n, line in enumerate(read(root, src).splitlines(), 1):
            m = README_DEV_REF.search(line)
            if m:
                problems.append(
                    '%s:%d names %r, which does not exist in an install; cite '
                    'the rule or the document by name and say it is on the dev '
                    'branch' % (src, n, m.group(0)))

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
    problems = check(root, out=out)
    if problems:
        raise ReleaseError('the allowlist is not whole:\n  ' + '\n  '.join(problems))
    if not gate_already_green:
        gate = subprocess.run([os.path.join(root, 'scripts', 'check.sh')],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if gate.returncode != 0:
            raise ReleaseError('check.sh is red; a release never ships a red gate:\n'
                               + gate.stdout.decode('utf-8', 'replace')[-2000:])

    version = json.loads(read(root, 'manifest.json'))['version']
    tag_name = 'v%s' % version
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
