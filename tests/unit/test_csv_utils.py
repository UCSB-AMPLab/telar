"""
Unit Tests for csv_to_json.py Utility Functions

This module tests the core utility functions used in Telar's CSV processing
pipeline. These functions handle DataFrame sanitization, URL extraction,
HTML stripping, and metadata cleaning — foundational operations that the
rest of the build system relies on.

The tests here ensure backward compatibility (e.g., legacy iiif_manifest
column support) and correct handling of edge cases (empty values, malformed
HTML, Unicode content).

Version: v0.7.0-beta
"""

import sys
import os
import pytest
import pandas as pd

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import (
    sanitize_dataframe,
    get_source_url,
    strip_html_tags,
    clean_metadata_value,
)


class TestSanitizeDataframe:
    """Tests for sanitize_dataframe function."""

    def test_removes_christmas_tree_emoji(self):
        """Christmas tree emoji should be removed from all string fields."""
        df = pd.DataFrame({
            'title': ['Hello 🎄 World'],
            'description': ['Test 🎄 content 🎄']
        })
        result = sanitize_dataframe(df)
        assert result['title'].iloc[0] == 'Hello  World'
        assert result['description'].iloc[0] == 'Test  content '

    def test_preserves_other_content(self):
        """Non-emoji content should be preserved."""
        df = pd.DataFrame({
            'title': ['Normal Title'],
            'number': [42]
        })
        result = sanitize_dataframe(df)
        assert result['title'].iloc[0] == 'Normal Title'
        assert result['number'].iloc[0] == 42

    def test_handles_nan_values(self):
        """NaN values should not cause errors."""
        df = pd.DataFrame({
            'title': ['Hello', None, 'World']
        })
        result = sanitize_dataframe(df)
        assert result['title'].iloc[0] == 'Hello'
        assert pd.isna(result['title'].iloc[1])
        assert result['title'].iloc[2] == 'World'


class TestGetSourceUrl:
    """Tests for get_source_url function."""

    def test_returns_source_url_when_present(self):
        """source_url should be returned when available."""
        row = {'source_url': 'https://example.com/manifest.json'}
        assert get_source_url(row) == 'https://example.com/manifest.json'

    def test_falls_back_to_iiif_manifest(self):
        """Should fall back to iiif_manifest when source_url is empty."""
        row = {'source_url': '', 'iiif_manifest': 'https://legacy.com/manifest'}
        assert get_source_url(row) == 'https://legacy.com/manifest'

    def test_source_url_takes_priority(self):
        """source_url should take priority over iiif_manifest."""
        row = {
            'source_url': 'https://new.com/manifest',
            'iiif_manifest': 'https://old.com/manifest'
        }
        assert get_source_url(row) == 'https://new.com/manifest'

    def test_returns_empty_when_neither_present(self):
        """Should return empty string when neither field exists."""
        row = {}
        assert get_source_url(row) == ''

    def test_strips_whitespace(self):
        """Whitespace should be stripped from URLs."""
        row = {'source_url': '  https://example.com/manifest  '}
        assert get_source_url(row) == 'https://example.com/manifest'


class TestStripHtmlTags:
    """Tests for strip_html_tags function."""

    def test_removes_html_tags(self):
        """HTML tags should be removed."""
        text = '<p>Hello <strong>World</strong></p>'
        assert strip_html_tags(text) == 'Hello World'

    def test_decodes_html_entities(self):
        """HTML entities should be decoded."""
        text = 'Hello &amp; World &lt;test&gt;'
        assert strip_html_tags(text) == 'Hello & World <test>'

    def test_normalizes_whitespace(self):
        """Extra whitespace should be collapsed."""
        text = 'Hello    World\n\nTest'
        assert strip_html_tags(text) == 'Hello World Test'

    def test_handles_empty_input(self):
        """Empty input should return empty string."""
        assert strip_html_tags('') == ''
        assert strip_html_tags(None) == ''

    def test_handles_nested_tags(self):
        """Nested HTML tags should be removed."""
        text = '<div><p>Nested <span>content</span></p></div>'
        assert strip_html_tags(text) == 'Nested content'


class TestCleanMetadataValue:
    """Tests for clean_metadata_value function."""

    def test_cleans_simple_string(self):
        """Simple string should be cleaned."""
        assert clean_metadata_value('  Hello World  ') == 'Hello World'

    def test_handles_list_values(self):
        """List values should be joined with semicolons."""
        value = ['First', 'Second', 'Third']
        assert clean_metadata_value(value) == 'First; Second; Third'

    def test_strips_html_from_values(self):
        """HTML should be stripped from values."""
        value = '<p>Hello</p>'
        assert clean_metadata_value(value) == 'Hello'

    def test_handles_empty_input(self):
        """Empty input should return empty string."""
        assert clean_metadata_value('') == ''
        assert clean_metadata_value(None) == ''
        assert clean_metadata_value([]) == ''

    def test_filters_empty_list_items(self):
        """Empty items in lists should be filtered out."""
        value = ['First', '', '  ', 'Second']
        assert clean_metadata_value(value) == 'First; Second'
