"""
Unit Tests for What a Link Leaves Unread

kramdown reads no span syntax in a link's destination, title or reference
id, nor in a link definition line: `[a](b $x$)` publishes the href
`b $x$`. An image's text becomes its `alt` attribute, printed as written:
`![$x^2$](b)` publishes `alt="$x^2$"`. So the glossary pass and the answer
maths pass leave all of these as written, and read them where kramdown does,
from `telar.code_spans`, rather than with an expression of their own. A
link's text is read like any text, so both passes still act there.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.code_spans import image_texts, link_destinations, unread_regions
from telar.glossary import process_glossary_links
from telar.processors.stories import _answer_maths_for_kramdown, _answer_pipes_for_kramdown

TERMS = {'iiif': 'IIIF'}
LINK = 'class="glossary-inline-link" data-term-id="iiif"'


def _linked(text):
    return process_glossary_links(text, TERMS, [], base_url='', markdown=True)


def _texts(text, spans):
    return [text[start:end] for start, end in spans]


class TestTheReader:

    @pytest.mark.parametrize('text, expected', [
        ('[a](b $x$)', ['(b $x$)']),
        ('[a](<b $x$>)', ['(<b $x$>)']),
        ('[a](b(c(d)) $x$)', ['(b(c(d)) $x$)']),
        ('[a](b "t $x$")', ['(b "t $x$")']),
        ('[a][r] x\n\n[r]: b $x$', ['[r]', '[r]: b $x$']),
        ('![a](b $x$)', ['(b $x$)']),
        ('[$x$](b)', ['(b)']),
    ], ids=['parenthesis', 'angle', 'nested', 'title', 'reference', 'image', 'text-is-not'])
    def test_destinations(self, text, expected):
        assert _texts(text, link_destinations(text)) == expected

    @pytest.mark.parametrize('text', [
        '[^a]($x$)',
        '[a] ($x$)',
        '`[a](b $x$)`',
        '[a][r] with no definition',
    ], ids=['footnote-marker', 'space-before', 'in-code', 'undefined-reference'])
    def test_no_destination(self, text):
        assert link_destinations(text) == []

    def test_an_image_text(self):
        text = 'An ![$x^2$ and `c`](b) here'
        assert _texts(text, image_texts(text)) == ['$x^2$ and `c`']

    def test_a_link_text_is_not_an_image_text(self):
        assert image_texts('[$x^2$](b) and ![](c)') == [(17, 17)]


class TestTheMathsPass:

    @pytest.mark.parametrize('written', [
        '[a](b $x^2$)',
        '[a](<$x^2$ b>)',
        '[a](b(c(d)) $x^2$)',
        '[a](b "t $x^2$")',
        '[a][r]\n\n[r]: b $x^2$',
        '![$x^2$](b)',
        'See ![a \\(x^2\\) b](c) here',
    ], ids=['destination', 'angle', 'nested', 'title', 'definition', 'image-text',
            'image-text-paren'])
    def test_left_as_written(self, written):
        assert _answer_maths_for_kramdown(written) == written

    @pytest.mark.parametrize('written, expected', [
        ('[$x^2$](b)', '[$$x^2$$](b)'),
        ('[^a]($x^2$)', '[^a]($$x^2$$)'),
        ('[a] ($x^2$)', '[a] ($$x^2$$)'),
        ('![a](b) then $x^2$', '![a](b) then $$x^2$$'),
    ], ids=['link-text', 'after-footnote-marker', 'not-a-link', 'after-an-image'])
    def test_still_rewritten(self, written, expected):
        assert _answer_maths_for_kramdown(written) == expected


class TestTheGlossaryPass:

    @pytest.mark.parametrize('written', [
        '[a](b [[iiif]])',
        '[a](<[[iiif]] b>)',
        '[a](b "[[iiif]]")',
        '[a][r]\n\n[r]: b [[iiif]]',
        '![[[iiif]]](b)',
    ], ids=['destination', 'angle', 'title', 'definition', 'image-text'])
    def test_left_as_written(self, written):
        assert _linked(written) == written

    @pytest.mark.parametrize('written', [
        '[a](b) and [[iiif]]',
        '[[iiif]] then [a](b [[x]])',
        '![a](b) [[iiif]]',
    ], ids=['after-a-link', 'before-a-link', 'after-an-image'])
    def test_still_linked(self, written):
        assert LINK in _linked(written)


class TestANomarkdownExtension:
    """kramdown prints a `nomarkdown` extension's body as written, so the
    glossary and maths passes leave it alone. Its line is still split at `|`
    by the table parser, so the pipe pass goes on escaping there."""

    def test_the_reader(self):
        text = 'a {::nomarkdown}$x$ [[t]]{:/} b [c](d)'
        assert [(kind, text[start:end]) for kind, start, end in unread_regions(text)] == [
            ('nomarkdown', '{::nomarkdown}$x$ [[t]]{:/}'), ('destination', '(d)')]

    @pytest.mark.parametrize('text', [
        'a {::nomarkdown /} $x$',
        'a {::comment}$x${:/} b',
        'a `{::nomarkdown}$x${:/}` b',
        'a {::nomarkdown}$x$ with no stop',
    ], ids=['no-body', 'comment', 'in-code', 'unclosed'])
    def test_no_body(self, text):
        assert [region for region in unread_regions(text) if region[0] == 'nomarkdown'] == []

    @pytest.mark.parametrize('written', [
        'a {::nomarkdown}$x^2$ b{:/} c',
        'a {::nomarkdown type="html"}\\(x^2\\){:/nomarkdown} c',
    ], ids=['dollar', 'paren'])
    def test_maths_left_as_written(self, written):
        assert _answer_maths_for_kramdown(written) == written

    def test_maths_beside_it_rewritten(self):
        assert (_answer_maths_for_kramdown('{::nomarkdown}a{:/} $x^2$')
                == '{::nomarkdown}a{:/} $$x^2$$')

    def test_glossary_left_as_written(self):
        written = 'a {::nomarkdown}[[iiif]]{:/} c'
        assert _linked(written) == written

    def test_glossary_beside_it_linked(self):
        assert LINK in _linked('a {::nomarkdown}b{:/} [[iiif]]')

    def test_pipes_still_escaped(self):
        assert (_answer_pipes_for_kramdown('a {::nomarkdown}x|y{:/} b')
                == 'a {::nomarkdown}x&#124;y{:/} b')
