// scripts/dev-harness/harness-lib.js -- the harness's OWN pure logic, in a
// file both the fake shell (QML `import "harness-lib.js"`) and node
// (`require`) can call, so a check can drive the instrument for real
// instead of re-implementing it beside a comment that says it is the same
// (CLAUDE.md rule 12). run.sh stages this file beside shell.qml in the
// scratch root exactly as it stages Model.js; scripts/check.sh stages it the
// same way for qmllint.
//
// Nothing here is shipped: scripts/ is outside the release allowlist.
// Nothing here imports anything: the plugin's Model is HANDED IN, because a
// QML `.import` line would make this file unloadable from node and a node
// `require` would make it unloadable from QML. ASCII only (rule 8).

// D-SINK-19, lead ruling R6. The active source of a bar entry as its 8-hex
// key, or "" when the entry names none -- comparable across the host's
// stored and published sides without ever printing a URL (S-08).
//
// Two named candidates, in this order, and NOTHING else:
//
//   1. `sourceKey`, the mirror the plugin writes onto the entry since
//      D-SINK-19 (Model.OWNED_SETTINGS). Read raw rather than through
//      Model.settingsFrom, because a tree from before the change has no such
//      setting and this instrument has to read the same numbers on both
//      sides of it (clip-scenario.sh's --baseline d55149b runs this file's
//      shell.qml against that tree's Model.js). Accepted only when it has
//      the key grammar (Model.isSourceKey: 8 lowercase hex, optionally -N).
//   2. the hash of `playlistUrl`, the way every tree before D-SINK-19 named
//      its active source and the way an entry a user has just written with
//      `omarchy bar set` still names one.
//
// Why "named candidates only" is the whole ruling. The first repair of this
// function (the D-SINK-19 harness lane's, never merged) tried three names
// and then ITERATED EVERY OWN VALUE of the entry, returning the first that
// looked like a key
// -- so an `mpvArgs` of "deadbeef" or a label of "0123abcd" would have been
// reported as the active source and the instrument would have graded
// D-LIVE-20 against a setting the user typed. The review found it; the lead
// ruled it out. A key is read from the one setting that carries one.
//
// Why `sourceKey` beats the URL hash rather than the other way round. After
// the plugin's own write the stored entry carries the key and no URL, while
// the published side (one write behind, rule 9) still carries the URL the
// plugin consumed: both must read as the SAME source for the D-LIVE-20 block
// of sources-scenario.sh to compare them. A fresh `omarchy bar set
// playlistUrl` lands beside a stale mirror on the stored side; there the
// plugin adopts the URL (R1) and rewrites the entry, and this instrument
// reports the stale key until it does -- which is what "stored" means.
//
// An ABSENT entry (the host has no object entry for the plugin) answers "",
// never throws: Model.findBarEntry returns {} for one, and a scenario asserts
// on the answer rather than on the instrument surviving.
function entryKey(Model, entry) {
  var e = entry && typeof entry === "object" ? entry : {}
  var raw = e.sourceKey === undefined || e.sourceKey === null ? "" : String(e.sourceKey)
  var key = raw.replace(/^\s+|\s+$/g, "")
  if (key !== "" && Model.isSourceKey(key)) return key
  var url = Model.settingsFrom(e).playlistUrl
  var normalized = Model.normalizeSourceUrl(url, { origin: "cli" })
  return normalized === "" ? "" : Model.sourceKey(normalized)
}

// The key NAMES an entry carries, sorted, `id` excluded. Names only, never
// values: the values can be a credentialed URL and this reaches a terminal
// and a transcript (rule 5). What a scenario needs from it is whether the
// retired URL keys are still ON the entry after the plugin's write, which is
// a question about names.
function entryKeyNames(entry) {
  var out = []
  if (!entry || typeof entry !== "object") return out
  for (var k in entry) {
    if (!Object.prototype.hasOwnProperty.call(entry, k) || k === "id") continue
    out.push(k)
  }
  out.sort()
  return out
}

if (typeof module !== "undefined") {
  module.exports = { entryKey: entryKey, entryKeyNames: entryKeyNames }
}
