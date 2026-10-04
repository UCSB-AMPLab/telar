"""
LaTeX Spans in Linear Time

`telar.latex` finds each LaTeX block once: an opening, then the first of
each close after it. The regular expressions it stood for searched the
rest of the text again from every opening that had no close, so a panel
or answer with many openings took time growing with the square of its
length. These tests hold the finders to exactly what those expressions
matched, on seeded random text, and hold the time to linear.

Version: v1.8.0
"""

import hashlib
import os
import random
import re
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar import latex
from telar.latex import protect_latex, restore_latex

# The expressions the finders stand for, in the same order.
EXPRESSIONS = [
    re.compile(r'\$\$.+?\$\$', re.DOTALL),
    re.compile(r'\\begin\{.*?\}.*?\\end\{.*?\}', re.DOTALL),
    re.compile(r'\\\[.*?\\\]', re.DOTALL),
    re.compile(r'\\\(.*?\\\)', re.DOTALL),
    re.compile(r'\\ce\{[^}]*\}'),
    re.compile(r'\$(\S[^$]*?\S|\S)\$'),
]

PIECES = ['$', '$$', '\\(', '\\)', '\\[', '\\]', '\\begin{', '\\end{', '{', '}', '\\ce{',
          'x', 'a^2', ' ', '\n', '\\']


def _random_texts(count, seed=574):
    rng = random.Random(seed)
    return [''.join(rng.choice(PIECES) for _ in range(rng.randint(1, 16)))
            for _ in range(count)]


def _has_latex_by_expressions(text):
    """`has_latex` as the expressions did it."""
    if not text:
        return False
    if (EXPRESSIONS[0].search(text) or '\\begin{' in text or '\\(' in text
            or '\\[' in text or '\\ce{' in text):
        return True
    return any(re.search(r'[\\^_{]', m.group(1)) for m in EXPRESSIONS[5].finditer(text))


def _restored_by_replacing(html, replacements):
    """`restore_latex` as it replaced each placeholder in turn."""
    for placeholder, original in replacements.items():
        html = html.replace(placeholder, original)
    return html


def _protected_by_expressions(text):
    """`protect_latex` as the expressions did it."""
    if not text or not _has_latex_by_expressions(text):
        return text, {}
    replacements = {}

    def placeholder(match):
        original = _restored_by_replacing(match.group(0), replacements)
        key = f"TLATEX{hashlib.md5(original.encode()).hexdigest()[:12]}END"
        replacements[key] = original
        return key
    for expression in EXPRESSIONS:
        text = expression.sub(placeholder, text)
    return text, replacements


def test_each_finder_matches_its_expression():
    for text in _random_texts(5000):
        for finder, expression in zip(latex._PROTECT_PATTERNS, EXPRESSIONS):
            assert finder(text) == [m.span() for m in expression.finditer(text)], (text, expression)


def test_detection_is_unchanged():
    for text in _random_texts(5000, seed=577):
        assert latex.has_latex(text) == _has_latex_by_expressions(text), text


def test_protected_and_restored_text_is_unchanged():
    for text in _random_texts(3000, seed=576):
        protected, replacements = protect_latex(text)
        assert (protected, replacements) == _protected_by_expressions(text), text
        assert restore_latex(protected, replacements) == _restored_by_replacing(protected, replacements)


def test_many_distinct_blocks():
    text = ''.join(f'\\({i}\\) ' for i in range(20000))
    started = time.perf_counter()
    protected, replacements = protect_latex(text)
    assert restore_latex(protected, replacements) == text
    assert time.perf_counter() - started < 2.0


@pytest.mark.parametrize('unit', ['$$ ', '\\( ', '\\[ ', '\\begin{align} ', '\\begin{a}x ',
                                  '\\ce{ ', '$$x$$ '])
def test_bounded(unit):
    started = time.perf_counter()
    protect_latex('\\(x\\) ' + unit * 20000)
    assert time.perf_counter() - started < 1.0
