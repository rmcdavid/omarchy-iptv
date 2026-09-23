"""state.json tests for bin/omarchy-iptv (`state` subcommand).

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest

from helper_loader import load_helper

helper = load_helper()
ROOT = pathlib.Path(__file__).resolve().parent.parent
# The session vectors are shared with tests/Model.test.js (CLAUDE.md: a rule
# written twice gets one fixture).
FIXTURE = ROOT / "tests" / "fixtures" / "player-argv.json"
# state.json version 2 (ARCHITECTURE-SOURCES.md 2.1): the 0.1 keys plus the
# cache layout marker and the source history, plus the optional nullable
# `session` of the detached player (ARCHITECTURE-PLAYER.md section 8), which
# is additive and does NOT bump the version.
EMPTY = {"version": 2, "cacheLayout": 0, "favorites": [], "recents": [], "lastPlayed": None, "session": None, "sources": [], "savedSearches": []}


def v2(**patch):
    state = dict(EMPTY)
    state.update(patch)
    return state


def run(*args):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    lines = out.getvalue().strip().splitlines()
    return code, json.loads(lines[-1]) if lines else None, err.getvalue()


class StateCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "state")
        self.path = pathlib.Path(self.dir) / "state.json"

    def state(self, *args):
        return run("state", "--state-dir", self.dir, *args)

    def test_show_on_missing_file_is_empty_and_writes_nothing(self):
        code, payload, _ = self.state("show")
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"ok": True, "kind": "state", "action": "show", "state": EMPTY})
        self.assertFalse(self.path.exists())

    def test_init_creates_an_empty_private_state_file(self):
        # S-02: the service's FileView would create the file 0644; init runs first.
        code, payload, _ = self.state("init")
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"ok": True, "kind": "state", "action": "init", "created": True, "state": EMPTY})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), EMPTY)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(pathlib.Path(self.dir).stat().st_mode & 0o777, 0o700)
        code, payload, _ = self.state("init")
        self.assertEqual(code, 0)
        self.assertFalse(payload["created"])

    def test_init_keeps_an_existing_file_and_tightens_its_mode(self):
        self.path.parent.mkdir(parents=True)
        content = json.dumps({"version": 1, "favorites": ["t:keep"], "recents": [], "lastPlayed": None}, indent=2) + "\n"
        self.path.write_text(content, encoding="utf-8")
        os.chmod(self.path, 0o644)
        code, payload, _ = self.state("init")
        self.assertEqual(code, 0)
        self.assertFalse(payload["created"])
        self.assertEqual(payload["state"]["favorites"], ["t:keep"])
        self.assertEqual(self.path.read_text(encoding="utf-8"), content)   # not rewritten
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_init_state_file_is_exclusive(self):
        os.makedirs(self.dir, mode=0o700)
        self.assertTrue(helper.init_state_file(str(self.path), helper.default_state()))
        self.assertFalse(helper.init_state_file(str(self.path), v2(favorites=["x"])))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), EMPTY)

    def test_favorite_add_is_idempotent_and_ordered(self):
        for cid in ("t:bbc1.uk", "u:3f2a9c11", "t:bbc1.uk"):
            code, payload, _ = self.state("favorite", "add", cid)
            self.assertEqual(code, 0)
        self.assertEqual(payload["state"]["favorites"], ["t:bbc1.uk", "u:3f2a9c11"])
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written, v2(favorites=["t:bbc1.uk", "u:3f2a9c11"]))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(pathlib.Path(self.dir).stat().st_mode & 0o777, 0o700)

    def test_favorite_remove(self):
        self.state("favorite", "add", "t:a")
        self.state("favorite", "add", "t:b")
        code, payload, _ = self.state("favorite", "remove", "t:a")
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"]["favorites"], ["t:b"])
        code, payload, _ = self.state("favorite", "remove", "t:missing")
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"]["favorites"], ["t:b"])

    def test_clear_recents_keeps_favorites_last_played_and_the_session(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "version": 1,
            "favorites": ["t:bbc1.uk"],
            "recents": [{"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000}],
            "lastPlayed": {"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000},
            "session": {"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000},
        }), encoding="utf-8")
        code, payload, _ = self.state("clear-recents")
        self.assertEqual(code, 0)
        # A v1 file is written back as v2 (section 2.2): favorites, lastPlayed
        # and the player's session record all kept.
        self.assertEqual(payload["state"], v2(
            favorites=["t:bbc1.uk"],
            lastPlayed={"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000},
            session={"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000},
        ))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), payload["state"])

    def test_tolerates_malformed_and_foreign_content(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        code, payload, _ = self.state("show")
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"], EMPTY)
        self.path.write_text(json.dumps({
            "version": 99,
            "favorites": ["t:a", "", None, "t:a", 7],
            "recents": [{"id": "t:a", "name": None, "at": "12"}, {"name": "no id"}, "junk", {"id": "t:b", "at": "x"}],
            "lastPlayed": {"id": "t:a"},
            "unknownKey": True,
        }), encoding="utf-8")
        code, payload, _ = self.state("show")
        self.assertEqual(payload["state"], v2(
            favorites=["t:a", "7"],
            recents=[{"id": "t:a", "name": "", "at": 12}, {"id": "t:b", "name": "", "at": 0}],
            lastPlayed={"id": "t:a", "name": "", "at": 0},
        ))

    def test_state_dir_after_the_action_also_works(self):
        code, payload, _ = run("state", "favorite", "add", "t:x", "--state-dir", self.dir)
        self.assertEqual(code, 0)
        self.assertTrue(self.path.exists())
        code, payload, _ = run("state", "show", "--state-dir", self.dir)
        self.assertEqual(payload["state"]["favorites"], ["t:x"])

    def test_pretty_printed_service_file_round_trips(self):
        # Service.qml writes JSON.stringify(state, null, 2); the helper must read it.
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"version": 1, "favorites": ["t:q"], "recents": [], "lastPlayed": None}, indent=2) + "\n", encoding="utf-8")
        code, payload, _ = self.state("favorite", "add", "t:r")
        self.assertEqual(payload["state"]["favorites"], ["t:q", "t:r"])

    def test_default_state_dir_follows_xdg_state_home(self):
        original = os.environ.get("XDG_STATE_HOME")
        os.environ["XDG_STATE_HOME"] = self.tmp.name
        try:
            self.assertEqual(helper.state_dir(None), os.path.join(self.tmp.name, "omarchy-iptv"))
        finally:
            if original is None:
                del os.environ["XDG_STATE_HOME"]
            else:
                os.environ["XDG_STATE_HOME"] = original


class SessionKeyTest(unittest.TestCase):
    """state.json `session` (ARCHITECTURE-PLAYER.md 4.6, section 8, PO-3).

    The service owns the key, but every `state` action rewrites the whole
    document, so the helper has to read it, keep it and write it back: a
    reader that dropped it would erase a playing channel's record on the next
    `favorite add`, and the reattach would have nothing to mark failed."""

    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads(FIXTURE.read_text(encoding="utf-8"))["session"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "state")
        self.path = pathlib.Path(self.dir) / "state.json"

    def state(self, *args):
        return run("state", "--state-dir", self.dir, *args)

    def write(self, document):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Indented, the way Service.qml's JSON.stringify(state, null, 2) writes it.
        self.path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    def test_every_shared_vector_reads_the_same_record_as_model_js(self):
        for vector in self.vectors:
            self.assertEqual(helper.normalize_state(vector["state"])["session"], vector["record"], vector["name"])

    def test_a_file_without_the_key_reads_as_none_and_the_version_does_not_move(self):
        self.write({"version": 1, "favorites": ["t:bbc1.uk"], "recents": [], "lastPlayed": None})
        code, payload, _ = self.state("show")
        self.assertEqual(code, 0)
        self.assertIsNone(payload["state"]["session"])
        self.assertEqual(payload["state"]["version"], 2)
        self.assertEqual(helper.STATE_VERSION, 2)

    def test_a_cli_write_carries_the_session_of_a_playing_channel_through(self):
        session = {"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1758000123}
        self.write({"version": 2, "favorites": [], "recents": [], "lastPlayed": None, "session": session})
        code, payload, _ = self.state("favorite", "add", "t:other")
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"]["session"], session)
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["session"], session)
        # clear-recents and a source edit rewrite the document too.
        code, payload, _ = self.state("clear-recents")
        self.assertEqual(payload["state"]["session"], session)
        code, payload, _ = self.state("source", "add", "--url", "http://h.test/a.m3u")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["session"], session)

    def test_the_write_keeps_the_file_private_and_atomic_and_url_free(self):
        session = {"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1758000123}
        self.write({"version": 2, "favorites": [], "recents": [], "lastPlayed": None, "session": session})
        os.chmod(self.path, 0o600)
        self.state("favorite", "add", "t:x")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(pathlib.Path(self.dir).stat().st_mode & 0o777, 0o700)
        self.assertEqual(sorted(os.listdir(self.dir)), ["state.json"])   # no .tmp left behind
        self.assertNotIn("://", self.path.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["session"], session)

    def test_init_creates_the_file_with_a_null_session(self):
        code, payload, _ = self.state("init")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), EMPTY)
        self.assertIn("session", json.loads(self.path.read_text(encoding="utf-8")))

    def test_a_junk_session_is_dropped_rather_than_carried(self):
        self.write({"version": 2, "session": {"name": "no id"}, "favorites": []})
        code, payload, _ = self.state("favorite", "add", "t:x")
        self.assertIsNone(payload["state"]["session"])
        self.assertIsNone(json.loads(self.path.read_text(encoding="utf-8"))["session"])

    def test_saved_searches_survive_a_write_by_this_writer(self):
        """Ruling: every state writer is a whitelist, and there are THREE.

        normalize_state here rebuilds from default_state() and copies only the
        keys it knows. Model.parseState is a second, independent whitelist in a
        second language. Model.cloneState is a third, and it rebuilds the
        document field by field too. Before this key was taught to all three,
        one `state favorite add` through the real CLI erased it -- exit 0,
        "ok": true, no warning -- which is exactly the trap the roadmap
        predicted and which was reproduced live before the fix.
        """
        doc = dict(helper.default_state())
        doc["savedSearches"] = [{"query": "baton rouge", "at": 1790000000}]
        state = helper.normalize_state(doc)
        self.assertEqual(state["savedSearches"], [{"query": "baton rouge", "at": 1790000000}])

    def test_saved_searches_run_the_shared_fixture(self):
        """The same file tests/Model.test.js runs, so neither implementation
        can change the folding or the bounds while believing it agrees."""
        import json, os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "saved-searches.json")
        with open(path, encoding="utf-8") as fh:
            fixture = json.load(fh)
        for row in fixture["terms"]:
            self.assertEqual(helper.saved_search_terms(row["query"]), row["terms"], row["query"])
        for row in fixture["records"]:
            self.assertEqual(helper.normalize_saved_search(row["in"]), row["out"], repr(row["in"]))

    def test_saved_searches_are_bounded_and_de_duplicated_on_the_folded_terms(self):
        many = [{"query": "term%d" % i, "at": 0} for i in range(helper.MAX_SAVED_SEARCHES + 10)]
        self.assertEqual(len(helper.normalize_state({"savedSearches": many})["savedSearches"]),
                         helper.MAX_SAVED_SEARCHES)
        dupes = [{"query": "BBC One", "at": 1}, {"query": "  bbc   one  ", "at": 2}, {"query": "bbc two", "at": 3}]
        kept = helper.normalize_state({"savedSearches": dupes})["savedSearches"]
        self.assertEqual([r["query"] for r in kept], ["BBC One", "bbc two"])

    def test_the_key_order_matches_the_document_the_service_writes(self):
        # Both sides emit version, cacheLayout, favorites, recents, lastPlayed,
        # session, sources, savedSearches - so a diff of two state files stays
        # readable. The order is asserted and not just the set, because the two
        # writers are in different languages and a key appended in one place and
        # inserted in the other makes every diff noisy.
        self.assertEqual(list(helper.default_state()),
                         ["version", "cacheLayout", "favorites", "recents", "lastPlayed", "session", "sources", "savedSearches"])


if __name__ == "__main__":
    unittest.main()
