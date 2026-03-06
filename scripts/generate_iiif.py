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

Version: v0.9.2-beta
"""

import os
import sys
import json
import shutil
from pathlib import Path

from iiif_utils import (
    check_dependencies, preprocess_image,
    generate_tiles_libvips, copy_base_image, create_single_canvas_manifest,
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

            # Need tiles if source URL is empty or not a URL
            if not source_url or not source_url.startswith('http'):
                objects_needing_tiles.append(object_id)

        return objects_needing_tiles

    except Exception as e:
        print(f"❌ Error loading objects.json: {e}")
        return None

def find_image_for_object(object_id, source_dir):
    """
    Find image file for a given object_id, checking multiple extensions (case-insensitive)

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

def generate_iiif_tiles(source_dir='telar-content/objects', output_dir='iiif/objects', base_url=None):
    """
    Generate IIIF tiles for objects listed in objects.json

    Args:
        source_dir: Directory containing source images (default: telar-content/objects)
        output_dir: Directory to output IIIF tiles and manifests (default: iiif/objects)
        base_url: Base URL for the site
    """
    backend = check_dependencies()
    if not backend:
        return False

    source_path = Path(source_dir)
    output_path = Path(output_dir)

    if not source_path.exists():
        # Check for old directory name (pre-v0.9.0)
        old_path = Path(str(source_dir).replace('telar-content/objects', 'telar-content/images'))
        if old_path.exists() and str(old_path) != str(source_path):
            print(f"⚠️  Found '{old_path}' — please rename to '{source_path}'")
            print(f"   Run: mv {old_path} {source_path}")
            source_path = old_path
        else:
            print(f"❌ Source directory {source_dir} does not exist.")
            print(f"   Please create it and add images, or use --source-dir to specify a different location.")
            return False

    # Get base URL from config or environment
    # Priority: --base-url flag > _config.yml > SITE_URL env var > localhost default
    if not base_url:
        base_url = (get_base_url_from_config() or
                    os.environ.get('SITE_URL') or
                    'http://localhost:4000')

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

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

    # Load objects from objects.json (CSV-driven approach)
    print("📋 Loading objects from objects.json...")
    objects_needing_tiles = load_objects_needing_tiles()

    if objects_needing_tiles is None:
        print("❌ Could not load objects.json")
        return False

    if not objects_needing_tiles:
        print("ℹ️  No objects need IIIF tiles (all use external manifests)")
        return True

    print(f"✓ Found {len(objects_needing_tiles)} objects needing tiles\n")

    # Process each object
    processed_count = 0
    skipped_count = 0

    for i, object_id in enumerate(objects_needing_tiles, 1):
        print(f"[{i}/{len(objects_needing_tiles)}] Processing {object_id}...")

        # Find image file for this object
        image_file = find_image_for_object(object_id, source_dir)

        if not image_file:
            print(f"  ⚠️  No image file found for {object_id}")
            print(f"      Checked: {object_id}.jpg, .jpeg, .png, .heic, .heif, .webp, .tif, .tiff, .pdf (case-insensitive)")
            skipped_count += 1
            print()
            continue

        print(f"  Found: {image_file.name}")

        # Output directory for this object
        object_output = output_path / object_id

        try:
            # Remove existing output if present
            if object_output.exists():
                shutil.rmtree(object_output)

            object_output.mkdir(parents=True, exist_ok=True)

            # PDF files get multi-page processing; everything else is a single image
            if image_file.suffix.lower() == '.pdf':
                try:
                    from process_pdf import process_pdf_object
                    process_pdf_object(image_file, object_output, object_id, base_url, backend)
                    print(f"  ✓ Generated multi-page tiles for {object_id}")
                    processed_count += 1
                except ImportError:
                    print(f"  ❌ PyMuPDF not installed — cannot process {image_file.name}")
                    skipped_count += 1
            else:
                generate_iiif_for_image(image_file, object_output, object_id, base_url, backend)
                print(f"  ✓ Generated tiles for {object_id}")
                processed_count += 1

            print()

        except Exception as e:
            print(f"  ❌ Error processing {image_file.name}: {e}")
            import traceback
            traceback.print_exc()
            skipped_count += 1
            print()
            continue

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

    args = parser.parse_args()

    success = generate_iiif_tiles(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        base_url=args.base_url
    )

    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
