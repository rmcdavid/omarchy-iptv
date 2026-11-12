"""D-SINK-80 (2026-11-05): the M3U attribute grammar never ends a value
inside a URL's run.

parse_attrs ended a quoted value at its first `"` and a bare one at its
first `,`, `"` or Python whitespace, before any redactor saw it, and every
redactor reads those as URL text (R32a'''). So a credentialed URL in ANY
attribute, read or not, was stored cut -- `http://qqqqqq:zz`, which both
redactors print as the host `qqqqqq` -- and the rest of the line, the
password's tail first, became the channel's NAME, which no redactor
touches: the window title, the guide row, the bus, the notifications. On
#EXTM3U a cut guide hint was adopted with the username as its host. A URL
now takes the rest of its run (parse_attrs' docstring holds the rule), and a
tvg-id holding a URL is dropped.

tests/fixtures/attr-grammar.json holds the lines and what they parse to, the
helper's alone: the shell has no M3U parser. Here: every case through
parse_attrs and parse_extinf, a subset through parse_m3u's whole row, every
case's row held to the helper's sinks; a sweep of URL shapes, cut characters,
attributes, forms and positions through parse_m3u, held to the helper's sinks
and, in node, to the shell's; the rule against a reference written from its
statement over random lines; and linear time.

D-SINK-95 and D-SINK-96 (2026-11-11): a URL's run is also one the redactors'
reading finds behind a mark any odd character may break
(tests/url_reading_rule.py), and the sweep's scheme form with a delimiter
after its `//` is no longer D-SINK-34's cost: the token after the delimiter
is withheld at every sink.
"""
import json
import os
import random
import re
import subprocess
import time
import unittest

import url_reading_rule as rule
from helper_loader import load_helper

helper = load_helper()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
with open(os.path.join(HERE, "fixtures", "attr-grammar.json"), encoding="utf-8") as fh:
    FIXTURE = json.load(fh)
CASES = FIXTURE["cases"]
SECRET = FIXTURE["secret"]
STREAM = "http://stream.example.test/live/1.ts"
# The six ASCII delimiters every redactor ends a URL's run at (R32a'''),
# spelt out rather than read from the helper.
DELIMITERS = "\t\n\x0b\x0c\r "


def leaked(text):
    return [c for c in SECRET if c in str(text)]


def parse(line):
    """(attrs, title) for a whole #EXTINF or #EXTM3U line, the #EXTM3U
    remainder as parse_attrs returns it."""
    if line.startswith("#EXTM3U"):
        return helper.parse_attrs(line[len("#EXTM3U"):])
    return helper.parse_extinf(line)


def parse_line(line, title_line="#EXTINF:-1,Plain Title"):
    """parse_m3u over one line and a stream: (the document, its one row)."""
    if line.startswith("#EXTM3U"):
        text = line + "\n" + title_line + "\n" + STREAM + "\n"
    else:
        text = "#EXTM3U\n" + line + "\n" + STREAM + "\n"
    doc = helper.parse_m3u(text)
    assert len(doc["channels"]) == 1, line
    return doc, doc["channels"][0]


def shown_fields(doc, channel):
    """Every stored text a sink shows: the name, the groups, the tvg-name,
    the logo and the guide hint."""
    fields = [("name", channel["name"])]
    fields += [("group", g) for g in channel.get("groups", [channel["group"]])]
    fields += [(k, channel[k]) for k in ("tvgName", "logo") if k in channel]
    if doc["epgUrlHint"]:
        fields.append(("epgUrlHint", doc["epgUrlHint"]))
    return fields


def helper_sinks(field, value, plain=True):
    """The helper's sinks for one stored field: the player's title, which
    deletes control characters before it redacts, and where `plain` (no
    control inside a `://`, no delimiter inside the URL) its redactor, and
    for a logo the host the logo survey names."""
    out = [("player_title_text", helper.player_title_text(value))]
    if plain:
        out.append(("redact_urls", helper.redact_urls(value)))
        if field == "logo":
            out.append(("logo_survey", " ".join(h["host"] for h in helper.logo_survey([{"logo": value}])["hosts"])))
    return out


def shell_sinks(rows):
    """The shell's sinks, in node, over [{name, groups, tvgName, logo,
    epgUrlHint}]: Model.sinkText of every field, the body Model.notifyArgv
    posts for a stream that did not play, the logo consent text
    (Model.logoSurvey, Model.logoConsentLines) and the guide hint's host
    (Model.epgHintVerdict under an https playlist), adopted or refused. The
    consent text's own closing word "request" holds a `q`, so it is taken
    out before the text is read."""
    script = ('const M=require("./Model.mjs");'
              'const rows=JSON.parse(require("fs").readFileSync(0,"utf8"));'
              'process.stdout.write(JSON.stringify(rows.map(r=>{'
              'const out=[];'
              'for(const v of [r.name].concat(r.groups,r.tvgName?[r.tvgName]:[],r.logo?[r.logo]:[],'
              'r.epgUrlHint?[r.epgUrlHint]:[]))out.push(["sinkText",M.sinkText(v)]);'
              'const a=M.notifyArgv("streamFailed",{name:r.name,reason:"r"});out.push(["notifyArgv",a[a.length-1]]);'
              'if(r.logo)out.push(["logoConsentLines",M.logoConsentLines(M.logoSurvey([{logo:r.logo}]))'
              '.join(" ").split(" request.").join(" ")]);'
              'if(r.epgUrlHint){const h=M.epgHintVerdict({epgUrlHint:r.epgUrlHint},"https://prov.test/get.php");'
              'out.push(["epgHintVerdict",h.host+" "+(h.url?h.url.split("/")[2]:"")])}'
              'return out})))')
    done = subprocess.run(["node", "-e", script], input=json.dumps(rows), capture_output=True,
                          text=True, cwd=ROOT, timeout=300)
    if done.returncode != 0:
        raise AssertionError(done.stderr[-800:])
    return json.loads(done.stdout)


def shell_row(doc, channel):
    return {"name": channel["name"], "groups": channel.get("groups", [channel["group"]]),
            "tvgName": channel.get("tvgName", ""), "logo": channel.get("logo", ""),
            "epgUrlHint": doc["epgUrlHint"]}


class FixtureTest(unittest.TestCase):
    def test_the_fixture_is_whole(self):
        # A shrunken fixture goes red: the ordinary lines, the leak shapes,
        # the stated costs, D-SINK-34's class and the parsed rows all there.
        kinds = {"leak": [c for c in CASES if leaked(c["line"]) and "accepted" not in c],
                 "cost": [c for c in CASES if "cost" in c],
                 "accepted": [c for c in CASES if c.get("accepted") == "D-SINK-34"],
                 "stored": [c for c in CASES if "stored" in c],
                 "header": [c for c in CASES if c["line"].startswith("#EXTM3U")]}
        self.assertEqual((len(CASES), {k: len(v) for k, v in kinds.items()}),
                         (109, {"leak": 66, "cost": 10, "accepted": 4, "stored": 43, "header": 9}))
        self.assertTrue(all(not leaked(c["line"]) for c in kinds["cost"]))
        self.assertEqual(SECRET, "qz")

    def test_parse_attrs_and_parse_extinf_answer_every_case(self):
        for c in CASES:
            self.assertEqual(list(parse(c["line"])), [c["attrs"], c["title"]], (c["why"], c["line"]))

    def test_parse_m3u_stores_the_row_each_case_names(self):
        for c in CASES:
            if "stored" not in c:
                continue
            doc, channel = parse_line(c["line"])
            for key, want in c["stored"].items():
                got = doc["epgUrlHint"] if key == "epgUrlHint" else channel.get(key)
                if key == "id" and want.endswith(":"):
                    self.assertTrue(got.startswith(want), (c["why"], got))
                else:
                    self.assertEqual(got, want, (c["why"], key))

    def test_no_stored_field_shows_a_credential_at_a_helper_sink(self):
        # D-SINK-34's accepted class aside: there a delimiter inside the URL
        # ends its run at every redactor, whatever the grammar does.
        bad = []
        for c in CASES:
            if "accepted" in c:
                continue
            doc, channel = parse_line(c["line"])
            for field, value in shown_fields(doc, channel):
                bad += [(c["line"], field, sink, out) for sink, out in helper_sinks(field, value, c.get("plain", True))
                        if leaked(out)]
            if leaked(channel["id"]):
                bad.append((c["line"], "id", channel["id"]))
        self.assertEqual(bad, [])

    def test_the_accepted_cases_leak_at_the_redactor_itself(self):
        # So they are D-SINK-34's class and not the grammar's: the URL as
        # written, its delimiter inside, already prints a fragment.
        for c in CASES:
            if "accepted" in c:
                url = c["line"][c["line"].index("http://"):]
                url = url[:url.index("@")] + "@cdn.test/x"
                self.assertTrue(any(ch in url for ch in DELIMITERS), c["why"])
                self.assertTrue(leaked(helper.redact_urls(url)), c["why"])


# The oracle sweep (the critic's M2): every URL form, cut character,
# attribute, form and position through parse_m3u, held to every sink, and
# each URL-bearing value held to its host exactly, so a grammar that drops
# values cannot pass -- except that a logo or a guide hint whose value ran
# past where every earlier release ended it is stored as none (the recheck
# of the review's F1, own_value), and that is held exactly too: a bare
# one always does here, since every cut character ended a bare value, and a
# quoted one when the cut holds a `"`. `{c}` is the cut character.
FORMS = {"user": "http://qq{c}qqqq:zzzzzz@cdn.test/x",
         "pass": "http://qqqqqq:zz{c}zzzz@cdn.test/x",
         "path": "http://cdn.test/live/qqqqqq/zz{c}zz/1.ts",
         "query": "http://cdn.test/get.php?username=qqqqqq&password=zz{c}zz",
         "scheme": "http://{c}qqqqqq:zzzzzz@cdn.test/x"}
# What ended a value early: the quote, the quote and comma, the comma, and
# every whitespace Python's class holds that no redactor ends a URL at.
CUTS = ['"', '",', ","] + [chr(cp) for cp in (0xa0, 0x1680, *range(0x2000, 0x200b), 0x2028, 0x2029,
                                             0x202f, 0x205f, 0x3000, 0x85, 0x1c, 0x1d, 0x1e, 0x1f)]
# D-SINK-34's class: an ASCII delimiter inside the URL.
ACCEPTED_CUTS = [" ", "\t", "\x0b", "\x0c", "\r"]
EXTINF_ATTRS = ["group-title", "tvg-name", "tvg-logo", "tvg-id", "catchup-source"]
HEADER_ATTRS = ["url-tvg", "x-tvg-url"]


def sweep():
    """[(meta, line, title line)] for every case of the sweep."""
    out = []
    for attr in EXTINF_ATTRS + HEADER_ATTRS:
        for form, url in FORMS.items():
            for cut in CUTS + ACCEPTED_CUTS:
                for quoted in (True, False):
                    for first in (True, False):
                        for comma in (True, False):
                            value = url.replace("{c}", cut)
                            if attr == "tvg-logo":
                                # https, the only scheme the logo survey names a host for.
                                value = "https" + value[len("http"):]
                            pair = "%s=%s" % (attr, '"%s"' % value if quoted else value)
                            sep = "," if comma else " "
                            if attr in HEADER_ATTRS:
                                head = "#EXTM3U " + (pair + ' tvg-shift="0"' if first else 'tvg-shift="0" ' + pair)
                                title = '#EXTINF:-1 tvg-chno="7"' + sep + "Plain Title"
                            else:
                                others = 'tvg-chno="7" tvg-shift="0"'
                                head = "#EXTINF:-1 " + (pair + " " + others if first else others + " " + pair)
                                head, title = head + sep + "Plain Title", None
                            meta = {"attr": attr, "form": form, "cut": cut, "quoted": quoted, "first": first,
                                    "comma": comma, "url": value, "accepted": cut in ACCEPTED_CUTS,
                                    "token": cut in ACCEPTED_CUTS and (form == "scheme"
                                                                       or (form in ("user", "pass") and cut != " "))}
                            out.append((meta, head, title))
    return out


def sweep_rows():
    """[(meta, document, row)] for the whole sweep, through parse_m3u."""
    rows = []
    for meta, line, title in sweep():
        doc, channel = parse_line(line, title) if title else parse_line(line)
        rows.append((meta, doc, channel))
    return rows


class SweepTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = sweep_rows()

    def own_value(self, meta, doc, channel):
        attr = meta["attr"]
        if attr in HEADER_ATTRS:
            return doc["epgUrlHint"]
        return {"group-title": channel["group"], "tvg-name": channel.get("tvgName"),
                "tvg-logo": channel.get("logo")}.get(attr)

    def test_the_sweep_is_whole(self):
        accepted = [m for m, _, _ in self.rows if m["accepted"]]
        self.assertEqual((len(self.rows), len(accepted)), (8680, 1400))

    def test_no_field_shows_a_credential_at_a_helper_sink(self):
        bad = []
        for meta, doc, channel in self.rows:
            if meta["accepted"]:
                continue
            for field, value in shown_fields(doc, channel):
                bad += [(meta, field, sink, out) for sink, out in helper_sinks(field, value) if leaked(out)]
            if leaked(channel["id"]):
                bad.append((meta, "id", channel["id"]))
        self.assertEqual(bad[:4], [])

    def test_each_url_value_is_stored_whole_and_redacts_to_its_host(self):
        # The other direction: stored, redacted, exactly the host; the
        # attribute after a URL value is read; and the title is the line's,
        # but where a bare URL value glued to the comma takes its first word
        # (a stated cost).
        bad = []
        for meta, doc, channel in self.rows:
            if meta["accepted"]:
                continue
            value = self.own_value(meta, doc, channel)
            glued = not meta["quoted"] and not meta["first"] and meta["comma"]
            if meta["attr"] in HEADER_ATTRS:
                want_name = "Plain Title"
            else:
                want_name = "Title" if glued else "Plain Title"
            if meta["attr"] in ("tvg-id", "catchup-source"):
                if "tvgId" in channel or channel["id"].startswith("t:"):
                    bad.append((meta, "tvg-id kept", channel["id"]))
            elif meta["attr"] in ["tvg-logo"] + HEADER_ATTRS and (not meta["quoted"] or '"' in meta["cut"]):
                if value:
                    bad.append((meta, "absorbed value kept", value))
            elif value is None or helper.redact_urls(value) != meta["url"].split("://")[0] + "://cdn.test" \
                    or not value.startswith(meta["url"]):
                bad.append((meta, "value", value))
            if channel["name"] != want_name or channel.get("chno") != "7":
                bad.append((meta, "row", channel["name"], channel.get("chno")))
        self.assertEqual(bad[:4], [])

    def test_the_accepted_class_is_the_redactors_own(self):
        # Excluded above, counted, and each one's URL as written already
        # prints a fragment through the redactor: D-SINK-34's cost, which no
        # grammar can close -- except the scheme form, whose credential after
        # the delimiter is a D-SINK-96 token every redactor withholds, so its
        # URL as written prints nothing of it (it printed all of it until
        # 2026-11-11; the next test holds its row at every sink); and, since
        # the review of cbd6679 read a credential across the URL in its token,
        # the user form with a delimiter but the space (`http://qq<TAB>qqqq:
        # zzzzzz@cdn.test/x`: the URL ends at the TAB, and the `:` after it
        # makes the token a credential, withheld whole); and, since the review
        # of 4d13d71, the pass form with a delimiter but the space
        # (`http://qqqqqq:zz<TAB>zzzz@cdn.test/x`: the URL ends at the TAB
        # before its `@`, so it holds the colon and not the `@`, and the
        # token is a credential withheld whole).
        tokens = 0
        for meta, _, _ in self.rows:
            if meta["accepted"]:
                tokens += meta["token"]
                self.assertEqual(bool(leaked(helper.redact_urls(meta["url"]))), not meta["token"], meta)
        self.assertEqual(tokens, 728)

    def test_d_sink_96_the_scheme_form_shows_no_credential_at_any_sink(self):
        # D-SINK-34's class, closed for the shape where the delimiter stands
        # right after `//`: whatever the grammar stores, no helper sink and
        # no shell sink shows a letter of the credential.
        kept = [(m, d, c) for m, d, c in self.rows if m["token"]]
        bad = []
        for meta, doc, channel in kept:
            for field, value in shown_fields(doc, channel):
                bad += [(meta, field, sink, out) for sink, out in helper_sinks(field, value) if leaked(out)]
            if leaked(channel["id"]):
                bad.append((meta, "id", channel["id"]))
        outs = shell_sinks([shell_row(d, c) for _, d, c in kept])
        bad += [(m, sink, out) for (m, _, _), row in zip(kept, outs) for sink, out in row if leaked(out)]
        self.assertEqual((len(kept), bad[:4]), (728, []))

    def test_no_field_shows_a_credential_at_a_shell_sink(self):
        kept = [(m, d, c) for m, d, c in self.rows if not m["accepted"]]
        outs = shell_sinks([shell_row(d, c) for _, d, c in kept])
        bad = [(m, sink, out) for (m, _, _), row in zip(kept, outs) for sink, out in row if leaked(out)]
        self.assertEqual(bad[:4], [])
        # And the hint the shell would fetch is never on the username: a
        # userinfo hint is refused, the rest name the provider's host.
        hints = [row for (m, _, _), row in zip(kept, outs) if m["attr"] in HEADER_ATTRS]
        self.assertEqual(len(hints), 2 * len(FORMS) * len(CUTS) * 8)


def deleted(text):
    """`text` without the controls both mirrors delete: C0, DEL and C1."""
    return "".join(c for c in text if not (ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f))


KEY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-")


def mark_end(text, i):
    """The end of a `://` that starts at `i` -- a `:`, then controls, a `/`,
    controls, a `/` -- or -1."""
    if text[i] != ":":
        return -1
    j = i + 1
    for _ in range(2):
        while j < len(text) and (ord(text[j]) < 0x20 or 0x7f <= ord(text[j]) <= 0x9f):
            j += 1
        if j >= len(text) or text[j] != "/":
            return -1
        j += 1
    return j


def host_follows(text, i, end):
    """Whether text[i:end] opens with a HOST, as the review of 4d13d71's lead
    call states one and the review of 2942e41's widens it: two or more
    labels whose last is letter-led and at least two characters, a dotted
    quad, or a bracketed IPv6 literal, each with an optional `:` and digits;
    or one letter-led label of two or more characters with a `:` and digits;
    a label of ASCII letters, digits, `-` and `_` or any non-ASCII
    character but whitespace, and one trailing dot allowed; then `end` (the
    token's end), a `/`, `?`, `#` or `,`, or whitespace."""
    name = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._"
    j = i
    single = False
    if j < end and text[j] == "[":
        k = j + 1
        while k < end and text[k] in "0123456789abcdefABCDEF:.":
            k += 1
        if k == j + 1 or k >= end or text[k] != "]":
            return False
        j = k + 1
    else:
        k = j
        while k < end and (text[k] in name or (ord(text[k]) > 0x7f and not text[k].isspace())):
            k += 1
        run = text[j:k]
        labels = (run[:-1] if run.endswith(".") else run).split(".")
        quad = len(labels) == 4 and all(0 < len(x) <= 3 and all(c in "0123456789" for c in x) for x in labels)
        named = len(labels) >= 2 and all(labels) and len(labels[-1]) >= 2 and labels[-1][0].isalpha()
        single = len(labels) == 1 and len(labels[0]) >= 2 and labels[0][0].isalpha()
        if not (quad or named or single):
            return False
        j = k
    if j < end and text[j] == ":" and j + 1 < end and text[j + 1] in "0123456789":
        k = j + 1
        while k < end and text[k] in "0123456789":
            k += 1
        j = k
    elif single:
        return False
    return j == end or text[j] in "/?#," or text[j].isspace()


def reference(text, trace):
    """parse_attrs as the rule states it, one character at a time, with no
    pattern: today's grammar, and inside a URL's run the run's own end."""
    attrs, pos, n = {}, 0, len(text)
    while pos < n:
        i = pos
        while i < n and text[i].isspace():
            i += 1
        k = i
        while i < n and text[i] in KEY_CHARS:
            i += 1
        if i == k or i >= n or text[i] != "=":
            break
        key, vs = text[k:i].lower(), i + 1
        if vs < n and text[vs] == '"':
            vs += 1
            q = text.find('"', vs)
            if q == -1:
                break
            s = max(vs, text.rfind(" ", vs, q) + 1)
            # D-SINK-95: or the redactors' reading finds a URL there.
            if "://" not in deleted(text[s:q]) and not rule.urls(text[s:q]):
                value, end = text[vs:q], q + 1
            else:
                e = n
                for j in range(q, n):
                    if text[j] in DELIMITERS:
                        e = j
                        break
                close = -1
                for j in range(q, e):
                    # ... or nothing but whitespace from it to the run's end
                    # (a non-ASCII space after the closing quote ends nothing).
                    if text[j] == '"' and (j + 1 == n or text[j + 1] in DELIMITERS or text[j + 1] == ","
                                           or (j + 1 < e and text[j + 1:e].isspace())):
                        close = j
                trace.append("quoted-unterminated" if close == -1 else "quoted-inside")
                if close == -1:
                    break
                value, end = text[vs:close], close + 1
        else:
            ve = vs
            while ve < n and not text[ve].isspace() and text[ve] not in ',"':
                ve += 1
            if ve == vs:
                break
            ends = [x for x in (mark_end(text, j) for j in range(vs, ve)) if x != -1]
            # D-SINK-95: or the reading finds a URL over the value and, when
            # FILLER ended it, the run of `:`, FILLER and SLASH after it.
            reach = ve
            if ve < n and rule.filler(text[ve]):
                while reach < n and (text[reach] == ":" or rule.filler(text[reach]) or rule.slash(text[reach])):
                    reach += 1
            url = rule.first_url(text[vs:reach])
            if url is not None:
                ends.append(vs + url[2])
            end = ve
            if ends:
                trace.append("bare-inside")
                end = n
                for j in range(max([ve] + ends), n):
                    if text[j] in DELIMITERS:
                        end = j
                        break
            # D-SINK-96 (the review of cbd6679): a value holding a `:` takes
            # the rest of its token's credential when the credential starts
            # before the value's end and its `@` stands at or after it.
            if ":" in text[vs:end]:
                ts = text.rfind(" ", 0, vs) + 1
                te = text.find(" ", end)
                te = n if te < 0 else te
                urls = rule.urls(text)
                found = rule.credential(text, ts, te, urls)
                # Across a `,`, only when a host follows an `@` it would take
                # (the review of 4d13d71; any such `@`, the review of
                # 2942e41); and across whitespace the same, when the
                # credential's colon is a URL's own (the review of 2942e41).
                if found is not None and found[1] >= end and found[2] < end:
                    we = found[2] + rule.trailing_keep(text[found[2]:te])
                    own = any(u[0] <= found[0] < u[3] for u in urls)
                    gated = text[end] == "," or (own and text[end].isspace())
                    if gated:
                        trace.append("bare-gated")
                    if we > end and (not gated or any(text[a] == "@" and host_follows(text, a + 1, te)
                                                      for a in range(end, we))):
                        trace.append("bare-credential")
                        end = we
            value = text[vs:end]
        value = value.strip()
        if value or key not in attrs:
            attrs[key] = value
        pos = end
    return attrs, text[pos:]


class RuleTest(unittest.TestCase):
    """parse_attrs against the rule as stated, over random lines built from
    the characters it reads."""

    # Value text: what ends a value today, what the rule reads (a `://`,
    # with a control inside it or not), the six delimiters, and whitespace
    # Python ends a bare value at and no redactor ends a URL at.
    ALPHABET = ["x", "Z", "=", '"', ",", " ", "\t", ":", "/", "://", "http://", ":\x01/\x00/", "@", "-",
                chr(0xa0), chr(0x3000), chr(0x85), chr(0x1c), "\x0b", "\r", "\x00", '",', '" ', "a=",
                "::", ":\x01", "\x9f/", "//", ":" + chr(0x85) + "//",
                # D-SINK-95: a STAND_IN, a look-alike slash and the marks they make.
                chr(0x200b), chr(0x2215), "http:" + chr(0x200b) + "//", "a" + chr(0xa0) + "://", ":" + chr(0x2215) * 2]
    # How an attribute starts: nothing, a space or other whitespace, then a
    # key (or something no key is) and `=`, quoted or bare.
    OPENERS = ["", " ", "\t", chr(0xa0), "  "]
    KEYS = ["a", "tvg-id", "K.b_c", "t" + chr(0xe9), "", "a "]
    # And how its value starts, a URL most of the time.
    STARTS = ["", "x", "http://", "http://", "a://", "x a://", ":\x01/\x00/", "http:" + chr(0x1c) + "//",
              "http:" + chr(0x200b) + "//", "http" + chr(0x7f) + "://", "http:" + chr(0x2215) * 2,
              # The review of cbd6679: a credential the value's end cuts.
              "qq:zz", "q:z\tz@", "http://q\tq:z"]

    def lines(self, seed, count):
        rng = random.Random(seed)
        for _ in range(count):
            if rng.random() < 0.2:
                yield "".join(rng.choice(self.ALPHABET) for _ in range(rng.randint(0, 24)))
                continue
            parts = []
            for _ in range(rng.randint(1, 4)):
                parts.append(rng.choice(self.OPENERS) + rng.choice(self.KEYS) + "=" + rng.choice(['"', '"', ""]))
                parts.append(rng.choice(self.STARTS))
                parts.extend(rng.choice(self.ALPHABET) for _ in range(rng.randint(0, 8)))
                parts.append(rng.choice(['"', '"', "", ","]))
            yield "".join(parts)

    def test_parse_attrs_is_the_rule(self):
        trace = []
        for text in self.lines(80, 40000):
            self.assertEqual(helper.parse_attrs(text), reference(text, trace), ascii(text))
        # Not vacuous: every branch of the rule was taken, often.
        counts = {b: trace.count(b) for b in ("quoted-inside", "quoted-unterminated", "bare-inside", "bare-credential")}
        self.assertTrue(counts["quoted-inside"] > 4000 and counts["bare-inside"] > 3000
                        and counts["quoted-unterminated"] > 1000 and counts["bare-credential"] > 300, counts)

    def test_the_reference_answers_the_fixture(self):
        # So the reference is the rule the fixture states, and not only the
        # code's: over a whole #EXTINF line, the duration and the title as
        # parse_extinf takes them, which the rule leaves alone.
        for c in CASES:
            line = c["line"]
            if line.startswith("#EXTM3U"):
                got = list(reference(line[len("#EXTM3U"):], []))
            else:
                body = line[len("#EXTINF:"):]
                body = body[re.match(r"\s*(-?\d+(?:\.\d+)?)?", body).end():]
                attrs, rest = reference(body, [])
                rest = rest.lstrip()
                got = [attrs, (rest[1:] if rest.startswith(",") else rest).strip()]
            self.assertEqual(got, [c["attrs"], c["title"]], c["why"])


class CredentialValueTest(unittest.TestCase):
    """The review of cbd6679 (its still-shows finding 4): a bare value ends at
    its first `,`, whitespace or `"`, so one cut inside a scheme-less
    credential stored the username and the password's head as the value
    and the rest as the title -- `group-title=qqqqqq:zz,zz@cdn.test,Name`
    listed the group `qqqqqq:zz` and named the row `zz@cdn.test,Name`,
    neither of which a redactor reads as a credential, so the group axis,
    the row, the bar and the notifications showed it. The value takes the
    credential's whole span now, as a URL takes its run (D-SINK-80): the
    title is swallowed and the name falls back. Red on cbd6679: every line
    below showed a letter of the credential at some sink."""

    LINES = ["#EXTINF:-1 group-title=qqqqqq:zz,zz@cdn.test,Name",
             "#EXTINF:-1 group-title=qqqqqq:zz\tzz@cdn.test,Name",
             '#EXTINF:-1 group-title=qqqqqq:zz"zz@cdn.test,Name',
             "#EXTINF:-1 tvg-name=qqqqqq:zz,zz@cdn.test,Name",
             "#EXTINF:-1 tvg-chno=7 group-title=http://qq\tqqqq:zzzzzz@cdn.test/x,Name"]

    def test_no_sink_shows_a_letter_of_the_credential(self):
        bad = []
        rows = [parse_line(line) for line in self.LINES]
        for line, (doc, channel) in zip(self.LINES, rows):
            for field, value in shown_fields(doc, channel):
                bad += [(line, field, sink, out) for sink, out in helper_sinks(field, value) if leaked(out)]
        outs = shell_sinks([shell_row(d, c) for d, c in rows])
        bad += [(line, sink, out) for line, row in zip(self.LINES, outs) for sink, out in row if leaked(out)]
        self.assertEqual(bad, [])

    def test_the_value_takes_the_credential_whole(self):
        _, channel = parse_line(self.LINES[0])
        self.assertEqual((channel["group"], channel["name"]), ("qqqqqq:zz,zz@cdn.test,Name", "Channel 1"))
        _, channel = parse_line(self.LINES[3])
        self.assertEqual(channel["name"], "qqqqqq:zz,zz@cdn.test,Name")
        # An ordinary bare value with a `:` and a title after it is read as
        # it always was, and so is one whose credential the comma does not
        # cut.
        _, channel = parse_line("#EXTINF:-1 group-title=UK:Sports,Name")
        self.assertEqual((channel["group"], channel["name"]), ("UK:Sports", "Name"))
        _, channel = parse_line("#EXTINF:-1 group-title=News,Sport:Live@HD")
        self.assertEqual((channel["group"], channel["name"]), ("News", "Sport:Live@HD"))
        # And a value whose `@` it holds already keeps its title: the
        # credential the value holds is withheld at its sinks.
        _, channel = parse_line("#EXTINF:-1 tvg-chno=7 group-title=a:b@c Name")
        self.assertEqual((channel["group"], channel["name"]), ("a:b@c", "Name"))


class HostShapedGrowthTest(unittest.TestCase):
    """The review of 4d13d71 (its changes-too-much finding 0): a bare value
    holding a `:` grew across the `,` that ended it to the end of its
    token's credential whenever an `@` followed, so an ordinary title whose
    first word held one was swallowed and the tvg-id before it dropped
    (`tvg-id=uk:bbc1,KC@BUF 20:15` stored no tvg-id and the name `20:15`),
    in 25 of 351 realistic names a form. Across a `,` the value grows only
    when a host follows the `@` it would take (host_shaped). Each benign
    line parses as a8e8174 parsed it, name and tvg-id; each credential is
    still taken whole. Red on 4d13d71 for the benign lines."""

    BENIGN = [("#EXTINF:-1 group-title=UK:News,Sky@News HD", "Sky@News HD", "UK:News", None),
              ("#EXTINF:-1 group-title=UK:Sports,NYY@BOS", "NYY@BOS", "UK:Sports", None),
              ("#EXTINF:-1 group-title=PPV:Events,UFC300@Vegas", "UFC300@Vegas", "PPV:Events", None),
              ("#EXTINF:-1 tvg-id=uk:bbc1,KC@BUF 20:15", "KC@BUF 20:15", helper.UNGROUPED, "uk:bbc1"),
              ("#EXTINF:-1 tvg-id=uk:bbc1,KC@BUF(20:15)", "KC@BUF(20:15)", helper.UNGROUPED, "uk:bbc1"),
              ("#EXTINF:-1 tvg-name=Live@8:30,Live@8:30", "Live@8:30", helper.UNGROUPED, None),
              ("#EXTINF:-1 catchup=default catchup-days=7 tvg-rec=3 timeshift=1:00,Q&A@10", "Q&A@10", helper.UNGROUPED, None)]

    def test_an_ordinary_title_after_a_value_holding_a_colon_keeps_its_name_and_tvg_id(self):
        got = [(parse_line(line)[1]["name"], parse_line(line)[1]["group"], parse_line(line)[1].get("tvgId"))
               for line, _, _, _ in self.BENIGN]
        self.assertEqual(got, [(name, group, tvg) for _, name, group, tvg in self.BENIGN])

    def test_a_credential_whose_at_a_host_follows_is_still_taken_whole(self):
        cases = [("#EXTINF:-1 group-title=qqqqqq:zz,zz@cdn.test,Name", "Channel 1", "qqqqqq:zz,zz@cdn.test,Name"),
                 ("#EXTINF:-1 group-title=qqqqqq:zz,zz@10.0.0.1:8080/x,Name", "Channel 1", "qqqqqq:zz,zz@10.0.0.1:8080/x,Name"),
                 ("#EXTINF:-1 group-title=qqqqqq:zz,zz@[::1]:8080,Name", "Channel 1", "qqqqqq:zz,zz@[::1]:8080,Name"),
                 ("#EXTINF:-1 group-title=qqqqqq:zz\tzz@News,Name", "Channel 1", "qqqqqq:zz\tzz@News,Name")]
        got = [(parse_line(line)[1]["name"], parse_line(line)[1]["group"]) for line, _, _ in cases]
        self.assertEqual(got, [(name, group) for _, name, group in cases])
        self.assertEqual([helper.host_shaped(t, 0, len(t)) for t in ("cdn.test", "News", "a.b", "1.2.3.4:80/x", "[::1]", "x.123",
                                                                    "KC@BUF", "8:30", "cdn.test(x")],
                         [True, False, False, True, True, False, False, False, False])

    def test_the_host_shapes_the_review_of_2942e41_named(self):
        # A single letter-led label with a port, a trailing dot, an underscore,
        # a non-ASCII label and a host whitespace ends are hosts; a bare
        # single label, a one-letter one with a port and a digit-led one with
        # a port are not (`Sky@News`, `Live@8:30` and `Breakfast@9:00` must
        # not grow).
        shapes = {"localhost:8080": True, "iptv:80": True, "cdn.test.": True, "cdn_test.com": True,
                  chr(0x43F) + chr(0x440) + chr(0x438) + chr(0x43C) + chr(0x435) + chr(0x440) + "." + chr(0x440) + chr(0x444): True,
                  "cdn.test\tx": True, "cdn.test" + chr(0xA0) + "x": True, "localhost.:80": True,
                  "localhost": False, "iptv": False, "localhost.": False, "x:80": False, "8:30": False, "9:00": False,
                  "localhost:": False, "localhost:80x": False, "cdn.1test": False, "1.2.3": False}
        self.assertEqual({t: helper.host_shaped(t, 0, len(t)) for t in shapes}, shapes)

    def test_a_credential_whose_host_the_review_of_2942e41_named_is_taken_whole(self):
        # Red on 2942e41: each stored the username and the password's head as
        # the group or the tvg-id, and every sink printed them.
        hosts = ["localhost:8080", "iptv:80", "cdn.test.", "cdn_test.com", "cdn.test\tx",
                 chr(0x43F) + chr(0x440) + chr(0x438) + chr(0x43C) + chr(0x435) + chr(0x440) + "." + chr(0x440) + chr(0x444)]
        lines = ["#EXTINF:-1 %s=qqqqqq:zz,zz@%s,Name" % (key, host) for key in ("group-title", "tvg-id") for host in hosts]
        # And a password holding an `@` is judged on every `@` the growth
        # would take, not on its own tail.
        lines.append("#EXTINF:-1 group-title=qqqqqq:zz,z@z@cdn.test,Name")
        rows = [parse_line(line) for line in lines]
        bad = []
        for line, (doc, channel) in zip(lines, rows):
            for field, value in shown_fields(doc, channel):
                bad += [(ascii(line), field, sink, out) for sink, out in helper_sinks(field, value) if leaked(out)]
            if leaked(channel["id"]) or "tvgId" in channel:
                bad.append((ascii(line), "id", channel["id"]))
        outs = shell_sinks([shell_row(d, c) for d, c in rows])
        bad += [(ascii(line), sink, out) for line, row in zip(lines, outs) for sink, out in row if leaked(out)]
        self.assertEqual(bad, [])

    def test_what_a_host_that_is_no_host_shape_leaves_stated(self):
        # The residual: a bare single label (or a digit-led last label, a
        # three-part number, a port with no digits or with text after them)
        # is no host, so the value is cut at the `,`: the username and the
        # password before it print in the group or the tvg-id, and the rest
        # of the password and the host in the name.
        _, channel = parse_line("#EXTINF:-1 group-title=qqqqqq:zz,zz@localhost,Name")
        self.assertEqual((channel["group"], channel["name"]), ("qqqqqq:zz", "zz@localhost,Name"))
        _, channel = parse_line("#EXTINF:-1 tvg-id=qqqqqq:zz,zz@iptv,Name")
        self.assertEqual((channel.get("tvgId"), channel["name"]), ("qqqqqq:zz", "zz@iptv,Name"))


class TabGrowthTest(unittest.TestCase):
    """The review of 2942e41 (its changes-too-much finding 2): a URL's own
    colon is a credential's when the URL's run ends before the `@` (the
    review of 4d13d71's eligibility), the run ends at a TAB, and a bare value
    grew across a TAB unconditionally, so a TAB-separated URL attribute took
    every attribute after it and the title's head whenever a word later in
    its U+0020 token held an `@`. Growth across whitespace from a URL's own
    colon is gated now as growth across a `,` is: only when a host follows
    an `@` it would take. Each line below reads as a8e8174 read it; red on
    2942e41. The stated cost is pinned in attr-grammar.json: a later word
    whose `@` a host follows still takes the URL attribute with it."""

    LINES = [("#EXTINF:-1 tvg-logo=http://logo.test/a.png\ttvg-name=Sky@News,Sky News",
              ("Sky News", helper.UNGROUPED, "http://logo.test/a.png", "Sky@News", None)),
             ("#EXTINF:-1 tvg-id=bbc1.uk\ttvg-logo=http://logo.test:8080/a.png\tgroup-title=News@UK,BBC One",
              ("BBC One", "News@UK", "http://logo.test:8080/a.png", None, "bbc1.uk")),
             ("#EXTINF:-1 tvg-logo=http://logo.test/a.png\tgroup-title=Sports,Live@8",
              ("Live@8", "Sports", "http://logo.test/a.png", None, None)),
             ("#EXTINF:-1 tvg-logo=http://logo.test:8080/a.png\tgroup-title=Sports,Breakfast@9:00",
              ("Breakfast@9:00", "Sports", "http://logo.test:8080/a.png", None, None))]

    def test_a_tab_separated_url_attribute_keeps_what_follows_it(self):
        got = [tuple(parse_line(line)[1].get(k) for k in ("name", "group", "logo", "tvgName", "tvgId")) for line, _ in self.LINES]
        self.assertEqual(got, [want for _, want in self.LINES])

    def test_a_password_a_tab_cuts_inside_a_url_is_still_taken_whole(self):
        # The review of 4d13d71's pins: the URL's colon, the TAB (or VT, FF,
        # CR) and the `@` a host follows.
        for sep in "\t\x0b\x0c\r":
            _, channel = parse_line("#EXTINF:-1 group-title=http://qqqqqq:zz%szz@cdn.test/x,Name" % sep)
            self.assertEqual((channel["group"], channel["name"]), ("http://qqqqqq:zz%szz@cdn.test/x,Name" % sep, "Channel 1"))
        _, channel = parse_line("#EXTINF:-1 tvg-name=http://qqqqqq:zz\tzz@cdn.test/x,")
        self.assertEqual((channel["name"], channel.get("tvgName")), ("http://qqqqqq:zz\tzz@cdn.test/x", None))


class TabInPasswordValueTest(unittest.TestCase):
    """The review of 4d13d71 (its still-shows finding 1): a TAB in the
    password of a bare URL value ended the URL's run before its `@`, so
    `group-title=http://qqqqqq:zz<TAB>zz@cdn.test/x,Name` stored the group
    `http://qqqqqq:zz`, which every sink printed as `qqqqqq`, and named the
    row `zz@cdn.test/x,Name`; `tvg-name=` stored `http://qqqqqq:zz` the
    same way. The URL holds the colon and not the `@` now, so the token is
    a credential and the value takes it whole. Red on 4d13d71."""

    LINES = ["#EXTINF:-1 group-title=http://qqqqqq:zz\tzz@cdn.test/x,Name",
             "#EXTINF:-1 tvg-name=http://qqqqqq:zz\tzz@cdn.test/x,"]

    def test_no_sink_shows_a_letter_of_the_credential(self):
        rows = [parse_line(line) for line in self.LINES]
        self.assertEqual([(c["name"], c["group"], c.get("tvgName")) for _, c in rows],
                         [("Channel 1", "http://qqqqqq:zz\tzz@cdn.test/x,Name", None),
                          ("http://qqqqqq:zz\tzz@cdn.test/x", helper.UNGROUPED, None)])
        bad = []
        for line, (doc, channel) in zip(self.LINES, rows):
            for field, value in shown_fields(doc, channel):
                bad += [(line, field, sink, out) for sink, out in helper_sinks(field, value) if leaked(out)]
        outs = shell_sinks([shell_row(d, c) for d, c in rows])
        bad += [(line, sink, out) for line, row in zip(self.LINES, outs) for sink, out in row if leaked(out)]
        self.assertEqual(bad, [])


class TvgIdTest(unittest.TestCase):
    def row(self, line):
        return parse_line(line)[1]

    def test_a_tvg_id_holding_a_url_is_dropped(self):
        for line in ('#EXTINF:-1 tvg-id="http://qqqqqq:zzzzzz@cdn.test/x",Plain Title',
                     '#EXTINF:-1 tvg-id="http://qqqqqq:zz"zzzz@cdn.test/x",Plain Title',
                     '#EXTINF:-1 tvg-id=http://qqqqqq:zz,zz@cdn.test/x,Plain Title',
                     '#EXTINF:-1 tvg-id="rtmp://cdn.test/live/qqqqqq/zzzzzz",Plain Title',
                     '#EXTINF:-1 tvg-id="http:\x01//qqqqqq:zzzzzz@cdn.test/x",Plain Title',
                     '#EXTINF:-1 tvg-id="news.us http:/\x9f/qqqqqq:zzzzzz@cdn.test/x",Plain Title'):
            channel = self.row(line)
            self.assertNotIn("tvgId", channel, ascii(line))
            self.assertFalse(channel["id"].startswith("t:"), ascii(line))
            self.assertEqual(leaked(channel["id"]), [], ascii(line))

    def test_d_sink_95_and_96_a_tvg_id_holding_a_broken_mark_or_a_token_is_dropped(self):
        # A mark the redactors' reading finds behind a scheme (url_mark_any),
        # or a `:` with an `@` after it: kept, the raw `t:` id would carry the
        # credential to every sink that shows an id, none of which redacts one.
        for tvg in ("qqqqqq:zzzzzz@cdn.test", "http:" + chr(0x200B) + "//qqqqqq:zzzzzz@cdn.test/x",
                    "http" + chr(0xFF1A) + "//cdn.test/live/qqqqqq/zzzzzz/1.ts", "x:" + chr(0x2215) * 2 + "qqqqqq/zzzzzz"):
            channel = self.row('#EXTINF:-1 tvg-id="%s",Plain Title' % tvg)
            self.assertNotIn("tvgId", channel, ascii(tvg))
            self.assertEqual(leaked(channel["id"]), [], ascii(tvg))

    def test_a_tvg_id_with_an_at_sign_or_a_colon_but_no_url_is_kept(self):
        for tvg in ("CNN.us@HD", "news:sports", "a:/b", "a//b", "bbc.uk@SD:1"):
            channel = self.row('#EXTINF:-1 tvg-id="%s",Plain Title' % tvg)
            self.assertEqual((channel.get("tvgId"), channel["id"]), (tvg, "t:" + tvg))

    def test_a_dropped_tvg_id_is_not_the_name_either(self):
        # With no title and no tvg-name the name falls back past it.
        channel = self.row('#EXTINF:-1 tvg-id="http://cdn.test/x",')
        self.assertEqual((channel["name"], "tvgId" in channel), ("Channel 1", False))

    def test_a_row_with_a_dropped_tvg_id_joins_no_guide(self):
        doc = helper.parse_m3u("#EXTM3U\n" + '#EXTINF:-1 tvg-id="http://cdn.test/x",A\n' + STREAM + "\n"
                               + '#EXTINF:-1 tvg-id="a.us",B\n' + STREAM.replace("1.ts", "2.ts") + "\n")
        alias, total = helper.build_alias(doc)
        self.assertEqual((total, sorted(alias["exact"])), (2, ["a.us"]))


class LinearTest(unittest.TestCase):
    """parse_attrs runs once a line on text no cap bounds first, so its URL
    rule may not search back from each quote or each colon: four times the
    text may cost at most eight times the time plus 2 ms, best of five, in
    this thread's CPU time."""

    SHAPES = [lambda n: 'a="http://x"' * (n // 12),
              lambda n: 'a="http://x' + '"y' * (n // 2),
              lambda n: "a=x:y " * (n // 6),
              lambda n: 'a="http://x"' + "," * n,
              lambda n: 'a="http://x' + '"' * n,
              lambda n: 'a="http://x" ' * (n // 13),
              lambda n: "a=" + ":" * n,
              lambda n: "a=" + ":\x00" * (n // 2),
              lambda n: 'a="' + " " * n + '"',
              lambda n: ('a="http://x' + "y" * 50 + '" ') * (n // 64),
              lambda n: "a=x:\t//y " * (n // 10),
              lambda n: 'a="x:"' * (n // 6),
              lambda n: 'a="http://x' + '",' * (n // 2) + "y",
              lambda n: "a=:" + "\x00" * n + " b=c",
              # The review of 4d13d71: a bare value holding a `:` asked its
              # token's credential over a URL reading of its own, which read
              # on to the line's end, so a line of them before an `@` was
              # quadratic (ratio 8.4 and 16.7 on 4d13d71; 42.8 s on a
              # 96,000-character #EXTINF line). One reading a line now.
              lambda n: "a=x:y " * (n // 6) + "@",
              lambda n: "a=x:y " * (n // 6) + "@" + chr(0xE9)]

    def best(self, text):
        times = []
        for _ in range(5):
            t0 = time.thread_time()
            helper.parse_attrs(text)
            times.append(time.thread_time() - t0)
        return min(times)

    # The review of 2942e41 (its cost finding 1): a bare value's U+0020
    # token bounds were searched for once a value, so values a TAB separates,
    # one token, read the whole line each: quadratic (12.6 s for
    # `a=x:@<TAB>` repeated to 1.6M characters, 33.9 s with two Han before
    # each TAB). They are found once a token now. At 8,000 and 32,000
    # characters the line's own linear work hides the square (a ratio of 5.2
    # and 6.2 on 2942e41), so these are held at 100,000 and 400,000, where
    # 2942e41 gives 11.9 and 13.2.
    LONG_SHAPES = [lambda n: "a=x:@\t" * (n // 6),
                   lambda n: ("a=x:" + chr(0x65E5) + chr(0x672C) + "\t") * (n // 7) + "@"]

    def test_parse_attrs_is_linear_on_every_shape(self):
        for shape in self.SHAPES:
            small, large = self.best(shape(8000)), self.best(shape(32000))
            self.assertLess(large, 8 * small + 0.002, ascii(shape(16)[:16]))

    def test_parse_attrs_is_linear_when_tabs_separate_the_values(self):
        for shape in self.LONG_SHAPES:
            small, large = self.best(shape(100000)), self.best(shape(400000))
            self.assertLess(large, 8 * small + 0.002, ascii(shape(16)[:16]))


if __name__ == "__main__":
    unittest.main()
