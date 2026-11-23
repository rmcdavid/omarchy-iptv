#!/usr/bin/env python3
"""Run qmllint over one QML file and count what it finds from its `--json`
report (F-GATE-16).

The gate used to count the lines of qmllint's text output, and qmllint
6.12.0's text output is only a trailing run of what it finds (Guide.qml 385
lines of the 649 entries its JSON lists, measured 2026-10-31), so every
printed count read low. The JSON report is whole.

    qmllint-count.py [--list] <qmllint> [-I <dir>]... <file.qml>

Prints one line, `<errors> <warnings> <model-members>`:

  errors         entries qmllint types as an error, plus one when qmllint's
                 exit status is not 0 and no entry is typed so. qmllint types
                 a syntax error as a warning and says so only by its status
                 (measured on 6.12.0), so the status is what fails a file.
  warnings       entries typed as a warning, the model-members among them.
  model-members  the warnings that say a member was not found on type
                 "Model": qmllint reads no ES module's exports (D-REL-5), so
                 every Model member in QML draws one. check-model-members.py
                 is what judges those; they are counted apart so the rest
                 stays comparable with the gate's baseline.

With `--list` every entry follows, one per line, as
`<type>: <file>:<line>:<column>: <message> [<id>]`.

Exit status: 0 when the report was read (whatever it counted), 2 when
qmllint could not be run or its report is not the shape this reads, with one
sentence on stderr. The gate fails a file on either an error count above 0
or a status that is not 0. Launches qmllint by argv, with a time limit.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

TIMEOUT_S = 120
ERROR_TYPES = ("error", "critical", "fatal")
MODEL_MEMBER = 'not found on type "Model"'


def read_report(text, status):
    """(errors, warnings, model_members, entries) from the text of a
    qmllint `--json` report and qmllint's exit status. Raises ValueError
    when the text is not a report."""
    document = json.loads(text)
    if not isinstance(document, dict) or not isinstance(document.get("files"), list):
        raise ValueError("no `files` list")
    entries = []
    for one in document["files"]:
        if not isinstance(one, dict) or not isinstance(one.get("warnings"), list):
            raise ValueError("a file entry with no `warnings` list")
        for entry in one["warnings"]:
            if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
                raise ValueError("an entry with no `type`")
            entries.append((str(one.get("filename") or ""), entry))
    errors = sum(1 for _, e in entries if e["type"].lower() in ERROR_TYPES)
    warnings = sum(1 for _, e in entries if e["type"].lower() == "warning")
    members = sum(1 for _, e in entries
                  if e["type"].lower() == "warning" and e.get("id") == "missing-property"
                  and MODEL_MEMBER in str(e.get("message") or ""))
    if status != 0 and errors == 0:
        errors = 1
    return errors, warnings, members, entries


def entry_line(filename, entry):
    return "%s: %s:%s:%s: %s [%s]" % (entry["type"], filename, entry.get("line", "?"), entry.get("column", "?"),
                                      str(entry.get("message") or "").replace("\n", " "), entry.get("id") or "?")


def view_of(service):
    """(text, origins, keep) for --service: the service's inline view
    (scripts/service_files.py), where each of its lines comes from, and the
    names beside Service.qml a lint of the view must still see -- every
    entry of its directory but Service.qml and the code-behinds the view
    already holds. Raises service_files.ServiceFilesError or OSError."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import service_files  # the service's files and its inline view (D-REL-14)
    text, origins = service_files.service_view(service)
    names = service_files.service_names(service)
    folder = os.path.dirname(os.path.abspath(service))
    keep = sorted(name for name in os.listdir(folder) if name not in names)
    return text, origins, keep


def placed(filename, entry, staged, service, origins):
    """An entry on the staged view, named where its line stands: Service.qml
    or the code-behind the line comes from, at that file's line. Any other
    entry is returned as qmllint gave it."""
    if os.path.realpath(filename) != os.path.realpath(staged):
        return filename, entry
    line = entry.get("line")
    if isinstance(line, int) and 1 <= line <= len(origins):
        path, at = origins[line - 1]
        return path, dict(entry, line=at)
    return service, entry


def main(argv):
    args = list(argv[1:])
    listing = bool(args) and args[0] == "--list"
    if listing:
        args.pop(0)
    service_mode = bool(args) and args[0] == "--service"
    if service_mode:
        args.pop(0)
    if len(args) < 2:
        print("usage: qmllint-count.py [--list] [--service] <qmllint> [-I <dir>]... <file.qml>", file=sys.stderr)
        return 2
    origins = None
    if service_mode:
        service = args[-1]
        try:
            text, origins, keep = view_of(service)
        except Exception as exc:  # a refusal of the readers, or a file they could not read
            print("qmllint-count: the service's inline view could not be built (%s: %s)"
                  % (type(exc).__name__, exc), file=sys.stderr)
            return 2
    scratch = tempfile.mkdtemp(prefix="qmllint-count-")
    report = os.path.join(scratch, "report.json")
    stage = os.path.join(scratch, "view")
    try:
        if service_mode:
            # F-GATE-29: qmllint reads a code-behind as JavaScript and checks
            # its syntax alone (measured on 6.12.0: a block-scoped `var` and an
            # unknown name draw nothing), and it does not follow a script
            # import, so the bodies moved out of Service.qml are linted only
            # where they run: in the view, the one-file Service.qml, beside
            # the files it imports, as qmllint read it before the move.
            # A sibling QML type is resolved by the folder's own listing,
            # which skips a symlinked .qml file (measured on 6.12.0: `Helper
            # was not found` through a link, found as a copy), so a regular
            # .qml file and a qmldir are copied and everything else is linked,
            # a symlink in the folder staying a symlink as qmllint met it there.
            os.mkdir(stage, 0o700)
            folder = os.path.dirname(os.path.abspath(service))
            for name in keep:
                source = os.path.join(folder, name)
                if (name.endswith(".qml") or name == "qmldir") and os.path.isfile(source) and not os.path.islink(source):
                    shutil.copyfile(source, os.path.join(stage, name))
                else:
                    os.symlink(source, os.path.join(stage, name))
            staged = os.path.join(stage, os.path.basename(service))
            with open(staged, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            args[-1] = staged
        try:
            done = subprocess.run([args[0], "--json", report] + args[1:], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print("qmllint-count: could not run qmllint (%s)" % type(exc).__name__, file=sys.stderr)
            return 2
        try:
            with open(report, encoding="utf-8") as handle:
                errors, warnings, members, entries = read_report(handle.read(), done.returncode)
        except (OSError, ValueError) as exc:
            print("qmllint-count: qmllint's report could not be read (%s; qmllint exited %d)"
                  % (exc, done.returncode), file=sys.stderr)
            return 2
        if service_mode:
            entries = [placed(filename, entry, staged, service, origins) for filename, entry in entries]
    finally:
        # Nothing here recurses: the stage holds the view, copied files and
        # symlinks, each unlinked as a name, so no link is ever followed.
        if os.path.isdir(stage) and not os.path.islink(stage):
            for name in os.listdir(stage):
                os.unlink(os.path.join(stage, name))
            os.rmdir(stage)
        for name in os.listdir(scratch):
            os.unlink(os.path.join(scratch, name))
        os.rmdir(scratch)
    print("%d %d %d" % (errors, warnings, members))
    if listing:
        for filename, entry in entries:
            print(entry_line(filename, entry))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
