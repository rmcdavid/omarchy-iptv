"""The Sources QA fixtures, read as the plan serves them (F-HARNESS-79).

scripts/qa-sources-scenarios.sh serves tests/fixtures/qa-sources/ from
http://127.0.0.1:8765 and its steps expect 8, 5 and 3 channels from
qa-src-a, -b and -userinfo. Every channel in them used to sit at
127.0.0.1:9, and since D-SINK-57 a loopback playlist's channels on this
machine are kept only on its own port, so all three parsed to nothing and
the plan's playlist steps could not run. Nothing in the gate read the
fixtures the way the plan does: its own `fixtures` step parses them as local
files, where every channel is kept.

These tests call the shipping parse with the source the plan's URL makes,
and hold the three v1 fixtures to the playlist they stand for: the saved
favorite's first-scheme id is the hash of a URL, so a fixture whose URLs
move without it loses the favorite at the first fetch (measured while
fixing this: the reference stayed `u:502142db` and matched no channel).
Red on the fixtures as they were: 0 channels three times.
"""
import json
import os
import re
import unittest

from helper_loader import load_helper

helper = load_helper()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "qa-sources")
SCRIPT = os.path.join(ROOT, "scripts", "qa-sources-scenarios.sh")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def served(name):
    """The plan's URL for a fixture, read from the scenario script's own
    assignments (A=, B=, C=), so a moved port there moves this too."""
    text = read(SCRIPT)
    for m in re.finditer(r'^[A-Z]+="?(http://[^";\s]+)"?;', text, re.M):
        if m.group(1).endswith("/" + name):
            return m.group(1)
    raise AssertionError("the scenario script assigns no URL ending in /%s" % name)


def parsed(name):
    url = served(name)
    source = helper.playlist_source("http", url, "loopback", "loopback")
    return helper.parse_m3u(read(os.path.join(FIX, name)), source)


class ServedFixtures(unittest.TestCase):

    def test_the_plan_serves_them_from_loopback_on_one_port(self):
        for name in ("qa-src-a.m3u", "qa-src-b.m3u", "qa-src-userinfo.m3u"):
            url = served(name)
            self.assertEqual((helper.url_host(url), helper.url_port(url)), ("127.0.0.1", 8765), name)

    def test_each_fixture_keeps_every_channel_the_plan_counts(self):
        for name, channels, groups in (("qa-src-a.m3u", 8, 3), ("qa-src-b.m3u", 5, 2), ("qa-src-userinfo.m3u", 3, 1)):
            out = parsed(name)
            self.assertEqual((len(out["channels"]), len(set(c["group"] for c in out["channels"]))),
                             (channels, groups), name)
            self.assertEqual(out["warnings"], [], name)

    def test_a_channel_on_another_loopback_port_is_what_emptied_them(self):
        # The rule the fixtures must fit, on one of their own entries.
        text = read(os.path.join(FIX, "qa-src-b.m3u")).replace("127.0.0.1:8765/", "127.0.0.1:9/")
        source = helper.playlist_source("http", served("qa-src-b.m3u"), "loopback", "loopback")
        self.assertEqual(helper.parse_m3u(text, source)["channels"], [])

    def test_the_guide_hint_stays_off_the_playlists_port(self):
        # The plan wants A's hint stored and never fetched: another port.
        hint = parsed("qa-src-a.m3u")["epgUrlHint"]
        self.assertEqual((helper.url_host(hint), helper.url_port(hint)), ("127.0.0.1", 9))


class V1Fixtures(unittest.TestCase):
    """state-v1.json and legacy-cache/ stand for qa-src-a as an old release
    left it: the same channels, under the first id scheme."""

    @classmethod
    def setUpClass(cls):
        cls.now = parsed("qa-src-a.m3u")["channels"]
        cls.legacy = json.loads(read(os.path.join(FIX, "legacy-cache", "channels.json")))["channels"]
        cls.state = json.loads(read(os.path.join(FIX, "state-v1.json")))

    def test_the_legacy_cache_lists_the_playlists_own_channels(self):
        self.assertEqual([(c["name"], c["url"]) for c in self.legacy], [(c["name"], c["url"]) for c in self.now])

    def test_its_ids_are_the_first_schemes(self):
        for c in self.legacy:
            want = "t:" + c["tvgId"] if c.get("tvgId") else "u:" + helper.fnv1a32(c["url"])
            self.assertEqual(c["id"], want, c["name"])

    def test_every_saved_reference_names_a_legacy_channel(self):
        ids = set(c["id"] for c in self.legacy)
        saved = list(self.state["favorites"]) + [r["id"] for r in self.state["recents"]] + [self.state["lastPlayed"]["id"]]
        self.assertEqual([i for i in saved if i not in ids], [])
        self.assertTrue(any(i.startswith("u:") for i in saved), "the fixture's point is one URL-hashed reference")

    def test_the_plan_and_the_fixture_comments_name_that_id_and_no_other(self):
        url_hashed = [i for i in self.state["favorites"] if i.startswith("u:")]
        self.assertEqual(len(url_hashed), 1)
        for path in (SCRIPT, os.path.join(ROOT, "docs", "QA-SOURCES.md")):
            self.assertIn(url_hashed[0], read(path), path)
        legacy_ids = set(c["id"] for c in self.legacy)
        self.assertIn(url_hashed[0], read(os.path.join(FIX, "qa-src-a.m3u")))
        # A `u:` id a fixture's comment cites is one the v1 fixtures hold:
        # qa-src-b's comment named an id no fixture had ever produced.
        for name in ("qa-src-a.m3u", "qa-src-b.m3u"):
            cited = set(re.findall(r"\bu:[0-9a-f]{8}\b", read(os.path.join(FIX, name))))
            self.assertEqual(sorted(cited - legacy_ids), [], name)


if __name__ == "__main__":
    unittest.main()
