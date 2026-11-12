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
an ASCII `:` outside every URL span with an ASCII `@` after it in the token
and at most one COUNTED code point (above U+009F, no slash look-alike)
outside the URL spans between them; the first such `:` decides. It is
withheld from the token's start, or, when the token holds two or more
counted code points outside the URL spans before that `:`, from just after
the last of them, to the token's end less its trailing punctuation.
"""

DELIMITERS = "\t\n\x0b\x0c\r "
SLASH_ALIKES = frozenset(map(chr, (0x1735, 0x2041, 0x2044, 0x2215, 0x2571, 0x27CB, 0x29F8, 0x2F03, 0x3033,
                                   0x31D3, 0xFF0F)))
# The reader's union above U+009F (tests/fixtures/url-whitespace.json):
# FILLER, never a STAND_IN.
SPACES_ABOVE_C1 = frozenset(map(chr, (0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F,
                                      0x3000, 0xFEFF)))
TRAILING = ".,;:!?)]'\"<>"
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


def credential(text, i, j, url_list):
    """For the token text[i:j]: (its credential's `:`, that `:`'s `@`, the
    withheld span's start), or None."""
    def inside(x):
        return any(u[0] <= x < u[3] for u in url_list)
    for c in range(i, j):
        if text[c] != ":" or inside(c):
            continue
        a = text.find("@", c + 1, j)
        if a < 0:
            return None
        if sum(1 for x in range(c + 1, a) if counted(text[x]) and not inside(x)) <= 1:
            before = [x for x in range(i, c) if counted(text[x]) and not inside(x)]
            return c, a, (i if len(before) <= 1 else before[-1] + 1)
    return None


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
