#!/usr/bin/env node
// scripts/split-model.mjs -- the model as ES modules, cut by domain (D-REL-5).
//
// WHY. The marketplace security baseline refuses any non-executable file over
// 512 KiB (securityFileByteLimit in omacom/omarchy-plugin-marketplace,
// scripts/security-baseline-limits.mjs), and the one-file Model.js reached
// 534,599 bytes at 0.13.5. The lead's ruling (D-REL-5, E1-E6): the code moves
// into parts under model/, Model.mjs re-exports exactly the old
// module.exports, and THIS script is the only thing that ever cuts a
// monolith -- deterministic, re-runnable over a later Model.js (the D-SINK-19
// chain's) with no hand edit to its output, and the judge of its own work.
//
// MODES (exactly one):
//   --write   cut the monolith (--input FILE, or --from-git REF for the
//             Model.js at a commit) into <root>/Model.mjs and <root>/model/,
//             then run every --verify check on what it wrote. Refuses to
//             write a split that breaks init locality (below).
//   --verify  the same cut in memory, compared with the tree on disk: each
//             file byte-identical to the cut, every top-level chunk of the
//             input byte-identical in exactly ONE part (found on disk, not
//             trusted from the cut), nothing else in a part but the
//             generated lines, the namespace of Model.mjs equal, name by
//             name, to require() of the input, and every line the cut drops
//             (the input's header, and the comments inside its export guard)
//             recorded in section 9 of ARCHITECTURE.md (or --record FILE).
//   --check   no monolith: the tree as it stands. Every part's generated
//             import/export lines, and the aggregator's generated header,
//             are what --relink would write, the static
//             rules below hold, every part loads, and Model.mjs exports
//             exactly the names its own export lines list. The gate runs it.
//   --relink  rewrite the generated lines of the parts and the aggregator
//             from the parts' code (after an edit adds a call across parts),
//             then --check.
//
// THE STATIC RULES, checked in every mode:
//   init locality  A top-level initializer never reads a declaration of
//                  ANOTHER part, directly or through a same-part function it
//                  names. Measured on 2026-10-12 (node 26, qmltestrunner and
//                  Quickshell in a nested headless cage, Qt 6.11.2): a cyclic
//                  import graph between .mjs parts links and runs, and an
//                  initializer that reads a binding of another part in the
//                  cycle reads `undefined` SILENTLY. So cycles are allowed
//                  and this rule is what makes them safe; cross-part
//                  references live only inside function bodies.
//   no assignment  No code assigns to, increments, or directly mutates a
//                  top-level binding outside its own initializer (an
//                  imported binding is read-only in a module, and one shared
//                  module instance replaces the per-component copies a
//                  classic QML script had, which is only equivalent while
//                  nothing writes to the shared state). Locals that shadow a
//                  top-level name are skipped, so this is an over-approximate
//                  guard and the runtime is the backstop: a write to an
//                  import throws in strict mode.
//   declared first A `var` is declared above every chunk of its own part whose
//                  code names it. The monolith never had to care: a classic
//                  script's `var` is hoisted and V4 says nothing. An ES module
//                  is compiled differently, and Quickshell logged
//                  `qt.qml.usedbeforedeclared` with the module's file:// URL on
//                  every load for each function that used a later `var` of
//                  its own part (measured 2026-10-12, PLACE_TTL_SEC and
//                  ZAP_MAX_SKIP; the rewind scenario's log sweep went red on
//                  the URL). Code is never reordered here, so the remedy is in
//                  the manifest: put the `var` in another part, whose binding
//                  is then an import, declared at the top.
//   imports        A part imports every top-level name of another part that
//                  its CODE names as a whole word -- comments and the
//                  contents of string, template and regex literals are not
//                  read (an over-approximation still: an unused import is
//                  harmless, a missing one is a ReferenceError on the first
//                  call). Until F-GATE-8 (2026-10-22) the raw text was read,
//                  so a comment that named another part's export created a
//                  cross-part import the relinker kept regenerating.
//
// The manifest (scripts/model-parts.json) assigns declarations to parts by
// NAME. A declaration it does not name goes to the part of the nearest
// preceding named declaration and is REPORTED; a name it lists that the input
// does not declare is reported too. Neither stops the cut.
// F-GATE-10: once the tree exists, `parts[].names` is a GENERATED record of
// it -- what each part declares at its top level, in declaration order,
// private names included. --relink rewrites the lists from the parts and
// --check reds on any drift, so the manifest's own `about` is a claim the
// gate proves. Until 2026-10-24 only the cut modes read the lists, and the
// tree had drifted 43 declarations past them with --check green.
//
// Node stdlib only. ASCII only (CLAUDE.md rule 8). Not shipped.

import fs from "node:fs"
import path from "node:path"
import os from "node:os"
import vm from "node:vm"
import { execFileSync } from "node:child_process"
import { createRequire } from "node:module"
import { pathToFileURL, fileURLToPath } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const AGGREGATOR = "Model.mjs"
const PART_DIR = "model"
// The generated lines SHIP, so they name the script the way a shipped comment
// names any dev-branch file: by name, never by a path that does not exist in
// an install (D-REL-2; release.py check refuses `scripts/...` in a shipped
// source).
const GENERATED_MARK = "// Generated by split-model.mjs on the dev branch (D-REL-5)"
const GENERATED_LINE = GENERATED_MARK + ": the model's public names, each from the part under model/ that declares it."
// The aggregator's header is WRITTEN here, not carried over from the
// monolith: the one-file model's header said "No ES module syntax" and
// `import "Model.js" as Model`, which stopped being true the day this file
// existed (D-REL-5 round 2, R4). The old header and the comment lines that
// lived inside its export guard are recorded in ARCHITECTURE.md section 9,
// and --write and --verify go red on any of them that is not (recordProblems).
// Shipped, so it names no path an install lacks (D-REL-2) and no model file
// that does not exist.
const AGG_HEADER = [
  "// Model.mjs -- the model of io.github.rmcdavid.iptv: the plugin's pure logic.",
  "// GENERATED by split-model.mjs on the dev branch (D-REL-5). Do not edit it by",
  "// hand: --check refuses an edit here and --relink writes it back.",
  "//",
  "// What it is. An ES module that re-exports every public name of the model",
  "// from the part under model/ that declares it. The code lives in the parts,",
  "// one domain each; this file holds this header and the export lines below,",
  "// nothing else. QML imports it AS A MODULE, `import \"Model.mjs\" as Model`,",
  "// and every `Model.<name>` resolves through these lines; node loads it with",
  "// `require(\"./Model.mjs\")` or `import`. One instance is shared by every",
  "// component that imports it, so no code in the model writes to its own state.",
  "//",
  "// How it is made, by split-model.mjs on the dev branch (scripts directory):",
  "//   --write --from-git REF    cut the one-file model at commit REF into this",
  "//                             file and the parts, then verify what it wrote",
  "//   --verify --from-git REF   prove the files on disk are that cut, chunk by",
  "//                             chunk and name by name",
  "//   --relink                  rewrite the generated import and export lines",
  "//                             after an edit inside a part",
  "//   --check                   the gate's check of the tree as it stands",
  "// The model's coding rules, and the header the one-file model carried, are",
  "// in ARCHITECTURE.md (dev branch), section 9.",
  "",
].join("\n") + "\n"
// Where the dropped lines are recorded: the `## 9.` section of this file.
const RECORD_FILE = path.join("docs", "ARCHITECTURE.md")
const RECORD_SECTION = /^## 9\. /
const NAME_RE = /^[A-Za-z_$][\w$]*$/
const PART_NAME_RE = /^[a-z][a-z0-9-]*$/
const WRAP = 78

class Refusal extends Error {}
function refuse(msg) { throw new Refusal(msg) }

// ---------------------------------------------------------------- lexer
// Blank out comments and the CONTENTS of string, template and regex literals,
// keeping every offset, newline and delimiter, so what remains still parses
// and a whole-word search over it sees code only. The blanked text of every
// declaration is compiled again (selfCheckStrip), so a division read as a
// regex, or the reverse, is caught here rather than trusted.
const REGEX_AFTER_WORDS = new Set(["return", "typeof", "instanceof", "in", "of", "new", "delete",
  "void", "throw", "case", "do", "else", "yield", "await"])

function stripCode(src) {
  const out = src.split("")
  const n = src.length
  let i = 0
  let prev = ""        // last significant token: "id:<word>", "num", or the punctuator
  const blank = (a, b) => { for (let k = a; k < b; k++) if (out[k] !== "\n") out[k] = " " }
  const regexAllowed = () => {
    if (prev === "") return true
    if (prev === "num") return false
    if (prev.startsWith("id:")) return REGEX_AFTER_WORDS.has(prev.slice(3))
    return !(prev === ")" || prev === "]")
  }
  function scanTemplate() {   // at the opening backtick; leaves i after the closing one
    let litFrom = i + 1
    i++
    while (i < n) {
      const c = src[i]
      if (c === "\\") { i += 2; continue }
      if (c === "`") { blank(litFrom, i); i++; return }
      if (c === "$" && src[i + 1] === "{") {
        blank(litFrom, i)
        i += 2
        let depth = 0
        while (i < n) {
          const ch = src[i]
          if (ch === "}" && depth === 0) break
          if (ch === "{") depth++
          else if (ch === "}") depth--
          step()
        }
        if (i >= n) break
        i++
        litFrom = i
        continue
      }
      i++
    }
    refuse("unterminated template literal")
  }
  function step() {
    const c = src[i], d = src[i + 1]
    if (c === "/" && d === "/") {
      let j = src.indexOf("\n", i); if (j < 0) j = n
      blank(i, j); i = j; return
    }
    if (c === "/" && d === "*") {
      let j = src.indexOf("*/", i + 2); j = j < 0 ? n : j + 2
      blank(i, j); i = j; return
    }
    if (c === "\"" || c === "'") {
      let j = i + 1
      while (j < n && src[j] !== c) { if (src[j] === "\\") j++; if (src[j] === "\n") refuse("newline in a string literal at offset " + i); j++ }
      if (j >= n) refuse("unterminated string literal at offset " + i)
      blank(i + 1, j); i = j + 1; prev = "str"; return
    }
    if (c === "`") { scanTemplate(); prev = "str"; return }
    if (c === "/" && regexAllowed()) {
      let j = i + 1, inClass = false
      while (j < n) {
        const e = src[j]
        if (e === "\n") refuse("newline in a regex literal at offset " + i)
        if (e === "\\") { j += 2; continue }
        if (inClass) { if (e === "]") inClass = false }
        else if (e === "[") inClass = true
        else if (e === "/") break
        j++
      }
      if (j >= n) refuse("unterminated regex literal at offset " + i)
      blank(i + 1, j)
      j++
      while (j < n && /[a-z]/.test(src[j])) j++
      i = j; prev = "num"; return   // a regex literal ends an operand, like a number
    }
    if (/[A-Za-z_$]/.test(c)) {
      let j = i + 1; while (j < n && /[\w$]/.test(src[j])) j++
      prev = "id:" + src.slice(i, j); i = j; return
    }
    if (/[0-9]/.test(c) || (c === "." && /[0-9]/.test(d || ""))) {
      let j = i + 1; while (j < n && /[\w$.]/.test(src[j])) j++
      prev = "num"; i = j; return
    }
    if (/\s/.test(c)) { i++; return }
    prev = c; i++
  }
  while (i < n) step()
  return out.join("")
}

// Identifiers in blanked code that are not property names after a dot.
function codeWords(stripped) {
  const words = new Set()
  const re = /[A-Za-z_$][\w$]*/g
  let m
  while ((m = re.exec(stripped)) !== null) {
    let k = m.index - 1
    while (k >= 0 && (stripped[k] === " " || stripped[k] === "\t" || stripped[k] === "\n")) k--
    if (k >= 0 && stripped[k] === "." && stripped[k - 1] !== ".") continue
    words.add(m[0])
  }
  return words
}

function wholeWord(name) {
  return new RegExp("(?<![\\w$])" + name.replace(/\$/g, "\\$") + "(?![\\w$])")
}

// ---------------------------------------------------------------- parsing
function lines(text) { return text.match(/[^\n]*\n|[^\n]+$/g) || [] }
const isBlank = (l) => /^\s*$/.test(l)
const isComment = (l) => l.startsWith("//")
const DECL_RE = /^(var|function) ([A-Za-z_$][\w$]*)/

// Cut a body of top-level code into chunks: each is the text since the end of
// the previous declaration (blank lines, comments) plus the declaration. A
// declaration runs from its `var` / `function` line to the last line before
// the next top-level start that is not a blank or column-0 comment line; those
// trailing lines lead the NEXT chunk, so a section comment travels with the
// code under it. Every line at column 0 must be a declaration start, a
// comment, a blank or a closer of the declaration above it.
function cutChunks(bodyLines, firstLineNo, where) {
  const starts = []
  bodyLines.forEach((l, k) => { if (DECL_RE.test(l)) starts.push(k) })
  const chunks = []
  for (let k = 0; k < (starts.length ? starts[0] : bodyLines.length); k++) {
    if (!isBlank(bodyLines[k]) && !isComment(bodyLines[k]))
      refuse(where + ":" + (firstLineNo + k) + ": top-level code that is not a declaration: " + JSON.stringify(bodyLines[k].slice(0, 60)))
  }
  let leadFrom = 0
  for (let s = 0; s < starts.length; s++) {
    const from = starts[s]
    const to = s + 1 < starts.length ? starts[s + 1] : bodyLines.length
    let end = to
    while (end > from + 1 && (isBlank(bodyLines[end - 1]) || isComment(bodyLines[end - 1]))) end--
    for (let k = from + 1; k < end; k++) {
      const l = bodyLines[k]
      if (!isBlank(l) && !/^\s/.test(l) && !isComment(l) && !/^[}\])]/.test(l))
        refuse(where + ":" + (firstLineNo + k) + ": a column-0 line inside a declaration: " + JSON.stringify(l.slice(0, 60)))
    }
    const m = DECL_RE.exec(bodyLines[from])
    const decl = bodyLines.slice(from, end).join("")
    chunks.push({
      kind: m[1], name: m[2],
      lead: bodyLines.slice(leadFrom, from).join(""),
      decl,
      text: bodyLines.slice(leadFrom, end).join(""),
      line: firstLineNo + from,
      where,
    })
    leadFrom = end
  }
  const trailing = bodyLines.slice(leadFrom).join("")
  return { chunks, trailing }
}

function compileCheck(c) {
  for (const prefix of ["", "\"use strict\";\n"]) {
    try { new vm.Script(prefix + c.decl, { filename: c.where }) }
    catch (e) { refuse(c.where + ":" + c.line + ": `" + c.name + "` does not compile on its own" + (prefix ? " in strict mode" : "") + ": " + e.message) }
  }
  c.stripped = stripCode(c.decl)
  try { new vm.Script(c.stripped, { filename: c.where }) }
  catch (e) { refuse(c.where + ":" + c.line + ": the lexer misread `" + c.name + "` (its blanked text no longer compiles: " + e.message + ")") }
}

// The monolith: header (the leading comment block through the first blank
// line), declarations, then the CommonJS export guard and nothing after it.
function parseMonolith(text, where) {
  if (/[^\x00-\x7f]/.test(text)) refuse(where + ": non-ASCII bytes (CLAUDE.md rule 8)")
  if (!text.endsWith("\n")) refuse(where + ": does not end with a newline")
  const ls = lines(text)
  let h = 0
  while (h < ls.length && isComment(ls[h])) h++
  if (h < ls.length && isBlank(ls[h])) h++
  else h = 0
  const g = ls.findIndex((l) => l.startsWith("if (typeof module !== \"undefined\")"))
  if (g < 0) refuse(where + ": no `if (typeof module !== \"undefined\")` export guard")
  const guard = ls.slice(g)
  const exportsList = []
  const guardComments = []
  guard.forEach((l, k) => {
    if (k === 0 || /^  module\.exports = \{\n$/.test(l) || /^  \}\n$/.test(l) || /^\}\n$/.test(l)) return
    if (/^\s+\/\//.test(l)) { guardComments.push(l.trim()); return }   // replaced with the guard, and reported
    const m = /^    ([A-Za-z_$][\w$]*): ([A-Za-z_$][\w$]*),?\n$/.exec(l)
    if (!m) refuse(where + ":" + (g + k + 1) + ": an export guard line that is not `name: name`: " + JSON.stringify(l))
    if (m[1] !== m[2]) refuse(where + ":" + (g + k + 1) + ": export `" + m[1] + "` is bound to `" + m[2] + "`, not to its own name")
    exportsList.push(m[1])
  })
  const { chunks, trailing } = cutChunks(ls.slice(h, g), h + 1, where)
  if (!isBlank(trailing) && trailing !== "")
    refuse(where + ": text between the last declaration and the export guard that is not blank")
  return { header: ls.slice(0, h).join(""), chunks, between: trailing, guard: guard.join(""), exportsList, guardComments, text }
}

// ---------------------------------------------------------------- the model
function indexModel(chunks, exportsList) {
  const byName = new Map()
  for (const c of chunks) {
    if (byName.has(c.name)) refuse(c.where + ":" + c.line + ": `" + c.name + "` is declared twice (also " + byName.get(c.name).where + ":" + byName.get(c.name).line + ")")
    byName.set(c.name, c)
  }
  const seen = new Set()
  for (const e of exportsList) {
    if (seen.has(e)) refuse("`" + e + "` is exported twice")
    seen.add(e)
    if (!byName.has(e)) refuse("`" + e + "` is exported but not declared at the top level")
  }
  for (const c of chunks) compileCheck(c)
  return byName
}

function assignParts(chunks, manifest) {
  const owner = new Map()
  manifest.parts.forEach((p) => p.names.forEach((n) => {
    if (owner.has(n)) refuse("scripts/model-parts.json names `" + n + "` in both " + owner.get(n) + " and " + p.name)
    owner.set(n, p.name)
  }))
  const unplaced = []
  let last = null
  for (const c of chunks) {
    if (owner.has(c.name)) { c.part = owner.get(c.name); last = c.part; continue }
    unplaced.push(c)
  }
  // nearest preceding named declaration; before the first, the first named one after it
  for (let k = 0; k < chunks.length; k++) {
    const c = chunks[k]
    if (c.part) continue
    let j = k - 1
    while (j >= 0 && !owner.has(chunks[j].name)) j--
    if (j < 0) { j = k + 1; while (j < chunks.length && !owner.has(chunks[j].name)) j++ }
    if (j >= chunks.length) refuse("the manifest names no declaration of the input at all")
    c.part = owner.get(chunks[j].name)
  }
  const declared = new Set(chunks.map((c) => c.name))
  const absent = [...owner.keys()].filter((n) => !declared.has(n))
  return { unplaced: unplaced.map((c) => ({ name: c.name, part: c.part, line: c.line })), absent }
}

// Locals a chunk declares (vars, params, inner functions, catch bindings),
// over-approximated, so a shadowing local is never read as a top-level write.
function localNames(stripped) {
  const s = new Set()
  let m
  const re1 = /\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)/g
  while ((m = re1.exec(stripped)) !== null) s.add(m[1])
  const re2 = /,\s*([A-Za-z_$][\w$]*)\s*=(?!=)/g
  while ((m = re2.exec(stripped)) !== null) s.add(m[1])
  const re3 = /\bfunction\b\s*([A-Za-z_$][\w$]*)?\s*\(([^)]*)\)/g
  while ((m = re3.exec(stripped)) !== null) {
    if (m[1]) s.add(m[1])
    m[2].split(",").map((x) => x.trim()).filter(Boolean).forEach((x) => s.add(x))
  }
  const re4 = /\bcatch\s*\(\s*([A-Za-z_$][\w$]*)/g
  while ((m = re4.exec(stripped)) !== null) s.add(m[1])
  return s
}

function staticRules(chunks, byName) {
  const problems = []
  const names = [...byName.keys()]
  const nameSet = new Set(names)
  // what each declaration's code (not its comments) names
  for (const c of chunks) {
    let code = c.stripped
    if (c.kind === "var") code = code.replace(/^var\s+[A-Za-z_$][\w$]*\s*=/, (s) => " ".repeat(s.length))
    else code = code.replace(/^function\s+[A-Za-z_$][\w$]*/, (s) => " ".repeat(s.length))
    c.code = code
    c.refs = new Set([...codeWords(code)].filter((w) => nameSet.has(w) && w !== c.name))
    if (c.kind === "function") {
      // a function's own name inside its body is a recursive call, not a write
    }
  }
  // no assignment to a top-level binding outside its initializer
  for (const c of chunks) {
    const locals = localNames(c.stripped)
    if (c.kind === "function") locals.delete(c.name)
    for (const w of codeWords(c.code)) {
      if (!nameSet.has(w) || locals.has(w)) continue
      const id = w.replace(/\$/g, "\\$")
      const write = new RegExp("(?<![\\w$.])" + id + "\\s*(?:=(?!=)|\\+=|-=|\\*=|/=|%=|<<=|>>>?=|&=|\\|=|\\^=|\\+\\+|--)|(?:\\+\\+|--)\\s*" + id + "(?![\\w$])")
      const mutate = new RegExp("(?<![\\w$.])" + id + "\\s*(?:(?:\\.[A-Za-z_$][\\w$]*|\\[[^\\]\\n]*\\])+\\s*(?:=(?!=)|\\+=|-=|\\+\\+|--)|\\.\\s*(?:push|pop|shift|unshift|splice|sort|reverse|fill|copyWithin)\\s*\\()")
      if (write.test(c.code)) problems.push(c.where + ":" + c.line + ": `" + c.name + "` assigns to the top-level binding `" + w + "`")
      else if (mutate.test(c.code)) problems.push(c.where + ":" + c.line + ": `" + c.name + "` mutates the top-level binding `" + w + "` in place")
    }
  }
  // declared first: no chunk names a later `var` of its own part
  const seenInPart = new Map()
  for (const c of chunks) {
    if (!seenInPart.has(c.part)) seenInPart.set(c.part, new Set())
    const seen = seenInPart.get(c.part)
    const locals = localNames(c.stripped)
    for (const r of c.refs) {
      const d = byName.get(r)
      if (d.kind !== "var" || d.part !== c.part || seen.has(r) || locals.has(r)) continue
      problems.push(c.where + ":" + c.line + ": `" + c.name + "` names `" + r + "`, which is declared below it in part " + c.part +
        " (V4 logs qt.qml.usedbeforedeclared for that in a module); assign `" + r + "` to another part in the manifest")
    }
    seen.add(c.name)
  }
  // init locality, transitively through same-part functions an initializer names
  for (const c of chunks) {
    if (c.kind !== "var") continue
    const seen = new Set([c.name])
    const queue = [...c.refs].map((r) => [r, [c.name, r]])
    while (queue.length) {
      const [r, trail] = queue.shift()
      if (seen.has(r)) continue
      seen.add(r)
      const d = byName.get(r)
      if (d.part !== c.part) {
        problems.push(c.where + ":" + c.line + ": init locality: the initializer of `" + c.name + "` (" + c.part +
          ") reads `" + r + "` of part " + d.part + " (" + trail.join(" -> ") + ")")
        continue
      }
      if (d.kind === "function") for (const r2 of d.refs) queue.push([r2, trail.concat(r2)])
    }
  }
  return problems
}

// ---------------------------------------------------------------- generation
function wrapNames(names) {
  const out = []
  let line = " "
  for (const n of names) {
    const piece = " " + n + ","
    if (line.length + piece.length > WRAP && line.trim() !== "") { out.push(line); line = " " }
    line += piece
  }
  if (line.trim() !== "") out.push(line)
  if (out.length) out[out.length - 1] = out[out.length - 1].replace(/,$/, "")
  return out.join("\n")
}
function importBlock(names, from) { return "import {\n" + wrapNames(names) + "\n} from \"./" + from + ".mjs\"\n" }
function exportBlock(names) { return "export {\n" + wrapNames(names) + "\n}\n" }
function reexportBlock(names, part) {
  if (!names.length) return "export {} from \"./" + PART_DIR + "/" + part + ".mjs\"\n"
  return "export {\n" + wrapNames(names) + "\n} from \"./" + PART_DIR + "/" + part + ".mjs\"\n"
}
function partHeader(p) {
  return "// " + PART_DIR + "/" + p.name + ".mjs -- " + p.about + ". One part of " + AGGREGATOR +
    " (D-REL-5); its import and export lines are generated by split-model.mjs on the dev branch.\n"
}

// Imports by whole word over the part's CODE (each declaration's blanked
// text, comments and literal contents stripped by the lexer, property names
// after a dot excluded): an unused import costs nothing, a missing one is a
// ReferenceError at call time. F-GATE-8: reading the raw text instead made a
// comment that named another part's export into an import of it.
function generate(parts, chunks, byName, publicNames, headers) {
  const files = new Map()
  const graph = new Map()
  for (const p of parts) {
    const mine = chunks.filter((c) => c.part === p.name)
    const body = mine.map((c) => c.text).join("")
    const used = new Set()
    for (const c of mine) for (const w of codeWords(c.stripped)) used.add(w)
    let text = headers && headers.has(p.name) ? headers.get(p.name) : partHeader(p)
    const deps = []
    for (const q of parts) {
      if (q.name === p.name) continue
      const want = chunks.filter((c) => c.part === q.name && used.has(c.name)).map((c) => c.name)
      if (want.length) { text += importBlock(want, q.name); deps.push(q.name) }
    }
    graph.set(p.name, deps)
    text += body
    text += exportBlock(mine.map((c) => c.name))
    files.set(PART_DIR + "/" + p.name + ".mjs", text)
  }
  let agg = AGG_HEADER + GENERATED_LINE + "\n"
  const pub = new Set(publicNames)
  for (const p of parts) agg += reexportBlock(chunks.filter((c) => c.part === p.name && pub.has(c.name)).map((c) => c.name), p.name)
  files.set(AGGREGATOR, agg)
  return { files, graph }
}

// ---------------------------------------------------------------- reading a tree
function readPartFile(text, rel) {
  const ls = lines(text)
  if (!ls.length || !new RegExp("^// " + rel.replace(/[.]/g, "\\.") + " -- .+\\n$").test(ls[0]))
    refuse(rel + ":1: the first line is not the generated `// " + rel + " -- ...` header")
  let k = 1
  const imports = []
  while (k < ls.length && ls[k] === "import {\n") {
    let j = k + 1
    while (j < ls.length && /^  /.test(ls[j])) j++
    const m = j < ls.length && /^\} from "\.\/([a-z][a-z0-9-]*)\.mjs"\n$/.exec(ls[j])
    if (!m) refuse(rel + ":" + (k + 1) + ": an import block that is not in the generated form")
    imports.push(m[1])
    k = j + 1
  }
  let e = ls.length - 1
  if (e < 0 || ls[e] !== "}\n") refuse(rel + ": does not end with the generated export block")
  e--
  while (e > k && /^  /.test(ls[e])) e--
  if (ls[e] !== "export {\n") refuse(rel + ": does not end with the generated export block")
  return { header: ls[0], imports, bodyLines: ls.slice(k, e), bodyFirstLine: k + 1 }
}

function readAggregator(text) {
  const ls = lines(text)
  const g = ls.findIndex((l) => l.startsWith(GENERATED_MARK))
  if (g < 0) refuse(AGGREGATOR + ": no `" + GENERATED_MARK + "` line")
  const reexports = []
  let k = g + 1
  while (k < ls.length) {
    let m = /^export \{\} from "\.\/model\/([a-z][a-z0-9-]*)\.mjs"\n$/.exec(ls[k])
    if (m) { reexports.push({ part: m[1], names: [] }); k++; continue }
    if (ls[k] !== "export {\n") refuse(AGGREGATOR + ":" + (k + 1) + ": not a generated export line")
    let j = k + 1
    const names = []
    while (j < ls.length && /^  /.test(ls[j])) { ls[j].trim().split(",").map((x) => x.trim()).filter(Boolean).forEach((x) => names.push(x)); j++ }
    m = j < ls.length && /^\} from "\.\/model\/([a-z][a-z0-9-]*)\.mjs"\n$/.exec(ls[j])
    if (!m) refuse(AGGREGATOR + ":" + (k + 1) + ": an export block that is not in the generated form")
    reexports.push({ part: m[1], names })
    k = j + 1
  }
  return { header: ls.slice(0, g).join(""), reexports }
}

function listPartFiles(root) {
  const dir = path.join(root, PART_DIR)
  if (!fs.existsSync(dir)) return []
  return fs.readdirSync(dir).filter((f) => f.endsWith(".mjs")).sort()
}

// ---------------------------------------------------------------- runtime
function sameValue(a, b, at, out) {
  if (typeof a === "function" || typeof b === "function") {
    if (typeof a !== typeof b || Function.prototype.toString.call(a) !== Function.prototype.toString.call(b)) out.push(at + ": function source differs")
    return
  }
  if (a instanceof RegExp || b instanceof RegExp) {
    if (!(a instanceof RegExp && b instanceof RegExp) || a.source !== b.source || a.flags !== b.flags) out.push(at + ": regex differs")
    return
  }
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") {
    if (!Object.is(a, b)) out.push(at + ": " + String(a) + " vs " + String(b))
    return
  }
  if (Array.isArray(a) !== Array.isArray(b)) { out.push(at + ": array vs object"); return }
  if (Object.isFrozen(a) !== Object.isFrozen(b)) out.push(at + ": frozen in one and not the other")
  const ka = Object.keys(a), kb = Object.keys(b)
  if (ka.join("\u0000") !== kb.join("\u0000")) { out.push(at + ": keys differ"); return }
  for (const k of ka) sameValue(a[k], b[k], at + "." + k, out)
}

async function loadModules(root, partNames) {
  const ns = await import(pathToFileURL(path.join(root, AGGREGATOR)).href + "?t=" + Date.now())
  for (const p of partNames) await import(pathToFileURL(path.join(root, PART_DIR, p + ".mjs")).href)
  return ns
}

// ---------------------------------------------------------------- reporting
function tarjan(graph) {
  let index = 0
  const idx = new Map(), low = new Map(), on = new Set(), stack = [], out = []
  const visit = (v) => {
    idx.set(v, index); low.set(v, index); index++; stack.push(v); on.add(v)
    for (const w of graph.get(v) || []) {
      if (!idx.has(w)) { visit(w); low.set(v, Math.min(low.get(v), low.get(w))) }
      else if (on.has(w)) low.set(v, Math.min(low.get(v), idx.get(w)))
    }
    if (low.get(v) === idx.get(v)) {
      const scc = []; let w
      do { w = stack.pop(); on.delete(w); scc.push(w) } while (w !== v)
      if (scc.length > 1) out.push(scc.sort())
    }
  }
  for (const v of graph.keys()) if (!idx.has(v)) visit(v)
  return out
}

function report(files, chunks, parts, graph) {
  for (const p of parts) {
    const rel = PART_DIR + "/" + p.name + ".mjs"
    const n = chunks.filter((c) => c.part === p.name).length
    console.log("  " + rel.padEnd(28) + String(Buffer.byteLength(files.get(rel))).padStart(8) + " bytes  " +
      String(n).padStart(4) + " declarations  imports " + (graph.get(p.name).join(" ") || "-"))
  }
  console.log("  " + AGGREGATOR.padEnd(28) + String(Buffer.byteLength(files.get(AGGREGATOR))).padStart(8) + " bytes")
  const sccs = tarjan(graph)
  console.log("import cycles (strongly connected parts): " + (sccs.length ? sccs.map((s) => "{" + s.join(" ") + "}").join(" ") : "none"))
}

// ---------------------------------------------------------------- modes
function loadManifest(file) {
  const m = JSON.parse(fs.readFileSync(file, "utf8"))
  if (!Array.isArray(m.parts) || !m.parts.length) refuse(file + ": no parts")
  const seen = new Set()
  for (const p of m.parts) {
    if (!PART_NAME_RE.test(p.name || "")) refuse(file + ": part name " + JSON.stringify(p.name) + " is not lower-case words")
    if (seen.has(p.name)) refuse(file + ": part " + p.name + " is listed twice")
    seen.add(p.name)
    if (typeof p.about !== "string" || !p.about || /[\n]/.test(p.about)) refuse(file + ": part " + p.name + " has no one-line `about`")
    if (!Array.isArray(p.names)) refuse(file + ": part " + p.name + " has no `names`")
    p.names.forEach((n) => { if (!NAME_RE.test(n)) refuse(file + ": " + JSON.stringify(n) + " is not a name") })
  }
  return m
}

function readInput(opts) {
  if (opts.fromGit) {
    const text = execFileSync("git", ["-C", opts.root, "show", opts.fromGit + ":Model.js"], { encoding: "utf8", maxBuffer: 64 << 20 })
    return { text, where: opts.fromGit + ":Model.js" }
  }
  const file = path.resolve(opts.root, opts.input || "Model.js")
  if (!fs.existsSync(file)) refuse("no monolith at " + file + " (pass --input FILE or --from-git REF)")
  return { text: fs.readFileSync(file, "utf8"), where: path.relative(opts.root, file) || file }
}

function cutMonolith(opts, manifest) {
  const input = readInput(opts)
  const mono = parseMonolith(input.text, input.where)
  const rebuilt = mono.header + mono.chunks.map((c) => c.text).join("") + mono.between + mono.guard
  if (rebuilt !== input.text) refuse(input.where + ": the cut does not reassemble to the input byte for byte")
  const byName = indexModel(mono.chunks, mono.exportsList)
  const placement = assignParts(mono.chunks, manifest)
  const problems = staticRules(mono.chunks, byName)
  const gen = generate(manifest.parts, mono.chunks, byName, mono.exportsList)
  return { input, mono, byName, placement, problems, gen }
}

// Independent of the cut: find every input chunk, byte for byte, in exactly
// one part file ON DISK, in input order, with nothing left over in any part
// but the generated header, import and export lines.
function partitionFromDisk(root, mono, manifest) {
  const problems = []
  const bodies = new Map()
  for (const p of manifest.parts) {
    const rel = PART_DIR + "/" + p.name + ".mjs"
    const file = path.join(root, rel)
    if (!fs.existsSync(file)) { problems.push(rel + ": missing"); continue }
    const pf = readPartFile(fs.readFileSync(file, "utf8"), rel)
    bodies.set(p.name, { text: pf.bodyLines.join(""), at: 0 })
  }
  const extra = listPartFiles(root).filter((f) => !manifest.parts.some((p) => p.name + ".mjs" === f))
  extra.forEach((f) => problems.push(PART_DIR + "/" + f + ": a part the manifest does not list"))
  for (const c of mono.chunks) {
    const hits = [...bodies.entries()].filter(([, b]) => b.text.startsWith(c.text, b.at))
    if (hits.length !== 1) { problems.push("`" + c.name + "` (input line " + c.line + ") is found at the cursor of " + hits.length + " parts, not exactly one"); continue }
    hits[0][1].at += c.text.length
  }
  for (const [name, b] of bodies) if (b.at !== b.text.length)
    problems.push(PART_DIR + "/" + name + ".mjs: " + (b.text.length - b.at) + " bytes of body that are not a chunk of the input")
  return problems
}

async function runtimeEquivalence(root, mono, input, parts) {
  const problems = []
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "split-model-"))
  try {
    const file = path.join(tmp, "Model.js")
    fs.writeFileSync(file, input.text)
    const old = createRequire(import.meta.url)(file)
    const ns = await loadModules(root, parts.map((p) => p.name))
    const want = Object.keys(old).sort(), have = Object.keys(ns).sort()
    if (want.join(",") !== have.join(",")) {
      const miss = want.filter((k) => !(k in ns)), more = have.filter((k) => !(k in old))
      problems.push("Model.mjs exports differ from module.exports: missing [" + miss.join(", ") + "], extra [" + more.join(", ") + "]")
    }
    for (const k of want) if (k in ns) sameValue(old[k], ns[k], k, problems)
    return { problems, count: have.length }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true })
  }
}

function guardReport(mono) {
  console.log("comment lines inside the export guard, which the generated export lines replace: " +
    (mono.guardComments.length ? mono.guardComments.length + "\n    " + mono.guardComments.join("\n    ") : "none"))
}

// The lines the cut drops, each by its text: the monolith's header comment
// (the aggregator's header is generated instead) and the comment lines inside
// its export guard (the generated export lines replace the guard). Nothing is
// dropped silently: every one must appear, as a whole line, in section 9 of
// the record (ARCHITECTURE.md), or --write and --verify go red naming it. A
// later monolith that adds a guard comment -- the D-SINK-19 chain's, at
// integration -- is red here until the comment is recorded or moved.
function droppedLines(mono) {
  const header = lines(mono.header).map((l) => l.replace(/\n$/, "").trim()).filter((l) => l !== "" && l !== "//")
  return [
    ...header.map((text) => ({ text, from: "the one-file model's header" })),
    ...mono.guardComments.map((text) => ({ text, from: "a comment inside its export guard" })),
  ]
}

function recordProblems(opts, mono) {
  const dropped = droppedLines(mono)
  const file = opts.record || path.join(opts.root, RECORD_FILE)
  const rel = path.relative(opts.root, file) || file
  if (!fs.existsSync(file)) return [rel + ": missing, so the " + dropped.length + " line(s) the cut drops are recorded nowhere"]
  const ls = lines(fs.readFileSync(file, "utf8")).map((l) => l.replace(/\n$/, ""))
  const from = ls.findIndex((l) => RECORD_SECTION.test(l))
  if (from < 0) return [rel + ": no `## 9.` section to hold the " + dropped.length + " line(s) the cut drops"]
  let to = from + 1
  while (to < ls.length && !/^## /.test(ls[to])) to++
  const have = new Set(ls.slice(from + 1, to).map((l) => l.trim()))
  const problems = []
  let recorded = 0
  for (const d of dropped) {
    if (have.has(d.text)) { recorded++; continue }
    problems.push("`" + d.text + "` (" + d.from + ") is dropped by the cut and not recorded in " + rel + " section 9")
  }
  const n = (from_) => dropped.filter((d) => d.from === from_).length
  console.log("dropped by the cut and recorded in " + rel + " section 9: " + recorded + " of " + dropped.length +
    " line(s) (" + n("the one-file model's header") + " header, " + n("a comment inside its export guard") + " export-guard)")
  return problems
}

function placementReport(placement) {
  console.log("unplaced by the manifest (placed after the nearest preceding named declaration): " +
    (placement.unplaced.length ? placement.unplaced.map((u) => u.name + " -> " + u.part + " (line " + u.line + ")").join(", ") : "none"))
  console.log("named by the manifest but not declared in the input: " + (placement.absent.length ? placement.absent.join(", ") : "none"))
}

async function modeWrite(opts, manifest) {
  const cut = cutMonolith(opts, manifest)
  guardReport(cut.mono)
  placementReport(cut.placement)
  if (cut.problems.length) refuse("refusing to write a split that breaks the static rules:\n  " + cut.problems.join("\n  "))
  fs.mkdirSync(path.join(opts.root, PART_DIR), { recursive: true })
  for (const f of listPartFiles(opts.root)) if (!manifest.parts.some((p) => p.name + ".mjs" === f)) fs.rmSync(path.join(opts.root, PART_DIR, f))
  for (const [rel, text] of cut.gen.files) fs.writeFileSync(path.join(opts.root, rel), text)
  console.log("wrote " + cut.gen.files.size + " files from " + cut.input.where + ":")
  return verifyAgainstDisk(opts, manifest, cut)
}

async function verifyAgainstDisk(opts, manifest, cut) {
  const problems = [...cut.problems]
  for (const [rel, text] of cut.gen.files) {
    const file = path.join(opts.root, rel)
    if (!fs.existsSync(file)) { problems.push(rel + ": missing"); continue }
    if (fs.readFileSync(file, "utf8") !== text) problems.push(rel + ": differs from what the cut of " + cut.input.where + " writes")
  }
  problems.push(...partitionFromDisk(opts.root, cut.mono, manifest))
  problems.push(...recordProblems(opts, cut.mono))
  if (!problems.length) {
    const rt = await runtimeEquivalence(opts.root, cut.mono, cut.input, manifest.parts)
    problems.push(...rt.problems)
    if (!rt.problems.length) console.log("runtime: Model.mjs exports " + rt.count + " names, each equal to require(" + cut.input.where + ")")
  }
  report(cut.gen.files, cut.mono.chunks, manifest.parts, cut.gen.graph)
  console.log("chunks: " + cut.mono.chunks.length + " declarations of " + cut.input.where + ", each found byte-identical in exactly one part")
  return problems
}

async function modeVerify(opts, manifest) {
  const cut = cutMonolith(opts, manifest)
  guardReport(cut.mono)
  placementReport(cut.placement)
  return verifyAgainstDisk(opts, manifest, cut)
}

function readTree(opts, manifest) {
  const aggFile = path.join(opts.root, AGGREGATOR)
  if (!fs.existsSync(aggFile)) refuse("no " + AGGREGATOR + " under " + opts.root)
  const agg = readAggregator(fs.readFileSync(aggFile, "utf8"))
  const problems = []
  const onDisk = listPartFiles(opts.root)
  const listed = manifest.parts.map((p) => p.name + ".mjs")
  onDisk.filter((f) => !listed.includes(f)).forEach((f) => problems.push(PART_DIR + "/" + f + ": a part the manifest does not list"))
  const aggParts = agg.reexports.map((r) => r.part)
  if (aggParts.join(" ") !== manifest.parts.map((p) => p.name).join(" "))
    problems.push(AGGREGATOR + ": re-exports the parts [" + aggParts.join(" ") + "], the manifest lists [" + manifest.parts.map((p) => p.name).join(" ") + "]")
  const chunks = []
  const headers = new Map()
  for (const p of manifest.parts) {
    const rel = PART_DIR + "/" + p.name + ".mjs"
    const file = path.join(opts.root, rel)
    if (!fs.existsSync(file)) { problems.push(rel + ": missing"); continue }
    const pf = readPartFile(fs.readFileSync(file, "utf8"), rel)
    headers.set(p.name, pf.header)
    const { chunks: cs, trailing } = cutChunks(pf.bodyLines, pf.bodyFirstLine, rel)
    if (trailing !== "") problems.push(rel + ": text after the last declaration that is not generated")
    cs.forEach((c) => { c.part = p.name })
    chunks.push(...cs)
  }
  const publicNames = []
  for (const r of agg.reexports) for (const n of r.names) publicNames.push(n)
  return { agg, chunks, headers, publicNames, problems }
}

// F-GATE-10. The manifest's `parts[].names`, compared with what the parts on
// disk declare: one problem per drifted part, naming the unlisted and the
// stale names, or nothing. The lists are a record of the tree, so --relink
// rewrites them (writeManifest) and --check reports them.
const MANIFEST_ABOUT = "D-REL-5: the parts of model/ in aggregator order, and which top-level declaration of the model lives in each, by NAME. " +
  "`parts[].names` is GENERATED: `node scripts/split-model.mjs --relink` rewrites each list from the part's own declarations " +
  "(private names included, in declaration order) and `--check` goes red on any drift (F-GATE-10). " +
  "The cut modes (--write, --verify) read the lists to place a monolith's declarations; see the script's header."
function manifestDrift(manifest, chunks, label) {
  const problems = []
  for (const p of manifest.parts) {
    const have = chunks.filter((c) => c.part === p.name).map((c) => c.name)
    if (have.join(",") === p.names.join(",")) continue
    const listed = new Set(p.names), declared = new Set(have)
    const unlisted = have.filter((n) => !listed.has(n)), stale = p.names.filter((n) => !declared.has(n))
    let why = ""
    if (unlisted.length) why += "; declared but not listed: " + unlisted.join(", ")
    if (stale.length) why += "; listed but not declared: " + stale.join(", ")
    if (!why) why = "; the same names in another order"
    problems.push(label + ": part " + p.name + " lists " + p.names.length + " name(s) and the part declares " + have.length +
      why + " (run node scripts/split-model.mjs --relink)")
  }
  return problems
}
function writeManifest(file, manifest, chunks) {
  const out = {
    about: MANIFEST_ABOUT,
    parts: manifest.parts.map((p) => ({ name: p.name, about: p.about, names: chunks.filter((c) => c.part === p.name).map((c) => c.name) })),
  }
  fs.writeFileSync(file, JSON.stringify(out, null, 2) + "\n")
}

async function modeTree(opts, manifest, rewrite) {
  const t = readTree(opts, manifest)
  const byName = indexModel(t.chunks, t.publicNames)
  const problems = [...t.problems]
  for (const r of t.agg.reexports) for (const n of r.names)
    if (byName.get(n).part !== r.part) {
      if (rewrite) continue
      problems.push(AGGREGATOR + ": `" + n + "` is re-exported from " + r.part + " but declared in " + byName.get(n).part)
    }
  problems.push(...staticRules(t.chunks, byName))
  // F-GATE-10: the manifest's name lists are judged against the tree like
  // every other generated text -- rewritten by --relink, red under --check.
  // The `about` is rewritten with them, so the file says what it is.
  const manifestLabel = path.relative(opts.root, opts.manifest) || opts.manifest
  const drift = manifestDrift(manifest, t.chunks, manifestLabel)
  if (drift.length || (rewrite && manifest.about !== MANIFEST_ABOUT)) {
    if (rewrite) { writeManifest(opts.manifest, manifest, t.chunks); console.log("relinked " + manifestLabel) }
    else problems.push(...drift)
  }
  const gen = generate(manifest.parts, t.chunks, byName, t.publicNames, t.headers)
  for (const [rel, text] of gen.files) {
    const file = path.join(opts.root, rel)
    const now = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null
    if (now === text) continue
    if (rewrite) { fs.writeFileSync(file, text); console.log("relinked " + rel) }
    else problems.push(rel + ": its generated lines are not what --relink writes (run node scripts/split-model.mjs --relink)")
  }
  if (!problems.length) {
    try {
      const ns = await loadModules(opts.root, manifest.parts.map((p) => p.name))
      const have = Object.keys(ns).sort(), want = [...t.publicNames].sort()
      if (have.join(",") !== want.join(",")) problems.push(AGGREGATOR + ": the loaded namespace is not the listed names")
      else console.log("runtime: " + AGGREGATOR + " and every part load; " + have.length + " public names")
    } catch (e) {
      problems.push("loading the modules failed: " + e.message)
    }
  }
  report(gen.files, t.chunks, manifest.parts, gen.graph)
  console.log("declarations: " + t.chunks.length + " in " + manifest.parts.length + " parts")
  return problems
}

// ---------------------------------------------------------------- main
function parseArgs(argv) {
  const opts = { root: path.resolve(HERE, ".."), manifest: null, input: null, fromGit: null, mode: null, record: null }
  for (let k = 0; k < argv.length; k++) {
    const a = argv[k]
    const val = () => { if (k + 1 >= argv.length) refuse(a + " needs a value"); return argv[++k] }
    if (a === "--write" || a === "--verify" || a === "--check" || a === "--relink") {
      if (opts.mode) refuse("one mode at a time (" + opts.mode + " and " + a + ")")
      opts.mode = a.slice(2)
    } else if (a === "--root") opts.root = path.resolve(val())
    else if (a === "--manifest") opts.manifest = path.resolve(val())
    else if (a === "--input") opts.input = val()
    else if (a === "--record") opts.record = path.resolve(val())
    else if (a === "--from-git") opts.fromGit = val()
    else refuse("unknown argument " + JSON.stringify(a) + "\nusage: split-model.mjs --write|--verify|--check|--relink [--root DIR] [--manifest FILE] [--input FILE | --from-git REF] [--record FILE]")
  }
  if (!opts.mode) refuse("usage: split-model.mjs --write|--verify|--check|--relink [--root DIR] [--manifest FILE] [--input FILE | --from-git REF] [--record FILE]")
  if ((opts.mode === "check" || opts.mode === "relink") && (opts.input || opts.fromGit)) refuse("--" + opts.mode + " reads the tree, not a monolith")
  if (opts.input && opts.fromGit) refuse("--input or --from-git, not both")
  if (!opts.manifest) opts.manifest = path.join(opts.root, "scripts", "model-parts.json")
  return opts
}

async function main() {
  let problems
  try {
    const opts = parseArgs(process.argv.slice(2))
    const manifest = loadManifest(opts.manifest)
    if (opts.mode === "write") problems = await modeWrite(opts, manifest)
    else if (opts.mode === "verify") problems = await modeVerify(opts, manifest)
    else problems = await modeTree(opts, manifest, opts.mode === "relink")
    if (problems.length) {
      console.log("split-model: " + problems.length + " problem(s):")
      problems.forEach((p) => console.log("  " + p))
      process.exitCode = 1
      return
    }
    console.log("split-model: " + opts.mode + " ok")
  } catch (e) {
    if (e instanceof Refusal) { console.log("split-model: refused: " + e.message); process.exitCode = 2; return }
    throw e
  }
}

await main()
