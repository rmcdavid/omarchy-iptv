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
                      behind the generated HEADER; the stub's HELPER_PARTS
                      names each with its length and CRC-32 (record below),
                      which the stub checks before any part runs

MODES (exactly one):
  --write   cut the one-file helper (--from-git REF, or --input FILE) into
            --root, then run --verify on what was written. Refuses a root
            whose bin/helper/ already holds anything.
  --verify  the same cut in memory against the tree on disk, every file byte
            for byte, and the proof that the cut loses nothing: head + body +
            tail is the input, and the parts without their headers
            concatenate to the body. A stub that differs is reported by
            region (head, loader, tail), because the head is the one-file
            helper's own text and is edited like any other code.
  --check   the tree as it stands, which the gate runs: HELPER_PARTS is read
            the one way every reader reads it (scripts/helper_files.py); the
            stub carries exactly the LOADER block those names generate,
            directly after the shield, so nothing is compiled before it; every
            name is a file under bin/helper/ that starts with HEADER, matches
            its entry and compiles, and bin/helper/ holds nothing else but
            names starting with "." (which the stub ignores too).
            The size ceiling is release.py's, on every allowlisted file, and
            its resolver proves every part ships.
  --seal    after an ordinary edit to a part (the parts are cut once and then
            edited as code): rewrite the stub's loader, so each entry of its
            HELPER_PARTS carries the part's length and CRC-32 as it now is,
            then --check. Every part edit changes the stub.

Exit status: 0 clean, 1 a problem (one line each on stderr), 2 usage.
Python 3 standard library only; ASCII only.
"""

import argparse
import os
import re
import subprocess
import sys
import zlib

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

# What the stub knows about each part (P2 of the D-REL-7 follow-up). Each
# entry of HELPER_PARTS is a part's name, its length and its CRC-32, both
# taken over the part's text with CRLF read as LF (`normalised` below), and
# the stub refuses a part that does not match its entry before any part
# runs. Kept in the STUB, not in the part, for the case a line in the part
# could not see: an update rewrites the parts one after another and the stub
# after them (git writes in index order and `h` sorts before `o`), so a
# helper spawned in between used to meet whole parts of two releases, run,
# write, and die on a NameError. Now the old stub refuses every part of the
# new release until the new stub lands, and a new stub refuses an old part.
#
# A checksum and a length rather than a cryptographic digest, on purpose:
# anyone able to rewrite the parts can rewrite the stub beside them, so no
# digest stored there could authenticate anything. It detects DAMAGE and a
# MIX: CRC-32 catches every truncation and every error burst up to 32 bits,
# and two releases of a part agree on both length and CRC by chance about
# once in four billion. zlib is cheap to import, where hashlib is imported
# late on purpose (01-core.py's import note).
#
# CRLF is read as LF because `omarchy plugin add` is a plain `git clone`
# and `omarchy-plugin-update` a `git merge --ff-only`, both of which honour
# a user's core.autocrlf=true and write every text file with CRLF (main
# ships no .gitattributes). Python compiles CRLF source as it compiles LF,
# so such a checkout is not damaged, and an entry over the raw bytes made
# every verb refuse on it while 0.14.2 ran (P1 of the follow-up's review).
# No part and not the stub holds a CR byte of its own (measured
# 2026-10-17), so the normalised text of any checkout is the committed blob.


def normalised(data):
    """A part's bytes as the stub judges them: CRLF read as LF."""
    return data.replace(b'\r\n', b'\n')


def record(name, data):
    """-> (name, length, crc32) of `data`, normalised: the entry the stub
    carries for the part and recomputes at every start."""
    data = normalised(data)
    return (name, len(data), zlib.crc32(data))


# The last line every part carried at lane-split-f1 (never shipped): --seal
# removes it, because the stub's record replaces it.
LEGACY_WITNESS = re.compile(rb'\n# end of \S+: [0-9]+ bytes above, crc32 [0-9a-f]{8}\n\Z')

LOADER = """

# D-REL-7: the rest of the helper is in the files below, under bin/helper/,
# because the marketplace's security scan refuses a file over 512 KiB and
# this one had grown to 447 KB. They are compiled into THIS module's
# namespace, in this order, exactly as if they were still one file: a name
# defined in any part is visible in every part, and a test that replaces a
# function on the module replaces it for every caller. They are compiled
# AFTER the shield above, which is the point of the order: what a same-uid
# process can read is now the interpreter starting and compiling this short
# file. The list is fixed and the files are read from this file's own
# directory (through any symlink to it), never from argv or the environment,
# and compile() writes no bytecode, so nothing is written into the plugin
# directory. Each entry carries the part's length and CRC-32 with CRLF read
# as LF (a core.autocrlf checkout is not damage), and ALL parts are read and
# checked before ANY of them runs: a part missing, not a regular file (opened
# without blocking, so a FIFO cannot stall the start), empty, not the part
# this list names (cut off, altered, or from another release, as during an
# update, which writes the parts before this file), not text, or not
# compiling, or a file here the list does not name (a name starting with "."
# excepted: an editor's swap file is not a part), ends the run before a verb
# can write anything, with one JSON error object on stdout and one line on
# stderr, like every other failure. Generated, and checked by the gate, by
# the split script on the dev branch.
HELPER_PARTS = (
@PARTS@)


def _load_parts(namespace: dict) -> None:
    import errno
    import os
    import stat
    import zlib

    def refuse(name, what):
        import json
        line = "bin/helper/%s %s; reinstall the plugin" % (name, what)
        sys.stdout.write(json.dumps({"ok": False, "part": name, "error": {
            "code": "helper_damaged", "message": line}}) + "\\n")
        sys.stdout.flush()
        sys.stderr.write("omarchy-iptv: %s\\n" % line)
        raise SystemExit(1)

    here = os.path.join(os.path.dirname(os.path.realpath(__file__)), "helper")
    codes = []
    for name, size, crc in HELPER_PARTS:
        path = os.path.join(here, name)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                refuse(name, "is not a regular file")
            with open(fd, "rb") as handle:
                source = handle.read(2 * size + 2)
        except OSError as error:
            if error.errno == errno.ENXIO:
                refuse(name, "is not a regular file")
            refuse(name, "cannot be read (%s)" % (error.strerror or type(error).__name__))
        source = source.replace(b"\\r\\n", b"\\n")
        if not source:
            refuse(name, "is empty")
        if len(source) != size or zlib.crc32(source) != crc:
            refuse(name, "is not the part this helper names (cut off, altered, or from another release)")
        try:
            if b"\\0" in source:
                raise UnicodeError
            source.decode("utf-8")
        except UnicodeError:
            refuse(name, "is not text")
        try:
            codes.append(compile(source, path, "exec", dont_inherit=True))
        except (SyntaxError, ValueError) as error:
            refuse(name, "does not compile (line %s)" % (getattr(error, "lineno", None) or "?"))
    try:
        found = os.listdir(here)
    except OSError as error:
        refuse("", "cannot be listed (%s)" % (error.strerror or type(error).__name__))
    named = set(name for name, _, _ in HELPER_PARTS)
    for name in sorted(set(found) - named):
        if not name.startswith("."):
            refuse(ascii(name)[1:-1], "is not one of this helper's parts")
    for code in codes:
        exec(code, namespace)


_load_parts(globals())


"""


class SplitError(Exception):
    pass


def loader_block(records):
    """The generated loader for these (name, length, crc32) entries."""
    return LOADER.replace('@PARTS@', ''.join('    ("%s", %d, 0x%08x),\n' % entry for entry in records))


def read_bytes(root, rel):
    with open(os.path.join(root, rel), 'rb') as fh:
        return fh.read()


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
    stub = head + loader_block([record(name, part.encode('utf-8')) for name, part in parts]) + tail
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
            where = stub_region(have, want) if rel == STUB else first_difference(have, want)
            problems.append('%s differs from the cut%s' % (rel, where))
    on_disk = sorted(os.listdir(os.path.join(root, PART_DIR))) if os.path.isdir(
        os.path.join(root, PART_DIR)) else []
    extra = sorted(n for n in set(on_disk) - {name for name, _ in parts} if not n.startswith('.'))
    if extra:
        problems.append('%s holds files the cut does not: %s' % (PART_DIR, ', '.join(extra)))
    return problems


def stub_regions(text):
    """-> (head through the shield, the loader, the tail from the guard), or
    None when the stub does not have that shape."""
    lines = text.splitlines(keepends=True)
    shields = [i for i, line in enumerate(lines) if line == SHIELD_LINE]
    guards = [i for i, line in enumerate(lines) if line == GUARD_LINE]
    if len(shields) != 1 or len(guards) != 1 or guards[0] < shields[0]:
        return None
    s, g = shields[0], guards[0]
    return ''.join(lines[:s + 1]), ''.join(lines[s + 1:g]), ''.join(lines[g:])


def stub_region(have, want):
    """Which of the stub's three regions differ, for --verify's line: the head
    is the one-file helper's own text, so an edit made since the cut (the
    shield docstring at c46ce50) shows there and nowhere else."""
    a, b = stub_regions(have), stub_regions(want)
    if a is None or b is None:
        return ' (it is not head, loader, tail)'
    which = [label for label, x, y in zip(('head', 'loader', 'tail'), a, b) if x != y]
    if 'loader' in which:
        # A part edited since the cut changes its entry, and only that.
        try:
            mine, cuts = helper_files.part_records(have), helper_files.part_records(want)
        except helper_files.HelperLayoutError:
            mine = cuts = None
        if mine and cuts and len(mine) == len(cuts) and (
                stub_regions(have)[1] == stub_regions(want)[1].replace(
                    loader_block(cuts), loader_block(mine))):
            names = [x[0] for x, y in zip(mine, cuts) if x != y]
            which[which.index('loader')] = 'loader, at the entr%s for %s only' % (
                'y' if len(names) == 1 else 'ies', ', '.join(names))
    return ' (in its %s)' % ' and '.join(which)


def first_difference(have, want):
    a, b = have.splitlines(keepends=True), want.splitlines(keepends=True)
    for n, (x, y) in enumerate(zip(a, b), 1):
        if x != y:
            return ' (from line %d)' % n
    return ' (from line %d)' % (min(len(a), len(b)) + 1)


def seal(root):
    """After an ordinary edit to a part: rewrite the stub's loader for the
    parts as they now are, each entry of HELPER_PARTS taking the length and
    CRC-32 of its part. A part still ending in lane-split-f1's generated
    last line (never shipped) loses it, since the entry replaces it. Nothing
    else is touched; --check then judges the result."""
    stub = helper_files.read(root, STUB)
    names = helper_files.part_names(stub)
    if not names:
        raise SplitError('%s assigns no HELPER_PARTS; --seal works on the split helper' % STUB)
    regions = stub_regions(stub)
    if regions is None:
        raise SplitError('%s does not have one shield line and one main guard' % STUB)
    changed, records = [], []
    for name in names:
        rel = '%s/%s' % (PART_DIR, name)
        data = read_bytes(root, rel)
        legacy = LEGACY_WITNESS.search(normalised(data))
        if legacy is not None:
            data = normalised(data)[:legacy.start() + 1]
            write_text(os.path.join(root, rel), data.decode('utf-8'))
            changed.append(rel)
        records.append(record(name, data))
    resealed = regions[0] + loader_block(records) + regions[2]
    if resealed != stub:
        write_text(os.path.join(root, STUB), resealed)
        changed.append(STUB)
    return changed


def write_text(path, text):
    mode = os.stat(path).st_mode & 0o777
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    os.chmod(path, mode)


def check(root):
    problems = []
    try:
        stub = helper_files.read(root, STUB)
        records = helper_files.part_records(stub)
    except (OSError, helper_files.HelperLayoutError) as error:
        return ['%s' % error]
    if not records:
        return ['%s assigns no HELPER_PARTS; it is not the split helper' % STUB]
    names = [name for name, _, _ in records]
    block = loader_block(records)
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
    for entry in records:
        name = entry[0]
        rel = '%s/%s' % (PART_DIR, name)
        try:
            data = read_bytes(root, rel)
            text = normalised(data).decode('utf-8')
        except (OSError, UnicodeError) as error:
            problems.append('%s is named in HELPER_PARTS and unreadable (%s)' % (rel, error))
            continue
        if not text.startswith(HEADER):
            problems.append('%s does not start with the generated part header' % rel)
        if record(name, data) != entry:
            problems.append('%s does not match its entry in HELPER_PARTS, which the helper '
                            'refuses (edited without --seal, or cut off)' % rel)
        try:
            compile(text, rel, 'exec', dont_inherit=True)
        except SyntaxError as error:
            problems.append('%s does not compile: %s' % (rel, error))
    # Nothing is exempt but what the stub exempts, a bytecode directory
    # included, so the gate is never more forgiving than the helper it
    # judges (rule 10): the stub ignores a name starting with "." (an
    # editor's swap file cannot be a part) and refuses anything else here
    # its list does not name.
    stray = sorted(name for name in on_disk - set(names) if not name.startswith('.'))
    if stray:
        problems.append('%s holds what HELPER_PARTS does not name, which the helper '
                        'refuses to start beside: %s' % (PART_DIR, ', '.join(stray)))
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--verify', action='store_true')
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--seal', action='store_true')
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
        if args.seal:
            for rel in seal(args.root):
                print('split-helper: sealed %s' % rel)
            problems, what = check(args.root), 'seal and check'
        elif args.write or args.verify:
            problems = verify(args.root, input_text(args))
            what = 'write and verify' if args.write else 'verify'
        else:
            problems = check(args.root)
            what = 'check'
    except SplitError as error:
        problems = [str(error)]
        what = ('write' if args.write else 'verify' if args.verify
                else 'seal' if args.seal else 'check')
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
