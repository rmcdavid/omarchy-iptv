"""D-SINK-104, D-SINK-105 and D-SINK-111 (2026-11-16): what the helper's
replies and status files print.

D-SINK-104. The state verbs printed hidden groups, saved searches and the
recents, last-played and session names as stored; the playlist reply and
playlist-status.json printed the per-channel warnings with the channel's name
as the playlist wrote it; the play and start replies printed the name; and
the record the player carries (its stash) held the name, the group and the
zap ring's scope raw, which the status and probe replies printed beside a
redacted title. One table, REPLY_READINGS, read by emit and both status-file
writers, now prints each such field as the guide shows it (shown_text), and
the record is stored that way.

D-SINK-105. emit and both status files wrote DEL, the C1 controls, U+2028,
U+2029 and the text-direction controls raw; the shell's IPC replies escaped
the first three and not the last. Both now write the same set as escapes,
held by tests/fixtures/reply-escapes.json (the node suite runs
Model.ipcJson over it).

D-SINK-111. A `t:` id 0.18.0 made from a tvg-id holding a credential stays
in state.json and in an older player's record, and every state reply printed
it whole. Those replies and the player's record print it as ID_WITHHELD
(tests/fixtures/withheld-ids.json); state.json keeps it.

The assertion every verb here meets: no stdout line and no status file
holds a piece of the synthetic credential (`qqqqqq`, `zzzzzz`) or a raw
character of the escape set -- ids included, the exemption the first draft
of these tests gave them narrowed away.
"""
import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import signal
import tempfile
import unittest

from helper_loader import load_helper

helper = load_helper()
import test_mpv  # noqa: E402  the play and status doubles (FakeMpv, its relay and identity seam)

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "fixtures", "reply-escapes.json"), encoding="ascii") as fh:
    ESCAPES = json.load(fh)
with open(os.path.join(HERE, "fixtures", "withheld-ids.json"), encoding="ascii") as fh:
    IDS = json.load(fh)


def code_points(entries):
    out = set()
    for low, high in entries:
        out.update(range(int(low[2:], 16), int(high[2:], 16) + 1))
    return out


ESCAPED = code_points(ESCAPES["ranges"])
C1 = chr(0x9b)
DEL = chr(0x7f)
RLO = chr(0x202e)
LRI = chr(0x2066)
LS = chr(0x2028)
CREDENTIAL = "http://qqqqqq:zzzzzz@cdn.test/x"
LEGACY_ID = "t:qqqqqq:zzzzzz@cdn.test"


def poisoned(word):
    """A provider's text holding the credential and three escape-set code
    points, one of them inside the address's port."""
    return "%s %s%s http://qqqqqq:12%s34/zzzz@cdn.test/y %s end" % (word, RLO, CREDENTIAL, C1, LS)


def leaks(text):
    """The credential's pieces and the raw escape-set code points `text`
    holds."""
    found = [piece for piece in ("qqqqqq", "zzzzzz", "qqqq", "zzzz") if piece in text]
    return found + ["U+%04X" % ord(ch) for ch in set(text) if ord(ch) in ESCAPED]


def shows(text):
    """The credential's pieces and the controls a composed field holds,
    before the reply's escapes."""
    return [piece for piece in ("qqqqqq", "zzzzzz", "qqqq", "zzzz") if piece in text] + \
        ["U+%04X" % ord(ch) for ch in set(text) if ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F]


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper.main(list(args))
    finally:
        # `state init` arms SIGALRM with its default action for its own
        # process (STATE_INIT_DEADLINE); in-process that is the test runner's
        # (F-HARNESS-27), so it is cancelled here, as tests/test_state.py does.
        signal.alarm(0)
    return code, out.getvalue(), err.getvalue()


def emitted(payload):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        helper.emit(payload)
    return out.getvalue()


class EscapeTest(unittest.TestCase):
    """D-SINK-105, over every code point but the surrogates."""

    def everything(self):
        return "".join(chr(c) for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF)

    def judge(self, text, value):
        wrong = []
        chars = set(text)
        escapes = {int(h, 16) for h in re.findall(chr(92) * 2 + "u([0-9a-f]{4})", text)}
        for c in range(0x110000):
            if 0xD800 <= c <= 0xDFFF:
                continue
            raw = chr(c) in chars
            escaped = c in escapes
            if c in ESCAPED and (raw or not escaped):
                wrong.append(("raw" if raw else "not escaped", hex(c)))
            elif c not in ESCAPED and c >= 0x20 and chr(c) not in "\"\\" and not raw:
                wrong.append(("escaped", hex(c)))
        self.assertEqual(wrong[:6], [])
        self.assertEqual(json.loads(text), value)

    def test_the_fixture_is_the_helpers_list(self):
        self.assertEqual(code_points([("U+%04X" % low, "U+%04X" % high) for low, high in helper.REPLY_ESCAPE_RANGES]),
                         ESCAPED)
        self.assertEqual(len(ESCAPED), 33 + 2 + 12)
        self.assertFalse(ESCAPED & code_points([(c, c) for c in ESCAPES["notEscaped"]]))

    def test_emit_escapes_the_set_and_nothing_else(self):
        value = {"x": self.everything()}
        self.judge(emitted({"ok": True, "kind": "clipboard", "text": value["x"]}).strip(),
                   {"ok": True, "kind": "clipboard", "text": value["x"]})

    def test_a_status_file_escapes_the_set_and_nothing_else(self):
        folder = tempfile.mkdtemp(prefix="reply-escapes-")
        self.addCleanup(shutil.rmtree, folder, True)
        path = os.path.join(folder, "status.json")
        status = {"ok": True, "kind": "clipboard", "text": self.everything()}
        helper.write_status(path, status)
        text = pathlib.Path(path).read_text(encoding="utf-8")
        self.assertTrue(text.endswith("}\n"))
        self.assertNotIn(", ", text[:40])
        self.judge(text, status)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_a_lone_surrogate_is_still_written_as_its_escape(self):
        self.assertEqual(emitted({"x": chr(0xD800) + C1}).strip(), '{"x": "%sud800%su009b"}' % (chr(92), chr(92)))


class BoundaryTest(unittest.TestCase):
    """Every field the table names, one payload each, written independently
    of the table: removing any one entry of REPLY_READINGS turns its case
    red."""

    STASH_NAME = "stash.name"

    def payloads(self):
        p = poisoned
        return {
            "error.message": {"ok": False, "kind": "play", "error": {"code": "x", "message": p("Failed")}},
            "warnings[]": {"ok": True, "kind": "playlist", "warnings": ["fine", p("dropped option-looking key for")]},
            "name": {"ok": True, "kind": "play", "id": "t:a", "name": p("News")},
            "playing.name": {"ok": True, "kind": "player.start", "playing": {"id": "t:b", "name": p("News")}},
            "firstLoad.reason": {"ok": True, "kind": "player.start", "firstLoad": {"state": "failed", "reason": p("Open")}},
            "firstLoad.fileError": {"ok": True, "kind": "player.start",
                                    "firstLoad": {"state": "failed", "reason": "", "ended": "end-file", "fileError": p("x")}},
            "stash.name": {"ok": True, "kind": "status", "stash": {"id": "t:a", "name": p("News")}},
            "stash.group": {"ok": True, "kind": "player.probe", "stash": {"id": "t:a", "group": p("Sports")}},
            "stash.launchedFrom": {"ok": True, "kind": "status", "stash": {"id": "t:a", "launchedFrom": "g:" + p("Sports")}},
            "mediaTitle": {"ok": True, "kind": "status", "mediaTitle": p("News")},
            "tracks[].lang": {"ok": True, "kind": "player.tracks", "tracks": [{"id": 1, "lang": p("en")}]},
            "tracks[].title": {"ok": True, "kind": "player.tracks", "tracks": [{"id": 1}, {"id": 2, "title": p("Audio")}]},
            "tracks[].codec": {"ok": True, "kind": "player.tracks", "tracks": [{"id": 1, "codec": p("aac")}]},
            "state.recents[].name": {"ok": True, "kind": "state", "state": {"recents": [{"id": "t:a", "name": p("News")}]}},
            "state.lastPlayed.name": {"ok": True, "kind": "state", "state": {"lastPlayed": {"id": "t:a", "name": p("News")}}},
            "state.session.name": {"ok": True, "kind": "state", "state": {"session": {"id": "t:a", "name": p("News")}}},
            "state.hiddenGroups[]": {"ok": True, "kind": "state", "state": {"hiddenGroups": ["UK", p("Group")]}},
            "state.savedSearches[].query": {"ok": True, "kind": "state",
                                            "state": {"savedSearches": [{"query": p("find"), "at": 1}]}},
            "stash.id": {"ok": True, "kind": "player.probe", "stash": {"id": LEGACY_ID, "name": "News"}},
            "state.favorites[]": {"ok": True, "kind": "state", "state": {"favorites": ["t:news.us", LEGACY_ID]}},
            "state.recents[].id": {"ok": True, "kind": "state", "state": {"recents": [{"id": LEGACY_ID, "name": "N"}]}},
            "state.lastPlayed.id": {"ok": True, "kind": "state", "state": {"lastPlayed": {"id": LEGACY_ID, "name": "N"}}},
            "state.session.id": {"ok": True, "kind": "state", "state": {"session": {"id": LEGACY_ID, "name": "N"}}},
        }

    def test_every_field_is_read_at_emit(self):
        leaking = {path: leaks(emitted(payload)) for path, payload in self.payloads().items()}
        self.assertEqual({path: found for path, found in leaking.items() if found}, {})

    def test_every_field_is_read_in_a_status_file(self):
        folder = tempfile.mkdtemp(prefix="reply-shown-")
        self.addCleanup(shutil.rmtree, folder, True)
        leaking = {}
        for i, (path, payload) in enumerate(self.payloads().items()):
            target = os.path.join(folder, "s%d.json" % i)
            helper.write_status(target, payload)
            found = leaks(pathlib.Path(target).read_text(encoding="utf-8"))
            if found:
                leaking[path] = found
        self.assertEqual(leaking, {})

    def test_the_table_names_every_path_these_cases_name(self):
        self.assertEqual(sorted(path for path, _ in helper.REPLY_READINGS), sorted(self.payloads()))

    def test_a_field_reads_as_the_guide_shows_it(self):
        out = json.loads(emitted(self.payloads()["name"]))
        self.assertEqual(out["name"], helper.shown_text(poisoned("News")))
        self.assertEqual(out["name"], "News %shttp://cdn.test http://[host withheld] %s end" % (RLO, LS))

    def test_the_scope_is_kept_only_when_it_reads_plainly(self):
        self.assertEqual(helper.scope_reading("g:http://qqqqqq:zzzzzz@cdn.test/g"), "")
        self.assertEqual(helper.scope_reading("g:Sports" + C1), "")
        self.assertEqual(helper.scope_reading("g:Sports"), "g:Sports")
        self.assertEqual(helper.scope_reading("favorites"), "favorites")
        # The kept-equivalent case: the `g:` supplies the token's colon, so a
        # group with an `@` reads as a credential and the scope is "", which a
        # reattach turns back into this same scope when the channel is found
        # (the node suite's harness check).
        self.assertEqual(helper.scope_reading("g:Sports@HD"), "")

    def test_a_clipboard_reply_is_never_read(self):
        payload = {"ok": True, "kind": "clipboard", "text": CREDENTIAL, "name": CREDENTIAL}
        self.assertIs(helper.shown_reply(payload), payload)
        self.assertEqual(json.loads(emitted(payload))["text"], CREDENTIAL)

    def test_only_the_containers_on_a_path_are_copied(self):
        other = {"keep": [CREDENTIAL]}
        payload = {"ok": True, "kind": "status", "other": other, "stash": {"id": "t:a", "name": "N"}}
        out = helper.shown_reply(payload)
        self.assertIs(out["other"], other)
        self.assertIsNot(out["stash"], payload["stash"])
        self.assertEqual(payload["stash"]["name"], "N")


class IdTest(unittest.TestCase):
    """D-SINK-111: the shared fixture's ids through the shipping predicate."""

    def test_the_token_is_the_fixtures(self):
        self.assertEqual(helper.ID_WITHHELD, IDS["token"])

    def test_each_id_is_withheld_or_kept_as_the_fixture_says(self):
        wrong = [i for i in IDS["withheld"] if not helper.channel_id_withheld(i)]
        wrong += [i for i in IDS["kept"] if helper.channel_id_withheld(i)]
        self.assertEqual([ascii(i) for i in wrong], [])

    def test_the_parse_reads_the_same_tvg_ids_as_absent(self):
        """The one rule: a tvg-id the parse refuses is exactly a `t:` tail
        the reply withholds."""
        for item in IDS["withheld"] + IDS["kept"]:
            if not item.startswith("t:") or "#" in item or item == "t:":
                continue
            row = helper.make_channel({"tvg-id": item[2:]}, "Name", "http://cdn.test/x.ts", "", {}, {}, [])
            self.assertEqual(row.get("tvgId", "") == "", helper.channel_id_withheld(item), ascii(item))

    def test_an_error_reply_withholds_the_id_it_echoes(self):
        payload = helper.error_payload("play", helper.HelperError("unknown_channel", "x"), id=LEGACY_ID)
        self.assertEqual(payload["id"], IDS["token"])
        payload = helper.error_payload("play", helper.HelperError("unknown_channel", "x"), id="t:news.us")
        self.assertEqual(payload["id"], "t:news.us")


class StateVerbsTest(unittest.TestCase):
    """Every state verb prints the state; on 1118ffb every one printed the
    names, groups, saved searches and ids below as stored."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="reply-state-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        played = {"id": LEGACY_ID, "name": poisoned("News"), "at": 1758000000}
        state = {
            "version": 2, "cacheLayout": 2, "favorites": [LEGACY_ID, "t:news.us"],
            "recents": [played, {"id": "t:news.us", "name": "News", "at": 1758000001}],
            "lastPlayed": played, "session": dict(played),
            "sources": [], "activeKey": "",
            "savedSearches": [{"query": poisoned("find"), "at": 1758000000}],
            "hiddenGroups": [poisoned("Group"), "UK"],
        }
        self.path = os.path.join(self.dir, "state.json")
        pathlib.Path(self.path).write_text(json.dumps(state), encoding="utf-8")
        os.chmod(self.path, 0o600)

    def test_no_state_verb_prints_a_credential_piece_or_a_raw_control(self):
        leaking = {}
        for verb in (["show"], ["init"], ["source", "list"], ["favorite", "add", "t:espn.us"], ["clear-recents"]):
            code, out, err = run("state", "--state-dir", self.dir, *verb)
            self.assertEqual(code, 0, err)
            found = leaks(out)
            if found:
                leaking[" ".join(verb)] = found
        self.assertEqual(leaking, {})

    def test_the_legacy_id_prints_withheld_and_stays_in_the_file(self):
        code, out, err = run("state", "--state-dir", self.dir, "favorite", "add", "t:espn.us")
        self.assertEqual(code, 0, err)
        state = json.loads(out)["state"]
        self.assertEqual(state["favorites"], [helper.ID_WITHHELD, "t:news.us", "t:espn.us"])
        self.assertEqual(state["lastPlayed"]["id"], helper.ID_WITHHELD)
        stored = json.loads(pathlib.Path(self.path).read_text(encoding="utf-8"))
        self.assertEqual(stored["favorites"], [LEGACY_ID, "t:news.us", "t:espn.us"])
        self.assertEqual(stored["session"]["id"], LEGACY_ID)
        self.assertEqual(stored["hiddenGroups"][0], poisoned("Group"))


class PlaylistTest(unittest.TestCase):
    """The playlist reply and playlist-status.json: the per-channel warnings
    name a channel as the row does."""

    def test_warnings_name_the_channel_as_shown(self):
        folder = tempfile.mkdtemp(prefix="reply-playlist-")
        self.addCleanup(shutil.rmtree, folder, True)
        playlist = os.path.join(folder, "list.m3u")
        names = [poisoned("Watch"), "qqqqqq:zzzzzz@cdn.test", "Ctl http:" + C1 + "//qqqqqq:zzzzzz@cdn.test/x " + LRI]
        lines = ["#EXTM3U"]
        for i, name in enumerate(names):
            lines += ['#EXTINF:-1 tvg-id="c%d.test",%s' % (i, name), "#EXTVLCOPT:--bad-key=1",
                      "http://stream.example.test/live/%d.ts" % i]
        pathlib.Path(playlist).write_text("\n".join(lines) + "\n", encoding="utf-8")
        cache = os.path.join(folder, "cache")
        code, out, err = run("playlist", "--url", playlist, "--cache-dir", cache)
        self.assertEqual(code, 0, err)
        reply = json.loads(out)
        self.assertEqual(len([w for w in reply["warnings"] if "option-looking" in w]), 3)
        status = pathlib.Path(os.path.join(cache, helper.PLAYLIST_STATUS_FILE)).read_text(encoding="utf-8")
        self.assertEqual({"reply": leaks(out), "status": leaks(status)}, {"reply": [], "status": []})
        self.assertEqual(json.loads(status)["warnings"], reply["warnings"])


class EpgStatusTest(unittest.TestCase):
    """epg-status.json goes through the same writer: a guide file named with
    a direction control, which the refusal names by its base name."""

    def test_the_guide_status_file_escapes_the_set(self):
        folder = tempfile.mkdtemp(prefix="reply-epg-")
        self.addCleanup(shutil.rmtree, folder, True)
        cache = os.path.join(folder, "cache")
        missing = os.path.join(folder, "guide" + RLO + "lmx.xml")
        code, out, err = run("epg", "--url", missing, "--cache-dir", cache)
        self.assertNotEqual(code, 0)
        status = pathlib.Path(os.path.join(cache, helper.EPG_STATUS_FILE)).read_text(encoding="utf-8")
        self.assertIn("guide%su202elmx.xml" % chr(92), status)
        self.assertEqual({"reply": leaks(out), "status": leaks(status)}, {"reply": [], "status": []})


class PlayerTest(test_mpv.MpvTestCase):
    """The play reply, the record the player carries, and the status reply,
    through the shipping verbs against the suite's FakeMpv."""

    def setUp(self):
        super().setUp()
        playlist = os.path.join(self.dir, "poisoned.m3u")
        self.group = "http://qqqqqq:zzzzzz@cdn.test/g"
        pathlib.Path(playlist).write_text(
            '#EXTM3U\n#EXTINF:-1 tvg-id="p.test" group-title="%s",%s\nhttp://stream.example.test/live/p.ts\n'
            % (self.group, poisoned("Watch")), encoding="utf-8")
        code, _, _, stderr = test_mpv.run("playlist", "--url", playlist, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)

    def test_play_prints_and_stores_the_name_as_shown(self):
        server = self.start()
        code, payload, stdout, stderr = self.play("--id", "t:p.test", "--scope", "g:" + self.group, "--since", "7")
        self.assertEqual(code, 0, stderr)
        shown = helper.shown_text(poisoned("Watch"))
        self.assertEqual(payload["name"], shown)
        self.assertEqual(leaks(stdout), [])
        stashes = [c[2] for c in server.commands
                   if c[:2] == ["set_property", helper.USER_DATA_STASH] and isinstance(c[2], dict)]
        self.assertTrue(stashes)
        self.assertEqual({(s["name"], s["group"], s["launchedFrom"]) for s in stashes},
                         {(shown, "http://cdn.test", "")})
        titles = [c[2] for c in server.commands if c[:2] == ["set_property", "force-media-title"]]
        self.assertEqual(titles, [shown])

    def test_status_prints_an_older_record_and_the_title_as_shown(self):
        raw = {"schema": 1, "playing": True, "id": LEGACY_ID, "name": poisoned("Watch"), "group": self.group,
               "launchedFrom": "g:" + self.group, "sourceKey": "", "since": 7, "entryId": 2, "seq": 1, "verb": "play"}
        props = dict(test_mpv.STATUS_PROPS)
        props["media-title"] = poisoned("Watch")
        self.start(props=props, user_data={"omarchy-iptv": raw})
        code, _, stdout, stderr = test_mpv.run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        reply = json.loads(stdout)
        self.assertEqual(leaks(stdout), [])
        self.assertEqual(reply["stash"]["id"], helper.ID_WITHHELD)
        self.assertEqual(reply["stash"]["launchedFrom"], "")
        self.assertEqual(reply["mediaTitle"], helper.shown_text(poisoned("Watch")))


class WriteSideTest(unittest.TestCase):
    """The reply's own composers read the same way, so a field the
    boundary reads again is read once."""

    def test_the_target_carries_the_shown_name(self):
        folder = tempfile.mkdtemp(prefix="reply-target-")
        self.addCleanup(shutil.rmtree, folder, True)
        playlist = os.path.join(folder, "p.m3u")
        pathlib.Path(playlist).write_text('#EXTM3U\n#EXTINF:-1 tvg-id="p.test",%s\nhttp://stream.example.test/p.ts\n'
                                          % poisoned("Watch"), encoding="utf-8")
        cache = os.path.join(folder, "cache")
        code, _, err = run("playlist", "--url", playlist, "--cache-dir", cache)
        self.assertEqual(code, 0, err)
        target = helper.player_target("t:p.test", "", cache)
        self.assertEqual(target["shown"], helper.player_title_text(target["name"]))
        self.assertEqual(shows(target["shown"]), [])

    def test_track_rows_read_as_shown(self):
        rows = helper.track_rows([{"id": 1, "type": "audio", "lang": "en" + C1, "title": poisoned("Audio"),
                                   "codec": "aac" + DEL}])
        self.assertEqual([shows(rows[0][k]) for k in ("lang", "title", "codec")], [[], [], []])
        self.assertEqual((rows[0]["lang"], rows[0]["codec"]), ("en", "aac"))

    def test_the_first_load_reason_reads_as_shown(self):
        class Client:
            def __init__(self, events):
                self.events = [events]

            def drain_events(self, deadline):
                return self.events.pop(0) if self.events else None

        verdict = helper.observe_first_load(Client([
            # A TAB in a dotted username's port ends the plain reading's run
            # there, which prints the username; an ESC outside the address
            # stays in the plain reading.
            {"event": "log-message", "level": "error",
             "text": "Failed to open " + poisoned("x") + " http://qqqqqq.x:12\t34/zzzz@cdn.test/y \x1b[0m done\n"},
            {"event": "end-file", "reason": "error", "playlist_entry_id": 4, "file_error": "loading failed" + C1}]), 4, 5.0)
        self.assertEqual(verdict["state"], "failed")
        self.assertEqual((shows(verdict["reason"]), verdict["fileError"]), ([], "loading failed"))


if __name__ == "__main__":
    unittest.main()
