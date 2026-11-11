"""D-SRC-77: the helper and the shell read a source key alike.

The helper's SOURCE_KEY_RE ended in `$` and is used with `.match`, and in
Python `$` also matches before a final line feed. So the helper kept a
state record keyed `d990c2e4` plus a line feed, took that key for a cache
folder name, and the shell, whose pattern refuses it, dropped the record on
its next save, URL included. tests/fixtures/source-key-shapes.json is the
one list both sides run (Model.isSourceKey in tests/Model.test.js); here
every helper reader of a key is called with it, by the job it does and not
through the pattern.
"""
import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from helper_loader import load_helper

helper = load_helper()
SHAPES = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "source-key-shapes.json").read_text(encoding="utf-8"))
URL = "http://provider.example.test/get.php?username=u&password=p"


class SourceKeyShapeTest(unittest.TestCase):
    def test_the_fixture_holds_the_case_the_defect_was(self):
        self.assertIn("d990c2e4\n", SHAPES["invalid"])
        self.assertTrue(SHAPES["valid"])

    def test_a_key_argument_is_taken_or_refused_as_the_shell_reads_it(self):
        for key in SHAPES["valid"]:
            self.assertEqual(helper.check_source_key(key), key)
        for key in SHAPES["invalid"]:
            with self.subTest(key=key):
                with self.assertRaises(helper.HelperError) as caught:
                    helper.check_source_key(key)
                self.assertEqual(caught.exception.code, "bad_key")

    def test_a_stored_record_is_kept_or_dropped_as_the_shell_reads_its_key(self):
        for key in SHAPES["valid"]:
            got = helper.normalize_source({"key": key, "url": URL})
            self.assertIsNotNone(got, key)
            self.assertEqual(got["key"], key)
        for key in SHAPES["invalid"]:
            with self.subTest(key=key):
                self.assertIsNone(helper.normalize_source({"key": key, "url": URL}))

    def test_a_cache_folder_names_a_source_only_under_a_well_formed_key(self):
        for key in SHAPES["valid"]:
            self.assertEqual(helper.source_key_of("/c/" + helper.SOURCES_DIR + "/" + key), key)
        for key in SHAPES["invalid"]:
            if "/" in key or key == "":
                continue  # not one folder name; os.path reads those its own way
            with self.subTest(key=key):
                self.assertEqual(helper.source_key_of("/c/" + helper.SOURCES_DIR + "/" + key), "")

    def test_a_preferred_key_is_kept_only_when_it_is_well_formed(self):
        for key in SHAPES["valid"]:
            self.assertEqual(helper.allocate_source_key([], URL, key, lambda: 1), key)
        for key in SHAPES["invalid"]:
            with self.subTest(key=key):
                self.assertEqual(helper.allocate_source_key([], URL, key, lambda: 1), "00000001")

    def test_the_cache_verb_refuses_a_key_ending_in_a_line_feed_and_names_no_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = helper.main(["cache", "remove", "--cache-dir", tmp, "--key", "d990c2e4\n"])
            payload = json.loads(out.getvalue())
            self.assertEqual((code, payload["error"]["code"]), (1, "bad_key"))
            self.assertFalse((pathlib.Path(tmp) / helper.SOURCES_DIR / "d990c2e4\n").exists())


if __name__ == "__main__":
    unittest.main()
