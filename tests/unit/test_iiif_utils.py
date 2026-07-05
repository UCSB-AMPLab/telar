"""
Unit Tests for scripts/iiif_utils.py

Covers preprocess_image()'s palette-mode (P) handling, which must match
copy_base_image()'s approach: composite onto a white background using the
alpha resolved from any palette transparency index, rather than converting
straight to RGB and losing that transparency.

Version: v1.6.0
"""

import sys
import tempfile
from pathlib import Path

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from iiif_utils import preprocess_image


def _make_p_mode_fixture(tmp_path):
    """Build a palette-mode PNG: left half opaque red, right half transparent.

    Each half is a solid 16x16 block (JPEG re-encodes in 8x8 blocks, so a
    single pixel would be smeared by compression artifacts from its
    neighbour). The transparent half's palette colour is green, so if
    transparency is dropped rather than composited, that half comes out
    green — not white.
    """
    from PIL import Image

    img = Image.new('P', (32, 16))
    palette = [255, 0, 0] + [0, 255, 0] + [0] * (256 * 3 - 6)
    img.putpalette(palette)
    for x in range(32):
        for y in range(16):
            img.putpixel((x, y), 0 if x < 16 else 1)
    img.info['transparency'] = 1

    fixture_path = tmp_path / 'palette-fixture.png'
    img.save(fixture_path, 'PNG')
    return fixture_path


def test_preprocess_image_composites_palette_transparency_onto_white(tmp_path):
    """P-mode images with a transparency index must composite onto white,
    not render the raw (often unrelated) palette colour at that index."""
    fixture_path = _make_p_mode_fixture(tmp_path)

    processed_path, temp_path = preprocess_image(fixture_path)

    try:
        from PIL import Image
        with Image.open(processed_path) as result_img:
            result_img = result_img.convert('RGB')
            opaque_pixel = result_img.getpixel((4, 8))
            transparent_pixel = result_img.getpixel((28, 8))

        # Opaque red block survives (allow JPEG compression tolerance)
        assert opaque_pixel[0] > 200 and opaque_pixel[1] < 60 and opaque_pixel[2] < 60

        # The block at the transparency index must composite to white, not
        # render the raw green palette colour stored at that index
        assert all(channel > 200 for channel in transparent_pixel), (
            f"Expected white composite for transparent pixel, got {transparent_pixel}"
        )
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)


def test_preprocess_image_p_mode_without_transparency(tmp_path):
    """P-mode images with no transparency index still convert cleanly to RGB."""
    from PIL import Image

    img = Image.new('P', (2, 1))
    palette = [10, 20, 30] + [40, 50, 60] + [0] * (256 * 3 - 6)
    img.putpalette(palette)
    img.putpixel((0, 0), 0)
    img.putpixel((1, 0), 1)
    fixture_path = tmp_path / 'palette-no-alpha.png'
    img.save(fixture_path, 'PNG')

    processed_path, temp_path = preprocess_image(fixture_path)

    try:
        with Image.open(processed_path) as result_img:
            assert result_img.mode == 'RGB'
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
