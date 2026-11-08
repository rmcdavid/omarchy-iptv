#!/usr/bin/env python3
"""Print a URL, or text holding URLs, the way the SHIPPING helper would.

F-HARNESS-96 and F-HARNESS-97. Three harness printers cut a URL down to its
host with their own patterns, and each got a shape wrong: run.sh's
`source_label` could not cross an `@` in a password and kept a `;sid=`
parameter, the chno scenarios' `url_context` stopped at the `@` and so printed
the username and password, and the live-rewind spike printed urllib's netloc,
userinfo included. Rule 12: a printer that reimplements the redaction grades
its own copy. This one CALLS the helper's `redact_urls`, the function every
helper sink uses, so a harness line says what a shipped line would, and a
later fix to that function reaches the harness without an edit here.

  helper_redact.py label   the URL on stdin as scheme://host, "local file",
                           "(not one URL)" or "(none)"
  helper_redact.py host    the host alone of the URL on stdin, "" for none
  helper_redact.py text    stdin to stdout, every URL as scheme://host

The URL arrives on STDIN, never as an argument: an argument sits in the
world-readable /proc/<pid>/cmdline while this runs (rule 5's argv sink,
F-HARNESS-98's shape), and the URL may carry the provider's credentials.

The helper is imported with `sys.dont_write_bytecode` set, so the import
writes no bin/__pycache__ into the tree (CLAUDE.md "Never touch").
OMARCHY_IPTV_HARNESS_HELPER points it at another helper stub (rule 11: grade
an older tree's redaction the same way).
"""

import importlib.machinery
import importlib.util
import os
import re
import sys

HELPER = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "bin", "omarchy-iptv"))
SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://")
WHITESPACE = re.compile(r"\s")
_MODULE = []


def helper():
    """The shipping helper, imported once."""
    if not _MODULE:
        sys.dont_write_bytecode = True
        path = os.environ.get("OMARCHY_IPTV_HARNESS_HELPER") or HELPER
        loader = importlib.machinery.SourceFileLoader("omarchy_iptv_harness_helper", path)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[loader.name] = module
        loader.exec_module(module)
        _MODULE.append(module)
    return _MODULE[0]


def redact(text):
    """`text` with every URL in it as scheme://host (the helper's R12)."""
    return helper().redact_urls(text or "")


def label(url):
    """How the harness names a source: "(none)", "local file", "(not one
    URL)" for text holding whitespace (no source URL does: both validators
    refuse it), or the redacted scheme://host. The whole URL is one run, so
    the redactor replaces all of it; never split what it prints, because
    its withheld marker holds a space."""
    if not url:
        return "(none)"
    if WHITESPACE.search(url):
        return "(not one URL)"
    match = SCHEME.match(url)
    if match is None or match.group(1).lower() == "file":
        return "local file"
    return redact(url)


def host(url):
    """The host the redactor prints for `url` (its withheld marker included),
    "" when `url` is not a scheme://host URL (a file URL has no host)."""
    if not url or WHITESPACE.search(url):
        return ""
    match = SCHEME.match(url)
    if match is None or match.group(1).lower() == "file":
        return ""
    printed = redact(url)
    return printed.split("://", 1)[1] if "://" in printed else ""


def main(argv):
    if argv == ["label"]:
        print(label(sys.stdin.read()))
        return 0
    if argv == ["host"]:
        print(host(sys.stdin.read()))
        return 0
    if argv == ["text"]:
        sys.stdout.write(redact(sys.stdin.read()))
        return 0
    sys.stderr.write("usage: helper_redact.py label|host|text (input on stdin)\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
