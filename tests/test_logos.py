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
        name = helper.write_logo(logo_dir, "https://x.test/../../etc/passwd", b"x", "image/png")
        self.assertNotIn("/", name)
        self.assertTrue(os.path.exists(os.path.join(logo_dir, name)))
        self.assertEqual(sorted(os.listdir(logo_dir)), [name])

    def test_the_written_file_is_private_and_the_directory_is_too(self):
        import os, stat, tempfile
        root = tempfile.mkdtemp()
        logo_dir = os.path.join(root, "logos")
        name = helper.write_logo(logo_dir, "https://x.test/a.png", b"\x89PNG", "image/png")
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(logo_dir, name)).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(logo_dir).st_mode), 0o700)

    def test_only_the_allowlisted_types_get_written(self):
        import tempfile, os
        logo_dir = os.path.join(tempfile.mkdtemp(), "logos")
        for ctype in helper.LOGO_TYPES:
            self.assertTrue(helper.write_logo(logo_dir, "https://x.test/%s" % ctype, b"x", ctype))
        for ctype in ("text/html", "image/svg+xml", "application/octet-stream", ""):
            with self.assertRaises(Exception, msg=ctype):
                helper.write_logo(logo_dir, "https://x.test/bad", b"x", ctype)

    def test_the_fetch_is_opt_in_twice(self):
        # The setting is off by default and so is this flag, so nothing
        # contacts anyone because a command was run without reading it.
        import inspect
        source = inspect.getsource(helper.cmd_logos)
        self.assertIn("if not args.fetch:", source)


if __name__ == "__main__":
    unittest.main()
