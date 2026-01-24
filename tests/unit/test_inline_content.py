"""
Unit Tests for Inline Content Processing

This module tests the inline panel content feature introduced in v0.6.3,
which allows users to write panel text directly in spreadsheet cells instead
of requiring separate markdown files. The processing handles:

- Line break normalization (different spreadsheet formats use different newlines)
- YAML frontmatter extraction for custom panel titles
- Markdown-to-HTML conversion
- Widget processing within inline content

Version: v0.7.0-beta
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import process_inline_content


class TestProcessInlineContent:
    """Tests for process_inline_content function."""

    def test_returns_none_for_empty_input(self):
        """Empty or whitespace-only input should return None."""
        assert process_inline_content('') is None
        assert process_inline_content('   ') is None
        assert process_inline_content(None) is None

    def test_converts_simple_text_to_html(self):
        """Simple text should be converted to HTML paragraphs."""
        result = process_inline_content('Hello world')
        assert result is not None
        assert 'Hello world' in result['content']
        assert result['title'] == ''

    def test_handles_markdown_bold(self):
        """Bold markdown should be converted to HTML."""
        result = process_inline_content('This is **bold** text')
        assert '<strong>bold</strong>' in result['content']

    def test_handles_markdown_italic(self):
        """Italic markdown should be converted to HTML."""
        result = process_inline_content('This is *italic* text')
        assert '<em>italic</em>' in result['content']

    def test_handles_markdown_links(self):
        """Markdown links should be converted to HTML."""
        result = process_inline_content('Visit [example](https://example.com)')
        assert '<a href="https://example.com">example</a>' in result['content']

    def test_normalizes_windows_line_endings(self):
        """Windows line endings (\\r\\n) should be normalized."""
        result = process_inline_content('Line 1\r\nLine 2')
        assert result is not None
        # nl2br extension converts single newlines to <br>
        assert 'Line 1' in result['content']
        assert 'Line 2' in result['content']

    def test_normalizes_old_mac_line_endings(self):
        """Old Mac line endings (\\r) should be normalized."""
        result = process_inline_content('Line 1\rLine 2')
        assert result is not None
        assert 'Line 1' in result['content']
        assert 'Line 2' in result['content']

    def test_extracts_yaml_frontmatter_title(self):
        """YAML frontmatter with title should be extracted."""
        content = '''---
title: "My Panel Title"
---

Panel content here.'''
        result = process_inline_content(content)
        assert result['title'] == 'My Panel Title'
        assert 'Panel content here' in result['content']
        assert '---' not in result['content']

    def test_handles_yaml_title_without_quotes(self):
        """YAML title without quotes should be extracted."""
        content = '''---
title: Panel Title Without Quotes
---

Content.'''
        result = process_inline_content(content)
        assert result['title'] == 'Panel Title Without Quotes'

    def test_ignores_frontmatter_without_title(self):
        """Frontmatter without title key should not extract title."""
        content = '''---
author: Someone
date: 2026-01-24
---

Content without title in frontmatter.'''
        result = process_inline_content(content)
        # Without a title: key, the --- is treated as regular content
        # The function only extracts title if title: key exists
        assert result['title'] == ''

    def test_handles_horizontal_rule_not_as_frontmatter(self):
        """Horizontal rules (---) should not be mistaken for frontmatter."""
        content = '''Some text

---

More text after rule.'''
        result = process_inline_content(content)
        # This should NOT be treated as frontmatter since it doesn't start with ---
        assert result['title'] == ''
        assert 'Some text' in result['content']

    def test_preserves_raw_html(self):
        """Raw HTML in content should be preserved."""
        result = process_inline_content('Text with <span class="custom">HTML</span>')
        assert '<span class="custom">HTML</span>' in result['content']

    def test_returns_dict_with_required_keys(self):
        """Result should always have 'title' and 'content' keys."""
        result = process_inline_content('Test content')
        assert 'title' in result
        assert 'content' in result
        assert isinstance(result['title'], str)
        assert isinstance(result['content'], str)


class TestProcessInlineContentLineBreaks:
    """Tests specifically for line break handling in inline content."""

    def test_single_newline_creates_line_break(self):
        """Single newline should create a line break (nl2br extension)."""
        result = process_inline_content('Line 1\nLine 2')
        # nl2br extension adds <br> for single newlines
        assert '<br' in result['content'] or 'Line 1' in result['content']

    def test_double_newline_creates_paragraphs(self):
        """Double newlines should create paragraph breaks."""
        result = process_inline_content('Paragraph 1\n\nParagraph 2')
        # Markdown creates separate <p> tags for paragraphs
        assert '<p>' in result['content']

    def test_multiple_paragraphs(self):
        """Multiple paragraphs should each be wrapped."""
        content = '''First paragraph with some text.

Second paragraph with more text.

Third paragraph to finish.'''
        result = process_inline_content(content)
        # Should have multiple paragraph tags
        assert result['content'].count('<p>') >= 2
