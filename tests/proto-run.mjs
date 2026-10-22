// tests/proto-run.mjs -- D-SG-3 (ruling R30f). Runs tests/proto-paths.mjs
// over the model named on the command line (default: this tree's Model.mjs),
// then the SERVICE's apply path -- the Service.qml beside that model, under
// tests/service-harness.js -- over the same names, in a process of its own,
// and prints one JSON line. A child process because a prototype pollution,
// which is what this looks for, would otherwise leak into every later check
// of the suite that found it.
// Usage: node tests/proto-run.mjs [path/to/Model.mjs]
import fs from "node:fs"
import path from "node:path"
import { createRequire } from "node:module"
import { pathToFileURL, fileURLToPath } from "node:url"
import { runProtoPaths, PROTO_KEYS } from "./proto-paths.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const modelPath = process.argv[2] ? path.resolve(process.argv[2]) : path.join(here, "../Model.mjs")
const Model = await import(pathToFileURL(modelPath).href)
const result = runProtoPaths(Model)

// The service: a channels.json whose groups, names and tvg-ids are the same
// names, applied the way the FileView applies it, then the lookups the service
// makes with ids that come from state.json and from IPC `play`.
const H = createRequire(import.meta.url)("./service-harness.js")
const svcText = fs.readFileSync(path.join(path.dirname(modelPath), "Service.qml"), "utf8")
const h = H.bootService(svcText, Model, { entry: { sourceKey: "", showLogos: false }, stateText: "", host: "lag" })
const service = { errors: [] }
try {
  service.indexBefore = PROTO_KEYS.map(k => h.root.channelIndex[k] === undefined)
  service.failedBefore = PROTO_KEYS.map(k => h.root.failedAt[k] === undefined)
  const channels = [{ name: "News One", group: "News", tvgId: "news1", url: "http://cdn.example.test/n.ts" }]
    .concat(PROTO_KEYS.map((k, i) => ({ name: k, group: k, tvgId: k, url: "http://cdn.example.test/" + i + ".ts" })))
  h.root.applyChannels(JSON.stringify({ version: 1, generatedAt: 1, channels }), "/cache/sources/aaaaaaaa")
  service.indexAfter = PROTO_KEYS.map(k => h.root.channelIndex[k] === undefined)
  service.indexIds = PROTO_KEYS.map(k => h.root.channelIndex["t:" + k] ? h.root.channelIndex["t:" + k].name : null)
  service.groups = Model.groupChannels(h.root.channels).map(g => g.name)
  service.withKey = Object.keys(h.root.withKey(h.root.sourceErrors, "__proto__", "x"))
  service.compileErrors = h.compileErrors
} catch (e) {
  service.errors.push(String(e && e.message || e))
}
const after = { names: Object.getOwnPropertyNames(Object.prototype).sort(), enumerable: [] }
for (const k in {}) after.enumerable.push(k)
service.prototypeUnchanged = JSON.stringify(after.names) === JSON.stringify(result.prototypeBefore.names) && after.enumerable.length === 0
result.service = service
console.log(JSON.stringify(result))
