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

// D-SINK-19 round 10 (R20d): one OWNED setting's value off an entry, as
// stored, for a check that must read the stored entry rather than the
// guide's overlay of our own write (key-scenario Y4: the lagging host's
// publish is one write behind). Only the two keys the plugin owns, so no
// retired URL key can ever be read through it; null when absent.
function storedOwnedValue(entry, name) {
  if (name !== "showLogos" && name !== "sourceKey") return null
  if (!entry || typeof entry !== "object" || !Object.prototype.hasOwnProperty.call(entry, name)) return null
  var v = entry[name]
  return typeof v === "boolean" || typeof v === "string" ? v : null
}

// D-SINK-19, R5 and round 6. `ipc pointerState`: where the two writes of a
// pointer change stand -- the service's start-up gate (`dirsReady`), the
// state save parked behind it (`stateSavePending`), the entry mirror
// waiting for that save (`pendingEntryKey`, R5's own property), the save
// count in flight, the sticky failure, the helper's start-up exit, the
// reloads the service ignored in total and BY REASON (R15), and the
// `activeKey` the in-memory state carries -- so a scenario can see the
// interruptible window from inside rather than infer it from timing.
//
// A property the service does NOT HAVE is OMITTED, never reported as null
// (round 6, the round-5 live lens's P2). This used to be
// `s.pendingEntryKey === undefined ? null : s.pendingEntryKey` on every
// field, so a tree lacking the property was published as a present null,
// exactly as a service holding nothing is, and qa_json_field's NULL /
// NOFIELD split (round 5) never saw an absence: `held:NULL` in W3, F2 and
// F5 was satisfied on f275bde, a tree with no pendingEntryKey at all.
// Omitted, the absence reaches the reader and reads NOFIELD. Every one of
// these is declared WITH an initializer on the trees that have it
// (`property var pendingEntryKey: null`, `property int ...: 0`), so
// `undefined` here means "not declared"; a `property var` declared with
// no initializer would also read as absent, which is why the scenario's
// wants for a held key say NULL only for the field that is null by design.
//
// `lastSaveText` lives beside these on the service and is NOT reported: it
// is the state.json text, URLs included (rule 5). Numbers, booleans, keys
// and the per-reason object only. Nothing here reads a URL.
//
// D-SINK-19 round 11 (R21): `entryInputReports`, the service's own record of
// every value it refused or reported off the bar entry, as { setting, reason }
// -- names and reasons, never the value -- so a scenario counts the reports.
// And two booleans the instrument DERIVES and the service does not hold:
// whether the migration marker is in the state the service last saw LAND
// (`landedMigrated`, off `landedState`) and in memory (`memoryMigrated`).
// Derived here rather than by publishing `landedState`, which carries every
// source URL. Absent on a tree that has no such property (NOFIELD).
// R22a (round 12): the no-write mode and the two facts it is decided from --
// the latest load's kind, the start-up init's verdict on the path -- and how
// many writes it refused. Reasons and counts, never a path or a URL.
// R26a (2026-10-16): the read-before-write -- whether a save waits for its
// read, how many reads finished, how many the watchdog finished with no
// load, how many were skipped for a write in flight, how many re-reads a
// liftable no-write mode was given, how many saves were deferred to a turn
// of their own, and the slowest read in ms. Booleans and numbers only.
var POINTER_FIELDS = ["stateLoaded", "reconciled", "dirsReady", "stateSavePending", "pendingEntryKey", "configured",
                      "activeSourceKey", "stateSavesInFlight", "stateSaveFailed", "stateInitOk", "stateReloadsIgnored",
                      "stateReloadsByReason", "entryInputReports", "stateWriteBlocked", "stateLoadKind", "stateInitFound",
                      "stateWritesRefused", "stateVerifyPending", "stateVerifies", "stateVerifyNoLoad", "stateVerifySkipped",
                      "stateVerifyRetries", "stateSavesDeferred", "stateVerifyMsMax"]
function pointerStateOf(s) {
  if (!s) return { ok: false, error: { code: "no_service" } }
  var out = { ok: true }
  for (var i = 0; i < POINTER_FIELDS.length; i++) {
    var v = s[POINTER_FIELDS[i]]
    if (v !== undefined) out[POINTER_FIELDS[i]] = v
  }
  var st = s.userState
  if (st && st.activeKey !== undefined) out.memoryActiveKey = String(st.activeKey)
  if (st && st.sources) out.sourceCount = st.sources.length
  if (s.landedState !== undefined) out.landedMigrated = !!(s.landedState && s.landedState.entryMigrated === true)
  if (st && typeof st === "object") out.memoryMigrated = st.entryMigrated === true
  return out
}

if (typeof module !== "undefined") {
  module.exports = { entryKey: entryKey, entryKeyNames: entryKeyNames, pointerStateOf: pointerStateOf, POINTER_FIELDS: POINTER_FIELDS, storedOwnedValue: storedOwnedValue }
}
