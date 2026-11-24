// Service-rewind.js -- a code-behind of Service.qml (D-REL-14). Each function here was
// moved byte for byte out of Service.qml, which reaches it through a
// one-line forwarder left at its old place; it runs in Service.qml's own
// scope. Edit a function here, never its forwarder.

  // The queue's own three fields, and what the service knows about the world
  // when an event reaches it (F-RWD-19). Every DECISION below is
  // Model.seekQueueStep's; these two compose its arguments out of Qt state
  // and nothing else, so a reader can see exactly what the reducer is told.
  function seekState() {
    return { pending: root.seekPending, liveQueued: root.seekLiveQueued, atFloor: root.seekAtFloor }
  }

  function seekCtx() {
    return {
      playing: root.playing, stopping: root.stopping, userStopped: root.userStopped,
      controlBusy: controlProc.running, throttled: seekThrottle.running,
      rewind: root.rewind, socket: root.socketPath,
      pendingPlayId: root.pendingPlayId, currentEntryId: root.currentEntryId,
      stepS: Model.REWIND_STEP_S
    }
  }

  // The one place a plan becomes Qt state: property writes, the timer, the
  // single control slot. Nothing here chooses anything. Returns the plan's
  // reply, which is what the IPC verbs serialise and the guide reads.
  function applySeekPlan(plan) {
    root.seekPending = plan.state.pending
    root.seekLiveQueued = plan.state.liveQueued
    root.seekAtFloor = plan.state.atFloor
    if (plan.clearReadout) {
      root.rewind = null
      seekThrottle.stop()
    }
    if (plan.readout) {
      // `rewind` is null, never {}, until the player says; a reading of
      // "none" restamps the zero point the same as a reading of numbers.
      if (plan.readout.clear) root.rewind = null
      else if (plan.readout.store) {
        root.rewind = plan.readout.rewind
        root.rewindAtSec = Math.floor(Date.now() / 1000)
        root.behindTickSec = root.rewindAtSec
      }
    }
    // The 300 ms throttle counts from THIS reply; the throttle timer
    // re-drives the queue when it elapses.
    if (plan.restartThrottle) seekThrottle.restart()
    if (plan.argv.length === 0) return plan.reply
    if (root.runControl("seek", plan.argv)) return plan.reply
    // A spawn the reducer asked for and runControl did not give us. runControl
    // refuses only while the slot is busy, which the reducer checked in the
    // same synchronous turn, so this is unreachable by construction rather
    // than a live path -- and it is here because "applying" for a run that
    // never happened is the false success CN15 forbids. The sum is spent
    // either way, exactly as it was before this refactor.
    root.seekPending = 0
    root.seekLiveQueued = false
    return root.seekRefuse(plan.reply && plan.reply.requested !== undefined ? plan.reply.requested : 0, "busy")
  }

  // Every reply that carries a `rewind` object refreshes the state --
  // `status`, `pause`, `probe` and `seek` all do. What a reply MEANS is
  // Model.rewindApply: whether to store, the coerced object, whether to
  // clear, and the at-floor memory after it. The entry-id drop and the
  // floor-clear rule live there (F-RWD-19).
  function applyRewind(status) {
    var readout = Model.rewindApply({ status: status, currentEntryId: root.currentEntryId,
                                      atFloor: root.seekAtFloor, stepS: Model.REWIND_STEP_S,
                                      // F-RWD-24: a queued play means every reading in
                                      // flight is the stream the user has left.
                                      zapping: root.pendingPlayId !== "" })
    root.seekAtFloor = readout.atFloor
    if (readout.clear) { root.rewind = null; return }
    if (!readout.store) return
    root.rewind = readout.rewind
    root.rewindAtSec = Math.floor(Date.now() / 1000)
    root.behindTickSec = root.rewindAtSec
  }

  // The player went away and the queue was aimed at it: play(), stop() and
  // the socket's EOF. What `clear` resets is the reducer's answer, so the
  // list cannot drift away from the one the queue itself keeps.
  function clearRewind() {
    root.applySeekPlan(Model.seekQueueStep(root.seekState(), { kind: "clear", ctx: root.seekCtx() }))
  }

  function seekRefuse(requested, code) {
    return Model.seekRefusal(requested, code, root.rewind)
  }

  // A relative seek of `seconds` (negative is back). Returns the reply the
  // IPC verbs serialise: accepted requests say "applying" when the helper
  // was spawned now and "queued" when the press coalesced behind a run in
  // flight or the throttle; refusals carry a code. Which of those it is --
  // and the refusals, and the coalescing, and the at-floor memory -- is
  // Model.seekQueueStep's decision, not this function's.
  function seekBy(seconds) {
    return root.applySeekPlan(Model.seekQueueStep(root.seekState(),
                                                  { kind: "press", by: seconds, ctx: root.seekCtx() }))
  }

  // Back to the live edge, or as near as the cache reaches (ruling D8): the
  // helper seeks to the range end minus 0.5 s and the reply says what
  // remains. It never re-tunes; only Enter on the row reloads.
  function seekLive() {
    return root.applySeekPlan(Model.seekQueueStep(root.seekState(),
                                                  { kind: "live", ctx: root.seekCtx() }))
  }

  // Drive the queue: spawn the queued seek if the slot is free and the
  // throttle has elapsed. Called from the throttle timer and after every
  // control reply (the press drives it through seekQueueStep itself).
  function issueSeek() {
    root.applySeekPlan(Model.seekQueueStep(root.seekState(), { kind: "issue", ctx: root.seekCtx() }))
  }

  // M3-02 (PLAN-M3 decision 5). Ask the player for its tracks, selecting
  // one first when `select` is { type, id }. "" when issued, "queued" when
  // another control holds the channel, "idle" when nothing plays.
  function requestTracks(select) {
    if (!root.nowPlaying) {
      root.clearTracks()
      return "idle"
    }
    root.tracksWanted = true
    root.tracksState = "asking"
    root.tracksAsking = String(root.nowPlaying.id || "")
    root.tracksAskedFor = root.tracksAsking
    if (!root.runControl("tracks", Model.playerTracksArgv(root.socketPath, select || null))) {
      root.tracksQueued = { select: select || null }
      return "queued"
    }
    return ""
  }

  // One `status` to the player, deferred so it is issued after the reply
  // that asked for it has finished unwinding (the channel is one at a time).
  // The `status` branch of handleControlResult, in Service.qml, is the only
  // place that learns pause, the channel and the health verdict from the
  // player itself.
  function askPlayerStatus() {
    if (root.userStopped || root.stopping || !root.playerUp) { root.statusQueued = false; return }
    // Keeps asking until the channel is free. runControl returns false while
    // another control holds it, and the caller used to discard that.
    root.statusQueued = !root.runControl("status", ["status", "--socket", root.socketPath])
  }

  function cancelTracks() {
    root.tracksWanted = false
    root.tracksQueued = null
    root.tracksAsking = ""
    root.tracksAskedFor = ""
    root.tracksRecoveries = 0
  }

  // The channel changed under an open picker and the play has now landed.
  function refreshTracks() {
    if (!Model.shouldRefreshTracks({
          wanted: root.tracksWanted,
          playingId: root.nowPlaying ? String(root.nowPlaying.id || "") : "",
          rowsFor: root.tracksFor,
          askedFor: root.tracksAskedFor,
          recoveries: root.tracksRecoveries })) return
    root.tracksRecoveries += 1
    root.requestTracks(null)
  }

  function clearTracks() {
    root.tracks = []
    root.tracksFor = ""
    root.tracksAsking = ""
    root.tracksAskedFor = ""
    root.tracksRecoveries = 0
    root.tracksState = "idle"
    root.tracksQueued = null
    root.tracksWanted = false
  }

  function issueQueuedTracks() {
    var queued = root.tracksQueued
    if (!queued) return
    root.tracksQueued = null
    root.requestTracks(queued.select)
  }

  // Pause or resume what is playing. Returns false when there is nothing to
  // pause, so a caller can say so rather than appearing to work.
  //
  // The local flip is applied at once and the helper confirms it on the next
  // health tick: the bar must not wait a process launch to show the state the
  // user just asked for (rule 9). A refusal corrects it within a tick.
  // -> "" on success, else a reason. Two different failures used to share one
  // `false` and the guide said "Nothing is playing" for both, including when
  // something WAS playing and the helper slot was merely busy. A message that
  // is wrong about why is worse than no message.
  function togglePause() {
    if (!root.nowPlaying) return "idle"
    var want = !root.paused
    if (!root.runControl("pause", Model.playerPauseArgv(root.socketPath, want ? "on" : "off"))) return "busy"
    root.paused = want
    return ""
  }
