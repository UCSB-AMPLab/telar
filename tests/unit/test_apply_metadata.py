"""
Unit Tests for IIIF Metadata Fallback Application

This module tests the apply_metadata_fallback function that implements the
CSV > IIIF > empty fallback hierarchy for object metadata. When users leave
fields empty in their CSV, the function auto-populates them from IIIF
manifest metadata.

Key behavior:
- CSV values always take precedence (user override)
- IIIF values used when CSV field is empty
- Fields affected: title, description, creator, period, location, credit

Version: v0.8.0-beta
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import apply_metadata_fallback


class TestApplyMetadataFallback:
    """Tests for apply_metadata_fallback function."""

    def test_preserves_csv_values(self):
        """Should preserve existing CSV values over IIIF values."""
        row_dict = {
            'title': 'CSV Title',
            'creator': 'CSV Creator'
        }
        iiif_metadata = {
            'title': 'IIIF Title',
            'creator': 'IIIF Creator'
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict['title'] == 'CSV Title'
        assert row_dict['creator'] == 'CSV Creator'

    def test_fills_empty_with_iiif(self):
        """Should fill empty CSV fields with IIIF values."""
        row_dict = {
            'title': '',
            'creator': ''
        }
        iiif_metadata = {
            'title': 'IIIF Title',
            'creator': 'IIIF Creator'
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict['title'] == 'IIIF Title'
        assert row_dict['creator'] == 'IIIF Creator'

    def test_handles_whitespace_only_csv(self):
        """Should treat whitespace-only CSV as empty."""
        row_dict = {
            'title': '   ',
            'creator': '\t\n'
        }
        iiif_metadata = {
            'title': 'IIIF Title',
            'creator': 'IIIF Creator'
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict['title'] == 'IIIF Title'
        assert row_dict['creator'] == 'IIIF Creator'

    def test_handles_missing_csv_fields(self):
        """Should add IIIF values for missing CSV fields."""
        row_dict = {}
        iiif_metadata = {
            'title': 'IIIF Title',
            'description': 'IIIF Description'
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict['title'] == 'IIIF Title'
        assert row_dict['description'] == 'IIIF Description'

    def test_handles_missing_iiif_fields(self):
        """Should leave fields empty when IIIF doesn't have them."""
        row_dict = {
            'title': '',
            'creator': ''
        }
        iiif_metadata = {
            'title': 'IIIF Title'
            # No creator in IIIF
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict['title'] == 'IIIF Title'
        assert row_dict['creator'] == ''

    def test_handles_empty_iiif_values(self):
        """Should not overwrite with empty IIIF values."""
        row_dict = {
            'title': ''
        }
        iiif_metadata = {
            'title': ''
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict['title'] == ''

    def test_handles_whitespace_iiif_values(self):
        """Should not overwrite with whitespace-only IIIF values."""
        row_dict = {
            'title': ''
        }
        iiif_metadata = {
            'title': '   '
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict['title'] == ''

    def test_all_supported_fields(self):
        """Should handle all six supported metadata fields."""
        row_dict = {}
        iiif_metadata = {
            'title': 'Title',
            'description': 'Description',
            'creator': 'Creator',
            'period': 'Period',
            'source': 'Source',
            'credit': 'Credit'
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict['title'] == 'Title'
        assert row_dict['description'] == 'Description'
        assert row_dict['creator'] == 'Creator'
        assert row_dict['period'] == 'Period'
        assert row_dict['source'] == 'Source'
        assert row_dict['credit'] == 'Credit'

    def test_partial_csv_override(self):
        """Should allow partial CSV override of IIIF values."""
        row_dict = {
            'title': 'My Custom Title',
            'description': '',
            'creator': 'Custom Creator',
            'period': '',
            'source': '',
            'credit': ''
        }
        iiif_metadata = {
            'title': 'IIIF Title',
            'description': 'IIIF Description',
            'creator': 'IIIF Creator',
            'period': '1850-1900',
            'source': 'British Museum',
            'credit': 'Museum Collection'
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict['title'] == 'My Custom Title'
        assert row_dict['description'] == 'IIIF Description'
        assert row_dict['creator'] == 'Custom Creator'
        assert row_dict['period'] == '1850-1900'
        assert row_dict['source'] == 'British Museum'
        assert row_dict['credit'] == 'Museum Collection'

    def test_modifies_dict_in_place(self):
        """Should modify row_dict in place (no return value needed)."""
        original = {'title': ''}
        iiif = {'title': 'IIIF Title'}
        result = apply_metadata_fallback(original, iiif)
        assert result is None
        assert original['title'] == 'IIIF Title'

    def test_handles_non_string_values(self):
        """Should handle non-string values gracefully."""
        row_dict = {
            'title': None,
            'period': 1850
        }
        iiif_metadata = {
            'title': 'IIIF Title',
            'period': '1900'
        }
        apply_metadata_fallback(row_dict, iiif_metadata)
        # None converts to 'None' string which is truthy after str().strip()
        # Integer 1850 converts to '1850' which is truthy
        # Both are considered non-empty CSV values, so they're preserved
        assert row_dict['title'] == None  # None as string 'None' is truthy
        assert row_dict['period'] == 1850  # '1850' is truthy

    def test_empty_dicts(self):
        """Should handle empty input dicts without error."""
        row_dict = {}
        iiif_metadata = {}
        apply_metadata_fallback(row_dict, iiif_metadata)
        assert row_dict == {}
