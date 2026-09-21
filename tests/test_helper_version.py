"""D-REL-1: the helper's version is the manifest's, not a constant that drifts.

bin/omarchy-iptv shipped for four releases saying VERSION = "0.2.0" while
manifest.json said 0.7.1, so `--version` and the outbound User-Agent both
lied. Nothing joined the two. This does: the helper now reads the version
from manifest.json beside itself, and this test fails if the two ever differ.
Rule 11: run against the helper as it shipped before the fix, this fails with
'0.2.0' != '0.7.x'.
"""
import json
import pathlib
import unittest

from helper_loader import load_helper

ROOT = pathlib.Path(__file__).resolve().parent.parent


class HelperVersionTest(unittest.TestCase):

    def setUp(self):
        self.helper = load_helper()
        with open(ROOT / "manifest.json", encoding="utf-8") as fh:
            self.manifest = json.load(fh)["version"]

    def test_the_helper_version_is_the_manifest_version(self):
        self.assertEqual(self.helper.VERSION, self.manifest)

    def test_the_user_agent_carries_the_manifest_version(self):
        self.assertEqual(self.helper.USER_AGENT, "omarchy-iptv/" + self.manifest)

    def test_the_version_is_not_the_fallback(self):
        # The fallback exists so a helper copied somewhere without a manifest
        # still starts; it must never be what ships.
        self.assertNotIn("unknown", self.helper.VERSION)


if __name__ == "__main__":
    unittest.main()
