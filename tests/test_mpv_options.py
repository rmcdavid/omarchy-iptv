"""D-SINK-43..46 (owner, 2026-10-29): every mpv option is classified, and the
helper's reserved set and trailing pin block are what the classification says.

tests/fixtures/mpv-options.json classifies every option base the installed
mpv lists (allowed, reserved, pinned, warned, base) and FFmpeg's TLS protocol
keys. This file pins the helper to it by CALLING the shipping filter and the
shipping argv builder (rule 12) -- tests/Model.test.js pins the JavaScript
mirror to the same file -- and runs scripts/check-mpv-options.py, the gate
that holds the fixture against the installed mpv, over saved listings, so the
gate is seen red for each thing it is there to catch (rule 14).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

from helper_loader import load_helper

helper = load_helper()
ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "mpv-options.json"
GATE = ROOT / "scripts" / "check-mpv-options.py"
SOCK = "/run/user/1000/omarchy-iptv/mpv.sock"


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def base_of(name):
    return re.sub(r"-(add|append|set|pre|clr|del|remove|toggle)$", "", name.split("=", 1)[0])


class ClassificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load()
        cls.options = cls.fixture["options"]

    def klass(self, *wanted):
        return {n for n, e in self.options.items() if e["class"] in wanted}

    def test_the_refused_set_is_the_reserved_and_pinned_classes(self):
        """MPV_RESERVED is exactly what the fixture refuses: the `reserved`
        class and the `pinned` one (a pinned option is refused as a token too,
        the honest half), except a key-pinned list, whose other keys stay the
        user's. `--{` and `--}` are refused by SHAPE, so they are not names in
        the set; that is asserted rather than assumed."""
        refused = {n for n, e in self.options.items()
                   if e["class"] == "reserved" or (e["class"] == "pinned" and "pinKey" not in e)}
        by_shape = {n for n in refused if not helper.MPV_ARG_RE.match(n + "=x")}
        self.assertEqual(by_shape, {"--{", "--}"})
        self.assertEqual(set(helper.MPV_RESERVED), refused - by_shape)
        for name in sorted(refused):
            with self.subTest(name=name):
                self.assertEqual(helper.filter_mpv_args([name + "=x"]), ([], [name + "=x"]))

    def test_the_pin_block_is_the_pinned_class_in_the_fixtures_order(self):
        block = self.fixture["pinBlock"]
        self.assertEqual(block[0], "--watch-later-dir={watchLater}")
        self.assertEqual(list(helper.MPV_PIN_BLOCK), block[1:])
        pinned = {n for n, e in self.options.items() if e["class"] == "pinned" and e["type"] != "alias"}
        self.assertEqual({base_of(t) for t in block}, pinned)
        for name in pinned:
            self.assertIn(self.options[name]["pin"], block, name)
        dirs = helper.player_dirs(SOCK, "/home/u/.local/state/omarchy-iptv")
        self.assertEqual(helper.mpv_pin_block(dirs), [t.format(watchLater=dirs["watchLater"]) for t in block])
        # The last element is D-SINK-13's layer 2 and stays last.
        self.assertEqual(block[-1], helper.MPV_TLS_VERIFY)

    def test_the_model_spells_the_same_pin_block(self):
        """Rule 13 across languages: the JavaScript literal is read here and
        the node suite asserts the same fixture with Model.MPV_PIN_BLOCK."""
        text = (ROOT / "model" / "build.mjs").read_text(encoding="utf-8")
        body = re.search(r"var MPV_PIN_BLOCK = \[(.*?)\n\]", text, re.S).group(1)
        tokens = re.findall(r'^\s+"([^"]+)",?', body, re.M)
        self.assertEqual(tokens + ["--tls-verify=yes"], list(helper.MPV_PIN_BLOCK))
        self.assertIn("MPV_TLS_VERIFY", body.strip().splitlines()[-1])

    def test_every_pin_lands_after_every_user_token(self):
        """The layer-2 shape for every pin: whatever the user's tokens say
        (here, the contrary value of each pinned option, injected PAST the
        filter so the position alone decides), the last occurrence of each
        pinned option is the pin block's."""
        contrary = ["--%s=x" % n[2:] for n in self.klass("pinned") if self.options[n]["type"] != "alias"]
        dirs = helper.player_dirs(SOCK, "/home/u/.local/state/omarchy-iptv")
        # D-SINK-47: the tokens reach mpv through the --include file, which mpv
        # parses at its position (measured); this is the sequence it applies.
        launch = helper.mpv_launch_argv(SOCK, contrary, dirs)
        at = launch.index("--include=" + dirs["mpvArgs"])
        argv = launch[:at] + contrary + launch[at + 1:]
        tail = helper.mpv_pin_block(dirs)
        self.assertEqual(argv[-len(tail):], tail)
        last_user = max(argv.index(t) for t in contrary)
        # An option the block pins with SEVERAL tokens (input-commands: -clr
        # then the paste key; demuxer-lavf-o: two keys, 2026-10-29) ends the
        # argv with exactly those tokens, in the block's order.
        for base in {base_of(t) for t in tail}:
            ours = [t for t in tail if base_of(t) == base]
            positions = [i for i, t in enumerate(argv) if base_of(t) == base]
            self.assertEqual([argv[i] for i in positions[-len(ours):]], ours, base)
            self.assertGreater(positions[-len(ours)], last_user, base)

    def test_the_base_section_holds_only_what_the_fixture_lets_the_plugin_set_first(self):
        argv = helper.mpv_launch_argv(SOCK, [])
        base = argv[1:len(argv) - len(helper.mpv_pin_block(helper.player_dirs(SOCK)))]
        names = {base_of(t) for t in base}
        for name in names:
            self.assertIn(self.options[name]["class"], ("base", "reserved", "pinned", "warned"), name)
        wanted = {n for n, e in self.options.items() if e["class"] == "base" and e["type"] != "alias"}
        self.assertEqual(wanted - names, set())
        # And a `base` option is NOT refused: a user's later token wins.
        for name in sorted(wanted):
            self.assertEqual(helper.filter_mpv_args([name + "=x"])[1], [], name)

    def test_the_warned_class_is_the_handoff_and_disk_sets(self):
        # 2026-10-29 (lane-p1b): an option of another class may warn as well
        # (`warn`): --script-opts is key-pinned now (D-SINK-52) and still warns
        # for ytdl (PO-10), --demuxer-lavf-o warns for http_proxy (D-SINK-59);
        # --rtsp-transport joins the warned class (D-SINK-53).
        warned = self.klass("warned") | {n for n, e in self.options.items() if e.get("warn")}
        self.assertEqual(warned, set(helper.MPV_HANDOFF) | set(helper.MPV_HANDOFF_SCRIPT_OPTS)
                         | {"--ytdl"} | set(helper.MPV_DISK_WARN) | set(helper.MPV_LISTEN_WARN)
                         | {helper.MPV_DEMUXER_OPTS})
        values = {"--ytdl": "yes", "--cache-on-disk": "yes", "--rtsp-transport": "udp",
                  "--demuxer-lavf-o": "http_proxy=http://p:1"}
        for name in sorted(warned):
            value = values.get(name, "ytdl_hook-x=1")
            self.assertNotEqual(helper.mpv_arg_warnings([name + "=" + value]), [], name)
            self.assertEqual(helper.filter_mpv_args([name + "=" + value])[1], [], name)

    def test_every_alias_takes_its_targets_class_and_a_refused_alias_is_refused(self):
        aliases = {n: e for n, e in self.options.items() if e["type"] == "alias"}
        self.assertGreaterEqual(len(aliases), 31)
        for name, entry in aliases.items():
            target = self.options[base_of(entry["alias"])]
            self.assertEqual(entry["class"], target["class"], name)
        # D-SINK-2 in the other direction: mpv's own alias for a reserved name.
        self.assertEqual(self.options["--watch-later-directory"]["alias"], "--watch-later-dir")
        self.assertIn("--watch-later-directory", helper.MPV_RESERVED)

    def test_string_shaped_options_carry_a_reason(self):
        stringy = ("String", "String list", "Key/value list", "Object settings list", "alias", "removed", "Print")
        for name, entry in self.options.items():
            if entry["type"] in stringy or entry.get("file"):
                self.assertTrue(entry.get("why"), name)

    def test_the_standing_rulings_hold(self):
        """PO-5, PO-10, D-PLY-5, D-SINK-13 layer 4, PO-11, M5-01, D-PLY-27:
        the classification may not quietly overturn one. These are the lines
        that should go red if someone 'completes' the list."""
        o = self.options
        self.assertEqual(o["--ytdl"]["class"], "warned")
        # The owner's decision of 2026-10-29 (D-SINK-52: pin and refuse) moved
        # --script-opts from `warned` to KEY-pinned: one OSC key is the pin
        # block's, a token setting an OSC command or carrying ${ is refused,
        # and PO-10's ytdl handoff warning stands, so it is not refused as a
        # name and it still warns.
        self.assertEqual(o["--script-opts"]["class"], "pinned")
        self.assertIn("pinKey", o["--script-opts"])
        self.assertNotIn("--script-opts", helper.MPV_RESERVED)
        self.assertNotEqual(helper.mpv_arg_warnings(["--script-opts=ytdl_hook-ytdl_path=/x"]), [])
        self.assertEqual(o["--profile"]["class"], "allowed")
        self.assertEqual(o["--tls-ca-file"]["class"], "allowed")
        self.assertEqual(o["--screenshot-dir"]["class"], "base")
        self.assertEqual(o["--cache-on-disk"]["class"], "warned")
        self.assertEqual(o["--gpu-sw"]["class"], "base")
        self.assertEqual(o["--demuxer-lavf-o"]["class"], "pinned")
        self.assertEqual(o["--demuxer-lavf-o"]["pinKey"], "tls_verify=1")
        # The owner's decision 3: only the select menu goes -- and, the
        # owner's decision on D-SINK-61 (2026-10-29), the console with it,
        # mpv's alias included, and on D-SINK-67 (2026-10-29, "yes" to
        # turning stats off), the stats overlay. Commands, the context menu,
        # positioning and the OSC stay.
        for name in ("--load-context-menu", "--load-commands", "--load-positioning", "--osc"):
            self.assertEqual(o[name]["class"], "allowed", name)
        for name in ("--load-select", "--load-console", "--load-osd-console", "--prefetch-playlist",
                     "--load-stats-overlay"):
            self.assertEqual(o[name]["class"], "pinned", name)

    def test_the_format_keys_are_the_helpers_whitelist_and_the_filters_words(self):
        """D-SINK-55 (2026-10-29): the demuxer's protocol whitelist is pinned
        (the helper's MPV_DEMUXER_WHITELIST_KEY, read back as exactly
        MPV_PROTOCOL_WHITELIST) and a blacklist is forbidden, both refused in
        a token by the filter's words. lane-p1c (2026-10-29): the format list
        the same way (D-SINK-62, MPV_DEMUXER_FORMATS_KEY and
        MPV_FORMAT_WHITELIST), and the `removed` keys are the read-back's
        DEMUXER_FORMAT_FORBIDDEN (D-SINK-64)."""
        fmt = self.fixture["ffmpegFormat"]["options"]
        self.assertEqual({k for k, c in fmt.items() if c == "pinned"},
                         {helper.MPV_DEMUXER_WHITELIST_KEY, helper.MPV_DEMUXER_FORMATS_KEY})
        self.assertEqual({k for k, c in fmt.items() if c == "removed"}, set(helper.DEMUXER_FORMAT_FORBIDDEN))
        self.assertEqual(set(fmt.values()), {"pinned", "forbidden", "removed"})
        for key, wanted in ((helper.MPV_DEMUXER_WHITELIST_KEY, helper.MPV_PROTOCOL_WHITELIST),
                            (helper.MPV_DEMUXER_FORMATS_KEY, helper.MPV_FORMAT_WHITELIST)):
            self.assertIn("--demuxer-lavf-o-append=%s=%s" % (key, wanted), self.fixture["pinBlock"])
        for key in fmt:
            for token in ("--demuxer-lavf-o=%s=file" % key, "--demuxer-lavf-o-append=%s=http" % key,
                          '--demuxer-lavf-o="%s"=x' % key):
                self.assertEqual(helper.filter_mpv_args([token]), ([], [token]), token)

    def test_ffmpeg_tls_keys_are_the_helpers_two_sets_and_the_filters_words(self):
        tls = self.fixture["ffmpegTls"]
        self.assertEqual(set(tls["words"]), set(helper.MPV_DEMUXER_TLS_WORDS))
        self.assertEqual({k for k, c in tls["options"].items() if c == "pinned"}, set(helper.DEMUXER_TLS_ON))
        self.assertEqual({k for k, c in tls["options"].items() if c == "forbidden"}, set(helper.DEMUXER_TLS_FORBIDDEN))
        for key, klass in tls["options"].items():
            token = "--demuxer-lavf-o=%s=1" % key
            refused = helper.filter_mpv_args([token])[1] == [token]
            self.assertEqual(refused, klass != "allowed" or any(w in key for w in tls["words"]), key)

    def test_the_counts_the_fixture_reports_are_its_own(self):
        counts = {}
        for entry in self.options.values():
            counts[entry["class"]] = counts.get(entry["class"], 0) + 1
        self.assertEqual(counts, self.fixture["counts"])
        self.assertEqual(len(self.options), self.fixture["mpv"]["listed"])


class GateTest(unittest.TestCase):
    """scripts/check-mpv-options.py, over saved listings: green on the
    fixture's own shape, red on each thing it exists to catch."""

    LISTING = (" --load-select                    Flag (default: yes)\n"
               " --watch-later-dir                String (default: ) [file]\n"
               " --watch-later-directory          alias for watch-later-dir\n")
    FFMPEG = ("tls AVOptions:\n  -tls_verify        <boolean>    ED......... Verify (default true)\n"
              "  -verifyhost        <string>     ED......... Verify against a specific hostname\n")

    def gate(self, fixture, listing=None, ffmpeg=None, env=None):
        with tempfile.TemporaryDirectory() as tmp:
            fx = os.path.join(tmp, "fixture.json")
            with open(fx, "w", encoding="utf-8") as fh:
                json.dump(fixture, fh)
            argv = [sys.executable, "-I", str(GATE), "--fixture", fx]
            if listing is not None:
                path = os.path.join(tmp, "listing.txt")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(listing)
                argv += ["--listing", path]
            if ffmpeg is not None:
                path = os.path.join(tmp, "ffmpeg.txt")
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(ffmpeg)
                argv += ["--ffmpeg-listing", path]
            done = subprocess.run(argv, capture_output=True, text=True, timeout=60, env=env)
            return done.returncode, done.stdout

    def small(self):
        full = load()
        keep = ("--load-select", "--watch-later-dir", "--watch-later-directory")
        return dict(full, options={k: full["options"][k] for k in keep},
                    ffmpegTls=dict(full["ffmpegTls"], options={"tls_verify": "pinned", "verifyhost": "forbidden"}))

    def test_green_when_everything_listed_is_classified(self):
        code, out = self.gate(self.small(), self.LISTING, self.FFMPEG)
        self.assertEqual(code, 0, out)
        self.assertIn("mpv option guard: 3 options classified", out)

    def test_red_on_an_option_the_fixture_does_not_classify(self):
        code, out = self.gate(self.small(), self.LISTING + " --brand-new-option         String (default: )\n", self.FFMPEG)
        self.assertEqual(code, 1, out)
        self.assertIn("RED  --brand-new-option: not classified", out)

    def test_red_on_a_deleted_entry(self):
        fixture = self.small()
        del fixture["options"]["--load-select"]
        code, out = self.gate(fixture, self.LISTING, self.FFMPEG)
        self.assertEqual(code, 1, out)
        self.assertIn("RED  --load-select: not classified", out)

    def test_red_on_a_type_or_alias_that_moved(self):
        listing = self.LISTING.replace("Flag (default: yes)", "String (default: )").replace(
            "alias for watch-later-dir", "alias for screenshot-dir")
        code, out = self.gate(self.small(), listing, self.FFMPEG)
        self.assertEqual(code, 1, out)
        self.assertIn("--load-select: the fixture says Flag, this mpv says String", out)
        self.assertIn("--watch-later-directory: an alias of --screenshot-dir here", out)

    def test_red_on_an_alias_classified_apart_from_its_target(self):
        fixture = self.small()
        fixture["options"]["--watch-later-directory"]["class"] = "allowed"
        code, out = self.gate(fixture, self.LISTING, self.FFMPEG)
        self.assertEqual(code, 1, out)
        self.assertIn("alias of --watch-later-dir but classified allowed, not pinned", out)

    def test_red_on_a_string_option_with_no_reason(self):
        fixture = self.small()
        del fixture["options"]["--watch-later-dir"]["why"]
        code, out = self.gate(fixture, self.LISTING, self.FFMPEG)
        self.assertEqual(code, 1, out)
        self.assertIn("--watch-later-dir: a String option needs a one-line `why`", out)

    def test_red_on_an_ffmpeg_tls_key_nobody_classified_or_the_filter_cannot_see(self):
        code, out = self.gate(self.small(), self.LISTING, self.FFMPEG + "  -new_trust     <string>     ED......... x\n")
        self.assertEqual(code, 1, out)
        self.assertIn("ffmpeg tls new_trust: not classified", out)
        fixture = self.small()
        fixture["ffmpegTls"]["options"]["new_trust"] = "forbidden"
        code, out = self.gate(fixture, self.LISTING, self.FFMPEG)
        self.assertEqual(code, 1, out)
        self.assertIn("the token filter's words", out)

    def test_an_option_this_mpv_lacks_is_a_note_not_red(self):
        code, out = self.gate(self.small(), self.LISTING.splitlines(True)[0], self.FFMPEG)
        self.assertEqual(code, 0, out)
        self.assertIn("NOTE the fixture names 2 option(s) this mpv lacks", out)

    def test_no_mpv_is_77_and_says_so(self):
        env = dict(os.environ, PATH="/nonexistent")
        code, out = self.gate(self.small(), None, self.FFMPEG, env=env)
        self.assertEqual(code, 77, out)
        self.assertIn("SKIP mpv option guard", out)

    def test_the_shipped_fixture_passes_its_own_rules(self):
        code, out = self.gate(load(), "".join(
            " %s  %s\n" % (n, ("alias for %s" % e["alias"]) if e["type"] == "alias" else
                           ("removed [deprecated]" if e["type"] == "removed" else
                            ("Choices: a b" if e["type"] == "Choices" else e["type"] + " (default: )")))
            for n, e in load()["options"].items()), self.FFMPEG)
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
