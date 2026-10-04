"""Unit Tests for the Answer Budget

`telar.answer_budget` is the rule the Compositor mirrors, so its cases live
in a fixture both read: `tests/fixtures/answer-budget.json`, answer HTML ->
words, paragraphs, cost and the cut HTML. These tests hold the module to
the fixture, and hold the cut to the two properties the rule promises: a
cut answer fits, and cutting it again changes nothing.

Version: v1.8.0
"""

import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar import answer_budget
from telar.answer_budget import cut_to_budget, fits, measure_answer

FIXTURE = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'answer-budget.json')

with open(FIXTURE, encoding='utf-8') as _f:
    SHARED = json.load(_f)

CASES = SHARED['cases']


def test_the_fixture_states_the_constants_the_module_uses():
    assert (SHARED['budget'], SHARED['paragraph_cost'], SHARED['max_paragraphs']) == (
        answer_budget.ANSWER_BUDGET, answer_budget.PARAGRAPH_COST,
        answer_budget.MAX_PARAGRAPHS) == (85, 15, 5)


@pytest.mark.parametrize('case', CASES, ids=[case['name'] for case in CASES])
def test_the_measure_is_the_fixtures(case):
    assert tuple(measure_answer(case['html'])) == (case['words'], case['paragraphs'], case['cost'])


@pytest.mark.parametrize('case', CASES, ids=[case['name'] for case in CASES])
def test_the_cut_is_the_fixtures(case):
    assert cut_to_budget(case['html']) == case['cut']


@pytest.mark.parametrize('case', CASES, ids=[case['name'] for case in CASES])
def test_a_cut_answer_fits_and_cutting_it_again_changes_nothing(case):
    cut = cut_to_budget(case['html'])

    assert fits(cut)
    assert cut_to_budget(cut) == cut


def _random_answer(rng):
    """Paragraphs of words, some inside links and emphasis."""
    paragraphs = []
    for _ in range(rng.randint(1, 12)):
        words = []
        for _ in range(rng.randint(0, rng.choice((3, 40)))):
            word = 'w%d' % rng.randint(0, 999)
            shape = rng.random()
            if shape < 0.1:
                word = '<a href="x">%s %s</a>' % (word, word)
            elif shape < 0.2:
                word = '<em>%s</em>' % word
            words.append(word)
        paragraphs.append('<p>%s</p>' % ' '.join(words))
    return '\n'.join(paragraphs)


def test_the_cut_holds_its_promises_on_random_answers():
    rng = random.Random(682)
    for _ in range(2000):
        answer = _random_answer(rng)
        cut = cut_to_budget(answer)
        assert fits(cut), answer
        assert cut_to_budget(cut) == cut, answer
        if fits(answer):
            assert cut == answer


def test_a_cut_never_ends_inside_a_link():
    rng = random.Random(683)
    for _ in range(2000):
        cut = cut_to_budget(_random_answer(rng))
        # Every link the cut keeps is the whole link: two words.
        for kept in cut.split('<a href="x">')[1:]:
            assert len(kept.split('</a>')[0].split()) == 2, cut


def test_an_answer_over_five_paragraphs_keeps_its_first_five_however_short():
    answer = ''.join('<p>w%d</p>' % n for n in range(1, 8))

    assert not fits(answer)
    assert cut_to_budget(answer) == '<p>w1</p><p>w2</p><p>w3</p><p>w4</p><p>w5…</p>'
    assert fits('<p>a</p>' * answer_budget.MAX_PARAGRAPHS)
