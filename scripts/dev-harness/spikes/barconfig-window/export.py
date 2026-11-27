#!/usr/bin/env python3
"""scripts/dev-harness/spikes/barconfig-window/export.py -- the plugin under
test: a dev commit's ALLOWLIST export, unchanged, as the only commit of a
scratch upstream the rig installs from.

  export.py REPO WORK DEVREF

REPO is this repository (read only: DEVREF is fetched out of it into a
scratch repository). WORK is a folder this creates (it must not exist).
The export is scripts/release.py's own build_tree over ALLOWLIST (imported
from REPO, as ../codebehind-reload/candidates.py imports it), committed with
no parent, and cloned bare to WORK/upstream.git, whose `main` is that
commit. Unlike candidates.py's C1 it carries no mark and no version change:
the files are DEVREF's bytes. Prints one JSON object: the upstream's path,
the export commit, the allowlist's length and Service.qml's sha256, which
run.sh holds the logging patch to.
Python 3 standard library only; every subprocess is an argv list.
"""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys

IDENTITY = {"GIT_AUTHOR_NAME": "dh15m", "GIT_AUTHOR_EMAIL": "dh15m@example.invalid",
            "GIT_COMMITTER_NAME": "dh15m", "GIT_COMMITTER_EMAIL": "dh15m@example.invalid",
            "GIT_AUTHOR_DATE": "2026-11-27T12:00:00Z", "GIT_COMMITTER_DATE": "2026-11-27T12:00:00Z"}


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd] + list(args), check=True, env=dict(os.environ, **IDENTITY),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()


def main(argv):
    if len(argv) != 4:
        raise SystemExit("usage: export.py REPO WORK DEVREF")
    repo, work, devref = os.path.abspath(argv[1]), os.path.abspath(argv[2]), argv[3]
    if os.path.exists(work):
        raise SystemExit("export.py: %s exists; refusing to reuse it" % work)
    os.makedirs(work, mode=0o700)
    src = os.path.join(work, "src")
    dev = git(repo, "rev-parse", "--verify", devref + "^{commit}").strip()
    subprocess.run(["git", "init", "-q", "-b", "scratch", src], check=True)
    git(src, "fetch", "-q", "--no-tags", repo, "%s:refs/heads/dev" % dev)
    if git(src, "rev-parse", "dev").strip() != dev:
        raise SystemExit("export.py: the fetched ref is not %s" % dev)
    spec = importlib.util.spec_from_file_location("release", os.path.join(repo, "scripts", "release.py"))
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    tree = release.build_tree(src, dev)
    if release.tree_paths(src, tree) != set(release.ALLOWLIST):
        raise SystemExit("export.py: the export's tree is not the allowlist")
    message = ("dh15m: %s's ALLOWLIST export (barconfig-window scratch build)\n\nscripts/release.py's build_tree; "
               "%d allowlisted files, unchanged.\n" % (dev, len(release.ALLOWLIST)))
    commit = git(src, "commit-tree", tree, "-m", message).strip()
    git(src, "update-ref", "refs/heads/main", commit)
    upstream = os.path.join(work, "upstream.git")
    subprocess.run(["git", "clone", "-q", "--bare", "--single-branch", "--branch", "main", src, upstream], check=True)
    service = subprocess.run(["git", "-C", src, "show", "%s:Service.qml" % commit], check=True,
                             stdout=subprocess.PIPE).stdout
    print(json.dumps({"upstream": upstream, "commit": commit, "dev": dev, "allowlist": len(release.ALLOWLIST),
                      "serviceSha256": hashlib.sha256(service).hexdigest()}))


if __name__ == "__main__":
    main(sys.argv)
