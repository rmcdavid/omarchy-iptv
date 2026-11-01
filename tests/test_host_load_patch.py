"""D-HOST-9: what keeps the THEME's Color in the plugin's QML on Qt 6.12.

Qt 6.12 exports a C++ singleton named Color from QtQuick (QQuickColor,
`exports: ["QtQuick/Color 6.12"]`). The engine's name lookup for a JS
identifier searches the C++ types of every unqualified import BEFORE any
qmldir composite singleton (QQmlTypeNameCache::doQuery in 6.12.0:
m_anonymousImports, then m_anonymousCompositeSingletons), so an unqualified
`Color` in Guide.qml or BarWidget.qml is Qt's whichever import comes last.
qmllint models the opposite (the last import wins), which is why the board
row first read the import order as the protection. It is not: upstream has it
as QTBUG-151278 (open, P1, a regression from 6.11.2), and lane-host9 measured
it on 2026-11-01 with the real quickshell in a headless cage on a private bus:
with the host's pragma absent, the shipped Guide's `accent` and `urgent` read
#000000 and BarWidget's `barFg` #000000, beside 15 TypeError and
undefined-assignment warnings, in BOTH import orders; with it, the theme's
values (#12ab34, #cd3456, #a1b2c3) and no warning, in both orders.

What holds it on the host is Omarchy's own Quickshell patch (omarchy-pkgs,
pkgbuilds/quickshell/load_qtquick_611.patch, "temporarily", pending Qt's
answer): a ROOT file whose header carries `//@ pragma OmarchyLoadPatch`
turns on a rewrite of every unversioned `import QtQuick` line into
`import QtQuick 6.11`, in every local QML file the engine loads -- the URL
interceptor scans the directory of each one, so a plugin outside the shell's
own folder is rewritten too -- and QtQuick 6.11 has no Color. A plugin's own
copy of the pragma does nothing (the scanner honours it on the root only).

So the protection is four joins, none of them the plugin's, and these tests
pin each one on this machine:
  1. the host root turns the patch on;
  2. the installed quickshell carries the rewrite: its pattern and its
     replacement are READ OUT OF THE BINARY and used below, not copied, so a
     changed rewrite is judged as it now is;
  3. every shipped QML file, with that rewrite applied to its own header,
     resolves every theme singleton it names unqualified to the theme, on the
     installed Qt -- observed in a plain `qml` run, offscreen, no display;
  4. the host hands each entry point to the engine as a LOCAL file URL, the
     only kind the patched interceptor rewrites: the host's own
     PluginRegistry.entryPointUrl and Util.fileUrl, run (rc-host9).
And one premise: without the rewrite, Qt's Color wins in the shipped files.
Join 3 also catches an import that brings QtQuick back at its latest version
behind the rewrite's back: QtQuick.Window's qmldir says `import QtQuick auto`,
so a shipped `import QtQuick.Window` makes Color Qt's again under the patch
(measured by rc-host9 in the cage, and red here on that mutant).
When the premise goes red, Qt changed the lookup (QTBUG-151278) or the files
stopped naming Color unqualified; re-measure the row. A red anywhere here
after an Omarchy or Qt update is a re-measurement request, not by itself a
plugin defect -- except that the plugin breaks when 1 or 2 goes and nothing
else in the gate would say so.

The probe stands in for two things and says so. Quickshell's modules are
registered by the quickshell binary and cannot load in plain qml, so each one
a shipped header imports is stubbed with a module of one dummy type; that is
only as forgiving as the real module if the real one exports none of the
theme's names, which test_the_stubbed_modules_export_no_theme_name reads from
the installed qmltypes (rule 10). And qs.Commons is a stand-in whose qmldir
declares the host's own singleton names as composite singletons, which is the
registration kind the host's Commons has; its members are a marker, not the
theme's tokens, because the question is which object a name resolves to.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = os.environ.get("OMARCHY_SHELL_DIR", "/usr/share/omarchy/shell")
QUICKSHELL = os.environ.get("OMARCHY_IPTV_QUICKSHELL", "/usr/bin/quickshell")
QT_QML_DIR = "/usr/lib/qt6/qml"
QML = "/usr/lib/qt6/bin/qml"
PRAGMA = "//@ pragma OmarchyLoadPatch"

_spec = importlib.util.spec_from_file_location("release", os.path.join(ROOT, "scripts", "release.py"))
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)
SHIPPED_QML = [f for f in release.ALLOWLIST if f.endswith(".qml")]


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def root_turns_patch_on(shell_qml):
    """The scanner's own reading: a trimmed header line equal to the pragma,
    where the header ends at the first line that contains `{`."""
    for line in read(shell_qml).split("\n"):
        line = line.strip()
        if line == PRAGMA:
            return True
        if "{" in line:
            return False
    return False


def rewrite_from_binary(path):
    """(pattern, replacement) of the installed quickshell's QtQuick import
    rewrite, or None. QStringLiteral stores both as UTF-16; the pragma the
    scanner compares against is a Latin-1 literal."""
    with open(path, "rb") as fh:
        data = fh.read()
    if PRAGMA.encode("ascii") not in data:
        return None
    runs = [m.group(0).decode("utf-16-le") for m in re.finditer(rb"(?:[\x20-\x7e]\x00){6,}", data)]
    patterns = [r for r in runs if "import" in r and "QtQuick" in r and r.startswith("^")]
    replacements = [r for r in runs if re.fullmatch(r"\\1 \d+\.\d+", r)]
    if len(patterns) != 1 or len(replacements) != 1:
        return None
    return re.compile(patterns[0]), replacements[0]


def theme_names():
    names = []
    for line in read(os.path.join(HOST, "Commons", "qmldir")).split("\n"):
        w = line.split()
        if len(w) >= 2 and w[0] == "singleton":
            names.append(w[1])
    return names


def strip_comments_and_strings(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    text = re.sub(r'"(?:\\.|[^"\\\n])*"', '""', text)
    return re.sub(r"'(?:\\.|[^'\\\n])*'", "''", text)


def split_header(text):
    """(everything above the root object, the rest). The probe copies the first
    half byte for byte, so its imports and pragmas are the shipped file's."""
    m = re.search(r"^[A-Z][\w.]*\s*\{\s*$", text, re.M)
    if not m:
        raise AssertionError("no root object line")
    return text[:m.start()], text[m.start():]


def unqualified_uses(body, names):
    body = strip_comments_and_strings(body)
    return [n for n in names if re.search(r"(?<![\w.$])" + n + r"\s*\.", body)]


def module_imports(header):
    out = []
    for line in header.split("\n"):
        m = re.match(r"^\s*import\s+([A-Za-z_][\w.]*)(?:\s+\d+\.\d+)?\s*(?:;|//.*)?$", line)
        if m:
            out.append(m.group(1))
    return out


def stubbed(module):
    return module.startswith("Quickshell") or module.startswith("qs.")


def module_exports(module, seen=None):
    """Every type name a module under QT_QML_DIR exports, with what its qmldir
    imports, read from the installed qmltypes."""
    seen = set() if seen is None else seen
    if module in seen:
        return set()
    seen.add(module)
    d = os.path.join(QT_QML_DIR, *module.split("."))
    qmldir = os.path.join(d, "qmldir")
    if not os.path.isfile(qmldir):
        return set()
    names = set()
    for line in read(qmldir).split("\n"):
        w = line.split()
        if not w:
            continue
        if w[0] == "typeinfo":
            for e in re.findall(r'"([^"/]+(?:/[^"/]+)*)/([A-Za-z_]\w*) \d+\.\d+"', read(os.path.join(d, w[1]))):
                names.add(e[1])
        elif w[0] == "import" or (w[0] in ("default", "optional") and len(w) > 2 and w[1] == "import"):
            names |= module_exports(w[1] if w[0] == "import" else w[2], seen)
        elif re.match(r"^[A-Z]", w[0]) and len(w) >= 3:
            names.add(w[0])
    return names


PROBE_BODY = """
// test_host_load_patch probe: the header above is %(origin)s.
Item {
  property var theme: ({})
  function check() {
    var out = {}
%(checks)s
    return out
  }
}
"""

CHECK = """    try { out["%(n)s"] = { theme: %(n)s === theme["%(n)s"], is: String(%(n)s) } }
    catch (e) { out["%(n)s"] = { theme: false, is: "throws " + String(e) } }"""

MAIN = """import QtQuick
import qs.Commons as Commons

QtObject {
  Component.onCompleted: {
    var theme = { %(theme)s }
    var jobs = %(jobs)s
    for (var i = 0; i < jobs.length; i++) {
      var comp = Qt.createComponent(Qt.resolvedUrl(jobs[i].file))
      if (comp.status !== Component.Ready) {
        console.log("HOSTPATCH " + JSON.stringify({ job: jobs[i], error: comp.errorString() }))
        continue
      }
      var obj = comp.createObject(null, { theme: theme })
      console.log("HOSTPATCH " + JSON.stringify({ job: jobs[i], out: obj.check() }))
      obj.destroy()
    }
    console.log("HOSTPATCH_DONE")
    Qt.exit(0)
  }
}
"""


def observe(texts, rewrite):
    """Run every file in `texts` ({name: source}) twice under plain Qt,
    offscreen: once as it is and once with `rewrite` applied to its header.
    Returns {(name, "shipped"|"rewritten"): {theme name: {theme, is}}} for each
    theme name the file names unqualified."""
    pattern, replacement = rewrite
    names = theme_names()
    work = tempfile.mkdtemp(prefix="omarchy-iptv-hostpatch-")
    try:
        home = os.path.join(work, "home")
        tree = os.path.join(work, "tree")
        os.makedirs(home, mode=0o700)
        os.makedirs(tree)
        # the relative imports a shipped header names travel with it
        shutil.copy(os.path.join(ROOT, "Model.mjs"), tree)
        shutil.copytree(os.path.join(ROOT, "model"), os.path.join(tree, "model"))
        imports = os.path.join(work, "imports")
        stand_in = os.path.join(imports, "qs", "Commons")
        os.makedirs(stand_in)
        with open(os.path.join(stand_in, "qmldir"), "w") as fh:
            fh.write("module qs.Commons\n" + "".join("singleton %s 1.0 %s.qml\n" % (n, n) for n in names))
        for n in names:
            with open(os.path.join(stand_in, n + ".qml"), "w") as fh:
                fh.write('pragma Singleton\nimport QtQml\nQtObject { readonly property string standIn: "qs.Commons.%s" }\n' % n)
        jobs, expect = [], {}
        for name, text in sorted(texts.items()):
            header, body = split_header(text)
            uses = unqualified_uses(body, names)
            if not uses:
                continue
            for mod in module_imports(header):
                if stubbed(mod) and mod != "qs.Commons":
                    d = os.path.join(imports, *mod.split("."))
                    os.makedirs(d, exist_ok=True)
                    stub = "HostPatchStub" + mod.replace(".", "")
                    with open(os.path.join(d, "qmldir"), "w") as fh:
                        fh.write("module %s\n%s 1.0 %s.qml\n" % (mod, stub, stub))
                    with open(os.path.join(d, stub + ".qml"), "w") as fh:
                        fh.write("import QtQml\nQtObject {}\n")
            checks = "\n".join(CHECK % {"n": n} for n in uses)
            for regime in ("shipped", "rewritten"):
                h = header
                if regime == "rewritten":
                    h = "\n".join(pattern.sub(replacement, line) for line in header.split("\n"))
                probe = "Probe%s%s.qml" % (re.sub(r"\W", "", name.rsplit(".", 1)[0]), regime.capitalize())
                with open(os.path.join(tree, probe), "w", encoding="utf-8") as fh:
                    fh.write(h + PROBE_BODY % {"origin": "%s's, %s" % (name, regime), "checks": checks})
                jobs.append({"file": probe, "name": name, "regime": regime})
                expect[(name, regime)] = uses
        with open(os.path.join(tree, "main.qml"), "w") as fh:
            fh.write(MAIN % {"theme": ", ".join("%s: Commons.%s" % (n, n) for n in names), "jobs": json.dumps(jobs)})
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": home, "XDG_CONFIG_HOME": home + "/.config",
               "XDG_CACHE_HOME": home + "/.cache", "XDG_DATA_HOME": home + "/.local/share",
               "XDG_STATE_HOME": home + "/.local/state", "XDG_RUNTIME_DIR": home,
               "QT_QPA_PLATFORM": "offscreen", "QT_FORCE_STDERR_LOGGING": "1"}
        run = subprocess.run(["prlimit", "--core=0", "--as=4294967296", "--", QML, "-I", imports,
                              os.path.join(tree, "main.qml")],
                             cwd=tree, env=env, capture_output=True, text=True, timeout=60)
        log = run.stdout + run.stderr
        if "HOSTPATCH_DONE" not in log:
            raise AssertionError("the probe did not finish: " + log[-1200:])
        seen = {}
        for line in log.splitlines():
            if "HOSTPATCH {" not in line:
                continue
            rec = json.loads(line.split("HOSTPATCH ", 1)[1])
            key = (rec["job"]["name"], rec["job"]["regime"])
            if "error" in rec:
                raise AssertionError("%s (%s) did not load: %s" % (key[0], key[1], rec["error"]))
            seen[key] = rec["out"]
        missing = sorted(set(expect) - set(seen))
        if missing:
            raise AssertionError("no report for %r: %s" % (missing, log[-800:]))
        return seen
    finally:
        shutil.rmtree(work, True)


def not_the_theme(seen, regime):
    return ["%s: %s is %s" % (name, n, r["is"])
            for (name, reg), out in sorted(seen.items()) if reg == regime
            for n, r in sorted(out.items()) if not r["theme"]]


def host_function(path, name):
    """The text of `function <name>(...) { ... }` in a host QML file, by brace
    count, or None. Good enough for the host's entryPointUrl, which has no
    brace inside a string, a regex or a comment; a function this cannot cut
    out is a host change to read by hand, so the caller treats None as red."""
    text = read(path)
    m = re.search(r"^[ \t]*function[ \t]+%s[ \t]*\(" % re.escape(name), text, re.M)
    if not m:
        return None
    start = text.find("{", m.end())
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[m.start():i + 1].strip()
    return None


def local_file_url_naming(url, path):
    """True when `url` is what QUrl::isLocalFile() accepts (scheme file, no
    host) and its decoded path is exactly `path`: the only URL shape whose
    loads the patched interceptor rewrites. A query is allowed, because the
    interceptor keys on toLocalFile(), which drops it (rc-host9 measured a
    `?x` load served the rewritten text)."""
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "file" and parts.netloc == "" and urllib.parse.unquote(parts.path) == path


ENTRY_MAIN = """import QtQuick
import qs.Commons

QtObject {
%(fn)s
  Component.onCompleted: {
    var jobs = %(jobs)s
    var out = []
    for (var i = 0; i < jobs.length; i++) {
      try { out.push({ kind: jobs[i].kind, url: String(entryPointUrl(jobs[i].manifest, jobs[i].kind)) }) }
      catch (e) { out.push({ kind: jobs[i].kind, error: String(e) }) }
    }
    console.log("HOSTURL " + JSON.stringify(out))
    Qt.exit(0)
  }
}
"""


def host_entry_point_urls(host, manifest, source_dir):
    """{kind: url} from the HOST's own PluginRegistry.entryPointUrl, run in plain
    qml over the host's own Commons/Util.qml (its Quickshell import stubbed: Util
    names Quickshell only inside functions this does not call), for each of the
    plugin's entry points as the host passes them (shell.qml asks for "overlay",
    "barWidget" and "service", the manifest's own entryPoints keys)."""
    fn = host_function(os.path.join(host, "services", "PluginRegistry.qml"), "entryPointUrl")
    if fn is None:
        raise AssertionError("%s/services/PluginRegistry.qml has no entryPointUrl this test can cut out; read how "
                             "the host hands a plugin's entry points to the engine now (D-HOST-9)" % host)
    # The probe's own URL is file:, the host file's is qs:@/qs/..., so a
    # function that resolved against its own URL would read local here and not
    # there. That shape is the one this probe cannot judge; refuse it.
    if "resolvedUrl" in fn or "baseUrl" in fn:
        raise AssertionError("the host's entryPointUrl now resolves against its own (qs:) URL, which a plain-qml "
                             "probe cannot reproduce; re-measure D-HOST-9 in a cage:\n" + fn)
    work = tempfile.mkdtemp(prefix="omarchy-iptv-hostpatch-")
    try:
        home = os.path.join(work, "home")
        os.makedirs(home, mode=0o700)
        commons = os.path.join(work, "imports", "qs", "Commons")
        os.makedirs(commons)
        shutil.copy(os.path.join(host, "Commons", "Util.qml"), commons)
        with open(os.path.join(commons, "qmldir"), "w") as fh:
            fh.write("module qs.Commons\nsingleton Util 1.0 Util.qml\n")
        stub = os.path.join(work, "imports", "Quickshell")
        os.makedirs(stub)
        with open(os.path.join(stub, "qmldir"), "w") as fh:
            fh.write("module Quickshell\nHostPatchStubQuickshell 1.0 HostPatchStubQuickshell.qml\n")
        with open(os.path.join(stub, "HostPatchStubQuickshell.qml"), "w") as fh:
            fh.write("import QtQml\nQtObject {}\n")
        m = dict(manifest)
        m["__sourceDir"] = source_dir
        jobs = [{"kind": k, "manifest": m} for k in sorted(manifest["entryPoints"])]
        main = os.path.join(work, "main.qml")
        with open(main, "w", encoding="utf-8") as fh:
            fh.write(ENTRY_MAIN % {"fn": fn, "jobs": json.dumps(jobs)})
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": home, "XDG_CONFIG_HOME": home + "/.config",
               "XDG_CACHE_HOME": home + "/.cache", "XDG_DATA_HOME": home + "/.local/share",
               "XDG_STATE_HOME": home + "/.local/state", "XDG_RUNTIME_DIR": home,
               "QT_QPA_PLATFORM": "offscreen", "QT_FORCE_STDERR_LOGGING": "1"}
        run = subprocess.run(["prlimit", "--core=0", "--as=4294967296", "--", QML, "-I",
                              os.path.join(work, "imports"), main],
                             cwd=work, env=env, capture_output=True, text=True, timeout=60)
        log = run.stdout + run.stderr
        rec = [l.split("HOSTURL ", 1)[1] for l in log.splitlines() if "HOSTURL [" in l]
        if len(rec) != 1:
            raise AssertionError("the entry point probe did not report: " + log[-1200:])
        return {r["kind"]: r.get("url", "throws " + r.get("error", "")) for r in json.loads(rec[0])}
    finally:
        shutil.rmtree(work, True)


class HostLoadPatchCase(unittest.TestCase):
    seen = None

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(os.path.join(HOST, "shell.qml")) or not os.path.isdir(os.path.join(HOST, "Commons")):
            raise unittest.SkipTest("no Omarchy shell under %s; the host's load path cannot be checked here" % HOST)
        cls.texts = {name: read(os.path.join(ROOT, name)) for name in SHIPPED_QML}

    def rewrite(self):
        if not os.path.isfile(QUICKSHELL):
            self.skipTest("no quickshell at %s" % QUICKSHELL)
        rw = rewrite_from_binary(QUICKSHELL)
        self.assertIsNotNone(rw, "%s carries no OmarchyLoadPatch QtQuick import rewrite; the plugin's unqualified "
                                 "Color is Qt's on Qt 6.12 without it (D-HOST-9). Re-measure." % QUICKSHELL)
        return rw

    def observed(self):
        if not os.path.isfile(QML):
            self.skipTest("no Qt qml runtime at %s" % QML)
        if HostLoadPatchCase.seen is None:
            HostLoadPatchCase.seen = observe(self.texts, self.rewrite())
        return HostLoadPatchCase.seen

    def test_the_host_root_turns_the_load_patch_on(self):
        self.assertTrue(root_turns_patch_on(os.path.join(HOST, "shell.qml")),
                        "%s/shell.qml no longer carries %r in its header: the host stopped rewriting plugins' "
                        "`import QtQuick`, and the guide's unqualified Color is Qt's (D-HOST-9). Re-measure."
                        % (HOST, PRAGMA))

    def test_a_host_root_without_the_pragma_is_caught(self):
        text = read(os.path.join(HOST, "shell.qml"))
        work = tempfile.mkdtemp(prefix="omarchy-iptv-hostpatch-")
        self.addCleanup(shutil.rmtree, work, True)
        copy = os.path.join(work, "shell.qml")
        with open(copy, "w", encoding="utf-8") as fh:
            fh.write("\n".join(l for l in text.split("\n") if l.strip() != PRAGMA))
        self.assertFalse(root_turns_patch_on(copy))
        with open(copy, "w", encoding="utf-8") as fh:
            fh.write("import QtQuick\nShellRoot {\n  " + PRAGMA + "\n}\n")
        self.assertFalse(root_turns_patch_on(copy), "a pragma below the header is not one the scanner reads")

    def test_the_installed_quickshell_carries_the_rewrite(self):
        pattern, replacement = self.rewrite()
        for name in SHIPPED_QML:
            header, _ = split_header(self.texts[name])
            for line in header.split("\n"):
                if re.match(r"^\s*import\s+QtQuick\s*$", line):
                    self.assertNotEqual(pattern.sub(replacement, line), line, "%s: %r" % (name, line))

    def test_a_quickshell_without_the_rewrite_is_caught(self):
        work = tempfile.mkdtemp(prefix="omarchy-iptv-hostpatch-")
        self.addCleanup(shutil.rmtree, work, True)
        fake = os.path.join(work, "quickshell")
        with open(fake, "wb") as fh:
            fh.write(b"\x00//@ pragma Internal\x00Unrecognized pragma\x00" + "^(import)".encode("utf-16-le") + b"\x00\x00")
        self.assertIsNone(rewrite_from_binary(fake))
        with open(fake, "wb") as fh:
            fh.write(b"\x00" + PRAGMA.encode("ascii") + b"\x00")
        self.assertIsNone(rewrite_from_binary(fake), "the pragma literal alone is not the rewrite")

    def test_the_stubbed_modules_export_no_theme_name(self):
        names = set(theme_names())
        mods = set()
        for name in SHIPPED_QML:
            header, _ = split_header(self.texts[name])
            mods |= {m for m in module_imports(header) if stubbed(m) and not m.startswith("qs.")}
        self.assertTrue(mods, "the shipped headers import no Quickshell module; the stub list is stale")
        clash = {m: sorted(module_exports(m) & names) for m in sorted(mods)}
        self.assertEqual({m: [] for m in clash}, clash)
        ui = os.path.join(HOST, "Ui", "qmldir")
        ui_names = {l.split()[0] for l in read(ui).split("\n") if re.match(r"^[A-Z]\w* \d", l)}
        self.assertEqual(set(), ui_names & names)

    def test_with_the_rewrite_every_theme_name_in_the_shipped_qml_is_the_theme(self):
        seen = self.observed()
        self.assertTrue(any(reg == "rewritten" for _, reg in seen), "no shipped file names a theme singleton")
        self.assertEqual([], not_the_theme(seen, "rewritten"))

    def test_premise_without_the_rewrite_qt_takes_color_in_the_shipped_qml(self):
        seen = self.observed()
        users = [(name, out["Color"]) for (name, reg), out in sorted(seen.items())
                 if reg == "shipped" and "Color" in out]
        self.assertTrue(users, "no shipped file names Color unqualified any more; D-HOST-9 may be closed. Re-measure.")
        theme = [name for name, r in users if r["theme"]]
        self.assertEqual([], theme, "Qt no longer puts its Color ahead of the theme's in %s (QTBUG-151278?); the "
                                    "plugin may not depend on the host's load patch any more. Re-measure D-HOST-9."
                         % theme)

    def test_a_file_the_rewrite_cannot_reach_is_caught(self):
        # Synthetic, so the control does not move when the shipped files do:
        # the same two-line import block, once in the form the rewrite reaches
        # and once versioned at 6.12, which its lookahead refuses.
        self.observed()
        body = "Item {\n  property color c: Color.accent\n}\n"
        seen = observe({"Reached.qml": "import QtQuick\nimport qs.Commons\n\n" + body,
                        "Unreached.qml": "import QtQuick 6.12\nimport qs.Commons\n\n" + body}, self.rewrite())
        bad = not_the_theme(seen, "rewritten")
        self.assertEqual(1, len(bad), bad)
        self.assertTrue(bad[0].startswith("Unreached.qml: Color is QQuickColor("), bad)
        self.assertEqual(2, len(not_the_theme(seen, "shipped")), "without the rewrite both are Qt's")

    def test_the_host_hands_every_entry_point_over_as_a_local_file_url(self):
        # Join 4 (rc-host9): the patched interceptor rewrites a load only when
        # its URL isLocalFile(). A host that handed the engine a bare path
        # would have it resolved against shell.qml's qs: URL, skip the rewrite
        # and serve the file as written, so the guide's Color would be Qt's
        # with the pragma still in place. This runs the host's own
        # entryPointUrl and Util.fileUrl, not a copy of what they say today.
        if not os.path.isfile(QML):
            self.skipTest("no Qt qml runtime at %s" % QML)
        with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        # a space and the real id in the path, as Util.fileUrl encodes them
        source_dir = "/home/omarchy user/.config/omarchy/plugins/" + manifest["id"]
        urls = host_entry_point_urls(HOST, manifest, source_dir)
        self.assertEqual(sorted(manifest["entryPoints"]), sorted(urls))
        bad = ["%s: %r" % (k, u) for k, u in sorted(urls.items())
               if not local_file_url_naming(u, source_dir + "/" + manifest["entryPoints"][k])]
        self.assertEqual([], bad, "the host no longer hands these entry points over as local file:// URLs, so "
                                  "the load patch does not rewrite them and the plugin's Color is Qt's (D-HOST-9). "
                                  "Re-measure.")

    def test_a_url_the_patch_would_not_rewrite_is_caught(self):
        path = "/home/omarchy user/.config/omarchy/plugins/x/Guide.qml"
        good = "file://" + urllib.parse.quote(path)
        self.assertTrue(local_file_url_naming(good, path))
        self.assertTrue(local_file_url_naming(good + "?v=1", path), "a query does not stop the rewrite")
        for url in (path, "qs:" + path, "qs:@/qs/Guide.qml", "file://host" + urllib.parse.quote(path),
                    "file://" + urllib.parse.quote(path + ".bak"), "file://" + path.replace(" ", "%2")):
            self.assertFalse(local_file_url_naming(url, path), url)


if __name__ == "__main__":
    unittest.main()
