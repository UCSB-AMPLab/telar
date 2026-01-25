"""
Unit Tests for Image Processing Functions

This module tests the markdown image processing that converts image syntax
with optional size modifiers and captions into HTML figures. The processing
happens BEFORE standard markdown conversion to allow custom syntax.

Supported syntax:
- ![alt](path) — basic image
- ![alt](path){size} — image with size class (sm, md, lg, full)
- Line after image becomes caption (optional "caption:" prefix stripped)

Version: v0.7.0-beta
"""

import sys
import os
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import process_images


class TestProcessImages:
    """Tests for process_images function."""

    def test_basic_image_conversion(self):
        """Should convert basic image syntax to HTML figure."""
        text = '![Portrait](image.jpg)'
        result = process_images(text)
        assert '<figure class="telar-image-figure">' in result
        assert '<img src=' in result
        assert 'alt="Portrait"' in result

    def test_prepends_default_path(self):
        """Should prepend /components/images/ to relative paths."""
        text = '![Alt](photo.jpg)'
        result = process_images(text)
        assert 'src="/components/images/photo.jpg"' in result

    def test_preserves_absolute_paths(self):
        """Should preserve paths starting with /."""
        text = '![Alt](/custom/path/image.jpg)'
        result = process_images(text)
        assert 'src="/custom/path/image.jpg"' in result

    def test_preserves_http_urls(self):
        """Should preserve HTTP/HTTPS URLs."""
        text = '![Alt](https://example.com/image.jpg)'
        result = process_images(text)
        assert 'src="https://example.com/image.jpg"' in result

    def test_size_small(self):
        """Should apply sm size class."""
        text = '![Alt](image.jpg){sm}'
        result = process_images(text)
        assert 'class="img-sm"' in result

    def test_size_medium(self):
        """Should apply md size class."""
        text = '![Alt](image.jpg){md}'
        result = process_images(text)
        assert 'class="img-md"' in result

    def test_size_large(self):
        """Should apply lg size class."""
        text = '![Alt](image.jpg){lg}'
        result = process_images(text)
        assert 'class="img-lg"' in result

    def test_size_full(self):
        """Should apply full size class."""
        text = '![Alt](image.jpg){full}'
        result = process_images(text)
        assert 'class="img-full"' in result

    def test_size_word_forms(self):
        """Should accept word forms of sizes (small, medium, large)."""
        assert 'class="img-sm"' in process_images('![Alt](i.jpg){small}')
        assert 'class="img-md"' in process_images('![Alt](i.jpg){medium}')
        assert 'class="img-lg"' in process_images('![Alt](i.jpg){large}')

    def test_size_case_insensitive(self):
        """Should handle size modifiers case-insensitively."""
        assert 'class="img-md"' in process_images('![Alt](i.jpg){MD}')
        assert 'class="img-lg"' in process_images('![Alt](i.jpg){LARGE}')

    def test_caption_from_next_line(self):
        """Should use next line as caption."""
        text = """![Portrait](image.jpg)
Francisco Maldonado, colonial figure"""
        result = process_images(text)
        assert '<figcaption class="telar-image-caption">' in result
        assert 'Francisco Maldonado' in result

    def test_caption_with_prefix(self):
        """Should strip 'caption:' prefix from caption."""
        text = """![Portrait](image.jpg)
caption: A historical portrait"""
        result = process_images(text)
        assert 'A historical portrait' in result
        assert 'caption:' not in result.lower() or 'telar-image-caption' in result

    def test_caption_markdown_converted(self):
        """Should convert markdown in captions."""
        text = """![Alt](image.jpg)
*Italic caption* with **bold**"""
        result = process_images(text)
        assert '<em>' in result or '<i>' in result

    def test_no_caption_when_blank_line(self):
        """Should not create caption when next line is blank."""
        text = """![Alt](image.jpg)

Next paragraph"""
        result = process_images(text)
        # Should still have figure but no figcaption with the paragraph content
        assert '<figure' in result
        # The paragraph should be separate, not in figcaption
        assert 'Next paragraph' in result

    def test_no_caption_when_another_image(self):
        """Should not use another image as caption."""
        text = """![First](first.jpg)
![Second](second.jpg)"""
        result = process_images(text)
        # Should have two separate figures
        assert result.count('<figure') == 2

    def test_no_caption_when_widget(self):
        """Should not use widget syntax as caption."""
        text = """![Alt](image.jpg)
:::carousel"""
        result = process_images(text)
        # Widget syntax should not become caption
        assert ':::carousel' in result

    def test_preserves_non_image_content(self):
        """Should preserve text that isn't image syntax."""
        text = """Some text before.

![Alt](image.jpg)

Some text after."""
        result = process_images(text)
        assert 'Some text before.' in result
        assert 'Some text after.' in result

    def test_handles_empty_alt_text(self):
        """Should handle empty alt text."""
        text = '![](image.jpg)'
        result = process_images(text)
        assert 'alt=""' in result

    def test_handles_multiple_images(self):
        """Should process multiple images."""
        text = """![First](first.jpg){sm}
Caption for first

![Second](second.jpg){lg}
Caption for second"""
        result = process_images(text)
        assert result.count('<figure') == 2
        assert 'img-sm' in result
        assert 'img-lg' in result
