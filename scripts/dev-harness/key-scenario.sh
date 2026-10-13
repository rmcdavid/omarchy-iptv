#!/bin/bash
# scripts/dev-harness/key-scenario.sh -- D-SINK-19, the repair round (lead
# rulings R1-R7), observed on the REAL Service.qml under a nested headless
# compositor: the active source is named by a KEY on the bar entry and the
# URL lives only in the plugin's own state.json.
#
#   key-scenario.sh check-tree              the instrument arm ONLY; run by check.sh
#   key-scenario.sh [live] [--baseline REF] the instrument arm, then the shell arm
#   key-scenario.sh [live] --tree DIR       the same over a PREPARED tree (an export
#                                           with a patch applied: spikes/key-mutations/)
#
# THE FINDING. For the life of the project the host's bar entry carried the
# provider's playlist URL -- credentials and all -- in ~/.config/omarchy/
# shell.json, a file the plugin does not own and whose mode other software
# resets (D-SINK-18 was the containment, the mode). D-SINK-19 removes the
# cause: the entry carries `sourceKey`, an 8-hex pointer; state.json (0600 in
# a 0700 directory) carries `activeKey`; `omarchy bar set ... playlistUrl`
# becomes an INPUT that is adopted and then taken OFF the entry by the
# plugin's own write. The first build (e618fce, integrated as f275bde) was
# reviewed and found not shippable: a URL set while the shell was down was
# DISCARDED and then ERASED from shell.json (review P1), removing the active
# source left a dangling key in the file (harness P1), the migration's only
# copy of a new source could be destroyed between its two writes (P2), and
# the harness's own instrument -- `hostEntry`, which hashes the entry's
# playlistUrl -- went blind on the very tree it had to grade (P2). Lane A
# repaired R1-R5 in Model.js / Service.qml (f84ee50); this file is R6 (the
# instrument) and R7 (the scenarios).
#
# "CLOSED" IS THE WRONG WORD AND THIS FILE NEVER USES IT. The key is fnv1a32
# of the normalized URL: it reveals no URL and it DOES confirm a guessed one,
# a 32-bit check on a guess. A green run here says the exposure went from the
# credential itself to that check, not that it went to zero.
#
# WHAT THIS SCENARIO OBSERVES, AND HOW. Two arms:
#
#   the instrument arm (check-tree, and the preflight of live). R6: the fake
#   shell's `entryKey` reads `sourceKey` first and the `playlistUrl` hash
#   second, NAMED CANDIDATES ONLY. It lives in harness-lib.js, which
#   shell.qml imports and node loads (rule 12), and this arm drives it with
#   the tree's own model: a key beside a differing URL answers the key; a
#   URL alone answers its hash; an entry whose only key-shaped values sit in
#   OTHER settings (`mpvArgs` "deadbeef", a label of 8 hex) answers "" -- the
#   first repair iterated every own value and would have reported the user's
#   mpv argument as the active source; an empty or malformed mirror falls
#   through to the URL. Then three seams: shell.qml's entryKey and hostEntry
#   go through that function, and run.sh stages the file beside the model.
#
#   the shell arm (live). The dev-harness fake shell with the REAL
#   Service.qml and the model under cage (docs/SPIKE-CAGE-HEADLESS.md), IPC
#   only -- no keystroke, no screenshot; the guide is opened once, in L,
#   through `ipc open` and driven through `ipc sourcesKey`, the harness
#   verb that calls the guide's own key handlers -- over a
#   state.json this scenario seeds and real cache directories the real
#   helper writes. Ten shells are started and stopped by their recorded pid,
#   each presenting the bar entry a HOST would hold at that point
#   (`run.sh --playlist` for a URL, `--source-key` for the mirror an earlier
#   shell wrote -- passed only when the entry observed stored CARRIES that
#   name); the fake host models the config in memory, so what survives a
#   stop is what this scenario observed stored and re-seeds. The entry's
#   content is read through `hostEntry` as keys and key NAMES, never values.
#
#   I1  a key beside a differing URL answers the key (sourceKey first)
#   I2  a URL alone answers its hash (the URL hash second)
#   I3  key-shaped values in other settings answer ""   <- named candidates only
#   I4  an empty mirror beside a URL answers the URL's hash
#   I5  a malformed mirror (uppercase) beside a URL answers the URL's hash
#   I6  an absent entry answers "" and does not throw
#   I7  the key-NAMES reader lists names sorted, `id` excluded, no value
#   S1  shell.qml's entryKey is HarnessLib.entryKey over findBarEntry   (seam)
#   S2  hostEntry reads BOTH sides through entryKey                     (seam)
#   S3  run.sh stages harness-lib.js beside the model and proves the copy (seam)
#
#   D1  the first start over the 0.13.5 shape ADOPTS the entry's URL in memory
#       while the state save is parked behind the start-up dirs (control: the
#       rig sees the adoption at all)
#   D2  the adopted key SURVIVES the start-up dirs becoming ready: still in
#       memory and now in the file           <- D-SRC-15, the drop this file found
#   D3  the file went in at 0644; the helper tightened it to 0600 and the
#       reload that chmod fired was IGNORED for the reason R9 names, read
#       off the service's own per-reason counter
#       (stateReloadsByReason['save-parked'] >= 1)  <- R9 observed, not inferred
#       (the round-3 review: the plain ignored TOTAL is satisfied by the
#       own-write echo that follows every start, so the first D3 could not
#       go red for the chmod reload it named; R15 counts by reason)
#   N1  a FRESH install (no state directory, no state.json, no cache): the
#       first start adopts the entry's URL in memory with no file to load
#       (control)
#   N2  the adopted key and its record survive the helper CREATING the file:
#       in memory, in the file, one record, mode 0600
#   N3  ... the stored entry carries sourceKey = that key and no playlistUrl
#   N4  ... configured, the first fetch wrote its cache, 20 channels loaded
#       (N2..N4 are CONTROLS on every tree measured: see STATUS)
#   M1  two-source migration: state.json `activeKey` = the entry URL's key
#   M2  ... and the file still holds the TWO records it went in with, as does
#       `sources()`                     <- R7, SRC-MIG-12 (docs/QA-SOURCES.md)
#   M3  the stored entry carries `sourceKey` = that key and NO playlistUrl /
#       epgUrl                                                       <- the fix
#   M4  the published entry (one write behind, rule 9) still carries the URL:
#       the host shape the instrument has to read through
#   M5  configured, 20 channels from the migrated cache, activeCache is its dir
#   M6  the inactive source's cache and the active one's are untouched: no
#       fetch ran, nothing was moved
#   J1  a start over the MIGRATED shape (key on the entry, no URL, key in the
#       file) makes NO entry write
#   J2  ... and the file's key and count are unchanged (idempotent, SRC-MIG-11)
#   J3  ... configured with the same 20 channels
#   C1  a URL set while the shell was down, beside the surviving mirror: a
#       record for it, origin cli                                 <- R1, review P1
#   C2  ... state.json `activeKey` = ITS key, not the mirror's
#   C3  ... the stored entry carries the NEW key and no URL
#   C4  ... the history kept every record (3)
#   C5  ... configured on it, its first fetch loaded, activeCache is its dir
#   E1  an epgUrl set while the shell was down lands on the ACTIVE record  <- R4
#   E2  ... and is taken off the stored entry by the same write
#   E3  ... and neither the harness log nor any IPC reply carries its credential
#   R1  removing the active source leaves `activeKey` "" IN THE FILE     <- R3
#   R2  ... the stored entry's mirror is "" and still present
#   R3  ... unconfigured, 0 channels, no active cache
#   R4  ... only that cache directory is gone; the other record and its
#       cache survive
#   R5  a start over that leaves it unconfigured with the one record
#       (control: the dangling-key resolution both trees have)
#   O1  the interruptible window was OBSERVED from inside: state loaded, dirs
#       not ready, state save parked, the in-memory state already naming the
#       NEW source (control: the rig reached the window at all)
#   O2  inside it the entry write WAITS: the stored entry still carries the
#       URL and the service holds the key for later        <- R5, review P2
#   O3  inside it state.json on disk is untouched (control)
#   O4  after a SIGKILL in the window state.json is still the file the shell
#       started from (control: nothing was written by either tree)
#   O5  the next start RECOVERS: the new source is in the file, active,
#       configured, fetched                                 <- R5, the loss
#   O6  ... and the migration then completes: key on the entry, URL off it
#   W1  the D-SRC-15 SIBLING (SRC-MIG-16): an IPC switch
#       INSIDE the start-up window, over a 0644 file, so the helper's chmod
#       reload lands AFTER the call carrying the pre-switch text: the switch
#       is accepted, in memory, held, the file still naming A (control)
#   W2  after the dirs are ready the switch SURVIVED that reload: C in
#       memory and in the file, mode 600                    <- R9, the sibling
#   W3  the reload was counted for the reason R9 names (save-parked) and the
#       mirror followed the LANDED save: stored C, no URL   <- R11 at the sink
#   W4  both caches survive; configured on C's 7 channels (control)
#   W5  the same window, a REMOVE of the active source: accepted, pointer
#       cleared in memory and held, the file still naming A (control)
#   W6  after the dirs are ready the removal survived the reload: the file's
#       pointer empty with one record, the mirror empty, A's cache gone, C's
#       kept, unconfigured, the reload counted save-parked  <- R9 / R3
#   F1  the state write FAILS with the dirs ready (round-3 review P1, R13):
#       configured on A, nothing in flight, no failure recorded (control)
#   F2  the state directory made unwritable, a CLI playlistUrl is adopted in
#       memory and its state write FAILED: failure recorded, nothing in
#       flight, nothing held                                (control: the
#       rig made the write fail at all)
#   F3  the stored entry was NOT rewritten: the URL is still on it, the only
#       copy of the input, beside the OLD mirror           <- R13, the loss
#   F4  state.json on disk untouched; the failure logged with no URL;
#       sourcesPersistFailed(state_write_failed) signalled ONCE
#   F5  a switch on the failed disk is accepted (the write is issued), lands
#       in memory only, holds no mirror, the entry left as it is, no second
#       signal for the same episode (counted from the switch's OWN mark)
#                                                          <- R13 / SR25 amended
#   L1  the LOGO TOGGLE on the same failed disk (Guide `g` + confirm in
#       Sources, through `ipc sourcesKey`): logos on, and the stored entry
#       STILL carries the URL beside the mirror the FILE holds -- not the
#       in-memory key -- with `showLogos` on it     <- R16, round-4 review P1
#   L2  that was ONE entry write, patched alone: its key list keeps
#       playlistUrl (set: the only copy) and sourceKey beside showLogos, the
#       service logged it as written alone (save-failed), no new signal,
#       state.json untouched. Until round 10 it asked for epgUrl too: R16
#       kept every retired key, the seed's EMPTY one included; R20c keeps
#       only a valid input the landed state does not hold, and an empty
#       value is no input (measured: `keys:0` on lane-key-z1's first live
#       run with the old want, every other L and F check green)
#   F6  the next start RE-ADOPTS the URL the failed write left on the entry,
#       over the entry as the host STORED it after L: its record in the
#       file, active, fetched, URL off the entry                  <- R1
#   F7  the history holds the three records and nothing carries B's path
#   U1  two saved sources, NONE active, an epgUrl set while the shell was
#       down: loaded on the lagging host, the EPG HELD in the state file and
#       off the stored entry, on no record (R19b; R12's on-entry state
#       until round 9)
#   U2  the logo toggle HEALS (nothing outstanding) and the held EPG is
#       untouched: one write, not written alone, nothing kept on the entry,
#       still held                      <- R17a, the round-6 data-loss P1
#   U3  a switch to A lands the EPG on A's record in the file, and only the
#       mirror's write after it strips the entry   <- R17b
#   U4  a restart over the entry as stored stands on A with the EPG on A
#   U5  the same rig on the ECHOING fake host (run.sh --host echo): the lever
#       took, the R12 state holds on both sides (control)
#   U6  a switch with NO toggle lands the EPG on A before the mirror strips
#       it, and the echoing host publishes the stripped entry at once
#                                       <- R17b, the echo half of the P1
#   U7  a restart over that (echoing host) stands on A with the EPG on A
#   K1  the lagging host, a REFUSED playlistUrl beside a pending EPG (no
#       source active): the shell SETTLES -- at most 2 entry writes and 50
#       CPU ticks in a 5 s window -- the refused value off the stored entry,
#       the EPG held in the state file (R19b)
#                                         <- R18b, the round-7 data-loss P1-B
#   K2  the same entry on the ECHOING host settles (control)
#   K3  the echoing host with the refused value WRAPPED IN WHITESPACE
#       settles and drops it                          <- R18a, P1-A's loop
#   Z1  a whitespace-wrapped CLI playlist adopted, then removed: the stored
#       entry carries no playlistUrl                  <- R18a, P1-A
#   Z2  the restart over that does not resurrect the removed source
#   Z3  a whitespace-wrapped REFUSED credential beside a working source
#       leaves the stored entry; the source stays active   <- R18a, P1-A
#   A1  an in-app add (harness addSource) with no form EPG while a CLI
#       epgUrl is pending: the new record holds it, the entry drops it
#                                          <- R17b's probe commit, live
#   A2  the same add with the form's OWN guide URL, submitted after the CLI
#       value was held: the form (later) wins, the held one is cleared and
#       logged by setting and key                  <- R18d, R19c since round 9
#   Y1  on the lagging host: in-app logo OFF, CLI showLogos true again (a
#       publish A -> B -> A), in-app OFF again -- each OFF takes and is
#       handed to the host               <- R19a, the round-8 lenses' P1-A
#   Y4  two in-app toggles in a row (ON, then OFF, nothing between): the
#       second takes and is handed to the host too
#                           <- R20d, the round-9 lens's mutant S1b, live
#   Y2  the same refused credential set three times beside the active
#       source is off the stored entry after EVERY set          <- R19a
#   Y3  the same epgUrl set twice, then the guide URL edited in the app:
#       off the entry each time, and the edit stands after a restart <- R19a
#   Q1  the add form submitted, THEN a CLI epgUrl set while its probe runs
#       (a slow local server): the CLI value (later) stands  <- R19c, P1-B
#   Q2  the CLI value held, THEN the add form submitted: the form stands
#       (control: the order R18d already got right)
#   V1  the CLI value held, then A's guide URL edited in the app, then the
#       switch to A: the edit (later) stands     <- R19c, the lens's P2
#   H1  an EPG input whose adoption's state write FAILED stays on the entry;
#       a later in-app edit's save LANDS and the owed mirror takes it off,
#       so the restart stands on the edit             <- R19d, D-SRC-18
#   P1  no labelled harness-log line carries a URL or a fixture path
#   P2  no credential token anywhere in the harness log
#   T1  the shell, the compositor and the nested socket are gone (by pid)
#
# Every segment seeds its OWN state.json, caches and entry and starts a fresh
# shell, so a red in one is attributable to one ruling and never to the
# segment before it (the first version chained them and one red cascaded
# into seventeen).
#
# STATUS. The drop this file found on 2026-10-11 against lane-key-r1
# (f84ee50) is D-SRC-15 on the board, and lane-key-s1 (3d2d8e7, lead
# rulings R9-R12) closes it: a reload never replaces in-memory state that
# is newer than the file (Model.reloadDisposition, asked first in
# applyUserState), the helper leaves a 0600 file alone (R10), and the entry
# mirror waits for the parked save to LAND (R11). The mechanism as it was
# found, attributed by polling `pointerState` at 50 ms through a start and
# then repeating it with a helper whose `state init` does nothing: the
# service adopts the entry's URL at the state load and PARKS the save
# (dirsReady false); the helper's start-up `state init` then ran
# `os.chmod(path, 0o600)` on the EXISTING state.json; that chmod is an
# inotify IN_ATTRIB on the file the service's FileView watches, mode
# changed or not (lane A's probe), so `onFileChanged: reload()` fired and
# applyUserState was handed the PRE-ADOPTION text; Model.stateOnLoad keeps
# only the session record of the in-memory state, so the adopted key --
# and a newly adopted RECORD, the review's P1 shape again -- was dropped;
# stateInitProc's exit then wrote the parked save, now the key-less state,
# and flushed the entry mirror, which stripped the URL and wrote
# `sourceKey ""`. Measured: +1489 ms adopted, parked, key held; +1909 ms
# dirsReady, memory "", file "", entry `sourceKey ""` with no URL; with
# `state init` skipped the key survived. The shape pre-exists D-SINK-19
# (the review's P2 said the URL on the entry "was doing work here too" as
# an accidental backup); D-SINK-19 turned a harmless re-adoption on the
# next start into the loss of the user's active source on the first start
# after the upgrade.
#
# The forward run seeds D's file at 0644 ON PURPOSE: seeded 0600, R10 means
# the helper never chmods, the reload never fires, and D2 is green with R9
# never deciding anything (lane A proved R9 alone by reverting R10 in a
# scratch copy; this file makes the ordinary run do it). D3 then reads the
# decision off `stateReloadsByReason['save-parked']`, which `pointerState`
# reports beside the plain ignored total, the in-flight count, the sticky
# save failure and the helper's exit (numbers and booleans; OMITTED on a
# tree without them since round 6, so they read NOFIELD there -- they used
# to be reported as null, which is how a `held` want of NULL came to be
# green on a tree with no pendingEntryKey; HarnessLib.pointerStateOf). BY
# REASON, because the round-3 review showed the total cannot go red for
# the mechanism D3 names: the service's own atomic write of the parked
# save raises a reload that is ignored as `own-write` after EVERY D
# start, so `stateReloadsIgnored >= 1` held whether or not the chmod
# reload was applied (a Service.qml mutated to apply every reload but
# its own write read `PASS D3` beside `FAIL D2`). The per-reason number is
# the decision itself: a tree that applies the chmod reload counts it as
# `file-newer` and never as `save-parked`, which is the mutation D3 was
# seen red against (Model.reloadDisposition's save-parked clause deleted:
# D2, D3, W2, W3 and W6 red, the rest of the run green). What the counter
# does NOT see is a Service.qml that counts the reason and applies the
# reload anyway; that is the `return` R14 pins in tests/Model.test.js, and
# D2 beside D3 is the sink.
#
# W AND F, ROUND 4. The round-3 live lens measured two things in scratch
# that no segment observed. W lifts its D-SRC-15 SIBLING driver: an IPC
# switch or remove made INSIDE the start-up window (cacheReady before
# dirsReady, the O staging) over a 0644 file, so the helper's chmod reload
# arrives AFTER the call carrying the pre-call text -- the fixture's named
# case (tests/fixtures/active-key.json), now joined to a live observation
# (rule 13). F is the round-3 P1 at the sink: with the dirs READY the first
# version of persistActive wrote the entry straight after setText and
# before the FileView reported, so a state write that failed (an unwritable
# ~/.local/state, a full disk) stripped the URL from the host's entry while
# the record existed in memory only -- the input lost with no copy anywhere.
# R13 makes the entry wait for the write to LAND on every route; F makes
# the state directory 0500 under a running shell, sets a CLI playlistUrl
# (the adoption route) and then switches (the switch route), and asserts
# the entry still carries the URL, the file is untouched, the failure is
# signalled once as `state_write_failed`, and the next start re-adopts
# what the failed write left behind. The directory is 0700 again before the
# shell is stopped; it is this scenario's own scratch, never the user's --
# and cleanup() puts it back on EVERY exit, because a TERM inside F used to
# leave it 0500 and an `rm -rf` of the harness directory then failed on
# state.json (round-4 live review).
#
# L, ROUND 5 (R16). The round-4 data-loss lens found rule 15's shape in
# R13 itself: Service.writeOwnedEntry has TWO callers, and R13 gated one.
# The logo toggle (Service.setShowLogos, reached from the guide's Sources
# view by `g` and the consent's confirm) wrote `{ sourceKey: <memory>,
# showLogos }` and Model.entryWith strips the retired URL keys on every
# owned write -- so in exactly the state F leaves (file older than memory,
# the URL on the entry the only copy) one toggle moved the mirror to a key
# the file lacks and stripped the URL; the next start found the record
# nowhere. Measured live on lane-key-t2 by the lens (its driver is what L
# lifts). R16: while a state write is parked, in flight or failed the
# toggle patches `showLogos` ALONE and leaves `sourceKey`, `playlistUrl`
# and `epgUrl` as the host publishes them (Model.ownedWriteMode decides,
# and since round 6 it patches before the first state load too; on the
# lagging host the publish is one write behind, D-SINK-20); the
# heal is writeActive's, under R13, once the file agrees with memory. L
# runs inside F, after the switch and before the restart, and F6 then
# restarts over the entry as the host stored it AFTER the toggle (the key
# observed stored, as O does it), so on a tree without R16 F6 and F7 go
# red with L1 and L2.
#
# K, Z AND A, ROUND 8 (R18). The round-7 data-loss lens found two P1s
# live, each in its own driver, and this file had no refused value and no
# whitespace-wrapped value anywhere: K lifts loop-child.sh (a refused
# playlistUrl beside an EPG R12 holds: the lagging host looped at about
# 3,000 entry writes a second, measured as writes and CPU ticks of the
# shell's own pid over a 5 s window), Z lifts resurrect-child.sh and
# MODE=badws (a whitespace-wrapped input never counted as consumed: a
# removed source came back, a refused credential stayed in shell.json), and
# A drives the in-app add's probe commit through the harness addSource
# verb, which the round-7 live lens found no segment reaching. The input
# values are never printed: key names from hostEntry, the record's EPG
# compared inside python, the window's numbers on one stderr line.
#
# Y, Q, V AND H, ROUND 9 (R19). Both round-8 lenses found R18b's write
# skip coming back after a publish A -> B -> A on the lagging host, live,
# and the data-loss lens found R18d dropping a CLI epgUrl set AFTER the add
# form was submitted, and the same principle on the edit form. Y lifts
# aba-child.sh (T=logo, bad, epg), Q lifts race-child.sh (both orders, a
# slow local listener holding the probe open), V lifts T=edit, and H is the
# board's D-SRC-18 at the sink. R19a: no skip on an estimate -- every owned
# write is handed to the host and updateEntryInline's own answer is the
# dirty check. R19b: a guide URL no record can take is HELD in state.json
# (pendingEpg { url, seenAt }) and taken off the entry, which is why U, K
# and A read `held:` from the file where they read the entry before.
# R19c: the latest explicit input wins, by time (seenAt against the
# record's epgSetAt). R19d: a mirror a failed save withheld is paid by the
# next save that lands.
#
# U, ROUND 7 (R17). The round-6 data-loss lens found an input no oracle
# had covered for five rounds, because every matrix checked the PLAYLIST
# input alone: an epgUrl R12 leaves on the entry on purpose while no
# source is active. Nothing recorded that state, so with the state loaded
# and nothing outstanding Model.ownedWriteMode answers `heal` and
# Model.entryWith dropped every retired key -- through the logo toggle on
# the lagging host (the lens observed it LOST with the toggle, KEPT
# without, on lane-key-v2, with its own epg-child.sh, which U lifts), and
# through the switch alone on the echoing host, where the mirror's heal
# stripped the entry and the host published the stripped entry at once, so
# no reconcile saw the input beside an active record (the lens measured
# that half in its simulator only; U5..U7 observe it, on the echo lever
# run.sh --host gives the fake host since this round, D-HOST-4). R17a: an
# owned write strips a retired input only when it is CONSUMED -- a record
# holds it, or the service already adopted or refused that value
# (Model.retiredInputsToKeep, which the funnel hands entryWith on every
# write). R17b: switchSource and the probe commit adopt a pending EPG onto
# the newly active record in the same turn (Model.adoptPendingEpg), before
# the save and before the mirror. The entry's values are never read here:
# key names from hostEntry, the record's EPG compared inside python and
# printed as the keys that hold it; and since the harness seed always
# carries an `epgUrl` NAME (empty when unset), the restart checks read the
# file and the service, never that name.
#
# N, THE CREATED-FILE SHAPE, IS A CONTROL, AND THAT IS A MEASUREMENT. The
# round-2 live lens wrote that the drop is "present in the no-state.json
# shape too", from the mechanism and not from a run. It is not: over a
# fresh install (no state directory, no file, no cache) the helper CREATES
# state.json under the parked adoption and the service's FileView, loaded
# over a missing path, never sees the creation -- `stateReloadsIgnored`
# reads 0 across the whole fresh start on lane-key-s2, and N2..N4 are
# GREEN on `--baseline lane-key-r2`, the tree that drops D2. So the fresh
# install was never exposed, and N stays because the fresh install is the
# one start every new user makes and nothing else observes it.
#
# RULE 11, THE RED RUN. `--baseline lane-key-r2` exports the round-2 tree
# (lane-key-r1's code under this harness's predecessor, the tree D-SRC-15
# was found on) and runs its model, Service.qml and helper through the
# same rig, with this tree's harness. Measured 2026-10-12 on this harness
# (round 5: L added, F5 from its own mark, the NULL sentinel; round 4: W
# and F added, D3 by reason), recipe in the footer the run prints; the
# counts of 2026-10-11 (49 / 0 forward, 36 / 13 on r2) were the harness
# before W, F and the by-reason D3 existed, and the round-4 counts (62 / 0,
# 54 / 8, 38 / 24, 39 / 23) the harness before L. Round 7 (U added) was
# measured on lane-key-w1 (2ccbb74) under the scenario's own nested cage,
# transcripts key-20261012-130320 and -130450:
#   lane-key-w1 (round 7's code):                 71 passed,  0 failed
#   --baseline lane-key-v2 (round 6's code):      66 passed,  5 failed
#       U2, U3, U4, U6, U7   <- R17: the toggle's heal stripped the EPG
#       (U2 `epgUrl:no kept:0`), so the switch had nothing to land (U3
#       `on:none`); on the echoing host the switch alone lost it (U6
#       `on:none`); both restarts stand on A with no EPG (U4, U7). U1 and
#       U5 are the controls, and nothing outside U moved.
# Round 8 (K, Z, A added) was measured on lane-key-x1 (7a429cd) under the
# scenario's own nested cage, transcripts key-20261012-144939 and -145158:
#   lane-key-x1 (round 8's code):                 79 passed,  0 failed
#   --baseline lane-key-w2 (round 7's code):      73 passed,  6 failed
#       K1 (LOOP: 17,414 entry writes and 596 CPU ticks in the 5 s window),
#       K3 (LOOP on the echoing host, 19,943 / 637, the credential kept),
#       Z1, Z2 (the removed source back and active), Z3 (the refused
#       credential kept), A2 (the stale CLI EPG on the record, the form's
#       on none). K2 and A1 are the controls, and nothing outside K, Z and
#       A moved. Through --tree, one decision removed from 7a429cd: the
#       keep decision's raw snapshot compare (P1-A) 75 / 4 -- K3, Z1, Z2,
#       Z3, with K3 reading `settled` and holding the credential, because
#       R18b alone stops the loop; R18b's two decisions removed 78 / 1 -- K1 only
#       (14,256 / 601); the probe commit not handing the form's EPG 78 / 1
#       -- A2.
# Round 9 (Y, Q, V, H added; U, K and A read the held guide URL) was
# measured on lane-key-y1 (42850dc) under the scenario's own nested cage,
# transcripts key-20261012-181012 and -181343:
#   lane-key-y1 (round 9's code):                 86 passed,  0 failed
#   --baseline lane-key-y0 (round 8's code):      74 passed, 12 failed
#       U1, U2, U5, K1, K2, K3 (the guide URL waits on the ENTRY, not held
#       in the state: R19b), Y1 (the second in-app OFF skipped: `off2:
#       true/0`), Y2 (the third re-set refused credential stays: `no no
#       yes`), Y3 (the re-set EPG stays on the entry and the restart puts
#       it back over the edit: `E/yes ... /E`) -- R19a, the A -> B -> A
#       skip; Q1 (the CLI value set during the probe on no record, the
#       earlier form's on it: `on:F`), V1 (the earlier held value over the
#       edit: `on:E`) -- R19c; H1 (D-SRC-18: `landed:false/yes ... /E`) --
#       R19d. A1, A2 and Q2 are its controls (the form submitted AFTER the
#       CLI value won there too), and nothing outside U, K, Y, Q, V and H
#       moved. The two patches below, through --tree over 42850dc: 80 / 6
#       and 81 / 5, the same letters as before.
# The rows below were measured before Y, Q, V and H existed; the two
# patch rows further down are the 64-check harness's.
# The rows below were measured before U existed (63 lettered checks):
#   lane-key-u2 (lane-key-u1's code):             64 passed,  0 failed
#   --baseline lane-key-t2 (round 4's code):      60 passed,  4 failed
#       L1, L2, F6, F7   <- R16: the logo toggle after the failed write
#   --baseline lane-key-s2 (round 3's code):      54 passed, 10 failed
#       D3, W3, W6, F3, F4, F5, L1, L2, F6, F7
#   --baseline lane-key-r2 (the D-SRC-15 tree):   38 passed, 26 failed
#       D2, D3, M1, M3, M5, C1..C5, E1, O5, O6, W2, W3, W4, W6, F1..F7, L1, L2
#   --baseline f275bde (the first build):         39 passed, 25 failed
#       D3, C1..C5, E1, O2, O5, O6, W1..W6, F1..F7, L1, L2
# On lane-key-t2 the four reds are L's: the toggle wrote the in-memory
# key and stripped the URL (L1 `stored:<C> playlistUrl:no`, L2 `keys:0
# alone:0`), and F6/F7 then restart over the entry as that tree stored it
# -- the mirror moved to a key the file lacks, no URL -- and find no record
# for B (F6 `record:0`, F7 `records:2`): the lens's live finding, now a
# segment. On lane-key-s2 the reds are round 4's: D3 (NOFIELD: no per-reason
# counter there), F3 (the stored entry read with NO playlistUrl and the
# mirror moved -- the loss at the sink), F4 (no state_write_failed signal),
# F6 (no record for B after the restart: the input is gone), F7 (two
# records, not three) and F5 (the mirror moved to C and nothing was
# signalled); W2, W4 and W5 are green there, because lane-key-s2 carries
# R9-R11 and the sibling holds under them (the lens measured the same),
# and W3 and W6 read NOFIELD for the per-reason counter they also assert.
# On lane-key-r2 D2 is the drop at the sink ("got [dirs:true memory:
# file:]"), D3 reads NOFIELD (no counter to read), W2, W3, W4 and W6 are
# the sibling dropping the same way (W2 "memory:A file:A" after a switch to
# C; W6 the pointer back on A with both records and the cache kept), F
# follows s2's reds with F1 and F2 reading NOFIELD for fields r2 lacks,
# and M1, M3, M5,
# C1..C5, E1, O5 and O6 are everything that rests on an adoption made at
# START-UP. E1 was red on EVERY tree until round 3 because its own `want`
# was wrong (`kind=x` where Model.maskUrl masks every query value);
# corrected, it is a discriminator (the baseline reads "file:other"). D1,
# N1..N4, M2, M4, M6, J1..J3, E2, E3, R1..R5, O1, O3, O4, P1, P2, T1 and
# every I and S check pass on every tree: controls (W1 and W5 need the
# held key R5 added, so they are instrument absences on f275bde only). R1 and
# R2 are controls live because Service.removeSource reaches
# persistActive("") on either tree; lane A's R3 (Model.removeSource
# clearing the key in what IT returns) is reached by the node and python
# fixtures. On f275bde (the first build) O2 is still the one check red
# there and green on every later tree (the entry rewritten while the save
# was parked, the review's P2); D2, M1, M3, M5 pass there by accident, and
# the rest of its reds are instrument absences (no held key, no counters,
# no in-flight count) and the start-up-adoption reds C1..C5 / O5 / O6 it
# shares with r2. The header used to cite 35 / 9 for it, the count of a
# harness two versions older; the number above is this one's.
# TWO MUTATIONS, both on this tree's code with this harness, each a patch
# file under spikes/key-mutations/ that the reader applies to an EXPORT of
# the tree (never the working tree) and runs through `--tree <export>`;
# the recipe is in that directory's README, and scripts/qa-lib-test.sh
# proves both patches still apply to this tree. Round 4 kept them as
# throwaway branches cited through --baseline; the lead deleted those.
#   d3-save-parked.patch: Model.reloadDisposition's save-parked clause
#   deleted (a reload over a parked save applied as file-newer):
#                                                 58 passed,  6 failed
#       D2, D3, W2, W3, W4, W6 -- the counter reads {"file-newer": 1,
#       "first-load": 1, "own-write": 1} and `save-parked` is absent
#   r14-no-return.patch: Service.applyUserState's R14 `return` deleted
#   (counted, then applied anyway):               59 passed,  5 failed
#       D2, W2, W3, W4, W6 -- and D3 GREEN, the counter reading
#       {"save-parked": 1, ...} beside the loss at the sink. That is the
#       honest limit of a counter: it observes the DECISION, and the
#       `return` is pinned structurally in tests/Model.test.js (R14); D2
#       and W2 beside it observe the sink. The instrument's own red is against the two
# instruments before it, not a tree: f275bde's entryKey hashed the URL
# alone (I1 reads the URL's key where the mirror names another source) and
# the first repair iterated every entry value (I3 reads "cafebabe"). Both
# were driven through this arm's node probe with their bodies in place of
# harness-lib.js's, one red of seven each; scripts/qa-lib-test.sh drives
# the same three clauses on every commit.
#
# MODES. `check-tree` (what scripts/check.sh runs on every commit: no
# transcript, no display, node over the tree's model, under 2 s) and
# `live` (the default: a transcript, both arms, and the --baseline / --tree
# levers; about 120 s). `--tree DIR` is --baseline pointed at a directory
# that already exists -- an export with a patch from spikes/key-mutations/
# applied -- and is never removed by this scenario. check-tree needs node
# and python3; live also needs cage and
# quickshell. A machine without one of them exits 77 with the reason, never
# 0, and those checks run BEFORE anything else so the reason is the first
# line out even with an empty PATH. KEY_CAGE_BIN overrides the cage binary,
# so the 77 path can be driven on a machine that has it.
#
# INTERRUPTED. INT and TERM are trapped into an exit, so cleanup() runs
# (bash runs no EXIT trap for a signal that kills it while it waits on a
# foreground child), and cleanup() records the shell's children by PARENT
# pid while the shell is alive before it reaps, because `reap` does not
# take a Process child with the shell. Measured 2026-10-11 with a TERM sent
# to the scenario's own pid inside THREE windows: the O window with the
# slow helper asleep in `state init` (KEY_SLOW_MS=30000; the sleeping
# child was listed under the shell before the TERM and gone 1 s after),
# the D window with the real helper mid-start-up (`cache` and `config
# shield` children listed, gone after), and the N window. Each left no
# shell, no helper child, no cage, no nested socket and no work directory.
# The round-2 live lens found the first version's O window stranding the
# slow helper for the rest of its sleep: only the segment's own recording,
# taken just before its deliberate SIGKILL, fed ORPHANS. The recipe is in
# scripts/qa-lib-test.sh's trap list.
# One window is not covered by `reap`, and the round-3 review corrected
# what this file's author had said about it: a TERM landing in the ~100 ms
# between `h --detach` returning and qs.pid being read. In every segment
# after the first, SHELL_STARTED is 0 at that instant (stop_shell cleared
# it), so cleanup() skips `reap` and SHELL_PID still names the PREVIOUS
# segment's dead shell -- not an empty value, and not one `reap` handles.
# The freshly detached quickshell dies anyway, and the mechanism is the
# nested display: cleanup() TERMs cage's child and cage, and a Wayland
# client whose compositor goes away exits. Measured by the review with a
# marker and a 3 s sleep inserted in that gap and a TERM sent on the
# marker: the new shell was alive at the TERM and gone 0.2 s after, with
# cage, the work directory and the nested socket. No residue, so the
# window stays as it is; what this paragraph corrects is the claim, not
# the behaviour. A helper child cannot exist before the shell does.
#
# Holds no display: everything this starts lives on the nested display cage
# creates, read from cage's own child and refused if it names the caller's
# session. It starts no quickshell on the user's session, sends no keystroke
# anywhere, reads nothing from the live install and touches nothing under
# ~/.config, ~/.cache or ~/.local/state (the harness points every XDG
# directory into its own scratch tree, which this scenario keeps apart from
# the shared harness directory so a display lane's running harness is never
# reaped by this one).
set -uo pipefail
SKIP=77
CAGE_BIN=${KEY_CAGE_BIN:-cage}
# How long the staged slow helper holds `state init` (ms): the width of the
# interruptible window O1-O4 look into. Under the service's own start-up it
# is otherwise ~100 ms wide. 8 s leaves the polling loop (bounded at 6 s)
# room to observe it and stop the shell inside it on a loaded machine.
SLOW_MS=${KEY_SLOW_MS:-8000}
MODE=${1:-}
case $MODE in
  check-tree) shift ;;
  live|"")
    MODE=live; (( $# )) && shift ;;
  -*) MODE=live ;;
  *) echo "usage: key-scenario.sh [check-tree|live] [--baseline <ref>]" >&2; exit 2 ;;
esac
BASELINE=""; TREE=""
while (( $# )); do
  case $1 in
    --baseline)
      [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--baseline needs a git ref, and got '${2:-}'" >&2; exit 2; }
      BASELINE=$2; shift ;;
    --tree)
      [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--tree needs a directory, and got '${2:-}'" >&2; exit 2; }
      TREE=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

# ---- refusals, above the transcript and above every external command, as
# logo- and clip-scenario.sh do them: builtins only, so an empty PATH reaches
# the SKIP line and nothing else.
for tool in node python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP key-scenario: $tool is not on PATH" >&2; exit $SKIP; }
done
if [[ $MODE == live ]]; then
  for tool in "$CAGE_BIN" quickshell qs; do
    command -v "$tool" >/dev/null 2>&1 || { echo "SKIP key-scenario: $tool is not on PATH" >&2; exit $SKIP; }
  done
fi
HERE=${BASH_SOURCE[0]%/*}
[[ $HERE == "${BASH_SOURCE[0]}" ]] && HERE=.
HERE=$(cd "$HERE" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
[[ -f $HERE/harness-lib.js ]] || { echo "$HERE/harness-lib.js is missing" >&2; exit 2; }
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
LIVE_DISPLAY=${WAYLAND_DISPLAY:-wayland-1}
# This scenario's OWN harness directory, never the shared default.
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-key}
export OMARCHY_IPTV_HARNESS_DIR=$SCRATCH
PLUGIN_ROOT=$ROOT
EXPORT_DIR=""
TREE_LINE="== tree $ROOT ($(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git))"
# The levers' refusals sit ABOVE the transcript (rewind-scenario.sh's shape,
# pinned by scripts/qa-lib-test.sh): a mistyped lever is one line on stderr
# and no file. --tree is a directory the caller prepared and keeps.
[[ -n $BASELINE && -n $TREE ]] && { echo "--baseline and --tree are the same lever; pass one" >&2; exit 2; }
if [[ -n $TREE ]]; then
  PLUGIN_ROOT=$(cd "$TREE" 2>/dev/null && pwd) || { echo "--tree $TREE is not a directory I can enter" >&2; exit 2; }
  # The model is whatever qa_model_files answers (D-REL-5: Model.mjs and its
  # parts, or a pre-split tree's Model.js), never a file name kept here.
  [[ -f $PLUGIN_ROOT/Service.qml && -f $PLUGIN_ROOT/bin/omarchy-iptv ]] && qa_model_files "$PLUGIN_ROOT" >/dev/null \
    || { echo "--tree $PLUGIN_ROOT is not a plugin tree (no Service.qml / readable model / bin/omarchy-iptv)" >&2; exit 2; }
  TREE_LINE="== prepared tree $PLUGIN_ROOT"
fi
if [[ -n $BASELINE ]]; then
  git -C "$ROOT" rev-parse --verify -q "$BASELINE^{commit}" >/dev/null \
    || { echo "--baseline '$BASELINE' does not resolve to a commit in this repository" >&2; exit 2; }
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-key-baseline.XXXXXX") || exit 2
  chmod 0700 "$EXPORT_DIR"
  if ! git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR"; then
    echo "could not export $BASELINE" >&2; rm -rf "$EXPORT_DIR"; exit 2
  fi
  [[ -f $EXPORT_DIR/Service.qml && -f $EXPORT_DIR/bin/omarchy-iptv ]] && qa_model_files "$EXPORT_DIR" >/dev/null \
    || { echo "$BASELINE holds no Service.qml / readable model / bin/omarchy-iptv" >&2; rm -rf "$EXPORT_DIR"; exit 2; }
  PLUGIN_ROOT=$EXPORT_DIR
  TREE_LINE="== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported to $EXPORT_DIR"
fi

if [[ $MODE == live ]]; then
  # CLAUDE.md parallel rule 7, and F-M3-1: the evidence does not live in
  # whoever remembered to keep stdout. Not in check-tree: a gate step may
  # neither print a path nobody asked for nor leave a file behind.
  qa_transcript_start key || exit 2
fi
echo "$TREE_LINE"
echo "== mode $MODE   plugin tree $PLUGIN_ROOT   instrument $HERE/harness-lib.js   caller's display $LIVE_DISPLAY (never driven)"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-key.XXXXXX") || exit 2
chmod 0700 "$WORK"
T_START=$(date +%s.%N)
elapsed() { python3 -c 'import sys; print("%.1f" % (float(sys.argv[1]) - float(sys.argv[2])))' "$(date +%s.%N)" "$T_START"; }

# Every process this scenario starts, by the pid bash handed it or the pid
# the process wrote itself (cage's child, run.sh's qs.pid). Nothing here is
# found by a pattern that could match this shell.
CAGE_PID=""; CAGE_CHILD=""; SHELL_STARTED=0; SHELL_PID=""; NESTED=""; ORPHANS=""; SLOW_PID=""
kill_pid() { [[ -n ${1:-} ]] && kill -0 "$1" 2>/dev/null && { kill -TERM "$1" 2>/dev/null; wait "$1" 2>/dev/null; }; return 0; }
cleanup() {
  # The shell's children, recorded by PARENT pid (never a pattern) while
  # the shell is still alive: `reap` TERMs then KILLs quickshell, which does
  # not take its Process children with it, so a helper mid-verb -- the slow
  # helper asleep in `state init` during the O window above all -- would be
  # reparented and live out its sleep. The round-2 live lens landed a TERM
  # inside that window and found the orphan; before this line only the O
  # segment's own recording (just before its deliberate SIGKILL) fed
  # ORPHANS, so a signal between the slow start and that line stranded it.
  if (( SHELL_STARTED )) && [[ -n $SHELL_PID ]] && kill -0 "$SHELL_PID" 2>/dev/null; then
    ORPHANS="$ORPHANS $(pgrep -P "$SHELL_PID" 2>/dev/null | tr '\n' ' ')"
  fi
  (( SHELL_STARTED )) && env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" reap >/dev/null 2>&1
  # The slow helper's sleeping child survives its parent's SIGKILL (O4) and
  # the reap above alike: recorded by pid, and not ours to `wait` for.
  local p; for p in $ORPHANS; do kill -KILL "$p" 2>/dev/null; done
  # Q's slow listener, by the pid its LISTENER names (never a pattern)
  [[ -n ${SLOW_PID:-} ]] && kill -TERM "$SLOW_PID" 2>/dev/null
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  kill_pid "$CAGE_PID"
  # F takes `w` off the state directory under the running shell and gives
  # it back inside the segment; a signal in between left it 0500, and an
  # `rm -rf` of the harness directory then stopped on state.json (round-4
  # live review). The directory is this scenario's own scratch: put it back
  # on every exit, whatever the segment was doing.
  [[ -n ${STATE:-} && -d $(dirname "$STATE") ]] && chmod 0700 "$(dirname "$STATE")" 2>/dev/null
  [[ -n ${EXPORT_DIR:-} && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  [[ -n ${WORK:-} && -d $WORK ]] && rm -rf "$WORK"
  return 0
}
trap cleanup EXIT
# A signal while this shell waits on a foreground child runs no EXIT trap;
# an exit does (clip-scenario.sh measured the stranded cage, shell and socket
# without these two lines).
trap 'exit 130' INT
trap 'exit 143' TERM

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL $1${2:+ -- $2}"; }
# One assertion, one line at column zero (inside a function, two spaces),
# labelled by its letter and number, so the floor at the foot can be counted
# by recipe.
ck() { local label=$1 got=$2 want=$3; [[ $got == "$want" ]] && pass "$label: $want" || fail "$label" "got [$got], want [$want]"; }

# ------------------------------------------------------- the instrument arm
instrument() {
  local out seams
  local model
  # The tree's model as node loads it: the first file qa_model_files names is
  # the aggregator (Model.mjs, D-REL-5) or a pre-split tree's Model.js.
  model=$(qa_model_files "$PLUGIN_ROOT" | head -n 1)
  echo "== instrument arm: harness-lib.js entryKey over ${model:-<no readable model>} ($(elapsed) s)"
  # The probe hands the instrument the tree's own Model and prints one
  # `<label> <answer>` line per case. URLs are fixture paths under $WORK and
  # never reach stdout: the answers are keys, "" or names.
  cat >"$WORK/probe.js" <<'JS'
const M = require(process.argv[2])
const H = require(process.argv[3])
const url = process.argv[4]
const other = process.argv[5]
const key = M.sourceKey(M.normalizeSourceUrl(url, { origin: "cli" }))
const otherKey = M.sourceKey(M.normalizeSourceUrl(other, { origin: "cli" }))
const show = (v) => v === "" ? "(empty)" : String(v)
console.log("KEY " + key + " " + otherKey)
console.log("I1 " + show(H.entryKey(M, { id: "x", sourceKey: otherKey, playlistUrl: url })) + " want " + otherKey)
console.log("I2 " + show(H.entryKey(M, { id: "x", playlistUrl: url })) + " want " + key)
console.log("I3 " + show(H.entryKey(M, { id: "x", mpvArgs: "deadbeef", label: "0123abcd", activeKey: "cafebabe", key: "12345678", barLabelMaxWidth: 180 })))
console.log("I4 " + show(H.entryKey(M, { id: "x", sourceKey: "", playlistUrl: url })) + " want " + key)
console.log("I5 " + show(H.entryKey(M, { id: "x", sourceKey: "DEADBEEF", playlistUrl: url })) + " want " + key)
let i6
try { i6 = show(H.entryKey(M, M.findBarEntry({ layout: { right: ["io.github.other"] } }, "io.github.rmcdavid.iptv"))) } catch (e) { i6 = "threw " + e }
console.log("I6 " + i6)
console.log("I7 " + JSON.stringify(H.entryKeyNames({ id: "x", playlistUrl: url, sourceKey: key, epgUrl: other, showLogos: false })))
JS
  out=$(node "$WORK/probe.js" "$model" "$HERE/harness-lib.js" "$WORK/fixtures/a.m3u" "$WORK/fixtures/b.m3u" 2>&1)
  line() { printf '%s\n' "$out" | grep -a "^$1 " | head -1 | cut -d' ' -f2-; }
  local k1 k2; read -r k1 k2 <<<"$(line KEY)"
  if [[ ! $k1 =~ ^[0-9a-f]{8}$ || ! $k2 =~ ^[0-9a-f]{8}$ || $k1 == "$k2" ]]; then
    echo "   the probe did not run: $out"; fail "I1 the probe ran at all"; fail "I2"; fail "I3"; fail "I4"; fail "I5"; fail "I6"; fail "I7"
  else
    ck "I1 a key beside a differing URL answers the key (sourceKey first)" "$(line I1)" "$k2 want $k2"
    ck "I2 a URL alone answers its hash" "$(line I2)" "$k1 want $k1"
    ck "I3 key-shaped values in other settings answer nothing (named candidates only)" "$(line I3)" "(empty)"
    ck "I4 an empty mirror beside a URL answers the URL's hash" "$(line I4)" "$k1 want $k1"
    ck "I5 a malformed mirror beside a URL answers the URL's hash" "$(line I5)" "$k1 want $k1"
    ck "I6 an absent entry answers nothing and does not throw" "$(line I6)" "(empty)"
    ck "I7 the key-names reader lists names sorted, id excluded, no value" "$(line I7)" '["epgUrl","playlistUrl","showLogos","sourceKey"]'
  fi
  # The seams: the live arm observes the call; this is what keeps a copy of
  # the function from being pasted back into shell.qml beside the import.
  seams=$(qa_count '^ *return HarnessLib\.entryKey\(Model, Model\.findBarEntry\(barConfig, harness\.pluginId\)\)$' "$HERE/shell.qml")
  ck "S1 shell.qml's entryKey is HarnessLib.entryKey over findBarEntry" "$seams" "1"
  seams="$(qa_count 'stored: harness\.entryKey\(fakeHost\.barConfig\), published: harness\.entryKey\(fakeShell\.barConfig\)' "$HERE/shell.qml") $(qa_count 'storedKeys: HarnessLib\.entryKeyNames\(Model\.findBarEntry\(fakeHost\.barConfig' "$HERE/shell.qml")"
  ck "S2 hostEntry reads both sides through entryKey and the names through entryKeyNames" "$seams" "1 1"
  seams="$(qa_count '^ *cp "\$HERE/harness-lib\.js" "\$root/harness-lib\.js" \|\| die' "$RUN") $(qa_count '^ *qa_same_file "\$HERE/harness-lib\.js" "\$root/harness-lib\.js"' "$RUN") $(qa_count '^import "harness-lib\.js" as HarnessLib$' "$HERE/shell.qml")"
  ck "S3 run.sh stages harness-lib.js beside the model and proves the copy; shell.qml imports it" "$seams" "1 1 1"
  echo "== instrument arm done ($(elapsed) s)"
}

# ------------------------------------------------------------ the shell arm
h()    { env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" "$@"; }
ipc()  { h ipc "$@" 2>/dev/null; }
svc()  { qa_field "d$1" "$(ipc state)"; }
hf()   { qa_json_field "d$1" "$(ipc hostEntry)"; }
pf()   { qa_json_field "d$1" "$(ipc pointerState)"; }
# Did the service IGNORE at least one reload for THIS reason (R9's counter,
# by reason: R15)? yes | no, and the sentinel itself (NOFIELD) on a tree
# that has no per-reason counter or never counted that reason -- a tree
# that applied the reload counted it `file-newer`, and `save-parked` is
# then absent from the object, which is the red D3 and W were seen under.
reason_some() { local n; n=$(pf "['stateReloadsByReason']['$1']"); case $n in 0) echo no ;; [1-9]*) echo yes ;; *) echo "$n" ;; esac; }
# The whole per-reason object, for the reader (numbers keyed by reason).
reasons() { qa_json_field "json.dumps(d['stateReloadsByReason'], sort_keys=True)" "$(ipc pointerState)"; }
# A field of state.json on disk, through the same sentinels as the IPC reads
# (NULL for a key that is there and null, NOFIELD for one that is not).
sj() {
  python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("NOFILE"); raise SystemExit(0)
try:
    v = eval(sys.argv[2])
except Exception:
    print("NOFIELD"); raise SystemExit(0)
print(json.dumps(v) if isinstance(v, bool) else ("NULL" if v is None else v))' "$STATE" "$1" 2>/dev/null \
    || printf '%s\n' "$QA_NO_FILE"
}
# The key of a URL or path, by the tree under test's own function.
# The tree's model through qa_model_files (D-REL-5): its first file is what
# node requires, the aggregator or a pre-split tree's Model.js.
key_of() { node -e 'const M = require(process.argv[1]); const n = M.normalizeSourceUrl(process.argv[2], { origin: "cli" }); process.stdout.write(n === "" ? "" : M.sourceKey(n))' "$(qa_model_files "$PLUGIN_ROOT" | head -n 1)" "$1"; }
# Does the stored entry carry a key NAME? yes | no (names, never values).
stored_has() { qa_json_field "'yes' if '$1' in d['storedKeys'] else 'no'" "$(ipc hostEntry)"; }
published_has() { qa_json_field "'yes' if '$1' in d['publishedKeys'] else 'no'" "$(ipc hostEntry)"; }
sha() { sha256sum "$1" 2>/dev/null | cut -c1-16; }
# Bounded, and it SAYS it gave up (CLAUDE.md rule 3).
wait_for() {
  local want=$1 secs=$2; shift 2
  local i
  for ((i = 0; i < secs * 10; i++)); do
    [[ "$("$@")" == "$want" ]] && return 0
    sleep 0.1
  done
  echo "   gave up waiting ${secs}s for '$want' from: $*"
  return 1
}
wait_gone() {
  local p=$1 secs=$2 i
  for ((i = 0; i < secs * 10; i++)); do [[ ! -e $p ]] && return 0; sleep 0.1; done
  return 1
}
LOG="$SCRATCH/harness.log"
LOG_MARK=0
# A missing log (the first start in a fresh harness directory) is mark 0:
# bash applies `<"$LOG"` before `2>/dev/null`, so the redirection's own
# error line reached the transcript on every fresh run (round-2 live lens).
log_mark() { if [[ -f $LOG ]]; then LOG_MARK=$(wc -l <"$LOG"); else LOG_MARK=0; fi; LOG_MARK=${LOG_MARK:-0}; }
# Lines the CURRENT shell added that match an ERE: the log is appended to by
# every detached start, so a count is taken from the mark the last start set.
log_since() { tail -n +"$((LOG_MARK + 1))" "$LOG" 2>/dev/null | grep -acE -- "$1"; }
# Start a detached shell on the nested display and wait until its service has
# loaded the state and settled the cache layout. `--keep`: the seed below is
# this scenario's, and every later start must find what the previous one
# wrote. Bounded 20 s; a shell that never settles is reported, not waited on.
start_shell() {
  log_mark
  h --detach --timeout 0 --keep "$@" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  local i
  for ((i = 0; i < 200; i++)); do
    [[ $(log_since 'service loaded') -gt 0 ]] && [[ $(svc "['stateLoaded']") == true ]] && [[ $(svc "['cacheReady']") == true ]] && return 0
    sleep 0.1
  done
  echo "   the shell (pid $SHELL_PID) did not settle within 20 s: $(tail -n 3 "$WORK/start.log" | tr '\n' ' ')"
  return 1
}
# Stop it by its recorded pid (run.sh shell-stop: TERM, wait, KILL after 5 s).
stop_shell() { h shell-stop >/dev/null 2>&1; local i; for ((i = 0; i < 50; i++)); do kill -0 "$SHELL_PID" 2>/dev/null || break; sleep 0.1; done; SHELL_STARTED=0; }

# The nested compositor, as clip-scenario.sh starts and stops it (the spike
# measured that SIGTERM to cage itself is ignored for 10 s and leaves a stale
# socket; its child's exit is what ends it).
cage_start() {
  local secs=$1 i
  rm -f "$WORK/display" "$WORK/child.pid"
  cat >"$WORK/child.sh" <<CHILD
#!/bin/bash
echo "\$WAYLAND_DISPLAY" >"$WORK/display"
echo \$\$ >"$WORK/child.pid"
exec sleep $secs
CHILD
  chmod 0700 "$WORK/child.sh"
  env -u WAYLAND_DISPLAY -u DISPLAY WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
    timeout -k 5 $((secs + 10)) "$CAGE_BIN" -- "$WORK/child.sh" >"$WORK/cage.log" 2>&1 &
  CAGE_PID=$!
  for ((i = 0; i < 100; i++)); do [[ -s $WORK/display && -s $WORK/child.pid ]] && break; sleep 0.1; done
  NESTED=$(cat "$WORK/display" 2>/dev/null)
  CAGE_CHILD=$(cat "$WORK/child.pid" 2>/dev/null)
  if [[ -z $NESTED || -z $CAGE_CHILD ]]; then
    echo "SKIP key-scenario: cage did not bring up a nested display within 10 s ($(tr '\n' ' ' <"$WORK/cage.log" | head -c 300))" >&2
    exit $SKIP
  fi
  if [[ $NESTED == "$LIVE_DISPLAY" || $NESTED == wayland-1 ]]; then
    echo "REFUSING: cage's child reports display '$NESTED', which is the live session; nothing will be driven" >&2
    exit 2
  fi
}
STOP_VERDICT=""
cage_stop() {
  local i left=""
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  for ((i = 0; i < 50; i++)); do kill -0 "$CAGE_PID" 2>/dev/null || break; sleep 0.1; done
  if kill -0 "$CAGE_PID" 2>/dev/null; then left="$left cage($CAGE_PID)"; kill -KILL "$CAGE_PID" 2>/dev/null; fi
  wait "$CAGE_PID" 2>/dev/null; CAGE_PID=""; CAGE_CHILD=""
  for ((i = 0; i < 20; i++)); do [[ -e $REAL_RUNTIME/$NESTED ]] || break; sleep 0.1; done
  [[ -e $REAL_RUNTIME/$NESTED ]] && left="$left socket($NESTED)"
  [[ -z $left ]] && STOP_VERDICT=gone || STOP_VERDICT="left:$left"
}

# A source record for the seeded state file: fetched, so a start over it
# reads the cache rather than fetching (the migration's own shape).
record() {
  local key=$1 url=$2 label=$3 count=$4
  python3 -c 'import json, sys; print(json.dumps({"key": sys.argv[1], "url": sys.argv[2], "epgUrl": "", "kind": "file", "label": sys.argv[3], "labelCustom": False, "origin": "cli", "addedAt": 1799990000, "lastUsed": 1799990000, "fetchedAt": 1799990000, "channelCount": int(sys.argv[4]), "groupCount": 1}))' "$key" "$url" "$label" "$count"
}
# Every segment starts from ITS OWN seed: the shell stopped, the scratch
# cache and state wiped, real cache directories for A (20 channels) and C
# (7) written by the real helper, and a v2 state file holding exactly those
# two records -- with the active key the segment names, or none at all
# (the 0.13.5 shape) when it names "". Mode 0600 in 0700 directories, the
# modes the service and the helper both keep (CLAUDE.md 6).
seed() {
  local active=$1 extra=""
  (( SHELL_STARTED )) && stop_shell
  h clean >/dev/null 2>&1
  mkdir -p "$CACHE/sources/$KA" "$CACHE/sources/$KC" "$(dirname "$STATE")"
  chmod 0700 "$CACHE" "$CACHE/sources" "$CACHE/sources/$KA" "$CACHE/sources/$KC" "$(dirname "$STATE")"
  python3 "$PLUGIN_ROOT/bin/omarchy-iptv" playlist --url "$A" --cache-dir "$CACHE/sources/$KA" >/dev/null 2>&1
  python3 "$PLUGIN_ROOT/bin/omarchy-iptv" playlist --url "$C" --cache-dir "$CACHE/sources/$KC" >/dev/null 2>&1
  [[ -f $CACHE/sources/$KA/channels.json && -f $CACHE/sources/$KC/channels.json ]] || echo "   the helper did not write the seed caches"
  [[ -n $active ]] && extra=",\"activeKey\":\"$active\""
  printf '{"version":2,"cacheLayout":2,"favorites":[],"recents":[],"lastPlayed":null,"session":null,"sources":[%s,%s],"savedSearches":[],"hiddenGroups":[]%s}\n' \
    "$(record "$KA" "$A" "a-twenty" 20)" "$(record "$KC" "$C" "c-seven" 7)" "$extra" >"$STATE"
  chmod 0600 "$STATE"
  SHA_A=$(sha "$CACHE/sources/$KA/channels.json"); SHA_C=$(sha "$CACHE/sources/$KC/channels.json"); SHA_STATE=$(sha "$STATE")
}
# Into the start-up window from inside: the state loaded and the in-memory
# state naming `key` while the dirs are NOT ready. Polled at 100 ms, bounded
# at `secs`; WINDOW is "observed" or "missed" and the snapshot fields are
# left in W_* for the check that reads them. Used by D (the ~400 ms window
# the real helper leaves) and by O (the seconds the slow helper leaves).
WINDOW=""; W_DIRS=""; W_PARKED=""; W_HELD=""; W_MEMORY=""; W_LOADED=""
observe_window() {
  local key=$1 secs=$2 i ps
  WINDOW=missed
  for ((i = 0; i < secs * 10; i++)); do
    ps=$(ipc pointerState)
    W_LOADED=$(qa_json_field "d['stateLoaded']" "$ps"); W_MEMORY=$(qa_json_field "d['memoryActiveKey']" "$ps")
    W_DIRS=$(qa_json_field "d['dirsReady']" "$ps"); W_PARKED=$(qa_json_field "d['stateSavePending']" "$ps"); W_HELD=$(qa_json_field "d['pendingEntryKey']" "$ps")
    if [[ $W_LOADED == true && $W_MEMORY == "$key" ]]; then
      [[ $W_DIRS == false ]] && WINDOW=observed
      return 0
    fi
    [[ $W_LOADED == true && $W_DIRS == true ]] && return 0   # the window is over; what we saw is what we report
    sleep 0.1
  done
  return 1
}

shell_arm() {
  local i left before window orphan seed_playlist seed_key sha0 staged
  echo "== shell arm: the real Service.qml under cage (plugin tree $PLUGIN_ROOT) ($(elapsed) s)"
  cage_start 500
  # The stub compositor in front of PATH, as pip- and clip-scenario.sh do
  # it, and HYPRLAND_INSTANCE_SIGNATURE unset: the service's hyprctl probe
  # stops at `which`, and nothing can reach the user's compositor from here.
  mkdir -p "$SCRATCH/bin" && ln -sfn "$HERE/stub-hyprctl.py" "$SCRATCH/bin/hyprctl"
  h reap >/dev/null 2>&1
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT
  CACHE="$SCRATCH/cache/omarchy-iptv"
  STATE="$SCRATCH/state/omarchy-iptv/state.json"
  KA=$(key_of "$A"); KB=$(key_of "$B"); KC=$(key_of "$C"); KD=$(key_of "$D")
  echo "   keys: A $KA  B $KB  C $KC  D $KD"

  echo "== D: the adoption made at start-up, watched across the start-up dirs becoming ready ($(elapsed) s)"
  seed ""
  # The file goes in at 0644, not the seed's 0600: the helper's start-up
  # `state init` leaves a 0600 file alone (R10) and still chmods any other
  # mode, and that chmod is the reload the service has to survive (R9).
  # Seeded 0600, the forward run never raises the reload at all and D2 is
  # green without R9 ever deciding anything; seeded 0644 it decides on every
  # run, and D3 reads the decision off the counter.
  chmod 0644 "$STATE"
  log_mark
  h --detach --timeout 0 --keep --playlist "$A" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  observe_window "$KA" 20 || true
  ck "D1 the first start adopts the entry's URL in memory while the state save is parked (control)" \
     "$WINDOW memory:$W_MEMORY dirs:$W_DIRS parked:$W_PARKED" "observed memory:$KA dirs:false parked:true"
  wait_for true 20 pf "['dirsReady']" >/dev/null || true
  sleep 1.0   # the parked save and the entry flush land in stateInitProc's exit; give the file its moment
  ck "D2 the adopted key survives the dirs becoming ready: in memory and in the file" \
     "dirs:$(pf "['dirsReady']") memory:$(pf "['memoryActiveKey']") file:$(sj "d.get('activeKey', 'absent')")" "dirs:true memory:$KA file:$KA"
  echo "   reloads by reason across the D start: $(reasons) (ignored total $(pf "['stateReloadsIgnored']"); NOFIELD on a pre-R9 tree)"
  ck "D3 the helper tightened the 0644 file to 0600, and the reload that chmod fired was IGNORED as save-parked, not applied (R9 at the per-reason counter)" \
     "mode:$(stat -c %a "$STATE" 2>/dev/null) save-parked:$(reason_some save-parked)" "mode:600 save-parked:yes"

  echo "== N: a FRESH install -- no state directory, no state.json, no cache -- the helper CREATES the file under the adoption ($(elapsed) s)"
  # The created-file shape of D-SRC-15 (round-2 live lens): the helper's
  # `state init` writes a new state.json (O_EXCL create, then its chmod)
  # while the adoption's save is parked, so the reload hands the service
  # the helper's EMPTY default state in place of the adopted record.
  (( SHELL_STARTED )) && stop_shell
  h clean >/dev/null 2>&1
  [[ -e $STATE || -e $CACHE/sources ]] && echo "   the fresh shape was not clean: state $([[ -e $STATE ]] && echo present || echo absent), caches $([[ -e $CACHE/sources ]] && echo present || echo absent)"
  log_mark
  h --detach --timeout 0 --keep --playlist "$A" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  observe_window "$KA" 20 || true
  ck "N1 the first start adopts the entry's URL in memory while the save is parked, with no file to load (control)" \
     "$WINDOW memory:$W_MEMORY dirs:$W_DIRS parked:$W_PARKED" "observed memory:$KA dirs:false parked:true"
  wait_for true 20 pf "['dirsReady']" >/dev/null || true
  wait_for 20 20 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  ck "N2 the adopted key and its record survive the helper creating state.json: in memory and in the file" \
     "memory:$(pf "['memoryActiveKey']") file:$(sj "d.get('activeKey', 'absent')") records:$(sj "len(d['sources'])") mode:$(stat -c %a "$STATE" 2>/dev/null)" "memory:$KA file:$KA records:1 mode:600"
  ck "N3 the stored entry carries sourceKey = that key and no playlistUrl" "$(hf "['stored']") sourceKey:$(stored_has sourceKey) playlistUrl:$(stored_has playlistUrl)" "$KA sourceKey:yes playlistUrl:no"
  ck "N4 configured on it, its first fetch wrote its cache and loaded, activeCache is its directory" "$(svc "['configured']") $(svc "['channels']") $(ipc activeCache) cache:$([[ -f $CACHE/sources/$KA/channels.json ]] && echo written || echo missing)" "true 20 $CACHE/sources/$KA cache:written"
  echo "   reloads the service ignored across the fresh start: $(pf "['stateReloadsIgnored']") by reason $(reasons) (numbers; NOFIELD on a pre-R9 tree)"

  echo "== M: the two-source migration (entry URL, no activeKey) ($(elapsed) s)"
  seed ""
  start_shell --playlist "$A" || true
  wait_for true 10 svc "['configured']" >/dev/null || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  # The entry write is deferred behind the start-up dirs (R5); give it its
  # bound rather than reading the entry on the way past.
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  ck "M1 state.json activeKey is the entry URL's key" "$(sj "d.get('activeKey', 'absent')")" "$KA"
  ck "M2 the file still holds the two records it went in with, and so does sources()" "$(sj "len(d['sources'])") $(qa_json_field 'len(d)' "$(ipc sources)")" "2 2"
  ck "M3 the stored entry carries sourceKey = that key and no playlistUrl / epgUrl" "$(hf "['stored']") sourceKey:$(stored_has sourceKey) playlistUrl:$(stored_has playlistUrl) epgUrl:$(stored_has epgUrl)" "$KA sourceKey:yes playlistUrl:no epgUrl:no"
  ck "M4 the published entry, one write behind, still carries the URL (the host shape)" "$(hf "['published']") playlistUrl:$(published_has playlistUrl)" "$KA playlistUrl:yes"
  ck "M5 configured, 20 channels from the migrated cache, activeCache is its directory" "$(svc "['configured']") $(svc "['channels']") $(ipc activeCache)" "true 20 $CACHE/sources/$KA"
  ck "M6 neither cache was touched: no fetch ran, nothing moved" "A:$([[ $(sha "$CACHE/sources/$KA/channels.json") == "$SHA_A" ]] && echo same || echo changed) C:$([[ $(sha "$CACHE/sources/$KC/channels.json") == "$SHA_C" ]] && echo same || echo changed) fetches:$(log_since 'omarchy-iptv playlist:')" "A:same C:same fetches:0"

  echo "== J: a start over the MIGRATED shape (key in the file, key on the entry, no URL) ($(elapsed) s)"
  seed "$KA"
  start_shell --playlist none --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  sleep 1.0   # the window in which a deferred entry write would land
  ck "J1 no entry write at all" "$(log_since 'updateEntryInline')" "0"
  ck "J2 the file's key and count are unchanged (idempotent)" "$(sj "d.get('activeKey', 'absent')") $(sj "len(d['sources'])")" "$KA 2"
  ck "J3 configured with the same 20 channels" "$(svc "['configured']") $(svc "['channels']")" "true 20"

  echo "== C: a playlistUrl set while the shell was down, beside the surviving mirror (review P1, R1) ($(elapsed) s)"
  seed "$KA"
  start_shell --playlist "$B" --source-key "$KA" || true
  wait_for "$KB" 10 svc "['activeSourceKey']" >/dev/null || true
  wait_for 3 20 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  ck "C1 a record for the new URL, origin cli" "$(sj "[s['origin'] for s in d['sources'] if s['key'] == '$KB']")" "['cli']"
  ck "C2 state.json activeKey is ITS key, not the mirror's" "$(sj "d.get('activeKey', 'absent')")" "$KB"
  ck "C3 the stored entry carries the NEW key and no URL" "$(hf "['stored']") playlistUrl:$(stored_has playlistUrl)" "$KB playlistUrl:no"
  ck "C4 the history kept every record" "$(sj "len(d['sources'])")" "3"
  ck "C5 configured on it, its first fetch loaded, activeCache is its directory" "$(svc "['configured']") $(svc "['channels']") $(ipc activeCache)" "true 3 $CACHE/sources/$KB"

  echo "== E: an epgUrl set while the shell was down (R4) ($(elapsed) s)"
  seed "$KA"
  start_shell --playlist none --epg "$EPG" --source-key "$KA" || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  # Model.maskUrl masks EVERY query value (`kind=****`, not `kind=x`): on
  # dev, lane-key-r2 and lane-key-s1 alike, by calling it. The first version
  # of this line wanted `kind=x` and could be green on no tree (lane A's
  # DQ-A3); the file half was always what the ruling claims.
  ck "E1 the EPG URL landed on the ACTIVE record, masked for the form" \
     "file:$(sj "'same' if [s['epgUrl'] for s in d['sources'] if s['key'] == '$KA'] == ['$EPG'] else 'other'") form:$(qa_json_field "d['epgMasked']" "$(ipc editMasked "$KA")")" \
     "file:same form:http://****@127.0.0.1:9/epg.xml?token=****&kind=****"
  ck "E2 the same write took it off the stored entry" "epgUrl:$(stored_has epgUrl) $(hf "['stored']")" "epgUrl:no $KA"
  ck "E3 no IPC reply and no harness-log line carries its credential" "$(qa_count 'u:p@|token=abc' "$LOG") $(printf '%s\n%s\n%s\n' "$(ipc editMasked "$KA")" "$(ipc sources)" "$(ipc state)" | grep -acE 'u:p@|token=abc')" "0 0"

  echo "== R: removing the active source (R3) ($(elapsed) s)"
  seed "$KA"
  start_shell --playlist none --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  before=$(sj "len(d['sources'])")
  ipc removeSource "$KA" >/dev/null
  wait_for false 10 svc "['configured']" >/dev/null || true
  wait_for '' 10 hf "['stored']" >/dev/null || true
  wait_gone "$CACHE/sources/$KA" 10 || true
  ck "R1 state.json activeKey is empty IN THE FILE" "$(sj "json.dumps(d.get('activeKey', 'absent'))")" '""'
  ck "R2 the stored entry's mirror is empty and still present" "$(qa_json_field "json.dumps(d['stored'])" "$(ipc hostEntry)") sourceKey:$(stored_has sourceKey)" '"" sourceKey:yes'
  ck "R3 unconfigured, 0 channels, no active cache" "$(svc "['configured']") $(svc "['channels']") [$(ipc activeCache)]" "false 0 []"
  ck "R4 only that cache directory is gone; the other record and its cache survive" "removed:$([[ -e $CACHE/sources/$KA ]] && echo present || echo gone) C:$([[ -f $CACHE/sources/$KC/channels.json ]] && echo present || echo gone) records:$(sj "len(d['sources'])")/$before" "removed:gone C:present records:1/2"
  stop_shell
  start_shell --playlist none --source-key "" || true
  sleep 1.0
  ck "R5 a start over that stays unconfigured with the one record (control)" "$(svc "['configured']") $(sj "json.dumps(d.get('activeKey', 'absent'))") $(sj "len(d['sources'])")" 'false "" 1'

  echo "== O: the interrupted order -- a NEW URL on the entry, the shell killed between the two writes (R5, review P2) ($(elapsed) s)"
  seed ""
  # The slow tree: the tree under test with its helper replaced by
  # fixtures/slow-helper.py, which holds `state init` for SLOW_MS and then
  # execs the real helper (bin/omarchy-iptv.real) with the same argv. Nothing
  # is stubbed: `dirsReady` simply stays false for seconds instead of ~400 ms,
  # which is the window the review's P2 lives in. rewind-scenario.sh's R16
  # stages the same shape for the same reason.
  SLOW_TREE="$WORK/slow-tree"; mkdir -p "$SLOW_TREE/bin"
  staged=1
  for f in manifest.json Service.qml Guide.qml BarWidget.qml; do cp "$PLUGIN_ROOT/$f" "$SLOW_TREE/$f" 2>/dev/null || staged=0; done
  # The model is every file qa_model_files names (Model.mjs and its parts since
  # D-REL-5, or a pre-split tree's Model.js), each at its own relative path:
  # rewind-scenario.sh's R16 stages its slow tree the same way.
  local -a model_files=(); local mf rel
  mapfile -t model_files < <(qa_model_files "$PLUGIN_ROOT")
  (( ${#model_files[@]} > 0 )) || staged=0
  for mf in "${model_files[@]}"; do
    rel=${mf#"$PLUGIN_ROOT/"}
    mkdir -p "$SLOW_TREE/$(dirname "$rel")" && cp "$mf" "$SLOW_TREE/$rel" 2>/dev/null || staged=0
  done
  cp -R "$PLUGIN_ROOT/contrib" "$SLOW_TREE/contrib" 2>/dev/null || true
  cp "$PLUGIN_ROOT/bin/omarchy-iptv" "$SLOW_TREE/bin/omarchy-iptv.real" 2>/dev/null || staged=0
  cp "$HERE/fixtures/slow-helper.py" "$SLOW_TREE/bin/omarchy-iptv" 2>/dev/null || staged=0
  chmod +x "$SLOW_TREE/bin/omarchy-iptv" "$SLOW_TREE/bin/omarchy-iptv.real" 2>/dev/null || true
  (( staged )) || echo "   the slow tree could not be staged from $PLUGIN_ROOT"
  sha0=$SHA_STATE
  export OMARCHY_IPTV_PLUGIN_ROOT=$SLOW_TREE OMARCHY_IPTV_SLOW_MS=$SLOW_MS OMARCHY_IPTV_SLOW_VERBS="state init"
  log_mark
  h --detach --timeout 0 --keep --playlist "$D" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  observe_window "$KD" 6 || true
  ck "O1 the window was observed from inside: state loaded, dirs not ready, save parked, memory naming the new source (control)" \
     "$WINDOW loaded:$W_LOADED dirs:$W_DIRS parked:$W_PARKED memory:$W_MEMORY" "observed loaded:true dirs:false parked:true memory:$KD"
  ck "O2 inside it the entry write WAITS for the parked state save: URL still stored, key held" \
     "playlistUrl:$(stored_has playlistUrl) held:$W_HELD" "playlistUrl:yes held:$KD"
  ck "O3 inside it state.json on disk is untouched (control)" "$([[ $(sha "$STATE") == "$sha0" ]] && echo untouched || echo written)" "untouched"
  # The seed for the restart is what the host would still HOLD: observed
  # now, before the kill, because a killed shell cannot be asked. The fake
  # host lives in memory, so this observation is the only thing that
  # survives the kill; the real host's file would survive it by itself.
  # Only what the stored entry CARRIES is re-seeded, by key NAME: `hf
  # stored` answers the URL's hash when the entry holds no `sourceKey`, and
  # the first version passed that back as `--source-key`, an entry no host
  # could hold at that point (the write is parked; round-2 live lens P3).
  seed_playlist=none; [[ $(stored_has playlistUrl) == yes ]] && seed_playlist=$D
  seed_args=(--playlist "$seed_playlist"); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  # The crash: SIGKILL by the recorded pid, the slow helper's sleeping child
  # recorded first (it is orphaned by the kill and reaped by pid below).
  orphan=$(pgrep -P "$SHELL_PID" 2>/dev/null | tr '\n' ' '); ORPHANS="$ORPHANS $orphan"
  kill -KILL "$SHELL_PID" 2>/dev/null
  for ((i = 0; i < 50; i++)); do kill -0 "$SHELL_PID" 2>/dev/null || break; sleep 0.1; done
  for p in $orphan; do kill -KILL "$p" 2>/dev/null; done
  rm -f "$SCRATCH/qs.pid"; SHELL_STARTED=0
  ck "O4 after the kill state.json is still the file the shell started from (control)" "$([[ $(sha "$STATE") == "$sha0" ]] && echo untouched || echo written) activeKey:$(sj "json.dumps(d.get('activeKey', 'absent'))")" 'untouched activeKey:"absent"'
  # The next start, on the real tree, over the entry as the host held it.
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT; unset OMARCHY_IPTV_SLOW_MS OMARCHY_IPTV_SLOW_VERBS
  echo "   restarting over the entry as stored: playlist $([[ $seed_playlist == none ]] && echo none || echo '(set)'), sourceKey $seed_key"
  start_shell "${seed_args[@]}" || true
  wait_for "$KD" 10 svc "['activeSourceKey']" >/dev/null || true
  wait_for 11 20 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  ck "O5 the next start RECOVERS the new source: in the file, active, configured, fetched" \
     "record:$(sj "len([s for s in d['sources'] if s['key'] == '$KD'])") activeKey:$(sj "d.get('activeKey', 'absent')") $(svc "['configured']") $(svc "['channels']")" \
     "record:1 activeKey:$KD true 11"
  ck "O6 and the migration then completes: key on the entry, URL off it" "$(hf "['stored']") playlistUrl:$(stored_has playlistUrl)" "$KD playlistUrl:no"

  echo "== W: the D-SRC-15 sibling -- an IPC switch, then a remove, INSIDE the start-up window, the chmod reload landing after the call (SRC-MIG-16) ($(elapsed) s)"
  # The O staging again (the slow tree holds `state init` for SLOW_MS), over
  # a file seeded at 0644 so the helper's chmod -- and the reload it raises
  # -- lands AFTER the IPC call, carrying the pre-call text. Lifted from the
  # round-3 live lens's scratch driver (rev-key3-dataloss/dqsib-child.sh),
  # which observed both calls holding on lane-key-s2 and nowhere in a
  # segment. The start names the key the file already holds (`--playlist
  # none --source-key KA`), the migrated shape, so nothing is adopted: the
  # only change in memory is the call's own.
  export OMARCHY_IPTV_PLUGIN_ROOT=$SLOW_TREE OMARCHY_IPTV_SLOW_MS=$SLOW_MS OMARCHY_IPTV_SLOW_VERBS="state init"
  seed "$KA"
  chmod 0644 "$STATE"
  log_mark
  h --detach --timeout 0 --keep --playlist none --source-key "$KA" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  observe_window "$KA" 6 || true
  res=$(ipc switchSource "$KC")
  ck "W1 inside the window a switch to C is accepted, in memory and held, the file still naming A at 0644 (control)" \
     "$WINDOW dirs:$(pf "['dirsReady']") ok:$(qa_json_field "d['ok']" "$res") memory:$(pf "['memoryActiveKey']") held:$(pf "['pendingEntryKey']") file:$(sj "d.get('activeKey', 'absent')") mode:$(stat -c %a "$STATE" 2>/dev/null)" \
     "observed dirs:false ok:true memory:$KC held:$KC file:$KA mode:644"
  wait_for true 15 pf "['dirsReady']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  wait_for "$KC" 10 hf "['stored']" >/dev/null || true
  sleep 1.0   # the parked save, the chmod reload and the mirror all land around stateInitProc's exit
  echo "   reloads by reason across the W switch: $(reasons)"
  ck "W2 after the dirs are ready the switch SURVIVED the chmod reload: C in memory and in the file, mode 600" \
     "memory:$(pf "['memoryActiveKey']") file:$(sj "d.get('activeKey', 'absent')") mode:$(stat -c %a "$STATE" 2>/dev/null)" "memory:$KC file:$KC mode:600"
  ck "W3 the reload was counted save-parked and the mirror followed the LANDED save: stored C, no playlistUrl, nothing held" \
     "save-parked:$(reason_some save-parked) $(hf "['stored']") playlistUrl:$(stored_has playlistUrl) held:$(pf "['pendingEntryKey']")" "save-parked:yes $KC playlistUrl:no held:NULL"
  ck "W4 both caches survive and the service is configured on C (control)" \
     "A:$([[ -f $CACHE/sources/$KA/channels.json ]] && echo present || echo gone) C:$([[ -f $CACHE/sources/$KC/channels.json ]] && echo present || echo gone) $(svc "['configured']") $(svc "['activeSourceKey']") $(svc "['channels']")" \
     "A:present C:present true $KC 7"
  # The same window, a remove of the active source.
  seed "$KA"
  chmod 0644 "$STATE"
  log_mark
  h --detach --timeout 0 --keep --playlist none --source-key "$KA" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  observe_window "$KA" 6 || true
  res=$(ipc removeSource "$KA")
  ck "W5 inside the window the active source is removed: accepted, the pointer cleared in memory and held empty, the file still naming A (control)" \
     "$WINDOW dirs:$(pf "['dirsReady']") ok:$(qa_json_field "d['ok']" "$res") memory:[$(pf "['memoryActiveKey']")] held:[$(pf "['pendingEntryKey']")] file:$(sj "d.get('activeKey', 'absent')")" \
     "observed dirs:false ok:true memory:[] held:[] file:$KA"
  wait_for true 15 pf "['dirsReady']" >/dev/null || true
  wait_for false 10 svc "['configured']" >/dev/null || true
  wait_gone "$CACHE/sources/$KA" 10 || true
  sleep 1.0
  echo "   reloads by reason across the W remove: $(reasons)"
  ck "W6 after the dirs are ready the removal survived the reload: pointer empty in the file with one record, mirror empty, A's cache gone, C's kept, unconfigured, counted save-parked" \
     "file:$(sj "json.dumps(d.get('activeKey', 'absent'))") records:$(sj "len(d['sources'])") stored:$(qa_json_field "json.dumps(d['stored'])" "$(ipc hostEntry)") A:$([[ -e $CACHE/sources/$KA ]] && echo present || echo gone) C:$([[ -f $CACHE/sources/$KC/channels.json ]] && echo present || echo gone) $(svc "['configured']") save-parked:$(reason_some save-parked)" \
     'file:"" records:1 stored:"" A:gone C:present false save-parked:yes'
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT; unset OMARCHY_IPTV_SLOW_MS OMARCHY_IPTV_SLOW_VERBS

  echo "== F: the state write FAILS with the dirs ready -- an unwritable state directory under a running shell, a CLI set, a switch, a restart (R13, round-3 P1) ($(elapsed) s)"
  seed "$KA"
  start_shell --playlist none --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  # A start over a matching key still parks one save (the round-3 review's
  # remark); let it land before the disk is taken away, so F2's failure is
  # the CLI set's and nothing else's.
  wait_for 0 10 pf "['stateSavesInFlight']" >/dev/null || true
  sleep 0.5
  ck "F1 configured on A with nothing in flight and no failure recorded (control)" \
     "$(svc "['configured']") $(svc "['activeSourceKey']") inflight:$(pf "['stateSavesInFlight']") failed:$(pf "['stateSaveFailed']") signalled:$(log_since 'sourcesPersistFailed')" "true $KA inflight:0 failed:false signalled:0"
  sha0=$(sha "$STATE")
  # The disk goes away: the directory loses `w`, so the FileView's atomic
  # temp file cannot be created (a full disk and a read-only ~/.local/state
  # fail the same call). This scenario's own scratch directory, 0700 again
  # below before the shell is stopped.
  chmod 0500 "$(dirname "$STATE")"
  ipc set playlistUrl "$B" >/dev/null
  wait_for true 10 pf "['stateSaveFailed']" >/dev/null || true
  wait_for "$KB" 10 svc "['activeSourceKey']" >/dev/null || true
  sleep 1.0
  ck "F2 the CLI value is adopted in memory and its state write FAILED: failure recorded, nothing in flight, nothing held (control: the rig made the write fail)" \
     "memory:$(pf "['memoryActiveKey']") failed:$(pf "['stateSaveFailed']") inflight:$(pf "['stateSavesInFlight']") held:$(pf "['pendingEntryKey']")" "memory:$KB failed:true inflight:0 held:NULL"
  ck "F3 the stored entry was NOT rewritten: the URL is still on it, the only copy of the input, beside the OLD mirror" \
     "$(hf "['stored']") playlistUrl:$(stored_has playlistUrl)" "$KA playlistUrl:yes"
  ck "F4 state.json on disk is untouched, the failure is logged without a URL, and sourcesPersistFailed(state_write_failed) was signalled exactly once" \
     "file:$([[ $(sha "$STATE") == "$sha0" ]] && echo untouched || echo written) logged:$([[ $(log_since 'state.json could not be written') -gt 0 ]] && echo yes || echo no) signalled:$(log_since 'sourcesPersistFailed .*state_write_failed') urls:$(tail -n +"$((LOG_MARK + 1))" "$LOG" 2>/dev/null | grep -a 'could not be written' | grep -ac '://')" \
     "file:untouched logged:yes signalled:1 urls:0"
  # The switch's OWN mark: F2's episode already logged one `left as it is`
  # line, so a count from the start's mark read `left:yes` before the
  # switch was issued and could not go red for the switch's own drop
  # (round-4 live review P3). From here F5's halves are the switch's.
  log_mark
  res=$(ipc switchSource "$KC")
  sleep 1.0
  ck "F5 a switch on the failed disk is accepted (the write is issued), lands in memory only, holds no mirror, the entry is left as it is, no second signal for the episode" \
     "ok:$(qa_json_field "d['ok']" "$res") code:$(qa_json_field "d['code']" "$res") memory:$(pf "['memoryActiveKey']") held:$(pf "['pendingEntryKey']") $(hf "['stored']") playlistUrl:$(stored_has playlistUrl) left:$([[ $(log_since 'left as it is \(save-failed\)') -gt 0 ]] && echo yes || echo no) signalled:$(log_since 'sourcesPersistFailed .*state_write_failed') file:$([[ $(sha "$STATE") == "$sha0" ]] && echo untouched || echo written)" \
     "ok:true code:ok memory:$KC held:NULL $KA playlistUrl:yes left:yes signalled:0 file:untouched"

  echo "== L: the logo toggle on the same failed disk, through the guide's Sources key path (R16, round-4 review P1) ($(elapsed) s)"
  # The second owned-entry writer, in the state F leaves: memory names C,
  # the file still names A, the stored entry carries A beside B's URL (the
  # only copy of that input). `g` in Sources opens the logo consent, the
  # confirm calls Service.setShowLogos(true). Before R16 that write mirrored
  # the in-memory key and stripped the URL -- the lens's driver read the
  # stored entry as [C, no playlistUrl] on lane-key-t2 and found no record
  # for B after the restart. The guide is opened here and only here; the
  # verbs call the guide's own handlers (shell.qml sourcesKey), no keystroke.
  log_mark
  ipc open '{}' >/dev/null; sleep 0.5
  ipc sourcesKey enter >/dev/null; sleep 0.3
  ipc sourcesKey g >/dev/null; sleep 0.3
  ipc sourcesKey confirm >/dev/null
  wait_for 1 10 log_since 'updateEntryInline' >/dev/null || true
  wait_for yes 5 stored_has showLogos >/dev/null || true
  sleep 0.5
  ck "L1 logos on, and the stored entry keeps the URL beside the mirror the FILE holds (not the in-memory key), with showLogos on it" \
     "logos:$(qa_json_field "d['guide']['showLogos']" "$(ipc state)") stored:$(hf "['stored']") file:$(sj "d.get('activeKey', 'absent')") memory:$(pf "['memoryActiveKey']") playlistUrl:$(stored_has playlistUrl) showLogos:$(stored_has showLogos)" \
     "logos:true stored:$KA file:$KA memory:$KC playlistUrl:yes showLogos:yes"
  ck "L2 one entry write, patched alone: the write's key list keeps playlistUrl (set: the only copy) and sourceKey beside showLogos, logged as written alone (save-failed), no new signal, state.json untouched" \
     "writes:$(log_since 'updateEntryInline') keys:$(tail -n +"$((LOG_MARK + 1))" "$LOG" 2>/dev/null | grep -a 'updateEntryInline' | grep -aE 'keys: ([^ ]*,)?playlistUrl(,| )' | grep -aE 'keys: ([^ ]*,)?sourceKey(,| )' | grep -aE 'keys: ([^ ]*,)?showLogos(,| )' | grep -ac 'playlist (set)') alone:$(log_since 'logo setting written alone.*\(save-failed\)') signalled:$(log_since 'sourcesPersistFailed .*state_write_failed') file:$([[ $(sha "$STATE") == "$sha0" ]] && echo untouched || echo written)" \
     "writes:1 keys:1 alone:1 signalled:0 file:untouched"
  ipc close >/dev/null
  # The next start, over the entry EXACTLY as the host stored it after L:
  # the URL the failed write left there, beside whatever mirror L left.
  # Re-seeded by key NAME as O does it, and observed BEFORE the stop: a
  # stopped shell cannot be asked, and the fake host lives in its memory
  # (the first run of this segment read the entry after stop_shell, got
  # "no" from a dead IPC, and restarted with no playlist at all: F6/F7 red
  # for the rig's own reason). The key is the one OBSERVED stored, not A:
  # a tree whose toggle moved the mirror restarts over the key it moved to.
  seed_playlist=none; [[ $(stored_has playlistUrl) == yes ]] && seed_playlist=$B
  seed_args=(--playlist "$seed_playlist"); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  chmod 0700 "$(dirname "$STATE")"
  stop_shell
  echo "   restarting over the entry as stored: playlist $([[ $seed_playlist == none ]] && echo none || echo '(set)'), sourceKey $seed_key"
  start_shell "${seed_args[@]}" || true
  wait_for "$KB" 10 svc "['activeSourceKey']" >/dev/null || true
  wait_for 3 20 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  ck "F6 the next start RE-ADOPTS the URL the failed write left on the entry (as stored after L): its record in the file, active, fetched, and the URL off the entry" \
     "record:$(sj "len([s for s in d['sources'] if s['key'] == '$KB'])") activeKey:$(sj "d.get('activeKey', 'absent')") $(svc "['configured']") $(svc "['channels']") $(hf "['stored']") playlistUrl:$(stored_has playlistUrl)" \
     "record:1 activeKey:$KB true 3 $KB playlistUrl:no"
  ck "F7 the history holds the three records and nothing carries B's path (the switch that landed in memory only went with the shell)" \
     "records:$(sj "len(d['sources'])") leaks:$(qa_count "$B" "$LOG") $(printf '%s\n%s\n%s\n' "$(ipc state)" "$(ipc hostEntry)" "$(ipc sources)" | grep -ac "$B")" "records:3 leaks:0 0"

  echo "== U: an EPG input with NO active source, HELD in the state by R19b, through a heal write and the active move, on both hosts (R17, round-6 data-loss P1; R19b) ($(elapsed) s)"
  # The round-6 data-loss lens's P1, lifted from its live driver
  # (rev-key6-dataloss/epg-child.sh): two saved sources, NONE active, and an
  # epgUrl the user set while the shell was down. R12 leaves it on the entry
  # because nothing can consume it, and nothing recorded that state: with
  # the state loaded and nothing outstanding the logo toggle HEALS, and
  # before R17a a heal dropped every retired key -- the value was then on no
  # record and off the entry (the lens read LOST with the toggle, KEPT
  # without, on lane-key-v2). R17a: a retired input leaves the entry only
  # when it is consumed. R17b: the switch lands it on the switched-to record
  # in the same turn, before the mirror strips it. The second half runs the
  # SAME rig on the echoing fake host (run.sh --host echo, D-HOST-4's lever):
  # there the switch alone lost it, because the mirror's heal stripped the
  # entry and the host published the stripped entry at once, so no reconcile
  # ever saw the input beside an active record. The entry's VALUES are never
  # read: key names from hostEntry, the record's EPG compared inside python
  # against the fixture string and printed as the keys that hold it. The
  # harness seed always carries an `epgUrl` NAME (empty when unset), so a
  # name read after a restart proves nothing (the lens's own correction);
  # the restart checks read the file and the service instead.
  # R19b (round 9) moved where the input waits: it is HELD in state.json as
  # pendingEpg and taken off the entry by the write after that save lands,
  # so U1 now reads the file for it (held:yes) and the entry for its absence;
  # R12 kept it on the entry, a possibly credentialed URL in shell.json for
  # as long as no source existed. The rest of U is unchanged in what it
  # proves: no write loses it, and the switch lands it.
  seed ""
  start_shell --playlist none --epg "$EPG" --source-key "" || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 0.5
  epg_on() { sj "','.join(sorted(s['key'] for s in d['sources'] if s.get('epgUrl') == '$EPG')) or 'none'"; }
  held() { sj "'yes' if (d.get('pendingEpg') or {}).get('url') == '$EPG' else 'no'"; }
  ck "U1 loaded on the lagging host with no active source: the EPG HELD in the state file, OFF the stored entry, on no record (R19b)" \
     "host:$(qa_json_field "d['host']" "$(ipc hostEntry)") configured:$(svc "['configured']") memory:[$(pf "['memoryActiveKey']")] epgUrl:$(stored_has epgUrl) held:$(held) on:$(epg_on)" \
     "host:lag configured:false memory:[] epgUrl:no held:yes on:none"
  log_mark
  ipc open '{}' >/dev/null; sleep 0.5
  ipc sourcesKey enter >/dev/null; sleep 0.3
  ipc sourcesKey g >/dev/null; sleep 0.3
  ipc sourcesKey confirm >/dev/null
  wait_for 1 10 log_since 'updateEntryInline io' >/dev/null || true
  wait_for yes 5 stored_has showLogos >/dev/null || true
  sleep 0.5
  ck "U2 the logo toggle HEALS (nothing outstanding) and the held EPG is untouched: logos on, one write, not written alone, nothing kept on the entry, still held in the file" \
     "logos:$(qa_json_field "d['guide']['showLogos']" "$(ipc state)") writes:$(log_since 'updateEntryInline io') alone:$(log_since 'logo setting written alone') epgUrl:$(stored_has epgUrl) kept:$(log_since 'keeps an input no source has adopted yet \(epgUrl\)') held:$(held) on:$(epg_on)" \
     "logos:true writes:1 alone:0 epgUrl:no kept:0 held:yes on:none"
  ipc close >/dev/null
  res=$(ipc switchSource "$KA")
  wait_for "$KA" 10 hf "['stored']" >/dev/null || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 1.0
  ck "U3 the switch lands the held EPG on A's record in the file and clears it: A holds it, nothing held, the file and the mirror name A, no epgUrl on the stored entry, configured on A" \
     "ok:$(qa_json_field "d['ok']" "$res") on:$(epg_on) held:$(held) file:$(sj "d.get('activeKey', 'absent')") stored:$(hf "['stored']") epgUrl:$(stored_has epgUrl) $(svc "['configured']") $(svc "['activeSourceKey']")" \
     "ok:true on:$KA held:no file:$KA stored:$KA epgUrl:no true $KA"
  seed_args=(--playlist none); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  [[ $(stored_has epgUrl) == yes ]] && seed_args+=(--epg "$EPG")
  stop_shell
  start_shell "${seed_args[@]}" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  ck "U4 a restart over the entry as stored stands on A with the EPG on A's record" \
     "$(svc "['activeSourceKey']") $(svc "['channels']") on:$(epg_on) records:$(sj "len(d['sources'])")" "$KA 20 on:$KA records:2"
  # The echoing host: no toggle, the switch alone.
  seed ""
  start_shell --host echo --playlist none --epg "$EPG" --source-key "" || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 0.5
  ck "U5 the fake host ECHOES (the lever took) and the R19b state holds: no active source, the EPG held in the file and off the stored and the published entry alike, on no record" \
     "host:$(qa_json_field "d['host']" "$(ipc hostEntry)") configured:$(svc "['configured']") epgUrl:$(stored_has epgUrl)/$(published_has epgUrl) held:$(held) on:$(epg_on)" \
     "host:echo configured:false epgUrl:no/no held:yes on:none"
  res=$(ipc switchSource "$KA")
  wait_for "$KA" 10 hf "['stored']" >/dev/null || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 1.0
  ck "U6 the switch lands the held EPG on A's record and clears it, and the echoing host publishes the mirror at once: A holds it, nothing held, both sides name A, epgUrl on neither" \
     "ok:$(qa_json_field "d['ok']" "$res") on:$(epg_on) held:$(held) stored:$(hf "['stored']") published:$(hf "['published']") epgUrl:$(stored_has epgUrl)/$(published_has epgUrl)" \
     "ok:true on:$KA held:no stored:$KA published:$KA epgUrl:no/no"
  seed_args=(--host echo --playlist none); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  [[ $(stored_has epgUrl) == yes ]] && seed_args+=(--epg "$EPG")
  stop_shell
  start_shell "${seed_args[@]}" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  ck "U7 a restart over that (echoing host) stands on A with the EPG on A's record" \
     "$(svc "['activeSourceKey']") $(svc "['channels']") on:$(epg_on) records:$(sj "len(d['sources'])")" "$KA 20 on:$KA records:2"

  echo "== K: a REFUSED playlistUrl beside a pending EPG SETTLES, on both hosts (R18b, R18a; the round-7 data-loss lens's two loops) ($(elapsed) s)"
  # Lifted from the round-7 data-loss lens's live driver (rev-key7-dataloss/
  # loop-child.sh). Two saved sources, NONE active, an epgUrl R12 leaves on
  # the entry, and a playlistUrl the plugin REFUSES (an ftp:// URL carrying a
  # credential). On lane-key-w2 the lagging host looped: the heal stripped
  # the refused value from the STORED entry, the host kept publishing the
  # pre-write entry, every reconcile asked for the strip again, the no-op
  # write reassigned the own-write record, `settings` re-evaluated and
  # reconcile ran again -- about 3,000 entry writes a second and the shell's
  # CPU saturated (the lens: 15,003 writes and 549 ticks in 5 s). The
  # echoing host settles on the bare value (K2, a control there) and looped
  # on a WHITESPACE-wrapped one (K3), which round 7's keep decision never
  # counted as consumed (P1-A). The window opens 2 s after the shell
  # settles and runs 5 s; writes are the harness log's updateEntryInline
  # lines (a no-op hand-over logs one too), ticks are utime + stime of the
  # shell's own pid. Bounds: at most 2 writes and 50 ticks (0.5 s of CPU)
  # in the window; an idle shell reads 0 and 0, the loop thousands.
  loop_window() {
    local w0 t0 w1 t1
    sleep 2
    w0=$(log_since 'updateEntryInline'); t0=$(awk '{print $14 + $15}' "/proc/$SHELL_PID/stat" 2>/dev/null)
    sleep 5
    w1=$(log_since 'updateEntryInline'); t1=$(awk '{print $14 + $15}' "/proc/$SHELL_PID/stat" 2>/dev/null)
    echo "   measured on shell pid $SHELL_PID: $((w1 - w0)) entry writes and $((t1 - t0)) CPU ticks in 5 s (CLK_TCK $(getconf CLK_TCK))" >&2
    if [[ ! $w0$w1 =~ ^[0-9]+$ || ! $t0$t1 =~ ^[0-9]+$ ]]; then echo unmeasured
    elif (( w1 - w0 <= 2 && t1 - t0 <= 50 )); then echo settled
    else echo LOOP; fi
  }
  seed ""
  start_shell --playlist "$BAD" --epg "$EPG" --source-key "" || true
  verdict=$(loop_window)
  ck "K1 the lagging host with a refused playlistUrl beside a pending EPG SETTLES (at most 2 entry writes and 50 CPU ticks in 5 s), the refused value is off the stored entry and the EPG is HELD in the state file, off it too (R19b)" \
     "$verdict host:$(qa_json_field "d['host']" "$(ipc hostEntry)") playlistUrl:$(stored_has playlistUrl) epgUrl:$(stored_has epgUrl) held:$(held) on:$(epg_on)" \
     "settled host:lag playlistUrl:no epgUrl:no held:yes on:none"
  seed ""
  start_shell --host echo --playlist "$BAD" --epg "$EPG" --source-key "" || true
  verdict=$(loop_window)
  ck "K2 the echoing host with the same entry settles too (control: the echo host settled on a bare value on every tree), the refused value off the stored entry, the EPG held in the file" \
     "$verdict host:$(qa_json_field "d['host']" "$(ipc hostEntry)") playlistUrl:$(stored_has playlistUrl) epgUrl:$(stored_has epgUrl) held:$(held)" \
     "settled host:echo playlistUrl:no epgUrl:no held:yes"
  seed ""
  start_shell --host echo --playlist "  $BAD " --epg "$EPG" --source-key "" || true
  verdict=$(loop_window)
  ck "K3 the echoing host with the refused value WRAPPED IN WHITESPACE (as \`omarchy bar set\` stores it) settles, and the refused credential leaves the stored entry once reported" \
     "$verdict host:$(qa_json_field "d['host']" "$(ipc hostEntry)") playlistUrl:$(stored_has playlistUrl) epgUrl:$(stored_has epgUrl) held:$(held)" \
     "settled host:echo playlistUrl:no epgUrl:no held:yes"

  echo "== Z: whitespace-wrapped inputs are compared the way adoption compares (R18a, the round-7 data-loss lens's P1-A) ($(elapsed) s)"
  # Lifted from the lens's resurrect-child.sh and loop-child.sh MODE=badws.
  # `omarchy bar set` hands the value to `jq --arg` as typed, so a pasted
  # URL can carry surrounding whitespace onto the entry; settingsFrom trims
  # it and round 7's keep decision did not, so the value never matched its
  # own snapshot. Z1/Z2: a whitespace-wrapped CLI playlist adopted and then
  # REMOVED -- on lane-key-w2 the remove's own mirror write carried it back
  # onto the stored entry and the next start re-adopted the removed source
  # and made it active. Z3: a whitespace-wrapped REFUSED credential beside a
  # working source stayed on the stored entry for good.
  seed "$KA"
  start_shell --playlist "  $B  " --source-key "$KA" || true
  wait_for "$KB" 10 svc "['activeSourceKey']" >/dev/null || true
  res=$(ipc removeSource "$KB")
  wait_for "" 10 hf "['stored']" >/dev/null || true
  sleep 1.0
  ck "Z1 a whitespace-wrapped CLI playlist adopted (B), then that source removed: the removal stands in memory and in the file, and the stored entry carries NO playlistUrl" \
     "ok:$(qa_json_field "d['ok']" "$res") active:[$(svc "['activeSourceKey']")] records:$(sj "len([s for s in d['sources'] if s['key'] == '$KB'])") playlistUrl:$(stored_has playlistUrl)" \
     "ok:true active:[] records:0 playlistUrl:no"
  seed_args=(--playlist none); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  [[ $(stored_has playlistUrl) == yes ]] && seed_args=(--playlist "  $B  " "${seed_args[@]:2}")
  stop_shell
  echo "   restarting over the entry as stored: playlist $([[ ${seed_args[1]} == none ]] && echo none || echo '(the removed source, as stored)'), sourceKey $seed_key"
  start_shell "${seed_args[@]}" || true
  sleep 1.0
  ck "Z2 the next start over that entry does NOT resurrect the removed source: no record for B, not active" \
     "records:$(sj "len([s for s in d['sources'] if s['key'] == '$KB'])") active:[$(svc "['activeSourceKey']")]" "records:0 active:[]"
  seed "$KA"
  start_shell --playlist "  $BAD"$'\t' --source-key "$KA" || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  sleep 0.5
  ck "Z3 a whitespace-wrapped REFUSED credential beside a working source leaves the stored entry once reported, and the working source stays active" \
     "playlistUrl:$(stored_has playlistUrl) active:$(svc "['activeSourceKey']") $(svc "['configured']")" "playlistUrl:no active:$KA true"

  echo "== A: the in-app add with an EPG pending, through the harness addSource verb (R17b, R18d / OQ-W3 ruled) ($(elapsed) s)"
  # The probe commit of an in-app add (Service's sourceProbeProc exit), which
  # U never reached live (the round-7 live lens's P3: the commit's R17b call
  # could be removed with this scenario green). A1: the form carries no
  # guide URL, and the pending CLI epgUrl lands on the new record (R17b).
  # A2: the form carries its OWN guide URL, and the lead's OQ-W3 ruling
  # (R18d) makes it win -- the user's later explicit input for the same slot
  # supersedes the pending value, which the commit's mirror strips and the
  # service logs by key name only. On lane-key-w2 the stale CLI value
  # replaced the form's on the record and the form's value existed nowhere.
  form_on() { sj "','.join(sorted(s['key'] for s in d['sources'] if s.get('epgUrl') == '$FORM_EPG')) or 'none'"; }
  seed ""
  start_shell --playlist none --epg "$EPG" --source-key "" || true
  res=$(ipc addSource "$D" "" "")
  wait_for "$KD" 20 svc "['activeSourceKey']" >/dev/null || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 0.5
  ck "A1 an in-app add with NO guide URL in the form while a CLI epgUrl is pending: the new record is active and holds the pending EPG, and the stored entry no longer carries it" \
     "ok:$(qa_json_field "d['ok']" "$res") active:$(svc "['activeSourceKey']") on:$(epg_on) epgUrl:$(stored_has epgUrl) stored:$(hf "['stored']")" \
     "ok:true active:$KD on:$KD epgUrl:no stored:$KD"
  seed ""
  start_shell --playlist none --epg "$EPG" --source-key "" || true
  res=$(ipc addSource "$D" "$FORM_EPG" "")
  wait_for "$KD" 20 svc "['activeSourceKey']" >/dev/null || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 0.5
  ck "A2 an in-app add whose FORM carries its own guide URL, submitted AFTER a CLI epgUrl was held: the form (later) is on the new record, the held value on no record, cleared and off the stored entry, superseded and logged by setting and key once (R19c)" \
     "ok:$(qa_json_field "d['ok']" "$res") active:$(svc "['activeSourceKey']") form:$(form_on) pending:$(epg_on) held:$(held) epgUrl:$(stored_has epgUrl) logged:$(log_since 'supersede.*\(epgUrl\)|\(epgUrl\).*supersede')" \
     "ok:true active:$KD form:$KD pending:none held:no epgUrl:no logged:1"

  echo "== Y: a publish that goes A -> B -> A on the lagging host, then the user's own act (R19a; the round-8 lenses' P1-A) ($(elapsed) s)"
  # Lifted from the round-8 data-loss lens's aba-child.sh (T=logo, bad, epg).
  # Round 8's funnel skipped an owned write when its record of its LAST
  # write said the host already stored the entry, judged while the publish
  # equalled the publish recorded then. `omarchy bar set` re-setting a value
  # restores exactly the entry stored before the plugin's last write, the
  # lagging host publishes it again, the record comes back, and the funnel
  # skipped writes the host WOULD have stored: Y1 the in-app logo OFF (the
  # guide's own `g`), Y2 the strip of a re-set refused credential, Y3 the
  # strip of a re-set EPG input -- which the next start then re-adopted over
  # an in-app guide URL edit. R19a hands every owned write to the host.
  # Values are never printed: names from hostEntry, the guide's own
  # showLogos, and the record's EPG compared inside python.
  # Y1 and Y3 start over an entry carrying A's playlistUrl, as the lens's
  # driver does: the start adopts it and the mirror's write strips it, so
  # every later entry carries no retired key and a re-set reproduces the
  # earlier entry EXACTLY. The harness seed's in-place empty `playlistUrl`
  # / `epgUrl` would otherwise make the first restore differ by those two
  # keys and hide the defect (measured: both green on lane-key-y0 that way).
  seed "$KA"
  start_shell --playlist "$A" --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  logos() { qa_json_field "d['guide']['showLogos']" "$(ipc state)"; }
  ipc set showLogos true >/dev/null; wait_for true 10 logos >/dev/null || true
  ipc open '{}' >/dev/null; sleep 0.5
  ipc sourcesKey enter >/dev/null; sleep 0.3
  log_mark
  ipc sourcesKey g >/dev/null
  wait_for false 10 logos >/dev/null || true
  sleep 0.5
  off1="$(logos)/$(log_since 'updateEntryInline io')"
  ipc set showLogos true >/dev/null; wait_for true 10 logos >/dev/null || true
  log_mark
  ipc sourcesKey g >/dev/null
  wait_for false 10 logos >/dev/null || true
  sleep 0.5
  ck "Y1 in-app OFF, CLI showLogos true again, in-app OFF again: each OFF takes and is handed to the host (logos/entry writes)" \
     "off1:$off1 off2:$(logos)/$(log_since 'updateEntryInline io')" "off1:false/1 off2:false/1"
  # Y4 (round 10, R20d): two in-app toggles with NOTHING between them. The
  # round-9 data-loss lens's mutant S1b skipped a write whose patch equalled
  # the lagging host's publish, and that publish is still the entry from
  # before the first toggle -- so the second toggle was ignored (its own
  # child run: `#2: showLogos=True writes 2`), while Y1, which re-sets the
  # value from the CLI between the two, stayed green. ON needs the count
  # confirmed (the guide's own `g` then `confirm`), OFF does not.
  log_mark
  ipc sourcesKey g >/dev/null; sleep 0.3; ipc sourcesKey confirm >/dev/null
  wait_for true 10 logos >/dev/null || true
  sleep 0.5
  on1="$(logos)/$(log_since 'updateEntryInline io')"
  ipc sourcesKey g >/dev/null
  wait_for false 10 logos >/dev/null || true
  sleep 0.5
  ck "Y4 two in-app logo toggles in a row, ON then OFF with nothing between: the second takes and is handed to the host too (logos/entry writes)" \
     "on1:$on1 off2:$(logos)/$(log_since 'updateEntryInline io') stored:$(qa_json_field "d['storedShowLogos']" "$(ipc hostEntry)")" \
     "on1:true/1 off2:false/2 stored:false"
  ipc close >/dev/null
  seed "$KA"
  start_shell --playlist none --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  after=""
  for i in 1 2 3; do
    ipc set playlistUrl "$BAD" >/dev/null
    wait_for no 5 stored_has playlistUrl >/dev/null || true
    sleep 1.0
    after="$after$(stored_has playlistUrl) "
  done
  ck "Y2 the same refused (credentialed) playlistUrl set three times beside the active source: off the stored entry after EVERY set, the source still active" \
     "after:${after% } active:$(svc "['activeSourceKey']")" "after:no no no active:$KA"
  seed "$KA"
  start_shell --playlist "$A" --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  rec_epg() { sj "','.join({'$EPG': 'E', '$FORM_EPG': 'F', '': 'none'}.get(s.get('epgUrl', ''), 'other') for s in d['sources'] if s['key'] == '$1') or 'norecord'"; }
  ipc set epgUrl "$EPG" >/dev/null; wait_for E 10 rec_epg "$KA" >/dev/null || true; sleep 1.0
  ipc set epgUrl "$EPG" >/dev/null; sleep 1.5
  twice="$(rec_epg "$KA")/$(stored_has epgUrl)"
  res=$(ipc updateSource "$KA" "{\"epgUrl\": \"$FORM_EPG\"}")
  wait_for F 10 rec_epg "$KA" >/dev/null || true
  sleep 1.0
  seed_args=(--playlist none); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  [[ $(stored_has epgUrl) == yes ]] && seed_args+=(--epg "$EPG")
  stop_shell
  echo "   restarting over the entry as stored: epgUrl $([[ ${#seed_args[@]} -gt 4 ]] && echo '(the CLI value, as stored)' || echo none), sourceKey $seed_key"
  start_shell "${seed_args[@]}" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  sleep 0.5
  ck "Y3 the same epgUrl set twice for the active source is off the stored entry each time, the guide URL is then edited in the app to F, and F stands after a restart over the entry as stored" \
     "twice:$twice edit:$(qa_json_field "d['ok']" "$res") after:$(svc "['activeSourceKey']")/$(rec_epg "$KA")" "twice:E/no edit:true after:$KA/F"

  echo "== Q: the add form submitted, a CLI epgUrl set while its probe runs -- the LATER input wins, by time (R19c; the round-8 data-loss lens's P1-B) ($(elapsed) s)"
  # Lifted from the lens's race-child.sh. The probe is held open by a local
  # server that answers after 4 s; the CLI value is set 1 s after the
  # submit (Q1) or before it (Q2). Round 8 let the form's guide URL win
  # whenever it carried one, so in Q1 the LATER CLI value existed nowhere.
  # The server is this scenario's own: its pid is read from the LISTENER
  # (never `$!`), recorded for cleanup(), and killed by that pid.
  python3 - "$WORK/slow.port" "$D" >"$WORK/slow.log" 2>&1 <<'SLOW' &
import http.server, sys, time
body = open(sys.argv[2], "rb").read()
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(4)
        self.send_response(200); self.send_header("Content-Type", "audio/x-mpegurl"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
srv = http.server.HTTPServer(("127.0.0.1", 0), H)
open(sys.argv[1], "w").write(str(srv.server_address[1]))
srv.serve_forever()
SLOW
  SLOW_PORT=""; for ((i = 0; i < 50; i++)); do [[ -s $WORK/slow.port ]] && { SLOW_PORT=$(cat "$WORK/slow.port"); break; }; sleep 0.1; done
  SLOW_PID=""; for ((i = 0; i < 50; i++)); do SLOW_PID=$(ss -ltnp 2>/dev/null | grep ":$SLOW_PORT " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [[ -n $SLOW_PID ]] && break; sleep 0.1; done
  SLOW="http://127.0.0.1:$SLOW_PORT/slow.m3u"; KS_SLOW=$(key_of "$SLOW")
  echo "   slow listener on port ${SLOW_PORT:-none}, pid ${SLOW_PID:-none}"
  seed ""
  start_shell --playlist none --source-key "" || true
  res=$(ipc addSource "$SLOW" "$FORM_EPG" "")
  sleep 1.0
  ipc set epgUrl "$EPG" >/dev/null
  wait_for no 5 stored_has epgUrl >/dev/null || true
  during="$(held)/$(svc "['activeSourceKey']")"
  wait_for "$KS_SLOW" 20 svc "['activeSourceKey']" >/dev/null || true
  sleep 1.0
  ck "Q1 form first: the CLI epgUrl set while the probe runs is HELD; at the commit it (later) is on the new record over the form's, nothing held, nothing on the entry" \
     "ok:$(qa_json_field "d['ok']" "$res") during:$during active:$(svc "['activeSourceKey']") on:$(rec_epg "$KS_SLOW") held:$(held) epgUrl:$(stored_has epgUrl)" \
     "ok:true during:yes/ active:$KS_SLOW on:E held:no epgUrl:no"
  seed ""
  start_shell --playlist none --source-key "" || true
  ipc set epgUrl "$EPG" >/dev/null
  wait_for yes 10 held >/dev/null || true
  res=$(ipc addSource "$SLOW" "$FORM_EPG" "")
  wait_for "$KS_SLOW" 20 svc "['activeSourceKey']" >/dev/null || true
  sleep 1.0
  ck "Q2 CLI first (control): the held CLI value is EARLIER than the form submitted after it, so the form's guide URL stands, the held value is cleared and logged as superseded" \
     "ok:$(qa_json_field "d['ok']" "$res") active:$(svc "['activeSourceKey']") on:$(rec_epg "$KS_SLOW") held:$(held) epgUrl:$(stored_has epgUrl) logged:$(log_since 'supersede.*\(epgUrl\)|\(epgUrl\).*supersede')" \
     "ok:true active:$KS_SLOW on:F held:no epgUrl:no logged:1"
  kill_pid "$SLOW_PID"; SLOW_PID=""

  echo "== V: the EDIT form -- a guide URL typed in the app after a CLI value was held wins at the switch (R19c; the round-8 data-loss lens's P2) ($(elapsed) s)"
  # Lifted from the lens's aba-child.sh T=edit. With no source active the
  # CLI value is held; the user then edits A's guide URL to F in the app
  # (an EPG-only edit commits at once); the switch to A meets the held value
  # and the LATER one -- F -- stands. Round 8 replaced F with the earlier
  # held value at the switch, and F existed nowhere.
  seed ""
  start_shell --playlist none --source-key "" || true
  ipc set epgUrl "$EPG" >/dev/null
  wait_for yes 10 held >/dev/null || true
  wait_for no 5 stored_has epgUrl >/dev/null || true
  res=$(ipc updateSource "$KA" "{\"epgUrl\": \"$FORM_EPG\"}")
  wait_for F 10 rec_epg "$KA" >/dev/null || true
  res2=$(ipc switchSource "$KA")
  wait_for "$KA" 10 hf "['stored']" >/dev/null || true
  sleep 1.0
  ck "V1 E held, A's guide URL edited to F, then the switch to A: F (later) stands on A, nothing held, nothing on the entry" \
     "edit:$(qa_json_field "d['ok']" "$res") switch:$(qa_json_field "d['ok']" "$res2") active:$(svc "['activeSourceKey']") on:$(rec_epg "$KA") held:$(held) epgUrl:$(stored_has epgUrl)" \
     "edit:true switch:true active:$KA on:F held:no epgUrl:no"

  echo "== H: an EPG input whose state write FAILED, then a later in-app edit whose save LANDS (R19d, D-SRC-18) ($(elapsed) s)"
  # The board's D-SRC-18 at the sink. The adoption's save fails (the state
  # directory loses `w`, F's lever), so R11's drop leaves the input on the
  # entry; the directory comes back and the user edits the guide URL in the
  # app, which LANDS. Before R19d nothing then took the older input off the
  # entry, and the next start re-adopted it, seen "now", over the edit. The
  # landed save pays the mirror the failed one owed.
  seed "$KA"
  start_shell --playlist none --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  wait_for 0 10 pf "['stateSavesInFlight']" >/dev/null || true
  sleep 0.5
  chmod 0500 "$(dirname "$STATE")"
  ipc set epgUrl "$EPG" >/dev/null
  wait_for true 10 pf "['stateSaveFailed']" >/dev/null || true
  sleep 1.0
  failed="$(pf "['stateSaveFailed']")/$(stored_has epgUrl)"
  chmod 0700 "$(dirname "$STATE")"
  res=$(ipc updateSource "$KA" "{\"epgUrl\": \"$FORM_EPG\"}")
  wait_for F 10 rec_epg "$KA" >/dev/null || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 1.0
  landed="$(pf "['stateSaveFailed']")/$(stored_has epgUrl)"
  seed_args=(--playlist none); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  [[ $(stored_has epgUrl) == yes ]] && seed_args+=(--epg "$EPG")
  stop_shell
  start_shell "${seed_args[@]}" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  sleep 0.5
  ck "H1 the failed adoption left the input on the entry; the later edit's save landed and the owed mirror took it off; the restart stands on the edit F" \
     "failed:$failed edit:$(qa_json_field "d['ok']" "$res") landed:$landed after:$(svc "['activeSourceKey']")/$(rec_epg "$KA")" \
     "failed:true/yes edit:true landed:false/no after:$KA/F"

  echo "== P: the console sink, then teardown ($(elapsed) s)"
  qa_leak_on_labelled 'sourceProbeFinished|sourceSwitched|sourceRemoved|updateEntryInline' "://|$WORK" "$LOG"
  case $? in 0) left=clean ;; 1) left=LEAK ;; *) left="nothing labelled to judge" ;; esac
  ck "P1 no labelled harness-log line carries a URL or a fixture path" "$left" "clean"
  ck "P2 no credential token anywhere in the harness log" "$(qa_count 'u:p@|token=abc|harness-live-cred' "$LOG")" "0"
  h reap >/dev/null 2>&1; SHELL_STARTED=0
  for ((i = 0; i < 50; i++)); do kill -0 "$SHELL_PID" 2>/dev/null || break; sleep 0.1; done
  left=""; kill -0 "$SHELL_PID" 2>/dev/null && left="shell($SHELL_PID) "
  cage_stop
  ck "T1 the shell, the compositor and the nested socket are gone" "$left$STOP_VERDICT" "gone"
  echo "== shell arm done ($(elapsed) s)"
}

# ---- fixtures: four playlists with distinct channel counts, under $WORK so a
# path in any sink is this run's. Live URLs inside them are dead loopback
# ports; one carries a synthetic credential so P2 can tell a leak from a path.
mkdir -p "$WORK/fixtures"
sed "s|__LIVE__|http://harness-live-cred:secret@127.0.0.1:9/dead/live.m3u8|g" "$HERE/fixtures/harness.m3u.in" >"$WORK/fixtures/a.m3u"
cp "$ROOT/tests/fixtures/basic.m3u" "$WORK/fixtures/b.m3u"
python3 "$ROOT/scripts/gen-playlist.py" --channels 7 --groups 2 --seed 2 --out "$WORK/fixtures/c.m3u" >/dev/null 2>&1
python3 "$ROOT/scripts/gen-playlist.py" --channels 11 --groups 3 --seed 3 --out "$WORK/fixtures/d.m3u" >/dev/null 2>&1
A="$WORK/fixtures/a.m3u"; B="$WORK/fixtures/b.m3u"; C="$WORK/fixtures/c.m3u"; D="$WORK/fixtures/d.m3u"
EPG="http://u:p@127.0.0.1:9/epg.xml?token=abc&kind=x"
# Round 8: a value the plugin REFUSES (ftp://, with a credential P2 scans
# for) and a second guide URL, the one an add form carries (A2).
BAD="ftp://u:p@127.0.0.1:9/refused.m3u"
FORM_EPG="http://127.0.0.1:9/form-epg.xml?token=abc&kind=form"

instrument
[[ $MODE == live ]] && shell_arm

# The floor. A check that stops executing must turn the run red rather than
# quietly shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ *ck "[IS][0-9]' key-scenario.sh   -> 10, the instrument arm -> check-tree
#   grep -cE '^ *ck "[A-Z][0-9]' key-scenario.sh  -> 85, both arms          -> live
# (48 -> 61 on 2026-10-12, round 4: W1..W6 and F1..F7; 61 -> 63 the same
# day, round 5: L1, L2; 63 -> 70 the same day, round 7: U1..U7; 70 -> 78
# the same day, round 8: K1..K3, Z1..Z3, A1, A2; 78 -> 85 the same day,
# round 9: Y1..Y3, Q1, Q2, V1, H1; 85 -> 86 on 2026-10-12, round 10: Y4.)
# Every assertion is one `ck "<letter><n> ...` line, none in a loop; the
# probe's fallback `fail` lines replace the seven I lines one for one when
# the probe does not run, so the count holds either way; the definition of
# ck() does not match the recipe. Never lower a floor to make a run green.
# scripts/check.sh's KEY_PREFLIGHT_MIN is the check-tree number plus one
# (this line), and scripts/qa-lib-test.sh asserts every join.
if [[ $MODE == check-tree ]]; then
  EXPECTED_CHECKS=10
else
  EXPECTED_CHECKS=86
fi
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  pass "the scenario ran every check it has ($ran)"
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi

if [[ -n $BASELINE || -n $TREE ]]; then
  echo "baseline ${BASELINE:-$TREE}: on lane-key-y0 (round 8's code) the reds are round 9's -- U1, U2, U5, K1, K2, K3 (a guide URL with no source to land on waits on the ENTRY instead of being held in state.json), Y1, Y2, Y3 (after a publish A -> B -> A the lagging host's write is skipped: the in-app logo OFF, the strip of a re-set refused credential and of a re-set EPG input that the restart then puts back over an in-app edit), Q1 (a CLI epgUrl set while the add's probe runs exists nowhere), V1 (an earlier held value replaces a guide URL typed in the edit form) and H1 (D-SRC-18): 74 passed, 12 failed; A1, A2 and Q2 are its controls. The counts that follow were measured before Y, Q, V and H existed (78 lettered checks). On lane-key-w2 (round 7's code) the reds are round 8's -- K1 (the lagging host LOOPS on a refused playlistUrl beside a pending EPG: about 17,000 entry writes and 600 CPU ticks in 5 s), K3 (the echoing host loops on the same value wrapped in whitespace and keeps the credential), Z1, Z2 (a whitespace-wrapped CLI playlist removed comes back at the next start), Z3 (a whitespace-wrapped refused credential stays on the stored entry) and A2 (a pending CLI epgUrl replaces the add form's own guide URL): 73 passed, 6 failed; K2 and A1 are its controls. The counts that follow were measured before K, Z and A existed (70 lettered checks). On lane-key-v2 (round 6's code) the reds are round 7's -- U2, U3, U4 (the logo toggle's heal stripped an EPG no source had adopted, so the switch had nothing to land and the restart stands on A with no EPG) and U6, U7 (the same input lost by the switch alone on the echoing fake host): 66 passed, 5 failed. The counts that follow were measured before U existed (63 lettered checks). On lane-key-t2 (round 4's code) the reds are round 5's -- L1, L2 (the logo toggle on the failed disk mirrored the in-memory key and stripped the URL) and F6, F7 (the restart over that entry finds no record for B): 60 passed, 4 failed. On lane-key-s2 (round 3's code) round 4's join them -- D3, W3, W6 (no per-reason counter there), F3, F4, F5 (the dirsReady-route state write failing strips the URL, moves the mirror and loses the input): 54 passed, 10 failed. On lane-key-r2 (the tree D-SRC-15 was found on) D2, D3, W2, W3, W6, M1, M3, M5, C1..C5, E1, O5, O6 and the F and L reds: the start-up chmod reload replaces the adoption and the in-window switch/remove alike (D2 and W at the sink, D3 NOFIELD for want of a counter) and everything resting on a start-up adoption with it: 38 passed, 26 failed. On f275bde (the first build) O2 is the one discriminating red against every later tree (the entry rewritten while the save is parked); D2, M1, M3, M5 pass there by the accident the header describes: 39 passed, 25 failed. The two patches under spikes/key-mutations/ read 58 / 6 (D2, D3, W2, W3, W4, W6) and 59 / 5 (D2, W2, W3, W4, W6; D3 green) through --tree. N1..N4 are green on EVERY tree: the created-file shape never fires the reload. D1, M2, M4, M6, J1..J3, E2, E3, R1..R5, O1, O3, O4, P1, P2, T1 and every I and S check are controls; W1, W5, F1 and F2 are controls wherever the field they read exists (NOFIELD on f275bde and, for F1/F2, on lane-key-r2)."
fi
echo "key-scenario: $PASS passed, $FAIL failed (mode $MODE, tree $PLUGIN_ROOT${BASELINE:+, baseline $BASELINE}${TREE:+, prepared tree}, $(elapsed) s)"
(( FAIL == 0 ))
