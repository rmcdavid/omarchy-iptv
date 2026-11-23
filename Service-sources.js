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
      Qt.callLater(function() { root.persistActive(key) })
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
