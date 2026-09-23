"""Channel id scheme 2 and the one-time remap (ARCHITECTURE.md decision 6).

Scheme 1 keyed every row without a unique tvg-id by a hash of its STREAM URL,
and an Xtream stream URL carries the account password. Measured on the user's
own 3,335-channel list, exactly 1 id of 3,335 survived a password rotation, so
every favorite, recent, lastPlayed and session record silently stopped naming
anything. Scheme 2 tries the channel NAME in between, and only when that name
is unique in the playlist.

tests/fixtures/channel-ids.json is the shared fixture: tests/Model.test.js runs
the same vectors against Model.js, so the two implementations are pinned to one
file rather than to each other.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import helper_loader
from helper_loader import load_helper

helper = load_helper()
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = helper_loader.HELPER


def load_fixture():
    with open(FIXTURES / "channel-ids.json", encoding="utf-8") as handle:
        return json.load(handle)


def rotated(channels, rule):
    """The same channels after the provider changed the account password."""
    out = []
    for channel in channels:
        copy = dict(channel)
        copy["url"] = copy["url"].replace(rule["from"], rule["to"])
        out.append(copy)
    return out


def state_from(fields):
    state = helper.default_state()
    for key in ("favorites", "recents", "lastPlayed", "session"):
        if key in fields:
            state[key] = json.loads(json.dumps(fields[key]))
    return state


class ChannelIdFixtureTest(unittest.TestCase):
    """The shared fixture, run against the shipping helper."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = load_fixture()

    def test_fixture_is_not_empty(self):
        # A fixture that fails to load would make every case below vacuous.
        self.assertGreaterEqual(len(self.fixture["vectors"]), 9)
        self.assertGreaterEqual(len(self.fixture["states"]), 5)
        self.assertGreaterEqual(len(self.fixture["folds"]), 14)

    def test_the_two_folds(self):
        """Search folds punctuation away; the id fold keeps + and *.

        One table, both readers (tests/Model.test.js runs the same rows), so
        neither implementation can change one job believing it changed the
        other. The first version of this change keyed ids with the SEARCH
        fold, which merged "USA  AMC" with "USA: AMC+" and "US: ESPN" with
        "US: ESPN*" -- two live streams under one id, which is worse than an
        id that stops resolving, because it resolves to the wrong channel.
        """
        for row in self.fixture["folds"]:
            with self.subTest(row["name"]):
                self.assertEqual(helper.normalize_id_text(row["name"]), row["id"])
                self.assertEqual(helper.normalize_text(row["name"]), row["search"])

    def test_scheme1_ids(self):
        for vector in self.fixture["vectors"]:
            with self.subTest(vector["name"]):
                self.assertEqual(helper.channel_ids(vector["channels"], helper.CHANNEL_ID_SCHEME_LEGACY), vector["scheme1"])

    def test_scheme2_ids(self):
        for vector in self.fixture["vectors"]:
            with self.subTest(vector["name"]):
                self.assertEqual(helper.channel_ids(vector["channels"]), vector["scheme2"])

    def test_no_key_is_also_a_new_id(self):
        """The invariant the whole upgrade rests on.

        If a scheme-1 id that the remap moves is ALSO some row's scheme-2 id,
        then a saved favorite silently starts naming a different channel and
        the remap stops being idempotent. It holds because scheme 2 is a
        substitution: an id either stays exactly as it was or becomes an `n:`
        id that never existed. Checked, not asserted in prose.
        """
        for vector in self.fixture["vectors"]:
            with self.subTest(vector["name"]):
                fresh = set(helper.channel_ids(vector["channels"]))
                for key in helper.channel_id_remap(vector["channels"]):
                    self.assertNotIn(key, fresh)

    def test_assign_ids_writes_scheme2(self):
        for vector in self.fixture["vectors"]:
            with self.subTest(vector["name"]):
                channels = [dict(channel) for channel in vector["channels"]]
                helper.assign_ids(channels)
                self.assertEqual([channel["id"] for channel in channels], vector["scheme2"])

    def test_remap(self):
        for vector in self.fixture["vectors"]:
            with self.subTest(vector["name"]):
                self.assertEqual(helper.channel_id_remap(vector["channels"]), vector["remap"])

    def test_survival_of_a_password_rotation(self):
        rule = self.fixture["rotate"]
        for vector in self.fixture["vectors"]:
            with self.subTest(vector["name"]):
                after = rotated(vector["channels"], rule)
                for scheme, expected in ((helper.CHANNEL_ID_SCHEME_LEGACY, vector["survivesScheme1"]),
                                         (helper.CHANNEL_ID_SCHEME, vector["survivesScheme2"])):
                    before_ids = helper.channel_ids(vector["channels"], scheme)
                    after_ids = helper.channel_ids(after, scheme)
                    survived = sum(1 for a, b in zip(before_ids, after_ids) if a == b)
                    self.assertEqual(survived, expected, "scheme %d" % scheme)

    def test_state_remap(self):
        for case in self.fixture["states"]:
            with self.subTest(case["name"]):
                vector = self.fixture["vectors"][case["vector"]]
                state = state_from(case["before"])
                moved = helper.remap_state_ids(state, helper.channel_id_remap(vector["channels"]))
                self.assertEqual(moved, case["moved"])
                for key, expected in case["after"].items():
                    self.assertEqual(state[key], expected, key)

    def test_state_remap_is_idempotent_on_every_case(self):
        # Not only on the case written to be already-current: applying the map
        # twice to ANY of them must leave the second pass with nothing to do.
        for case in self.fixture["states"]:
            with self.subTest(case["name"]):
                vector = self.fixture["vectors"][case["vector"]]
                remap = helper.channel_id_remap(vector["channels"])
                state = state_from(case["before"])
                helper.remap_state_ids(state, remap)
                once = json.dumps(state, sort_keys=True)
                self.assertEqual(helper.remap_state_ids(state, remap), 0)
                self.assertEqual(json.dumps(state, sort_keys=True), once)


class ChannelIdRuleTest(unittest.TestCase):
    """The decisions the rule makes, stated one at a time."""

    def test_name_key_folds_case_and_punctuation(self):
        self.assertEqual(helper.name_id_key("US: ESPN"), helper.name_id_key("us espn"))
        # Rule 8: the accented spelling is written as escapes, not as bytes.
        self.assertEqual(helper.name_id_key("Tele-Quebec"), helper.name_id_key("T\u00e9l\u00e9 Qu\u00e9bec"))

    def test_amc_plus_is_not_amc_and_espn_star_is_not_espn(self):
        """The pairs, keyed for real, from the user's own lists.

        Both pairs exist in SportsPPVAll.m3u and USChannels.m3u. Dropping
        `+` and `*` gave them one key each, and because each key was then
        shared by two rows the uniqueness test refused both -- so the visible
        symptom was not a merge but a silent loss of the fix on those rows.
        Change either of them to the shared fold and this goes red.
        """
        pairs = [("USA  AMC", "USA: AMC+"), ("US: ESPN", "US: ESPN*"), ("US NESN (A)", "US NESN+ (A)")]
        for left, right in pairs:
            with self.subTest("%s / %s" % (left, right)):
                self.assertNotEqual(helper.name_id_key(left), helper.name_id_key(right))
                # and SEARCH still folds them together, which is what search wants
                self.assertEqual(helper.search_key(left, ""), helper.search_key(right, ""))
        channels = [{"name": name, "url": "http://h.test/%d" % index}
                    for index, name in enumerate(sum(([a, b] for a, b in pairs), []))]
        helper.assign_ids(channels)
        ids = [channel["id"] for channel in channels]
        self.assertEqual(len(set(ids)), 6)
        self.assertTrue(all(value.startswith("n:") for value in ids), ids)

    def test_the_id_fold_keeps_nothing_else(self):
        # The class is narrow on purpose: `&`, `#` and `@` were measured over
        # the same four playlists and disambiguate nothing, so they stay
        # folded. A wider class would key more ids on characters a provider
        # re-spells.
        for char in "&#@!?()[]{}<>,.;:'\"/\\|~`^%$-_=":
            with self.subTest(char):
                self.assertEqual(helper.normalize_id_text("A" + char + "B"), "a b")
        self.assertEqual(helper.normalize_id_text("A+B"), "a+b")
        self.assertEqual(helper.normalize_id_text("A*B"), "a*b")

    def test_name_key_refuses_a_generated_name(self):
        self.assertEqual(helper.name_id_key("Channel 11"), "")
        self.assertEqual(helper.name_id_key(helper.GENERATED_NAME_FORMAT % 4), "")
        self.assertEqual(helper.name_id_key(""), "")
        self.assertEqual(helper.name_id_key("   "), "")
        # A name that only LOOKS generated still keys: the pattern is anchored.
        self.assertNotEqual(helper.name_id_key("Channel 4 News"), "")
        self.assertNotEqual(helper.name_id_key("Discovery Channel 4"), "")

    def test_the_generated_name_and_its_pattern_cannot_drift(self):
        # CLAUDE.md rule 13: the parser's fallback and the rule that refuses to
        # key on it are joined by a call, not by a copied string.
        result = helper.parse_m3u("#EXTM3U\n#EXTINF:-1,\nhttp://line.example.test/u5er/p4ssw0rd/1\n")
        generated = result["channels"][0]["name"]
        self.assertEqual(generated, helper.GENERATED_NAME_FORMAT % 1)
        self.assertEqual(helper.name_id_key(generated), "")
        self.assertTrue(result["channels"][0]["id"].startswith("u:"))

    def test_a_shared_name_never_merges_two_channels(self):
        channels = [
            {"name": "US: ESPN", "url": "http://line.example.test/u5er/p4ssw0rd/1"},
            {"name": "US: ESPN", "url": "http://line.example.test/u5er/p4ssw0rd/2"},
        ]
        helper.assign_ids(channels)
        self.assertNotEqual(channels[0]["id"], channels[1]["id"])
        self.assertTrue(all(channel["id"].startswith("u:") for channel in channels))

    HOSTILE = [
        {"name": "A", "url": "http://h.test/1"},
        {"name": "A", "url": "http://h.test/2"},
        {"name": "B", "url": "http://h.test/3"},
        {"name": "B", "url": "http://h.test/3"},
        {"name": "Channel 1", "url": "http://h.test/4"},
        {"name": "", "url": "http://h.test/4"},
        {"name": "C", "tvgId": "dup", "url": "http://h.test/5"},
        {"name": "D", "tvgId": "dup", "url": "http://h.test/6"},
        {"name": "E", "tvgId": "solo", "url": "http://h.test/7"},
        {"name": "F", "url": "http://h.test/7"},
        {"name": "G", "url": "http://h.test/8"},
        {"name": "G", "tvgId": "also.solo", "url": "http://h.test/9"},
    ]

    def test_a_shared_url_and_a_shared_name_still_suffix(self):
        # The `#n` path. tests/fixtures/attributes.m3u and qa-attrs.m3u used to
        # exercise it with their duplicate-URL pairs; under scheme 2 those rows
        # have names of their own and are keyed by them, so the case needs a
        # home of its own rather than quietly ceasing to be covered.
        channels = [
            {"name": "Twice", "url": "http://h.test/same"},
            {"name": "Twice", "url": "http://h.test/same"},
        ]
        helper.assign_ids(channels)
        self.assertEqual(channels[0]["id"], "u:" + helper.fnv1a32("http://h.test/same"))
        self.assertEqual(channels[1]["id"], channels[0]["id"] + "#2")

    def test_ids_are_unique_across_a_hostile_list(self):
        channels = [dict(channel) for channel in self.HOSTILE]
        helper.assign_ids(channels)
        ids = [channel["id"] for channel in channels]
        self.assertEqual(len(set(ids)), len(ids))

    def test_scheme2_only_ever_substitutes_a_brand_new_n_id(self):
        # The substitution property, on a list built to break it. An id either
        # stays byte-identical or becomes an `n:` id that never existed under
        # scheme 1 -- which is what makes the remap safe and idempotent.
        old = helper.channel_ids(self.HOSTILE, helper.CHANNEL_ID_SCHEME_LEGACY)
        new = helper.channel_ids(self.HOSTILE, helper.CHANNEL_ID_SCHEME)
        for before, after in zip(old, new):
            self.assertTrue(after == before or after.startswith("n:"), "%s -> %s" % (before, after))
        fresh = set(new)
        for key in helper.channel_id_remap(self.HOSTILE):
            self.assertNotIn(key, fresh)

    def test_the_remap_is_idempotent_on_a_hostile_list(self):
        remap = helper.channel_id_remap(self.HOSTILE)
        state = helper.default_state()
        state["favorites"] = helper.channel_ids(self.HOSTILE, helper.CHANNEL_ID_SCHEME_LEGACY)
        self.assertGreater(helper.remap_state_ids(state, remap), 0)
        once = list(state["favorites"])
        self.assertEqual(helper.remap_state_ids(state, remap), 0)
        self.assertEqual(state["favorites"], once)
        # And every reference now names the row it named before.
        self.assertEqual(once, helper.channel_ids(self.HOSTILE, helper.CHANNEL_ID_SCHEME))

    def test_names_are_counted_over_every_channel_including_tvg_rows(self):
        # The ruling: the name pool depends on nothing but names. The row with
        # the unique tvg-id still consumes the name, so the other row cannot
        # use it and keeps a URL id.
        channels = [
            {"name": "US: ESPN", "tvgId": "espn.us", "url": "http://h.test/1"},
            {"name": "US: ESPN", "url": "http://h.test/2"},
        ]
        helper.assign_ids(channels)
        self.assertEqual(channels[0]["id"], "t:espn.us")
        self.assertTrue(channels[1]["id"].startswith("u:"))

    def test_the_deferred_collision_is_real_and_is_demonstrated_here(self):
        """The accepted limit of D-ID-1, executed rather than written down.

        The uniqueness test is answered from ONE snapshot; uniqueness is a
        property across snapshots. Refusing a colliding pair today defers the
        collision, it does not settle it. This is what the deferral looks like
        when the provider later drops one member: the survivor becomes unique,
        takes the key the pair was refused, and a reference saved against the
        row that WENT AWAY now resolves to the row that stayed -- a silent
        wrong channel, not a silent loss.

        Nothing fixes this without a second snapshot, so this case is not a
        regression guard. It exists so that the limit is observable, and so
        that whoever does fix it has the failing shape already written down in
        code. See the ACCEPTED LIMIT note in channel_ids.
        """
        twins = [
            {"name": "US: ESPN", "url": "http://h.test/hd"},
            {"name": "US: ESPN", "url": "http://h.test/sd"},
        ]
        before = helper.channel_ids(twins)
        self.assertTrue(all(value.startswith("u:") for value in before), before)
        survivor = helper.channel_ids([twins[1]])
        self.assertEqual(survivor, [helper.name_id_key("US: ESPN")])
        # The favorite the user saved was the HD row, which has now gone.
        state = helper.default_state()
        state["favorites"] = [before[0]]
        helper.remap_state_ids(state, helper.channel_id_remap([twins[1]]))
        # It did not move -- the remap of the shorter list does not know it.
        self.assertEqual(state["favorites"], [before[0]])
        # But the SD row now answers to the name key, so any reference saved
        # under that key after the change means the SD row, whichever row the
        # user had in mind. This is the deferral, in one assertion.
        self.assertNotIn(survivor[0], before)
        self.assertEqual(helper.name_id_key(twins[0]["name"]), survivor[0])

    def test_remap_of_an_unchanged_list_is_empty(self):
        channels = [{"name": "A", "tvgId": "a.test", "url": "http://h.test/1"}]
        self.assertEqual(helper.channel_id_remap(channels), {})
        self.assertEqual(helper.remap_state_ids(helper.default_state(), {}), 0)


class RemapStateFileTest(unittest.TestCase):
    """The helper's own call site: a playlist fetch moves the saved references."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-ids-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, "state.json")
        self.channels = [
            {"name": "US: ESPN", "url": "http://line.example.test/u5er/p4ssw0rd/102"},
            {"name": "Alpha", "url": "http://line.example.test/u5er/p4ssw0rd/104"},
        ]

    def write(self, payload):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def read(self):
        with open(self.path, encoding="utf-8") as handle:
            return json.load(handle)

    def test_missing_state_file_is_not_created(self):
        self.assertEqual(helper.remap_state_file(self.path, self.channels), 0)
        self.assertFalse(os.path.exists(self.path))

    def test_a_state_file_that_is_not_an_object_is_left_alone(self):
        self.write([1, 2, 3])
        self.assertEqual(helper.remap_state_file(self.path, self.channels), 0)
        self.assertEqual(self.read(), [1, 2, 3])

    def test_moves_the_references_and_writes_once(self):
        self.write({"version": 2, "favorites": ["u:54f81d29"], "recents": [], "lastPlayed": None, "session": None, "sources": []})
        self.assertEqual(helper.remap_state_file(self.path, self.channels), 1)
        self.assertEqual(self.read()["favorites"], ["n:bc9e3e3d"])
        before = os.stat(self.path).st_mtime_ns
        # The second call must not rewrite the file at all.
        self.assertEqual(helper.remap_state_file(self.path, self.channels), 0)
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)

    def test_a_state_with_nothing_to_move_is_not_rewritten(self):
        self.write({"version": 2, "favorites": ["t:elsewhere"], "recents": [], "lastPlayed": None, "session": None, "sources": []})
        before = os.stat(self.path).st_mtime_ns
        self.assertEqual(helper.remap_state_file(self.path, self.channels), 0)
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)

    def test_keys_this_helper_does_not_know_survive_the_write(self):
        """The rewrite edits the document; it does not rebuild it.

        An earlier version passed the file through normalize_state, which is
        a whitelist, so a key written by any other version of the plugin --
        newer or older -- was dropped on a write the user never asked for.
        Moving four fields is the whole remit.
        """
        self.write({
            "version": 2,
            "favorites": ["u:54f81d29"],
            "recents": [],
            "lastPlayed": None,
            "session": None,
            "sources": [],
            "aFieldFromAFutureVersion": {"keep": [1, 2, 3]},
            "cacheLayout": 2,
        })
        self.assertEqual(helper.remap_state_file(self.path, self.channels), 1)
        after = self.read()
        self.assertEqual(after["favorites"], ["n:bc9e3e3d"])
        self.assertEqual(after["aFieldFromAFutureVersion"], {"keep": [1, 2, 3]})
        self.assertEqual(after["cacheLayout"], 2)

    def test_a_field_of_an_unexpected_shape_is_left_alone(self):
        # Tolerance, not coercion: the reader normalizes on load, and a write
        # triggered by an id scheme change must not double as a repair pass.
        self.write({"version": 2, "favorites": "not a list", "recents": {"not": "a list"},
                    "lastPlayed": ["not", "a", "record"], "session": None, "sources": []})
        self.assertEqual(helper.remap_state_file(self.path, self.channels), 0)
        after = self.read()
        self.assertEqual(after["favorites"], "not a list")
        self.assertEqual(after["recents"], {"not": "a list"})
        self.assertEqual(after["lastPlayed"], ["not", "a", "record"])


class PlaylistCommandRemapTest(unittest.TestCase):
    """`playlist` is the only thing that runs the remap. Asserted here.

    Nothing asserted this before: the remap call could be deleted from
    cmd_playlist outright and the whole suite -- 407 python cases, 1,399 node
    checks -- stayed green, because every case drove remap_state_file or
    remap_state_ids directly. CLAUDE.md rule 11.

    The same two cases pin the other half: without `--state-dir` the command
    reads and writes no state file at all. That is what makes omission safe,
    and it is why roughly fourteen existing tests that call `playlist` with no
    state flag can no longer reach the user's own state.json.
    """

    PLAYLIST = str(FIXTURES / "basic.m3u")
    # basic.m3u row 3 is the one with no tvg-id. Literals, not a call into the
    # code under test: the point is that the shipping command produces these.
    LEGACY_ID = "u:9d5090b0"
    SCHEME2_ID = "n:858057a4"

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-playlist-remap-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.cache = os.path.join(self.dir, "cache")
        self.state = os.path.join(self.dir, "state")
        # Where `state_dir(None)` resolves for these child processes. Every
        # case asserts against BOTH: the directory the run names, and the one
        # it would fall back to. Checking only the named one lets the whole
        # defect back in -- a fallback that quietly moves someone else's file
        # leaves the named file untouched too.
        self.default_state_home = os.path.join(self.dir, "xdg-state")
        self.default_state = os.path.join(self.default_state_home, "omarchy-iptv")
        for directory in (self.cache, self.state, self.default_state):
            os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(self.state, helper.STATE_FILE)
        self.default_path = os.path.join(self.default_state, helper.STATE_FILE)

    def write_state(self, path, payload):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def read_state(self, path):
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def seeded(self):
        return {"version": 2, "favorites": [self.LEGACY_ID], "recents": [],
                "lastPlayed": None, "session": None, "sources": []}

    def playlist(self, *extra):
        env = dict(os.environ)
        env["XDG_STATE_HOME"] = self.default_state_home
        completed = subprocess.run(
            [sys.executable, str(HELPER), "playlist", "--url", self.PLAYLIST, "--cache-dir", self.cache, *extra],
            capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def test_a_playlist_run_with_a_state_dir_moves_the_saved_references(self):
        # The executing path. Delete the remap call from cmd_playlist and this
        # is the case that notices.
        self.write_state(self.path, self.seeded())
        self.write_state(self.default_path, self.seeded())
        completed = self.playlist("--state-dir", self.state)
        self.assertEqual(self.read_state(self.path)["favorites"], [self.SCHEME2_ID])
        self.assertIn("moved 1 saved channel reference", completed.stderr)
        # and only the directory it was told about
        self.assertEqual(self.read_state(self.default_path)["favorites"], [self.LEGACY_ID])

    def test_a_second_run_moves_nothing_and_does_not_rewrite_the_file(self):
        self.write_state(self.path, self.seeded())
        self.playlist("--state-dir", self.state)
        before = os.stat(self.path).st_mtime_ns
        completed = self.playlist("--state-dir", self.state)
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)
        self.assertNotIn("saved channel reference", completed.stderr)

    def test_without_a_state_dir_the_state_file_is_not_even_read(self):
        self.write_state(self.path, self.seeded())
        before = os.stat(self.path).st_mtime_ns
        self.playlist()
        self.assertEqual(os.stat(self.path).st_mtime_ns, before)
        self.assertEqual(self.read_state(self.path)["favorites"], [self.LEGACY_ID])

    def test_without_a_state_dir_the_DEFAULT_state_file_is_not_touched_either(self):
        """The defect in one line.

        `playlist --url ... --cache-dir /tmp/scratch` resolved the default
        state directory and rewrote whatever it found there. That is how one
        `unittest discover` reached the user's own state.json 124 times, and
        how an ad-hoc run from a shell did the same. Silence must mean touch
        nothing, so this asserts against the fallback location, which is the
        only place the old code went.
        """
        self.write_state(self.default_path, self.seeded())
        before = os.stat(self.default_path).st_mtime_ns
        self.playlist()
        self.assertEqual(os.stat(self.default_path).st_mtime_ns, before)
        self.assertEqual(self.read_state(self.default_path)["favorites"], [self.LEGACY_ID])

    def test_without_a_state_dir_no_state_file_is_created_anywhere(self):
        self.playlist()
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(os.path.exists(self.default_path))
        self.assertEqual(os.listdir(self.state), [])
        self.assertEqual(os.listdir(self.default_state), [])

class DId2SequenceTest(unittest.TestCase):
    """D-ID-2, and the two writers must agree about it (D-ID-3's lesson).

    The board recorded the cause as a survivor inheriting a favourite that
    meant the row which went away. Run against the shipping functions that
    does not happen: the remap is keyed by the OLD id, which is url-derived
    and names the exact row.

    The harm needs three steps and no remap at all. A star made while the name
    is UNIQUE is name-keyed; a collision then orphans it; the collision later
    resolves onto a DIFFERENT row and the orphan comes back to life pointing
    somewhere else. The favourite never moves -- it starts resolving to
    another channel.

    So the open question the board records, how often provider names churn, is
    the wrong one. The frequency decides nothing: the mechanism is that ONE
    saved key cannot identify a channel, which is D-ID-4's finding, and
    D-ID-4's fix closes this one too.
    """

    @staticmethod
    def assigned(rows):
        helper.assign_ids(rows)
        return rows

    @staticmethod
    def ch(name, url, tvg=None):
        row = {"name": name, "url": url, "group": "G"}
        if tvg:
            row["tvgId"] = tvg
        return row

    def test_the_orphaned_name_key_comes_back_on_another_row(self):
        t0 = self.assigned([self.ch("ESPN", "http://p/A"), self.ch("BBC", "http://p/C")])
        starred = t0[0]["id"]
        self.assertTrue(starred.startswith("n:"), starred)

        t1 = self.assigned([self.ch("ESPN", "http://p/A"), self.ch("ESPN", "http://p/B"),
                            self.ch("BBC", "http://p/C")])
        self.assertEqual([c["id"][:2] for c in t1[:2]], ["u:", "u:"],
                         "a shared name refuses the key for both")
        self.assertNotIn(starred, [c["id"] for c in t1], "the star is orphaned here")

        t2 = self.assigned([self.ch("ESPN", "http://p/B"), self.ch("BBC", "http://p/C")])
        self.assertEqual(t2[0]["id"], starred,
                         "the survivor takes the key the removed row's star still holds")
        self.assertEqual(t2[0]["url"], "http://p/B",
                         "and it is the channel the user did NOT star")

    def test_both_writers_agree_on_every_step(self):
        """Model.js and the helper must produce the same ids, step for step."""
        import json
        import subprocess
        script = (
            'const M=require("./Model.js");'
            'const a=r=>{const v=M.channelIds(r);r.forEach((c,i)=>c.id=v[i]);return r};'
            'const c=(n,u)=>({name:n,url:u,group:"G"});'
            'console.log(JSON.stringify(['
            '  a([c("ESPN","http://p/A"),c("BBC","http://p/C")]).map(x=>x.id),'
            '  a([c("ESPN","http://p/A"),c("ESPN","http://p/B"),c("BBC","http://p/C")]).map(x=>x.id),'
            '  a([c("ESPN","http://p/B"),c("BBC","http://p/C")]).map(x=>x.id)]))')
        js = json.loads(subprocess.run(["node", "-e", script], capture_output=True,
                                       text=True, cwd=str(ROOT)).stdout)
        py = [[c["id"] for c in self.assigned(rows)] for rows in (
            [self.ch("ESPN", "http://p/A"), self.ch("BBC", "http://p/C")],
            [self.ch("ESPN", "http://p/A"), self.ch("ESPN", "http://p/B"), self.ch("BBC", "http://p/C")],
            [self.ch("ESPN", "http://p/B"), self.ch("BBC", "http://p/C")])]
        self.assertEqual(py, js, "the two writers disagree; D-ID-3 was exactly this class")

    def test_a_tvg_keyed_row_cannot_reach_this(self):
        """The population bound: a distinct tvg-id never consults the name."""
        t0 = self.assigned([self.ch("ESPN", "http://p/A", "espn.a"), self.ch("BBC", "http://p/C")])
        self.assertEqual(t0[0]["id"], "t:espn.a")
        t2 = self.assigned([self.ch("ESPN", "http://p/B", "espn.b"), self.ch("BBC", "http://p/C")])
        self.assertNotIn(t0[0]["id"], [c["id"] for c in t2],
                         "a t: key is never handed to another row")



if __name__ == "__main__":
    unittest.main()
