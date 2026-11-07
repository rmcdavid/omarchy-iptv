"""D-SINK-85 (owner, 2026-11-06). tests/Model.test.js and tests/Model.spec.qml
run the plugin's notification bodies through each Omarchy host's OWN code:
byte copies under tests/fixtures/notify-hosts, which the node loader refuses
unless their sha256 is the pin in hosts.json. A copy is evidence only while
it is the host's file, and a pin is a name, so this joins each pin to its
source by reading the source (rule 13):

- every copy is the bytes its pin names;
- the copies of the INSTALLED host are the files under OMARCHY_SHELL_DIR
  (default /usr/share/omarchy/shell), so an Omarchy update that changes how
  a body is read goes red here -- a re-measurement request, not a plugin
  defect: re-copy, re-pin, and see whether the fixture still draws as written;
- every copy is the member of the cached omarchy package it was taken from,
  when the package is still in OMARCHY_PKG_CACHE (default
  /var/cache/pacman/pkg);
- and the premises of the spec's double hold on the installed Toast.qml: the
  body is Store's `bodyRich` drawn as Text.StyledText in Liberation Sans at
  Style.font.title with Text.Wrap, a click on a link goes through
  Security.openExternalUrl, the summary is Text.PlainText, and the card's own
  click opens `row.link` through the same gate. The node harness clicks
  exactly those two ways.

Proven red, both counts in the commit: against the 4.0.6 tree, against a copy
of the 4.5.0 tree with one byte of Markup.js changed, with one byte of a
fixture copy changed, and with each Toast.qml premise flipped on a copy.
"""
import hashlib
import io
import json
import os
import re
import tarfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "notify-hosts")
SHELL = os.environ.get("OMARCHY_SHELL_DIR", "/usr/share/omarchy/shell")
PKG_CACHE = os.environ.get("OMARCHY_PKG_CACHE", "/var/cache/pacman/pkg")
SHELL_PREFIX = "usr/share/omarchy/shell/"


def pins():
    with io.open(os.path.join(FIXTURES, "hosts.json"), encoding="utf-8") as fh:
        return json.load(fh)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


# One block of a QML file, braces balanced, so a sibling's property can never
# stand in for the element's own: the element whose `id:` line `anchor`
# matches (its block opens before the anchor), or the function `anchor` names
# (its block opens after it).
def element(text, anchor, function=False):
    at = re.search(anchor, text)
    if at is None:
        return None
    start = text.find("{", at.end()) if function else text.rfind("{", 0, at.start())
    if start < 0:
        return None
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return None


class NotifyHostCopiesCase(unittest.TestCase):

    def test_every_copy_is_the_bytes_its_pin_names(self):
        wrong = []
        seen = 0
        for host in pins()["hosts"]:
            for f in host["files"]:
                seen += 1
                got = sha256(read_bytes(os.path.join(FIXTURES, f["copy"])))
                if got != f["sha256"]:
                    wrong.append("%s: %s, pinned %s" % (f["copy"], got, f["sha256"]))
        self.assertEqual(5, seen)
        self.assertEqual([], wrong)

    def test_the_fixture_directory_holds_only_the_pinned_copies(self):
        # A copy dropped in beside the pinned ones would be read by nothing
        # that checks it; one the pins name and the directory lacks is caught
        # above by the read.
        named = {f["copy"] for host in pins()["hosts"] for f in host["files"]}
        present = set()
        for root, _dirs, files in os.walk(FIXTURES):
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), FIXTURES).replace(os.sep, "/")
                if rel not in ("hosts.json", "cases.js"):
                    present.add(rel)
        self.assertEqual(sorted(named), sorted(present))


class InstalledNotifyHostCase(unittest.TestCase):

    def setUp(self):
        if not os.path.isdir(os.path.join(SHELL, "plugins", "notifications")):
            self.skipTest("no Omarchy shell under %s; the installed host cannot be checked here" % SHELL)

    def test_the_installed_host_is_the_pinned_one(self):
        changed = []
        for host in pins()["hosts"]:
            if not host["installed"]:
                continue
            for f in host["files"]:
                path = os.path.join(SHELL, f["source"][len(SHELL_PREFIX):])
                try:
                    got = sha256(read_bytes(path))
                except OSError as exc:
                    changed.append("%s: %s" % (path, exc))
                    continue
                if got != f["sha256"]:
                    changed.append("%s: %s, pinned %s (the %s copy)" % (path, got, f["sha256"], host["version"]))
        self.assertEqual([], changed, "\n".join([
            "",
            "The host's notification code is not the code tests/fixtures/notify-hosts copies.",
            "Re-copy the changed files, re-pin them in hosts.json, and run node tests/Model.test.js",
            "and the QML spec: D-SINK-85's fixture must still draw as written on the new host.",
        ] + ["  " + c for c in changed]))

    def read(self, rel):
        try:
            with io.open(os.path.join(SHELL, rel), encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return ""

    def test_the_toast_draws_the_body_as_the_spec_double_does(self):
        toast = self.read("plugins/notifications/Toast.qml")
        body = element(toast, r"id:\s*bodyBox\b")
        title = element(toast, r"id:\s*title\b")
        missing = []
        if body is None:
            missing.append("Toast.qml: no element with id bodyBox")
        else:
            for pattern, what in [
                (r"textFormat:\s*Text\.StyledText\b", "the body is StyledText"),
                (r"text:[^\n]*card\.row\.bodyRich", "the body text is Store's bodyRich"),
                (r'font\.family:\s*"Liberation Sans"', "the body's family"),
                (r"font\.pixelSize:\s*Style\.font\.title\b", "the body's size"),
                (r"wrapMode:\s*Text\.Wrap\b", "the body wraps"),
                (r"onLinkActivated:[^\n]*Security\.openExternalUrl\(url\)", "a link click goes through Security.openExternalUrl"),
            ]:
                if re.search(pattern, body) is None:
                    missing.append("Toast.qml bodyBox: %s (%s)" % (what, pattern))
        if title is None:
            missing.append("Toast.qml: no element with id title")
        else:
            if re.search(r"textFormat:\s*Text\.PlainText\b", title) is None:
                missing.append("Toast.qml title: the summary is not PlainText")
            if re.search(r"text:[^\n]*card\.row\.summary", title) is None:
                missing.append("Toast.qml title: the summary text is not the row's summary")
        service = self.read("plugins/notifications/Service.qml")
        # The card's click (activate) opens a URL in exactly the two ways the
        # node harness clicks: the source's host, and the row's link. An
        # opener added there with another argument goes red.
        activate = element(service, r"function\s+activate\s*\(", function=True)
        opens = re.findall(r"(?:openExternalUrl|openUrlExternally)\((.*)\)\s*$", activate or "", re.M)
        if opens != ['"https://" + Markup.hostname(row.source) + "/"', "String(row.link)"]:
            missing.append("Service.qml activate(): the card's click opens %r, not the source's host and row.link" % (opens,))
        self.assertEqual([], missing, "\n".join(["", "A premise of D-SINK-85's double no longer holds on the installed host:"]
                                                + ["  " + m for m in missing]))


class PackagedNotifyHostCase(unittest.TestCase):

    def test_every_copy_is_the_member_of_the_package_it_came_from(self):
        checked, wrong = 0, []
        for host in pins()["hosts"]:
            pkg = os.path.join(PKG_CACHE, host["package"])
            if not os.path.isfile(pkg):
                continue
            with tarfile.open(pkg, "r:zst") as tar:
                for f in host["files"]:
                    member = tar.extractfile(tar.getmember(f["source"]))
                    got = sha256(member.read())
                    checked += 1
                    if got != f["sha256"]:
                        wrong.append("%s in %s: %s, pinned %s" % (f["source"], host["package"], got, f["sha256"]))
        if checked == 0:
            self.skipTest("neither omarchy package is in %s" % PKG_CACHE)
        self.assertEqual([], wrong)


if __name__ == "__main__":
    unittest.main()
