"""
Contract Test for PDF Page Derivative Declarations

process_pdf_object() in scripts/process_pdf.py tiles each PDF page with
`vips dzsave`, then calls patch_info_json() to populate the page's
info.json `sizes` array, then calls generate_full_max() to write the
per-scaleFactor derivatives under full/. patch_info_json() builds
`sizes` by listing what is already on disk under full/
(_sizes_from_full_dir() in scripts/iiif_utils.py) — so any derivative
written after patch_info_json() runs is never declared. On the image
path (generate_tiles_libvips() in iiif_utils.py) generate_full_max()
runs first for exactly this reason; process_pdf.py has to follow the
same order.

vips 8.18 itself writes only one full-region derivative alongside
info.json — sized at ceil(width/4),ceil(height/4), the scaleFactor-4
thumbnail — and no sizes array. Everything else under full/ (the other
scaleFactor thumbnails, the width-only viewer thumbnail and its "w,h"
twin, the full-resolution copy) comes from generate_full_max(). This
test fakes `subprocess.run` to emulate that vips 8.18 output — CI does
not install libvips, and the fake also makes the test deterministic and
fast — while running every other line of process_pdf_object() for real,
so the ordering bug (or its fix) is exercised directly rather than
inferred.

The synthetic fixture is a single 1600x2000 PDF page, built with Pillow
at a resolution matching render_pdf_pages()'s default 200 DPI so the
page renders back to exactly 1600x2000 pixels. That's larger than the
512px tile size in both dimensions, so libvips's real dzsave (and this
fake) declares scaleFactors [1, 2, 4] — giving derivative sizes
1600x2000, 800x1000 and 400x500, plus the 96px-wide viewer thumbnail's
"w,h" twin at 96x120.

Unlike test_iiif_fallback_tile_sizes.py, nothing here is an optional
dependency to skip past — PyMuPDF and Pillow are both required by this
suite's environment — but the same discipline applies: if a precondition
this test relies on isn't met, it must fail loudly and say why, never
skip silently.

Version: v1.7.0
"""

import json
import math
import re
import sys
import types
from pathlib import Path

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))


def _make_fake_vips_dzsave():
    """Build a fake `subprocess.run` that emulates vips 8.18's dzsave.

    vips 8.18 writes info.json (placeholder id, no sizes array) and
    exactly one full-region derivative directory, sized at
    ceil(width/4),ceil(height/4) — the scaleFactor-4 thumbnail — under
    full/. Every other derivative under full/ has to come from
    generate_full_max() in the code under test, so the fake must not
    create them.

    Any subprocess.run call that isn't `vips dzsave` fails the test
    loudly rather than being silently accepted or ignored.
    """
    from PIL import Image

    def fake_run(cmd, capture_output=True, text=True):
        if cmd[:2] != ['vips', 'dzsave']:
            pytest.fail(f"Unexpected subprocess.run invocation: {cmd}")

        input_image = Path(cmd[2])
        output_root = Path(cmd[3])

        with Image.open(input_image) as im:
            width, height = im.size

        output_root.mkdir(parents=True, exist_ok=True)

        info = {
            "@context": "http://iiif.io/api/image/3/context.json",
            "id": "https://example.test/PLACEHOLDER",
            "type": "ImageService3",
            "protocol": "http://iiif.io/api/image",
            "profile": "level0",
            "width": width,
            "height": height,
            "tiles": [
                {"width": 512, "height": 512, "scaleFactors": [1, 2, 4]}
            ],
        }
        (output_root / 'info.json').write_text(json.dumps(info))

        fw = math.ceil(width / 4)
        fh = math.ceil(height / 4)
        region_dir = output_root / 'full' / f'{fw},{fh}' / '0'
        region_dir.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (fw, fh), (100, 100, 100)).save(
            region_dir / 'default.jpg', 'JPEG'
        )

        return types.SimpleNamespace(returncode=0, stdout='', stderr='')

    return fake_run


@pytest.fixture
def pdf_pipeline(tmp_path, monkeypatch):
    """Run process_pdf_object() end to end against a synthetic one-page PDF.

    subprocess.run is faked (see _make_fake_vips_dzsave) so the test
    doesn't need libvips installed. process_pdf.py imports subprocess
    inside process_pdf_object(), so patching the subprocess module's
    `run` attribute reaches that call.

    Returns the object's output_dir (iiif/objects/sample-pdf).
    """
    import subprocess

    from PIL import Image

    import process_pdf

    work_dir = tmp_path / 'work'
    work_dir.mkdir()
    # load_object_metadata() reads _data/objects.json relative to the
    # current working directory; none exists here, so it falls back to
    # an empty metadata dict, which is all process_pdf_object() needs
    # for this contract.
    monkeypatch.chdir(work_dir)

    pdf_path = work_dir / 'source.pdf'
    Image.new('RGB', (1600, 2000), (180, 180, 180)).save(
        pdf_path, 'PDF', resolution=200.0
    )

    monkeypatch.setattr(subprocess, 'run', _make_fake_vips_dzsave())

    output_dir = work_dir / 'iiif' / 'objects' / 'sample-pdf'
    process_pdf.process_pdf_object(pdf_path, output_dir, 'sample-pdf', 'https://example.test')

    return output_dir


def _load_page_one_info(output_dir):
    page_dir = output_dir / 'page-1'
    info = json.loads((page_dir / 'info.json').read_text())
    return page_dir, info


def test_every_declared_size_has_a_derivative_file_on_disk(pdf_pipeline):
    """Every entry in page-1/info.json's sizes array must resolve to a
    real file — a declared size nothing wrote is a 404 for a viewer."""
    page_dir, info = _load_page_one_info(pdf_pipeline)

    missing = [
        size for size in info['sizes']
        if not (page_dir / 'full' / f"{size['width']},{size['height']}" / '0' / 'default.jpg').exists()
    ]
    assert not missing, (
        f"info.json declares sizes with no derivative file on disk: {missing}"
    )


def test_sizes_cover_every_scale_factor_and_the_viewer_thumbnail(pdf_pipeline):
    """The declared sizes must match every scale-factor and viewer
    derivative actually written under full/ — not just whatever existed
    on disk at the moment patch_info_json() happened to run."""
    page_dir, info = _load_page_one_info(pdf_pipeline)

    declared = {(s['width'], s['height']) for s in info['sizes']}

    full_wh_dir_re = re.compile(r'^(\d+),(\d+)$')
    on_disk = set()
    for entry in (page_dir / 'full').iterdir():
        if not entry.is_dir() or entry.name == 'max':
            continue
        match = full_wh_dir_re.match(entry.name)
        if match:
            on_disk.add((int(match.group(1)), int(match.group(2))))

    assert declared == on_disk, (
        f"declared sizes {declared} do not match the full/ derivatives on disk {on_disk}"
    )
    assert declared == {(1600, 2000), (800, 1000), (400, 500), (96, 120)}


def test_root_info_json_matches_page_one(pdf_pipeline):
    """The root info.json (used for gallery thumbnails) is a straight
    copy of page-1's — it must stay byte-identical."""
    output_dir = pdf_pipeline
    root_bytes = (output_dir / 'info.json').read_bytes()
    page_bytes = (output_dir / 'page-1' / 'info.json').read_bytes()
    assert root_bytes == page_bytes
