"""
Glossary Links Found in Linear Time

A glossary link is `[[term]]` or `[[term|display]]`. The regular expression
that stood for the syntax searched the rest of the text again from every
`[[` that had no close, and backtracked over a run of whitespace before a
`|`, so a run of `[` took seconds. `find_glossary_links` finds the same
links in one pass. These tests hold its links to exactly the expression's
matches -- start, end and both groups -- on hand cases and on seeded random
text, since the Compositor reads the syntax with that expression and the
two must agree on every input; and they hold the time to linear.

Version: v1.8.0
"""

import os
import random
import re
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.glossary import find_glossary_links

# The expression the finder stands for, as the Compositor still reads it.
EXPRESSION = re.compile(r'\[\[\s*([^|\]]+?)(?:\s*\|\s*([^|\]]+?))?\s*\]\]')


def _by_expression(text):
    return [(m.start(), m.end(), m.group(1), m.group(2)) for m in EXPRESSION.finditer(text)]


def _by_finder(text):
    return [(link.start, link.end, link.term, link.display) for link in find_glossary_links(text)]


HAND_CASES = [
    '',
    '[[encomienda]]',
    '[[[encomienda]]]',
    '[[encomienda [note]]]',
    '[[[[x]]]]',
    '[[a|b]]',
    '[[ a | b ]]',
    '[[a|b|c]]',
    '[[a||b]]',
    '[[a|]]',
    '[[|x]]',
    '[[|]]',
    '[[ | ]]',
    '[[a| ]]',
    '[[ |a]]',
    '[[   ]]',
    '[[ ]]',
    '[[]]',
    '[[',
    '[[a',
    '[[a|b',
    '[[a]',
    '[[a|b]',
    ']]',
    'x]] [[y',
    '[[a\nb]]',
    '[[\na\n|\nb\n]]',
    '[[a]]b]]',
    '[[a]] [[b|c]] [[d]]',
    '[[a]][[b]]',
    '[[a\\]]',
    '[[\\|x]]',
    '[[a\\|b]]',
    '`[[a]]`',
    '[[a `b` c]]',
    '[[ a |　b ]]',
    '[[\x1ca\x1f]]',
    '[ [a]]',
    '[[ [ ]]',
    '[[a]]]]',
    '[[[a|b]]]',
    '[[a|[b]]]',
]


@pytest.mark.parametrize('text', HAND_CASES)
def test_hand_cases_match_the_expression(text):
    assert _by_finder(text) == _by_expression(text)


def test_random_text_matches_the_expression():
    rng = random.Random(562)
    alphabet = ['[', ']', '|', ' ', 'a', '\n', '\r']
    for _ in range(20000):
        text = ''.join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        assert _by_finder(text) == _by_expression(text), repr(text)


def test_random_pieces_match_the_expression():
    rng = random.Random(5620)
    pieces = ['[[', ']]', '[', ']', '|', ' ', '  ', 'a', 'bc', '\n', '\r', '\r\n', '\t', ' ', '\\', '`']
    for _ in range(20000):
        text = ''.join(rng.choice(pieces) for _ in range(rng.randint(0, 20)))
        assert _by_finder(text) == _by_expression(text), repr(text)


@pytest.mark.parametrize('text', [
    '[' * 20000,
    '[[' * 10000,
    '[[a|' * 5000,
    '[[' + 'a' * 20000,
    '[[' + ' ' * 20000 + '|',
    '[[a' + ' ' * 20000 + '|a|',
    '[[a|' + ' ' * 20000 + '|',
    '[[a]' * 5000,
    '[[ ' * 7000,
    '[[a]]' * 4000,
], ids=['open', 'double-open', 'open-pipe', 'open-then-text', 'open-spaces-pipe',
        'spaces-before-pipe', 'spaces-after-pipe', 'single-close', 'open-space',
        'many-links'])
def test_bounded(text):
    started = time.perf_counter()
    list(find_glossary_links(text))
    assert time.perf_counter() - started < 0.5
