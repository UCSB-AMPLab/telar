"""
The Anchor Reader Agrees with the Kramdown That Renders Answers

A glossary term inside a link's text is shown as text, because a link must
never hold a link. In an answer, `telar.code_spans.anchor_texts` finds the
content of each raw `<a>` element as kramdown reads span HTML, and the
glossary pass adds the link texts and, in what kramdown prints as written,
the anchors a browser reads. Each answer here goes through Jekyll's own
markdown converter, and the stretches that come back inside an `<a>` are
compared with those the readers find. A unique marker stands in for each
piece of text, so the markers inside an anchor say where it was.

Jekyll needs the Ruby the Gemfile asks for. Where `bundle exec` cannot run
against it, the tests are skipped and say so.

Version: v1.8.0
"""

import json
import os
import random
import re
import subprocess
import sys
from html.parser import HTMLParser

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.code_spans import anchor_texts
from telar.glossary import _link_text_regions

from .test_code_spans_match_kramdown import REPO, RENDER, _env, _jekyll_runs, _prose

pytestmark = pytest.mark.skipif(
    not _jekyll_runs(),
    reason='bundle exec jekyll does not run against the Gemfile with this Ruby')

MARKER = re.compile(r'ж\d+ж')

# Each `@` is a marker. The forms the reader once got wrong, and the places
# a tag is not one: code, a comment, an attribute, a longer name.
FORMS = [
    'x<y <a>@</a> @',
    '<a href=b>@ </a @',
    '<![CDATA[<!--]]> <a>@</a> @',
    '<?pi <!-- ?> <a>@</a> @',
    '<!DOCTYPE x <!-- > <a>@</a> @',
    '`<a>` @',
    '<!-- <a> --> @',
    '<span title="<a href=b>">@</span> @',
    '<a-b>@</a-b> @',
    '<A HREF=b>@</A> @',
    '<a>@<a>@</a>@</a> @',
    '@ <a',
    '@ <a>',
    '<a>@\n\n@',
    '<a/>@',
    '<a>@</a\n> @',
    '<u><a>@</a></u> @',
    '<code><a>@</a></code> @',
    '<span><a>@</span> @</a> @',
    '[@ <a>@</a> @](u) @',
    '<a>@ [@](u) @</a> @',
    '<a href="x>y">@</a> @',
    "<a href='</a>'>@</a> @",
    '<div><a href="b">@</a></div>\n\n@',
    '<div>x<y <a>@</a> @</div>\n\n@',
    '<div><a>@</div>\n\n@',
    '<div><span title="<a>">@</span> @</div>',
    '<div>\n<a>@</a>\n</div>\n\n@',
    '<div>\n\n<a>@</a> @\n\n</div>\n\n@',
    '<div><!-- <a> --> @</div>',
    '<div><script><a>@</script> @</div>\n\n',
    '<div><style><a>@</STYLE > @</div>',
    '<div><textarea><a>@</textarea> @</div>',
    '<div><pre><a>@</pre> @</div>',
    '<div><script><a>@ @</div>\n\n@',
    '<script><a>@</script> @\n\n@',
    '<div><script/><a>@</a></div>\n\n@',
]

PIECES = ['<a>', '<a href="b">', '</a>', '<A HREF=b>', '</A>', '<a-b>', '</a-b>', '<a/>', '<a',
          '</a ', 'x<y ', '<!--', '-->', '<![CDATA[', ']]>', '<?p ', '?>', '<!D ', '>', '`',
          '<code>', '</code>', '<u>', '</u>', '<span>', '</span>', '<span title="<a>">',
          '\n\n', '\n', ' ', '[', '](u)', '\\<', '@', '@', '@', '\n<div>', '\n</div>',
          '\n\n<div>', '\n\n<script>', '</script>', '\n\n<div><style>', '</style>']


def _random_answers(count, seed=650):
    rng = random.Random(seed)
    return [_prose('@' + ''.join(rng.choice(PIECES) for _ in range(rng.randint(2, 14))))
            for _ in range(count)]


def _marked(form):
    count = iter(range(1000))
    return re.sub('@', lambda _: f'ж{next(count)}ж', form)


ANSWERS = [_marked(form) for form in FORMS + _random_answers(600)]


class _Inside(HTMLParser):
    """The stretches of rendered HTML inside an `<a>` element, at any depth."""

    def __init__(self, rendered):
        super().__init__(convert_charrefs=False)
        self.starts = [0] + [m.end() for m in re.finditer('\n', rendered)]
        self.depth, self.start, self.stretches = 0, None, []
        self.feed(rendered)
        self.close()

    def at(self):
        line, column = self.getpos()
        return self.starts[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.depth += 1
            if self.depth == 1:
                self.start = self.at() + len(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        """kramdown writes an empty element as a start and an end tag."""

    def set_cdata_mode(self, elem, *args, **kwargs):
        """kramdown reads tags inside a `textarea` and writes them as tags,
        which is the element tree compared here; only `script` and `style`
        content is text to it."""
        if elem in ('script', 'style'):
            super().set_cdata_mode(elem, *args, **kwargs)

    def handle_endtag(self, tag):
        if tag == 'a' and self.depth:
            self.depth -= 1
            if not self.depth:
                self.stretches.append((self.start, self.at()))


def _rendered_inside(rendered):
    stretches = _Inside(rendered).stretches
    return sorted({marker for start, end in stretches
                   for marker in MARKER.findall(rendered[start:end])})


def _read_inside(answer, regions):
    return sorted({match.group() for match in MARKER.finditer(answer)
                   if any(start <= match.start() < end for start, end in regions)})


def _glossary_regions(answer):
    return _link_text_regions(answer, True)


@pytest.fixture(scope='module')
def kramdown(tmp_path_factory):
    site = tmp_path_factory.mktemp('kramdown')
    (site / '_config.yml').write_text(
        (REPO / '_config.yml').read_text(encoding='utf-8'), encoding='utf-8')
    result = subprocess.run(
        ['bundle', 'exec', 'ruby', '-e', RENDER, str(site)],
        input=''.join(json.dumps(a) + '\n' for a in ANSWERS),
        capture_output=True, text=True, cwd=REPO, env=_env(), timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
    rendered = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(rendered) == len(ANSWERS)
    return dict(zip(ANSWERS, rendered))


@pytest.mark.parametrize('answer', ANSWERS[:len(FORMS)])
def test_a_form_reads_as_kramdown_renders_it(kramdown, answer):
    assert _read_inside(answer, _glossary_regions(answer)) == _rendered_inside(kramdown[answer])


@pytest.mark.parametrize('answer', [a for a in ANSWERS[:len(FORMS)]
                                    if '[' not in a and '<u>' not in a and '<code>' not in a])
def test_the_scanner_alone_reads_a_form_as_kramdown_does(kramdown, answer):
    assert _read_inside(answer, anchor_texts(answer)) == _rendered_inside(kramdown[answer])


def test_random_answers(kramdown):
    disagreements = [(answer, _read_inside(answer, _glossary_regions(answer)),
                      _rendered_inside(kramdown[answer]), kramdown[answer])
                     for answer in ANSWERS[len(FORMS):]
                     if _read_inside(answer, _glossary_regions(answer))
                     != _rendered_inside(kramdown[answer])]
    assert disagreements == []


@pytest.mark.parametrize('answer,expected', [
    ('x<y <a>z</a>', [(7, 8)]),
    ('<A HREF=b>z</A>', [(10, 11)]),
    ('<a>x<a>y</a>z</a>', [(3, 13), (7, 8)]),
    ('<a href=b>x </a z', [(10, 17)]),
    ('<a>x\n\ny', [(3, 4)]),
    ('<a/>x', []),
    ('a <a', []),
])
def test_offsets(answer, expected):
    assert anchor_texts(answer) == expected
