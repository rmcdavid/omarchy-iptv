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
// folded per function the way Qt 6.12.0 was measured to fold it,
// F-HARNESS-130) and a clock. The root's
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
  // D-SRC-37 (c): and RECORDS its signals like the other process fakes; with
  // h.cacheHang true the helper never answers (a stalled cache directory),
  // which is the run the slot's watchdog exists for.
  const cacheProc = { name: "cacheProc", command: [], environment: {}, signals: [], signal(n) { this.signals.push(n) }, _running: false }
  Object.defineProperty(cacheProc, "running", {
    get() { return cacheProc._running },
    set(v) {
      cacheProc._running = v
      if (v === true) {
        // What the HELPER parses (helperView): since D-SINK-48 the keys ride
        // in the environment and the command names only the verb.
        const command = helperView(cacheProc.command, cacheProc.environment)
        h.cacheRuns.push(command)
        if (h.cacheHang) return
        h.later.push({ fn: () => { cacheProc._running = false; h.root.handleCacheExit(h.cacheAnswer(command)) }, args: [] })
      }
    }
  })
  // D-SINK-103: `state private` RUNS, as cacheProc does, because every write
  // of state.json now waits for its reply: setting `running` queues the
  // helper's work on the file as the double holds it (helperPrivate below,
  // the shipping helper's branches, pinned by tests/test_state.py's
  // StatePrivateTest), then the reload a chmod or a creation raises -- an
  // inotify event the view answers with reload(), asked BEFORE the exit is
  // handled, the order that leaves the shell the most to get wrong -- then
  // the exit, through Service.handleStatePrivateExit, the handler the real
  // Connections calls. `h.privateHang` leaves it running (a stalled
  // filesystem) for the watchdog; `h.privateAnswer()` replaces the helper's
  // answer ({ code, reply, raises }); h.privateExit() delivers a held exit.
  const statePrivateProc = { name: "statePrivateProc", command: [], environment: {}, signals: [], signal(n) { this.signals.push(n) }, _running: false }
  Object.defineProperty(statePrivateProc, "running", {
    get() { return statePrivateProc._running },
    set(v) {
      statePrivateProc._running = v
      if (v !== true) return
      h.privateRuns.push(statePrivateProc.command.slice())
      if (h.privateHang) return
      h.later.push({ fn: () => {
        if (!statePrivateProc._running) return
        const out = h.privateAnswer ? h.privateAnswer() : helperPrivate(h.stateFile)
        if (out.raises) h.stateFile.reload()
        h.later.push({ fn: () => { if (!statePrivateProc._running) return; statePrivateProc._running = false; h.root.handleStatePrivateExit(out.code, out.reply) }, args: [] })
      }, args: [] })
    }
  })
  // Timers do not run; restart() and stop() are COUNTED, so a test can see
  // that a watchdog was armed (R23c) without the harness running its clock.
  const timer = name => ({ name, restarts: 0, stops: 0, restart() { this.restarts++ }, stop() { this.stops++ }, start() {}, running: false })
  const view = name => ({ name, reload() {}, text() { return "" }, setText() {} })
  return {
    stateFile: h.stateFile,
    // D-HOST-16: the manifest's view (ManifestFile below), wired in bootService.
    manifestFile: h.manifestFile,
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
    whichProc: proc("whichProc"),
    // D-SRC-49: the `state mode` run after a landed save; its exit is
    // delivered by the test (h.stateModeExit), with the helper's own reply.
    stateModeProc: proc("stateModeProc"),
    // D-SINK-103: `state private` before every write; it runs (above).
    statePrivateProc,
    statePrivateWatchdog: timer("statePrivateWatchdog"),
    hyprWhichProc: proc("hyprWhichProc"),
    hyprInfoProc: proc("hyprInfoProc"),
    hyprInfoStdout: { text: "" },
    probeWatchdog: timer("probeWatchdog"),
    // D-SRC-37 (c): the bounds on the four slots that had none. Each is
    // driven from its own Timer block in the tree (interval and onTriggered)
    // by h.elapse, like the two R26a/R27a watchdogs below; a tree without the
    // block has a Timer that never fires, which is that tree.
    cacheWatchdog: timer("cacheWatchdog"),
    failedWatchdog: timer("failedWatchdog"),
    configShieldWatchdog: timer("configShieldWatchdog"),
    whichWatchdog: timer("whichWatchdog"),
    pipProbeWatchdog: timer("pipProbeWatchdog"),
    stateModeWatchdog: timer("stateModeWatchdog"),
    // D-REL-8: the one re-run of the start-up init, driven from its block.
    stateInitRetry: timer("stateInitRetry"),
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
    // D-PLY-66: the relay question's slot and its bound. The process does
    // not run: a test delivers its exit through Service.handleRelayAnswer
    // with the helper's own reply text, and h.fireTimer runs the watchdog's
    // own onTriggered.
    relayAskProc: proc("relayAskProc"),
    relayAskWatchdog: timer("relayAskWatchdog"),
    // D-PLY-30: the player slot's four timers, which handlePlayerResult
    // stops or restarts; a test runs that handler to see what a refused
    // `player start` tells the user. Counted like every timer; the watchdog
    // is driven from its own block by h.elapse since D-PLY-35 (below).
    playerWatchdog: timer("playerWatchdog"),
    playerSocketTimer: timer("playerSocketTimer"),
    playRetryTimer: timer("playRetryTimer"),
    relaunchTimer: timer("relaunchTimer"),
    // D-PLY-32: the socket observer's Component (ARCHITECTURE-PLAYER 13), so
    // a test can run handlePlayerResult's OK branch, which arms it. Each
    // createObject() is a fresh Socket, counted in h.socketsMade. No mpv runs
    // here, so a connect finds nothing listening and `connected` stays false
    // when set, which is what Quickshell's Socket does on a failed connect
    // (docs/SPIKE-QUICKSHELL-SOCKET.md, C5) -- never more forgiving than it
    // (rule 10). There is deliberately no switch that makes the connect
    // succeed: on the real Socket a success runs onConnectionStateChanged,
    // and so onPlayerAttached, synchronously inside the assignment (C4),
    // which this double does not do -- a `connected` reading true here would
    // be a half-attached player no real shell can be in. (The first version
    // had such a switch, `h.socketListening`, that no test set; the recheck
    // of lane-ply32 removed it.)
    // D-PLY-69 (2026-11-21): one opt-in exception that is not that switch.
    // A test that models the helper and its players (tests/player-world.js)
    // sets `h.socketWorld`, and each fresh object is that world's socket: it
    // connects only while the world has a live player bound to the path, and
    // its connect and its peer's close run the Component's OWN
    // onConnectionStateChanged, compiled from the tree's text
    // (h.socketChanged below), synchronously inside the assignment as the
    // real Socket does (C4) -- so an attached observer here is one the shell
    // attached itself, never one a test stood in.
    // D-PLY-32: and what the socket's EOF (handlePlayerGone) stops on its way
    // to the failure report: the player slot (asked whether a start is in
    // flight; nothing runs), the focus retry, the stop backstop and PiP's two
    // bounds. Counted like every timer here, never run.
    playerProc: proc("playerProc"),
    // the control slot, which the rewind's clear asks whether a seek is in
    // flight (clearRewind -> applySeekPlan); nothing runs on it here.
    controlProc: proc("controlProc"),
    // and the seek throttle the same clear stops (applySeekPlan).
    seekThrottle: timer("seekThrottle"),
    focusTimer: timer("focusTimer"),
    stopSettleTimer: timer("stopSettleTimer"),
    // The review of 9d604cf: the stop's early look (F-PLY-3). Counted, and
    // driven only by a check that asks (h.driveTimer), as the backstop is.
    stopLookTimer: timer("stopLookTimer"),
    pipSequenceWatchdog: timer("pipSequenceWatchdog"),
    pipStepWatchdog: timer("pipStepWatchdog"),
    // D-PLY-35: what the reattach probe's answer reaches through applyProbe,
    // which a start the watchdog stopped now asks: the one ambiguous-probe
    // re-read (counted; a test sends the second probe itself), and the PiP
    // read the adoption makes of a pid it did not have (pipPeek), which
    // nothing here answers -- the compositor's reply is not this harness's.
    probeRetryTimer: timer("probeRetryTimer"),
    // Restart on adoption: the hold over a player another build launched,
    // driven from its own Timer block by h.elapse (a tree without the block
    // has a Timer that never comes due, which is that tree).
    olderRestartTimer: timer("olderRestartTimer"),
    hyprPeekProc: proc("hyprPeekProc"),
    pipPeekWatchdog: timer("pipPeekWatchdog"),
    // D-HOST-11: `import qs.Commons as Commons`, the one member Service.qml
    // reads -- the host kit's Util.barSections, as the double's host declares
    // it (undefined on the 4.0.x kit, as Util has no such property there).
    Commons: { Util: { get barSections() { return h.host.barSections } } },
    playerSocketComponent: {
      createObject() {
        h.socketsMade = (h.socketsMade || 0) + 1
        if (h.socketWorld) return h.socketWorld.socket()
        return {
          get connected() { return false },
          set connected(v) {},
          write() {}, destroy() {}
        }
      }
    },
    // D-HOST-5: one notice post per object (Service.runNotify). Setting
    // `running` records the argv in h.detached -- the notification sink every
    // check before D-HOST-5 reads, which saw execDetached's argv the same way
    // -- and in h.notifyRuns, and asks h.notifyServer for the answer; the
    // exit is delivered asynchronously, as a Process's is, through the shell's
    // own handleNotifyExit. With no server (the default: what a scenario's
    // logging stub and a desktop with no notification daemon both are) the
    // wrapper fails: exit 1, nothing on stdout. h.notifyHang leaves a post
    // running until something ends it; a TERM ends it (signal exit, no
    // stdout), as it ends the wrapper's bash. The `guard` Timer and the exit
    // Connections inside the Component are QML glue this double replaces:
    // a test fires the guard by calling root.notifyOverdue(run).
    notifyComponent: {
      createObject(parent, props) {
        const run = { kind: String((props && props.kind) || ""), command: [], signals: [], destroyed: false, _running: false,
                      signal(n) {
                        this.signals.push(n)
                        if (!this._running || n !== 15) return
                        this._running = false
                        h.later.push({ fn: () => h.root.handleNotifyExit(run, run.kind, 15, 1, ""), args: [] })
                      },
                      destroy() { this.destroyed = true } }
        Object.defineProperty(run, "running", {
          get() { return run._running },
          set(v) {
            if (v !== true || run._running) return
            run._running = true
            const argv = run.command.slice()
            h.detached.push(argv)
            h.notifyRuns.push(run)
            NOTICE_LEDGER.slotted[run.kind] = (NOTICE_LEDGER.slotted[run.kind] || 0) + 1
            if (h.notifyHang) return
            const answer = h.notifyServer ? h.notifyServer.post(argv) : { code: 1, text: "" }
            h.later.push({ fn: () => { if (!run._running) return; run._running = false; h.root.handleNotifyExit(run, run.kind, answer.code, 0, answer.text) }, args: [] })
          }
        })
        return run
      }
    },
    configShieldDebounce: timer("configShieldDebounce"),
    // D-EPG-11 (R31b): the guide-data load is observed -- applyEpgNow runs
    // for real over both file shapes -- and these three are what a fetch
    // decided by it would touch (refreshEpg restarts the debounce; the run
    // itself would set the process running). Counted, never run, like every
    // other timer and process here.
    epgProc: proc("epgProc"),
    epgDebounce: timer("epgDebounce"),
    // D-SINK-41: what a playlist refresh decided at freshness restarts
    // (refreshPlaylist); counted, never run, like the EPG's debounce.
    refreshDebounce: timer("refreshDebounce"),
    epgWatchdog: timer("epgWatchdog"),
    epgFile: view("epgFile"),
    channelsFile: view("channelsFile"),
    playlistStatusFile: view("playlistStatusFile"),
    // execDetached is the notification sink (Service.notify) on a tree from
    // before D-HOST-5, and the fallback after it: recorded as the argv the
    // shell would run, never run (R21b's report is observed here). A
    // notification posted this way still reaches h.notifyServer when a test
    // set one -- detached is how it was sent, not whether it arrived -- and
    // its stdout goes nowhere, so nothing reads the id it was given.
    // D-PLY-64 (2026-11-06): ONLY the command list. Quickshell 0.3.2's
    // execDetached also declares a ProcessContext overload, but a plain JS
    // object { command, environment } handed to it is refused -- "Could not
    // convert argument 0 from [object Object] to qs::io::process::
    // ProcessContext", a TypeError, and nothing runs (measured 2026-11-06 in
    // an offscreen quickshell) -- so this double refuses it the same way
    // (rule 10: a double that ran it hid an orphan check that never starts).
    // h.detached keeps the command -- what /proc shows -- and h.detachedRuns
    // each run's command and what the helper parses (helperView, which throws
    // on a flag with no list, as the helper refuses one).
    // env: a name the test sets answers its string; any other name answers
    // null, as Quickshell 0.3.2 answers an unset variable (measured
    // offscreen, 2026-11-27; F-HARNESS-133). It answered "" until then,
    // which let D-PIP-8's `=== ""` guard pass here and fail on the host.
    Quickshell: { env(name) { return h.env && Object.prototype.hasOwnProperty.call(h.env, name) && typeof h.env[name] === "string" ? h.env[name] : null }, execDetached(context) {
      if (!Array.isArray(context) || context.length === 0) throw new TypeError("Passing incompatible arguments to C++ functions from JavaScript is not allowed (execDetached takes a command list; a { command, environment } object is refused, measured on Quickshell 0.3.2)")
      const ctx = { command: context, environment: {} }
      const argv = ctx.command.map(String)
      const environment = Object.assign({}, ctx.environment || {})
      h.detachedRuns.push({ command: argv.slice(), environment, parsed: helperView(argv, environment) })
      h.detached.push(argv.slice())
      if (argv[0] !== "omarchy-notification-send") return
      if (h.notifyServer) h.notifyServer.post(argv.slice())
      // The rule-15 ledger (D-HOST-5): a notice sent past the kind's slot. A
      // test that drives the fallback on purpose declares it first.
      if (h.allowDetachedNotice > 0) h.allowDetachedNotice--
      else NOTICE_LEDGER.detached.push(argv[argv.indexOf("-r") + 1] + " " + argv[argv.length - 2])
    } }
  }
}

// D-SINK-47, D-SINK-48 (lane-p2a, 2026-10-29): the helper's own reading of a
// spawn, for the doubles that answer as the helper would. A command carrying
// `--args-from-env` is the command without it, followed by the JSON list in
// OMARCHY_IPTV_ARGS -- helper_arguments in bin/helper/11-cli.py, pinned to
// this function by tests/fixtures/helper-args.json in both suites. Never more
// forgiving than the helper (rule 10): a flag with no list, or a list that is
// not strings, is a run that does not happen, here as there.
function helperView(command, environment) {
  const c = (command || []).map(String)
  const at = c.indexOf("--args-from-env")
  if (at === -1) return c
  if (c.indexOf("--args-from-env", at + 1) !== -1) throw new Error("service-harness: --args-from-env twice")
  const raw = environment && Object.prototype.hasOwnProperty.call(environment, "OMARCHY_IPTV_ARGS") ? environment.OMARCHY_IPTV_ARGS : null
  if (raw === null) throw new Error("service-harness: --args-from-env with no OMARCHY_IPTV_ARGS")
  const list = JSON.parse(raw)
  if (!Array.isArray(list) || list.some(x => typeof x !== "string" || x.indexOf("\0") !== -1)) throw new Error("service-harness: OMARCHY_IPTV_ARGS is not a list of strings")
  return c.slice(0, at).concat(c.slice(at + 1)).concat(list)
}

// The verb of a recorded `cache` run: the first word after `cache` that is
// neither an option nor an option's value. Index-free, because the
// interpreter's argv grew `-I` (D-SINK-50, 2026-10-29) and read `--cache-dir`
// plus two before that.
function cacheVerb(command) {
  const c = command || []
  let i = c.indexOf("cache") + 1
  if (i <= 0) return ""
  while (i < c.length && String(c[i]).indexOf("--") === 0) i += String(c[i]).indexOf("=") === -1 ? 2 : 1
  return i < c.length ? String(c[i]) : ""
}

// D-HOST-5, rule 15: every notice any service boot in this process posted,
// across the whole suite -- through a kind's slot (by kind), or detached past
// it. tests/Model.test.js reads it last: the tree must post every kind, and
// nothing detached but what a test declared (h.allowDetachedNotice).
const NOTICE_LEDGER = { slotted: Object.create(null), detached: [] }

// What the harness does not run, and why. Each is a QML-side effect with no
// say in what the bar entry or state.json end up holding.
const STUBBED = {
  runConfigShield: "starts the D-SINK-18 shield process; the file is taken as private (hostConfigShield below)",
  noteSessionOutcome: "the player session record; no part of the source state machine",
  markDeadSession: "the player session record",
  // schedulePrune and queuePrune RUN since D-LOGO-20 (R32f): a prune is a
  // cache job, recorded in h.cacheRuns like migrate and remove, so a pin can
  // see the start-up prune once and the switch prune on every switch.
  // clearSourceData RUNS since F-M3-18 (a) (2026-10-24): it is the reset of
  // every per-source property on a switch, and the no-op that stood here is
  // why the node suite stayed green while the logo slots blanked (the three
  // Service.qml-only decisions of D-LOGO-11's review had nothing that could
  // redden off-display).
  fetchLogos: "starts the logo fetch",
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
    let end = scan(text, start, true)
    // A binding continued on the next line by a ternary's `?` or `:` is ONE
    // expression (the shape `activeCacheDir` and `failedPath` take). The
    // scanner stopped at the first newline and compiled only the first
    // line, so `activeCacheDir` read as true or false here, equal across
    // every switch, and nothing keyed on it could be seen to change -- found
    // pinning D-LOGO-20 (R32f), rule 10: a double was more forgiving than
    // the binding it stood for.
    for (;;) {
      const nextEnd = text.indexOf("\n", end + 1)
      if (!/^[ \t]*[?:]/.test(text.slice(end + 1, nextEnd === -1 ? text.length : nextEnd))) break
      end = scan(text, end + 1, true)
    }
    out.push({ readonly: !!m[1], type: m[2], name: m[3], expr: text.slice(start, end), block: false })
  }
  return out
}

// F-SINK-16 (2026-10-29): the IpcHandler's verbs, `    function name(...)`
// inside the root's one `  IpcHandler {` block. What one of them returns is
// what `omarchy-shell ipc call` prints into the caller's terminal, so a test
// reads a reply off the shipping verb (h.ipc.status()) rather than
// recomposing it from the functions the verb calls -- which is how a verb
// that kept JSON.stringify while its neighbours moved would go unseen. The
// QML type annotations (`n: string`, `): string`) are not JavaScript and are
// stripped; nothing else is. A tree without the block has no verbs here.
function ipcFunctions(text) {
  const out = {}
  const at = text.search(/^  IpcHandler \{/m)
  if (at === -1) return out
  const open = text.indexOf("{", at)
  const close = matchBrace(text, open)
  if (close === -1) throw new Error("service-harness: cannot find the end of the IpcHandler block")
  const block = text.slice(open + 1, close)
  const re = /^    function ([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\)(?:: *[A-Za-z]+)? \{/gm
  let m
  while ((m = re.exec(block)) !== null) {
    const fopen = m.index + m[0].length - 1
    const fclose = matchBrace(block, fopen)
    if (fclose === -1) throw new Error("service-harness: cannot find the end of the IPC verb " + m[1])
    const args = m[2].split(",").map(a => a.replace(/:.*$/, "").trim()).filter(a => a !== "").join(", ")
    out[m[1]] = { args, body: block.slice(fopen + 1, fclose) }
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

// What a binding's value becomes in a property of `type`, where the double
// knows: a `string` property bound to null reads "" (measured on Quickshell
// 0.3.2 offscreen, 2026-11-27: a `readonly property string` bound to
// Quickshell.env(<unset>) read "", typeof string, with no warning). Since
// F-HARNESS-133 the double's Quickshell.env answers null for an unset name,
// as the host does, so Service.qml's `home` needs this to read as it does
// there. A plain property's initial binding goes through it too, read as
// the same assignment and not measured. Nothing else is converted,
// undefined included: no other case was measured.
function bindingValue(type, v) {
  return type === "string" && v === null ? "" : v
}

const PID = "io.github.rmcdavid.iptv"
const clone = x => JSON.parse(JSON.stringify(x))

// F-HARNESS-100 / D-HOST-11 (2026-11-06). The host's bar sections, read
// from the INSTALLED host's own Commons/Util.qml -- the array literal on its
// `readonly property var barSections:` line -- so the double's kit is the
// machine's and a host that adds a section changes it here too (rule 13: the
// join is a read of the host's file, not a copy of its list). undefined for
// a Util.qml that declares none, which is 4.0.x.
const fs = require("fs")
const path = require("path")
// D-REL-14: the service's readers, which judge a file set before it boots.
const serviceReader = require("./service-files.js")
const HarnessLib = require(path.join(__dirname, "../scripts/dev-harness/harness-lib.js"))
const HOST_SHELL = "/usr/share/omarchy/shell"
function hostBarSections(utilText) {
  const m = /^\s*readonly property var barSections:\s*(\[[^\]\n]*\])\s*$/m.exec(String(utilText || ""))
  if (!m) return undefined
  const list = JSON.parse(m[1])
  if (!Array.isArray(list) || list.some(s => typeof s !== "string")) throw new Error("service-harness: Util.qml's barSections is not a list of names: " + m[1])
  return list
}
const INSTALLED_BAR_SECTIONS = hostBarSections(fs.readFileSync(path.join(HOST_SHELL, "Commons", "Util.qml"), "utf8"))

// F-HARNESS-136 (2026-11-28). The bar config in the form a FRESH
// PluginShellApi carries it (D-HOST-15): createObject's property map hands
// the service Qt's own wrappers, a V4ReferenceObject for the config, the
// layout and each entry and a V4Sequence for each section, until the host's
// next syncPluginApis assigns a parsed copy. These doubles are those wrappers
// as lane-dh15m measured them in the host's own shell.qml and NOTHING MORE
// (rule 10): every operation the measurement did not see answered throws.
// tests/Model.test.js ("D-HOST-15 (the doubles, rule 10)") pins what they
// answer and holds the account of the measurement. They were that block's
// own; they are here so bootService can start EVERY service in this form
// (Host's `fresh`), where only one hand-swapped check met the window.
const V4 = (function () {
  const refuse = (what, key) => { throw new Error("V4 double: " + what + " " + String(key) + " was not measured") }
  const own = (o, k) => typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k)
  // A V4ReferenceObject over `fields`. `absent` says whether a key it lacks
  // reads as undefined (the layout: tray was read so) or throws. `proto`,
  // another such double, is its prototype: a read the wrapper lacks goes on
  // to it, and for...in walks it (protoForm below).
  const fieldsOf = new WeakMap()
  // A wrapper with no `proto` answers its prototype as V4 answered a plain
  // entry's (qmltestrunner on Qt 6.12.0, lane-dh15fix2's probe, `map:normal`):
  // an object that is NOT Object.prototype, whose tag is [object Object] and
  // which has no own name -- where this double first answered Object.prototype
  // itself, kinder than V4 to a plainness test (the second code recheck).
  const refObject = (fields, absent, proto) => {
    let staged = null, listing = null, json = false
    const standIn = Object.create(Object.prototype)
    const lends = key => proto !== undefined && own(fieldsOf.get(proto), key)
    const wrapper = new Proxy({}, {
      get(t, key) {
        if (key === Symbol.toStringTag) return "V4ReferenceObject"
        // JSON.stringify's first ask of an object; what it asks next is
        // answered only after it.
        if (key === "toJSON") { json = true; return own(fields, key) ? fields[key] : undefined }
        if (own(fields, key)) return fields[key]
        if (lends(key)) return proto[key]
        if (absent === true && typeof key === "string") return undefined
        return refuse("a read of", key)
      },
      ownKeys() {
        const keys = Object.keys(fields)
        if (json) { json = false; listing = keys.length ? keys.slice() : null } else staged = keys
        return keys.slice()
      },
      getPrototypeOf() {
        if (staged !== null) { listing = staged.length ? staged : null; staged = null }
        return proto !== undefined ? proto : standIn
      },
      getOwnPropertyDescriptor(t, key) {
        if (listing !== null && listing[0] === key) {
          listing.shift()
          if (listing.length === 0) listing = null
          return { value: fields[key], writable: true, enumerable: true, configurable: true }
        }
        // for...in then asks whether the wrapper shadows each key its
        // prototype lends (protoForm's, or a polluted Object.prototype's):
        // it does not.
        if (!own(fields, key) && (lends(key) || (typeof key === "string" && Object.prototype.propertyIsEnumerable.call(Object.prototype, key)))) return undefined
        staged = null
        return refuse("a property descriptor (hasOwnProperty, Object.keys) of", key)
      },
      has(t, key) { return refuse("`in` of", key) },
      set(t, key) { return refuse("a write of", key) },
      defineProperty(t, key) { return refuse("a define of", key) },
      deleteProperty(t, key) { return refuse("a delete of", key) }
    })
    fieldsOf.set(wrapper, fields)
    return wrapper
  }
  // An entry whose shell.json text holds a `__proto__` key, as V4 makes it
  // when it crosses createObject's property map (qmltestrunner on Qt 6.12.0,
  // the host's Qt, lane-dh15fix2's probe, 2026-11-27): a wrapper with NO own
  // field -- Object.keys and getOwnPropertyNames empty, JSON.stringify `{}`
  // -- whose prototype, another V4ReferenceObject, holds the entry's fields
  // merged with the nested object's. `{"id":<ours>,"__proto__":{"polluted":
  // true,"id":"x"},"maxRecents":25}` read id (ours), polluted (true) and
  // maxRecents (25) through it, for...in listing them in that order;
  // `{"__proto__":{"id":<ours>},"maxRecents":5}` read our id and 5. The
  // Array form (after syncPluginApis' JSON.parse) holds `__proto__` as an
  // own key instead and reads neither the nested fields nor a nested id.
  const protoForm = (merged) => refObject({}, false, refObject(merged))
  // A V4Sequence over `items`.
  const sequence = (items) => {
    const n = items.length
    const at = key => typeof key === "string" && /^(0|[1-9][0-9]*)$/.test(key) ? Number(key) : -1
    return new Proxy({}, {
      get(t, key) {
        if (key === Symbol.toStringTag) return "V4Sequence"
        if (key === "length") return n
        if (key === Symbol.iterator) return function* () { for (let i = 0; i < n; i++) yield items[i] }
        const i = at(key)
        if (i >= 0 && i < n) return items[i]
        return refuse("a read of", key)
      },
      // Array.prototype.slice.call asks HasProperty of each index below the length.
      has(t, key) { const i = at(key); return i >= 0 && i < n ? true : refuse("`in` of", key) },
      ownKeys() { return refuse("the keys of", "a sequence") },
      getOwnPropertyDescriptor(t, key) { return refuse("a property descriptor of", key) },
      set(t, key) { return refuse("a write of", key) },
      defineProperty(t, key) { return refuse("a define of", key) },
      deleteProperty(t, key) { return refuse("a delete of", key) }
    })
  }
  // A plain bar config as createObject's property map leaves it.
  const fresh = (bar) => {
    const layout = {}
    for (const s of Object.keys(bar.layout || {})) {
      const list = bar.layout[s]
      layout[s] = Array.isArray(list) ? sequence(list.map(e => e && typeof e === "object" ? refObject(Object.assign({}, e)) : e)) : list
    }
    return refObject({ layout: refObject(layout, true) })
  }
  return { refObject, protoForm, sequence, fresh }
})()

// The host, both shapes rule 9 names: "lag" publishes the bar one write
// behind (through 4.0.4), "echo" at once (omacom/omarchy#15082).
//
// F-HARNESS-100: and both host KITS. `kit.barSections` is what the plugin
// reads as Commons.Util.barSections (default: the installed host's list;
// pass undefined for 4.0.x), and the host walks HarnessLib.hostSections of
// it -- the list, or 4.0.x's three. `kit.section` is where the entry sits
// (default "right", where every earlier test put it), `kit.bare` makes it the
// bare-string entry a hand-written shell.json can hold (`omarchy plugin
// enable` writes an `{id}` object). updateEntryInline is
// HarnessLib.hostUpdateEntry, the mirror the dev harness's fake shell runs
// too, held to the installed host's own text by tests/Model.test.js. The
// double used to write `right[0]` and nothing else.
// IPTV_HARNESS_FRESH chooses the form for a whole run, as an option does for
// one boot: "load" (the default), "creation", or "none" for false.
function freshDefault() {
  const v = process.env.IPTV_HARNESS_FRESH
  return v === undefined || v === "" ? "load" : v === "none" ? false : v
}
class Host {
  constructor(entry, mode, kit) {
    const k = kit || {}
    this.mode = mode
    this.barSections = Object.prototype.hasOwnProperty.call(k, "barSections") ? k.barSections : INSTALLED_BAR_SECTIONS
    this.sections = HarnessLib.hostSections(this.barSections)
    this.section = k.section || "right"
    const layout = {}
    for (const s of this.sections) layout[s] = []
    if (!layout[this.section]) layout[this.section] = []
    layout[this.section].push(k.bare === true ? PID : Object.assign({ id: PID }, entry || {}))
    this.stored = { bar: { layout }, plugins: [] }
    this.published = clone(this.stored.bar)
    // F-HARNESS-136: what a service reads between its creation and the
    // host's next syncPluginApis. "load" (the default): the fresh API's
    // wrappers until the host's first assign, so the state load falls in
    // the window (D-HOST-15's worst case, and the form that sees a reading
    // go wrong: a sequence read as absent turned 186 checks red here and 11
    // in the Array form, 2026-11-28). "creation": the wrappers until
    // bootService's sync, before the state load, the order the host was
    // measured to keep; the gate's second node run boots this way. false:
    // the Array form from the start, which no service on a 4.5.0 host meets.
    this.fresh = k.fresh === undefined ? freshDefault() : k.fresh
    this.syncs = 0
    if (this.fresh !== false && this.fresh !== "creation" && this.fresh !== "load") throw new Error("service-harness: fresh takes \"creation\", \"load\" or false")
    if (this.fresh !== false) this.published = V4.fresh(this.published)
    this.onPublish = null
    this.writes = []
    this.answers = []
  }
  get barConfig() { return this.published }
  // syncPluginApis with nothing stored anew: the parsed copy replaces the
  // fresh API's wrappers and the bar config's change is raised.
  sync() {
    this.syncs++
    this.published = clone(this.stored.bar)
    if (this.onPublish) this.onPublish()
  }
  // The entry as stored, wherever it was placed -- also in a section this
  // host does not walk (an entry 4.5.0's migration moved, on 4.0.x).
  storedEntry() {
    const arr = this.stored.bar.layout[this.section] || []
    return arr.find(e => e === PID || (e && typeof e === "object" && e.id === PID))
  }
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
    const copy = HarnessLib.hostUpdateEntry(this.stored, this.sections, id, settings)
    if (copy === null) { this.answers.push(false); return false }
    this.answers.push(true)
    this.assign(copy)
    return true
  }
  // `omarchy bar set`: a foreign write, which the lagging host flushes with
  // the write after it -- modelled, as the driver does, by publishing twice.
  // F-HARNESS-100: PluginRegistry.setBarWidget through mutateShellConfig
  // (HarnessLib.hostSetBarWidget): the first entry in the host's sections
  // with our id takes the key, an object entry only, and the shaped copy is
  // persisted either way. `null` removes the key (a hand edit). -> whether
  // the widget took it.
  externalSet(key, value) {
    const r = HarnessLib.hostSetBarWidget(this.stored, this.sections, PID, key, value === null ? undefined : value)
    this.assign(r.config)
    if (this.mode === "lag") this.assign(r.config)
    return r.error === ""
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
    // D-SRC-39 (rule 10): a PER-WRITE failure, `failWhen(text) -> bool`, so a
    // burst can land its first write and fail a later one; `writeFails`
    // stays the switch for every write.
    this.failWhen = null
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
    const fails = this.writeFails || blocksWrite || (typeof this.failWhen === "function" && this.failWhen(text) === true)
    const ev = { kind: fails ? "saveFailed" : (this.inLoad ? "silent" : "saved"), text }
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

// D-HOST-16: the manifest's FileView (manifestFile), built the way stateFile's
// double is and never more forgiving than Quickshell's FileView (rule 10).
// What it models, read in the installed /usr/lib/qt6/qml/Quickshell/Io/
// FileView.qml and quickshell-io.qmltypes and measured on stateFile (the
// contract's FileView facts, docs/OMARCHY-PLUGIN-CONTRACT.md):
//   the view is made       one load is queued: the wrapper's `preload` is
//                          true unless set, and with `blockLoading` unset the
//                          read is asynchronous, so it lands later, never
//                          inside the creation
//   reload()               queues a load, never runs one inline; the load
//                          reads the file as it is when it is DELIVERED, and
//                          re-arms the watch when there is a file (the
//                          fourth and eighth facts)
//   a load                 `loaded` with the text, or `loadFailed` 2
//                          (FileNotFound) for a missing file (the fifth
//                          fact's table), through the tree's own onLoaded /
//                          onLoadFailed, compiled from their text
//   an in-place edit       (h.manifestEdit) raises `fileChanged`, queued,
//                          and only while the block declares `watchChanges:
//                          true` and the watch is armed; the view then runs
//                          the tree's onFileChanged and NOTHING else. The
//                          wrapper declares no handler of its own, so a tree
//                          without one reads nothing (whether the C++ view
//                          would reload by itself is not measured; a double
//                          that does not is the less forgiving of the two)
//   a replacement          (assigning h.manifestDisk) raises nothing and
//                          leaves the view watching nothing until a reload
//                          re-arms it (the eighth fact, R26c, measured on a
//                          LINKED state.json). D-DOC-39: it is NOT what the
//                          real view did at git's update, where the watch
//                          fired and its reload read the new file (L3's
//                          caged arms, 2026-11-25). The double stays the
//                          silent one on purpose: it is the less forgiving
//                          of the two, so a boot that reads the new version
//                          after it proves the hand-off or the re-read, and
//                          h.manifestEdit is the arm where the watch fires
// `disk` is the file's text, null for no file.
class ManifestFile {
  constructor(text) {
    this.disk = text
    this.view = ""
    this.watching = false
    this.armed = true
    this.loader = null
    this.loads = 0
    this.reloads = 0
  }
  text() { return this.view }
  reload() {
    this.reloads++
    if (this.disk !== null) this.armed = true
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
//   `empty` (D-REL-8) exit 0, nothing printed, nothing changed: the EMPTY
//                   stub git leaves for milliseconds mid-update (measured
//                   with inotify, 2026-10-17; the rewrite is delete, create,
//                   write in place)
function helperInit(file, code, empty) {
  if (empty === true) return { reply: "", raises: false }
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

// D-SINK-103: the REAL helper's `state private`, as a double that is not more
// forgiving than it (rule 10) -- each branch is state_private's in
// bin/helper/10-state.py, pinned by tests/test_state.py's StatePrivateTest:
//   a regular file of ours  made 0600 when it is not ("changed": a chmod,
//                           which raises a reload while the view watches),
//                           else "kept" (no chmod, nothing raised)
//   nothing there, or a     CREATED 0600 and EMPTY ("created"), which a
//   link whose target's     watching view sees as a change (sequence U: a
//   folder exists           missing file that appears reloads)
//   "file-0000"             ours: made 0600 ("changed"), readable again
//   "dir-0000"              unreachable: the run leaves every folder as it
//                           is, and an O_PATH open through a 0000 folder fails
//   "is-dir"                refused, not-a-file
//   "file-foreign"          refused, not-owned
//   "dir-foreign",          refused, unreachable (the open fails)
//   "dangling-link-nodir",
//   "not-a-dir"
//   "folder-link"           refused by the folder-link check, with no `why`
// A refusal is exit 1 and changes nothing.
function helperPrivate(file) {
  const line = o => JSON.stringify(o) + "\n"
  const refuse = why => ({ code: 1, raises: false, reply: line({ ok: false, kind: "state", error: { code: "state_not_private", message: "state.json ...; nothing may be written to it" }, why, action: "private" }) })
  if (file.fault === "is-dir") return refuse("not-a-file")
  if (file.fault === "file-foreign") return refuse("not-owned")
  if (file.fault === "dir-0000" || file.fault === "dir-foreign" || file.fault === "dangling-link-nodir" || file.fault === "not-a-dir") return refuse("unreachable")
  if (file.fault === "folder-link") return { code: 1, raises: false, reply: line({ ok: false, kind: "state", error: { code: "state_unreadable", message: "the state folder is a symbolic link whose target is missing or is not a folder; nothing was written" }, action: "private" }) }
  let how = "kept", raises = false
  if (!file.exists || file.fault === "dangling-link") {
    file.exists = true; file.disk = ""; file.mode = 0o600; file.dirAbsent = false
    if (file.fault === "dangling-link") file.fault = null
    how = "created"; raises = file.watchArmed
  } else if (file.fault === "file-0000" || file.mode !== 0o600) {
    if (file.fault === "file-0000") file.fault = null
    file.mode = 0o600
    how = "changed"; raises = file.watchArmed
  }
  return { code: 0, raises, reply: line({ ok: true, kind: "state", action: "private", file: how }) }
}

// D-REL-14 C2: the service bootService runs is a FILE SET, as the engine loads
// it -- { service: Service.qml's own text, files: each code-behind's text by
// name }, what tests/service-files.js's serviceSet(where) returns -- or, as
// before the split, one string: Service.qml's text, or its inline view. The
// readers judge it first, and what they refuse is refused here (rule 10: a
// split the shell would not load does not boot either): a string that still
// declares a code-behind is a split Service.qml without its files, refused
// as `missing`. Then each code-behind's functions are compiled, in the SAME
// scope as the root's, into the object its qualifier names (extras[Q]), and
// Service.qml's own functions -- the forwarders among them -- onto the root,
// as before. So what runs is the forwarder and the code-behind, not their
// inline view: a forwarder is called as the shell calls it, and STUBBED and
// unstub act on the root's member, the forwarder, as they always did. What
// only scripts/split-service.py --check refuses beyond the readers (a
// code-behind naming its own function unqualified, among others) still
// boots here, and reads otherwise: such a name resolves to the root's member
// -- the forwarder, or a STUBBED stand-in -- where the engine may reach the
// sibling itself. The gate's "service split guard" holds that shape, not
// this harness.
function fileSet(svc) {
  if (typeof svc === "string") return { service: svc, files: {} }
  if (svc && typeof svc === "object" && typeof svc.service === "string" && svc.files && typeof svc.files === "object") {
    return { service: svc.service, files: svc.files instanceof Map ? Object.fromEntries(svc.files) : svc.files }
  }
  throw new Error("service-harness: bootService takes Service.qml's text or a file set { service, files }")
}

// D-PLY-69: what bootService reads out of a tree's text depends on the text
// alone, so it is read once per text -- a seeded sweep boots the service a
// few hundred times (tests/player-world.js), and the read was a third of a
// boot. Nothing below writes to what it returns; every compile is still per
// boot, in that boot's own scope. A file set is read once per set object.
const PARSED = new Map()
const PARSED_SETS = new WeakMap()
function parsedSet(svc) {
  const cached = typeof svc === "string" ? PARSED.get(svc) : (svc && typeof svc === "object" ? PARSED_SETS.get(svc) : undefined)
  if (cached !== undefined) return cached
  const set = fileSet(svc)
  serviceReader.inlineText(set.service, set.files)
  const behinds = serviceReader.declarations(set.service).map(d => ({ qualifier: d.qualifier, file: d.file, fns: rootFunctions(set.files[d.file]) }))
  const v = { set, fns: rootFunctions(set.service), props: rootProperties(set.service), ipc: ipcFunctions(set.service), behinds }
  if (typeof svc === "string") PARSED.set(svc, v)
  else PARSED_SETS.set(svc, v)
  return v
}

function bootService(svc, Model, o) {
  const parsed = parsedSet(svc)
  const serviceText = parsed.set.service
  const opts = o || {}
  const h = { clock: opts.clock || 1760000000000, later: [], cacheRuns: [], signals: [], warnings: [], detached: [], detachedRuns: [], turns: 0, cacheHang: false,
              notifyRuns: [], notifyServer: null, notifyHang: false, allowDetachedNotice: 0,
              privateRuns: [], privateHang: false, privateAnswer: null }
  // F-HARNESS-100: `section`, `bare` and `barSections` (own key, undefined
  // allowed: the 4.0.x kit) place the entry and choose the host's kit.
  const kit = { section: opts.section, bare: opts.bare, fresh: opts.fresh }
  if (Object.prototype.hasOwnProperty.call(opts, "barSections")) kit.barSections = opts.barSections
  h.host = new Host(opts.entry, opts.host || "lag", kit)
  h.stateFile = new StateFile(opts.stateText || "", { exists: opts.exists, fault: opts.fault, ownEcho: opts.ownEcho, dirAbsent: opts.dirAbsent, dirPresent: opts.dirPresent, mode: opts.mode, umask: opts.umask })
  // D-HOST-16: manifest.json beside the tree as the view finds it --
  // `manifestText` (null for no file), or the running model's own version,
  // which is what a whole install holds (the gate proves the two agree).
  // D-REL-16: what Quickshell.env answers, by name (`env`); null for
  // anything else, as the host answers an unset name (F-HARNESS-133).
  h.env = opts.env && typeof opts.env === "object" ? opts.env : {}
  h.manifestFile = new ManifestFile(opts.manifestText !== undefined ? opts.manifestText : JSON.stringify({ id: PID, version: Model.PLUGIN_VERSION }) + "\n")
  h.stateInitStdout = { text: "" }
  // The helper's `cache` reply: ok for every verb, unless a test says
  // otherwise (h.cacheFails = ["migrate"]).
  h.cacheFails = []
  h.cacheAnswer = (command) => {
    const verb = cacheVerb(command)
    if (h.cacheFails.indexOf(verb) !== -1) return JSON.stringify({ ok: false, kind: "cache", action: verb, error: { code: "io", message: "failed" } }) + "\n"
    return JSON.stringify({ ok: true, kind: "cache", action: verb }) + "\n"
  }
  const ids = makeIds(h)
  const fns = parsed.fns
  const props = parsed.props
  const values = {}
  const root = {}
  // D-SINK-24 (rule 10): EVERY argument, joined by a space, as the real
  // console prints them. This kept the first argument only, so a line such
  // as `console.warn("...tokens:", rejected.join(" "))` reached the journal
  // with the credential and reached every leak check here without it.
  const quiet = { log() {}, info() {}, error() {}, warn(...a) { h.warnings.push(a.map(String).join(" ")) } }
  class FakeDate extends Date {
    constructor(...a) { if (a.length === 0) super(h.clock); else super(...a) }
    static now() { return h.clock }
  }
  const Qt = {
    // F-HARNESS-130 (rule 10): as Qt 6.12.0 was measured to do it (qml under
    // gdb; QA-RESULTS "D-REL-15 ... Round two"). A function already queued is
    // taken out and queued again at the END with the LAST call's arguments:
    // it runs once, where the last call put it. Only what is pending is
    // searched: runLater takes a batch at a time (below), so a call made
    // while a batch runs goes to the next one, and a function the running
    // batch has still to call runs in it and again in the next. Until
    // 2026-11-24 this kept the FIRST call's place and arguments, and folded
    // a call into the batch that was running.
    callLater(fn, ...args) {
      const at = h.later.findIndex(e => e.fn === fn)
      if (at !== -1) h.later.splice(at, 1)
      h.later.push({ fn, args })
    },
    resolvedUrl(x) { return { toString() { return String(x) } } }
  }
  // The double the service's code calls, for a check of the double itself.
  h.Qt = Qt
  const extras = Object.assign({ root, Model, console: quiet, Qt, Date: FakeDate }, ids)
  // D-REL-14 C2: each code-behind's qualifier, filled once `compile` exists.
  for (const b of parsed.behinds) extras[b.qualifier] = {}
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
  // D-PLY-69: the socket observer's own onConnectionStateChanged, from the
  // playerSocketComponent block of the tree, run by h.socketWorld's sockets
  // with `this` the socket (null on a tree without the block).
  const sockAt = serviceText.indexOf("id: playerSocketComponent")
  const sockBody = sockAt === -1 ? null : handlerBlock(serviceText.slice(sockAt), "onConnectionStateChanged: {")
  h.socketChanged = sockBody ? compile("", sockBody, "playerSocket_onConnectionStateChanged") : null
  const onHostSettingsChanged = onHostText ? compile("", onHostText, "onHostSettingsChanged") : () => {}
  // Properties. A readonly binding is re-evaluated on every read.
  for (const p of props) {
    if (p.readonly && p.expr !== null) {
      const get = p.block ? compile("", p.expr, "binding_" + p.name) : compile("", "return (" + p.expr + ")", "binding_" + p.name)
      Object.defineProperty(root, p.name, { get() { try { return bindingValue(p.type, get()) } catch (e) { return defaultOf(p.type) } }, enumerable: true, configurable: true })
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
        // D-HOST-16: `manifest` is a var property, so a new object is a new
        // value and QML runs onManifestChanged inside the assignment -- the
        // host's own, made after creation (shell.qml's ensureService), and
        // every rescan's fresh copy (_syncServices) alike.
        if (p.name === "manifest" && v !== before && typeof h.manifestChanged === "function") h.manifestChanged()
        // D-LOGO-20 (R32f): `activeCacheDir` is a readonly binding over
        // stateLoaded, cacheReady and the active key, and QML fires its
        // change handler synchronously the moment any of them moves it.
        // The handler is compiled from its own text below and fired here,
        // after every plain-property set that changed the binding's value
        // -- the start's first value included, as the shell sees it.
        if (h.started && typeof h.checkActiveDir === "function") h.checkActiveDir()
      },
      enumerable: true, configurable: true
    })
  }
  for (const p of props) {
    if (p.readonly || p.expr === null || p.block) continue
    try { values[p.name] = bindingValue(p.type, compile("", "return (" + p.expr + ")", "init_" + p.name)()) } catch (e) { values[p.name] = defaultOf(p.type) }
  }
  // Signals are recorded.
  for (const m of serviceText.matchAll(/^  signal ([A-Za-z_][A-Za-z0-9_]*)\(/gm)) root[m[1]] = (...a) => h.signals.push([m[1]].concat(a))
  for (const b of parsed.behinds) {
    for (const name in b.fns) extras[b.qualifier][name] = compile(b.fns[name].args, b.fns[name].body, name)
  }
  for (const name in fns) {
    if (name in STUBBED) continue
    root[name] = compile(fns[name].args, fns[name].body, name)
  }
  // D-SRC-37 (c): a test that needs a STUBBED function for real (the config
  // shield's run, to see its watchdog armed) installs the shipping text of
  // it; the stub stays for every other test.
  h.unstub = (name) => { if (!(name in fns)) throw new Error("service-harness: no function " + name); root[name] = compile(fns[name].args, fns[name].body, name) }
  // D-PLY-64: the Service object's destruction, from the shipping text of
  // its `Component.onDestruction` block -- what the host's destroy() runs.
  // A tree without the block destroys nothing.
  const destructionText = handlerBlock(serviceText, "  Component.onDestruction: {")
  h.destroy = destructionText ? compile("", destructionText, "onDestruction") : () => {}
  // F-SINK-16: the IPC verbs, from their own text (ipcFunctions above), run
  // in the root's scope as the handler's `root.` and `Model.` resolve there.
  h.ipc = {}
  const ipcFns = parsed.ipc
  for (const name in ipcFns) h.ipc[name] = compile(ipcFns[name].args, ipcFns[name].body, "ipc_" + name)
  root.runConfigShield = () => {}
  root.noteSessionOutcome = () => {}
  root.markDeadSession = () => {}
  root.fetchLogos = () => {}
  root.pruneFailed = () => {}
  // D-LOGO-20 (R32f): onActiveCacheDirChanged from its own text, fired by
  // the property setters above whenever the binding's value moved (""
  // before the state loads, as in the shell). A tree without the handler
  // fires nothing. Re-entrant sets inside the handler (pendingFreshness)
  // re-check and find no further change.
  const activeDirText = handlerBlock(serviceText, "  onActiveCacheDirChanged: {")
  const onActiveCacheDirChanged = activeDirText ? compile("", activeDirText, "onActiveCacheDirChanged") : () => {}
  let lastActiveDir = ""
  h.activeDirChanges = 0
  h.checkActiveDir = () => {
    const now = String(root.activeCacheDir || "")
    if (now === lastActiveDir) return
    lastActiveDir = now
    h.activeDirChanges++
    onActiveCacheDirChanged()
  }
  root.hostConfigShield = Model.CONFIG_SHIELD_PRIVATE
  // D-HOST-16: manifestFile's three handlers and the root's onManifestChanged,
  // from their own text (one line, or a block), with the view's own
  // unqualified `text()` and `reload()` read as the view's. A tree without a
  // handler runs nothing there, which is that tree.
  const manifestAt = serviceText.indexOf("    id: manifestFile")
  const manifestBlock = manifestAt === -1 ? "" : serviceText.slice(manifestAt, serviceText.indexOf("\n  }", manifestAt))
  const viewOwn = (t) => t.replace(/(^|[^.\w])text\(\)/g, "$1manifestFile.text()").replace(/(^|[^.\w])reload\(\)/g, "$1manifestFile.reload()")
  const manifestHandler = (name, args) => {
    const one = (manifestBlock.match(new RegExp("^    " + name + ": (?:\\(error\\) => )?(?!\\{)(.*)$", "m")) || [])[1]
    const body = one || handlerBlock(manifestBlock, "    " + name + ": " + (args ? "(error) => {" : "{"))
    return body ? compile(args, viewOwn(body), "manifestFile_" + name) : () => {}
  }
  const onManifestLoaded = manifestHandler("onLoaded", "")
  const onManifestLoadFailed = manifestHandler("onLoadFailed", "error")
  const onManifestFileChanged = manifestHandler("onFileChanged", "")
  h.manifestFile.watching = /^    watchChanges: true$/m.test(manifestBlock)
  const rootManifestText = (serviceText.match(/^  onManifestChanged: (?!\{)(.*)$/m) || [])[1] || handlerBlock(serviceText, "  onManifestChanged: {")
  h.manifestChanged = rootManifestText ? compile("", rootManifestText, "onManifestChanged") : () => {}
  // One load of manifest.json as it is NOW, through the tree's handlers.
  h.loadManifest = () => {
    const mf = h.manifestFile
    mf.loads++
    if (mf.disk === null) { mf.view = ""; onManifestLoadFailed(2); return }
    mf.view = mf.disk
    onManifestLoaded()
  }
  h.manifestFile.loader = () => h.later.push({ fn: h.loadManifest, args: [] })
  // An in-place edit: fileChanged, queued, while the view watches.
  h.manifestEdit = (text) => {
    const mf = h.manifestFile
    mf.disk = text
    if (mf.watching && mf.armed) h.later.push({ fn: onManifestFileChanged, args: [] })
  }
  // A replacement with nothing raised and the watch lost: the silent case,
  // kept as the less forgiving one (D-DOC-39: at git's update the real
  // watch fired; h.manifestEdit above is that arm).
  Object.defineProperty(h, "manifestDisk", {
    get() { return h.manifestFile.disk },
    set(v) { h.manifestFile.disk = v; h.manifestFile.armed = false },
    enumerable: true, configurable: true
  })
  // The view is made (its first load queued), then the host hands it the
  // manifest, as ensureService does once createObject returns.
  if (manifestAt !== -1) h.manifestFile.loader()
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
  // The interval is read from its own text every time, and a restart() arms
  // the Timer with the interval it has at that moment -- the order QML's
  // Timer takes it in. R28a made it a binding (its schedule's bound); R29a
  // put back R26a's literal 2000, and the getter reads either the same way.
  const verifyInterval = verifyIntervalText === null ? null : compile("", "return (" + verifyIntervalText + ")", "stateVerifyWatchdog_interval")
  Object.defineProperty(vw, "interval", { get() { return verifyInterval === null ? null : verifyInterval() }, enumerable: true, configurable: true })
  vw.armedAt = null
  vw.armedInterval = null
  vw.restart = function () { this.restarts++; this.running = true; this.armedAt = h.clock; this.armedInterval = this.interval }
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
  ww.restart = function () { this.restarts++; this.running = true; this.armedAt = h.clock; this.armedInterval = this.interval }
  ww.stop = function () { this.stops++; this.running = false; this.armedAt = null }
  h.writeWaitWatchdog = () => { onWriteWaitWatchdog(); h.runLater() }
  // D-SRC-37 (c): any other Timer of the tree, by id, driven the same way --
  // its `interval` (a binding, read at each restart) and its onTriggered
  // (one line or a block) compiled from its own Timer block. A tree without
  // the block gets a Timer with a null interval, which never comes due.
  const treeTimer = (id) => {
    const t = ids[id]
    const at = serviceText.indexOf("id: " + id + "\n")
    const block = at === -1 ? null : serviceText.slice(serviceText.lastIndexOf("  Timer {", at), serviceText.indexOf("\n  }", at))
    const intervalText = block === null ? null : ((block.match(/^    interval: (.*)$/m) || [])[1] || "1000")
    const oneLine = block === null ? null : (block.match(/^    onTriggered: (?!\{)(.*)$/m) || [])[1]
    const body = block === null ? null : (oneLine || handlerBlock(block, "onTriggered: {"))
    const fire = body ? compile("", body, id + "_onTriggered") : () => {}
    const interval = intervalText === null ? null : compile("", "return (" + intervalText + ")", id + "_interval")
    Object.defineProperty(t, "interval", { get() { return interval === null ? null : interval() }, enumerable: true, configurable: true })
    t.armedAt = null
    t.armedInterval = null
    t.restart = function () { this.restarts++; this.running = true; this.armedAt = h.clock; this.armedInterval = this.interval }
    t.stop = function () { this.stops++; this.running = false; this.armedAt = null }
    return [t, fire]
  }
  // The recheck of lane RA (2026-11-01): fire ONE Timer block's own
  // onTriggered, once, as QML does when it comes due -- for a timer h.elapse
  // does not drive (playRetryTimer is counted, never run), without putting
  // it on every test's clock. The double reads stopped afterwards, as a
  // non-repeating Timer does. -> false when the tree has no such block.
  h.fireTimer = (id) => {
    const at = serviceText.indexOf("id: " + id + "\n")
    if (at === -1) return false
    const block = serviceText.slice(serviceText.lastIndexOf("  Timer {", at), serviceText.indexOf("\n  }", at))
    const oneLine = (block.match(/^    onTriggered: (?!\{)(.*)$/m) || [])[1]
    const body = oneLine || handlerBlock(block, "onTriggered: {")
    if (!body) return false
    if (ids[id]) ids[id].running = false
    compile("", body, id + "_fired")()
    return true
  }
  h.timed = [[vw, onVerifyWatchdog], [ww, onWriteWaitWatchdog]]
  // D-SRC-69: probeWatchdog joins them -- a probe HELD behind a cache job
  // is bounded by it, and a test that never moves the clock is unchanged.
  // D-PLY-35: and the player slot's, whose interval is a binding over the
  // verb in flight (`root.playerTimeoutMs`), read at each restart() the way
  // QML's Timer reads it; h.elapse fires its own onTriggered, which TERMs a
  // running helper (recorded in playerProc.signals) and flags the exit.
  for (const id of ["cacheWatchdog", "failedWatchdog", "configShieldWatchdog", "whichWatchdog", "pipProbeWatchdog", "stateModeWatchdog", "statePrivateWatchdog", "stateInitRetry", "probeWatchdog", "playerWatchdog", "olderRestartTimer"]) h.timed.push(treeTimer(id))
  // D-PLY-40: a Timer the clock does not drive by default, put on it by a
  // test that asks -- its interval and onTriggered from its own block, as
  // above, from the moment of the call (a restart() made before it is not
  // seen). stopSettleTimer is the first: every earlier check that stops
  // keeps `stopping` held, as it was written against, and one that asks for
  // the backstop gets the tree's own. -> the Timer double.
  h.driveTimer = (id) => {
    const pair = treeTimer(id)
    h.timed.push(pair)
    return pair[0]
  }
  // D-SRC-49: the `state mode` run's exit, with the REAL helper's reply for
  // the file as the double holds it (rule 10: the verb chmods a regular
  // file that is not 0600 and nothing else; the fake's mode moves with it),
  // or `reply` as given.
  h.stateModeExit = (o2) => {
    const io = o2 || {}
    const p = ids.stateModeProc
    if (!p.running) return false
    p.running = false
    let text = io.reply
    if (text === undefined) {
      let file = "kept"
      if (h.stateFile.exists && !h.stateFile.fault && h.stateFile.mode !== null && h.stateFile.mode !== 0o600) { h.stateFile.mode = 0o600; file = "changed" }
      text = JSON.stringify({ ok: true, kind: "state", action: "mode", folder: "kept", file }) + "\n"
    }
    root.handleStateModeExit(io.code === undefined ? 0 : io.code, text)
    h.runLater()
    return true
  }
  // D-SINK-103: a `state private` left running by h.privateHang, ended now
  // with the double's answer for the file (or `reply` / `code` as given),
  // through the shipping exit handler. False when none runs.
  h.privateExit = (o2) => {
    const io = o2 || {}
    const p = ids.statePrivateProc
    if (!p._running) return false
    const out = io.reply !== undefined ? { code: io.code === undefined ? 0 : io.code, reply: io.reply, raises: false } : helperPrivate(h.stateFile)
    if (out.raises) h.stateFile.reload()
    h.runLater()
    p._running = false
    root.handleStatePrivateExit(out.code, out.reply)
    h.runLater()
    return true
  }
  // Each Timer fires once its restart() is `interval` old, in the order they
  // come due; a handler that re-arms its Timer (R27a's second read) is due
  // again `interval` after the moment it fired.
  h.elapse = (ms) => {
    const end = h.clock + ms
    for (;;) {
      const due = h.timed
        .filter(([t]) => t.running && t.armedInterval !== null && t.armedAt + t.armedInterval <= end)
        .sort((a, b) => (a[0].armedAt + a[0].armedInterval) - (b[0].armedAt + b[0].armedInterval))
      if (!due.length) break
      const [t, fire] = due[0]
      h.clock = t.armedAt + t.armedInterval
      t.running = false; t.armedAt = null
      fire(); h.runLater()
    }
    h.clock = end
  }
  // The start-up init's exit, with the double's reply and side effects.
  h.helperInit = (code, empty) => {
    const out = helperInit(h.stateFile, code, empty)
    h.stateInitStdout.text = out.reply
    return out
  }

  const BOUND = opts.bound || 400
  h.root = root
  // A batch at a time, as Qt's deferred-call queue takes its pending calls
  // (F-HARNESS-130): what is queued when the batch starts runs, in order;
  // what it queues -- a Qt.callLater, or one of this harness's own events
  // (a process's exit, a state load) -- waits for the next batch, so the
  // order is the queue's as before and only the fold is narrowed to what is
  // pending. A call that throws leaves the rest of its batch queued first.
  h.runLater = () => {
    while (h.later.length) {
      const batch = h.later
      h.later = []
      for (let i = 0; i < batch.length; i++) {
        if (++h.turns > BOUND) { h.later = []; throw new Error("LOOP: " + h.turns + " deferred calls, " + h.host.writes.length + " entry writes") }
        const e = batch[i]
        try { e.fn.apply(null, e.args) } catch (err) { h.later = batch.slice(i + 1).concat(h.later); throw err }
      }
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
  // D-SRC-69: the exit of a cache job left running by `h.cacheHang` (the
  // helper still starting, or slow), with the double's answer for its
  // command, through the handler the real exit calls. False when none runs.
  h.cacheExit = () => {
    if (!ids.cacheProc._running) return false
    ids.cacheProc._running = false
    root.handleCacheExit(h.cacheAnswer(ids.cacheProc.command.slice()))
    h.runLater()
    return true
  }
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
  // F-HARNESS-136: the host's next syncPluginApis, which assigns the parsed
  // copy (the Array form) and raises the bar config's change. On the host's
  // own order it comes before the state loads (110 of 110 creations,
  // lane-dh15m), so that is where "creation" ends the window; "load" leaves
  // it open through the load, until the host's first assign.
  if (h.host.fresh === "creation") h.host.sync()
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
    const io = Object.assign({ code: opts.initCode || 0, order: opts.initOrder || "reload-first", timeout: opts.initTimeout === true, empty: false }, o2 || {})
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
    const out = h.helperInit(io.code, io.empty === true)
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

// D-HOST-5: Omarchy's notification server as MEASURED, for a test that sets
// h.notifyServer (rule 10: never more forgiving than the real one). Quickshell
// 0.3.1's NotificationServer, run on a private bus on 2026-10-28 by lane-ply33
// and again by lane-host5 behind the real /usr/bin/omarchy-notification-send:
// it numbers cards itself from 1; `-r <id>` replaces a card only when the id
// is one it handed out and still holds (the card updates in place, the same
// id comes back); any other id -- a fixed 74021, an expired card's -- gets a
// NEW card with the next id; an expired or dismissed card is no longer held.
// The wrapper prints the returned id only with `-p`. `cards` is every card
// the server ever made, in order; `open()` those still held.
function notificationServer() {
  const s = { next: 1, cards: [], held: new Map() }
  s.post = (argv) => {
    const r = argv.indexOf("-r")
    const want = r === -1 ? 0 : Number(argv[r + 1])
    const app = argv.indexOf("--app-name") === -1 ? "omarchy-action" : argv[argv.indexOf("--app-name") + 1]
    const title = argv[argv.length - 2]
    const body = argv[argv.length - 1]
    let card = s.held.get(want)
    if (card) { card.title = title; card.body = body; card.app = app; card.updates++ }
    else { card = { id: s.next++, app, title, body, updates: 0, open: true }; s.cards.push(card); s.held.set(card.id, card) }
    return { code: 0, text: argv.indexOf("-p") === -1 ? "" : card.id + "\n" }
  }
  // The card's own timeout, or the user dismissing it: the server lets go.
  s.expire = (id) => { const c = s.held.get(id); if (c) { c.open = false; s.held.delete(id) } }
  s.open = () => s.cards.filter(c => c.open)
  return s
}

// A shell restart over what the last one left: the host's stored entry and
// the state file's bytes, the clock running on.
function restartService(svc, Model, h, o) {
  // F-HARNESS-100: on the same kit, with the entry where it was.
  const stored = h.host.storedEntry()
  const bare = typeof stored === "string"
  return bootService(svc, Model, Object.assign({ entry: bare ? {} : (() => { const e = clone(stored); delete e.id; return e })(),
                                                          stateText: h.stateFile.disk, host: h.host.mode, clock: h.clock + 60000,
                                                          section: h.host.section, bare, barSections: h.host.barSections }, o || {}))
}

module.exports = { V4, bootService, restartService, rootFunctions, rootProperties, ipcFunctions, matchBrace, STUBBED, PID, HELPER_EMPTY_STATE, notificationServer, NOTICE_LEDGER, cacheVerb, helperView,
                   hostBarSections, INSTALLED_BAR_SECTIONS, HOST_SHELL }
