"""D-LOGO-25 (2026-10-29): a JPEG logo with more scans than MAX_JPEG_SCANS
is refused at the gate and swept from the cache.

The dimension bound (D-LOGO-11) bounds what the decoder allocates, not how
long it works: a progressive JPEG is decoded scan by scan, and a file within
the byte cap can carry thousands of scans. Measured on Qt 6.11.2 with an
Image declared as the row slot and with djpeg, on files of 1 to 512 scans:
about 4.1 ms of CPU a refinement scan, on the shell's image reader thread,
which every other asynchronous image waits behind (docs/ARCHITECTURE.md,
security standard 12). Nothing here decodes: the gate counts.

Every file is built here, small (64x64, a few hundred bytes); the count is
what matters, not the size.
"""
import argparse
import contextlib
import io
import json
import os
import pathlib
import struct
import tempfile
import unittest
from unittest import mock

from helper_loader import load_helper

helper = load_helper()
HERE = pathlib.Path(__file__).resolve().parent
CASES = json.loads((HERE / "fixtures" / "logo-dimensions.json").read_text(encoding="ascii"))["cases"]


def segment(marker, body):
    return struct.pack(">BBH", 0xFF, marker, len(body) + 2) + body


def progressive_jpeg(scans, side=64, refine=True, pad=0, garbage=b""):
    """A progressive grayscale JPEG of `side` x `side`, all zero: one DC
    scan, then `scans - 1` AC scans (Ss=1..Se=63), each coding every block
    as end-of-band runs. `pad` bytes of APP15 segments go after the DC scan
    (legal between scans), so the frame header sits in the cached-file
    check's first read and the AC scans past it; `garbage` goes after them,
    where libjpeg skips it looking for the next marker."""
    blocks = (side // 8) ** 2
    out = bytearray(b"\xff\xd8")
    out += segment(0xDB, bytes([0]) + bytes([1] * 64))
    out += segment(0xC2, struct.pack(">BHHB", 8, side, side, 1) + bytes([1, 0x11, 0]))
    out += segment(0xC4, bytes([0x00]) + bytes([1] + [0] * 15) + bytes([0x00]))            # DC: '0'
    out += segment(0xC4, bytes([0x10]) + bytes([1, 1] + [0] * 14) + bytes([0xE0, 0x00]))   # AC: EOBRUN r=14 '0', EOB '10'
    out += segment(0xDA, bytes([1, 1, 0x00, 0, 0, 0x00])) + bytes((blocks + 7) // 8)       # every DC diff '0'
    while pad > 0:
        size = min(pad, 65533)
        out += segment(0xEF, b"\x00" * size)
        pad -= size
    out += garbage
    # Every block's end-of-band, '10' each, padded with ones; stuffed when a
    # byte is 0xFF.
    run_bits = "10" * blocks
    run_bits += "1" * (-len(run_bits) % 8)
    data = bytearray()
    for i in range(0, len(run_bits), 8):
        byte = int(run_bits[i:i + 8], 2)
        data.append(byte)
        if byte == 0xFF:
            data.append(0)
    ah = 0x10 if refine else 0x00
    for _ in range(scans - 1):
        out += segment(0xDA, bytes([1, 1, 0x00, 1, 63, ah])) + data
    out += b"\xff\xd9"
    return bytes(out)


class ScanCountTest(unittest.TestCase):
    def test_the_count_is_every_scan_the_file_holds(self):
        for scans in (1, 2, 10, 64, 65, 200):
            self.assertEqual(helper.jpeg_scan_count(progressive_jpeg(scans)), scans, scans)

    def test_a_scan_behind_garbage_or_fill_bytes_is_counted(self):
        """libjpeg resyncs past bytes that are not a marker and over 0xFF
        fill, so a scan it reaches that way must be counted too."""
        data = progressive_jpeg(3, garbage=b"junk not a marker\xff\xff\xff")
        self.assertEqual(helper.jpeg_scan_count(data), 3)

    def test_every_jpeg_in_the_dimension_fixture_is_within_the_scan_bound(self):
        jpegs = [c for c in CASES if c["contentType"] == "image/jpeg"]
        self.assertTrue(jpegs)
        for case in jpegs:
            data = bytes.fromhex(case["hex"])
            self.assertLessEqual(helper.jpeg_scan_count(data), helper.MAX_JPEG_SCANS, case["id"])
            self.assertTrue(helper.logo_scans_within_bound(data, "image/jpeg"), case["id"])

    def test_the_bound_is_a_jpeg_rule_only(self):
        png = bytes.fromhex(next(c["hex"] for c in CASES if c["id"] == "png-small"))
        many = png + b"\xff\xda" * (helper.MAX_JPEG_SCANS + 1)
        for ctype in ("image/png", "image/gif", "image/webp"):
            self.assertTrue(helper.logo_scans_within_bound(many, ctype), ctype)


class GateTest(unittest.TestCase):
    URL = "https://logos.example.test/many.jpg"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.logo_dir = os.path.join(tmp.name, "logos")

    def test_at_the_bound_it_is_written_and_one_over_it_is_refused(self):
        name = helper.write_logo(self.logo_dir, self.URL, progressive_jpeg(helper.MAX_JPEG_SCANS), "image/jpeg")
        self.assertTrue(os.path.isfile(os.path.join(self.logo_dir, name)))
        os.unlink(os.path.join(self.logo_dir, name))
        with self.assertRaises(helper.HelperError) as caught:
            helper.write_logo(self.logo_dir, self.URL, progressive_jpeg(helper.MAX_JPEG_SCANS + 1), "image/jpeg")
        self.assertEqual(caught.exception.code, "logo_scans")
        self.assertEqual(caught.exception.message,
                         "refused a logo from logos.example.test: its JPEG carries %d scans, over the %d scan bound"
                         % (helper.MAX_JPEG_SCANS + 1, helper.MAX_JPEG_SCANS))
        self.assertEqual(os.listdir(self.logo_dir), [], "a refusal writes nothing")

    def test_first_scans_count_as_refinement_scans_do(self):
        with self.assertRaises(helper.HelperError):
            helper.write_logo(self.logo_dir, self.URL, progressive_jpeg(helper.MAX_JPEG_SCANS + 1, refine=False), "image/jpeg")


class CachedFileTest(unittest.TestCase):
    """A file already on disk -- written before this bound existed -- is
    judged over ALL of its bytes: a count over the cached-file check's
    first read is a lower bound and proves nothing."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name

    def write(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_within_and_over_the_bound(self):
        self.assertTrue(helper.logo_file_within_bounds(self.write("a", progressive_jpeg(helper.MAX_JPEG_SCANS))))
        self.assertFalse(helper.logo_file_within_bounds(self.write("b", progressive_jpeg(helper.MAX_JPEG_SCANS + 1))))

    def test_scans_past_the_first_read_are_counted(self):
        data = progressive_jpeg(helper.MAX_JPEG_SCANS + 1, pad=helper.LOGO_HEADER_BYTES)
        self.assertLess(len(data), helper.MAX_LOGO_BYTES)
        head = data[:helper.LOGO_HEADER_BYTES]
        # The first read proves the header and holds one scan: a count over
        # it alone would pass the file.
        self.assertTrue(helper.logo_within_bounds(head, "image/jpeg"))
        self.assertEqual(helper.jpeg_scan_count(head), 1)
        self.assertFalse(helper.logo_file_within_bounds(self.write("c", data)))
        self.assertTrue(helper.logo_file_within_bounds(
            self.write("d", progressive_jpeg(helper.MAX_JPEG_SCANS, pad=helper.LOGO_HEADER_BYTES))))

    def test_the_run_sweeps_a_cached_file_over_the_bound_and_refuses_it_at_the_gate(self):
        cache = os.path.join(self.dir, "sources", "0123abcd")
        os.makedirs(os.path.join(cache, helper.LOGO_SUBDIR), mode=0o700)
        url = "https://logos.example.test/many.jpg"
        with open(os.path.join(cache, helper.CHANNELS_FILE), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "count": 1, "channels": [
                {"id": "c0", "name": "C0", "group": "G", "url": "http://127.0.0.1/0", "logo": url}]}, handle)
        bomb = progressive_jpeg(helper.MAX_JPEG_SCANS + 1)
        with open(os.path.join(cache, helper.LOGO_SUBDIR, helper.logo_filename(url)), "wb") as handle:
            handle.write(bomb)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(helper, "fetch_logo", lambda u, t, b=None: (bomb, "image/jpeg")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper.cmd_logos(argparse.Namespace(cache_dir=cache, fetch=True, survey=False, timeout=5))
        summary = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual((summary["swept"], summary["cached"], summary["refusedOnPolicy"]), (1, 0, 1), summary)
        self.assertEqual(summary["reasons"], {"logo_scans": 1}, summary)
        self.assertEqual(summary["names"], [])
        self.assertEqual(os.listdir(os.path.join(cache, helper.LOGO_SUBDIR)), [])


if __name__ == "__main__":
    unittest.main()
