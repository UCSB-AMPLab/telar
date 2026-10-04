"""
Unit Tests for LaTeX in a Story Step's Answer

A step's answer is rendered by kramdown, through `markdownify` in
story-step.html, not by `convert_markdown`, so the hold that keeps maths away
from Python Markdown never reached it. kramdown eats the backslash of
`\\(` `\\)` `\\[` `\\]`, so KaTeX found no delimiters, and reads `*` and `_`
inside `$...$` as emphasis. Its own `$$...$$` is the one form it prints as
written: `\\(...\\)` inside a paragraph, `\\[...\\]` as a paragraph of its own.

So the build gives each answer whose maths would be misread an
`answer_kramdown`, the same answer with each formula as `$$...$$`, and
story-steps.html hands that to the step. `answer` stays as the build read it.

The last class builds a small Jekyll site from the real includes and reads
the HTML each answer renders to. Jekyll needs the Ruby the Gemfile asks for;
where it cannot run, that class is skipped and says so.

Version: v1.8.0
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.processors.stories import _answer_maths_for_kramdown, _prepare_answer_maths

REPO = Path(__file__).resolve().parents[2]


class TestEachDelimiterBecomesKramdownMaths:

    @pytest.mark.parametrize('written, expected', [
        ('Area \\(x^2\\) here', 'Area $$x^2$$ here'),
        ('\\[y_1\\]', '$$y_1$$'),
        ('Inline $a*b*c^2$ here', 'Inline $$a*b*c^2$$ here'),
        ('\\begin{align} a &= b \\\\ c \\end{align}',
         '$$\\begin{align} a &= b \\\\ c \\end{align}$$'),
        ('$\\ce{H2O}$', '$$\\ce{H2O}$$'),
        ('Two \\(a_1\\) and $b^2$', 'Two $$a_1$$ and $$b^2$$'),
    ], ids=['paren', 'bracket', 'dollar', 'environment', 'chemistry', 'two'])
    def test_rewritten(self, written, expected):
        assert _answer_maths_for_kramdown(written) == expected

    def test_kramdown_maths_is_unchanged(self):
        assert _answer_maths_for_kramdown('Inline $$a*b$$ here') == 'Inline $$a*b$$ here'


class TestWhatIsNotMathsIsLeftAsWritten:

    @pytest.mark.parametrize('written', [
        'Price $5 and $6',
        'Price $5,$6',
        'Escaped \\$x^2\\$ dollars',
        'Code `$x^2$` here',
        'Code ``a`$x^2$`` here',
        'See [link](https://x.test/$x^2$) here',
        '<a title="$x^2$" href="#">term</a>',
        'Nested $x $$y$$ z$',
        '\\(a $b$\\)',
        'Bare \\ce{H2O} here',
        'No maths at all',
    ], ids=['currency', 'currency-tight', 'escaped', 'code', 'double-backtick-code',
            'link-destination', 'html-attribute', 'nested-dollars',
            'nested-in-paren', 'bare-chemistry', 'plain'])
    def test_unchanged(self, written):
        assert _answer_maths_for_kramdown(written) == written

    @pytest.mark.parametrize('written, expected', [
        ('An unmatched \\( marker; then \\(x^2\\).',
         'An unmatched \\( marker; then $$x^2$$.'),
        ('An unmatched \\[ marker; then \\[y_1\\].',
         'An unmatched \\[ marker; then $$y_1$$.'),
        ('<code>$x^2$</code> and <pre class="a">$y^2$</pre> then $z^2$',
         '<code>$x^2$</code> and <pre class="a">$y^2$</pre> then $$z^2$$'),
        ('[this](https://e.test/a(b)/$x^2$) and $z^2$',
         '[this](https://e.test/a(b)/$x^2$) and $$z^2$$'),
    ], ids=['unclosed-paren', 'unclosed-bracket', 'code-element', 'parenthesised-url'])
    def test_what_does_not_pair_or_is_code_does_not_move(self, written, expected):
        assert _answer_maths_for_kramdown(written) == expected

    def test_maths_in_a_link_text_is_rewritten(self):
        assert (_answer_maths_for_kramdown('See [$x^2$](https://x.test) here')
                == 'See [$$x^2$$](https://x.test) here')


class TestALongMalformedAnswerIsReadInLinearTime:
    """An opening with no close is searched past once, not once per
    formula: 20,000 of any of these take well under a second."""

    @pytest.mark.parametrize('unit', ['`x ', '``y ', '\\begin{align} ', '\\( ', '\\[ ',
                                      '$$ ', '$x ', '<code>a ', '](x(y '])
    def test_bounded(self, unit):
        started = time.perf_counter()
        _answer_maths_for_kramdown(unit * 20000)
        assert time.perf_counter() - started < 1.0


class TestTheColumn:

    def test_a_story_without_maths_gains_no_column(self):
        df = pd.DataFrame({'answer': ['Plain', 'Also *plain*', None]})

        assert 'answer_kramdown' not in _prepare_answer_maths(df).columns

    def test_only_changed_answers_carry_a_value(self):
        df = pd.DataFrame({'answer': ['Plain', 'Area \\(x^2\\)', float('nan')]})

        out = _prepare_answer_maths(df)

        assert list(out['answer_kramdown']) == ['', 'Area $$x^2$$', '']
        assert out['answer'][1] == 'Area \\(x^2\\)'


def _jekyll_env():
    env = dict(os.environ, BUNDLE_GEMFILE=str(REPO / 'Gemfile'))
    env.pop('BUNDLE_PATH', None)
    return env


def _jekyll_runs():
    if shutil.which('bundle') is None:
        return False
    try:
        result = subprocess.run(['bundle', 'exec', 'jekyll', '--version'],
                                capture_output=True, text=True, cwd=REPO,
                                env=_jekyll_env(), timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


RENDERED_ANSWERS = {
    'paren': ('Area \\(x^2\\) here', '<p>Area \\(x^2\\) here</p>'),
    'bracket_alone': ('\\[y_1\\]', '\\[y_1\\]'),
    'dollar_emphasis': ('Inline $a*b*c^2$ here', '<p>Inline \\(a*b*c^2\\) here</p>'),
    'environment': ('\\begin{cases} a \\\\ b \\end{cases}',
                    '\\[\\begin{cases} a \\\\ b \\end{cases}\\]'),
    'currency': ('Price $5 and $6', '<p>Price $5 and $6</p>'),
    'pipe_in_paren': ('Norm \\(|x|\\) and x | y', '<p>Norm \\(\\vert x\\vert\\) and x | y</p>'),
}


@pytest.mark.skipif(not _jekyll_runs(),
                    reason='bundle exec jekyll does not run against the Gemfile with this Ruby')
class TestTheStepRendersTheMaths:

    @pytest.fixture(scope='class')
    def rendered(self, tmp_path_factory):
        site = tmp_path_factory.mktemp('answer-latex') / 'site'
        for folder in ('_includes', '_data'):
            (site / folder).mkdir(parents=True)
        for include in ('story-steps.html', 'story-step.html'):
            shutil.copy(REPO / '_includes' / include, site / '_includes' / include)
        shutil.copytree(REPO / '_data' / 'languages', site / '_data' / 'languages')
        names = list(RENDERED_ANSWERS)
        df = pd.DataFrame({'step': [str(i + 1) for i in range(len(names))],
                           'question': names,
                           'answer': [RENDERED_ANSWERS[n][0] for n in names]})
        steps = _prepare_answer_maths(df).to_dict('records')
        (site / '_data' / 'steps.json').write_text(json.dumps(steps), encoding='utf-8')
        (site / '_config.yml').write_text('telar_language: en\n', encoding='utf-8')
        (site / 'steps.html').write_text(
            '---\n---\n{% include story-steps.html steps=site.data.steps %}',
            encoding='utf-8')

        result = subprocess.run(
            ['bundle', 'exec', 'jekyll', 'build', '--source', str(site),
             '--destination', str(site / '_site'), '--quiet'],
            capture_output=True, text=True, cwd=REPO, env=_jekyll_env(), timeout=300)
        assert result.returncode == 0, result.stdout + result.stderr

        html = (site / '_site' / 'steps.html').read_text(encoding='utf-8')
        answers = re.findall(
            r'<div class="step-answer">\s*(.*?)\s*</div>\s*<!-- Viewer Warning',
            html, re.S)
        assert len(answers) == len(names)
        return dict(zip(names, answers))

    @pytest.mark.parametrize('name', list(RENDERED_ANSWERS))
    def test_published(self, rendered, name):
        assert rendered[name] == RENDERED_ANSWERS[name][1]
