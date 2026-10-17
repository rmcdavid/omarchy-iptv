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
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
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


def run_logos_subprocess(cache, *args):
    """`logos --fetch` over `cache`, run the way the plugin runs it: as a
    subprocess of the real helper, never a function call that resembles it.
    Returns (CompletedProcess, the summary object, the per-logo lines)."""
    done = subprocess.run(
        [sys.executable, str(HELPER_BIN), "logos", "--fetch",
         "--cache-dir", cache, "--timeout", "2", *args],
        capture_output=True, text=True, env=dict(os.environ), timeout=120)
    lines = [json.loads(line) for line in done.stdout.strip().splitlines() if line.strip()]
    return done, lines[-1] if lines else None, [l for l in lines if l.get("kind") == "logo"]


# One maximal JPEG segment: a marker, a length field of 65,535 that counts
# itself, and 65,533 bytes of payload -- 65,537 bytes in all. APP9 is used
# because no decoder assigns it a meaning, so a real image padded with these
# is still the same real image to Qt; the parser steps over it by length.
MAXIMAL_SEGMENT = b"\xff\xe9\xff\xff" + b"\x00" * 65533
assert len(MAXIMAL_SEGMENT) == 65537


def padded_jpeg(base, segments, trailing=0):
    """`base` with `segments` maximal APP9 segments inserted after its SOI,
    and `trailing` zero bytes after its EOI. The frame header moves to
    2 + 65,537 * segments + (its offset in `base` minus 2), which is the only
    thing this is for: putting the SOF past LOGO_HEADER_BYTES, or the whole
    file past MAX_LOGO_BYTES, without storing 131 KB of hex in a fixture."""
    assert base[:2] == b"\xff\xd8"
    return base[:2] + MAXIMAL_SEGMENT * segments + base[2:] + b"\x00" * trailing


def png_chunks(data):
    """[(type, body)] of a PNG, read here and not by the helper."""
    out, pos = [], 8
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        out.append((data[pos + 4:pos + 8], data[pos + 8:pos + 8 + length]))
        pos += 12 + length
    return out


def _private_tmpdir(case):
    """A temp directory removed when the case ends.

    A review found these tests leaving their directories behind -- the cap
    test alone leaves 5,002 files a run -- on a /tmp that is a quota-bound
    tmpfs, where a full /tmp turns a gate red for a reason that says nothing
    about the tree.
    """
    path = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, path, True)
    return path


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
        url = "https://logos.provider.test:8443/sub/priv-seg/a.jpg?k=v"
        text = helper.logo_dimension_refusal(url, bomb["bytes"], "image/jpeg")
        self.assertIn("logos.provider.test", text)
        self.assertIn("20000x20000", text)
        for leak in ("://", "priv-seg", "/sub/", "?k=v", "8443"):
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
        for url in ("https://user:pwx@logos.provider.test/a.jpg",
                    "https://user:p@ss@logos.provider.test/a.jpg",
                    "https://logos.provider.test@evil.test/a.jpg"):
            text = helper.logo_dimension_refusal(url, bomb, "image/jpeg")
            self.assertIn("unnamed host", text, url)
            for leak in ("pwx", "@", "://", "user", "evil.test",
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
        # 44 when the fixture was built; 55 after the review round added the
        # EXIF-thumbnail pair, the height-side quartet for JPEG and for PNG,
        # and the two-frame GIF (the three tests below name every one).
        self.assertGreaterEqual(len(CASES), 55)
        self.assertEqual(len(BY_ID), len(CASES), "the case ids must be unique")
        for case in CASES:
            self.assertTrue(case["note"].strip(), "%s has no note" % case["id"])
            self.assertTrue(case["hex"] == "" or re.fullmatch(r"[0-9a-f]+", case["hex"]),
                            "%s: hex must be lowercase hex (rule 8, ASCII only)" % case["id"])

    def test_an_exif_thumbnail_before_the_frame_header_is_walked_past_not_read(self):
        """A review mutation replaced the segment walk with a scan for the
        first 0xFF+SOF byte pair, and 75 tests stayed green: no case put a
        whole JPEG -- an EXIF thumbnail inside APP1 -- in front of the real
        frame header. The reviewer built one. The scan reads the thumbnail's
        64x64 and passes a file the probe took to 1,239 MB; the walk steps
        over APP1 by its declared length and reads the frame.

        The shape is asserted on the bytes so the case cannot be swapped for
        one that no longer carries the thumbnail: an APP1 segment whose
        payload contains an SOI, sitting BEFORE the first SOF marker.
        """
        for cid, dims, within in (("jpeg-exif-thumbnail-before-a-bomb", (20000, 20000), False),
                                  ("jpeg-exif-thumbnail-control", (64, 64), True)):
            case = BY_ID.get(cid)
            self.assertIsNotNone(case, "%s has been removed" % cid)
            blob = case["bytes"]
            self.assertEqual(blob[2:4], b"\xff\xe1", "%s: no APP1 segment after the SOI" % cid)
            app1_len = (blob[4] << 8) | blob[5]
            app1 = blob[6:4 + app1_len]
            self.assertIn(b"\xff\xd8\xff", app1, "%s: APP1 carries no embedded JPEG" % cid)
            # The thumbnail's own SOF sits inside APP1, which is what a naive
            # scan finds first; the real one sits after it.
            inner_sof = next(i for i in range(len(app1) - 1)
                             if app1[i] == 0xFF and app1[i + 1] in helper.JPEG_SOF_MARKERS)
            self.assertLess(6 + inner_sof, 4 + app1_len, cid)
            self.assertEqual(helper.logo_dimensions(blob, "image/jpeg"), dims, cid)
            self.assertIs(helper.logo_within_bounds(blob, "image/jpeg"), within, cid)
            self.assertEqual(tuple(case["dimensions"]), dims, cid)
            self.assertIs(case["withinBounds"], within, cid)

    def test_the_offending_dimension_is_put_in_height_for_two_types(self):
        """The first fixture put every over-bound number in WIDTH, so the
        height half of the side check could be dropped, or the area computed
        as height squared, and nothing reddened. These are the boundary
        quartet transposed: 64x65535 (inside the pixel bound, over the side
        bound in height ONLY), 1024x4096 (at both bounds, passes), 1024x4097
        (one over in height) and 2049x2048 (both sides legal, 2,048 px over
        the area -- and height squared is exactly the bound, so an area
        computed that way passes it). For JPEG and for PNG, because the bound
        is a property of the comparison and not of one parser."""
        expected = {
            "jpeg-one-enormous-column": ([64, 65535], False),
            "jpeg-tall-at-the-pixel-bound": ([1024, 4096], True),
            "jpeg-tall-one-over-the-side": ([1024, 4097], False),
            "jpeg-tall-one-over-the-pixels": ([2049, 2048], False),
            "png-one-enormous-column": ([64, 65535], False),
            "png-tall-at-the-pixel-bound": ([1024, 4096], True),
            "png-tall-one-over-the-side": ([1024, 4097], False),
            "png-tall-one-over-the-pixels": ([2049, 2048], False),
        }
        for cid, (dims, within) in expected.items():
            case = BY_ID.get(cid)
            self.assertIsNotNone(case, "the transposed boundary case %s has been removed" % cid)
            self.assertEqual(case["dimensions"], dims, cid)
            self.assertIs(case["withinBounds"], within, cid)
            self.assertEqual(helper.logo_dimensions(case["bytes"], case["contentType"]),
                             tuple(dims), cid)
            self.assertIs(helper.logo_within_bounds(case["bytes"], case["contentType"]),
                          within, cid)
        # The two shapes that only a HEIGHT-aware comparison refuses, stated
        # as properties so they survive a renamed id.
        self.assertTrue(any(c["dimensions"] and c["dimensions"][1] > helper.MAX_LOGO_SIDE
                            and c["dimensions"][0] <= helper.MAX_LOGO_SIDE
                            and c["dimensions"][0] * c["dimensions"][1] <= helper.MAX_LOGO_PIXELS
                            for c in CASES),
                        "no case is over the side bound in height alone")
        self.assertTrue(any(c["dimensions"] and max(c["dimensions"]) <= helper.MAX_LOGO_SIDE
                            and c["dimensions"][0] * c["dimensions"][1] > helper.MAX_LOGO_PIXELS
                            and c["dimensions"][1] ** 2 <= helper.MAX_LOGO_PIXELS
                            for c in CASES),
                        "no case is over the area bound while height squared is not")

    def test_a_gif_bomb_past_the_second_descriptor_is_covered(self):
        """Rule 14, one notch over: the second-frame case cannot see a walk
        that stops after the SECOND descriptor, and a review showed that
        mutation passing every test. The fixture carries a third-frame bomb
        and the dimension and verdict tests above read it through the
        shipping parser; this only keeps the case from being trimmed."""
        case = next(c for c in CASES if c["id"] == "gif-bomb-third-frame-65500")
        self.assertEqual(case["dimensions"], [65500, 65500])
        self.assertFalse(case["withinBounds"])
        self.assertEqual(case["bytes"].count(b"\x2c\x00\x00\x00\x00"), 3)

    def test_a_gif_bomb_in_the_second_frame_is_reached(self):
        """The only frame bomb in the first fixture was in the FIRST image
        descriptor, so a walk that returned at the first descriptor stayed
        green. The walk has to reach the trailer: a GIF may carry any number
        of frames and the allocation is the largest of them."""
        case = BY_ID.get("gif-bomb-second-frame-65500")
        self.assertIsNotNone(case, "the two-frame GIF has been removed")
        blob = case["bytes"]
        # Walk the descriptors by hand so the shape is pinned: exactly two
        # image descriptors, the first 64x64 and the second 65500x65500.
        frames, pos = [], 13 + (3 * (1 << ((blob[10] & 0x07) + 1)) if blob[10] & 0x80 else 0)
        while pos < len(blob) and blob[pos] != 0x3B:
            if blob[pos] == 0x21:
                pos += 2
                while blob[pos]:
                    pos += blob[pos] + 1
                pos += 1
            elif blob[pos] == 0x2C:
                frames.append((blob[pos + 5] | (blob[pos + 6] << 8),
                               blob[pos + 7] | (blob[pos + 8] << 8)))
                packed = blob[pos + 9]
                pos += 10 + (3 * (1 << ((packed & 0x07) + 1)) if packed & 0x80 else 0) + 1
                while blob[pos]:
                    pos += blob[pos] + 1
                pos += 1
            else:
                self.fail("unexpected block 0x%02x at %d" % (blob[pos], pos))
        self.assertEqual(frames, [(64, 64), (65500, 65500)])
        self.assertEqual(blob[6] | (blob[7] << 8), 64, "the canvas is small on purpose")
        self.assertEqual(helper.logo_dimensions(blob, "image/gif"), (65500, 65500))
        self.assertFalse(helper.logo_within_bounds(blob, "image/gif"))

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
        return os.path.join(_private_tmpdir(self), "logos")

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
                on_disk = handle.read()
            if case["contentType"] != "image/png":
                self.assertEqual(on_disk, case["bytes"], cid)
                continue
            # D-LOGO-13: a PNG is cached in its canonical form. The fixture's
            # PNGs carry cHRM, bKGD, tIME and three tEXt chunks; the colour
            # chunk stays, the rest go, and the image data is the provider's.
            self.assertEqual([kind for kind, _ in png_chunks(on_disk)],
                             [b"IHDR", b"cHRM", b"IDAT", b"IEND"], cid)
            self.assertEqual([c for c in png_chunks(on_disk) if c[0] == b"IDAT"],
                             [c for c in png_chunks(case["bytes"]) if c[0] == b"IDAT"], cid)

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
        root = _private_tmpdir(self)
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
        root = _private_tmpdir(self)
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
        root = _private_tmpdir(self)
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
        return run_logos_subprocess(cache, *args)

    def plant(self, planted, blobs=None):
        """A cache directory holding `planted` = [case id, ...] already on
        disk under the exact names `cmd_logos` will look for. `blobs` maps an
        id to bytes for a file built by the test rather than read from the
        fixture (the padded JPEGs of LogoSecondReadTest)."""
        import tempfile
        cache = _private_tmpdir(self)
        logo_dir = os.path.join(cache, helper.LOGO_SUBDIR)
        os.makedirs(logo_dir, mode=0o700)
        channels, names = [], {}
        for index, cid in enumerate(planted):
            url = self.DEAD % cid
            name = helper.logo_filename(url)
            names[cid] = name
            with open(os.path.join(logo_dir, name), "wb") as handle:
                handle.write(blobs[cid] if blobs and cid in blobs else BY_ID[cid]["bytes"])
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
        # Same inode: the files were read, not rewritten -- except the PNG,
        # which carries text chunks and is made canonical in place first
        # (D-LOGO-13), keeping its name, its mode and its image data.
        self.assertEqual(summary["rewritten"], 1, summary)
        for cid, name in names.items():
            path = os.path.join(logo_dir, name)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600, cid)
            if cid != "png-small":
                self.assertEqual(os.stat(path).st_ino, before[name], cid)
                continue
            with open(path, "rb") as handle:
                self.assertEqual([kind for kind, _ in png_chunks(handle.read())],
                                 [b"IHDR", b"cHRM", b"IDAT", b"IEND"])

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


class LogoSecondReadTest(unittest.TestCase):
    """The second read in `logo_file_within_bounds` had never executed under a
    test: no on-disk case exceeded LOGO_HEADER_BYTES, so dropping it, shrinking
    the constant, or dropping the byte cap on it all stayed green. These files
    are GENERATED -- a real 64x64 JPEG padded with maximal APP9 segments so its
    frame header sits past the first read -- rather than stored as 131 KB of
    hex. The arithmetic the padding relies on is asserted here, because the
    helper's own comment once had it wrong by four bytes: two maximal segments
    after the SOI put the SOF at 131,076, past a 131,072-byte read.
    """

    SMALL = "jpeg-small-baseline"
    BOMB = "jpeg-bomb-progressive-20000"

    def setUp(self):
        import tempfile
        self.root = _private_tmpdir(self)

    def on_disk(self, name, blob):
        path = os.path.join(self.root, name)
        with open(path, "wb") as handle:
            handle.write(blob)
        return path

    def test_two_maximal_segments_put_the_frame_header_past_the_first_read(self):
        far = padded_jpeg(BY_ID[self.SMALL]["bytes"], 2)
        head = far[:helper.LOGO_HEADER_BYTES]
        self.assertEqual(2 + 2 * len(MAXIMAL_SEGMENT), 131076)
        self.assertGreater(131076, helper.LOGO_HEADER_BYTES,
                           "the SOF must sit past the first read for this test to mean anything")
        self.assertLess(len(far), helper.MAX_LOGO_BYTES, "and under the byte cap")
        # The head alone cannot prove it; the whole file can.
        self.assertIsNone(helper.logo_dimensions(head, "image/jpeg"))
        self.assertEqual(helper.logo_dimensions(far, "image/jpeg"), (64, 64))

    def test_the_first_read_alone_proves_a_logo_with_one_maximal_segment(self):
        """The helper's comment says the first read covers ONE maximal APPn
        segment before the frame header, which is the common camera-JPEG
        shape and the reason the sweep is one read for nearly every file.
        That is a claim about the constant, so it is called rather than
        read: the prefix the sweep reads first must prove such a file on its
        own. (A constant shrunk to 16 bytes still answers every verdict
        correctly through the second read; what it loses is this, one read
        per file, and this is the assertion that sees it go.)"""
        near = padded_jpeg(BY_ID[self.SMALL]["bytes"], 1)
        head = helper._read_logo_prefix(self.on_disk("near-ok", near), helper.LOGO_HEADER_BYTES)
        self.assertEqual(helper.logo_dimensions(head, "image/jpeg"), (64, 64),
                         "the first read no longer covers one maximal segment")
        self.assertTrue(helper.logo_within_bounds(head, "image/jpeg"))

    def test_a_valid_logo_whose_header_sits_past_the_first_read_is_proved_by_the_second(self):
        far = padded_jpeg(BY_ID[self.SMALL]["bytes"], 2)
        self.assertTrue(helper.logo_file_within_bounds(self.on_disk("far-ok", far)),
                        "a legitimate 131 KB logo was refused: the second read is not running")
        # And the gate agrees, which is the reason the second read exists: a
        # file write_logo accepts must not be swept on every run.
        self.assertTrue(helper.logo_within_bounds(far, "image/jpeg"))

    def test_a_far_header_that_declares_a_bomb_is_still_refused(self):
        far = padded_jpeg(BY_ID[self.BOMB]["bytes"], 2)
        self.assertLess(len(far), helper.MAX_LOGO_BYTES)
        self.assertEqual(helper.logo_dimensions(far, "image/jpeg"), (20000, 20000))
        self.assertFalse(helper.logo_file_within_bounds(self.on_disk("far-bomb", far)))

    def test_a_file_over_the_byte_cap_is_refused_even_when_its_header_would_pass(self):
        """R4 at the byte axis. The second read is capped at MAX_LOGO_BYTES
        plus one, so a file bigger than that is refused whatever its header
        says -- and the header here is deliberately a GOOD one that the
        capped read can see, so the refusal is on the size alone. The gate
        could never have written such a file (fetch_logo stops reading at the
        cap), which is exactly why the sweep must not believe it."""
        big = padded_jpeg(BY_ID[self.SMALL]["bytes"], 3, trailing=70000)
        self.assertGreater(len(big), helper.MAX_LOGO_BYTES)
        self.assertEqual(helper.logo_dimensions(big[:helper.MAX_LOGO_BYTES + 1], "image/jpeg"),
                         (64, 64), "the capped read must be able to see the frame header, "
                         "or this is testing a parse failure and not the byte cap")
        self.assertIsNone(helper.logo_dimensions(big[:helper.LOGO_HEADER_BYTES], "image/jpeg"))
        self.assertFalse(helper.logo_file_within_bounds(self.on_disk("too-big", big)))

    def test_the_sweep_announces_the_far_logo_and_removes_the_far_bomb_and_the_oversize(self):
        """The same three files through the real command as a subprocess:
        the cached-file branch names the legitimate one and sweeps the two
        it cannot prove. A cached file past the first read is the shape a
        camera-style JPEG with a big embedded colour profile takes."""
        sweep = LogoCacheSweepTest()
        blobs = {"far-ok": padded_jpeg(BY_ID[self.SMALL]["bytes"], 2),
                 "far-bomb": padded_jpeg(BY_ID[self.BOMB]["bytes"], 2),
                 "too-big": padded_jpeg(BY_ID[self.SMALL]["bytes"], 3, trailing=70000)}
        cache, logo_dir, names = sweep.plant(list(blobs), blobs)
        done, summary, announced = run_logos_subprocess(cache)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(summary["names"], [names["far-ok"]], summary)
        self.assertEqual([line["name"] for line in announced], [names["far-ok"]])
        self.assertEqual(summary["cached"], 1, summary)
        self.assertEqual(summary["swept"], 2, summary)
        self.assertEqual(sorted(os.listdir(logo_dir)), [names["far-ok"]])


class LogoFetchCapTest(unittest.TestCase):
    """MAX_LOGO_FILES bounds NEW FETCHES only; a cached file past it is still
    validated and announced.

    The cap check used to be the first line of the loop, as a `break`, so in
    a run that fetched 5,000 new files every cached file later in channel
    order was neither validated nor announced that run: blank slots for logos
    the guide already had, and a cached bomb past the cap left on disk (R5).

    The state is CONSTRUCTED rather than the cap lowered, because the helper
    has no lever for the cap and a lever that could also raise it would be a
    disclosure lever. 5,000 new URLs are served by a double standing in for
    the network only -- `fetch_logo` is the one function replaced, the way
    every fetch test in tests/test_logos.py replaces it -- and `cmd_logos`
    itself runs for real, at the real cap, over a real cache directory. The
    second half then runs the REAL HELPER AS A SUBPROCESS over the cache the
    capped run left, which is the run an upgraded install's next start is.
    """

    def test_a_cached_logo_past_the_cap_is_validated_and_announced_and_a_bomb_is_swept(self):
        import argparse
        import contextlib
        import io
        import tempfile
        cache = _private_tmpdir(self)
        logo_dir = os.path.join(cache, helper.LOGO_SUBDIR)
        os.makedirs(logo_dir, mode=0o700)
        dead = "https://127.0.0.1:1/%s.png"
        cap = helper.MAX_LOGO_FILES
        self.assertEqual(cap, 5000, "the constructed state assumes the shipped cap")
        # Channel order: `cap` new URLs, then three cached files (two safe,
        # one bomb), then two more new URLs the cap must defer.
        new_urls = [dead % ("new-%d" % i) for i in range(cap)]
        planted = ["png-small", "jpeg-bomb-progressive-20000", "gif-small"]
        planted_names = {}
        for cid in planted:
            name = helper.logo_filename(dead % cid)
            planted_names[cid] = name
            with open(os.path.join(logo_dir, name), "wb") as handle:
                handle.write(BY_ID[cid]["bytes"])
        after_urls = [dead % "late-0", dead % "late-1"]
        urls = new_urls + [dead % cid for cid in planted] + after_urls
        channels = [{"id": "c%d" % i, "name": "C%d" % i, "group": "G",
                     "url": "http://127.0.0.1/%d" % i, "logo": url}
                    for i, url in enumerate(urls)]
        with open(os.path.join(cache, helper.CHANNELS_FILE), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "count": len(channels), "channels": channels}, handle)

        served = []

        def network_double(url, timeout):
            served.append(url)
            return BY_ID["webp-small-vp8l"]["bytes"], "image/webp"

        real = helper.fetch_logo
        helper.fetch_logo = network_double
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                helper.cmd_logos(argparse.Namespace(cache_dir=cache, fetch=True,
                                                    survey=False, timeout=1))
        finally:
            helper.fetch_logo = real
        lines = [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]
        summary, announced = lines[-1], [l["name"] for l in lines if l.get("kind") == "logo"]

        self.assertEqual(summary["fetched"], cap)
        self.assertEqual(served, new_urls, "exactly the first `cap` URLs were fetched, "
                         "nothing past the cap and never the cached ones")
        # The cached files PAST the cap: validated, the safe ones announced.
        safe = sorted([planted_names["png-small"], planted_names["gif-small"]])
        self.assertEqual(summary["cached"], 2, summary)
        self.assertEqual(sorted(n for n in announced if n in planted_names.values()), safe)
        self.assertTrue(set(safe) <= set(summary["names"]), "a cached logo past the cap "
                        "was not announced, so the guide draws a blank slot it need not")
        self.assertNotIn(planted_names["jpeg-bomb-progressive-20000"], summary["names"])
        self.assertNotIn(planted_names["jpeg-bomb-progressive-20000"], announced)
        # The bomb past the cap is swept, not left for the shell.
        self.assertEqual(summary["swept"], 1, summary)
        self.assertFalse(os.path.exists(os.path.join(
            logo_dir, planted_names["jpeg-bomb-progressive-20000"])), "a cached bomb past "
            "the cap survived the run")
        # And what the cap held back is a number: the two late URLs plus the
        # swept bomb that fell through to a fetch the cap refused.
        self.assertEqual(summary["deferred"], 3, summary)
        self.assertEqual(summary["cap"], cap)
        self.assertEqual(len(summary["names"]), cap + 2)

        # Second half: the real helper, as a subprocess, over the cache this
        # run left behind. Everything is cached now, so the cap is not reached
        # and the three deferred URLs go to the dead host and fail; what must
        # hold is that every file the capped run wrote or kept is announced.
        done, again, announced_again = run_logos_subprocess(cache)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(again["cached"], cap + 2, again)
        self.assertEqual(again["fetched"], 0)
        self.assertEqual(again["deferred"], 0)
        self.assertEqual(again["swept"], 0)
        self.assertEqual(again["failed"], 3, "the two late URLs and the swept bomb's URL")
        self.assertEqual(sorted(again["names"]), sorted(summary["names"]))
        self.assertEqual(sorted(l["name"] for l in announced_again), sorted(summary["names"]))


def tiny_gif(screen, frames):
    """A GIF89a built here, a few dozen bytes: a logical screen of `screen`
    (w, h), a two-colour table, one image descriptor per (left, top, w, h) in
    `frames`, each carrying the 1x1 LZW stream of the classic 43-byte GIF,
    then the trailer. The reader walks blocks and decodes nothing, so the
    pixel stream does not have to fill the descriptor."""
    out = b"GIF89a" + struct.pack("<HH", *screen) + b"\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    for frame in frames:
        out += b"\x2c" + struct.pack("<HHHH", *frame) + b"\x00\x02\x02\x44\x01\x00"
    return out + b"\x3b"


class GifCanvasTest(unittest.TestCase):
    """D-LOGO-14, the maintainer's eighth finding, on #11892 against 0.14.1:
    the GIF reader took the larger of the logical screen and each frame's
    SIZE, while Qt's handler builds a zero logical screen from the first
    frame's left+width and top+height before it allocates. A 1x1 frame at
    8190,8190 under a 0x0 screen read as 1x1 and passed. The canvas is now the
    largest of the screen and every frame's right and bottom edge, and a zero
    screen or a zero frame is refused. Every input is built here and is a few
    dozen bytes; nothing is decoded."""

    def dims(self, screen, *frames):
        return helper.logo_dimensions(tiny_gif(screen, frames), "image/gif")

    def within(self, screen, *frames):
        return helper.logo_within_bounds(tiny_gif(screen, frames), "image/gif")

    def test_a_valid_tiny_gif_passes_and_an_offset_inside_the_canvas_changes_nothing(self):
        self.assertEqual(len(tiny_gif((1, 1), [(0, 0, 1, 1)])), 35)
        self.assertEqual(self.dims((1, 1), (0, 0, 1, 1)), (1, 1))
        self.assertTrue(self.within((1, 1), (0, 0, 1, 1)))
        self.assertEqual(self.dims((64, 64), (16, 16, 32, 32)), (64, 64))
        name = helper.write_logo(os.path.join(_private_tmpdir(self), "logos"),
                                 "https://logos.provider.test/g",
                                 tiny_gif((64, 64), [(16, 16, 32, 32)]), "image/gif")
        self.assertTrue(name)

    def test_a_small_frame_at_an_offset_past_the_side_bound_is_refused(self):
        blob = tiny_gif((1, 1), [(8190, 8190, 1, 1)])
        self.assertLess(len(blob), 48)
        self.assertEqual(helper.logo_dimensions(blob, "image/gif"), (8191, 8191))
        self.assertFalse(helper.logo_within_bounds(blob, "image/gif"))
        target = os.path.join(_private_tmpdir(self), "logos")
        with self.assertRaises(helper.HelperError) as caught:
            helper.write_logo(target, "https://logos.provider.test/g", blob, "image/gif")
        self.assertEqual(caught.exception.code, "logo_dimensions")
        self.assertIn("8191x8191", caught.exception.message)
        self.assertFalse(os.path.exists(target))
        # The cached-file branch reaches the same verdict on the same bytes.
        planted = os.path.join(_private_tmpdir(self), "planted")
        pathlib.Path(planted).write_bytes(blob)
        self.assertFalse(helper.logo_file_within_bounds(planted))

    def test_a_frame_offset_past_the_area_bound_is_refused_with_both_sides_legal(self):
        self.assertEqual(self.dims((1, 1), (2047, 2048, 1, 1)), (2048, 2049))
        self.assertFalse(self.within((1, 1), (2047, 2048, 1, 1)))

    def test_every_frame_is_offset_not_only_the_first(self):
        self.assertFalse(self.within((64, 64), (0, 0, 64, 64), (8000, 0, 64, 64)))
        self.assertFalse(self.within((64, 64), (0, 0, 64, 64), (0, 0, 64, 64), (0, 4096, 1, 1)))

    def test_a_zero_logical_screen_is_refused(self):
        # The maintainer's shape: Qt would size this canvas from the frame.
        self.assertIsNone(self.dims((0, 0), (8190, 8190, 1, 1)))
        self.assertIsNone(self.dims((0, 0), (0, 0, 1, 1)))
        self.assertIsNone(self.dims((0, 64), (0, 0, 64, 64)))
        self.assertIsNone(self.dims((64, 0), (0, 0, 64, 64)))

    def test_a_zero_sized_frame_is_refused(self):
        self.assertIsNone(self.dims((64, 64), (0, 0, 0, 64)))
        self.assertIsNone(self.dims((64, 64), (0, 0, 64, 64), (0, 0, 64, 0)))

    def test_a_frame_reaching_each_bound_exactly_passes_and_one_more_does_not(self):
        side, area = helper.MAX_LOGO_SIDE, helper.MAX_LOGO_PIXELS
        self.assertEqual((side, area), (4096, 4194304))
        self.assertEqual(self.dims((1, 1), (side - 1, 0, 1, 1)), (side, 1))
        self.assertTrue(self.within((1, 1), (side - 1, 0, 1, 1)))
        self.assertFalse(self.within((1, 1), (side, 0, 1, 1)))
        self.assertEqual(self.dims((1, 1), (2047, 2047, 1, 1)), (2048, 2048))
        self.assertTrue(self.within((1, 1), (2047, 2047, 1, 1)))
        # Both bounds at once: a 4096-wide strip whose bottom edge is row 1024.
        self.assertEqual(self.dims((1, 1), (0, 1023, side, 1)), (side, area // side))
        self.assertTrue(self.within((1, 1), (0, 1023, side, 1)))
        self.assertFalse(self.within((1, 1), (0, 1024, side, 1)))


if __name__ == "__main__":
    unittest.main()
