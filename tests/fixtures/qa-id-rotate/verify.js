// tests/fixtures/qa-id-rotate/verify.js -- the JavaScript half of the D-ID-1
// rotation fixture (README.md in this directory).
//
// tests/test_fixture_id_rotate.py runs this through node with an argv LIST,
// never a shell string:
//
//   node verify.js <channels-v1.json> <channels-v2.json> <state-seed.json>
//
// The first two files are the helper's own channels.json after the playlist
// verb ran on list-v1.m3u and on list-v2.m3u; the third is the committed
// seed. This calls the SHIPPING Model.js (CLAUDE.md rule 12: call it, never
// re-implement it) and prints one JSON object on stdout, so the python side
// can hold the two implementations of the id rule to ONE fixture, joined by a
// call rather than by a name. It asserts nothing itself; the assertions live
// in the python test that reads this output.
//
// ASCII only (CLAUDE.md rule 8).
"use strict"
const fs = require("fs")
const Model = require("../../../Model.js")

function readJson(path) {
  return JSON.parse(fs.readFileSync(path, "utf8"))
}

if (process.argv.length !== 5) {
  process.stderr.write("usage: node verify.js <channels-v1.json> <channels-v2.json> <state-seed.json>\n")
  process.exit(2)
}

const v1 = readJson(process.argv[2]).channels
const v2 = readJson(process.argv[3]).channels
const seed = readJson(process.argv[4])
const remap = Model.channelIdRemap(v1)
const result = Model.remapStateIds(seed, remap)

process.stdout.write(JSON.stringify({
  legacyV1: Model.channelIds(v1, Model.CHANNEL_ID_SCHEME_LEGACY),
  idsV1: Model.channelIds(v1),
  legacyV2: Model.channelIds(v2, Model.CHANNEL_ID_SCHEME_LEGACY),
  idsV2: Model.channelIds(v2),
  remap: remap,
  moved: result.moved,
  favorites: result.state.favorites,
  recents: result.state.recents,
  lastPlayed: result.state.lastPlayed,
  session: result.state.session
}) + "\n")
