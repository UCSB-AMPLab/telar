"""
Unit Tests for Glossary Syntax Inside Code

Code is shown as written: markdown syntax inside a code span or block is not
read, and neither is glossary syntax. An author who writes `` `[[term-id]]` ``
to teach the syntax gets the syntax on the page, not a link, and no warning
for a term that does not exist.

The link pass runs on rendered HTML -- a panel's, and a step answer's --
where code is a `<code>`, `<pre>`, `<kbd>` or `<samp>` element.

Version: v1.8.0
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.glossary import code_elements, process_glossary_links

TERMS = {'iiif': 'IIIF'}
LINK = 'class="glossary-inline-link" data-term-id="iiif"'


def _linked(text, warnings=None):
    return process_glossary_links(text, TERMS, warnings if warnings is not None else [],
                                  base_url='')


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


class TestAMissingTermInCodeIsNotReported:

    def test_no_warning_and_no_marker(self):
        warnings = []

        out = _linked('<p><code>[[term-id]]</code></p>', warnings)

        assert out == '<p><code>[[term-id]]</code></p>'
        assert warnings == []


class TestCodeElements:

    def test_code_elements_are_found(self):
        text = 'x <code>y</code> <pre>z</pre> <kbd>k</kbd>'

        assert [text[s:e] for s, e in code_elements(text)] == [
            '<code>y</code>', '<pre>z</pre>', '<kbd>k</kbd>']
