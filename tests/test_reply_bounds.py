"""The replies the shell collects WHOLE, and the memory limit around them.

Every helper verb the service runs is a Process whose stdout (and stderr) is
a StdioCollector with waitForEnd, so whatever a verb prints is held in the
shell, in one piece, before anything reads it. Four things are pinned here,
each seen red against the code before it (f55a32f) or against a mutation of
the shipping decision; the counts are in the lane's report.

  D-SRC-13  the playlist status line's per-channel warnings are bounded by
            COUNT (D-M3U-1's channel_warning), observed through the verb with
            the cap LOWERED, never by building a long playlist.
  D-M3U-3   the playlist and epg verbs lift their memory limit on EVERY way
            out, before they compose, write or print a status -- observed in
            a real helper process, at the moment each file is opened and each
            line written, never by exhausting anything.
  D-M3U-4   every counted sentence reads correctly for one and for many.
  rule 15   the other replies swept for D-SRC-13: the tracks list, the
            first-load reason, and main()'s answer to a bug, each bounded by
            a constant (the cap lowered in the test, ordinary inputs).

INPUTS ARE ORDINARY AND SMALL. A cap is shown by lowering it to 2 or 3 and
feeding a handful of records; nothing here is built to cost memory or time.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import resource
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helper_loader import load_helper          # redirects HOME and $XDG_* first

helper = load_helper()
ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"
FIXTURES = ROOT / "tests" / "fixtures"
LIMIT_ENV = "OMARCHY_IPTV_MEMORY_LIMIT_MB"


def run_main(argv):
    """helper.main in this process -> (exit code, last stdout line as JSON, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(argv)
    lines = out.getvalue().strip().splitlines()
    return code, (json.loads(lines[-1]) if lines else None), out.getvalue(), err.getvalue()


# ---------------------------------------------------------------- D-SRC-13

class PlaylistWarningCountTest(unittest.TestCase):
    """D-SRC-13: decided by calling the verb. Ten ordinary channels, each with
    one option-looking key, under a cap lowered to three."""

    CAP = 3
    CHANNELS = 10

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.playlist = os.path.join(self.dir, "opts.m3u")
        with open(self.playlist, "w", encoding="utf-8") as handle:
            handle.write("#EXTM3U\n" + "".join(
                "#EXTINF:-1,Channel %d\n#EXTVLCOPT:--bad=1\nhttp://x.test/%d\n" % (i, i)
                for i in range(self.CHANNELS)))
        self.cache = os.path.join(self.dir, "cache")

    def test_the_status_line_lists_at_most_the_cap_and_counts_the_rest(self):
        with mock.patch.object(helper, "M3U_MAX_CHANNEL_WARNINGS", self.CAP):
            code, status, stdout, _ = run_main(["playlist", "--url", self.playlist, "--cache-dir", self.cache])
        self.assertEqual(code, 0, stdout)
        self.assertEqual(len(stdout.strip().splitlines()), 1)
        listed = [w for w in status["warnings"] if w.startswith("dropped option-looking key for ")]
        self.assertEqual(len(listed), self.CAP, status["warnings"])
        self.assertIn("%d more warnings like the ones above not listed" % (self.CHANNELS - self.CAP),
                      status["warnings"])
        # Nothing else in the line grows with the channels: the cap plus one
        # tail sentence, whatever CHANNELS is.
        self.assertEqual(len(status["warnings"]), self.CAP + 1, status["warnings"])
        on_disk = json.loads(pathlib.Path(self.cache, helper.PLAYLIST_STATUS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(on_disk["warnings"], status["warnings"])

    def test_the_count_bound_holds_for_both_kinds_of_per_channel_warning(self):
        # The second per-channel warning (an unsafe header name), mixed in:
        # one cap over both, as channel_warning keeps one counter.
        with open(self.playlist, "a", encoding="utf-8") as handle:
            handle.write("".join(
                "#EXTINF:-1,Header %d\n#KODIPROP:inputstream.adaptive.stream_headers=bad%%20name=v\nhttp://h.test/%d\n" % (i, i)
                for i in range(4)))
        with mock.patch.object(helper, "M3U_MAX_CHANNEL_WARNINGS", self.CAP):
            parsed = helper.parse_m3u(pathlib.Path(self.playlist).read_text(encoding="utf-8"))
        per_channel = [w for w in parsed["warnings"] if w.startswith("dropped ")]
        self.assertEqual(len(per_channel), self.CAP, parsed["warnings"])
        self.assertIn("%d more warnings like the ones above not listed" % (self.CHANNELS + 4 - self.CAP),
                      parsed["warnings"])


# ---------------------------------------------------------------- D-M3U-3

# Run as the program (runpy, run_name __main__, the way the existing D-M3U-1
# probe does), with an audit hook that reads the process's RLIMIT_DATA at
# every file the run opens and a wrapper that reads it at every line the run
# writes to stdout or stderr. The record goes to the file named by argv[1]
# once the verb has returned; the rest of argv is the helper's.
PROBE = r"""
import json, os, resource, runpy, sys
record_path, helper, argv = sys.argv[1], sys.argv[2], sys.argv[3:]
events = []
recording = [True]
def soft():
    return resource.getrlimit(resource.RLIMIT_DATA)[0]
def hook(event, args):
    if recording[0] and event == "open" and isinstance(args[0], str):
        events.append(["open", os.path.basename(args[0]), soft()])
sys.addaudithook(hook)
class Wrap:
    def __init__(self, name, real):
        self.name, self.real = name, real
    def write(self, text):
        if recording[0] and text:
            events.append([self.name, "", soft()])
        return self.real.write(text)
    def flush(self):
        return self.real.flush()
    def __getattr__(self, attr):
        return getattr(self.real, attr)
baseline = soft()
sys.stdout, sys.stderr = Wrap("stdout", sys.stdout), Wrap("stderr", sys.stderr)
sys.argv = ["omarchy-iptv"] + argv
code = None
try:
    runpy.run_path(helper, run_name="__main__")
except SystemExit as done:
    code = done.code
recording[0] = False
with open(record_path, "w", encoding="utf-8") as handle:
    json.dump({"baseline": baseline, "end": soft(), "code": code, "events": events}, handle)
"""

PROBE_LIMIT_MIB = 400


class LimitLiftedBeforeStatusTest(unittest.TestCase):
    """D-M3U-3 (lead's rule): the limit is lifted on EVERY exit path before
    the verb composes or writes its status or speaks. Observed at the sink:
    the soft RLIMIT_DATA at the moment the status file's temporary is opened,
    and at every write to stdout and stderr."""

    LIMIT = PROBE_LIMIT_MIB * 1024 * 1024

    def setUp(self):
        soft = resource.getrlimit(resource.RLIMIT_DATA)[0]
        if soft != resource.RLIM_INFINITY and soft <= self.LIMIT:
            self.skipTest("this process already runs under a data limit of %d bytes, so the verb's own "
                          "limit cannot be told apart from it" % soft)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.cache = os.path.join(self.dir, "cache")
        self.runs = 0

    def probe(self, *argv):
        self.runs += 1
        record = os.path.join(self.dir, "record-%d.json" % self.runs)
        env = dict(os.environ)
        env[LIMIT_ENV] = str(PROBE_LIMIT_MIB)
        env.pop("OMARCHY_IPTV_URL", None)
        done = subprocess.run([sys.executable, "-c", PROBE, record, str(HELPER), *argv],
                              capture_output=True, text=True, env=env, timeout=60)
        self.assertTrue(os.path.exists(record), done.stderr)
        with open(record, encoding="utf-8") as handle:
            result = json.load(handle)
        lines = done.stdout.strip().splitlines()
        result["status"] = json.loads(lines[-1]) if lines else None
        result["stderr"] = done.stderr
        return result

    def opens(self, result, stem):
        return [soft for kind, name, soft in result["events"] if kind == "open" and name.startswith(".tmp-" + stem)]

    def assert_spoken_unbounded(self, result, status_file):
        baseline = result["baseline"]
        status_opens = self.opens(result, status_file)
        self.assertEqual(len(status_opens), 1, result["events"])
        self.assertEqual(status_opens, [baseline],
                         "the status file was written under a limit of %r" % status_opens)
        spoken = [soft for kind, _, soft in result["events"] if kind in ("stdout", "stderr")]
        self.assertTrue(spoken, result["events"])
        self.assertEqual(set(spoken), {baseline}, "a line was printed under the limit: %r" % result["events"])
        self.assertEqual(result["end"], baseline)

    def assert_held_at(self, result, name):
        """The run DID hold the limit -- when it opened `name` -- so the
        assertions above are about a limit that was there to lift."""
        held = [soft for kind, file, soft in result["events"] if kind == "open" and (file == name or file.startswith(".tmp-" + name))]
        self.assertTrue(held, "%s was never opened: %r" % (name, result["events"]))
        self.assertIn(self.LIMIT, held, result["events"])

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_playlist_refusal_writes_its_status_after_the_limit_is_lifted(self):
        source = self.write("words.txt", "these are words, not a playlist\n")
        result = self.probe("playlist", "--url", source, "--cache-dir", self.cache)
        self.assertEqual(result["status"]["error"]["code"], "not_a_playlist", result["stderr"])
        self.assert_held_at(result, "words.txt")
        self.assert_spoken_unbounded(result, helper.PLAYLIST_STATUS_FILE)

    def test_playlist_success_writes_its_status_after_the_limit_is_lifted(self):
        result = self.probe("playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", self.cache)
        self.assertTrue(result["status"]["ok"], result["stderr"])
        # channels.json is the parse's own output and is written under it.
        self.assertEqual(self.opens(result, helper.CHANNELS_FILE), [self.LIMIT])
        self.assert_spoken_unbounded(result, helper.PLAYLIST_STATUS_FILE)

    def test_epg_refusal_writes_its_status_after_the_limit_is_lifted(self):
        source = self.write("words.xml", "these are words, not a guide\n")
        result = self.probe("epg", "--url", source, "--cache-dir", self.cache, "--force")
        self.assertFalse(result["status"]["ok"], result["stderr"])
        self.assert_held_at(result, "words.xml")
        self.assert_spoken_unbounded(result, helper.EPG_STATUS_FILE)

    def test_epg_refusal_with_a_cached_window_refreshes_under_it_and_speaks_after(self):
        first = self.probe("playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", self.cache)
        self.assertTrue(first["status"]["ok"], first["stderr"])
        second = self.probe("epg", "--url", str(FIXTURES / "epg-basic.xml"), "--cache-dir", self.cache, "--force")
        self.assertTrue(second["status"]["ok"], second["stderr"])
        self.assert_spoken_unbounded(second, helper.EPG_STATUS_FILE)
        self.assertEqual(self.opens(second, helper.EPG_NOW_FILE), [self.LIMIT])
        source = self.write("broken.xml", "these are words, not a guide\n")
        third = self.probe("epg", "--url", source, "--cache-dir", self.cache, "--force")
        self.assertFalse(third["status"]["ok"], third["stderr"])
        self.assertTrue(third["status"]["stale"], third["status"])
        # The cached window still refreshes epg-now.json, under the limit...
        self.assertEqual(self.opens(third, helper.EPG_NOW_FILE), [self.LIMIT])
        # ...and the refusal is written and spoken after it is lifted.
        self.assert_spoken_unbounded(third, helper.EPG_STATUS_FILE)

    def test_epg_now_only_without_a_cache_writes_its_status_after_the_limit_is_lifted(self):
        result = self.probe("epg", "--now-only", "--cache-dir", self.cache)
        self.assertEqual(result["status"]["error"]["code"], "no_cache", result["stderr"])
        self.assert_spoken_unbounded(result, helper.EPG_STATUS_FILE)


class LimitLiftedInProcessTest(unittest.TestCase):
    """The same rule through the shipping verbs called in this process, with
    an injected HelperError: the order of the release, the status write and
    the first line printed, read off the calls themselves."""

    def order(self, verb, target, argv):
        events = []
        real_write = helper.write_text_atomic
        held = {"limit": 1 << 30, "previous": (resource.RLIM_INFINITY, resource.RLIM_INFINITY)}

        def write(path, text, *rest, **kw):
            events.append("write " + os.path.basename(path))
            return real_write(path, text, *rest, **kw)

        out, err = io.StringIO(), io.StringIO()

        class Spy:
            def __init__(self, name, real):
                self.name, self.real = name, real

            def write(self, text):
                if text:
                    events.append(self.name)
                return self.real.write(text)

            def flush(self):
                return self.real.flush()

        with mock.patch.object(helper, "limit_memory", return_value=held), \
                mock.patch.object(helper, "release_memory_limit", side_effect=lambda h: events.append("release")), \
                mock.patch.object(helper, "write_text_atomic", side_effect=write), \
                mock.patch.object(helper, target, side_effect=helper.HelperError("bad_input", "refused")), \
                contextlib.redirect_stdout(Spy("stdout", out)), contextlib.redirect_stderr(Spy("stderr", err)):
            code = helper.main([verb] + argv)
        self.assertEqual(code, 1, out.getvalue() + err.getvalue())
        return events

    def test_the_release_comes_before_every_status_write_and_every_line(self):
        for verb, target, argv, status_file in (
                ("playlist", "parse_m3u", ["--url", str(FIXTURES / "basic.m3u")], helper.PLAYLIST_STATUS_FILE),
                ("epg", "parse_xmltv", ["--url", str(FIXTURES / "epg-basic.xml"), "--force"], helper.EPG_STATUS_FILE)):
            with self.subTest(verb=verb), tempfile.TemporaryDirectory() as cache:
                events = self.order(verb, target, ["--cache-dir", cache] + argv)
                self.assertIn("release", events, events)
                first = events.index("release")
                self.assertLess(first, events.index("write " + status_file), events)
                for spoken in ("stdout", "stderr"):
                    if spoken in events:
                        self.assertLess(first, events.index(spoken), events)


# ---------------------------------------------------------------- D-M3U-4

# What each kind reads for ONE, written out (the copy is the thing pinned).
SINGULAR = {
    "name": "1 channel name cut to 512 characters",
    "tvgName": "1 tvg-name value cut to 512 characters",
    "groupText": "1 group value cut to 512 characters",
    "group": "1 group name cut to 128 characters",
    "groupCount": "1 channel listed in more than 16 groups kept the first 16",
    "tvgId": "1 tvg-id value longer than 256 characters dropped",
    "chno": "1 channel number longer than 32 characters dropped",
    "logo": "1 logo URL longer than 2048 characters dropped",
    "option": "1 option or header dropped: a name over 64 or a value over 1024 characters",
    "optionCount": "1 option or header dropped: more than 16 on one channel",
    "url": "1 entry skipped: stream URL longer than 4096 characters",
    "epgHint": "1 EPG hint longer than 2048 characters dropped",
    "warnings": "1 more warning like the ones above not listed",
}
PLURAL = {
    "name": "3 channel names cut to 512 characters",
    "tvgName": "3 tvg-name values cut to 512 characters",
    "groupText": "3 group values cut to 512 characters",
    "group": "3 group names cut to 128 characters",
    "groupCount": "3 channels listed in more than 16 groups kept the first 16",
    "tvgId": "3 tvg-id values longer than 256 characters dropped",
    "chno": "3 channel numbers longer than 32 characters dropped",
    "logo": "3 logo URLs longer than 2048 characters dropped",
    "option": "3 options or headers dropped: a name over 64 or a value over 1024 characters",
    "optionCount": "3 options or headers dropped: more than 16 on one channel",
    "url": "3 entries skipped: stream URL longer than 4096 characters",
    "epgHint": "3 EPG hints longer than 2048 characters dropped",
    "warnings": "3 more warnings like the ones above not listed",
}


class CountedSentenceTest(unittest.TestCase):
    def test_every_kind_in_the_bound_table_reads_for_one_and_for_many(self):
        kinds = [entry[0] for entry in helper.M3U_CUT_WARNINGS]
        self.assertEqual(sorted(kinds), sorted(SINGULAR))
        for kind in kinds:
            with self.subTest(kind=kind):
                self.assertEqual(helper.bound_warnings({kind: 1}), [SINGULAR[kind]])
                self.assertEqual(helper.bound_warnings({kind: 3}), [PLURAL[kind]])

    def test_the_parse_reads_its_own_counts_for_one(self):
        one = helper.parse_m3u("#EXTM3U\n#EXTINF:-1,%s\nhttp://x.test/a\n" % ("n" * 600))
        self.assertIn(SINGULAR["name"], one["warnings"])
        two = helper.parse_m3u("#EXTM3U\n" + "".join("#EXTINF:-1,%s\nhttp://x.test/%d\n" % ("n" * 600, i) for i in range(2)))
        self.assertIn("2 channel names cut to 512 characters", two["warnings"])

    def test_every_other_counted_sentence_of_the_parse_reads_for_one_and_for_many(self):
        def warnings(text):
            return helper.parse_m3u(text)["warnings"]
        self.assertEqual(warnings("#EXTM3U\n#EXTINF:-1,A\nftp://x.test/a\n"),
                         ["1 entry skipped: unsupported URL scheme"])
        self.assertEqual(warnings("#EXTM3U\n#EXTINF:-1,A\nftp://x.test/a\n#EXTINF:-1,B\nftp://x.test/b\n"),
                         ["2 entries skipped: unsupported URL scheme"])
        self.assertEqual(warnings("#EXTM3U\nhttp://x.test/a\n#EXTINF:-1,A\nhttp://x.test/b\n"),
                         ["1 URL line without #EXTINF skipped"])
        self.assertEqual(warnings("#EXTM3U\nhttp://x.test/a\nhttp://x.test/c\n#EXTINF:-1,A\nhttp://x.test/b\n"),
                         ["2 URL lines without #EXTINF skipped"])
        self.assertEqual(warnings("#EXTM3U\n#EXTINF:-1,A\nhttp://x.test/a\n#EXTINF:-1,B\n"),
                         ["1 #EXTINF entry without a URL skipped"])
        self.assertEqual(warnings("#EXTM3U\n#EXTINF:-1,B\n#EXTINF:-1,A\nhttp://x.test/a\n#EXTINF:-1,C\n"),
                         ["2 #EXTINF entries without a URL skipped"])
        three = "#EXTM3U\n" + "".join("#EXTINF:-1 group-title=\"G%d\",C%d\nhttp://x.test/%d\n" % (i, i, i) for i in range(3))
        with mock.patch.object(helper, "MAX_CHANNELS", 2):
            self.assertEqual(warnings(three), ["truncated to 2 channels (1 entry skipped)"])
        with mock.patch.object(helper, "MAX_CHANNELS", 1):
            self.assertEqual(warnings(three), ["truncated to 1 channel (2 entries skipped)"])
        with mock.patch.object(helper, "MAX_GROUPS", 2):
            self.assertEqual(warnings(three), ["group count capped at 2; 1 channel listed under %s" % helper.UNGROUPED])
        with mock.patch.object(helper, "MAX_GROUPS", 1):
            self.assertEqual(warnings(three), ["group count capped at 1; 2 channels listed under %s" % helper.UNGROUPED])


# ---------------------------------------------------------------- rule 15

class TrackReplyBoundTest(unittest.TestCase):
    """player.tracks: the list and its three free-text fields are the
    stream's. Called through the shipping verb, with the row cap lowered."""

    def tracks_reply(self, track_list):
        class Client:
            def try_command(self, *command):
                if command[:2] == ("get_property", "track-list"):
                    return True, track_list
                return True, None

            def close(self):
                pass

        args = helper.build_parser().parse_args(["player", "tracks", "--socket", "/nonexistent/sock"])
        out = io.StringIO()
        with mock.patch.object(helper, "find_player", return_value=[{"pid": 1}]), \
                mock.patch.object(helper, "probe_client", return_value=Client()), \
                contextlib.redirect_stdout(out):
            code = helper.player_tracks(args)
        self.assertEqual(code, 0)
        return json.loads(out.getvalue().strip().splitlines()[-1])

    def rows(self, count):
        return [{"id": i + 1, "type": "audio" if i % 2 else "sub", "lang": "eng", "title": "Track %d" % i,
                 "codec": "aac"} for i in range(count)]

    def test_the_rows_are_capped_and_the_rest_counted(self):
        with mock.patch.object(helper, "TRACK_MAX_ROWS", 2):
            payload = self.tracks_reply(self.rows(5))
        self.assertEqual([row["id"] for row in payload["tracks"]], [1, 2])
        self.assertEqual(payload["tracksOmitted"], 3)

    def test_an_ordinary_list_has_no_omitted_field(self):
        payload = self.tracks_reply(self.rows(3))
        self.assertEqual(len(payload["tracks"]), 3)
        self.assertNotIn("tracksOmitted", payload)

    def test_each_free_text_field_is_cut_to_its_cap(self):
        row = {"id": 1, "type": "audio", "title": "a title of forty characters, give or take",
               "lang": "english please", "codec": "a codec name"}
        with mock.patch.object(helper, "TRACK_MAX_TITLE", 7), mock.patch.object(helper, "TRACK_MAX_LANG", 3), \
                mock.patch.object(helper, "TRACK_MAX_CODEC", 5):
            payload = self.tracks_reply([row])
        track = payload["tracks"][0]
        self.assertEqual((track["title"], track["lang"], track["codec"]), ("a title", "eng", "a cod"))

    def test_the_cut_comes_after_the_redaction(self):
        """The cap falls INSIDE the userinfo (15 characters is
        `http://user:SEC`), which is the only place the order shows: cut
        first and the redactor reads `user` as the host and publishes it
        (the round-1 recheck of lane-bounds-p found this test cut at 30,
        where both orders give the same answer, so it could not go red).
        Seen red with track_text reversed to redact_urls(value[:limit])."""
        row = {"id": 1, "type": "audio", "title": "http://user:SECRETPW@h.test/path/to/a/stream"}
        with mock.patch.object(helper, "TRACK_MAX_TITLE", 15):
            payload = self.tracks_reply([row])
        self.assertEqual(payload["tracks"][0]["title"], "http://h.test")
        self.assertNotIn("user", payload["tracks"][0]["title"])


class FirstLoadReasonBoundTest(unittest.TestCase):
    """player start: the first-load reason is mpv's last error line."""

    class Client:
        def __init__(self, events):
            self.batches = [events]

        def drain_events(self, deadline):
            return self.batches.pop(0) if self.batches else None

    def test_the_reason_is_cut_to_its_cap(self):
        text = "the server said something rather long about why it would not play"
        client = self.Client([{"event": "log-message", "level": "error", "text": text},
                              {"event": "end-file", "reason": "error", "playlist_entry_id": 4}])
        with mock.patch.object(helper, "FIRST_LOAD_REASON_MAX", 10):
            verdict = helper.observe_first_load(client, 4, 5.0)
        # D-PLY-36: and the reply says it was an end-file (this one carries no
        # file_error, so its fileError is empty).
        self.assertEqual(verdict, {"state": "failed", "reason": "the server", "ended": "end-file", "fileError": ""})

    def test_a_closed_player_reason_is_cut_too(self):
        client = self.Client([{"event": "log-message", "level": "fatal", "text": "fatal words from the demuxer"}])
        with mock.patch.object(helper, "FIRST_LOAD_REASON_MAX", 5):
            verdict = helper.observe_first_load(client, 4, 5.0)
        self.assertEqual(verdict, {"state": "failed", "reason": "fatal", "ended": "closed"})

    def test_an_ordinary_reason_is_untouched(self):
        client = self.Client([{"event": "log-message", "level": "error", "text": "HTTP error 403 Forbidden"},
                              {"event": "end-file", "reason": "error", "playlist_entry_id": 4}])
        verdict = helper.observe_first_load(client, 4, 5.0)
        self.assertEqual(verdict, {"state": "failed", "reason": "HTTP error 403 Forbidden", "ended": "end-file", "fileError": ""})


class InternalErrorBoundTest(unittest.TestCase):
    """main()'s answer to a bug is part of every verb's reply; the
    exception's text is the one part of it no verb composes."""

    def test_the_message_and_the_traceback_are_cut_with_the_caps_lowered(self):
        text = "an exception that quotes its input: " + "q" * 200
        with mock.patch.object(helper, "cmd_clipboard", side_effect=ValueError(text)), \
                mock.patch.object(helper, "INTERNAL_MESSAGE_MAX", 40), \
                mock.patch.object(helper, "INTERNAL_TRACE_MAX", 120):
            code, payload, _, stderr = run_main(["clipboard"])
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "internal")
        self.assertEqual(payload["error"]["message"], ("ValueError: " + text)[:40])
        self.assertLessEqual(len(stderr), 120 + len("\n[%d characters not shown]\n" % 10 ** 6))
        self.assertIn("characters not shown]", stderr)
        # The tail is kept: the last line of a traceback names the exception.
        self.assertTrue(stderr.rstrip().endswith("q" * 10), stderr)

    def test_an_ordinary_bug_report_is_whole(self):
        with mock.patch.object(helper, "cmd_clipboard", side_effect=ValueError("short")):
            code, payload, _, stderr = run_main(["clipboard"])
        self.assertEqual(payload["error"]["message"], "ValueError: short")
        self.assertIn("Traceback", stderr)
        self.assertNotIn("characters not shown", stderr)

    def test_the_cut_comes_after_the_redaction(self):
        """As the track test: 26 characters of `ValueError: http://user:...`
        end inside the userinfo, so cutting first leaves `http://user` for
        the redactor to publish as a host. The traceback is cut at a cap
        inside the userinfo too. Seen red with both lines of main()
        reversed to redact_urls(bounded_text(...))."""
        text = "http://user:SECRETPW@h.test/" + "p" * 100
        with mock.patch.object(helper, "cmd_clipboard", side_effect=ValueError(text)), \
                mock.patch.object(helper, "INTERNAL_MESSAGE_MAX", 26), \
                mock.patch.object(helper, "INTERNAL_TRACE_MAX", 52):
            _, payload, _, stderr = run_main(["clipboard"])
        self.assertEqual(payload["error"]["message"], "ValueError: http://h.test")
        self.assertNotIn("http://user", payload["error"]["message"] + stderr)
        self.assertNotIn("SECRET", payload["error"]["message"] + stderr)
        # The traceback's tail is the exception line, redacted whole.
        self.assertTrue(stderr.rstrip().endswith("ValueError: http://h.test"), stderr)

    def test_the_counted_line_reads_right_for_one(self):
        """The round-1 recheck of lane-bounds-p: "[1 characters not shown]"."""
        self.assertEqual(helper.bounded_text("a" * 17, 16, keep_tail=True),
                         "aaaaaaaa\n[1 character not shown]\naaaaaaaa")
        self.assertEqual(helper.bounded_text("a" * 19, 16, keep_tail=True),
                         "aaaaaaaa\n[3 characters not shown]\naaaaaaaa")
        self.assertEqual(helper.bounded_text("a" * 17, 16), "a" * 16)


if __name__ == "__main__":
    unittest.main()
