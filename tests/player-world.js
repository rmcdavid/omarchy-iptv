// tests/player-world.js -- the helper's player verbs and their players, as a
// seeded world the service harness's shell plays against (D-PLY-69).
//
// The settle of a stop (ARCHITECTURE-PLAYER 4.10) is a protocol between the
// shell and the helper: detached `player stop`s, the player slot's `player
// start`, the control slot's zap, the socket observer, and the Timers that
// back them up, all ordered only by the lock and the intent sequence. The
// round that rebuilt it (the settle of three reviews of 9d604cf) found its
// cases by a seeded world model of exactly that, kept as scratch, and the
// recheck of 2cfeb74 found D-PLY-69 the same way. This is that model made
// permanent, so a sweep of seeds is a test rather than a memory.
//
// What it models, each as the shipping helper does it (bin/helper/07-player.py
// and 08-player-verbs.py, read; nothing here is measured on a real player):
//   - ONE lock. A verb that reaches it waits; the lock goes to ANY waiter
//     when it frees (flock grants are not FIFO, 4.10), and a waiter still
//     waiting after lockMs + lockPollMs gives up: a start answers `busy`, a
//     detached stop does nothing.
//   - The record. Under the lock a verb whose --seq is below the record is
//     `superseded` and does nothing; otherwise it writes its seq.
//   - `player stop`: ladders the live player (a quick quit, or a wedged one
//     the ladder takes seconds over, up to the 7 s the ladder can last),
//     holding the lock until it settles.
//   - `player start`: adopts the live player and loads its channel into it,
//     or spawns one (bound a moment before the load) and loads it; a zap
//     that reached a fresh spawn first is stood down for (D-PLY-11). It
//     releases the lock BEFORE its first-load window, so a stop can ladder
//     its player before it answers, and then its window saw mpv close the
//     connection (`failed`, `closed`); else the load was seen playing.
//   - `play` (the zap): no lock; it loads into whatever player listens on the
//     socket when it connects, or answers `not_running`.
//   - `player probe`: lock-free, the record and the live player's stash.
//   - The socket observer: h.socketWorld's sockets connect only to a live,
//     bound player and see its death a few milliseconds after it, through
//     the Component's own handler (tests/service-harness.js).
//   - `player restart --from term` (D-PLY-72), when a sequence asks for the
//     health path (`restartP`): under the lock it TERMs the live player, which
//     dies 20 ms to 2 s later, and then spawns as a start does. The verdict
//     that sends it is drawn, not observed: restartPlayer() is called as the
//     health tick calls it, and does what it does -- nothing with no player
//     up or a stop settling, a stop() once its one relaunch is spent, and,
//     with the slot busy, a retry on relaunchTimer, which runs from its own
//     block.
//   - Another launcher (D-PLY-73), when a sequence asks for it (`contestP`):
//     right after a user's stop, with that chance, another launcher's verb
//     wants the lock at once and, once it has it, holds it past a stop's
//     wait (the lock wait plus 0.1 to 2.5 s, drawn: which real verb holds it
//     that long is not claimed), records 0 as a terminal verb's default
//     --seq does, and leaves the player as it is. A user's stop it reaches
//     the lock before gives up and the player plays on; the 5 s look reads a
//     record below the stop and does nothing; the backstop's probe finds the
//     player and the shell stops it itself. The next action then also waits
//     out that backstop, so it lands around the shell's own stop.
//   - A stop's probe in flight (D-PLY-75), when a sequence asks for it
//     (`windowP`, with `contestP`): after a contested stop, with that chance,
//     the next action lands instead 1 to 250 ms after that stop's 5 s look
//     or its backstop sends its probe (drawn, half each), while that probe
//     is usually still out (it answers 60 to 300 ms after it is sent). The
//     plain schedule reaches that window about once in a few hundred
//     sequences (lane-ply73's seed 226 of 300).
//   - A slow player (D-PLY-78), when a sequence asks for it (`slowP`): with
//     that chance a start's or a restart's lock section first runs 6.15 to
//     24 s (a player slow to answer its requests, D-PLY-39's regime, inside
//     the verb's own bound), so a stop pressed in it gives up on the lock
//     and the verb can answer after that stop's backstop. No draw without
//     it.
//   - `status` (the control slot): the live player's stash, or not running.
//     Asked once, by the health tick's own block (h.fireTimer), after a
//     sequence whose last action is a play: ruling CL6 lets the label and the
//     player disagree for up to one health tick (D-PLY-11 T-A, a zap racing an
//     adopting start), and the tick's repair is the shell's own.
//   - Nothing crashes, no stream fails and no refusal but `busy` and
//     `superseded` happens: every death is a stop's or a restart's rung, so a
//     card that says a channel stopped unexpectedly or failed is a false card
//     here.
// What it does NOT model, so it cannot find a defect there: a player another
// build launched (restart on adoption's probe, hold and replacement -- the
// node suite's deterministic D-PLY-72 rows hold that start); a health tick
// during a sequence (only the one after it); a wedged player a start finds
// and ladders; the watchdog's stopped start beyond its TERM; another
// launcher that supersedes a stop with a higher --seq, writes a channel or
// starts a player (a second Service object's, a terminal `player start`'s);
// a player that does not answer, will not verify or cannot be identified
// (the node suite's D-PLY-73 table holds the shell's stop of each), and so
// no probe that finds a player idle and re-reads it 500 ms later: the world
// has no shell restart and no reattach, and its one way to an idle player
// under the observer is a start stopped by its 58.25 s watchdog after its
// spawn bound, which its starts never reach (the node suite's D-PLY-76 rows
// hold a play or a stop inside that re-read); and any
// real timing -- every interval here is drawn from the ranges written in it.
// Time is the harness's clock. The shell's Timers that the settle reads run
// from their own blocks (h.driveTimer), playerSocketTimer as the repeating
// Timer it is.
//
// The verdicts, over one sequence of user plays and stops:
//   (1) a channel written into a player by a verb the shell issued AFTER a
//       stop, when that stop then laddered that player: a zap written to a
//       socket a stop the user issued still had to tear down (4.10).
//   (2) the user's last action a play: at the end their LAST chosen channel
//       plays and the shell names it, or a card was raised after that play --
//       asked after the one health tick above, which is CL6's window.
//   (2b) any card the world does not justify (only "The player is busy"
//       after a start's every try met the lock is one).
//   (3) the user's last action a stop: at the end nothing plays.
"use strict"
const H = require("./service-harness.js")

// A small seeded generator (mulberry32): the suite fixes Math.random.
function rng32(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6D2B79F5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const BUSY = "another player command holds the lock"

function playerWorld(h, o) {
  const opts = o || {}
  const rnd = rng32(opts.seed || 1)
  const between = (lo, hi) => lo + Math.floor(rnd() * (hi - lo + 1))
  const LOCK_WAIT = opts.lockWaitMs
  const sourceKey = String(opts.sourceKey || "")
  const nameOf = id => String((h.root.channelIndex[id] || {}).name || "")
  const w = { record: 0, holder: null, waiters: [], player: null, players: [], nextPid: 4300, sockets: [],
              events: [], order: 0, issued: 0, stops: [], writes: [], log: [], slot: null, control: null }
  const at = (ms, label, fn) => { w.events.push({ at: h.clock + ms, n: w.order++, label, fn }) }
  const note = line => { w.log.push(Math.round(h.clock - w.t0) + " " + line) }
  w.t0 = h.clock

  // ---- the shell's three ways out: the player slot, the control slot, execDetached
  const pslot = h.ids.playerProc
  let pRunning = pslot.running
  Object.defineProperty(pslot, "running", { get() { return pRunning }, set(v) { pRunning = v; if (v === true) slotIssued() }, configurable: true })
  const pSignal = pslot.signal
  pslot.signal = function (n) {
    pSignal.call(pslot, n)
    if (n !== 15 || !pRunning || !w.slot) return
    // The helper dies: its lock goes with it, and its exit says nothing.
    const v = w.slot
    v.dead = true
    if (v.waiting) { v.waiting = false; w.waiters.splice(w.waiters.indexOf(v), 1) }
    if (w.holder === v) w.holder = null
    at(10, "slot TERMed", () => reply(v, ""))
  }
  const cslot = h.ids.controlProc
  let cRunning = cslot.running
  Object.defineProperty(cslot, "running", { get() { return cRunning }, set(v) { cRunning = v; if (v === true) controlIssued() }, configurable: true })
  const Q = h.ids.Quickshell
  const exec = Q.execDetached
  Q.execDetached = function (context) {
    exec.call(Q, context)
    const argv = context.map(String)
    const i = argv.indexOf("player")
    if (i !== -1 && argv[i + 1] === "stop") stopIssued(Number(argv[argv.indexOf("--seq") + 1]))
  }
  h.socketWorld = { socket: () => {
    const s = { _c: false, pid: 0, destroyed: false, write() {}, flush() {}, destroy() { this.destroyed = true } }
    Object.defineProperty(s, "connected", {
      get() { return s._c },
      set(v) {
        if (v !== true || s._c) return
        const p = w.player
        if (!p || !p.alive || !p.bound) return
        s._c = true
        s.pid = p.pid
        w.sockets.push(s)
        h.socketChanged.call(s)
      }
    })
    return s
  } }
  for (const id of ["stopSettleTimer", "stopLookTimer", "playRetryTimer", "probeRetryTimer", "relaunchTimer"]) h.driveTimer(id)
  // playerSocketTimer repeats: fired, it stays armed unless its own block
  // stopped or restarted it.
  const hunt = h.driveTimer("playerSocketTimer")
  const pair = h.timed[h.timed.length - 1]
  const fireHunt = pair[1]
  pair[1] = () => {
    const s = hunt.stops, r = hunt.restarts
    fireHunt()
    if (hunt.stops === s && hunt.restarts === r) { hunt.running = true; hunt.armedAt = h.clock; hunt.armedInterval = hunt.interval }
  }

  function argOf(c, flag) { const i = c.indexOf(flag); return i === -1 ? "" : c[i + 1] }

  function slotIssued() {
    const c = H.helperView(pslot.command, pslot.environment)
    const verb = argOf(c, "player")
    const v = { kind: verb, seq: Number(argOf(c, "--seq")), id: argOf(c, "--id"), issue: ++w.issued, slot: "player" }
    w.slot = v
    note("issue " + verb + (v.id ? " " + v.id : "") + (verb !== "probe" ? " @" + v.seq : ""))
    if (verb === "start" || verb === "restart") {
      at(between(30, 300), "lock wanted", () => wantLock(v))
      // D-PLY-78 (`slowP`): a slow player keeps this verb's lock section
      // past a stop's lock wait. No draw without it.
      if (opts.slowP && rnd() < opts.slowP) v.slowMs = between(LOCK_WAIT + 100, 24000)
    } else if (verb === "probe") at(between(60, 300), "probe answers", () => reply(v, probeReply()))
    else at(20, "unknown verb", () => reply(v, JSON.stringify({ ok: false, kind: "player." + verb, error: { code: "not_implemented", message: "not modelled" } })))
  }

  function controlIssued() {
    const kind = String(h.root.controlKind || "")
    const c = H.helperView(cslot.command, cslot.environment)
    const v = { kind, id: argOf(c, "--id"), issue: ++w.issued, slot: "control" }
    w.control = v
    note("issue control " + kind + (v.id ? " " + v.id : ""))
    if (kind === "status") {
      at(between(20, 80), "status answers", () => {
        const p = w.player && w.player.alive && w.player.bound ? w.player : null
        controlReply(v, JSON.stringify(p === null ? { ok: true, kind: "status", running: false }
          : { ok: true, kind: "status", running: true, paused: false, idle: p.channel === "", mpvVersion: "mpv 0.41.0", stash: stashOf(p), rewind: null }))
      })
      return
    }
    if (kind !== "play") { at(between(20, 80), "control answers", () => controlReply(v, JSON.stringify({ ok: false, kind, error: { code: "not_running", message: "mpv socket not found" } }))); return }
    at(between(40, 250), "zap connects", () => {
      const p = w.player
      if (!p || !p.alive || !p.bound) { at(between(5, 40), "zap answers", () => controlReply(v, JSON.stringify({ ok: false, kind: "play", error: { code: "not_running", message: "mpv socket not found" }, id: v.id }))); return }
      write(p, v)
      at(between(30, 300), "zap answers", () => controlReply(v, p.alive
        ? JSON.stringify({ ok: true, kind: "play", id: v.id, name: nameOf(v.id), entryId: ++p.entries })
        : JSON.stringify({ ok: false, kind: "play", error: { code: "ipc_error", message: "mpv closed the connection" }, id: v.id })))
    })
  }

  function stopIssued(seq) {
    const v = { kind: "stop", seq, issue: ++w.issued, laddered: 0 }
    w.stops.push(v)
    note("issue stop @" + seq)
    at(between(30, 300), "lock wanted", () => wantLock(v))
  }

  function write(p, v) {
    if (v.dead) return
    w.writes.push({ pid: p.pid, issue: v.issue, id: v.id, by: v.kind })
    p.channel = v.id
    if (v.kind === "play") p.zapped = true
    note(v.kind + " writes " + v.id + " into " + p.pid)
  }

  function kill(p, v) {
    if (!p.alive) return
    p.alive = false
    if (v) v.laddered = p.pid
    if (w.player === p) w.player = null
    note("player " + p.pid + " dies" + (v ? " (stop @" + v.seq + ")" : ""))
    for (const s of w.sockets) {
      if (s.pid !== p.pid || !s._c) continue
      at(between(1, 5), "EOF", () => { if (!s._c) return; s._c = false; h.socketChanged.call(s); h.drain() })
    }
    if (p.onDeath) p.onDeath()
  }

  function wantLock(v) {
    v.waiting = true
    w.waiters.push(v)
    at(LOCK_WAIT, "lock wait ends", () => {
      if (!v.waiting) return
      v.waiting = false
      w.waiters.splice(w.waiters.indexOf(v), 1)
      note(v.kind + " @" + v.seq + " gives up on the lock")
      if (v.kind !== "stop") reply(v, JSON.stringify({ ok: false, kind: "player." + v.kind, error: { code: "busy", message: BUSY }, id: v.id, seq: v.seq }))
    })
  }

  function release(ms) { at(ms, "lock released", () => { w.holder = null }) }

  function grant(v) {
    v.waiting = false
    w.waiters.splice(w.waiters.indexOf(v), 1)
    w.holder = v
    if (v.kind === "foreign") {
      // Another launcher's verb (`contest`): a terminal `omarchy-iptv player`
      // verb's --seq defaults to 0, which check_seq never refuses and
      // write_lock_record records; it leaves the player as it is.
      w.record = 0
      note("another launcher's verb holds the lock for " + v.holdMs + " ms (record 0)")
      release(v.holdMs)
      return
    }
    if (v.seq < w.record) {
      note(v.kind + " @" + v.seq + " superseded (record " + w.record + ")")
      release(5)
      if (v.kind !== "stop") at(between(5, 30), "superseded answers", () => reply(v, JSON.stringify({ ok: false, kind: "player." + v.kind, error: { code: "superseded", message: "intent " + v.seq + " is older than the recorded " + w.record }, id: v.id, seq: v.seq })))
      return
    }
    w.record = v.seq
    if (v.slowMs > 0) {
      const ms = v.slowMs
      v.slowMs = 0
      note(v.kind + " @" + v.seq + " holds the lock " + ms + " ms over a slow player")
      at(ms, "slow requests answered", () => { if (!v.dead) work(v) })
      return
    }
    work(v)
  }

  // What a verb does once it holds the lock and its seq stands.
  function work(v) {
    const p = w.player && w.player.alive ? w.player : null
    if (v.kind === "stop") {
      if (!p) { note("stop @" + v.seq + " finds nothing"); release(5); return }
      const ladder = rnd() < 0.65 ? between(20, 300) : between(2000, 7000)
      at(ladder, "ladder", () => kill(p, v))
      release(ladder + between(1, 100))
      return
    }
    if (p && v.kind === "start") {
      const took = between(40, 300)
      at(took, "adopted load", () => {
        if (w.holder === v) w.holder = null
        if (v.dead) return
        write(p, v)
        firstLoad(v, p, false, null)
      })
      return
    }
    if (p && v.kind === "restart") {
      // `--from term`: the TERM rung, then the spawn, still under the lock.
      at(between(20, 2000), "restart ladders", () => {
        if (v.dead) return
        kill(p, null)
        spawn(v)
      })
      return
    }
    if (p) kill(p, null)
    spawn(v)
  }

  function spawn(v) {
    const took = rnd() < 0.85 ? between(150, 400) : between(1500, 5000)
    const q = { pid: ++w.nextPid, alive: true, bound: false, channel: "", zapped: false, entries: 0 }
    w.players.push(q)
    at(Math.floor(took * 0.8), "spawn binds", () => { q.bound = true; w.player = q; note("player " + q.pid + " binds") })
    at(took, "spawn load", () => {
      if (w.holder === v) w.holder = null
      if (!q.alive || v.dead) return
      if (q.zapped) { note("start @" + v.seq + " stands down for " + q.channel); firstLoad(v, q, true, { id: q.channel, name: nameOf(q.channel) }); return }
      write(q, v)
      firstLoad(v, q, true, null)
    })
  }

  // The first-load window, after the lock is released: the load is seen
  // playing a moment later, unless the player dies first.
  function firstLoad(v, p, spawned, newer) {
    p.entries++
    const ok = (state, extra) => JSON.stringify({ ok: true, kind: "player." + v.kind, spawned, pid: p.pid, id: v.id, name: nameOf(v.id), entryId: p.entries,
      seq: v.seq, firstLoad: Object.assign({ state, reason: "" }, extra || {}), warnings: newer ? ["a newer channel change reached the player first"] : [],
      applied: newer === null, playing: newer })
    if (newer) { at(between(5, 30), "start answers", () => reply(v, ok("unknown"))); return }
    const seen = between(100, 1500)
    const watch = { done: false }
    at(seen, "first load seen", () => { if (watch.done) return; watch.done = true; reply(v, ok(p.alive ? "playing" : "failed", p.alive ? {} : { reason: "mpv exited", ended: "closed" })) })
    p.onDeath = () => { if (watch.done) return; watch.done = true; at(between(1, 10), "first load closed", () => reply(v, ok("failed", { reason: "mpv exited", ended: "closed" }))) }
  }

  function stashOf(p) {
    return p.channel === "" ? null : { schema: 1, playing: true, id: p.channel, name: nameOf(p.channel), group: "G", launchedFrom: "", sourceKey, since: 1, entryId: p.entries, seq: w.record, verb: "start" }
  }

  function probeReply() {
    const p = w.player && w.player.alive && w.player.bound ? w.player : null
    if (!p) return JSON.stringify({ ok: true, kind: "player.probe", running: false, responsive: false, pid: null, idle: null, stash: null, owner: null, seq: w.record, claimed: false, rewind: null, tls: null })
    const stash = stashOf(p)
    return JSON.stringify({ ok: true, kind: "player.probe", running: true, responsive: true, pid: p.pid, idle: stash === null, stash, owner: null, seq: w.record, claimed: true, rewind: null,
      tls: { verify: true, optionCount: 0, unpinned: 0, migrated: false } })
  }

  function reply(v, text) {
    if (w.slot !== v || v.answered) return
    v.answered = true
    w.slot = null
    note("reply " + v.kind + (v.kind !== "probe" ? " @" + v.seq : "") + " " + (text === "" ? "(nothing)" : text.slice(0, 90)))
    pRunning = false
    h.root.handlePlayerResult(text)
    h.drain()
    note("  shell: " + shellState())
  }

  function controlReply(v, text) {
    if (w.control !== v) return
    w.control = null
    note("reply control " + text.slice(0, 80))
    cRunning = false
    h.root.handleControlResult(text)
    h.drain()
    note("  shell: " + shellState())
  }

  function shellState() {
    const r = h.root
    return "stopping " + r.stopping + ", userStopped " + r.userStopped + ", now " + (r.nowPlaying ? r.nowPlaying.id : "-") + ", queued " + (r.pendingPlayId || "-")
      + ", attached " + r.socketAttached() + ", stopSeq " + r.stopSeq
  }

  function pump() {
    if (w.holder === null && w.waiters.length > 0) grant(w.waiters[Math.floor(rnd() * w.waiters.length)])
  }

  // Run the world and the shell's Timers up to `ms` from now, in time order.
  w.advance = (ms) => {
    const end = h.clock + ms
    for (let guard = 0; guard < 100000; guard++) {
      pump()
      const next = w.events.reduce((b, e) => (b === null || e.at < b.at || (e.at === b.at && e.n < b.n)) ? e : b, null)
      const due = h.timed.filter(([t]) => t.running && t.armedInterval !== null).reduce((m, [t]) => Math.min(m, t.armedAt + t.armedInterval), Infinity)
      const worldAt = next === null ? Infinity : next.at
      if (Math.min(worldAt, due) > end) { h.elapse(end - h.clock); return }
      if (due <= worldAt) { h.elapse(Math.max(0, due - h.clock)); continue }
      h.elapse(Math.max(0, worldAt - h.clock))
      w.events.splice(w.events.indexOf(next), 1)
      next.fn()
    }
    throw new Error("player-world: no end in sight")
  }
  w.quiet = () => w.events.length === 0 && w.waiters.length === 0 && w.holder === null && !pRunning && !cRunning
  // D-PLY-73: another launcher wants the lock now, and holds it past a
  // stop's wait once it has it (`contestP`, playerSequence).
  w.contest = () => {
    const v = { kind: "foreign", seq: 0, holdMs: between(LOCK_WAIT + 100, LOCK_WAIT + 2500) }
    note("another launcher wants the lock")
    wantLock(v)
  }
  w.rnd = rnd
  w.between = between
  w.note = note
  return w
}

// One seeded sequence: `steps` user plays and stops over `channels` (ids),
// the world run between them, then for `settleMs` after the last; -> the
// verdicts above, with the run's log. With `restartP`, before each action
// after the first the health path's restart is asked with that chance, and
// the action follows 0 to 600 ms later (no draw is made without it, so a
// sequence without it is the one it always was). With `contestP`, each user
// stop is contested by another launcher with that chance (the header), and
// the next action waits out the backstop too; likewise no draw without it.
// With `windowP` as well, that next action lands inside the contested stop's
// look's or backstop's probe with that chance (the header); no draw without
// it either. `slowP` is drawn per start or restart (the header).
function playerSequence(h, o) {
  const opts = o || {}
  const w = playerWorld(h, opts)
  const channels = opts.channels
  const actions = []
  let contested = false
  for (let k = 0; k < opts.steps; k++) {
    const r = w.rnd()
    const gap = r < 0.45 ? w.between(0, 120) : r < 0.8 ? w.between(120, 2500) : w.between(2500, 9000)
    // After a contested stop the next action waits out the stop's backstop
    // too, so it lands around the stop the shell then issues itself.
    const wait = contested ? w.between(h.root.stopSettleMs, h.root.stopSettleMs + 4000) : 0
    // D-PLY-75: or inside that stop's look's or backstop's probe, which goes
    // out a stop's look interval or its backstop's after the stop.
    const inProbe = contested && opts.windowP && w.rnd() < opts.windowP
      ? (w.rnd() < 0.5 ? h.root.stopLookMs : h.root.stopSettleMs) + w.between(1, 250) : 0
    contested = false
    w.advance(inProbe > 0 ? inProbe : gap + wait)
    if (opts.restartP && k > 0 && w.rnd() < opts.restartP) {
      w.note("HEALTH restart")
      h.root.restartPlayer()
      h.drain()
      w.advance(w.between(0, 600))
    }
    const stop = k > 0 && w.rnd() < 0.45
    let chosen = ""
    if (stop) {
      w.note("USER stop")
      h.root.stop()
      if (opts.contestP && w.rnd() < opts.contestP) {
        w.contest()
        contested = true
      }
    } else {
      chosen = channels[Math.floor(w.rnd() * channels.length)]
      w.note("USER play " + chosen)
      h.root.play(chosen, true, "")
    }
    h.drain()
    actions.push({ stop, id: chosen, cards: cardsOf(h).length })
  }
  w.advance(opts.settleMs)
  const last = actions[actions.length - 1]
  if (!last.stop && (h.root.playerUp || h.root.nowPlaying !== null)) {
    w.note("HEALTH tick")
    h.fireTimer("healthTimer")
    h.drain()
    w.advance(10000)
  }
  const verdict = { one: [], two: "", twoB: [], three: "", quiet: w.quiet(), log: w.log }
  for (const s of w.stops) {
    if (!s.laddered) continue
    for (const x of w.writes) if (x.pid === s.laddered && x.issue > s.issue) verdict.one.push(x.by + " " + x.id + " into " + x.pid + " after stop @" + s.seq + " that laddered it")
  }
  const cards = cardsOf(h)
  const p = w.player && w.player.alive ? w.player : null
  if (!last.stop) {
    const plays = p !== null && p.channel === last.id && h.root.nowPlaying !== null && String(h.root.nowPlaying.id) === last.id
    if (!plays && cards.length === last.cards) verdict.two = "the last play (" + last.id + ") dropped in silence: the world plays " + (p ? p.channel || "(idle)" : "nothing") + ", the shell names " + (h.root.nowPlaying ? h.root.nowPlaying.id : "nothing")
  } else if (p !== null) {
    verdict.three = "a player plays " + (p.channel || "(idle)") + " after the last stop"
  }
  for (const c of cards) if (!/The player is busy$/.test(c)) verdict.twoB.push(c)
  return verdict
}

function cardsOf(h) {
  return h.detached.filter(a => a[0] === "omarchy-notification-send").map(a => a[a.indexOf("-r") + 1] + " " + a[a.length - 2] + " | " + a[a.length - 1])
}

module.exports = { rng32, playerWorld, playerSequence, cardsOf }
