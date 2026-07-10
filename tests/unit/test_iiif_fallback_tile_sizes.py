"""
Contract Test for the IIIF Fallback Backend's Tile Sizes

The pure-Python `iiif` package (used when libvips is not installed; see
detect_tile_backend() in scripts/iiif_utils.py) defaults its internal
osd_version to '2.0.0'. That default makes it write every cropped-region
tile under a width-only "{w}," directory, pairing a "{w},{h}" companion
only for the full-region case. This module's manifests always declare
IIIF Image API v3, and OpenSeadragon 6.x derives its tile request syntax
from that declared version — v3 always requests "{w},{h}" — so every
cropped tile 404s on a static server unless something renames those
directories. fix_fallback_region_sizes() in scripts/iiif_utils.py is that
something; _generate_tiles_iiif() in scripts/generate_iiif.py calls it
right after the library's own generate().

This test forces the fallback backend directly (bypassing libvips
detection, so it exercises the same path whether or not libvips happens
to be installed on the machine running the suite) on a synthetic fixture,
then replicates OpenSeadragon's own cropped-region tile-URL derivation
from the emitted info.json and asserts every derived URL resolves to a
file on disk.

The `full/max/0/default.jpg` canonical full-image path is part of the same
contract: OpenSeadragon requests it for the pyramid's whole-image top level,
and every backend must provide it (`generate_full_max()` in iiif_utils.py —
called from `generate_tiles_libvips`, `process_pdf.py`, and
`_generate_tiles_iiif` alike). This test asserts it alongside the
cropped-region URLs.

Version: v1.6.0
"""

import json
import math
import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))


def _require_iiif_library():
    """Fail loudly if the `iiif` pip package isn't installed.

    This test must exercise the real fallback backend, not a stand-in —
    if the package is missing, say so rather than skip silently.
    """
    try:
        import iiif.static  # noqa: F401
    except ImportError:
        pytest.fail(
            "The `iiif` pip package is not installed in this environment. "
            "Install it (`pip install iiif`) to run the fallback contract test."
        )


def _osd_expected_cropped_tile_urls(info):
    """Replicate OpenSeadragon 6.0.2's cropped-region tile URL derivation
    from a v3 info.json.

    For each declared tile scaleFactor, OSD tiles the full image in
    scaleFactor*tileWidth blocks (in full-resolution coordinates) and
    requests each block's region at a size equal to the ceiling of the
    block's dimensions divided by the scale factor. Because the declared
    API version is v3, OSD always requests sizes in "{w},{h}" form — never
    the width-only "{w}," canonical shorthand. Returns a list of relative
    paths (region/size/rotation/quality.format) that should exist on disk.

    Scoped to cropped-region tiles only — the "full" region's canonical
    `full/max` request is asserted separately in the test body (it is
    written by `generate_full_max()`, not by the region-tile pyramid).
    """
    width = info['width']
    height = info['height']
    urls = []

    for tile in info.get('tiles', []):
        tile_w = tile['width']
        for sf in tile['scaleFactors']:
            step = tile_w * sf
            x = 0
            while x < width:
                rw = min(step, width - x)
                sw = math.ceil(rw / sf)
                y = 0
                while y < height:
                    rh = min(step, height - y)
                    sh = math.ceil(rh / sf)
                    urls.append(f"{x},{y},{rw},{rh}/{sw},{sh}/0/default.jpg")
                    y += step
                x += step
    return urls


def test_fallback_backend_cropped_tiles_resolve_to_osd_v3_urls(tmp_path):
    """Every OSD-derived cropped-region tile URL for a v3 manifest must
    exist on disk.

    Forces the `iiif` fallback backend (_generate_tiles_iiif) on a
    synthetic 1200x900 fixture — big enough to produce at least one
    cropped-region scale level at the library's 512px tile size — and
    checks that fix_fallback_region_sizes() has already run by the time
    _generate_tiles_iiif() returns, leaving every cropped tile reachable
    at the "{w},{h}" path OSD will actually request.
    """
    _require_iiif_library()

    from PIL import Image
    from generate_iiif import _generate_tiles_iiif

    src = tmp_path / 'fixture.png'
    Image.new('RGB', (1200, 900), (120, 80, 40)).save(src, 'PNG')

    tiles_dir = tmp_path / 'iiif' / 'objects' / 'fixture-object'
    tiles_dir.mkdir(parents=True)

    _generate_tiles_iiif(src, tiles_dir, 'fixture-object', 'http://localhost:4000')

    info_path = tiles_dir / 'info.json'
    assert info_path.exists(), "iiif fallback backend did not write info.json"
    info = json.loads(info_path.read_text())

    assert info['@context'] == 'http://iiif.io/api/image/3/context.json', (
        "info.json must declare IIIF Image API v3 for this contract to apply"
    )

    expected_urls = _osd_expected_cropped_tile_urls(info)
    assert len(expected_urls) > 0, "fixture did not produce any cropped-region tiles"

    missing = [url for url in expected_urls if not (tiles_dir / url).exists()]
    assert not missing, (
        f"OSD would request these tile URLs, but no file exists on disk: {missing}"
    )

    # The canonical full-image request — OSD uses this for the pyramid's
    # whole-image top level under a v3 manifest.
    assert (tiles_dir / 'full' / 'max' / '0' / 'default.jpg').exists(), (
        "full/max/0/default.jpg missing — generate_full_max() must run for "
        "the fallback backend too"
    )

    # Confirm the rename actually happened rather than the fixture
    # coincidentally requiring no width-only directories: no cropped-region
    # directory (i.e. any region other than "full") should have a
    # width-only "{w}," child left over.
    leftover_width_only = []
    for region_dir in tiles_dir.iterdir():
        if not region_dir.is_dir() or region_dir.name == 'full':
            continue
        for size_dir in region_dir.iterdir():
            if size_dir.is_dir() and size_dir.name.endswith(',') and ',' not in size_dir.name[:-1]:
                leftover_width_only.append(str(size_dir.relative_to(tiles_dir)))
    assert not leftover_width_only, (
        f"width-only cropped-region directories were not canonicalized: {leftover_width_only}"
    )
