"""D-STATE-7: a JSON document nested deeper than the decoder's stack takes is
damage, not a bug.

CPython's C decoder raises RecursionError (a RuntimeError) once a document
nests past roughly 50,000 levels, and every JSON reader in the helper caught
ValueError only, so a state.json or cache file nested that deep ended its
verb `internal` with the interpreter's own words. Every decode now goes
through json_decode, which raises it as the ValueError those readers
already handle. These call the readers by their jobs: the strict state
reader through two verbs (and the file is not written), the tolerant file
reader and the guide window's reader.

DEPTH is well past where the decoder gives up on an 8 MB stack (measured on
CPython 3.14: 100,000 levels raise). The first test holds that premise, so a
decoder that one day reads such a document makes this file say so instead of
passing for nothing.
"""
import contextlib
import io
import json
import pathlib
import re
import tempfile
import unittest

from helper_loader import load_helper

helper = load_helper()
DEPTH = 200000
DEEP = "[" * DEPTH + "]" * DEPTH
PARTS = pathlib.Path(__file__).resolve().parent.parent / "bin" / "helper"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class DeepJsonTest(unittest.TestCase):
    def test_the_premise_the_decoder_itself_refuses_this_depth(self):
        with self.assertRaises(RecursionError):
            json.loads(DEEP)

    def test_json_decode_raises_it_as_the_error_every_reader_catches(self):
        with self.assertRaises(ValueError):
            helper.json_decode(DEEP)
        with self.assertRaises(ValueError):
            helper.json_decode('{"a":' + DEEP + "}")
        self.assertEqual(helper.json_decode('{"a": [1, "x", null]}'), {"a": [1, "x", None]})
        with self.assertRaises(ValueError):
            helper.json_decode("{")

    def test_a_state_verb_answers_state_unreadable_and_writes_nothing(self):
        text = '{"version":2,"favorites":' + DEEP + "}"
        for verb in (("show",), ("favorite", "add", "t:x")):
            with self.subTest(verb=verb), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "state.json"
                path.write_text(text, encoding="utf-8")
                code, out, err = run("state", "--state-dir", tmp, *verb)
                payload = json.loads(out)
                self.assertEqual((code, payload["error"]["code"]), (1, "state_unreadable"), out[:200])
                self.assertNotIn("Recursion", out + err)
                self.assertNotIn("Traceback", out + err)
                self.assertEqual(path.read_text(encoding="utf-8"), text, "the unreadable state was written over")

    def test_the_tolerant_file_reader_reads_it_as_no_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "channels.json"
            path.write_text('{"channels":' + DEEP + "}", encoding="utf-8")
            self.assertIsNone(helper.read_json(str(path)))

    def test_a_guide_window_with_such_a_head_is_a_window_to_refetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / helper.EPG_WINDOW_FILE
            path.write_text('{"version":1,"warnings":' + DEEP + "}\n", encoding="utf-8")
            self.assertIsNone(helper.load_window(str(path)))

    def test_no_helper_part_decodes_json_any_other_way(self):
        """The join is by convention, so it is held: one json.loads in the
        helper, inside json_decode, and no json.load anywhere."""
        found = []
        for part in sorted(PARTS.glob("*.py")):
            for number, line in enumerate(part.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\bjson\.(loads?\(|JSONDecoder)", line) and not line.lstrip().startswith("#"):
                    found.append("%s:%d %s" % (part.name, number, line.strip()))
        self.assertEqual(len(found), 1, found)
        self.assertIn("return json.loads(text)", found[0])


if __name__ == "__main__":
    unittest.main()
