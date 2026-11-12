"""D-SINK-95 and D-SINK-96 (2026-11-11, restated by the review of cbd6679 on
2026-11-12): the redactors' reading of a URL in free text, and of a
credential token, stated one character at a time for the suites that hold a
parser, a cut or the fold to it (test_attr_grammar, test_group_split,
test_epg_fold, test_cut_urls, test_url_marks).

Every class here is this file's own literal, never the helper's or the
model's, and the walk keeps no `dead` bound: the shipping readings bound
their scheme walk by where the last failed one started, and skip a walk
with no letter before it, both claimed to change no answer, and these
suites check that claim on every text they generate.
tests/test_url_marks.py and tests/fixtures/url-mark.json hold both shipping
readings to the same answers; tests/test_redaction_cost.py states the same
rule a second way.

The reading. Every pair of SLASHes whose FILLER between them holds at most
one WIDE code point (above U+009F) is asked, left to right; P is the run of
`:` and FILLER that ends at the pair's first slash, never reaching below
`low`; the pair is a MARK when P holds a `:` or a STAND_IN and each FILLER
stretch of P between its colons holds at most one WIDE code point. Its
scheme starts at the first letter of the nearest SCHEME segment before P
that holds a letter, crossing CROSSABLE runs that hold at most one WIDE code
point each between letterless segments, and never below `low`; a mark with
none is no URL. The run is from the mark's end to the first of the six
delimiters, and may be empty.

A credential is a token -- a run of characters other than U+0020 -- holding
an ASCII `:` that is a credential's -- outside every URL span, or inside one
whose run holds no `@` after it (the review of 4d13d71) -- with an ASCII `@`
after it in the token and at most one code point of a script written
without spaces (SPACELESS, the review of 4d13d71; no slash look-alike)
outside the URL spans between them; the first such `:` decides. It is
withheld from the token's start, or, when the token holds two or more
COUNTED code points (above U+009F, no slash look-alike) outside the URL
spans before that `:`, from just after the last of them, to the token's
end less its trailing punctuation. And a URL starting in the token after
its start, whose scheme (its printable ASCII, lower-cased) is no NAMED one,
whose run holds an `@` and whose mark or run holds a `:` before that `@`,
makes the token a credential withheld from its start (the review of
4d13d71).
"""

DELIMITERS = "\t\n\x0b\x0c\r "
SLASH_ALIKES = frozenset(map(chr, (0x1735, 0x2041, 0x2044, 0x2215, 0x2571, 0x27CB, 0x29F8, 0x2F03, 0x3033,
                                   0x31D3, 0xFF0F)))
# The reader's union above U+009F (tests/fixtures/url-whitespace.json):
# FILLER, never a STAND_IN.
SPACES_ABOVE_C1 = frozenset(map(chr, (0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F,
                                      0x3000, 0xFEFF)))
TRAILING = ".,;:!?)]'\"<>"
# The scripts written without spaces, as the review of 4d13d71's lead call
# names them: Han, CJK symbols and kana, Hangul, Thai and Lao, Myanmar,
# Khmer, the halfwidth and fullwidth forms, and every astral code point.
SPACELESS = ((0x2E80, 0x2FDF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x3000, 0x30FF),
             (0x31F0, 0x31FF), (0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xAC00, 0xD7AF),
             (0xD7B0, 0xD7FF), (0x0E00, 0x0EFF), (0x1000, 0x109F), (0x1780, 0x17FF), (0xFF00, 0xFFEF),
             (0x10000, 0x10FFFF))
# The schemes the helper prints (D-SINK-94's list).
NAMED = frozenset(("http", "https", "rtmp", "rtmps", "rtsp", "udp", "rtp", "mms", "mmsh", "srt", "file", "ftp", "ftps",
                   "sftp", "data", "smb", "rtmpe", "rtmpt", "mmst", "tcp", "tls", "magnet", "acestream"))
WITHHELD = "[host withheld]"


def scheme_char(c):
    return c.isascii() and (c.isalnum() or c in "+.-")


def letter(c):
    return c.isascii() and c.isalpha()


def crossable(c):
    return not (" " <= c <= "~")


def slash(c):
    return c == "/" or c in SLASH_ALIKES


def filler(c):
    return crossable(c) and c not in SLASH_ALIKES


def stand_in(c):
    return filler(c) and ord(c) > 0x9F and c not in SPACES_ABOVE_C1


def deleted(c):
    return ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F


def wide(c):
    return ord(c) > 0x9F


def counted(c):
    return ord(c) > 0x9F and c not in SLASH_ALIKES


def spaceless(c):
    return counted(c) and any(a <= ord(c) <= b for a, b in SPACELESS)


def scheme_start(text, at, low):
    k = at
    while True:
        seg_end = k
        while k > low and scheme_char(text[k - 1]):
            k -= 1
        for q in range(k, seg_end):
            if letter(text[q]):
                return q
        cross_end = k
        while k > low and crossable(text[k - 1]):
            k -= 1
        if k == cross_end or sum(1 for c in text[k:cross_end] if wide(c)) > 1:
            return -1


def first_url(text, low=0):
    """(scheme start, mark start, mark end, run end) of the first URL at or
    after `low`, or None."""
    n = len(text)
    k = low
    while k < n and not slash(text[k]):
        k += 1
    while k < n:
        m = k + 1
        while m < n and filler(text[m]):
            m += 1
        if m >= n:
            return None
        if not slash(text[m]):
            k = m + 1
            while k < n and not slash(text[k]):
                k += 1
            continue
        if sum(1 for c in text[k + 1:m] if wide(c)) <= 1:
            a = k
            while a > low and (text[a - 1] == ":" or filler(text[a - 1])):
                a -= 1
            p = text[a:k]
            narrow = all(sum(1 for c in piece if wide(c)) <= 1 for piece in p.split(":"))
            if narrow and (":" in p or any(stand_in(c) for c in p)):
                start = scheme_start(text, a, low)
                if start >= 0:
                    end = m + 1
                    while end < n and text[end] not in DELIMITERS:
                        end += 1
                    return start, a, m + 1, end
        k = m
    return None


def urls(text, low=0):
    """Every URL the reading finds, each from the end of the run before it."""
    out = []
    while True:
        url = first_url(text, low)
        if url is None:
            return out
        out.append(url)
        low = url[3]


def trailing_keep(text):
    """How much of `text` to keep before its trailing punctuation (a `]` is
    kept when the text holds a `[`)."""
    bracket = "[" in text
    k = len(text)
    while k and text[k - 1] in TRAILING and not (bracket and text[k - 1] == "]"):
        k -= 1
    return k


def credential(text, i, j, url_list, pos=None):
    """For the token text[i:j]: (its credential's `:`, that `:`'s `@`, the
    withheld span's start), or None; with `pos`, the first whose `:` is at
    or after `pos` (the span's start still judged from `i`)."""
    lo = i if pos is None else pos

    def holder(x):
        for u in url_list:
            if u[0] <= x < u[3]:
                return u
        return None

    found = None
    for c in range(lo, j):
        if text[c] != ":":
            continue
        u = holder(c)
        if u is not None and "@" in text[c + 1:u[3]]:
            continue
        a = text.find("@", c + 1, j)
        if a < 0:
            break
        if sum(1 for x in range(c + 1, a) if spaceless(text[x]) and holder(x) is None) <= 1:
            before = [x for x in range(i, c) if counted(text[x]) and holder(x) is None]
            found = (c, a, i if len(before) <= 1 else before[-1] + 1)
            break
    held = None
    for u in url_list:
        if i < u[0] < j and u[0] >= lo and "@" in text[u[2]:u[3]]:
            at = text.index("@", u[2])
            scheme = "".join(ch for ch in text[u[0]:u[1]] if " " <= ch <= "~").lower()
            if ":" in text[u[1]:at] and scheme not in NAMED:
                held = (text.index(":", u[1]), at)
                break
    if held is None:
        return found
    if found is None or held[0] < found[0]:
        return held[0], held[1], i
    return found[0], found[1], i


def credentials(text, url_list=None):
    """(span start, span end, token end) of every credential in `text`."""
    url_list = urls(text) if url_list is None else url_list
    out = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == " ":
            i += 1
            continue
        j = i
        while j < n and text[j] != " ":
            j += 1
        found = credential(text, i, j, url_list)
        if found is not None:
            start = found[2]
            out.append((start, start + trailing_keep(text[start:j]), j))
        i = j
    return out


def narrow_mark(text, low=0):
    """Where the first `://` with only C0, DEL or C1 controls between its
    three characters starts at or after `low`, or -1 (the fetch side's
    _URL_MARK, which the parsers still read beside the wide mark)."""
    for i in range(low, len(text)):
        if text[i] != ":":
            continue
        j = i + 1
        ok = True
        for _ in range(2):
            while j < len(text) and deleted(text[j]):
                j += 1
            if j >= len(text) or text[j] != "/":
                ok = False
                break
            j += 1
        if ok:
            return i
    return -1


def mark_any(text, low=0):
    """The first mark either reading protects (url_mark_any), or -1."""
    narrow = narrow_mark(text, low)
    url = first_url(text, low)
    wide_mark = -1 if url is None else url[1]
    if narrow < 0 or wide_mark < 0:
        return max(narrow, wide_mark)
    return min(narrow, wide_mark)
