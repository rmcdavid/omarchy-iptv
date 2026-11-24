#!/usr/bin/env python3
"""scripts/dev-harness/spikes/codebehind-reload/analyze.py -- one arm's readout.

  analyze.py ARM_DIR ARM

Reads what run.sh kept for one arm (marks.jsonl, qs.log, steps.log,
watch.log) and prints, per step, what every running object says it is and
what the shell logged since the step before; then the update's write order
(the working tree's creates and closes, the .git folder left out) laid beside
the shell's own reload events on the same millisecond clock.
"""
import collections
import json
import re
import sys

PLUGIN_FILES = ("Service.qml", "Service-pip.js", "Service-player.js", "Service-rewind.js",
                "Service-sources.js", "Guide.qml", "BarWidget.qml", "Model.mjs", "manifest.json")
CODE_BEHINDS = PLUGIN_FILES[1:5]
NOTABLE = re.compile(r"TypeError|ReferenceError|SyntaxError|is not a function|unavailable|case mismatch|"
                     r"Error|error|WARN|warn|failed|received signal", re.I)


ANSI = re.compile(r"\x1b\[[0-9;]*m")


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
        if what.startswith(("control", "loaded", "not ready", "no scan", "update rc")):
            print("  note: %s" % what)
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
    rel = lambda p: p.split("/io.github.rmcdavid.iptv/", 1)[-1]
    closes = {}
    creates = {}
    for t, kind, path in tree:
        name = rel(path)
        if "CLOSE_WRITE" in kind:
            closes.setdefault(name, t)
        if "CREATE" in kind:
            creates.setdefault(name, t)
    print("  write order: %d working-tree events in %.1f ms (merge %.1f ms)" % (
        len(tree), (tree[-1][0] - tree[0][0]) if tree else 0, m1 - m0))
    order = sorted(closes, key=closes.get)
    print("    closed, in order: %s" % ", ".join(n for n in order if n in PLUGIN_FILES or n.startswith("model/build")))
    svc = creates.get("Service.qml")
    late = [n for n in CODE_BEHINDS if n in closes and svc is not None and closes[n] > svc]
    print("    Service.qml created before %s closed" % (", ".join(late) if late else "no code-behind"))
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


if __name__ == "__main__":
    main(sys.argv)
