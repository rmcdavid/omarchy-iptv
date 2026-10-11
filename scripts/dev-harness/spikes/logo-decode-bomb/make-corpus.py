#!/usr/bin/env python3
"""make-corpus.py -- craft the D-LOGO-11 logo corpus from code.

Why this is a generator and not a directory of committed binaries: the whole
finding is that a logo's DECLARED dimensions and its BYTE COUNT are
independent, and a generator is the only form of that statement a reader can
check. Every file below names its declared width and height as arguments, so
"304 bytes buy 840 MB" is visible in the call rather than asserted in a
README. It also keeps a 665 KB bomb out of the repository.

Python 3 standard library only, deliberately. CLAUDE.md rule 3 binds
bin/omarchy-iptv rather than a spike, but scripts/check.sh runs
logo-scenario.sh on every commit and that scenario builds its fixtures with
this file: a corpus that needed ImageMagick would make the gate depend on
whatever is installed. ASCII only (rule 8).

WHAT "CRAFTED" MEANS PER FORMAT, said plainly so nobody mistakes a synthetic
file for an encoder's output:

  JPEG   Built marker by marker. The quantisation tables, the Huffman tables
         and the entropy-coded scans are opaque known-good byte strings
         lifted from a minimal 64x64 JPEG (the lead's small-base.jpg,
         small-prog.jpg and small-prog-rgb.jpg, read with a segment dumper);
         the SOF -- precision, HEIGHT, WIDTH, component count -- is
         constructed here from the arguments. That split is the point: the
         bomb is the SOF and the SOF is code, not a patched byte offset.
         A JPEG whose SOF says 20000x20000 over a 64x64 scan is a MALFORMED
         file, and that is what makes it interesting: libjpeg allocates for
         the header before it discovers the scan is short.
  PNG    Entirely valid, built from zlib. An honestly huge 1-bit PNG is
         cheap (20000x20000 compresses to about 76 KB of zeros), so this
         format gets both treatments -- a rewritten IHDR with a repaired CRC
         AND a file that really is that big -- with no encoder.
  GIF    Entirely valid, including the LZW. The encoder here emits literals
         and a Clear code often enough that the code width never grows,
         which is legal and simple rather than efficient; a 64x64 frame
         costs about 2 KB. GIF carries a canvas size and a frame size
         separately, so "huge canvas, small frame" is a VALID file, and that
         is the honest-huge GIF case.
  WEBP   Header only, and this file is the one place that limitation is
         written down. A valid VP8 keyframe bitstream needs a real encoder;
         what is built here is a correct RIFF/WEBP container whose VP8
         frame header declares the dimensions, over a body that is not a
         decodable keyframe. That is enough to drive a header parser and
         enough to drive file(1), and it is NOT enough to reach
         Image.Ready -- so no WEBP here is ever used as a sink positive
         control. Pass --with-encoder to add encoder-made WEBP and JPEG
         files when ImageMagick is on the machine.

USAGE
  python3 make-corpus.py <outdir> [--with-encoder] [--only <name>,...]
  python3 make-corpus.py --list

It prints one line per file: name, bytes, and the dimensions the header
declares, so the caller can see the corpus it got. --list prints the table
without writing anything.
"""

import argparse
import os
import struct
import subprocess
import sys
import zlib

# ---- the opaque JPEG payloads. Everything here is entropy-coding data for a
# 64x64 image; none of it mentions a dimension. Dumped from the three minimal
# JPEGs named in the module docstring. A segment is (marker, body) and the
# body EXCLUDES the two length bytes, which build_jpeg writes.
DQT_LUMA = bytes.fromhex(
    "00140e0f120f0d14121012171514181e32211e1c1c1e3d2c2e243249404c4b47"
    "404645505a736250556d5645466488656d777b8182814e608d978c7d96737e817c")
DQT_CHROMA = bytes.fromhex(
    "011517171e1a1e3b21213b7c5346537c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c"
    "7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c7c")
APP0_JFIF = bytes.fromhex("4a46494600010100000100010000")

# Baseline grayscale: one DC table, one AC table, one scan.
BASE_GRAY_TAIL = [
    (0xC4, bytes.fromhex("00010100000000000000000000000000000001")),
    (0xC4, bytes.fromhex("100100000000000000000000000000000000")),
    (0xDA, bytes.fromhex("010100003f00")),
    ("SCAN", bytes.fromhex("800000000000000000000000000000003f")),
]

# Progressive grayscale: the six-scan sequence a progressive encoder emits.
PROG_GRAY_TAIL = [
    (0xC4, bytes.fromhex("00010100000000000000000000000000000001")),
    (0xDA, bytes.fromhex("010100000001")),
    ("SCAN", bytes.fromhex("80000000000000003f")),
    (0xC4, bytes.fromhex("100100000000000000000000000000000060")),
    (0xDA, bytes.fromhex("010100010502")),
    ("SCAN", bytes.fromhex("01")),
    (0xC4, bytes.fromhex("100100000000000000000000000000000060")),
    (0xDA, bytes.fromhex("010100063f02")),
    ("SCAN", bytes.fromhex("01")),
    (0xC4, bytes.fromhex("100100000000000000000000000000000060")),
    (0xDA, bytes.fromhex("010100013f21")),
    ("SCAN", bytes.fromhex("01")),
    (0xDA, bytes.fromhex("010100000010")),
    ("SCAN", bytes.fromhex("ff00ff00ff00ff00ff00ff00ff00ff00")),
    (0xC4, bytes.fromhex("100100000000000000000000000000000060")),
    (0xDA, bytes.fromhex("010100013f10")),
    ("SCAN", bytes.fromhex("01")),
]

# Progressive 3-component, 4:2:0. Three coefficient planes rather than one,
# which is where 304 bytes became 555 and 840 MB became 1,239 MB.
PROG_RGB_TAIL = [
    (0xC4, bytes.fromhex("00010100000000000000000000000000000002")),
    (0xC4, bytes.fromhex("01010100000000000000000000000000000002")),
    (0xDA, bytes.fromhex("03010002100310000001")),
    ("SCAN", bytes.fromhex("815000000000000000000000007f")),
    (0xC4, bytes.fromhex("100100000000000000000000000000000060")),
    (0xDA, bytes.fromhex("010100010502")),
    ("SCAN", bytes.fromhex("01")),
    (0xC4, bytes.fromhex("110100000000000000000000000000000040")),
    (0xDA, bytes.fromhex("010301013f01")),
    ("SCAN", bytes.fromhex("07")),
    (0xC4, bytes.fromhex("110100000000000000000000000000000040")),
    (0xDA, bytes.fromhex("010201013f01")),
    ("SCAN", bytes.fromhex("07")),
    (0xC4, bytes.fromhex("100100000000000000000000000000000060")),
    (0xDA, bytes.fromhex("010100063f02")),
    ("SCAN", bytes.fromhex("01")),
    (0xC4, bytes.fromhex("100100000000000000000000000000000060")),
    (0xDA, bytes.fromhex("010100013f21")),
    ("SCAN", bytes.fromhex("01")),
    (0xDA, bytes.fromhex("03010002000300000010")),
    ("SCAN", bytes.fromhex("ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00")),
    (0xC4, bytes.fromhex("110100000000000000000000000000000040")),
    (0xDA, bytes.fromhex("010301013f10")),
    ("SCAN", bytes.fromhex("07")),
    (0xC4, bytes.fromhex("110100000000000000000000000000000040")),
    (0xDA, bytes.fromhex("010201013f10")),
    ("SCAN", bytes.fromhex("07")),
    (0xC4, bytes.fromhex("100100000000000000000000000000000060")),
    (0xDA, bytes.fromhex("010100013f10")),
    ("SCAN", bytes.fromhex("01")),
]

SOF_BASELINE = 0xC0
SOF_PROGRESSIVE = 0xC2


def sof_body(width, height, components):
    """The one segment this file builds rather than quotes.

    Precision 8, then HEIGHT then WIDTH (that order is the format's, and
    getting it backwards is the classic way to craft a bomb that measures the
    wrong axis), then the component count, then one 3-byte descriptor per
    component: id, sampling factors, quantisation table 0 for luma and 1 for
    chroma. The sampling factors are what the lifted scans were ENCODED for
    and nothing else: grayscale is 0x11, and the 3-component case is 4:2:0
    (luma 0x22, chroma 0x11), because that is what the lead's 555-byte file
    carries and the scan data lifted from it only parses under that MCU
    layout. The first version of this function wrote 0x11 for all three and
    called it "the most expensive case"; the file it produced was 555 bytes
    with a different byte 170, the control did not match the lead's, and the
    1,239 MB figure had been measured on the other layout. Expensive is the
    wrong axis anyway -- the bomb is the dimension, not the subsampling.
    """
    body = bytes([8]) + struct.pack(">HH", height, width) + bytes([components])
    for index in range(components):
        sampling = 0x22 if (components == 3 and index == 0) else 0x11
        body += bytes([index + 1, sampling, 0 if index == 0 else 1])
    return body


def build_jpeg(width, height, kind):
    """A JPEG whose SOF says width x height, over a 64x64 scan.

    kind is "baseline", "progressive" or "progressive-rgb".
    """
    if kind == "baseline":
        marker, tail, comps, tables = SOF_BASELINE, BASE_GRAY_TAIL, 1, [DQT_LUMA]
    elif kind == "progressive":
        marker, tail, comps, tables = SOF_PROGRESSIVE, PROG_GRAY_TAIL, 1, [DQT_LUMA]
    elif kind == "progressive-rgb":
        marker, tail, comps, tables = (SOF_PROGRESSIVE, PROG_RGB_TAIL, 3,
                                       [DQT_LUMA, DQT_CHROMA])
    else:
        raise ValueError("unknown jpeg kind %r" % kind)
    out = [b"\xff\xd8"]

    def segment(code, body):
        out.append(bytes([0xFF, code]) + struct.pack(">H", len(body) + 2) + body)

    segment(0xE0, APP0_JFIF)
    for table in tables:
        segment(0xDB, table)
    segment(marker, sof_body(width, height, comps))
    for code, body in tail:
        if code == "SCAN":
            out.append(body)
        else:
            segment(code, body)
    out.append(b"\xff\xd9")
    return b"".join(out)


def build_jpeg_no_sof():
    """A JPEG with the right magic and no frame header at all.

    This is the R4 case -- "the gate refuses unless it can prove the file is
    within the bound" -- and it is not a hypothetical shape: it is what a
    truncated download looks like. It passes a magic-byte check and no
    dimension can be read from it.
    """
    body = APP0_JFIF
    return (b"\xff\xd8" + bytes([0xFF, 0xE0]) + struct.pack(">H", len(body) + 2)
            + body + DQT_LUMA[:16])


# ---- PNG


def png_chunk(kind, payload):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def build_png(width, height, bit_depth=8, declared=None):
    """A valid PNG of width x height, optionally LYING in its IHDR.

    `declared` rewrites the IHDR dimensions and repairs the CRC, which is the
    PNG equivalent of the SOF rewrite; with `declared` None the file is
    entirely valid and really is that big. Grayscale, no interlace, filter 0
    rows of zeros, so a 20000x20000 1-bit file is about 76 KB of deflate.
    """
    row_bytes = (width * bit_depth + 7) // 8
    # Fed to the compressor a row at a time rather than assembled first. The
    # 65500x65500 1-bit case is 536 MB of raw scanlines, and the first version
    # of this function built that bytearray in memory and compressed it at
    # level 9: it had not finished after two minutes. Streaming at level 6
    # takes seconds and holds one row.
    compressor = zlib.compressobj(6)
    row = b"\x00" + b"\x00" * row_bytes
    parts = []
    for _ in range(height):
        chunk = compressor.compress(row)
        if chunk:
            parts.append(chunk)
    parts.append(compressor.flush())
    ihdr_w, ihdr_h = (declared if declared else (width, height))
    ihdr = struct.pack(">IIBBBBB", ihdr_w, ihdr_h, bit_depth, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr)
            + png_chunk(b"IDAT", b"".join(parts))
            + png_chunk(b"IEND", b""))


# ---- GIF


class BitPacker:
    """LSB-first bit packer, which is GIF's order (and not PNG's or JPEG's)."""

    def __init__(self):
        self.out = bytearray()
        self.cur = 0
        self.bits = 0

    def put(self, code, width):
        self.cur |= code << self.bits
        self.bits += width
        while self.bits >= 8:
            self.out.append(self.cur & 0xFF)
            self.cur >>= 8
            self.bits -= 8

    def flush(self):
        if self.bits:
            self.out.append(self.cur & 0xFF)
            self.cur = 0
            self.bits = 0
        return bytes(self.out)


def gif_lzw(pixels, min_code_size=2):
    """A correct, deliberately unclever GIF LZW stream.

    Only literal codes and Clear codes are emitted, and a Clear is emitted
    before the decoder's table could ever force the code width up -- so every
    code in the stream is `min_code_size + 1` bits wide and no string table is
    ever consulted. That is legal GIF (a Clear is valid anywhere) and it is
    about 12 bits per 2 pixels, so a 64x64 frame costs roughly 2 KB. It is
    here because the alternative is an LZW encoder nobody on this project
    would want to debug inside a fixture generator.
    """
    width = min_code_size + 1
    clear = 1 << min_code_size
    end = clear + 1
    packer = BitPacker()
    packer.put(clear, width)
    since_clear = 0
    for pixel in pixels:
        # The decoder adds one table entry per code it reads after a Clear, so
        # after two codes the next entry would be `end + 2`; a Clear here keeps
        # the next entry below `1 << width` forever.
        if since_clear >= 2:
            packer.put(clear, width)
            since_clear = 0
        packer.put(pixel, width)
        since_clear += 1
    packer.put(end, width)
    return packer.flush()


def build_gif(frame_w, frame_h, canvas=None, declared_frame=None):
    """A GIF that carries dimensions in TWO places, and can lie in either.

    `frame_w`/`frame_h` are the pixels actually encoded. `canvas` is the
    logical screen size, which GIF stores separately: a huge canvas over a
    small frame is not malformed in any way -- it is what an animation that
    pans a sprite around looks like -- so canvas-only is the ENTIRELY VALID
    huge GIF, and it costs 2 KB. `declared_frame` additionally lies in the
    image descriptor, which is the rewritten-header case.

    Both levers exist because the first version of this function encoded a
    real 20000x20000 frame for the bomb and produced a 226 MB file: a bomb
    that is only dangerous if you can afford to store it is not this
    finding's bomb, and it filled the scratch directory proving it.
    """
    canvas_w, canvas_h = canvas if canvas else (frame_w, frame_h)
    desc_w, desc_h = declared_frame if declared_frame else (frame_w, frame_h)
    out = bytearray(b"GIF89a")
    out += struct.pack("<HH", canvas_w, canvas_h)
    out += bytes([0xF0, 0x00, 0x00])            # global table, 2 entries, 8 bpp
    out += bytes([0x7F, 0x7F, 0x7F, 0x00, 0x00, 0x00])
    # Graphic Control Extension: introducer, label, block size 4, four data
    # bytes, then the BLOCK TERMINATOR. The first version of this left the
    # terminator off, and the file still read as 64x64 to file(1) while
    # ImageMagick refused it with "negative or zero image size" -- a fixture
    # that a header reader accepts and a decoder does not is exactly the
    # fixture that would have made this scenario lie.
    out += bytes([0x21, 0xF9, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00])
    out += bytes([0x2C]) + struct.pack("<HHHH", 0, 0, desc_w, desc_h) + bytes([0x00])
    out += bytes([0x02])                        # LZW minimum code size
    data = gif_lzw([0] * (frame_w * frame_h), 2)
    for start in range(0, len(data), 255):
        block = data[start:start + 255]
        out += bytes([len(block)]) + block
    out += bytes([0x00, 0x3B])                  # block terminator, trailer
    return bytes(out)


# ---- WEBP (header only; see the module docstring)


def build_webp_header_only(width, height):
    """A RIFF/WEBP container whose VP8 frame header declares width x height.

    Frame tag: 3 bytes, key frame (bit 0 clear), version 0, show_frame set,
    partition length 0; then the 3-byte start code 9D 01 2A that a decoder
    looks for; then 14-bit width and height with a 2-bit scaling field each.
    The body after that is filler, so this reaches a header parser and
    file(1) and never reaches Image.Ready.
    """
    if not 1 <= width <= 0x3FFF or not 1 <= height <= 0x3FFF:
        raise ValueError("VP8 carries 14-bit dimensions; %dx%d does not fit"
                         % (width, height))
    vp8 = bytes([0x90, 0x03, 0x00]) + bytes([0x9D, 0x01, 0x2A])
    vp8 += struct.pack("<HH", width, height)
    vp8 += bytes(28)
    if len(vp8) % 2:
        vp8 += b"\x00"
    body = b"WEBP" + b"VP8 " + struct.pack("<I", len(vp8)) + vp8
    return b"RIFF" + struct.pack("<I", len(body)) + body


# ---- the corpus
#
# Each entry is (name, declared dimensions as a string for the log, builder).
# The names are the scenario's fixture names: logo-scenario.sh asks for them
# by name through --only, so this list and that script are joined by these
# strings (CLAUDE.md rule 13) and --only refuses a name it does not know
# rather than silently producing nothing.

CORPUS = [
    # ---- controls: in-bound, and the two the sink is asked about.
    ("ctl-base-64.jpg", "64x64", lambda: build_jpeg(64, 64, "baseline")),
    ("ctl-prog-64.jpg", "64x64", lambda: build_jpeg(64, 64, "progressive")),
    ("ctl-prog-rgb-64.jpg", "64x64", lambda: build_jpeg(64, 64, "progressive-rgb")),
    ("ctl-png-64.png", "64x64", lambda: build_png(64, 64)),
    ("ctl-gif-64.gif", "64x64", lambda: build_gif(64, 64)),
    ("ctl-webp-64.webp", "64x64", lambda: build_webp_header_only(64, 64)),
    # The sink positive control. A real 512x512 logo: entirely valid, drawn
    # by Qt, and the file logo-scenario.sh requires to be written, announced
    # and Ready. PNG because it is the format this generator can make
    # honestly without an encoder.
    ("good-512.png", "512x512", lambda: build_png(512, 512)),
    # The largest shape a real provider banner plausibly takes: 1920x1080 is
    # 2,073,600 pixels, half of MAX_LOGO_PIXELS, and it must pass.
    ("good-1920x1080.png", "1920x1080", lambda: build_png(1920, 1080)),
    # At the bound exactly: 4096 on the long side, 4,194,304 pixels. A gate
    # that refuses this one is wrong in the other direction.
    ("edge-at-bound.jpg", "4096x1024", lambda: build_jpeg(4096, 1024, "progressive")),
    ("edge-at-bound.png", "2048x2048", lambda: build_png(2048, 2048)),
    # ---- the two bounds, driven apart, so neither can be dropped unnoticed.
    ("edge-side-only.jpg", "5000x800",
     lambda: build_jpeg(5000, 800, "progressive")),        # 4.0 Mpx, side over
    ("edge-pixels-only.jpg", "2048x2049",
     lambda: build_jpeg(2048, 2049, "progressive")),       # both sides under
    # ---- the bombs. Tiny files, enormous headers.
    ("bomb-base-20000.jpg", "20000x20000", lambda: build_jpeg(20000, 20000, "baseline")),
    ("bomb-base-65500.jpg", "65500x65500", lambda: build_jpeg(65500, 65500, "baseline")),
    ("bomb-prog-20000.jpg", "20000x20000", lambda: build_jpeg(20000, 20000, "progressive")),
    ("bomb-prog-65500.jpg", "65500x65500", lambda: build_jpeg(65500, 65500, "progressive")),
    ("bomb-prog-rgb-20000.jpg", "20000x20000",
     lambda: build_jpeg(20000, 20000, "progressive-rgb")),
    ("bomb-prog-rgb-65500.jpg", "65500x65500",
     lambda: build_jpeg(65500, 65500, "progressive-rgb")),
    ("bomb-png-20000.png", "20000x20000",
     lambda: build_png(64, 64, declared=(20000, 20000))),
    ("bomb-png-65500.png", "65500x65500",
     lambda: build_png(64, 64, declared=(65500, 65500))),
    ("bomb-gif-20000.gif", "20000x20000",
     lambda: build_gif(64, 64, canvas=(20000, 20000),
                       declared_frame=(20000, 20000))),
    ("bomb-gif-65500.gif", "65500x65500",
     lambda: build_gif(64, 64, canvas=(65500, 65500),
                       declared_frame=(65500, 65500))),
    ("bomb-webp-16383.webp", "16383x16383",
     lambda: build_webp_header_only(16383, 16383)),
    # ---- honestly huge and entirely valid, which is the half of the finding
    # that cannot be waved away as "malformed input".
    ("valid-png-20000.png", "20000x20000", lambda: build_png(20000, 20000, bit_depth=1)),
    ("valid-png-65500.png", "65500x65500", lambda: build_png(65500, 65500, bit_depth=1)),
    ("valid-gif-canvas-20000.gif", "20000x20000",
     lambda: build_gif(64, 64, canvas=(20000, 20000))),
    ("valid-gif-canvas-65500.gif", "65500x65500",
     lambda: build_gif(64, 64, canvas=(65500, 65500))),
    # ---- the R4 case: magic bytes, allowed content type, no readable header.
    ("unreadable-no-sof.jpg", "none", build_jpeg_no_sof),
]

# Files that need a real encoder. --with-encoder adds them; nothing in
# scripts/check.sh asks for them.
ENCODER_CORPUS = [
    ("enc-webp-64.webp", "64x64", ["-size", "64x64", "gradient:red-blue"]),
    ("enc-prog-12000.jpg", "12000x12000",
     ["-size", "12000x12000", "-colorspace", "gray", "gradient:black-white",
      "-interlace", "Plane"]),
]


def write_corpus(outdir, only=None, with_encoder=False):
    os.makedirs(outdir, exist_ok=True)
    os.chmod(outdir, 0o700)
    wanted = None
    if only:
        wanted = [name.strip() for name in only.split(",") if name.strip()]
        known = set(name for name, _, _ in CORPUS)
        known |= set(name for name, _, _ in ENCODER_CORPUS)
        unknown = [name for name in wanted if name not in known]
        if unknown:
            sys.stderr.write("make-corpus: no such fixture: %s\n"
                             % ", ".join(sorted(unknown)))
            return 2
    written = 0
    for name, declared, builder in CORPUS:
        if wanted is not None and name not in wanted:
            continue
        data = builder()
        path = os.path.join(outdir, name)
        with open(path, "wb") as handle:
            handle.write(data)
        os.chmod(path, 0o600)
        print("%-28s %8d bytes  declares %s" % (name, len(data), declared))
        written += 1
    if with_encoder:
        for name, declared, recipe in ENCODER_CORPUS:
            path = os.path.join(outdir, name)
            if wanted is not None and name not in wanted:
                continue
            argv = ["magick"] + recipe + [path]
            try:
                subprocess.run(argv, check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except (OSError, subprocess.CalledProcessError) as error:
                sys.stderr.write("make-corpus: %s needs ImageMagick: %s\n"
                                 % (name, error))
                continue
            os.chmod(path, 0o600)
            print("%-28s %8d bytes  declares %s (encoder)"
                  % (name, os.path.getsize(path), declared))
            written += 1
    print("make-corpus: %d files in %s" % (written, outdir))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("outdir", nargs="?", help="where to write the corpus")
    parser.add_argument("--only", help="comma-separated fixture names")
    parser.add_argument("--with-encoder", action="store_true",
                        help="also build the files that need ImageMagick")
    parser.add_argument("--list", action="store_true",
                        help="print the corpus table and write nothing")
    args = parser.parse_args(argv)
    if args.list:
        for name, declared, _ in CORPUS:
            print("%-28s declares %s" % (name, declared))
        for name, declared, _ in ENCODER_CORPUS:
            print("%-28s declares %s (needs ImageMagick)" % (name, declared))
        return 0
    if not args.outdir:
        parser.error("an output directory is required unless --list is given")
    return write_corpus(args.outdir, args.only, args.with_encoder)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
