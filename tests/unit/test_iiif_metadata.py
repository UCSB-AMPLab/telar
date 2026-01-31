"""
Unit Tests for IIIF Metadata Extraction

This module tests functions that extract metadata from IIIF manifests. Telar
supports both IIIF Presentation API v2.0 and v3.0, which have significantly
different structures. These tests ensure correct version detection and
proper extraction of titles, creators, dates, and other metadata fields.

Key differences between versions:
- v2.0: Simple string values, @context contains "presentation/2"
- v3.0: Language maps ({"en": ["value"]}), @context contains "presentation/3"

Version: v0.7.0-beta
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import (
    detect_iiif_version,
    extract_language_map_value,
    find_metadata_field,
    is_legal_boilerplate,
)


class TestDetectIiifVersion:
    """Tests for detect_iiif_version function."""

    def test_detects_v2_from_string_context(self):
        """Should detect v2.0 from string @context."""
        manifest = {'@context': 'http://iiif.io/api/presentation/2/context.json'}
        assert detect_iiif_version(manifest) == '2.0'

    def test_detects_v3_from_string_context(self):
        """Should detect v3.0 from string @context."""
        manifest = {'@context': 'http://iiif.io/api/presentation/3/context.json'}
        assert detect_iiif_version(manifest) == '3.0'

    def test_detects_v3_from_array_context(self):
        """Should detect v3.0 from array @context."""
        manifest = {
            '@context': [
                'http://www.w3.org/ns/anno.jsonld',
                'http://iiif.io/api/presentation/3/context.json'
            ]
        }
        assert detect_iiif_version(manifest) == '3.0'

    def test_defaults_to_v2_when_missing(self):
        """Should default to v2.0 when @context is missing."""
        manifest = {'label': 'Test Manifest'}
        assert detect_iiif_version(manifest) == '2.0'

    def test_defaults_to_v2_when_unrecognized(self):
        """Should default to v2.0 for unrecognized context."""
        manifest = {'@context': 'http://example.com/unknown'}
        assert detect_iiif_version(manifest) == '2.0'

    def test_handles_empty_manifest(self):
        """Should handle empty manifest dict."""
        assert detect_iiif_version({}) == '2.0'


class TestExtractLanguageMapValue:
    """Tests for extract_language_map_value function."""

    def test_extracts_preferred_language(self):
        """Should extract value for site's preferred language."""
        language_map = {
            'en': ['English title'],
            'es': ['Spanish title'],
        }
        assert extract_language_map_value(language_map, 'es') == 'Spanish title'

    def test_falls_back_to_english(self):
        """Should fall back to English when preferred language unavailable."""
        language_map = {
            'en': ['English title'],
            'fr': ['French title'],
        }
        assert extract_language_map_value(language_map, 'de') == 'English title'

    def test_falls_back_to_none(self):
        """Should fall back to 'none' key when no languages match."""
        language_map = {
            'none': ['Unlabeled value'],
            'fr': ['French only'],
        }
        assert extract_language_map_value(language_map, 'de') == 'Unlabeled value'

    def test_uses_first_available(self):
        """Should use first available language as last resort."""
        language_map = {
            'ja': ['Japanese title'],
        }
        assert extract_language_map_value(language_map, 'en') == 'Japanese title'

    def test_handles_empty_array(self):
        """Should return empty string for empty arrays."""
        language_map = {'en': []}
        assert extract_language_map_value(language_map, 'en') == ''

    def test_handles_non_dict_input(self):
        """Should return empty string for non-dict input."""
        assert extract_language_map_value('not a dict', 'en') == ''
        assert extract_language_map_value(None, 'en') == ''

    def test_handles_multiple_values_in_array(self):
        """Should return first value when multiple exist."""
        language_map = {'en': ['First', 'Second', 'Third']}
        assert extract_language_map_value(language_map, 'en') == 'First'


class TestFindMetadataField:
    """Tests for find_metadata_field function."""

    def test_finds_exact_match_v2(self):
        """Should find field with exact label match (v2.0)."""
        metadata = [
            {'label': 'Creator', 'value': 'John Smith'},
            {'label': 'Date', 'value': '1850'},
        ]
        assert find_metadata_field(metadata, ['creator'], '2.0') == 'John Smith'

    def test_finds_partial_match(self):
        """Should find field with partial label match."""
        metadata = [
            {'label': 'Date Created', 'value': '1850'},
        ]
        assert find_metadata_field(metadata, ['date'], '2.0') == '1850'

    def test_case_insensitive_search(self):
        """Should perform case-insensitive search."""
        metadata = [
            {'label': 'CREATOR', 'value': 'Artist Name'},
        ]
        assert find_metadata_field(metadata, ['creator'], '2.0') == 'Artist Name'

    def test_searches_multiple_terms(self):
        """Should try multiple search terms."""
        metadata = [
            {'label': 'Artist', 'value': 'Painter Name'},
        ]
        result = find_metadata_field(metadata, ['creator', 'artist', 'author'], '2.0')
        assert result == 'Painter Name'

    def test_handles_v3_language_maps(self):
        """Should handle v3.0 language maps in labels and values."""
        metadata = [
            {
                'label': {'en': ['Creator']},
                'value': {'en': ['John Smith']},
            },
        ]
        assert find_metadata_field(metadata, ['creator'], '3.0', 'en') == 'John Smith'

    def test_returns_empty_for_no_match(self):
        """Should return empty string when no match found."""
        metadata = [
            {'label': 'Title', 'value': 'Some Title'},
        ]
        assert find_metadata_field(metadata, ['creator'], '2.0') == ''

    def test_handles_empty_metadata(self):
        """Should handle empty or None metadata."""
        assert find_metadata_field([], ['creator'], '2.0') == ''
        assert find_metadata_field(None, ['creator'], '2.0') == ''

    def test_handles_malformed_entries(self):
        """Should skip malformed metadata entries."""
        metadata = [
            'not a dict',
            {'label': 'Creator', 'value': 'Valid Artist'},
        ]
        assert find_metadata_field(metadata, ['creator'], '2.0') == 'Valid Artist'


class TestIsLegalBoilerplate:
    """Tests for is_legal_boilerplate function."""

    def test_detects_url_as_boilerplate(self):
        """Should detect URLs as boilerplate."""
        assert is_legal_boilerplate('https://example.com/rights') is True
        assert is_legal_boilerplate('http://library.edu/permissions') is True

    def test_detects_rights_language(self):
        """Should detect rights/permissions language as boilerplate."""
        text = "For information on use and rights and permissions, please see the library."
        assert is_legal_boilerplate(text) is True

    def test_detects_license_references(self):
        """Should detect license references as boilerplate."""
        text = "This work is licensed under Creative Commons. For more information visit..."
        assert is_legal_boilerplate(text) is True

    def test_accepts_simple_credit(self):
        """Should accept simple credit lines."""
        assert is_legal_boilerplate('Photo by John Smith') is False
        assert is_legal_boilerplate('Courtesy of the British Museum') is False

    def test_accepts_institution_names(self):
        """Should accept institution names."""
        assert is_legal_boilerplate('Princeton University Library') is False
        assert is_legal_boilerplate('National Archives of Colombia') is False

    def test_detects_very_long_text(self):
        """Should detect very long text as likely boilerplate."""
        long_text = "A" * 250  # 250 characters
        assert is_legal_boilerplate(long_text) is True

    def test_handles_empty_input(self):
        """Should return False for empty input."""
        assert is_legal_boilerplate('') is False
        assert is_legal_boilerplate(None) is False
