"""manifest.json is a contract, not documentation.

`omarchy plugin validate` checks the SHAPE of the manifest; nothing checked
its CONTENT until now, so a settings key could be declared in `schema` with
no `defaults` entry (the host then offers a control with no value), or with a
default outside its own min/max (the host stores a value the plugin clamps
away on every read), and every gate would stay green.

M2-03 adds three keys (section 7.1, rulings CN2 and CN3), so the rules the
shipped seven already follow are asserted here for all ten at once.

Run: python3 -m unittest discover -s tests
"""
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
BAR = MANIFEST["barWidget"]
DEFAULTS = BAR["defaults"]
SCHEMA = BAR["schema"]
BY_KEY = {entry["key"]: entry for entry in SCHEMA}

TYPES = {"string": str, "integer": int, "boolean": bool}


class SchemaShapeTest(unittest.TestCase):
    def test_every_schema_key_has_a_default(self):
        for key in BY_KEY:
            self.assertIn(key, DEFAULTS, key)

    def test_every_default_is_declared_in_the_schema(self):
        for key in DEFAULTS:
            self.assertIn(key, BY_KEY, key)

    def test_schema_and_defaults_agree_on_order(self):
        # The host renders the schema in order; a settings pane whose controls
        # are in a different order than the defaults block is how a key gets
        # added to one and forgotten in the other.
        self.assertEqual([e["key"] for e in SCHEMA], list(DEFAULTS.keys()))

    def test_each_default_matches_its_declared_type(self):
        for key, value in DEFAULTS.items():
            want = TYPES[BY_KEY[key]["type"]]
            # bool is a subclass of int: an integer key must not hold True.
            self.assertIs(type(value), want, key)

    def test_each_declared_default_value_matches_the_defaults_block(self):
        for key, entry in BY_KEY.items():
            if "defaultValue" in entry:
                self.assertEqual(entry["defaultValue"], DEFAULTS[key], key)

    def test_every_integer_key_has_a_range_containing_its_default(self):
        for key, entry in BY_KEY.items():
            if entry["type"] != "integer":
                continue
            for field in ("min", "max", "step"):
                self.assertIn(field, entry, "%s.%s" % (key, field))
            self.assertLess(entry["min"], entry["max"], key)
            self.assertLessEqual(entry["min"], DEFAULTS[key], key)
            self.assertLessEqual(DEFAULTS[key], entry["max"], key)


class ChannelNumberSettingsTest(unittest.TestCase):
    """M2-03 section 7.1. The values are quoted in the design, the README and
    the harness, so they are asserted literally rather than derived."""

    def test_channel_order_is_a_string_defaulting_to_playlist(self):
        # CN3, and the upgrade rule: v0.2.0 users must not find their guide
        # silently re-ordered. No min/max: the schema has no enum type, so an
        # unreadable value means "playlist" on the service side, not an error.
        self.assertEqual(DEFAULTS["channelOrder"], "playlist")
        self.assertEqual(BY_KEY["channelOrder"]["type"], "string")
        self.assertNotIn("min", BY_KEY["channelOrder"])
        self.assertEqual(BY_KEY["channelOrder"]["label"],
                         "Channel list order: playlist or number")

    def test_number_entry_timeout_is_an_integer_with_the_ruled_range(self):
        # CN2: the gap between a slow typist getting channel 101 and getting
        # channels 1, 0 and 1 is an accessibility matter, so it is a setting
        # with a range, not a constant.
        entry = BY_KEY["numberEntryMs"]
        self.assertEqual(entry["type"], "integer")
        self.assertEqual((entry["min"], entry["max"], entry["step"]), (400, 5000, 100))
        self.assertEqual(entry["defaultValue"], 2000)
        self.assertEqual(DEFAULTS["numberEntryMs"], 2000)

    def test_bar_channel_number_is_a_boolean_defaulting_to_on(self):
        entry = BY_KEY["barShowChannelNumber"]
        self.assertEqual(entry["type"], "boolean")
        self.assertIs(entry["defaultValue"], True)
        self.assertIs(DEFAULTS["barShowChannelNumber"], True)

    def test_the_shipped_seven_keys_are_untouched(self):
        # Additive by construction: an upgrade that renamed or dropped one of
        # these would take a user's configured playlist with it.
        for key in ("playlistUrl", "epgUrl", "refreshMinutes", "mpvArgs",
                    "showChannelName", "maxRecents", "barLabelMaxWidth"):
            self.assertIn(key, DEFAULTS, key)
            self.assertIn(key, BY_KEY, key)


if __name__ == "__main__":
    unittest.main()
