"""The host renders five kinds of string this plugin hands it, and the plugin
cannot set their textFormat (D-TEXT-1, docs/OMARCHY-PLUGIN-CONTRACT.md
"Verified host renderers"). Those joins are by file name and line, which
rule 13 says nothing verifies unless something calls them. This does: it
reads the host files on this machine and asserts the declarations the
contract records, and it RUNS the notification host's own markup grammar in
Qt's engine (tests/host_v4.py) and asserts what it does today. A red here
after an Omarchy update is a re-measurement request, not a plugin defect.

Re-anchored on omarchy 4.5.0-3 (2026-11-06, F-GATE-21). 4.5.0 replaced the
notification engine: the toast is plugins/notifications/Toast.qml, its
summary PlainText from `card.row.summary` and its body StyledText from
`card.row.bodyRich`, which Store.js derives as `Markup.render(body)`. That
renderer DECODES entities (up to three passes) before it escapes, puts back
b/i/u/s/em/strong/br and any `<a href>` Security.js accepts, and linkifies a
bare http(s) URL; a click on a link opens it (Toast.qml onLinkActivated), and
a click on the CARD opens the first safe URL Detect.links finds in the
summary and body (Service.qml activate). The test that used to assert "the
notification host activates no link" was true of 4.0.6 and is false of
4.5.0, so it is replaced by pins of that grammar and of every link opener,
each of which goes red when the host changes it.

The host directory comes from OMARCHY_SHELL_DIR so the test can be run
against a copy with one thing changed, which is how every pin here was
proven red (rule 11): against the 4.0.6 extract, and against mutated copies
of the 4.5.0 files, one mutation at a time (the lane write-up lists them).
What it does NOT see: a declaration moved to another line, so the line
numbers the contract's table records are for the reader, not for this test.
"""
import importlib.util
import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import host_v4  # noqa: E402

HOST = os.environ.get("OMARCHY_SHELL_DIR", "/usr/share/omarchy/shell")
NOTE = os.path.join(HOST, "plugins", "notifications")

# A window of the same element's properties: anything but a closing brace or
# the start of another Text, so a sibling's declaration can never satisfy a
# pin (the first version let ConfirmDialog's button-label line stand in for
# its message line, and flipping the message to AutoText stayed green).
W = r"(?:(?!\}|Text\s*\{)[\s\S]){0,400}?"

TOAST_SUMMARY = r"textFormat:\s*Text\.PlainText\s*\n\s*id:\s*title\b" + W + r"\btext:[^\n]*\bcard\.row\.summary\b"
TOAST_BODY = r"textFormat:\s*Text\.StyledText\s*\n\s*text:[^\n]*\bcard\.row\.bodyRich\b"

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
    ("plugins/notifications/Toast.qml", TOAST_SUMMARY, "a toast's summary (the plugin's literal titles), PlainText"),
    ("plugins/notifications/Toast.qml", TOAST_BODY, "a toast's body, StyledText from the rendered row.bodyRich"),
    ("plugins/notifications/Store.js", r"\bout\.bodyRich\s*=\s*Markup\.render\(out\.body\)", "bodyRich is Markup.render of the body as sent"),
    ("plugins/notifications/Store.js", r"\bout\.bodyLine\s*=\s*Markup\.oneLine\(out\.body\)", "bodyLine is Markup.oneLine of the body as sent"),
    ("plugins/notifications/Service.qml", r"\bbodyMarkupSupported:\s*true\b", "the server advertises body markup"),
    ("plugins/notifications/Service.qml", r"\bbodyHyperlinksSupported:\s*true\b", "the server advertises hyperlinks"),
]


def read(rel):
    path = os.path.join(HOST, rel)
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def text_format_guard():
    spec = importlib.util.spec_from_file_location("check_text_format", os.path.join(ROOT, "scripts", "check-text-format.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def function_body(text, name):
    """The text of `function name(` up to the next top-level `function `."""
    m = re.search(r"^\s*function %s\(" % re.escape(name), text, re.M)
    if m is None:
        return None
    n = re.search(r"^\s*function \w+\(", text[m.end():], re.M)
    return text[m.start():m.end() + (n.start() if n else len(text))]


class HostCase(unittest.TestCase):

    def setUp(self):
        if not os.path.isdir(os.path.join(HOST, "Ui")):
            self.skipTest("no Omarchy shell under %s; the host contract cannot be checked here" % HOST)


class HostTextFormatCase(HostCase):

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
            "D-SINK-49, scripts/dev-harness/spikes/text-autotext-img) before updating the row:",
        ] + ["  " + m for m in missing]))

    def test_the_toast_body_is_the_only_markup_text_in_the_notification_plugin(self):
        """Every Text in plugins/notifications declares a format, and exactly
        one is not PlainText: the toast body that draws bodyRich. Read by
        CALLING the plugin's own text-format guard over the host files, so a
        missing declaration (AutoText) is seen, not only a written one
        (rule 14, F-TEXT-2)."""
        guard = text_format_guard()
        blocks = 0
        problems = []
        # Every directory under the plugin, as the opener census below walks
        # it: 4.0.6 kept its card in components/ (the review of 2026-11-06).
        if not os.path.isdir(NOTE):
            self.fail("the notification plugin is not under %s" % NOTE)
        names = sorted(os.path.relpath(os.path.join(dirpath, n), NOTE)
                       for dirpath, _dirs, files in os.walk(NOTE) for n in files if n.endswith(".qml"))
        for name in names:
            count, found = guard.check_file(os.path.join(NOTE, name))
            blocks += count
            problems.extend((name, line, why) for line, why in found)
        self.assertGreaterEqual(blocks, 9, "the scan found only %d Text blocks in %s" % (blocks, NOTE))
        body = re.search(TOAST_BODY, read("plugins/notifications/Toast.qml"))
        self.assertIsNotNone(body, "the toast body pin no longer matches")
        line = read("plugins/notifications/Toast.qml")[:body.start()].count("\n") + 1
        self.assertEqual([("Toast.qml", line)], [(n, l) for n, l, _w in problems],
                         "the notification plugin's markup-capable Texts changed: %r" % problems)
        self.assertIn("StyledText", problems[0][2])


class HostMarkupSourceCase(HostCase):
    """The grammar and the openers, pinned in the host source. The behaviour
    case below runs the same grammar; these name WHICH declaration moved."""

    def markup(self):
        return read("plugins/notifications/Markup.js")

    def test_the_markup_grammar_is_the_one_the_contract_records(self):
        text = self.markup()
        bad = []
        decode = function_body(text, "decodeEntities") or ""
        m = re.search(r"for \(var i = 0; i < (\d+); i\+\+\)\s*\{\s*var once = decodeOnce\(out\)", decode)
        if m is None or m.group(1) != "3":
            bad.append("decodeEntities no longer runs exactly 3 decodeOnce passes")
        m = re.search(r"^var ENTITIES = \{([^}]*)\}", text, re.M)
        if m is None or sorted(re.findall(r"(\w+)\s*:", m.group(1))) != ["amp", "apos", "gt", "lt", "nbsp", "quot"]:
            bad.append("ENTITIES is no longer amp, lt, gt, quot, apos, nbsp")
        m = re.search(r"^var ALLOWED = \[([^\]]*)\]", text, re.M)
        if m is None or re.findall(r'"(\w+)"', m.group(1)) != ["b", "i", "u", "s", "em", "strong"]:
            bad.append("ALLOWED is no longer b, i, u, s, em, strong")
        restore = function_body(text, "unescapeAllowed") or ""
        if "Security.safeExternalUrl(href)" not in restore or "&lt;br" not in restore:
            bad.append("unescapeAllowed no longer restores br and gates <a href> on Security.safeExternalUrl")
        linkify = function_body(text, "linkify") or ""
        if "/(https?:\\/\\/[^\\s<]+)/g" not in linkify or "Security.safeHttpUrl(decodeEntities(url))" not in linkify:
            bad.append("linkify no longer links a bare http(s) run gated on Security.safeHttpUrl")
        render = function_body(text, "render") or ""
        if re.search(r"decodeEntities\(body\)[\s\S]*unescapeAllowed\(escapeAll\(text\)\)[\s\S]*linkify\(out\)", render) is None:
            bad.append("render is no longer decode, then escape, then restore, then linkify")
        self.assertEqual([], bad, "the 4.5.0 toast markup grammar changed; re-measure D-SINK-49 and the "
                                  "contract's \"Verified host renderers\":\n  " + "\n  ".join(bad))

    def test_every_link_opener_in_the_notification_plugin_is_one_the_contract_records(self):
        """A census, not an absence: each word counted per file. A new opener
        anywhere under plugins/notifications, or one taken away, is red."""
        words = ("onLinkActivated", "linkActivated", "linkAt", "hoveredLink", "onLinkHovered",
                 "openUrlExternally", "openExternalUrl")
        expected = {
            ("Security.js", "openExternalUrl"): 1,     # its definition
            ("Security.js", "openUrlExternally"): 1,   # the one call into Qt
            ("Toast.qml", "onLinkActivated"): 1,       # a click on a link in the body
            ("Toast.qml", "openExternalUrl"): 1,
            ("Service.qml", "openExternalUrl"): 2,     # activate(): the source site, then row.link
        }
        found = {}
        seen = 0
        for dirpath, _dirs, files in os.walk(NOTE):
            for name in sorted(files):
                if not name.endswith((".qml", ".js")):
                    continue
                seen += 1
                with io.open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                rel = os.path.relpath(os.path.join(dirpath, name), NOTE)
                for word in words:
                    n = len(re.findall(r"\b%s\b" % word, text))
                    if n:
                        found[(rel, word)] = n
        self.assertGreaterEqual(seen, 3, "the notifications plugin's files were not found under %s" % NOTE)
        self.assertEqual(expected, found, "the notification host's link openers changed; re-measure D-SINK-49 "
                                          "(docs/OMARCHY-PLUGIN-CONTRACT.md, Verified host renderers)")

    def test_a_link_opens_only_through_security_and_the_card_click_opens_row_link(self):
        bad = []
        toast = read("plugins/notifications/Toast.qml")
        if re.search(TOAST_BODY + W + r"onLinkActivated:\s*function\s*\(url\)\s*\{[^}\n]*Security\.openExternalUrl\(url\)", toast) is None:
            bad.append("Toast.qml: the body's onLinkActivated no longer calls Security.openExternalUrl(url)")
        security = read("plugins/notifications/Security.js")
        if re.search(r"function openExternalUrl\(raw\) \{\s*var safe=safeExternalUrl\(raw\)\s*return safe \? Qt\.openUrlExternally\(safe\) : false", security) is None:
            bad.append("Security.js: openExternalUrl no longer opens only what safeExternalUrl returns")
        if re.search(r"function safeExternalUrl\(raw\) \{ return /\^mailto:/i\.test\(raw\) \? safeMailtoUrl\(raw\) : safeHttpUrl\(raw\) \}", security) is None:
            bad.append("Security.js: safeExternalUrl is no longer mailto-or-http")
        service = read("plugins/notifications/Service.qml")
        activate = function_body(service, "activate") or ""
        if 'else if (String(row.link || "")) Security.openExternalUrl(String(row.link))' not in activate:
            bad.append("Service.qml: activate() no longer opens row.link on a card click")
        if 'Security.openExternalUrl("https://" + Markup.hostname(row.source) + "/")' not in activate:
            bad.append("Service.qml: activate() no longer opens the source's site")
        store = read("plugins/notifications/Store.js")
        if re.search(r"var found = Detect\.scan\(id\.summary, id\.body\)[\s\S]*?\blink: found\.link,", function_body(store, "snapshot") or "") is None:
            bad.append("Store.js: snapshot() no longer takes row.link from Detect.scan(summary, body)")
        detect = read("plugins/notifications/Detect.js")
        if re.search(r"function scan\(summary, body\) \{\s*var text = String\(summary \|\| \"\"\) \+ \"\\n\" \+ String\(body \|\| \"\"\)[\s\S]*?var link = links\(text\)", detect) is None:
            bad.append("Detect.js: scan() no longer reads links from the summary and the body")
        self.assertEqual([], bad, "\n  ".join(["a link path the contract records changed:"] + bad))


@unittest.skipUnless(host_v4.available(), "no Qt qml runtime or prlimit here; the host grammar cannot be run")
class HostMarkupBehaviourCase(HostCase):
    """What the 4.5.0-3 grammar DOES, run in Qt's own engine over the host's
    installed files. Every expected value below was measured on this machine
    on 2026-11-06; a host update that changes one is a re-measurement."""

    BODY = r"""
var R = function (s) { return Markup.render(s) }
var D = function (s) { return Markup.decodeEntities(s) }
var S = function (s) { return Security.safeExternalUrl(s) }
var snap = Store.snapshot({ appName: "IPTV", summary: "Stream failed", body: "News did not play - https://cdn.example/x?y=1", hints: {} }, "k1", { Normal: 1 })
return {
  d2: D("&amp;amp;lt;"), d3: D("&amp;amp;amp;lt;"),
  ent: D("&amp;|&lt;|&gt;|&quot;|&apos;|&nbsp;|&copy;|&AMP;|&#58;|&#x3A;|&#0;|&#x110000;"),
  tags: R("<b>b</b><i>i</i><u>u</u><s>s</s><em>em</em><strong>st</strong><br>x<img src=x><img><script>y</script><font color=red>f</font>"),
  aSafe: R('<a href="https://evil.example/p?q=1">L</a>'),
  aJs: R('<a href="javascript:alert(1)">L</a>'),
  aMail: R('<a href="mailto:a@b.example">m</a>'),
  aEnt: R('&lt;a href="https&amp;#58;//evil.example/renew"&gt;Renew&lt;/a&gt;'),
  lk: R("see https://x.example/a?b=1&c=2 now"),
  lkEnt: R("u http&#58;//h.example/p?x=1 v"),
  lkUser: R("https://user:pw@h.example/"),
  lkIp: R("http://127.0.0.1/x"),
  nl: R("a\nb"),
  one: Markup.oneLine("<b>x</b> &amp;lt;y&amp;gt;"),
  sx: [S("https://Evil.Example:443/x"), S("javascript:alert(1)"), S("file:///etc/passwd"), S("http://127.0.0.1/"),
       S("http://localhost/"), S("https://u:p@h.example/"), S("mailto:a@b.example"), S("mailto:a@b.example?subject=x"),
       S("http://0x7f.0x0.0x0.0x1/"), S("https://h.example/%2e%2e/")],
  host: Markup.hostname("IPTV"),
  links: Detect.links("x https://h.example/a. y https://h.example/a z https://u:p@q.example/"),
  snapLink: snap.link, snapRich: snap.bodyRich, snapSource: snap.source
}
"""

    @classmethod
    def setUpClass(cls):
        cls.got = None
        if not os.path.isdir(os.path.join(HOST, "Ui")):
            return
        try:
            cls.got = host_v4.run({"Markup": os.path.join(NOTE, "Markup.js"), "Security": os.path.join(NOTE, "Security.js"),
                                   "Detect": os.path.join(NOTE, "Detect.js"), "Store": os.path.join(NOTE, "Store.js")}, cls.BODY)
        except AssertionError as exc:
            cls.error = str(exc)

    def g(self, key):
        if self.got is None:
            self.fail("the host grammar could not be run: %s" % getattr(self, "error", "no answer"))
        return self.got[key]

    def test_entities_decode_in_exactly_three_passes(self):
        self.assertEqual("<", self.g("d2"), "three stacked escapes no longer decode to the character")
        self.assertEqual("&lt;", self.g("d3"), "a fourth stacked escape now decodes too")

    def test_the_entities_the_host_decodes(self):
        self.assertEqual("&|<|>|\"|'| |&copy;|&|:|:|&#0;|&#x110000;", self.g("ent"))

    def test_the_tags_the_host_puts_back_and_the_ones_it_leaves_as_text(self):
        self.assertEqual("<b>b</b><i>i</i><u>u</u><s>s</s><i>em</i><strong>st</strong><br/>x&lt;img src=x&gt;&lt;img&gt;"
                         "&lt;script&gt;y&lt;/script&gt;&lt;font color=red&gt;f&lt;/font&gt;", self.g("tags"))
        self.assertEqual("a<br/>b", self.g("nl"))
        self.assertEqual("x <y>", self.g("one"))

    def test_the_anchor_rule(self):
        self.assertEqual('<a href="https://evil.example/p?q=1">L</a>', self.g("aSafe"))
        self.assertEqual("L", self.g("aJs"))
        self.assertEqual('<a href="mailto:a@b.example">m</a>', self.g("aMail"))
        # D-SINK-49 on 4.5.0: an anchor escaped ONCE by its sender, with its
        # scheme colon spelled as an entity, is a live link after decoding.
        self.assertEqual('<a href="https://evil.example/renew">Renew</a>', self.g("aEnt"))

    def test_linkify(self):
        self.assertEqual('see <a href="https://x.example/a?b=1&amp;c=2">https://x.example/a?b=1&amp;c=2</a> now', self.g("lk"))
        self.assertEqual('u <a href="http://h.example/p?x=1">http://h.example/p?x=1</a> v', self.g("lkEnt"))
        self.assertEqual("https://user:pw@h.example/", self.g("lkUser"))
        self.assertEqual("http://127.0.0.1/x", self.g("lkIp"))

    def test_what_security_lets_a_click_open(self):
        self.assertEqual(["https://evil.example:443/x", "", "", "", "", "", "mailto:a@b.example", "", "",
                          "https://h.example/%2e%2e/"], self.g("sx"))

    def test_the_card_click_target_is_the_first_safe_url_in_the_text(self):
        # The plugin posts as app "IPTV": no dotted host, so no source site.
        self.assertEqual("", self.g("host"))
        self.assertEqual(["https://h.example/a"], self.g("links"))
        self.assertEqual("https://cdn.example/x?y=1", self.g("snapLink"))
        self.assertEqual("IPTV", self.g("snapSource"))
        self.assertEqual('News did not play - <a href="https://cdn.example/x?y=1">https://cdn.example/x?y=1</a>', self.g("snapRich"))


if __name__ == "__main__":
    unittest.main()
