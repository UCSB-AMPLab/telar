"""
A docblock documents the thing directly below it, or it documents nothing.

One defect produced all nine that v1.7.0 shipped: a helper is extracted from
a function and inserted between that function's docblock and the function.
The helper brings its own docblock, so the reader meets two in a row, and the
first describes something several hundred lines away. The code stays valid
and the comment stays in the file, which is why nothing caught it — including
the 1.7.0 review, which reported it twice from opposite ends without
recognising the two reports as one thing: `activateCard`'s docblock is wrong,
and `activateCard` is undocumented.

The consequence was that `card-pool.js` appeared to leave both its entry
points, `initCardPool` and `activateCard`, without documentation.

The shape is mechanically checkable, which is the whole reason this file
exists: the class is not removed until its detector is installed. A block
that documents a callable — one carrying `@param` or `@returns` — must not be
followed immediately by another block with nothing in between.

Module headers are deliberately not caught. A header followed by the first
function's docblock is the correct arrangement, and an early version of this
scan reported every module in the tree because it did not distinguish them.
Requiring `@param` or `@returns` is what separates the two.

Version: v1.8.0
"""

import re
from pathlib import Path

import pytest

JS_DIR = Path(__file__).resolve().parents[2] / 'assets' / 'js'

# The esbuild output. Generated, and it concatenates its sources, so a bundle
# reproduces whatever its modules hold and would report each finding twice.
BUNDLES = {'telar-story.js', 'object-image.js', 'object-video.js',
           'object-audio.js', 'home-page.js', 'objects-index-page.js',
           'iiif-url-warning.js', 'objects-filter.js', 'share-panel.js'}

DOCBLOCK = re.compile(r'/\*\*.*?\*/', re.S)
DOCUMENTS_A_CALLABLE = re.compile(r'@(param|returns)\b')


def _sources():
    return sorted(p for p in JS_DIR.rglob('*.js')
                  if p.name not in BUNDLES and not p.name.endswith('.min.js'))


def _orphans(path):
    """Blocks documenting a callable with another block, not code, below."""
    source = path.read_text(encoding='utf-8')
    blocks = [(m.start(), m.end(), m.group(0))
              for m in DOCBLOCK.finditer(source)]
    found = []
    for index, (start, end, text) in enumerate(blocks[:-1]):
        if not DOCUMENTS_A_CALLABLE.search(text):
            continue
        if source[end:blocks[index + 1][0]].strip():
            continue
        line = source[:start].count('\n') + 1
        summary = next(l.strip(' */') for l in text.splitlines() if l.strip(' */\n'))
        found.append(f'{path.name}:{line}  {summary}')
    return found


@pytest.mark.parametrize('path', _sources(), ids=lambda p: p.name)
def test_no_docblock_is_separated_from_what_it_documents(path):
    orphans = _orphans(path)
    assert not orphans, (
        'These document a callable but are followed by another docblock '
        'rather than by code, so they describe something further down the '
        'file:\n  ' + '\n  '.join(orphans))


def test_the_detector_finds_the_shape_it_is_looking_for(tmp_path):
    """The scan itself, against the arrangement that caused all nine.

    Without this the suite above passes equally well when the regex stops
    matching anything, which is the failure mode a guard like this has.
    """
    drifted = tmp_path / 'drifted.js'
    drifted.write_text(
        '/**\n * Do the thing.\n *\n * @param {number} n\n * @returns {number}\n */\n'
        '/**\n * A helper that arrived between them.\n */\n'
        'function helper() {}\n'
        'function doTheThing(n) { return n; }\n',
        encoding='utf-8')
    assert len(_orphans(drifted)) == 1

    attached = tmp_path / 'attached.js'
    attached.write_text(
        '/**\n * Do the thing.\n *\n * @param {number} n\n */\n'
        'function doTheThing(n) { return n; }\n'
        '/**\n * A helper below it.\n */\n'
        'function helper() {}\n',
        encoding='utf-8')
    assert _orphans(attached) == []


def test_a_module_header_above_a_first_docblock_is_not_an_orphan(tmp_path):
    """The false positive the first version of this scan produced."""
    module = tmp_path / 'module.js'
    module.write_text(
        '/**\n * Telar Story — Something\n *\n * What the module is for.\n *\n'
        ' * @version v1.8.0\n */\n'
        '/**\n * The first function.\n *\n * @param {number} n\n */\n'
        'function first(n) { return n; }\n',
        encoding='utf-8')
    assert _orphans(module) == []
