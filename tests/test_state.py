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
HELPER_PATH = ROOT / "bin" / "omarchy-iptv"
# The session vectors are shared with tests/Model.test.js (CLAUDE.md: a rule
# written twice gets one fixture).
FIXTURE = ROOT / "tests" / "fixtures" / "player-argv.json"
# state.json version 2 (ARCHITECTURE-SOURCES.md 2.1): the 0.1 keys plus the
# cache layout marker and the source history, plus the optional nullable
# `session` of the detached player (ARCHITECTURE-PLAYER.md section 8), which
# is additive and does NOT bump the version.
# D-SINK-19 adds the fifth additive key, `activeKey`: which source is active,
# by key, in the plugin's own 0600 file instead of as a URL in the host's.
# Additive at version 2 like the four before it.
EMPTY = {"version": 2, "cacheLayout": 0, "favorites": [], "recents": [], "lastPlayed": None, "session": None, "sources": [], "savedSearches": [], "hiddenGroups": [], "activeKey": ""}


# D-SINK-19's fixtures. Credentialed on purpose: the assertions about stdout
# and about what is left in the file are only worth anything over a URL that
# carries something.
SRC_PROVIDER = {
    "key": "d990c2e4",
    "url": "http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts",
    "epgUrl": "http://provider.example.test/xmltv.php?username=u&password=p",
    "kind": "http", "label": "provider.example.test", "labelCustom": False, "origin": "cli",
    "addedAt": 10, "lastUsed": 20, "fetchedAt": 30, "channelCount": 9, "groupCount": 2,
}
SRC_SECOND = {
    "key": "42839dd5", "url": "http://second.example.test/list.m3u", "epgUrl": "",
    "kind": "http", "label": "second.example.test", "labelCustom": False, "origin": "guide",
    "addedAt": 11, "lastUsed": 21, "fetchedAt": 31, "channelCount": 5, "groupCount": 1,
}


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

    def _init_as_subprocess(self, mode):
        """R10 (D-SRC-15), measured on the VERB as a subprocess the way the
        service runs it, over a file seeded with `mode`. Returns the stat
        before and after. ctime is the inotify IN_ATTRIB witness: a chmod
        bumps it whether or not the mode changed; nothing else here does."""
        import subprocess, sys, time
        self.path.parent.mkdir(parents=True, mode=0o700)
        content = json.dumps(v2(favorites=["t:keep"], activeKey="d990c2e4"), indent=2) + "\n"
        self.path.write_text(content, encoding="utf-8")
        os.chmod(self.path, mode)
        before = self.path.stat()
        time.sleep(0.02)   # so a chmod's ctime is distinguishable at any clock resolution
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run([sys.executable, "-I", str(HELPER_PATH), "state", "--state-dir", self.dir, "init"],
                              capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["created"])
        after = self.path.stat()
        self.assertEqual(self.path.read_text(encoding="utf-8"), content)   # never rewritten
        self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)             # the content clock never moves
        self.assertEqual(after.st_mode & 0o777, 0o600)
        return before, after

    def test_init_leaves_a_file_already_0600_alone(self):
        """R10: a file that is already private is NOT chmod-ed, so the shell's
        FileView sees no IN_ATTRIB from the ordinary start. ctime unchanged is
        the measurement (a chmod to the same mode bumps it; measured on this
        machine by the sibling test below, which seeds 0644)."""
        before, after = self._init_as_subprocess(0o600)
        self.assertEqual(after.st_ctime_ns, before.st_ctime_ns)

    def test_init_still_tightens_a_0644_file(self):
        """R10's other half, belt and braces: a file left 0644 (a FileView
        created it before S-02, or the user chmod-ed it) is still tightened,
        and that chmod IS the IN_ATTRIB the service has to survive (R9) --
        ctime moves, mtime and content do not."""
        before, after = self._init_as_subprocess(0o644)
        self.assertEqual(before.st_mode & 0o777, 0o644)
        self.assertGreater(after.st_ctime_ns, before.st_ctime_ns)

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

    def test_hidden_groups_survive_a_write_by_this_writer(self):
        """M3-01, the fourth key taught to this whitelist -- on the day it was
        added, not after a live erase. The shape is the savedSearches test's."""
        doc = dict(helper.default_state())
        doc["hiddenGroups"] = ["Religious", "Undefined"]
        state = helper.normalize_state(doc)
        self.assertEqual(state["hiddenGroups"], ["Religious", "Undefined"])

    def test_hidden_groups_survive_the_real_cli_writer(self):
        """Through main(), not normalize_state: the erase savedSearches suffered
        was exit 0, "ok": true, from exactly this verb."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = dict(helper.default_state())
        doc["hiddenGroups"] = ["Religious"]
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        code, payload, _ = self.state("favorite", "add", "t:x")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["hiddenGroups"], ["Religious"])

    def test_hidden_groups_run_the_shared_fixture(self):
        """tests/fixtures/hidden-groups.json, the same file Model.test.js runs,
        through normalize_hidden_groups AND through normalize_state."""
        import json as _json, os as _os
        path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "fixtures", "hidden-groups.json")
        with open(path, encoding="utf-8") as fh:
            fixture = _json.load(fh)
        self.assertEqual(fixture["cap"], helper.MAX_HIDDEN_GROUPS)
        for case in fixture["parse"]:
            self.assertEqual(helper.normalize_hidden_groups(case["raw"]), case["list"], case["name"])
            self.assertEqual(helper.normalize_state({"hiddenGroups": case["raw"]})["hiddenGroups"], case["list"], case["name"])
        many = ["G%d" % i for i in range(fixture["cap"] + 1)]
        self.assertEqual(len(helper.normalize_hidden_groups(many)), fixture["cap"])
        self.assertEqual(helper.normalize_hidden_groups(many)[-1], "G%d" % (fixture["cap"] - 1))

    # ---- D-SINK-19: activeKey, the fifth additive key ----------------------
    #
    # The plugin used to identify the active source by the provider URL on the
    # host's bar entry, so the credential HAD to be in a file the plugin does
    # not own. The key goes in state.json instead -- 0600 inside a 0700
    # directory -- and the host's file gets a pointer. The exposure is reduced,
    # not closed: a key is fnv1a32 of the URL, so it cannot carry one back and
    # it CAN confirm a guessed one (Model.entryShieldDecision states the trade).
    #
    # This reader is the dangerous half. It rebuilds the document from
    # default_state() and copies the keys it knows, so a key it has not been
    # taught is erased by the next write -- and for THIS key that means the
    # shell reads as not configured, with the sources still listed and no
    # active one. savedSearches suffered exactly that erase live.

    def test_active_key_survives_a_write_by_this_writer(self):
        """The fifth key taught to this whitelist, on the day it was added."""
        doc = dict(helper.default_state())
        doc["activeKey"] = "d990c2e4"
        self.assertEqual(helper.normalize_state(doc)["activeKey"], "d990c2e4")

    def test_active_key_survives_the_real_cli_writer(self):
        """Through main(), not normalize_state. This is the assertion that would
        have gone red for the erase savedSearches shipped with: exit 0,
        "ok": true, and the key gone from the file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = dict(helper.default_state())
        doc["activeKey"] = "d990c2e4"
        doc["sources"] = [SRC_PROVIDER]
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        for args in (("favorite", "add", "t:x"), ("favorite", "remove", "t:x"), ("clear-recents",)):
            code, payload, _ = self.state(*args)
            self.assertEqual(code, 0, args)
            written = json.loads(self.path.read_text(encoding="utf-8"))
            self.assertEqual(written["activeKey"], "d990c2e4", args)
            self.assertEqual(payload["state"]["activeKey"], "d990c2e4", args)

    def test_active_key_runs_the_shared_fixture(self):
        """tests/fixtures/active-key.json, the same file Model.test.js runs,
        through normalize_active_key AND through normalize_state.

        The fixture earned its keep on the first run: Model.activeKeyText used
        str() and coerced the number 12345678 and the list ["d990c2e4"] INTO
        the key grammar, where this reader rejects both for not being strings.
        A hand-edited or foreign-written file would have read as configured on
        one side and unconfigured on the other."""
        with open(ROOT / "tests" / "fixtures" / "active-key.json", encoding="utf-8") as fh:
            fixture = json.load(fh)
        for case in fixture["parse"]:
            self.assertEqual(helper.normalize_active_key(case["raw"]), case["key"], case["name"])
            self.assertEqual(helper.normalize_state({"activeKey": case["raw"]})["activeKey"],
                             case["key"], case["name"])
        # The fixture holds both answers and the shapes that are not strings.
        self.assertTrue(any(c["key"] for c in fixture["parse"]))
        self.assertTrue(any(not c["key"] for c in fixture["parse"]))
        self.assertTrue(any(not isinstance(c["raw"], str) for c in fixture["parse"]))

    def test_active_key_is_printed_rather_than_redacted(self):
        """public_state replaces every URL by its host, because stdout is a sink
        (rule 5). The key needs no treatment: it is fnv1a32 of the URL, it is
        already the cache directory name on disk, and it is the identifier every
        other field is keyed by. The assertion that matters beside it is that
        the URL is still gone."""
        doc = dict(helper.default_state())
        doc["activeKey"] = "d990c2e4"
        doc["sources"] = [SRC_PROVIDER]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        code, payload, _ = self.state("show")
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"]["activeKey"], "d990c2e4")
        self.assertNotIn("://", json.dumps(payload))
        self.assertNotIn("password", json.dumps(payload))

    def test_removing_the_active_source_clears_the_pointer(self):
        """D-SINK-19 introduced this obligation rather than fixing it: before
        the change nothing in this file could tell which source was active, so
        a CLI remove could not have left a dangling pointer. Now it could."""
        doc = dict(helper.default_state())
        doc["activeKey"] = "d990c2e4"
        doc["sources"] = [SRC_PROVIDER, SRC_SECOND]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        # Removing an INACTIVE source leaves the pointer alone.
        code, payload, _ = self.state("source", "remove", "42839dd5")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["activeKey"], "d990c2e4")
        # Removing the ACTIVE one clears it.
        code, payload, _ = self.state("source", "remove", "d990c2e4")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["activeKey"], "")

    def test_remove_runs_the_shared_fixture(self):
        """The `remove` section of tests/fixtures/active-key.json, the same
        cases Model.test.js runs through Model.removeSource (R3). The two
        implementations must leave the same pointer: the review found the JS
        side keeping a key that named the record it had just removed while
        this side cleared it, and 1,053 python tests were green because the
        join between them was a comment, not a call."""
        with open(ROOT / "tests" / "fixtures" / "active-key.json", encoding="utf-8") as fh:
            fixture = json.load(fh)
        self.assertGreaterEqual(len(fixture["remove"]), 4)
        for case in fixture["remove"]:
            state = dict(helper.default_state())
            state["sources"] = [dict(SRC_PROVIDER if k == "d990c2e4" else SRC_SECOND) for k in case["keys"]]
            state["activeKey"] = case["activeKey"]
            if case["ok"]:
                helper.remove_source_record(state, case["remove"])
            else:
                with self.assertRaises(helper.HelperError, msg=case["name"]):
                    helper.remove_source_record(state, case["remove"])
            self.assertEqual(state["activeKey"], case["want"]["activeKey"], case["name"])
            self.assertEqual(len(state["sources"]), case["want"]["count"], case["name"])
            # ... and the document the real writer leaves behind agrees.
            self.assertEqual(helper.normalize_state(state)["activeKey"], case["want"]["activeKey"], case["name"])

    def test_rekeying_the_active_source_carries_the_pointer_with_it(self):
        """`state source update --url` re-keys the record. The pointer has to
        follow, or state.json names a record that no longer exists."""
        doc = dict(helper.default_state())
        doc["activeKey"] = "d990c2e4"
        doc["sources"] = [SRC_PROVIDER, SRC_SECOND]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc), encoding="utf-8")
        code, payload, _ = self.state("source", "update", "d990c2e4",
                                      "--url", "http://provider.example.test:8080/get.php?username=u&password=p&type=m3u_plus&output=ts")
        self.assertEqual(code, 0)
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["replacedKey"], "d990c2e4")
        self.assertEqual(written["activeKey"], payload["key"])
        self.assertNotEqual(written["activeKey"], "d990c2e4")
        self.assertTrue(any(r["key"] == written["activeKey"] for r in written["sources"]))
        # Re-keying an INACTIVE source does not move the pointer.
        code, payload, _ = self.state("source", "update", "42839dd5",
                                      "--url", "http://second.example.test/other.m3u")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["activeKey"], written["activeKey"])

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

    def test_played_records_run_the_shared_fixture(self):
        """D-STATE-1. The same file tests/Model.test.js runs.

        `recents[]`, `lastPlayed` and `session` share one record shape and two
        implementations. They disagreed on any `at` that is numeric but not a
        plain integer literal: Model.js coerces with Math.trunc(Number(x)) and
        parses the whole JavaScript numeric grammar, while this reader used
        int(x), which raises on "12.9" and fell through to 0.
        """
        import json, os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "played-records.json")
        with open(path, encoding="utf-8") as fh:
            fixture = json.load(fh)
        for row in fixture["at"]:
            got = helper.normalize_played({"id": "x", "name": "X", "at": row["in"]})
            self.assertIsNotNone(got, repr(row["in"]))
            self.assertEqual(got["at"], row["want"], "at=%r: %s" % (row["in"], row["why"]))
        for row in fixture["records"]:
            self.assertEqual(helper.normalize_played(row["in"]), row["want"], repr(row["in"]))
        # The same coercion on the source-record keys, which is where D-STATE-1
        # turned out to live as well.
        for row in fixture["nonNegative"]:
            self.assertEqual(helper.non_negative_int(row["in"]), row["want"],
                             "non_negative_int(%r): %s" % (row["in"], row["why"]))

    def test_one_coercion_serves_every_caller(self):
        """Three readers wrote `int()` independently and two of them were wrong.

        The guard against a fourth is that there is now one function. If a
        caller stops routing through it, this goes red rather than the
        divergence being discovered years later by an unrelated fixture.
        """
        import inspect
        source = inspect.getsource(helper)
        self.assertEqual(source.count("int(float("), 1,
                         "coerce_int should be the only place that parses a number this way")
        for name in ("normalize_played", "non_negative_int", "normalize_saved_search"):
            body = inspect.getsource(getattr(helper, name))
            self.assertIn("coerce_int", body, "%s must route through coerce_int" % name)

    def test_the_key_order_matches_the_document_the_service_writes(self):
        # Both sides emit version, cacheLayout, favorites, recents, lastPlayed,
        # session, sources, savedSearches - so a diff of two state files stays
        # readable. The order is asserted and not just the set, because the two
        # writers are in different languages and a key appended in one place and
        # inserted in the other makes every diff noisy.
        self.assertEqual(list(helper.default_state()),
                         ["version", "cacheLayout", "favorites", "recents", "lastPlayed", "session",
                          "sources", "savedSearches", "hiddenGroups", "activeKey"])

    # ---- R20a (D-SINK-19 round 10, D-SRC-20): the helper keeps what the
    # service writes. The same fixture tests/Model.test.js runs; there, every
    # reducer Service.qml hands the state to is driven and the keys it emits
    # must EQUAL the fixture's list, and here the helper's reader must emit
    # exactly that list over the fixture's document. A key taught to one
    # reader alone is red on one side or the other the day it is added.
    def _state_keys_fixture(self):
        with open(ROOT / "tests" / "fixtures" / "state-keys.json", encoding="utf-8") as fh:
            return json.load(fh)

    def test_r20a_value_cases_run_the_shared_fixture(self):
        fixture = self._state_keys_fixture()
        for case in fixture["cases"]:
            state = helper.normalize_state(json.loads(json.dumps(case["input"])))
            got = {"pendingEpg": state.get("pendingEpg"), "entryInputs": state.get("entryInputs"),
                   "epgSetAt": [record.get("epgSetAt") for record in state["sources"]]}
            self.assertEqual(got, case["expect"], case["name"])

    def test_r20a_the_helper_emits_exactly_the_shared_vocabulary(self):
        fixture = self._state_keys_fixture()
        state = helper.normalize_state(json.loads(json.dumps(fixture["document"])))
        keys = fixture["keys"]
        only = fixture.get("helperOnly", {})

        def want(name):
            return sorted(keys[name] + list(only.get(name, {})))
        played = [r for r in state["recents"] + [state["lastPlayed"], state["session"]] if r]
        slots = state["entryInputs"].values()
        self.assertEqual(sorted(state), want("top"))
        self.assertEqual(sorted({k for r in state["sources"] for k in r}), want("source"))
        self.assertEqual(sorted({k for r in played for k in r}), want("played"))
        self.assertEqual(sorted({k for r in state["savedSearches"] for k in r}), want("savedSearch"))
        self.assertEqual(sorted(state["pendingEpg"]), want("pendingEpg"))
        self.assertEqual(sorted(state["entryInputs"]), want("entryInputs"))
        self.assertEqual(sorted({k for r in slots for k in r}), want("entryInput"))
        # Kept, not merely present: the three round-9/10 values come back as written.
        document = fixture["document"]
        self.assertEqual(state["pendingEpg"], document["pendingEpg"])
        self.assertEqual(state["entryInputs"], document["entryInputs"])
        self.assertEqual([r.get("epgSetAt") for r in state["sources"]],
                         [r.get("epgSetAt") for r in document["sources"]])

    def test_r20a_the_entry_input_slots_mirror_the_models_retired_settings(self):
        # Model.RETIRED_SETTINGS, the list Model.entryInputsRecord walks.
        model = (ROOT / "model" / "settings.mjs").read_text(encoding="utf-8")
        import re
        names = re.search(r'var RETIRED_SETTINGS = \[([^\]]*)\]', model).group(1)
        self.assertEqual(tuple(n.strip().strip('"') for n in names.split(",")), helper.ENTRY_INPUT_SLOTS)

    def test_r20a_d_src_20_a_helper_write_keeps_the_held_guide_url_and_every_set_time(self):
        """D-SRC-20, the round-9 lens's sequence at the helper's own sink:
        `state favorite add`, `clear-recents` and `source update` over a file
        holding a pending guide URL, a record's epgSetAt and the consumed
        slots. Seen red on lane-key-y2's helper: pendingEpg absent, epgSetAt
        [None], entryInputs absent after the first write."""
        fixture = self._state_keys_fixture()
        document = json.loads(json.dumps(fixture["document"]))
        os.makedirs(self.dir, exist_ok=True)
        self.path.write_text(json.dumps(document), encoding="utf-8")
        for args in (("favorite", "add", "t:itv.uk"), ("clear-recents",),
                     ("source", "update", document["sources"][1]["key"], "--label", "Second")):
            code, _payload, _ = self.state(*args)
            self.assertEqual(code, 0, args)
            written = json.loads(self.path.read_text(encoding="utf-8"))
            self.assertEqual(written.get("pendingEpg"), document["pendingEpg"], args)
            self.assertEqual(written.get("entryInputs"), document["entryInputs"], args)
            self.assertEqual([r.get("epgSetAt") for r in written["sources"]], [1760000000000, None], args)

    def test_r20a_stdout_carries_the_held_guide_urls_host_never_the_url(self):
        """Rule 5. public_state printed whatever the reader kept, and the reader
        had kept no pendingEpg -- so teaching the reader would have printed the
        held guide URL, credentials and all, on every `state` verb."""
        os.makedirs(self.dir, exist_ok=True)
        held = "http://u:secretpass@p.example.test/xmltv.php?username=u&password=secretpass"
        self.path.write_text(json.dumps({"version": 2, "pendingEpg": {"url": held, "seenAt": 5}}), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = helper.main(["state", "--state-dir", self.dir, "show"])
        self.assertEqual(code, 0)
        self.assertNotIn("secretpass", out.getvalue())
        self.assertEqual(json.loads(out.getvalue().strip().splitlines()[-1])["state"]["pendingEpg"],
                         {"epgHost": "p.example.test", "seenAt": 5})

    def test_r20a_a_guide_url_the_helper_sets_is_stamped_with_its_time_and_an_unchanged_one_is_not(self):
        """R19c's third route (round 9's rule-15 search left it open): `state
        source add|update --epg-url` is an explicit input, set NOW, in ms."""
        code, payload, _ = self.state("source", "add", "--url", "http://z.example.test/l.m3u", "--epg-url", "http://z.example.test/g.xml",
                                      "--now", "1760000000")
        self.assertEqual(code, 0)
        key = payload["key"]
        record = [r for r in json.loads(self.path.read_text(encoding="utf-8"))["sources"] if r["key"] == key][0]
        self.assertEqual(record["epgSetAt"], 1760000000000)
        code, _, _ = self.state("source", "update", key, "--epg-url", "http://z.example.test/g.xml", "--now", "1760000100")
        record = [r for r in json.loads(self.path.read_text(encoding="utf-8"))["sources"] if r["key"] == key][0]
        self.assertEqual(record["epgSetAt"], 1760000000000, "the same guide URL again is not a later input")
        code, _, _ = self.state("source", "update", key, "--epg-url", "http://z.example.test/g2.xml", "--now", "1760000200")
        record = [r for r in json.loads(self.path.read_text(encoding="utf-8"))["sources"] if r["key"] == key][0]
        self.assertEqual(record["epgSetAt"], 1760000200000)
        code, payload, _ = self.state("source", "add", "--url", "http://y.example.test/l.m3u", "--now", "1760000300")
        record = [r for r in json.loads(self.path.read_text(encoding="utf-8"))["sources"] if r["key"] == payload["key"]][0]
        self.assertNotIn("epgSetAt", record, "no guide URL given, nothing set")


if __name__ == "__main__":
    unittest.main()
