"""Where the model's code lives, read from the model itself (D-REL-5).

The model is `Model.mjs`, an aggregator that re-exports the public names from
parts under `model/` (scripts/split-model.mjs cuts and checks them). Anything
in Python that needs the model's FILES -- a structural pin that reads the
source, a copy of the plugin tree, the release allowlist's resolver, the
defect ledger's symbol index -- asks this module, and this module reads the
part list out of `Model.mjs`'s own `from "./model/<part>.mjs"` lines. There is
no second list: a part added to the aggregator is seen by every reader, and a
part missing from it is missing from the running plugin too, which is the
failure the gate goes red on.

Python 3 standard library only.
"""

import os
import re
import shutil

AGGREGATOR = 'Model.mjs'
PART_DIR = 'model'
# `} from "./model/x.mjs"` closes a generated block; an empty block is one line.
PART_REF = re.compile(r'^(?:\}|export \{\}) from "\./(model/[a-z][a-z0-9-]*\.mjs)"$', re.M)


class ModelLayoutError(Exception):
    pass


def part_paths(root):
    """The parts, repo-relative, in the aggregator's order."""
    agg = os.path.join(root, AGGREGATOR)
    try:
        with open(agg, encoding='utf-8') as fh:
            text = fh.read()
    except OSError as error:
        raise ModelLayoutError('%s is unreadable: %s' % (agg, error))
    parts = PART_REF.findall(text)
    if not parts:
        raise ModelLayoutError('%s names no part under %s/' % (agg, PART_DIR))
    if len(set(parts)) != len(parts):
        raise ModelLayoutError('%s names a part twice' % agg)
    return parts


# A generated re-export block of the aggregator: `export {`, the names, then
# `} from "./model/x.mjs"` (or the one-line empty form, which names nothing).
EXPORT_BLOCK = re.compile(r'^export \{\n((?:  [^\n]*\n)*)\} from "\./model/[a-z][a-z0-9-]*\.mjs"$', re.M)


def public_names(root):
    """The names Model.mjs re-exports, in its order: what QML sees as
    `Model.<name>`. Read from the generated export blocks, the same text the
    engine loads; split-model.mjs --check proves the loaded namespace is
    exactly this list."""
    agg = os.path.join(root, AGGREGATOR)
    try:
        with open(agg, encoding='utf-8') as fh:
            text = fh.read()
    except OSError as error:
        raise ModelLayoutError('%s is unreadable: %s' % (agg, error))
    names = []
    for block in EXPORT_BLOCK.findall(text):
        names.extend(n.strip() for n in block.replace('\n', ',').split(',') if n.strip())
    if not names:
        raise ModelLayoutError('%s re-exports no name' % agg)
    return names


def model_paths(root):
    """Every file of the model, repo-relative: the aggregator, then the parts."""
    return [AGGREGATOR] + part_paths(root)


def read_part(root, rel):
    with open(os.path.join(root, rel), encoding='utf-8') as fh:
        return fh.read()


def model_source(root):
    """The parts' text, concatenated in the aggregator's order: what a pin that
    used to read the one-file model reads now. The aggregator itself carries
    only the header and the generated export lines, so it is left out."""
    return ''.join(read_part(root, rel) for rel in part_paths(root))


def file_containing(root, needle):
    """The one model file whose text contains `needle`. A needle found in no
    file, or in more than one, is an error rather than a guess."""
    hits = [rel for rel in model_paths(root) if needle in read_part(root, rel)]
    if len(hits) != 1:
        raise ModelLayoutError('%r is in %d model files (%s), not exactly one'
                               % (needle, len(hits), ', '.join(hits) or 'none'))
    return hits[0]


def copy_model(root, dest):
    """Copy the model's files into `dest`, keeping their relative layout, so
    `dest/Model.mjs` imports the same parts it does at `root`."""
    for rel in model_paths(root):
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(root, rel), target)
    return os.path.join(dest, AGGREGATOR)
