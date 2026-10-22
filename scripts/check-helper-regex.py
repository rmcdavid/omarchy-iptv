#!/usr/bin/env python3
"""Prove every regular expression the helper compiles has been reviewed for
its cost, and say which ones are not linear.

WHY THIS EXISTS (D-EPG-8, ruling R30g, 2026-10-21). The bounds sweep found
`\\s*\\([^()]*\\)\\s*$` applied with .sub() to guide <display-name> text that
nothing folded or capped: no literal prefix, so the engine tried it at every
position, and each position inside a whitespace run of length k scanned the
rest of the run and backed off -- about k*k/2 steps for one run, in a helper
the service stops only after 180 s. F-SINK-11 had found the same shape in
the URL redactor a month earlier and fixed THAT pattern only. A review that
covers one pattern at a time is the review rule 15 says not to do, so this
is the call that makes it every pattern: R30g's rule, "no regex whose cost
is super-linear in its input is applied to provider text", needs to know
every regex there is, and a list written once in a report would be a list a
human is expected to keep copying (rule 13).

THE RULE. Every call `re.compile|search|match|fullmatch|sub|subn|split|
findall|finditer(<pattern>, ...)` in bin/helper/*.py must have its pattern
in REVIEWED below, with what it reads (`provider` text, `user` text, or the
plugin's `own` data) and a verdict: `linear` and why, or `open` and the
defect it is (its board id once the board has numbered it). A pattern that
is new or CHANGED is unreviewed and fails, so editing a pattern is editing
its review. A reviewed pattern no
longer in the helper fails too, so the table cannot keep a verdict for code
that is gone. `from re import ...` and `import re as ...` fail, because a
call through another name would not be seen.

The key is the pattern's own text when it is a string literal, and the
source of the expression (ast.unparse) when it is built, as two are. An
`open` verdict is reported on every run and does not fail the gate: it is a
defect, the board holds defects, and the gate is not the board. Nothing here
runs a pattern on any input.
"""
import argparse
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS = {"compile", "search", "match", "fullmatch", "sub", "subn", "split", "findall", "finditer"}

# (pattern, what it reads, verdict). Written with the same literal the
# helper uses, so a reader can find the line.
REVIEWED = [
    (r"^[0-9a-f]{8}(-[0-9]{1,3})?$", "own",
     "linear: anchored, every quantifier bounded (SOURCE_KEY_RE)"),
    ("'[A-Za-z0-9]{%d,}' % EPG_ADDR_MIN_TOKEN", "provider",
     "linear: one class run and nothing after it; finditer resumes past each match, and a run shorter "
     "than EPG_ADDR_MIN_TOKEN is re-counted from each of its own positions, at most 11 steps each "
     "(_EPG_ADDR_TOKEN, stream URLs in build_alias)"),
    (r"^[A-Za-z0-9-]+$", "provider",
     "linear: anchored, one run then $, backing off one test per character (_HEADER_NAME)"),
    (r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$", "provider",
     "linear: anchored, one run then $ (_SAFE_OPTION)"),
    ("([a-z])[\u0300-\u036f]+", "provider",
     "linear: a run of marks is entered only from the letter before it; every position inside the run "
     "is not a letter and fails at once (_LATIN_MARKS, fold_text)"),
    (r"[^\s'\"<>]+", "provider",
     "linear: matched at one given position, one run and nothing after it (_URL_TAIL_RE, redact_urls)"),
    (r"\w", "provider",
     "constant: one character at one given position (_WORD_CHAR_RE, redact_urls)"),
    (r"[A-Za-z0-9+.\-]*\Z", "provider",
     "open: search() has no literal prefix (minimum width 0), so it tries every start of redact_urls' "
     "window, and a start that fails costs the distance to the next non-scheme character; a "
     "scheme-legal run broken once inside the window costs about r*r/2 for a run of r. Reported by "
     "lane-bounds-h for the board to number (redact_urls is lane S's function this round); put the "
     "id here when it has one (_SCHEME_RUN_RE)"),
    (r"^[\s\-]+", "provider",
     "linear: anchored at the start, one run and nothing after it (_LEADING_DASHES, clean_name)"),
    ("'^' + GENERATED_NAME_WORD.lower() + ' [0-9]+$'", "provider",
     "linear: anchored, literal prefix, one digit run then $ (_GENERATED_NAME)"),
    (r"[\s\x00-\x1f\x7f]+", "provider",
     "linear: one class run and nothing after it; sub resumes past each run (_CONTROL_WS)"),
    ("[\x00-\x1f\x7f-\x9f]", "user",
     "linear: one character class, no quantifier (_CONTROL_CHARS)"),
    (r"^([A-Za-z][A-Za-z0-9+.\-]*):(.*)$", "user",
     "linear: anchored; the scheme run cannot hold ':' so it backs off at most once over its length, "
     "and (.*)$ under DOTALL reaches the end at once (_SCHEME_RE, _SOURCE_SCHEME_RE)"),
    (r"[/?#]", "user", "linear: one character class (_AUTHORITY_END)"),
    (r"[:\[\]]", "user", "linear: one character class (_BARE_HOST_CHARS)"),
    (r"^[0-9]+$", "user", "linear: anchored, one run then $ (_ASCII_DIGITS)"),
    ("[\u200b-\u200d\u2060\ufeff]", "user", "linear: one character class (_ZERO_WIDTH)"),
    (r"^\[(?=[0-9A-Fa-f.]*:)[0-9A-Fa-f:.]*(?:%25[A-Za-z0-9._~\-]+)?\]$", "user",
     "linear: fixed by lane-bounds-h (was two adjacent runs over one class, k*k): a lookahead over the "
     "class without ':' and ONE run, which nothing after it can make back off more than once a "
     "character (_IPV6_LITERAL)"),
    ("[\\s\ufeff]", "user", "linear: one character class (_URL_SPACE)"),
    (r"%(?![0-9A-Fa-f]{2})", "user",
     "linear: literal prefix '%', fixed-width lookahead (_BAD_ESCAPE)"),
    (r"^(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?\s*(?:([+-])(\d{2})(\d{2})|Z)?$", "provider",
     "linear: anchored match, fixed-width digit groups; the only run is \\s*, which a digit cannot "
     "extend, so it backs off at most once over its length on each of at most 8 ways through the "
     "three optional groups (_XMLTV_TIME)"),
    (r"[\s!-/:-@\[-`{-~]+", "provider",
     "linear: one class run and nothing after it (_PUNCT, search_key)"),
    (r"[\s!-)\,-/:-@\[-`{-~]+", "provider",
     "linear: one class run and nothing after it (_ID_PUNCT, the id and EPG name keys)"),
    (r"\((?:\d{3,4}p|sd|hd|fhd|uhd|4k|h\.?26[45])\)"
     r"|\[\s*not\s*24\s*[-/]?\s*7\s*\]"
     r"|\[\s*geo[\s-]*blocked\s*\]", "provider",
     "linear: every alternative opens with a literal '(' or '['; its \\s* runs are separated by "
     "literals they cannot hold, so each backs off at most once over its own length, and a "
     "whitespace run follows only one bracket start; the text is a name already cut to "
     "M3U_MAX_NAME or EPG_MAX_DISPLAY_NAME (_EPG_NAME_NOISE)"),
    (r'\s*([A-Za-z0-9_.\-]+)="([^"]*)"', "provider",
     "linear: matched at parse_attrs' position only, which moves past each match and stops at the "
     "first failure; the key run cannot hold '=' and the value run cannot hold '\"' (_ATTR_QUOTED)"),
    (r'\s*([A-Za-z0-9_.\-]+)=([^\s,"]+)', "provider",
     "linear: as _ATTR_QUOTED; the value run has nothing after it (_ATTR_BARE)"),
    (r"^[A-Za-z][A-Za-z0-9+.\-]*://([^/?#]*)", "user",
     "linear: anchored; the scheme run cannot hold ':' and the authority run has nothing after it "
     "(host_port_of)"),
    (r"\s*(-?\d+(?:\.\d+)?)?", "provider",
     "linear: matched at the start of the #EXTINF body, disjoint runs, one optional fraction "
     "(parse_extinf)"),
    (r"[.:]", "user", "linear: one character class (looks_like_host)"),
    (r"[?#].*$", "user",
     "linear: charset prefix, then .* under DOTALL reaches the end and $ holds there; one match "
     "(validate_source_url's file branch)"),
    (r"[0-9]{1,7}", "user", "linear: bounded quantifier (the channel-number override)"),
    (r"^--[a-z0-9][a-z0-9-]*(=.*)?$", "user",
     "linear: anchored; the name run cannot hold '=', and .* stops at a line break and backs off "
     "at most once to $ (MPV_ARG_RE, the user's own mpvArgs)"),
    (r"-(add|append|set|pre|clr|del|remove|toggle)$", "user",
     "linear: literal prefix '-', a fixed set of words then $ at each one (MPV_LIST_SUFFIX_RE)"),
    (r"-[0-9a-f]{8}\Z", "own",
     "linear: a bounded quantifier, so each start search() tries costs at most 9 steps; the text is "
     "a file name in the plugin's own cache folder (_TEMP_SUFFIX, is_stale_temp_name, D-SRC-60)"),
    (r"[0-9a-f]{8}\Z", "own",
     "linear: match() at the start only, a bounded quantifier; a file name in the plugin's own logo "
     "folder (_LOGO_NAME, the ceiling's sweep of unnamed files, D-LOGO-18)"),
]


def pattern_key(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.unparse(node)


def scan(paths):
    """-> (sites, problems): every regex call as (path, line, key)."""
    sites, problems = [], []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source, filename=path)
        rel = os.path.relpath(path, ROOT)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "re":
                problems.append("%s:%d: `from re import` hides a regex call from this guard" % (rel, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "re" and alias.asname not in (None, "re"):
                        problems.append("%s:%d: `import re as %s` hides a regex call from this guard"
                                        % (rel, node.lineno, alias.asname))
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and isinstance(node.func.value, ast.Name) and node.func.value.id == "re"
                  and node.func.attr in CALLS):
                if not node.args:
                    problems.append("%s:%d: re.%s with no positional pattern" % (rel, node.lineno, node.func.attr))
                    continue
                sites.append((rel, node.lineno, pattern_key(node.args[0])))
    return sites, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--helper-dir", default=os.path.join(ROOT, "bin", "helper"),
                        help="the directory of helper parts to scan (default: bin/helper)")
    args = parser.parse_args(argv)
    paths = sorted(os.path.join(args.helper_dir, name) for name in os.listdir(args.helper_dir)
                   if name.endswith(".py") and not name.startswith("."))
    if not paths:
        print("helper regex guard: no helper parts under %s" % args.helper_dir)
        return 1
    sites, problems = scan(paths)
    reviewed = {}
    for pattern, reads, verdict in REVIEWED:
        if pattern in reviewed:
            problems.append("REVIEWED lists %r twice" % pattern)
        if reads not in ("provider", "user", "own"):
            problems.append("REVIEWED %r: what it reads must be provider, user or own" % pattern)
        if not (verdict.startswith("linear: ") or verdict.startswith("constant: ")
                or verdict.startswith("open: ")):
            problems.append("REVIEWED %r: a verdict is `linear: why`, `constant: why` or `open: what and its id`" % pattern)
        reviewed[pattern] = (reads, verdict)
    found = set()
    for rel, line, key in sites:
        if key not in reviewed:
            problems.append("%s:%d: unreviewed regex %r -- add it to REVIEWED in scripts/check-helper-regex.py "
                            "with what it reads and why its cost is linear (or the defect id that holds it)"
                            % (rel, line, key))
        found.add(key)
    for pattern in reviewed:
        if pattern not in found:
            problems.append("REVIEWED holds %r, which no helper part compiles any more" % pattern)
    opened = [(pattern, reads, verdict) for pattern, (reads, verdict) in reviewed.items()
              if verdict.startswith("open") and pattern in found]
    for pattern, reads, verdict in opened:
        print("helper regex guard: OPEN on %s text: %r -- %s" % (reads, pattern, verdict))
    for problem in problems:
        print("helper regex guard: %s" % problem)
    print("helper regex guard: %d regex call(s) in %d part(s), %d pattern(s) reviewed, %d open, %d problem(s)"
          % (len(sites), len(paths), len(found & set(reviewed)), len(opened), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
