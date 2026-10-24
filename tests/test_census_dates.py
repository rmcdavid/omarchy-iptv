"""F-EPG-24: every census figure in a shipped comment sits in a block that
carries the date it was measured on.

The provider list drifted under the M4-01 audit -- 1,453 rows and 265
pairs frozen, 1,450 and 264 live on 2026-10-06 -- and the frozen inputs are
gone (F-EPG-26), so a number like "the 1,453-row list averages 0.7 tokens
per address" in a shipped comment is a dated measurement no test can grade
and no reader can re-derive. The honest fix is wording: each site says it
is a measurement over a named frozen input, with its date. This is the
call that makes that join (rule 13): a figure outside a dated block is red.

Graded at the comment-BLOCK level, the round's refuter's granularity
(2026-10-24): a figure's block is the run of contiguous comment lines (`#`
or `//`) around it, or, for a figure inside a docstring or a string, the
run of non-blank lines around it; the block must carry a `20xx-xx-xx`
date somewhere. A line-level rule would flag the lines INSIDE the already
dated census paragraph of 01-core.py (its first line carries the date, the
figures follow), and a fix made of dates padded into every line is not
the fix. OPEN lists the blocks known undated at the sites outside the
lane that wrote this (04-epg.py, model/, the QML), each named with the
finding; an entry that no longer matches an undated block is reported, as
the regex guard reports a reviewed pattern that is gone, so the list
cannot keep an excuse for a site that was fixed.
"""
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

ROOT = pathlib.Path(__file__).resolve().parent.parent
# The figures: the frozen list (1,453 rows, 2026-10-03), the live list of
# 2026-10-06 (1,450) and the configured list the logo and browse comments
# were measured on (1,462), each a count over a provider list that drifts.
CENSUS = ("1,453", "1,450", "1,462")
DATE = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}")
COMMENT = re.compile(r"^\s*(#|//)")

# Blocks known undated, outside the files lane H could write on 2026-10-24
# (F-EPG-24): path -> a phrase of the block's first line. Date the block and
# delete the entry together; a stale entry fails below.
OPEN = {
    ("bin/helper/04-epg.py", "of the address the row opens. Worth 185 of the 1,453"),
    ("bin/helper/04-epg.py", "the installed 1,453 channels are covered by a guide under the"),
    ("bin/helper/04-epg.py", "than an argument. On the installed 1,453-channel list this map holds 719"),
    ("bin/helper/04-epg.py", "contributes three. On the owner's 1,453 rows it reports 301 over 70"),
    ("model/logos.mjs", "channel. Measured on the configured list: 82 of 1,462 channels have no"),
    ("model/browse.mjs", "row 0, empty search, in a 1,462-row list."),
    ("Guide.qml", "no usable picture for -- 82 of 1,462 on this list, and"),
    # The three "until M4-01" sites the round's refuter read as historical:
    # they state the pre-M4-01 figure (0 of 1,453) and carry no date
    # either, so the block rule reads them as undated; outside lane H's
    # files, left for the lead to date or to rule historical on the heading.
    ("model/privacy.mjs", "F-SINK-10. Provider-controlled text on its way to a guide-text or"),
    ("model/view.mjs", "M4-02. Gated STRICTLY (`=== true`, not `!== false`) and not the way"),
    ("Guide.qml", "The one argument Model.programmeDetail takes. The lane contract calls it"),
}


def shipped_sources():
    """The shipped sources a comment can live in: the helper's parts, the
    model's parts and aggregator, and the QML."""
    paths = sorted(ROOT.glob("bin/helper/*.py")) + sorted(ROOT.glob("model/*.mjs"))
    paths += [ROOT / "Model.mjs"] + sorted(ROOT.glob("*.qml"))
    return [p for p in paths if p.is_file()]


def census_blocks(text):
    """[(first line number, block text)] for every block carrying a census
    figure. A comment line's block is the run of comment lines around it
    (one marker, `#` or `//`); any other line's block is the run of
    non-blank lines around it."""
    lines = text.splitlines()
    seen = set()
    blocks = []
    for index, line in enumerate(lines):
        if not any(figure in line for figure in CENSUS):
            continue
        marker = COMMENT.match(line)
        if marker:
            same = lambda other: COMMENT.match(other) is not None and COMMENT.match(other).group(1) == marker.group(1)
        else:
            same = lambda other: other.strip() != ""
        start = index
        while start > 0 and same(lines[start - 1]):
            start -= 1
        end = index
        while end + 1 < len(lines) and same(lines[end + 1]):
            end += 1
        if start in seen:
            continue
        seen.add(start)
        blocks.append((start + 1, "\n".join(lines[start:end + 1])))
    return blocks


def undated_blocks(text):
    return [(line, block) for line, block in census_blocks(text) if not DATE.search(block)]


def first_line(block):
    return block.splitlines()[0].strip()


class CensusDateTest(unittest.TestCase):
    def test_every_census_figure_in_a_shipped_comment_sits_in_a_dated_block(self):
        found = set()
        problems = []
        for path in shipped_sources():
            rel = str(path.relative_to(ROOT))
            for line, block in undated_blocks(path.read_text(encoding="utf-8")):
                head = first_line(block)
                entry = next((e for e in OPEN if e[0] == rel and e[1] in block), None)
                if entry is None:
                    problems.append("%s:%d: %s" % (rel, line, head))
                else:
                    found.add(entry)
        self.assertEqual(problems, [], "a census figure in an undated comment block:\n" + "\n".join(problems))
        stale = sorted(OPEN - found)
        self.assertEqual(stale, [], "OPEN names a block that is dated or gone; delete the entry: %r" % stale)

    def test_the_sites_this_round_dated_are_graded_by_the_block_not_the_line(self):
        # 01-core.py's census paragraph (8d40c70) carries its date on its
        # first lines and the figures on later ones; the grader must read
        # it as dated, and the four blocks dated on 2026-10-24 too.
        text = (ROOT / "bin/helper/01-core.py").read_text(encoding="utf-8")
        blocks = census_blocks(text)
        self.assertGreaterEqual(len(blocks), 5, [first_line(b) for _, b in blocks])
        self.assertEqual(undated_blocks(text), [])

    def test_the_grader_goes_red_when_a_block_loses_its_date(self):
        # Rule 11's mutation: strip every date from one dated block and the
        # grader names that block and no other.
        text = (ROOT / "bin/helper/01-core.py").read_text(encoding="utf-8")
        line, block = census_blocks(text)[0]
        stripped = DATE.sub("an undated day", block)
        mutated = text.replace(block, stripped, 1)
        self.assertNotEqual(mutated, text)
        self.assertEqual([l for l, _ in undated_blocks(mutated)], [line])

    def test_a_figure_outside_a_comment_is_graded_by_its_paragraph(self):
        text = 'x = 1\n"""A docstring.\n\nIt names the 1,453 rows\nof a list.\n\nOn 2026-10-03.\n"""\n'
        self.assertEqual([l for l, _ in undated_blocks(text)], [4])
        dated = text.replace("of a list.", "of a list frozen 2026-10-03.")
        self.assertEqual(undated_blocks(dated), [])
        mixed = "// a block\n// over 1,462 rows\n# not the same marker, dated 2026-10-20\n"
        self.assertEqual([l for l, _ in undated_blocks(mixed)], [1])


if __name__ == "__main__":
    unittest.main()
