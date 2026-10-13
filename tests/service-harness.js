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
  const proc = name => ({ name, running: false, command: [], environment: {}, signal() {} })
  const timer = name => ({ name, restart() {}, stop() {}, start() {}, running: false })
  const view = name => ({ name, reload() {}, text() { return "" }, setText() {} })
  return {
    stateFile: h.stateFile,
    stateInitProc: proc("stateInitProc"),
    sourceProbeProc: proc("sourceProbeProc"),
    configShieldProc: proc("configShieldProc"),
    logoFetchProc: proc("logoFetchProc"),
    cacheProc: proc("cacheProc"),
    failedProc: proc("failedProc"),
    probeWatchdog: timer("probeWatchdog"),
    switchTimeout: timer("switchTimeout"),
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
  queueCacheJob: "queues a cache-directory job for cacheProc; recorded in h.cacheJobs",
  runNextCacheJob: "drains cacheProc's queue",
  noteSessionOutcome: "the player session record; no part of the source state machine",
  markDeadSession: "the player session record",
  startCacheLayout: "the one-time cache migration; here the layout is current and the cache ready at once",
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
class StateFile {
  constructor(text) { this.disk = text; this.view = text; this.events = []; this.writeFails = false; this.coalesce = false }
  text() { return this.view }
  setText(text) {
    const ev = { kind: this.writeFails ? "saveFailed" : "saved", text }
    if (this.coalesce && this.events.length >= 2) this.events[this.events.length - 1] = ev
    else this.events.push(ev)
  }
  reload() {}
}

function bootService(serviceText, Model, o) {
  const opts = o || {}
  const h = { clock: opts.clock || 1760000000000, later: [], cacheJobs: [], signals: [], warnings: [], detached: [], turns: 0 }
  h.host = new Host(opts.entry, opts.host || "lag")
  h.stateFile = new StateFile(opts.stateText || "")
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
  root.queueCacheJob = (args) => h.cacheJobs.push(args)
  root.runNextCacheJob = () => {}
  root.noteSessionOutcome = () => {}
  root.markDeadSession = () => {}
  root.startCacheLayout = () => { root.cacheReady = true }
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
    if (ev.kind === "saved") {
      h.stateFile.disk = ev.text
      onSaved()
      if (o2 && o2.noLater) return true
      h.runLater()
      root.applyUserState(h.stateFile.text())
    } else {
      onSaveFailed(1)
    }
    if (!(o2 && o2.noLater)) h.runLater()
    return true
  }
  h.drain = () => { h.runLater(); while (h.deliverOne()) {} h.runLater(); return h }
  h.tick = (ms) => { h.clock += ms === undefined ? 1000 : ms }
  h.publish = () => { onHostSettingsChanged(); onSettingsChanged() }
  h.host.onPublish = () => { if (h.started) h.publish() }
  h.storedEntry = () => h.host.storedEntry()
  h.file = () => Model.parseState(h.stateFile.disk)
  // A helper process's exit, with its own status text.
  h.probeExit = (statusText) => { ids.sourceProbeProc.running = false; root.handleProbeExit(statusText); h.runLater() }
  h.STUBBED = STUBBED
  // The start, in the order the shell makes it: `shell` arrives (a reconcile
  // that is a no-op until the state loads), the state file loads, the
  // helper's `state init` exits, and the queued events drain.
  root.shell = h.host
  h.started = true
  root.reconcile()
  // `beforeLoad(h)`: the start-up window before stateFile's first load --
  // what a guide opened at once meets (the round-5 lens's window).
  if (opts.beforeLoad) { opts.beforeLoad(h); h.runLater() }
  root.applyUserState(h.stateFile.text())
  h.runLater()
  if (!opts.dirsLater) { onInitExited(0, 0); h.runLater() }
  h.initExit = () => { onInitExited(0, 0); h.runLater() }
  if (!opts.holdEvents) h.drain()
  return h
}

// A shell restart over what the last one left: the host's stored entry and
// the state file's bytes, the clock running on.
function restartService(serviceText, Model, h, o) {
  return bootService(serviceText, Model, Object.assign({ entry: (() => { const e = clone(h.host.storedEntry()); delete e.id; return e })(),
                                                          stateText: h.stateFile.disk, host: h.host.mode, clock: h.clock + 60000 }, o || {}))
}

module.exports = { bootService, restartService, rootFunctions, rootProperties, matchBrace, STUBBED, PID }
