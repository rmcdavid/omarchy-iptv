#!/usr/bin/env python3
"""schedule_oracle.py -- grade an EPG pairing WITHOUT the id-in-URL oracle.

Why this exists (F-EPG-9, and engineering rule 14).
----------------------------------------------------
`docs/QA-EPG-PRECISION.md` graded the name matcher with an independent
oracle: the guide declares every channel under a 24-hex Pluto id, and the
playlist row already carries that id inside its own stream or logo address.
The matcher reads NEITHER, so when the two agree the agreement was not
produced by the thing under test.

The matcher is now being taught to read that id. The moment it does, that
oracle grades the matcher with the matcher's own input and every pair it
matched by id is confirmed by construction -- a check that cannot go red,
which is exactly the shape of D-GS-3 (accessibility rules graded by a grep
for `Accessible.`).

This script is the replacement oracle. It answers
confirmed / contradicted / unknown for any proposed pairing of a playlist
row with a guide channel, and it NEVER reads an id: not the guide's
`<channel id>`, not the hex token in a stream address, not the hex token in
a logo address. Its evidence is the PROGRAMME SCHEDULE -- the half of the
XMLTV file the matcher never opens: titles, descriptions, categories and
times. Note that the frozen guide carries NO channel-level <desc> at all
(all 8,799 <desc> elements hang off <programme>), so the prose this reads is
programme prose, including the self-descriptions a FAST channel repeats in
every slot.

One design rule carries the whole thing, and it is the rule that keeps this
from being a second grep (rule 14):

    THE NAME IS NEVER A CONFIRMING ARM.

Every pair the name matcher produces has equal names by construction, so a
grader that confirms on name similarity confirms 100% of them and can never
go red. Names are used here for exactly one job: CONTRADICTION, where a
distinguishing marker (`+`, a feed number, East/West, a language) separates
our row from the guide channel it was married to while the guide declares a
sibling that carries the marker. That arm CAN fire on a name-matched pair,
and on the frozen data it does.

Confirmation comes only from the schedule:
  E1 title echo    a programme title on the guide channel repeats a token
                   of the playlist row's own name that NO OTHER guide
                   channel uses. This is the only arm on by default, and it
                   is the only one measured at zero false confirmations.
  E3 category fit  the schedule's categories fit the playlist group under a
                   fixed, pre-declared table. OFF by default: measured at 7
                   false confirmations on random negatives and 28 on
                   nearest-name negatives. --category-fit turns it on.
Contradiction comes from two arms:
  C1 prose marker  a programme description spells OUR brand with a
                   distinguishing marker our row does not carry (this is
                   what catches the Bloomberg TV / Bloomberg TV+ pair that
                   shipped before D-EPG-5, and the id oracle grades that
                   pair D -- no identifier -- so it could not see it).
  C2 marker sibling  our row's markers differ from the guide channel's AND
                   the guide declares a sibling that carries ours.

What it cannot see is stated in `docs/QA-EPG-PRECISION.md` section 10 and in
--limits.

Usage (all paths absolute; the frozen inputs are not committed):

  schedule_oracle.py --channels CH.json --guide G.xml.gz MODE

  MODE is one of
    --pairs        reconstruct the shipping pairing and verify it at the sink
    --clusters     simulcast clusters: guide channels no schedule can separate
    --grade        grade the shipping pairing
    --grade --pairings FILE
                   grade a pairing supplied as JSON {"pairs": [[tvgId, cid]]}
                   -- this is how to point it at a NEW matcher
    --sample N     draw the stratified, ID-BLIND hand-check worksheet
    --calibrate    grade the grader against the 65 hand-read pairings
                   embedded in this file (HAND_SAME, HAND_DIFFERENT)
    --negatives    false-confirmation rate over two constructed negative
                   sets: a random cross and a nearest-name cross
    --id-split     ask the OLD id oracle about itself (F-EPG-11)
    --findings     the numbers that settle F-EPG-7, F-EPG-8, F-EPG-10
    --limits       what this oracle cannot see

The id oracle is still computed, in ONE place (`id_oracle`), and only ever
to be COMPARED with this one. No grading path reads it.

Rule 5: nothing here prints a URL. No output path emits `url` or `logo`,
and every provider-controlled string that reaches stdout (channel names,
programme titles, guide prose) goes through the helper's own `redact_urls`
where it could contain one.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

HELPER = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..",
    "bin", "omarchy-iptv")


def load_helper(path=None):
    """Import the shipping helper so the shipping functions are CALLED.

    Rule 12: a grader that reimplements `epg_name_key` grades its own copy.
    `sys.dont_write_bytecode` is set before the load so the import writes no
    `bin/__pycache__` into the tree (CLAUDE.md "Never touch").

    `path` points it at ANOTHER helper, which is how rule 11 is served here:
    `git show <rev>:bin/omarchy-iptv > /tmp/old` and grade the pairing the
    code made before a change.
    """
    sys.dont_write_bytecode = True
    import importlib.machinery
    import importlib.util
    spec = importlib.util.spec_from_loader(
        "omarchy_iptv_helper",
        importlib.machinery.SourceFileLoader(
            "omarchy_iptv_helper", os.path.normpath(path or HELPER)))
    module = importlib.util.module_from_spec(spec)
    sys.modules["omarchy_iptv_helper"] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------- the guide

HEX24 = re.compile(r"\b[0-9a-f]{24}\b", re.IGNORECASE)


def read_guide(path):
    """-> (channels, programmes).

    channels: cid -> {"names": [raw display-names], "desc": str}
    programmes: cid -> [{"start","stop","title","desc","category"}]

    Reads the WHOLE file, not the matcher's window: a schedule signature
    wants every programme the guide published.
    """
    opener = gzip.open if path.endswith(".gz") else open
    channels = {}
    programmes = defaultdict(list)
    with opener(path, "rb") as stream:
        root = None
        for event, elem in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                if root is None:
                    root = elem
                continue
            if elem.tag == "channel":
                cid = (elem.get("id") or "").strip()
                if cid and cid not in channels:
                    names = [(child.text or "").strip()
                             for child in elem.iterfind("display-name")]
                    desc = ""
                    for child in elem.iterfind("desc"):
                        desc = (child.text or "").strip()
                        break
                    channels[cid] = {"names": [n for n in names if n],
                                     "desc": desc}
            elif elem.tag == "programme":
                cid = (elem.get("channel") or "").strip()
                if not cid:
                    continue
                title = elem.find("title")
                desc = elem.find("desc")
                cats = [(c.text or "").strip() for c in elem.iterfind("category")]
                programmes[cid].append({
                    "start": (elem.get("start") or "").strip(),
                    "stop": (elem.get("stop") or "").strip(),
                    "title": (title.text or "").strip() if title is not None else "",
                    "desc": (desc.text or "").strip() if desc is not None else "",
                    "category": "/".join([c for c in cats if c]),
                })
            if root is not None and elem is not root:
                root.clear()
    for items in programmes.values():
        items.sort(key=lambda p: p["start"])
    return channels, dict(programmes)


# ------------------------------------------------- the shipping pairing

def reconstruct_pairs(helper, channels_doc, guide_channels, guide_programmes):
    """-> (pairs, index, guide_names) for the matcher AS IT SHIPS.

    The DECISIONS come from the shipping functions: `build_alias` builds the
    index, `epg_name_key` folds every name, `match_xmltv_channel` picks the
    strategy, `claim_channel` resolves a contest. What is replayed here is
    only `parse_xmltv`'s bookkeeping around them -- which display-name a
    channel element offers and the guide-side uniqueness revocation -- for
    the single reason that `parse_xmltv` returns the window and not the
    pairing that produced it.

    The replay is not trusted. `verify_pairs` checks it at the sink against
    the shipping `epg-now.json`: same key set, and the same programme title
    on every key.
    """
    index, total = helper.build_alias(channels_doc)
    if index is None:
        raise SystemExit("channels.json has no channel list")
    playlist_names = index["name"]

    # parse_xmltv's channel pass: the first display-name a playlist channel
    # claims, blanked on both sides once two channels claim one name.
    guide_names = {}
    owner = {}
    for cid, rec in guide_channels.items():
        if cid in guide_names:
            continue
        name = ""
        for raw in rec["names"]:
            candidate = helper.epg_name_key(raw)
            if candidate and candidate in playlist_names:
                name = candidate
                break
        if not name:
            continue
        held = owner.get(name)
        if held is None:
            owner[name] = cid
            guide_names[cid] = name
        elif held != cid:
            guide_names[held] = ""
            guide_names[cid] = ""

    # parse_xmltv's programme pass, in the guide's own element order.
    claim = {}
    pending = {}
    order = [cid for cid in guide_programmes]
    for cid in order:
        key, rank = helper.match_xmltv_channel(index, cid, guide_names)
        if not key:
            continue
        if helper.claim_channel(claim, pending, key, rank, cid) < 0:
            continue
    pairs = [(key, cid) for key, (rank, cid) in claim.items()]
    pairs.sort()
    return pairs, index, guide_names, total


def verify_pairs(helper, pairs, guide_programmes, now_path, now):
    """Prove the reconstruction at the sink. -> (report dict, ok)."""
    shipped = json.load(open(now_path))["channels"]
    mine = {key for key, _ in pairs}
    theirs = set(shipped)
    title_mismatch = []
    for key, cid in pairs:
        if key not in shipped:
            continue
        want = (shipped[key].get("now") or {}).get("title") or ""
        got = ""
        for prog in guide_programmes.get(cid, []):
            start = helper.parse_xmltv_time(prog["start"], {})
            stop = helper.parse_xmltv_time(prog["stop"], {})
            if start is None:
                continue
            if stop is None:
                stop = start + 3600
            if start <= now < stop:
                got = helper.clean_title(prog["title"])
                break
        if want != got:
            title_mismatch.append(key)
    return {
        "reconstructed": len(mine),
        "shipped": len(theirs),
        "only_reconstructed": sorted(mine - theirs),
        "only_shipped": sorted(theirs - mine),
        "title_mismatch": sorted(title_mismatch),
    }, (mine == theirs and not title_mismatch)


# ------------------------------------------- the id oracle, for COMPARISON

def row_ids(row):
    """Every 24-hex token the playlist row carries, from its own addresses.

    This is the OLD oracle and the NEW matcher's input at once, which is why
    it lives in one function that no grading path calls.
    """
    found = []
    for field in ("url", "logo"):
        for token in HEX24.findall(str(row.get(field) or "")):
            token = token.lower()
            if token not in found:
                found.append(token)
    return found


def id_oracle(row, cid, guide_channels, claimed_by):
    """A/B/C/D exactly as docs/QA-EPG-PRECISION.md section 1.1 defines them."""
    ours = row_ids(row)
    if not ours:
        return "D"
    if cid.lower() in ours:
        return "A"
    declared = [tok for tok in ours if tok in guide_channels]
    if not declared:
        return "B" if claimed_by.get(cid, 0) <= 1 else "C"
    return "C"


# ------------------------------------------------------- the real grader

# Words that are a CHANNEL CATEGORY rather than a mark: a title echoing one
# of these says nothing. Fixed before any measurement, so it cannot be tuned
# to the answer.
GENERIC = set("""
tv television channel network live now today the a an and of on in for with to
from by at it is plus hd sd fhd uhd 4k us usa america american en espanol
news movies movie film films series show shows kids family comedy drama music
sports sport classic classics best great world national local city free
entertainment life lifestyle home food travel crime court reality cooking
documentary docs nature science history action western horror thriller romance
anime cartoon cartoons teen pop rock hits hit radio audio stream streaming
channel1 one two three east west pacific central mountain atlantic
""".split())

# Playlist group -> guide categories that FIT it. Declared before measuring.
# A group with no row here is not graded by category.
GROUP_FITS = {
    "Animation": {"animation", "children", "kids", "comedy", "family", "series", "anime"},
    "Auto": {"series", "documentary", "reality", "sports"},
    "Business": {"news", "business", "series", "documentary"},
    "Classic": {"series", "comedy", "drama", "western", "movie", "film"},
    "Comedy": {"comedy", "series", "sitcom", "movie", "film", "animation"},
    "Cooking": {"cooking", "food", "series", "reality", "lifestyle"},
    "Culture": {"documentary", "series", "arts", "culture", "music"},
    "Documentary": {"documentary", "series", "nature", "science", "history", "reality"},
    "Entertainment": set(),
    "Family": {"family", "children", "kids", "animation", "comedy", "series", "movie", "film"},
    "Kids": {"children", "kids", "animation", "family", "comedy", "series", "anime"},
    "Legislative": {"news", "politics", "series", "documentary"},
    "Movies": {"movie", "film", "western", "horror", "science fiction", "thriller",
               "action", "romance", "drama", "comedy", "crime", "adventure", "mystery",
               "fantasy", "war", "musical", "family", "animation", "documentary"},
    "Music": {"music", "musical", "concert", "series", "classical", "latino", "reality"},
    "News": {"news", "series", "documentary", "politics", "weather", "business"},
    "Outdoor": {"outdoor", "sports", "documentary", "nature", "series", "reality"},
    "Religious": {"religion", "religious", "series", "documentary", "music"},
    "Science": {"science", "documentary", "series", "nature", "technology"},
    "Series": set(),
    "Shop": {"shopping", "series", "reality", "lifestyle"},
    "Sports": {"sports", "sport", "series", "documentary", "reality", "fitness"},
    "Travel": {"travel", "documentary", "series", "nature", "reality", "lifestyle"},
    "Weather": {"weather", "news", "series", "documentary"},
    "Western": {"western", "movie", "film", "series", "drama"},
}

# The two title-echo thresholds. Module-level so --echo-* can move them and
# the sweep in QA-EPG-PRECISION 7.2 can be reproduced.
# census 1 means "no other guide channel's display-name uses this token".
# Measured: at census 1 the title-echo arm makes ZERO false confirmations on
# both constructed negative sets (452 pairings wrong by construction); at
# census 2 it makes 14 and at census 3 it makes 20, for 15 and 21 more real
# confirmations. The sweep is QA-EPG-PRECISION 7.2.
ECHO_MAX_CENSUS = 1
ECHO_MIN_TOKENS = 1
# The category-fit arm is OFF by default and that is a measurement, not
# taste: it confirms 34 real pairs and makes 7 false confirmations on random
# negatives and 28 on nearest-name negatives -- about one in five. An arm
# with that error rate cannot carry a precision acceptance criterion, so it
# is reported as a signal and never as a confirmation unless asked for.
CATEGORY_FIT_CONFIRMS = False

# A marker is a token that DISTINGUISHES two feeds of one brand. These are
# the forms the frozen data actually carries, named individually: an
# open-ended rule here would be F-EPG-10 all over again.
MARKER_TOKENS = {"+", "2", "3", "4", "east", "west", "espanol", "latino",
                 "en espanol", "pride", "hd", "uhd"}


def tokens(helper, text):
    return [t for t in helper.normalize_id_text(text).split(" ") if t]


def distinctive(helper, name):
    """The tokens of a channel name that could identify a programme."""
    out = []
    for tok in tokens(helper, name):
        if tok in GENERIC or len(tok) < 3 or tok.isdigit():
            continue
        if tok not in out:
            out.append(tok)
    return out


def marker_set(helper, name):
    """The distinguishing markers a raw name carries (`+`, a feed number...)."""
    found = set()
    low = helper.normalize_id_text(name)
    for tok in low.split(" "):
        if tok in MARKER_TOKENS:
            found.add(tok)
    if "+" in low:
        found.add("+")
    return found


# The markers that can trail a brand inside prose. ASCII only (rule 8).
PROSE_MARKERS = ("+", " plus", " 2", " 3", " east", " west", " en espanol")


def prose_marker_clash(helper, name, progs):
    """-> ("contradicted", reason, detail) or None.

    Looks for OUR row's brand, spelled contiguously inside a programme
    description, immediately followed by a distinguishing marker that our
    own name does not carry. Evidence: the guide's prose, which the matcher
    never reads.
    """
    core = tokens(helper, name)
    core = [t for t in core if t not in ("", )]
    # Drop the resolution marker the key strips, so "Bloomberg TV (1080p)"
    # looks for "bloomberg tv".
    stripped = helper.epg_name_key(name)
    core = [t for t in stripped.split(" ") if t]
    if len(core) < 2 or "+" in stripped:
        return None
    needle = " ".join(core)
    for prog in progs:
        folded = helper.normalize_id_text(prog["desc"])
        at = folded.find(needle)
        while at >= 0:
            tail = folded[at + len(needle):]
            for mark in PROSE_MARKERS:
                if tail.startswith(mark) and mark.strip() not in core:
                    return ("contradicted", "prose-marker",
                            "guide prose spells this brand as %r"
                            % (needle + mark.rstrip() if mark == "+"
                               else needle + mark))
            at = folded.find(needle, at + 1)
    return None


# The anti-pattern, kept runnable on purpose (--name-oracle). It is the
# grader rule 14 forbids: confirm when the names agree under the matcher's
# own key. Its numbers are the demonstration -- see QA-EPG-PRECISION 7.1.
NAME_ORACLE = False


def grade_pair(helper, row, cid, guide_channels, guide_programmes,
               guide_name_tokens, strict_categories):
    """-> (verdict, reason, detail). The id is never read here."""
    name = str(row.get("name") or "")
    group = str(row.get("group") or "")
    if NAME_ORACLE:
        want = helper.epg_name_key(name)
        for raw in (guide_channels.get(cid) or {"names": []})["names"]:
            if want and helper.epg_name_key(raw) == want:
                return ("confirmed", "name-equal", "the matcher's own key")
        return ("unknown", "name-differs", "")
    marks = distinctive(helper, name)
    progs = guide_programmes.get(cid, [])
    rec = guide_channels.get(cid) or {"names": [], "desc": ""}
    guide_name = rec["names"][0] if rec["names"] else ""

    # --- CONTRADICTION 1, from the SCHEDULE's prose and nothing else. A FAST
    # channel's programme descriptions routinely contain the channel's own
    # self-description, markers and all ("Bloomberg TV+ is a live 24-hour
    # global business and financial news channel"). When that prose spells
    # our row's brand WITH a distinguishing marker our row does not carry,
    # the guide channel is the other feed. This arm reads only
    # <programme><desc>, which the matcher never opens, so it can fire on a
    # pair whose names are equal by construction.
    verdict = prose_marker_clash(helper, name, progs)
    if verdict:
        return verdict

    # --- CONTRADICTION 2, the only arm the NAME is allowed to drive. A marker
    # on one side only, while the guide declares a sibling that carries it,
    # means the guide itself distinguishes two feeds and the pairing picked
    # the other one.
    ours = marker_set(helper, name)
    theirs = marker_set(helper, guide_name)
    if ours != theirs:
        core_ours = set(distinctive(helper, name))
        for other_cid, other in guide_channels.items():
            if other_cid == cid or not other["names"]:
                continue
            other_name = other["names"][0]
            if set(distinctive(helper, other_name)) != core_ours:
                continue
            if marker_set(helper, other_name) == ours:
                return ("contradicted", "marker-sibling",
                        "guide declares a sibling carrying %s"
                        % sorted(ours - theirs or theirs - ours))
    # A marker difference with no sibling to take it is suspicious but not
    # evidence: the guide may simply spell the feed differently.
    marker_odd = ours != theirs

    # --- CONFIRMATION, schedule only.
    if marks and progs:
        # A mark that is distinctive on OUR side can still be a word the
        # guide uses everywhere, so an echo counts only when the token is
        # RARE among the guide's own channel names, and a pair confirms only
        # when enough of the row's marks are echoed TOGETHER in one title.
        # Both thresholds are knobs, swept in QA-EPG-PRECISION 7.2 against
        # two constructed negative sets rather than chosen by eye.
        want = min(ECHO_MIN_TOKENS, len(marks))
        hits = []
        for prog in progs:
            ptoks = set(tokens(helper, prog["title"]))
            shared = [m for m in marks
                      if m in ptoks
                      and guide_name_tokens.get(m, 0) <= ECHO_MAX_CENSUS]
            if len(shared) >= want:
                hits.append((prog["title"], shared))
        if hits:
            rare = [m for _, sh in hits for m in sh]
            return ("confirmed", "title-echo",
                    "%d of %d programmes repeat %s"
                    % (len(hits), len(progs), sorted(set(rare))[:3]))
    if marks and rec["desc"]:
        dtoks = set(tokens(helper, rec["desc"]))
        shared = [m for m in marks
                  if m in dtoks and guide_name_tokens.get(m, 0) <= 3]
        if shared:
            return ("confirmed", "desc-echo",
                    "channel prose repeats %s" % sorted(set(shared))[:3])
    if progs and group in GROUP_FITS and GROUP_FITS[group]:
        fits = GROUP_FITS[group]
        seen = Counter()
        for prog in progs:
            for part in prog["category"].lower().split("/"):
                part = part.strip()
                if part:
                    seen[part] += 1
        if seen:
            inside = sum(n for cat, n in seen.items() if cat in fits)
            total = sum(seen.values())
            share = inside / float(total)
            if share == 0.0 and total >= 5 and strict_categories:
                return ("contradicted", "category-clash",
                        "no category of %d fits group %s: %s"
                        % (total, group, sorted(seen)[:4]))
            if share >= 0.8 and total >= 3 and not marker_odd \
                    and CATEGORY_FIT_CONFIRMS:
                return ("confirmed", "category-fit",
                        "%d/%d programme categories fit group %s"
                        % (inside, total, group))
    return ("unknown", "marker-odd" if marker_odd else "no-signal",
            "%d programmes, marks %s" % (len(progs), marks[:3]))


def guide_token_census(helper, guide_channels):
    """How many guide channels use each token in a display-name."""
    census = Counter()
    for rec in guide_channels.values():
        seen = set()
        for raw in rec["names"]:
            for tok in tokens(helper, raw):
                seen.add(tok)
        for tok in seen:
            census[tok] += 1
    return census


# ------------------------------------------------- the hand-checked sample
#
# 65 pairings read by a human on 2026-10-04 from the ID-BLIND worksheet
# `--sample 44` prints (seed 20261004), plus 20 nearest-name negatives and
# the one pairing the matcher really got wrong before D-EPG-5, and
# recorded HERE rather than in a side file so a reader cannot run the
# calibration against a different sample than the one that was judged.
#
# How the 44 were drawn: stratified by quota over features the ID CANNOT
# SEE -- the oracle's own verdict, membership of a simulcast cluster, a
# single-token key, whether the key needed a marker strip -- deliberately
# over-weighting the strata the oracle finds hard (every `contradicted` and
# every `simulcast` pair, 16 `unknown`, then 8 each of the rest). A uniform
# draw would have been mostly `plain` and would have measured nothing.
#
# The 20 constructed negatives are each row against the guide channel whose name is
# CLOSEST to it without being its partner (difflib), which is the hardest
# wrong pairing the data offers: sibling brands and same-city news. They are
# wrong by construction, and all 20 were read to confirm the construction is
# sound rather than taken on faith.
#
# The judgement is the reader's, from the playlist name, the group, the
# guide display-name and the programme titles and categories. No id was on
# the worksheet, and the reader did not look one up.
HAND_SAME = {
    "BETVisionaries.us@SD": "black cinema library on a channel of that name",
    "BounceXL.us@SD": "Mann & Wife is Bounce TV's own series",
    "OANPlus.us@SD": "OAN's own presenters by name",
    "Vevo2K.us@SD": "2000s music video blocks",
    "SupernaturalDrama.us@SD": "Ghost Whisperer, supernatural drama",
    "90sKidsTV2.us@SD": "Drake and Josh, Are You Afraid Of The Dark",
    "ToughJobs.us@SD": "Duck Dynasty, a working-trade reality library",
    "BETComedyMovies.us@SD": "Friday, Next Friday, BET comedy library",
    "PlutoTVComedy.us@US": "comedy features",
    "PlutoTVGameShows.us@SD": "Pictionary",
    "50CentAction.us@SD": "Arsenal, Primal, The Frozen Ground -- all 50 Cent",
    "YuGiOh.us@SD": "Yu-Gi-Oh! ZEXAL episodes",
    "PlutoTVFranchiseFavorites.us@SD": "the Jack Ryan films, one franchise",
    "LoveHipHop.us@SD": "Love & Hip Hop Atlanta and New York",
    "NBCSportsNOW.us@SD": "The Dan Patrick Show, NBC Sports talk",
    "PlutoTVStaffPicks.us@SD": "a curated film run",
    "MLB.us@SD": "Series Rewind, Great Games, category Sports",
    "PokerGo.us@US": "PokerGO Tour",
    "Degrassi.us@US": "Degrassi: The Next Generation",
    "MST3K.us@US": "Mystery Science Theater 3000",
    "Heartland.us@Eastern": "Heartland",
    "Classica.us@SD": "Mahler, Orff, Beethoven; category Classical",
    "Survivor.us@SD": "Survivor",
    "RiffTrax.us@US": "RiffTrax shorts and features",
    "BabySharkTV.us@SD": "Pinkfong and Baby Shark",
    "CBSNewsDetroit.us@SD": "CBS News Detroit's own 11pm bulletin",
    "EstrellaNews.us@SD": "Noticias 62 Los Angeles, Estrella News Miami",
    "AmericasVoiceNews.us@SD": "AVN's own programme names",
    "GolazoNetwork.us@SD": "soccer highlights, category Sports",
    "MTVFlowLatino.us@SD": "MTV Flow Latino",
    "AntiquesRoadTrip.us@SD": "Antiques Road Trip",
    "48Hours.us@US": "48 Hours",
    "BeyondtheGates.us@SD": "Beyond the Gates",
    "WildNOut.us@SD": "Nick Cannon Presents: Wild 'N Out",
    "BlackInkCrew.us@SD": "Black Ink Crew",
    "BellatorMMA.us@SD": "Bellator MMA Full Fight Cards",
    "HogansHeroes.us@SD": "Hogan's Heroes",
    "BeverlyHills90210.us@SD": "Beverly Hills, 90210",
    "TheAddamsFamily.us@SD": "The Addams Family",
    "TheChallenge.us@SD": "The Challenge (the guide's category is wrong, the title is not)",
    "PlutoTVCompetition.us@SD": "Forged in Fire, Hot Ones, competition reality",
    "ComedyCentralenEspanol.us@SD": "South Park and La familia del barrio, in Spanish",
    "MidsomerMurders.us@SD": "Midsomer Murders",
    "CBSNewsBaltimore.us@SD": "WJZ is Baltimore's CBS station",
}

# (tvgId, guide cid) -> why the reader called it a different channel.
HAND_DIFFERENT = {
    ("CBSNewsColorado.us@SD", "60cb6df2b2ad610008cd5bea"): "Sacramento's CBS13 bulletins, not Colorado's",
    ("Buzzr.us@SD", "60d39387706fe50007fda8e8"): "bull riding against a game-show channel",
    ("CourtTV.us@SD", "6a70da97a4bf6cded4fdaf53"): "Dora the Explorer against a court channel",
    ("CSIMiami.us@SD", "60fb299b79498900070b29e0"): "Miami local news against a drama series channel",
    ("BeverlyHillbillies.us@US", "5f4d83e0a382c00007bc02e7"): "90210 is not the Hillbillies; one shared word",
    ("AmericasNextTopModel.us@SD", "691cf0410a78a9ce61ad2121"): "Funniest Home Videos, a different show",
    ("CineAmor.us@SD", "5d8d180092e97a5e107638d3"): "horror features on a romance channel",
    ("KartoonChannel.us@SD", "5ced7d5df64be98e07ed47b6"): "NFL programming on a children's channel",
    ("CMTEqualPlay.us@SD", "5ca671f215a62078d2ec0abf"): "South Park on a country-music channel",
    ("GolazoNetwork.us@SD", "69699ae5d301d54fb3dc1499"): "self-improvement talk on a soccer channel",
    ("CBSenespanol.us@SD", "604928d54a4f730007ff76bc"): "CSI en espanol is a series, not the CBS feed",
    ("BellatorMMA.us@SD", "58af4c093a41ca9d4ecabe96"): "feature films on an MMA channel",
    ("HSN.us@East", "5dae084727c8af0009fe40a4"): "Tosh.0 on a shopping channel",
    ("PGATour.us@SD", "63a0e33a45264d000850ed7e"): "soccer on a golf channel",
    ("RiffTrax.us@US", "6565430c9d5ac4000822f508"): "Living Alaska on a comedy channel",
    ("CBSNewsBoston.us@SD", "5a6b92f6e22a617379789618"): "the national 24/7 feed, not Boston's",
    ("00sReplay.us@SD", "5ca525b650be2571e3943c63"): "1980s comedies on a 2000s channel",
    ("ClassicTVFamilies.us@US", "5f15e3cccf49290007053c67"): "Diagnosis Murder is the Drama channel's run",
    ("50CentAction.us@SD", "561d7d484dc7c8770484914a"): "a generic action library, no 50 Cent films",
    ("SupernaturalDrama.us@SD", "6675c713fc3a46000863dde7"): "Greenleaf and Power, not supernatural",
    # The 21st, and the only one that is not constructed: the pairing the
    # matcher really made before D-EPG-5 (b2f944d^). Read the same way --
    # the guide's own prose calls this channel Bloomberg TV+, which is a
    # separate service from Bloomberg Television, and the playlist row's
    # tvg-id is BloombergTV.us.
    ("BloombergTV.us@US", "54ff7ba69222cb1c2624c584"): "the guide's prose names this channel Bloomberg TV+, a different service",
}


# ----------------------------------------------------- simulcast clusters

def schedule_signature(progs):
    """What a schedule oracle can see of a channel. Two channels with equal
    signatures are the same playout and NO schedule oracle can separate
    them."""
    return tuple((p["start"], p["title"]) for p in progs)


def simulcast_clusters(guide_programmes, minimum=3):
    groups = defaultdict(list)
    for cid, progs in guide_programmes.items():
        if len(progs) < minimum:
            continue
        groups[schedule_signature(progs)].append(cid)
    return {sig: cids for sig, cids in groups.items() if len(cids) > 1}


def title_only_clusters(guide_programmes, minimum=3):
    """The weaker signature: the same titles in the same order, times free.
    A time-shifted sibling (a `+1`) lands here and not above."""
    groups = defaultdict(list)
    for cid, progs in guide_programmes.items():
        if len(progs) < minimum:
            continue
        groups[tuple(p["title"] for p in progs)].append(cid)
    return {sig: cids for sig, cids in groups.items() if len(cids) > 1}


# ------------------------------------------------------------------ modes

def load_inputs(args):
    helper = load_helper(args.helper or None)
    channels_doc = json.load(open(args.channels))
    guide_channels, guide_programmes = read_guide(args.guide)
    return helper, channels_doc, guide_channels, guide_programmes


def row_table(channels_doc):
    rows = {}
    for row in channels_doc.get("channels") or []:
        tvg = row.get("tvgId")
        if isinstance(tvg, str) and tvg and tvg not in rows:
            rows[tvg] = row
    return rows


def read_pairings(path):
    doc = json.load(open(path))
    return [(str(a), str(b)) for a, b in doc["pairs"]]


def mode_pairs(args, helper, channels_doc, guide_channels, guide_programmes):
    pairs, index, guide_names, total = reconstruct_pairs(
        helper, channels_doc, guide_channels, guide_programmes)
    out = {
        "playlistChannels": total,
        "guideDeclarations": len(guide_channels),
        "guideChannelsWithProgrammes": len(guide_programmes),
        "pairs": len(pairs),
        "nameIndexed": index["nameIndexed"],
        "nameDroppedPlaylist": index["nameDroppedPlaylist"],
    }
    if args.now_json:
        report, ok = verify_pairs(helper, pairs, guide_programmes,
                                  args.now_json, args.now)
        out["sinkCheck"] = report
        out["sinkCheckPassed"] = ok
    print(json.dumps(out, indent=2))
    return pairs


def mode_clusters(args, helper, channels_doc, guide_channels, guide_programmes):
    exact = simulcast_clusters(guide_programmes)
    loose = title_only_clusters(guide_programmes)
    sizes = Counter(len(cids) for cids in exact.values())
    print(json.dumps({
        "guideChannelsWithProgrammes": len(guide_programmes),
        "exactSignatureClusters": len(exact),
        "channelsInAnExactCluster": sum(len(c) for c in exact.values()),
        "clusterSizes": dict(sorted(sizes.items())),
        "titleOrderClusters": len(loose),
        "channelsInATitleOrderCluster": sum(len(c) for c in loose.values()),
        "examples": [[guide_channels[c]["names"][0] if guide_channels.get(c, {}).get("names") else c
                      for c in cids]
                     for cids in list(exact.values())[:8]],
    }, indent=2))


def grade_all(helper, pairs, rows, guide_channels, guide_programmes,
              strict_categories=False):
    census = guide_token_census(helper, guide_channels)
    claimed_by = Counter()
    for _, cid in pairs:
        claimed_by[cid] += 1
    graded = []
    for key, cid in pairs:
        row = rows.get(key)
        if row is None:
            continue
        verdict, reason, detail = grade_pair(
            helper, row, cid, guide_channels, guide_programmes, census,
            strict_categories)
        graded.append({
            "tvgId": key,
            "cid": cid,
            "name": row.get("name"),
            "group": row.get("group"),
            "guideName": (guide_channels.get(cid) or {}).get("names", [""])[0],
            "verdict": verdict,
            "reason": reason,
            "detail": detail,
        })
    return graded, claimed_by


def mode_grade(args, helper, channels_doc, guide_channels, guide_programmes):
    rows = row_table(channels_doc)
    if args.pairings:
        pairs = read_pairings(args.pairings)
    else:
        pairs, _, _, _ = reconstruct_pairs(
            helper, channels_doc, guide_channels, guide_programmes)
    graded, claimed_by = grade_all(helper, pairs, rows, guide_channels,
                                   guide_programmes, args.strict_categories)
    counts = Counter(g["verdict"] for g in graded)
    reasons = Counter(g["reason"] for g in graded)
    idcounts = Counter()
    cross = Counter()
    for g in graded:
        grade = id_oracle(rows[g["tvgId"]], g["cid"], guide_channels, claimed_by)
        idcounts[grade] += 1
        cross[(g["verdict"], grade)] += 1
        g["idOracle"] = grade
    print(json.dumps({
        "pairs": len(graded),
        "scheduleOracle": dict(counts),
        "reasons": dict(reasons),
        "idOracle": dict(sorted(idcounts.items())),
        "cross": {"%s/%s" % k: v for k, v in sorted(cross.items())},
        "contradicted": [g for g in graded if g["verdict"] == "contradicted"],
    }, indent=2))
    if args.dump:
        with open(args.dump, "w") as handle:
            json.dump(graded, handle, indent=1)


def mode_sample(args, helper, channels_doc, guide_channels, guide_programmes):
    """Draw the hand-check worksheet. ID-BLIND on purpose: the strata are
    computed from the names, the groups and the schedule only, so the draw
    cannot be accused of selecting on the answer, and the worksheet carries
    no id for the reader to peek at."""
    rows = row_table(channels_doc)
    pairs, _, _, _ = reconstruct_pairs(
        helper, channels_doc, guide_channels, guide_programmes)
    graded, _ = grade_all(helper, pairs, rows, guide_channels, guide_programmes)
    by_key = {g["tvgId"]: g for g in graded}
    exact = simulcast_clusters(guide_programmes)
    in_cluster = {c for cids in exact.values() for c in cids}
    strata = defaultdict(list)
    for g in graded:
        row = rows[g["tvgId"]]
        key = helper.epg_name_key(row.get("name"))
        if g["verdict"] == "contradicted":
            strata["contradicted"].append(g)
        elif g["cid"] in in_cluster:
            # First, not last: a pair on a channel no schedule oracle can
            # separate is the hardest case there is, and sorting it under
            # `unknown` would hide it.
            strata["simulcast"].append(g)
        elif g["verdict"] == "unknown":
            strata["unknown"].append(g)
        elif len(key.split(" ")) == 1:
            strata["single-token"].append(g)
        elif helper.epg_name_key(row.get("name")) != helper.normalize_id_text(row.get("name") or ""):
            strata["marker-stripped"].append(g)
        else:
            strata["plain"].append(g)
    # Fixed quotas, declared here rather than derived from the population, so
    # the sample is deliberately OVER-weighted toward the cases the grader
    # finds hard. A uniform draw of 40 from 226 would be 25 easy `plain`
    # pairs and would measure almost nothing.
    quota = {"contradicted": 99, "unknown": 16, "simulcast": 99,
             "single-token": 8, "marker-stripped": 8, "plain": 8}
    rng = random.Random(args.seed)
    picked = []
    for name in ("contradicted", "unknown", "simulcast", "single-token",
                 "marker-stripped", "plain"):
        pool = list(strata[name])
        rng.shuffle(pool)
        picked.extend(pool[:quota[name]])
    if args.sample > len(picked):
        rest = [g for g in graded if g not in picked]
        rng.shuffle(rest)
        picked.extend(rest[:args.sample - len(picked)])
    sheet = []
    for g in picked:
        row = rows[g["tvgId"]]
        progs = guide_programmes.get(g["cid"], [])
        sheet.append({
            "tvgId": g["tvgId"],
            "playlistName": row.get("name"),
            "group": row.get("group"),
            "guideDisplayNames": (guide_channels.get(g["cid"]) or {}).get("names", []),
            "guideDesc": helper.redact_urls((guide_channels.get(g["cid"]) or {}).get("desc", ""))[:300],
            "programmeTitles": [helper.redact_urls(p["title"]) for p in progs[:8]],
            "programmeCategories": sorted({p["category"] for p in progs if p["category"]})[:6],
            "judgement": "",
            "why": "",
        })
    strata_counts = {k: len(v) for k, v in sorted(strata.items())}
    print(json.dumps({"strata": strata_counts, "drawn": len(sheet),
                      "sheet": sheet}, indent=1))


def mode_id_split(args, helper, channels_doc, guide_channels, guide_programmes):
    """Ask the OLD oracle about itself. F-EPG-11.

    "The playlist row already carries that id" is one sentence covering two
    different fields: the stream address and the logo address. They are not
    the same evidence and they do not always agree. This mode grades every
    pairing twice, once with the stream token alone and once with the logo
    token alone, and counts the rows where the two disagree -- which is the
    measurement that says how much weight a C grade can carry.

    This mode READS THE ID on purpose. It is a diagnostic of the old oracle,
    never an input to the new one.
    """
    rows = row_table(channels_doc)
    if args.pairings:
        pairs = read_pairings(args.pairings)
    else:
        pairs, _, _, _ = reconstruct_pairs(
            helper, channels_doc, guide_channels, guide_programmes)
    claimed_by = Counter(cid for _, cid in pairs)

    def one_field(row, field):
        trimmed = {"url": "", "logo": ""}
        trimmed[field] = row.get(field) or ""
        return trimmed

    both_present = 0
    disagree_tokens = 0
    cross = Counter()
    split = []
    for key, cid in pairs:
        row = rows.get(key)
        if row is None:
            continue
        url_tokens = [t for t in HEX24.findall(str(row.get("url") or ""))]
        logo_tokens = [t for t in HEX24.findall(str(row.get("logo") or ""))]
        if url_tokens and logo_tokens:
            both_present += 1
            if {t.lower() for t in url_tokens} != {t.lower() for t in logo_tokens}:
                disagree_tokens += 1
        by_url = id_oracle(one_field(row, "url"), cid, guide_channels, claimed_by)
        by_logo = id_oracle(one_field(row, "logo"), cid, guide_channels, claimed_by)
        cross[(by_url, by_logo)] += 1
        if by_url != by_logo and "D" not in (by_url, by_logo):
            split.append({"name": row.get("name"),
                          "guideName": (guide_channels.get(cid) or {}).get("names", [""])[0],
                          "byStream": by_url, "byLogo": by_logo})
    whole = Counter()
    for key, cid in pairs:
        row = rows.get(key)
        if row is not None:
            whole[id_oracle(row, cid, guide_channels, claimed_by)] += 1
    # And the same question over the WHOLE playlist, not only the pairs.
    all_both = all_disagree = 0
    for row in channels_doc.get("channels") or []:
        url_tokens = {t.lower() for t in HEX24.findall(str(row.get("url") or ""))}
        logo_tokens = {t.lower() for t in HEX24.findall(str(row.get("logo") or ""))}
        if url_tokens and logo_tokens:
            all_both += 1
            if url_tokens != logo_tokens:
                all_disagree += 1
    print(json.dumps({
        "pairs": len(pairs),
        "idOracleAsPublished": dict(sorted(whole.items())),
        "pairsWithATokenInBothFields": both_present,
        "pairsWhereTheTwoFieldsNameDifferentChannels": disagree_tokens,
        "playlistRowsWithATokenInBothFields": all_both,
        "playlistRowsWhereTheTwoFieldsDisagree": all_disagree,
        "streamVsLogoGrade": {"%s/%s" % k: v for k, v in sorted(cross.items())},
        "pairsGradedDifferentlyByTheTwoFields": split,
    }, indent=2))


def mode_negatives(args, helper, channels_doc, guide_channels, guide_programmes):
    """Measure FALSE CONFIRMATIONS on pairings that are wrong by construction.

    The hand-checked sample cannot do this job: every pair the shipping
    matcher makes reads as the same channel to a human, so a sample of real
    pairs measures false CONTRADICTIONS and nothing else. Specificity needs
    known-wrong pairs, and the data supplies them -- cross a row with a guide
    channel that is not its partner and the pairing is wrong.

    Two sets, because they are not the same question:
      random   each matched row against a uniformly drawn other guide
               channel. The easy negative.
      nearest  each matched row against the guide channel whose name is
               closest to the row's WITHOUT being its partner, measured with
               difflib (stdlib, rule 3) -- deliberately not the matcher's
               key. These are sibling feeds and same-brand channels: the
               negatives that matter.
    """
    import difflib
    rows = row_table(channels_doc)
    pairs, _, _, _ = reconstruct_pairs(
        helper, channels_doc, guide_channels, guide_programmes)
    census = guide_token_census(helper, guide_channels)
    cids = [cid for cid in guide_channels if guide_programmes.get(cid)]
    guide_first = {cid: (rec["names"][0] if rec["names"] else "")
                   for cid, rec in guide_channels.items()}
    rng = random.Random(args.seed)
    out = {}
    for which in ("random", "nearest"):
        verdicts = Counter()
        examples = []
        for key, truth in pairs:
            row = rows.get(key)
            if row is None:
                continue
            if which == "random":
                pick = truth
                for _ in range(20):
                    pick = rng.choice(cids)
                    if pick != truth:
                        break
                if pick == truth:
                    continue
            else:
                name = str(row.get("name") or "")
                best, score = "", -1.0
                for cid in cids:
                    if cid == truth:
                        continue
                    ratio = difflib.SequenceMatcher(
                        None, helper.normalize_id_text(name),
                        helper.normalize_id_text(guide_first.get(cid, ""))).ratio()
                    if ratio > score:
                        best, score = cid, ratio
                if not best:
                    continue
                pick = best
            verdict, reason, detail = grade_pair(
                helper, row, pick, guide_channels, guide_programmes, census,
                args.strict_categories)
            verdicts[verdict + "/" + reason] += 1
            verdicts[verdict] += 1
            if verdict == "confirmed" and len(examples) < 12:
                examples.append({"name": row.get("name"),
                                 "pairedWith": guide_first.get(pick, ""),
                                 "reason": reason, "detail": detail})
        total = sum(v for k, v in verdicts.items() if "/" not in k)
        out[which] = {
            "pairings": total,
            "verdicts": {k: v for k, v in sorted(verdicts.items())},
            "falseConfirmationRate":
                round(verdicts["confirmed"] / float(total or 1), 4),
            "falseConfirmations": examples,
        }
    print(json.dumps(out, indent=2))


def mode_calibrate(args, helper, channels_doc, guide_channels, guide_programmes):
    """Grade the grader against the 65 hand-read pairings above.

    Reports the two errors separately, because they are not symmetrical: a
    false CONFIRMATION lets a wrong programme onto a row, which is what the
    acceptance criterion forbids; a false CONTRADICTION only costs a blank
    row. `unknown` is not an error, it is the oracle's coverage cost, and it
    is reported as such.
    """
    rows = row_table(channels_doc)
    pairs, _, _, _ = reconstruct_pairs(
        helper, channels_doc, guide_channels, guide_programmes)
    graded, claimed_by = grade_all(helper, pairs, rows, guide_channels,
                                   guide_programmes, args.strict_categories)
    by_key = {g["tvgId"]: g for g in graded}
    census = guide_token_census(helper, guide_channels)
    cross = Counter()
    errors = []
    missing = []
    for key, why in sorted(HAND_SAME.items()):
        g = by_key.get(key)
        if g is None:
            missing.append(key)
            continue
        cross[("same", g["verdict"])] += 1
        if g["verdict"] == "contradicted":
            errors.append({"kind": "false contradiction", "tvgId": key,
                           "humanSaid": why, "reason": g["reason"],
                           "detail": g["detail"]})
    for (key, cid), why in sorted(HAND_DIFFERENT.items()):
        row = rows.get(key)
        if row is None:
            missing.append(key)
            continue
        verdict, reason, detail = grade_pair(
            helper, row, cid, guide_channels, guide_programmes, census,
            args.strict_categories)
        cross[("different", verdict)] += 1
        if verdict == "confirmed":
            errors.append({"kind": "false confirmation", "tvgId": key,
                           "humanSaid": why, "reason": reason,
                           "detail": detail})
    same = sum(v for (h, _), v in cross.items() if h == "same")
    diff = sum(v for (h, _), v in cross.items() if h == "different")
    print(json.dumps({
        "handChecked": same + diff,
        "readAsTheSameChannel": same,
        "readAsDifferentChannels": diff,
        "humanVsSchedule": {"%s/%s" % k: v for k, v in sorted(cross.items())},
        "falseConfirmations": cross[("different", "confirmed")],
        "falseContradictions": cross[("same", "contradicted")],
        "silentOnARightPair": cross[("same", "unknown")],
        "caughtAWrongPair": cross[("different", "contradicted")],
        "errors": errors,
        "notInThisPairing": missing,
    }, indent=2))


def mode_findings(args, helper, channels_doc, guide_channels, guide_programmes):
    rows = row_table(channels_doc)
    names = [str(r.get("name") or "") for r in channels_doc["channels"]]
    guide_first = {cid: (rec["names"][0] if rec["names"] else "")
                   for cid, rec in guide_channels.items()}
    # F-EPG-7: the parenthetical.
    paren = re.compile(r"\(([^)]*)\)")
    us = [n for n in names if "(united states)" in n.lower()]
    guide_paren = Counter()
    for raw in guide_first.values():
        for inner in paren.findall(raw):
            guide_paren[inner.lower()] += 1
    # F-EPG-8: Tennis Channel, by schedule.
    tennis = {cid: raw for cid, raw in guide_first.items()
              if "tennis" in raw.lower()}
    tennis_scheds = {cid: [p["title"] for p in guide_programmes.get(cid, [])]
                     for cid in tennis}
    # F-EPG-10: bracket spans.
    bracket = re.compile(r"\[[^\]]*\]")
    pl_br = [n for n in names if bracket.search(n)]
    guide_br = [raw for raw in guide_first.values() if bracket.search(raw)]
    guide_br_any = [n for rec in guide_channels.values() for n in rec["names"]
                    if bracket.search(n)]
    print(json.dumps({
        "F-EPG-7": {
            "playlistNamesWithUnitedStates": len(us),
            "playlistNamesWithAnyParenthetical":
                len([n for n in names if paren.search(n)]),
            "guideNamesWithAnyParenthetical": sum(guide_paren.values()),
            "guideParentheticalContents": dict(guide_paren.most_common(10)),
        },
        "F-EPG-8": {
            "guideTennisChannels": tennis,
            "scheduleOverlap": tennis_scheds,
        },
        "F-EPG-10": {
            "playlistNamesWithBracketSpan": len(pl_br),
            "bracketSpanContents": dict(
                Counter(m for n in pl_br for m in bracket.findall(n)).most_common(6)),
            "guideFirstNamesWithBracketSpan": len(guide_br),
            "guideAnyDisplayNameWithBracketSpan": len(guide_br_any),
        },
    }, indent=2))


def mode_limits(args, *rest):
    print(__doc__)


def main(argv=None):
    global ECHO_MAX_CENSUS, ECHO_MIN_TOKENS, CATEGORY_FIT_CONFIRMS, NAME_ORACLE
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--channels", help="frozen channels.json")
    parser.add_argument("--guide", help="frozen XMLTV (.xml or .xml.gz)")
    parser.add_argument("--now-json", default="", help="epg-now.json to verify against")
    parser.add_argument("--now", type=int, default=1791015219)
    parser.add_argument("--helper", default="",
                        help="grade the pairing ANOTHER helper makes "
                             "(rule 11: the code as it was)")
    parser.add_argument("--pairings", default="", help='JSON {"pairs": [[tvgId, cid], ...]}')
    parser.add_argument("--dump", default="", help="write the per-pair grades here")
    parser.add_argument("--seed", type=int, default=20261004)
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--calibrate", action="store_true",
                        help="grade the grader against the embedded "
                             "hand-checked sample")
    parser.add_argument("--echo-max-census", type=int, default=ECHO_MAX_CENSUS,
                        help="an echoed token may appear in at most this many "
                             "guide display-names (default %d)" % ECHO_MAX_CENSUS)
    parser.add_argument("--echo-min-tokens", type=int, default=ECHO_MIN_TOKENS,
                        help="this many of the row's distinctive tokens must "
                             "be echoed in ONE programme title (default %d)"
                             % ECHO_MIN_TOKENS)
    parser.add_argument("--name-oracle", action="store_true",
                        help="replace the grader with the one rule 14 "
                             "forbids -- confirm when the names agree under "
                             "the matcher's own key -- so its numbers can be "
                             "shown rather than asserted")
    parser.add_argument("--category-fit", action="store_true",
                        help="ALSO confirm on a group/category fit. Off by "
                             "default and measured: 34 real confirmations "
                             "against 7 false ones on random negatives and 28 "
                             "on nearest-name negatives.")
    parser.add_argument("--strict-categories", action="store_true",
                        help="ALSO contradict on a group/category clash. Off "
                             "by default and measured: on the 226 shipping "
                             "pairs it fires twice and both are FALSE "
                             "contradictions (50 Cent Action, Hallmark "
                             "Movies & More -- group Movies against "
                             "categories Entertainment/Series). Kept behind "
                             "a flag so the measurement is reproducible.")
    for flag in ("pairs", "clusters", "grade", "findings", "limits",
                 "negatives", "id-split"):
        parser.add_argument("--" + flag, action="store_true")
    args = parser.parse_args(argv)
    ECHO_MAX_CENSUS = args.echo_max_census
    ECHO_MIN_TOKENS = args.echo_min_tokens
    CATEGORY_FIT_CONFIRMS = args.category_fit
    NAME_ORACLE = args.name_oracle
    if args.limits:
        return mode_limits(args)
    if not args.channels or not args.guide:
        parser.error("--channels and --guide are required")
    bundle = load_inputs(args)
    if args.pairs:
        mode_pairs(args, *bundle)
    elif args.clusters:
        mode_clusters(args, *bundle)
    elif args.grade:
        mode_grade(args, *bundle)
    elif args.sample:
        mode_sample(args, *bundle)
    elif args.calibrate:
        mode_calibrate(args, *bundle)
    elif args.negatives:
        mode_negatives(args, *bundle)
    elif args.id_split:
        mode_id_split(args, *bundle)
    elif args.findings:
        mode_findings(args, *bundle)
    else:
        parser.error("pick a mode: --pairs --clusters --grade --sample N "
                     "--calibrate --negatives --id-split --findings "
                     "--limits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
