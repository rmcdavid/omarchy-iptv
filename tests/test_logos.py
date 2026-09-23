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


if __name__ == "__main__":
    unittest.main()
