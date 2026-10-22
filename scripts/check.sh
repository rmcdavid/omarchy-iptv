#!/bin/bash
# scripts/check.sh -- the whole quality gate for omarchy-iptv, in one command.
#   1. omarchy plugin validate   (manifest schema, entry points, no symlinks)
#   2. qmllint on every .qml     (qs.Commons / qs.Ui mapped through $QMLROOT),
#                                INCLUDING the dev-harness fake (CLAUDE.md 10);
#                                every `Model.X` it reports must be a name
#                                Model.mjs exports (check-model-members.py)
#   3. node tests                (tests/Model.test.js)
#   4. python tests              (python3 -m unittest discover -s tests)
#   4b. model split              (scripts/split-model.mjs --check: Model.mjs and
#                                the parts under model/ are what the script
#                                writes, and no initializer reads another part)
#   5. QML spec                  (qmltestrunner on tests/Model.spec.qml)
#   6. harness predicates        (scripts/qa-lib-test.sh)
#   6b. chno-entry preflight     (scripts/dev-harness/chno-entry-scenario.sh check-tree)
#   7. ASCII check on code files (glyphs are allowed in .qml only) and the
#                                control-byte check. BOTH scan the working
#                                TREE, not the index: `git ls-files --cached
#                                --others --exclude-standard`, so a file that
#                                exists but has not been staged is covered
#                                (F-GATE-1), and the printed count says how
#                                many of the files it read were untracked
#   8. defect ledger             (scripts/check-defect-ledger.py: every defect
#                                id filed in any tracked .md has a row, with a
#                                severity and a state, in STATUS.md "## Defects")
#   8b. board staleness          (scripts/check-board-staleness.py: no row
#                                reads a bare `open` while a commit message of
#                                ours says that id was closed -- the agreement
#                                the ledger step does not check)
#   9. marketplace capabilities  (scripts/check-marketplace-capabilities.py: no
#                                tracked file the marketplace scan reads holds a
#                                string it would report as a capability)
#  10. release allowlist         (scripts/release.py check: what main ships is
#                                exactly what the runtime, the manifest and the
#                                README need, and no agent-instruction file)
#  11. text format guard         (scripts/check-text-format.py: every Text in
#                                every shipped .qml declares Text.PlainText,
#                                or Text.StyledText under a MARKUP-EXCEPTION
#                                comment -- a missing line is AutoText, which
#                                fetches an <img> out of a channel name)
# Exit status is non-zero if any gate fails. qmllint *warnings* are reported
# but do not fail the gate (the first-party widgets trigger the same
# unqualified-access / missing-property warnings); qmllint *errors* do.
#
# The known qmllint warning baseline (CLAUDE.md, "Verify before you claim"):
# missing-property and unqualified access on host-injected objects and on
# Style / Color children, uncreatable-type for PanelWindow, and
# signal-handler-parameters on Process.onExited. Plus, since the harness
# floating-window round, two more [unqualified] in Guide.qml on the two
# `visible: root.opened` bindings, one inside each inline Component
# (layerHost, floatingHost) the window Loader chooses between: qmllint cannot
# see the file's ids from inside a nested Component, while at runtime they
# resolve (measured under headless cage and on the shell). The remedy it
# proposes, `pragma ComponentBehavior: Bound`, would change how every delegate
# in the file reaches its model roles, so it is declined. Guide.qml went
# 222 -> 224 warnings, same three categories; anything outside this baseline
# is a real finding.
#
# EVERY COUNT THIS FILE PRINTS IS ALSO ASSERTED. A runner that exits 0 having
# executed nothing is the failure this whole cleanup round is about: the gate
# used to print `ok   qml spec (0 passed)` and stay green, and an emptied
# tests/ directory made `Ran 0 tests ... OK`. Raise a floor when you add
# tests; never lower one to make a run green.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
# E4: QMLROOT was a fixed /tmp/qmlroot and the mkdir and both ln statuses were
# discarded. If that directory exists owned by someone else the symlink
# refresh fails silently and qmllint resolves qs.Commons / qs.Ui against
# whatever is planted there - the import root of the entire lint gate.
CHECK_TMP=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-check-XXXXXX")
trap 'rm -rf "$CHECK_TMP"' EXIT
QMLROOT=${QMLROOT:-$CHECK_TMP/qmlroot}
QT_BIN=${QT_BIN:-/usr/lib/qt6/bin}
QML_IMPORTS=${QML_IMPORTS:-/usr/lib/qt6/qml}
SHELL_DIR=${OMARCHY_PATH:-/usr/share/omarchy}/shell
fail=0

# Recorded expected counts. These are floors, not decoration: each runner
# below is capable of exiting 0 having run nothing at all.
#
# All three of the suite floors had fallen behind what the suites actually run
# -- python 260, node 954, the qml spec 47, against the numbers below -- so
# between a fifth and a half of each suite could have stopped executing with
# the gate still green. Raised to what M2-03 leaves behind. Raise a floor when
# you add tests; never lower one to make a run green.
#
# M2-05 integration raises all three to exactly what the suites now run, so a
# suite that stops executing even one case is red here rather than quietly
# smaller. Adding a test means bumping the number in the same commit; that is
# the intended cost.
#
# M2-09 raises the two suites this lane adds to, and closes the drift that had
# crept into all three: node was floored at 1249 against 1258 actually run, and
# python at 357 against 361, so either suite could have lost nine cases and
# stayed green. Floors are again exactly what the suites run. This lane adds no
# python test; its 361 is the existing suite, floored honestly.
#
# GS8 adds the contrast rung: one qml spec case, five node checks (the rung,
# the ratios on the theme the live pass measured, the same ratios across every
# installed theme, the notice against the channel name beside it, and the two
# QML slots that have to ask for it). GS9 adds one more qml spec case and six
# node checks for the coverage the second line is decided by. GS11 adds six
# python tests for `cache epg-clear` and three node checks for the two callers
# that have to name it.
# The defect-ledger round adds fifteen python cases
# (tests/test_defect_ledger.py), one per branch of the new ledger check, each
# building a real git repository and mutating it. Two of them turned red
# against the checker as first written and found two real defects in it: an
# empty state cell was misdiagnosed as a short row, and a missing STATUS.md
# printed a stack trace instead of a sentence.
# D-ID-1 raises all three, and states the margin, because the margin is what
# went wrong. These floors were left at the counts of the milestone BEFORE the
# channel-id work: python 384 against 407 run, node 1345 against 1399, the qml
# spec 66 against 66. So the whole D-ID-1 suite could be deleted -- every case
# that proves a favorite survives a password rotation -- and this gate stayed
# green, because what remained still cleared a number written before any of it
# existed. A floor that trails the suite protects the settled tests and leaves
# the newest, least-settled ones unprotected, which is exactly backwards.
#
# MARGIN LEFT BELOW THE CURRENT COUNT: ZERO, on all three. Deliberate.
#   qml spec   66 -> 68    (floor 68)
#   node    1,399 -> 1,422 (floor 1422)
#   python    407 -> 423   (floor 423)
# A floor set n below the count is a licence to delete n cases in silence, and
# there is no n this project can afford: the last three times a suite went
# quiet here, nobody noticed for a milestone. Adding a test means bumping the
# number in the same commit; that is the intended cost and it is cheap. Never
# lower one to make a run green.
#
# The marketplace-capability round adds 46 python cases
# (tests/test_marketplace_capabilities.py), so the floor moves 423 -> 469,
# again with zero margin. Fifteen mutations were run against the checker and
# its transcribed patterns and every one of them turned this suite red; two
# went green on the first sweep and both were real gaps, since closed.
#
# A count is not the only guard on the D-ID-1 work, because a count cannot see
# a suite that shrinks and grows at once. tests/fixtures/channel-ids.json is
# run by node and by python, and BOTH assert its row counts before using it
# (`channel-ids fixture loaded`, `test_fixture_is_not_empty`), so deleting a
# vector is red on an assertion rather than on arithmetic here.
#
# Re-levelled 2026-09-25 on a clean 44b27df. The floors had drifted: node was
# 1427 against 1579 actual and python 531 against 635, so 152 node checks and
# 104 python tests could have been deleted in silence -- in a file whose own
# rule two paragraphs up is that the margin is deliberately zero. a11y was 32
# against 34. The drift is what happens when a floor is raised only when
# somebody remembers; the numbers below are the measured counts at that
# commit, with zero margin again, which is the whole point of them.
#
# Re-levelled again 2026-09-26 for 0.9.0, and THE DRIFT HAD ALREADY REOPENED
# at the cut one day later: 0.8.0 shipped from 65978e4 running 1620 node and
# 637 python against these same 1579/635, so 41 node checks and 2 python
# tests were deletable in silence at that cut. This release reopened it to
# 63 and 12 -- the whole of M3 -- before anyone looked.
#
# A draft of this comment claimed the re-level "belongs in the version-bump
# commit, and that is now where it is". NOTHING ENFORCES THAT and it was not
# even true of the commit it appeared in. It is deleted rather than left to
# be read as a rule: this has now drifted four times, and a fifth will not be
# prevented by a sentence. The honest statement is the one above -- the
# numbers below are the measured counts on this tree, with zero margin, and
# they are correct only until the next test is written.
QML_SPEC_MIN=${QML_SPEC_MIN:-78}
# 2074 -> 2075 on 2026-10-12: ab545f4's frozen-CHNO_NONE check arrived from
# dev without its floor.
# 2075 -> 2319 on 2026-10-12, D-SINK-19 round 10 (R20f): the chain's own
# checks had never been levelled -- 193 under the tree at round 9, more than
# every R19 pin together -- plus round 10's R20a key check and shared-fixture
# cases, and the R20b/c/d cases that run Service.qml's own functions
# (tests/service-harness.js).
# 2319 -> 2261 on 2026-10-13, D-SINK-19 round 11 (R21d / R21e), and it is a
# DELETION the ruling ordered, not a floor lowered to fit: the service-order
# driver that mirrored Service.qml and every check of the withdrawn R12, R17b,
# R18c/d, R19b/c and R20b/c machinery went (180 check names gone or renamed),
# and R21's model pins and the shipping-function harness cases came in (121,
# the data-loss matrix at length 2 among them; IPTV_MATRIX_LEN deepens it
# off the gate).
# 2261 -> 2348 on 2026-10-13, D-SINK-19 round 12 (R22): the load-failure pins
# through Service.qml's own handlers and the REAL startCacheLayout (80: every
# fault at a migrated and an unmigrated start, mid-session, both hosts), the
# R22a model functions (6), and R22e's absence pin (1); 2348 -> 2354 the same
# day, the six pins three surviving mutations asked for (every owned-entry
# writer in the no-write mode, the unmigrated session, a probe that ends in
# it; both hosts).
# 2354 -> 2372 on 2026-10-13, round 13 (R23): R23a's four (two no-write
# episodes in a session, with and without an own save between, both hosts),
# R23c's eight harness pins (the watchdog armed; a timed-out init over a
# file that is not one and one that does not parse; a timeout after the
# load) and two model pins, R23e's three and R23f's one. The node suite now
# also runs a second time with IPTV_HARNESS_OWN_ECHO=none (R23g), same count.
# 2372 -> 2459 on 2026-10-14, round 14 (R24): the merge fixture table (34
# cases of tests/fixtures/state-merge.json, its coverage check, the two
# identities over every case, sameState and the conflict line: 38), the
# reload fixture's six R24a cases (counted inside R9's one check, so 0 more),
# R24b's three model pins, R24f's four; and through the service harness, on
# both hosts, R24a's five per own-echo mode (failed, in flight, parked, the
# base reload, a conflict) and R24c's two per mode (20 + 8), R24c's double
# (2), R24d's mkdir hang (2), R24g's TERM-ignoring init and mkdir (4), R24e
# (2) and R24b's two faults (4).
# 2459 -> 2502 on 2026-10-14, round 15 (R25): through the service harness,
# on both hosts and both own-echo modes, R25a's four (FAV BAK DEL RSTB FAV,
# the UNFAV variant, the controls, the coalesced burst's mid-burst echo),
# R25d's two (the lens's a5 and a7), R25c's folder-link start and R25b's two
# caps (9 x 4 = 36); the double's dangling-link save, D-DOC-11 (2); and the
# model's R25c sentence, D-SRC-38's two and R25b's two direct pins (5). The
# reload fixture's three R25a cases are counted inside R9's one check.
# 2502 -> 2561 on 2026-10-16, R26 (lane-clean-a1): Model.stateSavePlan's and
# Model.stateBlockRecheck's tables and R26b's structural pin over every
# view's path to the one setText (3); and through the service harness on
# both hosts and both own-echo modes, R26a's ten (D-SRC-29 by rename and by
# re-point, D-SINK-21 and its file-link sibling, D-SRC-35 by a favourite and
# by a source verb, D3/W3's discrimination, the watchdog, the in-flight
# skip, a foreign write met by the read), R26b's two (D-SRC-46, the
# handler-write census), R26d's FRESH and R26c's file modes (14 x 4 = 56).
# The seven families R26a's premise moved were re-levelled in place, not
# added: R13 and R25a bursts, R21e D-SRC-18, R24a and R25b IN FLIGHT, R25d
# a7, and the R11 / R14 / R15 structural pins.
# 2561 -> 2565 on 2026-10-16, F4 (lane-clean-f1): "the read's bound is 2 s"
# through the service harness on both hosts and both own-echo modes (4).
# F-HARNESS-31's sixteen (R24a IN FLIGHT, R25d a7, R25b's in-flight saved
# search, R26b's census, each x 4) were re-levelled in place to the
# same-instant loss, not added.
# 2565 -> 2572 on 2026-10-17, the split's reviews P2/P3a (lane-split-f1): the
# damaged-helper reply mapped through the shared helper-damaged fixture (4),
# its routing as no_output's (1), every other reply reader unchanged by it
# (1), and Service.qml's own status branch through the harness (1).
# 2572 -> 2634 on 2026-10-20, R27 (lane-sweep-a1): R27a's waits, second
# read and read-timeout mode (window a twice, the wait's bound, window c
# three times, D-SRC-47's mechanism: 7 x 4), R27e's notice family (5 model,
# and the start/mid title and the entry-refusal journal line x 4), R27c (2
# x 4) and R27d (6 model, 3 x 4); the eviction pins were replaced, not added.
# 2634 -> 2692 on 2026-10-20, R28 (lane-sweep-a2), +58: R28a (2 model --
# the schedule, the stall notice -- and 9 x 4 through the harness: the
# silent read on its schedule, six ways the wait ends, the join, the
# restart; R27a's three window-c pins, 3 x 4, are gone), R28c's three
# resets (3 x 4), R28b (2 model, 2 x 4), R28e's two ways-back pins (2 x 4)
# and its probe line and one cap (2 model). The write-wait bound pin and
# R27e's five fixture pins were re-levelled in place.
# 2692 -> 2651 on 2026-10-20, R29a (lane-sweep-a3), -41, a DELETION the
# lead's ruling ordered: R28a's held save past the read's bound came out --
# its 2 model pins (the schedule, the stall notice) and its 9 x 4 harness
# pins, and R28c's read-state reset (1 x 4), the state it reset gone with
# it -- and one model pin came in (the withdrawal: no 74019, no notice, the
# cited names inert). R26a's two bound pins went back to 6f1d176's answer
# (saved without the read at 2 s), and the write-wait bound and R28c's two
# expiry pins were re-levelled in place to it.
# 2651 -> 2664 the same day, R29d and R29e's notice (lane-sweep-a3), +13:
# R29d through the service harness on both hosts and both own-echo modes
# (3 x 4: the unusable playlist beside A's own guide URL, the same entry
# with no source, and the seen playlist with a guide URL arriving before
# the marker lands) and the pair's notice (1 model); the shared fixture's
# three new adopt cases and R29e's "becomes the active source" sentence
# are counted inside checks that existed.
# 2664 -> 2678 on 2026-10-20 (the P3 sweep's finishing round, lane-sweep-f4):
# +4 F1 race and +4 F1 same-playlist sibling through the service harness
# (both hosts, both own-echo modes), +1 F1 model, +1 F4 (R29d's CLI origin),
# +4 F2 (window (c) decided by when the other program writes).
# 2678 -> 2679 on 2026-10-21 (lane-bounds-l, D-SRC-45 / D-LOGO-12): the
# shell's reading of the logos verb's no_cache refusal and of a summary at
# the ceiling (seen red on a mutation of Model.logoSummaryNames).
# 2679 -> 2699 on 2026-10-21 (lane-bounds-g, R30c / R30e): the shared
# logo-deadlines fixture's three numbers (2) and its thirteen summary lines
# through Model.logoSummaryNotice (13), and Service.qml's own logoFetchWatchdog
# interval and onTriggered, logoFetchProc's onRunningChanged and onExited, and
# onLogoLine's journal line, compiled against fakes (5). All 20 red against
# lane-bounds-int's Service.qml and model (17a2407).
NODE_CHECKS_MIN=${NODE_CHECKS_MIN:-2699}
# 1047 -> 1084 and a11y 34 -> 35 on 2026-10-12, D-REL-5: the split model's
# script and ceiling tests (tests/test_split_model.py, test_release.py), the
# .mjs byte scans, the ledger's resolver over every part, and the fidelity
# guard over every model file. The python floor sat one under the 1048 on the
# tree before them; it is level again. 1084 -> 1123 the same day, D-REL-5
# round 2: the Model-member judge (11), every static import form and the
# unreadable-model message (11), the generated header and the dropped-line
# record (7), the shipped Model.js refusal (6), and F-HARNESS-19's shell pin (4).
# 1123 -> 1143 on 2026-10-12, D-SINK-19 round 10 (R20f): the chain's 12
# (the merge never levelled them), round 10's six R20a helper tests and the
# ledger's two R20e cases.
# 1126 -> 1136 on 2026-10-13, F-HARNESS-20: tests/test_harness_home.py, run.sh's
# harness_env and seeding asked where the SHIPPED helper, Python and mpv land,
# against a decoy home the shield must not touch (10).
# 1153 -> 1152 on 2026-10-13, D-SINK-19 round 11 (R21d): test_state's six
# round-9/10 key tests (pendingEpg, entryInputs, epgSetAt, their stdout and
# slot pins) replaced by five for the migration marker and the withdrawn
# set time; and 1152 -> 1153 the same day, the ledger's withdrawn-symbol
# waiver (tests/test_defect_ledger.py, 1).
# 1153 -> 1170 the same day, round 12 (R22): test_state's twelve R22a helper
# cases (what `state init` found, that it never rewrites what it could not
# parse, every verb refusing an unread state), tests/test_shipped_copy.py's
# three (R22c, no shipped string sends the user to a retired setting) and the
# ledger's two (R22d, an unused waiver is red; the twenty are gone).
# 1170 -> 1180 the same day, round 13 (R23b, R23d): test_state's ten
# StateNeverBlocksTest cases, the real helper as a subprocess with a timeout
# over a FIFO, a socket and a directory at the state path, a file where the
# state directory should be, and a symlink to a 0000 file.
# 1180 -> 1194 on 2026-10-14, round 14 (R24b, R24d, F-HARNESS-25):
# test_state's eight StateSymlinkTest cases and the not-a-dir verb case
# (9), StateInitDeadlineTest's three (the init's own SIGALRM), and
# tests/test_harness_home.py's two PrivateBusIsolatesHome cases (private-
# bus.sh and the filewatch spike run for real against a decoy home).
# 1194 -> 1202 the same day, round 15 (R25c, D-SRC-34, F-HARNESS-27):
# test_state's five StateFolderLinkTest cases and FolderLinkSiblingsTest's
# one (the real helper over a link at the state folder and at every other
# folder ensure_private_dir makes), the in-process init's alarm (1), and
# test_logos's logo-folder link (1).
# 1202 -> 1229 on 2026-10-15, D-LOGO-13: tests/test_logo_chunks.py (27), the
# canonical PNG over ordinary images -- what it keeps and drops, what it
# refuses, `write_logo` and both branches of `logos --fetch`, and Qt drawing
# the canonical file and the original identically.
# 1229 -> 1240 on 2026-10-16, D-LOGO-14 and D-EPG-6 (levelled for 0.14.2):
# GifCanvasTest (7), a GIF's canvas as its frames' edges over GIFs built in
# the test, and EntityDeclarationTest (4), an XMLTV feed that declares an
# entity refused and one that does not parsed as before.
# 1240 -> 1272 on 2026-10-17, D-REL-7 landed on dev: tests/test_split_helper.py
# (27), the split script's every decision and the stub's one-namespace
# property over synthetic one-file helpers and this tree; and test_release's
# five for the parts (the resolver both ways, an unreadable list, the parts as
# shipped sources, the whole helper and nothing else under bin/ shipping).
# 1272 -> 1284 on 2026-10-17, the split's reviews P2/P3a/P3b (lane-split-f1):
# the damaged-part matrix over the real helper (16 damages as subtests of one
# test, and its intact control: 2), nothing runs before every part is checked
# (2), the symlinked stub and plugin directory (2), the check's last-line rule
# (1), and --seal (5). The bytecode directory's exemption became a stray in
# place, not added.
# 1284 -> 1293 on 2026-10-17, the split follow-up's P1/P2a-c/P3s
# (lane-split-f2): an add and an ff update cloned under core.autocrlf=true
# (1), a CRLF part matching its entry in the gate (1), a name starting with
# "." ignored by the gate and the stub (1) and by the real helper's verbs
# (1), parts of two releases refused both ways (2: the control, the mixes),
# every step of an update emulated and every byte prefix of the stub (2),
# and --version through a symlink to the stub (1). The last-line rule became
# the entry rule in place, and --seal's stale-line case became its removal
# of that line, not added; the matrix's subtests went 16 -> 18, gaining a
# FIFO, a part of another release, an entry one byte short and __pycache__,
# and losing the wrong last line and the swap file (now the ignored case).
# 1293 -> 1321 on 2026-10-20, D-M3U-1 (lane-m3u-a1): tests/test_m3u_bounds.py,
# 28 cases -- the per-channel caps over a few KB per field (16), the fixtures
# untouched by every cap and parsed alike line by line and whole (3), the
# memory limit observed in a subprocess, refusing ordinary inputs when set
# low and leaving RLIMIT_DATA at 512 MiB when run as the program, and a
# local source no longer reserving the input cap (7), and
# the TLS context built ahead of the limit, verifying (2). 25 of them seen
# red against 0.14.2 (85206f2); the other three pin what did not change.
# 1321 -> 1342 on 2026-10-21, D-SRC-13 / D-M3U-3 / D-M3U-4 (lane-bounds-p):
# tests/test_reply_bounds.py, 21 cases -- the playlist status line's warnings
# bounded by count through the verb with the cap lowered (2), the memory
# limit lifted before every status write and every printed line, observed
# in a real helper process at each open and each write (5) and in process
# by call order (1), every counted sentence for one and for many (3), and
# the rule-15 replies: tracks (4), the first-load reason (3), main()'s
# answer to a bug (3). 16 seen red on f55a32f, the other 5 on a mutation of
# the shipping decision. test_m3u_bounds's "leaves RLIMIT_DATA at 512 MiB"
# case became "holds it while parsing and lifts it after", in place.
# 1321 -> 1338 on 2026-10-21 (lane-bounds-l): tests/test_logo_ceiling.py (7),
# D-LOGO-12's ceiling on what a source's logo folder holds, over a real
# local TLS server with the cap lowered, and D-SRC-45's no_cache answer;
# test_failed_marks's MissingIdTest (1), the rule-15 sibling; and
# tests/test_epg_retention.py (9), D-EPG-7's compact retention held
# byte-identical to f55a32f's output, its measured cost, and the bounded
# time memo. All seen red on f55a32f except the three differential cases,
# which compare against f55a32f itself and were seen red on four mutations.
# LogoFetchCapTest was rewritten for the ceiling in place, not added.
# 1342 / 1338 -> 1359 on 2026-10-21, the two lanes together (lane-bounds-int).
# 1359 -> 1390 on 2026-10-21 (lane-bounds-g, R30a-c / R30e, D-SRC-59,
# D-SRC-60): tests/test_fetch_bounds.py (16) -- the five redirect methods of
# both openers closing a 3xx body unread (2), the whole download held to one
# deadline over a local scripted server with the deadline lowered (7), the
# status line's text redacted then cut (3), stale temporaries swept by the
# first write into a folder (4); tests/test_logo_run.py (15) -- one logo's
# and the run's deadline and a redirect body over TLS (3), the memory limit
# observed in a real helper process (1), the folder lock (3), the ceiling's
# sweep of unnamed files and of a stale temporary (3), the folder's age and
# its mark (3), the shared fixture (2). 29 red on lane-bounds-int (17a2407),
# the other 2 on a mutation of the shipping decision.
PY_TESTS_MIN=${PY_TESTS_MIN:-1390}
QMLLINT_FILES_MIN=${QMLLINT_FILES_MIN:-5}
A11Y_TESTS_MIN=${A11Y_TESTS_MIN:-35}
# The M2-03 entry preflight: 20 seams plus its own "ran every check" line.
CHNO_ENTRY_MIN=${CHNO_ENTRY_MIN:-21}
# The M2-05 picture-in-picture preflight: 34 seams (integration added the
# four the scenario's header reserved for a merged lane V1, and four more for
# PIP15's single dispatch spelling and the snapshot key's one name), the
# stub's executable probe, and its own "ran every check" line.
PIP_PREFLIGHT_MIN=${PIP_PREFLIGHT_MIN:-41}
# The marketplace scan surface: 30 tracked files at the time this landed. A
# floor for the same reason as every other number here -- a scan that reads
# nothing exits 0 having proved nothing at all.
MARKETPLACE_FILES_MIN=${MARKETPLACE_FILES_MIN:-35}
# The text format guard: 49 Text blocks across the three shipped .qml files
# when this landed (D-TEXT-1). A floor for the same reason again -- the guard
# derives its file list from the release allowlist, and a list that resolves
# to nothing would scan nothing and exit 0 if the guard did not refuse that
# itself; this is the second line of defence, in the gate's own vocabulary.
# 61 -> 58 on 2026-10-13, D-SINK-19 round 11 (R21): the guide's three Text
# blocks that advertised `omarchy bar set ... playlistUrl|epgUrl` (the
# unconfigured surface's command box and its EPG line, and the first-run
# form's terminal caption) are gone with the route; every remaining one still
# declares its format.
TEXT_BLOCKS_MIN=${TEXT_BLOCKS_MIN:-58}
# The player stub's self-test (M5-01): 14 cases when wired in, 16 with F-RWD-15, 17 with the ordering cases, 19 with the F-MPV-1 broadcast pair.
# 19 -> 26 on 2026-10-07: the stub learned tls-verify and stream-lavf-o for
# D-SINK-16. The lane that grew it reported there was no floor on this step;
# there is, it sits here, and leaving it at 19 would have let seven cases be
# deleted without the gate noticing. Found by the review of that lane.
STUB_TESTS_MIN=${STUB_TESTS_MIN:-28}
# The D-LOGO-11 logo preflight (scripts/dev-harness/logo-scenario.sh
# check-tree): 32 checks over the shipping helper as a subprocess and the
# shell's Image as a probe under an address-space rlimit, plus its own "ran
# every check" line. 28 -> 32 on 2026-10-11: three reviewer-crafted bombs
# (an EXIF thumbnail before the real frame header, a 64x65535 column, a
# two-frame GIF) and the EXIF control. The red run against the shipped
# 0.13.3 (159da94) answers 9 passed, 24 failed; recipe in the scenario's
# footer, and scripts/qa-lib-test.sh asserts this number is the scenario's
# EXPECTED_CHECKS plus one.
LOGO_PREFLIGHT_MIN=${LOGO_PREFLIGHT_MIN:-33}
# The D-CLIP-1 clipboard preflight (scripts/dev-harness/clip-scenario.sh
# check-tree): 6 checks over the lead's three probes inside a nested headless
# cage -- the editable TextField reads a 25 MB foreign offer in full, the
# read-only one and the no-field window read nothing, a consumer on that
# display gets every byte, and everything started is gone by its pid -- plus
# its own "ran every check" line. The shell arm (the real Guide.qml over
# 100 MB: red on --baseline d55149b at +286 MB with a 723 ms stall, and red
# on --baseline 96f5261 at +310 MB over one Ctrl+V, the shell collecting
# wl-paste's whole output before the cut) is the live mode's, for a human.
# scripts/qa-lib-test.sh asserts this number is the scenario's check-tree
# EXPECTED_CHECKS plus one.
CLIP_PREFLIGHT_MIN=${CLIP_PREFLIGHT_MIN:-7}
# The D-SINK-19 key preflight (scripts/dev-harness/key-scenario.sh
# check-tree): 10 checks over the harness's own instrument -- entryKey in
# harness-lib.js, driven from node with the tree's Model.js (lead ruling R6:
# `sourceKey` first, the URL hash second, named candidates only; the first
# repair would have reported a user's `mpvArgs` of "deadbeef" as the active
# source) and three seams that keep shell.qml, hostEntry and run.sh reading
# through it -- plus its own "ran every check" line. The shell arm (the real
# Service.qml under cage over ten seeded starts: the start-up adoption
# watched across the dirs becoming ready with the reload the helper's chmod
# fires (D-SRC-15, R9 read off the service's own counter), a fresh install
# with no state.json, the two-source migration, the idempotent second
# start, a URL and an EPG set while the shell was down, the remove of the
# active source, and a SIGKILL between the two writes of a pointer change)
# is the live mode's, for a human; its STATUS paragraph records the drop it
# found on lane-key-r1 and the counts on the tree that closes it.
# scripts/qa-lib-test.sh asserts this number is the scenario's check-tree
# EXPECTED_CHECKS plus one.
# 11 -> 12 on 2026-10-20, R29e (lane-sweep-a3): S4, init_pids answers this
# run's start-up init only (its own --state-dir), seen red on the unscoped
# scanner that read another harness's helper as `left:` in B14.
KEY_PREFLIGHT_MIN=${KEY_PREFLIGHT_MIN:-12}
# R27f (2026-10-20, D-PERF-1): the async open instrument's preflight, plus
# the scenario's own "ran every check" line. The live arm (the guide's open at
# 10,000 channels under cage, cold and warm, list and wall) is a human's.
# 9 -> 16 on 2026-10-20, R28d (lane-sweep-a2): the instrument counts what is
# DRAWN -- HarnessLib.openDrawnSet driven over ten frames (D1..D10),
# openDrawnSettle over four (E1..E4) and the seam (S1); R27f's openSettle and
# its seven traces are gone with it.
# 16 -> 19 on 2026-10-20, R29e (lane-sweep-a3): D11..D13, a delegate at
# effective opacity 0 is not drawn (a screen of them, one of them) and one
# at 0.3 is (the claim narrowed to "painted at all"); seen red on the
# harness-lib that read visible alone.
OPEN_PREFLIGHT_MIN=${OPEN_PREFLIGHT_MIN:-19}

step() { printf '\n== %s\n' "$*"; }
ok()   { printf 'ok   %s\n' "$*"; }
bad()  { printf 'FAIL %s\n' "$*"; fail=1; }

# --- the corpus the two byte scans run over -------------------------------
#
# E3, kept because it is the first half of the same story: the ASCII list used
# to be hand-maintained, and `[[ -f $file ]] || continue` dropped directories -
# so scripts/gen-playlist.py (a .py source, which CLAUDE.md rule 8 covers),
# every scripts/*.sh, everything under scripts/dev-harness/ and every fixture
# SUBdirectory went unscanned. The gate was green partly by accident:
# tests/fixtures/qa-nonascii/ was skipped because it is a directory, not
# because anyone excluded it. That is why the list is a pathspec against git
# and the exclusions are BY NAME.
#
# F-GATE-1. Both scans were driven from `git ls-files`, which lists the INDEX.
# A file that EXISTS in the working tree but has not been staged was therefore
# not scanned at all -- and a lane adding files is precisely the population
# these two checks exist to police. Found by the helper lane on itself: its
# first commit was red for a literal e-acute in a brand-new test file, a byte
# this gate had called green minutes earlier, because the check that was meant
# to stop it ran before the `git add` that made it visible. The printed count
# ("162 files scanned") read as coverage while silently excluding exactly that
# population, which is CLAUDE.md rule 14's shape: a check that cannot go red
# for the failure it guards is not a check.
#
# `--cached --others --exclude-standard` is the whole fix:
#   --cached            everything in the index -- ls-files' old default, so
#                       nothing that used to be scanned stops being scanned
#   --others            every path present in the working tree that is NOT in
#                       the index: the new file, BEFORE it is staged
#   --exclude-standard  apply .gitignore, .git/info/exclude and
#                       core.excludesFile. This one is load-bearing, not
#                       tidiness: without it the scan reads __pycache__/*.pyc,
#                       which are control bytes end to end, and the gate is
#                       red for everyone who has ever run the python suite.
# The two sets are disjoint -- a path is in the index or it is an "other",
# never both -- so the count does not double-count. The untracked share is
# printed SEPARATELY so the number stays honest about what it scanned.
#
# Rejected: `find`, which cannot read .gitignore and would walk .git/ and
# node_modules/; and `git status --porcelain`, which reports only CHANGED
# tracked paths and would drop the clean majority of the corpus.
#
# Consequence, accepted deliberately: an unignored stray file in the working
# tree is now scanned, and fails the gate if it carries the bytes rule 8
# forbids. That is wanted. An unignored file in the tree is a file somebody is
# about to commit -- `git add -A` cannot tell whose it is (rule 4b) -- and the
# declaration that a path is scratch belongs in .gitignore, where the next
# contributor can also see it. The finding line says "untracked" and names
# that remedy so the diagnosis is one line rather than a puzzle.
gate_corpus=()
declare -A gate_is_new=()
gate_load_corpus() {   # argv: pathspecs. Fills gate_corpus[] and gate_is_new[].
  local rel
  gate_corpus=()
  gate_is_new=()
  while IFS= read -r -d '' rel; do gate_is_new["$rel"]=1; done \
    < <(git -C "$ROOT" ls-files --others --exclude-standard -z -- "$@")
  while IFS= read -r -d '' rel; do gate_corpus+=( "$rel" ); done \
    < <(git -C "$ROOT" ls-files --cached --others --exclude-standard -z -- "$@")
}
gate_new_suffix() {   # $1: repo-relative path. A note if it is not in the index.
  [[ -v gate_is_new[$1] ]] || return 0
  printf ' (untracked -- in your tree, not in the index; if it is scratch, .gitignore it)'
}

gate_ascii_scan() {
  local rel file suffix bad_any=0 scanned=0 newly=0
  local -a specs=( '*.js' '*.mjs' '*.py' '*.json' 'bin/*' 'scripts/*.sh' \
                   'scripts/dev-harness/*' 'tests/fixtures/*' 'docs/ARCHITECTURE.md' )
  local -a exempt_files=( 'tests/fixtures/qa-player/qa-player.m3u' \
                          'scripts/dev-harness/fixtures/harness.m3u.in' )
  gate_load_corpus "${specs[@]}"
  for rel in "${gate_corpus[@]}"; do
    # Product owner ruling, 2026-09-14. The gate exists so that SOURCE stays
    # ASCII: escapes stay escapes and no tool silently rewrites a byte. A data
    # fixture that carries non-ASCII is the opposite case - carrying it IS what
    # it tests, because channel names are Cyrillic, Japanese and accented Latin
    # in the real world. So fixtures are exempt, but only BY NAME, one line per
    # file with the reason. A directory-wide glob would let the next file in
    # slip past unnoticed, which is how this gate was quietly green before.
    case $rel in
      */nonascii/*|tests/fixtures/qa-nonascii/*) continue ;;       # a whole tree, named for the purpose
      tests/fixtures/qa-player/qa-player.m3u) continue ;;          # channel names in German, Japanese and a check mark
      scripts/dev-harness/fixtures/harness.m3u.in) continue ;;     # channel names in French and Russian
    esac
    file="$ROOT/$rel"
    [[ -f $file ]] || continue
    scanned=$(( scanned + 1 ))
    [[ -v gate_is_new[$rel] ]] && newly=$(( newly + 1 ))
    if LC_ALL=C grep -n -P '[^\x00-\x7F]' "$file" >/dev/null; then
      suffix=$(gate_new_suffix "$rel")
      printf 'non-ASCII bytes in %s%s:\n' "$rel" "$suffix"
      LC_ALL=C grep -n -P '[^\x00-\x7F]' "$file" | head -5
      bad_any=1
    fi
  done
  # An exclusion that names a file which no longer exists is a dead line: it
  # goes on reading like a considered exemption while guarding nothing, and the
  # next person to move that fixture gets no signal. Same join-by-name failure
  # as rule 13, inside this very step, so assert the join.
  for rel in "${exempt_files[@]}"; do
    if [[ ! -f "$ROOT/$rel" ]]; then
      printf 'ascii exclusion names a path that does not exist: %s\n' "$rel"
      bad_any=1
    fi
  done
  if (( scanned == 0 )); then
    bad "ascii check scanned no files at all (is this a git checkout?)"; return 1
  elif (( bad_any )); then
    bad "ascii check ($scanned files scanned, $newly untracked)"; return 1
  else
    ok "ascii check ($scanned files scanned, $newly untracked)"; return 0
  fi
}

gate_control_scan() {
  local rel file suffix bad_any=0 scanned=0 newly=0
  local -a specs=( '*.js' '*.mjs' '*.py' '*.qml' '*.json' '*.sh' 'bin/*' 'scripts/dev-harness/*' )
  gate_load_corpus "${specs[@]}"
  for rel in "${gate_corpus[@]}"; do
    case $rel in
      *.gz|*.png|*.jpg) continue ;;                               # binary by definition
    esac
    file="$ROOT/$rel"
    [[ -f $file ]] || continue
    scanned=$(( scanned + 1 ))
    [[ -v gate_is_new[$rel] ]] && newly=$(( newly + 1 ))
    # -a is load-bearing: without it grep SKIPS the file the moment it holds a
    # NUL, which is exactly the file this check exists to find.
    if LC_ALL=C grep -a -q -P '[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]' "$file" 2>/dev/null; then
      suffix=$(gate_new_suffix "$rel")
      printf 'raw control bytes in %s%s (write them as \\uXXXX escapes)\n' "$rel" "$suffix"
      bad_any=1
    fi
  done
  if (( scanned == 0 )); then
    bad "control-byte check scanned no files at all"; return 1
  elif (( bad_any )); then
    bad "control-byte check ($scanned files scanned, $newly untracked)"; return 1
  else
    ok "control-byte check ($scanned files scanned, $newly untracked)"; return 0
  fi
}

# One byte scan, against one root, and nothing else. This is the door
# tests/test_gate_file_scan.py drives: it builds throwaway git repositories in
# a temp directory and runs the REAL functions above over them, rather than
# reimplementing the scan in python where it could pass while the gate is
# broken (CLAUDE.md 12). It must stay above the first `step` so that no other
# gate runs, and it never touches this repository.
if [[ ${1:-} == --byte-scan ]]; then
  if (( $# != 3 )); then
    printf 'usage: %s --byte-scan ascii|control <root>\n' "$0" >&2; exit 2
  fi
  ROOT=$(cd "$3" 2>/dev/null && pwd) || { printf 'no such root: %s\n' "$3" >&2; exit 2; }
  case $2 in
    ascii)   gate_ascii_scan ;;
    control) gate_control_scan ;;
    *)       printf 'unknown scan: %s\n' "$2" >&2; exit 2 ;;
  esac
  exit $?
fi

step "omarchy plugin validate $ROOT"
if omarchy plugin validate "$ROOT"; then ok "manifest valid"; else bad "manifest invalid"; fi

step "qmllint (imports: $QMLROOT, $QML_IMPORTS)"
mkdir -p "$QMLROOT/qs" || bad "could not create the qmllint import root $QMLROOT"
ln -sfn "$SHELL_DIR/Commons" "$QMLROOT/qs/Commons" || bad "could not link qs.Commons into $QMLROOT"
ln -sfn "$SHELL_DIR/Ui" "$QMLROOT/qs/Ui" || bad "could not link qs.Ui into $QMLROOT"
[[ -d $QMLROOT/qs/Commons && -d $QMLROOT/qs/Ui ]] || bad "qs.Commons / qs.Ui do not resolve under $QMLROOT"
if [[ ! -x "$QT_BIN/qmllint" ]]; then
  # Name the package, not an install command: the marketplace security baseline
  # scans this file as commands and cannot tell a message string from a real one.
  # scripts/check-marketplace-capabilities.py is what holds this phrasing in
  # place; this comment alone never did.
  bad "qmllint not found at $QT_BIN/qmllint (it ships in the qt6-declarative package)"
else
  linted=0
  # E2: the list was "$ROOT"/*.qml and "$ROOT"/tests/*.qml, so
  # scripts/dev-harness/shell.qml - the fake EVERY scenario in this repo runs
  # against, and the thing CLAUDE.md rule 10 says must never be more forgiving
  # than the real host - was never linted. A QML error there leaves this gate
  # green while every harness scenario fails to start.
  #
  # The harness fake imports "Model.mjs", which run.sh stages beside it in the
  # scratch root with the parts under model/ it re-exports (D-REL-5). Lint it
  # the way it actually runs, or the import warning is noise and the Model.*
  # calls are never resolved at all.
  stage="$CHECK_TMP/dev-harness"
  mkdir -p "$stage"
  for f in "$ROOT"/scripts/dev-harness/*.qml "$ROOT"/scripts/dev-harness/*.js; do
    [[ -f $f ]] || continue
    cp "$f" "$stage/" || bad "could not stage $(basename "$f") for linting"
  done
  ln -sfn "$ROOT/Model.mjs" "$stage/Model.mjs"
  ln -sfn "$ROOT/model" "$stage/model"
  for file in "$ROOT"/*.qml "$ROOT"/tests/*.qml "$stage"/*.qml; do
    [[ -f $file ]] || continue
    linted=$(( linted + 1 ))
    output=$("$QT_BIN/qmllint" -I "$QMLROOT" -I "$QML_IMPORTS" "$file" 2>&1)
    lint_status=$?
    errors=$(grep -c -E '^Error:|: error:|Error at' <<<"$output")
    (( lint_status == 0 )) || errors=$(( errors + 1 ))
    warnings=$(grep -c -E 'Warning:|: warning:' <<<"$output")
    # D-REL-5: qmllint 6.11 reads no ES module's exports, so since the model
    # became Model.mjs every Model member it reaches is a `missing-property`
    # on type "Model". The first version of this comment said the classic
    # Model.js was not resolved either, so no check was lost. Measured, that
    # was false: Model.js WAS resolved, a real member drew nothing and a
    # mistyped one drew a warning naming it (BarWidget.qml 0 -> 1). Here that
    # warning would be one line in a bucket of hundreds. So the member lines
    # are counted apart, to keep the rest comparable with the baseline, and
    # every name in them is judged against the aggregator's export names by
    # check-model-members.py: an unknown one is red. Not covered, measured on
    # the three entry points: a member qmllint never reaches (82 code
    # positions; the classic Model.js reached 1 of them).
    model_members=$(grep -c -E 'not found on type "Model" \[missing-property\]' <<<"$output")
    members_out=$(python3 "$ROOT/scripts/check-model-members.py" --root "$ROOT" --file "$file" <<<"$output")
    members_status=$?
    if (( errors > 0 )); then
      bad "$(basename "$file"): $errors error(s), $warnings warning(s)"
      printf '%s\n' "$output"
    else
      ok "$(basename "$file"): 0 errors, $(( warnings - model_members )) warning(s) + $model_members on Model members"
      if [[ ${CHECK_VERBOSE:-0} == 1 && -n $output ]]; then printf '%s\n' "$output"; fi
    fi
    if (( members_status != 0 )); then
      bad "$(basename "$file"): a Model member that Model.mjs does not export"
      printf '%s\n' "$members_out"
    fi
  done
  # `[[ -f $file ]] || continue` means an unmatched glob lints NOTHING while
  # the gate reports green. Count what was actually linted.
  if (( linted < QMLLINT_FILES_MIN )); then
    bad "qmllint examined $linted file(s), expected at least $QMLLINT_FILES_MIN"
  else
    ok "qmllint examined $linted file(s)"
  fi
fi

step "node tests/Model.test.js"
if command -v node >/dev/null 2>&1; then
  node_log="$CHECK_TMP/node.log"
  if node "$ROOT/tests/Model.test.js" >"$node_log" 2>&1; then
    cat "$node_log"
    # The runner prints "<n> checks, <m> failure(s)". An emptied or renamed
    # test file exits 0 having asserted nothing; assert the count.
    node_checks=$(grep -oE '^[0-9]+ checks' "$node_log" | head -1 | grep -oE '^[0-9]+')
    if [[ -z $node_checks ]]; then
      bad "node tests printed no check count at all"
    elif (( node_checks < NODE_CHECKS_MIN )); then
      bad "node tests ran $node_checks checks, expected at least $NODE_CHECKS_MIN"
    else
      ok "node tests ($node_checks checks)"
    fi
  else
    cat "$node_log"; bad "node tests"
  fi
  # R23g (round 13). The real FileView delivers the reload its OWN save
  # raises only sometimes (never for a lone save at idle; under load, or
  # with a later write queued, it lands carrying our own text), measured in
  # scripts/dev-harness/spikes/filewatch/. The harness delivers it by
  # default; this run delivers it never, so a pin that holds only because
  # the echo arrived goes red here. Same suite, same count.
  node_log2="$CHECK_TMP/node-no-echo.log"
  if IPTV_HARNESS_OWN_ECHO=none node "$ROOT/tests/Model.test.js" >"$node_log2" 2>&1; then
    node_checks2=$(grep -oE '^[0-9]+ checks' "$node_log2" | head -1 | grep -oE '^[0-9]+')
    if [[ -z $node_checks2 || $node_checks2 != "${node_checks:-}" ]]; then
      bad "node tests without the own-write echo ran ${node_checks2:-no} checks, against ${node_checks:-no} with it"
    else
      ok "node tests without the own-write echo, R23g ($node_checks2 checks)"
    fi
  else
    grep -E 'FAIL|failure' "$node_log2" | head -40; bad "node tests without the own-write echo (R23g)"
  fi
else
  bad "node not found (dev-only dependency: mise use node)"
fi

step "python3 -m unittest discover -s tests"
py_log="$CHECK_TMP/python.log"
if (cd "$ROOT" && python3 -m unittest discover -s tests) >"$py_log" 2>&1; then
  cat "$py_log"
  # `Ran 0 tests ... OK` exits 0. A tests/ directory that stops being
  # discoverable is invisible without this.
  py_tests=$(grep -oE '^Ran [0-9]+ test' "$py_log" | head -1 | grep -oE '[0-9]+')
  if [[ -z $py_tests ]]; then
    bad "python tests printed no test count at all"
  elif (( py_tests < PY_TESTS_MIN )); then
    bad "python ran $py_tests tests, expected at least $PY_TESTS_MIN"
  else
    ok "python tests ($py_tests tests)"
  fi
else
  cat "$py_log"; bad "python tests"
fi

step "model split (scripts/split-model.mjs --check)"
# D-REL-5. The model is Model.mjs and the parts under model/ it re-exports.
# This proves the tree as it stands: every part's generated import and export
# lines are what the script would write, no top-level initializer reads
# another part (a cyclic import hands it undefined, silently -- measured), no
# code writes to a top-level binding, every part loads, and Model.mjs exports
# exactly the names its own lines list. `--relink` repairs the generated lines
# after an edit adds a call across parts.
if command -v node >/dev/null 2>&1; then
  if node "$ROOT/scripts/split-model.mjs" --check --root "$ROOT" >"$CHECK_TMP/split.log" 2>&1; then
    ok "model split ($(grep -oE '^declarations: [0-9]+ in [0-9]+ parts' "$CHECK_TMP/split.log" | head -1))"
  else
    bad "model split"; cat "$CHECK_TMP/split.log"
  fi
else
  bad "node not found; the model split cannot be checked"
fi

step "helper split (scripts/split-helper.py --check)"
# D-REL-7. The helper is bin/omarchy-iptv, a stub that shields and then
# compiles the parts its HELPER_PARTS names, from bin/helper/, into its own
# namespace, so they run as the one file they were cut from. This proves the
# tree as it stands: the list is a literal of distinct names (read the one way
# every reader reads it, scripts/helper_files.py); the stub carries exactly
# the loader those names generate, directly after the shield, so nothing is
# compiled before the process is non-dumpable (D-SINK-9); every named part
# starts with the generated header, matches the length and CRC-32 its entry
# in the list gives (with CRLF read as LF, as the stub reads it, so a
# core.autocrlf checkout is not damage; an edit is sealed with --seal) and
# compiles; and bin/helper/ holds nothing the list leaves out but names
# starting with ".", a bytecode directory included, because the stub
# refuses to start beside any of it. The release allowlist step below proves
# every part ships, and the python suite runs the helper they make.
if python3 "$ROOT/scripts/split-helper.py" --check --root "$ROOT" >"$CHECK_TMP/split-helper.log" 2>&1; then
  ok "helper split ($(sed -n 's/^split-helper: check ok (\(.*\))$/\1/p' "$CHECK_TMP/split-helper.log" | head -1))"
else
  bad "helper split"; cat "$CHECK_TMP/split-helper.log"
fi

step "qmltestrunner tests/Model.spec.qml"
if [[ -x "$QT_BIN/qmltestrunner" ]]; then
  qml_log="$CHECK_TMP/qmltest.log"
  # F-HARNESS-20's sibling in the gate itself. Run with a decoy HOME and decoy
  # XDG directories on 2026-10-13, the whole gate left exactly two things in
  # the decoy, both from this step: a QML bytecode cache
  # (~/.cache/qmltestrunner/qmlcache) and ~/.config/fcitx/dbus. On an ordinary
  # run that decoy is the developer's real home, on every commit. Both are
  # content-free, and still not ours to write: the runner gets a home inside
  # CHECK_TMP, which the EXIT trap removes. (The clip and logo check-trees did
  # the same and are fixed in their own files.)
  qml_home="$CHECK_TMP/qml-home"
  mkdir -p -m 700 "$qml_home"
  if env -u MPV_HOME -u XCOMPOSEFILE HOME="$qml_home" XDG_CONFIG_HOME="$qml_home/.config" \
       XDG_CACHE_HOME="$qml_home/.cache" XDG_DATA_HOME="$qml_home/.local/share" \
       XDG_STATE_HOME="$qml_home/.local/state" QT_QPA_PLATFORM=offscreen \
       "$QT_BIN/qmltestrunner" -input "$ROOT/tests/Model.spec.qml" >"$qml_log" 2>&1; then
    # E1: this used to be `ok "qml spec ($(grep -c '^PASS' ...) passed)"` - the
    # count interpolated into a message, the grep's status discarded inside
    # the argument. A runner that exits 0 having executed ZERO test functions
    # printed `ok   qml spec (0 passed)` and the gate stayed green, while
    # CLAUDE.md and docs/QA-PLAYER.md cite the number as evidence.
    qml_passed=$(grep -c '^PASS' "$qml_log")
    if (( qml_passed < QML_SPEC_MIN )); then
      bad "qml spec ran $qml_passed test function(s), expected at least $QML_SPEC_MIN"
      cat "$qml_log"
    else
      ok "qml spec ($qml_passed passed)"
    fi
  else
    bad "qml spec"; cat "$qml_log"
  fi
else
  bad "qmltestrunner not found at $QT_BIN/qmltestrunner"
fi

step "scripts/qa-lib-test.sh (the harness predicates)"
# The tooling this project tests itself with is tested here. Every predicate
# is driven against the condition that used to make its check pass silently.
# Run with OMARCHY_IPTV_HARNESS_DIR UNSET (D-SINK-19 round 6, the round-5
# live lens's P3): the suite pins the DEFAULT transcript directory, and a
# gate started from a shell that exported the variable for a scenario run
# went red on that pin over a green tree. The suite sets the variable
# itself, per call, wherever it means to, and since round 7 the default pin
# unsets it inside its own subshell too (a bare run of the suite was still
# red, the round-6 live lens's P3); the `env -u` stays as belt and braces.
if env -u OMARCHY_IPTV_HARNESS_DIR bash "$ROOT/scripts/qa-lib-test.sh" >"$CHECK_TMP/qalib.log" 2>&1; then
  ok "harness predicates ($(grep -c '^PASS' "$CHECK_TMP/qalib.log") checks)"
  if [[ ${CHECK_VERBOSE:-0} == 1 ]]; then cat "$CHECK_TMP/qalib.log"; fi
else
  bad "harness predicates"; cat "$CHECK_TMP/qalib.log"
fi

step "scripts/qa-stub-mpv.py --self-test (the stub refuses like mpv)"
# M5-01: the player stub's seek semantics are measured facts (a seek below
# the floor answers success and moves nothing; a negative absolute target
# counts from the cache end; a loadfile restarts the timeline), and a stub
# more forgiving than mpv is the hazard rule 10 names. The cases live in the
# stub so they travel with it; the gate runs them so they cannot rot unseen.
if python3 -B "$ROOT/scripts/qa-stub-mpv.py" --self-test >"$CHECK_TMP/stub.log" 2>&1; then
  stub_n=$(grep -oE '^Ran [0-9]+ tests?' "$CHECK_TMP/stub.log" | grep -oE '[0-9]+' || echo 0)
  if (( stub_n >= STUB_TESTS_MIN )); then ok "player stub self-test ($stub_n cases)"
  else bad "player stub self-test ran $stub_n cases, floor $STUB_TESTS_MIN"; cat "$CHECK_TMP/stub.log"; fi
else
  bad "player stub self-test"; cat "$CHECK_TMP/stub.log"
fi

step "scripts/dev-harness/chno-entry-scenario.sh check-tree (M2-03 CN23)"
# The number-entry scenarios had no runner for a whole milestone, and nothing
# in this gate would have said so. The preflight half needs no display and no
# quickshell, so it runs here on every commit: if the four harness verbs or
# the seams they drive disappear, the gate goes red on this machine rather
# than on the display lane's, weeks later. It proves the code is present,
# never that it works - only the live half does that.
chno_log="$CHECK_TMP/chno-entry.log"
if bash "$ROOT/scripts/dev-harness/chno-entry-scenario.sh" check-tree >"$chno_log" 2>&1; then
  chno_checks=$(grep -c '^PASS' "$chno_log")
  if (( chno_checks < CHNO_ENTRY_MIN )); then
    bad "chno-entry preflight ran $chno_checks checks, expected at least $CHNO_ENTRY_MIN"
    cat "$chno_log"
  else
    ok "chno-entry preflight ($chno_checks checks)"
    if [[ ${CHECK_VERBOSE:-0} == 1 ]]; then cat "$chno_log"; fi
  fi
else
  bad "chno-entry preflight"; cat "$chno_log"
fi

step "scripts/dev-harness/pip-scenario.sh check-tree (M2-05)"
# The same preflight discipline for picture in picture, and for a sharper
# reason: PiP is the first feature here whose correctness depends on how a
# program OUTSIDE the plugin answers, so the seams that must exist are
# scattered across Service.qml, the harness fake and the stub compositor.
# This half needs no display, no quickshell and no hyprctl -- it proves the
# code is present, never that it works. Only the live half does that.
#
# D-PIP-6: the live half stays out of this gate, deliberately. It starts a
# quickshell and a real player, and no check that runs on every commit may do
# that on somebody's desktop. What changed is that the live half can no
# longer fail in silence: it refuses to start on a machine that cannot run it
# and exits 77, and scripts/qa-lib-test.sh (the step above) asserts that
# refusal is wired in. The live half is the display lane's to run, by hand,
# and its result belongs in docs/QA-RESULTS.md like every other live pass.
pip_log="$CHECK_TMP/pip-scenario.log"
if bash "$ROOT/scripts/dev-harness/pip-scenario.sh" check-tree >"$pip_log" 2>&1; then
  pip_checks=$(grep -c '^PASS' "$pip_log")
  if (( pip_checks < PIP_PREFLIGHT_MIN )); then
    bad "pip preflight ran $pip_checks checks, expected at least $PIP_PREFLIGHT_MIN"
    cat "$pip_log"
  else
    ok "pip preflight ($pip_checks checks)"
    if [[ ${CHECK_VERBOSE:-0} == 1 ]]; then cat "$pip_log"; fi
  fi
else
  bad "pip preflight"; cat "$pip_log"
fi

step "scripts/dev-harness/id-rotate-scenario.sh check-tree (D-ID-3)"
# The fix for D-ID-3 lives in Service.qml, which no unit test can reach; the
# scenario's live half proved it at the sink headless under cage. Its
# check-tree half runs here so the three seams the fix depends on cannot be
# refactored away silently: the map per parsed list, the move at apply, the
# write gated on a move. Floor recipe in the scenario's footer.
ID_ROTATE_MIN=${ID_ROTATE_MIN:-14}
idrot_log=$CHECK_TMP/id-rotate.log
if "$ROOT/scripts/dev-harness/id-rotate-scenario.sh" check-tree >"$idrot_log" 2>&1; then
  idrot_n=$(grep -cE '^(PASS|ok) ' "$idrot_log" || true)
  if (( idrot_n < ID_ROTATE_MIN )); then cat "$idrot_log"; bad "id-rotate preflight ran $idrot_n checks, expected at least $ID_ROTATE_MIN"; else ok "id-rotate preflight ($idrot_n checks)"; fi
else
  cat "$idrot_log"; bad "id-rotate preflight"
fi

step "scripts/dev-harness/logo-scenario.sh check-tree (D-LOGO-11)"
# A provider logo's HEADER chose how much memory the shell allocated: 304
# bytes took the row slot's Image to 840 MB (the fifth maintainer finding,
# docs/QA-RESULTS.md 2026-10-09). The unit tests prove the parsers; this
# half observes the two sinks -- the helper as the subprocess the service
# runs, over a loopback https provider, and the shell's Image as an offscreen
# probe under a 2.5 GB address-space rlimit (util-linux prlimit, on the qml
# process alone) -- so the gate goes red if the sweep, the refusal or the
# announcement stops happening, not only if a function changes its answer.
# It needs no network beyond loopback, no display, and it never decodes a
# bomb: on the fixed tree the helper withholds every one, and the 840 MB arm
# is `--baseline 159da94`, which a human runs.
#
# A machine without python3, openssl, prlimit or the qml runtime answers 77
# with the reason, and that is RED here unless LOGO_PREFLIGHT_SKIP_OK=1 is
# set in the environment. The first version printed the SKIP and went on to
# `all green`, so a machine with no qml runtime reported a green gate having
# observed neither sink; a scenario that measured nothing has proved nothing,
# and a gate that calls that green is the rule-14 shape. The reason prints
# either way, so the SKIP is never silent.
logo_log=$CHECK_TMP/logo-scenario.log
"$ROOT/scripts/dev-harness/logo-scenario.sh" check-tree >"$logo_log" 2>&1; logo_rc=$?
if (( logo_rc == 0 )); then
  logo_n=$(grep -c '^PASS' "$logo_log" || true)
  if (( logo_n < LOGO_PREFLIGHT_MIN )); then cat "$logo_log"; bad "logo preflight ran $logo_n checks, expected at least $LOGO_PREFLIGHT_MIN"; else ok "logo preflight ($logo_n checks)"; fi
elif (( logo_rc == 77 )); then
  logo_why=$(grep -a '^SKIP' "$logo_log" | head -1 | sed 's/^SKIP logo-scenario: //')
  if [[ ${LOGO_PREFLIGHT_SKIP_OK:-0} == 1 ]]; then
    printf 'SKIP logo preflight (LOGO_PREFLIGHT_SKIP_OK=1): %s\n' "$logo_why"
  else
    bad "logo preflight SKIPPED, which is not green: $logo_why (set LOGO_PREFLIGHT_SKIP_OK=1 to accept a gate that observed neither sink)"
  fi
else
  cat "$logo_log"; bad "logo preflight (exit $logo_rc)"
fi

step "scripts/dev-harness/clip-scenario.sh check-tree (D-CLIP-1)"
# An editable QtQuick TextInput subscribes to QClipboard::dataChanged, and
# on the released Qt 6.11.2 that slot reads the whole foreign offer -- 1 s
# per read, no byte limit, no deadline -- on the shell's main thread, at
# every clipboard change by any application while the form is open (the
# sixth maintainer finding, docs/QA-RESULTS.md 2026-10-11). The fix is
# `readOnly: true` on every form field, and `readOnly` is the one switch on
# that slot. This half re-measures the fact the fix rests on, on THIS
# machine, on every commit: the lead's three probes run inside a nested
# headless cage on a display of its own, a foreign producer there offers
# 25 MB of text/plain (DR-B1: a quarter of the live run's 100 MB, so the
# editable probe's transient stays under 100 MB on a machine short of
# memory; +58..+80 MB measured at 20 ms sampling, settling to +36 kept)
# with a virtual keyboard held on the seat (without one the compositor
# hands the selection to nobody and the measurement is vacuous), and the
# resident set is sampled from outside: the editable probe grows by the
# payload or more, the read-only probe and the no-field window by nothing.
# Nothing touches the user's session or clipboard; the nested display is
# read from cage's own child and refused if it names the live one. About
# 9 s.
#
# A machine without cage, wl-copy, wl-paste, wtype, python3, node or the
# qml runtime answers 77 with the reason, and so does a cage that brings up
# no display: RED here unless CLIP_PREFLIGHT_SKIP_OK=1 is set, printing the
# reason either way, for the same reason as the logo step above -- a gate
# that measured nothing has proved nothing.
clip_log=$CHECK_TMP/clip-scenario.log
"$ROOT/scripts/dev-harness/clip-scenario.sh" check-tree >"$clip_log" 2>&1; clip_rc=$?
if (( clip_rc == 0 )); then
  clip_n=$(grep -c '^PASS' "$clip_log" || true)
  if (( clip_n < CLIP_PREFLIGHT_MIN )); then cat "$clip_log"; bad "clip preflight ran $clip_n checks, expected at least $CLIP_PREFLIGHT_MIN"; else ok "clip preflight ($clip_n checks)"; fi
elif (( clip_rc == 77 )); then
  clip_why=$(grep -a '^SKIP' "$clip_log" | head -1 | sed 's/^SKIP clip-scenario: //')
  if [[ ${CLIP_PREFLIGHT_SKIP_OK:-0} == 1 ]]; then
    printf 'SKIP clip preflight (CLIP_PREFLIGHT_SKIP_OK=1): %s\n' "$clip_why"
  else
    bad "clip preflight SKIPPED, which is not green: $clip_why (set CLIP_PREFLIGHT_SKIP_OK=1 to accept a gate that observed no probe)"
  fi
else
  cat "$clip_log"; bad "clip preflight (exit $clip_rc)"
fi

step "scripts/dev-harness/open-scenario.sh check-tree (R27f, D-PERF-1)"
open_log=$CHECK_TMP/open-scenario.log
"$ROOT/scripts/dev-harness/open-scenario.sh" check-tree >"$open_log" 2>&1; open_rc=$?
if (( open_rc == 0 )); then
  open_n=$(grep -c '^PASS' "$open_log" || true)
  if (( open_n < OPEN_PREFLIGHT_MIN )); then cat "$open_log"; bad "open preflight ran $open_n checks, expected at least $OPEN_PREFLIGHT_MIN"; else ok "open preflight ($open_n checks)"; fi
elif (( open_rc == 77 )); then
  bad "open preflight SKIPPED, which is not green: $(grep -a '^SKIP' "$open_log" | head -1)"
else
  cat "$open_log"; bad "open preflight (exit $open_rc)"
fi

step "scripts/dev-harness/key-scenario.sh check-tree (D-SINK-19 R6)"
# The harness's instrument for the active source -- `hostEntry`, which
# every sources-scenario.sh check about the one-write-behind host grades
# through -- hashed the entry's playlistUrl, which D-SINK-19 takes OFF the
# entry, so it read "" on both sides of the very tree it had to grade and
# the gate could not see that (the D-SINK-19 review's harness P2). The
# function now lives in scripts/dev-harness/harness-lib.js, which shell.qml
# imports and this step drives from node with the tree's own Model.js:
# `sourceKey` first, the URL hash second, named candidates only. No
# display, no quickshell, under a second. A machine without node or
# python3 answers 77, RED here unless KEY_PREFLIGHT_SKIP_OK=1 is set, for
# the same reason as the two steps above.
key_log=$CHECK_TMP/key-scenario.log
"$ROOT/scripts/dev-harness/key-scenario.sh" check-tree >"$key_log" 2>&1; key_rc=$?
if (( key_rc == 0 )); then
  key_n=$(grep -c '^PASS' "$key_log" || true)
  if (( key_n < KEY_PREFLIGHT_MIN )); then cat "$key_log"; bad "key preflight ran $key_n checks, expected at least $KEY_PREFLIGHT_MIN"; else ok "key preflight ($key_n checks)"; fi
elif (( key_rc == 77 )); then
  key_why=$(grep -a '^SKIP' "$key_log" | head -1 | sed 's/^SKIP key-scenario: //')
  if [[ ${KEY_PREFLIGHT_SKIP_OK:-0} == 1 ]]; then
    printf 'SKIP key preflight (KEY_PREFLIGHT_SKIP_OK=1): %s\n' "$key_why"
  else
    bad "key preflight SKIPPED, which is not green: $key_why (set KEY_PREFLIGHT_SKIP_OK=1 to accept a gate that drove no instrument)"
  fi
else
  cat "$key_log"; bad "key preflight (exit $key_rc)"
fi

step "ascii check (code files)"
gate_ascii_scan

step "control-byte check (source files, .qml included)"
# M2-03 integration. A raw NUL in tests/Model.test.js and tests/Model.spec.qml
# made grep treat both as BINARY and skip them silently: `grep -c chno
# tests/Model.test.js` answered 0 for a file with 34 of them. The whole
# integration criterion for this milestone is "a grep for the stand-in markers
# returns nothing", and that proof was unsound while a tracked source file was
# invisible to grep. Escapes carry the same bytes into the string and stay
# greppable.
#
# This is NOT the ASCII check and does not overlap it: it covers .qml too
# (where rule 8 deliberately allows non-ASCII glyphs) and it looks only for C0
# controls other than tab/newline/CR, plus DEL.
gate_control_scan

step "a11y fidelity guard (scripts under tests/a11y)"
# These 32 cases landed and the gate could not see them: `unittest discover -s
# tests` does not recurse into tests/a11y because it is not a package, so the
# suite count stayed at exactly what it was before they existed. A test nobody
# runs is the same as no test, and this project has now hit that four times.
#
# PO ruling: the FIDELITY half goes in the gate, the AT-SPI half does not.
# Decision 9 kept the harness out of check.sh for two stated reasons, a
# deliberately red baseline and a first hard dependency on a live graphical
# session. Neither reaches this file: it is pure text, needs no display, no
# D-Bus and no Qt, runs in about 7 seconds and is green on shipping code. The
# guard's own proof must not be allowed to rot unnoticed.
a11y_log=$CHECK_TMP/a11y.log
if (cd "$ROOT" && python3 -m unittest discover -s tests/a11y) >"$a11y_log" 2>&1; then
  a11y_tests=$(grep -oP '^Ran \K[0-9]+' "$a11y_log" | tail -1)
  if [[ -z $a11y_tests ]]; then
    bad "a11y fidelity printed no test count at all"
  elif (( a11y_tests < A11Y_TESTS_MIN )); then
    bad "a11y fidelity ran $a11y_tests tests, expected at least $A11Y_TESTS_MIN"
  else
    ok "a11y fidelity ($a11y_tests tests)"
  fi
else
  cat "$a11y_log"; bad "a11y fidelity"
fi

step "defect ledger (every filed defect has a row on the board)"
# Defects are filed in prose by whichever lane found them, and docs/STATUS.md
# carries the table that is supposed to be the single view of what is
# outstanding. Nothing joined the two, so ids drifted off the board and the
# board looked clean -- CLAUDE.md's named pattern, two things joined by a NAME
# rather than by a call. A QA lane filed F-CHNO-4 against exactly this once
# already; 32 more ids went missing afterwards, including a P2 that had been a
# release gate. This makes the join a call.
ledger_log=$CHECK_TMP/ledger.log
if python3 "$ROOT/scripts/check-defect-ledger.py" >"$ledger_log" 2>&1; then
  ok "$(head -1 "$ledger_log")"
else
  cat "$ledger_log"; bad "defect ledger"
fi

step "board staleness (no row says open where a commit of ours says closed)"
# The ledger step above proves the board and the write-ups agree that an id
# EXISTS. It does not prove they agree about anything else, and on 2026-10-03
# five of the nine rows reading `open` were already fixed in the code
# (F-BOARD-1) -- one of them for a day after the commit whose own subject is
# "Close F-SINK-10 at the sink", three for a week after the commit that says
# "the D-SAVE-6 repair" in its own body. The gate was green throughout.
#
# This step never decides whether a defect is fixed. It refuses a tree in
# which a commit message of ours and a board row contradict each other, and
# either half can be made true. Measured over all 523 commits to 64fa114: 47
# red commits of the 486 that carry a board (9.7%), five ids ever flagged,
# four of them truly stale and one a repair in flight for four commits. A row
# whose state cell says anything more than the bare word `open` is exempt, so
# a repair that is mid-wave is recorded rather than refused. The --report mode
# adds document prose and the board's own cross-row claims, which reach the
# fifth stale row of 2026-10-03 at the cost of four more false alarms, and is
# deliberately not in the gate.
staleness_log=$CHECK_TMP/board-staleness.log
if python3 "$ROOT/scripts/check-board-staleness.py" >"$staleness_log" 2>&1; then
  ok "$(head -1 "$staleness_log")"
else
  cat "$staleness_log"; bad "board staleness"
fi

step "marketplace capability scan (developer messages stay messages)"
# The Omarchy marketplace runs a deterministic security scan over every
# submitted commit and rescans on listing updates. It parses this
# repository's shell-like files into command sequences and cannot tell a
# quoted message from an executed line. Two message strings in developer
# tooling -- one in THIS file, one in scripts/qa-player-scenarios.sh -- were
# therefore reported as capabilities this plugin does not have, and any
# capability at all moves the listing from passed to review-required.
#
# Both sites were reworded in f2d1dbf and both carry a comment saying why the
# phrasing is load-bearing. A comment is a NAME, not a call (CLAUDE.md rule
# 13), and nothing verified it: the next edit that writes an install line or
# an elevation verb into a log message would drop the listing back to manual
# review on the following scan, with nobody connecting the two. This is the
# call. It respects the real scan surface, so the docs/ prose that discusses
# these subjects on purpose stays out of it.
marketplace_log=$CHECK_TMP/marketplace.log
if python3 "$ROOT/scripts/check-marketplace-capabilities.py" \
     --root "$ROOT" --min-files "$MARKETPLACE_FILES_MIN" >"$marketplace_log" 2>&1; then
  ok "$(head -1 "$marketplace_log")"
else
  cat "$marketplace_log"; bad "marketplace capability scan"
fi

printf '\n'
step "release allowlist (what main ships is exactly what is needed)"
# main is the install artifact, exported from dev by scripts/release.py from
# an explicit allowlist. This proves the list is whole before anything is cut:
# every runtime import and manifest entry point is on it, the README names
# nothing off it, and no agent-instruction file is on it. Found the hard way:
# CLAUDE.md shipped into every user's plugin directory (marketplace #7374).
release_log=$CHECK_TMP/release.log
if python3 "$ROOT/scripts/release.py" check >"$release_log" 2>&1; then
  ok "$(head -1 "$release_log")"
else
  cat "$release_log"; bad "release allowlist"
fi

step "text format guard (every shipped Text says how it renders)"
# D-TEXT-1, found by a marketplace reviewer against shipped 2d3cee3: the
# logo-wall caption bound a provider's channel name to a Text with no
# textFormat, so Qt's AutoText default rendered the name as markup, and an
# <img src="http://..."> in a name made the shell process fetch it at
# creation, visible or not. PlainText is the only stop (measured; StyledText
# and RichText fetch too). The acceptance row for this was graded by a grep
# for StyledText|RichText, which cannot see a line nobody wrote (F-TEXT-2),
# so this is the call that replaces it: every Text block in every shipped
# .qml, found by a brace-aware scan, must declare Text.PlainText -- or
# Text.StyledText with a "// MARKUP-EXCEPTION: <reason>" comment directly
# above it, which today is the footer hint line and nothing else. The file
# list comes from the release allowlist, so a new shipped .qml is covered the
# day it ships.
textfmt_log=$CHECK_TMP/text-format.log
if python3 "$ROOT/scripts/check-text-format.py" >"$textfmt_log" 2>&1; then
  textfmt_n=$(grep -oE '^text format guard: [0-9]+ Text block' "$textfmt_log" | head -1 | grep -oE '[0-9]+')
  if [[ -z $textfmt_n ]]; then
    cat "$textfmt_log"; bad "text format guard printed no Text block count at all"
  elif (( textfmt_n < TEXT_BLOCKS_MIN )); then
    cat "$textfmt_log"; bad "text format guard checked $textfmt_n Text block(s), expected at least $TEXT_BLOCKS_MIN"
  else
    ok "text format guard ($textfmt_n Text blocks checked)"
  fi
else
  cat "$textfmt_log"; bad "text format guard"
fi

if (( fail )); then echo "check.sh: FAILED"; exit 1; fi
echo "check.sh: all green"
