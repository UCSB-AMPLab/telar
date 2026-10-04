"""
The Answer Cut in Linear Time

The word limit's cut must not land inside a glossary reference, a link, an
HTML tag, a code span or maths. It finds each of those once, where the
regular expressions it stood for searched the rest of the answer again
from every opening that had no close; and it steps back past them with a
search rather than a pass over every span. These tests hold the spans and
the cut to exactly what the expressions and the pass gave, on seeded
random answers, and hold the time to linear.

Version: v1.8.0
"""

import os
import random
import re
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.code_spans import code_spans
from telar.latex import latex_spans
from telar.processors import stories
from telar.processors.stories import _answer_atomic_spans, _cut_answer

# The expressions the atomic spans stand for, in the same order.
EXPRESSIONS = [
    re.compile(r'\[\[[^\]]*\]\]'),
    re.compile(r'\[[^\]]*\]\([^)]*\)'),
    re.compile(r'<[^>]+>'),
]

PIECES = ['[', ']', '[[', ']]', '(', ')', '<', '>', '<>', 'a', 'b c', ' ', '\n', '`', '$x^2$',
          '\\(', '\\)']


def _random_answers(count, seed=574):
    rng = random.Random(seed)
    return [''.join(rng.choice(PIECES) for _ in range(rng.randint(1, 20)))
            for _ in range(count)]


def _spans_by_expressions(text):
    spans = [m.span() for e in EXPRESSIONS for m in e.finditer(text)]
    return spans + latex_spans(text) + code_spans(text)


def _cut_by_pass(text, limit):
    """The cut as it stepped back before: every span checked on each step."""
    boundaries = [match.end() for match in re.finditer(r'\S+', text)]
    if len(boundaries) <= limit:
        return text
    spans = _spans_by_expressions(text)
    cut = boundaries[limit - 1]
    while True:
        straddled = [start for start, end in spans if start < cut < end]
        if not straddled:
            break
        cut = min(straddled)
        earlier = [end for end in boundaries if end <= cut]
        cut = earlier[-1] if earlier else 0
    return text[:cut] + stories._ANSWER_ELLIPSIS


def test_spans_are_the_expressions_spans():
    for answer in _random_answers(5000):
        assert _answer_atomic_spans(answer) == _spans_by_expressions(answer), answer


def test_the_cut_is_unchanged():
    for answer in _random_answers(5000, seed=575):
        for limit in (1, 2, 3, 5):
            assert _cut_answer(answer, limit) == _cut_by_pass(answer, limit), (answer, limit)


@pytest.mark.parametrize('unit', [' <', ' [[', ' [x](', ' [', '<a> ', '[a b](c) ', '[[a b]] ',
                                  '`a b` ', ' \\(', ' \\begin{align}'])
def test_bounded(unit):
    started = time.perf_counter()
    _cut_answer('a <u>' + unit * 20000, 5)
    assert time.perf_counter() - started < 1.0
