"""D-DOC-35 (2026-11-06): the chords this plugin documents are free of the
stock Omarchy bindings, checked against the stock bindings on this machine.

How it was found: on omarchy-settings 4.5.0-3 stock binds SUPER + SHIFT + T
to "Activity" (btop, default/hypr/bindings/utilities.lua), SUPER + SHIFT + I
to "Switch input language back" (input-method.lua) and SUPER + SHIFT + Q to
"Calculator" (applications.lua). contrib/bindings.lua bound the guide to
SUPER + SHIFT + T with `o.bind`, which does not unbind first, so after
pasting it both binds were registered on the chord (one key press most
likely runs both; that half is read, not pressed). Measured on 2026-11-06:
red on those chords, green once the guide moved to SUPER + ALT + T and the
picture-in-picture suggestion to SUPER + SHIFT + V. A red here now is a NEW
stock bind on a chord the plugin documents: pick a free chord and re-check
D-DOC-35.

The join is a NAME (a chord string in our files, a chord string in the
host's), which rule 13 says nothing verifies unless something calls it.
This parses every `o.bind`, `o.rebind`, `o.bind_toggle` and `o.bind_hold`
chord in the stock bindings directory -- including the ones behind
`o.preinstalled_bindings_enabled()`, which is on by default, and the
`code:NN` chords built in a `for` loop -- normalising modifier order, and
refuses any stock call whose chord it cannot read rather than skipping it.
It then fails when a chord the plugin
  - binds or suggests (every `o.bind`/`o.rebind` string in
    contrib/bindings.lua, commented out or not),
  - calls free in contrib/bindings.lua's comments (a chord written out, or a
    bare letter under the file's own SUPER + SHIFT convention, followed by
    "is free" / "are free", and a letter list "... leaves only H J K free"),
  - or names in README.md as the plugin's (every backticked chord, with the
    "`SUPER + SHIFT + H` / `L` / `R`" shorthand expanded, except one the
    same clause says stock already uses)
is stock-bound. OMARCHY_HYPR_BINDINGS_DIR points the host half at another
stock tree, OMARCHY_IPTV_DOC_ROOT the plugin half at another checkout.
"""
import glob
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("OMARCHY_IPTV_DOC_ROOT", os.path.dirname(HERE))
STOCK = os.environ.get("OMARCHY_HYPR_BINDINGS_DIR", "/usr/share/omarchy/default/hypr/bindings")

MODIFIERS = {"SUPER", "SHIFT", "CTRL", "ALT"}
CALL_RE = re.compile(r"\bo\.(?:bind|rebind|bind_toggle|bind_hold)\(\s*")
STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def chord(text):
    """("ALT", "SHIFT", "SUPER"), "T") for "SUPER + SHIFT + ALT + t"; None for
    a string that is not one modifier set and one key."""
    parts = [p.strip().upper() for p in text.split("+")]
    if not parts or any(not p for p in parts):
        return None
    keys = [p for p in parts if p not in MODIFIERS]
    if len(keys) != 1:
        return None
    return (tuple(sorted(p for p in parts if p in MODIFIERS)), keys[0])


def spell(c):
    order = ["SUPER", "SHIFT", "CTRL", "ALT"]
    return " + ".join(sorted(c[0], key=order.index) + [c[1]])


def first_argument(text, start):
    """The source text of a call's first argument: up to the first comma at
    depth 0 outside a string."""
    depth, i = 0, start
    while i < len(text):
        ch = text[i]
        if ch == '"':
            m = STRING_RE.match(text, i)
            if m is None:
                raise ValueError("unterminated string at %d" % i)
            i = m.end()
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return text[start:i]
            depth -= 1
        elif ch == "," and depth == 0:
            return text[start:i]
        i += 1
    raise ValueError("no end to the argument at %d" % start)


def binding(text, name, pos):
    """The nearest `local name = <expr>` or `for name = a, b do` before pos:
    ("local", expr) or ("for", range)."""
    best = None
    for m in re.finditer(r"^\s*local %s = (.+)$" % re.escape(name), text[:pos], re.M):
        best = (m.start(), ("local", m.group(1).strip()))
    for m in re.finditer(r"\bfor %s = (\d+), (\d+) do\b" % re.escape(name), text[:pos]):
        if best is None or m.start() > best[0]:
            best = (m.start(), ("for", range(int(m.group(1)), int(m.group(2)) + 1)))
    if best is None:
        raise ValueError("%s is bound nowhere before %d" % (name, pos))
    return best[1]


def evaluate(expr, text, pos):
    """Every string a Lua chord expression takes: literals joined by `..`,
    names bound by a `local` or a numeric `for`, and `tostring(name [+-] n)`.
    Anything else raises, so a stock bind this cannot read is a red, never a
    silent miss."""
    values = [""]
    for part in (p.strip() for p in expr.split("..")):
        m = re.fullmatch(STRING_RE.pattern, part)
        if m:
            values = [v + m.group(1) for v in values]
            continue
        m = re.fullmatch(r"tostring\((\w+)\s*(?:([+-])\s*(\d+))?\)", part)
        name, offset = (m.group(1), int(m.group(3) or 0) * (-1 if m.group(2) == "-" else 1)) if m else (part, 0)
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise ValueError("cannot read %r" % part)
        kind, bound = binding(text, name, pos)
        if kind == "for":
            inner = [str(n + offset) for n in bound]
        elif offset or m:
            raise ValueError("arithmetic on a local: %r" % part)
        else:
            inner = evaluate(bound, text, pos)
        if len(values) != 1 and len(inner) != 1:
            raise ValueError("two loops in one chord: %r" % expr)
        values = [v + i for v in values for i in inner]
    return values


def stock_chords(directory):
    """{chord: [file:line description, ...]} for every stock bind, and the
    calls it could not read."""
    found, unread = {}, []
    for path in sorted(glob.glob(os.path.join(directory, "*.lua"))):
        text = read(path)
        for m in CALL_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            where = "%s:%d" % (os.path.basename(path), line)
            try:
                for value in evaluate(first_argument(text, m.end()).strip(), text, m.start()):
                    c = chord(value)
                    if c is None:
                        unread.append("%s %r" % (where, value))
                        continue
                    found.setdefault(c, []).append(where)
            except ValueError as exc:
                unread.append("%s %s" % (where, exc))
    return found, unread


def contrib_chords(text):
    """(chord, why) for every chord contrib/bindings.lua binds, suggests or
    calls free."""
    out = []
    for m in re.finditer(r'\bo\.(?:bind|rebind)\(\s*"([^"]+)"', text):
        c = chord(m.group(1))
        line = text.count("\n", 0, m.start()) + 1
        out.append((c, "contrib/bindings.lua:%d binds or suggests %r" % (line, m.group(1))))
    comments = []
    for n, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if s.startswith("--") and not re.match(r"^--\s*o\.", s):
            comments.append((n, s[2:].strip()))
    # a paragraph of comment lines, read as one sentence stream
    paragraphs, current = [], []
    for n, s in comments:
        if current and n != current[-1][0] + 1:
            paragraphs.append(current)
            current = []
        current.append((n, s))
    if current:
        paragraphs.append(current)
    for para in paragraphs:
        prose = " ".join(s for _n, s in para)
        starts, at = [], 0
        for n, s in para:
            starts.append((at, n))
            at += len(s) + 1

        def line_at(offset):
            return [n for a, n in starts if a <= offset][-1]

        for m in re.finditer(r"((?:[A-Z]+ \+ )+[A-Za-z0-9:]+)\s+(?:is|are)\s+free\b", prose):
            out.append((chord(m.group(1)), "contrib/bindings.lua:%d calls %r free" % (line_at(m.start()), m.group(1))))
        for m in re.finditer(r"(?<![+\w])(?<!\+ )([A-Z])\s+is\s+free\b", prose):
            out.append((chord("SUPER + SHIFT + " + m.group(1)),
                        "contrib/bindings.lua:%d calls SUPER + SHIFT + %s free" % (line_at(m.start()), m.group(1))))
        for m in re.finditer(r"((?:[A-Z]+ \+ )+)<letter>[^.]*?\bleaves only ((?:[A-Z]\b[ ,]*(?:and )?)+)free\b", prose):
            for letter in re.findall(r"[A-Z]", m.group(2)):
                out.append((chord(m.group(1) + letter),
                            "contrib/bindings.lua:%d lists %s%s as free" % (line_at(m.start(2)), m.group(1), letter)))
    return out


def readme_chords(text):
    """(chord, why) for every backticked chord README.md names for the
    plugin."""
    out = []
    for m in re.finditer(r"`((?:[A-Z]+ \+ )+[A-Za-z0-9:]+)`((?:\s*/\s*`[A-Za-z0-9:]+`)*)", text):
        line = text.count("\n", 0, m.start()) + 1
        after = text[m.end():m.end() + 60]
        if re.match(r"\s*,?\s*which (?:stock|Omarchy)\b[^.;]*\b(?:already uses|already binds|uses|binds)\b", after):
            continue
        base = chord(m.group(1))
        out.append((base, "README.md:%d names %r" % (line, m.group(1))))
        prefix = m.group(1).rsplit("+", 1)[0] + "+ "
        for extra in re.findall(r"`([A-Za-z0-9:]+)`", m.group(2)):
            out.append((chord(prefix + extra), "README.md:%d names %s%s" % (line, prefix, extra)))
    return out


@unittest.skipUnless(os.path.isdir(STOCK), "no stock Omarchy bindings under %s" % STOCK)
class StockBindingsCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.stock, cls.unread = stock_chords(STOCK)

    def test_every_stock_bind_is_read(self):
        self.assertEqual([], self.unread, "stock binds this parser cannot read; extend it rather than skip them")
        self.assertGreater(len(self.stock), 150, "the parse found only %d stock chords" % len(self.stock))
        # the loops: workspaces, group windows and bar panels by keycode
        for c in (("SUPER",), "CODE:10"), (("SHIFT", "SUPER"), "CODE:19"), (("ALT", "SUPER"), "CODE:14"), (("CTRL", "SUPER"), "CODE:18"):
            self.assertIn(c, self.stock, "the code:NN loop chord %s was not read" % spell(c))

    def test_the_parsers_read_the_chords_they_are_written_to_read(self):
        self.assertEqual((("SHIFT", "SUPER"), "T"), chord("SUPER + SHIFT + t"))
        self.assertEqual((("ALT", "SHIFT", "SUPER"), "B"), chord("SUPER + SHIFT + ALT + B"))
        self.assertIsNone(chord("SUPER + SHIFT"))
        got = [c for c, _ in contrib_chords('-- of SUPER + SHIFT + <letter>, stock Omarchy leaves only\n'
                                            '-- H J and K free. V is free; SUPER + ALT + T is free.\n'
                                            '-- o.bind("SUPER + SHIFT + Z", "x", "y")\n'
                                            'o.bind("SUPER + CTRL + U", "x", "y")\n')]
        self.assertEqual(sorted([(("SHIFT", "SUPER"), "Z"), (("CTRL", "SUPER"), "U"), (("ALT", "SUPER"), "T"),
                                 (("SHIFT", "SUPER"), "V"), (("SHIFT", "SUPER"), "H"), (("SHIFT", "SUPER"), "J"),
                                 (("SHIFT", "SUPER"), "K")]), sorted(got))
        got = [c for c, _ in readme_chords("on `SUPER + SHIFT + H` / `L` / `R`; an earlier copy suggested\n"
                                           "`SUPER + SHIFT + P`, which stock Omarchy already uses for X.")]
        self.assertEqual([(("SHIFT", "SUPER"), "H"), (("SHIFT", "SUPER"), "L"), (("SHIFT", "SUPER"), "R")], got)

    def test_no_chord_the_plugin_documents_is_stock_bound(self):
        """D-DOC-35: a standing tripwire on the stock bindings (see the module
        docstring). Do not skip it."""
        named = contrib_chords(read(os.path.join(ROOT, "contrib", "bindings.lua")))
        named += readme_chords(read(os.path.join(ROOT, "README.md")))
        self.assertGreaterEqual(len(named), 8, "the plugin's chords were not found: %r" % named)
        unreadable = [why for c, why in named if c is None]
        self.assertEqual([], unreadable, "chords in our files that are not one modifier set and one key")
        taken = sorted("%s -- stock %s (%s)" % (why, spell(c), ", ".join(self.stock[c]))
                       for c, why in named if c in self.stock)
        self.assertEqual([], taken, "\n".join([
            "", "A chord the plugin documents is bound by stock Omarchy on this machine (D-DOC-35).",
            "Pick a chord stock leaves free, move it in contrib/bindings.lua and the README,",
            "and tell users who pasted the old line (the CHANGELOG):"] + ["  " + t for t in taken]))


if __name__ == "__main__":
    unittest.main()
