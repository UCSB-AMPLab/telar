"""
Unit Tests for Widget Parsing Functions

This module tests the widget parsing system that powers Telar's interactive
components (carousels, tabs, accordions). Widgets are defined using a
CommonMark-style syntax with triple colons (:::widget_type) and parsed
into structured data for HTML rendering.

The parsing involves:
- Key-value block parsing for carousel items
- Markdown section parsing for tabs and accordions
- Validation of required fields and constraints

Version: v0.7.0-beta
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import (
    parse_key_value_block,
    parse_markdown_sections,
    parse_tabs_widget,
    parse_accordion_widget,
)


class TestParseKeyValueBlock:
    """Tests for parse_key_value_block function."""

    def test_parses_simple_key_value(self):
        """Should parse simple key: value pairs."""
        content = """image: photo.jpg
alt: A description
caption: Photo caption"""
        result = parse_key_value_block(content)
        assert result['image'] == 'photo.jpg'
        assert result['alt'] == 'A description'
        assert result['caption'] == 'Photo caption'

    def test_handles_colons_in_value(self):
        """Should handle colons within the value."""
        content = "url: https://example.com/path"
        result = parse_key_value_block(content)
        assert result['url'] == 'https://example.com/path'

    def test_strips_whitespace(self):
        """Should strip whitespace from keys and values."""
        content = "  key  :   value with spaces  "
        result = parse_key_value_block(content)
        assert result['key'] == 'value with spaces'

    def test_ignores_comment_lines(self):
        """Should ignore lines starting with #."""
        content = """image: photo.jpg
# This is a comment
alt: Description"""
        result = parse_key_value_block(content)
        assert 'image' in result
        assert 'alt' in result
        assert len(result) == 2

    def test_ignores_lines_without_colon(self):
        """Should ignore lines that don't contain colons."""
        content = """image: photo.jpg
This line has no colon
alt: Description"""
        result = parse_key_value_block(content)
        assert len(result) == 2

    def test_handles_empty_value(self):
        """Should handle empty values."""
        content = "key:"
        result = parse_key_value_block(content)
        assert result['key'] == ''

    def test_handles_empty_input(self):
        """Should return empty dict for empty input."""
        result = parse_key_value_block('')
        assert result == {}

    def test_handles_multiline_content(self):
        """Should parse multiple lines correctly."""
        content = """
image: img1.jpg
alt: Alt text
caption: Caption here
credit: Photo credit
"""
        result = parse_key_value_block(content)
        assert len(result) == 4


class TestParseMarkdownSections:
    """Tests for parse_markdown_sections function."""

    def test_parses_two_sections(self):
        """Should parse content with two ## headers."""
        content = """## Section One
Content for section one.

## Section Two
Content for section two."""
        result = parse_markdown_sections(content)
        assert len(result) == 2
        assert result[0]['title'] == 'Section One'
        assert result[1]['title'] == 'Section Two'

    def test_converts_content_to_html(self):
        """Should convert section content to HTML."""
        content = """## My Section
This is **bold** text."""
        result = parse_markdown_sections(content)
        assert '<strong>bold</strong>' in result[0]['content_html']

    def test_handles_multiple_paragraphs(self):
        """Should handle multiple paragraphs in a section."""
        content = """## Section
First paragraph.

Second paragraph."""
        result = parse_markdown_sections(content)
        assert result[0]['content_html'].count('<p>') >= 2

    def test_ignores_content_before_first_header(self):
        """Should ignore content before the first ## header."""
        content = """Some intro text

## First Section
Section content."""
        result = parse_markdown_sections(content)
        assert len(result) == 1
        assert result[0]['title'] == 'First Section'

    def test_handles_empty_sections(self):
        """Should handle sections with no content."""
        content = """## Empty Section
## Next Section
Content here."""
        result = parse_markdown_sections(content)
        assert len(result) == 2
        # First section should have empty or minimal content
        assert result[0]['title'] == 'Empty Section'

    def test_handles_headers_with_special_chars(self):
        """Should handle section titles with special characters."""
        content = """## 1600-1650: Early Period
Content about early period."""
        result = parse_markdown_sections(content)
        assert result[0]['title'] == '1600-1650: Early Period'


class TestParseTabsWidget:
    """Tests for parse_tabs_widget function."""

    def test_parses_valid_tabs(self):
        """Should parse valid tabs widget with 2+ tabs."""
        content = """## Tab One
Content for tab one.

## Tab Two
Content for tab two."""
        warnings = []
        result = parse_tabs_widget(content, 'test.md', warnings)
        assert len(result['tabs']) == 2
        assert len(warnings) == 0

    def test_warns_for_single_tab(self):
        """Should warn when only one tab is provided."""
        content = """## Only Tab
Content here."""
        warnings = []
        result = parse_tabs_widget(content, 'test.md', warnings)
        assert len(result['tabs']) == 1
        assert len(warnings) == 1
        assert 'at least 2 tabs' in warnings[0]['message']

    def test_warns_for_too_many_tabs(self):
        """Should warn when more than 4 tabs are provided."""
        content = """## Tab 1
Content.

## Tab 2
Content.

## Tab 3
Content.

## Tab 4
Content.

## Tab 5
Content."""
        warnings = []
        result = parse_tabs_widget(content, 'test.md', warnings)
        assert len(result['tabs']) == 5
        assert any('maximum 4 tabs' in w['message'] for w in warnings)

    def test_warns_for_empty_tab_content(self):
        """Should warn when a tab has no content."""
        content = """## Tab One

## Tab Two
Content here."""
        warnings = []
        result = parse_tabs_widget(content, 'test.md', warnings)
        assert any('has no content' in w['message'] for w in warnings)


class TestParseAccordionWidget:
    """Tests for parse_accordion_widget function."""

    def test_parses_valid_accordion(self):
        """Should parse valid accordion with 2+ panels."""
        content = """## Panel One
Content for panel one.

## Panel Two
Content for panel two."""
        warnings = []
        result = parse_accordion_widget(content, 'test.md', warnings)
        assert len(result['panels']) == 2
        assert len(warnings) == 0

    def test_warns_for_single_panel(self):
        """Should warn when only one panel is provided."""
        content = """## Only Panel
Content here."""
        warnings = []
        result = parse_accordion_widget(content, 'test.md', warnings)
        assert len(result['panels']) == 1
        assert len(warnings) == 1
        assert 'at least 2 panels' in warnings[0]['message']

    def test_warns_for_too_many_panels(self):
        """Should warn when more than 6 panels are provided."""
        content = "\n\n".join([f"## Panel {i}\nContent." for i in range(1, 8)])
        warnings = []
        result = parse_accordion_widget(content, 'test.md', warnings)
        assert len(result['panels']) == 7
        assert any('maximum 6 panels' in w['message'] for w in warnings)
