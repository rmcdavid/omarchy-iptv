#!/usr/bin/env python3
"""scripts/dev-harness/spikes/barconfig-window/analyze.py -- one start of
run.sh, laid out: for every service the host created, which API object it
was handed, what it read, when the window closed, where the state load and
the marker's save fell against that, and what state.json held.

  analyze.py START_FOLDER NAME

Reads START_FOLDER's qs.log (the rig block's `RIG-W <ms> <seq> ...` lines,
the service's `IPTV-LOG <ms> ...` lines from service-log.patch, the stacks
the block's console.trace() printed), snaps.jsonl (snap.py: every
state.json that landed), rstate.jsonl (the block's `rigw state` replies),
shell.json.start (the playlist the fixture named) and state.json.end.
Prints one block and a closing
`verdict` line per service. Every reading is a line some process wrote;
nothing is inferred from timing alone.

THE WINDOW, per service: OPEN when the service's onShellChanged read its
shell's layout sections as sequences (`seq`, the shape createObject's
property map leaves: not an Array, a length, indexable) -- the API object
createScopedPluginShell made fresh, which the service then reads its
settings from (Model.findBarEntry answers `{}`, `entry=[]`); CLOSED at the
first assignment of that object's barConfig from script (syncPluginApis,
shell.qml 904: `apiBarConfig` with every section an `array`), or at once
when the object was already so (`cached`, or a fresh one whose sections
read `array`). A state load whose readout still reads `seq` fell INSIDE it;
one that reads every section an `array` fell AFTER it; one whose readout
names no section (`none`) or another mix (`mixed`, a section undefined: no
shell) is reported as `unknown-<kind>`, never as after, because the
service read no Array there (lane-dh15fix2: no kept start has one). The
service's FIRST state load is the one judged.
Python 3 standard library only.
"""
import json
import os
import re
import sys

ANSI = re.compile(r"\x1b\[[0-9;]*m")
RIG = re.compile(r"RIG-W (\d+) (\d+) (.*)$")
SVC = re.compile(r"IPTV-LOG (\d+) (.*)$")
FRAME = re.compile(r"^([A-Za-z_$][\w$]*)? ?\((\S+):(\d+)\)$")


def parse(lines):
    """The log as events, in the order they were written: ("rig", ms, text),
    ("svc", ms, text), ("warn", None, text) for the service's own
    `omarchy-iptv:` lines, and ("trace", None, [function names]) for the
    frames a console.trace() printed under the line before it."""
    events = []
    trace = None
    for raw in lines:
        line = ANSI.sub("", raw.rstrip("\n"))
        m = FRAME.match(line.strip())
        if "on_PluginShellApisChanged (" in line:
            trace = [line.split(": ", 1)[-1].split(" (", 1)[0]]
            events.append(("trace", None, trace))
            continue
        if trace is not None and m and not RIG.search(line) and not SVC.search(line):
            trace.append(m.group(1) or "")
            continue
        trace = None
        r = RIG.search(line)
        if r:
            events.append(("rig", int(r.group(1)), r.group(3)))
            continue
        s = SVC.search(line)
        if s:
            events.append(("svc", int(s.group(1)), s.group(2)))
            continue
        if "omarchy-iptv: " in line:
            events.append(("warn", None, line.split("omarchy-iptv: ", 1)[1]))
    return events


def field(text, name):
    m = re.search(r"(?:^| )%s=(\S*)" % re.escape(name), text)
    return m.group(1) if m else None


def sections(text):
    """`seq`, `array` or `none` for a readout's layout sections (those it
    names, tray left out when undefined)."""
    kinds = re.findall(r"(?:left|centerBegin|center|centerEnd|right)=(seq|array|undef|null)\(", text)
    if not kinds:
        return "none"
    if "seq" in kinds:
        return "seq"
    if all(k == "array" for k in kinds):
        return "array"
    return "mixed"


def services(events):
    """One record per service the host published, in order."""
    out = []
    cur = None
    pending_before = None
    pending_trace = []
    last_api_trace = {}
    last_api = None
    for i, (kind, ms, text) in enumerate(events):
        if kind == "trace":
            if last_api is not None:
                last_api_trace[last_api] = text
            continue
        if kind == "rig" and text.startswith("api "):
            last_api = text.split(" ")[1]
            continue
        if kind == "rig" and text.startswith("beforeApi ensureService "):
            pending_before = {"answer": text.split(" ")[2], "held": field(text, "held"), "t": ms,
                              "bar": field(text, "bar"), "barApi": field(text, "barApi"), "panel": field(text, "panel")}
            continue
        if kind == "svc" and text.startswith("created "):
            if cur is not None and cur.get("published") is None:
                cur["abandoned"] = True
            cur = {"created": ms, "object": text.split(" ", 1)[1], "before": None, "shell": None,
                   "published": None, "closed": None, "closedBy": None, "loads": [], "plans": [], "writes": [],
                   "saves": [], "warns": [], "settings": [], "firstSync": None}
            out.append(cur)
            pending_before = None
            continue
        if cur is None:
            continue
        if kind == "svc" and text.startswith("shellChanged ") and cur["shell"] is None:
            api = field(text, "shell")
            cur["before"] = pending_before
            cur["shell"] = {"t": ms, "api": api, "sections": sections(text.split(" || ")[0]),
                            "entry": field(text, "entry"), "entryMaxRecents": field(text, "entryMaxRecents"),
                            "shapes": text.split(" || ", 1)[1] if " || " in text else "",
                            "creator": last_api_trace.get(api, [])}
            if cur["shell"]["sections"] != "seq":
                cur["closed"] = ms
                cur["closedBy"] = "already" if pending_before and pending_before["answer"] == "cached" else "fresh-array"
            continue
        if kind == "rig" and text.startswith("service ") and not text.startswith("service none"):
            if cur["published"] is None and text.split(" ")[1] == cur["object"]:
                cur["published"] = ms
            continue
        if kind == "rig" and text.startswith("apiBarConfig ") and cur["shell"] and cur["closed"] is None:
            if text.split(" ")[1] == cur["shell"]["api"] and sections(text) == "array":
                cur["closed"] = ms
                trig = [t for k, _, t in events[max(0, i - 4):i] if k == "rig"]
                trig = [t for t in trig if t.startswith(("widgetRegistryChanged", "pluginsChanged", "release",
                                                         "syncPluginApis"))]
                cur["closedBy"] = trig[-1].split(" ")[0] if trig else "?"
            continue
        if kind == "svc" and text.startswith("settingsChanged ") and cur["shell"] and cur["closed"] is not None \
                and cur.get("firstSync") is None and ms >= cur["closed"]:
            cur["firstSync"] = {"t": ms, "sections": sections(text), "entry": field(text, "entry"),
                                "entryMaxRecents": field(text, "entryMaxRecents")}
            continue
        if kind == "svc" and text.startswith("stateLoad "):
            head = text.split(" || ")[0]
            cur["loads"].append({"t": ms, "onDisk": field(head, "onDisk"), "kept": field(head, "kept"),
                                 "trimMax": field(head, "trimMax"), "entry": field(head, "entry"),
                                 "sections": sections(head), "diskMarker": field(head, "diskMarker"),
                                 "shapes": text.split(" || ", 1)[1] if " || " in text else ""})
            continue
        if kind == "svc" and text.startswith("adoptActive "):
            cur["plans"].append({"t": ms, "act": field(text, "act"), "adoptUrl": field(text, "adoptUrl"),
                                 "migrating": field(text, "migrating"), "playlistSet": field(text, "playlistSet"),
                                 "refused": field(text, "refused")})
            continue
        if kind == "svc" and text.startswith("write "):
            cur["writes"].append({"t": ms, "recents": field(text, "recents"), "marker": field(text, "marker"),
                                  "sources": field(text, "sources")})
            continue
        if kind == "svc" and text.startswith("saved last "):
            cur["saves"].append({"t": ms, "recents": field(text, "recents"), "marker": field(text, "marker"),
                                 "sources": field(text, "sources")})
            continue
        if kind == "warn":
            cur["warns"].append(text)
    return out


def verdict(rec):
    """The window and what it reached, for one service record."""
    shell = rec.get("shell")
    if not shell:
        return {"window": "unread"}
    opened = shell["sections"] == "seq"
    v = {"handed": rec["before"]["answer"] if rec.get("before") else "unprobed",
         "window": "open" if opened else "closed", "defaults": shell["entry"] == "[]",
         "openMs": (rec["closed"] - shell["t"]) if opened and rec["closed"] is not None else None,
         "closedBy": rec["closedBy"] if opened else None}
    if opened and rec["closed"] is None:
        v["openMs"] = "never closed"
    load = rec["loads"][0] if rec["loads"] else None
    if load is None:
        v["load"] = "none"
    else:
        kind = load["sections"]
        v["load"] = "inside" if kind == "seq" else "after" if kind == "array" else "unknown-" + kind
        v["trim"] = "%s->%s" % (load["onDisk"], load["kept"])
        v["trimMax"] = load["trimMax"]
    plan = rec["plans"][0] if rec["plans"] else None
    v["firstPlan"] = ("%s(adoptUrl=%s,playlist=%s)" % (plan["act"], plan["adoptUrl"], plan["playlistSet"])
                      if plan else "none")
    marker = [s for s in rec["saves"] if s["marker"] == "true"]
    if marker and rec["closed"] is not None:
        v["markerSave"] = "before-close" if marker[0]["t"] < rec["closed"] else "after-close"
    elif marker:
        v["markerSave"] = "before-close"
    else:
        v["markerSave"] = "none"
    # Model.entryInputNotice's "retired" body (model/settings.mjs).
    v["refusedPlaylist"] = any(w.startswith("playlistUrl is no longer read from the bar settings") for w in rec["warns"])
    return v


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        out.append({"unparsed": line[:200]})
    except OSError:
        pass
    return out


def state_summary(path, playlist):
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError) as error:
        return "unreadable (%s)" % error
    srcs = st.get("sources") or []
    return "recents %d, marker %s, sources %d%s, activeKey %s" % (
        len(st.get("recents") or []), st.get("entryMigrated") is True, len(srcs),
        " (the playlist)" if srcs and all(s.get("url") == playlist for s in srcs) else "",
        "set" if st.get("activeKey") else "unset")


def fixture_playlist(h):
    """The playlist the fixture named, read off shell.json.start (so a start
    read again from its kept files, at another path, compares the same
    url); the start folder's play.m3u when the entry carries none."""
    try:
        with open(os.path.join(h, "shell.json.start"), encoding="utf-8") as fh:
            config = json.load(fh)
        for section in (config.get("bar") or {}).get("layout", {}).values():
            for entry in section or []:
                if isinstance(entry, dict) and entry.get("playlistUrl"):
                    return entry["playlistUrl"]
    except (OSError, ValueError, AttributeError):
        pass
    return os.path.join(h, "play.m3u")


def main(argv):
    if len(argv) != 3:
        raise SystemExit("usage: analyze.py START_FOLDER NAME")
    h, name = argv[1], argv[2]
    with open(os.path.join(h, "qs.log"), encoding="utf-8", errors="replace") as fh:
        events = parse(fh)
    playlist = fixture_playlist(h)
    recs = services(events)
    # The rig's own readings, which a start without service-log.patch
    # (RIGW_PATCH=0) still has: the probe's answer at each ensureService
    # and the shape of each published service's shell.
    for kind, ms, text in events:
        if kind == "rig" and text.startswith("beforeApi ensureService "):
            print("   rig: ensureService %s" % text.split(" ")[2])
        elif kind == "rig" and text.startswith("service ") and not text.startswith("service none"):
            print("   rig: service published, shell %s" % sections(text.replace(",", " ")))
    print("   services %d" % len(recs))
    for n, rec in enumerate(recs, 1):
        v = verdict(rec)
        sh = rec.get("shell") or {}
        before = rec.get("before") or {}
        print("   service %d: ensureService %s (held %s, bar %s, barApi %s, panel %s), creator %s" % (
            n, v.get("handed"), before.get("held"), before.get("bar"), before.get("barApi"), before.get("panel"),
            ">".join(reversed(sh.get("creator", [])[1:5])) or "-"))
        print("     onShellChanged: sections %s, entry %s, entry maxRecents %s" % (
            sh.get("sections"), sh.get("entry"), sh.get("entryMaxRecents")))
        if sh.get("sections") == "seq":
            print("     shapes: %s" % sh.get("shapes"))
        print("     window %s%s" % (v["window"], "" if v["window"] != "open" else
                                     ", closed after %s ms by %s" % (v["openMs"], v["closedBy"])))
        fs = rec.get("firstSync")
        if fs:
            print("     at the first syncPluginApis after it (+%s ms): sections %s, entry %s, entry maxRecents %s" % (
                fs["t"] - sh["t"] if sh else "?", fs["sections"], fs["entry"], fs["entryMaxRecents"]))
        for load in rec["loads"][:1]:
            print("     state load +%s ms: %s, recents %s -> %s at maxRecents %s, entry %s" % (
                load["t"] - sh["t"] if sh else "?", v["load"], load["onDisk"], load["kept"], load["trimMax"],
                load["entry"]))
        print("     first plan %s; writes %s; marker save %s" % (
            v["firstPlan"], " ".join("%s/%s/%s" % (w["recents"], w["marker"], w["sources"]) for w in rec["writes"]),
            v["markerSave"]))
        for w in rec["warns"]:
            print("     says: %s" % w[:160])
        print("   verdict %s service %d: handed %s, window %s, defaults %s, load %s, trim %s, plan %s, marker save %s, "
              "playlistUrl refused %s" % (
            name, n, v.get("handed"), v["window"], v.get("defaults"), v.get("load"), v.get("trim", "-"),
            v["firstPlan"], v["markerSave"], v["refusedPlaylist"]))
    snaps = read_jsonl(os.path.join(h, "snaps.jsonl"))
    for s in snaps[:1]:
        print("   first state.json landed: recents %s, marker %s, sources %s %s" % (
            s.get("recents"), s.get("marker"), s.get("sources"), s.get("sourceIsPlaylist")))
    print("   state.json writes landed: %d" % len(snaps))
    print("   state.json at the end: %s" % state_summary(os.path.join(h, "state.json.end"), playlist))
    ends = [r for r in read_jsonl(os.path.join(h, "rstate.jsonl")) if r.get("step") == "end"]
    for r in ends:
        st = r.get("state") or {}
        print("   service at the end: maxRecents %s, recents %s, marker %s, sources %s, sameAsCache %s, %s" % (
            st.get("maxRecents"), st.get("recents"), st.get("marker"), st.get("sources"), st.get("sameAsCache"),
            st.get("shape")))


if __name__ == "__main__":
    main(sys.argv)
