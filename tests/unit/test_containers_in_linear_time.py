"""
Quotes and List Items Nested Deep Are Read in Linear Time

A quote or list item holds blocks, and `telar.kramdown_blocks` reads each
one's content again as a text of its own. Nested many deep, each level
would read what is left of the answer once more; the levels read as
containers are bounded, and a content's place in the answer is kept a
stretch per line, so an answer of any nesting is read in time linear in
its length. Each of these, nested thousands deep, takes well under a
second, through the readers and through the answer limit that runs them
on every step.

Version: v1.8.0
"""

import os
import sys
import time

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.code_spans import answer_regions, code_spans
from telar.processors.stories import _limit_answers, _reduce_answer_to_prose

# After a block HTML element's close a mark survives the prose rules, and
# each one opens a container inside the last. The indented items are list
# items on lines of their own, each indented as the content of the one
# before it.
_NESTED = {
    'list items': '<div>x</div>' + '- ' * 9992 + '`x`',
    'quotes': '<div>x</div>' + '> ' * 9992 + '`x`',
    'quotes and list items': '<div>x</div>' + '> - ' * 4996 + '`x`',
    'indented items': '<div>x</div>' + ''.join('  ' * i + '- `a`\n' for i in range(2000)),
    'items with lazy lines': '<div>x</div>' + '- ' * 2000 + '`a`' + '\nb `c`' * 5000,
}


@pytest.mark.parametrize('shape', list(_NESTED))
def test_the_readers_are_bounded(shape):
    started = time.perf_counter()
    code_spans(_NESTED[shape])
    answer_regions(_NESTED[shape])
    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize('shape', ['list items', 'quotes', 'quotes and list items'])
def test_the_answer_limit_is_bounded(shape):
    answer = _NESTED[shape]
    assert _reduce_answer_to_prose(answer)[0] == answer
    frame = pd.DataFrame({'step': [1], 'answer': [answer]})
    started = time.perf_counter()
    _limit_answers(frame, 'my-story', [], [])
    assert time.perf_counter() - started < 1.0


def test_the_code_at_the_bottom_is_found():
    # Past the depth read as containers, the content is read as paragraphs,
    # where the code span is still code.
    answer = _NESTED['list items']
    assert code_spans(answer) == [(len(answer) - 3, len(answer))]
