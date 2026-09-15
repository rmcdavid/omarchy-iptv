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


class PictureInPictureSettingsTest(unittest.TestCase):
    """M2-05 section 6, and the one cross-lane deadlock this wave had.

    The three PiP keys could not be declared by lane V2 alone.
    tests/Model.test.js asserts the manifest and Model.SETTINGS_DEFAULTS /
    SETTING_RANGES 1:1 in BOTH directions, so a manifest key with no model
    side turned five node checks red, and a model key with no manifest entry
    turned the same checks red on lane V1's branch. Whichever half landed
    first was red on its own, which is ruling PIP16: two files a test
    asserts about each other are one unit, and ownership has to follow the
    coupling. Integration landed both halves and this file's own skip with
    them, so every assertion below now runs.

    What this pins: that the manifest never half-lands the three keys, that
    the values are the designed ones, and that the clamp behind them uses
    exactly those ranges. The clamp is the half a user feels: a range
    declared here and a different one clamped there is a control whose ends
    do nothing.
    """

    PIP_KEYS = ("pipCorner", "pipSizePercent", "pipMargin")

    def test_the_three_keys_land_together_or_not_at_all(self):
        # A half-landed settings block is the state where the host offers a
        # control the plugin cannot read, or reads a value the host never
        # offers. Either way it is worse than neither.
        in_schema = [key for key in self.PIP_KEYS if key in BY_KEY]
        in_defaults = [key for key in self.PIP_KEYS if key in DEFAULTS]
        self.assertEqual(in_schema, in_defaults)
        self.assertIn(len(in_schema), (0, 3), in_schema)

    def test_the_declared_values_are_the_designed_ones(self):
        # PIP4: proportional defaults, top-right. pipCorner has no min/max for
        # the same reason channelOrder has none -- the schema has no enum type,
        # so an unreadable value means "top-right" on the service side.
        corner = BY_KEY["pipCorner"]
        self.assertEqual(corner["type"], "string")
        self.assertNotIn("min", corner)
        self.assertEqual(DEFAULTS["pipCorner"], "top-right")
        self.assertEqual(
            corner["label"],
            "Picture-in-picture corner: top-right, top-left, bottom-right, bottom-left")
        percent = BY_KEY["pipSizePercent"]
        self.assertEqual(percent["type"], "integer")
        self.assertEqual((percent["min"], percent["max"], percent["step"]), (15, 60, 5))
        self.assertEqual(percent["defaultValue"], 30)
        margin = BY_KEY["pipMargin"]
        self.assertEqual(margin["type"], "integer")
        self.assertEqual((margin["min"], margin["max"], margin["step"]), (0, 200, 4))
        self.assertEqual(margin["defaultValue"], 16)

    def test_the_clamp_behind_the_manifest_is_the_manifest(self):
        # The clamp is the half a user feels: a range declared here and a
        # different one clamped there is a control whose ends do nothing.
        # Model.js is where it lives, and tests/Model.test.js asserts
        # SETTING_RANGES against these very entries in both directions --
        # this is the Python side of that same pin, so a range edited here
        # with no model side is red in both suites rather than neither.
        model = (ROOT / "Model.js").read_text(encoding="utf-8")
        self.assertIn("pipSizePercent: { def: %d, min: %d, max: %d }"
                      % (DEFAULTS["pipSizePercent"], BY_KEY["pipSizePercent"]["min"],
                         BY_KEY["pipSizePercent"]["max"]), model)
        self.assertIn("pipMargin: { def: %d, min: %d, max: %d }"
                      % (DEFAULTS["pipMargin"], BY_KEY["pipMargin"]["min"],
                         BY_KEY["pipMargin"]["max"]), model)
        # The corner is a string with no range, so the accepted values are a
        # list rather than a min/max -- and the label the host draws names
        # exactly those four, in that order.
        self.assertIn('var PIP_CORNERS = ["top-right", "top-left", "bottom-right", "bottom-left"]',
                      model)
        self.assertEqual(
            BY_KEY["pipCorner"]["label"].split(": ")[1].split(", "),
            ["top-right", "top-left", "bottom-right", "bottom-left"])

    def test_the_service_reads_the_keys_from_the_one_bar_entry(self):
        # Design section 6: "the guide and the service both read the one
        # entry". Through pipOptions, not through settingsFrom, so the three
        # keys have exactly one clamp rather than two that can drift.
        source = (ROOT / "Service.qml").read_text(encoding="utf-8")
        self.assertIn("Model.pipOptions(root.pipConfig())", source)


if __name__ == "__main__":
    unittest.main()
