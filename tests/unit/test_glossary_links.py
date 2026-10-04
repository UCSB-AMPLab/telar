"""
Unit Tests for Glossary Link Processing

This module tests the glossary auto-linking feature that transforms wiki-style
[[term]] syntax into clickable links. When users write [[colonial-period]] in
their markdown content, Telar converts it to an HTML link that opens a sliding
panel with the glossary definition.

The syntax supports two forms:
- [[term_id]] — displays the glossary term's title as link text
- [[term_id|custom text]] — displays custom text as the link

Invalid terms (not found in glossary) are marked with a warning indicator
to help authors catch typos and missing definitions.

Version: v1.8.0
"""

import sys
import os
import re
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

# Mock the get_lang_string function to avoid loading config
import csv_to_json
csv_to_json.get_lang_string = lambda key, **kwargs: f"Term not found: {kwargs.get('term_id', 'unknown')}"

from csv_to_json import process_glossary_links
from telar.glossary import _link_text_regions, strip_glossary_links


class TestProcessGlossaryLinks:
    """Tests for process_glossary_links function."""

    @pytest.fixture
    def glossary_terms(self):
        """Sample glossary terms for testing."""
        return {
            'colonial-period': 'Colonial Period',
            'viceroyalty': 'Viceroyalty',
            'encomienda': 'Encomienda System',
            'demo-term': 'Demo Term',
            'kcsb': 'KCSB',
        }

    def test_transforms_simple_term(self, glossary_terms):
        """Should transform [[term]] to glossary link."""
        text = 'During the [[colonial-period]] many changes occurred.'
        result = process_glossary_links(text, glossary_terms)
        assert 'glossary-inline-link' in result
        assert 'data-term-id="colonial-period"' in result
        assert '>Colonial Period</a>' in result

    def test_transforms_term_with_custom_display(self, glossary_terms):
        """Should use custom display text with [[term|display]] syntax."""
        text = 'The [[colonial-period|early colonial era]] was significant.'
        result = process_glossary_links(text, glossary_terms)
        assert '>early colonial era</a>' in result
        assert 'data-term-id="colonial-period"' in result

    def test_handles_multiple_terms(self, glossary_terms):
        """Should handle multiple glossary links in same text."""
        text = 'The [[viceroyalty]] used the [[encomienda]] system.'
        result = process_glossary_links(text, glossary_terms)
        assert result.count('glossary-inline-link') == 2
        assert 'data-term-id="viceroyalty"' in result
        assert 'data-term-id="encomienda"' in result

    def test_marks_invalid_terms_with_error(self, glossary_terms):
        """Should mark invalid terms with error class."""
        warnings = []
        text = 'The [[unknown-term]] is not defined.'
        result = process_glossary_links(text, glossary_terms, warnings)
        assert 'glossary-link-error' in result
        assert '[[unknown-term]]' in result

    def test_adds_warning_for_invalid_term(self, glossary_terms):
        """Should add warning when term is not found."""
        warnings = []
        text = 'Reference to [[missing-term]] here.'
        process_glossary_links(text, glossary_terms, warnings, step_num=1, layer_name='layer1')
        assert len(warnings) == 1
        assert warnings[0]['type'] == 'glossary'
        assert warnings[0]['term_id'] == 'missing-term'

    def test_handles_whitespace_in_syntax(self, glossary_terms):
        """Should handle whitespace around term and pipe."""
        text = 'The [[ colonial-period ]] was important.'
        result = process_glossary_links(text, glossary_terms)
        assert 'glossary-inline-link' in result
        assert 'data-term-id="colonial-period"' in result

    def test_handles_whitespace_with_custom_display(self, glossary_terms):
        """Should handle whitespace in [[term | display]] syntax."""
        text = 'The [[ colonial-period | colonial times ]] were eventful.'
        result = process_glossary_links(text, glossary_terms)
        assert '>colonial times</a>' in result

    def test_adds_demo_attribute_for_demo_terms(self, glossary_terms):
        """Should add data-demo attribute for terms starting with demo-."""
        text = 'See the [[demo-term]] for an example.'
        result = process_glossary_links(text, glossary_terms)
        assert 'data-demo="true"' in result

    def test_no_demo_attribute_for_regular_terms(self, glossary_terms):
        """Should not add data-demo attribute for regular terms."""
        text = 'The [[colonial-period]] was important.'
        result = process_glossary_links(text, glossary_terms)
        assert 'data-demo' not in result

    def test_returns_unchanged_if_no_glossary_terms(self):
        """Should return text unchanged if glossary_terms is empty."""
        text = 'Text with [[some-term]] here.'
        result = process_glossary_links(text, {})
        assert result == text

    def test_returns_unchanged_if_text_empty(self, glossary_terms):
        """Should return empty text unchanged."""
        assert process_glossary_links('', glossary_terms) == ''
        assert process_glossary_links(None, glossary_terms) is None

    def test_preserves_surrounding_html(self, glossary_terms):
        """Should preserve HTML around glossary links."""
        text = '<p>The [[colonial-period]] was <strong>important</strong>.</p>'
        result = process_glossary_links(text, glossary_terms)
        assert '<p>' in result
        assert '</p>' in result
        assert '<strong>' in result

    def test_handles_term_at_start_of_text(self, glossary_terms):
        """Should handle term at the very start of text."""
        text = '[[colonial-period]] began in 1492.'
        result = process_glossary_links(text, glossary_terms)
        assert result.startswith('<a href="#"')

    def test_handles_term_at_end_of_text(self, glossary_terms):
        """Should handle term at the very end of text."""
        text = 'This was the [[colonial-period]]'
        result = process_glossary_links(text, glossary_terms)
        assert result.endswith('</a>')

    def test_handles_adjacent_terms(self, glossary_terms):
        """Should handle terms with no space between them."""
        text = '[[colonial-period]][[viceroyalty]]'
        result = process_glossary_links(text, glossary_terms)
        assert result.count('glossary-inline-link') == 2

    def test_escapes_markup_in_valid_link_display_text(self, glossary_terms):
        """Custom display text with markup is escaped, not rendered."""
        text = '[[colonial-period|A <b>"bold"</b> term]]'
        result = process_glossary_links(text, glossary_terms)
        assert 'data-term-id="colonial-period"' in result
        assert '&lt;b&gt;' in result and '&quot;' in result
        assert '<b>' not in result  # author markup did not break out

    def test_matches_uppercase_term_case_insensitively(self, glossary_terms):
        """Author-typed [[KCSB]] resolves to the lowercase `kcsb` term."""
        text = 'Listen to [[KCSB]] for details.'
        result = process_glossary_links(text, glossary_terms)
        assert 'glossary-inline-link' in result
        # Canonical lowercase id is used for the data attribute, not the author's casing
        assert 'data-term-id="kcsb"' in result
        assert 'data-term-id="KCSB"' not in result
        assert '>KCSB</a>' in result  # display text is the glossary title

    def test_matches_mixedcase_term_case_insensitively(self, glossary_terms):
        """Mixed-case [[Colonial-Period]] resolves to `colonial-period`."""
        text = 'During the [[Colonial-Period]] much changed.'
        result = process_glossary_links(text, glossary_terms)
        assert 'data-term-id="colonial-period"' in result
        assert '>Colonial Period</a>' in result

    def test_case_insensitive_match_with_custom_display(self, glossary_terms):
        """Mixed-case id with a pipe keeps the canonical id but custom display."""
        text = 'The [[Colonial-Period|early era]] mattered.'
        result = process_glossary_links(text, glossary_terms)
        assert 'data-term-id="colonial-period"' in result
        assert '>early era</a>' in result

    def test_resolves_against_uppercase_stored_key(self):
        """A glossary whose stored key is uppercase still resolves, using the
        stored key (not a lowercased copy) as the display title and data-term-id.

        Glossary loaders (CSV, markdown, demo bundle) store term_id verbatim, so
        keys are not guaranteed lowercase (e.g. the demo bundle stores 'IIIF').
        Matching must tolerate any author casing AND any stored-key casing, and
        the rendered data-term-id is the stored key. The page URL is a separate
        attribute (see TestPublishedTermUrl).
        """
        terms = {'IIIF': 'IIIF', 'colonial-period': 'Colonial Period'}
        # Author types lowercase; stored key is uppercase
        result_lower = process_glossary_links('Served via [[iiif]].', terms)
        assert 'glossary-inline-link' in result_lower
        assert 'data-term-id="IIIF"' in result_lower
        assert 'data-term-id="iiif"' not in result_lower
        # Author types the same uppercase as stored
        result_upper = process_glossary_links('Served via [[IIIF]].', terms)
        assert 'data-term-id="IIIF"' in result_upper

    def test_strip_unwraps_valid_glossary_link_to_plain_title(self, glossary_terms):
        """strip_glossary_links reduces a glossary <a> to its plain title text.

        Protected (encrypted) stories are rendered by a runtime path that escapes
        the step answer and has no glossary panel, so the link markup would show
        as escaped tag-text. The strip yields clean prose before encryption.
        """
        linked = process_glossary_links('During the [[colonial-period]] much changed.', glossary_terms)
        assert 'glossary-inline-link' in linked  # precondition
        stripped = strip_glossary_links(linked)
        assert stripped == 'During the Colonial Period much changed.'
        assert '<a' not in stripped and 'glossary-inline-link' not in stripped

    def test_strip_unescapes_entities_in_title(self):
        """The unwrapped title is HTML-unescaped so a later re-escape is correct."""
        terms = {'amp-term': 'Black & White'}
        linked = process_glossary_links('See [[amp-term]].', terms)
        assert '&amp;' in linked  # the title was html-escaped inside the anchor
        stripped = strip_glossary_links(linked)
        assert stripped == 'See Black & White.'  # unescaped back to a literal &

    def test_strip_reduces_error_span_to_literal_brackets(self, glossary_terms):
        """An unresolved term's error span is reduced to plain text, not tag-soup."""
        warnings = []
        linked = process_glossary_links('See [[no-such-term]] here.', glossary_terms, warnings)
        assert 'glossary-link-error' in linked  # precondition
        stripped = strip_glossary_links(linked)
        assert '<span' not in stripped
        assert '[[no-such-term]]' in stripped

    def test_strip_leaves_plain_text_unchanged(self):
        """Text with no glossary markup passes through untouched."""
        assert strip_glossary_links('Just plain prose.') == 'Just plain prose.'
        assert strip_glossary_links('') == ''
        assert strip_glossary_links(None) is None

    def test_strip_handles_multiple_links(self, glossary_terms):
        """All glossary links in a string are unwrapped."""
        linked = process_glossary_links('The [[viceroyalty]] used the [[encomienda]].', glossary_terms)
        stripped = strip_glossary_links(linked)
        assert stripped == 'The Viceroyalty used the Encomienda System.'

    def test_escapes_markup_in_invalid_term_error_span(self, glossary_terms):
        """A bogus term carrying markup is escaped in the error span."""
        text = 'see [[a"<x>z]] here'
        result = process_glossary_links(text, glossary_terms)
        assert 'data-term-id="a&quot;&lt;x&gt;z"' in result
        assert '<x>' not in result


class TestPublishedTermUrl:
    """An inline link carries the URL its term's page is published at.

    Jekyll publishes each glossary page at `/glossary/:name/`, where `:name`
    is `Jekyll::Utils.slugify` of the file's basename, and the build names the
    file after the stored term id. The page for `IIIF` is therefore at
    `/glossary/iiif/`, and a link that builds its URL from the id verbatim
    fetches a page that does not exist.

    The expected slugs below were produced by Jekyll 4.4.1's
    `Jekyll::Utils.slugify` (default mode) for the same inputs.
    """

    JEKYLL_SLUGS = [
        ('IIIF', 'iiif'),
        ('demo-IIIF', 'demo-iiif'),
        ('Colonial-Period', 'colonial-period'),
        ('colonial period', 'colonial-period'),
        ('Café Crème', 'café-crème'),
        ('ÉPOCA', 'época'),
        ('a.b', 'a-b'),
        ('a_b', 'a-b'),
        ('año-1810', 'año-1810'),
        ('x--y', 'x-y'),
        ('-lead-', 'lead'),
        ('KCSB2', 'kcsb2'),
        ('Ω-omega', 'ω-omega'),
        ('naïve', 'naïve'),
        ('term(1)', 'term-1'),
        ('ΟΣ', 'οσ'),
        ('ΛΟΓΟΣ ΚΑΛΟΣ', 'λογοσ-καλοσ'),
    ]

    @pytest.mark.parametrize('term_id,slug', JEKYLL_SLUGS)
    def test_slug_matches_jekyll(self, term_id, slug):
        from telar.glossary import glossary_term_slug
        assert glossary_term_slug(term_id) == slug

    def test_uppercase_stored_key_links_to_lowercase_page(self):
        terms = {'IIIF': 'IIIF'}
        result = process_glossary_links('Served via [[IIIF]].', terms, base_url='/telar')
        assert 'data-term-id="IIIF"' in result
        assert 'data-term-url="/telar/glossary/iiif/"' in result

    def test_author_casing_does_not_change_the_url(self):
        terms = {'IIIF': 'IIIF'}
        for typed in ('iiif', 'IIIF', 'Iiif'):
            result = process_glossary_links(f'[[{typed}]]', terms, base_url='')
            assert 'data-term-url="/glossary/iiif/"' in result

    def test_id_with_spaces_and_accents(self):
        terms = {'Época Colonial': 'Época colonial'}
        result = process_glossary_links('[[Época Colonial]]', terms, base_url='/sitio')
        assert 'data-term-url="/sitio/glossary/época-colonial/"' in result

    def test_display_text_form_carries_the_url(self):
        terms = {'Colonial-Period': 'Colonial Period'}
        result = process_glossary_links('[[colonial-period|that era]]', terms, base_url='')
        assert 'data-term-url="/glossary/colonial-period/"' in result
        assert '>that era</a>' in result

    def test_demo_term_carries_the_url(self):
        terms = {'demo-IIIF': 'IIIF'}
        result = process_glossary_links('[[demo-IIIF]]', terms, base_url='/telar')
        assert 'data-term-url="/telar/glossary/demo-iiif/"' in result
        assert 'data-demo="true"' in result

    def test_base_url_defaults_to_the_site_config(self, tmp_path, monkeypatch):
        from telar import widgets
        (tmp_path / '_config.yml').write_text('baseurl: "/mysite"\n', encoding='utf-8')
        monkeypatch.chdir(tmp_path)
        widgets.reset_base_url_cache()
        try:
            result = process_glossary_links('[[IIIF]]', {'IIIF': 'IIIF'})
        finally:
            widgets.reset_base_url_cache()
        assert 'data-term-url="/mysite/glossary/iiif/"' in result

    def test_unresolved_term_carries_no_url(self):
        result = process_glossary_links('[[nope]]', {'IIIF': 'IIIF'}, base_url='')
        assert 'glossary-link-error' in result
        assert 'data-term-url' not in result

    def test_strip_still_unwraps_a_link_with_a_url(self):
        linked = process_glossary_links('See [[IIIF]].', {'IIIF': 'IIIF'}, base_url='/telar')
        assert strip_glossary_links(linked) == 'See IIIF.'


class TestGlossaryLinksAndEscaping:
    """A link is made in text only, and its display
    text is decoded before it is escaped, on both paths."""

    TERMS = {'loom': 'Loom', 'IIIF': 'IIIF'}

    def _panel(self, markdown_text):
        from telar.markdown import process_inline_content
        out = process_inline_content(markdown_text, [])
        html_text = out.get('content') if isinstance(out, dict) else out
        return process_glossary_links(html_text, self.TERMS, base_url='')

    def test_glossary_syntax_in_alt_text_stays_literal(self):
        result = self._panel('![a [[IIIF]] b](b.jpg)')
        assert 'glossary-inline-link' not in result
        assert 'alt="a [[IIIF]] b"' in result

    def test_an_escaped_double_bracket_in_alt_text_stays_literal(self):
        result = self._panel('![&#91;&#91;loom&#93;&#93;](a.jpg)')
        assert 'glossary-inline-link' not in result
        assert 'alt="[[loom]]"' in result

    def test_a_link_beside_an_image_is_still_made(self):
        result = self._panel('See [[loom]] here.\n\n![a](a.jpg)')
        assert result.count('glossary-inline-link') == 1

    def test_a_link_after_a_less_than_sign_in_prose_is_made(self):
        result = process_glossary_links('x < [[loom]] > y', self.TERMS,
                                        base_url='')
        assert 'glossary-inline-link' in result

    @pytest.mark.parametrize('markup', [
        '<span title="x > [[loom]]">t</span>',
        "<span title='x > [[loom]]'>t</span>",
    ])
    def test_a_quoted_attribute_holding_a_greater_than_sign_stays_literal(
            self, markup):
        assert process_glossary_links(markup, self.TERMS, base_url='') == markup

    def test_text_after_a_tag_with_a_quoted_greater_than_is_linked(self):
        result = process_glossary_links("<span title='a > b'>[[loom]]</span>",
                                        self.TERMS, base_url='')
        assert '>Loom</a></span>' in result

    @pytest.mark.parametrize('display,shown', [
        ('a &#93; b', 'a ] b'),
        ('a &#124; b', 'a | b'),
        ('x &amp; y', 'x &amp; y'),
    ])
    def test_display_text_is_decoded_then_escaped_once_on_the_answer_path(
            self, display, shown):
        result = process_glossary_links(f'A [[loom|{display}]] c.',
                                        self.TERMS, base_url='')
        assert f'>{shown}</a>' in result

    def test_an_ampersand_in_display_text_is_escaped_once_in_a_panel(self):
        assert '>x &amp; y</a>' in self._panel('A [[loom|x & y]] c.')

    def test_an_entity_in_display_text_is_its_character_in_a_panel(self):
        assert '>a ] b</a>' in self._panel('A [[loom|a &#93; b]] c.')


class TestATermInTheTextOfALink:
    """A link cannot hold a link: a term in a link's text is shown as text,
    and the link around it is kept. Answers and panels are both rendered
    HTML when the link pass reads them, so one reading serves both."""

    TERMS = {'iiif': 'IIIF', 'encomienda': 'Encomienda System'}

    def _run(self, text):
        warnings = []
        out = process_glossary_links(text, self.TERMS, warnings, step_num=3,
                                     layer_name='layer1', base_url='')
        return out, warnings

    def test_a_term_in_an_anchor_is_its_title(self):
        out, warnings = self._run('<p><a href="b">see [[iiif]]</a> [[iiif]]</p>')
        assert out.startswith('<p><a href="b">see IIIF</a> <a href="#" class="glossary-inline-link"')
        assert [(w['step'], w['term_id'], w['type']) for w in warnings] == [(3, 'iiif', 'glossary')]
        assert 'link' in warnings[0]['message']

    def test_a_term_with_display_text(self):
        out, _ = self._run('<a href="b">see [[iiif|the standard]]</a>')
        assert out == '<a href="b">see the standard</a>'

    def test_a_missing_term_is_text_with_the_not_found_warning(self):
        out, warnings = self._run('<a href="b">see [[nope]]</a>')
        assert out == '<a href="b">see nope</a>'
        assert 'does not exist' in warnings[0]['message']

    def test_a_term_in_an_attribute_is_left_alone(self):
        out, warnings = self._run('<img alt="see [[iiif]]" src="b.png">')
        assert out == '<img alt="see [[iiif]]" src="b.png">'
        assert warnings == []

    def test_the_missing_entry_named_by_triple_brackets_is_unchanged(self):
        out, _ = self._run('[[[encomienda]]]')
        assert 'data-term-id="[encomienda"' in out

    def test_a_quoted_attribute_may_hold_markup(self):
        out, _ = self._run('<a title="> </a>" href="b">see [[iiif]]</a>')
        assert out == '<a title="> </a>" href="b">see IIIF</a>'

    def test_an_anchor_never_closed_runs_to_the_end(self):
        out, warnings = self._run('<a href="b">see [[iiif]] and [[iiif]]')
        assert out == '<a href="b">see IIIF and IIIF'
        assert len(warnings) == 2

    @pytest.mark.parametrize('source', [
        '<!-- <a href="b"> --> [[iiif]]',
        '<span title="<a href=b>">x</span> [[iiif]]',
        '<a-b>[[iiif]]</a-b> [[iiif]]',
    ], ids=['comment', 'attribute', 'longer-name'])
    def test_a_tag_that_is_not_an_anchor_holds_no_link(self, source):
        out, _ = self._run(source)
        assert out.endswith('>IIIF</a>')
        assert out.count('glossary-inline-link') == source.count('[[')

    def test_shown_text_is_escaped_for_html_only(self):
        out = process_glossary_links('<p><a href="b">[[iiif]]</a></p>', {'iiif': 'A *B* <b>'},
                                     [], base_url='')
        assert out == '<p><a href="b">A *B* &lt;b&gt;</a></p>'


class TestLinkTextIsReadInLinearTime:

    @pytest.mark.parametrize('unit', ['<a href="b">x [[iiif]]</a> ', '<a href="b">x </a>[[iiif]] ',
                                      '<a href="b">x [[iiif]] ', '<!-- <a> --> [[iiif]] '])
    def test_bounded(self, unit):
        import time
        started = time.perf_counter()
        process_glossary_links(unit * 20000, {'iiif': 'IIIF'}, [], base_url='')
        assert time.perf_counter() - started < 1.0

    @pytest.mark.parametrize('unit', ['<a "', '<a title="x ', '<b "', "<a '", '<a href="b',
                                      'x<y ', '<script>x [[iiif]] ',
                                      '<style>x</style>[[iiif]] '])
    def test_a_tag_never_closed_is_bounded(self, unit):
        import time
        started = time.perf_counter()
        process_glossary_links(unit * 20000 + ' [[iiif]]', {'iiif': 'IIIF'}, [], base_url='')
        assert time.perf_counter() - started < 1.0


class TestAPanelsAnchorsAreReadByAnHTMLTokenizer:
    """In a panel's HTML, the content of each `<a>` element, at exact
    offsets, as Python's HTML tokenizer reads the tags."""

    @pytest.mark.parametrize('text,anchors', [
        ('<p>x\n<a href="b">y\nz</a> w</p>', ['y\nz']),
        ('<A HREF=b>y</A>', ['y']),
        ('x<y <a>z</a>', []),
        ('<a title="</a>">y</a>', ['y']),
        ('<!-- <a> -->y', []),
        ('<a>x<a>y</a>', ['x', 'y']),
        ('<a>x\ny', ['x\ny']),
        ('<a/>y', ['y']),
        ('<code><a>x</a></code><a>y</a>', ['y']),
        ('<a-b>x</a-b>', []),
        ('&# &# <a>x</a>;', ['x']),
        ('&#5a<a>x</a>;', ['x']),
        ('&#x <a>y</a>', ['y']),
        ('a &#60 <a>z</a> &amp; <a href="?a=1&b=2">w</a>', ['z', 'w']),
    ])
    def test_offsets(self, text, anchors):
        regions = _link_text_regions(text)
        assert [text[start:end] for start, end in regions] == anchors

    def test_a_term_after_an_unparsed_tag_is_linked(self):
        out = process_glossary_links('x<y <a>[[iiif]]</a>', {'iiif': 'IIIF'}, [], base_url='')
        assert out.count('glossary-inline-link') == 1


class TestTextOnlyContentIsLeftAsWritten:
    """A term in the content of `script`, `style` or another element whose
    content is text only is markup there, not a link."""

    TERMS = {'iiif': 'IIIF'}

    @pytest.mark.parametrize('text', [
        '<script>const s="<a>[[iiif]]</a>";</script>',
        '<style>/* [[iiif]] */</style>',
        '<SCRIPT>[[iiif]]</SCRIPT >',
        '<textarea>[[iiif]]</textarea>',
        '<script>[[iiif]]',
        '<div><script>[[iiif]]</script></div>',
        'x <script>[[iiif]]</script>',
    ])
    def test_the_term_is_left_as_written(self, text):
        warnings = []
        out = process_glossary_links(text, self.TERMS, warnings, base_url='')
        assert out == text
        assert warnings == []

    def test_a_term_after_the_element_is_linked(self):
        out = process_glossary_links('<script>x</script>\n\n<p>[[iiif]]</p>', self.TERMS, [],
                                     base_url='')
        assert out.count('glossary-inline-link') == 1
