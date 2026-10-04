"""
The Answer's Prose Rules in Linear Time

Seven of the expressions in ANSWER_PROSE_RULES take more than linear time
on some input: a long run of one fence marker, many unclosed widget
openings, a delimiter row of blanks that does not end, an unclosed tag or
label repeated, a heading followed by a long tail of blanks. The build
removes what those seven match with readers instead. These tests hold each
reader to exactly its expression's result on seeded random answers, hold
the rule set as a whole to the expressions applied in order, and hold the
time to linear.

Version: v1.8.0
"""

import os
import random
import sys
import time
import zlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.processors import stories
from telar.processors.stories import ANSWER_PROSE_RULES, _ANSWER_PROSE_READERS

RULES = {rule.name: rule for rule in ANSWER_PROSE_RULES}

# The alphabets and tokens each rule's fuzz draws from.
CHARS = {
    'widget': list(':') * 3 + list('ab_9') + [' ', '\t', '\n', '\n'],
    'fenced code block': list('``````~~~ \t\n\n\na'),
    'table': list('|-: \t\na'),
    'heading mark': list('# \t\na'),
}
TOKENS = {
    'image or embed': ['![', '](', ']', '[', ')', '<img', '<IMG ', '</img>',
                       '</IFRAME >', '<iframe', '<video', '<Audio x', '</audio',
                       '>', 'a', ' ', '\n', '</img\n>'],
    'footnote definition': ['[^', ']', ':', '\n', ' ', '\t', 'a', '\n ', ']:'],
    'footnote reference': ['[^', ']', ':', '\n', ' ', 'a', '[', '^'],
}


# Whole lines, for the rules whose matches need several lines in a row.
LINES = {
    'widget': ['', ' ', ':::', ':::a', ' :::b_1 ', '::: ', ':::a x', 'a', '\t:::\t', '::::'],
    'table': ['a|', '|', '|-|', '--', ' -- | -- ', ':-:|', 'a', '| a |', '-- |', '|--|--|'],
}


def answers(name, count, seed):
    rng = random.Random(seed)
    for n in range(count):
        size = rng.randint(0, 40)
        if name in LINES and n % 2:
            yield '\n'.join(rng.choices(LINES[name], k=rng.randint(0, 8))) + rng.choice(['', '\n'])
        elif name in TOKENS:
            yield ''.join(rng.choices(TOKENS[name], k=size // 2))
        else:
            yield ''.join(rng.choices(CHARS[name], k=size))


@pytest.mark.parametrize('name', sorted(_ANSWER_PROSE_READERS))
def test_reader_matches_expression_on_random_answers(name):
    rule = RULES[name]
    reader = _ANSWER_PROSE_READERS[name]
    matched = 0
    checked = 0
    for text in answers(name, 25000, seed=zlib.crc32(name.encode())):
        expected = rule.pattern.subn(rule.replacement, text)
        assert reader(text) == expected, repr(text)
        checked += 1
        matched += expected[1] > 0
    assert checked == 25000
    assert matched > 500


def test_fenced_reader_matches_expression_on_structured_answers():
    rule = RULES['fenced code block']
    reader = _ANSWER_PROSE_READERS['fenced code block']
    rng = random.Random(6210)
    for _ in range(5000):
        lines = []
        for _ in range(rng.randint(1, 8)):
            lines.append(rng.choice(['', ' ', '\t']) + rng.choice('`~') * rng.randint(0, 6)
                         + rng.choice(['', 'py', ' x', ' ']))
        text = '\n'.join(lines) + rng.choice(['', '\n'])
        assert reader(text) == rule.pattern.subn('', text), repr(text)


def test_the_rules_together_match_the_expressions_in_order():
    rng = random.Random(62100)
    pieces = ['```', '~~~', ':::a', ':::', '| a |', '|---|', '# ', '## x ##',
              '![a](b)', '<img src=x>', '</img>', '[^1]', '[^1]: note', '> ',
              '- ', '1. ', '---', 'word', ' ', '\n', '\n', '\t', '#']
    for _ in range(4000):
        text = ''.join(rng.choices(pieces, k=rng.randint(0, 30)))
        expected = text
        for rule in ANSWER_PROSE_RULES:
            expected = rule.pattern.sub(rule.replacement, expected)
        assert stories._reduce_answer_to_prose(text)[0] == expected, repr(text)


def test_a_fenced_block_is_reported_through_the_reader():
    text = 'before\n```\ncode\n```\nafter'
    assert stories._reduce_answer_to_prose(text) == ('before\nafter', ['markup'])


# name -> shape -> text of size n, the worst shapes for that rule.
SHAPES = {
    'widget': {
        'unclosed openings': lambda n: ':::a\n' * n,
        'openings then closes': lambda n: ':::a\n' * n + ':::\n' * n,
        'blank name tail': lambda n: ':::a' + ' ' * n + 'x',
    },
    'fenced code block': {
        'bare tick': lambda n: '`' * n,
        'bare tilde': lambda n: '~' * n,
        'tick newline': lambda n: '`' * n + '\n',
        'tilde newline': lambda n: '~' * n + '\n',
        'run then shorter lines': lambda n: '`' * n + '\n' + '``\n' * (n // 8),
        'run then close': lambda n: '`' * n + '\nbody\n' + '`' * n,
        'many openings': lambda n: '```x\n' * n,
    },
    'table': {
        'blank delimiter row': lambda n: 'a|\n' + ' ' * n + 'x',
        'blank delimiter tail': lambda n: 'a|\n--' + ' ' * n + 'x',
        'dashes': lambda n: 'a|\n' + '-' * n + 'x',
        'cells': lambda n: 'a|\n' + '-|' * n + 'x',
        'headers only': lambda n: 'a|\n' * n,
    },
    'image or embed': {
        'unclosed tags': lambda n: '<img ' * n,
        'tags without closes': lambda n: '<img>' * n,
        'tags and far close': lambda n: '<img>a' * n,
        'alt text unclosed': lambda n: '![' + '![a]' * n,
        'link target unclosed': lambda n: '![a](' * n,
        'nested brackets': lambda n: '![' + '[a]' * n + 'x',
    },
    'footnote definition': {
        'unclosed labels': lambda n: '[^a\n' * n,
        'definitions': lambda n: '[^a]: x\n' * n,
        'continuations': lambda n: '[^a]:\n x' + '\n x' * n,
        'label then no colon': lambda n: '[^a\n' * n + ']x',
    },
    'footnote reference': {
        'unclosed': lambda n: '[^a' * n,
        'unclosed lines': lambda n: '[^a\n' * n,
    },
    'heading mark': {
        'blank tail': lambda n: '# a' + ' ' * n + 'b',
        'hash tail': lambda n: '# ' + '#' * n + 'x',
        'many headings': lambda n: '# a #\n' * n,
    },
}
CASES = [(name, shape) for name in sorted(SHAPES) for shape in sorted(SHAPES[name])]


@pytest.mark.parametrize('name,shape', CASES)
def test_readers_take_linear_time(name, shape):
    text = SHAPES[name][shape](40000)
    begun = time.perf_counter()
    _ANSWER_PROSE_READERS[name](text)
    assert time.perf_counter() - begun < 0.5


@pytest.mark.parametrize('name,shape', CASES)
def test_readers_agree_with_the_expression_on_the_worst_shapes(name, shape):
    rule = RULES[name]
    text = SHAPES[name][shape](300)
    assert _ANSWER_PROSE_READERS[name](text) == rule.pattern.subn(rule.replacement, text)


def test_the_other_rules_are_linear_without_a_reader():
    others = [r for r in ANSWER_PROSE_RULES if r.name not in _ANSWER_PROSE_READERS]
    assert sorted(r.name for r in others) == [
        'blockquote mark', 'horizontal rule', 'list marker']
    shapes = ['-' * 40000 + 'x', '- ' * 20000 + 'x', '-' + ' ' * 40000 + 'x',
              '>' * 40000, '> ' * 20000 + 'x', ' ' * 40000 + 'x', '1' * 40000 + 'x',
              '---x\n' * 8000, '> a\n' * 10000, '- a\n' * 10000, '\t' * 40000]
    for rule in others:
        for text in shapes:
            begun = time.perf_counter()
            rule.pattern.subn(rule.replacement, text)
            assert time.perf_counter() - begun < 0.5, (rule.name, text[:20])


# A reader writes the replacement its rule had when it was written. A rule
# whose replacement changes has to have its reader changed with it.
READER_REPLACEMENTS = {
    'widget': '', 'fenced code block': '', 'table': '', 'image or embed': '',
    'footnote definition': '', 'footnote reference': '', 'heading mark': '\\1',
}


def test_each_reader_writes_its_rules_replacement():
    rules = {rule.name: rule.replacement for rule in ANSWER_PROSE_RULES
             if rule.name in _ANSWER_PROSE_READERS}
    assert rules == READER_REPLACEMENTS


@pytest.mark.parametrize('text', [
    '<img>X</\u0131mg>', '<IMG>X</img>', '<img>X</IMG >', '<Video>a</vIDEO>b',
    '<\u0131mg>X</img>', '<img>X</\u0130MG>', '<\u0130MG>X</img>', '<img>X</\u2170mg>',
])
def test_a_closing_tag_is_matched_as_the_backreference_matches_it(text):
    rule = next(r for r in ANSWER_PROSE_RULES if r.name == 'image or embed')
    assert _ANSWER_PROSE_READERS['image or embed'](text) == rule.pattern.subn(rule.replacement, text)


@pytest.mark.parametrize('name, text', [
    ('heading mark', '# a' + ' ' * 40000 + 'b'),
    ('heading mark', '# a' + ' \t' * 20000 + 'b'),
    ('table', 'a|\n' + ' ' * 40000 + 'x'),
])
def test_a_long_run_of_blanks_inside_a_line_takes_linear_time(name, text):
    start = time.perf_counter()
    _ANSWER_PROSE_READERS[name](text)
    assert time.perf_counter() - start < 0.5
