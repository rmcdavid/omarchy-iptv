// Service-sources.js -- a code-behind of Service.qml (D-REL-14). Each function here was
// moved byte for byte out of Service.qml, which reaches it through a
// one-line forwarder left at its old place; it runs in Service.qml's own
// scope. Edit a function here, never its forwarder.

  function beginSwitch() {
    root.switchStartedAt = Date.now()
    root.switching = true
    switchTimeout.restart()
  }

  function abortSwitch() {
    switchTimeout.stop()
    root.switching = false
  }

  // The new source's channels.json (or its absence) has been applied.
  function finishSwitch() {
    if (!root.switching) return
    switchTimeout.stop()
    root.switching = false
    if (root.debugTiming) {
      console.info("omarchy-iptv switch " + Math.round(Date.now() - root.switchStartedAt) + " ms (" + root.channels.length + " channels; read "
                   + Math.round(root.switchReadMs) + " ms, prepare " + Math.round(root.switchParseMs) + " ms, bindings " + Math.round(root.switchAssignMs) + " ms)")
    }
    root.sourceSwitched(root.activeSourceKey)
  }

  // One probe at a time (section 4.6): `playlist` into the source's own
  // directory. `key` is the record concerned, `dirKey` the directory
  // written (they differ for a URL edit), `mode` add | edit | switch |
  // retry, `commit` whether success writes the settings.
  function startProbe(key, dirKey, mode, commit) {
    var rec = root.probeRecord(mode, key)
    if (!rec || root.probing) {
      root.probeAdd = null
      root.probeEdit = null
      if (!rec) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
      return root.sourceResult(false, "busy", Model.sourceErrorMessage("busy"), root.probingKey)
    }
    root.probingKey = key
    root.probeDirKey = dirKey
    root.probeMode = mode
    root.probeCommit = commit
    root.probeCancelled = false
    root.probeTimedOut = false
    root.sourceErrors = root.withoutKey(root.sourceErrors, key)
    // D-SRC-69: this probe's claim on its folder, counted before any cache
    // job can be decided again, so a removal queued earlier for this key
    // knows the folder is the probe's now (Model.cacheJobArgs).
    root.sourceProbeSeq += 1
    root.sourceProbeClaims = root.withKey(root.sourceProbeClaims, dirKey, root.sourceProbeSeq)
    // D-SRC-69, the other order: a running cache job decided before this
    // probe existed and able to take its folder -- the helper is still
    // starting, or has listed sources/ and not reached it -- is waited for.
    // Its exit starts the probe (handleCacheExit). The watchdog bounds the
    // wait too: a job that never exits fails the probe as a timeout.
    if (cacheProc.running && root.cacheJob && Model.probeWaitsFor(root.cacheJob.args, dirKey)) {
      root.probeHeld = true
      probeWatchdog.restart()
      return root.sourceResult(true, "ok", "", key)
    }
    root.launchProbe()
    return root.sourceResult(true, "ok", "", key)
  }

  // The helper run of the probe startProbe set up (at once, or at the exit
  // of the cache job it was held behind). A record that went away while it
  // was held ends the probe as the record-less one it is.
  function launchProbe() {
    root.probeHeld = false
    var rec = root.probeRecord(root.probeMode, root.probingKey)
    if (!rec) {
      root.handleProbeExit("")
      return
    }
    var dirKey = root.probeDirKey
    // D-ID-1: NO `--state-dir` here, deliberately, and this absence is
    // load-bearing rather than an oversight. A probe runs for every source
    // add, edit, switch and re-check, including ones the user then cancels.
    // Passing the flag would remap the global favourites against a playlist
    // that never became the active list. The helper touches no state file
    // without the flag, so this is safe by construction.
    // D-SINK-8: a candidate's URL is as credentialed as the active one, so it
    // goes in the environment too, assigned immediately before the run so a
    // re-check of source B never runs with source A's URL (the assignment
    // replaces, measured; see Model.fetchEnvironment). D-SINK-40: a URL the
    // user is adding or re-checking is theirs.
    root.runHelper(sourceProbeProc, Model.playlistProbeArgv(root.helperPath, Model.sourceCacheDir(root.cacheDir, dirKey)),
                   Model.fetchEnvironmentFor(rec.url, { origin: "user" }))
    probeWatchdog.restart()
  }

  function handleProbeExit(text) {
    probeWatchdog.stop()
    var key = root.probingKey
    var dirKey = root.probeDirKey
    var mode = root.probeMode
    var commit = root.probeCommit
    var cancelled = root.probeCancelled
    var timedOut = root.probeTimedOut
    var pending = mode === "add" ? root.probeAdd : (mode === "edit" ? root.probeEdit : null)
    root.probeHeld = false
    root.probingKey = ""
    root.probeDirKey = ""
    root.probeMode = ""
    root.probeCancelled = false
    root.probeTimedOut = false
    root.probeAdd = null
    root.probeEdit = null
    var st = root.userState
    var rec = pending || Model.findSource(st.sources, key)
    var host = root.hostForRecord(rec)
    var nowSec = Math.floor(Date.now() / 1000)
    if (cancelled) {
      // SR7: the directory the probe was writing is discarded; a pending
      // add or replacement was never recorded (SR23) and the form keeps its
      // values (UX 5.5). D-SRC-70: a re-check of the ACTIVE source wrote
      // into the active source's own folder, not a new one, and the removal
      // is dropped when it runs (Model.cacheJobDrop "active"), the way the
      // prune always keeps that folder.
      root.queueCacheJob(["remove", "--key", dirKey], null)
      root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: "", host: host, cancelled: true, replacedId: "" })
      return
    }
    var status = Model.parseHelperStatus(timedOut ? root.helperTimeoutStatus("playlist", false) : text, "playlist")
    if (!rec) {
      root.queueCacheJob(["remove", "--key", dirKey], null)
      root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: Model.sourceErrorMessage("unknown_source"), code: "unknown_source", host: "", cancelled: false, replacedId: "" })
      return
    }
    // R22a: a probe that ENDS in the no-write mode (started before a reload
    // that was not a state) records nothing. Its commit is a state write and
    // a key mirror, and an add or a switch that would not be kept is refused
    // here as the verbs that start one are; nothing is deleted either (the
    // start-up prune drops a directory no record names).
    if (root.stateWriteBlocked !== "") {
      root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: Model.sourceErrorMessage("state_unreadable"), code: "state_unreadable", host: host, cancelled: false, replacedId: "" })
      return
    }
    if (status.ok === true) {
      var newKey = key
      // D-SRC-70: the edited record's old folder, removed once the state
      // that moves the pointer off it is published (below). A removal of
      // the key that is active when it runs is dropped (Model.cacheJobDrop),
      // and a job queued here can run at once, while root.userState -- and
      // so the active key -- is still the one before the commit: queued
      // here, an edit of the ACTIVE source would keep its old folder.
      var retiredKey = ""
      if (pending) {
        // Record the pending add now (SR23), or move the edited record to
        // its new key (SR7): the old record and its directory go.
        if (mode === "edit") {
          st = Model.removeSource(st, key).state
          retiredKey = key
          root.sourceErrors = root.withoutKey(root.sourceErrors, key)
        }
        var known = Model.findSourceByUrl(st.sources, pending.url)
        // R27c (D-SRC-41): the cap, against the state as it is NOW -- after any
        // merge that landed while the probe ran (a hand-run `state source add`
        // can take the last place). Until R27 the commit appended a 51st
        // record, which the next start's parse drops, silently. Refused with
        // `too_many`, told through the probe's own result; nothing recorded,
        // the probe's directory goes. An edit's old record is gone by here,
        // so a replacement never trips it.
        if (!known && Model.sourcesFull(st)) {
          root.queueCacheJob(["remove", "--key", dirKey], null)
          console.warn("omarchy-iptv: the new source was not added: Sources is full (" + Model.MAX_SOURCES + ")")
          root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: Model.sourceErrorMessage("too_many"), code: "too_many",
                                     host: host, cancelled: false, replacedId: "" })
          return
        }
        if (known) {
          // The same URL arrived while the probe ran (S5: a second add, or
          // the migration of an entry that named it): that record wins and
          // the counts land on it. Its own guide URL stands; R19c's
          // later-by-time landing of the form's is withdrawn with R21.
          newKey = String(known.key)
        } else {
          // D-SINK-48: new keys are random, so the probe's own key is
          // handed back and kept while it is free -- the probe's folder IS the
          // source's cache.
          newKey = Model.allocateSourceKey(st.sources, pending.url, pending.key)
          var record = pending
          if (newKey !== pending.key) {
            record = {}
            for (var k in pending) record[k] = pending[k]
            record.key = newKey
          }
          st = Model.cloneState(st, { sources: st.sources.concat([record]) })
        }
        // A key that moved (a colliding record appeared meanwhile) leaves
        // the probe's directory behind: it is dropped and the freshness
        // check fetches the source again.
        if (newKey !== dirKey) root.queueCacheJob(["remove", "--key", dirKey], null)
      }
      st = Model.withSourceStats(st, newKey, status, nowSec)
      st = Model.touchSource(st, newKey, nowSec)
      // D-SRC-14: decided against the active key as it still is (root.userState
      // has not moved), BEFORE the state is published. An edit of the active
      // source folds the pointer into this same state, so no assignment ever
      // publishes a state with no active source (configured flickered false,
      // clearSourceData ran, and a key-less save went out before the key's).
      var plan = Model.probeCommitPlan({ commit: commit, mode: mode, key: key, newKey: newKey, activeKey: root.activeSourceKey })
      st = Model.probeCommitState(st, plan, newKey)
      // beginSwitch BEFORE the key moves (switchSource's rule): with the
      // pointer folded, the assignment below is the move, and it fans out to
      // onActiveCacheDirChanged, which can call finishSwitch.
      if (plan.act === "switch") root.beginSwitch()
      root.userState = st
      root.saveState()
      if (retiredKey !== "") root.queueCacheJob(["remove", "--key", retiredKey], null)
      if (plan.act === "reload") {
        // Already the active directory (a retry of the active source):
        // the FileViews watch it, but reload deterministically.
        channelsFile.reload()
        playlistStatusFile.reload()
      } else if (plan.act === "switch") {
        // D-SINK-19: `newKey`, not `rec.key`. They differ when a colliding
        // record appeared through the CLI while the probe ran (S5, the
        // `known` branch above), and the pointer has to name the record the
        // history actually kept. The URL pair this used to pass hid that:
        // `rec.url` was right either way, so the bug could not show.
        // For the folded edit the key is already in memory, so this plans
        // `write-entry-after-saved`: the one save above, then the mirror.
        if (!root.persistActive(newKey)) {
          console.warn("omarchy-iptv: adopted source but could not mirror the key into the bar entry")
        }
      }
      root.sourceProbeFinished({
        ok: true, id: newKey, channelCount: Number(status.channelCount) || 0, groupCount: Number(status.groupCount) || 0,
        reason: "", host: host, cancelled: false, replacedId: mode === "edit" ? key : ""
      })
      return
    }
    // Failure (S8): the previous active source is untouched. A pending add
    // or replacement was never recorded and its directory goes (SR23); an
    // existing record keeps fetchedAt 0 plus a session-only reason for the
    // result line (SR26).
    // D-SRC-71: the code rides along, as on the refusals above (R28e), so
    // a failure on this machine -- the cache unwritable, the helper failing
    // or timing out -- is not put after the provider's host
    // (Model.probeFailureLine).
    var reason = Model.statusReason(status)
    if (pending) root.queueCacheJob(["remove", "--key", dirKey], null)
    else root.sourceErrors = root.withKey(root.sourceErrors, key, reason)
    root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: reason, code: Model.statusCode(status), host: host, cancelled: false, replacedId: "" })
  }

  // D-SINK-19, round 11 (R21). WHAT THE BAR ENTRY'S URLS MEAN: one
  // migration, then nothing.
  //
  // While the LANDED state does not carry the migration marker
  // (Model.entryMigratedOf over `landedState`), the entry's `playlistUrl` and
  // `epgUrl` are adopted exactly as they were before round 11 (R1: a URL
  // before any key is trusted; R4: a guide URL onto the active record), and
  // the marker rides the same state write (Model.adoptActiveSource). The
  // entry keeps them until that write has landed (R13, Model.retiredInputsToKeep).
  // From then on nothing on the entry is an input: a value found there is
  // refused, reported once per value (Model.entryInputNotice, through
  // reportEntryInput) and stripped by the owned write this asks for. An
  // EMPTY value is never a command, in either phase: the plugin strips the
  // keys on its own writes, the host comes to report them absent, and if
  // that meant "no active source" the host catching up would un-configure
  // the plugin. Clearing the active source is `removeSource`.
  //
  // The decision is Model.reconcileAction (what this write means) and
  // Model.adoptActiveSource (what the active source is now), so a test can
  // call both (rule 12). This function moves the session's in-memory record
  // of what it has handled (`entryInputsSeen`), reports, and hands the plan on.
  function reconcile(force) {
    // R22a: in the no-write mode the migration does not run, nothing is
    // reported and nothing is stripped -- whether the marker landed is
    // exactly what the unread file would have said.
    if (!root.stateLoaded || root.stateWriteBlocked !== "") return
    var s = root.settings
    var playlist = String(s.playlistUrl || "")
    var epg = String(s.epgUrl || "")
    // D-SRC-64: `parked` is the pair a held migration has parked in the
    // state (memory: the hold is this session's), the migration's input
    // whenever the entry carries no playlist URL -- after the hold's strip,
    // at a restart mid-hold, and at the retry a removal asks for.
    var plan = Model.reconcileAction({ first: !root.reconciled, force: force === true,
                                       migrating: !Model.entryMigratedOf(root.landedState),
                                       playlist: playlist, epg: epg, seen: root.entryInputsSeen,
                                       heldFull: root.migrationHeldFull,
                                       parked: Model.migrationPendingOf(root.userState) })
    root.reconciled = true
    // Every value this reconcile looked at is handled from here on: adopted
    // below, or refused and reported here. The host's stale publish of it
    // (rule 9) is neither adopted nor reported again.
    root.entryInputsSeen = Model.entryInputsSeenAfter(root.entryInputsSeen, { playlistUrl: playlist, epgUrl: epg })
    for (var i = 0; i < plan.report.length; i++) root.reportEntryInput(plan.report[i], "retired")
    // "ignore" with no guide URL to adopt is the ordinary steady state.
    if (!(plan.act === "ignore" && !plan.adoptEpg)) root.adoptActive(playlist, epg, plan)
    // R21b: a refused value leaves by the next owned write, and this is it --
    // deferred, never from inside the settings' own change notification.
    if (plan.refused.length > 0) Qt.callLater(root.stripEntryInputs)
  }

  // R21b. The owned write that takes a refused value off the bar entry: the
  // PATCH-ONLY shape (R16), every owned key at the value the plugin already
  // acts on and nothing moved, so it needs no gate -- it cannot mirror a key
  // the file does not have, and once the marker has landed the funnel strips
  // every retired key (Model.retiredInputsToKeep). The key mirror's own heal
  // stays persistActive's, under R13. On the lagging host the publish keeps
  // showing the value after the strip; the write that answers it is a no-op
  // the host answers `false` to, and Model.sameOwnWrite settles the cycle
  // (R19a). One function rather than a closure, so Qt.callLater folds a burst
  // of settings changes into one write.
  function stripEntryInputs() {
    if (!Model.entryMigratedOf(root.landedState)) return
    root.writeOwnedEntry({}, "refused bar setting", false, true)
  }

  // R21b. The one report of a value taken off the bar entry without being
  // adopted: a desktop notification and a console line, both the sentence
  // Model.entryInputNotice composes from the setting's NAME and the reason --
  // never the value (rule 5) -- and one { setting, reason } on
  // `entryInputReports` for the harness to count. Called once per value:
  // reconcile() only asks for a value `entryInputsSeen` has not seen.
  function reportEntryInput(setting, reason) {
    var notice = Model.entryInputNotice(setting, reason)
    console.warn("omarchy-iptv: " + notice.body)
    root.notify("entryInputRefused", { setting: setting, reason: reason })
    var reports = root.entryInputReports.slice()
    reports.push({ setting: String(setting), reason: String(reason) })
    while (reports.length > 32) reports.shift()
    root.entryInputReports = reports
  }

  // D-SINK-19. ONE resolver for the state load, the `shell` arrival, the
  // migration of an install whose active source was named by a URL on the
  // bar entry, and a settings change (R1).
  //
  // Model.adoptActiveSource holds the decision (and the reasoning for the
  // order it takes it in). What belongs here is only the consequences: write
  // the state if it moved -- the migration marker rides that write (R21a) --
  // mirror the key into the entry, which is also what takes the URLs out of
  // it once that write has landed, and surface an invalid migration value
  // through D16's synthesized status.
  //
  // Idempotent by construction: a second run over the same inputs finds the
  // values seen (reconcileAction) and the state's own `activeKey` answering.
  function adoptActive(playlist, epg, plan) {
    var entry = { playlistUrl: playlist, epgUrl: epg, sourceKey: String(root.settings.sourceKey || "") }
    var out = Model.adoptActiveSource(root.userState, entry, Math.floor(Date.now() / 1000), "",
                                      { adoptUrl: plan.adoptUrl === true, adoptEpg: plan.adoptEpg === true,
                                        migrating: plan.migrating === true })
    root.settingsInvalid = out.invalid
    // R21c: a guide URL the migration found with no source to guide, and one
    // that does not validate, are reported and stripped -- never held.
    if (out.noSourceEpg) root.reportEntryInput("epgUrl", "no-source")
    if (out.refusedEpg) root.reportEntryInput("epgUrl", "invalid")
    // R29d: a guide URL that came with an unusable playlist is told WITH it,
    // in one notice, and goes with it (the owned write strips both once the
    // marker has landed); never adopted onto the active source.
    if (out.invalid) root.reportEntryInput("playlistUrl", out.epgWithInvalid ? "invalid-pair" : "invalid")
    else if (out.epgWithInvalid) root.reportEntryInput("epgUrl", "invalid-pair")
    if (out.marked) console.warn("omarchy-iptv: migrating the bar entry: its URLs are read this once, and the Sources screen is where sources are kept from now on")
    if (out.marked) root.migrationAddedKey = out.added
    // R27d (D-SRC-44): the migration did not run -- Sources is full and it
    // never evicts. The user is told ONCE (Model.entryInputNotice "full": no
    // URL, no label), and the next reconcile after a removal tries again.
    // D-SRC-64 (round 7, the owner's decision): the pair is PARKED in the
    // state (Model.adoptActiveSource wrote `migrationPending` into
    // `out.state`; `out.changed` says the write is new), the save below
    // carries it into state.json (0600), and the owned write persistActive
    // asks for -- which waits for that save to LAND (R13) -- takes both
    // URLs off the bar entry (Model.retiredInputsToKeep over the landed
    // pair). No marker: the migration is still to run. A save that FAILS
    // leaves the entry as it is (the keep rule reads the LANDED state), so
    // the entry stays the backup until a later save lands or the next start
    // re-adopts it (R21e's shape). The journal says so, without a URL.
    if (out.full) {
      root.migrationHeldFull = true
      if (out.parked && out.changed) console.warn("omarchy-iptv: the bar entry's playlist" + (out.heldEpg ? " and guide URL are" : " is") + " kept in state.json until a source is removed; the entry is cleared once that write has landed")
      if (!root.migrationFullTold) {
        root.migrationFullTold = true
        root.reportEntryInput("playlistUrl", "full")
      }
    } else if (out.adoptedUrl) {
      root.migrationHeldFull = false
    }
    if (out.moved) {
      // A new source starts clean: the previous source's reason and host
      // must not stay on screen while its first fetch runs (UX 4.5,
      // D-LIVE-10). The fetch itself is driven by the new cache's freshness
      // once its directory is bound (section 4.4 step 6), never from here.
      // `moved`, not "the input changed": a refused value over a working
      // source used to blank that source's status line (review P3).
      root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, error: null })
      root.playlistLoadWarnings = []
      root.lastError = ""
    }
    if (out.changed) {
      root.userState = out.state
      root.saveState()
    }
    if (out.invalid) {
      // D16, narrowed by D-SINK-19: the error becomes the guide's body only
      // when there is no active source to show instead (re-applied by
      // clearSourceData when the cache directory unbinds, D-SRC-03).
      root.applyInvalidStatus()
      if (!root.invalidInputBlocks) console.warn("omarchy-iptv: ignoring an invalid playlistUrl setting; the active source is unchanged")
    }
    // The entry still carries a URL (a 0.13.x entry, a value just adopted,
    // or a refused one), or its mirrored key disagrees with the state. One
    // owned write fixes both; Model.adoptActiveSource decides (`writeEntry`).
    // Deferred: never write the host's settings from inside their own change
    // notification. persistActive saves the state again only if the key
    // actually moves, so the save above is not duplicated, and its ORDER
    // against the entry write is Model.pointerWritePlan's (R5): the entry
    // waits for the save above -- the one that carries the marker -- to
    // LAND (R13), and until it has, the funnel keeps the URLs (R21a).
    //
    // An INVALID value is written out too, and that is deliberate: a value
    // that failed validation can still carry credentials (`ftp://u:p@h/x`,
    // or a URL over the 2,048 cap), rule 5 treats whole URLs as secrets, and
    // the plugin has already reported it.
    if (out.writeEntry) {
      var key = out.key
      // The root builds the deferred call (persistActiveLater): a closure
      // made in this file and handed to Qt.callLater takes the engine down
      // if the Service is deleted before it runs (D-REL-15).
      root.persistActiveLater(key)
    }
  }

  // The synthesized status for an invalid configured URL (D16, SR8): the
  // UX 5.4 sentence, no host, no helper run.
  function applyInvalidStatus() {
    if (!root.invalidInputBlocks) return
    var code = String(root.settingsInvalid.code || "invalid")
    root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, sourceHost: "", error: { code: code, message: Model.sourceErrorMessage(code) } })
    root.lastError = root.statusReason
  }

  // Section 4.4 step 4: once per state file, move the 0.1 single cache
  // into the active source's directory. Needs `shell`, because the active key
  // may still have to be migrated off the bar entry (adoptActive, D-SINK-19);
  // without a configured source the legacy files are deleted.
  function startCacheLayout() {
    if (root.cacheReady || root.cacheMigrating || !root.stateLoaded || !root.shell) return
    if (root.userState.cacheLayout === 2) {
      root.cacheReady = true
      root.schedulePrune()
      return
    }
    root.cacheMigrating = true
    var args = ["migrate"]
    if (root.activeSourceKey !== "") args = args.concat(["--key", root.activeSourceKey])
    // CLOSURE-EXCEPTION: held only in root.cacheQueue and root.cacheJob,
    // and called only by runNextCacheJob and handleCacheExit, synchronously,
    // within a call into this Service (cacheProc's exit, the state init's, a
    // root function); nothing outside the Service holds it, and it is never
    // handed to Qt.callLater or a signal, the two that call a code-behind's
    // function after its Service is gone (D-REL-15).
    root.queueCacheJob(args, function(status) {
      root.cacheMigrating = false
      if (status.ok === true) {
        root.userState = Model.withCacheLayout(root.userState, 2)
        root.saveState()
      }
      root.cacheReady = true
      root.schedulePrune()
    })
  }

  // Section 4.4 step 7: once per start, drop orphan directories and age the
  // EPG files and logo folders of inactive sources.
  function schedulePrune() {
    if (root.pruned) return
    root.pruned = true
    root.queuePrune()
  }

  // D-LOGO-20 (R32f): the same prune again at every source switch
  // (onActiveCacheDirChanged, once the start-up one has been queued), so the
  // install-wide logo bound ARCHITECTURE section 8 item 17 states -- 1.22 GiB
  // for the active source plus 1.22 GiB for each source given logos within
  // the day -- holds at every moment of a session and not only after a
  // restart: a session that switched through fifty sources with logos on
  // used to keep all fifty folders until the next start. Keys only; the
  // helper skips a folder a running fetch holds and says so once.
  // D-SRC-69 (2026-10-27): queued as ["prune"] and given its list when it
  // RUNS (runNextCacheJob, Model.pruneArgs), not here. The start-up prune is
  // queued at cacheReady and runs at dirsReady, and its list used to be the
  // records of the first moment: an add made between the two probed into a
  // folder no record named yet and lost it.
  function queuePrune() {
    root.queueCacheJob(["prune"], null)
  }

  // Section 4.7: one cacheProc, a FIFO of { args, onDone, seq }; failures
  // are logged with the action and code only. `seq` is the probe count when
  // the job was asked for (D-SRC-69, Model.cacheJobArgs).
  function queueCacheJob(args, onDone) {
    var queue = root.cacheQueue.slice()
    queue.push({ args: args, onDone: onDone, seq: root.sourceProbeSeq })
    root.cacheQueue = queue
    root.runNextCacheJob()
  }

  // D-SRC-69: what a job deletes is decided HERE, when it runs, against the
  // state, the active key and the probe in flight as they are now
  // (Model.cacheJobArgs): a prune keeps every record and the folder a probe
  // not yet handled writes into; a removal a later probe has claimed the
  // folder of is dropped. probingKey and probeDirKey are cleared only by
  // handleProbeExit, so a probe whose process has ended and whose exit has
  // not been handled still counts as in flight.
  function cacheJobContext() {
    var inFlight = []
    if (root.probeDirKey !== "") inFlight.push(root.probeDirKey)
    if (root.probingKey !== "" && root.probingKey !== root.probeDirKey) inFlight.push(root.probingKey)
    return { state: root.userState, activeKey: root.activeSourceKey, inFlight: inFlight, claims: root.sourceProbeClaims, epgMaxAgeSec: root.epgMaxAgeSec }
  }

  function runNextCacheJob() {
    for (;;) {
      if (cacheProc.running || root.cacheQueue.length === 0 || !root.dirsReady) return
      var job = root.cacheQueue[0]
      root.cacheQueue = root.cacheQueue.slice(1)
      var context = root.cacheJobContext()
      var args = Model.cacheJobArgs(job, context)
      if (args === null) {
        // Keys only (R12): the folder is a later probe's, not the garbage
        // this job was asked to take (D-SRC-69), or it is the ACTIVE
        // source's, which no cache job takes, the way the prune always
        // keeps it (D-SRC-70).
        var why = Model.cacheJobDrop(job, context) === "active" ? "it is the active source's folder" : "a probe has started writing there since it was asked for"
        console.info("omarchy-iptv: cache " + job.args[0] + " of " + Model.asList(job.args).slice(1).join(" ") + " dropped: " + why)
        if (typeof job.onDone === "function") job.onDone({ ok: true, kind: "cache", skipped: true, error: null })
        continue
      }
      root.cacheJob = { args: args, onDone: job.onDone, seq: job.seq }
      root.runHelper(cacheProc, Model.cacheRunArgv(root.helperPath, root.cacheDir, args), {})
      cacheWatchdog.restart()   // D-SRC-37 (c): every run of the slot is bounded
      return
    }
  }

  function handleCacheExit(text) {
    cacheWatchdog.stop()
    var job = root.cacheJob
    root.cacheJob = null
    var status = Model.parseHelperStatus(text, "cache")
    if (status.ok !== true) console.warn("omarchy-iptv: cache " + (job ? job.args[0] : "?") + " failed:", status.error ? status.error.code : "error")
    if (job && typeof job.onDone === "function") job.onDone(status)
    // D-SRC-69: a probe held behind this job starts now. The next job is
    // decided with it in flight either way: probingKey and probeDirKey are
    // set while it is held (cacheJobContext), so a prune queued next keeps
    // its folder and a removal of that key is dropped.
    if (root.probeHeld) root.launchProbe()
    root.runNextCacheJob()
  }

  // Section 4.4 step 6: after a cache swap, playlist-status.json decides
  // whether the source is refreshed in the background (older than
  // refreshMinutes, never fetched, or last run failed).
  function applyFreshness() {
    if (!root.pendingFreshness) return
    root.pendingFreshness = false
    if (root.activeCacheDir === "") return
    var nowSec = Math.floor(Date.now() / 1000)
    // D-SINK-41, D-SINK-80: a cache written before the destination rules
    // or the attribute grammar is refreshed once, whatever its age
    // (Model.cacheBeforeDestinationRules). A guide window written before
    // D-SINK-79's fold is refetched by the helper's own stamp (GUIDE_RULES).
    if (Model.cacheStale(root.playlistStatus, root.refreshMinutes, nowSec)
        || Model.cacheBeforeDestinationRules(root.playlistStatus)) root.refreshPlaylist(true)
    if (root.epgFetchUrl !== "" && !epgProc.running) root.refreshEpg(true)
  }

  // Reset the per-source data to "nothing known yet" so no reason, count
  // or programme of the previous source survives a swap (D-LIVE-10). An
  // invalid configured URL keeps its synthesized status: the directory
  // unbinds after reconcile() set it, and the guide must not fall back to
  // `Loading playlist...` for good (D-SRC-03).
  function clearSourceData() {
    root.channels = []
    root.channelIndex = Model.keyedMap()
    // No stale numbers across a swap: the number space belongs to one source
    // (1.5), and a guide showing the previous playlist's numbers would let a
    // digit tune to a channel that is no longer loaded.
    root.chnoIndex = Model.buildChnoIndex(null)
    root.preparedActive = null
    root.channelsMeta = ({})
    root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, error: null })
    root.playlistLoadWarnings = []
    root.playlistAttempted = false
    root.epgNow = Model.emptyEpgStore()
    root.epgMeta = ({})
    root.epgLoaded = false
    root.epgAttempted = false
    root.epgStatus = ({ ok: false, kind: "epg", stale: false, error: null })
    root.epgWarnings = []
    root.lastError = ""
    // The announced logo set belongs to the directory it was announced for,
    // and that directory is the one being left. Clearing it here is belt to
    // the tag's braces: a set tagged for the old directory is blank in every
    // slot already (Model.logoSlot), but it would still be COUNTED on the IPC
    // status. What a still-running fetch prints after this lands tagged for
    // ITS directory (flushLogoNames), blank in every slot, until the new
    // playlist loads and fetchLogos() stops it and starts one for this one.
    root.logoHave = ({})
    root.logoPending = []
    root.applyInvalidStatus()
  }

  // D-SINK-98: the IPC status names the label as sourcesSummary does, and the
  // model composes it (Model.activeSourceSummary).
  function activeSourceSummary() {
    return Model.activeSourceSummary(root.userState, root.activeSourceKey, root.nowSec)
  }

  // What enabling logos would disclose, counted from the cache and contacting
  // nothing. The guide shows these numbers BEFORE the switch is thrown
  // (ruling rule 6): a generic "may contact third parties" is not informed
  // consent when the real answer is countable.
  function logoSurvey() { return Model.logoSurvey(root.channels) }

  // Debounced: settings changes, timers and the bar's middle click all funnel
  // through here so the helper never runs twice for one user action.
  // The URLs are read directly, never through the derived `configured` /
  // `epgConfigured` bindings: from on<Url>Changed those may not have been
  // re-evaluated yet, which is what kept an epgUrl set at runtime from ever
  // loading (D-LIVE-02). Since D-SINK-19 `playlistUrl` is the ACTIVE
  // RECORD's URL rather than the bar entry's; the rule is the same and so is
  // the reason for it.
  function refreshPlaylist(force) {
    if (root.playlistUrl === "") return
    if (playlistProc.running) {
      if (force) root.playlistRerun = true
      return
    }
    refreshDebounce.restart()
  }

  function refreshEpg(force) {
    // M4-01 repair 3: the RESOLVED URL, so a playlist-declared guide fetches
    // like a typed one. Read directly and never through `epgConfigured`, for
    // the reason D-LIVE-02 recorded above.
    if (root.epgFetchUrl === "") return
    if (epgProc.running) {
      if (force) root.epgRerun = true
      return
    }
    epgDebounce.restart()
  }

  function sourceResult(ok, code, message, id, field) {
    var out = { ok: ok, code: code, message: message || "", id: id || "" }
    if (field) out.field = field
    return out
  }

  function sourcesReady() {
    // R22a: refused, not made in memory only -- nothing made now would be kept.
    // R26a (D-SRC-35): and one reload asked for, so a file that is back lifts
    // the mode for the NEXT call (this one is refused either way, R26e).
    root.recheckStateBlock()
    if (root.stateWriteBlocked !== "") return root.sourceResult(false, "state_unreadable", Model.sourceErrorMessage("state_unreadable"), "")
    if (!root.stateLoaded || !root.cacheReady) return root.sourceResult(false, "not_ready", Model.sourceErrorMessage("not_ready"), "")
    if (root.probing || root.switching) return root.sourceResult(false, "busy", Model.sourceErrorMessage("busy"), root.probingKey)
    return null
  }

  // Add a source (S1, S2): Model.addSource sanitizes, validates both URLs
  // and the label, refuses duplicates (`duplicate` carries the existing id;
  // the guide retries a never-fetched one through retrySource) and the cap;
  // the new record is held in memory and probed into its own cache
  // directory; it is recorded and the settings are committed only when the
  // probe succeeds (D8, SR7, SR23). `kind: "xtream"` marks a record built
  // by buildXtreamSource (view kind, UX 8.1).
  function addSource(fields) {
    var f = fields || {}
    var gate = root.sourcesReady()
    if (gate) return gate
    var origin = f.kind === "xtream" ? "xtream" : (String(f.origin || "") || "guide")
    var added = Model.addSource(root.userState, { playlistUrl: f.playlistUrl, epgUrl: f.epgUrl, label: f.label, origin: origin }, Math.floor(Date.now() / 1000))
    if (!added.ok) return root.sourceResult(false, added.code, added.message, added.key, root.resultField(added.code, added.message))
    root.probeAdd = Model.findSource(added.state.sources, added.key)
    return root.startProbe(added.key, added.key, "add", true)
  }

  // Edit a source (S4, S6). Label and EPG changes commit at once (an EPG
  // change of the active source is persisted and refreshed in the
  // background). A changed playlist URL yields a replacement record
  // (Model.updateSource) that is probed into the new key's directory first;
  // the history moves to it, the old directory is deleted and the settings
  // follow only when the probe succeeds (SR7).
  function updateSource(id, fields) {
    var key = String(id || "")
    var gate = root.sourcesReady()
    if (gate) return gate
    var rec = Model.findSource(root.userState.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
    var updated = Model.updateSource(root.userState, key, fields || {}, Math.floor(Date.now() / 1000))
    if (!updated.ok) return root.sourceResult(false, updated.code, updated.message, updated.key, root.resultField(updated.code, updated.message))
    if (!updated.urlChanged) {
      root.userState = updated.state
      root.saveState()
      var next = Model.findSource(updated.state.sources, key)
      // M2-09 GS11: the other half of "a cleared guide URL takes its cache
      // with it". The ACTIVE source reaches that through Service.qml's
      // onActiveEpgUrlChanged, which also catches a change made from outside
      // the plugin; this is an INACTIVE source edited in the Sources form,
      // where activeEpgUrl never moves and nothing else would notice the file
      // is now an orphan.
      if (key !== root.activeSourceKey && String(rec.epgUrl || "") !== "" && next && String(next.epgUrl || "") === "") {
        root.queueCacheJob(["epg-clear", "--key", key], null)
      }
      // D-SINK-19: an EPG URL edit of the ACTIVE source used to be copied
      // into the bar entry here, because that entry was where the active
      // source's guide URL lived. The record is the only place now, and
      // `activeEpgUrl` reads it, so the state write above IS the persist and
      // there is nothing to carry into the host's file. One fewer write, and
      // one fewer URL in a file this plugin does not own.
      return root.sourceResult(true, "ok", "", key)
    }
    // URL change: the replacement lives in memory; nothing in the history
    // moves until the probe succeeds.
    root.probeEdit = Model.findSource(updated.state.sources, updated.key)
    return root.startProbe(key, updated.key, "edit", key === root.activeSourceKey)
  }

  // Remove a source (S7): drops the record, deletes its cache directory
  // through the helper and, when it was active, clears the settings so the
  // guide returns to the first-run state (playback, if any, continues).
  function removeSource(id) {
    var key = String(id || "")
    root.recheckStateBlock()
    if (root.stateWriteBlocked !== "") return root.sourceResult(false, "state_unreadable", Model.sourceErrorMessage("state_unreadable"), key)
    if (!root.stateLoaded || !root.cacheReady) return root.sourceResult(false, "not_ready", Model.sourceErrorMessage("not_ready"), key)
    if (root.probing && (root.probingKey === key || root.probeDirKey === key)) return root.sourceResult(false, "busy", Model.sourceErrorMessage("busy"), key)
    if (root.switching) return root.sourceResult(false, "busy", Model.sourceErrorMessage("busy"), key)
    var removed = Model.removeSource(root.userState, key)
    if (!removed.removed) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
    var wasActive = key === root.activeSourceKey
    root.userState = removed.state
    root.saveState()
    root.sourceErrors = root.withoutKey(root.sourceErrors, key)
    root.queueCacheJob(["remove", "--key", key], null)
    // D-SINK-19: clearing the pointer. The state write IS the removal, and
    // this reports on it being ISSUED (R13; its failure, if any, arrives
    // through stateFile's saveFailed as sourcesPersistFailed with its own
    // reason). Only the entry mirror can be refused, and a stale mirror
    // naming a record that is gone resolves to "no active source"
    // (Model.adoptActiveSource step 3 requires the key to name a record, and
    // Model.removeSource itself clears the pointer in the state it returns,
    // R3), so a refused mirror is logged and repaired on the next start
    // (SR25 as amended 2026-10-12), never reported as the removal failing.
    if (wasActive && !root.persistActive("")) {
      console.warn("omarchy-iptv: removed the active source but could not mirror the cleared key into the bar entry")
    }
    root.sourceRemoved(key)
    // R27d: a migration held because Sources was full runs now there is room
    // -- deferred, after the removal's own save has been asked for.
    if (root.migrationHeldFull) Qt.callLater(root.retryHeldMigration)
    return root.sourceResult(true, "ok", "", key)
  }

  // R27d: one function rather than a closure, so Qt.callLater folds a burst
  // of removals into one reconcile.
  function retryHeldMigration() { if (root.migrationHeldFull) root.reconcile(true) }

  // Switch (S3, D7): a source with a cache commits at once (settings
  // write -> cache FileViews rebind -> redraw from its channels.json ->
  // background refresh when stale); a never-fetched source probes first.
  function switchSource(id) {
    var key = String(id || "")
    var gate = root.sourcesReady()
    if (gate) return gate
    var rec = Model.findSource(root.userState.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
    if (key === root.activeSourceKey) return root.sourceResult(true, "ok", "", key)
    if (!(rec.fetchedAt > 0)) return root.startProbe(key, key, "switch", true)
    root.userState = Model.touchSource(root.userState, key, Math.floor(Date.now() / 1000))
    root.saveState()
    // beginSwitch BEFORE the active key moves: assigning it fans out through
    // activeSourceKey -> activeCacheDir -> onActiveCacheDirChanged in the same
    // turn, and that handler can call finishSwitch.
    root.beginSwitch()
    // D-SINK-19: persistActive writes the active key into the state (which is
    // what every binding in this service reads, so the switch happens in this
    // turn) and then mirrors it into the host entry.
    if (!root.persistActive(key)) {
      // The entry mirror failed; the switch itself has already happened.
      // Report it and let the switch finish, rather than aborting a change
      // that is already in our own state file.
      console.warn("omarchy-iptv: switched source but could not mirror the key into the bar entry")
    }
    return root.sourceResult(true, "ok", "", key)
  }

  // Xtream form (S6, D10, SR16-SR18): Model.xtreamUrls builds the get.php /
  // xmltv.php URLs (no scheme guessing, no userinfo, credentials never
  // truncated) and they are added as an ordinary source. The password lives
  // only inside the URLs from here on; it is never stored or logged on its own.
  function buildXtreamSource(fields) {
    var f = fields || {}
    var built = Model.xtreamUrls(f.server, f.username, f.password)
    if (!built.ok) return root.sourceResult(false, built.code, built.message, "", built.field)
    return root.addSource({ playlistUrl: built.playlistUrl, epgUrl: built.epgUrl, label: f.label, kind: "xtream" })
  }

  // The only call that hands a URL to the guide: the edit form binds
  // `playlistMasked` / `epgMasked` and reveals the raw value on Ctrl+R.
  function sourceForEdit(id) {
    return Model.sourceForEdit(root.userState, String(id || ""))
  }

  // Probe again a record that failed to fetch (S8); a fetched record is
  // simply switched to.
  function retrySource(id) {
    var key = String(id || "")
    var gate = root.sourcesReady()
    if (gate) return gate
    var rec = Model.findSource(root.userState.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
    if (rec.fetchedAt > 0 && key !== root.activeSourceKey) return root.switchSource(key)
    return root.startProbe(key, key, "retry", true)
  }

  // Abort the running probe (UX 1.2 step 8): the helper is terminated, the
  // probe's cache directory is discarded, a pending add or replacement is
  // dropped and sourceProbeFinished carries `cancelled: true`.
  function cancelProbe() {
    if (!root.probing) return root.sourceResult(true, "ok", "", "")
    var key = root.probingKey
    root.probeCancelled = true
    probeWatchdog.stop()
    // D-SRC-69: a probe still held behind a cache job has no process to
    // signal; it ends here, as a cancel, through the same exit path.
    if (root.probeHeld) root.handleProbeExit("")
    else sourceProbeProc.signal(15)
    return root.sourceResult(true, "ok", "", key)
  }

  // The paste path (D9; the only one since D-CLIP-1; Guide.qml pasteInto):
  // the helper's `clipboard` verb as argv (R8), which runs wl-paste with a
  // pipe, reads at most Model.CLIPBOARD_MAX_BYTES and terminates it at the
  // cap, EOF or its own deadline; the reply is one JSON line, parsed by
  // Model.parseClipboardReply, the text back through clipboardText(text),
  // never logged. The helper is the process allowed to hold the bytes
  // briefly and die; this one holds only the bounded reply. The shell
  // process itself never asks Qt. clipboardWatchdog is the outer bound.
  function requestClipboard() {
    if (clipboardProc.running) return false
    clipboardProc.command = Model.clipboardArgv(root.helperPath)
    clipboardProc.running = true
    clipboardWatchdog.restart()
    return true
  }

  // `source` is the cache directory the text was read from (D-PERF-4: the
  // LRU holds one entry per source, so a refresh replaces its own slot).
  function applyChannels(text, source) {
    var t0 = Date.now()
    root.switchReadMs = root.switching ? t0 - root.switchStartedAt : 0
    var lru = root.preparedLru
    var prepared = Model.preparedLruFind(lru, text, source)
    if (!prepared) {
      var parsed = Model.parseChannels(text)
      var channels = parsed.ok ? Model.prepareChannels(parsed.channels) : []
      prepared = { text: text, source: String(source || ""), channels: channels, channelIndex: Model.indexById(channels),
                   chnoIndex: Model.buildChnoIndex(channels), channelsMeta: parsed.meta,
                   // D-ID-3. The scheme-1 -> scheme-2 map of THIS list, computed
                   // once here where the O(n) parse is already paid: it hashes
                   // every URL, tens of milliseconds on 10,000 rows in node, which
                   // no LRU hit inside the 150 ms switch budget can afford. It
                   // reads each row's own id, the one the helper wrote, and folds
                   // no name (D-ID-5). The map depends on the channels alone; what it is
                   // applied to (the state) is decided at apply time below.
                   idRemap: Model.channelIdRemap(channels) }
    }
    if (text !== "" && prepared.channels.length > 0) root.preparedLru = Model.preparedLruNext(lru, prepared, root.preparedLruSize)
    var t1 = Date.now()
    // The LRU entry always holds PLAYLIST order; the display order is derived
    // from it here and again whenever channelOrder changes (5.2), so a flip
    // costs one O(n) gather and no helper run.
    root.preparedActive = prepared
    root.channels = Model.orderChannels(prepared.channels, root.channelOrder, prepared.chnoIndex)
    root.channelIndex = prepared.channelIndex
    root.chnoIndex = prepared.chnoIndex
    root.channelsMeta = prepared.channelsMeta
    root.switchParseMs = t1 - t0
    root.switchAssignMs = Date.now() - t1
    root.adoptIdScheme(prepared.idRemap)
    // A now-playing recovered from the player's stash resolves against the
    // cache the moment it lands (4.5); until then it is name-only.
    root.reconcileNowPlaying()
    // And D-SINK-16's reload needs the same arrival: the helper resolves the id
    // against this cache directory, which the reattach ran before. So does the
    // restart of a player another build launched, which waits for the channel
    // LIST (restart on adoption); reestablishAdopted asks both.
    root.reestablishAdopted()
  }

  // D-ID-3. Move the loaded state onto the id scheme of the channel set that
  // was just applied. The helper does the same to state.json when the active
  // fetch carries --state-dir (D-ID-1), but this service then wrote the state
  // it had loaded BEFORE the helper ran straight back over that file
  // (handlePlaylistExit -> applyPlaylistStatus -> adoptSourceStats ->
  // saveState), on the same fetch, every time observed
  // (QA-HEADLESS-2026-09-21.md on the dev branch, section 1): the rewrite reaches
  // neither memory nor, for longer than its own write, disk. Remapping the
  // in-memory state against every applied list makes this service's writes
  // agree with the helper's, so the order of the two writers stops mattering.
  // Idempotent: scheme 2 is a substitution (Model.channelIdRemap), so after
  // one pass no reference is a key of the map, `moved` is 0 and nothing is
  // written; a list on another scheme-1 vintage (a rotated URL, a probe of a
  // different source) has no key in the state either. Guarded on stateLoaded
  // for the record only: activeCacheDir is "" until the state has loaded, so
  // channels.json cannot be applied before the state is.
  function adoptIdScheme(remap) {
    if (!root.stateLoaded) return
    var moved = Model.remapStateIds(root.userState, remap)
    if (!(moved.moved > 0)) return
    root.userState = moved.state
    root.saveState()
  }

  function applyPlaylistStatus(text) {
    // D-SRC-52: the reason the status being replaced composed, read BEFORE
    // the reassignment (statusReason is a binding over playlistStatus), so a
    // good status clears exactly the sentence a failed one left in lastError
    // and never a play failure's (Model.lastErrorAfterStatus).
    var previousReason = root.statusReason
    root.playlistStatus = Model.parseHelperStatus(text, "playlist")
    root.lastError = Model.lastErrorAfterStatus(root.lastError, previousReason, root.playlistStatus)
    if (root.playlistStatus.ok === true) {
      root.playlistLoadWarnings = Model.statusWarnings(root.playlistStatus)
      root.adoptSourceStats(root.playlistStatus)
    }
  }

  // The history row shows counts without opening N status files: a
  // successful status of the active source (a helper run, or its
  // playlist-status.json loading after a cache swap: the migrated cache, a
  // CLI record fetched by the startup refresh, D-SRC-01) lands on the record
  // when it carries something the record does not have yet.
  function adoptSourceStats(status) {
    var key = root.activeSourceKey
    if (key === "" || !root.stateLoaded) return
    if (!Model.sourceStatsDiffer(Model.findSource(root.userState.sources, key), status)) return
    root.userState = Model.withSourceStats(root.userState, key, status, Math.floor(Date.now() / 1000))
    root.saveState()
  }

  function applyEpgStatus(text) {
    root.setEpgStatus(Model.parseHelperStatus(text, "epg"))
  }

  // The one place epg-status.json becomes state, so the file reload and the
  // helper exit cannot diverge. Warnings follow applyPlaylistStatus exactly
  // (D-LIVE-18): adopted from a successful run only, kept across a failed
  // one because the window still in use is that successful run's.
  function setEpgStatus(status) {
    root.epgStatus = status
    if (status && status.ok === true) root.epgWarnings = Model.statusWarnings(status)
  }

  // epg-now.json -> the store. The text is the FileView's own; the store
  // indexes its lines (one channel a line, R31b) and parses nothing whole. A
  // legacy single-line file -- 0.14.3's helper during an update window
  // (D-REL-9) -- is accepted once through the old whole parse and marked
  // `legacy`; the next `epg --now-only` recompute (epgRecomputeTimer, 5 min)
  // rewrites it in the new shape. The shape alone starts no fetch: a fetch
  // is decided by epgNowStale over the meta, as before.
  function applyEpgNow(text) {
    var store = Model.parseEpgNowStore(text)
    root.epgNow = store
    root.epgMeta = store.meta
    root.epgLoaded = store.ok
  }

  // Status JSON for a helper the watchdog killed (S-05): fixed text, host
  // only, so every sink (guide, notification, console) stays URL-free.
  function helperTimeoutStatus(kind, stale) {
    return JSON.stringify({
      ok: false,
      kind: kind,
      stale: stale,
      sourceHost: kind === "epg" ? root.epgSourceHost : root.sourceHost,
      error: { code: "helper_timeout", message: "helper timed out" }
    })
  }

  // Runs against the active source's own cache directory; nothing runs
  // while it is unknown ("" before startup finished, or unconfigured) or
  // while the configured URL is invalid (D16: the status is synthesized).
  function runPlaylistHelper() {
    // D-SINK-19: `invalidInputBlocks`, not `settingsInvalid`. A typo in the
    // CLI input must not stop the ACTIVE source refreshing; that URL was
    // validated when its record was written.
    if (root.playlistUrl === "" || root.activeCacheDir === "" || root.invalidInputBlocks || playlistProc.running) return
    root.playlistAttempted = true
    root.playlistTimedOut = false
    // D-ID-1. `--state-dir` is what makes the one-time id remap run, and it is
    // REQUIRED for it: the helper touches no state file without it, by design.
    // That is the whole safety property, and it is why only THIS call site
    // carries the flag. The active source's fetch is the one moment we know
    // the user means this list, so it is the one moment the saved references
    // may be rewritten to match it. The source PROBE at sourceProbeProc, in
    // Service.qml, must never pass it -- probing a candidate the user may
    // cancel must not rewrite favourites against a list they never adopted.
    //
    // Without this line the helper still writes scheme-2 ids into channels.json
    // while the migration sits dead, so 4,898 of 5,221 rows change id with
    // nothing repairing the references to them. The fix would CAUSE the loss it
    // exists to prevent, on an ordinary refresh. Two reviewers refused the
    // change for exactly that, and they were right: the lane could not land it
    // because Service.qml was not in its ownership, which was my error and not
    // theirs (parallel rule 1 (dev branch), ownership follows the coupling).
    // R24e (round 14, D-SRC-27): not in the no-write mode -- the remap is a
    // writer of state.json too, and that mode writes nothing to it.
    // D-SINK-8: the URL carries the provider's credentials and goes in the
    // environment, never on argv, where /proc/<pid>/cmdline shows it to every
    // local user for the life of the fetch. Assigned immediately before the
    // run, every run (runHelper): the assignment REPLACES the previous value
    // (measured on Quickshell 0.3.1, see Model.fetchEnvironment), so a stale
    // URL cannot survive a source switch. D-SINK-40: the same one assignment
    // says the URL is the user's, which is what lets its first hop reach a
    // LAN host.
    root.runHelper(playlistProc, Model.playlistFetchArgv(root.helperPath, root.activeCacheDir, Model.fetchStateDir(root.stateDir, root.stateWriteBlocked)),
                   Model.fetchEnvironmentFor(root.playlistUrl, { origin: "user" }))
    playlistWatchdog.restart()
  }

  // `epg` with a URL in the environment fetches (the helper honours its own
  // TTL, decision 5); `epg --now-only` recomputes now/next from the cached
  // window and contacts nobody.
  function runEpgHelper(nowOnly) {
    if (epgProc.running || root.activeCacheDir === "") return
    if (nowOnly) {
      if (!root.epgLoaded) return
      epgProc.nowOnly = true
    } else {
      if (root.epgFetchUrl === "") return
      root.epgAttempted = true
      epgProc.nowOnly = false
    }
    root.epgTimedOut = false
    // D-SINK-8: the EPG URL can carry credentials too, so it travels in the
    // environment like the playlist's. The `--now-only` run is handed {}
    // deliberately rather than left alone: the assignment REPLACES the value
    // the last fetch set (measured, see Model.fetchEnvironment), so the
    // offline recompute runs with no URL in its environment at all.
    // D-SINK-40: and where the URL came from -- the user's own field or the
    // playlist's hint -- with the playlist's host and the class its fetch
    // connected to, which a hint on that same host may share.
    root.runHelper(epgProc, Model.epgFetchArgv(root.helperPath, root.activeCacheDir, nowOnly),
                   Model.fetchEnvironmentFor(nowOnly ? "" : root.epgFetchUrl, root.epgProvenance))
    epgWatchdog.restart()
  }

  function handlePlaylistExit(text) {
    playlistWatchdog.stop()
    var timedOut = root.playlistTimedOut
    root.playlistTimedOut = false
    if (timedOut) {
      // The killed helper wrote no status file for this run; reloading the
      // one on disk would replace this error with the previous result.
      root.applyPlaylistStatus(root.helperTimeoutStatus("playlist", root.cacheLoaded))
    } else {
      root.applyPlaylistStatus(text)
      playlistStatusFile.reload()
    }
    // Deterministic reload; do not rely on inotify surviving the helper's
    // atomic rename (ARCHITECTURE.md, open risk 1).
    channelsFile.reload()
    var manual = root.manualRefresh
    root.manualRefresh = false
    var status = root.playlistStatus
    if (status.ok === true) {
      // The counts landed on the history record in applyPlaylistStatus.
      if (manual) root.notify("playlistRefreshed", { channelCount: status.channelCount, groupCount: status.groupCount })
      root.playlistRefreshed(Number(status.channelCount) || 0, manual)
      // US6: the EPG follows the playlist (the helper restricts programmes
      // to the playlist's ids). Fetch it when none is loaded or its now/next
      // window has expired; a run already in flight is repeated (D-LIVE-02).
      if (root.epgFetchUrl !== "" && (!root.epgLoaded || Model.epgNowStale(root.epgMeta, Math.floor(Date.now() / 1000)))) root.refreshEpg(true)
    } else {
      root.notify("playlistError", { reason: root.statusReason, cachedAt: status.stale === true ? root.lastUpdated : "" })
    }
    if (root.playlistRerun) {
      root.playlistRerun = false
      refreshDebounce.restart()
    }
  }

  function handleEpgExit(text, nowOnly) {
    epgWatchdog.stop()
    var timedOut = root.epgTimedOut
    root.epgTimedOut = false
    var status = Model.parseHelperStatus(timedOut ? root.helperTimeoutStatus("epg", root.epgLoaded) : text, "epg")
    if (!nowOnly) {
      root.setEpgStatus(status)
      root.manualEpgRefresh = false
      if (status.ok !== true) root.notify("epgError", { reason: Model.statusReason(status) })
    } else if (timedOut) {
      console.warn("omarchy-iptv: epg --now-only helper timed out")
    }
    epgFile.reload()
    if (root.epgRerun) {
      root.epgRerun = false
      epgDebounce.restart()
    }
  }

  // D-SINK-19. SET THE ACTIVE SOURCE. The state is the authority and the bar
  // entry is a mirror, which is the whole point of the change: the key goes
  // into the plugin's own 0600 state.json, and the host's shell.json gets a
  // pointer and no credential.
  //
  // The ORDER here is load-bearing in the other direction from D-SINK-18's.
  // The state write comes FIRST and cannot be refused: it is our own file, it
  // is already private, and it is what every binding in this service reads.
  // So a switch completes in this turn whatever the host does, and nothing
  // waits for an echo (rule 9). The entry write that follows can be refused
  // -- there may be no writable bar entry at all -- and that is logged and
  // repaired on the next start, NOT a failed switch, because the fact it
  // mirrors is already recorded (SR25 as amended 2026-10-12). Before this
  // change the entry WAS the fact, so a failed write had to abort the
  // switch; keeping that would now refuse a switch that has already
  // happened. What CAN fail a switch is the state write itself, and that is
  // reported from stateFile's saveFailed ("state_write_failed", R13).
  //
  // `key` is "" to clear the active source (removeSource).
  //
  // R5. The ORDER is Model.pointerWritePlan's and not this function's: state
  // first, and the entry WAITS when the state save is parked behind the
  // start-up dirs (saveState sets stateSavePending; stateInitProc's exit
  // writes the parked state and then settles the held entry). A shell that
  // dies in between leaves the URL still on the entry, which the next start
  // re-adopts -- never a source nobody points at.
  //
  // R13. The entry waits for the state write to LAND on every route, the
  // dirsReady one included: "write-entry-after-saved" holds the key and
  // settleEntryFlush writes it from stateFile's `saved`, or leaves the entry
  // exactly as it is from `saveFailed`. The plan is handed the in-flight
  // count because adoptActive saves and then reaches here through
  // Qt.callLater with the key already in memory -- "nothing moved" with a
  // write still in the air was the round-3 P1 -- and the sticky failure
  // because after a failed write the file is older than memory until a
  // later save lands, and a mirror written then would strip the one copy.
  function persistActive(key) {
    var want = Model.activeKeyText(key)
    var next = Model.withActiveKey(root.userState, want)
    var plan = Model.pointerWritePlan({ keyMoved: next !== root.userState, dirsReady: root.dirsReady,
                                        savePending: root.stateSavePending,
                                        savesInFlight: root.stateSavesInFlight,
                                        saveFailed: root.stateSaveFailed })
    for (var i = 0; i < plan.steps.length; i++) {
      var step = plan.steps[i]
      if (step === "save-state" || step === "defer-state") {
        root.userState = next
        root.saveState()
      } else if (step === "wait-entry") {
        root.pendingEntryKey = want
      } else if (step === "write-entry-after-saved") {
        // Held, then decided at once: with a save in flight the disposition
        // waits for `saved`; with the last save failed and nothing in flight
        // it drops the hold here, because nothing else would wake it.
        root.pendingEntryKey = want
        root.settleEntryFlush()
      } else if (step === "write-entry") {
        return root.persistEntryKey(want)
      }
    }
    // A held entry: accepted, not refused; nothing has been written to the
    // host's file yet. The state write it waits for CAN fail (an unwritable
    // directory, a full disk -- the FileView reports it through saveFailed),
    // and then the entry is not written at all (R11 / R13, settleEntryFlush)
    // and the failure is reported from there, as the state write's own.
    return true
  }

  // The second half of a "wait-entry" plan, run by settleEntryFlush once the
  // parked state save has LANDED (stateFile's `saved`, R11) -- never from
  // stateInitProc's exit directly, which only issues that save. The last key
  // asked for wins: every owned write states every owned key, so one write
  // for the latest value is the same file as one write per value.
  function flushPendingEntry() {
    if (root.pendingEntryKey === null) return
    var key = root.pendingEntryKey
    root.pendingEntryKey = null
    root.persistEntryKey(key)
  }

  // D-SINK-18's gate, kept and now asked about the ENTRY rather than about a
  // pair of URL arguments (Model.entryShieldDecision, which is where the
  // reasoning about whether a KEY is a secret lives). Three answers:
  //
  //   persist  write now -- the file is known private, or this write carries
  //            no URL. Every shipping write is this answer after D-SINK-19,
  //            because the plugin no longer puts a URL in that file; the
  //            other two stay reachable for the write that would, and the
  //            test that proves it feeds a URL-bearing patch through the real
  //            decision rather than grepping for one (rule 14)
  //   refuse   do not write; the file is known not private and the helper
  //            could not make it so. Surfaced exactly like every other
  //            persist failure, through sourcesPersistFailed -- F-UX-7 was
  //            filed for a refusal nobody saw
  //   defer    hold the key and let the shield's exit decide. Only reachable
  //            before the first run exits, because QML cannot block on a
  //            Process; `true` is returned, which is "accepted, not refused",
  //            and NOTHING has been written at that point
  //
  // The shield itself is NOT retired with the URLs, and not for symmetry: a
  // user can still put a credential in that file with their own hand
  // (`omarchy bar set ... playlistUrl <url>`, a route R21 refuses but cannot
  // stop anyone typing; and every 0.13.x entry the migration reads), and the
  // chmod this runs is the only thing that limits who can read it in the
  // window before the plugin adopts or refuses it and writes the entry back
  // without it.
  function persistEntryKey(key) {
    var patch = Model.ownedEntryPatch(root.settings, { sourceKey: Model.activeKeyText(key) })
    var decision = Model.entryShieldDecision(root.hostConfigShield, patch)
    if (decision === Model.CONFIG_REFUSE) {
      root.refuseUnsafePersist()
      // D-SINK-18, found by the review: without this the refusal is PERMANENT
      // until the shell restarts. The state is only ever refreshed after a
      // successful write and at start-up, so a user who reads the message,
      // runs the chmod it names and tries again was refused again, by an
      // answer taken before they fixed anything. Telling someone to do a thing
      // and then ignoring that they did it is worse than not telling them.
      // Re-arming here costs one short-lived process per refusal, and a
      // refusal is already the rare path.
      root.runConfigShield()
      return false
    }
    if (decision === Model.CONFIG_DEFER) {
      root.pendingPersist = { sourceKey: Model.activeKeyText(key) }
      root.runConfigShield()
      return true
    }
    return root.writeActive(key)
  }

  // The refusal, in one place so the deferred path and the immediate path say
  // the same thing. No URL in either message (rule 5): the guide's sentence
  // comes from Model.sourceErrorMessage("config_unsafe") and names the chmod,
  // not `omarchy bar set`, which would write the credential into the user's
  // shell history for ever.
  //
  // D-SINK-19: no shipping write reaches this any more, because the plugin
  // writes no URL into the host's file. It is kept, and kept reachable
  // through Model.entryShieldDecision, for the write that would.
  function refuseUnsafePersist() {
    console.warn("omarchy-iptv: refusing to save a source URL into settings other users can read; see the config shield warning above")
    root.sourcesPersistFailed("config_unsafe")
  }

  // Mirror the active source's KEY into the host entry (D-SINK-19; it was the
  // URL pair under D1 until 0.13.3). Reached only through persistEntryKey,
  // which is what decides whether this write is allowed to happen at all
  // (D-SINK-18), and from onConfigShieldExit for a write that deferred.
  //
  // The write is applied LOCALLY on success and the guide redraws from that;
  // the plugin never waits for the host to echo its own settings back
  // (D-LIVE-20 / D-LIVE-21, see `settings` in Service.qml) -- and since
  // D-SINK-19 it does not depend on this write at all: the active key is
  // already in state.json, which is what every binding here reads. The
  // failure HERE is only a missing host or an entry updateEntryInline cannot
  // rewrite: `false` from a writable entry is its `!dirty` branch
  // (shell.qml:1114), i.e. the host already stores exactly what we asked
  // for, which is success.
  //
  // R13 / SR25 as amended: `announce` false. The key is already in
  // state.json, so a refused mirror loses nothing -- the next start repairs
  // it (Model.adoptActiveSource step 2 rewrites a mirror that disagrees with
  // the state) -- and reporting it as a failed switch sent the user to
  // `omarchy bar set` for a switch that had succeeded. The funnel still logs
  // the refusal.
  function writeActive(key) {
    return root.writeOwnedEntry({ sourceKey: Model.activeKeyText(key) }, "settings change", false)
  }

  // THE ONLY PLACE THIS PLUGIN WRITES THE BAR ENTRY (D-LOGO-2, D-SINK-19).
  //
  // There were two call sites, and D-LOGO-2 is what having two cost: each
  // named the keys IT cared about, so each wrote the other's one-write-behind
  // value back to disk and the two could revert one another. The patch rule
  // fixed that; collapsing the writers is what stops the next key repeating
  // it (rule 15: the search is for the shape, and the shape was "a writer
  // that decides for itself what the entry contains").
  //
  // `Model.ownedEntryPatch` names every owned key at its current effective
  // value, and `Model.entryWith` carries every key we do NOT own through the
  // host's wholesale replace while dropping the retired URL keys -- so any
  // write here also heals an entry left behind by an older build.
  // `announce` is false for the logo toggle, which reports its own failure
  // through its return value: `sourcesPersistFailed` is the SOURCES screen's
  // error channel and raising it for a logo switch would put a source error
  // on screen for something that is not one. (R13 made it false for the key
  // mirror as well; see writeActive.)
  //
  // R16: `patchOnly` true is the PATCH-ONLY write. The caller (setShowLogos,
  // under Model.ownedWriteMode) passes it before the first state load and
  // while a state write is parked, in flight or failed: the overrides then
  // carry `showLogos` alone, so the patch's `sourceKey` is the host's own
  // value (ownedEntryPatch over `settings`), never memory's, and the write
  // does not pay a mirror a failed save left owing (R19d). What it does with
  // the retired URL keys is NOT its own decision any more (R21): every owned
  // write asks Model.retiredInputsToKeep over the LANDED migration marker,
  // which keeps every one until the marker has landed and none after it.
  //
  // `settings`, not `hostSettings`, is load-bearing (D-LOGO-2): `settings`
  // carries our own last write laid over the host's one-write-behind
  // publish, so a key this write does not override goes out at the value we
  // last wrote. Composed from `hostSettings`, the key mirror's write after a
  // logo toggle would carry the PRE-toggle showLogos back to disk on the
  // lagging host. Pinned by the node suite on the dev branch (the R16
  // funnel pin, and the service-order driver, which composes from whichever
  // this line names). Healing the entry is
  // the key mirror's job once the file agrees with memory again (writeActive
  // under R13), and the mirror never passes this.
  function writeOwnedEntry(overrides, what, announce, patchOnly) {
    // R22a: in the no-write mode the entry is left exactly as it is -- it may
    // hold the only copy of an input the unread file could not tell us about.
    if (root.stateWriteBlocked !== "") {
      // R27e's rule-15 sibling (D-SRC-42): the journal says why in the words
      // of the episode -- a block that began after a load is saving stopped.
      console.warn("omarchy-iptv: the bar entry is left as it is (" + (root.stateLoaded ? "saving to state.json has stopped" : "state.json was not loaded") + "); no " + what + " written")
      return false
    }
    if (!root.shell || typeof root.shell.updateEntryInline !== "function"
        || !Model.barEntryWritable(root.shell.barConfig, root.pluginId, Commons.Util.barSections)) {
      console.warn("omarchy-iptv: no writable bar entry for the " + what)
      if (announce !== false) root.sourcesPersistFailed("persist_failed")
      return false
    }
    var patch = Model.ownedEntryPatch(root.settings, overrides)
    patch.id = root.pluginId
    // R21a / R21b, decided here, in the one funnel, for EVERY owned write,
    // heal and patch alike: until the migration marker has LANDED the entry
    // keeps every retired URL key it carries (the URL there may be the only
    // copy of what the migration's state write carries), and from then on
    // every owned write strips them, whatever they are. R17a's held/consumed
    // rule and R20c's landed-state rule for the patch are withdrawn: the
    // only question left is the marker's.
    // D-SRC-64: and a retired key whose value the LANDED state holds as a
    // held migration's parked pair is redundant and stripped too, so the
    // entry carries a URL only until the hold's own state write lands.
    var published = Model.findBarEntry(root.shell.barConfig, root.pluginId, Commons.Util.barSections)
    var keep = Model.retiredInputsToKeep(published, Model.entryMigratedOf(root.landedState), Model.migrationPendingOf(root.landedState))
    var entry = Model.entryWith(published, patch, { keep: keep })
    // R19a (round 9): NO SKIP ON AN ESTIMATE. Every owned write is handed to
    // the host, and updateEntryInline's own answer is the dirty check: `false`
    // from a writable entry is "already stored", which is success. Round 8
    // skipped the hand-over when the plugin's record of its last write said
    // the host stored this entry already, and on the lagging host a publish
    // that went A -> B -> A brought that record back: a logo OFF, the strip
    // of a re-set refused credential and the strip of a re-set EPG input
    // were each skipped while the host would have stored them.
    var stored = root.shell.updateEntryInline(root.pluginId, entry)
    // R18b's first clause, which ALONE settles the cycle: the own-write
    // record is reassigned only when it differs from the one in force
    // (Model.sameOwnWrite). Reassigning an equal record re-evaluates
    // `settings` and fires onSettingsChanged -> reconcile -> this funnel
    // again: round 7's lagging-host loop, a refused playlistUrl beside a
    // pending EPG, at about 3,000 no-op writes a second.
    var record = Model.ownWriteOf(root.hostSettings, Model.ownedEntryPatch(root.settings, overrides))
    if (!Model.sameOwnWrite(root.ownWrite, record)) root.ownWrite = record
    // A heal states every owned key, so it pays any mirror a failed save
    // left owing (R19d).
    if (patchOnly !== true) root.entryMirrorOwed = false
    // Nothing was written (`false`): the file is as it was, and the gate in
    // front of the next write is no staler than before. Re-arming here would
    // spend a process on every hand-over the lagging host answers `false` to.
    if (stored === false) return true
    // D-SINK-18. Re-arm for the NEXT write. The file can be recreated 0644
    // while the shell runs -- omarchy-refresh-config copies the 0644 package
    // default with `cp -f`, which keeps an existing file's mode but gives a
    // file it CREATES the umask's -- and nothing tells a plugin that happened.
    // This run is not what protects the write above (the shield at service
    // start, or the deferred one, did that); it is what makes sure the gate in
    // front of the next one is answering about the file as it is now.
    //
    // THE RESIDUAL, which is not zero and must never be written as zero.
    // D-SINK-19 changed WHOSE credential is at stake here and did not remove
    // the window. The plugin no longer writes a provider URL into this file,
    // so a write that lands on a 0644 file now exposes a source KEY and not a
    // credential -- which is a 32-bit confirmation of a guessed URL rather
    // than the URL (Model.entryShieldDecision states that trade). What is
    // still a credential is the one the USER puts there with
    // `omarchy bar set ... playlistUrl <url>` (refused since R21, and read by
    // the migration before it): it sits in the file from their shell's write
    // until this plugin refuses or adopts it and writes the entry back
    // without it, and the chmod below is the only thing narrowing who can
    // read it in between.
    // `hostConfigShield` answers about the file as of the last shield run, so
    // a recreation that lands after that run and before this write is not
    // seen. Two windows, and they are different sizes:
    //   - the shield's own latency, measured on this machine (4 cores, one
    //     `config shield` per run, n=12 each): 194-213 ms idle, median 197;
    //     271-1076 ms with eight CPU spinners on four cores, median 919. It
    //     is a process start, so it scales with load exactly as D-SINK-9's
    //     shield does. A URL-bearing persist that lands during it defers;
    //     a key-only one does not, because the gate does not fire for a
    //     write that carries no secret -- and after a write this is how long
    //     the gate stays one run behind.
    //   - the gap from that run's exit to the next persist, which is however
    //     long the user goes between source edits and is therefore UNBOUNDED
    //     in time. It is bounded in EVENTS: the answer is at most one shield
    //     run old, and a run follows service start, every persist, every
    //     logo toggle and, since D-SINK-38, every host publish of the file
    //     (onHostSettingsChanged), which is the event a recreation raises.
    // What closes the second window is making every persist wait for its own
    // fresh answer -- the defer machinery already exists, so it is a one-line
    // change from "consult the cached state" to "always defer" -- at the cost
    // of the latency above on each source add, edit and switch. Not taken
    // this round: the brief says shield at start and after each persist, and
    // the trade is the product owner's to make rather than this lane's.
    root.runConfigShield()
    return true
  }

  // D-SINK-18. Start the shield, or remember to start it again. Setting
  // `running = true` on a Process that is already running is not a queue, so
  // a second request while one is in flight is folded into one re-run on exit
  // -- the same shape as playlistRerun / epgRerun in Service.qml.
  function runConfigShield() {
    if (configShieldProc.running) {
      root.configShieldRerun = true
      return
    }
    configShieldProc.running = true
    configShieldWatchdog.restart()   // D-SRC-37 (c)
  }

  // The verb's answer. `hostConfigShield` moves from unknown to private or
  // exposed and never back to unknown: Model.configShieldState fails closed,
  // so a helper that did not run, crashed or printed nothing reads as exposed
  // rather than leaving every future persist deferred for ever -- a run the
  // watchdog stopped (D-SRC-37 (c)) prints nothing and reads as exposed too.
  function onConfigShieldExit(out) {
    configShieldWatchdog.stop()
    root.hostConfigShield = Model.configShieldState(out)
    var pending = root.pendingPersist
    root.pendingPersist = null
    if (pending) {
      if (root.hostConfigShield === Model.CONFIG_SHIELD_PRIVATE) {
        root.writeActive(pending.sourceKey)
      } else {
        // The caller was told `true` and has already moved on, so the one
        // piece of its state that outlives it has to be unwound here:
        // switchSource and the probe commit both open a switch before
        // persisting, and a switch nothing finishes would leave the sources
        // API answering `busy` until switchTimeout fires.
        if (root.switching) root.abortSwitch()
        root.refuseUnsafePersist()
      }
    }
    // Drained through a Timer, not by starting the Process from inside its
    // own exit handler: the same shape as playlistRerun / epgRerun, which
    // restart their debounce rather than re-entering the slot they are in.
    if (root.configShieldRerun) {
      root.configShieldRerun = false
      configShieldDebounce.restart()
    }
  }

  // M2-04. The logo switch, written through the host the same way the source
  // URLs are and applied locally in the same turn (D-LIVE-20 / D-LIVE-21: the
  // host publishes barConfig one write behind, so waiting for the echo means
  // waiting forever).
  //
  // `false` is returned only for a real persist failure. The caller shows the
  // count BEFORE calling this; nothing here asks again.
  function setShowLogos(on) {
    var want = on === true
    if (root.showLogos === want) return true
    // D-LOGO-2, the other direction: this used to name showLogos alone and
    // wrote the one-write-behind playlist and EPG URLs back with it. There is
    // no second updateEntryInline in this file any more -- D-SINK-19 put both
    // writers behind writeOwnedEntry, so this one cannot disagree with the
    // source writer about what the entry contains, and it now REMOVES a URL
    // an older build left in the entry instead of carrying it forward.
    //
    // D-SINK-18: still not gated, and the reason is sharper than it was. The
    // write carries `sourceKey` and `showLogos` (or `showLogos` alone, the
    // patch below) and no URL of the plugin's own. What it does with a URL a
    // user put on the entry is the funnel's (R21): kept until the migration
    // marker has landed, stripped by every write after -- which ended
    // D-SINK-20, the patch-only toggle on the lagging host writing back a URL
    // the plugin's own heal had just stripped, a refused credential included.
    // Do NOT narrow the keep to "while no own-write override is in force":
    // that decides from the host's state, which knows nothing of the disk,
    // and strips the only copy of what a failed migration write carried.
    // What both get is the shield re-arm, which tightens the file and
    // shortens the drift window by one more event. writeOwnedEntry re-arms
    // the shield itself, so there is no second call here: one write, one
    // re-arm.
    //
    // R16 (round-4 review P1, rule 15: this is writeOwnedEntry's SECOND
    // caller, and R13 gated only the first). While a state write is parked,
    // in flight or failed, the file is older than memory and the URL on the
    // entry may be the only copy of a source whose write did not land; this
    // write used to mirror the in-memory key and strip that URL, and the
    // next start found the record nowhere. Model.ownedWriteMode decides from
    // four inputs: "patch" writes `showLogos` alone and leaves `sourceKey` as
    // the host publishes it (ownedEntryPatch takes the key from `settings`);
    // "heal" is today's write. Either way the retired URL keys are the
    // funnel's (R21, above). The mirror itself is written by writeActive
    // once the file agrees with memory, under R13.
    //
    // R16 as amended (round 6): `stateLoaded` is the fourth input. Before
    // stateFile's first load userState is Model.emptyState() and no save
    // flag is raised, so the three flags answered "heal" and the toggle
    // mirrored sourceKey "" and stripped a URL set while the shell was down
    // -- the only copy of it. Nothing on the guide's path waits for the
    // load (openSources needs serviceReady, toggleLogos inSources), so the
    // gate is here, where the write is decided.
    var mode = Model.ownedWriteMode({ blocked: root.stateWriteBlocked,
                                      stateLoaded: root.stateLoaded,
                                      savePending: root.stateSavePending,
                                      savesInFlight: root.stateSavesInFlight,
                                      saveFailed: root.stateSaveFailed })
    if (mode.mode === "none") {
      console.warn("omarchy-iptv: logo setting not written (" + mode.reason + "); the bar entry is left as it is")
      return false
    }
    if (mode.mode === "patch") {
      console.warn("omarchy-iptv: logo setting written alone; the bar entry's source keys are left as they are (" + mode.reason + ")")
      return root.writeOwnedEntry({ showLogos: want }, "logo setting", false, true)
    }
    return root.writeOwnedEntry({ sourceKey: root.activeSourceKey, showLogos: want }, "logo setting", false)
  }

  // Drain the queue. Without this a second mark raised while the first was
  // still being written would sit there for ever -- which is how the kill
  // this replaced came to exist. A root function rather than the handler's
  // body so the harness, which delivers exits by hand, runs the same code
  // (D-SRC-37 (c): and sees the watchdog stopped here).
  function handleFailedExit() {
    failedWatchdog.stop()
    if (root.failedQueue.length === 0) return
    var q = root.failedQueue.slice()
    var next = q.shift()
    root.failedQueue = q
    root.runFailedJob(next)
  }

  function persistFailed(action, id) {
    if (root.activeCacheDir === "" || str(id) === "") return false
    var job = { action: action, id: str(id), dir: root.activeCacheDir }
    if (failedProc.running) {
      // Collapse to the LAST request per id: a clear after a mark is the
      // truth, and replaying both in order would write the mark back.
      var q = root.failedQueue.filter(function (j) { return j.id !== job.id })
      q.push(job)
      root.failedQueue = q
      return true
    }
    root.runFailedJob(job)
    return true
  }

  function runFailedJob(job) {
    root.runHelper(failedProc, Model.failedArgv(root.helperPath, job.action, job.id, job.dir), {})
    failedWatchdog.restart()   // D-SRC-37 (c)
  }

  function applyFailed(text) {
    root.failedRaw = Model.parseFailed(text)
    root.pruneFailed()
  }

  // D-DEAD-1, found live: this used to pass `Model.knownIdSet(root.channels)`
  // straight through. With no channels loaded yet that is `{}` -- an EMPTY
  // object, which is truthy -- so every mark was dropped as "not in the
  // playlist" and the marks silently vanished on every cold start.
  //
  // `prunedFailed` already distinguishes "no channels, cannot tell" from "here
  // are the channels": it takes null for the first. The bug was entirely at
  // this call site, and the unit test passed because it tested the function
  // with null rather than the caller with what the caller actually sends.
  function pruneFailed() {
    var known = root.channels.length > 0 ? Model.knownIdSet(root.channels) : null
    root.failedAt = Model.failedIndex(Model.prunedFailed(root.failedRaw, root.nowSec, known))
  }

  function onLogoLine(line) {
    var name = Model.logoStreamName(line)
    if (name !== "") {
      root.logoPending.push(name)
      logoFlushTimer.restart()
      return
    }
    // The summary: authoritative, and it replaces rather than adds, so a file
    // that went away between the stream and the end is not claimed. An EMPTY
    // summary replaces too: everything swept (D-LOGO-11) means nothing
    // announced, and a length guard here once let a stale set outlive it.
    var names = Model.logoSummaryNames(line)
    if (names !== null) {
      root.logoPending = []
      root.logoHave = Model.logoHaveSet(names, root.logoFetchDir)
      root.logoFetchSeq += 1
    }
    // R30c: a run that stopped at the logo folder's ceiling or at its time
    // limit, or found another run holding the folder, exits 0 and says so
    // on a stderr this Process never reads; this is the one line that
    // reaches the journal. Counted, fixed words, no URL (rule 5).
    var notice = Model.logoSummaryNotice(line)
    if (notice !== "") console.log(notice)
  }

  function flushLogoNames() {
    if (root.logoPending.length === 0) return
    // Tagged with the directory the RUNNING fetch was started for, never the
    // current one: after a source switch those differ, and the merge then
    // answers a set for the old directory, which no slot draws.
    var pending = root.logoPending
    root.logoPending = []
    root.logoHave = Model.logoHaveMerge(root.logoHave, pending, root.logoFetchDir)
    root.logoFetchSeq += 1
  }

  function fetchLogos() {
    // Guarded three times over, because this is the one function in the
    // plugin that contacts hosts the user did not choose: the setting must be
    // on, a source must be active, and a fetch must not already be running
    // FOR THIS DIRECTORY. One running for another directory is stopped and
    // started again on its exit: letting it run on announced the old
    // directory's names for minutes while the rows were the new source's,
    // and the new directory got no sweep of its own. The decision is
    // Model.logoFetchPlan, so a node test can reach it.
    var plan = Model.logoFetchPlan({ showLogos: root.showLogos, wantDir: Model.logoDirFor(root.activeCacheDir),
                                     running: logoFetchProc.running, runningDir: root.logoFetchDir })
    if (plan === "skip") return false
    if (plan === "restart") {
      root.logoFetchAgain = true
      root.logoPending = []
      logoFetchProc.signal(15)
      return false
    }
    // The tag is the LOGOS directory, through the same call `logoDir` is
    // bound through, so the guide's comparison (Model.logoSlot) can match.
    root.logoFetchDir = Model.logoDirFor(root.activeCacheDir)
    root.runHelper(logoFetchProc, Model.logoFetchArgv(root.helperPath, root.activeCacheDir), {})
    return true
  }
