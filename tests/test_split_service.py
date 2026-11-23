"""scripts/split-service.py (D-REL-14 C2): the judge the gate runs over the
service's files, the move that cuts them, and the round trip back.

  * --check on this tree, which declares two code-behinds since D-REL-14's C3
    (2026-11-23; none before it): clean, every one of the root's member
    sites judged (a judge that stopped reading reads 0);
  * --check's own cases (tests/fixtures/service-split/check-cases.json), one
    by one, and every refusal kind it names among them;
  * --check over the readers' fixture (tests/fixtures/service-split/), a
    real one-code-behind layout, and that layout with a script beside it
    that Service.qml does not import as a code-behind (refused) and with the
    model's own beside it (clean); a CRLF Service.qml is refused for its line
    ends, by name;
  * --inline prints the readers' view, and nothing else;
  * --verify --from-git: the inline view against the commit a move was cut
    from, byte for byte, red on a one-byte mutant of a code-behind;
  * --cut: the readers' fixture cut again from its inline.txt is the
    fixture, file for file (but a new code-behind's header); this tree's
    service (its inline view, the one-file text on a split tree too) cut for
    three functions verifies and goes red on a one-byte mutant; a cut
    appended to a code-behind REV already holds; and the cuts it refuses,
    writing nothing -- among them a function whose arguments are not plain
    names, and a tree holding an untracked file at a new code-behind's path.

Rule 11: each refusal kind's case is wrong on a one-decision mutant of the
judge, and the round trip on a one-byte mutant; and the fix pass on 2a4ab03's
eight new cases, the untracked-file cut, the plain-argument cut, the script
beside the fixture and the CRLF message are each red on 2a4ab03's script or a
one-decision mutant; docs/QA-RESULTS.md "D-REL-14: the splitter and its
guards" has the counts.

Run: python3 -m unittest discover -s tests -p test_split_service.py
"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "split-service.py")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "service-split")
QML_DIR = "/usr/lib/qt6/qml"

_spec = importlib.util.spec_from_file_location("split_service", SCRIPT)
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)

KINDS = ("stray", "not-exact", "unforwarded", "missing", "declaration", "function-twice", "undeclared",
         "qualifier", "scope", "sibling", "member", "unjudged", "scan")


def raw(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8")


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def body_after_header(text):
    """A code-behind past its header: everything after its first blank line."""
    return text.split("\n\n", 1)[1]


def run(*args):
    out = io.StringIO()
    saved = sys.stdout
    sys.stdout = out
    try:
        rc = ss.main(list(args))
    finally:
        sys.stdout = saved
    return rc, out.getvalue()


GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="lane",
               GIT_AUTHOR_EMAIL="lane@localhost.invalid", GIT_COMMITTER_NAME="lane",
               GIT_COMMITTER_EMAIL="lane@localhost.invalid")


def git(repo, *args):
    done = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, env=GIT_ENV, timeout=120)
    if done.returncode != 0:
        raise AssertionError("git %s: %s" % (" ".join(args), done.stderr.decode()))
    return done.stdout.decode()


class Repo(object):
    """A throwaway git repository holding a service, committed."""

    def __init__(self, files):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-split-service-")
        git(self.dir, "init", "-q")
        self.commit(files)

    def commit(self, files):
        for name, text in files.items():
            write(os.path.join(self.dir, name), text)
        git(self.dir, "add", "-A")
        git(self.dir, "commit", "-q", "-m", "service")
        return git(self.dir, "rev-parse", "HEAD").strip()

    def read(self, name):
        return raw(os.path.join(self.dir, name))

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class ThisTree(unittest.TestCase):
    def test_check_is_clean_and_judges_every_member_site(self):
        problems, counts = ss.judge(*ss.tree_inputs(ROOT), qml_dir=QML_DIR)
        self.assertEqual(problems, [])
        self.assertEqual(counts["files"], 1 + counts["code_behinds"])
        # The root's member sites in the service's files: 2,267 on ab3d287,
        # all in Service.qml, and the same over Part A's four-code-behind
        # prototype. A judge that stopped reading them would pass anything.
        self.assertGreater(counts["sites"], 2000)
        self.assertGreater(counts["root_functions"] + counts["forwarders"], 150)

    def test_the_gate_command_is_clean_and_runs_its_own_cases(self):
        rc, out = run("--check", "--root", ROOT, "--qml-dir", QML_DIR)
        self.assertEqual(rc, 0, out)
        with open(ss.CASES, encoding="utf-8") as fh:
            n = len(json.load(fh)["cases"])
        self.assertIn("self-test %d of %d cases" % (n, n), out)


class Cases(unittest.TestCase):
    def setUp(self):
        with open(ss.CASES, encoding="utf-8") as fh:
            self.cases = json.load(fh)["cases"]

    def test_every_case(self):
        cache = {}
        for case in self.cases:
            with self.subTest(case=case["name"]):
                present = case.get("present", ss.scripts_beside(case["files"]))
                problems, counts = ss.judge(case["service"], case["files"], present, QML_DIR, cache)
                want = case["expect"]
                if "refusal" in want:
                    self.assertTrue(problems, counts)
                    self.assertEqual(problems[0].kind, want["refusal"], problems[0])
                else:
                    self.assertEqual(problems, [])
                    for key, value in want.get("counts", {}).items():
                        self.assertEqual(counts[key], value, key)
        self.assertEqual(len(self.cases), 32)

    def test_every_refusal_kind_has_a_case(self):
        kinds = set(c["expect"].get("refusal") for c in self.cases)
        self.assertEqual(sorted(set(KINDS) - kinds), [])

    def test_the_self_test_agrees(self):
        ran, wrong = ss.self_test(QML_DIR)
        self.assertEqual((ran, wrong), (len(self.cases), []))


class ReadersFixture(unittest.TestCase):
    def test_the_readers_fixture_is_a_clean_layout(self):
        rc, out = run("--check", "--root", FIXTURE, "--qml-dir", QML_DIR, "--no-self-test")
        self.assertEqual(rc, 0, out)
        self.assertIn("(2 file(s), 1 code-behind(s), 3 root function(s), 4 forwarder(s)", out)

    def copy(self):
        tmp = tempfile.mkdtemp(prefix="omarchy-iptv-split-service-")
        self.addCleanup(shutil.rmtree, tmp, True)
        for name in ("Service.qml", "Service-demo.js"):
            shutil.copyfile(os.path.join(FIXTURE, name), os.path.join(tmp, name))
        return tmp

    def test_a_script_beside_it_that_it_does_not_import_is_refused_and_the_models_own_is_not(self):
        # A comment before `import` hides the line from the readers, and QML
        # loads the script all the same; only its presence can be judged.
        for name, text, want in (("zap.js", "function zap() { return root.notAMember }\n", "undeclared"),
                                 ("helpers.mjs", "export function h() { return 1 }\n", "undeclared"),
                                 ("Model.mjs", "export function hostsOf(x) { return x }\n", None)):
            with self.subTest(name=name):
                tmp = self.copy()
                write(os.path.join(tmp, name), text)
                rc, out = run("--check", "--root", tmp, "--qml-dir", QML_DIR, "--no-self-test")
                if want is None:
                    self.assertEqual(rc, 0, out)
                else:
                    self.assertEqual(rc, 1, out)
                    self.assertIn("split-service: %s: %s is beside Service.qml" % (want, name), out)

    def test_a_crlf_service_is_refused_for_its_line_ends(self):
        tmp = self.copy()
        for name in ("Service.qml", "Service-demo.js"):
            path = os.path.join(tmp, name)
            write(path, raw(path).replace("\n", "\r\n"))
        rc, out = run("--check", "--root", tmp, "--qml-dir", QML_DIR, "--no-self-test")
        self.assertEqual(rc, 1, out)
        self.assertIn("member: Service.qml has CR line ends", out)

    def test_inline_prints_the_view_and_nothing_else(self):
        done = subprocess.run([sys.executable, "-I", SCRIPT, "--inline", "--root", FIXTURE], capture_output=True,
                              timeout=120)
        self.assertEqual((done.returncode, done.stdout), (0, raw(os.path.join(FIXTURE, "inline.txt")).encode()))


class Verify(unittest.TestCase):
    def setUp(self):
        # REV is the one-file service the fixture was cut from; the working
        # tree is the fixture's split.
        self.repo = Repo({"Service.qml": raw(os.path.join(FIXTURE, "inline.txt"))})
        self.rev = git(self.repo.dir, "rev-parse", "HEAD").strip()
        for name in ("Service.qml", "Service-demo.js"):
            shutil.copyfile(os.path.join(FIXTURE, name), os.path.join(self.repo.dir, name))

    def tearDown(self):
        self.repo.close()

    def test_the_split_verifies_against_the_one_file_commit(self):
        rc, out = run("--verify", "--from-git", self.rev, "--root", self.repo.dir)
        self.assertEqual(rc, 0, out)

    def test_a_one_byte_mutant_of_a_code_behind_is_red(self):
        path = os.path.join(self.repo.dir, "Service-demo.js")
        text = raw(path)
        self.assertEqual(text.count("root.count += by"), 1)
        write(path, text.replace("root.count += by", "root.count -= by"))
        rc, out = run("--verify", "--from-git", self.rev, "--root", self.repo.dir)
        self.assertEqual(rc, 1, out)
        self.assertIn("differs from", out)

    def test_a_split_commit_verifies_against_itself(self):
        rev = self.repo.commit({})
        rc, out = run("--verify", "--from-git", rev, "--root", self.repo.dir)
        self.assertEqual(rc, 0, out)


class Cut(unittest.TestCase):
    def tearDown(self):
        if getattr(self, "repo", None):
            self.repo.close()

    def cut(self, *args):
        return run("--cut", "--from", "HEAD", "--root", self.repo.dir, "--qml-dir", QML_DIR, *args)

    def test_the_fixture_cut_again_from_its_inline_text_is_the_fixture(self):
        # Named in reverse: a code-behind holds its functions in file order.
        self.repo = Repo({"Service.qml": raw(os.path.join(FIXTURE, "inline.txt"))})
        rc, out = self.cut("--domain", "demo", "last", "pattern", "quoted", "bump")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.repo.read("Service.qml"), raw(os.path.join(FIXTURE, "Service.qml")))
        self.assertEqual(body_after_header(self.repo.read("Service-demo.js")),
                         body_after_header(raw(os.path.join(FIXTURE, "Service-demo.js"))))
        self.assertIn("verify ok", out)

    def test_a_cut_appends_to_a_code_behind_rev_already_holds(self):
        self.repo = Repo({"Service.qml": raw(os.path.join(FIXTURE, "inline.txt"))})
        rc, out = self.cut("--domain", "demo", "bump", "quoted")
        self.assertEqual(rc, 0, out)
        self.repo.commit({})
        rc, out = self.cut("--domain", "demo", "pattern", "last")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.repo.read("Service.qml"), raw(os.path.join(FIXTURE, "Service.qml")))
        self.assertEqual(body_after_header(self.repo.read("Service-demo.js")),
                         body_after_header(raw(os.path.join(FIXTURE, "Service-demo.js"))))

    def test_this_trees_service_cut_for_three_functions_verifies_and_a_mutant_is_red(self):
        self.repo = Repo({"Service.qml": ss.service_files.service_text(ROOT)})
        rev = git(self.repo.dir, "rev-parse", "HEAD").strip()
        rc, out = self.cut("--domain", "pip", "togglePip", "requestPip", "pipConfig")
        self.assertEqual(rc, 0, out)
        names = list(ss.service_files.function_spans(self.repo.read("Service-pip.js"), "Service-pip.js"))
        self.assertEqual(names, ["togglePip", "requestPip", "pipConfig"])
        self.assertIn('import "Service-pip.js" as ServicePip\n', self.repo.read("Service.qml"))
        self.assertIn("  function togglePip() { return ServicePip.togglePip() }\n", self.repo.read("Service.qml"))
        problems, counts = ss.judge(*ss.tree_inputs(self.repo.dir), qml_dir=QML_DIR)
        self.assertEqual((problems, counts["code_behinds"], counts["forwarders"]), ([], 1, 3))
        path = os.path.join(self.repo.dir, "Service-pip.js")
        text = raw(path)
        at = text.index("function requestPip(")
        # One byte: a space after requestPip's opening brace.
        write(path, text[:at] + text[at:].replace("{", "{ ", 1))
        rc, out = run("--verify", "--from-git", rev, "--root", self.repo.dir)
        self.assertEqual(rc, 1, out)

    def refused(self, kind, *args):
        before = dict((n, self.repo.read(n)) for n in os.listdir(self.repo.dir) if n != ".git")
        rc, out = self.cut(*args)
        self.assertEqual(rc, 1, out)
        self.assertIn(kind + ":", out)
        after = dict((n, self.repo.read(n)) for n in os.listdir(self.repo.dir) if n != ".git")
        self.assertEqual(after, before, "a refused cut wrote a file")

    def test_the_cuts_it_refuses_write_nothing(self):
        self.repo = Repo({"Service.qml": ss.service_files.service_text(ROOT)})
        self.refused("name", "--domain", "pip", "noSuchFunction")
        self.refused("name", "--domain", "pip", "togglePip", "togglePip")
        self.refused("domain", "--domain", "Pip", "togglePip")
        # persistFailed calls the root's str() unqualified: moved together
        # into one code-behind, that names a sibling.
        self.refused("sibling", "--domain", "cache", "str", "persistFailed")

    def test_a_forwarder_is_not_cut_again(self):
        self.repo = Repo({"Service.qml": raw(os.path.join(FIXTURE, "inline.txt"))})
        self.assertEqual(self.cut("--domain", "demo", "bump", "quoted", "pattern", "last")[0], 0)
        self.repo.commit({})
        self.refused("name", "--domain", "other", "bump")

    def test_a_cut_whose_view_is_not_revs_is_refused(self):
        # The cut holds its own result to REV's inline view before it writes.
        # No input found makes the two differ (the move is byte for byte), so
        # the readers' view of the result is perturbed by one byte here.
        text = raw(os.path.join(FIXTURE, "inline.txt"))
        real = ss.service_files.inline_text
        calls = []

        def perturbed(service, files):
            calls.append(1)
            view = real(service, files)
            return view + "x" if len(calls) == 2 else view
        ss.service_files.inline_text = perturbed
        try:
            with self.assertRaises(ss.Problem) as caught:
                ss.cut_texts(text, {}, [("demo", ["bump"])], QML_DIR)
        finally:
            ss.service_files.inline_text = real
        self.assertEqual(caught.exception.kind, "round-trip")

    def test_an_untracked_file_at_a_new_code_behinds_path_is_refused(self):
        # No file of REV's, so the tree check above never compares it: the
        # cut must find the path empty, or it overwrites what nothing can
        # recover.
        self.repo = Repo({"Service.qml": raw(os.path.join(FIXTURE, "inline.txt"))})
        write(os.path.join(self.repo.dir, "Service-demo.js"), "  function wip() {\n    return 1\n  }\n")
        self.refused("tree", "--domain", "demo", "bump")
        self.assertIn("function wip()", self.repo.read("Service-demo.js"))

    def test_a_function_whose_arguments_are_not_plain_names_is_not_cut(self):
        text = raw(os.path.join(FIXTURE, "inline.txt"))
        self.assertEqual(text.count("  function stays(x) {\n"), 1)
        self.repo = Repo({"Service.qml": text.replace("  function stays(x) {\n", "  function stays(x = 1) {\n")})
        self.refused("name", "--domain", "demo", "stays")

    def test_a_tree_that_differs_from_rev_is_refused(self):
        self.repo = Repo({"Service.qml": raw(os.path.join(FIXTURE, "inline.txt"))})
        write(os.path.join(self.repo.dir, "Service.qml"), raw(os.path.join(FIXTURE, "inline.txt")) + "// edited\n")
        self.refused("tree", "--domain", "demo", "bump")


if __name__ == "__main__":
    unittest.main()
