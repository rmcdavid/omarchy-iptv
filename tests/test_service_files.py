"""The service readers (D-REL-14): scripts/service_files.py, and its agreement
with tests/service-files.js.

D-REL-14 splits Service.qml's functions into classic JavaScript code-behinds
reached through one-line forwarders, so every test that read Service.qml's
text now reads it through the readers: the FILES (Service.qml, then each
`import "<file>.js" as <Q>` it declares) or the INLINE view (each forwarder
read as its function's text, which is the one-file Service.qml the split was
cut from). This file holds the Python reader to:

  * this tree, where Service.qml declares nothing: the files are Service.qml
    alone and the view is its text, byte for byte (so no converted reader
    read anything but what it read before);
  * the shared fixture tests/fixtures/service-split/: its view is inline.txt,
    and the round trip closes -- inline.txt cut again by the reader's own
    function spans is the fixture's Service.qml;
  * the shared cases (cases.json), which tests/Model.test.js runs too;
  * the node reader, over this tree and over the fixture, by its CLI.

Rule 11: seen red with a reader that drops the code-behind (service_text
returning Service.qml's own text) and with one that lists no code-behind
(service_files returning Service.qml alone); docs/QA-RESULTS.md, "D-REL-14:
the service readers (lane-relsplit1, 2026-11-22)", has the counts.

Run: python3 -m unittest discover -s tests -p test_service_files.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import service_files  # noqa: E402  the service's files, read from Service.qml (D-REL-14)

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "service-split")
NODE_READER = os.path.join(ROOT, "tests", "service-files.js")
PY_READER = os.path.join(ROOT, "scripts", "service_files.py")


def raw(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


def cases():
    with open(os.path.join(FIXTURE, "cases.json"), encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def node(*args):
    exe = shutil.which("node")
    if not exe:
        # A hard failure, not a skip: the agreement is half of what this file
        # holds, and scripts/check.sh already refuses to run without node.
        raise RuntimeError("node is required to run tests/service-files.js (see scripts/check.sh)")
    return subprocess.run([exe, NODE_READER] + list(args), capture_output=True, timeout=60)


class ThisTree(unittest.TestCase):
    def test_the_files_are_service_qml_alone(self):
        self.assertEqual(service_files.service_files(ROOT), [os.path.join(ROOT, "Service.qml")])
        self.assertEqual(service_files.service_names(ROOT), ["Service.qml"])

    def test_the_view_is_service_qml_byte_for_byte(self):
        self.assertEqual(service_files.service_text(ROOT), raw(os.path.join(ROOT, "Service.qml")))

    def test_a_service_qml_path_reads_the_same_as_its_root(self):
        self.assertEqual(service_files.service_text(os.path.join(ROOT, "Service.qml")), service_files.service_text(ROOT))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.inline = raw(os.path.join(FIXTURE, "inline.txt"))

    def test_the_files_are_service_qml_and_its_code_behind(self):
        self.assertEqual(service_files.service_names(FIXTURE), ["Service.qml", "Service-demo.js"])
        self.assertEqual(service_files.service_files(FIXTURE),
                         [os.path.join(FIXTURE, "Service.qml"), os.path.join(FIXTURE, "Service-demo.js")])

    def test_the_view_is_inline_txt_byte_for_byte(self):
        self.assertEqual(service_files.service_text(FIXTURE), self.inline)
        self.assertEqual(service_files.service_text(os.path.join(FIXTURE, "Service.qml")), self.inline)

    def test_a_pin_on_a_moved_body_reads_it_where_its_forwarder_stands(self):
        view = service_files.service_text(FIXTURE)
        # The pins a converted test makes: a moved function's body and its
        # comment block are there, and no forwarder or declaration is.
        self.assertIn("    if (root.count > 3) tick.stop()\n", view)
        self.assertIn("  // The first moved function. Its comment block moves with it,\n  // both lines of it.\n  function bump(by) {", view)
        self.assertNotIn("ServiceDemo", view)
        # And the one function that stayed is read as it stands.
        self.assertIn("  function stays(x) {\n    return root.str(x) + root.label\n  }", view)

    def test_the_round_trip_closes(self):
        # Cut inline.txt again, by the reader's own spans: each function the
        # code-behind holds is replaced by its forwarder and the declaration
        # goes after the model's import. That is the fixture's Service.qml,
        # byte for byte, and each moved span is the code-behind's own.
        moved = service_files.function_spans(raw(os.path.join(FIXTURE, "Service-demo.js")), "Service-demo.js")
        whole = service_files.function_spans(self.inline, "inline.txt")
        cut = self.inline
        for name, span in moved.items():
            self.assertEqual(whole[name], span, name)
            args = service_files.HEADER.search(span).group(2)
            self.assertEqual(cut.count(span), 1, name)
            cut = cut.replace(span, "  function %s(%s) { return ServiceDemo.%s(%s) }" % (name, args, name, args))
        anchor = 'import "Model.mjs" as Model\n'
        self.assertEqual(cut.count(anchor), 1)
        cut = cut.replace(anchor, anchor + 'import "Service-demo.js" as ServiceDemo\n')
        self.assertEqual(cut, raw(os.path.join(FIXTURE, "Service.qml")))
        self.assertEqual(sorted(moved), ["bump", "last", "pattern", "quoted"])

    def test_a_missing_code_behind_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="omarchy-iptv-service-files-") as tmp:
            shutil.copyfile(os.path.join(FIXTURE, "Service.qml"), os.path.join(tmp, "Service.qml"))
            with self.assertRaises(service_files.ServiceFilesError) as caught:
                service_files.service_text(tmp)
            self.assertEqual(caught.exception.kind, "missing")
            # The file list still names what Service.qml declares: a caller
            # that copies the tree finds the missing file by copying it.
            self.assertEqual(service_files.service_names(tmp), ["Service.qml", "Service-demo.js"])
        with self.assertRaises(service_files.ServiceFilesError) as caught:
            service_files.service_text(os.path.join(FIXTURE, "no-such-dir"))
        self.assertEqual(caught.exception.kind, "missing")

    def test_bytes_that_are_not_utf8_are_refused_not_replaced(self):
        with tempfile.TemporaryDirectory(prefix="omarchy-iptv-service-files-") as tmp:
            with open(os.path.join(tmp, "Service.qml"), "wb") as fh:
                fh.write(b"Item {\n  // \xff\n}\n")
            with self.assertRaises(service_files.ServiceFilesError) as caught:
                service_files.service_text(tmp)
            self.assertEqual(caught.exception.kind, "encoding")
            done = node("text", tmp)
            self.assertEqual((done.returncode, done.stdout), (1, b""), done.stderr)
            self.assertIn(b"encoding", done.stderr)


class SharedCases(unittest.TestCase):
    def test_every_shared_case(self):
        seen = 0
        for case in cases():
            with self.subTest(case=case["name"]):
                seen += 1
                if "refusal" in case["expect"]:
                    with self.assertRaises(service_files.ServiceFilesError) as caught:
                        service_files.inline_text(case["service"], case["files"])
                    self.assertEqual(caught.exception.kind, case["expect"]["refusal"])
                else:
                    self.assertEqual(service_files.inline_text(case["service"], case["files"]), case["expect"]["text"])
                if "declarations" in case:
                    self.assertEqual([[f, q] for f, q, _n in service_files.declarations(case["service"])], case["declarations"])
        self.assertEqual(seen, 22)


class TheTwoReadersAgree(unittest.TestCase):
    """The node reader's CLI against this module, over the same directories:
    the bytes it prints are the bytes this one returns."""

    def test_on_this_tree(self):
        for verb in ("names", "text"):
            with self.subTest(verb=verb):
                done = node(verb, ROOT)
                self.assertEqual(done.returncode, 0, done.stderr)
                mine = service_files.service_text(ROOT) if verb == "text" else "".join(n + "\n" for n in service_files.service_names(ROOT))
                self.assertEqual(done.stdout, mine.encode("utf-8"))

    def test_on_the_fixture(self):
        for verb in ("names", "text"):
            with self.subTest(verb=verb):
                done = node(verb, FIXTURE)
                self.assertEqual(done.returncode, 0, done.stderr)
                mine = service_files.service_text(FIXTURE) if verb == "text" else "".join(n + "\n" for n in service_files.service_names(FIXTURE))
                self.assertEqual(done.stdout, mine.encode("utf-8"))

    def test_on_a_refusal_both_print_nothing_and_exit_one(self):
        with tempfile.TemporaryDirectory(prefix="omarchy-iptv-service-files-") as tmp:
            shutil.copyfile(os.path.join(FIXTURE, "Service.qml"), os.path.join(tmp, "Service.qml"))
            done = node("text", tmp)
            mine = subprocess.run([sys.executable, "-I", PY_READER, "text", tmp], capture_output=True, timeout=60)
            self.assertEqual((done.returncode, done.stdout), (1, b""))
            self.assertEqual((mine.returncode, mine.stdout), (1, b""))
            self.assertIn(b"missing", done.stderr)
            self.assertIn(b"missing", mine.stderr)

    def test_a_usage_error_is_two(self):
        mine = subprocess.run([sys.executable, "-I", PY_READER, "inline", ROOT], capture_output=True, timeout=60)
        self.assertEqual(mine.returncode, 2)
        self.assertEqual(node("inline", ROOT).returncode, 2)


if __name__ == "__main__":
    unittest.main()
