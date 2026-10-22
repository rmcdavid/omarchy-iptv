#!/usr/bin/env python3
"""Give every programme of a gen-playlist XMLTV an ordinary description,
category and episode number, so now AND next carry the three detail fields
(the shape lane-bounds-l measured D-EPG-11 on). Deterministic: the text is
a function of the programme's position. argv: in.xml out.xml"""
import re, sys
src, dst = sys.argv[1], sys.argv[2]
CATS = ["Entertainment", "News", "Sport", "Documentary", "Drama", "Film", "Children", "Music"]
DESC = ("A programme of ordinary length for the guide: two sentences that say what is on, who is in it and "
        "where it was made, the way a provider's feed describes a show. Nothing in it is unusual.")
n = 0
def fix(m):
    global n
    n += 1
    body = m.group(2)
    body = re.sub(r"<desc>.*?</desc>", "", body)
    return (m.group(1) + body + "<desc>" + DESC + " Entry %d.</desc>" % n
            + "<category>" + CATS[n % len(CATS)] + "</category>"
            + '<episode-num system="onscreen">S%02dE%02d</episode-num>' % (1 + n % 9, 1 + n % 24) + "</programme>")
text = open(src, encoding="utf-8").read()
out = re.sub(r"(<programme [^>]*>)(.*?)</programme>", fix, text, flags=re.S)
open(dst, "w", encoding="utf-8").write(out)
print("programmes with detail:", n)
