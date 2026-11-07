"""D-HOST-13 (2026-11-06): the system-wide mpv configuration the player reads.

omarchy-settings 4.5.0-3 ships /etc/mpv/mpv.conf, a package-owned config
layer mpv 0.41.0 reads before the user's own (its sysconfdir is /etc/mpv):
one line, `hwdec=auto-safe`. The plugin passes neither --no-config nor
--hwdec, so since 4.5.0 every player the plugin starts decodes in hardware
where mpv's own default was none; the owner accepted that. `hwdec` is
classified "allowed" in tests/fixtures/mpv-options.json, so it opens no sink.

What nothing watched until now is the LAYER: a later omarchy-settings could
put a D-SINK-44-class item there -- a `[protocol.*]` or `profile-cond`
profile, `player-operation-mode`, an `include`, or a reserved or pinned
option -- and no check would go red. This one does: it parses the system
mpv.conf (if present) and fails on any option there that the fixture does
not classify "allowed" (an unclassified one included), and on ANY profile
section, whatever it holds; and it fails when the system mpv directory
gains an entry beside mpv.conf and scripts/ (an input.conf binding can draw
`${path}` on the picture), or scripts/ gains one beside mpris.so, which
predates 4.5.0 and which the pinned --load-scripts=no keeps out. A red here
after an Omarchy update is a re-measurement request, not a plugin defect.

The option's base is decided by the SHIPPING helper's mpv_option_base (rule
12), with a `no-` flag form read as its option, as the helper's own filter
reads it. OMARCHY_SYSTEM_MPV_DIR points the test at a scratch directory,
which is how it was proven red (a reserved option, a pinned option, an
unclassified name, a profile section, an extra file).
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from helper_loader import load_helper  # noqa: E402

SYSTEM = os.environ.get("OMARCHY_SYSTEM_MPV_DIR", "/etc/mpv")
FIXTURE = os.path.join(HERE, "fixtures", "mpv-options.json")

# What the system mpv directory held on 2026-11-06 (omarchy-settings 4.5.0-3
# for mpv.conf; scripts/mpris.so is mpv-mpris's, from before the upgrade).
KNOWN_ENTRIES = {"mpv.conf", "scripts"}
KNOWN_SCRIPTS = {"mpris.so"}


def parse_conf(text):
    """[(line, section or None, name, value)] for a mpv config file, and the
    profile sections it opens. mpv's grammar: `#` comments, `[name]` opens a
    profile, `name=value` or a bare `name` (a flag set to yes); a leading
    `--` is tolerated."""
    entries, sections = [], []
    section = None
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            sections.append((n, section))
            continue
        name, sep, value = line.partition("=")
        name = name.strip()
        if name.startswith("--"):
            name = name[2:]
        entries.append((n, section, name, value.strip() if sep else None))
    return entries, sections


class SystemMpvConfCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.helper = load_helper()
        with open(FIXTURE, encoding="utf-8") as fh:
            cls.options = json.load(fh)["options"]

    def classify(self, name):
        """The fixture's class for a config-file option name, or None."""
        flag = "--" + name
        for candidate in (flag, self.helper.mpv_option_base(flag)):
            if candidate in self.options:
                return self.options[candidate]["class"]
        if name.startswith("no-"):
            bare = "--" + name[3:]
            for candidate in (bare, self.helper.mpv_option_base(bare)):
                if candidate in self.options:
                    return self.options[candidate]["class"]
        return None

    def test_the_classifier_reads_the_names_a_config_file_uses(self):
        self.assertEqual("allowed", self.classify("hwdec"))
        self.assertEqual("reserved", self.classify("include"))
        self.assertEqual("pinned", self.classify("no-tls-verify"))
        self.assertEqual("pinned", self.classify("stream-lavf-o-append"))
        self.assertIsNone(self.classify("not-an-mpv-option"))
        entries, sections = parse_conf("# c\nhwdec = auto-safe\n--fs\n[protocol.https]\ntls-verify=no\n")
        self.assertEqual([(2, None, "hwdec", "auto-safe"), (3, None, "fs", None), (5, "protocol.https", "tls-verify", "no")], entries)
        self.assertEqual([(4, "protocol.https")], sections)

    def test_the_system_mpv_conf_sets_only_allowed_options_and_no_profile(self):
        path = os.path.join(SYSTEM, "mpv.conf")
        if not os.path.isfile(path):
            return  # no system layer: nothing for the player to read
        with open(path, encoding="utf-8", errors="replace") as fh:
            entries, sections = parse_conf(fh.read())
        bad = []
        for n, section, name, value in entries:
            cls = self.classify(name)
            if cls != "allowed":
                bad.append("%s:%d `%s` is %s in tests/fixtures/mpv-options.json"
                           % (path, n, name, cls or "unclassified"))
        for n, section in sections:
            bad.append("%s:%d opens the profile [%s]: a profile applies over the command line "
                       "(D-SINK-44), whatever it holds" % (path, n, section))
        self.assertEqual([], bad, "\n".join(["", "The system mpv configuration changed (D-HOST-13); "
                                             "re-measure the player against it before updating this pin:"]
                                            + ["  " + b for b in bad]))

    def test_the_system_mpv_directory_holds_nothing_new(self):
        if not os.path.isdir(SYSTEM):
            return
        entries = set(os.listdir(SYSTEM))
        self.assertEqual(set(), entries - KNOWN_ENTRIES,
                         "the system mpv directory %s holds a new layer the player may read (D-HOST-13)" % SYSTEM)
        scripts = os.path.join(SYSTEM, "scripts")
        if os.path.isdir(scripts):
            self.assertEqual(set(), set(os.listdir(scripts)) - KNOWN_SCRIPTS,
                             "a new system mpv script under %s; re-read D-SINK-4 and the pinned --load-scripts=no" % scripts)


if __name__ == "__main__":
    unittest.main()
