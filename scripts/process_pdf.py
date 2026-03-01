#!/usr/bin/env python3
"""
Process PDF Documents for IIIF Viewing

Some exhibition objects are not single images but multi-page documents
— a colonial-era legal text, a field notebook, a set of architectural
plans. This script takes a PDF file and turns it into something the
IIIF viewer can display: a set of tiled page images with deep-zoom
support, plus the manifests that tell the viewer what to show.

The process works like this. First, each page of the PDF is rendered
as a high-resolution JPEG image using PyMuPDF (at 200 DPI by default,
which produces crisp results for most archival scans). Then each page
image is sliced into tiles by libvips, exactly the same way
generate_iiif.py handles regular images — the shared tile-generation
functions live in iiif_utils.py.

The output for a PDF object looks like this:

    iiif/objects/my-document/
        manifest.json          ← multi-canvas manifest (full document)
        my-document.jpg        ← page 1 as thumbnail
        page-1/
            info.json          ← IIIF Image API for page 1
            manifest.json      ← single-canvas manifest (for story steps)
            full/max/0/default.jpg
            0,0,512,512/...    ← tiles
        page-2/
            ...
        page-42/
            ...

Two kinds of manifest are generated. The top-level manifest.json is a
multi-canvas IIIF Presentation v3 manifest — one canvas per page —
which the object page loads to show the full document with page
navigation. Each page-N/ directory also gets its own single-canvas
manifest.json, which story steps use when they reference a specific
page: the viewer loads just that one page's manifest and shows it like
any other single image.

This script is designed to be called from generate_iiif.py when it
detects a .pdf source file, but it can also be run standalone for
testing.

Version: v0.9.0-beta
"""

import json
import shutil
import tempfile
from pathlib import Path

from iiif_utils import (
    detect_tile_backend, generate_tiles_libvips, patch_info_json,
    generate_full_max, load_object_metadata,
)


def render_pdf_pages(pdf_path, output_dir, dpi=200):
    """Render each page of a PDF as a JPEG image.

    Args:
        pdf_path: Path to the source PDF file
        output_dir: Directory to write page images into
        dpi: Resolution for rendering (default 200)

    Returns:
        List of (page_number, image_path, width, height) tuples.
        Page numbers are 1-indexed.
    """
    import fitz

    doc = fitz.open(str(pdf_path))
    pages_info = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Scale from 72 DPI (PDF default) to target DPI
        scale = dpi / 72
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix)

        # Save as JPEG (1-indexed page numbers)
        page_number = page_num + 1
        image_path = Path(output_dir) / f"page-{page_number}.jpg"
        pixmap.save(str(image_path), output="jpeg")

        pages_info.append((page_number, image_path, pixmap.width, pixmap.height))

    doc.close()
    return pages_info


def generate_multicanvas_manifest(object_id, pages_info, base_url, metadata):
    """Build a IIIF Presentation v3 manifest with one canvas per page.

    This is the manifest the object page loads to show the full document
    with page navigation. Its structure matches the prototype at
    iiif/objects/leyesyordenanzas/manifest.json.

    Args:
        object_id: Object identifier
        pages_info: List of (page_number, image_path, width, height) tuples
        base_url: Base URL for the site
        metadata: Object metadata dict from objects.json

    Returns:
        The manifest as a Python dict, ready to be written as JSON.
    """
    title = metadata.get('title', object_id)

    canvases = []
    for page_number, _, width, height in pages_info:
        page_id = f"page-{page_number}"
        canvas = {
            "id": f"{base_url}/iiif/objects/{object_id}/canvas/p{page_number}",
            "type": "Canvas",
            "label": {
                "none": [f"Page {page_number}"]
            },
            "height": height,
            "width": width,
            "items": [
                {
                    "id": f"{base_url}/iiif/objects/{object_id}/canvas/p{page_number}/page",
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "id": f"{base_url}/iiif/objects/{object_id}/canvas/p{page_number}/annotation",
                            "type": "Annotation",
                            "motivation": "painting",
                            "body": {
                                "id": f"{base_url}/iiif/objects/{object_id}/{page_id}/full/max/0/default.jpg",
                                "type": "Image",
                                "format": "image/jpeg",
                                "height": height,
                                "width": width,
                                "service": [
                                    {
                                        "id": f"{base_url}/iiif/objects/{object_id}/{page_id}",
                                        "type": "ImageService3",
                                        "profile": "level0"
                                    }
                                ]
                            },
                            "target": f"{base_url}/iiif/objects/{object_id}/canvas/p{page_number}"
                        }
                    ]
                }
            ]
        }
        canvases.append(canvas)

    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": f"{base_url}/iiif/objects/{object_id}/manifest.json",
        "type": "Manifest",
        "label": {
            "en": [title]
        },
        "items": canvases
    }

    # Add metadata fields if available
    manifest_metadata = []
    if metadata.get('creator'):
        manifest_metadata.append({
            "label": {"en": ["Creator"]},
            "value": {"en": [metadata['creator']]}
        })
    if metadata.get('period'):
        manifest_metadata.append({
            "label": {"en": ["Period"]},
            "value": {"en": [metadata['period']]}
        })
    if manifest_metadata:
        manifest['metadata'] = manifest_metadata

    if metadata.get('description'):
        manifest['summary'] = {"en": [metadata['description']]}

    return manifest


def _create_page_manifest(page_dir, object_id, page_number, width, height, base_url, metadata):
    """Create a single-canvas manifest for one page.

    Story steps reference individual pages via these manifests. The
    viewer loads page-N/manifest.json and displays it like any other
    single-image object.
    """
    page_id = f"page-{page_number}"
    title = metadata.get('title', object_id)
    page_label = f"{title} — Page {page_number}"

    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "id": f"{base_url}/iiif/objects/{object_id}/{page_id}/manifest.json",
        "type": "Manifest",
        "label": {
            "en": [page_label]
        },
        "items": [
            {
                "id": f"{base_url}/iiif/objects/{object_id}/{page_id}/canvas",
                "type": "Canvas",
                "label": {
                    "en": [page_label]
                },
                "height": height,
                "width": width,
                "items": [
                    {
                        "id": f"{base_url}/iiif/objects/{object_id}/{page_id}/page",
                        "type": "AnnotationPage",
                        "items": [
                            {
                                "id": f"{base_url}/iiif/objects/{object_id}/{page_id}/annotation",
                                "type": "Annotation",
                                "motivation": "painting",
                                "body": {
                                    "id": f"{base_url}/iiif/objects/{object_id}/{page_id}/full/max/0/default.jpg",
                                    "type": "Image",
                                    "format": "image/jpeg",
                                    "height": height,
                                    "width": width,
                                    "service": [
                                        {
                                            "id": f"{base_url}/iiif/objects/{object_id}/{page_id}",
                                            "type": "ImageService3",
                                            "profile": "level0"
                                        }
                                    ]
                                },
                                "target": f"{base_url}/iiif/objects/{object_id}/{page_id}/canvas"
                            }
                        ]
                    }
                ]
            }
        ]
    }

    manifest_path = page_dir / 'manifest.json'
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)


def process_pdf_object(pdf_path, output_dir, object_id, base_url, backend):
    """Process a PDF into tiled IIIF pages with manifests.

    This is the main orchestrator, called by generate_iiif.py when it
    finds a .pdf file for an object. It renders the PDF pages, tiles
    each one, creates per-page and multi-canvas manifests, and copies
    page 1 as the thumbnail image.

    Args:
        pdf_path: Path to the source PDF file
        output_dir: Output directory for this object (e.g. iiif/objects/my-doc)
        object_id: Object identifier
        base_url: Base URL for the site
        backend: Tile backend name (currently only 'libvips' is supported
                 for PDF processing)
    """
    from PIL import Image

    # Load metadata for manifests
    metadata = load_object_metadata(object_id)

    # Render PDF pages to a temporary directory
    temp_dir = tempfile.mkdtemp(prefix=f'telar-pdf-{object_id}-')
    try:
        print(f"  Rendering PDF pages...")
        pages_info = render_pdf_pages(pdf_path, temp_dir)
        print(f"  ✓ Rendered {len(pages_info)} pages")

        # Process each page
        for page_number, image_path, width, height in pages_info:
            page_id = f"page-{page_number}"
            page_dir = output_dir / page_id

            # Generate tiles for this page
            # libvips expects to create the output directory itself via dzsave,
            # so we point it at the parent and use page_id as the identifier
            cmd_output_name = str(output_dir / page_id)

            import subprocess
            cmd = [
                'vips', 'dzsave',
                str(image_path),
                cmd_output_name,
                '--layout', 'iiif3',
                '--tile-size', '512',
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"vips dzsave failed for page {page_number}: {result.stderr}")

            # Clean up vips-properties.xml
            vips_props = output_dir / 'vips-properties.xml'
            if vips_props.exists():
                vips_props.unlink()

            # Post-process: patch info.json with page-specific URL
            patch_info_json(page_dir, f"{object_id}/{page_id}", base_url)

            # Generate full/max/0/default.jpg
            generate_full_max(image_path, page_dir)

            # Create per-page single-canvas manifest
            _create_page_manifest(page_dir, object_id, page_number, width, height, base_url, metadata)

            if page_number % 10 == 0 or page_number == len(pages_info):
                print(f"  ✓ Tiled page {page_number}/{len(pages_info)}")

        # Copy page 1 as the object's thumbnail image
        first_page_full = output_dir / 'page-1' / 'full' / 'max' / '0' / 'default.jpg'
        if first_page_full.exists():
            thumb_dest = output_dir / f"{object_id}.jpg"
            img = Image.open(first_page_full)
            img.save(str(thumb_dest), 'JPEG', quality=95)
            print(f"  ✓ Copied page 1 as {object_id}.jpg")

        # Create multi-canvas manifest for the full document
        manifest = generate_multicanvas_manifest(object_id, pages_info, base_url, metadata)
        manifest_path = output_dir / 'manifest.json'
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        print(f"  ✓ Created multi-canvas manifest ({len(pages_info)} pages)")

    finally:
        # Clean up temporary rendered page images
        shutil.rmtree(temp_dir, ignore_errors=True)
