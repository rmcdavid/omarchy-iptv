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
EMPTY = {"version": 1, "favorites": [], "recents": [], "lastPlayed": None}


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
        self.assertFalse(helper.init_state_file(str(self.path), {"version": 1, "favorites": ["x"], "recents": [], "lastPlayed": None}))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), EMPTY)

    def test_favorite_add_is_idempotent_and_ordered(self):
        for cid in ("t:bbc1.uk", "u:3f2a9c11", "t:bbc1.uk"):
            code, payload, _ = self.state("favorite", "add", cid)
            self.assertEqual(code, 0)
        self.assertEqual(payload["state"]["favorites"], ["t:bbc1.uk", "u:3f2a9c11"])
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written, {"version": 1, "favorites": ["t:bbc1.uk", "u:3f2a9c11"], "recents": [], "lastPlayed": None})
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

    def test_clear_recents_keeps_favorites_and_last_played(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "version": 1,
            "favorites": ["t:bbc1.uk"],
            "recents": [{"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000}],
            "lastPlayed": {"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000},
        }), encoding="utf-8")
        code, payload, _ = self.state("clear-recents")
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"], {
            "version": 1, "favorites": ["t:bbc1.uk"], "recents": [],
            "lastPlayed": {"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000},
        })
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
        self.assertEqual(payload["state"], {
            "version": 1,
            "favorites": ["t:a", "7"],
            "recents": [{"id": "t:a", "name": "", "at": 12}, {"id": "t:b", "name": "", "at": 0}],
            "lastPlayed": {"id": "t:a", "name": "", "at": 0},
        })

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


if __name__ == "__main__":
    unittest.main()
