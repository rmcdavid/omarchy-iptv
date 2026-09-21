// tests/fixtures/qa-gs2/verify.js -- the D-GS-2 verdict, taken from Model.js
// itself and printed as one JSON object for tests/test_fixture_gs2.py.
//
//   node verify.js <Model.js> <channels.json> <epg-now.json> <nowSec>
//
// CLAUDE.md rule 12: the row-height decision lives in Model.js and a python
// test cannot reach it, so this is the bridge. It CALLS the shipping functions
// in the order Service.qml and Guide.qml call them, with two deviations named
// so they are not mistaken for fidelity: it passes a fourth key,
// epgConfigured: true, which Guide.qml:418 does not pass (kept so the pre-fix
// predicate can be reproduced on a scratch copy), and it walks the prepared
// channels rather than filterChannels rows (the same objects; Guide.qml:2423,
// Model.js:1415). tests/a11y/check_bus.py drove node before this file did;
// this is the first bridge that takes the Model.js PATH as an argument.
//
//   Service.qml  applyChannels:  Model.parseChannels(text) -> Model.prepareChannels
//   Service.qml  applyEpgNow:    Model.parseEpgNow(text).channels      (= root.epgNow)
//   Guide.qml    rebuildGroups:  Model.scopeSurface(channels, state).axis (= root.groupAxis)
//   Guide.qml    measureEpgRows: Model.epgCoverage(channels, epgMap).carries (= root.epgCarriesRows)
//   Guide.qml    rowsHaveDetail: Model.rowsHaveDetail({ scopeIsGroup, groupsNarrow, epgCarries })
//   Guide.qml    each row:       Model.rowShowsGroup, Model.epgFields, Model.rowDetail
//
// The Model.js path is an ARGUMENT, not a fixed require, so the test can run
// the same verdict against a scratch copy carrying the pre-fix decision and
// show the fixture turns it red (rule 11). `epgConfigured: true` is passed
// alongside `epgCarries` on purpose: it is the SETTING the pre-fix predicate
// read, and the whole fixture is "the setting is on, the data is absent". The
// shipping function ignores it; the pre-fix one is decided by it.
//
// Prints identifiers and programme titles only, never a URL (rule 5).
// ASCII only (rule 8). Run by node only; QML never loads this file.
"use strict"
var fs = require("fs")
var path = require("path")

function usage(message) {
  process.stderr.write("verify.js: " + message + "\n")
  process.stderr.write("usage: node verify.js <Model.js> <channels.json> <epg-now.json> <nowSec>\n")
  process.exit(2)
}

var argv = process.argv.slice(2)
if (argv.length !== 4) usage("expected 4 arguments, got " + argv.length)
var modelPath = path.resolve(argv[0])
var channelsPath = path.resolve(argv[1])
var epgNowPath = path.resolve(argv[2])
var nowSec = Number(argv[3])
if (!isFinite(nowSec) || nowSec <= 0) usage("nowSec must be a positive number of epoch seconds")

var Model = require(modelPath)

// Service.qml applyChannels / applyEpgNow, the same two calls in the same order.
var channelsDoc = Model.parseChannels(fs.readFileSync(channelsPath, "utf8"))
var channels = channelsDoc.ok ? Model.prepareChannels(channelsDoc.channels) : []
var epgDoc = Model.parseEpgNow(fs.readFileSync(epgNowPath, "utf8"))
var epgMap = epgDoc.channels

// Guide.qml rebuildGroups / measureEpgRows / rowsHaveDetail, in All scope.
var axis = Model.scopeSurface(channels, Model.emptyState()).axis
var coverage = Model.epgCoverage(channels, epgMap)
var rowsHaveDetail = Model.rowsHaveDetail({
  scopeIsGroup: false, groupsNarrow: axis.narrows, epgCarries: coverage.carries, epgConfigured: true
})
var showGroup = Model.rowShowsGroup({ scopeIsGroup: false, groupsNarrow: axis.narrows })

// What each row's second line would print, composed the way the delegate
// composes it. The defect is these two counts read 0 filled, N blank while
// rowsHaveDetail says the line exists.
var filled = 0
var blank = 0
var sample = []
for (var i = 0; i < channels.length; i++) {
  var row = channels[i]
  var tvgId = row && row.tvgId ? String(row.tvgId) : ""
  var epg = Model.epgFields(tvgId !== "" ? epgMap[tvgId] : null, nowSec)
  var detail = Model.rowDetail({
    showGroup: showGroup, group: Model.primaryGroup(row), failedAt: "",
    nowTitle: epg.nowTitle, nextTitle: epg.nextTitle
  })
  if (detail === "") blank++; else filled++
  if (sample.length < 3) sample.push({ tvgId: tvgId, detail: detail })
}

process.stdout.write(JSON.stringify({
  channelsOk: channelsDoc.ok,
  epgOk: epgDoc.ok,
  total: channels.length,
  axis: axis,
  coverage: coverage,
  rowShowsGroup: showGroup,
  rowsHaveDetail: rowsHaveDetail,
  detailFilledRows: filled,
  detailBlankRows: blank,
  sample: sample
}) + "\n")
