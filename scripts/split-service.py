#!/usr/bin/env python3
"""scripts/split-service.py -- Service.qml and its code-behinds (D-REL-14).

WHY. release.py holds every shipped file under 448 KiB (D-REL-5), and
Service.qml reached 446,973 bytes in November. D-REL-14 splits its functions
by domain into classic JavaScript code-behinds that run in the component's
own scope, the way D-REL-5 split the model and D-REL-7 the helper:

  Service.qml          every property, signal, object and handler, the
                       functions that stay on the root, a line
                       `import "Service-<domain>.js" as Service<Domain>` per
                       code-behind, and a one-line forwarder at each moved
                       function's old place:
                         `  function F(a, b) { return ServicePip.F(a, b) }`
  Service-<domain>.js  each moved function byte for byte at the root's
                       two-space indent, with the `//` lines that sat
                       directly above it, and nothing else but blank lines
                       and loose `//` comments; no `.import`, no `.pragma`

Everything here reads the service through the readers
(scripts/service_files.py, whose twin is tests/service-files.js), never
through a list of its own: the files Service.qml declares and the INLINE
view, each forwarder read as the function it forwards to, which is the
one-file Service.qml the split was cut from.

MODES (exactly one):
  --check   the tree as it stands, which the gate runs, and then this
            script's own cases (tests/fixtures/service-split/check-cases.json),
            so the step can go red on the gate when this judge stops judging.
            The tree is refused for anything the readers refuse (a script
            import that is not a code-behind's, a code-behind line outside
            every function, a forwarder that is not exactly its function's,
            a code-behind function no forwarder names, a declared file that
            is not there, ...) and, on top of their verdict, for
              function-twice  a name declared twice at the root's indent of
                              Service.qml, forwarders included -- two
                              code-behinds holding one name is this -- or of
                              the inline view: a header at the root's indent
                              inside another code-behind function, which the
                              engine nests and the view reads twice
              undeclared      a script (`*.js`, `*.mjs`) beside Service.qml
                              that it does not import as a code-behind, but
                              the model's own (Model.mjs, and Model.js on a
                              tree from before D-REL-5): a spelling of an
                              import the readers do not see loads it all the
                              same (`/* c */ import "x.js" as X`). A script
                              another QML file imports is refused here too,
                              until a split of that file teaches this judge
                              its importer
              qualifier       a code-behind's qualifier named anywhere but in
                              its forwarders and its import: a body that
                              calls `ServicePip.F(` past the root is code the
                              inline view cannot hold, and it would skip
                              the harness's stand-ins for root functions
              scope           `this` or `arguments` in a code-behind: a
                              forwarder calls the function on the code-behind
                              and passes only the arguments it names, so
                              both read otherwise than on the root
              sibling         a code-behind naming one of its OWN functions
                              unqualified: whether that is the sibling or
                              the root's forwarder is the engine's scope
                              order, and `Qt.callLater` deduplicates by the
                              function it is handed; say `root.F`
              member          a `root.N` (or `root?.N`, `root["N"]`,
                              `root?.["N"]`) in
                              Service.qml or a code-behind where N is no
                              member of the root: its properties and
                              aliases, their change signals, its signals and
                              functions, and the members its type
                              (`Item`) and that type's prototypes carry in
                              the installed qmltypes. qmllint no longer
                              reads a moved body (its entries on Service.qml
                              fell from 433 to 139 on D-REL-14's prototype),
                              and it only ever warned, so this is the member
                              check it did, made a refusal, over every file;
                              ids are no members (`root.<id>` reads
                              undefined)
              unjudged        `root[<expression>]` or `root?.[<expression>]`:
                              whatever it reads, no
                              reading of the source can say
              scan            the tokenizer lost its place in a file
  --verify  --from-git REV: the inline view equals REV's byte for byte --
            REV's Service.qml itself when REV declares no code-behind, REV's
            own inline view when it does. Run it after a move against the
            commit the move was cut from (D-REL-7's verify): a move that
            changed one byte of a function, or lost a comment above one, is
            red here.
  --inline  print the inline view to stdout; nothing is written.
  --cut     --from REV, then --domain D NAME... or --map FILE (a JSON object,
            domain to names): one-time. Moves each named root function of
            REV's Service.qml, with the `//` lines directly above it, into
            Service-<domain>.js (appended to one REV already declares, after
            a header for a new one), leaves its forwarder at its old place,
            and declares a new code-behind after the model's import, the
            declarations in name order. It writes nothing unless the result
            passes --check's judge and its inline view equals REV's
            (`round-trip`), and it refuses a tree whose service files differ
            from REV's, or that holds anything at a new code-behind's path
            (`tree`), so nothing uncommitted is overwritten; then it
            runs --verify against REV. Refused too: a name that is no root
            function, a forwarder, or named twice, a header whose arguments
            are not plain names, code after a closing brace (`name`), a
            domain that is not lower-case letters and digits (`domain`).

`--root` (default: this script's tree) is the plugin root; `--qml-dir` (default
/usr/lib/qt6/qml) is where the root type's members are read.

USE. A move (D-REL-14's C3 and C4) is a commit of its own, cut from a clean
tree and proved against its parent:
  python3 scripts/split-service.py --cut --from HEAD --domain rewind seekState seekCtx ...
  python3 scripts/split-service.py --verify --from-git HEAD
  python3 scripts/split-service.py --check
then the new file goes on release.py's ALLOWLIST. After the split a function
is added to a code-behind by writing it there and its forwarder on the root,
which --check holds; `--inline` prints what every pin and the node harness's
inline readers read.

Exit status: 0 clean, 1 a problem (one line each), 2 usage.
Python 3 standard library only; ASCII only.
"""

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import service_files  # noqa: E402  the service's files and its inline view (D-REL-14)

DEFAULT_QML_DIR = '/usr/lib/qt6/qml'
CASES = os.path.join(os.path.dirname(SCRIPT_DIR), 'tests', 'fixtures', 'service-split', 'check-cases.json')
# A new code-behind's first lines. Loose `//` comments, which the view drops.
# It names no path under docs/, tests/ or scripts/: the file ships.
HEADER = ('// %s -- a code-behind of Service.qml (D-REL-14). Each function here was\n'
          '// moved byte for byte out of Service.qml, which reaches it through a\n'
          '// one-line forwarder left at its old place; it runs in Service.qml\'s own\n'
          '// scope. Edit a function here, never its forwarder.\n\n')
ROOT_ELEMENT = re.compile(r'^([A-Z][A-Za-z0-9_]*(?:\.[A-Z][A-Za-z0-9_]*)*) \{[ \t]*\r?$', re.M)
ROOT_ID = re.compile(r'^  id: ([A-Za-z_][A-Za-z0-9_]*)[ \t]*\r?$', re.M)
PROPERTY = re.compile(r'^  (?:(?:readonly|required|default) )*property [A-Za-z_][A-Za-z0-9_.<>]* ([A-Za-z_][A-Za-z0-9_]*)', re.M)
SIGNAL = re.compile(r'^  signal ([A-Za-z_][A-Za-z0-9_]*)', re.M)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPT_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The tokenizer of check-model-members.py (comments, strings, templates and
# regular-expression literals told apart), and the type-file reader of
# check-qt-revisions.py, which reads the installed qmltypes as its guard does.
qtrev = _load('check_qt_revisions', 'check-qt-revisions.py')
theme = qtrev.theme
members = theme.members


class Problem(Exception):
    def __init__(self, kind, message):
        Exception.__init__(self, '%s: %s' % (kind, message))
        self.kind = kind


def read(path):
    return service_files.read_text(path)


# --- what the root is -------------------------------------------------------

def root_of(text):
    """(type name, id) of Service.qml's root element."""
    m = ROOT_ELEMENT.search(text)
    if m is None:
        raise Problem('member', 'Service.qml has no root element this judge can read')
    found = ROOT_ID.search(text, m.end())
    if found is None:
        raise Problem('member', 'the root %s declares no `id:` at the root\'s indent' % m.group(1))
    return m.group(1), found.group(1)


def type_members(text, type_name, qml_dir, cache):
    """Every member name the root's type and its prototypes carry in the
    installed type files, through the modules Service.qml imports unqualified."""
    unqualified, _aliases, _dirs = theme.file_imports(text)
    limits = {}
    try:
        for uri, limit in list(qtrev.ALWAYS) + [(u, l) for u, l in unqualified if not u.startswith('qs.')]:
            qtrev.module_limits(uri, limit, qml_dir, limits)
        by_cpp, by_export = {}, {}
        for uri in sorted(limits):
            for c in qtrev.module_components(uri, qml_dir, cache):
                by_cpp.setdefault(c.name, c)
                for _module, name, _version in c.exports:
                    by_export.setdefault(name, c)
    except theme.Unreadable as error:
        raise Problem('member', 'the root type\'s members are unreadable: %s' % error)
    c = by_export.get(type_name.split('.')[-1])
    if c is None and '\r' in text:
        raise Problem('member', 'Service.qml has CR line ends, and its imports are read from LF-ended lines only, '
                      'so no module it imports is read and its root type %s is unknown' % type_name)
    if c is None:
        raise Problem('member', 'no module Service.qml imports exports its root type %s' % type_name)
    out, seen = set(), set()
    while c is not None and c.name not in seen:
        seen.add(c.name)
        for _kind, name, _version in c.members:
            out.add(name)
        c = by_cpp.get(c.prototype)
    if not out:
        raise Problem('member', 'the type files name no member of %s' % type_name)
    return out


def root_members(text, qml_dir, cache):
    """(the root's id, every name `root.N` may read), from Service.qml's own
    text and the installed type files."""
    type_name, rid = root_of(text)
    names = set(type_members(text, type_name, qml_dir, cache))
    for m in PROPERTY.finditer(text):
        names.add(m.group(1))
        names.add(m.group(1) + 'Changed')
    names.update(m.group(1) for m in SIGNAL.finditer(text))
    names.update(service_files.function_spans(text, 'Service.qml'))
    return rid, names


def member_sites(text, rid, label):
    """(sites, values, problems) of one file: every `<rid>.N`, `<rid>?.N`
    and `<rid>["N"]` in code as (line, col, N); how many times the id is used
    whole, as a value; and the uses no reading can judge."""
    try:
        toks = members.tokens(text)
    except members.ScanError as error:
        raise Problem('scan', '%s: the tokenizer lost its place at %s' % (label, error))
    sites, values, problems = [], 0, []
    for k, t in enumerate(toks):
        if t.kind != 'ident' or t.text != rid:
            continue
        prev = toks[k - 1] if k else None
        if prev is not None and prev.kind == 'punct' and prev.text in ('.', '?.'):
            continue
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        after = toks[k + 2] if k + 2 < len(toks) else None
        if nxt is not None and nxt.kind == 'punct' and nxt.text in ('.', '?.') and after is not None \
                and after.kind == 'ident':
            sites.append((after.line, after.col, after.text))
        elif nxt is not None and nxt.kind == 'punct' and (nxt.text == '[' or (
                nxt.text == '?.' and after is not None and after.kind == 'punct' and after.text == '[')):
            # `root[...]`, and `root?.[...]`, whose index opens a token later.
            at = k + 2 if nxt.text == '[' else k + 3
            key = toks[at] if at < len(toks) else None
            if key is not None and key.kind == 'str' and at + 1 < len(toks) and toks[at + 1].text == ']':
                sites.append((key.line, key.col, key.text))
            else:
                problems.append(Problem('unjudged', '%s:%d:%d: `%s[...]` is indexed by an expression, which no '
                                        'reading of the source can judge' % (label, t.line, t.col, rid)))
        elif not (prev is not None and prev.kind == 'punct' and prev.text == ':' and k >= 2
                  and toks[k - 2].kind == 'ident' and toks[k - 2].text == 'id'):
            values += 1
    return sites, values, problems


# --- the judge --------------------------------------------------------------

def forwarder_lines(text, qualifiers):
    """The 1-based lines of Service.qml that are a declaration or an exact
    forwarder of a declared qualifier: the only places a qualifier is named."""
    out = set()
    for n, line in enumerate(text.split('\n'), 1):
        m = service_files.FORWARDER.fullmatch(line)
        if m and m.group(3) in qualifiers:
            out.add(n)
        d = service_files.DECLARATION.fullmatch(line)
        if d and d.group(2) in qualifiers:
            out.add(n)
    return out


def code_problems(label, text, qualifiers, own, allowed_lines=()):
    """`qualifier`, `scope` and `sibling` problems of one file's code:
    `own` is the file's own function names (a code-behind's), or None for
    Service.qml, where only the qualifier rule applies."""
    try:
        toks = members.tokens(text)
    except members.ScanError as error:
        return [Problem('scan', '%s: the tokenizer lost its place at %s' % (label, error))]
    out = []
    for k, t in enumerate(toks):
        if t.kind != 'ident':
            continue
        prev = toks[k - 1] if k else None
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        member_of = prev is not None and prev.kind == 'punct' and prev.text in ('.', '?.') \
            and not theme.spread_before(toks, k)
        # An object literal's key (`{ socketAttached: root.socketAttached() }`)
        # names nothing; a ternary's branch, after `?`, does.
        key = nxt is not None and nxt.kind == 'punct' and nxt.text == ':' \
            and prev is not None and prev.kind == 'punct' and prev.text in ('{', ',')
        if member_of or key:
            continue
        if t.text in qualifiers and t.line not in allowed_lines:
            out.append(Problem('qualifier', '%s:%d:%d: `%s` is a code-behind\'s qualifier, named outside its '
                               'forwarders: call the root\'s function, `root.F(...)`' % (label, t.line, t.col, t.text)))
            continue
        if own is None:
            continue
        if t.text in ('this', 'arguments'):
            out.append(Problem('scope', '%s:%d:%d: `%s` in a code-behind reads otherwise than on the root: a '
                               'forwarder calls the function on the code-behind and passes only the arguments it '
                               'names' % (label, t.line, t.col, t.text)))
            continue
        if t.text in own and not (prev is not None and prev.kind == 'ident' and prev.text == 'function'):
            out.append(Problem('sibling', '%s:%d:%d: `%s` is one of this code-behind\'s own functions, named '
                               'unqualified; say `root.%s`' % (label, t.line, t.col, t.text, t.text)))
    return out


def judge(service, files, present, qml_dir, cache=None):
    """(problems, counts) for one service: `service` is Service.qml's text,
    `files` the declared code-behinds that are there (name -> text),
    `present` every script name (`*.js`, `*.mjs`) beside Service.qml."""
    cache = {} if cache is None else cache
    counts = {'files': 1, 'code_behinds': 0, 'root_functions': 0, 'forwarders': 0, 'moved': 0,
              'sites': 0, 'values': 0}
    try:
        view = service_files.inline_text(service, files)
        decls = service_files.declarations(service)
        root_spans = service_files.function_spans(service, 'Service.qml')
        # The view's own functions: a header at the root's indent inside a
        # code-behind function is a nested function to the engine, so its
        # forwarder finds nothing, and the view holds it twice.
        service_files.function_spans(view, 'the inline view')
    except service_files.ServiceFilesError as error:
        return [Problem(error.kind, 'refused by the readers: %s' % error)], counts
    problems = []
    declared = set(file for file, _q, _n in decls)
    qualifiers = set(q for _f, q, _n in decls)
    model = set(['Model.mjs'] + ([] if service_files.imports_a_module(service) else ['Model.js']))
    for name in sorted(set(present) - declared - model):
        problems.append(Problem('undeclared', '%s is beside Service.qml and Service.qml does not import it as a '
                                'code-behind: a script nothing loads, or one loaded by a spelling the readers '
                                'cannot see' % name))
    forwarders = forwarder_lines(service, qualifiers)
    problems += code_problems('Service.qml', service, qualifiers, None, forwarders)
    own_of = {}
    for file, _q, _n in decls:
        own_of[file] = list(service_files.function_spans(files[file], file))
        problems += code_problems(file, files[file], qualifiers, set(own_of[file]))
    counts['code_behinds'] = len(decls)
    counts['files'] = 1 + len(decls)
    counts['moved'] = sum(len(v) for v in own_of.values())
    counts['forwarders'] = counts['moved']
    counts['root_functions'] = len(root_spans) - counts['forwarders']
    try:
        rid, names = root_members(service, qml_dir, cache)
    except Problem as error:
        return problems + [error], counts
    for label, text in [('Service.qml', service)] + [(f, files[f]) for f, _q, _n in decls]:
        try:
            sites, values, unjudged = member_sites(text, rid, label)
        except Problem as error:
            problems.append(error)
            continue
        problems += unjudged
        counts['sites'] += len(sites)
        counts['values'] += values
        for line, col, name in sites:
            if name not in names:
                problems.append(Problem('member', '%s:%d:%d: `%s.%s` is no member of the root (its properties, '
                                        'signals and functions, and its type\'s): undefined at run time, and no '
                                        'other check reads a moved body' % (label, line, col, rid, name)))
    return problems, counts


def tree_inputs(root):
    """(Service.qml's text, the declared code-behinds that are there, every
    script beside it), read through the readers' own paths."""
    svc = service_files.service_path(root)
    service = read(svc)
    files = {}
    try:
        decls = service_files.declarations(service)
    except service_files.ServiceFilesError:
        decls = []
    for path in service_files.service_files(svc)[1:] if decls else []:
        if os.path.exists(path):
            files[os.path.basename(path)] = read(path)
    present = scripts_beside(os.listdir(os.path.dirname(svc) or '.'))
    return service, files, present


def scripts_beside(names):
    """The script files among the names beside Service.qml: `*.js` and
    `*.mjs`, which a QML file may import; the judge sets the model's apart."""
    return sorted(n for n in names if n.endswith(('.js', '.mjs')))


def self_test(qml_dir, cases_path=CASES):
    """(ran, wrong) over the synthetic cases: each case's verdict -- ok, or
    the first problem's kind -- is the one it expects."""
    with open(cases_path, encoding='utf-8') as fh:
        cases = json.load(fh)['cases']
    wrong, cache = [], {}
    for case in cases:
        present = case.get('present', scripts_beside(case['files']))
        problems, counts = judge(case['service'], case['files'], present, qml_dir, cache)
        want = case['expect']
        if 'refusal' in want:
            ok = bool(problems) and problems[0].kind == want['refusal']
        else:
            ok = not problems and all(counts.get(k) == v for k, v in want.get('counts', {}).items())
        if not ok:
            wrong.append('%s (got %s)' % (case['name'], problems[0] if problems else counts))
    return len(cases), wrong


def check(root, qml_dir, run_self_test=True, out=None):
    out = out or sys.stdout
    try:
        service, files, present = tree_inputs(root)
    except service_files.ServiceFilesError as error:
        out.write('split-service: %s\n' % error)
        return 1
    problems, counts = judge(service, files, present, qml_dir)
    for p in problems:
        out.write('split-service: %s\n' % p)
    status = 1 if problems else 0
    tail = ''
    if run_self_test:
        try:
            ran, wrong = self_test(qml_dir)
        except (OSError, ValueError, KeyError) as error:
            out.write('split-service: the self-test cases are unreadable: %s\n' % error)
            return 1
        for w in wrong:
            out.write('split-service: self-test case wrong: %s\n' % w)
        if wrong or not ran:
            status = 1
        tail = '; self-test %d of %d cases' % (ran - len(wrong), ran)
    if status == 0:
        out.write('split-service: check ok (%d file(s), %d code-behind(s), %d root function(s), %d forwarder(s), '
                  '%d root member site(s) judged, %d use(s) of the root whole%s)\n'
                  % (counts['files'], counts['code_behinds'], counts['root_functions'], counts['forwarders'],
                     counts['sites'], counts['values'], tail))
    return status


# --- verify and inline ------------------------------------------------------

def git_show(root, rev, rel):
    done = subprocess.run(['git', '-C', root, 'show', '%s:%s' % (rev, rel)], capture_output=True, timeout=120)
    if done.returncode != 0:
        raise Problem('git', 'git show %s:%s: %s' % (rev, rel, done.stderr.decode('utf-8', 'replace').strip()))
    return done.stdout


def first_difference(have, want):
    n = min(len(have), len(want))
    at = next((i for i in range(n) if have[i] != want[i]), n)
    return at, have.count(b'\n', 0, at) + 1


def rev_service(root, rev):
    """(REV's Service.qml, its declared code-behinds), from git."""
    service = git_show(root, rev, service_files.SERVICE).decode('utf-8')
    files = {}
    for file, _q, _n in service_files.declarations(service):
        files[file] = git_show(root, rev, file).decode('utf-8')
    return service, files


def verify(root, rev, out=None):
    """The tree's inline view against REV's: REV's Service.qml itself when
    REV declares no code-behind, which is the commit a first move is cut
    from, and REV's own inline view when it does."""
    out = out or sys.stdout
    try:
        service, files = rev_service(root, rev)
        want = service_files.inline_text(service, files).encode('utf-8')
        have = service_files.service_text(root).encode('utf-8')
    except (Problem, service_files.ServiceFilesError, UnicodeDecodeError) as error:
        out.write('split-service: %s\n' % error)
        return 1
    if have != want:
        at, line = first_difference(have, want)
        out.write('split-service: the inline view differs from %s:Service.qml at byte %d (line %d of the view; '
                  '%d bytes against %d)\n' % (rev, at, line, len(have), len(want)))
        return 1
    out.write('split-service: verify ok (the inline view is %s:Service.qml byte for byte, %d bytes)\n' % (rev, len(have)))
    return 0


# --- the cut ----------------------------------------------------------------

def qualifier_of(domain):
    """The qualifier of `Service-<domain>.js`, by the readers' own rule;
    None for a domain that is not lower-case letters and digits."""
    return service_files.code_behind_qualifier('Service-%s.js' % domain)


def forwarder_text(name, args, qualifier):
    return '  function %s(%s) { return %s.%s(%s) }' % (name, args, qualifier, name, args)


def cut_texts(service, rev_files, moves, qml_dir):
    """The files a cut writes: {name: text}, Service.qml among them.
    `service` and `rev_files` are REV's service; `moves` is [(domain, [names])]."""
    try:
        before = service_files.inline_text(service, rev_files)
        decls = service_files.declarations(service)
        found = []
        service_files.function_spans(service, 'Service.qml', found)
    except service_files.ServiceFilesError as error:
        raise Problem(error.kind, 'REV\'s service is refused by the readers: %s' % error)
    spans = dict((name, (args, start, end, close)) for name, args, start, end, close in found)
    declared = dict((q, f) for f, q, _n in decls)
    seen, plan = set(), []
    for domain, names in moves:
        if qualifier_of(domain) is None:
            raise Problem('domain', '`%s` is not a domain: lower-case letters and digits' % domain)
        if not names:
            raise Problem('domain', 'the domain %s names no function' % domain)
        for name in names:
            if name in seen:
                raise Problem('name', '%s is named twice' % name)
            seen.add(name)
            if name not in spans:
                raise Problem('name', '%s is no function at the root\'s indent of Service.qml' % name)
            args, start, end, close = spans[name]
            last = service[start:end].split('\n')[-1]
            fw = service_files.FORWARDER.fullmatch(last)
            if fw and fw.group(3) in declared:
                raise Problem('name', '%s is a forwarder already' % name)
            # The forwarder the move would leave, held to the readers' exact
            # form: its arguments plain names, its own header's.
            if not service_files.FORWARDER.fullmatch(forwarder_text(name, args, 'Q')):
                raise Problem('name', '%s takes (%s): a forwarder passes plain names only' % (name, args))
            eol = service.find('\n', close)
            if not service_files.tail_reads(service[close + 1:len(service) if eol == -1 else eol]):
                raise Problem('name', '%s has code after its closing brace on its line' % name)
            plan.append((domain, name, args, start, end))
    plan.sort(key=lambda p: p[3])
    # Service.qml with each moved span replaced by its forwarder, in file order.
    out, cursor = [], 0
    for domain, name, args, start, end in plan:
        q = qualifier_of(domain)
        out.append(service[cursor:start])
        out.append(forwarder_text(name, args, q))
        cursor = end
    out.append(service[cursor:])
    new_service = ''.join(out)
    files = dict(rev_files)
    new_decls = []
    for domain, names in moves:
        q = qualifier_of(domain)
        file = 'Service-%s.js' % domain
        body = '\n\n'.join(service[s:e] for d, _n, _a, s, e in plan if d == domain)
        if q in declared:
            if declared[q] != file:
                raise Problem('domain', '%s is declared for %s already' % (q, declared[q]))
            files[file] = files[file].rstrip('\n') + '\n\n' + body + '\n'
        else:
            files[file] = HEADER % file + body + '\n'
            new_decls.append('import "%s" as %s' % (file, q))
    if new_decls:
        lines = new_service.split('\n')
        at = [i for i, line in enumerate(lines) if service_files.DECLARATION.fullmatch(line)]
        if at:
            block = sorted(set(lines[i] for i in at) | set(new_decls))
            lines = lines[:at[0]] + block + [line for i, line in enumerate(lines[at[0]:], at[0]) if i not in at]
        else:
            model = [i for i, line in enumerate(lines) if service_files.MODEL_MJS_IMPORT.fullmatch(line)]
            if len(model) != 1:
                raise Problem('domain', 'Service.qml must import the model once, `import "Model.mjs" as Model`, '
                              'for a new code-behind to be declared after it')
            lines = lines[:model[0] + 1] + sorted(new_decls) + lines[model[0] + 1:]
        new_service = '\n'.join(lines)
    try:
        after = service_files.inline_text(new_service, files)
    except service_files.ServiceFilesError as error:
        raise Problem(error.kind, 'the cut is refused by the readers: %s' % error)
    if after != before:
        at, line = first_difference(after.encode('utf-8'), before.encode('utf-8'))
        raise Problem('round-trip', 'the cut\'s inline view differs from REV\'s at byte %d (line %d)' % (at, line))
    problems, _counts = judge(new_service, files, scripts_beside(files), qml_dir)
    if problems:
        raise Problem(problems[0].kind, 'the cut is refused by --check: %s' % problems[0])
    files[service_files.SERVICE] = new_service
    return files


def cut(root, rev, moves, qml_dir, out=None):
    out = out or sys.stdout
    try:
        service, rev_files = rev_service(root, rev)
        for name, text in [(service_files.SERVICE, service)] + sorted(rev_files.items()):
            path = os.path.join(root, name)
            if not os.path.isfile(path) or read(path) != text:
                raise Problem('tree', '%s differs from %s:%s; commit or stash first, so the cut overwrites nothing '
                              'uncommitted' % (path, rev, name))
        written = cut_texts(service, rev_files, moves, qml_dir)
        # A new code-behind's path must be empty: an untracked or ignored
        # file there is no file of REV's, and writing would lose it.
        for name in sorted(written):
            if name == service_files.SERVICE or name in rev_files:
                continue
            if os.path.lexists(os.path.join(root, name)):
                raise Problem('tree', '%s is there and is no file of %s\'s service; move it away first, so the cut '
                              'overwrites nothing uncommitted' % (os.path.join(root, name), rev))
    except (Problem, service_files.ServiceFilesError, UnicodeDecodeError) as error:
        out.write('split-service: %s\n' % error)
        return 1
    for name in sorted(written):
        if written[name] == (service if name == service_files.SERVICE else rev_files.get(name)):
            continue
        with open(os.path.join(root, name), 'w', encoding='utf-8', newline='') as fh:
            fh.write(written[name])
        out.write('split-service: wrote %s (%d bytes)\n' % (name, len(written[name].encode('utf-8'))))
    return verify(root, rev, out)


def parse_moves(args):
    if args.map:
        with open(args.map, encoding='utf-8') as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or not all(isinstance(v, list) for v in data.values()):
            raise ValueError('--map wants a JSON object, domain to a list of names')
        return [(d, list(data[d])) for d in sorted(data)]
    if not args.domain or not args.names:
        raise ValueError('--cut wants --domain D NAME... or --map FILE')
    return [(args.domain, list(args.names))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--verify', action='store_true')
    mode.add_argument('--inline', action='store_true')
    mode.add_argument('--cut', action='store_true')
    parser.add_argument('--from-git', metavar='REV')
    parser.add_argument('--from', dest='from_rev', metavar='REV')
    parser.add_argument('--root', default=os.path.dirname(SCRIPT_DIR))
    parser.add_argument('--qml-dir', default=DEFAULT_QML_DIR)
    parser.add_argument('--no-self-test', action='store_true', help='--check the tree alone')
    parser.add_argument('--domain')
    parser.add_argument('--map')
    parser.add_argument('names', nargs='*')
    args = parser.parse_args(argv)
    if args.check:
        if args.names or args.from_git or args.from_rev:
            parser.error('--check takes no names and no revision')
        return check(args.root, args.qml_dir, not args.no_self_test)
    if args.verify:
        if not args.from_git or args.names:
            parser.error('--verify wants --from-git REV')
        return verify(args.root, args.from_git)
    if args.inline:
        try:
            text = service_files.service_text(args.root)
        except service_files.ServiceFilesError as error:
            sys.stdout.write('split-service: %s\n' % error)
            return 1
        sys.stdout.buffer.write(text.encode('utf-8'))
        return 0
    if not args.from_rev:
        parser.error('--cut wants --from REV')
    try:
        moves = parse_moves(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return cut(args.root, args.from_rev, moves, args.qml_dir)


if __name__ == '__main__':
    sys.exit(main())
