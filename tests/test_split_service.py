"""scripts/split-service.py (D-REL-14 C2): the judge the gate runs over the
service's files, the move that cuts them, and the round trip back.

  * --check on this tree, which declares four code-behinds since D-REL-14's
    C4 (2026-11-24; two since C3, 2026-11-23, and none before it): clean,
    every one of the root's member sites judged (a judge that stopped reading
    reads 0);
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
    names, a tree holding an untracked file at a new code-behind's path, and
    a function that makes a closure (persistActiveLater, D-REL-15);
  * the closure rule (D-REL-15, ss.closure_problems over small texts): each
    shape of a function a code-behind makes is refused, the immediate
    callback of a synchronous Array method is not, nor is anything that
    makes no function (a string, a comment, a regular expression, a
    statement's block); a refused one inside an allowed callback is still
    refused; the CLOSURE-EXCEPTION comment excuses on its line or in the run
    of comment lines directly above, with a reason, and nowhere else; this
    tree's code-behinds make no unexcused function, and with the fix undone
    the tree is refused at adoptActive and startCacheLayout.

Rule 11: each refusal kind's case is wrong on a one-decision mutant of the
judge, and the round trip on a one-byte mutant; the closure rule's tests are
red on baea04a's script and each on one of nineteen one-decision mutants of
the rule (docs/QA-RESULTS.md "D-REL-15: no code-behind closure outlives its
call"); and the fix pass on 2a4ab03's
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
import re
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
         "qualifier", "scope", "sibling", "member", "unjudged", "scan", "closure")


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
        self.assertEqual(len(self.cases), 34)

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
        self.assertIn("the inline view matches %s:Service.qml byte for byte" % self.rev, out)

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
        # A split REV is compared by its inline view, and the message names
        # that, never REV:Service.qml, whose own bytes are fewer (the review
        # of C3).
        self.assertIn("the inline view matches %s's inline view byte for byte" % rev, out)
        self.assertNotIn("%s:Service.qml" % rev, out)

    def test_a_mutant_against_a_split_commit_names_its_inline_view(self):
        rev = self.repo.commit({})
        path = os.path.join(self.repo.dir, "Service-demo.js")
        write(path, raw(path).replace("root.count += by", "root.count -= by"))
        rc, out = run("--verify", "--from-git", rev, "--root", self.repo.dir)
        self.assertEqual(rc, 1, out)
        self.assertIn("differs from %s's inline view at byte" % rev, out)
        self.assertNotIn("%s:Service.qml" % rev, out)


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
        # D-REL-15: persistActiveLater makes the closure it hands to
        # Qt.callLater, which a code-behind may not; the cut runs --check's
        # judge over its result, so it is refused and writes nothing.
        self.refused("closure", "--domain", "later", "persistActiveLater")

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


def code_behind(*body):
    """A code-behind holding one function whose body is `body`, one line
    each at four spaces: body line 0 is the file's line 4."""
    return "// a test code-behind\n\n  function f(x) {\n" + "".join("    %s\n" % line for line in body) + "  }\n"


BODY_LINE = 4
SYNC = ("filter", "map", "forEach", "some", "every", "find", "findIndex", "reduce", "reduceRight", "sort", "flatMap")


class Closures(unittest.TestCase):
    """D-REL-15: --check refuses a function a code-behind makes, but the
    immediate callback of a synchronous Array method and one a
    CLOSURE-EXCEPTION comment excuses. ss.closure_problems is the shipping
    judge, called here over small texts; Cases above runs it through
    judge() and the self-test, and Cut runs it through a refused cut."""

    def judged(self, *body):
        out = []
        for p in ss.closure_problems("Service-test.js", code_behind(*body)):
            m = re.match(r"([a-z-]+): Service-test\.js:([0-9]+):([0-9]+): ", str(p))
            self.assertIsNotNone(m, str(p))
            out.append((m.group(1), int(m.group(2)) - BODY_LINE, int(m.group(3))))
        return out

    def refused_at(self, body, line=0, col=None):
        got = self.judged(*body)
        self.assertEqual([(k, l) for k, l, _c in got], [("closure", line)], body)
        if col is not None:
            self.assertEqual(got[0][2], col, body)

    def test_the_allowed_methods_are_the_synchronous_array_methods(self):
        self.assertEqual(sorted(ss.SYNC_ARRAY_METHODS), sorted(SYNC))

    def test_each_shape_of_a_made_function_is_refused(self):
        for line in ("Qt.callLater(function () { root.persistActive(x) })",
                     "Qt.callLater(function() { root.persistActive(x) })",
                     "Qt.callLater(() => root.persistActive(x))",
                     "Qt.callLater(y => root.persistActive(y))",
                     "Qt.callLater(async () => root.persistActive(x))",
                     "root.queueCacheJob(x, function (status) { root.done(status) })",
                     "var g = function () { return root.count }",
                     "function helper() { return 1 }",
                     "function* gen() { yield 1 }",
                     "root.poke.connect(function () { root.done(1) })",
                     "root.label = Qt.binding(function () { return root.count })",
                     "var o = { done(status) { return status } }",
                     "var o = { get v() { return 1 } }",
                     "var o = { a: 1, async go() { return 2 } }",
                     "var o = { *items() { yield 1 } }",
                     "var o = { [x](s) { return s } }",
                     "class A {}",
                     "x.forEach(async (y) => { await y })",
                     "x.forEach(async function (y) { await y })",
                     "x.then(function (y) { return y })",
                     "Array.from(x, function (y) { return y })",
                     "x.map(x, function (y) { return y })",
                     "x.filter[0](function (y) { return y })"):
            with self.subTest(line=line):
                self.refused_at([line])

    def test_a_function_made_on_a_header_line_is_refused_and_the_header_is_not(self):
        # The header's own `function`, at the root's indent, declares what a
        # forwarder names; another on the same line is made inside it.
        text = "// a test code-behind\n\n  function g(x) { Qt.callLater(function () { root.done(x) }) }\n"
        problems = ss.closure_problems("Service-test.js", text)
        self.assertEqual([str(p).split(": ")[1] for p in problems], ["Service-test.js:3:32"])
        self.assertEqual(ss.closure_problems("Service-test.js", "  function g(x) { return x }\n"), [])

    def test_the_message_names_the_file_the_line_the_column_and_the_finding(self):
        problems = ss.closure_problems("Service-test.js", code_behind("var a = 1", "Qt.callLater(function () {})"))
        self.assertEqual(len(problems), 1)
        self.assertTrue(str(problems[0]).startswith("closure: Service-test.js:5:18: "), str(problems[0]))
        self.assertIn("D-REL-15", str(problems[0]))
        self.assertIn("CLOSURE-EXCEPTION", str(problems[0]))

    def test_a_synchronous_array_methods_immediate_callback_is_allowed(self):
        for method in SYNC:
            for line in ("var q = x.%s(function (a, b) { return a })" % method,
                         "var q = x.%s((a, b) => a)" % method,
                         "var q = x?.%s(a => a)" % method,
                         "var q = x.%s(function(a) {\n      return a\n    })" % method):
                with self.subTest(line=line):
                    self.assertEqual(self.judged(line), [])

    def test_what_makes_no_function_is_not_refused(self):
        for line in ("var o = { a: f(x), b: [g(x)], c: x ? h(x) : 0 }",
                     "if (x) { root.done(1) } else if (x > 1) { root.done(2) } else { root.done(3) }",
                     "for (var i = 0; i < 2; i++) { root.done(i) }",
                     "while (x) { x = 0 }",
                     "do { x = 0 } while (x)",
                     "switch (x) { case 1: break }",
                     "try { root.done(1) } catch (e) { root.done(2) }",
                     "var t = x >= 1 && x == 2 && (x = 3) > 2",
                     "root.countChanged.connect(root.str)",
                     "Qt.callLater(root.persistActive)",
                     "x.function(1)",
                     "var o = { class: 1, function: 2 }",
                     "var k = o.class",
                     'var s = "function () { return 1 }"',
                     "var s = 'x => y'",
                     "var s = `() => function () {} ${x}`",
                     "var r = /function \\(\\) =>/",
                     "var n = 1 /* () => 2, function () {} */",
                     "// Qt.callLater(function () { root.done(1) })"):
            with self.subTest(line=line):
                self.assertEqual(self.judged(line), [])

    def test_a_made_function_inside_an_allowed_callback_is_refused_and_an_allowed_one_is_not(self):
        self.assertEqual(self.judged("x.map(function (a) { return a.filter(function (b) { return b }) })"), [])
        line = "x.filter(function (a) { Qt.callLater(function () { root.done(a) }); return a })"
        self.refused_at([line], 0, 4 + line.index("function ()") + 1)
        self.refused_at(["x.forEach(function (a) {", "  Qt.callLater(() => root.done(a))", "})"], 1)

    def test_a_closure_exception_with_a_reason_excuses_it_on_its_line_or_directly_above(self):
        call = "Qt.callLater(function () { root.done(1) })"
        for body in ([call + " // CLOSURE-EXCEPTION: a test's reason"],
                     ["// CLOSURE-EXCEPTION: a test's reason", call],
                     ["// CLOSURE-EXCEPTION: a test's reason", "// and a second line of it", call],
                     ["// CLOSURE-EXCEPTION: a test's reason", "root.queueCacheJob(x, function (s) {", "  root.done(s)",
                      "})"]):
            with self.subTest(body=body):
                self.assertEqual(self.judged(*body), [])

    def test_what_is_no_closure_exception_does_not_excuse(self):
        call = "Qt.callLater(function () { root.done(1) })"
        for body, line in ((["// CLOSURE-EXCEPTION:", call], 1),
                           (["// CLOSURE-EXCEPTION:   ", call], 1),
                           (["// CLOSURE-EXCEPTION: a reason", "", call], 2),
                           (["var a = 1 // CLOSURE-EXCEPTION: its own line's", call], 1),
                           (['Qt.callLater(function () { root.done(1) }, "// CLOSURE-EXCEPTION: in a string")'], 0),
                           (["Qt.callLater(function () { root.done(1) }) /* CLOSURE-EXCEPTION: a block comment */"], 0),
                           (["var s = `a", "// CLOSURE-EXCEPTION: inside a template", "`; " + call], 2),
                           (["// CONVENTION-EXCEPTION: another guard's", call], 1)):
            with self.subTest(body=body):
                self.refused_at(body, line)

    def test_a_text_the_tokenizer_cannot_read_is_refused_as_unread(self):
        # Never passed as holding no closure: everything after the lost
        # place would go unread.
        problems = ss.closure_problems("Service-test.js", code_behind("var s = `never closed", "Qt.callLater(function () {})"))
        self.assertEqual([p.kind for p in problems], ["scan"])

    def test_this_trees_code_behinds_make_no_unexcused_function(self):
        for path in ss.service_files.service_files(ROOT)[1:]:
            with self.subTest(path=os.path.basename(path)):
                self.assertEqual(ss.closure_problems(os.path.basename(path), raw(path)), [])

    def test_this_tree_with_the_fix_undone_is_refused_at_adoptactive_and_startcachelayout(self):
        # One decision back each: adoptActive's closure made in the
        # code-behind again (C3's line), and startCacheLayout's onDone with
        # its CLOSURE-EXCEPTION taken away.
        text = raw(os.path.join(ROOT, "Service-sources.js"))
        fixed = "      root.persistActiveLater(key)\n"
        self.assertEqual(text.count(fixed), 1)
        text = text.replace(fixed, "      Qt.callLater(function() { root.persistActive(key) })\n")
        lines = text.split("\n")
        at = [i for i, line in enumerate(lines) if "CLOSURE-EXCEPTION:" in line]
        self.assertEqual(len(at), 1)
        start = at[0]
        while ss.service_files.COMMENT_LINE.match(lines[start - 1]):
            start -= 1
        end = at[0]
        while ss.service_files.COMMENT_LINE.match(lines[end + 1]):
            end += 1
        text = "\n".join(lines[:start] + lines[end + 1:])
        found = []
        ss.service_files.function_spans(text, "Service-sources.js", found)
        where = []
        for p in ss.closure_problems("Service-sources.js", text):
            line = int(str(p).split(":")[2])
            offset = sum(len(l) + 1 for l in text.split("\n")[:line - 1])
            where.append([name for name, _a, s, e, _c in found if s <= offset < e])
        self.assertEqual(where, [["adoptActive"], ["startCacheLayout"]])


if __name__ == "__main__":
    unittest.main()
