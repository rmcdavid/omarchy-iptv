#!/usr/bin/env python3
"""scripts/build_stamps.py -- every runtime file names its build (D-REL-16).

WHY. A shell that starts while `omarchy plugin update` is writing the plugin
can load files of two builds side by side, and Qt's disk cache can keep such
a mix through every later restart (D-REL-16, measured by the reload rig in
call (d), 2026-11-24). The manifest's version says what is on DISK; nothing
said what each file the engine COMPILED came from. So every file the plugin's
runtime loads carries a build stamp, a literal compiled into the unit Qt
caches: a stale unit carries the old literal, whichever file it was saved
under, and the running code can compare what it holds with the table the
model carries (D-HOST-1's check, part 1 of L3).

THE VALUE (the lead's call L3-a under the owner's standing authority of
2026-11-09): the version of the last cut that CHANGED the file. A file an
update does not change keeps its stamp and is not rewritten by its stamp, so
a cut writes no more files than it did. `model/build.mjs` carries BUILD_FILES,
every other runtime file in the order release.py's runtime_files reaches it
(the plugin's load order) and the stamp it carries; its own stamp is
PLUGIN_VERSION, which every cut moves.

THE FORMS, one per kind of runtime file (exactly one of each, judged by line):
  Service.qml, Guide.qml, BarWidget.qml
        `  readonly property string buildStamp: "N.N.N"`
  each code-behind Service-<domain>.js, as Service.qml declares it
        `  function buildStamp<Domain>() { return "N.N.N" }` -- the FIRST
        function of the file, because split-service.py --cut appends a moved
        function at the end; Service.qml reaches it through its forwarder
  each model part model/<part>.mjs but build.mjs
        `var BUILD_STAMP_<PART> = "N.N.N"` (the part's name upper-cased, a
        dash an underscore), its first declaration after the generated
        import blocks
  model/build.mjs
        `var PLUGIN_VERSION = "N.N.N"`, and directly under that line the
        generated BUILD_FILES block (table_block)
  Model.mjs
        `export var BUILD_STAMP_AGGREGATOR = "N.N.N"` (split-model.mjs keeps it)

REFUSALS (Problem.kind):
  missing  a runtime file with no stamp of its kind (or of no kind at all)
  twice    a second declaration of the file's stamp name
  form     the one declaration is not in the exact form, or not where the
           form puts it
  name     a declaration of a stamp name that is not the file's: a
           code-behind's not named for its qualifier's domain, a part's not
           named for its part
  value    a stamp that is not N.N.N, or one above PLUGIN_VERSION
  table    BUILD_FILES missing, declared twice, not exactly the runtime files
           but build.mjs in load order, a row unequal to its file's stamp, or
           the block not in its generated form directly under PLUGIN_VERSION
  stale    (cut_problems, the cut's own check) a runtime file that differs
           from REF and does not carry the version being cut

MODES (exactly one):
  --check    the tree, then this script's own cases
             (tests/fixtures/build-stamps/cases.json), so the gate's step goes
             red when the judge stops judging. release.py check calls
             problems().
  --cut      run after the version bump (manifest.json and PLUGIN_VERSION).
             Refuses on any --check problem, and on a PLUGIN_VERSION that is
             not manifest.json's version, before it writes anything; then
             every runtime file whose blob differs from --against's (default
             `main`) gets manifest.json's version, and BUILD_FILES is
             rewritten. A second --cut changes nothing.
  --strict   cut_problems against --against for manifest.json's version: what
             release.py build refuses on, by hand.
  --json     print the stamps it reads, file by file in load order.

A file's blob is what `git hash-object` gives for it at its path, the
repository's filters applied: the blob `git add` would store, which is the
blob a commit of dev holds and the blob release.py's build_tree puts on main
unchanged (it copies dev's blob ids). REF's are read with `git ls-tree`.
Nothing is written to git, and nothing outside the tree it is given.

Python 3 standard library only, ASCII only; every subprocess is an argv list.
"""

import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import service_files  # noqa: E402  the service's files, as Service.qml declares them (D-REL-14)

CASES = os.path.join(os.path.dirname(SCRIPT_DIR), 'tests', 'fixtures', 'build-stamps', 'cases.json')

BUILD = 'model/build.mjs'
AGGREGATOR = 'Model.mjs'
MANIFEST = 'manifest.json'
GIT_TIMEOUT = 120

KINDS = ('missing', 'twice', 'form', 'name', 'value', 'table', 'stale')

VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')

# The exact form of each kind's stamp line, by its name and its value.
FORMS = {
    'qml': '  readonly property string {name}: "{value}"',
    'code-behind': '  function {name}() {{ return "{value}" }}',
    'part': 'var {name} = "{value}"',
    'build': 'var {name} = "{value}"',
    'aggregator': 'export var {name} = "{value}"',
}
# Every declaration of a name of the kind's stamp family, at any indent and
# in any spelling, so a misspelt, misplaced or second stamp is seen.
FAMILY = {
    'qml': (re.compile(r'[ \t]*(?:(?:readonly|required|default)[ \t]+)*property[ \t]+[^ \t\n]+[ \t]+(buildStamp)(?![A-Za-z0-9_$])'),
            re.compile(r'[ \t]*function[ \t]+(buildStamp)[ \t]*\(')),
    'code-behind': (re.compile(r'[ \t]*function[ \t]+(buildStamp[A-Za-z0-9_$]*)[ \t]*\('),),
    'part': (re.compile(r'[ \t]*(?:export[ \t]+)?(?:var|let|const|function)[ \t]+(BUILD_STAMP_[A-Za-z0-9_$]*)(?![A-Za-z0-9_$])'),),
    'build': (re.compile(r'[ \t]*(?:export[ \t]+)?(?:var|let|const|function)[ \t]+(BUILD_STAMP_[A-Za-z0-9_$]*)(?![A-Za-z0-9_$])'),
              re.compile(r'[ \t]*(?:export[ \t]+)?(?:var|let|const|function)[ \t]+(PLUGIN_VERSION)(?![A-Za-z0-9_$])')),
    'aggregator': (re.compile(r'[ \t]*(?:export[ \t]+)?(?:var|let|const|function)[ \t]+(BUILD_STAMP_[A-Za-z0-9_$]*)(?![A-Za-z0-9_$])'),),
}
FUNCTION_LINE = re.compile(r'[ \t]*function[ \t]')
TABLE_DECL = re.compile(r'[ \t]*(?:export[ \t]+)?(?:var|let|const|function)[ \t]+BUILD_FILES(?![A-Za-z0-9_$])')
TABLE_ROW = re.compile(r'  "([^"\\\n]+)": "([^"\\\n]*)",?')
# The generated block. Shipped, so it names the tool the way a shipped
# comment names any dev-branch file: by name, never by a path an install
# lacks (D-REL-2).
TABLE_HEAD = (
    '// D-REL-16. GENERATED by build_stamps.py (dev branch) at the cut, never by',
    '// hand: every other runtime file of the plugin, in the order it is loaded,',
    '// and the build stamp it carries, the version of the last cut that changed',
    '// it. This part\'s own stamp is PLUGIN_VERSION, which every cut moves.',
)
TABLE_START = 'var BUILD_FILES = {'


class Problem(collections.namedtuple('Problem', 'kind file line message')):
    def __str__(self):
        where = self.file if not self.line else '%s:%d' % (self.file, self.line)
        return '%s: %s [%s]' % (where, self.message, self.kind)


class BuildStampsError(Exception):
    """The tree or REF cannot be read: no verdict, which is red."""


class Refused(Exception):
    def __init__(self, problems):
        Exception.__init__(self, '; '.join(str(p) for p in problems))
        self.problems = problems


# --- the kinds ---------------------------------------------------------------

def qualifiers(texts):
    """{code-behind file: qualifier}, from the Service.qml among `texts`."""
    service = texts.get(service_files.SERVICE)
    if service is None:
        return {}
    try:
        return dict((f, q) for f, q, _n in service_files.declarations(service))
    except service_files.ServiceFilesError:
        return {}       # the service split guard's to refuse


def kind_of(rel, quals):
    if rel.endswith('.qml'):
        return 'qml'
    if rel == AGGREGATOR:
        return 'aggregator'
    if rel == BUILD:
        return 'build'
    if rel.startswith('model/') and rel.endswith('.mjs'):
        return 'part'
    if rel in quals:
        return 'code-behind'
    return None


def stamp_name(rel, kind, quals):
    """The name of `rel`'s stamp, which its kind and its own name give."""
    if kind == 'qml':
        return 'buildStamp'
    if kind == 'code-behind':
        return 'buildStamp' + quals[rel][len('Service'):]
    if kind == 'part':
        return 'BUILD_STAMP_' + rel[len('model/'):-len('.mjs')].upper().replace('-', '_')
    if kind == 'build':
        return 'PLUGIN_VERSION'
    if kind == 'aggregator':
        return 'BUILD_STAMP_AGGREGATOR'
    return None


def stamp_line(kind, name, value):
    """The exact stamp line of `kind` (no newline)."""
    return FORMS[kind].format(name=name, value=value)


def exact(kind, name):
    """The exact form as a pattern whose one group is the value: anything
    between the quotes but a quote, a backslash or a newline."""
    before, after = stamp_line(kind, name, '\0').split('\0')
    return re.compile(re.escape(before) + r'([^"\\\n]*)' + re.escape(after))


def table_block(rows):
    """BUILD_FILES in its generated form, from [(file, stamp)] in load order."""
    out = list(TABLE_HEAD) + [TABLE_START]
    for k, (rel, value) in enumerate(rows):
        out.append('  "%s": "%s"%s' % (rel, value, ',' if k < len(rows) - 1 else ''))
    out.append('}')
    return '\n'.join(out) + '\n'


def version_key(value):
    m = VERSION.fullmatch(value or '')
    return None if m is None else tuple(int(g) for g in m.groups())


# --- the judge ---------------------------------------------------------------

def first_body_line(lines):
    """The index of a part's first line of code: past the header and the
    blank and comment lines, and past the generated import blocks."""
    k = 0
    while k < len(lines):
        s = lines[k].strip()
        if lines[k].startswith('import {'):
            while k < len(lines) and not lines[k].startswith('}'):
                k += 1
        elif lines[k].startswith('import '):
            pass
        elif s and not s.startswith(('//', '/*', '*')):
            return k
        k += 1
    return None


def judge_file(rel, text, kind, name):
    """(problems, (value, line index) or None) for one file's own stamp."""
    lines = text.split('\n')
    problems = []
    found = []
    for i, line in enumerate(lines):
        for family in FAMILY[kind]:
            m = family.match(line)
            if m:
                found.append((i, m.group(1)))
                break
    for i, n in found:
        if n != name:
            problems.append(Problem('name', rel, i + 1, 'declares %s, and this file\'s stamp is %s' % (n, name)))
    mine = [i for i, n in found if n == name]
    if not mine:
        if not problems:
            problems.append(Problem('missing', rel, 0, 'carries no build stamp; its kind\'s line is `%s`'
                                    % stamp_line(kind, name, 'N.N.N')))
        return problems, None
    if len(mine) > 1:
        problems.append(Problem('twice', rel, mine[1] + 1, 'declares %s again (first on line %d)' % (name, mine[0] + 1)))
        return problems, None
    i = mine[0]
    m = exact(kind, name).fullmatch(lines[i])
    if m is None:
        problems.append(Problem('form', rel, i + 1, 'declares %s, and not in the form `%s`'
                                % (name, stamp_line(kind, name, 'N.N.N'))))
        return problems, None
    if kind == 'code-behind':
        first = next((k for k, line in enumerate(lines) if FUNCTION_LINE.match(line)), None)
        if first != i:
            problems.append(Problem('form', rel, i + 1, '%s is not the first function of the file; it leads, because '
                                    'split-service.py --cut appends a moved function at the end' % name))
            return problems, None
    if kind == 'part' and first_body_line(lines) != i:
        problems.append(Problem('form', rel, i + 1, '%s is not the first declaration after the import blocks' % name))
        return problems, None
    return problems, (m.group(1), i)


def judge_table(text, order, stamps, plugin_at):
    """The `table` problems of model/build.mjs's BUILD_FILES."""
    lines = text.split('\n')
    decls = [i for i, line in enumerate(lines) if TABLE_DECL.match(line)]
    if not decls:
        return [Problem('table', BUILD, 0, 'carries no BUILD_FILES table')]
    if len(decls) > 1:
        return [Problem('table', BUILD, decls[1] + 1, 'declares BUILD_FILES again (first on line %d)' % (decls[0] + 1))]
    at = decls[0]
    if lines[at] != TABLE_START:
        return [Problem('table', BUILD, at + 1, 'BUILD_FILES is not in its generated form: `%s`' % TABLE_START)]
    rows = []
    k = at + 1
    while k < len(lines) and lines[k] != '}':
        m = TABLE_ROW.fullmatch(lines[k])
        if m is None:
            return [Problem('table', BUILD, k + 1, 'a BUILD_FILES line that is not a generated row')]
        rows.append((m.group(1), m.group(2), k + 1))
        k += 1
    if k >= len(lines):
        return [Problem('table', BUILD, at + 1, 'BUILD_FILES has no closing line')]
    want = [rel for rel in order if rel != BUILD]
    have = [r[0] for r in rows]
    problems = []
    if have != want:
        lack = [r for r in want if r not in have]
        extra = [r for r in have if r not in want]
        if lack:
            problems.append(Problem('table', BUILD, at + 1, 'BUILD_FILES has no row for %s' % ', '.join(lack)))
        if extra:
            problems.append(Problem('table', BUILD, at + 1, 'BUILD_FILES has a row for %s, which is no runtime file '
                                    'but this one' % ', '.join(extra)))
        if not lack and not extra:
            problems.append(Problem('table', BUILD, at + 1, 'BUILD_FILES rows are not in the order the plugin loads '
                                    'them (%s)' % ', '.join(want)))
        return problems
    for rel, value, n in rows:
        carried = stamps.get(rel)
        if carried is not None and carried != value:
            problems.append(Problem('table', BUILD, n, 'the row for %s says %s, and the file carries %s'
                                    % (rel, value, carried)))
    if problems or plugin_at is None or any(stamps.get(rel) is None for rel in want):
        return problems
    block = table_block([(rel, stamps[rel]) for rel in want]).split('\n')[:-1]
    if lines[plugin_at + 1:plugin_at + 1 + len(block)] != block:
        problems.append(Problem('table', BUILD, at + 1, 'BUILD_FILES is not in its generated form directly under '
                                'PLUGIN_VERSION (its comment, then the table)'))
    return problems


def judge(texts, order):
    """(problems, {file: stamp or None}, {file: line index}) over `texts`,
    the runtime files by name in load order `order`."""
    quals = qualifiers(texts)
    problems = []
    read = collections.OrderedDict()
    at = {}
    for rel in order:
        kind = kind_of(rel, quals)
        if kind is None:
            problems.append(Problem('missing', rel, 0, 'is a runtime file of no kind a build stamp is defined for'))
            read[rel] = None
            continue
        found, got = judge_file(rel, texts[rel], kind, stamp_name(rel, kind, quals))
        problems.extend(found)
        read[rel] = got[0] if got else None
        if got:
            at[rel] = got[1]
    plugin = read.get(BUILD)
    top = version_key(plugin)
    for rel in order:
        value = read.get(rel)
        if value is None:
            continue
        key = version_key(value)
        if key is None:
            problems.append(Problem('value', rel, at[rel] + 1, 'carries %r, which is not a version N.N.N' % value))
        elif top is not None and key > top:
            problems.append(Problem('value', rel, at[rel] + 1, 'carries %s, above PLUGIN_VERSION %s' % (value, plugin)))
    if BUILD in order:
        problems.extend(judge_table(texts[BUILD], order, read, at.get(BUILD)))
    return problems, read, at


# --- the tree ----------------------------------------------------------------

def _release():
    import release      # here, not at the top: release.py imports this module
    return release


def runtime_order(root):
    """release.py's runtime_files over <root>'s tracked files and its own
    ALLOWLIST: the plugin's runtime files in the order they are loaded."""
    release = _release()
    try:
        have = release.tracked(root)
        allow = set(release.allowlist_of(root))
    except (release.ReleaseError, OSError, ValueError, SyntaxError) as error:
        raise BuildStampsError('the runtime files of %s cannot be read: %s' % (root, error))
    return release.runtime_files(root, have, allow, [])


def read_texts(root, order):
    texts = {}
    for rel in order:
        try:
            with open(os.path.join(root, rel), encoding='utf-8', newline='') as fh:
                texts[rel] = fh.read()
        except (OSError, UnicodeDecodeError) as error:
            raise BuildStampsError('%s is unreadable: %s' % (rel, error))
    return texts


def problems(root, runtime=None):
    """The --check problems of <root>; `runtime` is the load order when the
    caller has it (release.py check passes its own)."""
    order = list(runtime) if runtime is not None else runtime_order(root)
    found, _stamps, _at = judge(read_texts(root, order), order)
    return found


def stamps(root, runtime=None):
    order = list(runtime) if runtime is not None else runtime_order(root)
    found, read, _at = judge(read_texts(root, order), order)
    return found, read


def manifest_version(root):
    try:
        with open(os.path.join(root, MANIFEST), encoding='utf-8') as fh:
            version = json.load(fh).get('version')
    except (OSError, ValueError, AttributeError) as error:
        raise BuildStampsError('%s is unreadable: %s' % (MANIFEST, error))
    if not isinstance(version, str):
        raise BuildStampsError('%s names no version' % MANIFEST)
    return version


def _git(root, *args):
    try:
        done = subprocess.run(['git', '-C', root] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BuildStampsError('git %s: %s' % (' '.join(args), error))
    if done.returncode != 0:
        raise BuildStampsError('git %s: %s' % (' '.join(args), done.stderr.decode('utf-8', 'replace').strip()))
    return done.stdout.decode('utf-8', 'replace')


def tree_blobs(root, order):
    """{file: the blob `git add` would store for it}, the filters applied."""
    ids = _git(root, 'hash-object', '--', *order).split()
    if len(ids) != len(order):
        raise BuildStampsError('git hash-object named %d blob(s) for %d file(s)' % (len(ids), len(order)))
    return dict(zip(order, ids))


def ref_blobs(root, ref, order):
    """{file: REF's blob, or None where REF has no such file}."""
    try:
        _git(root, 'rev-parse', '--verify', '--quiet', ref + '^{tree}')
    except BuildStampsError:
        raise BuildStampsError('%s names no commit or tree in %s' % (ref, root))
    out = dict((rel, None) for rel in order)
    for entry in _git(root, 'ls-tree', '-r', '-z', ref, '--', *order).split('\0'):
        if not entry:
            continue
        meta, rel = entry.split('\t', 1)
        _mode, kind, sha = meta.split()
        if rel in out and kind == 'blob':
            out[rel] = sha
    return out


def changed_files(root, ref, order):
    """The runtime files whose blob is not REF's, in load order."""
    mine, theirs = tree_blobs(root, order), ref_blobs(root, ref, order)
    return [rel for rel in order if mine[rel] != theirs[rel]]


def cut_problems(root, ref, version, runtime=None):
    """The cut's own check: a runtime file that differs from REF and does not
    carry `version` is `stale` (release.py build refuses on any)."""
    order = list(runtime) if runtime is not None else runtime_order(root)
    _found, read, at = judge(read_texts(root, order), order)
    out = []
    for rel in changed_files(root, ref, order):
        if read.get(rel) != version:
            out.append(Problem('stale', rel, at[rel] + 1 if rel in at else 0,
                               'differs from %s and carries %s, not %s, the version being cut (run build_stamps.py '
                               '--cut after the bump)' % (ref, read.get(rel) or 'no stamp', version)))
    return out


def restamped(text, line_at, kind, name, value):
    lines = text.split('\n')
    lines[line_at] = stamp_line(kind, name, value)
    return '\n'.join(lines)


def with_table(text, plugin_at, rows):
    """build.mjs with its BUILD_FILES block replaced by the generated one for
    `rows`, directly under its PLUGIN_VERSION line."""
    lines = text.split('\n')
    end = next(i for i, line in enumerate(lines) if TABLE_DECL.match(line))
    while lines[end] != '}':
        end += 1
    new = table_block(rows).split('\n')[:-1]
    return '\n'.join(lines[:plugin_at + 1] + new + lines[end + 1:])


def cut(root, ref='main', runtime=None, out=None):
    """Restamp <root> for manifest.json's version against REF. -> the files
    written, in load order. Raises Refused before writing anything."""
    out = out or sys.stdout
    order = list(runtime) if runtime is not None else runtime_order(root)
    texts = read_texts(root, order)
    found, read, at = judge(texts, order)
    if found:
        raise Refused(found)
    version = manifest_version(root)
    if version_key(version) is None:
        raise Refused([Problem('value', MANIFEST, 0, 'names %r, which is not a version N.N.N' % version)])
    if read.get(BUILD) != version:
        raise Refused([Problem('stale', BUILD, at[BUILD] + 1, 'PLUGIN_VERSION is %s and %s says %s: bump both before '
                               'the cut' % (read[BUILD], MANIFEST, version))])
    quals = qualifiers(texts)
    changed = changed_files(root, ref, order)
    new = dict(texts)
    now = collections.OrderedDict(read)
    for rel in changed:
        if rel == BUILD:
            continue
        kind = kind_of(rel, quals)
        new[rel] = restamped(texts[rel], at[rel], kind, stamp_name(rel, kind, quals), version)
        now[rel] = version
    new[BUILD] = with_table(new[BUILD], at[BUILD], [(rel, now[rel]) for rel in order if rel != BUILD])
    after, after_read, _at = judge(new, order)
    if after:
        raise Refused(after)            # a judge that disagrees with its own writer writes nothing
    written = [rel for rel in order if new[rel] != texts[rel]]
    for rel in written:
        path = os.path.join(root, rel)
        fd, tmp = tempfile.mkstemp(prefix='.build-stamps-', dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as fh:
                fh.write(new[rel])
            shutil.copymode(path, tmp)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    out.write('build-stamps: cut %s against %s: %s\n'
              % (version, ref, ('wrote ' + ', '.join(written)) if written else 'nothing to write'))
    return written


# --- the self-test -----------------------------------------------------------

def _case_tree(base, edits):
    files = collections.OrderedDict(base)
    for rel, change in (edits or {}).items():
        if change is None:
            files.pop(rel, None)
        elif isinstance(change, str):
            files[rel] = change
        else:
            text = files[rel]
            for old, new in change:
                if text.count(old) != 1:
                    raise ValueError('a case edit of %s finds %d copies of %r, not one' % (rel, text.count(old), old))
                text = text.replace(old, new)
            files[rel] = text
    return files


def _write_files(where, files):
    for rel, text in files.items():
        path = os.path.join(where, rel)
        os.makedirs(os.path.dirname(path) or where, exist_ok=True)
        with open(path, 'w', encoding='utf-8', newline='') as fh:
            fh.write(text)


def _run_git_case(case, base, order):
    """A --cut or --strict case in a scratch repository: REF is a commit of
    the case's `ref` edits, the tree its `edits` on top. -> what it got."""
    where = tempfile.mkdtemp(prefix='build-stamps-case-')
    try:
        env = dict(os.environ, GIT_AUTHOR_NAME='case', GIT_AUTHOR_EMAIL='case@example.invalid',
                   GIT_COMMITTER_NAME='case', GIT_COMMITTER_EMAIL='case@example.invalid',
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        def git(*args):
            subprocess.run(['git', '-C', where] + list(args), check=True, env=env, timeout=GIT_TIMEOUT,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git('init', '-q', '-b', 'ref')
        _write_files(where, _case_tree(base, case.get('ref')))
        git('add', '-A')
        git('commit', '-q', '-m', 'ref')
        tree = _case_tree(base, case.get('edits'))
        for rel in list(_case_tree(base, case.get('ref'))):
            if rel not in tree:
                os.unlink(os.path.join(where, rel))
        _write_files(where, tree)
        git('add', '-A')
        sink = open(os.devnull, 'w')
        try:
            if case['mode'] == 'strict':
                return {'stale': [p.file for p in cut_problems(where, 'ref', case['version'], runtime=order)]}
            try:
                first = cut(where, 'ref', runtime=order, out=sink)
            except Refused as refused:
                return {'refused': refused.problems[0].kind}
            second = cut(where, 'ref', runtime=order, out=sink)
            _f, read = stamps(where, runtime=order)
            return {'written': first, 'second': second, 'stamps': dict(read)}
        finally:
            sink.close()
    finally:
        shutil.rmtree(where, True)


def load_cases(cases_path=CASES):
    with open(cases_path, encoding='utf-8') as fh:
        return json.load(fh, object_pairs_hook=collections.OrderedDict)


def run_case(case, base):
    """(ok, what it got) for one case: its verdict is the one it expects."""
    mode = case.get('mode', 'check')
    # manifest.json and a repository's own dot-files are no runtime files.
    order = [rel for rel in _case_tree(base, case.get('edits')) if rel != MANIFEST and not rel.startswith('.')]
    want = case['expect']
    if mode == 'check':
        found, read, _at = judge(_case_tree(base, case.get('edits')), order)
        if 'refusal' in want:
            got = found[0].kind if found else 'clean'
            return got == want['refusal'], got
        got = {'problems': [str(p) for p in found], 'stamped': sum(1 for v in read.values() if v is not None)}
        return not found and got['stamped'] == want['stamped'], got
    if mode not in ('cut', 'strict'):
        raise ValueError('a case of no mode this script knows: %r' % mode)
    got = _run_git_case(case, base, order)
    return all(got.get(k) == v for k, v in want.items()), got


def self_test(cases_path=CASES):
    """(ran, wrong) over the cases: each case's verdict is the one it expects."""
    data = load_cases(cases_path)
    wrong = []
    for case in data['cases']:
        ok, got = run_case(case, data['base'])
        if not ok:
            wrong.append('%s (got %s)' % (case['name'], got))
    return len(data['cases']), wrong


# --- main --------------------------------------------------------------------

def check(root, run_self_test=True, out=None):
    out = out or sys.stdout
    try:
        order = runtime_order(root)
        found, read = stamps(root, runtime=order)
    except BuildStampsError as error:
        out.write('build-stamps: %s\n' % error)
        return 1
    for p in found:
        out.write('build-stamps: %s\n' % (p,))
    status = 1 if found else 0
    tail = ''
    if run_self_test:
        try:
            ran, wrong = self_test()
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            out.write('build-stamps: the self-test cases are unreadable: %s\n' % error)
            return 1
        for w in wrong:
            out.write('build-stamps: self-test case wrong: %s\n' % w)
        if wrong or not ran:
            status = 1
        tail = '; self-test %d of %d cases' % (ran - len(wrong), ran)
    if status == 0:
        out.write('build-stamps: check ok (%d runtime file(s), %d stamp(s) read, %d BUILD_FILES row(s)%s)\n'
                  % (len(order), sum(1 for v in read.values() if v is not None),
                     sum(1 for rel in order if rel != BUILD), tail))
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--cut', action='store_true')
    mode.add_argument('--strict', action='store_true')
    mode.add_argument('--json', action='store_true')
    parser.add_argument('--root', default=os.path.dirname(SCRIPT_DIR))
    parser.add_argument('--against', default='main', metavar='REF')
    parser.add_argument('--no-self-test', action='store_true', help='--check the tree alone')
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    if args.check:
        return check(root, not args.no_self_test)
    try:
        if args.json:
            found, read = stamps(root)
            for p in found:
                sys.stderr.write('build-stamps: %s\n' % (p,))
            sys.stdout.write(json.dumps(read, indent=1) + '\n')
            return 1 if found else 0
        if args.strict:
            stale = cut_problems(root, args.against, manifest_version(root))
            for p in stale:
                sys.stdout.write('build-stamps: %s\n' % (p,))
            if not stale:
                sys.stdout.write('build-stamps: strict ok against %s\n' % args.against)
            return 1 if stale else 0
        cut(root, args.against)
        return 0
    except Refused as refused:
        for p in refused.problems:
            sys.stdout.write('build-stamps: refused: %s\n' % (p,))
        return 1
    except BuildStampsError as error:
        sys.stdout.write('build-stamps: %s\n' % error)
        return 1


if __name__ == '__main__':
    sys.exit(main())
