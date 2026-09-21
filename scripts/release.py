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
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

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
    'Model.js',
    'bin/omarchy-iptv',
    'contrib/bindings.lua',
    'contrib/omarchy-menu.jsonc',
    'contrib/windows.lua',
)

# Files a coding agent discovers and obeys automatically. None may ship, and
# the assertion is by NAME so a future edit to ALLOWLIST cannot sneak one in.
AGENT_INSTRUCTION_NAMES = (
    'CLAUDE.md', 'CLAUDE.local.md', 'AGENTS.md', 'GEMINI.md', '.cursorrules',
    '.clinerules', '.windsurfrules', '.github/copilot-instructions.md',
)

# Directories that are development-only by construction.
DEV_ONLY_DIRS = ('docs', 'tests', 'scripts', '.claude', '.github')

# The three QML entry points and the shared model: the runtime surface.
RUNTIME_SOURCES = ('BarWidget.qml', 'Guide.qml', 'Service.qml', 'Model.js')
RUNTIME_REF = re.compile(
    r'(?:^\s*import\s+"([^"]+)"|Qt\.resolvedUrl\("([^"]+)"\))', re.M)

# A README on the artifact must not point at anything that is not there.
README_DEV_REF = re.compile(
    r'(?<![/\w.-])(?:docs|tests|scripts)/[\w./-]+|(?<![/\w.-])CLAUDE\.md\b')


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

def check(root, out=sys.stdout):
    """Prove the allowlist is whole. Returns a list of problems."""
    problems = []
    have = tracked(root)
    allow = set(ALLOWLIST)

    for path in ALLOWLIST:
        if path not in have:
            problems.append('%s is on the allowlist but is not tracked' % path)
        top = path.split('/')[0]
        if top in DEV_ONLY_DIRS:
            problems.append('%s is under a development-only directory' % path)
        if path in AGENT_INSTRUCTION_NAMES or os.path.basename(path) in AGENT_INSTRUCTION_NAMES:
            problems.append('%s is an agent instruction file and may not ship' % path)

    # Every file the runtime loads from its own directory must ship.
    for src in RUNTIME_SOURCES:
        if src not in have:
            continue
        for m in RUNTIME_REF.finditer(read(root, src)):
            ref = m.group(1) or m.group(2)
            if ref.startswith('qs.') or '://' in ref:
                continue  # a host module or an absolute URL, not a file
            if ref not in allow:
                problems.append(
                    '%s loads %r at runtime and it is not on the allowlist'
                    % (src, ref))

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

    out.write('release allowlist: %d files, %d runtime sources scanned\n'
              % (len(ALLOWLIST), len(RUNTIME_SOURCES)))
    return problems


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
          trailers=(), out=sys.stdout):
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
