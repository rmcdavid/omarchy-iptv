"""CLAUDE.md rule 11 for lane 2: prove each assertion can go red.

Every scenario lane 2 adds is new code, so there is no "before" to run
against. The rule's other half applies: break one decision deliberately in
the THROWAWAY tree and show which checks notice. A scenario that survives
every mutation is a scenario asserting nothing.

Nothing in the repo is touched. Each case rebuilds the tree from scratch,
applies one edit, and re-runs only the scenarios that edit can reach.

The last case is not a mutation of ours: it is the remedy the design pass
proposed for the credential leak, applied verbatim. It is here because the
prototype reported "19 checks, 0 failures" over it while it silently
replaced the user's stored credentials. If this harness cannot tell that
apart from a fix, it has the same hole.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The generated tree is a BUILD ARTIFACT, not source: it holds a copy of the
# host UI kit and a transformed copy of Guide.qml, both regenerated on every
# run. It must not land inside the repo, and it must not be shared between
# concurrent runs -- a shared directory written by two lanes at once already
# produced one reading that was green only because a mutation had been
# overwritten. Override with A11Y_TREE when you want to keep one to inspect.
TREE = os.environ.get("A11Y_TREE") or os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "omarchy-iptv-a11y-tree")
BASE_JSON = os.path.join(HERE, "lane2_baseline.json")
CASE_JSON = os.path.join(HERE, "lane2_case.json")

# (label, file in tree/, old, new, scenario groups to re-run)
MUTATIONS = [
    ("bar: Accessible.name no longer comes from Model.barAccessibleName",
     "BarWidget.qml",
     "Accessible.name: Model.barAccessibleName({ playing: root.playing, name: root.nowPlayingName,\n"
     "                                             chno: root.nowPlayingChno, error: root.hasError })",
     'Accessible.name: "IPTV"',
     ["bar"]),

    ("bar: Accessible.role Button -> StaticText",
     "BarWidget.qml",
     "Accessible.role: Accessible.Button",
     "Accessible.role: Accessible.StaticText",
     ["bar"]),

    ("bar: idle and error collapse to one announcement (colour-only state)",
     "Model.js",
     'if (o.error) return "IPTV, playlist error"',
     'if (o.error) return "IPTV, idle"',
     ["bar"]),

    ("form: the form Dialog loses its name",
     "GuideProbe.qml",
     "Accessible.name: root.formAccessibleName",
     'Accessible.name: ""',
     ["firstrun", "xtream"]),

    ("form: the field labels go away",
     "GuideProbe.qml",
     "Accessible.name: root.fieldAccessibleName(fieldRow.fieldId)",
     'Accessible.name: ""',
     ["firstrun", "xtream"]),

    ("banner: Accessible.role AlertMessage -> StaticText",
     "GuideProbe.qml",
     "Accessible.role: Accessible.AlertMessage\n          Accessible.name: root.bannerText",
     "Accessible.role: Accessible.StaticText\n          Accessible.name: root.bannerText",
     ["banner"]),

    ("banner: the banner says nothing",
     "GuideProbe.qml",
     "Accessible.name: root.bannerText",
     'Accessible.name: ""',
     ["banner"]),

    ("search: the field reads back the placeholder while a query is live",
     "GuideProbe.qml",
     'text: root.query !== "" ? root.query : root.copy.searchPlaceholder',
     "text: root.copy.searchPlaceholder",
     ["query"]),

    ("search: UX 7.1's description = current query is dropped",
     "GuideProbe.qml",
     "Accessible.description: root.query",
     'Accessible.description: ""',
     ["query"]),

    ("list: the channel list role List -> Grouping",
     "GuideProbe.qml",
     "Accessible.role: Accessible.List\n                Accessible.name: root.copy.accessibleChannels",
     "Accessible.role: Accessible.Grouping\n                Accessible.name: root.copy.accessibleChannels",
     ["scale", "query"]),

    ("rows: 'row N of M' leaves the row name (the only position an AT gets)",
     "Model.js",
     'out += ", row " + formatCount(at + 1) + " of " + formatCount(total)',
     'out += ""',
     ["scale", "query"]),

    ("bar: the error glyph becomes the idle glyph (R7 codepoints collapse)",
     "Model.js",
     "if (o.error) return GLYPHS.tvOff",
     "if (o.error) return GLYPHS.tv",
     ["bar"]),

    ("bar: the Nerd Font glyph is handed to the reader as the name",
     "BarWidget.qml",
     "Accessible.name: Model.barAccessibleName({ playing: root.playing, name: root.nowPlayingName,\n"
     "                                             chno: root.nowPlayingChno, error: root.hasError })",
     "Accessible.name: root.glyph",
     ["bar"]),

    ("first run: the submit verb stops being 'Load'",
     "GuideProbe.qml",
     "text: root.firstRunHead ? root.copy.buttonLoad : root.copy.buttonSave",
     "text: root.copy.buttonSave",
     ["firstrun"]),

    ("footer: the status line stops being announced",
     "GuideProbe.qml",
     "Accessible.name: root.footerStatusText",
     'Accessible.name: ""',
     ["banner"]),

    ("banner: the same alert is announced when nothing is wrong",
     "GuideProbe.qml",
     "Accessible.name: root.bannerText",
     'Accessible.name: "Playlist refresh failed (connection refused) '
     '\u00b7 showing cached copy from 8 Sep 14:02 \u00b7 r retry"',
     ["banner"]),

    ("banner: a saved source URL rides along on the failure text",
     "GuideProbe.qml",
     "Accessible.name: root.bannerText",
     "Accessible.name: root.bannerText + \" \" + (root.sourceList.length > 0 "
     "? String(root.sourceList[0].playlistUrl) : \"\")",
     ["banner"]),

    ("search: the search line loses its name",
     "GuideProbe.qml",
     "Accessible.name: root.copy.accessibleSearch",
     'Accessible.name: ""',
     ["query"]),

    ("groups: the group entry stops counting its channels",
     "GuideProbe.qml",
     'Accessible.name: isHeader ? label : label + ", " + Model.pluralChannels(count)',
     "Accessible.name: label",
     ["scale"]),

    ("password: its label is replaced by its value",
     "GuideProbe.qml",
     "? root.fieldLabelText(fieldRow.fieldId)",
     "? root.formValue(fieldRow.fieldId)",
     ["xtream"]),

    ("first run: the empty field reads back its placeholder as if it were content",
     "GuideProbe.qml",
     "text: root.fieldDisplay(fieldRow.fieldId)",
     "text: root.fieldPlaceholder(fieldRow.fieldId)",
     ["firstrun"]),

    ("footer: the stale cache stops being said in words (UX 7.2)",
     "Model.js",
     'out += SEP + (o.stale ? "cached " + str(o.lastUpdated) + SEP + "offline" : "updated " + str(o.lastUpdated))',
     'out += SEP + "updated " + str(o.lastUpdated)',
     ["banner"]),

    ("THE PROPOSED CREDENTIAL FIX, verbatim: rebind the field to the mask",
     "GuideProbe.qml",
     "text: root.fieldDisplay(fieldRow.fieldId)",
     "text: Model.maskUrl(root.formValue(fieldRow.fieldId))",
     ["xtream"]),
]


def run_check(groups, out_json, keep_tree):
    env = dict(os.environ)
    env["LANE2_JSON"] = out_json
    if keep_tree:
        env["KEEP_TREE"] = "1"
    else:
        env.pop("KEEP_TREE", None)
    subprocess.run([sys.executable, os.path.join(HERE, "check_bus.py")] + groups,
                   env=env, capture_output=True, text=True, timeout=1200)
    return {r["id"]: r["ok"] for r in json.load(open(out_json))}


def build_tree():
    for script in ("make_tree.py", "make_hosts.py"):
        subprocess.check_call([sys.executable, os.path.join(HERE, script)],
                              stdout=subprocess.DEVNULL)


def main():
    only = sys.argv[1:]
    print("=== baseline on shipping code (all scenarios)")
    build_tree()
    base = run_check([], BASE_JSON, keep_tree=True)
    base_fail = sorted(k for k, ok in base.items() if not ok)
    print("    %d checks, %d failures: %s" % (len(base), len(base_fail), base_fail))
    print()

    for label, filename, old, new, groups in MUTATIONS:
        if only and not any(o in label for o in only):
            continue
        print("=== %s" % label)
        build_tree()
        path = os.path.join(TREE, filename)
        text = open(path).read()
        if old not in text:
            print("    SKIPPED: pattern not found in %s" % filename)
            continue
        count = text.count(old)
        open(path, "w").write(text.replace(old, new))
        got = run_check(groups, CASE_JSON, keep_tree=True)
        newly_red = sorted(k for k, ok in got.items()
                           if not ok and base.get(k, True))
        newly_green = sorted(k for k, ok in got.items()
                             if ok and base.get(k) is False)
        print("    mutated %s (%d site%s), re-ran %s"
              % (filename, count, "" if count == 1 else "s", groups))
        print("    NEWLY RED:   %s" % (newly_red or "NOTHING -- this mutation is invisible"))
        if newly_green:
            print("    newly green: %s" % newly_green)
        print()

    build_tree()
    print("tree rebuilt clean")


if __name__ == "__main__":
    sys.exit(main())
