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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import model_files  # noqa: E402  the model's files, read from Model.mjs (D-REL-5)

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
#
# Round 4e (I7, the lead's call under the owner's standing authority of
# 2026-11-09): an anchor that matches nothing is a mutation nobody ran, and
# three did for weeks while every run reported them only as SKIPPED -- the
# two bar mutants since the bar's call grew `paused` and `behindS` over three
# lines, and the round-4b label mutant since round 4d ended labelSinkText in
# two lines. Both bar mutants and that one are re-anchored on today's text,
# and main() now exits non-zero when any mutation is SKIPPED or invisible.
MUTATIONS = [
    ("bar: Accessible.name no longer comes from Model.barAccessibleName",
     "BarWidget.qml",
     "Accessible.name: Model.barAccessibleName({ playing: root.playing, name: root.nowPlayingName,\n"
     "                                             chno: root.nowPlayingChno, error: root.hasError, paused: root.paused,\n"
     "                                             behindS: root.behindLiveS })",
     'Accessible.name: "IPTV"',
     ["bar"]),

    ("bar: Accessible.role Button -> StaticText",
     "BarWidget.qml",
     "Accessible.role: Accessible.Button",
     "Accessible.role: Accessible.StaticText",
     ["bar"]),

    ("bar: idle and error collapse to one announcement (colour-only state)",
     "Model.mjs",
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
     "Model.mjs",
     'out += ", row " + formatCount(at + 1) + " of " + formatCount(total)',
     'out += ""',
     ["scale", "query"]),

    ("bar: the error glyph becomes the idle glyph (R7 codepoints collapse)",
     "Model.mjs",
     "if (o.error) return GLYPHS.tvOff",
     "if (o.error) return GLYPHS.tv",
     ["bar"]),

    ("bar: the Nerd Font glyph is handed to the reader as the name",
     "BarWidget.qml",
     "Accessible.name: Model.barAccessibleName({ playing: root.playing, name: root.nowPlayingName,\n"
     "                                             chno: root.nowPlayingChno, error: root.hasError, paused: root.paused,\n"
     "                                             behindS: root.behindLiveS })",
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

    # Round 4d (F11): the anchor followed the group entry's name into
    # Model.scopeEntryAccessibleName (M3-01); the old text was skipped as
    # "pattern not found" on every run since.
    ("groups: the group entry stops counting its channels",
     "GuideProbe.qml",
     "Accessible.name: Model.scopeEntryAccessibleName({ label: label, count: count, kind: kind })",
     "Accessible.name: label",
     ["scale"]),

    ("password: its label is replaced by its value",
     "GuideProbe.qml",
     "Accessible.description: Model.fieldAccessibleDescription(fieldRow.fieldId, root.fieldLabelText(fieldRow.fieldId))",
     'Accessible.description: fieldRow.fieldId === "password" ? root.formValue(fieldRow.fieldId) : ""',
     ["xtream"]),

    # D-SINK-97 and D-SINK-98: the Sources scenarios.
    ("D-SINK-97: an address field's Description is its visual mask again",
     "GuideProbe.qml",
     "Accessible.description: Model.fieldAccessibleDescription(fieldRow.fieldId, root.fieldLabelText(fieldRow.fieldId))",
     'Accessible.description: fieldRow.fieldId === "password" ? root.fieldLabelText(fieldRow.fieldId) : '
     '(fieldRow.maskable ? Model.maskUrl(root.formValue(fieldRow.fieldId)) : "")',
     ["sources"]),

    ("D-SINK-97: an address field's Value is the visual mask again",
     "Model.mjs",
     "  if (ADDRESS_FIELDS.indexOf(id) !== -1) return addressAccessibleValue(value)\n",
     "  if (ADDRESS_FIELDS.indexOf(id) !== -1 && /^[A-Za-z][A-Za-z0-9+.-]*:\\/\\//.test(value)) return maskUrl(value)\n"
     "  if (ADDRESS_FIELDS.indexOf(id) !== -1) return addressAccessibleValue(value)\n",
     ["sources"]),

    ("D-SINK-98: the label field publishes the label raw",
     "Model.mjs",
     '  if (id === "label") return labelHeldAfter(f.labelHeld, value) ? accessibleStars(value) : labelSinkText(value)\n',
     '  if (id === "label") return value\n',
     ["sources"]),

    ("D-SINK-98: the Sources row draws and names the label raw",
     "GuideProbe.qml",
     "srow.source ? Model.labelSinkText(String(srow.source.label))",
     "srow.source ? String(srow.source.label)",
     ["sources"]),

    ("D-SINK-98: the row's accessible name carries the raw label",
     "Model.mjs",
     'var out = labelSinkText(str(v.label)) + ", " + str(v.host)',
     'var out = str(v.label) + ", " + str(v.host)',
     ["sources"]),

    ("D-SINK-98: the remove dialog quotes the raw label",
     "Model.mjs",
     "var quoted = QUOTE_OPEN + labelSinkText(str(label)) + QUOTE_CLOSE",
     "var quoted = QUOTE_OPEN + str(label) + QUOTE_CLOSE",
     ["sources"]),

    # Round 4b.
    ("D-A11Y-12: a hidden row's Edit and Remove buttons stay on the bus",
     "GuideProbe.qml",
     "                        Accessible.ignored: !sactions.visible\n",
     "",
     ["sources"]),

    ("D-SINK-98 (round 4b): the label reads through sinkText again, so a label without `://` passes raw",
     "Model.mjs",
     "  if (hosts.length > 0) return hosts.join(\" \")\n  return sinkText(s) !== s ? HOST_WITHHELD : s\n",
     "  return sinkText(s)\n",
     ["sources"]),

    ("D-SINK-98 (round 4b): the Sources row draws and names the label through sinkText",
     "GuideProbe.qml",
     "srow.source ? Model.labelSinkText(String(srow.source.label))",
     "srow.source ? Model.sinkText(String(srow.source.label))",
     ["sources"]),

    ("D-SINK-97 (round 4b): a bare local path is published as typed again",
     "Model.mjs",
     "  if (p === null) return accessibleStars(s)\n",
     "  if (p === null) return /^(\\/(?!\\/)|~\\/)[^?#@]*$/.test(s) ? s : accessibleStars(s)\n",
     ["sources"]),

    ("D-SINK-99: the fetching line names the probe host as the form holds it",
     "GuideProbe.qml",
     "if (root.formProbing && root.form) return Model.formFetchingLine(root.form)",
     "if (root.formProbing && root.form) return Model.fetchingLine(root.form.probeHost, root.form.probeKind)",
     ["sources"]),

    ("D-SINK-99: the probe's failure line names the probe host as the form holds it",
     "GuideProbe.qml",
     "message: Model.formProbeFailureLine(root.form, r.reason, String(r.host || root.form.probeHost), String(r.code || \"\"))",
     "message: Model.probeFailureLine(r.reason, String(r.host || root.form.probeHost), root.form.probeKind, String(r.code || \"\"))",
     ["sources"]),

    ("D-SINK-99: the label placeholder names the withheld host's derived label",
     "Model.mjs",
     "  return derived !== \"\" && formHostWithheld(f) ? HOST_WITHHELD : derived\n",
     "  return derived\n",
     ["sources"]),

    # Round 4c.
    ("D-SINK-98 (round 4c, E1): the label field ignores its hold",
     "Model.mjs",
     '  if (id === "label") return labelHeldAfter(f.labelHeld, value) ? accessibleStars(value) : labelSinkText(value)\n',
     '  if (id === "label") return labelSinkText(value)\n',
     ["sources"]),

    ("D-SINK-98 (round 4c, E2): labelSinkText cuts tokens at JS \\s again",
     "Model.mjs",
     '  var tokens = s.split(" ")\n  var hosts = []\n',
     '  var tokens = s.split(/\\s+/)\n  var hosts = []\n',
     ["sources"]),

    ("D-SINK-99 (round 4c, E4): the form withholds its lines' host for urlHostWithheld alone",
     "Model.mjs",
     "  return urlHostWithheld(text) || addressAtAfterAuthority(text)\n",
     "  return urlHostWithheld(text)\n",
     ["sources"]),

    ("D-A11Y-12 (round 4c, E3): a row's buttons leave the bus only when the row is not the cursor's (the review's mutant)",
     "GuideProbe.qml",
     "                        Accessible.ignored: !sactions.visible\n",
     "                        Accessible.ignored: !srow.hasCursor\n",
     ["sources"]),

    ("D-A11Y-12 (round 4c, E6): the closed remove dialog stays on the bus",
     "GuideProbe.qml",
     "          Accessible.ignored: !visible\n          Accessible.role: Accessible.Dialog\n          Accessible.name: root.confirmMessage\n",
     "          Accessible.role: Accessible.Dialog\n          Accessible.name: root.confirmMessage\n",
     ["sources"]),

    ("D-A11Y-12 (round 4c, E6): the closed form's Cancel button stays on the bus",
     "GuideProbe.qml",
     "                Accessible.ignored: !visible\n                Accessible.role: Accessible.Button\n                Accessible.name: root.copy.buttonCancel\n",
     "                Accessible.role: Accessible.Button\n                Accessible.name: root.copy.buttonCancel\n",
     ["sources"]),

    ("D-A11Y-12 (round 4c, E6): the Sources rows stay on the bus outside the Sources view",
     "GuideProbe.qml",
     "                Accessible.ignored: !visible\n                Accessible.role: Accessible.ListItem\n                Accessible.name: srow.source ? Model.sourceAccessibleName(srow.source) : srow.label\n",
     "                Accessible.role: Accessible.ListItem\n                Accessible.name: srow.source ? Model.sourceAccessibleName(srow.source) : srow.label\n",
     ["sources"]),

    ("D-A11Y-12 (round 4c, E6): an eye button on a field that cannot be masked stays on the bus",
     "GuideProbe.qml",
     "                  Accessible.ignored: !visible\n                  Accessible.role: Accessible.Button\n                  Accessible.name: fieldRow.masked",
     "                  Accessible.role: Accessible.Button\n                  Accessible.name: fieldRow.masked",
     ["xtream"]),

    ("D-A11Y-12 (round 4c, E6): the channel-number alert stays on the bus while no number is entered",
     "GuideProbe.qml",
     "                Accessible.ignored: !visible\n                Accessible.role: Accessible.AlertMessage\n                Accessible.name: \"Entering channel number \"",
     "                Accessible.role: Accessible.AlertMessage\n                Accessible.name: \"Entering channel number \"",
     ["sources"]),

    # Round 4d.
    ("D-A11Y-12 (round 4d, F6): the closed Programme panel's seven labels stay on the bus (the review's B1)",
     "GuideProbe.qml",
     "                Accessible.ignored: !visible\n                Accessible.role: Accessible.StaticText\n                Accessible.name: text\n",
     "                Accessible.role: Accessible.StaticText\n                Accessible.name: text\n",
     ["query", "sources"]),

    ("D-A11Y-12 (round 4d, F5): a hidden form's fields stay on the bus",
     "GuideProbe.qml",
     "                  enabled: field.enabled\n                  Accessible.ignored: !visible\n                  Accessible.role: Accessible.EditableText\n",
     "                  enabled: field.enabled\n                  Accessible.role: Accessible.EditableText\n",
     ["sources"]),

    ("D-A11Y-12 (round 4d, F7): the hidden wall's tiles stay on the bus",
     "GuideProbe.qml",
     "                  Accessible.ignored: !visible\n                  Accessible.role: Accessible.ListItem\n                  // The row's own composer",
     "                  Accessible.role: Accessible.ListItem\n                  // The row's own composer",
     ["query", "sources"]),

    ("D-SINK-98 (round 4d, F1): the label field is held by the stored reading alone again",
     "Model.mjs",
     "  return labelReadsAsAddress(s) || labelMayCarryCredential(s)\n",
     "  return labelReadsAsAddress(s)\n",
     ["sources"]),

    ("D-SINK-98 (round 4d, F4): a token's brackets are not set aside",
     "Model.mjs",
     "    b--\n  }\n  return s.substring(a, b)\n}\n",
     "    b--\n  }\n  return s\n}\n",
     ["sources"]),

    # Round 4e.
    ("D-SINK-98 (round 4e, I1): the fold decodes no escape",
     "Model.mjs",
     "  var d = labelDecode(s)\n  return d === s ? s : labelFoldNfkd(d)\n",
     "  return s\n",
     ["sources"]),

    ("D-SINK-98 (round 4e, I2): a token's raw text is not asked beside its core",
     "Model.mjs",
     "  if (labelShapeReadsAsAddress(t) || labelShapeReadsAsAddress(raw)) return true\n",
     "  if (labelShapeReadsAsAddress(t)) return true\n",
     ["sources"]),

    ("D-SINK-98 (round 4e, I3): a `//` at the first `/` is asked whatever the head before it",
     "Model.mjs",
     "  if (slash !== -1 && t.charAt(slash + 1) === \"/\" && head.indexOf(\"@\") === -1 && labelHost(head) === \"\") {\n",
     "  if (slash !== -1 && t.charAt(slash + 1) === \"/\") {\n",
     ["sources"]),

    ("D-A11Y-12 (round 4e, I9): rvfrsrc lists the hand-built record again (the harness's own fixture, not shipping code)",
     "host2.qml",
     "    : host.scenario === \"rvfrsrc\"\n",
     "    : host.scenario === \"never\"\n",
     ["sources"]),

    ("first run: the empty field reads back its placeholder as if it were content",
     "GuideProbe.qml",
     "text: root.fieldDisplay(fieldRow.fieldId)",
     "text: root.fieldPlaceholder(fieldRow.fieldId)",
     ["firstrun"]),

    ("footer: the stale cache stops being said in words (UX 7.2)",
     "Model.mjs",
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
    unproven = []
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
        if filename == "Model.mjs":
            # The model is several files (D-REL-5): mutate the one part that
            # holds the text, found by the shared reader, never by a list here.
            try:
                filename = model_files.file_containing(TREE, old)
            except model_files.ModelLayoutError as error:
                print("    SKIPPED: %s" % error)
                unproven.append("SKIPPED " + label)
                continue
        path = os.path.join(TREE, filename)
        text = open(path).read()
        if old not in text:
            print("    SKIPPED: pattern not found in %s" % filename)
            unproven.append("SKIPPED " + label)
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
        if not newly_red:
            unproven.append("INVISIBLE " + label)
        if newly_green:
            print("    newly green: %s" % newly_green)
        print()

    build_tree()
    print("tree rebuilt clean")
    # Round 4e (I7): a mutation that did not run, or that no check saw, is
    # a red run, not a line to read past.
    if unproven:
        print("\n%d mutation(s) proved nothing:" % len(unproven))
        for u in unproven:
            print("  " + u)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
