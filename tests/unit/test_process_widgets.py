"""
Unit Tests for Widget Processing Pipeline

This module tests the process_widgets function that finds and replaces
:::widget::: blocks in markdown text with rendered HTML. It also tests
the widget ID generation for unique component identification.

The widget processing pipeline:
1. Find :::type ... ::: blocks in text
2. Parse based on widget type (carousel, tabs, accordion)
3. Render HTML using Jinja2 templates
4. Replace original block with rendered HTML

Version: v0.7.0-beta
"""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

import telar.widgets
from csv_to_json import process_widgets, get_widget_id, render_widget_html


class TestGetWidgetId:
    """Tests for get_widget_id function."""

    def test_returns_widget_id_format(self):
        """Should return ID in widget-N format."""
        # Reset counter for predictable testing
        telar.widgets._widget_counter = 0
        widget_id = get_widget_id()
        assert widget_id.startswith('widget-')
        assert widget_id == 'widget-1'

    def test_increments_counter(self):
        """Should increment counter for each call."""
        telar.widgets._widget_counter = 0
        id1 = get_widget_id()
        id2 = get_widget_id()
        id3 = get_widget_id()
        assert id1 == 'widget-1'
        assert id2 == 'widget-2'
        assert id3 == 'widget-3'

    def test_returns_unique_ids(self):
        """Should return unique IDs across multiple calls."""
        telar.widgets._widget_counter = 0
        ids = [get_widget_id() for _ in range(100)]
        assert len(ids) == len(set(ids))


class TestProcessWidgets:
    """Tests for process_widgets function."""

    @pytest.fixture(autouse=True)
    def reset_counter(self):
        """Reset widget counter before each test."""
        telar.widgets._widget_counter = 0

    def test_detects_carousel_widget(self):
        """Should detect and process carousel widget blocks."""
        text = """Some text before.

:::carousel
image: photo.jpg
alt: Description
:::

Some text after."""

        with patch('telar.widgets.parse_carousel_widget') as mock_parse, \
             patch('telar.widgets.render_widget_html') as mock_render:
            mock_parse.return_value = {'items': []}
            mock_render.return_value = '<div class="carousel">Rendered</div>'

            warnings = []
            result = process_widgets(text, 'test.md', warnings)

            mock_parse.assert_called_once()
            assert 'Some text before.' in result
            assert 'Some text after.' in result

    def test_detects_tabs_widget(self):
        """Should detect and process tabs widget blocks."""
        text = """:::tabs
## Tab 1
Content
:::"""

        with patch('telar.widgets.parse_tabs_widget') as mock_parse, \
             patch('telar.widgets.render_widget_html') as mock_render:
            mock_parse.return_value = {'tabs': []}
            mock_render.return_value = '<div class="tabs">Rendered</div>'

            warnings = []
            process_widgets(text, 'test.md', warnings)

            mock_parse.assert_called_once()

    def test_detects_accordion_widget(self):
        """Should detect and process accordion widget blocks."""
        text = """:::accordion
## Panel 1
Content
:::"""

        with patch('telar.widgets.parse_accordion_widget') as mock_parse, \
             patch('telar.widgets.render_widget_html') as mock_render:
            mock_parse.return_value = {'panels': []}
            mock_render.return_value = '<div class="accordion">Rendered</div>'

            warnings = []
            process_widgets(text, 'test.md', warnings)

            mock_parse.assert_called_once()

    def test_warns_unknown_widget_type(self):
        """Should warn about unknown widget types."""
        text = """:::unknown_widget
Some content
:::"""

        warnings = []
        result = process_widgets(text, 'test.md', warnings)

        assert any('Unknown widget type' in w['message'] for w in warnings)
        assert 'telar-widget-error' in result

    def test_preserves_non_widget_content(self):
        """Should preserve text that isn't a widget block."""
        text = """# Heading

Regular paragraph text.

- List item 1
- List item 2"""

        warnings = []
        result = process_widgets(text, 'test.md', warnings)

        assert result == text
        assert len(warnings) == 0

    def test_handles_multiple_widgets(self):
        """Should process multiple widget blocks in same text."""
        text = """:::tabs
## Tab 1
Content
:::

Some text between.

:::accordion
## Panel 1
Content
:::"""

        with patch('telar.widgets.parse_tabs_widget') as mock_tabs, \
             patch('telar.widgets.parse_accordion_widget') as mock_accordion, \
             patch('telar.widgets.render_widget_html') as mock_render:
            mock_tabs.return_value = {'tabs': []}
            mock_accordion.return_value = {'panels': []}
            mock_render.return_value = '<div>Widget</div>'

            warnings = []
            result = process_widgets(text, 'test.md', warnings)

            assert mock_tabs.call_count == 1
            assert mock_accordion.call_count == 1
            assert 'Some text between.' in result

    def test_widget_type_case_insensitive(self):
        """Should handle widget types case-insensitively."""
        text = """:::TABS
## Tab 1
Content
:::"""

        with patch('telar.widgets.parse_tabs_widget') as mock_parse, \
             patch('telar.widgets.render_widget_html') as mock_render:
            mock_parse.return_value = {'tabs': []}
            mock_render.return_value = '<div>Tabs</div>'

            warnings = []
            process_widgets(text, 'test.md', warnings)

            mock_parse.assert_called_once()

    def test_passes_file_path_to_parser(self):
        """Should pass file path context to widget parsers."""
        text = """:::carousel
image: photo.jpg
:::"""

        with patch('telar.widgets.parse_carousel_widget') as mock_parse, \
             patch('telar.widgets.render_widget_html') as mock_render:
            mock_parse.return_value = {'items': []}
            mock_render.return_value = '<div>Carousel</div>'

            warnings = []
            process_widgets(text, 'path/to/file.md', warnings)

            # Check file_path was passed to parser
            call_args = mock_parse.call_args
            assert 'path/to/file.md' in call_args[0]


class TestRenderWidgetHtml:
    """Tests for render_widget_html function."""

    def test_returns_error_on_missing_template(self):
        """Should return error HTML when template not found."""
        widget_data = {'items': []}
        result = render_widget_html('nonexistent_type', widget_data, 'widget-1')
        assert 'telar-widget-error' in result
        assert 'error' in result.lower()

    def test_includes_widget_id(self):
        """Should include widget_id when rendering template."""
        with patch('telar.widgets.Environment') as MockEnv:
            mock_template = MagicMock()
            mock_template.render.return_value = '<div id="widget-1">Content</div>'
            mock_env = MagicMock()
            mock_env.get_template.return_value = mock_template
            MockEnv.return_value = mock_env

            result = render_widget_html('tabs', {'tabs': []}, 'widget-1')

            # Verify widget_id was passed to template
            render_call = mock_template.render.call_args
            assert render_call[1]['widget_id'] == 'widget-1'

    def test_includes_base_url_placeholder(self):
        """Should include Jekyll base_url placeholder."""
        with patch('telar.widgets.Environment') as MockEnv:
            mock_template = MagicMock()
            mock_template.render.return_value = '<div>Content</div>'
            mock_env = MagicMock()
            mock_env.get_template.return_value = mock_template
            MockEnv.return_value = mock_env

            render_widget_html('tabs', {'tabs': []}, 'widget-1')

            render_call = mock_template.render.call_args
            assert render_call[1]['base_url'] == '{{ site.baseurl }}'
