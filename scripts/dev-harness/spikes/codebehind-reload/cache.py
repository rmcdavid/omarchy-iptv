#!/usr/bin/env python3
"""scripts/dev-harness/spikes/codebehind-reload/cache.py -- what Qt's QML disk
cache holds for the plugin's files, read off the cache files themselves.

  cache.py CACHE_ROOT CAND_JSON PLUGIN_DIR [--dirs]

CACHE_ROOT is searched for cache files (*.qmlc, *.jsc, *.mjsc): the arm's
QML_DISK_CACHE_PATH folder, or with RIG_QMLCACHE=xdg or home the decoy
HOME's .cache, where the shell's own default puts them. CAND_JSON is candidates.py's
output (the scratch upstream and the four builds). PLUGIN_DIR is the
installed plugin.

A cache file is named for the file it caches: the hex SHA-1 of that file's
local path, a dot, the file's suffix and a `c` (so Service.qml's is
<sha1>.qmlc, Service-player.js's <sha1>.jsc). Each one this maps to a
plugin file is printed with:
  saved     the cache file's modification time (ms, the rig's clock)
  stamp     the unit's sourceTimeStamp; -1 is Qt 6.12's content-hash mode,
            in which the unit is accepted on load while sourceChecksum is
            the checksum of the source as it then reads
            (qv4compileddata_p.h 1220-1231, 1635-1647: magic 0-7, version
            8-11, reserved 12-15, sourceTimeStamp 16-23, unitSize 24-27,
            sourceChecksum 28-43)
  checksum  sourceChecksum, and the build whose text it is the MD5 of
  disk      which build's text the file on disk is now
  code      which build's mark the unit's string table holds (UTF-16 or
            UTF-8): "C<n> <file>" for the marked files, the version for
            model/build.mjs; C0 is the build with no mark
  verdict   agrees (the checksum and the code name one build), POISONED
            (they differ and the checksum is the file on disk's, so the
            next load takes this unit: the code of one build under the
            checksum of another), or stale (the checksum is not the file on
            disk's, so the next load compiles again)
--dirs prints only the folders that hold cache files, one per line, for
run.sh's cache clear. Reads only; Python 3 standard library; every
subprocess is an argv list.
"""
import hashlib
import json
import os
import subprocess
import sys

SUFFIXES = (".qmlc", ".jsc", ".mjsc")
MARKED = ("Service.qml", "Service-pip.js", "Service-player.js", "Service-rewind.js", "Service-sources.js",
          "Guide.qml", "BarWidget.qml")
VERSIONS = {"C1": "0.99.0", "C2": "0.99.1", "C3": "0.99.2"}


def cache_files(root):
    out = []
    for top, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            if name.endswith(SUFFIXES):
                out.append(os.path.join(top, name))
    return out


def build_text(upstream, commit, rel):
    proc = subprocess.run(["git", "-C", upstream, "show", "%s:%s" % (commit, rel)],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return proc.stdout if proc.returncode == 0 else None


def has(data, text):
    return text.encode("utf-8") in data or text.encode("utf-16-le") in data


def code_build(data, rel, c0_version):
    base = os.path.basename(rel)
    if base in MARKED:
        got = [b for b in ("C1", "C2", "C3") if has(data, "%s %s" % (b, base))]
        if got:
            return "+".join(got)
        return "C0 (no mark)"
    if rel == "model/build.mjs":
        got = [b for b, v in VERSIONS.items() if has(data, '"%s"' % v) or has(data, v)]
        if c0_version and has(data, c0_version):
            got.insert(0, "C0")
        return "+".join(got) if got else "no version found"
    return "unmarked"


def main(argv):
    dirs_only = "--dirs" in argv
    args = [a for a in argv[1:] if a != "--dirs"]
    if len(args) != 3:
        raise SystemExit("usage: cache.py CACHE_ROOT CAND_JSON PLUGIN_DIR [--dirs]")
    root, cand_path, plugin = (os.path.abspath(a) for a in args)
    files = cache_files(root) if os.path.isdir(root) else []
    if dirs_only:
        for d in sorted({os.path.dirname(f) for f in files}):
            print(d)
        return
    cand = json.load(open(cand_path, encoding="utf-8"))
    upstream, commits = cand["upstream"], cand["commits"]
    c0_manifest = build_text(upstream, commits["C0"], "manifest.json")
    c0_version = json.loads(c0_manifest.decode("utf-8")).get("version") if c0_manifest else None
    by_hash = {}
    for top, dirs, names in os.walk(plugin):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in names:
            path = os.path.join(top, name)
            by_hash[hashlib.sha1(path.encode("utf-8")).hexdigest()] = os.path.relpath(path, plugin)
    folders = sorted({os.path.dirname(f) for f in files})
    print("    cache: %d file(s) under %s, in %s" % (
        len(files), root, ", ".join(folders) if folders else "no folder"))
    other = 0
    for path in files:
        stem = os.path.basename(path).split(".", 1)[0]
        rel = by_hash.get(stem)
        if rel is None:
            other += 1
            continue
        with open(path, "rb") as fh:
            data = fh.read()
        stamp = int.from_bytes(data[16:24], "little", signed=True)
        checksum = data[28:44].hex()
        texts = {}
        for build in ("C0", "C1", "C2", "C3"):
            if build in commits:
                text = build_text(upstream, commits[build], rel)
                if text is not None:
                    texts[build] = hashlib.md5(text).hexdigest()
        names = [b for b, h in texts.items() if h == checksum]
        try:
            disk = hashlib.md5(open(os.path.join(plugin, rel), "rb").read()).hexdigest()
        except OSError:
            disk = None
        disk_names = [b for b, h in texts.items() if h == disk] if disk else []
        code = code_build(data, rel, c0_version)
        sum_build = "+".join(names) if names else "no build's text"
        if disk is not None and checksum == disk:
            if code in ("unmarked", "no version found"):
                verdict = "the disk file's checksum (its code carries no mark to read)"
            else:
                verdict = "agrees" if code.split(" ")[0] in names else "POISONED"
        else:
            verdict = "stale (recompiled at the next load)"
        print("    %-24s saved %d  stamp %d  checksum %s.. = %s; disk %s; code %s: %s" % (
            rel, os.stat(path).st_mtime_ns // 1000000, stamp, checksum[:8], sum_build,
            "+".join(disk_names) if disk_names else ("absent" if disk is None else "no build's text"),
            code, verdict))
    print("    (%d other cache file(s): the root's own files and Qt's)" % other)


if __name__ == "__main__":
    main(sys.argv)
