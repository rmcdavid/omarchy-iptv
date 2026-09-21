"""D-ID-1, end to end: seed a scheme-1 state, migrate it, rotate the provider
password, and watch every saved reference still name its channel.

The row (docs/STATUS.md) was fixed at 482a21e plus a25382f, and every test
that proves it (tests/test_channel_ids.py) either drives channel_id_remap /
remap_state_ids directly on tests/fixtures/channel-ids.json or drives the
`playlist` verb once on basic.m3u, where one row moves. The list the plugin is
actually configured with cannot show the defect at all: every row there has a
unique tvg-id, every id is `t:` under both schemes, and the migration is a
total no-op -- so a pass on it cannot tell a wired migration from a dead one,
which is byte for byte the state two reviewers refused.

This module runs the rotation those tests never run, through the REAL helper
verb in a subprocess (argv list, never a shell string), with --cache-dir and
--state-dir under mkdtemp and HOME redirected by tests/helper_loader.py:

  1. `playlist` on list-v1.m3u with the seeded state -> `moved 8`, the `t:`
     rows and the two refused pairs did not move, the merged favourite appears
     once, the unknown key survived, mode 0600, and every reference resolves
     to a channel NAME through the helper's own channels.json;
  2. `playlist` on list-v1.m3u again -> nothing moved, file not rewritten;
  3. `playlist` on list-v2.m3u (every stream URL's path segment differs) ->
     every moved reference and every `t:` reference resolves to the SAME name
     as before, while the legacy `u:` ids of those rows all differ between v1
     and v2 (the harm), and the two accepted-limit rows (D-ID-2) are orphaned;
  4. tests/fixtures/qa-id-rotate/verify.js, run through node, calls the
     shipping Model.js on the same fixture and must agree with the helper.

Read tests/fixtures/qa-id-rotate/README.md for the seed, row by row.

RULE 11. With `channel_id_remap` returning {} in bin/omarchy-iptv (a dead
migration behind a wired call site, the refused state) this module runs 7
tests and FAILS 4: test_the_first_run_moves_every_seeded_reference (no `moved`
line; the moved favourites orphaned against v1's own channels.json),
test_the_second_run_moves_nothing_and_leaves_the_file_alone (there was no
first move to be idempotent about), test_the_rotation_keeps_every_moved_
reference_on_its_channel (every seeded reference orphaned after v2) and
test_the_javascript_mirror_agrees_with_the_helper (node says moved 8 and
eight remap entries, the helper says 0 and none). Against the shipping helper
all 7 pass. The three fixture-shape tests stay green under that mutation on
purpose: they pin what the fixture IS, not what the migration does.
"""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import unittest

import helper_loader
from helper_loader import load_helper

helper = load_helper()
HELPER = helper_loader.HELPER
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "qa-id-rotate"
LIST_V1 = FIXTURE / "list-v1.m3u"
LIST_V2 = FIXTURE / "list-v2.m3u"
SEED = FIXTURE / "state-seed.json"
VERIFY_JS = FIXTURE / "verify.js"

LEGACY = helper.CHANNEL_ID_SCHEME_LEGACY

# The seed, by design (README.md): eight legacy references, one on each of the
# eight rows that move, spread over all four slots. Literals, not a call into
# the code under test -- the point is that the shipping command produces them.
MOVED = 8
MOVED_LINE = "moved %d saved channel reference(s) onto id scheme %d" % (MOVED, helper.CHANNEL_ID_SCHEME)
# What each slot names after the migration, in order. Favourites shrink by
# one because the legacy Charlie Kids reference lands on the scheme-2 id that
# was already in the list and is merged, not duplicated.
FAVORITE_NAMES = ["Alpha News", "Hotel TV", "Charlie Kids", "Lima Twins", "Golf HD", "Bravo Sports", "Hash Twin 132789"]
RECENT_NAMES = ["Delta Movies", "India TV", "Echo Music"]
LAST_PLAYED_NAME = "Foxtrot Docs"
SESSION_NAME = "Golf SD"
MERGED_NAME = "Charlie Kids"
# The accepted limit (D-ID-2): a refused name key leaves the row on a `u:` id
# that the rotation re-keys. The colliding-name pair (D) and the hash-collision
# pair (E) are orphaned by v2, and the test says so rather than looking away.
ORPHANED_BY_ROTATION = {"Lima Twins", "Hash Twin 132789"}
MOVING_ROWS = ["Alpha News", "Bravo Sports", "Charlie Kids", "Delta Movies", "Echo Music", "Foxtrot Docs", "Golf HD", "Golf SD"]
TVG_ROWS = ["Hotel TV", "India TV", "Juliet TV", "Kilo TV"]
REFUSED_ROWS = ["Lima Twins", "Lima Twins", "Hash Twin 132789", "Hash Twin 729192"]
UNKNOWN_KEY = "qaUnknownTopLevelKey"


def parse(path):
    with open(path, encoding="utf-8") as handle:
        return helper.parse_m3u(handle.read())["channels"]


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class RotationFixtureShapeTest(unittest.TestCase):
    """The fixture is what README.md says it is, checked through the shipping
    id functions rather than by reading the file. A fixture that drifted into
    a shape where nothing moves would make every run test below vacuous."""

    def test_v1_moves_exactly_the_rows_the_row_needs(self):
        channels = parse(LIST_V1)
        legacy = helper.channel_ids(channels, LEGACY)
        fresh = helper.channel_ids(channels)
        rows = list(zip([channel["name"] for channel in channels], legacy, fresh))
        self.assertEqual([name for name, before, after in rows if before != after], MOVING_ROWS)
        for name, before, after in rows:
            with self.subTest(name):
                if name in MOVING_ROWS:
                    self.assertTrue(before.startswith("u:"), before)
                    self.assertTrue(after.startswith("n:"), after)
                elif name in TVG_ROWS:
                    self.assertTrue(before.startswith("t:"), before)
                    self.assertEqual(before, after)
                else:
                    self.assertIn(name, REFUSED_ROWS)
                    self.assertTrue(before.startswith("u:"), before)
                    self.assertEqual(before, after)
        self.assertEqual(sorted(name for name, _, _ in rows if name in REFUSED_ROWS), sorted(REFUSED_ROWS))
        # The two categories that must NOT move, and why: D shares its bytes,
        # E shares only its hash. Two different names, one key.
        self.assertEqual(helper.name_id_key("Hash Twin 132789"), helper.name_id_key("Hash Twin 729192"))
        self.assertNotEqual("Hash Twin 132789", "Hash Twin 729192")
        # Every id on the list is still unique: the refused pairs keep distinct URL ids.
        self.assertEqual(len(set(fresh)), len(fresh))

    def test_v2_differs_from_v1_only_in_the_stream_urls(self):
        lines_v1 = LIST_V1.read_text(encoding="utf-8").splitlines()
        lines_v2 = LIST_V2.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines_v1), len(lines_v2))
        changed = [(a, b) for a, b in zip(lines_v1, lines_v2) if a != b]
        for a, b in changed:
            self.assertTrue(a.startswith("http://") and b.startswith("http://"), (a, b))
        v1 = parse(LIST_V1)
        v2 = parse(LIST_V2)
        # Every URL rotated, and nothing else about any row did.
        self.assertEqual(len(changed), len(v1))
        self.assertEqual([c.get("tvgId", "") for c in v1], [c.get("tvgId", "") for c in v2])
        self.assertEqual([c["name"] for c in v1], [c["name"] for c in v2])
        self.assertEqual([c["group"] for c in v1], [c["group"] for c in v2])
        self.assertTrue(all(a["url"] != b["url"] for a, b in zip(v1, v2)))
        self.assertTrue(all("@" not in c["url"] for c in v1 + v2), "no userinfo in any fixture URL")

    def test_the_harm_every_credentialed_legacy_id_changes_across_the_rotation(self):
        """D-ID-1 in two numbers, on this fixture: 4 of 16 ids survive the
        rotation under scheme 1, 12 of 16 under scheme 2. The 4 that survive
        scheme 1 are the `t:` rows, which never carried the credential."""
        v1 = parse(LIST_V1)
        v2 = parse(LIST_V2)
        legacy_v1 = helper.channel_ids(v1, LEGACY)
        legacy_v2 = helper.channel_ids(v2, LEGACY)
        fresh_v1 = helper.channel_ids(v1)
        fresh_v2 = helper.channel_ids(v2)
        self.assertEqual(sum(1 for a, b in zip(legacy_v1, legacy_v2) if a == b), 4)
        self.assertEqual([a for a, b in zip(legacy_v1, legacy_v2) if a == b], ["t:" + c["tvgId"] for c in v1 if c["name"] in TVG_ROWS])
        self.assertEqual(sum(1 for a, b in zip(fresh_v1, fresh_v2) if a == b), 12)
        self.assertEqual([c["name"] for c, a, b in zip(v1, fresh_v1, fresh_v2) if a != b], REFUSED_ROWS)
        # Every legacy reference the seed holds is gone from v2 under scheme 1:
        # that is the empty favourites list the user saw.
        seed = read_json(SEED)
        seeded = [item for item in seed["favorites"] if item.startswith("u:")]
        seeded += [entry["id"] for entry in seed["recents"] if entry["id"].startswith("u:")]
        seeded += [seed["lastPlayed"]["id"], seed["session"]["id"]]
        self.assertEqual(len(seeded), MOVED + 2)  # eight that move plus the two refused rows
        self.assertTrue(all(item in legacy_v1 for item in seeded), "the seed names v1 rows")
        self.assertEqual([item for item in seeded if item in legacy_v2], [])


class RotationRunTest(unittest.TestCase):
    """The whole rotation, through the real helper verb."""

    def setUp(self):
        self.dir = pathlib.Path(helper_loader.SANDBOX) / ("id-rotate-" + os.urandom(4).hex())
        self.cache = self.dir / "cache"
        self.state = self.dir / "state"
        for directory in (self.cache, self.state):
            directory.mkdir(mode=0o700, parents=True)
        self.addCleanup(shutil.rmtree, str(self.dir), True)
        self.path = self.state / helper.STATE_FILE
        shutil.copyfile(str(SEED), str(self.path))
        # Deliberately looser than the helper's own contract (CLAUDE.md 6), so
        # that 0600 after the run is an observation of the helper's write and
        # not of this copy.
        os.chmod(str(self.path), 0o644)
        self.seed = read_json(SEED)

    def playlist(self, playlist):
        completed = subprocess.run(
            [sys.executable, str(HELPER), "playlist", "--url", str(playlist),
             "--cache-dir", str(self.cache), "--state-dir", str(self.state)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed

    def channels_document(self):
        return read_json(self.cache / helper.CHANNELS_FILE)

    def index(self):
        """{id: name} from the helper's own channels.json, the sink the guide reads."""
        return {channel["id"]: channel["name"] for channel in self.channels_document()["channels"]}

    def state_file(self):
        return read_json(self.path)

    def resolved(self, state, index):
        return {
            "favorites": [index.get(item) for item in state["favorites"]],
            "recents": [index.get(entry["id"]) for entry in state["recents"]],
            "lastPlayed": index.get(state["lastPlayed"]["id"]),
            "session": index.get(state["session"]["id"]),
        }

    def assert_live_state_untouched(self):
        self.assertEqual(helper_loader.live_state_fingerprint(), helper_loader.LIVE_STATE_BEFORE,
                         "this test modified %s" % helper_loader.REAL_STATE_FILE)

    def test_the_first_run_moves_every_seeded_reference(self):
        completed = self.playlist(LIST_V1)
        self.assertIn(MOVED_LINE, completed.stderr)
        state = self.state_file()
        index = self.index()
        # Every reference resolves, by name, through the file the guide reads.
        self.assertEqual(self.resolved(state, index), {
            "favorites": FAVORITE_NAMES,
            "recents": RECENT_NAMES,
            "lastPlayed": LAST_PLAYED_NAME,
            "session": SESSION_NAME,
        })
        # What did not move is byte-identical with the seed: the `t:` rows and
        # the two refused pairs (their `u:` ids still resolve against v1).
        kept = [item for item in self.seed["favorites"]
                if item.startswith("t:") or index.get(item) in ORPHANED_BY_ROTATION]
        self.assertEqual(len(kept), 3)
        for item in kept:
            self.assertIn(item, state["favorites"])
        self.assertEqual(state["recents"][1], self.seed["recents"][1])
        self.assertTrue(state["recents"][1]["id"].startswith("t:"))
        # Merged, not duplicated: the seed held the target already.
        merged = [item for item, name in index.items() if name == MERGED_NAME]
        self.assertEqual(len(merged), 1)
        self.assertEqual(state["favorites"].count(merged[0]), 1)
        self.assertEqual(len(state["favorites"]), len(self.seed["favorites"]) - 1)
        # The rewrite edited the document; it did not rebuild it.
        self.assertEqual(state[UNKNOWN_KEY], self.seed[UNKNOWN_KEY])
        self.assertEqual(state["version"], self.seed["version"])
        self.assertEqual(state["sources"], self.seed["sources"])
        self.assertEqual(stat.S_IMODE(os.stat(str(self.path)).st_mode), 0o600)
        self.assert_live_state_untouched()

    def test_the_second_run_moves_nothing_and_leaves_the_file_alone(self):
        first = self.playlist(LIST_V1)
        # Not vacuous: a migration that never moves anything is idempotent too.
        self.assertIn(MOVED_LINE, first.stderr)
        before = helper_loader.fingerprint_of(self.path)
        second = self.playlist(LIST_V1)
        self.assertNotIn("saved channel reference", second.stderr)
        self.assertEqual(helper_loader.fingerprint_of(self.path), before)
        self.assert_live_state_untouched()

    def test_the_rotation_keeps_every_moved_reference_on_its_channel(self):
        self.playlist(LIST_V1)
        state_v1 = self.state_file()
        names_v1 = self.resolved(state_v1, self.index())
        # Before the rotation every reference resolves, so the comparison
        # below is between two full lists and not between two lists of None.
        self.assertEqual(names_v1, {
            "favorites": FAVORITE_NAMES,
            "recents": RECENT_NAMES,
            "lastPlayed": LAST_PLAYED_NAME,
            "session": SESSION_NAME,
        })
        before = helper_loader.fingerprint_of(self.path)
        rotated = self.playlist(LIST_V2)
        # The rotation itself has nothing to move and touches nothing.
        self.assertNotIn("saved channel reference", rotated.stderr)
        self.assertEqual(helper_loader.fingerprint_of(self.path), before)
        state_v2 = self.state_file()
        self.assertEqual(state_v2, state_v1)
        names_v2 = self.resolved(state_v2, self.index())
        # Every reference that moved, and every `t:` one, names the same channel
        # it named before the password changed. The accepted-limit rows do not,
        # and the assertion says which.
        self.assertEqual(names_v2["favorites"],
                         [None if name in ORPHANED_BY_ROTATION else name for name in names_v1["favorites"]])
        self.assertEqual(names_v2["recents"], names_v1["recents"])
        self.assertEqual(names_v2["lastPlayed"], names_v1["lastPlayed"])
        self.assertEqual(names_v2["session"], names_v1["session"])
        self.assertEqual(sorted(name for name in names_v1["favorites"] if name in ORPHANED_BY_ROTATION),
                         sorted(ORPHANED_BY_ROTATION))
        # The harm, stated on the rows the seed references: the legacy ids of
        # every moved row differ between v1 and v2, computed by the shipping
        # scheme-1 function, so under scheme 1 none of them would resolve now.
        v1 = parse(LIST_V1)
        v2 = parse(LIST_V2)
        legacy_v1 = dict(zip([c["name"] for c in v1], helper.channel_ids(v1, LEGACY)))
        legacy_v2 = dict(zip([c["name"] for c in v2], helper.channel_ids(v2, LEGACY)))
        for name in MOVING_ROWS:
            with self.subTest(name):
                self.assertNotEqual(legacy_v1[name], legacy_v2[name])
        for name in TVG_ROWS:
            with self.subTest(name):
                self.assertEqual(legacy_v1[name], legacy_v2[name])
        self.assert_live_state_untouched()

    def test_the_javascript_mirror_agrees_with_the_helper(self):
        """The first python-drives-node pattern here. verify.js calls the
        shipping Model.js on the helper's own channels.json output and the
        seed; both implementations are held to one fixture by a call."""
        node = shutil.which("node")
        self.assertIsNotNone(node, "node is required: the gate runs tests/Model.test.js with it")
        completed = self.playlist(LIST_V1)
        state_v1 = self.state_file()
        document_v1 = self.channels_document()
        channels_v1 = self.dir / "channels-v1.json"
        shutil.copyfile(str(self.cache / helper.CHANNELS_FILE), str(channels_v1))
        self.playlist(LIST_V2)
        document_v2 = self.channels_document()
        channels_v2 = self.dir / "channels-v2.json"
        shutil.copyfile(str(self.cache / helper.CHANNELS_FILE), str(channels_v2))
        run = subprocess.run([node, str(VERIFY_JS), str(channels_v1), str(channels_v2), str(SEED)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = json.loads(run.stdout)
        # The ids the helper wrote are the ids Model.js computes, on both lists.
        self.assertEqual(out["idsV1"], [channel["id"] for channel in document_v1["channels"]])
        self.assertEqual(out["idsV2"], [channel["id"] for channel in document_v2["channels"]])
        self.assertEqual(out["legacyV1"], helper.channel_ids(parse(LIST_V1), LEGACY))
        self.assertEqual(out["legacyV2"], helper.channel_ids(parse(LIST_V2), LEGACY))
        # The remap Model.js derives is the remap the helper derives ...
        self.assertEqual(out["remap"], helper.channel_id_remap(parse(LIST_V1)))
        self.assertEqual(len(out["remap"]), MOVED)
        # ... and applying it to the seed gives the file the helper wrote.
        self.assertEqual(out["moved"], MOVED)
        self.assertIn("moved %d saved" % out["moved"], completed.stderr)
        self.assertEqual(out["favorites"], state_v1["favorites"])
        self.assertEqual(out["recents"], state_v1["recents"])
        self.assertEqual(out["lastPlayed"], state_v1["lastPlayed"])
        self.assertEqual(out["session"], state_v1["session"])
        self.assert_live_state_untouched()


if __name__ == "__main__":
    unittest.main()
