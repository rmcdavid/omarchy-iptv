"""D-LOGO-11: a provider logo may not choose how much memory the shell allocates.

The finding, raised by the marketplace maintainer against the shipped 0.13.3:
a provider JPEG passes every check `write_logo` had -- content type, magic
bytes, a 256 KiB cap -- and nothing bounds the dimensions its header declares,
while `Guide.qml` renders it inside the long-running shell. The lead measured a
304-byte progressive JPEG whose SOF says 20000x20000 driving the Qt process to
840 MB, and a 555-byte three-component one to 1,239 MB. The byte cap is not a
bound on anything the decoder does, because **the cost is quadratic in a number
the header states and the bytes do not have to honour**.

What this module tests, and why it is shaped this way:

* Every case CALLS the shipping `logo_dimensions` and `logo_within_bounds`.
  Nothing here re-derives a verdict from the dimensions, because a test that
  mirrors the logic it checks can pass while the shipping path is broken
  (CLAUDE.md rule 12). The fixture states the expected answer; the helper is
  asked for its own.
* The expected numbers in `tests/fixtures/logo-dimensions.json` are not this
  project's opinion of its own arithmetic. Every case in the fixture that has
  readable dimensions was confirmed, when the fixture was built, by at least
  one independent HEADER reader -- `identify -ping` and `file` -- whose blind
  spots do not overlap. `test_the_fixture_still_covers_what_it_was_built_for`
  keeps the set from being trimmed to green afterwards.
* The boundary cases carry their weight on purpose. 4096x1024 is exactly
  MAX_LOGO_PIXELS and exactly MAX_LOGO_SIDE on one side, 4097x1024 is one
  pixel over one bound and inside the other, and 2048x2049 passes both side
  checks and is 2,048 pixels over the area. Those are the shapes a wrong
  comparison operator gets wrong and nothing else notices.

The ruling being tested is R1-R6 in docs/QA-RESULTS.md on the dev branch
(the bound lives in the helper at `write_logo`; it reads all four allowed
types; it REFUSES UNLESS IT CAN PROVE the file is within bounds, so an
unreadable header is a refusal; and the cache written by 0.13.3 and earlier is
swept, because a fix without a sweep is not a fix).
"""
import binascii
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper

helper = load_helper()

HERE = pathlib.Path(__file__).resolve().parent
HELPER_BIN = HERE.parent / "bin" / "omarchy-iptv"
FIXTURE = HERE / "fixtures" / "logo-dimensions.json"


def load_fixture():
    document = json.loads(FIXTURE.read_text(encoding="ascii"))
    for case in document["cases"]:
        case["bytes"] = binascii.unhexlify(case["hex"])
    return document


DOCUMENT = load_fixture()
CASES = DOCUMENT["cases"]
BY_ID = {case["id"]: case for case in CASES}


class LogoDimensionParserTest(unittest.TestCase):
    """The parser, over the whole fixture, calling the shipping functions."""

    def test_every_case_reads_the_dimensions_its_header_declares(self):
        for case in CASES:
            got = helper.logo_dimensions(case["bytes"], case["contentType"])
            want = tuple(case["dimensions"]) if case["dimensions"] else None
            self.assertEqual(got, want, "%s: %s" % (case["id"], case["note"]))

    def test_every_case_gets_the_verdict_the_fixture_states(self):
        for case in CASES:
            got = helper.logo_within_bounds(case["bytes"], case["contentType"])
            self.assertIs(got, case["withinBounds"],
                          "%s: %s" % (case["id"], case["note"]))

    def test_a_header_that_cannot_be_read_is_a_refusal_and_not_a_pass(self):
        """R4, which is the whole design: None means "cannot tell", never
        "small". A bounds check that cannot tell those two apart IS the
        defect, and the cost of being wrong this way round is a blank slot in
        a decorative feature against the user's desktop shell."""
        unreadable = [c for c in CASES if c["dimensions"] is None]
        self.assertGreaterEqual(len(unreadable), 10,
                                "the unreadable-header cases are the point of R4")
        for case in unreadable:
            self.assertIsNone(helper.logo_dimensions(case["bytes"], case["contentType"]),
                              case["id"])
            self.assertFalse(helper.logo_within_bounds(case["bytes"], case["contentType"]),
                             "%s must refuse: %s" % (case["id"], case["note"]))

    def test_the_bound_the_fixture_was_written_against_is_the_shipping_bound(self):
        """Not a grep for the numbers (rule 14) -- the constants are read off
        the module and compared with the fixture that was computed from them,
        so moving either one without the other fails here rather than quietly
        re-grading every expectation in the file."""
        self.assertEqual(helper.MAX_LOGO_SIDE, DOCUMENT["maxSide"])
        self.assertEqual(helper.MAX_LOGO_PIXELS, DOCUMENT["maxPixels"])
        self.assertEqual(helper.MAX_LOGO_SIDE, 4096)
        self.assertEqual(helper.MAX_LOGO_PIXELS, 2048 * 2048)

    def test_all_four_allowed_types_are_read_and_none_is_waved_through(self):
        """R3. JPEG is the only one of the four Qt's decoder can scale, which
        is the only reason it is the only one exposed today -- and that
        asymmetry is upstream behaviour nobody here controls, so a Qt that
        learns to scale PNG during decode must not reopen this in silence."""
        for ctype in helper.LOGO_TYPES:
            good = [c for c in CASES if c["contentType"] == ctype and c["withinBounds"]]
            over = [c for c in CASES
                    if c["contentType"] == ctype and c["dimensions"] and not c["withinBounds"]]
            self.assertTrue(good, "no legitimate %s case" % ctype)
            self.assertTrue(over, "no over-bound %s case" % ctype)
            for case in good:
                self.assertTrue(helper.logo_within_bounds(case["bytes"], ctype), case["id"])
            for case in over:
                self.assertFalse(helper.logo_within_bounds(case["bytes"], ctype), case["id"])

    def test_a_content_type_outside_the_allowlist_has_no_parser(self):
        png = BY_ID["png-small"]["bytes"]
        self.assertIsNone(helper.logo_dimensions(png, "image/svg+xml"))
        self.assertFalse(helper.logo_within_bounds(png, "image/svg+xml"))
        # And the type is believed from the caller rather than sniffed, so
        # bytes that are one type offered as another are a refusal.
        self.assertIsNone(helper.logo_dimensions(png, "image/jpeg"))

    def test_it_is_tolerant_of_rubbish_rather_than_raising(self):
        """The gate calls this on provider bytes, so an exception here would
        be a refusal that reads as a crash."""
        for junk in (b"", None, "a string", 7, bytearray(b"\xff\xd8"), b"\x00" * 64):
            for ctype in helper.LOGO_TYPES:
                self.assertFalse(helper.logo_within_bounds(junk, ctype), repr(junk))

    def test_the_refusal_text_names_a_host_and_numbers_and_never_a_url(self):
        """Rule 5 and R6. Nothing new reaches a sink: a logo URL can carry a
        provider path and, where the logos sit beside the playlist, a query
        string. The host is allowed -- it is what makes the refusal actionable
        -- and the port is not part of the answer, because `cdn.test` and
        `cdn.test:8443` are one party."""
        bomb = BY_ID["jpeg-bomb-progressive-20000"]
        url = "https://logos.provider.test:8443/sub/SECRET-TOKEN/a.jpg?k=v"
        text = helper.logo_dimension_refusal(url, bomb["bytes"], "image/jpeg")
        self.assertIn("logos.provider.test", text)
        self.assertIn("20000x20000", text)
        for leak in ("://", "SECRET-TOKEN", "/sub/", "?k=v", "8443"):
            self.assertNotIn(leak, text, text)
        # An unreadable header still says something, without inventing a size.
        text = helper.logo_dimension_refusal(url, b"\xff\xd8", "image/jpeg")
        self.assertIn("logos.provider.test", text)
        self.assertNotIn("20000", text)
        self.assertNotIn("://", text)

    def test_a_credentialed_url_is_refused_without_naming_the_host_at_all(self):
        """D-SINK-1's lesson, and `logo_host` is deliberately stricter than
        "strip the userinfo": userinfo makes the host "" outright, because
        `fetch_logo` refuses such a URL anyway so the host is never contacted,
        and naming it is one slip away from printing the credential beside it.
        The userinfo of a URL ends at the LAST `@`, so the two-at-sign form is
        here as well -- that is the shape that put a password into a Sources
        row in a shipped release (D-SINK-17)."""
        bomb = BY_ID["jpeg-bomb-progressive-20000"]["bytes"]
        for url in ("https://user:SECRET@logos.provider.test/a.jpg",
                    "https://user:p@ss@logos.provider.test/a.jpg",
                    "https://logos.provider.test@evil.test/a.jpg"):
            text = helper.logo_dimension_refusal(url, bomb, "image/jpeg")
            self.assertIn("unnamed host", text, url)
            for leak in ("SECRET", "@", "://", "user", "evil.test",
                         "logos.provider.test"):
                self.assertNotIn(leak, text, "%s leaked %r: %s" % (url, leak, text))
            self.assertIn("20000x20000", text, url)


class LogoFixtureCoverageTest(unittest.TestCase):
    """The fixture cannot be trimmed to green.

    Every assertion here names a shape the fixture exists to carry, so
    deleting the evidence fails instead of passing. This is the second half of
    rule 11: a mutation that reddens nothing is a hole in the fixture, and the
    way a hole gets in later is by someone dropping a case to make a change
    go green.
    """

    def test_the_case_count_does_not_quietly_shrink(self):
        self.assertTrue(FIXTURE.exists(), "tests/fixtures/logo-dimensions.json is missing")
        self.assertGreaterEqual(len(CASES), 44)
        self.assertEqual(len(BY_ID), len(CASES), "the case ids must be unique")
        for case in CASES:
            self.assertTrue(case["note"].strip(), "%s has no note" % case["id"])
            self.assertTrue(case["hex"] == "" or re.fullmatch(r"[0-9a-f]+", case["hex"]),
                            "%s: hex must be lowercase hex (rule 8, ASCII only)" % case["id"])

    def test_the_boundary_quartet_is_present_with_its_exact_expectations(self):
        """The four shapes a wrong comparison operator gets wrong. Spelled out
        by id and by number, because this is the one place where "roughly the
        right cases" is worth nothing."""
        expected = {
            "jpeg-at-the-pixel-bound": ([4096, 1024], True),
            "jpeg-square-at-the-bound": ([2048, 2048], True),
            "jpeg-one-over-the-side": ([4097, 1024], False),
            "jpeg-one-over-the-pixels": ([2048, 2049], False),
            "jpeg-square-sides-ok-area-not": ([4096, 4096], False),
            "jpeg-one-enormous-row": ([65535, 64], False),
        }
        for cid, (dims, within) in expected.items():
            case = BY_ID.get(cid)
            self.assertIsNotNone(case, "the boundary case %s has been removed" % cid)
            self.assertEqual(case["dimensions"], dims, cid)
            self.assertIs(case["withinBounds"], within, cid)
            self.assertEqual(helper.logo_dimensions(case["bytes"], case["contentType"]),
                             tuple(dims), cid)
            self.assertIs(helper.logo_within_bounds(case["bytes"], case["contentType"]),
                          within, cid)
        # Both bounds must be exercised in BOTH directions, or a cap that was
        # dropped altogether would still look guarded.
        self.assertTrue(any(c["dimensions"] and max(c["dimensions"]) > helper.MAX_LOGO_SIDE
                            and c["dimensions"][0] * c["dimensions"][1] <= helper.MAX_LOGO_PIXELS
                            for c in CASES),
                        "no case is over the SIDE bound while inside the pixel bound")
        self.assertTrue(any(c["dimensions"] and max(c["dimensions"]) <= helper.MAX_LOGO_SIDE
                            and c["dimensions"][0] * c["dimensions"][1] > helper.MAX_LOGO_PIXELS
                            for c in CASES),
                        "no case is over the PIXEL bound while inside the side bound")

    def test_the_frame_markers_a_narrow_jpeg_reader_cannot_see_are_covered(self):
        """A reader that takes only 0xC0..0xC2 -- baseline plus the two common
        progressive frames -- cannot find SOF3 or any arithmetic-coded frame,
        and R4 then refuses REAL images. These two cases are what makes the
        wide marker set load-bearing rather than decorative."""
        for cid, marker in (("jpeg-sof3-lossless-small", 0xC3),
                            ("jpeg-sof9-arithmetic-small", 0xC9)):
            case = BY_ID.get(cid)
            self.assertIsNotNone(case, "%s has been removed" % cid)
            self.assertIn(b"\xff" + bytes([marker]), case["bytes"],
                          "%s no longer carries an SOF%X marker" % (cid, marker - 0xC0))
            self.assertIs(case["withinBounds"], True,
                          "%s is a legitimate image and must be accepted" % cid)
            self.assertEqual(helper.logo_dimensions(case["bytes"], "image/jpeg"), (300, 200))
        self.assertIn(0xC3, helper.JPEG_SOF_MARKERS)
        self.assertIn(0xC9, helper.JPEG_SOF_MARKERS)
        # And a bomb behind the same marker is still refused, so widening the
        # set did not open a door.
        bomb = BY_ID["jpeg-sof3-bomb"]
        self.assertFalse(helper.logo_within_bounds(bomb["bytes"], "image/jpeg"))

    def test_the_gif_frame_can_exceed_the_canvas_and_both_are_covered(self):
        """The lead measured a 110-byte GIF whose canvas is 65500x65500 and
        whose only frame is 64x64, and it refused for the canvas. A frame
        descriptor can also declare a rectangle LARGER than the canvas, and
        whether Qt clips it is unmeasured -- so the answer is the maximum over
        both, and the fixture has to carry one of each or half the rule is
        untested."""
        canvas = BY_ID["gif-bomb-canvas-65500"]
        self.assertEqual(helper.logo_dimensions(canvas["bytes"], "image/gif"), (65500, 65500))
        frame = BY_ID["gif-bomb-frame-65500"]
        # The canvas here is SMALL: the refusal can only come from the frame.
        self.assertEqual(frame["bytes"][6] | (frame["bytes"][7] << 8), 120)
        self.assertEqual(frame["bytes"][8] | (frame["bytes"][9] << 8), 90)
        self.assertEqual(helper.logo_dimensions(frame["bytes"], "image/gif"), (65500, 65500))
        self.assertFalse(helper.logo_within_bounds(frame["bytes"], "image/gif"))

    def test_all_three_webp_variants_are_covered(self):
        """VP8 lossy, VP8L lossless and VP8X extended declare their size in
        three different places. Skipping a variant would refuse real lossless
        and real animated logos under R4 rather than failing open, so each one
        needs a case that is ACCEPTED, not only one that is refused."""
        seen = {}
        for case in CASES:
            if case["contentType"] != "image/webp":
                continue
            blob, pos = case["bytes"], 12
            while pos + 8 <= len(blob):
                fourcc = blob[pos:pos + 4]
                length = int.from_bytes(blob[pos + 4:pos + 8], "little")
                if fourcc in (b"VP8 ", b"VP8L", b"VP8X"):
                    seen.setdefault(fourcc, []).append(case)
                    break
                pos += 8 + length + (length & 1)
        for fourcc in (b"VP8 ", b"VP8L", b"VP8X"):
            cases = seen.get(fourcc, [])
            self.assertTrue(cases, "no %s case in the fixture" % fourcc.decode("ascii"))
            self.assertTrue(any(c["withinBounds"] for c in cases),
                            "%s is never ACCEPTED, so R4 would be refusing real logos"
                            % fourcc.decode("ascii"))
            for case in cases:
                self.assertIs(helper.logo_within_bounds(case["bytes"], "image/webp"),
                              case["withinBounds"], case["id"])

    def test_a_truncated_and_a_cut_off_header_of_each_type_is_covered(self):
        """One of each, because the four parsers run off the end of the bytes
        in four different ways and R4 makes every one of them a refusal."""
        for ctype, truncated, cut in (
                ("image/jpeg", "jpeg-truncated-soi-only", "jpeg-cut-mid-segment"),
                ("image/png", "png-truncated-signature-only", "png-cut-mid-ihdr"),
                ("image/gif", "gif-truncated-header-only", "gif-cut-mid-blocks"),
                ("image/webp", "webp-truncated-riff-only",
                 "webp-chunk-declares-more-than-it-has")):
            for cid in (truncated, cut):
                case = BY_ID.get(cid)
                self.assertIsNotNone(case, "%s has been removed" % cid)
                self.assertEqual(case["contentType"], ctype, cid)
                self.assertIsNone(case["dimensions"], cid)
                # The magic still matches: these are refusals decided by the
                # header reader, not by the magic-byte check upstream of it.
                self.assertTrue(helper.logo_bytes_match_type(case["bytes"], ctype)
                                or cid == "jpeg-truncated-soi-only",
                                "%s should still look like %s to the magic check"
                                % (cid, ctype))
                self.assertIsNone(helper.logo_dimensions(case["bytes"], ctype), cid)


class WriteLogoBoundTest(unittest.TestCase):
    """R1: the gate is at `write_logo`, and a refusal creates nothing.

    Deliberately after the magic-byte check and BEFORE `ensure_private_dir`,
    so a refused logo leaves neither the file nor the directory behind. The
    helper is the process that is allowed to die; the shell, which renders
    this, is not.
    """

    def logo_dir(self):
        import tempfile
        return os.path.join(tempfile.mkdtemp(), "logos")

    def test_an_over_bound_logo_is_refused_and_writes_nothing(self):
        for cid in ("jpeg-bomb-progressive-20000", "jpeg-bomb-baseline-65500",
                    "png-bomb-20000", "gif-bomb-canvas-65500", "webp-bomb-vp8-16383",
                    "jpeg-one-over-the-side", "jpeg-one-over-the-pixels",
                    "jpeg-sof3-bomb", "gif-bomb-frame-65500"):
            case = BY_ID[cid]
            target = self.logo_dir()
            with self.assertRaises(helper.HelperError, msg=cid) as caught:
                helper.write_logo(target, "https://logos.provider.test/a", case["bytes"],
                                  case["contentType"])
            self.assertEqual(caught.exception.code, "logo_dimensions", cid)
            self.assertNotIn("://", caught.exception.message, cid)
            # Nothing on disk: not the file, and not even the directory.
            self.assertFalse(os.path.exists(target),
                             "%s created %s" % (cid, target))

    def test_a_header_it_cannot_read_is_refused_at_the_same_gate(self):
        """R4 at the write path, not only in the parser."""
        for cid in ("jpeg-cut-mid-segment", "png-cut-mid-ihdr", "gif-cut-mid-blocks",
                    "webp-chunk-declares-more-than-it-has", "png-first-chunk-is-not-ihdr",
                    "jpeg-scan-before-any-frame"):
            case = BY_ID[cid]
            target = self.logo_dir()
            with self.assertRaises(helper.HelperError, msg=cid) as caught:
                helper.write_logo(target, "https://logos.provider.test/a", case["bytes"],
                                  case["contentType"])
            self.assertEqual(caught.exception.code, "logo_dimensions", cid)
            self.assertFalse(os.path.exists(target), cid)

    def test_a_legitimate_logo_is_still_written_0600_inside_0700(self):
        """The positive control, and it is not a formality: a gate that
        refused everything would pass every test above it."""
        for cid in ("jpeg-small-baseline", "jpeg-small-progressive", "png-small",
                    "gif-small", "webp-small-vp8", "webp-small-vp8l",
                    "webp-small-vp8x", "jpeg-at-the-pixel-bound",
                    "jpeg-square-at-the-bound", "jpeg-sof3-lossless-small",
                    "jpeg-sof9-arithmetic-small", "png-at-the-pixel-bound",
                    "gif-at-the-pixel-bound", "webp-at-the-pixel-bound"):
            case = BY_ID[cid]
            target = self.logo_dir()
            name = helper.write_logo(target, "https://logos.provider.test/%s" % cid,
                                     case["bytes"], case["contentType"])
            path = os.path.join(target, name)
            self.assertTrue(os.path.isfile(path), cid)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600, cid)
            self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o700, cid)
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), case["bytes"], cid)

    def test_the_magic_check_still_runs_first_and_keeps_its_own_code(self):
        """The bound is beside the magic-byte check, not instead of it: bytes
        that are not the declared type must still be `logo_bytes`, or a caller
        switching on the code loses a distinction it already had."""
        target = self.logo_dir()
        with self.assertRaises(helper.HelperError) as caught:
            helper.write_logo(target, "https://x.test/a", BY_ID["png-small"]["bytes"],
                              "image/jpeg")
        self.assertEqual(caught.exception.code, "logo_bytes")
        with self.assertRaises(helper.HelperError) as caught:
            helper.write_logo(target, "https://x.test/a", BY_ID["png-small"]["bytes"],
                              "image/svg+xml")
        self.assertEqual(caught.exception.code, "logo_type")

    def write_case(self, root, case):
        path = os.path.join(root, case["id"])
        with open(path, "wb") as handle:
            handle.write(case["bytes"])
        return path

    def test_a_cached_file_gets_the_same_verdict_as_the_gate(self):
        """`logo_file_within_bounds` is what the sweep calls. It must agree
        with the gate about every one of these files, because a disagreement
        is a file swept and refetched on every single run.

        The cases compared here are the ones whose bytes ARE the type the
        fixture declares. A file on disk carries no record of the content type
        it arrived with, so the sweep has to ask the bytes -- which makes the
        two deliberately different questions for a confused content type, and
        that case is asserted on its own below rather than folded into a
        formula here.
        """
        import tempfile
        root = tempfile.mkdtemp()
        compared = 0
        for case in CASES:
            if not case["bytes"] or helper.logo_sniff_type(case["bytes"]) != case["contentType"]:
                continue
            compared += 1
            self.assertIs(helper.logo_file_within_bounds(self.write_case(root, case)),
                          case["withinBounds"], "%s: %s" % (case["id"], case["note"]))
        self.assertGreaterEqual(compared, 25,
                                "too few cases reached the on-disk check to mean anything")

    def test_a_cached_file_is_judged_by_its_bytes_and_not_by_a_declared_type(self):
        """The one place the two checks are SUPPOSED to disagree. A cache file
        is named by the fnv1a32 of its URL and nothing else, so there is no
        content type on disk to be wrong about: real PNG bytes in the cache
        are a PNG, whatever header they arrived under. The write gate refuses
        the same bytes under `image/jpeg` because there the caller's claim is
        evidence of a confused response, not of a confused file."""
        import tempfile
        root = tempfile.mkdtemp()
        case = BY_ID["png-bytes-offered-as-jpeg"]
        self.assertFalse(helper.logo_within_bounds(case["bytes"], "image/jpeg"),
                         "the gate must refuse PNG bytes offered as JPEG")
        self.assertTrue(helper.logo_file_within_bounds(self.write_case(root, case)),
                        "a 64x64 PNG in the cache is within the bound as a PNG")
        self.assertEqual(helper.logo_sniff_type(case["bytes"]), "image/png")

    def test_a_cached_file_that_is_not_an_image_at_all_is_refused(self):
        """The magic check has guarded the write path since M2-04, but a file
        on disk is not evidence that it went through it."""
        import tempfile
        root = tempfile.mkdtemp()
        for name, blob in (("empty", b""), ("text", b"not an image at all"),
                           ("svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>"),
                           ("elf", b"\x7fELF" + b"\x00" * 64),
                           ("zeros", b"\x00" * 4096)):
            path = os.path.join(root, name)
            with open(path, "wb") as handle:
                handle.write(blob)
            self.assertFalse(helper.logo_file_within_bounds(path), name)
        self.assertFalse(helper.logo_file_within_bounds(os.path.join(root, "nothing-here")))
        self.assertFalse(helper.logo_file_within_bounds(root), "a directory is not a logo")


class LogoCacheSweepTest(unittest.TestCase):
    """R5: the cache 0.13.3 and earlier wrote was never dimension-checked.

    A logo an affected install already holds is still a bomb, the guide still
    loads it BY NAME, and the user cannot see why. So the "already on disk"
    branch of `cmd_logos` validates the header before it announces the name --
    and the name is the whole contract: the guide points an `Image` at a file
    only when this command names it (`Model.logoSlot`, `Service.qml`
    `logoHave`).

    Run as a SUBPROCESS, the way the plugin itself runs it, so what is tested
    is the command and not a function call that resembles it. The refetch that
    a swept file falls through to is pointed at port 1 on loopback, which is
    refused immediately: no DNS lookup, no packet off this machine, and the
    same dead-host path a logo whose provider has gone away already takes.
    """

    DEAD = "https://127.0.0.1:1/%s.png"

    def run_logos(self, cache, *args):
        env = dict(os.environ)
        done = subprocess.run(
            [sys.executable, str(HELPER_BIN), "logos", "--fetch",
             "--cache-dir", cache, "--timeout", "2", *args],
            capture_output=True, text=True, env=env, timeout=120)
        lines = [json.loads(line) for line in done.stdout.strip().splitlines() if line.strip()]
        return done, lines[-1] if lines else None, [l for l in lines if l.get("kind") == "logo"]

    def plant(self, planted):
        """A cache directory holding `planted` = [(case id, ...)] already on
        disk under the exact names `cmd_logos` will look for."""
        import tempfile
        cache = tempfile.mkdtemp()
        logo_dir = os.path.join(cache, helper.LOGO_SUBDIR)
        os.makedirs(logo_dir, mode=0o700)
        channels, names = [], {}
        for index, cid in enumerate(planted):
            url = self.DEAD % cid
            name = helper.logo_filename(url)
            names[cid] = name
            with open(os.path.join(logo_dir, name), "wb") as handle:
                handle.write(BY_ID[cid]["bytes"])
            os.chmod(os.path.join(logo_dir, name), 0o600)
            channels.append({"id": "c%d" % index, "name": "C%d" % index,
                             "group": "G", "url": "http://127.0.0.1/%d" % index,
                             "logo": url})
        with open(os.path.join(cache, helper.CHANNELS_FILE), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "count": len(channels), "channels": channels}, handle)
        return cache, logo_dir, names

    def test_a_bomb_already_in_the_cache_is_unlinked_and_never_announced(self):
        planted = ["jpeg-bomb-progressive-20000", "png-bomb-20000",
                   "gif-bomb-canvas-65500", "webp-bomb-vp8-16383",
                   "jpeg-one-over-the-pixels", "png-small"]
        cache, logo_dir, names = self.plant(planted)
        done, summary, announced = self.run_logos(cache)
        self.assertEqual(done.returncode, 0, done.stderr)
        safe = names["png-small"]
        # The ONLY name the guide is given is the safe one.
        self.assertEqual(summary["names"], [safe], summary)
        self.assertEqual([line["name"] for line in announced], [safe], announced)
        self.assertEqual(summary["cached"], 1, summary)
        self.assertEqual(summary["swept"], 5, summary)
        # And the bombs are off the disk, not merely unmentioned.
        for cid in planted:
            path = os.path.join(logo_dir, names[cid])
            if cid == "png-small":
                self.assertTrue(os.path.exists(path), "the safe logo was swept")
            else:
                self.assertFalse(os.path.exists(path), "%s survived the sweep" % cid)
        self.assertEqual(sorted(os.listdir(logo_dir)), [safe])

    def test_the_summary_reports_the_bound_it_enforced(self):
        """A number the user cannot see is a number they cannot act on, and
        these two are the numbers the README states."""
        cache, _, _ = self.plant(["png-small"])
        _, summary, _ = self.run_logos(cache)
        self.assertEqual(summary["maxSide"], helper.MAX_LOGO_SIDE)
        self.assertEqual(summary["maxPixels"], helper.MAX_LOGO_PIXELS)
        self.assertEqual(summary["maxBytes"], helper.MAX_LOGO_BYTES)

    def test_a_swept_logo_falls_through_to_the_fetch_and_is_counted_there(self):
        """R5's words put the count at the fetch path, so one cached bomb is
        one logo the guide does not get -- not two policy refusals for one
        file. What must be true either way is that the reason is COUNTED
        rather than silent, and that the count carries no URL."""
        cache, _, _ = self.plant(["jpeg-bomb-progressive-20000"])
        done, summary, announced = self.run_logos(cache)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(announced, [])
        self.assertEqual(summary["names"], [])
        self.assertEqual(summary["swept"], 1)
        self.assertEqual(summary["cached"], 0,
                         "a swept file is not on disk any more, so it is not cached")
        self.assertEqual(summary["fetched"], 0)
        # The refetch could not reach the host, so this run counts it as a
        # failure rather than a policy refusal -- which is the dead-host path.
        # Either way it is counted and named by code only.
        self.assertTrue(summary["reasons"], summary)
        # The summary is a sink. Rule 5 redacts to scheme and HOST, and the
        # survey reports hosts on purpose -- that count is the consent
        # sentence. What may never appear is the rest of the URL: the path can
        # carry a channel name and, where the logos sit beside the playlist, a
        # subscriber token in the query.
        blob = json.dumps(summary)
        self.assertNotIn("://", blob, "no URLs in the summary (rule 5)")
        self.assertNotIn("jpeg-bomb-progressive-20000.png", blob,
                         "the logo PATH reached the summary")
        self.assertNotIn(".png", blob, blob)
        self.assertEqual(summary["hosts"], [{"host": "127.0.0.1", "channels": 1}],
                         "the host is reported, and only the host")

    def test_a_legitimate_cached_logo_is_still_announced_and_not_refetched(self):
        """The positive control for the sweep. A sweep that unlinked the
        cache would pass the test above it and break the feature."""
        planted = ["png-small", "jpeg-small-progressive", "gif-small",
                   "webp-small-vp8l", "jpeg-at-the-pixel-bound"]
        cache, logo_dir, names = self.plant(planted)
        before = {name: os.stat(os.path.join(logo_dir, name)).st_ino
                  for name in names.values()}
        done, summary, announced = self.run_logos(cache)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(sorted(summary["names"]), sorted(names.values()), summary)
        self.assertEqual(sorted(line["name"] for line in announced),
                         sorted(names.values()))
        self.assertEqual(summary["cached"], len(planted), summary)
        self.assertEqual(summary["swept"], 0, summary)
        self.assertEqual(summary["fetched"], 0, "nothing may be refetched")
        self.assertEqual(summary["reasons"], {}, summary)
        # Same inode: the files were read, not rewritten.
        for name, ino in before.items():
            self.assertEqual(os.stat(os.path.join(logo_dir, name)).st_ino, ino, name)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(logo_dir, name)).st_mode),
                             0o600, name)

    def test_the_sweep_stays_inside_the_logo_directory(self):
        """A cache cleaner that unlinks by a name it computed is one bug from
        unlinking elsewhere, so the one thing worth proving is that it only
        ever touches the file it was going to announce."""
        cache, logo_dir, names = self.plant(["png-bomb-20000", "png-small"])
        bystander = os.path.join(cache, helper.CHANNELS_FILE)
        with open(os.path.join(logo_dir, "not-ours"), "wb") as handle:
            handle.write(b"somebody else's file")
        done, summary, _ = self.run_logos(cache)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(os.path.exists(bystander), "channels.json was removed")
        self.assertTrue(os.path.exists(os.path.join(logo_dir, "not-ours")),
                        "a file the command never named was removed")
        self.assertEqual(summary["swept"], 1, summary)


if __name__ == "__main__":
    unittest.main()
