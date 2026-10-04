"""
Unit Tests for Pipes in a Story Step's Answer

A step's answer is prose, run through `markdownify` in story-step.html.
kramdown reads any line holding a `|` as a table row, header separator or
not, so a pipe in prose, in a link's text, in inline LaTeX or in a glossary
link's display text turns the line into a table. The include hands kramdown
each pipe in prose as `&#124;`. kramdown prints the content of a code span and
of `$$…$$` maths literally, so an entity there would reach the reader as text:
a pipe inside a code span is left as written, and one inside maths becomes
`\\vert `, which KaTeX draws as the same glyph.

The story data and the answer string are not touched: the Compositor mirrors
them byte for byte. So these tests build a small Jekyll site from the real
include and language catalogues and read the HTML each answer renders to.

Jekyll needs the Ruby the Gemfile asks for. Where `bundle exec jekyll` cannot
run against it, the tests are skipped and say so; run them with that Ruby on
PATH, e.g.

    PATH="$HOME/.rubies/ruby-3.2.11/bin:$PATH" GEM_HOME="$HOME/.gem/ruby/3.2.11" \\
        .venv/bin/python3 -m pytest tests/unit/test_story_step_answer_pipes.py

Version: v1.8.0
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


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


pytestmark = pytest.mark.skipif(
    not _jekyll_runs(),
    reason='bundle exec jekyll does not run against the Gemfile with this Ruby')


GLOSSARY_LINK = ('<a href="/glossary/ab/" class="glossary-inline-link" '
                 'data-term-id="ab">a | b</a>')
CODE = '<code class="language-plaintext highlighter-rouge">'

ANSWERS = {
    'pipe_in_prose': 'Text x | y here',
    'pipe_in_link_text': 'See [a | b](https://x.org) here',
    'pipe_in_code_span': 'Type `a|b` here',
    'ends_in_code_span': 'Choose x | y, or type `a|b`',
    'ends_in_backtick_run': 'Choose x | y, or type ``a`|b``',
    'double_backtick_span': 'Type ``a`|b`` then x | y',
    'unmatched_backtick': 'It`s x | y here',
    'no_pipe': 'A plain *answer*, with `code` and a [link](https://x.org).\n\nTwo paragraphs.',
    'latex_norm': 'Norm $|x|$ here',
    'glossary_link': f'See {GLOSSARY_LINK} here',
    'glossary_link_and_prose_pipe': f'See {GLOSSARY_LINK} and x | y',
    'escaped_pipe': 'Escaped x \\| y here',
    'escaped_pipe_after_code': 'Type `a|b`, then x \\| y',
    'fenced_code': 'Before x | y\n\n```\ncode|x\n```\n\nAfter',
    'maths_block': '$$|x| + |y|$$',
    'maths_inline': 'Norm $$|x|$$ here',
    'maths_block_many_pipes': 'Before\n\n$$\n|a| + |b| \\ge |a + b| \\quad \\left|\\frac{a}{b}\\right|\n$$\n\nAfter',
    'maths_double_bar': 'Norm $$\\|x\\| \\ge |x|$$ here, x | y',
    'maths_in_code_span': 'Type `$$a|b$$` then x | y',
    'maths_unpaired': 'Costs $$ x | y here',
    'maths_and_prose_pipe': 'If x | y then $$|x| \\le |y|$$ holds',
}


@pytest.fixture(scope='module')
def rendered(tmp_path_factory):
    """Build every answer through story-step.html, and through a plain
    markdownify for comparison; return {name: (step_html, plain_html)}."""
    site = tmp_path_factory.mktemp('story-step') / 'site'
    for folder in ('_includes', '_data'):
        (site / folder).mkdir(parents=True)
    shutil.copy(REPO / '_includes' / 'story-step.html',
                site / '_includes' / 'story-step.html')
    shutil.copytree(REPO / '_data' / 'languages', site / '_data' / 'languages')
    names = list(ANSWERS)
    (site / '_data' / 'answers.json').write_text(
        json.dumps([ANSWERS[n] for n in names]), encoding='utf-8')
    (site / '_config.yml').write_text('telar_language: en\n', encoding='utf-8')
    (site / 'steps.html').write_text(
        '---\n---\n'
        '{% for a in site.data.answers %}'
        '{% include story-step.html step_number=forloop.index answer=a %}'
        '{% endfor %}', encoding='utf-8')
    (site / 'plain.html').write_text(
        '---\n---\n'
        '{% for a in site.data.answers %}'
        '<section data-n="{{ forloop.index }}">{{ a | markdownify }}</section>'
        '{% endfor %}', encoding='utf-8')

    result = subprocess.run(
        ['bundle', 'exec', 'jekyll', 'build', '--source', str(site),
         '--destination', str(site / '_site'), '--quiet'],
        capture_output=True, text=True, cwd=REPO, env=_jekyll_env(), timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr

    steps = (site / '_site' / 'steps.html').read_text(encoding='utf-8')
    plain = (site / '_site' / 'plain.html').read_text(encoding='utf-8')
    step_answers = re.findall(
        r'<div class="step-answer">\n      (.*?)\n    </div>\n\n    <!-- Viewer Warning',
        steps, re.S)
    plain_answers = re.findall(r'<section data-n="\d+">(.*?)</section>', plain, re.S)
    assert len(step_answers) == len(names) == len(plain_answers)
    return {n: (s, p) for n, s, p in zip(names, step_answers, plain_answers)}


def _answer(rendered, name):
    return rendered[name][0].strip()


class TestAPipeOutsideCode:

    def test_in_prose_stays_prose(self, rendered):
        assert _answer(rendered, 'pipe_in_prose') == '<p>Text x | y here</p>'

    def test_in_link_text_keeps_the_link(self, rendered):
        assert _answer(rendered, 'pipe_in_link_text') == (
            '<p>See <a href="https://x.org">a | b</a> here</p>')

    def test_in_inline_latex_reaches_katex_as_written(self, rendered):
        assert _answer(rendered, 'latex_norm') == '<p>Norm $|x|$ here</p>'

    def test_in_a_glossary_link_keeps_the_link(self, rendered):
        assert _answer(rendered, 'glossary_link') == f'<p>See {GLOSSARY_LINK} here</p>'

    def test_beside_a_glossary_link_holding_one_keeps_the_link(self, rendered):
        assert _answer(rendered, 'glossary_link_and_prose_pipe') == (
            f'<p>See {GLOSSARY_LINK} and x | y</p>')

    def test_escaped_by_the_author_renders_as_a_pipe(self, rendered):
        assert _answer(rendered, 'escaped_pipe') == '<p>Escaped x | y here</p>'
        assert _answer(rendered, 'escaped_pipe_after_code') == (
            f'<p>Type {CODE}a|b</code>, then x | y</p>')

    def test_after_an_unmatched_backtick_stays_prose(self, rendered):
        assert _answer(rendered, 'unmatched_backtick') == '<p>It`s x | y here</p>'

    def test_is_never_a_table(self, rendered):
        for name, (html, _plain) in rendered.items():
            assert '<table' not in html, name


class TestAPipeInsideCode:

    def test_in_a_code_span_is_left_as_written(self, rendered):
        assert _answer(rendered, 'pipe_in_code_span') == (
            f'<p>Type {CODE}a|b</code> here</p>')

    def test_in_a_code_span_that_ends_the_answer(self, rendered):
        assert _answer(rendered, 'ends_in_code_span') == (
            f'<p>Choose x | y, or type {CODE}a|b</code></p>')

    def test_in_a_double_backtick_span_that_ends_the_answer(self, rendered):
        assert _answer(rendered, 'ends_in_backtick_run') == (
            f'<p>Choose x | y, or type {CODE}a`|b</code></p>')

    def test_in_a_double_backtick_span_before_prose(self, rendered):
        assert _answer(rendered, 'double_backtick_span') == (
            f'<p>Type {CODE}a`|b</code> then x | y</p>')

    def test_in_a_fenced_block(self, rendered):
        html = _answer(rendered, 'fenced_code')
        assert html.startswith('<p>Before x | y</p>')
        assert re.search(r'<pre[^>]*><code>code\|x\n</code></pre>', html), html

    def test_never_prints_an_entity(self, rendered):
        for name, (html, _plain) in rendered.items():
            assert '&amp;#124;' not in html, name


class TestAnAnswerWithoutAPipe:

    def test_renders_exactly_as_markdownify_does(self, rendered):
        html, plain = rendered['no_pipe']
        assert html == plain


class TestAPipeInsideDisplayMaths:
    """kramdown prints `$$…$$` content literally, so a pipe there becomes
    `\\vert `, which KaTeX draws as the same glyph; `\\|` stays as written."""

    def test_in_a_block_reaches_katex_as_vert(self, rendered):
        assert _answer(rendered, 'maths_block') == (
            r'\[\vert x\vert  + \vert y\vert\]')

    def test_inline_is_not_a_table_and_reaches_katex_as_vert(self, rendered):
        assert _answer(rendered, 'maths_inline') == r'<p>Norm \(\vert x\vert\) here</p>'

    def test_in_a_block_with_several_pipes(self, rendered):
        assert _answer(rendered, 'maths_block_many_pipes') == (
            '<p>Before</p>\n\n'
            r'\[\vert a\vert  + \vert b\vert  \ge \vert a + b\vert  \quad '
            r'\left\vert \frac{a}{b}\right\vert\]'
            '\n\n<p>After</p>')

    def test_a_double_bar_stays_as_written(self, rendered):
        assert _answer(rendered, 'maths_double_bar') == (
            r'<p>Norm \(\|x\| \ge \vert x\vert\) here, x | y</p>')

    def test_beside_a_pipe_in_prose(self, rendered):
        assert _answer(rendered, 'maths_and_prose_pipe') == (
            r'<p>If x | y then \(\vert x\vert  \le \vert y\vert\) holds</p>')

    def test_in_a_code_span_is_code_not_maths(self, rendered):
        assert _answer(rendered, 'maths_in_code_span') == (
            f'<p>Type {CODE}$$a|b$$</code> then x | y</p>')

    def test_an_unpaired_delimiter_leaves_the_pipe_as_prose(self, rendered):
        assert _answer(rendered, 'maths_unpaired') == '<p>Costs $$ x | y here</p>'
