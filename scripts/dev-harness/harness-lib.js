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
                      "stateVerifyRetries", "stateSavesDeferred", "stateVerifyMsMax",
                      // R27a (2026-10-20): the write wait and the writes issued; R27d:
                      // the migration held at the cap. (R29a withdrew R27a's second
                      // read and R28a's silences, re-reads and stall notices, and their
                      // four counters with them.)
                      "stateWriteWaiting", "stateSavesWaited", "stateWriteWaits",
                      "stateWriteWaitTimeouts", "stateWritesIssued", "stateWriteWaitMsMax", "migrationHeldFull", "migrationFullTold"]
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

// R27f (2026-10-20, D-PERF-1): WHEN HAS AN OPEN FINISHED? The async open
// instrument (shell.qml, `openAsync`) starts its clock at the summon, lets
// the event loop run, and samples the PRESENTING view on every frame the
// guide's window swaps.
//
// R28d (2026-10-20, the lead's ruling): IT COUNTS WHAT IS DRAWN. R27f counted
// every delegate in the view's contentItem -- the cacheBuffer's off-screen
// ones included (13 rows and 21 tiles where 10 and 16 are drawn) -- and
// settled on a count that held for three frames, so it trailed the drawn
// screen by the time it took to build the off-screen ones (94-182 ms on a
// cold open, round 1's live review) and let a view that realised part of a
// screen and filled the rest later pass L1-L5 with the partial time. Now:
//
// openDrawnSet(items, vp, layout) -- one frame. `items` are the view's
// channel delegates as { index, x, y, w, h, shown } in content coordinates,
// `vp` the visible area { x, y, w, h } (contentX, contentY, width, height),
// `layout` { kind: "list" | "grid", total: the rows the guide HAS (its own
// rowCount, never the view's count, so a view whose model is cut short reads
// as unfilled), spacing (list), cellW, cellH (grid) }. DRAWN is a delegate
// that is shown and intersects the visible area. The set is COMPLETE when it
// tiles the visible area: not empty, its indices contiguous (no slot missing
// in between), nothing missing above it (index 0, or the slot before the
// first would lie wholly above the area) and nothing missing below it (the
// last index of the guide, or the slot after the last would lie wholly below
// the area). On a grid a slot is a cell and a row is `cols` cells: a row in
// view is complete only when all its cells are drawn, or the guide ends in it.
// -> { drawn, built, minIndex, maxIndex, complete, reason } where `built` is
// every delegate (what R27f counted) and `reason` names the first test that
// failed ("" when complete): empty | gap | above | below.
function openDrawnSet(items, vp, layout) {
  var its = Array.isArray(items) ? items : []
  var v = vp || {}
  var L = layout || {}
  var vx = Number(v.x) || 0, vy = Number(v.y) || 0, vw = Number(v.w) || 0, vh = Number(v.h) || 0
  var total = Math.max(0, Math.floor(Number(L.total) || 0))
  var grid = L.kind === "grid"
  var cellW = Number(L.cellW) || 0, cellH = Number(L.cellH) || 0
  var cols = grid && cellW > 0 ? Math.max(1, Math.floor(vw / cellW)) : 1
  var spacing = Number(L.spacing) || 0
  var drawn = []
  for (var i = 0; i < its.length; i++) {
    var it = its[i] || {}
    if (it.shown === false) continue
    var x = Number(it.x), y = Number(it.y), w = Number(it.w), h = Number(it.h)
    if (!(w > 0) || !(h > 0)) continue
    if (x < vx + vw && x + w > vx && y < vy + vh && y + h > vy) drawn.push({ index: Math.floor(Number(it.index)), y: y, h: h })
  }
  drawn.sort(function (p, q) { return p.index - q.index })
  var out = { drawn: drawn.length, built: its.length, minIndex: -1, maxIndex: -1, complete: false, reason: "empty" }
  if (!drawn.length) return out
  var first = drawn[0], last = drawn[drawn.length - 1]
  out.minIndex = first.index; out.maxIndex = last.index
  for (var j = 1; j < drawn.length; j++) if (drawn[j].index !== drawn[j - 1].index + 1) { out.reason = "gap"; return out }
  // above: the slot before the first drawn one
  if (first.index > 0) {
    if (grid && first.index % cols !== 0) { out.reason = "above"; return out }
    var prevBottom = grid ? first.y : first.y - spacing
    if (prevBottom > vy) { out.reason = "above"; return out }
  }
  // below: the slot after the last drawn one
  if (last.index < total - 1) {
    if (grid && (last.index + 1) % cols !== 0) { out.reason = "below"; return out }
    var nextTop = grid ? last.y + cellH : last.y + last.h + spacing
    if (nextTop < vy + vh) { out.reason = "below"; return out }
  }
  out.complete = true; out.reason = ""
  return out
}

// openDrawnSettle(frames, tailMs) -- the open. `frames` are the samples in
// order, each { at: ms since the summon, drawn, complete, minIndex,
// maxIndex }. The open is REALISED at the first frame whose drawn set is
// complete: the first frame swapped with the visible area tiled. After it
// the instrument keeps sampling for `tailMs` (shell.qml's openTailMs) and
// `changedAfter` counts the frames in that tail whose drawn set differs from
// the decision's -- a view still filling after the decision, which a correct
// completeness test makes impossible and this check makes visible.
// -> { settled, realisedAt, count, frame, changedAfter, tailFrames, tailDone }
function openDrawnSettle(frames, tailMs) {
  var fs = Array.isArray(frames) ? frames : []
  var tail = Math.max(0, Number(tailMs) || 0)
  var out = { settled: false, realisedAt: -1, count: -1, frame: -1, changedAfter: 0, tailFrames: 0, tailDone: false }
  for (var i = 0; i < fs.length; i++) {
    if (fs[i] && fs[i].complete === true) { out.settled = true; out.realisedAt = Number(fs[i].at); out.count = Number(fs[i].drawn); out.frame = i; break }
  }
  if (!out.settled) return out
  var d = fs[out.frame]
  for (var k = out.frame + 1; k < fs.length; k++) {
    var f = fs[k] || {}
    if (Number(f.at) - out.realisedAt > tail) { out.tailDone = true; break }
    out.tailFrames++
    if (Number(f.drawn) !== Number(d.drawn) || Number(f.minIndex) !== Number(d.minIndex) || Number(f.maxIndex) !== Number(d.maxIndex)) out.changedAfter++
  }
  return out
}

if (typeof module !== "undefined") {
  module.exports = { entryKey: entryKey, entryKeyNames: entryKeyNames, pointerStateOf: pointerStateOf, POINTER_FIELDS: POINTER_FIELDS, storedOwnedValue: storedOwnedValue,
                     openDrawnSet: openDrawnSet, openDrawnSettle: openDrawnSettle }
}
