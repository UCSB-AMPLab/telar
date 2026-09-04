#!/usr/bin/env python3
"""
Generate IIIF Image Tiles and Manifests

IIIF (International Image Interoperability Framework) is a standard for
serving high-resolution images over the web. Instead of loading one
enormous image file, the image is sliced into small tiles at multiple
zoom levels. The viewer requests only the tiles visible on screen,
enabling smooth deep-zoom into large images without overwhelming the
browser or network.

Telar supports two ways of serving images: external (the object's
source_url points to an existing IIIF server, e.g. a library's digital
collection — no tile generation needed) and self-hosted (the user
places image files in telar-content/objects/ and this script generates
static IIIF Level 0 tiles and a Presentation API v3 manifest for each
one).

The script reads objects.json to find which objects need tiles (those
without an external source URL), locates the source image for each,
and generates a directory of tile files plus a manifest.json that
the viewer can load. It handles format conversion (PNG, HEIC,
WebP, TIFF to JPEG), EXIF orientation correction, and transparency
removal.

The --base-url flag is important: tiles must be generated with the
correct URL prefix so the manifest points to the right location. For
local development, use the localhost URL; for production, use the
site's public URL.

Tile generation backends:
  - libvips (preferred): 28x faster. Uses `vips dzsave --layout iiif3`.
    Install: brew install vips (macOS) / apt-get install libvips-dev (Linux)
  - iiif library (fallback): Pure Python, no system dependencies.
    Install: pip install iiif

Version: v1.7.0
"""

import os
import sys
import re
import json
import shutil
from pathlib import Path

# Object IDs become filesystem path components (tile dirs, rmtree targets), so
# they must be a safe filename token. Same allowlist shape as the audio pipeline.
_SAFE_OBJECT_ID = re.compile(r'^[A-Za-z0-9_-]+$')

from iiif_utils import (
    check_dependencies, preprocess_image,
    generate_tiles_libvips, copy_base_image, create_single_canvas_manifest,
    fix_fallback_region_sizes, generate_full_max,
)


# ---------------------------------------------------------------------------
# iiif library backend (fallback)
# ---------------------------------------------------------------------------

def _generate_tiles_iiif(processed_path, tiles_dir, object_id, base_url):
    """Generate IIIF tiles using the Python iiif library."""
    from iiif.static import IIIFStatic

    parent_dir = tiles_dir.parent

    sg = IIIFStatic(
        dst=str(parent_dir),
        prefix=f"{base_url}/iiif/objects",
        tilesize=512,
        api_version='3.0'
    )
    sg.generate(src=str(processed_path), identifier=object_id)

    # Canonicalize cropped-region tile directories — see fix_fallback_region_sizes's
    # docstring in iiif_utils.py for why the library's own output needs this patch.
    fix_fallback_region_sizes(tiles_dir)

    # full/max/0/default.jpg — the canonical v3 full-image request, which
    # OpenSeadragon also uses for the pyramid's whole-image top level. The
    # iiif library does not write it; every backend must provide it.
    generate_full_max(processed_path, tiles_dir)


# ---------------------------------------------------------------------------
# Shared post-generation
# ---------------------------------------------------------------------------

def generate_iiif_for_image(image_path, output_dir, object_id, base_url, backend):
    """
    Generate IIIF tiles for a single image

    Args:
        image_path: Path to source image
        output_dir: Output directory for tiles (parent of object_id directory)
        object_id: Identifier for this object
        base_url: Base URL for the site
        backend: 'libvips' or 'iiif'
    """
    parent_dir = output_dir.parent
    tiles_dir = parent_dir / object_id

    # Preprocess image (shared by both backends)
    processed_path, temp_path = preprocess_image(image_path)

    try:
        if backend == 'libvips':
            generate_tiles_libvips(processed_path, tiles_dir, object_id, base_url)
        else:
            _generate_tiles_iiif(processed_path, tiles_dir, object_id, base_url)

        # Copy full-resolution image BEFORE cleaning up temp file
        copy_base_image(processed_path, tiles_dir, object_id)
    finally:
        # Clean up temporary file if created
        if temp_path and Path(temp_path).exists():
            Path(temp_path).unlink()

    # Create manifest wrapper for the viewer
    create_single_canvas_manifest(tiles_dir, object_id, image_path, base_url)

def load_objects_needing_tiles():
    """
    Load list of object_ids that need IIIF tiles generated from objects.json

    Returns:
        list: Object IDs that need self-hosted IIIF tiles (have no external source URL)
    """
    try:
        objects_json = Path('_data/objects.json')
        if not objects_json.exists():
            print("⚠️  objects.json not found - run csv_to_json.py first")
            return None

        with open(objects_json, 'r') as f:
            objects = json.load(f)

        # Find objects that need IIIF tiles (no external source URL/IIIF manifest)
        objects_needing_tiles = []
        for obj in objects:
            object_id = obj.get('object_id')

            # Check source_url first (v0.5.0+), fall back to iiif_manifest (v0.4.x)
            source_url = obj.get('source_url', '').strip()
            if not source_url:
                source_url = obj.get('iiif_manifest', '').strip()

            # Skip if no object_id
            if not object_id:
                continue

            # Reject object_ids that aren't a safe filename token before they
            # reach any tile-directory write or rmtree downstream.
            if not _SAFE_OBJECT_ID.match(str(object_id)):
                print(f"  [WARNING] Skipping object with unsafe object_id: {object_id!r}")
                continue

            # Need tiles if source URL is empty or not a URL
            if not source_url or not source_url.startswith('http'):
                objects_needing_tiles.append(object_id)

        return objects_needing_tiles

    except Exception as e:
        print(f"❌ Error loading objects.json: {e}")
        return None

def find_image_for_object(object_id, source_dir):
    """
    Find image file for a given object_id, trying each extension in both cases

    The stem is the object_id exactly as written: only the extension is tried
    in both cases. A file whose name differs from the object_id in any other
    way is not found here, and on a case-sensitive filesystem that includes a
    difference of capitalisation. macOS hides that; the build runs on Linux.
    Naming the near-match is `objects.py`'s job, at validation time.

    Args:
        object_id: Object identifier
        source_dir: Directory to search for images

    Returns:
        Path object if found, None otherwise
    """
    source_path = Path(source_dir)
    # Priority order: Common formats first, then newer/specialized formats
    image_extensions = ['.jpg', '.jpeg', '.png', '.heic', '.heif', '.webp', '.tif', '.tiff', '.pdf']

    for ext in image_extensions:
        # Check both lowercase and uppercase extensions
        for case_ext in [ext, ext.upper()]:
            image_path = source_path / f"{object_id}{case_ext}"
            if image_path.exists():
                return image_path

    return None

def get_base_url_from_config():
    """
    Read url and baseurl from _config.yml and combine them.

    Returns:
        Combined URL (e.g., "https://example.com/baseurl") or None if config can't be read
    """
    try:
        import yaml
        with open('_config.yml', 'r') as f:
            config = yaml.safe_load(f)

        url = config.get('url', '')
        baseurl = config.get('baseurl', '')

        if url:
            return url + baseurl
        return None
    except Exception as e:
        # Silently fail - caller will use fallback
        return None

def _resolve_base_url(base_url):
    """
    Settle the base URL the manifests will carry.

    Priority: the --base-url flag, then _config.yml, then the SITE_URL
    environment variable, then a localhost default.

    Args:
        base_url: Base URL passed by the caller, or None

    Returns:
        The base URL to generate with
    """
    if base_url:
        return base_url
    return (get_base_url_from_config() or
            os.environ.get('SITE_URL') or
            'http://localhost:4000')


def _print_run_banner(source_dir, output_dir, base_url, backend):
    """
    Print the header naming what this run is about to do.

    Args:
        source_dir: Directory containing source images
        output_dir: Directory the tiles and manifests go to
        base_url: Base URL the manifests will carry
        backend: 'libvips' or 'iiif'
    """
    print("=" * 60)
    print("IIIF Tile Generator for Telar")
    print("=" * 60)
    print(f"Source: {source_dir}")
    print(f"Output: {output_dir}")
    print(f"Base URL: {base_url}")
    print(f"Backend: {backend}" + (" (28x faster)" if backend == 'libvips' else " (fallback)"))

    # Show helpful message for local development
    if base_url and ('github.io' in base_url or base_url.startswith('https://')):
        # Extract baseurl from full URL for the hint
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        path = parsed.path if parsed.path != '/' else ''
        print(f"\nℹ️  Generating tiles for production URL")
        print(f"   For local development, use: --base-url http://localhost:4000{path}")

    print("=" * 60)
    print()


def _select_objects(filter_objects):
    """
    Choose the objects this run will generate tiles for.

    Args:
        filter_objects: Comma-separated string of object IDs, or None for all

    Returns:
        list: Object IDs to process, empty when there is nothing to do
        None: objects.json could not be read
    """
    # Load objects from objects.json (CSV-driven approach)
    objects_needing_tiles = load_objects_needing_tiles()

    if objects_needing_tiles is None:
        return None

    if not objects_needing_tiles:
        print("ℹ️  No objects need IIIF tiles (all use external manifests)")
        return []

    # Filter to requested object IDs if --objects was provided
    if filter_objects:
        requested = {o.strip() for o in filter_objects.split(',')}
        objects_needing_tiles = [o for o in objects_needing_tiles if o in requested]
        if not objects_needing_tiles:
            print(f"ℹ️  No matching objects found for: {filter_objects}")

    return objects_needing_tiles


def _generate_for_object(image_file, object_output, object_id, base_url, backend):
    """
    Run one source file through the pipeline its format calls for.

    Args:
        image_file: Path to the source file
        object_output: Output directory for this object
        object_id: Object identifier
        base_url: Base URL for the site
        backend: 'libvips' or 'iiif'

    Returns:
        'processed' or 'skipped'
    """
    # PDF files get multi-page processing; everything else is a single image
    if image_file.suffix.lower() == '.pdf':
        try:
            from process_pdf import process_pdf_object
            process_pdf_object(image_file, object_output, object_id, base_url)
            print(f"  ✓ Generated multi-page tiles for {object_id}")
            return 'processed'
        except ImportError:
            print(f"  ❌ PyMuPDF not installed — cannot process {image_file.name}")
            return 'skipped'

    generate_iiif_for_image(image_file, object_output, object_id, base_url, backend)
    print(f"  ✓ Generated tiles for {object_id}")
    return 'processed'


def _process_object(object_id, source_dir, output_path, base_url, backend):
    """
    Find one object's source file and rebuild its tile tree from scratch.

    A failure here is one object's, not the run's: it is reported and the
    caller moves on to the next.

    Args:
        object_id: Object identifier
        source_dir: Directory to search for the source file
        output_path: Parent directory of every object's tile tree
        base_url: Base URL for the site
        backend: 'libvips' or 'iiif'

    Returns:
        'processed', 'skipped', or 'rejected' for an out-of-bounds output path,
        which counts as neither
    """
    # Find image file for this object
    image_file = find_image_for_object(object_id, source_dir)

    if not image_file:
        print(f"  ⚠️  No image file found for {object_id}")
        print(f"      Checked: {object_id}.jpg, .jpeg, .png, .heic, .heif, .webp, .tif, .tiff, .pdf")
        print(f"      The name before the extension must match {object_id} exactly, including capitalisation.")
        print()
        return 'skipped'

    print(f"  Found: {image_file.name}")

    # Output directory for this object
    object_output = output_path / object_id

    # Boundary guard (belt-and-suspenders): never rmtree/mkdir outside the
    # output directory, whatever the object_id resolved to.
    if not object_output.resolve().is_relative_to(output_path.resolve()):
        print(f"  [WARNING] Skipping object with out-of-bounds output path: {object_id!r}")
        print()
        return 'rejected'

    try:
        # Remove existing output if present
        if object_output.exists():
            shutil.rmtree(object_output)

        object_output.mkdir(parents=True, exist_ok=True)

        outcome = _generate_for_object(image_file, object_output, object_id,
                                       base_url, backend)
        print()
        return outcome

    except Exception as e:
        print(f"  ❌ Error processing {image_file.name}: {e}")
        import traceback
        traceback.print_exc()
        print()
        return 'skipped'


def generate_iiif_tiles(source_dir='telar-content/objects', output_dir='iiif/objects', base_url=None, filter_objects=None):
    """
    Generate IIIF tiles for objects listed in objects.json

    Args:
        source_dir: Directory containing source images (default: telar-content/objects)
        output_dir: Directory to output IIIF tiles and manifests (default: iiif/objects)
        base_url: Base URL for the site
        filter_objects: Comma-separated string of object IDs to process (default: None = all)
    """
    backend = check_dependencies()
    if not backend:
        return False

    source_path = Path(source_dir)
    output_path = Path(output_dir)

    if not source_path.exists():
        print(f"❌ Source directory {source_dir} does not exist.")
        print(f"   Please create it and add images, or use --source-dir to specify a different location.")
        return False

    base_url = _resolve_base_url(base_url)

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    _print_run_banner(source_dir, output_dir, base_url, backend)

    print("📋 Loading objects from objects.json...")
    objects_needing_tiles = _select_objects(filter_objects)

    if objects_needing_tiles is None:
        print("❌ Could not load objects.json")
        return False

    if not objects_needing_tiles:
        return True

    print(f"✓ Found {len(objects_needing_tiles)} objects needing tiles\n")

    # Process each object
    processed_count = 0
    skipped_count = 0

    for i, object_id in enumerate(objects_needing_tiles, 1):
        print(f"[{i}/{len(objects_needing_tiles)}] Processing {object_id}...")

        outcome = _process_object(object_id, source_dir, output_path, base_url, backend)
        if outcome == 'processed':
            processed_count += 1
        elif outcome == 'skipped':
            skipped_count += 1

    print("=" * 60)
    print("✓ IIIF generation complete!")
    print(f"  Processed: {processed_count} objects")
    if skipped_count > 0:
        print(f"  Skipped: {skipped_count} objects (missing images or errors)")
    print(f"  Output directory: {output_dir}")
    print("=" * 60)
    return True

def main():
    """Main generation process"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate IIIF tiles and manifests for Telar objects (CSV-driven)'
    )
    parser.add_argument(
        '--source-dir',
        default='telar-content/objects',
        help='Source directory containing images and PDFs (default: telar-content/objects)'
    )
    parser.add_argument(
        '--output-dir',
        default='iiif/objects',
        help='Output directory for IIIF tiles (default: iiif/objects)'
    )
    parser.add_argument(
        '--base-url',
        help='Base URL for the site (default: from _config.yml or http://localhost:4000)'
    )
    parser.add_argument(
        '--objects',
        default=None,
        help='Comma-separated object IDs to process (default: all objects needing tiles)'
    )

    args = parser.parse_args()

    success = generate_iiif_tiles(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        base_url=args.base_url,
        filter_objects=args.objects,
    )

    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
