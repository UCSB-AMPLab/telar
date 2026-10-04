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

from telar.code_spans import answer_regions
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
        'a <u>$x^2$ and \\(y^2\\)</u>',
        'a <span markdown="0">\\(x^2\\)</span>',
        'a <SCRIPT>$x^2$</script> then',
        'a <![CDATA[\\(x^2\\)]]> then',
    ], ids=['currency', 'currency-tight', 'escaped', 'code', 'double-backtick-code',
            'link-destination', 'html-attribute', 'nested-dollars',
            'nested-in-paren', 'bare-chemistry', 'plain', 'raw-element',
            'made-raw', 'raw-any-case', 'cdata'])
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

    @pytest.mark.parametrize('written, expected', [
        ('a <u markdown="span">\\(x^2\\)</u>', 'a <u markdown="span">$$x^2$$</u>'),
        ('a <details>\\(x^2\\)</details>', 'a <details>$$x^2$$</details>'),
    ], ids=['made-read', 'block-model'])
    def test_maths_in_an_element_kramdown_reads_is_rewritten(self, written, expected):
        assert _answer_maths_for_kramdown(written) == expected

    def test_maths_in_a_link_text_is_rewritten(self):
        assert (_answer_maths_for_kramdown('See [$x^2$](https://x.test) here')
                == 'See [$$x^2$$](https://x.test) here')


class TestAStrayDoubleDollar:
    """A `$$` with no close in its paragraph is printed as it is. Once a
    formula after it is written `$$…$$`, kramdown would pair the two and read
    the text between as maths, so it is passed as `\\$\\$`, which prints `$$`."""

    @pytest.mark.parametrize('written, expected', [
        ('Costs $$ 5, then \\(x^2\\) here', 'Costs \\$\\$ 5, then $$x^2$$ here'),
        ('Area $$x^2$$ and $$', 'Area $$x^2$$ and \\$\\$'),
        ('Just $$ money', 'Just \\$\\$ money'),
        # kramdown drops the backslash before a paragraph's opening `$$`
        # when the next `$$` ends a line, so the escape replaces it.
        ('Cost\n\n\\$$ 5\n\n$$', 'Cost\n\n\\$\\$ 5\n\n\\$\\$'),
    ], ids=['before-a-formula', 'after-a-pair', 'alone', 'backslash-dropped'])
    def test_escaped(self, written, expected):
        assert _answer_maths_for_kramdown(written) == expected

    @pytest.mark.parametrize('written', [
        'Code `$$` here',
        '<code>$$</code> here',
        'Escaped \\$$ here',
        '<![CDATA[$$]]> then',
        'a <u>$$</u> then',
        '\\$$$$',
        'a\n\n    $$ in a code block\n\nb',
        'a\n\n$$x\n\ny$$\n\nb',
        'a\n<div>$$ b</div>',
        'a\n\n$$x\n\ny$$',
    ], ids=['in-code', 'in-a-code-element', 'after-an-escape', 'in-cdata', 'in-a-raw-element',
            'maths-after-a-dropped-backslash', 'in-an-indented-code-block',
            'block-maths-over-a-blank-line', 'in-block-html', 'block-maths-ending-the-answer'])
    def test_not_stray(self, written):
        assert _answer_maths_for_kramdown(written) == written


# Fences left open: 20,000 with no two runs the same; 20,000 the same, with
# only a close of the other character at the end; one run 20,000 long; and
# 20,000 after the only close line.
_FENCES = {
    'distinct-fences': 'a\n' + ''.join(
        '``' + format(i, 'b').replace('0', '~').replace('1', '`') + ' x\n' for i in range(20000)),
    'fences-and-another-close': 'a\n' + '```x\n' * 20000 + '~~~~\n',
    'one-long-run': 'a\n\n' + '`' * 20000 + '\n',
    'a-close-before-the-fences': 'a\n\n~~~\n\n' + '~~~x\n' * 20000,
}


class TestALongMalformedAnswerIsReadInLinearTime:
    """An opening with no close is searched past once, not once per
    formula: 20,000 of any of these take well under a second."""

    @pytest.mark.parametrize('unit', ['`x ', '``y ', '\\begin{align} ', '\\( ', '\\[ ',
                                      '$$ ', '$x ', '<code>a ', '](x(y ', '<!-- ',
                                      '<![CDATA[ ', '<u>a ', '<b markdown="0">a ',
                                      '\n{:x', '\n<div>', '\n: a', '\n````\n```', '\n```x\n',
                                      'distinct-fences', 'fences-and-another-close',
                                      'one-long-run', 'a-close-before-the-fences'])
    def test_bounded(self, unit):
        started = time.perf_counter()
        _answer_maths_for_kramdown(_FENCES.get(unit) or unit * 20000)
        assert time.perf_counter() - started < 1.0

    def test_many_guarded_stretches_and_formulas(self):
        # Each formula is checked against the guarded stretches by a
        # search, not against each one in turn.
        answer = '<code>x</code> ' * 10000 + '\\(x^2\\) ' * 10000
        started = time.perf_counter()
        _answer_maths_for_kramdown(answer)
        assert time.perf_counter() - started < 1.0


# Links, images, references, IALs and extensions left open or nested,
# 20,000 of each: each opener starts a reading of its text, which must not
# read again what an earlier one read.
_N = 20000
_LINKS = {unit: unit * _N for unit in [
    '[', '[`', '![', '[^a', '[^a]', '[a](', '[a](<', '[a](b "x', '[x]( (', '[`](', '[a](((',
    '[[a](b)', '[<span>', '[a <code>]', '`a`{: ', '{::comment}', '[a](b){:x', '[a](b){:x}{:']}
_LINKS.update({
    'parentheses': '[a](' + '(' * _N,
    'titles': '[a](b "' + '" x' * _N,
    'brackets': '[' * _N + ']' * _N,
    'images': '![' * _N + '](x)' * _N,
    'code in destinations': '[' + '[a](`)`[' * _N,
    'runs in destinations': '[' + ''.join('[a](' + '`' * (i % 8 + 1) + ')`[' for i in range(_N)),
    'extension tags': '{::comment ' * _N + '}',
    'references': '[r]: u\n\n' + '[' * _N + 'r' + ']' * _N,
    'many definitions': (''.join('[' + 'r' * k + ']: u\n' for k in range(1, 201)) + '\n'
                         + '[' * _N + 'r' + ']' * _N),
    'references and code': '[a]: u\n\n' + '[a`' * _N,
    'references opened': '[a]: u\n\n' + '[a][' * _N,
    'a definition line': '[a]: u' + ' "x' * _N,
})
# A link's text holding an element, code, maths, a comment or an extension
# that runs to the end of the paragraph, opened 20,000 times.
_LINKS.update({f'element {inner}': f'[[x]({inner})' * _N + '`z`' for inner in [
    '<code>', '<b>', '<span>', '<u markdown="span">', '$$', '`', '<!--', '{::comment}',
    '<code>`']})
_LINKS['element runs'] = ''.join('[[x](' + '`' * (i % 8 + 1) + ')' for i in range(_N)) + '`z`'


class TestALongLinkAnswerIsReadInLinearTime:
    """Whether a `[` opens a link is settled by reading its text; those
    readings share what they find, so 20,000 of any of these take well
    under a second, and nesting 20,000 deep needs no recursion."""

    @pytest.mark.parametrize('unit', list(_LINKS))
    def test_bounded(self, unit):
        started = time.perf_counter()
        answer_regions(_LINKS[unit])
        assert time.perf_counter() - started < 1.0

    def test_backtick_runs_each_a_new_length(self):
        # Every run is longer than any after it, so none closes, and each
        # length is searched for once: 4,800 runs, 11.5 million characters.
        answer = 'a ' + ''.join('`' * k + 'x' for k in range(4800, 0, -1))
        started = time.perf_counter()
        answer_regions(answer)
        assert time.perf_counter() - started < 1.0

    def test_nesting_needs_no_recursion(self):
        answer_regions('[' * _N + 'a' + ']' * _N + '(b)')
        answer_regions('![' * _N + '<span>' * _N + '`x`')


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
    'stray_dollars_then_formula': (
        'Costs $$ 5, and `a b` then \\(x^2\\) here',
        '<p>Costs $$ 5, and <code class="language-plaintext highlighter-rouge">a b</code>'
        ' then \\(x^2\\) here</p>'),
    'stray_dollars_alone': ('Just $$ money', '<p>Just $$ money</p>'),
    'maths_in_a_raw_element': ('a <u>$x^2$ and \\(y^2\\)</u>',
                               '<p>a <u>$x^2$ and \\(y^2\\)</u></p>'),
    'dollars_in_cdata': ('a <![CDATA[$$]]> then \\(x^2\\)', '<p>a $$ then \\(x^2\\)</p>'),
    'dropped_backslash': ('\\$$$$', '<p>\\(\\)</p>'),
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
