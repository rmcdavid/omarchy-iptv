"""M2-04 logo survey: who enabling logos would contact, counted without asking.

The ruling (docs/RULING-LOGOS.md, dev branch) turns on one measurement nobody
had taken: the configured playlist names 63 distinct third-party hosts, and
i.imgur.com alone covers two thirds of the channels. A generic warning is not
informed consent when the answer is countable, so the count is produced before
the choice -- by reading the cache and making no request at all.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper

helper = load_helper()


def ch(name, logo=None):
    row = {"name": name, "url": "http://127.0.0.1/%s" % name}
    if logo is not None:
        row["logo"] = logo
    return row


class LogoSurveyTest(unittest.TestCase):

    def test_it_counts_hosts_and_never_returns_a_url(self):
        # Rule 5: URLs are redacted to scheme and host at every sink, and this
        # is a sink. A logo URL can carry a provider path and, where the logos
        # sit beside the playlist, a query string.
        survey = helper.logo_survey([
            ch("A", "https://i.imgur.com/a.png"),
            ch("B", "https://i.imgur.com/b.png?token=SECRET"),
            ch("C", "https://upload.wikimedia.org/c.png"),
            ch("D"),
        ])
        self.assertEqual(survey["channels"], 4)
        self.assertEqual(survey["withLogo"], 3)
        self.assertEqual(survey["hostCount"], 2)
        self.assertEqual(survey["hosts"][0], {"host": "i.imgur.com", "channels": 2})
        blob = json.dumps(survey)
        self.assertNotIn("://", blob)
        self.assertNotIn("SECRET", blob)

    def test_https_only_is_counted_as_refused_not_silently_dropped(self):
        # Ruling rule 3. A refusal the user cannot see is a number they cannot
        # act on, so plain http is counted rather than skipped.
        survey = helper.logo_survey([
            ch("A", "http://cleartext.test/a.png"),
            ch("B", "https://fine.test/b.png"),
            ch("C", "ftp://odd.test/c.png"),
            ch("D", "https:///no-host.png"),
        ])
        self.assertEqual(survey["withLogo"], 4)
        self.assertEqual(survey["wouldContact"], 1)
        self.assertEqual(survey["refused"], 3)
        self.assertEqual(survey["hostCount"], 1)
        self.assertEqual(survey["schemes"], {"http": 1, "https": 2, "ftp": 1})

    def test_hosts_are_ordered_by_reach_so_the_worst_disclosure_is_first(self):
        # The host names are chosen so that by-reach and alphabetical DISAGREE:
        # `zeta` has the reach and sorts last. With names that agree, a mutation
        # replacing the sort with a plain alphabetical one stays green, which is
        # what the first version of this test did.
        survey = helper.logo_survey(
            [ch("x%d" % i, "https://alpha.test/%d.png" % i) for i in range(2)] +
            [ch("y%d" % i, "https://zeta.test/%d.png" % i) for i in range(9)])
        self.assertEqual([h["host"] for h in survey["hosts"]], ["zeta.test", "alpha.test"])
        self.assertEqual(survey["hosts"][0]["channels"], 9)

    def test_it_is_pure_and_tolerant(self):
        self.assertEqual(helper.logo_survey([])["hostCount"], 0)
        self.assertEqual(helper.logo_survey(None)["channels"], 0)
        self.assertEqual(helper.logo_survey(["junk", None, 7])["withLogo"], 0)
        self.assertEqual(helper.logo_survey([ch("A", "")])["withLogo"], 0)

    def test_the_allowlists_are_the_ruling_and_are_reported(self):
        # Reported in the output so the user sees the policy alongside the
        # number, not only in a document they will not read.
        survey = helper.logo_survey([])
        self.assertEqual(survey["allowedSchemes"], ["https"])
        self.assertEqual(survey["allowedTypes"], ["image/png", "image/jpeg", "image/webp", "image/gif"])

    def test_the_command_makes_no_request(self):
        # The strongest thing this test can assert cheaply: the module the
        # survey lives in reaches no network API on this path. urllib.request
        # is imported lazily inside the fetchers, never at survey time.
        import inspect
        source = inspect.getsource(helper.logo_survey) + inspect.getsource(helper.cmd_logos)
        for forbidden in ("urlopen", "urllib.request", "socket", "Request("):
            self.assertNotIn(forbidden, source)


# Real first bytes for each allowed type. The suite used to write b"x" and
# call it a PNG; write_logo now checks the payload against the content type,
# so a double that hands it nonsense would be testing the refusal rather than
# the write.
SAMPLE = {
    "image/png": b"\x89PNG\r\n\x1a\n" + b"\x00" * 8,
    "image/jpeg": b"\xff\xd8\xff\xe0" + b"\x00" * 8,
    "image/gif": b"GIF89a" + b"\x00" * 8,
    "image/webp": b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 8,
}


class LogoFetchGuardsTest(unittest.TestCase):
    """The fetch refuses before it connects. Every case here is a refusal
    decided from the URL or the response headers, so none of them touches the
    network -- and that is the point: the guards are not a code path you reach
    after asking, they are the reason you do not ask."""

    def test_http_is_refused_before_any_request(self):
        with self.assertRaises(Exception) as caught:
            helper.fetch_logo("http://cleartext.test/a.png", 1)
        self.assertEqual(caught.exception.code, "logo_scheme")

    def test_a_url_carrying_userinfo_is_refused(self):
        # THE security rule. read_http_source turns userinfo into an
        # Authorization header, which is right for a playlist and is the one
        # thing a logo request must never do: a provider whose logos sit beside
        # its playlist would be handed the subscription credentials for a
        # picture. fetch_logo refuses rather than stripping, because a URL with
        # credentials in it is not a URL we were meant to fetch.
        with self.assertRaises(Exception) as caught:
            helper.fetch_logo("https://user:pass@provider.test/logo.png", 1)
        self.assertEqual(caught.exception.code, "logo_userinfo")

    def test_the_fetch_sends_no_authorization_header(self):
        import ast, inspect
        # The CODE, not the prose. The docstring explains why Authorization must
        # never be sent, so a plain substring search over the source matches the
        # explanation and calls it the defect.
        tree = ast.parse(inspect.getsource(helper.fetch_logo).lstrip())
        func = tree.body[0]
        if (func.body and isinstance(func.body[0], ast.Expr)
                and isinstance(func.body[0].value, ast.Constant)):
            func.body = func.body[1:]
        code = ast.unparse(func)
        for forbidden in ("Authorization", "base64", "split_userinfo", "read_http_source"):
            self.assertNotIn(forbidden, code, "fetch_logo must not reach %s" % forbidden)

    def test_the_filename_is_derived_from_the_url_and_never_contains_it(self):
        # The provider's path can carry a channel name, a subscriber id or a
        # token, and a path built from an untrusted string is also how a
        # traversal escapes the cache.
        name = helper.logo_filename("https://i.imgur.com/a.png?token=SECRET")
        self.assertNotIn("SECRET", name)
        self.assertNotIn("/", name)
        self.assertNotIn("..", name)
        self.assertEqual(name, helper.logo_filename("https://i.imgur.com/a.png?token=SECRET"))
        self.assertNotEqual(name, helper.logo_filename("https://i.imgur.com/b.png"))

    def test_a_traversal_in_the_url_cannot_escape_the_directory(self):
        import os, tempfile
        root = tempfile.mkdtemp()
        logo_dir = os.path.join(root, "logos")
        name = helper.write_logo(logo_dir, "https://x.test/../../etc/passwd", SAMPLE["image/png"], "image/png")
        self.assertNotIn("/", name)
        self.assertTrue(os.path.exists(os.path.join(logo_dir, name)))
        self.assertEqual(sorted(os.listdir(logo_dir)), [name])

    def test_the_written_file_is_private_and_the_directory_is_too(self):
        import os, stat, tempfile
        root = tempfile.mkdtemp()
        logo_dir = os.path.join(root, "logos")
        name = helper.write_logo(logo_dir, "https://x.test/a.png", SAMPLE["image/png"], "image/png")
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(logo_dir, name)).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(logo_dir).st_mode), 0o700)

    def test_only_the_allowlisted_types_get_written(self):
        import tempfile, os
        logo_dir = os.path.join(tempfile.mkdtemp(), "logos")
        for ctype in helper.LOGO_TYPES:
            self.assertTrue(helper.write_logo(logo_dir, "https://x.test/%s" % ctype, SAMPLE[ctype], ctype))
        for ctype in ("text/html", "image/svg+xml", "application/octet-stream", ""):
            with self.assertRaises(Exception, msg=ctype):
                helper.write_logo(logo_dir, "https://x.test/bad", SAMPLE["image/png"], ctype)

    def test_the_fetch_is_opt_in_twice(self):
        # The setting is off by default and so is this flag, so nothing
        # contacts anyone because a command was run without reading it.
        import inspect
        source = inspect.getsource(helper.cmd_logos)
        self.assertIn("if not args.fetch:", source)

class LogoBytesGateTest(unittest.TestCase):
    """The content type is the SERVER's claim; the bytes are the evidence.

    Qt's Image loads a local file by content, not by name. Measured on Qt
    6.11.2: an extension-less PNG, GIF and JPEG all reach Image.Ready at their
    true size, and so does a PNG named `.txt`. So the extension the cache used
    to append gated nothing -- a file whose bytes are SVG renders as SVG
    whatever it is called, and Qt's SVG renderer is a much larger surface than
    a bitmap decoder. The magic check is the gate the extension looked like.
    """

    def test_every_allowed_type_accepts_its_own_first_bytes(self):
        for ctype, data in SAMPLE.items():
            self.assertTrue(helper.logo_bytes_match_type(data, ctype), ctype)

    def test_no_allowed_type_accepts_another_types_bytes(self):
        for claimed in SAMPLE:
            for actual, data in SAMPLE.items():
                if actual == claimed:
                    continue
                self.assertFalse(helper.logo_bytes_match_type(data, claimed),
                                 "%s bytes passed as %s" % (actual, claimed))

    def test_svg_claiming_to_be_png_is_refused(self):
        """The payload Qt would render as SVG, arriving under an allowed type."""
        svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'
        self.assertFalse(helper.logo_bytes_match_type(svg, "image/png"))
        import os, tempfile
        logo_dir = os.path.join(tempfile.mkdtemp(), "logos")
        with self.assertRaises(helper.HelperError) as caught:
            helper.write_logo(logo_dir, "https://x.test/a.png", svg, "image/png")
        self.assertEqual(caught.exception.code, "logo_bytes")
        self.assertFalse(os.path.exists(logo_dir),
                         "a refused payload must not create the directory either")

    def test_a_truncated_riff_is_not_a_webp(self):
        self.assertFalse(helper.logo_bytes_match_type(b"RIFF\x00\x00\x00\x00AVI ", "image/webp"))
        self.assertFalse(helper.logo_bytes_match_type(b"RIFF", "image/webp"))

    def test_the_file_name_is_the_hash_and_nothing_else(self):
        """The guide names this file from the URL alone, with no index to read.

        An index would be a second source of truth and a JSON parse inside the
        150 ms open budget. Nothing may be appended to this name.
        """
        import os, tempfile
        logo_dir = os.path.join(tempfile.mkdtemp(), "logos")
        url = "https://i.imgur.com/a.png"
        name = helper.write_logo(logo_dir, url, SAMPLE["image/png"], "image/png")
        self.assertEqual(name, helper.logo_filename(url))
        self.assertNotIn(".", name)
        self.assertEqual(os.listdir(logo_dir), [name])

    def test_one_url_is_one_file_whatever_the_type(self):
        """Refetching the same URL as a different type must not orphan a file."""
        import os, tempfile
        logo_dir = os.path.join(tempfile.mkdtemp(), "logos")
        url = "https://i.imgur.com/a.png"
        helper.write_logo(logo_dir, url, SAMPLE["image/png"], "image/png")
        helper.write_logo(logo_dir, url, SAMPLE["image/gif"], "image/gif")
        self.assertEqual(len(os.listdir(logo_dir)), 1)

class LogoSurveyFixtureTest(unittest.TestCase):
    """The survey the consent sentence is composed from, in two languages.

    tests/fixtures/logo-survey.json carries the agreed answers; this module and
    tests/Model.test.js both check against IT, never against each other, so the
    two implementations cannot drift together. The fixture found a real defect
    on its first run: case 7 used to report `user:pass@provider.test` as a host
    the plugin would contact, which both promised a fetch that fetch_logo
    refuses and put the credentials into the consent text -- a new sink, and
    CLAUDE.md rule 5 covers every sink.
    """

    def fixture(self):
        import pathlib
        path = pathlib.Path(__file__).resolve().parent / "fixtures" / "logo-survey.json"
        with open(path) as fh:
            return json.load(fh)["cases"]

    def test_every_case_matches_the_agreed_answer(self):
        cases = self.fixture()
        self.assertGreaterEqual(len(cases), 10)
        for case in cases:
            got = helper.logo_survey(case["channels"])
            for key, want in case["expect"].items():
                self.assertEqual(got[key], want,
                                 "%s / %s" % (case["name"], key))

    def test_userinfo_is_refused_and_never_named(self):
        """The case that matters: credentials must not reach the consent text."""
        survey = helper.logo_survey(
            [{"logo": "https://user:pass@provider.test/logo.png"}])
        self.assertEqual(survey["hosts"], [])
        self.assertEqual(survey["refused"], 1)
        self.assertEqual(survey["wouldContact"], 0)
        blob = json.dumps(survey)
        self.assertNotIn("pass", blob)
        self.assertNotIn("user", blob)

    def test_the_port_is_not_part_of_the_host(self):
        """One party, not two: the consent sentence counts parties."""
        survey = helper.logo_survey([{"logo": "https://cdn.test/a.png"},
                                     {"logo": "https://cdn.test:8443/b.png"}])
        self.assertEqual(survey["hostCount"], 1)
        self.assertEqual(survey["hosts"], [{"host": "cdn.test", "channels": 2}])

    def test_an_ipv6_literal_keeps_its_brackets_and_loses_its_port(self):
        self.assertEqual(helper.logo_host("[2001:db8::1]:8443"), "[2001:db8::1]")
        self.assertEqual(helper.logo_host("[2001:db8::1]"), "[2001:db8::1]")

    def test_the_survey_contacts_nothing(self):
        """It is a count over the cache, and it must stay one."""
        import ast, inspect
        tree = ast.parse(inspect.getsource(helper.logo_survey))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        for forbidden in ("urlopen", "Request", "fetch_logo", "fetch_bytes",
                          "read_http_source", "socket", "open"):
            self.assertNotIn(forbidden, names,
                             "logo_survey must not reach %s" % forbidden)

class LogoFetchCacheTest(unittest.TestCase):
    """A second fetch must contact nobody, and must still report what is there.

    Found live: the service runs a fetch whenever the channel cache loads, so
    without this the shell re-downloaded every logo on every start -- 1,445
    requests to sixty-three third parties per launch, which is exactly the
    disclosure the ruling exists to bound.
    """

    def run_fetch(self, tmp, urls, fetcher):
        """cmd_logos --fetch over a cache holding `urls`, with a stub fetcher."""
        import argparse, io, contextlib, os
        cache = os.path.join(tmp, "cache")
        os.makedirs(cache, exist_ok=True)
        with open(os.path.join(cache, "channels.json"), "w") as fh:
            json.dump({"channels": [{"id": "c%d" % i, "name": "C%d" % i,
                                     "group": "G", "url": "http://127.0.0.1/%d" % i,
                                     "logo": u} for i, u in enumerate(urls)]}, fh)
        args = argparse.Namespace(cache_dir=cache, fetch=True, survey=False, timeout=1)
        real = helper.fetch_logo
        helper.fetch_logo = fetcher
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                helper.cmd_logos(args)
            return json.loads(out.getvalue())
        finally:
            helper.fetch_logo = real

    def test_the_second_fetch_makes_no_requests_and_reports_the_same_names(self):
        import tempfile
        calls = []

        def fetcher(url, timeout):
            calls.append(url)
            return SAMPLE["image/png"], "image/png"

        tmp = tempfile.mkdtemp()
        urls = ["https://h.test/%d.png" % i for i in range(5)]
        first = self.run_fetch(tmp, urls, fetcher)
        self.assertEqual(first["fetched"], 5)
        self.assertEqual(first["cached"], 0)
        self.assertEqual(len(calls), 5)

        calls.clear()
        second = self.run_fetch(tmp, urls, fetcher)
        self.assertEqual(calls, [], "a cached logo must not be requested again")
        self.assertEqual(second["fetched"], 0)
        self.assertEqual(second["cached"], 5)
        self.assertEqual(sorted(second["names"]), sorted(first["names"]),
                         "the guide draws from `names`, so it must survive a cached run")

    def test_names_are_hashes_and_carry_no_urls(self):
        """`names` goes over stdout to the service; rule 5 covers that sink too."""
        import tempfile

        def fetcher(url, timeout):
            return SAMPLE["image/png"], "image/png"

        report = self.run_fetch(tempfile.mkdtemp(),
                                ["https://h.test/a.png?token=SECRET"], fetcher)
        blob = json.dumps(report["names"])
        self.assertNotIn("SECRET", blob)
        self.assertNotIn("h.test", blob)
        self.assertNotIn("/", blob)
        self.assertEqual(report["names"],
                         [helper.logo_filename("https://h.test/a.png?token=SECRET")])

    def test_a_logo_that_fails_is_not_in_names(self):
        """The guide must not point an Image at a file that was never written."""
        import tempfile

        def fetcher(url, timeout):
            if url.endswith("2.png"):
                raise helper.HelperError("logo_fetch", "could not fetch a logo from h.test")
            return SAMPLE["image/png"], "image/png"

        report = self.run_fetch(tempfile.mkdtemp(),
                                ["https://h.test/%d.png" % i for i in range(4)], fetcher)
        self.assertEqual(report["fetched"], 3)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(len(report["names"]), 3)
        self.assertNotIn(helper.logo_filename("https://h.test/2.png"), report["names"])



if __name__ == "__main__":
    unittest.main()
