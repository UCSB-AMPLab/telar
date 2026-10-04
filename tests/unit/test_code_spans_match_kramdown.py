"""
The Code-Span Reader Agrees with the Kramdown That Renders Answers

`telar.code_spans` tells three answer passes where code is: glossary links
and maths leave it alone, and the word limit does not cut inside it. It is
right only if it finds the spans kramdown renders as `<code>`. So each answer
here goes through Jekyll's own markdown converter, as `markdownify` in
`story-step.html` sends it, and the code elements that come back are compared
with the spans the reader finds: a fixed set of the forms where kramdown
differs from CommonMark, a seeded set of random answers built from
backtick runs, spaces, escapes, a tag and maths, two built around
links: one from the parts of a link, a reference, an IAL or an extension,
and one from brackets, parentheses, quotes and tags in any order, and one
of quotes and list items opening after a block HTML element's close.

Jekyll needs the Ruby the Gemfile asks for. Where `bundle exec` cannot run
against it, the tests are skipped and say so.

Version: v1.8.0
"""

import html
import itertools
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

from telar.code_spans import _KRAMDOWN_ESCAPE, _Scan, answer_regions, code_spans
from telar.processors.stories import (_answer_maths_for_kramdown, _answer_pipes_for_kramdown,
                                      _reduce_answer_to_prose)

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

# Link definitions and reference links (link.rb:21-35, 87-106).
DEFINITIONS = [
    '[a][ref]\n\n[ref]: https://example.org/`x`',
    'a `y`\n[ref]: u`x`\n\n[a][ref]',
    '[ref]: u "t" `x`\n[a][ref]',
    '[ref]: u\n  "t`x`"\n[a][ref]',
    '[ref]: u`x`\n$$y$$\n\nb `z`',
    '[`ΑΣ`]: u\n\n[a][`ασ`]',
    '[`b`]: u\n\n[x] [`b`]',
    '[a*b]: u\n\n[a\\*b]{: `c`}',
    '[ref]: u`x`\n\n[a][ref] `y`',
    '[ref]: u\n[r2]: v`x`\nb [a][r2]',
    '[ref]: u "t`x`"\n[a][ref]',
    '[ref]: <u `x`>\n[a][ref]',
    '   [ref]: u`x`\n\n[a][ref]',
    '[`a`]: u\n\n[`a`]',
    '# h\n[ref]: u`x`\n[a][ref]',
    '<div>x</div>\n[ref]: u`x`\n[a][ref]',
    '[ref]: u`x`',
    '[`R`]: u\n\n[a][`r`]',
    '[a]: u\n\n[a][]{: `c`}',
    '[ref]: u "t\n\n[a][ref] `x`',
]

# A definition line's break is `\r\n`, or a lone `\r`, or `\n`; a `\r` before
# a `\r\n` is a break of its own (parser/base.rb:102).
_BREAKS = ['\n', '\r\n', '\r\r\n', '\r \r\n', '\r', '\r\r', ' \r\n', '\r\n\r\n']
_LINE_BREAK_FORMS = [
    form
    for first in _BREAKS for second in _BREAKS
    for form in (f'[r]: u{first}"t`x`"{second}[a][r]',
                 f'[r]: u "t"{first}`x`{second}[a][r]',
                 f'[r]: u`x`{first}[a][r] `y`{second}')
] + [f'[r]: u`x`{b}' for b in _BREAKS] + [f'[r]: u{b}"t`x`"' for b in _BREAKS]

FORMS = [
    'a<<code>`x`',
    'a>><code>`x`',
    'a\\<<code>`x`',
    'a\\<<code>`x`</code> `y`',
    'a\\\\<<code>`x`',
    'a\\>><code>`x`',
    'a<<<code>`x`</code> `y`',
    'a<<<<code>`x`',
    'a << <code>`x`',
    'a <<code>`x`</code> `y`',
    'a<code>`x`</code> `y`',
    'a<<code>x</code> `y`',
    'a<<!-- `x` --> `y`',
    'a>>`x` <<b>`y`</b>',
    '<em>a<<code>`x`</code></em> `y`',
    '[a<<code>`x`](u) `y`',
    '[<em>a<<code>`x`</code></em>](u) `y`',
    '[<em>a\\<<code>`x`</em>](u) `y`',
    '[<em>a<<</code> `x`</em>](u) `y`',
    '[a<<code>`x`</code> b](u) `y`',
    '[a\\<<code>`x`](u) `y`',
    '<div>a<<code>`x`</div>\n\nb `y`',
    '[a<<code>x](u`z`)',
    '[a\\<<code>x](u`z`)',
    '[a\\\\<<code>x](u`z`)',
    '[<em>a<<code>x</em>](u`z`)',
    '![a<<code>x](u`z`)',
    '[a<<code>x][r]\n\n[r]: u`z`',
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
    'a <SCRIPT>`x`</SCRİPT> `y`</script> `z`',
    'a <script>`x`</ſcript> `y`</script> `z`',
    'a <kbd>`x`</\u212abd> `y` </kbd> `z`',
    'a <u>`x`</ı> `y`',
    'a <mark>`x`</marK> `y`</mark> `z`',
    'a\n<div>`x`</dİv> `y`</div> `z`',
    'a\n<div>`x`</\u212abd></div> `z`',
    'a\n<SCRIPT>`x`</ſcript>\n\n`y`',
    'a <kbd>`x\n<pre>y` z</pre> `w`',
    'a\n<div>b `x` c\n\nd</div> `y`',
    '<div>x</div> `y`\nmore `z`',
    '<p>`x`</p> `y`',
    'a\n<div>`x`</span>`y`</div> `w`',
    '<script>`x`\n\n`y`</script> `z`',
    'a `x\n<hr>` y',
    '<hr>` \nb` c',
    'a `x\n  <table>` y',
    'a `x\n<b>` y',
    'a `x\n<script>` y',
    'a `x\n</div>` y',
    'a `x\n<!-- c -->` y',
    'a `x\n1. b` c',
    'a `x\n# h` c',
    'a `x\n# #\nb` c',
    'a `x\n#   \nb` c',
    'a `x\n> q` c',
    'a `x\nb `y\n: d` c',
    'a `x\n^\nb` c',
    'a `x\n{: .c}\nb` c',
    'a `x\n```\nb` c',
    'a `x\n```\nb\n```\nc` d',
    'a `x\n``` p q\nb\n```\nc` d',
    'a\n\n```~~~\n`x`\n```~~~\n\nz `y`',
    'a\n\n~`~\n`x`\n~`~~~\n\nz `y`',
    'a\n\n~`~\n`x`\n~``\n\nz `y`',
    'a\n\n```~\n`x`\n`````\n\nz `y`',
    'a\n\n```\n`x`\n~~~~\n\nz `y`',
    'a\n\n```~ foo\n`x`\n`````\n\nz `y`',
    'a\n\n```\n`x`\n````~\n\nz `y`',
    'a `x\n١. y` z',
    'a `x\n<uä>` y',
    'a\n$$x$$\n\nb `y`',
    'a\n\n$$x\n\ny$$\n\nb `y`',
    'a\n^\n$$x\n\ny$$\n\nb `y`',
    'a\n<div>x</div>\n$$x\n\ny$$\n\nb `y`',
    'a\n<hr>\n$$x\n\ny$$\n\nb `y`',
    'a\n<hr>\n\\$$x$$\nb `y`',
    'a\n<div>x</div>\n\\$$x$$\nb `y`',
    'a\n\n    x\n<div>`y`</div> `z`',
    'a\n<DIV>`x`</div> `y`',
    'a\n<div>`x`</DIV> `y`',
    'a `y`\n\n$$x\n\ny$$',
    'a `y`\n\n$$x$$  ',
    'a `y`\n{: .c}\n\\$$x$$',
    '{: .c}\n\\$$x$$\nb `y`',
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
    # Links and images, as parse_link reads them.
    '[`a](b`)',
    '[`]` x](`y`)',
    '[a [b] c](`x`)',
    '[a](b c `d`)',
    '[a](b(c(d))`e`)',
    '[a](b "x" y`z`")',
    '[a](<b `c`>)',
    '[a](<b>`c`)',
    '[a](<b\n`c`>)',
    '[^a](`b`)',
    '[[a](`b`)](c)',
    '[![a](b)](`c`)',
    '[a ![b] c](`d`)',
    '[![a](b) ]](`c`)',
    '[a\\](`b`)',
    'a\n[b\n\nc](`d`)',
    '[a <code>]</code>](`c`)',
    '[a $$x]$$](`d`)',
    '[a](b\\)`c`)',
    '[a](`b` "")',
    'a <kbd><em markdown="span">[x</em>](y) `b`</kbd> `d`',
    '[`a](b)` x](`c`)',
    '[a](b\n`c`)',
    '[a <span>]</span>](`c`)',
    '[a](<b `c`> "t")',
    '[a](b `c` "t") `d`',
    '[`a` ](b `c`) `d`',
    'a][^a](b``)``',
    'a <code><span markdown="span">[x</span>](`b`) c</code> `d`',
    '[a](b (c \'d\') `e` f)',
    '[a [^b] c](`d`)',
    'a \\~`b` c',
    'a<[`<',
    '[`a` `b',
    '![^a](`x`)',
    '[a ![^ b](x) c]](`d`)',
    '[a ![^b](x) c](`d`)',
    # Link definitions and reference links, as written and with CRLF line
    # breaks, which the build does not normalize.
    *DEFINITIONS,
    *[form.replace('\n', '\r\n') for form in DEFINITIONS if '\n' in form],
    '[r]: u\r\n  "t`x`"\r\n[a][r]',
    *_LINE_BREAK_FORMS,
    # Span IALs and span extensions.
    'a [a](b){: title="`c`"}',
    'a{: `c`}',
    'a "q"{: `c`}',
    'a--{: `c`}',
    'a----{: `c`}',
    'a---{: `c`}',
    'a...{: `c`}',
    'a <code>x</code>{: `c`}',
    'a {::comment}`x`{:/} `d`',
    'a {::foo}`x`{:/foo} `d`',
    'a `a`{:/}{: `c`}',
    'a `x`{::options a="1" /}{: `c`}',
    'a x{::options a="1" /}{: `c`}',
    '[a `b`{: ]} c](`d`)',
    'a {::nomarkdown}x|y{:/} b',
    'a {::comment}x|y{:/} b',
    'a `a`{: .x `c`} `d`',
    'a <span>x</span>{: `c`}',
    'a <br>{: `c`}',
    'a <!--x-->{: `c`}',
    'a $$x$$ `d` $$y$${: `c`}',
    'a {::comment}`x`{:/comment} `d`',
    'a {::nomarkdown}`x`{:/} `d`',
    'a [a](b){: title="x\n`c`"}',
    'a [a](b){: title="x\\} `c`"}',
    'a ![a](b){: `c`}',
    'a `a`{::comment}`x`{:/comment}',
    '[a {::comment}]{:/comment}](`d`)',
    'a `a`{: x\\} `c` y\\} `d`',
    '[[x](<code>)[[x](<code>)`z`',
    # A quote or list item after a block HTML element's closing tag on its
    # line, where the prose rules leave its mark: its content is blocks.
    'a\n<div></A>\n</div>> # [<a/>`x\ny` z',
    '<div>x</div>> # h `a\nb` c',
    '<div>x</div>> <div>`a`</div> `b`',
    '<div>x</div>>     `a`',
    '<div>x</div>>\t\t`a`',
    '<div>x</div>> ```\n`a`\n```\n`b`',
    '<div>x</div>> \\$$a$$\nb `c`',
    '<div>x</div>> [r]: u`x`\n[a][r]',
    '<div>x</div>> a\n<div>`b`</div> `c`',
    '<div>x</div>>> # h `a\nb` c',
    '<div>x</div>- # h `a\nb` c',
    '<div>x</div>1. # h `a\nb` c',
    '<div>x</div>- <div>`a`</div> `b`',
    '<div>x</div>- ```\n`a`\n```\n`b`',
    '<div>x</div>- a\n\n    `b` c',
    '<div>x</div>- a\n\n\t`b` c',
    '<div>x</div>* a\n\n    `b` c',
    '<div>x</div>1. a\n\n     `b` c',
    '<div>x</div>-     `a`\n\n      `b`',
    '<div>x</div>- a\n<div>`b`</div> `c`',
    '<div>x</div>- {: .c}\n    `a`',
    '<div>x</div>- a\n^\n\\$$b$$\nc `d`',
    '<div>x</div>-\t\\$$\t\n\n\\$$\\$$ `d`',
    '<hr>- > # h `a\nb` c',
    '<!-- c -->> - a\n\n    `b` c',
    '<div>x</div>- - -\n`a`',
    # A line opening with one to three spaces and then a tab, which no
    # block parser takes: a text of its own, joined only to another such.
    'a\n\n  \t`x\ny` z',
    'a\n\n  \t`x\n \t y` z',
    'a\n\n \t`x\n{: .c}\n \ty` z',
    'a\n\n \tb\n- `x\n \ty`',
    '> a\n>\n>  \t`x\n> y`',
    # A comment after spaces, which is not block HTML.
    'a\n\n   <!---->    $$x$$',
    'a\n\n <!-- `x` --> `y`',
    # `\$$` opening a paragraph, the first `$$` after it not ending its
    # line, ahead of a stray `$$` and a lone `$`.
    'a\n\n\\$$    `<div>\na\\$$$$\n',
    # A stray `$$` next to a quote, whose smart quote reads the character
    # beside it.
    "a$$'i",
    'a$$"i',
    'a>["$$"',
    'a "$$" z',
    "a ['$$' z",
    "x $a^2$$' z",
    "a$$'x^2$ z",
    'a"$$ z',
    "a\n\n\\$$'i $$",
]

# Forms the reader does not model, pinned as it reads them and as kramdown
# renders them, so that a change to either is seen: a `]` hidden inside a
# link's text by emphasis or an autolink, and a span IAL after emphasis, an
# entity or `<<`. The last is the image rule: code in an image's text is
# reported as code, and kramdown writes it into `alt`, as written.
UNMODELLED = {
    'a *b*{: `c`}': (['c'], []),
    'a &amp;{: `c`}': (['c'], []),
    'a <<{: `c`}': (['c'], []),
    '[a *b] c*](`d`)': (['d'], []),
    '[a <http://x]>](`d`)': (['d'], []),
    '![`a`](b)': (['a'], []),
}

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


# Block syntax the answer passes can meet once the prose rules have run.
# Two kinds of block are not modelled, both rare in an answer, so they are
# left out here: a definition list's content past its first paragraph, and
# a `markdown` attribute on an element inside block HTML.
BLOCK_PIECES = ['\n<div>', '\n</div>', '\n<pre>', '</pre>', '\n```', '\n```\n', '\n^\n',
                '\n{: .c}\n', '\n<!-- c -->', '\n  <table>', '</table>', '\n<SCRIPT>',
                '\n<details>', '\n<hr>', '\n<p>', '\n<u>', '<div>', '\n\n<div>',
                '\n\n<!-- c -->', '\n# ', '\n\n$$']


def _random_block_answers(count, seed=571):
    rng = random.Random(seed)
    pieces = [p for p in PIECES if 'markdown=' not in p] + BLOCK_PIECES
    return [_prose('a' + ''.join(rng.choice(pieces) for _ in range(rng.randint(2, 14))))
            for _ in range(count)]


# Links: an opener, pieces of text, a close, pieces of a destination and
# what follows, after a prefix that may define a reference. A filler letter
# is a new one each time it is used, so a span's content says where it is.
LINK_PREFIXES = ['a', 'a ', '<span>', 'a\n', '[r]: u`v`\n\n', '[r]: u\n', 'a\n[r]: u`v`\n',
                 '[R]: u "`t`"\n', '[a]: u\n', 'a"', 'a--']
LINK_OPENERS = ['[', '![', '[^', '![^']
LINK_TEXT = ['a', ' ', '`', '``', '[', ']', '![', '[^a]', '\\]', '\\[', '<span>', '</span>',
             '<code>', '</code>', '$$', '\n', '\n\n', '(', ')', '{:x}', '{: `}`}',
             '{::comment}', '{:/}', '\\}', '{: `c` \\}`d` ']
LINK_CLOSES = [']', '] ', ']\n', ']]']
LINK_DESTINATION = ['b', ' ', '`', '``', '(', ')', '"', "'", '<', '>', '\n', '\n\n', '\\',
                    ' "t"', " 't'", '$$', '<b>']
LINK_SUFFIXES = [' `x`', ')`e`', '](f)', '[g](`h`)', '[r]', '[]', '[r]`z`', '[q]', '']
FILLERS = 'ijklmnopswyIJKLMNOPSWY'
# Syntax the reader does not model, which a generated answer must not hold:
# emphasis, entities, `<<` and `>>`, a definition begun by the
# pieces, an autolink, and a quote, which the prose rules flatten.
UNMODELLED_SYNTAX = re.compile(r'<<|>>|[*_&]|^ {0,3}\[[^\n]*\]:|http:|^>', re.MULTILINE)


def _fill(pieces, fillers):
    return ''.join(next(fillers) if piece in ('a', 'b') else piece for piece in pieces)


def _structured_answers(count, seed=580):
    rng = random.Random(seed)
    answers = []
    while len(answers) < count:
        fillers = itertools.cycle(FILLERS)
        body = (rng.choice(LINK_OPENERS)
                + _fill(rng.choices(LINK_TEXT, k=rng.randint(0, 6)), fillers)
                + rng.choice(LINK_CLOSES) + rng.choice(['(', '(<', ''])
                + _fill(rng.choices(LINK_DESTINATION, k=rng.randint(0, 6)), fillers)
                + rng.choice([')', '>)', '']) + rng.choice(LINK_SUFFIXES))
        if not UNMODELLED_SYNTAX.search(body):
            answers.append(rng.choice(LINK_PREFIXES) + body)
    return answers


FREE = ['[', ']', '(', ')', '`', ' ', '\n', '!', '<', '>', '"', "'", '\\', '^', '$$', 'a', 'b',
        '<span>', '</span>', '<code>', '</code>']


def _free_answers(count, seed=5800):
    rng = random.Random(seed)
    answers = []
    while len(answers) < count:
        fillers = itertools.cycle(FILLERS)
        answer = 'a' + _fill(rng.choices(FREE, k=rng.randint(2, 16)), fillers)
        if not UNMODELLED_SYNTAX.search(answer):
            answers.append(answer)
    return answers


# A quote or list item opening after a block HTML element's closing tag, then
# pieces of what its content may hold. Code and maths that run over a line
# are compared without the blanks that open each line after the first:
# kramdown strips a list item's indentation from them, and the reader places
# the span in the answer as written, where they remain.
CONTAINER_CLOSES = ['\n<div>x</div>', '<div>x</div>', '\n<hr>', '\n<!-- c -->',
                    '\n<div></A>\n</div>']
CONTAINER_STARTS = ['>', '> ', '>>', '- ', '* ', '1. ', '-\t', '>     ', '- # ', '> # ', '- > ',
                    '> - ']
CONTAINER_PIECES = ['`', '``', ' ', 'a', 'b c', '\n', '\n\n', '\na', '    ', '<div>', '</div>',
                    '# ', '```', '\n```\n', '$$', '\\$$', '\n^\n', '[r]: u`x`\n', '[a][r]',
                    '<span>', '</span>', '<a/>', '[', '\n  ', '\n    ', '<!--', '-->', '<u>',
                    '</u>']


def _container_answers(count, seed=668):
    rng = random.Random(seed)
    return [_prose('a' + rng.choice(CONTAINER_CLOSES) + rng.choice(CONTAINER_STARTS)
                   + ''.join(rng.choice(CONTAINER_PIECES) for _ in range(rng.randint(1, 10))))
            for _ in range(count)]


def _unindented(contents):
    return [re.sub(r'\n[ \t]*', '\n', content) for content in contents]


def _prose(answer):
    reduced = _reduce_answer_to_prose(answer)
    return reduced[0] if isinstance(reduced, tuple) else reduced


def _random_answers(count, seed=541):
    rng = random.Random(seed)
    return ['a' + ''.join(rng.choice(PIECES) for _ in range(rng.randint(2, 12)))
            for _ in range(count)]


def _rendered_code(rendered):
    """The text of every code span kramdown made, in order. Its spans carry
    the highlighter's class, after any an IAL gives them, and an IAL's id
    comes before it; a `<code>` the author wrote has no such class."""
    return [_line_ends(html.unescape(content)) for content in
            re.findall(r'<code(?: id="[^"]*")? class="language-plaintext[^"]*highlighter-rouge">'
                       r'(.*?)</code>', rendered, re.DOTALL)]


def _rendered_alts(rendered):
    """The text of every image kramdown made, in order."""
    return [html.unescape(alt) for alt in re.findall(r'<img [^>]*?alt="([^"]*)"', rendered)]


def _line_ends(content):
    """kramdown drops the spaces before a line break; where a span starts
    and ends does not depend on them."""
    return re.sub(r'[ \t]+\n', '\n', content)


def _read_code(answer, rendered=None):
    """The text of every span the reader finds, as kramdown prints it: the
    delimiters off, and for a run of two or more, one space off each end.
    Given what kramdown *rendered*, a span in an image's text is left out,
    since kramdown writes that text into the image's `alt` as written, and
    each span left out must be found there."""
    spans = code_spans(answer)
    if rendered is not None:
        spans = _outside_images(answer, spans, rendered)
    contents = []
    for start, end in spans:
        run = len(answer[start:end]) - len(answer[start:end].lstrip('`'))
        content = answer[start + run:end - run]
        if run > 1:
            content = content[1:] if content.startswith(' ') else content
            content = content[:-1] if content.endswith(' ') else content
        contents.append(_line_ends(content))
    return contents


def _outside_images(answer, spans, rendered):
    scan = _Scan(answer)
    scan.run()
    images = [image for image in scan.images
              if not any(outer[0] < image[0] and image[1] <= outer[1] for outer in scan.images)]
    alts = _rendered_alts(rendered)
    assert len(alts) == len(images), (answer, images, alts)
    kept = []
    for start, end in spans:
        holder = next((k for k, (first, last) in enumerate(images)
                       if first <= start and end <= last), None)
        if holder is None:
            kept.append((start, end))
        else:
            assert _KRAMDOWN_ESCAPE.sub(r'\1', answer[start:end]) in alts[holder], (answer, alts)
    return kept


def _rendered_maths(rendered):
    """The content of every formula kramdown made, inline or as a block
    of its own, in order."""
    return [_line_ends(html.unescape(inline or block)) for inline, block in
            re.findall(r'\\\((.*?)\\\)|\\\[(.*?)\\\]', rendered, re.DOTALL)]


def _read_maths(answer, rendered=None):
    """The content of every `$$…$$` span the reader finds, as kramdown
    prints it: the delimiters off, and trimmed of ASCII whitespace. Given
    what kramdown *rendered*, a span in an image's text is left out, as
    code is."""
    spans = [(start, end) for kind, start, end in answer_regions(answer) if kind == 'maths']
    if rendered is not None:
        spans = _outside_images(answer, spans, rendered)
    return [_line_ends(answer[start + 2:end - 2].strip(' \t\n\r\f\v')) for start, end in spans]


def _prepared(answer):
    return _answer_pipes_for_kramdown(_answer_maths_for_kramdown(answer))


ANSWERS = (FORMS + list(UNMODELLED) + _random_answers(400) + _random_block_answers(400)
           + _structured_answers(400) + _free_answers(400))
CONTAINER_ANSWERS = _container_answers(400)


@pytest.fixture(scope='module')
def kramdown(tmp_path_factory):
    """Each answer, and each as the build prepares it, rendered."""
    answers = ANSWERS + CONTAINER_ANSWERS + [_prepared(answer)
                                             for answer in ANSWERS + CONTAINER_ANSWERS]
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
    assert _read_code(answer, kramdown[answer]) == _rendered_code(kramdown[answer])
    assert _read_maths(answer, kramdown[answer]) == _rendered_maths(kramdown[answer])


@pytest.mark.parametrize('answer', list(UNMODELLED))
def test_an_unmodelled_form_reads_as_pinned(kramdown, answer):
    assert (_read_code(answer), _rendered_code(kramdown[answer])) == UNMODELLED[answer]


def test_code_in_an_image_is_written_into_its_alt(kramdown):
    answer = '![`a`](b)'
    assert _read_code(answer, kramdown[answer]) == _rendered_code(kramdown[answer]) == []


def _disagreements(kramdown, answers):
    """Where the reader and kramdown differ on code, or on maths. An answer
    holding `\\(`, `\\)`, `\\[` or `\\]` can print one of them as written,
    which reads as a formula's delimiter in what kramdown renders, so its
    maths is not compared."""
    return [(answer, _read_code(answer, kramdown[answer]), _rendered_code(kramdown[answer]),
             _read_maths(answer, kramdown[answer]), _rendered_maths(kramdown[answer]))
            for answer in answers
            if _read_code(answer, kramdown[answer]) != _rendered_code(kramdown[answer])
            or (not re.search(r'\\[][()]', answer)
                and _read_maths(answer, kramdown[answer]) != _rendered_maths(kramdown[answer]))]


def test_random_links(kramdown):
    assert _disagreements(kramdown, _structured_answers(400)) == []


def test_random_brackets(kramdown):
    assert _disagreements(kramdown, _free_answers(400)) == []


def test_random_answers(kramdown):
    disagreements = [(answer, _read_code(answer), _rendered_code(kramdown[answer]))
                     for answer in _random_answers(400)
                     if _read_code(answer) != _rendered_code(kramdown[answer])]
    assert disagreements == []


def test_random_answers_with_blocks(kramdown):
    disagreements = [(answer, _read_code(answer), _rendered_code(kramdown[answer]),
                      _read_maths(answer), _rendered_maths(kramdown[answer]))
                     for answer in _random_block_answers(400)
                     if (_read_code(answer), _read_maths(answer))
                     != (_rendered_code(kramdown[answer]), _rendered_maths(kramdown[answer]))]
    assert disagreements == []


def test_random_quotes_and_list_items(kramdown):
    disagreements = [(answer, kramdown[answer]) for answer in CONTAINER_ANSWERS
                     if (_unindented(_read_code(answer, kramdown[answer])),
                         _unindented(_read_maths(answer, kramdown[answer])))
                     != (_unindented(_rendered_code(kramdown[answer])),
                         _unindented(_rendered_maths(kramdown[answer])))]
    assert disagreements == []


def test_random_answers_maths(kramdown):
    disagreements = [(answer, _read_maths(answer), _rendered_maths(kramdown[answer]))
                     for answer in _random_answers(400)
                     if _read_maths(answer) != _rendered_maths(kramdown[answer])]
    assert disagreements == []


def test_the_build_changes_nothing_on_the_page(kramdown):
    """Of answers that hold no formula to rewrite and no pipe, the only
    changes the build makes are escaping a stray `$$` and, with it, writing
    a `\\$$` that opens a block as an escaped dollar, both of which must
    print what the answer as written prints. A pipe makes a table row of
    the answer as written, and `\\[` or `\\(` can open a formula."""
    changed = [(answer, _prepared(answer)) for answer in ANSWERS + CONTAINER_ANSWERS
               if not re.search(r'\||\\[\[(]', answer) and _prepared(answer) != answer]
    assert changed
    disagreements = [(answer, kramdown[answer], kramdown[prepared])
                     for answer, prepared in changed
                     if html.unescape(kramdown[answer]) != html.unescape(kramdown[prepared])]
    assert disagreements == []
