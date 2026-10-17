"""state.json tests for bin/omarchy-iptv (`state` subcommand).

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import signal
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
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper.main(list(args))
    finally:
        # F-HARNESS-27 (round 15): `state init` arms the helper's own
        # STATE_INIT_DEADLINE as SIGALRM with its DEFAULT action (R24d). Run
        # in-process here, that alarm belonged to the TEST RUNNER, which it
        # killed 30 s later (rc 142, no summary) whenever the rest of the
        # module took that long -- under load, run alone. Disarmed on the way
        # out of every in-process call.
        signal.alarm(0)
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
        self.assertEqual(payload, {"ok": True, "kind": "state", "action": "init", "found": "absent", "created": True, "state": EMPTY})
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
        # R22a (D-SINK-19 round 12): a file that does not parse is no longer
        # read as the empty state -- `show` says it could not be read, and the
        # file is left exactly as it was. Foreign CONTENT inside a JSON object
        # (an unknown version, junk entries, unknown keys) is still tolerated.
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        code, payload, _ = self.state("show")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "state_unreadable")
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{not json")
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
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import helper_files
        # The WHOLE helper, the stub and every part (D-REL-7): since the split
        # `inspect.getsource(helper)` is the stub alone, and this count read 0.
        source = helper_files.helper_source(str(ROOT))
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
            got = {"entryMigrated": state.get("entryMigrated")}
            if "dropped" in case["expect"]:
                gone = {"pendingEpg", "entryInputs"} - set(state)
                if not any("epgSetAt" in r for r in state["sources"]):
                    gone.add("epgSetAt")
                got["dropped"] = sorted(gone)
            self.assertEqual(got, case["expect"], case["name"])

    def test_r20a_the_helper_emits_exactly_the_shared_vocabulary(self):
        fixture = self._state_keys_fixture()
        state = helper.normalize_state(json.loads(json.dumps(fixture["document"])))
        keys = fixture["keys"]
        only = fixture.get("helperOnly", {})

        def want(name):
            return sorted(keys[name] + list(only.get(name, {})))
        played = [r for r in state["recents"] + [state["lastPlayed"], state["session"]] if r]
        self.assertEqual(sorted(state), want("top"))
        self.assertEqual(sorted({k for r in state["sources"] for k in r}), want("source"))
        self.assertEqual(sorted({k for r in played for k in r}), want("played"))
        self.assertEqual(sorted({k for r in state["savedSearches"] for k in r}), want("savedSearch"))
        # Kept, not merely present: the marker comes back as written.
        self.assertIs(state["entryMigrated"], True)

    def test_r21a_a_helper_write_keeps_the_migration_marker(self):
        """R21a's preserved-keys half, at the helper's own sink: `state
        favorite add`, `clear-recents` and `source update` over a migrated
        file. Erased, the next shell start would read the bar entry's URLs as
        migration inputs again. Seen red with the marker line removed from
        normalize_state (the first write drops it)."""
        fixture = self._state_keys_fixture()
        document = json.loads(json.dumps(fixture["document"]))
        os.makedirs(self.dir, exist_ok=True)
        self.path.write_text(json.dumps(document), encoding="utf-8")
        for args in (("favorite", "add", "t:itv.uk"), ("clear-recents",),
                     ("source", "update", document["sources"][1]["key"], "--label", "Second")):
            code, _payload, _ = self.state(*args)
            self.assertEqual(code, 0, args)
            written = json.loads(self.path.read_text(encoding="utf-8"))
            self.assertIs(written.get("entryMigrated"), True, args)

    def test_r21a_an_unmigrated_file_stays_unmigrated_and_no_helper_verb_invents_the_marker(self):
        """The marker is the SERVICE's to set, by the migration; a helper
        write over a 0.13.x file (no marker) must not set it, or the next start
        would refuse the URL that file's install named its source by."""
        os.makedirs(self.dir, exist_ok=True)
        self.path.write_text(json.dumps({"version": 2, "sources": [], "favorites": []}), encoding="utf-8")
        for args in (("favorite", "add", "t:itv.uk"), ("source", "add", "--url", "http://z.example.test/l.m3u", "--now", "100")):
            code, _payload, _ = self.state(*args)
            self.assertEqual(code, 0, args)
            self.assertNotIn("entryMigrated", json.loads(self.path.read_text(encoding="utf-8")), args)

    def test_r21d_a_guide_url_the_helper_sets_carries_no_set_time(self):
        """R21d: R19c's set times are withdrawn, so the helper's third route
        that set one (round 9's rule-15 search) sets none either."""
        code, payload, _ = self.state("source", "add", "--url", "http://z.example.test/l.m3u", "--epg-url", "http://z.example.test/g.xml",
                                      "--now", "1760000000")
        self.assertEqual(code, 0)
        key = payload["key"]
        # Read after EACH write: a stamp the add made would be dropped by the
        # update's own normalize_state, and a check after the update alone
        # was green with the add's stamp restored (lane-key-m1's mutation P3).
        record = [r for r in json.loads(self.path.read_text(encoding="utf-8"))["sources"] if r["key"] == key][0]
        self.assertNotIn("epgSetAt", record, "the add")
        code, _, _ = self.state("source", "update", key, "--epg-url", "http://z.example.test/g2.xml", "--now", "1760000200")
        self.assertEqual(code, 0)
        record = [r for r in json.loads(self.path.read_text(encoding="utf-8"))["sources"] if r["key"] == key][0]
        self.assertEqual(record["epgUrl"], "http://z.example.test/g2.xml")
        self.assertNotIn("epgSetAt", record, "the update")

if __name__ == "__main__":
    unittest.main()


class StateNeverWrittenUnreadTest(unittest.TestCase):
    """D-SINK-19 round 12, R22a: A STATE THAT DID NOT LOAD IS NEVER WRITTEN.

    The helper's half. `state init` reports what it FOUND at the path before
    it touched anything -- the service's one witness that tells a missing
    file from a file inside a directory it cannot search, which Quickshell's
    FileView reports identically (FileNotFound, measured) -- and it never
    rewrites a file it could not parse. Every other `state` verb refuses a
    file that exists and cannot be read or parsed, instead of writing the
    empty default over it (read_json + normalize_state used to do exactly
    that: `state favorite add` over an unreadable file wrote one favourite
    and nothing else, exit 0).

    These are also the pins for the service harness's double of the init
    (tests/service-harness.js helperInit, rule 10): each fault below is one
    of its branches, run against the REAL helper as a subprocess, the way the
    service runs it. The foreign-owner faults cannot be made without root and
    are argued, not run: the chmod fails, so nothing changes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "state")
        os.makedirs(self.dir, mode=0o700)
        self.path = pathlib.Path(self.dir) / "state.json"
        self.real = json.dumps(v2(favorites=["t:keep"], sources=[SRC_PROVIDER, SRC_SECOND], activeKey="d990c2e4", entryMigrated=True), indent=2) + "\n"
        # a 0000 directory would defeat the TemporaryDirectory cleanup
        self.addCleanup(lambda: os.chmod(self.dir, 0o700) if os.path.isdir(self.dir) else None)

    def init(self):
        import subprocess, sys
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        proc = subprocess.run([sys.executable, "-I", str(HELPER_PATH), "state", "--state-dir", self.dir, "init"],
                              capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_init_reports_absent_and_creates_the_file(self):
        payload = self.init()
        self.assertEqual((payload["found"], payload["created"]), ("absent", True))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), EMPTY)

    def test_init_over_a_0000_file_reports_file_restores_0600_and_never_rewrites_it(self):
        self.path.write_text(self.real, encoding="utf-8")
        os.chmod(self.path, 0)
        before = self.path.stat()
        payload = self.init()
        self.assertEqual((payload["found"], payload["created"]), ("file", False))
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.real)
        self.assertEqual(self.path.stat().st_mtime_ns, before.st_mtime_ns)

    def test_init_inside_a_0000_directory_reports_unreadable_restores_0700_and_never_rewrites_the_file(self):
        self.path.write_text(self.real, encoding="utf-8")
        os.chmod(self.path, 0o600)
        mtime = self.path.stat().st_mtime_ns
        os.chmod(self.dir, 0)
        payload = self.init()
        self.assertEqual((payload["found"], payload["created"]), ("unreadable", False))
        self.assertEqual(pathlib.Path(self.dir).stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.real)
        self.assertEqual(self.path.stat().st_mtime_ns, mtime)

    def test_init_over_a_directory_at_the_path_reports_other_and_changes_nothing(self):
        self.path.mkdir(mode=0o700)
        payload = self.init()
        self.assertEqual((payload["found"], payload["created"]), ("other", False))
        self.assertTrue(self.path.is_dir())
        self.assertEqual(os.listdir(self.path), [])

    def test_init_over_a_dangling_symlink_reports_link_and_creates_nothing(self):
        # R24b (round 14): `link`, not `other` -- the shell's sentence for it
        # names the link, where `other` led to the folder-permission advice.
        target = pathlib.Path(self.tmp.name) / "gone.json"
        os.symlink(target, self.path)
        payload = self.init()
        self.assertEqual((payload["found"], payload["created"]), ("link", False))
        self.assertTrue(self.path.is_symlink())
        self.assertFalse(target.exists())

    def test_init_never_rewrites_a_file_it_could_not_parse(self):
        for text in ("{\"version\": 2, \"sources\": [", "", "[1, 2]", "\x00\x01 not text"):
            with self.subTest(text=text[:12]):
                self.path.write_text(text, encoding="utf-8")
                os.chmod(self.path, 0o600)
                before = self.path.stat()
                payload = self.init()
                self.assertEqual((payload["found"], payload["created"]), ("file", False))
                self.assertEqual(self.path.read_bytes(), text.encode("utf-8"))
                after = self.path.stat()
                self.assertEqual((after.st_mtime_ns, after.st_ctime_ns, after.st_ino), (before.st_mtime_ns, before.st_ctime_ns, before.st_ino))

    def verbs(self):
        return [("show",), ("favorite", "add", "t:x"), ("favorite", "remove", "t:keep"), ("clear-recents",),
                ("source", "list"), ("source", "add", "--url", "http://new.example.test/list.m3u"),
                ("source", "update", "d990c2e4", "--label", "renamed"), ("source", "remove", "42839dd5")]

    def assert_refused_and_untouched(self, restore=None):
        before = self.path.read_bytes() if restore is None and self.path.is_file() else None
        for verb in self.verbs():
            with self.subTest(verb=" ".join(verb)):
                code, payload, err = run("state", "--state-dir", self.dir, *verb)
                self.assertEqual(code, 1)
                self.assertEqual(payload["ok"], False)
                self.assertEqual(payload["error"]["code"], "state_unreadable")
                self.assertNotIn("password", json.dumps(payload) + err)
        if restore is not None:
            restore()
        if before is not None:
            self.assertEqual(self.path.read_bytes(), before)
        elif self.path.is_file():
            self.assertEqual(self.path.read_text(encoding="utf-8"), self.real)

    def test_every_verb_refuses_a_file_that_does_not_parse_and_leaves_it_byte_for_byte(self):
        for text in ("{\"version\": 2, \"sources\": [", "", "[]", "null", "\"a string\""):
            with self.subTest(text=text[:12]):
                self.path.write_text(text, encoding="utf-8")
                self.assert_refused_and_untouched()

    def test_every_verb_refuses_a_0000_file_and_leaves_it_as_it_was(self):
        self.path.write_text(self.real, encoding="utf-8")
        os.chmod(self.path, 0)
        self.assert_refused_and_untouched(restore=lambda: os.chmod(self.path, 0o600))

    def test_every_verb_refuses_a_0000_directory_and_leaves_the_file_as_it_was(self):
        self.path.write_text(self.real, encoding="utf-8")
        os.chmod(self.dir, 0)
        self.assert_refused_and_untouched(restore=lambda: os.chmod(self.dir, 0o700))

    def test_every_verb_refuses_a_directory_at_the_path(self):
        self.path.mkdir(mode=0o700)
        self.assert_refused_and_untouched()
        self.assertTrue(self.path.is_dir())

    def test_a_missing_file_is_still_a_fresh_state_for_every_writer(self):
        code, payload, _ = run("state", "--state-dir", self.dir, "favorite", "add", "t:new")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["favorites"], ["t:new"])

    def test_the_d_id_1_remap_writes_nothing_over_a_file_it_could_not_parse(self):
        # R22b's list: the playlist fetch's state remap is the helper's other
        # writer of state.json, and it already wrote only a dict it read.
        for text in ("{not json", "", "[]"):
            with self.subTest(text=text[:12]):
                self.path.write_text(text, encoding="utf-8")
                channels = [{"id": "t:a", "name": "A", "url": "http://x.example.test/a.ts", "tvgId": "a"}]
                self.assertEqual(helper.remap_state_file(str(self.path), channels), 0)
                self.assertEqual(self.path.read_text(encoding="utf-8"), text)


class StateNeverBlocksTest(unittest.TestCase):
    """D-SINK-19 round 13, R23b and R23d: the helper never opens a state path
    in a way that can block, never reads one that is not a regular file (or a
    symlink to one), and never chmods anything that is not the kind it
    repairs.

    The round-12 lenses measured the defect: with a FIFO at state.json,
    `state init`, `state show` and `state favorite add` each sat in open()
    until `timeout` killed them (rc 124), on the shipped 0.13.6 as on the
    candidate; the service waited on that init forever and every start left
    an orphaned helper. And `state init` chmod-ed a DIRECTORY at the state
    path 0755 -> 0600, making the user's directory unsearchable.

    Every case here runs the REAL helper as a subprocess WITH A TIMEOUT, so a
    regression fails rather than hangs the suite (an in-process call to a
    blocking open would hang it). The socket is bound by a child that chdirs
    first, so the test does not depend on how long TMPDIR's path is (a unix
    socket path is limited to 107 bytes)."""

    TIMEOUT = 20

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "state")
        os.makedirs(self.dir, mode=0o700)
        self.path = pathlib.Path(self.dir) / "state.json"

    def helper(self, *argv):
        import subprocess, sys
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        try:
            proc = subprocess.run([sys.executable, "-I", str(HELPER_PATH), *argv],
                                  capture_output=True, text=True, env=env, timeout=self.TIMEOUT)
        except subprocess.TimeoutExpired:
            self.fail("the helper did not answer within %d s: %s" % (self.TIMEOUT, " ".join(argv)))
        lines = proc.stdout.strip().splitlines()
        return proc.returncode, (json.loads(lines[-1]) if lines else None), proc.stderr

    def make_fifo(self):
        os.mkfifo(self.path, 0o600)

    def make_socket(self):
        import subprocess, sys
        code = "import os, socket, sys; os.chdir(sys.argv[1]); s = socket.socket(socket.AF_UNIX); s.bind('state.json'); s.close()"
        subprocess.run([sys.executable, "-I", "-c", code, self.dir], check=True, timeout=self.TIMEOUT)

    def fingerprint(self):
        st = os.lstat(self.path)
        return (st.st_mode, st.st_ino, st.st_mtime_ns, st.st_ctime_ns)

    def verbs(self):
        return [("show",), ("favorite", "add", "t:x"), ("favorite", "remove", "t:x"), ("clear-recents",),
                ("source", "list"), ("source", "add", "--url", "http://new.example.test/list.m3u"),
                ("source", "update", "d990c2e4", "--label", "renamed"), ("source", "remove", "42839dd5")]

    def assert_init_reports_other_and_leaves_it(self):
        before = self.fingerprint()
        code, payload, err = self.helper("state", "--state-dir", self.dir, "init")
        self.assertEqual(code, 0, err)
        self.assertEqual((payload["found"], payload["created"]), ("other", False))
        self.assertEqual(self.fingerprint(), before)

    def assert_every_verb_refuses_and_leaves_it(self):
        before = self.fingerprint()
        for verb in self.verbs():
            with self.subTest(verb=" ".join(verb)):
                code, payload, err = self.helper("state", "--state-dir", self.dir, *verb)
                self.assertEqual(code, 1, err)
                self.assertEqual(payload["error"]["code"], "state_unreadable")
                self.assertIn("not a regular file", payload["error"]["message"])
                self.assertEqual(self.fingerprint(), before)

    def test_init_over_a_fifo_answers_other_at_once_and_leaves_it(self):
        self.make_fifo()
        self.assert_init_reports_other_and_leaves_it()

    def test_every_verb_refuses_a_fifo_at_once_and_leaves_it(self):
        self.make_fifo()
        self.assert_every_verb_refuses_and_leaves_it()

    def test_init_over_a_socket_answers_other_and_leaves_it(self):
        self.make_socket()
        self.assert_init_reports_other_and_leaves_it()

    def test_every_verb_refuses_a_socket_and_leaves_it(self):
        self.make_socket()
        self.assert_every_verb_refuses_and_leaves_it()

    def test_every_verb_refuses_a_directory_as_not_a_regular_file(self):
        self.path.mkdir(mode=0o755)
        self.assert_every_verb_refuses_and_leaves_it()

    def test_init_never_chmods_a_directory_at_the_path(self):
        # R23d: the round-12 live lens's case exactly -- a 0755 directory came
        # back 0600 and its contents could no longer be listed.
        self.path.mkdir(mode=0o755)
        os.chmod(self.path, 0o755)
        (self.path / "inside.txt").write_text("mine", encoding="utf-8")
        self.assert_init_reports_other_and_leaves_it()
        self.assertEqual(stat_mode(self.path), 0o755)
        self.assertEqual((self.path / "inside.txt").read_text(encoding="utf-8"), "mine")

    def test_init_never_chmods_a_fifo_at_the_path(self):
        os.mkfifo(self.path, 0o644)
        os.chmod(self.path, 0o644)
        self.assert_init_reports_other_and_leaves_it()
        self.assertEqual(stat_mode(self.path), 0o644)

    def test_init_still_repairs_a_symlink_to_a_0000_file(self):
        # The repair the round-12 CONFIRMED reading depends on still reaches a
        # regular file behind a symlink (a dotfiles-managed state.json).
        target = pathlib.Path(self.tmp.name) / "real-state.json"
        target.write_text(json.dumps(v2(favorites=["t:keep"])) + "\n", encoding="utf-8")
        os.chmod(target, 0)
        os.symlink(target, self.path)
        code, payload, err = self.helper("state", "--state-dir", self.dir, "init")
        self.assertEqual(code, 0, err)
        self.assertEqual((payload["found"], payload["created"]), ("file", False))
        self.assertEqual(stat_mode(target), 0o600)
        self.assertTrue(self.path.is_symlink())

    def test_init_never_chmods_a_file_where_the_state_directory_should_be(self):
        # R23d, rule 15's sibling in ensure_private_dir: its last chmod made
        # whatever was at the DIRECTORY path 0700 -- a regular file there came
        # out executable.
        # R24b (round 14, D-SRC-26): and it ANSWERS, cleanly -- `found`
        # "not-a-dir", nothing created, exit 0 -- where it printed a traceback
        # and `code: internal` (exit 1) before; the shell maps the answer to a
        # sentence that names the folder (Model.stateUnreadableNotice).
        os.rmdir(self.dir)
        pathlib.Path(self.dir).write_text("not a directory", encoding="utf-8")
        os.chmod(self.dir, 0o644)
        code, payload, err = self.helper("state", "--state-dir", self.dir, "init")
        self.assertEqual(code, 0, err)
        self.assertEqual((payload["found"], payload["created"]), ("not-a-dir", False))
        self.assertNotIn("Traceback", err)
        self.assertEqual(stat_mode(pathlib.Path(self.dir)), 0o644)
        self.assertEqual(pathlib.Path(self.dir).read_text(encoding="utf-8"), "not a directory")

    def test_every_verb_refuses_a_file_where_the_state_directory_should_be(self):
        # R24b: the same path, one answer: refused, exit 1, the file as it was.
        os.rmdir(self.dir)
        pathlib.Path(self.dir).write_text("not a directory", encoding="utf-8")
        for verb in self.verbs():
            with self.subTest(verb=" ".join(verb)):
                code, payload, err = self.helper("state", "--state-dir", self.dir, *verb)
                self.assertEqual(code, 1, err)
                self.assertEqual(payload["error"]["code"], "state_unreadable")
                self.assertNotIn("Traceback", err)
                self.assertEqual(pathlib.Path(self.dir).read_text(encoding="utf-8"), "not a directory")

    def test_the_d_id_1_remap_reads_a_fifo_without_blocking(self):
        # The playlist fetch's state remap reads state.json through read_json.
        # Run in a child with a timeout so a blocking open fails, not hangs.
        import subprocess, sys
        self.make_fifo()
        code = ("import importlib.machinery, importlib.util, sys\n"
                "loader = importlib.machinery.SourceFileLoader('h', sys.argv[1])\n"
                "spec = importlib.util.spec_from_loader('h', loader)\n"
                "h = importlib.util.module_from_spec(spec); loader.exec_module(h)\n"
                "print(h.remap_state_file(sys.argv[2], [{'id': 't:a', 'name': 'A', 'url': 'http://x.example.test/a.ts', 'tvgId': 'a'}]))\n")
        try:
            proc = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(HELPER_PATH), str(self.path)],
                                  capture_output=True, text=True, timeout=self.TIMEOUT,
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        except subprocess.TimeoutExpired:
            self.fail("remap_state_file blocked on a FIFO")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "0")
        self.assertTrue(stat_is_fifo(self.path))


class StateSymlinkTest(unittest.TestCase):
    """D-SINK-19 round 14, R24b (D-SRC-23): ONE ANSWER PER PATH for a symlink
    at state.json. Followed when its target is a regular file -- for reads AND
    writes: the write lands beside the TARGET and is renamed onto it, so the
    link survives (the shell's own FileView save was measured doing exactly
    that, spikes/filewatch set r24) -- and refused like any non-regular path
    when it dangles or leads to anything else: every verb exit 1, file and
    link untouched; init `link`. Red on dev (ced1bd1): a dangling link was
    "absent" to every verb, which wrote an empty state plus its change over
    it, exit 0, and a valid link was replaced by a regular file. Every case
    runs the real helper as a subprocess with a timeout (inherited)."""

    SEED = {"version": 2, "cacheLayout": 2, "favorites": ["t:seed"], "recents": [], "sources": [
        {"key": "d990c2e4", "url": "http://provider.example.test/get.php?username=u&password=p", "epgUrl": "",
         "kind": "http", "label": "provider.example.test", "labelCustom": False, "origin": "cli",
         "addedAt": 10, "lastUsed": 20, "fetchedAt": 30, "channelCount": 9, "groupCount": 2},
        {"key": "42839dd5", "url": "http://second.example.test/list.m3u", "epgUrl": "",
         "kind": "http", "label": "second.example.test", "labelCustom": False, "origin": "cli",
         "addedAt": 11, "lastUsed": 21, "fetchedAt": 31, "channelCount": 5, "groupCount": 1}],
        "activeKey": "d990c2e4"}

    TIMEOUT = StateNeverBlocksTest.TIMEOUT
    helper = StateNeverBlocksTest.helper
    verbs = StateNeverBlocksTest.verbs

    def setUp(self):
        StateNeverBlocksTest.setUp(self)
        self.elsewhere = pathlib.Path(self.tmp.name) / "dotfiles"
        os.makedirs(self.elsewhere, mode=0o755)
        self.target = self.elsewhere / "state.json"

    def link_to(self, target):
        os.symlink(target, self.path)

    def test_a_valid_link_is_written_THROUGH_by_every_writing_verb_and_survives(self):
        writers = [v for v in self.verbs() if v[0] not in ("show",) and v[:2] != ("source", "list")]
        for verb in writers:
            with self.subTest(verb=" ".join(verb)):
                if self.path.is_symlink() or self.path.exists():
                    os.unlink(self.path)
                self.target.write_text(json.dumps(self.SEED) + "\n", encoding="utf-8")
                os.chmod(self.target, 0o644)
                self.link_to(self.target)
                code, payload, err = self.helper("state", "--state-dir", self.dir, *verb)
                self.assertEqual(code, 0, err)
                self.assertTrue(self.path.is_symlink(), "the link was replaced by a regular file")
                self.assertEqual(os.readlink(self.path), str(self.target))
                self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")).get("version"), 2)
                self.assertEqual(stat_mode(self.target), 0o600)
                # nothing left beside either end, and the target's folder kept its mode
                self.assertEqual(sorted(os.listdir(self.elsewhere)), ["state.json"])
                self.assertEqual(sorted(os.listdir(self.dir)), ["state.json"])
                self.assertEqual(stat_mode(self.elsewhere), 0o755)

    def test_a_valid_link_is_read_through(self):
        self.target.write_text(json.dumps(self.SEED) + "\n", encoding="utf-8")
        self.link_to(self.target)
        code, payload, err = self.helper("state", "--state-dir", self.dir, "show")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["state"]["favorites"], ["t:seed"])
        self.assertEqual(len(payload["state"]["sources"]), 2)

    def test_the_favorite_lands_in_the_target(self):
        self.target.write_text(json.dumps(self.SEED) + "\n", encoding="utf-8")
        self.link_to(self.target)
        code, payload, err = self.helper("state", "--state-dir", self.dir, "favorite", "add", "t:new")
        self.assertEqual(code, 0, err)
        on_disk = json.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["favorites"], ["t:seed", "t:new"])
        self.assertEqual(len(on_disk["sources"]), 2)

    def assert_every_verb_refuses_and_leaves_the_link(self, why):
        before = os.readlink(self.path)
        for verb in self.verbs():
            with self.subTest(case=why, verb=" ".join(verb)):
                code, payload, err = self.helper("state", "--state-dir", self.dir, *verb)
                self.assertEqual(code, 1, err)
                self.assertEqual(payload["error"]["code"], "state_unreadable")
                self.assertIn("nothing was written", payload["error"]["message"])
                self.assertTrue(self.path.is_symlink())
                self.assertEqual(os.readlink(self.path), before)
                self.assertEqual(sorted(os.listdir(self.dir)), ["state.json"])

    def test_a_dangling_link_is_refused_by_every_verb(self):
        self.link_to(self.elsewhere / "gone.json")
        self.assert_every_verb_refuses_and_leaves_the_link("dangling")
        self.assertFalse((self.elsewhere / "gone.json").exists())

    def test_a_link_into_a_missing_folder_is_refused_by_every_verb(self):
        # The dotfiles folder not mounted yet: the realistic case.
        self.link_to(self.elsewhere / "not-mounted" / "state.json")
        self.assert_every_verb_refuses_and_leaves_the_link("missing folder")

    def test_a_link_to_a_directory_or_a_fifo_is_refused_by_every_verb(self):
        os.makedirs(self.elsewhere / "adir")
        self.link_to(self.elsewhere / "adir")
        self.assert_every_verb_refuses_and_leaves_the_link("to a directory")
        os.unlink(self.path)
        os.mkfifo(self.elsewhere / "afifo", 0o600)
        self.link_to(self.elsewhere / "afifo")
        self.assert_every_verb_refuses_and_leaves_the_link("to a fifo")

    def test_init_answers_link_for_every_link_it_will_not_follow_and_file_for_one_it_will(self):
        cases = [("dangling", self.elsewhere / "gone.json", "link"), ("to a directory", self.elsewhere, "link")]
        for why, target, want in cases:
            with self.subTest(case=why):
                if self.path.is_symlink():
                    os.unlink(self.path)
                self.link_to(target)
                code, payload, err = self.helper("state", "--state-dir", self.dir, "init")
                self.assertEqual(code, 0, err)
                self.assertEqual((payload["found"], payload["created"]), (want, False))
                self.assertTrue(self.path.is_symlink())
        os.unlink(self.path)
        self.target.write_text(json.dumps(self.SEED) + "\n", encoding="utf-8")
        self.link_to(self.target)
        code, payload, err = self.helper("state", "--state-dir", self.dir, "init")
        self.assertEqual((code, payload["found"], payload["created"]), (0, "file", False))
        self.assertTrue(self.path.is_symlink())

    def test_the_d_id_1_remap_leaves_a_dangling_link_alone(self):
        import subprocess, sys
        code = ("import importlib.machinery, importlib.util, sys\n"
                "sys.dont_write_bytecode = True\n"
                "loader = importlib.machinery.SourceFileLoader('h', sys.argv[1])\n"
                "spec = importlib.util.spec_from_loader('h', loader)\n"
                "h = importlib.util.module_from_spec(spec); loader.exec_module(h)\n"
                "print(h.remap_state_file(sys.argv[2], [{'id': 't:a', 'name': 'A', 'url': 'http://x.example.test/a.ts', 'tvgId': 'a'}]))\n")
        def remap():
            proc = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(HELPER_PATH), str(self.path)],
                                  capture_output=True, text=True, timeout=self.TIMEOUT,
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            return proc.returncode, proc.stdout.strip(), proc.stderr
        self.link_to(self.elsewhere / "gone.json")
        self.assertEqual(remap()[:2], (0, "0"))
        self.assertTrue(self.path.is_symlink())
        self.assertFalse((self.elsewhere / "gone.json").exists())


class StateFolderLinkTest(unittest.TestCase):
    """D-SINK-19 round 15, R25c (D-SRC-32): THE STATE FOLDER GETS THE FILE'S
    RULE. A symbolic link AT the state folder (~/.local/state/omarchy-iptv,
    or --state-dir) is followed when it leads to a folder, and refused when
    it dangles or leads to anything else: every verb exit 1 with a sentence,
    link and target untouched; `state init` answers `found: folder-link`.
    The same for a link ABOVE the folder. Red on dev (002662d): over a
    dangling folder link `show` and `source list` printed an EMPTY listing,
    exit 0, and init, `favorite add` and `clear-recents` died with a
    FileNotFoundError traceback, `code: internal`.

    What the chmod does through a VALID folder link was measured before this
    was written (the lane's before.txt, the helper as a subprocess): it
    reaches the TARGET, 0755 -> 0700 and 0500 -> 0700, the link left a link.
    That is the folder the plugin keeps state.json in, wherever the user
    keeps it, so it keeps the plugin's own mode; the README says so (R24b's
    principle: never change what the link points at WITHOUT SAYING SO).
    Every case runs the real helper as a subprocess with a timeout."""

    TIMEOUT = StateNeverBlocksTest.TIMEOUT
    helper = StateNeverBlocksTest.helper
    verbs = StateNeverBlocksTest.verbs
    SEED = StateSymlinkTest.SEED
    SENTENCE = "the state folder is a symbolic link whose target is missing or is not a folder; nothing was written"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.dir = str(self.root / "st")

    def listing(self):
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))

    def test_a_dangling_folder_link_is_refused_by_every_verb_and_left_alone(self):
        os.symlink(self.root / "gone", self.dir)
        before = self.listing()
        for verb in self.verbs() + [("source", "update", "d990c2e4", "--url", "http://other.example.test/l.m3u")]:
            with self.subTest(verb=" ".join(verb)):
                code, payload, err = self.helper("state", "--state-dir", self.dir, *verb)
                self.assertEqual((code, payload["ok"], payload["error"]["code"]), (1, False, "state_unreadable"), err)
                self.assertEqual(payload["error"]["message"], self.SENTENCE)
                self.assertNotIn("Traceback", err)
                self.assertNotIn("state", payload)   # no listing, empty or otherwise
                self.assertEqual(self.listing(), before)
                self.assertTrue(os.path.islink(self.dir))

    def test_init_answers_folder_link_creates_nothing_and_exits_0(self):
        for shape in ("dangling", "file", "above"):
            with self.subTest(shape=shape):
                if os.path.lexists(self.dir):
                    os.unlink(self.dir)
                state_dir = self.dir
                if shape == "dangling":
                    os.symlink(self.root / "gone", self.dir)
                elif shape == "file":
                    (self.root / "afile").write_text("x", encoding="utf-8")
                    os.symlink(self.root / "afile", self.dir)
                else:
                    # A link ABOVE the state folder (an XDG_STATE_HOME that is
                    # a link to a folder not mounted yet): the same answer.
                    os.symlink(self.root / "gone", self.dir)
                    state_dir = os.path.join(self.dir, "omarchy-iptv")
                before = self.listing()
                code, payload, err = self.helper("state", "--state-dir", state_dir, "init")
                self.assertEqual((code, payload["found"], payload["created"]), (0, "folder-link", False), err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(self.listing(), before)

    def test_a_link_above_the_folder_is_refused_by_show(self):
        os.symlink(self.root / "gone", self.dir)
        code, payload, err = self.helper("state", "--state-dir", os.path.join(self.dir, "omarchy-iptv"), "show")
        self.assertEqual((code, payload["error"]["code"], payload["error"]["message"]), (1, "state_unreadable", self.SENTENCE), err)

    def test_a_valid_folder_link_is_followed_by_every_verb_and_its_target_made_0700(self):
        target = self.root / "dotfiles"
        target.mkdir(mode=0o755)
        os.chmod(target, 0o755)
        (target / "state.json").write_text(json.dumps(self.SEED) + "\n", encoding="utf-8")
        os.chmod(target / "state.json", 0o600)
        os.symlink(target, self.dir)
        code, payload, err = self.helper("state", "--state-dir", self.dir, "show")
        self.assertEqual((code, payload["state"]["favorites"]), (0, ["t:seed"]), err)
        self.assertEqual(stat_mode(target), 0o755)   # a read changes nothing
        code, payload, err = self.helper("state", "--state-dir", self.dir, "favorite", "add", "t:x")
        self.assertEqual((code, payload["state"]["favorites"]), (0, ["t:seed", "t:x"]), err)
        self.assertTrue(os.path.islink(self.dir))
        self.assertEqual(json.loads((target / "state.json").read_text(encoding="utf-8"))["favorites"], ["t:seed", "t:x"])
        self.assertEqual(stat_mode(target), 0o700)
        os.chmod(target, 0o755)
        code, payload, err = self.helper("state", "--state-dir", self.dir, "init")
        self.assertEqual((code, payload["found"], payload["created"]), (0, "file", False), err)
        self.assertEqual(stat_mode(target), 0o700)

    def test_d_src_34_a_file_link_into_a_folder_that_cannot_be_written_is_a_sentence(self):
        os.makedirs(self.dir, mode=0o700)
        ro = self.root / "ro"
        ro.mkdir(mode=0o700)
        (ro / "state.json").write_text(json.dumps(self.SEED) + "\n", encoding="utf-8")
        os.chmod(ro / "state.json", 0o600)
        os.chmod(ro, 0o500)
        self.addCleanup(os.chmod, ro, 0o700)
        os.symlink(ro / "state.json", os.path.join(self.dir, "state.json"))
        before = (ro / "state.json").read_bytes()
        code, payload, err = self.helper("state", "--state-dir", self.dir, "favorite", "add", "t:x")
        self.assertEqual((code, payload["ok"], payload["error"]["code"]), (1, False, "state_unwritable"), err)
        self.assertEqual(payload["error"]["message"],
                         "state.json is a symbolic link into a folder that cannot be written (Permission denied); nothing was written")
        self.assertNotIn("Traceback", err)
        self.assertEqual((ro / "state.json").read_bytes(), before)
        self.assertEqual(sorted(os.listdir(ro)), ["state.json"])   # no temporary file left
        self.assertEqual(stat_mode(ro), 0o500)                     # a link target's folder is never chmod-ed (R24b)


class FolderLinkSiblingsTest(unittest.TestCase):
    """R25c's rule-15 search: every ensure_private_dir caller over a link that
    leads nowhere, through the real helper as a subprocess. The cache folder
    (`cache migrate`, `cache prune`, `failed mark`) and the runtime socket
    folder (`player stop`, which runs no mpv) each ended in a traceback and
    `code: internal` on dev (002662d), having written nothing; each now
    answers `folder_unusable` with a sentence naming the link, exit 1, and
    still writes nothing. The logo folder is the same function inside
    `logos --fetch` (https only, so it is pinned in test_logos by a call, not
    here). A VALID link at any of them is followed and its target made 0700,
    as it was."""

    TIMEOUT = StateNeverBlocksTest.TIMEOUT
    helper = StateNeverBlocksTest.helper

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.link = str(self.root / "c")
        os.symlink(self.root / "gone", self.link)

    def test_each_caller_answers_a_sentence_and_writes_nothing(self):
        cases = [("cache", "--cache-dir", self.link, "migrate"), ("cache", "--cache-dir", self.link, "prune"),
                 ("failed", "--cache-dir", self.link, "mark", "--id", "t:x"),
                 ("player", "stop", "--socket", os.path.join(self.link, "mpv.sock"))]
        for argv in cases:
            with self.subTest(argv=" ".join(argv[:2])):
                code, payload, err = self.helper(*argv)
                self.assertEqual((code, payload["ok"], payload["error"]["code"]), (1, False, "folder_unusable"), err)
                self.assertEqual(payload["error"]["message"],
                                 "%s is a symbolic link whose target is missing or is not a folder; nothing was written" % self.link)
                self.assertNotIn("Traceback", err)
                self.assertFalse(os.path.lexists(self.root / "gone"))
                self.assertTrue(os.path.islink(self.link))


class StateInitDeadlineTest(unittest.TestCase):
    """D-SINK-19 round 14, R24d (D-SRC-24): `state init` bounds ITSELF.
    SIGALRM, default action, armed at the top of the verb before the state
    path is touched, so a shell that stops while the init is held (a hung
    filesystem) leaves nothing running past STATE_INIT_DEADLINE. Observed by
    running the REAL verb in a child whose first lstat sleeps (the hung
    filesystem, made deterministic) with the deadline shrunk to one second:
    the child must die of SIGALRM. Red on dev (ced1bd1), where it sleeps on."""

    def test_a_held_init_dies_of_its_own_alarm(self):
        import signal, subprocess, sys
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        code = ("import importlib.machinery, importlib.util, os, sys, time\n"
                "sys.dont_write_bytecode = True\n"
                "loader = importlib.machinery.SourceFileLoader('h', sys.argv[1])\n"
                "spec = importlib.util.spec_from_loader('h', loader)\n"
                "h = importlib.util.module_from_spec(spec); loader.exec_module(h)\n"
                "h.STATE_INIT_DEADLINE = 1\n"
                "real = os.lstat\n"
                "def slow(p, *a, **k):\n"
                "    if str(p).endswith('state.json'):\n"
                "        time.sleep(8)\n"
                "    return real(p, *a, **k)\n"
                "os.lstat = slow\n"
                "sys.exit(h.main(['state', '--state-dir', sys.argv[2], 'init']))\n")
        try:
            proc = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(HELPER_PATH), os.path.join(tmp.name, "st")],
                                  capture_output=True, text=True, timeout=5,
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        except subprocess.TimeoutExpired:
            self.fail("the held init was still running after 5 s: it does not bound itself")
        self.assertEqual(proc.returncode, -signal.SIGALRM, proc.stderr)

    def test_the_deadline_is_past_the_services_bound(self):
        # 15 s watchdog + 2 s kill grace in Service.qml (stateInitTimeoutMs,
        # stateInitKillGraceMs): the self-bound must never pre-empt them.
        svc = (ROOT / "Service.qml").read_text(encoding="utf-8")
        import re
        timeout = int(re.search(r"stateInitTimeoutMs: (\d+) \* 1000", svc).group(1))
        grace = int(re.search(r"stateInitKillGraceMs: (\d+) \* 1000", svc).group(1))
        self.assertGreater(helper.STATE_INIT_DEADLINE, timeout + grace)

    def test_f_harness_27_an_in_process_init_leaves_no_alarm_in_the_test_runner(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        code, payload, _ = run("state", "--state-dir", os.path.join(tmp.name, "st"), "init")
        self.assertEqual((code, payload["found"]), (0, "absent"))
        self.assertEqual(signal.alarm(0), 0)

    def test_no_other_verb_arms_it(self):
        import signal, subprocess, sys
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        code = ("import importlib.machinery, importlib.util, signal, sys, io, contextlib\n"
                "sys.dont_write_bytecode = True\n"
                "loader = importlib.machinery.SourceFileLoader('h', sys.argv[1])\n"
                "spec = importlib.util.spec_from_loader('h', loader)\n"
                "h = importlib.util.module_from_spec(spec); loader.exec_module(h)\n"
                "out = io.StringIO()\n"
                "with contextlib.redirect_stdout(out):\n"
                "    h.main(['state', '--state-dir', sys.argv[2], 'show'])\n"
                "print(signal.alarm(0))\n")
        proc = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(HELPER_PATH), os.path.join(tmp.name, "st")],
                              capture_output=True, text=True, timeout=20, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(proc.stdout.strip().splitlines()[-1], "0", proc.stderr)


def stat_mode(path):
    return os.lstat(path).st_mode & 0o777


def stat_is_fifo(path):
    import stat as _stat
    return _stat.S_ISFIFO(os.lstat(path).st_mode)
