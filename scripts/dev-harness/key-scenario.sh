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
#   key-scenario.sh [live] ... --only A,B19 a PARTIAL live run: the instrument arm, the
#                                           named shell-arm segments, then P and T1
#                                           (F-HARNESS-49; never a release count;
#                                           PRUNE is a rig that only --only runs)
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
#       state is applied only on the helper's word that nothing was at the
#       path (R22a), and the entry's URL is adopted (it used to be observed
#       parked before the dirs were ready: a control, re-pointed in round 12)
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
#   G1  the first start over the 0.13.5 shape writes the migration MARKER
#       (entryMigrated) in the same state write as the adoption     <- R21a
#   G2  ... the service saw it land, holds it, and reported nothing
#   G3  ... the entry was stripped after the landing
#   G4  the REAL 0.13.6 helper (v0.13.6 tag) rewrites the file without the
#       marker and without activeKey: the downgrade the ruling accepts
#   G5  ... and the re-upgrade over 0.13.6's entry migrates again
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
#   F1  the state write FAILS (round-3 review P1, R13; R21a): the state
#       directory unwritable BEFORE the start, so the start's own migration
#       write fails and the marker never lands -- configured on A, failure
#       recorded once, nothing in flight (control)
#   F2  a playlistUrl set mid-session is therefore still a MIGRATION input:
#       adopted in memory on the dirsReady route and its state write
#       FAILED: failure recorded, nothing in flight, nothing held (control:
#       the rig made the write fail at all)
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
#   U1  two saved sources, NONE active, an epgUrl on the entry at the
#       migration: REPORTED once (no-source), off the stored entry, on no
#       record, nowhere in the state file -- never held  <- R21c (R12 kept
#       it on the entry, R19b in the state; both withdrawn)
#   U2  the logo toggle heals and nothing comes back, no second report
#   U3  a switch to A lands nothing on A
#   U4  a restart over the entry as stored stands on A with no guide URL
#   U5  the same rig on the ECHOING fake host (run.sh --host echo): the
#       lever took; reported once, off both sides (control)
#   U6  a switch on the echoing host lands nothing either
#   U7  a restart over that (echoing host) stands on A with no guide URL
#   K1  the lagging host, a REFUSED playlistUrl beside a guide URL with no
#       source (the migration): the shell SETTLES -- at most 2 entry writes
#       and 50 CPU ticks in a 5 s window -- both reported once and off the
#       stored entry (R21c)              <- R18b, the round-7 data-loss P1-B
#   K2  the same entry on the ECHOING host settles (control)
#   K3  the echoing host with the refused value WRAPPED IN WHITESPACE
#       settles and drops it                          <- R18a, P1-A's loop
#   Z1  after the marker, a whitespace-wrapped CLI playlist set while the
#       shell was down is REFUSED: no record, reported once, off the entry
#                                             <- R18a's normaliser, R21b
#   Z2  the restart over that resurrects nothing
#   Z3  a whitespace-wrapped REFUSED credential beside a working source
#       leaves the stored entry; the source stays active   <- R18a, P1-A
#   A1  a refused CLI epgUrl, then an in-app add (harness addSource) with no
#       form EPG: the new record holds none   <- the probe commit, live
#   A2  the same add with the form's OWN guide URL: that one and nothing
#       else                                   <- R21b (R18d, R19c withdrawn)
#   Y1  on the lagging host: in-app logo OFF, CLI showLogos true again (a
#       publish A -> B -> A), in-app OFF again -- each OFF takes and is
#       handed to the host               <- R19a, the round-8 lenses' P1-A
#   Y4  two in-app toggles in a row (ON, then OFF, nothing between): the
#       second takes and is handed to the host too
#                           <- R20d, the round-9 lens's mutant S1b, live
#   Y2  the same refused credential set three times beside the active
#       source is off the stored entry after EVERY set, reported once
#                                                           <- R19a, R21b
#   Y3  the same epgUrl set twice is refused each time (on no record), the
#       guide URL is then edited in the app, and the edit stands after a
#       restart                                             <- R19a, R21b
#   Q1  the add form submitted, THEN a CLI epgUrl set while its probe runs
#       (a slow local server): refused, the form's guide URL stands
#   Q2  the CLI value first (refused), THEN the add form: the form stands
#                                         <- R21b (R19c's time rule withdrawn)
#   V1  a refused CLI value, then A's guide URL edited in the app, then the
#       switch to A: the edit stands, the CLI value nowhere      <- R21b
#   H1  a MIGRATION guide URL whose state write FAILED stays on the entry;
#       a later in-app edit's save LANDS (the marker with it) and the owed
#       mirror takes it off, so the restart stands on the edit
#                                                  <- R19d, D-SRC-18, R21a
#   X1  AFTER the marker, a playlistUrl set while the shell was down is
#       REFUSED: never adopted, reported once, off the stored entry <- R21b
#   X2  an epgUrl set mid-session: refused, reported, off the entry
#   X3  the same value again: refused, NOT reported a second time
#   X4  a whitespace-wrapped refused credential: refused, reported, off
#   X5  the notification SINK: one notification per report, each naming the
#       Sources screen, none carrying a URL
#   X6  the echoing host: refused, reported once, off both sides
#   B1  a MIGRATED install whose state.json is 0000 at the start: the helper
#       restores 0600 and the start READS it -- records, key and marker
#       survive, nothing reported          <- R22a, the round-11 lens's P1
#   B2  ... and a second, ordinary start stands on both records
#   B3  the state DIRECTORY 0000 at the start (FileView: FileNotFound): the
#       helper found the file, restored 0700, the start read it -- records,
#       cache layout and marker survive    <- R22a, the sibling 0.13.6 has
#   B4  ... and a second, ordinary start stands on both records
#   B5  a state.json that does not parse: nothing written over it, an in-app
#       add and switch refused, the user told ONCE (the notification names
#       the file, no URL)                  <- R22a, the no-write mode
#   B6  ... the bar entry left EXACTLY as it is
#   B7  restoring the file lifts the mode; a switch then lands
#   B8  the guide's fetch-failure hint, as drawn, names the Sources screen
#       and no retired setting                                   <- R22c
#   B9  two no-write episodes in one session, no own save between: the
#       second is told again, an in-app add in it refused       <- R23a
#   B10 a start-up init that never answers is stopped by the watchdog and
#       reaped (no process left), and the held load decides as the
#       no-write mode, "init-timeout", told once                <- R23c
#   B11 a no-write START draws its own surface in the notification's own
#       words, not the first-run form                     <- R23e, R23h
#   B12 ... and the logo toggle's refusal there says the no-write reason,
#       not "try omarchy bar set"                                <- R23f
#   B13 a fresh install's drawn copy is the first-run form's    <- R23h
#   B14 a FIFO at state.json: the init answers at once, the start blocks
#       as not-a-file, no helper left running                    <- R23b
#   B15 a no-write START's Sources screen: the notice's title in its header,
#       no Add rows, no add hint, `a` opens no form              <- R24f
#   B16 the FRESH install's first session (state directory absent at the
#       first load) sees a hand-run `state source add`, keeps it through the
#       next in-app save, and notices garbage written in place  <- R24c
#   B17 a start-up init that IGNORES the TERM is KILLed and reaped <- R24g
#   B18 a shell stopped 5 s into a held init leaves it running, and the
#       init's own deadline ends it                              <- R24d
#   B19 R24a live: an in-app change held by a failed save, two hand edits
#       in place in that window (a favourite added, then removed), a
#       hand-run helper write, a second in-app change -- both in-app
#       changes and the helper's favourite kept, the removed one stays
#       removed, through a restart                   <- R25d, F-HARNESS-26
#   B20 a backup copied from the plugin's own file after its save landed,
#       put back after an in-app remove landed: the restore wins, through
#       the next save and a restart                          <- R25a, D-SRC-30
#   B21 the EXISTING-folder session damaged after an own save landed: the
#       garbage is noticed, told once                 <- R25d, D-DOC-9's half
#   B22 ... and the Sources header there says saving has stopped <- D-SRC-38
#   PRUNE (a RIG that only `--only PRUNE` runs: never in a full run, no check)
#       an add made while the start-up init is held, then the start-up
#       prune: prints what is left of the added source's cache
#                                    <- the start-up prune race, D-SRC-69 (F-HARNESS-49)
#   P1  no labelled harness-log line carries a URL or a fixture path
#   P2  no credential token anywhere in the harness log
#   T1  the shell, the compositor and the nested socket are gone (by pid)
#
# ROUND 11, R21 (the product owner's decision of 2026-10-13). The bar
# entry's `playlistUrl` and `epgUrl` are read ONCE, by the migration, until
# a state write carrying the migration marker (`entryMigrated`) has LANDED;
# after that a value found there is refused, reported once and stripped.
# Ten repair rounds of state built to tell a CLI input from the host's
# stale publish of one did not converge, and every P1 from round 3 on was a
# URL arriving on the entry from the command line. So the segments that
# adopted a CLI value mid-session (F, H) now do it inside a migration that
# has not landed (the state directory unwritable from the start), the ones
# that observed R12/R17b/R18d/R19b/R19c's held guide URL (U, K, A, Q, V)
# observe the refusal instead, and G and X observe the marker and the
# refusal at the sink. The seed writes the marker only when a segment says
# `migrated`; otherwise every start is a migration, which is what D, N, M,
# J, C, E, R, O, W, L and Y1 assert as before.
#
# ROUND 12, R22 (the lead's ruling on the round-11 lenses). A STATE THAT DID
# NOT LOAD IS NEVER WRITTEN. The round-11 data-loss lens found, live on both
# host shapes, that a migrated install whose state.json could not be read at
# the start had an empty state written over it -- every source, credential
# and favourite gone -- and that a state DIRECTORY that cannot be entered did
# the same through the cache layout's save, on every tree since D-SINK-19
# began and on 0.13.6 (re-measured live on dev 4740a50 this round). B lifts
# the lens's lf-child.sh for both, and adds the no-write mode (B5..B7) and
# R22c's hint (B8). What Quickshell's FileView reports for each case was
# measured first, and is in Model.STATE_LOAD_ERRORS' comment: the
# unreadable directory reads as FileNotFound, exactly like a fresh install,
# which is why the helper's `state init` now reports what it FOUND.
# Measured on lane-key-n1 (4fdb37c) under the scenario's own nested cage,
# with a private session bus, transcripts key-20261013-161816 and -162220:
#   lane-key-n1 (round 12's code):                106 passed,  0 failed
#   --baseline lane-key-m2 (round 11's code):      97 passed,  9 failed
#       B1..B8 (the loss itself: `records:0` after B1's start and B3's;
#       B5's garbage replaced, an add accepted, the mirror moved; B8's hint
#       `check playlistUrl`), and N1 for its new field alone.
# THE UNIT. Every "N passed, M failed" in this file, header and footer, is
# THE SUMMARY LINE'S: what `key-scenario: N passed, M failed` prints at the
# end of a run, which counts the floor line's PASS as well as the lettered
# checks (so a green run reads one more than the floor). Round 12 wrote the
# two lines above in lettered checks (105 / 0, 96 / 9) and its footer in
# summary counts (97 / 9), with only a parenthesis to say which (R23h).
# A "(N lettered checks)" or "N-check harness" in the footer is a different
# quantity, the size of the harness then, and says so.
#
# ROUND 13, R23 (the lead's ruling on the round-12 lenses). The no-write
# mode's loose ends, B9..B14 above: the lift's re-arm of the notice that
# nothing checked (the data-loss lens deleted it and read 0 red), the
# start-up init that a FIFO at state.json held for ever (now a non-blocking
# open in the helper, R23b, and a 15 s watchdog in the service, R23c), the
# first-run form a no-write start drew, the logo toggle's wrong refusal, and
# the drawn-copy fields that read the hidden empty state. B10 holds the
# init with O's slow tree (60 s) over a file that does not parse, so the
# load waits on the init; its pid is read from /proc by exact argv
# (init_pids), never by a pattern over a command line. The red runs are
# lane-key-n2 (--baseline) and the kept mutation r23a-no-rearm.patch
# (--tree), both in the footer.
#
# ROUND 14, R24 (the lead's ruling on the round-13 lenses). B15..B18 above.
# B16 is the session the round-13 live lens measured as never reloading --
# the production fresh shape, the state directory absent at the first load
# -- now re-armed by one stateFile.reload() after the start-up check
# (measured first, spikes/filewatch set r24). B18 holds the init INSIDE the
# real helper (slow-helper.py OMARCHY_IPTV_SLOW_AT=inside), so the verb's
# own SIGALRM deadline is what is observed; the held init was reparented to
# the user's service manager when the shell stopped, as the lens saw.
# Measured on lane-key-q1 at 318af7f under this harness, each in its own
# nested cage on a private bus (scripts/dev-harness/private-bus.sh,
# harness directories /run/user/1000/omarchy-iptv-q1-<n>, removed after),
# summary counts (THE UNIT above):
#   lane-key-q1 forward:                          116 passed, 0 failed
#       (transcript key-20261014-095236-969838)
#   --baseline dev (ced1bd1, round 13's code):    113 passed, 3 failed
#       (key-20261014-095838-996891)
#       B15 (`header:[No sources] rows:2 after-a:sourceEdit says:other`),
#       B16 (`seen:0 file:D blocked: told:0`: the helper's record unseen
#       and written over, the garbage unnoticed) and B18 (the held init
#       `after-deadline:alive(<pid>)`, killed by cleanup); B17 is GREEN
#       there, round 13 having the KILL, so it is seen red through
#   --tree with spikes/key-mutations/r24g-no-kill.patch: 115 passed, 1
#       failed, B17 (`blocked: helper:no(<pid>) left:<pid> told:0`;
#       key-20261014-100528-1027361).
#
# ROUND 15, R25 (the lead's ruling on the round-14 lenses). B19..B22 above.
# B19 is the first live observation of R24a's merge (the round-14 data-loss
# lens's a5 and a7 survived every check; a5 is driven here by two hand
# edits IN PLACE inside one held window -- a 0600 file needs no directory
# `w`, so the in-app save keeps failing while they land -- and a7 is pinned
# in node, its window being milliseconds wide). B20 is R25a's restore, red
# on dev. B21 is the existing-folder shape the round-14 lanes left to the
# spike, seen red through r25d-no-reload-on-change.patch; B22 is D-SRC-38,
# red on dev. Measured on lane-key-k1 under this harness, each in its own
# nested cage on a private bus (harness directories
# /run/user/1000/omarchy-iptv-kk1-<n>, removed after), summary counts:
#   lane-key-k1 forward (b10b5b6):                120 passed, 0 failed
#       (key-20261014-143514-1482764)
#   --baseline dev (002662d, round 14's code):    118 passed, 2 failed
#       (key-20261014-144201-1513141): B20 (`restored:1 records:1 ...
#       restart:1`, the restore ignored as own-write and written over) and
#       B22 (`header:Saved sources not loaded rows:2`)
#   --tree with r25d-a5-base-not-moved.patch:      119 passed, 1 failed
#       (key-20261014-144904-1545059): B19 (`merged:2 ... favs:
#       t:helper.uk,t:h3.uk`, the hand edit's removal ignored and written back)
#   --tree with r25d-no-reload-on-change.patch:    110 passed, 10 failed
#       (key-20261014-151410-1653892): B21 (`blocked: told:0`) with D3, W3,
#       W6, B7, B9, B16, B19, B20 and B22, every segment that needs a
#       reload. Its first run outlived the cage's 500 s lifetime (1007 s;
#       B19..B22 NOSTATE), which is why cage_start is now handed 1500.
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
# dirty check. R19b held a guide URL no record could take in state.json
# (pendingEpg { url, seenAt }), and R19c let the latest explicit input win
# by time (seenAt against the record's epgSetAt). [R19b and R19c WITHDRAWN
# 2026-10-13 by R21 and deleted from the model and the helper, with every
# field they wrote; U, K, A, Q and V observe the refusal instead -- no
# segment reads `held:` any more.] R19a and R19d stand: R19d, a mirror a
# failed save withheld is paid by the next save that lands, is what H
# observes.
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
# write). R17b: switchSource and the probe commit adopted a pending EPG onto
# the newly active record in the same turn (adoptPendingEpg, then in
# model/source-records.mjs), before the save and before the mirror.
# [WITHDRAWN 2026-10-13 by R21, the product owner's decision, and deleted
# from the model: R17a's consumed-input keep became the migration marker's
# (Model.retiredInputsToKeep over the LANDED marker), and R17b's adoption of
# a pending guide URL is gone with the pending guide URL itself. U is
# re-pointed at R21c -- a guide URL with no source to guide, at the
# migration, is reported once and stripped; the paragraph above is the
# round-7 record, not the code.] The entry's values are never read here:
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
# applied -- and is never removed by this scenario.
# `--only SEG[,SEG]` (F-HARNESS-49, 2026-10-27) runs the instrument arm, the
# named shell-arm segments and then P1, P2 and T1, and nothing else: a ten
# minute run to look at two checks was what made bisecting A2 and watching
# B19 cost an hour a sample. The names are the blocks it was made for, `A`
# (A1, A2) and `B19`, and `PRUNE`, a RIG that only --only runs (no check:
# it prints what the start-up prune leaves of an add, D-SRC-69);
# nothing else is accepted: a segment that leans on an earlier one's state
# cannot be cut loose by a flag without being checked, so a new name is
# added only with a run that shows it stands alone. A full run is untouched
# by it -- every block it does not name is `if [[ -z $ONLY ]]` or `if
# seg_on X`, both true when the flag is absent, PRUNE's is false then, and
# the counts are the same lines -- and a partial run cannot be read as one:
# its floor is the selected blocks' own (ONLY_CHECKS below, pinned to the
# ck lines between each block's markers by tests/test_key_scenario_only.py),
# and its summary line says `PARTIAL (only ...)`. Refused with check-tree.
# check-tree needs node
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
BASELINE=""; TREE=""; ONLY=""
while (( $# )); do
  case $1 in
    --only)
      [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--only needs a segment list (A, B19, PRUNE, comma separated), and got '${2:-}'" >&2; exit 2; }
      ONLY=$2; shift ;;
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
# F-HARNESS-20: this driver's own processes (its helper runs, probes, mpv)
# get the harness's HOME as well, not only what run.sh starts. Exports only.
qa_harness_home "$SCRATCH" || exit 2
PLUGIN_ROOT=$ROOT
EXPORT_DIR=""
TREE_LINE="== tree $ROOT ($(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git))"
# The levers' refusals sit ABOVE the transcript (rewind-scenario.sh's shape,
# pinned by scripts/qa-lib-test.sh): a mistyped lever is one line on stderr
# and no file. --tree is a directory the caller prepared and keeps.
[[ -n $BASELINE && -n $TREE ]] && { echo "--baseline and --tree are the same lever; pass one" >&2; exit 2; }
# F-HARNESS-49: --only, refused above the transcript like the other levers.
# How many lettered checks each selectable block holds (its ck lines, which
# tests/test_key_scenario_only.py counts between the block's markers).
declare -A ONLY_CHECKS=([A]=2 [B19]=1 [PRUNE]=0)
if [[ -n $ONLY ]]; then
  [[ $MODE == check-tree ]] && { echo "--only selects shell-arm segments; check-tree runs the instrument arm alone" >&2; exit 2; }
  IFS=, read -r -a only_names <<<"$ONLY"
  for seg in "${only_names[@]}"; do
    [[ -n $seg && -n ${ONLY_CHECKS[$seg]:-} ]] || { echo "--only: '$seg' is not a selectable segment (A, B19, PRUNE)" >&2; exit 2; }
  done
  unset seg only_names
fi
# Is block $1 in this run? Every block, when --only is absent.
seg_on() { [[ -z $ONLY || ",$ONLY," == *",$1,"* ]]; }
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
  # S4 (R29e): init_pids answers THIS run's start-up init and no other's.
  # Two stand-ins with the helper's exact argv shape run the same path, one
  # with this run's state folder and one with another's; only the first may
  # be named. Red on the unscoped scanner (both pids, round 2's B14 red in
  # miniature). The stand-ins are this shell's own children, killed by the
  # pids recorded here.
  local s4fake="$WORK/s4-helper.py" s4mine="$WORK/s4-mine/omarchy-iptv" s4theirs="$WORK/s4-theirs/omarchy-iptv" s4a s4b s4got s4i
  printf 'import time\ntime.sleep(30)\n' >"$s4fake"
  python3 "$s4fake" state --state-dir "$s4mine" init & s4a=$!
  python3 "$s4fake" state --state-dir "$s4theirs" init & s4b=$!
  for ((s4i = 0; s4i < 100; s4i++)); do
    [[ $(tr '\0' ' ' <"/proc/$s4a/cmdline" 2>/dev/null) == *" init "* && $(tr '\0' ' ' <"/proc/$s4b/cmdline" 2>/dev/null) == *" init "* ]] && break
    sleep 0.05
  done
  s4got=$(init_pids "$s4fake" "$s4mine")
  kill -TERM "$s4a" "$s4b" 2>/dev/null; wait "$s4a" "$s4b" 2>/dev/null
  ck "S4 init_pids names this run's start-up init only (its own state folder), never another harness's over the same helper path" \
     "$([[ $s4got == "$s4a" ]] && echo mine || echo "got:${s4got:-none} mine:$s4a theirs:$s4b")" "mine"
  echo "== instrument arm done ($(elapsed) s)"
}

# ------------------------------------------------------------ the shell arm
# F-HARNESS-45: the nested cage renders with pixman, so a player started toward
# it gets run.sh's software-GPU lever (harness_env appends --gpu-sw=yes and
# --ao=null to the mpvArgs). Since D-PLY-27 the base argv carries --gpu-sw=yes
# itself, so on this tree the lever's job is --ao=null (the cage's player stays
# off the user's sound server); on an older tree, such as a --baseline ref
# through 0.15.0, mpv 0.41.0 aborts in its VO probe without it.
h()    { env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" OMARCHY_IPTV_HARNESS_SOFTWARE_GPU=1 "$RUN" "$@"; }
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
# The records holding the bar's guide URL $EPG, by key ("none" for none),
# and whether that URL is anywhere in state.json's text. Compared inside
# python, never printed. Defined in U until F-HARNESS-49, and A reads them,
# so `--only A` would have called neither.
epg_on() { sj "','.join(sorted(s['key'] for s in d['sources'] if s.get('epgUrl') == '$EPG')) or 'none'"; }
infile() { python3 -c 'import sys; print("yes" if sys.argv[2] in open(sys.argv[1]).read() else "no")' "$STATE" "$EPG" 2>/dev/null || echo NOFILE; }
# The key of a URL or path, by the tree under test's own function.
# The tree's model through qa_model_files (D-REL-5): its first file is what
# node requires, the aggregator or a pre-split tree's Model.js.
key_of() { node -e 'const M = require(process.argv[1]); const n = M.normalizeSourceUrl(process.argv[2], { origin: "cli" }); process.stdout.write(n === "" ? "" : M.sourceKey(n))' "$(qa_model_files "$PLUGIN_ROOT" | head -n 1)" "$1"; }
# Does the stored entry carry a key NAME? yes | no (names, never values).
stored_has() { qa_json_field "'yes' if '$1' in d['storedKeys'] else 'no'" "$(ipc hostEntry)"; }
published_has() { qa_json_field "'yes' if '$1' in d['publishedKeys'] else 'no'" "$(ipc hostEntry)"; }
# R21. Is the migration marker in the state the service last saw LAND
# (pointerState's derived `landedMigrated`; NOFIELD on a tree without one)?
landed() { pf "['landedMigrated']"; }
# D-SRC-64 (round 7, 2026-10-22): the pair a migration HELD at the cap parks
# in the state, `migrationPending: { playlistUrl, epgUrl }`, which is where
# the entry's URL goes when the hold's own write strips the entry (the R21
# oracle: an entry URL ends in a record, in the parked pair, or is reported).
# Read two ways and folded into one answer, URL never printed (rule 5):
# the helper's `state show` over THIS run's scratch state folder -- the
# shipping read, whose public_state prints the pair as hosts only, so a
# fixture path reads "local file" there and cannot tell D's URL from any
# other path -- and the file itself through sj, COMPARED with the URL the
# check hands in. `yes` when the helper names a host for $1 and the file
# holds exactly $2 in it; NOFIELD when neither side has a pair (the key is
# absent, which is the want once the migration has landed: the pair is
# dropped in the write that sets the marker, and the two never coexist);
# otherwise what each side said, `<host-or-NOFIELD>|<yes|no|NOFIELD>`, so
# a red names the side. A want of `yes` cannot be met by a missing pair.
# $1 is playlistUrl or epgUrl; $2 the URL or path it must hold.
parked_is() {
  local field=$1 url=$2 hostkey host disk
  [[ $field == epgUrl ]] && hostkey=epgHost || hostkey=host
  host=$(qa_json_field "d['state']['migrationPending']['$hostkey'] or 'NOFIELD'" "$(python3 "$PLUGIN_ROOT/bin/omarchy-iptv" state --state-dir "$(dirname "$STATE")" show 2>/dev/null)")
  disk=$(sj "'yes' if d['migrationPending']['$field'] == '$url' else 'no'")
  if [[ $host != NOFIELD && $host != NOSTATE && $disk == yes ]]; then echo yes
  elif [[ $host == NOFIELD && $disk == NOFIELD ]]; then echo NOFIELD
  else echo "$host|$disk"; fi
}
# What the session REPORTED off the bar entry, as setting:reason pairs in
# order ("-" for none), and how many: names and reasons only, never a value
# (HarnessLib.pointerStateOf's entryInputReports; NOFIELD on a tree without).
reports() { qa_json_field "','.join(r['setting'] + ':' + r['reason'] for r in d['entryInputReports']) or '-'" "$(ipc pointerState)"; }
n_reports() { qa_json_field "len(d['entryInputReports'])" "$(ipc pointerState)"; }
# The notification SINK: the stand-in omarchy-notification-send that
# shell_arm puts in front of PATH appends its argv to this file, one line a
# notification. Counted by the refusal's replace id (74016), never read for
# a value the scenario prints.
NOTIFY_LOG=""
notified() { qa_count ' 74016 ' "$NOTIFY_LOG"; }
sha() { sha256sum "$1" 2>/dev/null | cut -c1-16; }
# R23b / R23c: the pids of every process anywhere running `state ... init`
# through the helper at $1, read from /proc by EXACT argv: argv[1] is that
# path and `init` is an argument. The scanner's own argv[1] is `-c`, so it
# cannot match itself (CLAUDE.md parallel rule 3); a pid is never matched by
# a pattern over a command line.
# R29e (2026-10-20, round 2's live review, P3): and only THIS scenario's --
# `--state-dir $2` in the argv, the folder the service hands its init
# (Service.qml's stateInitProc), which is under this run's own scratch. A
# second harness driving the same tree's helper at the same moment read as
# `left:<its pid>` in B14, and the reaps after B10 and B18 KILL what this
# returns, so an unscoped answer could kill another run's helper. The state
# folder is required; without it nothing matches.
init_pids() {
  python3 -c '
import os, sys
want = sys.argv[1]
state_dir = sys.argv[2] if len(sys.argv) > 2 else ""
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    try:
        argv = open("/proc/%s/cmdline" % pid, "rb").read().split(b"\0")
    except OSError:
        continue
    argv = [a.decode("utf-8", "replace") for a in argv if a]
    if not state_dir or "--state-dir" not in argv[3:-1] or argv[argv.index("--state-dir", 3) + 1] != state_dir:
        continue
    if len(argv) > 2 and argv[1] == want and argv[2] == "state" and "init" in argv[3:]:
        print(pid)' "$1" "${2:-}" 2>/dev/null | tr '
' ' ' | sed 's/ $//'
}
# Model.stateUnreadableNotice(reason, path)[field] from the TREE UNDER TEST's
# model, so the check compares the guide with the notification's own words.
notice_of() { node -e 'const M = require(process.argv[1]); process.stdout.write(String(M.stateUnreadableNotice(process.argv[2], process.argv[3])[process.argv[4]]))' "$(qa_model_files "$PLUGIN_ROOT" | head -n 1)" "$1" "$2" "$3"; }
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
# F-HARNESS-49. The shell's own helper children that can UNDO what a segment
# is about to stage: a `cache` job (the start-up prune, queued when the cache
# layout is ready and run when the dirs are, removes every sources/<key> no
# record named when it was QUEUED -- an in-app add's probe directory among
# them, which is how A2 lost its add on 2026-10-27: the start-up prune
# race, D-SRC-69, a product finding of its own found under F-HARNESS-49) and
# `state ... mode` (D-SRC-49: after every save that LANDS the helper puts
# the state folder back to 0700 -- B19's and B30's 0500 among them, which is
# how B19 lost its hold). Read from /proc/<shell>/task/*/children by EXACT
# argv -- argv[1] this tree's helper, argv[2] the verb -- for the recorded
# shell pid only, never by a pattern over a command line (parallel rule 3).
# Prints the verbs it found ("cache", "mode"), nothing when there is none.
helper_jobs() {
  python3 -c '
import os, sys
shell, helper = sys.argv[1], os.path.realpath(sys.argv[2])
kids = []
try:
    tids = os.listdir("/proc/%s/task" % shell)
except OSError:
    tids = []
for tid in tids:
    try:
        kids += open("/proc/%s/task/%s/children" % (shell, tid)).read().split()
    except OSError:
        pass
found = []
for kid in kids:
    try:
        argv = [a.decode("utf-8", "replace") for a in open("/proc/%s/cmdline" % kid, "rb").read().split(b"\0") if a]
    except OSError:
        continue
    # the helper itself, or the real one that a staged slow tree wrapper execs
    if len(argv) < 3 or os.path.realpath(argv[1]) not in (helper, helper + ".real"):
        continue
    if argv[2] == "cache":
        found.append("cache")
    elif argv[2] == "state" and argv[-1] == "mode":
        found.append("mode")
print(" ".join(sorted(found)))' "${SHELL_PID:-0}" "${OMARCHY_IPTV_PLUGIN_ROOT:-$PLUGIN_ROOT}/bin/omarchy-iptv" 2>/dev/null
}
# A start SETTLED: the dirs ready, no state save parked or in flight, and no
# helper job above running -- five reads in a row, 0.1 s apart, because a
# landed save asks for `state mode` from a turn of its own and one quiet
# read can fall between the two. start_shell returns at stateLoaded and
# cacheReady, which is BEFORE the start-up init has made the dirs ready and
# so before the prune has run and before the start's own save has landed
# and been repaired. Bounded at 15 s, and says when it gave up (rule 3).
wait_settled() {
  local i quiet=0 ps
  for ((i = 0; i < 150; i++)); do
    ps=$(ipc pointerState)
    if [[ $(qa_json_field "d['dirsReady'] and not d['stateSavePending'] and d['stateSavesInFlight'] == 0" "$ps") == true && -z $(helper_jobs) ]]; then
      quiet=$((quiet + 1)); (( quiet >= 5 )) && return 0
    else
      quiet=0
    fi
    sleep 0.1
  done
  echo "   gave up after 15 s waiting for the start to settle (helper jobs: [$(helper_jobs)])"
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
# R21 (round 11): `seed <key> migrated` writes the migration marker too --
# a file the migration has already written, over which nothing on the bar
# entry is an input. Without it the seed is a file the migration has NOT
# written (0.13.x, or a downgrade's), and the start migrates.
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
  [[ ${2:-} == migrated ]] && extra="$extra,\"entryMigrated\":true"
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

# The slow tree: the tree under test copied to $1 with its helper replaced by
# fixtures/slow-helper.py, which holds the verbs OMARCHY_IPTV_SLOW_VERBS names
# for OMARCHY_IPTV_SLOW_MS and then execs the real helper (bin/omarchy-iptv.real)
# with the same argv. O stages it (and B10, B17, B18 and the disk-gone tree
# reuse O's); PRUNE stages its own, O not running in a partial run. Lifted out
# of O on 2026-10-27 (F-HARNESS-49), every line as it was there. Fails when
# anything could not be copied.
stage_slow_tree() {
  local tree=$1 staged=1
  mkdir -p "$tree/bin"
  for f in manifest.json Service.qml Guide.qml BarWidget.qml; do cp "$PLUGIN_ROOT/$f" "$tree/$f" 2>/dev/null || staged=0; done
  # The model is every file qa_model_files names (Model.mjs and its parts since
  # D-REL-5, or a pre-split tree's Model.js), each at its own relative path:
  # rewind-scenario.sh's R16 stages its slow tree the same way.
  local -a model_files=(); local mf rel
  mapfile -t model_files < <(qa_model_files "$PLUGIN_ROOT")
  (( ${#model_files[@]} > 0 )) || staged=0
  for mf in "${model_files[@]}"; do
    rel=${mf#"$PLUGIN_ROOT/"}
    mkdir -p "$tree/$(dirname "$rel")" && cp "$mf" "$tree/$rel" 2>/dev/null || staged=0
  done
  cp -R "$PLUGIN_ROOT/contrib" "$tree/contrib" 2>/dev/null || true
  cp "$PLUGIN_ROOT/bin/omarchy-iptv" "$tree/bin/omarchy-iptv.real" 2>/dev/null || staged=0
  # D-REL-7: the helper is a stub and the parts it names, and the stub finds
  # them in bin/helper/ beside itself whatever it is called, so they are
  # copied there too (none for a tree from before the split).
  local -a helper_parts=(); local hp
  qa_helper_parts "$PLUGIN_ROOT" >/dev/null || staged=0
  mapfile -t helper_parts < <(qa_helper_parts "$PLUGIN_ROOT")
  for hp in "${helper_parts[@]}"; do
    mkdir -p "$tree/bin/helper" && cp "$hp" "$tree/bin/helper/" 2>/dev/null || staged=0
  done
  cp "$HERE/fixtures/slow-helper.py" "$tree/bin/omarchy-iptv" 2>/dev/null || staged=0
  chmod +x "$tree/bin/omarchy-iptv" "$tree/bin/omarchy-iptv.real" 2>/dev/null || true
  (( staged ))
}

shell_arm() {
  local i left before window orphan seed_playlist seed_key sha0
  echo "== shell arm: the real Service.qml under cage (plugin tree $PLUGIN_ROOT) ($(elapsed) s)"
  # The nested compositor's lifetime is an upper bound only (cage_stop ends
  # it). Round 15: 500 s was outlived by a mutated tree whose earlier waits
  # all time out -- r25d-no-reload-on-change.patch ran 1007 s and every
  # segment after the cage's end read NOSTATE, a red for the wrong reason --
  # and the forward run itself reached 425 s with B19..B22. So 1500 s, inside
  # private-bus.sh's 2400 s.
  cage_start 1500
  # The stub compositor in front of PATH, as pip- and clip-scenario.sh do
  # it, and HYPRLAND_INSTANCE_SIGNATURE unset: the service's hyprctl probe
  # stops at `which`, and nothing can reach the user's compositor from here.
  mkdir -p "$SCRATCH/bin" && ln -sfn "$HERE/stub-hyprctl.py" "$SCRATCH/bin/hyprctl"
  # R21b's report is a desktop notification (Service.notify ->
  # Quickshell.execDetached). The shell resolves the command through PATH,
  # which harness_env puts $SCRATCH/bin in front of, so this stand-in
  # receives it instead of the user's notification daemon -- and it is the
  # SINK the X checks count. Its log is this scenario's own scratch, 0600.
  NOTIFY_LOG="$SCRATCH/notify.log"
  : >"$NOTIFY_LOG"; chmod 0600 "$NOTIFY_LOG"
  printf '#!/bin/bash\nprintf "%%s\\n" "$*" >>%q\n' "$NOTIFY_LOG" >"$SCRATCH/bin/omarchy-notification-send"
  chmod 0700 "$SCRATCH/bin/omarchy-notification-send"
  h reap >/dev/null 2>&1
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT
  CACHE="$SCRATCH/cache/omarchy-iptv"
  STATE="$SCRATCH/state/omarchy-iptv/state.json"
  KA=$(key_of "$A"); KB=$(key_of "$B"); KC=$(key_of "$C"); KD=$(key_of "$D"); KDEAD=$(key_of "$DEAD")
  echo "   keys: A $KA  B $KB  C $KC  D $KD"
  [[ -n $ONLY ]] && echo "   PARTIAL RUN: only $ONLY (--only), then P and T1"

  # Every block --only does not name runs only when --only is absent.
  if [[ -z $ONLY ]]; then   # --only: D .. Z, full runs only
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
  # R22a (round 12): with no file to load, FileView reports FileNotFound --
  # which an unreadable directory reports too -- so the state is applied only
  # once the helper's `state init` says it found NOTHING at the path. The
  # adoption therefore happens after the dirs are ready (or at the reload the
  # helper's creation of the file raises), never parked over an unread load;
  # N1 used to observe it parked, the timing this round changed on purpose.
  wait_for true 20 pf "['dirsReady']" >/dev/null || true
  wait_for "$KA" 20 pf "['memoryActiveKey']" >/dev/null || true
  ck "N1 the fresh install is applied on the helper's word: it found nothing at the path, the no-write mode never engaged, and the entry's URL is adopted" \
     "found:$(pf "['stateInitFound']") blocked:$(pf "['stateWriteBlocked']") memory:$(pf "['memoryActiveKey']")" "found:absent blocked: memory:$KA"
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

  echo "== G: the migration MARKER -- it lands with the migration, a downgrade's helper drops it, and the re-upgrade migrates again (R21a) ($(elapsed) s)"
  # R21a: the bar entry's URLs are read only while the LANDED state does not
  # carry `entryMigrated`. G1..G3 are the first start over the 0.13.5 shape
  # (no activeKey, no marker): the marker lands in the same write as the
  # adoption, and the strip follows it. G4 is the downgrade the ruling
  # accepts on purpose, made by the REAL 0.13.6 helper (exported from the
  # v0.13.6 tag, run over this file with `state favorite add`): its
  # normalize_state is a whitelist from before D-SINK-19 and drops both
  # `activeKey` and the marker. 0.13.6 then names its active source by the
  # URL on the entry, so G5 restarts over that entry: the re-upgrade
  # migrates again -- adopts, marks, strips -- and reports nothing.
  seed ""
  start_shell --playlist "$A" || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  wait_for true 10 landed >/dev/null || true
  ck "G1 the first start over the 0.13.5 shape writes the marker WITH the adoption: entryMigrated true and activeKey A in the file" \
     "marker:$(sj "d.get('entryMigrated', 'absent')") activeKey:$(sj "d.get('activeKey', 'absent')")" "marker:true activeKey:$KA"
  ck "G2 the service saw it LAND, holds it in memory, and reported nothing (the migration is not a refusal)" \
     "landed:$(landed) memory:$(pf "['memoryMigrated']") reports:$(reports) notified:$(notified)" "landed:true memory:true reports:- notified:0"
  ck "G3 the entry was stripped after the landing: sourceKey A, no playlistUrl, no epgUrl" \
     "$(hf "['stored']") playlistUrl:$(stored_has playlistUrl) epgUrl:$(stored_has epgUrl)" "$KA playlistUrl:no epgUrl:no"
  stop_shell
  g4="notag"
  if git -C "$ROOT" show v0.13.6:bin/omarchy-iptv >"$WORK/helper-0136" 2>/dev/null; then
    python3 "$WORK/helper-0136" state --state-dir "$(dirname "$STATE")" favorite add t:g4.downgrade >/dev/null 2>&1
    g4="rc:$? marker:$(sj "d.get('entryMigrated', 'absent')") activeKey:$(sj "d.get('activeKey', 'absent')") records:$(sj "len(d['sources'])")"
  fi
  ck "G4 the 0.13.6 helper (the v0.13.6 tag's) rewrites the file without the marker and without activeKey, keeping the records" \
     "$g4" "rc:0 marker:absent activeKey:absent records:2"
  start_shell --playlist "$A" || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  wait_for true 10 landed >/dev/null || true
  ck "G5 the re-upgrade over 0.13.6's entry (its URL back on it) migrates again: A active in the file, the marker back, the URL stripped, nothing reported" \
     "activeKey:$(sj "d.get('activeKey', 'absent')") marker:$(sj "d.get('entryMigrated', 'absent')") playlistUrl:$(stored_has playlistUrl) reports:$(reports)" \
     "activeKey:$KA marker:true playlistUrl:no reports:-"

  echo "== C: a playlistUrl on the entry at the MIGRATION, beside the surviving mirror (review P1, R1; R21a) ($(elapsed) s)"
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

  echo "== E: an epgUrl on the entry at the MIGRATION lands on the active record (R4; R21a) ($(elapsed) s)"
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
  SLOW_TREE="$WORK/slow-tree"
  stage_slow_tree "$SLOW_TREE" || echo "   the slow tree could not be staged from $PLUGIN_ROOT"
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

  echo "== F: the migration's state write FAILS -- an unwritable state directory, a migration input set mid-session, a switch, a restart (R13, round-3 P1; R21a) ($(elapsed) s)"
  # R21 (round 11): the bar entry's URLs are read only while the migration
  # marker has not LANDED, so the route this segment observes -- a URL
  # adopted on the dirsReady route whose state write then fails -- exists
  # only inside a migration that has not landed. So the disk goes away AT
  # the start: the directory loses `w` the moment the helper's `state init`
  # has run (fixtures/disk-gone-after-init.py, staged over the O segment's
  # copy of the tree), so the start's own migration write (the marker)
  # fails and the marker never lands; a playlistUrl set after the start is
  # then still a migration input, adopted in memory on the dirsReady route
  # with a write that fails. Taking `w` away BEFORE the start does nothing
  # -- init's ensure_private_dir chmods the directory back to 0700, and
  # this segment's first live run read F1 `failed:false landed:true` -- and
  # taking it away under the running shell, as round 10 did, is too late:
  # the marker has landed and the same CLI set is REFUSED (X observes
  # that). This scenario's own scratch directory, 0700 again below before
  # the shell is stopped, and in cleanup().
  RO_TREE="$WORK/ro-tree"; rm -rf "$RO_TREE"
  if ! { cp -R "$SLOW_TREE" "$RO_TREE" && cp "$HERE/fixtures/disk-gone-after-init.py" "$RO_TREE/bin/omarchy-iptv" && chmod +x "$RO_TREE/bin/omarchy-iptv"; }; then
    echo "   the disk-gone tree could not be staged from $SLOW_TREE"
  fi
  seed "$KA"
  export OMARCHY_IPTV_PLUGIN_ROOT=$RO_TREE
  start_shell --playlist none --source-key "$KA" || true
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT
  wait_for 20 10 svc "['channels']" >/dev/null || true
  wait_for true 10 pf "['stateSaveFailed']" >/dev/null || true
  wait_for 0 10 pf "['stateSavesInFlight']" >/dev/null || true
  sleep 0.5
  ck "F1 configured on A; the start's own migration write FAILED, so the marker has not landed: failure recorded once, nothing in flight (control)" \
     "$(svc "['configured']") $(svc "['activeSourceKey']") inflight:$(pf "['stateSavesInFlight']") failed:$(pf "['stateSaveFailed']") landed:$(landed) signalled:$(log_since 'sourcesPersistFailed .*state_write_failed')" "true $KA inflight:0 failed:true landed:false signalled:1"
  sha0=$(sha "$STATE")
  ipc set playlistUrl "$B" >/dev/null
  wait_for "$KB" 10 svc "['activeSourceKey']" >/dev/null || true
  sleep 1.0
  ck "F2 the URL is a migration input (the marker never landed): adopted in memory and its state write FAILED: failure recorded, nothing in flight, nothing held (control: the rig made the write fail)" \
     "memory:$(pf "['memoryActiveKey']") failed:$(pf "['stateSaveFailed']") inflight:$(pf "['stateSavesInFlight']") held:$(pf "['pendingEntryKey']")" "memory:$KB failed:true inflight:0 held:NULL"
  ck "F3 the stored entry was NOT rewritten: the URL is still on it, the only copy of the input, beside the OLD mirror" \
     "$(hf "['stored']") playlistUrl:$(stored_has playlistUrl)" "$KA playlistUrl:yes"
  ck "F4 state.json on disk is untouched, the failure is logged without a URL, and sourcesPersistFailed(state_write_failed) was signalled exactly once for the episode, nothing reported" \
     "file:$([[ $(sha "$STATE") == "$sha0" ]] && echo untouched || echo written) logged:$([[ $(log_since 'state.json could not be written') -gt 0 ]] && echo yes || echo no) signalled:$(log_since 'sourcesPersistFailed .*state_write_failed') urls:$(tail -n +"$((LOG_MARK + 1))" "$LOG" 2>/dev/null | grep -a 'could not be written' | grep -ac '://') reports:$(reports)" \
     "file:untouched logged:yes signalled:1 urls:0 reports:-"
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
  echo "   restarting over the entry as stored, on the tree under test: playlist $([[ $seed_playlist == none ]] && echo none || echo '(set)'), sourceKey $seed_key"
  start_shell "${seed_args[@]}" || true
  wait_for "$KB" 10 svc "['activeSourceKey']" >/dev/null || true
  wait_for 3 20 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  ck "F6 the next start RE-ADOPTS the URL the failed write left on the entry (as stored after L): its record in the file, active, fetched, and the URL off the entry" \
     "record:$(sj "len([s for s in d['sources'] if s['key'] == '$KB'])") activeKey:$(sj "d.get('activeKey', 'absent')") $(svc "['configured']") $(svc "['channels']") $(hf "['stored']") playlistUrl:$(stored_has playlistUrl)" \
     "record:1 activeKey:$KB true 3 $KB playlistUrl:no"
  ck "F7 the history holds the three records and nothing carries B's path (the switch that landed in memory only went with the shell)" \
     "records:$(sj "len(d['sources'])") leaks:$(qa_count "$B" "$LOG") $(printf '%s\n%s\n%s\n' "$(ipc state)" "$(ipc hostEntry)" "$(ipc sources)" | grep -ac "$B")" "records:3 leaks:0 0"

  echo "== U: a guide URL with NO source to guide at the migration -- reported once and stripped, never held (R21c; R17's and R19b's rig) ($(elapsed) s)"
  # The round-6 data-loss lens's rig (rev-key6-dataloss/epg-child.sh): two
  # saved sources, NONE active, and an epgUrl set on the entry. R12 left it
  # on the entry and R19b held it in state.json as pendingEpg for the next
  # source to become active -- the machinery the product owner's decision of
  # 2026-10-13 withdrew (R21c: it never had a playlist to guide). It is now
  # REPORTED once (Model.entryInputNotice, `epgUrl:no-source`), taken off
  # the entry by the migration's write once that has landed, and never
  # reaches a record: not through the logo toggle's heal (U2), not through
  # the switch (U3), not at a restart (U4), on the echoing host either
  # (U5..U7). The entry's VALUES are never read: key names from hostEntry,
  # the record's EPG compared inside python against the fixture string. The
  # harness seed always carries an `epgUrl` NAME (empty when unset), so the
  # restart checks read the file and the service, never that name.
  seed ""
  start_shell --playlist none --epg "$EPG" --source-key "" || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 0.5
  ck "U1 loaded on the lagging host with no active source: the guide URL REPORTED once (no-source), OFF the stored entry, on no record, nowhere in the state file, and the marker landed" \
     "host:$(qa_json_field "d['host']" "$(ipc hostEntry)") configured:$(svc "['configured']") epgUrl:$(stored_has epgUrl) reports:$(reports) on:$(epg_on) file:$(infile) landed:$(landed)" \
     "host:lag configured:false epgUrl:no reports:epgUrl:no-source on:none file:no landed:true"
  log_mark
  ipc open '{}' >/dev/null; sleep 0.5
  ipc sourcesKey enter >/dev/null; sleep 0.3
  ipc sourcesKey g >/dev/null; sleep 0.3
  ipc sourcesKey confirm >/dev/null
  wait_for 1 10 log_since 'updateEntryInline io' >/dev/null || true
  wait_for yes 5 stored_has showLogos >/dev/null || true
  sleep 0.5
  ck "U2 the logo toggle HEALS (nothing outstanding): logos on, one write, not written alone, no epgUrl on the stored entry, no second report, on no record" \
     "logos:$(qa_json_field "d['guide']['showLogos']" "$(ipc state)") writes:$(log_since 'updateEntryInline io') alone:$(log_since 'logo setting written alone') epgUrl:$(stored_has epgUrl) reports:$(n_reports) on:$(epg_on)" \
     "logos:true writes:1 alone:0 epgUrl:no reports:1 on:none"
  ipc close >/dev/null
  res=$(ipc switchSource "$KA")
  wait_for "$KA" 10 hf "['stored']" >/dev/null || true
  sleep 1.0
  ck "U3 the switch to A does NOT land the guide URL anywhere: A's record has none, the file and the mirror name A, no epgUrl on the stored entry, configured on A" \
     "ok:$(qa_json_field "d['ok']" "$res") on:$(epg_on) file:$(sj "d.get('activeKey', 'absent')") stored:$(hf "['stored']") epgUrl:$(stored_has epgUrl) $(svc "['configured']") $(svc "['activeSourceKey']")" \
     "ok:true on:none file:$KA stored:$KA epgUrl:no true $KA"
  seed_args=(--playlist none); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  [[ $(stored_has epgUrl) == yes ]] && seed_args+=(--epg "$EPG")
  stop_shell
  start_shell "${seed_args[@]}" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  ck "U4 a restart over the entry as stored stands on A with no guide URL anywhere and nothing to report" \
     "$(svc "['activeSourceKey']") $(svc "['channels']") on:$(epg_on) records:$(sj "len(d['sources'])") reports:$(reports)" "$KA 20 on:none records:2 reports:-"
  # The echoing host: no toggle, the switch alone.
  seed ""
  start_shell --host echo --playlist none --epg "$EPG" --source-key "" || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 0.5
  ck "U5 the fake host ECHOES (the lever took): no active source, the guide URL reported once, off the stored and the published entry alike, on no record, nowhere in the file" \
     "host:$(qa_json_field "d['host']" "$(ipc hostEntry)") configured:$(svc "['configured']") epgUrl:$(stored_has epgUrl)/$(published_has epgUrl) reports:$(reports) on:$(epg_on) file:$(infile)" \
     "host:echo configured:false epgUrl:no/no reports:epgUrl:no-source on:none file:no"
  res=$(ipc switchSource "$KA")
  wait_for "$KA" 10 hf "['stored']" >/dev/null || true
  sleep 1.0
  ck "U6 the switch on the echoing host lands nothing: A has no guide URL, both sides name A, epgUrl on neither, still one report" \
     "ok:$(qa_json_field "d['ok']" "$res") on:$(epg_on) stored:$(hf "['stored']") published:$(hf "['published']") epgUrl:$(stored_has epgUrl)/$(published_has epgUrl) reports:$(n_reports)" \
     "ok:true on:none stored:$KA published:$KA epgUrl:no/no reports:1"
  seed_args=(--host echo --playlist none); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  [[ $(stored_has epgUrl) == yes ]] && seed_args+=(--epg "$EPG")
  stop_shell
  start_shell "${seed_args[@]}" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  ck "U7 a restart over that (echoing host) stands on A with no guide URL and nothing to report" \
     "$(svc "['activeSourceKey']") $(svc "['channels']") on:$(epg_on) records:$(sj "len(d['sources'])") reports:$(reports)" "$KA 20 on:none records:2 reports:-"

  echo "== K: a REFUSED playlistUrl beside a guide URL with no source SETTLES, on both hosts (R18b, R18a; the round-7 data-loss lens's two loops; R21c) ($(elapsed) s)"
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
  # R21 (round 11): the start is the MIGRATION (the seed has no marker), so
  # both values are read once: the refused playlist is D16's and reported
  # `invalid`, the guide URL has no source and is reported `no-source`
  # (R21c), and the migration's write strips both once it has landed --
  # nothing is held, and the cycle must still settle on the lagging host.
  # R29d (2026-10-20) re-levelled the reports: a guide URL that came with
  # an unusable playlist is told WITH it, one notice, `playlistUrl:invalid-pair`
  # (until R29d `epgUrl:no-source,playlistUrl:invalid`, two); the loop
  # window and the strip are unchanged.
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
  ck "K1 the lagging host with a refused playlistUrl beside a guide URL with no source SETTLES (at most 2 entry writes and 50 CPU ticks in 5 s), both reported once, both off the stored entry, the guide URL nowhere in the file (R21c)" \
     "$verdict host:$(qa_json_field "d['host']" "$(ipc hostEntry)") playlistUrl:$(stored_has playlistUrl) epgUrl:$(stored_has epgUrl) reports:$(reports) file:$(infile) on:$(epg_on)" \
     "settled host:lag playlistUrl:no epgUrl:no reports:playlistUrl:invalid-pair file:no on:none"
  seed ""
  start_shell --host echo --playlist "$BAD" --epg "$EPG" --source-key "" || true
  verdict=$(loop_window)
  ck "K2 the echoing host with the same entry settles too (control: the echo host settled on a bare value on every tree), both reported once and off the stored entry" \
     "$verdict host:$(qa_json_field "d['host']" "$(ipc hostEntry)") playlistUrl:$(stored_has playlistUrl) epgUrl:$(stored_has epgUrl) reports:$(reports)" \
     "settled host:echo playlistUrl:no epgUrl:no reports:playlistUrl:invalid-pair"
  seed ""
  start_shell --host echo --playlist "  $BAD " --epg "$EPG" --source-key "" || true
  verdict=$(loop_window)
  ck "K3 the echoing host with the refused value WRAPPED IN WHITESPACE (as \`omarchy bar set\` stores it) settles, and the refused credential leaves the stored entry once reported" \
     "$verdict host:$(qa_json_field "d['host']" "$(ipc hostEntry)") playlistUrl:$(stored_has playlistUrl) epgUrl:$(stored_has epgUrl) reports:$(reports)" \
     "settled host:echo playlistUrl:no epgUrl:no reports:playlistUrl:invalid-pair"

  echo "== Z: whitespace-wrapped values after the marker are refused the way any value is, compared the way adoption compares (R18a, R21b; the round-7 data-loss lens's P1-A) ($(elapsed) s)"
  # Lifted from the lens's resurrect-child.sh and loop-child.sh MODE=badws.
  # `omarchy bar set` hands the value to `jq --arg` as typed, so a pasted
  # URL can carry surrounding whitespace onto the entry; round 7's keep
  # decision compared it raw and never matched its own snapshot -- a removed
  # source came back and a refused credential stayed in shell.json. Under
  # R21 the seed carries the migration marker, so a wrapped value set while
  # the shell was down is REFUSED: never adopted (Z1), reported once, off
  # the stored entry; the restart over that entry resurrects nothing (Z2);
  # a wrapped refused credential likewise (Z3). The one comparison left --
  # has this session seen this value -- goes through the same normaliser.
  seed "$KA" migrated
  start_shell --playlist "  $B  " --source-key "$KA" || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  sleep 1.0
  ck "Z1 a whitespace-wrapped CLI playlist (B) set while the shell was down, after the marker: REFUSED -- no record for B, A still active, reported once, off the stored entry" \
     "active:$(svc "['activeSourceKey']") records:$(sj "len([s for s in d['sources'] if s['key'] == '$KB'])") reports:$(reports) playlistUrl:$(stored_has playlistUrl)" \
     "active:$KA records:0 reports:playlistUrl:retired playlistUrl:no"
  seed_args=(--playlist none); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  [[ $(stored_has playlistUrl) == yes ]] && seed_args=(--playlist "  $B  " "${seed_args[@]:2}")
  stop_shell
  echo "   restarting over the entry as stored: playlist $([[ ${seed_args[1]} == none ]] && echo none || echo '(the refused value, as stored)'), sourceKey $seed_key"
  start_shell "${seed_args[@]}" || true
  sleep 1.0
  ck "Z2 the next start over that entry resurrects nothing: no record for B, A active, nothing to report" \
     "records:$(sj "len([s for s in d['sources'] if s['key'] == '$KB'])") active:$(svc "['activeSourceKey']") reports:$(reports)" "records:0 active:$KA reports:-"
  seed "$KA" migrated
  start_shell --playlist "  $BAD"$'\t' --source-key "$KA" || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  sleep 0.5
  ck "Z3 a whitespace-wrapped REFUSED credential beside a working source leaves the stored entry once reported, and the working source stays active" \
     "playlistUrl:$(stored_has playlistUrl) active:$(svc "['activeSourceKey']") $(svc "['configured']") reports:$(reports)" "playlistUrl:no active:$KA true reports:playlistUrl:retired"

  fi   # --only: end of D .. Z

  # F-HARNESS-49 (2026-10-27): THE START-UP PRUNE RACE, D-SRC-69, a product
  # finding reported for the owner. A RIG, NOT A CHECK: it runs only when `--only
  # PRUNE` names it, never
  # in a full run, and asserts nothing -- it prints what the sink holds, so
  # the owner can see the defect on any tree (`--baseline REF --only PRUNE`)
  # until it is decided. The start-up `cache prune` is QUEUED when the cache
  # layout is ready (schedulePrune) with the keys the state holds THEN, and
  # RUN when the dirs are (stateInitExited -> runNextCacheJob); an in-app
  # add made in between probes into sources/<new key>, which no record names
  # (SR23), so the prune removes it: mid-write the probe fails on its rename
  # (A2's FileNotFoundError, 2026-10-27, the add dropped), and once written
  # the ADDED, ACTIVE source keeps a record and loses its channels for the
  # session. The window is made deterministic here by holding the start-up
  # init 4 s (the slow tree), so the add's probe completes and commits before
  # the dirs are ready. Measured 2026-10-27 on dev 45bded9 and on cc35557
  # (0.15.0) alike: committed with 11 channels and its directory; after
  # dirsReady the prune `--keep <A> <C>` (no D, no --active) removed
  # sources/<D>; the session then showed 0 channels on the active source
  # until a restart refetched it.
  if [[ -n $ONLY ]] && seg_on PRUNE; then   # --only PRUNE begins (a rig: never in a full run)
  echo "== PRUNE (a rig, no check): an add whose probe commits while the start-up init is held, then the start-up prune ($(elapsed) s)"
  PRUNE_TREE="$WORK/prune-tree"
  stage_slow_tree "$PRUNE_TREE" || echo "   the slow tree could not be staged from $PLUGIN_ROOT"
  seed "" migrated
  export OMARCHY_IPTV_PLUGIN_ROOT=$PRUNE_TREE OMARCHY_IPTV_SLOW_MS=4000 OMARCHY_IPTV_SLOW_VERBS="state init"
  start_shell --playlist none --source-key "" || true
  at_add="dirsReady:$(pf "['dirsReady']")"
  res=$(ipc addSource "$D" "" "")
  wait_for "$KD" 20 svc "['activeSourceKey']" >/dev/null || true
  committed="active:$([[ $(svc "['activeSourceKey']") == "$KD" ]] && echo D || echo other) dirsReady:$(pf "['dirsReady']") cache:$([[ -f $CACHE/sources/$KD/channels.json ]] && echo kept || echo gone) channels:$(svc "['channels']")"
  wait_for true 20 pf "['dirsReady']" >/dev/null || true
  wait_settled || true
  sleep 2
  after="active:$([[ $(svc "['activeSourceKey']") == "$KD" ]] && echo D || echo other) record:$(sj "'$KD' in [s['key'] for s in d['sources']]") cache:$([[ -f $CACHE/sources/$KD/channels.json ]] && echo kept || echo gone) channels:$(svc "['channels']")"
  stop_shell
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT; unset OMARCHY_IPTV_SLOW_MS OMARCHY_IPTV_SLOW_VERBS
  echo "   PRUNE at the add $at_add (add ok:$(qa_json_field "d['ok']" "$res")); committed $committed; after the start-up prune $after"
  case $after in
    *"cache:gone channels:0") echo "   PRUNE: the start-up prune REMOVED the added, active source's cache (the race is present on this tree)" ;;
    *"cache:kept channels:11") echo "   PRUNE: the added source's cache SURVIVED the start-up prune (the race is absent on this tree)" ;;
    *) echo "   PRUNE: neither shape -- read the lines above" ;;
  esac
  fi   # --only PRUNE ends

  if seg_on A; then   # --only A begins
  echo "== A: the in-app add after a CLI epgUrl was refused, through the harness addSource verb (R21b; R17b's and R18d's rig) ($(elapsed) s)"
  # The probe commit of an in-app add (Service's sourceProbeProc exit),
  # which the round-7 live lens found no segment reaching. R17b landed a
  # pending CLI epgUrl on the new record and R18d/R19c decided between it
  # and the form's own; R21 withdrew both, because a CLI epgUrl after the
  # marker is REFUSED: A1 the new record carries no guide URL at all, A2 the
  # form's own guide URL and nothing else. Saved sources, none active, the
  # marker landed (the seed).
  form_on() { sj "','.join(sorted(s['key'] for s in d['sources'] if s.get('epgUrl') == '$FORM_EPG')) or 'none'"; }
  # F-HARNESS-49: each add waits for the start to SETTLE (wait_settled). A2
  # was red on 2026-10-27 at idle (`active: form:none`): the add's probe
  # wrote into sources/<D> while the start-up `cache prune`, queued before
  # the add with the two seeded keys, ran at dirsReady and removed that
  # directory between the probe's temporary file and its rename
  # (FileNotFoundError in the harness log, the probe failed, the add was
  # dropped). Not a regression: the prune has run at dirsReady with a keep
  # list taken at queue time since f138740 (2026-09-13), and the same rig
  # deletes an added source's cache on cc35557 (0.15.0) and on dev alike
  # (`--only PRUNE`). That race is a product finding of its own, reported
  # with F-HARNESS-49 for the owner to decide; A observes R21b, the CLI
  # value refused and the form's own guide URL kept, in a settled session.
  seed "" migrated
  start_shell --playlist none --epg "$EPG" --source-key "" || true
  wait_settled || true
  res=$(ipc addSource "$D" "" "")
  wait_for "$KD" 20 svc "['activeSourceKey']" >/dev/null || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 0.5
  ck "A1 a CLI epgUrl set while the shell was down is REFUSED (reported once); an in-app add with NO guide URL in the form makes a record that is active and holds none, and the stored entry carries none" \
     "ok:$(qa_json_field "d['ok']" "$res") active:$(svc "['activeSourceKey']") on:$(epg_on) reports:$(reports) epgUrl:$(stored_has epgUrl) stored:$(hf "['stored']")" \
     "ok:true active:$KD on:none reports:epgUrl:retired epgUrl:no stored:$KD"
  seed "" migrated
  start_shell --playlist none --epg "$EPG" --source-key "" || true
  wait_settled || true
  res=$(ipc addSource "$D" "$FORM_EPG" "")
  wait_for "$KD" 20 svc "['activeSourceKey']" >/dev/null || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 0.5
  ck "A2 an in-app add whose FORM carries its own guide URL, after a refused CLI epgUrl: the form's guide URL is on the new record, the CLI value on none and nowhere in the file" \
     "ok:$(qa_json_field "d['ok']" "$res") active:$(svc "['activeSourceKey']") form:$(form_on) cli:$(epg_on) file:$(infile) epgUrl:$(stored_has epgUrl)" \
     "ok:true active:$KD form:$KD cli:none file:no epgUrl:no"
  fi   # --only A ends

  if [[ -z $ONLY ]]; then   # --only: Y .. B18, full runs only
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
  wait_for true 10 landed >/dev/null || true
  after=""
  for i in 1 2 3; do
    ipc set playlistUrl "$BAD" >/dev/null
    wait_for no 5 stored_has playlistUrl >/dev/null || true
    sleep 1.0
    after="$after$(stored_has playlistUrl) "
  done
  ck "Y2 the same refused (credentialed) playlistUrl set three times beside the active source, after the marker: off the stored entry after EVERY set, the source still active, reported ONCE (R21b)" \
     "after:${after% } active:$(svc "['activeSourceKey']") reports:$(reports)" "after:no no no active:$KA reports:playlistUrl:retired"
  seed "$KA"
  start_shell --playlist "$A" --source-key "$KA" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  rec_epg() { sj "','.join({'$EPG': 'E', '$FORM_EPG': 'F', '': 'none'}.get(s.get('epgUrl', ''), 'other') for s in d['sources'] if s['key'] == '$1') or 'norecord'"; }
  wait_for true 10 landed >/dev/null || true
  # R21b: after the marker (the start above landed it) the CLI value is
  # REFUSED both times: it never reaches A's record, and one report.
  ipc set epgUrl "$EPG" >/dev/null; wait_for no 10 stored_has epgUrl >/dev/null || true; sleep 1.0
  ipc set epgUrl "$EPG" >/dev/null; sleep 1.5
  twice="$(rec_epg "$KA")/$(stored_has epgUrl)"; y3_reports=$(reports)
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
  ck "Y3 the same epgUrl set twice after the marker is refused each time (on no record, off the stored entry, reported once), the guide URL is then edited in the app to F, and F stands after a restart over the entry as stored" \
     "twice:$twice reports:$y3_reports edit:$(qa_json_field "d['ok']" "$res") after:$(svc "['activeSourceKey']")/$(rec_epg "$KA")" "twice:none/no reports:epgUrl:retired edit:true after:$KA/F"

  echo "== Q: the add form submitted, a CLI epgUrl set while its probe runs -- REFUSED, so the form's guide URL stands, in either order (R21b; R19c's rig, the round-8 data-loss lens's P1-B) ($(elapsed) s)"
  # Lifted from the lens's race-child.sh. The probe is held open by a local
  # server that answers after 4 s; the CLI value is set 1 s after the
  # submit (Q1) or before it (Q2). Round 8 let the form's guide URL win
  # whenever it carried one, so in Q1 the LATER CLI value existed nowhere;
  # round 9 judged the two by time. R21 refuses the CLI value after the
  # marker, so there is no order to judge: the form's guide URL stands in
  # both, and the CLI value is reported once and on no record.
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
  wait_for true 10 landed >/dev/null || true
  res=$(ipc addSource "$SLOW" "$FORM_EPG" "")
  sleep 1.0
  ipc set epgUrl "$EPG" >/dev/null
  wait_for no 5 stored_has epgUrl >/dev/null || true
  during="$(reports)/$(svc "['activeSourceKey']")"
  wait_for "$KS_SLOW" 20 svc "['activeSourceKey']" >/dev/null || true
  sleep 1.0
  ck "Q1 form first: the CLI epgUrl set while the probe runs is REFUSED (reported once); at the commit the form's guide URL is on the new record, the CLI value nowhere, nothing on the entry" \
     "ok:$(qa_json_field "d['ok']" "$res") during:$during active:$(svc "['activeSourceKey']") on:$(rec_epg "$KS_SLOW") file:$(infile) epgUrl:$(stored_has epgUrl)" \
     "ok:true during:epgUrl:retired/ active:$KS_SLOW on:F file:no epgUrl:no"
  seed ""
  start_shell --playlist none --source-key "" || true
  wait_for true 10 landed >/dev/null || true
  ipc set epgUrl "$EPG" >/dev/null
  wait_for no 10 stored_has epgUrl >/dev/null || true
  res=$(ipc addSource "$SLOW" "$FORM_EPG" "")
  wait_for "$KS_SLOW" 20 svc "['activeSourceKey']" >/dev/null || true
  sleep 1.0
  ck "Q2 CLI first: refused (reported once), then the add form: the form's guide URL stands on the new record, the CLI value nowhere" \
     "ok:$(qa_json_field "d['ok']" "$res") active:$(svc "['activeSourceKey']") on:$(rec_epg "$KS_SLOW") reports:$(reports) file:$(infile) epgUrl:$(stored_has epgUrl)" \
     "ok:true active:$KS_SLOW on:F reports:epgUrl:retired file:no epgUrl:no"
  kill_pid "$SLOW_PID"; SLOW_PID=""

  echo "== V: the EDIT form -- a guide URL typed in the app after a refused CLI value stands at the switch (R21b; R19c's rig, the round-8 data-loss lens's P2) ($(elapsed) s)"
  # Lifted from the lens's aba-child.sh T=edit. With no source active the
  # CLI value used to be HELD (R19b) and to meet the edited record at the
  # switch; round 8 replaced the later edit F with it. R21 refuses the CLI
  # value after the marker: it is reported, held nowhere, and the switch to
  # A has nothing to meet but A's own guide URL, F.
  seed ""
  start_shell --playlist none --source-key "" || true
  wait_for true 10 landed >/dev/null || true
  ipc set epgUrl "$EPG" >/dev/null
  wait_for no 5 stored_has epgUrl >/dev/null || true
  res=$(ipc updateSource "$KA" "{\"epgUrl\": \"$FORM_EPG\"}")
  wait_for F 10 rec_epg "$KA" >/dev/null || true
  res2=$(ipc switchSource "$KA")
  wait_for "$KA" 10 hf "['stored']" >/dev/null || true
  sleep 1.0
  ck "V1 a refused CLI epgUrl (reported once), A's guide URL edited to F, then the switch to A: F stands on A, the CLI value nowhere, nothing on the entry" \
     "edit:$(qa_json_field "d['ok']" "$res") switch:$(qa_json_field "d['ok']" "$res2") active:$(svc "['activeSourceKey']") on:$(rec_epg "$KA") reports:$(reports) file:$(infile) epgUrl:$(stored_has epgUrl)" \
     "edit:true switch:true active:$KA on:F reports:epgUrl:retired file:no epgUrl:no"

  echo "== H: a migration guide URL whose state write FAILED, then a later in-app edit whose save LANDS (R19d, D-SRC-18; R21a) ($(elapsed) s)"
  # The board's D-SRC-18 at the sink. The migration's guide URL is adopted
  # onto the active source A, and its save fails (the state directory loses
  # `w` right after `state init`, F's staging), so R11's drop leaves the input on
  # the entry -- the only copy -- and the marker does not land. The
  # directory comes back and the user edits the guide URL in the app, which
  # LANDS, the marker with it; R19d's owed mirror then takes the older input
  # off the entry. Before R19d the next start re-adopted it over the edit;
  # under R21 the next start would REFUSE it even had the strip not run,
  # because the marker landed with the edit -- and nothing is reported here,
  # because the strip did run.
  seed "$KA"
  export OMARCHY_IPTV_PLUGIN_ROOT=$RO_TREE
  start_shell --playlist none --epg "$EPG" --source-key "$KA" || true
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT
  wait_for 20 10 svc "['channels']" >/dev/null || true
  wait_for true 10 pf "['stateSaveFailed']" >/dev/null || true
  sleep 1.0
  failed="$(pf "['stateSaveFailed']")/$(stored_has epgUrl)/$(landed)"
  chmod 0700 "$(dirname "$STATE")"
  res=$(ipc updateSource "$KA" "{\"epgUrl\": \"$FORM_EPG\"}")
  wait_for F 10 rec_epg "$KA" >/dev/null || true
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 1.0
  landed="$(pf "['stateSaveFailed']")/$(stored_has epgUrl)/$(landed)"
  seed_args=(--playlist none); seed_key="(none)"
  [[ $(stored_has sourceKey) == yes ]] && { seed_key=$(hf "['stored']"); seed_args+=(--source-key "$seed_key"); }
  [[ $(stored_has epgUrl) == yes ]] && seed_args+=(--epg "$EPG")
  stop_shell
  start_shell "${seed_args[@]}" || true
  wait_for 20 10 svc "['channels']" >/dev/null || true
  sleep 0.5
  ck "H1 the failed migration left the guide URL on the entry with no marker landed; the later edit's save landed (the marker with it) and the owed mirror took the URL off; the restart stands on the edit F and reports nothing" \
     "failed:$failed edit:$(qa_json_field "d['ok']" "$res") landed:$landed after:$(svc "['activeSourceKey']")/$(rec_epg "$KA") reports:$(reports)" \
     "failed:true/yes/false edit:true landed:false/no/true after:$KA/F reports:-"

  echo "== X: AFTER the marker, nothing on the bar entry is an input -- refused, reported once, stripped (R21b; the product owner's decision of 2026-10-13) ($(elapsed) s)"
  # The route ten repair rounds could not make safe: `omarchy bar set ...
  # playlistUrl|epgUrl` on an install whose migration has landed. Each value
  # is REFUSED (never adopted, whatever it is), REPORTED once per value --
  # through the notification sink, the stand-in shell_arm put in front of
  # PATH, and the service's own record of it -- and gone from the STORED
  # entry after the owned write that strips it. The seed carries the marker.
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  start_shell --playlist "$B" --source-key "$KA" || true
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  sleep 0.5
  ck "X1 a playlistUrl set while the shell was down: REFUSED -- A still active, no record for B, reported once, off the stored entry, the marker as it was" \
     "active:$(svc "['activeSourceKey']") B:$(sj "len([s for s in d['sources'] if s['key'] == '$KB'])") records:$(sj "len(d['sources'])") reports:$(reports) playlistUrl:$(stored_has playlistUrl) landed:$(landed)" \
     "active:$KA B:0 records:2 reports:playlistUrl:retired playlistUrl:no landed:true"
  ipc set epgUrl "$EPG" >/dev/null
  wait_for no 10 stored_has epgUrl >/dev/null || true
  sleep 1.0
  ck "X2 an epgUrl set mid-session: REFUSED -- on no record, nowhere in the file, reported once, off the stored entry" \
     "on:$(epg_on) file:$(infile) reports:$(reports) epgUrl:$(stored_has epgUrl)" \
     "on:none file:no reports:playlistUrl:retired,epgUrl:retired epgUrl:no"
  ipc set epgUrl "$EPG" >/dev/null
  sleep 1.5
  ck "X3 the same epgUrl set again: still refused and off the stored entry, and NOT reported a second time" \
     "on:$(epg_on) reports:$(n_reports) epgUrl:$(stored_has epgUrl)" "on:none reports:2 epgUrl:no"
  ipc set playlistUrl "  $BAD " >/dev/null
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  sleep 1.0
  ck "X4 a whitespace-wrapped REFUSED credential: off the stored entry, reported once, A still active, no record for it" \
     "playlistUrl:$(stored_has playlistUrl) reports:$(n_reports) active:$(svc "['activeSourceKey']") records:$(sj "len(d['sources'])")" "playlistUrl:no reports:3 active:$KA records:2"
  ck "X5 the notification SINK: one notification per report, each naming the Sources screen, none carrying a URL or the credential" \
     "notified:$(notified) sources:$(qa_count ' 74016 .*Sources screen' "$NOTIFY_LOG") urls:$(qa_count '://|u:p@|token=' "$NOTIFY_LOG")" "notified:3 sources:3 urls:0"
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  start_shell --host echo --playlist none --source-key "$KA" || true
  wait_for true 10 landed >/dev/null || true
  ipc set playlistUrl "$B" >/dev/null
  wait_for no 10 stored_has playlistUrl >/dev/null || true
  sleep 1.0
  ck "X6 the echoing host: a playlistUrl set mid-session is refused, reported once (one notification), off the stored AND the published entry, A still active" \
     "host:$(qa_json_field "d['host']" "$(ipc hostEntry)") active:$(svc "['activeSourceKey']") reports:$(reports) notified:$(notified) playlistUrl:$(stored_has playlistUrl)/$(published_has playlistUrl)" \
     "host:echo active:$KA reports:playlistUrl:retired notified:1 playlistUrl:no/no"

  echo "== B: a state.json that does NOT load at the start is never written over (R22a; the round-11 data-loss lens's P1 and its sibling), and the guide's fetch-failure hint (R22c) ($(elapsed) s)"
  # Lifted from the round-11 data-loss lens's lf-child.sh. Every case is a
  # MIGRATED install (the marker in the file) whose state.json cannot be read
  # when the shell starts. Before R22a the failed load was applied as an
  # EMPTY state: the migration ran on it and marked it, its save parked
  # behind the start-up dirs, the helper's chmod reload carrying the real
  # text was ignored because a save was parked (R9), and the parked save
  # wrote the empty state over the file (B1, B2: every record gone, on
  # lane-key-m2 and on both host shapes, measured live by the lens). The
  # directory case reads as FileNotFound -- a fresh install, to Quickshell --
  # and the cache layout's save did the same on every tree, 0.13.6 included
  # (B3, B4; measured live on dev 4740a50 by this round's code lane: the
  # in-app record gone, the entry's one re-adopted). R22a: a load that is not
  # a state is never applied, a FileNotFound is a fresh install only when
  # the helper's `state init` found nothing there, and the init's own mode
  # repair is followed by one re-read. B5..B7: a file that cannot be made
  # readable holds the session in the no-write mode -- nothing written, the
  # entry left exactly as it is, the user told once -- until a load that IS
  # a state lifts it.
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  chmod 0000 "$STATE"
  start_shell --playlist none --source-key "$KA" || true
  sleep 1.0
  ck "B1 state.json 0000 while the shell was down: the helper restores 0600 and the start READS it -- both records, the active key and the marker survive, nothing is reported" \
     "records:$(sj "len(d['sources'])") active:$(sj "d.get('activeKey', 'absent')") marker:$(sj "d.get('entryMigrated', 'absent')") mode:$(stat -c %a "$STATE" 2>/dev/null) memory:$(svc "['activeSourceKey']") blocked:$(pf "['stateWriteBlocked']") told:$(qa_count ' 74017 ' "$NOTIFY_LOG")" \
     "records:2 active:$KA marker:true mode:600 memory:$KA blocked: told:0"
  stop_shell
  start_shell --playlist none --source-key "$KA" || true
  sleep 0.5
  ck "B2 ... and a second, ordinary start stands on both records" "records:$(sj "len(d['sources'])") active:$(svc "['activeSourceKey']") channels:$(svc "['channels']")" "records:2 active:$KA channels:20"
  seed "$KA" migrated
  chmod 0000 "$(dirname "$STATE")"
  start_shell --playlist none --source-key "$KA" || true
  sleep 1.0
  ck "B3 the state DIRECTORY 0000 while the shell was down (FileView: FileNotFound): the helper found the file there, restored 0700, and the start READ it -- both records, the cache layout and the marker survive" \
     "records:$(sj "len(d['sources'])") layout:$(sj "d.get('cacheLayout')") marker:$(sj "d.get('entryMigrated', 'absent')") dir:$(stat -c %a "$(dirname "$STATE")" 2>/dev/null) memory:$(svc "['activeSourceKey']") found:$(pf "['stateInitFound']") told:$(qa_count ' 74017 ' "$NOTIFY_LOG")" \
     "records:2 layout:2 marker:true dir:700 memory:$KA found:present told:0"
  stop_shell
  chmod 0700 "$(dirname "$STATE")"
  start_shell --playlist none --source-key "$KA" || true
  sleep 0.5
  ck "B4 ... and a second, ordinary start stands on both records" "records:$(sj "len(d['sources'])") active:$(svc "['activeSourceKey']")" "records:2 active:$KA"
  seed "$KA" migrated
  cp -p "$STATE" "$WORK/good-state.json"
  printf '{"version": 2, "sources": [' >"$STATE"
  chmod 0600 "$STATE"
  sha0=$(sha "$STATE")
  (( SHELL_STARTED )) && stop_shell
  log_mark
  h --detach --timeout 0 --keep --playlist none --source-key "$KA" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  # Not start_shell: a state that never loads never settles, by design. The
  # bound is the no-write mode being reported (or the state loading, on a
  # tree that applies the garbage), 20 s, and it says when it gave up.
  for ((i = 0; i < 200; i++)); do
    [[ $(pf "['stateWriteBlocked']") =~ ^[a-z] || $(svc "['stateLoaded']") == true ]] && break
    sleep 0.1
  done
  (( i == 200 )) && echo "   gave up after 20 s waiting for the no-write mode or a state load"
  sleep 1.0
  keys0=$(qa_json_field "','.join(d['storedKeys'])" "$(ipc hostEntry)")
  add=$(qa_json_field "d['code']" "$(ipc addSource "$D" "" "")")
  swc=$(qa_json_field "d['code']" "$(ipc switchSource "$KC")")
  sleep 1.5
  ck "B5 a state.json that does not parse: NOTHING is written over it, through the start and an in-app add and switch, which are refused; the user is told ONCE, by a notification that names the file and carries no URL" \
     "file:$([[ $(sha "$STATE") == "$sha0" ]] && echo same || echo changed) blocked:$(pf "['stateWriteBlocked']") add:$add switch:$swc told:$(qa_count ' 74017 ' "$NOTIFY_LOG") path:$(qa_count ' 74017 .*state\.json' "$NOTIFY_LOG") urls:$(qa_count '://' "$NOTIFY_LOG")" \
     "file:same blocked:unparsed add:state_unreadable switch:state_unreadable told:1 path:1 urls:0"
  ck "B6 ... and the bar entry is left EXACTLY as it is: the same key names, the same mirror, no owned write" \
     "keys:$([[ $(qa_json_field "','.join(d['storedKeys'])" "$(ipc hostEntry)") == "$keys0" ]] && echo same || echo changed) stored:$(hf "['stored']") writes:$(log_since 'updateEntryInline')" \
     "keys:same stored:$KA writes:0"
  # The user puts the file back, in place (what an editor or a restore does):
  # the FileView's watch reloads it, and a load that IS a state lifts the mode.
  cat "$WORK/good-state.json" >"$STATE"
  wait_for "" 10 pf "['stateWriteBlocked']" >/dev/null || true
  wait_for true 10 svc "['stateLoaded']" >/dev/null || true
  wait_for true 10 svc "['cacheReady']" >/dev/null || true
  res=$(ipc switchSource "$KC")
  wait_for "$KC" 10 sj "d.get('activeKey', 'absent')" >/dev/null || true
  ck "B7 restoring the file LIFTS the no-write mode: the state is applied, and a switch then lands in the file" \
     "blocked:$(pf "['stateWriteBlocked']") loaded:$(svc "['stateLoaded']") switch:$(qa_json_field "d['ok']" "$res") file:$(sj "d.get('activeKey', 'absent')") records:$(sj "len(d['sources'])") told:$(qa_count ' 74017 ' "$NOTIFY_LOG")" \
     "blocked: loaded:true switch:true file:$KC records:2 told:1"
  # R22c. A provider that is down: the active record's playlist is a dead
  # loopback port, so the start's fetch fails and the guide opens on its
  # error state. What the user is told to check is read off the guide AS
  # DRAWN (its emptyState's prose) and off its copy, never off this file.
  seed ""
  python3 - "$STATE" "$KDEAD" "$DEAD" <<'PYSEED'
import json, sys
path, key, url = sys.argv[1], sys.argv[2], sys.argv[3]
rec = {"key": key, "url": url, "epgUrl": "", "kind": "http", "label": "127.0.0.1", "labelCustom": False, "origin": "guide",
       "addedAt": 1799990000, "lastUsed": 1799990000, "fetchedAt": 0, "channelCount": 0, "groupCount": 0}
json.dump({"version": 2, "cacheLayout": 2, "favorites": [], "recents": [], "lastPlayed": None, "session": None, "sources": [rec],
           "savedSearches": [], "hiddenGroups": [], "activeKey": key, "entryMigrated": True}, open(path, "w"))
PYSEED
  chmod 0600 "$STATE"
  start_shell --playlist none --source-key "$KDEAD" || true
  wait_for error 15 svc "['status']" >/dev/null || true
  ipc open '{}' >/dev/null; sleep 0.8
  gs=$(ipc state)
  ck "B8 the guide's fetch-failure hint, as drawn, sends the user to the Sources screen and names no retired setting" \
     "kind:$(qa_json_field "d['guide']['emptyKind']" "$gs") sources:$(qa_json_field "'yes' if 'Sources' in d['guide']['emptyProse'] else 'no'" "$gs") retired:$(qa_json_field "'yes' if ('playlistUrl' in d['guide']['errorCheck'] or 'epgUrl' in d['guide']['errorCheck'] or 'playlistUrl' in d['guide']['emptyProse']) else 'no'" "$gs")" \
     "kind:error sources:yes retired:no"
  ipc close >/dev/null

  echo "== B, round 13: a second no-write episode is told again (R23a), the start-up init is bounded (R23c), the no-write mode has its own surface (R23e, R23h), its refusals say why (R23f), and a FIFO cannot hang the init (R23b) ($(elapsed) s)"
  # R23a. The lift re-arms the notice (liftStateBlock resets stateBlockTold).
  # The round-12 data-loss lens deleted that line and nothing went red,
  # node or live; here are two episodes in one session with no own save
  # between them, each reached the way a user reaches it -- the file damaged
  # IN PLACE under a running shell, which the FileView reloads (measured,
  # spikes/filewatch/) -- and restored in place between them.
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  start_shell --playlist none --source-key "$KA" || true
  cp -p "$STATE" "$WORK/good-state.json"
  printf 'garbage{' >"$STATE"
  wait_for unparsed 10 pf "['stateWriteBlocked']" >/dev/null || true
  ep1=$(pf "['stateWriteBlocked']"); told1=$(qa_count ' 74017 ' "$NOTIFY_LOG")
  cat "$WORK/good-state.json" >"$STATE"
  wait_for "" 10 pf "['stateWriteBlocked']" >/dev/null || true
  lift=$(pf "['stateWriteBlocked']")
  : >"$STATE"
  wait_for unparsed 10 pf "['stateWriteBlocked']" >/dev/null || true
  ep2=$(pf "['stateWriteBlocked']")
  add=$(qa_json_field "d['code']" "$(ipc addSource "$D" "" "")")
  sleep 1.0
  ck "B9 two no-write episodes in ONE session, no own save between: the lift re-arms the notice, so the second is told again (two notices, each naming the file), and an in-app add in it is refused with the file left as the damage left it" \
     "episodes:$ep1/[$lift]/$ep2 told:$told1/$(qa_count ' 74017 ' "$NOTIFY_LOG") path:$(qa_count ' 74017 .*state\.json' "$NOTIFY_LOG") add:$add file:$([[ -s $STATE ]] && echo written || echo same) urls:$(qa_count '://' "$NOTIFY_LOG")" \
     "episodes:unparsed/[]/unparsed told:1/2 path:2 add:state_unreadable file:same urls:0"
  cat "$WORK/good-state.json" >"$STATE"
  wait_for "" 10 pf "['stateWriteBlocked']" >/dev/null || true

  # R23c. The start-up `state init` held for 60 s by the slow tree (O's
  # staging: fixtures/slow-helper.py sleeps, then execs the real helper)
  # over a file that does not parse, so the load WAITS on the init's
  # witness. The service's watchdog stops it at stateInitTimeoutMs (15 s),
  # QProcess reaps it, and the held load decides as the no-write mode with
  # its own reason. The helper's pid is read from the process table by its
  # exact argv -- argv[1] is the slow tree's helper and the verb is `init` --
  # by a scanner whose own argv[1] is `-c`, so it can never match itself.
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  printf '{"version": 2, "sources": [' >"$STATE"; chmod 0600 "$STATE"
  sha0=$(sha "$STATE")
  if [[ ! -x $SLOW_TREE/bin/omarchy-iptv ]]; then echo "   the slow tree from O is not staged"; fi
  export OMARCHY_IPTV_PLUGIN_ROOT=$SLOW_TREE OMARCHY_IPTV_SLOW_MS=60000 OMARCHY_IPTV_SLOW_VERBS="state init"
  log_mark
  h --detach --timeout 0 --keep --playlist none --source-key "$KA" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  initpid=""
  for ((i = 0; i < 50; i++)); do initpid=$(init_pids "$SLOW_TREE/bin/omarchy-iptv" "$(dirname "$STATE")"); [[ -n $initpid ]] && break; sleep 0.1; done
  ORPHANS="$ORPHANS $initpid"
  echo "   slow init helper pid ${initpid:-none}"
  # A wall-clock deadline, not an iteration count: each poll is an IPC
  # round trip, and 300 of them took over a minute on lane-key-n2, long
  # enough for the slow init to finish by itself.
  deadline=$((SECONDS + 25))
  while (( SECONDS < deadline )); do [[ $(pf "['stateWriteBlocked']") =~ ^[a-z] ]] && break; sleep 0.1; done
  (( SECONDS >= deadline )) && echo "   gave up after 25 s waiting for the no-write mode"
  sleep 2.5
  gone=yes; for p in $initpid; do kill -0 "$p" 2>/dev/null && gone="no($p)"; done
  [[ -z $initpid ]] && gone=never-seen
  left=$(init_pids "$SLOW_TREE/bin/omarchy-iptv" "$(dirname "$STATE")")
  ck "B10 a start-up init that never answers is STOPPED by the service's watchdog and reaped -- no process left anywhere running it -- and the held load decides as the no-write mode with its own reason, told once by a sentence that names the file, the file untouched" \
     "blocked:$(pf "['stateWriteBlocked']") found:$(pf "['stateInitFound']") helper:$gone left:${left:-none} told:$(qa_count ' 74017 ' "$NOTIFY_LOG") stopped:$(qa_count ' 74017 .*state\.json .*stopped' "$NOTIFY_LOG") file:$([[ $(sha "$STATE") == "$sha0" ]] && echo same || echo changed) watchdog:$(log_since 'state init exceeded')" \
     "blocked:init-timeout found:timeout helper:yes left:none told:1 stopped:1 file:same watchdog:1"
  for p in $left; do kill -KILL "$p" 2>/dev/null; done
  stop_shell
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT; unset OMARCHY_IPTV_SLOW_MS OMARCHY_IPTV_SLOW_VERBS

  # R23e / R23h / R23f. A no-write START (the file does not parse, the real
  # tree): the guide is opened and what it DRAWS is read -- not the
  # first-run form, but the notification's own title and body -- and the
  # logo toggle in Sources, which round 12 answered "Could not save settings
  # - try omarchy bar set", answers the no-write sentence.
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  printf '{"version": 2, "sources": [' >"$STATE"; chmod 0600 "$STATE"
  log_mark
  h --detach --timeout 0 --keep --playlist none --source-key "$KA" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  for ((i = 0; i < 200; i++)); do [[ $(pf "['stateWriteBlocked']") =~ ^[a-z] ]] && break; sleep 0.1; done
  ipc open '{}' >/dev/null; sleep 0.8
  gs=$(ipc state)
  want_title=$(notice_of unparsed "$STATE" title); want_body=$(notice_of unparsed "$STATE" body)
  ck "B11 a no-write START draws its own surface, not the first-run form: no form and NO editable input anywhere under the guide (D-CLIP-1), the empty state shown, its title and prose the NOTIFICATION's own words (Model.stateUnreadableNotice), and that notification sent once" \
     "kind:$(qa_json_field "d['guide']['emptyKind']" "$gs") form:$(qa_json_field "d['guide']['firstRunForm']" "$gs") editable:$(qa_json_field "d['editable']" "$(ipc editable)") shown:$(qa_json_field "d['guide']['emptyShown']" "$gs") title:$([[ $(qa_json_field "d['guide']['emptyTitle']" "$gs") == "$want_title" ]] && echo notice || echo other) prose:$([[ $(qa_json_field "d['guide']['emptyProse']" "$gs") == "$want_body" ]] && echo notice || echo other) sent:$(grep -aF -c -- "$want_body" "$NOTIFY_LOG")" \
     "kind:stateUnreadable form:false editable:0 shown:true title:notice prose:notice sent:1"
  ipc sourcesKey enter >/dev/null; sleep 0.3
  ipc sourcesKey g >/dev/null; sleep 0.3
  ipc sourcesKey confirm >/dev/null; sleep 0.5
  foot=$(qa_json_field "d['guide']['footer']" "$(ipc state)")
  ck "B12 in that mode the logo toggle's refusal says the no-write reason, never the persist_failed advice (omarchy bar set)" \
     "says:$([[ $foot == *"state.json could not be read"* ]] && echo no-write || echo other) advice:$([[ $foot == *"omarchy bar set"* ]] && echo bar-set || echo none) writes:$(log_since 'updateEntryInline')" \
     "says:no-write advice:none writes:0"
  ipc close >/dev/null
  stop_shell

  # R23h, the control the instrument fix needs: a FRESH install's guide
  # draws the first-run form, and the drawn-copy fields now read THAT
  # form's sentence -- round 12's read the hidden empty state's.
  h clean >/dev/null 2>&1
  start_shell --playlist none --source-key "" || true
  ipc open '{}' >/dev/null; sleep 0.8
  gs=$(ipc state)
  # The census is the control here: the form's fields exist and are all
  # read-only (D-CLIP-1), so a field made editable reads editable:1 -- seen
  # with spikes/key-mutations/r23e-editable-field.patch.
  ck "B13 a fresh install's guide draws the first-run form, the drawn-copy fields read what that form draws (its title and the paste-or-type prose), not the hidden empty state's, and the form's fields are all read-only" \
     "form:$(qa_json_field "d['guide']['firstRunHead']" "$gs") editable:$(qa_json_field "d['editable']" "$(ipc editable)") title:$(qa_json_field "d['guide']['emptyTitle']" "$gs") prose:$(qa_json_field "d['guide']['emptyProse']" "$gs")" \
     "form:true editable:0 title:No playlist configured prose:Paste or type your M3U URL or path, then press Enter"
  ipc close >/dev/null
  stop_shell

  # R23b. A FIFO at state.json: the real helper's init answers at once
  # (`other`, never a blocking open), the load (FileView: NotAFile) blocks
  # as `not-a-file`, the user is told once, and no helper is left running.
  # On a tree whose init blocks in open(), the start waits for ever and the
  # helper outlives the shell: its pid is recorded for cleanup.
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  rm -f "$STATE"; mkfifo -m 600 "$STATE"
  log_mark
  h --detach --timeout 0 --keep --playlist none --source-key "$KA" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  deadline=$((SECONDS + 10))
  while (( SECONDS < deadline )); do [[ $(pf "['stateWriteBlocked']") =~ ^[a-z] ]] && break; sleep 0.1; done
  (( SECONDS >= deadline )) && echo "   gave up after 10 s waiting for the no-write mode"
  sleep 0.5
  left=$(init_pids "$PLUGIN_ROOT/bin/omarchy-iptv" "$(dirname "$STATE")"); ORPHANS="$ORPHANS $left"
  ck "B14 a FIFO at state.json: the init answers at once (found, not hung), the start blocks as not-a-file, the user is told once, no helper is left running, and the FIFO is left as it was" \
     "blocked:$(pf "['stateWriteBlocked']") found:$(pf "['stateInitFound']") told:$(qa_count ' 74017 ' "$NOTIFY_LOG") left:${left:-none} fifo:$([[ -p $STATE ]] && stat -c %a "$STATE" || echo gone)" \
     "blocked:not-a-file found:present told:1 left:none fifo:600"
  stop_shell
  for p in $left; do kill -KILL "$p" 2>/dev/null; done
  rm -f "$STATE"

  echo "== B, round 14: the fresh install's first session sees external changes (R24c), Sources in the no-write mode (R24f), the KILL half of the start-up bound (R24g) and the init's own deadline (R24d) ($(elapsed) s)"
  # R24f (D-SRC-28). The no-write START again (the file does not parse),
  # and this time Sources: round 13 drew "No sources" over "Add source" and
  # "Add Xtream login" while the file held two records, and `a` opened a
  # read-only form whose submit could only be refused.
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  printf '{"version": 2, "sources": [' >"$STATE"; chmod 0600 "$STATE"
  log_mark
  h --detach --timeout 0 --keep --playlist none --source-key "$KA" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  for ((i = 0; i < 200; i++)); do [[ $(pf "['stateWriteBlocked']") =~ ^[a-z] ]] && break; sleep 0.1; done
  ipc open '{}' >/dev/null; sleep 0.8
  ipc sourcesKey enter >/dev/null; sleep 0.4
  gs=$(ipc state)
  want_title=$(notice_of unparsed "$STATE" title)
  hdr=$(qa_json_field "d['guide']['headerRight']" "$gs"); hints=$(qa_json_field "d['guide']['footerHints']" "$gs")
  m1=$(qa_json_field "d['guide']['mode']" "$gs"); rows=$(qa_json_field "d['guide']['sourceRows']" "$gs")
  ipc sourcesKey a >/dev/null; sleep 0.4
  gs=$(ipc state)
  ck "B15 a no-write START's Sources screen: its header is the notice's title (Model.stateUnreadableNotice), not \"No sources\"; no Add rows are drawn and no add key is hinted; \`a\` opens no form, says the no-write reason, and nothing editable exists" \
     "mode:$m1 header:$([[ $hdr == "$want_title" ]] && echo notice || echo "[$hdr]") rows:$rows addhint:$([[ $hints == *" add"* || $hints == *"Xtream"* ]] && echo yes || echo no) after-a:$(qa_json_field "d['guide']['mode']" "$gs") says:$([[ $(qa_json_field "d['guide']['footer']" "$gs") == *"state.json could not be read"* ]] && echo no-write || echo other) editable:$(qa_json_field "d['editable']" "$(ipc editable)")" \
     "mode:sources header:notice rows:0 addhint:no after-a:sources says:no-write editable:0"
  ipc close >/dev/null
  stop_shell

  # R24c (D-SRC-19, D-DOC-8). THE FIRST SESSION AFTER A FRESH INSTALL, in
  # the production shape: XDG_STATE_HOME present (run.sh makes it) and
  # omarchy-iptv/ under it ABSENT (h clean removed it). The round-13 live
  # lens measured that such a session NEVER reloads -- a hand-run `state
  # source add` unseen and then written over by the next in-app save,
  # in-place garbage unnoticed -- and spikes/filewatch (set r24) that one
  # explicit reload() after the start-up mkdir/init re-arms the watch.
  : >"$NOTIFY_LOG"
  (( SHELL_STARTED )) && stop_shell
  h clean >/dev/null 2>&1
  start_shell --playlist none --source-key "" || true
  shape="first-load:$(pf "['stateReloadsByReason']['first-load']") found:$(pf "['stateInitFound']")"
  wait_for true 20 pf "['dirsReady']" >/dev/null || true
  python3 "$PLUGIN_ROOT/bin/omarchy-iptv" state --state-dir "$(dirname "$STATE")" source add --url "$C" >/dev/null 2>&1; hrc=$?
  wait_for 1 10 qa_json_field 'len(d)' "$(ipc sources)" >/dev/null 2>&1 || true
  for ((i = 0; i < 100; i++)); do [[ $(qa_json_field 'len(d)' "$(ipc sources)") == 1 ]] && break; sleep 0.1; done
  seen=$(qa_json_field 'len(d)' "$(ipc sources)")
  res=$(ipc addSource "$D" "" "")
  wait_for "$KD" 20 svc "['activeSourceKey']" >/dev/null || true
  sleep 1.0
  kept=$(sj "','.join(sorted('C' if s['key'] == '$KC' else 'D' if s['key'] == '$KD' else '?' for s in d['sources']))")
  printf 'garbage{' >"$STATE"
  wait_for unparsed 10 pf "['stateWriteBlocked']" >/dev/null || true
  ck "B16 the FRESH install's first session (state directory absent at the first load): a hand-run \`state source add\` is SEEN, the next in-app add's save KEEPS it, and garbage written in place is NOTICED (the no-write mode, told once)" \
     "$shape helper:$hrc seen:$seen add:$(qa_json_field "d['ok']" "$res") file:$kept blocked:$(pf "['stateWriteBlocked']") told:$(qa_count ' 74017 ' "$NOTIFY_LOG")" \
     "first-load:1 found:absent helper:0 seen:1 add:true file:C,D blocked:unparsed told:1"
  stop_shell

  # R24g (F-HARNESS-24). The KILL half of the start-up bound, observed: the
  # slow tree's init IGNORES SIGTERM (fixtures/slow-helper.py,
  # OMARCHY_IPTV_SLOW_IGNORE_TERM=1, inherited across exec), so only the
  # service's KILL after stateInitKillGraceMs can end it. Seen red with the
  # KILL deleted: spikes/key-mutations/r24g-no-kill.patch (--tree).
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  printf '{"version": 2, "sources": [' >"$STATE"; chmod 0600 "$STATE"
  sha0=$(sha "$STATE")
  export OMARCHY_IPTV_PLUGIN_ROOT=$SLOW_TREE OMARCHY_IPTV_SLOW_MS=60000 OMARCHY_IPTV_SLOW_VERBS="state init" OMARCHY_IPTV_SLOW_IGNORE_TERM=1
  log_mark
  h --detach --timeout 0 --keep --playlist none --source-key "$KA" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  initpid=""
  for ((i = 0; i < 50; i++)); do initpid=$(init_pids "$SLOW_TREE/bin/omarchy-iptv" "$(dirname "$STATE")"); [[ -n $initpid ]] && break; sleep 0.1; done
  ORPHANS="$ORPHANS $initpid"
  echo "   TERM-ignoring init helper pid ${initpid:-none}"
  deadline=$((SECONDS + 28))
  while (( SECONDS < deadline )); do [[ $(pf "['stateWriteBlocked']") =~ ^[a-z] ]] && break; sleep 0.1; done
  (( SECONDS >= deadline )) && echo "   gave up after 28 s waiting for the no-write mode"
  sleep 1.0
  gone=yes; for p in $initpid; do kill -0 "$p" 2>/dev/null && gone="no($p)"; done
  [[ -z $initpid ]] && gone=never-seen
  left=$(init_pids "$SLOW_TREE/bin/omarchy-iptv" "$(dirname "$STATE")")
  ck "B17 a start-up init that IGNORES the TERM is KILLed after the grace and reaped -- no process left -- and the held load decides as the no-write mode, told once, the file untouched" \
     "blocked:$(pf "['stateWriteBlocked']") helper:$gone left:${left:-none} told:$(qa_count ' 74017 ' "$NOTIFY_LOG") file:$([[ $(sha "$STATE") == "$sha0" ]] && echo same || echo changed) watchdog:$(log_since 'state init exceeded') killed:$(log_since 'state init ignored the terminate signal, killing it')" \
     "blocked:init-timeout helper:yes left:none told:1 file:same watchdog:1 killed:1"
  for p in $left; do kill -KILL "$p" 2>/dev/null; done
  stop_shell
  unset OMARCHY_IPTV_SLOW_IGNORE_TERM

  # R24d (D-SRC-24). The shell stopped INSIDE the bound: round 13's live
  # lens stopped it 5 s after the start with the init held and found the
  # init reparented to the user's service manager, alive for as long as the
  # hold lasted. Here the hold is INSIDE the real helper's own code
  # (OMARCHY_IPTV_SLOW_AT=inside: its first lstat of state.json sleeps 60
  # s), so the verb's own SIGALRM self-deadline (STATE_INIT_DEADLINE, 30 s)
  # is what ends it. Polled to the init's start plus 36 s, by its recorded
  # pid; on a tree without the self-deadline it outlives that and is killed
  # by cleanup through ORPHANS.
  seed "$KA" migrated
  export OMARCHY_IPTV_PLUGIN_ROOT=$SLOW_TREE OMARCHY_IPTV_SLOW_MS=60000 OMARCHY_IPTV_SLOW_VERBS="state init" OMARCHY_IPTV_SLOW_AT=inside
  t_start=$SECONDS
  h --detach --timeout 0 --keep --playlist none --source-key "$KA" >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  initpid=""
  for ((i = 0; i < 50; i++)); do initpid=$(init_pids "$SLOW_TREE/bin/omarchy-iptv" "$(dirname "$STATE")"); [[ -n $initpid ]] && break; sleep 0.1; done
  t_init=$SECONDS
  ORPHANS="$ORPHANS $initpid"
  while (( SECONDS < t_start + 5 )); do sleep 0.2; done
  stop_shell
  atstop=gone; for p in $initpid; do kill -0 "$p" 2>/dev/null && atstop=alive; done
  parent=$(ps -o ppid= -p "${initpid:-0}" 2>/dev/null | tr -d ' ')
  echo "   held init pid ${initpid:-none} after the shell stopped at 5 s: $atstop (parent ${parent:-none})"
  deadline=$((t_init + 36))
  while (( SECONDS < deadline )); do
    alive=no; for p in $initpid; do kill -0 "$p" 2>/dev/null && alive=yes; done
    [[ $alive == no ]] && break
    sleep 0.5
  done
  after=gone; for p in $initpid; do kill -0 "$p" 2>/dev/null && after="alive($p)"; done
  [[ -z $initpid ]] && after=never-seen
  left=$(init_pids "$SLOW_TREE/bin/omarchy-iptv" "$(dirname "$STATE")"); ORPHANS="$ORPHANS $left"
  ck "B18 the shell stopped 5 s into a held start-up init: the init outlives the shell, and then ENDS by its own deadline -- nothing left running 36 s after it started" \
     "at-stop:$atstop after-deadline:$after left:${left:-none}" \
     "at-stop:alive after-deadline:gone left:none"
  for p in $initpid $left; do kill -KILL "$p" 2>/dev/null; done
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT; unset OMARCHY_IPTV_SLOW_MS OMARCHY_IPTV_SLOW_VERBS OMARCHY_IPTV_SLOW_AT
  fi   # --only: end of Y .. B18

  if seg_on B19; then   # --only B19 begins
  [[ -n $ONLY ]] && echo "== B19 alone (--only): R24a's merge, live ($(elapsed) s)"
  # R25d (F-HARNESS-26): R24a OBSERVED. The round-14 data-loss lens found
  # that nothing live watched the merge: two of its decisions (a5, the base
  # moved to theirs; a7, the in-flight re-save) survived every check. The
  # state directory loses `w` under the running shell (F's staging), so the
  # FileView's atomic save fails and the in-app label change is HELD; two
  # hand edits IN PLACE (an existing 0600 file needs no directory `w`) add a
  # favourite and take it away again inside that one held window -- the
  # second compared with the base the first moved it to (a5); then a
  # hand-run helper write, which makes the directory 0700 again
  # (ensure_private_dir) and lands; then a second in-app change. Both in-app
  # changes and the helper's favourite must be in the file, the favourite
  # the hand edits removed must stay removed, and a restart stands on all
  # of it. Seen red through spikes/key-mutations/r25d-a5-base-not-moved.patch.
  # Every foreign write MERGED, whichever hold it met (a save failed, or the
  # merge's own re-save still in flight when the next write lands).
  merges() { qa_json_field "sum(v for k, v in d['stateReloadsByReason'].items() if k.startswith('foreign-'))" "$(ipc pointerState)"; }
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  start_shell --playlist none --source-key "$KA" || true
  # start_shell returns once the state loaded and the cache is ready, which
  # can be BEFORE the start-up `state init` has run -- and the init makes
  # the directory 0700 again (ensure_private_dir). The first live run of
  # this segment took `w` away inside that window and saw no failure
  # (`held:false merged:0`). So: after dirsReady.
  # F-HARNESS-49 (2026-10-27): and after the start SETTLES (wait_settled),
  # because dirsReady stopped being enough. D-SRC-49 (9203141, the P2/P3
  # sweep) runs the helper's `state mode` after every save that LANDS, and
  # it puts the state folder back to 0700 -- by design: the folder is the
  # plugin's own, and `state init` at every start and every helper write
  # already did the same. Observed at idle on dev 45bded9 (the shell's
  # children from /proc, the folder's chmods by inotify): the `state mode`
  # the start's own landed save asked for began 340 ms before this chmod,
  # was still starting under the start-up load when the chmod landed, and
  # put 0700 back 75 ms after it; the shell logged "state.json's mode was
  # repaired after a save (file kept, folder changed)", the in-app save
  # LANDED, and B19 read `held:false merged:0`: no merge was exercised at
  # all, and the outcome it printed was the outcome of no hold. A repair
  # landing later, mid-window, is the `merged:2`, `:1`, `:1` the lanes read
  # under load on 2026-10-26. A save that fails asks for no repair, so once
  # nothing is in flight at the chmod the hold stands until the helper's own
  # write gives the folder back. And the hold is the PREMISE, checked on its
  # own below: without it B19 has observed nothing, and says so.
  wait_settled || true
  pre19="folder:$(stat -c %a "$(dirname "$STATE")") jobs:[$(helper_jobs)]"
  repairs0=$(log_since 'mode was repaired after a save')
  chmod 0500 "$(dirname "$STATE")"
  res=$(ipc updateSource "$KC" '{"label": "in-app-one"}')
  wait_for true 10 pf "['stateSaveFailed']" >/dev/null || true
  held="$(pf "['stateSaveFailed']")"
  premise="held:$held folder:$(stat -c %a "$(dirname "$STATE")") repaired:+$(( $(log_since 'mode was repaired after a save') - repairs0 ))"
  echo "   B19 premise: settled with $pre19; after the in-app change $premise"
  python3 -c 'import json, sys; p = sys.argv[1]; d = json.load(open(p)); d["favorites"] = d.get("favorites", []) + ["t:h3.uk"]; open(p, "w").write(json.dumps(d) + "\n")' "$STATE"
  wait_for 1 10 merges >/dev/null || true
  python3 -c 'import json, sys; p = sys.argv[1]; d = json.load(open(p)); d["favorites"] = [f for f in d.get("favorites", []) if f != "t:h3.uk"]; open(p, "w").write(json.dumps(d) + "\n")' "$STATE"
  wait_for 2 10 merges >/dev/null || true
  python3 "$PLUGIN_ROOT/bin/omarchy-iptv" state --state-dir "$(dirname "$STATE")" favorite add t:helper.uk >/dev/null 2>&1; hrc=$?
  wait_for false 10 pf "['stateSaveFailed']" >/dev/null || true
  res2=$(ipc updateSource "$KA" '{"label": "in-app-two"}')
  sleep 1.5
  labels() { sj "','.join(('A=' if s['key'] == '$KA' else 'C=' if s['key'] == '$KC' else '?=') + s['label'] for s in sorted(d['sources'], key=lambda s: s['key'] != '$KA'))"; }
  file1="labels:$(labels) favs:$(sj "','.join(d['favorites']) or '-'")"
  merged="$(merges)"
  stop_shell
  start_shell --playlist none --source-key "$KA" || true
  sleep 0.5
  outcome="edits:$(qa_json_field "d['ok']" "$res")/$(qa_json_field "d['ok']" "$res2") helper:$hrc merged:$merged $file1 restart:$(qa_json_field "','.join(sorted(s['label'] for s in d))" "$(ipc sources)")/$(sj "','.join(d['favorites']) or '-'")"
  # The premise first, and the outcome only on it. One assertion either way
  # (the fail line is the ck's other branch, as the probe's fallback lines
  # are the I lines'), so the floor's recipe counts one.
  if [[ $premise == "held:true folder:500 repaired:+0" ]]; then
  ck "B19 R24a live: an in-app change HELD by a failed save, two hand edits in place inside that window (a favourite added, then removed), a hand-run helper write, a second in-app change -- the file keeps BOTH in-app changes and the helper's favourite, the removed one stays removed, every foreign write was merged, and a restart stands on all of it" \
     "$outcome" \
     "edits:true/true helper:0 merged:3 labels:A=in-app-two,C=in-app-one favs:t:helper.uk restart:in-app-one,in-app-two/t:helper.uk"
  else
    fail "B19 R24a live: PREMISE NOT ESTABLISHED -- the in-app change's save was not held" "got [$premise], want [held:true folder:500 repaired:+0]: the folder was writable again when the save ran, so no merge was exercised and the outcome [$outcome] grades nothing"
  fi
  stop_shell
  fi   # --only B19 ends

  if [[ -z $ONLY ]]; then   # --only: B20 .. B40, full runs only
  # R25a (D-SRC-30): THE RESTORE OF A BACKUP TAKEN FROM THE PLUGIN'S OWN
  # FILE. The round-14 data-loss lens: a copy of state.json taken after an
  # in-app change had LANDED, then an in-app remove that landed, then the
  # copy put back in place -- the copy's text was one of the service's last
  # eight writes, so it was ignored as an echo and the next in-app save
  # wrote over the restore, silently. The echo is now only a text still in
  # flight. Red on dev (002662d), where it lives.
  seed "$KA" migrated
  start_shell --playlist none --source-key "$KA" || true
  wait_for true 20 pf "['dirsReady']" >/dev/null || true
  res=$(ipc updateSource "$KA" '{"label": "before-backup"}')
  for ((i = 0; i < 100; i++)); do [[ $(sj "[s['label'] for s in d['sources'] if s['key'] == '$KA'][0]") == before-backup && $(pf "['stateSavesInFlight']") == 0 ]] && break; sleep 0.1; done
  sleep 1.0
  cp "$STATE" "$WORK/backup.json"
  res2=$(ipc removeSource "$KC")
  wait_for 1 10 sj "len(d['sources'])" >/dev/null || true
  sleep 1.0
  afterdel=$(sj "len(d['sources'])")
  cat "$WORK/backup.json" >"$STATE"
  for ((i = 0; i < 100; i++)); do [[ $(pf "['sourceCount']") == 2 ]] && break; sleep 0.1; done
  restored="$(pf "['sourceCount']")"
  res3=$(ipc updateSource "$KA" '{"label": "after-restore"}')
  sleep 1.5
  file2="records:$(sj "len(d['sources'])") label:$(sj "[s['label'] for s in d['sources'] if s['key'] == '$KA'][0]")"
  stop_shell
  start_shell --playlist none --source-key "$KA" || true
  sleep 0.5
  ck "B20 R25a: a backup copied from the plugin's own file AFTER its save landed, put back in place after an in-app remove landed, is another writer's: memory takes it back (2 sources), the next in-app save keeps it, and a restart stands on it" \
     "edits:$(qa_json_field "d['ok']" "$res")/$(qa_json_field "d['ok']" "$res2")/$(qa_json_field "d['ok']" "$res3") after-remove:$afterdel restored:$restored $file2 restart:$(qa_json_field 'len(d)' "$(ipc sources)")" \
     "edits:true/true/true after-remove:1 restored:2 records:2 label:after-restore restart:2"
  stop_shell

  # R25d (D-DOC-9's open half): the EXISTING-folder session damaged AFTER an
  # own save. B5..B7 and B9 damage a session that has saved nothing of its
  # own yet, and B16 is the fresh-install shape; the round-14 lane recorded
  # that no segment observed this one. A migrated install starts (its
  # directory present at the first load), an in-app change's save LANDS,
  # and then garbage is written in place: the FileView must still be
  # watching. Seen red through spikes/key-mutations/r25d-no-reload-on-change.patch
  # (stateFile's `onFileChanged: reload()` deleted). And D-SRC-38: the
  # Sources header in that MID-session block says saving stopped -- red on
  # dev, where it said the sources were not loaded over rows still listed.
  : >"$NOTIFY_LOG"
  seed "$KA" migrated
  start_shell --playlist none --source-key "$KA" || true
  wait_for true 20 pf "['dirsReady']" >/dev/null || true
  res=$(ipc updateSource "$KC" '{"label": "own-save"}')
  for ((i = 0; i < 100; i++)); do [[ $(sj "[s['label'] for s in d['sources'] if s['key'] == '$KC'][0]") == own-save && $(pf "['stateSavesInFlight']") == 0 ]] && break; sleep 0.1; done
  sleep 1.0
  landed1="$(sj "[s['label'] for s in d['sources'] if s['key'] == '$KC'][0]")"
  printf 'garbage{' >"$STATE"
  wait_for unparsed 10 pf "['stateWriteBlocked']" >/dev/null || true
  ck "B21 the EXISTING-folder session damaged AFTER an own save landed: the garbage written in place is noticed (the no-write mode, told once), the file left as the user wrote it" \
     "edit:$(qa_json_field "d['ok']" "$res") landed:$landed1 blocked:$(pf "['stateWriteBlocked']") told:$(qa_count ' 74017 ' "$NOTIFY_LOG") file:$(head -c 8 "$STATE")" \
     "edit:true landed:own-save blocked:unparsed told:1 file:garbage{"
  ipc open '{}' >/dev/null; sleep 0.8
  ipc sourcesKey enter >/dev/null; sleep 0.4
  gs=$(ipc state)
  ck "B22 D-SRC-38: in that MID-session block the Sources header says saving has stopped, above the session's own rows -- not that the sources were not loaded" \
     "mode:$(qa_json_field "d['guide']['mode']" "$gs") header:$(qa_json_field "d['guide']['headerRight']" "$gs") rows:$(qa_json_field "d['guide']['sourceRows']" "$gs")" \
     "mode:sources header:Saving has stopped rows:2"
  # R27e (2026-10-20, D-SRC-42): and the NOTIFICATION that block sent is
  # titled so too -- the one sentence family, at the sink (the stand-in
  # omarchy-notification-send's argv). Red on 6f1d176, which titled every
  # block "Saved sources not loaded".
  # R28e (2026-10-20): the body's second sentence is the MID-session one,
  # which names the ways back on which a change made now is dropped.
  ck "B32 R27e (D-SRC-42) / R28e: the notification of that MID-session block is titled \"Saving has stopped\" and its body says changes made now are held in this session only, and when they are dropped" \
     "saving-stopped:$(qa_count ' 74017 Saving has stopped ' "$NOTIFY_LOG") not-loaded:$(qa_count ' 74017 Saved sources not loaded ' "$NOTIFY_LOG") body:$(qa_count 'are held in this session only: the next such change made here saves them if it finds the file again, but they are dropped if the file comes back by itself first' "$NOTIFY_LOG")" \
     "saving-stopped:1 not-loaded:0 body:1"
  ipc close >/dev/null
  stop_shell

  echo "== B, R26: read before write -- a linked state.json replaced three ways and re-pointed, the state folder link re-pointed at another state and at an EMPTY folder, a link target that comes back, a save asked for inside a load, and an idle shell (R26a, R26b, R26d) ($(elapsed) s)"
  # D-SINK-19 R26 (the lead's ruling of 2026-10-16). The FileView's watch is
  # lost WITHOUT a signal when the path is replaced or re-pointed (measured
  # on a bare FileView: spikes/filewatch-links on lane-clean-w-probe), so
  # before R26 the next in-app save was the first the session knew of it: it
  # wrote memory over the hand edit (D-SRC-29), over another state the link
  # now named (D-SRC-29, D-SRC-40), or created a 0644 state.json carrying
  # every source URL in an empty folder (D-SINK-21). Every save now READS
  # first and decides through the dispositions every load already has. The
  # segments are lane W's service rig made checks: S29-mv, S29-sed,
  # S29-rmcp, S29-ln (B23..B26), S40 (B27), S21 (B28), S35 (B29), INLOAD
  # (B30, D-SRC-46) and IDLE (B31). Each is seen red on dev 1c88877
  # (--baseline) and by one decision through --tree: r26a-no-read.patch
  # (B23..B28 and B31's save half), r26b-no-defer.patch (B30),
  # r26a-no-verb-recheck.patch (B29) and r26d-periodic-reload.patch (B31's
  # idle half, which no earlier tree can red: none reloads while idle),
  # under spikes/key-mutations/.
  # FRESH (a replacement with no save after it) is the stated gap and has no
  # check here: R26d refuses a periodic reload, and B31 is what proves none.
  LINKS="$WORK/links"
  SDIR=$(dirname "$STATE")
  # A state with custom labels (a derived label is re-derived on load, and
  # the hand edits below change A's) and one favourite, from the seed's own
  # records: r26_state LABEL-A FAVOURITE >file
  r26_state() {
    python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
for s in d["sources"]:
    s["labelCustom"] = True
    if s["key"] == sys.argv[2]: s["label"] = sys.argv[4]
    if s["key"] == sys.argv[3]: s["label"] = "c-seven"
d["favorites"] = [sys.argv[5]]
print(json.dumps(d))' "$WORK/r26-seed.json" "$KA" "$KC" "$1" "$2"
  }
  # Every R26 segment starts from seed, then arranges the links:
  #   flink  state.json is a link to links/T1/state.json; T2 holds another state
  #   dlink  the state FOLDER is a link to links/F1; F2 holds another state;
  #          F3 is EMPTY, made by plain mkdir under this shell's umask
  #   dir    the plain folder, the seed rewritten as r26_state
  seed_r26() {
    seed "$KA" migrated
    cp "$STATE" "$WORK/r26-seed.json"
    rm -rf "$LINKS"; mkdir -m 0700 "$LINKS"
    case $1 in
      flink) mkdir -m 0700 "$LINKS/T1" "$LINKS/T2"
             r26_state seed t:seed.uk >"$LINKS/T1/state.json"; r26_state t2-own t:t2.uk >"$LINKS/T2/state.json"
             chmod 0600 "$LINKS/T1/state.json" "$LINKS/T2/state.json"
             rm -f "$STATE"; ln -s "$LINKS/T1/state.json" "$STATE" ;;
      dlink) mkdir -m 0700 "$LINKS/F1" "$LINKS/F2"; mkdir "$LINKS/F3"
             r26_state seed t:seed.uk >"$LINKS/F1/state.json"; r26_state f2-own t:f2.uk >"$LINKS/F2/state.json"
             chmod 0600 "$LINKS/F1/state.json" "$LINKS/F2/state.json"
             rm -rf "$SDIR"; ln -s "$LINKS/F1" "$SDIR" ;;
      dir)   r26_state seed t:seed.uk >"$STATE"; chmod 0600 "$STATE" ;;
    esac
  }
  # What a state file holds: A's label, C's label, the favourites (keys and
  # labels only, never a URL); NOFILE when there is none.
  r26_info() {
    python3 -c 'import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("NOFILE"); raise SystemExit(0)
lab = {s["key"]: s["label"] for s in d.get("sources", [])}
print("A=%s,C=%s,favs=%s" % (lab.get(sys.argv[2], "-"), lab.get(sys.argv[3], "-"), "+".join(d.get("favorites", [])) or "-"))' "$1" "$KA" "$KC" 2>/dev/null || echo NOFILE
  }
  # The session's own labels, from the sources answer.
  r26_mem() {
    qa_json_field "','.join(('A=' if s.get('id', s.get('key')) == '$KA' else 'C=' if s.get('id', s.get('key')) == '$KC' else '?=') + str(s.get('label')) for s in sorted(d, key=lambda s: s.get('id', s.get('key')) != '$KA'))" "$(ipc sources)"
  }
  # A hand edit of the file at $1, as JSON on stdout: A's label $2, favourite $3 added.
  r26_hand() {
    python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
for s in d["sources"]:
    if s["key"] == sys.argv[2]: s["label"] = sys.argv[3]
d["favorites"].append(sys.argv[4])
print(json.dumps(d))' "$1" "$KA" "$2" "$3"
  }
  # Bounded: until the file at $1 names C's label $2, then until nothing of
  # ours is outstanding (6 s; a tree that never writes it is reported by the
  # check that follows, not waited on).
  r26_landed() {
    local i
    for ((i = 0; i < 60; i++)); do [[ $(r26_info "$1") == *",C=$2,"* ]] && break; sleep 0.1; done
    for ((i = 0; i < 30; i++)); do [[ $(pf "['stateSavesInFlight']") == 0 && $(pf "['stateSavePending']") == false ]] && break; sleep 0.1; done
    sleep 0.3
  }
  r26_start() { start_shell --playlist none --source-key "$KA" || true; wait_for true 20 pf "['dirsReady']" >/dev/null || true; sleep 0.5; }
  okf() { qa_json_field "d['ok']" "$1"; }

  # B23..B25: S29 -- the link REPLACED at the path, three ways, each carrying
  # a hand edit (A's label, a favourite), a second, then an in-app save of C.
  # r26_replace leaves the shell running and the call's answer in R26_RES.
  r26_replace() {
    local kind=$1
    seed_r26 flink; r26_start
    case $kind in
      mv)   r26_hand "$STATE" hand-mv t:hand.uk >"$SDIR/.r26.tmp"; mv -f "$SDIR/.r26.tmp" "$STATE" ;;
      sed)  sed -i 's/"label": "seed"/"label": "hand-sed"/; s/"t:seed.uk"/"t:seed.uk", "t:hand.uk"/' "$STATE" ;;
      rmcp) r26_hand "$STATE" hand-rmcp t:hand.uk >"$LINKS/copy.json"; rm -f "$STATE"; cp "$LINKS/copy.json" "$STATE" ;;
    esac
    sleep 1
    R26_RES=$(ipc updateSource "$KC" "{\"label\": \"app-$kind\"}")
    r26_landed "$STATE" "app-$kind"
    echo "   S29-$kind: path $([[ -L $STATE ]] && echo link || stat -c '%a %F' "$STATE" 2>/dev/null); verifies $(pf "['stateVerifies']"); reasons $(reasons)"
  }
  r26_replace mv
  ck "B23 R26a (D-SRC-29, S29-mv): the linked state.json REPLACED by a rename carrying a hand edit (no signal), then an in-app save: the save READ the file first and merged -- the file and memory hold both edits, the old target untouched" \
     "edit:$(okf "$R26_RES") disk:$(r26_info "$STATE") memory:$(r26_mem) old:$(r26_info "$LINKS/T1/state.json")" \
     "edit:true disk:A=hand-mv,C=app-mv,favs=t:seed.uk+t:hand.uk memory:A=hand-mv,C=app-mv old:A=seed,C=c-seven,favs=t:seed.uk"
  stop_shell
  r26_replace sed
  ck "B24 R26a (D-SRC-29, S29-sed): the linked state.json rewritten by sed -i (a rename over the link, no signal), then an in-app save: both edits kept" \
     "edit:$(okf "$R26_RES") disk:$(r26_info "$STATE") memory:$(r26_mem) old:$(r26_info "$LINKS/T1/state.json")" \
     "edit:true disk:A=hand-sed,C=app-sed,favs=t:seed.uk+t:hand.uk memory:A=hand-sed,C=app-sed old:A=seed,C=c-seven,favs=t:seed.uk"
  stop_shell
  r26_replace rmcp
  ck "B25 R26a (D-SRC-29, S29-rmcp): the link removed and a copy put in its place (no signal), then an in-app save: both edits kept" \
     "edit:$(okf "$R26_RES") disk:$(r26_info "$STATE") memory:$(r26_mem) old:$(r26_info "$LINKS/T1/state.json")" \
     "edit:true disk:A=hand-rmcp,C=app-rmcp,favs=t:seed.uk+t:hand.uk memory:A=hand-rmcp,C=app-rmcp old:A=seed,C=c-seven,favs=t:seed.uk"
  stop_shell

  # B26: S29-ln -- the link RE-POINTED at another state.
  seed_r26 flink; r26_start
  ln -sfn "$LINKS/T2/state.json" "$STATE"; sleep 1
  res=$(ipc updateSource "$KC" '{"label": "app-ln"}')
  r26_landed "$LINKS/T2/state.json" app-ln
  ck "B26 R26a (D-SRC-29 / D-SRC-40, S29-ln): the state.json link re-pointed (ln -sfn, no signal) at another state, then an in-app save: THAT file keeps its own label and favourite and takes the in-app edit; the old target is untouched; memory is the new file's" \
     "edit:$(okf "$res") new:$(r26_info "$LINKS/T2/state.json") old:$(r26_info "$LINKS/T1/state.json") memory:$(r26_mem)" \
     "edit:true new:A=t2-own,C=app-ln,favs=t:t2.uk old:A=seed,C=c-seven,favs=t:seed.uk memory:A=t2-own,C=app-ln"
  stop_shell

  # B27: S40 -- the state FOLDER link re-pointed at another folder's state.
  seed_r26 dlink; r26_start
  ln -sfn "$LINKS/F2" "$SDIR"; sleep 1
  res=$(ipc updateSource "$KC" '{"label": "app-fl"}')
  r26_landed "$LINKS/F2/state.json" app-fl
  ck "B27 R26a (D-SRC-40, S40): the state FOLDER link re-pointed (ln -sfn, no signal) at a folder holding another state, then an in-app save: that state keeps its own and takes the edit; the old folder's is untouched" \
     "edit:$(okf "$res") new:$(r26_info "$LINKS/F2/state.json") old:$(r26_info "$LINKS/F1/state.json") memory:$(r26_mem)" \
     "edit:true new:A=f2-own,C=app-fl,favs=t:f2.uk old:A=seed,C=c-seven,favs=t:seed.uk memory:A=f2-own,C=app-fl"
  stop_shell

  # B28: S21 -- the folder link re-pointed at an EMPTY folder. Before R26 the
  # save CREATED state.json there at 0666 & ~umask -- 0644, every source URL
  # in it -- and nothing noticed (D-SINK-21, measured by the sink lane). Now
  # the read finds nothing: the no-write mode, told once, nothing created;
  # the call that asked answered ok when its write was issued and the NEXT
  # call answers state_unreadable (R26e, stated).
  seed_r26 dlink; r26_start
  : >"$NOTIFY_LOG"
  ln -sfn "$LINKS/F3" "$SDIR"; sleep 1
  res=$(ipc updateSource "$KC" '{"label": "app-empty"}')
  wait_for absent 6 pf "['stateWriteBlocked']" >/dev/null || true
  sleep 0.5
  res2=$(ipc updateSource "$KC" '{"label": "app-empty-two"}')
  ck "B28 R26a (D-SINK-21, S21): the state FOLDER link re-pointed at an EMPTY folder, then an in-app save: NO file is created there (before R26: a 0644 state.json holding the session's sources), the no-write mode (absent), told once; the call that asked answered ok and the next answers state_unreadable" \
     "edit:$(okf "$res") created:$([[ -e $LINKS/F3/state.json ]] && stat -c %a "$LINKS/F3/state.json" || echo none) holds:[$(ls -A "$LINKS/F3" | tr '\n' ' ' | sed 's/ $//')] blocked:$(pf "['stateWriteBlocked']") told:$(qa_count ' 74017 ' "$NOTIFY_LOG") next:$(qa_json_field "d['code']" "$res2")" \
     "edit:true created:none holds:[] blocked:absent told:1 next:state_unreadable"
  stop_shell

  # B29: S35 -- a link's TARGET moved away (seen: the no-write mode), moved
  # back (unseen: a move back raises nothing), then two source calls. The
  # first is refused and asks for one reload (Model.stateBlockRecheck), which
  # lifts the mode; the second lands. Accepted and stated (R26a).
  seed_r26 flink; r26_start
  : >"$NOTIFY_LOG"
  mv "$LINKS/T1/state.json" "$LINKS/T1/away.json"
  wait_for absent 10 pf "['stateWriteBlocked']" >/dev/null || true
  away=$(pf "['stateWriteBlocked']")
  mv "$LINKS/T1/away.json" "$LINKS/T1/state.json"; sleep 1
  first=$(ipc updateSource "$KC" '{"label": "app-back"}')
  wait_for "" 5 pf "['stateWriteBlocked']" >/dev/null || true
  lifted=$(pf "['stateWriteBlocked']")
  second=$(ipc updateSource "$KC" '{"label": "app-back"}')
  r26_landed "$LINKS/T1/state.json" app-back
  ck "B29 R26a (D-SRC-35, S35): a link's target moved away (the no-write mode, told) and put back unseen: the FIRST source call is refused and its re-read lifts the mode; the SECOND lands" \
     "away:$away told:$(qa_count ' 74017 ' "$NOTIFY_LOG") first:$(qa_json_field "d['code']" "$first") lifted:[$lifted] second:$(okf "$second") disk:$(r26_info "$LINKS/T1/state.json")" \
     "away:absent told:1 first:state_unreadable lifted:[] second:true disk:A=seed,C=app-back,favs=t:seed.uk"
  stop_shell

  # B30: INLOAD (D-SRC-46, R26b) -- a save that FAILS (the folder 0500) is
  # held; the folder given back; a hand-run helper write lands while the
  # failure is held, so R24a merges INSIDE that load and asks for a save.
  # Issued inside stateFile's onLoaded, that write raised no `saved`: the
  # session read inFlight 1 and saveFailed true for good (lane W, 16 of 16,
  # and live on dev). Issued from a turn of its own, it is reported.
  # F-HARNESS-49, B19's sibling (rule 15): the same 0500 under a running
  # shell, the same D-SRC-49 repair able to undo it. r26_start's 0.5 s after
  # dirsReady outlasted the start's `state mode` at idle; nothing bounded
  # it under load. So: settled first, and the hold is the premise.
  seed_r26 dir; r26_start
  wait_settled || true
  repairs0=$(log_since 'mode was repaired after a save')
  chmod 0500 "$SDIR"
  res=$(ipc updateSource "$KC" '{"label": "app-fail"}')
  wait_for true 10 pf "['stateSaveFailed']" >/dev/null || true
  held=$(pf "['stateSaveFailed']")
  premise="held:$held folder:$(stat -c %a "$SDIR") repaired:+$(( $(log_since 'mode was repaired after a save') - repairs0 ))"
  chmod 0700 "$SDIR"
  python3 "$PLUGIN_ROOT/bin/omarchy-iptv" state --state-dir "$SDIR" favorite add t:helper.uk >/dev/null 2>&1; hrc=$?
  wait_for false 10 pf "['stateSaveFailed']" >/dev/null || true
  for ((i = 0; i < 30; i++)); do [[ $(pf "['stateSavesInFlight']") == 0 ]] && break; sleep 0.1; done
  sleep 1.0
  outcome="edit:$(okf "$res") helper:$hrc inFlight:$(pf "['stateSavesInFlight']") saveFailed:$(pf "['stateSaveFailed']") disk:$(r26_info "$STATE")"
  if [[ $premise == "held:true folder:500 repaired:+0" ]]; then
  ck "B30 R26b (D-SRC-46, INLOAD): a failed save held, the folder given back, a hand-run helper write: the merge's save, asked for inside that load, is issued from a turn of its own and REPORTED -- nothing in flight, the failure cleared, both on disk" \
     "$outcome" \
     "edit:true helper:0 inFlight:0 saveFailed:false disk:A=seed,C=app-fail,favs=t:seed.uk+t:helper.uk"
  else
    fail "B30 R26b (D-SRC-46, INLOAD): PREMISE NOT ESTABLISHED -- the in-app change's save was not held" "got [$premise], want [held:true folder:500 repaired:+0]: no load was asked to merge, and the outcome [$outcome] grades nothing"
  fi
  stop_shell

  # B31: IDLE (R26d) -- no periodic reload: 30 s of an idle shell reads the
  # file NOT ONCE (no load of any kind is counted), and one in-app save then
  # reads it exactly once before it writes.
  seed_r26 dir; r26_start
  sleep 1
  loads() { qa_json_field "sum(d['stateReloadsByReason'].values())" "$(ipc pointerState)"; }
  delta() { [[ $1 =~ ^[0-9]+$ && $2 =~ ^[0-9]+$ ]] && echo "+$(( $2 - $1 ))" || echo "$1->$2"; }
  l0=$(loads); v0=$(pf "['stateVerifies']")
  sleep 30
  l1=$(loads); v1=$(pf "['stateVerifies']")
  res=$(ipc updateSource "$KC" '{"label": "app-idle"}')
  r26_landed "$STATE" app-idle
  v2=$(pf "['stateVerifies']")
  ck "B31 R26d (IDLE): 30 s of an idle shell loads state.json NOT ONCE (no periodic reload); one in-app save then reads it once before it writes" \
     "idle-loads:$(delta "$l0" "$l1") idle-reads:$(delta "$v0" "$v1") edit:$(okf "$res") save-reads:$(delta "$v1" "$v2") disk:$(r26_info "$STATE")" \
     "idle-loads:+0 idle-reads:+0 edit:true save-reads:+1 disk:A=seed,C=app-idle,favs=t:seed.uk"
  stop_shell
  rm -rf "$LINKS"

  echo "== B, R27: no write without a read, the cap at the migration and at the probe commit (R27a, R27c, R27d) ($(elapsed) s)"
  # B33: R27a window (a). The harness's editDuringWrite makes a label edit
  # and asks a SECOND in the first turn after the service reports that
  # edit's write in flight. Before R27 that save skipped its read (the view
  # drops a reload while our write is out) and was written from the next
  # turn; now it waits for the write to land, reads, then writes. Whether a
  # re-point can be timed INSIDE that window from outside the shell: no --
  # the window is the few milliseconds between the first write landing and
  # the second's read, inside the shell's own turn order, and nothing a
  # process outside it does lands there on purpose. The node pins time it
  # (tests/Model.test.js, R27a window a, D-SINK-22); this observes the
  # ordering on the real FileView.
  seed_r26 dir; r26_start
  w0=$(pf "['stateSavesWaited']"); k0=$(pf "['stateVerifySkipped']")
  res=$(ipc editDuringWrite "$KC" w-one w-two)
  for ((i = 0; i < 50; i++)); do [[ $(qa_json_field "d['state']" "$(ipc editDuringWriteResult)") == asked ]] && break; sleep 0.1; done
  r26_landed "$STATE" w-two
  dw=$(ipc editDuringWriteResult)
  ck "B33 R27a (D-SINK-22 window a): a second in-app change asked while the first one's write is OUT waits for it to land and then reads -- nothing written without a read (skipped +0), the wait counted, the second edit on disk" \
     "first:$(okf "$res") asked-in-flight:$(qa_json_field "d['inFlightAtAsk']" "$dw") second:$(qa_json_field "d['secondOk']" "$dw") waited:$(delta "$w0" "$(pf "['stateSavesWaited']")") skipped:$(delta "$k0" "$(pf "['stateVerifySkipped']")") disk:$(r26_info "$STATE") mode:$(stat -c %a "$STATE")" \
     "first:true asked-in-flight:1 second:true waited:+1 skipped:+0 disk:A=seed,C=w-two,favs=t:seed.uk mode:600"
  # What the wait costs a BURST (R27a's measurement, not a check). N label
  # edits one a turn apart, timed in the shell from the first to the turn the
  # last has landed; the writes and the reads it made. It was a check (B34,
  # "lands whole, writes == reads") and is not one, by rule 11: AT IDLE it read
  # green on 6f1d176 too (no write of a burst was still out a turn later, so
  # the read was never skipped there either) and through
  # spikes/key-mutations/r27a-wait-never-released.patch (a later edit of the
  # burst picks the held one up). R28e: that is load-dependent -- under load
  # (round 1's review, load 5-8) 6f1d176's bursts of 5, 10 and 20 made fewer
  # reads than writes (3/+2, 5/+4, 7/+6) -- and a check red only under load
  # is no gate, so it stays a printed measurement.
  burst_run() {
    local n=$1 i r
    v0=$(pf "['stateVerifies']")
    ipc burst "$KC" "$n" "b$n-" >/dev/null
    for ((i = 0; i < 150; i++)); do r=$(ipc burstResult); [[ $(qa_json_field "d['state']" "$r") != running ]] && break; sleep 0.1; done
    BURST=$r; BURST_READS=$(delta "$v0" "$(pf "['stateVerifies']")")
    echo "   burst of $n: $(qa_json_field "d['state']" "$r"), last asked at $(qa_json_field "d['lastAskMs']" "$r") ms, landed at $(qa_json_field "d['landedMs']" "$r") ms, $(qa_json_field "d['writes']" "$r") writes, reads $BURST_READS, disk $(r26_info "$STATE")"
  }
  for n in 2 5 10 20; do burst_run "$n"; done
  stop_shell

  # B35, B36: R27d (D-SRC-44) -- THE MIGRATION NEVER EVICTS. A 0.13.6
  # install: 50 records, no migration marker, and the bar entry naming D,
  # which is not among them. Before R27 the migration evicted the least
  # recently used record -- the only copy of its URL -- with a journal line;
  # now it does not run: nothing evicted or added, no marker, the user told
  # once. D-SRC-64 (round 7, 2026-10-22, the owner's decision): D's URL is
  # PARKED in state.json (`migrationPending`) and the entry is stripped in
  # the hold's own write, once the save carrying the pair has landed; until
  # D-SRC-64 the entry kept D's URL for the hold's life, every owned write
  # re-carried it, and B35 wanted `entry:yes` -- red on 7c1d37f (the 0.15.0
  # pre-cut live run, 136 / 2, 2026-10-22) once the hold parked instead.
  # `parked:yes` is the proof the URL moved rather than vanished (the R21
  # oracle). Then one record removed in Sources: the next reconcile reads
  # the parked pair (the entry carries nothing) and migrates D into the
  # place it left, dropping the pair in the write that sets the marker.
  seed50() {
    seed "$KA"
    python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
base = d["sources"][0]
for i in range(48):
    r = dict(base); r["key"] = "%08x" % (0x10000000 + i); r["url"] = "/srv/none/m%d.m3u" % i; r["label"] = "m%d" % i; r["lastUsed"] = 1799990000 - 1000 - i
    d["sources"].append(r)
json.dump(d, open(sys.argv[1], "w"))' "$STATE"
    chmod 0600 "$STATE"
  }
  : >"$NOTIFY_LOG"
  seed50
  keys50=$(sj "','.join(sorted(s['key'] for s in d['sources']))")
  start_shell --playlist "$D" || true
  sleep 3
  # The strip waits for the save carrying the pair to LAND (R13); bounded,
  # and the check reads whatever is there when it gives up.
  wait_for no 10 stored_has playlistUrl >/dev/null 2>&1
  ck "B35 R27d (D-SRC-44), D-SRC-64: at 50 sources with the entry's URL not among them the migration does NOT run -- the 50 kept (none evicted, none added), no marker, the entry STRIPPED and its URL parked in state.json (migrationPending holds D's URL exactly), told ONCE (\"Sources is full\", no URL), reported as playlistUrl:full" \
     "records:$(sj "len(d['sources'])") same:$([[ $(sj "','.join(sorted(s['key'] for s in d['sources']))") == "$keys50" ]] && echo yes || echo no) d:$(sj "'$KD' in [s['key'] for s in d['sources']]") marker:$(sj "d.get('entryMigrated', False)") entry:$(stored_has playlistUrl) parked:$(parked_is playlistUrl "$D") told:$(qa_count ' 74016 Sources is full ' "$NOTIFY_LOG") url-in-notice:$(qa_count '://|/srv/|fixtures' "$NOTIFY_LOG") reports:$(reports)" \
     "records:50 same:yes d:false marker:false entry:no parked:yes told:1 url-in-notice:0 reports:playlistUrl:full"
  res=$(ipc removeSource 10000007)
  wait_for "$KD" 15 svc "['activeSourceKey']" >/dev/null || true
  wait_for true 10 landed >/dev/null 2>&1; wait_for no 10 stored_has playlistUrl >/dev/null 2>&1; sleep 0.5
  ck "B36 R27d: ONE record removed in Sources, and the next reconcile migrates the parked URL into the place it left -- 50 records, D active, the marker landed, the entry stripped, the pair gone from state.json (dropped in the marker's write); told once in all" \
     "remove:$(okf "$res") records:$(sj "len(d['sources'])") d:$(sj "'$KD' in [s['key'] for s in d['sources']]") active:$([[ $(svc "['activeSourceKey']") == "$KD" ]] && echo D || echo other) marker:$(sj "d.get('entryMigrated', False)") entry:$(stored_has playlistUrl) parked:$(parked_is playlistUrl "$D") told:$(qa_count ' 74016 Sources is full ' "$NOTIFY_LOG")" \
     "remove:true records:50 d:true active:D marker:true entry:no parked:NOFIELD told:1"
  stop_shell

  # B38, B39: R28b (2026-10-20) -- A HELD MIGRATION HOLDS BOTH URLS. The same
  # 0.13.6 install, the bar entry naming D AND a guide URL, and A carrying a
  # guide URL of its own. The user picks A, the shell restarts over the entry
  # the plugin left (D and the guide URL still on it, the key mirrored): on
  # lane-sweep-c1 the held migration ran R4 on the step-2 key and A's own
  # guide URL -- its only copy -- read the bar's after the restart, and the
  # guide URL was reported "removed" while it stayed on the entry. Then one
  # record removed: D moves in WITH the bar's guide URL (on c1 it got none,
  # and the strip took it off the entry). On 6f1d176 the migration evicted
  # and ran at the first start, so the entry no longer carries either.
  # D-SRC-64 (round 7, 2026-10-22): the pair is parked in state.json as ONE
  # pair and both URLs leave the entry in the hold's own write, at the first
  # start and again after the restart (the entry start_shell writes carries
  # both again; the hold re-parks the same pair, no new write, and the keep
  # rule over the landed pair strips it). B38 wanted `entry:yes/yes` until
  # then -- red on 7c1d37f (136 / 2, 2026-10-22); `parked:yes/yes` is what
  # says both moved rather than vanished, and B39's `parked:NOFIELD/NOFIELD`
  # that the pair went in the write that set the marker.
  AOWN=/srv/none/a-own.xml
  : >"$NOTIFY_LOG"
  seed50
  python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
for r in d["sources"]:
    if r["key"] == sys.argv[2]: r["epgUrl"] = sys.argv[3]
json.dump(d, open(sys.argv[1], "w"))' "$STATE" "$KA" "$AOWN"
  chmod 0600 "$STATE"
  epg_of() { local e; e=$(sj "([s.get('epgUrl', '') for s in d['sources'] if s['key'] == '$1'] or ['<none>'])[0]"); [[ $e == "$AOWN" ]] && echo own || { [[ $e == "$EPG" ]] && echo bar || { [[ -z $e ]] && echo empty || echo other; }; }; }
  start_shell --playlist "$D" --epg "$EPG" || true
  sleep 3
  ipc switchSource "$KA" >/dev/null
  wait_for "$KA" 15 svc "['activeSourceKey']" >/dev/null || true
  for ((i = 0; i < 100; i++)); do [[ $(sj "d.get('activeKey', '')") == "$KA" && $(pf "['stateSavesInFlight']") == 0 ]] && break; sleep 0.1; done
  sleep 1
  stop_shell
  start_shell --playlist "$D" --epg "$EPG" --source-key "$KA" || true
  sleep 3
  wait_for no 10 stored_has epgUrl >/dev/null 2>&1
  ck "B38 R28b, D-SRC-64: at 50 sources the bar's playlist AND guide URL are held TOGETHER -- parked as one pair in state.json and both stripped from the entry, a source the user picked keeps its OWN guide URL across a restart, and the one card each start is \"Sources is full\" (never \"Bar setting removed\")" \
     "a-epg:$(epg_of "$KA") active:$([[ $(svc "['activeSourceKey']") == "$KA" ]] && echo A || echo other) entry:$(stored_has playlistUrl)/$(stored_has epgUrl) parked:$(parked_is playlistUrl "$D")/$(parked_is epgUrl "$EPG") removed-card:$(qa_count ' 74016 Bar setting removed ' "$NOTIFY_LOG") full-card:$(qa_count ' 74016 Sources is full ' "$NOTIFY_LOG") reports:$(reports)" \
     "a-epg:own active:A entry:no/no parked:yes/yes removed-card:0 full-card:2 reports:playlistUrl:full"
  res=$(ipc removeSource 10000007)
  wait_for "$KD" 15 svc "['activeSourceKey']" >/dev/null || true
  wait_for true 10 landed >/dev/null 2>&1; wait_for no 10 stored_has epgUrl >/dev/null 2>&1; sleep 0.5
  ck "B39 R28b: then ONE record removed, and D moves in WITH the bar's guide URL -- D active, its guide URL the bar's, the entry stripped of both, the pair gone from state.json, A's own guide URL kept, 50 records" \
     "remove:$(okf "$res") d-epg:$(epg_of "$KD") active:$([[ $(svc "['activeSourceKey']") == "$KD" ]] && echo D || echo other) entry:$(stored_has playlistUrl)/$(stored_has epgUrl) parked:$(parked_is playlistUrl "$D")/$(parked_is epgUrl "$EPG") a-epg:$(epg_of "$KA") records:$(sj "len(d['sources'])")" \
     "remove:true d-epg:bar active:D entry:no/no parked:NOFIELD/NOFIELD a-epg:own records:50"
  stop_shell

  # B40: R29d (2026-10-20) -- R28b's sibling. A 0.13.6 install whose state
  # names A active (no marker), A carrying a guide URL of its own, and the
  # bar entry holding a playlistUrl that is NOT A USABLE URL with a guide URL
  # beside it. On lane-sweep-c2, 6f1d176 and 0.14.2 the migration refused
  # the playlist, resolved A from the state's key and ran R4 there: A's own
  # guide URL -- its only copy -- became the bar's, and the only card was the
  # playlist's. Now the guide URL goes WITH the playlist: one card naming the
  # pair (no URL), A keeps its own, and both leave the entry once the
  # marker's write has landed.
  : >"$NOTIFY_LOG"
  seed "$KA"
  python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
for r in d["sources"]:
    if r["key"] == sys.argv[2]: r["epgUrl"] = sys.argv[3]
json.dump(d, open(sys.argv[1], "w"))' "$STATE" "$KA" "$AOWN"
  chmod 0600 "$STATE"
  start_shell --playlist "$BAD" --epg "$EPG" --source-key "$KA" || true
  wait_for true 15 landed >/dev/null 2>&1; wait_for no 10 stored_has epgUrl >/dev/null 2>&1; sleep 0.5
  ck "B40 R29d: an UNUSABLE bar playlist with a guide URL beside it, A active with its OWN guide URL -- A keeps its own (the guide URL is never adopted onto it), ONE card names the pair with no URL, the guide URL is nowhere in the file, and both leave the entry once the marker has landed" \
     "a-epg:$(epg_of "$KA") active:$([[ $(svc "['activeSourceKey']") == "$KA" ]] && echo A || echo other) entry:$(stored_has playlistUrl)/$(stored_has epgUrl) marker:$(landed) cards:$(qa_count ' 74016 ' "$NOTIFY_LOG") pair:$(qa_count ' 74016 Bar setting removed playlistUrl in the bar settings was not a usable URL and was removed, with the epgUrl beside it' "$NOTIFY_LOG") url-in-notice:$(qa_count '://' "$NOTIFY_LOG") file:$(python3 -c 'import sys; print("yes" if sys.argv[2] in open(sys.argv[1]).read() else "no")' "$STATE" "$EPG" 2>/dev/null || echo NOFILE) reports:$(reports)" \
     "a-epg:own active:A entry:no/no marker:true cards:1 pair:1 url-in-notice:0 file:no reports:playlistUrl:invalid-pair"
  stop_shell

  # B37: R27c (D-SRC-41) -- the probe commit re-checks the cap. 49 records,
  # an in-app add of a source behind a server that answers after 4 s, and a
  # hand-run `state source add` taking the 50th place 1 s into the probe.
  # Before R27 the commit appended a 51st, which the next start's parse
  # dropped in silence; now it is refused too_many, told through the probe's
  # own result, and a restart reads the same 50.
  python3 - "$WORK/slow2.port" "$C" >"$WORK/slow2.log" 2>&1 <<'SLOW' &
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
  SLOW_PORT=""; for ((i = 0; i < 50; i++)); do [[ -s $WORK/slow2.port ]] && { SLOW_PORT=$(cat "$WORK/slow2.port"); break; }; sleep 0.1; done
  SLOW_PID=""; for ((i = 0; i < 50; i++)); do SLOW_PID=$(ss -ltnp 2>/dev/null | grep ":$SLOW_PORT " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [[ -n $SLOW_PID ]] && break; sleep 0.1; done
  SLOW2="http://127.0.0.1:$SLOW_PORT/slow2.m3u"; KS2=$(key_of "$SLOW2")
  echo "   slow listener on port ${SLOW_PORT:-none}, pid ${SLOW_PID:-none}"
  seed50
  python3 -c 'import json, sys
d = json.load(open(sys.argv[1])); d["sources"] = d["sources"][:49]; d["entryMigrated"] = True
json.dump(d, open(sys.argv[1], "w"))' "$STATE"; chmod 0600 "$STATE"
  start_shell --playlist none --source-key "$KA" || true
  wait_for true 20 pf "['dirsReady']" >/dev/null || true; sleep 0.5
  res=$(ipc addSource "$SLOW2" "" "")
  sleep 1.0
  python3 "$PLUGIN_ROOT/bin/omarchy-iptv" state --state-dir "$SDIR" source add --url "$D" >/dev/null 2>&1; hrc=$?
  wait_for 50 10 pf "['sourceCount']" >/dev/null || true
  for ((i = 0; i < 100; i++)); do [[ $(qa_json_field "len([s for s in d if s.get('signal') == 'sourceProbeFinished'])" "$(ipc signals)") -ge 1 ]] && break; sleep 0.1; done
  sleep 1.0
  probe=$(qa_json_field "json.dumps([s for s in d if s.get('signal') == 'sourceProbeFinished'][-1]['payload'])" "$(ipc signals)")
  stop_shell
  start_shell --playlist none --source-key "$KA" || true
  sleep 0.5
  ck "B37 R27c (D-SRC-41): at 49 sources an in-app add's probe runs while a hand-run \`state source add\` takes the 50th place: the commit refuses too_many (told through the probe's result) -- 50 on disk, the hand-run one among them, and a restart drops nothing (before R27: 51 committed, the next start's parse dropping the in-app one)" \
     "add:$(okf "$res") helper:$hrc probe:$(qa_json_field "'ok' if d.get('ok') else d.get('reason', '?')" "$probe") on-disk:$(sj "len(d['sources'])") d:$(sj "'$KD' in [s['key'] for s in d['sources']]") slow:$(sj "'$KS2' in [s['key'] for s in d['sources']]") restart:$(qa_json_field 'len(d)' "$(ipc sources)")" \
     "add:true helper:0 probe:$(node -e 'const M = require(process.argv[1]); process.stdout.write(M.sourceErrorMessage("too_many"))' "$(qa_model_files "$PLUGIN_ROOT" | head -n 1)") on-disk:50 d:true slow:false restart:50"
  stop_shell
  kill_pid "$SLOW_PID"; SLOW_PID=""
  fi   # --only: end of B20 .. B40

  echo "== P: the console sink, then teardown ($(elapsed) s)"
  qa_leak_on_labelled 'sourceProbeFinished|sourceSwitched|sourceRemoved|updateEntryInline' "://|$WORK" "$LOG"
  case $? in 0) left=clean ;; 1) left=LEAK ;; *) left="nothing labelled to judge" ;; esac
  # A PARTIAL run may label nothing at all (B19 alone adds no source and
  # writes no entry), and says so rather than reading red for it; a full run
  # labels dozens of lines and wants them clean, as before.
  p1_want=clean
  [[ -n $ONLY && $left == "nothing labelled to judge" ]] && p1_want=$left
  ck "P1 no labelled harness-log line carries a URL or a fixture path" "$left" "$p1_want"
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
# Round 12 (B8): a provider that is down -- nothing listens on port 9.
DEAD="http://127.0.0.1:9/dead-provider.m3u"

instrument
[[ $MODE == live ]] && shell_arm

# The floor. A check that stops executing must turn the run red rather than
# quietly shorten the summary (D-PLY-9). Recount with
#   grep -cE '^ *ck "[IS][0-9]' key-scenario.sh   -> 11, the instrument arm -> check-tree
#   grep -cE '^ *ck "[A-Z][0-9]' key-scenario.sh  -> 137, both arms         -> live
# (48 -> 61 on 2026-10-12, round 4: W1..W6 and F1..F7; 61 -> 63 the same
# day, round 5: L1, L2; 63 -> 70 the same day, round 7: U1..U7; 70 -> 78
# the same day, round 8: K1..K3, Z1..Z3, A1, A2; 78 -> 85 the same day,
# round 9: Y1..Y3, Q1, Q2, V1, H1; 85 -> 86 on 2026-10-12, round 10: Y4;
# 86 -> 97 on 2026-10-13, round 11: G1..G5 and X1..X6, the migration and
# the refusal, R21. U, K, Z, A, Y2, Y3, Q, V, F and H were re-pointed at
# the R21 contract, one for one; 97 -> 105 the same day, round 12: B1..B8,
# R22a's load failures and R22c's hint; 105 -> 111 the same day, round 13:
# B9..B14, R23a-c, R23e, R23f, R23h; 111 -> 115 on 2026-10-14, round 14:
# B15..B18, R24f, R24c, R24g, R24d; 115 -> 119 the same day, round 15:
# B19..B22, R25d, R25a, D-SRC-38; 119 -> 128 on 2026-10-16, R26: B23..B31,
# the read before every write, the in-load save deferred, and idle; 128 ->
# 133 on 2026-10-20, R27: B32 (the mid-session notice's title, R27e), B33
# (no write without a read, R27a), B35 and B36 (the migration at the cap,
# R27d) and B37 (the probe commit at the cap, R27c); B34 is unused, the
# burst measurement it was is printed, not graded; 135 on 2026-10-20, R28b:
# B38 and B39 (the held migration holds the bar's guide URL with its
# playlist); 137 the same day, R29: B40 (R29d, a guide URL beside an
# unusable playlist is never adopted onto the active source) and S4 (R29e,
# init_pids scoped to this run), which also takes check-tree 10 -> 11.)
# Every assertion is one `ck "<letter><n> ...` line, none in a loop; the
# probe's fallback `fail` lines replace the seven I lines one for one when
# the probe does not run, so the count holds either way; the definition of
# ck() does not match the recipe. Never lower a floor to make a run green.
# scripts/check.sh's KEY_PREFLIGHT_MIN is the check-tree number plus one
# (this line), and scripts/qa-lib-test.sh asserts every join.
if [[ $MODE == check-tree ]]; then
  EXPECTED_CHECKS=11
else
  EXPECTED_CHECKS=137
fi
# F-HARNESS-49: a PARTIAL run's floor is the instrument arm, the selected
# blocks and P1, P2, T1 -- its own, never the full one, and never lowered
# to make a run green either.
if [[ -n $ONLY ]]; then
  only_floor=$((11 + 3))
  IFS=, read -r -a only_names <<<"$ONLY"
  for seg in "${only_names[@]}"; do only_floor=$((only_floor + ONLY_CHECKS[$seg])); done
  EXPECTED_CHECKS=$only_floor
fi
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  if [[ -n $ONLY ]]; then pass "the scenario ran every check the selected segments have ($ran)"
  else pass "the scenario ran every check it has ($ran)"; fi
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi

if [[ -n $BASELINE || -n $TREE ]]; then
  # F-HARNESS-28 (round 15): this footer is what a transcript reader sees
  # under every --baseline / --tree run, and round 14 added B15..B18 without
  # a sentence here, so a run whose reds were B15, B16 and B18 printed "the
  # reds are round 13's -- B10 ... B14". Each round's sentence now leads, and
  # every older one names the tree it was measured on and says it was.
  echo "baseline ${BASELINE:-$TREE}: R29 (measured 2026-10-20 by lane-sweep-a3 under this harness, 137 lettered checks): on lane-sweep-c2 2bb1237 134 passed, 4 failed -- K1..K3 (\`reports:epgUrl:no-source,playlistUrl:invalid\`, two notices where R29d tells the pair once) and B40 (\`a-epg:bar ... pair:0 file:yes\`: the active source's own guide URL replaced by the one beside the unusable playlist); on 6f1d176 127 passed, 11 failed -- those four, B32, B33 (\`waited:NOFIELD\`), B35..B39. S4 reads the harness, not the product, so it is green on every baseline; it was seen red on the unscoped init_pids in check-tree. Before that, R28 (measured 2026-10-20 by lane-sweep-a2 under this harness, 135 lettered checks): on lane-sweep-c1 843ae87 133 passed, 3 failed -- B32 (R28e's sentence: \`body:0\`), B38 (\`a-epg:bar\`: the picked source's own guide URL replaced by the bar's across the restart) and B39 (\`d-epg:empty ... a-epg:bar\`: D moved in with no guide URL); on 6f1d176 129 passed, 7 failed -- B32, B33 (\`waited:NOFIELD\` at load 2-3), B35, B36, B37, and B38 / B39 (the migration evicted and ran at the first start: \`entry:no/no ... reports:playlistUrl:retired,epgUrl:retired\`, \`records:49\`). Before that, on 6f1d176 (0.14.2's code, the helper split on top; measured 2026-10-20 by lane-sweep-a1 under this harness: 129 passed, 5 failed of the 134 lettered checks then, B34 since dropped) the reds are R27's -- B32 (the mid-session block's notification titled \`Saved sources not loaded\`: \`saving-stopped:0 not-loaded:1 body:0\`), B33 (at idle \`waited:NOFIELD->NOFIELD\` only, the first write having landed by the deferred turn; under load -- round 1's review at load 5-8, \`key-20261020-135918-1751390\` -- red on behaviour too, \`skipped:+1\`, a write without its read: window (a) DOES open from outside the shell under load, and the node pins time it either way; seen red on behaviour through spikes/key-mutations/r27a-wait-never-released.patch, --tree: 133 passed, 1 failed, B33 \`disk:...C=w-one\`, the held edit never written), B35 (the migration at 50 sources evicted the least recently used record and marked: \`same:no d:true marker:true entry:no told:0\`), B36 (\`records:49 told:0\`) and B37 (\`probe:ok\`, the 51st committed). The counts that follow were measured before B32..B37 existed (128 lettered checks). On dev 1c88877 (round 15's code and 0.14.1, measured 2026-10-16 by lane-clean-a1 under this harness: 120 passed, 9 failed) the reds are R26's -- B23..B27 (a linked state.json replaced by a rename, sed -i or rm-and-copy, or re-pointed, or the state folder link re-pointed: unseen, and the in-app save writes memory over it, \`disk:A=seed\` beside the hand edit lost), B28 (the folder link re-pointed at an EMPTY folder: \`created:644 holds:[state.json] blocked: told:0\`, D-SINK-21), B29 (a target put back stays blocked for every call: \`lifted:[absent] second:false\`), B30 (the merge's save inside the load is never reported: \`inFlight:1 saveFailed:true\`, D-SRC-46) and B31 (\`idle-reads:NOFIELD\`: no read before a save). Through --tree: r26a-no-read.patch 122 / 7 (B23..B28, B31), r26b-no-defer.patch 128 / 1 (B30), r26a-no-verb-recheck.patch 128 / 1 (B29), r26d-periodic-reload.patch 126 / 3 (B31 \`idle-loads:+15\`, and B28 and B29, which the timer answers before the first call does); d3-save-parked.patch now reads 76 / 53, D3 and W3 among them, because every in-app save waits behind a read that only save-parked keeps from being applied. The counts that follow were measured before B23..B31 existed (119 lettered checks). On dev 002662d (round 14's code, measured 2026-10-14 by lane-key-k1 under this harness: 118 passed, 2 failed) the reds are round 15's -- B20 (a backup copied from the plugin's own file, put back after an in-app remove, is ignored as an echo and written over: \`restored:1 records:1 ... restart:1\`) and B22 (the MID-session Sources header reads \`Saved sources not loaded\` above the session's two rows). B19 and B21 are GREEN there: R24a's merge and the FileView's watch after an own save were in round 14's code and only their checks were missing, so they are seen red through spikes/key-mutations/r25d-a5-base-not-moved.patch (--tree: 119 passed, 1 failed, B19 \`merged:2 ... favs:t:helper.uk,t:h3.uk\`: the favourite the second hand edit removed is written back) and r25d-no-reload-on-change.patch (--tree: 110 passed, 10 failed, B21 \`blocked: told:0\` among every segment that needs a reload: D3, W3, W6, B7, B9, B16, B19, B20, B22). The counts that follow were measured before B19..B22 existed (115 lettered checks). On ced1bd1 (round 13's code, measured 2026-10-14 by lane-key-q1 under this harness: 113 passed, 3 failed) the reds were round 14's -- B15 (\`header:[No sources] rows:2 after-a:sourceEdit says:other\`), B16 (\`seen:0 file:D blocked: told:0\`) and B18 (the held init \`after-deadline:alive(<pid>)\`); B17 is GREEN there, round 13 having the KILL, and is seen red through r24g-no-kill.patch (--tree: 115 passed, 1 failed, B17 \`blocked: helper:no(<pid>) left:<pid> told:0\`). The counts that follow were measured before B15..B18 existed (111 lettered checks). On lane-key-n2 (round 12's code, measured 2026-10-13 by lane-key-p1 under this harness: 107 passed, 5 failed) the reds were round 13's -- B10 (no watchdog: the init held by the slow tree is still running and the start never decides, \`blocked: found: helper:no(<pid>) left:<pid> told:0\`), B11 (the no-write start draws the first-run form: \`kind:unconfigured form:true shown:NOFIELD title:other prose:other\`), B12 (the logo refusal says \`try omarchy bar set\`: \`says:other advice:bar-set\`), B13 (the drawn-copy field reads the hidden empty state's \`Add your M3U URL or path in Sources...\` over the form that draws \`Paste or type...\`) and B14 (the FIFO hangs the init: \`blocked: found: told:0 left:<pid>\`). B9 is GREEN there: the re-arm it guards was in round 12's code and only its check was missing, so it is seen red through spikes/key-mutations/r23a-no-rearm.patch instead (--tree: 111 passed, 1 failed, B9 \`told:1/1\`); r23e-editable-field.patch reads 111 / 1 the same way (B13, \`editable:2\`). The counts that follow were measured before B9..B14 existed (105 lettered checks). On lane-key-m2 (round 11's code, measured 2026-10-13 by lane-key-n1 under this harness: 97 passed, 9 failed) the reds are round 12's -- B1..B4 (a migrated install whose state.json, or whose state directory, could not be read at the start: the failed load is applied as an EMPTY state and written over the file, \`records:0\` at B1 and at the second start, B2, and through the directory, B3/B4), B5, B6 (a file that does not parse is replaced at the start, \`file:changed\`; an add goes through, \`add:ok\`; the mirror moves, \`writes:2\`), B7 (nothing left to restore: \`records:0\`) and B8 (the hint reads \`check playlistUrl\`: \`retired:yes\`). N1 is red there ONLY for the field it reads (\`found:NOFIELD\`): its adoption is the same. Every other check is green on round 11's code. The counts that follow were measured before B existed (97 lettered checks). On lane-key-z2 (round 10's code, measured 2026-10-13 by lane-key-m1 under the 97-check harness: 68 passed, 30 failed) the reds were G1, G2, G5, F4, U1..U7, K1..K3, Z1..Z3, A1, Y2, Y3, Q1, Q2, V1, H1 and X1..X6, and EIGHT of them -- F4, U2, K2, K3, Q2, V1, Y2 and Z3 -- differ from their want ONLY in \`reports:NOFIELD\`: they prove the refusal record does not exist there, and nothing about behaviour (classified got against want token by token over the round-11 live lens's transcript, which counted seven and missed U2; this footer used to fold Y2 in with Y3's \`twice:E\`, leave Z3 out, and describe K1..K3 by K1's \`file:yes\` alone). The twenty-two that discriminate: G1, G2, G5 (no migration marker is ever written, so a downgrade's entry and a 0.13.5 entry are read alike), U1, U3..U7 (the guide URL with no source is HELD in state.json, \`file:yes\`, and the switch lands it on A: U3 \`on:<A>\`), K1 (the guide URL held in the file, \`file:yes\`), Z1, Z2 and X1..X4 (a CLI value after the marker is ADOPTED: Z1 and X1 read B active), X5, X6 (no notification: the refusal does not exist), A1, Q1 (the CLI guide URL lands on the new record), Y3 (the CLI guide URL is adopted onto A, \`twice:E\`) and H1 (the marker never lands, \`landed:.../false\`). G3, G4, F1..F3, F5..F7, L1, L2 and A2 are its controls (F and L are R13 and R16 on a migration that fails, which round 10 already held). The counts that follow were measured before G and X existed and before U, K, Z, A, Y2, Y3, Q, V, F and H moved to the R21 contract (86 lettered checks). On lane-key-y0 (round 8's code) the reds are round 9's -- U1, U2, U5, K1, K2, K3 (a guide URL with no source to land on waits on the ENTRY instead of being held in state.json), Y1, Y2, Y3 (after a publish A -> B -> A the lagging host's write is skipped: the in-app logo OFF, the strip of a re-set refused credential and of a re-set EPG input that the restart then puts back over an in-app edit), Q1 (a CLI epgUrl set while the add's probe runs exists nowhere), V1 (an earlier held value replaces a guide URL typed in the edit form) and H1 (D-SRC-18): 74 passed, 12 failed; A1, A2 and Q2 are its controls. The counts that follow were measured before Y, Q, V and H existed (78 lettered checks). On lane-key-w2 (round 7's code) the reds are round 8's -- K1 (the lagging host LOOPS on a refused playlistUrl beside a pending EPG: about 17,000 entry writes and 600 CPU ticks in 5 s), K3 (the echoing host loops on the same value wrapped in whitespace and keeps the credential), Z1, Z2 (a whitespace-wrapped CLI playlist removed comes back at the next start), Z3 (a whitespace-wrapped refused credential stays on the stored entry) and A2 (a pending CLI epgUrl replaces the add form's own guide URL): 73 passed, 6 failed; K2 and A1 are its controls. The counts that follow were measured before K, Z and A existed (70 lettered checks). On lane-key-v2 (round 6's code) the reds are round 7's -- U2, U3, U4 (the logo toggle's heal stripped an EPG no source had adopted, so the switch had nothing to land and the restart stands on A with no EPG) and U6, U7 (the same input lost by the switch alone on the echoing fake host): 66 passed, 5 failed. The counts that follow were measured before U existed (63 lettered checks). On lane-key-t2 (round 4's code) the reds are round 5's -- L1, L2 (the logo toggle on the failed disk mirrored the in-memory key and stripped the URL) and F6, F7 (the restart over that entry finds no record for B): 60 passed, 4 failed. On lane-key-s2 (round 3's code) round 4's join them -- D3, W3, W6 (no per-reason counter there), F3, F4, F5 (the dirsReady-route state write failing strips the URL, moves the mirror and loses the input): 54 passed, 10 failed. On lane-key-r2 (the tree D-SRC-15 was found on) D2, D3, W2, W3, W6, M1, M3, M5, C1..C5, E1, O5, O6 and the F and L reds: the start-up chmod reload replaces the adoption and the in-window switch/remove alike (D2 and W at the sink, D3 NOFIELD for want of a counter) and everything resting on a start-up adoption with it: 38 passed, 26 failed. On f275bde (the first build) O2 is the one discriminating red against every later tree (the entry rewritten while the save is parked); D2, M1, M3, M5 pass there by the accident the header describes: 39 passed, 25 failed. The two patches under spikes/key-mutations/ read 58 / 6 (D2, D3, W2, W3, W4, W6) and 59 / 5 (D2, W2, W3, W4, W6; D3 green) through --tree. N1..N4 are green on EVERY tree: the created-file shape never fires the reload. D1, M2, M4, M6, J1..J3, E2, E3, R1..R5, O1, O3, O4, P1, P2, T1 and every I and S check are controls; W1, W5, F1 and F2 are controls wherever the field they read exists (NOFIELD on f275bde and, for F1/F2, on lane-key-r2)."
fi
echo "key-scenario: $PASS passed, $FAIL failed (mode $MODE${ONLY:+, PARTIAL (only $ONLY)}, tree $PLUGIN_ROOT${BASELINE:+, baseline $BASELINE}${TREE:+, prepared tree}, $(elapsed) s)"
(( FAIL == 0 ))
