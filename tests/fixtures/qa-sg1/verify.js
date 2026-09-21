// tests/fixtures/qa-sg1/verify.js -- run the guide's SEARCH PATH over a
// channels.json from the terminal and print what the header and footer
// would be told, for D-SG-1 (docs/STATUS.md "## Defects", ruling SG1).
//
// This is the python-drives-node seam: tests/test_fixture_sg1.py runs it with
// an argv LIST (never a shell string) and reads the JSON it prints. It calls
// the shipping functions in the order Service.qml and Guide.qml call them,
// never a re-implementation (CLAUDE.md rule 12):
//
//   Service.qml applyChannels   Model.parseChannels -> Model.prepareChannels
//                               -> Model.buildChnoIndex
//   Guide.qml rebuildGroups     Model.scopeSurface, then the group NAMES the
//                               way the guide collects them (the sole group off
//                               the axis first, then every group entry)
//   Guide.qml candidates        Model.channelsForScope(channels, effectiveScope)
//   Guide.qml rebuildDisplay    Model.filterChannels(candidates, query,
//                               Model.MAX_ROWS_DEFAULT, favorites, chnoIndex)
//   Guide.qml empty state       Model.groupWordHint(query, groupNames), only
//                               when nothing matched
//
// Usage:
//   node verify.js <channels.json> <post-Model.js> <pre-Model.js | -> <query>...
//
// <post-Model.js> is the shipping Model.js. <pre-Model.js> is a scratch copy
// the test mutates back to the pre-fix ranking (tier 3 accepting a substring
// instead of whole words); pass "-" to skip it. Both are loaded with require()
// from the paths given, so the same script measures either logic.
//
// Output, one JSON object on stdout:
//   { "channels": N, "groupNames": [...], "limit": 200,
//     "results": { "<query>": { "pre": n | null, "post": n,
//                               "preTruncated": bool | null, "postTruncated": bool,
//                               "postRows": n, "hint": "<group or empty>" } } }
//
// `post` and `pre` are filterChannels().total: the number the header prints as
// "N matches". `postTruncated` is what makes the footer say "First 200 of N -
// keep typing". `hint` is the group name the empty state would name, "" when
// rows were produced or nothing is worth naming. The strings themselves live
// in Guide.qml copy and can only be checked on a screen.
//
// ASCII only (CLAUDE.md rule 8). Node stdlib only.
"use strict"

var fs = require("fs")
var path = require("path")

function die(message) {
  process.stderr.write("verify.js: " + message + "\n")
  process.exit(2)
}

function loadModel(file) {
  var resolved = path.resolve(file)
  var Model = require(resolved)
  var needed = ["parseChannels", "prepareChannels", "buildChnoIndex", "emptyState", "scopeSurface",
                "channelsForScope", "effectiveScope", "filterChannels", "groupWordHint"]
  for (var i = 0; i < needed.length; i++) {
    if (typeof Model[needed[i]] !== "function") die(resolved + " does not export " + needed[i])
  }
  if (typeof Model.MAX_ROWS_DEFAULT !== "number" || typeof Model.SCOPE_ALL !== "string") {
    die(resolved + " does not export MAX_ROWS_DEFAULT and SCOPE_ALL")
  }
  return Model
}

// The load path, as Service.qml applyChannels runs it.
function load(Model, text) {
  var parsed = Model.parseChannels(text)
  if (!parsed.ok) die("channels.json did not parse: " + parsed.error)
  var channels = Model.prepareChannels(parsed.channels)
  var state = Model.emptyState()
  // Guide.qml rebuildGroups: the sole group comes off the axis because a
  // one-group list publishes no group entries, and that is precisely the list
  // D-SG-1 bites on.
  var surface = Model.scopeSurface(channels, state)
  var groupNames = []
  if (surface.axis.soleGroup !== "") groupNames.push(surface.axis.soleGroup)
  for (var i = 0; i < surface.entries.length; i++) {
    if (surface.entries[i].kind === "group") groupNames.push(surface.entries[i].label)
  }
  return {
    channels: channels,
    state: state,
    chnoIndex: Model.buildChnoIndex(channels),
    groupNames: groupNames
  }
}

// One keystroke's worth of the guide: Guide.qml rebuildDisplay, from the All
// scope, with no favorites.
function search(Model, loaded, query) {
  var scope = Model.effectiveScope(Model.SCOPE_ALL, query)
  var candidates = Model.channelsForScope(loaded.channels, scope, loaded.state)
  var result = Model.filterChannels(candidates, query, Model.MAX_ROWS_DEFAULT, loaded.state.favorites, loaded.chnoIndex)
  return {
    total: result.total,
    rows: result.rows.length,
    truncated: result.truncated,
    hint: result.total === 0 ? Model.groupWordHint(query, loaded.groupNames) : ""
  }
}

function main(argv) {
  if (argv.length < 4) die("usage: node verify.js <channels.json> <post-Model.js> <pre-Model.js|-> <query>...")
  var cacheFile = argv[0]
  var postFile = argv[1]
  var preFile = argv[2]
  var queries = argv.slice(3)
  var text
  try {
    text = fs.readFileSync(cacheFile, "utf8")
  } catch (e) {
    die("cannot read " + cacheFile + ": " + e.message)
  }
  var Post = loadModel(postFile)
  var post = load(Post, text)
  var Pre = null
  var pre = null
  if (preFile !== "-") {
    Pre = loadModel(preFile)
    if (Pre === Post) die("pre and post resolve to the same module; pass two different files")
    pre = load(Pre, text)
    if (pre.channels.length !== post.channels.length) die("pre and post loaded different channel counts")
  }
  var results = {}
  for (var i = 0; i < queries.length; i++) {
    var q = queries[i]
    var after = search(Post, post, q)
    var entry = {
      pre: null,
      preTruncated: null,
      post: after.total,
      postRows: after.rows,
      postTruncated: after.truncated,
      hint: after.hint
    }
    if (Pre) {
      var before = search(Pre, pre, q)
      entry.pre = before.total
      entry.preTruncated = before.truncated
    }
    results[q] = entry
  }
  process.stdout.write(JSON.stringify({
    channels: post.channels.length,
    groupNames: post.groupNames,
    limit: Post.MAX_ROWS_DEFAULT,
    results: results
  }) + "\n")
}

main(process.argv.slice(2))
