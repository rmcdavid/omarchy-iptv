"""D-SINK-95 and D-SINK-96 (2026-11-11): the redactors' reading of a URL in
free text, and of a credential token, stated one character at a time for
the suites that hold a parser, a cut or the fold to it (test_attr_grammar,
test_group_split, test_epg_fold, test_cut_urls).

Every class here is this file's own literal, never the helper's or the
model's, and the walk keeps no `dead` bound: the shipping readings bound
their scheme walk by where the last failed one started, which is claimed to
change no answer, and these suites check that claim on every text they
generate. tests/test_url_marks.py and tests/fixtures/url-mark.json hold both
shipping readings to the same answers; tests/test_redaction_cost.py states
the same rule a second way, as one pattern.

The reading. Every pair of SLASHes with only FILLER between them is asked,
left to right; P is the run of `:` and FILLER that ends at the pair's first
slash, never reaching below `low`; the pair is a MARK when P holds a `:` or
a STAND_IN. Its scheme starts at the first letter of the nearest SCHEME
segment before P that holds a letter, crossing CROSSABLE runs between
letterless segments, and never below `low`; a mark with none is no URL. The
run is from the mark's end to the first of the six delimiters. A token is a
run of characters other than U+0020 in the free text between URLs; it is
withheld when it holds a `:` with an `@` after it.
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


def scheme_start(text, at, low):
    k = at
    while True:
        seg_end = k
        while k > low and scheme_char(text[k - 1]):
            k -= 1
        for q in range(k, seg_end):
            if letter(text[q]):
                return q
        crossed = False
        while k > low and crossable(text[k - 1]):
            k -= 1
            crossed = True
        if not crossed:
            return -1


def first_url(text, low=0, need_body=False):
    """(scheme start, mark start, mark end, run end) of the first URL at or
    after `low`, or None. `need_body`: an empty run is no URL (the
    helper's redactor)."""
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
        a = k
        while a > low and (text[a - 1] == ":" or filler(text[a - 1])):
            a -= 1
        p = text[a:k]
        if ":" in p or any(stand_in(c) for c in p):
            start = scheme_start(text, a, low)
            if start >= 0:
                end = m + 1
                while end < n and text[end] not in DELIMITERS:
                    end += 1
                if end > m + 1 or not need_body:
                    return start, a, m + 1, end
        k = m
    return None


def urls(text, need_body=False, low=0):
    """Every URL the reading finds, each from the end of the run before it."""
    out = []
    while True:
        url = first_url(text, low, need_body)
        if url is None:
            return out
        out.append(url)
        low = url[3]


def tokens(text, start=0, end=None):
    """(start, end) of every withheld token in text[start:end], one piece of
    free text."""
    end = len(text) if end is None else end
    out = []
    i = start
    while i < end:
        if text[i] == " ":
            i += 1
            continue
        j = i
        while j < end and text[j] != " ":
            j += 1
        colon = text.find(":", i, j)
        if colon >= 0 and text.find("@", colon + 1, j) >= 0:
            out.append((i, j))
        i = j
    return out


def free_pieces(text, need_body=False):
    """The free text between the URLs: [(start, end)]."""
    out = []
    pos = 0
    for url in urls(text, need_body):
        out.append((pos, url[0]))
        pos = url[3]
    out.append((pos, len(text)))
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
    wide = -1 if url is None else url[1]
    if narrow < 0 or wide < 0:
        return max(narrow, wide)
    return min(narrow, wide)
