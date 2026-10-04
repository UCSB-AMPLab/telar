"""
The Code-Span Reader Agrees with the Kramdown That Renders Answers

`telar.code_spans` tells three answer passes where code is: glossary links
and maths leave it alone, and the word limit does not cut inside it. It is
right only if it finds the spans kramdown renders as `<code>`. So each answer
here goes through Jekyll's own markdown converter, as `markdownify` in
`story-step.html` sends it, and the code elements that come back are compared
with the spans the reader finds: a fixed set of the forms where kramdown
differs from CommonMark, and a seeded set of random answers built from
backtick runs, spaces, escapes, a tag and maths.

Jekyll needs the Ruby the Gemfile asks for. Where `bundle exec` cannot run
against it, the tests are skipped and say so.

Version: v1.8.0
"""

import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.code_spans import answer_regions, code_spans
from telar.processors.stories import _answer_maths_for_kramdown, _answer_pipes_for_kramdown

REPO = Path(__file__).resolve().parents[2]


def _env():
    env = dict(os.environ, BUNDLE_GEMFILE=str(REPO / 'Gemfile'))
    env.pop('BUNDLE_PATH', None)
    return env


def _jekyll_runs():
    if shutil.which('bundle') is None:
        return False
    try:
        result = subprocess.run(['bundle', 'exec', 'jekyll', '--version'],
                                capture_output=True, text=True, cwd=REPO,
                                env=_env(), timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


pytestmark = pytest.mark.skipif(
    not _jekyll_runs(),
    reason='bundle exec jekyll does not run against the Gemfile with this Ruby')

# Jekyll's converter with the site's own configuration, one answer per line
# of JSON in, one rendering per line of JSON out.
RENDER = '''
require "jekyll"
require "json"
site = Jekyll::Site.new(Jekyll.configuration("source" => ARGV[0], "quiet" => true))
converter = site.find_converter_instance(Jekyll::Converters::Markdown)
STDIN.each_line { |line| puts JSON.generate(converter.convert(JSON.parse(line))) }
'''

FORMS = [
    'one two `a b c d` six',
    'one two ``a b c d`` six',
    'one two ```a b``` six',
    'one two `a b c d`` six seven',
    'one two ``a b c d``` six seven',
    'x ``a`` b`` c',
    'x `a``b` c',
    'It`s x `y z` w',
    'a ` b `c d` e',
    'a `b` c ``d`e`` f ` g',
    '<br title="``"> one two three four`` five six',
    'one two \\`literal `a b c d e` six seven',
    'one \\\\`code x` two',
    '$$a `b` c$$ then `d e`',
    '$$ unclosed `a b` c',
    '`$$a$$` and $$b$$',
    '<em>`a b`</em> c',
    'a < b `c d` e > f',
    'a \u00a0` b` c',
    'a <!--`--> [[t]] `c`',
    'a [x](y`z) `w` v',
    'a [x](y "`t") `w` v',
    '<u>`a</u> b` c',
    '<span>`a</span> b` c',
    '<code>`a` $$b$$</code> `c`',
    '<kbd>`a</kbd> b` c',
    '<u>`a b` no close',
    '<x-y>`a</x-y> b` c',
    'a <details>`x`</details> then `y`',
    'a <figure>`x`</figure> then `y`',
    'a <SCRIPT>`x</script> then `y` z',
    'a <TEXTAREA>`x</textarea> then `y` z',
    'a <X>`x</x> then `y` z',
    'a <u>`x</U> then `y` z',
    'a <pre>`x`</pre> then `y`',
    'a <table>`x`</table> then `y`',
    'a\n\n    `x` $$ and `y`\nlazy `z`\n\nb `w`',
    'a\n\n\t`x` $$\n\nb `w`',
    'a <u markdown="span">`x`</u> `y`',
    'a <u markdown="1">`x`</u> `y`',
    'a <span markdown="0">`x`</span> `y`',
    'a <span markdown="block">`x`</span> `y`',
    'a <U MARKDOWN="span">`x`</U> `y`',
    'a <u><b markdown="1">`x`</b> `y`</u> `z`',
    'a <![CDATA[`x]]> `y`',
    'a <!-- `x --> <!-- `y` -->',
    '` <b title="`">x',
    '`x <b title="`">y',
    '`a b\n\nc` d',
    '`a b\nc` d',
]

# Span syntax only. No pipe: the template escapes it before markdownify,
# since kramdown reads a line holding one as a table row. A new line starts
# with a letter, and so does the answer: a fence, a list, an indented code
# block or a maths block at the start of a line is
# block syntax, which the answer's prose rules have removed before any pass
# reads it.
PIECES = ['`', '``', '```', ' ', '\t', '\u00a0', 'a', 'b c', '\\', '\\`', '<em>',
          '</em>', '<br title="`">', '<!--`-->', '[x](y`z)', '$$', '*', '\na',
          '\n\na', '<u>', '</u>', '<code>', '</code>', '<span>', '</span>',
          '<x-y>', '</x-y>', '<img src="`"/>', '<details>', '</details>', '<SCRIPT>',
          '</script>', '<b markdown="0">', '</b>', '<u markdown="span">', '<![CDATA[',
          ']]>', '<!--', '-->', '\\$', '\n\n\\$$', 'x$$', '\n\n    ', '\n\n\t']


def _random_answers(count, seed=541):
    rng = random.Random(seed)
    return ['a' + ''.join(rng.choice(PIECES) for _ in range(rng.randint(2, 12)))
            for _ in range(count)]


def _rendered_code(rendered):
    """The text of every code span kramdown made, in order. Its spans carry
    the highlighter's class; a `<code>` the author wrote does not."""
    return [_line_ends(html.unescape(content)) for content in
            re.findall(r'<code class="language-plaintext highlighter-rouge">(.*?)</code>',
                       rendered, re.DOTALL)]


def _line_ends(content):
    """kramdown drops the spaces before a line break; where a span starts
    and ends does not depend on them."""
    return re.sub(r'[ \t]+\n', '\n', content)


def _read_code(answer):
    """The text of every span the reader finds, as kramdown prints it: the
    delimiters off, and for a run of two or more, one space off each end."""
    contents = []
    for start, end in code_spans(answer):
        run = len(answer[start:end]) - len(answer[start:end].lstrip('`'))
        content = answer[start + run:end - run]
        if run > 1:
            content = content[1:] if content.startswith(' ') else content
            content = content[:-1] if content.endswith(' ') else content
        contents.append(_line_ends(content))
    return contents


def _rendered_maths(rendered):
    """The content of every inline formula kramdown made, in order."""
    return [_line_ends(html.unescape(content)) for content in
            re.findall(r'\\\((.*?)\\\)', rendered, re.DOTALL)]


def _read_maths(answer):
    """The content of every `$$…$$` span the reader finds, as kramdown
    prints it: the delimiters off, and trimmed of ASCII whitespace."""
    return [_line_ends(answer[start + 2:end - 2].strip(' \t\n\r\f\v'))
            for kind, start, end in answer_regions(answer) if kind == 'maths']


def _prepared(answer):
    return _answer_pipes_for_kramdown(_answer_maths_for_kramdown(answer))


ANSWERS = FORMS + _random_answers(400)


@pytest.fixture(scope='module')
def kramdown(tmp_path_factory):
    """Each answer, and each as the build prepares it, rendered."""
    answers = ANSWERS + [_prepared(answer) for answer in ANSWERS]
    site = tmp_path_factory.mktemp('kramdown')
    (site / '_config.yml').write_text(
        (REPO / '_config.yml').read_text(encoding='utf-8'), encoding='utf-8')
    result = subprocess.run(
        ['bundle', 'exec', 'ruby', '-e', RENDER, str(site)],
        input=''.join(json.dumps(a) + '\n' for a in answers),
        capture_output=True, text=True, cwd=REPO, env=_env(), timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
    rendered = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rendered) == len(answers)
    return dict(zip(answers, rendered))


@pytest.mark.parametrize('answer', FORMS)
def test_a_form_where_kramdown_is_not_commonmark(kramdown, answer):
    assert _read_code(answer) == _rendered_code(kramdown[answer])
    assert _read_maths(answer) == _rendered_maths(kramdown[answer])


def test_random_answers(kramdown):
    disagreements = [(answer, _read_code(answer), _rendered_code(kramdown[answer]))
                     for answer in _random_answers(400)
                     if _read_code(answer) != _rendered_code(kramdown[answer])]
    assert disagreements == []


def test_random_answers_maths(kramdown):
    disagreements = [(answer, _read_maths(answer), _rendered_maths(kramdown[answer]))
                     for answer in _random_answers(400)
                     if _read_maths(answer) != _rendered_maths(kramdown[answer])]
    assert disagreements == []


def test_the_build_changes_nothing_on_the_page(kramdown):
    """None of these answers holds a formula to rewrite or a pipe, so the
    only change the build makes is escaping a stray `$$`, which must print
    what the answer as written prints."""
    changed = [(answer, _prepared(answer)) for answer in ANSWERS
               if _prepared(answer) != answer]
    assert changed
    disagreements = [(answer, kramdown[answer], kramdown[prepared])
                     for answer, prepared in changed
                     if html.unescape(kramdown[answer]) != html.unescape(kramdown[prepared])]
    assert disagreements == []
