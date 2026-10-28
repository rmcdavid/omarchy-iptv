#!/usr/bin/env python3
"""Refuse UTF-8 that was decoded as a single-byte charset and encoded again.

WHY (D-DOC-28, 2026-10-28). docs/UX.md's glyph cells held every Nerd Font
codepoint as the UTF-8 of its own four bytes read as Latin-1: U+F0503 is
F3 B0 94 83 on disk, and the file held the four characters U+00F3 U+00B0
U+0094 U+0083 instead -- four characters where the glyph should be, two of
them invisible C1 controls. One commit put 57 of them there on 2026-09-13
(acd1723, a wording change to section 6.4 that rewrote 88 lines), and the
defect then spread BY COPY: later rows copied a neighbour's glyph cell byte
for byte, so 57 became 62 and then 64 on 50 lines, and the 6.4 glyph column
read as garbage for six weeks with every gate green. Nothing read for it.

WHAT IT FLAGS. A run of characters each of which is the image of ONE byte
under Latin-1 (U+0080..U+00FF) or under Windows-1252 (the 27 characters it
puts at 0x80..0x9F, the curly quotes, dashes, the ellipsis and the euro
sign, which a cp1252 round trip leaves behind where a Latin-1 one leaves C1
controls) is turned back into those bytes and walked for a valid UTF-8
sequence, strict: no overlong form, no surrogate, nothing past U+10FFFF. A
valid sequence is flagged when
  * it is three or four bytes long -- it decodes to U+0800 or above (the
    glyphs, the curly quotes and dashes, arrows, emoji), and no text writes
    a Latin-1 letter from U+00E0..U+00F4 followed by two or three symbols
    from U+0080..U+00BF; or
  * it is two bytes long and its lead is U+00C2 or U+00C3 (the classic
    accented-letter form, an e-acute as U+00C3 U+00A9), or its second
    character is a C1 control (U+0080..U+009F), which text never holds.
Everything else is a REJECTED candidate, counted on the summary line and
left alone: a character that cannot start a sequence, a lead whose
followers do not complete one, and a two-byte sequence whose lead is a
Latin-1 letter from U+00C4..U+00DF followed by a printable Latin-1 symbol
or a no-break space, because legitimate text writes exactly that -- an
upper-case accented word before a French closing guillemet with its
no-break space, a sharp s before a middle dot -- and decodes as valid
UTF-8 all the same. A guard red on legitimate text gets routed around.
Decode validity alone is the discriminator for everything else: an e-acute
followed by a letter decodes to nothing, so it is not touched.

WHAT IT SCANS. Every file `git ls-files --cached --others
--exclude-standard` lists (F-GATE-1: a file in the tree that is not yet
staged is the population a gate exists to police), read as UTF-8. A file
that is not UTF-8 text (a NUL byte, or bytes that do not decode) and a
symbolic link are skipped and NAMED on every run, never silently.
`--root DIR` scans another tree; FILE arguments scan exactly those files.

`--repair FILE...` rewrites each flagged sequence to the codepoint it
encodes and nothing else, and refuses to write unless the repaired text,
turned back through the same per-character reading at the same places, is
the original text exactly.

Exit 0 and one summary line ("double-encoding guard: N file(s) read (U
untracked), S skipped, C candidate(s) rejected, 0 problem(s)") when clean;
exit 1 with one `file:line:col: ...` per sequence otherwise. ASCII only, in
this file and in what it prints (CLAUDE.md rule 8). Python 3 stdlib only.
Not shipped.
"""
import os
import re
import subprocess
import sys

# The characters Windows-1252 puts at 0x80..0x9F, mapped to their byte. The
# five bytes it leaves undefined (0x81 0x8D 0x8F 0x90 0x9D) come back through
# the Latin-1 reading as the C1 control with the same number.
CP1252_BYTE = {}
for _b in range(0x80, 0xA0):
    try:
        _ch = bytes([_b]).decode("cp1252")
    except UnicodeDecodeError:
        continue
    if _ch != chr(_b):
        CP1252_BYTE[_ch] = _b

RUN = re.compile("[" + re.escape(chr(0x80)) + "-" + re.escape(chr(0xFF)) + "".join(re.escape(c) for c in sorted(CP1252_BYTE)) + "]+")


def byte_of(ch):
    o = ord(ch)
    if 0x80 <= o <= 0xFF:
        return o
    return CP1252_BYTE[ch]


def sequence_length(lead):
    if 0xC2 <= lead <= 0xDF:
        return 2
    if 0xE0 <= lead <= 0xEF:
        return 3
    if 0xF0 <= lead <= 0xF4:
        return 4
    return 0


def flagged(chars):
    """The rule in the docstring, for one valid sequence of `chars`."""
    if len(chars) >= 3:
        return True
    lead, second = chars
    return ord(lead) in (0xC2, 0xC3) or 0x80 <= ord(second) <= 0x9F


def scan_text(text):
    """(hits, rejected): hits are (offset, chars, decoded) for every flagged
    sequence; rejected counts the lead characters that started none."""
    hits = []
    rejected = 0
    for m in RUN.finditer(text):
        run = m.group()
        k = 0
        while k < len(run):
            n = sequence_length(byte_of(run[k]))
            if n == 0:
                k += 1
                continue
            chars = run[k:k + n]
            decoded = None
            if len(chars) == n:
                try:
                    decoded = bytes(byte_of(c) for c in chars).decode("utf-8")
                except UnicodeDecodeError:
                    decoded = None
            if decoded is not None and flagged(chars):
                hits.append((m.start() + k, chars, decoded))
                k += n
            else:
                rejected += 1
                k += 1
    return hits, rejected


def escape(s):
    return "".join("\\u%04x" % ord(c) if ord(c) < 0x10000 else "\\U%08x" % ord(c) for c in s)


def position(text, offset):
    line = text.count("\n", 0, offset) + 1
    col = offset - (text.rfind("\n", 0, offset) + 1) + 1
    return line, col


def repair_text(text):
    """The text with every flagged sequence replaced by what it encodes, and
    the hits, after proving the reverse at the same places is the original."""
    hits, _ = scan_text(text)
    out = []
    last = 0
    for offset, chars, decoded in hits:
        out.append(text[last:offset])
        out.append(decoded)
        last = offset + len(chars)
    out.append(text[last:])
    repaired = "".join(out)
    # The reverse transform, walked over the REPAIRED text: each decoded
    # character, at the place the repair put it, is turned back into the
    # characters it was read from.
    back = []
    pos = 0
    shift = 0
    for offset, chars, decoded in hits:
        at = offset - shift
        if repaired[at:at + len(decoded)] != decoded:
            raise AssertionError("repair misplaced a sequence at offset %d" % offset)
        back.append(repaired[pos:at])
        back.append(chars)
        pos = at + len(decoded)
        shift += len(chars) - len(decoded)
    back.append(repaired[pos:])
    if "".join(back) != text:
        raise AssertionError("reverse of the repair is not the original")
    return repaired, hits


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def corpus(root):
    def ls(*extra):
        out = subprocess.run(
            ["git", "-C", root, "ls-files", "-z"] + list(extra),
            stdout=subprocess.PIPE, check=True).stdout
        return [p for p in out.decode("utf-8").split("\0") if p]
    untracked = set(ls("--others", "--exclude-standard"))
    return ls("--cached", "--others", "--exclude-standard"), untracked


def read_text(path):
    """The file's text, or None when it is a link or not UTF-8 text."""
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        data = fh.read()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def check(root, files, untracked):
    """`files` are paths relative to `root`, or absolute."""
    problems = []
    skipped = []
    read = new = rejected_total = 0
    for rel in files:
        path = os.path.join(root, rel)
        text = read_text(path)
        if text is None:
            if os.path.lexists(path):
                skipped.append(rel)
            continue
        read += 1
        if rel in untracked:
            new += 1
        hits, rejected = scan_text(text)
        rejected_total += rejected
        for offset, chars, decoded in hits:
            line, col = position(text, offset)
            problems.append(
                "%s:%d:%d: U+%04X written as %d characters (%s)%s; "
                "scripts/check-double-encoding.py --repair %s"
                % (rel, line, col, ord(decoded), len(chars), escape(chars),
                   " (untracked)" if rel in untracked else "", rel))
    return read, new, skipped, rejected_total, problems


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = repo_root()
    if argv[:1] == ["--repair"]:
        paths = argv[1:]
        if not paths:
            print("usage: check-double-encoding.py --repair FILE...")
            return 2
        for path in paths:
            text = read_text(path)
            if text is None:
                print("%s: not UTF-8 text; nothing repaired" % path)
                return 1
            repaired, hits = repair_text(text)
            if hits:
                with open(path, "wb") as fh:
                    fh.write(repaired.encode("utf-8"))
            print("%s: %d sequence(s) repaired" % (path, len(hits)))
        return 0
    if argv[:1] == ["--root"]:
        if len(argv) < 2:
            print("usage: check-double-encoding.py [--root DIR] [FILE...]")
            return 2
        root = os.path.abspath(argv[1])
        argv = argv[2:]
    if any(a.startswith("-") for a in argv):
        print("usage: check-double-encoding.py [--root DIR] [FILE...] | --repair FILE...")
        return 2
    if argv:
        files, untracked = [os.path.abspath(a) for a in argv], set()
    else:
        files, untracked = corpus(root)
    read, new, skipped, rejected, problems = check(root, files, untracked)
    for line in problems:
        print(line)
    if skipped:
        print("double-encoding guard: skipped as a link or not UTF-8 text: %s"
              % ", ".join(skipped))
    if read == 0:
        print("double-encoding guard: read no files at all")
        return 1
    print("double-encoding guard: %d file(s) read (%d untracked), %d skipped,"
          " %d candidate(s) rejected, %d problem(s)"
          % (read, new, len(skipped), rejected, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
