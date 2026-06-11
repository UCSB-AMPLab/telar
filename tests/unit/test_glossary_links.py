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

Version: v1.5.1
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

# Mock the get_lang_string function to avoid loading config
import csv_to_json
csv_to_json.get_lang_string = lambda key, **kwargs: f"Term not found: {kwargs.get('term_id', 'unknown')}"

from csv_to_json import process_glossary_links
from telar.glossary import strip_glossary_links


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
        the rendered data-term-id must equal the stored key so it matches the
        published glossary page slug.
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
