"""
Unit Tests for Carousel Widget Parsing

This module tests the carousel widget parsing that transforms CommonMark-style
:::carousel blocks into structured data. Carousels display multiple images
with optional captions and credits, using --- separators between slides.

The parsing validates required fields (image), warns about missing alt text
for accessibility, and analyzes image aspect ratios to determine optimal
carousel height.

Version: v0.7.0-beta
"""

import sys
import os
import pytest
from unittest.mock import patch

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from csv_to_json import parse_carousel_widget


class TestParseCarouselWidget:
    """Tests for parse_carousel_widget function."""

    @pytest.fixture
    def mock_image_validation(self):
        """Mock validate_image_path to always return True."""
        with patch('telar.widgets.validate_image_path') as mock:
            mock.return_value = (True, '/full/path/to/image.jpg')
            yield mock

    @pytest.fixture
    def mock_image_dimensions(self):
        """Mock get_image_dimensions to return standard dimensions."""
        with patch('telar.widgets.get_image_dimensions') as mock:
            mock.return_value = (800, 600)  # Landscape aspect ratio
            yield mock

    def test_parses_single_item(self, mock_image_validation, mock_image_dimensions):
        """Should parse a carousel with one item."""
        content = """image: photo.jpg
alt: A description
caption: Photo caption"""
        warnings = []
        result = parse_carousel_widget(content, 'test.md', warnings)
        assert len(result['items']) == 1
        assert result['items'][0]['image'] == 'photo.jpg'
        assert result['items'][0]['alt'] == 'A description'

    def test_parses_multiple_items(self, mock_image_validation, mock_image_dimensions):
        """Should parse carousel with multiple items separated by ---."""
        content = """image: first.jpg
alt: First image

---

image: second.jpg
alt: Second image

---

image: third.jpg
alt: Third image"""
        warnings = []
        result = parse_carousel_widget(content, 'test.md', warnings)
        assert len(result['items']) == 3
        assert result['items'][0]['image'] == 'first.jpg'
        assert result['items'][1]['image'] == 'second.jpg'
        assert result['items'][2]['image'] == 'third.jpg'

    def test_warns_missing_image(self, mock_image_validation, mock_image_dimensions):
        """Should warn when item is missing required image field."""
        content = """alt: Just alt text
caption: No image here"""
        warnings = []
        result = parse_carousel_widget(content, 'test.md', warnings)
        assert len(result['items']) == 0
        assert any('missing required field: image' in w['message'] for w in warnings)

    def test_warns_missing_alt_text(self, mock_image_validation, mock_image_dimensions):
        """Should warn when alt text is missing (accessibility)."""
        content = """image: photo.jpg
caption: Has caption but no alt"""
        warnings = []
        result = parse_carousel_widget(content, 'test.md', warnings)
        assert len(result['items']) == 1
        assert any('missing alt text' in w['message'] for w in warnings)

    def test_warns_image_not_found(self, mock_image_dimensions):
        """Should warn when image file doesn't exist."""
        with patch('telar.widgets.validate_image_path') as mock:
            mock.return_value = (False, '/path/to/missing.jpg')
            content = """image: missing.jpg
alt: Missing image"""
            warnings = []
            result = parse_carousel_widget(content, 'test.md', warnings)
            assert any('image not found' in w['message'].lower() for w in warnings)

    def test_processes_caption_markdown(self, mock_image_validation, mock_image_dimensions):
        """Should process markdown in captions."""
        content = """image: photo.jpg
alt: Image
caption: **Bold** caption"""
        warnings = []
        result = parse_carousel_widget(content, 'test.md', warnings)
        assert '<strong>Bold</strong>' in result['items'][0]['caption']

    def test_processes_credit_markdown(self, mock_image_validation, mock_image_dimensions):
        """Should process markdown in credits."""
        content = """image: photo.jpg
alt: Image
credit: *Photographer Name*"""
        warnings = []
        result = parse_carousel_widget(content, 'test.md', warnings)
        assert '<em>Photographer Name</em>' in result['items'][0]['credit']

    def test_handles_empty_blocks(self, mock_image_validation, mock_image_dimensions):
        """Should skip empty blocks between separators."""
        content = """image: first.jpg
alt: First

---

---

image: second.jpg
alt: Second"""
        warnings = []
        result = parse_carousel_widget(content, 'test.md', warnings)
        assert len(result['items']) == 2

    def test_size_class_landscape(self, mock_image_validation):
        """Should set 'default' size class for landscape images."""
        with patch('telar.widgets.get_image_dimensions') as mock:
            mock.return_value = (800, 600)  # 0.75 aspect ratio
            content = """image: landscape.jpg
alt: Landscape image"""
            warnings = []
            result = parse_carousel_widget(content, 'test.md', warnings)
            assert result['size_class'] == 'default'

    def test_size_class_portrait(self, mock_image_validation):
        """Should set 'portrait' size class for portrait images."""
        with patch('telar.widgets.get_image_dimensions') as mock:
            mock.return_value = (600, 1000)  # 1.67 aspect ratio
            content = """image: portrait.jpg
alt: Portrait image"""
            warnings = []
            result = parse_carousel_widget(content, 'test.md', warnings)
            assert result['size_class'] == 'portrait'

    def test_size_class_compact(self, mock_image_validation):
        """Should set 'compact' size class for wide panoramas."""
        with patch('telar.widgets.get_image_dimensions') as mock:
            mock.return_value = (1000, 400)  # 0.4 aspect ratio
            content = """image: panorama.jpg
alt: Panorama image"""
            warnings = []
            result = parse_carousel_widget(content, 'test.md', warnings)
            assert result['size_class'] == 'compact'

    def test_size_class_tall(self, mock_image_validation):
        """Should set 'tall' size class for square to mild portrait."""
        with patch('telar.widgets.get_image_dimensions') as mock:
            mock.return_value = (800, 900)  # 1.125 aspect ratio
            content = """image: square.jpg
alt: Square-ish image"""
            warnings = []
            result = parse_carousel_widget(content, 'test.md', warnings)
            assert result['size_class'] == 'tall'

    def test_size_class_uses_max_aspect_ratio(self, mock_image_validation):
        """Should use maximum aspect ratio when images have different ratios."""
        call_count = [0]
        dimensions = [(800, 600), (600, 1000)]  # landscape, then portrait

        def mock_dimensions(path):
            result = dimensions[call_count[0]]
            call_count[0] += 1
            return result

        with patch('telar.widgets.get_image_dimensions', side_effect=mock_dimensions):
            content = """image: landscape.jpg
alt: Landscape

---

image: portrait.jpg
alt: Portrait"""
            warnings = []
            result = parse_carousel_widget(content, 'test.md', warnings)
            # Max aspect ratio is 1.67 (portrait), so should be 'portrait'
            assert result['size_class'] == 'portrait'

    def test_handles_colons_in_caption(self, mock_image_validation, mock_image_dimensions):
        """Should handle colons in caption and credit values."""
        content = """image: photo.jpg
alt: Image
caption: Time: 3:00 PM
credit: Source: Museum Archives"""
        warnings = []
        result = parse_carousel_widget(content, 'test.md', warnings)
        assert 'Time: 3:00 PM' in result['items'][0]['caption']
        assert 'Source: Museum Archives' in result['items'][0]['credit']
