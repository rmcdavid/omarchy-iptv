#!/usr/bin/env python3
"""scripts/split-helper.py -- bin/omarchy-iptv as a stub and its parts (D-REL-7).

WHY. release.py holds every shipped file under 448 KiB, because the
marketplace's security baseline cannot scan a file over 512 KiB, executables
included (D-REL-5), and the one-file helper reached 445,263 bytes at 0.14.1
and 447,660 at 0.14.2, the last release cut from one file.
The owner chose the shape on 2026-10-15 (docs/HELPER-SPLIT.md): a stub that
shields first and then compiles the parts into its OWN namespace, so the
helper behaves as the one file it was cut from -- the same names, the same
definition order, one module a test can patch -- and nothing that runs or
imports `bin/omarchy-iptv` changes.

THE SHAPE.
  bin/omarchy-iptv    the one-file helper's head (everything up to and
                      including `SHIELDED = shield_environment()`), then the
                      generated LOADER block (HELPER_PARTS and _load_parts),
                      then its tail (the `if __name__ == "__main__":` guard)
  bin/helper/NN-*.py  each a contiguous run of the body between them, cut at
                      a section banner of the one-file helper (CUTS below),
                      behind the generated HEADER

MODES (exactly one):
  --write   cut the one-file helper (--from-git REF, or --input FILE) into
            --root, then run --verify on what was written. Refuses a root
            whose bin/helper/ already holds anything.
  --verify  the same cut in memory against the tree on disk, every file byte
            for byte, and the proof that the cut loses nothing: head + body +
            tail is the input, and the parts without their headers
            concatenate to the body.
  --check   the tree as it stands, which the gate runs: HELPER_PARTS is read
            the one way every reader reads it (scripts/helper_files.py); the
            stub carries exactly the LOADER block those names generate,
            directly after the shield, so nothing is compiled before it; every
            name is a file under bin/helper/ that starts with HEADER and
            compiles, and bin/helper/ holds nothing else. The size ceiling is
            release.py's, on every allowlisted file, and its resolver proves
            every part ships.

Exit status: 0 clean, 1 a problem (one line each on stderr), 2 usage.
Python 3 standard library only; ASCII only.
"""

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import helper_files  # noqa: E402  the one reader of HELPER_PARTS (D-REL-7)

STUB = helper_files.STUB
PART_DIR = helper_files.PART_DIR
SHIELD_LINE = 'SHIELDED = shield_environment()\n'
GUARD_LINE = 'if __name__ == "__main__":\n'

# Where the one-file helper is cut: each part begins at the line that starts
# with its banner, which must match exactly one line of the input, and the
# first begins right after the shield. Contiguous and in order, so the
# definition order is the one-file helper's.
CUTS = (
    ('01-core.py', None),
    ('02-sources.py', '# -------------------------------------------------------------- sources'),
    ('03-io-playlist.py', '# ------------------------------------------------------------------- IO'),
    ('04-epg.py', '# ----------------------------------------------------------------- EPG'),
    ('05-ipc-logos.py', '# ------------------------------------------------------------- mpv IPC'),
    ('06-failed.py', '# ---- dead-channel memory'),
    ('07-player.py', '# --------------------------------------------------------------- player'),
    ('08-player-verbs.py', '# ------------------------------------------------------------- the channel'),
    ('09-cache.py', '# --------------------------------------------------------------- cache'),
    ('10-state.py', '# --------------------------------------------------------------- state'),
    ('11-cli.py', '# ----------------------------------------------------- host config shield'),
)

HEADER = (
    '# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles\n'
    '# this file into its own namespace in the order its HELPER_PARTS lists, so\n'
    '# a part sees every name the parts before it define. Run the helper.\n'
    'from __future__ import annotations\n'
)

LOADER = '''

# D-REL-7: the rest of the helper is in the files below, under bin/helper/,
# because the marketplace's security scan refuses a file over 512 KiB and
# this one had grown to 447 KB. They are compiled into THIS module's
# namespace, in this order, exactly as if they were still one file: a name
# defined in any part is visible in every part, and a test that replaces a
# function on the module replaces it for every caller. They are compiled
# AFTER the shield above, which is the point of the order: what a same-uid
# process can read is now the interpreter starting and compiling this short
# file. The list is fixed and the files are read from this file's own
# directory, never from argv or the environment, and compile() writes no
# bytecode, so nothing is written into the plugin directory. Generated, and
# checked by the gate, by the split script on the dev branch.
HELPER_PARTS = (
%s)


def _load_parts(namespace: dict) -> None:
    import os
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "helper")
    for name in HELPER_PARTS:
        path = os.path.join(here, name)
        try:
            with open(path, "rb") as handle:
                source = handle.read()
        except OSError as error:
            sys.stderr.write("omarchy-iptv: cannot read bin/helper/%%s (%%s); reinstall the plugin\\n"
                             %% (name, error.strerror or type(error).__name__))
            raise SystemExit(1)
        exec(compile(source, path, "exec", dont_inherit=True), namespace)


_load_parts(globals())


'''


class SplitError(Exception):
    pass


def loader_block(names):
    return LOADER % ''.join('    "%s",\n' % name for name in names)


def one_line(lines, prefix, what):
    hits = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(hits) != 1:
        raise SplitError('%s: %r starts %d lines of the input, not exactly one'
                         % (what, prefix, len(hits)))
    return hits[0]


def cut(text):
    """-> (stub text, [(name, part text)]), with the losslessness asserted."""
    lines = text.splitlines(keepends=True)
    shield = one_line(lines, SHIELD_LINE, 'the shield')
    guard = one_line(lines, GUARD_LINE, 'the main guard')
    starts = [shield + 1]
    for name, banner in CUTS[1:]:
        at = one_line(lines, banner, name)
        if not starts[-1] < at < guard:
            raise SplitError('%s: its banner is out of order (line %d)' % (name, at + 1))
        starts.append(at)
    ends = starts[1:] + [guard]
    head = ''.join(lines[:shield + 1])
    body = ''.join(lines[shield + 1:guard])
    tail = ''.join(lines[guard:])
    parts = [(name, HEADER + ''.join(lines[a:b])) for (name, _), a, b in zip(CUTS, starts, ends)]
    names = [name for name, _ in parts]
    stub = head + loader_block(names) + tail
    # The two facts the cut rests on, checked rather than trusted.
    if head + body + tail != text:
        raise SplitError('the cut does not reassemble the input')
    if ''.join(part[len(HEADER):] for _, part in parts) != body:
        raise SplitError('the parts without their headers are not the body')
    return stub, parts


def input_text(args):
    if args.input:
        with open(args.input, encoding='utf-8') as fh:
            return fh.read()
    done = subprocess.run(['git', '-C', args.root, 'show', '%s:%s' % (args.from_git, STUB)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if done.returncode != 0:
        raise SplitError('git show %s:%s failed: %s'
                         % (args.from_git, STUB, done.stderr.decode('utf-8', 'replace').strip()))
    return done.stdout.decode('utf-8')


def write(root, text):
    stub, parts = cut(text)
    part_dir = os.path.join(root, PART_DIR)
    if os.path.isdir(part_dir) and os.listdir(part_dir):
        raise SplitError('%s already holds files; --write cuts a one-file helper only' % PART_DIR)
    os.makedirs(part_dir, exist_ok=True)
    for name, part in parts:
        with open(os.path.join(part_dir, name), 'w', encoding='utf-8', newline='') as fh:
            fh.write(part)
        os.chmod(os.path.join(part_dir, name), 0o644)
    stub_path = os.path.join(root, STUB)
    mode = os.stat(stub_path).st_mode & 0o777 if os.path.exists(stub_path) else 0o755
    with open(stub_path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(stub)
    os.chmod(stub_path, mode)


def verify(root, text):
    problems = []
    stub, parts = cut(text)
    expected = [(STUB, stub)] + [('%s/%s' % (PART_DIR, name), part) for name, part in parts]
    for rel, want in expected:
        try:
            have = helper_files.read(root, rel)
        except OSError as error:
            problems.append('%s: unreadable (%s)' % (rel, error))
            continue
        if have != want:
            problems.append('%s differs from the cut' % rel)
    on_disk = sorted(os.listdir(os.path.join(root, PART_DIR))) if os.path.isdir(
        os.path.join(root, PART_DIR)) else []
    extra = sorted(set(on_disk) - {name for name, _ in parts})
    if extra:
        problems.append('%s holds files the cut does not: %s' % (PART_DIR, ', '.join(extra)))
    return problems


def check(root):
    problems = []
    try:
        stub = helper_files.read(root, STUB)
        names = helper_files.part_names(stub)
    except (OSError, helper_files.HelperLayoutError) as error:
        return ['%s' % error]
    if not names:
        return ['%s assigns no HELPER_PARTS; it is not the split helper' % STUB]
    block = loader_block(names)
    lines = stub.splitlines(keepends=True)
    try:
        shield = one_line(lines, SHIELD_LINE, STUB)
    except SplitError as error:
        return [str(error)]
    after_shield = ''.join(lines[:shield + 1])
    if stub.count(block) != 1:
        problems.append('%s does not carry exactly the generated loader for its HELPER_PARTS '
                        '(hand-edited, or the names changed without regenerating it)' % STUB)
    elif not stub.startswith(after_shield + block):
        problems.append('%s compiles its parts somewhere other than directly after the '
                        'shield; nothing may be compiled before it (D-SINK-9)' % STUB)
    part_dir = os.path.join(root, PART_DIR)
    on_disk = set(os.listdir(part_dir)) if os.path.isdir(part_dir) else set()
    for name in names:
        rel = '%s/%s' % (PART_DIR, name)
        try:
            text = helper_files.read(root, rel)
        except OSError as error:
            problems.append('%s is named in HELPER_PARTS and unreadable (%s)' % (rel, error))
            continue
        if not text.startswith(HEADER):
            problems.append('%s does not start with the generated part header' % rel)
        try:
            compile(text, rel, 'exec', dont_inherit=True)
        except SyntaxError as error:
            problems.append('%s does not compile: %s' % (rel, error))
    stray = sorted(on_disk - set(names) - {'__pycache__'})   # gitignored, never ships
    if stray:
        problems.append('%s holds what HELPER_PARTS does not name, which would never run: %s'
                        % (PART_DIR, ', '.join(stray)))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--verify', action='store_true')
    mode.add_argument('--check', action='store_true')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--from-git', metavar='REF')
    source.add_argument('--input', metavar='FILE')
    parser.add_argument('--root', default=os.path.dirname(SCRIPT_DIR))
    args = parser.parse_args(argv)
    if (args.write or args.verify) and not (args.from_git or args.input):
        parser.error('--write and --verify need --from-git REF or --input FILE')
    try:
        if args.write:
            write(args.root, input_text(args))
        if args.write or args.verify:
            problems = verify(args.root, input_text(args))
            what = 'write and verify' if args.write else 'verify'
        else:
            problems = check(args.root)
            what = 'check'
    except SplitError as error:
        problems, what = [str(error)], 'write' if args.write else ('verify' if args.verify else 'check')
    for problem in problems:
        sys.stderr.write('split-helper: %s\n' % problem)
    if problems:
        return 1
    names = helper_files.part_names(helper_files.read(args.root, STUB))
    sizes = sorted((os.path.getsize(os.path.join(args.root, PART_DIR, n)), n) for n in names)
    print('split-helper: %s ok (%d parts, largest %s at %d bytes; the stub %d bytes)'
          % (what, len(names), sizes[-1][1], sizes[-1][0],
             os.path.getsize(os.path.join(args.root, STUB))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
