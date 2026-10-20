// tests/service-harness.js -- runs Service.qml's OWN functions in node.
//
// D-SINK-19 round 10, R20d. The service-order driver in tests/Model.test.js
// reproduces Service.qml's call order over the shipping MODEL decisions and
// binds itself to the shipping file by regular expressions. That is rule 12
// for the model and rule 14's failure for the service: the round-9 data-loss
// lens put a skip one line above the funnel's compose (`if (published && ...)
// return true`) and the suite read 2268 checks, 0 failures, because no regex
// changed and the driver went on modelling the funnel it remembered; on the
// lagging host the user's second logo toggle was ignored. A mirror cannot see
// an edit to the thing it mirrors.
//
// This harness does not mirror. It reads Service.qml, compiles every
// top-level `function` of the root item -- and the handful of signal-handler
// blocks the state machine lives in -- as JavaScript, and runs THEM against
// fakes of what QML supplies: the host (`shell`, lagging one write behind or
// echoing at once, rule 9), the state FileView (its `saved` / `saveFailed`
// as queued events, a failing disk on request), Qt.callLater (deferred, and
// de-duplicated per function the way Qt does it) and a clock. The root's
// `readonly property` bindings are compiled from their own text and
// re-evaluated on every read, so `settings`, `activeSourceKey` and the rest
// are what Service.qml says they are. A Service.qml edit is therefore an
// edit to what runs here: S1b's skip skips here too.
//
// What is faked is what QML itself does, and nothing that decides anything:
// processes do not run (a probe's exit is delivered by the test, with the
// helper's own status text), cache jobs are recorded and dropped, and change
// handlers fire for the three properties the source state machine listens
// to (`settings` on an own-write reassignment or a host publish, the host
// publish itself, and nothing else). A function the harness must not run is
// named in STUBBED with what QML-side effect it stands for.
"use strict"

// A free identifier in Service.qml that is an element id or a QML global,
// and the fake that stands in for it. Anything else unqualified resolves to
// the root's own properties (QML's scoping), or to the JavaScript global.
function makeIds(h) {
  // A process fake RECORDS the signals it is sent (R24g): whether a TERM or
  // a KILL ends it is the double's decision below, never the service's.
  const proc = name => ({ name, running: false, command: [], environment: {}, signals: [], signal(n) { this.signals.push(n) } })
  // cacheProc RUNS (R22b, rule 10): the cache layout's start-up save is one of
  // the state writers, and the round-11 harness stubbed startCacheLayout as
  // "current" and so could not see it. Setting `running` queues the helper's
  // answer for the command it was given (h.cacheAnswer), delivered through
  // Service.handleCacheExit, the handler the real exit calls.
  const cacheProc = { name: "cacheProc", command: [], environment: {}, signal() {}, _running: false }
  Object.defineProperty(cacheProc, "running", {
    get() { return cacheProc._running },
    set(v) {
      cacheProc._running = v
      if (v === true) {
        const command = cacheProc.command.slice()
        h.cacheRuns.push(command)
        h.later.push({ fn: () => { cacheProc._running = false; h.root.handleCacheExit(h.cacheAnswer(command)) }, args: [] })
      }
    }
  })
  // Timers do not run; restart() and stop() are COUNTED, so a test can see
  // that a watchdog was armed (R23c) without the harness running its clock.
  const timer = name => ({ name, restarts: 0, stops: 0, restart() { this.restarts++ }, stop() { this.stops++ }, start() {}, running: false })
  const view = name => ({ name, reload() {}, text() { return "" }, setText() {} })
  return {
    stateFile: h.stateFile,
    stateInitProc: proc("stateInitProc"),
    // R24d: the start-up mkdir is the first half of the check the watchdog
    // bounds; it runs (h.initExit delivers its exit) like the init.
    mkdirProc: proc("mkdirProc"),
    // R24e: the active fetch's command is observed (Model.fetchStateDir);
    // nothing is run.
    playlistProc: proc("playlistProc"),
    playlistWatchdog: timer("playlistWatchdog"),
    // The start-up init's reply (R22a), written by h.helperInit just before
    // the exit handler runs, as the collector holds it when `exited` fires.
    stateInitStdout: h.stateInitStdout,
    sourceProbeProc: proc("sourceProbeProc"),
    configShieldProc: proc("configShieldProc"),
    logoFetchProc: proc("logoFetchProc"),
    cacheProc,
    failedProc: proc("failedProc"),
    probeWatchdog: timer("probeWatchdog"),
    // R23c: the init's watchdog and its kill grace. Timers do not run here;
    // a test that times the init out calls h.initExit({ timeout: true }),
    // which runs the watchdog's OWN onTriggered and then the exit handler.
    stateInitWatchdog: timer("stateInitWatchdog"),
    stateInitKill: timer("stateInitKill"),
    // R26a: the bound on the read before a save. A test fires it by hand
    // with h.verifyWatchdog(), which runs its OWN onTriggered from its text,
    // or by moving the clock with h.elapse(ms), which fires it at the
    // interval the tree DECLARES (F4, lane-clean-f1; bootService below).
    stateVerifyWatchdog: timer("stateVerifyWatchdog"),
    // R27a: the bound on a save held for our write in flight. Fired by hand
    // with h.writeWaitWatchdog(), or by h.elapse(ms) at its declared interval.
    stateWriteWaitWatchdog: timer("stateWriteWaitWatchdog"),
    switchTimeout: timer("switchTimeout"),
    // D-REL-7: the control slot's watchdog, which handleControlResult stops
    // first; a test runs that handler to see how the status branch routes a
    // reply from a damaged helper. Counted like every timer, never run.
    controlWatchdog: timer("controlWatchdog"),
    configShieldDebounce: timer("configShieldDebounce"),
    channelsFile: view("channelsFile"),
    playlistStatusFile: view("playlistStatusFile"),
    // execDetached is the notification sink (Service.notify): recorded as the
    // argv the shell would run, never run (R21b's report is observed here).
    Quickshell: { env() { return "" }, execDetached(argv) { h.detached.push(argv.slice()) } }
  }
}

// What the harness does not run, and why. Each is a QML-side effect with no
// say in what the bar entry or state.json end up holding.
const STUBBED = {
  runConfigShield: "starts the D-SINK-18 shield process; the file is taken as private (hostConfigShield below)",
  noteSessionOutcome: "the player session record; no part of the source state machine",
  markDeadSession: "the player session record",
  schedulePrune: "the start-up cache prune",
  fetchLogos: "starts the logo fetch",
  clearSourceData: "unbinds the channel and EPG data of the previous source",
  pruneFailed: "dead-channel memory"
}

// One scanner for the two jobs below. From `start`, skipping strings,
// comments and regular-expression literals: with `untilNewline` false, the
// index of the "}" matching the "{" at `start`; with it true, the end of the
// expression that starts there -- the first newline outside every bracket.
function scan(text, start, untilNewline) {
  let depth = 0
  let prev = untilNewline ? "=" : ""
  for (let i = start; i < text.length; i++) {
    const c = text[i]
    if (c === "\n" && untilNewline && depth === 0) return i
    if (c === "/" && text[i + 1] === "/") {
      if (untilNewline && depth === 0) return i
      i = text.indexOf("\n", i)
      if (i === -1) return untilNewline ? text.length : -1
      if (untilNewline && depth === 0) return i
      prev = "\n"
      continue
    }
    if (c === "/" && text[i + 1] === "*") { i = text.indexOf("*/", i + 2); if (i === -1) return -1; i++; continue }
    if (c === '"' || c === "'" || c === "`") {
      for (i++; i < text.length && text[i] !== c; i++) if (text[i] === "\\") i++
      prev = c
      continue
    }
    if (c === "/" && /[(,=:[!&|?{};+\-*%<>~^\n]/.test(prev || "\n")) {
      let cls = false
      for (i++; i < text.length; i++) {
        if (text[i] === "\\") { i++; continue }
        if (text[i] === "[") cls = true
        else if (text[i] === "]") cls = false
        else if (text[i] === "/" && !cls) break
      }
      prev = "/"
      continue
    }
    if (c === "{" || c === "(" || c === "[") depth++
    else if (c === "}" || c === ")" || c === "]") {
      depth--
      if (!untilNewline && depth === 0 && c === "}") return i
    }
    if (!/\s/.test(c)) prev = c
  }
  return untilNewline ? text.length : -1
}

function matchBrace(text, open) { return scan(text, open, false) }

// Every top-level function of the root item: `  function name(args) {`.
function rootFunctions(text) {
  const out = {}
  const re = /^  function ([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\) \{/gm
  let m
  while ((m = re.exec(text)) !== null) {
    const open = m.index + m[0].length - 1
    const close = matchBrace(text, open)
    if (close === -1) throw new Error("service-harness: cannot find the end of " + m[1])
    out[m[1]] = { args: m[2], body: text.slice(open + 1, close) }
  }
  return out
}

// The root's single-line and block property declarations.
function rootProperties(text) {
  const out = []
  const re = /^  (readonly )?property ([A-Za-z]+) ([A-Za-z_][A-Za-z0-9_]*)(: )?/gm
  let m
  while ((m = re.exec(text)) !== null) {
    if (!m[4]) { out.push({ readonly: !!m[1], type: m[2], name: m[3], expr: null, block: false }); continue }
    const start = m.index + m[0].length
    if (text[start] === "{" && /^\{\s*\n/.test(text.slice(start, start + 40))) {
      const close = matchBrace(text, start)
      out.push({ readonly: !!m[1], type: m[2], name: m[3], expr: text.slice(start + 1, close), block: true })
      continue
    }
    const end = scan(text, start, true)
    out.push({ readonly: !!m[1], type: m[2], name: m[3], expr: text.slice(start, end), block: false })
  }
  return out
}

// One signal-handler block, by an anchor that precedes its "{".
function handlerBlock(text, anchor) {
  const at = text.indexOf(anchor)
  if (at === -1) return null
  const open = text.indexOf("{", at + anchor.length - 1)
  const close = matchBrace(text, open)
  return close === -1 ? null : text.slice(open + 1, close)
}

function defaultOf(type) {
  if (type === "bool") return false
  if (type === "int" || type === "real" || type === "double") return 0
  if (type === "string") return ""
  return null
}

const PID = "io.github.rmcdavid.iptv"
const clone = x => JSON.parse(JSON.stringify(x))

// The host, both shapes rule 9 names: "lag" publishes the bar one write
// behind (through 4.0.4), "echo" at once (omacom/omarchy#15082).
class Host {
  constructor(entry, mode) {
    this.mode = mode
    this.stored = { bar: { layout: { left: [], center: [], right: [Object.assign({ id: PID }, entry || {})] } } }
    this.published = clone(this.stored.bar)
    this.onPublish = null
    this.writes = []
    this.answers = []
  }
  get barConfig() { return this.published }
  storedEntry() { return this.stored.bar.layout.right[0] }
  assign(next) {
    const prev = clone(this.stored)
    this.stored = clone(next)
    this.published = clone(this.mode === "lag" ? prev.bar : this.stored.bar)
    if (this.onPublish) this.onPublish()
  }
  // shell.qml's updateEntryInline: `false` when the stored entry already is
  // exactly this (its !dirty branch), else the write and a publish. A test
  // that needs the host to have no writer at all (the harness shell.qml's
  // persistFails) shadows it with `host.updateEntryInline = undefined` and
  // deletes the shadow to restore it.
  updateEntryInline(id, settings) {
    const next = { id }
    for (const k in settings) if (k !== "id") next[k] = settings[k]
    this.writes.push(clone(next))
    const copy = clone(this.stored)
    if (JSON.stringify(copy.bar.layout.right[0]) === JSON.stringify(next)) { this.answers.push(false); return false }
    copy.bar.layout.right[0] = next
    this.answers.push(true)
    this.assign(copy)
    return true
  }
  // `omarchy bar set`: a foreign write, which the lagging host flushes with
  // the write after it -- modelled, as the driver does, by publishing twice.
  externalSet(key, value) {
    const copy = clone(this.stored)
    if (value === null) delete copy.bar.layout.right[0][key]; else copy.bar.layout.right[0][key] = value
    this.assign(copy)
    if (this.mode === "lag") this.assign(copy)
  }
}

// The state FileView (atomicWrites): setText queues `saved` or `saveFailed`;
// the view's text is what the last delivered event wrote.
// `coalesce`: the measured behaviour of a burst (Model.stateSaveLanded): a
// write queued behind one still in flight is REPLACED by the next, and the
// replaced write raises nothing -- so at most two events are outstanding,
// the started one and the latest.
//
// R22a (round 12). The file can also be MISSING or UNREADABLE, and a load is
// delivered through stateFile's own onLoaded / onLoadFailed handlers (compiled
// from Service.qml), carrying what Quickshell 0.3.1's FileView was MEASURED to
// report for each case (Model.STATE_LOAD_ERRORS; nested headless cage,
// 2026-10-13):
//   exists false            loadFailed 2 (FileNotFound)
//   fault "file-0000"       loadFailed 3 (PermissionDenied)
//   fault "dir-0000"        loadFailed 2 (FileNotFound) -- the unreadable
//                           directory reads like a missing file
//   fault "is-dir"          loadFailed 4 (NotAFile)
//   fault "file-foreign",   the same two, for a file or directory the helper
//   "dir-foreign"           cannot chmod (another owner): nothing repairs them
//   any other text          loaded, with that text ("" for an empty file)
// `reload()` queues a load, as stateFile.reload() does. A save to a file
// whose directory cannot be entered fails, as it does for real.
//
// R23g (round 13): WHICH CHANGES RAISE A RELOAD, measured on Quickshell
// 0.3.1 / Qt 6.11.2 in a nested headless cage on a private D-Bus, both with
// a bare FileView declared exactly as stateFile is
// (scripts/dev-harness/spikes/filewatch/measure.sh, 16 sequences) and with
// the REAL Service.qml under the dev harness, idle and under load:
//   an external IN-PLACE write (truncate, empty, garbage, a good copy put
//     back), the helper's atomic rename (`state favorite add`, `state source
//     add`), a chmod              fileChanged AND a load, every time, before
//                                 or after any number of the view's own
//                                 saves, and again after a restart: the
//                                 watch was never lost in any sequence
//   the view's OWN setText save   fileChanged, and the reload it causes
//                                 delivers a load ONLY SOMETIMES: never for
//                                 a lone save at idle (16 of 16 probe
//                                 saves), but under load, or when a later
//                                 setText is already queued, the reload
//                                 lands and carries our own text (the
//                                 service counted it as `own-write`)
// So the external reloads the tests deliver by hand (h.loadState() after a
// change to h.stateFile.disk) are all reloads the real view delivers, and
// the own-write echo is a reload it MAY deliver. Both shapes are run:
// `ownEcho` "load" (the default, the echo delivered after every `saved`)
// and "none" (never delivered) -- the opts field, or IPTV_HARNESS_OWN_ECHO
// for a whole run, which scripts/check.sh makes a second time with "none".
// A pin that holds in only one of the two is relying on timing.
//
// R24c (round 14): WHETHER THE WATCH IS ARMED AT ALL. Measured in the same
// cage (spikes/filewatch, set r24): a FileView whose path's DIRECTORY did not
// exist when it first loaded -- the production fresh install, XDG_STATE_HOME
// present and omarchy-iptv/ under it absent -- raises NOTHING for the rest of
// the session: not the init's creation of the file, not a helper rename, not
// an in-place garbage write, and not the echo of its own saves (sequence Q;
// the round-13 live lens saw the same on the real Service.qml). One explicit
// reload() once the file exists arms it, and from then on everything is
// seen (R, T, R2). With the directory present and the file absent, the
// init's creation IS seen (U). So `dirAbsent` (the default for a boot with
// no file and no fault; `dirPresent: true` for the other shape) starts the
// view unarmed: `reload()` arms it when the file exists, h.foreign() delivers
// a change only while it is armed, and the own-write echo needs it too.
//
// R26c (2026-10-16, F-HARNESS-29, rule 10): three more measured facts, from
// a bare FileView declared as stateFile is and from the real Service.qml,
// in a nested cage on a private bus (scripts/dev-harness/spikes/filewatch-
// links on lane-clean-w-probe, and the sink lane's lane-s-rig probe):
//   a setText issued INSIDE the view's own onLoaded  writes the file and
//     raises NO `saved` (16 of 16); the reload its change raises is still
//     delivered. Here: a "silent" event -- the disk takes the text, nothing
//     is reported, the echo comes when the watch is armed. `handlerWrites`
//     counts every setText made inside any of the view's handlers, so a
//     pin can hold the service to none.
//   a save that CREATES the file  creates it 0666 & ~umask -- 0644 at the
//     shell's umask 022 (measured on the user's own omarchy-shell and in the
//     rig) -- whatever atomicWrites says; a save over an EXISTING file keeps
//     that file's mode (0600 and 0640 measured). Here: `mode` (null while
//     there is no file) and `umask`; the helper's `state init` creates 0600.
//   a REPLACEMENT or a RE-POINT at the path  (a rename over a link, sed -i,
//     rm and cp, ln -sfn to another file or folder) raises NOTHING, and the
//     view watches nothing after it until one reload() re-arms it. Here:
//     h.replace(change) changes the disk and unarms the watch, delivering no
//     load; reload() arms it again when there is a file to watch.
//   F-HARNESS-31 (lane-clean-f1, the same measurement's set `inflight`):
//   a reload asked while the view's OWN write is out delivers no load
//     during that write (30 of 30). Here: h.foreign delivers nothing while
//     one of our writes is queued (counted in h.droppedForeign), so the
//     change it made is replaced by our rename -- the same-instant loss.
class StateFile {
  constructor(text, o) {
    const opts = o || {}
    this.exists = opts.exists !== undefined ? opts.exists : text !== ""
    this.fault = opts.fault || null
    this.dirAbsent = opts.dirAbsent !== undefined ? opts.dirAbsent === true : (!this.exists && !this.fault && opts.dirPresent !== true)
    this.watchArmed = !this.dirAbsent
    this.disk = text; this.view = text; this.events = []; this.writeFails = false; this.coalesce = false
    this.loader = null
    this.mode = this.exists ? (opts.mode !== undefined ? opts.mode : 0o600) : null
    this.umask = opts.umask !== undefined ? opts.umask : 0o022
    this.inLoad = false; this.inHandler = 0; this.handlerWrites = 0; this.droppedReloads = 0
    this.ownEcho = opts.ownEcho || process.env.IPTV_HARNESS_OWN_ECHO || "load"
    if (this.ownEcho !== "load" && this.ownEcho !== "none") throw new Error("service-harness: ownEcho is load or none, not " + this.ownEcho)
  }
  text() { return this.view }
  setText(text) {
    // An atomic write replaces the file by a rename inside its directory, so
    // a file nobody may read is still REPLACED (the round-11 P1's last step)
    // and only a directory that cannot be entered, or a directory AT the
    // path, makes it fail. R24b: and a DANGLING symlink whose target's
    // FOLDER is missing (measured: the view's save follows the link and
    // fails, sequence X), or a file where the state directory should be.
    // D-DOC-11 (round 15, rule 10): a dangling link whose target's folder
    // EXISTS does not fail -- measured (the round-14 lens's C6 and Z9, two
    // runs): the save follows the link and CREATES the target, saved+1, the
    // link left a link; deliverOne then finds a link that leads somewhere.
    // R25c: a link at the state FOLDER that leads nowhere has no folder to
    // write the temporary file in, which is sequence X's mechanism.
    const blocksWrite = this.fault === "dir-0000" || this.fault === "dir-foreign" || this.fault === "is-dir"
      || this.fault === "dangling-link-nodir" || this.fault === "not-a-dir" || this.fault === "folder-link"
    // R26c: inside the view's own onLoaded, a write that lands raises nothing.
    if (this.inHandler > 0) this.handlerWrites++
    const ev = { kind: this.writeFails || blocksWrite ? "saveFailed" : (this.inLoad ? "silent" : "saved"), text }
    if (this.coalesce && this.events.length >= 2) this.events[this.events.length - 1] = ev
    else this.events.push(ev)
  }
  // What a load of the file reports, as { loaded, error } plus the text.
  loadResult() {
    if (this.fault === "file-0000" || this.fault === "file-foreign") return { loaded: false, error: 3 }
    if (this.fault === "dir-0000" || this.fault === "dir-foreign") return { loaded: false, error: 2 }
    if (this.fault === "is-dir") return { loaded: false, error: 4 }
    // R24b: both measured as FileNotFound (the round-13 claims lens's
    // fvkinds.txt: "dangling ... ERR2", "filedir ... ERR2"); a dangling link
    // into a missing folder and a dangling FOLDER link (R25c) are a missing
    // parent, which the R22a table measured as FileNotFound too.
    if (this.fault === "dangling-link" || this.fault === "dangling-link-nodir" || this.fault === "not-a-dir" || this.fault === "folder-link") return { loaded: false, error: 2 }
    if (!this.exists) return { loaded: false, error: 2 }
    return { loaded: true, text: this.disk }
  }
  // R27a (rule 10): a reload asked while one of OUR writes is out delivers
  // NO load during that write -- the measured view (F-HARNESS-31, 30 of 30),
  // which until R27 this double modelled only for a FOREIGN change's reload
  // (h.foreign) and delivered here. Counted in `droppedReloads`, so a pin can
  // see a read the service asked for at the wrong time go unanswered.
  reload() {
    if (this.events.length > 0) { this.droppedReloads++; return }
    if (this.exists && !this.fault) this.watchArmed = true
    if (this.loader) this.loader()
  }
}

// The REAL helper's `state init`, as a double that is not more forgiving
// than it (rule 10) -- every branch below is the shipping helper's, pinned by
// tests/test_state.py's R22a cases against the same five faults:
//   nothing there   found "absent"; creates the file 0600 with the default
//                   state (the helper's own bytes, HELPER_EMPTY_STATE), which
//                   raises a reload (a watched missing file that appears
//                   reloads, measured)
//   "file-0000"     found "file"; chmods it to 0600, which raises a reload
//                   (inotify IN_ATTRIB, measured)
//   "dir-0000"      found "unreadable" (lstat EACCES); ensure_private_dir
//                   chmods the directory to 0700; NO reload follows (the
//                   watch never attached, measured), but an explicit
//                   stateFile.reload() then loads the file (measured)
//   "is-dir"        found "other"; changes nothing
//   "dangling-link" found "link" (R24b); changes nothing (and
//   "-nodir"        the same for the one whose target's folder is missing)
//   "folder-link"   found "folder-link" (R25c): a link at the state FOLDER
//                   that dangles or leads to a non-folder; changes nothing
//   "not-a-dir"     found "not-a-dir" (R24b: a file where the state
//                   directory should be); changes nothing
//   "*-foreign"     found as above; the chmod fails, so nothing changes
//   garbage / empty found "file"; changes nothing (O_EXCL refuses, the mode
//                   is already 0600)
const HELPER_EMPTY_STATE = '{"version":2,"cacheLayout":0,"favorites":[],"recents":[],"lastPlayed":null,"session":null,"sources":[],"savedSearches":[],"hiddenGroups":[],"activeKey":""}\n'
//   a non-zero exit  nothing printed and nothing changed (the init that
//                   could not make the directory, say)
function helperInit(file, code) {
  if (code !== undefined && code !== 0) return { reply: "", raises: false }
  let found, raises = false
  if (file.fault === "dir-0000") { found = "unreadable"; file.fault = null }
  else if (file.fault === "file-0000") { found = "file"; file.fault = null; raises = true }
  else if (file.fault === "is-dir") found = "other"
  // R24b: the real helper's answers (tests/test_state.py's StateSymlinkTest
  // and the not-a-dir case); it changes nothing at either.
  else if (file.fault === "dangling-link" || file.fault === "dangling-link-nodir") found = "link"
  // R25c: a link at the state folder (or above it) that leads nowhere.
  else if (file.fault === "folder-link") found = "folder-link"
  else if (file.fault === "not-a-dir") found = "not-a-dir"
  else if (file.fault === "file-foreign") found = "file"
  else if (file.fault === "dir-foreign") found = "unreadable"
  else if (!file.exists) {
    // R24c: the creation raises a reload only when the view is watching --
    // the directory existed at its first load (sequence U); in the fresh
    // install's dir-absent shape it raises nothing (sequence Q).
    found = "absent"; file.exists = true; file.disk = HELPER_EMPTY_STATE; file.mode = 0o600; raises = file.watchArmed
    file.dirAbsent = false
  }
  else found = "file"
  return { reply: JSON.stringify({ ok: true, kind: "state", action: "init", found, created: found === "absent" }) + "\n", raises }
}

function bootService(serviceText, Model, o) {
  const opts = o || {}
  const h = { clock: opts.clock || 1760000000000, later: [], cacheRuns: [], signals: [], warnings: [], detached: [], turns: 0 }
  h.host = new Host(opts.entry, opts.host || "lag")
  h.stateFile = new StateFile(opts.stateText || "", { exists: opts.exists, fault: opts.fault, ownEcho: opts.ownEcho, dirAbsent: opts.dirAbsent, dirPresent: opts.dirPresent, mode: opts.mode, umask: opts.umask })
  h.stateInitStdout = { text: "" }
  // The helper's `cache` reply: ok for every verb, unless a test says
  // otherwise (h.cacheFails = ["migrate"]).
  h.cacheFails = []
  h.cacheAnswer = (command) => {
    const verb = command[command.indexOf("--cache-dir") + 2] || ""
    if (h.cacheFails.indexOf(verb) !== -1) return JSON.stringify({ ok: false, kind: "cache", action: verb, error: { code: "io", message: "failed" } }) + "\n"
    return JSON.stringify({ ok: true, kind: "cache", action: verb }) + "\n"
  }
  const ids = makeIds(h)
  const fns = rootFunctions(serviceText)
  const props = rootProperties(serviceText)
  const values = {}
  const root = {}
  const quiet = { log() {}, info() {}, error() {}, warn(m) { h.warnings.push(String(m)) } }
  class FakeDate extends Date {
    constructor(...a) { if (a.length === 0) super(h.clock); else super(...a) }
    static now() { return h.clock }
  }
  const Qt = {
    callLater(fn, ...args) {
      if (h.later.some(e => e.fn === fn)) return
      h.later.push({ fn, args })
    },
    resolvedUrl(x) { return { toString() { return String(x) } } }
  }
  const extras = Object.assign({ root, Model, console: quiet, Qt, Date: FakeDate }, ids)
  const scope = new Proxy({}, {
    has(t, k) { return typeof k === "string" && (k in extras || Object.prototype.hasOwnProperty.call(root, k)) },
    get(t, k) { if (k === Symbol.unscopables) return undefined; return k in extras ? extras[k] : root[k] },
    set(t, k, v) { root[k] = v; return true }
  })
  h.compileErrors = []
  const compile = (args, body, name) => {
    try {
      return new Function("scope", "with (scope) { return function " + name + "(" + args + ") {" + body + "\n} }")(scope)
    } catch (e) {
      h.compileErrors.push(name + ": " + e.message)
      return function () { throw new Error("service-harness: " + name + " did not compile: " + e.message) }
    }
  }
  // Change handlers, compiled from their own text.
  const onSettingsText = (serviceText.match(/^  onSettingsChanged: (.*)$/m) || [])[1]
  const onHostText = (serviceText.match(/^  onHostSettingsChanged: (.*)$/m) || [])[1]
  const onSettingsChanged = onSettingsText ? compile("", onSettingsText, "onSettingsChanged") : () => {}
  const onHostSettingsChanged = onHostText ? compile("", onHostText, "onHostSettingsChanged") : () => {}
  // Properties. A readonly binding is re-evaluated on every read.
  for (const p of props) {
    if (p.readonly && p.expr !== null) {
      const get = p.block ? compile("", p.expr, "binding_" + p.name) : compile("", "return (" + p.expr + ")", "binding_" + p.name)
      Object.defineProperty(root, p.name, { get() { try { return get() } catch (e) { return defaultOf(p.type) } }, enumerable: true, configurable: true })
      continue
    }
    values[p.name] = defaultOf(p.type)
    // `ownWrite` is the one plain property whose reassignment re-evaluates
    // `settings` (and so fires onSettingsChanged -> reconcile), whatever its
    // content: a new object is a new value to a QML var property.
    Object.defineProperty(root, p.name, {
      get() { return values[p.name] },
      set(v) {
        const before = values[p.name]
        values[p.name] = v
        if (p.name === "ownWrite" && v !== before && h.started) onSettingsChanged()
      },
      enumerable: true, configurable: true
    })
  }
  for (const p of props) {
    if (p.readonly || p.expr === null || p.block) continue
    try { values[p.name] = compile("", "return (" + p.expr + ")", "init_" + p.name)() } catch (e) { values[p.name] = defaultOf(p.type) }
  }
  // Signals are recorded.
  for (const m of serviceText.matchAll(/^  signal ([A-Za-z_][A-Za-z0-9_]*)\(/gm)) root[m[1]] = (...a) => h.signals.push([m[1]].concat(a))
  for (const name in fns) {
    if (name in STUBBED) continue
    root[name] = compile(fns[name].args, fns[name].body, name)
  }
  root.runConfigShield = () => {}
  root.noteSessionOutcome = () => {}
  root.markDeadSession = () => {}
  root.schedulePrune = () => {}
  root.fetchLogos = () => {}
  root.clearSourceData = () => {}
  root.pruneFailed = () => {}
  root.hostConfigShield = Model.CONFIG_SHIELD_PRIVATE
  root.manifest = { id: PID }
  // The FileView's two outcome handlers and the start-up init's exit, from
  // their own text.
  const onSaved = compile("", handlerBlock(serviceText, "    onSaved: {") || "", "onSaved")
  const failedText = handlerBlock(serviceText, "    onSaveFailed: (error) => {")
  const onSaveFailed = compile("error", failedText || "", "onSaveFailed")
  const initText = handlerBlock(serviceText.slice(serviceText.indexOf("target: stateInitProc")), "function onExited(exitCode, exitStatus) {")
  const onInitExited = compile("exitCode, exitStatus", initText || "", "onInitExited")
  // R23c: the init watchdog's own handler, from its text ("" on a tree
  // without one: the timeout then changes nothing, which is that tree).
  const watchdogText = serviceText.indexOf("id: stateInitWatchdog") === -1 ? ""
    : handlerBlock(serviceText.slice(serviceText.indexOf("id: stateInitWatchdog")), "onTriggered: {") || ""
  const onInitWatchdog = compile("", watchdogText, "stateInitWatchdog_onTriggered")
  // R24g: the kill grace's own handler, from its text, run only when the
  // service ARMED it (a restart counted since the watchdog fired) -- a tree
  // without the KILL leaves a TERM-ignoring process running here, as it
  // would for real.
  const killText = serviceText.indexOf("id: stateInitKill") === -1 ? ""
    : handlerBlock(serviceText.slice(serviceText.indexOf("id: stateInitKill")), "onTriggered: {") || ""
  const onInitKill = compile("", killText, "stateInitKill_onTriggered")
  // R26a: the verify watchdog's one-line handler ("" on a tree without one).
  const verifyText = (serviceText.slice(Math.max(0, serviceText.indexOf("id: stateVerifyWatchdog"))).match(/^    onTriggered: (.*)$/m) || [])[1]
  const onVerifyWatchdog = serviceText.indexOf("id: stateVerifyWatchdog") === -1 || !verifyText ? () => {} : compile("", verifyText, "stateVerifyWatchdog_onTriggered")
  // R24d: mkdir's exit handler, from its text (on a tree before R24d it
  // starts the init, which then arms the watchdog itself).
  const mkdirText = serviceText.indexOf("target: mkdirProc") === -1 ? ""
    : handlerBlock(serviceText.slice(serviceText.indexOf("target: mkdirProc")), "function onExited(exitCode, exitStatus) {") || ""
  const onMkdirExited = compile("exitCode, exitStatus", mkdirText, "onMkdirExited")
  // stateFile's two LOAD handlers, from their own text (R22a): the harness
  // never calls applyUserState itself any more, so a load is classified the
  // way the shipping handlers classify it. One-line handlers: `onLoaded: X`
  // and `onLoadFailed: (error) => X`, inside the stateFile block.
  const stateBlock = serviceText.slice(serviceText.indexOf("    id: stateFile"))
  // The pre-R22 handlers (`root.applyUserState(text())` and
  // `root.applyUserState("")`) compile too, so another tree's Service.qml
  // (IPTV_SERVICE_QML) runs its OWN load path here: `text()` is the view's.
  const loadedText = ((stateBlock.match(/^    onLoaded: (.*)$/m) || [])[1] || "").replace(/(^|[^.\w])text\(\)/g, "$1stateFile.text()") || null
  const failedLoadText = (stateBlock.match(/^    onLoadFailed: (?:\(error\) => )?(.*)$/m) || [])[1]
  const onLoaded = loadedText ? compile("", loadedText, "stateFile_onLoaded") : () => { throw new Error("service-harness: no stateFile onLoaded") }
  const onLoadFailed = failedLoadText ? compile("error", failedLoadText, "stateFile_onLoadFailed") : () => { throw new Error("service-harness: no stateFile onLoadFailed") }
  // One load of the file as it is NOW (the view reads what it loaded).
  h.loadState = () => {
    const r = h.stateFile.loadResult()
    h.stateFile.inLoad = true; h.stateFile.inHandler++
    try {
      if (r.loaded) { h.stateFile.view = r.text; onLoaded() } else onLoadFailed(r.error)
    } finally { h.stateFile.inLoad = false; h.stateFile.inHandler-- }
  }
  // stateFile.reload() is asynchronous: the load is queued, not run inline.
  h.stateFile.loader = () => h.later.push({ fn: h.loadState, args: [] })
  // R24c: a change made to the file by something else (a hand-run helper
  // verb, an editor, a restore). `change(stateFile)` makes it; the reload is
  // delivered only while the view's watch is armed -- in the fresh install's
  // dir-absent session, until something re-arms it, nothing is.
  //
  // F-HARNESS-31 (rule 10): the reload such a change raises is asked by the
  // service's own onFileChanged, and a reload asked while one of OUR writes
  // is out delivers no load during that write (measured, 30 of 30: lane W's
  // spikes/filewatch-links inflight-1.txt on lane-clean-w-probe, the
  // contract's eighth FileView fact). Our rename then replaces the change,
  // and the next load reads our own text: a change another program lands in
  // the same instant as one of our writes is LOST, on this double as on the
  // real view. Counted in `droppedForeign`, so a pin can see it happen.
  // Before this line the double delivered the change during our write and
  // the service merged it -- more forgiving than the FileView.
  h.droppedForeign = 0
  h.foreign = (change) => {
    change(h.stateFile)
    if (h.stateFile.watchArmed && h.stateFile.events.length) { h.droppedForeign++; return }
    if (h.stateFile.watchArmed) { h.loadState(); h.runLater() }
  }
  // R26c: the path REPLACED or RE-POINTED by something else -- a rename over
  // a link, `sed -i`, rm and cp, `ln -sfn` to another file or folder. The
  // view raises nothing and watches nothing from then on (measured), so no
  // load is delivered; the next reload() re-arms it.
  h.replace = (change) => {
    change(h.stateFile)
    h.stateFile.watchArmed = false
  }
  // R26a: the read-before-write's watchdog, from its own text, as if its 2 s
  // passed with no load (the reload the save asked for was never delivered).
  h.verifyWatchdog = () => { onVerifyWatchdog(); h.runLater() }
  // F4 (2026-10-16, lane-clean-f1): the watchdog's BOUND, observed. The
  // Timer's declared `interval` is evaluated from its own block in the
  // tree's Service.qml (Qt's default, 1000 ms, when the block declares
  // none; null when there is no such Timer), and h.elapse(ms) moves the
  // clock and fires it, through its own onTriggered, once a restart() is
  // that old and no stop() came after -- so a pin can see a read still
  // awaited at 1,999 ms and given up at 2,000. Nothing else here runs a
  // Timer; h.verifyWatchdog() above still fires it by hand.
  const verifyBlock = serviceText.indexOf("id: stateVerifyWatchdog") === -1 ? null
    : serviceText.slice(serviceText.lastIndexOf("  Timer {", serviceText.indexOf("id: stateVerifyWatchdog")), serviceText.indexOf("\n  }", serviceText.indexOf("id: stateVerifyWatchdog")))
  const verifyIntervalText = verifyBlock === null ? null : ((verifyBlock.match(/^    interval: (.*)$/m) || [])[1] || "1000")
  const vw = ids.stateVerifyWatchdog
  vw.interval = verifyIntervalText === null ? null : compile("", "return (" + verifyIntervalText + ")", "stateVerifyWatchdog_interval")()
  vw.armedAt = null
  vw.restart = function () { this.restarts++; this.running = true; this.armedAt = h.clock }
  vw.stop = function () { this.stops++; this.running = false; this.armedAt = null }
  // R27a: the write-wait watchdog the same way, from its own block.
  const waitAt = serviceText.indexOf("id: stateWriteWaitWatchdog")
  const waitBlock = waitAt === -1 ? null
    : serviceText.slice(serviceText.lastIndexOf("  Timer {", waitAt), serviceText.indexOf("\n  }", waitAt))
  const waitIntervalText = waitBlock === null ? null : ((waitBlock.match(/^    interval: (.*)$/m) || [])[1] || "1000")
  const waitTrigText = waitBlock === null ? null : (waitBlock.match(/^    onTriggered: (.*)$/m) || [])[1]
  const onWriteWaitWatchdog = waitTrigText ? compile("", waitTrigText, "stateWriteWaitWatchdog_onTriggered") : () => {}
  const ww = ids.stateWriteWaitWatchdog
  ww.interval = waitIntervalText === null ? null : compile("", "return (" + waitIntervalText + ")", "stateWriteWaitWatchdog_interval")()
  ww.armedAt = null
  ww.restart = function () { this.restarts++; this.running = true; this.armedAt = h.clock }
  ww.stop = function () { this.stops++; this.running = false; this.armedAt = null }
  h.writeWaitWatchdog = () => { onWriteWaitWatchdog(); h.runLater() }
  // Each Timer fires once its restart() is `interval` old, in the order they
  // come due; a handler that re-arms its Timer (R27a's second read) is due
  // again `interval` after the moment it fired.
  h.elapse = (ms) => {
    const end = h.clock + ms
    for (;;) {
      const due = [[vw, onVerifyWatchdog], [ww, onWriteWaitWatchdog]]
        .filter(([t]) => t.running && t.interval !== null && t.armedAt + t.interval <= end)
        .sort((a, b) => (a[0].armedAt + a[0].interval) - (b[0].armedAt + b[0].interval))
      if (!due.length) break
      const [t, fire] = due[0]
      h.clock = t.armedAt + t.interval
      t.running = false; t.armedAt = null
      fire(); h.runLater()
    }
    h.clock = end
  }
  // The start-up init's exit, with the double's reply and side effects.
  h.helperInit = (code) => {
    const out = helperInit(h.stateFile, code)
    h.stateInitStdout.text = out.reply
    return out
  }

  const BOUND = opts.bound || 400
  h.root = root
  h.runLater = () => {
    while (h.later.length) {
      if (++h.turns > BOUND) { h.later = []; throw new Error("LOOP: " + h.turns + " deferred calls, " + h.host.writes.length + " entry writes") }
      const e = h.later.shift()
      e.fn.apply(null, e.args)
    }
  }
  // Deliver one FileView event, then the own-write reload a `saved` raises
  // (onFileChanged -> reload -> onLoaded -> applyUserState).
  // `noLater`: deliver the event and STOP there, before anything it deferred
  // runs -- the shell dying in that window (the case R19d's owed mirror
  // cannot cover: the debt is paid one Qt.callLater after the landing).
  h.deliverOne = (o2) => {
    const ev = h.stateFile.events.shift()
    if (!ev) return false
    h.stateFile.view = ev.text
    if (ev.kind === "silent") {
      // R26c: the write landed and the view reported nothing; only the echo
      // its change raises, when the watch is armed.
      if (!h.stateFile.exists) h.stateFile.mode = 0o666 & ~h.stateFile.umask
      h.stateFile.disk = ev.text
      h.stateFile.exists = true
      if (h.stateFile.fault === "dangling-link") h.stateFile.fault = null
      if (o2 && o2.noLater) return true
      h.runLater()
      if (h.stateFile.ownEcho === "load" && h.stateFile.watchArmed) h.loadState()
      h.runLater()
      return true
    }
    if (ev.kind === "saved") {
      // R26c: a save that CREATES the file makes it 0666 & ~umask; one over
      // an existing file keeps its mode.
      if (!h.stateFile.exists) h.stateFile.mode = 0o666 & ~h.stateFile.umask
      h.stateFile.disk = ev.text
      // The rename made a file of OURS at the path, with the mode of the one
      // it replaced (FileView keeps an existing file's mode, S-02): a foreign
      // file becomes our 0000 file, a 0000 file stays one.
      h.stateFile.exists = true
      if (h.stateFile.fault === "file-foreign") h.stateFile.fault = "file-0000"
      // D-DOC-11: the save created the dangling link's target; it leads somewhere now.
      if (h.stateFile.fault === "dangling-link") h.stateFile.fault = null
      h.stateFile.inHandler++
      try { onSaved() } finally { h.stateFile.inHandler-- }
      if (o2 && o2.noLater) return true
      h.runLater()
      // The own-write reload (onFileChanged -> reload -> onLoaded), when the
      // view delivers one (R23g: sometimes; see StateFile) -- and never while
      // its watch is unarmed (R24c: the dir-absent session saw no echo).
      if (h.stateFile.ownEcho === "load" && h.stateFile.watchArmed) h.loadState()
    } else {
      h.stateFile.inHandler++
      try { onSaveFailed(1) } finally { h.stateFile.inHandler-- }
    }
    if (!(o2 && o2.noLater)) h.runLater()
    return true
  }
  // Bounded like runLater: a save whose own reload re-applies a failed load
  // and saves again (the pre-R22 load path over an unreadable file) is a
  // LOOP, reported as one, never a hang.
  h.drain = () => {
    h.runLater()
    while (h.deliverOne()) { if (++h.turns > BOUND) { h.stateFile.events = []; throw new Error("LOOP: " + h.turns + " state events, " + h.host.writes.length + " entry writes") } }
    h.runLater()
    return h
  }
  h.tick = (ms) => { h.clock += ms === undefined ? 1000 : ms }
  h.publish = () => { onHostSettingsChanged(); onSettingsChanged() }
  h.host.onPublish = () => { if (h.started) h.publish() }
  h.storedEntry = () => h.host.storedEntry()
  h.file = () => Model.parseState(h.stateFile.disk)
  // A helper process's exit, with its own status text.
  h.probeExit = (statusText) => { ids.sourceProbeProc.running = false; root.handleProbeExit(statusText); h.runLater() }
  h.STUBBED = STUBBED
  h.ids = ids
  // The start, in the order the shell makes it: `shell` arrives (a reconcile
  // that is a no-op until the state loads), the state file loads, the
  // helper's `state init` exits, and the queued events drain.
  root.shell = h.host
  h.started = true
  // Component.onCompleted's start-up check (R24d: mkdir and its bound start
  // together); a tree without it starts mkdir there and arms nothing yet.
  if (typeof root.startStartupCheck === "function") root.startStartupCheck()
  else ids.mkdirProc.running = true
  root.reconcile()
  // `beforeLoad(h)`: the start-up window before stateFile's first load --
  // what a guide opened at once meets (the round-5 lens's window).
  if (opts.beforeLoad) { opts.beforeLoad(h); h.runLater() }
  // The init's exit. `initCode` non-zero: the helper failed and printed
  // nothing. A chmod the init makes raises a reload, queued BEFORE the exit
  // is handled ("reload-first", the default) or after it ("exit-first"):
  // the inotify event and QProcess's finished signal race for real.
  // R24d: the start-up check's FIRST process. mkdir exits at once, unless a
  // test hangs it (`hangAt: "mkdir"`); its exit handler, from its own text,
  // starts the init.
  h.mkdirExit = () => {
    ids.mkdirProc.running = false
    onMkdirExited(0, 0)
    h.runLater()
  }
  // R23c / R24d / R24g: one of the two start-up processes never answers. The
  // watchdog fires only if the service ARMED it (a restart counted); its own
  // handler sends what it sends; the double then decides what dies: a TERM
  // ends the process unless `ignoreTerm`, and then the kill grace's own
  // handler runs only if the service armed IT, and only a KILL ends a
  // TERM-ignoring process. A process nothing ended stays running and its
  // exit is never delivered -- the hang, as it is for real. Returns what
  // happened, for the test to read.
  const hangOut = (p, exitIfDead) => {
    const watchArmed = ids.stateInitWatchdog.restarts > 0
    if (!watchArmed) return "hung (no watchdog armed)"
    const killsBefore = ids.stateInitKill.restarts
    onInitWatchdog()
    if (p.signals.indexOf(15) !== -1 && !h.ignoreTerm) { p.running = false; exitIfDead(15); return "terminated" }
    if (ids.stateInitKill.restarts === killsBefore) return "hung (no kill armed)"
    onInitKill()
    if (p.signals.indexOf(9) !== -1) { p.running = false; exitIfDead(9); return "killed" }
    return "hung (the kill was not sent)"
  }
  h.initExit = (o2) => {
    const io = Object.assign({ code: opts.initCode || 0, order: opts.initOrder || "reload-first", timeout: opts.initTimeout === true }, o2 || {})
    h.ignoreTerm = io.ignoreTerm === true
    if (io.timeout && io.hangAt === "mkdir") {
      // The mkdir itself hangs (a hung filesystem): the init is never reached.
      ids.mkdirProc.running = true
      h.hang = hangOut(ids.mkdirProc, (sig) => { onMkdirExited(sig, 1); h.runLater() })
      return
    }
    h.mkdirExit()
    if (io.timeout) {
      // R23c: the init never answers. It dies having printed nothing and
      // changed nothing, and QProcess reports the exit -- a signal death --
      // to the shipping exit handler.
      ids.stateInitProc.running = true
      h.stateInitStdout.text = ""
      h.hang = hangOut(ids.stateInitProc, (sig) => { onInitExited(sig, 1); h.runLater() })
      return
    }
    const out = h.helperInit(io.code)
    ids.stateInitProc.running = false
    if (out.raises && io.order === "reload-first") { h.loadState(); h.runLater() }
    onInitExited(io.code, 0)
    h.runLater()
    if (out.raises && io.order !== "reload-first") { h.loadState(); h.runLater() }
  }
  // `initFirst`: the init exits before the FileView's first load arrives.
  if (opts.initFirst && !opts.dirsLater) h.initExit()
  h.loadState()
  h.runLater()
  if (!opts.dirsLater && !opts.initFirst) h.initExit()
  if (!opts.holdEvents) h.drain()
  return h
}

// A shell restart over what the last one left: the host's stored entry and
// the state file's bytes, the clock running on.
function restartService(serviceText, Model, h, o) {
  return bootService(serviceText, Model, Object.assign({ entry: (() => { const e = clone(h.host.storedEntry()); delete e.id; return e })(),
                                                          stateText: h.stateFile.disk, host: h.host.mode, clock: h.clock + 60000 }, o || {}))
}

module.exports = { bootService, restartService, rootFunctions, rootProperties, matchBrace, STUBBED, PID, HELPER_EMPTY_STATE }
