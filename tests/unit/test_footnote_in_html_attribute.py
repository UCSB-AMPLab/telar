"""Unit Tests for a Footnote Reference Inside an HTML Attribute

An author who writes `<span title="[^b]">x</span>` has put the reference
inside the tag, where no reader can follow it. Python Markdown's footnote
pattern does not know it is inside a tag and writes a `<sup>` into the
attribute value, whose quotes end the attribute early and break the
element. The reference stays literal text there, and the tag stays
intact; a reference in the element's text beside it is still a note.

The definition such a reference points at then has no reference. The
footnotes extension keeps an unreferenced definition: it is listed after
the referenced notes, with a return arrow to an anchor that does not
exist. That is how any orphan definition renders, and the last test here
pins it so a change to it is seen.

Version: v1.8.0
"""

import os
import re
import sys
from html.parser import HTMLParser

import pytest

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))

from telar.latex import convert_markdown
from telar.markdown import process_inline_content



class _Elements(HTMLParser):
    """Every start tag, as (tag, attributes), in document order."""

    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def _elements(html, tag):
    parser = _Elements()
    parser.feed(html)
    return [attrs for name, attrs in parser.elements if name == tag]


def _references(html):
    return re.findall(r'class="footnote-ref" href="#fn:([^"]+)"', html)


def _convert(text):
    return convert_markdown(text)


class TestTheTagStaysIntact:

    def test_double_quoted_attribute(self):
        html = _convert('Text <span title="[^b]">x</span>.\n\n[^b]: B')
        assert _elements(html, 'span') == [{'title': '[^b]'}]
        assert _references(html) == []
        assert '<span title="[^b]">x</span>' in html

    def test_single_quoted_attribute(self):
        html = _convert("Text <span title='[^b]'>x</span>.\n\n[^b]: B")
        assert _elements(html, 'span') == [{'title': '[^b]'}]
        assert _references(html) == []

    def test_several_attributes(self):
        html = _convert(
            'Text <abbr class="n" title="see [^b]" data-note=\'[^c] and [^b]\'>'
            'x</abbr>.\n\n[^b]: B\n\n[^c]: C')
        assert _elements(html, 'abbr') == [{
            'class': 'n', 'title': 'see [^b]', 'data-note': '[^c] and [^b]'}]
        assert _references(html) == []

    def test_a_quoted_angle_bracket_does_not_release_the_reference(self):
        """Markdown itself ends the tag at the `>` and escapes the rest,
        footnote or not; the reference after it is still in the attribute."""
        html = _convert('Text <span title="a > b [^b]">x</span>.\n\n[^b]: B')
        assert _references(html) == []


class TestTheElementTextStillConverts:

    def test_reference_in_text_beside_one_in_the_attribute(self):
        html = _convert('Text <span title="[^b]">x[^a]</span>.\n\n'
                        '[^a]: A\n\n[^b]: B')
        assert _elements(html, 'span') == [{'title': '[^b]'}]
        assert _references(html) == ['a']
        assert re.search(r'<sup id="fnref:a"><a class="footnote-ref" '
                         r'href="#fn:a">1</a></sup>', html)

    def test_reference_after_the_tag_is_numbered_first(self):
        html = _convert('Text <span title="[^b]">x</span> then[^b].\n\n'
                        '[^b]: B')
        assert _elements(html, 'span')[0] == {'title': '[^b]'}
        assert _references(html) == ['b']

    def test_a_less_than_sign_in_prose_is_not_a_tag(self):
        """Markdown reads a tag within one paragraph; so does the hold."""
        html = _convert('Compare a<b.\n\nLater a note[^a] and x>y.\n\n[^a]: A')
        assert _references(html) == ['a']

    def test_a_code_span_keeps_its_text(self):
        html = _convert('Code `<span title="[^b]">`.')
        assert '<code>&lt;span title="[^b]"&gt;</code>' in html


class TestAPanelWithAWidget:

    TEXT = """:::accordion
## One
Section <span title="[^s]">x</span> and a note[^r].

[^r]: R
[^s]: S
:::

Panel <em title='[^t]'>y</em> and[^u].

[^u]: U
[^t]: T
"""

    @pytest.fixture(autouse=True)
    def _repo_root(self, monkeypatch):
        """The widget templates are read from `_includes/widgets` in the cwd."""
        monkeypatch.chdir(REPO_ROOT)

    def test_attributes_in_the_section_and_the_panel_stay_literal(self):
        html = process_inline_content(self.TEXT)['content']
        assert {'title': '[^s]'} in _elements(html, 'span')
        assert _elements(html, 'em') == [{'title': '[^t]'}]
        labels = [re.sub(r'^widget-\d+-\d+-', '', ref)
                  for ref in _references(html)]
        assert labels == ['r', 'u']


class TestTheUnreferencedDefinition:

    def test_it_is_listed_after_the_referenced_notes(self):
        html = _convert('One[^a] <span title="[^b]">x</span>.\n\n'
                        '[^b]: B\n\n[^a]: A')
        items = re.findall(r'<li id="fn:([^"]+)"', html)
        assert items == ['a', 'b']
        assert 'id="fnref:b"' not in html
