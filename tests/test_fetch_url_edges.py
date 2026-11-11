"""D-SRC-76: a fetch verb takes off a URL's edges what the validator does.

`resolve_source` and the `--url` and environment readers called a bare
strip(), Python's whitespace, before validate_source_url saw the text. The
validator takes only the six ASCII whitespace characters and a no-break
space off the ends and REFUSES any other whitespace or control character
that is left (D-SRC-63: refused, never deleted). So with an information
separator, U+0085 or a Unicode space at either end, `playlist --url` read
the source while `state source add` and the guide's form refused the same
text.

Every case goes through the shipping verb or the shipping function; the
sources are local files, so nothing is fetched from anywhere. The members
are built from code points, so this file stays ASCII (CLAUDE.md 8).
"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from helper_loader import load_helper

helper = load_helper()

# What Python's strip() takes and the validator's edge rule does not.
REFUSED_EDGES = [chr(c) for c in (0x1c, 0x1d, 0x1e, 0x1f, 0x85, 0x1680, 0x2000, 0x2005, 0x200a, 0x2028, 0x2029,
                                  0x202f, 0x205f, 0x3000)]
# What both take: the six ASCII whitespace characters and NBSP.
TAKEN_EDGES = ["\t", "\n", "\x0b", "\x0c", "\r", " ", chr(0xa0)]
PLAYLIST = "#EXTM3U\n#EXTINF:-1 tvg-id=\"a.test\",Alpha\nhttp://stream.example.test/live/a.m3u8\n"
HTTP = "http://provider.example.test/get.php?type=m3u"


def run(*args, env=None):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        with mock.patch.dict(os.environ, env or {}):
            code = helper.main(list(args))
    # By the line feed alone, as the shell reads a reply: splitlines() also
    # cuts at U+0085, U+2028 and U+2029, which a reply naming a local file
    # can hold.
    lines = out.getvalue().strip("\n").split("\n")
    return code, (json.loads(lines[-1]) if lines[-1] else None), err.getvalue()


class FetchUrlEdgesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-edges-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.playlist = os.path.join(self.dir, "list.m3u")
        with open(self.playlist, "w", encoding="utf-8") as fh:
            fh.write(PLAYLIST)
        self.count = 0
        os.environ.pop(helper.URL_ENV, None)

    def cache(self):
        self.count += 1
        return os.path.join(self.dir, "cache%d" % self.count)

    def test_the_sets_are_the_two_rules(self):
        for ch in REFUSED_EDGES:
            self.assertEqual(("x" + ch).strip(), "x", hex(ord(ch)))
            self.assertNotIn(ch, helper._URL_EDGE_SPACE)
        self.assertEqual(sorted(TAKEN_EDGES), sorted(helper._URL_EDGE_SPACE))

    def test_resolve_source_answers_as_the_validator_does(self):
        for ch in REFUSED_EDGES + TAKEN_EDGES:
            for text in (HTTP + ch, ch + HTTP, ch + HTTP + ch):
                with self.subTest(ch=hex(ord(ch)), lead=text.startswith(ch), tail=text.endswith(ch)):
                    verdict = helper.validate_source_url(text, "cli")
                    self.assertEqual(verdict["ok"], ch in TAKEN_EDGES)
                    if verdict["ok"]:
                        self.assertEqual(helper.resolve_source(text), ("http", HTTP))
                    else:
                        with self.assertRaises(helper.HelperError) as caught:
                            helper.resolve_source(text)
                        # A control character is `invalid`; a Unicode space
                        # before the scheme leaves no scheme the rule knows.
                        self.assertIn(caught.exception.code, ("bad_url", "unsupported_scheme"))
                        self.assertNotIn("provider", str(caught.exception))

    def test_a_home_path_behind_an_edge_the_validator_takes_is_still_expanded(self):
        with mock.patch.dict(os.environ, {"HOME": self.dir}):
            self.assertEqual(helper.resolve_source(" \t~/list.m3u\n"), ("file", self.playlist))
            for ch in REFUSED_EDGES:
                with self.subTest(ch=hex(ord(ch))):
                    with self.assertRaises(helper.HelperError):
                        helper.resolve_source(ch + "~/list.m3u")

    def test_playlist_url_with_an_edge_the_validator_refuses_reads_nothing(self):
        for ch in REFUSED_EDGES:
            for text in (self.playlist + ch, ch + self.playlist):
                with self.subTest(ch=hex(ord(ch)), lead=text.startswith(ch)):
                    cache = self.cache()
                    code, payload, _ = run("playlist", "--url", text, "--cache-dir", cache)
                    self.assertNotEqual(code, 0)
                    self.assertFalse(payload["ok"])
                    self.assertFalse(os.path.exists(os.path.join(cache, helper.CHANNELS_FILE)))

    def test_the_environment_s_url_is_read_by_the_same_rule(self):
        for ch in REFUSED_EDGES:
            with self.subTest(ch=hex(ord(ch))):
                cache = self.cache()
                code, payload, _ = run("playlist", "--cache-dir", cache, env={helper.URL_ENV: self.playlist + ch})
                self.assertNotEqual(code, 0)
                self.assertFalse(os.path.exists(os.path.join(cache, helper.CHANNELS_FILE)))

    def test_an_edge_the_validator_takes_still_reads_the_playlist(self):
        for ch in TAKEN_EDGES:
            with self.subTest(ch=hex(ord(ch))):
                cache = self.cache()
                code, payload, err = run("playlist", "--url", ch + self.playlist + ch, "--cache-dir", cache)
                self.assertEqual(code, 0, err)
                with open(os.path.join(cache, helper.CHANNELS_FILE), encoding="utf-8") as fh:
                    self.assertEqual(json.load(fh)["count"], 1)
                cache = self.cache()
                code, payload, err = run("playlist", "--cache-dir", cache, env={helper.URL_ENV: ch + self.playlist + ch})
                self.assertEqual(code, 0, err)

    def test_a_url_of_nothing_but_such_edges_is_absent(self):
        # An empty --url is absent and the environment's is read; so is one
        # of nothing but what the validator takes off.
        cache = self.cache()
        code, payload, err = run("playlist", "--url", " \t\n", "--cache-dir", cache, env={helper.URL_ENV: self.playlist})
        self.assertEqual(code, 0, err)
        # And the environment's, when it holds nothing but those, is no URL
        # at all: the verb's own sentence, not a validator's.
        cache = self.cache()
        code, payload, _ = run("playlist", "--cache-dir", cache, env={helper.URL_ENV: " \n" + chr(0xa0)})
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"], {"code": "bad_url", "message": "no playlist URL: pass --url or set $%s"
                                                                          % helper.URL_ENV})
        # One of something the validator refuses is a URL, and refused.
        cache = self.cache()
        code, payload, _ = run("playlist", "--url", chr(0x2028), "--cache-dir", cache, env={helper.URL_ENV: self.playlist})
        self.assertNotEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(cache, helper.CHANNELS_FILE)))

    def test_the_guide_verb_reads_its_url_by_the_same_rule(self):
        guide = os.path.join(self.dir, "guide.xml")
        with open(guide, "w", encoding="utf-8") as fh:
            fh.write('<?xml version="1.0"?><tv><channel id="a.test"><display-name>Alpha</display-name></channel></tv>\n')
        cache = self.cache()
        code, payload, err = run("playlist", "--url", self.playlist, "--cache-dir", cache)
        self.assertEqual(code, 0, err)
        code, taken, err = run("epg", "--url", " " + guide + "\n", "--cache-dir", cache, "--force")
        for ch in REFUSED_EDGES:
            with self.subTest(ch=hex(ord(ch))):
                code, payload, _ = run("epg", "--url", guide + ch, "--cache-dir", cache, "--force")
                self.assertNotEqual((code, json.dumps(payload, sort_keys=True)),
                                    (0, json.dumps(taken, sort_keys=True)))
                self.assertFalse(payload.get("ok") and payload.get("fetched"))


if __name__ == "__main__":
    unittest.main()
