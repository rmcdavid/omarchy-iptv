#!/usr/bin/env python3
"""scripts/dev-harness/spikes/codebehind-reload/analyze.py -- one arm's readout.

  analyze.py ARM_DIR ARM

Reads what run.sh kept for one arm (marks.jsonl, qs.log, steps.log,
watch.log, open.log, cache.txt) and prints, per step, what every running
object says it is and what the shell logged since the step before; then the
cold start's reads (open.log: the first time the shell opened each plugin
file); then the update's write order (the working tree's unlinks, creates
and closes, the .git folder left out) with the moments a cold load could
read (h0, h1, h4), laid beside the shell's own reload events on the same
millisecond clock; then, for a race arm, each marked file's read, git's
write and the cache's save in one line; then what the QML disk cache held
at each step it was read (cache.py).
"""
import collections
import json
import re
import sys

PLUGIN_FILES = ("Service.qml", "Service-pip.js", "Service-player.js", "Service-rewind.js",
                "Service-sources.js", "Guide.qml", "BarWidget.qml", "Model.mjs", "manifest.json")
CODE_BEHINDS = PLUGIN_FILES[1:5]
READ_FILES = PLUGIN_FILES + ("model/build.mjs",)
PLUGIN_DIR = "/io.github.rmcdavid.iptv/"
# D-REL-16: the version each build's cut stamps on the files it changes
# (candidates.py's bump): a marked file's stamp names the build its mark does.
MARK_VERSIONS = {"C1": "0.99.0", "C2": "0.99.1", "C3": "0.99.2"}
NOTABLE = re.compile(r"TypeError|ReferenceError|SyntaxError|is not a function|unavailable|case mismatch|"
                     r"Error|error|WARN|warn|failed|received signal", re.I)


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def rel(path):
    return path.split(PLUGIN_DIR, 1)[-1]


def watch_events(path):
    """(ms, events, path) of one watch.py log, the .git folder left out."""
    out = []
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return out
    for line in lines:
        t, _, rest = line.strip().partition(" ")
        kind, _, p = rest.partition("|")
        if "/.git/" in p or p.endswith("/.git") or PLUGIN_DIR not in p + "/":
            continue
        out.append((float(t), kind, p))
    return out


def shell_reads(d):
    """The first time each plugin file was opened by anything but git: an open
    within 2 ms after git created the same path is git's own write."""
    created = collections.defaultdict(list)
    for t, kind, path in watch_events(d + "/watch.log"):
        if "CREATE" in kind:
            created[rel(path)].append(t)
    first, later = {}, collections.defaultdict(list)
    for t, kind, path in watch_events(d + "/open.log"):
        name = rel(path)
        if "OPEN" not in kind or "ISDIR" in kind:
            continue
        if any(0 <= t - c <= 2.0 for c in created.get(name, ())):
            continue
        if name in first:
            later[name].append(t)
        else:
            first[name] = t
    return first, later


def tidy(line, d):
    """A log line without its colour codes, the plugin's folder written
    <plugin> and the arm's <arm>."""
    text = ANSI.sub("", line).strip()
    return text.replace(d + "/home/.config/omarchy/plugins/io.github.rmcdavid.iptv", "<plugin>").replace(d, "<arm>")


def short(obj):
    if not isinstance(obj, str):
        return str(obj)
    m = re.match(r"([A-Za-z_]+?(?:_QMLTYPE_\d+)?)\(", obj)
    return m.group(1) if m else obj


def main(argv):
    d, arm = argv[1], argv[2]
    marks = [json.loads(line) for line in open(d + "/marks.jsonl", encoding="utf-8") if line.strip()]
    log = open(d + "/qs.log", encoding="utf-8", errors="replace").read().splitlines()
    prev = 0
    for m in marks:
        k = m["marks"] if isinstance(m["marks"], dict) else {"raw": m["marks"]}
        st = k.get("status")
        if isinstance(st, dict):
            b = st.get("build") or {}
            status = "%s/%s ch, build running %s onDisk %s stale %s" % (
                st.get("status"), st.get("channels"), b.get("running"), b.get("onDisk"), b.get("stale"))
        else:
            status = str(st)
        print("  [%s]" % m["step"])
        print("    service  %s | %s" % (short(k.get("serviceObject")), k.get("service", k.get("raw"))))
        print("    status   %s; favorites %s; refreshMinutes %s; installed %s; enabled %s" % (
            status, k.get("favorites"), k.get("refreshMinutes"), k.get("installed"), k.get("enabled")))
        print("    guide    %s | %s; footer %r" % (short(k.get("guideObject")), k.get("guide"),
                                                   k.get("guideFooter")))
        print("    bar      %s | %s; bar.service is the service: %s" % (
            short(k.get("barObject")), k.get("bar"), k.get("barServiceIsService")))
        for line in stamp_lines(k):
            print("    " + line)
        lines = [l for l in log[prev:m["logLine"]] if "RIG-EVENT" not in l and NOTABLE.search(l)]
        counts = collections.Counter(tidy(l, d)[:300] for l in lines)
        print("    log      %d notable line(s) since the step before" % len(lines))
        for text, n in counts.most_common(12):
            print("      %3dx %s" % (n, text))
        prev = m["logLine"]
    try:
        shell = json.load(open(d + "/shell.json.end", encoding="utf-8"))
        entry = [e for e in shell["bar"]["layout"].get("right", []) if e.get("id") == "io.github.rmcdavid.iptv"]
        print("  at the end: bar entry %s" % (json.dumps(entry[0], sort_keys=True) if entry else "none"))
    except (OSError, ValueError, KeyError) as error:
        print("  at the end: shell.json unreadable (%s)" % error)
    try:
        state = json.load(open(d + "/state.json.end", encoding="utf-8"))
        print("  at the end: state favorites %s, sources %s" % (
            state.get("favorites"), [x.get("label") for x in state.get("sources", [])]))
    except (OSError, ValueError) as error:
        print("  at the end: state.json unreadable (%s)" % error)
    steps = {}
    for line in open(d + "/steps.log", encoding="utf-8"):
        t, _, what = line.strip().partition(" ")
        steps.setdefault(what, float(t))
        if what.startswith(("control", "loaded", "not ready", "no scan", "update rc", "half tree", "race armed",
                            "cache folder", "merge rc")):
            print("  note: %s" % what)
    reads(d, steps)
    write_order(d, steps, log)
    race(d, steps)
    cache(d)


def file_marks(k):
    """{file: build} the marks name: Service.qml's reloadMarks string ("C1
    Service.qml, C1 Service-pip.js, ..."), the guide's and the bar's mark;
    None for a file with none (C0's, or a read that threw)."""
    out = {}
    svc = k.get("service")
    if isinstance(svc, str):
        for part in svc.split(", "):
            m = re.match(r"(C[0-9]) (\S+)$", part.strip())
            if m:
                out[m.group(2)] = m.group(1)
    for key, name in (("guide", "Guide.qml"), ("bar", "BarWidget.qml")):
        m = re.match(r"(C[0-9]) ", str(k.get(key) or ""))
        out.setdefault(name, m.group(1) if m else None)
    for name in ("Service.qml",) + CODE_BEHINDS:
        out.setdefault(name, None)
    return out


def stamp_lines(k):
    """D-REL-16: the `build` reply's verdict beside the marks -- its notice,
    `mixed` and `stamps` -- what the guide's footer and the bar's tooltip and
    name say, and whether the stamps agree with the marks: a marked file's
    stamp is the version its mark's build was cut at (MARK_VERSIONS), and an
    unmarked one (C0's) has none to give."""
    b = k.get("build")
    if not isinstance(b, dict):
        return ["build    %s" % (b if b is not None else "no build reply (a rig from before the stamps)")]
    stamps = b.get("stamps") if isinstance(b.get("stamps"), dict) else {}
    lines = ["build    notice %r; mixed %s; running %s onDisk %s loadedDisk %s; %d stamp(s)" % (
        b.get("notice"), b.get("mixed"), b.get("running"), b.get("onDisk"), b.get("loadedDisk"), len(stamps))]
    by = collections.defaultdict(list)
    for name in sorted(stamps):
        by[stamps[name]].append(name)
    for version in sorted(by):
        lines.append("  stamps %s: %s" % (version, ", ".join(by[version])))
    lines.append("views    guide notice %r stamp %r; bar notice %r stamp %r" % (
        k.get("guideNotice"), k.get("guideStamp"), k.get("barNotice"), k.get("barStamp")))
    lines.append("  bar tooltip %r" % (k.get("barTooltip"),))
    lines.append("  bar name    %r" % (k.get("barName"),))
    marks = file_marks(k)
    off = []
    for name, build in sorted(marks.items()):
        stamp = stamps.get(name)
        want = MARK_VERSIONS.get(build) if build else None
        if build is None and stamp not in (None, "?"):
            off.append("%s unmarked but stamped %s" % (name, stamp))
        elif build is not None and stamp is None:
            # A marked file the reply does not stamp: a view that never
            # reported (the l3-bar-no-report patch's shape), which a check
            # that skipped it read as agreeing (the gate recheck of 1c64c77).
            off.append("%s marked %s (%s) but not stamped" % (name, build, want))
        elif build is not None and stamp != want:
            off.append("%s marked %s (%s) but stamped %s" % (name, build, want, stamp))
    builds = sorted(set(v for v in marks.values() if v)) + (["C0"] if any(v is None for v in marks.values()) else [])
    mixed_marks = len(builds) > 1
    # A mix the marks see must read "cache"; one build may read anything
    # (a whole build loaded behind the disk reads "cache" too).
    agree = not off and (not mixed_marks or b.get("notice") == "cache")
    lines.append("agree    marks name %s; stamps %s; %s" % (
        "one build, " + builds[0] if len(builds) == 1 else "a mix of " + ", ".join(builds),
        "agree with every mark" if not off else "disagree: " + "; ".join(off),
        "the notice fits the marks" if agree else "THE NOTICE DOES NOT FIT THE MARKS (a finding)"))
    return lines


def write_order(d, steps, log):
    if "merge start" not in steps or "merge end" not in steps:
        print("  write order: no merge recorded")
        return
    m0, m1 = steps["merge start"], steps["merge end"]
    events = []
    for line in open(d + "/watch.log", encoding="utf-8"):
        t, _, rest = line.strip().partition(" ")
        kind, _, path = rest.partition("|")
        if "/.git/" in path or path.endswith("/.git"):
            continue
        events.append((float(t), kind, path))
    tree = [e for e in events if m0 - 5 <= e[0] <= m1 + 5]
    closes = {}
    creates = {}
    deletes = {}
    for t, kind, path in tree:
        name = rel(path)
        if "CLOSE_WRITE" in kind:
            closes.setdefault(name, t)
        if "CREATE" in kind:
            creates.setdefault(name, t)
        if "DELETE" in kind or "MOVED_FROM" in kind:
            deletes.setdefault(name, t)
    print("  write order: %d working-tree events in %.1f ms (merge %.1f ms)" % (
        len(tree), (tree[-1][0] - tree[0][0]) if tree else 0, m1 - m0))
    order = sorted(closes, key=closes.get)
    print("    closed, in order: %s" % ", ".join(n for n in order if n in PLUGIN_FILES or n.startswith("model/build")))
    for name in [n for n in READ_FILES if n in closes]:
        print("      %-20s unlinked %s, created %s, closed %+.1f ms after the merge started" % (
            name, "%+.1f" % (deletes[name] - m0) if name in deletes else "never",
            "%+.1f" % (creates[name] - m0) if name in creates else "never", closes[name] - m0))
    # The moments a cold load could read (docs/SERVICE-SPLIT.md's table):
    # h0, the old Service.qml unlinked and the new one not yet created; h1,
    # every changed code-behind complete and the old Service.qml not yet
    # unlinked; h4, the new Service.qml complete while a changed code-behind
    # is unlinked or still being written.
    svc_gone, svc_new, svc_done = deletes.get("Service.qml"), creates.get("Service.qml"), closes.get("Service.qml")
    changed_cb = [n for n in CODE_BEHINDS if n in closes]
    if svc_gone is not None and svc_new is not None:
        print("    h0: Service.qml absent %.1f ms (unlinked %+.1f, created %+.1f); every changed file unlinked "
              "before the first create: %s" % (
                  svc_new - svc_gone, svc_gone - m0, svc_new - m0,
                  "yes" if deletes and creates and max(deletes.values()) <= min(creates.values()) else "no"))
    if changed_cb and svc_done is not None:
        before = svc_gone if svc_gone is not None else (svc_new if svc_new is not None else svc_done)
        h1 = all(closes[n] <= before for n in changed_cb)
        print("    h1: every changed code-behind closed before the old Service.qml went: %s" % ("yes" if h1 else "no"))
        open_cb = [n for n in changed_cb if closes[n] > svc_done]
        print("    h4: the new Service.qml complete while %s" % (
            "%s not yet closed" % ", ".join(open_cb) if open_cb else "every changed code-behind was already closed: no"))
    gaps = [b[0] - a[0] for a, b in zip(tree, tree[1:])]
    print("    largest gap between two working-tree events: %.1f ms (the host's debounce is 150 ms)" % (max(gaps) if gaps else 0))
    last = tree[-1][0] if tree else m1
    rig = []
    for line in log:
        mm = re.search(r"RIG-EVENT (\d+) (.*)$", line)
        if mm and float(mm.group(1)) >= m0:
            rig.append((float(mm.group(1)), mm.group(2)))
    changed = [t for t, w in rig if w.startswith("localPluginChanged")]
    if changed:
        print("    localPluginChanged x%d, %+.1f to %+.1f ms after the last write" % (
            len(changed), changed[0] - last, changed[-1] - last))
    for t, what in [r for r in rig if not r[1].startswith("localPluginChanged")][:16]:
        print("    %+8.1f ms after the last write: %s" % (t - last, what[:120]))
    early = [w for t, w in rig if t < last and not w.startswith("localPluginChanged")]
    print("    a reload or load before the last write: %s" % ("yes: " + "; ".join(early) if early else "no"))


def saves(d, step):
    """{file: ms} of the cache files cache.py read at STEP (their mtimes)."""
    out, inside = {}, False
    try:
        lines = open(d + "/cache.txt", encoding="utf-8").read().splitlines()
    except OSError:
        return out
    for line in lines:
        if line.startswith("  [cache "):
            inside = line.strip() == "[cache %s]" % step
            continue
        parts = line.split()
        if inside and len(parts) > 2 and parts[1] == "saved":
            out[parts[0]] = float(parts[2])
    return out


def reads(d, steps):
    """The cold start's reads: the first time the shell opened each plugin
    file, from the moment run.sh started it and from its first open of the
    plugin's folder."""
    first, later = shell_reads(d)
    start = steps.get("shell starting")
    folder = None
    for t, kind, path in watch_events(d + "/open.log"):
        if "OPEN" in kind and "ISDIR" in kind and path.rstrip("/").endswith(PLUGIN_DIR.rstrip("/")):
            if start is None or t >= start:
                folder = t
                break
    if not first:
        print("  cold-start reads: no open watch kept")
        return
    base = folder if folder is not None else min(first.values())
    print("  cold-start reads (the shell's first open of each file; +ms from its first open of the plugin folder%s):" % (
        ", which came %+.1f ms after run.sh started it" % (folder - start) if folder is not None and start else ""))
    saved = saves(d, "start") or saves(d, "race")
    for name in sorted((n for n in READ_FILES if n in first), key=first.get):
        again = later.get(name, [])
        print("    %-20s %+9.1f ms%s%s" % (
            name, first[name] - base,
            ("; opened again %d time(s), first %+.1f" % (len(again), again[0] - base)) if again else "",
            ("; its cache file saved %+.1f" % (saved[name] - base)) if name in saved else "; no cache file"))
    cbs = [first[n] for n in CODE_BEHINDS if n in first]
    if "Service.qml" in first and cbs:
        print("    from the first read of Service.qml to the first of a code-behind: %.1f ms, to the last: %.1f ms" % (
            min(cbs) - first["Service.qml"], max(cbs) - first["Service.qml"]))


def race(d, steps):
    """A race arm: when the trigger opened, when the merge ran, and for each
    marked file its read by the shell, git's write and its read after."""
    if "race open" not in steps:
        return
    t0 = steps["race open"]
    print("  race: the trigger's open at 0; merge %+.1f to %+.1f ms" % (
        steps.get("merge start", t0) - t0, steps.get("merge end", t0) - t0))
    first, later = shell_reads(d)
    closes = {}
    for t, kind, path in watch_events(d + "/watch.log"):
        if "CLOSE_WRITE" in kind:
            closes.setdefault(rel(path), t)
    saved = saves(d, "race")
    for name in READ_FILES:
        if name not in first and name not in closes:
            continue
        reads_at = [first[name]] + later.get(name, []) if name in first else []
        before = [t for t in reads_at if name not in closes or t < closes[name]]
        after = [t for t in reads_at if name in closes and t >= closes[name]]
        print("    %-20s read %s; git closed %s; read after it %s; cache saved %s" % (
            name, ("%+.1f" % (before[0] - t0)) if before else "never before the write",
            ("%+.1f" % (closes[name] - t0)) if name in closes else "unchanged",
            ("%+.1f" % (after[0] - t0)) if after else "never",
            ("%+.1f" % (saved[name] - t0)) if name in saved else "no file"))


def cache(d):
    try:
        text = open(d + "/cache.txt", encoding="utf-8").read().rstrip("\n")
    except OSError:
        return
    if text:
        print("  the QML disk cache (cache.py):")
        print(text)



if __name__ == "__main__":
    # The readout is ASCII, a guide footer's middle dot written as an escape,
    # so a RESULT file kept beside this rig passes the gate's ASCII scan.
    sys.stdout.reconfigure(errors="backslashreplace", encoding="ascii")
    main(sys.argv)
