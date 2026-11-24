// Service-pip.js -- a code-behind of Service.qml (D-REL-14). Each function here was
// moved byte for byte out of Service.qml, which reaches it through a
// one-line forwarder left at its old place; it runs in Service.qml's own
// scope. Edit a function here, never its forwarder.

  // The guide's `p` key (design section 5). Same answer shape as the IPC
  // verb, so both surfaces refuse for the same reasons in the same words.
  function togglePip() {
    return root.requestPip("toggle")
  }

  // The one entry point. Returns SYNCHRONOUSLY with what is knowable
  // synchronously - whether the request was accepted, and why not if it was
  // refused - and never with a claim of success: success is a fact about the
  // compositor that only a readback can establish (PIP11), and that readback
  // is two process round-trips away. The verified outcome arrives on
  // pipOutcome() and is readable in `status`.
  function requestPip(mode) {
    var want = String(mode || "").toLowerCase()
    if (want !== "on" && want !== "off" && want !== "toggle")
      return root.pipRefuse(want, "bad_mode")
    // The same function the guide's `p` key asks before it calls in at all
    // (Model.pipKeyRequest), so the two surfaces cannot drift into refusing
    // for different reasons or in different words. The guide answers what it
    // can see; this is the authority, because only the service knows whether
    // the player's pid is known. PiP never starts a player (4.10), and
    // "nothing playing" covers a player whose pid we do not have, because
    // addressing by class alone is the one thing this feature must not do.
    var gate = Model.pipKeyRequest({ available: root.pipAvailable,
                                     playing: root.playing && root.playerPid > 0 })
    if (!gate.ok) return root.pipRefuse(want, gate.code)
    if (root.pipBusy)
      return root.pipRefuse(want, "busy")
    root.pipMode = want
    root.pipIntent = ""
    root.pipRound = 0
    root.pipQueue = []
    root.pipGeom = null
    root.pipLive = null
    root.pipReason = ""
    root.pipPhase = "resolve"
    pipSequenceWatchdog.restart()
    root.pipReadClients()
    return { ok: true, kind: "pip", requested: want, was: root.pipOn, state: "applying" }
  }

  // A request that never started. The answer goes back to the caller AND out
  // on pipOutcome, so the guide's footer says the same thing whether the
  // refusal was decided here or fifteen steps later - `bad_mode` and `busy`
  // have no line in Model.pipStatusText and so say nothing, which is right:
  // a second `p` while the first is still applying is not news.
  function pipRefuse(requested, code) {
    var result = { ok: false, kind: "pip", requested: requested,
                   state: root.pipOn ? "on" : "off", code: String(code),
                   error: { code: String(code) } }
    root.pipOutcome(result)
    return result
  }

  // Every phase begins here. The read is the same read the verification uses,
  // which is the point: there is one way to learn what the window is.
  function pipReadClients() {
    if (hyprClientsProc.running) return
    hyprClientsProc.running = true
    pipStepWatchdog.restart()
  }

  function pipReadMonitors() {
    if (hyprMonitorsProc.running) return
    hyprMonitorsProc.running = true
    pipStepWatchdog.restart()
  }

  // `hyprctl -j clients` came back. One function, three phases, because all
  // three want exactly the same thing: the truth about our window, right now.
  function pipApplyClients(text) {
    pipStepWatchdog.stop()
    if (!root.pipBusy) return
    var live = Model.pipFindWindow(text, root.playerPid, root.pipClass)
    if (!live.ok) {
      // Garbage, no match, or more than one match. Never act on a guess.
      root.pipFinish(false, String(live.reason || "no_window"))
      return
    }
    root.pipLive = live
    if (root.pipPhase === "resolve") {
      // The answer to "am I in PiP?" is read out of the compositor, not out
      // of a boolean this shell may not even have been alive to set (4.7),
      // and the mode is resolved against that same read by the same function
      // the model's own tests drive.
      root.pipOn = Model.pipActive(live)
      root.pipIntent = Model.pipResolveIntent(root.pipMode, live)
      if (root.pipIntent === "on") {
        // What the window WAS. Written to the player before the first
        // dispatch, so a shell that dies mid-sequence still leaves something
        // that knows how to put the window back. NOT rewritten when PiP is
        // already on: `pip on` twice must not overwrite the restore point
        // with the PiP box's own rectangle.
        if (!root.pipOn) root.pipWriteMpv("on", live)
        root.pipPhase = "monitors"
        root.pipReadMonitors()
        return
      }
      // The tag is what says "we did this to this window" (design 4.8). A
      // window the user floated and pinned themselves with SUPER+O carries
      // none, so `pip off` has nothing of ours to undo and must not drag it
      // back to a rectangle out of a stale snapshot - or, worse, resize a
      // TILED window, which changes the split ratio of the user's layout.
      if (!Model.pipHasTag(live)) {
        root.pipSnapshot = null
        root.pipOn = false
        root.pipFinish(true, "")
        return
      }
      root.pipPhase = "dispatch"
      root.pipPlanRound()
      return
    }
    if (root.pipPhase === "verify") {
      root.pipCheck(live)
      return
    }
    root.pipPlanRound()
  }

  function pipApplyMonitors(text) {
    pipStepWatchdog.stop()
    if (!root.pipBusy) return
    var live = root.pipLive
    var monitor = Model.pipFindMonitor(text, live ? live.monitor : -1)
    var geom = monitor ? Model.pipGeometry(monitor, Model.pipOptions(root.pipConfig())) : null
    if (!geom) {
      root.pipFinish(false, "no_monitor")
      return
    }
    root.pipGeom = geom
    // Read the windows again rather than planning against the read the
    // monitor lookup was entered on. It costs one more process on the way in
    // and it is what makes "decided from a fresh read" literally true of
    // every conditional step, rather than true to within a round trip
    // (PIP10).
    root.pipPhase = "dispatch"
    root.pipReadClients()
  }

  // One round: decide from the read we are holding, then run what it decided.
  // `pipLive` here is at most a few milliseconds old - it is the read this
  // round was entered on - which is what "read the live state and act
  // conditionally" means in a process-driven engine (PIP10).
  function pipPlanRound() {
    // Counted here, unconditionally, because this is also the termination
    // proof: at most pipMaxRounds passes, and a re-plan that has nothing
    // left to try stops instead of asking the compositor the same question
    // for ever.
    root.pipRound += 1
    var plan = Model.pipPlan(root.pipLive, root.pipSnapshot, root.pipGeom, root.pipIntent)
    if (!plan || plan.length === 0) {
      if (root.pipRound > 1) {
        root.pipOn = Model.pipActive(root.pipLive)
        root.pipFinish(false, "dispatch_failed")
        return
      }
      // First pass with nothing to do: the window may already be exactly
      // right. Verify anyway - the compositor, not an empty plan, is what
      // decides whether we are done (PIP11).
      root.pipPhase = "verify"
      root.pipReadClients()
      return
    }
    if (plan.length > root.pipMaxSteps) plan = plan.slice(0, root.pipMaxSteps)
    root.pipQueue = plan
    root.pipRunNextStep()
  }

  function pipRunNextStep() {
    if (!root.pipBusy) return
    var queue = root.pipQueue
    if (!queue || queue.length === 0) {
      root.pipPhase = "verify"
      root.pipReadClients()
      return
    }
    var argv = queue[0]
    root.pipQueue = queue.slice(1)
    if (!argv || argv.length < 3) {
      // A builder refused to produce a vector (a value that did not match the
      // address regex or the integer range, 4.11 / PIP7). Refusing is the
      // correct outcome; carrying on past it is not.
      root.pipFinish(false, "bad_step")
      return
    }
    hyprDispatchProc.command = argv
    hyprDispatchProc.running = true
    pipStepWatchdog.restart()
  }

  // PIP11 in one function: the exit code and the text are diagnostics, never
  // a verdict. `hyprctl` says `ok` for a dispatch that did nothing at all, so
  // the only thing this does is move to the next step.
  function pipNoteStep(text, exitCode) {
    pipStepWatchdog.stop()
    if (!root.pipBusy) return
    var line = String(text || "").trim()
    // Model.pipDispatchAccepted reads the reply as a KEYWORD - the
    // compositor prints exactly `ok`, and a refusal arrives as
    // `warning: ...` with rc 0 - so it is the cheap first filter and
    // nothing more. Asking it here rather than re-testing the text with a
    // regex of our own keeps "what does the compositor's reply mean" in one
    // place.
    if (line !== "" && !Model.pipDispatchAccepted(line)) {
      // Redacted like every other process output, though by construction a
      // dispatch vector holds an address, integers and constants and nothing
      // a provider or the user controls (4.11).
      console.warn("omarchy-iptv pip:", Model.redactUrls(line.split("\n")[0]))
    }
    if (exitCode !== 0) {
      // Non-zero means a Lua parse or nil-call error, i.e. a bug in OUR
      // string, never a refused effect. Worth one line; the verdict is still
      // the readback below.
      console.warn("omarchy-iptv pip: the compositor could not parse a dispatch (rc " + exitCode + ")")
    }
    root.pipRunNextStep()
  }

  // The single definition of success in this feature. What was ASKED FOR is
  // the geometry on the way in and the snapshot on the way out, and
  // Model.pipVerify compares a fresh read against it field by field.
  function pipCheck(live) {
    var expected = root.pipIntent === "off" ? root.pipSnapshot : root.pipGeom
    var verdict = Model.pipVerify(live, root.pipIntent, expected)
    if (verdict.ok) {
      root.pipOn = root.pipIntent === "on"
      root.pipFinish(true, "")
      return
    }
    if (root.pipRound >= root.pipMaxRounds) {
      // Stop, leave the window as it is, and say so. A half-applied PiP is
      // visible, and the next `p` reads this same live state and either
      // finishes it or undoes it (design 4.10).
      root.pipOn = Model.pipActive(live)
      // The mismatch the readback found, for the journal. It is a field
      // name from a fixed set, never compositor text and never a value.
      console.warn("omarchy-iptv pip: the window did not reach the requested state ("
                   + String(verdict.reason || "unknown") + ")")
      root.pipFinish(false, "dispatch_failed")
      return
    }
    // Re-plan from what is true NOW, rather than repeating what was planned
    // against what was true then. This is the branch that absorbs a user's
    // own SUPER+T or SUPER+O landing in the middle of our sequence.
    root.pipPhase = "dispatch"
    root.pipPlanRound()
  }

  function pipFinish(ok, code) {
    pipSequenceWatchdog.stop()
    pipStepWatchdog.stop()
    var requested = root.pipMode
    var intent = root.pipIntent
    // The player's record of what the window was is retired only once the
    // window is verifiably back, and the user's own auto-window-resize goes
    // back with it. On a FAILED exit both are kept: the window is still in
    // the corner, so the record still describes something true, and the next
    // `p` reads the live state and finishes or undoes the half-applied
    // sequence using that same snapshot.
    if (ok && intent === "off") {
      root.pipWriteMpv("off", null)
      root.pipSnapshot = null
    }
    root.pipReason = ok ? "" : String(code || "")
    root.pipMode = ""
    root.pipIntent = ""
    root.pipPhase = ""
    root.pipQueue = []
    root.pipRound = 0
    // One of the six codes section 5 gives copy for, decided by
    // Model.pipResultCode from the verdict - so the guide renders a line
    // this service never composed, and a failure reason the model does not
    // recognise becomes `dispatch_failed` rather than leaking a raw
    // compositor word into the footer.
    var result = { ok: ok, kind: "pip", requested: requested,
                   state: root.pipOn ? "on" : "off",
                   code: Model.pipResultCode({ ok: ok, reason: root.pipReason }, intent) }
    if (!ok) result.error = { code: root.pipReason, intent: intent }
    root.pipOutcome(result)
  }

  // The player is gone, so the window it owned is gone, and with it every
  // piece of state this feature has (PIP3: PiP does not survive stop and
  // replay - press the key again).
  function pipReset() {
    pipSequenceWatchdog.stop()
    pipStepWatchdog.stop()
    root.playerPid = 0
    root.pipOn = false
    // Nothing left to focus either: the window went with the process, and a
    // pending focus would be aimed at an address that no longer exists.
    root.pipFocusPending = false
    root.pipMode = ""
    root.pipIntent = ""
    root.pipPhase = ""
    root.pipQueue = []
    root.pipGeom = null
    root.pipLive = null
    root.pipSnapshot = null
  }

  // `player probe` and `player start` both report the mpv pid; G-2 proved it
  // is the pid Hyprland reports for the window, with no wrapper in between.
  function notePlayerPid(value) {
    var pid = Math.floor(Number(value) || 0)
    if (pid <= 0 || pid === root.playerPid) return
    root.playerPid = pid
    // A pid we did not have is the first moment the window can be found at
    // all, so it is the first moment the question in 4.7 step 3 can be
    // answered. On the reattach path this runs before the socket is even
    // armed, which is why the restart case is covered twice over.
    root.pipPeek()
  }

  // ---- what picture in picture IS, asked of the compositor (4.7, D-PIP-4)
  //
  // A request re-reads the window before it plans, which is why `p` kept
  // working across `omarchy restart shell`. This is the other half: the same
  // read, taken once when a player becomes ours, so that what the plugin
  // REPORTS follows the window too. Before it, `status.pip.on` answered
  // false on 30 consecutive samples with the box demonstrably in the corner,
  // the bar tooltip never gained its line, and an accepted request replied
  // `"was":false`.
  //
  // Nothing here remembers anything: the decision is Model.pipDeriveState,
  // which is given the compositor's own bytes and no previous value at all.
  function pipPeek() {
    var gate = Model.pipDeriveGate({ pid: root.playerPid, busy: root.pipBusy, reading: root.pipPeeking })
    if (!gate.ok) return false
    root.pipPeeking = true
    hyprPeekProc.running = true
    pipPeekWatchdog.restart()
    return true
  }

  // The read came back. A request that started in the meantime owns the
  // answer - its read is fresher and it is about to verify it - so this
  // stands down rather than overwriting a verified state with an older one.
  function pipApplyPeek(text) {
    pipPeekWatchdog.stop()
    root.pipPeeking = false
    var wantedFocus = root.pipFocusPending
    root.pipFocusPending = false
    var derived = Model.pipDeriveState(text, root.playerPid, root.pipClass)
    // `decided` false means the read could not see OUR window: garbage, no
    // match, or two matches. Saying "off" on the strength of that would be
    // the same defect pointing the other way, so nothing is written. A
    // request that started in the meantime owns the answer too - its read is
    // fresher and it is about to verify it.
    if (derived.decided && !root.pipBusy) root.pipOn = derived.on
    // D-PIP-5: focus the window this read RESOLVED. An undecided read leaves
    // the address empty, the builder refuses it, and nothing is dispatched -
    // which is the honest answer when we cannot say which window we mean.
    if (wantedFocus && derived.decided) root.dispatchFocus(derived.address)
  }

  // The two mpv-side writes (4.6). Both go over the socket the service
  // already holds; a dead socket answers false and that is recorded, never
  // fatal - the compositor half is what PiP actually is.
  function pipWriteMpv(intent, live) {
    // Kept in memory too, so an exit in the same session does not depend on
    // a round trip; the player's copy is what survives a shell restart. Set
    // BEFORE the write, because the write can fail and the compositor half
    // still applies - the snapshot must describe what we are about to do
    // either way. The "off" case does NOT clear it here: Model.pipPlan and
    // Model.pipVerify are both still to read it; pipFinish clears it.
    //
    // Model.pipMpvCommands derives the snapshot from the same live read, so
    // what goes into the player and what stays in memory are one function's
    // output rather than two that could drift.
    if (intent === "on") root.pipSnapshot = Model.pipSnapshotFor(live)
    var sock = root.playerSocket
    if (!root.socketAttached()) return false
    var commands = Model.pipMpvCommands(intent, { live: live, mpvArgs: root.mpvArgs })
    for (var i = 0; i < commands.length; i++) root.socketWrite(sock, commands[i], 0)
    if (sock.flush) sock.flush()
    return true
  }

  // Read the snapshot back out of the surviving player. Needed in exactly one
  // case - the shell restarted while in PiP and the user then exits - so it
  // is one get_property issued from onPlayerAttached, and a failure degrades
  // to "unpin and unfloat", never to stuck (4.5, 4.7).
  function pipRequestSnapshot(sock) {
    root.socketWrite(sock, ["get_property", Model.PIP_SNAPSHOT_KEY], root.pipSnapshotRequestId)
    root.socketWrite(sock, ["get_property", "pid"], root.pipPidRequestId)
  }

  // Our own replies on the player socket, routed by request id. Returns true
  // when the line was ours, so the event router never sees it.
  function pipNoteReply(line) {
    var reply = Model.parsePlayerReply(line)
    if (!reply) return false
    if (reply.requestId === root.pipSnapshotRequestId) {
      root.pipSnapshot = reply.ok ? Model.pipParseSnapshot(reply.data) : null
      return true
    }
    if (reply.requestId !== root.pipPidRequestId) return false
    if (reply.ok) root.notePlayerPid(reply.data)
    return true
  }

  // The settings entry the guide and the service both read (design section
  // 6). Read from the bar entry rather than from `settings`, because
  // `pipOptions` is the clamp for these three keys and running a value
  // through two different clamps is how they drift apart.
  function pipConfig() {
    return Model.findBarEntry(root.shell ? root.shell.barConfig : null, root.pluginId, Commons.Util.barSections) || ({})
  }

  // D-SRC-37 (c), rule 15 -- D-PLY-26: the two decide-once compositor probes
  // had no watchdog. They are the shape of whichProc (a process the start
  // waits on with no bound), found by the search for it and bounded by ONE
  // Timer over whichever of the pair is running, the way stateInitWatchdog
  // covers mkdir and the init. A probe the watchdog stopped exits non-zero
  // and PiP is hidden, the answer the exit code gave before. Root functions
  // so the harness runs the same code.
  function runPipProbe() {
    hyprWhichProc.running = true
    pipProbeWatchdog.restart()
  }

  function handlePipWhichExit(exitCode) {
    pipProbeWatchdog.stop()
    if (exitCode !== 0 || Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE") === "") {
      root.pipAvailable = false
      return
    }
    hyprInfoProc.running = true
    pipProbeWatchdog.restart()
  }

  // Anything else - an older Hyprland on the hyprlang provider, or a
  // systeminfo this build does not print - means a compositor whose
  // dispatch language we do not speak. PiP is then hidden rather than
  // broken: `p` says so immediately instead of dispatching strings that
  // cannot parse and calling it `dispatch_failed` fifteen seconds later.
  function handlePipInfoExit(exitCode) {
    pipProbeWatchdog.stop()
    root.pipProvider = /configProvider:\s*lua/i.test(String(hyprInfoStdout.text)) ? "lua" : "other"
    root.pipAvailable = exitCode === 0 && root.pipProvider === "lua"
  }
