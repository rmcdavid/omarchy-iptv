"""D-SG-1, the synthetic single-group fixture (docs/STATUS.md "## Defects",
ruling SG1, docs/QA-PHASE3.md tier 3c).

The defect: a search key is `name + " " + group`, so on a list whose every
row sits in ONE group every key ends with the same words, and the pre-fix
ranking let any FRAGMENT of those words through tier 3. On the subscriber's
3,335-row "United States" list `st`, `sta`, `ted`, `ited` and `unit` each
reported 3,335 matches; the header and the footer repeated the number. The
fix, Model.matchRank tier 3 requiring every term as a WHOLE WORD of the key
(Model.containsAllWords), is the one decision this file measures.

Why the configured source cannot show it: 28 groups, so a fragment of one
group's name pulls in at most that group. The symptom needs every key to end
in the SAME group words, which is what tests/fixtures/qa-sg1 supplies:

  (a) the committed 50-row list tests/fixtures/qa-sg1/single-group.m3u,
      hand-readable, names chosen so the fragment queries have non-trivial
      genuine matches;
  (b) the full scale, 3,335 rows in one group, GENERATED here into a scratch
      directory by scripts/gen-playlist.py (seed 1, byte-identical, digest
      asserted) with the group-title rewritten to "United States", so the
      filed magnitude is reproduced without committing 3,335 lines;
  (c) a 26-group control at the same scale, which shows the fix's accepted
      cost: some queries now return FEWER rows (docs/UX.md 2.6, cost 3).

Every count is produced by the SHIPPING path, never re-implemented (CLAUDE.md
rule 12): the helper `bin/omarchy-iptv playlist` parses each list into a
channels.json exactly as the service would, and tests/fixtures/qa-sg1/verify.js
(run by node with an argv list) feeds that cache through Model.parseChannels,
prepareChannels, buildChnoIndex, scopeSurface, channelsForScope,
effectiveScope, filterChannels and groupWordHint in the order Service.qml and
Guide.qml call them. What comes back is filterChannels().total, the number the
header prints, `truncated`, the condition that makes the footer say "First
200 of N - keep typing", and the group the empty state would name.

The pre-fix logic is not remembered, it is BUILT: a scratch copy of Model.js
with the whole-word test in matchRank replaced by the substring test the
parent commit (e904721^) had there. verify.js loads both and reports
{query: {pre, post}} side by side; the assertions say the post counts are the
real matches and the pre counts are the whole list.

Rule-11 proof (CLAUDE.md), the same mutation applied to the REPO Model.js in
place, `git checkout -- Model.js` afterwards, 2026-09-20:
  RED   10 of 13 failed against the pre-fix ranking. The committed list's
        six came back {st: 50, sta: 50, ted: 50, ited: 50, unit: 50,
        starz: 5} against {11, 7, 4, 3, 2, 5}; at scale `st` 3335 against
        302 and `unit` 3335 with no hint against 0 with "United States";
        the control's `port` 631 against 110 and `roup` 3335 against 0. The
        three tests that need the pre-fix copy failed on building it, since
        the line they replace was already gone. The three that stayed green
        are the ones that only assert what the lists ARE: row counts,
        digests, the sole group.
  GREEN 13 of 13 against the shipping Model.js, 1.2 s.

What this settles from the terminal: the counts, the cap, the hint's text.
What still needs a screen (do not read this file as evidence for it): the
header and footer STRINGS the guide composes from these numbers, the empty
state's rendering of the hint while typing toward the sole group name, and
per-keystroke responsiveness in the QML engine at 3,335 rows.
"""
from helper_loader import load_helper   # FIRST: it redirects HOME before anything touches the helper

import contextlib
import hashlib
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "qa-sg1"
SMALL_M3U = FIXTURE_DIR / "single-group.m3u"
VERIFY_JS = FIXTURE_DIR / "verify.js"
GENERATOR = ROOT / "scripts" / "gen-playlist.py"
MODEL_JS = ROOT / "Model.js"

# The one decision ruling SG1 made, as it reads in Model.matchRank, and what
# the parent commit had in its place. The pre-fix copy is built from the
# shipping file by this one replacement and nothing else.
FIX_LINE = "if (containsAllWords(text, tokens)) return 3"
PRE_FIX_LINE = "if (containsAll(text, tokens)) return 3"

GROUP = "United States"
SCALE = 3335
SEED = "1"
CONTROL_GROUPS = 26
GENERATED_TITLE = re.compile(r'group-title="Group 001 [A-Za-z]+"')
ANY_TITLE = re.compile(r'group-title="([^"]*)"')

# sha256 of the two generated playlists. gen-playlist.py promises byte-identical
# output for the same flags, and asserting the digest ties every count below to
# THE list it was measured on: a generator change moves the digest first, so
# the counts read as "measured on a different list", never as merely wrong.
SINGLE_GROUP_SHA256 = "9b6cb8d10d0e8c6a92915364f9924d12b5430f79636cf490eb0f129ce040adc9"
CONTROL_SHA256 = "910400e046c2890ba339dc420ea755267872008c26910306dc91007f36248057"

# The six queries docs/QA-PHASE3.md names, then the ones the accepted costs
# in docs/UX.md 2.6 predict, then the control's group-noun fragments.
SIX = ["st", "sta", "ted", "ited", "unit", "starz"]
SMALL_QUERIES = SIX + ["stat", "state", "states", "united", "united states", "united stat",
                       "unit states", "stat states", "ted states", "ited united"]
SCALE_QUERIES = SIX + ["es", "tes", "ni", "stat", "state", "unite", "states", "united", "united states",
                       "unit states", "stat states", "ted states"]
CONTROL_QUERIES = ["port", "istor", "atur", "ew", "cienc", "utdoor", "lassic",
                   "sports", "news", "history", "roup", "grou", "sport"]


def sha256_of(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def parse_with_helper(m3u, cache_dir):
    """`bin/omarchy-iptv playlist`, in-process, the way tests/test_playlist.py
    runs it. The helper insists on an absolute path for a local playlist and
    writes channels.json under --cache-dir and nowhere else."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = helper.main(["playlist", "--url", str(pathlib.Path(m3u).resolve()),
                            "--cache-dir", str(cache_dir)])
    status = json.loads(out.getvalue().strip().splitlines()[-1])
    return code, status


def generate(channels, groups, out):
    subprocess.run([sys.executable, str(GENERATOR), "--channels", str(channels), "--groups", str(groups),
                    "--seed", SEED, "--out", str(out)],
                   check=True, capture_output=True, timeout=120)


def retitle(src, dst):
    """Rewrite the generator's sole group-title to the two-word name the
    defect was filed against. Returns (rows rewritten, titles left over)."""
    text = pathlib.Path(src).read_text(encoding="utf-8")
    new, count = GENERATED_TITLE.subn('group-title="%s"' % GROUP, text)
    others = sorted(set(title for title in ANY_TITLE.findall(new) if title != GROUP))
    pathlib.Path(dst).write_text(new, encoding="utf-8")
    return count, others


def build_pre_fix_model(dst):
    text = MODEL_JS.read_text(encoding="utf-8")
    found = text.count(FIX_LINE)
    if found != 1:
        raise AssertionError("expected exactly one %r in Model.js, found %d: the pre-fix copy "
                             "cannot be built from this tree" % (FIX_LINE, found))
    pathlib.Path(dst).write_text(text.replace(FIX_LINE, PRE_FIX_LINE), encoding="utf-8")


def run_verify(node, cache, pre_model, queries):
    """node verify.js, as an argv list (CLAUDE.md engineering rule 2)."""
    argv = [node, str(VERIFY_JS), str(cache), str(MODEL_JS), str(pre_model) if pre_model else "-"] + list(queries)
    done = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if done.returncode != 0:
        raise AssertionError("verify.js exited %d: %s" % (done.returncode, done.stderr.strip()))
    return json.loads(done.stdout)


class SingleGroupSearchFixtureTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            # Not a skip: check.sh needs node for its own node step, and a
            # fixture that silently stops running is the failure this phase
            # exists to prevent.
            raise AssertionError("node is required to run tests/fixtures/qa-sg1/verify.js")
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="omarchy-iptv-sg1-"))
        cls.addClassCleanup(shutil.rmtree, str(cls.tmp), True)

        cls.pre_model = cls.tmp / "Model-pre-fix.js"
        cls.pre_error = ""
        try:
            build_pre_fix_model(cls.pre_model)
        except AssertionError as exc:
            # Recorded, not raised: the post-count tests still run and show
            # their numbers; every test that needs the pre side fails on this.
            cls.pre_error = str(exc)
            cls.pre_model = None

        # (a) the committed list
        small_cache = cls.tmp / "small"
        small_cache.mkdir()
        cls.small_code, cls.small_status = parse_with_helper(SMALL_M3U, small_cache)
        if cls.small_code != 0:
            raise AssertionError("helper could not parse %s: %s" % (SMALL_M3U, cls.small_status))
        cls.small = run_verify(cls.node, small_cache / "channels.json", cls.pre_model, SMALL_QUERIES)

        # (b) the full scale, one group, generated here
        scale_dir = cls.tmp / "scale"
        scale_dir.mkdir()
        generated = scale_dir / "gen.m3u"
        generate(SCALE, 1, generated)
        cls.scale_sha = sha256_of(generated)
        cls.scale_retitled = retitle(generated, scale_dir / "united-states.m3u")
        cls.scale_code, cls.scale_status = parse_with_helper(scale_dir / "united-states.m3u", scale_dir)
        if cls.scale_code != 0:
            raise AssertionError("helper could not parse the generated single-group list: %s" % cls.scale_status)
        cls.scale = run_verify(cls.node, scale_dir / "channels.json", cls.pre_model, SCALE_QUERIES)

        # (c) the multi-group control, same scale, same seed
        control_dir = cls.tmp / "control"
        control_dir.mkdir()
        control = control_dir / "gen.m3u"
        generate(SCALE, CONTROL_GROUPS, control)
        cls.control_sha = sha256_of(control)
        cls.control_code, cls.control_status = parse_with_helper(control, control_dir)
        if cls.control_code != 0:
            raise AssertionError("helper could not parse the generated control list: %s" % cls.control_status)
        cls.control = run_verify(cls.node, control_dir / "channels.json", cls.pre_model, CONTROL_QUERIES)

    # ---- helpers

    def post(self, doc, queries):
        return {q: doc["results"][q]["post"] for q in queries}

    def pre(self, doc, queries):
        if self.pre_error:
            self.fail(self.pre_error)
        return {q: doc["results"][q]["pre"] for q in queries}

    # ---- (a) the committed 50-row list

    def test_committed_list_is_fifty_rows_in_one_group(self):
        self.assertEqual(self.small_status["channelCount"], 50)
        self.assertEqual(self.small_status["groupCount"], 1)
        self.assertEqual(self.small["channels"], 50)
        # verify.js collects groupNames the way Guide.qml:696-700 does, by a
        # COPY of that loop, not a call: the join is unverified (D-SG-2).
        self.assertEqual(self.small["groupNames"], [GROUP], "the sole group must come off the axis")
        self.assertEqual(self.small["limit"], 200)

    def test_committed_list_shipping_counts_are_the_real_name_matches(self):
        self.assertEqual(self.post(self.small, SIX),
                         {"st": 11, "sta": 7, "ted": 4, "ited": 3, "unit": 2, "starz": 5})

    def test_committed_list_pre_fix_counts_balloon_to_every_row(self):
        pre = self.pre(self.small, SIX)
        self.assertEqual(pre, {"st": 50, "sta": 50, "ted": 50, "ited": 50, "unit": 50, "starz": 5})
        post = self.post(self.small, SIX)
        for q in ("st", "sta", "ted", "ited", "unit"):
            self.assertGreater(pre[q], post[q], q)
            self.assertGreater(post[q], 0, "%s must have genuine matches, or the two counts are not both non-trivial" % q)
        # `starz` is not a fragment of the group name: the ranking never
        # touched it, and it is the query the filed row counted 19 of.
        self.assertEqual(pre["starz"], post["starz"])

    def test_every_term_must_be_a_whole_word_not_only_the_last(self):
        """The verifier's catch: a rule that checks only the LAST token as a
        whole word survived every query here, the node suite and the QML spec.
        A fragment BEFORE a whole word is the case that tells them apart:
        `unit states` has a whole second word and a fragment first."""
        first = ["unit states", "stat states", "ted states"]
        self.assertEqual(self.post(self.small, first), {q: 0 for q in first})
        self.assertEqual(self.pre(self.small, first), {q: 50 for q in first})
        self.assertEqual(self.post(self.scale, first), {q: 0 for q in first})
        self.assertEqual(self.pre(self.scale, first), {q: SCALE for q in first})
        # and one that DOES match, so the rule is not simply "two tokens -> 0"
        self.assertEqual(self.post(self.small, ["ited united"]), {"ited united": 2})
        self.assertEqual(self.pre(self.small, ["ited united"]), {"ited united": 50})

    def test_the_hint_stays_silent_when_the_query_is_not_a_group_word_prefix(self):
        """The negative half of the hint. A hint that unconditionally named the
        first group passed every positive assertion here."""
        for q in ("ted", "ited", "tes", "starz"):
            self.assertEqual(self.scale["results"][q]["hint"], "", q)
        self.assertEqual(self.control["results"]["roup"]["hint"], "")

    def test_control_list_one_more_keystroke_restores_the_group(self):
        # docs/UX.md 2.6 cost 3, second clause: `sport` answers with names
        # only; `sports`, one keystroke on, is a whole group word again.
        post = self.post(self.control, ["sport", "sports"])
        self.assertGreater(post["sport"], 0)
        self.assertLess(post["sport"], post["sports"])
        self.assertEqual(post["sports"], 631)

    def test_committed_list_whole_group_words_still_reach_every_row(self):
        # docs/UX.md 2.6 cost 2: a count can GROW as you type, because the
        # longer query completes a group word. `state` names two channels;
        # `states` is a whole word of the group and reaches all fifty.
        self.assertEqual(self.post(self.small, ["stat", "state", "states", "united", "united states"]),
                         {"stat": 2, "state": 2, "states": 50, "united": 50, "united states": 50})

    def test_committed_list_dead_zone_names_the_group(self):
        # docs/UX.md 2.6 cost 1: `united` is a whole group word, `stat` only a
        # fragment of the other, no name carries both. Nothing matches, and the
        # empty state names the group the user is typing toward.
        row = self.small["results"]["united stat"]
        self.assertEqual(row["post"], 0)
        self.assertEqual(row["hint"], GROUP)
        self.assertEqual(self.pre(self.small, ["united stat"]), {"united stat": 50},
                         "pre-fix, the same query reported every row instead")

    # ---- (b) 3,335 rows in one group, generated

    def test_generated_list_is_the_one_the_counts_were_measured_on(self):
        self.assertEqual(self.scale_sha, SINGLE_GROUP_SHA256,
                         "gen-playlist.py --channels 3335 --groups 1 --seed 1 no longer produces the list "
                         "the counts below were measured on; re-measure before touching them")
        self.assertEqual(self.scale_retitled, (SCALE, []), "every row must be retitled and no other title may remain")
        self.assertEqual(self.scale_status["channelCount"], SCALE)
        self.assertEqual(self.scale_status["groupCount"], 1)
        self.assertEqual(self.scale["channels"], SCALE)
        self.assertEqual(self.scale["groupNames"], [GROUP])

    def test_generated_list_shipping_counts_are_the_real_matches(self):
        self.assertEqual(self.post(self.scale, SIX + ["es", "tes", "ni"]),
                         {"st": 302, "sta": 90, "ted": 0, "ited": 0, "unit": 0, "starz": 0,
                          "es": 312, "tes": 0, "ni": 104})
        # The 200-row cap is honest now: `st` has 302 real matches, so the
        # footer's "First 200 of 302 - keep typing" is true, and `sta` fits.
        st = self.scale["results"]["st"]
        self.assertEqual((st["postRows"], st["postTruncated"]), (200, True))
        sta = self.scale["results"]["sta"]
        self.assertEqual((sta["postRows"], sta["postTruncated"]), (90, False))

    def test_generated_list_pre_fix_reported_the_whole_list(self):
        fragments = ["st", "sta", "ted", "ited", "unit", "es", "tes", "ni"]
        self.assertEqual(self.pre(self.scale, fragments), {q: SCALE for q in fragments})
        for q in fragments:
            # "First 200 of 3,335 - keep typing" for a query with 0 to 312 real matches
            self.assertTrue(self.scale["results"][q]["preTruncated"], q)
        self.assertEqual(self.pre(self.scale, ["starz"]), {"starz": 0})

    def test_generated_list_dead_zone_and_growth(self):
        # No generated name contains any of these, so typing toward the
        # group's own words crosses a dead zone, and the hint names the group.
        for q in ("stat", "state", "unit", "unite"):
            row = self.scale["results"][q]
            self.assertEqual((row["post"], row["hint"]), (0, GROUP), q)
        # ...until the word is whole, when the tier reaches every row.
        for q in ("states", "united", "united states"):
            row = self.scale["results"][q]
            self.assertEqual((row["post"], row["postRows"], row["postTruncated"]), (SCALE, 200, True), q)

    # ---- (c) the 26-group control at the same scale

    def test_control_list_is_the_one_the_counts_were_measured_on(self):
        self.assertEqual(self.control_sha, CONTROL_SHA256,
                         "gen-playlist.py --channels 3335 --groups 26 --seed 1 no longer produces the list "
                         "the counts below were measured on; re-measure before touching them")
        self.assertEqual(self.control_status["channelCount"], SCALE)
        self.assertEqual(self.control_status["groupCount"], CONTROL_GROUPS)
        self.assertEqual(self.control["channels"], SCALE)
        self.assertEqual(len(self.control["groupNames"]), CONTROL_GROUPS)

    def test_control_list_some_queries_now_return_fewer_rows(self):
        # docs/UX.md 2.6 cost 3. Each query is a fragment of a group noun
        # (Sports, History, Nature, News, Science, Outdoor, Classic) that some
        # channel names also carry: pre-fix the group half pulled in whole
        # groups, now only the names answer.
        expected = {"port": (631, 110), "istor": (510, 100), "atur": (360, 85), "ew": (377, 120),
                    "cienc": (216, 102), "utdoor": (366, 97), "lassic": (238, 101)}
        queries = list(expected)
        post = self.post(self.control, queries)
        self.assertEqual(post, {q: expected[q][1] for q in queries})
        pre = self.pre(self.control, queries)
        self.assertEqual(pre, {q: expected[q][0] for q in queries})
        for q in queries:
            self.assertGreater(pre[q], post[q], q)
            self.assertGreater(post[q], 0, q)

    def test_control_list_whole_group_words_are_unchanged(self):
        # The tier itself survives: a whole group word reaches its groups
        # exactly as before.
        words = ["sports", "news", "history"]
        self.assertEqual(self.post(self.control, words), {"sports": 631, "news": 377, "history": 510})
        self.assertEqual(self.pre(self.control, words), self.post(self.control, words))

    def test_control_list_word_shared_by_every_title_is_the_same_defect(self):
        # The generator writes "Group NNN <Noun>" on every title, so the word
        # "Group" is common to all 26 of them and a fragment of it reproduced
        # the D-SG-1 symptom on a multi-group list too: the condition is a
        # word shared by every key's group half, of which "one group" is only
        # the commonest case.
        roup = self.control["results"]["roup"]
        self.assertEqual(roup["post"], 0)
        self.assertEqual(self.pre(self.control, ["roup"]), {"roup": SCALE})
        grou = self.control["results"]["grou"]
        self.assertEqual(grou["post"], 0)
        self.assertIn(grou["hint"], self.control["groupNames"], "the empty state names a group the user is typing toward")


if __name__ == "__main__":
    unittest.main()
