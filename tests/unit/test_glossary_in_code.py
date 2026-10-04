"""
Unit Tests for Glossary Syntax Inside Code

Code is shown as written: markdown syntax inside a code span or block is not
read, and neither is glossary syntax. An author who writes `` `[[term-id]]` ``
to teach the syntax gets the syntax on the page, not a link, and no warning
for a term that does not exist.

The link pass runs on a panel's HTML, where code is a `<code>` or `<pre>`
element, and on a step answer's markdown, where it is a backtick span. Both
are read by `telar.code_spans`, the same reading the answer maths pass uses.

Version: v1.8.0
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.code_spans import code_regions, code_spans
from telar.glossary import process_glossary_links

TERMS = {'iiif': 'IIIF'}
LINK = 'class="glossary-inline-link" data-term-id="iiif"'


def _linked(text, warnings=None, markdown=False):
    return process_glossary_links(text, TERMS, warnings if warnings is not None else [],
                                  base_url='', markdown=markdown)


class TestInPanelHtml:

    @pytest.mark.parametrize('html', [
        '<p>Type <code>[[iiif]]</code> here.</p>',
        '<pre><code>[[iiif]]\n</code></pre>',
        '<p><kbd>[[iiif]]</kbd></p>',
        '<p>Type <code class="x">[[iiif|IIIF]]</code> here.</p>',
    ], ids=['inline-code', 'code-block', 'kbd', 'with-display-text'])
    def test_code_keeps_the_syntax(self, html):
        assert _linked(html) == html

    def test_the_same_term_outside_code_is_still_linked(self):
        out = _linked('<p>Type <code>[[iiif]]</code> for [[iiif]].</p>')

        assert out.count(LINK) == 1
        assert '<code>[[iiif]]</code>' in out

    def test_backticks_are_characters(self):
        # Markdown has already made its code spans into elements, so a
        # backtick left in the HTML is text and hides nothing.
        assert LINK in _linked('<p>It`s a [[iiif]] and ``</p>')


class TestInAnswerMarkdown:

    @pytest.mark.parametrize('markdown', [
        'Type `[[iiif]]` here.',
        'Type ``a`[[iiif]]`` here.',
        'Type ```[[iiif]]``` here.',
    ], ids=['single', 'double', 'triple'])
    def test_a_code_span_keeps_the_syntax(self, markdown):
        assert _linked(markdown, markdown=True) == markdown

    def test_an_unmatched_backtick_does_not_hide_a_link(self):
        assert LINK in _linked("It`s [[iiif]] here.", markdown=True)

    def test_a_code_span_in_an_element_made_read_keeps_the_syntax(self):
        markdown = 'Type <u markdown="span">`[[iiif]]`</u> here.'
        assert _linked(markdown, markdown=True) == markdown

    def test_a_raw_element_that_is_not_code_is_linked(self):
        # As in a panel: only code shows the syntax. kramdown prints the
        # element as written, so the link inside it works.
        assert LINK in _linked('Type <u>[[iiif]]</u> here.', markdown=True)

    def test_many_code_elements_and_links_are_read_in_linear_time(self):
        markdown = '<code>x</code> ' * 10000 + '[[iiif]] ' * 10000
        started = time.perf_counter()
        _linked(markdown, markdown=True)
        assert time.perf_counter() - started < 2.0


class TestAMissingTermInCodeIsNotReported:

    def test_no_warning_and_no_marker(self):
        warnings = []

        out = _linked('<p><code>[[term-id]]</code></p>', warnings)

        assert out == '<p><code>[[term-id]]</code></p>'
        assert warnings == []


class TestTheSharedReader:

    def test_spans_follow_the_template_rule(self):
        text = 'a `b` c ``d`e`` f ` g'

        assert [text[s:e] for s, e in code_spans(text)] == ['`b`', '``d`e``']

    def test_regions_include_code_elements(self):
        text = 'x <code>y</code> <pre>z</pre>'

        assert sorted(text[s:e] for s, e in code_regions(text)) == [
            '<code>y</code>', '<pre>z</pre>']
