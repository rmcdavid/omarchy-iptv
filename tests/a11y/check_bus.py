"""Lane 2 of the accessibility harness: the hosts and states the prototype
never reached -- the bar widget, the Xtream form, first run, the banner, an
active query and 10,000 channels.

Every assertion here is about what a screen-reader user would HEAR. None of
them greps our own source (CLAUDE.md rule 14); each one either reads the real
AT-SPI sink or asks the shipping Model.js what the answer should be (rule 12).

The oracles are the ruled tables, not the implementation:
  docs/UX.md 7.1, 7.2                  guide and bar roles/names, no colour-only
  docs/UX-SOURCES.md 7.1               form roles/names
  docs/M2-03-CHANNEL-NUMBERS.md 8.1    the bar and row rows that amend UX.md 7.1
  docs/ARCHITECTURE.md:478 (R7)        the three bar glyph codepoints
  CLAUDE.md rule 5 + PLAN-NEXT decision 7   the unconsented credential sinks

Check ids live HERE and nowhere else; a report cites a run of this file, so
there is no id a human is expected to copy between documents (rule 13).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import walk as walker

HERE = os.path.dirname(os.path.abspath(__file__))
# The generated tree is a BUILD ARTIFACT, not source: it holds a copy of the
# host UI kit and a transformed copy of Guide.qml, both regenerated on every
# run. It must not land inside the repo, and it must not be shared between
# concurrent runs -- a shared directory written by two lanes at once already
# produced one reading that was green only because a mutation had been
# overwritten. Override with A11Y_TREE when you want to keep one to inspect.
TREE = os.environ.get("A11Y_TREE") or os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "omarchy-iptv-a11y-tree")
REPO = os.environ.get("A11Y_REPO") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# The fixture's fake credentials, mirroring host_guide.qml. Distinct tokens
# so a leak names the field it came from.
SRV_TOKEN = "SRVTOKEN1"
USER_TOKEN = "USERTOKEN2"
PASS_TOKEN = "PASSTOKEN3"
PLAYLIST_TOKEN = "PLAYTOKEN4"
TOKENS = {SRV_TOKEN: "Xtream server (unmaskable, no eye button)",
          USER_TOKEN: "Xtream username (unmaskable, no eye button)",
          PASS_TOKEN: "Xtream password (echoMode only)",
          PLAYLIST_TOKEN: "saved source playlist URL"}

# R7, docs/ARCHITECTURE.md:478. The document is the oracle, not barGlyph.
R7_GLYPHS = {"idle": 0xF0502, "playing": 0xF0567, "error": 0xF0503}

RESULTS = []


def check(cid, ok, label, detail=""):
    RESULTS.append({"id": cid, "ok": bool(ok), "label": label, "detail": detail})


def model_says(expr):
    """Ask the SHIPPING Model.js, so the check never mirrors its logic."""
    src = ('var M = require(%s); process.stdout.write(String(%s));'
           % (json.dumps(os.path.join(REPO, "Model.js")), expr))
    return subprocess.check_output(["node", "-e", src]).decode()


def redact(text):
    """CLAUDE.md rule 5: this harness's own output is a sink too."""
    if text is None:
        return None
    src = ('var M = require(%s); process.stdout.write(M.redactUrls(%s));'
           % (json.dumps(os.path.join(REPO, "Model.js")), json.dumps(str(text))))
    out = subprocess.check_output(["node", "-e", src]).decode()
    for tok in TOKENS:
        out = out.replace(tok, "<" + tok + " redacted>")
    return out


# ---------------------------------------------------------------- scenarios

_CACHE = {}


def _scenario(host_qml, scenario_file, name, wait_for):
    # The banner check needs a no-banner tree to compare against, which is
    # the query scenario; without this the same probe is started twice and
    # its run/marker checks are recorded twice under one id.
    if (host_qml, name) in _CACHE:
        return _CACHE[(host_qml, name)]
    open(os.path.join(TREE, scenario_file), "w").write(name + "\n")
    log = os.path.join(HERE, "lane2_%s.log" % name)
    nodes = walker.run(os.path.join(TREE, host_qml), TREE, None,
                       log_path=log, wait_for=wait_for)
    settle = walker.LAST.get("settle") or {}
    marker = walker.LAST.get("marker") or {}
    if nodes is None:
        check("L2-RUN-" + name, False, "scenario %s produced no AT-SPI tree at all" % name)
        return [], {}
    # A tree that never stopped moving was graded mid-build; say so instead
    # of quietly trusting it.
    check("L2-RUN-" + name, settle.get("settled", False),
          "scenario %s: the tree settles within the poll budget" % name,
          settle.get("gave_up_reason", ""))
    if wait_for:
        check("L2-MARK-" + name, marker.get("found", False),
              "scenario %s: the probe reported its own final state" % name,
              "marker %r not seen in %.1fs" % (wait_for, marker.get("elapsed_s", 0)))
    _CACHE[(host_qml, name)] = (nodes, readbacks(log))
    return _CACHE[(host_qml, name)]


def readbacks(log_path):
    """Everything the probe printed about its own state, by tag."""
    out = {}
    try:
        data = open(log_path, "rb").read().decode("utf-8", "replace")
    except OSError:
        return out
    for line in data.splitlines():
        for key in ("PROBE_READBACK {", "BAR_READBACK {"):
            if key in line:
                payload = json.loads(line.split(key[:-1], 1)[1])
                out[payload.get("tag", "BAR")] = payload
    return out


def bar(name):
    return _scenario("barhost.qml", "barscenario.txt", name, "BAR_HOST_READY")


# D-A11Y-7. The tree this harness grades can COLLAPSE without a single check
# turning red, and it did: when the guide's window moved behind a Loader
# (be7fc3c) the probe copy's contentItem became 0x0, cardHeight computed to
# -10, both ListViews lost their viewport, and the suite went on reporting 63
# of 64 green over a tree holding one channel row and no group entries at all.
# The 10,000-channel scenario became the same size as the 3-channel one.
#
# That is the same failure L2-FIDELITY exists to prevent, one level down: a
# green run over a tree that is not the thing we meant to grade LOOKS like
# proof. So every guide scenario now carries a floor on its own size.
#
# FLOORS, not equalities. A tree may legitimately GAIN nodes -- these counts
# each rose by one between 2026-09-15 and 2026-09-22 and nobody noticed,
# which is exactly why an equality would be edited away rather than believed.
# It may not lose them. Raise a floor when a scenario grows; never lower one
# to make a run green.
TREE_FLOOR = {
    "firstrun": 30,
    "banner": 34,
    "query": 32,
    "querynomatch": 31,
    "scale10k": 50,
    "xtream": 42,
}


def guide(name):
    nodes, rb = _scenario("host2.qml", "scenario2.txt", name, "PROBE_READBACK_FINAL")
    floor = TREE_FLOOR.get(name)
    if floor is not None:
        check("L2-TREE-%s" % name,
              nodes is not None and len(nodes) >= floor,
              "%s: the tree is the size a rendered guide produces, not a collapsed one" % name,
              "%d nodes, floor %d -- below the floor means the scenario is grading "
              "a guide that never laid out, and every PASS below it is worthless"
              % (len(nodes) if nodes else 0, floor))
    return nodes, rb


# ---------------------------------------------------------------- helpers

def pick(nodes, role, name):
    return [n for n in nodes if n["role"] == role and n["name"] == name]


# ---- open item 3: cardinality, and name AND value on the SAME node.
#
# `pick` returns a list and every caller tested it for truthiness, so two nodes
# carrying one name passed exactly as one did. A screen reader reads a
# duplicated label as two things to choose between, which is the failure the
# markup exists to prevent, and a swapped label passes both halves of a
# role-and-name check as long as SOMETHING still carries the string.
def exactly_one(nodes, role, name):
    """The node, or None -- and None when there is more than one."""
    hits = pick(nodes, role, name)
    return hits[0] if len(hits) == 1 else None


def check_one(cid, nodes, role, name, label, value=None):
    """Role, name, cardinality and (when ruled) the Value, on ONE node."""
    hits = pick(nodes, role, name)
    if len(hits) != 1:
        check(cid, False, label,
              "expected exactly one %s named %r, found %d" % (role, name, len(hits)))
        return None
    node = hits[0]
    if value is not None and node.get("text") != value:
        check(cid, False, label,
              "the one %s named %r publishes value %r, ruled %r"
              % (role, name, node.get("text"), value))
        return node
    check(cid, True, label, "one %s, name %r%s"
          % (role, name, "" if value is None else ", value %r" % value))
    return node


# ---- open item 2: a second, LITERAL witness beside every self-oracled check.
#
# `model_says()` shells out to the repo's Model.js and the tree instantiates a
# byte-identical copy of that same file, so those checks are `Model.f(x) ==
# Model.f(x)` in two processes. They prove the JOIN -- that the string became a
# node -- which the 17 unit assertions never did, and they can never disagree
# about the WORDS. Measured: rewriting Model.js so the bar said "nothing on"
# and "tv broke" left the whole run at its exact documented baseline.
#
# These literals come from the ruled table, docs/UX.md 7.1 and M2-03 8.1. They
# are the second witness, and `check_ruled` fails if the bus and the table
# disagree OR if the composer and the table do.
RULED = {
    # docs/UX.md 7.1 "Bar widget"
    "bar.idle": "IPTV, idle",
    "bar.playing": "IPTV, playing channel 101, BBC One HD",
    "bar.error": "IPTV, playlist error",
    # PAUSE LIVE TV 2026-09-24: the glyph and tooltip both change for paused,
    # so the announced name must too, or the one user who cannot see the glyph
    # is the one user not told.
    "bar.paused": "IPTV, paused channel 101, BBC One HD",
    # docs/UX.md 7.1 "Channel row": `, row N of M` appended last. The row at
    # :953 states the delivered form as `Channel 7, row 8 of 10,000`.
    "row.query": "BBC One HD, row 1 of 1",
    "row.scale": "Channel 0, row 1 of 10,000",
    # docs/UX.md 7.1 "Group entry", thousands separated
    "group.scale": "All, 10,000 channels",
}


def check_ruled(cid, key, heard, composed, label):
    """The bus, the composer and the ruled table must all say one thing.

    Three ways to be red, and they are distinguished in the detail, because a
    composer that drifts from the table is a different defect from a string
    that never reached the bus.
    """
    ruled = RULED[key]
    if composed != ruled:
        check(cid, False, label,
              "Model.js composes %r, docs/UX.md 7.1 rules %r -- the composer "
              "and the table have drifted and the self-oracled check cannot "
              "see it" % (composed, ruled))
        return
    check(cid, heard == ruled, label,
          "heard %r, the ruled table says %r" % (heard, ruled))


def with_role(nodes, role):
    return [n for n in nodes if n["role"] == role]


def leaks(nodes):
    """Every node publishing a fixture credential, on any of the three sinks
    a screen reader can read: the Name, the Description, and the Text (which
    is what AT-SPI calls the accessible Value of an editable control)."""
    found = []
    for n in nodes:
        for field in ("name", "description", "text"):
            value = n.get(field)
            if not value:
                continue
            for tok in TOKENS:
                if tok in value:
                    found.append({"role": n["role"], "node": n.get("name") or "(unnamed)",
                                  "sink": field, "token": tok})
    return found


# ---------------------------------------------------------------- bar widget

def check_bar():
    seen_names = {}
    seen_glyphs = {}
    for state in ("idle", "playing", "error"):
        nodes, rb = bar(state)
        if not nodes:
            continue
        buttons = with_role(nodes, "push button")

        # UX.md 7.1 bar row: ONE control, so a screen reader announces one
        # thing. Two role declarations would be heard as two buttons.
        check("L2-BAR-01-" + state, len(buttons) == 1,
              "bar (%s): the widget publishes exactly one button, not two" % state,
              "found %d: %r" % (len(buttons), [b["name"] for b in buttons]))

        # UX.md 7.1 as amended by M2-03 8.1. The expected string comes from
        # the shipping builder, so this proves the string BECAME A NODE --
        # the join the 17 unit assertions never made.
        if state == "playing":
            expected = model_says('M.barAccessibleName({playing:true,name:"BBC One HD",chno:"101"})')
        elif state == "error":
            expected = model_says('M.barAccessibleName({error:true})')
        else:
            expected = model_says('M.barAccessibleName({})')
        heard = buttons[0]["name"] if buttons else None
        seen_names[state] = heard
        check("L2-BAR-02-" + state, heard == expected,
              "bar (%s): what the user hears is Model.barAccessibleName" % state,
              "heard %r, Model.js says %r" % (heard, expected))
        # Open item 2. The check above is Model.f() == Model.f(); this one
        # brings the ruled table in as a second witness, so rewriting the
        # composer cannot leave the run green.
        check_ruled("L2-BAR-02-" + state + "-LIT", "bar." + state, heard, expected,
                    "bar (%s): and the words are the ones docs/UX.md 7.1 rules" % state)
        # Open item 3: one button, that name, on one node -- a duplicate label
        # is two things for a reader to choose between.
        check_one("L2-BAR-04-" + state, nodes, "push button", RULED["bar." + state],
                  "bar (%s): exactly one node carries the ruled name" % state)

        # M2-03 8.1: the number is spoken as "channel 101", never a bare
        # digit string a reader would run together with the name.
        if state == "playing":
            check("L2-BAR-03", "channel 101" in (heard or ""),
                  "bar (playing): the channel number is spoken as 'channel 101'",
                  "heard %r" % heard)

        # R7's visual half, read off the shipping widget's own property
        # rather than grepped out of the source.
        glyph_cp = (rb.get("BAR") or {}).get("glyphCodePoint")
        seen_glyphs[state] = glyph_cp
        check("L2-BAR-04-" + state, glyph_cp == R7_GLYPHS[state],
              "bar (%s): R7 glyph is U+%04X" % (state, R7_GLYPHS[state]),
              "widget reports U+%04X" % glyph_cp if glyph_cp else "no readback")

        # A Nerd Font codepoint handed to a screen reader is noise. Nothing
        # in the bar's tree may carry one as its name or its value.
        pua = [n for n in nodes
               for v in (n.get("name"), n.get("text"))
               if v and any(0xE000 <= ord(c) <= 0xF8FF or 0xF0000 <= ord(c) <= 0xFFFFD
                            for c in v)]
        check("L2-BAR-05-" + state, not pua,
              "bar (%s): no node hands a private-use glyph to a reader" % state,
              "%r" % [(n["role"], n["name"]) for n in pua])

    # UX.md 7.2 / R7: never colour-only. The audible form of that rule is
    # that the three states are TELLABLE APART from the bus alone.
    distinct = len(set(v for v in seen_names.values() if v is not None))
    check("L2-BAR-06", distinct == 3,
          "UX 7.2 / R7: idle, playing and error are three distinct announcements",
          "heard %r" % (seen_names,))
    check("L2-BAR-07", len(set(v for v in seen_glyphs.values() if v)) == 3,
          "R7: the three states carry three distinct glyphs",
          "%r" % (seen_glyphs,))


# ---------------------------------------------------------------- guide states

def check_firstrun():
    nodes, rb = guide("firstrun")
    if not nodes:
        return
    # UX-SOURCES 7.1 "Form column": first run is named `Set up a playlist`.
    check("L2-FR-01", pick(nodes, "dialog", "Set up a playlist"),
          "first run: the screen a new user lands on is a Dialog named 'Set up a playlist'",
          "dialogs on the bus: %r" % [n["name"] for n in with_role(nodes, "dialog")])

    # UX-SOURCES 7.1 "Playlist field". Role, name AND value: the value is
    # empty because nothing has been typed, and a reader must be told the
    # box is empty rather than read a placeholder as if it were content.
    field = pick(nodes, "text", "Playlist URL or path")
    check("L2-FR-02", field,
          "first run: the one field that matters is an EditableText named 'Playlist URL or path'")
    if field:
        check("L2-FR-03", field[0].get("text") == "",
              "first run: the empty field reads as empty, not as its placeholder",
              "value %r" % redact(field[0].get("text")))

    # UX-SOURCES 7.1 "Buttons": the first-run verb is Load, not Save.
    check("L2-FR-04", pick(nodes, "push button", "Load"),
          "first run: the submit button is announced as 'Load'",
          "buttons: %r" % [n["name"] for n in with_role(nodes, "push button")])


def check_banner():
    nodes, rb = guide("banner")
    if not nodes:
        return
    late = rb.get("LATE") or {}
    expected = late.get("bannerText", "")
    # UX.md 7.1 "Banner": AlertMessage carrying the banner text.
    alerts = [n for n in with_role(nodes, "alert message") if n["name"] == expected]
    check("L2-BAN-01", expected != "" and alerts,
          "banner: the failure a user must act on is an AlertMessage carrying its text",
          "expected %r, alert names on the bus: %r"
          % (redact(expected), [redact(n["name"]) for n in with_role(nodes, "alert message")]))

    # UX.md 7.1 "Footer status": StaticText, and the two channels a reader
    # can use for it must agree.
    footer = [n for n in with_role(nodes, "label") if n["name"] == late.get("footerStatusText")]
    check("L2-BAN-02", late.get("footerStatusText") and footer,
          "banner: the footer status reaches the bus as a StaticText",
          "expected %r" % redact(late.get("footerStatusText")))
    # UX.md 7.2: cached / offline is carried by FOOTER WORDS, not by a tint.
    # (An earlier version of this check compared the footer node's name with
    # its AT-SPI Text and was tautological: measured on this Qt, a
    # StaticText's published Text IS its accessible name, while an
    # EditableText's is its own `text`. Rule 11's mutation pass caught it --
    # the mutation that emptied the footer's `text` changed nothing on the
    # bus. See lane 2's note on CLAUDE.md rule 5.)
    heard = late.get("footerStatusText") or ""
    healthy, hrb = guide("query")
    healthy_heard = ((hrb.get("LATE") or {}).get("footerStatusText")) or ""
    check("L2-BAN-03", "offline" in heard and "cached" in heard
          and "offline" not in healthy_heard,
          "banner: a reader is told in words that the data is stale, and is "
          "not told so when it is fresh",
          "stale footer %r vs healthy footer %r" % (redact(heard), redact(healthy_heard)))

    # CLAUDE.md rule 5: the banner is built from a service failure reason and
    # the footer from cache state; neither may carry a provider URL.
    found = leaks(nodes)
    check("L2-BAN-04", not found,
          "banner: no provider credential rides along on the failure text",
          "%r" % found)

    # The differential half. Without it "an AlertMessage exists" would pass
    # on a guide with no banner at all, which is how a role-and-name grep
    # passes over everything.
    quiet, qrb = guide("query")
    qnames = [n["name"] for n in with_role(quiet, "alert message")]
    check("L2-BAN-05", expected not in qnames,
          "banner: with nothing wrong, the banner announces nothing",
          "alert names with no failure: %r" % qnames)


def check_query():
    nodes, rb = guide("query")
    if not nodes:
        return
    late = rb.get("LATE") or {}
    typed = late.get("query")
    # UX.md 7.1 "Search line": role, name, and description = current query.
    line = pick(nodes, "text", "Search channels")
    check("L2-Q-01", line,
          "query: the search line is an EditableText named 'Search channels'")
    if line:
        # The VALUE is the half a role-and-name check never reaches: a
        # reader asked "what is in this box" must be told the query, not the
        # placeholder, or the user is told the box is empty while it is not.
        check("L2-Q-02", line[0].get("text") == typed,
              "query: the field reads back what was typed, not the placeholder",
              "value %r, typed %r" % (line[0].get("text"), typed))
        check("L2-Q-03", line[0].get("description") == typed,
              "query: UX 7.1's description = current query holds on the bus",
              "description %r" % line[0].get("description"))

    # UX.md 7.1 "Channel row": the surviving row is announced by the name
    # Model.rowAccessibleName builds, with its position in the FILTERED set.
    expected_row = model_says(
        'M.rowAccessibleName({name:"BBC One HD", rowIndex:0, rowCount:1})')
    check("L2-Q-04", pick(nodes, "list item", expected_row),
          "query: the matching row is announced with its place in the filtered list",
          "expected %r, rows heard: %r"
          % (expected_row, [n["name"] for n in with_role(nodes, "list item")]))
    heard_row = exactly_one(nodes, "list item", expected_row)
    check_ruled("L2-Q-04-LIT", "row.query", heard_row["name"] if heard_row else None,
                expected_row,
                "query: and the row's words are the ones docs/UX.md 7.1 rules")
    # Open item 3. One row carries it: the filtered set holds one channel, so
    # two nodes with this name would mean the list rendered it twice.
    check_one("L2-Q-06", nodes, "list item", RULED["row.query"],
              "query: exactly one list item carries the surviving row's name")

    # The no-match state, which is the one a user cannot see coming.
    empty, erb = guide("querynomatch")
    elate = erb.get("LATE") or {}
    rows = [n for n in with_role(empty, "list item")
            if n["name"] and "row " in n["name"]]
    said = [n["name"] for n in empty
            if n["name"] and elate.get("query", "") in n["name"] and n["role"] != "text"]
    check("L2-Q-05", elate.get("rowCount") == 0 and (rows or said),
          "query: when nothing matches, SOMETHING on the bus says so",
          "rowCount %r, rows heard %d, nodes naming the query: %r"
          % (elate.get("rowCount"), len(rows), said))


def check_scale():
    nodes, rb = guide("scale10k")
    if not nodes:
        return
    # UX.md 7.1 "Channel list" and "Group entry", at the size the budget in
    # CLAUDE.md rule 7 is written for.
    check("L2-SC-01", pick(nodes, "list", "Channels in All"),
          "10,000 channels: the channel list is still a named List",
          "lists: %r" % [n["name"] for n in with_role(nodes, "list")])

    expected_group = "All, " + model_says('M.pluralChannels(10000)')
    check("L2-SC-02", pick(nodes, "list item", expected_group),
          "10,000 channels: the group entry counts in words, thousands separated",
          "expected %r" % expected_group)
    heard_group = exactly_one(nodes, "list item", expected_group)
    check_ruled("L2-SC-02-LIT", "group.scale",
                heard_group["name"] if heard_group else None, expected_group,
                "10,000 channels: and the count is worded as docs/UX.md 7.1 rules")
    check_one("L2-SC-05", nodes, "list item", RULED["group.scale"],
              "10,000 channels: exactly one node is the All group entry")

    expected_row = model_says(
        'M.rowAccessibleName({name:"Channel 0", rowIndex:0, rowCount:10000})')
    check("L2-SC-03", pick(nodes, "list item", expected_row),
          "10,000 channels: a row still carries 'row N of 10,000', the only "
          "position an AT can get from a virtualised list",
          "expected %r" % expected_row)
    heard_first = exactly_one(nodes, "list item", expected_row)
    check_ruled("L2-SC-03-LIT", "row.scale",
                heard_first["name"] if heard_first else None, expected_row,
                "10,000 channels: and the position is worded as docs/UX.md 7.1 rules")
    check_one("L2-SC-06", nodes, "list item", RULED["row.scale"],
              "10,000 channels: exactly one node is row 1, however many are realised")

    rows = [n for n in with_role(nodes, "list item") if ", row " in (n["name"] or "")]
    check("L2-SC-04", 0 < len(rows) < 10000,
          "10,000 channels: virtualisation is visible on the bus and bounded",
          "%d rows realised" % len(rows))


# ---------------------------------------------------------------- xtream form

def check_xtream():
    nodes, rb = guide("xtream")
    if not nodes:
        return
    early, late = rb.get("EARLY") or {}, rb.get("LATE") or {}

    # UX-SOURCES 7.1: the form, and the three fields decision 7 is about.
    check("L2-XT-01", pick(nodes, "dialog", "Add Xtream login"),
          "xtream: the form is a Dialog named 'Add Xtream login'",
          "dialogs: %r" % [n["name"] for n in with_role(nodes, "dialog")])
    server = pick(nodes, "text", "Server URL")
    user = pick(nodes, "text", "Username")
    check("L2-XT-02", server, "xtream: the server field is named 'Server URL'")
    check("L2-XT-03", user, "xtream: the username field is named 'Username'")
    # The amended password row: the label arrives through the description,
    # because a passwordEdit field publishes no name on this Qt.
    pwd = [n for n in nodes if n.get("description") == "Password"]
    check("L2-XT-04", pwd,
          "xtream: the password field carries its label (decision 5, shipped)",
          "descriptions: %r" % [n.get("description") for n in with_role(nodes, "text")])

    # ---- decision 7: the UNCONSENTED sinks --------------------------------
    # No reveal, no eye button, no user action beyond typing. Nothing here
    # says anything about what a deliberately revealed field may publish;
    # decision 8 is unanswered and this lane does not pre-empt it.
    found = leaks(nodes)
    by_token = {}
    for f in found:
        by_token.setdefault(f["token"], []).append("%s/%s" % (f["role"], f["sink"]))

    check("L2-XT-05", SRV_TOKEN not in by_token,
          "decision 7: the provider login pasted into the unmaskable Server "
          "field does not reach the accessibility bus",
          "published on %r" % by_token.get(SRV_TOKEN))
    check("L2-XT-06", USER_TOKEN not in by_token,
          "decision 7: the Xtream username does not reach the accessibility bus",
          "published on %r" % by_token.get(USER_TOKEN))
    check("L2-XT-07", PASS_TOKEN not in by_token,
          "decision 7: the Xtream password does not reach the accessibility bus",
          "published on %r" % by_token.get(PASS_TOKEN))

    # ---- the pairing that stops a data-losing remedy reading as green -----
    # Reading the bus must not change what the user typed. A fix that
    # rebinds a field's text to a masked rendering feeds that rendering back
    # through onTextChanged into the stored value and saves it clean: the
    # credential vanishes from the bus AND from the user's account. Absence
    # of a secret is not success on its own, and these two say so.
    # The probe reports a fingerprint of each field, never the field, so this
    # harness does not become the leak it is looking for.
    check("L2-XT-08", (early.get("digest") == late.get("digest")
                       and bool(late.get("digest"))),
          "the form holds the same values after the bus was read as before it",
          "EARLY digests %r vs LATE digests %r"
          % (early.get("digest"), late.get("digest")))
    intact = late.get("intact") or {}
    check("L2-XT-09", all(intact.get(f) for f in ("server", "username", "password")),
          "the credentials the user typed are still in the form, character for "
          "character -- a fix that empties or masks the STORED value fails here",
          "intact per field: %r, lengths %r" % (intact, late.get("length")))
    # ...and the field must still be findable by the name UX-SOURCES 7.1
    # rules, so "delete the node" is not a way to pass L2-XT-05 either.
    check("L2-XT-10", server and user,
          "the server and username fields are still announced by name in the "
          "same run that the credential check passes")

    # UX-SOURCES 7.1 "Eye button": Accessible.checked MEANS revealed. On the
    # Xtream form nothing is maskable (Model.js:4491 URL_FIELDS), so nothing
    # is revealed, and no eye button may claim otherwise.
    eyes = [n for n in with_role(nodes, "push button")
            if n["name"] in ("Show query", "Hide query")]
    wrong = [n for n in eyes if "checked" in n.get("state_names", [])]
    check("L2-XT-11", not wrong,
          "xtream: no eye button tells a reader the query is revealed when no "
          "field on this form can be masked at all",
          "%d of %d eye buttons publish checked=true" % (len(wrong), len(eyes)))


# ---------------------------------------------------------------- main

def main():
    # KEEP_TREE=1 means "a mutation is already applied to the throwaway tree,
    # do not rebuild it". It has to gate BOTH builders or a bar mutation is
    # silently undone before it is graded.
    if os.environ.get("KEEP_TREE") != "1":
        subprocess.check_call([sys.executable, os.path.join(HERE, "make_tree.py")],
                              stdout=subprocess.DEVNULL)
        subprocess.check_call([sys.executable, os.path.join(HERE, "make_hosts.py")],
                              stdout=subprocess.DEVNULL)
    # Lane 1's fidelity guard gates this run. Lane 2's guide scenarios grade
    # the same generated copy, so every claim below rests on that copy still
    # being the shipping guide. A guard that cannot run is recorded as a
    # FAILURE, never skipped: a green run over a drifted copy looks like
    # proof, which is the whole failure this harness exists to end.
    sys.path.insert(0, os.path.join(REPO, "tests", "a11y"))
    try:
        import fidelity
        drift = fidelity.guard_tree(TREE)
        check("L2-FIDELITY", not drift,
              "the generated copy the guide scenarios grade is still the shipping Guide.qml",
              "; ".join(str(d) for d in drift))
        # The bar half needs no projection: its copy is byte-identical, and
        # make_hosts.py refuses to build a tree where it is not.
        check("L2-FID-BAR", not fidelity.ungraded_surfaces(REPO, {"Guide.qml", "BarWidget.qml"}),
              "every tracked QML that declares accessibility is graded by a scenario",
              "%r" % (fidelity.ungraded_surfaces(REPO, {"Guide.qml", "BarWidget.qml"}),))
    except Exception as exc:      # noqa: BLE001 - reporting it IS the handling
        check("L2-FIDELITY", False,
              "lane 1's fidelity guard could not run, so nothing below is trustworthy",
              "%s: %s" % (type(exc).__name__, exc))

    only = set(sys.argv[1:])
    for name, fn in (("bar", check_bar), ("firstrun", check_firstrun),
                     ("banner", check_banner), ("query", check_query),
                     ("scale", check_scale), ("xtream", check_xtream)):
        if only and name not in only:
            continue
        fn()

    out_json = os.environ.get("LANE2_JSON")
    if out_json:
        open(out_json, "w").write(json.dumps(RESULTS, indent=1))

    failures = [r for r in RESULTS if not r["ok"]]
    print("%d checks, %d failures" % (len(RESULTS), len(failures)))
    for r in failures:
        print("  FAIL %-16s %s" % (r["id"], r["label"]))
        if r["detail"]:
            print("       %s" % r["detail"])

    # The baseline is a SET, and the run is graded against it here rather than
    # by a human comparing counts with a document.
    #
    # That comparison is what failed. 0.7.8 added one unguarded
    # `root.service.recheckBuild()` to Guide.open(); the fake service here has
    # no such method, so open() threw and every statement below it never ran.
    # The run went from 3 failures to 31, every guide scenario fell below its
    # own node-count floor, and it stayed that way through a release --
    # because nobody ran this, and because "compare against the baseline in
    # docs/QA-A11Y.md" is a step a person performs and therefore a step a
    # person skips. A machine does it now.
    ids = sorted(r["id"] for r in failures)
    if ids == sorted(BASELINE):
        print("\nbaseline: exactly the %d recorded failures, and nothing else."
              % len(BASELINE))
        return 0
    unexpected = [i for i in ids if i not in BASELINE]
    fixed = [i for i in BASELINE if i not in ids]
    print("\nOFF BASELINE.")
    if unexpected:
        print("  NEW failures, not in the recorded baseline: %s" % ", ".join(unexpected))
    if fixed:
        print("  recorded failures that now PASS: %s" % ", ".join(fixed))
        print("  if that is the fix, update BASELINE here and the table in docs/QA-A11Y.md")
    return 1


# The failures shipping code is known to produce, by id. Every one is a filed
# defect, not harness noise:
#   L2-XT-05 / L2-XT-06  D-A11Y-1, the Xtream server and username publishing
#                        provider credentials as their accessible Value
#   L2-XT-11             the eye buttons all publish checked=true on a form
#                        where no field can be masked at all
# A run that matches this set exactly is GREEN, because that is what "no
# regression" means for a harness whose baseline is deliberately red.
BASELINE = ["L2-XT-05", "L2-XT-06", "L2-XT-11"]


if __name__ == "__main__":
    sys.exit(main())
