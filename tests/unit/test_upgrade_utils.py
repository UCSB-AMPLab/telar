"""
Unit Tests for Upgrade Script Utilities

This module tests utility functions from the upgrade script that are used
to organize and present migration changes to users. The categorization
function groups changes by file type for better readability.

Version: v0.7.0-beta
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from upgrade import _categorize_changes


class TestCategorizeChanges:
    """Tests for _categorize_changes function."""

    def test_categorizes_config_changes(self):
        """Should categorize _config.yml changes as Configuration."""
        changes = [
            'Updated _config.yml with new settings',
            'Modified configuration for theme',
        ]
        result = _categorize_changes(changes)
        assert 'Configuration' in result
        assert len(result['Configuration']) == 2

    def test_categorizes_layout_changes(self):
        """Should categorize layout changes."""
        changes = [
            'Updated layout for story pages',
            'Modified _layouts/default.html',
        ]
        result = _categorize_changes(changes)
        assert 'Layouts' in result
        assert len(result['Layouts']) == 2

    def test_categorizes_include_changes(self):
        """Should categorize include file changes."""
        changes = [
            'Updated _includes/header.html',
            'Modified include for footer',
        ]
        result = _categorize_changes(changes)
        assert 'Includes' in result
        assert len(result['Includes']) == 2

    def test_categorizes_style_changes(self):
        """Should categorize CSS/SCSS changes as Styles."""
        changes = [
            'Updated main.scss with new variables',
            'Modified style for buttons',
            'Changed assets/css/telar.css',
        ]
        result = _categorize_changes(changes)
        assert 'Styles' in result
        assert len(result['Styles']) == 3

    def test_categorizes_script_changes(self):
        """Should categorize JavaScript changes as Scripts."""
        changes = [
            'Updated story.js navigation',
            'Modified JavaScript for panels',
            'Changed assets/js/viewer.js',
        ]
        result = _categorize_changes(changes)
        assert 'Scripts' in result
        assert len(result['Scripts']) == 3

    def test_categorizes_documentation_changes(self):
        """Should categorize documentation changes."""
        changes = [
            'Updated README.md',
            'Modified docs for installation',
            'Changed documentation structure',
        ]
        result = _categorize_changes(changes)
        assert 'Documentation' in result
        assert len(result['Documentation']) == 3

    def test_categorizes_other_changes(self):
        """Should categorize unrecognized changes as Other."""
        changes = [
            'Added new feature',
            'Removed deprecated code',
        ]
        result = _categorize_changes(changes)
        assert 'Other' in result
        assert len(result['Other']) == 2

    def test_handles_mixed_changes(self):
        """Should correctly categorize a mix of different changes."""
        changes = [
            'Updated _config.yml',
            'Modified _layouts/story.html',
            'Changed main.scss',
            'Updated story.js',
            'Fixed README.md',
            'Added new helper function',
        ]
        result = _categorize_changes(changes)
        assert 'Configuration' in result
        assert 'Layouts' in result
        assert 'Styles' in result
        assert 'Scripts' in result
        assert 'Documentation' in result
        assert 'Other' in result

    def test_empty_changes_list(self):
        """Should return empty dict for empty input."""
        result = _categorize_changes([])
        assert result == {}

    def test_removes_empty_categories(self):
        """Should not include categories with no changes."""
        changes = [
            'Updated _config.yml',
        ]
        result = _categorize_changes(changes)
        assert 'Configuration' in result
        assert 'Layouts' not in result
        assert 'Includes' not in result

    def test_case_insensitive_matching(self):
        """Should match categories case-insensitively."""
        changes = [
            'Updated _CONFIG.YML',
            'Modified LAYOUT for pages',
            'Changed STYLE.CSS',
        ]
        result = _categorize_changes(changes)
        assert 'Configuration' in result
        assert 'Layouts' in result
        assert 'Styles' in result

    def test_prioritizes_specific_patterns(self):
        """Should prioritize specific patterns over general ones."""
        # _config.yml contains both 'config' and could match others
        changes = [
            '_config.yml: added new script setting',
        ]
        result = _categorize_changes(changes)
        # Should be categorized as Configuration, not Scripts
        assert 'Configuration' in result
        assert result['Configuration'][0] == '_config.yml: added new script setting'
