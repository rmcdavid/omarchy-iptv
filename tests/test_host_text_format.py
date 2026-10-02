"""The host renders five kinds of string this plugin hands it, and the plugin
cannot set their textFormat (D-TEXT-1, docs/OMARCHY-PLUGIN-CONTRACT.md
"Verified host renderers"). Those joins are by file name and line, which
rule 13 says nothing verifies unless something calls them. This does: it
reads the host files on this machine and asserts the declarations the
contract records. A red here after an Omarchy update is a re-measurement
request, not a plugin defect.

The host directory comes from OMARCHY_SHELL_DIR so the test can be run
against a copy with one line changed, which is how it was proven red: the
tooltip, the confirm-dialog message and the toast summary each flipped to
AutoText on a copy, one at a time, each a red run. What it does NOT see: a
declaration moved to another line, so the line numbers the contract's
table records are for the reader, not for this test.
"""
import io
import os
import re
import unittest

HOST = os.environ.get("OMARCHY_SHELL_DIR", "/usr/share/omarchy/shell")

# A window of the same element's properties: anything but a closing brace or
# the start of another Text, so a sibling's declaration can never satisfy a
# pin (the first version let ConfirmDialog's button-label line stand in for
# its message line, and flipping the message to AutoText stayed green).
W = r"(?:(?!\}|Text\s*\{)[\s\S]){0,400}?"

# (relative file, regex that must match at least once, what it guards).
# Each pin is anchored on the element the contract names, by its id or by
# the property that binds the plugin's string; a moved line stays green,
# a changed or removed declaration goes red.
PINS = [
    ("Ui/PanelSectionHeader.qml", r"textFormat:\s*Text\.PlainText", "group names, field labels and track titles (the file's one Text)"),
    ("Ui/ConfirmDialog.qml", r"id:\s*messageText" + W + r"textFormat:\s*Text\.PlainText", "the confirm-dialog message"),
    ("Ui/ConfirmDialog.qml", r"textFormat:\s*Text\.PlainText" + W + r"text:\s*modelData", "the confirm-dialog button labels"),
    ("plugins/bar/Bar.qml", r"id:\s*tooltipLabel" + W + r"textFormat:\s*Text\.PlainText", "the bar tooltip"),
    ("plugins/bar/widgets/ActiveWindow.qml", r"textFormat:\s*Text\.PlainText" + W + r"text:\s*root\.title", "mpv's window title, the channel name after a zap"),
    ("plugins/notifications/components/NotificationCard.qml", r"textFormat:\s*Text\.PlainText" + W + r"text:\s*root\.summary", "a failure toast's summary"),
    ("plugins/notifications/components/NotificationCard.qml", r"text:\s*root\.styledBody" + W + r"textFormat:\s*Text\.StyledText", "a failure toast's body (StyledText, behind the stripper below)"),
    ("plugins/notifications/NotificationLogic.js", r"function stripImageTags\(", "the image-tag stripper the toast body sits behind"),
]


def read(rel):
    path = os.path.join(HOST, rel)
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


class HostTextFormatCase(unittest.TestCase):

    def setUp(self):
        if not os.path.isdir(os.path.join(HOST, "Ui")):
            self.skipTest("no Omarchy shell under %s; the host contract cannot be checked here" % HOST)

    def test_every_host_renderer_the_contract_records_still_declares_its_format(self):
        missing = []
        for rel, pattern, what in PINS:
            try:
                text = read(rel)
            except OSError as exc:
                missing.append("%s: %s (%s)" % (rel, exc, what))
                continue
            if re.search(pattern, text) is None:
                missing.append("%s: no match for %r (%s)" % (rel, pattern, what))
        self.assertEqual([], missing, "\n".join([
            "",
            "A host renderer the plugin depends on no longer declares what",
            "docs/OMARCHY-PLUGIN-CONTRACT.md records. Re-measure (D-TEXT-1,",
            "scripts/dev-harness/spikes/text-autotext-img) before updating the row:",
        ] + ["  " + m for m in missing]))


if __name__ == "__main__":
    unittest.main()
