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

Version: v0.7.0-beta
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
