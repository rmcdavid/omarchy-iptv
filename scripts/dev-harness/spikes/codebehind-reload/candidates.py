#!/usr/bin/env python3
"""scripts/dev-harness/spikes/codebehind-reload/candidates.py -- the three
builds the reload rig updates between, in a scratch upstream repository.

  candidates.py REPO WORK C0REF DEVREF

REPO is this repository (read only: two refs are fetched out of it). WORK is a
scratch folder this creates (it must not exist). C0REF is the released
artifact (local `main`, 1321aff, 0.20.0: one Service.qml); DEVREF is the dev
tree whose ALLOWLIST export is C1 (3200d22: Service.qml and four
code-behinds). Prints one JSON object: the three commits and the upstream
repository's path.

  C0  C0REF itself, as installs have it.
  C1  DEVREF's ALLOWLIST export, built by scripts/release.py's own
      build_tree and ALLOWLIST (imported from REPO), committed onto C0 with C0
      as its parent, the way release.py's build does (commit-tree -p main).
      The version is 0.99.0 in manifest.json and in
      Model.PLUGIN_VERSION (model/build.mjs), as release.py requires them
      equal, and each build carries an INERT MARK in every file the reload
      can mix, so what runs is read off the running objects rather than
      inferred: Service.qml's reloadMarks() returns its own mark and each
      code-behind's reloadMark() (Service-pip.js, Service-player.js,
      Service-rewind.js, Service-sources.js), and Guide.qml and BarWidget.qml
      carry a reloadMark property. C0 carries none: its absence is C0's mark.
  C2  C1 with a version change between two code-behind builds:
      0.99.1, the marks reading C2, and ONE function changed
      across Service.qml and a code-behind so that a mixed pair fails
      loudly -- Service-player.js's socketAttached is renamed
      socketAttachedLive and Service.qml's forwarder socketAttached() calls
      ServicePlayer.socketAttachedLive(). A C2 Service.qml over a C1
      Service-player.js, or the other way round, throws a TypeError on every
      call, and the service's `status` reply calls it. Only that pair: a C1
      Service-pip.js beside C2's other files runs, and reads as a mix only by
      its mark.
  C3  C2 with the version 0.99.2 and the marks reading C3, and nothing else
      changed: the LATER update a race arm publishes to ask whether an update
      that rewrites every marked file recovers a cache the race poisoned
      (run.sh's RIG_RECOVER=update; a C0 to C1 race takes C2 for it).

Each build carries true build stamps (D-REL-16): after its marks, bump()
runs scripts/build_stamps.py's own cut (imported from REPO, as release.py
is) against the build it updates from -- C1 against C0, C2 against C1, C3
against C2 -- so every runtime file a build changes carries that build's
version and model/build.mjs's BUILD_FILES says so, as a real cut's would.
C1 restamps all 26 runtime files (C0, 0.20.0, has no stamps); C2 and C3 the
seven files their marks change and build.mjs. So DEVREF must be a dev
commit that carries the stamps; an older one is refused, by name.

The upstream is a bare repository whose `main` starts at C0 and holds C1, C2
and C3 under refs/heads/art; publishing a build is `git update-ref refs/heads/main
<commit>` in it (run.sh's publish), which is what a release's push does to
origin's main. Nothing is pushed anywhere, and REPO is never written.
Python 3 standard library only; every subprocess is an argv list.
"""
import importlib.util
import json
import os
import subprocess
import sys

IDENTITY = {"GIT_AUTHOR_NAME": "reload-d", "GIT_AUTHOR_EMAIL": "reload-d@example.invalid",
            "GIT_COMMITTER_NAME": "reload-d", "GIT_COMMITTER_EMAIL": "reload-d@example.invalid",
            "GIT_AUTHOR_DATE": "2026-11-24T12:00:00Z", "GIT_COMMITTER_DATE": "2026-11-24T12:00:00Z"}

CODE_BEHINDS = ("Service-pip.js", "Service-player.js", "Service-rewind.js", "Service-sources.js")


def git(cwd, *args, env=None):
    full = dict(os.environ, **IDENTITY)
    if env:
        full.update(env)
    return subprocess.run(["git", "-C", cwd] + list(args), check=True, env=full,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()


def replace_once(path, old, new):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if text.count(old) != 1:
        raise SystemExit("candidates.py: %s holds %d copies of the anchor %r, not one" % (path, text.count(old), old))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new))


def bump(tree, version, old_version, stamps, against):
    """The version in the three places release.py check holds equal, and then
    the stamps' own step: build_stamps.py's cut against `against`, the build
    this one updates from (D-REL-16). Called after the build's other edits,
    its marks, which the cut must see."""
    replace_once(os.path.join(tree, "manifest.json"), '"version": "%s",' % old_version, '"version": "%s",' % version)
    replace_once(os.path.join(tree, "model", "build.mjs"), 'var PLUGIN_VERSION = "%s"' % old_version,
                 'var PLUGIN_VERSION = "%s"' % version)
    replace_once(os.path.join(tree, "README.md"), "Status: v%s." % old_version, "Status: v%s." % version)
    with open(os.devnull, "w") as sink:
        try:
            stamps.cut(tree, against, out=sink)
        except (stamps.Refused, stamps.BuildStampsError) as error:
            raise SystemExit("candidates.py: build_stamps.py refuses the %s tree against %s (DEVREF must carry the "
                             "stamps): %s" % (version, against, error))


def first_marks(tree):
    anchor = "  readonly property bool staleBuild: buildNotice !== \"\"\n"
    marks = ("  // RELOAD-D MARK (a scratch build of the reload rig, never shipped)\n"
             "  function reloadMarks() {\n"
             "    var out = [\"C1 Service.qml\"]\n"
             "    try { out.push(ServicePip.reloadMark()) } catch (e) { out.push(\"Service-pip.js: \" + e) }\n"
             "    try { out.push(ServicePlayer.reloadMark()) } catch (e) { out.push(\"Service-player.js: \" + e) }\n"
             "    try { out.push(ServiceRewind.reloadMark()) } catch (e) { out.push(\"Service-rewind.js: \" + e) }\n"
             "    try { out.push(ServiceSources.reloadMark()) } catch (e) { out.push(\"Service-sources.js: \" + e) }\n"
             "    return out.join(\", \")\n"
             "  }\n")
    replace_once(os.path.join(tree, "Service.qml"), anchor, anchor + marks)
    for name in CODE_BEHINDS:
        with open(os.path.join(tree, name), "a", encoding="utf-8") as fh:
            fh.write("\n  // RELOAD-D MARK (a scratch build of the reload rig, never shipped)\n"
                     "  function reloadMark() { return \"C1 %s\" }\n" % name)
    replace_once(os.path.join(tree, "Guide.qml"), "  property bool opened: false\n",
                 "  property bool opened: false\n  readonly property string reloadMark: \"C1 Guide.qml\"\n")
    replace_once(os.path.join(tree, "BarWidget.qml"), "  property var service: null\n",
                 "  property var service: null\n  readonly property string reloadMark: \"C1 BarWidget.qml\"\n")


def second_marks(tree):
    replace_once(os.path.join(tree, "Service.qml"), '"C1 Service.qml"', '"C2 Service.qml"')
    for name in CODE_BEHINDS:
        replace_once(os.path.join(tree, name), '"C1 %s"' % name, '"C2 %s"' % name)
    replace_once(os.path.join(tree, "Guide.qml"), '"C1 Guide.qml"', '"C2 Guide.qml"')
    replace_once(os.path.join(tree, "BarWidget.qml"), '"C1 BarWidget.qml"', '"C2 BarWidget.qml"')
    # The one function changed across the pair (the module docstring).
    replace_once(os.path.join(tree, "Service-player.js"), "  function socketAttached() {\n",
                 "  function socketAttachedLive() {\n")
    replace_once(os.path.join(tree, "Service.qml"),
                 "  function socketAttached() { return ServicePlayer.socketAttached() }\n",
                 "  function socketAttached() { return ServicePlayer.socketAttachedLive() }\n")


def third_marks(tree):
    for name in ("Service.qml",) + CODE_BEHINDS + ("Guide.qml", "BarWidget.qml"):
        replace_once(os.path.join(tree, name), '"C2 %s"' % name, '"C3 %s"' % name)


def main(argv):
    if len(argv) != 5:
        raise SystemExit("usage: candidates.py REPO WORK C0REF DEVREF")
    repo, work, c0ref, devref = (os.path.abspath(argv[1]), os.path.abspath(argv[2]), argv[3], argv[4])
    if os.path.exists(work):
        raise SystemExit("candidates.py: %s exists; refusing to reuse it" % work)
    os.makedirs(work, mode=0o700)
    src = os.path.join(work, "src")
    c0 = git(repo, "rev-parse", "--verify", c0ref + "^{commit}").strip()
    dev = git(repo, "rev-parse", "--verify", devref + "^{commit}").strip()
    subprocess.run(["git", "init", "-q", "-b", "scratch", src], check=True)
    git(src, "fetch", "-q", "--no-tags", repo, "%s:refs/heads/main" % c0ref, "%s:refs/heads/dev" % devref)
    if git(src, "rev-parse", "main").strip() != c0 or git(src, "rev-parse", "dev").strip() != dev:
        raise SystemExit("candidates.py: the fetched refs are not %s and %s" % (c0, dev))
    # release.py's own ALLOWLIST and build_tree, imported from REPO's tree.
    spec = importlib.util.spec_from_file_location("release", os.path.join(repo, "scripts", "release.py"))
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    # And build_stamps.py's cut, which a real cut runs after the bump.
    spec = importlib.util.spec_from_file_location("build_stamps", os.path.join(repo, "scripts", "build_stamps.py"))
    stamps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stamps)
    git(src, "checkout", "-q", "-b", "c1src", "dev")
    with open(os.path.join(src, "manifest.json"), encoding="utf-8") as fh:
        dev_version = json.load(fh)["version"]
    first_marks(src)
    bump(src, "0.99.0", dev_version, stamps, c0)
    git(src, "commit", "-q", "-a", "-m", "reload-d: C1 source (version and marks)")
    git(src, "checkout", "-q", "-b", "c2src", "c1src")
    second_marks(src)
    bump(src, "0.99.1", "0.99.0", stamps, "c1src")
    git(src, "commit", "-q", "-a", "-m", "reload-d: C2 source (version, marks, socketAttached renamed)")
    git(src, "checkout", "-q", "-b", "c3src", "c2src")
    third_marks(src)
    bump(src, "0.99.2", "0.99.1", stamps, "c2src")
    git(src, "commit", "-q", "-a", "-m", "reload-d: C3 source (version and marks)")
    commits = {"C0": c0}
    parent = c0
    for build, ref in (("C1", "c1src"), ("C2", "c2src"), ("C3", "c3src")):
        git(src, "checkout", "-q", ref)
        problems = release.check(src, out=open(os.devnull, "w"))
        if problems:
            raise SystemExit("candidates.py: release.py check refuses %s: %s" % (build, problems))
        tree = release.build_tree(src, git(src, "rev-parse", "HEAD").strip())
        got = release.tree_paths(src, tree)
        if got != set(release.ALLOWLIST):
            raise SystemExit("candidates.py: %s's tree is not the allowlist" % build)
        message = ("release: %s (reload-d scratch build)\n\nExported from %s by scripts/release.py's "
                   "build_tree; %d allowlisted files.\n" % (build, ref, len(release.ALLOWLIST)))
        parent = git(src, "commit-tree", tree, "-p", parent, "-m", message).strip()
        commits[build] = parent
    git(src, "update-ref", "refs/heads/art", commits["C3"])
    upstream = os.path.join(work, "upstream.git")
    subprocess.run(["git", "clone", "-q", "--bare", "--single-branch", "--branch", "main", src, upstream],
                   check=True)
    git(upstream, "fetch", "-q", "--no-tags", src, "refs/heads/art:refs/heads/art")
    git(upstream, "update-ref", "refs/heads/main", c0)
    print(json.dumps({"upstream": upstream, "allowlist": len(release.ALLOWLIST),
                      "commits": commits, "dev": dev}))


if __name__ == "__main__":
    main(sys.argv)
