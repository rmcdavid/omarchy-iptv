"""D-HOST-12 (2026-11-06): the 4.5.0 notification host reads a provider's
channel name as a verification code, and this pins what it does so a host
change reopens the question.

Since omarchy 4.5.0-3 every card's summary AND body go through
plugins/notifications/Detect.js. A code word (pin, otp, verify, confirm,
2fa, security key, ...) within 24 characters before or 72 after a run of 4
to 8 digits (or a two-part `24 365`, or an uppercase alphanumeric `S01E02`)
makes the card a verification notification: Delivery.quietReason lets it
through Do Not Disturb (unconditionally: the `codesBypassQuiet` key that
migration 1792648436 writes into quiet.json is read by no file of the
shell), it gains a Copy code deed, SUPER+comma (`notifications.act`) runs
that one deed and copies the digits with `wl-copy --sensitive`, and the
stored live and history rows read "Verification notification" /
"[redacted]" with the app name blanked. So the plugin's own Stream failed
card for `PIN 1234 Adult` behaves that way. The lead accepted it with no
plugin change (every plugin-side lever costs fidelity or information);
the contract records it, and this is the tripwire.

The expected values are what Qt's own engine returned on this machine on
2026-11-06, running the installed host files (tests/host_v4.py). The cards
are shaped like the plugin's own (summary "Stream failed", the quoted name
in the body), built as literals here so a change to the plugin's wording
does not move a HOST pin. OMARCHY_SHELL_DIR points the test at a copy, which
is how each pin was proven red (rule 11): the 4.0.6 extract has no
Detect.js, and each mutated 4.5.0 copy in the lane write-up reddens the pin
it names.
"""
import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import host_v4  # noqa: E402

HOST = os.environ.get("OMARCHY_SHELL_DIR", "/usr/share/omarchy/shell")
NOTE = os.path.join(HOST, "plugins", "notifications")
MIGRATIONS = os.environ.get("OMARCHY_MIGRATIONS_DIR", os.path.join(os.path.dirname(HOST), "migrations"))

TRIGGER = {
    # name: the code the host offers for it
    "PIN 1234 Adult": "1234", "Confirm 4567": "4567", "VERIFY TV 7788": "7788", "2FA News 123456": "123456",
    "OTP Live 9090": "9090", "Security Key 4K 2160": "2160", "Code Lyoko 1080": "1080",
    "Code Black S01E02": "S01E02", "Pin Up Kids 24 365": "24365", "One-Time Movies 7070": "7070",
}
# A year, a product name ("Claude Code"), a code word with no digits near it,
# a word that only contains one ("Verified").
CLEAR = ["Sky Sports 1 FHD", "Code 8 HD", "Code Black 2017", "Claude Code 2468", "Channel 4 +1",
         "Verified Sports 5555", "BBC One HD"]

BODY = r"""
var card = function (summary, bodyText) {
  return Store.snapshot({ appName: "IPTV", summary: summary, body: bodyText, hints: {} }, "k1", { Normal: 1 })
}
var names = NAMES
var out = {}
for (var i = 0; i < names.length; i++) {
  var row = card("Stream failed", "\"" + names[i] + "\" did not play - HTTP 403")
  var closed = Store.closedEntry(row, "dismissed", 1000)
  var live = Store.persistable(row)
  out[names[i]] = { code: row.code, codes: row.codes, quietOn: Delivery.quietReason(row, true),
                    quietOff: Delivery.quietReason(row, false), deeds: Delivery.deeds(row, []).map(function (d) { return d.kind + ":" + d.value }),
                    hist: [closed.summary, closed.body, closed.app, closed.rawBody], live: [live.summary, live.body, live.app] }
}
var pad = function (n) { var s = ""; for (var k = 0; k < n; k++) s += "x"; return s }
return {
  words: [Detect.CODE_WORDS.source, Detect.CODE_WORDS.flags], before: Detect.NEAR_BEFORE, after: Detect.NEAR_AFTER,
  shape: Detect.CODE_SHAPE.source, alnum: Detect.CODE_ALNUM.source, maxCodes: Security.MAX_CODES,
  edgeIn: Detect.codes("pin " + pad(66) + " 1234"), edgeOut: Detect.codes("pin " + pad(67) + " 1234"),
  beforeIn: Detect.codes("1234 " + pad(18) + " pin"), beforeOut: Detect.codes("1234 " + pad(19) + " pin"),
  summaryOnly: card("PIN 1234 Adult", "did not play").code,
  redacted: [Store.REDACTED_SUMMARY, Store.REDACTED_BODY],
  cards: out
}
"""


def read(path):
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def function_body(text, name):
    m = re.search(r"^\s*function %s\(" % re.escape(name), text, re.M)
    if m is None:
        return ""
    n = re.search(r"^\s*function \w+\(", text[m.end():], re.M)
    return text[m.start():m.end() + (n.start() if n else len(text))]


class HostCodeCase(unittest.TestCase):

    def setUp(self):
        if not os.path.isdir(os.path.join(HOST, "Ui")):
            self.skipTest("no Omarchy shell under %s; the host contract cannot be checked here" % HOST)


class HostCodeSourceCase(HostCodeCase):

    def test_the_do_not_disturb_bypass_for_a_code_is_unconditional(self):
        """quietReason lets a row with a code through whatever the user set,
        and no shell file reads the codesBypassQuiet key the 4.5.0 migration
        writes. A host that starts reading it makes the bypass a setting, and
        the contract's sentence wrong."""
        delivery = function_body(read(os.path.join(NOTE, "Delivery.js")), "quietReason")
        self.assertRegex(delivery, r'if \(String\(\(row && row\.code\) \|\| ""\)\) return ""',
                         "Delivery.quietReason's code clause changed; re-read D-HOST-12")
        readers = []
        for dirpath, _dirs, files in os.walk(HOST):
            for name in files:
                if name.endswith((".qml", ".js")) and "codesBypassQuiet" in read(os.path.join(dirpath, name)):
                    readers.append(os.path.relpath(os.path.join(dirpath, name), HOST))
        self.assertEqual([], readers, "the shell now reads codesBypassQuiet; the code bypass is a setting now (D-HOST-12)")

    def test_the_migration_writes_the_key_nobody_reads(self):
        path = os.path.join(MIGRATIONS, "1792648436.sh")
        if not os.path.isfile(path):
            self.fail("migration 1792648436.sh is not under %s; re-read D-HOST-12's record of it" % MIGRATIONS)
        self.assertIn('"codesBypassQuiet":true', read(path))

    def test_the_copy_code_deed_and_the_act_shortcut(self):
        service = read(os.path.join(NOTE, "Service.qml"))
        bad = []
        if 'if (deed.kind === "code") copyCode(deed.value, key)' not in function_body(service, "runDeed"):
            bad.append("runDeed no longer copies a code deed")
        if not re.search(r'runClip\(\["wl-copy", "--sensitive", "--", value\]\)', function_body(service, "copySecret")):
            bad.append("copySecret no longer runs wl-copy --sensitive")
        if not re.search(r"else if \(deeds\) runDeed\(key, 0\)", service):
            bad.append("act no longer runs the only deed of a card with no click target")
        self.assertEqual([], bad, "the code deed path changed (D-HOST-12):\n  " + "\n  ".join(bad))

    def test_persistence_redacts_a_row_with_a_code(self):
        store = read(os.path.join(NOTE, "Store.js"))
        body = function_body(store, "sanitiseForPersistence")
        self.assertRegex(body, r"var secret = out\.codes \|\| out\.code \|\| redacted\(out\) \|\| Detect\.codes\(")
        self.assertRegex(body, r"out\.summary = REDACTED_SUMMARY\s*out\.body = REDACTED_BODY")


@unittest.skipUnless(host_v4.available(), "no Qt qml runtime or prlimit here; the host detector cannot be run")
class HostCodeBehaviourCase(HostCodeCase):

    @classmethod
    def setUpClass(cls):
        cls.got = None
        cls.error = "no answer"
        if not os.path.isdir(os.path.join(HOST, "Ui")):
            return
        names = sorted(TRIGGER) + CLEAR
        body = BODY.replace("NAMES", "[" + ", ".join('"%s"' % n for n in names) + "]")
        try:
            cls.got = host_v4.run({"Detect": os.path.join(NOTE, "Detect.js"), "Delivery": os.path.join(NOTE, "Delivery.js"),
                                   "Store": os.path.join(NOTE, "Store.js"), "Security": os.path.join(NOTE, "Security.js")}, body)
        except AssertionError as exc:
            cls.error = str(exc)

    def g(self, key):
        if self.got is None:
            self.fail("the host detector could not be run: %s" % self.error)
        return self.got[key]

    def test_the_code_words_and_shapes(self):
        self.assertEqual([r"\b(code|otp|one[\s-]?time|verification|verify|passcode|pin|2fa|two[\s-]factor|security key|confirm(?:ation)?)\b", "i"],
                         self.g("words"))
        self.assertEqual(r"(?:^|[^\w-])((?:[A-Za-z]-)?\d{2,4}[\s-]\d{2,5}|(?:[A-Za-z]-)?\d{4,8})(?![\w-])", self.g("shape"))
        self.assertEqual(r"(?:^|[^\w-])([A-Z0-9]{5,8})(?![\w-])", self.g("alnum"))
        self.assertEqual(8, self.g("maxCodes"))

    def test_the_window_is_24_before_and_72_after_the_word(self):
        self.assertEqual((24, 72), (self.g("before"), self.g("after")))
        self.assertEqual((["1234"], []), (self.g("edgeIn"), self.g("edgeOut")), "the 72-character window moved")
        self.assertEqual((["1234"], []), (self.g("beforeIn"), self.g("beforeOut")), "the 24-character window moved")

    def test_the_summary_is_scanned_too(self):
        self.assertEqual("1234", self.g("summaryOnly"))

    def test_a_name_with_a_code_word_makes_the_failure_card_a_verification_card(self):
        cards = self.g("cards")
        redacted = self.g("redacted")
        self.assertEqual(["Verification notification", "[redacted]"], redacted)
        bad = []
        for name, code in sorted(TRIGGER.items()):
            got = cards[name]
            # rawBody is "" in both stored forms: persistable() drops a raw
            # body equal to the body, and redaction set it to the body.
            want = {"code": code, "codes": code, "quietOn": "", "quietOff": "", "deeds": ["code:" + code],
                    "hist": [redacted[0], redacted[1], "", ""], "live": [redacted[0], redacted[1], ""]}
            if got != want:
                bad.append("%s: %r" % (name, got))
        self.assertEqual([], bad, "the host's code heuristic changed for names it caught on 2026-11-06")

    def test_the_names_it_leaves_alone(self):
        cards = self.g("cards")
        bad = []
        for name in CLEAR:
            got = cards[name]
            want = {"code": "", "codes": "", "quietOn": "silenced", "quietOff": "", "deeds": [],
                    "hist": ["Stream failed", "\"%s\" did not play - HTTP 403" % name, "IPTV", ""],
                    "live": ["Stream failed", "\"%s\" did not play - HTTP 403" % name, "IPTV"]}
            if got != want:
                bad.append("%s: %r" % (name, got))
        self.assertEqual([], bad, "the host's code heuristic changed for names it left alone on 2026-11-06")


if __name__ == "__main__":
    unittest.main()
