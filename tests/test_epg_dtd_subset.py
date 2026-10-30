"""D-EPG-15 (2026-10-29): a guide that carries a DTD INTERNAL SUBSET is
refused as `bad_xml` before ElementTree reads a byte of it, whatever the
subset declares.

D-EPG-6 refused entity declarations, and expat expands a second kind: an
ATTLIST default is copied onto every element that omits the attribute, so a
small subset multiplied every element of the guide by its default (a 270 KB
guide reached the verb's memory limit) and could hand a programme an
attribute it never carried. XMLTV feeds carry no internal subset, so the
prolog parser refuses one at the DOCTYPE's start; a DOCTYPE without a subset
(`<!DOCTYPE tv SYSTEM "xmltv.dtd">`) passes as before.

Ordinary small documents only: one short declaration is all a refusal needs,
and the one default that is ever expanded here (the control, against the
code before the fix) is a channel id on one programme.
"""
import calendar
import contextlib
import gzip
import io
import json
import os
import tempfile
import unittest

from helper_loader import load_helper

helper = load_helper()
NOW = calendar.timegm((2026, 9, 12, 21, 0, 0, 0, 0, 0))
CHANNEL = '<channel id="a.tv"><display-name>A</display-name></channel>'
PROGRAMME = ('<programme start="20260912203000 +0000" stop="20260912213000 +0000" channel="a.tv">'
             '<title>News</title></programme>')
BODY = "<tv>" + CHANNEL + PROGRAMME + "<x/><x/></tv>"
XML_DECL = '<?xml version="1.0" encoding="UTF-8"?>'

REFUSED = {
    "attlist default": '<!DOCTYPE tv [<!ATTLIST x pad CDATA "p">]>',
    "element only": "<!DOCTYPE tv [<!ELEMENT x EMPTY>]>",
    "empty subset": "<!DOCTYPE tv []>",
    "system id and a subset": '<!DOCTYPE tv SYSTEM "xmltv.dtd" [<!ATTLIST x pad CDATA "p">]>',
    "after a comment": '<!-- c --><!DOCTYPE tv [<!ATTLIST x pad CDATA "p">]>',
    "after a processing instruction": '<?pi x?><!DOCTYPE tv [<!ATTLIST x pad CDATA "p">]>',
    "notation": '<!DOCTYPE tv [<!NOTATION n SYSTEM "n">]>',
    "an entity (D-EPG-6, now refused one step earlier)": '<!DOCTYPE tv [<!ENTITY e "y">]>',
}
ACCEPTED = {
    "no doctype": "",
    "system id only": '<!DOCTYPE tv SYSTEM "xmltv.dtd">',
    "public and system ids": '<!DOCTYPE tv PUBLIC "-//x//y//EN" "xmltv.dtd">',
    "after a comment and a processing instruction": '<?pi x?>\n<!-- c -->\n<!DOCTYPE tv SYSTEM "xmltv.dtd">\n',
}


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    text = out.getvalue().strip()
    return code, (json.loads(text.splitlines()[-1]) if text else None), err.getvalue()


def document(prolog, body=BODY):
    return (XML_DECL + prolog + body).encode("ascii")


class InternalSubsetTest(unittest.TestCase):
    def parse(self, data):
        return helper.parse_xmltv(helper.open_xml_stream(data), NOW, None)

    def test_every_internal_subset_is_refused_as_bad_xml(self):
        for label, prolog in REFUSED.items():
            for data in (document(prolog), gzip.compress(document(prolog))):
                with self.subTest(label=label, gzip=data[:2] == b"\x1f\x8b"):
                    with self.assertRaises(helper.HelperError) as caught:
                        self.parse(data)
                    self.assertEqual(caught.exception.code, "bad_xml")
                    self.assertEqual(caught.exception.message,
                                     "refused the EPG: it carries a DTD internal subset, which XMLTV feeds never do")

    def test_a_doctype_without_a_subset_parses_as_before(self):
        for label, prolog in ACCEPTED.items():
            with self.subTest(label=label):
                parsed = self.parse(document(prolog))
                self.assertEqual(sorted(parsed["channels"]), ["a.tv"])
                self.assertEqual(parsed["warnings"], [])

    def test_the_refusal_hands_elementtree_nothing(self):
        """The prolog reader raises on its FIRST read, so the parse it feeds
        never receives a byte, let alone an element a default was copied
        onto. Two feeds of the prolog are made available; neither is read
        past the DOCTYPE."""
        for label, prolog in REFUSED.items():
            with self.subTest(label=label):
                stream = io.BytesIO(document(prolog))
                reader = helper.EntityRefusingReader(stream)
                with self.assertRaises(helper.HelperError):
                    reader.read(16384)
                self.assertFalse(reader.cleared, "the reader released the stream to the parse")

    def test_an_attlist_default_no_longer_reaches_a_programme(self):
        """The observable half, through the verb: a programme with NO channel
        attribute took one from `<!ATTLIST programme channel CDATA "a.tv">`
        and was matched to a.tv. Now the guide is refused instead."""
        orphan = ('<programme start="20260912203000 +0000" stop="20260912213000 +0000">'
                  '<title>From the default</title></programme>')
        with tempfile.TemporaryDirectory() as tmp:
            guide = os.path.join(tmp, "guide.xml")
            with open(guide, "wb") as handle:
                handle.write(document('<!DOCTYPE tv [<!ATTLIST programme channel CDATA "a.tv">]>',
                                      "<tv>" + CHANNEL + orphan + "</tv>"))
            code, status, stderr = run("epg", "--url", guide, "--cache-dir", tmp, "--now", str(NOW))
            self.assertEqual(code, 1, stderr)
            self.assertEqual(status["error"]["code"], "bad_xml", status)
            self.assertNotIn(tmp, status["error"]["message"] + stderr)
            self.assertFalse(os.path.exists(os.path.join(tmp, "epg-now.json")))


if __name__ == "__main__":
    unittest.main()
