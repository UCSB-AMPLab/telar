"""
Unit Tests for Project Setup Processing

This module tests the process_project_setup function that converts project.csv
data into the JSON structure used by Jekyll. The project CSV defines the story
catalog with ordering, titles, subtitles, bylines, and optional story_id
identifiers.

Key behavior:
- Converts order column to 'number' in JSON
- Validates story_id format (lowercase, numbers, hyphens, underscores)
- Warns about duplicate story_ids
- Skips rows with empty order or title
- Returns a DataFrame with a 'stories' column containing the list

Version: v0.7.0-beta
"""

import sys
import os
import pytest
import pandas as pd

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import process_project_setup


def get_stories(result_df):
    """Helper to extract stories list from result DataFrame."""
    return result_df.iloc[0]['stories']


class TestProcessProjectSetup:
    """Tests for process_project_setup function."""

    def test_processes_basic_project(self):
        """Should process basic project with order and title."""
        df = pd.DataFrame({
            'order': ['1', '2'],
            'title': ['First Story', 'Second Story']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert len(stories) == 2
        assert stories[0]['number'] == '1'
        assert stories[0]['title'] == 'First Story'

    def test_includes_subtitle(self):
        """Should include subtitle when present."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story Title'],
            'subtitle': ['A fascinating tale']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert stories[0]['subtitle'] == 'A fascinating tale'

    def test_includes_byline(self):
        """Should include byline when present."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story Title'],
            'byline': ['By Jane Author']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert stories[0]['byline'] == 'By Jane Author'

    def test_includes_story_id(self):
        """Should include story_id when present."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story Title'],
            'story_id': ['my-story']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert stories[0]['story_id'] == 'my-story'

    def test_skips_empty_order(self):
        """Should skip rows with empty order."""
        df = pd.DataFrame({
            'order': ['1', '', '3'],
            'title': ['First', 'Second', 'Third']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert len(stories) == 2
        assert stories[0]['number'] == '1'
        assert stories[1]['number'] == '3'

    def test_skips_nan_title(self):
        """Should skip rows with NaN title."""
        df = pd.DataFrame({
            'order': ['1', '2'],
            'title': ['First Story', None]
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert len(stories) == 1

    def test_handles_empty_subtitle(self):
        """Should not include empty subtitle in output."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story'],
            'subtitle': ['']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert 'subtitle' not in stories[0]

    def test_handles_nan_subtitle(self):
        """Should not include NaN subtitle in output."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story'],
            'subtitle': [None]
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert 'subtitle' not in stories[0]

    def test_handles_empty_byline(self):
        """Should not include empty byline in output."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story'],
            'byline': ['']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert 'byline' not in stories[0]

    def test_strips_whitespace_from_order(self):
        """Should strip whitespace from order values."""
        df = pd.DataFrame({
            'order': ['  1  '],
            'title': ['Story']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert stories[0]['number'] == '1'

    def test_strips_whitespace_from_story_id(self):
        """Should strip whitespace from story_id values."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story'],
            'story_id': ['  my-story  ']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert stories[0]['story_id'] == 'my-story'

    def test_strips_whitespace_from_subtitle(self):
        """Should strip whitespace from subtitle values."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story'],
            'subtitle': ['  Subtitle text  ']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert stories[0]['subtitle'] == 'Subtitle text'

    def test_handles_missing_story_id_column(self):
        """Should handle dataframe without story_id column."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert 'story_id' not in stories[0]

    def test_excludes_empty_story_id(self):
        """Should not include empty story_id in output."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story'],
            'story_id': ['']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert 'story_id' not in stories[0]

    def test_handles_nan_story_id(self):
        """Should handle NaN story_id gracefully."""
        df = pd.DataFrame({
            'order': ['1'],
            'title': ['Story'],
            'story_id': [None]
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert 'story_id' not in stories[0]

    def test_valid_story_id_formats(self):
        """Should accept valid story_id formats."""
        valid_ids = ['my-story', 'story_1', 'story123', 'a-b_c-1']
        for story_id in valid_ids:
            df = pd.DataFrame({
                'order': ['1'],
                'title': ['Story'],
                'story_id': [story_id]
            })
            result = process_project_setup(df)
            stories = get_stories(result)
            assert stories[0]['story_id'] == story_id

    def test_preserves_order_of_stories(self):
        """Should preserve the order of stories from CSV."""
        df = pd.DataFrame({
            'order': ['3', '1', '2'],
            'title': ['Third', 'First', 'Second']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert stories[0]['number'] == '3'
        assert stories[1]['number'] == '1'
        assert stories[2]['number'] == '2'

    def test_handles_numeric_order(self):
        """Should handle numeric order values (not just strings)."""
        df = pd.DataFrame({
            'order': [1, 2, 3],
            'title': ['First', 'Second', 'Third']
        })
        result = process_project_setup(df)
        stories = get_stories(result)
        assert stories[0]['number'] == '1'
        assert stories[1]['number'] == '2'

    def test_empty_dataframe(self):
        """Should handle empty dataframe."""
        df = pd.DataFrame(columns=['order', 'title'])
        result = process_project_setup(df)
        stories = get_stories(result)
        assert stories == []
