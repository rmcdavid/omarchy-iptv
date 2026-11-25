// Service-player.js -- a code-behind of Service.qml (D-REL-14). Each function here was
// moved byte for byte out of Service.qml, which reaches it through a
// one-line forwarder left at its old place; it runs in Service.qml's own
// scope. Edit a function here, never its forwarder.

  // D-REL-16. This file's build stamp: the version of the last cut that
  // changed it, written by build_stamps.py (dev branch) at the cut. The first
  // function here, because a move appends at the end; Service.qml reads it
  // through its forwarder.
  function buildStampPlayer() { return "0.20.0" }

  // Start (or switch to) a channel by id. `keepOpen` true = preview from the
  // guide (no focus change); false = close-and-focus semantics, the service
  // only does the focus part. `launchedFrom` is the zap ring scope
  // (Model.launchScope); defaults to the channel's own group.
  function play(id, keepOpen, launchedFrom) {
    var channel = root.channelIndex[String(id || "")]
    if (!channel || !channel.url) return false
    if (!root.mpvAvailable) {
      root.runWhichMpv()
      root.notify("mpvMissing", {})
      return false
    }
    var key = Model.channelId(channel)
    // Enter on the row already playing: no reload, just focus (UX 8 #4).
    // A false negative here costs one redundant `player start`, which adopts
    // the live player and re-zaps it (4.7). It is cheap, not free: an
    // adopting start re-applies its own channel over anything that landed
    // while it was adopting, and nothing orders the two (D-PLY-11 T-A, and
    // ruling CL4 withholds the instrument that would). That ordering has
    // never been observed to fire - 0 in 30 live bursts - but "only costs"
    // overstated what is known and it is corrected here.
    // Restart on adoption: not while another build's player is owed its
    // replacement -- the row's id may even be another source's channel (a
    // deferred stash) -- so Enter there is the replacement, at live.
    if (root.zapReady && root.nowPlaying && root.nowPlaying.id === key) {
      // Re-selected from another list: the zap ring follows the list the
      // user is in (UX 3.4, D-LIVE-12). A new object so bindings notice.
      var from = String(launchedFrom || "")
      if (from !== "" && from !== String(root.nowPlaying.launchedFrom)) {
        root.nowPlaying = {
          id: root.nowPlaying.id,
          name: root.nowPlaying.name,
          group: root.nowPlaying.group,
          launchedFrom: from,
          since: root.nowPlaying.since
        }
      }
      if (!keepOpen) root.focusPlayer()
      return true
    }
    var nowSec = Math.floor(Date.now() / 1000)
    root.userStopped = false
    root.relaunchPending = false
    root.relaunched = false
    root.playRetries = 0
    relaunchTimer.stop()
    playRetryTimer.stop()
    root.healthFailures = 0
    root.lastError = ""
    // A new play is never paused: the flag belongs to the stream that was
    // playing, and carrying it over would show a pause nobody asked for.
    root.paused = false
    // M5-01: and it has no history. Every loadfile empties the cache and
    // restarts the timeline at zero (spike 11.1), so the readout goes absent
    // -- not to zero -- until the player reports again, and a seek that was
    // waiting its turn was aimed at the stream this play replaces.
    root.clearRewind()
    // D-SINK-16: and it subsumes a reload owed for the channel this play
    // replaces. The load about to go out asserts the same properties and
    // refuses rather than loads, so re-establishing the old channel afterwards
    // would buy a second rebuffer and nothing else.
    root.tlsReloadPending = false
    // A new play puts the last failure behind us: the next guide open is a
    // fresh start, not a come-back.
    root.lastFailedId = ""
    if (Model.hasOwnKey(root.failedAt, key)) {
      root.failedAt = Model.withoutFailed(root.failedAt, key)
      root.persistFailed("clear", key)
    }
    root.notifiedFailureId = ""
    // A play cancels a pending stop-confirmation: the player that is coming
    // up is wanted, whatever the one before it did.
    root.stopConfirmPending = false
    root.stopConfirmLook = false
    root.playSeq += 1                       // every play is a new intent (4.10)
    root.previousPlaying = root.playerUp ? root.nowPlaying : null
    root.previousPlayingSeq = root.playSeq
    // D-PLY-58: the channel is this source's from here on. The key was set
    // only by an adoption (applyProbe) and outlived it, so every later play
    // still read as the adopted stash's source.
    root.playerSourceKey = root.activeSourceKey
    root.nowPlaying = {
      id: key,
      name: String(channel.name || ""),
      group: Model.primaryGroup(channel),
      launchedFrom: String(launchedFrom || "") || Model.groupScopeId(Model.primaryGroup(channel)),
      since: nowSec
    }
    root.userState = Model.recordPlayed(root.userState, channel, root.maxRecents, nowSec)
    root.sessionConsumed = false        // a new record, not the spent one
    // A PO-3 mark owed from before this play was about the record this play
    // has just replaced. Leaving it owed would land it on the channel now
    // starting, which is the opposite of what PO-3 is for.
    root.deadSessionPending = false
    root.saveState()
    root.wantFocus = !keepOpen
    root.channelRepairs = 0             // a new intent, a fresh repair budget
    // The fork (Model.playFork). `player start` is idempotent - it adopts a
    // live player and zaps it - so a wrong answer costs one extra ~130 ms
    // helper run. It was recorded here that the fork is "never a correctness
    // gate"; that was asserted, never measured, and it is now known to be
    // too strong. `playerPending` makes `playerUp` true synchronously, so
    // every call after the first in a COLD burst takes the zap branch and
    // aims at a socket mpv has not bound yet; wave two measured what happens
    // when one of those lands and the cold start then applies its own
    // channel over it - ten user-visible divergences in twenty cold bursts.
    // The fork stays as it is (a zap aimed at a socket that is about to
    // exist is how a burst stays responsive, and ruling CL4 withholds the
    // instrument that would order the two slots); what was fixed is the far
    // end, where the start now stands down instead of overwriting, and this
    // shell re-applies its intent when the two disagree.
    //
    // While `stopping` is true we always take the start branch, so a zap can
    // never be written to a socket that is being torn down (4.10). And while a
    // restart of another build's player is owed (restart on adoption), the
    // start branch too: the start replaces that player and plays this channel
    // in one call. The decision is Model.playFork, called (F-GATE-18, rule
    // 12): it used to be a statement of this fork, not a call of it.
    // A channel change while a restart is owed IS the replacement: the
    // automatic one is spent, so it can neither fire over this intent nor
    // lend it the old player's pause (Model.olderRestartKeepsPause).
    if (root.olderRestart && root.olderRestart.spent !== true) {
      root.olderRestart = Model.olderRestartWith(root.olderRestart, { spent: true })
      olderRestartTimer.stop()
    }
    var fork = Model.playFork({ socketAttached: root.socketAttached(), playerPending: root.playerPending,
                                stopping: root.stopping, controlBusy: controlProc.running,
                                restartOwed: root.olderRestartOwed })
    if (fork === "start") {
      root.startPlayer(channel)
      return true
    }
    if (fork === "queue") {
      // A zap burst: remember only the last target, applied when the
      // current helper call returns.
      root.pendingPlayId = key
    } else {
      root.runControl("play", root.playArgs(key))
    }
    if (root.wantFocus) root.focusPlayer()
    return true
  }

  // `play --id ... --scope ... --since ...`: the additive session flags make
  // a zap refresh the now-playing stash inside mpv, which is what lets a
  // shell restart recover the channel the user last switched TO rather than
  // the one the player was started with (4.6, requirement 11). The rule is
  // Model.zapArgs (engineering rule 12 (dev branch)) - it was the one argv builder still spelled
  // here, and the decision it makes reaches all the way into the helper.
  function playArgs(key) {
    return Model.zapArgs(root.socketPath, root.activeCacheDir, key, root.nowPlaying)
  }

  // The UI contract is unchanged: nowPlaying and the timers clear
  // synchronously, so the bar and the guide drop the channel on the
  // keystroke. The ladder itself - quit, SIGTERM at 2 s, SIGKILL at 4 s -
  // now runs inside ONE detached helper (4.9), which is strictly stronger
  // than the QML version: no rung can be starved behind a busy control
  // channel, the pid comes from /proc so a wedged mpv is reachable, and the
  // ladder completes even if this shell is killed one millisecond from now.
  // A user stop never notifies. Issued unconditionally: `player stop`
  // against nothing is a cheap no-op that also tidies a stale socket.
  function stop() {
    root.pendingPlayId = ""
    root.wantFocus = false
    focusTimer.stop()
    // Nothing queued may resurrect the player after a stop (D-LIVE-15).
    relaunchTimer.stop()
    playRetryTimer.stop()
    playerSocketTimer.stop()
    root.relaunchPending = false
    root.playRetries = 0
    root.channelRepairs = 0
    root.nowPlaying = null
    root.userStopped = true
    root.playerPending = false
    // Restart on adoption: the stop ends the older player too (its own
    // ladder), so its replacement is owed to nothing.
    root.endOlderRestart()
    // M5-01: the history goes with the player; a press queued behind the
    // stop has nothing to seek in.
    root.clearRewind()
    // Stop hunting for a socket, but keep an attached one: its EOF is how
    // we learn the ladder finished (and is what clears `stopping`).
    root.playerWanted = false
    // D-PLY-75: a question the stop before this one still had open is this
    // stop's now. A confirmation probe in flight -- the 5 s look's or the
    // backstop's, after a user's stop or one the shell issued -- answers
    // stale once this stop moves `playSeq`, and applyProbe drops a stale
    // answer before the branch that clears the two flags; an answer that
    // was unreadable has left `stopConfirmPending` set as well, and so has
    // a backstop whose probe the busy slot refused (stopSettleTimer does
    // not read runPlayerProbe's answer: the flag waits for the slot's next
    // probe answer). Left set, they made this stop's look and backstop
    // skip, both returning while a confirmation is pending, so a player
    // that outlived the earlier stop and this one played on under an idle
    // bar. Two more questions were forgotten here the same way while the
    // earlier settle still ran: a start from before the earlier stop whose
    // player its backstop was still to look for (stopOlderStartOk), and the
    // player a stop the shell issued itself was laddering (stopByShell) --
    // with nothing attached this stop had no way to learn that either
    // outlived it. And so were two that no stop opened (the review of
    // 8504ba8): the re-read a probe that found a player idle still owes
    // (`probeRetried`, while its 500 ms run or its probe is out), which
    // this stop overrules (probeRetryTimer) and which was then the only
    // look at that player; and any probe in flight -- the reattach's at a
    // shell start, D-PLY-35's of a start its watchdog stopped, the hunt's
    // -- whose answer this stop makes stale, so that the player it would
    // have found was looked for by nothing. So the flags are cleared, and
    // when any of those questions was open this stop's own look and
    // backstop look even with nothing attached, as after an older start's
    // ok: at most two probes, each finding nothing when this stop took.
    var asking = root.stopConfirmPending || root.probeRetried
      || (playerProc.running && root.playerKind === "probe")
      || (root.stopping && (root.stopOlderStartOk || root.stopByShell))
    root.stopConfirmPending = false
    root.stopConfirmLook = false
    root.stopByShell = false
    root.playSeq += 1
    root.stopSeq = root.playSeq
    root.stopAt = Date.now()
    root.stopOlderStartOk = asking
    // D-PLY-73: the user's stop is looked at by its backstop whatever the
    // settle before it was.
    root.stopFromBackstop = false
    stopSettleTimer.restart()
    stopLookTimer.restart()
    // The user asked for it, so nothing died unattended: the session record
    // has done its job and a reattach must not find it (PO-3 would then mark
    // a perfectly good channel red).
    root.noteSessionOutcome("stopped")
    Quickshell.execDetached(Model.helperArgv(root.helperPath, Model.playerStopArgv(root.socketPath, root.playSeq)))
  }

  // Health verdict: the player is unresponsive. `player restart --from term`
  // runs the ladder and the spawn under ONE lock acquisition, which removes
  // the stop-then-start race two independent detached calls would have; IPC
  // is by definition not answering here, so rung 1 is skipped. The
  // bookkeeping is unchanged: one automatic relaunch per player.
  function restartPlayer() {
    if (!root.playerUp || root.stopping) return
    if (!root.nowPlaying) return
    if (!Model.adoptedSourceMatches(root.playerSourceKey, root.activeSourceKey)) {
      // D-PLY-58: the player was adopted on another source's channel, and a
      // restart re-resolves the id against THIS source's cache, so it would
      // come back on this source's channel of the same id under the old
      // name. There is nothing here to relaunch it to: it ends, as a player
      // whose one relaunch is spent does.
      console.warn("omarchy-iptv: mpv unresponsive on another source's channel, stopping the player")
      root.stop()
      return
    }
    var channel = root.channelIndex[root.nowPlaying.id]
    if (!channel) return
    if (root.relaunched) {
      // The one automatic relaunch for this player is spent: ladder it down
      // and show idle, which is what the QML ladder did with
      // relaunchPending false (a quit exits 0, i.e. silently).
      console.warn("omarchy-iptv: mpv unresponsive again, stopping the player")
      root.stop()
      return
    }
    if (playerProc.running) {
      // The one player slot is busy (a start or a probe): try again in a
      // moment rather than dropping the verdict.
      root.relaunchPending = true
      relaunchTimer.restart()
      return
    }
    console.warn("omarchy-iptv: mpv unresponsive, restarting player")
    root.healthFailures = 0
    root.healthSkips = 0
    root.relaunchPending = !root.relaunched && root.nowPlaying !== null
    root.relaunched = true
    root.playSeq += 1
    root.issuePlayerSession("restart", channel, "term")
  }

  function zap(delta) {
    if (!root.nowPlaying) return false
    var ring = Model.zapRing(root.channels, root.userState, root.nowPlaying)
    var hop = Model.zapStep(ring, root.nowPlaying.id, delta, root.failedAt)
    if (!hop.channel) return false
    root.zapSkipped = hop.skipped
    // Say so. Skipping rows the user can see without telling them would be
    // the guide lying about state (UX principle 4) -- and an unwired notice
    // is exactly what the 0.7.10 preflight caught: the composer existed, the
    // property was set, and nothing ever read either of them.
    if (hop.skipped > 0) root.zapSkippedDead(Model.zapSkipNotice(hop.skipped))
    return root.play(Model.channelId(hop.channel), true, root.nowPlaying.launchedFrom)
  }

  // The channel a typed number resolves to, or null (M2-03 3.2). Exact match
  // first, else the lowest number that starts with it; NO duplicate cycling,
  // because a script asking for 12 must get the same channel every time.
  //
  // Resolved against the playlist-order array the index was built from, never
  // against root.channels: with channelOrder "number" those two disagree on
  // every position (5.2).
  function channelByNumber(text) {
    var base = root.preparedActive ? root.preparedActive.channels : root.channels
    return Model.channelByNumber(base, root.chnoIndex, text)
  }

  // D-PIP-5. Focus is read-then-act now, like every other window command
  // this plugin issues. The D-PIP-1 repair fixed the spelling and kept the
  // selector, which was `class:omarchy-iptv`; with a user's own
  // `mpv --wayland-app-id=omarchy-iptv` open, the live pass watched it focus
  // the STRANGER'S window three times out of three. Design 4.2 had already
  // ruled that narrowing by pid is not optional - focus was the one verb
  // nobody applied it to.
  //
  // So there is nothing to dispatch until the compositor has been asked
  // which window is ours, and the focus retry timer (UX 7.5) was built for
  // exactly that wait: the mpv window maps a moment after launch. mpv binds
  // its IPC socket before the video output creates a surface, so the pid is
  // known by the time there is a window to aim at, and an attempt made
  // before then simply resolves nothing and retries.
  function focusPlayer() {
    // A read already in flight answers this one too. Anything else the gate
    // refuses - no pid, a PiP sequence in progress - means there is nothing
    // coming and nothing to aim at, so the intent is dropped rather than
    // held forever.
    if (root.pipPeek() || root.pipPeeking) {
      root.pipFocusPending = true
      return true
    }
    root.pipFocusPending = false
    return false
  }

  // The one place a focus command leaves this plugin. `address` came out of
  // the pid-narrowed lookup; the builder checks it again against the address
  // pattern (PIP7) and answers [] rather than a guess, so an empty vector
  // means "we cannot say which window", never "focus whatever matches".
  function dispatchFocus(address) {
    var argv = Model.focusPlayerArgv(address)
    if (argv.length === 0) return false
    Quickshell.execDetached(argv)
    // The retry loop (UX 7.5) exists because the mpv window maps a moment
    // after launch and a focus dispatched before then reaches nothing. We
    // only get here with a window the compositor listed a few milliseconds
    // ago, so this one lands and there is nothing left to retry. Before
    // D-PIP-5 nothing could know that, and the loop dispatched its whole
    // budget every time.
    root.wantFocus = false
    root.focusAttempts = 0
    focusTimer.stop()
    return true
  }

  function runControl(kind, args) {
    if (controlProc.running) return false
    root.controlKind = kind
    root.runHelper(controlProc, Model.helperArgv(root.helperPath, args), {})
    controlWatchdog.restart()
    return true
  }

  function handleControlResult(text) {
    controlWatchdog.stop()
    var kind = root.controlKind
    root.controlKind = ""
    var status = Model.parseHelperStatus(text, kind)
    // M3-02: a queued tracks request goes out once this handler is done,
    // whatever this reply was. Deferred rather than inline because the
    // branches below return early and some issue a control of their own.
    if (root.statusQueued) Qt.callLater(root.askPlayerStatus)
    if (root.tracksQueued) Qt.callLater(root.issueQueuedTracks)
    // M5-01: a press that coalesced behind this run goes out once the
    // handler is done. Deferred for the same reason as the two above, and
    // AFTER the drain at the bottom takes the slot synchronously: a zap
    // queued behind this reply outranks a seek, which play() has by then
    // dropped as aimed at the previous stream.
    if (Model.seekQueuePending(root.seekState())) Qt.callLater(root.issueSeek)
    // Whatever this reply was, an open picker may ask again -- the whole
    // rule is Model.shouldRefreshTracks, which is a function and not a
    // conjunction here precisely because two comments in a row described a
    // rule this code did not have. The last of them said "at most once per
    // channel", and the same commit that wrote it added the recovery edge
    // in the healthy-status branch below, which makes it once per channel
    // per observed-alive edge. Read the function.
    else if (Model.shouldRefreshTracks({
               wanted: root.tracksWanted,
               playingId: root.nowPlaying ? String(root.nowPlaying.id || "") : "",
               rowsFor: root.tracksFor,
               askedFor: root.tracksAskedFor,
               recoveries: root.tracksRecoveries })) Qt.callLater(root.refreshTracks)
    if (kind === "tracks") {
      // The helper is authoritative (decision 5): the rows are what mpv has
      // AFTER any selection, never what was asked.
      // A reply for a channel that is no longer playing describes the wrong
      // file: drop it and leave the panel asking, so the re-ask above fires.
      var asked = root.tracksAsking
      root.tracksAsking = ""
      var playingId = root.nowPlaying ? String(root.nowPlaying.id || "") : ""
      if (asked !== "" && asked !== playingId) {
        root.drainPendingPlay()
        return
      }
      if (status.ok === true && status.running === true) {
        root.tracks = Model.parseTracks(status)
        root.tracksFor = playingId
        root.tracksState = "ready"
      } else if (status.ok === true) {
        // The helper says no player answered. That is "did not answer", not
        // "nothing is playing": nowPlaying, the bar and the highlighted row
        // all still name the channel, and a panel contradicting them is a
        // panel the user has to decide between.
        root.tracks = []
        root.tracksFor = ""
        root.tracksState = root.nowPlaying ? "failed" : "idle"
      } else {
        root.tracksState = "failed"
      }
      // A zap queued behind this reply must not wait for the health tick:
      // this branch returns early on two paths (a stale-channel reply and a
      // failed one), so it owes the drain itself. The `pause` branch does
      // the same below (D-PLY-23). This comment has been wrong about that
      // branch twice -- once saying the gap was filed when no id existed,
      // once saying a pause could never be in flight across a zap -- which
      // is why it now says only what is true of the branch it sits in.
      root.drainPendingPlay()
      return
    }
    if (kind === "seek") {
      // M5-01 (design 2.3). The helper read, clamped, seeked and read again;
      // its reply is the whole verdict and `success` from mpv was never
      // evidence (spike 11.4). Nothing here decides whether the seek moved:
      // the guide's transient and the bar's number come from the reply.
      //
      // A zap queued behind this run means the reply describes the stream
      // the user has already left: play() cleared `rewind` when the zap was
      // asked for, and the drain below spawns `play` directly, so writing
      // these numbers back would put the OLD stream's clock on the new
      // channel's bar for up to a health tick. Stale replies apply nothing
      // and say nothing (the tracks branch above does the same by channel).
      // And a reply that lands after stop() or the player's EOF describes a
      // player that is gone: nothing plays, so nothing is behind live, and
      // the guide would otherwise show a transient for it (review finding).
      // Both of those are Model.seekQueueStep's `reply` event: it decides
      // whether the reply is applied and announced, what it means for the
      // readout (through Model.rewindApply), the at-floor memory after it,
      // and that the 300 ms throttle counts from THIS reply rather than from
      // the press. applySeekPlan only obeys. A zap queued behind the seek
      // outranks any press that coalesced behind it: the press was aimed at
      // the stream the zap replaces, and play() has already dropped it.
      var seekPlan = Model.seekQueueStep(root.seekState(), { kind: "reply", status: status, ctx: root.seekCtx() })
      root.applySeekPlan(seekPlan)
      if (seekPlan.announce) root.seekReplied(status)
      // D-PLY-24: every path of a new branch owes the queued play its drain,
      // and this branch has only one path, so it is here and not in an else.
      root.drainPendingPlay()
      return
    }
    if (kind === "pause") {
      // M5-01: a `pause` reply carries the rewind numbers too (2.1), so the
      // bar's `-m:ss` is current from the key the user just pressed rather
      // than from the next 10 s status tick.
      root.applyRewind(status)
      // The helper is authoritative: the optimistic flip is corrected here if
      // the player refused, or if there was no player to ask.
      if (status.ok === true && status.running === true && status.paused !== undefined
          && status.paused !== null) {
        root.paused = status.paused === true
      } else if (status.ok === true && status.running !== true) {
        root.paused = false
      } else if (status.ok !== true) {
        // D-PLY-20's other half, found in the 0.9.0 preflight. Both branches
        // above require ok === true, so the REFUSAL -- the case the comment
        // above says is corrected here -- fell through and left the
        // optimistic flip from togglePause standing. That flag is not
        // internal: it drives the bar's glyph and tooltip and the footer's
        // resume hint, so the bar read "Paused" over a playing stream until
        // the ten-second health poll happened to correct it. A refusal
        // means we do not know, so ask: the `status` branch above is the
        // one place that learns the truth from the player itself. QUEUED
        // rather than issued, because the drain below takes the single
        // control slot synchronously while this was deferred -- so the ask
        // was refused by runControl and dropped, and the optimistic flip
        // stood for a health tick anyway. That is the defect D-PLY-20 was
        // filed for, reintroduced by D-PLY-23's own repair. Issued here AND
        // self-queueing: askPlayerStatus re-arms when the channel is busy,
        // and the next reply drains it. Setting the flag alone would strand
        // it whenever there was no queued play to produce that next reply.
        Qt.callLater(root.askPlayerStatus)
      }
      // D-PLY-23. Every branch that returns early owes the queued play its
      // drain, or a zap issued while this reply was in flight waits for the
      // ten-second health tick. The `tracks` branch was given this when it
      // was written; `pause` was left, and the comment there said a pause
      // could never be in flight across a zap -- which is false, `c` and the
      // bar wheel are one keystroke apart. Outside the if/else so it runs on
      // every path, including the refusal that issues a status of its own.
      root.drainPendingPlay()
      return
    }
    if (kind === "status") {
      var code = status.error ? String(status.error.code) : ""
      if (Model.statusHealthy(status)) {
        // A player observed ALIVE is the one edge on which an open picker
        // may ask again, and it is what D-TRK-6's bound took away: a single
        // `running: false` reply -- a cold start inside the socket-bind
        // window, or a wedge the health poll then restarts -- stamped the
        // channel as asked and nothing ever unstamped it, so the panel sat
        // on "the player did not answer" for the rest of that channel.
        // `statusHealthy` is false for the reply shape that caused the loop,
        // so this cannot restore it: a dead player still gets one ask.
        if (root.tracksWanted) root.tracksAskedFor = ""
        root.healthFailures = 0
        if (status.paused !== undefined && status.paused !== null) root.paused = status.paused === true
        // D-PLY-14: a healthy player that its own stash says is on this exact
        // channel is proof the channel plays, so any failure mark it still
        // carries is stale and goes. The only other clear runs when a play
        // STARTS, so without this a transient first-load error left a channel
        // the user was watching showing "Failed - Space to retry".
        var beforeHealthy = root.failedAt
        root.failedAt = Model.failedAfterHealthy(root.failedAt,
                                                 root.checkPlayerChannel(status),
                                                 root.nowPlaying)
        // D-PLY-14 clears in memory; the mark is durable now, so the clear
        // has to reach the file too or it returns at the next guide open.
        if (root.failedAt !== beforeHealthy && root.nowPlaying)
          root.persistFailed("clear", String(root.nowPlaying.id || ""))
        // M5-01 (2.3): the 10 s status tick re-syncs "behind live" from the
        // player, which also absorbs seeks made with mpv's own arrow keys --
        // live in the player window today, since the plugin passes no
        // --input-default-bindings override. AFTER the D-PLY-14 call above:
        // the node suite bounds that call's distance from the healthy test
        // as a proxy for "it sits in the healthy branch", and a block
        // inserted ahead of it is what turns the proxy red.
        root.applyRewind(status)
        // D-PLY-67: a player of this build whose relay no longer answers is
        // pinned to a port nothing of ours holds. The probe reads it as
        // older and what follows replaces or stops it, as at a shell start;
        // until this the tick did not ask, so with no zap it played on.
        if (Model.healthRelayAction(status.relay, { restartOwed: root.olderRestartOwed, slotBusy: playerProc.running,
                                                    stopping: root.stopping, userStopped: root.userStopped }) === "probe") {
          console.warn(Model.RELAY_GONE_LINE)
          root.runPlayerProbe()
        }
      } else if (Model.helperCannotTell(code)) {
        // The helper cannot tell (stub, crash, or a damaged part the stub
        // refused, D-REL-7): neither healthy nor a strike, so a missing
        // subcommand never reaps a working player.
        if (root.healthFailures === 0) console.warn("omarchy-iptv: status check unavailable:", Model.statusReason(status))
      } else {
        root.healthFailures += 1
        if (root.healthFailures >= root.healthFailuresBeforeRestart) root.restartPlayer()
      }
    } else if (kind === "play") {
      if (root.stopping) {
        // An answer from a player on its way out: nothing to retry or
        // restore, the next play() starts a fresh one (4.10).
        root.playRetries = 0
      } else if (status.ok !== true && status.error) {
        var reason = Model.statusReason(status)
        var verdict = Model.playFailureVerdict(status.error.code, {
          playerUp: root.playerUp,
          nowPlaying: root.nowPlaying !== null,
          userStopped: root.userStopped,
          retriesLeft: root.playRetries < root.playRetryMax
        })
        if (verdict === "start") {
          // The player vanished between two zaps. The `not_running` /
          // `still there` disambiguation collapses (4.7): `player start`
          // adopts a live player and spawns a dead one, so the same call is
          // right either way.
          root.lastError = reason
          var channel = root.channelIndex[root.nowPlaying.id]
          if (channel) root.startPlayer(channel)
        } else if (verdict === "retry") {
          // mpv did not answer in time, or something held the lock: retry
          // with backoff instead of losing the zap (D-LIVE-15).
          root.playRetries += 1
          playRetryTimer.interval = root.playRetryBaseMs * root.playRetries
          playRetryTimer.restart()
        } else if (verdict === "unknown") {
          // A reply we could not read, or one that never reached the player
          // at all. The status branch above has had this guard from the
          // start; the play branch fell into the rollback instead, which
          // WRITES nowPlaying with no load to match it - and then drains the
          // burst's last intent unconditionally two lines later.
          root.lastError = reason
          console.warn("omarchy-iptv: could not tell whether the channel changed:", reason)
        } else {
          root.lastError = reason
          console.warn("omarchy-iptv: play failed:", reason)
          // The switch did not happen; mpv still plays the previous channel.
          if (root.playerUp && root.previousPlaying) root.nowPlaying = root.previousPlaying
        }
      } else if (status.ok === true) {
        root.playRetries = 0
        root.previousPlaying = null
        // The zap's own entry id AND the zap's own channel, so a failure
        // that arrives after the next zap still names this one (4.8). Taking
        // the owner from nowPlaying recorded whichever intent happened to be
        // current when the REPLY landed - exactly the case the ring exists
        // for, and why the "Stream failed" toast could name a channel that
        // never failed.
        root.rememberEntry(status.entryId, Model.replyTarget(status, root.nowPlaying))
      }
    }
    // Apply the last queued zap of a burst.
    root.drainPendingPlay()
  }

  // The last target of a zap burst, applied once the channel is free. It
  // goes over IPC when the player is up and starts one when it is not; both
  // are the same user intent, so neither may be dropped.
  // D-PLY-43's sibling (rule 15): the same gate as the retry. It returned
  // while `stopping`, so a zap issued before a stop whose reply came after
  // it drained the queued last intent of a play made after the stop -- and
  // dropped it, the guide naming a channel the player never got. The user's
  // word gates it now, and the play fork's own branch (Model.playFork) sends
  // it to a start while the stop settles, never to the dying socket; a
  // start still in flight queues it again (startPlayer).
  // The review of 9d604cf: and only while it is still the guide's channel.
  // Every writer of pendingPlayId queues the id `nowPlaying` holds at that
  // moment, so one that is no longer `nowPlaying`'s was superseded by a play
  // that went out itself (a start through a free slot, or a zap) -- and
  // drained, it put the player on the older channel under the newer name
  // until a health tick's repair, now that a retry made while a stop settles
  // keeps the queue (D-PLY-43).
  function drainPendingPlay() {
    var id = root.pendingPlayId
    root.pendingPlayId = ""
    if (id === "" || root.userStopped || !root.nowPlaying) return
    if (String(root.nowPlaying.id) !== String(id)) return
    var fork = Model.playFork({ socketAttached: root.socketAttached(), playerPending: root.playerPending,
                                stopping: root.stopping, controlBusy: controlProc.running,
                                restartOwed: root.olderRestartOwed })
    if (fork === "zap") {
      root.runControl("play", root.playArgs(id))
      return
    }
    if (fork === "queue") {
      root.pendingPlayId = id
      return
    }
    var channel = root.channelIndex[id]
    if (channel) root.startPlayer(channel)
  }

  // Ruling CL5's repair, and the only one allowed: the shell holds the
  // user's intent, so when the player is on a different channel the fix is
  // to send the intent again. Relabelling nowPlaying from the player would
  // turn a visible reporting bug into a silent wrong channel - the user
  // watching something they did not choose, with the interface agreeing.
  function reapplyIntent(id) {
    var key = String(id || "")
    if (key === "" || root.stopping || root.userStopped) return false
    if (!root.nowPlaying || String(root.nowPlaying.id) !== key) return false
    // Restart on adoption: no zap into a player another build launched while
    // its replacement is owed (the helper would refuse it anyway).
    if (!root.zapReady) return false
    if (controlProc.running) {
      root.pendingPlayId = key
      return true
    }
    return root.runControl("play", root.playArgs(key))
  }

  // D-PLY-11's detection half. `status` now carries the player's own
  // now-playing record (4.6), so the health tick asks the one question it
  // never asked: which channel. Every divergence wave two produced was still
  // there two health ticks later, because nothing looked and nothing
  // corrected it. Under ruling CL6 the contract is that the label and the
  // player agree WITHIN ONE HEALTH TICK, which is exactly this.
  function checkPlayerChannel(status) {
    if (root.stopping || root.userStopped || !root.nowPlaying) return "unknown"
    var verdict = Model.reconcileVerdict(status.stash, root.nowPlaying, root.activeSourceKey)
    if (verdict.state === "agree") root.channelRepairs = 0
    if (verdict.state !== "diverged") return verdict.state
    if (root.channelRepairs >= root.channelRepairMax) return "diverged"
    root.channelRepairs += 1
    console.warn("omarchy-iptv: the player is not on the channel the guide names; re-applying it")
    root.reapplyIntent(verdict.repair)
    return "diverged"
  }

  // Cold start, and the recovery path for every "the player is not there"
  // answer. `playerPending` is set synchronously so the bar lights up on
  // this frame; the socket observer is armed in the same turn, so it is
  // already retrying when mpv binds ~150 ms later (4.4 step 13).
  function startPlayer(channel) {
    if (!channel) return
    root.mpvStderrTail = []
    root.lastEndFile = null
    root.currentEntryId = 0
    root.healthSkips = 0
    root.healthFailures = 0
    if (playerProc.running) {
      // The one player slot is busy: keep the intent and apply it when the
      // call in flight returns, the way a zap burst coalesces.
      root.playerPending = true
      root.playerWanted = true
      root.armPlayerSocket()
      root.pendingPlayId = Model.channelId(channel)
      return
    }
    root.issuePlayerSession("start", channel, "")
    if (root.wantFocus) {
      root.focusAttempts = 0
      focusTimer.restart()
    }
  }

  // `player start` / `player restart`: one helper call carrying the channel
  // id (never the URL), the intent seq, the zap-ring scope for the stash and
  // this shell's pid and this object's token as the owner claim (4.14,
  // D-PLY-64).
  function issuePlayerSession(verb, channel, fromRung) {
    var extra = Model.splitMpvArgs(root.mpvArgs)
    // D-SINK-24: option names only, redacted -- never the refused token whole.
    var rejectedLine = Model.mpvRejectedLine(extra.rejected)
    if (rejectedLine !== "") console.warn(rejectedLine)
    var np = root.nowPlaying
    var key = np ? String(np.id) : Model.channelId(channel)
    var scope = np ? String(np.launchedFrom || "") : ""
    var since = np ? Math.floor(Number(np.since) || 0) : 0
    // Restart on adoption: the episode's own automatic restart, and a retry
    // of it, keeps the replaced player's pause; a user's channel change, which
    // moves playSeq, never does (Model.olderRestartKeepsPause).
    var keepPause = Model.olderRestartKeepsPause(root.olderRestart, root.playSeq)
    var argv = verb === "restart"
      ? Model.playerRestartArgv(root.socketPath, root.activeCacheDir, key, root.playSeq, scope, since, extra.args, fromRung, Quickshell.processId, keepPause, root.ownerToken)
      : Model.playerStartArgv(root.socketPath, root.activeCacheDir, key, root.playSeq, scope, since, extra.args, Quickshell.processId, keepPause, root.ownerToken)
    root.sessionSocket = root.socketAttached() ? root.playerSocket : null
    root.sessionSeq = root.playSeq
    root.sessionInStop = root.stopping
    root.playerPending = true
    root.playerWanted = true
    root.armPlayerSocket()
    // D-PLY-72: after the arm. An observer on a player now -- kept, or
    // attached by this arm's own connect, which is synchronous (C5) -- is on
    // one that was there before the verb, which has not run yet: the verb
    // adopts it or ladders it (a restart, another build's, a wedged one).
    // And a restart ladders from `term` whatever it finds, and an owed start
    // replaces another build's player, whether or not the observer is on it
    // yet (a connect that fails now can reach it later in the flight).
    root.sessionOverPlayer = root.socketAttached() || verb === "restart" || root.olderRestartOwed
    return root.runPlayer(verb, argv)
  }

  // D-PLY-69: two stops outstanding around the start in the player slot --
  // it went out while an earlier stop still settled, and the user has
  // stopped again since (its seq is below `stopSeq`). An EOF that arrives
  // now may be the EARLIER stop's: that stop laddered the player the
  // observer was on, while the later stop has not run, and this start, its
  // seq past the earlier stop's, may yet adopt or spawn a player under the
  // lock -- the one the later stop then ladders.
  // D-PLY-72: and with one stop, the same EOF may be the start's OWN ladder:
  // a restart, an owed replacement or a start over the observed player
  // ladders the player it finds before it spawns, under the lock the stop
  // waits for, so the stop has still to ladder what it spawns. So such an
  // EOF ends the stop's settle for nothing (handlePlayerGone): the start's
  // own reply reads as a start from before the stop (stopOlderStartOk), and
  // a play after the stop goes out as a fresh start, which the lock and the
  // seq rule order after it. A start that went out with no stop settling
  // and over nothing it may ladder -- a cold start -- is the single stop's
  // case: the player its flight shows the observer is the one it spawns,
  // which only the stop ladders, so that EOF still ends the settle. One
  // exception is left, read and not built (D-PLY-72's row): a cold start
  // whose arm could not reach a player that was already there -- a wedged
  // one of this build, which the start then ladders -- when a later connect
  // of the hunt does reach it during the flight. At EOF nothing tells that
  // player from the start's own spawn, and holding every cold start would
  // undo the single stop's settle.
  function staleStartInFlight() {
    return playerProc.running && (root.playerKind === "start" || root.playerKind === "restart")
      && (root.sessionInStop || root.sessionOverPlayer) && root.sessionSeq < root.stopSeq
  }

  // D-PLY-78: the player of a start or restart issued before the last stop,
  // answering ok, refused or stopped by its watchdog with nothing named. A
  // verb that held the lock past the stop's wait outlived that stop, which
  // gave up, so its player is looked for: inside the settle by the backstop
  // (stopOlderStartOk), after it at once, as the backstop looks
  // (applyProbe's confirmation stops it if it is there). After the settle the
  // ok was read as the shell's own player to recover, adopted and named.
  function lookForWithdrawn() {
    if (root.stopping) {
      root.stopOlderStartOk = true
      return
    }
    root.stopConfirmPending = true
    root.stopConfirmLook = false
    root.runPlayerProbe()
  }

  // The player slot: its own Process with its own watchdog, so a cold start
  // can never starve a `play` or a `status` on controlProc (F1).
  function runPlayer(kind, args) {
    if (playerProc.running) return false
    root.playerKind = kind
    root.runHelper(playerProc, Model.helperArgv(root.helperPath, args), {})
    playerWatchdog.restart()
    return true
  }

  // Reattach (4.5): lock-free, side-effect-free except for one stale-socket
  // unlink, and it claims the player for this shell.
  function runPlayerProbe() {
    if (playerProc.running) return false
    root.probeSeq = root.playSeq
    return root.runPlayer("probe", Model.playerProbeArgv(root.socketPath, Quickshell.processId, root.ownerToken))
  }

  function handlePlayerResult(text) {
    playerWatchdog.stop()
    var kind = root.playerKind
    root.playerKind = ""
    var timedOut = root.playerTimedOut
    root.playerTimedOut = false
    if (kind === "probe") {
      root.applyProbe(text)
      // A restart held because this slot was busy can be delivered now.
      root.reestablishAdopted()
      root.drainPendingPlay()
      return
    }
    var status = Model.parseHelperStatus(text, "player." + kind)
    // D-PLY-71: this start went out before the user's last stop, which
    // withdrew its intent (issuePlayerSession recorded its seq; every reply
    // of a start or a restart is this one's, the slot running one verb).
    var withdrawn = root.sessionSeq < root.stopSeq
    if (status.ok === true) {
      var warnings = Model.statusWarnings(status)
      if (warnings.length > 0) console.warn("omarchy-iptv: player " + kind + ":", warnings.join("; "))
      // D-PLY-40: a start of an intent issued AFTER the last stop has run
      // under the player lock, so that stop has either laddered its player
      // down before this start began or, reaching the lock after it, is
      // refused as superseded: nothing it does can touch the player this
      // start reports. So the stop's settle ends here, before the repair,
      // the observer's follow-up and the drain below read `stopping`. With
      // no socket EOF to end it -- a stop with nothing attached, or one this
      // start superseded -- it held for the whole backstop, and through it a
      // zap burst's last intent was dropped (drainPendingPlay), the repair
      // refused, rewind presses refused and the new player's death read as
      // the stop's; the backstop is now the stop's own bound with the
      // margin, 18.25 s.
      if (root.stopping && Number(status.seq) > root.stopSeq) {
        root.stopAt = 0
        stopSettleTimer.stop()
        stopLookTimer.stop()
        // D-PLY-79: and the backstop's question goes with its backstop.
        // This start ran after whatever an older verb left, and adopted
        // or laddered it; left set, the flag was asked by the next settle
        // that does not reset it (stopUnadoptedPlayer's).
        root.stopOlderStartOk = false
      } else if (root.stopping) {
        // The review of 9d604cf: a start issued before the stop. Its player
        // was up; whether the stop laddered it or was refused behind this
        // start's own lock, the backstop looks (stopOlderStartOk).
        root.stopOlderStartOk = true
      }
      root.relaunchPending = false
      if (Number(status.seq) === root.previousPlayingSeq) root.previousPlaying = null
      // Restart on adoption: a start or a restart that answered ok has
      // replaced (or adopted, or spawned) the player, so nothing is owed any
      // more; the reply's `paused` is the replaced player's pause, kept.
      if (root.olderRestart) {
        if (root.olderRestart.spent === true && Model.olderRestartKeepsPause(root.olderRestart, Number(status.seq))) {
          root.olderRestartDelivered = true
        }
        root.paused = status.paused === true
        root.endOlderRestart()
      }
      // A start or a restart that answered ok IS the relaunch, delivered.
      // Leaving the queue armed is how the health path fired a SECOND
      // `player restart --from term` at the player it had just respawned,
      // one tick after the observer reattached (the timer's `playerUp`
      // branch reads a healthy new player as "still not answering").
      relaunchTimer.stop()
      root.playRetries = 0
      // The reply's own channel, not whatever is current now: a start that
      // stood down left a DIFFERENT channel on the player, and that entry id
      // belongs to that channel.
      root.rememberEntry(status.entryId, Model.replyTarget(status, root.nowPlaying))
      // D-PLY-11, ruling CL5. The helper says which channel it left on the
      // player. During a cold burst that can be the burst's FIRST intent
      // while the shell is holding the eighth - measured 10 times in 20 - or
      // a newer one this start stood down for. Either way the shell is
      // authoritative: if the player is not on the channel the user asked
      // for, send the intent again rather than relabel the interface.
      var repair = Model.sessionIntentRepair(status, root.nowPlaying)
      if (repair !== "") {
        console.log("omarchy-iptv: the player start settled on another channel; re-applying the intent")
        root.reapplyIntent(repair)
      }
      // The review of 9d604cf: a start that SPAWNED replaced whatever the
      // observer was on when it was issued (sessionSocket) -- it spawns only
      // after laddering what it found, or finding nothing -- so an observer
      // still on that same object is on a player that is gone or going,
      // whose EOF has not been delivered yet (the shell's events can come in
      // either order). Read as "attached", the shell kept watching that
      // connection, and its EOF then read as this player's death: "Playback
      // stopped" and the channel dropped while the new player played on
      // (silent before D-PLY-40 ended a stop's settle here, loud after). So
      // it is released here, before the follow-up, which then hunts for the
      // player this start reports.
      if (status.spawned === true && root.sessionSocket && root.playerSocket === root.sessionSocket)
        root.releasePlayerSocket()
      // The helper has just reported a live player of this shell's making,
      // so the observer belongs on it. Doing nothing here is the second
      // half of the reported P1: `wanted` false leaves the 250 ms retry
      // timer off, and nothing else ever looks again.
      var follow = Model.playerSessionFollowUp({
        attached: root.socketAttached(),
        stopping: root.stopping,
        userStopped: root.userStopped,
        nowPlaying: root.nowPlaying !== null,
        // D-PLY-78: `withdrawn` above, spelled from root (CL10's check runs
        // this branch alone)
        withdrawn: root.sessionSeq < root.stopSeq
      })
      if (follow === "attached" || follow === "abandoned" || follow === "confirm") {
        // Already observed, or a stop really did overtake this start - the
        // two legitimately interleave, because the helper releases the lock
        // before its first-load window precisely so a stop ladder can get
        // in. Do not hunt for a socket that is being torn down; that would
        // be twelve journal lines for a player nobody wants any more.
        root.playerPending = false
        // D-PLY-78: and after that stop's settle, its player is looked for.
        if (follow === "confirm") root.lookForWithdrawn()
      } else {
        // The player is up but the observer has not attached yet: keep the
        // birth edge rather than blinking the bar to idle, bounded by the
        // watchdog, and keep hunting for the socket.
        root.playerWanted = true
        root.armPlayerSocket()
        playerWatchdog.restart()
        // `recover`: a live player and no idea what it is playing. Read the
        // identity back out of its own stash, which is the reattach path of
        // 4.5 unchanged - the same answer a shell restart gets.
        if (follow === "recover") root.runPlayerProbe()
      }
      var first = status.firstLoad && typeof status.firstLoad === "object" ? status.firstLoad : null
      // D-PLY-71: not for a start the user's stop withdrew. The helper
      // releases the lock before its first-load window so that a stop can
      // ladder in, and a stop that does reads there as mpv closing the
      // connection; a stream failure of it is a channel the user stopped.
      // Told, it named the play made AFTER the stop ("stopped unexpectedly",
      // the target being nowPlaying) and, with nothing attached, dropped that
      // play before the drain below could send it.
      if (first && String(first.state) === "failed" && !withdrawn) root.playerFirstLoadFailed(first)
      root.drainPendingPlay()
      return
    }
    var code = status.error ? String(status.error.code) : ""
    if (timedOut && code === "no_output") {
      // D-PLY-35: no output because the watchdog stopped it, which is the
      // S-05 shape the fetch slots already report (helperTimeoutStatus).
      status = Model.parseHelperStatus(root.helperTimeoutStatus("player." + kind, false), "player." + kind)
      code = "helper_timeout"
    }
    if (code === "helper_timeout" && root.nowPlaying !== null) {
      // D-PLY-35. A start the watchdog ended has not refused anything: it
      // may have spawned a player and loaded the channel before the signal
      // landed, which is what dev did at 12 s -- the channel played on,
      // unobserved, under a "Could not start playback" card. So nothing is
      // told yet and the intent is kept: the socket hunt is armed and the
      // reattach probe, the read a shell restart makes, finds what the start
      // left. A player carrying this shell's stash is adopted; anything else
      // ends in settleTimedOutPlay(false), told as the start's own failure.
      // The intent alone gates it: a stop withdraws it (stop() clears
      // `nowPlaying` and its own ladder ends whatever the start left, unless
      // it gave up on the lock: D-PLY-78 below), and a
      // play after a stop is a new intent even while that stop settles.
      console.warn("omarchy-iptv: player " + kind + " was stopped by its watchdog; looking for the player it may have left")
      root.timedOutPlay = { kind: kind, intent: root.nowPlaying }
      root.playerWanted = true
      root.armPlayerSocket()
      if (!root.runPlayerProbe()) root.settleTimedOutPlay(false)
      return
    }
    // D-PLY-78: one a later stop withdrew, nothing named, may have left a
    // player that stop gave up on (the start held the lock past its wait):
    // its watchdog's stop, or a refusal after it adopted one (the helper
    // stops only its own spawn). Not `busy` (no lock) or `superseded` (the
    // record read as it took the lock): both come before any adopt or spawn.
    if (withdrawn && root.nowPlaying === null && code !== "superseded" && code !== "busy") root.lookForWithdrawn()
    root.playerPending = false
    var reason = Model.statusReason(status)
    if (code === "superseded") {
      // A later intent already won under the lock; this one never happened.
      // That intent wrote its own record and owns it, so this one leaves it.
      root.noteSessionOutcome("superseded")
      root.drainPendingPlay()
      return
    }
    if (code === "mpv_missing") {
      root.mpvAvailable = false
      root.runWhichMpv()
      root.playerWanted = false
      playerSocketTimer.stop()
      root.nowPlaying = null
      // spawn_detached refuses after the ladder: an older player is gone too
      root.endOlderRestart()
      root.notify("mpvMissing", {})
      // The user has been told, in a critical toast, that the player program
      // is not installed. Leaving the record would spend that same event a
      // second time as a red row on the next reattach (PO-3).
      root.noteSessionOutcome("mpvMissing")
      return
    }
    if ((code === "busy" || code === "no_socket") && root.nowPlaying && !root.userStopped
        && root.playRetries < root.playRetryMax) {
      // Another launcher holds the lock, or the spawn did not bind in time:
      // the existing backoff, not a second spawn (4.4 step 12).
      // D-PLY-43: gated on the user's word, as the refusal tail below is
      // (D-PLY-41), and no longer on `stopping`: a stop still settling
      // belongs to the player BEFORE this play, and it is the stop that
      // holds the lock. With it in the gate a play made in the seconds after
      // a stop whose ladder outlasted the start's own lock wait was told
      // "The player is busy" instead of retried. The retries' lock waits
      // outlast the stop's own bound (the node suite holds the arithmetic),
      // and the retry starts, never zaps, while the stop settles
      // (playRetryTimer).
      root.playRetries += 1
      playRetryTimer.interval = root.playRetryBaseMs * root.playRetries
      playRetryTimer.restart()
      root.noteSessionOutcome("retrying")
      return
    }
    // D-PLY-71: a start the user's stop withdrew, refused, while a play made
    // after that stop waits behind it. The refusal is no verdict on that
    // play: told, it named it (a channel refusal of the older channel marked
    // the newer one failed) and cleared it before anything sent it. So the
    // drain sends it as its own start, which meets this machine's refusal
    // itself if there is one, as a superseded start's newer intent does
    // above (a play queued behind this start, which is every play made while
    // it ran but one that went out as a zap). With the user's stop the last
    // word there is no such play (stop() clears `nowPlaying`, and only a
    // play or an adoption, which clear `userStopped`, set it again), and the
    // tail below tells nothing, as before.
    if (withdrawn && root.nowPlaying !== null) {
      root.noteSessionOutcome("superseded")
      root.drainPendingPlay()
      return
    }
    root.lastError = reason
    console.warn("omarchy-iptv: player " + kind + " failed:", reason)
    // D-PLY-52 and restart on adoption: refused while the observer is still
    // on a live player -- the helper refused before it laddered anything, so
    // the player this shell adopted plays on. The tail below assumes "the
    // player never started", and with it the bar went idle over a playing
    // channel and a card said playback could not start.
    var watched = root.sessionSocket
    root.sessionSocket = null
    // Q4's second exception: the episode's own automatic restart refused
    // because THIS build refuses the channel the older player streams. Stopped
    // and told whether or not an observer was on it when the restart went out
    // (the reattach's connect can fail), so the older build's weaker policy
    // never outlives the update (the recheck of lane RA).
    if (kind === "start" && Model.playerStartFailure(code) === "channel" && root.olderRestart
        && Model.olderRestartKeepsPause(root.olderRestart, Number(status.seq))) {
      var refusedTarget = root.nowPlaying
      root.endOlderRestart()
      root.stopUnadoptedPlayer("failed")
      root.raiseStreamFailure(refusedTarget, reason)
      return
    }
    // A `player restart` is the health path's replacement of a player that
    // stopped answering, never "refused while it plays on": its refusal takes
    // the tail and is told, as before (the recheck of lane RA).
    if (kind === "start" && watched && root.playerSocket === watched && root.socketAttached() && root.nowPlaying !== null
        && root.refusedWhilePlaying(status, code, reason)) return
    root.playerWanted = false
    playerSocketTimer.stop()
    var target = root.nowPlaying
    root.nowPlaying = null
    root.playRetries = 0
    // The player is gone or never came: an owed restart is owed to nothing.
    root.endOlderRestart()
    // The player never started (requirement 6). D-PLY-32: and the reply is
    // no verdict on the stream, which was never contacted -- a refusal of
    // this machine (the runtime folder, the lock, the plugin's files, the
    // cache, `busy` and `no_socket` out of retries) marks nothing and is told
    // as a local failure, on every try (the owner's "refresh on every try",
    // one card refreshed in place since D-HOST-5). Only a refusal about the
    // channel's own entry is a stream failure (Model.playerStartFailure).
    //
    // D-PLY-41: told whenever the play was the user's and not taken back by
    // a stop -- `userStopped`, which stop() sets and play() clears. A stop
    // that is still settling (`stopping`) is not a reason to keep quiet: it
    // belongs to the player BEFORE this play, and with it in the gate a play
    // made in the seconds after a stop that this machine refused vanished,
    // no card and the intent dropped. play() does not clear `stopping`
    // instead, because that flag is what sends a play after a stop down the
    // start branch rather than at a socket being torn down (4.10).
    if (!root.userStopped) {
      if (Model.playerStartFailure(code) === "channel") root.raiseStreamFailure(target, reason)
      else root.raiseLocalPlayFailure(target, reason)
    }
    // Terminal either way. The toast above is the user's copy of this event
    // when the play was theirs; when a stop overtook it, stop() already
    // retired the record. Neither leaves anything for a reattach to mark.
    root.noteSessionOutcome("failed")
  }

  // `player start` observed the first load fail on its own connection (F3,
  // signal 1 of 4). Under --idle=once mpv exits on that failure, so socket
  // EOF is about to say the same thing; whichever wins, the user sees one
  // toast. `first` is the reply's firstLoad member.
  function playerFirstLoadFailed(first) {
    var reason = String(first && first.reason ? first.reason : "")
    if (reason !== "") root.rememberStderr(reason)
    // D-PLY-33: the same decision as every other death. D-PLY-36: the reply
    // now says which ending the window saw -- an end-file error for the
    // start's entry (`ended` "end-file", mpv's file_error in `fileError`) or
    // mpv closing the connection (`ended` "closed") -- and only the first is
    // the stream's (and not even then for an output of this machine,
    // D-PLY-37). A reply without `ended` is the helper's word, as before.
    var report = Model.deathReport({ firstLoad: true, nowPlaying: root.nowPlaying, reason: reason,
                                     ended: first ? first.ended : undefined, fileError: first ? first.fileError : undefined })
    root.raiseDeath(report)
    if (!root.socketAttached()) {
      root.playerPending = false
      root.playerWanted = false
      playerSocketTimer.stop()
      root.nowPlaying = null
      // No socket means no EOF is coming to say this again: the toast the
      // user just saw is the whole story, so the record ends here too.
      root.noteSessionOutcome("failed")
      return
    }
    // The socket is live, so handlePlayerGone() is moments away and owns the
    // record; retiring it here would only race that.
    root.noteSessionOutcome("attached")
  }

  // A probe's answer, or the re-read an ambiguous one armed, that an intent
  // issued since has overtaken (4.10, section 15): that intent owns the
  // outcome. The stale branch of applyProbe below, and since D-PLY-76 the
  // re-read that has not gone out yet (probeRetryTimer) and, since the
  // review of 8504ba8, an unreadable answer to a probe the intent overtook.
  function probeOverruled() {
    root.probeRetried = false
    // D-PLY-35: and a stopped start's, whose player the newer one adopts.
    root.timedOutPlay = null
  }

  function applyProbe(text) {
    var probe = Model.parsePlayerProbe(text)
    if (!probe.valid) {
      // The review of 8504ba8: an intent issued after this probe went out is
      // the newer word over an answer it cannot read as much as over one it
      // can (the readable answers' staleness test below, asked here with no
      // record to resync from).
      // This branch used to run first and act regardless: a play made while
      // D-PLY-35's probe was out lost its `nowPlaying`, its observer and its
      // hunt to the stopped start's failure, and the only card named that
      // start, so the play then played unobserved under an idle bar.
      if (Model.probeVerdict(0, root.probeSeq, root.playSeq).stale) {
        root.probeOverruled()
        return
      }
      // Garbage, a truncated line or an error reply is not evidence of a
      // player; the 10 s poll and the next play() both recover.
      root.playerPending = false
      // The review of 9d604cf: and the early look learned nothing, so the
      // backstop, which skips while a confirmation is pending, still looks.
      if (root.stopConfirmLook) {
        root.stopConfirmPending = false
        root.stopConfirmLook = false
      }
      // The review of 8504ba8 (rule 15): and an answer that cannot be read
      // is no re-read of the ambiguous one before it. Left set, the next
      // idle answer, however much later -- a start's spawn found by
      // D-PLY-35's probe -- was taken for the re-read and stopped at once.
      root.probeRetried = false
      // D-PLY-35: and when this probe was looking for what a stopped start
      // left, it has found nothing it can name, so that start fails here.
      root.settleTimedOutPlay(false)
      return
    }
    // Ordering survives the restart, and an intent issued after this probe
    // went out is the newer word (4.10, section 15). Both answers come from
    // the one call because the resync moves the counter the other is
    // measured against.
    var verdict = Model.probeVerdict(probe.seq, root.probeSeq, root.playSeq)
    root.playSeq = verdict.seq
    if (verdict.stale) {
      // Everything below is about a world the user has since moved on from;
      // the play they issued owns the outcome, and drainPendingPlay() is
      // about to deliver it.
      root.probeOverruled()
      return
    }
    if (root.stopConfirmPending) {
      root.stopConfirmPending = false
      var look = root.stopConfirmLook
      root.stopConfirmLook = false
      if (look && !(probe.running && Number(probe.seq) > root.stopSeq)) {
        // The early look (the review of 9d604cf): the lock record holds this
        // stop's own sequence, or one before it, so the stop is laddering or
        // still waiting for the lock. A second stop then was D-PLY-40's
        // noise; its EOF or the backstop decides.
        return
      }
      if (probe.running) {
        // The stop was refused and the player is still there. Now that the
        // sequence is resynced, the ladder cannot be superseded again. That
        // stop settles as the user's did, its own bound from now
        // (stopUnadoptedPlayer, D-PLY-73, which since then opens the settle
        // for the backstop's stop as it always did for the look's).
        console.warn("omarchy-iptv: stopping a player that survived a superseded stop")
        root.stopForeignPlayer()
        // D-PLY-73: and a stop issued on the BACKSTOP's own probe is the
        // last the shell sends after the user's: its settle's backstop ends
        // it and looks no further (stopFromBackstop). The 5 s look's stop is
        // looked at once by its backstop, as before.
        if (!look) root.stopFromBackstop = true
      } else {
        root.playerWanted = false
        playerSocketTimer.stop()
        root.playerPending = false
        // The detached stop landed after all. stop() already retired the
        // record; saying so again costs nothing and keeps this branch on the
        // same decision as every other ending.
        root.noteSessionOutcome("stopped")
      }
      return
    }
    if (!probe.running) {
      root.playerWanted = false
      playerSocketTimer.stop()
      root.playerPending = false
      root.nowPlaying = null
      // Restart on adoption: no player, so nothing is owed a replacement.
      root.endOlderRestart()
      // D-PLY-35: a stopped start that left no player failed, and is told.
      if (root.timedOutPlay !== null) {
        root.settleTimedOutPlay(false)
        return
      }
      // Nothing is playing and nothing claimed to have stopped it: if a
      // session record survived, that channel died unattended (PO-3).
      root.markDeadSession()
      return
    }
    if (!probe.responsive) {
      console.warn("omarchy-iptv: the player is not answering, stopping it")
      root.stopForeignPlayer()
      return
    }
    // D-SINK-16, and BEFORE the stash is looked at, for two reasons. The
    // readings decide whether this player may be fed at all, and that question
    // outranks which channel it is on; and the ambiguous-stash branch below
    // RETURNS to be retried 500 ms later, by which time the helper's own
    // migration has already happened. Since D-SINK-72 the second probe reports
    // it too, from the mark the first one left; the flag is still taken on the
    // first answer that carries it, for a player whose mark mpv refused. Only
    // ever set here, never cleared (the property's comment).
    //
    // 0.13.0 made every player this plugin LAUNCHES verify (D-SINK-13), but
    // every one of those four layers lives on the launch argv, and an adopted
    // player's argv is whatever the version that started it wrote. The
    // maintainer raised exactly that against the shipped 0.13.0 (#10389): we
    // were not merely leaving a stale setting there, we were sending that
    // process new provider headers and new credentialed URLs.
    var tls = Model.playerTlsVerdict(probe.tls)
    // D-SINK-71: whether this player had to be migrated, the retry of an
    // ambiguous first probe keeping that probe's answer (probeRetryMigrated).
    var migrated = tls.migrated === true || (root.probeRetried && root.probeRetryMigrated)
    root.probeRetryMigrated = false
    // Restart on adoption (owner, 2026-10-31): a player ANOTHER build launched
    // is replaced, not migrated and kept. It is adopted for the hold below --
    // unsafe or not, because it is fed nothing and the restart that replaces
    // it sets every pin from its own command line -- and the restart is owed.
    // `null` (a helper too old to say) keeps the path below exactly.
    var older = Model.probeLaunchOlder(probe.launch)
    // And a player that does NOT read as another build's owes nothing: an
    // episode still open from before this probe (an automatic restart the
    // watchdog stopped after its replacement came up) ends here, or its
    // `unsafe` would stop the replacement and its spent restart would turn
    // every later zap into a start (the recheck of lane RA).
    if (!older) root.endOlderRestart()
    if (!older && !tls.safe) {
      console.warn("omarchy-iptv: the player will not verify the stream's certificate, stopping it")
      root.stopUnadoptedPlayer("unverified")
      return
    }
    if (!older && tls.action === "reload") root.tlsReloadPending = true
    var stash = probe.stash
    if (stash === null || stash.playing !== true || probe.idle === true) {
      // Under --idle=once an idle player exists only between spawn and the
      // first loadfile, so this is either a racing start or a foreign /
      // pre-M2-02 player. Re-read once before deciding (4.5).
      if (!root.probeRetried) {
        root.probeRetried = true
        root.probeRetryMigrated = migrated
        root.probeRetrySeq = root.playSeq
        probeRetryTimer.restart()
        return
      }
      root.probeRetried = false
      console.warn("omarchy-iptv: found a player this shell cannot identify, stopping it")
      root.stopForeignPlayer()
      return
    }
    root.probeRetried = false
    // M2-05: the reattach path learns the window-owning pid too, so PiP
    // works on a player this shell did not start (4.7).
    root.notePlayerPid(probe.pid)
    // M5-01 (2.2): the zero point lives on the player, so a shell restart
    // recovers "behind live" from the probe reply the way the channel is
    // recovered from the stash, with the number continuous across it.
    // Model.parsePlayerProbe carries it, coerced by Model.parseRewind
    // (numbers finite or null, booleans strict); the service lane's first
    // version re-parsed the reply text and said the probe parser did not
    // carry it, which was true of the design and not of the tree.
    root.applyRewind({ ok: true, running: probe.running === true, rewind: probe.rewind })
    // Restored from the stash inside the surviving process, BEFORE the
    // channel cache exists: the bar and the guide are correct immediately
    // and the zap ring is fixed by reconcileNowPlaying() when the cache
    // lands (4.5, 4.6, requirement 11).
    root.userStopped = false
    root.stopAt = 0
    stopSettleTimer.stop()
    root.playerSourceKey = String(stash.sourceKey || "")
    root.nowPlaying = {
      id: String(stash.id),
      name: String(stash.name || ""),
      group: String(stash.group || ""),
      launchedFrom: String(stash.launchedFrom || ""),
      since: Math.floor(Number(stash.since) || 0)
    }
    if (stash.entryId) root.rememberEntry(stash.entryId, root.nowPlaying)
    root.reconcilePending = true
    // Only when the observer is not on it yet: raising the birth edge over a
    // live socket buys nothing and ends in the watchdog's "did not become
    // observable" twelve seconds later.
    root.playerPending = !root.socketAttached()
    root.playerWanted = true
    root.armPlayerSocket()
    playerWatchdog.restart()
    root.reconcileNowPlaying()
    // D-SINK-102, decision 15: a player with no relay pin reads unsafe in
    // its TLS readings, and one whose relay does not answer is unsafe too, so
    // either is restarted or stopped, never deferred (Model.olderPlayerUnsafe).
    if (older) root.openOlderRestart(Model.olderPlayerUnsafe(tls, probe.relay), migrated, probe.pid, stash)
    root.reestablishAdopted()
    // D-PLY-35: a stopped start's player, found and adopted.
    root.settleTimedOutPlay(true)
  }

  // Restart on adoption: the episode opens on the reattach's adoption of a
  // player another build launched. The TLS reload is subsumed (the restart
  // reloads the channel in a player that verifies). Two cases do not restart
  // at once (design 4.4.3 and path 6): a start the watchdog stopped whose
  // probe finds the older player still there -- that start's failure is told
  // once, as it would have been, and the older player plays on, deferred --
  // and a player this shell's own restart started that reads as another
  // build's again, journaled and deferred, so a disagreement between the
  // builder and the reader shows itself instead of looping.
  // D-SINK-73: a later probe of the SAME player (the socket hunt's after
  // its burst) keeps the episode already open for it -- spent, expired and
  // its intent as they were, the hold not re-armed -- and a different player
  // opens its own (Model.olderRestartOpen). D-SINK-71: `migrated` is kept
  // from an open episode either way: a later probe reads it migrated again
  // from the mark (D-SINK-72) or, if mpv refused the mark, already migrated,
  // and the stream it has open is the same one -- also when that probe names
  // it under another pid (rc-sk73). Path 6's card is raised
  // whichever way the episode goes.
  function openOlderRestart(unsafe, migrated, pid, stash) {
    root.tlsReloadPending = false
    var timedOut = false
    if (root.timedOutPlay !== null) {
      var pending = root.timedOutPlay
      root.timedOutPlay = null
      var kind = "player." + String(pending.kind || "start")
      var reason = Model.statusReason(Model.parseHelperStatus(root.helperTimeoutStatus(kind, false), kind))
      if (!root.userStopped) root.raiseLocalPlayFailure(pending.intent, reason)
      else root.lastError = reason
      timedOut = true
    }
    var open = Model.olderRestartOpen(root.olderRestart, {
      seq: root.playSeq, pid: pid, stash: stash, unsafe: unsafe === true, migrated: migrated === true,
      timedOut: timedOut, delivered: root.olderRestartDelivered
    })
    if (open.again) console.warn(Model.OLDER_RESTART_AGAIN_LINE)
    root.olderRestart = open.episode
    if (open.armHold) olderRestartTimer.restart()
  }

  function endOlderRestart() {
    if (!root.olderRestart) return
    root.olderRestart = null
    olderRestartTimer.stop()
  }

  // The one question, asked from every place the restart can become
  // deliverable: the channel list applied (applyChannels), the reattach's own
  // end (applyProbe), the player slot freed by a probe, and the hold's end
  // (olderRestartTimer). With no episode it is D-SINK-16's reload, unchanged.
  function reestablishAdopted() {
    var ep = root.olderRestart || null
    var np = root.nowPlaying
    var want = Model.olderRestartDisposition({
      owed: ep !== null, spent: ep !== null && ep.spent === true,
      stopping: root.stopping, userStopped: root.userStopped,
      nowPlayingId: np === null ? "" : String(np.id),
      channelsLoaded: root.cacheLoaded,
      hasChannel: np !== null && !!root.channelIndex[String(np.id)],
      sourceMatches: Model.adoptedSourceMatches(root.playerSourceKey, root.activeSourceKey),
      playerUp: root.playerUp, slotBusy: playerProc.running,
      expired: ep !== null && ep.expired === true, unsafe: ep !== null && ep.unsafe === true,
      migrated: ep !== null && ep.migrated === true
    })
    if (want === "none") return root.reestablishForTls()
    if (want === "clear") {
      root.endOlderRestart()
      return false
    }
    if (want === "hold") return false
    if (want === "stop") {
      console.warn("omarchy-iptv: the player another build started cannot be restarted and will not verify the stream's certificate, stopping it")
      root.endOlderRestart()
      root.stopUnadoptedPlayer("unverified")
      return true
    }
    if (want === "defer") {
      // Q4: it plays on, fed nothing; the user's next channel change replaces
      // it and a stop ends it. The episode stays owed, so the zap sites send
      // that change as a start.
      if (ep.spent !== true) root.olderRestart = Model.olderRestartWith(ep, { spent: true })
      olderRestartTimer.stop()
      return false
    }
    // "restart": once per episode, the same channel, at live, keeping pause.
    root.playSeq += 1
    root.olderRestart = Model.olderRestartWith(ep, { seq: root.playSeq, spent: true })
    olderRestartTimer.stop()
    root.wantFocus = false
    console.warn(Model.OLDER_RESTART_LINE)
    root.issuePlayerSession("start", root.channelIndex[String(np.id)], "")
    return true
  }

  // A `player start` refused while the observer is still on the player that
  // was playing: nothing was laddered, so it plays on (D-PLY-52).
  // -> true when the refusal is fully handled here.
  //   - the episode's own automatic restart (its channel refusal is handled
  //     before this is asked): journaled above, kept, deferred -- no card
  //     (Q4), or stopped when it cannot be made safe
  //   - anyone else's start (a user's channel change, a repair): the switch
  //     did not happen and the player plays the channel it was on, so the
  //     label goes back to the one play() kept, as a failed zap's does -- no
  //     card, nothing dropped, the observer kept. A start of that intent that
  //     answered ok has spent it (previousPlayingSeq), so a later refusal
  //     keeps the label it has.
  function refusedWhilePlaying(status, code, reason) {
    var ep = root.olderRestart || null
    var automatic = ep !== null && Model.olderRestartKeepsPause(ep, Number(status.seq))
    root.playRetries = 0
    if (automatic) {
      root.reestablishAdopted()
      return true
    }
    if (root.previousPlaying) root.nowPlaying = root.previousPlaying
    root.previousPlaying = null
    if (ep !== null) root.reestablishAdopted()
    return true
  }

  // D-SINK-16's second half: the player has been MIGRATED, and now the channel
  // it is already streaming is re-established so that nothing continues on a
  // connection that was opened without verification.
  //
  // THE RELOAD IS DELIBERATE AND IT IS NOT BELT-AND-BRACES. Setting
  // `tls-verify` covers the NEXT load - that much the lead measured on
  // 2026-10-07, attacker GETs 1 -> 0 on one unchanged process. Whether an
  // ALREADY-OPEN stream picks the change up for its ongoing segment fetches was
  // NOT measured, and this does not assume either answer: it closes the
  // connection and opens a new one, which makes the unmeasured behaviour
  // irrelevant instead of trusted. The cost is one visible rebuffer, once, on
  // the first reattach after an upgrade - a player this shell started is
  // already verifying, so it answers "feed" and nothing here fires.
  //
  // It waits for `activeCacheDir`, because the helper resolves a channel id
  // against the cache DIRECTORY and the reattach deliberately runs before that
  // exists (the stash names the channel ~130 ms in; the cache lands later). So
  // this is called from both of reconcileNowPlaying()'s own call sites and
  // delivers on whichever is late. Residual, stated rather than hidden: if the
  // cache never lands at all - no source configured - the reload never fires
  // and that one already-open connection runs to the end of its stream
  // unverified. Every LATER load on that player is verified by the migration
  // and by apply_channel's refusal. [D-SINK-72: the mark stays on the player
  // until a load, so the next shell's probe owes the reload again.]
  function reestablishForTls() {
    // D-SINK-16. The three conditions are a FUNCTION (rule 12), because the
    // first version of this guard cleared the flag whenever `nowPlaying` was
    // null, and null there means two different things: "the user stopped", for
    // which nothing is owed, and "not assigned yet", which is the
    // reattach-after-upgrade moment itself -- the flag is set before
    // nowPlaying is. Clearing it there dropped the reload for good, since it
    // is armed in exactly one place, and the already-open unverified stream
    // then ran to the end of its stream. Found by the review of the lane that
    // wrote this.
    // D-PLY-51 (2026-11-01): and only for the channel THIS source's list
    // holds. The reload re-sends the id against the active source's cache
    // (playArgs), so a stash from another source -- switched while the shell
    // was down -- played the active source's channel of the same id.
    var np = root.nowPlaying
    var want = Model.tlsReloadDisposition({
      pending: root.tlsReloadPending, stopping: root.stopping,
      userStopped: root.userStopped,
      nowPlayingId: np === null ? null : String(np.id),
      cacheDir: root.activeCacheDir, playerUp: root.playerUp,
      channelsLoaded: root.cacheLoaded,
      hasChannel: np !== null && !!root.channelIndex[String(np.id)],
      sourceMatches: Model.adoptedSourceMatches(root.playerSourceKey, root.activeSourceKey)
    })
    if (want === "none") return false
    if (want === "clear") {
      // Nothing of ours is playing any more: whatever replaces it goes through
      // apply_channel, which asserts the same thing and refuses rather than
      // loads.
      root.tlsReloadPending = false
      return false
    }
    // "hold": still owed, and the shell is not ready. The flag STAYS set so a
    // later call delivers it.
    if (want !== "deliver") return false
    root.tlsReloadPending = false
    console.warn("omarchy-iptv: re-establishing the channel on an adopted player that was not verifying certificates")
    return root.reapplyIntent(String(root.nowPlaying.id))
  }

  // Ruling PO-3. The probe says nothing is running; if state.json still
  // holds a session record, the channel it names died with no shell attached
  // to notice - so the guide gets a red row, silently, and the record is
  // cleared. A toast for something that stopped minutes ago, possibly on
  // another login, is noise that arrives without context. [D-PLY-33,
  // 2026-10-28: no red row any more -- see the mark below; the record is
  // still cleared and nothing is told.]
  //
  // The race: this runs from the probe reply, about 130 ms after
  // Component.onCompleted, while stateFile loads whenever it loads - either
  // can win. Model.deadSessionVerdict() refuses to decide on a state that
  // has not landed (it would read the empty default, drop the mark, and
  // write that empty default over the user's file) and asks to be called
  // again; applyUserState() drains that.
  function markDeadSession() {
    var verdict = Model.deadSessionVerdict(root.userState, root.stateLoaded, root.failedAt,
                                           Model.formatClock(Math.floor(Date.now() / 1000)))
    root.deadSessionPending = verdict.pending
    if (!verdict.mark) return
    // D-PLY-33 (owner, 2026-10-28): a surviving record is a player that died
    // with nobody attached, so nobody saw an end-file -- and a death with no
    // end-file marks nothing. The record cannot tell a dead stream from a
    // crash, a kill, a logout, or a clean end PO-4 keeps silent. So the mark
    // deadSessionVerdict prepared is applied only if Model.deathReport says
    // an unattended death marks, which it does not; PO-3's "no stale toast"
    // stands with it.
    if (Model.deathReport({ unattended: true }).mark === true) root.failedAt = verdict.failed
    // The record is spent either way. Retiring it goes through the same
    // decision as every other ending rather than being written here: that
    // is what makes the clear stick when the write loses its race with
    // state.json's own load.
    root.noteSessionOutcome("marked")
  }

  // The player is gone for good and nobody needs marking: an explicit stop,
  // The other half of PO-3, and the ONE place any player outcome is allowed
  // to reach the session record. Every branch below that ends in "the player
  // is gone" or "the player is still coming" says so here in one word and
  // Model.sessionAfterOutcome() decides, because the rule is the same rule
  // everywhere - a record must not outlive the shell that saw how the play
  // ended - and a rule spelled out per branch is a rule three branches will
  // get wrong. They did: a failed start, a missing mpv and an abandoned
  // relaunch each left the record behind, so the next reattach marked that
  // channel red a second time for a failure the user had already been shown
  // and already dealt with.
  //
  // Like markDeadSession() this is assignments and a write gate, no rule of
  // its own: the verdict carries the deferred-PO-3 flag as well as the state,
  // and hands back the same state object when there is nothing to clear, so
  // this writes only when it actually changed something.
  function noteSessionOutcome(outcome) {
    var verdict = Model.sessionAfterOutcome(root.userState, outcome, root.deadSessionPending,
                                            root.sessionConsumed)
    root.deadSessionPending = verdict.pending
    root.sessionConsumed = verdict.consumed
    if (!verdict.write) return
    root.userState = verdict.state
    root.saveState()
  }

  // A player that exists but is not ours to show: wedged, foreign, or from
  // a version that did not stash its identity (migration, section 8). It
  // ends in nothing playing, so the session record goes with it.
  function stopForeignPlayer() {
    return root.stopUnadoptedPlayer("foreign")
  }

  // The same ladder under a second name, because D-SINK-16 ends in it for a
  // different reason and the session record should say which: a player that
  // could not be made to verify the stream's certificate is stopped rather than
  // fed, and that is not the same event as a player we could not identify.
  //
  // D-PLY-73 (closed 2026-11-21): and the stop the shell issues here settles
  // as the user's does (4.10). It kept the observer on the player it ladders
  // and opened no settle, so play() -- an observer attached, nothing
  // stopping, nothing owed -- zapped the user's next channel into that
  // player, the backstop's stop of a player that outlived the user's stop
  // above all (the 5 s look's reopened the settle itself). Now `stopping`
  // runs from here until that player's EOF, a start of an intent issued
  // after this stop answering ok, or this stop's own bound (stopSettleTimer),
  // so a play made meanwhile goes out as a start, which the lock and the seq
  // rule order after the ladder. Every caller: the backstop's and the look's
  // stop of a survivor, and at any probe a player that does not answer, one
  // that will not verify the certificate or one this shell cannot identify
  // (each can be a player of this build, which the helper's `play` feeds),
  // and another build's player that cannot be restarted or whose automatic
  // restart this build refused (whose zap the build gate already routed to
  // a start). `stopSeq` moves to this stop, so a start's reply is judged
  // against the last stop issued, the user's or the shell's.
  function stopUnadoptedPlayer(outcome) {
    root.playSeq += 1
    root.playerWanted = false
    playerSocketTimer.stop()
    root.playerPending = false
    root.nowPlaying = null
    // Nothing of ours plays now, so a reload owed to D-SINK-16 is owed to
    // nothing, and so is a restart (restart on adoption).
    root.tlsReloadPending = false
    root.endOlderRestart()
    root.noteSessionOutcome(outcome)
    Quickshell.execDetached(Model.helperArgv(root.helperPath, Model.playerStopArgv(root.socketPath, root.playSeq)))
    root.stopSeq = root.playSeq
    root.stopAt = Date.now()
    // Looked at once by its backstop, as the user's stop is -- unless it was
    // issued on the backstop's own probe (applyProbe sets this after the
    // call). Restarted even while a settle runs: the 5 s look's stop is
    // issued inside the user's, and its ladder needs a whole bound from
    // here, not what is left of the user's (the review of 241a226).
    root.stopFromBackstop = false
    // D-PLY-75: a user's stop pressed while this settles inherits the
    // player this stop ladders (stop()).
    root.stopByShell = true
    stopSettleTimer.restart()
    // D-PLY-35: when the reattach probe was looking for what a stopped start
    // left, this is what it found, and that start failed.
    root.settleTimedOutPlay(false)
    return true
  }

  // The second half of the reattach: the stash named the channel, the cache
  // resolves it. A playlist that changed while the shell was down degrades
  // to name-only rather than resolving to the wrong row, and a stash from
  // another source is never resolved against this one.
  function reconcileNowPlaying() {
    if (!root.reconcilePending || !root.nowPlaying || !root.cacheLoaded) return
    if (!Model.adoptedSourceMatches(root.playerSourceKey, root.activeSourceKey)) {
      root.reconcilePending = false
      return
    }
    root.reconcilePending = false
    var np = root.nowPlaying
    var channel = root.channelIndex[String(np.id)]
    if (!channel) return
    var group = Model.primaryGroup(channel)
    root.nowPlaying = {
      id: np.id,
      name: String(channel.name || np.name),
      group: group,
      launchedFrom: String(np.launchedFrom || "") || Model.groupScopeId(group),
      since: np.since
    }
  }

  function socketAttached() {
    return root.playerSocket !== null && root.playerSocket.connected === true
  }

  function releasePlayerSocket() {
    if (root.playerSocket === null) return
    var s = root.playerSocket
    root.playerSocket = null      // drop the reference first
    s.destroy()                   // deferred by QML, safe from inside a handler (C10)
  }

  // Returns true iff attached. Synchronous: a failed connect emits `error`
  // and never a state change, so `connected` on the next line is the only
  // authoritative answer (C5).
  function attachPlayerSocket() {
    if (root.socketPath === "") return false          // C8: arming with "" is a silent no-op
    root.releasePlayerSocket()
    var s = playerSocketComponent.createObject(root)
    if (s === null) {
      console.warn("omarchy-iptv: could not create the player socket observer")
      return false
    }
    root.playerSocket = s
    // createObject() is typed QObject, so the linter cannot see Socket's
    // own properties here; the type is guaranteed by playerSocketComponent
    // in Service.qml.
    // qmllint disable missing-property
    s.connected = true
    if (s.connected) return true
    // qmllint enable missing-property
    root.playerSocket = null
    s.destroy()                   // a failed connect bricks it: discard (C1)
    return false
  }

  function armPlayerSocket() {
    if (root.socketAttached()) return      // C2: never re-arm a live socket
    playerSocketTimer.tries = 0
    if (root.attachPlayerSocket()) return
    playerSocketTimer.restart()
  }

  function socketWrite(sock, command, requestId) {
    if (!sock || sock.connected !== true) return false   // C7: a write to a dead socket vanishes
    sock.write(JSON.stringify({ command: command, request_id: requestId }) + "\n")
    return true
  }

  // Called from inside the Socket's own onConnectionStateChanged, so it
  // reads the object it is handed and never root.playerSocket (C4).
  function onPlayerAttached(sock) {
    root.playerPending = false
    root.playerWanted = true
    root.probeRetried = false
    // Observed properties are dropped when a connection closes, so a new
    // shell subscribes for itself rather than inheriting (4.4 step 13).
    root.socketWrite(sock, ["request_log_messages", "error"], 1)
    root.socketWrite(sock, ["observe_property", 1, "idle-active"], 2)
    // M2-05 4.5. One more read on the same connection: what the window was
    // before PiP, out of the player that outlived us. Needed only when the
    // shell restarted while in PiP and the user then exits; a failure or an
    // `active:false` degrades the exit to "unpin and unfloat", never to
    // stuck.
    root.pipRequestSnapshot(sock)
    // 4.7 step 3, the compositor half of the same recovery: the snapshot
    // above says what the window WAS, this says what it IS. Both are needed
    // and neither substitutes for the other - a shell that reattached to a
    // player in PiP has no memory of either (D-PIP-4).
    root.pipPeek()
    if (sock.flush) sock.flush()
  }

  // Quickshell logs one WARN per failed attempt itself, so this stays quiet
  // by default; the burst cap is what keeps that bounded (C6).
  function onSocketError(err) {
    root.playerSocketError = Number(err)
    if (root.debugTiming) console.warn("omarchy-iptv: player socket error", String(err))
  }

  // Event router (4.8). Every line is one JSON object from mpv's own socket.
  // The routing DECISION is Model.routePlayerEvent(): which entry is
  // loading, whether the last end-file still stands, idle-active, and the
  // log tail. This method is the four property writes that decision implies,
  // and nothing else - a rule that lived here could only ever be pinned by a
  // copy of itself in the spec file (engineering rule 10 (dev branch)).
  function handlePlayerLine(line) {
    // Our own get_property answer (M2-05 4.5), routed by request id before
    // the event router sees it. Everything else falls through unchanged.
    if (root.pipNoteReply(line)) return
    var before = { entryId: root.currentEntryId, lastEndFile: root.lastEndFile, idle: root.playerIdle, tail: root.mpvStderrTail }
    var next = Model.routePlayerEvent(before, line)
    // Unchanged fields come back by reference, so this writes only what moved.
    if (next.entryId !== before.entryId) root.currentEntryId = next.entryId
    if (next.lastEndFile !== before.lastEndFile) root.lastEndFile = next.lastEndFile
    if (next.idle !== before.idle) root.playerIdle = next.idle
    if (next.tail !== before.tail) root.mpvStderrTail = next.tail
  }

  // Which channel a load belonged to (Model.rememberEntryOwner): at most
  // four entries, and the gate fails open, so an unknown id degrades the
  // name and never suppresses a toast.
  function rememberEntry(entryId, target) {
    var owners = Model.rememberEntryOwner(root.entryOwners, entryId, target)
    if (owners === root.entryOwners) return
    root.entryOwners = owners
    root.currentEntryId = Math.floor(Number(entryId))
  }

  // One toast per failed play, whichever detector saw it first (R11, S-04).
  function raiseStreamFailure(target, reason) {
    if (!target) return
    var id = String(target.id || "")
    if (id !== "" && root.notifiedFailureId === id) return
    root.notifiedFailureId = id
    root.lastError = reason
    if (id !== "") {
      // Applied locally at once and persisted in the same turn. The local
      // apply is not an optimisation: the file is reloaded asynchronously, so
      // waiting for it would leave the row unmarked for as long as a process
      // launch takes -- and engineering rule 9 is that a plugin never waits for
      // its own write to come back.
      root.failedAt = Model.withFailed(root.failedAt, id, Math.floor(Date.now() / 1000))
      root.persistFailed("mark", id)
      root.lastFailedId = id
    }
    root.notify("streamFailed", { name: String(target.name || ""), reason: reason })
  }

  // D-PLY-32: a play this machine refused before the stream was contacted.
  // The reason is recorded where every play failure records it (`lastError`,
  // the IPC status); `failedAt`, failed.json and `lastFailedId` are NOT
  // touched, because nothing is known about the channel, and a broken
  // runtime folder would otherwise mark every channel the user tries and
  // take each out of the zap ring. Told on EVERY try (the owner, 2026-10-28:
  // "refresh on every try"): each post refreshes the one card in place, with
  // the channel and the reason of the latest try, because the notice slot
  // sends back the id the server returned for the last one (D-HOST-5). Until
  // then it was told once per episode, because a fixed replace id stacked a
  // card per try on Omarchy's server.
  function raiseLocalPlayFailure(target, reason) {
    root.lastError = reason
    if (!target) return
    root.notify("localPlayFailure", { name: String(target.name || ""), reason: reason })
  }

  // D-PLY-35: the end of a start the watchdog stopped, once the reattach
  // probe has said what it left (applyProbe). `found`: the probe adopted that
  // player, which is the start delivered late, so it settles as an ok reply
  // does -- the relaunch is spent, the retries and the local-failure episode
  // end -- and nothing is told. If the player is on another channel (the
  // start was stopped before it loaded its own), the intent is put back and
  // sent again over the socket, ruling CL5's repair: the shell holds what the
  // user asked for, and relabelling would hide the wrong channel. Otherwise
  // nothing of this start's plays: the probe's own branch has stopped
  // anything it could not adopt, and this ends the intent and tells the
  // failure the start would have answered had it been let finish,
  // `helper_timeout` ("Helper timed out"), which is local (D-PLY-32: it marks
  // nothing). A no-op when no stopped start is waiting.
  function settleTimedOutPlay(found) {
    var pending = root.timedOutPlay
    if (pending === null) return
    root.timedOutPlay = null
    var intent = pending.intent
    if (found) {
      root.relaunchPending = false
      relaunchTimer.stop()
      root.playRetries = 0
      if (intent && root.nowPlaying && String(root.nowPlaying.id) !== String(intent.id)) {
        console.log("omarchy-iptv: the stopped start left another channel on the player; re-applying the intent")
        root.nowPlaying = intent
        root.pendingPlayId = String(intent.id)
      }
      return
    }
    var kind = "player." + String(pending.kind || "start")
    var reason = Model.statusReason(Model.parseHelperStatus(root.helperTimeoutStatus(kind, false), kind))
    root.playerWanted = false
    playerSocketTimer.stop()
    root.playerPending = false
    root.nowPlaying = null
    root.playRetries = 0
    // D-PLY-41's gate, the refusal tail's: the intent was the user's unless
    // a stop took it back; a stop still settling from before it is no reason.
    if (!root.userStopped) root.raiseLocalPlayFailure(intent, reason)
    else root.lastError = reason
    root.noteSessionOutcome("failed")
  }

  // D-PLY-33 (owner, 2026-10-28): the player died and mpv never said the load
  // failed (Model.deathReport card "playerStopped"). Told, because a player
  // that vanished must never vanish in silence (F4), and in copy that blames
  // no stream; `failedAt`, failed.json and `lastFailedId` are NOT touched.
  // The same one-card-per-failed-play gate as raiseStreamFailure, so
  // whichever detector speaks first is the one the user hears.
  function raisePlayerStopped(target, reason) {
    if (!target) return
    var id = String(target.id || "")
    if (id !== "" && root.notifiedFailureId === id) return
    root.notifiedFailureId = id
    root.lastError = reason
    root.notify("playerStopped", { name: String(target.name || "") })
  }

  // D-PLY-37 (owner, 2026-10-28): mpv ended the load because an output of
  // THIS machine could not be opened -- no audio device, the sound server
  // down (Model.deathReport card "outputFailed"). Told in copy that blames
  // this computer and marks nothing; the same one-card-per-failed-play gate
  // as the two above. `output` is "audio" or "video"; `reason` is the
  // sentence lastError records.
  function raiseOutputFailure(target, output, reason) {
    if (!target) return
    var id = String(target.id || "")
    if (id !== "" && root.notifiedFailureId === id) return
    root.notifiedFailureId = id
    root.lastError = reason
    root.notify("outputFailed", { name: String(target.name || ""), output: output })
  }

  // D-PLY-66. A failed open the player's relay refused -- a redirect, an HLS
  // or DASH open, a name that led it to a local address -- reaches the shell
  // only as a failed open, so before a "Stream failed" card is told the
  // relay is asked, once, how many of that load's connections it refused
  // (`player refused`, a read; the handle came with the load's own reply and
  // rides the entry ring). The card is told on the answer
  // (handleRelayAnswer) or when relayAskWatchdog gives up, whichever is
  // first, and exactly once: a count nobody can read changes nothing and
  // withholds nothing (F4). Every other report is told at once, as before.
  function askRelayThenRaise(report) {
    var argv = Model.playerRefusedArgv(root.socketPath, Model.relayAsk(report))
    if (argv.length === 0 || relayAskProc.running || root.relayAskReport !== null) {
      root.raiseDeath(report)
      return
    }
    root.relayAskReport = report
    root.runHelper(relayAskProc, Model.helperArgv(root.helperPath, argv), {})
    relayAskWatchdog.restart()
  }

  function handleRelayAnswer(text) {
    relayAskWatchdog.stop()
    var report = root.relayAskReport
    if (report === null) return
    root.relayAskReport = null
    root.raiseDeath(Model.relayRefusedReport(report, text))
  }

  // Model.deathReport's card, raised. One dispatcher for every detector that
  // asks it (the socket's EOF, the first-load window), so a card the model
  // adds is a card every detector tells.
  function raiseDeath(report) {
    if (!report) return
    if (report.card === "streamFailed") root.raiseStreamFailure(report.target, report.reason)
    else if (report.card === "playerStopped") root.raisePlayerStopped(report.target, report.reason)
    else if (report.card === "outputFailed") root.raiseOutputFailure(report.target, report.output, report.reason)
  }

  function rememberStderr(line) {
    var tail = Model.pushPlayerLog(root.mpvStderrTail, line)
    if (tail === root.mpvStderrTail) return
    root.mpvStderrTail = tail
  }

  // Socket EOF: the one-for-one replacement for mpvProc.onExited, and the
  // only death signal that covers quit, SIGTERM, SIGKILL and a segfault
  // alike - 2 to 3 ms after the fact instead of a 10 s poll (4.8 signal 3).
  // The exit code is replaced by Model.endedReport() over the last end-file:
  // whether the user hears about this death (our own stop and the .m3u8
  // redirect IPTV masters emit on every load say nothing), which channel it
  // names, and with what text. Read before any of the state below is
  // cleared, which is also what keeps the decision out of this method.
  function handlePlayerGone() {
    // The review of 9d604cf: the player a stop is laddering died while a play
    // made AFTER that stop is still on its way -- its start in flight, or
    // between the retries D-PLY-43 now makes while a stop settles. Read as
    // below, the death was the stop's own (silent), so the retry was
    // cancelled, `nowPlaying` cleared and the user's play dropped with no
    // card -- the opposite of D-PLY-41's rule. This EOF ends the stop and
    // nothing else: the play keeps its intent, its queued last channel and
    // its retries, and the hunt goes on for the player its start will
    // report.
    // D-PLY-69 (closed 2026-11-21): except with two stops outstanding --
    // stop, play, stop, play while the start the first play sent still holds
    // the lock (staleStartInFlight). This EOF may then be the EARLIER stop's
    // while the later one has not run, and ending the settle here let that
    // start's ok zap the queued channel at the player the later stop then
    // laddered (the repair, the drain, or a play() meanwhile). So the death
    // is told to no one and ends nothing: the settle runs on until a start
    // issued after the last stop answers ok, or a later EOF with no such
    // start in flight, or its backstop. And the same EOF with the user's
    // stop the last word, which took the plain path below, is held over
    // here too: that path ended the settle and cleared `userStopped`, so the
    // start's ok read as the shell's own player to recover, and the probe
    // adopted it under the user's stop (the node suite's seeded world of
    // the player, dev branch, found it). Held over, nothing hunts for it.
    // D-PLY-72 (closed 2026-11-21): and with ONE stop, when the start in
    // flight went out before it over a player it ladders itself (a restart,
    // an owed replacement, a start over the observed player): the EOF is
    // then that start's own rung while the stop waits for its lock, and
    // ending the settle here let its ok zap a play made after the stop into
    // the player the stop then laddered, or, with the stop the last word,
    // recover and adopt that player under it (staleStartInFlight).
    var heldOver = root.staleStartInFlight()
    if (root.stopping && (heldOver || (!root.userStopped && root.nowPlaying !== null))) {
      if (!heldOver) {
        root.stopAt = 0
        stopSettleTimer.stop()
        stopLookTimer.stop()
        root.stopOlderStartOk = false
        root.stopConfirmPending = false
        root.stopConfirmLook = false
      }
      root.lastEndFile = null
      root.currentEntryId = 0
      root.playerIdle = false
      root.clearRewind()
      root.pipReset()
      root.entryOwners = Model.keyedMap()
      if (playerProc.running && !root.userStopped && root.nowPlaying !== null) {
        root.playerPending = true
        root.playerWanted = true
        root.armPlayerSocket()
      }
      return
    }
    focusTimer.stop()
    playRetryTimer.stop()
    playerSocketTimer.stop()
    var current = root.nowPlaying
    var end = root.lastEndFile
    var stopped = root.userStopped
    // D-PLY-33: Model.deathReport is endedReport plus what the death is
    // evidence of -- marked only for an end-file error on the channel's own
    // entry, which is why it takes the entry the player last started.
    var report = Model.deathReport({
      lastEndFile: end,
      owners: root.entryOwners,
      nowPlaying: current,
      entryId: root.currentEntryId,
      userStopped: stopped,
      stopping: root.stopping,
      tail: root.mpvStderrTail
    })
    // Model.playerDeathKind() decides what this EOF was, because a helper
    // that ladders a player down and spawns its replacement under one lock
    // delivers the old one's death here while that call is still running.
    var death = Model.playerDeathKind({
      sessionInFlight: playerProc.running && (root.playerKind === "start" || root.playerKind === "restart"),
      relaunchPending: root.relaunchPending,
      nowPlaying: current !== null,
      hasChannel: current !== null && !!root.channelIndex[String(current.id)],
      userStopped: stopped,
      stopping: root.stopping
    })
    root.lastEndFile = null
    root.currentEntryId = 0
    root.playerIdle = false
    root.playerPending = false
    root.playerWanted = false
    root.userStopped = false
    root.relaunchPending = false
    root.stopConfirmPending = false     // the EOF is the confirmation
    root.stopConfirmLook = false
    root.stopOlderStartOk = false
    root.pendingPlayId = ""
    root.playRetries = 0
    // D-PLY-35: a stopped start whose player the socket reached has its end
    // told here, as every death is; the probe's later "nothing there" must
    // not tell it a second time.
    root.timedOutPlay = null
    // M5-01: no player, no history, and no seek to deliver to it.
    root.clearRewind()
    root.healthSkips = 0
    root.healthFailures = 0
    // The death IS the end of the stop (4.10); the backstop (stopSettleMs,
    // the stop's own bound since D-PLY-40) is only for a stop that never had
    // a player to observe.
    root.stopAt = 0
    stopSettleTimer.stop()
    stopLookTimer.stop()
    // M2-05 / PIP3. The window PiP was applied to is gone, so PiP is over -
    // including on a respawn, which brings back a different window with a
    // different pid. Nothing remembers an intent across a window's lifetime
    // to re-apply it later; the user presses the key again.
    root.pipReset()
    if (death === "respawn") {
      // A rung of the ladder the helper is running right now, for this very
      // channel. The intent is unchanged, so the birth edge is held, the
      // observer keeps hunting - it is already retrying when the new mpv
      // binds, with no dependence on the helper's reply arriving - and the
      // user is told nothing, because nothing has ended. The record outlives
      // this death for the same reason a queued relaunch does.
      root.playerPending = true
      root.playerWanted = true
      root.armPlayerSocket()
      root.noteSessionOutcome("respawning")
      return
    }
    if (death === "relaunch") {
      // The health verdict's one automatic relaunch, a moment after the
      // exit: the old socket file is gone by then and a stop() in the
      // meantime cancels it (D-LIVE-15, D-LIVE-17).
      root.wantFocus = false
      relaunchTimer.restart()
      // The record outlives this death on purpose: the same channel is
      // coming back in a moment, and if the shell dies in between, nothing
      // watched the outcome after all.
      root.noteSessionOutcome("relaunching")
      return
    }
    root.nowPlaying = null
    // Restart on adoption: the older player ended on its own (the user pressed
    // q in its window, the stream ended) with no start in flight: nothing to
    // replace any more.
    root.endOlderRestart()
    // Terminal: the player is gone and nothing is bringing it back, whatever
    // the verdict says. This is where a clean end, a crash we have just
    // toasted and a stop we did not issue all leave the session record
    // behind if nobody clears it, and the next reattach would read that as a
    // channel that died unattended (PO-3).
    root.noteSessionOutcome("ended")
    root.entryOwners = Model.keyedMap()
    // D-PLY-33 (owner, 2026-10-28). A load mpv said failed is the stream's:
    // marked, "Stream failed", and report.reason is the log-message tail when
    // there is one ("Failed to open scheme://host" says what actually went
    // wrong), else mpv's own generic file_error -- both redacted, the tail
    // twice (in python and again in Model.pushPlayerLog). A death with no
    // such end-file -- a crash, a kill, a VO abort -- is told and marks
    // nothing, because nothing says the stream caused it. D-PLY-37: nor does
    // an end-file error that names an output of this machine. D-PLY-66: a
    // "Stream failed" report first asks the relay whether it refused the
    // load, so the card can say so.
    root.askRelayThenRaise(report)
  }

  // D-SRC-37 (c): `which mpv` is one more process this shell waits on (the
  // start, a play without mpv, a `mpv_missing` reply), so it is run and read
  // through one pair the harness can call, and bounded like every helper
  // slot. A run the watchdog stopped exits non-zero: mpv reads as absent
  // until the next ask, the answer the exit code gave before.
  function runWhichMpv() {
    whichProc.running = true
    whichWatchdog.restart()
  }

  function handleWhichExit(exitCode) {
    whichWatchdog.stop()
    root.mpvAvailable = exitCode === 0
  }
