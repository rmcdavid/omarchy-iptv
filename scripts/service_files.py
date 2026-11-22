"""The service as the files Service.qml declares (D-REL-14).

D-REL-14 splits Service.qml's functions into classic JavaScript code-behinds,
`Service-<domain>.js`, each imported by Service.qml as
`import "Service-<domain>.js" as Service<Domain>` and reached through a
one-line forwarder left at the function's old place,
`  function F(a, b) { return ServicePip.F(a, b) }`. Anything in Python that
needs the service's FILES (a tree copy, a reader that judges each file) or
its TEXT (a pin on a function's body) asks this module, never Service.qml
directly:

  service_files(where)  the files, Service.qml first, then each code-behind
                        its `import "<file>.js" as <Q>` lines declare, in
                        their order;
  service_text(where)   the INLINE view: Service.qml with each declaration
                        line dropped and each forwarder line replaced by its
                        function's text in the code-behind -- the contiguous
                        `//` lines directly above `  function F(` and the
                        function through its closing brace's line. That is
                        the one-file Service.qml the split was cut from, so
                        a text pin never moves.

`where` is a plugin root, or the path of the service's file: a path ending in
`.qml`, or any regular file (IPTV_SERVICE_QML may name a mutant copy called
anything); code-behinds are read from that file's directory, as the QML
engine resolves them. While Service.qml declares no code-behind,
service_files is [Service.qml] and service_text is its text exactly. A tree
from before D-REL-5 (2026-10-12) imports its one-file model as
`import "Model.js" as Model`; that exact line is the model's import, not a
code-behind, so it is neither declared nor refused and stays in the view,
and such a tree -- a `--baseline` export -- reads as its Service.qml. Only
such a tree: one that imports no ES module, as every tree before D-REL-5 did.
On a text that imports Model.mjs a `Model.js` import is a script import like
any other, so it is held to the code-behind's name and refused, never kept
unread (D-REL-14 C2, the recheck of 76bff05's proposal).

A code-behind is named for its domain: `Service-<domain>.js`, the domain
lower-case letters and digits, imported as `Service<Domain>` -- the domain
with its first letter upper-cased (`Service-pip.js` as `ServicePip`). The
one ES module Service.qml imports is the model, exactly
`import "Model.mjs" as Model`; any other `.mjs` import is refused (kind
`module`), because it is neither a code-behind the view reads in nor text
the view can vouch for: its forwarders would stay as root text and its body
unread.

Its twin is tests/service-files.js, and the two agree byte for byte: one
shared fixture (tests/fixtures/service-split/) runs in both, and each
engine's test runs the other over the tree and the fixture. So the text is
read as the node reader reads it: lines split at "\\n" only, a "\\r" kept as
text (no universal-newline translation, which pathlib's read_text applies),
and bytes that are not UTF-8 refused rather than replaced. A refusal is a
ServiceFilesError whose `kind` is one of the node reader's: declaration,
module, declared-twice, missing, encoding, function-twice, unbalanced, stray,
not-exact, no-function, forwarded-twice, unforwarded (tests/service-files.js
says what each means; `stray` includes text after a function's closing
brace on its line that is neither blank nor a `//` comment, which the
harness, reading a function from its header to its brace, would drop). So
the view holds every line of every code-behind but its blank lines and
loose `//` comments, and runs as the forwarders do
(their arguments plain names, the function's own); the rest of the layout is
scripts/split-service.py --check's to judge (D-REL-14's C2).

CLI: `service_files.py names|files|text <where>` prints the file names
(relative to Service.qml's directory), the paths, or the inline view; exit 1
with one line on stderr on a refusal, 2 on a usage error.

Python 3 standard library only, ASCII only.
"""

import os
import re
import sys

SERVICE = 'Service.qml'

DECLARATION = re.compile(r'import "([A-Za-z0-9_][A-Za-z0-9_.-]*\.js)" as ([A-Z][A-Za-z0-9_]*)\r?')
# Either quote: QML takes both, and DECLARATION (double quotes) refuses the
# single, so no spelling drops a code-behind in silence.
IMPORTS_A_SCRIPT = re.compile(r'[ \t]*import[ \t]+(?:"[^"]*\.js"|\'[^\']*\.js\')')
# The model's own import on a tree from before D-REL-5, read whole: the model
# was Model.js until it became Model.mjs and model/, and a --baseline export
# of such a tree is read as it is, not refused. Only on a text that imports
# no ES module (MODULE_IMPORT), which is what such a tree is.
MODEL_JS_IMPORT = re.compile(r'import "Model\.js" as Model\r?')
# A code-behind's name and qualifier: `Service-<domain>.js` as
# `Service<Domain>`, the domain lower-case letters and digits.
CODE_BEHIND = re.compile(r'Service-([a-z][a-z0-9]*)\.js')
# Any import of an ES module, in either quote, and the one Service.qml may
# hold: the model's, exactly.
MODULE_IMPORT = re.compile(r'[ \t]*import[ \t]+(?:"[^"]*\.mjs"|\'[^\']*\.mjs\')')
MODEL_MJS_IMPORT = re.compile(r'import "Model\.mjs" as Model\r?')
HEADER = re.compile(r'  function ([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\) \{')
COMMENT_LINE = re.compile(r'[ \t]*//')
BLANK_LINE = re.compile(r'[ \t]*\r?')
FORWARDER_SHAPE = re.compile(r'  function ([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\) \{ return ([A-Z][A-Za-z0-9_]*)\.')
# The exact form's arguments are plain names: a default or a pattern repeated
# in the call is an assignment or an object there, not the value passed.
FORWARDER = re.compile(r'  function ([A-Za-z_][A-Za-z0-9_]*)\(((?:[A-Za-z_][A-Za-z0-9_]*(?:, [A-Za-z_][A-Za-z0-9_]*)*)?)\) '
                       r'\{ return ([A-Z][A-Za-z0-9_]*)\.\1\(\2\) \}\r?')
# The node reader's rule for a "/" that opens a regular-expression literal,
# and JavaScript's `\s`, written as code points so this file stays ASCII.
REGEX_AFTER = set('(,=:[!&|?{};+-*%<>~^\n')
JS_SPACE = set(chr(c) for c in (0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x20, 0xa0, 0x1680, 0x2028, 0x2029,
                                0x202f, 0x205f, 0x3000, 0xfeff)) | set(chr(c) for c in range(0x2000, 0x200b))


def imports_a_module(text):
    """Whether any line of `text` imports an ES module: true of every
    Service.qml since D-REL-5 (Model.mjs), and of none before it."""
    return any(MODULE_IMPORT.match(line) for line in text.split('\n'))


def imports_a_script(line, modern=True):
    """Whether `line` imports a classic script that may be a code-behind:
    any `.js` import, in either quote, but the pre-D-REL-5 model's on a text
    that imports no ES module (`modern` false)."""
    return bool(IMPORTS_A_SCRIPT.match(line)) and (modern or not MODEL_JS_IMPORT.fullmatch(line))


def code_behind_qualifier(file):
    """The qualifier a code-behind's name gives it, `Service-pip.js` ->
    `ServicePip`; None for a name that is not `Service-<domain>.js`."""
    m = CODE_BEHIND.fullmatch(file)
    return None if m is None else 'Service' + m.group(1)[:1].upper() + m.group(1)[1:]


def tail_reads(text):
    """Whether the text after a code-behind function's closing brace, to
    the end of its line, is blank or a `//` comment: anything else is code
    the view would place after a root function and the harness would drop."""
    return bool(BLANK_LINE.fullmatch(text) or COMMENT_LINE.match(text))


class ServiceFilesError(Exception):
    def __init__(self, kind, message):
        Exception.__init__(self, '%s: %s' % (kind, message))
        self.kind = kind


def match_brace(text, open_at):
    """The index of the "}" matching the "{" at `open_at`, skipping strings,
    comments and regular-expression literals; -1 when there is none. The
    node reader's matchBrace (tests/service-harness.js scan()), step for
    step, indices included."""
    depth = 0
    prev = ''
    n = len(text)
    i = open_at
    while i < n:
        c = text[i]
        if c == '/' and text[i + 1:i + 2] == '/':
            i = text.find('\n', i)
            if i == -1:
                return -1
            prev = '\n'
            i += 1
            continue
        if c == '/' and text[i + 1:i + 2] == '*':
            i = text.find('*/', i + 2)
            if i == -1:
                return -1
            i += 2
            continue
        if c in '"\'`':
            i += 1
            while i < n and text[i] != c:
                if text[i] == '\\':
                    i += 1
                i += 1
            prev = c
            i += 1
            continue
        if c == '/' and (prev or '\n') in REGEX_AFTER:
            cls = False
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == '[':
                    cls = True
                elif text[i] == ']':
                    cls = False
                elif text[i] == '/' and not cls:
                    break
                i += 1
            prev = '/'
            i += 1
            continue
        if c in '{([':
            depth += 1
        elif c in '})]':
            depth -= 1
            if depth == 0 and c == '}':
                return i
        if c not in JS_SPACE:
            prev = c
        i += 1
    return -1


def declarations(text):
    """[(file, qualifier, line)] in order."""
    out = []
    modern = imports_a_module(text)
    for n, line in enumerate(text.split('\n'), 1):
        if MODULE_IMPORT.match(line) and not MODEL_MJS_IMPORT.fullmatch(line):
            raise ServiceFilesError('module', 'line %d imports an ES module and is not the model\'s '
                                    '`import "Model.mjs" as Model`' % n)
        if not imports_a_script(line, modern):
            continue
        m = DECLARATION.fullmatch(line)
        if not m:
            raise ServiceFilesError('declaration', 'line %d imports a script and is not `import "<file>.js" as <Qualifier>`' % n)
        for file, qualifier, at in out:
            if file == m.group(1):
                raise ServiceFilesError('declared-twice', '%s is declared on lines %d and %d' % (file, at, n))
            if qualifier == m.group(2):
                raise ServiceFilesError('declared-twice', 'the qualifier %s is declared on lines %d and %d' % (qualifier, at, n))
        if code_behind_qualifier(m.group(1)) != m.group(2):
            raise ServiceFilesError('declaration', 'line %d declares %s as %s, and a code-behind is '
                                    '`import "Service-<domain>.js" as Service<Domain>`, the domain lower-case '
                                    'letters and digits' % (n, m.group(1), m.group(2)))
        out.append((m.group(1), m.group(2), n))
    return out


def function_spans(text, label='', found=None):
    """Every function at the two-space indent of `text`, by name (in file
    order), as its text: the contiguous `//` lines directly above the header,
    through the end of the closing brace's line, its newline not included.
    `found`, when given, gets one (name, args, start, end, close) a
    function: its header's argument text, the span's offsets, end
    exclusive, and its closing brace's offset."""
    out = {}
    at = 0
    while True:
        m = HEADER.match(text, at)
        if m:
            close = match_brace(text, m.end() - 1)
            if close == -1:
                raise ServiceFilesError('unbalanced', '%s: %s has no closing brace' % (label or 'the text', m.group(1)))
            start = at
            while start > 0:
                prev_end = start - 1
                prev_start = 0 if prev_end == 0 else text.rfind('\n', 0, prev_end) + 1
                if not COMMENT_LINE.match(text[prev_start:prev_end]):
                    break
                start = prev_start
            eol = text.find('\n', close)
            if m.group(1) in out:
                raise ServiceFilesError('function-twice', '%s declares %s twice' % (label or 'the text', m.group(1)))
            end = len(text) if eol == -1 else eol
            out[m.group(1)] = text[start:end]
            if found is not None:
                found.append((m.group(1), m.group(2), start, end, close))
        nl = text.find('\n', at)
        if nl == -1:
            break
        at = nl + 1
    return out


def stray_line(text, found):
    """The first line (1-based) of a code-behind's `text` that holds text
    outside every span in `found` that is neither blank nor a `//` comment:
    a whole line outside them, or a span's closing line whose text after the
    closing brace is not (tail_reads); 0 when there is none. Such text is
    code the inline view would drop, or place where the harness drops it."""
    at = 0
    n = 1
    while True:
        nl = text.find('\n', at)
        stop = len(text) if nl == -1 else nl
        line = text[at:stop]
        if any(start <= at < end for _name, _args, start, end, _close in found):
            if any(at <= close < stop and not tail_reads(text[close + 1:stop])
                   for _name, _args, _start, _end, close in found):
                return n
        elif not BLANK_LINE.fullmatch(line) and not COMMENT_LINE.match(line):
            return n
        if nl == -1:
            return 0
        at = nl + 1
        n += 1


def inline_text(text, files):
    """The inline view of a Service.qml text over its code-behinds' texts,
    `files` mapping each declared file name to its text."""
    decls = declarations(text)
    if not decls:
        return text
    by_qualifier = {}
    for file, qualifier, line in decls:
        body = files.get(file)
        if not isinstance(body, str):
            raise ServiceFilesError('missing', '%s is declared (line %d) and is not there' % (file, line))
        found = []
        spans = function_spans(body, file, found)
        stray = stray_line(body, found)
        if stray:
            raise ServiceFilesError('stray', '%s line %d holds text outside every function that is neither blank nor a // comment'
                                    % (file, stray))
        by_qualifier[qualifier] = (file, spans, dict((name, args) for name, args, _s, _e, _c in found), set())
    out = []
    modern = imports_a_module(text)
    for line in text.split('\n'):
        if imports_a_script(line, modern):
            continue
        shape = FORWARDER_SHAPE.match(line)
        if shape and shape.group(3) in by_qualifier:
            m = FORWARDER.fullmatch(line)
            if not m:
                raise ServiceFilesError('not-exact', '`%s` calls %s and is not `function F(args) { return %s.F(args) }`'
                                        % (line.strip(), shape.group(3), shape.group(3)))
            file, spans, own_args, used = by_qualifier[m.group(3)]
            if m.group(1) not in spans:
                raise ServiceFilesError('no-function', '%s is forwarded to %s, which has no such function' % (m.group(1), file))
            if m.group(1) in used:
                raise ServiceFilesError('forwarded-twice', '%s of %s has two forwarders' % (m.group(1), file))
            if own_args.get(m.group(1)) != m.group(2):
                raise ServiceFilesError('not-exact', '`%s` takes (%s) and %s in %s takes (%s)'
                                        % (line.strip(), m.group(2), m.group(1), file, own_args.get(m.group(1))))
            used.add(m.group(1))
            out.append(spans[m.group(1)])
            continue
        out.append(line)
    for file, spans, _own_args, used in by_qualifier.values():
        left = [name for name in spans if name not in used]
        if left:
            raise ServiceFilesError('unforwarded', '%s holds %s, which no forwarder names' % (file, ', '.join(left)))
    return '\n'.join(out)


def read_text(path):
    try:
        with open(path, 'rb') as fh:
            data = fh.read()
    except FileNotFoundError:
        raise ServiceFilesError('missing', '%s is not there' % path)
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        raise ServiceFilesError('encoding', '%s is not UTF-8' % path)


def service_path(where):
    """A path ending in `.qml`, or any regular file, is the service's file;
    anything else is a plugin root holding Service.qml."""
    where = str(where)
    return where if where.endswith('.qml') or os.path.isfile(where) else os.path.join(where, SERVICE)


def service_names(where):
    """The file names, relative to Service.qml's directory: its own first."""
    svc = service_path(where)
    return [os.path.basename(svc)] + [file for file, _q, _n in declarations(read_text(svc))]


def service_files(where):
    svc = service_path(where)
    return [svc] + [os.path.join(os.path.dirname(svc), file) for file, _q, _n in declarations(read_text(svc))]


def service_text(where):
    svc = service_path(where)
    text = read_text(svc)
    decls = declarations(text)
    if not decls:
        return text
    files = {}
    for file, _q, _n in decls:
        path = os.path.join(os.path.dirname(svc), file)
        if os.path.exists(path):
            files[file] = read_text(path)
    return inline_text(text, files)


def main(argv):
    if len(argv) != 2 or argv[0] not in ('names', 'files', 'text'):
        sys.stderr.write('usage: service_files.py names|files|text <plugin root or Service.qml>\n')
        return 2
    verb, where = argv
    try:
        if verb == 'names':
            out = ''.join(name + '\n' for name in service_names(where))
        elif verb == 'files':
            out = ''.join(path + '\n' for path in service_files(where))
        else:
            out = service_text(where)
    except (ServiceFilesError, OSError) as error:
        sys.stderr.write('service_files: %s\n' % error)
        return 1
    sys.stdout.buffer.write(out.encode('utf-8'))
    sys.stdout.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
