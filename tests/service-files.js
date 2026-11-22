// tests/service-files.js -- the service as the files Service.qml declares
// (D-REL-14). NOT shipped: a reader for the tests and the harness.
//
// WHY. D-REL-14 splits Service.qml's functions into classic JavaScript
// code-behinds: `Service-<domain>.js` files, each imported by Service.qml as
// `import "Service-<domain>.js" as Service<Domain>` with no `.import` and no
// `.pragma`, so they run in the component's own scope, while Service.qml keeps
// a one-line forwarder at each moved function's old place:
//
//   function F(a, b) { return ServicePip.F(a, b) }    (two-space indent)
//
// Every test that read Service.qml's TEXT -- a pin on a function's body, a
// harness boot, a seam grep -- would then read a forwarder where the body
// used to be. So nothing reads Service.qml directly any more; it asks here.
//
//   serviceFiles(where)  the files of the service, Service.qml first and then
//                        each code-behind its `import "<file>.js" as <Q>`
//                        lines declare, in their order: the real files, for
//                        a reader that judges each file or copies the tree.
//   serviceText(where)   the INLINE view: Service.qml with each declaration
//                        line dropped and each forwarder line replaced by
//                        its function's text from the code-behind -- the
//                        contiguous `//` lines directly above
//                        `  function F(` and the function through its closing
//                        brace's line. That is the one-file Service.qml the
//                        split was cut from, so a text pin never moves.
//
// `where` is a plugin root, or the path of the service's file: a path ending
// in `.qml`, or any regular file (IPTV_SERVICE_QML may name a mutant copy
// called anything). Its code-behinds are read from the same directory, as the
// QML engine resolves them. While Service.qml declares no code-behind -- true
// of every tree up to and including this reader's own commit -- serviceFiles
// is [Service.qml] and serviceText is the file's text exactly.
//
// The reader refuses rather than guesses, with a kind both engines share:
//   declaration      a line importing a .js, in either quote, that is not
//                    exactly `import "<file>.js" as <Qualifier>`
//   declared-twice   a file or a qualifier declared twice
//   missing          Service.qml, or a declared code-behind, is not there
//   encoding         a file that is not UTF-8
//   function-twice   a code-behind declares one function twice
//   unbalanced       a code-behind function with no closing brace
//   stray            a code-behind line outside every function that is
//                    neither blank nor a `//` comment: a top-level statement,
//                    a function at another indent or spelled
//                    `function F (`, a header whose arguments hold a ")" --
//                    anything the view would otherwise drop in silence
//   not-exact        a line shaped `  function F(...) { return Q.` for a
//                    declared Q that is not exactly F's forwarder: the call
//                    repeats the header's arguments, those are plain names
//                    (`a, b`, so the forwarder passes what it was given), and
//                    they are F's own in the code-behind
//   no-function      a forwarder whose code-behind has no such function
//   forwarded-twice  two forwarders for one function
//   unforwarded      a code-behind function no forwarder names
// So the view holds every line of every code-behind but its blank lines and
// loose `//` comments, and runs as the forwarders do. The rest of the layout
// (what a moved body may name, `.import` and `.pragma` beyond their being
// stray) is scripts/split-service.py --check's to judge (D-REL-14's C2).
//
// Its twin in Python is scripts/service_files.py. The two agree byte for byte
// on every input, held by one shared fixture both run
// (tests/fixtures/service-split/), by the node case "D-REL-14: the service
// readers" and by tests/test_service_files.py, each of which also runs the
// other engine over this tree and over the fixture. Both read lines split at
// "\n" only, keep a "\r" as text, and refuse bytes that are not UTF-8 rather
// than replace them. The brace matcher is tests/service-harness.js's scan,
// copied so this file loads nothing else; the node case holds the two to the
// same answer over every root function of the tree's Service.qml.
//
// CLI (for the other engine and for a human):
//   node tests/service-files.js names <where>   one file name a line
//   node tests/service-files.js text <where>    the inline view, as is
// Exit 1 with one line on stderr on a refusal, 2 on a usage error.
"use strict"
const fs = require("fs")
const path = require("path")

const SERVICE = "Service.qml"

// One declaration a line. A "\r" before the end is a CRLF checkout's, and
// QML reads that line as the same import.
const DECLARATION = /^import "([A-Za-z0-9_][A-Za-z0-9_.-]*\.js)" as ([A-Z][A-Za-z0-9_]*)\r?$/
// Any line that imports a classic script must read as a declaration: a
// spelling this reader did not see would drop a code-behind in silence. QML
// takes either quote (qmllint 6.12 resolves `import 'x.js' as X`), so both
// are seen here and DECLARATION, double quotes only, refuses the single.
const IMPORTS_A_SCRIPT = /^[ \t]*import[ \t]+(?:"[^"]*\.js"|'[^']*\.js')/
// A function at the root's two-space indent, matched at a line start.
const HEADER = /  function ([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\) \{/y
const COMMENT_LINE = /^[ \t]*\/\//
const BLANK_LINE = /^[ \t]*\r?$/
// A forwarder: the shape first (so a near miss for a declared qualifier is
// refused, never kept as a root function), then the exact form, whose
// arguments are plain names: a default (`a = 1`) or a pattern (`{ k }`)
// repeated in the call is an assignment or an object there, not the value
// the forwarder was given, so the shell would run something the view does
// not show.
const FORWARDER_SHAPE = /^  function ([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\) \{ return ([A-Z][A-Za-z0-9_]*)\./
const FORWARDER = /^  function ([A-Za-z_][A-Za-z0-9_]*)\(((?:[A-Za-z_][A-Za-z0-9_]*(?:, [A-Za-z_][A-Za-z0-9_]*)*)?)\) \{ return ([A-Z][A-Za-z0-9_]*)\.\1\(\2\) \}\r?$/
// After one of these a "/" opens a regular-expression literal (the harness's
// own rule, character for character).
const REGEX_AFTER = /[(,=:[!&|?{};+\-*%<>~^\n]/
const SPACE = /\s/

class ServiceFilesError extends Error {
  constructor(kind, message) {
    super(message)
    this.kind = kind
  }
}

function refuse(kind, message) { return new ServiceFilesError(kind, kind + ": " + message) }

// The index of the "}" matching the "{" at `open`, skipping strings,
// comments and regular-expression literals; -1 when there is none.
// tests/service-harness.js scan() with untilNewline false, line for line.
function matchBrace(text, open) {
  let depth = 0
  let prev = ""
  for (let i = open; i < text.length; i++) {
    const c = text[i]
    if (c === "/" && text[i + 1] === "/") {
      i = text.indexOf("\n", i)
      if (i === -1) return -1
      prev = "\n"
      continue
    }
    if (c === "/" && text[i + 1] === "*") { i = text.indexOf("*/", i + 2); if (i === -1) return -1; i++; continue }
    if (c === '"' || c === "'" || c === "`") {
      for (i++; i < text.length && text[i] !== c; i++) if (text[i] === "\\") i++
      prev = c
      continue
    }
    if (c === "/" && REGEX_AFTER.test(prev || "\n")) {
      let cls = false
      for (i++; i < text.length; i++) {
        if (text[i] === "\\") { i++; continue }
        if (text[i] === "[") cls = true
        else if (text[i] === "]") cls = false
        else if (text[i] === "/" && !cls) break
      }
      prev = "/"
      continue
    }
    if (c === "{" || c === "(" || c === "[") depth++
    else if (c === "}" || c === ")" || c === "]") {
      depth--
      if (depth === 0 && c === "}") return i
    }
    if (!SPACE.test(c)) prev = c
  }
  return -1
}

// The declarations, in order: [{ file, qualifier, line }].
function declarations(text) {
  const out = []
  const lines = text.split("\n")
  for (let n = 0; n < lines.length; n++) {
    if (!IMPORTS_A_SCRIPT.test(lines[n])) continue
    const m = DECLARATION.exec(lines[n])
    if (!m) throw refuse("declaration", "line " + (n + 1) + " imports a script and is not `import \"<file>.js\" as <Qualifier>`")
    for (const d of out) {
      if (d.file === m[1]) throw refuse("declared-twice", m[1] + " is declared on lines " + d.line + " and " + (n + 1))
      if (d.qualifier === m[2]) throw refuse("declared-twice", "the qualifier " + m[2] + " is declared on lines " + d.line + " and " + (n + 1))
    }
    out.push({ file: m[1], qualifier: m[2], line: n + 1 })
  }
  return out
}

// Every function at the two-space indent of `text`, by name, as its text:
// the contiguous `//` lines directly above the header, through the end of
// the closing brace's line (its "\n" not included). A Map, in file order.
// `found`, when given, gets one { name, args, start, end } a function: its
// header's argument text and the span's offsets in `text`, end exclusive.
function functionSpans(text, label, found) {
  const out = new Map()
  let at = 0
  for (;;) {
    HEADER.lastIndex = at
    const m = HEADER.exec(text)
    if (m) {
      const open = at + m[0].length - 1
      const close = matchBrace(text, open)
      if (close === -1) throw refuse("unbalanced", (label || "the text") + ": " + m[1] + " has no closing brace")
      let start = at
      while (start > 0) {
        const prevEnd = start - 1
        const prevStart = prevEnd === 0 ? 0 : text.lastIndexOf("\n", prevEnd - 1) + 1
        if (!COMMENT_LINE.test(text.slice(prevStart, prevEnd))) break
        start = prevStart
      }
      const eol = text.indexOf("\n", close)
      if (out.has(m[1])) throw refuse("function-twice", (label || "the text") + " declares " + m[1] + " twice")
      const end = eol === -1 ? text.length : eol
      out.set(m[1], text.slice(start, end))
      if (found) found.push({ name: m[1], args: m[2], start, end })
    }
    const nl = text.indexOf("\n", at)
    if (nl === -1) break
    at = nl + 1
  }
  return out
}

// The first line (1-based) of a code-behind's `text` that lies outside every
// span in `found` and is neither blank nor a `//` comment; 0 when there is
// none. Such a line is code the inline view would drop.
function strayLine(text, found) {
  let at = 0
  for (let n = 1; ; n++) {
    const nl = text.indexOf("\n", at)
    const line = text.slice(at, nl === -1 ? text.length : nl)
    if (!BLANK_LINE.test(line) && !COMMENT_LINE.test(line) && !found.some(f => at >= f.start && at < f.end)) return n
    if (nl === -1) return 0
    at = nl + 1
  }
}

// The inline view of a Service.qml text over its code-behinds' texts, given
// as a Map (or object) from declared file name to text.
function inlineText(text, files) {
  const decls = declarations(text)
  if (decls.length === 0) return text
  const get = files instanceof Map ? n => files.get(n) : n => (Object.prototype.hasOwnProperty.call(files, n) ? files[n] : undefined)
  const byQualifier = new Map()
  for (const d of decls) {
    const body = get(d.file)
    if (typeof body !== "string") throw refuse("missing", d.file + " is declared (line " + d.line + ") and is not there")
    const found = []
    const spans = functionSpans(body, d.file, found)
    const stray = strayLine(body, found)
    if (stray) throw refuse("stray", d.file + " line " + stray + " is outside every function and is neither blank nor a // comment")
    byQualifier.set(d.qualifier, { file: d.file, spans, args: new Map(found.map(f => [f.name, f.args])), used: new Set() })
  }
  const out = []
  const lines = text.split("\n")
  for (const line of lines) {
    if (IMPORTS_A_SCRIPT.test(line)) continue
    const shape = FORWARDER_SHAPE.exec(line)
    if (shape && byQualifier.has(shape[3])) {
      const m = FORWARDER.exec(line)
      if (!m) throw refuse("not-exact", "`" + line.trim() + "` calls " + shape[3] + " and is not `function F(args) { return " + shape[3] + ".F(args) }`")
      const cb = byQualifier.get(m[3])
      if (!cb.spans.has(m[1])) throw refuse("no-function", m[1] + " is forwarded to " + cb.file + ", which has no such function")
      if (cb.used.has(m[1])) throw refuse("forwarded-twice", m[1] + " of " + cb.file + " has two forwarders")
      if (cb.args.get(m[1]) !== m[2]) throw refuse("not-exact", "`" + line.trim() + "` takes (" + m[2] + ") and " + m[1] + " in " + cb.file + " takes (" + cb.args.get(m[1]) + ")")
      cb.used.add(m[1])
      out.push(cb.spans.get(m[1]))
      continue
    }
    out.push(line)
  }
  for (const cb of byQualifier.values()) {
    const left = [...cb.spans.keys()].filter(n => !cb.used.has(n))
    if (left.length > 0) throw refuse("unforwarded", cb.file + " holds " + left.join(", ") + ", which no forwarder names")
  }
  return out.join("\n")
}

const DECODER = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true })

function readText(file) {
  let bytes
  try {
    bytes = fs.readFileSync(file)
  } catch (error) {
    if (error && error.code === "ENOENT") throw refuse("missing", file + " is not there")
    throw error
  }
  try {
    return DECODER.decode(bytes)
  } catch (error) {
    throw refuse("encoding", file + " is not UTF-8")
  }
}

// A path ending in `.qml`, or any regular file, is the service's file;
// anything else is a plugin root holding Service.qml.
function servicePath(where) {
  const p = String(where)
  if (/\.qml$/.test(p)) return p
  let st = null
  try { st = fs.statSync(p) } catch (error) { st = null }
  return st && st.isFile() ? p : path.join(p, SERVICE)
}

// The file names, relative to Service.qml's directory: its own first.
function serviceNames(where) {
  const svc = servicePath(where)
  return [path.basename(svc)].concat(declarations(readText(svc)).map(d => d.file))
}

function serviceFiles(where) {
  const svc = servicePath(where)
  return [svc].concat(declarations(readText(svc)).map(d => path.join(path.dirname(svc), d.file)))
}

function serviceText(where) {
  const svc = servicePath(where)
  const text = readText(svc)
  const decls = declarations(text)
  if (decls.length === 0) return text
  const files = new Map()
  for (const d of decls) {
    const file = path.join(path.dirname(svc), d.file)
    if (fs.existsSync(file)) files.set(d.file, readText(file))
  }
  return inlineText(text, files)
}

module.exports = { SERVICE, ServiceFilesError, matchBrace, declarations, functionSpans, inlineText, servicePath, serviceNames, serviceFiles, serviceText }

if (require.main === module) {
  const [verb, where] = process.argv.slice(2)
  if (!where || (verb !== "names" && verb !== "text") || process.argv.length !== 4) {
    process.stderr.write("usage: node tests/service-files.js names|text <plugin root or Service.qml>\n")
    process.exit(2)
  }
  let out
  try {
    out = verb === "names" ? serviceNames(where).map(n => n + "\n").join("") : serviceText(where)
  } catch (error) {
    process.stderr.write("service-files: " + (error && error.message || String(error)) + "\n")
    process.exit(1)
  }
  process.stdout.write(out)
}
