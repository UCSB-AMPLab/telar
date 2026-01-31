"""
Unit Tests for IIIF Credit Extraction

This module tests the extract_credit function that pulls attribution/credit
information from IIIF manifests. The function handles both IIIF Presentation
API v2.0 (simple attribution field) and v3.0 (requiredStatement with language
maps), with smart fallback logic when attribution contains legal boilerplate.

Key behavior:
- v2.0: Uses 'attribution' field directly
- v3.0: Uses requiredStatement.value or provider.label
- Falls back to repository/institution if attribution is legal boilerplate

Version: v0.7.0-beta
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import extract_credit


class TestExtractCreditV2:
    """Tests for extract_credit with IIIF v2.0 manifests."""

    def test_extracts_simple_attribution(self):
        """Should extract attribution from v2.0 manifest."""
        manifest = {
            'attribution': 'National Museum Collection'
        }
        result = extract_credit(manifest, version='2.0')
        assert result == 'National Museum Collection'

    def test_handles_empty_attribution(self):
        """Should return empty string when no attribution."""
        manifest = {}
        result = extract_credit(manifest, version='2.0')
        assert result == ''

    def test_cleans_html_from_attribution(self):
        """Should clean HTML tags from attribution."""
        manifest = {
            'attribution': '<span>Museum <a href="#">Collection</a></span>'
        }
        result = extract_credit(manifest, version='2.0')
        assert '<' not in result
        assert '>' not in result

    def test_falls_back_when_attribution_is_url(self):
        """Should fall back to repository when attribution is just a URL."""
        manifest = {
            'attribution': 'https://library.edu/rights',
            'metadata': [
                {'label': 'Repository', 'value': 'University Library'}
            ]
        }
        result = extract_credit(manifest, version='2.0')
        assert result == 'University Library'

    def test_falls_back_when_attribution_is_boilerplate(self):
        """Should fall back when attribution is legal boilerplate."""
        manifest = {
            # Text with 2+ boilerplate indicators: 'for information on use' and 'rights and permissions'
            'attribution': 'For information on use and rights and permissions, please see the library website.',
            'metadata': [
                {'label': 'Holding Institution', 'value': 'British Museum'}
            ]
        }
        result = extract_credit(manifest, version='2.0')
        assert result == 'British Museum'

    def test_keeps_simple_credit(self):
        """Should keep simple credit lines that aren't boilerplate."""
        manifest = {
            'attribution': 'Courtesy of the National Gallery'
        }
        result = extract_credit(manifest, version='2.0')
        assert result == 'Courtesy of the National Gallery'


class TestExtractCreditV3:
    """Tests for extract_credit with IIIF v3.0 manifests."""

    def test_extracts_required_statement(self):
        """Should extract from requiredStatement.value language map."""
        manifest = {
            'requiredStatement': {
                'label': {'en': ['Attribution']},
                'value': {'en': ['Metropolitan Museum of Art']}
            }
        }
        result = extract_credit(manifest, version='3.0', site_language='en')
        assert result == 'Metropolitan Museum of Art'

    def test_extracts_preferred_language(self):
        """Should extract value in preferred language."""
        manifest = {
            'requiredStatement': {
                'label': {'en': ['Attribution']},
                'value': {
                    'en': ['English credit'],
                    'es': ['Credito en espanol']
                }
            }
        }
        result = extract_credit(manifest, version='3.0', site_language='es')
        assert result == 'Credito en espanol'

    def test_falls_back_to_provider(self):
        """Should fall back to provider label when no requiredStatement."""
        manifest = {
            'provider': [
                {
                    'label': {'en': ['Princeton University Library']}
                }
            ]
        }
        result = extract_credit(manifest, version='3.0', site_language='en')
        assert result == 'Princeton University Library'

    def test_handles_string_required_statement_value(self):
        """Should handle requiredStatement with string value (non-standard)."""
        manifest = {
            'requiredStatement': {
                'label': {'en': ['Credit']},
                'value': 'Simple string value'
            }
        }
        result = extract_credit(manifest, version='3.0')
        assert result == 'Simple string value'

    def test_handles_empty_required_statement(self):
        """Should handle empty requiredStatement gracefully."""
        manifest = {
            'requiredStatement': {}
        }
        result = extract_credit(manifest, version='3.0')
        assert result == ''

    def test_handles_empty_provider(self):
        """Should handle empty provider list gracefully."""
        manifest = {
            'provider': []
        }
        result = extract_credit(manifest, version='3.0')
        assert result == ''


class TestExtractCreditFallback:
    """Tests for credit extraction fallback behavior."""

    def test_tries_multiple_metadata_fields(self):
        """Should try multiple field names for fallback."""
        manifest = {
            'attribution': 'http://example.com/rights',
            'metadata': [
                {'label': 'Institution', 'value': 'Found via Institution'}
            ]
        }
        result = extract_credit(manifest, version='2.0')
        assert result == 'Found via Institution'

    def test_keeps_boilerplate_when_no_fallback(self):
        """Should keep original attribution when no fallback available."""
        manifest = {
            'attribution': 'http://example.com/rights',
            'metadata': [
                {'label': 'Title', 'value': 'Not a repository field'}
            ]
        }
        result = extract_credit(manifest, version='2.0')
        # URL is boilerplate but no repository fallback found, so keeps URL
        assert result == 'http://example.com/rights'

    def test_keeps_boilerplate_when_missing_metadata(self):
        """Should keep attribution when no metadata array exists."""
        manifest = {
            'attribution': 'http://example.com/rights'
        }
        result = extract_credit(manifest, version='2.0')
        # No metadata to fall back to, so keeps URL
        assert result == 'http://example.com/rights'
