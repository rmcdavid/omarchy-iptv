"""D-SINK-19 round 12, R22c: no shipped string tells the user to set
`playlistUrl` or `epgUrl`.

Round 11 (R21) retired both bar settings: after the one migration a URL set
there is refused, reported and removed. The guide's fetch-failure hint still
read `check playlistUrl` (Guide.qml's errorCheck), so a user whose provider
was down was sent to the one route that no longer works; the helper's
`state source update --help` still said the shell's `playlistUrl` / `epgUrl`
setting owned the record. Both were found by reviewers, not by a check.

This is the search R22c asks for, made a check: every string LITERAL in every
shipped code file -- the release allowlist (scripts/release.py), so a file
added to the artifact is searched the day it is added -- that names either
setting AND carries an instruction verb fails. A setting name on its own (a
key, a log line saying a value was ignored) is not an instruction and passes.
Comments are not shipped copy and are skipped; the README and CHANGELOG are
prose about the settings' history and are searched by hand in the lane
report, not here.

Seen red: against lane-key-m2's tree (IPTV_SHIPPED_ROOT=<export>) it names
two -- Guide.qml's `check playlistUrl` and the `--epg-url` help string in
bin/omarchy-iptv ("change the setting"). The `--url` help string beside it
("will overwrite it") carries no instruction verb and is not named; it was
reworded in the same change on its own merits (R22f).
"""
import os
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(os.environ.get("IPTV_SHIPPED_ROOT") or pathlib.Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import release  # noqa: E402

LITERAL = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`')
SETTING = re.compile(r"\b(?:playlistUrl|epgUrl)\b")
# An instruction: a verb a sentence would use to send the user to the
# setting, or the command that sets it.
INSTRUCTION = re.compile(r"\b(?:set|sets|check|configure|enter|edit|change|fix|update|use|try|run|paste|put)\b|bar set", re.I)
CODE = (".qml", ".mjs", ".js", ".json", ".jsonc", ".lua", ".py")
COMMENT = ("//", "#", "*", "/*")


def shipped_code():
    for rel in release.ALLOWLIST:
        if rel.endswith(CODE) or rel == "bin/omarchy-iptv":
            yield rel


def instructions(text):
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(COMMENT):
            continue
        for match in LITERAL.finditer(line):
            literal = match.group(0)
            if SETTING.search(literal) and INSTRUCTION.search(literal):
                out.append((number, literal[:160]))
    return out


class ShippedCopyTest(unittest.TestCase):
    def test_the_search_covers_every_shipped_code_file(self):
        files = list(shipped_code())
        for rel in ("Guide.qml", "Service.qml", "BarWidget.qml", "bin/omarchy-iptv", "Model.mjs", "manifest.json"):
            self.assertIn(rel, files)
        self.assertTrue(any(rel.startswith("model/") for rel in files))
        # D-REL-7: the helper's code is mostly in its parts.
        self.assertTrue(any(rel.startswith("bin/helper/") for rel in files))

    def test_no_shipped_string_tells_the_user_to_set_a_retired_url_setting(self):
        found = []
        for rel in shipped_code():
            path = ROOT / rel
            for number, literal in instructions(path.read_text(encoding="utf-8")):
                found.append("%s:%d: %s" % (rel, number, literal))
        self.assertEqual(found, [])

    def test_the_search_finds_an_instruction_when_there_is_one(self):
        # The check's own red: the string the guide shipped through round 11,
        # and the help text the helper shipped beside it.
        self.assertEqual(len(instructions('    errorCheck: "check playlistUrl",')), 1)
        self.assertEqual(len(instructions("help=\"The running shell's 'epgUrl' setting owns this; change the setting instead\"")), 1)
        self.assertEqual(len(instructions('`omarchy bar set io.github.rmcdavid.iptv playlistUrl "<url>"`')), 1)
        # and a name on its own is not one
        self.assertEqual(instructions('  return "playlistUrl"\n  "omarchy-iptv: ignoring an invalid playlistUrl setting"'), [])
        self.assertEqual(instructions('  // check playlistUrl (a comment, not shipped copy)'), [])


if __name__ == "__main__":
    unittest.main()
