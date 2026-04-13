"""
Unit Tests for Bibliography Widget

This module tests the bibliography widget parser and its integration with
the process_widgets pipeline. The bibliography widget lets authors apply
hanging-indent formatting to citation lists in panel content using the
:::bibliography ... ::: fenced-block syntax.

Each blank-line-separated block inside the fenced region becomes one entry
with hanging-indent styling applied via CSS.

Version: v1.1.0
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from telar.widgets import parse_bibliography_widget, process_widgets


class TestParseBibliographyWidget:
    """Tests for parse_bibliography_widget function."""

    def test_parses_single_entry(self):
        """Should parse a single entry into a list with one dict."""
        content = "Author, A. (2020). *Title*. Publisher."
        warnings = []
        result = parse_bibliography_widget(content, 'test.md', warnings)
        assert 'entries' in result
        assert len(result['entries']) == 1
        assert '<em>Title</em>' in result['entries'][0]['content_html']

    def test_parses_multiple_entries(self):
        """Should parse two blank-line-separated blocks into two entries."""
        content = "Author, A. (2020). *First Title*. Publisher.\n\nAuthor, B. (2019). *Second Title*. Journal."
        warnings = []
        result = parse_bibliography_widget(content, 'test.md', warnings)
        assert len(result['entries']) == 2

    def test_markdown_in_entries(self):
        """Should convert markdown italic and links in entries to HTML."""
        content = "*Italic title* and [link text](https://example.com)"
        warnings = []
        result = parse_bibliography_widget(content, 'test.md', warnings)
        assert '<em>Italic title</em>' in result['entries'][0]['content_html']
        assert '<a href=' in result['entries'][0]['content_html']

    def test_warns_empty_block(self):
        """Should append a warning when the content has no entries."""
        content = ""
        warnings = []
        result = parse_bibliography_widget(content, 'test.md', warnings)
        assert len(warnings) == 1
        warning = warnings[0]
        assert warning['type'] == 'widget'
        assert warning['widget_type'] == 'bibliography'
        assert 'no entries' in warning['message'].lower()

    def test_warns_empty_block_returns_empty_entries(self):
        """Should return empty entries list when content has no entries."""
        content = ""
        warnings = []
        result = parse_bibliography_widget(content, 'test.md', warnings)
        assert result['entries'] == []

    def test_preserves_multiline_entry(self):
        """A single entry spanning two lines without a blank line stays as one entry."""
        content = "Author, A. (2020). *Long title that\ncontinues on the next line*. Publisher."
        warnings = []
        result = parse_bibliography_widget(content, 'test.md', warnings)
        assert len(result['entries']) == 1

    def test_ignores_blank_only_blocks(self):
        """Blocks that are only whitespace should be skipped, not become entries."""
        content = "Entry one.\n\n\n\nEntry two."
        warnings = []
        result = parse_bibliography_widget(content, 'test.md', warnings)
        assert len(result['entries']) == 2

    def test_returns_dict_with_entries_key(self):
        """Return value must be a dict with an 'entries' key."""
        content = "Author, A. (2020). Title. Publisher."
        warnings = []
        result = parse_bibliography_widget(content, 'test.md', warnings)
        assert isinstance(result, dict)
        assert 'entries' in result

    def test_each_entry_has_content_html(self):
        """Each entry dict must have a 'content_html' key."""
        content = "Author, A. (2020). Title. Publisher."
        warnings = []
        result = parse_bibliography_widget(content, 'test.md', warnings)
        for entry in result['entries']:
            assert 'content_html' in entry


class TestBibliographyIntegration:
    """Integration tests for the bibliography widget in the full process_widgets pipeline."""

    def test_integration_process_widgets(self):
        """Full :::bibliography block through process_widgets produces HTML with telar-widget-bibliography."""
        text = ":::bibliography\nAuthor. *Title*.\n:::"
        warnings = []
        result = process_widgets(text, 'test.md', warnings)
        assert 'telar-widget-bibliography' in result
        assert len(warnings) == 0

    def test_integration_multiple_entries(self):
        """Two entries in a bibliography block produce two telar-bib-entry elements."""
        text = ":::bibliography\nAuthor A. *First*.\n\nAuthor B. *Second*.\n:::"
        warnings = []
        result = process_widgets(text, 'test.md', warnings)
        assert 'telar-widget-bibliography' in result
        assert result.count('telar-bib-entry') == 2

    def test_integration_empty_bibliography_warns(self):
        """Empty bibliography block produces a warning via process_widgets."""
        text = ":::bibliography\n\n:::"
        warnings = []
        process_widgets(text, 'test.md', warnings)
        assert any(w.get('widget_type') == 'bibliography' for w in warnings)
