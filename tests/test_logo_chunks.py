"""D-LOGO-13: a cached PNG logo carries only the chunks drawing needs.

The finding, raised by the marketplace maintainer on
omacom/omarchy-plugin-marketplace#11315 against the shipped 0.13.6: D-LOGO-11
bounded the dimensions a logo's header declares, and `write_logo` then cached
the provider's bytes unchanged, so every compressed ancillary chunk in a PNG
-- zTXt, iTXt, iCCP and the rest -- reached the shell's decoder, which
inflates them, and nothing the plugin checks bounds what they inflate to.

The fix (the owner's "option 1", 2026-10-13) is to rewrite every PNG logo to
a canonical file holding IHDR, PLTE, IDAT, IEND and the four small fixed-size
colour chunks tRNS, gAMA, cHRM and sRGB, walking the chunk list WITHOUT
decompressing anything, verifying every CRC, and refusing a file whose
structure is broken. The IDAT bytes are copied untouched, so the pixels
cannot change.

How this module is shaped, and why:

* Every image here is an ORDINARY small one, built in-process from the
  stdlib: a 2x2 picture carrying a short `Comment`, a short iTXt, an iCCP
  holding a profile the size of a plain sRGB one, a private chunk. The fix is
  judged by what it keeps and what it drops, which images like these prove
  completely; nothing here builds a large or highly compressible payload, and
  nothing measures memory.
* The assertions read the output with this module's OWN chunk walker, which
  shares no code with the helper's. Every verdict comes from calling the
  shipping function (`canonical_png`, `write_logo`, `cmd_logos`, and the
  helper as a subprocess), never from a re-derivation of its rules (rule 12).
* "The pixels do not change" is asserted twice: the IDAT chunks are
  byte-identical, and their concatenation inflates to exactly the scanlines
  the test built.
"""
import argparse
import binascii
import contextlib
import io
import json
import os
import random
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper

helper = load_helper()

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER_BIN = os.path.join(os.path.dirname(HERE), "bin", "omarchy-iptv")
SIGNATURE = b"\x89PNG\r\n\x1a\n"
KEPT = (b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB")


# ---- building ordinary PNGs ------------------------------------------------

def chunk(kind, body=b"", crc=None):
    """One chunk: length, type, data, and the CRC over type and data."""
    if crc is None:
        crc = binascii.crc32(kind + body) & 0xFFFFFFFF
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)


def ihdr(width=2, height=2, depth=8, colour=6):
    return chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, colour, 0, 0, 0))


def png(*chunks):
    return SIGNATURE + b"".join(chunks)


# 2x2 RGBA, filter type 0 on both rows: red, green / blue, half-white.
RGBA_SCANLINES = (b"\x00" + bytes((255, 0, 0, 255, 0, 255, 0, 255))
                  + b"\x00" + bytes((0, 0, 255, 255, 255, 255, 255, 128)))
RGBA_IDAT = zlib.compress(RGBA_SCANLINES)
# 2x2 palette (colour type 3, 8-bit): indices 0 1 / 2 0.
PALETTE_SCANLINES = b"\x00\x00\x01" + b"\x00\x02\x00"
PALETTE = bytes((255, 0, 0, 0, 255, 0, 0, 0, 255))      # three entries
GREY_SCANLINES = b"\x00\x10\x80" + b"\x00\xff\x00"
RGB_SCANLINES = b"\x00" + bytes(range(6)) + b"\x00" + bytes(range(6, 12))

GAMA = chunk(b"gAMA", struct.pack(">I", 45455))
CHRM = chunk(b"cHRM", struct.pack(">8I", 31270, 32900, 64000, 33000,
                                  30000, 60000, 15000, 6000))
SRGB = chunk(b"sRGB", b"\x00")
TEXT = chunk(b"tEXt", b"Comment\x00made by a test")
ZTXT = chunk(b"zTXt", b"Comment\x00\x00" + zlib.compress(b"a short compressed comment"))
ITXT = chunk(b"iTXt", b"Title\x00\x00\x00en\x00Title\x00a short title")
EXIF = chunk(b"eXIf", b"MM\x00\x2a\x00\x00\x00\x08\x00\x00")
PHYS = chunk(b"pHYs", struct.pack(">IIB", 2835, 2835, 1))
TIME = chunk(b"tIME", struct.pack(">HBBBBB", 2026, 10, 15, 12, 0, 0))
BKGD = chunk(b"bKGD", struct.pack(">HHH", 255, 255, 255))
PRIVATE = chunk(b"prVt", b"a provider's own chunk")
ACTL = chunk(b"acTL", struct.pack(">II", 1, 0))


def icc_like_profile():
    """3,144 bytes, the size of the common sRGB IEC61966-2.1 profile: a
    128-byte header with the profile size and the `acsp` signature where the
    format puts them, then deterministic pseudo-random bytes so it compresses
    about as poorly as a real profile does. Nothing ever parses it: the helper
    walks chunks without inflating any of them, and it is dropped."""
    body = bytearray(random.Random(13).randbytes(3144))
    body[0:4] = struct.pack(">I", 3144)
    body[36:40] = b"acsp"
    return bytes(body)


ICCP = chunk(b"iCCP", b"sRGB built-in\x00\x00" + zlib.compress(icc_like_profile()))


def rgba_with_everything():
    """The ordinary provider logo: colour chunks the decoder may use, every
    kind of metadata it must not see, and the image data split across two
    IDAT chunks the way encoders write large images."""
    half = len(RGBA_IDAT) // 2
    return png(ihdr(), GAMA, CHRM, SRGB, ICCP, TEXT, ZTXT, ITXT, EXIF, PHYS,
               TIME, BKGD, PRIVATE, ACTL,
               chunk(b"IDAT", RGBA_IDAT[:half]), chunk(b"IDAT", RGBA_IDAT[half:]),
               TEXT, chunk(b"IEND"))


def canonical_rgba():
    half = len(RGBA_IDAT) // 2
    return png(ihdr(), GAMA, CHRM, SRGB,
               chunk(b"IDAT", RGBA_IDAT[:half]), chunk(b"IDAT", RGBA_IDAT[half:]),
               chunk(b"IEND"))


def forged_crc_suffix(prefix, target=0):
    """Four bytes that make crc32(prefix + them) == target. CRC-32 is affine
    over GF(2) in a message of fixed length, so this is a 32x32 linear solve:
    one column per bit of the suffix, eliminated top bit first."""
    base = binascii.crc32(prefix + bytes(4))
    basis = []
    for bit in range(32):
        vector = binascii.crc32(prefix + (1 << bit).to_bytes(4, "little")) ^ base
        tag = 1 << bit
        for known, known_tag in basis:
            if vector ^ known < vector:
                vector, tag = vector ^ known, tag ^ known_tag
        if vector:
            basis.append((vector, tag))
            basis.sort(reverse=True)
    want, suffix = base ^ target, 0
    for known, known_tag in basis:
        if want ^ known < want:
            want, suffix = want ^ known, suffix ^ known_tag
    assert want == 0
    return suffix.to_bytes(4, "little")


# ---- reading them back, independently of the helper --------------------------

def walk(data):
    """[(type, body, crc_ok)] for a PNG, asserting only the signature and
    that the chunks tile the file exactly."""
    assert data[:8] == SIGNATURE, "no PNG signature"
    out, pos = [], 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        crc = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]
        out.append((kind, body, crc == binascii.crc32(kind + body) & 0xFFFFFFFF))
        pos += 12 + length
    assert pos == len(data), "the chunks do not tile the file"
    return out


def types(data):
    return [kind for kind, _, _ in walk(data)]


def scanlines(data):
    """Every IDAT body, concatenated and inflated: the raw scanlines the
    decoder will unfilter into pixels."""
    return zlib.decompress(b"".join(body for kind, body, _ in walk(data) if kind == b"IDAT"))


def _fixture():
    """The D-LOGO-11 corpus, for the real JPEG, GIF and WEBP files in it."""
    with open(os.path.join(HERE, "fixtures", "logo-dimensions.json"), encoding="ascii") as handle:
        return {case["id"]: binascii.unhexlify(case["hex"]) for case in json.load(handle)["cases"]}


FIXTURE = _fixture()


def private_tmpdir(case):
    path = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, path, True)
    return path


class CanonicalPngKeepsWhatDrawingNeedsTest(unittest.TestCase):
    """What survives, in what order, and that the pixels are untouched."""

    def test_metadata_is_dropped_and_the_drawing_chunks_are_kept_in_order(self):
        out = helper.canonical_png(rgba_with_everything())
        self.assertIsNotNone(out)
        self.assertEqual(types(out), [b"IHDR", b"gAMA", b"cHRM", b"sRGB",
                                      b"IDAT", b"IDAT", b"IEND"])
        for kind in (b"tEXt", b"zTXt", b"iTXt", b"iCCP", b"eXIf", b"pHYs",
                     b"tIME", b"bKGD", b"prVt", b"acTL"):
            self.assertNotIn(kind, types(out), kind)

    def test_every_chunk_written_carries_a_valid_crc(self):
        out = helper.canonical_png(rgba_with_everything())
        self.assertTrue(all(ok for _, _, ok in walk(out)), walk(out))

    def test_the_image_data_is_copied_untouched_and_decodes_to_the_same_scanlines(self):
        before = rgba_with_everything()
        out = helper.canonical_png(before)
        self.assertEqual([c for c in walk(out) if c[0] == b"IDAT"],
                         [c for c in walk(before) if c[0] == b"IDAT"])
        self.assertEqual(scanlines(out), RGBA_SCANLINES)
        # And the kept chunks are the input's own bytes, not re-encodings.
        kept_in = [c for c in walk(before) if c[0] in KEPT]
        self.assertEqual(walk(out), kept_in)

    def test_a_png_that_is_already_canonical_comes_back_byte_for_byte(self):
        """The cached-file branch announces a PNG only when it is canonical,
        so canonical has to be a fixed point: a file this writes must read as
        canonical on every later run, or it is rewritten on every start."""
        already = canonical_rgba()
        self.assertEqual(helper.canonical_png(already), already)
        once = helper.canonical_png(rgba_with_everything())
        self.assertEqual(once, already)
        self.assertEqual(helper.canonical_png(once), once)

    def test_a_palette_image_keeps_its_palette_and_its_transparency(self):
        source = png(ihdr(colour=3), GAMA, chunk(b"PLTE", PALETTE),
                     chunk(b"tRNS", b"\x00\x80"), TEXT,
                     chunk(b"IDAT", zlib.compress(PALETTE_SCANLINES)), chunk(b"IEND"))
        out = helper.canonical_png(source)
        self.assertEqual(types(out), [b"IHDR", b"gAMA", b"PLTE", b"tRNS", b"IDAT", b"IEND"])
        self.assertEqual(scanlines(out), PALETTE_SCANLINES)

    def test_trns_is_kept_only_at_the_length_its_colour_type_defines(self):
        """tRNS is the one kept chunk whose length depends on the image: two
        bytes for greyscale, six for truecolour, at most one per palette
        entry, and none at all with an alpha channel. A wrong length is
        dropped, which is what the decoder does with it too; the image is
        still cached."""
        def with_trns(colour, trns, scan, plte=None):
            parts = [ihdr(colour=colour)]
            if plte is not None:
                parts.append(chunk(b"PLTE", plte))
            parts += [chunk(b"tRNS", trns), chunk(b"IDAT", zlib.compress(scan)), chunk(b"IEND")]
            return helper.canonical_png(png(*parts))
        kept = [(0, b"\x00\x10", GREY_SCANLINES, None),
                (2, b"\x00\x01\x00\x02\x00\x03", RGB_SCANLINES, None),
                (3, b"\x00", PALETTE_SCANLINES, PALETTE),
                (3, b"\x00\x40\x80", PALETTE_SCANLINES, PALETTE)]
        dropped = [(0, b"\x00\x10\x00\x10\x00\x10", GREY_SCANLINES, None),
                   (2, b"\x00\x10", RGB_SCANLINES, None),
                   (3, b"\x00\x40\x80\xff", PALETTE_SCANLINES, PALETTE),   # 4 > 3 entries
                   (3, b"", PALETTE_SCANLINES, PALETTE),
                   (6, b"\x00\x10", RGBA_SCANLINES, None),
                   (4, b"\x00\x10", b"\x00\x10\x80\xff\x00" * 2, None)]
        for colour, trns, scan, plte in kept:
            out = with_trns(colour, trns, scan, plte)
            self.assertIsNotNone(out, (colour, trns))
            self.assertIn(b"tRNS", types(out), (colour, trns))
        for colour, trns, scan, plte in dropped:
            out = with_trns(colour, trns, scan, plte)
            self.assertIsNotNone(out, (colour, trns))
            self.assertNotIn(b"tRNS", types(out), (colour, trns))

    def test_a_colour_chunk_with_the_wrong_length_is_dropped_and_the_image_kept(self):
        for bad in (chunk(b"gAMA", b"\x00\x00\xb1\x8f\x00"), chunk(b"gAMA", b""),
                    chunk(b"cHRM", b"\x00" * 31), chunk(b"sRGB", b"\x00\x00")):
            out = helper.canonical_png(png(ihdr(), bad, chunk(b"IDAT", RGBA_IDAT),
                                           chunk(b"IEND")))
            self.assertEqual(types(out), [b"IHDR", b"IDAT", b"IEND"], bad[4:8])

    def test_only_the_first_of_each_colour_chunk_is_kept(self):
        second = chunk(b"gAMA", struct.pack(">I", 100000))
        out = helper.canonical_png(png(ihdr(), GAMA, second, SRGB, SRGB,
                                       chunk(b"IDAT", RGBA_IDAT), chunk(b"IEND")))
        self.assertEqual(types(out), [b"IHDR", b"gAMA", b"sRGB", b"IDAT", b"IEND"])
        self.assertEqual(walk(out)[1][1], struct.pack(">I", 45455), "the first gAMA")
        # "First" means the first one KEPT: one dropped for its length does
        # not shut out a sound one after it, which libpng would use too.
        out = helper.canonical_png(png(ihdr(), chunk(b"gAMA", b"\x00" * 5), GAMA,
                                       chunk(b"IDAT", RGBA_IDAT), chunk(b"IEND")))
        self.assertEqual(types(out), [b"IHDR", b"gAMA", b"IDAT", b"IEND"])
        self.assertEqual(walk(out)[1][1], struct.pack(">I", 45455))

    def test_colour_chunks_out_of_their_place_are_dropped(self):
        """gAMA, cHRM and sRGB belong before PLTE and IDAT, and tRNS before
        IDAT; the decoder ignores one out of place, so it is dropped rather
        than handed over."""
        late = helper.canonical_png(png(ihdr(), chunk(b"IDAT", RGBA_IDAT), GAMA, SRGB,
                                        chunk(b"IEND")))
        self.assertEqual(types(late), [b"IHDR", b"IDAT", b"IEND"])
        after_plte = helper.canonical_png(png(ihdr(colour=3), chunk(b"PLTE", PALETTE),
                                              GAMA, CHRM, SRGB,
                                              chunk(b"IDAT", zlib.compress(PALETTE_SCANLINES)),
                                              chunk(b"tRNS", b"\x00"), chunk(b"IEND")))
        self.assertEqual(types(after_plte), [b"IHDR", b"PLTE", b"IDAT", b"IEND"])

    def test_animation_chunks_are_dropped_and_the_default_image_kept(self):
        """APNG's frames travel in fdAT, compressed like IDAT, and Qt's PNG
        reader draws the default image only. Dropping them leaves exactly
        what is drawn."""
        fctl = chunk(b"fcTL", struct.pack(">IIIIIHHBB", 0, 2, 2, 0, 0, 1, 10, 0, 0))
        fdat = chunk(b"fdAT", struct.pack(">I", 1) + RGBA_IDAT)
        out = helper.canonical_png(png(ihdr(), ACTL, fctl, chunk(b"IDAT", RGBA_IDAT),
                                       fctl, fdat, chunk(b"IEND")))
        self.assertEqual(types(out), [b"IHDR", b"IDAT", b"IEND"])
        self.assertEqual(scanlines(out), RGBA_SCANLINES)


class CanonicalPngRefusesWhatItCannotWalkTest(unittest.TestCase):
    """None means "do not cache". Each of these is a file whose chunk list
    cannot be walked to a clean IEND, so it cannot be proved to hold only
    what the canonical form keeps."""

    def assertRefused(self, data, why):
        self.assertIsNone(helper.canonical_png(data), why)

    def test_a_bad_crc_is_refused_on_a_kept_chunk_and_on_a_dropped_one(self):
        """Every CRC is checked, including those of chunks about to be
        dropped: a bad CRC means the walk is not reading the file's chunks,
        and a dropped chunk is the easiest place to hide that."""
        self.assertRefused(png(ihdr(), chunk(b"IDAT", RGBA_IDAT, crc=0), chunk(b"IEND")),
                           "IDAT with a bad CRC")
        self.assertRefused(png(ihdr(), chunk(b"tEXt", b"Comment\x00x", crc=1),
                               chunk(b"IDAT", RGBA_IDAT), chunk(b"IEND")),
                           "a dropped tEXt with a bad CRC")
        good = canonical_rgba()
        flipped = bytearray(good)
        flipped[-1] ^= 0x01                                    # IEND's CRC
        self.assertRefused(bytes(flipped), "IEND with a bad CRC")

    def test_a_truncated_file_is_refused_at_every_cut(self):
        whole = rgba_with_everything()
        for cut in range(8, len(whole)):
            self.assertRefused(whole[:cut], "cut at %d of %d" % (cut, len(whole)))

    def test_anything_after_iend_is_refused(self):
        base = canonical_rgba()
        self.assertRefused(base + b"\x00", "one trailing byte")
        self.assertRefused(base + TEXT, "a whole chunk after IEND")
        self.assertRefused(base + chunk(b"IEND"), "a second IEND")

    def test_more_than_the_chunk_ceiling_is_refused_and_the_ceiling_itself_is_not(self):
        """A fixed maximum number of chunks, so the walk is bounded by a
        number and not only by the byte cap. The filler is EMPTY private
        chunks, twelve bytes each and no payload at all."""
        ceiling = helper.MAX_PNG_CHUNKS
        self.assertEqual(ceiling, 4096)
        filler = chunk(b"prVt")
        at = png(ihdr(), filler * (ceiling - 3), chunk(b"IDAT", RGBA_IDAT), chunk(b"IEND"))
        self.assertEqual(types(helper.canonical_png(at)), [b"IHDR", b"IDAT", b"IEND"])
        over = png(ihdr(), filler * (ceiling - 2), chunk(b"IDAT", RGBA_IDAT), chunk(b"IEND"))
        self.assertRefused(over, "one chunk over the ceiling")

    def test_a_broken_structure_is_refused(self):
        idat, iend = chunk(b"IDAT", RGBA_IDAT), chunk(b"IEND")
        plte_scan = chunk(b"IDAT", zlib.compress(PALETTE_SCANLINES))
        cases = {
            "no signature": b"\x89PNX\r\n\x1a\n" + ihdr() + idat + iend,
            "empty": b"",
            "signature only": SIGNATURE,
            "no IDAT": png(ihdr(), iend),
            "no IEND": png(ihdr(), idat),
            "IHDR not first": png(GAMA, ihdr(), idat, iend),
            "no IHDR at all": png(GAMA, idat, iend),
            "IDAT where IHDR belongs": png(idat, iend),
            "IHDR twice": png(ihdr(), ihdr(), idat, iend),
            "IHDR of the wrong length": png(chunk(b"IHDR", b"\x00" * 12), idat, iend),
            "IDAT split by another chunk": png(ihdr(), idat, TEXT, idat, iend),
            "PLTE twice": png(ihdr(colour=3), chunk(b"PLTE", PALETTE),
                              chunk(b"PLTE", PALETTE), plte_scan, iend),
            "PLTE after IDAT": png(ihdr(colour=3), plte_scan, chunk(b"PLTE", PALETTE), iend),
            "PLTE not a multiple of three": png(ihdr(colour=3), chunk(b"PLTE", PALETTE[:-1]),
                                                plte_scan, iend),
            "PLTE empty": png(ihdr(colour=3), chunk(b"PLTE", b""), plte_scan, iend),
            "PLTE over 256 entries": png(ihdr(colour=3), chunk(b"PLTE", b"\x00" * 771),
                                         plte_scan, iend),
            "IEND carrying data": png(ihdr(), idat, chunk(b"IEND", b"\x00")),
            "an unknown critical chunk": png(ihdr(), chunk(b"CRIT", b"\x00"), idat, iend),
            "a chunk type that is not four letters": png(ihdr(), chunk(b"ab1d"), idat, iend),
            "a length over the format's 2**31-1, past the end as any such length is":
                png(ihdr(), idat)[:] + struct.pack(">I", 0x80000000) + b"IEND",
        }
        for why, data in cases.items():
            self.assertRefused(data, why)

    def test_it_is_tolerant_of_rubbish_rather_than_raising(self):
        # A cut-off IHDR whose four bytes are chosen so the CRC over what is
        # there reads as the zero a missing CRC field reads as: the CRC check
        # passes, and only the end-of-file check stands between the walk and
        # an index past the last byte.
        cut = SIGNATURE + struct.pack(">I", 13) + b"IHDR" + forged_crc_suffix(b"IHDR")
        self.assertEqual(binascii.crc32(cut[12:]), 0)
        for blob in (None, "a string", 42, SIGNATURE + b"\xff" * 64, cut,
                     bytearray(canonical_rgba())):
            try:
                result = helper.canonical_png(blob)
            except Exception as error:                      # noqa: BLE001
                self.fail("%r raised %r" % (type(blob).__name__, error))
            if isinstance(blob, bytearray):
                self.assertEqual(result, bytes(blob), "a bytearray is a PNG like bytes is")


class WriteLogoCachesTheCanonicalFormTest(unittest.TestCase):
    """The gate: `write_logo` stores the canonical form, or nothing."""

    URL = "https://logos.provider.test/channel-one.png"

    def logo_dir(self):
        return os.path.join(private_tmpdir(self), "logos")

    def test_the_file_on_disk_holds_only_the_drawing_chunks(self):
        target = self.logo_dir()
        name = helper.write_logo(target, self.URL, rgba_with_everything(), "image/png")
        path = os.path.join(target, name)
        with open(path, "rb") as handle:
            on_disk = handle.read()
        self.assertEqual(on_disk, canonical_rgba())
        self.assertEqual(scanlines(on_disk), RGBA_SCANLINES)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o700)

    def test_a_malformed_png_is_refused_with_its_own_code_and_writes_nothing(self):
        for why, data in (("bad CRC", png(ihdr(), chunk(b"IDAT", RGBA_IDAT, crc=7), chunk(b"IEND"))),
                          ("after IEND", canonical_rgba() + TEXT),
                          ("no IEND", png(ihdr(), chunk(b"IDAT", RGBA_IDAT)))):
            target = self.logo_dir()
            with self.assertRaises(helper.HelperError, msg=why) as caught:
                helper.write_logo(target, self.URL + "?token=SECRET", data, "image/png")
            self.assertEqual(caught.exception.code, "logo_chunks", why)
            message = caught.exception.message
            self.assertIn("logos.provider.test", message, why)
            for leak in ("://", "channel-one", "SECRET"):
                self.assertNotIn(leak, message, "%s: the refusal carries %r" % (why, leak))
            self.assertFalse(os.path.exists(target), "%s created %s" % (why, target))

    def test_the_dimension_bound_still_runs_before_the_chunk_walk(self):
        """D-LOGO-11's refusal keeps its own code: a well-formed PNG whose
        header declares 20000x20000 is `logo_dimensions`, not `logo_chunks`."""
        target = self.logo_dir()
        bomb = png(ihdr(20000, 20000), chunk(b"IDAT", RGBA_IDAT), chunk(b"IEND"))
        with self.assertRaises(helper.HelperError) as caught:
            helper.write_logo(target, self.URL, bomb, "image/png")
        self.assertEqual(caught.exception.code, "logo_dimensions")

    def test_the_other_three_types_are_still_written_as_they_came(self):
        by_id = FIXTURE
        for cid, ctype in (("jpeg-small-baseline", "image/jpeg"), ("gif-small", "image/gif"),
                           ("webp-small-vp8x", "image/webp")):
            target = self.logo_dir()
            name = helper.write_logo(target, self.URL, by_id[cid], ctype)
            with open(os.path.join(target, name), "rb") as handle:
                self.assertEqual(handle.read(), by_id[cid], cid)


class LogoFetchCanonicalTest(unittest.TestCase):
    """`logos --fetch` end to end over the fetch path, with `fetch_logo` the
    one function replaced (it is the network), as tests/test_logos.py does."""

    def run_fetch(self, served):
        cache = private_tmpdir(self)
        urls = sorted(served)
        with open(os.path.join(cache, helper.CHANNELS_FILE), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "channels": [
                {"id": "c%d" % i, "name": "C%d" % i, "group": "G",
                 "url": "http://127.0.0.1/%d" % i, "logo": url} for i, url in enumerate(urls)]},
                handle)
        real = helper.fetch_logo
        helper.fetch_logo = lambda url, timeout, budget=None: (served[url], "image/png")
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                helper.cmd_logos(argparse.Namespace(cache_dir=cache, fetch=True,
                                                    survey=False, timeout=1))
        finally:
            helper.fetch_logo = real
        lines = [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]
        return os.path.join(cache, helper.LOGO_SUBDIR), lines[-1]

    def test_a_fetched_logo_is_cached_canonical_and_a_malformed_one_not_at_all(self):
        good, bad = "https://cdn.test/good.png", "https://cdn.test/bad.png"
        logo_dir, summary = self.run_fetch({
            good: rgba_with_everything(),
            bad: png(ihdr(), chunk(b"tEXt", b"Comment\x00x", crc=3),
                     chunk(b"IDAT", RGBA_IDAT), chunk(b"IEND"))})
        good_name, bad_name = helper.logo_filename(good), helper.logo_filename(bad)
        self.assertEqual(summary["names"], [good_name], summary)
        self.assertEqual(summary["fetched"], 1, summary)
        self.assertEqual(summary["reasons"], {"logo_chunks": 1}, summary)
        self.assertEqual(summary["refusedOnPolicy"], 1, "a malformed file is a policy refusal")
        with open(os.path.join(logo_dir, good_name), "rb") as handle:
            self.assertEqual(handle.read(), canonical_rgba())
        self.assertEqual(sorted(os.listdir(logo_dir)), [good_name])


class LogoCachedFileCanonicalTest(unittest.TestCase):
    """The cache earlier versions wrote holds the provider's bytes verbatim.

    The cached-file branch of `logos --fetch` announces a PNG only once it is
    canonical: one already canonical is announced untouched, one that is not
    is rewritten in place (atomically, 0600) and then announced, and one that
    cannot be walked is swept and falls through to the fetch. Run as the
    SUBPROCESS the service runs, against a dead loopback port so a swept file's
    refetch fails at once without leaving this machine.
    """

    DEAD = "https://127.0.0.1:1/%s.png"

    def plant(self, blobs):
        cache = private_tmpdir(self)
        logo_dir = os.path.join(cache, helper.LOGO_SUBDIR)
        os.makedirs(logo_dir, mode=0o700)
        channels, names = [], {}
        for index, (key, blob) in enumerate(sorted(blobs.items())):
            url = self.DEAD % key
            names[key] = helper.logo_filename(url)
            path = os.path.join(logo_dir, names[key])
            with open(path, "wb") as handle:
                handle.write(blob)
            os.chmod(path, 0o600)
            channels.append({"id": "c%d" % index, "name": "C%d" % index, "group": "G",
                             "url": "http://127.0.0.1/%d" % index, "logo": url})
        with open(os.path.join(cache, helper.CHANNELS_FILE), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "channels": channels}, handle)
        return cache, logo_dir, names

    def run_logos(self, cache):
        done = subprocess.run([sys.executable, HELPER_BIN, "logos", "--fetch", "--cache-dir",
                               cache, "--timeout", "2"],
                              capture_output=True, text=True, env=dict(os.environ), timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = [json.loads(l) for l in done.stdout.splitlines() if l.strip()]
        return lines[-1], [l["name"] for l in lines if l.get("kind") == "logo"]

    def read(self, logo_dir, name):
        with open(os.path.join(logo_dir, name), "rb") as handle:
            return handle.read()

    def test_a_cached_png_with_metadata_is_rewritten_canonical_in_place_and_announced(self):
        cache, logo_dir, names = self.plant({"old": rgba_with_everything()})
        summary, announced = self.run_logos(cache)
        self.assertEqual(announced, [names["old"]])
        self.assertEqual(summary["names"], [names["old"]], summary)
        self.assertEqual((summary["cached"], summary["rewritten"], summary["swept"],
                          summary["fetched"]), (1, 1, 0, 0), summary)
        self.assertEqual(self.read(logo_dir, names["old"]), canonical_rgba())
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(logo_dir, names["old"])).st_mode),
                         0o600)
        self.assertEqual(os.listdir(logo_dir), [names["old"]], "a temporary file was left")
        # The next start finds it canonical and leaves it alone.
        ino = os.stat(os.path.join(logo_dir, names["old"])).st_ino
        again, announced_again = self.run_logos(cache)
        self.assertEqual(announced_again, [names["old"]])
        self.assertEqual((again["cached"], again["rewritten"], again["swept"]), (1, 0, 0), again)
        self.assertEqual(os.stat(os.path.join(logo_dir, names["old"])).st_ino, ino)

    def test_a_cached_png_already_canonical_is_announced_and_not_touched(self):
        cache, logo_dir, names = self.plant({"canon": canonical_rgba()})
        path = os.path.join(logo_dir, names["canon"])
        before = os.stat(path)
        summary, announced = self.run_logos(cache)
        self.assertEqual(announced, [names["canon"]])
        self.assertEqual((summary["cached"], summary.get("rewritten", 0)), (1, 0), summary)
        after = os.stat(path)
        self.assertEqual((after.st_ino, after.st_mtime_ns), (before.st_ino, before.st_mtime_ns))

    def test_a_cached_png_that_cannot_be_walked_is_swept_and_never_announced(self):
        broken = {
            "bad-crc": png(ihdr(), chunk(b"tEXt", b"Comment\x00x", crc=9),
                           chunk(b"IDAT", RGBA_IDAT), chunk(b"IEND")),
            "after-iend": canonical_rgba() + TEXT,
            "no-iend": png(ihdr(), chunk(b"IDAT", RGBA_IDAT)),
        }
        cache, logo_dir, names = self.plant(dict(broken, good=canonical_rgba()))
        summary, announced = self.run_logos(cache)
        self.assertEqual(announced, [names["good"]])
        self.assertEqual(summary["names"], [names["good"]], summary)
        self.assertEqual((summary["cached"], summary["swept"], summary["rewritten"]),
                         (1, 3, 0), summary)
        self.assertEqual(sorted(os.listdir(logo_dir)), [names["good"]])
        # Swept files fall through to the fetch, which D-SINK-40 refuses
        # before any connect: the dead host is 127.0.0.1, and a logo never
        # reaches an address on this machine.
        self.assertEqual((summary["failed"], summary["refusedOnPolicy"], summary["reasons"]),
                         (0, 3, {"local_address": 3}), summary)

    def test_a_cached_png_longer_than_the_byte_cap_is_swept_as_the_gate_would_refuse_it(self):
        """An ordinary 300x300 picture stored WITHOUT compression (zlib level
        0, so every byte of it is a pixel byte and nothing in it inflates),
        360 KB: well-formed and canonical, and over MAX_LOGO_BYTES, which
        `fetch_logo` never lets through. The cache read stops one byte past
        the cap, so such a file never walks to its IEND, and the sweep and the
        gate agree about it instead of the sweep announcing what the gate
        would refuse. The header alone (all D-LOGO-11 reads) passes it."""
        width = 300
        row = (bytes(range(256)) * 5)[:width * 4]
        big = png(ihdr(width, width), chunk(b"IDAT", zlib.compress((b"\x00" + row) * width, 0)),
                  chunk(b"IEND"))
        self.assertGreater(len(big), helper.MAX_LOGO_BYTES)
        self.assertEqual(helper.canonical_png(big), big, "canonical: only its size is wrong")
        cache, logo_dir, names = self.plant({"big": big})
        self.assertTrue(helper.logo_file_within_bounds(os.path.join(logo_dir, names["big"])))
        summary, announced = self.run_logos(cache)
        self.assertEqual(announced, [])
        self.assertEqual((summary["cached"], summary["swept"]), (0, 1), summary)
        self.assertEqual(os.listdir(logo_dir), [])

    def test_cached_jpeg_gif_and_webp_files_are_left_exactly_as_they_are(self):
        by_id = FIXTURE
        blobs = {cid: by_id[cid] for cid in ("jpeg-small-progressive", "gif-small",
                                              "webp-small-vp8l")}
        cache, logo_dir, names = self.plant(blobs)
        before = {cid: os.stat(os.path.join(logo_dir, names[cid])).st_ino for cid in blobs}
        summary, announced = self.run_logos(cache)
        self.assertEqual(sorted(announced), sorted(names.values()))
        self.assertEqual((summary["cached"], summary.get("rewritten", 0)), (3, 0), summary)
        for cid, blob in blobs.items():
            self.assertEqual(self.read(logo_dir, names[cid]), blob, cid)
            self.assertEqual(os.stat(os.path.join(logo_dir, names[cid])).st_ino, before[cid], cid)


QML_BIN = "/usr/lib/qt6/bin/qml"

# Every file named on the command line becomes an Image declared as the
# guide's slots are (no sourceSize: the full decode, the strictest compare);
# once all are Ready each is grabbed to "<file>.grab.png". The exit status is
# the verdict -- 0 every grab saved, 1 an Image.Error, 2 the timer -- so two
# files that BOTH failed to load can never compare equal as two blank grabs.
GRAB_QML = """
import QtQuick
import QtQuick.Window
Window {
  id: win
  width: 64; height: 64; visible: true
  property var files: Qt.application.arguments.slice(Qt.application.arguments.indexOf("--") + 1)
  property int ready: 0
  property int saved: 0
  Repeater {
    id: images
    model: win.files
    Image {
      source: "file://" + modelData
      asynchronous: false
      cache: false
      onStatusChanged: {
        if (status === Image.Error) Qt.exit(1)
        if (status === Image.Ready && ++win.ready === win.files.length) grabAll.start()
      }
    }
  }
  Timer {
    id: grabAll
    interval: 50
    onTriggered: {
      for (var i = 0; i < win.files.length; i++) {
        var path = win.files[i]
        images.itemAt(i).grabToImage(function (path) { return function (r) {
          r.saveToFile(path + ".grab.png"); if (++win.saved === win.files.length) Qt.exit(0) } }(path))
      }
    }
  }
  Timer { interval: 20000; running: true; onTriggered: Qt.exit(2) }
}
"""


@unittest.skipUnless(os.access(QML_BIN, os.X_OK), "Qt's qml runtime is not installed")
class QtDrawsTheSamePixelsTest(unittest.TestCase):
    """The sink itself: Qt's own PNG reader, in a QML Image offscreen, draws
    the canonical file exactly as it draws the provider's. The chunks dropped
    carry no pixels, and this is where that is observed rather than argued.
    Run with HOME and every XDG directory in a scratch directory (Qt writes a
    cache under HOME) and, where util-linux has it, under the address-space
    cap the logo scenario puts on its probe."""

    def test_the_canonical_file_and_the_original_are_drawn_identically(self):
        root = private_tmpdir(self)
        sources = {
            "rgba": rgba_with_everything(),
            "palette": png(ihdr(colour=3), GAMA, ICCP, chunk(b"PLTE", PALETTE),
                           chunk(b"tRNS", b"\x00\x80"), TEXT, ITXT,
                           chunk(b"IDAT", zlib.compress(PALETTE_SCANLINES)), PRIVATE,
                           chunk(b"IEND")),
            "grey": png(ihdr(colour=0), SRGB, ZTXT, chunk(b"tRNS", b"\x00\x10"), EXIF,
                        chunk(b"IDAT", zlib.compress(GREY_SCANLINES)), chunk(b"IEND")),
        }
        files = []
        for key, blob in sources.items():
            canon = helper.canonical_png(blob)
            self.assertNotEqual(canon, blob, "%s: nothing was dropped, so nothing is compared" % key)
            for suffix, data in (("orig", blob), ("canon", canon)):
                files.append(os.path.join(root, "%s-%s.png" % (key, suffix)))
                with open(files[-1], "wb") as handle:
                    handle.write(data)
        qml = os.path.join(root, "grab.qml")
        with open(qml, "w", encoding="ascii") as handle:
            handle.write(GRAB_QML)
        home = os.path.join(root, "home")
        env = {"PATH": "/usr/bin:/bin", "HOME": home, "XDG_CACHE_HOME": home + "/.cache",
               "XDG_CONFIG_HOME": home + "/.config", "XDG_DATA_HOME": home + "/.local/share",
               "LANG": "C.UTF-8", "QT_FORCE_STDERR_LOGGING": "1",
               "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"}
        cap = ["prlimit", "--as=2500000000", "--"] if shutil.which("prlimit") else []
        done = subprocess.run(cap + [QML_BIN, qml, "--"] + files, env=env, capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(done.returncode, 0, "the probe did not grab every image:\n" + done.stderr)
        for key in sources:
            grabs = []
            for suffix in ("orig", "canon"):
                with open(os.path.join(root, "%s-%s.png.grab.png" % (key, suffix)), "rb") as handle:
                    grabs.append(handle.read())
            self.assertEqual(scanlines(grabs[0]), scanlines(grabs[1]), key)
            self.assertEqual(walk(grabs[0])[0][1][:8], struct.pack(">II", 2, 2), key)


if __name__ == "__main__":
    unittest.main()
