"""Where the helper's code lives, read from the helper itself (D-REL-7).

`bin/omarchy-iptv` is a stub: it makes the process non-dumpable (D-SINK-9)
and then compiles the parts under `bin/helper/`, in the order its
`HELPER_PARTS` tuple lists, into its own namespace, so the parts behave as
the one file they were cut from (scripts/split-helper.py cuts and checks
them; docs/HELPER-SPLIT.md says why). Anything in Python that needs the
helper's FILES -- the release allowlist's resolver, a pin that reads the
helper's source, a copy of the plugin tree -- asks this module, and this
module reads the part list out of the stub with `ast`. There is no second
list: a part the stub does not name is a part the running helper never
compiles, which is the failure the gate goes red on.

A stub that assigns no HELPER_PARTS is a one-file helper (every tree before
D-REL-7, and a `--baseline` export of one): its parts are none and its
source is the stub, so the same readers work on both.

Python 3 standard library only.
"""

import ast
import os
import re
import shutil

STUB = 'bin/omarchy-iptv'
PART_DIR = 'bin/helper'
PART_NAME = re.compile(r'^[0-9]{2}-[a-z][a-z0-9-]*\.py$')


class HelperLayoutError(Exception):
    pass


def part_names(stub_text):
    """The names HELPER_PARTS assigns at the stub's top level, in order, or
    () when it assigns none. Read with `ast.literal_eval`, never by running
    the stub, so a reader cannot be made to execute anything."""
    try:
        tree = ast.parse(stub_text)
    except SyntaxError as error:
        raise HelperLayoutError('%s does not parse: %s' % (STUB, error))
    found = [node for node in tree.body if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'HELPER_PARTS' for t in node.targets)]
    if not found:
        return ()
    if len(found) > 1:
        raise HelperLayoutError('%s assigns HELPER_PARTS twice' % STUB)
    try:
        value = ast.literal_eval(found[0].value)
    except ValueError:
        raise HelperLayoutError('%s: HELPER_PARTS is not a literal' % STUB)
    if (not isinstance(value, tuple) or not value
            or not all(isinstance(v, str) and PART_NAME.match(v) for v in value)):
        raise HelperLayoutError('%s: HELPER_PARTS is not a tuple of part names like '
                                '"01-core.py"' % STUB)
    if len(set(value)) != len(value):
        raise HelperLayoutError('%s names a part twice in HELPER_PARTS' % STUB)
    return value


def read(root, rel):
    with open(os.path.join(root, rel), encoding='utf-8') as fh:
        return fh.read()


def part_paths(root):
    """The parts, repo-relative, in the order the stub compiles them."""
    try:
        stub = read(root, STUB)
    except OSError as error:
        raise HelperLayoutError('%s is unreadable: %s' % (STUB, error))
    return ['%s/%s' % (PART_DIR, name) for name in part_names(stub)]


def helper_paths(root):
    """Every file of the helper, repo-relative: the stub, then the parts."""
    return [STUB] + part_paths(root)


def helper_source(root):
    """The stub's text and then every part's, in the order the stub compiles
    them: what a reader that used to read the one-file helper reads now."""
    return ''.join(read(root, rel) for rel in helper_paths(root))


def copy_helper(root, dest, stub_name=None):
    """Copy the helper into `dest`, keeping the layout the stub resolves its
    parts by (`bin/helper/` beside it). `stub_name` renames the stub only,
    for a harness that puts a wrapper in its place; the parts are found from
    the stub's own directory whatever it is called."""
    for rel in helper_paths(root):
        target = os.path.join(dest, rel)
        if rel == STUB and stub_name:
            target = os.path.join(dest, os.path.dirname(STUB), stub_name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(root, rel), target)
    return os.path.join(dest, STUB)
