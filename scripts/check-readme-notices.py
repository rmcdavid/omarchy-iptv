#!/usr/bin/env python3
"""Join every notice the README quotes to the string the plugin ships
(F-HARNESS-35).

WHY. README.md quotes the plugin's own notices in backticks -- `Bar setting
ignored`, `Set a playlist first`, `Sources is full (50) - remove one first`
-- and nothing joined a quotation to the model, Guide.qml, Service.qml or
the helper that composes it, so a copy change could leave the README quoting
text the plugin no longer shows and nothing went red. CLAUDE.md rule 13's
shape: two things joined by a name and verified by nobody. Raised 2026-10-20
by the sweep's docs lane, given its id 2026-10-21.

WHAT IS A NOTICE HERE. A backticked span outside a code fence whose first
character is a capital letter and which contains a space. That shape also
catches key chords (`SUPER + SHIFT + H`) and commands
(`OMARCHY_IPTV_URL=... python3 ...`), so those two shapes are skipped by
rule and EVERY skip is printed with its reason: a quote this script stops
looking at is visible on the gate's log, never silently exempt.

WHAT JOINS. A notice joins when it is
  exact:    equal to a string literal in a shipped code file -- the .qml and
            .mjs entries of ALLOWLIST in scripts/release.py and the helper's
            stub and parts (bin/omarchy-iptv, bin/helper/*.py); comments and
            python docstrings are not copy and are not read;
  composed: equal to what a named composer returns with the shipping
            constants -- `Model.sourceErrorMessage(code, {})` over every key
            the sources table declares, run through node against the real
            Model.mjs, so `Sources is full (50) - remove one first` is
            checked against MAX_SOURCES and not against a copy of it;
  elided:   ending in `...` (ASCII or U+2026), and the text before the
            ellipsis is the START of a shipped literal or composed string --
            the README's way of quoting a line the plugin completes.
A quote that is merely a prefix of a literal without saying so does NOT
join (the plugin never shows `Playlist warning:` alone; it shows
`Playlist warning: ...`), which is what the ellipsis rule is for.

Exit 0 and one summary line ("readme notices: Q quote(s) in F file(s), J
joined (E exact, C composed, P elided), S skipped, 0 problem(s)") when
clean; exit 1 with `file:line: <quote> matches no shipped string` per
problem. `--root DIR` reads another tree; FILE arguments name the documents
to read (default README.md under the root). ASCII only (CLAUDE.md rule 8).
Not shipped.
"""
import ast
import glob
import io
import json
import os
import re
import subprocess
import sys

SPAN = re.compile(r"`([^`\n]+)`")
CHORD = re.compile(r"^[A-Z][A-Za-z0-9]*( \+ [A-Za-z0-9]+)+$")
ENV_COMMAND = re.compile(r"^[A-Z][A-Z0-9_]*=")
ELLIPSIS = ("...", "…")


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def allowlist(root):
    path = os.path.join(root, "scripts", "release.py")
    with io.open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and "ALLOWLIST" in [
                t.id for t in node.targets if isinstance(t, ast.Name)]:
            return [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
    return []


def shipped_code_files(root):
    files = [f for f in allowlist(root) if f.endswith((".qml", ".mjs"))]
    helper = [f for f in allowlist(root) if f.startswith("bin/")]
    return files + helper


def js_literals(text):
    """Every "..." and '...' literal outside comments, escapes decoded.
    A hand tokenizer, because `//` inside a URL string is not a comment."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'`":
            quote = c
            j = i + 1
            buf = []
            while j < n and text[j] != quote:
                if text[j] == "\\" and j + 1 < n:
                    esc = text[j + 1]
                    if esc == "u" and j + 5 < n:
                        try:
                            buf.append(chr(int(text[j + 2:j + 6], 16)))
                            j += 6
                            continue
                        except ValueError:
                            pass
                    buf.append({"n": "\n", "t": "\t", "r": "\r"}.get(esc, esc))
                    j += 2
                    continue
                if text[j] == "\n" and quote != "`":
                    break
                buf.append(text[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
            continue
        i += 1
    return out


def py_literals(text, path):
    tree = ast.parse(text, path)
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            docstrings.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            out.append(node.value)
    return out


def shipped_literals(root):
    literals = set()
    files = 0
    for rel in shipped_code_files(root):
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding="utf-8") as fh:
            text = fh.read()
        files += 1
        if rel.endswith(".py") or rel == "bin/omarchy-iptv":
            literals.update(py_literals(text, path))
        else:
            literals.update(js_literals(text))
    # Surrogate pairs written as two \uXXXX escapes (the Nerd Font glyphs)
    # decode to lone surrogates; join them so the set holds real text.
    joined = set()
    for s in literals:
        try:
            joined.add(s.encode("utf-16", "surrogatepass").decode("utf-16"))
        except UnicodeDecodeError:
            joined.add(s)
    return joined, files


NODE_COMPOSE = """
const M = require(process.argv[1]);
const keys = JSON.parse(process.argv[2]);
const out = {};
for (const k of keys) {
  try { const s = M.sourceErrorMessage(k, {}); if (typeof s === "string" && s) out[k] = s; } catch (e) {}
}
process.stdout.write(JSON.stringify(out));
"""


def composed_strings(root):
    """What the named composers return with the shipping constants, or None
    with a reason when they cannot be run (a problem in the real tree, a
    non-event in a tree with no model)."""
    model = os.path.join(root, "Model.mjs")
    sources = os.path.join(root, "model", "sources.mjs")
    if not os.path.isfile(model) or not os.path.isfile(sources):
        return {}, None
    with io.open(sources, encoding="utf-8") as fh:
        keys = sorted(set(re.findall(r"^\s+([a-z_]+):\s", fh.read(), re.M)))
    try:
        proc = subprocess.run(
            ["node", "-e", NODE_COMPOSE, model, json.dumps(keys)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {}, "node could not run the composer: %s" % e
    if proc.returncode != 0:
        return {}, "the composer failed: %s" % proc.stderr.decode("utf-8", "replace").strip()[:200]
    table = json.loads(proc.stdout.decode("utf-8"))
    return {"sourceErrorMessage(%s)" % k: v for k, v in table.items()}, None


def notices_in(text):
    """(line, quote) for every candidate span outside code fences."""
    out = []
    fenced = False
    for n, line in enumerate(text.split("\n"), 1):
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for m in SPAN.finditer(line):
            q = m.group(1)
            if q[:1].isupper() and " " in q:
                out.append((n, q))
    return out


def classify(quote, literals, composed):
    if CHORD.match(quote):
        return "skipped", "a key chord"
    if ENV_COMMAND.match(quote):
        return "skipped", "a command"
    if quote in literals:
        return "exact", None
    for name, value in composed.items():
        if value == quote:
            return "composed", name
    for mark in ELLIPSIS:
        if quote.endswith(mark):
            head = quote[:-len(mark)].rstrip()
            if head and any(s.startswith(head) and len(s) > len(head) for s in literals):
                return "elided", None
            for name, value in composed.items():
                if value.startswith(head) and len(value) > len(head):
                    return "elided", name
            return "problem", "elided, and nothing shipped starts with `%s`" % head
    return "problem", "matches no shipped string"


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = repo_root()
    if argv[:1] == ["--root"]:
        root = os.path.abspath(argv[1])
        argv = argv[2:]
    docs = argv or ["README.md"]
    literals, code_files = shipped_literals(root)
    composed, why = composed_strings(root)
    problems = []
    if why:
        problems.append("composer: " + why)
    counts = {"exact": 0, "composed": 0, "elided": 0, "skipped": 0}
    quotes = 0
    for rel in docs:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if not os.path.isfile(path):
            problems.append("%s: not found" % rel)
            continue
        with io.open(path, encoding="utf-8") as fh:
            text = fh.read()
        for n, q in notices_in(text):
            quotes += 1
            kind, note = classify(q, literals, composed)
            if kind == "skipped":
                counts[kind] += 1
                print("%s:%d: skipped `%s` (%s)" % (rel, n, q, note))
            elif kind == "problem":
                problems.append("%s:%d: `%s` %s" % (rel, n, q, note))
            else:
                counts[kind] += 1
    for line in problems:
        print(line)
    joined = counts["exact"] + counts["composed"] + counts["elided"]
    print("readme notices: %d quote(s) in %d file(s), %d joined (%d exact, %d composed,"
          " %d elided), %d skipped, %d shipped code file(s), %d composed string(s),"
          " %d problem(s)"
          % (quotes, len(docs), joined, counts["exact"], counts["composed"],
             counts["elided"], counts["skipped"], code_files, len(composed),
             len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
