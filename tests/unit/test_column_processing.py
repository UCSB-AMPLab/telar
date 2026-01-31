"""
Unit Tests for Column Processing Functions

This module tests the bilingual column name handling introduced in v0.6.0,
which allows users to write CSV headers in either English or Spanish. It also
tests the header row detection logic that enables dual-language header rows
in a single CSV file.

The column mapping is central to Telar's internationalization strategy —
it allows Spanish-speaking users to work entirely in their language while
the build system normalizes everything to English internally.

Version: v0.7.0-beta
"""

import sys
import os
import pytest
import pandas as pd

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import (
    normalize_column_names,
    is_header_row,
    COLUMN_NAME_MAPPING,
)


class TestNormalizeColumnNames:
    """Tests for normalize_column_names function."""

    def test_normalizes_spanish_story_columns(self):
        """Spanish story column names should be converted to English."""
        df = pd.DataFrame({
            'paso': [1, 2],
            'objeto': ['obj-1', 'obj-2'],
            'pregunta': ['Q1', 'Q2'],
            'respuesta': ['A1', 'A2'],
        })
        result = normalize_column_names(df)
        assert 'step' in result.columns
        assert 'object' in result.columns
        assert 'question' in result.columns
        assert 'answer' in result.columns

    def test_normalizes_spanish_layer_columns(self):
        """Spanish layer column names should be normalized."""
        df = pd.DataFrame({
            'boton_capa1': ['Learn more'],
            'contenido_capa1': ['Content'],
            'boton_capa2': ['Go deeper'],
            'contenido_capa2': ['More content'],
        })
        result = normalize_column_names(df)
        assert 'layer1_button' in result.columns
        assert 'layer1_content' in result.columns
        assert 'layer2_button' in result.columns
        assert 'layer2_content' in result.columns

    def test_backward_compatibility_layer_file(self):
        """Legacy layer1_file columns should map to layer1_content."""
        df = pd.DataFrame({
            'layer1_file': ['path/to/file.md'],
            'layer2_file': ['path/to/file2.md'],
        })
        result = normalize_column_names(df)
        assert 'layer1_content' in result.columns
        assert 'layer2_content' in result.columns

    def test_backward_compatibility_archivo_capa(self):
        """Legacy archivo_capa columns should map to layer_content."""
        df = pd.DataFrame({
            'archivo_capa1': ['archivo.md'],
            'archivo_capa2': ['archivo2.md'],
        })
        result = normalize_column_names(df)
        assert 'layer1_content' in result.columns
        assert 'layer2_content' in result.columns

    def test_normalizes_spanish_object_columns(self):
        """Spanish object column names should be converted to English."""
        df = pd.DataFrame({
            'id_objeto': ['obj-1'],
            'titulo': ['Title'],
            'descripcion': ['Description'],
            'creador': ['Artist'],
        })
        result = normalize_column_names(df)
        assert 'object_id' in result.columns
        assert 'title' in result.columns
        assert 'description' in result.columns
        assert 'creator' in result.columns

    def test_normalizes_spanish_project_columns(self):
        """Spanish project column names should be converted to English."""
        df = pd.DataFrame({
            'orden': [1, 2],
            'id_historia': ['story-1', 'story-2'],
            'titulo': ['Title 1', 'Title 2'],
            'subtitulo': ['Sub 1', 'Sub 2'],
            'firma': ['By Author', 'By Author'],
        })
        result = normalize_column_names(df)
        assert 'order' in result.columns
        assert 'story_id' in result.columns
        assert 'title' in result.columns
        assert 'subtitle' in result.columns
        assert 'byline' in result.columns

    def test_preserves_english_columns(self):
        """English column names should remain unchanged."""
        df = pd.DataFrame({
            'step': [1],
            'object': ['obj-1'],
            'question': ['Q1'],
        })
        result = normalize_column_names(df)
        assert 'step' in result.columns
        assert 'object' in result.columns
        assert 'question' in result.columns

    def test_preserves_unknown_columns(self):
        """Unknown column names should remain unchanged."""
        df = pd.DataFrame({
            'custom_column': ['value'],
            'another_custom': ['value2'],
        })
        result = normalize_column_names(df)
        assert 'custom_column' in result.columns
        assert 'another_custom' in result.columns

    def test_case_insensitive_matching(self):
        """Column name matching should be case-insensitive."""
        df = pd.DataFrame({
            'PASO': [1],
            'Objeto': ['obj-1'],
            'PREGUNTA': ['Q1'],
        })
        result = normalize_column_names(df)
        assert 'step' in result.columns
        assert 'object' in result.columns
        assert 'question' in result.columns


class TestIsHeaderRow:
    """Tests for is_header_row function."""

    def test_detects_english_header_row(self):
        """Should detect English column names as header row."""
        row = ['step', 'object', 'question', 'answer', 'x', 'y', 'zoom']
        assert is_header_row(row) is True

    def test_detects_spanish_header_row(self):
        """Should detect Spanish column names as header row."""
        row = ['paso', 'objeto', 'pregunta', 'respuesta', 'x', 'y', 'zoom']
        assert is_header_row(row) is True

    def test_rejects_data_row(self):
        """Should reject rows with data values."""
        row = [1, 'textile-001', 'What is this?', 'A textile.', 0.5, 0.5, 1.0]
        assert is_header_row(row) is False

    def test_handles_mixed_case(self):
        """Should handle mixed case column names."""
        row = ['Step', 'OBJECT', 'Question', 'answer']
        assert is_header_row(row) is True

    def test_handles_partial_headers(self):
        """Should detect row as header if 80%+ cells are column names."""
        row = ['step', 'object', 'question', 'unknown_col', 'x']
        # 4 of 5 are valid (80%), so this should pass
        assert is_header_row(row) is True

    def test_rejects_low_match_rate(self):
        """Should reject row if less than 80% are column names."""
        row = ['value1', 'value2', 'step', 'value3', 'value4']
        # Only 1 of 5 is valid (20%), should fail
        assert is_header_row(row) is False

    def test_handles_nan_values(self):
        """Should ignore NaN values in calculation."""
        row = ['step', 'object', None, None, 'question']
        # 3 valid of 3 non-empty = 100%
        assert is_header_row(row) is True

    def test_handles_completely_empty_row(self):
        """Should return False for completely empty row."""
        row = [None, None, '', '']
        assert is_header_row(row) is False
