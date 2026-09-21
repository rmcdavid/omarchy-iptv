#!/usr/bin/env python3
# scripts/check-marketplace-capabilities.py -- refuse any string the Omarchy
# marketplace security baseline would read as a capability this plugin does
# not have.
#
# WHY THIS EXISTS.
# The marketplace runs a deterministic scan over every submitted commit and
# rescans on listing updates. It parses shell-like files into command
# sequences and cannot tell a quoted message from an executed line. Two
# message strings in developer tooling were therefore reported as
# capabilities this plugin has never had: a lint hint naming the package that
# provides qmllint, and a QA note explaining why the missing-player case uses
# a PATH-shadowed stub. Both were arguments to printf-only helpers. Neither
# was executed. Neither script is reachable from manifest.json. Rewording
# them moved the scan outcome from review-required to passed.
#
# ANY capability at all -- not a finding, just a capability -- makes the
# outcome review-required. The margin is zero, so this check is zero
# tolerance and has no allowlist.
#
# CLAUDE.md rule 13. Both reworded sites carry a comment saying why the
# phrasing is load-bearing, and a comment is a NAME, not a call: nothing
# verified it. If a future edit writes a package verb or an elevation verb
# into a log message, the listing drops back to manual review on the next
# scan and nobody connects the two. This makes that join a call.
#
# WHAT IT DOES. It reproduces, from the transcribed data in
# scripts/marketplace-capability-patterns.json:
#   * the scan SURFACE  (which paths the marketplace reads at all), and
#   * the command CAPABILITY patterns it applies to them.
# Respecting the surface is half the point. docs/ is an excluded directory
# and .md is not a scanned extension, so the many prose lines under docs/
# that discuss elevation are out of scope; flagging them would make this
# check noise and noise gets muted. Comments are not commands either: the
# marketplace strips trailing comments and drops comment-only lines, and so
# does this.
#
# WHAT IT DOES NOT DO is listed in the data file under "_notPorted", and
# printed on every run, so this never implies coverage it lacks.
#
# Python 3 standard library only (CLAUDE.md rule 3). ASCII only (rule 8).

import argparse
import json
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATTERNS = os.path.join(SCRIPT_DIR, "marketplace-capability-patterns.json")

TRAILING_BACKSLASH = re.compile(r"\\\s*$")
REMOTE_URL = re.compile(
    r"""(?:https?|git|ssh)://[^\s"'`|;&)]+|git@[^\s:"'`|;&)]+:[^\s"'`|;&)]+""",
    re.IGNORECASE,
)
URL_TRIM = re.compile(r"(?:[),;]+|[.:!?]+$)")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class Patterns(object):
    """The transcribed baseline, compiled once."""

    def __init__(self, data):
        self.data = data
        scope = data["scope"]
        self.excluded_directories = set(scope["excludedDirectories"])
        self.scanned_extensions = set(scope["scannedExtensions"])
        self.binary_asset_extensions = set(scope["binaryAssetExtensions"])
        self.root_readme = re.compile(scope["rootReadme"], re.IGNORECASE)
        self.setup_named = re.compile(scope["setupNamedBasename"], re.IGNORECASE)
        self.comment_only = re.compile(scope["commentOnly"])
        self.continued = re.compile(scope["lineContinued"])
        self.inline_comment = re.compile(scope["stripInlineComment"])
        self.fence_open = re.compile(scope["readmeFenceOpen"], re.IGNORECASE)
        self.fence_close = re.compile(scope["readmeFenceClose"])
        self.heading = re.compile(scope["readmeHeading"])
        self.fence_exempt = re.compile(scope["readmeFenceExemptContext"], re.IGNORECASE)
        self.submission_repository = str(data.get("submissionRepository", "")).lower()

        self.command_rules = []
        for rule in data["commandCapabilities"]:
            self.command_rules.append({
                "id": rule["id"],
                "title": rule["title"],
                "any": [re.compile(p, re.IGNORECASE) for p in rule.get("any", [])],
                "all": [re.compile(p, re.IGNORECASE) for p in rule.get("all", [])],
                "submission": bool(rule.get("requiresSubmissionRepositoryUrl")),
            })

        self.file_rules = []
        for rule in data["fileCapabilities"]:
            self.file_rules.append({
                "id": rule["id"],
                "title": rule["title"],
                "path": re.compile(rule["path"], re.IGNORECASE) if rule.get("path") else None,
                "basename": (re.compile(rule["pathBasename"], re.IGNORECASE)
                             if rule.get("pathBasename") else None),
            })

        self.privilege = self._compile_privilege(data["privilegeBoundary"])

    def _compile_privilege(self, spec):
        # The upstream helper composes its regular expressions from named
        # fragments and then strips the phrases that mean the opposite of
        # what they contain, so that "it is not needed" does not read as a
        # request. Expansion is longest-token-first: the wider token holds
        # the narrower one, and expanding the narrower one first would eat
        # part of the wider one.
        order = [
            "EXPLICITNEGATIVELIST", "NOTUSEDPREDICATE", "NOUSEPREDICATE",
            "NEGATIVEPREDICATE", "TERMINAL", "LIST", "NAMES",
        ]
        values = {
            "EXPLICITNEGATIVELIST": spec["explicitNegativeList"],
            "NOTUSEDPREDICATE": spec["notUsedPredicate"],
            "NOUSEPREDICATE": spec["noUsePredicate"],
            "NEGATIVEPREDICATE": spec["negativePredicate"],
            "TERMINAL": spec["terminal"],
            "LIST": spec["list"],
            "NAMES": spec["names"],
        }

        def expand(text):
            for token in order:
                text = text.replace(token, values[token])
            return text

        return {
            "id": spec["id"],
            "title": spec["title"],
            "strip": [re.compile(expand(p), re.IGNORECASE) for p in spec["strip"]],
            "detect": re.compile(expand(spec["detect"]), re.IGNORECASE),
        }

    def is_root_readme(self, path):
        return "/" not in path and bool(self.root_readme.match(path))

    def is_binary_asset_path(self, path):
        basename = path.replace("\\", "/").split("/")[-1].lower()
        at = basename.rfind(".")
        return at > 0 and basename[at:] in self.binary_asset_extensions

    def in_excluded_directory(self, path):
        parts = path.lower().split("/")
        return any(part in self.excluded_directories for part in parts[:-1])

    def is_scan_path(self, path):
        # Port of isSecurityScanPath in scripts/security-baseline-scope.mjs.
        normalized = path.replace("\\", "/")
        if not normalized or normalized.startswith("/") or "\0" in normalized:
            return False
        if self.is_root_readme(normalized):
            return True
        if self.in_excluded_directory(normalized):
            return False
        parts = normalized.lower().split("/")
        basename = parts[-1]
        at = basename.rfind(".")
        extension = basename[at:] if at > 0 else ""
        if extension in self.scanned_extensions:
            return True
        if self.is_binary_asset_path(normalized):
            return False
        if parts[0] in ("bin", "scripts"):
            return at < 0
        return bool(self.setup_named.search(basename))


def tracked_files(root):
    """Every tracked blob, with its mode, exactly as the snapshot sees it."""
    out = subprocess.run(
        ["git", "-C", root, "ls-files", "-s", "-z"],
        check=True, stdout=subprocess.PIPE,
    ).stdout
    entries = []
    for record in out.split(b"\0"):
        if not record:
            continue
        head, _, path = record.partition(b"\t")
        mode = head.split(b" ")[0].decode("ascii")
        entries.append((mode, path.decode("utf-8")))
    return entries


def read_text(path):
    """Return (text, is_binary). The marketplace refuses to parse a blob it
    reads as binary, and so do we."""
    with open(path, "rb") as handle:
        raw = handle.read()
    if b"\0" in raw:
        return "", True
    try:
        return raw.decode("utf-8"), False
    except UnicodeDecodeError:
        return "", True


def entry_points(root):
    manifest = os.path.join(root, "manifest.json")
    if not os.path.exists(manifest):
        return set()
    try:
        with open(manifest, "r") as handle:
            data = json.load(handle)
    except (ValueError, OSError):
        return set()
    points = data.get("entryPoints") or {}
    if not isinstance(points, dict):
        return set()
    return set(
        value for value in points.values()
        if isinstance(value, str) and value and not value.startswith("/") and ".." not in value
    )


def scan_surface(root, patterns):
    """The paths the marketplace actually reads, in its own order of
    reasons: an entry point is read wherever it lives, an excluded directory
    is skipped, and anything executable or extensionless is read even when
    its extension would not have qualified it."""
    forced = entry_points(root)
    surface = []
    for mode, path in tracked_files(root):
        if mode == "120000":
            continue
        is_forced = path in forced
        if patterns.in_excluded_directory(path) and not is_forced:
            continue
        basename = path.split("/")[-1]
        extensionless = "." not in basename
        if not (patterns.is_scan_path(path) or mode == "100755" or extensionless or is_forced):
            continue
        surface.append((mode, path))
    return surface


def logical_commands(patterns, text, path, line_offset=0):
    """Port of logicalCommands: physical lines are joined into one logical
    command across a trailing backslash and across a trailing pipe or
    boolean operator. The line number reported is the FIRST line of the
    logical command, which is what the marketplace cites."""
    commands = []
    buffered = ""
    start = 1
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(lines):
        if not buffered:
            start = index + 1
        continued = bool(patterns.continued.search(line))
        piece = TRAILING_BACKSLASH.sub("", line).strip()
        buffered = (buffered + " " + piece) if buffered else piece
        if not continued:
            commands.append((start + line_offset, buffered.strip()))
            buffered = ""
    if buffered:
        commands.append((start + line_offset, buffered.strip()))
    return commands


def command_sequence(patterns, text, path, line_offset=0):
    """logicalCommands minus blank lines and comment-only lines. A root
    README is exempt from the comment filter upstream -- its prose is read
    as commands too -- so it is exempt here."""
    readme = patterns.is_root_readme(path)
    sequence = []
    for line, command in logical_commands(patterns, text, path, line_offset):
        if not command:
            continue
        if not readme and patterns.comment_only.match(command.strip()):
            continue
        sequence.append((line, command))
    return sequence


def readme_shell_fences(patterns, text, path):
    """Port of shellFenceFiles: a shell-tagged fenced block in the root
    README is read as a shell file, unless the heading or the adjacent
    paragraph marks the section as development or testing. Returns
    (line_offset, body) pairs; the offset makes the reported line the real
    line of the README rather than the line within the fence."""
    if not patterns.is_root_readme(path):
        return []
    fences = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    section = ""
    paragraph = []
    previous = []
    index = 0
    while index < len(lines):
        heading = patterns.heading.match(lines[index])
        if heading:
            section = heading.group(1).strip().lower()
            paragraph = []
            previous = []
            index += 1
            continue
        opening = patterns.fence_open.match(lines[index])
        if not opening:
            if lines[index].strip():
                paragraph.append(lines[index])
            elif paragraph:
                previous = paragraph
                paragraph = []
            else:
                previous = []
            index += 1
            continue
        marker = opening.group(1)[0]
        minimum = len(opening.group(1))
        body = []
        body_start = index + 2
        index += 1
        while index < len(lines):
            closing = patterns.fence_close.match(lines[index])
            if closing and closing.group(1)[0] == marker and len(closing.group(1)) >= minimum:
                break
            body.append(lines[index])
            index += 1
        context = section + "\n" + "\n".join(paragraph if paragraph else previous)
        if not patterns.fence_exempt.search(context):
            fences.append((body_start - 1, "\n".join(body)))
        paragraph = []
        previous = []
        index += 1
    return fences


def remote_repositories(patterns, text):
    """Every GitHub repository a command names, as owner/name."""
    found = []
    for match in REMOTE_URL.finditer(text):
        raw = URL_TRIM.sub("", match.group(0).strip("\"'"))
        slug = ""
        lowered = raw.lower()
        if lowered.startswith("https://github.com/"):
            parts = [p for p in raw[len("https://github.com/"):].split("/") if p]
            if len(parts) >= 2:
                slug = (parts[0] + "/" + re.sub(r"\.git$", "", parts[1])).lower()
        elif lowered.startswith("https://raw.githubusercontent.com/"):
            parts = [p for p in raw[len("https://raw.githubusercontent.com/"):].split("/") if p]
            if len(parts) >= 2:
                slug = (parts[0] + "/" + parts[1]).lower()
        found.append(slug)
    return found


def uses_only_submission_repository(patterns, text):
    expected = patterns.submission_repository
    slugs = remote_repositories(patterns, text)
    if not expected or not slugs:
        return False
    return all(slug == expected for slug in slugs)


def invokes_privilege_boundary(patterns, text):
    value = patterns.inline_comment.sub("", text).strip()
    for stripper in patterns.privilege["strip"]:
        value = stripper.sub("", value)
    return bool(patterns.privilege["detect"].search(value))


def command_hits(patterns, text):
    """Every capability the transcribed patterns read in one command."""
    hits = []
    for rule in patterns.command_rules:
        if rule["any"] and not any(p.search(text) for p in rule["any"]):
            continue
        if rule["all"] and not all(p.search(text) for p in rule["all"]):
            continue
        if not rule["any"] and not rule["all"]:
            continue
        if rule["submission"] and not uses_only_submission_repository(patterns, text):
            continue
        hits.append((rule["id"], rule["title"]))
    if invokes_privilege_boundary(patterns, text):
        hits.append((patterns.privilege["id"], patterns.privilege["title"]))
    return hits


def snippet(text):
    return CONTROL.sub(" ", text)[:300].strip()


def scan(root, patterns):
    findings = []
    files = 0
    commands = 0
    for mode, path in scan_surface(root, patterns):
        absolute = os.path.join(root, path)
        if not os.path.isfile(absolute):
            continue
        text, binary = read_text(absolute)
        if binary:
            if mode == "100755":
                findings.append((path, 1, "bundled-executable-binary",
                                 "Bundled executable binary", "executable binary blob"))
            continue
        files += 1
        basename = path.split("/")[-1]
        for rule in patterns.file_rules:
            if rule["basename"] and rule["basename"].search(basename):
                findings.append((path, 1, rule["id"], rule["title"], "path names this capability"))
            if rule["path"] and rule["path"].search(path):
                findings.append((path, 1, rule["id"], rule["title"], "path names this capability"))
        sources = [(0, text)] + readme_shell_fences(patterns, text, path)
        for offset, body in sources:
            for line, command in command_sequence(patterns, body, path, offset):
                commands += 1
                for identifier, title in command_hits(patterns, command):
                    findings.append((path, line, identifier, title, snippet(command)))
    seen = set()
    unique = []
    for finding in findings:
        key = (finding[0], finding[1], finding[2])
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    unique.sort(key=lambda item: (item[0], item[1], item[2]))
    return unique, files, commands


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fail if a tracked file reintroduces a string the Omarchy "
                    "marketplace security baseline reads as a capability.")
    parser.add_argument("--root", default=os.path.dirname(SCRIPT_DIR),
                        help="repository root (default: the parent of scripts/)")
    parser.add_argument("--patterns", default=DEFAULT_PATTERNS,
                        help="the transcribed baseline (default: beside this script)")
    parser.add_argument("--min-files", type=int, default=1,
                        help="fail if fewer than this many files were read")
    parser.add_argument("--verbose", action="store_true",
                        help="print the scan surface")
    args = parser.parse_args(argv)

    try:
        with open(args.patterns, "r") as handle:
            patterns = Patterns(json.load(handle))
    except (OSError, ValueError, KeyError) as error:
        sys.stderr.write("cannot read the transcribed baseline %s: %s\n"
                         % (args.patterns, error))
        return 2

    root = os.path.abspath(args.root)
    findings, files, commands = scan(root, patterns)

    print("marketplace capability scan: %d file(s), %d command(s), %d capability hit(s)"
          % (files, commands, len(findings)))

    if args.verbose:
        for mode, path in scan_surface(root, patterns):
            print("  surface %s %s" % (mode, path))

    if files < args.min_files:
        print("")
        print("FAIL the scan read %d file(s), expected at least %d. A scan that "
              "reads nothing is green for the wrong reason." % (files, args.min_files))
        return 1

    if not findings:
        return 0

    print("")
    print("These strings would be read as capabilities by the marketplace scan.")
    print("Any capability at all moves the listing from passed to review-required,")
    print("and the rescan runs on every listing update.")
    print("")
    for path, line, identifier, title, text in findings:
        print("  %s:%d" % (path, line))
        print("      capability: %s -- %s" % (identifier, title))
        print("      reads as:   %s" % text)
    print("")
    print("Reword the message so it carries the same information without the verb,")
    print("or, if the capability is real, disclose it on the submission issue.")
    print("See docs/MARKETPLACE-SUBMISSION.md.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
