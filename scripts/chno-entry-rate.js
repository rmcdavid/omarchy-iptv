#!/usr/bin/env node
// scripts/chno-entry-rate.js -- the deterministic reproduction of D-CHNO-2
// (the silent mistune), and the measurement that decides whether a fix for it
// pays for itself.
//
// WHY IT EXISTS. The live pass measured two numbers on the machine of record
// and the fix has to move one without destroying the other:
//
//   * 28.4% of ABSENT five-digit numbers (2,690 of 9,484 in 10000-19999)
//     auto-committed on a prefix that does exist, leaving the user on an
//     unrelated channel with no error anywhere (QA-RESULTS C7, D-CHNO-2);
//   * 93.1% of the numbers that DO exist (2,739 of 2,942 distinct) commit the
//     instant the last digit lands, with no wait at all (QA-RESULTS C4).
//
// Both are properties of the entry state machine alone -- no compositor, no
// font, no keyboard -- so both are reproducible here, on the same fixture the
// live pass used:
//
//   scripts/gen-playlist.py --profile realistic --numbering blocks \
//     --channels 3000 --groups 120 --seed 7 --epg-ids 0.6 --out $S/gen-num.m3u
//   sha256 de376228478d76d799e64697653dc5f2989b7949fbcb8463b767ff3e040f7ca2
//   bin/omarchy-iptv playlist --url $S/gen-num.m3u --cache-dir $S/cache
//   node scripts/chno-entry-rate.js $S/cache/channels.json
//
// WHAT IT DRIVES. `Model.numberKeyStep` and `Model.numberCommitStep` -- the
// same two functions Guide.qml calls per keystroke and per commit, not a copy
// of them (CLAUDE.md rule 12). The only thing this file adds is the user:
// digits arrive faster than the timeout, and the timeout is the last event.
//
// It prints one line per metric and a machine-readable JSON tail, and it
// exits non-zero if the sample is empty -- a rate over nothing is not
// evidence.
"use strict"

const fs = require("fs")
const path = require("path")
const Model = require(path.join(__dirname, "..", "Model.js"))

function usage(code) {
  process.stdout.write("usage: chno-entry-rate.js <channels.json> [--range LOW-HIGH] [--cursor ROW] [--quiet]\n")
  process.exit(code)
}

const args = process.argv.slice(2)
let file = ""
let low = 10000
let high = 19999
let startCursor = 0
let quiet = false
for (let i = 0; i < args.length; i++) {
  const a = args[i]
  if (a === "-h" || a === "--help") usage(0)
  else if (a === "--quiet") quiet = true
  else if (a === "--range") {
    const m = /^([0-9]+)-([0-9]+)$/.exec(String(args[++i] || ""))
    if (!m) usage(2)
    low = Number(m[1]); high = Number(m[2])
  } else if (a === "--cursor") startCursor = Math.max(0, Math.floor(Number(args[++i])))
  else if (a.charAt(0) === "-") usage(2)
  else file = a
}
if (file === "") usage(2)

const parsed = Model.parseChannels(fs.readFileSync(file, "utf8"))
const rows = Model.prepareChannels(parsed.channels)
const index = Model.buildChnoIndex(rows)
if (!index.hasNumbers) { process.stderr.write("chno-entry-rate: the fixture has no channel numbers at all\n"); process.exit(1) }
const idAt = rows.map(function (r) { return Model.channelId(r) })
const rowOfId = {}
for (let i = 0; i < idAt.length; i++) if (!Object.prototype.hasOwnProperty.call(rowOfId, idAt[i])) rowOfId[idAt[i]] = i

// One typing session: the digits of `text` arrive inside the timeout window
// (so they are one number by the rule the timeout defines), and the session
// ends with the timeout firing. Every decision below is a Model call; the
// cursor, the timer and the transient are the guide's side of it and are
// modelled as the three variables they are.
function type(text, cursor) {
  const start = cursor
  let entry = Model.numberEntry()
  let resolution = Model.resolveChno(null, "", -1)
  const said = []
  let commits = 0
  let earlyCommit = false
  let instant = false

  function land(hit) {
    if (!hit || hit.kind === "none") return
    const at = rowOfId[Model.chnoIdAt(index, hit.channelIndex)]
    if (at !== undefined) cursor = at
  }
  function commit(reason) {
    const name = rows[cursor] ? String(rows[cursor].name || "") : ""
    const done = Model.numberCommitStep(entry, resolution, name, { play: false, reason: reason })
    said.push(done.plan.status)
    if (done.plan.restore) cursor = start
    entry = done.entry
    resolution = Model.resolveChno(null, "", -1)
    commits++
  }

  for (let i = 0; i < text.length; i++) {
    const step = Model.numberKeyStep(entry, index, text.charAt(i), { cursorId: idAt[cursor], cursorIndex: cursor, scopeId: "all", query: "" })
    if (!step.changed) continue
    entry = step.entry
    resolution = step.resolution
    land(step.resolution)
    if (step.commit) {
      // The auto-commit: it fired without the user asking, so whether it
      // fired BEFORE the number was finished is the whole of D-CHNO-2.
      if (i < text.length - 1) earlyCommit = true
      else instant = true
      const name = rows[cursor] ? String(rows[cursor].name || "") : ""
      said.push(Model.chnoStatus(step.commit.kind, step.commit.label, name, step.commit.matches, step.commit.ordinal, true))
      if (step.commit.restore) cursor = start
      resolution = Model.resolveChno(null, "", -1)
      commits++
    }
  }
  if (entry.active === true) commit("timeout")   // the timer, the last event

  const toldNo = said.some(function (s) { return s.indexOf("No channel ") === 0 })
  return {
    cursor: cursor,
    moved: cursor !== start,
    instant: instant,
    earlyCommit: earlyCommit,
    toldNo: toldNo,
    toldNoExactly: said.indexOf("No channel " + text) !== -1,
    // The defect, in one predicate: the user asked for a number that does not
    // exist, ended up somewhere else, and was never told.
    silent: cursor !== start && !toldNo,
    said: said,
    commits: commits
  }
}

// ---- sample 1: absent numbers (D-CHNO-2)
const absent = []
for (let n = low; n <= high; n++) if (!Object.prototype.hasOwnProperty.call(index.byKey, String(n))) absent.push(String(n))
// ---- sample 2: the numbers that exist (the instant path, QA-RESULTS C4)
const present = Object.keys(index.byKey)

if (absent.length === 0 || present.length === 0) {
  process.stderr.write("chno-entry-rate: empty sample; a rate over nothing is not evidence\n")
  process.exit(1)
}

let silent = 0, early = 0, said = 0, moved = 0
const examples = []
for (const n of absent) {
  const r = type(n, startCursor)
  if (r.silent) { silent++; if (examples.length < 5) examples.push({ typed: n, landedOn: rows[r.cursor] ? rows[r.cursor].chnoLabel : "", said: r.said }) }
  if (r.earlyCommit) early++
  if (r.toldNoExactly) said++
  if (r.moved) moved++
}
let instant = 0
for (const n of present) if (type(n, startCursor).instant) instant++

const pct = function (a, b) { return (100 * a / b).toFixed(1) + "%" }
const report = {
  fixture: path.basename(file),
  channels: rows.length,
  numbered: index.count,
  duplicates: index.duplicates,
  maxLabelLen: index.maxLabelLen,
  absentSample: absent.length,
  silentMistunes: silent,
  silentRate: pct(silent, absent.length),
  autoCommittedEarly: early,
  earlyRate: pct(early, absent.length),
  toldNoChannel: said,
  toldRate: pct(said, absent.length),
  movedAtAll: moved,
  distinctNumbers: present.length,
  instantCommits: instant,
  instantRate: pct(instant, present.length)
}
if (!quiet) {
  process.stdout.write("fixture " + report.fixture + ": " + rows.length + " channels, " + index.count
    + " numbered, " + index.duplicates + " duplicates, maxLabelLen " + index.maxLabelLen + "\n")
  process.stdout.write("absent numbers " + low + "-" + high + ": " + absent.length + "\n")
  process.stdout.write("  silent mistunes (landed elsewhere, never told): " + silent + " (" + report.silentRate + ")\n")
  process.stdout.write("  auto-committed before the number was finished:  " + early + " (" + report.earlyRate + ")\n")
  process.stdout.write("  told 'No channel <what was typed>':             " + said + " (" + report.toldRate + ")\n")
  process.stdout.write("instant path: " + instant + " of " + present.length + " distinct numbers commit on the last digit ("
    + report.instantRate + ")\n")
  for (const e of examples) process.stdout.write("  e.g. typed " + e.typed + " -> landed on " + e.landedOn + ", said: " + JSON.stringify(e.said) + "\n")
}
process.stdout.write(JSON.stringify(report) + "\n")
